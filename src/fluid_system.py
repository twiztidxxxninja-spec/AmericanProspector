"""
src/fluid_system.py

3D fluid physics for American Prospector.
Water flows DOWN z-levels first (gravity), then laterally (pressure).
Streams sit at their surface elevation and flow naturally downhill.
Waterfalls form at cliff edges. Mine shafts flood near the water table.

Architecture:
    - Surface fluid stored in a 2D grid (fast, covers all streams)
    - Non-surface fluid (underground, above-surface) in sparse dict
    - Simulation runs per-step, gravity-first priority
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import random

from src.local_map import LocalTerrain


class FluidType:
    WATER = 0


@dataclass
class FluidTile:
    fluid_type: int = FluidType.WATER
    level: int = 0          # 0-7 (DF-style depth)
    pressure: int = 0
    is_source: bool = False # infinite water (stream head)
    is_sink: bool = False


class FluidSystem:
    """
    3D fluid simulation. Surface fluids in a 2D grid for performance.
    Non-surface fluids in sparse dict keyed by (x, y, z).
    """

    MAX_LEVEL = 7

    def __init__(self, local_map):
        self.local_map = local_map
        # Surface-level fluid (cheap 2D grid — matches existing behavior)
        self.surface_fluid: List[List[FluidTile]] = [
            [FluidTile() for _ in range(local_map.width)]
            for _ in range(local_map.height)
        ]
        # Non-surface fluid (sparse — only where water has flowed underground/above)
        self.z_fluid: Dict[Tuple[int, int, int], FluidTile] = {}

    # ── Initialization ─────────────────────────────────────────────────

    def initialize_streams(self):
        """Set up flowing water after stream generation."""
        for y in range(self.local_map.height):
            for x in range(self.local_map.width):
                tile = self.local_map.tiles[y][x]
                if tile.terrain == LocalTerrain.WATER:
                    self.surface_fluid[y][x].level = self.MAX_LEVEL
                    self.surface_fluid[y][x].is_source = True

    # ── Access ─────────────────────────────────────────────────────────

    def get_fluid_level(self, x: int, y: int, z: int = None) -> int:
        """Get fluid level at position. z=None means surface."""
        if not self.local_map.in_bounds(x, y):
            return 0
        if z is None:
            return self.surface_fluid[y][x].level
        sz = int(self.local_map.surface_z[y][x])
        if z == sz:
            return self.surface_fluid[y][x].level
        ft = self.z_fluid.get((x, y, z))
        return ft.level if ft else 0

    def get_fluid_tile(self, x: int, y: int, z: int) -> FluidTile:
        """Get or create fluid tile at (x, y, z)."""
        sz = int(self.local_map.surface_z[y][x])
        if z == sz:
            return self.surface_fluid[y][x]
        key = (x, y, z)
        if key not in self.z_fluid:
            self.z_fluid[key] = FluidTile()
        return self.z_fluid[key]

    def add_fluid(self, x: int, y: int, amount: int = 7,
                   z: int = None, fluid_type: int = FluidType.WATER):
        """Add water at a position."""
        if not self.local_map.in_bounds(x, y):
            return
        if z is None:
            sz = int(self.local_map.surface_z[y][x])
            z = sz
        ft = self.get_fluid_tile(x, y, z)
        ft.level = min(self.MAX_LEVEL, ft.level + amount)
        ft.fluid_type = fluid_type

    def remove_fluid(self, x: int, y: int, amount: int, z: int = None):
        """Remove water (sluicing, evaporation)."""
        if not self.local_map.in_bounds(x, y):
            return
        if z is None:
            self.surface_fluid[y][x].level = max(
                0, self.surface_fluid[y][x].level - amount)
        else:
            ft = self.z_fluid.get((x, y, z))
            if ft:
                ft.level = max(0, ft.level - amount)

    # ── Simulation ─────────────────────────────────────────────────────

    def simulate_step(self) -> bool:
        """
        One simulation step. Returns True if anything changed.

        Priority order:
        1. Gravity: water at any z flows DOWN to z-1 if there's open space
        2. Lateral: water flows sideways to tiles with lower level (pressure)
        3. Sources refill, sinks drain
        """
        updated = False
        lm = self.local_map

        # ── Phase 1: Surface water — gravity to lower z-levels ─────────
        for y in range(lm.height):
            for x in range(lm.width):
                sf = self.surface_fluid[y][x]
                if sf.level == 0:
                    continue
                sz = int(lm.surface_z[y][x])

                # Can water flow down to z-1?
                below_z = sz - 1
                below_tile = lm.z_tiles.get((x, y, below_z))
                if below_tile is not None:
                    # There's an open space below (player dug it out)
                    below_fluid = self.get_fluid_tile(x, y, below_z)
                    if below_fluid.level < self.MAX_LEVEL:
                        space = self.MAX_LEVEL - below_fluid.level
                        move = min(sf.level, space)
                        if move > 0 and not sf.is_source:
                            sf.level -= move
                            below_fluid.level += move
                            updated = True
                            continue

                # Can water flow laterally to lower-elevation surface tiles?
                for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                    nx, ny = x + dx, y + dy
                    if not lm.in_bounds(nx, ny):
                        continue
                    nsz = int(lm.surface_z[ny][nx])
                    nf = self.surface_fluid[ny][nx]

                    # Flow downhill to lower surface
                    if nsz < sz and nf.level < self.MAX_LEVEL:
                        move = min(sf.level, self.MAX_LEVEL - nf.level, 3)
                        if move > 0 and not sf.is_source:
                            sf.level -= move
                            nf.level += move
                            # Set terrain to water if enough flow
                            if nf.level >= 4:
                                lm.tiles[ny][nx].terrain = LocalTerrain.WATER
                            updated = True
                            break  # one direction per step

                    # Same-level pressure flow
                    elif nsz == sz and nf.level < sf.level - 1:
                        move = min(sf.level - nf.level - 1, 2)
                        if move > 0 and not sf.is_source:
                            sf.level -= move
                            nf.level += move
                            updated = True

                # Source refill
                if sf.is_source and sf.level < self.MAX_LEVEL:
                    sf.level = self.MAX_LEVEL

                # Sink drain
                if sf.is_sink and sf.level > 0 and not sf.is_source:
                    sf.level -= 1
                    updated = True

        # ── Phase 2: Underground water — gravity first, then lateral ───
        for (x, y, z), ft in list(self.z_fluid.items()):
            if ft.level == 0:
                continue

            # Gravity: flow down to z-1
            below_z = z - 1
            below_tile = lm.z_tiles.get((x, y, below_z))
            if below_tile is not None:
                below_ft = self.get_fluid_tile(x, y, below_z)
                if below_ft.level < self.MAX_LEVEL:
                    space = self.MAX_LEVEL - below_ft.level
                    move = min(ft.level, space)
                    if move > 0:
                        ft.level -= move
                        below_ft.level += move
                        updated = True
                        continue

            # Lateral flow at same z-level
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nx, ny = x + dx, y + dy
                if not lm.in_bounds(nx, ny):
                    continue
                # Only flow to open spaces at this z
                neighbor_tile = lm.tile_at_z(nx, ny, z)
                if neighbor_tile is None:
                    continue  # solid rock
                nft = self.get_fluid_tile(nx, ny, z)
                if nft.level < ft.level - 1:
                    move = min(ft.level - nft.level - 1, 2)
                    if move > 0:
                        ft.level -= move
                        nft.level += move
                        updated = True

        return updated

    # ── Query helpers ──────────────────────────────────────────────────

    def is_flooded(self, x: int, y: int, z: int) -> bool:
        """Is this tile flooded (water level >= 4)?"""
        return self.get_fluid_level(x, y, z) >= 4

    def water_table_z(self, x: int, y: int) -> int:
        """Approximate water table z-level at (x, y).
        Used to warn players about flooding risk when mining."""
        sz = int(self.local_map.surface_z[y][x])
        # Water table is roughly at the lowest nearby stream elevation
        if self.surface_fluid[y][x].level > 0:
            return sz
        # Check nearby for water
        for r in range(1, 10):
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    nx, ny = x + dx, y + dy
                    if self.local_map.in_bounds(nx, ny):
                        if self.surface_fluid[ny][nx].level > 0:
                            return int(self.local_map.surface_z[ny][nx])
        return sz - 10  # deep default if no water nearby
