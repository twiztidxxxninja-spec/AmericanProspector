"""
Trapping system — place, trigger, check, harvest traps.

Traps are placed on map tiles as structures. They trigger passively
based on time, region, bait, skill, and proximity to other traps.
Animals caught can be skinned for pelts or released.

Pelt quality depends on: season, time in trap, skinning skill,
kill method, and randomness.
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.local_map import LocalMap
    from src.player import Player


# ── Pelt quality grades ───────────────────────────────────────────────────

PELT_GRADES = ["Ruined", "Damaged", "Poor", "Fair", "Good", "Fine", "Prime", "Flawless"]
PELT_GRADE_MULT = [0.0, 0.30, 0.50, 0.70, 1.00, 1.30, 1.60, 2.00]

# ── Trap types and what they catch ────────────────────────────────────────

TRAP_SPECIES = {
    "snare": ["jackrabbit", "cottontail_rabbit", "raccoon", "red_fox",
              "gray_fox", "pine_marten", "opossum", "skunk", "muskrat",
              "ground_squirrel", "wild_turkey", "passenger_pigeon",
              "prairie_dog"],
    "deadfall_trap": ["beaver", "pine_marten", "fisher", "raccoon", "mink",
                      "muskrat", "opossum", "cottontail_rabbit"],
    "steel_trap": ["beaver", "river_otter", "red_fox", "gray_fox", "coyote",
                   "bobcat", "lynx", "wolverine", "mink", "badger",
                   "wild_boar"],
    "bear_trap": ["grizzly_bear", "black_bear", "gray_wolf", "mountain_lion",
                  "wolverine", "wild_boar"],
}

# Species → pelt item ID mapping
SPECIES_PELT = {
    "beaver": "beaver_pelt", "red_fox": "fox_pelt", "gray_fox": "fox_pelt",
    "gray_wolf": "wolf_pelt", "coyote": "coyote_pelt", "raccoon": "raccoon_pelt",
    "bobcat": "bobcat_pelt", "river_otter": "otter_pelt", "mink": "mink_pelt",
    "pine_marten": "marten_pelt", "fisher": "fisher_pelt",
    "wolverine": "wolverine_pelt", "lynx": "lynx_pelt",
    "muskrat": "muskrat_pelt", "skunk": "skunk_pelt",
    "grizzly_bear": "bear_pelt", "black_bear": "bear_pelt",
    "mountain_lion": "cougar_pelt", "badger": "badger_pelt",
    "mule_deer": "deer_pelt", "black_tailed_deer": "deer_pelt",
    "whitetail_deer": "deer_pelt",
    "elk": "elk_pelt", "buffalo": "buffalo_robe",
    "opossum": "raccoon_pelt",  # similar low-value fur
    "wild_boar": "deer_pelt",   # hog skin similar processing
    "mountain_goat": "deer_pelt",
    "wild_horse": "deer_pelt",  # horse hide
    "cottontail_rabbit": "rabbit_pelt",
}


@dataclass
class PlacedTrap:
    """A trap placed on the local map."""
    trap_type: str           # snare, deadfall_trap, steel_trap, bear_trap
    x: int
    y: int
    world_x: int
    world_y: int
    area_x: int
    area_y: int
    bait: str = ""           # item name used as bait
    set_quality: int = 0     # from trapping skill check (0-10)
    time_set: int = 0        # game time (total_seconds) when placed
    caught_species: str = "" # species ID if caught
    caught_time: int = 0     # game time when animal was caught
    sprung: bool = False     # triggered but empty
    id: int = 0


class TrapManager:
    """Manages all placed traps across the game."""

    def __init__(self):
        self.traps: List[PlacedTrap] = []
        self._next_id = 1
        self._last_check_time = 0

    def place_trap(self, trap_type: str, x: int, y: int,
                   wx: int, wy: int, ax: int, ay: int,
                   bait: str, set_quality: int, game_time: int) -> PlacedTrap:
        trap = PlacedTrap(
            trap_type=trap_type, x=x, y=y,
            world_x=wx, world_y=wy, area_x=ax, area_y=ay,
            bait=bait, set_quality=set_quality,
            time_set=game_time, id=self._next_id,
        )
        self._next_id += 1
        self.traps.append(trap)
        return trap

    def remove_trap(self, trap_id: int) -> Optional[PlacedTrap]:
        for i, t in enumerate(self.traps):
            if t.id == trap_id:
                return self.traps.pop(i)
        return None

    def traps_at(self, wx, wy, ax, ay) -> List[PlacedTrap]:
        return [t for t in self.traps
                if t.world_x == wx and t.world_y == wy
                and t.area_x == ax and t.area_y == ay]

    def tick(self, game_time_seconds: int, region: str, season: str,
             rng: random.Random) -> List[str]:
        """Check traps for catches. Call from advance_time().
        Only checks every 4+ hours of game time."""
        messages = []
        check_interval = 4 * 3600  # 4 hours in seconds

        if game_time_seconds - self._last_check_time < check_interval:
            return messages
        self._last_check_time = game_time_seconds

        for trap in self.traps:
            if trap.caught_species or trap.sprung:
                continue  # already triggered

            # Base chance per check
            chance = 0.15

            # Bait bonus
            if trap.bait:
                chance *= 2.0
                if "castoreum" in trap.bait.lower():
                    chance *= 1.5  # castoreum is the best bait

            # Set quality (trapping skill)
            chance *= 1.0 + trap.set_quality * 0.05

            # Season — dramatic difference; winter pelts are prime
            if season == "winter":
                chance *= 1.5
            elif season == "fall":
                chance *= 1.2
            elif season == "spring":
                chance *= 0.8
            elif season == "summer":
                chance *= 0.4

            # Proximity penalty — traps too close reduce catch
            nearby = sum(1 for t2 in self.traps
                         if t2.id != trap.id
                         and t2.world_x == trap.world_x
                         and t2.world_y == trap.world_y
                         and t2.area_x == trap.area_x
                         and t2.area_y == trap.area_y
                         and abs(t2.x - trap.x) + abs(t2.y - trap.y) <= 10)
            if nearby > 0:
                chance *= 0.5 ** nearby

            if rng.random() < chance:
                # Caught something! Pick species based on trap type + region
                possible = TRAP_SPECIES.get(trap.trap_type, [])
                if possible:
                    species = rng.choice(possible)
                    trap.caught_species = species
                    trap.caught_time = game_time_seconds
                    messages.append(
                        f"One of your traps caught something! (trap #{trap.id})")
            elif rng.random() < 0.05:
                # Sprung empty
                trap.sprung = True
                messages.append(f"A trap sprung empty. (trap #{trap.id})")

        return messages

    def to_dict(self) -> dict:
        return {
            "traps": [
                {"trap_type": t.trap_type, "x": t.x, "y": t.y,
                 "world_x": t.world_x, "world_y": t.world_y,
                 "area_x": t.area_x, "area_y": t.area_y,
                 "bait": t.bait, "set_quality": t.set_quality,
                 "time_set": t.time_set, "caught_species": t.caught_species,
                 "caught_time": t.caught_time, "sprung": t.sprung, "id": t.id}
                for t in self.traps
            ],
            "next_id": self._next_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TrapManager":
        mgr = cls()
        mgr._next_id = d.get("next_id", 1)
        for td in d.get("traps", []):
            mgr.traps.append(PlacedTrap(**td))
        return mgr


# ── Pelt quality calculation ──────────────────────────────────────────────

def calculate_pelt_quality(season: str, time_in_trap_hours: float,
                           trapping_skill: int, kill_method: str,
                           has_skinning_knife: bool,
                           rng: random.Random) -> int:
    """Calculate pelt quality grade index (0=Ruined, 7=Flawless)."""
    grade = 4  # start at "Good" (index 4)

    # Season
    if season == "winter":
        grade += 2
    elif season == "fall":
        grade += 1
    elif season == "summer":
        grade -= 1

    # Time in trap
    if time_in_trap_hours > 24:
        grade -= 2
    elif time_in_trap_hours > 16:
        grade -= 1

    # Skinning skill
    if trapping_skill <= 2:
        grade -= 1
    elif trapping_skill >= 9:
        grade += 1

    # Skinning knife bonus
    if has_skinning_knife:
        grade += 1

    # Kill method
    if kill_method == "gunshot":
        grade -= 1
    elif kill_method == "mauled":
        grade -= 1

    # Randomness
    grade += rng.choice([-1, 0, 0, 0, 1])

    # Clamp
    return max(0, min(len(PELT_GRADES) - 1, grade))


def grade_name(grade_idx: int) -> str:
    return PELT_GRADES[max(0, min(grade_idx, len(PELT_GRADES) - 1))]


def grade_multiplier(grade_idx: int) -> float:
    return PELT_GRADE_MULT[max(0, min(grade_idx, len(PELT_GRADE_MULT) - 1))]
