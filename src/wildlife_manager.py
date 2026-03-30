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


class WildlifeManager:
    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng  = random.Random(seed)
        # key = (world_x, world_y, area_x, area_y) → list of WildlifeInstance
        self.active: Dict[Tuple[int, int, int, int], List[WildlifeInstance]] = {}
        self._tick = 0   # global counter for attack rate-limiting

    # ── Spawning ─────────────────────────────────────────────────────────

    def spawn_for_local(self, lmap: LocalMap, world_x: int, world_y: int,
                        area_x: int = 7, area_y: int = 7):
        key = (world_x, world_y, area_x, area_y)
        if key in self.active:
            return

        self.active[key] = []
        candidates = _species_for_region(lmap._region_name)
        if not candidates:
            return

        # 2–6 animals; weighted by spawn_chance
        count = self.rng.randint(2, 6)
        types, weights = zip(*candidates)

        for _ in range(count):
            wt = self.rng.choices(types, weights=weights, k=1)[0]
            sp = WILDLIFE_DB[wt]

            for attempt in range(50):
                x = self.rng.randint(15, lmap.width  - 15)
                y = self.rng.randint(15, lmap.height - 15)
                if _can_move_to(lmap, x, y):
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
            animal.state = "dead"   # off-map, treat as gone

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
