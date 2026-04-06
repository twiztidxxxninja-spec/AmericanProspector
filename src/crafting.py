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
    requires_fire: bool = False


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
        description="Silent ranged weapon. Uses arrows. Bowstring required.",
        materials=[("log", 1), ("bowstring", 1)],
        tool_required="cut", skill="survival", difficulty=10, time_minutes=90,
        output_id="hunting_bow",
        category="woodwork",
    ),
    Recipe(
        id="repair_tool", name="Repair Tool Handle",
        description="Re-glue and bind a worn tool handle with hoof glue and gut string.",
        materials=[("hoof_glue", 1), ("gut_string", 1)],
        skill="engineering", difficulty=5, time_minutes=30,
        output_custom={"id": "repair_kit", "name": "Tool Repair Kit", "weight": 0.3,
                       "category": "tool", "base_value": 0.75, "stackable": True,
                       "tool_tags": ["repair"],
                       "description": "Glue and binding. Restores condition on worn tools."},
        output_qty=2,
        category="tools",
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
        category="materials",
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
        category="tools",
    ),
    # ── Food Preservation ──────────────────────────────────────────────
    Recipe(
        id="clean_fish", name="Clean Fish",
        description="Gut, scale, and fillet a fresh fish. "
                    "Produces clean fillets and fish guts for bait.",
        materials=[("fresh_fish", 1)],
        tool_required="cut", skill="cooking", difficulty=3, time_minutes=5,
        output_custom={"id": "fish_fillet", "name": "Fish Fillet", "weight": 0.3,
                       "category": "food", "nutrition": 20.0, "base_value": 0.04,
                       "stackable": True, "perishable": True, "days_until_spoil": 2,
                       "description": "Clean fish fillet. Cook, smoke, or dry."},
        output_qty=2,
        category="food",
    ),
    Recipe(
        id="smoke_meat", name="Smoked Meat",
        description="Hang fresh meat over a smoky fire. Takes hours but keeps for weeks. "
                    "Requires a campfire or drying rack nearby.",
        materials=[("fresh_venison", 1)],
        skill="cooking", difficulty=6, time_minutes=180,
        output_id="smoked_meat", output_qty=2,
        category="food",
    ),
    Recipe(
        id="smoke_fish", name="Smoked Fish",
        description="Hang fish over a smoky fire. Preserves for weeks.",
        materials=[("fresh_fish", 2)],
        skill="cooking", difficulty=5, time_minutes=120,
        output_id="dried_fish", output_qty=2,
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
        description="Pemmican with wild berries mixed in. Tastes better "
                    "and more nutritious. Berries add slight spoilage risk.",
        materials=[("jerky", 2), ("tallow", 1), ("wild_berries", 1)],
        skill="survival", difficulty=8, time_minutes=120,
        output_custom={"id": "pemican_berry", "name": "Berry Pemmican",
                       "weight": 0.2, "category": "food", "nutrition": 40.0,
                       "description": "Pemmican with dried berries. "
                                      "Richer flavor, more energy. "
                                      "The berries prevent scurvy and lift spirits.",
                       "base_value": 0.25, "stackable": True,
                       "perishable": True, "days_until_spoil": 365,
                       "extra": {"fatigue_restore": 8, "scurvy_cure": True}},
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
        skill="cooking", difficulty=3, time_minutes=15,
        output_custom={"id": "cooked_meat", "name": "Cooked Meat", "weight": 0.8,
                       "category": "food", "nutrition": 35.0, "base_value": 0.10,
                       "perishable": True, "days_until_spoil": 3,
                       "description": "Well-cooked venison. Filling."},
        category="food",
    ),
    Recipe(
        id="cook_fillet", name="Cooked Fish Fillet",
        description="Pan-fry a cleaned fillet. Quick and nourishing.",
        materials=[("fish_fillet", 1)],
        skill="cooking", difficulty=2, time_minutes=8,
        output_custom={"id": "cooked_fish", "name": "Cooked Fish Fillet", "weight": 0.25,
                       "category": "food", "nutrition": 20.0, "base_value": 0.08,
                       "perishable": True, "days_until_spoil": 2,
                       "description": "Crispy pan-fried fillet."},
        category="food",
    ),
    Recipe(
        id="cook_fish", name="Cooked Fish (whole)",
        description="Roast a whole fish over the fire. No cleaning needed.",
        materials=[("fresh_fish", 1)],
        skill="cooking", difficulty=2, time_minutes=10,
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
        skill="cooking", difficulty=4, time_minutes=60,
        output_custom={"id": "stew", "name": "Hot Stew", "weight": 0.8,
                       "category": "food", "nutrition": 50.0, "base_value": 0.15,
                       "hydration": 10.0, "perishable": True, "days_until_spoil": 1,
                       "description": "Thick stew. Warms you from the inside."},
        output_qty=2,
        category="food",
    ),
    Recipe(
        id="make_hardtack", name="Hardtack",
        description="Flour, water, and salt baked into rock-hard biscuits. Lasts forever.",
        materials=[("flour", 2), ("salt", 1)],
        skill="cooking", difficulty=3, time_minutes=60,
        output_id="hardtack", output_qty=6,
        category="food",
    ),
    Recipe(
        id="dry_fish", name="Dried Fish",
        description="Salt and dry fish on a rack. Trail food.",
        materials=[("fresh_fish", 2), ("salt", 1)],
        skill="cooking", difficulty=5, time_minutes=180,
        output_custom={"id": "dried_fish", "name": "Dried Fish", "weight": 0.3,
                       "category": "food", "nutrition": 18.0, "base_value": 0.10,
                       "stackable": True, "perishable": True, "days_until_spoil": 45,
                       "description": "Salt-dried fish. Keeps well on the trail."},
        output_qty=3,
        category="food",
    ),
    # ── Brewing & Distilling ─────────────────────────────────────────
    # Step 1: Mash barrel → Beer (base fermentation)
    Recipe(
        id="brew_grain_beer", name="Grain Beer",
        description="Ferment flour in a mash barrel. Basic frontier beer.",
        materials=[("flour", 3)],
        skill="chemistry", difficulty=5, time_minutes=240,
        output_custom={"id": "beer", "name": "Grain Beer", "weight": 1.0,
                       "category": "drink", "base_value": 0.25, "hydration": 10.0,
                       "stackable": True, "perishable": True, "days_until_spoil": 14,
                       "extra": {"warmth_bonus": 5, "aim_penalty": -1, "brew_base": "grain"},
                       "description": "Cloudy frontier beer from grain. Refreshing."},
        output_qty=3, category="food",
    ),
    Recipe(
        id="brew_corn_beer", name="Corn Beer",
        description="Ferment corn in a mash barrel. Sweeter than grain beer.",
        materials=[("corn", 3)],
        skill="chemistry", difficulty=5, time_minutes=240,
        output_custom={"id": "corn_beer", "name": "Corn Beer", "weight": 1.0,
                       "category": "drink", "base_value": 0.30, "hydration": 10.0,
                       "stackable": True, "perishable": True, "days_until_spoil": 14,
                       "extra": {"warmth_bonus": 5, "aim_penalty": -1, "brew_base": "corn"},
                       "description": "Corn beer. Sweeter and smoother than grain."},
        output_qty=3, category="food",
    ),
    Recipe(
        id="brew_berry_beer", name="Berry Beer",
        description="Ferment berries for a fruity, tart beer.",
        materials=[("wild_berries", 4)],
        skill="chemistry", difficulty=6, time_minutes=240,
        output_custom={"id": "berry_beer", "name": "Berry Beer", "weight": 1.0,
                       "category": "drink", "base_value": 0.35, "hydration": 10.0,
                       "stackable": True, "perishable": True, "days_until_spoil": 10,
                       "extra": {"warmth_bonus": 5, "aim_penalty": -1, "brew_base": "berry"},
                       "description": "Fruity, tart berry beer. Unusual but popular."},
        output_qty=3, category="food",
    ),
    Recipe(
        id="brew_mead", name="Mead",
        description="Ferment honey with water. Ancient drink of warriors.",
        materials=[("wild_honey", 2)],
        skill="chemistry", difficulty=7, time_minutes=360,
        output_custom={"id": "mead", "name": "Mead", "weight": 1.0,
                       "category": "drink", "base_value": 1.00, "hydration": 8.0,
                       "stackable": True, "perishable": True, "days_until_spoil": 30,
                       "extra": {"warmth_bonus": 8, "aim_penalty": -1, "brew_base": "honey"},
                       "description": "Golden honey mead. Sweet, strong, ancient."},
        output_qty=2, category="food",
    ),

    Recipe(
        id="brew_wine", name="Wine",
        description="Ferment berries into wine. Simple, no grain needed. "
                    "Just berries, time, and a barrel.",
        materials=[("wild_berries", 6)],
        skill="chemistry", difficulty=6, time_minutes=360,
        output_id="wine", output_qty=3, category="food",
    ),

    # Step 2: Beer/Mead/Wine + Still → Whiskey/Spirits (distillation)
    Recipe(
        id="distill_grain_whiskey", name="Grain Whiskey",
        description="Distill grain beer through a copper still. Standard frontier whiskey.",
        materials=[("beer", 3)],
        tool_required="distill",
        skill="chemistry", difficulty=10, time_minutes=480,
        output_id="whiskey", output_qty=2,
        category="food",
    ),
    Recipe(
        id="distill_bourbon", name="Bourbon",
        description="Distill corn beer into smooth bourbon. Premium American spirit.",
        materials=[("corn_beer", 3)],
        tool_required="distill",
        skill="chemistry", difficulty=10, time_minutes=480,
        output_custom={"id": "bourbon", "name": "Bourbon", "weight": 1.5,
                       "category": "drink", "base_value": 1.50, "hydration": 3.0,
                       "stackable": True,
                       "extra": {"warmth_bonus": 20, "aim_penalty": -3, "courage_bonus": 5,
                                 "disinfect": True},
                       "description": "Smooth corn bourbon. The good stuff."},
        output_qty=2, category="food",
    ),
    Recipe(
        id="distill_brandy", name="Brandy",
        description="Distill berry beer into brandy. Smooth and valuable.",
        materials=[("berry_beer", 3)],
        tool_required="distill",
        skill="chemistry", difficulty=11, time_minutes=480,
        output_custom={"id": "brandy", "name": "Brandy", "weight": 1.5,
                       "category": "drink", "base_value": 3.00, "hydration": 3.0,
                       "stackable": True,
                       "extra": {"warmth_bonus": 20, "aim_penalty": -3, "courage_bonus": 5,
                                 "disinfect": True},
                       "description": "Fruit brandy. Rich, smooth, expensive."},
        output_qty=2, category="food",
    ),
    Recipe(
        id="distill_wine_brandy", name="Brandy (from wine)",
        description="Distill wine into brandy. The classic method.",
        materials=[("wine", 3)],
        tool_required="distill",
        skill="chemistry", difficulty=10, time_minutes=480,
        output_custom={"id": "brandy", "name": "Brandy", "weight": 1.5,
                       "category": "drink", "base_value": 3.00, "hydration": 3.0,
                       "stackable": True,
                       "extra": {"warmth_bonus": 20, "aim_penalty": -3, "courage_bonus": 5,
                                 "disinfect": True},
                       "description": "Wine brandy. The proper way to make it."},
        output_qty=2, category="food",
    ),
    Recipe(
        id="distill_honey_mead_spirit", name="Honey Spirit",
        description="Distill mead into a powerful honey spirit.",
        materials=[("mead", 3)],
        tool_required="distill",
        skill="chemistry", difficulty=12, time_minutes=480,
        output_custom={"id": "honey_spirit", "name": "Honey Spirit", "weight": 1.5,
                       "category": "drink", "base_value": 5.00, "hydration": 3.0,
                       "stackable": True,
                       "extra": {"warmth_bonus": 25, "aim_penalty": -4, "courage_bonus": 8,
                                 "disinfect": True},
                       "description": "Distilled honey mead. Liquid gold. Rare and prized."},
        output_qty=2, category="food",
    ),

    # Flavored spirits (add botanicals to whiskey)
    Recipe(
        id="make_gin", name="Gin",
        description="Redistill whiskey with juniper berries. Classic spirit.",
        materials=[("whiskey", 1), ("juniper_berries", 2)],
        tool_required="distill",
        skill="chemistry", difficulty=9, time_minutes=120,
        output_custom={"id": "gin", "name": "Gin", "weight": 1.5,
                       "category": "drink", "base_value": 2.00, "hydration": 3.0,
                       "stackable": True,
                       "extra": {"warmth_bonus": 15, "aim_penalty": -3,
                                 "disinfect": True},
                       "description": "Juniper gin. Piney, sharp, civilized."},
        output_qty=1, category="food",
    ),
    Recipe(
        id="make_applejack", name="Applejack",
        description="Freeze-distill hard cider. Leave beer out in the cold, "
                    "remove the ice, keep the alcohol. Winter-only.",
        materials=[("berry_beer", 2)],
        skill="chemistry", difficulty=7, time_minutes=60,
        output_custom={"id": "applejack", "name": "Applejack", "weight": 1.0,
                       "category": "drink", "base_value": 1.00, "hydration": 5.0,
                       "stackable": True,
                       "extra": {"warmth_bonus": 15, "aim_penalty": -2,
                                 "disinfect": True},
                       "description": "Freeze-concentrated fruit liquor. Strong and rough."},
        output_qty=1, category="food",
    ),
    Recipe(
        id="make_bitters", name="Bitters",
        description="Steep roots, bark, and herbs in whiskey for weeks. "
                    "Medicinal tonic and cocktail ingredient.",
        materials=[("whiskey", 1), ("brush_bundle", 2)],
        skill="chemistry", difficulty=8, time_minutes=60,
        output_custom={"id": "bitters", "name": "Bitters", "weight": 0.3,
                       "category": "drink", "base_value": 2.50, "stackable": True,
                       "extra": {"pain_relief": 10, "fatigue_restore": 10},
                       "description": "Herbal bitters. Settles the stomach, steadies the nerves. "
                                      "A few drops in whiskey makes a proper cocktail."},
        output_qty=2, category="food",
    ),
    Recipe(
        id="make_rum", name="Rum",
        description="Ferment molasses, then distill. Sweet, dark spirit.",
        materials=[("molasses", 3)],
        tool_required="distill",
        skill="chemistry", difficulty=11, time_minutes=480,
        output_custom={"id": "rum", "name": "Rum", "weight": 1.5,
                       "category": "drink", "base_value": 2.00, "hydration": 3.0,
                       "stackable": True,
                       "extra": {"warmth_bonus": 20, "aim_penalty": -3, "courage_bonus": 6,
                                 "disinfect": True},
                       "description": "Sweet dark rum. Sailor's drink, frontiersman's friend."},
        output_qty=2, category="food",
    ),
    Recipe(
        id="make_hot_toddy", name="Hot Toddy",
        description="Whiskey, honey, and hot water. The frontier cold remedy.",
        materials=[("whiskey", 1), ("wild_honey", 1)],
        skill="survival", difficulty=3, time_minutes=10,
        output_custom={"id": "hot_toddy", "name": "Hot Toddy", "weight": 0.5,
                       "category": "drink", "base_value": 0.75, "hydration": 10.0,
                       "extra": {"warmth_bonus": 25, "pain_relief": 15,
                                 "fatigue_restore": 10},
                       "description": "Whiskey and honey in hot water. "
                                      "Cures what ails you. Or at least makes you not care."},
        output_qty=2, category="food",
    ),
    Recipe(
        id="make_mint_julep", name="Mint Julep",
        description="Whiskey muddled with fresh mint and honey. A gentleman's drink.",
        materials=[("whiskey", 1), ("wild_mint", 1), ("wild_honey", 1)],
        skill="chemistry", difficulty=4, time_minutes=10,
        output_custom={"id": "mint_julep", "name": "Mint Julep", "weight": 0.5,
                       "category": "drink", "base_value": 1.50, "hydration": 5.0,
                       "extra": {"warmth_bonus": 10, "aim_penalty": -2,
                                 "fatigue_restore": 5},
                       "description": "Whiskey with mint and honey. Refreshing and civilized."},
        output_qty=2, category="food",
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
        category="tools",
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
        category="tools",
    ),
    Recipe(
        id="make_rope", name="Rope (from rawhide)",
        description="Cut rawhide into strips and braid into rope.",
        materials=[("raw_hide", 1)],
        tool_required="cut", skill="survival", difficulty=5, time_minutes=30,
        output_id="rope_10ft", output_qty=2,
        category="materials",
    ),
    Recipe(
        id="make_fishing_line", name="Fishing Line & Hook",
        description="Twist sinew into line, bend bone into a hook.",
        materials=[("sinew", 1), ("animal_bones", 1)],
        tool_required="cut", skill="survival", difficulty=6, time_minutes=25,
        output_id="fishing_line",
        category="tools",
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
        category="shelter",
    ),
    Recipe(
        id="make_bedroll", name="Bedroll",
        description="A bedroll from leather and blanket material. Sleep anywhere.",
        materials=[("leather", 2), ("raw_hide", 1)],
        tool_required="cut", skill="survival", difficulty=6, time_minutes=60,
        output_id="bedroll",
        category="shelter",
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
        category="tools",
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
        category="tools",
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
        category="tools",
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
        category="tools",
    ),

    # ── Medical ──────────────────────────────────────────────────────
    Recipe(
        id="bandage", name="Cloth Bandage",
        description="Tear clean cloth into bandages for treating wounds.",
        materials=[("canvas", 1)],
        skill="firstAid", difficulty=4, time_minutes=10,
        output_custom={"id": "bandage", "name": "Bandage", "weight": 0.1,
                       "category": "tool", "base_value": 0.20, "stackable": True,
                       "tool_tags": ["medical"],
                       "description": "A strip of clean cloth for bandaging wounds."},
        category="medical",
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
        category="tools",
    ),

    # ── Animal parts crafting ────────────────────────────────────────
    Recipe(
        id="horn_cup", name="Horn Cup",
        description="A drinking cup carved from animal horn. Holds water.",
        materials=[("animal_horn", 1)],
        tool_required="cut", skill="survival", difficulty=5, time_minutes=30,
        output_custom={"id": "horn_cup", "name": "Horn Cup", "weight": 0.3,
                       "category": "tool", "base_value": 0.50,
                       "hydration": 15.0, "tool_tags": ["drink"],
                       "description": "A horn cup. Fill at any stream."},
        category="bonework",
    ),
    Recipe(
        id="claw_necklace", name="Bear Claw Necklace",
        description="String bear claws into a necklace. Impressive and tradeable.",
        materials=[("bear_claws", 1), ("sinew", 1)],
        skill="survival", difficulty=4, time_minutes=20,
        output_custom={"id": "claw_necklace", "name": "Bear Claw Necklace",
                       "weight": 0.2, "category": "misc", "base_value": 5.00,
                       "description": "A necklace of grizzly claws. Commands respect."},
        category="bonework",
    ),
    Recipe(
        id="hoof_glue", name="Hoof Glue",
        description="Boil hooves into strong adhesive. Used in repairs and woodwork.",
        materials=[("hooves", 2)],
        skill="survival", difficulty=5, time_minutes=120,
        output_custom={"id": "hoof_glue", "name": "Hoof Glue", "weight": 0.5,
                       "category": "material", "base_value": 0.30, "stackable": True,
                       "description": "Strong hide glue. Repairs tool handles and bindings."},
        output_qty=2,
        category="materials",
    ),
    Recipe(
        id="gut_string", name="Gut String",
        description="Clean and twist intestines into durable cord. Stronger than sinew.",
        materials=[("intestines", 1)],
        tool_required="cut", skill="survival", difficulty=6, time_minutes=45,
        output_custom={"id": "gut_string", "name": "Gut String", "weight": 0.1,
                       "category": "material", "base_value": 0.40, "stackable": True,
                       "description": "Twisted intestine cord. Strong for snares and bowstrings."},
        output_qty=3,
        category="materials",
    ),
    Recipe(
        id="water_bag", name="Stomach Water Bag",
        description="Clean a stomach sac and use as a water carrier. Free canteen.",
        materials=[("stomach_sac", 1)],
        tool_required="cut", skill="survival", difficulty=5, time_minutes=20,
        output_custom={"id": "stomach_bag", "name": "Stomach Water Bag", "weight": 0.3,
                       "category": "drink", "base_value": 0.25, "hydration": 25.0,
                       "description": "A cleaned animal stomach. Holds water. Smells faintly."},
        category="tools",
    ),
    Recipe(
        id="small_leather", name="Small Leather Piece",
        description="Tan a small hide into usable leather scraps.",
        materials=[("small_hide", 1), ("brain", 1)],
        tool_required="cut", skill="survival", difficulty=6, time_minutes=40,
        output_custom={"id": "leather_scrap", "name": "Leather Scraps", "weight": 0.5,
                       "category": "material", "base_value": 0.50, "stackable": True,
                       "description": "Small pieces of tanned leather. Patches and repairs."},
        output_qty=2,
        category="leatherwork",
    ),
    Recipe(
        id="castoreum_lure", name="Castoreum Lure",
        description="Beaver castoreum is the best trapping lure. Animals can't resist it.",
        materials=[("castoreum", 1)],
        skill="trapping", difficulty=3, time_minutes=10,
        output_custom={"id": "castoreum_lure", "name": "Castoreum Lure", "weight": 0.1,
                       "category": "tool", "base_value": 2.00, "stackable": True,
                       "tool_tags": ["bait", "lure"],
                       "description": "Beaver scent lure. Irresistible to furbearers."},
        output_qty=3,
        category="trapping",
    ),
    Recipe(
        id="skull_trophy", name="Skull Trophy",
        description="Clean and mount an animal skull. Decoration or trade goods.",
        materials=[("head", 1)],
        tool_required="cut", skill="survival", difficulty=4, time_minutes=30,
        output_custom={"id": "skull_trophy", "name": "Skull Trophy", "weight": 2.0,
                       "category": "misc", "base_value": 1.50,
                       "description": "A cleaned animal skull. Decoration or curiosity."},
        category="bonework",
    ),
    Recipe(
        id="gallbladder_medicine", name="Bear Bile Medicine",
        description="Traditional medicine from bear gallbladder. Highly valued by Chinese merchants.",
        materials=[("bear_gallbladder", 1)],
        skill="firstAid", difficulty=5, time_minutes=15,
        output_custom={"id": "bear_bile", "name": "Bear Bile Medicine", "weight": 0.1,
                       "category": "tool", "base_value": 8.00,
                       "tool_tags": ["medical"],
                       "description": "Traditional medicine. Valuable trade item with Chinese merchants."},
        category="medical",
    ),
    Recipe(
        id="rattlesnake_charm", name="Rattlesnake Rattle Charm",
        description="String a rattlesnake rattle as a good luck charm. Superstition pays.",
        materials=[("rattlesnake_rattle", 1), ("sinew", 1)],
        skill="survival", difficulty=2, time_minutes=10,
        output_custom={"id": "rattle_charm", "name": "Rattlesnake Charm", "weight": 0.05,
                       "category": "misc", "base_value": 1.00,
                       "description": "A rattlesnake rattle on a sinew cord. Lucky, some say."},
        category="bonework",
    ),
    Recipe(
        id="clay_pot", name="Clay Pot",
        description="Shape and fire a clay pot. Cook stew, carry water, store food.",
        materials=[("clay", 2)],
        skill="survival", difficulty=7, time_minutes=120,
        output_custom={"id": "clay_pot", "name": "Clay Pot", "weight": 2.0,
                       "category": "tool", "base_value": 0.50,
                       "tool_tags": ["cook", "brew"],
                       "description": "A hand-fired clay pot. Cook, boil, or store."},
        category="tools",
    ),

    # ── Medical ──────────────────────────────────────────────────────
    Recipe(
        id="splint", name="Splint",
        description="Immobilize a broken bone with sticks and cloth.",
        materials=[("log", 1)],
        tool_required="cut", skill="firstAid", difficulty=6, time_minutes=15,
        output_custom={"id": "splint", "name": "Splint", "weight": 0.3,
                       "category": "tool", "base_value": 0.15, "stackable": True,
                       "tool_tags": ["medical", "set_bone"],
                       "description": "A wooden splint. Immobilizes fractures."},
        category="medical",
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
        category="medical",
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
        category="medical",
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
        category="medical",
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
        category="materials",
    ),
    Recipe(
        id="make_nails", name="Nails (from iron)",
        description="Hammer iron into nails. Required for construction.",
        materials=[("iron_bar", 1)],
        skill="engineering", difficulty=8, time_minutes=60,
        output_id="nails", output_qty=10,
        category="materials",
    ),
    Recipe(
        id="make_rawhide_rope", name="Rawhide Lashing",
        description="Cut raw hide into strips for tying, lashing, and binding.",
        materials=[("raw_hide", 1)],
        tool_required="cut", skill="survival", difficulty=3, time_minutes=15,
        output_id="cordage", output_qty=4,
        category="materials",
    ),

    # ── Crafting intermediates ────────────────────────────────────────
    Recipe(
        id="make_charcoal", name="Charcoal",
        description="Burn wood into charcoal. Used for smelting and filtration.",
        materials=[("log", 1)],
        skill="survival", difficulty=4, time_minutes=30,
        output_id="charcoal", output_qty=3,
        category="materials",
    ),
    Recipe(
        id="make_lye", name="Lye",
        description="Mix wood ash with water to make lye. Soap, hide processing.",
        materials=[("charcoal", 1)],
        skill="survival", difficulty=5, time_minutes=20,
        output_id="lye", output_qty=2,
        category="materials",
    ),
    Recipe(
        id="make_cordage", name="Cordage (from brush)",
        description="Strip bark and fibers from brush, twist into usable rope.",
        materials=[("brush_bundle", 1)],
        skill="survival", difficulty=3, time_minutes=15,
        output_id="cordage", output_qty=3,
        category="materials",
    ),

    # ── Survival crafting ─────────────────────────────────────────────
    Recipe(
        id="salt_meat", name="Salt Preserved Meat",
        description="Preserve meat with salt. Triples time before spoiling.",
        materials=[("salt", 1)],  # player picks meat from inventory during craft
        skill="cooking", difficulty=4, time_minutes=15,
        output_custom={"id": "salted_meat", "name": "Salted Meat", "weight": 1.0,
                       "category": "food", "base_value": 0.80,
                       "nutrition": 35.0, "perishable": True,
                       "days_until_spoil": 30,
                       "description": "Salt-preserved meat. Lasts weeks."},
        category="food",
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
        category="food",
    ),
    # ── Additional Food ──────────────────────────────────────────────
    Recipe(
        id="cornbread", name="Cornbread",
        description="Corn, flour, and water baked in a pan. Filling frontier staple.",
        materials=[("corn", 1), ("flour", 1)],
        skill="cooking", difficulty=4, time_minutes=30,
        output_custom={"id": "cornbread", "name": "Cornbread", "weight": 0.4,
                       "category": "food", "nutrition": 25.0, "base_value": 0.08,
                       "stackable": True, "perishable": True, "days_until_spoil": 5,
                       "description": "Dense cornbread. Filling, travels well."},
        output_qty=3, category="food",
    ),
    Recipe(
        id="bone_broth", name="Bone Broth",
        description="Simmer bones in water for hours. Nutritious, warms you, heals.",
        materials=[("animal_bones", 2)],
        skill="cooking", difficulty=3, time_minutes=120,
        output_custom={"id": "bone_broth", "name": "Bone Broth", "weight": 0.5,
                       "category": "food", "nutrition": 15.0, "hydration": 15.0,
                       "base_value": 0.05, "perishable": True, "days_until_spoil": 2,
                       "extra": {"warmth_bonus": 15, "health_restore": 3},
                       "description": "Rich bone broth. Warms and heals."},
        output_qty=2, category="food",
    ),
    Recipe(
        id="fried_fillet", name="Fried Fish Fillet",
        description="Fry a fillet in tallow. Crispy, rich, more nutritious than plain.",
        materials=[("fish_fillet", 1), ("tallow", 1)],
        skill="cooking", difficulty=5, time_minutes=15,
        output_custom={"id": "fried_fish", "name": "Fried Fish", "weight": 0.3,
                       "category": "food", "nutrition": 28.0, "base_value": 0.12,
                       "perishable": True, "days_until_spoil": 2,
                       "description": "Pan-fried in tallow. Golden and crispy."},
        category="food",
    ),

    # ── Weapons ──────────────────────────────────────────────────────
    Recipe(
        id="make_spear", name="Spear",
        description="Sharpen a long pole into a thrusting weapon. "
                    "Reach advantage in combat and essential for spear fishing.",
        materials=[("log", 1)],
        tool_required="cut", skill="survival", difficulty=5, time_minutes=20,
        output_custom={"id": "spear", "name": "Spear", "weight": 4.0,
                       "category": "weapon", "base_value": 0.50, "weapon_type": "melee",
                       "damage_min": 8, "damage_max": 20,
                       "tool_tags": ["spear"],
                       "description": "A sharpened wooden spear. Fishing, hunting, fighting."},
        category="woodwork",
    ),
    Recipe(
        id="make_sling", name="Sling",
        description="Leather pouch on two cords. Hurls stones with lethal force. "
                    "David killed Goliath with one of these.",
        materials=[("leather", 1), ("cordage", 2)],
        skill="survival", difficulty=6, time_minutes=20,
        output_custom={"id": "sling", "name": "Sling", "weight": 0.2,
                       "category": "weapon", "base_value": 0.25, "weapon_type": "ranged",
                       "damage_min": 5, "damage_max": 15,
                       "description": "Leather sling. Silent, ammo is everywhere (rocks)."},
        category="leatherwork",
    ),
    Recipe(
        id="war_club", name="Stone War Club",
        description="A heavy stone lashed to a handle. Devastating blunt weapon.",
        materials=[("log", 1), ("stone", 2), ("cordage", 1)],
        skill="survival", difficulty=7, time_minutes=45,
        output_custom={"id": "war_club", "name": "Stone War Club", "weight": 5.0,
                       "category": "weapon", "base_value": 0.50, "weapon_type": "melee",
                       "damage_min": 10, "damage_max": 25,
                       "description": "A stone-headed club. Crushes bone."},
        category="woodwork",
    ),

    # ── Shelter ──────────────────────────────────────────────────────
    Recipe(
        id="brush_shelter", name="Brush Shelter",
        description="Emergency shelter from brush and branches. "
                    "Keeps rain off, breaks wind. No tools needed.",
        materials=[("brush_bundle", 4)],
        skill="survival", difficulty=4, time_minutes=30,
        output_custom={"id": "brush_shelter", "name": "Brush Shelter", "weight": 0.0,
                       "category": "misc", "base_value": 0.0,
                       "extra": {"shelter": True, "warmth_bonus": 10},
                       "description": "A crude brush shelter. Better than nothing."},
        category="shelter",
    ),

    # ── Tools & Transport ────────────────────────────────────────────
    Recipe(
        id="make_raft", name="Log Raft",
        description="Lash logs together into a river raft. "
                    "Cross deep water without swimming. Carry gear dry.",
        materials=[("log", 6), ("rope_10ft", 3)],
        skill="engineering", difficulty=8, time_minutes=180,
        output_custom={"id": "raft", "name": "Log Raft", "weight": 40.0,
                       "category": "tool", "base_value": 3.00,
                       "extra": {"river_crossing": True, "carry_capacity_lb": 200},
                       "description": "A lashed-log raft. Safe river crossings. "
                                      "Carries 200lb of gear across water."},
        category="tools",
    ),
    Recipe(
        id="make_wooden_stakes", name="Wooden Stakes (x4)",
        description="Sharpen logs into stakes. Claim markers, tent pegs, defense.",
        materials=[("log", 1)],
        tool_required="cut", skill="survival", difficulty=3, time_minutes=15,
        output_custom={"id": "wooden_stake", "name": "Wooden Stakes", "weight": 0.5,
                       "category": "material", "base_value": 0.05, "stackable": True,
                       "description": "Sharpened wooden stakes."},
        output_qty=4, category="woodwork",
    ),
    Recipe(
        id="pine_torch", name="Pine Torch",
        description="A resinous pine branch. Burns without tallow — the wood IS the fuel.",
        materials=[("log", 1)],
        skill="survival", difficulty=2, time_minutes=5,
        output_custom={"id": "pine_torch", "name": "Pine Torch", "weight": 0.8,
                       "category": "tool", "base_value": 0.05,
                       "tool_tags": ["light"],
                       "description": "A resinous pine torch. Burns bright, smells like forest."},
        category="woodwork",
    ),
    Recipe(
        id="make_pitch", name="Pine Pitch",
        description="Boil pine resin into sticky pitch. "
                    "Waterproofing, fire starter, adhesive, torch fuel.",
        materials=[("log", 2)],
        skill="survival", difficulty=5, time_minutes=60,
        output_custom={"id": "pine_pitch", "name": "Pine Pitch", "weight": 0.5,
                       "category": "material", "base_value": 0.20, "stackable": True,
                       "description": "Sticky pine pitch. Waterproofs, burns, glues."},
        output_qty=2, category="materials",
    ),

    # ── Medical ──────────────────────────────────────────────────────
    Recipe(
        id="make_sutures", name="Sutures",
        description="Bone needle and sinew thread. Close deep cuts surgically.",
        materials=[("bone_needle", 1), ("sinew", 1)],
        skill="firstAid", difficulty=8, time_minutes=5,
        output_custom={"id": "sutures", "name": "Sutures", "weight": 0.05,
                       "category": "tool", "base_value": 0.30, "stackable": True,
                       "tool_tags": ["medical", "stitch"],
                       "description": "Bone needle threaded with sinew. Stitch wounds closed."},
        output_qty=3, category="medical",
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
        id="make_dip_net", name="Dip Net",
        description="Weave a small hand net from cordage. Scoop fish from shallows.",
        materials=[("cordage", 3), ("log", 1)],
        tool_required="cut", skill="survival", difficulty=6, time_minutes=45,
        output_id="dip_net",
        category="tools",
    ),
    Recipe(
        id="make_gill_net", name="Gill Net",
        description="Weave a wide mesh net from cordage and sinew. "
                    "Stretch across a stream to catch everything swimming through.",
        materials=[("cordage", 6), ("sinew", 2), ("log", 2)],
        tool_required="cut", skill="survival", difficulty=9, time_minutes=180,
        output_id="gill_net",
        category="tools",
    ),
    Recipe(
        id="pelt_frame", name="Pelt Stretching Frame",
        description="For drying raw pelts. Place on ground, load pelt, wait 24h.",
        materials=[("log", 2), ("cordage", 1)],
        tool_required="cut", skill="furriery", difficulty=5, time_minutes=30,
        output_id="pelt_frame",
        category="trapping",
    ),

    # ── Pelt stretching (preserves raw pelts) ─────────────────────
    # Raw pelts spoil in 3 days. Stretching on a frame preserves them.
    Recipe(
        id="stretch_beaver", name="Stretch Beaver Pelt",
        description="Lace the raw beaver pelt onto a stretching frame, "
                    "flesh side out. Scrape the fat. Let it dry for a day.",
        materials=[("beaver_pelt", 1)],
        tool_required="stretch", skill="furriery", difficulty=4, time_minutes=20,
        output_custom={"id": "stretched_beaver", "name": "Stretched Beaver Pelt",
                       "weight": 1.5, "category": "material", "base_value": 5.00,
                       "description": "Beaver pelt stretched and dried on a frame. "
                                      "Preserved for trade. Prime quality if winter-caught."},
        category="trapping",
    ),
    Recipe(
        id="stretch_pelt_generic", name="Stretch Pelt",
        description="Lace a raw pelt onto the stretching frame and scrape it clean. "
                    "Takes a day to dry but stops the pelt from spoiling.",
        materials=[("fox_pelt", 1)],
        tool_required="stretch", skill="furriery", difficulty=3, time_minutes=15,
        output_custom={"id": "stretched_pelt", "name": "Stretched Pelt",
                       "weight": 1.0, "category": "material", "base_value": 2.50,
                       "description": "A pelt stretched and dried. Preserved for trade."},
        category="trapping",
    ),
    Recipe(
        id="stretch_large_pelt", name="Stretch Large Pelt",
        description="A large hide — bear, elk, buffalo — takes more frame and more time.",
        materials=[("bear_pelt", 1)],
        tool_required="stretch", skill="furriery", difficulty=5, time_minutes=30,
        output_custom={"id": "stretched_large_pelt", "name": "Stretched Large Pelt",
                       "weight": 3.0, "category": "material", "base_value": 8.00,
                       "description": "A large pelt stretched and dried. Heavy but valuable."},
        category="trapping",
    ),

    # ── Missing cooking recipes ────────────────────────────────────
    Recipe(
        id="roast_camas", name="Pit-Roast Camas Root",
        description="Slow-roast camas bulbs in a pit for a full day. "
                    "Turns the starch to sugar — tastes like sweet potato.",
        materials=[("camas_root", 2)],
        skill="cooking", difficulty=5, time_minutes=1440,  # 24 hours
        output_custom={"id": "roasted_camas", "name": "Roasted Camas",
                       "weight": 0.2, "category": "food", "nutrition": 20.0,
                       "base_value": 0.15, "stackable": True,
                       "description": "Slow-roasted camas root. Sweet and filling."},
        output_qty=3,
        category="food",
        requires_fire=True,
    ),
    Recipe(
        id="boil_bitterroot", name="Boil Bitterroot",
        description="Boil bitterroot to remove the bitter compounds. "
                    "Needs a pot and water.",
        materials=[("bitterroot", 2)],
        skill="cooking", difficulty=3, time_minutes=30,
        output_custom={"id": "boiled_bitterroot", "name": "Boiled Bitterroot",
                       "weight": 0.2, "category": "food", "nutrition": 12.0,
                       "base_value": 0.08, "stackable": True,
                       "description": "Boiled bitterroot. Bland but nutritious."},
        output_qty=2,
        category="food",
        requires_fire=True,
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

    # ── AMMUNITION ────────────────────────────────────────────────────────
    Recipe(
        id="cast_rifle_balls", name="Cast Rifle Balls",
        description="Melt lead and cast balls for a rifle. Requires a bullet mold.",
        materials=[("lead_bar", 1), ("gunpowder", 1), ("primer_caps", 1)],
        tool_required="mold", skill="firearms", difficulty=8, time_minutes=30,
        output_id="rifle_ball", output_qty=10,
        category="ammunition",
    ),
    Recipe(
        id="cast_revolver_balls", name="Cast Revolver Balls",
        description="Cast small-caliber balls for a percussion revolver.",
        materials=[("lead_bar", 1), ("gunpowder", 1), ("primer_caps", 1)],
        tool_required="mold", skill="firearms", difficulty=7, time_minutes=25,
        output_id="revolver_ball", output_qty=15,
        category="ammunition",
    ),
    Recipe(
        id="make_shot_charges", name="Make Shot Charges",
        description="Cut lead into shot and measure powder charges for a shotgun.",
        materials=[("lead_bar", 1), ("gunpowder", 1)],
        skill="firearms", difficulty=6, time_minutes=20,
        output_id="shotgun_shell", output_qty=8,
        category="ammunition",
    ),
    Recipe(
        id="craft_arrows", name="Craft Arrows",
        description="Assemble arrows from shafts, iron points, and feather fletching.",
        materials=[("arrow_shaft", 1), ("arrowhead_iron", 1), ("fletching", 1)],
        skill="survival", difficulty=5, time_minutes=15,
        output_id="arrow", output_qty=5,
        category="ammunition",
    ),
    Recipe(
        id="whittle_arrow_shafts", name="Whittle Arrow Shafts",
        description="Strip and straighten wooden sticks into arrow shafts.",
        materials=[("log", 1)],
        tool_required="cut", skill="survival", difficulty=4, time_minutes=20,
        output_custom={"id": "arrow_shaft", "name": "Arrow Shafts", "weight": 0.1,
                       "category": "material", "base_value": 0.05, "stackable": True,
                       "description": "Straight wooden shafts for arrow-making."},
        output_qty=8,
        category="ammunition",
    ),
    Recipe(
        id="knap_arrowheads", name="Knap Stone Arrowheads",
        description="Chip flint or obsidian into crude arrowheads. No forge needed.",
        materials=[("stone", 2)],
        skill="survival", difficulty=7, time_minutes=30,
        output_custom={"id": "arrowhead_iron", "name": "Stone Arrowheads", "weight": 0.1,
                       "category": "material", "base_value": 0.05, "stackable": True,
                       "description": "Knapped stone points. Crude but functional."},
        output_qty=4,
        category="ammunition",
    ),

    # ── FORAGE / HERBAL ───────────────────────────────────────────────────
    Recipe(
        id="brew_pine_tea", name="Pine Needle Tea",
        description="Steep fresh pine needles in hot water. Prevents scurvy.",
        materials=[("pine_needles", 1)],
        skill="survival", difficulty=2, time_minutes=10,
        output_id="pine_needle_tea", output_qty=2,
        category="food",
        requires_fire=True,
    ),
    Recipe(
        id="brew_mint_tea", name="Mint Tea",
        description="Steep wild mint in hot water. Settles the stomach.",
        materials=[("wild_mint", 1)],
        skill="survival", difficulty=2, time_minutes=10,
        output_custom={"id": "mint_tea", "name": "Mint Tea", "weight": 0.3,
                       "category": "drink", "hydration": 15.0, "nutrition": 1.0,
                       "base_value": 0.05,
                       "description": "Warm mint tea. Settles the gut."},
        output_qty=2,
        category="food",
        requires_fire=True,
    ),
    Recipe(
        id="brew_rosehip_tea", name="Rose Hip Tea",
        description="Steep rose hips in hot water. Tart and full of vitamins.",
        materials=[("rose_hips", 1)],
        skill="survival", difficulty=2, time_minutes=10,
        output_custom={"id": "rosehip_tea", "name": "Rose Hip Tea", "weight": 0.3,
                       "category": "drink", "hydration": 15.0, "nutrition": 2.0,
                       "base_value": 0.05,
                       "description": "Tart vitamin-rich tea from wild rose hips."},
        output_qty=2,
        category="food",
        requires_fire=True,
    ),
    Recipe(
        id="roast_cattail", name="Roasted Cattail Root",
        description="Roast cattail root over coals. Starchy and filling.",
        materials=[("cattail_root", 1)],
        skill="cooking", difficulty=3, time_minutes=15,
        output_custom={"id": "roasted_cattail", "name": "Roasted Cattail Root",
                       "weight": 0.2, "category": "food", "nutrition": 12.0,
                       "base_value": 0.05,
                       "description": "Roasted cattail root. Tastes like potato."},
        category="food",
        requires_fire=True,
    ),
    Recipe(
        id="leach_acorns", name="Leached Acorn Meal",
        description="Soak acorns to remove tannins, then grind into flour.",
        materials=[("acorns", 2)],
        skill="survival", difficulty=4, time_minutes=30,
        output_custom={"id": "acorn_meal", "name": "Acorn Meal", "weight": 0.3,
                       "category": "food", "nutrition": 10.0,
                       "base_value": 0.05, "stackable": True,
                       "description": "Ground acorn flour. Nutty. Mix into stew or bake."},
        output_qty=2,
        category="food",
    ),
    Recipe(
        id="yarrow_poultice", name="Yarrow Poultice",
        description="Crush yarrow into a wound dressing. Stops bleeding.",
        materials=[("yarrow", 1)],
        skill="firstAid", difficulty=3, time_minutes=5,
        output_custom={"id": "yarrow_poultice", "name": "Yarrow Poultice",
                       "weight": 0.1, "category": "medical",
                       "base_value": 0.10,
                       "description": "Crushed yarrow. Pack into wounds to stop bleeding."},
        category="medical",
    ),

    # ── OFFAL / ORGAN COOKING ─────────────────────────────────────────────
    Recipe(
        id="fry_liver", name="Fried Liver",
        description="Slice and fry in tallow. Rich, iron-heavy, deeply satisfying. "
                    "Best eaten fresh from the kill.",
        materials=[("liver", 1)],
        skill="cooking", difficulty=2, time_minutes=10,
        output_custom={"id": "cooked_liver", "name": "Fried Liver",
                       "weight": 0.4, "category": "food", "nutrition": 25.0,
                       "base_value": 0.12, "perishable": True, "days_until_spoil": 3,
                       "description": "Pan-fried liver. Rich and tender."},
        category="food",
        requires_fire=True,
    ),
    Recipe(
        id="roast_heart", name="Roasted Heart",
        description="Skewer and roast over coals. Dense, lean, good flavor.",
        materials=[("heart", 1)],
        skill="cooking", difficulty=2, time_minutes=15,
        output_custom={"id": "cooked_heart", "name": "Roasted Heart",
                       "weight": 0.3, "category": "food", "nutrition": 22.0,
                       "base_value": 0.10, "perishable": True, "days_until_spoil": 3,
                       "description": "Roasted heart. Firm, lean meat."},
        category="food",
        requires_fire=True,
    ),
    Recipe(
        id="fry_kidneys", name="Fried Kidneys",
        description="Split and fry in fat. Strong flavor — an acquired taste.",
        materials=[("kidneys", 1)],
        skill="cooking", difficulty=3, time_minutes=10,
        output_custom={"id": "cooked_kidneys", "name": "Fried Kidneys",
                       "weight": 0.2, "category": "food", "nutrition": 15.0,
                       "base_value": 0.08, "perishable": True, "days_until_spoil": 3,
                       "description": "Fried kidneys. Not for everyone."},
        category="food",
        requires_fire=True,
    ),
    Recipe(
        id="make_sausage", name="Frontier Sausage",
        description="Stuff chopped meat into cleaned intestines. Smoke or fry. "
                    "Uses the whole animal — nothing wasted.",
        materials=[("intestines", 1), ("fresh_venison", 1)],
        skill="cooking", difficulty=5, time_minutes=45,
        output_custom={"id": "sausage", "name": "Frontier Sausage",
                       "weight": 0.4, "category": "food", "nutrition": 30.0,
                       "base_value": 0.20, "stackable": True,
                       "perishable": True, "days_until_spoil": 7,
                       "description": "Meat stuffed in intestine casing. Smoked. Keeps well."},
        output_qty=3,
        category="food",
        requires_fire=True,
    ),
    Recipe(
        id="make_haggis", name="Trapper's Haggis",
        description="Chop organs and oats, stuff into a stomach, boil for hours. "
                    "Scottish trappers brought this recipe west.",
        materials=[("stomach_lining", 1), ("liver", 1), ("lungs", 1)],
        skill="cooking", difficulty=6, time_minutes=120,
        output_custom={"id": "haggis", "name": "Trapper's Haggis",
                       "weight": 0.5, "category": "food", "nutrition": 40.0,
                       "base_value": 0.25, "perishable": True, "days_until_spoil": 5,
                       "description": "Offal pudding boiled in a stomach. "
                                      "Sounds terrible. Tastes surprisingly good."},
        category="food",
        requires_fire=True,
    ),
    Recipe(
        id="render_tallow_from_offal", name="Render Fat from Scraps",
        description="Boil down scraps and organ trimmings to extract tallow. "
                    "Good for candles, waterproofing, and cooking.",
        materials=[("lungs", 1), ("kidneys", 1)],
        skill="cooking", difficulty=3, time_minutes=30,
        output_id="tallow", output_qty=1,
        category="food",
        requires_fire=True,
    ),
    Recipe(
        id="blood_sausage", name="Blood Sausage",
        description="Mix blood with fat and grain, stuff into intestine. "
                    "Boil until firm. Common frontier food — wastes nothing.",
        materials=[("intestines", 1), ("tallow", 1)],
        skill="cooking", difficulty=5, time_minutes=40,
        output_custom={"id": "blood_sausage", "name": "Blood Sausage",
                       "weight": 0.3, "category": "food", "nutrition": 25.0,
                       "base_value": 0.15, "stackable": True,
                       "perishable": True, "days_until_spoil": 7,
                       "description": "Dense, dark sausage. Filling and cheap to make."},
        output_qty=2,
        category="food",
        requires_fire=True,
    ),
    Recipe(
        id="stomach_water_bag", name="Stomach Water Bag",
        description="Clean and dry a stomach to make a watertight bag. "
                    "Natives and trappers used these before canteens.",
        materials=[("stomach_lining", 1)],
        skill="survival", difficulty=4, time_minutes=20,
        output_custom={"id": "stomach_bag", "name": "Stomach Water Bag",
                       "weight": 0.3, "category": "misc",
                       "base_value": 0.30,
                       "description": "A cleaned animal stomach. Holds water. "
                                      "Not pretty but it works.",
                       "extra": {"hydration_capacity": 20}},
        category="trapping",
    ),

    # ── USES FOR ORPHANED MATERIALS ──────────────────────────────────────
    Recipe(
        id="claw_necklace", name="Claw & Teeth Necklace",
        description="String bear claws or wolf teeth on sinew. "
                    "Worn as trophy and trade good.",
        materials=[("teeth_claws", 1), ("sinew", 1)],
        skill="furriery", difficulty=3, time_minutes=20,
        output_custom={"id": "claw_necklace", "name": "Claw Necklace",
                       "weight": 0.1, "category": "misc",
                       "base_value": 3.00,
                       "description": "A necklace of claws and teeth. "
                                      "Impressive to trappers and natives alike."},
        category="bonework",
    ),
    Recipe(
        id="sage_smudge", name="Sage Smudge Bundle",
        description="Bind dried sage into a smudge stick. "
                    "Burn to repel insects and purify a camp.",
        materials=[("wild_sage", 2)],
        skill="survival", difficulty=2, time_minutes=10,
        output_custom={"id": "sage_smudge", "name": "Sage Smudge Bundle",
                       "weight": 0.1, "category": "misc",
                       "base_value": 0.15, "stackable": True,
                       "description": "Dried sage bundle. Burn to keep bugs away "
                                      "and mask your scent from game."},
        category="materials",
    ),
    Recipe(
        id="fish_bait", name="Fish Bait from Guts",
        description="Cut fish guts into bait chunks. "
                    "Better than worms for big fish.",
        materials=[("fish_guts", 1)],
        skill="fishing", difficulty=1, time_minutes=5,
        output_custom={"id": "fish_bait", "name": "Fish Bait",
                       "weight": 0.1, "category": "material",
                       "base_value": 0.02, "stackable": True,
                       "perishable": True, "days_until_spoil": 2,
                       "description": "Chunks of fish gut. Irresistible to trout."},
        output_qty=3,
        category="trapping",
    ),

    # ── Water vehicles ────────────────────────────────────────────────
    Recipe(
        id="build_dugout_canoe", name="Dugout Canoe",
        description="Carve a canoe from a single large log. Days of work "
                    "with an axe. Heavy but durable.",
        materials=[("Log", 3)],
        tool_required="chop",
        skill="survival", difficulty=10, time_minutes=480,  # full day
        output_id="dugout_canoe",
        category="vehicle",
    ),
    Recipe(
        id="build_birchbark_canoe", name="Birchbark Canoe",
        description="Build a light canoe from birch bark over a cedar frame. "
                    "Requires bark, poles, and cordage. Light enough to portage.",
        materials=[("Log", 2), ("Rope (10 ft)", 2)],
        tool_required="cut",
        skill="survival", difficulty=12, time_minutes=600,  # 10 hours
        output_id="birchbark_canoe",
        category="vehicle",
    ),
]

# Index by category
# ── Append furniture recipes from furniture module ────────────────────────
try:
    from src.furniture import FURNITURE_RECIPES as _FR
    for fid, fname, fmats, fskill, fdiff, ftime, fterrain in _FR:
        RECIPES.append(Recipe(
            id=fid, name=fname,
            description=f"Build {fname.lower()} from raw materials.",
            materials=fmats,
            skill=fskill, difficulty=fdiff, time_minutes=ftime,
            output_custom={"id": fid, "name": fname, "weight": 5.0,
                           "category": "misc", "base_value": 2.0,
                           "description": f"A handmade {fname.lower()}."},
            category="furniture",
            # The terrain placement is handled by a post-craft hook
        ))
except ImportError:
    pass

RECIPE_CATEGORIES = {}
for r in RECIPES:
    RECIPE_CATEGORIES.setdefault(r.category, []).append(r)


# Items that count as equivalent for recipe matching
_MATERIAL_GROUPS = {
    "fresh_venison": {"fresh_venison", "hindquarter_meat", "shoulder_meat",
                      "rib_meat", "neck_meat", "breast_meat", "snake_meat",
                      "human_meat"},
}

def _item_matches_material(item_id: str, mat_id: str) -> bool:
    """Check if an item satisfies a recipe material requirement."""
    if item_id == mat_id:
        return True
    group = _MATERIAL_GROUPS.get(mat_id)
    return group is not None and item_id in group


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
            if _item_matches_material(item.id, mat_id):
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
            if not _item_matches_material(item.id, mat_id):
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
        if recipe.output_qty > 1:
            item.quantity = recipe.output_qty
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
