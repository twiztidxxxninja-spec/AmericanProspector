"""
src/ui_build.py

[B] Build menu — four tabs:
    Tab 1: Equipment (sluice box, rocker, campfire, etc.)
    Tab 2: Walls & Floors (place edge walls tile by tile)
    Tab 3: Zones (designate areas)
    Tab 4: Status (build queue, repair, structure list)
"""

import tcod.event
from typing import Any, List, Tuple

from src.ui_framework import (
    TabbedMenu, MenuTab, MenuState, draw_list_item, draw_separator,
    WHITE, YELLOW, CYAN, GREEN, RED, GREY, DGREY, ORANGE, BG, BG2
)


# ============================================================================
#  TAB 1: EQUIPMENT
# ============================================================================

def _draw_equipment(con, x, y, w, h, state: MenuState, ctx: dict):
    from src.construction import EQUIPMENT_BLUEPRINTS

    con.print(x + 1, y, "BUILD EQUIPMENT", fg=YELLOW, bg=BG)
    y += 1
    con.print(x + 1, y, "Select what to build. Materials consumed on start.",
              fg=GREY, bg=BG)
    y += 2

    bps = list(EQUIPMENT_BLUEPRINTS.values())
    visible = h - 5
    for i in range(visible):
        idx = state.scroll + i
        if idx >= len(bps):
            break
        bp = bps[idx]
        sel = (idx == state.selected)
        mats = ", ".join(f"{q}x {n}" for n, q in bp.materials)
        line = f"{bp.name:<20} ({bp.build_minutes}min)"
        draw_list_item(con, x + 1, y + i, w - 2, line, sel)

    # Detail panel for selected
    if bps and state.selected < len(bps):
        bp = bps[state.selected]
        dy = y + visible + 1
        con.print(x + 1, dy, bp.description[:w - 2], fg=WHITE, bg=BG)
        dy += 1
        mats = ", ".join(f"{q}x {n}" for n, q in bp.materials)
        con.print(x + 1, dy, f"Materials: {mats}", fg=GREY, bg=BG)
        dy += 1
        tags = ", ".join(bp.functional_tags) if bp.functional_tags else "none"
        con.print(x + 1, dy, f"Functions: {tags}", fg=GREY, bg=BG)

    con.print(x + 1, y + h - 1, "Enter=Build here  T=Type custom structure",
              fg=DGREY, bg=BG)


def _handle_equipment(sym, state: MenuState, ctx: dict) -> bool:
    K = tcod.event.KeySym
    from src.construction import EQUIPMENT_BLUEPRINTS

    bps = list(EQUIPMENT_BLUEPRINTS.values())
    count = len(bps)

    if sym in (K.DOWN, K.KP_2):
        state.selected = min(state.selected + 1, count - 1)
        if state.selected >= state.scroll + 25:
            state.scroll += 1
        return True
    if sym in (K.UP, K.KP_8):
        state.selected = max(state.selected - 1, 0)
        if state.selected < state.scroll:
            state.scroll = state.selected
        return True

    if sym in (K.RETURN, K.KP_ENTER) and count > 0:
        bp = bps[state.selected]
        state.result = ("build_equipment", bp.key)
        state.should_close = True
        return True

    if sym == K.t:
        state.result = ("build_custom", "")
        state.should_close = True
        return True

    return False


# ============================================================================
#  TAB 2: WALLS & FLOORS
# ============================================================================

def _draw_walls(con, x, y, w, h, state: MenuState, ctx: dict):
    from src.construction import Edge, EDGE_LABELS, FloorType

    con.print(x + 1, y, "PLACE WALLS & FLOORS", fg=YELLOW, bg=BG)
    y += 1
    con.print(x + 1, y, "Select type, then place on the map.", fg=GREY, bg=BG)
    y += 2

    options = [
        ("Wood Wall",   "wall", Edge.WOOD_WALL),
        ("Stone Wall",  "wall", Edge.STONE_WALL),
        ("Door",        "wall", Edge.DOOR),
        ("Window",      "wall", Edge.WINDOW),
        ("Fence",       "wall", Edge.FENCE),
        ("Canvas Wall", "wall", Edge.CANVAS),
        ("Iron Bars",   "wall", Edge.IRON_BARS),
        ("",            "",     0),   # separator
        ("Wood Floor",  "floor", FloorType.WOOD_PLANK),
        ("Stone Floor", "floor", FloorType.STONE_FLAG),
        ("",            "",     0),   # separator
        ("Build Room (quick)", "room", 0),
    ]

    for i, (label, kind, val) in enumerate(options):
        if not label:
            con.print(x + 1, y + i, "", fg=DGREY, bg=BG)
            continue
        sel = (i == state.selected)
        draw_list_item(con, x + 1, y + i, w - 2, label, sel)

    # Material cost hint
    from src.construction import EDGE_MATERIALS, FLOOR_MATERIALS
    real_opts = [(l, k, v) for l, k, v in options if l]
    if state.selected < len(options):
        label, kind, val = options[state.selected]
        if kind == "wall" and val in EDGE_MATERIALS:
            mat, qty, mins = EDGE_MATERIALS[val]
            con.print(x + 1, y + len(options) + 1,
                      f"Cost per segment: {qty}x {mat}, {mins} min",
                      fg=GREY, bg=BG)
        elif kind == "floor" and val in FLOOR_MATERIALS:
            mat, qty, mins = FLOOR_MATERIALS[val]
            con.print(x + 1, y + len(options) + 1,
                      f"Cost per tile: {qty}x {mat}, {mins} min",
                      fg=GREY, bg=BG)

    con.print(x + 1, y + h - 1,
              "Enter=Start placing  (move cursor, Enter to place each piece)",
              fg=DGREY, bg=BG)


def _handle_walls(sym, state: MenuState, ctx: dict) -> bool:
    K = tcod.event.KeySym
    from src.construction import Edge, FloorType

    options = [
        ("Wood Wall",   "wall", Edge.WOOD_WALL),
        ("Stone Wall",  "wall", Edge.STONE_WALL),
        ("Door",        "wall", Edge.DOOR),
        ("Window",      "wall", Edge.WINDOW),
        ("Fence",       "wall", Edge.FENCE),
        ("Canvas Wall", "wall", Edge.CANVAS),
        ("Iron Bars",   "wall", Edge.IRON_BARS),
        ("",            "",     0),
        ("Wood Floor",  "floor", FloorType.WOOD_PLANK),
        ("Stone Floor", "floor", FloorType.STONE_FLAG),
        ("",            "",     0),
        ("Build Room",  "room", 0),
    ]

    if sym in (K.DOWN, K.KP_2):
        state.selected = min(state.selected + 1, len(options) - 1)
        while state.selected < len(options) and not options[state.selected][0]:
            state.selected += 1
        return True
    if sym in (K.UP, K.KP_8):
        state.selected = max(state.selected - 1, 0)
        while state.selected > 0 and not options[state.selected][0]:
            state.selected -= 1
        return True

    if sym in (K.RETURN, K.KP_ENTER):
        if state.selected < len(options) and options[state.selected][0]:
            label, kind, val = options[state.selected]
            state.result = ("place_mode", kind, val)
            state.should_close = True
        return True

    return False


# ============================================================================
#  TAB 3: ZONES
# ============================================================================

def _draw_zones(con, x, y, w, h, state: MenuState, ctx: dict):
    from src.construction import ZoneType, ZONE_LABELS

    con.print(x + 1, y, "DESIGNATE ZONES", fg=YELLOW, bg=BG)
    y += 1
    con.print(x + 1, y, "NPCs go to zones matching their assigned task.",
              fg=GREY, bg=BG)
    y += 2

    zone_types = list(ZONE_LABELS.items())
    for i, (ztype, zlabel) in enumerate(zone_types):
        sel = (i == state.selected)
        draw_list_item(con, x + 1, y + i, w - 2, zlabel, sel)

    # Show existing zones
    local_map = ctx.get("local_map")
    zones = getattr(local_map, "zones", []) if local_map else []
    if zones:
        zy = y + len(zone_types) + 2
        con.print(x + 1, zy, "EXISTING ZONES:", fg=GREY, bg=BG)
        zy += 1
        for z in zones:
            con.print(x + 1, zy,
                      f"  {z.label} ({z.width}x{z.height} at {z.x},{z.y})",
                      fg=WHITE, bg=BG)
            zy += 1

    con.print(x + 1, y + h - 1,
              "Enter=Start designating (move to corner, Enter, move to opposite corner, Enter)",
              fg=DGREY, bg=BG)


def _handle_zones(sym, state: MenuState, ctx: dict) -> bool:
    K = tcod.event.KeySym
    from src.construction import ZONE_LABELS

    zone_types = list(ZONE_LABELS.keys())
    count = len(zone_types)

    if sym in (K.DOWN, K.KP_2):
        state.selected = min(state.selected + 1, count - 1)
        return True
    if sym in (K.UP, K.KP_8):
        state.selected = max(state.selected - 1, 0)
        return True

    if sym in (K.RETURN, K.KP_ENTER):
        ztype = zone_types[state.selected]
        state.result = ("designate_zone", ztype)
        state.should_close = True
        return True

    return False


# ============================================================================
#  TAB 4: STATUS
# ============================================================================

def _draw_status(con, x, y, w, h, state: MenuState, ctx: dict):
    local_map = ctx.get("local_map")

    con.print(x + 1, y, "BUILD STATUS", fg=YELLOW, bg=BG)
    y += 2

    # Build queue
    queue = getattr(local_map, "build_queue", None) if local_map else None
    if queue and queue.pending():
        pending = queue.pending()
        con.print(x + 1, y, f"BUILD QUEUE: {len(pending)} tasks", fg=WHITE, bg=BG)
        y += 1
        total_time = queue.total_time_remaining()
        con.print(x + 1, y, f"Est. time: {total_time} min", fg=GREY, bg=BG)
        y += 1
        mats = queue.total_materials_needed()
        if mats:
            mat_str = ", ".join(f"{q}x {n}" for n, q in mats.items())
            con.print(x + 1, y, f"Materials needed: {mat_str}", fg=GREY, bg=BG)
            y += 1
        y += 1
        for i, order in enumerate(pending[:10]):
            pct = f"{order.progress:.0f}%"
            line = f"  {order.order_type} at ({order.x},{order.y}) {pct}"
            con.print(x + 1, y + i, line, fg=WHITE, bg=BG)
    else:
        con.print(x + 1, y, "No active build orders.", fg=GREY, bg=BG)

    y += 12

    # Placed structures
    structures = local_map.structures if local_map else {}
    if structures:
        from src.construction import PlacedEquipment
        equips = [s for s in structures.values() if isinstance(s, PlacedEquipment)]
        if equips:
            con.print(x + 1, y, f"STRUCTURES: {len(equips)}", fg=WHITE, bg=BG)
            y += 1
            for s in equips:
                status = "complete" if s.complete else f"{s.progress:.0f}%"
                cond = f" cond:{s.condition:.0f}%" if s.complete else ""
                con.print(x + 1, y,
                          f"  {s.name} ({status}{cond})", fg=WHITE, bg=BG)
                y += 1


def _handle_status(sym, state: MenuState, ctx: dict) -> bool:
    K = tcod.event.KeySym
    if sym in (K.DOWN, K.KP_2):
        state.scroll += 1
        return True
    if sym in (K.UP, K.KP_8):
        state.scroll = max(0, state.scroll - 1)
        return True
    return False


# ============================================================================
#  PUBLIC
# ============================================================================

def open_build(con, ctx, player, local_map=None, construction=None) -> Any:
    tabs = [
        MenuTab("Equipment", _draw_equipment, _handle_equipment),
        MenuTab("Walls", _draw_walls, _handle_walls),
        MenuTab("Zones", _draw_zones, _handle_zones),
        MenuTab("Status", _draw_status, _handle_status),
    ]
    menu = TabbedMenu("BUILD", tabs, width=72, height=40)
    return menu.run(con, ctx, player=player, local_map=local_map,
                     construction=construction)
