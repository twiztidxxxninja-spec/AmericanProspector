"""
src/health_system.py

Deep wound and health simulation for American Prospector.
Combat is dangerous and consequential — every wound is specific,
persistent, and meaningful.

Architecture:
    1. Mechanical resolution determines hit location, wound type, severity
    2. Wound tracks bleeding, pain, infection, lodged objects, fractures
    3. HealthTracker manages blood, all wounds, shock, consciousness
    4. Treatment system handles bandaging, cleaning, extraction, bone setting
    5. Skill-gated descriptions — low skill sees "bad cut", doctor sees details
    6. LLM generates narrative flavor after mechanical result is determined

Backward compatibility:
    HealthTracker exposes the same public API as the old CreatureWounds
    (apply_hit, tick, bandage_worst, blood_pct, alive, etc.) so existing
    engine/combat code works without changes.

Integration:
    player.py:   player.wounds = HealthTracker(MAX_BLOOD["human"])
    combat.py:   wound = player.wounds.apply_hit(dmg, dtype, part)
    clothing.py: dmg = damage_after_clothing(raw, part, player.worn)
    engine.py:   msgs = player.wounds.tick(minutes)
    llm:         context = describe_wound_for_llm(wound, medical_skill)
"""

import random
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any


# ============================================================================
#  BODY PARTS (14 hit locations)
# ============================================================================

class BP:
    """Body part constants."""
    HEAD        = "head"
    NECK        = "neck"
    CHEST       = "chest"
    ABDOMEN     = "abdomen"
    L_UPPER_ARM = "l_upper_arm"
    R_UPPER_ARM = "r_upper_arm"
    L_FOREARM   = "l_forearm"
    R_FOREARM   = "r_forearm"
    L_HAND      = "l_hand"
    R_HAND      = "r_hand"
    L_THIGH     = "l_thigh"
    R_THIGH     = "r_thigh"
    L_LOWER_LEG = "l_lower_leg"
    R_LOWER_LEG = "r_lower_leg"
    GROIN       = "groin"


ALL_BODY_PARTS = [
    BP.HEAD, BP.NECK, BP.CHEST, BP.ABDOMEN, BP.GROIN,
    BP.L_UPPER_ARM, BP.R_UPPER_ARM, BP.L_FOREARM, BP.R_FOREARM,
    BP.L_HAND, BP.R_HAND,
    BP.L_THIGH, BP.R_THIGH, BP.L_LOWER_LEG, BP.R_LOWER_LEG,
]

# Full data per body part
PART_DATA: Dict[str, dict] = {
    BP.HEAD:        {"label": "Head",           "hit_w": 5,  "vital": True,  "arterial": True,
                     "treat_diff": 3, "clothing": "head",
                     "impair": "severe head trauma — vision blurred, dizzy"},
    BP.NECK:        {"label": "Neck",           "hit_w": 3,  "vital": True,  "arterial": True,
                     "treat_diff": 5, "clothing": "neck",
                     "impair": "neck wound — extreme pain, choking risk"},
    BP.CHEST:       {"label": "Chest",          "hit_w": 20, "vital": True,  "arterial": True,
                     "treat_diff": 4, "clothing": "torso",
                     "impair": "chest wound — breathing difficulty"},
    BP.ABDOMEN:     {"label": "Abdomen",        "hit_w": 12, "vital": True,  "arterial": False,
                     "treat_diff": 5, "clothing": "torso",
                     "impair": "gut wound — high infection risk, severe pain"},
    BP.GROIN:       {"label": "Groin",          "hit_w": 4,  "vital": False, "arterial": True,
                     "treat_diff": 4, "clothing": "legs",
                     "impair": "groin wound — extreme pain, movement impaired"},
    BP.L_UPPER_ARM: {"label": "Left Upper Arm", "hit_w": 6,  "vital": False, "arterial": True,
                     "treat_diff": 2, "clothing": "outer",
                     "impair": "left arm weakened — can't swing or lift"},
    BP.R_UPPER_ARM: {"label": "Right Upper Arm","hit_w": 6,  "vital": False, "arterial": True,
                     "treat_diff": 2, "clothing": "outer",
                     "impair": "right arm weakened — can't swing or lift"},
    BP.L_FOREARM:   {"label": "Left Forearm",   "hit_w": 5,  "vital": False, "arterial": False,
                     "treat_diff": 1, "clothing": "outer",
                     "impair": "left forearm damaged — grip weakened"},
    BP.R_FOREARM:   {"label": "Right Forearm",  "hit_w": 5,  "vital": False, "arterial": False,
                     "treat_diff": 1, "clothing": "outer",
                     "impair": "right forearm damaged — grip weakened"},
    BP.L_HAND:      {"label": "Left Hand",      "hit_w": 2,  "vital": False, "arterial": False,
                     "treat_diff": 1, "clothing": "hands",
                     "impair": "left hand mangled — can't hold items"},
    BP.R_HAND:      {"label": "Right Hand",     "hit_w": 2,  "vital": False, "arterial": False,
                     "treat_diff": 1, "clothing": "hands",
                     "impair": "right hand mangled — can't hold items"},
    BP.L_THIGH:     {"label": "Left Thigh",     "hit_w": 9,  "vital": False, "arterial": True,
                     "treat_diff": 2, "clothing": "legs",
                     "impair": "left leg crippled — movement halved"},
    BP.R_THIGH:     {"label": "Right Thigh",    "hit_w": 9,  "vital": False, "arterial": True,
                     "treat_diff": 2, "clothing": "legs",
                     "impair": "right leg crippled — movement halved"},
    BP.L_LOWER_LEG: {"label": "Left Lower Leg", "hit_w": 7,  "vital": False, "arterial": False,
                     "treat_diff": 1, "clothing": "feet",
                     "impair": "left lower leg damaged — limping"},
    BP.R_LOWER_LEG: {"label": "Right Lower Leg","hit_w": 7,  "vital": False, "arterial": False,
                     "treat_diff": 1, "clothing": "feet",
                     "impair": "right lower leg damaged — limping"},
}

# Body part HP caps — max direct HP damage a hit to this part can cause.
# Damage beyond the cap still creates the wound and bleeding but doesn't
# reduce the character's main HP pool. A .50 cal to the hand destroys the
# hand (full bleed) but only does 15 HP of direct shock damage.
PART_HP = {
    BP.HEAD:        100,  # headshots are lethal
    BP.NECK:        100,  # neck wounds are lethal
    BP.CHEST:       100,  # center mass, full damage
    BP.ABDOMEN:     80,   # gut shots are very dangerous
    BP.L_UPPER_ARM: 30,   # arm can't kill you directly
    BP.R_UPPER_ARM: 30,
    BP.L_FOREARM:   20,
    BP.R_FOREARM:   20,
    BP.L_HAND:      15,   # hand wound = shock + bleed, not lethal HP damage
    BP.R_HAND:      15,
    BP.L_THIGH:     40,   # femoral artery bleed is the killer, not direct HP
    BP.R_THIGH:     40,
    BP.L_LOWER_LEG: 25,
    BP.R_LOWER_LEG: 25,
    BP.GROIN:       50,   # femoral artery proximity, extreme pain/shock
}

# Adjacent parts for aim scatter
SCATTER_MAP: Dict[str, List[str]] = {
    BP.HEAD:        [BP.NECK],
    BP.NECK:        [BP.HEAD, BP.CHEST],
    BP.CHEST:       [BP.NECK, BP.ABDOMEN, BP.L_UPPER_ARM, BP.R_UPPER_ARM],
    BP.ABDOMEN:     [BP.CHEST, BP.GROIN, BP.L_THIGH, BP.R_THIGH],
    BP.GROIN:       [BP.ABDOMEN, BP.L_THIGH, BP.R_THIGH],
    BP.L_UPPER_ARM: [BP.CHEST, BP.L_FOREARM],
    BP.R_UPPER_ARM: [BP.CHEST, BP.R_FOREARM],
    BP.L_FOREARM:   [BP.L_UPPER_ARM, BP.L_HAND],
    BP.R_FOREARM:   [BP.R_UPPER_ARM, BP.R_HAND],
    BP.L_HAND:      [BP.L_FOREARM],
    BP.R_HAND:      [BP.R_FOREARM],
    BP.L_THIGH:     [BP.ABDOMEN, BP.L_LOWER_LEG],
    BP.R_THIGH:     [BP.ABDOMEN, BP.R_LOWER_LEG],
    BP.L_LOWER_LEG: [BP.L_THIGH],
    BP.R_LOWER_LEG: [BP.R_THIGH],
}

# Backward-compat mapping: old 8-part system → new 14-part
_OLD_TO_NEW = {
    "head":      BP.HEAD,
    "face":      BP.HEAD,
    "skull":     BP.HEAD,
    "neck":      BP.NECK,
    "throat":    BP.NECK,
    "torso":     BP.CHEST,
    "chest":     BP.CHEST,
    "ribs":      BP.CHEST,
    "back":      BP.CHEST,
    "upper back": BP.CHEST,
    "lower back": BP.ABDOMEN,
    "abdomen":   BP.ABDOMEN,
    "stomach":   BP.ABDOMEN,
    "gut":       BP.ABDOMEN,
    "groin":     BP.GROIN,
    "pelvis":    BP.GROIN,
    "crotch":    BP.GROIN,
    "genitals":  BP.GROIN,
    "rectum":    BP.ABDOMEN,
    "buttock":   BP.ABDOMEN,
    "buttocks":  BP.ABDOMEN,
    "butt":      BP.ABDOMEN,
    "left_arm":  BP.L_UPPER_ARM,
    "left arm":  BP.L_UPPER_ARM,
    "left shoulder": BP.L_UPPER_ARM,
    "left forearm":  BP.L_FOREARM,
    "left wrist":    BP.L_FOREARM,
    "left hand": BP.L_HAND,
    "left finger": BP.L_HAND,
    "right_arm": BP.R_UPPER_ARM,
    "right arm": BP.R_UPPER_ARM,
    "right shoulder": BP.R_UPPER_ARM,
    "right forearm":  BP.R_FOREARM,
    "right wrist":    BP.R_FOREARM,
    "right hand": BP.R_HAND,
    "right finger": BP.R_HAND,
    "left_leg":  BP.L_THIGH,
    "left leg":  BP.L_THIGH,
    "left thigh": BP.L_THIGH,
    "left knee":  BP.L_LOWER_LEG,
    "left shin":  BP.L_LOWER_LEG,
    "left ankle":  BP.L_LOWER_LEG,
    "left foot":  BP.L_LOWER_LEG,
    "right_leg": BP.R_THIGH,
    "right leg": BP.R_THIGH,
    "right thigh": BP.R_THIGH,
    "right knee":  BP.R_LOWER_LEG,
    "right shin":  BP.R_LOWER_LEG,
    "right ankle":  BP.R_LOWER_LEG,
    "right foot":  BP.R_LOWER_LEG,
}


# ============================================================================
#  DAMAGE & WOUND TYPES
# ============================================================================

class DmgType:
    BLUNT   = "blunt"
    SLASH   = "slash"
    PIERCE  = "pierce"
    GUNSHOT = "gunshot"
    BLAST   = "blast"
    BITE    = "bite"
    BURN    = "burn"


class WndType:
    BRUISE      = "bruise"
    SPRAIN      = "sprain"
    CUT         = "cut"
    LACERATION  = "laceration"
    STAB        = "stab"
    GUNSHOT     = "gunshot_wound"
    CRUSH       = "crush"
    FRACTURE    = "fracture"
    BITE_WOUND  = "bite_wound"
    BURN_WOUND  = "burn_wound"
    AVULSION    = "avulsion"     # tissue torn away


class Sev:
    LIGHT    = "light"
    MODERATE = "moderate"
    SEVERE   = "severe"
    CRITICAL = "critical"


SEV_ORDER = [Sev.LIGHT, Sev.MODERATE, Sev.SEVERE, Sev.CRITICAL]

class BleedLevel:
    NONE     = "none"
    MINOR    = "minor"        # < 0.15 units/min
    STEADY   = "steady"       # 0.15 - 0.60
    HEAVY    = "heavy"        # 0.60 - 2.00
    ARTERIAL = "arterial"     # > 2.00 — will kill in minutes


def bleed_label(rate: float) -> str:
    if rate <= 0:        return BleedLevel.NONE
    if rate < 0.15:      return BleedLevel.MINOR
    if rate < 0.60:      return BleedLevel.STEADY
    if rate < 2.00:      return BleedLevel.HEAVY
    return BleedLevel.ARTERIAL


# ============================================================================
#  WOUND DATACLASS
# ============================================================================

@dataclass
class DetailedWound:
    """A single wound with full simulation data."""
    id: int
    part: str                       # BP constant
    wound_type: str                 # WndType
    damage_type: str                # DmgType
    severity: str                   # Sev

    # ── Bleeding ──
    bleed_rate: float = 0.0         # blood units/min
    bandaged: bool = False
    tourniquet: bool = False
    cauterized: bool = False
    stitched: bool = False

    # ── Pain ──
    pain: float = 0.0               # 0-100

    # ── Infection ──
    dirty: bool = False             # wound contaminated
    infected: bool = False
    infection_stage: str = "none"   # none | early | spreading | sepsis

    # ── Foreign object ──
    lodged: str = ""                # "bullet", "arrowhead", "splinter", ""

    # ── Bone ──
    bone_broken: bool = False
    compound_fracture: bool = False
    bone_set: bool = False
    splinted: bool = False

    # ── Sprain ──
    sprain: bool = False

    # ── Nerve ──
    nerve_damage: bool = False

    # ── Healing/Treatment ──
    age_days: int = 0
    treated: bool = False
    treatment_quality: float = 0.0  # 0-1
    permanent: bool = False         # permanent injury / scarring

    # ── Description ──
    description: str = ""

    # ── Backward compat ──
    @property
    def active_bleed(self) -> float:
        if self.cauterized or self.stitched:
            return 0.0
        if self.tourniquet:
            return 0.0
        if self.bandaged:
            return self.bleed_rate * 0.12
        return self.bleed_rate

    @property
    def is_bleeding(self) -> bool:
        return self.active_bleed > 0.0

    @property
    def bleed_level(self) -> str:
        return bleed_label(self.active_bleed)

    @property
    def severity_color(self) -> tuple:
        return {
            Sev.LIGHT:    (180, 180, 180),
            Sev.MODERATE: (220, 180,  60),
            Sev.SEVERE:   (220,  80,  40),
            Sev.CRITICAL: (255,  30,  30),
        }.get(self.severity, (255, 255, 255))


# ============================================================================
#  WOUND GENERATION TABLES
# ============================================================================

# Base bleed rates by wound_type × severity
_BLEED: Dict[Tuple[str, str], float] = {
    (WndType.BRUISE,    Sev.LIGHT): 0.0,   (WndType.BRUISE,    Sev.MODERATE): 0.0,
    (WndType.BRUISE,    Sev.SEVERE): 0.0,  (WndType.BRUISE,    Sev.CRITICAL): 0.0,
    (WndType.SPRAIN,    Sev.LIGHT): 0.0,   (WndType.SPRAIN,    Sev.MODERATE): 0.0,
    (WndType.CUT,       Sev.LIGHT): 0.08,  (WndType.CUT,       Sev.MODERATE): 0.22,
    (WndType.CUT,       Sev.SEVERE): 0.55, (WndType.CUT,       Sev.CRITICAL): 1.20,
    (WndType.LACERATION,Sev.LIGHT): 0.18,  (WndType.LACERATION,Sev.MODERATE): 0.55,
    (WndType.LACERATION,Sev.SEVERE): 1.80, (WndType.LACERATION,Sev.CRITICAL): 4.00,
    (WndType.STAB,      Sev.LIGHT): 0.12,  (WndType.STAB,      Sev.MODERATE): 0.45,
    (WndType.STAB,      Sev.SEVERE): 1.40, (WndType.STAB,      Sev.CRITICAL): 3.20,
    (WndType.GUNSHOT,   Sev.LIGHT): 0.20,  (WndType.GUNSHOT,   Sev.MODERATE): 0.70,
    (WndType.GUNSHOT,   Sev.SEVERE): 2.50, (WndType.GUNSHOT,   Sev.CRITICAL): 5.00,
    (WndType.CRUSH,     Sev.LIGHT): 0.04,  (WndType.CRUSH,     Sev.MODERATE): 0.20,
    (WndType.CRUSH,     Sev.SEVERE): 0.70, (WndType.CRUSH,     Sev.CRITICAL): 2.00,
    (WndType.FRACTURE,  Sev.LIGHT): 0.0,   (WndType.FRACTURE,  Sev.MODERATE): 0.10,
    (WndType.FRACTURE,  Sev.SEVERE): 0.35, (WndType.FRACTURE,  Sev.CRITICAL): 1.50,
    (WndType.BITE_WOUND,Sev.LIGHT): 0.10,  (WndType.BITE_WOUND,Sev.MODERATE): 0.40,
    (WndType.BITE_WOUND,Sev.SEVERE): 1.20, (WndType.BITE_WOUND,Sev.CRITICAL): 3.00,
    (WndType.BURN_WOUND,Sev.LIGHT): 0.0,   (WndType.BURN_WOUND,Sev.MODERATE): 0.05,
    (WndType.BURN_WOUND,Sev.SEVERE): 0.15, (WndType.BURN_WOUND,Sev.CRITICAL): 0.40,
    (WndType.AVULSION,  Sev.MODERATE): 0.80,(WndType.AVULSION,  Sev.SEVERE): 2.50,
    (WndType.AVULSION,  Sev.CRITICAL): 5.50,
}

# Base pain by severity
_PAIN = {Sev.LIGHT: 8, Sev.MODERATE: 22, Sev.SEVERE: 50, Sev.CRITICAL: 80}

# Weapon → wound type mapping
WEAPON_WOUND_MAP: Dict[str, dict] = {
    "fists":       {"dtype": DmgType.BLUNT,   "wtype": WndType.BRUISE},
    "knife":       {"dtype": DmgType.SLASH,   "wtype": WndType.CUT},
    "bowie_knife": {"dtype": DmgType.SLASH,   "wtype": WndType.LACERATION, "deep": True},
    "hatchet":     {"dtype": DmgType.SLASH,   "wtype": WndType.LACERATION, "bone": 0.35},
    "pickaxe":     {"dtype": DmgType.PIERCE,  "wtype": WndType.STAB,       "bone": 0.30},
    "hammer":      {"dtype": DmgType.BLUNT,   "wtype": WndType.CRUSH,      "bone": 0.40},
    "rifle":       {"dtype": DmgType.GUNSHOT, "wtype": WndType.GUNSHOT,    "lodged": "bullet"},
    "revolver":    {"dtype": DmgType.GUNSHOT, "wtype": WndType.GUNSHOT,    "lodged": "bullet"},
    "shotgun":     {"dtype": DmgType.GUNSHOT, "wtype": WndType.GUNSHOT,    "lodged": "shot"},
    "arrow":       {"dtype": DmgType.PIERCE,  "wtype": WndType.STAB,       "lodged": "arrowhead"},
    "bear_claw":   {"dtype": DmgType.SLASH,   "wtype": WndType.LACERATION, "dirty": True},
    "bear_bite":   {"dtype": DmgType.BITE,    "wtype": WndType.BITE_WOUND, "dirty": True, "bone": 0.25},
    "snake_bite":  {"dtype": DmgType.BITE,    "wtype": WndType.BITE_WOUND, "dirty": True},
    "explosion":   {"dtype": DmgType.BLAST,   "wtype": WndType.AVULSION,   "dirty": True, "bone": 0.50},
    "fire":        {"dtype": DmgType.BURN,    "wtype": WndType.BURN_WOUND},
    "rock_fall":   {"dtype": DmgType.BLUNT,   "wtype": WndType.CRUSH,      "bone": 0.45},
}


# ============================================================================
#  WOUND GENERATION
# ============================================================================

_wound_counter = 0

def _next_wound_id() -> int:
    global _wound_counter
    _wound_counter += 1
    return _wound_counter


def classify_severity(damage: float) -> str:
    if damage <  5:  return Sev.LIGHT
    if damage < 14:  return Sev.MODERATE
    if damage < 28:  return Sev.SEVERE
    return Sev.CRITICAL


def create_wound(damage: float, damage_type: str = DmgType.BLUNT,
                  target_part: Optional[str] = None,
                  weapon_key: str = "",
                  rng: Optional[random.Random] = None,
                  body_parts: Optional[List[str]] = None,
                  part_data: Optional[Dict[str, dict]] = None) -> DetailedWound:
    """
    Generate a fully-detailed wound from hit parameters.
    body_parts/part_data override defaults for non-human creatures.
    """
    if rng is None:
        rng = random.Random()

    bp_list = body_parts or ALL_BODY_PARTS
    bp_data = part_data or PART_DATA

    # Resolve body part
    if target_part:
        part = _OLD_TO_NEW.get(target_part, target_part)
        # If mapped part isn't in this body plan, pick random
        if part not in bp_data:
            part = rng.choice(bp_list)
    else:
        parts = list(bp_list)
        weights = [bp_data.get(p, {}).get("hit_w", 10) for p in parts]
        part = rng.choices(parts, weights=weights, k=1)[0]

    part_info = bp_data.get(part, PART_DATA.get(part, PART_DATA.get(BP.CHEST, {})))

    # Resolve weapon profile
    wpn = WEAPON_WOUND_MAP.get(weapon_key, {})
    dtype = wpn.get("dtype", damage_type)
    base_wtype = wpn.get("wtype", _infer_wound_type(damage_type))

    # Severity
    sev = classify_severity(damage)
    # Vital parts escalate severity by one step
    if part_info["vital"] and sev != Sev.CRITICAL:
        idx = SEV_ORDER.index(sev)
        if rng.random() < 0.6:  # 60% chance of escalation on vitals
            sev = SEV_ORDER[min(idx + 1, 3)]

    # Determine final wound type
    wtype = base_wtype
    if sev == Sev.CRITICAL and dtype == DmgType.BLUNT:
        wtype = WndType.CRUSH
    if sev == Sev.CRITICAL and dtype == DmgType.SLASH:
        wtype = WndType.AVULSION if rng.random() < 0.3 else WndType.LACERATION

    # Bleed rate
    bleed = _BLEED.get((wtype, sev), 0.0)
    # Arterial hit on arterial body parts boosts bleed
    if part_info["arterial"] and sev in (Sev.SEVERE, Sev.CRITICAL):
        if rng.random() < 0.35:  # 35% chance of arterial hit
            bleed *= 2.5

    # Pain
    pain = _PAIN.get(sev, 20)
    if part in (BP.ABDOMEN, BP.L_HAND, BP.R_HAND):
        pain *= 1.3   # gut wounds and hand wounds hurt more

    # Dirty — only wounds that break the skin can get contaminated
    # Bruises and crushes don't expose tissue to bacteria
    dirty = wpn.get("dirty", False)
    skin_broken = wtype not in (WndType.BRUISE, WndType.CRUSH)
    if not dirty and skin_broken and rng.random() < 0.15:
        dirty = True   # 15% chance open wounds get contaminated

    # Lodged object — bullets have ~60% chance, arrows ~80%, shot ~40%
    lodged = ""
    if wpn.get("lodged") and sev != Sev.LIGHT:
        lodge_chance = {"bullet": 0.60, "arrowhead": 0.80, "shot": 0.40
                        }.get(wpn["lodged"], 0.50)
        if rng.random() < lodge_chance:
            lodged = wpn["lodged"]

    # Bone fracture
    bone_broken = False
    compound = False
    if wpn.get("bone") and rng.random() < wpn["bone"]:
        bone_broken = True
        if sev == Sev.CRITICAL:
            compound = True
            pain *= 1.5
    elif sev == Sev.CRITICAL and dtype in (DmgType.BLUNT, DmgType.GUNSHOT, DmgType.BLAST):
        bone_broken = True
        compound = dtype == DmgType.GUNSHOT

    # Sprain (joint-related parts only, lower severity impacts)
    sprain = False
    if part in (BP.L_HAND, BP.R_HAND, BP.L_LOWER_LEG, BP.R_LOWER_LEG,
                BP.L_FOREARM, BP.R_FOREARM):
        if dtype == DmgType.BLUNT and sev in (Sev.LIGHT, Sev.MODERATE):
            sprain = rng.random() < 0.40

    # Nerve damage (severe/critical to extremities)
    nerve = False
    if sev == Sev.CRITICAL and part not in (BP.CHEST, BP.ABDOMEN):
        nerve = rng.random() < 0.20

    # Description
    part_label = part_info["label"]
    desc = _build_description(wtype, sev, part_label, bone_broken, compound,
                               lodged, sprain, nerve, dtype=dtype)

    return DetailedWound(
        id=_next_wound_id(), part=part, wound_type=wtype,
        damage_type=dtype, severity=sev,
        bleed_rate=bleed, pain=pain,
        dirty=dirty, lodged=lodged,
        bone_broken=bone_broken, compound_fracture=compound,
        sprain=sprain, nerve_damage=nerve,
        description=desc,
    )


def _infer_wound_type(dtype: str) -> str:
    return {
        DmgType.BLUNT:   WndType.BRUISE,
        DmgType.SLASH:   WndType.CUT,
        DmgType.PIERCE:  WndType.STAB,
        DmgType.GUNSHOT: WndType.GUNSHOT,
        DmgType.BLAST:   WndType.AVULSION,
        DmgType.BITE:    WndType.BITE_WOUND,
        DmgType.BURN:    WndType.BURN_WOUND,
    }.get(dtype, WndType.BRUISE)


def _build_description(wtype, sev, part_label, bone, compound,
                        lodged, sprain, nerve, dtype="") -> str:
    """Build LCS-style vivid wound description based on damage type × body part."""
    rng = random.Random()
    pl = part_label.lower()

    # ── LCS-style per-type per-severity descriptions ──
    # These replace the generic "moderate cut to the head" with vivid text
    _GUNSHOT_DESC = {
        Sev.LIGHT:    [f"A bullet grazes the {pl}, tearing skin.",
                       f"A round clips the {pl} — a shallow furrow."],
        Sev.MODERATE: [f"A bullet punches through the {pl}, spraying blood.",
                       f"The {pl} is shot — clean entry, blood flowing."],
        Sev.SEVERE:   [f"The {pl} is shattered by a bullet — bone fragments visible.",
                       f"A round tears through the {pl}, splattering the ground."],
        Sev.CRITICAL: [f"The {pl} is blown apart — a catastrophic gunshot wound.",
                       f"A bullet destroys the {pl}. Blood everywhere."],
    }
    _SLASH_DESC = {
        Sev.LIGHT:    [f"A shallow cut across the {pl}.",
                       f"The blade nicks the {pl} — bleeding lightly."],
        Sev.MODERATE: [f"A deep gash opens across the {pl}.",
                       f"The {pl} is sliced open — muscle visible."],
        Sev.SEVERE:   [f"The {pl} is laid open to the bone.",
                       f"A vicious cut nearly severs the {pl}."],
        Sev.CRITICAL: [f"The {pl} is hacked apart — hanging by strips of flesh.",
                       f"The blade bites deep into the {pl} — catastrophic damage."],
    }
    _BLUNT_DESC = {
        Sev.LIGHT:    [f"A glancing blow bruises the {pl}.",
                       f"The {pl} takes a solid hit — swelling immediately."],
        Sev.MODERATE: [f"A heavy blow crunches into the {pl}.",
                       f"The {pl} is smashed hard — deep purple bruising."],
        Sev.SEVERE:   [f"The {pl} crumples under a devastating impact.",
                       f"Bones crack in the {pl} — the sound is sickening."],
        Sev.CRITICAL: [f"The {pl} is crushed flat. Bone and tissue pulped.",
                       f"A massive impact caves in the {pl}."],
    }
    _BITE_DESC = {
        Sev.LIGHT:    [f"Teeth rake across the {pl}, drawing blood.",
                       f"A bite tears the skin of the {pl}."],
        Sev.MODERATE: [f"Jaws clamp down on the {pl} and rip.",
                       f"The {pl} is savaged — deep punctures and torn flesh."],
        Sev.SEVERE:   [f"The {pl} is mauled — flesh hanging in strips.",
                       f"Teeth sink deep into the {pl} and wrench sideways."],
        Sev.CRITICAL: [f"The {pl} is torn apart by powerful jaws.",
                       f"Jaws crush the {pl} — mangled beyond recognition."],
    }
    _BURN_DESC = {
        Sev.LIGHT:    [f"The {pl} is singed — red and blistering.",
                       f"A burn reddens the {pl}."],
        Sev.MODERATE: [f"The skin of the {pl} bubbles and blackens.",
                       f"A serious burn covers the {pl} — second degree."],
        Sev.SEVERE:   [f"The {pl} is charred — flesh cracking open.",
                       f"Third-degree burns cover the {pl}. Skin gone."],
        Sev.CRITICAL: [f"The {pl} is burned to the bone.",
                       f"The {pl} is a mass of charred ruin."],
    }
    _STAB_DESC = {
        Sev.LIGHT:    [f"A shallow puncture in the {pl}.",
                       f"The point pricks the {pl} — a minor wound."],
        Sev.MODERATE: [f"A deep puncture wound in the {pl}.",
                       f"The blade sinks into the {pl} — dark blood wells up."],
        Sev.SEVERE:   [f"The {pl} is impaled — the blade goes deep.",
                       f"A savage thrust pierces the {pl} through."],
        Sev.CRITICAL: [f"The {pl} is run through — the point exits the far side.",
                       f"A devastating thrust destroys the {pl} from within."],
    }

    # Pick description by damage type
    type_descs = {
        DmgType.GUNSHOT: _GUNSHOT_DESC,
        DmgType.BLAST:   _GUNSHOT_DESC,
        DmgType.SLASH:   _SLASH_DESC,
        DmgType.BLUNT:   _BLUNT_DESC,
        DmgType.BITE:    _BITE_DESC,
        DmgType.BURN:    _BURN_DESC,
        DmgType.PIERCE:  _STAB_DESC,
    }
    desc_table = type_descs.get(dtype, _BLUNT_DESC)
    options = desc_table.get(sev, desc_table.get(Sev.MODERATE, [f"Wound to the {pl}."]))
    base_desc = rng.choice(options)

    # Append complications
    extras = []
    if compound:
        extras.append("Bone exposed through the wound")
    elif bone:
        extras.append("Bone broken")
    if lodged:
        extras.append(f"{lodged.capitalize()} lodged in the wound")
    if sprain:
        extras.append("Joint sprained")
    if nerve:
        extras.append("Nerve damage — numbness spreading")

    if extras:
        return base_desc + " " + ". ".join(extras) + "."
    return base_desc


# ============================================================================
#  AIMING SYSTEM
# ============================================================================

def resolve_aimed_shot(target_part: str, skill: int, distance: int,
                        weapon_accuracy: float = 0.0,
                        rng: Optional[random.Random] = None) -> Tuple[bool, str]:
    """
    Resolve a targeted shot at a specific body part.

    Returns (hit: bool, actual_part_hit: str).
    On miss, actual_part is "" (complete miss).
    On hit with scatter, actual_part may differ from target.

    skill:     firearms or relevant combat skill (0-10)
    distance:  tiles to target
    weapon_accuracy: bonus from weapon (+0.0 to +0.15)
    """
    if rng is None:
        rng = random.Random()

    part = _OLD_TO_NEW.get(target_part, target_part)
    part_info = PART_DATA.get(part, PART_DATA[BP.CHEST])
    part_size = part_info["hit_w"]

    # Base hit chance
    base = 0.45 + skill * 0.04 + weapon_accuracy
    # Distance penalty: -5% per tile beyond 3
    base -= max(0, distance - 3) * 0.05
    # Small targets are harder
    if part_size <= 3:
        base -= 0.15
    elif part_size <= 5:
        base -= 0.08

    hit_chance = max(0.05, min(0.92, base))

    # Natural 20 / natural 1
    nat_roll = rng.randint(1, 20)
    if nat_roll == 20:
        return True, part       # perfect hit
    if nat_roll == 1:
        return False, ""        # total whiff

    if rng.random() > hit_chance:
        return False, ""        # miss

    # Hit — check for scatter
    scatter_chance = 0.30 - skill * 0.02  # better skill = less scatter
    if rng.random() < max(0.05, scatter_chance):
        neighbors = SCATTER_MAP.get(part, [])
        if neighbors:
            part = rng.choice(neighbors)

    return True, part


# ============================================================================
#  HEALTH TRACKER
# ============================================================================

# Blood volumes
MAX_BLOOD = {
    "human": 100.0, "very_large": 220.0, "large": 140.0,
    "medium": 80.0, "small": 30.0, "tiny": 10.0,
}


# ============================================================================
#  BODY PLANS — species-specific anatomy
# ============================================================================

def _bp(label, hit_w, vital=False, arterial=False, treat_diff=2):
    return {"label": label, "hit_w": hit_w, "vital": vital, "arterial": arterial,
            "treat_diff": treat_diff, "clothing": None,
            "impair": f"{label.lower()} damaged"}

BODY_PLANS: Dict[str, dict] = {
    "human": {
        "parts": ALL_BODY_PARTS,
        "part_data": PART_DATA,
    },
    "quadruped": {
        "parts": ["head", "neck", "chest", "abdomen",
                   "l_foreleg", "r_foreleg", "l_hindleg", "r_hindleg", "tail"],
        "part_data": {
            "head":      _bp("Head",          6,  vital=True,  arterial=True, treat_diff=3),
            "neck":      _bp("Neck",          5,  vital=True,  arterial=True, treat_diff=4),
            "chest":     _bp("Chest",         25, vital=True,  arterial=True, treat_diff=4),
            "abdomen":   _bp("Abdomen",       18, vital=True,  arterial=False, treat_diff=5),
            "l_foreleg": _bp("Left Foreleg",  10),
            "r_foreleg": _bp("Right Foreleg", 10),
            "l_hindleg": _bp("Left Hindleg",  10, arterial=True),
            "r_hindleg": _bp("Right Hindleg", 10, arterial=True),
            "tail":      _bp("Tail",          6,  treat_diff=1),
        },
    },
    "small_quadruped": {
        "parts": ["head", "body", "l_foreleg", "r_foreleg",
                   "l_hindleg", "r_hindleg", "tail"],
        "part_data": {
            "head":      _bp("Head",          10, vital=True,  arterial=True, treat_diff=3),
            "body":      _bp("Body",          35, vital=True,  arterial=True, treat_diff=4),
            "l_foreleg": _bp("Left Foreleg",  12, treat_diff=1),
            "r_foreleg": _bp("Right Foreleg", 12, treat_diff=1),
            "l_hindleg": _bp("Left Hindleg",  12, treat_diff=1),
            "r_hindleg": _bp("Right Hindleg", 12, treat_diff=1),
            "tail":      _bp("Tail",          7,  treat_diff=1),
        },
    },
    "bird": {
        "parts": ["head", "neck", "body", "l_wing", "r_wing",
                   "l_leg", "r_leg", "tail"],
        "part_data": {
            "head":   _bp("Head",       6,  vital=True,  arterial=True, treat_diff=3),
            "neck":   _bp("Neck",       5,  vital=True,  arterial=True, treat_diff=4),
            "body":   _bp("Body",       35, vital=True,  arterial=True, treat_diff=4),
            "l_wing": _bp("Left Wing",  14),
            "r_wing": _bp("Right Wing", 14),
            "l_leg":  _bp("Left Leg",   8,  treat_diff=1),
            "r_leg":  _bp("Right Leg",  8,  treat_diff=1),
            "tail":   _bp("Tail Feathers", 10, treat_diff=1),
        },
    },
    "snake": {
        "parts": ["head", "body_front", "body_mid", "body_rear", "tail"],
        "part_data": {
            "head":       _bp("Head",         10, vital=True, arterial=True, treat_diff=3),
            "body_front": _bp("Body (front)", 25, vital=True, arterial=True, treat_diff=3),
            "body_mid":   _bp("Body (mid)",   30, vital=True, treat_diff=2),
            "body_rear":  _bp("Body (rear)",  20, treat_diff=1),
            "tail":       _bp("Tail",         15, treat_diff=1),
        },
    },
}


class HealthTracker:
    """
    Full health simulation for one creature.
    Drop-in replacement for CreatureWounds with expanded features.
    """

    def __init__(self, max_blood: float = 100.0, body_plan: str = "human"):
        self.max_blood: float = max_blood
        self.blood: float = max_blood
        self.wounds: List[DetailedWound] = []

        # Foreign objects lodged in body
        self.foreign_objects: List[Dict[str, Any]] = []

        # Body plan — determines which body parts this creature has
        self.body_plan_name: str = body_plan
        plan = BODY_PLANS.get(body_plan, BODY_PLANS["human"])
        self._body_parts: List[str] = plan["parts"]
        self._part_data: Dict[str, dict] = plan["part_data"]

        # Part functional state
        self.part_state: Dict[str, str] = {p: "intact" for p in self._body_parts}

        # Aggregate state
        self.shock: float = 0.0
        self.conscious: bool = True
        self.total_pain: float = 0.0

    # ── Core properties (backward compat) ──────────────────────────────

    @property
    def blood_pct(self) -> float:
        return self.blood / self.max_blood if self.max_blood > 0 else 0.0

    @property
    def alive(self) -> bool:
        return self.blood > 0.0

    @property
    def total_bleed_rate(self) -> float:
        return sum(w.active_bleed for w in self.wounds)

    @property
    def is_bleeding(self) -> bool:
        return self.total_bleed_rate > 0.0

    @property
    def impairments(self) -> List[str]:
        return [self._part_data.get(p, {}).get("impair", f"{p} damaged")
                for p in self._body_parts
                if self.part_state.get(p) in ("impaired", "disabled")]

    # ── Apply hit (backward compat + expanded) ─────────────────────────

    def apply_hit(self, damage: float, damage_type: str = DmgType.BLUNT,
                  target_part: Optional[str] = None,
                  weapon_key: str = "",
                  worn_equipment=None) -> DetailedWound:
        """
        Generate a wound, optionally reduce damage via clothing,
        apply it, update state. Returns the wound.
        """
        # Clothing protection
        part_for_clothing = target_part or BP.CHEST
        part_for_clothing = _OLD_TO_NEW.get(part_for_clothing, part_for_clothing)
        clothing_msg = None

        if worn_equipment is not None:
            try:
                from src.clothing import damage_after_clothing
                clothing_slot = PART_DATA.get(part_for_clothing, {}).get("clothing", "torso")
                damage, clothing_msg = damage_after_clothing(
                    damage, clothing_slot, worn_equipment)
            except ImportError:
                pass

        wound = create_wound(damage, damage_type, target_part, weapon_key,
                              body_parts=self._body_parts,
                              part_data=self._part_data)
        self.wounds.append(wound)
        self._update_part_state(wound)
        self._recalc_pain()
        return wound

    def _update_part_state(self, wound: DetailedWound) -> None:
        part = wound.part
        current = self.part_state.get(part, "intact")
        if current == "disabled":
            return
        if wound.severity == Sev.CRITICAL or wound.compound_fracture:
            self.part_state[part] = "disabled"
        elif wound.severity == Sev.SEVERE or wound.bone_broken:
            self.part_state[part] = "impaired" if current == "intact" else "disabled"
        elif wound.severity == Sev.MODERATE and current == "intact":
            self.part_state[part] = "impaired"

    def _recalc_pain(self) -> None:
        self.total_pain = sum(w.pain for w in self.wounds)

    # ── Time tick ──────────────────────────────────────────────────────

    def tick(self, minutes: float) -> List[Tuple[str, str]]:
        """
        Advance bleed, shock, infection. Returns list of (message, severity).
        Call from engine.advance_time().
        """
        msgs: List[Tuple[str, str]] = []
        old_pct = self.blood_pct

        # Bleeding
        for w in self.wounds:
            if w.active_bleed > 0:
                self.blood = max(0.0, self.blood - w.active_bleed * minutes)

        # Tourniquet tissue damage (causes pain over time)
        for w in self.wounds:
            if w.tourniquet:
                w.pain = min(100, w.pain + 0.02 * minutes)

        new_pct = self.blood_pct

        # Blood loss thresholds
        for thr, msg, sev in [
            (0.70, "You feel light-headed from blood loss.", "advisory"),
            (0.50, "Your vision swims. Losing too much blood.", "advisory"),
            (0.30, "Dangerously low on blood. May pass out.", "critical"),
            (0.10, "You are dying. Need aid immediately.", "critical"),
        ]:
            if old_pct > thr >= new_pct:
                msgs.append((msg, sev))

        # Shock from pain + blood loss
        blood_shock = max(0, (1.0 - self.blood_pct) * 60)
        pain_shock = self.total_pain * 0.4
        self.shock = min(100, blood_shock + pain_shock)

        if self.shock > 80 and self.conscious:
            self.conscious = False
            msgs.append(("You pass out from shock.", "critical"))
        elif self.shock < 50 and not self.conscious and self.alive:
            self.conscious = True
            msgs.append(("You regain consciousness.", "advisory"))

        self._recalc_pain()
        return msgs

    def tick_daily(self, constitution: int = 10) -> List[Tuple[str, str]]:
        """
        Daily tick: infection progression, healing, wound aging.
        Constitution reduces infection risk and speeds healing.
        Call once per game day.
        """
        msgs: List[Tuple[str, str]] = []
        rng = random.Random()

        for w in self.wounds:
            w.age_days += 1

            # ── Infection check ──
            if not w.infected and w.dirty and not w.treated:
                risk = 0.08 + (0.04 if w.lodged else 0)
                if w.part == BP.ABDOMEN:
                    risk += 0.10
                # Constitution reduces infection risk (CON 16 = -40%, CON 6 = +20%)
                con_mod = (constitution - 10) * 0.02
                risk = max(0.02, risk - con_mod)
                if rng.random() < risk:
                    w.infected = True
                    w.infection_stage = "early"
                    msgs.append((f"Your {PART_DATA.get(w.part, {}).get('label', w.part)} "
                                 f"wound looks inflamed.", "advisory"))

            # ── Infection progression ──
            if w.infected:
                if w.infection_stage == "early" and w.age_days > 2:
                    if rng.random() < 0.20:
                        w.infection_stage = "spreading"
                        w.pain += 10
                        msgs.append((f"The infection in your {PART_DATA.get(w.part, {}).get('label', w.part).lower()} "
                                     f"is getting worse.", "advisory"))
                elif w.infection_stage == "spreading" and w.age_days > 5:
                    if rng.random() < 0.15:
                        w.infection_stage = "sepsis"
                        w.pain += 20
                        msgs.append(("You have blood poisoning. Without treatment "
                                     "you will die.", "critical"))

            # ── Natural healing (CON speeds recovery) ──
            heal_days_light = max(1, 3 - (constitution - 10) // 3)
            heal_days_treated = max(3, 7 - (constitution - 10) // 2)
            pain_recovery = 2 + max(0, (constitution - 10) // 3)
            if not w.infected and w.severity == Sev.LIGHT and w.age_days >= heal_days_light:
                w.bleed_rate = 0.0
                w.pain = max(0, w.pain - pain_recovery)
            if not w.infected and w.treated and w.age_days >= heal_days_treated:
                w.pain = max(0, w.pain - 1)
                if w.bleed_rate > 0:
                    w.bleed_rate = max(0, w.bleed_rate - 0.01)

        # Remove fully healed light wounds
        self.wounds = [w for w in self.wounds
                       if not (w.severity == Sev.LIGHT and w.age_days >= 5
                               and w.pain <= 0 and not w.infected)]
        self._recalc_pain()
        return msgs

    # ── Treatment ──────────────────────────────────────────────────────

    def treat_wound(self, wound_id: int, treatment: str,
                     skill: int = 0, intelligence: int = 10,
                     self_treatment: bool = True,
                     has_tools: bool = False) -> Tuple[bool, str]:
        """
        Apply a treatment to a specific wound.
        Returns (success: bool, message: str).

        treatment types:
            "bandage"    — slow bleeding
            "tourniquet" — stop limb bleeding (risky)
            "clean"      — reduce infection risk
            "extract"    — remove lodged object
            "stitch"     — close laceration permanently
            "set_bone"   — align broken bone
            "splint"     — immobilize fracture
            "cauterize"  — burn wound closed
            "poultice"   — herbal infection treatment
            "amputate"   — last resort for gangrene
        """
        wound = self._find_wound(wound_id)
        if not wound:
            return False, "No such wound."

        part_info = self._part_data.get(wound.part, PART_DATA.get(wound.part, {}))
        diff = part_info.get("treat_diff", 3)

        # Self-treatment penalty
        if self_treatment:
            diff += 1
            if wound.part in (BP.ABDOMEN, BP.CHEST, BP.NECK):
                diff += 2   # very hard to treat yourself in these areas

        # Skill check: d20 + skill + INT_bonus vs difficulty × 4
        roll = random.randint(1, 20) + skill + (intelligence - 10) // 3
        if has_tools:
            roll += 2
        threshold = diff * 4

        success = roll >= threshold
        quality = min(1.0, max(0.1, (roll - threshold + 10) / 20.0))

        return self._apply_treatment(wound, treatment, success, quality)

    def _apply_treatment(self, w: DetailedWound, treatment: str,
                          success: bool, quality: float
                          ) -> Tuple[bool, str]:
        part_label = self._part_data.get(w.part, PART_DATA.get(w.part, {})).get("label", w.part).lower()

        if treatment == "bandage":
            w.bandaged = True
            w.treated = True
            w.treatment_quality = max(w.treatment_quality, quality)
            return True, f"You bandage the {part_label} wound. Bleeding slows."

        if treatment == "tourniquet":
            if w.part in (BP.HEAD, BP.NECK, BP.CHEST, BP.ABDOMEN):
                return False, "Can't tourniquet that body part."
            w.tourniquet = True
            w.treated = True
            return True, (f"You tie a tourniquet above the {part_label} wound. "
                         f"Bleeding stops but the limb throbs painfully.")

        if treatment == "clean":
            if success:
                w.dirty = False
                if w.infection_stage == "early":
                    w.infected = False
                    w.infection_stage = "none"
                w.treated = True
                w.treatment_quality = max(w.treatment_quality, quality)
                return True, f"You clean the {part_label} wound thoroughly."
            w.treated = True
            return False, f"You try to clean the wound but can't get it all."

        if treatment == "extract":
            if not w.lodged:
                return False, "Nothing lodged in this wound."
            if success:
                obj = w.lodged
                w.lodged = ""
                w.bleed_rate *= 1.3   # extraction opens the wound more
                w.treated = True
                return True, f"You extract the {obj} from the {part_label}. Fresh blood flows."
            w.pain += 15
            w.bleed_rate *= 1.5
            return False, (f"You dig for the {w.lodged} but can't get it. "
                          f"The wound bleeds worse now.")

        if treatment == "stitch":
            if w.wound_type not in (WndType.CUT, WndType.LACERATION,
                                     WndType.STAB, WndType.GUNSHOT):
                return False, "This wound type can't be stitched."
            if success:
                w.stitched = True
                w.bleed_rate = 0
                w.treated = True
                w.treatment_quality = max(w.treatment_quality, quality)
                return True, f"You stitch the {part_label} wound closed."
            w.pain += 10
            return False, f"The stitches don't hold. You'll need to try again."

        if treatment == "set_bone":
            if not w.bone_broken:
                return False, "No broken bone to set."
            if success:
                w.bone_set = True
                w.pain += 20   # setting a bone is extremely painful
                w.treated = True
                return True, (f"With a sickening grind, you align the broken "
                             f"bone in the {part_label}. Agony.")
            w.pain += 25
            return False, (f"You try to set the bone but it won't align. "
                          f"The pain is blinding.")

        if treatment == "splint":
            if not w.bone_broken and not w.sprain:
                return False, "Nothing to splint."
            w.splinted = True
            w.treated = True
            return True, f"You splint the {part_label} to immobilize it."

        if treatment == "cauterize":
            if success:
                w.cauterized = True
                w.bleed_rate = 0
                w.dirty = False
                w.pain += 35
                w.permanent = True
                w.treated = True
                return True, (f"You press the hot iron to the {part_label} wound. "
                             f"The smell of burning flesh. The bleeding stops.")
            w.pain += 25
            return False, "The cauterization didn't fully seal the wound."

        if treatment == "poultice":
            if success:
                if w.infection_stage in ("early", "spreading"):
                    w.infection_stage = "early" if w.infection_stage == "spreading" else "none"
                    w.infected = w.infection_stage != "none"
                w.dirty = False
                w.treated = True
                return True, f"You apply the poultice to the {part_label}. It draws heat."
            return False, "The poultice doesn't seem to help."

        return False, "Unknown treatment."

    def _find_wound(self, wound_id: int) -> Optional[DetailedWound]:
        for w in self.wounds:
            if w.id == wound_id:
                return w
        return None

    # ── Foreign objects (non-wound lodged items) ─────────────────────

    def insert_object(self, item_name: str, part: str,
                       causes_damage: bool = False,
                       damage: float = 0.0) -> Tuple[str, Optional["DetailedWound"]]:
        """
        Insert a foreign object into a body part.
        Only creates a wound if the item is sharp/large enough to cause damage.
        Returns (message, wound_or_None).
        """
        part = _OLD_TO_NEW.get(part.lower().replace(" ", "_"), part)
        part_label = PART_DATA.get(part, {}).get("label", part)

        self.foreign_objects.append({
            "item": item_name, "part": part, "removable": True,
        })

        wound = None
        if causes_damage and damage > 0:
            wound = self.apply_hit(damage, DmgType.PIERCE, part)
            wound.lodged = item_name
            return (f"{item_name} lodged in {part_label.lower()} — "
                    f"causing injury. {wound.description}.", wound)

        return f"{item_name} is now lodged in your {part_label.lower()}.", None

    def remove_object(self, item_name: str,
                       skill: int = 0, self_treatment: bool = True
                       ) -> Tuple[bool, str]:
        """
        Remove a foreign object. May cause damage on extraction
        depending on location and what it is.
        Returns (success, message).
        """
        found = None
        for i, obj in enumerate(self.foreign_objects):
            if obj["item"].lower() == item_name.lower():
                found = (i, obj)
                break
        if not found:
            # Check wound lodged objects too
            for w in self.wounds:
                if w.lodged and w.lodged.lower() == item_name.lower():
                    # This is a wound-lodged object — use treatment system
                    success, msg = self.treat_wound(
                        w.id, "extract", skill=skill,
                        self_treatment=self_treatment)
                    return success, msg
            return False, f"Nothing called {item_name} lodged in you."

        idx, obj = found
        self.foreign_objects.pop(idx)
        part_label = PART_DATA.get(obj["part"], {}).get("label", obj["part"])
        return True, f"You remove the {item_name} from your {part_label.lower()}."

    def get_foreign_objects(self) -> List[Dict[str, Any]]:
        """All non-wound foreign objects + wound-lodged items."""
        result = list(self.foreign_objects)
        for w in self.wounds:
            if w.lodged:
                result.append({
                    "item": w.lodged,
                    "part": w.part,
                    "removable": True,
                    "wound_id": w.id,
                })
        return result

    # ── Bandage helpers (backward compat) ──────────────────────────────

    def bandage_worst(self) -> Optional[str]:
        bleeding = sorted(
            [w for w in self.wounds if not w.bandaged and w.is_bleeding],
            key=lambda w: -w.active_bleed)
        if not bleeding:
            return None
        w = bleeding[0]
        w.bandaged = True
        w.treated = True
        return f"You bandage the {w.description.lower()}. Bleeding slows."

    def bandage_all(self) -> str:
        n = 0
        for w in self.wounds:
            if not w.bandaged and w.is_bleeding:
                w.bandaged = True
                w.treated = True
                n += 1
        return f"You bandage {n} wound{'s' if n != 1 else ''}." if n else "No open wounds."

    # ── Blood restore ──────────────────────────────────────────────────

    def restore_blood(self, amount: float):
        self.blood = min(self.max_blood, self.blood + amount)

    def clear_light_wounds(self):
        self.wounds = [w for w in self.wounds if w.severity != Sev.LIGHT]
        self._recalc_pain()

    # ── Display (backward compat) ──────────────────────────────────────

    def blood_bar(self, width: int = 10) -> str:
        filled = max(0, round(self.blood_pct * width))
        return "█" * filled + "░" * (width - filled)

    def blood_color(self) -> tuple:
        p = self.blood_pct
        if p > 0.70: return (80, 180, 80)
        if p > 0.50: return (220, 180, 60)
        if p > 0.30: return (220, 100, 40)
        return (220, 40, 40)

    def summary_lines(self) -> List[Tuple[str, tuple]]:
        WHITE = (255, 255, 255)
        GREY  = (120, 120, 120)
        lines = []

        pct = f"{self.blood_pct*100:.0f}%"
        lines.append((f"Blood  {self.blood_bar(12)} {pct}", self.blood_color()))
        lines.append((f"Bleed: {self.total_bleed_rate:.2f}/min  "
                       f"Pain: {self.total_pain:.0f}  Shock: {self.shock:.0f}",
                       GREY))
        if not self.conscious:
            lines.append(("** UNCONSCIOUS **", (255, 60, 60)))
        lines.append(("", GREY))

        for part in self._body_parts:
            part_wounds = [w for w in self.wounds if w.part == part]
            state = self.part_state.get(part, "intact")
            label = self._part_data.get(part, {}).get("label", part)
            padded = f"{label:<18}"

            if not part_wounds and state == "intact":
                lines.append((f"{padded} intact", GREY))
            else:
                for w in part_wounds:
                    bleed_tag = f" [{w.bleed_level}]" if w.is_bleeding else ""
                    treat_tag = ""
                    if w.bandaged: treat_tag += " [bandaged]"
                    if w.tourniquet: treat_tag += " [tourniquet]"
                    if w.stitched: treat_tag += " [stitched]"
                    if w.splinted: treat_tag += " [splinted]"
                    if w.infected: treat_tag += f" [INFECTED-{w.infection_stage}]"
                    if w.lodged: treat_tag += f" [{w.lodged} lodged]"
                    if w.bone_broken:
                        bt = "compound fracture" if w.compound_fracture else "fracture"
                        if w.bone_set: bt += " (set)"
                        treat_tag += f" [{bt}]"

                    lines.append((
                        f"{padded} {w.wound_type} — {w.severity}{bleed_tag}{treat_tag}",
                        w.severity_color))

        imps = self.impairments
        if imps:
            lines.append(("", GREY))
            lines.append(("Impairments:", (220, 100, 40)))
            for imp in imps:
                lines.append((f"  {imp}", (220, 100, 40)))

        # Foreign objects (non-wound lodged items)
        if self.foreign_objects:
            lines.append(("", GREY))
            lines.append(("Foreign objects:", (180, 140, 60)))
            for obj in self.foreign_objects:
                part_label = PART_DATA.get(obj["part"], {}).get("label", obj["part"])
                lines.append((f"  {obj['item']} — in {part_label.lower()}",
                               (180, 140, 60)))

        return lines

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> Dict:
        return {
            "max_blood": self.max_blood,
            "body_plan": self.body_plan_name,
            "blood": self.blood,
            "shock": self.shock,
            "conscious": self.conscious,
            "part_state": dict(self.part_state),
            "foreign_objects": self.foreign_objects,
            "wounds": [
                {
                    "id": w.id, "part": w.part, "wound_type": w.wound_type,
                    "damage_type": w.damage_type, "severity": w.severity,
                    "bleed_rate": w.bleed_rate, "bandaged": w.bandaged,
                    "tourniquet": w.tourniquet, "cauterized": w.cauterized,
                    "stitched": w.stitched, "pain": w.pain,
                    "dirty": w.dirty, "infected": w.infected,
                    "infection_stage": w.infection_stage,
                    "lodged": w.lodged, "bone_broken": w.bone_broken,
                    "compound_fracture": w.compound_fracture,
                    "bone_set": w.bone_set, "splinted": w.splinted,
                    "sprain": w.sprain, "nerve_damage": w.nerve_damage,
                    "age_days": w.age_days, "treated": w.treated,
                    "treatment_quality": w.treatment_quality,
                    "permanent": w.permanent, "description": w.description,
                }
                for w in self.wounds
            ],
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "HealthTracker":
        ht = cls(d.get("max_blood", 100.0), body_plan=d.get("body_plan", "human"))
        ht.blood = d.get("blood", ht.max_blood)
        ht.shock = d.get("shock", 0.0)
        ht.conscious = d.get("conscious", True)
        ht.part_state = d.get("part_state", {p: "intact" for p in ALL_BODY_PARTS})
        ht.foreign_objects = d.get("foreign_objects", [])
        for wd in d.get("wounds", []):
            ht.wounds.append(DetailedWound(**wd))
        ht._recalc_pain()
        return ht


# ============================================================================
#  SKILL-GATED DESCRIPTION
# ============================================================================

def describe_wound(wound: DetailedWound, medical_skill: int = 0,
                    intelligence: int = 10) -> str:
    """
    Generate a wound description appropriate to the observer's skill.
    Low skill: vague. High skill: clinical detail.

    medical_skill: firstAid skill level (0-10)
    intelligence: INT attribute (1-18)
    """
    score = medical_skill * 2 + (intelligence - 10)
    part_label = PART_DATA.get(wound.part, {}).get("label", wound.part)

    # Level 0: barely literate description
    if score < 3:
        size = "small" if wound.severity == Sev.LIGHT else \
               "bad" if wound.severity == Sev.MODERATE else "real bad"
        wt = "cut" if wound.wound_type in (WndType.CUT, WndType.LACERATION) else \
             "hole" if wound.wound_type in (WndType.STAB, WndType.GUNSHOT) else \
             "bruise" if wound.wound_type == WndType.BRUISE else "hurt"
        bleed = " Bleeding." if wound.is_bleeding else ""
        return f"Got a {size} {wt} on my {part_label.lower()}.{bleed}"

    # Level 1: basic description
    if score < 8:
        bleed = f" Bleeding {wound.bleed_level}." if wound.is_bleeding else ""
        bone = " Feels like something's broken." if wound.bone_broken else ""
        stuck = f" Something's stuck in there." if wound.lodged else ""
        inf = " Looks red and angry." if wound.infected else ""
        return f"{wound.description}.{bleed}{bone}{stuck}{inf}"

    # Level 2: competent field assessment
    if score < 14:
        parts = [wound.description]
        if wound.is_bleeding:
            parts.append(f"Bleeding: {wound.bleed_level} ({wound.active_bleed:.2f}/min)")
        if wound.bone_broken:
            bt = "compound fracture" if wound.compound_fracture else "fracture"
            parts.append(f"Bone: {bt}")
        if wound.lodged:
            parts.append(f"Foreign body: {wound.lodged}")
        if wound.infected:
            parts.append(f"Infection: {wound.infection_stage}")
        if wound.nerve_damage:
            parts.append("Possible nerve involvement")
        return ". ".join(parts) + "."

    # Level 3: trained doctor
    parts = [wound.description]
    parts.append(f"Type: {wound.wound_type}, severity: {wound.severity}")
    if wound.is_bleeding:
        rate_desc = "ARTERIAL" if wound.active_bleed > 2.0 else "significant" \
                    if wound.active_bleed > 0.5 else "moderate"
        parts.append(f"Hemorrhage: {rate_desc} ({wound.active_bleed:.2f} units/min)")
    if wound.bone_broken:
        bt = "compound" if wound.compound_fracture else "simple"
        aligned = "aligned" if wound.bone_set else "displaced"
        parts.append(f"Fracture: {bt}, {aligned}")
    if wound.lodged:
        parts.append(f"Foreign body ({wound.lodged}) requires extraction")
    if wound.infected:
        parts.append(f"Infection stage: {wound.infection_stage} — "
                     f"{'antibacterial wash needed' if wound.infection_stage == 'early' else 'systemic risk'}")
    if wound.nerve_damage:
        parts.append("Nerve damage detected — possible permanent deficit")
    if wound.dirty:
        parts.append("Wound contaminated — must clean before closure")
    parts.append(f"Treatment quality: {wound.treatment_quality:.0%}" if wound.treated
                 else "UNTREATED")
    return ". ".join(parts) + "."


# ============================================================================
#  LLM CONTEXT BUILDER
# ============================================================================

def wounds_llm_context(tracker: HealthTracker) -> str:
    """
    Build a concise wound summary for inclusion in LLM action context.
    """
    if not tracker.wounds:
        return "HEALTH: No injuries. Blood 100%."

    lines = [f"HEALTH: Blood {tracker.blood_pct*100:.0f}%. "
             f"Pain {tracker.total_pain:.0f}. Shock {tracker.shock:.0f}."]

    if not tracker.conscious:
        lines.append("UNCONSCIOUS.")

    for w in tracker.wounds:
        tags = []
        if w.is_bleeding:
            tags.append(f"bleeding-{w.bleed_level}")
        if w.bandaged: tags.append("bandaged")
        if w.lodged: tags.append(f"{w.lodged}-lodged")
        if w.infected: tags.append(f"infected-{w.infection_stage}")
        if w.bone_broken: tags.append("fracture")
        tag_str = f" [{', '.join(tags)}]" if tags else ""
        lines.append(f"  {w.description}{tag_str}")

    return "\n".join(lines)
