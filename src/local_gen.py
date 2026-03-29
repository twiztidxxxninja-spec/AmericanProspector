"""
src/local_gen.py

Noise-based terrain generator for LocalMap.
Replaces the scatter_grid ellipse approach with multi-octave value noise,
producing natural forests with clearings, irregular edges, and organic
terrain transitions instead of blocky solid masses.

Integration — in local_map.py LocalMap._generate(), replace the block of
regional generator calls with:

    from src.local_gen import LocalGenerator
    LocalGenerator(self, self.seed).generate(region_name, gold_bias, world_terrain)

Keep Phases 2-4 (stream, feature, fluid) unchanged.
"""

import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.local_map import LocalMap

from src.local_map import LocalTerrain


# ── Core noise primitive ────────────────────────────────────────────────────

def _hash_cell(y: np.ndarray, x: np.ndarray, seed: int) -> np.ndarray:
    """Deterministic hash of grid cell coordinates → float in [0,1].
    Works with numpy broadcasting (e.g. y is (H,1), x is (1,W))."""
    # Large primes for spatial hash; int64 avoids overflow
    h = (x.astype(np.int64) * 73856093) ^ (y.astype(np.int64) * 19349663) ^ np.int64(seed)
    h = ((h >> 13) ^ h) * np.int64(1274126177)
    h = (h >> 16) ^ h
    return (h & np.int64(0x7FFFFFFF)).astype(np.float32) / np.float32(0x7FFFFFFF)


def _make_noise_absolute(seed: int,
                         abs_y_start: int, abs_x_start: int,
                         height: int, width: int,
                         cell_size: int = 64, octaves: int = 4,
                         lacunarity: float = 2.0, gain: float = 0.5) -> np.ndarray:
    """
    Multi-octave smooth value noise using ABSOLUTE tile coordinates.
    Adjacent patches with contiguous abs_start values produce continuous noise.

    abs_y_start, abs_x_start — the absolute tile coordinate of this patch's (0,0)
    """
    result = np.zeros((height, width), dtype=np.float32)
    total_amp = 0.0
    amp = 1.0
    cs = float(cell_size)

    for oct in range(octaves):
        cs_i = max(2.0, cs)
        oct_seed = (seed + oct * 65537) & 0x7FFFFFFF

        # Absolute coordinates mapped to noise grid cells
        abs_ys = (np.arange(height, dtype=np.float32) + abs_y_start) / cs_i
        abs_xs = (np.arange(width,  dtype=np.float32) + abs_x_start) / cs_i

        y0 = np.floor(abs_ys).astype(np.int32)
        x0 = np.floor(abs_xs).astype(np.int32)
        y1 = y0 + 1
        x1 = x0 + 1

        fy = (abs_ys - y0.astype(np.float32))[:, None]   # (H, 1)
        fx = (abs_xs - x0.astype(np.float32))[None, :]   # (1, W)
        # Smoothstep
        fy = fy * fy * (3.0 - 2.0 * fy)
        fx = fx * fx * (3.0 - 2.0 * fx)

        # Hash grid cell positions → deterministic noise values
        g00 = _hash_cell(y0[:, None], x0[None, :], oct_seed)
        g01 = _hash_cell(y0[:, None], x1[None, :], oct_seed)
        g10 = _hash_cell(y1[:, None], x0[None, :], oct_seed)
        g11 = _hash_cell(y1[:, None], x1[None, :], oct_seed)

        layer = (g00 * (1.0 - fy) * (1.0 - fx) +
                 g01 * (1.0 - fy) * fx +
                 g10 * fy * (1.0 - fx) +
                 g11 * fy * fx)

        result += layer * amp
        total_amp += amp
        amp *= gain
        cs /= lacunarity

    result /= total_amp
    return result


def _make_noise(seed: int, height: int, width: int,
                cell_size: int = 64, octaves: int = 4,
                lacunarity: float = 2.0, gain: float = 0.5) -> np.ndarray:
    """
    Multi-octave smooth value noise via numpy bilinear interpolation.
    Returns float32 array shape (height, width) in [0, 1].
    NOTE: This is the legacy local-only version. For cross-patch continuity,
    use _make_noise_absolute() instead.
    """
    rng = np.random.RandomState(seed & 0x7FFFFFFF)
    result = np.zeros((height, width), dtype=np.float32)
    total_amp = 0.0
    amp = 1.0
    cs = float(cell_size)

    for _ in range(octaves):
        cs_i = max(2.0, cs)
        gcols = int(width  / cs_i) + 3
        grows = int(height / cs_i) + 3
        grid = rng.rand(grows, gcols).astype(np.float32)

        ys = np.arange(height, dtype=np.float32) / cs_i
        xs = np.arange(width,  dtype=np.float32) / cs_i

        y0 = np.floor(ys).astype(np.int32).clip(0, grows - 2)
        x0 = np.floor(xs).astype(np.int32).clip(0, gcols - 2)
        y1 = (y0 + 1).clip(0, grows - 1)
        x1 = (x0 + 1).clip(0, gcols - 1)

        fy = (ys - y0.astype(np.float32))[:, None]   # (H, 1)
        fx = (xs - x0.astype(np.float32))[None, :]   # (1, W)
        # Smoothstep — removes grid alignment artifacts
        fy = fy * fy * (3.0 - 2.0 * fy)
        fx = fx * fx * (3.0 - 2.0 * fx)

        layer = (grid[y0[:, None], x0[None, :]] * (1.0 - fy) * (1.0 - fx) +
                 grid[y0[:, None], x1[None, :]] * (1.0 - fy) * fx +
                 grid[y1[:, None], x0[None, :]] * fy * (1.0 - fx) +
                 grid[y1[:, None], x1[None, :]] * fy * fx)

        result += layer * amp
        total_amp += amp
        amp *= gain
        cs /= lacunarity

    result /= total_amp
    return result


def _apply_terrain(local_map: "LocalMap", terrain_array: np.ndarray) -> None:
    """Write a 2D int32 terrain array into LocalMap.tiles."""
    H, W = terrain_array.shape
    for y in range(H):
        row_data = terrain_array[y].tolist()
        row_tiles = local_map.tiles[y]
        for x in range(W):
            row_tiles[x].terrain = row_data[x]


# ── Generator class ─────────────────────────────────────────────────────────

class LocalGenerator:
    """
    Noise-based local map terrain generator.

    Usage:
        gen = LocalGenerator(local_map, seed)
        gen.generate(region_name, gold_bias, world_terrain)

    This fills local_map.tiles with terrain only.
    Streams, features, and fluid simulation are handled separately
    by StreamGenerator, FeaturePlacer, and FluidSystem as before.
    """

    def __init__(self, local_map: "LocalMap", seed: int):
        self.lm = local_map
        self.H = local_map.height   # 384
        self.W = local_map.width    # 384
        # Absolute tile offsets for cross-patch noise continuity
        from src.constants import AREAS_PER_WORLD, PATCH_SIZE
        ax = getattr(local_map, 'area_x', 7)
        ay = getattr(local_map, 'area_y', 7)
        wx = local_map.world_x
        wy = local_map.world_y
        self._abs_x = (wx * AREAS_PER_WORLD + ax) * PATCH_SIZE
        self._abs_y = (wy * AREAS_PER_WORLD + ay) * PATCH_SIZE
        # Noise seed must be consistent across all patches in the same world tile
        # so terrain flows continuously across patch boundaries
        self.seed = (wx * 10007 + wy * 1000003) & 0x7FFFFFFF

    # ── Public entry point ─────────────────────────────────────────────────

    def generate(self, region_name: str, gold_bias: float,
                 world_terrain: int = 1) -> None:
        """Route to the appropriate regional generator + generate elevation."""
        from src.world_map import Terrain
        rn = region_name

        if "Sierra Nevada" in rn or "California" in rn:
            self._gen_california(gold_bias)
        elif "Gulf Coast" in rn:
            self._gen_gulf_coast()
        elif "Appalachian" in rn:
            self._gen_appalachian()
        elif "Pacific Northwest" in rn or "British Columbia" in rn:
            self._gen_pacific_northwest()
        elif "Alaska" in rn:
            self._gen_alaska(gold_bias)
        elif "Rocky" in rn or "Montana" in rn or "Idaho" in rn:
            self._gen_mountain()
        elif "Great Plains" in rn or "Prairie" in rn:
            self._gen_plains()
        elif world_terrain == Terrain.MOUNTAINS:
            self._gen_mountain()
        elif world_terrain in (Terrain.DESERT, Terrain.SCRUB):
            self._gen_desert()
        elif world_terrain == Terrain.SWAMP:
            self._gen_swamp()
        elif world_terrain in (Terrain.FOREST, Terrain.CONIFER):
            self._gen_eastern_forest()
        else:
            self._gen_plains()

        # Thin out trees — at 5ft/tile scale, trees need spacing
        self._thin_trees()

        # Generate elevation after terrain
        self._generate_elevation(world_terrain)

    # ── Elevation generation ──────────────────────────────────────────

    def _generate_elevation(self, world_terrain: int) -> None:
        """
        Generate surface_z elevation from noise, scaled by world terrain type.
        Mountains get high z-range, plains get near-flat.
        Stores result in self.lm.surface_z (numpy int8 array).
        """
        from src.world_map import Terrain

        # Z-range by world terrain type
        z_params = {
            Terrain.MOUNTAINS: (-1, 16),   # valleys at -1, peaks at +15
            Terrain.HILLS:     (-1, 9),
            Terrain.FOREST:    (0, 5),
            Terrain.CONIFER:   (0, 6),
            Terrain.PLAINS:    (0, 2),
            Terrain.PRAIRIE:   (0, 2),
            Terrain.DESERT:    (0, 4),
            Terrain.SCRUB:     (0, 3),
            Terrain.SWAMP:     (-2, 1),    # mostly flat, slightly below sea level
            Terrain.COAST:     (-1, 2),
            Terrain.TUNDRA:    (0, 3),
            Terrain.RIVER:     (-2, 3),
        }
        z_min, z_max = z_params.get(world_terrain, (0, 3))
        z_range = z_max - z_min

        if z_range <= 1:
            # Flat terrain — uniform elevation
            self.lm.surface_z[:] = z_min
            return

        # Generate smooth elevation noise
        n_elev = self._n(offset=999, cell_size=96, octaves=5)

        # Map 0.0-1.0 noise to z-range
        z_float = n_elev * z_range + z_min
        self.lm.surface_z = z_float.astype(np.int8)

        # Water tiles are always at the local minimum
        from src.local_map import LocalTerrain
        for y in range(self.H):
            for x in range(self.W):
                if self.lm.tiles[y][x].terrain == LocalTerrain.WATER:
                    # Water sits at the lowest nearby elevation
                    neighbors = []
                    for dy in range(-2, 3):
                        for dx in range(-2, 3):
                            nx, ny = x + dx, y + dy
                            if 0 <= nx < self.W and 0 <= ny < self.H:
                                neighbors.append(int(self.lm.surface_z[ny][nx]))
                    if neighbors:
                        self.lm.surface_z[y][x] = min(neighbors)

        # Town flattening — if this tile has a named location
        self._flatten_for_town()

        # Place ramps and cliff edges at elevation transitions
        self._place_ramps_and_cliffs()

    def _thin_trees(self) -> None:
        """
        At 5ft/tile scale, trees shouldn't be adjacent. A real forest has
        individual tree trunks with ground between them. This post-process
        removes trees that are too close to other trees, keeping ~15-20%
        tree coverage in dense forest and ~5-10% in sparse woodland.
        """
        from src.local_map import LocalTerrain
        import random as _rng

        TREE_TYPES = frozenset([
            LocalTerrain.PINE, LocalTerrain.OAK, LocalTerrain.ASPEN,
            LocalTerrain.JUNIPER, LocalTerrain.CEDAR, LocalTerrain.MAPLE,
            LocalTerrain.CHESTNUT, LocalTerrain.HICKORY, LocalTerrain.CYPRESS,
            LocalTerrain.MAGNOLIA, LocalTerrain.FOREST,
        ])

        rng = _rng.Random(self.seed + 777)

        # Pass 1: convert dense FOREST tiles to specific tree types with ground
        for y in range(self.H):
            for x in range(self.W):
                t = self.lm.tiles[y][x].terrain
                if t == LocalTerrain.FOREST:
                    # Replace with specific tree + mostly ground
                    if rng.random() < 0.15:  # 15% chance to be a tree
                        self.lm.tiles[y][x].terrain = rng.choice([
                            LocalTerrain.OAK, LocalTerrain.PINE,
                            LocalTerrain.MAPLE, LocalTerrain.HICKORY])
                    else:
                        self.lm.tiles[y][x].terrain = LocalTerrain.GRASS

        # Pass 2: thin individual tree species — minimum 2 tile spacing
        for y in range(1, self.H - 1):
            for x in range(1, self.W - 1):
                t = self.lm.tiles[y][x].terrain
                if t not in TREE_TYPES:
                    continue

                # Check if any adjacent tile is also a tree
                has_neighbor_tree = False
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        if dx == 0 and dy == 0:
                            continue
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < self.W and 0 <= ny < self.H:
                            if self.lm.tiles[ny][nx].terrain in TREE_TYPES:
                                has_neighbor_tree = True
                                break
                    if has_neighbor_tree:
                        break

                # If surrounded by other trees, randomly remove to create spacing
                if has_neighbor_tree and rng.random() < 0.65:
                    self.lm.tiles[y][x].terrain = LocalTerrain.GRASS

    def _place_ramps_and_cliffs(self) -> None:
        """
        Post-process elevation: place ramp tiles where adjacent surface z
        differs by exactly 1, and cliff edges where it differs by 2+.
        """
        from src.local_map import LocalTerrain, LOCAL_PASSABLE
        sz = self.lm.surface_z
        DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1)]

        for y in range(1, self.H - 1):
            for x in range(1, self.W - 1):
                my_z = int(sz[y][x])
                tile = self.lm.tiles[y][x]

                # Skip water, rock, buildings
                if tile.terrain in (LocalTerrain.WATER, LocalTerrain.ROCK):
                    continue

                has_higher = False
                has_lower = False
                max_diff = 0

                for dx, dy in DIRS:
                    nz = int(sz[y + dy][x + dx])
                    diff = nz - my_z
                    max_diff = max(max_diff, abs(diff))
                    if diff == 1:
                        has_higher = True
                    elif diff == -1:
                        has_lower = True

                if max_diff >= 2:
                    # Cliff edge — dangerous, impassable
                    tile.terrain = LocalTerrain.CLIFF_EDGE
                elif has_higher and not has_lower:
                    # This tile is at the bottom of a slope going up
                    tile.terrain = LocalTerrain.RAMP_UP
                elif has_lower and not has_higher:
                    # This tile is at the top of a slope going down
                    tile.terrain = LocalTerrain.RAMP_DOWN

    def _flatten_for_town(self) -> None:
        """
        If this local map tile has a named location (town/city),
        flatten a circular area around the center to a uniform z-level.
        Larger towns get larger flat zones.
        """
        loc = self.lm.world_map.get_location_at(self.lm.world_x, self.lm.world_y)
        if not loc:
            return

        cx, cy = self.W // 2, self.H // 2

        # Radius scales with population
        pop = getattr(loc, "population", 0)
        if pop >= 10000:
            radius = 50
        elif pop >= 2000:
            radius = 35
        elif pop >= 500:
            radius = 25
        elif pop >= 100:
            radius = 18
        else:
            radius = 12

        # Determine the town's z-level (median of center area)
        center_elevs = []
        for dy in range(-5, 6):
            for dx in range(-5, 6):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < self.W and 0 <= ny < self.H:
                    center_elevs.append(int(self.lm.surface_z[ny][nx]))
        town_z = int(np.median(center_elevs)) if center_elevs else 0

        # Flatten the core area
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                dist_sq = dx * dx + dy * dy
                if dist_sq > radius * radius:
                    continue
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < self.W and 0 <= ny < self.H:
                    dist = (dist_sq ** 0.5)
                    # Inner 70% is fully flat
                    if dist < radius * 0.7:
                        self.lm.surface_z[ny][nx] = town_z
                    else:
                        # Outer ring grades smoothly to natural terrain
                        natural = int(self.lm.surface_z[ny][nx])
                        blend = (dist - radius * 0.7) / (radius * 0.3)
                        blend = min(1.0, max(0.0, blend))
                        blended = int(town_z * (1.0 - blend) + natural * blend)
                        self.lm.surface_z[ny][nx] = blended

    # ── Noise convenience ──────────────────────────────────────────────────

    def _n(self, offset: int = 0, cell_size: int = 64,
           octaves: int = 4) -> np.ndarray:
        """Generate noise using absolute coordinates for cross-patch continuity."""
        return _make_noise_absolute(
            self.seed + offset,
            self._abs_y, self._abs_x,
            self.H, self.W,
            cell_size=cell_size, octaves=octaves)

    def _base(self, terrain: int) -> np.ndarray:
        return np.full((self.H, self.W), terrain, dtype=np.int32)

    # ── Regional generators ────────────────────────────────────────────────

    def _gen_california(self, gold_bias: float) -> None:
        """
        California Gold Country: oak savanna dotted with chaparral,
        rock ridges, and gravel bars. Natural oak clumps with open
        grass glades between them — no solid walls of trees.
        """
        T = LocalTerrain
        n_veg   = self._n(0,   cell_size=80, octaves=4)   # vegetation density
        n_rock  = self._n(100, cell_size=55, octaves=3)   # rocky terrain
        n_micro = self._n(200, cell_size=28, octaves=2)   # fine detail

        t = self._base(T.GRASS)

        # Chaparral brush at intermediate density
        t[(n_veg > 0.38) & (n_veg <= 0.58)] = T.BRUSH
        # Oak woodland — clumpy, leaving clearings below 0.38
        t[n_veg > 0.58] = T.OAK
        # Ponderosa at densest zones, micro-varied
        t[(n_veg > 0.74) & (n_micro > 0.55)] = T.PINE

        # Rocky ridges override vegetation
        t[n_rock > 0.68] = T.ROCK
        t[(n_rock > 0.68) & (n_micro > 0.58)] = T.BEDROCK
        # Gravel bars and placer ground at moderate rocky zones
        t[(n_rock > 0.52) & (n_rock <= 0.68)] = T.GRAVEL_BAR
        t[(n_rock > 0.52) & (n_rock <= 0.68) & (n_micro < 0.38)] = T.SAND

        _apply_terrain(self.lm, t)

    def _gen_appalachian(self) -> None:
        """
        Appalachian hardwood forest: American Chestnut dominant in 1849
        (one in four trees pre-blight), mixed with maple, oak, hickory.
        Rhododendron hollows, grass glades on balds, rock outcrops.
        Forest has natural clearings — not a solid canopy wall.
        """
        T = LocalTerrain
        n_canopy = self._n(0,   cell_size=90, octaves=4)   # canopy density
        n_type   = self._n(100, cell_size=60, octaves=3)   # species selector
        n_rock   = self._n(200, cell_size=45, octaves=3)
        n_micro  = self._n(300, cell_size=22, octaves=2)

        t = self._base(T.CHESTNUT)

        # Meadow glades (canopy gaps) — about 28% of area open
        t[n_canopy < 0.28] = T.GRASS
        # Brush hollows: rhododendron/mountain laurel
        t[(n_canopy >= 0.28) & (n_canopy < 0.42)] = T.BRUSH

        # Within dense zones: species by type noise
        dense = n_canopy >= 0.42
        t[dense & (n_type > 0.70)] = T.MAPLE
        t[dense & (n_type > 0.52) & (n_type <= 0.70)] = T.OAK
        t[dense & (n_type > 0.35) & (n_type <= 0.52)] = T.HICKORY
        # Chestnut fills dense & n_type <= 0.35 (already base)

        # Yellow/Paper Birch at meadow edges
        t[(n_canopy < 0.32) & (n_micro > 0.62)] = T.ASPEN

        # Sandstone and quartzite outcrops
        t[n_rock > 0.70] = T.ROCK
        t[(n_rock > 0.70) & (n_micro > 0.50)] = T.BEDROCK

        _apply_terrain(self.lm, t)

    def _gen_pacific_northwest(self) -> None:
        """
        Pacific Northwest / BC coastal rainforest: massive cedar and fir,
        fern understory, rare meadow openings, steep cliff faces.
        Denser than eastern forest but still has natural light gaps.
        """
        T = LocalTerrain
        n_forest = self._n(0,   cell_size=100, octaves=4)
        n_rock   = self._n(100, cell_size=60,  octaves=3)
        n_micro  = self._n(200, cell_size=30,  octaves=2)

        t = self._base(T.CEDAR)

        # Rare openings — temperate rainforest is very dense
        t[n_forest < 0.20] = T.GRASS
        # Fern/moss understory at low-moderate density
        t[(n_forest >= 0.20) & (n_forest < 0.36)] = T.BRUSH
        # Red Alder at clearing edges
        t[(n_forest >= 0.20) & (n_forest < 0.33) & (n_micro > 0.55)] = T.ASPEN

        # Cliff faces and rocky slopes
        t[n_rock > 0.65] = T.ROCK
        t[(n_rock > 0.65) & (n_micro < 0.40)] = T.BEDROCK

        _apply_terrain(self.lm, t)

    def _gen_gulf_coast(self) -> None:
        """
        Gulf Coast / Deep South: baldcypress swamps, live oak hammocks,
        magnolia uplands, longleaf pine savanna, tidal mudflats.
        Wetness gradient drives vegetation naturally.
        """
        T = LocalTerrain
        n_wet   = self._n(0,   cell_size=85, octaves=4)   # wetness 0=dry 1=wet
        n_veg   = self._n(100, cell_size=65, octaves=3)   # plant type
        n_micro = self._n(200, cell_size=28, octaves=2)

        t = self._base(T.GRASS)

        # Dry upland zones — magnolia, oak, pine
        dry = n_wet < 0.38
        t[dry & (n_veg > 0.62)] = T.MAGNOLIA
        t[dry & (n_veg > 0.42) & (n_veg <= 0.62)] = T.OAK
        t[dry & (n_veg < 0.28)] = T.PINE

        # Transitional wet areas
        trans = (n_wet >= 0.38) & (n_wet < 0.55)
        t[trans] = T.BRUSH
        t[trans & (n_veg > 0.55)] = T.MAGNOLIA

        # Swamp zones: baldcypress and tupelo
        wet = n_wet >= 0.55
        t[wet] = T.CYPRESS
        t[wet & (n_micro < 0.40)] = T.MUD
        t[wet & (n_micro < 0.22)] = T.SAND   # sandy tidal margins

        _apply_terrain(self.lm, t)

    def _gen_alaska(self, gold_bias: float) -> None:
        """
        Alaskan tundra/taiga: open tundra with boreal spruce pockets,
        boggy permafrost thaw areas, gravel-bed creeks, rocky ridges.
        """
        T = LocalTerrain
        n_forest = self._n(0,   cell_size=75, octaves=4)
        n_rock   = self._n(100, cell_size=55, octaves=3)
        n_wet    = self._n(200, cell_size=60, octaves=3)
        n_micro  = self._n(300, cell_size=25, octaves=2)

        t = self._base(T.TUNDRA)

        # Boreal spruce pockets (drier areas only)
        t[(n_forest > 0.55) & (n_wet < 0.50)] = T.PINE
        # Paper/Alaska Birch at forest edges
        t[(n_forest > 0.68) & (n_wet < 0.42)] = T.ASPEN

        # Boggy permafrost thaw pools
        t[n_wet > 0.62] = T.MUD
        # Gravel river bars
        t[(n_wet > 0.45) & (n_wet <= 0.62) & (n_micro > 0.52)] = T.GRAVEL_BAR

        # Rocky ridges and scree
        t[n_rock > 0.70] = T.ROCK
        t[(n_rock > 0.70) & (n_micro > 0.55)] = T.BEDROCK

        _apply_terrain(self.lm, t)

    def _gen_plains(self) -> None:
        """
        Open prairie: rolling grass with scattered brush, dry sandy draws,
        and gallery woodland (oak/cottonwood) along low drainages.
        """
        T = LocalTerrain
        n_veg   = self._n(0,   cell_size=70, octaves=4)
        n_dry   = self._n(100, cell_size=50, octaves=3)
        n_micro = self._n(200, cell_size=25, octaves=2)

        t = self._base(T.GRASS)

        # Dry draws and bare patches
        t[n_dry > 0.68] = T.GROUND
        t[(n_dry > 0.68) & (n_micro > 0.58)] = T.SAND

        # Brush thickets
        t[(n_veg > 0.60) & (n_dry <= 0.60)] = T.BRUSH

        # Gallery woodland along drainage lows
        t[(n_veg > 0.72) & (n_dry < 0.38)] = T.OAK
        t[(n_veg > 0.65) & (n_dry < 0.30) & (n_micro > 0.50)] = T.ASPEN

        _apply_terrain(self.lm, t)

    def _gen_mountain(self) -> None:
        """
        Mountain terrain: rocky ridges, scree slopes, pine forest in
        sheltered pockets, high meadows. Rock patterns are continuous
        and irregular, not circular blobs.
        """
        T = LocalTerrain
        n_elev  = self._n(0,   cell_size=90, octaves=4)   # elevation
        n_rock  = self._n(100, cell_size=55, octaves=3)
        n_micro = self._n(200, cell_size=28, octaves=2)

        t = self._base(T.ROCK)

        # Lower ledges and plateaus
        t[n_elev < 0.45] = T.GROUND
        # High meadows on the most open ground
        t[n_elev < 0.30] = T.GRASS
        # Scree slopes
        t[(n_elev >= 0.35) & (n_elev < 0.50) & (n_rock < 0.55)] = T.GRAVEL_BAR
        # Bedrock slabs at high rocky zones
        t[n_rock > 0.72] = T.BEDROCK

        # Pine forest on open ground (not the most exposed rock)
        t[(n_elev < 0.42) & (n_rock < 0.55)] = T.PINE
        # Aspen in meadow pockets
        t[(n_elev < 0.28) & (n_micro > 0.58)] = T.ASPEN

        _apply_terrain(self.lm, t)

    def _gen_desert(self) -> None:
        """
        Desert and scrubland: sand base, rock mesas, hardpan flats,
        sparse creosote/sage brush, piñon-juniper at higher rocky ground.
        """
        T = LocalTerrain
        n_elev  = self._n(0,   cell_size=80, octaves=4)
        n_rock  = self._n(100, cell_size=55, octaves=3)
        n_micro = self._n(200, cell_size=32, octaves=2)

        t = self._base(T.SAND)

        # Gravel desert pavement
        t[n_elev > 0.40] = T.GRAVEL_BAR
        # Hardpan
        t[(n_elev > 0.50) & (n_rock < 0.40)] = T.GROUND
        # Creosote/sagebrush
        t[(n_elev > 0.38) & (n_elev < 0.62) & (n_micro > 0.55)] = T.BRUSH
        # Rock mesas
        t[n_rock > 0.62] = T.ROCK
        t[(n_rock > 0.62) & (n_micro < 0.40)] = T.BEDROCK
        # Piñon-juniper on rocky higher ground
        t[(n_elev > 0.58) & (n_rock < 0.55) & (n_micro > 0.50)] = T.JUNIPER

        _apply_terrain(self.lm, t)

    def _gen_swamp(self) -> None:
        """
        Swamp / wetland: mud-dominant with open water pools, cypress
        groves, and small upland islands of grass and brush.
        """
        T = LocalTerrain
        n_wet   = self._n(0,   cell_size=75, octaves=4)
        n_veg   = self._n(100, cell_size=50, octaves=3)
        n_micro = self._n(200, cell_size=25, octaves=2)

        t = self._base(T.MUD)

        # Open water pools
        t[n_wet > 0.72] = T.WATER
        t[(n_wet > 0.72) & (n_micro > 0.65)] = T.MUD   # muddy shallows
        # Cypress and tupelo in wet zones
        t[(n_wet > 0.45) & (n_wet <= 0.72)] = T.CYPRESS
        # Higher ground: grass and brush
        t[n_wet < 0.30] = T.GRASS
        t[(n_wet < 0.38) & (n_veg > 0.55)] = T.BRUSH
        t[(n_wet < 0.35) & (n_veg > 0.65)] = T.MAGNOLIA

        _apply_terrain(self.lm, t)

    def _gen_eastern_forest(self) -> None:
        """
        Eastern mixed hardwood-conifer: pine base with maple, oak,
        hickory, birch openings — all placed by noise so species
        transition naturally rather than in discrete ellipses.
        """
        T = LocalTerrain
        n_canopy = self._n(0,   cell_size=85, octaves=4)
        n_type   = self._n(100, cell_size=55, octaves=3)
        n_rock   = self._n(200, cell_size=45, octaves=3)
        n_micro  = self._n(300, cell_size=22, octaves=2)

        t = self._base(T.PINE)

        # Clearings — about 25% open
        t[n_canopy < 0.25] = T.GRASS
        t[(n_canopy >= 0.25) & (n_canopy < 0.38)] = T.BRUSH

        # Species variation within forest
        dense = n_canopy >= 0.38
        t[dense & (n_type > 0.65)] = T.MAPLE
        t[dense & (n_type > 0.48) & (n_type <= 0.65)] = T.OAK
        t[dense & (n_type > 0.32) & (n_type <= 0.48)] = T.HICKORY
        t[dense & (n_type <= 0.18)] = T.ASPEN   # paper birch patches

        # Rock outcrops
        t[n_rock > 0.72] = T.ROCK
        t[(n_rock > 0.72) & (n_micro < 0.45)] = T.BEDROCK

        _apply_terrain(self.lm, t)
