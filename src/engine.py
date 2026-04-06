"""
Main game engine: event loop, state management, input dispatch.
"""

import os
import random
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
        self.era_id   = "gold_rush"  # set by _apply_character
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
        from src.trapping import TrapManager
        self.trap_mgr        = TrapManager()
        from src.pack_animals import PackAnimalManager
        self.animal_mgr      = PackAnimalManager()
        self.player._animal_mgr = self.animal_mgr
        from src.claims import ClaimManager
        self.claim_mgr       = ClaimManager()
        from src.vehicles import VehicleManager
        self.vehicle_mgr     = VehicleManager()
        from src.bounty_system import BountyBoard
        self.bounty_board    = BountyBoard()
        from src.newspaper import NewspaperSystem
        self.newspaper       = NewspaperSystem()
        from src.property import PropertyManager
        self.property_mgr    = PropertyManager()
        from src.rival_prospectors import RivalProspectorSystem
        self.rival_system    = RivalProspectorSystem()
        self.marriage_state  = None  # set when player marries
        from src.tribal_system import TribalSystem
        self.tribal          = TribalSystem(seed=42)
        from src.war_system import WarSystem
        self.war_system      = WarSystem()
        from src.town_services import TownServiceRegistry
        self.town_services   = TownServiceRegistry()
        _music_dir = os.path.join(
            os.environ.get('GAME_DATA_ROOT', '.'), "music")
        self.music           = MusicManager(_music_dir)

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
            mode=_cfg.get("llm_mode", "local"),
            api_key=_cfg.get("llm_api_key", ""),
            api_model=_cfg.get("llm_api_model", "claude-sonnet-4-20250514"),
        )

        # ── Post-LLM system wiring ────────────────────────────────────
        from src.economy import TradeEngine
        from src.item_factory import ItemFactory
        from src.business import BusinessManager
        from src.construction import ConstructionManager

        self.trade        = TradeEngine(self.llm)
        self.item_factory = ItemFactory(self.llm)
        self.business_mgr = BusinessManager(self.llm)
        self.player._biz_mgr = self.business_mgr  # for trade price recording
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
            self.wildlife_mgr.spawn_for_local(self.locals[key], wx, wy, ax, ay,
                                               year=self.time.year,
                                               season=self.time.season)
        lm = self.locals[key]
        # Ensure world elevation is set (backward compat for old saves)
        if not getattr(lm, 'world_elevation_ft', 0) and self.world:
            lm.world_elevation_ft = self.world.get_elevation(wx, wy)
        return lm

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
                # Find a walkable random position (try up to 20 times)
                for _attempt in range(20):
                    rx = rng.randint(5, lmap.width - 5)
                    ry = rng.randint(5, lmap.height - 5)
                    if lmap.is_passable(rx, ry):
                        break
                npc.local_x = rx
                npc.local_y = ry
                npc.local_z = lmap.ground_z(npc.local_x, npc.local_y)
                # Place NPCs at their building's door in settlements
                if loc and hasattr(lmap, 'town_layout') and lmap.town_layout:
                    for b in lmap.town_layout.buildings:
                        if b.occupation and b.occupation == npc.occupation:
                            dx, dy = b.door_x, b.door_y + 1
                            if lmap.in_bounds(dx, dy) and lmap.is_passable(dx, dy):
                                npc.local_x = dx
                                npc.local_y = dy
                                npc.local_z = lmap.ground_z(dx, dy)
                            break
                # Equip NPC with occupation-appropriate weapon
                if hasattr(npc, 'equip_occupation_weapon'):
                    npc.equip_occupation_weapon()
                self.npc_mgr.npcs[npc.npc_id] = npc
                # Register with town services
                if hasattr(self, 'town_services'):
                    self.town_services.register_npc(
                        wx, wy, npc.npc_id, npc.occupation)
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

    def _on_npc_death(self, npc):
        """Handle all side effects of an NPC dying."""
        # ── War-aware kill check ──────────────────────────────────────
        # Killing an enemy combatant during war is NOT a crime.
        # It earns positive faction rep instead.
        is_wartime_kill = False
        npc_faction = getattr(npc, 'faction', '')
        if hasattr(self, 'war_system') and npc_faction:
            if self.war_system.is_enemy_combatant(npc_faction):
                is_wartime_kill = True
                self.war_system.kills_in_war += 1
                # Track in active battle if one exists
                bs = getattr(self, '_active_battle', None)
                if bs and not bs.resolved:
                    bs.enemies_killed += 1
                    # Check if this was an officer
                    occ = getattr(npc, 'occupation', '')
                    if occ in ("Militia Captain", "Fort Commander",
                               "Officer", "Colonel", "General"):
                        bs.officers_killed += 1

        # Tribal standing impact — only if NOT a wartime kill
        tribe = getattr(npc, 'tribe', '')
        if tribe and hasattr(self, 'tribal') and not is_wartime_kill:
            day = self.time.total_minutes // 1440
            self.tribal.adjust_standing(
                tribe, -50, f"Killed {npc.name}", day)
            self.add_message(
                f"The {tribe} will not forget this.", "critical")
        elif tribe and is_wartime_kill:
            # Enemy tribe during war — smaller standing hit
            day = self.time.total_minutes // 1440
            self.tribal.adjust_standing(
                tribe, -15, f"Killed {npc.name} in battle", day)

        # Remove from town services registry
        if hasattr(self, 'town_services'):
            from src.town_services import on_npc_death
            msgs = on_npc_death(
                self.town_services,
                self.player.world_x, self.player.world_y,
                npc.npc_id, getattr(npc, 'occupation', ''),
                self.npc_mgr.npcs)
            for msg in msgs:
                self.add_message(msg, "advisory")

        # Record in newspaper — war kills reported differently
        if hasattr(self, 'newspaper'):
            if is_wartime_kill:
                self.newspaper.record_event(
                    "battle", f"{npc.name} killed in action.",
                    self.player.world_x, self.player.world_y,
                    self.time.total_minutes // 1440)
            else:
                self.newspaper.record_event(
                    "crime", f"{npc.name} ({npc.occupation}) was killed.",
                    self.player.world_x, self.player.world_y,
                    self.time.total_minutes // 1440)

    def _splatter_blood(self, lmap, x: int, y: int, intensity: int = 1):
        """Mark tiles with blood. intensity: 1=light (pink), 2=heavy (dark red)."""
        if lmap.in_bounds(x, y):
            tile = lmap.tiles[y][x]
            tile.blood = max(tile.blood, intensity)
            lmap.mark_dirty(x, y)

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

        # Clear previously visible ADJACENT patch tiles
        prev_adj = getattr(self, '_adj_visible_cache', None)
        if prev_adj:
            for (almap, atx, aty) in prev_adj:
                if almap.in_bounds(atx, aty):
                    almap.tiles[aty][atx].visible = False
        self._adj_visible_cache = []

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

        # Mark adjacent patch tiles as explored when viewport extends beyond edge,
        # but ONLY if within FOV radius (don't reveal entire viewport strip).
        from src.constants import AREAS_PER_WORLD, PATCH_SIZE
        half_w = 40  # VIEWPORT_W // 2
        half_h = 19  # VIEWPORT_H // 2
        cam_x = px - half_w
        cam_y = py - half_h
        wx, wy = self.player.world_x, self.player.world_y
        ax, ay = self.player.area_x, self.player.area_y
        r_sq = r * r  # FOV radius squared for distance check
        for vsy in range(half_h * 2):
            for vsx in range(half_w * 2):
                atx, aty = cam_x + vsx, cam_y + vsy
                if lmap.in_bounds(atx, aty):
                    continue  # on current patch
                # Only reveal if within FOV radius
                ddx, ddy = atx - px, aty - py
                if ddx * ddx + ddy * ddy > r_sq:
                    continue
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
                    adj_lmap.tiles[_ty][_tx].visible = True
                    self._adj_visible_cache.append((adj_lmap, _tx, _ty))

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
            base = 12   # ~60ft — moonlit/starlit visibility
        elif period in ("dawn", "dusk"):
            base = 35   # ~175ft — dim light
        else:
            base = 60   # ~300ft — clear daylight on open ground
        # Weather reduces visibility
        return max(4, int(base * self.time.weather_visibility_mult))

    # ── Time & survival tick ──────────────────────────────────────────────

    def advance_time(self, minutes: int):
        old_weather = self.time.weather
        self.time.advance(minutes)

        # Weather change notification
        new_weather = self.time.weather
        if new_weather != old_weather:
            _WEATHER_MSG = {
                "rain": "Rain begins to fall.",
                "snow": "Snow starts drifting down.",
                "blizzard": "A blizzard sets in. Visibility drops to nothing.",
                "fog": "Thick fog rolls in.",
                "thunderstorm": "Thunder rumbles. A storm is coming.",
                "hot": "The heat is oppressive.",
                "cold": "A bitter cold settles in.",
                "clear": "The sky clears.",
                "overcast": "Clouds move in overhead.",
            }
            msg = _WEATHER_MSG.get(new_weather)
            if msg:
                self.add_message(msg, "advisory")

        # Warmth from clothing + weather + altitude
        from src.clothing import warmth_modifier
        clothing_mod = warmth_modifier(self.player.worn) if self.player.worn else 0.0
        # Altitude cooling: -3°F per 1000 ft above 3000 ft (standard lapse rate)
        altitude_mod = 0.0
        lmap = self.current_local
        if lmap:
            elev = getattr(lmap, 'world_elevation_ft', 0)
            if elev > 3000:
                altitude_mod = -((elev - 3000) / 1000.0) * 1.5  # warmth penalty
        temp_mod = clothing_mod + self.time.weather_temp_mod + altitude_mod
        con = self.player.attributes.get("constitution", 10)
        # Shelter quality affects warmth retention
        shelter_struct = self._nearby_structure("shelter", radius=2)
        sheltered = shelter_struct is not None
        if shelter_struct and hasattr(shelter_struct, 'blueprint_key'):
            from src.construction import EQUIPMENT_BLUEPRINTS
            bp = EQUIPMENT_BLUEPRINTS.get(shelter_struct.blueprint_key)
            sq = bp.shelter_quality if bp else 0.3
            # Quality scales the warmth bonus from being sheltered
            temp_mod += sq * 5  # lean-to: +1.5, cabin: +4.0
        # Town buildings count as full shelter
        if not sheltered and self.current_local:
            tile = self.current_local.tile_at(
                self.player.local_x, self.player.local_y)
            if tile.terrain >= 100:  # town terrain IDs
                sheltered = True
                temp_mod += 4.5  # building = good shelter
        self.player.survival.tick(float(minutes), activity_mult=1.0,
                                   temp_mod=temp_mod, sheltered=sheltered,
                                   constitution=con)

        for stat, severity in self.player.survival.warnings():
            if " " in stat or "\u2014" in stat:
                # Raw descriptive warning (e.g. scurvy, mercury) — use as-is
                text = f"You are {stat}."
            elif severity == "critical":
                text = f"You are {severity}ly {stat}."
            else:
                text = f"You are getting {stat}y."
            if not self.messages or self.messages[-1][0] != text:
                self.add_message(text, severity)

        # Skill level-up announcements
        for lvl_msg in self.player.flush_levelups():
            self.add_message(lvl_msg, "advisory")

        # Exhaustion collapse — forced rest if fatigue hits 0
        if self.player.survival.fatigue <= 0:
            self.add_message(
                "You collapse from exhaustion. Your body refuses to go further.",
                "critical")
            self.player.survival.rest(120)  # forced 2-hour nap
            self.time.advance(120)
            self.add_message(
                "You wake up on the ground, groggy. You slept where you fell.",
                "advisory")

        # Wound bleeding tick
        for msg, sev in self.player.wounds.tick(float(minutes)):
            self.add_message(msg, sev)
        if not self.player.wounds.alive:
            self.player.survival.health = 0.0
            self._trigger_death("You have bled out.")
            return

        # Clothing wear
        if self.player.worn:
            for msg in self.player.worn.tick_wear(minutes,
                                                    weather=self.time.weather):
                self.add_message(msg, "advisory")

        # NPC-to-NPC overheard conversations
        if self.state == GameState.LOCAL_MAP:
            self._check_npc_conversations()

        # Companion task completions
        npc_lookup = {n.npc_id: n for n in self._tile_npcs()}
        gold_bias = self.current_local._gold_bias if self.current_local else 0.3
        for result in self.companion_mgr.check_completions(
                self.time.total_minutes, npc_lookup, gold_bias):
            self.add_message(result.message, "advisory")
            self.player.gold_oz += result.gold_found
            if result.for_business and self.business_mgr.businesses:
                # Route items to the first active business
                biz_list = list(self.business_mgr.businesses.values())
                biz = biz_list[0] if biz_list else None
                if not biz:
                    # No business — items go to player instead
                    for item_name in result.items_produced:
                        item = self.item_factory.create(item_name)
                        self.player.inventory.append(item)
                    continue
                for item_name in result.items_produced:
                    item = self.item_factory.create(item_name)
                    biz.inventory.append(item)
                if result.cost > 0:
                    biz.cash_reserve -= result.cost
                    self.add_message(
                        f"  Bought {len(result.items_produced)} items "
                        f"(${result.cost:.2f} from business cash).", "advisory")
            else:
                for item_name in result.items_produced:
                    item = self.item_factory.create(item_name)
                    self.player.inventory.append(item)

        # ── Daily ticks (once per game day) ───────────────────────────
        current_day = self.time.total_minutes // 1440
        if current_day > self._last_tick_day:
            self._last_tick_day = current_day
            # Keep LLM era context in sync with game year
            if self.llm and hasattr(self.llm, 'set_year'):
                self.llm.set_year(self.time.year)
            # Sync year to world map for fast travel frontier calculation
            self.world._game_year = self.time.year
            self._run_daily_ticks(current_day)

        if self.state == GameState.LOCAL_MAP:
            self._npc_wander_tick(minutes)
            lmap = self.current_local
            if lmap:
                self.wildlife_mgr._game_minutes = self.time.total_minutes
                for msg in self.wildlife_mgr.update_all(minutes, self.player, lmap):
                    severity = "critical" if "mauls" in msg or "claws" in msg or "charges" in msg else "advisory"
                    self.add_message(msg, severity)
                # Fluid simulation — run every 10+ minutes of game time
                if lmap.fluid_system and minutes >= 10:
                    lmap.fluid_system.simulate_step()
                # Trap check (every 4+ hours of game time)
                import random as _trap_rng
                region = lmap._region_name if lmap else ""
                trap_msgs = self.trap_mgr.tick(
                    self.time.total_seconds, region, self.time.season,
                    _trap_rng.Random())
                for tm in trap_msgs:
                    self.add_message(tm, "advisory")
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
                        # Fire destroys items in player inventory
                        import random as _frng
                        burnable = [i for i in self.player.inventory
                                    if i.category in ("food", "material", "misc")
                                    and i.weight < 5.0]
                        if burnable and _frng.random() < 0.3:
                            burned = _frng.choice(burnable)
                            self.player.inventory.remove(burned)
                            self.add_message(
                                f"Your {burned.name} catches fire and burns!",
                                "critical")
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
                    # Burn ground items in fire tiles
                    for (fx, fy) in lmap._fire.get_fire_tiles():
                        if not lmap.in_bounds(fx, fy):
                            continue
                        tile = lmap.tile_at(fx, fy)
                        if tile.ground_items:
                            import random as _grng
                            for gi in list(tile.ground_items):
                                if gi.category in ("food", "material", "misc") \
                                        and _grng.random() < 0.5:
                                    tile.ground_items.remove(gi)

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

                # Scavenger attraction — food/carcasses on ground draw predators
                self._scavenger_check(lmap, minutes)

    def _scavenger_check(self, lmap, minutes: int):
        """Food, carcasses, or fish guts on the ground attract scavengers.
        Bears for large food piles, coyotes/wolves for smaller ones.
        Higher chance at night. Fire nearby repels them."""
        import random as _scrng
        px, py = self.player.local_x, self.player.local_y

        # Only check once per ~30 min of game time (not every tick)
        if _scrng.random() > minutes / 30.0:
            return

        # Count food/meat items on ground within 20 tiles of player
        food_score = 0
        for dy in range(-20, 21, 4):  # sample, not every tile
            for dx in range(-20, 21, 4):
                tx, ty = px + dx, py + dy
                if not lmap.in_bounds(tx, ty):
                    continue
                tile = lmap.tile_at(tx, ty)
                for gi in tile.ground_items:
                    if gi.category == "food":
                        food_score += gi.weight
                    if gi.id in ("fish_guts", "fresh_fish", "fresh_venison"):
                        food_score += gi.weight * 3  # strong smell
                # Dead animals = massive attraction
                for a in self.wildlife_mgr.get_animals(
                        self.player.world_x, self.player.world_y,
                        self.player.area_x, self.player.area_y):
                    if a.state == "dead" and not a.recoverable:
                        continue
                    if a.state == "dead" and abs(a.local_x - tx) < 3 and abs(a.local_y - ty) < 3:
                        food_score += 10

        if food_score < 2:
            return  # not enough to attract anything

        # Fire repels scavengers
        has_fire = self._nearby_structure("cook", radius=10)
        if has_fire:
            food_score *= 0.3

        # Night = more scavengers
        if self.time.period == "night":
            food_score *= 2.0

        # Chance scales with food score
        chance = min(0.15, food_score * 0.01)
        if _scrng.random() > chance:
            return

        # Pick scavenger type based on food score
        from src.wildlife import WildlifeType, WILDLIFE_DB
        from src.wildlife_manager import WildlifeInstance
        if food_score >= 15:
            # Big attraction = bear
            scav_type = _scrng.choice([WildlifeType.GRIZZLY_BEAR, WildlifeType.BLACK_BEAR])
            msg = "smell of food"
        elif food_score >= 8:
            # Medium = wolf or coyote
            scav_type = _scrng.choice([WildlifeType.GRAY_WOLF, WildlifeType.COYOTE])
            msg = "scent of meat"
        else:
            # Small = coyote or fox
            scav_type = WildlifeType.COYOTE
            msg = "smell of food scraps"

        sp = WILDLIFE_DB.get(scav_type)
        if not sp:
            return

        # Spawn near the food source, approaching from edge
        edge_dir = _scrng.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
        sx = px + edge_dir[0] * _scrng.randint(15, 25)
        sy = py + edge_dir[1] * _scrng.randint(15, 25)
        sx = max(5, min(lmap.width - 5, sx))
        sy = max(5, min(lmap.height - 5, sy))

        key = (self.player.world_x, self.player.world_y,
               self.player.area_x, self.player.area_y)
        animal = WildlifeInstance(scav_type, sp, sx, sy)
        animal.local_z = lmap.ground_z(sx, sy)
        self.wildlife_mgr.active.setdefault(key, []).append(animal)

        if self.time.period == "night":
            self.add_message(
                f"Something is moving in the dark. The {msg} "
                f"has drawn a {sp.display_name}.",
                "warning")
        else:
            self.add_message(
                f"A {sp.display_name} approaches, drawn by the {msg}.",
                "advisory")

    def _run_daily_ticks(self, current_day: int):
        """Run all once-per-day system updates."""
        self._greeted_today = set()  # reset NPC greetings for new day
        p = self.player
        region = ""
        if self.current_local:
            region = self.current_local._region_name

        # Wound infection/healing (CON affects infection resistance + healing)
        con = p.attributes.get("constitution", 10)
        for msg, sev in p.wounds.tick_daily(constitution=con):
            self.add_message(msg, sev)

        # Disease exposure checks (daily)
        import random as _disease_rng
        _drng = _disease_rng.Random(current_day + self.player.world_x * 97)
        season = self.time.season
        elev = 0
        if self.current_local:
            elev = getattr(self.current_local, 'world_elevation_ft', 0)

        # Wound infection — open wounds can get infected
        if p.wounds.wounds:
            open_wounds = [w for w in p.wounds.wounds if w.is_bleeding]
            if open_wounds and _drng.random() < 0.08:
                msg = p.survival.contract_disease("wound_infection", con)
                if msg:
                    self.add_message(msg, "critical")

        # Cholera/dysentery — from drinking untreated water
        # PREVENTION: boiling water eliminates risk. Players who boil are safe.
        # Check if player has boiled water (campfire nearby + canteen)
        has_fire = self._nearby_structure("cook", radius=5) is not None
        has_tea = any(i.id in ("pine_needle_tea", "willow_tea", "mint_tea",
                               "rose_hip_tea")
                      for i in p.inventory)
        boils_water = has_fire or has_tea  # tea implies boiled water
        if not boils_water:
            near_town = self.current_local and hasattr(self.current_local, 'town_layout') \
                        and self.current_local.town_layout
            water_risk = 0.015 if near_town else 0.003
            if _drng.random() < water_risk:
                disease = "cholera" if _drng.random() < 0.3 else "dysentery"
                msg = p.survival.contract_disease(disease, con)
                if msg:
                    self.add_message(msg, "critical")

        # Malaria — mosquito-borne. Summer/fall, low elevation, near water
        # PREVENTION: sleeping near a campfire (smoke repels mosquitoes),
        # or being sheltered in a building
        if season in ("summer", "fall") and elev < 3000:
            sheltered = self._nearby_structure("shelter", radius=3) is not None
            smoky_fire = has_fire  # campfire smoke deters mosquitoes
            if not sheltered and not smoky_fire:
                malaria_risk = 0.008
                if region and ("gulf" in region.lower() or "swamp" in region.lower()):
                    malaria_risk = 0.02
                if _drng.random() < malaria_risk:
                    msg = p.survival.contract_disease("malaria", con)
                    if msg:
                        self.add_message(msg, "critical")

        # Mountain fever (tick-borne) — spring/summer in mountains
        # PREVENTION: checking clothes/body (the action "check for ticks")
        if season in ("spring", "summer") and elev > 3000:
            if _drng.random() < 0.003:
                msg = p.survival.contract_disease("mountain_fever", con)
                if msg:
                    self.add_message(msg, "advisory")

        # Companion daily morale/loyalty
        for msg in self.companion_mgr.tick_daily():
            self.add_message(msg, "advisory")

        # Business daily revenue
        rep = self.reputation.get(region)
        # Auto-pause/unpause businesses based on player presence + manager
        for biz in self.business_mgr.businesses.values():
            at_biz = (p.world_x == biz.world_x and p.world_y == biz.world_y)
            if at_biz:
                biz.paused = False
                biz.last_update_day = current_day
            elif biz.manager_npc_id:
                biz.paused = False
            else:
                biz.paused = True

        for biz_name, finance, event in self.business_mgr.tick_daily(current_day, rep):
            if event:
                self.add_message(f"[{biz_name}] {event.description}", "advisory")

        # Competition effects — NPC providers react to player businesses
        if hasattr(self, 'town_services'):
            for biz in self.business_mgr.businesses.values():
                if biz.active:
                    from src.town_services import on_business_event
                    try:
                        comp_mult = on_business_event(
                            self.town_services, biz.world_x, biz.world_y,
                            biz.blueprint_key, "player_opened")
                        # Store for revenue calc reference
                        biz._competition_mult = comp_mult
                    except Exception:
                        pass

        # Shipment arrivals
        for biz_name, msg in self.business_mgr.resolve_shipments(current_day, self.world):
            self.add_message(f"[{biz_name}] {msg}", "advisory")
            # Send as letter too
            self.writing.mail.send_letter(
                sender=f"Freight Agent, {biz_name}",
                recipient=p.name, body=msg)

        # Manager weekly reports → mail
        for biz_name, report in self.business_mgr.get_pending_reports(current_day):
            self.writing.mail.send_letter(
                sender=f"Manager, {biz_name}",
                recipient=p.name,
                body=report,
            )

        # Settlement events (interactive — NPCs with motives, player choices)
        if self.current_local and hasattr(self.current_local, 'town_layout') \
                and self.current_local.town_layout:
            from src.settlement_events import roll_settlement_event
            stype = self.current_local.town_layout.settlement_type
            season = self.time.season
            # Event handles its own UI, NPC selection, and outcome application
            roll_settlement_event(self, stype, season, self.time.year)

        # Expire old settlement price effects
        if hasattr(self, '_settlement_price_effects'):
            self._settlement_price_effects = [
                e for e in self._settlement_price_effects
                if e["expires"] > current_day
            ]

        # Mining claim maintenance
        for msg in self.claim_mgr.tick_daily(current_day):
            self.add_message(msg, "warning")

        # Pack animal daily care
        if self.animal_mgr.animals:
            from src.local_map import LocalTerrain
            on_grass = False
            if self.current_local:
                t = self.current_local.tile_at(
                    self.player.local_x, self.player.local_y).terrain
                on_grass = t in (LocalTerrain.GRASS, LocalTerrain.GROUND)
            for msg in self.animal_mgr.tick_daily(
                    on_grass, self.player.inventory, random.Random(),
                    season=season):
                self.add_message(msg, "advisory")

        # Legal sentence serving
        msg = self.legal.tick_sentence(current_day)
        if msg:
            self.add_message(msg, "normal")

        # Dynamic location aging (every 90 days = 1 season)
        if current_day % 90 == 0:
            for loc in self.dynamic_locs.age_one_season(self.time.year):
                self.add_message(f"{loc.name} is {loc.stage}.", "advisory")

        # Town growth from player gold finds
        # Track daily gold delta and boost nearby settlements
        gold_today = p.gold_oz - getattr(self, '_gold_yesterday', p.gold_oz)
        self._gold_yesterday = p.gold_oz
        if gold_today > 0.01:
            self.dynamic_locs.record_activity(p.world_x, p.world_y)
            growth_msg = self.dynamic_locs.boost_growth(
                p.world_x, p.world_y, gold_today, self.time.year)
            if growth_msg:
                self.add_message(growth_msg, "normal")

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

        # Personal letter replies from known NPCs
        self.writing.check_letter_replies(
            current_day, p.name, nearest_town,
            self._find_npc_by_name, self.llm, p)

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

        # Bounty board — decay trails, generate new bounties
        import random as _daily_rng
        self.bounty_board.tick_daily(current_day)
        if current_day % 7 == 0 and nearest_town:
            self.bounty_board.generate_bounty(
                current_day, nearest_town, _daily_rng.Random(current_day))

        # Rival prospectors — daily mining, events
        rival_events = self.rival_system.tick_daily(current_day, _daily_rng.Random(current_day))
        if rival_events:
            for evt in rival_events[:2]:  # max 2 messages per day
                self.add_message(evt, "normal")

        # Claim jump check
        jump = self.rival_system.check_claim_jump(
            p.world_x, p.world_y, p.area_x, p.area_y,
            current_day, _daily_rng.Random(current_day + 999))
        if jump:
            self.add_message(jump.get("message", "Someone is eyeing your claim."), "critical")

        # Newspaper — weekly issue generation
        if current_day % 7 == 0 and nearest_town:
            self.newspaper.generate_issue(
                nearest_town, current_day, _daily_rng.Random(current_day))

        # Annual Rendezvous (Mountain Men era, July, 1825-1840)
        if (self.time.year >= 1825 and self.time.year <= 1840 and
                self.time.month == 7 and self.time.day == 1):
            self._trigger_rendezvous(current_day)

        # Vehicle condition degradation
        _cl = self.current_local
        terrain = "road" if _cl and hasattr(_cl, 'town_layout') and _cl.town_layout else "off_road"
        self.vehicle_mgr.tick_daily(terrain)

        # Marriage daily tick
        if self.marriage_state:
            from src.marriage import tick_marriage
            spouse = self._find_npc_by_name(self.marriage_state.spouse_name)
            s_wx = getattr(spouse, 'world_x', p.world_x) if spouse else p.world_x
            s_wy = getattr(spouse, 'world_y', p.world_y) if spouse else p.world_y
            msgs = tick_marriage(self.marriage_state, p.world_x, p.world_y,
                                s_wx, s_wy, current_day)
            for msg in msgs:
                self.add_message(msg, "advisory")

        # Hide/pelt drying on stretching frames
        lmap_daily = self.current_local
        if lmap_daily and lmap_daily.structures:
            from src.items import make_item as _dm_item
            for _sid, struct in lmap_daily.structures.items():
                drying = getattr(struct, '_drying', [])
                finished = []
                for d in drying:
                    if current_day - d["day_placed"] >= 1:  # 24 hours
                        finished.append(d)
                for d in finished:
                    drying.remove(d)
                    if d["type"] == "fur":
                        # Fur path: output keeps original pelt ID but non-perishable
                        orig_id = d.get("original_id", "beaver_pelt")
                        product = _dm_item(orig_id)
                        product.name = f"Stretched {d.get('original_name', 'Pelt')}"
                        product.base_value = d.get("base_value", 3.0) * 1.5
                        product.perishable = False
                        product.extra = {**getattr(product, 'extra', {}),
                                         "processed": True}
                        product.description = "Dried and preserved pelt. Ready for trade or crafting."
                    else:
                        # Leather path: output is "leather" so it matches all leather recipes
                        product = _dm_item("leather")
                        product.perishable = False
                        product.description = "Soft brain-tanned leather. Ready for crafting."
                    # Place on ground next to frame
                    fx, fy = struct.x, struct.y
                    if lmap_daily.in_bounds(fx, fy):
                        lmap_daily.tile_at(fx, fy).ground_items.append(product)
                        lmap_daily.mark_dirty(fx, fy)
                    self.add_message(
                        f"The {product.name} on the frame has dried. Pick it up.",
                        "advisory")

        # Tribal system daily tick
        if hasattr(self, 'tribal'):
            tribal_msgs = self.tribal.tick_daily(
                p.world_x, p.world_y, current_day, _daily_rng.Random(current_day + 777))
            for cat, msg in tribal_msgs:
                sev = "critical" if cat in ("raid", "warning") else "advisory"
                self.add_message(msg, sev)
            # Check for raids
            n_horses = len(self.animal_mgr.animals)
            n_pelts = sum(1 for i in p.inventory
                          if "pelt" in i.id or "fur" in i.id or "robe" in i.id)
            raid = self.tribal.check_raids(
                p.world_x, p.world_y, n_horses, n_pelts,
                current_day, _daily_rng.Random(current_day + 888))
            if raid:
                raid_tribe = raid["tribe"]
                raid_type = raid["raid_type"]
                if raid_type == "horse_raid" and self.animal_mgr.animals:
                    stolen = self.animal_mgr.animals.pop()
                    self.add_message(
                        f"In the night, {raid_tribe} raiders stole {stolen.name}!",
                        "critical")
                elif raid_type == "supply_raid":
                    if p.inventory:
                        import random as _raid_rng
                        lost = _raid_rng.choice(p.inventory)
                        p.inventory.remove(lost)
                        self.add_message(
                            f"{raid_tribe} raiders took your {lost.name} in the night!",
                            "critical")
                elif raid_type == "ambush":
                    self.add_message(
                        f"A {raid_tribe} war party of {raid['warriors']} warriors "
                        f"attacks!", "critical")

        # Non-tribal language exposure (Chinese, Spanish, French)
        # Track days near speakers for language learning
        _exposure_changed = False
        for npc in self._tile_npcs():
            if not npc.alive or not npc.present:
                continue
            eth = getattr(npc, 'ethnicity', '')
            lang_key = None
            if eth == "chinese":
                lang_key = "chinese"
            elif eth == "mexican":
                lang_key = "spanish"
            elif eth == "french_canadian":
                lang_key = "french"
            if lang_key and p.languages.get(lang_key, "none") != "fluent":
                # Spouse/companion doubles exposure rate
                mult = 1
                if hasattr(self, 'marriage_state') and self.marriage_state:
                    spouse = self.marriage_state.spouse_name or ""
                    if spouse and spouse == npc.name:
                        mult = 2
                p._lang_exposure[lang_key] = p._lang_exposure.get(lang_key, 0) + mult
                days = p._lang_exposure[lang_key]
                cur_lvl = p.languages.get(lang_key, "none")
                if cur_lvl == "none" and days >= 7:
                    p.languages[lang_key] = "sign"
                    self.add_message(
                        f"You've picked up basic gestures in {lang_key.title()}.",
                        "advisory")
                    _exposure_changed = True
                elif cur_lvl == "sign" and days >= 21:
                    p.languages[lang_key] = "pidgin"
                    self.add_message(
                        f"You can now speak pidgin {lang_key.title()} — basic conversation.",
                        "advisory")
                    _exposure_changed = True
                elif cur_lvl == "pidgin" and days >= 90:
                    p.languages[lang_key] = "fluent"
                    self.add_message(
                        f"You are now fluent in {lang_key.title()}!",
                        "advisory")
                    _exposure_changed = True
                if _exposure_changed:
                    break  # one level-up per day max

        # ── War system daily tick ─────────────────────────────────────
        if hasattr(self, 'war_system'):
            war_msgs = self.war_system.tick_daily(
                self.time.year, region,
                _daily_rng.Random(current_day + 5555))
            for msg, sev in war_msgs:
                self.add_message(msg, sev)

            # Check for historical battles happening today
            yr, mo, dy = self.time.calendar
            battle = self.war_system.get_todays_battle(
                yr, mo, dy, p.world_x, p.world_y, detection_range=25)
            if battle and not getattr(self, '_battle_notified', None) == battle.battle_id:
                self._battle_notified = battle.battle_id
                direction = ""
                dx = battle.world_x - p.world_x
                dya = battle.world_y - p.world_y
                if abs(dx) > abs(dya):
                    direction = "east" if dx > 0 else "west"
                else:
                    direction = "south" if dya > 0 else "north"
                dist_miles = (abs(dx) + abs(dya)) * 5
                self.add_message(
                    f"Gunfire to the {direction}. Heavy. "
                    f"The Battle of {battle.name} is underway — "
                    f"{dist_miles} miles from here.", "critical")
                self.add_message(
                    f"{battle.factions[0]} ({battle.strength[0]} men) vs "
                    f"{battle.factions[1]} ({battle.strength[1]} men).",
                    "advisory")
                # Store battle state for player to join
                from src.war_system import BattleState
                self._active_battle = BattleState(battle=battle)

                # Spawn a military camp dynamic location
                camp_name = f"{battle.factions[0]} Camp"
                self.dynamic_locs.add(
                    __import__('src.dynamic_locations', fromlist=['DynamicLocation'])
                    .DynamicLocation(
                        id=f"camp_{battle.battle_id}",
                        name=camp_name,
                        loc_type="military_camp",
                        world_x=battle.world_x - 2,
                        world_y=battle.world_y - 2,
                        population=50,
                        era_founded=self.time.year,
                        notes=f"Military camp for the Battle of {battle.name}.",
                        discovered=True,
                    ))

            # Wartime walking event — military patrols
            active_wars = self.war_system.get_active_wars(self.time.year, region)
            if active_wars and _daily_rng.Random(current_day + 777).random() < 0.15:
                war = active_wars[0]
                faction = _daily_rng.Random(current_day).choice(war.factions)
                patrol_msgs = [
                    f"A column of {faction} soldiers marches past heading west.",
                    f"A {faction} patrol rides through. They eye you but move on.",
                    f"Campfires on the ridge — {faction} troops bivouacked for the night.",
                    f"A {faction} supply wagon rattles past escorted by armed riders.",
                    f"You hear drums. A {faction} regiment is on the move nearby.",
                ]
                self.add_message(
                    _daily_rng.Random(current_day + 888).choice(patrol_msgs),
                    "normal")

        # ── Captivity tick ─────────────────────────────────────────────
        if hasattr(self, 'tribal'):
            for tribe_name in list(self.tribal.standings.keys()):
                ts = self.tribal.get_standing(tribe_name)
                if ts.captive:
                    captive_msgs = self.tribal.tick_captivity(
                        tribe_name, current_day,
                        _daily_rng.Random(current_day + hash(tribe_name)))
                    for msg, sev in captive_msgs:
                        self.add_message(msg, sev)

        # ── Seasonal terrain transitions ──────────────────────────────
        lmap = self.current_local
        if lmap:
            from src.local_map import LocalTerrain as _ST
            prev_season = getattr(self, '_last_season', season)
            elev = getattr(lmap, 'world_elevation_ft', 0)

            # Winter freeze — rivers freeze when cold enough
            if season == "winter" and self.time.weather in (
                    "snow", "blizzard", "cold"):
                # Higher elevation = freezes earlier and harder
                freeze_chance = 0.15 if elev > 4000 else 0.05
                if _daily_rng.Random(current_day + 333).random() < freeze_chance:
                    frozen = 0
                    for y in range(lmap.height):
                        for x in range(lmap.width):
                            if lmap.tiles[y][x].terrain == _ST.WATER:
                                lmap.tiles[y][x].terrain = _ST.FROZEN_WATER
                                frozen += 1
                    if frozen > 0:
                        self.add_message(
                            "The creek has frozen over. You can walk across.",
                            "advisory")
                        lmap.invalidate_terrain_cache()

            # Spring thaw — frozen water melts, floods deposit gold
            if season == "spring" and prev_season == "winter":
                thawed = 0
                for y in range(lmap.height):
                    for x in range(lmap.width):
                        t = lmap.tiles[y][x].terrain
                        if t == _ST.FROZEN_WATER:
                            lmap.tiles[y][x].terrain = _ST.WATER
                            thawed += 1
                        # Spring flood — water expands into adjacent low ground
                        if t == _ST.WATER:
                            for dy in (-1, 0, 1):
                                for dx in (-1, 0, 1):
                                    nx, ny = x + dx, y + dy
                                    if lmap.in_bounds(nx, ny):
                                        adj = lmap.tiles[ny][nx]
                                        if adj.terrain in (_ST.GRAVEL_BAR,
                                                           _ST.MUD, _ST.SAND):
                                            if _daily_rng.Random(
                                                    x * 97 + y + current_day
                                                    ).random() < 0.08:
                                                adj.terrain = _ST.FLOOD_WATER
                                                # Fresh gold deposited by flood
                                                adj.gold_grade = min(1.0,
                                                    adj.gold_grade + 0.05 +
                                                    _daily_rng.Random(
                                                        x + y * 13).random() * 0.10)
                if thawed > 0:
                    self.add_message(
                        "The ice breaks up. Spring meltwater swells the creek. "
                        "Fresh gravel on the bars — could be new gold.", "normal")
                    lmap.invalidate_terrain_cache()

            # Flood water recedes after a few days in spring
            if season == "spring":
                for y in range(lmap.height):
                    for x in range(lmap.width):
                        if lmap.tiles[y][x].terrain == _ST.FLOOD_WATER:
                            if _daily_rng.Random(
                                    x + y * 7 + current_day).random() < 0.3:
                                lmap.tiles[y][x].terrain = _ST.GRAVEL_BAR
                                lmap.tiles[y][x].panned = False  # fresh ground

            # Summer drought — small streams can dry up
            hot_days = getattr(self, '_consecutive_hot_days', 0)
            if self.time.weather in ("hot", "clear") and season == "summer":
                self._consecutive_hot_days = hot_days + 1
            else:
                self._consecutive_hot_days = 0
            if self._consecutive_hot_days >= 10 and season == "summer":
                # Dry up isolated water tiles (not main streams)
                dried = 0
                for y in range(lmap.height):
                    for x in range(lmap.width):
                        if lmap.tiles[y][x].terrain != _ST.WATER:
                            continue
                        # Count adjacent water — isolated pools dry first
                        adj_water = 0
                        for dy in (-1, 0, 1):
                            for dx in (-1, 0, 1):
                                nx, ny = x + dx, y + dy
                                if lmap.in_bounds(nx, ny) and \
                                        lmap.tiles[ny][nx].terrain in (
                                            _ST.WATER, _ST.DEEP_WATER,
                                            _ST.BEAVER_POND):
                                    adj_water += 1
                        if adj_water <= 2 and \
                                _daily_rng.Random(x * 31 + y + current_day
                                                  ).random() < 0.1:
                            lmap.tiles[y][x].terrain = _ST.MUD
                            dried += 1
                if dried > 0:
                    self.add_message(
                        "The drought is drying up the smaller streams.", "advisory")
                    lmap.invalidate_terrain_cache()

            self._last_season = season

    def _tile_npcs(self):
        """NPCs whose ID belongs to the current area patch or active battle."""
        wx, wy = self.player.world_x, self.player.world_y
        ax, ay = self.player.area_x, self.player.area_y
        prefixes = (f"sett_{wx}_{wy}_{ax}_{ay}_", f"wild_{wx}_{wy}_{ax}_{ay}_",
                    "battle_")  # battle NPCs are visible everywhere during combat
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
        """Goal-driven NPC movement. NPCs walk toward activity targets."""
        import random as _r
        lmap = self.current_local
        period = self.time.period
        px, py = self.player.local_x, self.player.local_y

        for npc in self._tile_npcs():
            if not npc.alive or not npc.present:
                continue
            if npc.combat_state == "hostile":
                continue
            if _r.random() > min(0.8, minutes / 10.0):
                continue

            # Try goal-driven activity movement first
            dx, dy = 0, 0
            try:
                from src.npc_activities import pick_activity, find_activity_target, step_toward
                act = pick_activity(npc, period, _r.Random())
                if act:
                    # Cache or find target
                    tx = getattr(npc, '_act_target_x', -1)
                    ty = getattr(npc, '_act_target_y', -1)
                    cur_act = getattr(npc, '_current_act', "")
                    if cur_act != act.activity_id or tx < 0:
                        # Pick new target
                        if act.target_terrain >= 0:
                            target = find_activity_target(
                                lmap, npc.local_x, npc.local_y,
                                act.target_terrain, _r.Random())
                            if target:
                                tx, ty = target
                        else:
                            tx, ty = -1, -1  # patrol / random
                        npc._act_target_x = tx
                        npc._act_target_y = ty
                        npc._current_act = act.activity_id

                    if tx >= 0 and ty >= 0:
                        dist = max(abs(npc.local_x - tx), abs(npc.local_y - ty))
                        if dist <= 1:
                            # At target — show activity message if player nearby
                            pdist = max(abs(npc.local_x - px), abs(npc.local_y - py))
                            if pdist <= 15 and act.messages and _r.random() < 0.1:
                                self.add_message(
                                    f"{npc.name} {_r.choice(act.messages)}", "normal")
                            continue  # stay at target
                        dx, dy = step_toward(npc.local_x, npc.local_y, tx, ty)
                    else:
                        dx = _r.choice([-1, 0, 0, 1])
                        dy = _r.choice([-1, 0, 0, 1])
                else:
                    dx = _r.choice([-1, 0, 0, 1])
                    dy = _r.choice([-1, 0, 0, 1])
            except (ImportError, AttributeError):
                dx = _r.choice([-1, 0, 0, 1])
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

    def _investigate_nearby(self):
        """Investigate recent event hints — find what caused tracks, smoke, etc."""
        import re
        lmap = self.current_local
        if not lmap:
            return
        px, py = self.player.local_x, self.player.local_y
        tracking = self.player.skills.get("tracking", 0)
        found_something = False

        # Parse recent messages for directional hints
        _DIR_MAP = {
            "north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0),
            "northwest": (-1, -1), "northeast": (1, -1),
            "southwest": (-1, 1), "southeast": (1, 1),
        }
        recent = [m[0].lower() for m in self.messages[-8:]]
        hint_dir = None
        hint_type = None
        for msg in recent:
            for dname, dvec in _DIR_MAP.items():
                if dname in msg:
                    hint_dir = dvec
                    break
            # Classify what we're investigating
            if "track" in msg or "boot print" in msg or "moccasin" in msg:
                hint_type = "tracks"
            elif "smoke" in msg or "campfire" in msg or "fire" in msg or "coffee" in msg or "cooking" in msg:
                hint_type = "smoke"
            elif "vulture" in msg or "circling" in msg or "dead" in msg:
                hint_type = "carrion"
            elif "figure" in msg or "movement" in msg or "someone" in msg:
                hint_type = "person"
            elif "wagon" in msg or "drag mark" in msg:
                hint_type = "wagon"

        # Search in the hinted direction (or all around if no direction)
        search_range = 8 + tracking * 2
        findings = []

        # Find NPCs in search area
        for npc in self._tile_npcs():
            if not npc.alive or not npc.present:
                continue
            dist = abs(npc.local_x - px) + abs(npc.local_y - py)
            if dist <= search_range:
                dx = npc.local_x - px
                dy = npc.local_y - py
                # If we have a directional hint, prioritize that direction
                if hint_dir and (dx * hint_dir[0] < 0 or dy * hint_dir[1] < 0):
                    continue  # wrong direction
                dir_str = self._compass_dir(dx, dy)
                findings.append((dist, f"{npc.display_name()} ({npc.occupation}), {dist * 5}ft {dir_str}"))

        # Find animals
        animals = self.wildlife_mgr.get_animals(
            self.player.world_x, self.player.world_y,
            self.player.area_x, self.player.area_y)
        for animal in animals:
            dist = abs(animal.local_x - px) + abs(animal.local_y - py)
            if dist <= search_range:
                dx = animal.local_x - px
                dy = animal.local_y - py
                if hint_dir and (dx * hint_dir[0] < 0 or dy * hint_dir[1] < 0):
                    continue
                dir_str = self._compass_dir(dx, dy)
                findings.append((dist, f"{animal.species.display_name} ({animal.state}), {dist * 5}ft {dir_str}"))

        # Find ground items in search direction
        items_found = []
        if hint_dir:
            for step in range(1, search_range):
                cx = px + hint_dir[0] * step
                cy = py + hint_dir[1] * step
                if lmap.in_bounds(cx, cy):
                    t = lmap.tile_at(cx, cy)
                    if t.ground_items:
                        for gi in t.ground_items:
                            items_found.append((step, gi.name, cx, cy))

        # Report findings
        self.advance_time(10)
        self.player.gain_skill_xp("tracking", 1.5)

        if not findings and not items_found and not hint_type:
            self.add_message("You search the area carefully but find nothing unusual.", "normal")
            return

        if hint_type == "tracks":
            self.add_message("You study the tracks carefully...", "normal")
        elif hint_type == "smoke":
            self.add_message("You scan for the source of the smoke...", "normal")
        elif hint_type == "carrion":
            self.add_message("You look for what the vultures are circling...", "normal")
        elif hint_type == "person":
            self.add_message("You try to spot the figure...", "normal")
        else:
            self.add_message("You search the surrounding area...", "normal")

        findings.sort(key=lambda x: x[0])
        for _, desc in findings[:5]:
            self.add_message(f"  Found: {desc}", "advisory")
            found_something = True

        for dist, iname, ix, iy in items_found[:3]:
            self.add_message(f"  Found: {iname} on the ground, {dist * 5}ft away", "advisory")
            found_something = True

        if not found_something:
            if tracking < 3:
                self.add_message("The signs are hard to read. A better tracker might find more.", "normal")
            else:
                self.add_message("Whatever it was, it's moved on.", "normal")

    @staticmethod
    def _compass_dir(dx: int, dy: int) -> str:
        if abs(dx) > abs(dy) * 2:
            return "east" if dx > 0 else "west"
        if abs(dy) > abs(dx) * 2:
            return "south" if dy > 0 else "north"
        if dx > 0:
            return "southeast" if dy > 0 else "northeast"
        return "southwest" if dy > 0 else "northwest"

    def _examine_cursor_mode(self):
        """Cursor-based examine mode. Move cursor to inspect tiles."""
        lmap = self.current_local
        if not lmap:
            return
        cur_x = self.player.local_x
        cur_y = self.player.local_y
        K = tcod.event.KeySym
        MOVES = {
            K.UP: (0, -1), K.DOWN: (0, 1), K.LEFT: (-1, 0), K.RIGHT: (1, 0),
            K.KP_8: (0, -1), K.KP_2: (0, 1), K.KP_4: (-1, 0), K.KP_6: (1, 0),
            K.KP_7: (-1, -1), K.KP_9: (1, -1), K.KP_1: (-1, 1), K.KP_3: (1, 1),
        }
        from src.local_map import LocalTerrain
        from src.constants import VIEWPORT_W, VIEWPORT_H

        while True:
            # Render map centered on player
            self.renderer._season = self.time.season
            self.renderer.render_all(
                lmap, self.world, self.player, self.messages,
                state="local_map", locals_dict=self.locals)

            # Camera coords
            half_w = VIEWPORT_W // 2
            half_h = VIEWPORT_H // 2
            cam_x = self.player.local_x - half_w
            cam_y = self.player.local_y - half_h

            # Draw cursor
            sx = cur_x - cam_x
            sy = cur_y - cam_y
            if 0 <= sx < VIEWPORT_W and 0 <= sy < VIEWPORT_H:
                self._console.print(sx, sy + 1, "X",
                                    fg=(255, 255, 0), bg=(40, 40, 80))

            # Examine what's at cursor position
            info_lines = []
            dist = max(abs(cur_x - self.player.local_x),
                       abs(cur_y - self.player.local_y))
            info_lines.append(f"Examining ({cur_x},{cur_y}) — {dist * 5}ft away")

            if lmap.in_bounds(cur_x, cur_y):
                tile = lmap.tile_at(cur_x, cur_y)
                # Terrain name lookup
                _T = LocalTerrain
                _TNAMES = {
                    _T.GROUND: "Bare Ground", _T.GRASS: "Grass",
                    _T.FOREST: "Forest", _T.ROCK: "Rock", _T.WATER: "Water",
                    _T.GRAVEL_BAR: "Gravel Bar", _T.BEDROCK: "Bedrock",
                    _T.MUD: "Mud", _T.SAND: "Sand", _T.BRUSH: "Brush",
                    _T.PIT: "Pit", _T.SPOIL_PILE: "Spoil Pile",
                    _T.PINE: "Pine", _T.OAK: "Oak", _T.ASPEN: "Aspen",
                    _T.CEDAR: "Cedar", _T.MAPLE: "Maple",
                    _T.WORKED_GRAVEL: "Worked Gravel",
                    _T.WORKED_DIRT: "Worked Dirt",
                    _T.SHALLOW_PIT: "Shallow Pit", _T.DEEP_PIT: "Deep Pit",
                    _T.TAILINGS: "Tailings",
                }
                t_name = _TNAMES.get(tile.terrain, "terrain")
                info_lines.append(f"Terrain: {t_name}")

                # Gold sign
                if tile.gold_grade > 0.1:
                    info_lines.append(f"Gold sign: {'strong' if tile.gold_grade > 0.5 else 'moderate' if tile.gold_grade > 0.2 else 'faint'}")

                # Ground items
                if tile.ground_items:
                    for gi in tile.ground_items[:4]:
                        info_lines.append(f"  Item: {gi.name}")
                    if len(tile.ground_items) > 4:
                        info_lines.append(f"  +{len(tile.ground_items) - 4} more")

                # NPCs at cursor
                for n in self._tile_npcs():
                    if n.alive and n.present and n.local_x == cur_x and n.local_y == cur_y:
                        info_lines.append(f"Person: {n.display_name()} ({n.occupation})")
                        if hasattr(n, 'rel'):
                            info_lines.append(f"  {n.rel_label()}")

                # Animals at cursor
                for animal in self.wildlife_mgr.get_animals(
                        self.player.world_x, self.player.world_y,
                        self.player.area_x, self.player.area_y):
                    if animal.local_x == cur_x and animal.local_y == cur_y:
                        state_str = animal.state
                        info_lines.append(
                            f"Animal: {animal.species.display_name} ({state_str})")

                # Structures
                if lmap.structures:
                    for _, s in lmap.structures.items():
                        if s.x == cur_x and s.y == cur_y:
                            info_lines.append(f"Structure: {s.name}")

            # Draw info panel
            panel_x = VIEWPORT_W + 2
            panel_y = 2
            self._console.print(panel_x, panel_y,
                                "── Examine ──────────", fg=(80, 200, 200))
            for i, line in enumerate(info_lines[:12]):
                self._console.print(panel_x, panel_y + 1 + i,
                                    line[:34], fg=(200, 200, 200))

            # Controls hint
            self._console.print(panel_x, panel_y + 14,
                                "Arrows: move cursor", fg=(80, 80, 80))
            self._console.print(panel_x, panel_y + 15,
                                "ESC: exit examine", fg=(80, 80, 80))

            self._ctx.present(self._console)

            # Input
            for event in tcod.event.wait():
                if isinstance(event, tcod.event.Quit):
                    raise SystemExit()
                if not isinstance(event, tcod.event.KeyDown):
                    continue
                sym = event.sym
                if sym == K.ESCAPE:
                    self.player.gain_skill_xp("tracking", 0.5)
                    self.advance_time(5)
                    return
                if sym in MOVES:
                    dx, dy = MOVES[sym]
                    nx, ny = cur_x + dx, cur_y + dy
                    if lmap.in_bounds(nx, ny):
                        cur_x, cur_y = nx, ny
                break

    def _check_npc_greetings(self):
        """NPCs who know the player may call out when nearby."""
        px, py = self.player.local_x, self.player.local_y
        current_day = self.time.total_minutes // 1440
        greeted = getattr(self, '_greeted_today', set())
        for npc in self._tile_npcs():
            if not npc.alive or not npc.present:
                continue
            if npc.combat_state != "neutral":
                continue
            if npc.npc_id in greeted:
                continue
            dist = max(abs(npc.local_x - px), abs(npc.local_y - py))
            if dist > 8 or dist < 2:
                continue  # only greet at medium range
            if not hasattr(npc, 'generate_greeting'):
                continue
            days_since = current_day - npc.rel.last_interaction_day
            greeting = npc.generate_greeting(self.player.name, days_since)
            if greeting:
                self.add_message(greeting, "normal")
                greeted.add(npc.npc_id)
                npc.rel.record_meeting(current_day)
        self._greeted_today = greeted

    def _check_npc_conversations(self):
        """NPCs near each other occasionally have overheard conversations.
        Player must be within earshot to see them."""
        import random as _conv_rng
        px, py = self.player.local_x, self.player.local_y
        current_minute = self.time.total_minutes
        earshot = 15  # tiles — player must be this close to overhear

        # Only check every ~30 game minutes to avoid spam
        if current_minute % 30 != 0:
            return
        # Don't fire if we already had one this hour
        last_overheard = getattr(self, '_last_overheard_minute', 0)
        if current_minute - last_overheard < 60:
            return

        rng = _conv_rng.Random(current_minute)

        # 20% chance per check (roughly 1 overheard conversation per 2-3 game hours)
        if rng.random() > 0.20:
            return

        npcs = [n for n in self._tile_npcs()
                if n.alive and n.present and n.combat_state == "neutral"]

        # Find NPC pairs near each other
        pairs = []
        for i, a in enumerate(npcs):
            for b in npcs[i + 1:]:
                dist_ab = max(abs(a.local_x - b.local_x),
                              abs(a.local_y - b.local_y))
                if dist_ab <= 4:  # NPCs must be within 4 tiles of each other
                    # Player must be within earshot of both
                    dist_pa = max(abs(a.local_x - px), abs(a.local_y - py))
                    dist_pb = max(abs(b.local_x - px), abs(b.local_y - py))
                    if dist_pa <= earshot and dist_pb <= earshot:
                        pairs.append((a, b, max(dist_pa, dist_pb)))

        if not pairs:
            return

        # Pick closest pair
        pairs.sort(key=lambda t: t[2])
        npc_a, npc_b, dist = pairs[0]

        try:
            from src.npc_speech import generate_overheard
            player_langs = getattr(self.player, 'languages', {"english": "fluent"})
            tribal = getattr(self, 'tribal', None)
            lines = generate_overheard(npc_a, npc_b, player_langs,
                                       tribal=tribal, rng=rng)
            if lines:
                # Prefix with distance flavor
                if dist > 10:
                    self.add_message("You overhear a distant conversation...", "normal")
                else:
                    self.add_message("You overhear nearby...", "normal")
                for line in lines:
                    self.add_message(f"  {line}", "normal")
                self._last_overheard_minute = current_minute
        except (ImportError, Exception):
            pass

    # ── Messages ──────────────────────────────────────────────────────────

    def add_message(self, text: str, severity: str = "normal"):
        self.messages.append((text, severity))
        if len(self.messages) > 200:
            self.messages = self.messages[-200:]

    # ── Input handling ────────────────────────────────────────────────────

    _last_keydown_char = ""  # character from last KeyDown (for dedup)

    def handle_event(self, event: tcod.event.Event) -> bool:
        """Returns False to quit."""
        if isinstance(event, tcod.event.Quit):
            return False

        if isinstance(event, tcod.event.KeyDown):
            # Track which character this KeyDown corresponds to
            # so we can skip the matching TextInput (prevents double-fire)
            sym = event.sym
            if 97 <= sym <= 122:  # a-z
                self._last_keydown_char = chr(sym)
            else:
                self._last_keydown_char = ""
            try:
                return self._handle_key(event)
            except Exception as _exc:
                import traceback as _tb
                with open("error.log", "a") as _f:
                    _f.write(f"\n--- key handler crash ---\n")
                    _tb.print_exc(file=_f)
                self.add_message(f"Error: {_exc}", "critical")
                return True

        # Handle TextInput as key presses — for RDP, iPad, and SDL3
        # where letter keys arrive as TextInput not KeyDown.
        # Only skip if this EXACT character was already handled by KeyDown.
        if isinstance(event, tcod.event.TextInput):
            text = event.text.lower()
            if len(text) == 1 and text == self._last_keydown_char:
                # Same key already handled by KeyDown — skip duplicate
                self._last_keydown_char = ""
                return True
            self._last_keydown_char = ""
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
        # Trapping mode  Y
        if sym == K.y:
            if self.state == GameState.LOCAL_MAP:
                from src.trapping_mode import enter_trapping_mode
                enter_trapping_mode(self, self._console, self._ctx)
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
        open_inventory(self._console, self._ctx, self.player,
                       animal_mgr=self.animal_mgr)

    def _open_character(self):
        from src.ui_character import open_character
        open_character(self._console, self._ctx, self.player,
                        reputation=self.reputation,
                        writing=self.writing)

    def _open_build_menu(self):
        if self.state != GameState.LOCAL_MAP:
            self.add_message("Building only on the local map.", "normal")
            return
        # Check if player needs a land deed to build here
        key = (self.player.world_x, self.player.world_y, self.player.area_x, self.player.area_y)
        lmap = self.locals.get(key)
        if lmap and hasattr(lmap, 'town_layout') and lmap.town_layout:
            stype = lmap.town_layout.settlement_type
            if stype in ("small_town", "city"):
                has_deed = any(
                    i.id == "land_deed"
                    and getattr(i, "extra", {}).get("lot_wx") == self.player.world_x
                    and getattr(i, "extra", {}).get("lot_wy") == self.player.world_y
                    for i in self.player.inventory
                )
                if not has_deed:
                    self.add_message(
                        "You need a land deed to build in this town. "
                        "Visit the Land Office.", "warning")
                    return
        from src.ui_build import open_build
        result = open_build(self._console, self._ctx, self.player,
                             local_map=self.current_local,
                             construction=self.construction,
                             year=self.time.year)
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

        elif action == "place_mode":
            from src.build_mode import enter_build_mode
            enter_build_mode(self, self._console, self._ctx)

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
                # Alcohol effects
                extra = getattr(item, 'extra', {}) or {}
                if extra.get("warmth_bonus") or item.id in (
                        "whiskey", "corn_whiskey", "bourbon", "brandy",
                        "rum", "gin", "beer", "mead"):
                    strength = 2.0  # default whiskey
                    if item.id in ("beer", "mead"):
                        strength = 0.5
                    elif item.id in ("brandy", "bourbon"):
                        strength = 2.5
                    elif item.id == "rum":
                        strength = 2.0
                    elif item.id == "gin":
                        strength = 1.5
                    self.player.survival.drink_alcohol(strength)
                    drunk = self.player.survival.drunk_level
                    if drunk >= 9:
                        self.add_message(
                            f"You drink the {item.name}. The world tilts sideways.",
                            "advisory")
                    elif drunk >= 6:
                        self.add_message(
                            f"You drink the {item.name}. Everything's a little fuzzy now.",
                            "normal")
                    elif drunk >= 3:
                        self.add_message(
                            f"You drink the {item.name}. Warm going down. "
                            f"You feel bold.", "normal")
                    else:
                        self.add_message(
                            f"You drink the {item.name}. Takes the edge off.",
                            "normal")
                else:
                    self.add_message(
                        f"You drink. (+{item.hydration:.0f} thirst)", "normal")
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
                         npc_mgr=self.npc_mgr, wildlife_mgr=self.wildlife_mgr,
                         claim_mgr=self.claim_mgr)
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
        """Butcher planning UI for a downed or dead animal."""
        from src.butcher import has_sharp_tool
        from src.menus import pick_from_list

        sp = animal.species
        body_weight = sp.meat_yield_lb * 2.5

        if not has_sharp_tool(self.player):
            self.add_message(
                "You need a knife or axe to butcher.", "advisory")
            # Allow drag/carry without tools
            can_drag, can_carry = self._body_move_options(body_weight)
            if can_drag or can_carry:
                labels = []
                if can_carry:
                    labels.append(f"Pick up carcass ({body_weight:.0f} lb)")
                if can_drag:
                    labels.append(f"Drag carcass ({body_weight:.0f} lb)")
                labels.append("Leave it")
                didx = pick_from_list(self._console, self._ctx,
                                      "No blade — but you can move it.", labels)
                if didx is not None and labels[didx].startswith("Pick up"):
                    self._carry_animal_carcass(animal, body_weight)
                elif didx is not None and labels[didx].startswith("Drag"):
                    self._drag_body(animal.local_x, animal.local_y,
                                    body_weight, animal_ref=animal)
            return

        # Offer: butcher or drag/carry
        options = ["Butcher"]
        can_drag, can_carry = self._body_move_options(body_weight)
        if can_carry:
            options.append(f"Pick up whole ({body_weight:.0f} lb)")
        if can_drag:
            options.append(f"Drag ({body_weight:.0f} lb)")
        if len(options) > 1:
            oidx = pick_from_list(self._console, self._ctx,
                                   f"{sp.display_name} — what do you do?", options)
            if oidx is None:
                return
            if options[oidx].startswith("Pick up"):
                self._carry_animal_carcass(animal, body_weight)
                return
            if options[oidx].startswith("Drag"):
                self._drag_body(animal.local_x, animal.local_y,
                                body_weight, animal_ref=animal)
                return

        # Open the butcher planning UI
        from src.butcher_ui import open_butcher_ui
        msgs = open_butcher_ui(self, self._console, self._ctx, animal)
        for msg in msgs:
            self.add_message(msg, "normal")

    def _body_move_options(self, weight_lb: float):
        """Return (can_drag, can_carry) based on weight and player strength."""
        strength = self.player.attributes.get("strength", 10)
        # Can carry: small bodies up to ~strength × 5 lb (strong player: 90 lb)
        carry_limit = strength * 5
        # Can drag: anything up to strength × 20 lb (strong player: 360 lb)
        drag_limit = strength * 20
        can_carry = weight_lb <= carry_limit
        can_drag = weight_lb <= drag_limit and not can_carry
        return can_drag, can_carry

    def _carry_animal_carcass(self, animal, weight_lb: float):
        """Pick up a small animal carcass as an inventory item."""
        from src.items import Item
        sp = animal.species
        carcass = Item(
            id=f"carcass_{sp.id}", name=f"{sp.display_name} Carcass",
            weight=weight_lb, category="material",
            description=f"Whole carcass of a {sp.display_name}. "
                        f"Can be butchered with a knife.",
            base_value=sp.hide_value + sp.meat_yield_lb * 0.05,
        )
        carcass.extra = {"species_id": sp.id, "meat_yield_lb": sp.meat_yield_lb}
        self.player.inventory.append(carcass)
        animal.state = "butchered"  # remove from map
        self.add_message(
            f"You hoist the {sp.display_name} carcass onto your shoulder. "
            f"({weight_lb:.0f} lb)", "normal")
        self.advance_time(3)

    def _drag_body(self, bx: int, by: int, weight_lb: float,
                   animal_ref=None, npc_ref=None):
        """Drag a body/carcass one tile in a chosen direction."""
        from src.menus import pick_direction_menu
        lmap = self.current_local
        direction = pick_direction_menu(self._console, self._ctx,
            "Drag which direction?")
        if direction is None:
            return
        dx, dy = direction
        nx, ny = bx + dx, by + dy
        if not lmap.in_bounds(nx, ny) or not lmap.is_passable(nx, ny):
            self.add_message("Can't drag it there.", "advisory")
            return
        # Move the body
        if animal_ref:
            animal_ref.local_x = nx
            animal_ref.local_y = ny
            name = animal_ref.species.display_name
        elif npc_ref:
            npc_ref.local_x = nx
            npc_ref.local_y = ny
            name = npc_ref.name
        else:
            return
        # Time cost scales with weight — heavier = slower
        time_cost = max(5, int(weight_lb / 10))
        self.player.survival.fatigue = max(0, self.player.survival.fatigue - 2)
        self.add_message(
            f"You drag the {name} one step. ({weight_lb:.0f} lb, exhausting.)",
            "normal")
        self.advance_time(time_cost)

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

        # Cash on the body
        rng = _rnd.Random(hash(npc.npc_id))
        cash_found = rng.uniform(0.50, 15.00)
        options.append(f"Take ${cash_found:.2f} (coins & dust)")
        option_actions.append(("take_cash", cash_found))

        # Gold dust (prospectors/miners)
        occ = (npc.occupation or "").lower()
        if "prospector" in occ or "miner" in occ:
            gold = rng.uniform(0.01, 0.15)
            options.append(f"Take {gold:.3f} oz gold dust")
            option_actions.append(("take_gold", gold))

        # Actual inventory items (weapons, tools, etc.)
        npc_inv = getattr(npc, 'inventory', [])
        loot_items = []
        for item in npc_inv:
            loot_items.append(item.id)
            options.append(f"Take {item.name}")
            option_actions.append(("take_item", item.id))

        # Dropped weapon on the ground (from disarm)
        dropped = getattr(npc, '_dropped_weapon', None)
        if dropped:
            options.append(f"Pick up {dropped.name} (dropped)")
            option_actions.append(("take_dropped", dropped))

        # If NPC had no inventory, generate a couple random pocket items
        if not npc_inv:
            pocket_items = []
            if rng.random() < 0.4:
                pocket_items.append("hardtack")
            if rng.random() < 0.3:
                pocket_items.append("candle")
            if rng.random() < 0.35:
                pocket_items.append(rng.choice([
                    "percussion_revolver", "bowie_knife", "hunting_knife"]))
            for item_id in pocket_items:
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

        # Drag body option (NPCs ≈ 150 lb)
        npc_weight = 150.0
        can_drag, _ = self._body_move_options(npc_weight)
        if can_drag or npc_weight <= self.player.attributes.get("strength", 10) * 5:
            options.append(f"Drag body ({npc_weight:.0f} lb)")
            option_actions.append(("drag", None))

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
                    item = make_item(data)
                    self.player.inventory.append(item)
                    self.add_message(f"Took {item.name}.", "normal")
                    taken_items.add(data)
                    options[choice] = f"(taken) {item.name}"
                    # Remove from NPC inventory if present
                    npc_inv = getattr(npc, 'inventory', [])
                    for ni in list(npc_inv):
                        if ni.id == data:
                            npc_inv.remove(ni)
                            if npc.equipped_weapon == data:
                                npc.equipped_weapon = None
                            break
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
                # Execute butcher, then loop back so player can pick up results
                self._do_butcher_npc(npc)
                # After butcher, ground items may exist — add pickup option
                lmap = self.current_local
                tile = lmap.tile_at(npc.local_x, npc.local_y) if lmap else None
                if tile and tile.ground_items:
                    for gi in tile.ground_items:
                        options.append(f"Pick up {gi.name}")
                        option_actions.append(("pickup_ground", gi))
                options[choice] = "(butchered)"
                option_actions[choice] = ("done", None)
                continue
            elif act == "pickup_ground":
                gi = data
                lmap = self.current_local
                tile = lmap.tile_at(npc.local_x, npc.local_y) if lmap else None
                if tile and gi in tile.ground_items:
                    tile.ground_items.remove(gi)
                    self.player.inventory.append(gi)
                    self.add_message(f"Took {gi.name}.", "normal")
                    options[choice] = f"(taken) {gi.name}"
            elif act == "take_dropped":
                dropped = data
                self.player.inventory.append(dropped)
                self.add_message(f"Took {dropped.name}.", "normal")
                npc._dropped_weapon = None
                options[choice] = f"(taken) {dropped.name}"
            elif act == "drag":
                self._drag_body(npc.local_x, npc.local_y,
                                npc_weight, npc_ref=npc)
                return  # exit menu after dragging
            self.advance_time(1)

    def _do_butcher_npc(self, npc):
        """Execute the butcher action on an NPC. Places items on ground."""
        from src.menus import pick_from_list
        from src.butcher import has_sharp_tool
        from src.items import Item
        import random as _rnd

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

        rng = _rnd.Random()

        # Human yields — treated as medium-sized creature
        # Generate all possible parts, let player choose via butcher UI
        all_parts = [
            Item(id="human_meat", name=f"{npc.name} Hindquarter",
                 weight=rng.uniform(6, 10), category="food",
                 nutrition=40, perishable=True, days_until_spoil=2,
                 base_value=0.0,
                 description="Human flesh. Most people would find this abhorrent."),
            Item(id="human_meat", name=f"{npc.name} Shoulder",
                 weight=rng.uniform(4, 7), category="food",
                 nutrition=35, perishable=True, days_until_spoil=2,
                 base_value=0.0,
                 description="Human flesh. Deeply disturbing."),
            Item(id="human_meat", name=f"{npc.name} Ribs",
                 weight=rng.uniform(3, 5), category="food",
                 nutrition=30, perishable=True, days_until_spoil=2,
                 base_value=0.0,
                 description="Human ribs. Abhorrent to possess."),
            Item(id="raw_hide", name=f"{npc.name} Skin",
                 weight=5.0, category="material", base_value=0.0,
                 description="Human skin. Deeply disturbing to possess."),
            Item(id="animal_bones", name="Human Bones",
                 weight=4.0, category="material", base_value=0.0,
                 description="Human skeletal remains."),
            Item(id="tallow", name="Human Fat",
                 weight=rng.uniform(1.5, 3.0), category="material",
                 base_value=0.0,
                 description="Rendered human fat."),
            Item(id="sinew", name="Human Sinew",
                 weight=0.3, category="material", base_value=0.0,
                 description="Sinew from a human body."),
        ]

        # Let player pick which parts to take
        part_names = [f"{p.name} ({p.weight:.1f} lb)" for p in all_parts]
        selected = []
        while True:
            display = []
            for i, name in enumerate(part_names):
                prefix = "[X] " if i in selected else "[ ] "
                display.append(f"{prefix}{name}")
            display.append("── Done ──")
            idx = pick_from_list(self._console, self._ctx,
                f"Butcher {npc.display_name()} — select parts", display)
            if idx is None:
                return  # cancelled
            if idx == len(part_names):
                break  # done selecting
            if idx in selected:
                selected.remove(idx)
            else:
                selected.append(idx)

        if not selected:
            return

        yields = [all_parts[i] for i in selected]
        time_min = 15 + len(selected) * 10  # more parts = more time

        # Place on ground
        lmap = self.current_local
        tile = lmap.tile_at(npc.local_x, npc.local_y)
        for item in yields:
            tile.ground_items.append(item)

        # Remove NPC
        npc.present = False
        npc.alive = False

        self.add_message(
            f"You butcher {npc.name}. {len(yields)} parts on the ground.",
            "critical")
        self.advance_time(time_min)
        self.player.gain_skill_xp("survival", 2.0)
        self.player.gain_skill_xp("butchering", 3.0)

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

    def _open_crafting(self, quick_recipe_name: str = ""):
        """Crafting menu — tabbed interface by category.
        If quick_recipe_name is set, skip the menu and craft that recipe directly."""
        if quick_recipe_name:
            from src.crafting import ALL_RECIPES, can_craft, execute_craft
            recipe = None
            for r in ALL_RECIPES:
                if r.name.lower() == quick_recipe_name.lower():
                    recipe = r
                    break
            if recipe:
                ok, reason = can_craft(recipe, self.player.inventory)
                if ok:
                    ok2, msg = execute_craft(recipe, self.player)
                    self.add_message(msg,
                                     "normal" if ok2 else "advisory")
                    if ok2:
                        self.advance_time(recipe.time_minutes)
                        self.action_history.record(f"Craft {recipe.name}")
                else:
                    self.add_message(f"Can't craft {recipe.name}: need {reason}.",
                                     "advisory")
                return
        from src.ui_crafting import open_crafting, _get_last_recipe_name
        results = open_crafting(self._console, self._ctx, self.player)
        if results:
            if isinstance(results, list):
                total_min = 0
                last_name = ""
                for status, msg, minutes in results:
                    self.add_message(msg,
                                     "normal" if status == "crafted" else "advisory")
                    if status == "crafted":
                        total_min += minutes
                if total_min > 0:
                    self.advance_time(total_min)
            else:
                status, msg, minutes = results
                self.add_message(msg,
                                 "normal" if status == "crafted" else "advisory")
                self.advance_time(minutes)
            # Record last crafted recipe as recent action
            recipe_name = _get_last_recipe_name()
            if recipe_name:
                self.action_history.record(f"Craft {recipe_name}")

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

        # Map wounds.py damage types to health_system.py types
        from src.health_system import DmgType as _DT
        _THROW_DTYPE_MAP = {"edged": _DT.SLASH, "piercing": _DT.PIERCE,
                            "blunt": _DT.BLUNT, "explosive": _DT.BLAST}
        hs_dtype = _THROW_DTYPE_MAP.get(dtype, _DT.BLUNT)

        hit_chance = throw_hit_chance(self.player, dist, size)
        if _rnd.random() > hit_chance:
            self.add_message(
                f"You throw the {item.name} — it misses!", "normal")
        else:
            if target_npc:
                target_npc.take_damage(float(dmg), hs_dtype)
                self.add_message(
                    f"You hit {target_npc.display_name()} with the {item.name}! "
                    f"({dmg:.0f} dmg).", "advisory")
                if not target_npc.alive:
                    self.add_message(
                        f"{target_npc.display_name()} is killed.", "critical")
            else:
                target_animal.take_damage(dmg, hs_dtype)
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

    def _find_npc_by_name(self, name: str):
        """Find any known NPC by display name."""
        name_lower = name.lower().strip()
        for npc in self.npc_mgr.npcs.values():
            if npc.name.lower() == name_lower and npc.alive:
                return npc
        if hasattr(self, '_npc_gen'):
            for npc in self._npc_gen.npcs.values():
                if npc.name.lower() == name_lower and npc.alive:
                    return npc
        return None

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
        key = (self.player.world_x, self.player.world_y, self.player.area_x, self.player.area_y)
        lmap = self.locals.get(key)
        s_layout = getattr(lmap, 'town_layout', None) if lmap else None
        log, llm_history = talk_menu(
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
            settlement_layout=s_layout,
            legal=self.legal,
            animal_mgr=self.animal_mgr,
            time_period=self.time.period,
            reputation=self.reputation,
            weather=self.time.weather,
            tribal=getattr(self, 'tribal', None),
            war_system=getattr(self, 'war_system', None),
            region=self.current_local._region_name if self.current_local else "",
        )
        for line in log[-4:]:   # last 4 exchanges into message log
            self.add_message(line, "normal")
        # If NPC went hostile during conversation (provoked), enter combat
        if npc.combat_state == "hostile":
            self.add_message(f"{npc.name} attacks!", "critical")
            from src.combat_mode import enter_combat_mode
            enter_combat_mode(self, self._console, self._ctx)
            return
        # Summarize conversation and store in NPC memory
        if llm_history and len(llm_history) >= 2 and self.llm:
            try:
                from src.npc_system import build_npc_llm_context
                npc_ctx = build_npc_llm_context(npc, self.player)
            except (ImportError, AttributeError):
                npc_ctx = ""
            summary = self.llm.summarize_conversation(
                npc.name, llm_history, npc_ctx)
            if summary and hasattr(npc, 'expanded_memory'):
                current_day = self.time.total_minutes // 1440
                npc.expanded_memory.add(
                    content=summary,
                    day=current_day,
                    significance=0.4,
                    valence=0.1,
                    category="conversation_summary",
                )
        self.advance_time(10)

    def _run_battle_mode(self, battle_state):
        """Run a battle — NPCs fight each other, player participates.
        Runs for multiple rounds until one side breaks or player leaves."""
        import random as _brng
        import time as _btime
        from src.war_system import BattleState

        bs = battle_state
        b = bs.battle
        con = self._console
        ctx = self._ctx
        lmap = self.current_local
        rng = _brng.Random()
        rounds = 0
        max_rounds = 120  # ~6 game hours of fighting — battles are long

        self.add_message(f"── Battle of {b.name} ──", "critical")
        if sum(b.artillery) > 0:
            self.add_message(
                f"Artillery: {b.factions[0]} has {b.artillery[0]} guns, "
                f"{b.factions[1]} has {b.artillery[1]} guns.", "advisory")

        while rounds < max_rounds and not bs.resolved:
            rounds += 1
            bs.patches_fought = max(bs.patches_fought, 1)

            # Get all battle NPCs
            all_npcs = [n for n in self._tile_npcs()
                        if getattr(n, 'faction', '') and n.alive and n.present]

            side0 = [n for n in all_npcs
                     if getattr(n, 'faction', '') == b.factions[0]
                     and n.combat_state == "hostile"]
            side1 = [n for n in all_npcs
                     if getattr(n, 'faction', '') == b.factions[1]
                     and n.combat_state == "hostile"]

            # Check if one side is eliminated on this patch
            if not side0 or not side1:
                if not side0 and not side1:
                    self.add_message("The fighting dies down. Both sides spent.", "normal")
                elif not side0:
                    self.add_message(
                        f"The {b.factions[0]} are driven from this ground. "
                        f"The {b.factions[1]} hold the field.", "normal")
                else:
                    self.add_message(
                        f"The {b.factions[1]} fall back. "
                        f"The {b.factions[0]} hold this position.", "normal")
                    if bs.player_side == 0:
                        bs.flanks_held += 1
                break

            # NPC-vs-NPC combat round
            round_msgs = self.war_system.tick_battle_round(
                bs, all_npcs,
                self.player.local_x, self.player.local_y, rng)

            # Render the scene
            self.recompute_fov()
            self.renderer.render_all(
                lmap, self.world, self.player, self.messages,
                state="local_map", locals_dict=self.locals)
            _on_map = self._tile_npcs()
            self.renderer.draw_npcs(_on_map, lmap, self.player)

            # Battle HUD
            con.draw_rect(0, 0, 120, 1, ord(" "),
                          fg=(255, 255, 255), bg=(100, 15, 15))
            con.print(2, 0, f"BATTLE: {b.name}", fg=(255, 255, 255))
            con.print(50, 0,
                      f"{b.factions[0]}: {len(side0)}  vs  "
                      f"{b.factions[1]}: {len(side1)}",
                      fg=(255, 200, 100))

            # Show round messages
            for msg, sev in round_msgs:
                self.add_message(msg, sev)

            # Show recent messages in combat log area
            log_y = 44
            for i, (msg, sev) in enumerate(self.messages[-4:]):
                fg = (255, 80, 80) if sev == "critical" else (200, 200, 200)
                con.print(1, log_y + i, msg[:78], fg=fg, bg=(0, 0, 0))

            # Controls
            role = bs.player_role
            if role == "fighter":
                con.print(82, 42, "[F] Fire  [D] Drag wounded",
                          fg=(120, 120, 120))
                con.print(82, 43, "[arrows] Move  [ESC] Retreat",
                          fg=(120, 120, 120))
            elif role == "medic":
                con.print(82, 42, "[B] Treat nearest wounded",
                          fg=(120, 120, 120))
                con.print(82, 43, "[D] Drag wounded to safety",
                          fg=(120, 120, 120))
                con.print(82, 44, "[arrows] Move  [ESC] Retreat",
                          fg=(120, 120, 120))
            else:
                con.print(82, 42, "[ESC] Leave  [arrows] Move",
                          fg=(120, 120, 120))

            ctx.present(con)

            # Advance time — each round is ~3 minutes
            self.time.advance_seconds(180)

            # Player input — brief window to act each round
            import tcod.event
            K = tcod.event.KeySym
            _btime.sleep(0.3)  # brief pause so player can read

            acted = False
            for event in tcod.event.get():
                if isinstance(event, tcod.event.Quit):
                    raise SystemExit()
                if isinstance(event, tcod.event.KeyDown):
                    sym = event.sym

                    if sym == K.ESCAPE:
                        self.add_message("You pull back from the fighting.", "normal")
                        bs.resolved = True
                        break

                    # Fighter actions
                    if role == "fighter" and sym == K.f:
                        # Snap shot at nearest enemy
                        from src.combat_mode import _get_held_weapon
                        weapon = _get_held_weapon(self.player)
                        if weapon and weapon.weapon_type == "firearm":
                            loaded = weapon.extra.get("loaded", 0)
                            if loaded > 0:
                                enemies = side1 if bs.player_side == 0 else side0
                                if enemies:
                                    target = min(enemies, key=lambda n:
                                        abs(n.local_x - self.player.local_x) +
                                        abs(n.local_y - self.player.local_y))
                                    from src.combat import player_attack_npc
                                    dist = max(abs(target.local_x - self.player.local_x),
                                               abs(target.local_y - self.player.local_y))
                                    evt = player_attack_npc(
                                        self.player, target, weapon,
                                        distance=dist)
                                    self.add_message(evt.message, "critical" if evt.killed else "normal")
                                    if evt.killed:
                                        bs.enemies_killed += 1
                                        self._on_npc_death(target)
                            else:
                                self.add_message("*click* — reload!", "advisory")
                        acted = True

                    # Medic actions — full health system
                    if role == "medic" and sym == K.b:
                        # Treat nearest wounded ally — uses real wound system
                        all_allies = side0 if bs.player_side == 0 else side1
                        wounded = [n for n in all_allies
                                   if n.health < 60 and n.alive and n.present]
                        if wounded:
                            target = min(wounded, key=lambda n:
                                abs(n.local_x - self.player.local_x) +
                                abs(n.local_y - self.player.local_y))
                            dist = abs(target.local_x - self.player.local_x) + \
                                   abs(target.local_y - self.player.local_y)
                            if dist > 3:
                                self.add_message(
                                    f"{target.name} is wounded {dist * 5}ft away. "
                                    f"Get closer or [D] drag him here.", "advisory")
                            else:
                                # Full medical treatment
                                from src.health_system import PART_DATA
                                wounds = target.wounds.wounds if hasattr(target, 'wounds') else []
                                if wounds:
                                    w = wounds[0]
                                    part_label = PART_DATA.get(w.part, {}).get("label", w.part)
                                    # Bandage bleeding
                                    if w.is_bleeding:
                                        w.is_bleeding = False
                                        w.bleed_level = "none"
                                        self.add_message(
                                            f"You tie off the bleeding on "
                                            f"{target.name}'s {part_label.lower()}.",
                                            "normal")
                                    # Extract lodged projectile
                                    elif w.lodged:
                                        obj = w.lodged
                                        w.lodged = ""
                                        self.add_message(
                                            f"You dig the {obj} out of "
                                            f"{target.name}'s {part_label.lower()}. "
                                            f"He screams.", "normal")
                                    else:
                                        self.add_message(
                                            f"You clean and bandage {target.name}'s "
                                            f"{part_label.lower()} wound.", "normal")
                                else:
                                    target.health = min(100, target.health + 20)
                                    self.add_message(
                                        f"You patch up {target.name}.", "normal")
                                bs.allies_saved += 1
                                self.player.gain_skill_xp("firstAid", 5.0)
                        else:
                            self.add_message("No wounded nearby.", "advisory")
                        acted = True

                    # Drag wounded ally [D] — medic or fighter
                    if sym == K.d:
                        all_allies = side0 if bs.player_side == 0 else side1
                        downed = [n for n in all_allies
                                  if n.health < 30 and n.alive and n.present]
                        if not downed:
                            # Also check enemies — medics can treat anyone
                            if role == "medic":
                                enemies = side1 if bs.player_side == 0 else side0
                                downed = [n for n in enemies
                                          if n.health < 30 and n.alive]
                        if downed:
                            target = min(downed, key=lambda n:
                                abs(n.local_x - self.player.local_x) +
                                abs(n.local_y - self.player.local_y))
                            dist = abs(target.local_x - self.player.local_x) + \
                                   abs(target.local_y - self.player.local_y)
                            if dist <= 2:
                                # Drag to player's position
                                target.local_x = self.player.local_x
                                target.local_y = self.player.local_y
                                target.combat_state = "neutral"  # out of combat
                                bs.allies_saved += 1
                                self.add_message(
                                    f"You grab {target.name} and drag him "
                                    f"behind cover.", "normal")
                                self.player.gain_skill_xp("firstAid", 3.0)
                                self.player.survival.fatigue = max(
                                    0, self.player.survival.fatigue - 5)
                            else:
                                self.add_message(
                                    f"{target.name} is down {dist * 5}ft away. "
                                    f"Get closer to drag him.", "advisory")
                        else:
                            self.add_message("No one to drag.", "advisory")
                        acted = True

                    # Movement for all roles
                    moves = {K.UP: (0, -1), K.DOWN: (0, 1),
                             K.LEFT: (-1, 0), K.RIGHT: (1, 0)}
                    if sym in moves:
                        dx, dy = moves[sym]
                        nx = self.player.local_x + dx
                        ny = self.player.local_y + dy
                        if lmap.in_bounds(nx, ny) and lmap.is_passable(nx, ny):
                            self.player.local_x = nx
                            self.player.local_y = ny
                        acted = True
                    break

            # Check player health
            if self.player.survival.health <= 0:
                self._trigger_death(f"Killed at the Battle of {b.name}.")
                return

            # Apply cannon damage to player from this round
            cannon_hit = bs.roll_cannon_fire(
                self.player.local_x, self.player.local_y, rng)
            if cannon_hit and cannon_hit["damage"] > 0:
                self.player.survival.health = max(
                    0, self.player.survival.health - cannon_hit["damage"])
                if cannon_hit["hit_type"] == "direct":
                    self.add_message(
                        f"You're hit by shrapnel! ({cannon_hit['damage']} damage)",
                        "critical")
                elif cannon_hit["hit_type"] == "near_miss":
                    self.add_message(
                        f"Debris hits you. ({cannon_hit['damage']} damage)",
                        "advisory")

        # Battle over — resolve outcome
        if not bs.resolved:
            outcome = bs.resolve_outcome()
            self.add_message(bs.outcome_message(), "critical")

        # Clean up battle NPCs
        for npc_id in list(self._npc_gen.npcs.keys()):
            if npc_id.startswith(f"battle_{b.battle_id}_"):
                npc = self._npc_gen.npcs[npc_id]
                if not npc.alive:
                    npc.present = False  # dead stay as bodies
                else:
                    npc.combat_state = "neutral"
                    npc.present = False  # survivors leave

        self._active_battle = None
        self.add_message(f"── End of Battle: {b.name} ──", "normal")

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
                if evt.event_type not in ("letter", "friend_letter"):
                    continue
                # Find nearest town for delivery
                from src.world_gen import era_locations
                nearest_town = ""
                best_dist = 9999
                for loc in era_locations(self.time.year):
                    d = abs(loc.x - self.player.world_x) + abs(loc.y - self.player.world_y)
                    if d < best_dist and loc.loc_type in ("town", "city"):
                        best_dist = d
                        nearest_town = loc.name
                if not nearest_town:
                    continue

                body = evt.description
                # Friend/spouse letters: use LLM for a personal letter
                if evt.event_type == "friend_letter" and self.llm:
                    npc = self._npc_gen.npcs.get(evt.npc_id)
                    if npc:
                        try:
                            from src.npc_system import build_npc_llm_context
                            npc_ctx = build_npc_llm_context(npc, self.player)
                        except (ImportError, AttributeError):
                            npc_ctx = f"Name: {evt.npc_name}"
                        # Get NPC memories of player for context
                        memories = ""
                        if hasattr(npc, 'expanded_memory'):
                            important = npc.expanded_memory.get_important(5)
                            if important:
                                memories = "\n".join(
                                    f"- {e.content}" for e in important)
                        prompt_ctx = npc_ctx
                        if memories:
                            prompt_ctx += (
                                f"\n\nYOUR MEMORIES OF THE PLAYER:\n{memories}")
                        body = self.llm.generate_letter_reply(
                            evt.npc_name, prompt_ctx,
                            "(no prior letter — you are writing first, "
                            "to catch up with your friend)")
                        # Store what they wrote so they remember it in person
                        npc.expanded_memory.add(
                            content=f"Wrote a letter to {self.player.name}: \"{body[:120]}\"",
                            day=self.time.total_minutes // 1440,
                            significance=0.5,
                            valence=0.2,
                            category="interaction",
                        )

                self.writing.mail.send_letter(
                    sender=evt.npc_name,
                    recipient=self.player.name,
                    body=body,
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

        year = getattr(self.player, 'start_year',
                       getattr(self, 'game_year', 1849))

        # Era-aware getting started text
        if year < 1800:
            era_intro = [
                ("You are a long hunter on the Appalachian", WHITE),
                ("frontier. Deer hides are money — a good", WHITE),
                ("buck is worth a dollar. The Revolution rages", WHITE),
                ("east; out here, it's you vs. the wilderness.", WHITE),
            ]
            era_steps = [
                ("1. Hunt deer [H] and skin them [P].", WHITE),
                ("2. Sell hides at a trading post or fort.", WHITE),
                ("3. Trap beaver and other furbearers [Y].", WHITE),
                ("4. Explore west — uncharted country.", WHITE),
                ("5. Eat, drink, sleep. Don't die.", WHITE),
            ]
            gold_line = "Gold: $19.00/oz (rare in Appalachians)."
        elif year < 1845:
            era_intro = [
                ("You are a mountain man in the Rockies.", WHITE),
                ("Beaver pelts fuel the fur trade. No towns,", WHITE),
                ("no law, no map past the Missouri.", WHITE),
                ("The Rendezvous is your link to civilization.", WHITE),
            ]
            era_steps = [
                ("1. Trap beaver along streams [Y].", WHITE),
                ("2. Sell pelts at Rendezvous or forts.", WHITE),
                ("3. Hunt for food — buy nothing you can", WHITE),
                ("   kill or make yourself.", WHITE),
                ("4. Learn the land. Survive the winter.", WHITE),
            ]
            gold_line = "Gold: $19.39/oz (not yet discovered out here)."
        elif year < 1870:
            era_intro = [
                ("The Gold Rush is on. River bars and rumors.", WHITE),
                ("No law west of Missouri. Pan for gold, sell", WHITE),
                ("it, buy supplies, don't starve. Everything", WHITE),
                ("else is up to you.", WHITE),
            ]
            era_steps = [
                ("1. Find water (~) and gravel (:). Pan [M].", WHITE),
                ("2. If you see color, keep panning that spot.", WHITE),
                ("3. Sell gold in town. [T] talk to merchant.", WHITE),
                ("4. Build a sluice [B] for 6x throughput.", WHITE),
                ("5. Buy food and supplies. Don't starve.", WHITE),
            ]
            gold_line = "Gold: $20.67/oz (US Mint fixed price)."
        elif year < 1934:
            era_intro = [
                ("The easy placer gold is played out. Lode", WHITE),
                ("mining, dynamite, and stamp mills define", WHITE),
                ("the era. Fortunes still exist for those", WHITE),
                ("who dig deep and think smart.", WHITE),
            ]
            era_steps = [
                ("1. Prospect for lode deposits — dig deep.", WHITE),
                ("2. Build equipment [B] to process ore.", WHITE),
                ("3. Stake claims. Buy property.", WHITE),
                ("4. Run a business — mining or otherwise.", WHITE),
                ("5. The railroad connects everything now.", WHITE),
            ]
            gold_line = "Gold: $20.67/oz (fixed until 1934)."
        elif year < 1972:
            era_intro = [
                ("FDR raised gold to $35/oz. Every creek", WHITE),
                ("and hillside looks worth prospecting again.", WHITE),
                ("Hard times breed hard men.", WHITE),
                ("The law is thin in the back country.", WHITE),
            ]
            era_steps = [
                ("1. Prospect old claims — overlooked gold.", WHITE),
                ("2. Pan, sluice, or dredge creek beds.", WHITE),
                ("3. Sell at $35/oz — nearly double the old", WHITE),
                ("   price.", WHITE),
                ("4. Watch for uranium (Atomic Age, 1948+).", WHITE),
            ]
            gold_line = "Gold: $35.00/oz (FDR fixed price)."
        else:
            era_intro = [
                ("Gold trades on the free market for the", WHITE),
                ("first time since 1934. Permits and NEPA", WHITE),
                ("gate every operation — bureaucracy is the", WHITE),
                ("new wilderness to navigate.", WHITE),
            ]
            era_steps = [
                ("1. File permits. Stake legal claims.", WHITE),
                ("2. Prospect with modern equipment.", WHITE),
                ("3. Sell on the open market — prices rise.", WHITE),
                ("4. Navigate regulations or face fines.", WHITE),
                ("5. Small-scale placer still works.", WHITE),
            ]
            gold_line = "Gold: free market (~$120+/oz, rising)."

        pages = [
            # Page 1: Getting Started (era-aware)
            [
                ("GETTING STARTED", YELLOW),
                ("", GREY),
            ] + era_intro + [
                ("", GREY),
                ("FIRST STEPS", YELLOW),
            ] + era_steps + [
                ("", GREY),
                ("TERRAIN", YELLOW),
                (":  Gravel bar — pan here for gold", WHITE),
                ("~  Water — panning, drinking, sluicing", WHITE),
                ("^  Pine tree   T  Oak/other tree", WHITE),
                (".  Ground/grass   #  Rock (impassable)", WHITE),
                (";  Brush   o  Shallow pit   O  Deep pit", WHITE),
                ("=  Tailings (sluice waste)", WHITE),
                ("", GREY),
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
                ("MENUS & MODES", YELLOW),
                ("I  Inventory (items, clothing, equip)", CYAN),
                ("C  Character (stats, health, wounds)", CYAN),
                ("J  Journal (diary, people, places, mail)", CYAN),
                ("A  Actions (eat, drink, forage, custom...)", CYAN),
                ("T  Talk (conversation, trade, hire, barter)", CYAN),
                ("B  Build (structures, walls, furniture)", CYAN),
                ("E  Examine (look at surroundings)", CYAN),
                ("P  Pickup items / Butcher carcasses", CYAN),
                ("L  Message log (scroll history)", CYAN),
                ("G  Gold overlay (panned tile grades)", CYAN),
                ("M  Mining mode (pan/sluice area select)", CYAN),
                ("H  Hunting mode (stalk, track, shoot)", CYAN),
                ("Y  Trapping mode (set, check, collect)", CYAN),
                ("K  Enter combat mode", CYAN),
                ("S  Cycle stance  |  W  Cycle speed", CYAN),
                ("Ctrl+S  Save game  |  ?  This help", CYAN),
            ],
            # Page 3: Mining Mode
            [
                ("MINING MODE [M]", YELLOW),
                ("", GREY),
                ("Select tiles to work, then auto-mine.", WHITE),
                ("Your @ walks to each tile, pans or hauls", WHITE),
                ("to sluice, and repeats. You watch it work.", WHITE),
                ("", GREY),
                ("SELECTION", CYAN),
                ("  Arrows     Move cursor", WHITE),
                ("  Space      Toggle tile on/off", WHITE),
                ("  S twice    Rectangle select (anchor+end)", WHITE),
                ("  D          Deselect tile under cursor", WHITE),
                ("  C          Clear all selected tiles", WHITE),
                ("  < >        Z-level cursor up/down", WHITE),
                ("  R          Dig ramp to lower level", WHITE),
                ("  Tab        Switch pan / sluice mode", WHITE),
                ("  Enter      Start working selected tiles", WHITE),
                ("  Esc        Exit mining mode", WHITE),
                ("", GREY),
                ("PAN MODE: walk to tile, walk to water, pan.", WHITE),
                ("  Shows live gold count (you see it in pan).", WHITE),
                ("SLUICE MODE: walk to tile, shovel, walk to", WHITE),
                ("  sluice, dump. Riffles fill up — clean out", WHITE),
                ("  when prompted. Enter = cleanout.", WHITE),
                ("", GREY),
                ("Auto-stops if hungry, thirsty, exhausted,", WHITE),
                ("or hostiles approach.", WHITE),
            ],
            # Page 4: Hunting, Trapping, Fishing
            [
                ("HUNTING MODE [H]", YELLOW),
                ("", GREY),
                ("  Arrows   Sneak (quieter, slower)", WHITE),
                ("  F        Fire at target", WHITE),
                ("  Tab      Cycle between animals", WHITE),
                ("  R        Reload", WHITE),
                ("  Space    Wait / watch", WHITE),
                ("  H / Esc  Exit hunting mode", WHITE),
                ("  Tracking skill reveals tracks + trails", WHITE),
                ("", GREY),
                ("TRAPPING MODE [Y]", YELLOW),
                ("  S  Set trap (snare, deadfall, pit, cage)", WHITE),
                ("  C  Check trap for catches", WHITE),
                ("  R  Reset / rebait trap", WHITE),
                ("  P  Pick up trap", WHITE),
                ("  Tab  Cycle between set traps", WHITE),
                ("  F  Craft (make traps, bait in field)", WHITE),
                ("  B  Toggle auto-bait", WHITE),
                ("  T  Select default trap type", WHITE),
                ("  N  Select default bait", WHITE),
                ("  Shows animal sign overlay on map", WHITE),
                ("", GREY),
                ("FISHING (Actions menu)", YELLOW),
                ("  6 methods: hands, net, rod, trap,", WHITE),
                ("  weir, spear. Skill affects catch rate.", WHITE),
                ("  Canoe gives bonus to fishing.", WHITE),
            ],
            # Page 5: Combat
            [
                ("COMBAT [K]", YELLOW),
                ("", GREY),
                ("Auto-enters when hostiles attack.", WHITE),
                ("", GREY),
                ("  F   Snap shot (fast, normal accuracy)", WHITE),
                ("  G   Careful aim (slow, +5 accuracy)", WHITE),
                ("  R   Reload weapon", WHITE),
                ("  X   Melee attack / rush to target", WHITE),
                ("  Z   Grapple (wrestle at close range)", WHITE),
                ("  T   Throw item at target", WHITE),
                ("  W   Swap weapon", WHITE),
                ("  Tab Cycle targets", WHITE),
                ("  1-6 Aim: legs/abdomen/chest/arm/head/eye", WHITE),
                ("  C   Crouch / stand toggle", WHITE),
                ("  X   Take cover (rush to nearest)", WHITE),
                ("  I   Intimidate (force morale check)", WHITE),
                ("  S   Accept surrender (disarm/release)", WHITE),
                ("  V   Free look (snap to target)", WHITE),
                ("  Space  Hold / wait", WHITE),
                ("  Q   Flee (enemies get parting shot)", WHITE),
                ("", GREY),
                ("COVER: trees/rocks = partial (-4 to hit).", WHITE),
                ("Boulders = full cover. Crouch + partial =", WHITE),
                ("full. NPCs stay melee unless you draw a gun", WHITE),
                ("or someone gets badly hurt.", WHITE),
                ("", GREY),
                ("Firearms are LETHAL. One shot can kill.", WHITE),
                ("Wounds bleed. Bandage fast or die.", WHITE),
            ],
            # Page 6: Survival & Health
            [
                ("SURVIVAL", YELLOW),
                ("", GREY),
                ("Hunger/Thirst/Fatigue drain over time.", WHITE),
                ("  0 hunger = 1 HP/hr   0 thirst = 3 HP/hr", WHITE),
                ("Eat, drink, sleep regularly. Carry a canteen.", WHITE),
                ("Overloaded = slow. Drop what you don't need.", WHITE),
                ("", GREY),
                ("DISEASE", YELLOW),
                ("Cholera/dysentery: boil water to prevent.", WHITE),
                ("Malaria: camp near smoke to repel mosquitoes.", WHITE),
                ("Smallpox: no cure, pray for constitution.", WHITE),
                ("Wound infection: keep wounds bandaged clean.", WHITE),
                ("Treat with medicine (willow tea, quinine,", WHITE),
                ("laudanum). Diseases warn before they kill.", WHITE),
                ("", GREY),
                ("ALCOHOL", YELLOW),
                ("Drinking adds warmth but drains fatigue.", WHITE),
                ("Buzzed (1-3), Drunk (4-6, aim -2),", WHITE),
                ("Hammered (7-9, aim -8), Blackout (10+).", WHITE),
                ("Metabolizes ~1 level per hour.", WHITE),
                ("", GREY),
                ("WOUNDS", YELLOW),
                ("Inspect wounds [A]. Bandage to stop bleed.", WHITE),
                ("Untreated wounds infect. Limb wounds slow", WHITE),
                ("you or disable aim. Head wounds blur vision.", WHITE),
            ],
            # Page 7: Economy & Trade
            [
                ("ECONOMY & TRADE", YELLOW),
                ("", GREY),
                (gold_line, WHITE),
                ("Merchants lowball 35-40%. Haggle for more.", WHITE),
                ("Trading skill + charisma improve prices.", WHITE),
                ("", GREY),
                ("BARTER", CYAN),
                ("Trade items directly — no cash needed.", WHITE),
                ("Tobacco, salt, pelts, ammo work as currency", WHITE),
                ("on the frontier.", WHITE),
                ("", GREY),
                ("BUSINESSES", CYAN),
                ("Buy/build: saloon, store, smithy, sawmill,", WHITE),
                ("bakery, livery, hotel, assay office, more.", WHITE),
                ("Hire managers, set prices, run production:", WHITE),
                ("  Sawmill: logs -> planks", WHITE),
                ("  Bakery: flour -> bread", WHITE),
                ("  Blacksmith: iron -> nails + horseshoes", WHITE),
                ("Work it yourself [A] or manage from afar.", WHITE),
                ("", GREY),
                ("PROPERTY", CYAN),
                ("Buy town lots from land agents. Build on", WHITE),
                ("your own land. Store items on your property.", WHITE),
                ("", GREY),
                ("CRIMES", CYAN),
                ("Witnesses report crimes (200ft day, 75ft", WHITE),
                ("night). Reputation affects all NPC dealings.", WHITE),
            ],
            # Page 8: NPCs & Social
            [
                ("NPCs & SOCIAL", YELLOW),
                ("", GREY),
                ("TALKING [T]", CYAN),
                ("Introduce, ask name, trade, barter, hire.", WHITE),
                ("Ask rumors — gold, bandits, bounties, lost", WHITE),
                ("travelers, abandoned claims.", WHITE),
                ("NPCs remember you. Relationships build.", WHITE),
                ("", GREY),
                ("LANGUAGE BARRIERS", CYAN),
                ("Non-English speakers: gesture -> pidgin ->", WHITE),
                ("fluent. Learn words [T], practice, or find", WHITE),
                ("a bilingual NPC for lessons.", WHITE),
                ("Tribal languages, Chinese, Spanish, French,", WHITE),
                ("German — each learned separately.", WHITE),
                ("", GREY),
                ("COMPANIONS & HIRE", CYAN),
                ("Ask NPCs to join you. Delegate tasks.", WHITE),
                ("Hire workers for businesses or claims.", WHITE),
                ("", GREY),
                ("MARRIAGE", CYAN),
                ("Build relationship: stranger -> friend ->", WHITE),
                ("close friend -> courting -> engaged -> wed.", WHITE),
                ("Requires romantic interest 60+ and a", WHITE),
                ("preacher for the ceremony.", WHITE),
                ("", GREY),
                ("PROVOCATION", CYAN),
                ("Insults and threats anger NPCs. Pick fights", WHITE),
                ("carefully — or run.", WHITE),
            ],
            # Page 9: Building & Crafting
            [
                ("BUILDING [B]", YELLOW),
                ("", GREY),
                ("BUILD MODE KEYS", CYAN),
                ("  Arrows   Move cursor", WHITE),
                ("  Tab      Cycle tool (wall/door/window..)", WHITE),
                ("  Enter    Place element", WHITE),
                ("  F        Toggle floor type", WHITE),
                ("  U        Undo last placement", WHITE),
                ("  < >      Z-level up/down", WHITE),
                ("  Esc      Exit build mode", WHITE),
                ("", GREY),
                ("Walls, doors, windows, fences, iron bars.", WHITE),
                ("Wood or stone. Multi-level structures.", WHITE),
                ("Zones: kitchen, workshop, bedroom, storage.", WHITE),
                ("", GREY),
                ("CONSTRUCTION [A -> Build menu]", YELLOW),
                ("Sluice box, rocker, long tom, arrastra,", WHITE),
                ("cabin, lean-to, drying rack, fleshing beam.", WHITE),
                ("Some items are portable — pick up and move.", WHITE),
                ("Continue incomplete builds [A] at the site.", WHITE),
                ("", GREY),
                ("CRAFTING [A -> Craft]", YELLOW),
                ("127+ recipes: food, weapons, ammo, tools,", WHITE),
                ("clothing, shelters, traps, medicine.", WHITE),
                ("Need materials + sometimes a fire or bench.", WHITE),
                ("", GREY),
                ("CUSTOM ACTIONS [A -> type anything]", YELLOW),
                ("AI resolves it. 'build a still', 'carve a", WHITE),
                ("canoe', 'write a letter'. If you have the", WHITE),
                ("tools and materials, it can happen.", WHITE),
            ],
            # Page 10: World & Travel
            [
                ("WORLD MAP & TRAVEL", YELLOW),
                ("", GREY),
                ("[ zoom out, ] zoom in. 5 zoom levels.", WHITE),
                ("Enter on any tile = fast travel there.", WHITE),
                ("Compass in sidebar shows nearest town.", WHITE),
                ("", GREY),
                ("PACK ANIMALS", CYAN),
                ("Mule (250lb), horse (150lb), donkey (100lb),", WHITE),
                ("ox (350lb). Buy at liveries. Feed and rest", WHITE),
                ("them or they die. Named and persistent.", WHITE),
                ("", GREY),
                ("VEHICLES", CYAN),
                ("Handcart, mule cart, wagon, freight wagon.", WHITE),
                ("Canoe, pirogue, flatboat, keelboat.", WHITE),
                ("Larger = more cargo, slower, needs crew.", WHITE),
                ("", GREY),
                ("RIVER TRAVEL", CYAN),
                ("Board canoe at water's edge [A]. Paddle", WHITE),
                ("downstream fast, upstream slow. Portage", WHITE),
                ("small boats around rapids. Fishing bonus.", WHITE),
                ("Steamboat routes on major rivers.", WHITE),
                ("", GREY),
                ("FRONTIER LINE", CYAN),
                ("The frontier moves west over the decades.", WHITE),
                ("Past the frontier: no towns, more danger,", WHITE),
                ("more wildlife, more opportunity.", WHITE),
                ("", GREY),
                ("FORAGING [A -> Forage]", CYAN),
                ("50+ plants by region/season. Some need", WHITE),
                ("knowledge to identify. Medicinal herbs too.", WHITE),
            ],
            # Page 11: War & Combat Events
            [
                ("WARS & BATTLES", YELLOW),
                ("", GREY),
                ("Historical wars happen at the right time", WHITE),
                ("and place. You're a civilian caught in it.", WHITE),
                ("", GREY),
                ("EFFECTS: supply shortages, price spikes,", WHITE),
                ("military patrols, refugees, destroyed towns.", WHITE),
                ("", GREY),
                ("PARTICIPATION", CYAN),
                ("Enlist at forts [T]: scout, soldier, medic.", WHITE),
                ("Or stay neutral — trade with both sides,", WHITE),
                ("profit from shortages, avoid the fighting.", WHITE),
                ("", GREY),
                ("BATTLES", CYAN),
                ("Near a battle: hear cannon fire, choose to", WHITE),
                ("join, observe, or flee.", WHITE),
                ("  Fighter: kill enemies, earn faction rep", WHITE),
                ("  Medic: drag wounded, bandage, save lives", WHITE),
                ("  Observer: watch from safety, loot after", WHITE),
                ("", GREY),
                ("Your actions affect small battle outcomes.", WHITE),
                ("Large battles are decided by history — but", WHITE),
                ("your survival and reputation still matter.", WHITE),
                ("", GREY),
                ("Wartime kills of enemy combatants are NOT", WHITE),
                ("crimes. Killing civilians still is.", WHITE),
                ("Desertion puts a bounty on your head.", WHITE),
            ],
            # Page 12: Prospecting Tips
            [
                ("PROSPECTING TIPS", YELLOW),
                ("", GREY),
                ("WHERE TO FIND GOLD", CYAN),
                ("Gravel bars on inside bends = best gold.", WHITE),
                ("Bedrock crevices trap heavy gold.", WHITE),
                ("Dig deeper for richer pay layers.", WHITE),
                ("Geology skill reveals ground quality.", WHITE),
                ("Gold overlay [G] shows what you've found.", WHITE),
                ("Ground depletes — move to new spots.", WHITE),
                ("", GREY),
                ("EQUIPMENT", CYAN),
                ("Pan: slow but portable. Good for sampling.", WHITE),
                ("Rocker: 2x pan speed. Small, movable.", WHITE),
                ("Sluice: 6x throughput. Needs water flow.", WHITE),
                ("Long tom: biggest. Needs a crew.", WHITE),
                ("", GREY),
                ("REGIONAL GOLD", CYAN),
                ("Appalachians: small but very pure (.95+).", WHITE),
                ("California: biggest nuggets (up to 25oz).", WHITE),
                ("Colorado/Montana: good placer + lode.", WHITE),
                ("Great Plains: essentially zero.", WHITE),
                ("Desert SW: sparse but rich pockets.", WHITE),
                ("", GREY),
                ("RUMORS [T]", CYAN),
                ("Ask NPCs about gold, strikes, claims.", WHITE),
                ("Rumors point to real locations.", WHITE),
                ("The journal [J] tracks what you've heard.", WHITE),
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

        W, H = 40, 20
        X = (con.width - W) // 2
        Y = (con.height - H) // 2
        selected = 0

        options = [
            "Resume",
            "Save Game",
            f"Music Volume: {int(self.music.volume * 100)}%",
            f"Music: {'ON' if self.music.enabled else 'OFF'}",
            "Report Bug",
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
                        from src.bug_report import open_bug_report_ui
                        result = open_bug_report_ui(self, con, ctx)
                        if result:
                            self.add_message(result, "advisory")
                    elif selected == 5:
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

        # Join active battle
        bs = getattr(self, '_active_battle', None)
        if bs and not bs.resolved:
            actions.insert(0, f"Join battle ({bs.battle.factions[0]})")
            actions.insert(1, f"Join battle ({bs.battle.factions[1]})")
            actions.insert(2, "Serve as medic")
            actions.insert(3, "Observe battle from distance")

        # Captivity actions
        if hasattr(self, 'tribal'):
            for tribe_name in self.tribal.standings:
                ts = self.tribal.get_standing(tribe_name)
                if ts.captive:
                    actions.insert(0, "Attempt escape (night)")
                    if ts.standing >= 0 and ts.language_level in ("pidgin", "fluent") \
                            and ts.captive_days >= 21:
                        actions.insert(0, "Accept adoption")
                        actions.insert(1, "Refuse adoption")
                    break

        if near_water:
            actions.append("Fill canteen")
            # Canoe actions — launch if carrying, board if deployed
            has_canoe = any("water_vehicle" in getattr(i, "tool_tags", [])
                           for i in self.player.inventory)
            if has_canoe:
                actions.append("Launch canoe")
            deployed = getattr(self, '_deployed_canoe', None)
            if deployed:
                actions.append("Board canoe (river travel)")
                vtype_id = deployed.get("vehicle_type", "")
                from src.vehicles import VEHICLE_TYPES
                _vt = VEHICLE_TYPES.get(vtype_id)
                if _vt and _vt.portable:
                    actions.append("Portage canoe (carry overland)")
                actions.append("Pick up canoe")

        # In canoe — can disembark
        if getattr(self.player, '_in_canoe', False):
            actions.insert(0, "Disembark (leave canoe)")
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
            # Dry soaked items near fire
            soaked = [i for i in self.player.inventory
                      if getattr(i, 'extra', None) and i.extra.get("soaked")]
            if soaked:
                actions.append(f"Dry soaked gear ({len(soaked)} items)")

        sluice = self._nearby_structure("pan_gold", radius=3)
        if sluice:
            if "sluice" in sluice.name.lower():
                actions.append("Work the sluice")
            else:
                actions.append("Work the rocker")

        shelter = self._nearby_structure("shelter", radius=2)
        if shelter:
            actions.append("Rest here")

        # Incomplete structures nearby — can continue building
        from src.construction import PlacedEquipment
        for sid, s in lmap.structures.items():
            if not isinstance(s, PlacedEquipment):
                continue
            if s.complete:
                continue
            if max(abs(s.x - px), abs(s.y - py)) <= 2:
                pct = int(s.progress)
                actions.insert(0, f"Continue building {s.name} ({pct}%)")
                break

        # Player's business nearby — can work it
        for biz in self.business_mgr.businesses.values():
            if biz.active and biz.world_x == self.player.world_x \
                    and biz.world_y == self.player.world_y:
                actions.append(f"Work at {biz.name}")
                break

        # Portable structures nearby — can pick up
        from src.construction import PlacedEquipment, EQUIPMENT_BLUEPRINTS
        for sid, s in lmap.structures.items():
            if not isinstance(s, PlacedEquipment):
                continue
            if max(abs(s.x - px), abs(s.y - py)) > 2:
                continue
            bp = EQUIPMENT_BLUEPRINTS.get(s.blueprint_key)
            if bp and bp.portable and s.complete:
                # Don't offer pickup if items are drying on it
                if hasattr(s, '_drying') and s._drying:
                    continue
                actions.append(f"Pick up {s.name}")

        # Near NPCs? (6 tiles = 30ft conversation range)
        nearby_npcs = [n for n in self._tile_npcs()
                       if n.alive and max(abs(n.local_x - px), abs(n.local_y - py)) <= 6]
        if nearby_npcs:
            actions.append("Talk to nearby person")
            actions.append("Rob someone")
            # Check if any nearby NPC is at a gambling location
            for n in nearby_npcs:
                if any(w in getattr(n, 'occupation', '').lower()
                       for w in ('bartender', 'gambler')):
                    actions.append("Gamble (cards)")
                    break

        # Near a gambling table — can always gamble there
        near_gambling = False
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                nx, ny = px + dx, py + dy
                if lmap.in_bounds(nx, ny) and lmap.tiles[ny][nx].terrain == LocalTerrain.GAMBLING_TABLE:
                    near_gambling = True
                    break
            if near_gambling:
                break
        if near_gambling and "Gamble (cards)" not in actions:
            actions.append("Gamble (cards)")

        # Trapping — show if player has traps or has set traps nearby
        has_traps = any("trap" in getattr(i, "tool_tags", [])
                        for i in self.player.inventory)
        if has_traps:
            actions.append("Set trap")
        nearby_traps = self.trap_mgr.traps_at(
            self.player.world_x, self.player.world_y,
            self.player.area_x, self.player.area_y)
        if nearby_traps:
            caught = sum(1 for t in nearby_traps if t.caught_species)
            if caught:
                actions.append(f"Check traps ({caught} caught!)")
            else:
                actions.append("Check traps")

        # Clean fish — when player has fresh fish and a knife
        has_fresh_fish = any(i.id == "fresh_fish" for i in self.player.inventory)
        if has_fresh_fish:
            actions.append("Clean fish")

        # Medical — show when wounded or sick
        if self.player.wounds.wounds:
            actions.append("Inspect wounds")
            if any(not getattr(w, '_cleaned', False)
                   for w in self.player.wounds.wounds):
                actions.append("Clean wounds")
            if any(w.is_bleeding for w in self.player.wounds.wounds):
                actions.append("Bandage wounds")
            if any(w.lodged for w in self.player.wounds.wounds):
                actions.append("Extract lodged object")
        if self.player.survival.is_gut_sick:
            actions.append("Treat gut sickness")

        # Trees nearby — fell or chop
        TREE_TILES = (LocalTerrain.PINE, LocalTerrain.OAK, LocalTerrain.ASPEN,
                      LocalTerrain.JUNIPER, LocalTerrain.CEDAR, LocalTerrain.MAPLE,
                      LocalTerrain.CHESTNUT, LocalTerrain.HICKORY, LocalTerrain.CYPRESS,
                      LocalTerrain.MAGNOLIA, LocalTerrain.FOREST)
        has_axe = any("chop" in getattr(i, "tool_tags", [])
                      for i in self.player.inventory)
        near_tree = False
        near_downed = False
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                nx, ny = px + dx, py + dy
                if lmap.in_bounds(nx, ny):
                    t = lmap.tiles[ny][nx].terrain
                    if t in TREE_TILES:
                        near_tree = True
                    if t == LocalTerrain.DOWNED_TREE:
                        near_downed = True
            if near_tree and near_downed:
                break
        if near_tree and has_axe:
            actions.append("Fell tree")
        if near_downed and has_axe:
            actions.append("Chop wood (logs)")
        if near_tree and not has_axe:
            actions.append("Gather firewood")

        # Build campfire — outdoors with wood/logs
        if not fire:
            has_wood = any(i.id in ("log", "firewood", "plank", "kindling")
                          for i in self.player.inventory)
            if has_wood or near_tree:
                actions.append("Build campfire")

        # Camp — always available outdoors
        if not (hasattr(lmap, 'town_layout') and lmap.town_layout):
            actions.append("Make camp")

        # Crafting — always available if player has any raw materials
        raw_mats = ("raw_hide", "animal_bones", "tallow", "sinew", "antlers",
                    "bird_feathers", "log", "plank", "rope_10ft")
        if any(i.id in raw_mats for i in self.player.inventory):
            actions.append("Craft")

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

        # Furniture interactions — check adjacent tiles for interactive furniture
        from src.furniture import get_furniture_actions
        checked_terrains = set()
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                nx, ny = px + dx, py + dy
                if not lmap.in_bounds(nx, ny):
                    continue
                ft = lmap.tile_at(nx, ny).terrain
                if ft in checked_terrains:
                    continue
                f_actions = get_furniture_actions(ft)
                for fa in f_actions:
                    if fa.label not in actions:
                        actions.append(fa.label)
                checked_terrains.add(ft)

        # Scout / Read sign — always available outdoors
        if not (hasattr(lmap, 'town_layout') and lmap.town_layout):
            actions.append("Read sign / Scout area")

        # Investigate — show when a recent event message hints at something
        _investigate_hints = ("tracks", "smoke", "campfire", "vulture",
                              "figure", "movement", "smell", "coffee",
                              "boot print", "wagon", "drag mark",
                              "dead", "circling", "someone")
        recent_msgs = [m[0].lower() for m in self.messages[-5:]]
        if any(hint in msg for msg in recent_msgs for hint in _investigate_hints):
            actions.insert(0, "Investigate nearby")

        # Mount/dismount
        if self.player.mounted:
            actions.append("Dismount")
        elif any(a.alive and a.species.rideable for a in self.animal_mgr.animals):
            actions.append("Mount horse")

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
        px, py = self.player.local_x, self.player.local_y
        tile = lmap.tile_at(px, py)

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
        # ── Business management ───────────────────────────────────────────
        _BIZ_WORDS = ("business", "company", "shop",
                      "trading", "freight", "operation", "enterprise")
        _NOT_BIZ = ("fire", "fight", "camp", "snare", "trap",
                    "saloon", "store item", "store gear", "store supplies")
        is_biz_action = (a == "business" or a == "ledger" or
                         (any(w in a for w in _BIZ_WORDS) and
                          not any(w in a for w in _NOT_BIZ)))
        if is_biz_action:
            from src.business_ui import open_business_ui
            open_business_ui(self, self._console, self._ctx)
            return

        # ── Rob / Hold up ─────────────────────────────────────────────────
        if "rob" in a or "hold up" in a or "holdup" in a or "stick up" in a or \
           "demand money" in a or "mug" in a:
            from src.menus import pick_from_list
            nearby = [n for n in self._tile_npcs()
                      if n.alive and n.present and n.combat_state == "neutral"
                      and max(abs(n.local_x - px), abs(n.local_y - py)) <= 3]
            if not nearby:
                self.add_message("No one nearby to rob.", "advisory")
                return
            if len(nearby) == 1:
                victim = nearby[0]
            else:
                labels = [n.display_name() for n in nearby]
                idx = pick_from_list(self._console, self._ctx, "Rob whom?", labels)
                if idx is None:
                    return
                victim = nearby[idx]

            # Intimidation check: CHA + weapon bonus vs victim WIS + bravery
            import random as _rob_rng
            rng = _rob_rng.Random()
            player_roll = rng.randint(1, 20)
            cha = self.player.attributes.get("charisma", 10)
            # Weapon in hand bonus
            weapon_bonus = 0
            weapons = [i for i in self.player.inventory if i.is_weapon()]
            if weapons:
                best = max(weapons, key=lambda w: w.damage_max)
                weapon_bonus = best.damage_max // 3  # scary weapon = bigger bonus
                if best.weapon_type == "firearm":
                    weapon_bonus += 5  # guns are very persuasive
            player_roll += cha // 3 + weapon_bonus

            victim_wis = victim.attributes.get("wisdom", 10)
            victim_roll = rng.randint(1, 20) + victim_wis // 3
            # Brave/hot-tempered resist, cowardly/nervous fold
            v_traits = set(getattr(victim, 'traits', []))
            if v_traits & {"brave", "hot-tempered", "utterly fearless", "stubborn"}:
                victim_roll += 5
            if v_traits & {"nervous", "cowardly", "mild"}:
                victim_roll -= 5
            # Law enforcement fights back
            is_law = victim.occupation in ("Sheriff", "Marshal", "Deputy", "Ranger")
            if is_law:
                victim_roll += 8

            if player_roll >= victim_roll + 5:
                # Total surrender — hand over everything
                loot_msgs = []
                # Cash
                cash = rng.uniform(1.0, 20.0)
                self.player.cash += cash
                loot_msgs.append(f"${cash:.2f} cash")
                # Their inventory items
                npc_inv = getattr(victim, 'inventory', [])
                for item in list(npc_inv):
                    self.player.inventory.append(item)
                    loot_msgs.append(item.name)
                npc_inv.clear()
                victim.equipped_weapon = None
                victim._disarmed = True
                self.add_message(
                    f'*{victim.name} raises hands.* "Don\'t shoot! Take it all!"',
                    "normal")
                self.add_message(
                    f"You take: {', '.join(loot_msgs)}.", "advisory")
                victim.adjust_relationship(-30)
                victim.rel.adjust(fear=40, trust=-30)
            elif player_roll >= victim_roll:
                # Partial success — they hand over some cash but keep weapon
                cash = rng.uniform(0.5, 8.0)
                self.player.cash += cash
                self.add_message(
                    f'*{victim.name} slowly reaches into a pocket.* '
                    f'"Here... take it. Just go." (${cash:.2f})', "normal")
                victim.adjust_relationship(-20)
                victim.rel.adjust(fear=25, trust=-20)
            else:
                # Failed — they resist
                if is_law or v_traits & {"brave", "hot-tempered"}:
                    victim.combat_state = "hostile"
                    victim.go_hostile()
                    self.add_message(
                        f'{victim.name} goes for a weapon. '
                        f'"You picked the wrong man."', "critical")
                else:
                    victim.combat_state = "fleeing"
                    self.add_message(
                        f'{victim.name} bolts. They\'ll tell everyone.',
                        "advisory")

            # Crime: robbery
            current_day = self.time.total_minutes // 1440
            witnesses = self._witnesses_near(px, py, exclude_names={victim.name})
            region = lmap._region_name if lmap else ""
            self.legal.record_crime(
                "robbery", current_day,
                self.player.world_x, self.player.world_y, region,
                victim_name=victim.name,
                victim_npc_id=victim.npc_id,
                self_defense=False,
                nearby_npcs=witnesses,
            )
            self.reputation.adjust(region, -25)
            # Newspaper
            if hasattr(self, 'newspaper'):
                self.newspaper.record_event(
                    "crime", f"Highway robbery: {victim.name} robbed at gunpoint.",
                    self.player.world_x, self.player.world_y, current_day)
            # Gossip spreads
            self._record_gossip(f"Robbed {victim.name}", -0.6)
            # Witnesses react
            from src.combat import witness_reactions
            for msg in witness_reactions(witnesses, self.player.name,
                                         victim.name, False,
                                         current_day=current_day):
                self.add_message(msg, "advisory")
            # Memory
            if hasattr(victim, 'expanded_memory'):
                victim.expanded_memory.add(
                    content=f"{self.player.name} robbed me at gunpoint.",
                    day=current_day, significance=0.95, valence=-0.9,
                    category="witnessed_violence")
            self.advance_time(5)
            return

        # ── Process hide / pelt ───────────────────────────────────────────
        if "process" in a and ("hide" in a or "pelt" in a or "fur" in a or "skin" in a) or \
           "scrape" in a and ("hide" in a or "pelt" in a) or \
           "flesh" in a and ("hide" in a or "pelt" in a):
            # Check for fleshing beam nearby
            beam = self._nearby_structure("flesh_hide", radius=2)
            if not beam:
                self.add_message(
                    "You need a fleshing beam nearby. Build one first.", "advisory")
                return
            # Find raw pelts/hides in inventory
            from src.menus import pick_from_list
            from src.items import make_item
            raw_items = [i for i in self.player.inventory
                         if i.id.endswith("_pelt") or i.id == "raw_hide"
                         or "hide" in i.id or "robe" in i.id
                         or "skin" in i.id.lower()]
            if not raw_items:
                self.add_message("You have no raw pelts or hides to process.", "normal")
                return
            labels = [f"{i.name} ({i.id})" for i in raw_items]
            idx = pick_from_list(self._console, self._ctx,
                                 "Process which hide/pelt?", labels)
            if idx is None:
                return
            item = raw_items[idx]
            # Determine if this is a furbearer (pelt for trade) or big game (leather)
            FURBEARERS = {"beaver_pelt", "fox_pelt", "wolf_pelt", "coyote_pelt",
                          "raccoon_pelt", "bobcat_pelt", "otter_pelt", "mink_pelt",
                          "marten_pelt", "fisher_pelt", "wolverine_pelt", "lynx_pelt",
                          "muskrat_pelt", "skunk_pelt", "badger_pelt", "cougar_pelt"}
            LEATHER_HIDES = {"raw_hide", "deer_pelt", "elk_pelt", "buffalo_robe",
                             "bear_pelt"}

            is_furbearer = item.id in FURBEARERS
            is_leather_hide = item.id in LEATHER_HIDES or "hide" in item.id

            if is_furbearer:
                # Furbearers: always fur path, no leather option
                choice_labels = [
                    f"Scrape and preserve fur for trade",
                    "Cancel",
                ]
            elif is_leather_hide:
                # Big game: offer both options
                choice_labels = [
                    f"Keep the fur — stretch for trade",
                    f"Tan into leather — remove the fur",
                    "Cancel",
                ]
            else:
                # Unknown — offer both
                choice_labels = [
                    f"Keep the fur — stretch for trade",
                    f"Tan into leather — remove the fur",
                    "Cancel",
                ]

            cidx = pick_from_list(self._console, self._ctx,
                                  f"What do you want to do with {item.name}?",
                                  choice_labels)
            if cidx is None or choice_labels[cidx] == "Cancel":
                return

            want_fur = (is_furbearer or cidx == 0)

            # Leather path requires brain; fur path does not
            if not want_fur:
                has_brain = any(i.id == "brain" for i in self.player.inventory)
                if not has_brain:
                    self.add_message(
                        "You need a brain to tan leather. "
                        "Every animal has enough brain to tan its own hide.",
                        "advisory")
                    return
                # Consume brain
                for bi in self.player.inventory:
                    if bi.id == "brain":
                        if bi.stackable and bi.quantity > 1:
                            bi.quantity -= 1
                        else:
                            self.player.inventory.remove(bi)
                        break

            # Scrape time based on furriery skill
            skill = self.player.skills.get("furriery", 0)
            scrape_time = max(8, 20 - skill)

            # Remove the raw item
            if item.stackable and item.quantity > 1:
                item.quantity -= 1
            else:
                self.player.inventory.remove(item)

            if want_fur:
                # FUR PATH: scrape flesh, keep fur → scraped_pelt (needs frame next)
                scraped = make_item("scraped_pelt")
                scraped.name = f"Scraped {item.name}"
                scraped.extra = {"original_id": item.id, "original_name": item.name}
                scraped.base_value = item.base_value * 1.2
                self.player.inventory.append(scraped)
                self.add_message(
                    f"You work the {item.name} on the beam with brain, keeping "
                    f"the fur intact. Now stretch it on a frame to dry.", "normal")
                self.player.gain_skill_xp("furriery", 2.0)
            else:
                # LEATHER PATH: scrape + de-fur + brain
                brained = make_item("brained_hide")
                brained.name = f"Brained {item.name} Hide"
                brained.extra = {"original_id": item.id, "original_name": item.name}
                brained.base_value = item.base_value * 0.8
                self.player.inventory.append(brained)
                self.add_message(
                    f"You scrape the fur from the {item.name} and work brain "
                    f"into the skin. Now stretch it on a frame to dry.", "normal")
                self.player.gain_skill_xp("furriery", 3.0)
                scrape_time += 10
            self.advance_time(scrape_time)
            return

        # ── Stretch pelt/hide on frame ───────────────────────────────────
        if "stretch" in a and ("pelt" in a or "hide" in a or "leather" in a):
            frame = self._nearby_structure("stretch_hide", radius=2)
            if not frame:
                self.add_message(
                    "You need a stretching board nearby. Build one first.", "advisory")
                return
            from src.menus import pick_from_list
            from src.items import make_item
            stretchable = [i for i in self.player.inventory
                           if i.id in ("scraped_pelt", "scraped_hide", "brained_hide")]
            if not stretchable:
                self.add_message(
                    "You have nothing ready to stretch. Process a raw pelt first.", "normal")
                return
            labels = [i.name for i in stretchable]
            idx = pick_from_list(self._console, self._ctx,
                                 "Stretch which item?", labels)
            if idx is None:
                return
            item = stretchable[idx]
            self.player.inventory.remove(item)
            # Place on frame — will be converted by daily tick
            if not hasattr(frame, '_drying'):
                frame._drying = []
            frame._drying.append({
                "item_id": item.id,
                "original_id": getattr(item, 'extra', {}).get("original_id", item.id),
                "original_name": getattr(item, 'extra', {}).get("original_name", item.name),
                "base_value": item.base_value,
                "day_placed": self.time.total_minutes // 1440,
                "type": "fur" if item.id == "scraped_pelt" else "leather",
            })
            self.add_message(
                f"You lace the {item.name} onto the stretching board. "
                f"It'll need a day to dry.", "normal")
            self.advance_time(10)
            return

        # ── Read sign / Scout area ────────────────────────────────────────
        if "read sign" in a or "scout area" in a or a == "scout" or \
           ("track" in a and ("animal" in a or "game" in a or "sign" in a)):
            from src.scouting import scout_area
            result = scout_area(self.player, lmap, self.wildlife_mgr,
                                self.time, random.Random(),
                                npc_mgr=self.npc_mgr)
            for msg, sev in result.messages:
                self.add_message(msg, sev)
            for entry in result.journal_entries:
                self.journal.add_diary(self.time.date_string, entry)
            self.player.gain_skill_xp("tracking", 2.0)
            self.player.gain_skill_xp("survival", 1.0)
            self.advance_time(10)
            return

        # ── Forage / Gather ───────────────────────────────────────────────
        if "forage" in a or "gather" in a or ("pick" in a and ("berr" in a or "plant" in a or "herb" in a)):
            from src.foraging import forage_area
            results = forage_area(self.player, lmap, px, py,
                                   self.time.season, random.Random())
            if results:
                from src.items import make_item
                for item_id, msg, learned in results:
                    try:
                        item = make_item(item_id)
                        self.player.inventory.append(item)
                        self.add_message(msg, "normal")
                        if learned:
                            self.player.knowledge[item_id] = 1
                            self.add_message(
                                f"You'll remember what {item.name} looks like.",
                                "advisory")
                    except (ValueError, KeyError):
                        pass
                day = self.time.total_minutes // 1440
                self.player.survival.log_food(False, day)
                self.player.gain_skill_xp("survival", 1.0)
            else:
                self.add_message(
                    "You search but find nothing edible nearby.", "normal")
            self.advance_time(15)
            return

        # ── Furniture interaction ──────────────────────────────────────────
        from src.furniture import get_furniture_actions, execute_furniture_action
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                nx, ny = px + dx, py + dy
                if not lmap.in_bounds(nx, ny):
                    continue
                for fa in get_furniture_actions(lmap.tile_at(nx, ny).terrain):
                    if fa.label.lower() == a or fa.action_id in a:
                        msg = execute_furniture_action(fa.action_id, self, nx, ny)
                        if msg:
                            self.add_message(msg, "normal")
                        return

        # ── Investigate / Look around ─────────────────────────────────────
        if "investigate" in a or "look around" in a or "search area" in a or \
           "examine ground" in a or "check tracks" in a:
            self._investigate_nearby()
            return

        # ── Place portable structure from inventory ─────────────────────────
        if ("place" in a or "set up" in a) and \
                ("frame" in a or "beam" in a or "rack" in a or "rail" in a or "structure" in a):
            portable = [i for i in self.player.inventory
                        if "portable_structure" in getattr(i, 'tool_tags', [])]
            if not portable:
                self.add_message("You don't have any portable structures to place.", "advisory")
                return
            from src.menus import pick_from_list
            labels = [i.name for i in portable]
            idx = pick_from_list(self._console, self._ctx, "Place which structure?", labels)
            if idx is None:
                return
            item = portable[idx]
            struct_key = item.extra.get("structure_key", "") if item.extra else ""
            if struct_key:
                # Pass empty list — item is pre-built, don't consume materials
                _dummy = []
                result = self.construction.start_equipment(
                    struct_key, lmap,
                    self.player.local_x + 1, self.player.local_y,
                    _dummy)
                if result[0]:
                    result[0].progress = 100.0
                    self.player.inventory.remove(item)
                    self.add_message(f"You set up the {item.name}.", "normal")
                    self.advance_time(5)
                elif "Need" in (result[1] or ""):
                    # Material check failed on empty list — bypass it
                    # Manually place the structure without material consumption
                    from src.construction import PlacedEquipment, EQUIPMENT_BLUEPRINTS
                    bp = EQUIPMENT_BLUEPRINTS.get(struct_key)
                    if bp:
                        px_p = self.player.local_x + 1
                        py_p = self.player.local_y
                        sid = lmap._next_id
                        lmap._next_id += 1
                        equip = PlacedEquipment(
                            id=sid, blueprint_key=struct_key, name=bp.name,
                            x=px_p, y=py_p, width=bp.width, height=bp.height,
                            condition=100.0, progress=100.0,
                            functional_tags=list(bp.functional_tags),
                        )
                        lmap.structures[sid] = equip
                        self.player.inventory.remove(item)
                        self.add_message(f"You set up the {item.name}.", "normal")
                        self.advance_time(5)
                    else:
                        self.add_message("Can't place that here.", "advisory")
                else:
                    self.add_message("Can't place that here.", "advisory")
            return

        # ── Continue building incomplete structure ──────────────────────
        if "continue building" in a and lmap:
            from src.construction import PlacedEquipment
            px, py = self.player.local_x, self.player.local_y
            for sid, s in lmap.structures.items():
                if not isinstance(s, PlacedEquipment):
                    continue
                if s.complete:
                    continue
                if max(abs(s.x - px), abs(s.y - py)) > 2:
                    continue
                skill = self.player.skills.get("engineering", 0)
                msg = self.construction.work_on_equipment(
                    s, 30, skill_level=skill, local_map=lmap)
                self.add_message(msg, "normal")
                if s.complete:
                    self.add_message(
                        f"The {s.name} is finished!", "normal")
                else:
                    self.add_message(
                        f"{s.name}: {int(s.progress)}% complete.", "advisory")
                self.player.gain_skill_xp("engineering", 2.0)
                self.advance_time(30)
                return

        # ── Pick up portable structure ─────────────────────────────────────
        if "pick up" in a and lmap:
            from src.construction import PlacedEquipment, EQUIPMENT_BLUEPRINTS
            from src.items import make_item
            px, py = self.player.local_x, self.player.local_y
            for sid, s in list(lmap.structures.items()):
                if not isinstance(s, PlacedEquipment):
                    continue
                if max(abs(s.x - px), abs(s.y - py)) > 2:
                    continue
                bp = EQUIPMENT_BLUEPRINTS.get(s.blueprint_key)
                if not bp or not bp.portable or not s.complete:
                    continue
                if s.name.lower() not in a:
                    continue
                # Don't allow pickup if items drying on it
                if hasattr(s, '_drying') and s._drying:
                    self.add_message(
                        f"There's something drying on the {s.name}. "
                        f"Remove it first.", "advisory")
                    return
                # Remove structure, give item
                del lmap.structures[sid]
                try:
                    item = make_item(s.blueprint_key)
                    self.player.inventory.append(item)
                    self.add_message(
                        f"You take down the {s.name} and pack it up.", "normal")
                except (ValueError, KeyError):
                    # No matching item — give back materials instead
                    for mat_name, qty in bp.materials:
                        for _ in range(qty):
                            try:
                                self.player.inventory.append(make_item(
                                    mat_name.lower().replace(" ", "_")))
                            except (ValueError, KeyError):
                                pass
                    self.add_message(
                        f"You dismantle the {s.name}.", "normal")
                self.advance_time(5)
                return

        # ── Work on construction orders ────────────────────────────────────
        if ("work" in a and ("build" in a or "construct" in a)) or \
           "construction" in a or "build wall" in a or "build floor" in a:
            if lmap and lmap.build_queue:
                order = lmap.build_queue.next_order()
                if order:
                    skill = self.player.skills.get("engineering", 0)
                    wg = getattr(lmap, 'wall_grid', None)
                    fo = getattr(lmap, 'floor_overlay', None)
                    if wg is None:
                        from src.construction import WallGrid
                        lmap.wall_grid = WallGrid()
                        wg = lmap.wall_grid
                    if fo is None:
                        from src.construction import FloorOverlay
                        lmap.floor_overlay = FloorOverlay()
                        fo = lmap.floor_overlay
                    done, msg = self.construction.work_on_order(
                        order, 30, skill, wg, fo, self.player.inventory,
                        local_map=lmap)
                    self.add_message(msg, "advisory" if done else "normal")
                    self.player.gain_skill_xp("engineering", 2.0)
                    self.advance_time(30)
                else:
                    self.add_message("No pending construction orders.", "normal")
            else:
                self.add_message("No construction orders queued. Press [B] to plan.", "advisory")
            return

        # ── Saloon Entertainment ──────────────────────────────────────────
        if ("arm wrestl" in a or "drinking contest" in a or
                "tell a story" in a or "storytell" in a or "saloon" in a):
            from src.local_map import LocalTerrain as _SLT
            tile = lmap.tile_at(self.player.local_x, self.player.local_y)
            nearby_bar = tile.terrain == _SLT.BAR_COUNTER or any(
                lmap.in_bounds(self.player.local_x + ddx, self.player.local_y + ddy) and
                lmap.tile_at(self.player.local_x + ddx,
                             self.player.local_y + ddy).terrain == _SLT.BAR_COUNTER
                for ddx in range(-2, 3) for ddy in range(-2, 3)
            )
            if not nearby_bar:
                self.add_message("You need to be at a saloon for that.", "advisory")
                return
            from src.saloon_mode import saloon_menu
            msgs = saloon_menu(self, self._console, self._ctx)
            for msg in msgs:
                self.add_message(msg, "normal")
            return

        # ── Bounty Board ─────────────────────────────────────────────────
        if "bounty" in a or "wanted" in a:
            from src.menus import pick_from_list
            active = self.bounty_board.get_active()
            accepted = self.bounty_board.get_accepted()
            if not active and not accepted:
                self.add_message("No bounties posted right now.", "normal")
                return
            labels = []
            for b in active:
                labels.append(f"[${b.reward:.0f}] {b.target_name} — {b.crime}")
            for b in accepted:
                labels.append(f"[TRACKING] {b.target_name} — {b.crime}")
            idx = pick_from_list(self._console, self._ctx, "Bounty Board", labels)
            if idx is not None:
                if idx < len(active):
                    self.bounty_board.accept_bounty(active[idx].bounty_id)
                    self.add_message(
                        f"Accepted bounty on {active[idx].target_name}. "
                        f"Reward: ${active[idx].reward:.0f}.", "advisory")
                else:
                    b = accepted[idx - len(active)]
                    hint = self.bounty_board.get_tracking_hint(
                        b, self.player.world_x, self.player.world_y,
                        random.Random())
                    if hint:
                        self.add_message(hint, "advisory")
                    else:
                        self.add_message("The trail has gone cold. No leads.", "advisory")
            return

        # ── Propose / Wedding ────────────────────────────────────────────
        if "propose" in a or "marry" in a or "wedding" in a:
            from src.marriage import can_propose, propose, can_wed, conduct_wedding
            # Find nearby NPC the player is romancing
            target = None
            for n in self._tile_npcs():
                if not n.alive or not n.present:
                    continue
                dist = max(abs(n.local_x - self.player.local_x),
                           abs(n.local_y - self.player.local_y))
                if dist > 2:
                    continue
                if hasattr(n, 'rel') and n.rel.status in (
                        "close_friend", "courting", "engaged"):
                    target = n
                    break
            if not target:
                self.add_message("No one nearby to propose to.", "advisory")
                return
            current_day = self.time.total_minutes // 1440
            if target.rel.status == "engaged":
                # Try to conduct wedding
                ok, reason = can_wed(self.player, target, list(self._tile_npcs()))
                if not ok:
                    self.add_message(reason, "advisory")
                    return
                preacher = None
                for n in self._tile_npcs():
                    if n.occupation in ("Preacher", "Minister", "Priest",
                                        "Justice of the Peace"):
                        preacher = n
                        break
                town_name = ""
                loc = self.world.get_location_at(
                    self.player.world_x, self.player.world_y)
                if loc:
                    town_name = loc.name
                state = conduct_wedding(
                    self.player, target, preacher, current_day, town_name)
                self.marriage_state = state
                self.add_message(
                    f"You and {target.name} are married! "
                    f"Congratulations.", "advisory")
                self.advance_time(60)
            else:
                # Try to propose
                ok, reason = can_propose(self.player, target)
                if not ok:
                    self.add_message(reason, "advisory")
                    return
                accepted, msg = propose(self.player, target, current_day)
                self.add_message(msg, "advisory" if accepted else "normal")
                self.advance_time(10)
            return

        # ── Buy Property ─────────────────────────────────────────────────
        if "buy lot" in a or "buy property" in a or "buy land" in a:
            loc = self.world.get_location_at(
                self.player.world_x, self.player.world_y)
            if not loc:
                self.add_message("You can only buy lots in a town.", "advisory")
                return
            from src.property import LOT_PRICES
            stype = "small_town"
            if lmap and hasattr(lmap, 'town_layout') and lmap.town_layout:
                stype = lmap.town_layout.settlement_type
            price = LOT_PRICES.get(stype, 50)
            ok, msg = self.property_mgr.buy_lot(
                loc.name, self.player.local_x, self.player.local_y,
                8, 8,  # default lot size
                self.player.world_x, self.player.world_y,
                price, self.player)
            self.add_message(msg, "advisory" if ok else "normal")
            return

        # ── Store/Retrieve items at owned property ───────────────────────
        if "store" in a and ("item" in a or "gear" in a or "supplies" in a):
            props = self.property_mgr.get_at(
                self.player.world_x, self.player.world_y)
            built = [p for p in props if p.built]
            if not built:
                self.add_message("You don't own a built property here.", "advisory")
                return
            from src.menus import pick_from_list
            items = [(i, i.name) for i in self.player.inventory]
            if not items:
                self.add_message("Nothing in your inventory to store.", "normal")
                return
            labels = [name for _, name in items]
            idx = pick_from_list(self._console, self._ctx, "Store which item?", labels)
            if idx is not None:
                item = self.player.inventory.pop(idx)
                self.property_mgr.store_item(built[0].lot_id, item)
                self.add_message(f"Stored {item.name} at your property.", "normal")
            return

        # ── Cache / Bury supplies ────────────────────────────────────────
        if "cache" in a or "bury" in a and ("supplies" in a or "items" in a or "stash" in a):
            from src.menus import pick_from_list
            if not self.player.inventory:
                self.add_message("Nothing to cache.", "normal")
                return
            labels = [f"{i.name} (${i.base_value:.2f})" for i in self.player.inventory]
            idx = pick_from_list(self._console, self._ctx, "Cache which item?", labels)
            if idx is not None:
                item = self.player.inventory.pop(idx)
                # Bury at current tile as hidden ground item
                tile = lmap.tile_at(px, py)
                if not hasattr(tile, '_cached_items'):
                    tile._cached_items = []
                tile._cached_items.append(item)
                lmap.mark_dirty(px, py)
                self.journal.add_place(
                    f"Cache ({item.name})", self.player.world_x, self.player.world_y,
                    f"Buried {item.name} at ({px},{py})")
                self.add_message(
                    f"You dig a hole and bury the {item.name}. "
                    f"Location marked in journal.", "normal")
                self.advance_time(10)
            return

        if "dig up" in a or "retrieve cache" in a or "unbury" in a:
            tile = lmap.tile_at(px, py)
            cached = getattr(tile, '_cached_items', [])
            if not cached:
                self.add_message("No cache buried here.", "normal")
                return
            from src.menus import pick_from_list
            labels = [f"{i.name} (${i.base_value:.2f})" for i in cached]
            idx = pick_from_list(self._console, self._ctx, "Retrieve which item?", labels)
            if idx is not None:
                item = cached.pop(idx)
                self.player.inventory.append(item)
                lmap.mark_dirty(px, py)
                self.add_message(f"You dig up the {item.name}.", "normal")
                self.advance_time(10)
            return

        # ── Mount / Dismount ──────────────────────────────────────────────
        if "dismount" in a or "get off" in a:
            if self.player.mounted:
                self.player.mounted = False
                self.player.mount_animal_id = None
                self.add_message("You dismount.", "normal")
                self.advance_time(1)
            else:
                self.add_message("You aren't mounted.", "normal")
            return

        if "mount" in a or "ride" in a or "get on horse" in a:
            if self.player.mounted:
                self.add_message("You're already mounted.", "normal")
                return
            rideables = [an for an in self.animal_mgr.animals
                         if an.alive and an.species.rideable]
            if not rideables:
                self.add_message("You don't have a rideable animal.", "advisory")
                return
            if len(rideables) == 1:
                mount = rideables[0]
            else:
                from src.menus import pick_from_list
                names = [f"{an.name} ({an.species.name})" for an in rideables]
                idx = pick_from_list(self._console, self._ctx, "Mount which animal?", names)
                if idx is None:
                    return
                mount = rideables[idx]
            self.player.mounted = True
            self.player.mount_animal_id = mount.animal_id
            self.add_message(f"You mount {mount.name}.", "normal")
            self.advance_time(2)
            return

        # ── Set trap ──────────────────────────────────────────────────────
        if "set trap" in a or "set snare" in a or "place trap" in a or \
           "set deadfall" in a or "set steel" in a or "set bear" in a:
            from src.menus import pick_from_list, pick_direction_menu
            from src.trapping import TrapManager, TRAP_SPECIES
            # Find traps in inventory
            trap_items = [i for i in self.player.inventory
                          if "trap" in getattr(i, "tool_tags", [])]
            if not trap_items:
                self.add_message("You don't have any traps.", "advisory")
                return
            labels = [f"{t.name} ({t.weight:.0f}lb)" for t in trap_items]
            tidx = pick_from_list(self._console, self._ctx, "Set which trap?", labels)
            if tidx is None:
                return
            trap_item = trap_items[tidx]
            # Pick direction
            direction = pick_direction_menu(self._console, self._ctx,
                "Place trap in which direction?")
            if direction is None:
                return
            dx, dy = direction
            tx, ty = self.player.local_x + dx, self.player.local_y + dy
            if not lmap.in_bounds(tx, ty) or not lmap.is_passable(tx, ty):
                self.add_message("Can't place a trap there.", "advisory")
                return
            # Optional bait
            bait_items = [i for i in self.player.inventory
                          if i.is_food() or i.id == "castoreum"]
            bait = ""
            if bait_items:
                bait_labels = ["No bait"] + [i.name for i in bait_items]
                bidx = pick_from_list(self._console, self._ctx, "Add bait?", bait_labels)
                if bidx and bidx > 0:
                    bait_item = bait_items[bidx - 1]
                    bait = bait_item.name
                    if bait_item.stackable and bait_item.quantity > 1:
                        bait_item.quantity -= 1
                    else:
                        self.player.inventory.remove(bait_item)
            # Trapping skill check for set quality
            import random as _trap_rng
            skill = self.player.skills.get("trapping", 0)
            set_quality = min(10, skill + _trap_rng.randint(-2, 2))
            # Place the trap
            self.player.inventory.remove(trap_item)
            self.trap_mgr.place_trap(
                trap_item.id, tx, ty,
                self.player.world_x, self.player.world_y,
                self.player.area_x, self.player.area_y,
                bait, max(0, set_quality), self.time.total_seconds)
            bait_msg = f" Baited with {bait}." if bait else ""
            self.add_message(
                f"You carefully set the {trap_item.name}.{bait_msg} "
                f"Check back in 8+ hours.", "normal")
            self.advance_time(15)
            self.player.gain_skill_xp("trapping", 3.0)
            return

        # ── Check traps ──────────────────────────────────────────────────
        if "check trap" in a or "check snare" in a:
            from src.trapping import SPECIES_PELT, calculate_pelt_quality, grade_name
            from src.menus import pick_from_list
            nearby = self.trap_mgr.traps_at(
                self.player.world_x, self.player.world_y,
                self.player.area_x, self.player.area_y)
            if not nearby:
                self.add_message("No traps set in this area.", "advisory")
                return
            labels = []
            for t in nearby:
                if t.caught_species:
                    labels.append(f"Trap #{t.id}: CAUGHT {t.caught_species}!")
                elif t.sprung:
                    labels.append(f"Trap #{t.id}: sprung empty")
                else:
                    labels.append(f"Trap #{t.id}: set ({t.trap_type})")
            tidx = pick_from_list(self._console, self._ctx, "Check which trap?", labels)
            if tidx is None:
                return
            trap = nearby[tidx]
            if trap.caught_species:
                hours_in = (self.time.total_seconds - trap.caught_time) / 3600
                self.add_message(
                    f"Your {trap.trap_type} caught a {trap.caught_species}! "
                    f"In trap for {hours_in:.0f} hours.", "normal")
                # Skin it
                import random as _sk_rng
                has_sk = any("skin" in getattr(i, "tool_tags", [])
                             for i in self.player.inventory)
                quality = calculate_pelt_quality(
                    self.time.season, hours_in,
                    self.player.skills.get("trapping", 0),
                    "trap_kill", has_sk, _sk_rng.Random())
                gname = grade_name(quality)
                pelt_id = SPECIES_PELT.get(trap.caught_species, "")
                if pelt_id:
                    from src.items import make_item
                    from src.trapping import grade_multiplier
                    pelt = make_item(pelt_id)
                    pelt.name = f"{gname} {pelt.name}"
                    pelt.base_value *= grade_multiplier(quality)
                    self.player.inventory.append(pelt)
                    # Quality feedback — tell player what affected the grade
                    factors = []
                    if hours_in > 24:
                        factors.append(f"sat {hours_in:.0f}hrs (too long)")
                    elif hours_in < 4:
                        factors.append("fresh catch")
                    if self.time.season == "winter":
                        factors.append("winter coat (premium)")
                    elif self.time.season == "summer":
                        factors.append("thin summer fur")
                    if has_sk:
                        factors.append("skinning knife (clean cut)")
                    if self.player.skills.get("trapping", 0) >= 5:
                        factors.append("expert handling")
                    factor_str = ", ".join(factors) if factors else "standard"
                    self.add_message(
                        f"You skin it: {pelt.name} (${pelt.base_value:.2f}) "
                        f"[{factor_str}]",
                        "normal")
                    self.player.gain_skill_xp("trapping", 5.0)
                    self.player.gain_skill_xp("furriery", 2.0)
                # Reset trap
                trap.caught_species = ""
                trap.caught_time = 0
                trap.sprung = False
                self.advance_time(15)
            elif trap.sprung:
                self.add_message("Trap sprung but empty. Resetting.", "normal")
                trap.sprung = False
                self.advance_time(5)
            else:
                self.add_message("Trap is still set. Nothing yet.", "normal")
            return

        # ── Crafting ──────────────────────────────────────────────────────
        # Quick-craft from recent action (e.g. "Craft Plank")
        if a.startswith("craft ") and len(a) > 6:
            recipe_name = action[6:]  # preserve original case
            self._open_crafting(quick_recipe_name=recipe_name)
            return
        _CRAFT_VERBS = ("craft", "make", "brew", "smoke", "tan", "stretch",
                        "leach", "roast", "boil", "dry", "cure", "preserve",
                        "build", "sew", "knit", "weave", "carve")
        _CRAFT_NOUNS = ("knife", "arrow", "bow", "leather", "pouch", "plank",
                        "torch", "candle", "snare", "club", "bowl", "moccasin",
                        "tea", "jerky", "pemmican", "meat", "hide", "pelt",
                        "rope", "bandage", "poultice", "frame", "trap",
                        "acorn", "camas", "bitterroot", "charcoal")
        if any(v in a for v in _CRAFT_VERBS) and any(n in a for n in _CRAFT_NOUNS):
            self._open_crafting()
            return
        if a in ("craft", "crafting", "recipes", "make something"):
            self._open_crafting()
            return

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
        # ── Join battle ────────────────────────────────────────────────
        if "join battle" in a or "serve as medic" in a or "observe battle" in a:
            bs = getattr(self, '_active_battle', None)
            if not bs or bs.resolved:
                self.add_message("No active battle nearby.", "advisory")
                return

            battle = bs.battle
            if "medic" in a:
                bs.player_role = "medic"
                bs.player_side = 0  # medics serve their own side
                if hasattr(self, 'war_system') and self.war_system.player_faction:
                    for i, f in enumerate(battle.factions):
                        if f == self.war_system.player_faction:
                            bs.player_side = i
                self.add_message(
                    "You grab your medical kit and head toward the wounded.",
                    "normal")
            elif "observe" in a:
                bs.player_role = "observer"
                bs.player_side = -1
                self.add_message(
                    "You find a ridge overlooking the field and watch.",
                    "normal")
            else:
                # Joining a side
                for i, faction in enumerate(battle.factions):
                    if faction.lower() in a:
                        bs.player_side = i
                        break
                else:
                    bs.player_side = 0
                bs.player_role = "fighter"
                faction_name = battle.factions[bs.player_side]
                self.add_message(
                    f"You join the {faction_name} line. "
                    f"Fix bayonets. Here they come.", "critical")

            # Spawn battle NPCs
            lmap = self.current_local
            if lmap and hasattr(self, 'war_system'):
                import random as _brng
                rng = _brng.Random(battle.battle_id.__hash__())
                per_side = min(15, max(8, battle.strength[0] // (battle.patches * 10)))
                for side in range(2):
                    spawned = self.war_system.spawn_battle_npcs(
                        battle, side, per_side,
                        lmap, self.player.area_x, self.player.area_y,
                        self._npc_gen, rng)
                    # Register in npc_mgr so _tile_npcs() finds them
                    for npc in spawned:
                        self.npc_mgr.npcs[npc.npc_id] = npc

            # Enter battle loop
            self._run_battle_mode(bs)
            return

        # ── Work at your business ─────────────────────────────────────
        if "work at" in a and hasattr(self, 'business_mgr'):
            import random as _biz_rng
            for biz in self.business_mgr.businesses.values():
                if not biz.active:
                    continue
                if biz.world_x != self.player.world_x or \
                        biz.world_y != self.player.world_y:
                    continue
                if biz.name.lower() not in a:
                    continue

                # Player works the business directly
                from src.business import BUSINESS_BLUEPRINTS
                bp = BUSINESS_BLUEPRINTS.get(biz.blueprint_key)
                skill_name = biz.skill_used or "trading"
                skill = self.player.skills.get(skill_name, 0)

                # Work shift: 4 hours
                shift_hours = 4
                self.advance_time(shift_hours * 60)

                # Revenue from player working (better than employees)
                # Player skill directly multiplies output
                player_mult = 1.0 + skill * 0.15  # skill 5 = 1.75x
                base_rev = biz.base_revenue * (shift_hours / 24.0)
                earned = base_rev * player_mult * 2.0  # 2x vs employee rate

                # Production chain — player does the work
                if bp and bp.consumes and bp.produces:
                    can_produce = True
                    for item_id, qty in bp.consumes:
                        available = sum(1 for i in biz.inventory
                                        if i.id == item_id)
                        if available < qty:
                            can_produce = False
                            break
                    if can_produce:
                        from src.items import make_item
                        for item_id, qty in bp.consumes:
                            consumed = 0
                            for item in list(biz.inventory):
                                if item.id == item_id and consumed < qty:
                                    biz.inventory.remove(item)
                                    consumed += 1
                        produced_names = []
                        for item_id, qty in bp.produces:
                            # Player skill bonus on output
                            bonus_qty = int(qty * player_mult)
                            for _ in range(bonus_qty):
                                try:
                                    biz.inventory.append(make_item(item_id))
                                except Exception:
                                    pass
                            produced_names.append(f"{bonus_qty}x {item_id}")
                        self.add_message(
                            f"You work the {biz.name} for {shift_hours} hours. "
                            f"Produced: {', '.join(produced_names)}.", "normal")
                    else:
                        self.add_message(
                            f"You work at the {biz.name} but you're short on "
                            f"materials.", "advisory")
                        earned *= 0.3  # can still do service work without materials
                else:
                    # Service business — no production, just revenue
                    self.add_message(
                        f"You work the {biz.name} for {shift_hours} hours. "
                        f"Earned ${earned:.2f} in revenue.", "normal")

                biz.cash_reserve += earned
                biz.total_revenue += earned
                self.player.gain_skill_xp(skill_name, 3.0)
                self.player.survival.fatigue = max(
                    0, self.player.survival.fatigue - 15)

                # Working your own business builds reputation faster
                biz.reputation = min(100, biz.reputation + 0.5)
                return

        # ── Captivity actions ─────────────────────────────────────────
        if "escape" in a and hasattr(self, 'tribal'):
            import random as _esc_rng
            for tribe_name in self.tribal.standings:
                ts = self.tribal.get_standing(tribe_name)
                if ts.captive:
                    success, msg = self.tribal.attempt_escape(
                        tribe_name,
                        self.player.skills.get("tracking", 0),
                        self.player.attributes.get("agility", 10),
                        _esc_rng.Random())
                    self.add_message(msg, "normal" if success else "critical")
                    if not success and ts.escape_attempts >= 3:
                        self.player.survival.health = max(
                            0, self.player.survival.health - 15)
                    self.advance_time(60)  # takes an hour to attempt
                    return

        if "accept adoption" in a and hasattr(self, 'tribal'):
            for tribe_name in self.tribal.standings:
                ts = self.tribal.get_standing(tribe_name)
                if ts.captive:
                    msg = self.tribal.accept_adoption(
                        tribe_name, self.time.total_minutes // 1440)
                    self.add_message(msg, "normal")
                    return

        if "refuse adoption" in a and hasattr(self, 'tribal'):
            for tribe_name in self.tribal.standings:
                ts = self.tribal.get_standing(tribe_name)
                if ts.captive:
                    msg = self.tribal.refuse_adoption(tribe_name)
                    self.add_message(msg, "normal")
                    return

        # ── Canoe actions ─────────────────────────────────────────────
        if "launch" in a and "canoe" in a:
            canoes = [i for i in self.player.inventory
                      if "water_vehicle" in getattr(i, "tool_tags", [])]
            if not canoes:
                self.add_message("You don't have a canoe.", "advisory")
                return
            if not _near_water():
                self.add_message("No water nearby to launch.", "advisory")
                return
            canoe = canoes[0]
            self.player.inventory.remove(canoe)
            self._deployed_canoe = {
                "item_id": canoe.id,
                "vehicle_type": canoe.extra.get("vehicle_type", "birchbark_canoe"),
                "x": self.player.local_x,
                "y": self.player.local_y,
            }
            self.add_message(
                f"You set the {canoe.name} in the water. Ready to board.", "normal")
            self.advance_time(5)
            return

        if "board" in a and "canoe" in a:
            if not getattr(self, '_deployed_canoe', None):
                self.add_message("No canoe deployed nearby.", "advisory")
                return
            self.player._in_canoe = True
            self.player._canoe_type = self._deployed_canoe["vehicle_type"]
            self.add_message(
                "You board the canoe. Open the map [M] and select a "
                "river destination to travel by water.", "normal")
            return

        if ("disembark" in a or "get out" in a or "leave canoe" in a or
                "exit canoe" in a or "beach" in a):
            if getattr(self.player, '_in_canoe', False):
                self.player._in_canoe = False
                self.player._canoe_type = ""
                self.add_message(
                    "You step out of the canoe and pull it ashore.", "normal")
                self.advance_time(3)
                return
            if getattr(self, '_deployed_canoe', None):
                # Pick up deployed canoe back into inventory
                from src.items import make_item
                canoe_id = self._deployed_canoe["item_id"]
                try:
                    item = make_item(canoe_id)
                    self.player.inventory.append(item)
                    self.add_message(
                        f"You pull the {item.name} out of the water.", "normal")
                except (ValueError, KeyError):
                    self.add_message("You pull the canoe ashore.", "normal")
                self._deployed_canoe = None
                self.advance_time(5)
                return
            self.add_message("You're not in a canoe.", "advisory")
            return

        if "portage" in a and ("canoe" in a or "carry" in a):
            deployed = getattr(self, '_deployed_canoe', None)
            if not deployed:
                self.add_message("No canoe to portage.", "advisory")
                return
            from src.items import make_item
            from src.vehicles import VEHICLE_TYPES
            canoe_id = deployed["item_id"]
            vtype = VEHICLE_TYPES.get(deployed["vehicle_type"])
            if vtype and not vtype.portable:
                self.add_message(
                    f"The {vtype.name} is too heavy to carry overland.", "advisory")
                return
            try:
                item = make_item(canoe_id)
                self.player.inventory.append(item)
                self._deployed_canoe = None
                self.player._in_canoe = False
                weight = vtype.portage_weight if vtype else 60
                self.add_message(
                    f"You hoist the canoe onto your shoulders ({weight:.0f} lbs). "
                    f"Carry it overland to the next waterway.", "normal")
            except (ValueError, KeyError):
                self.add_message("You pick up the canoe.", "normal")
                self._deployed_canoe = None
            self.advance_time(10)
            return

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
                # Check if water is stagnant (few adjacent water tiles = puddle)
                from src.local_map import LocalTerrain as _WLT
                water_adj = 0
                for dy2 in range(-2, 3):
                    for dx2 in range(-2, 3):
                        wx2 = self.player.local_x + dx2
                        wy2 = self.player.local_y + dy2
                        if lmap.in_bounds(wx2, wy2) and \
                                lmap.tile_at(wx2, wy2).terrain == _WLT.WATER:
                            water_adj += 1
                if water_adj <= 3:
                    # Stagnant water — risk of gut sickness
                    import random as _wrng
                    con = self.player.attributes.get("constitution", 10)
                    risk = max(0.05, 0.25 - con * 0.015)
                    if _wrng.random() < risk:
                        self.player.survival.contract_gut_sickness()
                        self.add_message(
                            "You fill your canteen from a still pool. "
                            "The water tastes off. Your stomach churns.",
                            "warning")
                    else:
                        self.add_message(
                            "You fill your canteen from a still pool. "
                            "Looks clear enough.", "normal")
                else:
                    self.add_message(
                        "You kneel by the flowing stream and fill your canteen. "
                        "Cold, clean water.", "normal")
                self.advance_time(5)
            else:
                self.add_message("There's no water nearby to fill from.", "advisory")
                self.advance_time(2)
            return

        # ── Inspect wounds ────────────────────────────────────────────────
        if "inspect" in a and ("wound" in a or "injur" in a or "health" in a):
            wounds = self.player.wounds.wounds
            if not wounds:
                self.add_message("No active wounds.", "normal")
            else:
                for w in wounds:
                    from src.health_system import PART_DATA
                    part_label = PART_DATA.get(w.part, {}).get("label", w.part)
                    status = []
                    if w.is_bleeding:
                        status.append(f"bleeding ({w.bleed_level})")
                    if w.infected:
                        status.append("INFECTED")
                    if w.bone_broken:
                        status.append("broken bone")
                    if w.lodged:
                        status.append(f"{w.lodged} lodged")
                    status_str = ", ".join(status) if status else "stable"
                    self.add_message(
                        f"  {part_label}: {w.description} [{status_str}]",
                        "advisory")
                # Show gut sickness / mercury
                if self.player.survival.is_gut_sick:
                    hrs = self.player.survival.gut_sick_hours
                    self.add_message(
                        f"  Gut sickness: {hrs:.0f} hours remaining. "
                        f"Treat with medicine or wait it out.",
                        "advisory")
                if self.player.survival.mercury_exposure >= 20:
                    self.add_message(
                        f"  Mercury: {self.player.survival.mercury_symptoms}",
                        "warning")
            self.advance_time(5)
            return

        # ── Clean fish ────────────────────────────────────────────────────
        if "clean" in a and "fish" in a:
            fish_items = [i for i in self.player.inventory if i.id == "fresh_fish"]
            if not fish_items:
                self.add_message("No fresh fish to clean.", "normal")
                return
            has_knife = any(any(t in getattr(i, "tool_tags", [])
                               for t in ("cut", "butcher"))
                           for i in self.player.inventory)
            if not has_knife:
                self.add_message("You need a knife to clean fish.", "advisory")
                return
            fish = fish_items[0]
            fish_name = fish.name
            self.player.inventory.remove(fish)
            from src.items import make_item
            # Fillets
            for _ in range(2):
                fillet = make_item("fish_fillet")
                fillet.name = fish_name.replace("Fresh ", "") + " Fillet"
                self.player.inventory.append(fillet)
            # Guts (bait)
            guts = make_item("fish_guts")
            self.player.inventory.append(guts)
            self.add_message(
                f"You gut and fillet the {fish_name}. "
                f"2 fillets + fish guts (bait).", "normal")
            self.player.gain_skill_xp("survival", 1.0)
            self.advance_time(5)
            return

        # ── Clean wound ──────────────────────────────────────────────────
        if "clean" in a and "wound" in a:
            wounds = [w for w in self.player.wounds.wounds
                      if not getattr(w, '_cleaned', False)]
            if not wounds:
                self.add_message("No wounds need cleaning.", "normal")
                return
            # Need water nearby or canteen
            has_water = any(i.id == "canteen" and i.extra.get("filled")
                           for i in self.player.inventory)
            if not has_water and not _near_water():
                self.add_message("You need water to clean wounds. Fill your canteen.", "advisory")
                return
            w = wounds[0]
            w._cleaned = True
            # Cleaning reduces infection chance
            if hasattr(w, 'infection_chance'):
                w.infection_chance = max(0, w.infection_chance - 0.3)
            self.add_message(
                f"You clean the {w.description} on your {w.part} with water. "
                f"Infection risk reduced.", "normal")
            self.player.gain_skill_xp("firstAid", 2.0)
            self.advance_time(10)
            return

        # ── Treat gut sickness ───────────────────────────────────────────
        if ("treat" in a or "medicine" in a or "cure" in a) and \
                ("gut" in a or "sick" in a or "stomach" in a):
            if not self.player.survival.is_gut_sick:
                self.add_message("You're not sick.", "normal")
                return
            # Check for medicine items
            meds = [i for i in self.player.inventory
                    if any(t in getattr(i, 'tool_tags', [])
                           for t in ('medical', 'painkiller'))
                    or i.id in ('whiskey', 'willow_tea', 'laudanum')]
            if meds:
                med = meds[0]
                if med.stackable and med.quantity > 1:
                    med.quantity -= 1
                else:
                    self.player.inventory.remove(med)
                self.player.survival.treat_gut_sickness()
                self.add_message(
                    f"You take {med.name}. Your stomach settles. "
                    f"Should clear up within a day.", "normal")
            else:
                self.add_message(
                    "No medicine available. Whiskey, willow bark tea, "
                    "or laudanum would help. Otherwise wait it out.",
                    "advisory")
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

        # ── Treat disease with medicine ────────────────────────────────────
        if ("treat" in a and ("disease" in a or "sick" in a or "illness" in a)) \
                or "take medicine" in a or "drink medicine" in a \
                or ("use" in a and ("willow" in a or "quinine" in a or "laudanum" in a)):
            diseases = self.player.survival.diseases
            if not diseases:
                self.add_message("You aren't sick.", "advisory")
                return
            # Find medicine in inventory
            _MEDICINE_IDS = {"willow_tea", "quinine", "laudanum",
                             "pine_needle_tea"}
            medicine = [i for i in self.player.inventory if i.id in _MEDICINE_IDS]
            if not medicine:
                self.add_message(
                    "You have no medicine. Willow bark tea, quinine, or "
                    "laudanum can treat illness.", "advisory")
                return
            # Use the best medicine for the worst disease
            from src.survival import SurvivalStats
            for d in diseases:
                defn = SurvivalStats.DISEASE_DEFS.get(d["id"], {})
                treatment_items = defn.get("treatment_items", [])
                for med in medicine:
                    if med.id in treatment_items or med.id == "laudanum":
                        if self.player.survival.treat_disease(d["id"]):
                            self.player.inventory.remove(med)
                            self.add_message(
                                f"You take the {med.name}. It helps with "
                                f"the {d['name']}. The worst should pass sooner.",
                                "normal")
                            self.advance_time(5)
                            return
            # No matching medicine for the disease
            self.add_message(
                "That medicine won't help with what you have.", "advisory")
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

        # ── Dry soaked food/gear (requires nearby campfire) ─────────────
        if "dry" in a and ("food" in a or "meat" in a or "soaked" in a or "gear" in a):
            fire = self._nearby_structure("cook", radius=2)
            if not fire:
                self.add_message("You need a campfire nearby to dry food.", "advisory")
                self.advance_time(2)
                return
            soaked = [i for i in self.player.inventory
                      if getattr(i, 'extra', {}) and i.extra.get("soaked")]
            if not soaked:
                self.add_message("You don't have any soaked food.", "normal")
                return
            for item in soaked:
                orig = item.extra.get("original_spoil", item.days_until_spoil * 2)
                item.days_until_spoil = max(item.days_until_spoil,
                                            int(orig * 0.75))
                item.extra.pop("soaked", None)
                item.extra.pop("original_spoil", None)
                self.add_message(
                    f"You spread your {item.name} near the fire to dry. "
                    f"Salvaged — won't spoil as fast now.",
                    "advisory")
            self.advance_time(30)
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
            # Cooking skill affects nutrition bonus
            cook_skill = self.player.skills.get("cooking", 0)
            bonus = 1.0 + cook_skill * 0.05  # up to 50% more nutrition at skill 10
            cooked.nutrition *= bonus
            self.add_message(f"You cook the {item.name} over the fire. Smells good.", "normal")
            self.player.gain_skill_xp("cooking", 2.0)
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
            # Track meat vs non-meat for scurvy
            is_meat = any(w in item.id.lower() for w in
                          ("venison", "meat", "jerky", "pemmican", "fish",
                           "bacon", "pork", "bear", "elk", "buffalo"))
            current_day = self.time.total_minutes // 1440
            self.player.survival.log_food(is_meat, current_day)
            # Poison check for unknown foods
            poison_chance = getattr(item, 'extra', {}).get('poison_chance', 0)
            if poison_chance > 0:
                import random as _poison_rng
                if _poison_rng.random() < poison_chance:
                    severity = getattr(item, 'extra', {}).get(
                        'poison_severity', 'mild')
                    if severity == "lethal":
                        self.player.survival.health = max(0,
                            self.player.survival.health - 40)
                        self.player.survival.gut_sick_hours = max(
                            self.player.survival.gut_sick_hours, 72)
                        self.add_message(
                            f"The {item.name} tastes fine at first... "
                            f"but hours later your gut is on fire. "
                            f"Something is very wrong.", "critical")
                    else:
                        self.player.survival.gut_sick_hours = max(
                            self.player.survival.gut_sick_hours, 12)
                        self.add_message(
                            f"The {item.name} makes you violently ill. "
                            f"Vomiting and cramps.", "critical")
                else:
                    self.add_message(
                        f"You eat the {item.name}. Seems fine.", "normal")
                    # Survived eating unknown food — learn to identify it
                    from src.foraging import learn_from_eating
                    learn_msg = learn_from_eating(self.player, item.id)
                    if learn_msg:
                        self.add_message(learn_msg, "advisory")
            else:
                self.add_message(
                    f"You eat the {item.name}. Hunger restored.", "normal")
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

        # ── Stake claim ───────────────────────────────────────────────────
        if "stake" in a and ("claim" in a or "ground" in a):
            # Need wooden stakes (or just logs) and paper
            has_stakes = any(i.id in ("log", "wooden_stake")
                            for i in self.player.inventory)
            has_paper = any(i.id in ("paper", "pencil")
                           for i in self.player.inventory)
            if not has_stakes:
                self.add_message("You need wooden stakes (or logs) to mark your claim.", "advisory")
                return
            claim, msg = self.claim_mgr.stake_claim(
                self.player.name,
                self.player.world_x, self.player.world_y,
                self.player.area_x, self.player.area_y,
                self.player.local_x, self.player.local_y,
                self.time.total_minutes // 1440)
            self.add_message(msg, "advisory" if claim else "normal")
            if claim:
                self.player.gain_skill_xp("law", 2.0)
                self.advance_time(30)
            return

        # ── Register claim at land office ─────────────────────────────────
        if "register" in a and "claim" in a:
            claims = self.claim_mgr.player_claims(self.player.name)
            unregistered = [c for c in claims if not c.registered]
            if not unregistered:
                self.add_message("No unregistered claims.", "normal")
                return
            # Check if near a land office
            lmap = self.current_local
            in_town = hasattr(lmap, 'town_layout') and lmap.town_layout
            if not in_town:
                self.add_message("You need to be at a land office in town to register.", "advisory")
                return
            if self.player.cash < 5.0:
                self.add_message("Registration costs $5. You can't afford it.", "advisory")
                return
            # Register the first unregistered claim
            c = unregistered[0]
            self.player.cash -= 5.0
            ok, msg = self.claim_mgr.register_claim(c.claim_id)
            self.add_message(msg, "advisory")
            self.advance_time(20)
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
                # Count companions panning nearby (partnership bonus)
                partners = sum(1 for link in self.companion_mgr.links.values()
                               if link.current_task == "prospect_pan"
                               and link.currently_tasked)
                result = pan_for_gold(self.player, lmap,
                                      season=self.time.season,
                                      partner_count=partners)
                tile.gold_grade = saved_grade  # restore
                self.player.pan_loaded = False
                self.player.pan_source_x = -1
                self.player.pan_source_y = -1
                self.player.gain_skill_xp("placer",  result.xp_placer)
                self.player.gain_skill_xp("geology", result.xp_geology)
                self.player.gold_oz += result.gold_oz
                # Track claim work
                claim = self.claim_mgr.claim_at(
                    self.player.world_x, self.player.world_y,
                    self.player.area_x, self.player.area_y,
                    self.player.local_x, self.player.local_y)
                if claim and claim.owner == self.player.name:
                    self.claim_mgr.work_claim(
                        claim.claim_id,
                        self.time.total_minutes // 1440,
                        result.gold_oz)
                # Significant find = reputation boost + triumph music
                if result.gold_oz > 0.05:
                    self.reputation.adjust(lmap._region_name, 3)
                    self.music.set_category("triumph", immediate=True)
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
                    dep_msg = depletion_message(grade_before, src_tile.gold_grade)
                    if dep_msg:
                        self.add_message(dep_msg, "advisory")
                # Nugget roll — use source tile data, not player's current tile
                _nugget_tile = src_tile if src_tile else tile
                _nugget_tile.pan_count = getattr(_nugget_tile, 'pan_count', 0) + 1
                nugget = NuggetSystem.roll_nugget(
                    dig_depth=_nugget_tile.dig_depth,
                    gold_grade=_nugget_tile.gold_grade,
                    region_name=lmap.world_map.get_region(lmap.world_x, lmap.world_y),
                    era_year=self.time.year,
                    placer_skill=self.player.skills.get("placer", 0),
                    rng=_rnd.Random(_rnd.randint(0, 999999)),
                    pan_count=_nugget_tile.pan_count,
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
            tile.pan_count = getattr(tile, 'pan_count', 0) + runs
            nugget = NuggetSystem.roll_nugget(
                dig_depth=tile.dig_depth,
                gold_grade=tile.gold_grade,
                region_name=lmap.world_map.get_region(lmap.world_x, lmap.world_y),
                era_year=self.time.year,
                placer_skill=self.player.skills.get("placer", 0),
                rng=_rnd.Random(_rnd.randint(0, 999999)),
                pan_count=tile.pan_count,
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
                tile.pan_count = getattr(tile, 'pan_count', 0) + 1
                nugget = NuggetSystem.roll_nugget(
                    dig_depth=tile.dig_depth,
                    gold_grade=tile.gold_grade,
                    region_name=lmap.world_map.get_region(lmap.world_x, lmap.world_y),
                    era_year=self.time.year,
                    placer_skill=self.player.skills.get("placer", 0),
                    rng=_rnd.Random(_rnd.randint(0, 999999)),
                    pan_count=tile.pan_count,
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
        if "geology" in a or "mineral" in a or ("read" in a and "terrain" in a):
            from src.prospecting import assess_ground
            msg = assess_ground(self.player, lmap,
                                self.player.local_x, self.player.local_y)
            self.player.gain_skill_xp("geology", 3.0)
            self.advance_time(5)
            self.add_message(msg, "advisory")
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
                tile.pan_count = getattr(tile, 'pan_count', 0) + 1
                nugget = NuggetSystem.roll_nugget(
                    dig_depth=depth_below_surface,
                    gold_grade=gold,
                    region_name=lmap.world_map.get_region(lmap.world_x, lmap.world_y),
                    era_year=self.time.year,
                    placer_skill=self.player.skills.get("placer", 0),
                    rng=_rnd.Random(_rnd.randint(0, 999999)),
                    pan_count=tile.pan_count,
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

        # (duplicate fill canteen handler removed — handled earlier)

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
            from src.items import make_item as _cb_make
            if "chop" in inv_tags:
                self.add_message(
                    "You hack through the brush with your axe. "
                    "Dry sticks and kindling pile up.", "normal")
                self.advance_time(30)
            else:
                self.add_message(
                    "You tear through the brush by hand. "
                    "Scratched up but you pull out useful material.", "normal")
                self.advance_time(45)
            tile.terrain = LocalTerrain.GROUND
            lmap.invalidate_terrain_cache()
            # Yield brush bundle
            try:
                bundle = _cb_make("brush_bundle")
                bundle.quantity = 2
                self.player.inventory.append(bundle)
                self.add_message("Got 2x Brush Bundle.", "normal")
            except (ValueError, KeyError):
                pass
            self.player.gain_skill_xp("survival", 1.0)
            return

        # ── Gather firewood (no axe needed — pick up sticks/deadfall) ─────
        if "gather" in a and ("firewood" in a or "wood" in a or "kindling" in a):
            TREE_TILES_G = (LocalTerrain.PINE, LocalTerrain.OAK, LocalTerrain.ASPEN,
                          LocalTerrain.JUNIPER, LocalTerrain.CEDAR, LocalTerrain.MAPLE,
                          LocalTerrain.CHESTNUT, LocalTerrain.HICKORY, LocalTerrain.CYPRESS,
                          LocalTerrain.MAGNOLIA, LocalTerrain.FOREST)
            near = False
            for dy in range(-3, 4):
                for dx in range(-3, 4):
                    nx, ny = px + dx, py + dy
                    if lmap.in_bounds(nx, ny) and lmap.tiles[ny][nx].terrain in TREE_TILES_G:
                        near = True
                        break
                if near:
                    break
            if not near:
                self.add_message("No trees nearby to gather wood from.", "advisory")
                return
            from src.items import make_item
            log = make_item("log")
            self.player.inventory.append(log)
            self.add_message(
                "You scrounge fallen branches and deadwood from the forest floor. "
                "Enough for a small fire.", "normal")
            self.advance_time(15)
            self.player.gain_skill_xp("survival", 1.0)
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



        # ── Rest / camp / sleep ───────────────────────────────────────────
        if "sleep until dawn" in a or "wait until morning" in a or \
                "sleep until morning" in a:
            # Calculate minutes until 6 AM
            hour = self.time.hour
            if hour >= 6:
                mins_to_dawn = (24 - hour + 6) * 60
            else:
                mins_to_dawn = (6 - hour) * 60
            if mins_to_dawn < 60:
                self.add_message("It's nearly dawn already.", "advisory")
                return
            has_bedroll = any(i.id == "bedroll" for i in self.player.inventory)
            is_sheltered = self._nearby_structure("shelter", radius=2) is not None
            from src.sleep import resolve_sleep
            result = resolve_sleep(self.player, mins_to_dawn,
                                   is_sheltered, has_bedroll)
            self.advance_time(mins_to_dawn)
            self.add_message(
                f"You sleep until dawn ({mins_to_dawn // 60} hours). "
                f"{result['quality'].capitalize()} rest.", "normal")
            return

        if "rest" in a or "sleep" in a:
            self._open_wait()
            return

        if ("camp" in a or "make camp" in a or "set up camp" in a) and "fire" not in a and "burn" not in a:
            # Set up camp — place campfire + tent if available
            lmap = self.current_local
            px, py = self.player.local_x, self.player.local_y
            messages_camp = []

            # Auto-build campfire if not already nearby
            fire = self._nearby_structure("cook", radius=3)
            if not fire:
                result = self.construction.start_equipment(
                    "campfire", lmap, px + 1, py, self.player.inventory)
                if result[0]:
                    self.construction.work_on_equipment(result[0], 15, 3)
                    messages_camp.append("You build a campfire.")
                else:
                    messages_camp.append("No logs for a fire.")

            # Note tent in inventory
            has_tent = any(i.id == "canvas_tent" for i in self.player.inventory)
            has_bedroll = any(i.id == "bedroll" for i in self.player.inventory)
            if has_tent:
                messages_camp.append("You set up your tent.")
            if has_bedroll:
                messages_camp.append("You lay out your bedroll.")
            if not has_tent and not has_bedroll:
                messages_camp.append("No tent or bedroll — sleeping on bare ground.")

            for m in messages_camp:
                self.add_message(m, "normal")

            # Journal entry
            if self.journal:
                self.journal.add_diary(
                    self.time.date_string,
                    f"Made camp. {'Tent up. ' if has_tent else ''}{'Bedroll down. ' if has_bedroll else ''}Fire {'lit.' if not fire else 'already burning.'}")

            self.advance_time(20)
            self._open_wait()  # then offer to rest
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
            msg = assess_ground(self.player, lmap,
                                self.player.local_x, self.player.local_y)
            self.add_message(msg, "advisory")
            self.advance_time(5)
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
            from src.fishing_mode import enter_fishing_mode
            enter_fishing_mode(self, self._console, self._ctx)
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

    def _trigger_rendezvous(self, current_day: int):
        """Activate the annual mountain man Rendezvous."""
        # Rotating historical sites
        sites = [
            ("Green River", 195, 138),
            ("Pierres Hole", 170, 125),
            ("Cache Valley", 185, 140),
        ]
        import random as _rv_rng
        site_name, sx, sy = sites[self.time.year % len(sites)]

        # Notify player
        dist = abs(self.player.world_x - sx) + abs(self.player.world_y - sy)
        if dist <= 40:
            self.add_message(
                f"Word reaches you: the Rendezvous has begun at {site_name}! "
                f"Trappers, traders, and tribes are gathering.", "advisory")

        # Create dynamic location if it doesn't exist
        if hasattr(self, 'dynamic_locs'):
            from src.dynamic_locations import DynamicLocation
            rdv = DynamicLocation(
                id="", name=f"Rendezvous at {site_name}",
                world_x=sx, world_y=sy,
                loc_type="trading_post", stage="active",
                discovered=True,
                notes=f"{self.time.year} Summer Rendezvous. Trade, resupply, compete.",
            )
            self.dynamic_locs.add(rdv)

        # Record in journal
        self.journal.add_diary(
            self.time.date_string,
            f"The {self.time.year} Rendezvous is at {site_name}. "
            f"Time to sell furs and resupply.")

        # Record in newspaper/gossip
        if hasattr(self, 'newspaper'):
            self.newspaper.record_event(
                "social",
                f"Annual Mountain Man Rendezvous begins at {site_name}.",
                sx, sy, current_day)

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

        p = self.player
        region = self.world.get_region(p.world_x, p.world_y)
        year = self.time.year if hasattr(self.time, "year") else "1849"

        # ── Compute lifetime stats ─────────────────────────────────────────
        start_minutes = getattr(self, '_start_minutes', self.time.total_minutes)
        days_survived = max(1, (self.time.total_minutes - start_minutes) // 1440)

        # Kills from combat log
        people_killed = []
        animals_killed = 0
        for aar in self.journal.combat_log:
            for name in aar.enemies_killed:
                # Animals don't have surnames typically
                if any(a in name.lower() for a in (
                    "bear", "wolf", "deer", "elk", "cougar", "coyote", "snake",
                    "beaver", "rabbit", "boar", "bison", "moose", "fox", "lynx",
                    "otter", "mink", "badger", "wolverine", "pronghorn", "mountain lion",
                    "grizzly", "rattlesnake")):
                    animals_killed += 1
                else:
                    people_killed.append(name)

        # People met
        people_met = len(self.journal.people)
        places_found = len(self.journal.places)

        # Best skills
        skill_desc = []
        for k, v in sorted(p.skills.items(), key=lambda x: -x[1]):
            if v >= 7:
                skill_desc.append(f"expert {k}")
            elif v >= 4:
                skill_desc.append(f"skilled {k}")
        skills_str = ", ".join(skill_desc[:5]) if skill_desc else "none"

        # Physical description
        attr_desc = []
        s = p.attributes
        if s.get("strength", 10) >= 14: attr_desc.append("powerfully built")
        elif s.get("strength", 10) <= 7: attr_desc.append("slight of frame")
        if s.get("agility", 10) >= 14: attr_desc.append("quick and nimble")
        if s.get("intelligence", 10) >= 14: attr_desc.append("sharp-minded")
        if s.get("charisma", 10) >= 14: attr_desc.append("silver-tongued")
        if s.get("constitution", 10) >= 14: attr_desc.append("iron constitution")
        elif s.get("constitution", 10) <= 7: attr_desc.append("sickly and frail")
        phys_str = ", ".join(attr_desc) if attr_desc else "an ordinary man"

        # Wounds at death
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

        # Final events
        recent_events = "\n".join(
            f"  {txt}" for txt, sev in self.messages[-50:])

        # Journal highlights
        diary_str = ""
        for entry in list(self.journal.diary)[-15:]:
            diary_str += f"  {entry.date_str}: {entry.text[:200]}\n"

        # People known
        known_people = ""
        for pp in self.journal.people[:10]:
            known_people += f"  {pp['name']} ({pp['occupation']})"
            if pp.get('notes'):
                known_people += f" — {pp['notes'][:80]}"
            known_people += "\n"

        # Combat history summary
        combat_str = ""
        for aar in self.journal.combat_log[-5:]:
            killed = ", ".join(aar.enemies_killed) if aar.enemies_killed else "none killed"
            combat_str += f"  {aar.date_str} at {aar.location}: {killed}\n"

        context = (
            f"CHARACTER: {p.name}, age {p.age}\n"
            f"YEAR OF DEATH: {year}\n"
            f"LOCATION: {region}\n"
            f"DAYS SURVIVED: {days_survived}\n"
            f"PHYSICAL DESCRIPTION: {phys_str}\n"
            f"NOTABLE ABILITIES: {skills_str}\n"
            f"CAUSE OF DEATH: {cause}\n"
            f"GOLD ACCUMULATED: {p.gold_oz:.3f} troy ounces\n"
            f"CASH ON PERSON: ${p.cash:.2f}\n"
            f"PEOPLE KILLED: {', '.join(people_killed) if people_killed else 'none'}\n"
            f"ANIMALS KILLED: {animals_killed}\n"
            f"PEOPLE MET: {people_met}\n"
            f"PLACES DISCOVERED: {places_found}\n"
            f"WOUNDS AT TIME OF DEATH:\n{wounds_str}"
            f"BLOOD REMAINING: {p.wounds.blood_pct*100:.0f}%\n"
            f"PEOPLE KNOWN:\n{known_people}\n"
            f"COMBAT HISTORY:\n{combat_str}\n"
            f"JOURNAL ENTRIES:\n{diary_str}\n"
            f"EVENTS LEADING TO DEATH (most recent last):\n{recent_events}\n"
        )

        # ── Generate obituary ──────────────────────────────────────────────
        con.clear()
        con.print(SCREEN_WIDTH // 2 - 10, SCREEN_HEIGHT // 2,
                  "Writing obituary...", fg=(180, 60, 60), bg=(0, 0, 0))
        ctx.present(con)

        obit = self.llm.generate_obituary(context) if self.llm else \
               f"{p.name} died in {region}. The frontier does not mourn long."

        # ── Build display lines ────────────────────────────────────────────
        W = SCREEN_WIDTH - 6
        max_w = W - 4
        lines = []

        # Stats block at top
        lines.append("")
        lines.append(f"{p.name}, age {p.age}")
        lines.append(f"Died {self.time.date_string}, {year}")
        lines.append(f"{region}")
        lines.append("")
        lines.append(f"  Cause of death:    {cause}")
        lines.append(f"  Days survived:     {days_survived}")
        lines.append(f"  Gold accumulated:  {p.gold_oz:.3f} troy oz  (${p.gold_oz * 20.67:.2f})")
        lines.append(f"  Cash on person:    ${p.cash:.2f}")
        if people_killed:
            lines.append(f"  Men killed:        {len(people_killed)}")
        else:
            lines.append(f"  Men killed:        none")
        lines.append(f"  Animals killed:    {animals_killed}")
        lines.append(f"  People met:        {people_met}")
        lines.append(f"  Places found:      {places_found}")
        if skills_str != "none":
            lines.append(f"  Known for:         {skills_str}")
        lines.append("")

        # Separator
        lines.append("─" * max_w)
        lines.append("")

        # Obituary text word-wrapped
        for para in obit.split("\n"):
            para = para.strip()
            if not para:
                lines.append("")
                continue
            line = ""
            for word in para.split():
                test = (line + " " + word).strip()
                if len(test) <= max_w:
                    line = test
                else:
                    if line:
                        lines.append(line)
                    line = word
            if line:
                lines.append(line)
            lines.append("")

        # People killed list
        if people_killed:
            lines.append("─" * max_w)
            lines.append("")
            lines.append("KILLED:")
            for name in people_killed:
                lines.append(f"  {name}")
            lines.append("")

        # Epitaph
        lines.append("─" * max_w)
        lines.append("")
        if p.gold_oz >= 10.0:
            lines.append("He found his gold. It did not save him.")
        elif p.gold_oz >= 1.0:
            lines.append("A little gold, and a lot of suffering.")
        elif days_survived > 365:
            lines.append("He lasted longer than most. The land got him anyway.")
        elif len(people_killed) >= 3:
            lines.append("He lived by the gun. He died the same way.")
        else:
            lines.append("The frontier does not mourn long.")
        lines.append("")

        scroll = 0
        view_h = SCREEN_HEIGHT - 8
        total = len(lines)

        while True:
            con.clear()

            # Title banner — black on dark red
            con.draw_rect(0, 0, SCREEN_WIDTH, 3, ord(" "),
                          fg=(180, 60, 60), bg=(30, 0, 0))
            title = f"  {p.name.upper()} — DEAD  "
            con.print(SCREEN_WIDTH // 2 - len(title) // 2, 1,
                      title, fg=(255, 100, 100), bg=(30, 0, 0))

            # Content
            scroll = max(0, min(scroll, max(0, total - view_h)))
            for i, line in enumerate(lines[scroll: scroll + view_h]):
                # Color coding
                if line.startswith("─"):
                    fg = (80, 60, 40)
                elif line.startswith("  Cause"):
                    fg = (220, 80, 80)
                elif line.startswith("  Days") or line.startswith("  Gold") or \
                     line.startswith("  Cash") or line.startswith("  Men") or \
                     line.startswith("  Animals") or line.startswith("  People") or \
                     line.startswith("  Places") or line.startswith("  Known"):
                    fg = (180, 160, 120)
                elif line.startswith("KILLED:"):
                    fg = (200, 80, 80)
                elif line == lines[-2] if len(lines) >= 2 else False:
                    # Epitaph line
                    fg = (160, 140, 100)
                else:
                    fg = (210, 190, 160)
                con.print(3, 4 + i, line[:max_w], fg=fg, bg=(0, 0, 0))

            # Footer
            footer = "[Up/Down] scroll    [Enter] exit"
            con.print(SCREEN_WIDTH // 2 - len(footer) // 2,
                      SCREEN_HEIGHT - 2, footer, fg=(100, 100, 100))
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

    def _river_crossing_check(self, lmap, move_dx: int, move_dy: int):
        """Water crossing risk. Only triggers for crossings wider than 2 tiles.
        Risks scale with load, constitution, and crossing width.
        Lost items wash downstream and can be found on the bank."""
        import random as _rng
        from src.local_map import LocalTerrain as _LT
        p = self.player
        px, py = p.local_x, p.local_y

        # Measure water width PERPENDICULAR to movement direction.
        # This tells us if we're crossing a wide body of water vs
        # just wading along a narrow stream.
        perp_dx, perp_dy = -move_dy, move_dx  # 90° rotation
        if perp_dx == 0 and perp_dy == 0:
            return  # no movement, skip
        width = 1  # current tile counts
        # Scan perpendicular one direction
        cx, cy = px, py
        for _ in range(20):
            cx += perp_dx
            cy += perp_dy
            if not lmap.in_bounds(cx, cy):
                break
            if lmap.tile_at(cx, cy).terrain != _LT.WATER:
                break
            width += 1
        # Scan perpendicular other direction
        cx, cy = px, py
        for _ in range(20):
            cx -= perp_dx
            cy -= perp_dy
            if not lmap.in_bounds(cx, cy):
                break
            if lmap.tile_at(cx, cy).terrain != _LT.WATER:
                break
            width += 1

        # Narrow water (0-2 tiles) = wade safely, no risk
        if width <= 2:
            return

        # First step into deep water = warning
        if not hasattr(p, '_in_water_warned') or not p._in_water_warned:
            p._in_water_warned = True
            load_pct = p.carried_weight / max(1, p.carry_capacity)
            con = p.attributes.get("constitution", 10)
            danger = "DANGEROUS" if load_pct > 0.8 or con < 8 else \
                     "risky" if load_pct > 0.5 else "manageable"
            self.add_message(
                f"Deep water ahead — crossing looks {width} tiles wide. "
                f"Your load is {p.carried_weight:.0f}lb. "
                f"This will be {danger}.",
                "warning" if danger != "manageable" else "advisory")
            return

        # ── Risk calculation ──────────────────────────────────────────
        con = p.attributes.get("constitution", 10)
        survival = p.skills.get("survival", 0)
        load_pct = p.carried_weight / max(1, p.carry_capacity)

        # Base risk per step in deep water
        base_risk = 0.05 * (width - 2)  # 5% per tile beyond 2
        # Load multiplier: heavier = more risk
        load_mult = 1.0 + max(0, load_pct - 0.3) * 3.0  # 30%+ load starts adding risk
        # Fitness helps
        fitness_mult = max(0.3, 1.5 - (con + survival) * 0.05)
        risk = base_risk * load_mult * fitness_mult

        if _rng.random() >= risk:
            return  # safe this step

        # ── Something goes wrong ──────────────────────────────────────
        roll = _rng.random()

        if roll < 0.25 and p.gold_oz > 0.01:
            # Gold dust washes away
            lost = min(p.gold_oz * 0.15, p.gold_oz)
            p.gold_oz -= lost
            self.add_message(
                f"Water surges over your pack — {lost:.3f} oz of gold "
                f"dust washes into the current!",
                "warning")

        elif roll < 0.55:
            # Item lost — washes downstream, lands on bank
            droppable = [i for i in p.inventory
                         if i.weight > 0.3
                         and not getattr(i, 'extra', {}).get('carry_capacity_lb')]
            if droppable:
                item = _rng.choice(droppable)
                p.inventory.remove(item)

                # Place item downstream on the nearest bank
                downstream_dist = _rng.randint(15, 40)
                # Flow direction: downstream = positive y generally
                flow_dx = 0 if abs(move_dx) > 0 else _rng.choice([-1, 1])
                flow_dy = 1 if move_dy == 0 else move_dy
                placed = False
                for dist in range(downstream_dist, downstream_dist + 20):
                    bx = px + flow_dx * dist + _rng.randint(-3, 3)
                    by = py + flow_dy * dist + _rng.randint(-2, 2)
                    if lmap.in_bounds(bx, by):
                        bank_tile = lmap.tile_at(bx, by)
                        if bank_tile.terrain not in (_LT.WATER, _LT.ROCK):
                            bank_tile.ground_items.append(item)
                            placed = True
                            break

                if placed:
                    self.add_message(
                        f"Your {item.name} is torn from your pack by the "
                        f"current! It might wash up downstream.",
                        "warning")
                else:
                    self.add_message(
                        f"Your {item.name} is swept away by the river. Gone.",
                        "warning")

        elif roll < 0.75:
            # Soaked — food marked as wet, spoils faster, can be dried
            food = [i for i in p.inventory
                    if i.perishable and i.days_until_spoil and i.days_until_spoil > 1]
            if food:
                item = _rng.choice(food)
                orig_spoil = item.days_until_spoil
                item.days_until_spoil = max(1, item.days_until_spoil // 3)
                if not hasattr(item, 'extra') or item.extra is None:
                    item.extra = {}
                item.extra["soaked"] = True
                item.extra["original_spoil"] = orig_spoil
                self.add_message(
                    f"Your {item.name} is completely waterlogged. "
                    f"Dry it near a fire before it spoils!",
                    "warning")

        else:
            # Drowning risk — heavy load + low CON
            if load_pct > 0.7 and con < 10:
                drown_dmg = int((load_pct - 0.5) * 40 + (10 - con) * 3)
                p.survival.health -= drown_dmg
                p.survival.fatigue = max(0, p.survival.fatigue - 30)
                self.add_message(
                    f"The weight drags you under! You thrash and fight "
                    f"for the surface, swallowing water. "
                    f"({drown_dmg} damage, exhausted)",
                    "critical")
                if p.survival.health <= 0:
                    # 60% chance to survive — wash up downstream without pack
                    if _rng.random() < 0.60:
                        self._drown_survive(lmap, _rng)
                    else:
                        self.add_message(
                            "The river takes you. The current is stronger "
                            "than you are. Your pack drags you down.",
                            "critical")
            elif load_pct > 0.5:
                p.survival.fatigue = max(0, p.survival.fatigue - 15)
                self.add_message(
                    "You struggle against the current. The weight of "
                    "your pack makes every stroke a fight.",
                    "advisory")

    def _drown_survive(self, lmap, rng):
        """Player nearly drowns but survives. Wake up downstream on the bank
        without backpack/rucksack. Inventory scattered in the river."""
        from src.local_map import LocalTerrain as _LT
        p = self.player

        # Separate items by weight — heavy items sink or travel far,
        # light items wash up closer. Pack/bags go the farthest.
        flow_dy = 1  # downstream = south-ish
        items_by_weight = sorted(p.inventory,
                                  key=lambda i: i.weight * getattr(i, 'quantity', 1),
                                  reverse=True)
        for item in items_by_weight:
            item_weight = item.weight * getattr(item, 'quantity', 1)
            is_bag = (getattr(item, 'extra', {}) or {}).get('carry_capacity_lb', 0) > 0

            # Bags/packs go VERY far downstream — might not be worth recovering
            if is_bag:
                dist = rng.randint(120, 200)
            elif item_weight > 5.0:
                # Heavy items (pickaxe, rifle) — far but findable
                dist = rng.randint(60, 120)
            elif item_weight > 1.0:
                # Medium items — moderate distance
                dist = rng.randint(30, 70)
            else:
                # Light items (food, ammo) — closer
                dist = rng.randint(15, 40)

            placed = False
            for offset in range(dist, dist + 40):
                bx = p.local_x + rng.randint(-5, 5)
                by = p.local_y + flow_dy * offset + rng.randint(-3, 3)
                if lmap.in_bounds(bx, by):
                    bank = lmap.tile_at(bx, by)
                    if bank.terrain not in (_LT.WATER, _LT.ROCK):
                        bank.ground_items.append(item)
                        placed = True
                        break
            # If can't place on bank, item is gone forever
        p.inventory.clear()
        p.left_hand = None
        p.right_hand = None

        # Lose gold dust — all of it
        gold_lost = p.gold_oz
        p.gold_oz = 0.0

        # Teleport player downstream onto a bank
        new_x, new_y = p.local_x, p.local_y
        for dist in range(30, 80):
            bx = p.local_x + rng.randint(-3, 3)
            by = p.local_y + flow_dy * dist
            if lmap.in_bounds(bx, by):
                bank = lmap.tile_at(bx, by)
                if bank.terrain not in (_LT.WATER, _LT.ROCK):
                    new_x, new_y = bx, by
                    break

        p.local_x = new_x
        p.local_y = new_y
        p.local_z = lmap.ground_z(new_x, new_y)

        # Time passes — several hours unconscious
        hours = rng.randint(3, 8)
        self.time.advance(hours * 60)

        # Survival state — alive but wrecked
        p.survival.health = max(5, p.survival.health)  # don't actually die
        p.survival.fatigue = 5
        p.survival.hunger = max(10, p.survival.hunger - 40)
        p.survival.thirst = max(5, p.survival.thirst - 30)
        p.survival.warmth = 30  # wet and cold

        self.add_message(
            f"...You wake face-down in the mud on the riverbank. "
            f"Coughing water. Everything hurts. {hours} hours have passed.",
            "critical")
        self.add_message(
            "Your pack is gone. Your gold is gone. Everything was "
            "ripped away by the current.",
            "critical")
        if gold_lost > 0:
            self.add_message(
                f"  [{gold_lost:.3f} oz gold dust lost to the river]",
                "critical")
        self.add_message(
            "Light items may have washed up nearby. Heavier gear "
            "could be a long walk downstream. Your pack... "
            "it might be half a mile away by now. Up to you if "
            "it's worth going after.",
            "advisory")
        self.recompute_fov()

    def _clear_water_warning(self):
        """Reset water warning flag when player leaves water."""
        if hasattr(self.player, '_in_water_warned'):
            self.player._in_water_warned = False

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
            was_hostile = target.combat_state == "hostile"
            event = player_attack_npc(self.player, target, weapon,
                                      distance=dist, aimed_part=aimed_part,
                                      weather=self.time.weather)
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
                    self._on_npc_death(target)
                    lmap.invalidate_terrain_cache()
                if event.defender_fled:
                    self.journal.log_enemy_fled(target.name)

            witnesses = self._witnesses_near(
                self.player.local_x, self.player.local_y,
                exclude_names={target.name})
            for msg in witness_reactions(witnesses, self.player.name,
                                         target.name, event.killed,
                                         current_day=self.time.total_minutes // 1440):
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
                    self_defense=was_hostile,
                    nearby_npcs=witnesses,
                )
                # Reputation + gossip
                if event.killed:
                    self.reputation.adjust(region, -5 if was_hostile else -40)
                    self._record_gossip(f"Killed {target.name}", -0.2 if was_hostile else -0.8)
                else:
                    self.reputation.adjust(region, -2 if was_hostile else -15)
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
                    return
            elif npc.combat_state == "fleeing":
                # Move NPC away from player (simple — just mark not present
                # after a few ticks; full pathfinding TBD)
                lmap = self.current_local
                fdx = -2 if npc.local_x < self.player.local_x else (2 if npc.local_x > self.player.local_x else random.choice([-2, 2]))
                fdy = -2 if npc.local_y < self.player.local_y else (2 if npc.local_y > self.player.local_y else random.choice([-2, 2]))
                npc.local_x = max(1, min(lmap.width - 2, npc.local_x + fdx))
                npc.local_y = max(1, min(lmap.height - 2, npc.local_y + fdy))
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
                npc.present = True   # body stays for looting
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
                                         victim, was_killed,
                                         current_day=self.time.total_minutes // 1440):
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
            "weather":    self.time.weather,
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

        from src.fast_travel import (calculate_trip, fast_travel_ui,
                                      execute_trip, encounter_ui,
                                      get_available_routes, take_transport)

        def _river_encounter(eng, canoe_type):
            """Resolve a river encounter — rapids, snags, capsizing."""
            import random as _riv_rng
            rng = _riv_rng.Random()
            skill = eng.player.skills.get("survival", 0)
            agi = eng.player.attributes.get("agility", 10)

            # Roll: d20 + survival/2 + agility/3 vs difficulty
            roll = rng.randint(1, 20) + skill // 2 + agi // 3
            difficulty = 12  # base rapids difficulty

            # Heavier boats handle rapids worse
            if canoe_type in ("flatboat", "keelboat", "pirogue"):
                difficulty += 3

            if roll >= difficulty:
                msgs = [
                    "Rapids ahead! You read the current and steer through. "
                    "Water sprays over the gunwales but you stay dry.",
                    "White water! You brace and paddle hard. The canoe "
                    "shoots through the chute clean.",
                    "Rocks ahead. You pull hard left, scrape the hull, "
                    "but make it through.",
                ]
                eng.player.gain_skill_xp("survival", 3.0)
                return rng.choice(msgs)
            else:
                # Capsized or damaged
                msgs = [
                    "The current catches you sideways. The canoe flips. "
                    "You're in the water.",
                    "A submerged log catches the hull. CRACK. "
                    "Water pours in. You scramble for shore.",
                    "The rapids are worse than they looked. The canoe "
                    "slams into a rock and spills you into the current.",
                ]
                # Lose some cargo
                lost = 0
                for item in list(eng.player.inventory):
                    if rng.random() < 0.2 and item.weight < 5:
                        eng.player.inventory.remove(item)
                        lost += 1
                # Damage player
                eng.player.survival.health = max(
                    0, eng.player.survival.health - rng.randint(5, 15))
                eng.player.survival.warmth = max(
                    0, eng.player.survival.warmth - 20)  # soaked
                result = rng.choice(msgs)
                if lost > 0:
                    result += f" You lost {lost} items in the river."
                return result

        # River travel — if player is in a canoe, try river path first
        if getattr(self.player, '_in_canoe', False):
            from src.fast_travel import calculate_river_trip
            canoe_type = getattr(self.player, '_canoe_type', 'birchbark_canoe')
            river_est = calculate_river_trip(
                self.player, self.world, cx, cy, vehicle_type=canoe_type)
            if river_est:
                loc = self.world.get_location_at(cx, cy)
                dest_name = loc.name if loc else f"({cx}, {cy})"
                style = fast_travel_ui(
                    self._console, self._ctx, river_est,
                    self.player, f"{dest_name} (by river)")
                if style is None:
                    return
                # Execute river trip — rapids encounters
                result, pos = execute_trip(
                    self, river_est, style)
                if result == "encounter":
                    # Rapids or river encounter
                    self.state = GameState.LOCAL_MAP
                    enc_msg = _river_encounter(self, canoe_type)
                    self.add_message(enc_msg, "critical")
                else:
                    self.add_message(
                        f"You arrive at {dest_name} by river.", "normal")
                    self.state = GameState.LOCAL_MAP
                return
            else:
                self.add_message(
                    "No river connects here. Disembark to travel overland.",
                    "advisory")
                return

        # Calculate trip
        estimate = calculate_trip(self.player, self.world, cx, cy)

        # Check for ocean
        if any("ocean" in w.lower() for w in estimate.warnings):
            self.add_message("Route crosses ocean — can't travel there.", "normal")
            return

        # Get destination name and check for transport routes
        loc = self.world.get_location_at(cx, cy)
        dest_name = loc.name if loc else f"({cx}, {cy})"

        # Find transport routes from current town to destination
        current_loc = self.world.get_location_at(
            self.player.world_x, self.player.world_y)
        transport_routes = []
        if current_loc and loc:
            from src.fast_travel import TRANSPORT_ROUTES
            for r in TRANSPORT_ROUTES:
                if (r.origin == current_loc.name
                        and r.destination == loc.name
                        and self.time.year >= r.era_start):
                    transport_routes.append(r)

        # Show confirmation UI with transport options
        style = fast_travel_ui(self._console, self._ctx, estimate,
                                self.player, dest_name,
                                transport_routes=transport_routes or None)
        if style is None:
            return  # cancelled

        # Handle transport route selection
        if isinstance(style, str) and style.startswith("transport_"):
            route_idx = int(style.split("_")[1])
            if route_idx < len(transport_routes):
                route = transport_routes[route_idx]
                msg = take_transport(self, route)
                self.add_message(msg, "advisory")
                self.state = GameState.LOCAL_MAP
                self.map_level_index = 0
                self.recompute_fov()
                return

        # Execute the trip (overland)
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
                self.advance_time(random.randint(60, 120))
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
                # Place pack animals near player
                if self.animal_mgr.animals and self.current_local:
                    self.animal_mgr.place_all_near(
                        self.player.local_x, self.player.local_y,
                        self.current_local)
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

    def check_edge_transition(self, nx: int, ny: int) -> bool:
        """If nx/ny is outside local map bounds, perform patch transition.
        Returns True if a transition happened, False if still in-bounds.
        Called by modal modes (combat, mining, trapping, etc.) that have
        their own movement loops."""
        lmap = self.current_local
        if not lmap:
            return False
        if 0 <= nx < lmap.width and 0 <= ny < lmap.height:
            return False
        if nx < 0:
            self._transition_patch(-1, 0,
                entry_x=lmap.width - 2, entry_y=self.player.local_y)
        elif nx >= lmap.width:
            self._transition_patch(1, 0,
                entry_x=1, entry_y=self.player.local_y)
        elif ny < 0:
            self._transition_patch(0, -1,
                entry_x=self.player.local_x, entry_y=lmap.height - 2)
        elif ny >= lmap.height:
            self._transition_patch(0, 1,
                entry_x=self.player.local_x, entry_y=1)
        return True

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

        # ── Elevation transition effects ──────────────────────────────
        old_key = getattr(self, '_last_patch_key', None)
        old_lmap = self.locals.get(old_key) if old_key else None
        old_elev = getattr(old_lmap, 'world_elevation_ft', 0) if old_lmap else 0
        new_elev = getattr(new_lmap, 'world_elevation_ft', 0)
        elev_delta = new_elev - old_elev

        if abs(elev_delta) > 50:
            # Ascending
            if elev_delta > 500:
                self.add_message(
                    "The trail climbs steeply. The air is noticeably thinner.",
                    "normal")
                self.advance_time(5)  # extra time for steep climb
            elif elev_delta > 200:
                self.add_message(
                    "The ground rises sharply. Hard going uphill.", "normal")
                self.advance_time(3)
            elif elev_delta > 50:
                self.add_message(
                    "The trail rises gently ahead.", "normal")
                self.advance_time(1)
            # Descending
            elif elev_delta < -500:
                self.add_message(
                    "You descend steeply into the valley below.", "normal")
            elif elev_delta < -200:
                self.add_message(
                    "The trail drops. Easier going downhill.", "normal")
            elif elev_delta < -50:
                self.add_message(
                    "The ground slopes gently downward.", "normal")

        # Track for next transition
        self._last_patch_key = (new_wx, new_wy, new_ax, new_ay)

        # Show location name when entering a new world tile's center patch
        center = AREAS_PER_WORLD // 2
        if new_ax == center and new_ay == center:
            loc = self.world.get_location_at(new_wx, new_wy)
            if loc:
                self.add_message(f"You enter {loc.name}.", "normal")
                self.journal.add_place(
                    loc.name, new_wx, new_wy,
                    notes=f"Visited {self.time.date_string}")

        # Tribal territory notification — only if player has knowledge
        if hasattr(self, 'tribal'):
            last = getattr(self, '_last_territory', [])
            new_tribes = self.tribal.get_territory_at(new_wx, new_wy)
            for tribe in new_tribes:
                if tribe in last:
                    continue
                # Only notify if player has encountered this tribe before
                standing = self.tribal.get_standing(tribe)
                if standing.last_contact_day > 0 or standing.days_near_tribe > 0:
                    from src.tribal_system import standing_label
                    label = standing_label(standing.standing)
                    self.add_message(
                        f"You are entering {tribe} territory. ({label})",
                        "advisory" if standing.standing >= 0 else "critical")
            self._last_territory = new_tribes

        # Location discovery when entering new world tiles
        from src.discovery import roll_location_discovery
        disc = roll_location_discovery(self, new_wx, new_wy)
        if disc:
            self.add_message(disc, "advisory")
            # Drop to area view momentarily to show the icon
            # (just show message — player can zoom out to see it)

    def _do_move(self, dx: int, dy: int):
        # Update weather penalty on player
        self.player._weather_move_penalty = self.time.weather_move_penalty

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
                # Bump attacks use melee only — no firearms (would need ammo check)
                melee_weapons = [i for i in self.player.inventory
                                 if i.is_weapon() and getattr(i, 'weapon_type', '') != "firearm"]
                weapon   = melee_weapons[0] if melee_weapons else None
                skn      = "survival"
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
                    was_hostile = True  # known hostile before attack
                    from src.combat import player_attack_npc, witness_reactions
                    weapons = [i for i in self.player.inventory if i.is_weapon()]
                    weapon = weapons[0] if weapons else None
                    event = player_attack_npc(self.player, npc_at, weapon,
                                              weather=self.time.weather)
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
                                                 npc_at.name, event.killed,
                                                 current_day=self.time.total_minutes // 1440):
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
                        self_defense=was_hostile,
                        nearby_npcs=witnesses,
                    )
                    if was_hostile:
                        self.reputation.adjust(region, -5 if event.killed else -2)
                    else:
                        self.reputation.adjust(region, -40 if event.killed else -15)
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
                # Offer climb attempt instead of flat block
                z_diff = abs(target_sz - cur_z)
                from src.movement import climb_check
                import random as _climb_rng
                success, fall_dmg, climb_msg = climb_check(
                    self.player, z_diff, _climb_rng.Random())
                self.add_message(climb_msg, "advisory" if success else "critical")
                if success:
                    cost_secs = int(self.player.move(dx, dy) * 3)
                    self.player.local_z = target_sz
                    self.player.survival.fatigue = max(0,
                        self.player.survival.fatigue - 10)
                    self.advance_time(max(1, cost_secs // 60))
                else:
                    if fall_dmg > 0:
                        self.player.survival.health = max(0,
                            self.player.survival.health - fall_dmg)
                        self.add_message(
                            f"You fall and take {fall_dmg} damage!", "critical")
                        if self.player.survival.health <= 0:
                            self._trigger_death("Fell from a cliff.")
                    self.advance_time(2)
                return

            # Deep water — swimming check
            from src.local_map import LocalTerrain as _MVT
            target_terrain = lmap.tile_at(nx, ny).terrain if lmap.in_bounds(nx, ny) else 0
            if target_terrain == _MVT.DEEP_WATER and not wall_blocked:
                from src.movement import swim_check, can_swim
                if not can_swim(self.player):
                    self.add_message("You're too exhausted to swim.", "critical")
                    return
                import random as _sw_rng
                ok, swim_msg = swim_check(self.player, _sw_rng.Random())
                self.add_message(swim_msg, "advisory" if ok else "critical")
                if ok:
                    self.player.move(dx, dy)
                    self.player.survival.fatigue = max(0,
                        self.player.survival.fatigue - 15)
                    self.advance_time(3)
                else:
                    self.advance_time(2)
                return

            if lmap.is_passable(nx, ny) and not wall_blocked:
                cost_secs = self.player.move(dx, dy)  # returns seconds
                # Mounted speed bonus
                if self.player.mounted and self.player.mount_animal_id:
                    mount = self.animal_mgr.get(self.player.mount_animal_id)
                    if mount and mount.alive:
                        cost_secs = int(cost_secs * 0.5)  # twice as fast mounted
                    else:
                        self.player.mounted = False
                        self.player.mount_animal_id = None
                if z_delta != 0:
                    self.player.local_z += z_delta
                    cost_secs = int(cost_secs * CLIMB_TIME_MULT)
                # Gravity check — if stepped into open air, fall
                self._apply_gravity(self.player, lmap)
                self.time.advance_seconds(cost_secs)
                # Wildlife movement — animals react to player presence
                if lmap:
                    self.wildlife_mgr._game_minutes = self.time.total_minutes
                    for wmsg in self.wildlife_mgr.update_all(
                            max(1, cost_secs // 60), self.player, lmap):
                        sev = ("critical" if "mauls" in wmsg or "claws" in wmsg
                               or "charges" in wmsg else "advisory")
                        self.add_message(wmsg, sev)
                # Pack animals follow player
                if self.animal_mgr.animals:
                    self.animal_mgr.move_animals(
                        self.player.local_x, self.player.local_y, lmap)
                self.recompute_fov()

                # River crossing — warn and risk check
                from src.local_map import LocalTerrain as _LT
                new_terrain = lmap.tile_at(
                    self.player.local_x, self.player.local_y).terrain
                if new_terrain == _LT.WATER:
                    self._river_crossing_check(lmap, dx, dy)
                else:
                    self._clear_water_warning()

                # Random walking event (very rare on local movement)
                from src.walking_events import roll_walking_event
                evt = roll_walking_event(self, lmap,
                    self.player.local_x, self.player.local_y)
                if evt:
                    self.add_message(evt[0], evt[1])
                # NPC-initiated greetings when player walks near
                self._check_npc_greetings()
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

        # Reset combat message pools for new playthrough
        try:
            from src.combat import _seen_messages
            _seen_messages.clear()
        except ImportError:
            pass

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
            attr_keys = set(self.player.attributes.keys())
            for key, val in cc["skills"].items():
                if key in attr_keys:
                    # Attribute bonus (e.g., River Trader's +1 charisma)
                    self.player.attributes[key] = self.player.attributes.get(key, 10) + val
                elif key in self.player.skills:
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

        # Advance time to the chosen era's start date
        from src.time_system import minutes_from_anchor, MONTH_NAMES
        self.time.total_minutes = minutes_from_anchor(
            cc["start_year"], cc["start_month"], 1, 6)
        self._start_minutes = self.time.total_minutes
        self.era_id = cc["era"]["id"]
        # Update NPC generator with era year for demographics
        self._npc_gen.year = cc["start_year"]

        # Era-specific starting inventory and equipment
        if self.era_id == "long_hunter":
            from src.items import starting_inventory_long_hunter
            bg_id = cc.get("background", {}).get("id", "long_hunter")
            self.player.inventory = starting_inventory_long_hunter(bg_id)
            self.player.left_hand = "Flintlock Rifle"
            self.player.right_hand = "Hunting Knife"
            # No horse — Long Hunters traveled on foot
            # Minimal map reveal — everything west is unknown
            self.world.mark_visited(self.player.world_x, self.player.world_y)
            self.world.mark_visited_radius(
                self.player.world_x, self.player.world_y, 2)

        elif self.era_id == "mountain_men":
            from src.items import starting_inventory_mountain_men
            bg_id = cc.get("background", {}).get("id", "mountain_man")
            self.player.inventory = starting_inventory_mountain_men(bg_id)
            self.player.left_hand = "Flintlock Rifle"
            self.player.right_hand = "Tomahawk"
            self.player.pack_animals = [
                {"type_id": "horse", "name": "Buck", "condition": 90,
                 "carrying_capacity_lb": 200.0},
            ]
            # Minimal map reveal — the Rockies are unmapped
            self.world.mark_visited(self.player.world_x, self.player.world_y)
            self.world.mark_visited_radius(
                self.player.world_x, self.player.world_y, 3)

        # Seed starting plant knowledge from background
        bg_id = cc.get("background", {}).get("id", "")
        from src.foraging import init_background_plants
        init_background_plants(self.player, bg_id)

        # Seed the opening journal entry for this character
        mo = MONTH_NAMES[cc["start_month"]]
        self.journal.diary.clear()
        self.journal.rumors.clear()
        self.journal.letters.clear()
        self.journal.places.clear()

        if self.era_id == "long_hunter":
            self.journal.add_diary(
                f"{mo} 1, {cc['start_year']}",
                f"Set out from the {cc['era']['region']}. Kentucky country "
                f"stretches west — canebrakes, hollows, and hardwood forest "
                f"as far as anyone has gone.\n\n"
                f"The Shawnee hunt these grounds. They don't share.\n\n"
                f"Deer hides are money — a good buck is a dollar. Hunt with "
                f"[K] combat mode. Skin your kills [A→Butcher]. Process hides "
                f"[A→Process hide]. Sell at any fort or settlement.\n\n"
                f"Travel light. Travel quiet. Come back rich — or don't come back.",
            )
        elif self.era_id == "mountain_men":
            self.journal.add_diary(
                f"{mo} 1, {cc['start_year']}",
                f"Outfitted at the {cc['era']['region']}. The Missouri "
                f"stretches west into country no white man has mapped. "
                f"Beaver country is in the mountains — weeks of travel.\n\n"
                f"The Rendezvous is in July at Green River. Trade your "
                f"year's catch there or at any fort along the way.\n\n"
                f"Set traps near streams [A→Set trap]. "
                f"Skin your catch [P]. Trade furs at forts [T→Trade]. "
                f"Head west to find beaver country. "
                f"Press [?] for controls. Press [J] to read this journal.",
            )
        else:
            self.journal.add_diary(
                f"{mo} 1, {cc['start_year']}",
                f"Arrived in {cc['era']['region']}. "
                f"The land is rough and the competition is real. "
                f"I am {cc['name']}, and I did not come this far "
                f"to go home empty-handed.\n\n"
                f"Pan for gold at creeks [A]. Sell dust to merchants [T→Trade]. "
                f"Build a sluice [B]. Talk to folks for tips [T]. "
                f"Press [?] for controls.",
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
        # Resolve data path — works both from source and PyInstaller exe
        _data_root = os.path.join(
            os.environ.get('GAME_DATA_ROOT', '.'), "data")
        _font_path = os.path.join(_data_root, "fonts", "terminal12x12_gs_ro.png")

        tileset = tcod.tileset.load_tilesheet(
            _font_path, 16, 16,
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

            # Start background music — plays during character creation
            self.music.play_shuffle()

            # Character creation — runs before the game loop
            from src.char_create import run_character_creation
            cc = run_character_creation(console, ctx)
            if cc is None:
                return   # player quit from name screen
            self._apply_character(cc)

            self.recompute_fov()

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

                self.renderer._season = self.time.season
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
                    self.renderer._period = self.time.period
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
                self.renderer.draw_traps(self.player, lmap, self.trap_mgr)
                self.renderer.draw_claims_on_map(self.player, lmap,
                                                    self.claim_mgr)
                self.renderer.draw_animals_on_map(self.player, lmap,
                                                     self.animal_mgr)
                self.renderer.draw_pack_animals(self.player, self.animal_mgr)
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
                    self.music.set_category("combat", immediate=True)
                    from src.combat_mode import enter_combat_mode
                    enter_combat_mode(self, console, ctx)

                # Auto-advance music track when current one ends
                # Update music category based on game context
                if self.time.period == "night":
                    self.music.set_category("night")
                elif hasattr(lmap, 'town_layout') and lmap and lmap.town_layout:
                    self.music.set_category("town")
                else:
                    self.music.set_category("explore")
                self.music.check_advance()

                # NOTE: _poll_keyboard_state disabled — it double-fires with
                # normal KeyDown events, causing toggles to cancel themselves.
                # TextInput fallback in handle_event covers RDP/SDL3 cases.

                for event in tcod.event.wait(timeout=0.05):
                    if not self.handle_event(event):
                        return
