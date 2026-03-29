"""
Main game engine: event loop, state management, input dispatch.
"""

import tcod
import tcod.event
from tcod import libtcodpy
from typing import List, Tuple, Optional, Dict

from src.constants import SCREEN_WIDTH, SCREEN_HEIGHT, TITLE
from src.player import Player, Stance, Speed, STANCE_LIST, SPEED_LIST
from src.world_map import WorldMap
from src.local_map import LocalMap, LocalTerrain
from src.time_system import GameTime
from src.renderer import Renderer
from src.survival import SurvivalStats
from src.llm_client import LLMClient


class GameState:
    LOCAL_MAP  = "local_map"
    AREA_MAP   = "area_map"    # zoom level 1  (~0.5 mi/tile, stride 0.1x — 8 world tiles wide)
    COUNTY_MAP = "county_map"  # zoom level 2  (~5 mi/tile,   1:1 world map)
    STATE_MAP  = "state_map"   # zoom level 3  (~25 mi/tile,  stride 5x)
    COUNTRY_MAP= "country_map" # zoom level 4  (~100 mi/tile, stride 20x)
    MENU       = "menu"
    INVENTORY  = "inventory"
    JOURNAL    = "journal"

MAP_LEVELS = [
    GameState.LOCAL_MAP,
    GameState.AREA_MAP,
    GameState.COUNTY_MAP,
    GameState.STATE_MAP,
    GameState.COUNTRY_MAP,
]

MAP_LEVEL_NAMES = {
    GameState.LOCAL_MAP:   "Local",
    GameState.AREA_MAP:    "Area",
    GameState.COUNTY_MAP:  "County",
    GameState.STATE_MAP:   "State",
    GameState.COUNTRY_MAP: "Country",
}

# For non-local views: how many world tiles each screen tile represents
# (stride) and the display label
MAP_STRIDE = {
    GameState.AREA_MAP:    0,   # special: magnified — each world tile = multiple screen tiles
    GameState.COUNTY_MAP:  1,   # 1:1
    GameState.STATE_MAP:   5,   # each screen tile = 5x5 world tiles
    GameState.COUNTRY_MAP: 20,  # each screen tile = 20x20 world tiles
}


class Engine:
    def __init__(self, llm_model_path: str = ""):
        from src.items import starting_inventory
        from src.npc import NPCManager
        from src.journal import Journal
        from src.wildlife_manager import WildlifeManager
        self.llm_model_path = llm_model_path  # passed to LLMClient when wired
        self.player   = Player(name="John Doe")
        self.player.inventory = starting_inventory()
        self.player.left_hand  = "Gold Pan"
        self.player.right_hand = "Pickaxe"
        # Starting pack animals
        self.player.pack_animals = [
            {"type_id": "mule",  "name": "Bessie", "condition": 85,
             "carrying_capacity_lb": 250.0},
            {"type_id": "dog",   "name": "Ranger", "condition": 90,
             "carrying_capacity_lb": 0.0},
        ]
        self.npc_mgr      = NPCManager(seed=42)
        self.wildlife_mgr = WildlifeManager(seed=42)
        self.journal  = Journal()
        # Seed starting journal entry
        self.journal.add_diary(
            "Apr 1, 1849",
            "Arrived at the American River. The hills are crawling with men. "
            "Found a decent-looking gravel bar. Time to see if the stories are true.\n\n"
            "What I know: Pan for gold at creeks and gravel bars [A]. "
            "Sell gold dust to merchants in town [T→Trade]. "
            "Build a sluice box for better recovery [B]. "
            "Talk to folks for tips on where the ground is rich [T]. "
            "Press [?] for controls. Press [J] to read this journal."
        )
        self.journal.add_letter(
            __import__('src.journal', fromlist=['Letter']).Letter(
                date_str="Mar 15, 1849",
                sender="Mother",
                recipient="John",
                body="We pray for your safe passage every evening. Your father "
                     "says not to trust anyone out there. Write when you can. "
                     "The money you send will help greatly. God keep you. — Mother",
            )
        )
        self.time     = GameTime()
        self.world    = WorldMap(seed=42)
        self.locals:  Dict[Tuple[int,int,int,int], LocalMap] = {}  # (wx, wy, ax, ay)
        self.state    = GameState.LOCAL_MAP
        self.map_level_index: int = 0   # index into MAP_LEVELS
        self.messages: List[Tuple[str, str]] = []
        self.renderer: Optional[Renderer] = None
        self._console = None  # set in run()
        self._ctx = None      # set in run()

        # ── System managers (must init before _ensure_local) ──────────
        from src.dynamic_locations import DynamicLocationDB
        from src.action_menu import ActionHistory
        from src.economy import ReputationTracker
        from src.companions import CompanionManager
        from src.legal import LegalSystem
        from src.npc_system import NPCGenerator, GossipSystem, BackgroundSimulator
        from src.writing import WritingManager
        from src.music import MusicManager

        self.dynamic_locs   = DynamicLocationDB()
        self.action_history = ActionHistory()
        self.reputation     = ReputationTracker()
        self.companion_mgr  = CompanionManager()
        self.legal           = LegalSystem()
        self._npc_gen        = NPCGenerator(seed=42)
        self.gossip          = GossipSystem()
        self.bg_sim          = BackgroundSimulator()
        self.writing         = WritingManager()
        self.music           = MusicManager("music")

        # Start on local map at Sacramento (center patch of world tile)
        self.world.mark_visited(self.player.world_x, self.player.world_y)
        start_lmap = self._ensure_local(
            self.player.world_x, self.player.world_y,
            self.player.area_x, self.player.area_y)
        # Move player near water — find closest stream/creek to center
        self._snap_player_near_water(start_lmap)
        self.player.local_z = start_lmap.ground_z(
            self.player.local_x, self.player.local_y)

        # Seed guaranteed gold near spawn — the player should find color
        # within the first few pans so they know the loop works
        px, py = self.player.local_x, self.player.local_y
        from src.local_map import LocalTerrain
        for dy in range(-8, 9):
            for dx in range(-8, 9):
                tx, ty = px + dx, py + dy
                if start_lmap.in_bounds(tx, ty):
                    tile = start_lmap.tiles[ty][tx]
                    if tile.terrain in (LocalTerrain.GRAVEL_BAR, LocalTerrain.WATER):
                        # Boost gold grade on nearby gravel/water tiles
                        tile.gold_grade = max(tile.gold_grade, 0.35 + abs(dx + dy) * 0.01)

        self._preload_neighbors()
        # Reveal a starting area on the world map so area/county views aren't blank
        self.world.mark_visited_radius(self.player.world_x, self.player.world_y, 8)

        self.show_gold_overlay = False   # toggled with G key
        self.combat_mode_pending = False  # auto-enter combat mode next frame

        # World map cursor (used in zoomed-out views for fast travel)
        self.map_cursor_x: int = self.player.world_x
        self.map_cursor_y: int = self.player.world_y

        self._last_tick_day = 0

        # LLM — loaded from config.json; model loads lazily on first call
        import json as _json
        try:
            with open("config.json") as _f:
                _cfg = _json.load(_f)
        except Exception:
            _cfg = {}
        self.llm = LLMClient(
            model_path=_cfg.get("model_path", "models/qwen2.5-7b-instruct-q4_k_m.gguf"),
            enabled=_cfg.get("llm_enabled", False),
            n_gpu_layers=_cfg.get("n_gpu_layers", -1),
            n_ctx=_cfg.get("n_ctx", 4096),
        )

        # ── Post-LLM system wiring ────────────────────────────────────
        from src.economy import TradeEngine
        from src.item_factory import ItemFactory
        from src.business import BusinessManager
        from src.construction import ConstructionManager

        self.trade        = TradeEngine(self.llm)
        self.item_factory = ItemFactory(self.llm)
        self.business_mgr = BusinessManager(self.llm)
        self.construction = ConstructionManager(self.llm)

        # Load the starting rifle
        for item in self.player.inventory:
            if item.weapon_type == "firearm" and item.extra.get("capacity", 0) > 0:
                ammo_type = item.extra.get("ammo_type", "")
                for ammo in self.player.inventory:
                    if ammo.id == ammo_type:
                        rounds = min(item.extra["capacity"], getattr(ammo, "quantity", 0))
                        item.extra["loaded"] = rounds
                        if ammo.stackable and ammo.quantity > rounds:
                            ammo.quantity -= rounds
                        else:
                            self.player.inventory.remove(ammo)
                        break
                break

        self.add_message(
            "You made it. California. The stories were true — men are pulling "
            "gold out of the rivers with their bare hands. The hills are crawling "
            "with prospectors, drifters, and dreamers. Time to get to work.",
            "normal")
        self.add_message("Press [?] for help.", "normal")

    # ── Local map management ──────────────────────────────────────────────

    def _ensure_local(self, wx: int, wy: int, ax: int = 7, ay: int = 7) -> LocalMap:
        key = (wx, wy, ax, ay)
        if key not in self.locals:
            terrain = int(self.world.tiles[wy][wx])
            seed = wx * 100000 + wy * 1000 + ax * 100 + ay
            self.locals[key] = LocalMap(
                wx, wy, terrain, world_map=self.world, seed=seed,
                area_x=ax, area_y=ay)
            # NPC spawning — use new generator if available, fall back to old
            self._spawn_npcs_for_tile(wx, wy, ax, ay, self.locals[key])
            self.wildlife_mgr.spawn_for_local(self.locals[key], wx, wy, ax, ay)
        return self.locals[key]

    def _spawn_npcs_for_tile(self, wx: int, wy: int, ax: int, ay: int, lmap):
        """
        Spawn NPCs for an area patch using NPCGenerator.
        Settlement patches (center of town world tile) get professions
        matched to buildings. Wilderness gets sparse prospectors.
        NPCs stored in npc_mgr.npcs for talk/combat/rendering.
        """
        import random as _r
        from src.town_gen import classify_settlement
        from src.constants import AREAS_PER_WORLD

        # Only spawn town NPCs in the center patch (7,7) of the world tile
        center = AREAS_PER_WORLD // 2
        loc = self.world.get_location_at(wx, wy)
        if loc and ax == center and ay == center:
            stype = classify_settlement(loc.location_type, loc.population)
            npcs = self._npc_gen.populate_settlement(
                stype, wx, wy, self.time.year, loc.name, ax=ax, ay=ay)
        else:
            terrain = int(self.world.tiles[wy][wx])
            npcs = self._npc_gen.populate_wilderness(
                wx, wy, terrain, self.time.year, ax=ax, ay=ay)

        rng = _r.Random(self.world.seed + wx * 100007 + wy * 1007 + ax * 101 + ay)
        for npc in npcs:
            if npc.npc_id not in self.npc_mgr.npcs:
                npc.local_x = rng.randint(5, lmap.width - 5)
                npc.local_y = rng.randint(5, lmap.height - 5)
                # Set z to surface elevation
                npc.local_z = lmap.ground_z(npc.local_x, npc.local_y)
                # Place NPCs at their building's door in settlements
                if loc and hasattr(lmap, 'town_layout') and lmap.town_layout:
                    for b in lmap.town_layout.buildings:
                        if b.occupation and b.occupation == npc.occupation:
                            npc.local_x = b.door_x
                            npc.local_y = b.door_y + 1
                            npc.local_z = lmap.ground_z(npc.local_x, npc.local_y)
                            break
                self.npc_mgr.npcs[npc.npc_id] = npc
                # Apply gossip — pre-adjust relationship if they've heard about player
                import random as _gossip_rng
                region = self.world.get_region(wx, wy)
                heard = self.gossip.apply_to_new_npc(
                    npc, region, self.time.total_minutes // 1440,
                    _gossip_rng.Random())
                for g in heard:
                    self.add_message(f"({npc.name} has heard: {g})", "advisory")
            npc.present = True

    def _preload_neighbors(self):
        """Generate all 8 adjacent area patches so the renderer can show them."""
        from src.constants import AREAS_PER_WORLD
        wx, wy = self.player.world_x, self.player.world_y
        ax, ay = self.player.area_x, self.player.area_y
        for day in (-1, 0, 1):
            for dax in (-1, 0, 1):
                if dax == 0 and day == 0:
                    continue
                nax, nay = ax + dax, ay + day
                nwx, nwy = wx, wy
                # Wrap area coords across world tile boundaries
                if nax < 0:
                    nwx -= 1; nax = AREAS_PER_WORLD - 1
                elif nax >= AREAS_PER_WORLD:
                    nwx += 1; nax = 0
                if nay < 0:
                    nwy -= 1; nay = AREAS_PER_WORLD - 1
                elif nay >= AREAS_PER_WORLD:
                    nwy += 1; nay = 0
                if self.world.in_bounds(nwx, nwy):
                    self._ensure_local(nwx, nwy, nax, nay)

    @property
    def current_local(self) -> LocalMap:
        return self._ensure_local(
            self.player.world_x, self.player.world_y,
            self.player.area_x, self.player.area_y)

    # ── Spawn positioning ──────────────────────────────────────────────

    def _snap_player_near_water(self, lmap):
        """Move player to the nearest passable tile adjacent to water."""
        from src.local_map import LocalTerrain, LOCAL_PASSABLE
        px, py = self.player.local_x, self.player.local_y
        best_d = 9999
        best_x, best_y = px, py
        # Search outward from center for water, pick adjacent passable tile
        for y in range(lmap.height):
            for x in range(lmap.width):
                if lmap.tiles[y][x].terrain != LocalTerrain.WATER:
                    continue
                d = abs(x - px) + abs(y - py)
                if d >= best_d:
                    continue
                # Find a passable neighbor of this water tile
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        nx, ny = x + dx, y + dy
                        if not lmap.in_bounds(nx, ny):
                            continue
                        t = lmap.tiles[ny][nx].terrain
                        if LOCAL_PASSABLE.get(t, False) and t != LocalTerrain.WATER:
                            nd = abs(nx - px) + abs(ny - py)
                            if nd < best_d:
                                best_d = nd
                                best_x, best_y = nx, ny
        self.player.local_x = best_x
        self.player.local_y = best_y

    # ── Gore: blood on ground, severed parts ────────────────────────────

    def _splatter_blood(self, lmap, x: int, y: int, intensity: int = 1):
        """Mark tiles with blood. intensity: 1=light (pink), 2=heavy (dark red)."""
        if lmap.in_bounds(x, y):
            tile = lmap.tiles[y][x]
            tile.blood = max(tile.blood, intensity)

    def _blood_pool(self, lmap, cx: int, cy: int, radius: int = 2, heavy: bool = False):
        """Create a blood pool centered at (cx, cy)."""
        import random as _r
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                nx, ny = cx + dx, cy + dy
                if not lmap.in_bounds(nx, ny):
                    continue
                dist = abs(dx) + abs(dy)
                if dist <= radius:
                    intensity = 2 if (heavy and dist <= 1) else 1
                    if _r.random() < 0.7:  # not every tile, looks more natural
                        self._splatter_blood(lmap, nx, ny, intensity)

    def _fling_severed_part(self, lmap, part_name: str,
                            from_x: int, from_y: int,
                            attacker_x: int, attacker_y: int):
        """Create a severed body part item and fling it away from the attacker.
        Leaves a blood trail as it skids across tiles."""
        import random as _r
        from src.items import Item

        # Direction: away from attacker
        dx = from_x - attacker_x
        dy = from_y - attacker_y
        # Normalize to -1/0/1
        if dx != 0: dx = dx // abs(dx)
        if dy != 0: dy = dy // abs(dy)
        if dx == 0 and dy == 0:
            dx = _r.choice([-1, 1])

        # Fling 2-5 tiles
        distance = _r.randint(2, 5)
        cx, cy = from_x, from_y
        for i in range(distance):
            # Jitter path slightly
            nx = cx + dx + _r.choice([0, 0, _r.choice([-1, 1])])
            ny = cy + dy + _r.choice([0, 0, _r.choice([-1, 1])])
            if not lmap.in_bounds(nx, ny) or not lmap.is_passable(nx, ny):
                break
            cx, cy = nx, ny
            self._splatter_blood(lmap, cx, cy, 2 if i < 2 else 1)

        # Create the body part item on the final tile
        part_item = Item(
            id=f"severed_{part_name.lower().replace(' ', '_')}",
            name=f"Severed {part_name}",
            weight=_r.uniform(0.5, 8.0),
            category="remains",
            description=f"A severed {part_name.lower()}. Gruesome.",
            base_value=0.0,
        )
        if lmap.in_bounds(cx, cy):
            lmap.tiles[cy][cx].ground_items.append(part_item)
            self._splatter_blood(lmap, cx, cy, 2)  # pool where it lands

        # Heavy blood at the source
        self._blood_pool(lmap, from_x, from_y, radius=1, heavy=True)

        return cx, cy  # where it landed

    # ── LOD: Progressive detail / eyesight ──────────────────────────────

    # Patch summaries — lightweight metadata for nearby unvisited patches
    _patch_summaries: Dict[Tuple[int,int,int,int], "PatchSummary"] = None

    def _init_patch_summaries(self):
        if self._patch_summaries is None:
            self._patch_summaries = {}

    def visible_patch_radius(self) -> int:
        """How many patches away the player can see (for area map LOD)."""
        lmap = self.current_local
        base = 2  # flat terrain, daytime = 2 patches ≈ 0.7 miles

        # Elevation bonus: +1 patch per 3 z-levels above local surface
        px, py = self.player.local_x, self.player.local_y
        surface = int(lmap.surface_z[py][px]) if lmap.in_bounds(px, py) else 0
        z_above = self.player.local_z - surface
        base += max(0, z_above // 3)

        # Terrain penalty: forest/brush reduces range
        from src.local_map import LocalTerrain
        tile = lmap.tile_at(px, py)
        if tile and tile.terrain in (
            LocalTerrain.FOREST, LocalTerrain.PINE, LocalTerrain.OAK,
            LocalTerrain.CEDAR, LocalTerrain.BRUSH
        ):
            base = max(1, base - 1)

        # Time of day
        period = self.time.period
        if period in ("dusk", "dawn"):
            base = max(1, base // 2)
        elif period == "night":
            base = 1

        return min(base, 6)  # cap at ~2 miles

    def _generate_patch_summary(self, wx, wy, ax, ay):
        """Generate lightweight PatchSummary for a nearby unvisited patch."""
        self._init_patch_summaries()
        key = (wx, wy, ax, ay)
        if key in self._patch_summaries:
            return self._patch_summaries[key]

        from src.local_map import PatchSummary
        from src.constants import AREAS_PER_WORLD

        terrain = int(self.world.tiles[wy][wx])
        center = AREAS_PER_WORLD // 2
        loc = self.world.get_location_at(wx, wy)
        has_struct = bool(loc) and ax == center and ay == center

        summary = PatchSummary(
            terrain_type=terrain,
            has_stream=(hash((wx, wy, ax, ay, 'stream')) % 3 == 0),
            avg_elevation=0,
            has_structure=has_struct,
            structure_type=loc.name if has_struct and loc else "",
        )
        self._patch_summaries[key] = summary
        return summary

    # ── FOV ───────────────────────────────────────────────────────────────

    def recompute_fov(self):
        lmap = self.current_local
        import numpy as np
        from src.local_map import LOCAL_TRANSPARENT

        r  = self._fov_radius()
        px = self.player.local_x
        py = self.player.local_y

        # Crop to (2r+2)×(2r+2) window around the player
        x1 = max(0, px - r - 1);  x2 = min(lmap.width,  px + r + 2)
        y1 = max(0, py - r - 1);  y2 = min(lmap.height, py + r + 2)
        cw, ch = x2 - x1, y2 - y1

        pz = self.player.local_z

        # Build transparency array — slice from cached numpy terrain array
        full_terrain = lmap.terrain_array()
        terrain_crop = full_terrain[y1:y2, x1:x2]
        # Build transparency: start with all True, mark opaque terrains False
        transparent = np.ones((ch, cw), dtype=bool)
        for opaque_terrain, is_transp in LOCAL_TRANSPARENT.items():
            if not is_transp:
                transparent[terrain_crop == opaque_terrain] = False

        fov = tcod.map.compute_fov(
            transparent,
            (py - y1, px - x1),
            radius=r,
            algorithm=libtcodpy.FOV_RESTRICTIVE,
        )

        # Clear previously visible tiles using cached set
        prev_visible = getattr(lmap, '_visible_tiles', None)
        if prev_visible is not None:
            for (tx, ty) in prev_visible:
                if lmap.in_bounds(tx, ty):
                    lmap.tiles[ty][tx].visible = False
        else:
            for cy in range(ch):
                for cx in range(cw):
                    lmap.tiles[y1 + cy][x1 + cx].visible = False

        # Mark new visible tiles — use numpy to find FOV indices
        fov_ys, fov_xs = np.where(fov)
        new_vis = set()
        wg = getattr(lmap, 'wall_grid', None)
        # Wall LOS check is expensive — only do it within wall range (15 tiles)
        wall_range = 15
        tiles_row = lmap.tiles
        for idx in range(len(fov_ys)):
            tx = x1 + int(fov_xs[idx])
            ty = y1 + int(fov_ys[idx])
            # Edge wall LOS check (only for nearby tiles where walls matter)
            if wg and abs(tx - px) + abs(ty - py) <= wall_range:
                if tx != px or ty != py:
                    if self._edge_wall_blocks_los(wg, px, py, tx, ty):
                        continue
            row = tiles_row[ty]
            row[tx].visible  = True
            row[tx].explored = True
            new_vis.add((tx, ty))
        lmap._visible_tiles = new_vis

        # Mark adjacent patch tiles as explored when viewport extends beyond edge.
        # Only process the out-of-bounds strips (not the entire FOV area).
        from src.constants import AREAS_PER_WORLD, PATCH_SIZE
        half_w = 40  # VIEWPORT_W // 2
        half_h = 19  # VIEWPORT_H // 2
        cam_x = px - half_w
        cam_y = py - half_h
        wx, wy = self.player.world_x, self.player.world_y
        ax, ay = self.player.area_x, self.player.area_y
        for vsy in range(half_h * 2):
            for vsx in range(half_w * 2):
                atx, aty = cam_x + vsx, cam_y + vsy
                if lmap.in_bounds(atx, aty):
                    continue  # on current patch
                # Resolve to adjacent patch coords
                _ax, _ay, _wx, _wy = ax, ay, wx, wy
                _tx, _ty = atx, aty
                if _tx < 0:
                    _ax -= 1; _tx += PATCH_SIZE
                elif _tx >= PATCH_SIZE:
                    _ax += 1; _tx -= PATCH_SIZE
                if _ty < 0:
                    _ay -= 1; _ty += PATCH_SIZE
                elif _ty >= PATCH_SIZE:
                    _ay += 1; _ty -= PATCH_SIZE
                if _ax < 0:
                    _wx -= 1; _ax += AREAS_PER_WORLD
                elif _ax >= AREAS_PER_WORLD:
                    _wx += 1; _ax -= AREAS_PER_WORLD
                if _ay < 0:
                    _wy -= 1; _ay += AREAS_PER_WORLD
                elif _ay >= AREAS_PER_WORLD:
                    _wy += 1; _ay -= AREAS_PER_WORLD
                adj_lmap = self.locals.get((_wx, _wy, _ax, _ay))
                if adj_lmap and adj_lmap.in_bounds(_tx, _ty):
                    adj_lmap.tiles[_ty][_tx].explored = True

    def _edge_wall_blocks_los(self, wg, px: int, py: int,
                                tx: int, ty: int) -> bool:
        """
        Walk a line from (px,py) to (tx,ty) checking for edge walls
        that block LOS.  Uses simple step-by-step walk (not Bresenham)
        for adjacency-correct edge checking.
        """
        cx, cy = px, py
        dx = 1 if tx > px else -1 if tx < px else 0
        dy = 1 if ty > py else -1 if ty < py else 0
        # Step one axis at a time toward target
        steps = abs(tx - px) + abs(ty - py)
        for _ in range(steps):
            # Decide which axis to step on
            rem_x = abs(tx - cx)
            rem_y = abs(ty - cy)
            if rem_x > rem_y:
                nx, ny = cx + dx, cy
            elif rem_y > rem_x:
                nx, ny = cx, cy + dy
            else:
                # Diagonal — step x first
                nx, ny = cx + dx, cy
            if wg.blocks_sight(cx, cy, nx, ny, z=self.player.local_z):
                return True
            cx, cy = nx, ny
            if cx == tx and cy == ty:
                break
        return False

    def _fov_radius(self) -> int:
        """FOV radius in tiles. At 5ft/tile, 60 tiles ≈ 300ft open-air sight."""
        period = self.time.period
        if period == "night":
            return 12   # ~60ft — moonlit/starlit visibility
        if period in ("dawn", "dusk"):
            return 35   # ~175ft — dim light
        return 60       # ~300ft — clear daylight on open ground

    # ── Time & survival tick ──────────────────────────────────────────────

    def advance_time(self, minutes: int):
        self.time.advance(minutes)

        # Warmth from clothing
        from src.clothing import warmth_modifier
        temp_mod = warmth_modifier(self.player.worn) if self.player.worn else 0.0
        con = self.player.attributes.get("constitution", 10)
        self.player.survival.tick(float(minutes), activity_mult=1.0,
                                   temp_mod=temp_mod, constitution=con)

        for stat, severity in self.player.survival.warnings():
            text = f"You are {severity}ly {stat}." if severity == "critical" \
                   else f"You are getting {stat}y."
            if not self.messages or self.messages[-1][0] != text:
                self.add_message(text, severity)

        # Wound bleeding tick
        for msg, sev in self.player.wounds.tick(float(minutes)):
            self.add_message(msg, sev)
        if not self.player.wounds.alive:
            self.player.survival.health = 0.0
            self._trigger_death("You have bled out.")
            return

        # Clothing wear
        if self.player.worn:
            for msg in self.player.worn.tick_wear(minutes):
                self.add_message(msg, "advisory")

        # Companion task completions
        npc_lookup = {n.npc_id: n for n in self._tile_npcs()}
        gold_bias = self.current_local._gold_bias if self.current_local else 0.3
        for result in self.companion_mgr.check_completions(
                self.time.total_minutes, npc_lookup, gold_bias):
            self.add_message(result.message, "advisory")
            self.player.gold_oz += result.gold_found
            for item_name in result.items_produced:
                item = self.item_factory.create(item_name)
                self.player.inventory.append(item)

        # ── Daily ticks (once per game day) ───────────────────────────
        current_day = self.time.total_minutes // 1440
        if current_day > self._last_tick_day:
            self._last_tick_day = current_day
            self._run_daily_ticks(current_day)

        if self.state == GameState.LOCAL_MAP:
            self._npc_wander_tick(minutes)
            lmap = self.current_local
            if lmap:
                for msg in self.wildlife_mgr.update_all(minutes, self.player, lmap):
                    severity = "critical" if "mauls" in msg or "claws" in msg or "charges" in msg else "advisory"
                    self.add_message(msg, severity)
                # Fluid simulation — run every 10+ minutes of game time
                if lmap.fluid_system and minutes >= 10:
                    lmap.fluid_system.simulate_step()
                # Fire spread — tick every minute
                if hasattr(lmap, '_fire') and lmap._fire and lmap._fire.active:
                    for _ in range(max(1, minutes)):
                        fire_msgs = lmap._fire.tick(lmap)
                        for fm in fire_msgs:
                            self.add_message(fm, "critical")
                    lmap.invalidate_terrain_cache()
                    # Damage player if standing in or near fire
                    pkey = (self.player.local_x, self.player.local_y)
                    if pkey in lmap._fire.burning:
                        burn_dmg = 8.0 * minutes
                        self.player.survival.health -= burn_dmg
                        self.add_message("You're in the fire! MOVE!", "critical")
                    else:
                        # Heat damage from nearby fire
                        fire_tiles = lmap._fire.get_fire_tiles()
                        near_fire = 0
                        for (fx, fy) in fire_tiles:
                            d = max(abs(fx - self.player.local_x),
                                    abs(fy - self.player.local_y))
                            if d <= 3:
                                near_fire += 1
                        if near_fire >= 3:
                            heat_dmg = 1.0 * minutes
                            self.player.survival.health -= heat_dmg
                            self.add_message(
                                "The heat is intense. You're too close to the fire.",
                                "advisory")
                    # NPC fire damage + flee
                    fire_tiles = lmap._fire.get_fire_tiles()
                    for npc in self._tile_npcs():
                        if not npc.alive:
                            continue
                        nk = (npc.local_x, npc.local_y)
                        if nk in fire_tiles:
                            npc.health -= 8.0 * minutes
                            if npc.health <= 0:
                                npc.alive = False
                                npc.combat_state = "dead"
                                self.add_message(
                                    f"{npc.name} burns to death.", "critical")
                                self._blood_pool(lmap, npc.local_x, npc.local_y, 1)
                            elif npc.combat_state != "fleeing":
                                npc.combat_state = "fleeing"
                                self.add_message(
                                    f"{npc.name} runs from the fire!", "advisory")
                        elif npc.combat_state == "neutral":
                            # Flee if fire nearby
                            for (fx, fy) in fire_tiles:
                                if max(abs(fx - npc.local_x), abs(fy - npc.local_y)) <= 3:
                                    npc.combat_state = "fleeing"
                                    break
                    # Wildlife fire damage + flee
                    for animal in self.wildlife_mgr.get_animals(
                            self.player.world_x, self.player.world_y,
                            self.player.area_x, self.player.area_y):
                        if not animal.alive:
                            continue
                        ak = (animal.local_x, animal.local_y)
                        if ak in fire_tiles:
                            animal.take_damage(8.0 * minutes)
                            if animal.state == "dead":
                                self.add_message(
                                    f"A {animal.species.display_name} burns in the fire.",
                                    "advisory")
                        elif animal.state == "idle":
                            for (fx, fy) in fire_tiles:
                                if max(abs(fx - animal.local_x),
                                       abs(fy - animal.local_y)) <= 5:
                                    animal.state = "fleeing"
                                    animal.alert = True
                                    break

    def _run_daily_ticks(self, current_day: int):
        """Run all once-per-day system updates."""
        p = self.player
        region = ""
        if self.current_local:
            region = self.current_local._region_name

        # Wound infection/healing (CON affects infection resistance + healing)
        con = p.attributes.get("constitution", 10)
        for msg, sev in p.wounds.tick_daily(constitution=con):
            self.add_message(msg, sev)

        # Companion daily morale/loyalty
        for msg in self.companion_mgr.tick_daily():
            self.add_message(msg, "advisory")

        # Business daily revenue
        rep = self.reputation.get(region)
        for biz_name, finance, event in self.business_mgr.tick_daily(current_day, rep):
            if finance.profit != 0:
                p.cash += finance.profit
            if event:
                self.add_message(f"[{biz_name}] {event.description}", "advisory")

        # Legal sentence serving
        msg = self.legal.tick_sentence(current_day)
        if msg:
            self.add_message(msg, "normal")

        # Dynamic location aging (every 90 days = 1 season)
        if current_day % 90 == 0:
            for loc in self.dynamic_locs.age_one_season(self.time.year):
                self.add_message(f"{loc.name} is {loc.stage}.", "advisory")

        # Construction decay
        if self.current_local:
            for msg in self.construction.tick_daily(self.current_local):
                self.add_message(msg, "advisory")

        # Publishing responses — check if any submission responses arrived
        # Responses route through mail system; player picks them up at post office
        from src.world_gen import era_locations
        nearest_town = ""
        best_d = 9999
        for loc in era_locations(self.time.year):
            d = abs(loc.x - p.world_x) + abs(loc.y - p.world_y)
            if d < best_d and loc.loc_type in ("town", "city"):
                best_d = d
                nearest_town = loc.name
        self.writing.check_responses(
            current_day, p.name, nearest_town, self.llm)

        # Book royalties (monthly)
        if current_day % 30 == 0:
            royalties = self.writing.collect_royalties(current_day)
            if royalties > 0:
                # Royalties arrive by mail, not magically
                self.writing.mail.send_letter(
                    sender="Publisher",
                    recipient=p.name,
                    body=f"Enclosed: royalty payment of ${royalties:.2f} "
                         f"for your published works.",
                    day=current_day,
                    origin="New York City",
                    destination=nearest_town,
                    distance_tiles=60,
                )

        # Writer fame → reputation
        fame = self.writing.writer_fame()
        if fame > 10 and region:
            self.reputation.adjust(region, fame * 0.01, spread=True)

    def _tile_npcs(self):
        """NPCs whose ID belongs to the current area patch only."""
        wx, wy = self.player.world_x, self.player.world_y
        ax, ay = self.player.area_x, self.player.area_y
        prefixes = (f"sett_{wx}_{wy}_{ax}_{ay}_", f"wild_{wx}_{wy}_{ax}_{ay}_")
        return [n for n in self.npc_mgr.npcs.values()
                if n.present and any(n.npc_id.startswith(p) for p in prefixes)]

    def _witnesses_near(self, x: int, y: int, exclude_id: str = "",
                        exclude_names: set = None) -> list:
        """NPCs within sight range of (x, y) who could witness an event.
        NPC sight: 40 tiles (200ft) day, 15 tiles (75ft) night."""
        period = self.time.period
        if period == "night":
            sight = 15
        elif period in ("dawn", "dusk"):
            sight = 25
        else:
            sight = 40
        result = []
        for n in self._tile_npcs():
            if not n.alive:
                continue
            if exclude_id and n.npc_id == exclude_id:
                continue
            if exclude_names and n.name in exclude_names:
                continue
            dist = max(abs(n.local_x - x), abs(n.local_y - y))
            if dist <= sight:
                result.append(n)
        return result

    def _npc_wander_tick(self, minutes: int):
        """Simple time-proportional random walk for non-combat NPCs."""
        import random as _r
        lmap = self.current_local
        for npc in self._tile_npcs():
            if not npc.alive or not npc.present:
                continue
            if npc.combat_state == "hostile":
                continue  # handled by combat tick
            # Probability of moving scales with time — ~1 step per 10 minutes
            if _r.random() > minutes / 10.0:
                continue
            dx = _r.choice([-1, 0, 0, 1])  # bias toward staying put
            dy = _r.choice([-1, 0, 0, 1])
            if dx == 0 and dy == 0:
                continue
            nx, ny = npc.local_x + dx, npc.local_y + dy
            # Check tile passability AND edge walls
            wall_ok = True
            npc_z = getattr(npc, "local_z", 0)
            if hasattr(lmap, 'wall_grid') and lmap.wall_grid:
                wall_ok = lmap.wall_grid.can_pass(npc.local_x, npc.local_y, nx, ny,
                                                    z=npc_z)
            # NPCs stay at their z-level — don't walk up/down cliffs
            z_ok = True
            if lmap.in_bounds(nx, ny):
                target_sz = int(lmap.surface_z[ny][nx])
                if abs(target_sz - npc_z) > 1:
                    z_ok = False
                elif target_sz != npc_z:
                    # Only cross z-diff of 1 if there's a ramp
                    from src.local_map import LocalTerrain as _NLT
                    cur_tile = lmap.tile_at_z(npc.local_x, npc.local_y, npc_z)
                    ramp_types = (_NLT.RAMP_UP, _NLT.RAMP_DOWN, _NLT.STAIRS_UP,
                                  _NLT.STAIRS_DOWN, _NLT.STAIRS_BOTH)
                    if not (cur_tile and cur_tile.terrain in ramp_types):
                        z_ok = False
                    else:
                        npc.local_z = target_sz
            if (lmap.in_bounds(nx, ny)
                    and lmap.is_passable(nx, ny)
                    and wall_ok and z_ok
                    and not (nx == self.player.local_x
                             and ny == self.player.local_y)
                    and self.npc_mgr.get_at(nx, ny) is None):
                npc.local_x = nx
                npc.local_y = ny

    # ── Messages ──────────────────────────────────────────────────────────

    def add_message(self, text: str, severity: str = "normal"):
        self.messages.append((text, severity))
        if len(self.messages) > 200:
            self.messages = self.messages[-200:]

    # ── Input handling ────────────────────────────────────────────────────

    _last_keydown_handled = False

    def handle_event(self, event: tcod.event.Event) -> bool:
        """Returns False to quit."""
        if isinstance(event, tcod.event.Quit):
            return False

        if isinstance(event, tcod.event.KeyDown):
            self._last_keydown_handled = True
            try:
                return self._handle_key(event)
            except Exception as _exc:
                import traceback as _tb
                with open("error.log", "a") as _f:
                    _f.write(f"\n--- key handler crash ---\n")
                    _tb.print_exc(file=_f)
                self.add_message(f"Error: {_exc}", "critical")
                return True

        # Handle TextInput as key presses — SDL3 on Windows sends
        # letter keys as TextInput, not KeyDown, when text input is active.
        # Skip if KeyDown already handled this key (prevents double-toggle).
        if isinstance(event, tcod.event.TextInput):
            if self._last_keydown_handled:
                self._last_keydown_handled = False
                return True
            self._last_keydown_handled = False
            with open("keylog.txt", "a") as _kf:
                _kf.write(f"TEXTINPUT: text={repr(event.text)}\n")
                _kf.flush()
            text = event.text.lower()
            if len(text) == 1 and text.isalpha():
                # Create a synthetic KeyDown from the text character
                sym_val = ord(text)
                class _SyntheticKey:
                    def __init__(self, s):
                        self.sym = s
                        self.mod = 0
                        self.repeat = False
                try:
                    return self._handle_key(_SyntheticKey(sym_val))
                except Exception as _exc:
                    self.add_message(f"Error: {_exc}", "critical")
                    return True

        return True

    _prev_keys: set = set()

    def _poll_keyboard_state(self):
        """
        Poll Windows keyboard state directly via GetAsyncKeyState.
        Workaround for SDL3 on Windows not generating KeyDown for letters.
        """
        try:
            import ctypes
            user32 = ctypes.windll.user32
        except Exception:
            return

        pressed_now = set()
        # Virtual key codes: A=0x41 through Z=0x5A
        for vk in range(0x41, 0x5B):
            if user32.GetAsyncKeyState(vk) & 0x8000:
                pressed_now.add(vk)

        # Also check special keys that might be missing
        # ? = Shift+/ : VK_OEM_2=0xBF
        if user32.GetAsyncKeyState(0x10) & 0x8000:  # VK_SHIFT
            if user32.GetAsyncKeyState(0xBF) & 0x8000:  # VK_OEM_2 (/)
                pressed_now.add(0x100)  # synthetic "?" code

        new_presses = pressed_now - Engine._prev_keys
        Engine._prev_keys = pressed_now

        for vk in new_presses:
            if vk == 0x100:
                # ? key
                sym_val = ord('?')
            else:
                sym_val = vk + 32  # VK 0x41='A' -> ord('a')=97

            class _WinKey:
                def __init__(self, s):
                    self.sym = s
                    self.mod = 0
                    self.repeat = False
            try:
                self._handle_key(_WinKey(sym_val))
            except Exception:
                pass

    def _handle_key(self, event) -> bool:
        sym = event.sym
        K   = tcod.event.KeySym

        # Movement — arrow keys and vi-keys
        MOVE_KEYS = {
            K.UP:    ( 0, -1), K.KP_8:  ( 0, -1),
            K.DOWN:  ( 0,  1), K.KP_2:  ( 0,  1),
            K.LEFT:  (-1,  0), K.KP_4:  (-1,  0),
            K.RIGHT: ( 1,  0), K.KP_6:  ( 1,  0),
            K.KP_7:  (-1, -1), K.KP_9:  ( 1, -1),
            K.KP_1:  (-1,  1), K.KP_3:  ( 1,  1),
        }
        if sym in MOVE_KEYS:
            if self.map_level_index > 0:
                # Zoomed out — move cursor, not player
                dx, dy = MOVE_KEYS[sym]
                stride = {1: 1, 2: 1, 3: 5, 4: 20}.get(self.map_level_index, 1)
                self.map_cursor_x += dx * stride
                self.map_cursor_y += dy * stride
                self.map_cursor_x = max(0, min(self.world.width - 1, self.map_cursor_x))
                self.map_cursor_y = max(0, min(self.world.height - 1, self.map_cursor_y))
            else:
                self._do_move(*MOVE_KEYS[sym])
            return True

        # Note: all key checks use sym directly, not char conversion

        # Fast travel — Enter while zoomed out
        if sym in (K.RETURN, K.KP_ENTER) and self.map_level_index > 0:
            self._handle_fast_travel()
            return True

        # Zoom out  [
        if sym == K.LEFTBRACKET:
            self._zoom_out()
            return True

        # Zoom in  ]
        if sym == K.RIGHTBRACKET:
            self._zoom_in()
            return True

        # Z-level navigation: < up, > down
        if sym == K.COMMA and (event.mod & tcod.event.KMOD_SHIFT):
            if self.state == GameState.LOCAL_MAP:
                from src.constants import Z_MAX
                if self.player.local_z < Z_MAX:
                    self.player.local_z += 1
                    self.recompute_fov()
                    sz = int(self.current_local.surface_z[
                        self.player.local_y][self.player.local_x])
                    if self.player.local_z > sz:
                        self.add_message(f"Looking up (Z:{self.player.local_z:+d})", "normal")
                    else:
                        self.add_message(f"Z-level: {self.player.local_z:+d}", "normal")
            return True
        if sym == K.PERIOD and (event.mod & tcod.event.KMOD_SHIFT):
            if self.state == GameState.LOCAL_MAP:
                from src.constants import Z_MIN
                if self.player.local_z > Z_MIN:
                    self.player.local_z -= 1
                    self.recompute_fov()
                    sz = int(self.current_local.surface_z[
                        self.player.local_y][self.player.local_x])
                    if self.player.local_z < sz:
                        self.add_message(f"Looking down (Z:{self.player.local_z:+d})", "normal")
                    else:
                        self.add_message(f"Z-level: {self.player.local_z:+d}", "normal")
            return True

        # All key bindings use sym directly — char-based checks fail
        # on some tcod/SDL configurations where text input mode
        # intercepts letter keys.

        if sym == K.i:
            self._open_inventory()
            return True
        if sym == K.c:
            self._open_character()
            return True
        if sym == K.e:
            self._open_examine()
            return True
        if sym == K.p:
            self._open_pickup()
            return True
        if sym == K.b:
            self._open_build_menu()
            return True
        if sym == K.a:
            self._open_actions()
            return True
        if sym == K.j:
            self._open_journal()
            return True
        if sym == K.t:
            self._open_talk()
            return True
        # Hunting mode  H
        if sym == K.h:
            if self.state == GameState.LOCAL_MAP:
                from src.hunting_mode import enter_hunting_mode
                enter_hunting_mode(self, self._console, self._ctx)
            return True
        if sym == K.s:
            if event.mod & tcod.event.Modifier.CTRL:
                self._do_save()
            else:
                self.player.cycle_stance()
                self.add_message(f"Stance: {self.player.stance}.", "normal")
            return True
        if sym == K.w:
            self.player.cycle_speed()
            self.add_message(f"Speed: {self.player.speed}.", "normal")
            return True
        if sym == K.g and self.state == GameState.LOCAL_MAP:
            self.show_gold_overlay = not self.show_gold_overlay
            state = "ON" if self.show_gold_overlay else "OFF"
            self.add_message(f"Gold overlay {state}.", "normal")
            return True
        if sym == K.SPACE:
            self._open_wait()
            return True
        if sym == K.k:
            self._open_combat()
            return True

        # Help  ?
        if sym == K.SLASH and (event.mod & tcod.event.KMOD_SHIFT):
            self._open_help()
            return True

        # Mining work mode  M
        if sym == K.m:
            if self.state == GameState.LOCAL_MAP:
                from src.mining_mode import enter_mining_mode
                enter_mining_mode(self, self._console, self._ctx)
            return True

        # Message log  L
        if sym == K.l:
            self._open_log_viewer()
            return True

        # Pause / Settings menu
        if sym == K.ESCAPE:
            result = self._open_pause_menu()
            if result == "quit":
                return False
            return True

        return True

    # ── Menu handlers ─────────────────────────────────────────────────────

    def _open_inventory(self):
        from src.ui_inventory import open_inventory
        open_inventory(self._console, self._ctx, self.player)

    def _open_character(self):
        from src.ui_character import open_character
        open_character(self._console, self._ctx, self.player,
                        reputation=self.reputation,
                        writing=self.writing)

    def _open_build_menu(self):
        if self.state != GameState.LOCAL_MAP:
            self.add_message("Building only on the local map.", "normal")
            return
        from src.ui_build import open_build
        result = open_build(self._console, self._ctx, self.player,
                             local_map=self.current_local,
                             construction=self.construction)
        if result:
            self._process_build_result(result)

    def _process_build_result(self, result):
        """Handle build menu return values."""
        if not result:
            return
        action = result[0] if isinstance(result, tuple) else result

        if action == "build_equipment":
            bp_key = result[1]
            lmap = self.current_local
            px, py = self.player.local_x, self.player.local_y
            equip, msg = self.construction.start_equipment(
                bp_key, lmap, px + 1, py, self.player.inventory)
            self.add_message(msg, "advisory" if equip else "normal")
            if equip:
                skill = self.player.skills.get("engineering", 0)
                result_msg = self.construction.work_on_equipment(equip, 30, skill)
                self.add_message(result_msg, "advisory")
                self.player.gain_skill_xp("engineering", 3.0)
                self.advance_time(30)

        elif action == "build_custom":
            ctx = self._build_llm_context()
            self.add_message("Describe what you want to build:", "normal")
            # Custom build handled through action menu LLM path
            self._resolve_action("build custom structure")

        elif action == "designate_zone":
            ztype = result[1]
            from src.construction import ZONE_LABELS
            label = ZONE_LABELS.get(ztype, ztype)
            # Quick zone: 3x3 at player position
            px, py = self.player.local_x, self.player.local_y
            lmap = self.current_local
            self.construction.designate_zone(
                ztype, px - 1, py - 1, 3, 3,
                lmap.zones, label)
            self.add_message(f"Designated {label} zone (3x3 at your position).", "advisory")

    # ── DEAD CODE: _open_food, _open_fishing, _open_throw, _open_health ──
    # These are unreachable — no key binding calls them.
    # Functionality consolidated into tabbed menus.
    # Safe to delete in a cleanup pass.

    def _open_food(self):
        # If near water and on local map, offer to fish instead
        if self.state == GameState.LOCAL_MAP and self.current_local is not None:
            lmap = self.current_local
            near_water = any(
                lmap.in_bounds(self.player.local_x + dx, self.player.local_y + dy)
                and lmap.tile_at(self.player.local_x + dx,
                                 self.player.local_y + dy).terrain == LocalTerrain.WATER
                for dy in range(-3, 4) for dx in range(-3, 4)
            )
            if near_water:
                from src.menus import pick_from_list
                choice = pick_from_list(self._console, self._ctx,
                                        "Near water — what do you do?",
                                        ["Eat / drink from supplies", "Fish"])
                if choice == 1:
                    self._open_fishing()
                    return
                elif choice is None:
                    return
                # else fall through to normal food menu

        from src.menus import food_menu
        result = food_menu(self._console, self._ctx, self.player)
        if result:
            item = result["consumed"]
            if item.is_food() and not item.extra.get("requires_cooking"):
                self.player.survival.eat(item.nutrition)
                self.add_message(f"You eat the {item.name}. (+{item.nutrition:.0f} hunger)", "normal")
                # Remove one from inventory
                if item.stackable and item.quantity > 1:
                    item.quantity -= 1
                else:
                    self.player.inventory.remove(item)
                self.advance_time(5)
            elif item.extra.get("requires_cooking"):
                self.add_message(f"The {item.name} needs to be cooked first.", "advisory")
            elif item.is_drink():
                self.player.survival.drink(item.hydration)
                self.add_message(f"You drink. (+{item.hydration:.0f} thirst)", "normal")
                self.player.inventory.remove(item)
                self.advance_time(2)

    def _open_fishing(self):
        """Fish near water. F key when adjacent to water."""
        import random as _rnd
        from src.menus import pick_from_list
        from src.fish_system import FishingMechanics
        from src.items import make_item

        METHODS = [
            ("By hand (no tools)",      "hand"),
            ("With a knife (spear)",     "spear"),
            ("With a fishing pole",      "pole"),
            ("Set a net / trap",         "trap"),
        ]
        # Filter to what the player might plausibly have
        available = []
        inv_names = [i.name.lower() for i in self.player.inventory]
        has_pole = any("pole" in n or "rod" in n for n in inv_names)
        has_net  = any("net" in n for n in inv_names)
        for label, key in METHODS:
            if key == "pole" and not has_pole:
                continue
            if key == "trap" and not has_net:
                continue
            available.append((label, key))

        if not available:
            available = [("By hand (no tools)", "hand"),
                         ("With a knife (spear)", "spear")]

        labels = [l for l, _ in available]
        idx = pick_from_list(self._console, self._ctx, "How do you fish?", labels)
        if idx is None:
            return

        _, method = available[idx]
        lmap = self.current_local
        region = lmap._region_name or "California"
        season = self.time.season

        rng = _rnd.Random()
        fish = FishingMechanics.attempt_catch(
            region_name=region,
            method=method,
            survival_skill=self.player.skills.get("survival", 0),
            season=season,
            rng=rng,
        )
        time_spent = FishingMechanics.time_cost(method)

        if fish is None:
            msgs = [
                "Nothing biting today.",
                "You fish for a while, but come up empty.",
                "The water looks good, but luck isn't with you.",
                "You wait, but the fish aren't interested.",
            ]
            self.add_message(_rnd.choice(msgs), "normal")
        else:
            msg = FishingMechanics.get_catch_message(fish, method)
            self.add_message(msg, "normal")

            # Add to inventory
            caught = make_item("fresh_fish")
            caught.name = f"Fresh {fish.display_name}"
            caught.nutrition = fish.nutrition
            # Stack if already have fish
            existing = next((i for i in self.player.inventory
                             if i.id == "fresh_fish"), None)
            if existing and existing.stackable:
                existing.quantity = getattr(existing, "quantity", 1) + 1
            else:
                self.player.inventory.append(caught)

            self.player.gain_skill_xp("survival", 1.5 + fish.catch_difficulty * 0.5)

        self.advance_time(time_spent)

    def _open_examine(self):
        """Pure look/examine — shows terrain, NPCs, animals, items."""
        if self.state == GameState.LOCAL_MAP:
            from src.menus import examine_menu
            lmap = self.current_local
            examine_menu(self._console, self._ctx, self.player, lmap,
                         npc_mgr=self.npc_mgr, wildlife_mgr=self.wildlife_mgr)
        else:
            self._examine_world_tile()

    def _open_pickup(self):
        """[P] — pick up items, butcher animals, or butcher dead/surrendered NPCs."""
        if self.state != GameState.LOCAL_MAP:
            return
        lmap = self.current_local
        from src.menus import pick_from_list

        # Collect all butcherable targets adjacent
        targets = []

        # Animals
        for a in self.wildlife_mgr.get_animals(
                self.player.world_x, self.player.world_y,
                self.player.area_x, self.player.area_y):
            if (a.recoverable
                and max(abs(a.local_x - self.player.local_x),
                        abs(a.local_y - self.player.local_y)) <= 1
                and getattr(a, "local_z", 0) == self.player.local_z):
                targets.append(("animal", a, f"{a.species.display_name} (animal)"))

        # Dead, surrendered, or incapacitated NPCs
        for npc in self._tile_npcs():
            dist = max(abs(npc.local_x - self.player.local_x),
                       abs(npc.local_y - self.player.local_y))
            if dist > 2:
                continue
            if npc.combat_state in ("dead", "surrendered"):
                state = "dead" if npc.combat_state == "dead" else "surrendered"
                targets.append(("npc", npc, f"{npc.display_name()} ({state})"))
            elif npc.health < 25 and npc.alive:
                targets.append(("npc", npc, f"{npc.display_name()} (incapacitated)"))

        # Ground items on current tile
        tile = lmap.tile_at(self.player.local_x, self.player.local_y)
        has_items = bool(tile.ground_items)

        if not targets and not has_items:
            self.add_message("Nothing here to pick up or butcher.", "normal")
            return

        # If only ground items, just pick up
        if not targets and has_items:
            self._pick_up_ground_items(tile)
            return

        # If only one target and no items, go straight to it
        if len(targets) == 1 and not has_items:
            kind, obj, _ = targets[0]
            if kind == "animal":
                self._open_butcher(obj)
            else:
                self._open_butcher_npc(obj)
            return

        # Multiple options — let player choose
        labels = [t[2] for t in targets]
        if has_items:
            labels.append("Pick up ground items")
        idx = pick_from_list(self._console, self._ctx, "What do you do?", labels)
        if idx is None:
            return
        if idx < len(targets):
            kind, obj, _ = targets[idx]
            if kind == "animal":
                self._open_butcher(obj)
            else:
                self._open_butcher_npc(obj)
        else:
            self._pick_up_ground_items(tile)

    def _open_butcher(self, animal):
        """Butcher menu for a downed or dead animal."""
        from src.menus import pick_from_list
        from src.butcher import butcher, has_sharp_tool, METHODS, TIME_COST
        import random as _rnd

        sp = animal.species
        state_str = "dead" if animal.state == "dead" else "downed (still alive)"
        self.add_message(
            f"{sp.display_name} — {state_str}, {sp.meat_yield_lb:.0f} lb animal.",
            "normal")

        if not has_sharp_tool(self.player):
            self.add_message(
                "You need a knife or axe to butcher. You don't have one.", "advisory")
            return

        labels = [label for _, label in METHODS]
        idx = pick_from_list(self._console, self._ctx, "How do you butcher?", labels)
        if idx is None:
            return

        method_key = METHODS[idx][0]
        rng = _rnd.Random()
        items, msgs = butcher(animal, method_key, self.current_local, rng)

        for msg in msgs:
            self.add_message(msg, "normal")

        self.player.gain_skill_xp("survival", 2.0 + idx * 1.5)
        self.advance_time(TIME_COST[method_key])

    def _open_butcher_npc(self, npc):
        """Loot and/or butcher a dead, surrendered, or incapacitated NPC."""
        from src.menus import pick_from_list
        from src.butcher import has_sharp_tool, TIME_COST
        from src.items import Item, make_item
        import random as _rnd

        # Build unified menu: let go / individual loot items / lodged / butcher
        options = []
        option_actions = []  # parallel list of (action_type, data)

        if npc.combat_state == "surrendered" or (npc.alive and npc.health < 25):
            options.append("Let them go")
            option_actions.append(("let_go", None))

        # Generate loot preview
        rng = _rnd.Random(hash(npc.npc_id))
        cash_found = rng.uniform(0.50, 15.00)
        options.append(f"Take ${cash_found:.2f} (coins & dust)")
        option_actions.append(("take_cash", cash_found))

        # Occupation-based loot items
        occ = (npc.occupation or "").lower()
        loot_items = []
        if "prospector" in occ or "miner" in occ:
            gold = rng.uniform(0.01, 0.15)
            options.append(f"Take {gold:.3f} oz gold dust")
            option_actions.append(("take_gold", gold))
            if rng.random() < 0.4:
                loot_items.append("gold_pan")
        if "hunter" in occ or "trapper" in occ:
            if rng.random() < 0.5:
                loot_items.append("hunting_knife")
        if rng.random() < 0.3:
            loot_items.append("hardtack")
        if rng.random() < 0.35:
            weapon_ids = ["percussion_revolver", "bowie_knife", "hunting_knife"]
            loot_items.append(rng.choice(weapon_ids))

        for item_id in loot_items:
            try:
                test = make_item(item_id)
                options.append(f"Take {test.name}")
                option_actions.append(("take_item", item_id))
            except Exception:
                pass

        # Lodged objects in wounds
        if hasattr(npc, 'wounds') and npc.wounds:
            for w in npc.wounds.wounds:
                if w.lodged:
                    options.append(f"Extract {w.lodged} from {w.part}")
                    option_actions.append(("extract_lodged", w))

        # Butcher option
        if has_sharp_tool(self.player):
            options.append("--- Butcher body ---")
            option_actions.append(("butcher", None))

        options.append("Done")
        option_actions.append(("done", None))

        # Loop so player can take multiple items
        taken_cash = False
        taken_gold = False
        taken_items = set()
        while True:
            choice = pick_from_list(self._console, self._ctx,
                f"{npc.display_name()} — {npc.combat_state}", options)
            if choice is None:
                return

            act, data = option_actions[choice]

            if act == "done":
                return
            if act == "let_go":
                npc.combat_state = "fleeing"
                self.add_message(f"{npc.name} scrambles away.", "normal")
                return
            if act == "take_cash" and not taken_cash:
                self.player.cash += data
                self.add_message(f"Took ${data:.2f}.", "normal")
                taken_cash = True
                options[choice] = f"(taken) ${data:.2f}"
            elif act == "take_gold" and not taken_gold:
                self.player.gold_oz += data
                self.add_message(f"Took {data:.3f} oz gold dust.", "normal")
                taken_gold = True
                options[choice] = f"(taken) gold dust"
            elif act == "take_item" and data not in taken_items:
                try:
                    self.player.inventory.append(make_item(data))
                    nm = make_item(data).name
                    self.add_message(f"Took {nm}.", "normal")
                    taken_items.add(data)
                    options[choice] = f"(taken) {nm}"
                except Exception:
                    pass
            elif act == "extract_lodged":
                w = data
                lodged_items = {
                    "bullet": "rifle_ball", "shot": "shotgun_shell",
                    "arrowhead": "arrow",
                }
                item_id = lodged_items.get(w.lodged, "")
                if item_id:
                    try:
                        self.player.inventory.append(make_item(item_id))
                        self.add_message(f"Extracted {w.lodged} from {w.part}.", "normal")
                    except Exception:
                        pass
                w.lodged = ""
                options[choice] = f"(extracted) {w.part}"
            elif act == "butcher":
                break  # fall through to butcher code below
            self.advance_time(1)

        # ── Butcher path ──────────────────────────────────────────────
            # Generate loot based on NPC occupation
            rng = _rnd.Random(hash(npc.npc_id))
            loot = []
            cash_found = rng.uniform(0.50, 15.00)
            self.player.cash += cash_found
            loot_msgs = [f"${cash_found:.2f} in coins and dust"]

            # Occupation-based loot
            occ = (npc.occupation or "").lower()
            if "prospector" in occ or "miner" in occ:
                gold = rng.uniform(0.01, 0.15)
                self.player.gold_oz += gold
                loot_msgs.append(f"{gold:.3f} oz gold dust")
                if rng.random() < 0.4:
                    try:
                        loot.append(make_item("gold_pan"))
                    except Exception:
                        pass
            if "hunter" in occ or "trapper" in occ:
                if rng.random() < 0.5:
                    try:
                        loot.append(make_item("hunting_knife"))
                    except Exception:
                        pass
            if rng.random() < 0.3:
                try:
                    loot.append(make_item("hardtack"))
                except Exception:
                    pass
            if rng.random() < 0.2:
                try:
                    loot.append(make_item("whiskey"))
                except Exception:
                    pass
            # Weapon
            if rng.random() < 0.35:
                weapon_ids = ["percussion_revolver", "bowie_knife", "hunting_knife"]
                try:
                    loot.append(make_item(rng.choice(weapon_ids)))
                except Exception:
                    pass

            for item in loot:
                self.player.inventory.append(item)
                loot_msgs.append(item.name)

            self.add_message(
                f"You search {npc.name}'s body: {', '.join(loot_msgs)}.",
                "normal")
            # Recover lodged objects from wounds
            if hasattr(npc, 'wounds') and npc.wounds:
                for w in npc.wounds.wounds:
                    if w.lodged:
                        lodged_items = {
                            "bullet": ("rifle_ball", "Lead Ball"),
                            "shot": ("shotgun_shell", "Shotgun Pellets"),
                            "arrowhead": ("arrow", "Arrowhead"),
                            "knife": ("hunting_knife", "Lodged Blade"),
                        }
                        item_id, item_name = lodged_items.get(
                            w.lodged, ("", w.lodged))
                        if item_id:
                            try:
                                recovered = make_item(item_id)
                                self.player.inventory.append(recovered)
                                self.add_message(
                                    f"You dig out a {w.lodged} from the body.",
                                    "normal")
                            except Exception:
                                pass
                        w.lodged = ""
            self.advance_time(3)

            # Crime if witnessed
            witnesses = self._witnesses_near(
                self.player.local_x, self.player.local_y,
                exclude_id=npc.npc_id)
            if witnesses and npc.combat_state != "dead":
                lmap = self.current_local
                region = lmap._region_name if lmap else ""
                self.legal.record_crime(
                    "theft", self.time.total_minutes // 1440,
                    self.player.world_x, self.player.world_y, region,
                    nearby_npcs=witnesses)
            return

        # ── Butcher path ──────────────────────────────────────────────
        if npc.combat_state == "surrendered" or (npc.alive and npc.health < 25):
            # Killing a surrendered person
            confirm = pick_from_list(self._console, self._ctx,
                f"{npc.display_name()} is surrendered. Kill and butcher?",
                ["Yes — kill them", "No — let them go"])
            if confirm != 0:
                return
            npc.health = 0
            npc.alive = False
            npc.combat_state = "dead"
            self.add_message(f"You kill {npc.display_name()}.", "critical")
            # Crime
            lmap = self.current_local
            region = lmap._region_name if lmap else ""
            witnesses = self._witnesses_near(
                self.player.local_x, self.player.local_y,
                exclude_id=npc.npc_id)
            self.legal.record_crime(
                "murder", self.time.total_minutes // 1440,
                self.player.world_x, self.player.world_y, region,
                victim_name=npc.name, victim_npc_id=npc.npc_id,
                nearby_npcs=witnesses)
            self.reputation.adjust(region, -40)
            self._record_gossip(f"Murdered {npc.name} in cold blood", -1.0)

        if not has_sharp_tool(self.player):
            self.add_message(
                "You need a knife or axe to butcher.", "advisory")
            return

        method_labels = ["Quick (15 min)", "Normal (45 min)", "Extensive (90 min)"]
        idx = pick_from_list(self._console, self._ctx,
            f"Butcher {npc.display_name()}?", method_labels)
        if idx is None:
            return

        rng = _rnd.Random()
        time_costs = [15, 45, 90]

        # Human yields — medium-sized creature
        yields = []
        if idx >= 0:
            yields.append(Item(id="human_meat", name=f"{npc.name}'s Meat",
                weight=rng.uniform(3, 8), category="food",
                nutrition=30, perishable=True, days_until_spoil=2,
                base_value=0.0,
                description="Human flesh. Most people would find this abhorrent."))
        if idx >= 1:
            yields.append(Item(id="raw_hide", name=f"Human Skin",
                weight=5.0, category="material", base_value=0.0,
                description="Tanned human skin. Deeply disturbing to possess."))
            yields.append(Item(id="animal_bones", name=f"Human Bones",
                weight=4.0, category="material", base_value=0.0,
                description="Human skeletal remains."))
        if idx >= 2:
            yields.append(Item(id="tallow", name="Human Fat",
                weight=2.0, category="material", base_value=0.0))

        # Place on ground
        lmap = self.current_local
        tile = lmap.tile_at(npc.local_x, npc.local_y)
        for item in yields:
            tile.ground_items.append(item)

        # Remove NPC
        npc.present = False
        npc.alive = False

        self.add_message(
            f"You butcher {npc.name}. {len(yields)} items on the ground.",
            "critical")
        self.advance_time(time_costs[idx])
        self.player.gain_skill_xp("survival", 2.0)

        # Massive reputation hit — anyone who finds out
        region = self.current_local._region_name if self.current_local else ""
        self.reputation.adjust(region, -30)
        self._record_gossip(f"Butchered {npc.name}'s body", -1.0)

        # Crime if witnessed
        witnesses = self._witnesses_near(
            self.player.local_x, self.player.local_y)
        if witnesses:
            self.legal.record_crime(
                "murder", self.time.total_minutes // 1440,
                self.player.world_x, self.player.world_y, region,
                victim_name=npc.name, victim_npc_id=npc.npc_id,
                nearby_npcs=witnesses)

    def _pick_up_ground_items(self, tile):
        """Pick up all items from a ground tile into player inventory."""
        if not tile.ground_items:
            self.add_message("Nothing here.", "normal")
            return
        picked = list(tile.ground_items)
        tile.ground_items.clear()
        # Tag items as unpaid if inside a settlement (store goods)
        lmap = self.current_local
        in_settlement = hasattr(lmap, 'town_layout') and lmap.town_layout is not None
        for item in picked:
            if in_settlement:
                item.unpaid = True
            self.player.inventory.append(item)
        names = ", ".join(dict.fromkeys(i.name for i in picked[:4]))
        if len(picked) > 4:
            names += f" +{len(picked)-4} more"
        self.add_message(f"You pick up: {names}.", "normal")
        if self.player.overloaded:
            self.add_message(
                f"You're overloaded! ({self.player.carried_weight:.0f}/{self.player.carry_capacity:.0f} lb)",
                "advisory")

    def _open_throw(self):
        """[V] — select an item to throw, then select a target."""
        from src.menus import pick_from_list
        from src.wounds import throw_damage, throw_hit_chance, DamageType
        import random as _rnd

        if self.state != GameState.LOCAL_MAP:
            return

        throwables = [i for i in self.player.inventory
                      if getattr(i, "weight", 0) > 0]
        if not throwables:
            self.add_message("You have nothing to throw.", "normal")
            return

        labels = [f"{i.name} ({i.weight:.1f} lb)" for i in throwables]
        idx = pick_from_list(self._console, self._ctx,
                             "Throw what?", labels)
        if idx is None:
            return
        item = throwables[idx]
        dmg, dtype = throw_damage(item)

        # Build target list: NPCs + animals within 15 tiles
        npcs    = [n for n in self._tile_npcs()
                   if n.alive and n.present]
        animals = [a for a in self.wildlife_mgr.get_animals(
                        self.player.world_x, self.player.world_y,
                        self.player.area_x, self.player.area_y)
                   if a.alive]

        if not npcs and not animals:
            self.add_message("No targets in range.", "normal")
            return

        tgt_labels = (
            [f"{n.display_name()} (NPC)" for n in npcs] +
            [f"{a.species.display_name} (animal)" for a in animals]
        )
        tidx = pick_from_list(self._console, self._ctx,
                              "Throw at?", tgt_labels)
        if tidx is None:
            return

        # Resolve target and distance
        if tidx < len(npcs):
            target_npc  = npcs[tidx]
            target_animal = None
            dist = max(abs(target_npc.local_x - self.player.local_x),
                       abs(target_npc.local_y - self.player.local_y))
            size = "human"
        else:
            target_npc  = None
            target_animal = animals[tidx - len(npcs)]
            dist = max(abs(target_animal.local_x - self.player.local_x),
                       abs(target_animal.local_y - self.player.local_y))
            size = target_animal.species.size

        hit_chance = throw_hit_chance(self.player, dist, size)
        if _rnd.random() > hit_chance:
            self.add_message(
                f"You throw the {item.name} — it misses!", "normal")
        else:
            if target_npc:
                wound = target_npc.wounds.apply_hit(dmg, dtype)
                target_npc.health = max(0.0, target_npc.health - dmg)
                self.add_message(
                    f"You hit {target_npc.display_name()} with the {item.name}! "
                    f"{wound.description} ({dmg:.0f} dmg).", "advisory")
                if not target_npc.alive:
                    self.add_message(
                        f"{target_npc.display_name()} is killed.", "critical")
            else:
                target_animal.take_damage(dmg, dtype)
                sp = target_animal.species
                self.add_message(
                    f"You hit the {sp.display_name} with the {item.name}! "
                    f"({dmg:.0f} dmg).", "advisory")
                if target_animal.state == "dead":
                    self.add_message(
                        f"The {sp.display_name} drops. [P] to butcher.", "normal")
                elif target_animal.state == "downed":
                    self.add_message(
                        f"The {sp.display_name} goes down. [P] to butcher.", "normal")
                elif target_animal.state == "wounded_fleeing":
                    self.add_message(
                        f"The {sp.display_name} staggers away. Follow it.", "advisory")

        # Remove item from inventory (thrown items land on the target's tile or nearby)
        self.player.inventory.remove(item)
        if target_npc:
            lx, ly = target_npc.local_x, target_npc.local_y
        else:
            lx, ly = target_animal.local_x, target_animal.local_y
        lmap = self.current_local
        if lmap and lmap.in_bounds(lx, ly):
            lmap.tile_at(lx, ly).ground_items.append(item)

        self.player.gain_skill_xp("tracking", 1.0)
        self.advance_time(2)

    def _open_health(self):
        """[H] — full-screen health/wound status display."""
        import tcod.event as _ev

        console = self._console
        ctx     = self._ctx
        wounds  = self.player.wounds

        while True:
            console.clear()
            console.print(2, 1, "=== HEALTH STATUS ===", (220, 220, 220))

            lines = wounds.summary_lines()
            for row, (text, color) in enumerate(lines):
                if 3 + row >= console.height - 2:
                    break
                console.print(2, 3 + row, text, color)

            # Impairments from disabled parts
            console.print(2, console.height - 2,
                          "[Any key] Close", (120, 120, 120))
            ctx.present(console)

            for event in tcod.event.wait():
                if isinstance(event, (_ev.KeyDown, _ev.Quit)):
                    return

    def _examine_world_tile(self):
        """Show what the player can observe about the current world tile."""
        from src.world_map import (TERRAIN_NAME, TERRAIN_DESCRIPTION,
                                    TERRAIN_TRAVEL_MULT)
        from src.constants import WORLD_TRAVEL
        wx, wy = self.player.world_x, self.player.world_y
        if not self.world.in_bounds(wx, wy):
            return
        terrain = int(self.world.tiles[wy][wx])
        name = TERRAIN_NAME.get(terrain, "Unknown terrain")
        desc = TERRAIN_DESCRIPTION.get(terrain, "")
        view = MAP_LEVEL_NAMES.get(self.state, "")
        self.add_message(f"[{view}] {name} — {desc}", "normal")

        loc = self.world.get_location_at(wx, wy)
        if loc and loc.discovered:
            self.add_message(
                f"  {loc.name} ({loc.location_type}, pop. ~{loc.population:,})", "normal")

        cost = int(WORLD_TRAVEL * TERRAIN_TRAVEL_MULT.get(terrain, 1.0))
        self.add_message(
            f"  On foot: ~{cost//60}h{cost%60:02d}m per 5-mile tile  |  Pos: {wx},{wy}",
            "normal")

        # Geology hints if skilled
        geology = self.player.skills.get("geology", 0)
        from src.world_map import Terrain
        hints = {
            Terrain.MOUNTAINS: (1, "Hard-rock mineral veins possible in these peaks."),
            Terrain.RIVER:     (0, "Placer gold concentrates in bends and gravel bars."),
            Terrain.HILLS:     (2, "Mixed potential — outcrops worth sampling."),
            Terrain.PLAINS:    (3, "Low mineral potential. Good farmland, little ore."),
        }
        if terrain in hints:
            req, msg = hints[terrain]
            if geology >= req:
                self.add_message(f"  [Geology] {msg}", "advisory")

    def _open_journal(self):
        from src.ui_journal import open_journal
        result = open_journal(self._console, self._ctx, self.journal,
                               self.player, self.npc_mgr,
                               writing=self.writing,
                               current_day=self.time.total_minutes // 1440)
        if result and isinstance(result, tuple) and result[0] == "write":
            self._handle_write_action(result[1])

    def _handle_write_action(self, write_type: str):
        """Handle a write request from the journal Write tab."""
        p = self.player
        lit = p.skills.get("literacy", 0)
        intel = p.attributes.get("intelligence", 10)
        date = self.time.date_string

        if write_type == "diary":
            ok, msg = self.writing.write_diary(
                "A day's account.", p.name, date, lit, intel, p.inventory)
            self.add_message(msg, "advisory")
            if ok:
                self.journal.add_diary(date, "Wrote in journal.")
                from src.writing import grant_writing_xp, WorkType
                grant_writing_xp(p, WorkType.DIARY_ENTRY, 0.5)
                self.advance_time(10)

        elif write_type == "letter":
            self.add_message("(Letter writing requires post office — use custom action for now.)", "advisory")

        elif write_type in ("article", "poem", "skill_book", "sketch", "painting"):
            # These require the LLM or player text — route through action system
            self._resolve_action(f"write {write_type}")

        elif write_type == "book":
            if self.writing.book_in_progress:
                ok, msg = self.writing.write_chapter(
                    "Another chapter.", lit, intel, p.inventory)
                self.add_message(msg, "advisory")
                if ok:
                    from src.writing import grant_writing_xp, WorkType
                    grant_writing_xp(p, WorkType.BOOK, 0.5)
                    self.advance_time(240)
            else:
                self.add_message("Use custom action: 'start writing a book about [topic]'", "advisory")

    def _open_talk(self):
        if self.state != GameState.LOCAL_MAP:
            self.add_message("No one to talk to here.", "normal")
            return
        # Find nearest NPC within conversation range (6 tiles = 30ft)
        TALK_RANGE = 6
        px, py = self.player.local_x, self.player.local_y
        best_npc = None
        best_dist = TALK_RANGE + 1
        for n in self._tile_npcs():
            if not n.alive or not n.present:
                continue
            if n.combat_state == "dead":
                continue
            if getattr(n, 'local_z', 0) != self.player.local_z:
                continue
            dist = max(abs(n.local_x - px), abs(n.local_y - py))
            if dist <= TALK_RANGE and dist < best_dist:
                best_dist = dist
                best_npc = n
        npc = best_npc
        if not npc:
            self.add_message("There's no one nearby to talk to.", "normal")
            return
        from src.talk import talk_menu
        log = talk_menu(
            self._console, self._ctx, npc, self.player,
            llm=self.llm,
            world_map=self.world,
            journal=self.journal,
            date_str=self.time.date_string,
            companion_mgr=self.companion_mgr,
            current_minute=self.time.total_minutes,
            current_day=self.time.total_minutes // 1440,
            dynamic_locs=self.dynamic_locs,
            year=self.time.year,
            writing=self.writing,
            trade_engine=self.trade,
        )
        for line in log[-4:]:   # last 4 exchanges into message log
            self.add_message(line, "normal")
        self.advance_time(10)

    def _open_wait(self):
        from src.sleep import wait_menu, resolve_sleep
        minutes = wait_menu(self._console, self._ctx, self.player, self.time)
        if minutes is None:
            return
        has_bedroll  = any(i.id == "bedroll" for i in self.player.inventory)
        is_sheltered = self._nearby_structure("shelter", radius=2) is not None
        if minutes >= 60:
            result = resolve_sleep(self.player, minutes, is_sheltered, has_bedroll)
            quality = result["quality"]
            self.add_message(
                f"You rest for {minutes // 60}h {minutes % 60}m. "
                f"{quality.capitalize()} sleep. Fatigue restored.", "normal")
            # Autosave on full sleep
            if minutes >= 420:
                self._do_save()
                self.add_message("Game saved.", "normal")

        # Background simulation — NPCs act while player sleeps/rests
        # Nothing is shown to the player. Letters route through mail
        # system to nearest post office. Other events discovered later.
        if minutes >= 60:
            import random as _bg_rng
            days = max(1, minutes // 1440) if minutes >= 1440 else 1
            events = self.bg_sim.simulate(
                days, self.time.total_minutes // 1440,
                self._npc_gen.npcs, _bg_rng.Random())
            # Route letters through the mail system
            for evt in events:
                if evt.event_type == "letter":
                    # Find nearest town for delivery
                    from src.world_gen import era_locations
                    nearest_town = ""
                    best_dist = 9999
                    for loc in era_locations(self.time.year):
                        d = abs(loc.x - self.player.world_x) + abs(loc.y - self.player.world_y)
                        if d < best_dist and loc.loc_type in ("town", "city"):
                            best_dist = d
                            nearest_town = loc.name
                    if nearest_town:
                        self.writing.mail.send_letter(
                            sender=evt.npc_name,
                            recipient=self.player.name,
                            body=evt.description,
                            day=self.time.total_minutes // 1440,
                            origin=nearest_town,
                            destination=nearest_town,
                            distance_tiles=best_dist,
                            sender_npc_id=evt.npc_id,
                        )

        self.advance_time(minutes)

    def _open_help(self):
        """? key — controls and tips overlay."""
        con = self._console
        ctx = self._ctx
        from src.ui_framework import draw_box, WHITE, YELLOW, CYAN, GREY, DGREY, BG

        W, H = 60, 38
        X = (con.width - W) // 2
        Y = (con.height - H) // 2

        pages = [
            # Page 1: Getting Started
            [
                ("GETTING STARTED", YELLOW),
                ("", GREY),
                ("You are a prospector in the California Gold Rush.", WHITE),
                ("Pan for gold, sell it, survive. Everything else", WHITE),
                ("is up to you.", WHITE),
                ("", GREY),
                ("FIRST STEPS", YELLOW),
                ("1. You're standing near water (~). Walk to it.", WHITE),
                ("2. Press [A] and select 'Pan for gold'.", WHITE),
                ("3. If you see color, keep panning that spot.", WHITE),
                ("4. Find a town to sell your gold. [T] to talk", WHITE),
                ("   to a merchant, select 'Sell gold dust'.", WHITE),
                ("5. Buy food and supplies. Don't starve.", WHITE),
                ("", GREY),
                ("TERRAIN", YELLOW),
                (":  Gravel bar — pan here for gold", WHITE),
                ("~  Water — needed for panning and drinking", WHITE),
                ("^  Pine tree   T  Oak/other tree (blocks path)", WHITE),
                (".  Ground/grass   #  Rock (impassable)", WHITE),
                (";  Brush   o  Shallow pit   O  Deep pit", WHITE),
                ("=  Tailings (sluice waste)", WHITE),
                ("", GREY),
                ("Your gold and cash show in the right sidebar.", WHITE),
                ("Watch your hunger/thirst/fatigue bars.", WHITE),
            ],
            # Page 2: Controls
            [
                ("MOVEMENT & CONTROLS", YELLOW),
                ("", GREY),
                ("Arrow keys / Numpad   Move on local map", WHITE),
                ("< >                   Z-level up/down", WHITE),
                ("[ ]                   Zoom out/in (world map)", WHITE),
                ("Enter                 Fast travel (zoomed out)", WHITE),
                ("Space                 Wait / Rest / Sleep", WHITE),
                ("Esc                   Pause menu / Exit mode", WHITE),
                ("", GREY),
                ("MENUS", YELLOW),
                ("I  Inventory (items, clothing, equip)", CYAN),
                ("C  Character (stats, health, wounds)", CYAN),
                ("J  Journal (diary, rumors, places, mail, AAR)", CYAN),
                ("A  Actions (pan, dig, eat, drink, custom)", CYAN),
                ("T  Talk (conversation, trade, hire)", CYAN),
                ("B  Build (structures, walls, zones)", CYAN),
                ("E  Examine (look at surroundings)", CYAN),
                ("P  Pickup items / Butcher", CYAN),
                ("L  Message log (scroll history)", CYAN),
                ("G  Gold overlay (panned tile grades)", CYAN),
                ("S  Cycle stance  |  W  Cycle speed", CYAN),
                ("Ctrl+S  Save game", CYAN),
            ],
            # Page 3: Work Modes
            [
                ("WORK MODES", YELLOW),
                ("", GREY),
                ("MINING MODE [M]", CYAN),
                ("Near water + pan: enter pan mode.", WHITE),
                ("  SPACE = pan one cycle", WHITE),
                ("  Arrows = move to test different spots", WHITE),
                ("  ESC = stop, see session totals", WHITE),
                ("Near sluice + shovel + water: sluice mode.", WHITE),
                ("  SPACE = shovel a load into sluice", WHITE),
                ("  ENTER = clean out (recover all gold)", WHITE),
                ("", GREY),
                ("HUNTING MODE [H]", CYAN),
                ("  Arrows = sneak (quiet, slower)", WHITE),
                ("  F = fire at target", WHITE),
                ("  TAB = cycle between animals", WHITE),
                ("  SPACE = wait/watch", WHITE),
                ("  Tracking skill shows tracks + directions", WHITE),
                ("", GREY),
                ("GAMBLING (type 'gamble' or 'cards')", CYAN),
                ("  Poker, Blackjack, Faro (1840s card game)", WHITE),
                ("  Buy a card table to run your own games", WHITE),
                ("  Cheat with marked cards (risky)", WHITE),
            ],
            # Page 4: Combat
            [
                ("COMBAT", YELLOW),
                ("", GREY),
                ("Combat mode auto-enters when hostiles attack.", WHITE),
                ("Red 'IN COMBAT' banner appears.", WHITE),
                ("", GREY),
                ("COMBAT KEYS", CYAN),
                ("  F = Snap shot (3 sec, normal accuracy)", WHITE),
                ("  G = Careful aim (10 sec, +25% accuracy)", WHITE),
                ("  R = Reload weapon", WHITE),
                ("  TAB = Cycle targets", WHITE),
                ("  1-5 = Aim body part:", WHITE),
                ("    1=Center  2=Head  3=Legs  4=Arms  5=Torso", WHITE),
                ("  SPACE = Wait (enemies act, you don't)", WHITE),
                ("  V = Free look (snap camera to target)", WHITE),
                ("  ESC = Exit combat (access menus)", WHITE),
                ("", GREY),
                ("COVER", YELLOW),
                ("Stand near trees/rocks for partial cover (-4", WHITE),
                ("to enemy hit). Behind boulders = full cover.", WHITE),
                ("NPCs seek cover when wounded.", WHITE),
                ("Sidebar shows: EXPOSED / Partial / FULL", WHITE),
                ("", GREY),
                ("Firearms are LETHAL. One rifle shot can kill.", WHITE),
                ("Extremity wounds bleed you out over minutes.", WHITE),
            ],
            # Page 5: Survival & Economy
            [
                ("SURVIVAL", YELLOW),
                ("", GREY),
                ("Hunger/Thirst/Fatigue drain with time.", WHITE),
                ("Eat food and drink water regularly.", WHITE),
                ("Sleep to restore fatigue (Space → Rest).", WHITE),
                ("  0 hunger = 1 HP/hour damage", WHITE),
                ("  0 thirst = 3 HP/hour damage", WHITE),
                ("Carry a canteen. Fill at streams.", WHITE),
                ("Weight matters — overloaded = slow movement.", WHITE),
                ("", GREY),
                ("ECONOMY", YELLOW),
                ("Pan gold → sell to merchants in town [T].", WHITE),
                ("Gold price: $20.67/oz (1849 fixed price).", WHITE),
                ("Merchants lowball you. Better merchants pay", WHITE),
                ("closer to true value.", WHITE),
                ("Buy supplies, weapons, tools from merchants.", WHITE),
                ("", GREY),
                ("CRIMES", YELLOW),
                ("Witnesses within 200ft report crimes.", WHITE),
                ("At night, witness range drops to 75ft.", WHITE),
                ("Stealing: pick up items in a store, leave.", WHITE),
                ("Murder, assault, theft, fraud all tracked.", WHITE),
                ("Reputation affects NPC attitudes.", WHITE),
            ],
            # Page 6: Advanced
            [
                ("ADVANCED", YELLOW),
                ("", GREY),
                ("CUSTOM ACTIONS", CYAN),
                ("Press [A] and type ANYTHING. The AI resolves", WHITE),
                ("it. 'climb the tree', 'set a snare', 'write", WHITE),
                ("a letter home', 'build a still'. If you have", WHITE),
                ("the tools and materials, it can happen.", WHITE),
                ("", GREY),
                ("WORLD MAP", CYAN),
                ("[ zoom out, ] zoom in. 5 zoom levels.", WHITE),
                ("Enter on any tile = fast travel there.", WHITE),
                ("Compass in sidebar shows nearest town.", WHITE),
                ("", GREY),
                ("PROSPECTING TIPS", CYAN),
                ("Gravel bars on inside bends = best gold.", WHITE),
                ("Bedrock crevices trap heavy gold.", WHITE),
                ("Dig deeper for richer pay layers.", WHITE),
                ("Build sluice for 6x throughput vs hand pan.", WHITE),
                ("Geology skill reveals ground quality.", WHITE),
                ("Ground depletes — move to new spots.", WHITE),
                ("", GREY),
                ("RUMORS", CYAN),
                ("Ask NPCs [T] about rumors. They point you", WHITE),
                ("to gold, bandits, bounties, lost travelers,", WHITE),
                ("abandoned claims, and more.", WHITE),
            ],
        ]

        page = 0
        while True:
            draw_box(con, X, Y, W, H, f"HELP  —  Page {page + 1}/{len(pages)}")
            for i, (text, color) in enumerate(pages[page]):
                if i + 2 >= H - 2:
                    break
                con.print(X + 2, Y + 2 + i, text[:W - 4], fg=color, bg=BG)
            con.print(X + 2, Y + H - 2,
                      f"[</>] Page  [Esc] Close    {page+1}/{len(pages)}",
                      fg=DGREY, bg=BG)
            ctx.present(con)
            for event in tcod.event.wait():
                if isinstance(event, tcod.event.KeyDown):
                    sym = event.sym
                    K = tcod.event.KeySym
                    if sym == K.ESCAPE:
                        return
                    if sym in (K.RIGHT, K.PERIOD, K.DOWN):
                        page = min(page + 1, len(pages) - 1)
                    elif sym in (K.LEFT, K.COMMA, K.UP):
                        page = max(page - 1, 0)
                    else:
                        return
                    break

    def _open_pause_menu(self) -> str:
        """ESC pause menu with settings and quit."""
        con = self._console
        ctx = self._ctx
        from src.ui_framework import draw_box, WHITE, YELLOW, CYAN, GREY, DGREY, BG, BG_SEL
        K = tcod.event.KeySym

        W, H = 40, 18
        X = (con.width - W) // 2
        Y = (con.height - H) // 2
        selected = 0

        options = [
            "Resume",
            "Save Game",
            f"Music Volume: {int(self.music.volume * 100)}%",
            f"Music: {'ON' if self.music.enabled else 'OFF'}",
            "Quit to Desktop",
        ]

        while True:
            # Rebuild volume display
            options[2] = f"Music Volume: {int(self.music.volume * 100)}%"
            options[3] = f"Music: {'ON' if self.music.enabled else 'OFF'}"

            draw_box(con, X, Y, W, H, "PAUSED")

            for i, opt in enumerate(options):
                sel = (i == selected)
                fg = CYAN if sel else WHITE
                bg = BG_SEL if sel else BG
                marker = ">" if sel else " "
                con.print(X + 2, Y + 3 + i * 2, f"{marker} {opt}", fg=fg, bg=bg)

            # Volume bar
            vol_y = Y + 3 + 2 * 2 + 1
            bar_len = int(self.music.volume * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            con.print(X + 4, vol_y, f"  [{bar}]", fg=GREY, bg=BG)

            # Now playing
            status = self.music.status_line()
            con.print(X + 2, Y + H - 3, status[:W - 4], fg=DGREY, bg=BG)

            con.print(X + 2, Y + H - 2, "↑↓ Select  ←→ Volume  Enter Confirm",
                      fg=DGREY, bg=BG)
            ctx.present(con)

            for event in tcod.event.wait():
                if isinstance(event, tcod.event.Quit):
                    return "quit"
                if not isinstance(event, tcod.event.KeyDown):
                    continue
                sym = event.sym

                if sym == K.ESCAPE:
                    return "resume"
                if sym in (K.UP, K.KP_8):
                    selected = (selected - 1) % len(options)
                if sym in (K.DOWN, K.KP_2):
                    selected = (selected + 1) % len(options)

                # Volume adjustment with left/right when on volume row
                if selected == 2 and sym in (K.LEFT, K.KP_4):
                    self.music.volume_down(0.05)
                if selected == 2 and sym in (K.RIGHT, K.KP_6):
                    self.music.volume_up(0.05)

                if sym in (K.RETURN, K.KP_ENTER):
                    if selected == 0:
                        return "resume"
                    elif selected == 1:
                        self._do_save()
                        self.add_message("Game saved.", "normal")
                    elif selected == 2:
                        pass  # volume adjusted with left/right
                    elif selected == 3:
                        self.music.toggle_mute()
                    elif selected == 4:
                        self._do_save()
                        return "quit"

    def _do_save(self):
        from src.save_load import save_game
        path = save_game(self, slot="autosave")
        self.add_message(f"Saved.", "normal")

    def _open_log_viewer(self):
        """L — scrollable full message history."""
        con = self._console
        ctx = self._ctx
        from src.menus import draw_box

        W = min(SCREEN_WIDTH - 4, 100)
        H = SCREEN_HEIGHT - 4
        X = (SCREEN_WIDTH  - W) // 2
        Y = (SCREEN_HEIGHT - H) // 2

        colors = {"normal": (255, 255, 255),
                  "advisory": (255, 220, 60),
                  "critical": (220, 50, 50)}
        max_w = W - 4

        # Pre-wrap all messages once
        wrapped = []
        for text, severity in self.messages:
            color = colors.get(severity, (255, 255, 255))
            line = ""
            for word in text.split():
                test = (line + " " + word).strip()
                if len(test) <= max_w:
                    line = test
                else:
                    if line:
                        wrapped.append((line, color))
                    while len(word) > max_w:
                        wrapped.append((word[:max_w], color))
                        word = word[max_w:]
                    line = word
            if line:
                wrapped.append((line, color))

        view_h  = H - 4
        total   = len(wrapped)
        scroll  = max(0, total - view_h)   # start at bottom

        while True:
            scroll = max(0, min(scroll, max(0, total - view_h)))
            draw_box(con, X, Y, W, H, "Message Log")
            con.draw_rect(X + 1, Y + 2, W - 2, view_h,
                          ord(" "), fg=(255, 255, 255), bg=(10, 10, 20))

            visible = wrapped[scroll: scroll + view_h]
            for i, (line, color) in enumerate(visible):
                con.print(X + 2, Y + 2 + i, line, fg=color, bg=(10, 10, 20))

            lo = scroll + 1
            hi = min(scroll + view_h, total)
            footer = (f"[↑↓] scroll  [PgUp/PgDn] page  "
                      f"[Home/End]  [Esc] close    {lo}-{hi}/{total}")
            con.print(X + 2, Y + H - 2, footer[:W - 4],
                      fg=(100, 100, 100), bg=(10, 10, 20))
            ctx.present(con)

            for event in tcod.event.wait():
                if isinstance(event, tcod.event.Quit):
                    return
                if isinstance(event, tcod.event.KeyDown):
                    sym = event.sym
                    K   = tcod.event.KeySym
                    if sym == tcod.event.KeySym.ESCAPE:
                        return
                    elif sym in (tcod.event.KeySym.UP, tcod.event.KeySym.KP_8):
                        scroll -= 1
                    elif sym in (tcod.event.KeySym.DOWN, tcod.event.KeySym.KP_2):
                        scroll += 1
                    elif sym == tcod.event.KeySym.PAGEUP:
                        scroll -= view_h
                    elif sym == tcod.event.KeySym.PAGEDOWN:
                        scroll += view_h
                    elif sym == tcod.event.KeySym.HOME:
                        scroll = 0
                    elif sym == tcod.event.KeySym.END:
                        scroll = max(0, total - view_h)

    def _open_actions(self):
        if self.state != GameState.LOCAL_MAP:
            self.add_message("Actions are only available on the local map.", "normal")
            return
        from src.action_menu import open_action_menu
        ctx_actions = self._get_context_actions_nearby()
        result = open_action_menu(self._console, self._ctx,
                                   self.action_history,
                                   context_actions=ctx_actions)
        if result:
            self._resolve_action(result)

    def _get_context_actions_nearby(self) -> list:
        """Build context-sensitive action list based on what's near the player."""
        actions = []
        lmap = self.current_local
        if not lmap:
            return actions
        from src.local_map import LocalTerrain

        px, py = self.player.local_x, self.player.local_y
        tile = lmap.tile_at(px, py)

        # Near water?
        near_water = False
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                nx, ny = px + dx, py + dy
                if lmap.in_bounds(nx, ny) and lmap.tile_at(nx, ny).terrain == LocalTerrain.WATER:
                    near_water = True
                    break
            if near_water:
                break

        if near_water:
            actions.append("Fill canteen")
            actions.append("Fish")

        # On pannable ground?
        PANNABLE = (LocalTerrain.GRAVEL_BAR, LocalTerrain.SAND,
                    LocalTerrain.MUD, LocalTerrain.BEDROCK,
                    LocalTerrain.WORKED_GRAVEL, LocalTerrain.WORKED_DIRT,
                    LocalTerrain.SPOIL_PILE)
        if tile.terrain in PANNABLE:
            actions.append("Pan for gold")
            if near_water:
                actions.append("Load pan from here")

        # Near structures?
        fire = self._nearby_structure("cook", radius=2)
        if fire:
            actions.append("Cook food")

        sluice = self._nearby_structure("pan_gold", radius=3)
        if sluice:
            if "sluice" in sluice.name.lower():
                actions.append("Work the sluice")
            else:
                actions.append("Work the rocker")

        shelter = self._nearby_structure("shelter", radius=2)
        if shelter:
            actions.append("Rest here")

        # Near NPCs? (6 tiles = 30ft conversation range)
        nearby_npcs = [n for n in self._tile_npcs()
                       if n.alive and max(abs(n.local_x - px), abs(n.local_y - py)) <= 6]
        if nearby_npcs:
            actions.append("Talk to nearby person")
            # Check if any nearby NPC is at a gambling location
            for n in nearby_npcs:
                if any(w in getattr(n, 'occupation', '').lower()
                       for w in ('bartender', 'gambler')):
                    actions.append("Gamble (cards)")
                    break

        # Dead animals nearby?
        animals = self.wildlife_mgr.get_animals(
            self.player.world_x, self.player.world_y,
            self.player.area_x, self.player.area_y)
        for a in animals:
            if (a.recoverable and
                max(abs(a.local_x - px), abs(a.local_y - py)) <= 1 and
                getattr(a, "local_z", 0) == self.player.local_z):
                actions.append(f"Butcher {a.species.display_name}")
                break

        # Items on ground?
        if tile.ground_items:
            actions.append("Pick up items")

        return actions

    def _resolve_action(self, action: str):
        """
        Route a chosen/typed action to the right system.
        Actions are never blocked — terrain and tools shape the outcome.
        """
        from src.local_map import LocalTerrain
        a = action.lower().strip()
        self.add_message(f"> {action}", "normal")

        lmap = self.current_local
        tile = lmap.tile_at(self.player.local_x, self.player.local_y)

        # ── Helper: is there water within 3 tiles? ───────────────────────
        def _near_water() -> bool:
            for dy in range(-3, 4):
                for dx in range(-3, 4):
                    nx, ny = self.player.local_x + dx, self.player.local_y + dy
                    if lmap.in_bounds(nx, ny) and \
                       lmap.tile_at(nx, ny).terrain == LocalTerrain.WATER:
                        return True
            return False

        # ── Soft material at current tile? ────────────────────────────────
        SOFT = (LocalTerrain.GROUND, LocalTerrain.GRASS, LocalTerrain.MUD,
                LocalTerrain.GRAVEL_BAR, LocalTerrain.SAND, LocalTerrain.BEDROCK,
                LocalTerrain.PIT, LocalTerrain.SPOIL_PILE)

        # ── Gambling ──────────────────────────────────────────────────────
        if any(w in a for w in ("gamble", "poker", "cards", "faro", "blackjack",
                                "twenty-one", "play cards", "card game")):
            from src.gambling_mode import enter_gambling_mode
            enter_gambling_mode(self, self._console, self._ctx)
            return

        # ── Hidden action: scalp (not in any menu, must be typed) ─────────
        if "scalp" in a:
            # Find a dead or incapacitated NPC or animal nearby
            px, py = self.player.local_x, self.player.local_y
            victim = None
            victim_name = ""
            for n in self._tile_npcs():
                if n.combat_state in ("dead", "surrendered") and max(abs(n.local_x - px), abs(n.local_y - py)) <= 2:
                    victim = n
                    victim_name = n.name
                    break
            # Also check downed NPCs (health < 25, not fleeing)
            if not victim:
                for n in self._tile_npcs():
                    if n.health < 25 and n.alive and max(abs(n.local_x - px), abs(n.local_y - py)) <= 2:
                        victim = n
                        victim_name = n.name
                        break
            if not victim:
                for a_obj in self.wildlife_mgr.get_animals(
                        self.player.world_x, self.player.world_y,
                        self.player.area_x, self.player.area_y):
                    if a_obj.state in ("dead", "downed") and max(abs(a_obj.local_x - px), abs(a_obj.local_y - py)) <= 2:
                        victim = a_obj
                        victim_name = a_obj.species.display_name
                        break
            if not victim:
                self.add_message("There's nobody dead close enough to... do that to.", "advisory")
                return
            # Need a blade
            has_blade = any(t in getattr(i, "tool_tags", []) for i in self.player.inventory
                           for t in ("cut", "butcher", "skin"))
            if not has_blade:
                self.add_message("You'd need a knife for that.", "advisory")
                return
            # Do the deed
            import random as _sc_rng
            from src.items import Item
            self.advance_time(5)
            scalp_item = Item(
                id="scalp", name=f"Scalp of {victim_name}",
                weight=0.1, category="remains",
                description=f"A human scalp taken from {victim_name}. Gruesome trophy.",
                base_value=0.0,
            )
            self.player.inventory.append(scalp_item)
            self._splatter_blood(lmap, px, py, 2)

            msgs = [
                f"You kneel beside {victim_name}'s body. The knife does its work. "
                f"You pull the scalp free with a wet sound and tuck it away.",
                f"You grab a fistful of hair and draw the blade across. "
                f"It comes away in one piece. Blood runs down your wrist.",
                f"You work the knife around the hairline. It takes longer than "
                f"you expected. The result is a ragged, bloody trophy.",
            ]
            self.add_message(_sc_rng.choice(msgs), "normal")

            # Witnesses react with extreme horror
            witnesses = self._witnesses_near(px, py)
            if witnesses:
                region = lmap._region_name if lmap else ""
                self.legal.record_crime(
                    "murder", self.time.total_minutes // 1440,
                    self.player.world_x, self.player.world_y, region,
                    nearby_npcs=witnesses)
                for w in witnesses:
                    w.combat_state = "fleeing"
                    w.adjust_relationship(-50)
                self.add_message(
                    "The witnesses stare in horror. They will never forget this.",
                    "critical")
                self.reputation.adjust(region, -60)
                self._record_gossip(f"Scalped {victim_name} like a savage", -1.0)
            else:
                self.add_message("Nobody saw. But you know what you did.", "advisory")

            self.player.gain_skill_xp("survival", 2.0)
            return

        # ── Reload firearm ────────────────────────────────────────────────
        if "reload" in a or ("load" in a and any(w in a for w in
                ("gun", "rifle", "revolver", "pistol", "shotgun", "firearm"))):
            firearm = None
            for item in self.player.inventory:
                if item.weapon_type == "firearm":
                    firearm = item
                    break
            if not firearm:
                self.add_message("You don't have a firearm.", "advisory")
                self.advance_time(2)
                return
            ammo_type = firearm.extra.get("ammo_type", "")
            capacity = firearm.extra.get("capacity", 1)
            loaded = firearm.extra.get("loaded", 0)
            if isinstance(loaded, bool):
                loaded = 1 if loaded else 0
            if loaded >= capacity:
                self.add_message(f"{firearm.name} is fully loaded.", "advisory")
                self.advance_time(1)
                return
            ammo_item = None
            for item in self.player.inventory:
                if item.id == ammo_type:
                    ammo_item = item
                    break
            if not ammo_item:
                self.add_message(
                    f"No {ammo_type.replace('_', ' ')} in your pack.", "advisory")
                self.advance_time(2)
                return
            rounds = min(capacity - loaded, getattr(ammo_item, "quantity", 1))
            firearm.extra["loaded"] = loaded + rounds
            if ammo_item.stackable and ammo_item.quantity > rounds:
                ammo_item.quantity -= rounds
            else:
                self.player.inventory.remove(ammo_item)
            self.advance_time(firearm.extra.get("reload_time", 30))
            self.player.gain_skill_xp("firearms", 0.5)
            self.add_message(
                f"Loaded {rounds} round{'s' if rounds > 1 else ''} into "
                f"{firearm.name}. ({firearm.extra['loaded']}/{capacity})", "normal")
            return

        # ── Fill canteen ──────────────────────────────────────────────────
        if "fill" in a and "canteen" in a:
            canteen = None
            for item in self.player.inventory:
                if item.id == "canteen":
                    canteen = item
                    break
            if not canteen:
                self.add_message("You don't have a canteen.", "advisory")
                self.advance_time(2)
                return
            if canteen.extra.get("filled"):
                self.add_message("Your canteen is already full.", "advisory")
                self.advance_time(1)
                return
            if _near_water():
                canteen.extra["filled"] = True
                canteen.extra["contents"] = "water"
                self.add_message("You kneel by the water and fill your canteen.", "normal")
                self.advance_time(5)
            else:
                self.add_message("There's no water nearby to fill from.", "advisory")
                self.advance_time(2)
            return

        # ── Bandage wounds ───────────────────────────────────────────────
        if "bandage" in a:
            result = self.player.wounds.bandage_worst()
            if result:
                self.add_message(result, "normal")
                self.player.gain_skill_xp("firstAid", 2.0)
                self.advance_time(10)
            else:
                self.add_message("No open wounds to bandage.", "advisory")
                self.advance_time(2)
            return

        # ── Extract lodged object ─────────────────────────────────────────
        if "extract" in a or "remove bullet" in a or "dig out" in a or "pull out" in a:
            lodged_wounds = [w for w in self.player.wounds.wounds if w.lodged]
            if not lodged_wounds:
                self.add_message("No lodged objects in your wounds.", "advisory")
                return
            from src.menus import pick_from_list
            labels = [f"{w.lodged} in {w.part} ({w.severity})" for w in lodged_wounds]
            idx = pick_from_list(self._console, self._ctx, "Extract what?", labels)
            if idx is None:
                return
            wound = lodged_wounds[idx]
            # Skill check: firstAid
            import random as _ext_rng
            skill = self.player.skills.get("firstAid", 0)
            roll = _ext_rng.randint(1, 20) + skill // 2
            self.advance_time(15)
            if roll >= 10:
                from src.items import make_item
                lodged_items = {
                    "bullet": "rifle_ball", "shot": "shotgun_shell",
                    "arrowhead": "arrow",
                }
                item_id = lodged_items.get(wound.lodged, "")
                if item_id:
                    try:
                        self.player.inventory.append(make_item(item_id))
                    except Exception:
                        pass
                self.add_message(
                    f"You extract the {wound.lodged} from your {wound.part}. "
                    f"Painful but it's out.", "normal")
                wound.lodged = ""
                wound.bleed_rate *= 1.3  # extraction reopens bleeding
                self.player.gain_skill_xp("firstAid", 5.0)
            else:
                self.player.survival.health -= 3
                self.add_message(
                    f"You dig for the {wound.lodged} but can't get it. "
                    f"The wound bleeds more.", "critical")
                wound.bleed_rate *= 1.5
                self.player.gain_skill_xp("firstAid", 2.0)
            return

        # ── Check wounds ─────────────────────────────────────────────────
        if "check wound" in a or "examine wound" in a:
            if not self.player.wounds.wounds:
                self.add_message("You have no injuries.", "normal")
            else:
                from src.health_system import describe_wound
                skill = self.player.skills.get("firstAid", 0)
                intel = self.player.attributes.get("intelligence", 10)
                for w in self.player.wounds.wounds:
                    desc = describe_wound(w, skill, intel)
                    self.add_message(f"  {desc}", "advisory")
            self.advance_time(5)
            return

        # ── Cook food (requires nearby campfire/fireplace) ─────────────
        if "cook" in a:
            fire = self._nearby_structure("cook", radius=2)
            if not fire:
                self.add_message("You need a campfire or fireplace nearby to cook.", "advisory")
                self.advance_time(2)
                return
            # Find raw/cookable food in inventory
            raw_food = [i for i in self.player.inventory
                        if i.is_food() and i.extra.get("requires_cooking")]
            raw_meat = [i for i in self.player.inventory
                        if i.is_food() and "fresh" in i.name.lower()]
            cookable = raw_food + raw_meat
            if not cookable:
                self.add_message("You have nothing that needs cooking.", "advisory")
                self.advance_time(2)
                return
            from src.menus import pick_from_list
            names = [f"{i.display_name()} ({i.nutrition:.0f} nut)" for i in cookable]
            cidx = pick_from_list(self._console, self._ctx, "Cook what?", names)
            if cidx is None:
                return
            item = cookable[cidx]
            # Convert to cooked version
            from src.items import Item
            cooked = Item(
                id="cooked_" + item.id, name=f"Cooked {item.name}",
                weight=item.weight * 0.8, category="food",
                nutrition=item.nutrition * 1.4,  # cooking increases nutrition
                perishable=True, days_until_spoil=3,
                base_value=item.base_value * 2,
                description=f"Well-cooked {item.name.lower()}. Hot and filling.",
            )
            # Remove raw, add cooked
            if item.stackable and item.quantity > 1:
                item.quantity -= 1
            else:
                self.player.inventory.remove(item)
            self.player.inventory.append(cooked)
            self.add_message(f"You cook the {item.name} over the fire. Smells good.", "normal")
            self.player.gain_skill_xp("survival", 1.5)
            self.advance_time(20)
            return

        # ── Eat / Drink ───────────────────────────────────────────────────
        if ("eat" in a and ("food" in a or "meal" in a)) or a == "eat":
            food = sorted(
                [i for i in self.player.inventory if i.is_food()],
                key=lambda i: i.days_until_spoil if i.days_until_spoil is not None else 9999)
            if not food:
                self.add_message("You have nothing to eat.", "advisory")
                self.advance_time(2)
                return
            item = food[0]  # eat most perishable first
            self.player.survival.eat(item.nutrition)
            self.add_message(f"You eat the {item.name}. Hunger restored.", "normal")
            if item.stackable and item.quantity > 1:
                item.quantity -= 1
            else:
                self.player.inventory.remove(item)
            self.advance_time(10)
            return

        if ("drink" in a and "water" in a) or a == "drink":
            # Check canteen first, then water items
            drink = None
            for i in self.player.inventory:
                if i.is_drink():
                    drink = i
                    break
                if i.id == "canteen" and i.extra.get("filled"):
                    drink = i
                    break
            if not drink:
                if _near_water():
                    self.player.survival.drink(20)
                    self.add_message("You drink from the stream.", "normal")
                    self.advance_time(5)
                    return
                self.add_message("You have nothing to drink and no water nearby.", "advisory")
                self.advance_time(2)
                return
            if drink.id == "canteen":
                self.player.survival.drink(25)
                drink.extra["filled"] = False
                self.add_message("You drink from your canteen.", "normal")
            else:
                self.player.survival.drink(drink.hydration)
                self.add_message(f"You drink the {drink.name}.", "normal")
                if drink.stackable and drink.quantity > 1:
                    drink.quantity -= 1
                else:
                    self.player.inventory.remove(drink)
            self.advance_time(5)
            return

        # ── Throw ────────────────────────────────────────────────────────
        if "throw" in a:
            throwable = [i for i in self.player.inventory if i.weight < 10]
            if not throwable:
                self.add_message("Nothing light enough to throw.", "advisory")
                self.advance_time(2)
                return
            from src.menus import pick_from_list
            names = [i.display_name() for i in throwable]
            idx = pick_from_list(self._console, self._ctx, "Throw what?", names)
            if idx is None or idx < 0:
                return
            item = throwable[idx]
            # Find target
            targets = [(n.name, n) for n in self._tile_npcs()
                       if n.alive and n.present]
            if not targets:
                self.add_message("Nothing to throw at.", "advisory")
                return
            target_names = [t[0] for t in targets]
            tidx = pick_from_list(self._console, self._ctx, "Throw at?", target_names)
            if tidx is None or tidx < 0:
                return
            _, target_npc = targets[tidx]
            # Resolve
            from src.wounds import throw_damage, throw_hit_chance
            import random as _throw_rng
            dist = abs(target_npc.local_x - self.player.local_x) + \
                   abs(target_npc.local_y - self.player.local_y)
            hit_chance = throw_hit_chance(self.player, dist)
            dmg, dtype = throw_damage(item)
            if _throw_rng.random() < hit_chance:
                wound = target_npc.wounds.apply_hit(dmg, dtype)
                target_npc.health = max(0, target_npc.health - dmg)
                self.add_message(
                    f"You throw the {item.name} at {target_npc.name} — hit! "
                    f"({dmg:.0f} dmg, {wound.description})", "normal")
                if target_npc.combat_state == "neutral":
                    target_npc.combat_state = "hostile"
            else:
                self.add_message(
                    f"You throw the {item.name} at {target_npc.name} — miss!",
                    "normal")
            # Item lands on the ground
            self.player.inventory.remove(item)
            lmap.tile_at(target_npc.local_x, target_npc.local_y).ground_items.append(item)
            self.player.gain_skill_xp("tracking", 1.0)
            self.advance_time(3)
            return

        # ── Panning ───────────────────────────────────────────────────────
        if "pan" in a and ("gold" in a or "crevice" in a or "bedrock" in a):
            has_pan = any("pan" in getattr(i, "tool_tags", [])
                          for i in self.player.inventory)
            if not has_pan:
                self.add_message(
                    "You don't have a pan. You need a gold pan to wash material.", "advisory")
                self.advance_time(2)
                return

            if _near_water():
                # Full wet-pan cycle (hand panning)
                import random as _rnd
                from src.prospecting import pan_for_gold, depletion_message
                from src.nugget_system import NuggetSystem
                from src.volume_gold import VolumeGoldSystem

                # Determine which tile we're actually panning material FROM
                if self.player.pan_loaded and self.player.pan_source_x >= 0:
                    # Washing pre-loaded material from a different tile
                    src_x = self.player.pan_source_x
                    src_y = self.player.pan_source_y
                    src_tile = lmap.tile_at(src_x, src_y) if lmap.in_bounds(src_x, src_y) else tile
                    prefix = f"You wash the loaded pan (material from {src_x},{src_y}). "
                else:
                    # Panning the tile we're standing on
                    src_tile = tile
                    src_x, src_y = self.player.local_x, self.player.local_y
                    prefix = ""

                # Lazy column creation on the SOURCE tile
                if src_tile.gold_column is None:
                    _col_bias = max(src_tile.gold_grade, lmap._gold_bias * 0.5)
                    _col_rng = _rnd.Random(lmap.seed + src_x * 100 + src_y)
                    src_tile.gold_column = VolumeGoldSystem.create_column(
                        lmap._region_name, _col_bias, _col_rng)
                # Track grade before panning for depletion feedback
                grade_before = src_tile.gold_grade if src_tile.panned else -1.0
                # Sync surface grade from column at current dig depth
                src_tile.gold_grade = max(src_tile.gold_column.get_current_grade(), 0.001)
                # Volumetric depletion on SOURCE tile
                VolumeGoldSystem.pan_volume(
                    src_tile.gold_column,
                    placer_skill=self.player.skills.get("placer", 0))
                # Temporarily set current tile's grade to source grade for pan_for_gold
                saved_grade = tile.gold_grade
                tile.gold_grade = src_tile.gold_grade
                result = pan_for_gold(self.player, lmap)
                tile.gold_grade = saved_grade  # restore
                self.player.pan_loaded = False
                self.player.pan_source_x = -1
                self.player.pan_source_y = -1
                self.player.gain_skill_xp("placer",  result.xp_placer)
                self.player.gain_skill_xp("geology", result.xp_geology)
                self.player.gold_oz += result.gold_oz
                # Significant find = reputation boost
                if result.gold_oz > 0.05:
                    self.reputation.adjust(lmap._region_name, 3)
                src_tile.panned = True
                # Visual terrain change on source tile
                if src_tile.terrain == LocalTerrain.GRAVEL_BAR:
                    src_tile.terrain = LocalTerrain.WORKED_GRAVEL
                elif src_tile.terrain in (LocalTerrain.GROUND, LocalTerrain.GRASS,
                                          LocalTerrain.MUD, LocalTerrain.SAND):
                    src_tile.terrain = LocalTerrain.WORKED_DIRT
                lmap.invalidate_terrain_cache()
                self.advance_time(result.time_minutes)
                self.add_message(prefix + result.message, "normal")
                # Depletion feedback — warn when ground is thinning
                if grade_before > 0:
                    dep_msg = depletion_message(grade_before, tile.gold_grade)
                    if dep_msg:
                        self.add_message(dep_msg, "advisory")
                # Nugget roll
                nugget = NuggetSystem.roll_nugget(
                    dig_depth=tile.dig_depth,
                    gold_grade=tile.gold_grade,
                    region_name=lmap.world_map.get_region(lmap.world_x, lmap.world_y),
                    era_year=self.time.year,
                    placer_skill=self.player.skills.get("placer", 0),
                    rng=_rnd.Random(_rnd.randint(0, 999999)),
                )
                if nugget:
                    self.player.gold_oz += nugget.weight_oz * nugget.fineness
                    self.add_message(NuggetSystem.format_nugget_message(nugget), "normal")
            elif tile.terrain in SOFT:
                # Away from water — fill the pan, can't wash yet
                self.player.pan_loaded = True
                self.player.pan_source_x = self.player.local_x
                self.player.pan_source_y = self.player.local_y
                self.advance_time(10)
                self.player.gain_skill_xp("placer", 1.0)
                self.add_message(
                    "You scoop promising material into the pan. "
                    "You'll need to find water to wash it down.", "advisory")
            else:
                self.add_message(
                    "Nothing to pan here. Find loose gravel or soft ground "
                    "— and water to wash it.", "advisory")
                self.advance_time(2)
            return

        # ── Work sluice / rocker ──────────────────────────────────────────
        if "work the sluice" in a or "work the rocker" in a:
            equip = self._nearby_structure("pan_gold", radius=3)
            if not equip:
                self.add_message("No sluice or rocker nearby.", "advisory")
                return
            if not _near_water():
                self.add_message(
                    f"The {equip.name} needs running water. Set up near a stream.",
                    "advisory")
                return
            has_shovel = any("dig" in getattr(i, "tool_tags", [])
                            for i in self.player.inventory)
            if not has_shovel:
                self.add_message(
                    "You need a shovel to feed material into the sluice.", "advisory")
                return

            import random as _rnd
            from src.prospecting import pan_for_gold, depletion_message
            from src.nugget_system import NuggetSystem
            from src.volume_gold import VolumeGoldSystem

            is_sluice = "sluice" in equip.name.lower()
            runs = 6 if is_sluice else 4  # sluice processes ~6 pans, rocker ~4
            time_cost = 45 if is_sluice else 30  # total time per cycle

            # Lazy column creation
            if tile.gold_column is None:
                _col_bias = max(tile.gold_grade, lmap._gold_bias * 0.5)
                _col_rng = _rnd.Random(lmap.seed + self.player.local_x * 100 + self.player.local_y)
                tile.gold_column = VolumeGoldSystem.create_column(lmap._region_name, _col_bias, _col_rng)

            grade_before = tile.gold_grade if tile.panned else -1.0
            total_oz = 0.0
            for _ in range(runs):
                tile.gold_grade = max(tile.gold_column.get_current_grade(), 0.001)
                VolumeGoldSystem.pan_volume(tile.gold_column,
                    placer_skill=self.player.skills.get("placer", 0))
                result = pan_for_gold(self.player, lmap)
                total_oz += result.gold_oz

            tile.panned = True
            total_value = total_oz * 20.67 * 0.9
            self.player.gold_oz += total_oz
            self.player.gain_skill_xp("placer", 8.0 + total_oz * 50)
            self.player.gain_skill_xp("geology", 2.0)
            self.advance_time(time_cost)

            if total_oz > 0.001:
                self.add_message(
                    f"You shovel gravel into the {equip.name} and work it for "
                    f"{time_cost} minutes. Water carries the light stuff away. "
                    f"Total recovery: {total_oz:.3f} oz (${total_value:.2f}).",
                    "normal")
            else:
                self.add_message(
                    f"You run {runs} loads through the {equip.name}. "
                    f"Nothing. The ground here is played out or barren.",
                    "normal")

            # Nugget roll (one chance per sluice run)
            nugget = NuggetSystem.roll_nugget(
                dig_depth=tile.dig_depth,
                gold_grade=tile.gold_grade,
                region_name=lmap.world_map.get_region(lmap.world_x, lmap.world_y),
                era_year=self.time.year,
                placer_skill=self.player.skills.get("placer", 0),
                rng=_rnd.Random(_rnd.randint(0, 999999)),
            )
            if nugget:
                self.player.gold_oz += nugget.weight_oz * nugget.fineness
                self.add_message(NuggetSystem.format_nugget_message(nugget), "normal")

            # Depletion feedback
            if grade_before > 0:
                dep_msg = depletion_message(grade_before, tile.gold_grade)
                if dep_msg:
                    self.add_message(dep_msg, "advisory")
            return

        # ── Loosen + pan ──────────────────────────────────────────────────
        if "loosen" in a or ("pan" in a and "dirt" in a):
            if tile.terrain == LocalTerrain.ROCK:
                self.add_message(
                    "Solid rock here. Break some material loose with a pick first.",
                    "advisory")
                self.advance_time(5)
                return
            if _near_water():
                import random as _rnd
                from src.prospecting import pan_for_gold
                from src.nugget_system import NuggetSystem
                from src.volume_gold import VolumeGoldSystem
                if tile.gold_column is None:
                    _col_bias = max(tile.gold_grade, lmap._gold_bias * 0.5)
                    _col_rng = _rnd.Random(lmap.seed + self.player.local_x * 100 + self.player.local_y)
                    tile.gold_column = VolumeGoldSystem.create_column(lmap._region_name, _col_bias, _col_rng)
                tile.gold_grade = max(tile.gold_column.get_current_grade(), 0.001)
                VolumeGoldSystem.pan_volume(tile.gold_column, placer_skill=self.player.skills.get("placer", 0))
                result = pan_for_gold(self.player, lmap)
                self.player.pan_loaded = False
                self.player.gain_skill_xp("placer",  result.xp_placer)
                self.player.gain_skill_xp("geology", result.xp_geology)
                self.player.gold_oz += result.gold_oz
                tile.panned = True
                self.advance_time(result.time_minutes + 10)
                self.add_message(
                    "You loosen a patch of soil and pan it at the water's edge. "
                    + result.message, "normal")
                nugget = NuggetSystem.roll_nugget(
                    dig_depth=tile.dig_depth,
                    gold_grade=tile.gold_grade,
                    region_name=lmap.world_map.get_region(lmap.world_x, lmap.world_y),
                    era_year=self.time.year,
                    placer_skill=self.player.skills.get("placer", 0),
                    rng=_rnd.Random(_rnd.randint(0, 999999)),
                )
                if nugget:
                    self.player.gold_oz += nugget.weight_oz * nugget.fineness
                    self.add_message(NuggetSystem.format_nugget_message(nugget), "normal")
            else:
                self.player.pan_loaded = True
                self.advance_time(15)
                self.player.gain_skill_xp("placer", 1.0)
                self.add_message(
                    "You loosen a patch and fill the pan with raw material. "
                    "Find water to wash it.", "advisory")
            return

        # ── Load pan from adjacent material ───────────────────────────────
        if "load pan" in a or ("load" in a and "pan" in a):
            has_pan = any("pan" in getattr(i, "tool_tags", [])
                          for i in self.player.inventory)
            if not has_pan:
                self.add_message("You need a gold pan to load material into.", "advisory")
                self.advance_time(2)
                return
            from src.menus import pick_direction_menu
            direction = pick_direction_menu(
                self._console, self._ctx, "Load from which direction?")
            if direction is None:
                self.add_message("Cancelled.", "normal")
                return
            dx, dy = direction
            tx, ty = self.player.local_x + dx, self.player.local_y + dy
            if not lmap.in_bounds(tx, ty):
                self.add_message("Nothing there.", "advisory")
                return
            src_tile = lmap.tile_at(tx, ty)
            if src_tile.terrain in SOFT:
                self.player.pan_loaded = True
                self.player.pan_source_x = tx
                self.player.pan_source_y = ty
                self.advance_time(8)
                self.player.gain_skill_xp("placer", 1.0)
                terrain_name = {
                    LocalTerrain.GRAVEL_BAR: "gravel", LocalTerrain.SPOIL_PILE: "the spoil pile",
                    LocalTerrain.BEDROCK: "bedrock material", LocalTerrain.SAND: "sand",
                    LocalTerrain.MUD: "mud",
                    LocalTerrain.WORKED_GRAVEL: "worked gravel",
                    LocalTerrain.WORKED_DIRT: "turned dirt",
                }.get(src_tile.terrain, "loose material")
                depth_info = ""
                if src_tile.dig_depth > 0:
                    depth_info = f" (from {src_tile.dig_depth * 3}ft depth)"
                self.add_message(
                    f"You scoop {terrain_name}{depth_info} into the pan. "
                    "Find water to wash it.", "advisory")
            else:
                self.add_message(
                    "No loose material there to pan. Try gravel, sand, or a spoil pile.",
                    "advisory")
                self.advance_time(3)
            return

        # ── Geology / sampling ────────────────────────────────────────────
        if "sample" in a or "assess" in a or "geology" in a or "mineral" in a or "terrain" in a:
            from src.prospecting import assess_ground
            msg = assess_ground(self.player, lmap)
            self.player.gain_skill_xp("geology", 3.0)
            self.advance_time(10)
            self.add_message(msg, "normal")
            return

        # ── Digging ───────────────────────────────────────────────────────
        if "dig" in a or "excavat" in a or "test pit" in a:
            inv_tags = {tag for item in self.player.inventory for tag in item.tool_tags}
            px, py = self.player.local_x, self.player.local_y
            pz = self.player.local_z
            sz = int(lmap.surface_z[py][px])

            _DIR_NAMES = {
                (-1,-1): "northwest", (0,-1): "north",  (1,-1): "northeast",
                (-1, 0): "west",                         (1, 0): "east",
                (-1, 1): "southwest", (0, 1): "south",  (1, 1): "southeast",
            }

            if tile.terrain == LocalTerrain.WATER:
                self.add_message(
                    "The water keeps filling in. Divert or dam it first.", "advisory")
                self.advance_time(10)
                return

            # What's below the player's current z-level?
            from src.local_map import ZTile, SubsurfaceMaterial
            from src.constants import Z_MIN, Z_FEET_PER_LEVEL
            dig_target_z = pz - 1

            if dig_target_z < Z_MIN:
                self.add_message("You've hit the deepest point possible.", "advisory")
                self.advance_time(5)
                return

            # Check if already dug out below
            existing_below = lmap.z_tiles.get((px, py, dig_target_z))
            if existing_below is not None:
                self.add_message("Already dug out below. Use stairs/ladder to descend.", "advisory")
                self.advance_time(2)
                return

            # Determine material at target depth
            material = lmap.natural_material_at(px, py, dig_target_z)
            depth_below_surface = sz - dig_target_z

            if material == SubsurfaceMaterial.BEDROCK:
                if "pick" not in inv_tags:
                    self.add_message(
                        "Solid bedrock. You need a pick to make any progress.", "advisory")
                    self.advance_time(5)
                    return
                time_cost = 90
                doing = "You drive your pick into solid bedrock. Brutal work."
                skill_name = "hardRock"
            elif material in (SubsurfaceMaterial.STONE, SubsurfaceMaterial.ORE):
                if "pick" not in inv_tags and "dig" not in inv_tags:
                    self.add_message(
                        "Rock below. You need a pick.", "advisory")
                    self.advance_time(5)
                    return
                time_cost = 60
                doing = "You break through rock and stone."
                skill_name = "hardRock"
            elif material == SubsurfaceMaterial.GRAVEL:
                time_cost = 25 if ("dig" in inv_tags or "pick" in inv_tags) else 40
                doing = "You dig through loose gravel."
                skill_name = "placer"
            else:
                # Soil / clay
                time_cost = 20 if ("dig" in inv_tags or "pick" in inv_tags) else 35
                doing = "You dig through soft earth."
                skill_name = "placer"

            # First dig on this tile — ask where to pile the spoil
            if tile.spoil_dir is None:
                from src.menus import pick_direction_menu
                direction = pick_direction_menu(
                    self._console, self._ctx, "Pile spoil which way?")
                if direction is None:
                    self.add_message("Dig cancelled.", "normal")
                    return
                tile.spoil_dir = direction

            # Create the z-tile below (open space the player dug out)
            material_terrain = {
                SubsurfaceMaterial.SOIL: LocalTerrain.GROUND,
                SubsurfaceMaterial.GRAVEL: LocalTerrain.GRAVEL_BAR,
                SubsurfaceMaterial.CLAY: LocalTerrain.MUD,
                SubsurfaceMaterial.STONE: LocalTerrain.GROUND,
                SubsurfaceMaterial.ORE: LocalTerrain.GROUND,
                SubsurfaceMaterial.BEDROCK: LocalTerrain.BEDROCK,
            }.get(material, LocalTerrain.GROUND)

            # Gold grade from GoldColumn if it exists
            gold = 0.0
            if tile.gold_column is not None:
                layer_idx = min(depth_below_surface,
                                len(tile.gold_column.layers) - 1)
                if 0 <= layer_idx < len(tile.gold_column.layers):
                    gold = tile.gold_column.layers[layer_idx].gold_grade

            zt = ZTile(terrain=material_terrain, gold_grade=gold)
            lmap.z_tiles[(px, py, dig_target_z)] = zt

            # Update surface tile to show it's a pit
            tile.dig_depth += 1
            # Visual pit depth — shallow vs deep
            if tile.dig_depth <= 2:
                tile.terrain = LocalTerrain.SHALLOW_PIT
            else:
                tile.terrain = LocalTerrain.DEEP_PIT
            if tile.gold_column is not None:
                tile.gold_column.total_dug_depth = tile.dig_depth
                tile.gold_grade = tile.gold_column.get_current_grade()

            # Place spoil pile at surface
            sdx, sdy = tile.spoil_dir
            sx, sy = px + sdx, py + sdy
            if lmap.in_bounds(sx, sy):
                st = lmap.tile_at(sx, sy)
                if st.terrain not in (LocalTerrain.WATER, LocalTerrain.ROCK):
                    st.terrain = LocalTerrain.SPOIL_PILE
            lmap.invalidate_terrain_cache()

            self.advance_time(time_cost)
            self.player.gain_skill_xp(skill_name, 2.0)
            self.recompute_fov()

            depth_ft = depth_below_surface * Z_FEET_PER_LEVEL
            pile_dir = _DIR_NAMES.get(tile.spoil_dir, "nearby")
            material_names = {
                SubsurfaceMaterial.SOIL: "soil",
                SubsurfaceMaterial.GRAVEL: "gravel",
                SubsurfaceMaterial.CLAY: "clay",
                SubsurfaceMaterial.STONE: "rock",
                SubsurfaceMaterial.ORE: "ore-bearing rock",
                SubsurfaceMaterial.BEDROCK: "solid bedrock",
            }
            mat_name = material_names.get(material, "earth")
            self.add_message(
                f"{doing} Dug through {mat_name} at {depth_ft}ft below surface. "
                f"Spoil to the {pile_dir}. Build a ladder to descend.",
                "normal")

            # Nugget chance from the layer
            if gold > 0.05:
                import random as _rnd
                from src.nugget_system import NuggetSystem
                nugget = NuggetSystem.roll_nugget(
                    dig_depth=depth_below_surface,
                    gold_grade=gold,
                    region_name=lmap.world_map.get_region(lmap.world_x, lmap.world_y),
                    era_year=self.time.year,
                    placer_skill=self.player.skills.get("placer", 0),
                    rng=_rnd.Random(_rnd.randint(0, 999999)),
                )
                if nugget:
                    self.player.gold_oz += nugget.weight_oz * nugget.fineness
                    self.add_message(
                        "In the loose material: " + NuggetSystem.format_nugget_message(nugget),
                        "normal")

            # Check for mine flooding — if we dug near or below water table
            if lmap.fluid_system:
                wt_z = lmap.fluid_system.water_table_z(px, py)
                if dig_target_z <= wt_z:
                    lmap.fluid_system.add_fluid(px, py, amount=3, z=dig_target_z)
                    self.add_message(
                        "Water seeps in from the walls! The shaft is flooding.",
                        "critical")
            return

        # ── Fill canteen ──────────────────────────────────────────────────
        if "fill" in a and "canteen" in a:
            adj_water = tile.terrain == LocalTerrain.WATER or any(
                lmap.in_bounds(self.player.local_x + dx, self.player.local_y + dy) and
                lmap.tile_at(self.player.local_x + dx,
                             self.player.local_y + dy).terrain == LocalTerrain.WATER
                for dx in range(-1, 2) for dy in range(-1, 2)
            )
            if adj_water:
                self.player.survival.drink(30)
                self.add_message(
                    "You fill your canteen from the stream and drink deeply.", "normal")
                self.advance_time(5)
            else:
                self.add_message(
                    "No water here. You'll need to find a stream or spring first.",
                    "advisory")
                self.advance_time(2)
            return

        # ── Move rocks ────────────────────────────────────────────────────
        if "move rock" in a or "clear rock" in a:
            # Find rock tile on or adjacent to player
            rock_tile = None
            if tile.terrain == LocalTerrain.ROCK:
                rock_tile = tile
            else:
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        nx, ny = px + dx, py + dy
                        if lmap.in_bounds(nx, ny) and lmap.tiles[ny][nx].terrain == LocalTerrain.ROCK:
                            rock_tile = lmap.tiles[ny][nx]
                            break
                    if rock_tile:
                        break
            if not rock_tile:
                self.add_message("No rocks next to you to move.", "advisory")
                return
            self.add_message(
                "You heave the rocks aside, exposing the gravel and soil beneath. "
                "The work is harder than it looks.", "normal")
            rock_tile.terrain = LocalTerrain.GRAVEL_BAR
            lmap.invalidate_terrain_cache()
            self.advance_time(15)
            self.player.gain_skill_xp("placer", 1.0)
            return

        # ── Clear brush ───────────────────────────────────────────────────
        if "clear" in a and "brush" in a:
            if tile.terrain != LocalTerrain.BRUSH:
                self.add_message("No brush here to clear.", "advisory")
                return
            inv_tags = {tag for item in self.player.inventory
                        for tag in item.tool_tags}
            if "chop" in inv_tags:
                self.add_message(
                    "You hack through the brush with your axe. "
                    "The area opens up after a half-hour of work.", "normal")
                self.advance_time(30)
            else:
                self.add_message(
                    "You tear through the brush by hand. "
                    "Scratched up but the ground is clear.", "normal")
                self.advance_time(45)
            tile.terrain = LocalTerrain.GROUND
            lmap.invalidate_terrain_cache()
            return

        # ── Fell tree (standing → downed) ─────────────────────────────────
        TREE_TILES = (LocalTerrain.PINE, LocalTerrain.OAK, LocalTerrain.ASPEN,
                      LocalTerrain.JUNIPER, LocalTerrain.CEDAR, LocalTerrain.MAPLE,
                      LocalTerrain.CHESTNUT, LocalTerrain.HICKORY, LocalTerrain.CYPRESS,
                      LocalTerrain.MAGNOLIA, LocalTerrain.FOREST)
        is_fell = ("fell" in a and "tree" in a) or \
                  ("cut" in a and "tree" in a) or \
                  ("chop" in a and "tree" in a)
        if is_fell:
            inv_tags = {tag for item in self.player.inventory
                        for tag in item.tool_tags}
            if "chop" not in inv_tags:
                self.add_message("You need an axe to fell a tree.", "advisory")
                return
            tree_tile = None
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    nx, ny = px + dx, py + dy
                    if lmap.in_bounds(nx, ny) and lmap.tiles[ny][nx].terrain in TREE_TILES:
                        tree_tile = lmap.tiles[ny][nx]
                        break
                if tree_tile:
                    break
            if not tree_tile:
                self.add_message("No standing trees nearby.", "advisory")
                return
            tree_tile.terrain = LocalTerrain.DOWNED_TREE
            lmap.invalidate_terrain_cache()
            self.add_message(
                "CRACK — the tree leans, sways, and crashes to the ground. "
                "Branches scatter. Chop it up for logs.", "normal")
            self.advance_time(20)
            self.player.gain_skill_xp("survival", 2.0)
            return

        # ── Chop wood (downed tree → logs) ────────────────────────────────
        if "chop" in a and "wood" in a:
            inv_tags = {tag for item in self.player.inventory
                        for tag in item.tool_tags}
            # Find downed tree or standing tree nearby
            target_tile = None
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    nx, ny = px + dx, py + dy
                    if lmap.in_bounds(nx, ny):
                        t = lmap.tiles[ny][nx].terrain
                        if t == LocalTerrain.DOWNED_TREE:
                            target_tile = lmap.tiles[ny][nx]
                            break
                        if t in TREE_TILES and target_tile is None:
                            target_tile = lmap.tiles[ny][nx]
                if target_tile and target_tile.terrain == LocalTerrain.DOWNED_TREE:
                    break
            if not target_tile:
                self.add_message("No trees or downed timber nearby.", "advisory")
                return
            from src.items import make_item
            if "chop" not in inv_tags:
                self.add_message(
                    "You break dead branches by hand — enough for a fire.", "normal")
                self.advance_time(15)
                return
            if target_tile.terrain == LocalTerrain.DOWNED_TREE:
                # Process downed tree into logs
                target_tile.terrain = LocalTerrain.GROUND
                lmap.invalidate_terrain_cache()
                try:
                    self.player.inventory.append(make_item("log"))
                    self.player.inventory.append(make_item("log"))
                    self.player.inventory.append(make_item("log"))
                except Exception:
                    pass
                self.add_message(
                    "You buck the downed trunk into sections. Three logs.", "normal")
                self.advance_time(25)
            else:
                # Fell + chop in one go (standing tree)
                target_tile.terrain = LocalTerrain.GROUND
                lmap.invalidate_terrain_cache()
                try:
                    self.player.inventory.append(make_item("log"))
                    self.player.inventory.append(make_item("log"))
                except Exception:
                    pass
                self.add_message(
                    "You fell a tree and split it into two rough logs.", "normal")
                self.advance_time(40)
            self.player.gain_skill_xp("survival", 2.0)
            return

        # ── Follow stream / river ─────────────────────────────────────────
        if ("follow" in a and ("stream" in a or "river" in a or "creek" in a or "water" in a)) or \
           ("upstream" in a or "downstream" in a):
            # Actually move the player along the water
            direction = -1 if "upstream" in a or "up" in a else 1
            moved = 0
            for _ in range(20):
                # Find adjacent water tile and move toward it
                best_dx, best_dy = 0, 0
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        if dx == 0 and dy == 0:
                            continue
                        nx, ny = self.player.local_x + dx, self.player.local_y + dy
                        if lmap.in_bounds(nx, ny):
                            # Follow water tiles, preferring the direction
                            if lmap.tiles[ny][nx].terrain == LocalTerrain.WATER:
                                if dy * direction >= 0:
                                    best_dx, best_dy = dx, dy
                                    break
                    if best_dx or best_dy:
                        break
                if best_dx == 0 and best_dy == 0:
                    break
                self.player.local_x += best_dx
                self.player.local_y += best_dy
                self.player.local_z = lmap.ground_z(
                    self.player.local_x, self.player.local_y)
                moved += 1
            self.add_message(
                f"You follow the watercourse {'upstream' if direction == -1 else 'downstream'}, "
                f"reading the bends and gravel bars as you go. "
                f"Moved {moved * 5}ft along the water.", "normal")
            self.advance_time(20)
            self.player.gain_skill_xp("geology", 1.5)
            self.player.gain_skill_xp("tracking", 1.0)
            self.recompute_fov()
            return

        # ── Cross water ───────────────────────────────────────────────────
        if "cross" in a and "water" in a:
            if tile.terrain == LocalTerrain.WATER or any(
                lmap.in_bounds(self.player.local_x + dx, self.player.local_y + dy) and
                lmap.tile_at(self.player.local_x + dx,
                             self.player.local_y + dy).terrain == LocalTerrain.WATER
                for dx in range(-2, 3) for dy in range(-2, 3)
            ):
                self.add_message(
                    "You wade across. Cold water up to your knees, "
                    "footing uncertain on the slick rocks.", "normal")
                self.advance_time(10)
                self.player.survival.tick(10.0, activity_mult=1.5)
            else:
                self.add_message("No water here to cross.", "advisory")
                self.advance_time(2)
            return

        # ── Rest / camp / sleep ───────────────────────────────────────────
        if "rest" in a or "camp" in a or "sleep" in a:
            self._open_wait()
            return

        # ── Look / search ─────────────────────────────────────────────────
        if "look" in a or "search" in a:
            self.add_message("You look around carefully.", "normal")
            self.advance_time(5)
            self.player.gain_skill_xp("tracking", 0.5)
            return

        # ── Read a book (check BEFORE streamflow so "read" doesn't catch it) ─
        if "read" in a and ("book" in a or "guide" in a or "manual" in a
                             or "bible" in a or "reader" in a):
            self._handle_read_book()
            return

        # ── Read streamflow ───────────────────────────────────────────────
        if "stream" in a and ("read" in a or "flow" in a):
            from src.prospecting import assess_ground
            msg = assess_ground(self.player, lmap)
            self.add_message(msg, "normal")
            self.advance_time(10)
            self.player.gain_skill_xp("geology", 2.0)
            return

        # ── Light a fire ─────────────────────────────────────────────────
        # ── Light a fire (spreading) — pick a direction ─────────────────
        is_set_fire = ("set fire" in a or
                       ("light" in a and "fire" in a and "camp" not in a) or
                       ("burn" in a and ("brush" in a or "tree" in a or
                        "building" in a or "camp" in a)))
        if is_set_fire:
            has_flint = any(i.id == "flint_steel" for i in self.player.inventory)
            if not has_flint:
                self.add_message("You need flint and steel.", "advisory")
                return
            from src.fire_system import FireSystem, IGNITE_TICKS
            from src.menus import pick_direction_menu
            direction = pick_direction_menu(
                self._console, self._ctx, "Set fire in which direction?")
            if direction is None:
                return
            dx, dy = direction
            nx, ny = px + dx, py + dy
            if not lmap.in_bounds(nx, ny):
                self.add_message("Nothing there.", "advisory")
                return
            t = lmap.tiles[ny][nx].terrain
            if IGNITE_TICKS.get(t, 0) <= 0:
                self.add_message("That won't burn.", "advisory")
                return
            if not hasattr(lmap, '_fire') or lmap._fire is None:
                lmap._fire = FireSystem()
            lmap._fire.ignite(nx, ny, lmap)
            self.add_message(
                "You strike the flint. Sparks catch. Flames lick upward. "
                "The fire begins to spread.", "normal")
            self.advance_time(5)
            # Arson crime if in settlement
            if hasattr(lmap, 'town_layout') and lmap.town_layout:
                witnesses = self._witnesses_near(px, py)
                if witnesses:
                    region = lmap._region_name if lmap else ""
                    self.legal.record_crime(
                        "arson", self.time.total_minutes // 1440,
                        self.player.world_x, self.player.world_y, region,
                        nearby_npcs=witnesses)
                    self.add_message("Arson! Witnesses see what you've done.", "critical")
            return

        # ── Build campfire (contained, doesn't spread) ────────────────
        if ("camp" in a and "fire" in a) or "make fire" in a or \
           "start fire" in a or "build fire" in a or "campfire" in a:
            has_flint = any(i.id == "flint_steel" for i in self.player.inventory)
            has_wood = any(i.id == "log" or "wood" in i.name.lower()
                          for i in self.player.inventory)
            if not has_flint:
                self.add_message(
                    "You need flint and steel to start a fire.", "advisory")
                self.advance_time(2)
                return
            if not has_wood:
                self.add_message(
                    "You need wood or fuel to burn.", "advisory")
                self.advance_time(2)
                return
            # Consume one log
            for item in self.player.inventory:
                if item.id == "log":
                    if item.stackable and item.quantity > 1:
                        item.quantity -= 1
                    else:
                        self.player.inventory.remove(item)
                    break
            # Place campfire on adjacent tile
            from src.construction import PlacedEquipment
            fx, fy = self.player.local_x + 1, self.player.local_y
            if lmap.in_bounds(fx, fy):
                sid = lmap._next_id
                lmap._next_id += 1
                fire = PlacedEquipment(
                    id=sid, blueprint_key="campfire", name="Campfire",
                    x=fx, y=fy, width=1, height=1,
                    condition=100, progress=100,
                    functional_tags=["cook", "warmth", "light"],
                )
                lmap.structures[sid] = fire
            self.add_message(
                "You strike sparks and nurse a flame. A campfire crackles to life.",
                "normal")
            self.player.gain_skill_xp("survival", 2.0)
            self.advance_time(15)
            return

        # ── Fish ─────────────────────────────────────────────────────────
        if "fish" in a:
            if not _near_water():
                self.add_message("No water nearby to fish in.", "advisory")
                self.advance_time(2)
                return
            import random as _fish_rng
            skill = self.player.skills.get("survival", 0)
            roll = _fish_rng.randint(1, 20) + skill
            self.advance_time(30)
            self.player.gain_skill_xp("survival", 2.0)
            if roll >= 10:
                from src.items import make_item
                fish = make_item("fresh_fish")
                self.player.inventory.append(fish)
                self.add_message(
                    "You catch a fish! Fresh fish added to inventory.", "normal")
            else:
                self.add_message(
                    "You wait patiently but nothing bites.", "normal")
            return

        # ── Forage ───────────────────────────────────────────────────────
        if "forage" in a or ("gather" in a and "food" in a):
            import random as _forage_rng
            skill = self.player.skills.get("survival", 0)
            roll = _forage_rng.randint(1, 20) + skill
            self.advance_time(40)
            self.player.gain_skill_xp("survival", 1.5)
            if roll >= 12:
                from src.items import Item
                berries = Item(id="wild_berries", name="Wild Berries",
                               weight=0.2, category="food", nutrition=8.0,
                               description="A handful of edible wild berries.",
                               perishable=True, days_until_spoil=2,
                               base_value=0.02, stackable=True)
                self.player.inventory.append(berries)
                self.add_message(
                    "You find some edible berries and greens.", "normal")
            elif roll >= 8:
                self.add_message(
                    "You find a few edible roots but nothing substantial.",
                    "normal")
                self.player.survival.eat(3)
            else:
                self.add_message(
                    "You search but find nothing worth eating.", "normal")
            return

        # ── Set up tent ──────────────────────────────────────────────────
        if "tent" in a and ("set" in a or "pitch" in a or "put" in a or "up" in a):
            has_tent = any(i.id == "canvas_tent" for i in self.player.inventory)
            if not has_tent:
                self.add_message("You don't have a tent.", "advisory")
                self.advance_time(2)
                return
            # Place tent as structure
            from src.construction import PlacedEquipment
            tx, ty = self.player.local_x, self.player.local_y + 1
            if lmap.in_bounds(tx, ty):
                sid = lmap._next_id
                lmap._next_id += 1
                tent = PlacedEquipment(
                    id=sid, blueprint_key="tent_pitched", name="Pitched Tent",
                    x=tx, y=ty, width=2, height=2,
                    condition=100, progress=100,
                    functional_tags=["shelter", "sleep"],
                )
                lmap.structures[sid] = tent
            self.add_message(
                "You pitch your tent and stake it down.", "normal")
            self.player.gain_skill_xp("survival", 1.0)
            self.advance_time(20)
            return

        # ── Build / construct ─────────────────────────────────────────────
        if "build" in a or "construct" in a:
            self._handle_build_action(a)
            return

        # ── LLM fallback — all unrecognised actions ───────────────────────
        ctx = self._build_llm_context()
        resp = self.llm.resolve_action(a, ctx)

        # Apply result
        if resp.message:
            self.add_message(resp.message, "normal")
        if resp.gold_delta:
            self.player.gold_oz += resp.gold_delta
        if resp.health_delta and resp.health_delta < 0:
            self._apply_llm_damage(abs(resp.health_delta),
                                   resp.damage_type, resp.wound_location, a)
        elif resp.health_delta and resp.health_delta > 0:
            self.player.survival.health = min(
                100.0, self.player.survival.health + resp.health_delta)
        for skill, xp in resp.xp_grants.items():
            self.player.gain_skill_xp(skill, float(xp))
        for npc_name, delta in resp.relationship_changes.items():
            for npc in self._tile_npcs():
                if npc.name == npc_name:
                    npc.adjust_relationship(delta)
        # Items consumed by this action (durable items degrade, not vanish)
        if resp.items_used:
            from src.action_menu import apply_item_use_safe
            for msg in apply_item_use_safe(self.player, resp.items_used):
                self.add_message(msg, "advisory")
        # NPC damage/kills from LLM (explosions, area attacks, etc.)
        if resp.npc_damage or resp.npc_killed:
            self._apply_llm_npc_effects(resp)
        # Items created/gained (ItemFactory gives full categorization)
        if resp.items_gained:
            ctx_for_items = self._build_llm_context()
            ctx_for_items["items_used"] = resp.items_used or []
            for msg in self.item_factory.create_from_response(
                    resp.items_gained, ctx_for_items, self.player,
                    resp.equip_right, resp.equip_left):
                self.add_message(msg, "advisory")
        # Terrain mutation: tree felling, digging, burning, etc.
        self._apply_llm_terrain(a, resp)
        # Check for death after all effects applied
        if self.player.survival.health <= 0 or not self.player.wounds.alive:
            self._trigger_death(resp.message or a)
        # Hostile NPCs get their response turn
        self._npc_combat_tick()
        if resp.time_cost > 0:
            self.advance_time(resp.time_cost)
        elif not resp.message:
            self.advance_time(5)

    def _apply_llm_damage(self, damage: float, damage_type, wound_location, action_text: str):
        """Apply damage from an LLM action — reduces health AND creates a wound."""
        from src.health_system import DmgType
        dtype_map = {
            "blunt": DmgType.BLUNT, "edged": DmgType.SLASH,
            "piercing": DmgType.PIERCE, "explosive": DmgType.BLAST,
            "gunshot": DmgType.GUNSHOT, "slash": DmgType.SLASH,
            "fire": DmgType.BURN, "bite": DmgType.BITE,
        }
        dtype = dtype_map.get(damage_type, None)
        if not dtype:
            low = action_text.lower()
            if any(w in low for w in ("shoot", "bullet", "gun", "rifle", "pistol", "arrow")):
                dtype = DmgType.GUNSHOT
            elif any(w in low for w in ("cut", "slice", "knife", "blade", "slash", "axe", "chop")):
                dtype = DmgType.SLASH
            elif any(w in low for w in ("blast", "explode", "dynamite", "powder")):
                dtype = DmgType.BLAST
            elif any(w in low for w in ("fire", "burn", "flame")):
                dtype = DmgType.BURN
            elif any(w in low for w in ("bite", "claw", "maul")):
                dtype = DmgType.BITE
            else:
                dtype = DmgType.BLUNT

        # Check if this is an insertion rather than a combat hit
        low = action_text.lower()
        is_insertion = any(w in low for w in
                           ("insert", "put", "shove", "stick", "push into",
                            "place in", "lodge", "swallow"))
        if is_insertion:
            self._apply_insertion(damage, wound_location, action_text)
            return

        wound = self.player.wounds.apply_hit(
            damage, dtype, wound_location or None,
            worn_equipment=self.player.worn)
        self.player.survival.health = max(0.0, self.player.survival.health - damage)
        bleed_str = f"  [bleeding {wound.bleed_level}]" if wound.is_bleeding else ""
        self.add_message(
            f"  Wound: {wound.description} ({wound.severity}){bleed_str}",
            "critical")

    def _apply_insertion(self, damage: float, wound_location: str, action_text: str):
        """Handle voluntary insertion of an object into a body part."""
        # Find the item being inserted
        item_name = ""
        for item in self.player.inventory:
            if item.name.lower() in action_text.lower():
                item_name = item.name
                break
        if not item_name:
            # Try to extract from action text
            for word in action_text.split():
                if len(word) > 2 and word.lower() not in (
                    "put", "insert", "shove", "stick", "into", "in", "my",
                    "the", "push", "place", "your", "swallow"):
                    item_name = word
                    break

        part = wound_location or "abdomen"

        # Determine if the item causes damage based on properties
        causes_damage = False
        dmg = 0.0
        if item_name:
            for item in self.player.inventory:
                if item.name.lower() == item_name.lower():
                    # Sharp or heavy items cause damage
                    if item.is_weapon() or item.damage_max > 0:
                        causes_damage = True
                        dmg = max(damage, item.damage_max * 0.3)
                    elif item.weight > 2.0:
                        causes_damage = True
                        dmg = max(damage * 0.5, 3.0)
                    elif any(t in getattr(item, "tool_tags", [])
                             for t in ("cut", "chop", "dig")):
                        causes_damage = True
                        dmg = max(damage, 5.0)
                    break

        msg, wound = self.player.wounds.insert_object(
            item_name or "unknown object", part,
            causes_damage=causes_damage, damage=dmg)

        if causes_damage and wound:
            self.player.survival.health = max(0.0, self.player.survival.health - dmg)
            self.add_message(f"  {msg}", "critical")
        else:
            self.add_message(f"  {msg}", "advisory")

    def _trigger_death(self, cause: str):
        if getattr(self, "_death_triggered", False):
            return
        self._death_triggered = True
        self.player.survival.health = 0.0
        self.add_message("You are dead.", "critical")
        self._open_death_screen(cause)

    def _open_death_screen(self, cause: str):
        """Full-screen death / obituary display. Blocks until player presses Enter."""
        con = self._console
        ctx = self._ctx
        from src.menus import draw_box

        # ── Build player context for the obituary ──────────────────────────
        p = self.player

        # Describe skills as character traits, not numbers
        skill_desc = []
        for k, v in sorted(p.skills.items(), key=lambda x: -x[1]):
            if v >= 7:
                skill_desc.append(f"expert {k}")
            elif v >= 4:
                skill_desc.append(f"competent {k}")
            elif v >= 2:
                skill_desc.append(f"basic {k}")
        skills_str = ", ".join(skill_desc) if skill_desc else "no notable skills"

        # Describe attributes as physical traits
        attr_desc = []
        s = p.attributes
        if s.get("strength", 10) >= 14: attr_desc.append("powerfully built")
        elif s.get("strength", 10) <= 7: attr_desc.append("slight of frame")
        if s.get("agility", 10) >= 14: attr_desc.append("quick and nimble")
        if s.get("intelligence", 10) >= 14: attr_desc.append("sharp-minded")
        if s.get("wisdom", 10) >= 14: attr_desc.append("deeply perceptive")
        if s.get("charisma", 10) >= 14: attr_desc.append("silver-tongued")
        if s.get("constitution", 10) >= 14: attr_desc.append("iron constitution")
        elif s.get("constitution", 10) <= 7: attr_desc.append("sickly and frail")
        phys_str = ", ".join(attr_desc) if attr_desc else "an ordinary man"

        # Wounds at death — detailed
        wounds_str = ""
        for w in p.wounds.wounds:
            from src.health_system import PART_DATA
            part_label = PART_DATA.get(w.part, {}).get("label", w.part)
            wounds_str += f"  - {w.description} on {part_label.lower()}"
            if w.is_bleeding:
                wounds_str += f" (bleeding {w.bleed_level})"
            if w.lodged:
                wounds_str += f" ({w.lodged} lodged)"
            if w.bone_broken:
                wounds_str += " (broken bone)"
            wounds_str += "\n"
        if not wounds_str:
            wounds_str = "  none visible\n"

        # Last 50 messages — the final events leading to death
        recent_events = "\n".join(
            f"  {txt}" for txt, sev in self.messages[-50:]
        )
        # Journal diary
        diary_str = ""
        for entry in list(self.journal.diary)[-10:]:
            diary_str += f"  {entry.date_str}: {entry.text[:200]}\n"

        region = self.world.get_region(p.world_x, p.world_y)
        year = self.time.year if hasattr(self.time, "year") else "1849"

        context = (
            f"CHARACTER: {p.name}, age {p.age}\n"
            f"YEAR: {year}\n"
            f"LOCATION: {region}\n"
            f"PHYSICAL DESCRIPTION: {phys_str}\n"
            f"ABILITIES: {skills_str}\n"
            f"CAUSE OF DEATH: {cause}\n"
            f"GOLD ACCUMULATED: {p.gold_oz:.3f} troy ounces\n"
            f"CASH ON PERSON: ${p.cash:.2f}\n"
            f"WOUNDS AT TIME OF DEATH:\n{wounds_str}\n"
            f"BLOOD REMAINING: {p.wounds.blood_pct*100:.0f}%\n"
            f"EVENTS LEADING TO DEATH (most recent last):\n{recent_events}\n\n"
            f"JOURNAL ENTRIES:\n{diary_str}\n"
            f"Write the death narrative now. Be GRAPHIC about the final moments. "
            f"Describe the physical reality of dying. Use the wound details and "
            f"events above to reconstruct exactly what happened."
        )

        # ── Generate obituary ──────────────────────────────────────────────
        # Show "writing..." placeholder while LLM works
        con.clear()
        con.print(SCREEN_WIDTH // 2 - 10, SCREEN_HEIGHT // 2,
                  "Writing obituary...", fg=(180, 60, 60), bg=(0, 0, 0))
        ctx.present(con)

        obit = self.llm.generate_obituary(context) if self.llm else \
               f"{self.player.name} died in {region}. The frontier does not mourn long."

        # ── Word-wrap obituary ─────────────────────────────────────────────
        W = SCREEN_WIDTH - 6
        max_w = W - 4
        obit_lines = []
        for para in obit.split("\n"):
            para = para.strip()
            if not para:
                obit_lines.append("")
                continue
            line = ""
            for word in para.split():
                test = (line + " " + word).strip()
                if len(test) <= max_w:
                    line = test
                else:
                    if line:
                        obit_lines.append(line)
                    line = word
            if line:
                obit_lines.append(line)
            obit_lines.append("")

        scroll   = 0
        view_h   = SCREEN_HEIGHT - 10
        total    = len(obit_lines)

        while True:
            con.clear()
            # Title banner
            title = f"  {self.player.name.upper()} — DEAD  "
            con.draw_rect(0, 0, SCREEN_WIDTH, 3, ord(" "), fg=(180, 60, 60), bg=(30, 0, 0))
            con.print(SCREEN_WIDTH // 2 - len(title) // 2, 1,
                      title, fg=(255, 100, 100), bg=(30, 0, 0))

            # Cause + stats strip
            stats = (f"Cause: {cause[:60]}    "
                     f"Gold: {self.player.gold_oz:.2f} oz    "
                     f"Cash: ${self.player.cash:.2f}    "
                     f"Region: {region}")
            con.print(2, 3, stats[:SCREEN_WIDTH - 4], fg=(160, 100, 60), bg=(0, 0, 0))

            # Obituary text
            scroll = max(0, min(scroll, max(0, total - view_h)))
            for i, line in enumerate(obit_lines[scroll: scroll + view_h]):
                con.print(3, 5 + i, line, fg=(210, 190, 160), bg=(0, 0, 0))

            # Footer
            footer = "[↑↓ / PgUp / PgDn] scroll    [Enter] exit game"
            con.print(SCREEN_WIDTH // 2 - len(footer) // 2,
                      SCREEN_HEIGHT - 2, footer, fg=(100, 100, 100), bg=(0, 0, 0))
            ctx.present(con)

            for event in tcod.event.wait():
                if isinstance(event, tcod.event.Quit):
                    raise SystemExit(0)
                if isinstance(event, tcod.event.KeyDown):
                    sym = event.sym
                    if sym in (tcod.event.KeySym.RETURN, tcod.event.KeySym.KP_ENTER,
                               tcod.event.KeySym.ESCAPE):
                        raise SystemExit(0)
                    elif sym in (tcod.event.KeySym.UP, tcod.event.KeySym.KP_8):
                        scroll -= 1
                    elif sym in (tcod.event.KeySym.DOWN, tcod.event.KeySym.KP_2):
                        scroll += 1
                    elif sym == tcod.event.KeySym.PAGEUP:
                        scroll -= view_h
                    elif sym == tcod.event.KeySym.PAGEDOWN:
                        scroll += view_h
                    elif sym == tcod.event.KeySym.HOME:
                        scroll = 0
                    elif sym == tcod.event.KeySym.END:
                        scroll = max(0, total - view_h)

    def _apply_gravity(self, entity, lmap) -> int:
        """
        If entity is in open air, drop them to solid ground.
        Applies fall damage for drops > 1 z-level.
        Returns number of z-levels fallen.
        """
        x = entity.local_x
        y = entity.local_y
        z = entity.local_z
        if not lmap.in_bounds(x, y):
            return 0

        ground = lmap.ground_z(x, y)

        if z <= ground:
            return 0  # on solid ground

        # Fall to ground
        fall_dist = z - ground
        entity.local_z = ground

        # Fall damage: 0 for 1 level, increasing after that
        if fall_dist > 1:
            from src.health_system import DmgType
            damage = (fall_dist - 1) * 8  # 8 dmg per level beyond the first
            if hasattr(entity, "wounds"):
                wound = entity.wounds.apply_hit(damage, DmgType.BLUNT)
                if hasattr(entity, "survival"):
                    entity.survival.health = max(0, entity.survival.health - damage)
                elif hasattr(entity, "health"):
                    entity.health = max(0, entity.health - damage)

            name = getattr(entity, "name", "Something")
            if entity is self.player:
                self.add_message(
                    f"You fall {fall_dist * 3} feet! ({damage} damage)",
                    "critical")
            else:
                self.add_message(
                    f"{name} falls {fall_dist * 3} feet!", "advisory")

        return fall_dist

    def _record_gossip(self, content: str, severity: float) -> None:
        """Add a gossip entry for the current region."""
        region = ""
        if self.current_local:
            region = self.current_local._region_name
        self.gossip.add(content, self.time.total_minutes // 1440,
                         region, severity)

    def _nearby_structure(self, tag: str, radius: int = 3):
        """Find a nearby functional structure with the given tag."""
        lmap = self.current_local
        if not lmap:
            return None
        px, py = self.player.local_x, self.player.local_y
        from src.construction import PlacedEquipment
        for sid, s in lmap.structures.items():
            if not isinstance(s, PlacedEquipment):
                continue
            if not s.functional:
                continue
            if tag not in s.functional_tags:
                continue
            # Check distance
            dx = abs(s.x - px)
            dy = abs(s.y - py)
            if max(dx, dy) <= radius:
                return s
        return None

    _TREE_TERRAINS = frozenset([
        13, 14, 15, 16, 17, 18, 19, 20, 21, 22,  # PINE…MAGNOLIA
        2,                                          # FOREST
    ])
    _CHOP_WORDS = frozenset([
        "chop", "fell", "cut down", "cut tree", "hack", "axe", "hatchet",
        "timber", "log", "fell tree",
    ])

    def _handle_read_book(self):
        """Player reads a book from inventory."""
        readable = []
        for i, item in enumerate(self.player.inventory):
            extra = getattr(item, "extra", {})
            if extra.get("readable") or extra.get("teaches_skill"):
                readable.append((i, item))
            # Also check by category/name
            elif any(w in item.name.lower() for w in
                     ("book", "guide", "manual", "bible", "reader",
                      "handbook", "almanac", "commentaries", "works of")):
                readable.append((i, item))

        if not readable:
            self.add_message("You don't have anything to read.", "advisory")
            self.advance_time(2)
            return

        if len(readable) == 1:
            _, book = readable[0]
        else:
            from src.menus import pick_from_list
            names = [item.display_name() for _, item in readable]
            idx = pick_from_list(self._console, self._ctx, "Read which book?", names)
            if idx is None or idx < 0:
                return
            _, book = readable[idx]

        from src.writing import read_book
        msgs, minutes = read_book(self.player, book, reading_minutes=30)
        for msg in msgs:
            self.add_message(msg, "advisory")
        self.advance_time(minutes)

    def _handle_build_action(self, action_text: str):
        """Route build/construct actions to the construction system."""
        if not self.construction:
            self.add_message("(Construction system unavailable.)", "advisory")
            self.advance_time(5)
            return

        from src.construction import EQUIPMENT_BLUEPRINTS
        a = action_text.lower()
        lmap = self.current_local
        px, py = self.player.local_x, self.player.local_y

        # Match against known equipment blueprints
        matched_key = None
        for key, bp in EQUIPMENT_BLUEPRINTS.items():
            if bp.name.lower() in a or key.replace("_", " ") in a:
                matched_key = key
                break

        if matched_key:
            # Build known equipment at player's position
            equip, msg = self.construction.start_equipment(
                matched_key, lmap, px + 1, py, self.player.inventory)
            self.add_message(msg, "advisory" if equip else "normal")
            if equip:
                # Work on it immediately
                skill = self.player.skills.get("engineering", 0)
                result_msg = self.construction.work_on_equipment(equip, 30, skill)
                self.add_message(result_msg, "advisory")
                self.player.gain_skill_xp("engineering", 3.0)
                self.advance_time(30)
            else:
                self.advance_time(5)
        else:
            # Try LLM custom structure
            ctx = self._build_llm_context()
            bp = self.construction.categorize_custom_equipment(action_text, ctx)
            if bp:
                self.add_message(f"You figure out how to build: {bp.name}.", "advisory")
                self.add_message(f"  Materials: {', '.join(f'{q}x {n}' for n, q in bp.materials)}", "normal")
                self.add_message(f"  Time: ~{bp.build_minutes} minutes. Skill: {bp.skill}.", "normal")
                equip, msg = self.construction.start_equipment(
                    bp.key, lmap, px + 1, py, self.player.inventory)
                self.add_message(msg, "advisory" if equip else "normal")
                if equip:
                    skill = self.player.skills.get(bp.skill, 0)
                    result_msg = self.construction.work_on_equipment(equip, 30, skill)
                    self.add_message(result_msg, "advisory")
                    self.player.gain_skill_xp(bp.skill, 3.0)
                    self.advance_time(30)
                else:
                    self.advance_time(5)
            else:
                self.add_message(
                    "You think about how to build that but can't figure it out.",
                    "normal")
                self.advance_time(5)

    def _apply_llm_terrain(self, action_text: str, resp):
        """
        Translate successful LLM action outcomes into tile mutations.
        Currently handles: tree felling → GROUND + log item.
        """
        from src.local_map import LocalTerrain
        if resp.outcome not in ("success", "partial"):
            return

        low = action_text.lower()
        lmap = self.current_local
        px, py = self.player.local_x, self.player.local_y

        # Tree felling
        if any(w in low for w in self._CHOP_WORDS):
            # Find nearest tree tile — standing on it OR adjacent (8-dir)
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    tx, ty = px + dx, py + dy
                    if not lmap.in_bounds(tx, ty):
                        continue
                    t = lmap.tiles[ty][tx].terrain
                    if t in self._TREE_TERRAINS:
                        lmap.tiles[ty][tx].terrain = LocalTerrain.GROUND
                        # Create a log item if success
                        if resp.outcome == "success":
                            from src.items import Item
                            log_item = Item(
                                id="log", name="Log", weight=12.0,
                                category="material",
                                description="A felled tree trunk, rough-cut.",
                            )
                            lmap.tiles[ty][tx].ground_items.append(log_item)
                            self.add_message(
                                "The tree crashes to the ground. A log lies where it stood.",
                                "advisory")
                        return  # only fell one tree per action

    # ── Combat ────────────────────────────────────────────────────────────

    def _open_combat(self):
        """K key — explicit attack menu. Targets NPCs and wildlife."""
        from src.menus import pick_from_list
        from src.combat import player_attack_npc, witness_reactions
        import random as _rnd

        lmap = self.current_local

        # Build unified target list sorted by distance
        px, py = self.player.local_x, self.player.local_y
        targets = []  # (distance, kind, obj, label)

        for n in self._tile_npcs():
            if n.alive:
                d = max(abs(n.local_x - px), abs(n.local_y - py))
                state = f" [{n.combat_state}]" if n.combat_state != "neutral" else ""
                targets.append((d, "npc", n,
                    f"{n.display_name()} ({d} tiles){state}"))

        for a in self.wildlife_mgr.get_animals(
                self.player.world_x, self.player.world_y,
                self.player.area_x, self.player.area_y):
            if a.alive and getattr(a, "local_z", 0) == self.player.local_z:
                d = max(abs(a.local_x - px), abs(a.local_y - py))
                targets.append((d, "animal", a,
                    f"{a.species.display_name} ({d} tiles)"))

        if not targets:
            self.add_message("Nothing nearby to fight.", "advisory")
            return

        # Sort by distance (closest first)
        targets.sort(key=lambda t: t[0])

        labels = [t[3] for t in targets]
        idx = pick_from_list(self._console, self._ctx, "Attack what?", labels)
        if idx is None:
            return

        dist, kind, target_obj, _ = targets[idx]

        # Rebuild npcs/animals lists for legacy code below
        npcs = [t[2] for t in targets if t[1] == "npc"]
        animals = [t[2] for t in targets if t[1] == "animal"]

        # Weapon selection — show what's in hands first
        weapons = [i for i in self.player.inventory if i.is_weapon()]
        weapon = None
        if weapons:
            # Mark which weapons are equipped
            w_labels = []
            for w in weapons:
                equipped = ""
                if self.player.right_hand and w.name == self.player.right_hand:
                    equipped = " [R.Hand]"
                elif self.player.left_hand and w.name == self.player.left_hand:
                    equipped = " [L.Hand]"
                ammo_str = ""
                if w.weapon_type == "firearm":
                    loaded = w.extra.get("loaded", 0)
                    cap = w.extra.get("capacity", 1)
                    ammo_str = f" ({loaded}/{cap})"
                w_labels.append(f"{w.display_name()}{ammo_str}{equipped}")
            w_labels.append("Unarmed")
            widx = pick_from_list(self._console, self._ctx, "Attack with?", w_labels)
            if widx is None:
                return
            if widx < len(weapons):
                weapon = weapons[widx]
                # Auto-equip if not in hand
                wname = weapon.name
                if (self.player.right_hand != wname and
                        self.player.left_hand != wname):
                    if not self.player.right_hand:
                        self.player.right_hand = wname
                    elif not self.player.left_hand:
                        self.player.left_hand = wname
                    else:
                        # Both hands full — ask to swap
                        swap = pick_from_list(self._console, self._ctx,
                            f"Equip {wname}? Hands full.",
                            [f"Replace R.Hand ({self.player.right_hand})",
                             f"Replace L.Hand ({self.player.left_hand})",
                             "Cancel"])
                        if swap == 0:
                            self.player.right_hand = wname
                        elif swap == 1:
                            self.player.left_hand = wname
                        else:
                            return
                    self.add_message(f"You ready the {wname}.", "normal")

        # ── Aimed shot selection (firearms and melee) ─────────────────────
        aimed_part = 0
        if weapon:
            from src.combat import AIMED_SHOTS
            aim_labels = [a[0] for a in AIMED_SHOTS]
            aim_idx = pick_from_list(self._console, self._ctx, "Aim where?", aim_labels)
            if aim_idx is None:
                return
            aimed_part = aim_idx

        # ── NPC target ────────────────────────────────────────────────────
        if kind == "npc":
            target = target_obj

            # Range check: melee/unarmed must be adjacent
            is_ranged = weapon and weapon.weapon_type == "firearm"
            if not is_ranged and dist > 1:
                self.add_message(
                    f"{target.display_name()} is too far for melee. "
                    f"Get closer or use a firearm.", "advisory")
                return

            # Ranged: apply distance penalty to hit
            if is_ranged and dist > 5:
                self.add_message(f"(Range: {dist} tiles — accuracy reduced)", "advisory")
            event = player_attack_npc(self.player, target, weapon,
                                      distance=dist, aimed_part=aimed_part)
            self.add_message(event.message, "normal")

            # Log to After Action Report
            region = lmap._region_name if lmap else ""
            self.journal.begin_combat(self.time.date_string, region)
            self.journal.log_combat_event(event.message,
                "critical" if event.killed else "normal")

            if event.hit:
                skill = "firearms" if (weapon and weapon.weapon_type == "firearm") \
                        else "survival"
                self.player.gain_skill_xp(skill, 3.0 if event.killed else 1.5)
                # Blood on the ground
                self._splatter_blood(lmap, target.local_x, target.local_y,
                                     2 if event.killed else 1)
                if event.killed:
                    self._blood_pool(lmap, target.local_x, target.local_y,
                                     radius=2, heavy=True)
                    self.journal.log_enemy_killed(target.name)
                    lmap.invalidate_terrain_cache()
                if event.defender_fled:
                    self.journal.log_enemy_fled(target.name)

            witnesses = self._witnesses_near(
                self.player.local_x, self.player.local_y,
                exclude_names={target.name})
            for msg in witness_reactions(witnesses, self.player.name,
                                         target.name, event.killed):
                self.add_message(msg, "advisory")

            # Record crime
            if event.hit:
                lmap = self.current_local
                region = lmap._region_name if lmap else ""
                self.legal.record_crime(
                    "murder" if event.killed else "assault",
                    self.time.total_minutes // 1440,
                    self.player.world_x, self.player.world_y, region,
                    victim_name=target.name,
                    victim_npc_id=target.npc_id,
                    self_defense=(target.combat_state == "hostile"),
                    nearby_npcs=witnesses,
                )
                # Reputation + gossip
                if event.killed:
                    self.reputation.adjust(region, -40 if target.combat_state != "hostile" else -5)
                    self._record_gossip(f"Killed {target.name}", -0.8 if target.combat_state != "hostile" else -0.2)
                else:
                    self.reputation.adjust(region, -15 if target.combat_state != "hostile" else -2)
                    self._record_gossip(f"Attacked {target.name}", -0.4)

            if event.hit and not event.killed and not event.defender_fled:
                if target.combat_state == "neutral":
                    target.combat_state = "hostile"
                    self.add_message(
                        f"{target.name} draws a weapon and turns on you.", "critical")

        # ── Animal target ─────────────────────────────────────────────────
        elif kind == "animal":
            animal = target_obj
            sp     = animal.species

            # Aimed shot modifiers
            from src.combat import AIMED_SHOTS
            aim = AIMED_SHOTS[aimed_part] if 0 <= aimed_part < len(AIMED_SHOTS) else AIMED_SHOTS[0]
            aim_label, aim_penalty, aim_dmg_mult, aim_special = aim

            # Hit roll: firearms skill vs animal's dodge (agility-proxy = size)
            size_defense = {"small": 12, "medium": 9, "large": 6, "very_large": 5}
            defense   = size_defense.get(sp.size, 8)
            skill_val = self.player.skills.get("firearms" if (weapon and weapon.weapon_type == "firearm") else "survival", 0)
            attr_val  = self.player.attributes.get("agility" if (weapon and weapon.weapon_type == "firearm") else "strength", 10)
            roll      = _rnd.randint(1, 20) + skill_val // 2 + attr_val // 3 + aim_penalty

            if roll < defense:
                aim_str = f" (aimed: {aim_label})" if aimed_part > 0 else ""
                self.add_message(f"You miss the {sp.display_name}.{aim_str}", "normal")
            else:
                # Damage with aimed shot multiplier
                if weapon:
                    dmg = max(1, int(_rnd.randint(weapon.damage_min, weapon.damage_max) * aim_dmg_mult))
                else:
                    dmg = max(1, int(_rnd.randint(1, 4) * aim_dmg_mult))

                # Headshot instant kill chance on animals too
                if aim_special == "head" and dmg >= 5 and _rnd.random() < 0.6:
                    dmg = max(dmg, int(animal.health) + 10)

                animal.take_damage(float(dmg))
                skill_name = "firearms" if (weapon and weapon.weapon_type == "firearm") else "survival"

                # Blood on ground
                self._splatter_blood(lmap, animal.local_x, animal.local_y,
                                     2 if animal.state == "dead" else 1)

                if animal.state == "dead":
                    self.add_message(
                        f"The {sp.display_name} drops. Blood pools beneath it. "
                        f"[P] to butcher.",
                        "normal")
                    self._blood_pool(lmap, animal.local_x, animal.local_y,
                                     radius=2, heavy=True)
                    self.player.gain_skill_xp(skill_name, 5.0)
                elif animal.state == "downed":
                    self.add_message(
                        f"The {sp.display_name} collapses, breathing hard. "
                        f"[P] to butcher.",
                        "normal")
                    self.player.gain_skill_xp(skill_name, 3.0)
                elif animal.state == "wounded_fleeing":
                    self.add_message(
                        f"The {sp.display_name} staggers and runs, leaving a blood trail.",
                        "advisory")
                    self.player.gain_skill_xp(skill_name, 1.5)
                else:
                    self.add_message(
                        f"You hit the {sp.display_name}. It recoils, bleeding.",
                        "normal")
                    self.player.gain_skill_xp(skill_name, 1.5)
                    if sp.danger_level == 2 and animal.state not in ("fleeing", "wounded_fleeing"):
                        animal.state = "hostile"
                        self.add_message(
                            f"The wounded {sp.display_name} turns on you!", "critical")

        self._npc_combat_tick()
        self.advance_time(1)   # combat round = ~1 minute (seconds really, but min is floor)

    def _npc_combat_tick(self):
        """
        Called after every player action. Hostile NPCs attack; fleeing NPCs move.
        Surrendered and neutral NPCs do nothing.
        """
        import random
        from src.combat import npc_attack_player, incap_message, combat_taunt
        lmap = self.current_local
        for npc in self._tile_npcs():
            if not npc.alive:
                continue
            # Badly wounded NPCs emit incapacitation flavor
            if npc.health < 25 and npc.health > 0 and npc.combat_state != "dead":
                if random.random() < 0.4:
                    self.add_message(incap_message(npc.name), "normal")
                    self._splatter_blood(lmap, npc.local_x, npc.local_y, 1)
            if npc.combat_state == "hostile":
                # Combat taunt (30% chance per tick)
                if random.random() < 0.3:
                    hp_pct = npc.health / max(npc.wounds.max_blood, 1)
                    taunt = combat_taunt(npc.name, hp_pct, True)
                    if taunt:
                        self.add_message(taunt, "normal")
                        self.journal.log_combat_event(taunt)
                # Attack
                event = npc_attack_player(npc, self.player)
                self.add_message(event.message,
                                 "critical" if event.hit else "normal")
                self.journal.log_combat_event(event.message,
                    "critical" if event.hit else "normal")
                if event.hit:
                    self._splatter_blood(lmap,
                        self.player.local_x, self.player.local_y, 1)
                    if hasattr(event, 'wound_desc') and event.wound_desc:
                        self.journal.log_player_wound(event.wound_desc)
                if event.killed:
                    self.journal.end_combat()
                    self._trigger_death(f"Killed by {npc.name}.")
            elif npc.combat_state == "fleeing":
                # Move NPC away from player (simple — just mark not present
                # after a few ticks; full pathfinding TBD)
                npc.local_x += 2 if npc.local_x < self.player.local_x else -2
                npc.local_y += 2 if npc.local_y < self.player.local_y else -2
                if (abs(npc.local_x - self.player.local_x) > 20 or
                        abs(npc.local_y - self.player.local_y) > 20):
                    npc.present = False
        self._check_combat_state()

    def _check_combat_state(self):
        """Check if any hostiles nearby — trigger combat mode if so."""
        if self.state != GameState.LOCAL_MAP:
            return
        hostiles = [n for n in self._tile_npcs()
                    if n.alive and n.combat_state == "hostile"]
        hostile_animals = [a for a in self.wildlife_mgr.get_animals(
            self.player.world_x, self.player.world_y,
            self.player.area_x, self.player.area_y)
            if a.alive and a.state == "hostile"]
        if hostiles or hostile_animals:
            self.combat_mode_pending = True

    def _apply_llm_npc_effects(self, resp):
        """Apply npc_damage and npc_killed from an LLMResponse to actual NPCs."""
        from src.combat import _check_npc_morale, witness_reactions

        npcs_by_name = {n.name: n for n in self._tile_npcs() if n.alive}

        # Outright kills from LLM judgment (e.g. dynamite in a lake)
        for name in resp.npc_killed:
            npc = npcs_by_name.get(name)
            if npc:
                npc.health = 0
                npc.alive = False
                npc.present = False
                npc.combat_state = "dead"
                self.add_message(f"{name} is dead.", "critical")

        # Damage amounts
        killed_names = set(resp.npc_killed)
        for name, dmg in resp.npc_damage.items():
            if name in killed_names:
                continue
            npc = npcs_by_name.get(name)
            if npc:
                killed = npc.take_damage(float(dmg))
                if killed:
                    self.add_message(f"{name} is killed.", "critical")
                    killed_names.add(name)
                elif npc.combat_state == "fleeing":
                    self.add_message(f"{name} turns and runs.", "advisory")
                elif npc.combat_state == "neutral" and dmg > 5:
                    npc.combat_state = "hostile"
                    self.add_message(
                        f"{name} draws a weapon, eyes cold.", "critical")

        # Witnesses to any deaths + crime recording
        all_victims = killed_names | set(resp.npc_damage.keys())
        lmap = self.current_local
        region = lmap._region_name if lmap else ""
        for victim in all_victims:
            was_killed = victim in killed_names
            witnesses = self._witnesses_near(
                self.player.local_x, self.player.local_y,
                exclude_names=all_victims)
            for msg in witness_reactions(witnesses, self.player.name,
                                         victim, was_killed):
                self.add_message(msg, "advisory")
            # Record crime
            victim_npc = npcs_by_name.get(victim)
            self.legal.record_crime(
                "murder" if was_killed else "assault",
                self.time.total_minutes // 1440,
                self.player.world_x, self.player.world_y, region,
                victim_name=victim,
                victim_npc_id=getattr(victim_npc, "npc_id", ""),
                nearby_npcs=witnesses,
            )
            self.reputation.adjust(region, -40 if was_killed else -15)

    def _build_llm_context(self) -> dict:
        """Snapshot of game state for the LLM prompt."""
        lmap = self.current_local
        tile = lmap.tile_at(self.player.local_x, self.player.local_y)

        from src.local_map import LOCAL_GLYPH
        terrain_name = {
            0: "bare ground", 1: "grass", 2: "forest", 3: "rock",
            4: "water", 5: "gravel bar", 6: "bedrock", 7: "mud",
            8: "sand", 9: "brush", 10: "pit", 11: "spoil pile", 12: "tundra",
        }.get(tile.terrain, "ground")

        all_npcs   = self._tile_npcs()
        nearby_npcs = [n.short_desc() for n in all_npcs]
        hostile_npcs = [n.name for n in all_npcs
                        if n.alive and n.combat_state == "hostile"]

        ctx = {
            "year":       self.time.year,
            "time_of_day": self.time.period,
            "region":     lmap._region_name or lmap.world_map.get_region(
                              lmap.world_x, lmap.world_y),
            "terrain":    terrain_name,
            "weather":    "clear",   # TODO: wire weather system
            "skills":     {k: v for k, v in self.player.skills.items() if v > 0},
            "attributes": self.player.attributes,
            "inventory":  [getattr(i, "name", str(i))
                           for i in self.player.inventory],
            "nearby":     ", ".join(nearby_npcs) if nearby_npcs else "",
            "hostile_npcs": hostile_npcs,
            "gold_oz":    round(self.player.gold_oz, 4),
            "gold_grade": round(tile.gold_grade, 3),
            "dig_depth":  tile.dig_depth,
        }

        # ── System contexts for the LLM ──────────────────────────────
        from src.llm_wounds import build_wound_context, build_clothing_context

        ctx["wound_context"] = build_wound_context(self.player.wounds)
        if self.player.worn:
            ctx["clothing_context"] = build_clothing_context(self.player.worn)

        # Companions
        if self.companion_mgr.links:
            comp_lines = []
            for link in self.companion_mgr.links.values():
                status = f"busy: {link.current_task}" if link.currently_tasked else "idle"
                comp_lines.append(f"{link.name} ({link.role_label}, {status})")
            ctx["companions"] = ", ".join(comp_lines)

        # Legal warrants
        if self.legal.has_active_warrant():
            ctx["legal_status"] = "WANTED — active warrant"

        return ctx

    def _handle_fast_travel(self):
        """Enter pressed on zoomed-out map — initiate fast travel to cursor."""
        cx, cy = self.map_cursor_x, self.map_cursor_y
        if cx == self.player.world_x and cy == self.player.world_y:
            self.add_message("You're already here.", "normal")
            return

        # Check if destination is valid
        if not self.world.in_bounds(cx, cy):
            self.add_message("Can't travel there.", "normal")
            return

        from src.fast_travel import calculate_trip, fast_travel_ui, execute_trip, encounter_ui

        # Calculate trip
        estimate = calculate_trip(self.player, self.world, cx, cy)

        # Check for ocean
        if any("ocean" in w.lower() for w in estimate.warnings):
            self.add_message("Route crosses ocean — can't travel there.", "normal")
            return

        # Get destination name
        loc = self.world.get_location_at(cx, cy)
        dest_name = loc.name if loc else f"({cx}, {cy})"

        # Show confirmation UI
        style = fast_travel_ui(self._console, self._ctx, estimate,
                                self.player, dest_name)
        if style is None:
            return  # cancelled

        # Execute the trip
        result, final_pos = execute_trip(self, estimate, style)

        if result == "encounter":
            enc_wx, enc_wy = final_pos
            # Show encounter options
            choice = encounter_ui(self._console, self._ctx, enc_wx, enc_wy, self.world)
            if choice == "investigate":
                self.add_message("You investigate what's ahead...", "normal")
                # Player is already at the encounter tile
            elif choice == "avoid":
                # Add 1-2 hours and continue to destination
                self.time.advance(random.randint(60, 120))
                _dest_wx, _dest_wy = estimate.path[-1]
                from src.fast_travel import _teleport_player
                _teleport_player(self, _dest_wx, _dest_wy)
                self.player.survival.fatigue = max(20, self.player.survival.fatigue - 5)
                self.add_message("You go around and continue on your way.", "normal")
            elif choice == "run":
                # Agility check
                agi = self.player.attributes.get("agility", 10)
                if random.randint(1, 20) + agi // 3 >= 10:
                    _dest_wx, _dest_wy = estimate.path[-1]
                    from src.fast_travel import _teleport_player
                    _teleport_player(self, _dest_wx, _dest_wy)
                    self.add_message("You sprint past without incident.", "normal")
                else:
                    self.add_message("You couldn't avoid it — something's coming!", "critical")
        elif result == "ocean_blocked":
            self.add_message("The route is blocked by water.", "normal")

        # Reset cursor to player position
        self.map_cursor_x = self.player.world_x
        self.map_cursor_y = self.player.world_y

    def _zoom_out(self):
        if self.map_level_index < len(MAP_LEVELS) - 1:
            self.map_level_index += 1
            self.state = MAP_LEVELS[self.map_level_index]
            self.map_cursor_x = self.player.world_x
            self.map_cursor_y = self.player.world_y
            name = MAP_LEVEL_NAMES[self.state]
            self.add_message(f"{name} view. Arrows=move cursor. Enter=travel. [/]=zoom.", "normal")
        else:
            self.add_message("Already at maximum zoom out.", "normal")

    def _zoom_in(self):
        if self.map_level_index > 0:
            self.map_level_index -= 1
            self.state = MAP_LEVELS[self.map_level_index]
            name = MAP_LEVEL_NAMES[self.state]
            if self.state == GameState.LOCAL_MAP:
                self.add_message("Local map.", "normal")
                self.recompute_fov()
            else:
                self.add_message(f"{name} view.", "normal")
        else:
            self.add_message("Already at local map.", "normal")

    def _check_theft_on_leave(self):
        """Check if player is leaving a settlement with unpaid items."""
        lmap = self.current_local
        if not (hasattr(lmap, 'town_layout') and lmap.town_layout):
            return
        stolen = [i for i in self.player.inventory if getattr(i, 'unpaid', False)]
        if not stolen:
            return
        # Theft detected — check for witnesses
        witnesses = self._witnesses_near(
            self.player.local_x, self.player.local_y)
        names = ", ".join(dict.fromkeys(i.name for i in stolen[:3]))
        if len(stolen) > 3:
            names += f" +{len(stolen)-3} more"
        if witnesses:
            region = lmap._region_name if lmap else ""
            self.legal.record_crime(
                "theft", self.time.total_minutes // 1440,
                self.player.world_x, self.player.world_y, region,
                nearby_npcs=witnesses)
            self.add_message(
                f"You're spotted leaving with unpaid goods: {names}! Theft!",
                "critical")
            self.reputation.adjust(region, -15)
            self._record_gossip(f"Stole {names} from a store", -0.5)
        else:
            self.add_message(
                f"You slip away with: {names}. No one noticed.", "advisory")
        # Clear unpaid tags — crime recorded (or gotten away with)
        for i in stolen:
            i.unpaid = False

    def _transition_patch(self, dax: int, day: int, entry_x: int, entry_y: int):
        """Step into an adjacent area patch, wrapping across world tile boundaries."""
        # Check for theft before leaving current patch
        self._check_theft_on_leave()

        from src.constants import AREAS_PER_WORLD
        new_ax = self.player.area_x + dax
        new_ay = self.player.area_y + day
        new_wx, new_wy = self.player.world_x, self.player.world_y

        # Wrap area coords to world tile boundary
        if new_ax < 0:
            new_wx -= 1; new_ax = AREAS_PER_WORLD - 1
        elif new_ax >= AREAS_PER_WORLD:
            new_wx += 1; new_ax = 0
        if new_ay < 0:
            new_wy -= 1; new_ay = AREAS_PER_WORLD - 1
        elif new_ay >= AREAS_PER_WORLD:
            new_wy += 1; new_ay = 0

        if not self.world.in_bounds(new_wx, new_wy):
            self.add_message("There is nothing beyond the horizon.", "normal")
            return

        self.player.world_x = new_wx
        self.player.world_y = new_wy
        self.player.area_x = new_ax
        self.player.area_y = new_ay
        self.world.mark_visited(new_wx, new_wy)
        new_lmap = self._ensure_local(new_wx, new_wy, new_ax, new_ay)
        self.player.local_x = max(1, min(new_lmap.width  - 2, entry_x))
        self.player.local_y = max(1, min(new_lmap.height - 2, entry_y))
        # Set z to solid ground at new position
        self.player.local_z = new_lmap.ground_z(
            self.player.local_x, self.player.local_y)
        self._preload_neighbors()
        self.recompute_fov()

        # Show location name when entering a new world tile's center patch
        center = AREAS_PER_WORLD // 2
        if new_ax == center and new_ay == center:
            loc = self.world.get_location_at(new_wx, new_wy)
            if loc:
                self.add_message(f"You enter {loc.name}.", "normal")

        # Location discovery when entering new world tiles
        from src.discovery import roll_location_discovery
        disc = roll_location_discovery(self, new_wx, new_wy)
        if disc:
            self.add_message(disc, "advisory")
            # Drop to area view momentarily to show the icon
            # (just show message — player can zoom out to see it)

    def _do_move(self, dx: int, dy: int):
        if self.state == GameState.LOCAL_MAP:
            lmap = self.current_local
            nx = self.player.local_x + dx
            ny = self.player.local_y + dy

            # Walk off the edge → transition to adjacent area patch
            if nx < 0:
                self._transition_patch(-1, 0,
                    entry_x=lmap.width - 2, entry_y=self.player.local_y)
                return
            if nx >= lmap.width:
                self._transition_patch(1, 0,
                    entry_x=1, entry_y=self.player.local_y)
                return
            if ny < 0:
                self._transition_patch(0, -1,
                    entry_x=self.player.local_x, entry_y=lmap.height - 2)
                return
            if ny >= lmap.height:
                self._transition_patch(0, 1,
                    entry_x=self.player.local_x, entry_y=1)
                return

            # Bump detection — check for hostile animal at destination
            animal_at = self.wildlife_mgr.get_at(
                self.player.world_x, self.player.world_y,
                self.player.area_x, self.player.area_y,
                nx, ny, lz=self.player.local_z)
            if animal_at and animal_at.alive and animal_at.state == "hostile":
                import random as _rnd
                sp = animal_at.species
                size_defense = {"small": 12, "medium": 9, "large": 6, "very_large": 5}
                defense  = size_defense.get(sp.size, 8)
                weapons  = [i for i in self.player.inventory if i.is_weapon()]
                weapon   = weapons[0] if weapons else None
                skn      = "firearms" if (weapon and weapon.weapon_type == "firearm") else "survival"
                sv       = self.player.skills.get(skn, 0)
                av       = self.player.attributes.get("agility" if skn == "firearms" else "strength", 10)
                roll     = _rnd.randint(1, 20) + sv // 2 + av // 3
                if roll >= defense:
                    dmg = _rnd.randint(weapon.damage_min, weapon.damage_max) if weapon \
                          else _rnd.randint(1, 4)
                    animal_at.take_damage(float(dmg))
                    if animal_at.state == "dead":
                        self.add_message(
                            f"The {sp.display_name} drops. [P] to butcher.",
                            "normal")
                        self.player.gain_skill_xp(skn, 5.0)
                    elif animal_at.state == "downed":
                        self.add_message(
                            f"The {sp.display_name} goes down. [P] to butcher.",
                            "normal")
                        self.player.gain_skill_xp(skn, 3.0)
                    elif animal_at.state == "wounded_fleeing":
                        self.add_message(
                            f"The {sp.display_name} staggers and runs. Follow it.",
                            "advisory")
                        self.player.gain_skill_xp(skn, 1.5)
                    else:
                        self.add_message(f"You strike the {sp.display_name} ({dmg} dmg).", "normal")
                        self.player.gain_skill_xp(skn, 1.5)
                else:
                    self.add_message(f"Your blow misses the {sp.display_name}!", "normal")
                self._npc_combat_tick()
                self.advance_time(5)
                return

            # Bump detection — check destination tile for NPC
            npc_at = self.npc_mgr.get_at(nx, ny, z=self.player.local_z)
            if npc_at and npc_at.present and npc_at.alive:
                if npc_at.combat_state == "hostile":
                    # Auto-attack hostile NPC on bump
                    from src.combat import player_attack_npc, witness_reactions
                    weapons = [i for i in self.player.inventory if i.is_weapon()]
                    weapon = weapons[0] if weapons else None
                    event = player_attack_npc(self.player, npc_at, weapon)
                    self.add_message(event.message,
                                     "critical" if event.hit else "normal")
                    if event.hit:
                        skill = ("firearms" if weapon and weapon.weapon_type == "firearm"
                                 else "survival")
                        self.player.gain_skill_xp(skill,
                                                   3.0 if event.killed else 1.5)
                    witnesses = self._witnesses_near(
                        self.player.local_x, self.player.local_y,
                        exclude_names={npc_at.name})
                    for msg in witness_reactions(witnesses, self.player.name,
                                                 npc_at.name, event.killed):
                        self.add_message(msg, "advisory")
                    # Record crime
                    if event.killed:
                        crime_type = "murder"
                    else:
                        crime_type = "assault"
                    lmap = self.current_local
                    region = lmap._region_name if lmap else ""
                    self.legal.record_crime(
                        crime_type, self.time.total_minutes // 1440,
                        self.player.world_x, self.player.world_y, region,
                        victim_name=npc_at.name,
                        victim_npc_id=npc_at.npc_id,
                        self_defense=(npc_at.combat_state == "hostile"),
                        nearby_npcs=witnesses,
                    )
                    if npc_at.combat_state != "hostile":
                        self.reputation.adjust(region, -40 if event.killed else -15)
                    else:
                        self.reputation.adjust(region, -5 if event.killed else -2)
                    self._npc_combat_tick()
                    self.advance_time(5)
                else:
                    # Friendly/neutral bump — show who it is, prompt to talk
                    dist = (abs(npc_at.local_x - self.player.local_x) +
                            abs(npc_at.local_y - self.player.local_y))
                    rel  = npc_at.rel_label()
                    self.add_message(
                        f"{npc_at.display_name()} ({npc_at.occupation}, {rel}). "
                        f"Press [T] to talk.",
                        "normal")
                return

            # Check edge-based walls (construction system)
            wall_blocked = False
            if hasattr(lmap, 'wall_grid') and lmap.wall_grid:
                wall_blocked = not lmap.wall_grid.can_pass(
                    self.player.local_x, self.player.local_y, nx, ny,
                    z=self.player.local_z)

            # Z-level transition check
            from src.constants import CLIMB_TIME_MULT
            cur_z = self.player.local_z
            target_sz = int(lmap.surface_z[ny][nx]) if lmap.in_bounds(nx, ny) else cur_z
            z_delta = 0
            z_blocked = False

            if target_sz != cur_z:
                diff = target_sz - cur_z
                if abs(diff) == 1:
                    # 1 z-level difference = natural slope, always passable
                    # (ramps make it faster but aren't required for ±1)
                    z_delta = diff
                elif abs(diff) >= 2:
                    # Cliff — need stairs or ladder to pass
                    z_blocked = True

            if z_blocked:
                self.add_message("A cliff blocks the way. Build stairs to pass.", "normal")
                self.advance_time(1)
                return

            if lmap.is_passable(nx, ny) and not wall_blocked:
                cost_secs = self.player.move(dx, dy)  # returns seconds
                if z_delta != 0:
                    self.player.local_z += z_delta
                    cost_secs = int(cost_secs * CLIMB_TIME_MULT)
                # Gravity check — if stepped into open air, fall
                self._apply_gravity(self.player, lmap)
                self.time.advance_seconds(cost_secs)
                self.recompute_fov()
                # Random walking event (very rare on local movement)
                from src.walking_events import roll_walking_event
                evt = roll_walking_event(self, lmap,
                    self.player.local_x, self.player.local_y)
                if evt:
                    self.add_message(evt[0], evt[1])
                # Notify if there are items on the new tile
                new_tile = lmap.tile_at(self.player.local_x, self.player.local_y)
                if new_tile.ground_items:
                    names = ", ".join(dict.fromkeys(
                        i.name for i in new_tile.ground_items[:3]))
                    extra = f" +{len(new_tile.ground_items)-3} more" \
                            if len(new_tile.ground_items) > 3 else ""
                    self.add_message(
                        f"Items here: {names}{extra}. [P] to pick up.",
                        "normal")
            else:
                self.add_message("The way is blocked.", "normal")
        else:
            # State/Country views jump multiple world tiles per keypress (stride matches visual scale)
            stride = {GameState.STATE_MAP: 5, GameState.COUNTRY_MAP: 20}.get(self.state, 1)
            total_cost = 0
            for _ in range(stride):
                cost = self.player.move_world(dx, dy, self.world)
                if cost == 0:
                    break
                total_cost += cost

            # Reveal tiles around new position — area = wide view, others = narrow
            reveal_r = {
                GameState.AREA_MAP:     5,
                GameState.COUNTY_MAP:   2,
                GameState.STATE_MAP:    3,
                GameState.COUNTRY_MAP:  4,
            }.get(self.state, 2)
            self.world.mark_visited_radius(
                self.player.world_x, self.player.world_y, reveal_r)

            # Time advances for area and county (actual foot travel); state/country = cursor nav
            if total_cost > 0 and self.state in (GameState.AREA_MAP, GameState.COUNTY_MAP):
                self.advance_time(total_cost)
                loc = self.world.get_location_at(self.player.world_x, self.player.world_y)
                if loc:
                    self.add_message(f"You arrive at {loc.name}.", "normal")

    # ── Character creation ────────────────────────────────────────────────

    def _apply_character(self, cc: dict):
        """Apply character-creation choices to player and game state."""
        from src.constants import LOCAL_WIDTH, LOCAL_HEIGHT

        self.player.name       = cc["name"]
        self.player.attributes = dict(cc["attributes"])
        self.player.cash       = cc["cash"]
        self.player.world_x    = cc["world_x"]
        self.player.world_y    = cc["world_y"]
        self.player.area_x     = 7   # center patch of world tile
        self.player.area_y     = 7
        self.player.local_x    = LOCAL_WIDTH  // 2
        self.player.local_y    = LOCAL_HEIGHT // 2

        # Apply skills from character creation (includes background bonuses)
        if "skills" in cc and cc["skills"]:
            for key, val in cc["skills"].items():
                if key in self.player.skills:
                    self.player.skills[key] = min(10, val)
        else:
            # Fallback: old-style background bonuses only
            attr_keys = set(self.player.attributes.keys())
            for key, bonus in cc.get("skill_bonuses", {}).items():
                if key in attr_keys:
                    self.player.attributes[key] = (
                        self.player.attributes.get(key, 10) + bonus)
                else:
                    self.player.skills[key] = min(
                        10, self.player.skills.get(key, 0) + bonus)

        # Reveal world map around the actual start position (not the default Sacramento)
        self.world.mark_visited(self.player.world_x, self.player.world_y)
        self.world.mark_visited_radius(self.player.world_x, self.player.world_y, 8)
        # Generate local map for the real start and its neighbors
        start_lmap = self._ensure_local(self.player.world_x, self.player.world_y,
                                        self.player.area_x, self.player.area_y)
        self._snap_player_near_water(start_lmap)
        self.player.local_z = start_lmap.ground_z(
            self.player.local_x, self.player.local_y)
        self._preload_neighbors()

        # Advance time to the chosen era's start year
        # (GameTime base is April 1, 1849; offset by years elapsed)
        START_YEAR = 1849
        year_diff  = cc["start_year"] - START_YEAR
        self.time.total_minutes = year_diff * 365 * 24 * 60

        # Seed the opening journal entry for this character
        from src.time_system import MONTH_NAMES
        mo  = MONTH_NAMES[cc["start_month"]]
        self.journal.diary.clear()
        self.journal.rumors.clear()
        self.journal.letters.clear()
        self.journal.places.clear()
        self.journal.add_diary(
            f"{mo} 1, {cc['start_year']}",
            f"Arrived in {cc['era']['region']}. "
            f"The land is rough and the competition is real. "
            f"I am {cc['name']}, and I did not come this far to go home empty-handed.",
        )

        # Clear default messages and greet the player
        self.messages.clear()
        self.add_message(
            f"Welcome, {cc['name']}. "
            f"Era: {cc['era']['name']}. "
            f"Background: {cc['background']['name']}.",
            "normal")

    # ── Main loop ─────────────────────────────────────────────────────────

    def run(self):
        tileset = tcod.tileset.load_truetype_font(
            "data/fonts/DejaVuSansMono.ttf", 12, 12
        ) if False else tcod.tileset.load_tilesheet(
            "data/fonts/terminal12x12_gs_ro.png", 16, 16,
            tcod.tileset.CHARMAP_CP437,
        )

        with tcod.context.new(
            columns=SCREEN_WIDTH,
            rows=SCREEN_HEIGHT,
            tileset=tileset,
            title=TITLE,
            vsync=True,
        ) as ctx:
            console = tcod.console.Console(SCREEN_WIDTH, SCREEN_HEIGHT, order="F")
            self.renderer = Renderer(console)
            self._console = console
            self._ctx     = ctx

            # Character creation — runs before the game loop
            from src.char_create import run_character_creation
            cc = run_character_creation(console, ctx)
            if cc is None:
                return   # player quit from name screen
            self._apply_character(cc)

            self.recompute_fov()

            # Start background music
            self.music.play_shuffle()

            # Flush stale events and ensure keyboard focus
            for _ in tcod.event.get():
                pass
            ctx.sdl_window.raise_window()
            # Stop text input mode so letter keys arrive as KeyDown not TextInput
            try:
                ctx.sdl_window.stop_text_input()
            except Exception:
                pass

            while True:
                lmap = self.current_local if self.state == GameState.LOCAL_MAP else None
                self.player.recalc_weight()

                self.renderer.render_all(
                    lmap, self.world, self.player, self.messages,
                    state=self.state, locals_dict=self.locals,
                    gold_overlay=self.show_gold_overlay,
                    cursor_x=self.map_cursor_x if self.map_level_index > 0 else -1,
                    cursor_y=self.map_cursor_y if self.map_level_index > 0 else -1,
                )
                if self.state == GameState.LOCAL_MAP and lmap:
                    _on_map = self._tile_npcs()
                    self.renderer.draw_npcs(_on_map, lmap, self.player)
                    self.renderer.draw_npc_sidebar(_on_map, self.player)
                    _animals = self.wildlife_mgr.get_animals(
                        self.player.world_x, self.player.world_y,
                        self.player.area_x, self.player.area_y)
                    self.renderer.draw_wildlife(_animals, lmap, self.player)
                self.renderer.draw_poi_indicators(
                    self.player, self.dynamic_locs, self.world)
                # Fire rendering
                if hasattr(lmap, '_fire') and lmap._fire and lmap._fire.active:
                    self.renderer.draw_fire(lmap._fire, lmap, self.player)
                self.renderer.draw_pack_animals(self.player)
                # Time/date in sidebar
                console.print(
                    82, 46,
                    self.time.date_string,
                    fg=(180, 180, 180), bg=(0, 0, 0)
                )
                console.print(
                    82, 47,
                    self.time.time_string + "  " + self.time.period.capitalize(),
                    fg=(180, 180, 180), bg=(0, 0, 0)
                )
                ctx.present(console)

                # Auto-enter combat mode if hostiles detected
                if self.combat_mode_pending:
                    self.combat_mode_pending = False
                    from src.combat_mode import enter_combat_mode
                    enter_combat_mode(self, console, ctx)

                # Auto-advance music track when current one ends
                self.music.check_advance()

                # Poll keyboard state directly — SDL3 on some Windows
                # configs doesn't generate KeyDown events for letter keys
                self._poll_keyboard_state()

                for event in tcod.event.wait(timeout=0.05):
                    if not self.handle_event(event):
                        return
