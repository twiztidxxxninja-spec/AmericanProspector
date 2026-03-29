"""
Crafting system — turn raw materials into useful items.

Every recipe output has a gameplay purpose. No decorative items.
Accessed via [A] actions → "Craft" or type "craft".
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict


@dataclass
class Recipe:
    id: str
    name: str
    description: str
    materials: List[Tuple[str, int]]   # [(item_id, quantity), ...]
    tool_required: str = ""
    skill: str = "survival"
    difficulty: int = 8
    time_minutes: int = 30
    output_id: str = ""
    output_qty: int = 1
    output_custom: Optional[dict] = None
    category: str = "general"


RECIPES: List[Recipe] = [
    # ── Leatherwork (raw_hide → leather → clothing/gear) ─────────────
    Recipe(
        id="tan_hide", name="Tanned Leather",
        description="Brain-tan a raw hide into soft, workable leather.",
        materials=[("raw_hide", 1), ("brain", 1)],
        tool_required="cut", skill="survival", difficulty=8, time_minutes=60,
        output_custom={"id": "leather", "name": "Tanned Leather", "weight": 4.0,
                       "category": "material", "base_value": 3.00,
                       "description": "Worked leather. Craft into clothing, bags, or sheaths."},
        category="leatherwork",
    ),
    Recipe(
        id="leather_jacket", name="Leather Jacket",
        description="A heavy leather coat. Warmth and some protection.",
        materials=[("leather", 2), ("sinew", 1)],
        tool_required="cut", skill="survival", difficulty=10, time_minutes=90,
        output_custom={"id": "leather_jacket", "name": "Leather Jacket", "weight": 4.0,
                       "category": "clothing", "base_value": 8.00,
                       "extra": {"warmth": 15, "armor": 2, "slot": "torso"},
                       "description": "A hand-sewn leather jacket. Warm, tough."},
        category="leatherwork",
    ),
    Recipe(
        id="leather_pants", name="Leather Trousers",
        description="Durable hide pants. Protection from brush and cold.",
        materials=[("leather", 2), ("sinew", 1)],
        tool_required="cut", skill="survival", difficulty=9, time_minutes=80,
        output_custom={"id": "leather_pants", "name": "Leather Trousers", "weight": 3.0,
                       "category": "clothing", "base_value": 6.00,
                       "extra": {"warmth": 12, "armor": 1, "slot": "legs"},
                       "description": "Heavy leather trousers. Thorn-proof."},
        category="leatherwork",
    ),
    Recipe(
        id="leather_hat", name="Leather Hat",
        description="A wide-brimmed leather hat. Sun and rain protection.",
        materials=[("leather", 1)],
        tool_required="cut", skill="survival", difficulty=6, time_minutes=30,
        output_custom={"id": "leather_hat", "name": "Leather Hat", "weight": 0.5,
                       "category": "clothing", "base_value": 2.00,
                       "extra": {"warmth": 5, "slot": "head"},
                       "description": "A wide-brimmed leather hat."},
        category="leatherwork",
    ),
    Recipe(
        id="leather_gloves", name="Leather Gloves",
        description="Protects hands while working. Reduces blisters.",
        materials=[("leather", 1)],
        tool_required="cut", skill="survival", difficulty=7, time_minutes=30,
        output_custom={"id": "leather_gloves", "name": "Leather Gloves", "weight": 0.3,
                       "category": "clothing", "base_value": 1.50,
                       "extra": {"warmth": 5, "armor": 1, "slot": "hands"},
                       "description": "Work gloves. Protects hands from blisters and cuts."},
        category="leatherwork",
    ),
    Recipe(
        id="moccasins", name="Moccasins",
        description="Soft hide footwear. Quiet movement.",
        materials=[("raw_hide", 1), ("sinew", 1)],
        tool_required="cut", skill="survival", difficulty=7, time_minutes=40,
        output_custom={"id": "moccasins", "name": "Moccasins", "weight": 0.5,
                       "category": "clothing", "base_value": 1.50,
                       "extra": {"warmth": 5, "slot": "feet"},
                       "description": "Soft hide moccasins. Quiet on forest floor."},
        category="leatherwork",
    ),
    Recipe(
        id="waterskin", name="Waterskin",
        description="Carry water without a canteen. Holds a quart.",
        materials=[("raw_hide", 1), ("sinew", 1)],
        tool_required="cut", skill="survival", difficulty=8, time_minutes=45,
        output_custom={"id": "waterskin", "name": "Waterskin", "weight": 0.5,
                       "category": "drink", "base_value": 2.00, "hydration": 30.0,
                       "description": "A leather water bag. Refill at any stream."},
        category="leatherwork",
    ),
    Recipe(
        id="knife_sheath", name="Knife Sheath",
        description="A leather sheath. Protects blade and your leg.",
        materials=[("leather", 1)],
        tool_required="cut", skill="survival", difficulty=5, time_minutes=20,
        output_custom={"id": "knife_sheath", "name": "Knife Sheath", "weight": 0.2,
                       "category": "misc", "base_value": 1.00,
                       "description": "Belt sheath for a knife. Keeps the edge safe."},
        category="leatherwork",
    ),

    # ── Bonework ──────────────────────────────────────────────────────
    Recipe(
        id="bone_knife", name="Bone Knife",
        description="A crude blade. Emergency tool when you have no metal.",
        materials=[("animal_bones", 1)],
        skill="survival", difficulty=6, time_minutes=30,
        output_custom={"id": "bone_knife", "name": "Bone Knife", "weight": 0.3,
                       "category": "tool", "base_value": 0.25, "weapon_type": "melee",
                       "damage_min": 3, "damage_max": 8,
                       "tool_tags": ["cut", "butcher"],
                       "description": "A sharpened bone blade. Better than nothing."},
        category="bonework",
    ),
    Recipe(
        id="bone_fishhook", name="Bone Fishhooks",
        description="For catching fish. Essential near water.",
        materials=[("animal_bones", 1)],
        tool_required="cut", skill="survival", difficulty=5, time_minutes=20,
        output_custom={"id": "bone_fishhook", "name": "Bone Fishhooks", "weight": 0.05,
                       "category": "tool", "base_value": 0.15, "stackable": True,
                       "tool_tags": ["fish"],
                       "description": "Hand-carved bone hooks for fishing."},
        category="bonework",
    ),
    Recipe(
        id="bone_needle", name="Bone Needle",
        description="Required for sewing leather into clothing.",
        materials=[("animal_bones", 1)],
        tool_required="cut", skill="survival", difficulty=7, time_minutes=25,
        output_custom={"id": "bone_needle", "name": "Bone Needle", "weight": 0.01,
                       "category": "tool", "base_value": 0.10,
                       "tool_tags": ["sew"],
                       "description": "A thin bone needle. Needed for leatherwork."},
        category="bonework",
    ),
    Recipe(
        id="antler_knife", name="Antler-Handled Knife",
        description="A quality knife with antler grip. Better than bone.",
        materials=[("antlers", 1), ("animal_bones", 1)],
        tool_required="cut", skill="survival", difficulty=10, time_minutes=60,
        output_custom={"id": "antler_knife", "name": "Antler Knife", "weight": 0.4,
                       "category": "weapon", "base_value": 2.00, "weapon_type": "melee",
                       "damage_min": 5, "damage_max": 12,
                       "tool_tags": ["cut", "butcher", "skin"],
                       "description": "A sharp blade with an antler handle."},
        category="bonework",
    ),

    # ── Woodwork ──────────────────────────────────────────────────────
    Recipe(
        id="split_planks", name="Planks (x4)",
        description="Split a log for construction. Required for sluice boxes, buildings.",
        materials=[("log", 1)],
        tool_required="chop", skill="survival", difficulty=5, time_minutes=20,
        output_id="plank", output_qty=4,
        category="woodwork",
    ),
    Recipe(
        id="wooden_club", name="Wooden Club",
        description="A heavy blunt weapon. No tools needed.",
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
        description="Ammunition for a hunting bow.",
        materials=[("log", 1), ("bird_feathers", 1), ("animal_bones", 1)],
        tool_required="cut", skill="survival", difficulty=8, time_minutes=45,
        output_id="arrow", output_qty=5,
        category="woodwork",
    ),
    Recipe(
        id="torch", name="Torch",
        description="Light source. Burns for hours. Scares animals.",
        materials=[("log", 1), ("tallow", 1)],
        skill="survival", difficulty=4, time_minutes=10,
        output_custom={"id": "torch", "name": "Torch", "weight": 1.0,
                       "category": "tool", "base_value": 0.15,
                       "tool_tags": ["light"],
                       "description": "A burning torch. Light, warmth, scares predators."},
        category="woodwork",
    ),
    Recipe(
        id="craft_bow", name="Hunting Bow",
        description="Silent ranged weapon. Uses arrows.",
        materials=[("log", 1), ("sinew", 2)],
        tool_required="cut", skill="survival", difficulty=10, time_minutes=90,
        output_id="hunting_bow",
        category="woodwork",
    ),

    # ── Trapping & Rope ───────────────────────────────────────────────
    Recipe(
        id="snare", name="Snare Trap",
        description="Catches small game while you do other things.",
        materials=[("rope_10ft", 1)],
        tool_required="cut", skill="tracking", difficulty=7, time_minutes=20,
        output_custom={"id": "snare", "name": "Snare Trap", "weight": 0.5,
                       "category": "tool", "base_value": 0.30,
                       "tool_tags": ["trap"],
                       "description": "A loop snare. Set on a game trail and wait."},
        category="trapping",
    ),
    Recipe(
        id="bowstring", name="Bowstring",
        description="Required to craft a hunting bow.",
        materials=[("sinew", 2)],
        skill="survival", difficulty=6, time_minutes=20,
        output_custom={"id": "bowstring", "name": "Bowstring", "weight": 0.05,
                       "category": "material", "base_value": 0.50,
                       "description": "Twisted sinew cord. String a bow with this."},
        category="general",
    ),
    Recipe(
        id="candle", name="Tallow Candle",
        description="Light source. Cheaper than a torch, lasts longer.",
        materials=[("tallow", 1)],
        skill="survival", difficulty=3, time_minutes=15,
        output_custom={"id": "candle", "name": "Tallow Candle", "weight": 0.2,
                       "category": "tool", "base_value": 0.10,
                       "tool_tags": ["light"],
                       "description": "A tallow candle. Burns for hours."},
        category="general",
    ),
    Recipe(
        id="bandage", name="Cloth Bandage",
        description="Tear cloth into bandages for treating wounds.",
        materials=[("raw_hide", 1)],
        skill="firstAid", difficulty=4, time_minutes=10,
        output_custom={"id": "bandage", "name": "Bandage", "weight": 0.1,
                       "category": "tool", "base_value": 0.20, "stackable": True,
                       "tool_tags": ["medical"],
                       "description": "A strip of clean cloth for bandaging wounds."},
        category="general",
    ),
]

# Index by category
RECIPE_CATEGORIES = {}
for r in RECIPES:
    RECIPE_CATEGORIES.setdefault(r.category, []).append(r)


def can_craft(recipe: Recipe, inventory: list) -> Tuple[bool, str]:
    """Check if player has materials and tools."""
    if recipe.tool_required:
        has_tool = any(recipe.tool_required in getattr(i, "tool_tags", [])
                       for i in inventory)
        if not has_tool:
            return False, f"Need '{recipe.tool_required}' tool"

    for mat_id, qty_needed in recipe.materials:
        total = 0
        for item in inventory:
            if item.id == mat_id:
                total += getattr(item, "quantity", 1)
        if total < qty_needed:
            from src.items import ITEM_TEMPLATES
            name = ITEM_TEMPLATES.get(mat_id, {}).get("name", mat_id)
            return False, f"{qty_needed}x {name}"
    return True, ""


def execute_craft(recipe: Recipe, player) -> Tuple[bool, str]:
    """Consume materials and create output."""
    import random

    ok, reason = can_craft(recipe, player.inventory)
    if not ok:
        return False, f"Can't craft: need {reason}."

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

    # Skill check
    skill_val = player.skills.get(recipe.skill, 0)
    roll = random.randint(1, 20) + skill_val // 2
    if roll < recipe.difficulty:
        player.gain_skill_xp(recipe.skill, 2.0)
        return False, (f"You try to make {recipe.name} but ruin it. "
                       f"Materials wasted.")

    # Create output
    from src.items import make_item, Item
    if recipe.output_id:
        item = make_item(recipe.output_id)
        if recipe.output_qty > 1:
            item.quantity = recipe.output_qty
    elif recipe.output_custom:
        d = dict(recipe.output_custom)
        item = Item(**{k: v for k, v in d.items() if k in Item.__dataclass_fields__})
    else:
        return False, "Recipe error."

    player.inventory.append(item)
    player.gain_skill_xp(recipe.skill, 3.0 + recipe.difficulty * 0.5)
    return True, f"Crafted: {item.display_name()}."
