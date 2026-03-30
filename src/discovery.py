"""
Location discovery — roll for points of interest when entering unexplored tiles.

~5% chance per unvisited world tile to spawn a location of interest.
Creates a DynamicLocation and returns a discovery message.
Used during fast travel, patch transitions, and zoomed-out movement.
"""

import random
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine import Engine


DISCOVERY_CHANCE = 0.05  # 5% per unvisited world tile


# Location types with discovery text and NPC/loot hints
_DISCOVERY_TYPES = [
    {
        "type": "prospector_camp",
        "names": ["Lone Prospector's Camp", "Small Diggings", "Worked Creek Bed",
                  "Abandoned Pan Site", "Miner's Lean-to"],
        "messages": [
            "You spot a thin column of smoke. A prospector's camp — someone's working this ground.",
            "Fresh diggings along the creek. Someone's been panning here recently.",
            "A lean-to shelter and a sluice box set up by the water. Camp is occupied.",
        ],
        "notes": "Active prospector camp.",
    },
    {
        "type": "abandoned_camp",
        "names": ["Abandoned Camp", "Deserted Diggings", "Empty Tent",
                  "Ruined Shelter", "Ghost Claim"],
        "messages": [
            "An abandoned camp. Tent still standing, tools scattered. Nobody home.",
            "Old workings. Sluice box rotting. Whoever was here left in a hurry.",
            "A collapsed lean-to and a cold fire pit. Abandoned weeks ago.",
        ],
        "notes": "Abandoned — scavengeable.",
    },
    {
        "type": "waystation",
        "names": ["Trail Crossing", "Spring Camp", "Relay Station",
                  "Water Hole", "Rest Stop"],
        "messages": [
            "A natural spring with a cleared area around it. Good water here.",
            "A trail crossing marked with a cairn. Others have camped here.",
            "A flat spot by the creek with fire rings. Popular stopping point.",
        ],
        "notes": "Rest point with water.",
    },
    {
        "type": "mining_camp",
        "names": ["Busy Diggings", "Strike Camp", "Creek Camp",
                  "Gravel Bar Camp", "Mining Settlement"],
        "messages": [
            "The sound of picks on rock. A mining camp — several men working claims.",
            "Tents and sluice boxes along the creek. An active mining operation.",
            "You've found a settlement. Miners' tents, a makeshift store, activity.",
        ],
        "notes": "Active mining settlement.",
    },
    {
        "type": "outlaw_camp",
        "names": ["Hidden Camp", "Suspicious Camp", "Rough Camp",
                  "Outlaw Den"],
        "messages": [
            "A camp hidden in the brush, off the main trail. Armed men eye you warily.",
            "Horses tied up behind a rock outcrop. A camp that doesn't want to be found.",
            "You stumble onto a camp. The men there don't look like miners.",
        ],
        "notes": "CAUTION — possible outlaws.",
    },
    {
        "type": "native_camp",
        "names": ["Indian Camp", "Native Village", "Tribal Grounds",
                  "Fishing Camp"],
        "messages": [
            "Smoke from cook fires. A native encampment along the river.",
            "You see evidence of a long-established camp. Not miners — indigenous people.",
            "A fishing camp. Drying racks and shelters. They've been here a while.",
        ],
        "notes": "Indigenous camp — approach respectfully.",
    },
]


def roll_location_discovery(engine: "Engine", wx: int, wy: int
                            ) -> Optional[str]:
    """Roll for a location discovery at world tile (wx, wy).
    Returns a discovery message string, or None.
    Creates a DynamicLocation if successful."""
    rng = random.Random(wx * 9973 + wy * 7919 + engine.world.seed)

    if rng.random() > DISCOVERY_CHANCE:
        return None

    # Don't spawn on top of existing locations
    if engine.world.get_location_at(wx, wy):
        return None
    # Don't duplicate dynamic locations
    existing = engine.dynamic_locs.get_at(wx, wy)
    if existing:
        return None

    # Check terrain suitability
    from src.world_map import Terrain
    terrain = int(engine.world.tiles[wy][wx])
    if terrain == Terrain.OCEAN:
        return None

    # Pick a discovery type (weighted by terrain)
    if terrain in (Terrain.MOUNTAINS, Terrain.HILLS):
        weights = [3, 2, 1, 2, 1, 0]  # more mining camps in mountains
    elif terrain in (Terrain.FOREST, Terrain.CONIFER):
        weights = [2, 2, 1, 1, 1, 1]
    elif terrain in (Terrain.PLAINS, Terrain.PRAIRIE):
        weights = [1, 1, 2, 1, 0, 2]  # more waystations/native on plains
    elif terrain in (Terrain.RIVER,):
        weights = [3, 1, 2, 3, 0, 2]  # lots of mining near rivers
    else:
        weights = [2, 2, 2, 1, 1, 1]

    if not any(w > 0 for w in weights):
        weights = [1] * len(weights)
    disc = rng.choices(_DISCOVERY_TYPES, weights=weights, k=1)[0]

    name = rng.choice(disc["names"])
    message = rng.choice(disc["messages"])

    # Create dynamic location
    from src.dynamic_locations import DynamicLocation
    loc = DynamicLocation(
        id="",
        name=name,
        world_x=wx, world_y=wy,
        loc_type=disc["type"],
        stage="active",
        discovered=True,
        notes=disc["notes"],
    )
    engine.dynamic_locs.add(loc)

    return f"DISCOVERY: {message} ({name} at {wx},{wy})"
