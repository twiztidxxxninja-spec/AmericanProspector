"""
src/detail_map.py

Fine-scale detail map at ~6 feet per tile.

Purpose: close-up work — panning a specific gravel bar, digging a test pit,
laying out a sluice, NPC interaction inside a building footprint.

Scale relationship:
    1 local tile  ≈ 30 ft (10 yards)
    1 detail tile ≈ 6 ft
    → 1 local tile = 5×5 detail tiles

Detail map covers a 32×20 local-tile area around the player:
    32 × 5 = 160 detail tiles wide
    20 × 5 = 100 detail tiles tall
    → 960 ft × 600 ft visible area

The map is generated on-demand when the player enters detail view.
If the player moves beyond a boundary, the detail map regenerates
centred on the new position (seamless regeneration, not stored).

Zoom integration:
    MAP_LEVELS = ["detail_map", "local_map", ...] (detail_map is index 0)
    Engine._zoom_in() from local_map → enters detail mode at player position
    Engine._zoom_out() from detail_map → returns to local_map

    In engine.py add to MAP_LEVELS and GameState:
        GameState.DETAIL_MAP = "detail_map"
        MAP_LEVELS = ["detail_map", "local_map", "area_map", ...]

    In renderer.py add:
        if state == GameState.DETAIL_MAP:
            self._draw_detail_map(detail_map, player, ...)

    In engine.py _zoom_in():
        if self.state == GameState.LOCAL_MAP:
            self._enter_detail_mode()
            return

    In engine.py _zoom_out():
        if self.state == GameState.DETAIL_MAP:
            self._exit_detail_mode()
            return
"""

from dataclasses import dataclass, field
from typing import Optional, List, Any, Tuple
import random
import numpy as np


# ── Detail terrain constants ────────────────────────────────────────────────

class DetailTerrain:
    # Ground surfaces
    DIRT          = 0    # bare mineral soil
    GRASS_PATCH   = 1    # clumped grass
    MOSS          = 2    # damp moss, soft footing
    LEAF_LITTER   = 3    # fallen leaves underfoot
    NEEDLE_LITTER = 4    # pine needle duff
    DRY_GRASS     = 5    # coarse dry tussock

    # Rock and mineral
    PEBBLES       = 10   # loose small stones
    GRAVEL        = 11   # stream gravel, pannable
    COARSE_GRAVEL = 12   # fist-sized cobbles
    SAND_FINE     = 13   # silt-fine sand
    SAND_COARSE   = 14   # gritty coarse sand
    CLAY          = 15   # sticky clay
    BEDROCK_FLAT  = 16   # exposed bedrock surface, walkable
    BEDROCK_CRACK = 17   # crevice in bedrock — high gold concentration
    BOULDER_BASE  = 18   # base of a large boulder, impassable
    ROCK_FACE     = 19   # cliff face, impassable
    HARDPAN       = 20   # cemented caliche, hard to dig

    # Water
    SHALLOW       = 30   # ankle-deep, transparent bottom visible
    DEEP          = 31   # knee-to-waist, opaque
    FAST_WATER    = 32   # strong current lane — panning ineffective, slippery
    POOL          = 33   # still deep pool — good gold trap
    MUD_MARGIN    = 34   # muddy bank edge

    # Vegetation detail
    SHRUB         = 40   # dense shrub, passable with effort
    SAPLING       = 41   # young tree, passable
    TREE_BASE     = 42   # trunk base of a mature tree, impassable
    ROOT_TANGLE   = 43   # exposed roots, slow movement
    REED_BED      = 44   # cattail/reed, wetland margin

    # Structure / feature
    SPOIL_LOOSE   = 50   # fresh excavation spoil
    SPOIL_OLD     = 51   # settled old spoil pile
    FIREPIT       = 52   # fire ring / ash
    CAMP_GROUND   = 53   # packed-earth camp clearing
    POST_HOLE     = 54   # structural post, impassable
    PLANK_FLOOR   = 55   # wooden floor inside a structure


DETAIL_GLYPH = {
    # (glyph, fg_rgb, bg_rgb)
    DetailTerrain.DIRT:          (".", ( 90,  70,  45), (25, 18, 10)),
    DetailTerrain.GRASS_PATCH:   ('"', ( 80, 145,  55), (18, 45, 10)),
    DetailTerrain.MOSS:          (".", ( 60, 115,  70), (14, 36, 18)),
    DetailTerrain.LEAF_LITTER:   ("~", (135, 110,  60), (45, 35, 14)),
    DetailTerrain.NEEDLE_LITTER: (".", ( 75,  90,  55), (22, 28, 14)),
    DetailTerrain.DRY_GRASS:     ('"', (155, 145,  75), (55, 50, 20)),
    DetailTerrain.PEBBLES:       (":", (140, 128,  95), (55, 48, 32)),
    DetailTerrain.GRAVEL:        (":", (158, 140, 100), (65, 55, 38)),
    DetailTerrain.COARSE_GRAVEL: (":", (148, 132,  95), (60, 50, 35)),
    DetailTerrain.SAND_FINE:     (".", (215, 198, 140), (95, 85, 55)),
    DetailTerrain.SAND_COARSE:   (".", (200, 180, 120), (85, 75, 45)),
    DetailTerrain.CLAY:          (".", (150, 110,  80), (60, 40, 28)),
    DetailTerrain.BEDROCK_FLAT:  ("#", (115, 105,  95), (48, 42, 38)),
    DetailTerrain.BEDROCK_CRACK: ("%", (100,  92,  82), (40, 36, 30)),
    DetailTerrain.BOULDER_BASE:  ("@", (160, 155, 148), (70, 68, 65)),
    DetailTerrain.ROCK_FACE:     ("|", (140, 135, 130), (62, 60, 58)),
    DetailTerrain.HARDPAN:       (".", (170, 155, 115), (72, 65, 45)),
    DetailTerrain.SHALLOW:       ("~", ( 90, 175, 220), (28, 80, 118)),
    DetailTerrain.DEEP:          ("~", ( 45, 120, 195), (12, 45,  95)),
    DetailTerrain.FAST_WATER:    ("≈", ( 80, 158, 215), (22, 65, 112)),
    DetailTerrain.POOL:          ("~", ( 30,  95, 170), ( 8, 35,  85)),
    DetailTerrain.MUD_MARGIN:    (".", ( 85,  72,  48), (30, 25, 15)),
    DetailTerrain.SHRUB:         (";", ( 80, 112,  55), (22, 38, 14)),
    DetailTerrain.SAPLING:       ("|", ( 60, 105,  45), (16, 34, 10)),
    DetailTerrain.TREE_BASE:     ("0", ( 95,  72,  42), (38, 28, 15)),
    DetailTerrain.ROOT_TANGLE:   ("~", ( 88,  68,  40), (32, 24, 12)),
    DetailTerrain.REED_BED:      ("|", ( 95, 135,  60), (28, 48, 16)),
    DetailTerrain.SPOIL_LOOSE:   ("*", (145, 118,  72), (58, 45, 25)),
    DetailTerrain.SPOIL_OLD:     ("*", (120,  98,  60), (48, 38, 20)),
    DetailTerrain.FIREPIT:       ("0", (195,  82,  30), (80, 28,  8)),
    DetailTerrain.CAMP_GROUND:   (".", ( 88,  68,  42), (30, 22, 12)),
    DetailTerrain.POST_HOLE:     ("|", (100,  80,  50), (40, 30, 18)),
    DetailTerrain.PLANK_FLOOR:   ("=", (155, 118,  68), (62, 45, 24)),
}

DETAIL_PASSABLE = {
    DetailTerrain.BOULDER_BASE:  False,
    DetailTerrain.ROCK_FACE:     False,
    DetailTerrain.POST_HOLE:     False,
    DetailTerrain.DEEP:          False,  # must ford deliberately
    DetailTerrain.FAST_WATER:    False,  # too dangerous without check
}

DETAIL_TRANSPARENT = {
    DetailTerrain.SHRUB:        False,
    DetailTerrain.REED_BED:     False,
    DetailTerrain.TREE_BASE:    False,
}

# Gold yield per panning attempt (troy oz chance weight)
# Higher = richer panning spot
DETAIL_GOLD_WEIGHT = {
    DetailTerrain.BEDROCK_CRACK: 3.0,   # highest — trapped gold in crevices
    DetailTerrain.POOL:          2.0,   # still water, natural gold trap
    DetailTerrain.GRAVEL:        1.2,   # standard placer ground
    DetailTerrain.COARSE_GRAVEL: 1.0,
    DetailTerrain.CLAY:          0.8,   # clay pan — old paleo-channel
    DetailTerrain.PEBBLES:       0.6,
    DetailTerrain.SAND_COARSE:   0.4,
    DetailTerrain.SAND_FINE:     0.2,
    DetailTerrain.MUD_MARGIN:    0.2,
    DetailTerrain.SHALLOW:       0.3,
    DetailTerrain.BEDROCK_FLAT:  0.5,
}


@dataclass
class DetailTile:
    terrain:    int   = DetailTerrain.DIRT
    explored:   bool  = False
    visible:    bool  = False
    gold_grade: float = 0.0       # 0.0–1.0 local concentration
    dug:        bool  = False     # has been excavated
    wet:        bool  = False     # currently holding water (filled pit etc)
    ground_items: List[Any] = field(default_factory=list)


# ── Noise helper (reuse same algorithm as local_gen) ───────────────────────

def _make_noise(seed: int, height: int, width: int,
                cell_size: int = 32, octaves: int = 3) -> np.ndarray:
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
        fy = (ys - y0.astype(np.float32))[:, None]
        fx = (xs - x0.astype(np.float32))[None, :]
        fy = fy * fy * (3.0 - 2.0 * fy)
        fx = fx * fx * (3.0 - 2.0 * fx)
        layer = (grid[y0[:, None], x0[None, :]] * (1 - fy) * (1 - fx) +
                 grid[y0[:, None], x1[None, :]] * (1 - fy) * fx +
                 grid[y1[:, None], x0[None, :]] * fy * (1 - fx) +
                 grid[y1[:, None], x1[None, :]] * fy * fx)
        result += layer * amp
        total_amp += amp
        amp *= 0.5
        cs /= 2.0
    result /= total_amp
    return result


# ── DetailMap ───────────────────────────────────────────────────────────────

# Fixed size: 160 × 100 detail tiles (covers 32×20 local tiles = 960×600 ft)
DETAIL_WIDTH  = 160
DETAIL_HEIGHT = 100

# Detail tiles per local tile (1 local tile = 30 ft, 1 detail tile = 6 ft)
DTILES_PER_LOCAL = 5


class DetailMap:
    """
    Fine-scale (~6 ft/tile) map covering a 32×20 local-tile area.

    Generated from the local map context (terrain type + gold grade)
    centred on the player's local position.  Regenerated seamlessly
    when the player moves far enough in detail view.

    Player coordinates in detail space:
        detail_x = (local_x - origin_lx) * DTILES_PER_LOCAL + offset_within_tile
        detail_y = (local_y - origin_ly) * DTILES_PER_LOCAL + offset_within_tile
    Start at (DETAIL_WIDTH // 2, DETAIL_HEIGHT // 2) when entering detail view.
    """

    def __init__(self,
                 local_map,        # LocalMap instance
                 origin_lx: int,   # local map x of the detail area's top-left corner
                 origin_ly: int,   # local map y of the detail area's top-left corner
                 seed: int = 0):
        self.local_map  = local_map
        self.origin_lx  = origin_lx
        self.origin_ly  = origin_ly
        self.seed       = seed
        self.width      = DETAIL_WIDTH
        self.height     = DETAIL_HEIGHT

        self.tiles: List[List[DetailTile]] = [
            [DetailTile() for _ in range(self.width)]
            for _ in range(self.height)
        ]
        self._generate()

    # ── Generation ─────────────────────────────────────────────────────────

    def _generate(self) -> None:
        """
        Build the detail map from local map terrain context.
        Each local tile becomes a 5×5 block of detail tiles, then
        noise is added for micro-variation within each block.
        """
        # Phase 1: paint 5×5 blocks from local terrain
        for ly in range(DETAIL_HEIGHT // DTILES_PER_LOCAL):
            for lx in range(DETAIL_WIDTH // DTILES_PER_LOCAL):
                world_lx = self.origin_lx + lx
                world_ly = self.origin_ly + ly
                if not self.local_map.in_bounds(world_lx, world_ly):
                    continue
                ltile = self.local_map.tile_at(world_lx, world_ly)
                base_gold = ltile.gold_grade

                dx_start = lx * DTILES_PER_LOCAL
                dy_start = ly * DTILES_PER_LOCAL
                for dy in range(DTILES_PER_LOCAL):
                    for dx in range(DTILES_PER_LOCAL):
                        dtx = dx_start + dx
                        dty = dy_start + dy
                        if 0 <= dtx < self.width and 0 <= dty < self.height:
                            self.tiles[dty][dtx].gold_grade = base_gold

        # Phase 2: noise-based micro-terrain overwriting base blocks
        self._apply_micro_detail()

        # Phase 3: gold concentration hotspots
        self._place_gold_concentrations()

    def _apply_micro_detail(self) -> None:
        """
        Apply fine noise to the detail terrain.  Each 5×5 local block
        gets its base terrain type; noise then sub-divides that into
        the correct detail variants for that terrain class.
        """
        from src.local_map import LocalTerrain as LT

        n_micro  = _make_noise(self.seed,      self.height, self.width, cell_size=12, octaves=3)
        n_detail = _make_noise(self.seed+1000, self.height, self.width, cell_size=6,  octaves=2)
        n_water  = _make_noise(self.seed+2000, self.height, self.width, cell_size=18, octaves=3)

        DT = DetailTerrain

        # Map from local terrain class → detail terrain choices by noise threshold
        # Each entry: list of (noise_threshold, detail_terrain)
        # Applied top-down — first threshold that is exceeded wins.
        LOCAL_TO_DETAIL = {
            LT.GROUND:     [(0.75, DT.PEBBLES),    (0.50, DT.HARDPAN),
                            (0.25, DT.CLAY),        (0.0,  DT.DIRT)],
            LT.GRASS:      [(0.80, DT.DRY_GRASS),  (0.55, DT.GRASS_PATCH),
                            (0.30, DT.MOSS),        (0.0,  DT.LEAF_LITTER)],
            LT.BRUSH:      [(0.70, DT.SHRUB),      (0.45, DT.ROOT_TANGLE),
                            (0.25, DT.GRASS_PATCH), (0.0,  DT.LEAF_LITTER)],
            LT.GRAVEL_BAR: [(0.80, DT.COARSE_GRAVEL), (0.55, DT.GRAVEL),
                            (0.30, DT.SAND_COARSE),    (0.0,  DT.SAND_FINE)],
            LT.BEDROCK:    [(0.75, DT.BEDROCK_CRACK), (0.50, DT.BEDROCK_FLAT),
                            (0.0,  DT.HARDPAN)],
            LT.ROCK:       [(0.80, DT.ROCK_FACE),   (0.60, DT.BEDROCK_FLAT),
                            (0.30, DT.COARSE_GRAVEL),(0.0,  DT.PEBBLES)],
            LT.WATER:      [(0.80, DT.FAST_WATER),  (0.55, DT.DEEP),
                            (0.25, DT.SHALLOW),      (0.0,  DT.MUD_MARGIN)],
            LT.MUD:        [(0.75, DT.MUD_MARGIN),  (0.50, DT.CLAY),
                            (0.25, DT.SHALLOW),      (0.0,  DT.DIRT)],
            LT.SAND:       [(0.75, DT.SAND_COARSE), (0.45, DT.SAND_FINE),
                            (0.0,  DT.CLAY)],
            LT.TUNDRA:     [(0.70, DT.DRY_GRASS),  (0.45, DT.MOSS),
                            (0.25, DT.PEBBLES),     (0.0,  DT.DIRT)],
            # Tree types → forest floor detail under/between trunks
            LT.PINE:       [(0.85, DT.TREE_BASE),  (0.65, DT.ROOT_TANGLE),
                            (0.40, DT.NEEDLE_LITTER),(0.0,  DT.MOSS)],
            LT.OAK:        [(0.85, DT.TREE_BASE),  (0.65, DT.ROOT_TANGLE),
                            (0.40, DT.LEAF_LITTER), (0.0,  DT.GRASS_PATCH)],
            LT.ASPEN:      [(0.80, DT.SAPLING),    (0.55, DT.LEAF_LITTER),
                            (0.0,  DT.GRASS_PATCH)],
            LT.CEDAR:      [(0.85, DT.TREE_BASE),  (0.65, DT.ROOT_TANGLE),
                            (0.40, DT.NEEDLE_LITTER),(0.0,  DT.MOSS)],
            LT.MAPLE:      [(0.85, DT.TREE_BASE),  (0.60, DT.LEAF_LITTER),
                            (0.0,  DT.GRASS_PATCH)],
            LT.CHESTNUT:   [(0.85, DT.TREE_BASE),  (0.60, DT.LEAF_LITTER),
                            (0.30, DT.ROOT_TANGLE), (0.0,  DT.MOSS)],
            LT.HICKORY:    [(0.85, DT.TREE_BASE),  (0.60, DT.LEAF_LITTER),
                            (0.0,  DT.GRASS_PATCH)],
            LT.CYPRESS:    [(0.85, DT.TREE_BASE),  (0.65, DT.ROOT_TANGLE),
                            (0.40, DT.MUD_MARGIN),  (0.0,  DT.SHALLOW)],
            LT.MAGNOLIA:   [(0.85, DT.TREE_BASE),  (0.60, DT.LEAF_LITTER),
                            (0.30, DT.SHRUB),       (0.0,  DT.GRASS_PATCH)],
            LT.JUNIPER:    [(0.80, DT.SHRUB),      (0.55, DT.PEBBLES),
                            (0.0,  DT.DIRT)],
        }

        DEFAULT_CHOICES = [(0.6, DT.PEBBLES), (0.0, DT.DIRT)]

        for ly in range(DETAIL_HEIGHT // DTILES_PER_LOCAL):
            for lx in range(DETAIL_WIDTH // DTILES_PER_LOCAL):
                world_lx = self.origin_lx + lx
                world_ly = self.origin_ly + ly
                if not self.local_map.in_bounds(world_lx, world_ly):
                    continue
                ltile = self.local_map.tile_at(world_lx, world_ly)
                choices = LOCAL_TO_DETAIL.get(ltile.terrain, DEFAULT_CHOICES)

                dx_start = lx * DTILES_PER_LOCAL
                dy_start = ly * DTILES_PER_LOCAL
                for dy in range(DTILES_PER_LOCAL):
                    for dx in range(DTILES_PER_LOCAL):
                        dtx = dx_start + dx
                        dty = dy_start + dy
                        if not (0 <= dtx < self.width and 0 <= dty < self.height):
                            continue
                        v = n_micro[dty, dtx]
                        terrain = choices[-1][1]
                        for threshold, t in choices:
                            if v >= threshold:
                                terrain = t
                                break
                        self.tiles[dty][dtx].terrain = terrain

        # Water pools and still areas added by separate water noise
        for dty in range(self.height):
            for dtx in range(self.width):
                tile = self.tiles[dty][dtx]
                if tile.terrain in (DT.SHALLOW, DT.DEEP, DT.FAST_WATER):
                    # Replace fast water in low-movement zones with pools
                    if n_water[dty, dtx] < 0.30 and tile.terrain == DT.FAST_WATER:
                        tile.terrain = DT.POOL
                    tile.wet = True

    def _place_gold_concentrations(self) -> None:
        """
        Increase gold_grade for geologically correct detail tiles.
        Bedrock cracks, pools, and clay pans are natural gold traps.
        """
        DT = DetailTerrain
        HIGH_GOLD = {DT.BEDROCK_CRACK, DT.POOL, DT.CLAY}
        MED_GOLD  = {DT.GRAVEL, DT.COARSE_GRAVEL, DT.SHALLOW, DT.MUD_MARGIN}

        for row in self.tiles:
            for tile in row:
                base = tile.gold_grade
                if base <= 0.0:
                    continue
                if tile.terrain in HIGH_GOLD:
                    tile.gold_grade = min(1.0, base * 2.5)
                elif tile.terrain in MED_GOLD:
                    tile.gold_grade = min(1.0, base * 1.4)

    # ── Access helpers ──────────────────────────────────────────────────────

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def tile_at(self, x: int, y: int) -> DetailTile:
        return self.tiles[y][x]

    def is_passable(self, x: int, y: int) -> bool:
        if not self.in_bounds(x, y):
            return False
        return DETAIL_PASSABLE.get(self.tiles[y][x].terrain, True)

    def is_transparent(self, x: int, y: int) -> bool:
        if not self.in_bounds(x, y):
            return False
        return DETAIL_TRANSPARENT.get(self.tiles[y][x].terrain, True)

    def panning_yield_modifier(self, x: int, y: int) -> float:
        """
        Return a multiplier for gold panning at this tile.
        0.0 = cannot pan here.  1.0 = standard.  3.0 = rich crevice.
        """
        if not self.in_bounds(x, y):
            return 0.0
        tile = self.tiles[y][x]
        return DETAIL_GOLD_WEIGHT.get(tile.terrain, 0.0) * tile.gold_grade

    def dig(self, x: int, y: int) -> Optional[int]:
        """
        Mark a tile as dug.  Returns the new terrain type, or None if
        digging is not possible here.
        """
        if not self.in_bounds(x, y):
            return None
        tile = self.tiles[y][x]
        if tile.terrain in (DetailTerrain.BOULDER_BASE, DetailTerrain.ROCK_FACE,
                             DetailTerrain.BEDROCK_FLAT, DetailTerrain.BEDROCK_CRACK,
                             DetailTerrain.HARDPAN):
            return None   # requires pick or blasting
        tile.dug = True
        tile.terrain = DetailTerrain.SPOIL_LOOSE
        return tile.terrain

    # ── Coordinate conversion ───────────────────────────────────────────────

    def local_to_detail(self, local_x: int, local_y: int) -> Tuple[int, int]:
        """Convert local map coordinates to detail map coordinates (top-left of block)."""
        dx = (local_x - self.origin_lx) * DTILES_PER_LOCAL
        dy = (local_y - self.origin_ly) * DTILES_PER_LOCAL
        return dx, dy

    def detail_to_local(self, detail_x: int, detail_y: int) -> Tuple[int, int]:
        """Convert detail map coordinates to the corresponding local map tile."""
        lx = self.origin_lx + detail_x // DTILES_PER_LOCAL
        ly = self.origin_ly + detail_y // DTILES_PER_LOCAL
        return lx, ly


# ── Factory function ────────────────────────────────────────────────────────

def make_detail_map(local_map, player_local_x: int, player_local_y: int,
                    seed: int = 0) -> DetailMap:
    """
    Create a DetailMap centred on the player's local map position.

    The returned map has DETAIL_WIDTH×DETAIL_HEIGHT tiles.
    Player's starting detail position: (DETAIL_WIDTH//2, DETAIL_HEIGHT//2)
    """
    half_w = (DETAIL_WIDTH  // DTILES_PER_LOCAL) // 2
    half_h = (DETAIL_HEIGHT // DTILES_PER_LOCAL) // 2
    origin_lx = max(0, player_local_x - half_w)
    origin_ly = max(0, player_local_y - half_h)
    return DetailMap(local_map, origin_lx, origin_ly, seed=seed)
