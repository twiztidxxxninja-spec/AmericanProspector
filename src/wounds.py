"""
src/wounds.py

Wound and injury system — DF-inspired.
Every creature has blood volume and a list of wounds per body part.
Wounds bleed over time; blood loss degrades function and causes death.
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple


# ── Body parts ────────────────────────────────────────────────────────────────

class Part:
    HEAD       = "head"
    NECK       = "neck"
    TORSO      = "torso"
    ABDOMEN    = "abdomen"
    LEFT_ARM   = "left_arm"
    RIGHT_ARM  = "right_arm"
    LEFT_LEG   = "left_leg"
    RIGHT_LEG  = "right_leg"

ALL_PARTS = [
    Part.HEAD, Part.NECK, Part.TORSO, Part.ABDOMEN,
    Part.LEFT_ARM, Part.RIGHT_ARM, Part.LEFT_LEG, Part.RIGHT_LEG,
]

PART_DISPLAY = {
    Part.HEAD:      "Head     ",
    Part.NECK:      "Neck     ",
    Part.TORSO:     "Torso    ",
    Part.ABDOMEN:   "Abdomen  ",
    Part.LEFT_ARM:  "L. Arm   ",
    Part.RIGHT_ARM: "R. Arm   ",
    Part.LEFT_LEG:  "L. Leg   ",
    Part.RIGHT_LEG: "R. Leg   ",
}

# Hit location probability weights (torso/abdomen = biggest target)
HIT_WEIGHTS = {
    Part.HEAD:      5,
    Part.NECK:      3,
    Part.TORSO:    25,
    Part.ABDOMEN:  18,
    Part.LEFT_ARM:  11,
    Part.RIGHT_ARM: 11,
    Part.LEFT_LEG:  14,
    Part.RIGHT_LEG: 13,
}

# Parts whose damage can directly kill
VITAL_PARTS = {Part.HEAD, Part.NECK, Part.TORSO}

# Functional consequence of a disabled part
PART_IMPAIRMENT = {
    Part.LEFT_ARM:  "left arm useless",
    Part.RIGHT_ARM: "right arm useless",
    Part.LEFT_LEG:  "left leg crippled",
    Part.RIGHT_LEG: "right leg crippled",
    Part.HEAD:      "severe head trauma",
    Part.NECK:      "neck wound",
    Part.TORSO:     "chest wound",
    Part.ABDOMEN:   "gut wound",
}


# ── Wound classification ──────────────────────────────────────────────────────

class DamageType:
    BLUNT     = "blunt"     # fists, rocks, hammer blows
    EDGED     = "edged"     # knives, axes, hatchets
    PIERCING  = "piercing"  # bullets, arrows, spears
    EXPLOSIVE = "explosive" # blast damage


class WoundType:
    BRUISE     = "bruise"     # blunt, no bleed
    SPRAIN     = "sprain"     # joint/tendon, no bleed, functional loss
    CUT        = "cut"        # superficial edged
    LACERATION = "laceration" # deep edged
    PUNCTURE   = "puncture"   # piercing, internal
    FRACTURE   = "fracture"   # bone break (blunt/heavy)
    CRUSH      = "crush"      # heavy blunt, internal bleed


class Severity:
    LIGHT    = "light"
    MODERATE = "moderate"
    SEVERE   = "severe"
    CRITICAL = "critical"

SEV_ORDER = [Severity.LIGHT, Severity.MODERATE, Severity.SEVERE, Severity.CRITICAL]

# Bleed rates (blood units / minute) by wound type × severity
# Blood units: 100 = human adult; 0 = dead
_BLEED = {
    (WoundType.BRUISE,     Severity.LIGHT):    0.00,
    (WoundType.BRUISE,     Severity.MODERATE): 0.00,
    (WoundType.BRUISE,     Severity.SEVERE):   0.00,
    (WoundType.BRUISE,     Severity.CRITICAL): 0.00,
    (WoundType.SPRAIN,     Severity.LIGHT):    0.00,
    (WoundType.SPRAIN,     Severity.MODERATE): 0.00,
    (WoundType.SPRAIN,     Severity.SEVERE):   0.00,
    (WoundType.CUT,        Severity.LIGHT):    0.08,
    (WoundType.CUT,        Severity.MODERATE): 0.20,
    (WoundType.CUT,        Severity.SEVERE):   0.50,
    (WoundType.LACERATION, Severity.LIGHT):    0.20,
    (WoundType.LACERATION, Severity.MODERATE): 0.60,
    (WoundType.LACERATION, Severity.SEVERE):   1.80,
    (WoundType.LACERATION, Severity.CRITICAL): 4.00,
    (WoundType.PUNCTURE,   Severity.LIGHT):    0.15,
    (WoundType.PUNCTURE,   Severity.MODERATE): 0.50,
    (WoundType.PUNCTURE,   Severity.SEVERE):   1.50,
    (WoundType.PUNCTURE,   Severity.CRITICAL): 3.50,
    (WoundType.FRACTURE,   Severity.LIGHT):    0.00,
    (WoundType.FRACTURE,   Severity.MODERATE): 0.10,
    (WoundType.FRACTURE,   Severity.SEVERE):   0.30,
    (WoundType.CRUSH,      Severity.LIGHT):    0.05,
    (WoundType.CRUSH,      Severity.MODERATE): 0.25,
    (WoundType.CRUSH,      Severity.SEVERE):   0.80,
    (WoundType.CRUSH,      Severity.CRITICAL): 2.50,
}

def _bleed_rate(wound_type: str, severity: str) -> float:
    return _BLEED.get((wound_type, severity), 0.0)


# ── Wound ─────────────────────────────────────────────────────────────────────

@dataclass
class Wound:
    part:       str
    wound_type: str
    severity:   str
    bleed_rate: float        # units/min; set at creation
    bandaged:   bool = False
    description: str = ""

    @property
    def active_bleed(self) -> float:
        """Effective bleed rate accounting for bandaging."""
        if self.bandaged:
            return self.bleed_rate * 0.10   # bandage slows to 10%
        return self.bleed_rate

    @property
    def is_bleeding(self) -> bool:
        return self.active_bleed > 0.0

    @property
    def severity_color(self) -> tuple:
        return {
            Severity.LIGHT:    (180, 180, 180),
            Severity.MODERATE: (220, 180,  60),
            Severity.SEVERE:   (220,  80,  40),
            Severity.CRITICAL: (255,  30,  30),
        }.get(self.severity, (255, 255, 255))


# ── Wound generation ──────────────────────────────────────────────────────────

def _classify_severity(damage: float) -> str:
    if damage <  6:  return Severity.LIGHT
    if damage < 15:  return Severity.MODERATE
    if damage < 30:  return Severity.SEVERE
    return Severity.CRITICAL


def _wound_type_for(damage_type: str, severity: str) -> str:
    if damage_type == DamageType.BLUNT:
        return WoundType.BRUISE if severity == Severity.LIGHT else \
               WoundType.FRACTURE if severity == Severity.MODERATE else \
               WoundType.CRUSH
    if damage_type == DamageType.EDGED:
        return WoundType.CUT if severity == Severity.LIGHT else WoundType.LACERATION
    if damage_type == DamageType.PIERCING:
        return WoundType.PUNCTURE
    if damage_type == DamageType.EXPLOSIVE:
        return WoundType.LACERATION if severity != Severity.CRITICAL else WoundType.CRUSH
    return WoundType.BRUISE


def _wound_description(wound_type: str, severity: str, part: str) -> str:
    part_name = PART_DISPLAY.get(part, part).strip().lower()
    if wound_type == WoundType.BRUISE:
        return f"Bruised {part_name}"
    if wound_type == WoundType.SPRAIN:
        return f"Sprained {part_name}"
    if wound_type == WoundType.CUT:
        adj = {"light": "shallow cut", "moderate": "clean cut",
               "severe": "deep cut"}.get(severity, "cut")
        return f"{adj.capitalize()} on {part_name}"
    if wound_type == WoundType.LACERATION:
        adj = {"light": "minor laceration", "moderate": "laceration",
               "severe": "severe laceration",
               "critical": "arterial laceration"}.get(severity, "laceration")
        return f"{adj.capitalize()} of {part_name}"
    if wound_type == WoundType.PUNCTURE:
        adj = {"light": "puncture wound", "moderate": "deep puncture",
               "severe": "penetrating wound",
               "critical": "critical penetrating wound"}.get(severity, "puncture")
        return f"{adj.capitalize()} to {part_name}"
    if wound_type == WoundType.FRACTURE:
        return f"Fractured {part_name}"
    if wound_type == WoundType.CRUSH:
        adj = {"moderate": "crushed", "severe": "badly crushed",
               "critical": "shattered"}.get(severity, "crushed")
        return f"{adj.capitalize()} {part_name}"
    return f"Wound on {part_name}"


def make_wound(damage: float, damage_type: str,
               part: Optional[str] = None) -> Wound:
    """Generate a Wound from hit parameters. Part chosen randomly if not specified."""
    if part is None:
        parts = list(HIT_WEIGHTS.keys())
        weights = [HIT_WEIGHTS[p] for p in parts]
        part = random.choices(parts, weights=weights, k=1)[0]

    severity  = _classify_severity(damage)
    wtype     = _wound_type_for(damage_type, severity)

    # Neck/head wounds upgrade severity by one step
    if part in VITAL_PARTS and severity != Severity.CRITICAL:
        idx = SEV_ORDER.index(severity)
        severity = SEV_ORDER[min(idx + 1, len(SEV_ORDER) - 1)]

    bleed = _bleed_rate(wtype, severity)
    desc  = _wound_description(wtype, severity, part)

    return Wound(part=part, wound_type=wtype, severity=severity,
                 bleed_rate=bleed, description=desc)


# ── CreatureWounds ────────────────────────────────────────────────────────────

# Blood volumes by creature size
MAX_BLOOD = {
    "very_large": 220.0,
    "large":      140.0,
    "medium":      80.0,
    "small":       30.0,
    "tiny":        10.0,
    "human":      100.0,
}


class CreatureWounds:
    """
    Tracks all wounds and blood volume for one creature.
    Compose into Player, NPC, WildlifeInstance.
    """

    def __init__(self, max_blood: float = 100.0):
        self.max_blood: float  = max_blood
        self.blood:     float  = max_blood
        self.wounds:    List[Wound] = []
        # Part functional state: "intact" | "impaired" | "disabled"
        self.part_state: Dict[str, str] = {p: "intact" for p in ALL_PARTS}

    # ── Core properties ───────────────────────────────────────────────────

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
        return [PART_IMPAIRMENT[p] for p, s in self.part_state.items()
                if s in ("impaired", "disabled") and p in PART_IMPAIRMENT]

    # ── Apply hit ─────────────────────────────────────────────────────────

    def apply_hit(self, damage: float, damage_type: str = DamageType.BLUNT,
                  target_part: Optional[str] = None) -> Wound:
        """Generate a wound, apply it, update part state. Returns the wound."""
        wound = make_wound(damage, damage_type, target_part)
        self.wounds.append(wound)
        self._update_part_state(wound)
        return wound

    def _update_part_state(self, wound: Wound):
        part = wound.part
        current = self.part_state.get(part, "intact")
        if current == "disabled":
            return
        if wound.severity == Severity.CRITICAL:
            self.part_state[part] = "disabled"
        elif wound.severity == Severity.SEVERE:
            self.part_state[part] = "impaired" if current == "intact" else "disabled"
        elif wound.severity == Severity.MODERATE and current == "intact":
            self.part_state[part] = "impaired"

    # ── Time tick ─────────────────────────────────────────────────────────

    def tick(self, minutes: float) -> List[str]:
        """
        Apply bleed over `minutes`. Returns warning messages.
        Call from advance_time.
        """
        msgs = []
        old_pct = self.blood_pct

        for wound in self.wounds:
            if wound.active_bleed > 0:
                self.blood = max(0.0, self.blood - wound.active_bleed * minutes)

        new_pct = self.blood_pct

        # Threshold-crossing messages (only warn when crossing down through a threshold)
        thresholds = [
            (0.70, "You feel light-headed from blood loss.",        "advisory"),
            (0.50, "Your vision swims. You're losing too much blood.", "advisory"),
            (0.30, "You're dangerously low on blood. You may pass out.", "critical"),
            (0.10, "You are dying. You need first aid immediately.",  "critical"),
        ]
        for thr, msg, sev in thresholds:
            if old_pct > thr >= new_pct:
                msgs.append((msg, sev))

        return msgs

    # ── Bandage ───────────────────────────────────────────────────────────

    def bandage_worst(self) -> Optional[str]:
        """
        Bandage the worst active bleeding wound.
        Returns description or None if nothing to bandage.
        """
        bleeding = sorted(
            [w for w in self.wounds if not w.bandaged and w.is_bleeding],
            key=lambda w: -w.active_bleed
        )
        if not bleeding:
            return None
        w = bleeding[0]
        w.bandaged = True
        return f"You bandage the {w.description.lower()}. Bleeding slows."

    def bandage_all(self) -> str:
        """Bandage every open wound."""
        n = 0
        for w in self.wounds:
            if not w.bandaged and w.is_bleeding:
                w.bandaged = True
                n += 1
        if n == 0:
            return "No open wounds to bandage."
        return f"You bandage {n} wound{'s' if n>1 else ''}."

    # ── Restore ───────────────────────────────────────────────────────────

    def restore_blood(self, amount: float):
        """Drinking, eating, or time heals blood. Cap at max."""
        self.blood = min(self.max_blood, self.blood + amount)

    def clear_light_wounds(self):
        """Light bruises / minor cuts heal on rest."""
        self.wounds = [w for w in self.wounds
                       if w.severity != Severity.LIGHT]

    # ── Display helpers ───────────────────────────────────────────────────

    def blood_bar(self, width: int = 10) -> str:
        filled = max(0, round(self.blood_pct * width))
        return "█" * filled + "░" * (width - filled)

    def blood_color(self) -> tuple:
        p = self.blood_pct
        if p > 0.70: return ( 80, 180,  80)   # green
        if p > 0.50: return (220, 180,  60)   # yellow
        if p > 0.30: return (220, 100,  40)   # orange
        return                (220,  40,  40)   # red

    def summary_lines(self) -> List[Tuple[str, tuple]]:
        """Returns list of (text, color) lines for health screen display."""
        WHITE    = (255, 255, 255)
        GREY     = (120, 120, 120)
        lines = []

        # Blood volume header
        pct_str = f"{self.blood_pct*100:.0f}%"
        bar = self.blood_bar(12)
        lines.append((f"Blood  {bar} {pct_str}", self.blood_color()))
        lines.append((f"Bleed rate: {self.total_bleed_rate:.2f}/min", GREY))
        lines.append(("", GREY))

        # Per-part status
        for part in ALL_PARTS:
            part_wounds = [w for w in self.wounds if w.part == part]
            state = self.part_state.get(part, "intact")
            if not part_wounds and state == "intact":
                color = GREY
                status = "intact"
            else:
                worst = max(part_wounds, key=lambda w: SEV_ORDER.index(w.severity)) \
                        if part_wounds else None
                if worst:
                    color = worst.severity_color
                    bleed_tag = " [bleeding]" if worst.is_bleeding else ""
                    bndg_tag  = " [bandaged]" if worst.bandaged else ""
                    status = f"{worst.wound_type} — {worst.severity}{bleed_tag}{bndg_tag}"
                else:
                    color, status = GREY, "intact"
            lines.append((f"{PART_DISPLAY[part]} {status}", color))

        # Impairment summary
        imps = self.impairments
        if imps:
            lines.append(("", GREY))
            lines.append(("Impairments:", (220, 100, 40)))
            for imp in imps:
                lines.append((f"  {imp}", (220, 100, 40)))

        return lines


# ── Throw damage type inference ───────────────────────────────────────────────

def damage_type_for_item(item) -> str:
    """Infer DamageType from an item's properties."""
    name_l = item.name.lower()
    # Firearms handled by combat, not throw
    if getattr(item, "weapon_type", "") == "firearm":
        return DamageType.BLUNT   # pistol-whip style
    if any(w in name_l for w in ("knife", "blade", "hatchet", "tomahawk", "axe", "cleaver")):
        return DamageType.EDGED
    if any(w in name_l for w in ("arrow", "bolt", "spear", "dart", "lance")):
        return DamageType.PIERCING
    return DamageType.BLUNT   # rocks, bottles, random objects


def throw_damage(item) -> Tuple[float, str]:
    """
    Base throw damage and damage_type for a thrown item.
    Returns (damage, damage_type).
    """
    dtype = damage_type_for_item(item)
    weight = getattr(item, "weight", 0.5)

    # Power multipliers: sharp/pointed items deal much more damage
    mult = {
        DamageType.EDGED:    3.5,
        DamageType.PIERCING: 4.0,
        DamageType.BLUNT:    1.2,
    }.get(dtype, 1.2)

    # Aerodynamics: very heavy items lose power after a few tiles
    # Captured here as a cap
    dmg = min(weight * mult, 45.0)
    return round(dmg, 1), dtype


# ── Throw hit chance ──────────────────────────────────────────────────────────

def throw_hit_chance(player, dist_tiles: int, target_size: str = "medium") -> float:
    """
    Base hit probability (0.0–1.0) for a thrown object.
    Uses tracking + agility. Range and target size matter.
    """
    tracking = player.skills.get("tracking", 0)
    agility  = player.attributes.get("agility", 10)

    base  = 0.40
    base += tracking * 0.04
    base += (agility - 10) * 0.03
    base -= max(0, dist_tiles - 5) * 0.05   # penalty beyond 5 tiles

    size_mod = {
        "very_large": +0.20,
        "large":      +0.10,
        "medium":      0.00,
        "small":      -0.15,
        "human":       0.00,
    }.get(target_size, 0.0)

    return max(0.05, min(0.95, base + size_mod))
