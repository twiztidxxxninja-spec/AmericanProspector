"""
src/wildlife_manager.py

Wildlife spawning, movement, and proximity AI.
Prey flees; predators alert then attack if cornered.
"""

import random
from typing import List, Optional, Dict, Tuple, TYPE_CHECKING

from src.wildlife import WILDLIFE_DB, WildlifeSpecies, WildlifeType
from src.local_map import LocalMap, LocalTerrain
from src.health_system import HealthTracker, MAX_BLOOD, DmgType

if TYPE_CHECKING:
    from src.player import Player


# ── Glyph / color per species ─────────────────────────────────────────────

WILDLIFE_RENDER = {
    # (glyph, fg_color)
    WildlifeType.GRIZZLY_BEAR:        ("B", (160,  90,  40)),
    WildlifeType.BLACK_BEAR:          ("B", ( 60,  50,  40)),
    WildlifeType.MOUNTAIN_LION:       ("f", (200, 160,  80)),
    WildlifeType.GRAY_WOLF:           ("w", (150, 150, 150)),
    WildlifeType.BUFFALO:             ("B", ( 80,  60,  30)),
    WildlifeType.ELK:                 ("d", (160, 120,  60)),
    WildlifeType.MULE_DEER:           ("d", (180, 140,  80)),
    WildlifeType.BLACK_TAILED_DEER:   ("d", (150, 110,  60)),
    WildlifeType.PRONGHORN:           ("d", (200, 160,  80)),
    WildlifeType.BIGHORN_SHEEP:       ("d", (200, 180, 140)),
    WildlifeType.MOOSE:               ("D", (100,  70,  30)),
    WildlifeType.COYOTE:              ("c", (180, 150,  80)),
    WildlifeType.GRAY_FOX:            ("c", (120, 110,  90)),
    WildlifeType.RED_FOX:             ("c", (200,  80,  30)),
    WildlifeType.BEAVER:              ("b", (120,  90,  50)),
    WildlifeType.RACCOON:             ("r", (130, 130, 130)),
    WildlifeType.BOBCAT:              ("f", (180, 140,  80)),
    WildlifeType.JACKRABBIT:          ("r", (180, 160, 120)),
    WildlifeType.GROUND_SQUIRREL:     ("s", (160, 130,  80)),
    WildlifeType.RATTLESNAKE:         ("~", ( 80, 120,  40)),
    WildlifeType.BALD_EAGLE:          ("^", (200, 200, 255)),
    WildlifeType.CALIFORNIA_CONDOR:   ("^", ( 50,  50,  50)),
    WildlifeType.WILD_TURKEY:         ("t", (100,  80,  40)),
    # Eastern / additional
    WildlifeType.WHITETAIL_DEER:      ("d", (170, 130,  70)),
    WildlifeType.COTTONTAIL_RABBIT:   ("r", (160, 140, 110)),
    WildlifeType.WILD_HORSE:          ("H", (140, 110,  70)),
    WildlifeType.PRAIRIE_DOG:         ("s", (180, 150, 100)),
    WildlifeType.MOUNTAIN_GOAT:       ("g", (220, 220, 220)),
    WildlifeType.WILD_BOAR:           ("p", (100,  70,  40)),
    WildlifeType.TIMBER_RATTLESNAKE:  ("~", ( 90, 100,  50)),
    WildlifeType.PASSENGER_PIGEON:    ("^", (140, 120, 100)),
    WildlifeType.SANDHILL_CRANE:      ("^", (160, 160, 160)),
}

_DEFAULT_RENDER = ("?", (180, 180, 180))


# ── Alert distance by danger level ────────────────────────────────────────

# At 5ft/tile: prey detects at ~250ft, predators at ~150ft
_ALERT_DIST   = {0: 30, 1: 40, 2: 50}  # tiles at which animal notices player
_FLEE_DIST    = {0: 25, 1: 35, 2: 15}  # prey flees when player within this
_ATTACK_DIST  = {2: 12}                 # predators attack within this range (~60ft)

# ── Species attack profiles ──────────────────────────────────────────────
# (damage_type, weapon_key, verb_low, verb_mid, verb_high)
# weapon_key references WEAPON_WOUND_MAP in health_system.py

_ATK = {
    WildlifeType.GRIZZLY_BEAR: {
        "attacks": [
            (DmgType.BLUNT, "bear_claw", "swats",   "claws",    "mauls"),
            (DmgType.SLASH, "bear_claw", "rakes",   "slashes",  "tears into"),
            (DmgType.BITE,  "bear_bite", "nips at", "bites",    "crushes"),
        ], "weights": [50, 30, 20],
    },
    WildlifeType.BLACK_BEAR: {
        "attacks": [
            (DmgType.BLUNT, "bear_claw", "swats",      "claws",   "mauls"),
            (DmgType.SLASH, "bear_claw", "scratches",  "slashes", "rakes"),
            (DmgType.BITE,  "bear_bite", "nips at",    "bites",   "clamps onto"),
        ], "weights": [45, 35, 20],
    },
    WildlifeType.MOUNTAIN_LION: {
        "attacks": [
            (DmgType.SLASH, "bear_claw", "scratches", "rakes",      "tears into"),
            (DmgType.BITE,  "bear_bite", "nips at",   "bites",      "clamps onto"),
        ], "weights": [55, 45],
    },
    WildlifeType.GRAY_WOLF: {
        "attacks": [
            (DmgType.BITE,  "bear_bite", "snaps at",   "bites",    "clamps onto"),
            (DmgType.SLASH, "bear_claw", "scratches",  "rakes",    "tears at"),
        ], "weights": [70, 30],
    },
    WildlifeType.BOBCAT: {
        "attacks": [
            (DmgType.SLASH, "bear_claw", "scratches", "claws at", "rakes"),
            (DmgType.BITE,  "bear_bite", "nips at",   "bites",    "bites down on"),
        ], "weights": [60, 40],
    },
    WildlifeType.COYOTE: {
        "attacks": [
            (DmgType.BITE, "snake_bite", "nips at", "bites", "bites"),
        ], "weights": [100],
    },
    WildlifeType.RATTLESNAKE: {
        "attacks": [
            (DmgType.BITE, "snake_bite", "strikes at", "bites", "sinks fangs into"),
        ], "weights": [100],
    },
    WildlifeType.BUFFALO: {
        "attacks": [
            (DmgType.BLUNT,  "",  "shoves",     "tramples",  "gores"),
            (DmgType.PIERCE, "",  "jabs horn at","gores",     "impales"),
        ], "weights": [60, 40],
    },
    WildlifeType.ELK: {
        "attacks": [
            (DmgType.BLUNT,  "", "kicks at", "kicks",  "tramples"),
            (DmgType.PIERCE, "", "jabs at",  "gores",  "antler-rakes"),
        ], "weights": [50, 50],
    },
    WildlifeType.MOOSE: {
        "attacks": [
            (DmgType.BLUNT, "", "kicks at", "kicks",   "tramples"),
            (DmgType.BLUNT, "", "charges",  "stomps",  "crushes"),
        ], "weights": [50, 50],
    },
    WildlifeType.WILD_BOAR: {
        "attacks": [
            (DmgType.PIERCE, "", "jabs tusks at", "gores",  "rips into"),
            (DmgType.BLUNT,  "", "charges",       "rams",   "tramples"),
        ], "weights": [60, 40],
    },
    WildlifeType.TIMBER_RATTLESNAKE: {
        "attacks": [
            (DmgType.BITE, "snake_bite", "strikes at", "bites", "sinks fangs into"),
        ], "weights": [100],
    },
}
_DEFAULT_ATK = {
    "attacks": [(DmgType.BITE, "", "nips at", "bites", "attacks")],
    "weights": [100],
}

# ── Species → body plan mapping ──────────────────────────────────────────
SPECIES_BODY_PLAN = {
    WildlifeType.GRIZZLY_BEAR:      "quadruped",
    WildlifeType.BLACK_BEAR:        "quadruped",
    WildlifeType.MOUNTAIN_LION:     "quadruped",
    WildlifeType.GRAY_WOLF:         "quadruped",
    WildlifeType.BUFFALO:           "quadruped",
    WildlifeType.ELK:               "quadruped",
    WildlifeType.MULE_DEER:         "quadruped",
    WildlifeType.BLACK_TAILED_DEER: "quadruped",
    WildlifeType.PRONGHORN:         "quadruped",
    WildlifeType.BIGHORN_SHEEP:     "quadruped",
    WildlifeType.MOOSE:             "quadruped",
    WildlifeType.COYOTE:            "quadruped",
    WildlifeType.BOBCAT:            "small_quadruped",
    WildlifeType.GRAY_FOX:          "small_quadruped",
    WildlifeType.RED_FOX:           "small_quadruped",
    WildlifeType.RACCOON:           "small_quadruped",
    WildlifeType.JACKRABBIT:        "small_quadruped",
    WildlifeType.GROUND_SQUIRREL:   "small_quadruped",
    WildlifeType.BEAVER:            "small_quadruped",
    WildlifeType.RATTLESNAKE:       "snake",
    WildlifeType.BALD_EAGLE:        "bird",
    WildlifeType.CALIFORNIA_CONDOR: "bird",
    WildlifeType.WILD_TURKEY:       "bird",
    # Fur-bearers
    WildlifeType.RIVER_OTTER:      "small_quadruped",
    WildlifeType.MINK:             "small_quadruped",
    WildlifeType.PINE_MARTEN:      "small_quadruped",
    WildlifeType.FISHER:           "small_quadruped",
    WildlifeType.WOLVERINE:        "quadruped",
    WildlifeType.BADGER:           "small_quadruped",
    WildlifeType.SKUNK:            "small_quadruped",
    WildlifeType.MUSKRAT:          "small_quadruped",
    WildlifeType.OPOSSUM:          "small_quadruped",
    WildlifeType.LYNX:             "quadruped",
    # Eastern / additional
    WildlifeType.WHITETAIL_DEER:   "quadruped",
    WildlifeType.COTTONTAIL_RABBIT:"small_quadruped",
    WildlifeType.WILD_HORSE:       "quadruped",
    WildlifeType.PRAIRIE_DOG:      "small_quadruped",
    WildlifeType.MOUNTAIN_GOAT:    "quadruped",
    WildlifeType.WILD_BOAR:        "quadruped",
    WildlifeType.TIMBER_RATTLESNAKE: "snake",
    WildlifeType.PASSENGER_PIGEON: "bird",
    WildlifeType.SANDHILL_CRANE:   "bird",
}


class WildlifeInstance:
    __slots__ = ("species", "species_type", "local_x", "local_y", "local_z",
                 "health", "alert", "state", "last_attack_tick",
                 "wound_flee_steps", "butchered", "wounds",
                 "death_time", "decayed")

    def __init__(self, species_type: WildlifeType, species: WildlifeSpecies,
                 x: int, y: int):
        self.species_type     = species_type
        self.species          = species
        self.local_x          = x
        self.local_y          = y
        self.local_z          = 0
        self.health           = 100.0
        self.alert            = False
        # States:
        #   "idle"            — normal wandering
        #   "fleeing"         — unharmed flee (scared off)
        #   "hostile"         — charging / attacking
        #   "wounded_fleeing" — hit but not down, running; will collapse
        #   "downed"          — immobile but alive; can be finished or butchered
        #   "dead"            — killed outright or bled out; can be butchered
        #   "butchered"       — fully processed; nothing left
        self.state            = "idle"
        self.last_attack_tick = 0
        self.wound_flee_steps = 0    # steps remaining before wounded animal collapses
        self.butchered        = False
        self.death_time       = 0      # game minute when died (0 = alive)
        self.decayed          = False   # True = skeleton, no meat left
        self.wounds           = HealthTracker(
            MAX_BLOOD.get(species.size, 80.0),
            body_plan=SPECIES_BODY_PLAN.get(species_type, "quadruped"))

    @property
    def alive(self) -> bool:
        return self.state not in ("dead", "butchered")

    @property
    def recoverable(self) -> bool:
        """Can be butchered — downed or dead but not yet butchered."""
        return self.state in ("downed", "dead") and not self.butchered

    @property
    def glyph(self) -> Tuple[str, tuple]:
        return WILDLIFE_RENDER.get(self.species_type, _DEFAULT_RENDER)

    def take_damage(self, dmg: float, damage_type: str = DmgType.BLUNT):
        """
        Apply damage and update state.
        Wound thresholds:
          health <  0%  → dead (instant kill)
          health < 20%  → downed (dropped; paralyzed or too weak to move)
          health < 55%  → wounded_fleeing (runs, then collapses)
          health >= 55% → normal fear response (flee or fight)
        """
        self.health = max(0.0, self.health - dmg)
        self.wounds.apply_hit(dmg, damage_type)

        if self.health <= 0:
            self.state = "dead"
        elif self.health < 20:
            self.state = "downed"
        elif self.health < 55:
            self.state = "wounded_fleeing"
            # Distance before collapsing: less health = shorter run
            self.wound_flee_steps = int(4 + self.health * 0.6)
        else:
            # Light wound — normal fear response
            if self.species.danger_level == 0:
                self.state = "fleeing"
            elif self.species.danger_level == 1:
                self.state = "fleeing"
            else:
                # Apex predator with >55% health fights back harder
                self.state = "hostile"


# ── Terrain passability for animals ───────────────────────────────────────

_IMPASSABLE = frozenset([LocalTerrain.WATER, LocalTerrain.ROCK])


def _can_move_to(lmap: LocalMap, x: int, y: int) -> bool:
    if not lmap.in_bounds(x, y):
        return False
    return lmap.tile_at(x, y).terrain not in _IMPASSABLE


# ── Region → typical species ──────────────────────────────────────────────

def _era_wildlife_mult(species_id: str, year: int) -> float:
    """Species-specific historical population curves.
    Beaver peaked 1810s, crashed by 1840. Bison crashed 1870s.
    Each species has its own depletion timeline."""

    # Beaver — peak of fur trade 1810-1825, heavily trapped out by 1840
    if species_id == "beaver":
        if year < 1810: return 2.0   # pristine, pre-trade
        if year < 1825: return 1.8   # peak abundance, rendezvous era
        if year < 1835: return 1.2   # heavy trapping, declining
        if year < 1845: return 0.6   # severely depleted
        if year < 1860: return 0.4   # near-extirpated in most areas
        return 0.2                    # remnant populations only

    # River otter, mink, muskrat — follow beaver but lag 10 years
    if species_id in ("river_otter", "mink", "muskrat"):
        if year < 1820: return 1.8
        if year < 1835: return 1.5
        if year < 1845: return 1.0
        if year < 1860: return 0.6
        return 0.4

    # Pine marten, fisher — deep forest, trapped later
    if species_id in ("pine_marten", "fisher"):
        if year < 1830: return 1.6
        if year < 1845: return 1.2
        if year < 1860: return 0.8
        return 0.5

    # Wolverine — always rare, slow decline
    if species_id == "wolverine":
        if year < 1840: return 1.3
        if year < 1860: return 1.0
        return 0.7

    # Lynx, bobcat — moderate decline
    if species_id in ("lynx", "bobcat"):
        if year < 1835: return 1.4
        if year < 1850: return 1.0
        if year < 1870: return 0.7
        return 0.5

    # Red/gray fox — resilient, slight decline
    if species_id in ("red_fox", "gray_fox"):
        if year < 1840: return 1.3
        if year < 1860: return 1.0
        return 0.8

    # Bison — abundant until hide hunters, crash in 1870s
    if species_id in ("buffalo", "bison"):
        if year < 1840: return 2.0   # vast herds
        if year < 1860: return 1.5   # declining from settlement
        if year < 1870: return 0.8   # serious pressure
        if year < 1880: return 0.2   # mass slaughter
        return 0.05                   # near extinction

    # Elk — pushed out of plains by settlement
    if species_id == "elk":
        if year < 1840: return 1.5
        if year < 1860: return 1.0
        return 0.7

    # Gray wolf — poisoned/hunted alongside bison decline
    if species_id == "gray_wolf":
        if year < 1850: return 1.5
        if year < 1870: return 1.0
        if year < 1880: return 0.5
        return 0.3

    # Grizzly bear — slow retreat westward
    if species_id == "grizzly_bear":
        if year < 1840: return 1.4
        if year < 1860: return 1.0
        if year < 1880: return 0.6
        return 0.3

    # ── Eastern big game — abundant pre-1800, overhunted after ────────

    # Deer (all types) — massive herds pre-settlement
    if species_id in ("mule_deer", "black_tailed_deer", "whitetail_deer"):
        if year < 1780: return 2.5   # virgin wilderness, enormous herds
        if year < 1810: return 2.0   # still abundant
        if year < 1840: return 1.5   # declining from settlement
        if year < 1870: return 1.0
        return 0.8

    # Elk — eastern herds abundant pre-1800, gone from east by 1850
    if species_id == "elk":
        if year < 1790: return 2.0
        if year < 1820: return 1.5
        if year < 1850: return 1.0
        return 0.7

    # Passenger pigeon — billions of birds, declining from 1800, extinct 1914
    if species_id == "passenger_pigeon":
        if year < 1800: return 3.0   # flocks darkening the sky
        if year < 1850: return 2.0
        if year < 1880: return 0.8
        if year < 1900: return 0.2
        return 0.0                    # extinct

    # Wild horse — feral Spanish mustangs, expanding across plains
    if species_id == "wild_horse":
        if year < 1800: return 0.8   # still building herds
        if year < 1850: return 1.5   # peak mustang population
        if year < 1900: return 1.0
        return 0.5                    # rounded up and removed

    # Wild boar — feral hogs spreading from Spanish settlements
    if species_id == "wild_boar":
        if year < 1800: return 0.5   # limited to Gulf Coast
        if year < 1850: return 0.8   # spreading
        return 1.2                    # invasive, ever-increasing

    # Black bear — resilient but declining with deforestation
    if species_id == "black_bear":
        if year < 1800: return 1.8
        if year < 1850: return 1.3
        return 1.0

    # Wild turkey — abundant in eastern hardwoods, hunted hard
    if species_id == "wild_turkey":
        if year < 1800: return 2.0
        if year < 1860: return 1.2
        return 0.8

    return 1.0


def _species_for_region(region: str) -> List[WildlifeType]:
    """Return a list of WildlifeType values plausible for the region."""
    region_l = region.lower()
    candidates = []
    for wt, sp in WILDLIFE_DB.items():
        if any(r.lower() in region_l for r in sp.core_regions):
            candidates.append((wt, sp.base_spawn_chance))
    # Fall back to universal small game if nothing matches
    if not candidates:
        candidates = [
            (WildlifeType.JACKRABBIT, 0.4),
            (WildlifeType.COYOTE,     0.2),
            (WildlifeType.WILD_TURKEY,0.15),
        ]
    return candidates


# ── Habitat-terrain matching ─────────────────────────────────────────────
# Maps species habitats to LocalTerrain types they need nearby to spawn.
# "aquatic" species need water within 5 tiles. "forest" need tree tiles.
# Species without entries spawn anywhere passable.

_HABITAT_REQUIRE_WATER = frozenset([
    "beaver", "river_otter", "mink", "muskrat",
])

_HABITAT_PREFER_WATER = frozenset([
    "raccoon", "moose",  # forage near water but don't require it
])

_HABITAT_REQUIRE_FOREST = frozenset([
    "pine_marten", "fisher",
])

_HABITAT_REQUIRE_DENSE = frozenset([
    "wolverine", "lynx",  # remote, dense habitat
])

_HABITAT_PREFER_OPEN = frozenset([
    "pronghorn", "buffalo", "jackrabbit", "ground_squirrel", "badger",
])

_TREE_TERRAINS = frozenset([
    LocalTerrain.FOREST, LocalTerrain.PINE, LocalTerrain.OAK,
    LocalTerrain.ASPEN, LocalTerrain.CEDAR, LocalTerrain.MAPLE,
    LocalTerrain.CHESTNUT, LocalTerrain.HICKORY, LocalTerrain.CYPRESS,
    LocalTerrain.MAGNOLIA, LocalTerrain.JUNIPER,
])

_WATER_TERRAINS = frozenset([
    LocalTerrain.WATER, LocalTerrain.DEEP_WATER,
    LocalTerrain.BEAVER_POND, LocalTerrain.BEAVER_DAM,
])

_OPEN_TERRAINS = frozenset([
    LocalTerrain.GRASS, LocalTerrain.GROUND, LocalTerrain.SAND,
    LocalTerrain.TUNDRA,
])


def _has_terrain_nearby(lmap: LocalMap, x: int, y: int,
                        terrain_set: frozenset, radius: int = 5) -> bool:
    """Check if any tile in terrain_set exists within radius."""
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            nx, ny = x + dx, y + dy
            if lmap.in_bounds(nx, ny):
                if lmap.tiles[ny][nx].terrain in terrain_set:
                    return True
    return False


def _valid_spawn_pos(lmap: LocalMap, x: int, y: int, species_id: str) -> bool:
    """Check if position is valid for this species' habitat requirements."""
    if not _can_move_to(lmap, x, y):
        return False

    if species_id in _HABITAT_REQUIRE_WATER:
        return _has_terrain_nearby(lmap, x, y, _WATER_TERRAINS, radius=5)

    if species_id in _HABITAT_PREFER_WATER:
        # 70% chance of requiring water nearby, 30% anywhere
        return True  # checked during weighted selection instead

    if species_id in _HABITAT_REQUIRE_FOREST:
        return _has_terrain_nearby(lmap, x, y, _TREE_TERRAINS, radius=3)

    if species_id in _HABITAT_REQUIRE_DENSE:
        # Need multiple tree tiles nearby (dense forest)
        count = 0
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                nx, ny = x + dx, y + dy
                if lmap.in_bounds(nx, ny) and lmap.tiles[ny][nx].terrain in _TREE_TERRAINS:
                    count += 1
                    if count >= 4:
                        return True
        return False

    if species_id in _HABITAT_PREFER_OPEN:
        return _has_terrain_nearby(lmap, x, y, _OPEN_TERRAINS, radius=3)

    return True  # no special requirement


class WildlifeManager:
    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng  = random.Random(seed)
        # key = (world_x, world_y, area_x, area_y) → list of WildlifeInstance
        self.active: Dict[Tuple[int, int, int, int], List[WildlifeInstance]] = {}
        self._tick = 0   # global counter for attack rate-limiting

    # ── Spawning ─────────────────────────────────────────────────────────

    def spawn_for_local(self, lmap: LocalMap, world_x: int, world_y: int,
                        area_x: int = 7, area_y: int = 7, year: int = 1849,
                        season: str = "summer"):
        key = (world_x, world_y, area_x, area_y)
        if key in self.active:
            return

        self.active[key] = []
        candidates = _species_for_region(lmap._region_name)
        if not candidates:
            return

        # Apply era multipliers (species-specific historical curves)
        candidates = [(wt, w * _era_wildlife_mult(wt.value, year))
                      for wt, w in candidates]

        # Seasonal migration — herds move with the seasons
        # Buffalo/elk go to high ground in summer, low valleys in winter
        # Latitude (world_y) affects this: southern tiles warmer
        elev = getattr(lmap, 'world_elevation_ft', 0)
        _season_mods = []
        for wt, w in candidates:
            sid = wt.value if hasattr(wt, 'value') else str(wt)
            mult = 1.0
            if sid in ("buffalo", "elk", "pronghorn"):
                if season == "winter" and elev > 5000:
                    mult = 0.3  # herds move to lower ground
                elif season == "summer" and elev > 5000:
                    mult = 1.5  # summer high pastures
                elif season == "winter" and elev < 3000:
                    mult = 1.5  # winter lowland concentration
            elif sid == "whitetail_deer":
                if season == "winter":
                    mult = 0.7  # yard up, fewer visible
                elif season == "fall":
                    mult = 1.3  # rut, more active/visible
            _season_mods.append((wt, w * mult))
        candidates = _season_mods

        # Boost aquatic species if map has significant water
        water_count = 0
        sample_step = 8  # sample every 8th tile for speed
        for sy in range(0, lmap.height, sample_step):
            for sx in range(0, lmap.width, sample_step):
                if lmap.tiles[sy][sx].terrain in _WATER_TERRAINS:
                    water_count += 1
        water_rich = water_count > 5  # meaningful water presence

        if water_rich:
            # Boost aquatic furbearers on water-rich maps
            boosted = []
            for wt, w in candidates:
                sid = wt.value if hasattr(wt, 'value') else str(wt)
                if sid in _HABITAT_REQUIRE_WATER:
                    boosted.append((wt, w * 2.0))
                elif sid in _HABITAT_PREFER_WATER:
                    boosted.append((wt, w * 1.5))
                else:
                    boosted.append((wt, w))
            candidates = boosted
        else:
            # Suppress aquatic species on dry maps
            candidates = [(wt, w * 0.1 if (hasattr(wt, 'value') and
                           wt.value in _HABITAT_REQUIRE_WATER) else w)
                          for wt, w in candidates]

        # Filter out zero-weight candidates
        candidates = [(wt, w) for wt, w in candidates if w > 0.001]
        if not candidates:
            return

        # 2–6 animals; weighted by spawn_chance
        count = self.rng.randint(2, 6)
        types, weights = zip(*candidates)

        for _ in range(count):
            wt = self.rng.choices(types, weights=weights, k=1)[0]
            sp = WILDLIFE_DB[wt]
            sid = wt.value if hasattr(wt, 'value') else str(wt)

            for attempt in range(50):
                x = self.rng.randint(15, lmap.width  - 15)
                y = self.rng.randint(15, lmap.height - 15)
                if _valid_spawn_pos(lmap, x, y, sid):
                    animal = WildlifeInstance(wt, sp, x, y)
                    animal.local_z = lmap.ground_z(x, y)
                    self.active[key].append(animal)
                    break

    # ── Query ────────────────────────────────────────────────────────────

    def get_animals(self, world_x: int, world_y: int,
                    area_x: int = 7, area_y: int = 7) -> List[WildlifeInstance]:
        """Return all animals except fully butchered ones (dead bodies remain visible)."""
        return [a for a in self.active.get((world_x, world_y, area_x, area_y), [])
                if a.state != "butchered"]

    def get_at(self, world_x: int, world_y: int,
               area_x: int = 7, area_y: int = 7,
               lx: int = 0, ly: int = 0, lz: int = None) -> Optional[WildlifeInstance]:
        for a in self.get_animals(world_x, world_y, area_x, area_y):
            if a.local_x == lx and a.local_y == ly:
                if lz is None or a.local_z == lz:
                    return a
        return None

    # ── Per-tick update ──────────────────────────────────────────────────

    def update_all(self, minutes: int, player: "Player",
                   lmap: LocalMap) -> List[str]:
        """
        Move animals, handle proximity alerts/attacks.
        Returns list of message strings (attacks, sightings).
        Called from engine.advance_time when on local map.
        """
        self._tick += 1
        key = (lmap.world_x, lmap.world_y, lmap.area_x, lmap.area_y)
        animals = self.active.get(key, [])
        messages = []

        for animal in animals:
            if not animal.alive:
                continue

            # Tick wound bleeding; a wounded-fleeing animal may bleed out
            if animal.state in ("wounded_fleeing", "downed") and animal.wounds.is_bleeding:
                animal.wounds.tick(float(minutes))
                if not animal.wounds.alive and animal.state != "dead":
                    animal.state = "dead"
                    messages.append(
                        f"The {animal.species.display_name} bleeds out.")
                    continue

            dist = max(abs(animal.local_x - player.local_x),
                       abs(animal.local_y - player.local_y))
            sp   = animal.species
            dl   = sp.danger_level

            # ── Alert check ─────────────────────────────────────────────
            alert_d = _ALERT_DIST.get(dl, 10)
            if dist <= alert_d and not animal.alert:
                animal.alert = True

            # ── State transitions ────────────────────────────────────────
            if animal.state == "idle":
                flee_d = _FLEE_DIST.get(dl, 8)
                atk_d  = _ATTACK_DIST.get(dl, 999)
                if dl == 0 or dl == 1:
                    if dist <= flee_d:
                        animal.state = "fleeing"
                        if dist <= 4:
                            messages.append(
                                f"A {sp.display_name} bolts away from you!")
                elif dl == 2:
                    if dist <= atk_d:
                        animal.state = "hostile"
                        messages.append(f"A {sp.display_name} charges at you!")

            # Skip movement for downed/dead/butchered
            if animal.state in ("downed", "dead", "butchered"):
                continue

            # ── Movement ────────────────────────────────────────────────
            steps = max(1, minutes // 5)
            for _ in range(steps):
                if animal.state == "fleeing":
                    self._move_away(animal, player, lmap)
                elif animal.state == "wounded_fleeing":
                    self._move_away(animal, player, lmap)
                    animal.wound_flee_steps -= 1
                    if animal.wound_flee_steps <= 0:
                        animal.state = "downed"
                        messages.append(
                            f"The wounded {sp.display_name} stumbles and goes down.")
                        break
                elif animal.state == "hostile":
                    self._move_toward(animal, player, lmap)
                elif animal.state == "idle" and self.rng.random() < 0.3:
                    self._wander(animal, lmap)

            # ── Attack ──────────────────────────────────────────────────
            if animal.state == "hostile":
                cur_dist = max(abs(animal.local_x - player.local_x),
                               abs(animal.local_y - player.local_y))
                if cur_dist <= 1 and self._tick != animal.last_attack_tick:
                    animal.last_attack_tick = self._tick
                    dmg, msg = self._animal_attack(animal, player)
                    messages.append(msg)

        # ── Body decay ──────────────────────────────────────────────────
        # Dead animals decay over time. After ~24 hours → skeleton,
        # no longer butcherable. Attracts scavengers before that.
        current_min = getattr(self, '_game_minutes', 0)
        for animal in animals:
            if animal.state == "dead" and not animal.decayed:
                if animal.death_time == 0:
                    animal.death_time = current_min
                hours_dead = (current_min - animal.death_time) / 60.0
                # After 24 hours: decayed, can't butcher
                if hours_dead >= 24:
                    animal.decayed = True
                    animal.butchered = True  # nothing left to take
                    messages.append(
                        f"The {animal.species.display_name} carcass "
                        f"has rotted. Nothing left but bones.")
                # After 12 hours: warn
                elif hours_dead >= 12 and animal.recoverable:
                    if self.rng.random() < 0.05:  # occasional reminder
                        messages.append(
                            f"The {animal.species.display_name} carcass "
                            f"is starting to smell. Butcher it soon.")

        return messages

    # ── Movement helpers ─────────────────────────────────────────────────

    def _wander(self, animal: WildlifeInstance, lmap: LocalMap):
        dx = self.rng.choice([-1, 0, 0, 1])
        dy = self.rng.choice([-1, 0, 0, 1])
        nx, ny = animal.local_x + dx, animal.local_y + dy
        if _can_move_to(lmap, nx, ny):
            animal.local_x = nx
            animal.local_y = ny

    def _move_away(self, animal: WildlifeInstance, player: "Player",
                   lmap: LocalMap):
        """Move one step away from player."""
        pdx = animal.local_x - player.local_x
        pdy = animal.local_y - player.local_y
        dx  = 1 if pdx > 0 else (-1 if pdx < 0 else self.rng.choice([-1, 1]))
        dy  = 1 if pdy > 0 else (-1 if pdy < 0 else self.rng.choice([-1, 1]))
        nx, ny = animal.local_x + dx, animal.local_y + dy
        if _can_move_to(lmap, nx, ny):
            animal.local_x = nx
            animal.local_y = ny
        # Despawn once far enough away
        if max(abs(animal.local_x - player.local_x),
               abs(animal.local_y - player.local_y)) > 30:
            animal.state = "butchered"   # off-map, treat as gone

    def _move_toward(self, animal: WildlifeInstance, player: "Player",
                     lmap: LocalMap):
        """Move one step toward player (simple Chebyshev step)."""
        pdx = player.local_x - animal.local_x
        pdy = player.local_y - animal.local_y
        dx  = (1 if pdx > 0 else -1) if pdx != 0 else 0
        dy  = (1 if pdy > 0 else -1) if pdy != 0 else 0
        nx, ny = animal.local_x + dx, animal.local_y + dy
        if _can_move_to(lmap, nx, ny):
            animal.local_x = nx
            animal.local_y = ny

    # ── Attack resolution ────────────────────────────────────────────────

    @staticmethod
    def _animal_attack(animal: WildlifeInstance,
                       player: "Player") -> Tuple[float, str]:
        """Species-aware attack. Picks from attack profile for correct
        damage type and verb. Returns (dmg, message)."""
        sp = animal.species
        size_dmg = {"small": (1, 4), "medium": (3, 8),
                    "large": (8, 18), "very_large": (15, 30)}
        lo, hi = size_dmg.get(sp.size, (3, 8))
        dmg = random.randint(lo, hi)
        player.survival.health = max(0.0, player.survival.health - dmg)

        # Pick species-appropriate attack from profile
        profile = _ATK.get(animal.species_type, _DEFAULT_ATK)
        attacks = profile["attacks"]
        weights = profile["weights"]
        chosen = random.choices(attacks, weights=weights, k=1)[0]
        dtype, weapon_key, verb_lo, verb_mid, verb_hi = chosen

        # Apply wound with correct damage type and weapon profile
        wound = player.wounds.apply_hit(dmg, dtype,
                                          weapon_key=weapon_key if weapon_key else "",
                                          worn_equipment=player.worn)

        if dmg <= 5:
            verb = verb_lo
        elif dmg <= 12:
            verb = verb_mid
        else:
            verb = verb_hi

        bleed_note = f" [{wound.description}]" if wound.is_bleeding else ""
        msg = (f"The {sp.display_name} {verb} you for {dmg} damage!{bleed_note} "
               f"(Health: {player.survival.health:.0f})")
        return dmg, msg
