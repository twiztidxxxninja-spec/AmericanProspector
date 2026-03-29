"""
Fire spread simulation. Fire ignites flammable tiles, spreads to neighbors,
and burns out over time. Different materials catch at different rates.

Tick this every game-minute from engine.advance_time().
"""

from typing import Dict, Set, Tuple, List, TYPE_CHECKING

if TYPE_CHECKING:
    from src.local_map import LocalMap

from src.local_map import LocalTerrain


# ── Flammability: how many ticks of adjacent fire before ignition ─────────
# Lower = catches faster. 0 = not flammable.
IGNITE_TICKS: Dict[int, int] = {
    LocalTerrain.BRUSH:       2,    # dry brush — catches almost instantly
    LocalTerrain.GRASS:       3,    # dry grass — fast
    LocalTerrain.DOWNED_TREE: 4,    # fallen timber — catches quick
    LocalTerrain.WORKED_DIRT: 0,    # dirt doesn't burn
    LocalTerrain.PINE:        8,    # standing pine — resinous, catches eventually
    LocalTerrain.OAK:         12,   # hardwood — slow to catch
    LocalTerrain.ASPEN:       7,    # thin bark
    LocalTerrain.JUNIPER:     6,    # oily, burns well
    LocalTerrain.CEDAR:       9,    # thick bark, slow start then hot
    LocalTerrain.MAPLE:       10,
    LocalTerrain.CHESTNUT:    11,
    LocalTerrain.HICKORY:     12,
    LocalTerrain.CYPRESS:     14,   # wet swamp wood — hardest to light
    LocalTerrain.MAGNOLIA:    10,
    LocalTerrain.FOREST:      10,   # dense forest
    LocalTerrain.SPOIL_PILE:  0,    # dirt/rock
    LocalTerrain.TAILINGS:    0,
    LocalTerrain.GROUND:      0,
    LocalTerrain.ROCK:        0,
    LocalTerrain.WATER:       0,
    LocalTerrain.GRAVEL_BAR:  0,
    LocalTerrain.BEDROCK:     0,
    LocalTerrain.MUD:         0,
    LocalTerrain.SAND:        0,
    LocalTerrain.TUNDRA:      0,
}

# How long a tile burns before turning to ash (ticks)
BURN_DURATION: Dict[int, int] = {
    LocalTerrain.BRUSH:       5,
    LocalTerrain.GRASS:       3,
    LocalTerrain.DOWNED_TREE: 15,
    LocalTerrain.PINE:        20,
    LocalTerrain.OAK:         25,
    LocalTerrain.ASPEN:       12,
    LocalTerrain.JUNIPER:     15,
    LocalTerrain.CEDAR:       22,
    LocalTerrain.MAPLE:       20,
    LocalTerrain.CHESTNUT:    22,
    LocalTerrain.HICKORY:     25,
    LocalTerrain.CYPRESS:     18,
    LocalTerrain.MAGNOLIA:    18,
    LocalTerrain.FOREST:      20,
}

# What a tile becomes after burning out
BURN_RESULT = LocalTerrain.GROUND  # charred ground


class FireSystem:
    """Tracks active fires on a local map. Tick once per game-minute."""

    def __init__(self):
        # Tiles currently on fire: (x, y) → ticks_remaining
        self.burning: Dict[Tuple[int, int], int] = {}
        # Tiles being heated by adjacent fire: (x, y) → heat_accumulated
        self.heating: Dict[Tuple[int, int], int] = {}

    @property
    def active(self) -> bool:
        return len(self.burning) > 0

    def ignite(self, x: int, y: int, lmap: "LocalMap") -> bool:
        """Start a fire at (x, y). Returns True if tile is flammable."""
        if not lmap.in_bounds(x, y):
            return False
        if (x, y) in self.burning:
            return True  # already on fire
        terrain = lmap.tiles[y][x].terrain
        duration = BURN_DURATION.get(terrain, 0)
        if duration <= 0:
            return False  # not flammable
        self.burning[(x, y)] = duration
        return True

    def tick(self, lmap: "LocalMap") -> List[str]:
        """Advance fire by one tick (1 game-minute). Returns messages."""
        messages = []

        # ── Spread heat to neighbors of burning tiles ─────────────
        new_heating: Dict[Tuple[int, int], int] = dict(self.heating)
        for (bx, by) in list(self.burning.keys()):
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    if dx == 0 and dy == 0:
                        continue
                    nx, ny = bx + dx, by + dy
                    if not lmap.in_bounds(nx, ny):
                        continue
                    if (nx, ny) in self.burning:
                        continue
                    terrain = lmap.tiles[ny][nx].terrain
                    threshold = IGNITE_TICKS.get(terrain, 0)
                    if threshold <= 0:
                        continue  # not flammable
                    new_heating[(nx, ny)] = new_heating.get((nx, ny), 0) + 1
        self.heating = new_heating

        # ── Ignite tiles that have accumulated enough heat ────────
        for (hx, hy), heat in list(self.heating.items()):
            if (hx, hy) in self.burning:
                continue
            terrain = lmap.tiles[hy][hx].terrain
            threshold = IGNITE_TICKS.get(terrain, 0)
            if threshold > 0 and heat >= threshold:
                duration = BURN_DURATION.get(terrain, 10)
                self.burning[(hx, hy)] = duration
                del self.heating[(hx, hy)]
                # Get terrain name for message
                _NAMES = {
                    LocalTerrain.BRUSH: "brush", LocalTerrain.GRASS: "grass",
                    LocalTerrain.PINE: "a pine tree", LocalTerrain.OAK: "an oak",
                    LocalTerrain.FOREST: "the forest", LocalTerrain.DOWNED_TREE: "fallen timber",
                }
                name = _NAMES.get(terrain, "something")
                if len(self.burning) <= 5:  # don't spam for big fires
                    messages.append(f"The fire catches {name}!")

        # ── Burn down active fires ────────────────────────────────
        burned_out = []
        for (bx, by) in list(self.burning.keys()):
            self.burning[(bx, by)] -= 1
            if self.burning[(bx, by)] <= 0:
                burned_out.append((bx, by))

        for (bx, by) in burned_out:
            del self.burning[(bx, by)]
            if lmap.in_bounds(bx, by):
                lmap.tiles[by][bx].terrain = BURN_RESULT
            if (bx, by) in self.heating:
                del self.heating[(bx, by)]

        if burned_out and len(burned_out) <= 3:
            messages.append("The fire dies down in places.")

        return messages

    def get_fire_tiles(self) -> Set[Tuple[int, int]]:
        """Return set of (x, y) tiles currently on fire."""
        return set(self.burning.keys())

    def get_heat_tiles(self) -> Set[Tuple[int, int]]:
        """Return set of (x, y) tiles being heated (about to catch)."""
        return set(self.heating.keys())
