"""
src/town_gen.py

Town and settlement physical layout generator for American Prospector.

Generates buildings, roads, and structures on the local map when the
player first approaches a named location.  Layout is deterministic
per world position so re-entering the same tile produces the same town.

Two-tier design:
    Tier 1 — permanent named locations exist in WorldMap.locations from
             world creation (world_gen.py).  NPCs know about them, can
             reference them, give directions.
    Tier 2 — physical layout (buildings, streets, wells, corrals) is
             generated on-demand by this module the first time the
             player enters the local map tile.

Settlement types and their layouts:
    mining_camp_small  — scattered tents around a clearing, fire pits
    mining_camp_medium — tents/cabins along a rough path, maybe a store
    boomtown           — main street with wood buildings, side alleys
    small_town         — grid streets, town square, permanent buildings
    trading_post       — single compound: store, corral, living quarters

Integration:
    In engine._ensure_local() or LocalMap._generate(), after base terrain:

        from src.town_gen import TownGenerator, classify_settlement
        loc = world_map.get_location_at(wx, wy)
        if loc:
            stype = classify_settlement(loc.location_type, loc.population)
            gen = TownGenerator(seed=world_map.seed + wx*997 + wy)
            layout = gen.generate(local_map, stype, loc.name)
            # layout.buildings available for NPC placement
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.local_map import LocalMap


# ============================================================================
#  TOWN TERRAIN CONSTANTS
# ============================================================================
# Extend LocalTerrain at runtime so the renderer picks them up.

_TOWN_TERRAIN_REGISTERED = False

# Terrain type IDs (start at 30 to avoid clashing with local_map.py 0-22)
ROAD        = 30
WOOD_FLOOR  = 31
WOOD_WALL   = 32
STONE_WALL  = 33
DOOR        = 34
FENCE       = 35
TENT_CANVAS = 36
HITCHING    = 37
WELL_TILE   = 38
FIREPIT_T   = 39
SIGN_POST   = 40
PORCH       = 41
COUNTER     = 42

_TOWN_GLYPHS = {
    #              glyph   fg_rgb              bg_rgb
    ROAD:        ("=", (140, 115,  75), (55, 42, 22)),
    WOOD_FLOOR:  (".", (155, 118,  68), (62, 45, 24)),
    WOOD_WALL:   ("#", (130, 100,  55), (50, 35, 15)),
    STONE_WALL:  ("#", (150, 148, 140), (65, 62, 58)),
    DOOR:        ("+", (170, 130,  70), (62, 45, 24)),
    FENCE:       ("-", (130, 105,  60), (40, 30, 12)),
    TENT_CANVAS: ("/", (185, 175, 150), (75, 70, 55)),
    HITCHING:    ("|", (110,  85,  50), (35, 25, 10)),
    WELL_TILE:   ("O", (100, 100, 110), (38, 38, 42)),
    FIREPIT_T:   ("*", (200,  90,  30), (80, 30,  8)),
    SIGN_POST:   ("!", (160, 130,  70), (55, 42, 22)),
    PORCH:       (".", (145, 112,  62), (58, 42, 20)),
    COUNTER:     ("=", (120,  90,  50), (45, 32, 15)),
}

_TOWN_PASSABLE = {
    ROAD: True, WOOD_FLOOR: True, WOOD_WALL: False, STONE_WALL: False,
    DOOR: True, FENCE: True, TENT_CANVAS: False, HITCHING: True,
    WELL_TILE: False, FIREPIT_T: True, SIGN_POST: True, PORCH: True,
    COUNTER: False,
}

_TOWN_TRANSPARENT = {
    ROAD: True, WOOD_FLOOR: True, WOOD_WALL: False, STONE_WALL: False,
    DOOR: True, FENCE: True, TENT_CANVAS: False, HITCHING: True,
    WELL_TILE: True, FIREPIT_T: True, SIGN_POST: True, PORCH: True,
    COUNTER: True,
}


def register_town_terrain() -> None:
    """
    Register town terrain types in the LocalTerrain system.
    Call once during engine initialization.
    Safe to call multiple times (idempotent).
    """
    global _TOWN_TERRAIN_REGISTERED
    if _TOWN_TERRAIN_REGISTERED:
        return
    from src.local_map import LocalTerrain, LOCAL_GLYPH, LOCAL_PASSABLE, LOCAL_TRANSPARENT

    LocalTerrain.ROAD        = ROAD
    LocalTerrain.WOOD_FLOOR  = WOOD_FLOOR
    LocalTerrain.WOOD_WALL   = WOOD_WALL
    LocalTerrain.STONE_WALL  = STONE_WALL
    LocalTerrain.DOOR        = DOOR
    LocalTerrain.FENCE       = FENCE
    LocalTerrain.TENT_CANVAS = TENT_CANVAS
    LocalTerrain.HITCHING    = HITCHING
    LocalTerrain.WELL_TILE   = WELL_TILE
    LocalTerrain.FIREPIT_T   = FIREPIT_T
    LocalTerrain.SIGN_POST   = SIGN_POST
    LocalTerrain.PORCH       = PORCH
    LocalTerrain.COUNTER     = COUNTER

    LOCAL_GLYPH.update(_TOWN_GLYPHS)
    LOCAL_PASSABLE.update(_TOWN_PASSABLE)
    LOCAL_TRANSPARENT.update(_TOWN_TRANSPARENT)
    _TOWN_TERRAIN_REGISTERED = True


# ============================================================================
#  BUILDING TEMPLATES
# ============================================================================

@dataclass
class BuildingDef:
    """Template describing a building type."""
    key: str            # lookup key
    label: str          # display name on the map
    w: int              # width in local tiles
    h: int              # height in local tiles
    wall: int           # terrain type for walls (WOOD_WALL, STONE_WALL, TENT_CANVAS)
    floor: int          # terrain type for floor (WOOD_FLOOR, or ROAD for open-air)
    occupation: str     # NPC occupation that works here ("" = residential / no staff)


BUILDING_DEFS: Dict[str, BuildingDef] = {}

def _bd(key, label, w, h, wall, floor, occ=""):
    BUILDING_DEFS[key] = BuildingDef(key, label, w, h, wall, floor, occ)

# Structures — sized so 1 tile = 1 person standing
_bd("tent",           "Tent",             2, 2, TENT_CANVAS, WOOD_FLOOR)
_bd("cabin",          "Cabin",            3, 3, WOOD_WALL,   WOOD_FLOOR)
_bd("general_store",  "General Store",   10, 7, WOOD_WALL,   WOOD_FLOOR, "Merchant")
_bd("saloon",         "Saloon",          14,10, WOOD_WALL,   WOOD_FLOOR, "Saloon Keeper")
_bd("hotel",          "Hotel",           14,12, WOOD_WALL,   WOOD_FLOOR, "Boarding House Keeper")
_bd("boarding_house", "Boarding House",  10, 8, WOOD_WALL,   WOOD_FLOOR, "Boarding House Keeper")
_bd("church",         "Church",          10,14, WOOD_WALL,   WOOD_FLOOR, "Preacher")
_bd("jail",           "Sheriff's Office",10, 7, STONE_WALL,  WOOD_FLOOR, "Sheriff")
_bd("blacksmith",     "Blacksmith",       8, 7, WOOD_WALL,   ROAD,       "Blacksmith")
_bd("assay_office",   "Assay Office",     7, 5, WOOD_WALL,   WOOD_FLOOR, "Assayer")
_bd("livery",         "Livery Stable",   12, 8, WOOD_WALL,   ROAD,       "Teamster")
_bd("bank",           "Bank",             8, 6, STONE_WALL,  WOOD_FLOOR, "Banker")
_bd("doctor_office",  "Doctor's Office",  8, 6, WOOD_WALL,   WOOD_FLOOR, "Doctor")
_bd("lawyer_office",  "Attorney at Law",  6, 5, WOOD_WALL,   WOOD_FLOOR, "Lawyer")
_bd("barber",         "Barber",           6, 5, WOOD_WALL,   WOOD_FLOOR, "Barber")
_bd("newspaper",      "Newspaper Office", 8, 6, WOOD_WALL,   WOOD_FLOOR, "Newspaper Editor")
_bd("telegraph",      "Telegraph Office", 6, 4, WOOD_WALL,   WOOD_FLOOR, "Telegraph Operator")
_bd("school",         "School",          10, 8, WOOD_WALL,   WOOD_FLOOR, "Teacher")
_bd("house",          "House",            7, 6, WOOD_WALL,   WOOD_FLOOR)
_bd("small_house",    "House",            5, 4, WOOD_WALL,   WOOD_FLOOR)
_bd("trading_store",  "Trading Post",    12, 8, WOOD_WALL,   WOOD_FLOOR, "Merchant")
_bd("warehouse",      "Warehouse",       14, 8, WOOD_WALL,   WOOD_FLOOR)
_bd("dancehall",      "Dance Hall",      14,10, WOOD_WALL,   WOOD_FLOOR, "Dancehall Girl")
# ── New buildings (1849 era) ──────────────────────────────────────────────
_bd("brothel",        "Brothel",         12, 8, WOOD_WALL,   WOOD_FLOOR, "Madam")
_bd("gunsmith",       "Gunsmith",         8, 6, WOOD_WALL,   WOOD_FLOOR, "Gunsmith")
_bd("undertaker",     "Undertaker",       8, 6, WOOD_WALL,   WOOD_FLOOR, "Undertaker")
_bd("bakery",         "Bakery",           8, 6, WOOD_WALL,   WOOD_FLOOR, "Baker")
_bd("butcher_shop",   "Butcher Shop",     8, 6, WOOD_WALL,   WOOD_FLOOR, "Butcher")
_bd("tailor",         "Tailor",           8, 6, WOOD_WALL,   WOOD_FLOOR, "Tailor")
_bd("apothecary",     "Apothecary",       8, 6, WOOD_WALL,   WOOD_FLOOR, "Apothecary")
_bd("land_office",    "Land Office",      8, 6, STONE_WALL,  WOOD_FLOOR, "Land Agent")
_bd("courthouse",     "Courthouse",      14,10, STONE_WALL,  WOOD_FLOOR, "Judge")
_bd("theater",        "Opera House",     16,12, WOOD_WALL,   WOOD_FLOOR, "Impresario")
_bd("lumber_mill",    "Lumber Mill",     14, 8, WOOD_WALL,   ROAD,       "Mill Operator")
_bd("brewery",        "Brewery",         10, 8, WOOD_WALL,   WOOD_FLOOR, "Brewmaster")
_bd("bathhouse",      "Bathhouse",        8, 8, WOOD_WALL,   WOOD_FLOOR, "Attendant")
_bd("freight_office", "Freight Office",   8, 6, WOOD_WALL,   WOOD_FLOOR, "Freight Agent")
_bd("laundry",        "Laundry",          6, 5, WOOD_WALL,   WOOD_FLOOR, "Laundress")
_bd("cobbler",        "Cobbler",          6, 5, WOOD_WALL,   WOOD_FLOOR, "Cobbler")
_bd("fur_post",       "Fur Trading Post",12, 8, WOOD_WALL,   WOOD_FLOOR, "Fur Trader")
_bd("bulletin_board", "Bulletin Board",   2, 2, 0,           SIGN_POST)
# Outdoor features (no walls — placed as single terrain tiles)
_bd("fire_pit",       "Fire Pit",         1, 1, 0, FIREPIT_T)
_bd("well",           "Well",             1, 1, 0, WELL_TILE)
_bd("corral",         "Corral",           6, 6, FENCE, ROAD)
_bd("hitching_post",  "Hitching Post",    1, 1, 0, HITCHING)


# ============================================================================
#  SETTLEMENT BUILDING LISTS
# ============================================================================
# For each settlement type:
#   required  — always placed
#   pool      — (building_key, min_count, max_count) sampled randomly
#   layout    — algorithm name

SETTLEMENT_BUILDINGS: Dict[str, dict] = {
    "mining_camp_small": {
        "required": [],
        "pool": [
            ("tent",      3, 6),
            ("fire_pit",  1, 2),
            ("hitching_post", 0, 1),
        ],
        "layout": "scattered",
        "radius": 20,            # scatter radius from center
    },
    "mining_camp_medium": {
        "required": ["general_store"],
        "pool": [
            ("tent",       4, 10),
            ("cabin",      1, 4),
            ("fire_pit",   2, 3),
            ("blacksmith", 0, 1),
            ("saloon",     0, 1),
            ("well",       0, 1),
            ("hitching_post", 1, 2),
        ],
        "layout": "path",
        "radius": 35,
    },
    "boomtown": {
        "required": ["general_store", "saloon", "boarding_house"],
        "pool": [
            ("saloon",      0, 2),
            ("assay_office", 0, 1),
            ("blacksmith",  1, 1),
            ("doctor_office", 0, 1),
            ("barber",      0, 1),
            ("livery",      0, 1),
            ("newspaper",   0, 1),
            ("dancehall",   0, 1),
            ("house",       2, 6),
            ("small_house", 2, 5),
            ("tent",        3, 8),
            ("well",        1, 2),
            ("hitching_post", 2, 4),
            ("fire_pit",    1, 2),
        ],
        "layout": "main_street",
        "street_len": 70,
    },
    "small_town": {
        "required": ["general_store", "saloon", "hotel", "church", "jail"],
        "pool": [
            ("bank",         0, 1),
            ("school",       0, 1),
            ("telegraph",    0, 1),
            ("assay_office", 0, 1),
            ("blacksmith",   1, 1),
            ("doctor_office",1, 1),
            ("lawyer_office",0, 1),
            ("barber",       0, 1),
            ("livery",       1, 1),
            ("newspaper",    0, 1),
            ("dancehall",    0, 1),
            ("warehouse",    0, 1),
            ("boarding_house",0, 2),
            ("gunsmith",     0, 1),
            ("bakery",       0, 1),
            ("brothel",      0, 1),
            ("bathhouse",    0, 1),
            ("house",        4, 10),
            ("small_house",  3, 8),
            ("well",         1, 3),
            ("hitching_post",3, 6),
            ("bulletin_board",1, 1),
            ("corral",       0, 2),
        ],
        "layout": "grid",
        "streets_ew": 3,
        "streets_ns": 3,
    },
    "city": {
        "required": ["general_store", "saloon", "hotel", "church", "jail",
                     "bank", "courthouse", "school", "newspaper"],
        "pool": [
            ("saloon",       1, 3),
            ("hotel",        0, 2),
            ("blacksmith",   1, 2),
            ("doctor_office",1, 2),
            ("lawyer_office",1, 2),
            ("barber",       1, 2),
            ("livery",       1, 2),
            ("telegraph",    1, 1),
            ("assay_office", 0, 1),
            ("dancehall",    1, 2),
            ("warehouse",    1, 3),
            ("boarding_house",1, 3),
            ("brothel",      1, 2),
            ("gunsmith",     1, 1),
            ("undertaker",   1, 1),
            ("bakery",       1, 2),
            ("butcher_shop", 1, 1),
            ("tailor",       1, 1),
            ("apothecary",   1, 1),
            ("land_office",  1, 1),
            ("theater",      0, 1),
            ("lumber_mill",  0, 1),
            ("brewery",      0, 1),
            ("bathhouse",    1, 1),
            ("freight_office",1, 1),
            ("laundry",      1, 2),
            ("cobbler",      0, 1),
            ("trading_store",0, 1),
            ("house",        8, 20),
            ("small_house",  5, 12),
            ("well",         2, 5),
            ("hitching_post",4, 8),
            ("bulletin_board",1, 2),
            ("corral",       1, 3),
        ],
        "layout": "grid",
        "streets_ew": 5,
        "streets_ns": 5,
    },
    "trading_post": {
        "required": ["trading_store"],
        "pool": [
            ("fur_post",    0, 1),
            ("cabin",       1, 3),
            ("corral",      1, 1),
            ("well",        1, 1),
            ("hitching_post", 1, 2),
            ("fire_pit",    1, 1),
        ],
        "layout": "compound",
        "radius": 22,
    },
}


# ============================================================================
#  PLACED BUILDING
# ============================================================================

@dataclass
class PlacedBuilding:
    """A building placed on the local map."""
    template: str       # key into BUILDING_DEFS
    x: int              # top-left corner (local map coords)
    y: int
    w: int              # actual dimensions
    h: int
    door_x: int         # door tile position
    door_y: int
    label: str = ""     # display name
    occupation: str = "" # NPC occupation associated with this building


# ============================================================================
#  SETTLEMENT LAYOUT
# ============================================================================

@dataclass
class SettlementLayout:
    """Complete layout of a settlement — result of generation."""
    buildings: List[PlacedBuilding] = field(default_factory=list)
    road_tiles: List[Tuple[int, int]] = field(default_factory=list)
    settlement_type: str = ""
    settlement_name: str = ""
    center_x: int = 192
    center_y: int = 192

    def building_at(self, x: int, y: int) -> Optional[PlacedBuilding]:
        """Return the building whose footprint contains (x, y), or None."""
        for b in self.buildings:
            if b.x <= x < b.x + b.w and b.y <= y < b.y + b.h:
                return b
        return None

    def to_dict(self) -> Dict:
        return {
            "buildings": [
                {"template": b.template, "x": b.x, "y": b.y,
                 "w": b.w, "h": b.h, "door_x": b.door_x, "door_y": b.door_y,
                 "label": b.label, "occupation": b.occupation}
                for b in self.buildings
            ],
            "road_tiles": self.road_tiles,
            "settlement_type": self.settlement_type,
            "settlement_name": self.settlement_name,
            "center_x": self.center_x,
            "center_y": self.center_y,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "SettlementLayout":
        layout = cls()
        layout.settlement_type = d.get("settlement_type", "")
        layout.settlement_name = d.get("settlement_name", "")
        layout.center_x = d.get("center_x", 192)
        layout.center_y = d.get("center_y", 192)
        layout.road_tiles = [tuple(t) for t in d.get("road_tiles", [])]
        for bd in d.get("buildings", []):
            layout.buildings.append(PlacedBuilding(**bd))
        return layout


# ============================================================================
#  SETTLEMENT TYPE CLASSIFIER
# ============================================================================

def classify_settlement(loc_type: str, population: int) -> str:
    """
    Determine settlement_type from a WorldLocation's type and population.

    Also handles DynamicLocation.loc_type values.
    """
    lt = loc_type.lower()
    if lt == "mining_camp":
        return "mining_camp_small" if population < 25 else "mining_camp_medium"
    if lt == "prospector_camp":
        return "mining_camp_small"
    if lt in ("waystation", "trading_post"):
        return "trading_post"
    if lt == "boomtown" or (lt == "town" and population > 2000):
        return "boomtown"
    if lt == "city" or population > 10000:
        return "city"
    if population > 5000:
        return "small_town"
    if lt == "fort" or lt == "outpost":
        return "trading_post"
    if lt == "camp":
        return "mining_camp_small" if population < 25 else "mining_camp_medium"
    if lt == "town":
        return "boomtown" if population > 500 else "mining_camp_medium"
    return "mining_camp_medium"


# ============================================================================
#  TOWN GENERATOR
# ============================================================================

class TownGenerator:
    """
    Generates a settlement layout on a LocalMap.
    Deterministic for the same seed.

    Usage:
        gen = TownGenerator(seed=world_seed + wx*997 + wy)
        layout = gen.generate(local_map, "boomtown", "Sacramento")
        # layout.buildings contains all placed buildings with NPC occupation hints
    """

    def __init__(self, seed: int = 0):
        self.seed = seed
        self.rng = random.Random(seed)

    def generate(self, local_map: "LocalMap", settlement_type: str,
                 settlement_name: str = "") -> SettlementLayout:
        """Main entry: generate and apply settlement layout to local_map."""
        register_town_terrain()

        sett = SETTLEMENT_BUILDINGS.get(settlement_type,
                                         SETTLEMENT_BUILDINGS["mining_camp_small"])
        cx = local_map.width  // 2
        cy = local_map.height // 2

        layout = SettlementLayout(
            settlement_type=settlement_type,
            settlement_name=settlement_name,
            center_x=cx, center_y=cy,
        )

        # Collect buildings to place
        to_place: List[str] = list(sett["required"])
        for bkey, lo, hi in sett["pool"]:
            count = self.rng.randint(lo, hi)
            to_place.extend([bkey] * count)

        # Route to layout algorithm
        algo = sett.get("layout", "scattered")
        if algo == "main_street":
            self._layout_main_street(local_map, layout, to_place, sett)
        elif algo == "grid":
            self._layout_grid(local_map, layout, to_place, sett)
        elif algo == "compound":
            self._layout_compound(local_map, layout, to_place, sett)
        elif algo == "path":
            self._layout_path(local_map, layout, to_place, sett)
        else:
            self._layout_scattered(local_map, layout, to_place, sett)

        # Apply layout to local map tiles
        self._apply_to_map(local_map, layout)

        return layout

    # ── Layout algorithms ──────────────────────────────────────────────

    def _layout_scattered(self, lm, layout: SettlementLayout,
                           to_place: List[str], sett: dict) -> None:
        """
        Mining camp: tents and fire pits scattered in a circular clearing.
        No roads, just a rough clearing in the terrain.
        """
        cx, cy = layout.center_x, layout.center_y
        radius = sett.get("radius", 14)

        # Clear a rough circular area
        self._clear_area(lm, cx, cy, radius)

        placed_rects: List[Tuple[int, int, int, int]] = []
        for bkey in to_place:
            bdef = BUILDING_DEFS.get(bkey)
            if not bdef:
                continue
            pos = self._find_scattered_pos(cx, cy, radius, bdef.w, bdef.h,
                                            placed_rects, lm)
            if pos:
                px, py = pos
                pb = self._place_building(lm, bdef, px, py)
                layout.buildings.append(pb)
                placed_rects.append((px, py, bdef.w, bdef.h))

    def _layout_path(self, lm, layout: SettlementLayout,
                      to_place: List[str], sett: dict) -> None:
        """
        Medium camp: a winding path through the center with buildings
        placed along both sides.
        """
        cx, cy = layout.center_x, layout.center_y
        radius = sett.get("radius", 22)

        # Create a roughly east-west path through the center
        path_y = cy
        for px in range(cx - radius, cx + radius + 1):
            path_y += self.rng.choice([-1, 0, 0, 0, 1])
            path_y = max(cy - 4, min(cy + 4, path_y))
            if lm.in_bounds(px, path_y):
                layout.road_tiles.append((px, path_y))

        # Clear area around path
        self._clear_area(lm, cx, cy, radius)

        # Place buildings alternating above and below the path
        placed_rects: List[Tuple[int, int, int, int]] = []
        side = 1
        cursor_x = cx - radius + 2

        for bkey in to_place:
            bdef = BUILDING_DEFS.get(bkey)
            if not bdef:
                continue
            # Try placing beside the path
            if side > 0:
                by = cy - 3 - bdef.h
            else:
                by = cy + 3
            bx = cursor_x

            if self._can_place(bx, by, bdef.w, bdef.h, placed_rects, lm):
                pb = self._place_building(lm, bdef, bx, by)
                layout.buildings.append(pb)
                placed_rects.append((bx, by, bdef.w, bdef.h))
                cursor_x += bdef.w + 1
            else:
                # Try scattered fallback
                pos = self._find_scattered_pos(cx, cy, radius, bdef.w, bdef.h,
                                                placed_rects, lm)
                if pos:
                    pb = self._place_building(lm, bdef, pos[0], pos[1])
                    layout.buildings.append(pb)
                    placed_rects.append((pos[0], pos[1], bdef.w, bdef.h))

            side *= -1
            if cursor_x > cx + radius - 4:
                cursor_x = cx - radius + 2

    def _layout_main_street(self, lm, layout: SettlementLayout,
                             to_place: List[str], sett: dict) -> None:
        """
        Boomtown: one main street running east-west with buildings
        on both sides and alleys between them.
        """
        cx, cy = layout.center_x, layout.center_y
        street_len = sett.get("street_len", 36)
        half = street_len // 2

        # Main street: 2 tiles wide
        for sx in range(cx - half, cx + half + 1):
            for sy in (cy, cy + 1):
                if lm.in_bounds(sx, sy):
                    layout.road_tiles.append((sx, sy))

        # Clear the town area
        self._clear_area(lm, cx, cy, max(half + 6, 24))

        # Sort buildings: larger ones first (they're harder to place)
        to_place.sort(key=lambda k: -(BUILDING_DEFS.get(k, BuildingDef("", "", 1, 1, 0, 0, "")).w *
                                       BUILDING_DEFS.get(k, BuildingDef("", "", 1, 1, 0, 0, "")).h))

        placed_rects: List[Tuple[int, int, int, int]] = []
        north_cursor = cx - half + 1
        south_cursor = cx - half + 1

        for bkey in to_place:
            bdef = BUILDING_DEFS.get(bkey)
            if not bdef:
                continue

            placed = False
            # Try north side of street
            bx = north_cursor
            by = cy - 2 - bdef.h  # 1 tile porch gap
            if self._can_place(bx, by, bdef.w, bdef.h, placed_rects, lm):
                # Add porch between building and street
                for px in range(bx, bx + bdef.w):
                    if lm.in_bounds(px, cy - 1):
                        layout.road_tiles.append((px, cy - 1))
                pb = self._place_building(lm, bdef, bx, by)
                layout.buildings.append(pb)
                placed_rects.append((bx, by, bdef.w, bdef.h))
                north_cursor = bx + bdef.w + 1
                placed = True

            if not placed:
                # Try south side
                bx = south_cursor
                by = cy + 3  # street is 2 wide + 1 porch
                if self._can_place(bx, by, bdef.w, bdef.h, placed_rects, lm):
                    for px in range(bx, bx + bdef.w):
                        if lm.in_bounds(px, cy + 2):
                            layout.road_tiles.append((px, cy + 2))
                    pb = self._place_building(lm, bdef, bx, by)
                    layout.buildings.append(pb)
                    placed_rects.append((bx, by, bdef.w, bdef.h))
                    south_cursor = bx + bdef.w + 1
                    placed = True

            if not placed:
                # Overflow to side streets
                pos = self._find_scattered_pos(cx, cy, half, bdef.w, bdef.h,
                                                placed_rects, lm)
                if pos:
                    pb = self._place_building(lm, bdef, pos[0], pos[1])
                    layout.buildings.append(pb)
                    placed_rects.append((pos[0], pos[1], bdef.w, bdef.h))

        # Add cross-street alleys
        for i in range(2):
            alley_x = cx - half // 3 + i * (2 * half // 3)
            for ay in range(cy - 15, cy + 15):
                if lm.in_bounds(alley_x, ay):
                    layout.road_tiles.append((alley_x, ay))

    def _layout_grid(self, lm, layout: SettlementLayout,
                      to_place: List[str], sett: dict) -> None:
        """
        Established town: grid of streets with buildings in blocks.
        Town square at center intersection.
        """
        cx, cy = layout.center_x, layout.center_y
        ew = sett.get("streets_ew", 3)
        ns = sett.get("streets_ns", 3)
        block_w = 20    # tiles between N-S streets (fits bigger buildings)
        block_h = 16    # tiles between E-W streets

        total_w = ns * block_w + (ns + 1)
        total_h = ew * block_h + (ew + 1)
        start_x = cx - total_w // 2
        start_y = cy - total_h // 2

        self._clear_area(lm, cx, cy, max(total_w, total_h) // 2 + 4)

        # Lay E-W streets
        for i in range(ew + 1):
            sy = start_y + i * (block_h + 1)
            for sx in range(start_x, start_x + total_w):
                if lm.in_bounds(sx, sy):
                    layout.road_tiles.append((sx, sy))

        # Lay N-S streets
        for i in range(ns + 1):
            sx = start_x + i * (block_w + 1)
            for sy in range(start_y, start_y + total_h):
                if lm.in_bounds(sx, sy):
                    layout.road_tiles.append((sx, sy))

        # Town square: clear center block
        sq_x = start_x + (ns // 2) * (block_w + 1) + 1
        sq_y = start_y + (ew // 2) * (block_h + 1) + 1
        for sy in range(sq_y, sq_y + block_h):
            for sx in range(sq_x, sq_x + block_w):
                if lm.in_bounds(sx, sy):
                    layout.road_tiles.append((sx, sy))

        # Place buildings in blocks (skip center block = town square)
        to_place.sort(key=lambda k: -(BUILDING_DEFS.get(k, BuildingDef("", "", 1, 1, 0, 0, "")).w *
                                       BUILDING_DEFS.get(k, BuildingDef("", "", 1, 1, 0, 0, "")).h))

        placed_rects: List[Tuple[int, int, int, int]] = []
        bldg_idx = 0

        for bi in range(ew):
            for bj in range(ns):
                if bi == ew // 2 and bj == ns // 2:
                    continue  # skip town square block

                blk_x = start_x + bj * (block_w + 1) + 1
                blk_y = start_y + bi * (block_h + 1) + 1

                # Fill this block with buildings
                cursor_x = blk_x
                cursor_y = blk_y
                while bldg_idx < len(to_place):
                    bkey = to_place[bldg_idx]
                    bdef = BUILDING_DEFS.get(bkey)
                    if not bdef:
                        bldg_idx += 1
                        continue
                    if cursor_x + bdef.w > blk_x + block_w:
                        cursor_x = blk_x
                        cursor_y += bdef.h + 1
                    if cursor_y + bdef.h > blk_y + block_h:
                        break  # block full, move to next
                    if self._can_place(cursor_x, cursor_y, bdef.w, bdef.h,
                                        placed_rects, lm):
                        pb = self._place_building(lm, bdef, cursor_x, cursor_y)
                        layout.buildings.append(pb)
                        placed_rects.append((cursor_x, cursor_y, bdef.w, bdef.h))
                        cursor_x += bdef.w + 1
                    else:
                        cursor_x += 1
                    bldg_idx += 1

    def _layout_compound(self, lm, layout: SettlementLayout,
                          to_place: List[str], sett: dict) -> None:
        """
        Trading post: a main building with outbuildings around it.
        """
        cx, cy = layout.center_x, layout.center_y
        radius = sett.get("radius", 10)
        self._clear_area(lm, cx, cy, radius)

        placed_rects: List[Tuple[int, int, int, int]] = []

        # Place main building at center
        if to_place:
            main_key = to_place.pop(0)
            bdef = BUILDING_DEFS.get(main_key)
            if bdef:
                bx = cx - bdef.w // 2
                by = cy - bdef.h // 2
                pb = self._place_building(lm, bdef, bx, by)
                layout.buildings.append(pb)
                placed_rects.append((bx, by, bdef.w, bdef.h))

        # Scatter outbuildings around the main one
        for bkey in to_place:
            bdef = BUILDING_DEFS.get(bkey)
            if not bdef:
                continue
            pos = self._find_scattered_pos(cx, cy, radius, bdef.w, bdef.h,
                                            placed_rects, lm)
            if pos:
                pb = self._place_building(lm, bdef, pos[0], pos[1])
                layout.buildings.append(pb)
                placed_rects.append((pos[0], pos[1], bdef.w, bdef.h))

        # Road from center to edges
        for dx in range(cx - radius, cx + radius + 1):
            if lm.in_bounds(dx, cy + 3):
                layout.road_tiles.append((dx, cy + 3))

    # ── Building placement helpers ─────────────────────────────────────

    def _place_building(self, lm, bdef: BuildingDef,
                         bx: int, by: int) -> PlacedBuilding:
        """Create a PlacedBuilding (does not write to map yet)."""
        # Door in the center of the south wall
        door_x = bx + bdef.w // 2
        door_y = by + bdef.h - 1
        return PlacedBuilding(
            template=bdef.key, x=bx, y=by, w=bdef.w, h=bdef.h,
            door_x=door_x, door_y=door_y,
            label=bdef.label, occupation=bdef.occupation,
        )

    def _can_place(self, x: int, y: int, w: int, h: int,
                    placed: List[Tuple[int, int, int, int]],
                    lm) -> bool:
        """Check if a rectangle fits without overlapping placed buildings."""
        if not lm.in_bounds(x, y) or not lm.in_bounds(x + w - 1, y + h - 1):
            return False
        for px, py, pw, ph in placed:
            if not (x + w <= px or px + pw <= x or
                    y + h <= py or py + ph <= y):
                return False
        return True

    def _find_scattered_pos(self, cx: int, cy: int, radius: int,
                             w: int, h: int,
                             placed: List[Tuple[int, int, int, int]],
                             lm) -> Optional[Tuple[int, int]]:
        """Find a random non-overlapping position within radius of center."""
        for _ in range(40):
            bx = cx + self.rng.randint(-radius, radius - w)
            by = cy + self.rng.randint(-radius, radius - h)
            if self._can_place(bx, by, w, h, placed, lm):
                return (bx, by)
        return None

    def _clear_area(self, lm, cx: int, cy: int, radius: int) -> None:
        """Clear terrain in a rough circle to make room for the settlement."""
        from src.local_map import LocalTerrain
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy <= radius * radius:
                    nx, ny = cx + dx, cy + dy
                    if lm.in_bounds(nx, ny):
                        t = lm.tiles[ny][nx].terrain
                        # Only clear natural terrain, not water or rock
                        if t not in (LocalTerrain.WATER, LocalTerrain.ROCK,
                                     LocalTerrain.BEDROCK):
                            lm.tiles[ny][nx].terrain = LocalTerrain.GROUND

    # ── Apply layout to local map ──────────────────────────────────────

    def _apply_to_map(self, lm, layout: SettlementLayout) -> None:
        """
        Write all roads and buildings to the local map.

        Buildings use EDGE-BASED WALLS via lm.wall_grid:
        - All tiles inside the building footprint become floor tiles
          (walkable, usable space).
        - Walls are placed on the outer edges of perimeter tiles, not
          as full impassable tiles.
        - Doors are edge openings (passable, no LOS block).

        This matches the player construction system in construction.py.
        """
        from src.construction import Edge

        # Ensure wall_grid exists on this local map
        if not hasattr(lm, "wall_grid") or lm.wall_grid is None:
            from src.construction import WallGrid
            lm.wall_grid = WallGrid()
        wg = lm.wall_grid

        # Map BuildingDef.wall terrain constants → Edge types
        _WALL_TO_EDGE = {
            WOOD_WALL:   Edge.WOOD_WALL,
            STONE_WALL:  Edge.STONE_WALL,
            FENCE:       Edge.FENCE,
            TENT_CANVAS: Edge.CANVAS,
        }

        # Roads first
        for rx, ry in layout.road_tiles:
            if lm.in_bounds(rx, ry):
                lm.tiles[ry][rx].terrain = ROAD

        # Buildings
        for b in layout.buildings:
            bdef = BUILDING_DEFS.get(b.template)
            if not bdef:
                continue

            # Single-tile features (fire pit, well, hitching post)
            if bdef.w == 1 and bdef.h == 1 and bdef.wall == 0:
                if lm.in_bounds(b.x, b.y):
                    lm.tiles[b.y][b.x].terrain = bdef.floor
                continue

            # Determine edge type for this building's walls
            edge_type = _WALL_TO_EDGE.get(bdef.wall, Edge.WOOD_WALL)
            floor_terrain = bdef.floor if bdef.floor else WOOD_FLOOR

            # All tiles inside footprint become floor (walkable space)
            for dy in range(bdef.h):
                for dx in range(bdef.w):
                    nx, ny = b.x + dx, b.y + dy
                    if lm.in_bounds(nx, ny):
                        lm.tiles[ny][nx].terrain = floor_terrain

            # Place edge walls on the outer boundary
            for dx in range(bdef.w):
                # North wall (top row, north edge)
                wg.set_edge(b.x + dx, b.y, "N", edge_type)
                # South wall (bottom row, south edge)
                wg.set_edge(b.x + dx, b.y + bdef.h - 1, "S", edge_type)

            for dy in range(bdef.h):
                # West wall (left column, west edge)
                wg.set_edge(b.x, b.y + dy, "W", edge_type)
                # East wall (right column, east edge)
                wg.set_edge(b.x + bdef.w - 1, b.y + dy, "E", edge_type)

            # Door — replace one wall segment with a door edge
            if lm.in_bounds(b.door_x, b.door_y):
                # Figure out which edge the door is on
                if b.door_y == b.y + bdef.h - 1:
                    wg.set_edge(b.door_x, b.door_y, "S", Edge.DOOR)
                elif b.door_y == b.y:
                    wg.set_edge(b.door_x, b.door_y, "N", Edge.DOOR)
                elif b.door_x == b.x:
                    wg.set_edge(b.door_x, b.door_y, "W", Edge.DOOR)
                elif b.door_x == b.x + bdef.w - 1:
                    wg.set_edge(b.door_x, b.door_y, "E", Edge.DOOR)

            # Sign post in front of labeled buildings
            if b.label and b.label not in ("House", "Cabin", "Tent"):
                sign_x = b.door_x
                sign_y = b.door_y + 1
                if lm.in_bounds(sign_x, sign_y):
                    t = lm.tiles[sign_y][sign_x].terrain
                    if t in (ROAD, 0, 1):  # GROUND, GRASS
                        lm.tiles[sign_y][sign_x].terrain = SIGN_POST

            # Spawn skill books inside certain buildings
            if b.label in ("School", "Doctor's Office", "Attorney at Law",
                            "Church", "Newspaper Office", "Hotel",
                            "Boarding House", "House"):
                try:
                    from src.items import random_skill_books
                    import random as _bk_rng
                    books = random_skill_books(
                        _bk_rng.Random(self.seed + b.x * 100 + b.y),
                        count=_bk_rng.Random(self.seed + b.y).randint(0, 2))
                    for book in books:
                        # Place on floor inside the building
                        bx = b.x + b.w // 2
                        by = b.y + b.h // 2
                        if lm.in_bounds(bx, by):
                            lm.tiles[by][bx].ground_items.append(book)
                except Exception:
                    pass

            # Furnish building interior with furniture + items
            self._furnish_building(lm, b)

    def _furnish_building(self, lm, b):
        """Place furniture and items inside a building based on its type."""
        from src.local_map import LocalTerrain
        import random as _frng
        rng = _frng.Random(self.seed + b.x * 311 + b.y * 173)

        key = b.template
        bx, by, bw, bh = b.x, b.y, b.w, b.h

        def _set(x, y, terrain):
            if lm.in_bounds(x, y):
                lm.tiles[y][x].terrain = terrain

        def _place_item(x, y, item_id, qty=1):
            if not lm.in_bounds(x, y):
                return
            try:
                from src.items import make_item
                item = make_item(item_id)
                if qty > 1 and item.stackable:
                    item.quantity = qty
                lm.tiles[y][x].ground_items.append(item)
            except Exception:
                pass

        # ── General Store ─────────────────────────────────────────
        if key == "general_store":
            # Shelves along left and right walls
            for iy in range(by + 1, by + bh - 1):
                _set(bx + 1, iy, LocalTerrain.SHELF)
                _set(bx + bw - 2, iy, LocalTerrain.SHELF)
            # Shelves along back wall
            for ix in range(bx + 2, bx + bw - 2):
                _set(ix, by + 1, LocalTerrain.SHELF)
            # Counter across middle
            counter_y = by + bh * 3 // 5
            for ix in range(bx + 2, bx + bw - 2):
                _set(ix, counter_y, LocalTerrain.BAR_COUNTER)
            # Items on shelves
            _place_item(bx + 1, by + 2, "hardtack", 5)
            _place_item(bx + 1, by + 3, "salt", 3)
            _place_item(bx + 1, by + 4, "coffee_beans", 2)
            _place_item(bx + bw - 2, by + 2, "rope_10ft", 3)
            _place_item(bx + bw - 2, by + 3, "rifle_ball", 10)
            _place_item(bx + bw - 2, by + 4, "tobacco", 3)
            _place_item(bx + 3, by + 1, "canteen")

        # ── Saloon ────────────────────────────────────────────────
        elif key == "saloon":
            # Long bar counter along back wall
            for ix in range(bx + 1, bx + bw // 2 + 2):
                _set(ix, by + 1, LocalTerrain.BAR_COUNTER)
            # Liquor shelf behind bar
            for ix in range(bx + 1, bx + bw // 2 + 2):
                _set(ix, by + 2, LocalTerrain.SHELF)
            # Tables with chairs (3-4 groups)
            for i in range(3):
                tx = bx + 2 + i * 4
                ty = by + 4 + (i % 2) * 2
                if tx + 1 < bx + bw - 1 and ty + 1 < by + bh - 1:
                    _set(tx, ty, LocalTerrain.TABLE)
                    _set(tx + 1, ty, LocalTerrain.TABLE)
                    _set(tx - 1, ty, LocalTerrain.CHAIR)
                    _set(tx + 2, ty, LocalTerrain.CHAIR)
                    _set(tx, ty + 1, LocalTerrain.CHAIR)
                    _set(tx + 1, ty + 1, LocalTerrain.CHAIR)
            # Barrels in corners
            _set(bx + bw - 2, by + bh - 2, LocalTerrain.BARREL_TILE)
            _set(bx + bw - 3, by + bh - 2, LocalTerrain.BARREL_TILE)
            # Items
            _place_item(bx + 2, by + 1, "whiskey", 3)
            _place_item(bx + 4, by + 1, "whiskey", 2)
            _place_item(bx + 3, by + 4, "playing_cards")
            _place_item(bx + 7, by + 6, "tobacco")

        # ── Hotel ─────────────────────────────────────────────────
        elif key == "hotel":
            # Front desk
            _set(bx + 1, by + 1, LocalTerrain.DESK)
            for ix in range(bx + 3, bx + bw // 2 + 1):
                _set(ix, by + 1, LocalTerrain.BAR_COUNTER)
            # Lobby chairs
            _set(bx + 1, by + 3, LocalTerrain.CHAIR)
            _set(bx + 2, by + 3, LocalTerrain.CHAIR)
            # Guest rooms — two rows of 3
            rooms_per_row = min(3, (bw - 2) // 4)
            for row in range(2):
                ry = by + 4 + row * 3
                for col in range(rooms_per_row):
                    rx = bx + 1 + col * 4
                    _set(rx, ry, LocalTerrain.BED)
                    _place_item(rx, ry, "bedroll")
            _place_item(bx + 1, by + 1, "candle")

        # ── Jail ──────────────────────────────────────────────────
        elif key == "jail":
            # Office: desk + rifle rack
            _set(bx + 1, by + 1, LocalTerrain.DESK)
            _set(bx + bw - 2, by + 1, LocalTerrain.SHELF)
            # Cell bars across middle
            cell_y = by + bh // 2
            for ix in range(bx + 1, bx + bw - 1):
                _set(ix, cell_y, LocalTerrain.CELL_BARS)
            # Gap for cell door
            _set(bx + bw // 2, cell_y, LocalTerrain.WOOD_FLOOR)
            # Beds in cells
            for ix in range(bx + 1, bx + bw - 1, 3):
                if ix < bx + bw - 1:
                    _set(ix, cell_y + 1, LocalTerrain.BED)
            _place_item(bx + 1, by + 1, "percussion_rifle")
            _place_item(bx + 1, by + 2, "rifle_ball", 5)

        # ── Blacksmith ────────────────────────────────────────────
        elif key == "blacksmith":
            _set(bx + 1, by + 1, LocalTerrain.ANVIL_TILE)
            _set(bx + 2, by + 3, LocalTerrain.STOVE)
            _set(bx + 3, by + 3, LocalTerrain.STOVE)
            # Barrels
            _set(bx + bw - 2, by + bh - 2, LocalTerrain.BARREL_TILE)
            _set(bx + bw - 3, by + bh - 2, LocalTerrain.BARREL_TILE)
            _set(bx + 1, by + bh - 2, LocalTerrain.BARREL_TILE)
            _place_item(bx + bw - 2, by + bh - 2, "iron_bar", 3)
            _place_item(bx + 1, by + bh - 2, "nail", 5)

        # ── Church ────────────────────────────────────────────────
        elif key == "church":
            # Pulpit at front
            _set(bx + bw // 2, by + 1, LocalTerrain.DESK)
            # Pews — rows of chairs
            for row in range(min(8, bh - 4)):
                py = by + 3 + row
                for col in range(bw - 4):
                    _set(bx + 2 + col, py, LocalTerrain.CHAIR)

        # ── Bank ──────────────────────────────────────────────────
        elif key == "bank":
            _set(bx + 1, by + 1, LocalTerrain.DESK)
            # Vault shelves
            for iy in range(by + 1, by + 3):
                _set(bx + bw - 2, iy, LocalTerrain.SHELF)
            # Teller counter
            counter_y = by + bh // 2
            for ix in range(bx + 1, bx + bw - 1):
                _set(ix, counter_y, LocalTerrain.BAR_COUNTER)

        # ── Doctor ────────────────────────────────────────────────
        elif key == "doctor_office":
            _set(bx + 1, by + 1, LocalTerrain.BED)
            _set(bx + 3, by + 1, LocalTerrain.BED)
            _set(bx + 5, by + 1, LocalTerrain.BED)
            _set(bx + bw - 2, by + 1, LocalTerrain.SHELF)
            _set(bx + bw - 2, by + 2, LocalTerrain.SHELF)
            _set(bx + 2, by + bh - 2, LocalTerrain.DESK)
            _place_item(bx + bw - 2, by + 1, "laudanum", 2)
            _place_item(bx + bw - 2, by + 2, "bandage", 5)

        # ── House / Small House ───────────────────────────────────
        elif key in ("house", "small_house"):
            _set(bx + 1, by + 1, LocalTerrain.BED)
            if bw > 4:
                _set(bx + 3, by + 1, LocalTerrain.BED)
            _set(bx + bw - 2, by + 1, LocalTerrain.STOVE)
            _set(bx + bw - 2, by + bh - 2, LocalTerrain.TABLE)
            _set(bx + bw - 3, by + bh - 2, LocalTerrain.CHAIR)
            _place_item(bx + 1, by + 1, "bedroll")

        # ── Boarding House ────────────────────────────────────────
        elif key == "boarding_house":
            # Front counter
            for ix in range(bx + 1, bx + bw // 2):
                _set(ix, by + 1, LocalTerrain.BAR_COUNTER)
            # Guest rooms
            rooms = min(4, (bw - 2) // 3)
            for i in range(rooms):
                rx = bx + 1 + i * 3
                _set(rx, by + 3, LocalTerrain.BED)
                if by + 5 < by + bh - 1:
                    _set(rx, by + 5, LocalTerrain.BED)
                _place_item(rx, by + 3, "bedroll")

        # ── School ────────────────────────────────────────────────
        elif key == "school":
            # Teacher desk at front
            _set(bx + bw // 2, by + 1, LocalTerrain.DESK)
            # Student desks in rows
            for row in range(min(4, bh - 4)):
                for col in range(min(3, (bw - 4) // 2)):
                    dx = bx + 2 + col * 3
                    dy = by + 3 + row
                    _set(dx, dy, LocalTerrain.DESK)
                    _set(dx + 1, dy, LocalTerrain.CHAIR)
            _place_item(bx + bw // 2, by + 1, "paper", 3)
            _place_item(bx + bw // 2 + 1, by + 1, "pencil")

        # ── Livery Stable ─────────────────────────────────────────
        elif key == "livery":
            # Stall dividers (fence terrain along middle)
            for iy in range(by + 2, by + bh - 2):
                _set(bx + bw // 3, iy, LocalTerrain.CELL_BARS)
                _set(bx + 2 * bw // 3, iy, LocalTerrain.CELL_BARS)
            # Feed barrels
            _set(bx + 1, by + bh - 2, LocalTerrain.BARREL_TILE)
            _set(bx + bw - 2, by + bh - 2, LocalTerrain.BARREL_TILE)
            _place_item(bx + 1, by + bh - 2, "rope_10ft", 2)

        # ── Lawyer / Barber / Telegraph / Newspaper / Assay ──────
        elif key in ("lawyer_office", "barber", "telegraph", "newspaper",
                     "assay_office"):
            _set(bx + 1, by + 1, LocalTerrain.DESK)
            _set(bx + 2, by + 1, LocalTerrain.CHAIR)
            if bw > 5:
                _set(bx + bw - 2, by + 1, LocalTerrain.SHELF)
            _set(bx + bw // 2, by + bh - 2, LocalTerrain.CHAIR)

        # ── Trading Post ──────────────────────────────────────────
        elif key == "trading_store":
            # Same as general store but bigger
            for iy in range(by + 1, by + bh - 1):
                _set(bx + 1, iy, LocalTerrain.SHELF)
                _set(bx + bw - 2, iy, LocalTerrain.SHELF)
            for ix in range(bx + 2, bx + bw - 2):
                _set(ix, by + 1, LocalTerrain.SHELF)
            counter_y = by + bh * 3 // 5
            for ix in range(bx + 2, bx + bw - 2):
                _set(ix, counter_y, LocalTerrain.BAR_COUNTER)
            _place_item(bx + 1, by + 2, "hardtack", 8)
            _place_item(bx + 1, by + 3, "salt", 5)
            _place_item(bx + 1, by + 4, "coffee_beans", 3)
            _place_item(bx + bw - 2, by + 2, "rope_10ft", 5)
            _place_item(bx + bw - 2, by + 3, "rifle_ball", 20)
            _place_item(bx + bw - 2, by + 4, "hunting_knife")
            _place_item(bx + 3, by + 1, "percussion_revolver")

        # ── Warehouse ─────────────────────────────────────────────
        elif key == "warehouse":
            # Rows of barrels
            for row in range(min(3, (bh - 2) // 2)):
                for col in range(min(5, (bw - 2) // 2)):
                    _set(bx + 1 + col * 2, by + 1 + row * 2, LocalTerrain.BARREL_TILE)

        # ── Dance Hall ────────────────────────────────────────────
        elif key == "dancehall":
            # Small bar in corner
            for ix in range(bx + 1, bx + 4):
                _set(ix, by + 1, LocalTerrain.BAR_COUNTER)
            # Tables along walls
            _set(bx + bw - 2, by + 2, LocalTerrain.TABLE)
            _set(bx + bw - 2, by + 4, LocalTerrain.TABLE)
            _set(bx + bw - 3, by + 2, LocalTerrain.CHAIR)
            _set(bx + bw - 3, by + 4, LocalTerrain.CHAIR)
            # Open floor for dancing
            _place_item(bx + 2, by + 1, "whiskey", 2)

        # ── Brothel ───────────────────────────────────────────────
        elif key == "brothel":
            # Bar in front
            for ix in range(bx + 1, bx + 4):
                _set(ix, by + 1, LocalTerrain.BAR_COUNTER)
            # Private rooms with beds
            rooms = min(4, (bw - 2) // 3)
            for i in range(rooms):
                rx = bx + 1 + i * 3
                _set(rx, by + 3, LocalTerrain.BED)
                if by + 5 < by + bh - 1:
                    _set(rx, by + 5, LocalTerrain.BED)
            _place_item(bx + 2, by + 1, "whiskey", 3)
            _place_item(bx + 4, by + 1, "tobacco")

        # ── Gunsmith ──────────────────────────────────────────────
        elif key == "gunsmith":
            # Display counter
            counter_y = by + bh // 2
            for ix in range(bx + 1, bx + bw - 1):
                _set(ix, counter_y, LocalTerrain.BAR_COUNTER)
            # Weapon racks (shelves) along back wall
            for ix in range(bx + 1, bx + bw - 1):
                _set(ix, by + 1, LocalTerrain.SHELF)
            _set(bx + 1, by + bh - 2, LocalTerrain.DESK)
            # Stock
            _place_item(bx + 2, by + 1, "percussion_rifle")
            _place_item(bx + 3, by + 1, "percussion_revolver")
            _place_item(bx + 4, by + 1, "derringer")
            _place_item(bx + 5, by + 1, "bowie_knife")
            _place_item(bx + 2, counter_y, "rifle_ball", 20)
            _place_item(bx + 4, counter_y, "revolver_ball", 20)
            _place_item(bx + 6, counter_y, "shotgun_shell", 10)

        # ── Undertaker ────────────────────────────────────────────
        elif key == "undertaker":
            # Coffin display (tables)
            for i in range(3):
                tx = bx + 1 + i * 2
                if tx < bx + bw - 1:
                    _set(tx, by + 1, LocalTerrain.TABLE)
            _set(bx + 1, by + bh - 2, LocalTerrain.DESK)
            _set(bx + bw - 2, by + 1, LocalTerrain.SHELF)

        # ── Bakery ────────────────────────────────────────────────
        elif key == "bakery":
            # Oven (stove) in back
            _set(bx + bw - 2, by + 1, LocalTerrain.STOVE)
            _set(bx + bw - 3, by + 1, LocalTerrain.STOVE)
            # Counter
            counter_y = by + bh // 2
            for ix in range(bx + 1, bx + bw - 1):
                _set(ix, counter_y, LocalTerrain.BAR_COUNTER)
            # Bread on counter
            _place_item(bx + 2, counter_y, "hardtack", 10)
            _place_item(bx + 4, counter_y, "hardtack", 10)

        # ── Butcher Shop ──────────────────────────────────────────
        elif key == "butcher_shop":
            # Chopping block (table)
            _set(bx + bw // 2, by + 1, LocalTerrain.TABLE)
            # Counter
            counter_y = by + bh // 2
            for ix in range(bx + 1, bx + bw - 1):
                _set(ix, counter_y, LocalTerrain.BAR_COUNTER)
            # Meat hooks (shelf)
            for ix in range(bx + 1, bx + bw - 1):
                _set(ix, by + 1, LocalTerrain.SHELF)
            _place_item(bx + 2, by + 1, "salt", 5)

        # ── Tailor ────────────────────────────────────────────────
        elif key == "tailor":
            _set(bx + 1, by + 1, LocalTerrain.DESK)  # sewing table
            _set(bx + 2, by + 1, LocalTerrain.CHAIR)
            # Fabric shelves
            for iy in range(by + 1, by + bh - 1):
                _set(bx + bw - 2, iy, LocalTerrain.SHELF)
            counter_y = by + bh // 2
            for ix in range(bx + 1, bx + bw - 2):
                _set(ix, counter_y, LocalTerrain.BAR_COUNTER)

        # ── Apothecary ────────────────────────────────────────────
        elif key == "apothecary":
            # Medicine shelves on all walls
            for iy in range(by + 1, by + bh - 1):
                _set(bx + 1, iy, LocalTerrain.SHELF)
                _set(bx + bw - 2, iy, LocalTerrain.SHELF)
            for ix in range(bx + 2, bx + bw - 2):
                _set(ix, by + 1, LocalTerrain.SHELF)
            counter_y = by + bh * 3 // 5
            for ix in range(bx + 2, bx + bw - 2):
                _set(ix, counter_y, LocalTerrain.BAR_COUNTER)
            _place_item(bx + 1, by + 2, "laudanum", 5)
            _place_item(bx + 1, by + 3, "whiskey", 3)
            _place_item(bx + bw - 2, by + 2, "bandage", 10)
            _place_item(bx + bw - 2, by + 3, "tobacco", 3)

        # ── Land Office ───────────────────────────────────────────
        elif key == "land_office":
            _set(bx + 1, by + 1, LocalTerrain.DESK)
            _set(bx + 3, by + 1, LocalTerrain.DESK)
            for iy in range(by + 1, by + bh - 1):
                _set(bx + bw - 2, iy, LocalTerrain.SHELF)  # records
            counter_y = by + bh // 2
            for ix in range(bx + 1, bx + bw - 1):
                _set(ix, counter_y, LocalTerrain.BAR_COUNTER)
            _place_item(bx + 1, by + 1, "paper", 5)
            _place_item(bx + 3, by + 1, "pencil")

        # ── Courthouse ────────────────────────────────────────────
        elif key == "courthouse":
            # Judge's bench at front
            for ix in range(bx + 3, bx + bw - 3):
                _set(ix, by + 1, LocalTerrain.DESK)
            _set(bx + bw // 2, by + 2, LocalTerrain.CHAIR)  # judge chair
            # Witness stand
            _set(bx + 2, by + 3, LocalTerrain.DESK)
            _set(bx + 2, by + 4, LocalTerrain.CHAIR)
            # Gallery seating
            for row in range(min(5, bh - 6)):
                for col in range(bw - 4):
                    _set(bx + 2 + col, by + 5 + row, LocalTerrain.CHAIR)
            # Railing
            for ix in range(bx + 1, bx + bw - 1):
                _set(ix, by + 4, LocalTerrain.BAR_COUNTER)

        # ── Opera House / Theater ─────────────────────────────────
        elif key == "theater":
            # Stage at front (table terrain)
            for ix in range(bx + 2, bx + bw - 2):
                _set(ix, by + 1, LocalTerrain.TABLE)
                _set(ix, by + 2, LocalTerrain.TABLE)
            # Audience seating
            for row in range(min(7, bh - 5)):
                for col in range(bw - 4):
                    _set(bx + 2 + col, by + 4 + row, LocalTerrain.CHAIR)

        # ── Lumber Mill ───────────────────────────────────────────
        elif key == "lumber_mill":
            # Saw table
            for ix in range(bx + 2, bx + bw - 2):
                _set(ix, by + bh // 2, LocalTerrain.TABLE)
            # Log storage (barrels)
            for i in range(4):
                _set(bx + 1 + i * 2, by + 1, LocalTerrain.BARREL_TILE)
            # Plank output
            _place_item(bx + bw - 2, by + bh - 2, "plank", 10)
            _place_item(bx + 1, by + 1, "log", 5)

        # ── Brewery ───────────────────────────────────────────────
        elif key == "brewery":
            # Vats (barrels)
            for i in range(4):
                _set(bx + 1 + i * 2, by + 1, LocalTerrain.BARREL_TILE)
                _set(bx + 1 + i * 2, by + 2, LocalTerrain.BARREL_TILE)
            _set(bx + bw - 2, by + bh - 2, LocalTerrain.STOVE)
            _place_item(bx + bw - 2, by + 1, "whiskey", 10)

        # ── Bathhouse ─────────────────────────────────────────────
        elif key == "bathhouse":
            # Tubs (beds repurposed as tubs)
            for i in range(3):
                _set(bx + 1 + i * 2, by + 2, LocalTerrain.BED)
            _set(bx + bw - 2, by + 1, LocalTerrain.STOVE)  # water heater
            _set(bx + 1, by + bh - 2, LocalTerrain.SHELF)  # towels

        # ── Freight Office ────────────────────────────────────────
        elif key == "freight_office":
            _set(bx + 1, by + 1, LocalTerrain.DESK)
            _set(bx + 2, by + 1, LocalTerrain.CHAIR)
            # Crates/barrels
            for i in range(3):
                _set(bx + bw - 2, by + 1 + i, LocalTerrain.BARREL_TILE)
            _set(bx + bw // 2, by + bh // 2, LocalTerrain.TABLE)  # scale

        # ── Fur Trading Post ───────────────────────────────────────
        elif key == "fur_post":
            # Pelt display shelves
            for iy in range(by + 1, by + bh - 1):
                _set(bx + 1, iy, LocalTerrain.SHELF)
                _set(bx + bw - 2, iy, LocalTerrain.SHELF)
            for ix in range(bx + 2, bx + bw - 2):
                _set(ix, by + 1, LocalTerrain.SHELF)
            # Trade counter
            counter_y = by + bh * 3 // 5
            for ix in range(bx + 2, bx + bw - 2):
                _set(ix, counter_y, LocalTerrain.BAR_COUNTER)
            # Barrels for storing pelts
            _set(bx + bw - 2, by + bh - 2, LocalTerrain.BARREL_TILE)
            _set(bx + bw - 3, by + bh - 2, LocalTerrain.BARREL_TILE)
            # Stock
            _place_item(bx + 1, by + 2, "steel_trap", 3)
            _place_item(bx + 1, by + 3, "castoreum", 2)
            _place_item(bx + 1, by + 4, "skinning_knife")
            _place_item(bx + bw - 2, by + 2, "rope_10ft", 5)
            _place_item(bx + bw - 2, by + 3, "beaver_pelt")
            _place_item(bx + bw - 2, by + 4, "wolf_pelt")

        # ── Laundry / Cobbler ─────────────────────────────────────
        elif key in ("laundry", "cobbler"):
            _set(bx + 1, by + 1, LocalTerrain.TABLE)
            _set(bx + 2, by + 1, LocalTerrain.CHAIR)
            _set(bx + bw - 2, by + 1, LocalTerrain.SHELF)
            _set(bx + bw - 2, by + bh - 2, LocalTerrain.BARREL_TILE)


# ============================================================================
#  CONVENIENCE: generate town for a world location
# ============================================================================

def generate_town_layout(local_map, world_map, wx: int, wy: int
                          ) -> Optional[SettlementLayout]:
    """
    Check if (wx, wy) has a named location; if so, generate and apply
    the town layout.  Returns the layout or None.

    Call this after base terrain generation in LocalMap._generate() or
    in Engine._ensure_local().
    """
    loc = world_map.get_location_at(wx, wy)
    if not loc:
        return None

    stype = classify_settlement(loc.location_type, loc.population)
    seed = world_map.seed + wx * 997 + wy * 100003
    gen = TownGenerator(seed=seed)
    return gen.generate(local_map, stype, loc.name)
