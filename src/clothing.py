"""
src/clothing.py

Clothing and worn equipment system for American Prospector.
Inspired by Dwarf Fortress Adventure Mode — separate from inventory,
shows exactly what the player is wearing on each body part, tracks
condition, and provides warmth/protection/movement bonuses.

Key classes:
    GarmentDef       — template for a type of garment
    WornItem         — a specific garment instance being worn
    WornEquipment    — all body slots and their contents
    GARMENT_CATALOG  — 30+ historically accurate 1840s garments

Integration:
    Player gets a `worn` field of type WornEquipment.
    SurvivalStats.tick() uses worn.total_warmth() to modify temp_mod.
    Wound system uses worn.protection_for(body_part) to reduce damage.
    LLM custom actions can reference worn items by name.
    Save/load via to_dict() / from_dict().
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any


# ============================================================================
#  BODY SLOTS
# ============================================================================

class BodySlot:
    HEAD  = "head"
    TORSO = "torso"
    OUTER = "outer"    # coat, jacket, poncho — over torso
    LEGS  = "legs"
    FEET  = "feet"
    HANDS = "hands"
    NECK  = "neck"
    WAIST = "waist"


SLOT_ORDER: List[str] = [
    BodySlot.HEAD, BodySlot.NECK, BodySlot.TORSO, BodySlot.OUTER,
    BodySlot.WAIST, BodySlot.HANDS, BodySlot.LEGS, BodySlot.FEET,
]

SLOT_LABELS: Dict[str, str] = {
    "head":  "Head",
    "neck":  "Neck",
    "torso": "Torso",
    "outer": "Outer Layer",
    "waist": "Waist",
    "hands": "Hands",
    "legs":  "Legs",
    "feet":  "Feet",
}

# Map body slots → wound system body parts they protect
SLOT_TO_WOUND_PARTS: Dict[str, List[str]] = {
    "head":  ["head"],
    "neck":  ["head"],       # neck protection reduces head wound severity
    "torso": ["torso"],
    "outer": ["torso", "left arm", "right arm"],
    "waist": ["torso"],
    "hands": ["left arm", "right arm"],
    "legs":  ["left leg", "right leg"],
    "feet":  ["left leg", "right leg"],
}


# ============================================================================
#  CONDITION SYSTEM
# ============================================================================

class Condition:
    EXCELLENT = "Excellent"    # 80-100%
    GOOD      = "Good"         # 60-80%
    WORN      = "Worn"         # 40-60%
    RAGGED    = "Ragged"       # 20-40%
    DESTROYED = "Destroyed"    # 0-20%


def condition_label(value: float) -> str:
    """Convert 0-100 condition float to named label."""
    if value >= 80:
        return Condition.EXCELLENT
    if value >= 60:
        return Condition.GOOD
    if value >= 40:
        return Condition.WORN
    if value >= 20:
        return Condition.RAGGED
    return Condition.DESTROYED


def condition_mult(value: float) -> float:
    """
    Multiplier on warmth/protection based on condition.
    Excellent = 100%, Good = 85%, Worn = 60%, Ragged = 35%, Destroyed = 10%.
    """
    if value >= 80:
        return 1.0
    if value >= 60:
        return 0.85
    if value >= 40:
        return 0.60
    if value >= 20:
        return 0.35
    return 0.10


# ============================================================================
#  MATERIAL PROPERTIES
# ============================================================================

MATERIALS: Dict[str, dict] = {
    "cotton":  {"warmth_mult": 0.6, "wet_penalty": 0.8, "durability": 0.7,
                "label": "Cotton"},
    "wool":    {"warmth_mult": 1.0, "wet_penalty": 0.3, "durability": 0.8,
                "label": "Wool"},     # wool retains warmth when wet
    "flannel": {"warmth_mult": 0.9, "wet_penalty": 0.5, "durability": 0.7,
                "label": "Flannel"},
    "canvas":  {"warmth_mult": 0.5, "wet_penalty": 0.6, "durability": 1.0,
                "label": "Canvas"},   # very durable, low warmth
    "leather": {"warmth_mult": 0.7, "wet_penalty": 0.4, "durability": 0.9,
                "label": "Leather"},
    "buckskin":{"warmth_mult": 0.8, "wet_penalty": 0.3, "durability": 0.85,
                "label": "Buckskin"},
    "fur":     {"warmth_mult": 1.5, "wet_penalty": 0.6, "durability": 0.6,
                "label": "Fur"},
    "felt":    {"warmth_mult": 0.8, "wet_penalty": 0.5, "durability": 0.75,
                "label": "Felt"},
    "silk":    {"warmth_mult": 0.3, "wet_penalty": 0.9, "durability": 0.3,
                "label": "Silk"},
    "straw":   {"warmth_mult": 0.2, "wet_penalty": 0.9, "durability": 0.4,
                "label": "Straw"},
    "rubber":  {"warmth_mult": 0.3, "wet_penalty": 0.0, "durability": 0.6,
                "label": "Rubber"},   # waterproof
}


# ============================================================================
#  GARMENT DEFINITION
# ============================================================================

@dataclass
class GarmentDef:
    """Template defining a type of garment."""
    id: str
    name: str
    slot: str               # BodySlot
    material: str           # key into MATERIALS
    weight: float           # pounds
    warmth: float           # base warmth bonus (0-30)
    protection: float       # base damage reduction (0.0-0.5)
    base_value: float       # dollars
    description: str = ""
    speed_penalty: float = 0.0   # movement speed penalty (0.0-0.3)
    tags: List[str] = field(default_factory=list)
    # tags: "waterproof", "insulating", "armored", "sun_shade", "holster"


# ============================================================================
#  GARMENT CATALOG  — 1840s-1860s American West
# ============================================================================

GARMENT_CATALOG: Dict[str, GarmentDef] = {}

def _g(id, name, slot, mat, wt, warmth, prot, val, desc="", spd=0.0, tags=None):
    GARMENT_CATALOG[id] = GarmentDef(
        id=id, name=name, slot=slot, material=mat, weight=wt,
        warmth=warmth, protection=prot, base_value=val,
        description=desc, speed_penalty=spd, tags=tags or [],
    )

# ── Head ────────────────────────────────────────────────────────────────────
_g("slouch_hat", "Slouch Hat", "head", "felt", 0.4, 3, 0.02, 1.50,
   "Wide-brimmed felt hat. Standard miner's headwear.", tags=["sun_shade"])
_g("straw_hat", "Straw Hat", "head", "straw", 0.2, 1, 0.01, 0.25,
   "Cheap braided straw hat. Keeps the sun off.", tags=["sun_shade"])
_g("fur_cap", "Fur Cap", "head", "fur", 0.6, 8, 0.03, 3.00,
   "Raccoon or beaver fur cap. Warm in mountain winters.", tags=["insulating"])
_g("bandana_head", "Bandana (head)", "head", "cotton", 0.05, 1, 0.0, 0.10,
   "Cotton bandana tied over the head. Keeps dust and sweat out.")
_g("sombrero", "Sombrero", "head", "felt", 0.5, 3, 0.02, 5.00,
   "Wide-brimmed Mexican hat. Excellent sun protection. "
   "Uncommon in Anglo camps — a mark of the vaquero.", tags=["sun_shade"])
_g("bowler_hat", "Bowler Hat", "head", "felt", 0.4, 2, 0.02, 3.00,
   "A stiff felt hat favored by merchants and city folk.")
_g("coonskin_cap", "Coonskin Cap", "head", "fur", 0.7, 9, 0.03, 4.00,
   "Cap made from raccoon hide with tail attached. Mountain man wear.", tags=["insulating"])

# ── Neck ────────────────────────────────────────────────────────────────────
_g("neckerchief", "Neckerchief", "neck", "cotton", 0.05, 1, 0.0, 0.10,
   "Cotton square tied at the throat. Pulls up over nose in dust.")
_g("wool_scarf", "Wool Scarf", "neck", "wool", 0.2, 5, 0.0, 0.50,
   "Heavy knitted wool scarf. Essential in cold weather.", tags=["insulating"])
_g("silk_cravat", "Silk Cravat", "neck", "silk", 0.05, 0, 0.0, 2.00,
   "A dandy's neckcloth. Offers no warmth but looks fine.")
_g("leather_gorget", "Leather Gorget", "neck", "leather", 0.3, 1, 0.08, 1.50,
   "Thick leather neck guard. Uncommon but effective protection.")

# ── Torso ───────────────────────────────────────────────────────────────────
_g("cotton_shirt", "Cotton Work Shirt", "torso", "cotton", 0.4, 3, 0.02, 0.75,
   "Plain cotton work shirt. The universal garment of the diggings.")
_g("wool_shirt", "Wool Shirt", "torso", "wool", 0.6, 6, 0.03, 1.50,
   "Heavy wool pullover shirt. Warm even when damp.", tags=["insulating"])
_g("flannel_shirt", "Flannel Shirt", "torso", "flannel", 0.5, 5, 0.02, 1.00,
   "Soft brushed flannel. Comfortable and warm.")
_g("calico_shirt", "Calico Shirt", "torso", "cotton", 0.3, 2, 0.01, 0.50,
   "Printed cotton calico. Cheap and colorful.")
_g("buckskin_shirt", "Buckskin Shirt", "torso", "buckskin", 0.8, 6, 0.08, 4.00,
   "Native-style buckskin tunic. Tough and warm.", tags=["insulating"])
_g("linen_undershirt", "Linen Undershirt", "torso", "cotton", 0.2, 1, 0.0, 0.30,
   "A thin linen undergarment. Worn beneath outer shirts.")

# ── Outer Layer ─────────────────────────────────────────────────────────────
_g("wool_coat", "Wool Coat", "outer", "wool", 3.0, 12, 0.06, 8.00,
   "Heavy wool overcoat. Essential for mountain winters.", spd=0.03, tags=["insulating"])
_g("canvas_duster", "Canvas Duster", "outer", "canvas", 2.5, 5, 0.05, 4.00,
   "Long canvas riding coat. Repels rain and brush.", tags=["waterproof"])
_g("poncho", "Poncho", "outer", "wool", 1.5, 8, 0.03, 3.00,
   "Wool poncho. Quick on and off; doubles as a blanket.", tags=["insulating"])
_g("buckskin_jacket", "Buckskin Jacket", "outer", "buckskin", 2.0, 8, 0.10, 6.00,
   "Fringed buckskin jacket. Frontier classic — tough and warm.", tags=["insulating"])
_g("blanket_coat", "Blanket Coat", "outer", "wool", 3.5, 14, 0.04, 5.00,
   "A coat cut from a Hudson's Bay blanket. Extremely warm.", spd=0.05, tags=["insulating"])
_g("oilskin_slicker", "Oilskin Slicker", "outer", "canvas", 2.0, 3, 0.03, 5.00,
   "Waterproofed canvas coat. Keeps you dry in downpours.", tags=["waterproof"])
_g("vest_wool", "Wool Vest", "outer", "wool", 0.5, 4, 0.02, 2.00,
   "Buttoned wool vest. Adds warmth without bulk.")
_g("vest_leather", "Leather Vest", "outer", "leather", 0.8, 3, 0.06, 3.50,
   "Thick leather vest. Some protection; pockets.")

# ── Legs ────────────────────────────────────────────────────────────────────
_g("duck_trousers", "Canvas Duck Trousers", "legs", "canvas", 1.0, 3, 0.03, 1.50,
   "Sturdy canvas trousers. The miner's standard — nearly indestructible.")
_g("wool_trousers", "Wool Trousers", "legs", "wool", 1.2, 6, 0.03, 3.00,
   "Heavy wool trousers. Warm in cold weather.", tags=["insulating"])
_g("buckskin_leggings", "Buckskin Leggings", "legs", "buckskin", 1.0, 5, 0.06, 4.00,
   "Native-style leggings. Quiet movement, good protection.")
_g("cotton_trousers", "Cotton Trousers", "legs", "cotton", 0.7, 2, 0.02, 1.00,
   "Lightweight cotton pants. Comfortable in summer heat.")

# ── Feet ────────────────────────────────────────────────────────────────────
_g("leather_boots", "Leather Boots", "feet", "leather", 2.5, 4, 0.08, 5.00,
   "Tall leather boots. Essential footwear for rough country.")
_g("brogans", "Brogans", "feet", "leather", 1.5, 3, 0.06, 2.50,
   "Heavy work shoes. Cheaper than boots but less ankle support.")
_g("moccasins", "Moccasins", "feet", "buckskin", 0.4, 2, 0.02, 1.50,
   "Soft buckskin moccasins. Quiet and comfortable; wear out fast.")
_g("oiled_boots", "Oiled Leather Boots", "feet", "leather", 3.0, 4, 0.06, 10.00,
   "Heavy leather boots treated with tallow and beeswax. Water-resistant for creek work.",
   spd=0.02, tags=["waterproof"])

# ── Hands ───────────────────────────────────────────────────────────────────
_g("leather_gloves", "Leather Work Gloves", "hands", "leather", 0.3, 2, 0.05, 1.00,
   "Heavy cowhide gloves. Protect hands while digging and hauling.")
_g("buckskin_gauntlets", "Buckskin Gauntlets", "hands", "buckskin", 0.4, 3, 0.06, 2.50,
   "Long-cuffed buckskin gloves. Good for riding and brush.")
_g("wool_mittens", "Wool Mittens", "hands", "wool", 0.2, 6, 0.01, 0.75,
   "Thick wool mittens. Very warm; hard to do fine work in.", spd=0.02, tags=["insulating"])
_g("fingerless_gloves", "Fingerless Gloves", "hands", "leather", 0.2, 1, 0.03, 0.75,
   "Cut-off leather gloves. Protect palms; leave fingers free.")

# ── Waist ───────────────────────────────────────────────────────────────────
_g("leather_belt", "Leather Belt", "waist", "leather", 0.3, 0, 0.02, 0.75,
   "Plain leather belt. Holds up trousers and carries a knife sheath.")
_g("gun_belt", "Gun Belt", "waist", "leather", 0.8, 0, 0.03, 4.00,
   "Wide leather belt with holster loops. Carries a pistol and cartridges.", tags=["holster"])
_g("sash", "Sash", "waist", "cotton", 0.1, 1, 0.0, 0.50,
   "Wide cloth sash. Mexican and Chilean miners often wear these.")
_g("money_belt", "Money Belt", "waist", "leather", 0.2, 0, 0.01, 2.00,
   "Thin belt with a hidden pouch for coins and gold dust.")


# ============================================================================
#  WORN ITEM INSTANCE
# ============================================================================

@dataclass
class WornItem:
    """A specific garment instance being worn by the player."""
    garment_id: str         # key into GARMENT_CATALOG
    name: str
    slot: str               # BodySlot
    condition: float        # 0-100
    material: str           # key into MATERIALS
    warmth: float           # base warmth bonus
    protection: float       # base damage reduction (0.0-0.5)
    weight: float
    base_value: float
    speed_penalty: float = 0.0
    tags: List[str] = field(default_factory=list)
    wet: bool = False       # currently wet (rain, river crossing)
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def condition_label(self) -> str:
        return condition_label(self.condition)

    @property
    def effective_warmth(self) -> float:
        """Warmth adjusted for condition and wetness."""
        base = self.warmth * condition_mult(self.condition)
        if self.wet:
            mat = MATERIALS.get(self.material, {})
            penalty = mat.get("wet_penalty", 0.5)
            base *= (1.0 - penalty)
        return base

    @property
    def effective_protection(self) -> float:
        """Protection adjusted for condition."""
        return self.protection * condition_mult(self.condition)

    def degrade(self, amount: float) -> None:
        """Reduce condition by amount (0-100 scale)."""
        self.condition = max(0.0, self.condition - amount)

    def display(self) -> str:
        """One-line display for UI."""
        cond = self.condition_label
        wet_str = " [WET]" if self.wet else ""
        return f"{self.name} ({cond}){wet_str}"

    @classmethod
    def from_garment(cls, garment_id: str, condition: float = 100.0) -> "WornItem":
        """Create a WornItem from a catalog garment definition."""
        gdef = GARMENT_CATALOG.get(garment_id)
        if not gdef:
            raise ValueError(f"Unknown garment: {garment_id}")
        return cls(
            garment_id=gdef.id, name=gdef.name, slot=gdef.slot,
            condition=condition, material=gdef.material,
            warmth=gdef.warmth, protection=gdef.protection,
            weight=gdef.weight, base_value=gdef.base_value,
            speed_penalty=gdef.speed_penalty, tags=list(gdef.tags),
        )


# ============================================================================
#  WORN EQUIPMENT  (all body slots)
# ============================================================================

class WornEquipment:
    """
    Tracks all clothing and equipment worn on the player's body.
    Separate from inventory — equipping moves items here, unequipping
    moves them back to inventory.
    """

    def __init__(self):
        self.slots: Dict[str, Optional[WornItem]] = {
            slot: None for slot in SLOT_ORDER
        }

    # ── Equip / Unequip ────────────────────────────────────────────────

    def equip(self, item: WornItem) -> Optional[WornItem]:
        """
        Equip item to its body slot.
        Returns the previously worn item (if any) so it can go to inventory.
        """
        old = self.slots.get(item.slot)
        self.slots[item.slot] = item
        return old

    def unequip(self, slot: str) -> Optional[WornItem]:
        """Remove and return item from a body slot."""
        item = self.slots.get(slot)
        if item:
            self.slots[slot] = None
        return item

    def get(self, slot: str) -> Optional[WornItem]:
        """Get item in a slot without removing it."""
        return self.slots.get(slot)

    def is_wearing(self, garment_id: str) -> bool:
        """Check if a specific garment type is currently worn."""
        return any(w and w.garment_id == garment_id
                   for w in self.slots.values())

    def find_by_name(self, name: str) -> Optional[WornItem]:
        """Find a worn item by display name (for LLM action matching)."""
        nl = name.lower()
        for item in self.slots.values():
            if item and item.name.lower() == nl:
                return item
        return None

    def remove_by_name(self, name: str) -> Optional[WornItem]:
        """Remove a worn item by name. Returns it or None."""
        nl = name.lower()
        for slot, item in self.slots.items():
            if item and item.name.lower() == nl:
                self.slots[slot] = None
                return item
        return None

    # ── Stat queries ───────────────────────────────────────────────────

    def total_warmth(self) -> float:
        """Total warmth bonus from all worn clothing."""
        return sum(w.effective_warmth for w in self.slots.values() if w)

    def total_weight(self) -> float:
        """Total weight of all worn clothing."""
        return sum(w.weight for w in self.slots.values() if w)

    def total_speed_penalty(self) -> float:
        """Total movement speed penalty from heavy/bulky clothing."""
        return sum(w.speed_penalty for w in self.slots.values() if w)

    def protection_for(self, body_part: str) -> float:
        """
        Damage reduction for a specific wound body part.
        Checks all slots that cover this body part and returns
        the highest effective protection value.
        """
        best = 0.0
        for slot, parts in SLOT_TO_WOUND_PARTS.items():
            if body_part in parts:
                item = self.slots.get(slot)
                if item:
                    best = max(best, item.effective_protection)
        return best

    def has_tag(self, tag: str) -> bool:
        """Check if any worn item has a specific tag (e.g., 'waterproof')."""
        return any(w and tag in w.tags for w in self.slots.values())

    def is_waterproof(self) -> bool:
        return self.has_tag("waterproof")

    # ── Condition degradation ──────────────────────────────────────────

    def tick_wear(self, minutes: int, activity: str = "normal") -> List[str]:
        """
        Degrade all worn clothing based on time and activity.
        Returns list of warning messages for items crossing condition thresholds.

        activity: "normal" | "labor" | "combat" | "crawling" | "swimming"
        """
        warnings: List[str] = []

        # Base degradation per hour
        base_rate = {
            "normal":   0.01,
            "labor":    0.04,
            "combat":   0.10,
            "crawling": 0.06,
            "swimming": 0.05,
        }.get(activity, 0.01)

        hours = minutes / 60.0

        for slot, item in self.slots.items():
            if not item:
                continue

            mat = MATERIALS.get(item.material, {})
            durability = mat.get("durability", 0.7)
            # Tougher materials degrade slower
            degrade = base_rate * hours / max(0.1, durability)

            # Extra degradation for specific activities + slots
            if activity == "crawling" and slot in ("torso", "legs", "hands"):
                degrade *= 2.0
            if activity == "swimming":
                item.wet = True

            old_label = item.condition_label
            item.degrade(degrade)
            new_label = item.condition_label

            if old_label != new_label and new_label in (Condition.RAGGED, Condition.DESTROYED):
                warnings.append(f"Your {item.name} is now {new_label.lower()}.")

        return warnings

    def dry_all(self) -> None:
        """Mark all wet items as dry (after resting by a fire, etc.)."""
        for item in self.slots.values():
            if item:
                item.wet = False

    def get_wet_items(self) -> List[WornItem]:
        """Return all currently wet items."""
        return [w for w in self.slots.values() if w and w.wet]

    def soak_all(self) -> None:
        """Make all items wet (river crossing, heavy rain)."""
        for item in self.slots.values():
            if item:
                item.wet = True

    # ── Display ────────────────────────────────────────────────────────

    def display_lines(self) -> List[Tuple[str, str]]:
        """Return list of (slot_label, item_display) for UI rendering."""
        lines = []
        for slot in SLOT_ORDER:
            label = SLOT_LABELS[slot]
            item = self.slots.get(slot)
            if item:
                lines.append((label, item.display()))
            else:
                lines.append((label, "-- empty --"))
        return lines

    def summary(self) -> str:
        """Multi-line summary for LLM context."""
        parts = []
        for slot in SLOT_ORDER:
            item = self.slots.get(slot)
            if item:
                parts.append(f"  {SLOT_LABELS[slot]}: {item.name} ({item.condition_label})")
        if not parts:
            return "  Wearing nothing."
        return "\n".join(parts)

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> Dict:
        result = {}
        for slot, item in self.slots.items():
            if item:
                result[slot] = {
                    "garment_id": item.garment_id, "name": item.name,
                    "slot": item.slot, "condition": item.condition,
                    "material": item.material, "warmth": item.warmth,
                    "protection": item.protection, "weight": item.weight,
                    "base_value": item.base_value,
                    "speed_penalty": item.speed_penalty,
                    "tags": item.tags, "wet": item.wet,
                    "extra": item.extra,
                }
        return result

    @classmethod
    def from_dict(cls, d: Dict) -> "WornEquipment":
        eq = cls()
        for slot, data in d.items():
            if slot in SLOT_ORDER and data:
                eq.slots[slot] = WornItem(**data)
        return eq


# ============================================================================
#  STARTING OUTFIT
# ============================================================================

def starting_outfit() -> WornEquipment:
    """Default clothing for a Forty-Niner arriving in California."""
    eq = WornEquipment()
    eq.equip(WornItem.from_garment("slouch_hat",      condition=90))
    eq.equip(WornItem.from_garment("neckerchief",     condition=95))
    eq.equip(WornItem.from_garment("cotton_shirt",    condition=85))
    eq.equip(WornItem.from_garment("leather_belt",    condition=90))
    eq.equip(WornItem.from_garment("duck_trousers",   condition=85))
    eq.equip(WornItem.from_garment("leather_boots",   condition=80))
    return eq


# ============================================================================
#  INTEGRATION HELPERS
# ============================================================================

def warmth_modifier(worn: WornEquipment) -> float:
    """
    Returns a temperature modifier for SurvivalStats.tick().
    Positive = warmer (reduces cold damage), negative = colder.

    Usage in engine.advance_time():
        from src.clothing import warmth_modifier
        temp_mod = base_temperature + warmth_modifier(player.worn)
        player.survival.tick(minutes, temp_mod=temp_mod)
    """
    return worn.total_warmth()


def damage_after_clothing(raw_damage: float, body_part: str,
                           worn: WornEquipment) -> Tuple[float, Optional[str]]:
    """
    Reduce incoming damage by clothing protection on the hit body part.
    Returns (reduced_damage, clothing_message_or_None).

    Usage in combat/wound application:
        final_dmg, msg = damage_after_clothing(raw, part, player.worn)
    """
    prot = worn.protection_for(body_part)
    if prot <= 0:
        return raw_damage, None

    reduced = raw_damage * (1.0 - prot)
    absorbed = raw_damage - reduced

    # Damage the clothing that provided protection
    for slot, parts in SLOT_TO_WOUND_PARTS.items():
        if body_part in parts:
            item = worn.get(slot)
            if item:
                # Clothing takes condition damage proportional to hit force
                item.degrade(absorbed * 0.5)
                material_name = MATERIALS.get(item.material, {}).get("label", item.material)
                msg = f"Your {item.name} absorbs some of the blow."
                return reduced, msg

    return reduced, None
