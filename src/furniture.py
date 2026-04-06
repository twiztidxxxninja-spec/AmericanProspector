"""
src/furniture.py

Furniture interaction system — sit, sleep, cook, flip tables for cover,
repair tools at the anvil, gamble, order drinks, search barrels, etc.

Each furniture terrain type maps to one or more context actions.  The engine
calls get_furniture_actions() to populate a menu, then execute_furniture_action()
to perform the chosen action and get back a message string.
"""

import random
from dataclasses import dataclass
from typing import List, Tuple, Optional

from src.local_map import LocalTerrain


# ── Terrain constant shorthand (mirrors LocalTerrain) ─────────────────────
TABLE          = LocalTerrain.TABLE           # 43
CHAIR          = LocalTerrain.CHAIR           # 44
BED            = LocalTerrain.BED             # 45
STOVE          = LocalTerrain.STOVE           # 46
BAR_COUNTER    = LocalTerrain.BAR_COUNTER     # 47
ANVIL_TILE     = LocalTerrain.ANVIL_TILE      # 48
SHELF          = LocalTerrain.SHELF           # 49
CELL_BARS      = LocalTerrain.CELL_BARS       # 50
DESK           = LocalTerrain.DESK            # 51
BARREL_TILE    = LocalTerrain.BARREL_TILE     # 52
GAMBLING_TABLE = LocalTerrain.GAMBLING_TABLE  # 53

# Overturned table — improvised cover in combat
OVERTURNED_TABLE = LocalTerrain.OVERTURNED_TABLE  # 54


# ── FurnitureAction dataclass ─────────────────────────────────────────────

@dataclass
class FurnitureAction:
    action_id: str            # unique key, e.g. "sit_chair"
    label: str                # display text shown to the player
    requires_adjacent: bool   # True = player must be next to tile, not on it


# ── Per-terrain interaction menus ─────────────────────────────────────────

FURNITURE_INTERACTIONS: dict = {
    CHAIR: [
        FurnitureAction("sit_chair", "Sit down", requires_adjacent=False),
    ],
    BED: [
        FurnitureAction("sleep_bed", "Sleep here", requires_adjacent=True),
    ],
    STOVE: [
        FurnitureAction("cook_stove", "Cook on stove", requires_adjacent=True),
    ],
    BAR_COUNTER: [
        FurnitureAction("order_drink", "Order a drink", requires_adjacent=True),
        FurnitureAction("lean_bar", "Lean on bar", requires_adjacent=True),
    ],
    BARREL_TILE: [
        FurnitureAction("search_barrel", "Search barrel", requires_adjacent=True),
        FurnitureAction("store_barrel", "Store items", requires_adjacent=True),
    ],
    TABLE: [
        FurnitureAction("flip_table", "Flip table", requires_adjacent=True),
    ],
    DESK: [
        FurnitureAction("write_desk", "Write", requires_adjacent=True),
    ],
    ANVIL_TILE: [
        FurnitureAction("repair_anvil", "Repair tools", requires_adjacent=True),
    ],
    SHELF: [
        FurnitureAction("browse_shelf", "Browse goods", requires_adjacent=True),
    ],
    GAMBLING_TABLE: [
        FurnitureAction("gamble", "Gamble", requires_adjacent=True),
    ],
}


# ── Public API ────────────────────────────────────────────────────────────

def get_furniture_actions(terrain_type: int) -> List[FurnitureAction]:
    """Return available actions for a furniture terrain type (empty list if none)."""
    return list(FURNITURE_INTERACTIONS.get(terrain_type, []))


def execute_furniture_action(action_id: str, engine, x: int, y: int) -> str:
    """
    Perform a furniture interaction and return a human-readable result message.

    Parameters
    ----------
    action_id : str
        One of the action_id values defined in FURNITURE_INTERACTIONS.
    engine : Engine
        The main game engine (provides player, time, local map, messages).
    x, y : int
        Tile coordinates of the furniture being interacted with.
    """
    player = engine.player
    lmap = engine.current_local

    # ── Sit on a chair ────────────────────────────────────────────────
    if action_id == "sit_chair":
        player.survival.fatigue = min(100.0, player.survival.fatigue + 5)
        engine.advance_time(10)
        return "You sit down and rest your legs for a spell. (+5 fatigue restored)"

    # ── Sleep in a bed ────────────────────────────────────────────────
    if action_id == "sleep_bed":
        player.survival.fatigue = min(100.0, player.survival.fatigue + 40)
        player.survival.warmth = min(100.0, player.survival.warmth + 25)
        engine.advance_time(60)
        return ("You lie down and sleep for an hour. "
                "The bedding keeps you warm. (+30 fatigue, +10 warmth)")

    # ── Cook on stove ─────────────────────────────────────────────────
    if action_id == "cook_stove":
        return _cook_on_stove(engine, player)

    # ── Order a drink at the bar ──────────────────────────────────────
    if action_id == "order_drink":
        engine.advance_time(5)
        return _order_drink(player)

    # ── Lean on bar / listen to gossip ────────────────────────────────
    if action_id == "lean_bar":
        engine.advance_time(10)
        rumors = [
            "A miner up near Placerville pulled a two-pound nugget last week.",
            "They say the Chinese miners are reworking tailings — finding gold everyone missed.",
            "Heard a grizzly killed a man on the Cosumnes. Watch yourself out there.",
            "Flour's up to a dollar a pound at the Hangtown store.",
            "Some fellow struck a vein of quartz thick with wire gold up on the Yuba.",
            "Word is the assay office in Sacramento is buying dust at $16 the ounce.",
            "A claim jumper got strung up near Rough and Ready. Justice is swift here.",
            "The stage from San Francisco got held up again. Roads ain't safe.",
        ]
        rumor = random.choice(rumors)
        return f"You lean on the bar and listen. Someone mentions: \"{rumor}\""

    # ── Search barrel ─────────────────────────────────────────────────
    if action_id == "search_barrel":
        return _search_barrel(engine, player)

    # ── Store items in barrel ─────────────────────────────────────────
    if action_id == "store_barrel":
        # Storage is handled by the inventory UI — flag that this tile is a
        # valid storage point so the engine can open the storage screen.
        return "Open the barrel for storage. (Use inventory to move items.)"

    # ── Flip table for cover ──────────────────────────────────────────
    if action_id == "flip_table":
        lmap.set_terrain(x, y, OVERTURNED_TABLE)
        return ("You heave the table onto its side! "
                "It provides partial cover. (cover value 2)")

    # ── Write at a desk ───────────────────────────────────────────────
    if action_id == "write_desk":
        engine.advance_time(15)
        return ("You sit at the desk and write. "
                "(Open journal [J] to compose a letter or diary entry.)")

    # ── Repair tools at the anvil ─────────────────────────────────────
    if action_id == "repair_anvil":
        return _repair_at_anvil(engine, player)

    # ── Browse goods on a shelf ───────────────────────────────────────
    if action_id == "browse_shelf":
        # Shelf interaction depends on context — in a shop the engine should
        # redirect to the trade screen.  Outside a shop, it is just scenery.
        return ("You look over the goods on the shelf. "
                "(If in a shop, press [T] to trade with the shopkeeper.)")

    # ── Gamble at the card table ──────────────────────────────────────
    if action_id == "gamble":
        return ("You pull up a chair at the card table. "
                "(Gambling mode — press [G] to start a game.)")

    return "Nothing happens."


# ── Internal helpers ──────────────────────────────────────────────────────

def _cook_on_stove(engine, player) -> str:
    """Find raw food in the player's inventory and cook it on the stove."""
    # Items that can be cooked and their cooked counterparts
    COOK_MAP = {
        "fresh_venison": ("cooked_venison", "Cooked Venison",
                          "Pan-fried venison steak. Filling and nourishing.", 40.0),
        "fresh_fish":    ("cooked_fish", "Cooked Fish",
                          "Fire-roasted fish. Better than raw.", 28.0),
        "beans":         ("cooked_beans", "Cooked Beans",
                          "A pot of slow-cooked beans. Hearty fare.", 25.0),
        "flour":         ("hardtack", "Hardtack",
                          "A hard, dry biscuit. Keeps indefinitely. Tastes like it.", 10.0),
    }

    from src.items import Item

    for i, item in enumerate(player.inventory):
        item_id = item.id if hasattr(item, "id") else ""
        if item_id in COOK_MAP:
            cooked_id, cooked_name, cooked_desc, nutrition = COOK_MAP[item_id]
            # Remove raw item (consume one unit)
            if hasattr(item, "quantity") and item.quantity > 1:
                item.quantity -= 1
            else:
                player.inventory.pop(i)
            # Create cooked item
            cooked = Item(
                id=cooked_id,
                name=cooked_name,
                weight=item.weight,
                category="food",
                description=cooked_desc,
                nutrition=nutrition,
            )
            player.inventory.append(cooked)
            engine.advance_time(15)
            return f"You cook the {item.name} on the stove. ({cooked_name} ready to eat.)"

    return "You have nothing to cook. (Need raw food: fresh meat, fish, beans, or flour.)"


def _order_drink(player) -> str:
    """Buy a drink at the bar counter — costs $0.25, restores thirst."""
    DRINK_COST = 0.25
    if player.cash < DRINK_COST:
        return "You can't afford a drink. (Need $0.25.)"
    player.cash -= DRINK_COST
    player.survival.thirst = min(100.0, player.survival.thirst + 20)
    return ("You pay two bits and the barkeep pours you a whiskey. "
            "(+20 thirst, -$0.25)")


def _search_barrel(engine, player) -> str:
    """Rummage through a barrel — random chance of finding supplies."""
    from src.items import Item

    BARREL_LOOT = [
        ("hardtack",  "Hardtack",         0.1, "food",     "A hard, dry biscuit."),
        ("rope_10ft", "Rope (10 ft)",     1.0, "material", "Ten feet of hemp rope."),
        ("tallow",    "Tallow",           1.5, "material", "Rendered animal fat."),
        ("nails",     "Nails",            0.5, "material", "A handful of iron nails."),
        ("flour",     "Flour",            2.0, "food",     "Sack of wheat flour."),
        ("beans",     "Beans",            1.0, "food",     "Dried beans."),
        ("salt",      "Salt",             0.5, "material", "A small pouch of salt."),
    ]

    roll = random.random()
    if roll < 0.35:
        # Nothing useful
        return "The barrel is empty — just dust and splinters."
    if roll < 0.55:
        return "Nothing but stale air and a dead mouse."

    # Found something
    loot_id, loot_name, weight, category, desc = random.choice(BARREL_LOOT)
    found = Item(id=loot_id, name=loot_name, weight=weight,
                 category=category, description=desc)
    player.inventory.append(found)
    engine.advance_time(5)
    return f"You rummage through the barrel and find: {loot_name}."


def _repair_at_anvil(engine, player) -> str:
    """Pick the most damaged tool in inventory and repair it at the anvil."""
    eng_skill = player.skills.get("engineering", 0)

    # Find the tool with lowest condition
    best_idx = -1
    worst_condition = 100.0
    for i, item in enumerate(player.inventory):
        if hasattr(item, "tool_tags") and item.tool_tags:
            if item.condition < worst_condition:
                worst_condition = item.condition
                best_idx = i

    if best_idx < 0:
        return "You have no damaged tools to repair."

    tool = player.inventory[best_idx]
    if tool.condition >= 100.0:
        return f"Your {tool.name} is already in fine shape."

    repair_amount = 20 + eng_skill * 3
    old_cond = tool.condition
    tool.condition = min(100.0, tool.condition + repair_amount)
    engine.advance_time(20)

    # Small engineering XP for the work
    if hasattr(player, "skill_xp"):
        player.skill_xp["engineering"] = player.skill_xp.get("engineering", 0.0) + 2.0

    return (f"You hammer and true up your {tool.name} on the anvil. "
            f"Condition {old_cond:.0f} -> {tool.condition:.0f}. "
            f"(+{repair_amount} from engineering {eng_skill})")


# ── Furniture crafting recipes ────────────────────────────────────────────
# Format: (recipe_id, display_name, materials, skill, difficulty, time_min, terrain_placed)
# These can be imported and appended to the main RECIPES list in crafting.py.

FURNITURE_RECIPES: List[Tuple] = [
    ("craft_table",   "Build a Table",       [("plank", 4)],                   "engineering", 6, 30, TABLE),
    ("craft_chair",   "Build a Chair",       [("plank", 2)],                   "engineering", 4, 20, CHAIR),
    ("craft_bed",     "Build a Bed Frame",   [("plank", 4), ("rope_10ft", 1)], "engineering", 7, 45, BED),
    ("craft_barrel",  "Build a Barrel",      [("plank", 6)],                   "engineering", 8, 40, BARREL_TILE),
    ("craft_shelf",   "Build a Shelf",       [("plank", 3)],                   "engineering", 5, 25, SHELF),
    ("craft_desk",    "Build a Writing Desk",[("plank", 4)],                   "engineering", 7, 35, DESK),
]
