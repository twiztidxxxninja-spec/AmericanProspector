"""
src/construction.py

Building, construction, and zone system — Dwarf Fortress / Rimworld style.

Key architecture:
    WALLS ARE EDGES, NOT TILES.  A wall on the west side of a tile means
    you can stand in the tile but cannot cross the west boundary.  The tile
    itself remains usable floor space.

    Players design a layout (place wall edges, floors, doors tile-by-tile),
    then commit the design to a build queue.  Player or NPCs work through
    the queue, each segment taking time and materials.

Data structures:
    WallGrid        — sparse edge-based wall/door/window storage
    FloorOverlay    — player-placed floor tiles over natural terrain
    DesignatedZone  — rectangular zone with type (kitchen, workshop, etc.)
    BuildOrder      — a single construction task (wall segment, floor tile, etc.)
    BuildQueue      — ordered list of all pending build orders
    StructureBlueprint — template for standalone equipment (sluice, rocker, etc.)
    PlacedStructure — a built standalone structure on the map

Integration:
    local_map.py    — movement checks call wall_grid.can_pass(from, to)
    engine.py       — player movement uses can_pass before allowing step
    renderer.py     — tiles with edges get visual indicators
    companions.py   — NPC tasks use zones to find work locations
    FOV             — edge walls block line of sight directionally
"""

import json
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.local_map import LocalMap
    from src.llm_client import LLMClient


# ============================================================================
#  EDGE TYPES (walls, doors, windows, fences)
# ============================================================================

class Edge:
    NONE       = 0
    WOOD_WALL  = 1
    STONE_WALL = 2
    DOOR       = 3     # passable, doesn't block LOS
    WINDOW     = 4     # impassable, doesn't block LOS
    FENCE      = 5     # passable (climbable), blocks LOS partially
    IRON_BARS  = 6     # impassable, doesn't block LOS (jail)
    CANVAS     = 7     # impassable, blocks LOS (tent wall)


EDGE_LABELS = {
    Edge.NONE:       "",
    Edge.WOOD_WALL:  "Wood Wall",
    Edge.STONE_WALL: "Stone Wall",
    Edge.DOOR:       "Door",
    Edge.WINDOW:     "Window",
    Edge.FENCE:      "Split-Rail Fence",
    Edge.IRON_BARS:  "Iron Bars",
    Edge.CANVAS:     "Canvas Wall",
}

# Which edges block movement
EDGE_BLOCKS_MOVE = {
    Edge.NONE: False, Edge.WOOD_WALL: True, Edge.STONE_WALL: True,
    Edge.DOOR: False, Edge.WINDOW: True, Edge.FENCE: False,
    Edge.IRON_BARS: True, Edge.CANVAS: True,
}

# Which edges block line of sight
EDGE_BLOCKS_LOS = {
    Edge.NONE: False, Edge.WOOD_WALL: True, Edge.STONE_WALL: True,
    Edge.DOOR: False, Edge.WINDOW: False, Edge.FENCE: False,
    Edge.IRON_BARS: False, Edge.CANVAS: True,
}

# Rendering hints: (char, fg_color) drawn on the tile edge
EDGE_GLYPH = {
    Edge.WOOD_WALL:  ("#", (130, 100, 55)),
    Edge.STONE_WALL: ("#", (150, 148, 140)),
    Edge.DOOR:       ("+", (170, 130, 70)),
    Edge.WINDOW:     ("=", (140, 160, 180)),
    Edge.FENCE:      ("-", (130, 105, 60)),
    Edge.IRON_BARS:  ("|", (160, 160, 170)),
    Edge.CANVAS:     ("/", (185, 175, 150)),
}


# ============================================================================
#  DIRECTIONS
# ============================================================================

DIR_N = "N"
DIR_S = "S"
DIR_E = "E"
DIR_W = "W"

ALL_DIRS = [DIR_N, DIR_S, DIR_E, DIR_W]

OPPOSITE = {DIR_N: DIR_S, DIR_S: DIR_N, DIR_E: DIR_W, DIR_W: DIR_E}

# Movement delta for each direction
DIR_DELTA = {DIR_N: (0, -1), DIR_S: (0, 1), DIR_E: (1, 0), DIR_W: (-1, 0)}

def direction_between(from_x: int, from_y: int,
                       to_x: int, to_y: int) -> Optional[str]:
    """Return direction from (from) to (to), or None if not adjacent."""
    dx, dy = to_x - from_x, to_y - from_y
    for d, (ddx, ddy) in DIR_DELTA.items():
        if dx == ddx and dy == ddy:
            return d
    return None


# ============================================================================
#  WALL GRID — sparse edge-based wall storage
# ============================================================================

class WallGrid:
    """
    Stores wall segments on tile edges.  Sparse dict — only tiles with
    walls consume memory.  A wall on the east edge of tile (3,5) is
    automatically mirrored as a wall on the west edge of tile (4,5).

    Movement integration:
        In engine.py or local_map.py, before allowing a step:
            if not wall_grid.can_pass(old_x, old_y, new_x, new_y):
                return  # blocked by wall

    FOV integration:
        When checking LOS between adjacent tiles:
            if wall_grid.blocks_sight(from_x, from_y, to_x, to_y):
                # edge wall blocks this sight line
    """

    def __init__(self):
        # Keyed by (x, y, direction) for surface walls (backward compat)
        # and (x, y, z, direction) for z-specific walls
        self._edges: Dict[Tuple, int] = {}

    def set_edge(self, x: int, y: int, direction: str,
                  edge_type: int, z: int = None) -> None:
        """
        Place a wall/door/window on the edge of tile (x,y) in direction.
        Automatically mirrors on the adjacent tile.
        z=None stores as (x,y,dir); z=int stores as (x,y,z,dir).
        """
        if z is not None:
            self._edges[(x, y, z, direction)] = edge_type
            dx, dy = DIR_DELTA[direction]
            opp = OPPOSITE[direction]
            self._edges[(x + dx, y + dy, z, opp)] = edge_type
        else:
            self._edges[(x, y, direction)] = edge_type
            dx, dy = DIR_DELTA[direction]
            opp = OPPOSITE[direction]
            self._edges[(x + dx, y + dy, opp)] = edge_type

    def remove_edge(self, x: int, y: int, direction: str,
                     z: int = None) -> None:
        if z is not None:
            self._edges.pop((x, y, z, direction), None)
            dx, dy = DIR_DELTA[direction]
            opp = OPPOSITE[direction]
            self._edges.pop((x + dx, y + dy, z, opp), None)
        else:
            self._edges.pop((x, y, direction), None)
            dx, dy = DIR_DELTA[direction]
            opp = OPPOSITE[direction]
            self._edges.pop((x + dx, y + dy, opp), None)

    def get_edge(self, x: int, y: int, direction: str,
                  z: int = None) -> int:
        """Get edge. Checks z-specific key first, then surface key."""
        if z is not None:
            val = self._edges.get((x, y, z, direction), None)
            if val is not None:
                return val
        return self._edges.get((x, y, direction), Edge.NONE)

    def edges_at(self, x: int, y: int, z: int = None) -> Dict[str, int]:
        """Return all non-NONE edges at tile (x,y) at z-level."""
        result = {}
        for d in ALL_DIRS:
            e = self.get_edge(x, y, d, z)
            if e != Edge.NONE:
                result[d] = e
        return result

    def has_any_edge(self, x: int, y: int) -> bool:
        return any(self.get_edge(x, y, d) != Edge.NONE for d in ALL_DIRS)

    # ── Movement check ─────────────────────────────────────────────────

    def can_pass(self, from_x: int, from_y: int,
                  to_x: int, to_y: int, z: int = None) -> bool:
        """
        Can an entity move from (from) to (to)?
        Returns False if a blocking edge is in the way.
        """
        d = direction_between(from_x, from_y, to_x, to_y)
        if d is None:
            return True
        edge = self.get_edge(from_x, from_y, d, z)
        return not EDGE_BLOCKS_MOVE.get(edge, False)

    # ── LOS check ──────────────────────────────────────────────────────

    def blocks_sight(self, from_x: int, from_y: int,
                      to_x: int, to_y: int, z: int = None) -> bool:
        """Does an edge wall block line of sight between adjacent tiles?"""
        d = direction_between(from_x, from_y, to_x, to_y)
        if d is None:
            return False
        edge = self.get_edge(from_x, from_y, d, z)
        return EDGE_BLOCKS_LOS.get(edge, False)

    # ── Enclosed area detection ────────────────────────────────────────

    def is_enclosed(self, x: int, y: int, max_area: int = 100) -> bool:
        """
        Flood-fill from (x,y) to check if the area is fully enclosed
        by walls.  Returns True if enclosed within max_area tiles.
        Used to auto-detect rooms for zone suggestions.
        """
        visited = set()
        stack = [(x, y)]
        while stack:
            if len(visited) > max_area:
                return False  # too big, probably not enclosed
            cx, cy = stack.pop()
            if (cx, cy) in visited:
                continue
            visited.add((cx, cy))
            for d in ALL_DIRS:
                if EDGE_BLOCKS_MOVE.get(self.get_edge(cx, cy, d), False):
                    continue  # wall blocks this direction
                dx, dy = DIR_DELTA[d]
                nx, ny = cx + dx, cy + dy
                if (nx, ny) not in visited:
                    stack.append((nx, ny))
        return True  # flood fill was contained

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> List:
        """Serialize to list of [x, y, dir, type] or [x, y, z, dir, type] entries."""
        seen = set()
        result = []
        for key, etype in self._edges.items():
            if etype == Edge.NONE:
                continue
            if len(key) == 3:
                x, y, d = key
                dx, dy = DIR_DELTA[d]
                opp_key = (x + dx, y + dy, OPPOSITE[d])
                if opp_key in seen:
                    continue
                seen.add(key)
                result.append([x, y, d, etype])
            elif len(key) == 4:
                x, y, z, d = key
                dx, dy = DIR_DELTA[d]
                opp_key = (x + dx, y + dy, z, OPPOSITE[d])
                if opp_key in seen:
                    continue
                seen.add(key)
                result.append([x, y, z, d, etype])
        return result

    @classmethod
    def from_dict(cls, data: List) -> "WallGrid":
        grid = cls()
        for entry in data:
            if len(entry) == 4:
                x, y, d, etype = entry
                grid.set_edge(x, y, d, etype)
            elif len(entry) == 5:
                x, y, z, d, etype = entry
                grid.set_edge(x, y, d, etype, z=z)
        return grid


# ============================================================================
#  FLOOR OVERLAY — player-placed floors over natural terrain
# ============================================================================

class FloorType:
    NONE       = 0
    DIRT_PACK  = 1     # packed dirt (natural ground)
    HAY        = 2     # hay/straw floor (stable, animal pen)
    WOOD_PLANK = 101   # matches town_gen WOOD_FLOOR
    STONE_FLAG = 103   # matches town_gen STONE_WALL (reused as stone floor)


class FloorOverlay:
    """
    Sparse overlay of player-placed floor tiles.
    When rendering, if a floor exists here, draw it instead of natural terrain.
    """

    def __init__(self):
        self._floors: Dict[Tuple[int, int], int] = {}

    def set_floor(self, x: int, y: int, floor_type: int) -> None:
        self._floors[(x, y)] = floor_type

    def get_floor(self, x: int, y: int) -> int:
        return self._floors.get((x, y), FloorType.NONE)

    def has_floor(self, x: int, y: int) -> bool:
        return (x, y) in self._floors

    def remove(self, x: int, y: int) -> None:
        self._floors.pop((x, y), None)

    def all_floors(self) -> Dict[Tuple[int, int], int]:
        return dict(self._floors)

    def to_dict(self) -> List:
        return [[x, y, ft] for (x, y), ft in self._floors.items()]

    @classmethod
    def from_dict(cls, data: List) -> "FloorOverlay":
        overlay = cls()
        for entry in data:
            x, y, ft = entry
            overlay._floors[(x, y)] = ft
        return overlay


# ============================================================================
#  ZONE DESIGNATION
# ============================================================================

class ZoneType:
    KITCHEN      = "kitchen"
    WORKSHOP     = "workshop"
    SLEEPING     = "sleeping"
    STORAGE      = "storage"
    CAMPSITE     = "campsite"
    CLEANING     = "cleaning"
    MINING       = "mining"
    CORRAL       = "corral"
    SHOP_FLOOR   = "shop"
    MEETING      = "meeting"
    GUARD_POST   = "guard"
    DINING       = "dining"
    JAIL_CELL    = "jail"


ZONE_LABELS: Dict[str, str] = {
    ZoneType.KITCHEN:    "Kitchen",
    ZoneType.WORKSHOP:   "Workshop",
    ZoneType.SLEEPING:   "Sleeping Area",
    ZoneType.STORAGE:    "Storage",
    ZoneType.CAMPSITE:   "Campsite",
    ZoneType.CLEANING:   "Cleaning Station",
    ZoneType.MINING:     "Mining Area",
    ZoneType.CORRAL:     "Corral / Pen",
    ZoneType.SHOP_FLOOR: "Shop Floor",
    ZoneType.MEETING:    "Meeting Area",
    ZoneType.GUARD_POST: "Guard Post",
    ZoneType.DINING:     "Dining Area",
    ZoneType.JAIL_CELL:  "Jail Cell",
}

ZONE_TASK_MAP: Dict[str, List[str]] = {
    ZoneType.KITCHEN:    ["cook_food"],
    ZoneType.WORKSHOP:   ["repair_equip", "build_cont"],
    ZoneType.SLEEPING:   ["rest"],
    ZoneType.STORAGE:    ["haul_supplies", "haul_ore"],
    ZoneType.CAMPSITE:   ["tend_fire", "set_camp", "cook_food"],
    ZoneType.CLEANING:   ["cook_food"],
    ZoneType.MINING:     ["prospect_pan", "dig_test_pit"],
    ZoneType.CORRAL:     [],
    ZoneType.SHOP_FLOOR: ["trade_town"],
    ZoneType.GUARD_POST: ["guard_camp"],
}


@dataclass
class DesignatedZone:
    """A rectangular zone on the local map."""
    id: int
    zone_type: str
    x: int
    y: int
    width: int
    height: int
    label: str = ""

    def contains(self, tx: int, ty: int) -> bool:
        return self.x <= tx < self.x + self.width and self.y <= ty < self.y + self.height

    @property
    def center(self) -> Tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


# ============================================================================
#  BUILD ORDER — a single construction task
# ============================================================================

@dataclass
class BuildOrder:
    """One unit of work in the construction queue."""
    id: int
    order_type: str         # "wall"|"floor"|"door"|"window"|"fence"|"equipment"
    x: int
    y: int
    direction: str          # DIR_N/S/E/W for edges, "" for tile-based
    target_type: int        # Edge type for walls, floor type for floors
    material_name: str      # "Log", "Plank", "Stone" — what's consumed
    material_qty: int       # how many units
    build_minutes: int      # time to build this one segment
    progress: float = 0.0   # 0-100
    assigned_npc: str = ""  # NPC id working on this, "" = player

    @property
    def complete(self) -> bool:
        return self.progress >= 100.0


# Material costs per edge/floor type
EDGE_MATERIALS: Dict[int, Tuple[str, int, int]] = {
    # edge_type → (material_name, quantity, build_minutes)
    Edge.WOOD_WALL:  ("Log",   1,  8),
    Edge.STONE_WALL: ("Stone", 2, 15),
    Edge.DOOR:       ("Plank", 2, 12),
    Edge.WINDOW:     ("Plank", 1, 10),
    Edge.FENCE:      ("Log",   1,  5),
    Edge.IRON_BARS:  ("Iron Bar", 1, 20),
    Edge.CANVAS:     ("Canvas", 1, 3),
}

FLOOR_MATERIALS: Dict[int, Tuple[str, int, int]] = {
    FloorType.WOOD_PLANK: ("Plank", 1, 5),
    FloorType.STONE_FLAG: ("Stone", 1, 8),
}


# ============================================================================
#  BUILD QUEUE
# ============================================================================

class BuildQueue:
    """
    Ordered list of construction tasks.
    Player designs a layout → build orders are created → worked through
    one at a time by player or assigned NPCs.
    """

    def __init__(self):
        self.orders: List[BuildOrder] = []
        self._counter = 0

    def _next_id(self) -> int:
        self._counter += 1
        return self._counter

    # ── Add orders ─────────────────────────────────────────────────────

    def add_wall(self, x: int, y: int, direction: str,
                  edge_type: int = Edge.WOOD_WALL) -> BuildOrder:
        """Queue a wall segment to be built."""
        mat_name, mat_qty, mins = EDGE_MATERIALS.get(
            edge_type, ("Log", 1, 10))
        order = BuildOrder(
            id=self._next_id(), order_type="wall",
            x=x, y=y, direction=direction, target_type=edge_type,
            material_name=mat_name, material_qty=mat_qty,
            build_minutes=mins,
        )
        self.orders.append(order)
        return order

    def add_floor(self, x: int, y: int,
                   floor_type: int = FloorType.WOOD_PLANK) -> BuildOrder:
        mat_name, mat_qty, mins = FLOOR_MATERIALS.get(
            floor_type, ("Plank", 1, 5))
        order = BuildOrder(
            id=self._next_id(), order_type="floor",
            x=x, y=y, direction="", target_type=floor_type,
            material_name=mat_name, material_qty=mat_qty,
            build_minutes=mins,
        )
        self.orders.append(order)
        return order

    def add_door(self, x: int, y: int, direction: str) -> BuildOrder:
        return self.add_wall(x, y, direction, Edge.DOOR)

    def add_window(self, x: int, y: int, direction: str) -> BuildOrder:
        return self.add_wall(x, y, direction, Edge.WINDOW)

    def add_fence(self, x: int, y: int, direction: str) -> BuildOrder:
        return self.add_wall(x, y, direction, Edge.FENCE)

    # ── Batch helpers ──────────────────────────────────────────────────

    def add_room(self, x: int, y: int, w: int, h: int,
                  wall_type: int = Edge.WOOD_WALL,
                  floor_type: int = FloorType.WOOD_PLANK,
                  door_dir: str = DIR_S) -> List[BuildOrder]:
        """
        Queue a full rectangular room: walls on all edges, floor inside,
        one door on the specified side.
        """
        orders = []

        # North and south walls
        for dx in range(w):
            orders.append(self.add_wall(x + dx, y, DIR_N, wall_type))
            orders.append(self.add_wall(x + dx, y + h - 1, DIR_S, wall_type))

        # East and west walls
        for dy in range(h):
            orders.append(self.add_wall(x, y + dy, DIR_W, wall_type))
            orders.append(self.add_wall(x + w - 1, y + dy, DIR_E, wall_type))

        # Floor
        for dy in range(h):
            for dx in range(w):
                if floor_type:
                    orders.append(self.add_floor(x + dx, y + dy, floor_type))

        # Door (replace one wall segment)
        mid = w // 2 if door_dir in (DIR_N, DIR_S) else h // 2
        if door_dir == DIR_S:
            for o in self.orders:
                if o.x == x + mid and o.y == y + h - 1 and o.direction == DIR_S:
                    o.target_type = Edge.DOOR
                    o.order_type = "door"
                    o.material_name, o.material_qty, o.build_minutes = EDGE_MATERIALS[Edge.DOOR]
                    break
        elif door_dir == DIR_N:
            for o in self.orders:
                if o.x == x + mid and o.y == y and o.direction == DIR_N:
                    o.target_type = Edge.DOOR
                    o.order_type = "door"
                    o.material_name, o.material_qty, o.build_minutes = EDGE_MATERIALS[Edge.DOOR]
                    break

        return orders

    # ── Query ──────────────────────────────────────────────────────────

    def pending(self) -> List[BuildOrder]:
        return [o for o in self.orders if not o.complete]

    def next_order(self) -> Optional[BuildOrder]:
        for o in self.orders:
            if not o.complete:
                return o
        return None

    def total_materials_needed(self) -> Dict[str, int]:
        """Sum materials for all incomplete orders."""
        totals: Dict[str, int] = {}
        for o in self.orders:
            if not o.complete:
                totals[o.material_name] = totals.get(o.material_name, 0) + o.material_qty
        return totals

    def total_time_remaining(self) -> int:
        return sum(int(o.build_minutes * (1.0 - o.progress / 100.0))
                   for o in self.orders if not o.complete)

    def clear_completed(self) -> None:
        self.orders = [o for o in self.orders if not o.complete]

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> Dict:
        return {
            "counter": self._counter,
            "orders": [
                {"id": o.id, "type": o.order_type, "x": o.x, "y": o.y,
                 "dir": o.direction, "target": o.target_type,
                 "mat": o.material_name, "qty": o.material_qty,
                 "mins": o.build_minutes, "progress": o.progress,
                 "npc": o.assigned_npc}
                for o in self.orders
            ],
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "BuildQueue":
        q = cls()
        q._counter = d.get("counter", 0)
        for od in d.get("orders", []):
            q.orders.append(BuildOrder(
                id=od["id"], order_type=od["type"], x=od["x"], y=od["y"],
                direction=od.get("dir", ""), target_type=od.get("target", 0),
                material_name=od.get("mat", "Log"), material_qty=od.get("qty", 1),
                build_minutes=od.get("mins", 10), progress=od.get("progress", 0),
                assigned_npc=od.get("npc", ""),
            ))
        return q


# ============================================================================
#  STANDALONE EQUIPMENT BLUEPRINTS
# ============================================================================
# These are single-tile or multi-tile objects that aren't edge-based walls.
# Sluice boxes, rocker boxes, campfires, drying racks, etc.

@dataclass
class EquipmentBlueprint:
    key: str
    name: str
    width: int
    height: int
    materials: List[Tuple[str, int]]   # [(item_name, quantity), ...]
    build_minutes: int
    skill: str
    difficulty: int
    description: str = ""
    functional_tags: List[str] = field(default_factory=list)
    glyph: str = "*"
    fg_color: Tuple[int, int, int] = (160, 130, 80)
    source: str = "builtin"
    portable: bool = False  # can player pick this up and carry it?
    year_available: int = 0  # 0 = always available; otherwise earliest year
    shelter_quality: float = 0.0  # 0-1: lean-to 0.3, tent 0.5, cabin 0.8


EQUIPMENT_BLUEPRINTS: Dict[str, EquipmentBlueprint] = {}

def _eq(key, name, w, h, mats, mins, skill, diff, desc="", tags=None,
        glyph="*", fg=(160, 130, 80), portable=False, year_available=0):
    EQUIPMENT_BLUEPRINTS[key] = EquipmentBlueprint(
        key=key, name=name, width=w, height=h,
        materials=mats, build_minutes=mins, skill=skill, difficulty=diff,
        description=desc, functional_tags=tags or [],
        glyph=glyph, fg_color=fg, portable=portable,
        year_available=year_available,
    )

_eq("campfire", "Campfire", 1, 1,
    [("Log", 2)], 15, "survival", 3,
    "A campfire ring.", ["cook", "warmth", "light"],
    glyph="*", fg=(200, 90, 30))
_eq("lean_to", "Lean-To", 2, 1,
    [("Log", 3)], 45, "survival", 5,
    "Crude shelter from rain.", ["shelter"])
_eq("drying_rack", "Drying Rack", 2, 1,
    [("Log", 2), ("Rope (10 ft)", 1)], 30, "survival", 4,
    "Frame for drying meat/fish.", ["preserve_food"],
    portable=True)
_eq("fleshing_beam", "Fleshing Beam", 2, 1,
    [("Log", 2)], 20, "survival", 3,
    "A smooth log propped at an angle for scraping hides and pelts.",
    ["flesh_hide"],
    glyph="/", fg=(140, 100, 55), portable=True)
_eq("stretching_board", "Hide & Pelt Frame", 2, 1,
    [("Log", 2), ("Rope (10 ft)", 1)], 25, "survival", 4,
    "A frame for stretching pelts and hides to dry. Works for both fur "
    "trade pelts and leather tanning. Takes a day per hide.",
    ["stretch_hide"],
    glyph="H", fg=(130, 95, 50), portable=True)
_eq("rocker_box", "Rocker Box", 2, 1,
    [("Plank", 4), ("Nails", 1), ("Rope (10 ft)", 1)], 120, "engineering", 8,
    "A cradle rocker for washing gold.", ["pan_gold", "process_ore"],
    year_available=1810)
_eq("sluice_box", "Sluice Box", 3, 1,
    [("Plank", 6), ("Nails", 1)], 180, "engineering", 10,
    "Long trough with riffles for catching gold.", ["pan_gold", "process_ore"],
    year_available=1800)
_eq("long_tom", "Long Tom", 4, 1,
    [("Plank", 10), ("Nails", 1), ("Iron Bar", 1)], 300, "engineering", 12,
    "Extended sluice with hopper.", ["pan_gold", "process_ore"],
    year_available=1840)
_eq("arrastra", "Arrastra", 3, 3,
    [("Stone", 8), ("Log", 4), ("Rope (10 ft)", 1)], 480, "engineering", 14,
    "Stone-drag ore mill.", ["crush_ore"],
    year_available=1820)
_eq("ore_bin", "Ore Bin", 2, 2,
    [("Plank", 6), ("Nails", 1)], 90, "engineering", 6,
    "Timber bin for ore.", ["store"])
_eq("windlass", "Windlass", 1, 1,
    [("Log", 2), ("Rope (10 ft)", 1), ("Nails", 1)], 60, "engineering", 8,
    "Crank and rope for hoisting.", ["hoist"])
_eq("well", "Dug Well", 1, 1,
    [("Log", 4), ("Rope (10 ft)", 1), ("Stone", 6)], 480, "engineering", 12,
    "Lined well with windlass.", ["water_source"],
    glyph="O", fg=(100, 100, 110))
_eq("hitching_rail", "Hitching Rail", 2, 1,
    [("Log", 2)], 20, "survival", 3,
    "Rail for tying animals.", ["animal_hold"],
    portable=True)
_eq("water_channel", "Water Channel", 5, 1,
    [("Plank", 8)], 180, "engineering", 9,
    "Wooden flume to divert water.", ["water_divert"])
_eq("stone_fireplace", "Stone Fireplace", 1, 1,
    [("Stone", 12)], 360, "engineering", 11,
    "Proper fireplace and chimney.", ["warmth", "cook"],
    glyph="0", fg=(140, 100, 60))
# Shelter quality assignments
EQUIPMENT_BLUEPRINTS["lean_to"].shelter_quality = 0.3      # crude, blocks rain
EQUIPMENT_BLUEPRINTS["stone_fireplace"].shelter_quality = 0.1  # warmth only

# Vertical movement structures
_eq("stairs_down", "Stairs Down", 1, 1,
    [("Plank", 4), ("Nails", 1)], 60, "engineering", 7,
    "Wooden stairs descending one z-level.", ["z_down"],
    glyph=">", fg=(160, 140, 100))
_eq("stairs_up", "Stairs Up", 1, 1,
    [("Plank", 4), ("Nails", 1)], 60, "engineering", 7,
    "Wooden stairs ascending one z-level.", ["z_up"],
    glyph="<", fg=(160, 140, 100))
_eq("ladder_down", "Ladder Down", 1, 1,
    [("Log", 2), ("Rope (10 ft)", 1)], 30, "survival", 5,
    "A crude ladder descending one z-level.", ["z_down"],
    glyph="H", fg=(130, 100, 55))
_eq("ladder_up", "Ladder Up", 1, 1,
    [("Log", 2), ("Rope (10 ft)", 1)], 30, "survival", 5,
    "A crude ladder ascending one z-level.", ["z_up"],
    glyph="H", fg=(130, 100, 55))
# Brewing & Distilling
_eq("copper_still", "Copper Still", 2, 2,
    [("Copper Sheet", 3), ("Plank", 4), ("Rope (10 ft)", 1)], 480, "engineering", 14,
    "A copper pot still for distilling spirits. Copper conducts heat evenly "
    "and doesn't taint the flavor.",
    ["distill", "brew"],
    glyph="U", fg=(200, 140, 60))
_eq("mash_barrel", "Mash Barrel", 1, 1,
    [("Plank", 6), ("Nails", 1)], 120, "engineering", 10,
    "A wooden barrel for fermenting grain mash. First step in whiskey-making.",
    ["ferment"],
    glyph="O", fg=(140, 100, 50))
_eq("rain_barrel", "Rain Barrel", 1, 1,
    [("Plank", 4), ("Nails", 1)], 60, "engineering", 7,
    "Collects rainwater. Clean water source without a stream.",
    ["water_source"],
    glyph="O", fg=(80, 100, 160))


def _keyword_match_equipment(description: str) -> Optional[EquipmentBlueprint]:
    """Match a custom equipment description to closest existing blueprint."""
    low = description.lower()
    _EQUIP_KEYWORDS = {
        "campfire":      {"fire", "campfire", "flame", "cook fire", "hearth"},
        "lean_to":       {"lean-to", "lean to", "shelter", "shade", "awning"},
        "drying_rack":   {"drying", "rack", "jerky", "dry meat", "smoke"},
        "rocker_box":    {"rocker", "cradle", "gold wash"},
        "sluice_box":    {"sluice", "riffle", "gold catch"},
        "long_tom":      {"long tom", "hopper"},
        "arrastra":      {"arrastra", "ore mill", "crush", "grind"},
        "ore_bin":       {"ore bin", "ore storage", "bin", "stockpile"},
        "windlass":      {"windlass", "hoist", "winch", "crank", "pulley"},
        "well":          {"well", "water hole", "dig well"},
        "hitching_rail": {"hitching", "hitch", "tie post", "rail"},
        "water_channel": {"channel", "flume", "aqueduct", "ditch", "divert water"},
        "stone_fireplace": {"fireplace", "chimney", "stone fire", "hearth stone"},
        "stairs_down":   {"stairs down", "staircase down", "descend"},
        "stairs_up":     {"stairs up", "staircase up", "ascend"},
        "ladder_down":   {"ladder down"},
        "ladder_up":     {"ladder up", "ladder"},
    }
    best_key = None
    best_score = 0
    for bp_key, keywords in _EQUIP_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in low)
        if score > best_score:
            best_score = score
            best_key = bp_key

    if best_key and best_score > 0:
        base = EQUIPMENT_BLUEPRINTS.get(best_key)
        if base:
            custom_key = f"custom_{description.lower().replace(' ', '_')[:20]}"
            return EquipmentBlueprint(
                key=custom_key, name=description[:30],
                width=base.width, height=base.height,
                materials=base.materials, build_minutes=base.build_minutes,
                skill=base.skill, difficulty=base.difficulty,
                description=f"Custom: {description}.",
                functional_tags=base.functional_tags,
                glyph=base.glyph, fg_color=base.fg_color,
                source="keyword",
            )
    return None


# ============================================================================
#  PLACED EQUIPMENT (on-map instance)
# ============================================================================

@dataclass
class PlacedEquipment:
    id: int
    blueprint_key: str
    name: str
    x: int
    y: int
    width: int
    height: int
    condition: float = 100.0
    progress: float = 100.0     # <100 = under construction
    functional_tags: List[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.progress >= 100.0

    @property
    def functional(self) -> bool:
        return self.complete and self.condition > 10.0


# ============================================================================
#  CONSTRUCTION MANAGER
# ============================================================================

class ConstructionManager:
    """
    Central manager for all construction, walls, floors, zones, and equipment.
    Each local map tile gets its own WallGrid, FloorOverlay, zones, and equipment.
    """

    def __init__(self, llm: Optional["LLMClient"] = None):
        self.llm = llm
        self._custom_equipment: Dict[str, EquipmentBlueprint] = {}

    # ── Wall / Floor placement (immediate, for design commit) ──────────

    def place_wall(self, wall_grid: WallGrid, x: int, y: int,
                    direction: str, edge_type: int) -> None:
        wall_grid.set_edge(x, y, direction, edge_type)

    def place_floor(self, floor_overlay: FloorOverlay, x: int, y: int,
                     floor_type: int) -> None:
        floor_overlay.set_floor(x, y, floor_type)

    # ── Build order execution ──────────────────────────────────────────

    def work_on_order(self, order: BuildOrder, minutes: int,
                       skill_level: int,
                       wall_grid: WallGrid,
                       floor_overlay: FloorOverlay,
                       inventory: list,
                       local_map=None) -> Tuple[bool, str]:
        """
        Work on a build order for `minutes`.
        Consumes materials when order starts (progress goes from 0).
        Places the result when order completes.
        Returns (completed, message).
        """
        if order.complete:
            return True, "Already finished."

        # Consume materials on first work (progress == 0)
        if order.progress == 0:
            consumed = self._try_consume(order.material_name,
                                          order.material_qty, inventory)
            if not consumed:
                return False, f"Need {order.material_qty}x {order.material_name}."

        # Advance progress
        rate = 1.0 + skill_level * 0.08
        pct_per_min = (100.0 / order.build_minutes) * rate
        order.progress = min(100.0, order.progress + pct_per_min * minutes)

        if order.complete:
            # Place the result
            if order.order_type in ("wall", "door", "window", "fence"):
                wall_grid.set_edge(order.x, order.y, order.direction,
                                    order.target_type)
                label = EDGE_LABELS.get(order.target_type, "segment")
                return True, f"{label} built at ({order.x},{order.y}) {order.direction}."
            elif order.order_type == "floor":
                floor_overlay.set_floor(order.x, order.y, order.target_type)
                return True, f"Floor placed at ({order.x},{order.y})."
            elif order.order_type == "stairs":
                from src.local_map import LocalTerrain
                STAIR_MAP = {
                    -1: LocalTerrain.STAIRS_UP,
                    -2: LocalTerrain.STAIRS_DOWN,
                    -3: LocalTerrain.LADDER_UP,
                    -4: LocalTerrain.LADDER_DOWN,
                }
                terrain_id = STAIR_MAP.get(order.target_type,
                                           LocalTerrain.STAIRS_UP)
                if local_map and local_map.in_bounds(order.x, order.y):
                    local_map.tiles[order.y][order.x].terrain = terrain_id
                    local_map.invalidate_terrain_cache()
                label = {-1: "Stairs up", -2: "Stairs down",
                         -3: "Ladder up", -4: "Ladder down"
                         }.get(order.target_type, "Stairs")
                return True, f"{label} built at ({order.x},{order.y})."

        return False, f"Building... {order.progress:.0f}%"

    def _try_consume(self, name: str, qty: int, inventory: list) -> bool:
        nl = name.lower()
        total = 0
        for item in inventory:
            if item.name.lower() == nl:
                total += getattr(item, "quantity", 1)
        if total < qty:
            return False
        # Actually consume
        remaining = qty
        for item in list(inventory):
            if remaining <= 0:
                break
            if item.name.lower() != nl:
                continue
            avail = getattr(item, "quantity", 1)
            if getattr(item, "stackable", False) and avail > remaining:
                item.quantity -= remaining
                remaining = 0
            else:
                inventory.remove(item)
                remaining -= avail
        return True

    # ── Equipment building ─────────────────────────────────────────────

    def start_equipment(self, blueprint_key: str,
                         local_map: "LocalMap",
                         x: int, y: int,
                         inventory: list) -> Tuple[Optional[PlacedEquipment], str]:
        """Start building a standalone equipment piece."""
        bp = EQUIPMENT_BLUEPRINTS.get(blueprint_key) or self._custom_equipment.get(blueprint_key)
        if not bp:
            return None, "Unknown equipment type."

        # Check space
        from src.local_map import LocalTerrain as _BLT
        for dy in range(bp.height):
            for dx in range(bp.width):
                if not local_map.in_bounds(x + dx, y + dy):
                    return None, "Not enough room."
                t = local_map.tiles[y + dy][x + dx].terrain
                if t == _BLT.ROCK:
                    return None, "Can't build on solid rock."
                # Sluices and water structures CAN be placed on water
                water_ok = any(tag in bp.functional_tags
                               for tag in ("pan_gold", "process_ore",
                                           "water_divert"))
                if t == _BLT.WATER and not water_ok:
                    return None, "Can't build on water. Try adjacent ground."
                if t == _BLT.DEEP_WATER:
                    return None, "Water too deep to build here."

        # Check materials
        for mat_name, mat_qty in bp.materials:
            if not self._has_material(mat_name, mat_qty, inventory):
                return None, f"Need {mat_qty}x {mat_name}."

        # Consume materials
        for mat_name, mat_qty in bp.materials:
            self._try_consume(mat_name, mat_qty, inventory)

        sid = local_map._next_id
        local_map._next_id += 1

        equip = PlacedEquipment(
            id=sid, blueprint_key=blueprint_key, name=bp.name,
            x=x, y=y, width=bp.width, height=bp.height,
            condition=100.0, progress=0.0,
            functional_tags=list(bp.functional_tags),
        )
        local_map.structures[sid] = equip
        return equip, f"Started building {bp.name}. ({bp.build_minutes} min to complete)"

    def work_on_equipment(self, equip: PlacedEquipment, minutes: int,
                            skill_level: int = 0,
                            local_map=None) -> str:
        if equip.complete:
            return f"{equip.name} is already finished."

        bp = EQUIPMENT_BLUEPRINTS.get(equip.blueprint_key) or self._custom_equipment.get(equip.blueprint_key)
        if not bp:
            return "Unknown equipment."

        rate = 1.0 + skill_level * 0.08
        pct_per_min = (100.0 / bp.build_minutes) * rate
        equip.progress = min(100.0, equip.progress + pct_per_min * minutes)

        if equip.complete:
            # Set terrain type for stairs/ladders when complete
            if local_map and "z_down" in equip.functional_tags:
                from src.local_map import LocalTerrain
                if local_map.in_bounds(equip.x, equip.y):
                    if "ladder" in equip.blueprint_key:
                        local_map.tiles[equip.y][equip.x].terrain = LocalTerrain.LADDER_DOWN
                    else:
                        local_map.tiles[equip.y][equip.x].terrain = LocalTerrain.STAIRS_DOWN
            elif local_map and "z_up" in equip.functional_tags:
                from src.local_map import LocalTerrain
                if local_map.in_bounds(equip.x, equip.y):
                    if "ladder" in equip.blueprint_key:
                        local_map.tiles[equip.y][equip.x].terrain = LocalTerrain.LADDER_UP
                    else:
                        local_map.tiles[equip.y][equip.x].terrain = LocalTerrain.STAIRS_UP
            return f"{equip.name} is complete and ready to use!"
        return f"{equip.name}: {equip.progress:.0f}% done."

    def _has_material(self, name: str, qty: int, inventory: list) -> bool:
        nl = name.lower()
        total = 0
        for item in inventory:
            if item.name.lower() == nl:
                total += getattr(item, "quantity", 1)
        return total >= qty

    # ── Zone management ────────────────────────────────────────────────

    def designate_zone(self, zone_type: str,
                        x: int, y: int, w: int, h: int,
                        zones: List[DesignatedZone],
                        label: str = "") -> DesignatedZone:
        zid = len(zones) + 1
        zone = DesignatedZone(
            id=zid, zone_type=zone_type,
            x=x, y=y, width=w, height=h,
            label=label or ZONE_LABELS.get(zone_type, zone_type),
        )
        zones.append(zone)
        return zone

    def tick_daily(self, local_map) -> List[str]:
        """Daily maintenance tick — equipment decay and build queue progress."""
        messages = []
        # Equipment condition decay (slow — 0.1% per day)
        for sid, struct in list(local_map.structures.items()):
            if hasattr(struct, 'condition') and struct.condition > 0:
                struct.condition = max(0.0, struct.condition - 0.1)
                if struct.condition <= 0:
                    messages.append(
                        f"{struct.name} has fallen into disrepair.")
        return messages

    def remove_zone(self, zone_id: int, zones: List[DesignatedZone]) -> bool:
        for i, z in enumerate(zones):
            if z.id == zone_id:
                zones.pop(i)
                return True
        return False

    def find_zone_for_task(self, task_key: str,
                            zones: List[DesignatedZone]
                            ) -> Optional[DesignatedZone]:
        for zone in zones:
            tasks = ZONE_TASK_MAP.get(zone.zone_type, [])
            if task_key in tasks:
                return zone
        return None

    # ── Keyword fallback for custom equipment ─────────────────────────

    # (see module-level _keyword_match_equipment below)

    # ── LLM custom equipment ──────────────────────────────────────────

    def categorize_custom_equipment(self, description: str,
                                     context: Dict[str, Any]
                                     ) -> Optional[EquipmentBlueprint]:
        if not self.llm or not self.llm.available:
            return _keyword_match_equipment(description)
        self.llm._load()
        if not self.llm.available:
            return _keyword_match_equipment(description)

        prompt = _build_equip_prompt(description, context)
        try:
            raw = self.llm._chat(
                [{"role": "system", "content": _EQUIP_SYSTEM},
                 {"role": "user",   "content": prompt}],
                temperature=0.30, max_tokens=400, json_mode=True,
            )
            bp = _parse_equip_blueprint(raw, description)
            if bp:
                # Don't overwrite builtin blueprints with LLM-generated ones
                if bp.key not in EQUIPMENT_BLUEPRINTS:
                    self._custom_equipment[bp.key] = bp
                    EQUIPMENT_BLUEPRINTS[bp.key] = bp
                else:
                    # Return the existing builtin instead
                    return EQUIPMENT_BLUEPRINTS[bp.key]
            return bp
        except Exception:
            return None

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> Dict:
        return {
            "custom_equipment": {
                k: {
                    "key": bp.key, "name": bp.name,
                    "width": bp.width, "height": bp.height,
                    "materials": bp.materials,
                    "build_minutes": bp.build_minutes,
                    "skill": bp.skill, "difficulty": bp.difficulty,
                    "description": bp.description,
                    "functional_tags": bp.functional_tags,
                    "glyph": bp.glyph,
                    "fg_color": list(bp.fg_color),
                    "source": "llm",
                }
                for k, bp in self._custom_equipment.items()
            },
        }

    @classmethod
    def from_dict(cls, d: Dict, llm=None) -> "ConstructionManager":
        mgr = cls(llm)
        for k, bd in d.get("custom_equipment", {}).items():
            # Don't let saved custom blueprints overwrite builtins
            if k in EQUIPMENT_BLUEPRINTS:
                continue
            bd["fg_color"] = tuple(bd.get("fg_color", (160, 130, 80)))
            bd["materials"] = [tuple(m) for m in bd.get("materials", [])]
            mgr._custom_equipment[k] = EquipmentBlueprint(**bd)
            EQUIPMENT_BLUEPRINTS[k] = mgr._custom_equipment[k]
        return mgr


# ============================================================================
#  LLM CUSTOM EQUIPMENT CATEGORIZATION
# ============================================================================

_EQUIP_SYSTEM = """\
You are a construction analyst for a frontier game set in 1849 America. \
A prospector wants to build a piece of equipment or structure. Determine \
realistic construction parameters given frontier materials and skills.

Return ONLY valid JSON. No commentary.
"""

def _build_equip_prompt(description: str, context: Dict) -> str:
    skills = ", ".join(f"{k}:{v}" for k, v in context.get("skills", {}).items()
                       if v > 0) or "untrained"
    return f"""\
STRUCTURE: "{description}"
PLAYER SKILLS: {skills}

Return JSON:
{{
  "key": "<snake_case_id>",
  "name": "<name>",
  "width": <int 1-6>,
  "height": <int 1-6>,
  "materials": [["<material_name>", <quantity>], ...],
  "build_minutes": <int>,
  "skill": "<governing_skill>",
  "difficulty": <int 1-20>,
  "description": "<1-2 sentences>",
  "functional_tags": [<list of tags>],
  "glyph": "<single ASCII char>",
  "fg_color": [<r>, <g>, <b>]
}}"""

def _parse_equip_blueprint(raw: str, fallback: str) -> Optional[EquipmentBlueprint]:
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return None
    key = f"custom_{str(d.get('key', fallback))[:24]}"
    # Normalize LLM material names to actual game item names
    _MAT_NORMALIZE = {
        "wood": "Log", "lumber": "Plank", "plank": "Plank",
        "planks": "Plank", "logs": "Log", "timber": "Log",
        "board": "Plank", "boards": "Plank",
        "nail": "Nails", "iron": "Iron Bar", "iron bar": "Iron Bar",
        "rope": "Rope (10 ft)", "stone": "Stone", "stones": "Stone",
        "rock": "Stone", "rocks": "Stone",
        "hide": "Deer Pelt", "leather": "Tanned Leather",
        "cloth": "Trade Blanket", "canvas": "Trade Blanket",
    }
    raw_mats = d.get("materials", [["Log", 1]])
    mats = []
    for m in raw_mats:
        name = str(m[0])
        qty = int(m[1]) if len(m) > 1 else 1
        normalized = _MAT_NORMALIZE.get(name.lower(), name)
        mats.append((normalized, qty))
    fg = tuple(d.get("fg_color", [160, 130, 80]))[:3]
    return EquipmentBlueprint(
        key=key, name=str(d.get("name", fallback)),
        width=max(1, min(6, int(d.get("width", 1)))),
        height=max(1, min(6, int(d.get("height", 1)))),
        materials=mats,
        build_minutes=max(5, int(d.get("build_minutes", 60))),
        skill=str(d.get("skill", "engineering")),
        difficulty=max(1, min(20, int(d.get("difficulty", 8)))),
        description=str(d.get("description", "")),
        functional_tags=d.get("functional_tags", []),
        glyph=str(d.get("glyph", "*"))[:1],
        fg_color=fg, source="llm",
    )
