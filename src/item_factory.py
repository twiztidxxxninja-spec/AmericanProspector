"""
src/item_factory.py

Infinite item creation system for American Prospector.

Any item the player creates through LLM custom actions becomes a fully
functional game object — not just flavor text.  The LLM is called ONCE
to categorize a new item type; the result is permanently saved so all
future instances are consistent and require no LLM call.

Pipeline:
    1. LLM action resolves → items_gained: ["Improvised Water Filter"]
    2. Engine calls ItemFactory.create("Improvised Water Filter", context)
    3. Factory checks catalog:
       - Known? → build Item from saved ItemBlueprint
       - New?   → call LLM to categorize → save blueprint → build Item
    4. Item added to inventory with full stats, tool tags, weapon data, etc.

Integration:
    In engine.py __init__:
        from src.item_factory import ItemFactory
        self.item_factory = ItemFactory(self.llm)

    Replace _apply_llm_items() body with:
        for name in items_gained:
            item = self.item_factory.create(name, context, player_skill, quality)
            player.inventory.append(item)
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.llm_client import LLMClient

from src.items import Item, ITEM_TEMPLATES


# ============================================================================
#  ITEM BLUEPRINT — the permanent saved definition for an item type
# ============================================================================

@dataclass
class ItemBlueprint:
    """
    Complete definition for a player-created item type.
    Generated once by the LLM, then saved permanently to catalog.
    All future instances of this item use this data directly.
    """
    id: str                             # "improvised_water_filter"
    name: str                           # "Improvised Water Filter"
    weight: float                       # pounds
    category: str                       # tool|weapon|food|drink|material|clothing|container|misc
    description: str                    # flavor text
    base_value: float                   # dollars at fair market
    quality: str = "standard"           # improvised|poor|standard|good|excellent

    # Tool
    tool_tags: List[str] = field(default_factory=list)

    # Weapon
    weapon_type: str = ""               # "" | "melee" | "firearm" | "thrown"
    damage_min: int = 0
    damage_max: int = 0
    damage_type: str = ""               # "blunt"|"edged"|"piercing"

    # Food / Drink
    nutrition: float = 0.0
    hydration: float = 0.0
    perishable: bool = False
    days_until_spoil: Optional[int] = None

    # Clothing / Armor
    clothing_slot: str = ""             # BodySlot or ""
    warmth: float = 0.0
    protection: float = 0.0

    # Container
    capacity_lb: float = 0.0           # carrying capacity if container

    # Stacking
    stackable: bool = False

    # Durability (starting condition 0-100)
    durability: float = 100.0

    # Arbitrary tags for game system integration
    tags: List[str] = field(default_factory=list)
    # e.g. ["waterproof", "fragile", "flammable", "two_handed", "light_source"]

    # Special properties the LLM assigned
    special: Dict[str, Any] = field(default_factory=dict)
    # e.g. {"purify_water": true, "light_radius": 3, "noise_level": "loud"}

    # Creation metadata
    materials_hint: str = ""            # what materials were used
    creation_skill: str = ""            # skill used to create
    creation_difficulty: int = 10       # how hard to make (1-20)
    source: str = "llm"                 # "builtin" | "llm"


# ============================================================================
#  CATALOG PERSISTENCE
# ============================================================================

CATALOG_PATH = os.path.join("data", "item_catalog.json")


def _save_catalog(catalog: Dict[str, ItemBlueprint]) -> None:
    """Save the item catalog to disk."""
    os.makedirs(os.path.dirname(CATALOG_PATH) or ".", exist_ok=True)
    data = {}
    for key, bp in catalog.items():
        d = {
            "id": bp.id, "name": bp.name, "weight": bp.weight,
            "category": bp.category, "description": bp.description,
            "base_value": bp.base_value, "quality": bp.quality,
            "tool_tags": bp.tool_tags, "weapon_type": bp.weapon_type,
            "damage_min": bp.damage_min, "damage_max": bp.damage_max,
            "damage_type": bp.damage_type,
            "nutrition": bp.nutrition, "hydration": bp.hydration,
            "perishable": bp.perishable, "days_until_spoil": bp.days_until_spoil,
            "clothing_slot": bp.clothing_slot, "warmth": bp.warmth,
            "protection": bp.protection, "capacity_lb": bp.capacity_lb,
            "stackable": bp.stackable, "durability": bp.durability,
            "tags": bp.tags, "special": bp.special,
            "materials_hint": bp.materials_hint,
            "creation_skill": bp.creation_skill,
            "creation_difficulty": bp.creation_difficulty,
            "source": bp.source,
        }
        data[key] = d
    with open(CATALOG_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _load_catalog() -> Dict[str, ItemBlueprint]:
    """Load saved catalog from disk."""
    if not os.path.exists(CATALOG_PATH):
        return {}
    try:
        with open(CATALOG_PATH, "r") as f:
            data = json.load(f)
        catalog = {}
        for key, d in data.items():
            catalog[key] = ItemBlueprint(
                id=d["id"], name=d["name"], weight=d["weight"],
                category=d["category"], description=d.get("description", ""),
                base_value=d.get("base_value", 0),
                quality=d.get("quality", "standard"),
                tool_tags=d.get("tool_tags", []),
                weapon_type=d.get("weapon_type", ""),
                damage_min=d.get("damage_min", 0),
                damage_max=d.get("damage_max", 0),
                damage_type=d.get("damage_type", ""),
                nutrition=d.get("nutrition", 0),
                hydration=d.get("hydration", 0),
                perishable=d.get("perishable", False),
                days_until_spoil=d.get("days_until_spoil"),
                clothing_slot=d.get("clothing_slot", ""),
                warmth=d.get("warmth", 0),
                protection=d.get("protection", 0),
                capacity_lb=d.get("capacity_lb", 0),
                stackable=d.get("stackable", False),
                durability=d.get("durability", 100),
                tags=d.get("tags", []),
                special=d.get("special", {}),
                materials_hint=d.get("materials_hint", ""),
                creation_skill=d.get("creation_skill", ""),
                creation_difficulty=d.get("creation_difficulty", 10),
                source=d.get("source", "llm"),
            )
        return catalog
    except Exception:
        return {}


# ============================================================================
#  QUALITY FROM SKILL
# ============================================================================

def _quality_from_skill(skill_level: int, intelligence: int) -> str:
    """Determine item quality based on creator's skill and INT."""
    score = skill_level * 2 + max(0, intelligence - 10)
    if score < 3:
        return "improvised"
    if score < 6:
        return "poor"
    if score < 12:
        return "standard"
    if score < 18:
        return "good"
    return "excellent"


# Quality multipliers for item stats
_QUALITY_MULT = {
    "improvised": 0.5,
    "poor":       0.7,
    "standard":   1.0,
    "good":       1.2,
    "excellent":  1.4,
}


# ============================================================================
#  NORMALIZE KEY
# ============================================================================

def _normalize(name: str) -> str:
    """Normalize an item name into a catalog lookup key."""
    return name.strip().lower().replace(" ", "_").replace("'", "").replace('"', '')


# ============================================================================
#  ITEM FACTORY
# ============================================================================

class ItemFactory:
    """
    Creates fully-categorized Item objects from names.

    Known items (built-in templates + previously categorized) return
    instantly.  Unknown items are categorized via a single LLM call,
    then saved permanently.
    """

    def __init__(self, llm: Optional["LLMClient"] = None):
        self.llm = llm
        self.catalog: Dict[str, ItemBlueprint] = {}
        self._load()

    def _load(self) -> None:
        """Load built-in templates + saved catalog."""
        # Built-in items → blueprints (never re-categorized)
        for tid, tdata in ITEM_TEMPLATES.items():
            bp = _template_to_blueprint(tid, tdata)
            self.catalog[_normalize(bp.name)] = bp

        # Saved LLM-created items
        saved = _load_catalog()
        for key, bp in saved.items():
            if key not in self.catalog:
                self.catalog[key] = bp

    def save(self) -> None:
        """Save LLM-created blueprints to disk (call on game save)."""
        llm_only = {k: v for k, v in self.catalog.items()
                    if v.source == "llm"}
        if llm_only:
            _save_catalog(llm_only)

    # ── Main creation entry point ──────────────────────────────────────

    def create(self, name: str,
               context: Optional[Dict[str, Any]] = None,
               skill_level: int = 0,
               intelligence: int = 10,
               materials_used: Optional[List[str]] = None
               ) -> Item:
        """
        Create a fully functional Item from a name.

        If the item type is already known (built-in or previously
        categorized), returns instantly from the blueprint.

        If unknown, calls the LLM once to categorize it, saves the
        blueprint permanently, then creates the Item.
        """
        key = _normalize(name)

        if key not in self.catalog:
            bp = self._categorize(name, context or {}, materials_used or [])
            if bp:
                self.catalog[key] = bp
                self.save()

        bp = self.catalog.get(key)
        if bp:
            quality = _quality_from_skill(skill_level, intelligence)
            return self._instantiate(bp, quality)

        # Absolute fallback — no LLM, no match
        return _fallback_item(name)

    def create_from_response(self, items_gained: List[str],
                               context: Dict[str, Any],
                               player,
                               equip_right: Optional[str] = None,
                               equip_left: Optional[str] = None
                               ) -> List[str]:
        """
        Replacement for engine._apply_llm_items().
        Creates all gained items with full categorization.
        Returns list of messages.
        """
        msgs: List[str] = []
        created: Dict[str, Item] = {}

        skill = max(player.skills.values()) if player.skills else 0
        intel = player.attributes.get("intelligence", 10)
        materials = [str(i) for i in context.get("items_used", [])]

        for name in items_gained:
            name = name.strip()
            if not name:
                continue
            item = self.create(name, context, skill, intel, materials)
            player.inventory.append(item)
            created[name.lower()] = item

            q_tag = f" [{item.quality}]" if item.quality != "standard" else ""
            cat_tag = f" ({item.category})"
            msgs.append(f"  + {item.name}{q_tag}{cat_tag} added to inventory.")

        # Equip to hands
        if equip_right:
            match = created.get(equip_right.lower()) or next(
                (i for i in player.inventory
                 if i.name.lower() == equip_right.lower()), None)
            if match:
                player.right_hand = match.name
        if equip_left:
            match = created.get(equip_left.lower()) or next(
                (i for i in player.inventory
                 if i.name.lower() == equip_left.lower()), None)
            if match:
                player.left_hand = match.name

        return msgs

    # ── LLM Categorization ─────────────────────────────────────────────

    def _categorize(self, name: str, context: Dict[str, Any],
                     materials: List[str]) -> Optional[ItemBlueprint]:
        """Call the LLM once to fully categorize a new item type."""
        if not self.llm or not self.llm.available:
            return _heuristic_blueprint(name)

        self.llm._load()
        if not self.llm.available:
            return _heuristic_blueprint(name)

        prompt = _build_categorization_prompt(name, context, materials)

        try:
            raw = self.llm._chat(
                [
                    {"role": "system", "content": _CATEGORIZE_SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.25,
                max_tokens=600,
                json_mode=True,
            )
            return _parse_categorization(raw, name)
        except Exception:
            return _heuristic_blueprint(name)

    # ── Instantiation ──────────────────────────────────────────────────

    def _instantiate(self, bp: ItemBlueprint, quality: str) -> Item:
        """Create a concrete Item from a blueprint + quality modifier."""
        qm = _QUALITY_MULT.get(quality, 1.0)

        item = Item(
            id=bp.id,
            name=bp.name,
            weight=bp.weight,
            category=bp.category,
            description=bp.description,
            nutrition=bp.nutrition,
            hydration=bp.hydration,
            perishable=bp.perishable,
            days_until_spoil=bp.days_until_spoil,
            tool_tags=list(bp.tool_tags),
            condition=min(100.0, bp.durability * qm),
            quality=quality,
            damage_min=max(0, int(bp.damage_min * qm)),
            damage_max=max(0, int(bp.damage_max * qm)),
            weapon_type=bp.weapon_type,
            base_value=round(bp.base_value * qm, 2),
            stackable=bp.stackable,
            quantity=1,
            extra=dict(bp.special),
        )

        # Inject clothing data into extra for the clothing system
        if bp.clothing_slot:
            item.extra["clothing_slot"] = bp.clothing_slot
            item.extra["warmth"] = bp.warmth * qm
            item.extra["protection"] = bp.protection * qm

        # Inject container data
        if bp.capacity_lb > 0:
            item.extra["capacity_lb"] = bp.capacity_lb * qm

        # Copy tags
        item.extra["tags"] = list(bp.tags)

        return item

    # ── Lookup ─────────────────────────────────────────────────────────

    def get_blueprint(self, name: str) -> Optional[ItemBlueprint]:
        return self.catalog.get(_normalize(name))

    def knows(self, name: str) -> bool:
        return _normalize(name) in self.catalog


# ============================================================================
#  LLM CATEGORIZATION PROMPT
# ============================================================================

_CATEGORIZE_SYSTEM = """\
You are a game item categorizer for American Prospector, a historically \
accurate frontier survival game starting in 1849 America.

When a player creates an item through freeform action, you assign it \
proper game mechanics based on what the player actually has available — \
their materials, tools, skills, knowledge, and any infrastructure they \
have built.

CRITICAL RULE — ANYTHING IS POSSIBLE given sufficient steps:
A player CAN build advanced or complex items IF they have done the \
prerequisite work. Building a steam engine requires first building a \
forge, sourcing iron, learning metallurgy, etc. — dozens of individual \
steps, each judged independently. If the player has completed those \
steps and has the materials and knowledge, the item is valid. \
Do NOT reject items based on calendar year alone. Reject only if the \
player clearly lacks the materials, tools, or knowledge right now.

Quality and function must match the materials, tools, and skill level \
described. Improvised items from raw materials should have lower stats \
than items made with proper tools and training. A knife carved from \
flint is valid but weaker than one forged from steel.

Return ONLY valid JSON with the exact fields specified. No commentary.
"""


def _build_categorization_prompt(name: str, context: Dict[str, Any],
                                   materials: List[str]) -> str:
    region = context.get("region", "California frontier")
    year = context.get("year", 1849)
    skills_str = ", ".join(f"{k}:{v}" for k, v in context.get("skills", {}).items()
                           if v > 0) or "untrained"
    mat_str = ", ".join(materials) if materials else "unspecified"

    return f"""\
ITEM TO CATEGORIZE: "{name}"
MATERIALS USED: {mat_str}
SETTING: {region}, year {year}
PLAYER SKILLS: {skills_str}

Return JSON with exactly these fields:
{{
  "name": "{name}",
  "weight": <float, pounds — estimate realistically>,
  "category": <"tool"|"weapon"|"food"|"drink"|"material"|"clothing"|"container"|"misc">,
  "description": <string, 1-2 sentence physical description>,
  "base_value": <float, dollars — what a frontier merchant would pay>,
  "tool_tags": <list of strings — functional tags like "dig", "chop", "cut", "pan", \
"filter_water", "light", "carry_water", "navigate", "measure", etc. Empty list if not a tool>,
  "weapon_type": <""|"melee"|"firearm"|"thrown" — empty string if not a weapon>,
  "damage_min": <int, minimum damage if weapon, else 0>,
  "damage_max": <int, maximum damage if weapon, else 0>,
  "damage_type": <""|"blunt"|"edged"|"piercing" — empty if not weapon>,
  "nutrition": <float 0-50, hunger restored if food, else 0>,
  "hydration": <float 0-50, thirst restored if drink, else 0>,
  "perishable": <bool>,
  "days_until_spoil": <int or null>,
  "clothing_slot": <""|"head"|"neck"|"torso"|"outer"|"waist"|"hands"|"legs"|"feet">,
  "warmth": <float 0-30, warmth bonus if clothing, else 0>,
  "protection": <float 0.0-0.5, damage reduction if armor/clothing, else 0>,
  "capacity_lb": <float, carrying capacity in pounds if container, else 0>,
  "stackable": <bool — true only for simple consumables/materials>,
  "durability": <float 10-100 — how sturdy; improvised items 20-50, well-made 70-100>,
  "tags": <list of strings — any of: "fragile", "heavy", "waterproof", "flammable", \
"two_handed", "light_source", "noisy", "sharp", "blunt", "insulating", etc.>,
  "special": <object — any unique properties as key:value pairs, or empty {{}}>,
  "creation_skill": <string — which skill was primarily used to make this>,
  "creation_difficulty": <int 1-20 — how hard to make>
}}"""


# ============================================================================
#  PARSE LLM RESPONSE
# ============================================================================

def _parse_categorization(raw: str, fallback_name: str) -> Optional[ItemBlueprint]:
    """Parse LLM JSON into an ItemBlueprint."""
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return None

    name = str(d.get("name", fallback_name)).strip()
    item_id = _normalize(name)

    return ItemBlueprint(
        id=item_id,
        name=name,
        weight=max(0.01, float(d.get("weight", 0.5))),
        category=str(d.get("category", "misc")),
        description=str(d.get("description", "")),
        base_value=max(0, float(d.get("base_value", 0))),
        quality="standard",
        tool_tags=_ensure_list(d.get("tool_tags", [])),
        weapon_type=str(d.get("weapon_type", "")),
        damage_min=max(0, int(d.get("damage_min", 0))),
        damage_max=max(0, int(d.get("damage_max", 0))),
        damage_type=str(d.get("damage_type", "")),
        nutrition=max(0, float(d.get("nutrition", 0))),
        hydration=max(0, float(d.get("hydration", 0))),
        perishable=bool(d.get("perishable", False)),
        days_until_spoil=d.get("days_until_spoil"),
        clothing_slot=str(d.get("clothing_slot", "")),
        warmth=max(0, float(d.get("warmth", 0))),
        protection=max(0, min(0.5, float(d.get("protection", 0)))),
        capacity_lb=max(0, float(d.get("capacity_lb", 0))),
        stackable=bool(d.get("stackable", False)),
        durability=max(5, min(100, float(d.get("durability", 50)))),
        tags=_ensure_list(d.get("tags", [])),
        special=dict(d.get("special", {})) if isinstance(d.get("special"), dict) else {},
        creation_skill=str(d.get("creation_skill", "")),
        creation_difficulty=max(1, min(20, int(d.get("creation_difficulty", 10)))),
        source="llm",
    )


def _ensure_list(val) -> List[str]:
    if isinstance(val, list):
        return [str(v) for v in val]
    return []


# ============================================================================
#  HEURISTIC FALLBACK (no LLM available)
# ============================================================================

_WEIGHT_HINTS = {
    "log": 12, "plank": 6, "branch": 3, "timber": 15,
    "rock": 4, "stone": 3, "boulder": 20, "ore": 5,
    "stick": 0.5, "twig": 0.1, "bone": 0.5, "horn": 1,
    "rope": 1, "cord": 0.3, "string": 0.1,
    "knife": 0.5, "blade": 0.8, "axe": 3, "hammer": 2,
    "pan": 2, "pot": 3, "bucket": 2, "basket": 1,
    "shirt": 0.4, "coat": 3, "hat": 0.4, "boots": 2.5,
    "bandage": 0.1, "poultice": 0.2, "salve": 0.1,
    "torch": 1, "candle": 0.2, "lantern": 2,
}

_CAT_HINTS = {
    "knife": "weapon", "blade": "weapon", "axe": "weapon", "club": "weapon",
    "spear": "weapon", "bow": "weapon", "sword": "weapon", "hammer": "weapon",
    "pan": "tool", "shovel": "tool", "pick": "tool", "saw": "tool",
    "rope": "material", "cord": "material", "cloth": "material",
    "shirt": "clothing", "coat": "clothing", "hat": "clothing",
    "pants": "clothing", "boots": "clothing", "gloves": "clothing",
    "jerky": "food", "bread": "food", "stew": "food", "meat": "food",
    "water": "drink", "tea": "drink", "coffee": "drink", "whiskey": "drink",
    "bag": "container", "sack": "container", "pouch": "container",
    "bucket": "container", "barrel": "container", "crate": "container",
    "torch": "tool", "candle": "misc", "lantern": "tool",
}

_TOOL_TAG_HINTS = {
    "pan": ["pan"], "shovel": ["dig"], "pick": ["dig", "break_rock"],
    "axe": ["chop"], "saw": ["cut"], "hammer": ["build", "break_rock"],
    "rope": ["tie", "climb"], "torch": ["light"], "lantern": ["light"],
    "filter": ["filter_water"], "net": ["fish", "catch"],
    "needle": ["sew"], "compass": ["navigate"],
}


def _heuristic_blueprint(name: str) -> ItemBlueprint:
    """Generate a rough blueprint from name keywords when LLM unavailable."""
    low = name.lower()
    item_id = _normalize(name)

    # Weight
    weight = 0.5
    for hint, w in _WEIGHT_HINTS.items():
        if hint in low:
            weight = w
            break

    # Category
    category = "misc"
    for hint, cat in _CAT_HINTS.items():
        if hint in low:
            category = cat
            break

    # Tool tags
    tool_tags = []
    for hint, tags in _TOOL_TAG_HINTS.items():
        if hint in low:
            tool_tags.extend(tags)

    # Weapon
    weapon_type = ""
    dmg_min, dmg_max = 0, 0
    damage_type = ""
    if category == "weapon":
        weapon_type = "melee"
        dmg_min, dmg_max = 2, 8
        if any(w in low for w in ("knife", "blade", "axe")):
            damage_type = "edged"
        elif any(w in low for w in ("spear", "arrow")):
            damage_type = "piercing"
        else:
            damage_type = "blunt"

    return ItemBlueprint(
        id=item_id, name=name, weight=weight, category=category,
        description=f"A {name.lower()}.",
        base_value=round(weight * 0.5, 2),
        tool_tags=tool_tags,
        weapon_type=weapon_type, damage_min=dmg_min, damage_max=dmg_max,
        damage_type=damage_type,
        durability=50, source="llm",
    )


def _fallback_item(name: str) -> Item:
    """Absolute last resort — create a bare-minimum Item."""
    bp = _heuristic_blueprint(name)
    return Item(
        id=bp.id, name=bp.name, weight=bp.weight, category=bp.category,
        description=bp.description, base_value=bp.base_value,
        tool_tags=bp.tool_tags, weapon_type=bp.weapon_type,
        damage_min=bp.damage_min, damage_max=bp.damage_max,
        condition=bp.durability, quality="improvised",
    )


# ============================================================================
#  CONVERT BUILT-IN TEMPLATES TO BLUEPRINTS
# ============================================================================

def _template_to_blueprint(template_id: str, tdata: dict) -> ItemBlueprint:
    """Convert an ITEM_TEMPLATES entry into an ItemBlueprint."""
    extra = tdata.get("extra", {})
    return ItemBlueprint(
        id=template_id,
        name=tdata.get("name", template_id),
        weight=tdata.get("weight", 0.5),
        category=tdata.get("category", "misc"),
        description=tdata.get("description", ""),
        base_value=tdata.get("base_value", 0),
        quality=tdata.get("quality", "standard"),
        tool_tags=tdata.get("tool_tags", []),
        weapon_type=tdata.get("weapon_type", ""),
        damage_min=tdata.get("damage_min", 0),
        damage_max=tdata.get("damage_max", 0),
        nutrition=tdata.get("nutrition", 0),
        hydration=tdata.get("hydration", 0),
        perishable=tdata.get("perishable", False),
        days_until_spoil=tdata.get("days_until_spoil"),
        stackable=tdata.get("stackable", False),
        durability=tdata.get("condition", 100),
        clothing_slot=extra.get("slot", ""),
        warmth=extra.get("warmth_bonus", 0),
        tags=list(extra.get("tags", [])),
        special={k: v for k, v in extra.items()
                 if k not in ("slot", "warmth_bonus", "tags")},
        source="builtin",
    )
