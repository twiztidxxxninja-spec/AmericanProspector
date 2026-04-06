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

def _get_system_prompt(year: int = 1849) -> str:
    """Return era-appropriate system prompt for LLM interactions."""
    if year < 1800:
        era_context = (
            f"The year is {year}. The setting is the Appalachian frontier — "
            f"Kentucky, Tennessee, Virginia. Long hunters disappear into the "
            f"wilderness for months, living off their rifles. Deerskins are "
            f"currency — a prime buck is worth a dollar. Native nations "
            f"(Shawnee, Cherokee) hunt these grounds and do not welcome "
            f"trespassers. Forts and trading posts are the only shelter. "
            f"Flintlock rifles and skinning knives are the tools. No steel "
            f"traps yet. No towns past the Appalachians. The Revolution rages "
            f"on the coast but here the war is between settlers and the land."
        )
    elif year < 1840:
        era_context = (
            f"The year is {year}. The setting is the Rocky Mountain fur trade. "
            f"Beaver pelts are the currency of the wilderness. Mountain men trap "
            f"the streams, trade at annual Rendezvous gatherings, and survive by "
            f"their wits and rifles. There are no towns west of St. Louis — only "
            f"forts, trapper camps, and Native villages. Flintlock rifles, steel "
            f"traps, and skinning knives are the tools of the trade. The wilderness "
            f"is vast, unmapped, and dangerous."
        )
    elif year < 1870:
        era_context = (
            f"The year is {year}. The setting is the American frontier during the "
            f"Gold Rush era. Prospectors flood California and the Western territories "
            f"seeking gold. Mining camps, boomtowns, and lawlessness define the age. "
            f"Percussion rifles and revolvers are standard. Placer mining, sluice boxes, "
            f"and hard rock mining drive the economy."
        )
    else:
        era_context = (
            f"The year is {year}. The American West is being settled and civilized. "
            f"Railroads connect the coasts. Mining has industrialized. Law and order "
            f"are taking hold, though the frontier remains rough."
        )

    return (
        f"You are the game master for American Prospector, a historically accurate "
        f"prospecting and survival simulator set on the American frontier. Your role is "
        f"to simulate the authentic frontier experience with unflinching realism.\n\n"
        f"ERA CONTEXT: {era_context}\n\n"
        f"ABSOLUTE RULE — NO EXCEPTIONS:\n"
        f"Never generate, reference, imply, or interact with any character under "
        f"18 years of age. If a player input attempts to involve a minor in any way, "
        f"redirect the scene to adult characters without comment.\n\n"
        f"CONTENT — everything else is unrestricted:\n"
        f"- Historical violence: claim jumping, murder, robbery, bar fights, mining "
        f"accidents, stampedes, disease — portray with full realism. Death is "
        f"permanent and ugly.\n"
        f"- Injury: graphic and specific. A cave-in crushes. Dynamite maims. Fever "
        f"wastes a man over days.\n"
        f"- Racial and ethnic tensions of the era (Chinese exclusion, indigenous "
        f"displacement, Irish and Mexican discrimination) — portray honestly as "
        f"they existed. Do not sanitize history.\n"
        f"- Alcohol, gambling, saloons, prostitution: normal parts of frontier life.\n"
        f"- Harsh period-appropriate language and profanity.\n"
        f"- Moral ambiguity: corrupt lawmen, crooked merchants, violent men, desperate "
        f"choices. Portray authentically.\n"
        f"- Failure and death are valid outcomes with no safety net.\n\n"
        f"GAME RULES:\n"
        f"- You are the GM, not a chatbot. Every response is game narration or "
        f"NPC dialogue — never break character.\n"
        f"- Physics and history constrain outcomes. A man cannot outrun a bullet. "
        f"A pan cannot recover gold that is not there.\n"
        f"- Skill and knowledge gate execution, not the calendar year.\n"
        f"- Be specific and sensory. \"The mud is cold and heavy\" beats \"you dig.\"\n"
        f"- Every action costs time. Specify minutes or hours.\n"
        f"- The player can die. Say so plainly when it happens.\n"
        f"- The step-by-step approach is always valid: breaking a complex task into "
        f"individual physical steps is rewarded."
    )


# ── Minor-content filter ───────────────────────────────────────────────────

_MINOR_SIGNALS = frozenset([
    "child", "children", "kid", "kids", "boy", "girl", "infant", "baby",
    "toddler", "youth", "juvenile", "minor", "teen", "teenager", "adolescent",
    "underage", "young one", "little one", "schoolboy", "schoolgirl",
    "orphan", "newborn",
])

def _has_minor_ref(text: str) -> bool:
    import re
    low = text.lower()
    return any(re.search(r'\b' + re.escape(w) + r'\b', low) for w in _MINOR_SIGNALS)


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
    LLM interface — supports local llama-cpp-python OR Claude API.
    Mode determined by config:
      llm_mode: "local" (default) — uses local GGUF model
      llm_mode: "api"  — uses Claude API via HTTP
    """

    def __init__(self, model_path: str = "", enabled: bool = True,
                 n_gpu_layers: int = -1, n_ctx: int = 4096,
                 mode: str = "local",
                 api_key: str = "", api_model: str = "claude-sonnet-4-20250514"):
        self.mode = mode
        self.api_key = api_key
        self.api_model = api_model

        if mode == "api" and api_key:
            self.enabled = enabled
            self.model_path = ""
        else:
            self.model_path = os.path.abspath(model_path) if model_path else ""
            self.enabled = enabled and bool(self.model_path) and os.path.exists(self.model_path)

        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        self._llm = None
        self.year = 1849  # current game year — updated by engine daily

    # ── Public interface ───────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self.enabled

    def set_year(self, year: int):
        """Update the game year for era-appropriate LLM prompts."""
        self.year = year

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
                    {"role": "system", "content": _get_system_prompt(self.year)},
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
                  history: List[tuple],
                  speech_direction: str = "",
                  mood_context: str = "",
                  lying_instruction: str = "") -> str:
        """
        Generate an NPC reply to free-text player input.
        history: list of (speaker_name, text) pairs, most recent last.
        speech_direction: how the NPC speaks (dialect, mannerisms).
        mood_context: NPC's current emotional/physical state.
        lying_instruction: whether NPC should be evasive about secrets.
        Returns a plain string (no JSON).
        """
        if not self.enabled:
            return f'*{npc_name} shrugs.* "Can\'t say."'

        if _has_minor_ref(player_said):
            return f'*{npc_name} ignores that and says nothing.*'

        self._load()
        if not self.enabled:
            return f'*{npc_name} shrugs.* "Can\'t say."'

        messages = [{"role": "system", "content": _get_system_prompt(self.year)}]

        # Build character-specific system prompt
        char_parts = [
            f"You are {npc_name}. Write what {npc_name} says and does.",
            f"Format: mix *actions in asterisks* with \"dialogue in quotes\".",
            f"Example: *{npc_name} scratches his chin.* \"Well now, that depends.\"",
        ]
        if speech_direction:
            char_parts.append(f"SPEECH STYLE: {speech_direction}")
        if mood_context:
            char_parts.append(f"YOUR CURRENT STATE: {mood_context}")
        if lying_instruction:
            char_parts.append(f"SECRET: {lying_instruction}")
        char_parts.append(
            "For casual exchanges keep it brief (1-2 sentences). "
            "For personal stories, confessions, teaching, or emotional moments "
            "write more (3-5 sentences). Match the depth of the question. "
            "Never break character. Never use modern language or slang."
        )

        messages.append({
            "role": "system",
            "content": "\n".join(char_parts),
        })
        messages.append({
            "role": "user",
            "content": f"NPC BACKGROUND:\n{npc_context}",
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
            reply = self._chat(messages, temperature=0.75, max_tokens=400,
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
            return _hardcoded_obituary(player_context)
        self._load()
        if not self.enabled:
            return _hardcoded_obituary(player_context)

        obit_system = (
            "You are writing the death account of a man who died on the American "
            "frontier. Third person, past tense. Write like Cormac McCarthy — spare, "
            "brutal, no sentimentality.\n\n"
            "STRUCTURE:\n"
            "1. THE DEATH — Reconstruct exactly what happened from the wound details "
            "and final events. Be visceral and specific. What did he see, feel, hear "
            "in those last moments? If shot, describe the bullet's path. If starved, "
            "describe the body shutting down. If bled out, describe the cold.\n\n"
            "2. THE LIFE — Who was he? What brought him west? Use the journal entries, "
            "people he knew, places he found. What did he accomplish? Was he a good man "
            "or a killer? Reference specific people and events from the data.\n\n"
            "3. WHAT REMAINS — Gold found, men killed, friends made. Was any of it "
            "worth it? One final unsentimental line.\n\n"
            "RULES:\n"
            "- NEVER mention stats, skill levels, HP, game mechanics, or numbers.\n"
            "- Use his NAME. Use SPECIFIC locations and people from the data.\n"
            "- If he killed people, name them. If he had friends, name them.\n"
            "- Be graphic about the death. This is not a children's game.\n"
            "- Write 4-6 paragraphs. Dense and vivid.\n"
            "- End with a single short sentence. Cold."
        )
        try:
            return self._chat(
                [
                    {"role": "system",  "content": obit_system},
                    {"role": "user",    "content": player_context},
                ],
                temperature=0.75,
                max_tokens=1200,
                json_mode=False,
            ).strip()
        except Exception as exc:
            return f"[Obituary generation failed: {exc}]"

    def summarize_conversation(self, npc_name: str,
                                history: List[tuple],
                                npc_context: str) -> str:
        """
        Summarize a conversation into 1-2 factual sentences for NPC memory.
        history: list of (speaker_name, text) pairs.
        Returns empty string if conversation was too short to summarize.
        """
        if len(history) < 2:
            return ""

        transcript = "\n".join(f"{speaker}: {text}" for speaker, text in history[-8:])

        if not self.enabled:
            # Template fallback — extract last player line as topic
            player_lines = [t for s, t in history if s == "player"]
            topic = player_lines[-1][:60] if player_lines else "various matters"
            return f"Spoke with the player about {topic}."

        self._load()
        if not self.enabled:
            return f"Had a conversation with the player."

        messages = [
            {"role": "system", "content": (
                f"Summarize this conversation from {npc_name}'s perspective "
                f"in 1-2 factual sentences. Focus on: what topics were discussed, "
                f"what the player revealed about themselves, any promises or deals "
                f"made, and the emotional tone. Write as a memory entry, not dialogue. "
                f"Example: 'The player asked about gold prospects near the river. "
                f"Seemed experienced with placer mining. Mentioned coming from Ohio.'"
            )},
            {"role": "user", "content": f"NPC: {npc_name}\n\nCONVERSATION:\n{transcript}"},
        ]
        try:
            return self._chat(messages, temperature=0.3, max_tokens=150,
                              json_mode=False).strip()
        except Exception:
            return f"Had a conversation with the player."

    def generate_letter_reply(self, npc_name: str,
                               npc_context: str,
                               player_letter_body: str) -> str:
        """
        Generate an NPC's reply to a personal letter from the player.
        Returns the reply letter body text.
        """
        if not self.enabled:
            return (f"Dear friend,\n\nReceived your letter. All is well here. "
                    f"Hope to see you on the trail.\n\nYours,\n{npc_name}")

        self._load()
        if not self.enabled:
            return (f"Dear friend,\n\nThank you for writing. Things are much "
                    f"the same here.\n\nYours truly,\n{npc_name}")

        messages = [
            {"role": "system", "content": (
                f"You are {npc_name}, writing a reply letter on the American "
                f"frontier in the 1849-1860s era. Write in first person as "
                f"{npc_name}. Reply specifically to what the player wrote — "
                f"address their questions, respond to their news, share your "
                f"own updates based on your background and personality. "
                f"Keep it 3-6 sentences. Sign with your name. "
                f"Write naturally, as a real person of this era would."
            )},
            {"role": "user", "content": f"YOUR BACKGROUND:\n{npc_context}"},
            {"role": "user", "content": (
                f"THE PLAYER WROTE YOU THIS LETTER:\n\n{player_letter_body}\n\n"
                f"Write your reply letter."
            )},
        ]
        try:
            reply = self._chat(messages, temperature=0.72, max_tokens=300,
                               json_mode=False).strip()
            if _has_minor_ref(reply):
                return (f"Dear friend,\n\nGood to hear from you. Things keep on "
                        f"here as they do.\n\nYours,\n{npc_name}")
            return reply
        except Exception:
            return (f"Dear friend,\n\nReceived your letter. All is well here. "
                    f"Hope to see you on the trail.\n\nYours,\n{npc_name}")

    # ── Private helpers ────────────────────────────────────────────────────

    def _load(self):
        if self._llm is not None or self.mode == "api":
            return
        try:
            from llama_cpp import Llama
        except ImportError:
            self.enabled = False
            return   # callers re-check self.enabled after _load()
        if not self.model_path or not os.path.exists(self.model_path):
            self.enabled = False
            return
        self._llm = Llama(
            model_path=self.model_path,
            n_gpu_layers=self.n_gpu_layers,
            n_ctx=self.n_ctx,
            verbose=False,
        )

    def _chat(self, messages: list, temperature: float,
              max_tokens: int, json_mode: bool) -> str:
        if self.mode == "api":
            return self._chat_api(messages, temperature, max_tokens, json_mode)
        # Local llama-cpp
        kwargs = dict(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        result = self._llm.create_chat_completion(**kwargs)
        choices = result.get("choices", [])
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "")

    def _chat_api(self, messages: list, temperature: float,
                  max_tokens: int, json_mode: bool) -> str:
        """Call Claude API via HTTP."""
        import urllib.request
        import json as _json

        # Convert messages to Anthropic format
        # Anthropic uses "system" separately from "messages"
        system_text = ""
        user_messages = []
        for m in messages:
            if m["role"] == "system":
                system_text += m["content"] + "\n"
            else:
                user_messages.append({
                    "role": m["role"],
                    "content": m["content"],
                })
        # Ensure alternating user/assistant — Anthropic requires this
        if not user_messages:
            user_messages = [{"role": "user", "content": "respond"}]

        payload = {
            "model": self.api_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": user_messages,
        }
        if system_text:
            payload["system"] = system_text.strip()

        body = _json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = _json.loads(resp.read().decode())
            # Anthropic response format
            content = data.get("content", [])
            if content and isinstance(content, list):
                return content[0].get("text", "")
            return ""
        except Exception as exc:
            return f"[API error: {exc}]"

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


def _hardcoded_obituary(context: str) -> str:
    """Generate a templated obituary from the player context string."""
    import re

    def _extract(label):
        m = re.search(rf"{label}:\s*(.+?)(?:\n|$)", context)
        return m.group(1).strip() if m else ""

    name = _extract("CHARACTER") or "The prospector"
    first = name.split(",")[0]
    year = _extract("YEAR OF DEATH") or _extract("YEAR") or "1849"
    region = _extract("LOCATION") or "the frontier"
    cause = _extract("CAUSE OF DEATH") or "unknown causes"
    gold = _extract("GOLD ACCUMULATED") or "0"
    cash = _extract("CASH ON PERSON") or "$0"
    days = _extract("DAYS SURVIVED") or "?"
    people_killed_str = _extract("PEOPLE KILLED")
    animals = _extract("ANIMALS KILLED") or "0"
    people_met = _extract("PEOPLE MET") or "0"

    # Extract wound lines
    wounds = []
    in_wounds = False
    for line in context.split("\n"):
        if "WOUNDS AT TIME OF DEATH" in line:
            in_wounds = True
            continue
        if in_wounds:
            if line.strip().startswith("-"):
                wounds.append(line.strip().lstrip("- "))
            elif line.strip() and not line.startswith(" "):
                break

    # Extract known people names
    known = []
    in_people = False
    for line in context.split("\n"):
        if "PEOPLE KNOWN:" in line:
            in_people = True
            continue
        if in_people:
            if line.strip() and line.strip()[0] != " " and ":" in line:
                break
            name_match = re.match(r"\s+(\S.+?)\s*\(", line)
            if name_match:
                known.append(name_match.group(1).strip())

    # Death paragraph
    wound_desc = ""
    if wounds:
        wound_desc = f" {wounds[0].capitalize()}"
        if len(wounds) > 1:
            wound_desc += f". {wounds[1].capitalize()}"
        wound_desc += "."

    para1 = (f"{first} died in {region}. {cause.capitalize()}.{wound_desc} "
             f"It took {days} days on the frontier to kill him.")

    # Life paragraph
    gold_f = 0.0
    try:
        gold_f = float(gold.split()[0])
    except (ValueError, IndexError):
        pass

    killed_names = [n.strip() for n in people_killed_str.split(",")
                    if n.strip() and n.strip().lower() != "none"] if people_killed_str else []

    life_parts = []
    if gold_f > 5.0:
        life_parts.append(f"He pulled {gold} of gold from the earth")
    elif gold_f > 0.5:
        life_parts.append(f"He found a little gold — {gold}")
    else:
        life_parts.append("He never found much gold")

    if killed_names:
        if len(killed_names) == 1:
            life_parts.append(f"killed {killed_names[0]}")
        else:
            life_parts.append(f"killed {len(killed_names)} men")

    if known and len(known) >= 2:
        life_parts.append(f"knew men like {known[0]} and {known[1]}")
    elif known:
        life_parts.append(f"knew {known[0]}")

    para2 = ". ".join(life_parts) + f". He carried {cash} when he died."

    # Closing
    if killed_names and len(killed_names) >= 3:
        para3 = ("He was not a good man. But the frontier does not sort men "
                 "by their goodness. It sorts them by whether they are alive or dead.")
    elif gold_f > 10.0:
        para3 = ("He found what he came for. It bought him nothing in the end. "
                 "The claim will be restaked by morning.")
    elif int(days) > 365 if days.isdigit() else False:
        para3 = ("He lasted longer than most. A year and more in country that "
                 "kills men in weeks. The land outlasted him anyway.")
    else:
        para3 = ("By tomorrow the tent will be taken down, the name forgotten. "
                 "The land endures. The people pass through it like weather.")

    return f"{para1}\n\n{para2}\n\n{para3}"
