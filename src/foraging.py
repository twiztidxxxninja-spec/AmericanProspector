"""
src/foraging.py

Knowledge-based foraging system.  Players don't have a magic skill level
that identifies plants — they learn individual plants through experience,
teaching, or trial and error.  The ``player.knowledge`` dict stores learned
plant IDs (value 1 = recognised).

Main entry points:
    forage_area()        — scan nearby tiles and return found plants
    learn_from_eating()  — after eating safely, maybe learn to ID the plant
    learn_from_npc()     — spending time with a knowledgeable NPC
    init_background_plants() — seed starting knowledge from background
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    import random as _rng_module
    from src.local_map import LocalMap
    from src.player import Player


# ── Terrain constants (mirrors local_map.LocalTerrain) ────────────────────────

GROUND      = 0
GRASS       = 1
FOREST      = 2
ROCK        = 3
WATER       = 4
GRAVEL_BAR  = 5
BEDROCK     = 6
MUD         = 7
SAND        = 8
BRUSH       = 9
PINE        = 13
OAK         = 14
ASPEN       = 15
JUNIPER     = 16
CEDAR       = 17
MAPLE       = 18
CHESTNUT    = 19
HICKORY     = 20
CYPRESS     = 21
MAGNOLIA    = 22
BEAVER_POND = 91

TREE_TERRAINS:  Set[int] = {FOREST, PINE, OAK, ASPEN, JUNIPER, CEDAR,
                             MAPLE, CHESTNUT, HICKORY, CYPRESS, MAGNOLIA}
GRASS_TERRAINS: Set[int] = {GROUND, GRASS, BRUSH}
WATER_TERRAINS: Set[int] = {WATER, BEAVER_POND}

# Radius (in tiles) used to check for nearby terrain / water.
SCAN_RADIUS = 3

# Maximum items returned per single forage action.
MAX_FORAGE_RESULTS = 3


# ── Master plant table ────────────────────────────────────────────────────────

FORAGEABLE_PLANTS: List[Dict] = [
    # ── Always identifiable ──────────────────────────────────────────────
    {
        "id": "pine_needles",
        "name": "Pine Needles",
        "terrain": TREE_TERRAINS,
        "near_water": False,
        "near_terrain": {PINE, CEDAR, JUNIPER},
        "seasons": {"spring", "summer", "fall", "winter"},
        "chance": 0.6,
        "safe": True,
        "unknown_as": "",
        "region_hint": "",
    },
    {
        "id": "cattail_root",
        "name": "Cattail Root",
        "terrain": GRASS_TERRAINS | {MUD},
        "near_water": True,
        "near_terrain": None,
        "seasons": {"spring", "summer", "fall", "winter"},
        "chance": 0.4,
        "safe": True,
        "unknown_as": "",
        "region_hint": "",
    },
    {
        "id": "wild_onion",
        "name": "Wild Onion",
        "terrain": GRASS_TERRAINS,
        "near_water": False,
        "near_terrain": None,
        "seasons": {"spring", "summer", "fall"},
        "chance": 0.35,
        "safe": True,
        "unknown_as": "",
        "region_hint": "",
    },
    {
        "id": "wild_mint",
        "name": "Wild Mint",
        "terrain": GRASS_TERRAINS | {MUD},
        "near_water": True,
        "near_terrain": None,
        "seasons": {"spring", "summer"},
        "chance": 0.3,
        "safe": True,
        "unknown_as": "",
        "region_hint": "",
    },
    {
        "id": "wild_sage",
        "name": "Wild Sage",
        "terrain": {GROUND, SAND, BRUSH},
        "near_water": False,
        "near_terrain": None,
        "seasons": {"summer", "fall"},
        "chance": 0.25,
        "safe": True,
        "unknown_as": "",
        "region_hint": "",
    },
    {
        "id": "yarrow",
        "name": "Yarrow",
        "terrain": GRASS_TERRAINS,
        "near_water": False,
        "near_terrain": None,
        "seasons": {"spring", "summer"},
        "chance": 0.2,
        "safe": True,
        "unknown_as": "",
        "region_hint": "",
    },

    # ── Berries ──────────────────────────────────────────────────────────
    {
        "id": "wild_berries",
        "name": "Wild Berries",
        "terrain": TREE_TERRAINS,
        "near_water": False,
        "near_terrain": None,
        "seasons": {"summer", "fall"},
        "chance": 0.5,
        "safe": True,
        "unknown_as": "unknown_berries",
        "region_hint": "",
    },
    {
        "id": "chokecherry",
        "name": "Chokecherries",
        "terrain": TREE_TERRAINS,
        "near_water": True,
        "near_terrain": None,
        "seasons": {"summer", "fall"},
        "chance": 0.35,
        "safe": True,
        "unknown_as": "unknown_berries",
        "region_hint": "",
    },
    {
        "id": "serviceberry",
        "name": "Serviceberries",
        "terrain": TREE_TERRAINS,
        "near_water": False,
        "near_terrain": None,
        "seasons": {"summer"},
        "chance": 0.3,
        "safe": True,
        "unknown_as": "unknown_berries",
        "region_hint": "rocky",
    },
    {
        "id": "rose_hips",
        "name": "Rose Hips",
        "terrain": {BRUSH} | TREE_TERRAINS,
        "near_water": False,
        "near_terrain": None,
        "seasons": {"fall"},
        "chance": 0.4,
        "safe": True,
        "unknown_as": "unknown_berries",
        "region_hint": "",
    },
    {
        "id": "thimbleberry",
        "name": "Thimbleberries",
        "terrain": TREE_TERRAINS,
        "near_water": False,
        "near_terrain": None,
        "seasons": {"summer"},
        "chance": 0.25,
        "safe": True,
        "unknown_as": "unknown_berries",
        "region_hint": "pacific",
    },
    {
        "id": "salal_berries",
        "name": "Salal Berries",
        "terrain": TREE_TERRAINS,
        "near_water": False,
        "near_terrain": None,
        "seasons": {"summer", "fall"},
        "chance": 0.3,
        "safe": True,
        "unknown_as": "unknown_berries",
        "region_hint": "pacific",
    },
    {
        "id": "oregon_grape",
        "name": "Oregon Grape Berries",
        "terrain": TREE_TERRAINS,
        "near_water": False,
        "near_terrain": None,
        "seasons": {"fall"},
        "chance": 0.25,
        "safe": True,
        "unknown_as": "unknown_berries",
        "region_hint": "pacific",
    },
    {
        "id": "manzanita_berries",
        "name": "Manzanita Berries",
        "terrain": {BRUSH, JUNIPER},
        "near_water": False,
        "near_terrain": None,
        "seasons": {"summer", "fall"},
        "chance": 0.2,
        "safe": True,
        "unknown_as": "unknown_berries",
        "region_hint": "california",
    },
    {
        "id": "pawpaw",
        "name": "Pawpaw Fruit",
        "terrain": TREE_TERRAINS,
        "near_water": False,
        "near_terrain": None,
        "seasons": {"fall"},
        "chance": 0.2,
        "safe": True,
        "unknown_as": "unknown_berries",
        "region_hint": "eastern",
    },
    {
        "id": "persimmon",
        "name": "Wild Persimmon",
        "terrain": TREE_TERRAINS,
        "near_water": False,
        "near_terrain": None,
        "seasons": {"fall"},
        "chance": 0.2,
        "safe": True,
        "unknown_as": "unknown_berries",
        "region_hint": "eastern",
    },
    {
        "id": "baneberry",
        "name": "White Baneberry",
        "terrain": TREE_TERRAINS,
        "near_water": False,
        "near_terrain": None,
        "seasons": {"summer", "fall"},
        "chance": 0.1,
        "safe": False,
        "unknown_as": "unknown_berries",
        "region_hint": "",
    },
    {
        "id": "nightshade_berries",
        "name": "Nightshade Berries",
        "terrain": {GRASS, GROUND, BRUSH},
        "near_water": False,
        "near_terrain": None,
        "seasons": {"summer", "fall"},
        "chance": 0.1,
        "safe": False,
        "unknown_as": "unknown_berries",
        "region_hint": "",
    },
    {
        "id": "pokeweed",
        "name": "Pokeweed Berries",
        "terrain": TREE_TERRAINS | GRASS_TERRAINS,
        "near_water": False,
        "near_terrain": None,
        "seasons": {"summer", "fall"},
        "chance": 0.08,
        "safe": False,
        "unknown_as": "unknown_berries",
        "region_hint": "",
    },

    # ── Mushrooms ────────────────────────────────────────────────────────
    {
        "id": "morel_mushroom",
        "name": "Morel Mushroom",
        "terrain": TREE_TERRAINS,
        "near_water": False,
        "near_terrain": None,
        "seasons": {"spring"},
        "chance": 0.2,
        "safe": True,
        "unknown_as": "unknown_mushroom",
        "region_hint": "",
    },
    {
        "id": "chanterelle",
        "name": "Pacific Golden Chanterelle",
        "terrain": {FOREST, PINE, CEDAR, JUNIPER},
        "near_water": False,
        "near_terrain": None,
        "seasons": {"summer", "fall"},
        "chance": 0.2,
        "safe": True,
        "unknown_as": "unknown_mushroom",
        "region_hint": "",
    },
    {
        "id": "puffball_mushroom",
        "name": "Giant Puffball",
        "terrain": GRASS_TERRAINS | TREE_TERRAINS,
        "near_water": False,
        "near_terrain": None,
        "seasons": {"summer", "fall"},
        "chance": 0.15,
        "safe": True,
        "unknown_as": "unknown_mushroom",
        "region_hint": "",
    },
    {
        "id": "oyster_mushroom",
        "name": "Oyster Mushroom",
        "terrain": {FOREST, OAK, MAPLE, CHESTNUT, HICKORY, MAGNOLIA},
        "near_water": False,
        "near_terrain": None,
        "seasons": {"fall"},
        "chance": 0.15,
        "safe": True,
        "unknown_as": "unknown_mushroom",
        "region_hint": "",
    },
    {
        "id": "destroying_angel",
        "name": "Destroying Angel",
        "terrain": TREE_TERRAINS,
        "near_water": False,
        "near_terrain": None,
        "seasons": {"summer", "fall"},
        "chance": 0.08,
        "safe": False,
        "unknown_as": "unknown_mushroom",
        "region_hint": "",
    },

    # ── Roots / nuts / greens ────────────────────────────────────────────
    {
        "id": "wild_turnip",
        "name": "Wild Turnip",
        "terrain": GRASS_TERRAINS,
        "near_water": False,
        "near_terrain": None,
        "seasons": {"summer", "fall"},
        "chance": 0.3,
        "safe": True,
        "unknown_as": "",
        "region_hint": "",
    },
    {
        "id": "camas_root",
        "name": "Camas Root",
        "terrain": {GRASS},
        "near_water": True,
        "near_terrain": None,
        "seasons": {"spring", "summer"},
        "chance": 0.2,
        "safe": True,
        "unknown_as": "",
        "region_hint": "rocky",
    },
    {
        "id": "bitterroot",
        "name": "Bitterroot",
        "terrain": {GRASS, GROUND},
        "near_water": False,
        "near_terrain": None,
        "seasons": {"spring"},
        "chance": 0.15,
        "safe": True,
        "unknown_as": "",
        "region_hint": "rocky",
    },
    {
        "id": "acorns",
        "name": "Acorns",
        "terrain": TREE_TERRAINS,
        "near_water": False,
        "near_terrain": {OAK},
        "seasons": {"fall"},
        "chance": 0.5,
        "safe": True,
        "unknown_as": "",
        "region_hint": "",
    },
    {
        "id": "black_walnut",
        "name": "Black Walnuts",
        "terrain": TREE_TERRAINS,
        "near_water": False,
        "near_terrain": None,
        "seasons": {"fall"},
        "chance": 0.2,
        "safe": True,
        "unknown_as": "",
        "region_hint": "eastern",
    },
    {
        "id": "hickory_nut",
        "name": "Hickory Nuts",
        "terrain": TREE_TERRAINS,
        "near_water": False,
        "near_terrain": None,
        "seasons": {"fall"},
        "chance": 0.2,
        "safe": True,
        "unknown_as": "",
        "region_hint": "eastern",
    },
    {
        "id": "pinon_nuts",
        "name": "Pinon Nuts",
        "terrain": TREE_TERRAINS,
        "near_water": False,
        "near_terrain": {JUNIPER, PINE},
        "seasons": {"fall"},
        "chance": 0.25,
        "safe": True,
        "unknown_as": "",
        "region_hint": "rocky",
    },
    {
        "id": "prickly_pear",
        "name": "Prickly Pear Fruit",
        "terrain": {SAND, GROUND, BRUSH},
        "near_water": False,
        "near_terrain": None,
        "seasons": {"summer", "fall"},
        "chance": 0.2,
        "safe": True,
        "unknown_as": "",
        "region_hint": "",
    },
    {
        "id": "ramps",
        "name": "Ramps (Wild Leek)",
        "terrain": {FOREST, OAK, MAPLE, CHESTNUT, HICKORY, MAGNOLIA},
        "near_water": False,
        "near_terrain": None,
        "seasons": {"spring"},
        "chance": 0.2,
        "safe": True,
        "unknown_as": "",
        "region_hint": "eastern",
    },
    {
        "id": "watercress",
        "name": "Watercress",
        "terrain": GRASS_TERRAINS | {MUD},
        "near_water": True,
        "near_terrain": None,
        "seasons": {"spring", "summer"},
        "chance": 0.4,
        "safe": True,
        "unknown_as": "",
        "region_hint": "",
    },
    {
        "id": "wild_carrot",
        "name": "Wild Carrot",
        "terrain": GRASS_TERRAINS,
        "near_water": False,
        "near_terrain": None,
        "seasons": {"summer"},
        "chance": 0.15,
        "safe": True,
        "unknown_as": "",
        "region_hint": "",
    },
    {
        "id": "water_hemlock",
        "name": "Water Hemlock Root",
        "terrain": GRASS_TERRAINS | {MUD},
        "near_water": True,
        "near_terrain": None,
        "seasons": {"spring", "summer"},
        "chance": 0.05,
        "safe": False,
        "unknown_as": "",
        "region_hint": "",
    },
]

# Fast lookup by item id.
_PLANT_BY_ID: Dict[str, Dict] = {p["id"]: p for p in FORAGEABLE_PLANTS}


# ── Background starting knowledge ────────────────────────────────────────────

BACKGROUND_PLANTS: Dict[str, List[str]] = {
    "mountain_man": [
        "pine_needles", "chokecherry", "cattail_root", "wild_onion",
        "serviceberry", "camas_root", "bitterroot", "morel_mushroom",
    ],
    "voyageur": [
        "pine_needles", "wild_onion", "cattail_root", "wild_mint",
        "ramps", "chanterelle",
    ],
    "company_man": [
        "pine_needles", "wild_onion",
    ],
    "forty_niner": [
        "wild_berries", "wild_onion", "wild_mint",
    ],
    "soldier": [
        "pine_needles", "cattail_root", "yarrow",
    ],
    "trader": [
        "wild_berries", "wild_onion", "wild_mint",
    ],
    "homesteader": [
        "wild_berries", "wild_onion", "wild_carrot", "ramps",
        "pawpaw", "persimmon", "hickory_nut", "black_walnut",
        "morel_mushroom", "chanterelle",
    ],
    "scholar": [
        "yarrow", "wild_mint",
    ],
    "assayer": [
        "pine_needles",
    ],
}


def init_background_plants(player: "Player", background_id: str) -> None:
    """Seed *player.knowledge* with plants known from their background."""
    for plant_id in BACKGROUND_PLANTS.get(background_id, []):
        player.knowledge[plant_id] = 1


# ── Region matching ──────────────────────────────────────────────────────────

# Map region_hint keywords to substrings found in region names from regions.py.
_REGION_KEYWORDS: Dict[str, List[str]] = {
    "rocky":      ["Rocky", "Montana", "Idaho", "Black Hills", "Great Basin",
                   "Nevada"],
    "pacific":    ["Pacific Northwest", "Alaska"],
    "california": ["California", "Sierra Nevada"],
    "eastern":    ["Appalachian", "Gulf Coast", "Great Plains"],
}


def _region_matches(region_name: str, hint: str) -> bool:
    """Return True if *region_name* satisfies the plant's *region_hint*."""
    if not hint:
        return True  # universal plant
    for substr in _REGION_KEYWORDS.get(hint, []):
        if substr.lower() in region_name.lower():
            return True
    return False


# ── Terrain scanning helpers ─────────────────────────────────────────────────

def _nearby_terrains(lmap: "LocalMap", px: int, py: int,
                     radius: int = SCAN_RADIUS) -> Set[int]:
    """Return the set of terrain types within *radius* of (px, py)."""
    terrains: Set[int] = set()
    for dy in range(-radius, radius + 1):
        ny = py + dy
        for dx in range(-radius, radius + 1):
            nx = px + dx
            if lmap.in_bounds(nx, ny):
                terrains.add(lmap.tiles[ny][nx].terrain)
    return terrains


def _has_water_nearby(nearby: Set[int]) -> bool:
    """Check whether any water terrain appears in *nearby*."""
    return bool(nearby & WATER_TERRAINS)


# ── Main foraging function ───────────────────────────────────────────────────

def forage_area(
    player: "Player",
    lmap: "LocalMap",
    px: int,
    py: int,
    season: str,
    rng: "_rng_module.Random",
) -> List[Tuple[str, str, bool]]:
    """Forage for plants near the player's position.

    Returns a list of ``(item_id, message, learned_new)`` tuples.

    * If the player knows a plant (``item_id in player.knowledge``), they
      receive the named item with a recognition message.
    * If they don't know it but the plant has *unknown_as*, they receive the
      generic unknown version.
    * If the plant has no *unknown_as* (always identifiable), they get it
      directly regardless of knowledge.
    * *learned_new* is always ``False`` here — learning happens when the
      player eats the item safely (see :func:`learn_from_eating`).

    At most :data:`MAX_FORAGE_RESULTS` items are returned per action.
    """
    standing_terrain: int = lmap.tiles[py][px].terrain
    nearby = _nearby_terrains(lmap, px, py)
    water_nearby = _has_water_nearby(nearby)

    region_name: str = getattr(lmap, "_region_name", "")

    results: List[Tuple[str, str, bool]] = []

    # Build a shuffled candidate list so we don't always favour the same
    # plants when the cap is reached.
    candidates = list(FORAGEABLE_PLANTS)
    rng.shuffle(candidates)

    for plant in candidates:
        if len(results) >= MAX_FORAGE_RESULTS:
            break

        # --- Season ---
        if season not in plant["seasons"]:
            continue

        # --- Region ---
        if not _region_matches(region_name, plant["region_hint"]):
            continue

        # --- Terrain: player must be on or adjacent to a valid terrain ---
        if not (plant["terrain"] & nearby):
            continue

        # --- Near water requirement ---
        if plant["near_water"] and not water_nearby:
            continue

        # --- Near specific terrain requirement ---
        near_req = plant["near_terrain"]
        if near_req is not None and not (near_req & nearby):
            continue

        # --- Probability roll ---
        if rng.random() >= plant["chance"]:
            continue

        # --- Determine what the player actually gets ---
        plant_id: str = plant["id"]
        plant_name: str = plant["name"]
        unknown_as: str = plant["unknown_as"]

        if plant_id in player.knowledge:
            # Player recognises this plant.
            item_id = plant_id
            msg = f"You recognize {plant_name.lower()}."
        elif unknown_as:
            # Player doesn't know it — give the generic version.
            item_id = unknown_as
            if "mushroom" in unknown_as:
                msg = "A mushroom growing at the base of a tree. You don't recognize it."
            else:
                msg = "Berries on a bush. You don't recognize them."
        else:
            # Always identifiable (distinctive enough that anyone can tell).
            item_id = plant_id
            msg = f"You find {plant_name.lower()}."

        results.append((item_id, msg, False))

    return results


# ── Learning ─────────────────────────────────────────────────────────────────

def learn_from_eating(player: "Player", item_id: str) -> Optional[str]:
    """If the player eats something safely, they might learn to identify it.

    Called by the engine after consuming a foraged item without getting sick.
    Returns a message string if new knowledge was gained, else ``None``.
    """
    plant = _PLANT_BY_ID.get(item_id)
    if plant is None:
        return None
    if not plant["safe"]:
        return None
    if item_id in player.knowledge:
        return None  # already known
    player.knowledge[item_id] = 1
    return "You'll remember what this plant looks like."


def learn_from_npc(
    player: "Player",
    npc_tribe_or_bg: str,
    rng: "_rng_module.Random",
) -> List[str]:
    """Teach the player 1-2 plants they don't yet know.

    *npc_tribe_or_bg* is a region-flavoured keyword (e.g. ``"rocky"``,
    ``"pacific"``, ``"eastern"``) or a background id.  Plants whose
    *region_hint* matches the keyword are preferred; universal plants fill
    any remaining slots.

    Returns a list of human-readable messages for each plant learned.
    """
    # Determine region hint from the NPC context.  If it matches a
    # background id, map it to a likely region; otherwise treat it as a
    # region keyword directly.
    bg_to_region: Dict[str, str] = {
        "mountain_man": "rocky",
        "voyageur":     "rocky",
        "homesteader":  "eastern",
    }
    hint = bg_to_region.get(npc_tribe_or_bg, npc_tribe_or_bg)

    # Collect plants the player doesn't know yet, preferring regional ones.
    regional: List[Dict] = []
    universal: List[Dict] = []
    for plant in FORAGEABLE_PLANTS:
        if plant["id"] in player.knowledge:
            continue
        if not plant["safe"]:
            continue  # NPCs won't teach you to eat poison
        ph = plant["region_hint"]
        if ph == hint:
            regional.append(plant)
        elif ph == "":
            universal.append(plant)

    rng.shuffle(regional)
    rng.shuffle(universal)

    pool = regional + universal
    teach_count = min(rng.randint(1, 2), len(pool))

    messages: List[str] = []
    for plant in pool[:teach_count]:
        player.knowledge[plant["id"]] = 1
        messages.append(
            f"You learn to identify {plant['name'].lower()}."
        )

    return messages
