"""
src/rumor_system.py

Generates map-grounded rumors from real world tile data.
Every rumor references an actual world coordinate derived from
gold_bias, terrain, and known locations near the player.

Specificity scales with NPC relationship and knowledge:
  vague       — direction only, no map reveal
  directional — area + distance, small fog-of-war reveal
  specific    — named landmark, full reveal + journal place note
"""

import random
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.world_map import WorldMap
    from src.npc import NPC
    from src.player import Player


# ── Rumor result ───────────────────────────────────────────────────────────────

@dataclass
class Rumor:
    text:             str             # what the NPC says out loud
    wx:               int  = -1       # world tile X (-1 = truly vague)
    wy:               int  = -1       # world tile Y (-1 = truly vague)
    category:         str  = "gold"   # gold | location | water | trail | danger
    specificity:      str  = "vague"  # vague | directional | specific
    reveal_radius:    int  = 0        # tiles of fog to lift (0 = none)
    journal_text:     str  = ""       # added to Rumors tab (empty = skip)
    place_name:       str  = ""       # added to Places tab (empty = skip)


# ── Direction / distance helpers ───────────────────────────────────────────────

def _dir(dx: int, dy: int) -> str:
    ax, ay = abs(dx), abs(dy)
    if ax < 1 and ay < 1:
        return "right here"
    if ax > ay * 2:
        return "east" if dx > 0 else "west"
    if ay > ax * 2:
        return "south" if dy > 0 else "north"
    if dx > 0:
        return "southeast" if dy > 0 else "northeast"
    return "southwest" if dy > 0 else "northwest"


def _dist_text(tiles: int) -> str:
    miles = tiles * 5
    if miles < 15:   return "just a short ways"
    if miles < 40:   return "about a day's ride"
    if miles < 80:   return "two days out"
    if miles < 150:  return "three or four days"
    return "a good week's travel"


def _terrain_phrase(terrain: int) -> str:
    from src.world_map import Terrain
    return {
        Terrain.MOUNTAINS: "up in the mountains",
        Terrain.HILLS:     "in the hill country",
        Terrain.RIVER:     "along the river",
        Terrain.FOREST:    "back in the timber",
        Terrain.CONIFER:   "deep in the pines",
        Terrain.DESERT:    "out in the desert",
        Terrain.PLAINS:    "on the flats",
        Terrain.PRAIRIE:   "out on the prairie",
        Terrain.SCRUB:     "in the scrublands",
        Terrain.SWAMP:     "in the swamp country",
        Terrain.COAST:     "near the coast",
    }.get(terrain, "out there")


# Deterministic creek/place name from coordinates
_CREEK_FIRST = ["Bear", "Willow", "Clear", "Dry", "Slate", "Lost", "Cold",
                "Copper", "Silver", "Dead", "Pine", "Blue", "Gravel", "Eagle"]
_CREEK_LAST  = ["Creek", "Fork", "Run", "Branch", "Draw", "Gulch", "Wash",
                "Canyon", "Ravine", "Hollow"]
_PEAK_NAMES  = ["Bald", "Black", "Red", "Lone", "Broken", "Thunder", "Iron",
                "Copper", "Table", "Sentinel"]

def _place_name_from_coords(wx: int, wy: int, terrain: int) -> str:
    from src.world_map import Terrain
    seed = wx * 7919 + wy * 6271
    rng  = random.Random(seed)
    if terrain in (Terrain.MOUNTAINS, Terrain.HILLS):
        return f"{rng.choice(_PEAK_NAMES)} Peak"
    return f"{rng.choice(_CREEK_FIRST)} {rng.choice(_CREEK_LAST)}"


# ── NPC occupation → preferred rumor categories ───────────────────────────────

_OCC_CATEGORIES = {
    "prospector":   ["gold", "gold", "gold", "water"],
    "miner":        ["gold", "gold", "gold", "trail"],
    "assayer":      ["gold", "gold", "location", "gold"],
    "trader":       ["location", "location", "trail", "gold"],
    "merchant":     ["location", "location", "trail", "danger"],
    "trapper":      ["water", "trail", "gold", "danger"],
    "hunter":       ["water", "trail", "danger", "gold"],
    "scout":        ["trail", "location", "water", "danger"],
    "farmer":       ["water", "location", "trail", "gold"],
    "rancher":      ["water", "trail", "location", "danger"],
    "sheriff":      ["danger", "location", "trail", "gold"],
    "lawman":       ["danger", "location", "trail", "gold"],
    "bartender":    ["gold", "location", "danger", "trail"],
    "engineer":     ["trail", "location", "gold", "water"],
    "doctor":       ["danger", "location", "water", "trail"],
}
_DEFAULT_CATS = ["gold", "location", "trail", "water"]


def _pick_category(npc: "NPC", rng: random.Random) -> str:
    occ  = npc.occupation.lower()
    cats = _OCC_CATEGORIES.get(occ, _DEFAULT_CATS)
    # Knowledge boosts: geology/placer → gold; law → danger; etc.
    if any(k in npc.knowledge for k in ("geology", "placer", "hardRock", "assaying")):
        cats = ["gold"] + cats
    if "law" in npc.knowledge:
        cats = ["danger"] + cats
    return rng.choice(cats)


# ── Tile finders ───────────────────────────────────────────────────────────────

def _find_gold_tile(player: "Player", world_map: "WorldMap",
                    rng: random.Random,
                    search_radius: int = 30) -> Optional[Tuple[int, int]]:
    """Find a high gold-bias tile the player hasn't visited."""
    px, py = player.world_x, player.world_y
    candidates = []
    for dy in range(-search_radius, search_radius + 1):
        for dx in range(-search_radius, search_radius + 1):
            wx, wy = px + dx, py + dy
            if not world_map.in_bounds(wx, wy):
                continue
            if world_map.visited[wy, wx]:
                continue
            from src.world_map import Terrain
            terrain = int(world_map.tiles[wy, wx])
            if terrain == Terrain.OCEAN:
                continue
            bias = float(world_map.gold_bias[wy, wx])
            dist = max(abs(dx), abs(dy))
            if bias > 0.3 and dist > 3:
                candidates.append((bias - dist * 0.01, wx, wy))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    # Pick from top 5 with some randomness
    top = candidates[:min(5, len(candidates))]
    _, wx, wy = rng.choice(top)
    return wx, wy


def _find_location_tile(player: "Player", world_map: "WorldMap",
                        rng: random.Random) -> Optional[Tuple[int, int]]:
    """Point toward a known location (town) or interesting terrain feature."""
    px, py = player.world_x, player.world_y
    # Known locations first
    locs = [loc for loc in world_map.locations.values()
            if not loc.discovered]
    if locs:
        loc = rng.choice(locs)
        return loc.x, loc.y
    # Fall back to a river or mountain tile
    from src.world_map import Terrain
    interesting = [Terrain.RIVER, Terrain.MOUNTAINS, Terrain.COAST]
    candidates  = []
    for dy in range(-40, 41):
        for dx in range(-40, 41):
            wx, wy = px + dx, py + dy
            if not world_map.in_bounds(wx, wy):
                continue
            if world_map.visited[wy, wx]:
                continue
            if int(world_map.tiles[wy, wx]) in interesting and max(abs(dx), abs(dy)) > 5:
                candidates.append((wx, wy))
    if candidates:
        return rng.choice(candidates)
    return None


def _find_water_tile(player: "Player", world_map: "WorldMap",
                     rng: random.Random) -> Optional[Tuple[int, int]]:
    """Find an unvisited river or water-adjacent tile."""
    from src.world_map import Terrain
    px, py = player.world_x, player.world_y
    candidates = []
    for dy in range(-25, 26):
        for dx in range(-25, 26):
            wx, wy = px + dx, py + dy
            if not world_map.in_bounds(wx, wy):
                continue
            if int(world_map.tiles[wy, wx]) == Terrain.RIVER and max(abs(dx), abs(dy)) > 4:
                candidates.append((wx, wy))
    return rng.choice(candidates) if candidates else None


def _find_danger_tile(player: "Player", world_map: "WorldMap",
                      rng: random.Random) -> Optional[Tuple[int, int]]:
    """Find a difficult-terrain tile to warn about."""
    from src.world_map import Terrain
    px, py = player.world_x, player.world_y
    hard   = [Terrain.MOUNTAINS, Terrain.DESERT, Terrain.SWAMP]
    candidates = []
    for dy in range(-20, 21):
        for dx in range(-20, 21):
            wx, wy = px + dx, py + dy
            if not world_map.in_bounds(wx, wy):
                continue
            if int(world_map.tiles[wy, wx]) in hard and max(abs(dx), abs(dy)) > 5:
                candidates.append((wx, wy))
    return rng.choice(candidates) if candidates else None


# ── Text builders ──────────────────────────────────────────────────────────────

def _gold_rumor_text(dx: int, dy: int, dist: int,
                     terrain: int, place: str, spec: str) -> str:
    direction  = _dir(dx, dy)
    dist_txt   = _dist_text(dist)
    terr_txt   = _terrain_phrase(terrain)

    if spec == "vague":
        options = [
            f"Heard there's color {direction} of here. Couldn't say exactly where.",
            f"Men are talking about something {direction}. Gold, maybe. Nobody's saying much.",
            f"Somebody came back with dust in their poke. Headed {direction} when they left.",
            f"Word is there's pay dirt {direction}. Take it for what it's worth.",
        ]
    elif spec == "directional":
        options = [
            f"{dist_txt} {direction}, {terr_txt}. Fellow I know pulled good color there last season.",
            f"There's a creek {direction} of here, {dist_txt} out. Worth panning if you get the chance.",
            f"{dist_txt} {direction} — {terr_txt}. Saw color in the gravel bars myself, passing through.",
            f"Old worked ground {direction}, {dist_txt}. Whoever was there left in a hurry. Might still be color.",
        ]
    else:  # specific
        options = [
            f"{place}, {dist_txt} {direction}. Coarse gold in the black sand, inside the big bend. "
            f"I pulled two ounces off that bar two seasons back.",
            f"You want gold, go to {place} — {dist_txt} {direction}. Float gold in the gravel, "
            f"bedrock crevices packed tight. Don't tell everyone.",
            f"{dist_txt} {direction} — {place}. The color runs fine but there's a lot of it. "
            f"You'll need to work a bar for a week minimum, but it pays.",
        ]
    return random.choice(options)


def _location_rumor_text(dx: int, dy: int, dist: int,
                         terrain: int, place: str, spec: str,
                         loc_name: str = "") -> str:
    direction = _dir(dx, dy)
    dist_txt  = _dist_text(dist)
    terr_txt  = _terrain_phrase(terrain)
    name_str  = loc_name if loc_name else place

    if spec == "vague":
        options = [
            f"There's a settlement {direction} of here somewhere. Don't know much about it.",
            f"Heard there's a trading post {direction}. Couldn't tell you how far.",
        ]
    elif spec == "directional":
        options = [
            f"{dist_txt} {direction} there's a camp. Supply prices are decent, from what I hear.",
            f"Town {direction}, {dist_txt}. Small, but they've got an assay office.",
            f"There's a river crossing {direction}, {dist_txt} out — {terr_txt}. "
            f"Fellow runs a ferry there.",
        ]
    else:
        options = [
            f"{name_str} is {dist_txt} {direction}. They've got a store, a saloon, and "
            f"a blacksmith last I checked.",
            f"Follow the trail {direction}, {dist_txt} — you'll hit {name_str}. "
            f"Tell them I sent you.",
        ]
    return random.choice(options)


def _water_rumor_text(dx: int, dy: int, dist: int, spec: str, place: str) -> str:
    direction = _dir(dx, dy)
    dist_txt  = _dist_text(dist)
    if spec == "vague":
        return (f"There's water {direction} of here, somewhere. In this country "
                f"that's worth knowing.")
    if spec == "directional":
        return (f"River {direction}, {dist_txt} out. Good water, runs year-round "
                f"far as I know.")
    return (f"{place} runs clear {dist_txt} {direction}. "
            f"Spring-fed — never goes dry, not even in August.")


def _danger_rumor_text(dx: int, dy: int, dist: int,
                       terrain: int, spec: str) -> str:
    direction = _dir(dx, dy)
    dist_txt  = _dist_text(dist)
    terr_txt  = _terrain_phrase(terrain)
    if spec == "vague":
        return f"Watch yourself {direction} of here. Lost a man that way last summer."
    if spec == "directional":
        return (f"{dist_txt} {direction}, {terr_txt} — rough country. "
                f"Men have come back short a horse, or not at all.")
    return (f"{terr_txt}, {dist_txt} {direction}. "
            f"Passes close in by November. Don't get caught in there late in the season.")


# ── Main entry point ───────────────────────────────────────────────────────────

def generate_rumor(player: "Player", npc: "NPC",
                   world_map: "WorldMap",
                   rng: Optional[random.Random] = None) -> Rumor:
    """
    Generate one map-grounded rumor. Called when player asks an NPC about rumors.
    Returns a Rumor with text, coordinates, and reveal/journal metadata.
    """
    if rng is None:
        rng = random.Random()

    rel = npc.relationship

    # Specificity by relationship + NPC knowledge depth
    npc_knows_topic = bool(npc.knowledge)
    if rel < 5:
        spec = "vague"
    elif rel < 30 or not npc_knows_topic:
        spec = "directional"
    else:
        spec = "specific"

    category = _pick_category(npc, rng)

    # Find reference tile
    tile: Optional[Tuple[int, int]] = None
    if category == "gold":
        tile = _find_gold_tile(player, world_map, rng)
    elif category == "location":
        tile = _find_location_tile(player, world_map, rng)
    elif category == "water":
        tile = _find_water_tile(player, world_map, rng)
    elif category == "danger":
        tile = _find_danger_tile(player, world_map, rng)

    # Fall back to gold if the specific finder came up empty
    if tile is None:
        tile = _find_gold_tile(player, world_map, rng, search_radius=50)
    if tile is None:
        # Truly nothing found — return a generic atmospheric rumor
        return Rumor(
            text=rng.choice([
                "\"Quiet lately. Nothing much moving out there.\"",
                "\"Been a slow season. Ask someone who's been farther out than me.\"",
                "\"I got nothing for you. Talk to the assayer.\"",
            ]),
            category="none",
            specificity="vague",
        )

    wx, wy   = tile
    dx, dy   = wx - player.world_x, wy - player.world_y
    dist     = max(abs(dx), abs(dy))
    terrain  = int(world_map.tiles[wy, wx])
    place    = _place_name_from_coords(wx, wy, terrain)

    # Known location name override
    loc_obj  = world_map.get_location_at(wx, wy)
    loc_name = loc_obj.name if loc_obj else ""

    # Build text
    if category == "gold":
        text = _gold_rumor_text(dx, dy, dist, terrain, place, spec)
    elif category == "location":
        text = _location_rumor_text(dx, dy, dist, terrain, place, spec, loc_name)
    elif category == "water":
        text = _water_rumor_text(dx, dy, dist, spec, place)
    else:
        text = _danger_rumor_text(dx, dy, dist, terrain, spec)

    # Map reveal radius
    reveal = {"vague": 0, "directional": 3, "specific": 6}.get(spec, 0)

    # Journal text and place note
    if spec == "vague":
        j_text = f"{npc.name}: \"{text.strip('\"')}\""
        p_name = ""
    elif spec == "directional":
        direction = _dir(dx, dy)
        j_text = (f"{npc.name} mentioned {category} {_dist_text(dist)} "
                  f"{direction}. Unverified.")
        p_name = ""
    else:
        display = loc_name or place
        j_text = (f"{npc.name} told me about {display} — "
                  f"{_dist_text(dist)} {_dir(dx, dy)}. "
                  f"{category.capitalize()} potential. Worth investigating.")
        p_name = display

    return Rumor(
        text=f"\"{text.strip('\"')}\"",
        wx=wx, wy=wy,
        category=category,
        specificity=spec,
        reveal_radius=reveal,
        journal_text=j_text,
        place_name=p_name,
    )
