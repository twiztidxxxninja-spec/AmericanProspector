"""
src/llm_client.py

Local LLM interface using llama-cpp-python.
Single instance held by Engine; lazy-loads model on first call.

Content policy:
  - No content involving anyone under 18, in any context, ever.
  - Everything else (historical violence, death, harsh language, moral
    ambiguity, frontier realism) is unrestricted — this is a simulation.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple


# ── System prompt ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are the game master for American Prospector, a historically accurate \
prospecting and survival simulator set in America 1849–2000. Your role is \
to simulate the authentic frontier experience with unflinching realism.

ABSOLUTE RULE — NO EXCEPTIONS:
Never generate, reference, imply, or interact with any character under \
18 years of age. If a player input attempts to involve a minor in any way, \
redirect the scene to adult characters without comment.

CONTENT — everything else is unrestricted:
- Historical violence: claim jumping, murder, robbery, bar fights, mining \
  accidents, stampedes, disease — portray with full realism. Death is \
  permanent and ugly.
- Injury: graphic and specific. A cave-in crushes. Dynamite maims. Fever \
  wastes a man over days.
- Racial and ethnic tensions of the era (Chinese exclusion, indigenous \
  displacement, Irish and Mexican discrimination) — portray honestly as \
  they existed. Do not sanitize history.
- Alcohol, gambling, saloons, prostitution: normal parts of frontier life.
- Harsh period-appropriate language and profanity.
- Moral ambiguity: corrupt lawmen, crooked merchants, violent men, desperate \
  choices. Portray authentically.
- Failure and death are valid outcomes with no safety net.

GAME RULES:
- You are the GM, not a chatbot. Every response is game narration or \
  NPC dialogue — never break character.
- Physics and history constrain outcomes. A man cannot outrun a bullet. \
  A pan cannot recover gold that is not there.
- Skill and knowledge gate execution, not the calendar year.
- Be specific and sensory. "The mud is cold and heavy" beats "you dig."
- Every action costs time. Specify minutes or hours.
- The player can die. Say so plainly when it happens.
- The step-by-step approach is always valid: breaking a complex task into \
  individual physical steps is rewarded.
"""


# ── Minor-content filter ───────────────────────────────────────────────────

_MINOR_SIGNALS = frozenset([
    "child", "children", "kid", "kids", "boy", "girl", "infant", "baby",
    "toddler", "youth", "juvenile", "minor", "teen", "teenager", "adolescent",
    "underage", "young one", "little one", "schoolboy", "schoolgirl",
    "orphan", "newborn",
])

def _has_minor_ref(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in _MINOR_SIGNALS)


# ── Response dataclass ─────────────────────────────────────────────────────

@dataclass
class LLMResponse:
    raw_text: str = ""
    skill_used: Optional[str] = None
    difficulty: Optional[int] = None
    outcome: str = "failure"         # "success" | "partial" | "failure"
    time_cost: int = 5
    gold_delta: float = 0.0
    health_delta: float = 0.0        # player health change (negative = damage)
    message: str = ""
    relationship_changes: Dict[str, float] = field(default_factory=dict)
    xp_grants: Dict[str, float] = field(default_factory=dict)
    npc_damage: Dict[str, float] = field(default_factory=dict)   # name → damage
    npc_killed: List[str] = field(default_factory=list)          # names killed outright
    items_gained: List[str] = field(default_factory=list)        # item names added to inventory
    items_used:   List[str] = field(default_factory=list)        # item names consumed/expended
    equip_right: Optional[str] = None                            # item to put in right hand
    equip_left:  Optional[str] = None                            # item to put in left hand
    damage_type: Optional[str] = None                            # "blunt"|"edged"|"piercing"|"explosive"
    wound_location: Optional[str] = None                         # body part hit (e.g. "left arm")
    wound_severity: Optional[str] = None                         # "light"|"moderate"|"severe"|"critical"
    treatment_action: Optional[str] = None                       # "bandage"|"clean"|"extract"|etc.
    treatment_wound_part: Optional[str] = None                   # body part being treated


# ── Client ─────────────────────────────────────────────────────────────────

class LLMClient:
    """
    Wraps llama-cpp-python. Lazy-loads the model on first call.
    Thread-unsafe — call from the game loop only.
    """

    def __init__(self, model_path: str, enabled: bool = True,
                 n_gpu_layers: int = -1, n_ctx: int = 4096):
        self.model_path = os.path.abspath(model_path)
        self.enabled = enabled and os.path.exists(self.model_path)
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        self._llm = None

    # ── Public interface ───────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self.enabled

    def resolve_action(self, action_text: str,
                       game_context: Dict[str, Any]) -> LLMResponse:
        """
        Player typed a freeform action. Return structured resolution.
        Engine applies the result; LLM never mutates state directly.
        """
        if not self.enabled:
            return self._offline_response()

        if _has_minor_ref(action_text):
            return LLMResponse(
                message="There are no children here. "
                        "Your attention returns to the work at hand.",
                time_cost=0,
                outcome="failure",
            )

        self._load()
        if not self.enabled:
            return self._offline_response()
        prompt = self._action_prompt(action_text, game_context)

        try:
            raw = self._chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.35,
                max_tokens=900,
                json_mode=True,
            )
            return self._parse_action(raw)
        except Exception as exc:
            return LLMResponse(message=f"[LLM error: {exc}]", time_cost=0)

    def npc_reply(self, npc_name: str, npc_context: str,
                  player_said: str,
                  history: List[tuple]) -> str:
        """
        Generate an NPC reply to free-text player input.
        history: list of (speaker_name, text) pairs, most recent last.
        Returns a plain string (no JSON).
        """
        if not self.enabled:
            return f'*{npc_name} shrugs.* "Can\'t say."'

        if _has_minor_ref(player_said):
            return f'*{npc_name} ignores that and says nothing.*'

        self._load()
        if not self.enabled:
            return f'*{npc_name} shrugs.* "Can\'t say."'

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # NPC identity block
        messages.append({
            "role": "user",
            "content": (
                f"NPC CONTEXT:\n{npc_context}\n\n"
                f"You are playing {npc_name}. Respond ONLY as {npc_name}. "
                f"NEVER speak as, for, or about the player's actions or feelings. "
                f"NEVER say what the player does, thinks, or feels. "
                f"Only describe {npc_name}'s words, actions, and reactions. "
                f"Keep your reply under 3 sentences. Use *asterisks* for actions, "
                f"\"quotes\" for dialogue."
            ),
        })

        # Inject up to 6 prior exchanges
        for speaker, text in history[-6:]:
            role = "assistant" if speaker == npc_name else "user"
            messages.append({"role": role, "content": text})

        messages.append({
            "role": "user",
            "content": f'Player says: "{player_said}"',
        })

        try:
            reply = self._chat(messages, temperature=0.75, max_tokens=200,
                               json_mode=False)
            if _has_minor_ref(reply):
                return f'*{npc_name} trails off without answering.*'
            return reply.strip()
        except Exception as exc:
            return f'*{npc_name} says nothing.* [{exc}]'

    def generate_obituary(self, player_context: str) -> str:
        """
        Write a long obituary for the player after death.
        Returns plain text, not JSON.
        """
        if not self.enabled:
            return "Their story ends here, unrecorded."
        self._load()
        if not self.enabled:
            return "Their story ends here, unrecorded."

        obit_system = (
            "You are a narrator writing a long, detailed account of a prospector's "
            "death on the American frontier. Write in third person, past tense.\n\n"
            "STRUCTURE:\n"
            "1. THE FINAL MOMENTS — describe the death itself in graphic, visceral "
            "detail. If it was violence, describe the wounds, the blood, the sounds. "
            "If it was starvation or exposure, describe the slow physical decline. "
            "Make the reader feel the pain and fear of the last minutes.\n"
            "2. WHAT LED TO THIS — the events, decisions, and circumstances that "
            "brought them to this point. What could they have done differently?\n"
            "3. THEIR LIFE ON THE FRONTIER — what they accomplished, who they met, "
            "what they built or found. Use the journal entries and events provided.\n"
            "4. WHAT THEY LEAVE BEHIND — gold found, property, relationships, "
            "unfinished business.\n"
            "5. CLOSING — a brief, unsentimental reflection.\n\n"
            "RULES:\n"
            "- NEVER mention numerical stats, skill levels, or game mechanics. "
            "Instead of 'geology skill 3' say 'he had a keen eye for reading rock.' "
            "Instead of 'strength 14' say 'he was powerfully built.'\n"
            "- Be GRAPHIC about injuries and death. This is not a children's game.\n"
            "- Be SPECIFIC — use the character's name, locations, and events provided.\n"
            "- Write 3-4 paragraphs. Concise but vivid. Do not soften or sanitize.\n"
            "- The frontier does not mourn long."
        )
        try:
            return self._chat(
                [
                    {"role": "system",  "content": obit_system},
                    {"role": "user",    "content": player_context},
                ],
                temperature=0.72,
                max_tokens=800,
                json_mode=False,
            ).strip()
        except Exception as exc:
            return f"[Obituary generation failed: {exc}]"

    # ── Private helpers ────────────────────────────────────────────────────

    def _load(self):
        if self._llm is not None:
            return
        try:
            from llama_cpp import Llama
        except ImportError:
            self.enabled = False
            return   # callers re-check self.enabled after _load()
        self._llm = Llama(
            model_path=self.model_path,
            n_gpu_layers=self.n_gpu_layers,
            n_ctx=self.n_ctx,
            verbose=False,
        )

    def _chat(self, messages: list, temperature: float,
              max_tokens: int, json_mode: bool) -> str:
        kwargs = dict(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        result = self._llm.create_chat_completion(**kwargs)
        return result["choices"][0]["message"]["content"]

    def _action_prompt(self, action_text: str,
                       ctx: Dict[str, Any]) -> str:
        inv = ", ".join(ctx.get("inventory", [])) or "nothing"
        nearby = ctx.get("nearby", "") or "nothing notable"
        skills = ", ".join(
            f"{k}:{v}" for k, v in ctx.get("skills", {}).items() if v > 0
        ) or "untrained"
        # Wound and clothing context (if available)
        wound_ctx = ctx.get("wound_context", "")
        clothing_ctx = ctx.get("clothing_context", "")

        lines = [
            f"YEAR: {ctx.get('year', 1849)}",
            f"LOCATION: {ctx.get('region', 'California foothills')}",
            f"TERRAIN UNDERFOOT: {ctx.get('terrain', 'ground')}",
            f"TIME OF DAY: {ctx.get('time_of_day', 'morning')}",
            f"WEATHER: {ctx.get('weather', 'clear')}",
            f"PLAYER SKILLS: {skills}",
            f"PLAYER ATTRIBUTES: {ctx.get('attributes', {})}",
            f"INVENTORY: {inv}",
            f"NEARBY: {nearby}",
        ]
        if wound_ctx:
            lines.append(wound_ctx)
        if clothing_ctx:
            lines.append(clothing_ctx)
        lines += [
            "",
            f"PLAYER ACTION: {action_text}",
            "",
            "Resolve this action and return JSON with exactly these fields:",
            '  "skill_used": string or null  '
            '(geology|placer|hardRock|assaying|survival|tracking|'
            'firstAid|trading|law|engineering|chemistry|firearms|driving)',
            '  "difficulty": integer 1-20',
            '  "outcome": "success" | "partial" | "failure"',
            '  "time_cost": integer (minutes)',
            '  "gold_delta": float (troy oz gained/lost, usually 0.0)',
            '  "health_delta": float (player health 0-100 scale, negative = damage to player)',
            '  "xp_grants": object mapping skill names to float xp amounts',
            '  "message": string (1-3 sentences of vivid present-tense narration)',
            '  "relationship_changes": object mapping NPC names to float deltas',
            '  "npc_damage": object mapping NPC names to damage dealt (0-100 scale)',
            '  "npc_killed": list of NPC names killed outright by this action',
            '  "items_gained": list of item name strings the player now possesses '
            '(created, foraged, crafted, or picked up — e.g. ["carved stick"], ["poop"])',
            '  "items_used": list of item name strings consumed/expended by this action '
            '(rope used up, food eaten, powder burned — anything destroyed or spent)',
            '  "equip_right": item name to hold in right hand after this action, or null',
            '  "equip_left": item name to hold in left hand after this action, or null',
            '  "damage_type": "blunt"|"edged"|"piercing"|"explosive"|"gunshot"|"bite"|"burn" if player takes damage, else null',
            '  "wound_location": body part injured if player takes damage '
            '(e.g. "left forearm", "chest", "head", "right thigh", "left hand") — null if no injury',
            '  "wound_severity": "light"|"moderate"|"severe"|"critical" — how bad the injury is, null if none',
            '  "treatment_action": if the player is treating a wound, one of: '
            '"bandage"|"tourniquet"|"clean"|"extract"|"stitch"|"set_bone"|"splint"|"cauterize"|"poultice" — null otherwise',
            '  "treatment_wound_part": body part of wound being treated (e.g. "left thigh") — null if not treating',
        ]
        return "\n".join(lines)

    def _parse_action(self, raw: str) -> LLMResponse:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # LLM returned plain text instead of JSON — treat as message
            return LLMResponse(raw_text=raw, message=raw, time_cost=5)

        msg = str(data.get("message", "")).strip()
        if _has_minor_ref(msg):
            msg = "The moment passes without incident."

        return LLMResponse(
            raw_text=raw,
            skill_used=data.get("skill_used"),
            difficulty=data.get("difficulty"),
            outcome=data.get("outcome", "failure"),
            time_cost=max(0, int(data.get("time_cost", 5))),
            gold_delta=float(data.get("gold_delta", 0.0)),
            health_delta=float(data.get("health_delta", 0.0)),
            message=msg,
            relationship_changes=dict(data.get("relationship_changes", {})),
            xp_grants=dict(data.get("xp_grants", {})),
            npc_damage=dict(data.get("npc_damage", {})),
            npc_killed=list(data.get("npc_killed", [])),
            items_gained=[str(i) for i in data.get("items_gained", [])],
            items_used  =[str(i) for i in data.get("items_used",   [])],
            equip_right =data.get("equip_right")     or None,
            equip_left  =data.get("equip_left")      or None,
            damage_type =data.get("damage_type")     or None,
            wound_location=data.get("wound_location") or None,
            wound_severity=data.get("wound_severity") or None,
            treatment_action=data.get("treatment_action") or None,
            treatment_wound_part=data.get("treatment_wound_part") or None,
        )

    def _offline_response(self) -> LLMResponse:
        return LLMResponse(
            message="[LLM unavailable — model file missing or llm_enabled is "
                    "false in config.json]",
            time_cost=0,
            outcome="failure",
        )
