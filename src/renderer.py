"""
Rendering: draws local map, sidebar, hotbar, and message log using tcod.
"""

import tcod
import tcod.console
from typing import List, Tuple, Optional
from src.constants import (SCREEN_WIDTH, SCREEN_HEIGHT, MAP_WIDTH, MAP_HEIGHT,
                            SIDE_X, SIDE_WIDTH, MSG_Y, MSG_HEIGHT,
                            VIEWPORT_W, VIEWPORT_H, LOCAL_WIDTH, LOCAL_HEIGHT,
                            SCREEN_HEIGHT)
from src.local_map import LocalMap, LOCAL_GLYPH, LocalTerrain
from src.world_map import (WorldMap, TERRAIN_GLYPH, TERRAIN_NAME,
                            TERRAIN_DESCRIPTION, TERRAIN_TRAVEL_MULT)
from src.player import Player, Stance, Speed


# Colors
WHITE   = (255, 255, 255)
YELLOW  = (255, 220,  60)
RED     = (220,  50,  50)
GREY    = (120, 120, 120)
DGREY   = ( 60,  60,  60)
GREEN   = ( 80, 180,  80)
CYAN    = ( 80, 200, 200)
BLACK   = (  0,   0,   0)
DIM     = ( 40,  40,  40)   # explored but not visible

HOTBAR = [
    ("[I]nventory", "i"),
    ("[C]haracter", "c"),
    ("[J]ournal",   "j"),
    ("[A]ctions",   "a"),
    ("[T]alk",      "t"),
    ("[B]uild",     "b"),
    ("[K]ombat",    "k"),
    ("[E]xamine",   "e"),
    ("[P]ickup",    "p"),
    ("[L]og",       "l"),
    ("[[][ []]",    ""),   # zoom
]


class Renderer:
    def __init__(self, console: tcod.console.Console):
        self.con = console

    def render_all(self, local_map: Optional[LocalMap], world_map: WorldMap,
                   player: Player, messages: List[Tuple[str, str]],
                   state: str = "local_map",
                   locals_dict: Optional[dict] = None,
                   gold_overlay: bool = False,
                   cursor_x: int = -1, cursor_y: int = -1):
        from src.engine import GameState, MAP_LEVEL_NAMES
        self.con.clear()
        self._draw_hotbar(MAP_LEVEL_NAMES.get(state, "Local"))

        if state == GameState.LOCAL_MAP:
            self._draw_local_map(local_map, player, locals_dict or {}, gold_overlay=gold_overlay)
            self._draw_minimap(world_map, player)
        elif state == GameState.AREA_MAP:
            self._draw_world_zoomed(world_map, player, tile_size=4,
                                     locals_dict=locals_dict or {})
        elif state == GameState.COUNTY_MAP:
            self._draw_world_at_stride(world_map, player, stride=1,
                                        locals_dict=locals_dict or {})
        elif state == GameState.STATE_MAP:
            self._draw_world_at_stride(world_map, player, stride=5)
        elif state == GameState.COUNTRY_MAP:
            self._draw_world_at_stride(world_map, player, stride=20)

        # Draw cursor on zoomed-out views
        if cursor_x >= 0 and state != GameState.LOCAL_MAP:
            self._draw_map_cursor(world_map, player, cursor_x, cursor_y, state)

        self._draw_sidebar(player, world_map=world_map, state=state, local_map=local_map)
        self._draw_messages(messages)

    # ── Hotbar ─────────────────────────────────────────────────────────────

    def _draw_hotbar(self, map_level: str = "Local"):
        self.con.draw_rect(0, 0, SCREEN_WIDTH, 1, ord(" "), fg=WHITE, bg=(30, 30, 30))
        x = 1
        for label, _ in HOTBAR:
            self.con.print(x, 0, label, fg=CYAN, bg=(30, 30, 30))
            x += len(label) + 2
        # Map level indicator right-aligned
        level_str = f"[{map_level}  [/] zoom]"
        self.con.print(SCREEN_WIDTH - len(level_str) - 1, 0, level_str,
                       fg=YELLOW, bg=(30, 30, 30))

    # ── Local Map ──────────────────────────────────────────────────────────

    def _adj_tile(self, local_map: LocalMap, locals_dict: dict,
                  wx: int, wy: int, ax: int, ay: int,
                  tx: int, ty: int):
        """
        Return the tile at local coords (tx, ty), crossing into adjacent area
        patches (and potentially world tiles) as needed.
        Returns None if the adjacent patch isn't loaded yet.
        """
        from src.constants import AREAS_PER_WORLD
        aax, aay, atx, aty = ax, ay, tx, ty
        awx, awy = wx, wy

        # Wrap x across patch / world tile boundaries
        while atx < 0:
            aax -= 1;  atx += LOCAL_WIDTH
        while atx >= LOCAL_WIDTH:
            aax += 1;  atx -= LOCAL_WIDTH
        if aax < 0:
            awx -= 1;  aax += AREAS_PER_WORLD
        elif aax >= AREAS_PER_WORLD:
            awx += 1;  aax -= AREAS_PER_WORLD

        # Wrap y across patch / world tile boundaries
        while aty < 0:
            aay -= 1;  aty += LOCAL_HEIGHT
        while aty >= LOCAL_HEIGHT:
            aay += 1;  aty -= LOCAL_HEIGHT
        if aay < 0:
            awy -= 1;  aay += AREAS_PER_WORLD
        elif aay >= AREAS_PER_WORLD:
            awy += 1;  aay -= AREAS_PER_WORLD

        if awx == wx and awy == wy and aax == ax and aay == ay:
            return local_map.tiles[aty][atx]
        adj = locals_dict.get((awx, awy, aax, aay))
        if adj is None:
            return None
        return adj.tiles[aty][atx]

    def _draw_local_map(self, local_map: LocalMap, player: Player,
                        locals_dict: dict, gold_overlay: bool = False):
        if local_map is None:
            return
        half_w = VIEWPORT_W // 2
        half_h = VIEWPORT_H // 2
        cam_x  = player.local_x - half_w
        cam_y  = player.local_y - half_h
        wx, wy = player.world_x, player.world_y
        ax, ay = player.area_x, player.area_y

        # Current view z-level
        view_z = player.local_z
        player_surface = int(local_map.surface_z[player.local_y][player.local_x]) \
            if local_map.in_bounds(player.local_x, player.local_y) else 0
        underground = view_z < player_surface

        from src.constants import VIEW_Z_BELOW

        for sy in range(VIEWPORT_H):
            for sx in range(VIEWPORT_W):
                tx, ty = cam_x + sx, cam_y + sy

                # Out of bounds — fetch from adjacent patch
                if not local_map.in_bounds(tx, ty):
                    adj = self._adj_tile(local_map, locals_dict,
                                         wx, wy, ax, ay, tx, ty)
                    if adj and (adj.visible or adj.explored):
                        glyph, fg, bg = LOCAL_GLYPH.get(adj.terrain, ("?", WHITE, BLACK))
                        if adj.explored and not adj.visible:
                            fg = tuple(max(0, c // 4) for c in fg)
                            bg = tuple(max(0, c // 4) for c in bg)
                        blood = getattr(adj, "blood", 0)
                        if blood == 1:
                            bg = (max(bg[0], 60), bg[1] // 2, bg[2] // 2)
                        elif blood >= 2:
                            bg = (max(bg[0], 90), min(bg[1], 10), min(bg[2], 10))
                        self.con.print(sx, sy + 1, glyph, fg=fg, bg=bg)
                    else:
                        self.con.print(sx, sy + 1, " ", fg=BLACK, bg=(5, 5, 15))
                    continue

                sz = int(local_map.surface_z[ty][tx])
                tile = local_map.tile_at_z(tx, ty, view_z)

                if tile is None:
                    if view_z > sz:
                        # Open air above surface — look down to find visible tile
                        found = False
                        for dz in range(1, VIEW_Z_BELOW + 1):
                            below_z = view_z - dz
                            below_tile = local_map.tile_at_z(tx, ty, below_z)
                            if below_tile is not None:
                                glyph, fg, bg = LOCAL_GLYPH.get(
                                    below_tile.terrain, (".", WHITE, BLACK))
                                dim = max(0.15, 1.0 - dz * 0.18)
                                fg = tuple(int(c * dim) for c in fg)
                                bg = tuple(int(c * dim * 0.5) for c in bg)
                                if below_tile.visible or below_tile.explored:
                                    self.con.print(sx, sy + 1, glyph, fg=fg, bg=bg)
                                else:
                                    self.con.print(sx, sy + 1, " ", fg=BLACK, bg=BLACK)
                                found = True
                                break
                        if not found:
                            self.con.print(sx, sy + 1, " ", fg=BLACK, bg=(3, 3, 5))
                    else:
                        # Solid underground — not dug out
                        self.con.print(sx, sy + 1, "#",
                                       fg=(40, 35, 30), bg=(15, 12, 8))
                    continue

                glyph, fg, bg = LOCAL_GLYPH.get(tile.terrain, ("?", WHITE, BLACK))

                # Blood tint on background
                blood = getattr(tile, "blood", 0)
                if blood == 1:  # light — pink tint
                    bg = (max(bg[0], 60), bg[1] // 2, bg[2] // 2)
                elif blood >= 2:  # heavy — dark red
                    bg = (max(bg[0], 90), min(bg[1], 10), min(bg[2], 10))

                if gold_overlay and getattr(tile, "panned", False):
                    g = tile.gold_grade
                    if g < 0.05:
                        fg, glyph = (80, 80, 80), "·"
                    elif g < 0.25:
                        fg, glyph = (160, 130, 60), "·"
                    elif g < 0.55:
                        fg, glyph = (220, 180, 60), "$"
                    else:
                        fg, glyph = (255, 220, 40), "$"
                    bg = (15, 10, 5)
                    self.con.print(sx, sy + 1, glyph, fg=fg, bg=bg)
                    continue

                if tile.visible:
                    if underground:
                        rfg = tuple(max(0, c * 7 // 10) for c in fg)
                        rbg = tuple(max(0, c * 5 // 10) for c in bg)
                        self.con.print(sx, sy + 1, glyph, fg=rfg, bg=rbg)
                    else:
                        self.con.print(sx, sy + 1, glyph, fg=fg, bg=bg)
                elif tile.explored:
                    dfg = tuple(max(0, c // 4) for c in fg)
                    dbg = tuple(max(0, c // 4) for c in bg)
                    self.con.print(sx, sy + 1, glyph, fg=dfg, bg=dbg)
                else:
                    self.con.print(sx, sy + 1, " ", fg=BLACK, bg=BLACK)

        # Edge wall indicators — show wall edges on tiles that have them
        wg = getattr(local_map, 'wall_grid', None)
        if wg:
            _WALL_COLOR = (130, 100, 55)
            _DOOR_COLOR = (170, 130, 70)
            _STONE_COLOR = (150, 148, 140)
            for sy in range(VIEWPORT_H):
                for sx in range(VIEWPORT_W):
                    tx, ty = cam_x + sx, cam_y + sy
                    tile = self._adj_tile(local_map, locals_dict, wx, wy, ax, ay, tx, ty)
                    if not tile or (not tile.visible and not tile.explored):
                        continue
                    edges = wg.edges_at(tx, ty, z=player.local_z)
                    if not edges:
                        continue
                    # Dim walls in explored-but-not-visible tiles
                    is_dim = tile.explored and not tile.visible
                    from src.construction import Edge
                    n = edges.get("N", 0)
                    s = edges.get("S", 0)
                    e = edges.get("E", 0)
                    w_edge = edges.get("W", 0)
                    has_n = n not in (0, Edge.DOOR)
                    has_s = s not in (0, Edge.DOOR)
                    has_e = e not in (0, Edge.DOOR)
                    has_w = w_edge not in (0, Edge.DOOR)
                    door_here = Edge.DOOR in (n, s, e, w_edge)

                    wc = tuple(c // 4 for c in _WALL_COLOR) if is_dim else _WALL_COLOR
                    dc = tuple(c // 4 for c in _DOOR_COLOR) if is_dim else _DOOR_COLOR

                    if door_here:
                        self.con.print(sx, sy + 1, "+", fg=dc)
                    elif has_n and has_s and has_e and has_w:
                        self.con.print(sx, sy + 1, "#", fg=wc)
                    elif has_n and has_s:
                        self.con.print(sx, sy + 1, "│", fg=wc)
                    elif has_e and has_w:
                        self.con.print(sx, sy + 1, "─", fg=wc)
                    elif has_n and has_e:
                        self.con.print(sx, sy + 1, "└", fg=wc)
                    elif has_n and has_w:
                        self.con.print(sx, sy + 1, "┘", fg=wc)
                    elif has_s and has_e:
                        self.con.print(sx, sy + 1, "┌", fg=wc)
                    elif has_s and has_w:
                        self.con.print(sx, sy + 1, "┐", fg=wc)
                    elif has_n or has_s:
                        self.con.print(sx, sy + 1, "│", fg=wc)
                    elif has_e or has_w:
                        self.con.print(sx, sy + 1, "─", fg=wc)

        # Ground item indicators — small dot overlay on visible tiles with items
        for sy in range(VIEWPORT_H):
            for sx in range(VIEWPORT_W):
                tx, ty = cam_x + sx, cam_y + sy
                tile = self._adj_tile(local_map, locals_dict, wx, wy, ax, ay, tx, ty)
                if tile and tile.visible and tile.ground_items:
                    # Don't overwrite the player glyph
                    if tx == player.local_x and ty == player.local_y:
                        continue
                    self.con.print(sx, sy + 1, "·", fg=(180, 160, 80), bg=BLACK)

        # Player — red tint when underground
        player_fg = (255, 160, 160) if underground else WHITE
        self.con.print(half_w, half_h + 1, "@", fg=player_fg, bg=BLACK)

    def draw_fire(self, fire_system, local_map, player: Player):
        """Render fire tiles as flickering glyphs."""
        import random
        cam_x = player.local_x - VIEWPORT_W // 2
        cam_y = player.local_y - VIEWPORT_H // 2
        for (fx, fy) in fire_system.get_fire_tiles():
            sx = fx - cam_x
            sy = fy - cam_y + 1
            if 0 <= sx < VIEWPORT_W and 1 <= sy < VIEWPORT_H + 1:
                glyph = random.choice(["^", "*", "~", "#"])
                fg = random.choice([
                    (255, 200, 50), (255, 150, 30), (255, 100, 20),
                    (255, 80, 10), (255, 255, 100),
                ])
                self.con.print(sx, sy, glyph, fg=fg, bg=(80, 20, 5))
        # Draw heating tiles (about to catch) with dim orange
        for (hx, hy) in fire_system.get_heat_tiles():
            if (hx, hy) in fire_system.burning:
                continue
            sx = hx - cam_x
            sy = hy - cam_y + 1
            if 0 <= sx < VIEWPORT_W and 1 <= sy < VIEWPORT_H + 1:
                self.con.print(sx, sy, ".", fg=(180, 80, 20), bg=(40, 10, 0))

    def draw_poi_indicators(self, player: Player, dynamic_locs, world_map):
        """Draw directional arrows at viewport edge pointing to nearby POIs."""
        if not dynamic_locs:
            return
        from src.constants import AREAS_PER_WORLD, PATCH_SIZE
        px, py = player.local_x, player.local_y
        half_w, half_h = VIEWPORT_W // 2, VIEWPORT_H // 2

        nearby = dynamic_locs.get_nearby(player.world_x, player.world_y, radius=3)
        for loc in nearby:
            if not loc.discovered:
                continue
            # Convert world tile distance to approximate local tile offset
            dwx = loc.world_x - player.world_x
            dwy = loc.world_y - player.world_y
            # Each world tile = 14 patches × 384 tiles
            approx_dx = dwx * AREAS_PER_WORLD * PATCH_SIZE // 2
            approx_dy = dwy * AREAS_PER_WORLD * PATCH_SIZE // 2
            # If same world tile, point toward center patch
            if dwx == 0 and dwy == 0:
                center = AREAS_PER_WORLD // 2
                approx_dx = (center - player.area_x) * PATCH_SIZE
                approx_dy = (center - player.area_y) * PATCH_SIZE

            if approx_dx == 0 and approx_dy == 0:
                continue

            # Project to viewport edge
            if abs(approx_dx) > abs(approx_dy):
                edge_x = (VIEWPORT_W - 2) if approx_dx > 0 else 1
                edge_y = half_h + int(approx_dy * half_w / max(abs(approx_dx), 1))
                arrow = ">" if approx_dx > 0 else "<"
            else:
                edge_y = (VIEWPORT_H - 1) if approx_dy > 0 else 1
                edge_x = half_w + int(approx_dx * half_h / max(abs(approx_dy), 1))
                arrow = "v" if approx_dy > 0 else "^"

            edge_y = max(1, min(VIEWPORT_H - 1, edge_y)) + 1  # +1 for hotbar
            edge_x = max(0, min(VIEWPORT_W - 1, edge_x))

            # Draw arrow + abbreviated name
            self.con.print(edge_x, edge_y, arrow, fg=(255, 200, 50), bg=(40, 30, 10))
            label = loc.name[:8]
            lx = max(0, min(edge_x - len(label) // 2, VIEWPORT_W - len(label)))
            ly = edge_y + (1 if arrow in ("^", "<", ">") else -1)
            if 1 <= ly <= VIEWPORT_H:
                self.con.print(lx, ly, label, fg=(200, 170, 80), bg=(0, 0, 0))

    def draw_npcs(self, npcs, local_map: LocalMap, player: Player):
        """Render NPC glyphs and adjacent name labels over the viewport."""
        cam_x = player.local_x - VIEWPORT_W // 2
        cam_y = player.local_y - VIEWPORT_H // 2

        for npc in npcs:
            if not npc.present:
                continue
            # Only show NPCs at the player's z-level
            if getattr(npc, "local_z", 0) != player.local_z:
                continue
            sx = npc.local_x - cam_x
            sy = npc.local_y - cam_y
            if not (0 <= sx < VIEWPORT_W and 0 <= sy < VIEWPORT_H):
                continue
            tile = local_map.tile_at(npc.local_x, npc.local_y)
            if not tile.visible:
                continue

            _, _, bg = LOCAL_GLYPH.get(tile.terrain, (".", WHITE, BLACK))

            # Color encodes state + relationship
            state = npc.combat_state
            if state == "hostile":
                fg_color = (220, 50, 50)       # red
            elif state == "fleeing":
                fg_color = (220, 160, 40)      # orange-yellow
            elif state == "surrendered":
                fg_color = (160, 160, 160)     # grey
            else:
                rel = npc.relationship
                if rel >= 50:
                    fg_color = (80, 220, 100)  # green — friend
                elif rel >= 5:
                    fg_color = (255, 200, 80)  # amber — acquaintance
                elif rel >= -20:
                    fg_color = (200, 200, 200) # white — stranger
                else:
                    fg_color = (220, 110, 60)  # orange-red — unfriendly

            # Dead NPCs show as % (corpse)
            if not npc.alive or npc.combat_state == "dead":
                self.con.print(sx, sy + 1, "%", fg=(120, 60, 60), bg=bg)
            else:
                self.con.print(sx, sy + 1, "@", fg=fg_color, bg=bg)

            # Name label when player is adjacent (within 2 tiles)
            dist = max(abs(npc.local_x - player.local_x),
                       abs(npc.local_y - player.local_y))
            if dist <= 2:
                label = npc.display_name()[:14]
                lx = max(0, min(sx, VIEWPORT_W - len(label)))
                ly = sy       # one row above glyph if possible
                if ly < 1:
                    ly = sy + 2
                self.con.print(lx, ly, label, fg=fg_color, bg=(0, 0, 0))

    def draw_wildlife(self, animals, local_map: LocalMap, player: Player):
        """Render wildlife glyphs over the viewport."""
        cam_x = player.local_x - VIEWPORT_W // 2
        cam_y = player.local_y - VIEWPORT_H // 2

        for animal in animals:
            if not (animal.alive or animal.recoverable):
                continue
            # Only show animals at the player's z-level
            if getattr(animal, "local_z", 0) != player.local_z:
                continue
            sx = animal.local_x - cam_x
            sy = animal.local_y - cam_y
            if not (0 <= sx < VIEWPORT_W and 0 <= sy < VIEWPORT_H):
                continue
            tile = local_map.tile_at(animal.local_x, animal.local_y)
            if not tile.visible:
                continue

            _, _, bg = LOCAL_GLYPH.get(tile.terrain, (".", WHITE, BLACK))
            glyph, fg = animal.glyph

            if animal.state == "hostile":
                fg = (220, 50, 50)          # charging — red
            elif animal.state == "wounded_fleeing":
                fg = (200, 120, 40)         # wounded — orange
            elif animal.state == "downed":
                glyph = "%"                 # down but alive — corpse symbol
                fg = (160, 80, 80)          # dark red
            elif animal.state == "dead":
                glyph = "%"                 # dead
                fg = (100, 60, 60)          # darker red

            self.con.print(sx, sy + 1, glyph, fg=fg, bg=bg)

            # Label when adjacent
            dist = max(abs(animal.local_x - player.local_x),
                       abs(animal.local_y - player.local_y))
            if dist <= 2 and animal.state in ("downed", "dead"):
                label = animal.species.display_name[:14]
                lx = max(0, min(sx, VIEWPORT_W - len(label)))
                ly = max(1, sy)
                self.con.print(lx, ly, label, fg=fg, bg=(0, 0, 0))

    # ── World Map ──────────────────────────────────────────────────────────

    def _draw_world_map(self, world_map: WorldMap, player: Player):
        # Center the view on the player
        vx = player.world_x - MAP_WIDTH  // 2
        vy = player.world_y - MAP_HEIGHT // 2

        for sy in range(MAP_HEIGHT):
            for sx in range(MAP_WIDTH):
                wx, wy = vx + sx, vy + sy
                if not world_map.in_bounds(wx, wy):
                    self.con.print(sx, sy + 1, " ", fg=BLACK, bg=BLACK)
                    continue
                terrain = world_map.tiles[wy][wx]
                glyph, fg, bg = TERRAIN_GLYPH.get(terrain, ("?", WHITE, BLACK))
                loc = world_map.get_location_at(wx, wy)
                if not world_map.visited[wy][wx]:
                    fg = tuple(max(1, c * 18 // 100) for c in fg)
                    bg = tuple(max(1, c * 18 // 100) for c in bg)
                    if loc:
                        # Show undiscovered cities as dim dots
                        self.con.print(sx, sy + 1, ".", fg=(70, 65, 35), bg=bg)
                    else:
                        self.con.print(sx, sy + 1, glyph, fg=fg, bg=bg)
                    continue
                if loc and loc.discovered:
                    self.con.print(sx, sy + 1, "*", fg=YELLOW, bg=bg)
                elif loc:
                    self.con.print(sx, sy + 1, ".", fg=(100, 90, 40), bg=bg)
                else:
                    self.con.print(sx, sy + 1, glyph, fg=fg, bg=bg)

        # Player marker
        px = player.world_x - vx
        py = player.world_y - vy
        if 0 <= px < MAP_WIDTH and 0 <= py < MAP_HEIGHT:
            self.con.print(px, py + 1, "@", fg=WHITE, bg=BLACK)

    # ── World Map — zoomed in (Area view, tile_size screen tiles per world tile) ──

    def _draw_world_zoomed(self, world_map: WorldMap, player: Player,
                           tile_size: int = 4, locals_dict: dict = None):
        """Each world tile rendered as tile_size×tile_size screen tiles."""
        if locals_dict is None:
            locals_dict = {}
        # How many world tiles fit on screen
        wt_cols = MAP_WIDTH  // tile_size
        wt_rows = MAP_HEIGHT // tile_size
        vx = player.world_x - wt_cols // 2
        vy = player.world_y - wt_rows // 2

        for wty in range(wt_rows):
            for wtx in range(wt_cols):
                wx, wy = vx + wtx, vy + wty
                sx = wtx * tile_size
                sy = wty * tile_size + 1   # +1 for hotbar row

                if not world_map.in_bounds(wx, wy):
                    for dy in range(tile_size):
                        for dx in range(tile_size):
                            if sx+dx < MAP_WIDTH and sy+dy < MAP_HEIGHT+1:
                                self.con.print(sx+dx, sy+dy, " ", fg=BLACK, bg=BLACK)
                    continue

                terrain = world_map.tiles[wy][wx]
                glyph, fg, bg = TERRAIN_GLYPH.get(terrain, ("?", WHITE, BLACK))
                loc = world_map.get_location_at(wx, wy)
                visited = world_map.visited[wy][wx]
                if not visited:
                    dfg = tuple(max(1, c * 18 // 100) for c in fg)
                    dbg = tuple(max(1, c * 18 // 100) for c in bg)
                else:
                    dfg, dbg = fg, bg

                for dy in range(tile_size):
                    for dx in range(tile_size):
                        if sx+dx >= MAP_WIDTH or sy+dy >= MAP_HEIGHT+1:
                            continue
                        if loc and dx == tile_size//2 and dy == tile_size//2:
                            if loc.discovered:
                                self.con.print(sx+dx, sy+dy, "*", fg=YELLOW, bg=dbg)
                            else:
                                self.con.print(sx+dx, sy+dy, ".", fg=(70, 65, 35), bg=dbg)
                        else:
                            self.con.print(sx+dx, sy+dy, glyph, fg=dfg, bg=dbg)

        # Overlay player structures on visited patches
        from src.construction import PlacedEquipment
        for key, lmap in locals_dict.items():
            wx, wy = key[0], key[1]
            if not world_map.in_bounds(wx, wy):
                continue
            has_struct = any(isinstance(s, PlacedEquipment) and s.progress >= 100
                            for s in lmap.structures.values())
            if not has_struct:
                continue
            # Draw structure marker at this world tile
            bx = (wx - vx) * tile_size
            by = (wy - vy) * tile_size + 1
            # Place marker at corner of the tile block (not center — that's for towns)
            mx, my = bx, by
            if 0 <= mx < MAP_WIDTH and 1 <= my < MAP_HEIGHT + 1:
                self.con.print(mx, my, "+", fg=(200, 160, 80), bg=BLACK)

        # Player marker — center of their world tile block
        px = (player.world_x - vx) * tile_size + tile_size // 2
        py = (player.world_y - vy) * tile_size + tile_size // 2 + 1
        if 0 <= px < MAP_WIDTH and 1 <= py < MAP_HEIGHT + 1:
            self.con.print(px, py, "@", fg=WHITE, bg=BLACK)

    # ── World Map — strided (County / State / Country views) ───────────────

    def _draw_world_at_stride(self, world_map: WorldMap, player: Player,
                              stride: int = 1, locals_dict: dict = None):
        """
        stride=1: each screen tile = 1 world tile (County — scrollable, centered on player)
        stride=5: each screen tile = 5×5 world tiles sampled (State)
        stride=20: full US (Country)
        """
        if stride == 1:
            # Scrollable 1:1 — center on player
            vx = player.world_x - MAP_WIDTH  // 2
            vy = player.world_y - MAP_HEIGHT // 2
            for sy in range(MAP_HEIGHT):
                for sx in range(MAP_WIDTH):
                    wx, wy = vx + sx, vy + sy
                    self._draw_world_tile(world_map, wx, wy, sx, sy + 1, player)
            # Player structure markers on county map
            if locals_dict:
                from src.construction import PlacedEquipment
                for key, lmap in locals_dict.items():
                    wx, wy = key[0], key[1]
                    has_struct = any(isinstance(s, PlacedEquipment) and s.progress >= 100
                                    for s in lmap.structures.values())
                    if not has_struct:
                        continue
                    sx = wx - vx
                    sy = wy - vy + 1
                    if 0 <= sx < MAP_WIDTH and 1 <= sy < MAP_HEIGHT + 1:
                        self.con.print(sx, sy, "+", fg=(200, 160, 80), bg=BLACK)
            # Player marker
            self.con.print(MAP_WIDTH // 2, MAP_HEIGHT // 2 + 1, "@", fg=WHITE, bg=BLACK)
        else:
            # Strided views — center on player, fill the screen
            scaled_w = world_map.width  // stride
            scaled_h = world_map.height // stride

            if scaled_w <= MAP_WIDTH and scaled_h <= MAP_HEIGHT:
                # Fits on screen — center the map (country zoom)
                off_x = (MAP_WIDTH  - scaled_w) // 2
                off_y = (MAP_HEIGHT - scaled_h) // 2 + 1
                vx, vy = 0, 0
            else:
                # Larger than screen — scroll centered on player (state zoom)
                off_x, off_y = 0, 1
                vx = player.world_x // stride - MAP_WIDTH // 2
                vy = player.world_y // stride - MAP_HEIGHT // 2
                vx = max(0, min(vx, scaled_w - MAP_WIDTH))
                vy = max(0, min(vy, scaled_h - MAP_HEIGHT))

            draw_w = min(scaled_w, MAP_WIDTH)
            draw_h = min(scaled_h, MAP_HEIGHT)

            for sy in range(draw_h):
                for sx in range(draw_w):
                    wx = (vx + sx) * stride
                    wy = (vy + sy) * stride
                    self._draw_world_tile(world_map, wx, wy,
                                          off_x + sx, off_y + sy, player,
                                          sample_stride=stride, no_dim=True)
            # Player marker
            px = off_x + player.world_x // stride - vx
            py = off_y + player.world_y // stride - vy
            if 0 <= px < MAP_WIDTH and 0 <= py < MAP_HEIGHT + 1:
                self.con.print(px, py, "@", fg=WHITE, bg=BLACK)

            # Location labels — only discovered, filter by zoom
            for loc in world_map.locations.values():
                if not loc.discovered:
                    continue
                if stride >= 20 and loc.population < 10000:
                    continue
                if stride >= 5 and loc.population < 2000:
                    continue
                lx = off_x + loc.x // stride - vx
                ly = off_y + loc.y // stride - vy
                if 0 <= lx < MAP_WIDTH - 1 and 1 <= ly < MAP_HEIGHT + 1:
                    self.con.print(lx, ly, "*", fg=YELLOW, bg=BLACK)
                    label = loc.name[:10]
                    if lx + 1 + len(label) < MAP_WIDTH:
                        self.con.print(lx + 1, ly, label, fg=YELLOW, bg=BLACK)

    def _draw_world_tile(self, world_map: WorldMap, wx: int, wy: int,
                          sx: int, sy: int, player: Player,
                          sample_stride: int = 1, no_dim: bool = False):
        """Draw a single world map tile to screen position (sx, sy)."""
        if not world_map.in_bounds(wx, wy):
            self.con.print(sx, sy, " ", fg=BLACK, bg=(5, 5, 20))
            return
        terrain = int(world_map.tiles[wy][wx])
        # For strided views, pick most common terrain in block
        if sample_stride > 1:
            terrain = self._sample_terrain(world_map, wx, wy, sample_stride)
        glyph, fg, bg = TERRAIN_GLYPH.get(terrain, ("?", WHITE, BLACK))
        visited = world_map.visited[wy][wx]
        if not visited and not no_dim:
            # Unvisited: show terrain at ~18% brightness so US map shape is visible
            fg = tuple(max(1, c * 18 // 100) for c in fg)
            bg = tuple(max(1, c * 18 // 100) for c in bg)
        self.con.print(sx, sy, glyph, fg=fg, bg=bg)

    def _sample_terrain(self, world_map: WorldMap, wx: int, wy: int, stride: int) -> int:
        """Return most common terrain type in a stride×stride block."""
        counts: dict = {}
        for dy in range(stride):
            for dx in range(stride):
                x, y = wx + dx, wy + dy
                if world_map.in_bounds(x, y):
                    t = int(world_map.tiles[y][x])
                    counts[t] = counts.get(t, 0) + 1
        return max(counts, key=counts.get) if counts else 0

    # ── Mini Map ────────────────────────────────────────────────────────────

    def _draw_map_cursor(self, world_map: WorldMap, player: Player,
                           cx: int, cy: int, state: str):
        """Draw the fast-travel cursor on zoomed-out world map views."""
        from src.engine import GameState, MAP_STRIDE
        stride = MAP_STRIDE.get(state, 1)

        if state == GameState.AREA_MAP:
            tile_size = 4
            wt_cols = MAP_WIDTH // tile_size
            wt_rows = MAP_HEIGHT // tile_size
            vx = player.world_x - wt_cols // 2
            vy = player.world_y - wt_rows // 2
            sx = (cx - vx) * tile_size + tile_size // 2
            sy = (cy - vy) * tile_size + tile_size // 2 + 1
        elif stride == 1:
            # County — scrollable 1:1
            vx = player.world_x - MAP_WIDTH // 2
            vy = player.world_y - MAP_HEIGHT // 2
            sx = cx - vx
            sy = cy - vy + 1
        else:
            # State/Country — strided
            scaled_w = world_map.width // stride
            scaled_h = world_map.height // stride
            off_x = (MAP_WIDTH - scaled_w) // 2
            off_y = (MAP_HEIGHT - scaled_h) // 2 + 1
            sx = off_x + cx // stride
            sy = off_y + cy // stride

        if 0 <= sx < MAP_WIDTH and 1 <= sy < MAP_HEIGHT + 1:
            # Draw cursor as blinking X
            self.con.print(sx, sy, "X", fg=(255, 80, 255), bg=(40, 10, 40))

            # Show cursor info in sidebar
            loc = world_map.get_location_at(cx, cy)
            from src.world_map import TERRAIN_NAME
            terrain = int(world_map.tiles[cy][cx]) if world_map.in_bounds(cx, cy) else 0
            tname = TERRAIN_NAME.get(terrain, "?")
            dist = abs(cx - player.world_x) + abs(cy - player.world_y)
            miles = dist * 5

            info_x = SIDE_X
            info_y = 2
            self.con.print(info_x, info_y, "CURSOR", fg=YELLOW, bg=(0, 0, 0))
            info_y += 1
            if loc:
                self.con.print(info_x, info_y, f"  {loc.name}", fg=WHITE, bg=(0, 0, 0))
                info_y += 1
            self.con.print(info_x, info_y, f"  {tname}", fg=GREY, bg=(0, 0, 0))
            info_y += 1
            self.con.print(info_x, info_y, f"  {dist} tiles (~{miles} mi)",
                           fg=WHITE, bg=(0, 0, 0))
            info_y += 1
            # Rough time estimate
            hours = dist * 5  # ~5 hours per tile average
            days = hours // 24
            rem_h = hours % 24
            self.con.print(info_x, info_y, f"  ~{days}d {rem_h}h travel",
                           fg=GREY, bg=(0, 0, 0))
            info_y += 2
            self.con.print(info_x, info_y, "  Enter = Travel here",
                           fg=CYAN, bg=(0, 0, 0))

    def _draw_minimap(self, world_map: WorldMap, player: Player):
        # 20 wide x 8 tall in top-right of sidebar
        mx, my = SIDE_X, 2
        mw, mh = 20, 8
        self.con.print(mx, my - 1, "AREA MAP", fg=GREY, bg=BLACK)
        vx = player.world_x - mw // 2
        vy = player.world_y - mh // 2
        for sy in range(mh):
            for sx in range(mw):
                wx, wy = vx + sx, vy + sy
                if not world_map.in_bounds(wx, wy):
                    self.con.print(mx + sx, my + sy, " ", fg=BLACK, bg=(10,10,10))
                    continue
                terrain = world_map.tiles[wy][wx]
                glyph, fg, bg = TERRAIN_GLYPH.get(terrain, (".", GREY, BLACK))
                if not world_map.visited[wy][wx]:
                    fg = tuple(max(1, c * 18 // 100) for c in fg)
                    bg = tuple(max(1, c * 18 // 100) for c in bg)
                self.con.print(mx + sx, my + sy, glyph, fg=fg, bg=bg)
        # Player dot on minimap
        self.con.print(mx + mw // 2, my + mh // 2, "@", fg=WHITE, bg=BLACK)
        # Local coordinates (changes every step — confirms movement is working)
        self.con.print(mx, my + mh + 1,
                       f"Local {player.local_x:>3},{player.local_y:<3}",
                       fg=DGREY, bg=BLACK)

    # ── World tile info panel (replaces minimap when in world views) ─────────

    def _draw_world_tile_info(self, x: int, y: int, player: Player,
                               world_map: WorldMap) -> int:
        """Draw terrain info for current world tile. Returns next y."""
        from src.constants import WORLD_TRAVEL
        wx, wy = player.world_x, player.world_y
        if not world_map.in_bounds(wx, wy):
            return y
        terrain = int(world_map.tiles[wy][wx])
        glyph, fg, bg = TERRAIN_GLYPH.get(terrain, ("?", WHITE, BLACK))
        name  = TERRAIN_NAME.get(terrain, "Unknown")
        desc  = TERRAIN_DESCRIPTION.get(terrain, "")

        self.con.print(x, y, "── Terrain ──────────────────", fg=GREY, bg=BLACK)
        y += 1
        self.con.print(x, y, f"{glyph} {name}", fg=fg, bg=bg)
        y += 1

        # Word-wrap description
        max_w = SIDE_WIDTH - 2
        words = desc.split()
        line  = ""
        for word in words:
            test = (line + " " + word).strip()
            if len(test) <= max_w:
                line = test
            else:
                self.con.print(x, y, line, fg=WHITE, bg=BLACK)
                y += 1
                line = word
        if line:
            self.con.print(x, y, line, fg=WHITE, bg=BLACK)
            y += 1

        # Location at this tile
        loc = world_map.get_location_at(wx, wy)
        if loc and loc.discovered:
            self.con.print(x, y, f"* {loc.name}", fg=YELLOW, bg=BLACK)
            y += 1
            self.con.print(x, y,
                f"  {loc.location_type}  pop. ~{loc.population:,}",
                fg=GREY, bg=BLACK)
            y += 1

        # Travel cost
        cost = int(WORLD_TRAVEL * TERRAIN_TRAVEL_MULT.get(terrain, 1.0))
        self.con.print(x, y,
            f"~{cost//60}h{cost%60:02d}m / tile on foot",
            fg=DGREY, bg=BLACK)
        y += 1
        self.con.print(x, y, f"Pos: {wx},{wy}", fg=DGREY, bg=BLACK)
        y += 1
        return y

    # ── Sidebar ─────────────────────────────────────────────────────────────

    def _draw_sidebar(self, player: Player, world_map: WorldMap = None,
                      state: str = "local_map", local_map: Optional[LocalMap] = None):
        from src.engine import GameState
        x = SIDE_X
        y = 12   # below minimap (local view); world view fills top of sidebar

        if state != GameState.LOCAL_MAP and world_map is not None:
            self._draw_world_tile_info(x, 1, player, world_map)

        # Terrain name — what the player is standing on
        if state == GameState.LOCAL_MAP and local_map is not None:
            tile = local_map.tile_at(player.local_x, player.local_y)
            if tile:
                _TERRAIN_NAMES = {
                    LocalTerrain.GROUND: "Bare Ground",
                    LocalTerrain.GRASS: "Grass",
                    LocalTerrain.FOREST: "Dense Forest",
                    LocalTerrain.ROCK: "Solid Rock",
                    LocalTerrain.WATER: "Water",
                    LocalTerrain.GRAVEL_BAR: "Gravel Bar",
                    LocalTerrain.BEDROCK: "Bedrock",
                    LocalTerrain.MUD: "Mud",
                    LocalTerrain.SAND: "Sand",
                    LocalTerrain.BRUSH: "Brush",
                    LocalTerrain.PIT: "Pit",
                    LocalTerrain.SPOIL_PILE: "Spoil Pile",
                    LocalTerrain.TUNDRA: "Tundra",
                    LocalTerrain.PINE: "Pine Tree",
                    LocalTerrain.OAK: "Oak Tree",
                    LocalTerrain.ASPEN: "Aspen",
                    LocalTerrain.JUNIPER: "Juniper",
                    LocalTerrain.CEDAR: "Cedar",
                    LocalTerrain.MAPLE: "Maple",
                    LocalTerrain.CHESTNUT: "Chestnut",
                    LocalTerrain.HICKORY: "Hickory",
                    LocalTerrain.CYPRESS: "Cypress",
                    LocalTerrain.MAGNOLIA: "Magnolia",
                    LocalTerrain.WORKED_GRAVEL: "Worked Gravel",
                    LocalTerrain.WORKED_DIRT: "Turned Dirt",
                    LocalTerrain.SHALLOW_PIT: "Shallow Pit",
                    LocalTerrain.DEEP_PIT: "Deep Pit",
                    LocalTerrain.TAILINGS: "Tailings",
                    LocalTerrain.TABLE: "Table",
                    LocalTerrain.CHAIR: "Chair",
                    LocalTerrain.BED: "Bed",
                    LocalTerrain.STOVE: "Stove",
                    LocalTerrain.BAR_COUNTER: "Bar Counter",
                    LocalTerrain.ANVIL_TILE: "Anvil",
                    LocalTerrain.SHELF: "Shelf",
                    LocalTerrain.CELL_BARS: "Cell Bars",
                    LocalTerrain.DESK: "Desk",
                    LocalTerrain.BARREL_TILE: "Barrel",
                    LocalTerrain.GAMBLING_TABLE: "Gambling Table",
                }
                tname = _TERRAIN_NAMES.get(tile.terrain, "")
                if tname:
                    self.con.print(x, y - 3, f"{tname:<20}", fg=(180, 170, 140), bg=BLACK)

        # Z-level indicator
        if state == GameState.LOCAL_MAP and local_map is not None:
            pz = player.local_z
            sz = int(local_map.surface_z[player.local_y][player.local_x])
            from src.constants import Z_FEET_PER_LEVEL
            if pz < sz:
                depth_ft = (sz - pz) * Z_FEET_PER_LEVEL
                z_label = f"[Z:{pz:+d}  UNDERGROUND {depth_ft}ft]"
                z_color = (255, 160, 60)
            elif pz > sz:
                height_ft = (pz - sz) * Z_FEET_PER_LEVEL
                z_label = f"[Z:{pz:+d}  Elevated {height_ft}ft]"
                z_color = (120, 180, 255)
            elif pz != 0:
                z_label = f"[Z:{pz:+d}  Surface]"
                z_color = (150, 150, 150)
            else:
                z_label = ""
                z_color = GREY
            if z_label:
                self.con.print(x, y - 2, z_label, fg=z_color, bg=BLACK)

        # Hand slots
        lh = player.left_hand  or "[empty]"
        rh = player.right_hand or "[empty]"
        self.con.print(x, y,     f"L.Hand: {lh}", fg=WHITE, bg=BLACK)
        self.con.print(x, y + 1, f"R.Hand: {rh}", fg=WHITE, bg=BLACK)
        y += 3

        # Gold & cash — directly below hand slots so it's always visible
        gold_color = YELLOW if player.gold_oz > 0 else DGREY
        self.con.print(x, y,
                       f"Gold {player.gold_oz:>8.3f} oz   ${player.cash:>7.2f}",
                       fg=gold_color, bg=BLACK)
        y += 2

        # Compass — show direction to nearest town if player has one
        has_compass = any("navigate" in getattr(i, "tool_tags", [])
                          for i in player.inventory)
        if has_compass and world_map is not None:
            best_name, best_dist, best_dir = "", 9999, ""
            wx, wy = player.world_x, player.world_y
            for loc in world_map.locations.values():
                d = abs(loc.x - wx) + abs(loc.y - wy)
                if d < best_dist and d > 0:
                    best_dist = d
                    best_name = loc.name
                    dx = loc.x - wx
                    dy = loc.y - wy
                    dirs = []
                    if dy < 0: dirs.append("N")
                    if dy > 0: dirs.append("S")
                    if dx < 0: dirs.append("W")
                    if dx > 0: dirs.append("E")
                    best_dir = "".join(dirs)
            if best_name:
                miles = best_dist * 5
                self.con.print(x, y,
                    f"Compass: {best_name} {best_dir} ~{miles}mi",
                    fg=(140, 170, 200), bg=BLACK)
                y += 1

        # Stance & Speed
        self.con.print(x, y, "── Stance ──  [S]  ── Speed ── [W]", fg=GREY, bg=BLACK)
        y += 1
        stances = ["Standing", "Crouched", "Prone↓", "Prone↑"]
        speeds  = ["Walk", "Jog", "Run", "Crawl"]
        stance_short = {
            "Standing": "Standing",
            "Crouched": "Crouched",
            "Prone (face down)": "Prone↓",
            "Prone (face up)":   "Prone↑",
        }
        for i, (s, sp) in enumerate(zip(stances, speeds)):
            cur_s  = stance_short.get(player.stance, "") == s
            cur_sp = player.speed[:len(sp)] == sp
            sfg  = CYAN  if cur_s  else GREY
            spfg = CYAN  if cur_sp else GREY
            pre_s  = ">" if cur_s  else " "
            pre_sp = ">" if cur_sp else " "
            self.con.print(x,      y + i, f"{pre_s} {s:<10}", fg=sfg,  bg=BLACK)
            self.con.print(x + 14, y + i, f"{pre_sp} {sp}",   fg=spfg, bg=BLACK)
        y += 5

        # Cover / Hidden
        cover_color  = GREEN if player.in_cover != "none" else GREY
        hidden_color = GREEN if player.hidden == "yes"    else (YELLOW if player.hidden == "possible" else GREY)
        self.con.print(x, y,     f"Cover:  [{player.in_cover}]",  fg=cover_color,  bg=BLACK)
        self.con.print(x, y + 1, f"Hidden: [{player.hidden}]",    fg=hidden_color, bg=BLACK)
        y += 3

        # Vitals
        self.con.print(x, y, "── Vitals ──────────────────", fg=GREY, bg=BLACK)
        y += 1
        stats = [
            ("Health",  "health",  player.survival.health),
            ("Fatigue", "fatigue", player.survival.fatigue),
            ("Hunger",  "hunger",  player.survival.hunger),
            ("Thirst",  "thirst",  player.survival.thirst),
            ("Warmth",  "warmth",  player.survival.warmth),
        ]
        from src.constants import STAT_WARNING, STAT_CRITICAL
        for label, attr, val in stats:
            bar = player.survival.bar(attr, width=10)
            if val <= STAT_CRITICAL:
                color = RED
            elif val <= STAT_WARNING:
                color = YELLOW
            else:
                color = GREEN
            self.con.print(x, y, f"{label:<7} {bar}", fg=color, bg=BLACK)
            y += 1

        # Blood / wound status
        wounds = player.wounds
        if wounds.is_bleeding or wounds.blood_pct < 1.0:
            bar   = wounds.blood_bar(10)
            bpct  = wounds.blood_pct
            bcolor = wounds.blood_color()
            bleed = wounds.total_bleed_rate
            bleed_str = f" -{bleed:.1f}/m" if bleed > 0 else ""
            self.con.print(x, y,
                           f"Blood   {bar}{bleed_str}",
                           fg=bcolor, bg=BLACK)
            y += 1
        y += 1

        # Date / Time / Weather (placeholder weather)
        from src.time_system import GameTime
        # time passed in via game state — for now placeholder
        self.con.print(x, y, "─" * (SIDE_WIDTH - 2), fg=DGREY, bg=BLACK)

    def draw_pack_animals(self, player: Player):
        """Show pack animal status in sidebar below the nearby-NPC list."""
        if not player.pack_animals:
            return
        x = SIDE_X
        y = 48   # bottom two rows before screen edge
        self.con.print(x, y, "── Animals ─────────────────", fg=GREY, bg=BLACK)
        y += 1
        for pa in player.pack_animals:
            cond = pa.get("condition", 100)
            cap  = pa.get("carrying_capacity_lb", 0.0)
            name = pa.get("name", "?")[:8]
            tid  = pa.get("type_id", "animal")[:4]
            color = GREEN if cond >= 70 else (YELLOW if cond >= 40 else RED)
            cap_str = f"{cap:.0f}lb" if cap > 0 else "  --"
            line = f"{name:<8} {tid:<4} {cond:>3}%  {cap_str}"
            self.con.print(x, y, line[:SIDE_WIDTH - 2], fg=color, bg=BLACK)
            y += 1
            if y >= SCREEN_HEIGHT - 1:
                break

    def draw_npc_sidebar(self, npcs, player: Player):
        """Render visible-NPC list in the lower sidebar panel."""
        x = SIDE_X
        # Position below the separator drawn at the end of _draw_sidebar
        y = 37

        present = [n for n in npcs
                   if n.present and n.alive
                   and max(abs(n.local_x - player.local_x),
                           abs(n.local_y - player.local_y)) <= 20]
        # Sort: hostiles first, then by distance
        present.sort(key=lambda n: (
            0 if n.combat_state == "hostile" else
            1 if n.combat_state == "fleeing" else 2,
            max(abs(n.local_x - player.local_x),
                abs(n.local_y - player.local_y))
        ))

        self.con.print(x, y, "── Nearby ──────────────────", fg=GREY, bg=BLACK)
        y += 1

        if not present:
            self.con.print(x, y, "  No one visible.", fg=DGREY, bg=BLACK)
            return

        max_rows = 48 - y   # sidebar column extends past message area
        for npc in present[:max_rows]:
            state = npc.combat_state
            rel   = npc.relationship

            if state == "hostile":
                color = (220, 50, 50)
                tag   = "[!]"
            elif state == "fleeing":
                color = (220, 160, 40)
                tag   = "[~]"
            elif state == "surrendered":
                color = (160, 160, 160)
                tag   = "[?]"
            else:
                tag = "   "
                if rel >= 50:
                    color = (80, 220, 100)
                elif rel >= 5:
                    color = (255, 200, 80)
                elif rel >= -20:
                    color = (200, 200, 200)
                else:
                    color = (220, 110, 60)

            name = npc.display_name()[:12]
            dist = max(abs(npc.local_x - player.local_x),
                       abs(npc.local_y - player.local_y))
            # Eye icon: can this NPC see the player? (witness range)
            can_see = dist <= 40  # day default
            try:
                from src.engine import Engine
                # Approximate — use same ranges as _witnesses_near
                period = getattr(self, '_period', 'day')
                if period == "night":
                    can_see = dist <= 15
                elif period in ("dawn", "dusk"):
                    can_see = dist <= 25
            except Exception:
                pass
            eye = "*" if can_see and npc.alive else " "
            line = f"{tag}{eye}{name:<12} {dist:>3}t"
            self.con.print(x, y, line[:SIDE_WIDTH - 2], fg=color, bg=BLACK)
            y += 1

    # ── Messages ────────────────────────────────────────────────────────────

    def _draw_messages(self, messages: List[Tuple[str, str]]):
        """messages: list of (text, severity). Word-wraps long lines to fit the panel."""
        self.con.draw_rect(0, MSG_Y, MAP_WIDTH, MSG_HEIGHT, ord(" "), fg=WHITE, bg=(10, 10, 10))
        self.con.draw_rect(0, MSG_Y, MAP_WIDTH, 1, ord("─"), fg=DGREY, bg=BLACK)

        colors  = {"normal": WHITE, "advisory": YELLOW, "critical": RED}
        max_w   = MAP_WIDTH - 2
        max_rows = MSG_HEIGHT - 1   # rows below the separator

        # Word-wrap all recent messages into (line, color) pairs
        wrapped: List[Tuple[str, tuple]] = []
        for text, severity in messages[-30:]:
            color = colors.get(severity, WHITE)
            words = text.split()
            line  = ""
            for word in words:
                test = (line + " " + word).strip()
                if len(test) <= max_w:
                    line = test
                else:
                    if line:
                        wrapped.append((line, color))
                    line = word
            if line:
                wrapped.append((line, color))

        for i, (line, color) in enumerate(wrapped[-max_rows:]):
            self.con.print(1, MSG_Y + 1 + i, line, fg=color, bg=(10, 10, 10))
