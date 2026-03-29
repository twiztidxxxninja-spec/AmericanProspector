"""
src/dynamic_locations.py

Dynamic location system for American Prospector.
Handles temporary and semi-permanent locations that emerge through
NPC conversation, random travel events, and player activity.

These are NOT pre-generated at world creation — they surface when
the game needs them and then persist in the save file.

Location types:
    mining_camp     — cluster of prospectors around a strike
    prospector_camp — solo or small group camp
    native_camp     — Indigenous settlement (era-appropriate)
    waystation      — relay station, remote resupply
    abandoned_camp  — ruins of prior activity, scavengeable
    boomtown        — rapidly-grown settlement around a new find
    outlaw_camp     — hidden camp, hostile or cautious

Lifecycle:
    active → declining → abandoned → ruins (→ overgrown)
    Time-based: each "season" (90 game-days) without active mining
    degrades the location one tier.

Integration points:
    engine.py — holds a DynamicLocationDB on self.dynamic_locs
    rumor_system.py — calls dynamic_locs.from_npc_rumor(npc, region, year)
    engine._travel_event() — calls dynamic_locs.from_travel_event(...)
    engine._ensure_local() — calls dynamic_locs.get_at(wx, wy) to add NPCs

Save/load:
    Call DynamicLocationDB.to_dict() / from_dict() alongside other game state.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import random


# ── Constants ───────────────────────────────────────────────────────────────

class LocationType:
    MINING_CAMP     = "mining_camp"
    PROSPECTOR_CAMP = "prospector_camp"
    NATIVE_CAMP     = "native_camp"
    WAYSTATION      = "waystation"
    ABANDONED_CAMP  = "abandoned_camp"
    BOOMTOWN        = "boomtown"
    OUTLAW_CAMP     = "outlaw_camp"


class LifecycleStage:
    ACTIVE    = "active"
    DECLINING = "declining"
    ABANDONED = "abandoned"
    RUINS     = "ruins"
    OVERGROWN = "overgrown"


# Approximate population ranges per type and stage
_POP_RANGES = {
    LocationType.MINING_CAMP:     {"active": (8, 80),  "declining": (2, 20), "abandoned": (0, 0)},
    LocationType.PROSPECTOR_CAMP: {"active": (1, 6),   "declining": (1, 2),  "abandoned": (0, 0)},
    LocationType.NATIVE_CAMP:     {"active": (10, 120), "declining": (5, 30), "abandoned": (0, 0)},
    LocationType.WAYSTATION:      {"active": (2, 8),   "declining": (1, 3),  "abandoned": (0, 0)},
    LocationType.BOOMTOWN:        {"active": (50, 600),"declining": (10, 80),"abandoned": (0, 0)},
    LocationType.OUTLAW_CAMP:     {"active": (3, 20),  "declining": (1, 5),  "abandoned": (0, 0)},
    LocationType.ABANDONED_CAMP:  {"active": (0, 0),   "declining": (0, 0),  "abandoned": (0, 0)},
}

# Seasons (90-day periods) before location degrades one tier
_SEASONS_TO_DEGRADE = {
    LocationType.MINING_CAMP:     2,
    LocationType.PROSPECTOR_CAMP: 1,
    LocationType.NATIVE_CAMP:     4,
    LocationType.WAYSTATION:      6,
    LocationType.BOOMTOWN:        3,
    LocationType.OUTLAW_CAMP:     1,
    LocationType.ABANDONED_CAMP:  8,   # ruins take a long time to fully vanish
}

_LIFECYCLE_ORDER = [
    LifecycleStage.ACTIVE,
    LifecycleStage.DECLINING,
    LifecycleStage.ABANDONED,
    LifecycleStage.RUINS,
    LifecycleStage.OVERGROWN,
]


@dataclass
class DynamicLocation:
    """
    A location not pre-placed at world creation, but generated
    through gameplay events.
    """
    id: str                          # unique key, e.g. "mining_camp_95_165_0"
    name: str
    loc_type: str                    # LocationType constant
    world_x: int
    world_y: int
    population: int = 0
    stage: str = LifecycleStage.ACTIVE
    era_founded: int = 1849          # game year it appeared
    resource_type: str = ""          # "placer_gold" | "lode_silver" | "oil" | ""
    tribe: str = ""                  # for native_camp: e.g. "Paiute", "Crow"
    notes: str = ""                  # one-line description for NPC dialogue
    seasons_idle: int = 0            # seasons since last player or NPC activity
    discovered: bool = False         # player has been here or heard of it
    loot_taken: bool = False         # abandoned camp has been searched

    # Optional precise local-map coordinates within the world tile
    local_x: Optional[int] = None
    local_y: Optional[int] = None

    def is_visible(self) -> bool:
        """True if NPCs can mention this location and it can appear on map."""
        return self.stage not in (LifecycleStage.OVERGROWN,)

    def npc_description(self) -> str:
        """Short description for NPC dialogue, adapted to lifecycle stage."""
        if self.stage == LifecycleStage.ACTIVE:
            pop_str = f"{self.population} men" if self.population > 1 else "a lone prospector"
            return f"{self.name} — {self.notes} ({pop_str})"
        if self.stage == LifecycleStage.DECLINING:
            return f"{self.name} — {self.notes} (mostly worked out, a few men left)"
        if self.stage == LifecycleStage.ABANDONED:
            return f"{self.name} — abandoned camp, {self.notes}"
        if self.stage == LifecycleStage.RUINS:
            return f"{self.name} — ruins, barely anything left"
        return ""


class DynamicLocationDB:
    """
    Registry of all dynamic locations generated during a game session.

    Indexed by (world_x, world_y) for fast spatial lookup.
    Also indexed by id string for direct access.

    Usage:
        self.dynamic_locs = DynamicLocationDB()

        # From NPC rumour:
        loc = self.dynamic_locs.from_npc_rumor(npc, player, world_map, year, rng)

        # From travel event:
        loc = self.dynamic_locs.from_travel_event(wx, wy, terrain, year, rng)

        # Query:
        nearby = self.dynamic_locs.get_nearby(wx, wy, radius=5)

        # Time advance (call each in-game season = 90 days):
        self.dynamic_locs.age_one_season(year)
    """

    def __init__(self):
        self._by_id:  Dict[str, DynamicLocation] = {}
        self._by_pos: Dict[Tuple[int, int], List[str]] = {}  # pos → [id, ...]
        self._counter: int = 0

    # ── Internal helpers ───────────────────────────────────────────────────

    def _new_id(self, loc_type: str, wx: int, wy: int) -> str:
        self._counter += 1
        return f"{loc_type}_{wx}_{wy}_{self._counter}"

    def add(self, loc: DynamicLocation) -> DynamicLocation:
        """Add an externally-created location to the registry."""
        if not loc.id:
            loc.id = self._new_id(loc.loc_type, loc.world_x, loc.world_y)
        return self._register(loc)

    def _register(self, loc: DynamicLocation) -> DynamicLocation:
        self._by_id[loc.id] = loc
        pos = (loc.world_x, loc.world_y)
        if pos not in self._by_pos:
            self._by_pos[pos] = []
        self._by_pos[pos].append(loc.id)
        return loc

    # ── Query ──────────────────────────────────────────────────────────────

    def get(self, loc_id: str) -> Optional[DynamicLocation]:
        return self._by_id.get(loc_id)

    def get_at(self, wx: int, wy: int) -> List[DynamicLocation]:
        """All locations at exactly this world tile."""
        ids = self._by_pos.get((wx, wy), [])
        return [self._by_id[i] for i in ids if i in self._by_id]

    def get_nearby(self, wx: int, wy: int,
                   radius: int = 6) -> List[DynamicLocation]:
        """All visible locations within Chebyshev radius."""
        results = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                for loc in self.get_at(wx + dx, wy + dy):
                    if loc.is_visible():
                        results.append(loc)
        return results

    def get_all_active(self) -> List[DynamicLocation]:
        return [loc for loc in self._by_id.values()
                if loc.stage == LifecycleStage.ACTIVE]

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def mark_visited(self, loc_id: str) -> None:
        """Call when the player enters a dynamic location's world tile."""
        loc = self._by_id.get(loc_id)
        if loc:
            loc.discovered = True
            loc.seasons_idle = 0

    def age_one_season(self, current_year: int) -> List[DynamicLocation]:
        """
        Advance all locations by one season (90 game-days).
        Returns list of locations that degraded this season.
        """
        degraded = []
        for loc in list(self._by_id.values()):
            loc.seasons_idle += 1
            threshold = _SEASONS_TO_DEGRADE.get(loc.loc_type, 3)
            if loc.seasons_idle >= threshold:
                loc.seasons_idle = 0
                idx = _LIFECYCLE_ORDER.index(loc.stage)
                if idx < len(_LIFECYCLE_ORDER) - 1:
                    loc.stage = _LIFECYCLE_ORDER[idx + 1]
                    # Update population for new stage
                    ranges = _POP_RANGES.get(loc.loc_type, {})
                    stage_key = loc.stage if loc.stage in ranges else "abandoned"
                    lo, hi = ranges.get(stage_key, (0, 0))
                    loc.population = random.randint(lo, hi) if hi > 0 else 0
                    degraded.append(loc)
                if loc.stage == LifecycleStage.OVERGROWN:
                    # Remove from spatial index but keep id record for history
                    pos = (loc.world_x, loc.world_y)
                    if pos in self._by_pos:
                        self._by_pos[pos] = [i for i in self._by_pos[pos]
                                              if i != loc.id]
        return degraded

    # ── Factory: from NPC rumour ───────────────────────────────────────────

    def from_npc_rumor(self, player_x: int, player_y: int,
                        region: str, year: int,
                        rng: random.Random,
                        resource_type: str = "placer_gold"
                        ) -> Optional[DynamicLocation]:
        """
        Generate a dynamic mining camp or prospector camp that an NPC
        claims to know about.  Placed 3–12 world tiles from the player.

        Returns None if no suitable position could be found.
        """
        attempts = 20
        for _ in range(attempts):
            dx = rng.randint(-12, 12)
            dy = rng.randint(-12, 12)
            dist = abs(dx) + abs(dy)
            if dist < 3:
                continue
            wx, wy = player_x + dx, player_y + dy

            # Don't stack at an existing dynamic location
            if self.get_at(wx, wy):
                continue

            if rng.random() < 0.35:
                loc = _make_mining_camp(self._new_id, wx, wy, year,
                                        resource_type, rng)
            else:
                loc = _make_prospector_camp(self._new_id, wx, wy, year, rng)

            return self._register(loc)
        return None

    def from_travel_event(self, wx: int, wy: int,
                           world_terrain: int, year: int,
                           rng: random.Random) -> Optional[DynamicLocation]:
        """
        Potentially generate a location when the player manually travels
        through (wx, wy).  Called from engine's travel loop — returns
        None most of the time (low probability event).
        """
        # Already something here
        existing = self.get_at(wx, wy)
        if existing:
            existing[0].discovered = True
            return existing[0]

        from src.world_map import Terrain
        # Type probabilities by terrain
        roll = rng.random()
        if world_terrain in (Terrain.MOUNTAINS, Terrain.HILLS):
            if roll < 0.04:
                loc = _make_prospector_camp(self._new_id, wx, wy, year, rng)
                return self._register(loc)
            if roll < 0.08 and year >= 1849:
                loc = _make_abandoned_camp(self._new_id, wx, wy, year, rng)
                return self._register(loc)
        elif world_terrain in (Terrain.PLAINS, Terrain.PRAIRIE):
            if roll < 0.03 and year < 1880:
                loc = _make_native_camp(self._new_id, wx, wy, year, rng)
                return self._register(loc)
            if roll < 0.05:
                loc = _make_waystation(self._new_id, wx, wy, year, rng)
                return self._register(loc)
        return None

    def add_player_camp(self, wx: int, wy: int,
                         player_name: str, year: int) -> DynamicLocation:
        """
        Register the player's own camp when they set up at a location.
        Persists as a known waypoint on their map.
        """
        loc = _make_prospector_camp(self._new_id, wx, wy, year,
                                     random.Random())
        loc.name = f"{player_name}'s Camp"
        loc.notes = "Your own camp."
        loc.discovered = True
        return self._register(loc)

    # ── Serialization ──────────────────────────────────────────────────────

    def to_dict(self) -> Dict:
        return {
            "counter": self._counter,
            "locations": [
                {k: v for k, v in loc.__dict__.items()}
                for loc in self._by_id.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "DynamicLocationDB":
        db = cls()
        db._counter = data.get("counter", 0)
        for ldata in data.get("locations", []):
            loc = DynamicLocation(**ldata)
            db._by_id[loc.id] = loc
            pos = (loc.world_x, loc.world_y)
            if pos not in db._by_pos:
                db._by_pos[pos] = []
            db._by_pos[pos].append(loc.id)
        return db


# ── Location factory functions ───────────────────────────────────────────────

def _make_mining_camp(id_fn, wx: int, wy: int, year: int,
                       resource_type: str,
                       rng: random.Random) -> DynamicLocation:
    pop = rng.randint(8, 80)
    flavors = {
        "placer_gold": [
            "Creek placer diggings, rockers set up along the bank.",
            "Ravine camp — men working benches above the creek.",
            "Bar camp on a gravel flat, sluices running.",
        ],
        "lode_silver": [
            "Hard rock camp — a short adit driven into the hillside.",
            "Prospect shaft, windlass rig on the collar.",
        ],
        "oil": [
            "Cable tool rig, smell of crude on the air.",
            "Seep camp — men bailing oil from a hand-dug sump.",
        ],
        "coal": [
            "Drift mine into the seam face, tipple at the entrance.",
        ],
    }
    note_list = flavors.get(resource_type, ["Mining camp."])
    name_words = ["Gulch", "Creek", "Fork", "Bar", "Flat", "Bench", "Ledge"]
    name = f"{rng.choice(['Rich', 'Lucky', 'Dry', 'Cold', 'Deep', 'High'])} {rng.choice(name_words)} Camp"

    return DynamicLocation(
        id="",   # filled by _register via id_fn
        name=name,
        loc_type=LocationType.MINING_CAMP,
        world_x=wx, world_y=wy,
        population=pop,
        stage=LifecycleStage.ACTIVE,
        era_founded=year,
        resource_type=resource_type,
        notes=rng.choice(note_list),
        discovered=False,
    )


def _make_prospector_camp(id_fn, wx: int, wy: int, year: int,
                            rng: random.Random) -> DynamicLocation:
    pop = rng.randint(1, 4)
    notes_choices = [
        "A lone prospector's tent, pan and rocker nearby.",
        "Small camp — two men working the creek bend.",
        "Canvas tent, mule picketed by the water.",
        "Crude brush shelter, bedroll inside.",
    ]
    first_names = ["J.", "T.", "W.", "R.", "H.", "E.", "M."]
    last_names  = ["Smith", "Brown", "Jones", "Davis", "Wilson",
                   "Moore", "Taylor", "Anderson", "Thomas", "White"]
    name = f"{rng.choice(first_names)} {rng.choice(last_names)}'s Camp"
    return DynamicLocation(
        id="",
        name=name,
        loc_type=LocationType.PROSPECTOR_CAMP,
        world_x=wx, world_y=wy,
        population=pop,
        stage=LifecycleStage.ACTIVE,
        era_founded=year,
        notes=rng.choice(notes_choices),
        discovered=False,
    )


def _make_native_camp(id_fn, wx: int, wy: int, year: int,
                       rng: random.Random) -> DynamicLocation:
    # Era-appropriate tribes by approximate world-map region (rough)
    # In practice the engine should cross-reference region_name
    tribes_by_era = {
        1849: ["Miwok", "Maidu", "Paiute", "Shoshone", "Crow",
               "Cheyenne", "Sioux", "Nez Perce", "Yakama", "Chinook"],
        1870: ["Crow", "Lakota Sioux", "Northern Cheyenne", "Arapaho",
               "Comanche", "Apache", "Navajo"],
        1890: ["Navajo", "Apache", "Lakota", "Crow"],
    }
    era_key = max(k for k in tribes_by_era if k <= year)
    tribe = rng.choice(tribes_by_era[era_key])

    pop = rng.randint(10, 80)
    notes_choices = [
        f"{tribe} seasonal camp — hide-covered lodges.",
        f"{tribe} band, traveling through traditional territory.",
        f"Small {tribe} village, women scraping hides outside.",
    ]
    return DynamicLocation(
        id="",
        name=f"{tribe} Camp",
        loc_type=LocationType.NATIVE_CAMP,
        world_x=wx, world_y=wy,
        population=pop,
        stage=LifecycleStage.ACTIVE,
        era_founded=year,
        tribe=tribe,
        notes=rng.choice(notes_choices),
        discovered=False,
    )


def _make_waystation(id_fn, wx: int, wy: int, year: int,
                      rng: random.Random) -> DynamicLocation:
    types = [
        ("Stage stop",   "Mud-walled stage stop, water trough and corral."),
        ("Relay station","Pony Express or telegraph relay — sparse but stocked."),
        ("Road ranch",   "Sod-walled road ranch, sells flour and beans at robbery prices."),
        ("Toll crossing","Rope ferry crossing, operator charges by weight."),
    ]
    t_name, t_notes = rng.choice(types)
    return DynamicLocation(
        id="",
        name=t_name,
        loc_type=LocationType.WAYSTATION,
        world_x=wx, world_y=wy,
        population=rng.randint(2, 6),
        stage=LifecycleStage.ACTIVE,
        era_founded=year,
        notes=t_notes,
        discovered=False,
    )


def _make_abandoned_camp(id_fn, wx: int, wy: int, year: int,
                           rng: random.Random) -> DynamicLocation:
    notes_choices = [
        "Collapsed tent frame, rusted pan in the brush.",
        "Old rocker box rotting beside a worked-out bar.",
        "Stone firepit, tin cans — left in a hurry.",
        "Claim stakes still driven in, no one here for years.",
    ]
    return DynamicLocation(
        id="",
        name="Abandoned Camp",
        loc_type=LocationType.ABANDONED_CAMP,
        world_x=wx, world_y=wy,
        population=0,
        stage=LifecycleStage.ABANDONED,
        era_founded=max(1848, year - rng.randint(1, 10)),
        notes=rng.choice(notes_choices),
        discovered=False,
        loot_taken=False,
    )
