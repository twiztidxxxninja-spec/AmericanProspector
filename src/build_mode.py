"""
src/build_mode.py

Building mode UI -- plan walls, floors, rooms, doors, stairs, then queue
construction orders.  Uses its own modal event loop (same pattern as
mining_mode.py).

Camera follows the *cursor*, not the player.  The real player position is
saved, temporarily overridden so the renderer centres on the cursor, then
restored.  The player '@' glyph is drawn at its true map position.
"""

import tcod
import tcod.event
from typing import Optional, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine import Engine

from src.constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT,
    MAP_WIDTH, MAP_HEIGHT,
    VIEWPORT_W, VIEWPORT_H,
    SIDE_X, SIDE_WIDTH,
)
from src.construction import (
    Edge, EDGE_LABELS, EDGE_MATERIALS,
    FloorType, FLOOR_MATERIALS,
    DIR_N, DIR_S, DIR_E, DIR_W, ALL_DIRS,
    BuildQueue,
)

# ── Tool enum ──────────────────────────────────────────────────────────────

TOOL_ROOM   = 0
TOOL_WALL   = 1
TOOL_FLOOR  = 2
TOOL_DOOR   = 3
TOOL_STAIRS = 4
TOOL_ERASE  = 5
TOOL_COUNT  = 6

TOOL_NAMES = {
    TOOL_ROOM:   "ROOM",
    TOOL_WALL:   "WALL",
    TOOL_FLOOR:  "FLOOR",
    TOOL_DOOR:   "DOOR",
    TOOL_STAIRS: "STAIRS",
    TOOL_ERASE:  "ERASE",
}

# Wall types selectable with 1-6
WALL_TYPES = [
    Edge.WOOD_WALL,   # 1
    Edge.STONE_WALL,  # 2
    Edge.DOOR,        # 3
    Edge.WINDOW,      # 4
    Edge.FENCE,       # 5
    Edge.CANVAS,      # 6
]

WALL_TYPE_LABELS = {
    Edge.WOOD_WALL:  "Wood",
    Edge.STONE_WALL: "Stone",
    Edge.DOOR:       "Door",
    Edge.WINDOW:     "Window",
    Edge.FENCE:      "Fence",
    Edge.CANVAS:     "Canvas",
}

FLOOR_TYPES = [FloorType.WOOD_PLANK, FloorType.STONE_FLAG, FloorType.DIRT_PACK]

FLOOR_TYPE_LABELS = {
    FloorType.WOOD_PLANK: "Wood Plank",
    FloorType.STONE_FLAG: "Stone Flag",
    FloorType.DIRT_PACK:  "Packed Dirt",
}

# Stair / ladder choices for STAIRS tool
STAIR_OPTIONS = [
    ("stairs_up",   "Stairs Up"),
    ("stairs_down", "Stairs Down"),
    ("ladder_up",   "Ladder Up"),
    ("ladder_down", "Ladder Down"),
]

# Colours
_CYAN   = (0, 220, 220)
_WHITE  = (255, 255, 255)
_BLACK  = (0, 0, 0)
_YELLOW = (255, 220, 50)
_GREY   = (150, 150, 150)
_DKGREY = (80, 80, 80)
_GREEN  = (60, 220, 60)
_RED    = (220, 60, 60)
_BANNER_BG = (30, 30, 50)
_GHOST_FG  = (0, 180, 200)
_GHOST_BG  = (0, 40, 50)
_CURSOR_FG = (255, 255, 255)
_CURSOR_BG = (60, 60, 120)
_ORDER_FG  = (200, 180, 80)


# ── Directional picker (reused by ROOM, WALL, DOOR) ───────────────────────

def _pick_direction(console, ctx, prompt: str = "Pick side") -> Optional[str]:
    """Block until the user presses a direction key.  Returns DIR_* or None."""
    console.print(1, VIEWPORT_H + 1, f" {prompt}: N/S/E/W (ESC cancel) ",
                  fg=_YELLOW, bg=_BANNER_BG)
    ctx.present(console)
    while True:
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                raise SystemExit()
            if isinstance(event, tcod.event.KeyDown):
                K = tcod.event.KeySym
                if event.sym == K.ESCAPE:
                    return None
                if event.sym == K.n:
                    return DIR_N
                if event.sym == K.s:
                    return DIR_S
                if event.sym == K.e:
                    return DIR_E
                if event.sym == K.w:
                    return DIR_W


# ── Stair picker ───────────────────────────────────────────────────────────

def _pick_stair(console, ctx) -> Optional[str]:
    """Show a small list and let user pick 1-4."""
    y0 = VIEWPORT_H // 2 - 2
    for i, (key, label) in enumerate(STAIR_OPTIONS):
        console.print(VIEWPORT_W // 2 - 10, y0 + i, f"  {i + 1}) {label}  ",
                      fg=_YELLOW, bg=_BANNER_BG)
    console.print(VIEWPORT_W // 2 - 10, y0 + len(STAIR_OPTIONS),
                  "  ESC) Cancel  ", fg=_GREY, bg=_BANNER_BG)
    ctx.present(console)
    while True:
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                raise SystemExit()
            if isinstance(event, tcod.event.KeyDown):
                K = tcod.event.KeySym
                if event.sym == K.ESCAPE:
                    return None
                idx = event.sym - K.N1  # N1=0x31 ... N4=0x34
                if 0 <= idx < len(STAIR_OPTIONS):
                    return STAIR_OPTIONS[idx][0]


# ── Main entry point ──────────────────────────────────────────────────────

def enter_build_mode(engine: "Engine", console, ctx) -> None:
    """Modal build-mode event loop.  ESC returns to normal play."""
    lmap = engine.current_local
    if lmap is None:
        engine.add_message("No local map -- cannot enter build mode.", "advisory")
        return

    # Ensure the map has a build queue
    if not hasattr(lmap, "build_queue") or lmap.build_queue is None:
        from src.construction import BuildQueue as BQ
        lmap.build_queue = BQ()
    bq: BuildQueue = lmap.build_queue

    # Cursor starts at player position
    cur_x = engine.player.local_x
    cur_y = engine.player.local_y
    cur_z = engine.player.local_z

    # Save real player position so we can hijack it for camera
    real_px = engine.player.local_x
    real_py = engine.player.local_y
    real_pz = engine.player.local_z

    tool = TOOL_ROOM
    wall_type = Edge.WOOD_WALL
    floor_type_idx = 0  # index into FLOOR_TYPES
    floor_type = FLOOR_TYPES[floor_type_idx]

    # ROOM tool state
    anchor: Optional[Tuple[int, int]] = None  # NW corner set, waiting for SE

    # Undo stack: list of order ids added this session (for U key)
    undo_stack: List[int] = []

    def _cur_floor_type() -> int:
        return FLOOR_TYPES[floor_type_idx % len(FLOOR_TYPES)]

    def _restore_player():
        engine.player.local_x = real_px
        engine.player.local_y = real_py
        engine.player.local_z = real_pz

    # ── Render helper ──────────────────────────────────────────────────

    def _render():
        nonlocal cur_x, cur_y

        # Temporarily move player to cursor so renderer centres on it
        engine.player.local_x = cur_x
        engine.player.local_y = cur_y
        engine.player.local_z = cur_z

        # Render the normal local map
        engine.renderer.render_all(
            lmap, engine.world, engine.player, engine.messages,
            state="local_map", locals_dict=engine.locals,
            gold_overlay=False,
        )

        # Restore player
        _restore_player()

        # Camera coords (same math the renderer uses)
        half_w = VIEWPORT_W // 2
        half_h = VIEWPORT_H // 2
        cam_x = cur_x - half_w
        cam_y = cur_y - half_h

        # Draw real player '@' at its true position
        psx = real_px - cam_x
        psy = real_py - cam_y
        if 0 <= psx < VIEWPORT_W and 0 <= psy < VIEWPORT_H:
            console.print(psx, psy + 1, "@", fg=_WHITE, bg=_BLACK)

        # Draw pending build orders as highlighted tiles
        for order in bq.pending():
            osx = order.x - cam_x
            osy = order.y - cam_y
            if 0 <= osx < VIEWPORT_W and 0 <= osy < VIEWPORT_H:
                glyph = "+"
                if order.order_type == "floor":
                    glyph = "."
                elif order.order_type in ("wall", "door"):
                    glyph = "#"
                console.print(osx, osy + 1, glyph, fg=_ORDER_FG, bg=(20, 15, 5))

        # Draw ghost rectangle when ROOM anchor is set
        if tool == TOOL_ROOM and anchor is not None:
            ax, ay = anchor
            x1, x2 = min(ax, cur_x), max(ax, cur_x)
            y1, y2 = min(ay, cur_y), max(ay, cur_y)
            for gy in range(y1, y2 + 1):
                for gx in range(x1, x2 + 1):
                    sx = gx - cam_x
                    sy = gy - cam_y
                    if 0 <= sx < VIEWPORT_W and 0 <= sy < VIEWPORT_H:
                        is_edge = (gx == x1 or gx == x2 or gy == y1 or gy == y2)
                        g = "#" if is_edge else "."
                        console.print(sx, sy + 1, g, fg=_GHOST_FG, bg=_GHOST_BG)

        # Draw cursor on top
        csx = cur_x - cam_x  # should be half_w
        csy = cur_y - cam_y  # should be half_h
        if 0 <= csx < VIEWPORT_W and 0 <= csy < VIEWPORT_H:
            # Read existing glyph if possible, fallback to 'X'
            console.print(csx, csy + 1, "X", fg=_CURSOR_FG, bg=_CURSOR_BG)

        # ── Toolbar banner (row 0) ─────────────────────────────────────
        console.draw_rect(0, 0, SCREEN_WIDTH, 1, ord(" "),
                          fg=_WHITE, bg=_BANNER_BG)
        console.print(1, 0, "BUILD MODE", fg=_CYAN, bg=_BANNER_BG)

        # Tool indicators
        tx = 14
        for t in range(TOOL_COUNT):
            label = TOOL_NAMES[t]
            if t == tool:
                console.print(tx, 0, f"[{label}]", fg=_YELLOW, bg=_BANNER_BG)
            else:
                console.print(tx, 0, f" {label} ", fg=_GREY, bg=_BANNER_BG)
            tx += len(label) + 3

        # Wall/floor type on banner
        wt_label = WALL_TYPE_LABELS.get(wall_type, "?")
        ft_label = FLOOR_TYPE_LABELS.get(_cur_floor_type(), "?")
        info = f"Wall:{wt_label}  Floor:{ft_label}"
        console.print(SCREEN_WIDTH - len(info) - 2, 0, info,
                      fg=_WHITE, bg=_BANNER_BG)

        # ── Sidebar info ───────────────────────────────────────────────
        sx_start = SIDE_X
        sy = 2

        console.print(sx_start, sy, "-- Build Mode --", fg=_CYAN)
        sy += 1
        console.print(sx_start, sy, f"Tool: {TOOL_NAMES[tool]}", fg=_YELLOW)
        sy += 1
        console.print(sx_start, sy, f"Cursor: {cur_x},{cur_y} z:{cur_z}",
                      fg=_WHITE)
        sy += 1

        if tool == TOOL_ROOM and anchor is not None:
            ax, ay = anchor
            rw = abs(cur_x - ax) + 1
            rh = abs(cur_y - ay) + 1
            console.print(sx_start, sy, f"Room: {rw}x{rh}", fg=_GREEN)
            sy += 1
            # Estimate materials: perimeter walls + interior floor
            perim = 2 * (rw + rh)
            w_mat, w_qty, _ = EDGE_MATERIALS.get(wall_type, ("Log", 1, 10))
            f_mat, f_qty, _ = FLOOR_MATERIALS.get(_cur_floor_type(),
                                                   ("Plank", 1, 5))
            console.print(sx_start, sy,
                          f"Walls: ~{perim * w_qty} {w_mat}", fg=_GREY)
            sy += 1
            console.print(sx_start, sy,
                          f"Floor: ~{rw * rh * f_qty} {f_mat}", fg=_GREY)
            sy += 1
        else:
            sy += 1  # spacing

        # Material totals for pending queue
        totals = bq.total_materials_needed()
        if totals:
            console.print(sx_start, sy, "Pending materials:", fg=_WHITE)
            sy += 1
            for mat, qty in totals.items():
                console.print(sx_start + 1, sy, f"{qty}x {mat}", fg=_GREY)
                sy += 1
                if sy > 20:
                    break

        pending_n = len(bq.pending())
        time_rem = bq.total_time_remaining()
        sy = max(sy + 1, 14)
        console.print(sx_start, sy, f"Orders: {pending_n}", fg=_WHITE)
        sy += 1
        console.print(sx_start, sy, f"Build time: ~{time_rem} min", fg=_WHITE)

        # ── Key hints at bottom ────────────────────────────────────────
        hy = VIEWPORT_H + 2
        console.print(1, hy,     "Arrows:Move  TAB:Tool  1-6:WallType",
                      fg=_DKGREY)
        console.print(1, hy + 1, "ENTER:Place  F:Floor  U:Undo  ESC:Exit",
                      fg=_DKGREY)
        console.print(1, hy + 2, "</> or +/-:Z-level",
                      fg=_DKGREY)

        ctx.present(console)

    # ── Movement deltas ────────────────────────────────────────────────

    K = tcod.event.KeySym
    MOVE_KEYS = {
        K.UP:    (0, -1), K.DOWN:  (0, 1),
        K.LEFT:  (-1, 0), K.RIGHT: (1, 0),
        K.KP_8:  (0, -1), K.KP_2:  (0, 1),
        K.KP_4:  (-1, 0), K.KP_6:  (1, 0),
        K.KP_7:  (-1, -1), K.KP_9:  (1, -1),
        K.KP_1:  (-1, 1), K.KP_3:  (1, 1),
    }

    # ── Main loop ──────────────────────────────────────────────────────

    while True:
        _render()

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                raise SystemExit()

            if not isinstance(event, tcod.event.KeyDown):
                continue

            sym = event.sym

            # ── ESC: exit or cancel anchor ─────────────────────────────
            if sym == K.ESCAPE:
                if anchor is not None:
                    anchor = None  # cancel room selection
                    break
                # Exit build mode
                _restore_player()
                engine.add_message("Exited build mode.", "normal")
                return

            # ── TAB: cycle tool ────────────────────────────────────────
            if sym == K.TAB:
                anchor = None
                tool = (tool + 1) % TOOL_COUNT
                break

            # ── Cursor movement ────────────────────────────────────────
            if sym in MOVE_KEYS:
                dx, dy = MOVE_KEYS[sym]
                nx, ny = cur_x + dx, cur_y + dy
                if lmap.in_bounds(nx, ny):
                    cur_x, cur_y = nx, ny
                break

            # ── 1-6: select wall type ──────────────────────────────────
            digit = sym - K.N1  # 0-based
            if 0 <= digit < len(WALL_TYPES):
                wall_type = WALL_TYPES[digit]
                break

            # ── F: toggle floor type ───────────────────────────────────
            if sym == K.f:
                floor_type_idx = (floor_type_idx + 1) % len(FLOOR_TYPES)
                floor_type = FLOOR_TYPES[floor_type_idx]
                break

            # ── Z-level change: < > + - ────────────────────────────────
            if sym in (K.COMMA, K.MINUS):
                # Go down
                cur_z = max(cur_z - 1, -20)
                break
            if sym in (K.PERIOD, K.EQUALS):
                # Go up  (EQUALS is unshifted +)
                cur_z = min(cur_z + 1, 20)
                break

            # ── U: undo last order ─────────────────────────────────────
            if sym == K.u:
                if undo_stack:
                    remove_id = undo_stack.pop()
                    bq.orders = [o for o in bq.orders if o.id != remove_id]
                    engine.add_message("Build order undone.", "normal")
                else:
                    engine.add_message("Nothing to undo.", "advisory")
                break

            # ── ENTER: tool-specific action ────────────────────────────
            if sym == K.RETURN:

                # ── ROOM tool ──────────────────────────────────────────
                if tool == TOOL_ROOM:
                    if anchor is None:
                        # Set NW corner
                        anchor = (cur_x, cur_y)
                        engine.add_message(
                            f"Room corner set at ({cur_x},{cur_y}). "
                            "Move to opposite corner and press ENTER.",
                            "normal")
                    else:
                        # Confirm room: normalise to NW/SE
                        ax, ay = anchor
                        x1, x2 = min(ax, cur_x), max(ax, cur_x)
                        y1, y2 = min(ay, cur_y), max(ay, cur_y)
                        rw = x2 - x1 + 1
                        rh = y2 - y1 + 1
                        if rw < 2 or rh < 2:
                            engine.add_message(
                                "Room must be at least 2x2.", "advisory")
                            break

                        # Pick door side
                        _render()  # refresh before prompt
                        door_dir = _pick_direction(console, ctx,
                                                   "Door side")
                        if door_dir is None:
                            engine.add_message("Room cancelled.", "advisory")
                            anchor = None
                            break

                        orders = bq.add_room(
                            x1, y1, rw, rh,
                            wall_type=wall_type,
                            floor_type=_cur_floor_type(),
                            door_dir=door_dir,
                        )
                        for o in orders:
                            undo_stack.append(o.id)
                        anchor = None
                        engine.add_message(
                            f"Room {rw}x{rh} queued ({len(orders)} orders).",
                            "normal")
                    break

                # ── WALL tool ──────────────────────────────────────────
                elif tool == TOOL_WALL:
                    _render()
                    d = _pick_direction(console, ctx, "Wall direction")
                    if d is not None:
                        order = bq.add_wall(cur_x, cur_y, d, wall_type)
                        undo_stack.append(order.id)
                        engine.add_message(
                            f"Wall ({WALL_TYPE_LABELS.get(wall_type, '?')}) "
                            f"queued at ({cur_x},{cur_y}) {d}.", "normal")
                    break

                # ── FLOOR tool ─────────────────────────────────────────
                elif tool == TOOL_FLOOR:
                    ft = _cur_floor_type()
                    order = bq.add_floor(cur_x, cur_y, ft)
                    undo_stack.append(order.id)
                    engine.add_message(
                        f"Floor ({FLOOR_TYPE_LABELS.get(ft, '?')}) "
                        f"queued at ({cur_x},{cur_y}).", "normal")
                    break

                # ── DOOR tool ──────────────────────────────────────────
                elif tool == TOOL_DOOR:
                    _render()
                    d = _pick_direction(console, ctx, "Door direction")
                    if d is not None:
                        # Check if there is an existing wall to replace
                        wg = getattr(lmap, "wall_grid", None)
                        existing = wg.get_edge(cur_x, cur_y, d) if wg else Edge.NONE
                        if existing not in (Edge.NONE, Edge.DOOR):
                            # Remove old wall edge, place door
                            if wg:
                                wg.remove_edge(cur_x, cur_y, d)
                            # Remove any pending wall order at this spot
                            bq.orders = [
                                o for o in bq.orders
                                if not (o.x == cur_x and o.y == cur_y
                                        and o.direction == d
                                        and o.order_type == "wall")
                            ]
                        order = bq.add_door(cur_x, cur_y, d)
                        undo_stack.append(order.id)
                        engine.add_message(
                            f"Door queued at ({cur_x},{cur_y}) {d}.",
                            "normal")
                    break

                # ── STAIRS tool ────────────────────────────────────────
                elif tool == TOOL_STAIRS:
                    _render()
                    choice = _pick_stair(console, ctx)
                    if choice is not None:
                        # Stairs are stored as floor orders with special type
                        # Use a sentinel floor type (negative, for now)
                        STAIR_FLOOR_MAP = {
                            "stairs_up":   -1,
                            "stairs_down": -2,
                            "ladder_up":   -3,
                            "ladder_down": -4,
                        }
                        st = STAIR_FLOOR_MAP.get(choice, -1)
                        order = bq.add_floor(cur_x, cur_y, st)
                        # Override material info for stairs
                        order.order_type = "stairs"
                        order.material_name = "Log"
                        order.material_qty = 2
                        order.build_minutes = 15
                        undo_stack.append(order.id)
                        engine.add_message(
                            f"{choice.replace('_', ' ').title()} queued "
                            f"at ({cur_x},{cur_y}).", "normal")
                    break

                # ── ERASE tool ─────────────────────────────────────────
                elif tool == TOOL_ERASE:
                    removed = 0
                    before = len(bq.orders)
                    bq.orders = [
                        o for o in bq.orders
                        if not (o.x == cur_x and o.y == cur_y
                                and not o.complete)
                    ]
                    removed = before - len(bq.orders)
                    if removed:
                        engine.add_message(
                            f"Erased {removed} order(s) at "
                            f"({cur_x},{cur_y}).", "normal")
                    else:
                        engine.add_message(
                            "No pending orders here.", "advisory")
                    break

            # end ENTER handling
        # end event loop -- break re-renders
