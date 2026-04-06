"""
src/scouting.py

Tracking and land-reading system.  Used by ALL eras — Mountain Men, Gold Rush
prospectors, anyone with tracking skill benefits from scouting the area.

Call scout_area() to scan the surroundings; returns a ScoutResult with graduated
detail based on the player's tracking (and optionally geology) skill level.
"""

import math
import random
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, TYPE_CHECKING

from src.local_map import LocalTerrain

if TYPE_CHECKING:
    from src.player import Player
    from src.local_map import LocalMap
    from src.wildlife_manager import WildlifeManager
    from src.time_system import GameTime


# ── Result container ─────────────────────────────────────────────────────

@dataclass
class ScoutResult:
    messages: List[Tuple[str, str]] = field(default_factory=list)
    """(message_text, severity) pairs.  severity: 'normal', 'advisory', 'critical'."""
    journal_entries: List[str] = field(default_factory=list)
    """Auto-generated journal notes for significant finds."""
    discovered_dams: List[Tuple[int, int]] = field(default_factory=list)
    """Beaver dam positions found during this scout."""


# ── Terrain classification sets ──────────────────────────────────────────

_WATER_TILES = frozenset([
    LocalTerrain.WATER, LocalTerrain.DEEP_WATER,
    LocalTerrain.BEAVER_POND,
])

_TREE_TILES = frozenset([
    LocalTerrain.FOREST, LocalTerrain.PINE, LocalTerrain.OAK,
    LocalTerrain.ASPEN, LocalTerrain.JUNIPER, LocalTerrain.CEDAR,
    LocalTerrain.MAPLE, LocalTerrain.CHESTNUT, LocalTerrain.HICKORY,
    LocalTerrain.CYPRESS, LocalTerrain.MAGNOLIA,
])

_ROCK_TILES = frozenset([
    LocalTerrain.ROCK, LocalTerrain.BEDROCK,
])

_GRASS_TILES = frozenset([
    LocalTerrain.GRASS, LocalTerrain.GROUND, LocalTerrain.TUNDRA,
])

_GOLD_HINT_TILES = frozenset([
    LocalTerrain.GRAVEL_BAR, LocalTerrain.BEDROCK,
])


# ── Direction helpers ────────────────────────────────────────────────────

def _dir_name(dx: int, dy: int) -> str:
    """Human-readable compass direction from a delta vector."""
    d = ""
    if dy < 0:
        d += "north"
    if dy > 0:
        d += "south"
    if dx < 0:
        d += "west"
    if dx > 0:
        d += "east"
    return d or "nearby"


def _dist_ft(tile_dist: int) -> int:
    """Convert tile distance to approximate feet (5 ft per tile)."""
    return tile_dist * 5


def _tile_dist(ax: int, ay: int, bx: int, by: int) -> float:
    """Chebyshev distance between two tile positions."""
    return max(abs(ax - bx), abs(ay - by))


# ── Wind direction (deterministic from time) ─────────────────────────────

_WIND_DIRS = ["north", "northeast", "east", "southeast",
              "south", "southwest", "west", "northwest"]


def _wind_direction(time: "GameTime", rng: random.Random) -> str:
    """Pseudo-random wind direction seeded from the current hour."""
    idx = rng.randint(0, len(_WIND_DIRS) - 1)
    return _WIND_DIRS[idx]


# ── Terrain summary generation ───────────────────────────────────────────

def _terrain_summary(counts: dict, px: int, py: int,
                     quadrant_data: dict) -> str:
    """Build a natural-language terrain summary from tile counts and
    per-quadrant analysis."""
    parts = []

    # Describe dominant tree cover
    total_trees = counts.get("trees", 0)
    total_tiles = max(sum(counts.values()), 1)

    if total_trees > total_tiles * 0.5:
        # Find the quadrant with the densest trees
        best_q = max(quadrant_data, key=lambda q: quadrant_data[q].get("trees", 0))
        parts.append(f"Thick forest to the {best_q}")
    elif total_trees > total_tiles * 0.2:
        best_q = max(quadrant_data, key=lambda q: quadrant_data[q].get("trees", 0))
        parts.append(f"Scattered timber to the {best_q}")

    # Describe water
    total_water = counts.get("water", 0)
    if total_water > 0:
        # Figure out if water runs in a direction
        water_quads = [q for q in quadrant_data
                       if quadrant_data[q].get("water", 0) > 2]
        if len(water_quads) >= 2:
            parts.append(f"Stream runs {water_quads[0]}-{water_quads[1]}")
        elif water_quads:
            parts.append(f"Water to the {water_quads[0]}")
        else:
            parts.append("Some water nearby")

    # Describe rock
    total_rock = counts.get("rock", 0)
    if total_rock > total_tiles * 0.15:
        best_q = max(quadrant_data, key=lambda q: quadrant_data[q].get("rock", 0))
        parts.append(f"Rocky ground to the {best_q}")

    # Describe open ground
    total_grass = counts.get("grass", 0)
    if total_grass > total_tiles * 0.5:
        parts.append("Open grassland stretches around you")

    if not parts:
        parts.append("Mixed terrain, nothing remarkable")

    return ". ".join(parts) + "."


# ── Phase implementations ────────────────────────────────────────────────

def _phase1_basic_observation(
    result: ScoutResult,
    player: "Player",
    lmap: "LocalMap",
    time: "GameTime",
    scan_radius: int,
) -> None:
    """Phase 1: Basic terrain observation (all skill levels)."""
    px, py = player.local_x, player.local_y
    counts = {"water": 0, "trees": 0, "rock": 0, "grass": 0}
    quadrant_data = {
        "north": {"water": 0, "trees": 0, "rock": 0, "grass": 0},
        "south": {"water": 0, "trees": 0, "rock": 0, "grass": 0},
        "east":  {"water": 0, "trees": 0, "rock": 0, "grass": 0},
        "west":  {"water": 0, "trees": 0, "rock": 0, "grass": 0},
    }

    for dy in range(-scan_radius, scan_radius + 1):
        for dx in range(-scan_radius, scan_radius + 1):
            tx, ty = px + dx, py + dy
            if not lmap.in_bounds(tx, ty):
                continue
            terrain = lmap.tiles[ty][tx].terrain

            # Classify
            if terrain in _WATER_TILES:
                category = "water"
            elif terrain in _TREE_TILES:
                category = "trees"
            elif terrain in _ROCK_TILES:
                category = "rock"
            elif terrain in _GRASS_TILES:
                category = "grass"
            else:
                continue

            counts[category] = counts.get(category, 0) + 1

            # Quadrant assignment
            if dy < 0:
                quadrant_data["north"][category] += 1
            elif dy > 0:
                quadrant_data["south"][category] += 1
            if dx < 0:
                quadrant_data["west"][category] += 1
            elif dx > 0:
                quadrant_data["east"][category] += 1

    summary = _terrain_summary(counts, px, py, quadrant_data)
    result.messages.append((summary, "normal"))

    # Weather and time of day
    period = time.period
    weather = time.weather
    period_desc = {
        "dawn": "The sun is rising",
        "day": "Daylight",
        "dusk": "The sun is setting",
        "night": "Darkness surrounds you",
    }.get(period, "Daylight")

    weather_desc = {
        "clear": "skies are clear",
        "overcast": "clouds hang low",
        "rain": "rain is falling",
        "snow": "snow drifts down",
        "blizzard": "a blizzard howls",
        "fog": "fog limits visibility",
        "thunderstorm": "thunder rumbles overhead",
        "hot": "the air shimmers with heat",
        "cold": "a bitter chill hangs in the air",
    }.get(weather, "skies are clear")

    result.messages.append((f"{period_desc}, {weather_desc}.", "normal"))


def _phase2_animal_sign(
    result: ScoutResult,
    player: "Player",
    lmap: "LocalMap",
    wildlife_mgr: "WildlifeManager",
    tracking: int,
    scan_radius: int,
    rng: random.Random,
) -> None:
    """Phase 2: Animal sign reading (tracking >= 2)."""
    if tracking < 2:
        return

    px, py = player.local_x, player.local_y
    detect_range = scan_radius * 2

    animals = wildlife_mgr.get_animals(
        lmap.world_x, lmap.world_y, lmap.area_x, lmap.area_y)

    for animal in animals:
        if not animal.alive:
            continue

        dist = _tile_dist(px, py, animal.local_x, animal.local_y)
        if dist > detect_range:
            continue

        dx = animal.local_x - px
        dy = animal.local_y - py
        direction = _dir_name(dx, dy)
        name = animal.species.display_name
        dist_ft = _dist_ft(int(dist))
        state = animal.state

        if tracking <= 4:
            # Vague: species + direction
            verb = rng.choice(["tracks", "sign", "droppings"])
            result.messages.append(
                (f"{name} {verb} heading {direction}.", "normal"))

        elif tracking <= 7:
            # Moderate: species, count-hint, direction, distance, state
            state_desc = {
                "idle": "grazing" if animal.species.danger_level == 0
                        else "resting",
                "fleeing": "moving quickly",
                "hostile": "agitated",
                "wounded_fleeing": "wounded, moving slowly",
            }.get(state, "present")
            result.messages.append(
                (f"{name}, {dist_ft}ft {direction}, {state_desc}.", "normal"))

        else:
            # Expert: exact position hint, wind, behavioral detail
            state_detail = {
                "idle": "feeding calmly, unaware of you"
                        if animal.species.danger_level == 0
                        else "watchful, testing the air",
                "fleeing": "spooked, moving fast downwind",
                "hostile": "aggressive, hackles raised",
                "wounded_fleeing": "bleeding, stumbling",
            }.get(state, "present")
            result.messages.append(
                (f"{name} about {dist_ft}ft {direction}. {state_detail.capitalize()}.",
                 "normal"))


def _phase3_beaver_dams(
    result: ScoutResult,
    player: "Player",
    lmap: "LocalMap",
    tracking: int,
    scan_radius: int,
) -> None:
    """Phase 3: Beaver dam detection (tracking >= 3)."""
    if tracking < 3:
        return

    px, py = player.local_x, player.local_y

    for dam_x, dam_y in lmap.beaver_dams:
        dist = _tile_dist(px, py, dam_x, dam_y)
        if dist > scan_radius:
            continue

        dx = dam_x - px
        dy = dam_y - py
        direction = _dir_name(dx, dy)
        dist_ft = _dist_ft(int(dist))

        if tracking <= 5:
            msg = (f"Fresh chew marks on aspens. Beaver active "
                   f"upstream to the {direction}.")
            result.messages.append((msg, "normal"))
            result.journal_entries.append(
                f"Beaver sign spotted to the {direction}.")
        else:
            msg = (f"Beaver dam about {dist_ft}ft {direction}. "
                   f"Good trapping ground.")
            result.messages.append((msg, "normal"))
            result.discovered_dams.append((dam_x, dam_y))
            result.journal_entries.append(
                f"Found beaver dam {dist_ft}ft {direction} "
                f"at ({dam_x}, {dam_y}). Good trapping ground.")


def _phase4_danger(
    result: ScoutResult,
    player: "Player",
    lmap: "LocalMap",
    wildlife_mgr: "WildlifeManager",
    npc_mgr,
    tracking: int,
    scan_radius: int,
    rng: random.Random,
) -> None:
    """Phase 4: Danger assessment (tracking >= 4)."""
    if tracking < 4:
        return

    px, py = player.local_x, player.local_y

    # Check for predators (danger_level >= 2) within scan radius
    animals = wildlife_mgr.get_animals(
        lmap.world_x, lmap.world_y, lmap.area_x, lmap.area_y)

    predator_messages = {
        "Grizzly Bear": [
            "Fresh grizzly scat. Large bear, recent.",
            "Deep claw marks on a pine trunk. Grizzly, and big.",
        ],
        "Gray Wolf": [
            "Wolf tracks, a pack. They've been hunting here.",
            "Wolf scat and trampled ground. A pack passed through.",
        ],
        "Mountain Lion": [
            "Cougar scrape marks in the dirt. Big cat nearby.",
            "Mountain lion tracks, fresh. It knows you're here.",
        ],
        "Black Bear": [
            "Overturned logs and torn bark. Black bear foraging.",
        ],
    }

    seen_species = set()
    for animal in animals:
        if not animal.alive:
            continue
        if animal.species.danger_level < 2:
            continue

        dist = _tile_dist(px, py, animal.local_x, animal.local_y)
        if dist > scan_radius:
            continue

        name = animal.species.display_name
        if name in seen_species:
            continue
        seen_species.add(name)

        dx = animal.local_x - px
        dy = animal.local_y - py
        direction = _dir_name(dx, dy)

        msgs = predator_messages.get(name)
        if msgs:
            msg = rng.choice(msgs)
        else:
            msg = f"Predator sign — {name} tracks, {direction}."

        result.messages.append((msg, "critical"))
        result.journal_entries.append(
            f"Danger: {name} sign spotted to the {direction}.")

    # Check for human sign: NPCs within radius * 1.5
    if npc_mgr is not None:
        npc_range = int(scan_radius * 1.5)
        npcs_nearby = []
        for npc in npc_mgr.npcs_on_map():
            if not npc.alive:
                continue
            dist = _tile_dist(px, py, npc.local_x, npc.local_y)
            if dist <= npc_range:
                npcs_nearby.append(npc)

        for npc in npcs_nearby:
            dx = npc.local_x - px
            dy = npc.local_y - py
            direction = _dir_name(dx, dy)

            # Check for tribal affiliation (NPCExpanded has .tribe attr)
            is_tribal = False
            tribe_name = ""
            if hasattr(npc, "tribe") and npc.tribe:
                is_tribal = True
                tribe_name = npc.tribe

            if is_tribal:
                result.messages.append(
                    (f"Moccasin tracks, heading {direction}. Not alone.",
                     "advisory"))
                result.journal_entries.append(
                    f"Found moccasin tracks heading {direction}.")
            else:
                result.messages.append(
                    ("Boot prints. Someone passed through recently.",
                     "advisory"))


def _phase5_camp_site(
    result: ScoutResult,
    player: "Player",
    lmap: "LocalMap",
    tracking: int,
    scan_radius: int,
    rng: random.Random,
) -> None:
    """Phase 5: Camp site assessment (tracking >= 5)."""
    if tracking < 5:
        return

    px, py = player.local_x, player.local_y
    best_site = None
    best_score = 0

    # Sample tiles within radius looking for sheltered spots near water
    step = max(1, scan_radius // 10)
    for dy in range(-scan_radius, scan_radius + 1, step):
        for dx in range(-scan_radius, scan_radius + 1, step):
            tx, ty = px + dx, py + dy
            if not lmap.in_bounds(tx, ty):
                continue
            terrain = lmap.tiles[ty][tx].terrain
            if terrain in _ROCK_TILES or terrain in _WATER_TILES:
                continue

            # Count adjacent trees and nearby water
            tree_sides = 0
            water_nearby = False
            for ndy in range(-2, 3):
                for ndx in range(-2, 3):
                    nx, ny = tx + ndx, ty + ndy
                    if not lmap.in_bounds(nx, ny):
                        continue
                    adj_terrain = lmap.tiles[ny][nx].terrain
                    if adj_terrain in _TREE_TILES:
                        tree_sides += 1
                    if adj_terrain in _WATER_TILES:
                        water_nearby = True

            if tree_sides >= 3 and water_nearby:
                score = tree_sides + (5 if water_nearby else 0)
                if score > best_score:
                    best_score = score
                    best_site = (tx, ty)

    if best_site is not None:
        dx = best_site[0] - px
        dy = best_site[1] - py
        direction = _dir_name(dx, dy)
        dist_ft = _dist_ft(int(_tile_dist(px, py, best_site[0], best_site[1])))
        result.messages.append(
            (f"Good camp site to the {direction}. Sheltered, near water.",
             "normal"))
        result.journal_entries.append(
            f"Found good camp site {dist_ft}ft {direction}. "
            f"Sheltered by trees, water access.")

    # Identify game trails: clusters of non-predator animals suggest trails
    from src.wildlife_manager import WildlifeManager as _WM  # just for type ref
    # (wildlife_mgr is not passed to phase5 — use lmap to check for
    #  animal-passable corridors between tree clusters)
    # Simple heuristic: look for ground tiles forming corridors through trees
    trail_found = False
    for dy in range(-scan_radius, scan_radius + 1, step * 2):
        for dx in range(-scan_radius, scan_radius + 1, step * 2):
            tx, ty = px + dx, py + dy
            if not lmap.in_bounds(tx, ty):
                continue
            terrain = lmap.tiles[ty][tx].terrain
            if terrain not in _GRASS_TILES:
                continue
            # Check if flanked by trees on two sides (corridor)
            left_tree = (lmap.in_bounds(tx - 1, ty)
                         and lmap.tiles[ty][tx - 1].terrain in _TREE_TILES)
            right_tree = (lmap.in_bounds(tx + 1, ty)
                          and lmap.tiles[ty][tx + 1].terrain in _TREE_TILES)
            up_tree = (lmap.in_bounds(tx, ty - 1)
                       and lmap.tiles[ty - 1][tx].terrain in _TREE_TILES)
            down_tree = (lmap.in_bounds(tx, ty + 1)
                         and lmap.tiles[ty + 1][tx].terrain in _TREE_TILES)

            if (left_tree and right_tree) or (up_tree and down_tree):
                direction = _dir_name(dx, dy)
                if not trail_found:
                    result.messages.append(
                        (f"Game trail to the {direction}. "
                         f"Animals pass through here regularly.", "normal"))
                    trail_found = True
                break
        if trail_found:
            break


def _phase6_gold_crossover(
    result: ScoutResult,
    player: "Player",
    lmap: "LocalMap",
    tracking: int,
    scan_radius: int,
) -> None:
    """Phase 6: Gold prospecting crossover (tracking >= 3 AND geology >= 2)."""
    geology = player.skills.get("geology", 0)
    if tracking < 3 or geology < 2:
        return

    px, py = player.local_x, player.local_y
    best_gold = None
    best_grade = 0.0
    found_mineral_tile = False

    # Scan for gold-relevant terrain
    step = max(1, scan_radius // 8)
    for dy in range(-scan_radius, scan_radius + 1, step):
        for dx in range(-scan_radius, scan_radius + 1, step):
            tx, ty = px + dx, py + dy
            if not lmap.in_bounds(tx, ty):
                continue

            tile = lmap.tiles[ty][tx]
            terrain = tile.terrain

            # Check for gravel bar / bedrock
            if terrain in _GOLD_HINT_TILES and not found_mineral_tile:
                direction = _dir_name(dx, dy)
                result.messages.append(
                    (f"This gravel bar shows good mineral color. "
                     f"Worth a test pan.", "normal"))
                found_mineral_tile = True

            # Check for high gold grade
            if tile.gold_grade > best_grade:
                best_grade = tile.gold_grade
                best_gold = (tx, ty)

    if best_gold is not None and best_grade > 0.3:
        dx = best_gold[0] - px
        dy = best_gold[1] - py
        direction = _dir_name(dx, dy)
        dist_ft = _dist_ft(int(_tile_dist(px, py, best_gold[0], best_gold[1])))

        if best_grade > 0.7:
            result.messages.append(
                (f"Black sand in the streambed to the {direction}. "
                 f"Promising ground.", "normal"))
            result.journal_entries.append(
                f"Found black sand and promising mineral color "
                f"{dist_ft}ft {direction}.")
        else:
            result.messages.append(
                (f"Some color in the gravel to the {direction}. "
                 f"Might be worth investigating.", "normal"))


# ── Main entry point ─────────────────────────────────────────────────────

def scout_area(
    player: "Player",
    lmap: "LocalMap",
    wildlife_mgr: "WildlifeManager",
    time: "GameTime",
    rng: random.Random,
    npc_mgr=None,
) -> ScoutResult:
    """
    Scout the area around the player's current position.

    Graduated by ``player.skills.get("tracking", 0)``:

    - Phase 1 (all):       Basic terrain observation, weather, time of day
    - Phase 2 (tracking 2+): Animal sign with increasing detail
    - Phase 3 (tracking 3+): Beaver dam detection
    - Phase 4 (tracking 4+): Danger assessment (predators, human sign)
    - Phase 5 (tracking 5+): Camp site assessment, game trail identification
    - Phase 6 (tracking 3+ AND geology 2+): Gold prospecting crossover

    Parameters
    ----------
    player : Player
        The player character (position and skills read from here).
    lmap : LocalMap
        The current local map.
    wildlife_mgr : WildlifeManager
        Manages wildlife instances on the map.
    time : GameTime
        Current game time (for weather/period reporting).
    rng : random.Random
        Seeded RNG for deterministic message variation.
    npc_mgr : NPCManager, optional
        NPC manager for human-sign detection in Phase 4.

    Returns
    -------
    ScoutResult
        Messages, journal entries, and discovered beaver dam positions.
    """
    tracking = player.skills.get("tracking", 0)
    scan_radius = 8 + tracking * 3  # range 8 at skill 0, 38 at skill 10

    result = ScoutResult()

    # Phase 1: Basic observation (all skill levels)
    _phase1_basic_observation(result, player, lmap, time, scan_radius)

    # Phase 2: Animal sign (tracking >= 2)
    _phase2_animal_sign(result, player, lmap, wildlife_mgr,
                        tracking, scan_radius, rng)

    # Phase 3: Beaver dams (tracking >= 3)
    _phase3_beaver_dams(result, player, lmap, tracking, scan_radius)

    # Phase 4: Danger (tracking >= 4)
    _phase4_danger(result, player, lmap, wildlife_mgr, npc_mgr,
                   tracking, scan_radius, rng)

    # Phase 5: Camp site assessment (tracking >= 5)
    _phase5_camp_site(result, player, lmap, tracking, scan_radius, rng)

    # Phase 6: Gold prospecting crossover (tracking >= 3 AND geology >= 2)
    _phase6_gold_crossover(result, player, lmap, tracking, scan_radius)

    return result
