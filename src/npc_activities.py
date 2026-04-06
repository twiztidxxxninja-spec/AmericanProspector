"""
src/npc_activities.py

NPC goal-driven behavior system.  Each NPC picks an activity based on
occupation and time-of-day period, walks toward the appropriate terrain,
and broadcasts flavor text when the player is nearby.

Periods (set by the time system):
    dawn        ~05:00-07:00
    morning     ~07:00-12:00
    afternoon   ~12:00-17:00
    dusk        ~17:00-19:00
    night       ~19:00-05:00
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.local_map import LocalTerrain


# ── Activity definition ────────────────────────────────────────────────────

@dataclass
class ActivityDef:
    """A single activity an NPC can perform."""
    activity_id: str            # pan_gold, tend_shop, patrol, chop_wood, etc.
    occupation: str             # which occupation uses this
    period: str                 # dawn | morning | afternoon | dusk | night
    target_terrain: int = -1    # LocalTerrain type to walk toward (-1 = any)
    duration_minutes: int = 30
    messages: List[str] = field(default_factory=list)  # flavor text


# ── Activity tables ────────────────────────────────────────────────────────
# Mapping:  occupation -> period -> [ActivityDef, ...]
# An NPC picks one at random from the list for the matching period.

def _a(aid, occ, per, terrain=-1, dur=30, msgs=None):
    """Shorthand constructor."""
    return ActivityDef(aid, occ, per, terrain, dur, msgs or [])


OCCUPATION_ACTIVITIES: Dict[str, Dict[str, List[ActivityDef]]] = {

    # ── Prospector ──────────────────────────────────────────────────────
    "Prospector": {
        "dawn": [
            _a("wake_up", "Prospector", "dawn", LocalTerrain.BED, 15,
               ["stretches and yawns", "rolls up a bedroll"]),
        ],
        "morning": [
            _a("pan_gold", "Prospector", "morning", LocalTerrain.WATER, 45,
               ["squats by the water, swirling a pan",
                "sifts through gravel with calloused hands",
                "peers intently at the pan's rim"]),
            _a("pan_gold_bar", "Prospector", "morning",
               LocalTerrain.GRAVEL_BAR, 45,
               ["shovels gravel into a pan",
                "works the edge of a gravel bar"]),
        ],
        "afternoon": [
            _a("pan_gold", "Prospector", "afternoon", LocalTerrain.WATER, 45,
               ["pans with a determined frown",
                "washes another load of gravel"]),
            _a("pan_gold_bar", "Prospector", "afternoon",
               LocalTerrain.GRAVEL_BAR, 45,
               ["digs at the gravel bar",
                "scrapes bedrock crevices with a knife"]),
        ],
        "dusk": [
            _a("rest", "Prospector", "dusk", LocalTerrain.CHAIR, 30,
               ["sits down, rubbing sore shoulders",
                "eats a tin of beans by the fire"]),
        ],
        "night": [
            _a("sleep", "Prospector", "night", LocalTerrain.BED, 60,
               ["snores softly"]),
        ],
    },

    # ── Merchant ────────────────────────────────────────────────────────
    "Merchant": {
        "dawn": [
            _a("open_shop", "Merchant", "dawn", LocalTerrain.SHELF, 15,
               ["unlocks the store", "sets out the day's wares"]),
        ],
        "morning": [
            _a("tend_shop", "Merchant", "morning",
               LocalTerrain.SHELF, 60,
               ["arranges goods on a shelf",
                "counts inventory with a pencil",
                "polishes a glass display case"]),
        ],
        "afternoon": [
            _a("tend_shop", "Merchant", "afternoon",
               LocalTerrain.SHELF, 60,
               ["adjusts prices on a chalkboard",
                "weighs flour on a balance scale",
                "chats with a customer"]),
        ],
        "dusk": [
            _a("close_shop", "Merchant", "dusk", LocalTerrain.DESK, 20,
               ["tallies the day's receipts",
                "locks the cash drawer"]),
        ],
        "night": [
            _a("sleep", "Merchant", "night", LocalTerrain.BED, 60,
               ["rests above the store"]),
        ],
    },

    # ── Sheriff ─────────────────────────────────────────────────────────
    "Sheriff": {
        "dawn": [
            _a("wake_up", "Sheriff", "dawn", LocalTerrain.BED, 15,
               ["buckles on a gunbelt"]),
        ],
        "morning": [
            _a("patrol", "Sheriff", "morning", -1, 60,
               ["walks the main street, scanning faces",
                "tips a hat at a passing miner",
                "checks doors and windows along the road"]),
        ],
        "afternoon": [
            _a("patrol", "Sheriff", "afternoon", -1, 60,
               ["patrols the outskirts of town",
                "stops to question a stranger",
                "leans on a post, watching the crowd"]),
        ],
        "dusk": [
            _a("return_office", "Sheriff", "dusk", LocalTerrain.DESK, 30,
               ["returns to the office",
                "sits behind the desk, cleaning a revolver"]),
        ],
        "night": [
            _a("sleep", "Sheriff", "night", LocalTerrain.BED, 60,
               ["dozes lightly, one ear open"]),
        ],
    },

    # ── Blacksmith ──────────────────────────────────────────────────────
    "Blacksmith": {
        "dawn": [
            _a("stoke_forge", "Blacksmith", "dawn",
               LocalTerrain.ANVIL_TILE, 20,
               ["pumps the bellows, sparks fly"]),
        ],
        "morning": [
            _a("forge_work", "Blacksmith", "morning",
               LocalTerrain.ANVIL_TILE, 60,
               ["hammers a red-hot horseshoe",
                "shapes a pickaxe head on the anvil",
                "plunges glowing metal into water with a hiss"]),
        ],
        "afternoon": [
            _a("forge_work", "Blacksmith", "afternoon",
               LocalTerrain.ANVIL_TILE, 60,
               ["grinds a blade on a whetstone",
                "repairs a broken wagon hitch",
                "bends an iron rod into shape"]),
        ],
        "dusk": [
            _a("rest", "Blacksmith", "dusk", LocalTerrain.CHAIR, 30,
               ["wipes soot from his face",
                "drinks water from a ladle"]),
        ],
        "night": [
            _a("sleep", "Blacksmith", "night", LocalTerrain.BED, 60,
               ["sleeps near the cooling forge"]),
        ],
    },

    # ── Barber ──────────────────────────────────────────────────────────
    "Barber": {
        "morning": [
            _a("tend_shop", "Barber", "morning", LocalTerrain.CHAIR, 45,
               ["strops a razor on leather",
                "trims a miner's beard",
                "sweeps hair clippings from the floor"]),
        ],
        "afternoon": [
            _a("tend_shop", "Barber", "afternoon", LocalTerrain.CHAIR, 45,
               ["pulls a bad tooth with pliers",
                "applies a hot towel to a customer"]),
        ],
        "night": [
            _a("sleep", "Barber", "night", LocalTerrain.BED, 60,
               ["rests after a day of shaves and tooth-pulls"]),
        ],
    },

    # ── Doctor ──────────────────────────────────────────────────────────
    "Doctor": {
        "morning": [
            _a("tend_shop", "Doctor", "morning", LocalTerrain.DESK, 45,
               ["reads a medical journal",
                "mixes a tincture of laudanum",
                "bandages a patient's hand"]),
        ],
        "afternoon": [
            _a("tend_shop", "Doctor", "afternoon", LocalTerrain.DESK, 45,
               ["examines a coughing miner",
                "writes a prescription with careful hand"]),
        ],
        "night": [
            _a("sleep", "Doctor", "night", LocalTerrain.BED, 60,
               ["sleeps above the surgery"]),
        ],
    },

    # ── Saloon Keeper ───────────────────────────────────────────────────
    "Saloon Keeper": {
        "morning": [
            _a("clean_saloon", "Saloon Keeper", "morning",
               LocalTerrain.BAR_COUNTER, 30,
               ["sweeps sawdust off the floor",
                "wipes down the bar with a rag"]),
        ],
        "afternoon": [
            _a("tend_bar", "Saloon Keeper", "afternoon",
               LocalTerrain.BAR_COUNTER, 60,
               ["pours whiskey for an early drinker",
                "polishes a glass behind the bar",
                "refills the beer barrel"]),
        ],
        "dusk": [
            _a("tend_bar", "Saloon Keeper", "dusk",
               LocalTerrain.BAR_COUNTER, 60,
               ["pours drinks as the crowd thickens",
                "breaks up an argument between miners"]),
        ],
        "night": [
            _a("tend_bar", "Saloon Keeper", "night",
               LocalTerrain.BAR_COUNTER, 60,
               ["serves the late crowd",
                "collects payment from a drunken card player",
                "kicks a passed-out man toward the door"]),
        ],
    },

    # ── Lumberjack (alias for the game: Carpenter doing wood work) ─────
    "Carpenter": {
        "dawn": [
            _a("wake_up", "Carpenter", "dawn", LocalTerrain.BED, 15,
               ["shoulders an axe"]),
        ],
        "morning": [
            _a("chop_wood", "Carpenter", "morning", LocalTerrain.PINE, 60,
               ["chops at a pine tree with steady swings",
                "notches a tree trunk, gauging the fall"]),
            _a("chop_wood", "Carpenter", "morning", LocalTerrain.OAK, 60,
               ["hacks at an oak, chips flying",
                "measures a straight trunk for lumber"]),
            _a("chop_wood", "Carpenter", "morning", LocalTerrain.CEDAR, 60,
               ["fells a cedar, fragrant chips scattering"]),
        ],
        "afternoon": [
            _a("chop_wood", "Carpenter", "afternoon", LocalTerrain.PINE, 60,
               ["bucks a fallen log into rounds",
                "stacks split wood in neat rows"]),
            _a("chop_wood", "Carpenter", "afternoon", LocalTerrain.OAK, 60,
               ["trims branches from a felled oak"]),
            _a("chop_wood", "Carpenter", "afternoon", LocalTerrain.CEDAR, 60,
               ["splits cedar shakes for roofing"]),
        ],
        "dusk": [
            _a("rest", "Carpenter", "dusk", LocalTerrain.CHAIR, 30,
               ["stretches aching arms",
                "sharpens an axe blade by firelight"]),
        ],
        "night": [
            _a("sleep", "Carpenter", "night", LocalTerrain.BED, 60,
               ["sleeps the sleep of honest labor"]),
        ],
    },

    # ── Cook ────────────────────────────────────────────────────────────
    "Cook": {
        "dawn": [
            _a("prepare_food", "Cook", "dawn", LocalTerrain.STOVE, 30,
               ["kindles the cookfire",
                "puts a pot of coffee on the stove"]),
        ],
        "morning": [
            _a("prepare_food", "Cook", "morning", LocalTerrain.STOVE, 45,
               ["fries bacon in a cast-iron skillet",
                "kneads dough for biscuits"]),
        ],
        "afternoon": [
            _a("prepare_food", "Cook", "afternoon", LocalTerrain.STOVE, 45,
               ["stirs a pot of beans",
                "rolls out pie crust"]),
        ],
        "night": [
            _a("sleep", "Cook", "night", LocalTerrain.BED, 60,
               ["snores near the kitchen"]),
        ],
    },

    # ── Gambler ─────────────────────────────────────────────────────────
    "Gambler": {
        "morning": [
            _a("rest", "Gambler", "morning", LocalTerrain.BED, 60,
               ["sleeps off last night's whiskey"]),
        ],
        "afternoon": [
            _a("gamble", "Gambler", "afternoon",
               LocalTerrain.GAMBLING_TABLE, 60,
               ["shuffles a deck with practiced fingers",
                "fans cards on the table"]),
        ],
        "dusk": [
            _a("gamble", "Gambler", "dusk",
               LocalTerrain.GAMBLING_TABLE, 60,
               ["deals faro to eager miners",
                "slides chips across the felt"]),
        ],
        "night": [
            _a("gamble", "Gambler", "night",
               LocalTerrain.GAMBLING_TABLE, 60,
               ["plays poker by lamplight",
                "rakes in a pile of coins"]),
        ],
    },

    # ── Hunter ──────────────────────────────────────────────────────────
    "Hunter": {
        "dawn": [
            _a("hunt", "Hunter", "dawn", LocalTerrain.FOREST, 30,
               ["slips into the tree line with a rifle"]),
        ],
        "morning": [
            _a("hunt", "Hunter", "morning", LocalTerrain.FOREST, 60,
               ["tracks game through the underbrush",
                "crouches behind a fallen log, waiting"]),
        ],
        "afternoon": [
            _a("rest", "Hunter", "afternoon", LocalTerrain.CHAIR, 30,
               ["skins a rabbit outside camp",
                "dries strips of venison over a fire"]),
        ],
        "night": [
            _a("sleep", "Hunter", "night", LocalTerrain.BED, 60,
               ["sleeps lightly, rifle at hand"]),
        ],
    },

    # ── Preacher ────────────────────────────────────────────────────────
    "Preacher": {
        "morning": [
            _a("preach", "Preacher", "morning", -1, 45,
               ["reads scripture aloud to anyone who'll listen",
                "prays on a knoll overlooking camp"]),
        ],
        "afternoon": [
            _a("visit", "Preacher", "afternoon", -1, 30,
               ["visits the sick and injured",
                "writes a letter for an illiterate miner"]),
        ],
        "night": [
            _a("sleep", "Preacher", "night", LocalTerrain.BED, 60,
               ["reads by candlelight before sleeping"]),
        ],
    },
}


# ── Fallback: any occupation not listed gets generic activities ─────────

_GENERIC_ACTIVITIES: Dict[str, List[ActivityDef]] = {
    "dawn": [
        _a("wake_up", "*", "dawn", LocalTerrain.BED, 15,
           ["stretches and rises"]),
    ],
    "morning": [
        _a("work", "*", "morning", -1, 60,
           ["goes about the day's work"]),
    ],
    "afternoon": [
        _a("work", "*", "afternoon", -1, 60,
           ["continues working"]),
    ],
    "dusk": [
        _a("rest", "*", "dusk", LocalTerrain.CHAIR, 30,
           ["sits down to rest"]),
    ],
    "night": [
        _a("sleep", "*", "night", LocalTerrain.BED, 60,
           ["sleeps"]),
        _a("sleep_chair", "*", "night", LocalTerrain.CHAIR, 60,
           ["dozes in a chair"]),
    ],
}


# ── Public API ──────────────────────────────────────────────────────────

def pick_activity(npc, period: str, rng) -> Optional[ActivityDef]:
    """Pick an activity for *npc* given the current time-of-day *period*.

    Uses the NPC's ``occupation`` field to look up the activity table.
    Falls back to generic activities if the occupation is not listed or the
    period has no entries.  Returns ``None`` only when there is absolutely
    nothing defined (should not happen with the generic table).

    Parameters
    ----------
    npc : NPC or NPCExpanded
        Must have an ``occupation`` attribute (str).
    period : str
        One of ``"dawn"``, ``"morning"``, ``"afternoon"``, ``"dusk"``,
        ``"night"``.
    rng : random.Random
        Seeded RNG for deterministic choice.
    """
    occ = getattr(npc, "occupation", "")
    table = OCCUPATION_ACTIVITIES.get(occ, {})
    candidates = table.get(period)

    if not candidates:
        candidates = _GENERIC_ACTIVITIES.get(period)

    if not candidates:
        return None

    return rng.choice(candidates)


def find_activity_target(
    lmap,
    npc_x: int,
    npc_y: int,
    target_terrain: int,
    rng,
    max_range: int = 30,
) -> Optional[Tuple[int, int]]:
    """Find the nearest tile matching *target_terrain* within *max_range*.

    Uses a simple expanding-square scan (not pathfinding) so it's cheap to
    call every tick.  Returns ``(tx, ty)`` of the closest match, or ``None``
    if nothing is found.

    When multiple tiles are equally close, one is chosen at random via *rng*
    to avoid herding all NPCs toward the same corner.

    Parameters
    ----------
    lmap : LocalMap
        Must support ``lmap.terrain[y][x]`` indexing and have ``width`` /
        ``height`` attributes.
    npc_x, npc_y : int
        NPC's current position.
    target_terrain : int
        ``LocalTerrain`` constant to search for.  If ``-1``, returns
        ``None`` (caller should random-walk instead).
    rng : random.Random
        Seeded RNG for tie-breaking.
    max_range : int
        Maximum Chebyshev distance to search.
    """
    if target_terrain < 0:
        return None

    width = getattr(lmap, "width", 384)
    height = getattr(lmap, "height", 384)
    terrain = lmap.terrain

    best_dist = max_range + 1
    best_tiles: List[Tuple[int, int]] = []

    # Expanding-square scan: check each ring outward
    for r in range(1, max_range + 1):
        # Early-out: if we already have candidates closer than this ring,
        # no need to keep scanning.
        if best_tiles and r > best_dist:
            break

        for dx in range(-r, r + 1):
            for dy in (-r, r) if abs(dx) < r else range(-r, r + 1):
                tx, ty = npc_x + dx, npc_y + dy
                if 0 <= tx < width and 0 <= ty < height:
                    if terrain[ty][tx] == target_terrain:
                        dist = max(abs(dx), abs(dy))  # Chebyshev
                        if dist < best_dist:
                            best_dist = dist
                            best_tiles = [(tx, ty)]
                        elif dist == best_dist:
                            best_tiles.append((tx, ty))

    if not best_tiles:
        return None

    return rng.choice(best_tiles)


def step_toward(
    npc_x: int, npc_y: int, target_x: int, target_y: int
) -> Tuple[int, int]:
    """Return ``(dx, dy)`` to move one step toward *target* (Chebyshev).

    Each component is clamped to -1, 0, or +1 so the NPC moves at most one
    tile diagonally per call.
    """
    dx = 0
    dy = 0
    if target_x > npc_x:
        dx = 1
    elif target_x < npc_x:
        dx = -1
    if target_y > npc_y:
        dy = 1
    elif target_y < npc_y:
        dy = -1
    return (dx, dy)
