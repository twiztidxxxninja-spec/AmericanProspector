"""
src/world_map.py

To-scale continent map for American Prospector (1849–2000).
Includes Alaska and southwest Canada.
"""

import random
import numpy as np
from dataclasses import dataclass
from typing import Dict, Tuple, Optional

from src.constants import WORLD_WIDTH, WORLD_HEIGHT
from src.regions import REGIONS, get_region_for_world_tile


# ==================== TERRAIN DEFINITIONS ====================

class Terrain:
    OCEAN     = 0
    PLAINS    = 1
    FOREST    = 2
    HILLS     = 3
    MOUNTAINS = 4
    DESERT    = 5
    SWAMP     = 6
    RIVER     = 7
    COAST     = 8
    TUNDRA    = 9
    PRAIRIE   = 10
    SCRUB     = 11
    CONIFER   = 12


TERRAIN_GLYPH = {
    Terrain.OCEAN:     ("~", ( 30,  80, 180), ( 10,  30,  80)),
    Terrain.PLAINS:    (".", (130, 170,  70), ( 30,  50,  10)),
    Terrain.FOREST:    ("T", ( 35, 105,  35), ( 12,  35,  12)),
    Terrain.HILLS:     ("n", (150, 130,  85), ( 55,  45,  20)),
    Terrain.MOUNTAINS: ("^", (195, 195, 195), ( 85,  85,  85)),
    Terrain.DESERT:    (".", (215, 190, 110), (110,  95,  40)),
    Terrain.SWAMP:     ("~", ( 50,  90,  55), ( 18,  38,  18)),
    Terrain.RIVER:     ("~", ( 65, 145, 225), ( 22,  60, 120)),
    Terrain.COAST:     (".", (205, 185, 125), ( 85,  75,  45)),
    Terrain.TUNDRA:    (".", (155, 165, 145), ( 65,  75,  60)),
    Terrain.PRAIRIE:   ('"', (155, 195,  65), ( 55,  80,  10)),
    Terrain.SCRUB:     (";", (160, 148,  92), ( 72,  62,  30)),
    Terrain.CONIFER:   ("t", ( 22,  78,  22), (  7,  24,   7)),
}

TERRAIN_NAME = {
    Terrain.OCEAN:     "Open Water",
    Terrain.PLAINS:    "Plains",
    Terrain.FOREST:    "Forest",
    Terrain.HILLS:     "Hill Country",
    Terrain.MOUNTAINS: "Mountains",
    Terrain.DESERT:    "Desert",
    Terrain.SWAMP:     "Swamp",
    Terrain.RIVER:     "River",
    Terrain.COAST:     "Coast",
    Terrain.TUNDRA:    "Tundra",
    Terrain.PRAIRIE:   "Prairie",
    Terrain.SCRUB:     "Scrubland",
    Terrain.CONIFER:   "Conifer Forest",
}

TERRAIN_DESCRIPTION = {
    Terrain.OCEAN:     "Open water — impassable on foot.",
    Terrain.PLAINS:    "Flat, open land. Easy travel. Scattered brush and short grass.",
    Terrain.FOREST:    "Dense hardwood forest. Good timber and game. Difficult footing.",
    Terrain.HILLS:     "Rolling hills. Stream cuts and rocky outcrops. Moderate travel.",
    Terrain.MOUNTAINS: "Rugged peaks and deep canyons. Steep scree, thin air.",
    Terrain.DESERT:    "Arid wasteland. Water scarce. Searing heat by day, cold by night.",
    Terrain.SWAMP:     "Boggy wetlands. Standing water, cypress, mosquitoes.",
    Terrain.RIVER:     "A major river. Ford, ferry, or bridge required to cross.",
    Terrain.COAST:     "Sandy shore and tidal flats. Ocean smell on the breeze.",
    Terrain.TUNDRA:    "Open tundra. Permafrost, sparse lichen, brutal cold.",
    Terrain.PRAIRIE:   "Tallgrass sea, flat to gently rolling. Good grazing country.",
    Terrain.SCRUB:     "Sagebrush and dry gullies. Semi-arid, sparse water.",
    Terrain.CONIFER:   "Dense evergreen forest. Excellent timber and fur. Slow going.",
}

TERRAIN_TRAVEL_MULT = {
    Terrain.OCEAN:     99.0,
    Terrain.PLAINS:     1.0,
    Terrain.FOREST:     1.8,
    Terrain.HILLS:      2.0,
    Terrain.MOUNTAINS:  4.0,
    Terrain.DESERT:     1.6,
    Terrain.SWAMP:      2.8,
    Terrain.RIVER:      3.0,
    Terrain.COAST:      1.2,
    Terrain.TUNDRA:     2.5,
    Terrain.PRAIRIE:    1.0,
    Terrain.SCRUB:      1.4,
    Terrain.CONIFER:    2.0,
}


@dataclass
class WorldLocation:
    name: str
    x: int
    y: int
    location_type: str
    population: int = 0
    discovered: bool = False


class WorldMap:
    def __init__(self, seed: int = 42):
        self.width = WORLD_WIDTH
        self.height = WORLD_HEIGHT
        self.seed = seed
        
        self.tiles = np.zeros((self.height, self.width), dtype=np.int8)
        self.elevation = np.zeros((self.height, self.width), dtype=np.float32)
        self.visited = np.zeros((self.height, self.width), dtype=bool)
        self.gold_bias = np.zeros((self.height, self.width), dtype=np.float32)
        # Trail overlay: 0=none, 1=trail, 2=road. Reduces travel time.
        self.trails = np.zeros((self.height, self.width), dtype=np.int8)
        
        self.locations: Dict[str, WorldLocation] = {}
        self._loc_by_pos: Dict[Tuple[int,int], str] = {}
        self.region_map: Dict[Tuple[int,int], str] = {}
        
        self._generate()

    def _generate(self):
        rng = random.Random(self.seed)
        self._place_terrain(rng)
        self._generate_elevation()
        self._place_trails()
        self._place_fixed_locations()
        self._assign_regions_and_gold_bias()
        # Expanded historical locations (100+) and gold-bias hotspots
        try:
            from src.world_gen import WorldGenerator
            WorldGenerator(self.seed).populate(self)
        except Exception:
            pass  # falls back to base 34 locations if world_gen unavailable

    # ── Elevation bands by terrain (feet above sea level) ───────────
    _TERRAIN_ELEV = {
        Terrain.OCEAN:     (0, 0),
        Terrain.COAST:     (0, 200),
        Terrain.SWAMP:     (0, 500),
        Terrain.PLAINS:    (500, 2000),
        Terrain.PRAIRIE:   (1000, 3000),
        Terrain.FOREST:    (500, 3000),
        Terrain.RIVER:     (500, 3000),
        Terrain.SCRUB:     (1500, 4000),
        Terrain.HILLS:     (2000, 5000),
        Terrain.DESERT:    (2000, 4500),
        Terrain.CONIFER:   (3000, 7000),
        Terrain.MOUNTAINS: (5000, 12000),
        Terrain.TUNDRA:    (4000, 10000),
    }

    def _generate_elevation(self):
        """Populate self.elevation with feet-above-sea-level per world tile.
        Uses terrain type to set the range, then Perlin noise for smooth
        variation so adjacent mountain tiles have similar elevations and
        ranges transition gradually."""
        rng = np.random.RandomState(self.seed + 7777)

        # Generate smooth world-scale noise (large features)
        # Two octaves: broad continental shape + regional variation
        noise = np.zeros((self.height, self.width), dtype=np.float32)
        for octave, (freq, amp) in enumerate([(0.008, 0.6), (0.02, 0.3), (0.05, 0.1)]):
            # Phase-shifted sine/cosine noise (cheap, smooth, no perlin dep)
            xs = np.arange(self.width) * freq
            ys = np.arange(self.height) * freq
            phase_x = rng.uniform(0, 6.28)
            phase_y = rng.uniform(0, 6.28)
            x_wave = np.sin(xs + phase_x + octave * 1.7)
            y_wave = np.sin(ys + phase_y + octave * 2.3)
            grid = np.outer(y_wave, x_wave) * amp
            noise += grid
        # Normalize to 0-1
        noise = (noise - noise.min()) / max(noise.max() - noise.min(), 0.001)

        # Map noise to elevation using terrain bands
        for wy in range(self.height):
            for wx in range(self.width):
                terrain = int(self.tiles[wy, wx])
                lo, hi = self._TERRAIN_ELEV.get(terrain, (500, 2000))
                # Noise provides variation within the band
                n = float(noise[wy, wx])
                self.elevation[wy, wx] = lo + n * (hi - lo)

        # Smooth transitions between adjacent tiles (3-pass box blur)
        for _ in range(3):
            padded = np.pad(self.elevation, 1, mode='edge')
            self.elevation = (
                padded[1:-1, 1:-1] * 0.5 +
                padded[:-2, 1:-1] * 0.125 +
                padded[2:, 1:-1] * 0.125 +
                padded[1:-1, :-2] * 0.125 +
                padded[1:-1, 2:] * 0.125
            )

    def get_elevation(self, wx: int, wy: int) -> int:
        """Return elevation in feet above sea level for a world tile."""
        if 0 <= wx < self.width and 0 <= wy < self.height:
            return int(self.elevation[wy, wx])
        return 0

    def _place_trails(self):
        """Place historical trails and roads on the world map.
        Each trail is a list of (x, y) waypoints; Bresenham between them."""
        # (waypoints, trail_type, year_available)
        # trail_type: 1=trail, 2=road
        TRAILS = [
            # Wilderness Road — Cumberland Gap to Boonesborough (1775+)
            ([(350, 198), (348, 196), (345, 192), (342, 190)], 1, 1775),
            # Natchez Trace — Nashville to Natchez (1801 improved)
            ([(335, 205), (330, 210), (325, 215), (315, 220), (310, 225)], 1, 1780),
            # Oregon Trail — Independence to Oregon (1843+)
            ([(285, 160), (270, 150), (250, 140), (230, 135), (210, 130),
              (190, 125), (170, 120), (150, 115), (130, 110), (110, 105),
              (90, 100)], 1, 1843),
            # California Trail — splits from Oregon Trail (1844+)
            ([(210, 130), (200, 135), (180, 140), (160, 148), (140, 155),
              (120, 160), (100, 163)], 1, 1844),
            # Santa Fe Trail — Independence to Santa Fe (1821+)
            ([(285, 160), (270, 165), (255, 170), (240, 175), (225, 180),
              (215, 185)], 1, 1821),
        ]

        for waypoints, trail_type, _year in TRAILS:
            for i in range(len(waypoints) - 1):
                x0, y0 = waypoints[i]
                x1, y1 = waypoints[i + 1]
                # Bresenham line
                dx = abs(x1 - x0)
                dy = abs(y1 - y0)
                sx = 1 if x1 > x0 else -1
                sy = 1 if y1 > y0 else -1
                err = dx - dy
                cx, cy = x0, y0
                while True:
                    if self.in_bounds(cx, cy):
                        self.trails[cy][cx] = max(
                            int(self.trails[cy][cx]), trail_type)
                    if cx == x1 and cy == y1:
                        break
                    e2 = 2 * err
                    if e2 > -dy:
                        err -= dy
                        cx += sx
                    if e2 < dx:
                        err += dx
                        cy += sy

    def _fill_polygon(self, points: list, terrain: int) -> None:
        """Scanline polygon fill on the tiles array."""
        n = len(points)
        if n < 3:
            return
        min_y = max(0, min(p[1] for p in points))
        max_y = min(self.height - 1, max(p[1] for p in points))

        for y in range(min_y, max_y + 1):
            intersections = []
            for i in range(n):
                x1, y1 = points[i]
                x2, y2 = points[(i + 1) % n]
                if y1 == y2:
                    continue
                if min(y1, y2) <= y < max(y1, y2):
                    x = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                    intersections.append(int(x))
            intersections.sort()
            for j in range(0, len(intersections) - 1, 2):
                xs = max(0, intersections[j])
                xe = min(self.width, intersections[j + 1] + 1)
                self.tiles[y, xs:xe] = terrain

    def _paint(self, x1: int, y1: int, x2: int, y2: int, terrain: int, prob: float = 1.0, seed_off: int = 0):
        y1c = max(0, y1)
        y2c = min(self.height, y2)
        x1c = max(0, x1)
        x2c = min(self.width, x2)
        if y2c <= y1c or x2c <= x1c:
            return
        if prob >= 1.0:
            self.tiles[y1c:y2c, x1c:x2c] = terrain
        else:
            rs = np.random.RandomState(self.seed + seed_off)
            mask = rs.random((y2c - y1c, x2c - x1c)) < prob
            old = self.tiles[y1c:y2c, x1c:x2c]
            self.tiles[y1c:y2c, x1c:x2c] = np.where(mask, terrain, old)

    def _place_terrain(self, rng: random.Random):
        T = Terrain
        p = self._paint

        # Start with ALL ocean — then paint US landmass on top
        self.tiles[:] = T.OCEAN

        # ── Continental US outline (polygon fill) ─────────────────────
        # Traced clockwise: Pacific coast → Mexico border → Gulf →
        # Atlantic coast → Canada border → back to Pacific NW
        _US_COAST = [
            # Pacific Coast (N→S)
            (30, 78),  (28, 85),  (27, 92),  (26, 100), (25, 108),
            (23, 118), (21, 128), (19, 138), (18, 148), (20, 158),
            (22, 165), (24, 172), (28, 180), (32, 188), (36, 193),
            # Mexico border (W→E)
            (50, 196), (75, 198), (105, 200),(135, 202),(165, 205),
            (195, 208),(220, 212),(245, 218),(265, 224),
            # Gulf Coast (W→E: Texas → Florida)
            (285, 228),(300, 226),(315, 224),(325, 226),(335, 220),
            (345, 214),(355, 206),(362, 198),(370, 196),(378, 200),
            (385, 208),(390, 216),(395, 220),
            # Florida east coast + Atlantic (S→N)
            (398, 212),(400, 200),(402, 190),(405, 178),(410, 168),
            (415, 158),(420, 148),(424, 140),(428, 132),(432, 124),
            (436, 118),(440, 112),(444, 106),(448, 100),(452, 92),
            (454, 84), (450, 78),
            # Canada border (E→W)
            (440, 76), (425, 74), (410, 73), (395, 72), (380, 71),
            (365, 71), (345, 70), (325, 69), (305, 68), (285, 68),
            (265, 69), (245, 70), (225, 71), (205, 72), (185, 72),
            (165, 72), (145, 73), (125, 73), (105, 74), (80, 75),
            (55, 76),  (40, 77),  (30, 78),
        ]
        self._fill_polygon(_US_COAST, T.PLAINS)

        # ── Alaska outline ────────────────────────────────────────────
        _ALASKA = [
            (15, 15), (85, 15), (92, 22), (90, 35), (85, 48),
            (78, 58), (65, 62), (48, 60), (32, 56), (18, 48),
            (15, 35), (15, 15),
        ]
        self._fill_polygon(_ALASKA, T.TUNDRA)

        # Alaska terrain detail
        p(25, 15, 75, 55, T.MOUNTAINS, 0.65)
        p(30, 18, 70, 50, T.CONIFER, 0.70)

        # Southwest Canada (mountains north of US border)
        p(95, 25, 160, 72, T.MOUNTAINS, 0.82)
        p(105, 30, 150, 65, T.CONIFER, 0.75)

        # Pacific Northwest
        p(13, 26, 21, 38,  T.MOUNTAINS, 0.55, 11)
        p(20, 26, 31, 56,  T.MOUNTAINS, 0.82, 12)
        p(31, 26, 38, 55,  T.MOUNTAINS, 0.38, 13)
        p(13, 26, 22, 58,  T.CONIFER,   1.00)
        p(22, 26, 64, 57,  T.CONIFER,   0.68, 14)
        p(30, 38, 72, 62,  T.SCRUB,     0.80, 15)

        # Sierra Nevada
        p(24, 63, 37, 116, T.MOUNTAINS, 0.88, 20)
        p(37, 65, 44, 112, T.MOUNTAINS, 0.38, 21)

        # California
        p(13, 58, 22, 115, T.HILLS,     0.78, 25)
        p(17, 73, 26, 112, T.PLAINS,    1.00)
        p(13, 110, 30, 132, T.SCRUB,    0.82, 26)

        # Great Basin & Rockies
        p(35, 63, 78, 108, T.DESERT,   0.72, 30)
        p(35, 63, 78, 108, T.SCRUB,    0.50, 31)
        p(62, 27, 100, 68, T.MOUNTAINS, 0.78, 40)
        p(62, 27,  88, 66, T.CONIFER,   0.58, 41)
        p(85, 66, 116, 105, T.MOUNTAINS, 0.82, 42)
        p(85, 100, 112, 132, T.MOUNTAINS, 0.72, 43)

        # Deserts & Plains
        p(58,  88,  90, 125, T.SCRUB,   0.78, 45)
        p(60,  88,  88, 118, T.DESERT,  0.42, 46)
        p(26, 106, 58, 130, T.DESERT,   0.90, 50)
        p(55, 113, 92, 145, T.DESERT,   0.85, 55)
        p(82, 118, 140, 150, T.DESERT,  0.62, 58)

        p(100, 27, 185, 73, T.PRAIRIE,  0.88, 65)
        p(122, 57, 136, 73, T.HILLS,    0.72, 63)
        p(124, 58, 134, 72, T.FOREST,   0.55, 64)
        p(118, 73, 205, 108, T.PRAIRIE, 0.90, 66)
        p(198, 73, 248, 105, T.PRAIRIE, 0.72, 67)
        p(148, 105, 208, 148, T.PLAINS, 0.85, 68)
        p(175, 118, 210, 145, T.HILLS,  0.50, 69)

        # Ozarks, Midwest, Appalachians, East Coast
        p(198, 94, 238, 120, T.HILLS,   0.75, 70)
        p(200, 95, 236, 118, T.FOREST,  0.60, 71)
        p(200, 43, 268, 82, T.FOREST,   0.72, 75)
        p(200, 43, 240, 65, T.CONIFER,  0.55, 76)

        # Great Lakes
        p(212, 43, 252, 54, T.OCEAN)
        p(232, 48, 244, 68, T.OCEAN)
        p(246, 50, 264, 68, T.OCEAN)
        p(260, 70, 296, 77, T.OCEAN)
        p(293, 65, 312, 72, T.OCEAN)

        p(240, 80, 295, 105, T.FOREST,  0.75, 80)

        p(310, 38, 340, 68, T.HILLS,    0.80, 85)
        p(318, 40, 336, 65, T.MOUNTAINS, 0.42, 86)
        p(280, 65, 318, 138, T.HILLS,   0.85, 87)
        p(288, 72, 312, 120, T.MOUNTAINS, 0.40, 88)
        p(288, 110, 318, 138, T.HILLS,  0.82, 89)

        p(322, 36, 358, 68, T.FOREST,   0.82, 90)
        p(325, 38, 355, 65, T.HILLS,    0.52, 91)
        p(306, 65, 355, 98, T.FOREST,   0.72, 92)
        p(330, 78, 358, 148, T.PLAINS,  0.65, 93)
        p(330, 80, 358, 145, T.FOREST,  0.52, 94)
        p(286, 98, 350, 135, T.FOREST,  0.70, 95)

        p(218, 128, 335, 155, T.FOREST, 0.82, 100)

        # Gulf Coast Swamps
        p(160, 145, 312, 158, T.SWAMP,  0.72, 105)
        p(205, 142, 235, 158, T.SWAMP,  1.00)
        p(288, 143, 322, 158, T.SWAMP,  0.82, 106)
        p(330, 128, 358, 158, T.SWAMP,  0.55, 108)
        p(328, 110, 342, 126, T.SWAMP,  0.60, 109)

        # ── Rivers ────────────────────────────────────────────────────────
        # Mississippi River
        for y in range(50, 280):
            xr = 212 + int(2.5 * np.sin((y - 50) * 0.14))
            for ox in range(-1, 2):
                xx = xr + ox
                if 0 <= xx < self.width:
                    self.tiles[y, xx] = T.RIVER

        # Missouri River
        for x in range(98, 213):
            yr = 78 + int(3 * np.sin((x - 98) * 0.07))
            if 0 <= yr < self.height:
                self.tiles[yr, x] = T.RIVER

        # Ohio River
        for x in range(238, 296):
            yr = 93 + int(2 * np.sin((x - 238) * 0.10))
            if 0 <= yr < self.height:
                self.tiles[yr, x] = T.RIVER

        # Colorado River
        for y in range(88, 148):
            xr = int(75 - (y - 88) * 0.28)
            if 0 <= xr < self.width:
                self.tiles[y, xr] = T.RIVER

        # Columbia River
        for x in range(18, 68):
            yr = 46 + int(2 * np.sin((x - 18) * 0.18))
            if 0 <= yr < self.height:
                self.tiles[yr, x] = T.RIVER

        # Rio Grande
        for y in range(100, 156):
            xr = int(105 - (y - 100) * 0.30)
            if 0 <= xr < self.width:
                self.tiles[y, xr] = T.RIVER

        # Arkansas River
        for x in range(105, 213):
            yr = int(103 + (x - 105) * 0.06 + 2 * np.sin((x - 105) * 0.12))
            if 0 <= yr < self.height:
                self.tiles[yr, x] = T.RIVER

        # Platte River
        for x in range(105, 185):
            yr = int(82 - (x - 105) * 0.01 + 1.5 * np.sin((x - 105) * 0.15))
            if 0 <= yr < self.height:
                self.tiles[yr, x] = T.RIVER

    def _assign_regions_and_gold_bias(self):
        for wy in range(self.height):
            for wx in range(self.width):
                region = get_region_for_world_tile(wx, wy)
                self.region_map[(wx, wy)] = region
                self.gold_bias[wy, wx] = REGIONS.get(region, REGIONS["Great Plains"]).gold_bias

    def _place_fixed_locations(self):
        # (name, x, y, type, pop)  — world grid is 400×200, ~10 mi/tile
        locs = [
            # California
            ("Sacramento",      95, 165, "city",   25000),
            ("San Francisco",   72, 172, "city",   60000),
            ("Stockton",        88, 170, "town",    4000),
            ("Coloma",         102, 162, "camp",     200),   # gold discovery site
            ("Grass Valley",    97, 157, "town",    3000),   # hard rock mining
            ("Marysville",      93, 158, "town",    2500),
            ("Los Angeles",     80, 188, "town",    5000),
            # Nevada
            ("Reno",           110, 153, "town",    5000),
            ("Virginia City",  114, 158, "town",   15000),   # Comstock Lode
            # Utah
            ("Salt Lake City", 172, 150, "city",   20000),
            ("Moab",           195, 162, "camp",     500),   # uranium area
            # Colorado
            ("Denver",         222, 155, "city",   35000),
            ("Leadville",      214, 163, "town",   14000),   # silver/lead
            ("Cripple Creek",  224, 165, "town",   10000),   # gold
            ("Grand Junction", 207, 158, "town",    3000),
            # Montana
            ("Butte",          178,  88, "city",   30000),   # copper/silver
            ("Helena",         188,  90, "town",    4000),   # gold
            ("Missoula",       172,  86, "town",    3000),
            # Wyoming
            ("Cheyenne",       222, 128, "town",    8000),   # railroad hub
            ("Casper",         220, 118, "town",    2500),
            # South Dakota
            ("Deadwood",       268, 108, "town",    4000),   # Black Hills gold
            # Idaho
            ("Boise",          152, 125, "town",    5000),
            ("Silver City",    148, 138, "camp",     800),
            # Oregon / Washington
            ("Portland",        78, 108, "city",   20000),
            ("Seattle",         78,  98, "town",    8000),
            # Texas
            ("El Paso",        228, 200, "town",    5000),
            ("San Antonio",    272, 215, "town",   37000),
            ("Beaumont",       308, 218, "town",    9000),   # Spindletop oil 1901
            # Oklahoma
            ("Tulsa",          300, 192, "town",    7000),   # oil boom
            # Pennsylvania
            ("Titusville",     350, 112, "town",    6000),   # first oil well
            # Illinois
            ("Chicago",        313, 115, "city",  500000),
            # Alaska
            ("Juneau",          45,  35, "town",    1000),
            ("Skagway",         40,  38, "camp",    8000),   # Klondike gateway
            ("Fairbanks",       68,  28, "town",    3500),   # interior gold
        ]
        for name, x, y, loc_type, pop in locs:
            if 0 <= y < self.height and 0 <= x < self.width:
                loc = WorldLocation(name=name, x=x, y=y, location_type=loc_type, population=pop)
                self.locations[name] = loc
                # Don't overwrite mountains/rivers — only overwrite ocean/plains
                if int(self.tiles[y, x]) in (Terrain.OCEAN,):
                    self.tiles[y, x] = Terrain.PLAINS

        self._loc_by_pos = {(loc.x, loc.y): name for name, loc in self.locations.items()}

    # Required methods for Engine
    def mark_visited(self, x: int, y: int):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.visited[y][x] = True
            loc = self.get_location_at(x, y)
            if loc:
                loc.discovered = True

    def mark_visited_radius(self, cx: int, cy: int, radius: int):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                self.mark_visited(cx + dx, cy + dy)

    def get_location_at(self, x: int, y: int) -> Optional[WorldLocation]:
        name = self._loc_by_pos.get((x, y))
        return self.locations.get(name)

    def travel_cost(self, x: int, y: int) -> float:
        from src.constants import WORLD_TRAVEL
        terrain = self.tiles[y][x]
        base = WORLD_TRAVEL * TERRAIN_TRAVEL_MULT.get(int(terrain), 1.0)
        # Trails reduce travel time
        if hasattr(self, 'trails') and self.trails[y][x] > 0:
            trail_type = int(self.trails[y][x])
            if trail_type == 2:    # road
                base *= 0.4
            elif trail_type == 1:  # trail
                base *= 0.6
        return base

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def get_region(self, wx: int, wy: int) -> str:
        return self.region_map.get((wx, wy), "Great Plains")

    def get_gold_bias(self, wx: int, wy: int) -> float:
        return float(self.gold_bias[wy, wx])