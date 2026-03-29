"""
Crafting system — turn raw materials into useful items.

Recipes require specific materials in inventory + sometimes a tool.
Skill affects quality and time. Higher skill = faster, better result.

Accessed via [A] actions → "Craft" or type "craft".
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict


@dataclass
class Recipe:
    id: str
    name: str                    # display name of output
    description: str             # what you're making
    materials: List[Tuple[str, int]]   # [(item_id, quantity), ...]
    tool_required: str = ""      # tool_tag needed (e.g. "cut", "chop")
    skill: str = "survival"      # governing skill
    difficulty: int = 8          # DC for skill check
    time_minutes: int = 30       # base time
    output_id: str = ""          # item template ID to create
    output_custom: Optional[dict] = None  # custom item dict if no template
    category: str = "general"    # for menu grouping


# ── Recipes ───────────────────────────────────────────────────────────────

RECIPES: List[Recipe] = [
    # ── Leather & Hide ────────────────────────────────────────────────
    Recipe(
        id="tan_hide", name="Tanned Leather",
        description="Tan a raw hide into usable leather.",
        materials=[("raw_hide", 1), ("tallow", 1)],
        tool_required="cut", skill="survival", difficulty=8, time_minutes=60,
        output_custom={"id": "leather", "name": "Tanned Leather", "weight": 4.0,
                       "category": "material", "base_value": 3.00,
                       "description": "Worked leather. Good for bags, sheaths, repairs."},
        category="leatherwork",
    ),
    Recipe(
        id="leather_pouch", name="Leather Pouch",
        description="A small bag for carrying gold dust or supplies.",
        materials=[("raw_hide", 1)],
        tool_required="cut", skill="survival", difficulty=6, time_minutes=30,
        output_custom={"id": "leather_pouch", "name": "Leather Pouch", "weight": 0.3,
                       "category": "misc", "base_value": 1.00,
                       "description": "A hand-stitched leather pouch."},
        category="leatherwork",
    ),
    Recipe(
        id="waterskin", name="Waterskin",
        description="A hide bag for carrying water.",
        materials=[("raw_hide", 1), ("sinew", 1)],
        tool_required="cut", skill="survival", difficulty=8, time_minutes=45,
        output_custom={"id": "waterskin", "name": "Waterskin", "weight": 0.5,
                       "category": "drink", "base_value": 2.00, "hydration": 30.0,
                       "description": "A leather water bag. Holds about a quart."},
        category="leatherwork",
    ),
    Recipe(
        id="moccasins", name="Moccasins",
        description="Simple hide footwear.",
        materials=[("raw_hide", 1), ("sinew", 1)],
        tool_required="cut", skill="survival", difficulty=7, time_minutes=40,
        output_custom={"id": "moccasins", "name": "Moccasins", "weight": 0.5,
                       "category": "clothing", "base_value": 1.50,
                       "description": "Soft hide moccasins. Quiet on forest floor."},
        category="leatherwork",
    ),

    # ── Bone & Antler ─────────────────────────────────────────────────
    Recipe(
        id="bone_knife", name="Bone Knife",
        description="A crude but sharp knife carved from bone.",
        materials=[("animal_bones", 1)],
        tool_required="", skill="survival", difficulty=6, time_minutes=30,
        output_custom={"id": "bone_knife", "name": "Bone Knife", "weight": 0.3,
                       "category": "tool", "base_value": 0.25, "weapon_type": "melee",
                       "damage_min": 3, "damage_max": 8,
                       "tool_tags": ["cut", "butcher"],
                       "description": "A sharpened bone blade. Better than nothing."},
        category="bonework",
    ),
    Recipe(
        id="bone_fishhook", name="Bone Fishhooks",
        description="Carved hooks for catching fish.",
        materials=[("animal_bones", 1)],
        tool_required="cut", skill="survival", difficulty=5, time_minutes=20,
        output_custom={"id": "bone_fishhook", "name": "Bone Fishhooks", "weight": 0.05,
                       "category": "tool", "base_value": 0.15, "stackable": True,
                       "tool_tags": ["fish"],
                       "description": "Hand-carved bone hooks. Crude but effective."},
        category="bonework",
    ),
    Recipe(
        id="bone_needle", name="Bone Needle",
        description="A sewing needle for repairs and leatherwork.",
        materials=[("animal_bones", 1)],
        tool_required="cut", skill="survival", difficulty=7, time_minutes=25,
        output_custom={"id": "bone_needle", "name": "Bone Needle", "weight": 0.01,
                       "category": "tool", "base_value": 0.10,
                       "tool_tags": ["sew"],
                       "description": "A thin bone needle. Essential for hide work."},
        category="bonework",
    ),
    Recipe(
        id="antler_handle", name="Antler-Handled Knife",
        description="A proper knife with an antler grip.",
        materials=[("antlers", 1), ("animal_bones", 1)],
        tool_required="cut", skill="survival", difficulty=10, time_minutes=60,
        output_custom={"id": "antler_knife", "name": "Antler Knife", "weight": 0.4,
                       "category": "weapon", "base_value": 2.00, "weapon_type": "melee",
                       "damage_min": 5, "damage_max": 12,
                       "tool_tags": ["cut", "butcher", "skin"],
                       "description": "A sharp blade with an antler handle. Well-made."},
        category="bonework",
    ),

    # ── Woodwork ──────────────────────────────────────────────────────
    Recipe(
        id="split_planks", name="Planks (x4)",
        description="Split a log into rough planks.",
        materials=[("log", 1)],
        tool_required="chop", skill="survival", difficulty=5, time_minutes=20,
        output_id="plank",
        category="woodwork",
    ),
    Recipe(
        id="wooden_bowl", name="Wooden Bowl",
        description="Carve a bowl from a log. For eating or panning.",
        materials=[("log", 1)],
        tool_required="cut", skill="survival", difficulty=7, time_minutes=40,
        output_custom={"id": "wooden_bowl", "name": "Wooden Bowl", "weight": 0.5,
                       "category": "misc", "base_value": 0.25,
                       "description": "A rough-carved wooden bowl."},
        category="woodwork",
    ),
    Recipe(
        id="wooden_club", name="Wooden Club",
        description="A heavy stick, shaped for hitting things.",
        materials=[("log", 1)],
        tool_required="chop", skill="survival", difficulty=4, time_minutes=15,
        output_custom={"id": "wooden_club", "name": "Wooden Club", "weight": 3.0,
                       "category": "weapon", "base_value": 0.10, "weapon_type": "melee",
                       "damage_min": 4, "damage_max": 10,
                       "description": "A crude wooden club. Blunt but effective."},
        category="woodwork",
    ),
    Recipe(
        id="craft_arrows", name="Arrows (x5)",
        description="Fletch arrows from wood, feathers, and bone.",
        materials=[("log", 1), ("bird_feathers", 1), ("animal_bones", 1)],
        tool_required="cut", skill="survival", difficulty=8, time_minutes=45,
        output_id="arrow",
        category="woodwork",
    ),
    Recipe(
        id="torch", name="Torch",
        description="A stick wrapped in tallow-soaked cloth. Burns for hours.",
        materials=[("log", 1), ("tallow", 1)],
        tool_required="", skill="survival", difficulty=4, time_minutes=10,
        output_custom={"id": "torch", "name": "Torch", "weight": 1.0,
                       "category": "tool", "base_value": 0.15,
                       "tool_tags": ["light"],
                       "description": "A burning torch. Light and warmth."},
        category="woodwork",
    ),
    Recipe(
        id="snare", name="Snare Trap",
        description="A rope and stick snare for catching small game.",
        materials=[("rope_10ft", 1)],
        tool_required="cut", skill="tracking", difficulty=7, time_minutes=20,
        output_custom={"id": "snare", "name": "Snare Trap", "weight": 0.5,
                       "category": "tool", "base_value": 0.30,
                       "tool_tags": ["trap"],
                       "description": "A simple loop snare. Set it on a game trail."},
        category="trapping",
    ),

    # ── Tallow & Fat ──────────────────────────────────────────────────
    Recipe(
        id="candle", name="Tallow Candle",
        description="A simple candle for light.",
        materials=[("tallow", 1)],
        tool_required="", skill="survival", difficulty=3, time_minutes=15,
        output_custom={"id": "candle", "name": "Tallow Candle", "weight": 0.2,
                       "category": "misc", "base_value": 0.10,
                       "tool_tags": ["light"],
                       "description": "A tallow candle. Burns for several hours."},
        category="general",
    ),
    Recipe(
        id="grease", name="Axle Grease",
        description="Rendered fat for lubricating wagon wheels and tools.",
        materials=[("tallow", 2)],
        tool_required="", skill="survival", difficulty=4, time_minutes=20,
        output_custom={"id": "grease", "name": "Axle Grease", "weight": 1.0,
                       "category": "material", "base_value": 0.50,
                       "description": "Thick rendered grease. Many uses."},
        category="general",
    ),

    # ── Sinew & Rope ──────────────────────────────────────────────────
    Recipe(
        id="bowstring", name="Bowstring",
        description="Twist sinew into a strong bowstring.",
        materials=[("sinew", 2)],
        tool_required="", skill="survival", difficulty=6, time_minutes=20,
        output_custom={"id": "bowstring", "name": "Bowstring", "weight": 0.05,
                       "category": "material", "base_value": 0.50,
                       "description": "Twisted sinew cord. Strong enough for a bow."},
        category="general",
    ),
    Recipe(
        id="craft_bow", name="Hunting Bow",
        description="Shape a bow from flexible wood and string it.",
        materials=[("log", 1), ("sinew", 2)],
        tool_required="cut", skill="survival", difficulty=10, time_minutes=90,
        output_id="hunting_bow",
        category="woodwork",
    ),
]

# Index by category
RECIPE_CATEGORIES = {}
for r in RECIPES:
    RECIPE_CATEGORIES.setdefault(r.category, []).append(r)


def can_craft(recipe: Recipe, inventory: list) -> Tuple[bool, str]:
    """Check if player has materials and tools. Returns (ok, reason)."""
    # Check tool
    if recipe.tool_required:
        has_tool = any(recipe.tool_required in getattr(i, "tool_tags", [])
                       for i in inventory)
        if not has_tool:
            return False, f"Need a tool with '{recipe.tool_required}' ability."

    # Check materials
    for mat_id, qty_needed in recipe.materials:
        total = 0
        for item in inventory:
            if item.id == mat_id:
                total += getattr(item, "quantity", 1)
        if total < qty_needed:
            from src.items import ITEM_TEMPLATES
            name = ITEM_TEMPLATES.get(mat_id, {}).get("name", mat_id)
            return False, f"Need {qty_needed}x {name} (have {total})."
    return True, ""


def execute_craft(recipe: Recipe, player) -> Tuple[bool, str]:
    """Consume materials and create the output item. Returns (ok, message)."""
    import random

    ok, reason = can_craft(recipe, player.inventory)
    if not ok:
        return False, reason

    # Consume materials
    for mat_id, qty_needed in recipe.materials:
        remaining = qty_needed
        for item in list(player.inventory):
            if remaining <= 0:
                break
            if item.id != mat_id:
                continue
            avail = getattr(item, "quantity", 1)
            if getattr(item, "stackable", False) and avail > remaining:
                item.quantity -= remaining
                remaining = 0
            else:
                player.inventory.remove(item)
                remaining -= avail

    # Skill check for quality
    skill_val = player.skills.get(recipe.skill, 0)
    roll = random.randint(1, 20) + skill_val // 2
    success = roll >= recipe.difficulty

    if not success:
        # Partial failure — materials consumed but poor result
        player.gain_skill_xp(recipe.skill, 2.0)
        return False, (f"You try to craft {recipe.name} but the result is unusable. "
                       f"Materials wasted. (Skill check failed)")

    # Create output
    from src.items import make_item, Item
    if recipe.output_id:
        item = make_item(recipe.output_id)
        # Planks and arrows come in multiples
        if recipe.id == "split_planks":
            item.quantity = 4
        elif recipe.id == "craft_arrows":
            item.quantity = 5
    elif recipe.output_custom:
        d = dict(recipe.output_custom)
        item = Item(**{k: v for k, v in d.items() if k in Item.__dataclass_fields__})
    else:
        return False, "Recipe has no output defined."

    player.inventory.append(item)
    player.gain_skill_xp(recipe.skill, 3.0 + recipe.difficulty * 0.5)

    return True, f"Crafted: {item.name}."
