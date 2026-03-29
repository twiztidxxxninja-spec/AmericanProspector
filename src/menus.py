"""
Overlay menus: Inventory, Food, Examine, Actions (freeform input).
Each returns a result dict or None if cancelled.
Drawn over the existing console, then cleared on exit.
"""

import tcod
import tcod.event
import tcod.console
from typing import Optional, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.items import Item
    from src.player import Player
    from src.local_map import LocalMap

WHITE  = (255, 255, 255)
YELLOW = (255, 220,  60)
CYAN   = ( 80, 200, 200)
GREEN  = ( 80, 180,  80)
RED    = (220,  50,  50)
GREY   = (120, 120, 120)
DGREY  = ( 60,  60,  60)
BLACK  = (  0,   0,   0)
BG     = ( 15,  15,  30)
BG2    = ( 25,  25,  50)


def draw_box(con: tcod.console.Console, x: int, y: int, w: int, h: int,
             title: str = "", bg=BG):
    """Draw a filled box with a border and optional title."""
    con.draw_rect(x, y, w, h, ord(" "), fg=WHITE, bg=bg)
    # Border
    for bx in range(w):
        con.print(x + bx, y,         "─", fg=GREY, bg=bg)
        con.print(x + bx, y + h - 1, "─", fg=GREY, bg=bg)
    for by in range(h):
        con.print(x,         y + by, "│", fg=GREY, bg=bg)
        con.print(x + w - 1, y + by, "│", fg=GREY, bg=bg)
    con.print(x,         y,         "┌", fg=GREY, bg=bg)
    con.print(x + w - 1, y,         "┐", fg=GREY, bg=bg)
    con.print(x,         y + h - 1, "└", fg=GREY, bg=bg)
    con.print(x + w - 1, y + h - 1, "┘", fg=GREY, bg=bg)
    if title:
        con.print(x + 2, y, f" {title} ", fg=YELLOW, bg=bg)


# ── Inventory Menu ─────────────────────────────────────────────────────────

def inventory_menu(con: tcod.console.Console, ctx, player: "Player") -> Optional[dict]:
    """
    Full inventory screen. Returns {"action": "equip"/"drop"/"eat", "item": item}
    or None if closed.
    """
    W, H = 60, 40
    X = (con.width  - W) // 2
    Y = (con.height - H) // 2
    scroll = 0

    while True:
        draw_box(con, X, Y, W, H, "Inventory")

        # Weight bar
        carried = sum(i.weight * i.quantity for i in player.inventory)
        cap     = player.carry_capacity
        pct     = min(1.0, carried / cap)
        bar_w   = W - 20
        filled  = int(pct * bar_w)
        wcolor  = RED if pct > 0.9 else (YELLOW if pct > 0.75 else GREEN)
        con.print(X + 2, Y + 1,
                  f"Weight: {carried:.1f}/{cap:.0f} lb  ",
                  fg=WHITE, bg=BG)
        con.print(X + 22, Y + 1, "█" * filled + "░" * (bar_w - filled),
                  fg=wcolor, bg=BG)

        # Cash
        con.print(X + 2, Y + 2, f"Cash: ${player.cash:.2f}", fg=GREEN, bg=BG)

        # Column headers
        con.print(X + 2, Y + 3, f"{'Item':<28} {'Wt':>5} {'Val':>6}  Cat",
                  fg=GREY, bg=BG)
        con.draw_rect(X + 1, Y + 4, W - 2, 1, ord("─"), fg=DGREY, bg=BG)

        items = player.inventory
        visible_rows = H - 8
        for i, item in enumerate(items[scroll:scroll + visible_rows]):
            row = Y + 5 + i
            idx = scroll + i
            line = f"{item.display_name():<28} {item.weight*item.quantity:>5.1f} {item.base_value:>6.2f}  {item.category}"
            spoil = item.spoil_warning()
            color = RED if spoil == "spoiled" else (YELLOW if spoil else WHITE)
            con.print(X + 2, row, line[:W - 4], fg=color, bg=BG)

        # Footer
        con.draw_rect(X + 1, Y + H - 3, W - 2, 1, ord("─"), fg=DGREY, bg=BG)
        con.print(X + 2, Y + H - 2,
                  "↑↓ scroll   Esc close",
                  fg=GREY, bg=BG)

        ctx.present(con)

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return None
            if isinstance(event, tcod.event.KeyDown):
                if event.repeat:
                    continue
                sym = event.sym
                K   = tcod.event.KeySym
                if sym == K.ESCAPE or sym == K.i:
                    return None
                if sym in (K.DOWN, K.KP_2) and scroll < len(items) - visible_rows:
                    scroll += 1
                if sym in (K.UP, K.KP_8) and scroll > 0:
                    scroll -= 1


# ── Food Quick Menu ─────────────────────────────────────────────────────────

def food_menu(con: tcod.console.Console, ctx, player: "Player") -> Optional[dict]:
    """Quick eat/drink menu. Returns {"ate": item, "drank": item} or None."""
    from src.items import sort_food_by_perishability
    W, H = 44, 24
    X = (con.width  - W) // 2
    Y = (con.height - H) // 2
    selected = 0

    food  = sort_food_by_perishability(player.inventory)
    drink = [i for i in player.inventory if i.is_drink()]

    all_items = food + drink
    if not all_items:
        # Draw a quick message and return
        draw_box(con, X, Y, W, 6, "Food & Drink")
        con.print(X + 2, Y + 2, "You have nothing to eat or drink.", fg=RED, bg=BG)
        con.print(X + 2, Y + 3, "Press any key.", fg=GREY, bg=BG)
        ctx.present(con)
        for event in tcod.event.wait():
            if isinstance(event, (tcod.event.KeyDown, tcod.event.Quit)):
                return None
        return None

    while True:
        draw_box(con, X, Y, W, H, "Food & Drink")

        # Stat bars
        s = player.survival
        con.print(X + 2, Y + 1, f"Hunger {s.bar('hunger', 8)}  Thirst {s.bar('thirst', 8)}",
                  fg=WHITE, bg=BG)

        con.print(X + 2, Y + 3, f"{'Item':<24} {'Nutr':>4} {'Hyd':>4}", fg=GREY, bg=BG)
        con.draw_rect(X + 1, Y + 4, W - 2, 1, ord("─"), fg=DGREY, bg=BG)

        visible = H - 8
        for i, item in enumerate(all_items[:visible]):
            row = Y + 5 + i
            nutr = f"{item.nutrition:.0f}" if item.nutrition else "  - "
            hydr = f"{item.hydration:.0f}" if item.hydration else "  - "
            spoil = item.spoil_warning()
            color = RED if spoil == "spoiled" else (YELLOW if spoil else WHITE)
            prefix = ">" if i == selected else " "
            bg2 = BG2 if i == selected else BG
            con.print(X + 2, row,
                      f"{prefix} {item.display_name():<23} {nutr:>4} {hydr:>4}",
                      fg=color, bg=bg2)

        con.draw_rect(X + 1, Y + H - 3, W - 2, 1, ord("─"), fg=DGREY, bg=BG)
        con.print(X + 2, Y + H - 2,
                  "↑↓ select   Enter consume   Esc cancel",
                  fg=GREY, bg=BG)
        ctx.present(con)

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return None
            if isinstance(event, tcod.event.KeyDown):
                if event.repeat:
                    continue
                sym = event.sym
                K   = tcod.event.KeySym
                if sym == K.ESCAPE or sym == K.f:
                    return None
                if sym in (K.DOWN, K.KP_2):
                    selected = min(selected + 1, len(all_items) - 1)
                if sym in (K.UP, K.KP_8):
                    selected = max(selected - 1, 0)
                if sym in (K.RETURN, K.KP_ENTER):
                    return {"consumed": all_items[selected]}


# ── Examine ─────────────────────────────────────────────────────────────────

TERRAIN_DESC = {}   # populated below to avoid re-import cost

def _terrain_desc_map():
    from src.local_map import LocalTerrain
    return {
        LocalTerrain.GROUND:     "Bare earth. Packed dirt and small stones.",
        LocalTerrain.GRASS:      "A patch of grass and low vegetation.",
        LocalTerrain.FOREST:     "Dense timber. Fir and pine crowd together overhead.",
        LocalTerrain.ROCK:       "Solid rock. The mountain's bones showing through.",
        LocalTerrain.WATER:      "Running water. Clear and cold from the snowmelt upstream.",
        LocalTerrain.GRAVEL_BAR: "A gravel bar along the water's edge. Gold settles in gravel like this.",
        LocalTerrain.BEDROCK:    "Exposed bedrock. Gold sinks into the cracks and pockets in bedrock.",
        LocalTerrain.MUD:        "Soft mud. Your boot sinks an inch.",
        LocalTerrain.SAND:       "Coarse sand, likely deposited by high water.",
        LocalTerrain.BRUSH:      "Dense brush. Hard to move through quietly.",
    }


def _describe_tile(tile, player, W: int) -> List[str]:
    """Return word-wrapped description lines for a tile."""
    from src.local_map import LocalTerrain
    tmap = _terrain_desc_map()
    desc = tmap.get(tile.terrain, "Nothing remarkable.")
    geo = player.skills.get("geology", 0)
    if tile.terrain == LocalTerrain.GRAVEL_BAR and geo >= 2:
        desc += " Fine black sand mixed in — the composition looks favorable."
    if tile.terrain == LocalTerrain.BEDROCK and geo >= 3:
        desc += " The cracks run perpendicular to the old streamflow — natural gold traps."
    words = desc.split()
    line, lines = "", []
    for w in words:
        if len(line) + len(w) + 1 <= W - 4:
            line = (line + " " + w).strip()
        else:
            lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


def _look_direction(dx: int, dy: int, player, local_map, fov_radius: int = 14) -> str:
    """
    Scan in direction (dx,dy) from player up to fov_radius tiles.
    Return a natural-language summary of notable features seen.
    """
    from src.local_map import LocalTerrain

    DIR_NAMES = {
        ( 0,-1): "north",   ( 0, 1): "south",
        (-1, 0): "west",    ( 1, 0): "east",
        (-1,-1): "northwest",(1,-1): "northeast",
        (-1, 1): "southwest",(1, 1): "southeast",
    }
    direction = DIR_NAMES.get((dx, dy), "that direction")

    seen_terrains: dict = {}   # terrain -> closest distance
    water_dist   = None
    gravel_dist  = None
    bedrock_dist = None
    forest_count = 0
    rock_count   = 0

    for dist in range(1, fov_radius + 1):
        tx = player.local_x + dx * dist
        ty = player.local_y + dy * dist
        if not local_map.in_bounds(tx, ty):
            break
        tile = local_map.tile_at(tx, ty)
        if not tile.visible and not tile.explored:
            break   # can't see past unexplored
        t = tile.terrain
        if t not in seen_terrains:
            seen_terrains[t] = dist
        if t == LocalTerrain.WATER and water_dist is None:
            water_dist = dist
        if t == LocalTerrain.GRAVEL_BAR and gravel_dist is None:
            gravel_dist = dist
        if t == LocalTerrain.BEDROCK and bedrock_dist is None:
            bedrock_dist = dist
        if t == LocalTerrain.FOREST:
            forest_count += 1
        if t == LocalTerrain.ROCK:
            rock_count += 1

    if not seen_terrains:
        return f"You can't see much to the {direction}."

    parts = []
    if water_dist is not None:
        dist_word = "just ahead" if water_dist <= 3 else \
                    "nearby" if water_dist <= 6 else "in the distance"
        parts.append(f"water {dist_word}")
    if gravel_dist is not None:
        dist_word = "right at the edge" if gravel_dist <= 3 else "nearby"
        parts.append(f"a gravel bar {dist_word}")
    if bedrock_dist is not None:
        parts.append("exposed bedrock")
    if forest_count > 5:
        parts.append("heavy timber")
    elif forest_count > 2:
        parts.append("scattered trees")
    if rock_count > 6:
        parts.append("rocky ground")

    geo = player.skills.get("geology", 0)
    if geo >= 2 and gravel_dist is not None:
        parts.append("(gravel looks worth sampling)")
    if geo >= 3 and bedrock_dist is not None:
        parts.append("(bedrock exposure — check the crevices)")

    if parts:
        return f"To the {direction}: {', '.join(parts)}."
    else:
        dominant = max(seen_terrains, key=seen_terrains.get)
        tmap = _terrain_desc_map()
        short = tmap.get(dominant, "open ground")[:40]
        return f"To the {direction}: {short.lower()}"


def examine_menu(con: tcod.console.Console, ctx, player: "Player",
                 local_map: "LocalMap", npc_mgr=None, wildlife_mgr=None) -> None:
    """
    Examine mode. Two sub-modes:
      - Directional look: press a compass direction key for a broad description
      - Cursor mode: move cursor tile by tile for detail
    """
    from src.local_map import LOCAL_GLYPH, LocalTerrain

    cx, cy   = player.local_x, player.local_y
    cursor   = False          # False = directional mode, True = cursor mode
    look_msg = ""             # last directional look result

    BOX_W = 78
    BOX_H = 8
    BOX_X = 1
    BOX_Y = con.height - BOX_H - 1

    # Compass layout drawn in the box
    COMPASS = [
        " NW  N  NE ",
        "  W  +  E  ",
        " SW  S  SE ",
    ]
    # Direction key to (dx,dy)
    DIR_KEYS_KP = {
        tcod.event.KeySym.KP_7: (-1,-1), tcod.event.KeySym.KP_8: ( 0,-1),
        tcod.event.KeySym.KP_9: ( 1,-1), tcod.event.KeySym.KP_4: (-1, 0),
        tcod.event.KeySym.KP_6: ( 1, 0), tcod.event.KeySym.KP_1: (-1, 1),
        tcod.event.KeySym.KP_2: ( 0, 1), tcod.event.KeySym.KP_3: ( 1, 1),
    }
    DIR_KEYS_ARROW = {
        tcod.event.KeySym.UP:    ( 0,-1), tcod.event.KeySym.DOWN:  ( 0, 1),
        tcod.event.KeySym.LEFT:  (-1, 0), tcod.event.KeySym.RIGHT: ( 1, 0),
    }

    while True:
        draw_box(con, BOX_X, BOX_Y, BOX_W, BOX_H, "Examine")

        if not cursor:
            # ── Directional mode ──
            # Draw compass rose
            for i, row in enumerate(COMPASS):
                con.print(BOX_X + 2, BOX_Y + 1 + i, row, fg=CYAN, bg=BG)

            if look_msg:
                # Word-wrap look message
                words = look_msg.split()
                line, lines = "", []
                for w in words:
                    if len(line) + len(w) + 1 <= BOX_W - 18:
                        line = (line + " " + w).strip()
                    else:
                        lines.append(line)
                        line = w
                if line:
                    lines.append(line)
                for i, ln in enumerate(lines[:4]):
                    con.print(BOX_X + 16, BOX_Y + 1 + i, ln, fg=WHITE, bg=BG)
            else:
                con.print(BOX_X + 16, BOX_Y + 2,
                          "Press a direction key", fg=GREY, bg=BG)
                con.print(BOX_X + 16, BOX_Y + 3,
                          "to look that way.", fg=GREY, bg=BG)

            con.draw_rect(BOX_X + 1, BOX_Y + BOX_H - 3, BOX_W - 2, 1,
                          ord("─"), fg=DGREY, bg=BG)
            con.print(BOX_X + 2, BOX_Y + BOX_H - 2,
                      "Arrow/numpad look   C cursor mode   Esc/E close",
                      fg=GREY, bg=BG)
        else:
            # ── Cursor mode ──
            tile  = local_map.tile_at(cx, cy)
            glyph, fg, bg = LOCAL_GLYPH.get(tile.terrain, ("?", WHITE, BLACK))
            tname = {v: k for k, v in vars(LocalTerrain).items()
                     if not k.startswith("_")}.get(tile.terrain, "Unknown")

            con.print(BOX_X + 2, BOX_Y + 1,
                      f"[{cx},{cy}] {tname.title()}", fg=YELLOW, bg=BG)

            if not tile.explored:
                con.print(BOX_X + 2, BOX_Y + 2,
                          "You can't see that far.", fg=GREY, bg=BG)
            else:
                lines = _describe_tile(tile, player, BOX_W)
                # Check for NPC at cursor position
                if npc_mgr:
                    npc_at = npc_mgr.get_at(cx, cy, z=player.local_z)
                    if npc_at and npc_at.alive:
                        lines.append(f"{npc_at.display_name()} — {npc_at.occupation}, "
                                     f"{npc_at.rel_label()}")
                # Check for animal at cursor position
                if wildlife_mgr:
                    animal_at = wildlife_mgr.get_at(
                        player.world_x, player.world_y, cx, cy,
                        lz=player.local_z)
                    if animal_at and animal_at.alive:
                        lines.append(f"{animal_at.species.display_name} — "
                                     f"{animal_at.state}")
                # Blood
                blood = getattr(tile, "blood", 0)
                if blood >= 2:
                    lines.append("The ground is dark with blood.")
                elif blood == 1:
                    lines.append("Blood spatters on the ground.")
                # Ground items
                if tile.ground_items:
                    names = ", ".join(i.name for i in tile.ground_items[:3])
                    extra = f" +{len(tile.ground_items)-3}" if len(tile.ground_items) > 3 else ""
                    lines.append(f"Items: {names}{extra}")
                for i, ln in enumerate(lines[:6]):
                    con.print(BOX_X + 2, BOX_Y + 2 + i, ln[:BOX_W-4], fg=WHITE, bg=BG)

            # Draw cursor on map — translate map coords to viewport screen coords
            from src.constants import VIEWPORT_W, VIEWPORT_H
            scx = cx - (player.local_x - VIEWPORT_W // 2)
            scy = cy - (player.local_y - VIEWPORT_H // 2) + 1
            if 0 <= scx < VIEWPORT_W and 0 <= scy < VIEWPORT_H + 1:
                con.print(scx, scy, "X", fg=YELLOW, bg=bg)

            con.draw_rect(BOX_X + 1, BOX_Y + BOX_H - 3, BOX_W - 2, 1,
                          ord("─"), fg=DGREY, bg=BG)
            con.print(BOX_X + 2, BOX_Y + BOX_H - 2,
                      "Arrow keys move cursor   L directional look   Esc/E close",
                      fg=GREY, bg=BG)

        ctx.present(con)

        # Restore cursor tile after present
        if cursor:
            tile  = local_map.tile_at(cx, cy)
            glyph, fg, bg = LOCAL_GLYPH.get(tile.terrain, ("?", WHITE, BLACK))
            from src.constants import VIEWPORT_W, VIEWPORT_H
            scx = cx - (player.local_x - VIEWPORT_W // 2)
            scy = cy - (player.local_y - VIEWPORT_H // 2) + 1
            if 0 <= scx < VIEWPORT_W and 0 <= scy < VIEWPORT_H + 1:
                if tile.visible:
                    con.print(scx, scy, glyph, fg=fg, bg=bg)

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return
            if isinstance(event, tcod.event.KeyDown):
                if event.repeat:
                    continue
                sym = event.sym
                K   = tcod.event.KeySym

                if sym == K.ESCAPE or sym == K.e:
                    return

                if not cursor:
                    # Directional look
                    all_dir = {**DIR_KEYS_KP, **DIR_KEYS_ARROW}
                    if sym in all_dir:
                        dx, dy = all_dir[sym]
                        look_msg = _look_direction(dx, dy, player, local_map)
                    elif sym == K.c:
                        cursor   = True
                        look_msg = ""
                        cx, cy   = player.local_x, player.local_y
                else:
                    # Cursor movement
                    all_dir = {**DIR_KEYS_KP, **DIR_KEYS_ARROW}
                    if sym in all_dir:
                        dx, dy = all_dir[sym]
                        nx, ny = cx + dx, cy + dy
                        if local_map.in_bounds(nx, ny):
                            cx, cy = nx, ny
                    elif sym == K.l:
                        cursor   = False
                        look_msg = ""


# ── Actions (freeform text input) ──────────────────────────────────────────

def actions_menu(con: tcod.console.Console, ctx, player: "Player",
                 local_map: "LocalMap",
                 context_actions: List[str]) -> Optional[str]:
    """
    Actions overlay. All actions always shown; scroll with ↑↓.
    Returns the chosen/typed action string, or None if cancelled.
    """
    W, H  = 70, 28
    X = (con.width  - W) // 2
    Y = (con.height - H) // 2
    selected   = 0
    scroll     = 0
    text_input = ""
    input_mode = False

    VISIBLE = H - 7   # rows available for the action list

    while True:
        draw_box(con, X, Y, W, H, "Actions  [↑↓ scroll  Enter confirm  T type  Esc close]")

        # Action list (scrollable)
        for i in range(VISIBLE):
            idx = scroll + i
            if idx >= len(context_actions):
                break
            row    = Y + 1 + i
            is_sel = (not input_mode) and idx == selected
            color  = CYAN if is_sel else WHITE
            bgc    = BG2  if is_sel else BG
            con.print(X + 2, row, f"  {context_actions[idx]}"[:W - 4],
                      fg=color, bg=bgc)

        # Scroll indicator
        if len(context_actions) > VISIBLE:
            pct  = scroll / max(1, len(context_actions) - VISIBLE)
            bar_h = VISIBLE
            thumb = int(pct * (bar_h - 1))
            for i in range(bar_h):
                ch = "█" if i == thumb else "│"
                con.print(X + W - 2, Y + 1 + i, ch, fg=DGREY, bg=BG)

        # Free text input line
        input_y = Y + H - 4
        con.draw_rect(X + 1, input_y - 1, W - 2, 1, ord("─"), fg=DGREY, bg=BG)
        prompt = "Type any action: "
        caret  = "_" if input_mode else " "
        fg_in = YELLOW if input_mode else GREY
        full = f"{prompt}{text_input}{caret}"
        max_w = W - 4
        con.print(X + 2, input_y, full[:max_w], fg=fg_in, bg=BG)
        if len(full) > max_w:
            con.print(X + 2, input_y + 1, full[max_w:max_w*2], fg=fg_in, bg=BG)

        # Footer
        con.draw_rect(X + 1, Y + H - 3, W - 2, 1, ord("─"), fg=DGREY, bg=BG)
        if input_mode:
            con.print(X + 2, Y + H - 2,
                      "Type freely   Enter submit   Esc cancel",
                      fg=GREY, bg=BG)
        else:
            con.print(X + 2, Y + H - 2,
                      "↑↓ scroll   Enter confirm   T type   Esc close",
                      fg=GREY, bg=BG)

        ctx.present(con)

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return None

            if isinstance(event, tcod.event.TextInput) and input_mode:
                text_input += event.text
                continue

            if isinstance(event, tcod.event.KeyDown):
                if event.repeat:
                    continue
                sym = event.sym
                K   = tcod.event.KeySym

                if input_mode:
                    if sym == K.ESCAPE:
                        input_mode = False
                        text_input = ""
                        ctx.sdl_window.stop_text_input()
                    elif sym == K.BACKSPACE and text_input:
                        text_input = text_input[:-1]
                    elif sym in (K.RETURN, K.KP_ENTER) and text_input.strip():
                        ctx.sdl_window.stop_text_input()
                        return text_input.strip()
                else:
                    if sym == K.ESCAPE or sym == K.a:
                        return None
                    if sym in (K.DOWN, K.KP_2):
                        selected = min(selected + 1, len(context_actions) - 1)
                        if selected >= scroll + VISIBLE:
                            scroll += 1
                    if sym in (K.UP, K.KP_8):
                        selected = max(selected - 1, 0)
                        if selected < scroll:
                            scroll -= 1
                    if sym in (K.RETURN, K.KP_ENTER) and context_actions:
                        return context_actions[selected]
                    if sym == K.t:
                        input_mode = True
                        text_input = ""
                        ctx.sdl_window.start_text_input()


# ── Generic list picker ───────────────────────────────────────────────────────

def pick_from_list(con: tcod.console.Console, ctx,
                   title: str, options: list) -> Optional[int]:
    """
    Simple scrollable selection menu. Returns chosen index or None if cancelled.
    """
    if not options:
        return None

    W = min(60, con.width - 4)
    H = min(len(options) + 6, con.height - 4)
    X = (con.width  - W) // 2
    Y = (con.height - H) // 2
    selected = 0

    while True:
        draw_box(con, X, Y, W, H, title)
        visible_start = max(0, selected - (H - 6))
        for i, opt in enumerate(options[visible_start:visible_start + H - 4]):
            real_i = visible_start + i
            is_sel = real_i == selected
            color  = CYAN if is_sel else WHITE
            bgc    = BG2  if is_sel else BG
            prefix = ">" if is_sel else " "
            con.print(X + 2, Y + 2 + i, f"{prefix} {opt}"[:W - 4],
                      fg=color, bg=bgc)
        con.print(X + 2, Y + H - 2,
                  "↑↓ select   Enter confirm   Esc cancel",
                  fg=GREY, bg=BG)
        ctx.present(con)

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return None
            if isinstance(event, tcod.event.KeyDown):
                if event.repeat:
                    continue
                sym = event.sym
                K   = tcod.event.KeySym
                if sym == K.ESCAPE:
                    return None
                elif sym in (K.UP, K.KP_8):
                    selected = max(0, selected - 1)
                elif sym in (K.DOWN, K.KP_2):
                    selected = min(len(options) - 1, selected + 1)
                elif sym in (K.RETURN, K.KP_ENTER):
                    return selected


# ── Direction picker ─────────────────────────────────────────────────────────

def pick_direction_menu(con: tcod.console.Console, ctx,
                        title: str = "Which direction?") -> Optional[tuple]:
    """
    Show a small compass prompt. Returns (dx, dy) or None if cancelled.
    Used for spoil pile placement, etc.
    """
    from typing import Tuple as T
    W, H = 32, 10
    X = (con.width  - W) // 2
    Y = (con.height - H) // 2

    DIR_KEYS = {
        tcod.event.KeySym.KP_7: (-1, -1), tcod.event.KeySym.KP_8: ( 0, -1),
        tcod.event.KeySym.KP_9: ( 1, -1), tcod.event.KeySym.KP_4: (-1,  0),
        tcod.event.KeySym.KP_6: ( 1,  0), tcod.event.KeySym.KP_1: (-1,  1),
        tcod.event.KeySym.KP_2: ( 0,  1), tcod.event.KeySym.KP_3: ( 1,  1),
        tcod.event.KeySym.UP:   ( 0, -1), tcod.event.KeySym.DOWN:  ( 0,  1),
        tcod.event.KeySym.LEFT: (-1,  0), tcod.event.KeySym.RIGHT:  ( 1,  0),
    }

    draw_box(con, X, Y, W, H, title)
    con.print(X + 2, Y + 2, "Numpad or arrow keys:", fg=GREY, bg=BG)
    con.print(X + 4, Y + 4, "7  8  9", fg=CYAN, bg=BG)
    con.print(X + 4, Y + 5, "4  @  6", fg=CYAN, bg=BG)
    con.print(X + 4, Y + 6, "1  2  3", fg=CYAN, bg=BG)
    con.print(X + 2, Y + 8, "Esc — cancel dig", fg=GREY, bg=BG)
    ctx.present(con)

    while True:
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return None
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                if sym == tcod.event.KeySym.ESCAPE:
                    return None
                if sym in DIR_KEYS:
                    return DIR_KEYS[sym]
