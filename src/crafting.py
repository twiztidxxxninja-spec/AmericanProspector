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
    # ── Food Preservation ──────────────────────────────────────────────
    Recipe(
        id="smoke_meat", name="Smoked Meat",
        description="Hang fresh meat over a smoky fire. Takes hours but keeps for weeks. "
                    "Requires a campfire or drying rack nearby.",
        materials=[("fresh_venison", 1)],
        skill="survival", difficulty=6, time_minutes=180,
        output_id="smoked_meat", output_qty=2,
        category="food",
    ),
    Recipe(
        id="smoke_fish", name="Smoked Fish",
        description="Hang fish over a smoky fire. Preserves for weeks.",
        materials=[("fresh_fish", 2)],
        skill="survival", difficulty=5, time_minutes=120,
        output_id="smoked_meat", output_qty=2,
        category="food",
    ),
    Recipe(
        id="make_jerky", name="Jerky",
        description="Cut meat thin, salt it, dry it on a rack. Lasts months on the trail. "
                    "Requires salt and a drying rack or campfire.",
        materials=[("fresh_venison", 1), ("salt", 1)],
        skill="survival", difficulty=7, time_minutes=240,
        output_id="jerky", output_qty=3,
        category="food",
    ),
    Recipe(
        id="make_pemmican", name="Pemmican",
        description="Pound dried jerky, mix with rendered tallow. "
                    "Dense trail food. Keeps for months.",
        materials=[("jerky", 2), ("tallow", 1)],
        skill="survival", difficulty=7, time_minutes=120,
        output_id="pemican", output_qty=3,
        category="food",
    ),
    Recipe(
        id="make_berry_pemmican", name="Berry Pemmican",
        description="Pemmican with wild berries mixed in. Tastes better, "
                    "more nutritious, and the berries help it keep even longer.",
        materials=[("jerky", 2), ("tallow", 1), ("wild_berries", 1)],
        skill="survival", difficulty=8, time_minutes=120,
        output_custom={"id": "pemican_berry", "name": "Berry Pemmican",
                       "weight": 0.2, "category": "food", "nutrition": 40.0,
                       "description": "Pemmican with dried berries. "
                                      "Richer flavor, more energy, keeps longer.",
                       "base_value": 0.25, "stackable": True,
                       "perishable": True, "days_until_spoil": 365},
        output_qty=3,
        category="food",
    ),
    Recipe(
        id="render_tallow", name="Render Tallow",
        description="Boil animal fat over a fire to render it into clean tallow. "
                    "Used for candles, pemmican, waterproofing, and soap.",
        materials=[("bear_fat", 1)],
        skill="survival", difficulty=4, time_minutes=60,
        output_id="tallow", output_qty=2,
        category="food",
    ),

    # ── Cooking (requires campfire nearby) ──────────────────────────────
    Recipe(
        id="cook_meat", name="Cooked Meat",
        description="Cook fresh meat over a fire. Edible and nourishing.",
        materials=[("fresh_venison", 1)],
        skill="survival", difficulty=3, time_minutes=15,
        output_custom={"id": "cooked_meat", "name": "Cooked Meat", "weight": 0.8,
                       "category": "food", "nutrition": 35.0, "base_value": 0.10,
                       "perishable": True, "days_until_spoil": 3,
                       "description": "Well-cooked venison. Filling."},
        category="food",
    ),
    Recipe(
        id="cook_fish", name="Cooked Fish",
        description="Pan-fry or roast fish. Quick meal.",
        materials=[("fresh_fish", 1)],
        skill="survival", difficulty=2, time_minutes=10,
        output_custom={"id": "cooked_fish", "name": "Cooked Fish", "weight": 0.4,
                       "category": "food", "nutrition": 22.0, "base_value": 0.08,
                       "perishable": True, "days_until_spoil": 2,
                       "description": "Roasted fish. Simple but good."},
        category="food",
    ),
    Recipe(
        id="cook_stew", name="Stew",
        description="A hot stew from meat, beans, and whatever else you have.",
        materials=[("fresh_venison", 1), ("dried_beans", 1)],
        skill="survival", difficulty=4, time_minutes=60,
        output_custom={"id": "stew", "name": "Hot Stew", "weight": 0.8,
                       "category": "food", "nutrition": 50.0, "base_value": 0.15,
                       "hydration": 10.0, "perishable": True, "days_until_spoil": 1,
                       "description": "Thick stew. Warms you from the inside."},
        output_qty=2,
        category="food",
    ),
    Recipe(
        id="make_hardtack", name="Hardtack",
        description="Flour and water baked into rock-hard biscuits. Lasts forever.",
        materials=[("flour", 2)],
        skill="survival", difficulty=3, time_minutes=60,
        output_id="hardtack", output_qty=6,
        category="food",
    ),
    Recipe(
        id="dry_fish", name="Dried Fish",
        description="Salt and dry fish on a rack. Trail food.",
        materials=[("fresh_fish", 2), ("salt", 1)],
        skill="survival", difficulty=5, time_minutes=180,
        output_custom={"id": "dried_fish", "name": "Dried Fish", "weight": 0.3,
                       "category": "food", "nutrition": 18.0, "base_value": 0.10,
                       "stackable": True, "perishable": True, "days_until_spoil": 45,
                       "description": "Salt-dried fish. Keeps well on the trail."},
        output_qty=3,
        category="food",
    ),
    Recipe(
        id="make_whiskey_still", name="Distill Whiskey",
        description="Distill grain mash into whiskey. Requires a still or copper pot.",
        materials=[("flour", 3)],
        skill="chemistry", difficulty=10, time_minutes=480,
        output_id="whiskey", output_qty=2,
        category="food",
    ),

    # ── Practical tools (things players will try to make) ────────────
    Recipe(
        id="stone_knife", name="Stone Knife",
        description="Knap a sharp edge from stone. The most basic cutting tool.",
        materials=[("stone", 2)],
        skill="survival", difficulty=6, time_minutes=30,
        output_custom={"id": "stone_knife", "name": "Stone Knife", "weight": 0.5,
                       "category": "tool", "base_value": 0.10, "weapon_type": "melee",
                       "damage_min": 2, "damage_max": 6,
                       "tool_tags": ["cut", "butcher"],
                       "description": "A knapped stone blade. Crude but functional."},
        category="general",
    ),
    Recipe(
        id="stone_axe", name="Stone Axe",
        description="Lash a sharp stone to a handle. Chops wood slowly.",
        materials=[("stone", 1), ("log", 1), ("cordage", 1)],
        skill="survival", difficulty=7, time_minutes=45,
        output_custom={"id": "stone_axe", "name": "Stone Axe", "weight": 3.0,
                       "category": "tool", "base_value": 0.25, "weapon_type": "melee",
                       "damage_min": 5, "damage_max": 14,
                       "tool_tags": ["chop"],
                       "description": "A crude stone axe. Gets the job done, barely."},
        category="general",
    ),
    Recipe(
        id="make_rope", name="Rope (from rawhide)",
        description="Cut rawhide into strips and braid into rope.",
        materials=[("raw_hide", 1)],
        tool_required="cut", skill="survival", difficulty=5, time_minutes=30,
        output_id="rope_10ft", output_qty=2,
        category="general",
    ),
    Recipe(
        id="make_fishing_line", name="Fishing Line & Hook",
        description="Twist sinew into line, bend bone into a hook.",
        materials=[("sinew", 1), ("animal_bones", 1)],
        tool_required="cut", skill="survival", difficulty=6, time_minutes=25,
        output_id="fishing_line",
        category="general",
    ),
    Recipe(
        id="make_canvas_tent", name="Canvas Tent",
        description="Sew canvas into a simple tent. Shelter from rain and wind.",
        materials=[("canvas", 3), ("rope_10ft", 2), ("log", 2)],
        skill="survival", difficulty=8, time_minutes=120,
        output_custom={"id": "canvas_tent", "name": "Canvas Tent", "weight": 8.0,
                       "category": "misc", "base_value": 5.00,
                       "extra": {"shelter": True, "warmth_bonus": 15},
                       "description": "A canvas tent. Basic shelter from the elements."},
        category="general",
    ),
    Recipe(
        id="make_bedroll", name="Bedroll",
        description="A bedroll from leather and blanket material. Sleep anywhere.",
        materials=[("leather", 2), ("raw_hide", 1)],
        tool_required="cut", skill="survival", difficulty=6, time_minutes=60,
        output_id="bedroll",
        category="general",
    ),
    Recipe(
        id="make_travois", name="Travois",
        description="Two poles and a hide platform. Drag heavy loads without a mule.",
        materials=[("log", 2), ("raw_hide", 1), ("rope_10ft", 1)],
        skill="survival", difficulty=6, time_minutes=45,
        output_custom={"id": "travois", "name": "Travois", "weight": 8.0,
                       "category": "tool", "base_value": 2.00,
                       "extra": {"carry_bonus_lb": 100},
                       "description": "A drag sled. Haul 100 extra pounds behind you."},
        category="general",
    ),
    Recipe(
        id="make_snowshoes", name="Snowshoes",
        description="Bent wood frame with rawhide webbing. Walk on deep snow.",
        materials=[("log", 1), ("raw_hide", 1), ("sinew", 1)],
        tool_required="cut", skill="survival", difficulty=8, time_minutes=90,
        output_custom={"id": "snowshoes", "name": "Snowshoes", "weight": 2.0,
                       "category": "clothing", "base_value": 3.00,
                       "extra": {"snow_speed": 0.5, "slot": "feet"},
                       "description": "Snowshoes. Walk on snow without sinking."},
        category="general",
    ),
    Recipe(
        id="make_stretcher", name="Stretcher/Litter",
        description="Carry an injured person. Or a lot of gear.",
        materials=[("log", 2), ("canvas", 1)],
        skill="survival", difficulty=5, time_minutes=30,
        output_custom={"id": "stretcher", "name": "Stretcher", "weight": 6.0,
                       "category": "tool", "base_value": 1.00,
                       "extra": {"carry_bonus_lb": 80},
                       "description": "A canvas stretcher. Carry the injured or extra gear."},
        category="general",
    ),
    Recipe(
        id="make_bucket", name="Wooden Bucket",
        description="A cooper's bucket from planks. Haul water.",
        materials=[("plank", 3), ("rope_10ft", 1)],
        skill="engineering", difficulty=7, time_minutes=60,
        output_custom={"id": "bucket", "name": "Wooden Bucket", "weight": 2.0,
                       "category": "tool", "base_value": 0.50,
                       "tool_tags": ["haul_water"],
                       "description": "A wooden bucket. Haul water from streams."},
        category="general",
    ),

    # ── Medical ──────────────────────────────────────────────────────
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

    # ── Storage & Carrying ──────────────────────────────────────────
    Recipe(
        id="make_satchel", name="Leather Satchel",
        description="A shoulder bag from leather. Carry documents and small items.",
        materials=[("leather", 2), ("sinew", 1)],
        tool_required="cut", skill="survival", difficulty=7, time_minutes=60,
        output_id="leather_satchel",
        category="leatherwork",
    ),
    Recipe(
        id="make_rucksack", name="Rucksack",
        description="A canvas and leather pack with shoulder straps. "
                    "The standard prospector's carrying solution.",
        materials=[("canvas", 2), ("leather", 1), ("rope_10ft", 1)],
        tool_required="cut", skill="survival", difficulty=8, time_minutes=90,
        output_id="rucksack",
        category="leatherwork",
    ),
    Recipe(
        id="make_belt_pouch", name="Belt Pouch",
        description="A small belt pouch for gold dust and ammunition.",
        materials=[("leather", 1)],
        tool_required="cut", skill="survival", difficulty=5, time_minutes=20,
        output_id="belt_pouch",
        category="leatherwork",
    ),
    Recipe(
        id="make_ore_sack", name="Ore Sack",
        description="A heavy sack for hauling rock samples and ore.",
        materials=[("canvas", 1)],
        skill="survival", difficulty=3, time_minutes=15,
        output_id="ore_sack",
        category="general",
    ),

    Recipe(
        id="splint", name="Splint",
        description="Immobilize a broken bone with sticks and cloth.",
        materials=[("log", 1)],
        tool_required="cut", skill="firstAid", difficulty=6, time_minutes=15,
        output_custom={"id": "splint", "name": "Splint", "weight": 0.3,
                       "category": "tool", "base_value": 0.15, "stackable": True,
                       "tool_tags": ["medical", "set_bone"],
                       "description": "A wooden splint. Immobilizes fractures."},
        category="general",
    ),
    Recipe(
        id="poultice", name="Herbal Poultice",
        description="Mash herbs and mud into a wound dressing. Fights infection.",
        materials=[("wild_berries", 1)],
        skill="firstAid", difficulty=6, time_minutes=20,
        output_custom={"id": "poultice", "name": "Herbal Poultice", "weight": 0.2,
                       "category": "tool", "base_value": 0.25, "stackable": True,
                       "tool_tags": ["medical", "poultice"],
                       "description": "A damp herbal pack. Reduces infection."},
        category="general",
    ),
    Recipe(
        id="willow_tea", name="Willow Bark Tea",
        description="Brew willow bark into a pain-killing tea. Frontier aspirin.",
        materials=[("log", 1)],
        skill="firstAid", difficulty=4, time_minutes=15,
        output_custom={"id": "willow_tea", "name": "Willow Bark Tea", "weight": 0.3,
                       "category": "drink", "base_value": 0.10, "hydration": 10.0,
                       "extra": {"pain_relief": 20},
                       "description": "Bitter tea. Dulls pain for hours."},
        category="general",
    ),
    Recipe(
        id="tourniquet", name="Tourniquet",
        description="A tight band to stop severe bleeding. Emergency use only.",
        materials=[("rope_10ft", 1)],
        tool_required="cut", skill="firstAid", difficulty=5, time_minutes=5,
        output_custom={"id": "tourniquet", "name": "Tourniquet", "weight": 0.2,
                       "category": "tool", "base_value": 0.20, "stackable": True,
                       "tool_tags": ["medical", "tourniquet"],
                       "description": "Emergency tourniquet. Stops bleeding but risks the limb."},
        category="general",
    ),

    # ── Material processing ──────────────────────────────────────────
    Recipe(
        id="make_soap", name="Lye Soap",
        description="Mix lye with tallow to make soap. Cleans wounds, trades well.",
        materials=[("lye", 1), ("tallow", 1)],
        skill="survival", difficulty=5, time_minutes=45,
        output_custom={"id": "soap", "name": "Lye Soap", "weight": 0.3,
                       "category": "misc", "base_value": 0.50, "stackable": True,
                       "description": "Hard lye soap. Cleans everything. Trades well."},
        output_qty=3,
        category="general",
    ),
    Recipe(
        id="make_nails", name="Nails (from iron)",
        description="Hammer iron into nails. Required for construction.",
        materials=[("iron_bar", 1)],
        skill="engineering", difficulty=8, time_minutes=60,
        output_id="nails", output_qty=10,
        category="general",
    ),
    Recipe(
        id="make_rawhide_rope", name="Rawhide Lashing",
        description="Cut raw hide into strips for tying, lashing, and binding.",
        materials=[("raw_hide", 1)],
        tool_required="cut", skill="survival", difficulty=3, time_minutes=15,
        output_id="cordage", output_qty=4,
        category="general",
    ),

    # ── Crafting intermediates ────────────────────────────────────────
    Recipe(
        id="make_charcoal", name="Charcoal",
        description="Burn wood into charcoal. Used for smelting and filtration.",
        materials=[("log", 1)],
        skill="survival", difficulty=4, time_minutes=30,
        output_id="charcoal", output_qty=3,
        category="general",
    ),
    Recipe(
        id="make_lye", name="Lye",
        description="Mix wood ash with water to make lye. Soap, hide processing.",
        materials=[("charcoal", 1)],
        skill="survival", difficulty=5, time_minutes=20,
        output_id="lye", output_qty=2,
        category="general",
    ),
    Recipe(
        id="make_cordage", name="Cordage",
        description="Twist plant fiber into usable rope. Free materials from grass.",
        materials=[],  # no material cost — gather from surroundings
        skill="survival", difficulty=3, time_minutes=15,
        output_id="cordage", output_qty=2,
        category="general",
    ),

    # ── Survival crafting ─────────────────────────────────────────────
    Recipe(
        id="salt_meat", name="Salt Preserved Meat",
        description="Preserve meat with salt. Triples time before spoiling.",
        materials=[("salt", 1)],  # player picks meat from inventory during craft
        skill="survival", difficulty=4, time_minutes=15,
        output_custom={"id": "salted_meat", "name": "Salted Meat", "weight": 1.0,
                       "category": "food", "base_value": 0.80,
                       "nutrition": 35.0, "perishable": True,
                       "days_until_spoil": 30,
                       "description": "Salt-preserved meat. Lasts weeks."},
        category="general",
    ),
    Recipe(
        id="brew_coffee", name="Brew Coffee",
        description="Brew coffee at a fire. Restores fatigue without sleeping.",
        materials=[("coffee_beans", 1)],
        tool_required="brew", skill="survival", difficulty=3, time_minutes=10,
        output_custom={"id": "coffee", "name": "Hot Coffee", "weight": 0.3,
                       "category": "drink", "base_value": 0.20,
                       "hydration": 10.0,
                       "extra": {"fatigue_restore": 20},
                       "description": "Black coffee. Bitter but it wakes you up."},
        category="general",
    ),
    Recipe(
        id="make_bear_trap", name="Bear Trap",
        description="Forge a jaw trap from iron. Immobilizes anything that steps on it.",
        materials=[("iron_bar", 1), ("log", 1)],
        tool_required="chop", skill="engineering", difficulty=12, time_minutes=120,
        output_id="bear_trap",
        category="trapping",
    ),
    # ── Trapping gear ─────────────────────────────────────────────
    Recipe(
        id="deadfall", name="Deadfall Trap",
        description="A weighted log trap. Kills medium game cleanly.",
        materials=[("log", 1), ("cordage", 1)],
        tool_required="cut", skill="trapping", difficulty=6, time_minutes=30,
        output_id="deadfall_trap",
        category="trapping",
    ),
    Recipe(
        id="pelt_frame", name="Pelt Stretching Frame",
        description="For drying raw pelts. Place on ground, load pelt, wait 24h.",
        materials=[("log", 2), ("cordage", 1)],
        tool_required="cut", skill="furriery", difficulty=5, time_minutes=30,
        output_id="pelt_frame",
        category="trapping",
    ),

    # ── Fur clothing (requires stretched or raw pelts) ────────────
    Recipe(
        id="fur_cap", name="Fur Cap",
        description="A warm cap made from small pelts. Coonskin or fox.",
        materials=[("raccoon_pelt", 2)],
        tool_required="cut", skill="furriery", difficulty=6, time_minutes=45,
        output_custom={"id": "fur_cap", "name": "Fur Cap", "weight": 0.5,
                       "category": "clothing", "base_value": 4.00,
                       "extra": {"warmth": 20, "slot": "head"},
                       "description": "A raccoon fur cap. Warm as hell."},
        category="furwork",
    ),
    Recipe(
        id="fox_fur_cap", name="Fox Fur Cap",
        description="A handsome fox fur hat.",
        materials=[("fox_pelt", 2)],
        tool_required="cut", skill="furriery", difficulty=7, time_minutes=50,
        output_custom={"id": "fox_fur_cap", "name": "Fox Fur Cap", "weight": 0.5,
                       "category": "clothing", "base_value": 5.00,
                       "extra": {"warmth": 22, "slot": "head"},
                       "description": "A red fox fur cap. Looks sharp."},
        category="furwork",
    ),
    Recipe(
        id="beaver_felt_hat", name="Beaver Felt Hat",
        description="Process beaver fur into felt for a premium hat.",
        materials=[("beaver_pelt", 2)],
        tool_required="cut", skill="furriery", difficulty=9, time_minutes=120,
        output_custom={"id": "beaver_hat", "name": "Beaver Felt Hat", "weight": 0.4,
                       "category": "clothing", "base_value": 10.00,
                       "extra": {"warmth": 15, "slot": "head"},
                       "description": "A beaver felt hat. The mark of a gentleman."},
        category="furwork",
    ),
    Recipe(
        id="fur_coat_wolf", name="Wolf Fur Coat",
        description="A heavy coat from wolf pelts. Extreme cold protection.",
        materials=[("wolf_pelt", 4)],
        tool_required="cut", skill="furriery", difficulty=10, time_minutes=180,
        output_custom={"id": "wolf_coat", "name": "Wolf Fur Coat", "weight": 8.0,
                       "category": "clothing", "base_value": 25.00,
                       "extra": {"warmth": 35, "armor": 2, "slot": "torso"},
                       "description": "A massive wolf fur coat. Nothing stops the cold."},
        category="furwork",
    ),
    Recipe(
        id="fur_coat_bear", name="Bear Fur Coat",
        description="A bear hide coat. Impressive and warm.",
        materials=[("bear_pelt", 2)],
        tool_required="cut", skill="furriery", difficulty=10, time_minutes=200,
        output_custom={"id": "bear_coat", "name": "Bear Fur Coat", "weight": 12.0,
                       "category": "clothing", "base_value": 30.00,
                       "extra": {"warmth": 40, "armor": 3, "slot": "torso"},
                       "description": "A grizzly bear coat. You look terrifying."},
        category="furwork",
    ),
    Recipe(
        id="buffalo_robe_coat", name="Buffalo Robe",
        description="A massive buffalo hide worn as a cloak.",
        materials=[("buffalo_robe", 1)],
        tool_required="cut", skill="furriery", difficulty=8, time_minutes=120,
        output_custom={"id": "buffalo_robe_coat", "name": "Buffalo Robe", "weight": 15.0,
                       "category": "clothing", "base_value": 20.00,
                       "extra": {"warmth": 45, "armor": 2, "slot": "torso"},
                       "description": "A buffalo robe. Warmest garment on the frontier."},
        category="furwork",
    ),
    Recipe(
        id="fur_gloves_mink", name="Mink Fur Gloves",
        description="Luxurious mink-lined gloves.",
        materials=[("mink_pelt", 2)],
        tool_required="cut", skill="furriery", difficulty=7, time_minutes=40,
        output_custom={"id": "mink_gloves", "name": "Mink Fur Gloves", "weight": 0.3,
                       "category": "clothing", "base_value": 8.00,
                       "extra": {"warmth": 18, "slot": "hands"},
                       "description": "Mink-lined gloves. Warm and luxurious."},
        category="furwork",
    ),
    Recipe(
        id="fur_gloves_beaver", name="Beaver Fur Gloves",
        description="Waterproof beaver fur gloves.",
        materials=[("beaver_pelt", 1)],
        tool_required="cut", skill="furriery", difficulty=6, time_minutes=35,
        output_custom={"id": "beaver_gloves", "name": "Beaver Fur Gloves", "weight": 0.3,
                       "category": "clothing", "base_value": 5.00,
                       "extra": {"warmth": 15, "slot": "hands"},
                       "description": "Beaver fur gloves. Waterproof."},
        category="furwork",
    ),
    Recipe(
        id="fur_boots", name="Fur-Lined Boots",
        description="Boots lined with rabbit or muskrat fur.",
        materials=[("muskrat_pelt", 2), ("leather", 1)],
        tool_required="cut", skill="furriery", difficulty=8, time_minutes=60,
        output_custom={"id": "fur_boots", "name": "Fur-Lined Boots", "weight": 2.0,
                       "category": "clothing", "base_value": 6.00,
                       "extra": {"warmth": 20, "slot": "feet"},
                       "description": "Warm fur-lined boots. Feet stay dry."},
        category="furwork",
    ),
    Recipe(
        id="fur_vest", name="Fur Vest",
        description="A vest from smaller pelts. Warmth without bulk.",
        materials=[("bobcat_pelt", 2)],
        tool_required="cut", skill="furriery", difficulty=7, time_minutes=60,
        output_custom={"id": "fur_vest", "name": "Fur Vest", "weight": 2.0,
                       "category": "clothing", "base_value": 8.00,
                       "extra": {"warmth": 18, "slot": "torso"},
                       "description": "A bobcat fur vest. Warm under a jacket."},
        category="furwork",
    ),
    Recipe(
        id="lynx_fur_coat", name="Lynx Fur Coat",
        description="A spotted lynx coat. Rare and beautiful.",
        materials=[("lynx_pelt", 3)],
        tool_required="cut", skill="furriery", difficulty=10, time_minutes=160,
        output_custom={"id": "lynx_coat", "name": "Lynx Fur Coat", "weight": 5.0,
                       "category": "clothing", "base_value": 22.00,
                       "extra": {"warmth": 30, "armor": 1, "slot": "torso"},
                       "description": "A lynx fur coat. Spotted, elegant, warm."},
        category="furwork",
    ),
    Recipe(
        id="otter_fur_hat", name="Otter Fur Hat",
        description="A sleek otter fur hat. Waterproof.",
        materials=[("otter_pelt", 1)],
        tool_required="cut", skill="furriery", difficulty=7, time_minutes=40,
        output_custom={"id": "otter_hat", "name": "Otter Fur Hat", "weight": 0.4,
                       "category": "clothing", "base_value": 7.00,
                       "extra": {"warmth": 18, "slot": "head"},
                       "description": "An otter fur hat. Sheds water."},
        category="furwork",
    ),
    Recipe(
        id="wolverine_coat", name="Wolverine Fur Coat",
        description="A wolverine fur coat. Frost never sticks to it.",
        materials=[("wolverine_pelt", 3)],
        tool_required="cut", skill="furriery", difficulty=11, time_minutes=180,
        output_custom={"id": "wolverine_coat", "name": "Wolverine Fur Coat", "weight": 6.0,
                       "category": "clothing", "base_value": 35.00,
                       "extra": {"warmth": 40, "armor": 2, "slot": "torso"},
                       "description": "Wolverine fur. Frost brushes right off. Premium."},
        category="furwork",
    ),
    Recipe(
        id="coyote_blanket", name="Coyote Fur Blanket",
        description="A sewn blanket from coyote pelts.",
        materials=[("coyote_pelt", 4)],
        tool_required="cut", skill="furriery", difficulty=6, time_minutes=90,
        output_custom={"id": "coyote_blanket", "name": "Coyote Fur Blanket", "weight": 4.0,
                       "category": "misc", "base_value": 6.00,
                       "extra": {"warmth_bonus": 25, "sleep_bonus": 1.3},
                       "description": "A warm fur blanket. Better sleep."},
        category="furwork",
    ),
    Recipe(
        id="marten_scarf", name="Marten Fur Scarf",
        description="A soft pine marten fur scarf.",
        materials=[("marten_pelt", 2)],
        tool_required="cut", skill="furriery", difficulty=6, time_minutes=30,
        output_custom={"id": "marten_scarf", "name": "Marten Fur Scarf", "weight": 0.3,
                       "category": "clothing", "base_value": 8.00,
                       "extra": {"warmth": 12, "slot": "neck"},
                       "description": "A pine marten scarf. Soft and warm."},
        category="furwork",
    ),
    Recipe(
        id="fisher_hat", name="Fisher Fur Hat",
        description="A rare fisher fur hat.",
        materials=[("fisher_pelt", 1)],
        tool_required="cut", skill="furriery", difficulty=8, time_minutes=45,
        output_custom={"id": "fisher_hat", "name": "Fisher Fur Hat", "weight": 0.5,
                       "category": "clothing", "base_value": 9.00,
                       "extra": {"warmth": 20, "slot": "head"},
                       "description": "A fisher fur hat. Dark, thick, rare."},
        category="furwork",
    ),
    Recipe(
        id="skunk_cap", name="Skunk Fur Cap",
        description="A striped skunk cap. Cheap but warm.",
        materials=[("skunk_pelt", 2)],
        tool_required="cut", skill="furriery", difficulty=4, time_minutes=30,
        output_custom={"id": "skunk_cap", "name": "Skunk Fur Cap", "weight": 0.3,
                       "category": "clothing", "base_value": 1.50,
                       "extra": {"warmth": 12, "slot": "head"},
                       "description": "A skunk fur cap. Smells faintly. Warm."},
        category="furwork",
    ),
    Recipe(
        id="deer_fur_pants", name="Deerskin Trousers",
        description="Fringed deerskin pants. Frontier classic.",
        materials=[("deer_pelt", 2), ("sinew", 1)],
        tool_required="cut", skill="furriery", difficulty=8, time_minutes=80,
        output_custom={"id": "deer_pants", "name": "Deerskin Trousers", "weight": 2.5,
                       "category": "clothing", "base_value": 7.00,
                       "extra": {"warmth": 15, "armor": 1, "slot": "legs"},
                       "description": "Fringed deerskin trousers. Tough and warm."},
        category="furwork",
    ),
    Recipe(
        id="elk_coat", name="Elk Hide Coat",
        description="A large elk hide coat.",
        materials=[("elk_pelt", 2), ("sinew", 2)],
        tool_required="cut", skill="furriery", difficulty=9, time_minutes=120,
        output_custom={"id": "elk_coat", "name": "Elk Hide Coat", "weight": 6.0,
                       "category": "clothing", "base_value": 12.00,
                       "extra": {"warmth": 28, "armor": 2, "slot": "torso"},
                       "description": "A thick elk hide coat. Heavy but warm."},
        category="furwork",
    ),
    Recipe(
        id="cougar_cloak", name="Cougar Skin Cloak",
        description="A mountain lion skin worn as a cloak. Imposing.",
        materials=[("cougar_pelt", 2)],
        tool_required="cut", skill="furriery", difficulty=9, time_minutes=100,
        output_custom={"id": "cougar_cloak", "name": "Cougar Skin Cloak", "weight": 4.0,
                       "category": "clothing", "base_value": 15.00,
                       "extra": {"warmth": 25, "armor": 1, "slot": "torso"},
                       "description": "A mountain lion cloak. You look dangerous."},
        category="furwork",
    ),

    # ── Fur trade goods (not wearable — pure trade value) ─────────
    Recipe(
        id="pelt_bundle", name="Pelt Bundle (10)",
        description="Bundle 10 stretched pelts for transport. Higher trade value.",
        materials=[("beaver_pelt", 10)],
        skill="furriery", difficulty=4, time_minutes=20,
        output_custom={"id": "pelt_bundle", "name": "Beaver Pelt Bundle", "weight": 15.0,
                       "category": "material", "base_value": 50.00,
                       "description": "10 beaver pelts bundled for trade. Premium."},
        category="furwork",
    ),
    Recipe(
        id="fur_blanket", name="Fur Blanket",
        description="Sew pelts into a blanket. Any 6 pelts work.",
        materials=[("raccoon_pelt", 6)],
        tool_required="cut", skill="furriery", difficulty=5, time_minutes=90,
        output_custom={"id": "fur_blanket", "name": "Fur Blanket", "weight": 5.0,
                       "category": "misc", "base_value": 8.00,
                       "extra": {"warmth_bonus": 30, "sleep_bonus": 1.5},
                       "description": "A warm fur blanket sewn from pelts."},
        category="furwork",
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

    # Consume materials — track source names for prefixing output
    source_names = {}  # mat_id → display name of consumed item
    for mat_id, qty_needed in recipe.materials:
        remaining = qty_needed
        for item in list(player.inventory):
            if remaining <= 0:
                break
            if item.id != mat_id:
                continue
            # Remember the name (e.g. "Mule Deer Large Hide" for raw_hide)
            if mat_id not in source_names:
                source_names[mat_id] = item.name
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

    # Prefix with animal source name if applicable
    # e.g. "Mule Deer Large Hide" → extract "Mule Deer" → "Mule Deer Tanned Leather"
    hide_name = source_names.get("raw_hide", "") or source_names.get("leather", "")
    if hide_name:
        # Extract animal prefix: everything before "Hide", "Leather", "Large", "Medium", "Small"
        import re
        prefix = re.split(r'\b(Hide|Skin|Leather|Large|Medium|Small|Raw|Tanned)\b',
                          hide_name, maxsplit=1)[0].strip()
        if prefix and prefix.lower() not in item.name.lower():
            item.name = f"{prefix} {item.name}"

    player.inventory.append(item)
    player.gain_skill_xp(recipe.skill, 3.0 + recipe.difficulty * 0.5)
    return True, f"Crafted: {item.display_name()}."
