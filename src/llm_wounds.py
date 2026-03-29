"""
src/llm_wounds.py

LLM integration layer for the health/wound system.

Bridges the mechanical wound simulation (health_system.py) with the
LLM narrative engine (llm_client.py).  Three responsibilities:

1. BUILD CONTEXT — inject wound state into LLM action prompts so the
   LLM knows about current injuries when resolving custom actions.

2. PARSE TREATMENT — when the LLM's structured response indicates a
   medical/treatment action, map it to the correct mechanical
   treat_wound() call.

3. GENERATE NARRATIVE — after mechanical resolution, call the LLM to
   produce rich, skill-appropriate wound/treatment descriptions.

Flow for injury:
    Player types: "I try to jump across the ravine"
    → LLM resolves: outcome=failure, health_delta=-18, damage_type=blunt,
      wound_location=right leg
    → Engine: wound = tracker.apply_hit(18, "blunt", "r_thigh")
    → Engine: narrative = generate_wound_narrative(llm, wound, skill)
    → Display: "You misjudge the distance. Your right leg catches the
      edge and folds under you with a wet snap..."

Flow for treatment:
    Player has wound #5: gunshot to left thigh, bullet lodged
    Player types: "I heat my knife and dig the bullet out"
    → LLM resolves: treatment_action=extract, wound_target=left thigh
    → Engine: success, msg = tracker.treat_wound(5, "extract", ...)
    → Engine: narrative = generate_treatment_narrative(llm, wound, "extract", success, skill)
    → Display: "You clench your teeth and probe with the blade.
      After an agonizing minute, the flattened ball clinks into the pan..."

Integration:
    In engine.py, after calling llm.resolve_action():

        from src.llm_wounds import (
            apply_wound_from_response, apply_treatment_from_response,
            generate_wound_narrative, generate_treatment_narrative,
            build_wound_context,
        )
"""

from typing import Optional, List, Dict, Any, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.llm_client import LLMClient, LLMResponse
    from src.health_system import HealthTracker, DetailedWound


# ============================================================================
#  CONTEXT BUILDER — inject wound state into LLM action prompts
# ============================================================================

def build_wound_context(tracker: "HealthTracker") -> str:
    """
    Build a concise wound block to append to the LLM action prompt.
    Tells the LLM about current injuries so it can:
    - Reference them in custom actions ("the wound in my leg")
    - Recognize treatment attempts
    - Factor injuries into action outcomes
    """
    if not tracker.wounds:
        return "PLAYER INJURIES: None."

    lines = [
        f"PLAYER INJURIES (blood: {tracker.blood_pct*100:.0f}%, "
        f"pain: {tracker.total_pain:.0f}, "
        f"conscious: {'yes' if tracker.conscious else 'NO'}):"
    ]
    for w in tracker.wounds:
        tags = []
        if w.is_bleeding:
            tags.append(f"bleeding-{w.bleed_level}")
        if w.bandaged:
            tags.append("bandaged")
        if w.tourniquet:
            tags.append("tourniquet")
        if w.stitched:
            tags.append("stitched")
        if w.lodged:
            tags.append(f"{w.lodged} lodged")
        if w.bone_broken:
            bt = "compound fracture" if w.compound_fracture else "fracture"
            tags.append(bt)
        if w.infected:
            tags.append(f"infected-{w.infection_stage}")
        if w.dirty and not w.treated:
            tags.append("dirty/contaminated")

        tag_str = f" [{', '.join(tags)}]" if tags else ""
        from src.health_system import PART_DATA
        label = PART_DATA.get(w.part, {}).get("label", w.part)
        lines.append(f"  - Wound #{w.id}: {w.description} ({label}){tag_str}")

    return "\n".join(lines)


def build_clothing_context(worn) -> str:
    """
    Build clothing block for LLM context.
    Tells the LLM what the player is wearing so it can reference garments
    in custom actions and treatment.
    """
    if worn is None:
        return "WORN CLOTHING: Nothing."
    summary = worn.summary()
    return f"WORN CLOTHING:\n{summary}"


def action_prompt_wound_fields() -> str:
    """
    Additional JSON field specs to append to the action prompt.
    These tell the LLM to return treatment-specific fields when appropriate.
    """
    return (
        '  "treatment_action": string or null — if the player is treating a wound, '
        'one of: "bandage"|"tourniquet"|"clean"|"extract"|"stitch"|"set_bone"|'
        '"splint"|"cauterize"|"poultice" — null if not a medical action\n'
        '  "treatment_wound_part": string or null — body part of the wound being '
        'treated (e.g. "left thigh", "chest") — null if not treating\n'
        '  "wound_severity": "light"|"moderate"|"severe"|"critical" or null — '
        'if the player takes damage, how severe is the injury'
    )


# ============================================================================
#  TREATMENT INTENT PARSING
# ============================================================================

# Map LLM freeform descriptions to treatment types
_TREATMENT_KEYWORDS: Dict[str, List[str]] = {
    "bandage":    ["bandage", "wrap", "bind", "tie off", "dress the wound",
                   "tear cloth", "strip of shirt", "compress"],
    "tourniquet": ["tourniquet", "tie above", "restrict blood flow"],
    "clean":      ["clean", "wash", "rinse", "disinfect", "pour whiskey",
                   "pour alcohol", "scrub", "irrigate", "wipe"],
    "extract":    ["extract", "dig out", "remove bullet", "pull out",
                   "remove arrowhead", "remove splinter", "probe for"],
    "stitch":     ["stitch", "sew", "suture", "close the wound", "needle and thread"],
    "set_bone":   ["set the bone", "align the bone", "push it back", "realign"],
    "splint":     ["splint", "immobilize", "brace", "tie sticks"],
    "cauterize":  ["cauterize", "burn closed", "hot iron", "hot knife",
                   "sear", "brand the wound"],
    "poultice":   ["poultice", "herb", "moss", "clay pack", "mud pack",
                   "chew bark", "plantain leaf"],
}


def infer_treatment_type(action_text: str,
                          llm_treatment: Optional[str] = None) -> Optional[str]:
    """
    Determine treatment type from either the LLM's explicit field
    or by keyword matching the player's action text.

    Returns a treatment type string or None if not a medical action.
    """
    # Trust the LLM if it gave an explicit treatment
    if llm_treatment and llm_treatment in _TREATMENT_KEYWORDS:
        return llm_treatment

    # Keyword fallback
    text_lower = action_text.lower()
    for treatment, keywords in _TREATMENT_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return treatment

    return None


def find_target_wound(tracker: "HealthTracker",
                       wound_part_hint: Optional[str] = None,
                       action_text: str = "") -> Optional["DetailedWound"]:
    """
    Find the wound the player is trying to treat.

    Priority:
    1. LLM-specified body part → match wound on that part
    2. Keywords in action text → match wound
    3. Worst untreated bleeding wound (fallback)
    """
    from src.health_system import PART_DATA, _OLD_TO_NEW

    # Try LLM-specified part
    if wound_part_hint:
        hint = _OLD_TO_NEW.get(wound_part_hint.lower().replace(" ", "_"),
                                wound_part_hint.lower().replace(" ", "_"))
        for w in tracker.wounds:
            part_label = PART_DATA.get(w.part, {}).get("label", "").lower()
            if w.part == hint or hint in part_label:
                return w

    # Try keyword matching from action text
    text_lower = action_text.lower()
    for w in tracker.wounds:
        part_label = PART_DATA.get(w.part, {}).get("label", "").lower()
        if part_label in text_lower:
            return w
        # Check for wound-specific terms
        if w.lodged and w.lodged in text_lower:
            return w

    # Fallback: worst untreated bleeding wound
    bleeding = [w for w in tracker.wounds if w.is_bleeding and not w.treated]
    if bleeding:
        return max(bleeding, key=lambda w: w.active_bleed)

    # Fallback: any untreated wound
    untreated = [w for w in tracker.wounds if not w.treated]
    if untreated:
        return untreated[0]

    return tracker.wounds[0] if tracker.wounds else None


# ============================================================================
#  APPLY FROM LLM RESPONSE
# ============================================================================

def apply_wound_from_response(tracker: "HealthTracker",
                               response: "LLMResponse",
                               worn_equipment=None
                               ) -> Optional["DetailedWound"]:
    """
    When the LLM response indicates the player took damage, create a
    proper wound through the health system.

    Call this instead of the old `player.survival.health -= delta` pattern.
    Returns the created wound or None.
    """
    if not response.health_delta or response.health_delta >= 0:
        return None

    damage = abs(response.health_delta)

    # Map LLM damage types to health system types
    from src.health_system import DmgType
    dtype_map = {
        "blunt":    DmgType.BLUNT,
        "edged":    DmgType.SLASH,
        "piercing": DmgType.PIERCE,
        "explosive": DmgType.BLAST,
        "gunshot":  DmgType.GUNSHOT,
        "slash":    DmgType.SLASH,
        "fire":     DmgType.BURN,
        "bite":     DmgType.BITE,
    }
    dtype = dtype_map.get(response.damage_type or "blunt", DmgType.BLUNT)

    # Map LLM wound location to body part
    target = None
    if response.wound_location:
        from src.health_system import _OLD_TO_NEW
        target = _OLD_TO_NEW.get(
            response.wound_location.lower().replace(" ", "_"),
            response.wound_location.lower().replace(" ", "_"))

    wound = tracker.apply_hit(damage, dtype, target,
                               worn_equipment=worn_equipment)
    return wound


def apply_treatment_from_response(tracker: "HealthTracker",
                                    response: "LLMResponse",
                                    action_text: str,
                                    player_skill: int = 0,
                                    player_int: int = 10,
                                    has_tools: bool = False
                                    ) -> Optional[Tuple[bool, str, "DetailedWound"]]:
    """
    When the LLM response or action text indicates a treatment attempt,
    resolve it mechanically through the health system.

    Returns (success, message, wound) or None if not a treatment action.
    """
    # Determine treatment type
    llm_treatment = getattr(response, "treatment_action", None)
    treatment = infer_treatment_type(action_text, llm_treatment)
    if not treatment:
        return None

    # Find target wound
    wound_part = getattr(response, "treatment_wound_part", None)
    wound = find_target_wound(tracker, wound_part, action_text)
    if not wound:
        return None

    # Resolve mechanically
    success, msg = tracker.treat_wound(
        wound.id, treatment,
        skill=player_skill,
        intelligence=player_int,
        self_treatment=True,
        has_tools=has_tools,
    )

    return success, msg, wound


# ============================================================================
#  NARRATIVE GENERATION (LLM calls)
# ============================================================================

_WOUND_NARRATE_SYSTEM = """\
You are the narrator for a brutal frontier survival game set in 1849 America.
Generate a vivid, sensory, 2-3 sentence description of a wound being inflicted.
Be specific about the body part, the damage, and how it feels.
Write in second person present tense ("You feel...", "The blade catches...").
Do not soften or sanitize. Injuries are ugly and painful.
Use the mechanical wound data provided to ground your description in reality.
"""

_TREATMENT_NARRATE_SYSTEM = """\
You are the narrator for a brutal frontier survival game set in 1849 America.
Generate a vivid, sensory, 2-3 sentence description of a wound treatment attempt.
Be specific about what the character is doing, the tools used, and the physical
sensation. Write in second person present tense.
If the treatment failed, describe the failure honestly.
If it succeeded, describe the relief mixed with pain.
"""


def generate_wound_narrative(llm: "LLMClient",
                              wound: "DetailedWound",
                              cause: str = "",
                              medical_skill: int = 0) -> str:
    """
    After mechanical wound generation, call the LLM to produce a
    rich narrative description.

    cause: what caused the wound (e.g. "fell from cliff", "shot by bandit")
    medical_skill: affects how clinical vs visceral the description is

    Returns narrative string. Falls back to mechanical description if
    LLM unavailable.
    """
    if not llm.available:
        from src.health_system import describe_wound
        return describe_wound(wound, medical_skill)

    from src.health_system import PART_DATA
    part_label = PART_DATA.get(wound.part, {}).get("label", wound.part)

    prompt_lines = [
        f"WOUND DATA:",
        f"  Body part: {part_label}",
        f"  Wound type: {wound.wound_type}",
        f"  Severity: {wound.severity}",
        f"  Damage type: {wound.damage_type}",
        f"  Bleeding: {wound.bleed_level} ({wound.bleed_rate:.2f}/min)",
        f"  Pain: {wound.pain:.0f}/100",
    ]
    if wound.bone_broken:
        bt = "compound (bone protruding)" if wound.compound_fracture else "simple"
        prompt_lines.append(f"  Fracture: {bt}")
    if wound.lodged:
        prompt_lines.append(f"  Foreign object: {wound.lodged} lodged in tissue")
    if wound.nerve_damage:
        prompt_lines.append(f"  Nerve damage: numbness/loss of control")
    if cause:
        prompt_lines.append(f"  Cause: {cause}")

    if medical_skill >= 5:
        prompt_lines.append(
            "\nThe character has medical training — use slightly more clinical "
            "language mixed with the visceral sensation.")
    else:
        prompt_lines.append(
            "\nThe character has no medical training — describe in raw, "
            "visceral, layman's terms. Focus on sensation and fear.")

    prompt = "\n".join(prompt_lines)

    try:
        result = llm._chat(
            [
                {"role": "system", "content": _WOUND_NARRATE_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.70,
            max_tokens=200,
            json_mode=False,
        )
        return result.strip()
    except Exception:
        from src.health_system import describe_wound
        return describe_wound(wound, medical_skill)


def generate_treatment_narrative(llm: "LLMClient",
                                  wound: "DetailedWound",
                                  treatment_type: str,
                                  success: bool,
                                  action_text: str = "",
                                  medical_skill: int = 0) -> str:
    """
    After mechanical treatment resolution, call the LLM to produce
    a narrative description of the treatment attempt.
    """
    if not llm.available:
        outcome = "succeeds" if success else "fails"
        return f"You attempt to {treatment_type} the wound. The attempt {outcome}."

    from src.health_system import PART_DATA
    part_label = PART_DATA.get(wound.part, {}).get("label", wound.part)

    prompt_lines = [
        f"TREATMENT ATTEMPT:",
        f"  Action: {treatment_type}",
        f"  Success: {'YES' if success else 'NO'}",
        f"  Wound: {wound.description} on {part_label}",
        f"  Wound severity: {wound.severity}",
    ]
    if wound.lodged and treatment_type == "extract":
        prompt_lines.append(f"  Extracting: {wound.lodged}")
    if wound.bone_broken and treatment_type == "set_bone":
        bt = "compound" if wound.compound_fracture else "simple"
        prompt_lines.append(f"  Fracture type: {bt}")
    if action_text:
        prompt_lines.append(f"  Player's stated method: \"{action_text}\"")
    if medical_skill >= 5:
        prompt_lines.append("  Character has medical training.")
    else:
        prompt_lines.append("  Character has no medical training — crude frontier first aid.")

    prompt = "\n".join(prompt_lines)

    try:
        result = llm._chat(
            [
                {"role": "system", "content": _TREATMENT_NARRATE_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.70,
            max_tokens=200,
            json_mode=False,
        )
        return result.strip()
    except Exception:
        outcome = "succeeds" if success else "fails"
        return f"You attempt to {treatment_type} the wound. The attempt {outcome}."
