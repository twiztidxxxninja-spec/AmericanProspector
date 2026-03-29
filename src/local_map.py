"""
src/local_map.py

Local map (384x384 tiles) — procedurally generated but guided by world region.
Base terrain set by region generators; streams and features delegated to
StreamGenerator and FeaturePlacer so each concern has one owner.
"""

import random
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict, Any

from src.constants import LOCAL_WIDTH, LOCAL_HEIGHT
from src.world_map import Terrain
from src.regions import REGIONS
from src.volume_gold import GoldColumn


# Local terrain types
class LocalTerrain:
    GROUND      = 0
    GRASS       = 1
    FOREST      = 2   # dense mixed/generic forest
    ROCK        = 3
    WATER       = 4
    GRAVEL_BAR  = 5
    BEDROCK     = 6
    MUD         = 7
    SAND        = 8
    BRUSH       = 9
    PIT         = 10
    SPOIL_PILE  = 11
    TUNDRA      = 12
    # Tree species — distinct glyphs/colors by NA region & era
    PINE        = 13  # Ponderosa, Sugar, Lodgepole, Subalpine Fir, White/Black Spruce
    OAK         = 14  # Blue Oak, Valley Oak, Bur Oak, Gambel Oak, Live Oak
    ASPEN       = 15  # Quaking Aspen, Paper Birch, Cottonwood (riparian)
    JUNIPER     = 16  # Rocky Mtn Juniper, Piñon Pine, Utah Juniper
    CEDAR       = 17  # Western Red Cedar, Douglas Fir, Giant Sequoia, Sitka Spruce
    MAPLE       = 18  # Sugar Maple, Red Maple, Silver Maple, Bigleaf Maple, Box Elder
    CHESTNUT    = 19  # American Chestnut (dominant pre-blight), Am. Beech, Tulip Poplar, Basswood
    HICKORY     = 20  # Shagbark/Bitternut Hickory, Black Walnut, Butternut, Pecan
    CYPRESS     = 21  # Baldcypress, Water Tupelo, Swamp Blackgum, Atlantic White Cedar
    MAGNOLIA    = 22  # Southern Magnolia, Sweetgum, Sassafras, Pawpaw, Persimmon
    # Worked ground — visual feedback from mining/panning
    WORKED_GRAVEL = 30  # panned gravel bar — disturbed, darker
    WORKED_DIRT   = 31  # shoveled ground — loose earth
    SHALLOW_PIT   = 32  # dug 1-2 levels — visible depression
    DEEP_PIT      = 33  # dug 3+ levels — dark hole
    TAILINGS      = 34  # processed waste from sluice/rocker
    # Z-level terrain types
    RAMP_UP     = 50  # natural slope connecting to z+1
    RAMP_DOWN   = 51  # natural slope connecting to z-1
    CLIFF_EDGE  = 52  # impassable drop-off (z diff >= 2)
    STAIRS_UP   = 53  # built stairs going up
    STAIRS_DOWN = 54  # built stairs going down
    STAIRS_BOTH = 55  # built stairs going both ways
    LADDER_UP   = 56  # ladder going up
    LADDER_DOWN = 57  # ladder going down


LOCAL_GLYPH = {
    LocalTerrain.GROUND:     (".", (100, 80,  50),  (30, 20, 10)),
    LocalTerrain.GRASS:      (".", (80,  140, 60),  (20, 50, 10)),
    LocalTerrain.FOREST:     ("T", (40,  100, 40),  (10, 30, 10)),
    LocalTerrain.ROCK:       ("#", (140, 140, 140), (60, 60, 60)),
    LocalTerrain.WATER:      ("~", (60,  120, 200), (20, 50, 100)),
    LocalTerrain.GRAVEL_BAR: (":", (160, 140, 100), (70, 60, 40)),
    LocalTerrain.BEDROCK:    ("#", (120, 110, 100), (50, 45, 40)),
    LocalTerrain.MUD:        (".", (80,  70,  50),  (30, 25, 15)),
    LocalTerrain.SAND:       (".", (200, 180, 120), (90, 80, 50)),
    LocalTerrain.BRUSH:      (";", (100, 120, 60),  (30, 40, 15)),
    LocalTerrain.PIT:        (" ", ( 80,  60,  30),  ( 8,  5,  2)),
    LocalTerrain.SPOIL_PILE: ("*", (140, 115,  70),  (55, 40, 15)),
    LocalTerrain.TUNDRA:     (".", (140, 155, 130),  (45, 52, 40)),
    # Tree species
    LocalTerrain.PINE:       ("^", ( 30,  90,  40),  ( 8, 28, 12)),  # dark pointed silhouette
    LocalTerrain.OAK:        ("T", ( 70, 130,  50),  (22, 50, 15)),  # rounded canopy, warmer green
    LocalTerrain.ASPEN:      ("|", (160, 200, 120),  (55, 80, 35)),  # slender pale trunk
    LocalTerrain.JUNIPER:    ("*", ( 60,  95,  70),  (18, 35, 22)),  # compact grey-green
    LocalTerrain.CEDAR:      ("T", ( 20,  70,  35),  ( 5, 22,  8)),  # very dark, massive
    LocalTerrain.MAPLE:      ("T", (120, 185,  55),  (40, 72,  14)), # bright yellow-green
    LocalTerrain.CHESTNUT:   ("%", ( 55, 115,  35),  (16, 40,   9)), # spreading canopy — dominant eastern tree pre-blight
    LocalTerrain.HICKORY:    ("T", (145, 165,  45),  (52, 62,  12)), # yellow-olive
    LocalTerrain.CYPRESS:    ("^", ( 35, 115,  85),  ( 8, 40,  25)), # blue-green, swamp conifer
    LocalTerrain.MAGNOLIA:   ("T", ( 45, 110,  60),  (12, 36,  16)), # warm medium green, glossy
    # Worked ground
    LocalTerrain.WORKED_GRAVEL: (":", (120, 100,  70), (40, 35, 20)),  # darker, disturbed gravel
    LocalTerrain.WORKED_DIRT:   ("~", ( 90,  75,  45), (30, 25, 12)),  # loose churned earth
    LocalTerrain.SHALLOW_PIT:   ("o", ( 70,  55,  30), (12, 10,  5)),  # visible depression
    LocalTerrain.DEEP_PIT:      ("O", ( 50,  35,  15), ( 5,  3,  1)),  # dark deep hole
    LocalTerrain.TAILINGS:      ("=", (130, 110,  75), (50, 42, 25)),  # flat waste piles
    # Z-level terrain
    LocalTerrain.RAMP_UP:    ("/", (140, 120,  80),  (50, 40, 25)),  # slope going up
    LocalTerrain.RAMP_DOWN:  ("\\", (140, 120,  80), (50, 40, 25)),  # slope going down
    LocalTerrain.CLIFF_EDGE: ("!", (200,  60,  40),  (80, 25, 15)),  # dangerous edge
    LocalTerrain.STAIRS_UP:  ("<", (160, 140, 100),  (55, 45, 30)),  # built stairs up
    LocalTerrain.STAIRS_DOWN:(">", (160, 140, 100),  (55, 45, 30)),  # built stairs down
    LocalTerrain.STAIRS_BOTH:("X", (160, 140, 100),  (55, 45, 30)),  # up/down stairwell
    LocalTerrain.LADDER_UP:  ("H", (130, 100,  55),  (45, 35, 18)),  # ladder up
    LocalTerrain.LADDER_DOWN:("H", (130, 100,  55),  (45, 35, 18)),  # ladder down
}

LOCAL_PASSABLE = {
    LocalTerrain.GROUND:     True,
    LocalTerrain.GRASS:      True,
    LocalTerrain.FOREST:     True,
    LocalTerrain.ROCK:       False,
    LocalTerrain.WATER:      False,
    LocalTerrain.GRAVEL_BAR: True,
    LocalTerrain.BEDROCK:    True,
    LocalTerrain.MUD:        True,
    LocalTerrain.SAND:       True,
    LocalTerrain.BRUSH:      True,
    LocalTerrain.PIT:        True,
    LocalTerrain.SPOIL_PILE: True,
    LocalTerrain.TUNDRA:     True,
    LocalTerrain.PINE:       False,  # solid trunk at 5ft scale
    LocalTerrain.OAK:        False,
    LocalTerrain.ASPEN:      False,
    LocalTerrain.JUNIPER:    False,
    LocalTerrain.CEDAR:      False,
    LocalTerrain.MAPLE:      False,
    LocalTerrain.CHESTNUT:   False,
    LocalTerrain.HICKORY:    False,
    LocalTerrain.CYPRESS:    False,
    LocalTerrain.MAGNOLIA:   False,
    LocalTerrain.WORKED_GRAVEL: True,
    LocalTerrain.WORKED_DIRT:   True,
    LocalTerrain.SHALLOW_PIT:   True,
    LocalTerrain.DEEP_PIT:      True,   # can walk in but slow
    LocalTerrain.TAILINGS:      True,
    LocalTerrain.RAMP_UP:    True,
    LocalTerrain.RAMP_DOWN:  True,
    LocalTerrain.CLIFF_EDGE: False,   # can't walk off a cliff
    LocalTerrain.STAIRS_UP:  True,
    LocalTerrain.STAIRS_DOWN:True,
    LocalTerrain.STAIRS_BOTH:True,
    LocalTerrain.LADDER_UP:  True,
    LocalTerrain.LADDER_DOWN:True,
}

LOCAL_TRANSPARENT = {
    LocalTerrain.GROUND:     True,
    LocalTerrain.GRASS:      True,
    LocalTerrain.FOREST:     False,
    LocalTerrain.ROCK:       False,
    LocalTerrain.WATER:      True,
    LocalTerrain.GRAVEL_BAR: True,
    LocalTerrain.BEDROCK:    True,
    LocalTerrain.MUD:        True,
    LocalTerrain.SAND:       True,
    LocalTerrain.BRUSH:      False,
    LocalTerrain.PIT:        True,
    LocalTerrain.SPOIL_PILE: True,
    LocalTerrain.TUNDRA:     True,
    # Individual tree tiles don't block LOS — you see the trunk/canopy but can
    # look between trees.  Dense FOREST (=2) and BRUSH block vision; open trees don't.
    LocalTerrain.PINE:       True,
    LocalTerrain.OAK:        True,
    LocalTerrain.ASPEN:      True,
    LocalTerrain.JUNIPER:    True,
    LocalTerrain.CEDAR:      True,
    LocalTerrain.MAPLE:      True,
    LocalTerrain.CHESTNUT:   True,
    LocalTerrain.HICKORY:    True,
    LocalTerrain.CYPRESS:    True,
    LocalTerrain.MAGNOLIA:   True,
    LocalTerrain.WORKED_GRAVEL: True,
    LocalTerrain.WORKED_DIRT:   True,
    LocalTerrain.SHALLOW_PIT:   True,
    LocalTerrain.DEEP_PIT:      True,
    LocalTerrain.TAILINGS:      True,
    LocalTerrain.RAMP_UP:    True,
    LocalTerrain.RAMP_DOWN:  True,
    LocalTerrain.CLIFF_EDGE: True,
    LocalTerrain.STAIRS_UP:  True,
    LocalTerrain.STAIRS_DOWN:True,
    LocalTerrain.STAIRS_BOTH:True,
    LocalTerrain.LADDER_UP:  True,
    LocalTerrain.LADDER_DOWN:True,
}


@dataclass
class LocalTile:
    terrain: int = LocalTerrain.GROUND
    explored: bool = False
    visible: bool = False
    gold_grade: float = 0.0
    dig_depth: int = 0
    spoil_dir: Optional[Tuple[int, int]] = None
    panned: bool = False
    mineral_hint: str = ""           # geology assessment label (set by prospecting)
    gold_column: Optional[GoldColumn] = None
    ground_items: List[Any] = field(default_factory=list)


@dataclass
class ZTile:
    """A tile at a non-surface z-level. Sparse — only created when needed."""
    terrain: int = LocalTerrain.GROUND
    explored: bool = False
    visible: bool = False
    gold_grade: float = 0.0
    ground_items: List[Any] = field(default_factory=list)


@dataclass
class PatchSummary:
    """Lightweight metadata for unvisited patches — generated when within eyesight.
    Much cheaper than full LocalMap generation. Used for LOD rendering on area map."""
    terrain_type: int = 0           # dominant terrain from world tile
    has_stream: bool = False        # quick noise check
    avg_elevation: int = 0          # from noise
    has_structure: bool = False     # town building, camp, etc.
    structure_type: str = ""        # "cabin", "camp", "mine entrance"
    npc_count: int = 0              # approximate visible count
    animal_count: int = 0           # approximate visible count


class SubsurfaceMaterial:
    """What's naturally underground at a given depth below surface."""
    SOIL    = 0   # depth 1-2 below surface
    GRAVEL  = 1   # depth 3-4
    CLAY    = 2   # regional variant
    STONE   = 3   # depth 5-7
    ORE     = 4   # rare, location-dependent
    BEDROCK = 5   # depth 8+


class LocalMap:
    def __init__(self, world_x: int, world_y: int, world_terrain: int,
                 world_map, seed: int = 0,
                 area_x: int = 7, area_y: int = 7):
        self.world_x = world_x
        self.world_y = world_y
        self.area_x = area_x
        self.area_y = area_y
        self.world_map = world_map
        self.seed = seed
        self.width = LOCAL_WIDTH
        self.height = LOCAL_HEIGHT
        self.tiles = [
            [LocalTile() for _ in range(self.width)]
            for _ in range(self.height)
        ]

        # Stored after generation; used for lazy GoldColumn creation in engine
        self._region_name: str = ""
        self._gold_bias: float = 0.3

        # Z-level terrain elevation
        import numpy as np
        self.surface_z = np.zeros((self.height, self.width), dtype=np.int8)
        self.z_tiles: Dict[Tuple[int, int, int], ZTile] = {}  # (x,y,z) → ZTile

        # Cached terrain array for fast FOV — rebuilt after generation
        self._terrain_np: Optional[np.ndarray] = None

        # Structure registry: id → structure object (sluice boxes, cabins, etc.)
        self.structures: Dict[int, Any] = {}
        self._next_id: int = 1

        # Fluid simulation — set in _generate() after streams are placed
        self.fluid_system = None

        # Construction system overlays (edge walls, player-placed floors, zones)
        self.wall_grid = None      # WallGrid from construction.py
        self.floor_overlay = None  # FloorOverlay from construction.py
        self.zones = []            # List[DesignatedZone]
        self.build_queue = None    # BuildQueue from construction.py
        try:
            from src.construction import WallGrid, FloorOverlay, BuildQueue
            self.wall_grid = WallGrid()
            self.floor_overlay = FloorOverlay()
            self.build_queue = BuildQueue()
        except ImportError:
            pass

        self._generate(world_terrain)

    def _generate(self, world_terrain: int):
        rng = random.Random(self.seed)

        region_name = self.world_map.get_region(self.world_x, self.world_y)
        gold_bias   = self.world_map.get_gold_bias(self.world_x, self.world_y)
        self._region_name = region_name
        self._gold_bias   = gold_bias

        # ── Phase 1: Base terrain ──────────────────────────────────────────
        # LocalGenerator (local_gen.py) uses noise-based generation for
        # natural forests; falls back to scatter_grid methods if unavailable.
        stream_count = 1
        stream_twist = 0.6

        gen_ok = False
        try:
            from src.local_gen import LocalGenerator
            LocalGenerator(self, self.seed).generate(
                region_name, gold_bias, world_terrain)
            gen_ok = True
        except Exception:
            pass

        if not gen_ok:
            # Fallback: original scatter_grid generators
            if "Sierra Nevada" in region_name or "California" in region_name:
                self._gen_sierra_foothills(rng, gold_bias)
            elif "Great Plains" in region_name or "Prairie" in region_name:
                self._gen_plains(rng, gold_bias)
            elif "Alaska" in region_name:
                self._gen_alaska(rng, gold_bias)
            elif "Pacific Northwest" in region_name or "British Columbia" in region_name:
                self._gen_coastal_mountains(rng, gold_bias)
            elif "Appalachian" in region_name:
                self._gen_appalachian(rng, gold_bias)
            elif "Gulf Coast" in region_name:
                self._gen_gulf_coast(rng, gold_bias)
            elif world_terrain == Terrain.MOUNTAINS:
                self._gen_mountain(rng)
            elif world_terrain == Terrain.FOREST:
                self._gen_forest(rng)
            elif world_terrain == Terrain.DESERT:
                self._gen_desert(rng)
            else:
                self._gen_plains(rng)

        # Stream count/twist by region — streams are common in most terrain.
        # At 5ft/tile scale, a 384-tile patch is only 0.36 miles. Creeks and
        # springs are everywhere in the American landscape — most patches
        # should have at least one water feature.
        if "Sierra Nevada" in region_name or "California" in region_name:
            stream_count, stream_twist = 3, 0.85
        elif "Great Plains" in region_name or "Prairie" in region_name:
            stream_count = rng.choice([1, 1, 2])
            stream_twist = 0.35
        elif "Alaska" in region_name:
            stream_count, stream_twist = 2, 0.6
        elif "Pacific Northwest" in region_name or "British Columbia" in region_name:
            stream_count, stream_twist = 3, 0.8
        elif "Appalachian" in region_name:
            stream_count, stream_twist = 2, 0.65
        elif "Gulf Coast" in region_name:
            stream_count, stream_twist = 3, 0.7
        elif world_terrain == Terrain.MOUNTAINS:
            stream_count = rng.choice([1, 2, 2])
            stream_twist = 0.4
        elif world_terrain == Terrain.FOREST:
            stream_count = rng.choice([1, 1, 2])
            stream_twist = 0.5
        elif world_terrain == Terrain.DESERT:
            stream_count = 1 if rng.random() < 0.5 else 0
            stream_twist = 0.3
        else:
            stream_count = rng.choice([1, 1, 2])
            stream_twist = 0.35

        # ── Phase 2: Streams (StreamGenerator) ────────────────────────────
        if stream_count > 0:
            from src.stream_generator import StreamGenerator
            sg = StreamGenerator(rng)
            sg.generate_streams(self, count=stream_count, base_twist=stream_twist)
            sg.add_side_channels(self, probability=0.2)

        # ── Phase 3: Placer features (FeaturePlacer) ──────────────────────
        from src.feature_placer import FeaturePlacer
        fp = FeaturePlacer(rng)
        fp.place_features(self, region_name, gold_bias)
        if stream_count > 0:
            fp.enhance_streams(self)

        # ── Phase 4: Town layout (only in center patch of world tile) ─────
        self.town_layout = None
        try:
            from src.constants import AREAS_PER_WORLD
            center = AREAS_PER_WORLD // 2
            if self.area_x == center and self.area_y == center:
                from src.town_gen import generate_town_layout
                layout = generate_town_layout(self, self.world_map,
                                               self.world_x, self.world_y)
                if layout:
                    self.town_layout = layout
        except Exception:
            pass

        # ── Phase 5: Fluid simulation ──────────────────────────────────────
        from src.fluid_system import FluidSystem
        self.fluid_system = FluidSystem(self)
        self.fluid_system.initialize_streams()

    # ── Region-specific terrain generators ────────────────────────────────
    # These set base terrain only; streams and features handled in _generate().
    #
    # FOV is 14 tiles.  Random large-zone placement fails because on a 384×384
    # map the nearest zone edge can be 20+ tiles away — outside the FOV.
    #
    # _scatter_grid() places one zone per cell in a cols×rows grid.  With a
    # 10×10 grid (38×38 cells) and minimum zone radius 14, the maximum distance
    # from any map point to the nearest zone edge is √(19²+19²)−14 ≈ 12.9 tiles
    # — guaranteed inside the 14-tile FOV.

    def _paint_zone(self, cx: int, cy: int, rx: int, ry: int,
                    terrain: int, on_terrain: Optional[int] = None) -> None:
        """Fill a filled ellipse with terrain. Optionally only overwrite on_terrain."""
        rx2, ry2 = rx * rx, ry * ry
        rxy2 = rx2 * ry2
        for dy in range(-ry, ry + 1):
            dy2ry = dy * dy * rx2
            for dx in range(-rx, rx + 1):
                if dx * dx * ry2 + dy2ry <= rxy2:
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < self.width and 0 <= ny < self.height:
                        if on_terrain is None or self.tiles[ny][nx].terrain == on_terrain:
                            self.tiles[ny][nx].terrain = terrain

    def _scatter_grid(self, rng, cols: int, rows: int,
                      rx_range: tuple, ry_range: tuple,
                      terrain: int, on_terrain: Optional[int] = None) -> None:
        """
        Place one elliptical zone per cell of a cols×rows grid.
        Guarantees uniform terrain coverage so any spawn point has
        terrain variety within FOV regardless of map size.
        """
        cw = self.width  // cols
        ch = self.height // rows
        for gy in range(rows):
            for gx in range(cols):
                rx = rng.randint(*rx_range)
                ry = rng.randint(*ry_range)
                # Zone centre within the cell, far enough from edge not to clip badly
                lo_x = gx * cw + rx;  hi_x = (gx + 1) * cw - rx
                lo_y = gy * ch + ry;  hi_y = (gy + 1) * ch - ry
                cx = rng.randint(lo_x, max(lo_x + 1, hi_x))
                cy = rng.randint(lo_y, max(lo_y + 1, hi_y))
                self._paint_zone(cx, cy, rx, ry, terrain, on_terrain)

    def _gen_sierra_foothills(self, rng, gold_bias):
        """California Gold Rush country: grass/chaparral mix with rock and gravel."""
        self._fill(LocalTerrain.GRASS)
        # Chaparral / brush — 10×10 grid guarantees coverage anywhere on the map
        self._scatter_grid(rng, 10, 10, (14, 22), (10, 16), LocalTerrain.BRUSH)
        # Rock outcrops and ridgelines
        self._scatter_grid(rng, 6, 6, (12, 22), (9, 16), LocalTerrain.ROCK)
        # A few large dramatic rock formations
        for _ in range(rng.randint(3, 6)):
            self._paint_zone(rng.randint(40, self.width - 40),
                             rng.randint(40, self.height - 40),
                             rng.randint(28, 48), rng.randint(18, 32),
                             LocalTerrain.ROCK)
        # Gravel bars / placer ground
        self._scatter_grid(rng, 7, 7, (8, 16), (6, 12), LocalTerrain.GRAVEL_BAR)
        # Bedrock exposures (paint on top of gravel so they stand out)
        self._scatter_grid(rng, 5, 5, (6, 13), (5, 10), LocalTerrain.BEDROCK)
        # Blue Oak / Valley Oak woodland — iconic California foothill tree
        self._scatter_grid(rng, 7, 7, (10, 18), (8, 13), LocalTerrain.OAK,
                           on_terrain=LocalTerrain.GRASS)
        # Ponderosa / Sugar Pine — pine-chaparral transition at higher ground
        self._scatter_grid(rng, 5, 5, (7, 13), (5, 9), LocalTerrain.PINE,
                           on_terrain=LocalTerrain.BRUSH)

    def _gen_plains(self, rng, gold_bias=0.3):
        """Open prairie: rolling grass with scrub, bare ground, sandy draws."""
        self._fill(LocalTerrain.GRASS)
        # Brush / scrubland throughout
        self._scatter_grid(rng, 10, 10, (14, 24), (10, 18), LocalTerrain.BRUSH)
        # Bare ground (dry draws, cattle-grazed patches)
        self._scatter_grid(rng, 6, 6, (10, 18), (8, 14), LocalTerrain.GROUND)
        # Sandy low spots
        self._scatter_grid(rng, 4, 4, (8, 16), (6, 12), LocalTerrain.SAND)
        # Bur Oak / savanna oaks — gallery woodland, eastern plains edge
        self._scatter_grid(rng, 5, 5, (8, 16), (6, 12), LocalTerrain.OAK,
                           on_terrain=LocalTerrain.GRASS)
        # Plains Cottonwood — along draws and low-lying ground
        self._scatter_grid(rng, 4, 4, (6, 11), (4, 8), LocalTerrain.ASPEN,
                           on_terrain=LocalTerrain.GROUND)

    def _gen_alaska(self, rng, gold_bias):
        """Alaskan tundra/taiga: boggy, rocky, gravelly with boreal forest patches."""
        self._fill(LocalTerrain.TUNDRA)
        # Boggy permafrost-thaw mud — dominant secondary terrain
        self._scatter_grid(rng, 10, 10, (12, 20), (9, 15), LocalTerrain.MUD)
        # Rock outcrops / talus
        self._scatter_grid(rng, 6, 6, (12, 22), (9, 16), LocalTerrain.ROCK)
        # Creek-bed gravel bars
        self._scatter_grid(rng, 5, 5, (8, 16), (6, 12), LocalTerrain.GRAVEL_BAR)
        # Black Spruce / White Spruce — boreal forest patches on open tundra
        self._scatter_grid(rng, 7, 7, (10, 18), (7, 13), LocalTerrain.PINE,
                           on_terrain=LocalTerrain.TUNDRA)
        # Paper Birch / Alaska Birch — lighter forest, interior lowlands
        self._scatter_grid(rng, 5, 5, (7, 13), (5, 9), LocalTerrain.ASPEN,
                           on_terrain=LocalTerrain.TUNDRA)

    def _gen_coastal_mountains(self, rng, gold_bias):
        """BC coastal mountains: temperate rainforest with cliff faces and meadow clearings."""
        # Western Red Cedar, Sitka Spruce, Douglas Fir — BC coastal rainforest
        self._fill(LocalTerrain.CEDAR)
        # Meadow clearings cut into the forest
        self._scatter_grid(rng, 8, 8, (14, 22), (10, 17), LocalTerrain.GRASS)
        # Rock cliffs and faces
        self._scatter_grid(rng, 6, 6, (12, 22), (9, 16), LocalTerrain.ROCK)
        # Large dramatic cliff features
        for _ in range(rng.randint(3, 6)):
            self._paint_zone(rng.randint(40, self.width - 40),
                             rng.randint(40, self.height - 40),
                             rng.randint(26, 44), rng.randint(16, 30),
                             LocalTerrain.ROCK)
        # Bedrock slabs at high elevation
        self._scatter_grid(rng, 5, 5, (6, 14), (5, 10), LocalTerrain.BEDROCK)
        # Red Alder / Bigleaf Maple — lighter forest at clearing edges and stream banks
        self._scatter_grid(rng, 5, 5, (7, 14), (5, 10), LocalTerrain.ASPEN,
                           on_terrain=LocalTerrain.GRASS)

    def _gen_forest(self, rng):
        """Mixed eastern hardwood-conifer forest: pine base with maple, oak, hickory."""
        # Generic eastern mixed forest — pine/hardwood transition
        self._fill(LocalTerrain.PINE)
        # Grass clearings throughout (10×10 guarantees they're always visible)
        self._scatter_grid(rng, 10, 10, (14, 24), (10, 18), LocalTerrain.GRASS)
        # Sugar/Red Maple — mid-successional, abundant in eastern mixed forest
        self._scatter_grid(rng, 8, 8, (10, 18), (7, 14), LocalTerrain.MAPLE)
        # White/Red/Chestnut Oak mixed in — oak-pine transition zone
        self._scatter_grid(rng, 7, 7, (10, 17), (7, 13), LocalTerrain.OAK,
                           on_terrain=LocalTerrain.MAPLE)
        # Shagbark Hickory / Black Walnut — understory and edges
        self._scatter_grid(rng, 6, 6, (8, 14), (6, 10), LocalTerrain.HICKORY,
                           on_terrain=LocalTerrain.GRASS)
        # Paper Birch / Aspen — disturbed areas, old fields
        self._scatter_grid(rng, 5, 5, (7, 13), (5, 9), LocalTerrain.ASPEN,
                           on_terrain=LocalTerrain.GRASS)
        # Rocky outcrops
        self._scatter_grid(rng, 5, 5, (8, 18), (6, 13), LocalTerrain.ROCK)

    def _gen_appalachian(self, rng, gold_bias):
        """
        Appalachian hardwood forest: American Chestnut was the dominant canopy tree —
        1 in 4 Appalachian trees pre-blight (1904–1940). Mixed with oak, maple, hickory,
        and dense rhododendron/mountain laurel brush in hollows.
        """
        # American Chestnut / Beech / Tulip Poplar — dominant in 1840s
        self._fill(LocalTerrain.CHESTNUT)
        # Sugar/Red Maple — abundant at all elevations
        self._scatter_grid(rng, 9, 9, (12, 20), (9, 15), LocalTerrain.MAPLE)
        # White Oak / Chestnut Oak / Red Oak — ridges and dry slopes
        self._scatter_grid(rng, 8, 8, (10, 18), (7, 13), LocalTerrain.OAK)
        # Shagbark Hickory / Black Walnut / Butternut — coves and lower slopes
        self._scatter_grid(rng, 7, 7, (9, 16), (6, 12), LocalTerrain.HICKORY)
        # Rhododendron / Mountain Laurel — dense brush in hollows (blocks view)
        self._scatter_grid(rng, 8, 8, (10, 18), (7, 13), LocalTerrain.BRUSH,
                           on_terrain=LocalTerrain.CHESTNUT)
        # Grass glades / bald meadows
        self._scatter_grid(rng, 6, 6, (10, 18), (7, 13), LocalTerrain.GRASS)
        # Sandstone / quartzite outcrops
        self._scatter_grid(rng, 5, 5, (10, 18), (7, 14), LocalTerrain.ROCK)
        # Bedrock along ridgelines
        self._scatter_grid(rng, 4, 4, (7, 14), (5, 10), LocalTerrain.BEDROCK)
        # Paper Birch / Yellow Birch — high-elevation forest
        self._scatter_grid(rng, 5, 5, (8, 14), (5, 10), LocalTerrain.ASPEN,
                           on_terrain=LocalTerrain.GRASS)

    def _gen_gulf_coast(self, rng, gold_bias):
        """
        Gulf Coast / Deep South: Baldcypress swamps, Live Oak hammocks, Southern Magnolia,
        longleaf pine savanna, and tidal marsh. Oil seeps in Texas lowlands.
        """
        self._fill(LocalTerrain.GRASS)
        # Baldcypress / Tupelo — dominant swamp forest (fills low wet ground)
        self._scatter_grid(rng, 9, 9, (12, 20), (9, 15), LocalTerrain.CYPRESS)
        # Southern Magnolia / Sweetgum / Sassafras — upland and hammocks
        self._scatter_grid(rng, 8, 8, (10, 18), (7, 13), LocalTerrain.MAGNOLIA)
        # Live Oak / Water Oak / Laurel Oak — hammocks and ridges
        self._scatter_grid(rng, 7, 7, (10, 17), (7, 12), LocalTerrain.OAK)
        # Longleaf Pine / Loblolly Pine — pine savanna on higher sandy ground
        self._scatter_grid(rng, 6, 6, (9, 16), (6, 11), LocalTerrain.PINE,
                           on_terrain=LocalTerrain.GRASS)
        # Spanish Moss / Cane thicket — understory brush
        self._scatter_grid(rng, 7, 7, (8, 15), (6, 11), LocalTerrain.BRUSH,
                           on_terrain=LocalTerrain.GRASS)
        # Swamp mud / bottomland
        self._scatter_grid(rng, 8, 8, (10, 18), (7, 13), LocalTerrain.MUD,
                           on_terrain=LocalTerrain.CYPRESS)
        # Sandy coastal / beach ridges
        self._scatter_grid(rng, 4, 4, (8, 16), (5, 10), LocalTerrain.SAND)

    def _gen_mountain(self, rng):
        """Mountain terrain: mostly rock with ledges, scree, pine slopes, and high meadows."""
        self._fill(LocalTerrain.ROCK)
        # Open ground — ledges and plateaus
        self._scatter_grid(rng, 10, 10, (14, 22), (10, 16), LocalTerrain.GROUND)
        # Gravel / scree slopes
        self._scatter_grid(rng, 7, 7, (10, 18), (8, 14), LocalTerrain.GRAVEL_BAR)
        # Bedrock slabs
        self._scatter_grid(rng, 6, 6, (8, 16), (6, 12), LocalTerrain.BEDROCK)
        # High meadow grass pockets
        self._scatter_grid(rng, 4, 4, (8, 16), (6, 12), LocalTerrain.GRASS)
        # Lodgepole / Subalpine Fir — dominant mountain conifers on open ledges
        self._scatter_grid(rng, 8, 8, (10, 18), (7, 13), LocalTerrain.PINE,
                           on_terrain=LocalTerrain.GROUND)
        # Quaking Aspen — sheltered slopes and high meadow edges
        self._scatter_grid(rng, 6, 6, (8, 14), (6, 10), LocalTerrain.ASPEN,
                           on_terrain=LocalTerrain.GRASS)

    def _gen_desert(self, rng):
        """Desert: sand base with mesa rock, hardpan, sparse brush, and piñon-juniper."""
        self._fill(LocalTerrain.SAND)
        # Rock formations and mesas
        self._scatter_grid(rng, 10, 10, (14, 22), (10, 16), LocalTerrain.ROCK)
        # Large mesa features
        for _ in range(rng.randint(3, 6)):
            self._paint_zone(rng.randint(40, self.width - 40),
                             rng.randint(40, self.height - 40),
                             rng.randint(30, 50), rng.randint(18, 32),
                             LocalTerrain.ROCK)
        # Desert hardpan / bedrock flats
        self._scatter_grid(rng, 6, 6, (10, 18), (7, 14), LocalTerrain.BEDROCK)
        # Dry brush (creosote, sage)
        self._scatter_grid(rng, 5, 5, (6, 14), (5, 10), LocalTerrain.BRUSH)
        # Gravel flats
        self._scatter_grid(rng, 4, 4, (8, 16), (6, 12), LocalTerrain.GRAVEL_BAR)
        # Piñon Pine / Rocky Mtn Juniper — classic high-desert/desert-margin woodland
        self._scatter_grid(rng, 6, 6, (8, 14), (5, 10), LocalTerrain.JUNIPER,
                           on_terrain=LocalTerrain.SAND)

    # ── Utilities ──────────────────────────────────────────────────────────

    def _fill(self, terrain: int):
        for row in self.tiles:
            for tile in row:
                tile.terrain = terrain

    def terrain_array(self):
        """Cached numpy int32 array of terrain types for fast FOV/rendering."""
        import numpy as np
        if self._terrain_np is None:
            self._terrain_np = np.array(
                [[self.tiles[y][x].terrain for x in range(self.width)]
                 for y in range(self.height)], dtype=np.int32)
        return self._terrain_np

    def invalidate_terrain_cache(self):
        """Call after modifying tile terrain (dig, pan, build)."""
        self._terrain_np = None

    def tile_at(self, x: int, y: int) -> LocalTile:
        """Legacy 2D accessor — returns surface tile."""
        return self.tiles[y][x]

    def tile_at_z(self, x: int, y: int, z: int):
        """
        Get tile at (x, y, z).  Returns:
        - LocalTile if z == surface elevation (fast path)
        - ZTile if z != surface and a z_tile exists (dug/built)
        - None if z > surface (open air) or z < surface (solid, not dug)
        """
        if not self.in_bounds(x, y):
            return None
        sz = int(self.surface_z[y][x])
        if z == sz:
            return self.tiles[y][x]
        return self.z_tiles.get((x, y, z))

    def is_passable(self, x: int, y: int) -> bool:
        if not self.in_bounds(x, y):
            return False
        t = self.tiles[y][x].terrain
        return LOCAL_PASSABLE.get(t, True)

    def is_passable_z(self, x: int, y: int, z: int) -> bool:
        """Check passability at a specific z-level."""
        if not self.in_bounds(x, y):
            return False
        sz = int(self.surface_z[y][x])
        if z == sz:
            return LOCAL_PASSABLE.get(self.tiles[y][x].terrain, True)
        if z > sz:
            # Open air above surface is passable (but needs floor below!)
            zt = self.z_tiles.get((x, y, z))
            if zt is None:
                return True
            return LOCAL_PASSABLE.get(zt.terrain, True)
        # Underground: solid unless explicitly dug out
        zt = self.z_tiles.get((x, y, z))
        return zt is not None and LOCAL_PASSABLE.get(zt.terrain, True)

    def is_transparent(self, x: int, y: int) -> bool:
        if not self.in_bounds(x, y):
            return False
        t = self.tiles[y][x].terrain
        return LOCAL_TRANSPARENT.get(t, True)

    def is_transparent_z(self, x: int, y: int, z: int) -> bool:
        """Check transparency at a specific z-level."""
        if not self.in_bounds(x, y):
            return False
        sz = int(self.surface_z[y][x])
        if z == sz:
            return LOCAL_TRANSPARENT.get(self.tiles[y][x].terrain, True)
        if z > sz:
            zt = self.z_tiles.get((x, y, z))
            if zt is None:
                return True  # open air is transparent
            return LOCAL_TRANSPARENT.get(zt.terrain, True)
        # Underground solid = not transparent
        zt = self.z_tiles.get((x, y, z))
        if zt is None:
            return False
        return LOCAL_TRANSPARENT.get(zt.terrain, True)

    def natural_material_at(self, x: int, y: int, z: int) -> int:
        """What material is naturally underground at this z-level?"""
        if not self.in_bounds(x, y):
            return SubsurfaceMaterial.BEDROCK
        sz = int(self.surface_z[y][x])
        depth = sz - z
        if depth <= 0:
            return SubsurfaceMaterial.SOIL
        if depth <= 2:
            return SubsurfaceMaterial.SOIL
        if depth <= 4:
            return SubsurfaceMaterial.GRAVEL
        if depth <= 7:
            return SubsurfaceMaterial.STONE
        return SubsurfaceMaterial.BEDROCK

    def ground_z(self, x: int, y: int) -> int:
        """Return the z-level of solid ground at (x, y).
        This is surface_z unless there are dug-out z-tiles below,
        in which case it's the lowest open z before hitting solid."""
        if not self.in_bounds(x, y):
            return 0
        sz = int(self.surface_z[y][x])
        # Check for open space below surface (mine shafts)
        z = sz
        while z > -20:
            below = self.z_tiles.get((x, y, z - 1))
            if below is not None:
                z -= 1  # open space below, keep falling
            else:
                break   # solid ground
        return z

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height
