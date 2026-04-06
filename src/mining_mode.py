"""
Mining work mode — area-select, then watch your prospector work.

Two modes:
1. PAN MODE — select tiles to pan, watch player walk to each tile then to
   water and back. Gold overlay updates as results come in.
2. SLUICE MODE — select tiles to shovel, watch player walk to each tile,
   shovel material, carry to sluice, repeat. Cleanout at end.

Entered via action menu or 'M' key.
"""

import tcod
import tcod.event
import random
import time as _pytime
from typing import List, Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine import Engine

from src.local_map import LocalTerrain


# ── Pannable terrain ─────────────────────────────────────────────────────

_PANNABLE = frozenset([
    LocalTerrain.GRAVEL_BAR, LocalTerrain.WATER,
    LocalTerrain.WORKED_GRAVEL, LocalTerrain.WORKED_DIRT,
    LocalTerrain.MUD, LocalTerrain.SAND,
])

# Shovelable — same as pannable plus some extras, but NOT bedrock (needs pick)
_SHOVELABLE = frozenset([
    LocalTerrain.GRAVEL_BAR, LocalTerrain.GROUND, LocalTerrain.GRASS,
    LocalTerrain.MUD, LocalTerrain.SAND,
    LocalTerrain.WORKED_GRAVEL, LocalTerrain.WORKED_DIRT,
])

# Bedrock requires pickaxe — rich gold but hard work
_BEDROCK = frozenset([LocalTerrain.BEDROCK])


# ── Helpers ──────────────────────────────────────────────────────────────

def _find_water(lmap, px, py, radius=20) -> Optional[Tuple[int, int]]:
    """Find nearest water tile within radius. Extended range — player walks."""
    best, best_d = None, 999
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            tx, ty = px + dx, py + dy
            if lmap.in_bounds(tx, ty) and lmap.tiles[ty][tx].terrain == LocalTerrain.WATER:
                d = abs(dx) + abs(dy)
                if d < best_d:
                    best_d = d
                    best = (tx, ty)
    return best


def _check_danger(engine) -> Optional[str]:
    """Check for nearby hostiles AND survival needs. Returns warning or None."""
    # Survival checks — stop working when player needs to eat/drink/rest
    s = engine.player.survival
    if s.fatigue <= 10:
        return "You're exhausted. Rest before continuing."
    if s.hunger <= 10:
        return "You're starving. Eat something."
    if s.thirst <= 10:
        return "You're dangerously dehydrated. Drink."
    if s.health <= 20:
        return "You're badly hurt. Stop working."
    if s.drunk_level >= 8:
        return "You're too drunk to work safely."

    px, py = engine.player.local_x, engine.player.local_y
    # Hostile NPCs
    for npc in engine._tile_npcs():
        if not npc.alive or not npc.present:
            continue
        if npc.combat_state == "hostile":
            d = max(abs(npc.local_x - px), abs(npc.local_y - py))
            if d <= 15:
                return f"{npc.name} is hostile and approaching!"
    # Hostile or dangerous animals
    animals = engine.wildlife_mgr.get_animals(
        engine.player.world_x, engine.player.world_y,
        engine.player.area_x, engine.player.area_y)
    for a in animals:
        if not a.alive:
            continue
        d = max(abs(a.local_x - px), abs(a.local_y - py))
        if a.state == "hostile" and d <= 10:
            return f"A {a.species.display_name} is attacking!"
        if a.species.danger_level >= 2 and d <= 8:
            return f"A {a.species.display_name} is dangerously close!"
    return None


def _walk_to(engine, console, ctx, tx, ty, lmap, delay=0.06):
    """Animate player walking tile-by-tile to target.
    Returns: True=arrived, False=blocked, None=cancelled/danger."""
    while engine.player.local_x != tx or engine.player.local_y != ty:
        dx = (1 if tx > engine.player.local_x else
              -1 if tx < engine.player.local_x else 0)
        dy = (1 if ty > engine.player.local_y else
              -1 if ty < engine.player.local_y else 0)
        nx = engine.player.local_x + dx
        ny = engine.player.local_y + dy
        if not lmap.in_bounds(nx, ny) or not lmap.is_passable(nx, ny):
            if dx != 0 and dy != 0:
                if lmap.in_bounds(engine.player.local_x + dx, engine.player.local_y) and \
                        lmap.is_passable(engine.player.local_x + dx, engine.player.local_y):
                    ny = engine.player.local_y
                elif lmap.in_bounds(engine.player.local_x, engine.player.local_y + dy) and \
                        lmap.is_passable(engine.player.local_x, engine.player.local_y + dy):
                    nx = engine.player.local_x
                else:
                    return False
            else:
                return False
        engine.player.local_x = nx
        engine.player.local_y = ny
        engine.player.local_z = lmap.ground_z(nx, ny)
        engine.time.advance_seconds(3)
        engine.recompute_fov()
        engine.renderer.render_all(
            lmap, engine.world, engine.player, engine.messages,
            state="local_map", locals_dict=engine.locals,
            gold_overlay=engine.show_gold_overlay)
        ctx.present(console)
        _pytime.sleep(delay)
        # Check for ESC to cancel
        for ev in tcod.event.get():
            if isinstance(ev, tcod.event.KeyDown):
                if ev.sym == tcod.event.KeySym.ESCAPE:
                    return None
        # Check for danger
        danger = _check_danger(engine)
        if danger:
            engine.add_message(f"DANGER: {danger}", "critical")
            engine.add_message("Auto-work paused. [ESC] to exit.", "advisory")
            return None
    return True


# ── Entry point ──────────────────────────────────────────────────────────

def enter_mining_mode(engine: "Engine", console, ctx) -> None:
    """Enter gold mode — player picks pan or sluice, then selects area."""
    lmap = engine.current_local
    px, py = engine.player.local_x, engine.player.local_y

    sluice = engine._nearby_structure("pan_gold", radius=15)
    water = _find_water(lmap, px, py, radius=20)

    has_pan = any("pan" in getattr(i, "tool_tags", []) for i in engine.player.inventory)
    has_shovel = any("dig" in getattr(i, "tool_tags", []) for i in engine.player.inventory)
    has_pick = any("break_rock" in getattr(i, "tool_tags", []) for i in engine.player.inventory)

    if not water:
        engine.add_message("No water nearby. Find a stream.", "advisory")
        return
    if not has_pan and not has_shovel:
        engine.add_message("You need a gold pan or a shovel.", "advisory")
        return

    # Build available mode options
    modes = []
    if has_pan:
        modes.append(("Pan gold (hand pan at water)", "pan"))
    if sluice and has_shovel:
        sluice_name = sluice.name
        modes.append((f"Sluice ({sluice_name})", "sluice"))

    if len(modes) == 1:
        chosen_mode = modes[0][1]
    else:
        from src.menus import pick_from_list
        labels = [m[0] for m in modes]
        idx = pick_from_list(console, ctx, "Gold Mode", labels)
        if idx is None:
            return
        chosen_mode = modes[idx][1]

    _select_and_work(engine, console, ctx, mode=chosen_mode,
                     sluice=sluice if chosen_mode == "sluice" else None,
                     water_pos=water, has_pick=has_pick)


# ── Area selection + auto-work ───────────────────────────────────────────

def _select_and_work(engine: "Engine", console, ctx,
                     mode: str = "pan",
                     sluice=None, water_pos=None,
                     has_pick: bool = False) -> None:
    """
    Phase 1: Cursor-driven area selection. Mark tiles to work.
    Phase 2: Auto-work — watch player walk to each tile and work it.
    """
    engine.music.set_category("work")
    from src.constants import VIEWPORT_W, VIEWPORT_H

    lmap = engine.current_local
    px, py = engine.player.local_x, engine.player.local_y
    cur_x, cur_y = px, py
    cur_z = engine.player.local_z   # cursor z-level

    # Restore previous selection if re-entering gold mode
    prev = getattr(engine, '_gold_mode_selection', None)
    if prev:
        selected: List[Tuple[int, int, int]] = list(prev)
        engine.add_message(
            f"Previous selection restored ({len(selected)} tiles).", "normal")
    else:
        selected: List[Tuple[int, int, int]] = []

    rect_anchor = None  # (x, y) for rectangle drag start
    K = tcod.event.KeySym

    MOVES = {
        K.UP: (0, -1), K.DOWN: (0, 1), K.LEFT: (-1, 0), K.RIGHT: (1, 0),
        K.KP_8: (0, -1), K.KP_2: (0, 1), K.KP_4: (-1, 0), K.KP_6: (1, 0),
        K.KP_7: (-1, -1), K.KP_9: (1, -1), K.KP_1: (-1, 1), K.KP_3: (1, 1),
    }

    mode_label = "PAN" if mode == "pan" else "SLUICE"

    def _is_workable(tx, ty, tz):
        """Check if tile at position is workable."""
        if not lmap.in_bounds(tx, ty):
            return False
        _sz = int(lmap.surface_z[ty][tx])
        _t = lmap.tile_at(tx, ty)
        _zt = None
        if tz < _sz:
            _zt = lmap.z_tiles.get((tx, ty, tz))
        _ter = _zt.terrain if _zt else _t.terrain
        return (_ter in _PANNABLE or _ter in _SHOVELABLE or
                (_ter in _BEDROCK and has_pick))

    # ── Phase 1: Selection ───────────────────────────────────────────
    while True:
        half_w = VIEWPORT_W // 2
        half_h = VIEWPORT_H // 2
        cam_x = px - half_w
        cam_y = py - half_h

        engine.renderer.render_all(
            lmap, engine.world, engine.player, engine.messages,
            state="local_map", locals_dict=engine.locals,
            gold_overlay=True)

        # Draw selected tiles
        for sx, sy, sz in selected:
            scr_x = sx - cam_x
            scr_y = sy - cam_y + 1
            if 0 <= scr_x < VIEWPORT_W and 1 <= scr_y < VIEWPORT_H + 1:
                console.print(scr_x, scr_y, "#",
                              fg=(50, 255, 50), bg=(20, 60, 20))

        # Draw rectangle preview if dragging
        if rect_anchor:
            ax, ay = rect_anchor
            rx1, rx2 = min(ax, cur_x), max(ax, cur_x)
            ry1, ry2 = min(ay, cur_y), max(ay, cur_y)
            for ry in range(ry1, ry2 + 1):
                for rx in range(rx1, rx2 + 1):
                    scr_x = rx - cam_x
                    scr_y = ry - cam_y + 1
                    if 0 <= scr_x < VIEWPORT_W and 1 <= scr_y < VIEWPORT_H + 1:
                        if (rx, ry, cur_z) not in selected:
                            console.print(scr_x, scr_y, ".",
                                          fg=(50, 200, 50), bg=(15, 40, 15))

        # Draw cursor
        scr_cx = cur_x - cam_x
        scr_cy = cur_y - cam_y + 1
        if 0 <= scr_cx < VIEWPORT_W and 1 <= scr_cy < VIEWPORT_H + 1:
            console.print(scr_cx, scr_cy, "X",
                          fg=(255, 255, 0), bg=(60, 60, 20))

        # HUD — check terrain at cursor position + z-level
        surface_z = int(lmap.surface_z[cur_y][cur_x]) if lmap.in_bounds(cur_x, cur_y) else 0
        tile = lmap.tile_at(cur_x, cur_y)
        ztile = None
        if cur_z < surface_z:
            ztile = lmap.z_tiles.get((cur_x, cur_y, cur_z))
        check_terrain = ztile.terrain if ztile else tile.terrain
        dig_depth = getattr(tile, 'dig_depth', 0)

        terrain_ok = check_terrain in _PANNABLE or check_terrain in _SHOVELABLE
        bedrock = check_terrain in _BEDROCK

        # Clear sidebar area
        for _hy in range(8, 26):
            console.print(82, _hy, " " * 36, fg=(0, 0, 0), bg=(0, 0, 0))

        console.print(82, 8, f"── {mode_label} MODE ──────────",
                      fg=(255, 200, 50))
        console.print(82, 9, "SELECT WORK AREA", fg=(200, 200, 200))
        console.print(82, 10, f"Selected: {len(selected)} tiles",
                      fg=(100, 255, 100))

        z_label = "surface" if cur_z == surface_z else f"{(surface_z - cur_z) * 3}ft down"
        console.print(82, 11, f"Depth: {z_label}  (dig: {dig_depth})",
                      fg=(180, 180, 200))

        status = ("PANNABLE" if terrain_ok else
                  "BEDROCK (need pick)" if bedrock and not has_pick else
                  "BEDROCK (pickaxe)" if bedrock else "not workable")
        status_fg = ((100, 255, 100) if terrain_ok else
                     (255, 200, 100) if bedrock else (255, 80, 80))
        console.print(82, 12, f"Cursor: {status}", fg=status_fg)

        if rect_anchor:
            ax, ay = rect_anchor
            rw = abs(cur_x - ax) + 1
            rh = abs(cur_y - ay) + 1
            console.print(82, 13, f"Rectangle: {rw}x{rh}",
                          fg=(50, 200, 50))

        # Water/sluice distance
        if water_pos:
            wd = abs(water_pos[0] - px) + abs(water_pos[1] - py)
            console.print(82, 20, f"Water: {wd * 5}ft",
                          fg=(80, 140, 200))
        if sluice:
            sd = abs(sluice.x - px) + abs(sluice.y - py)
            console.print(82, 21, f"Sluice: {sd * 5}ft",
                          fg=(200, 160, 80))

        can_pan = any("pan" in getattr(i, "tool_tags", [])
                      for i in engine.player.inventory)
        can_sluice = sluice is not None and any(
            "dig" in getattr(i, "tool_tags", [])
            for i in engine.player.inventory)
        can_switch = (can_pan and can_sluice)

        y_ctrl = 15
        console.print(82, y_ctrl, "[SPACE] Toggle tile", fg=(150, 150, 150))
        y_ctrl += 1
        console.print(82, y_ctrl, "[S] Start rect  [D] Deselect tile",
                      fg=(150, 150, 150))
        y_ctrl += 1
        console.print(82, y_ctrl, "[ENTER] Start working", fg=(150, 150, 150))
        y_ctrl += 1
        console.print(82, y_ctrl, "[arrows] Move  [</>] Z-level",
                      fg=(150, 150, 150))
        y_ctrl += 1
        if can_switch:
            other = "SLUICE" if mode == "pan" else "PAN"
            console.print(82, y_ctrl, f"[TAB] Switch to {other}",
                          fg=(150, 150, 150))
            y_ctrl += 1
        console.print(82, y_ctrl, "[R] Dig ramp  [C] Clear all",
                      fg=(150, 150, 150))
        y_ctrl += 1
        console.print(82, y_ctrl, "[ESC] Cancel", fg=(150, 150, 150))

        ctx.present(console)

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                raise SystemExit()
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym

                if sym == K.ESCAPE:
                    # Save selection for re-entry
                    engine._gold_mode_selection = list(selected) if selected else None
                    return

                if sym in MOVES:
                    dx, dy = MOVES[sym]
                    nx, ny = cur_x + dx, cur_y + dy
                    if lmap.in_bounds(nx, ny):
                        cur_x, cur_y = nx, ny
                    break

                # Switch pan/sluice mode
                if sym == K.TAB and can_switch:
                    mode = "sluice" if mode == "pan" else "pan"
                    mode_label = "PAN" if mode == "pan" else "SLUICE"
                    break

                # Toggle single tile
                if sym == K.SPACE:
                    pos = (cur_x, cur_y, cur_z)
                    if _is_workable(cur_x, cur_y, cur_z):
                        if pos in selected:
                            selected.remove(pos)
                        else:
                            selected.append(pos)
                    break

                # Deselect single tile under cursor
                if sym == K.d:
                    pos = (cur_x, cur_y, cur_z)
                    if pos in selected:
                        selected.remove(pos)
                    break

                # Rectangle select: S starts anchor, S again completes
                if sym == K.s:
                    if rect_anchor is None:
                        rect_anchor = (cur_x, cur_y)
                    else:
                        # Complete rectangle — add all workable tiles
                        ax, ay = rect_anchor
                        rx1, rx2 = min(ax, cur_x), max(ax, cur_x)
                        ry1, ry2 = min(ay, cur_y), max(ay, cur_y)
                        added = 0
                        for ry in range(ry1, ry2 + 1):
                            for rx in range(rx1, rx2 + 1):
                                pos = (rx, ry, cur_z)
                                if pos not in selected and \
                                        _is_workable(rx, ry, cur_z):
                                    selected.append(pos)
                                    added += 1
                        rect_anchor = None
                        engine.add_message(
                            f"Selected {added} tiles in rectangle.", "normal")
                    break

                # Clear all selections (including saved)
                if sym == K.c:
                    selected.clear()
                    rect_anchor = None
                    engine._gold_mode_selection = None
                    engine.add_message("Selection cleared.", "normal")
                    break

                # Z-level cursor
                if sym == K.COMMA or sym == K.LESS:
                    if cur_z < surface_z:
                        cur_z += 1
                    break
                if sym == K.PERIOD or sym == K.GREATER:
                    if dig_depth > 0 and cur_z > surface_z - dig_depth:
                        cur_z -= 1
                    break

                # Dig ramp
                if sym == K.r:
                    if dig_depth == 0:
                        engine.add_message("No pit here to ramp out of.",
                                           "advisory")
                        break
                    from src.menus import pick_from_list
                    dirs = ["North", "South", "East", "West"]
                    d_vecs = [(0, -1), (0, 1), (1, 0), (-1, 0)]
                    didx = pick_from_list(console, ctx,
                        "Dig ramp which direction?", dirs)
                    if didx is not None:
                        rdx, rdy = d_vecs[didx]
                        ramp_x = cur_x + rdx
                        ramp_y = cur_y + rdy
                        if lmap.in_bounds(ramp_x, ramp_y):
                            ramp_tile = lmap.tile_at(ramp_x, ramp_y)
                            if ramp_tile.terrain not in (
                                    LocalTerrain.WATER, LocalTerrain.ROCK):
                                lmap.surface_z[ramp_y][ramp_x] = max(
                                    surface_z - 1,
                                    int(lmap.surface_z[ramp_y][ramp_x]) - 1)
                            lmap.invalidate_terrain_cache()
                            engine.add_message(
                                f"You dig a ramp {dirs[didx].lower()} "
                                f"out of the pit.", "normal")
                            engine.advance_time(20)
                            engine.player.gain_skill_xp("placer", 1.0)
                        else:
                            engine.add_message("Can't dig there.", "advisory")
                    break

                # Start working
                if sym in (K.RETURN, K.KP_ENTER):
                    if not selected:
                        engine.add_message(
                            "Select tiles first. [SPACE] or [S] rect.",
                            "advisory")
                        break
                    work_tiles = [(x, y) for x, y, z in selected]
                    if mode == "pan":
                        remaining = _auto_pan(engine, console, ctx,
                                              work_tiles, water_pos, has_pick)
                    else:
                        remaining = _auto_sluice(engine, console, ctx,
                                                 work_tiles, sluice,
                                                 water_pos, has_pick)
                    # Save unworked tiles for re-entry
                    if remaining:
                        engine._gold_mode_selection = [
                            (x, y, cur_z) for x, y in remaining]
                    else:
                        engine._gold_mode_selection = None
                    return
                break


# ── Auto-pan ─────────────────────────────────────────────────────────────

def _auto_pan(engine: "Engine", console, ctx,
              tiles: List[Tuple[int, int]],
              water_pos: Tuple[int, int],
              has_pick: bool) -> List[Tuple[int, int]]:
    """Auto-pan selected tiles. Returns list of unworked tiles if interrupted."""
    from src.prospecting import pan_for_gold, depletion_message, tile_grade_label
    from src.nugget_system import NuggetSystem
    from src.volume_gold import VolumeGoldSystem

    lmap = engine.current_local
    total_gold = 0.0
    pan_count = 0
    rng = random.Random()
    wx, wy = water_pos
    remaining = list(tiles)  # track unworked tiles

    engine.add_message(
        f"You start panning {len(tiles)} tiles. Watch and wait...", "normal")

    for tile_idx, (tx, ty) in enumerate(tiles):
        tile = lmap.tile_at(tx, ty)

        # Walk to work tile
        walk = _walk_to(engine, console, ctx, tx, ty, lmap)
        if walk is None:
            # Interrupted — return remaining unworked tiles
            value = total_gold * 20.67 * 0.9
            if pan_count > 0:
                engine.add_message(
                    f"Stopped. {pan_count} pans so far, "
                    f"{total_gold:.4f} oz (${value:.2f}).", "normal")
            engine.show_gold_overlay = True
            return remaining
        if walk is False:
            remaining.remove((tx, ty))
            continue

        # Bedrock needs pickaxe work first
        if tile.terrain in _BEDROCK:
            if not has_pick:
                continue
            engine.add_message("You chip at the bedrock crevices with your pickaxe...", "normal")
            engine.time.advance_seconds(15 * 60)
            engine.player.gain_skill_xp("geology", 2.0)
            tile.gold_grade = max(tile.gold_grade, lmap._gold_bias * 1.5)

        # Lazy gold column
        if tile.gold_column is None:
            _col_bias = max(tile.gold_grade, lmap._gold_bias * 0.5)
            _col_rng = random.Random(lmap.seed + tx * 100 + ty)
            tile.gold_column = VolumeGoldSystem.create_column(
                lmap._region_name, _col_bias, _col_rng)

        tile.gold_grade = max(tile.gold_column.get_current_grade(), 0.001)
        VolumeGoldSystem.pan_volume(
            tile.gold_column,
            placer_skill=engine.player.skills.get("placer", 0))

        # Pan calculation done HERE while standing on the work tile
        # (pan_for_gold reads gold_grade from player's current position)
        result = pan_for_gold(engine.player, lmap)

        # Walk to water to wash (visual only — gold already calculated)
        walk = _walk_to(engine, console, ctx, wx, wy, lmap, delay=0.04)
        if walk is None:
            value = total_gold * 20.67 * 0.9
            if pan_count > 0:
                engine.add_message(
                    f"Stopped. {pan_count} pans so far, "
                    f"{total_gold:.4f} oz (${value:.2f}).", "normal")
            engine.show_gold_overlay = True
            return remaining
        if walk is False:
            engine.add_message("Can't reach water. Stopping.", "advisory")
            engine.show_gold_overlay = True
            return remaining
        # Tile completed — remove from remaining
        if (tx, ty) in remaining:
            remaining.remove((tx, ty))
        engine.player.gold_oz += result.gold_oz
        total_gold += result.gold_oz
        pan_count += 1
        engine.player.gain_skill_xp("placer", result.xp_placer)
        engine.player.gain_skill_xp("geology", result.xp_geology)
        # Pan wash time only — walking to/from water handled by _walk_to
        # result.time_minutes is the full old-style cycle (10-20 min);
        # subtract walking overhead since that's now separate
        wash_time = max(5, result.time_minutes - 5)
        engine.time.advance_seconds(wash_time * 60)
        tile.panned = True

        # Terrain change
        if tile.terrain == LocalTerrain.GRAVEL_BAR:
            tile.terrain = LocalTerrain.WORKED_GRAVEL
        elif tile.terrain in (LocalTerrain.GROUND, LocalTerrain.GRASS,
                              LocalTerrain.MUD, LocalTerrain.SAND):
            tile.terrain = LocalTerrain.WORKED_DIRT
        lmap.invalidate_terrain_cache()

        engine.add_message(result.message, "normal")

        # Nugget
        nugget = NuggetSystem.roll_nugget(
            dig_depth=getattr(tile, 'dig_depth', 0),
            gold_grade=tile.gold_grade,
            region_name=lmap.world_map.get_region(lmap.world_x, lmap.world_y)
                if hasattr(lmap, 'world_map') and lmap.world_map else "",
            era_year=engine.time.year,
            placer_skill=engine.player.skills.get("placer", 0),
            rng=random.Random(rng.randint(0, 999999)))
        if nugget:
            engine.player.gold_oz += nugget.weight_oz * nugget.fineness
            total_gold += nugget.weight_oz * nugget.fineness
            engine.add_message(
                NuggetSystem.format_nugget_message(nugget), "normal")

        # Render with live progress HUD
        # Panning: you CAN see gold in the pan — show results per tile
        engine.recompute_fov()
        engine.renderer.render_all(
            lmap, engine.world, engine.player, engine.messages,
            state="local_map", locals_dict=engine.locals,
            gold_overlay=True)
        _val = total_gold * 20.67 * 0.9
        console.print(82, 8, "── PANNING ──────────────",
                      fg=(255, 200, 50))
        console.print(82, 9,
                      f"Tile {tile_idx + 1}/{len(tiles)}",
                      fg=(200, 200, 200))
        console.print(82, 10,
                      f"Pans: {pan_count}  Gold: {total_gold:.4f} oz",
                      fg=(220, 200, 140))
        console.print(82, 11,
                      f"Value: ${_val:.2f}",
                      fg=(200, 180, 100))
        console.print(82, 13, "[ESC] Stop", fg=(120, 120, 120))
        ctx.present(console)

    # Summary
    value = total_gold * 20.67 * 0.9
    engine.add_message(
        f"Done. {pan_count} pans, {total_gold:.4f} oz (${value:.2f}).", "normal")
    engine.show_gold_overlay = True
    return []  # all tiles worked


# ── Auto-sluice ──────────────────────────────────────────────────────────

def _auto_sluice(engine: "Engine", console, ctx,
                 tiles: List[Tuple[int, int]],
                 sluice, water_pos: Tuple[int, int],
                 has_pick: bool) -> List[Tuple[int, int]]:
    """Auto-sluice selected tiles. Returns unworked tiles if interrupted."""
    from src.prospecting import pan_for_gold
    from src.volume_gold import VolumeGoldSystem
    from src.nugget_system import NuggetSystem

    lmap = engine.current_local
    rng = random.Random()
    # Shoveling time only — walking to/from sluice is handled by _walk_to
    shovel_time_sec = 3 * 60  # 3 min to dig and load a shovel of material

    loads = 0
    sx, sy = sluice.x, sluice.y

    # Track accumulated gold on a virtual sluice state.
    # Riffle capacity is based on historical equipment:
    #
    # ROCKER (cradle): Small, hand-rocked. Wooden riffles and apron catch
    #   gold. Processes ~1 cubic yard/hour. Riffles hold ~0.3 oz before
    #   needing cleanout. In rich ground, clean out every 15-20 minutes.
    #   In lean ground, every few hours.
    #
    # SLUICE BOX (12 ft): Standard long trough with wooden crossbar riffles.
    #   Processes 3-5 cubic yards/hour with good water flow. Riffles hold
    #   ~1.0 oz. Cleanout every 1-2 hours in moderate ground. In bonanza
    #   ground (1849 surface deposits), every 30 minutes.
    #
    # LONG TOM (16-20 ft): Extended sluice with hopper and perforated plate.
    #   Processes 5-8 cubic yards/hour. More riffles = ~2.0 oz capacity.
    #   Cleanout every 2-4 hours typically.
    #
    sluice_gold = 0.0
    batch_tiles: List[Tuple[int, int]] = []  # tiles in current cleanout batch
    is_long = "long" in sluice.name.lower()
    is_rocker = "rocker" in sluice.name.lower()
    if is_long:
        riffle_cap = 2.0
    elif is_rocker:
        riffle_cap = 0.3
    else:
        riffle_cap = 1.0

    remaining = list(tiles)

    engine.add_message(
        f"You start working {len(tiles)} tiles into the {sluice.name}.", "normal")

    for tx, ty in tiles:
        tile = lmap.tile_at(tx, ty)

        # Skip non-workable terrain
        if tile.terrain not in _SHOVELABLE and tile.terrain not in _BEDROCK:
            continue

        # Walk to work tile
        walk = _walk_to(engine, console, ctx, tx, ty, lmap)
        if walk is None:
            # Interrupted — cleanout what's accumulated, return remaining
            if sluice_gold > 0:
                _do_cleanout(engine, lmap, sluice, sluice_gold,
                             loads, rng, batch_tiles)
            engine.show_gold_overlay = True
            return remaining
        if walk is False:
            if (tx, ty) in remaining:
                remaining.remove((tx, ty))
            continue

        # Bedrock needs pickaxe
        if tile.terrain in _BEDROCK:
            if not has_pick:
                continue
            engine.add_message(
                "You break up bedrock crevice material with the pickaxe...", "normal")
            engine.time.advance_seconds(15 * 60)
            engine.player.gain_skill_xp("geology", 2.0)
            tile.gold_grade = max(tile.gold_grade, lmap._gold_bias * 1.5)

        # Lazy gold column
        if tile.gold_column is None:
            _col_bias = max(tile.gold_grade, lmap._gold_bias * 0.5)
            _col_rng = random.Random(lmap.seed + tx * 100 + ty)
            tile.gold_column = VolumeGoldSystem.create_column(
                lmap._region_name, _col_bias, _col_rng)

        tile.gold_grade = max(tile.gold_column.get_current_grade(), 0.001)

        # Shovel ~3 pan volumes per load
        load_gold = 0.0
        for _ in range(3):
            VolumeGoldSystem.pan_volume(
                tile.gold_column,
                placer_skill=engine.player.skills.get("placer", 0))

        result = pan_for_gold(engine.player, lmap)
        load_gold = result.gold_oz
        engine.player.gain_skill_xp("placer", 2.0)

        # Riffle overflow penalty — if riffles are near capacity,
        # less gold gets trapped. The rest washes out the tailings end.
        riffle_pct = sluice_gold / max(riffle_cap, 0.01)
        if riffle_pct >= 1.0:
            load_gold *= 0.2   # losing 80% — riffles packed
        elif riffle_pct >= 0.85:
            load_gold *= 0.6   # losing 40%
        elif riffle_pct >= 0.7:
            load_gold *= 0.85  # losing 15%

        sluice_gold += load_gold
        batch_tiles.append((tx, ty))

        # Terrain change — mark surface worked
        if tile.terrain == LocalTerrain.GRAVEL_BAR:
            tile.terrain = LocalTerrain.WORKED_GRAVEL
        elif tile.terrain in (LocalTerrain.GROUND, LocalTerrain.GRASS):
            tile.terrain = LocalTerrain.WORKED_DIRT
        tile.sluiced = True

        # Dig down — lower surface z by 1 to expose the layer below.
        # Real sluicing: shovel away the surface gravel, work your way
        # down toward bedrock where the richest gold settles.
        cur_surface = int(lmap.surface_z[ty][tx])
        if cur_surface > 0:
            lmap.surface_z[ty][tx] = cur_surface - 1
            # Reset the surface tile for the newly exposed layer:
            # terrain reverts to unworked, gold grade increases with depth
            depth_dug = 1  # how many z-levels down from original
            # Check how far we've dug total by looking at original height
            orig_surface = getattr(tile, '_orig_surface_z', cur_surface)
            if not hasattr(tile, '_orig_surface_z'):
                tile._orig_surface_z = cur_surface
            depth_dug = orig_surface - (cur_surface - 1)

            # Deeper layers are richer (closer to bedrock)
            depth_bonus = min(0.35, depth_dug * 0.08)
            tile.terrain = LocalTerrain.GRAVEL_BAR  # fresh layer exposed
            tile.gold_grade = min(1.0, tile.gold_grade * 1.15 + depth_bonus)
            tile.sluiced = False
            tile.panned = False
            # At depth 4+ we hit bedrock — richest layer, then it's done
            if depth_dug >= 4:
                tile.terrain = LocalTerrain.BEDROCK
                tile.gold_grade = min(1.0, tile.gold_grade + 0.20)
                engine.add_message(
                    "You've hit bedrock! This is where the heavy gold sits.",
                    "advisory")

        lmap.invalidate_terrain_cache()

        # Tile shoveled — remove from remaining
        if (tx, ty) in remaining:
            remaining.remove((tx, ty))

        # Walk to sluice to dump
        walk = _walk_to(engine, console, ctx, sx, sy, lmap, delay=0.04)
        if walk is None:
            if sluice_gold > 0:
                _do_cleanout(engine, lmap, sluice, sluice_gold,
                             loads, rng, batch_tiles)
            engine.show_gold_overlay = True
            return remaining
        if walk is False:
            engine.add_message("Can't reach sluice. Stopping.", "advisory")
            if sluice_gold > 0:
                _do_cleanout(engine, lmap, sluice, sluice_gold,
                             loads, rng, batch_tiles)
            engine.show_gold_overlay = True
            return remaining

        loads += 1
        engine.time.advance_seconds(shovel_time_sec)
        engine.add_message(f"Load {loads} dumped into the {sluice.name}.", "normal")

        # Render with sluice HUD — no gold amount (can't see inside riffles)
        engine.recompute_fov()
        engine.renderer.render_all(
            lmap, engine.world, engine.player, engine.messages,
            state="local_map", locals_dict=engine.locals,
            gold_overlay=True)
        riffle_pct = sluice_gold / max(riffle_cap, 0.01)
        console.print(82, 8, f"── {sluice.name.upper()} ──────",
                      fg=(255, 200, 50))
        console.print(82, 9,
                      f"Loads: {loads}",
                      fg=(200, 200, 200))
        # Riffle visual — what the miner can SEE looking at the sluice
        if riffle_pct >= 1.0:
            console.print(82, 10,
                          "Riffles: OVERFLOWING",
                          fg=(255, 50, 50))
        elif riffle_pct >= 0.85:
            console.print(82, 10,
                          "Riffles: heavy concentrates",
                          fg=(255, 180, 50))
        elif riffle_pct >= 0.5:
            console.print(82, 10,
                          "Riffles: black sand building",
                          fg=(200, 180, 100))
        elif riffle_pct >= 0.2:
            console.print(82, 10,
                          "Riffles: some color showing",
                          fg=(160, 150, 100))
        else:
            console.print(82, 10,
                          "Riffles: running clean",
                          fg=(120, 120, 120))
        console.print(82, 12, "[ESC] Stop", fg=(120, 120, 120))
        ctx.present(console)

        # Check riffles — pause auto-mine if they look full
        riffle_pct = sluice_gold / max(riffle_cap, 0.01)
        if riffle_pct >= 0.85:
            if riffle_pct >= 1.0:
                engine.add_message(
                    "Riffles are OVERLOADED — gold is piling up against the "
                    "crossbars and washing over the end! Clean out NOW!",
                    "critical")
            else:
                engine.add_message(
                    "Riffles look heavy — you can see concentrates building up. "
                    "Might want to clean out before you lose gold.",
                    "advisory")
            # Pause auto-mine — player must manually clean out
            engine.add_message(
                "[ENTER] Clean out  [SPACE] Keep running  [ESC] Stop", "normal")
            _paused = True
            while _paused:
                for ev in tcod.event.wait():
                    if isinstance(ev, tcod.event.Quit):
                        raise SystemExit()
                    if isinstance(ev, tcod.event.KeyDown):
                        if ev.sym == tcod.event.KeySym.RETURN:
                            _do_cleanout(engine, lmap, sluice, sluice_gold,
                                         loads, rng, batch_tiles)
                            sluice_gold = 0.0
                            loads = 0
                            batch_tiles = []
                            _paused = False
                        elif ev.sym == tcod.event.KeySym.SPACE:
                            engine.add_message(
                                "You keep running material. "
                                "Some gold is washing over...", "advisory")
                            _paused = False
                        elif ev.sym == tcod.event.KeySym.ESCAPE:
                            if sluice_gold > 0:
                                _do_cleanout(engine, lmap, sluice, sluice_gold,
                                             loads, rng, batch_tiles)
                            engine.add_message("Done sluicing.", "normal")
                            engine.show_gold_overlay = True
                            return remaining
                        break

    # Final cleanout if anything left
    if sluice_gold > 0:
        engine.add_message("You stop and clean out the last batch...", "normal")
        _do_cleanout(engine, lmap, sluice, sluice_gold, loads, rng, batch_tiles)

    engine.add_message("Done sluicing.", "normal")
    engine.show_gold_overlay = True
    return []  # all tiles worked


def _do_cleanout(engine, lmap, sluice, accumulated_oz, loads, rng,
                  batch_tiles=None):
    """Perform sluice cleanout. Stamps batch tiles with average grade for overlay."""
    from src.nugget_system import NuggetSystem

    cleanout_time_sec = 15 * 60
    engine.time.advance_seconds(cleanout_time_sec)

    # Skill bonus
    placer = engine.player.skills.get("placer", 0)
    recovery_mult = 1.0 + placer * 0.07
    final_oz = accumulated_oz * recovery_mult
    engine.player.gold_oz += final_oz
    engine.player.gain_skill_xp("placer", 5.0 + final_oz * 30)

    # Stamp batch tiles with average grade for gold overlay
    # You don't know per-tile yield from a sluice — only the batch average
    if batch_tiles:
        avg_grade = final_oz / max(len(batch_tiles), 1)
        # Convert oz to approximate grade (0-1 scale) for overlay color
        # 0.001 oz/tile ≈ 0.10 grade, 0.01 oz ≈ 0.35, 0.05 oz ≈ 0.65
        avg_display = min(1.0, avg_grade * 15.0)
        for bx, by in batch_tiles:
            if lmap.in_bounds(bx, by):
                bt = lmap.tile_at(bx, by)
                bt.sluice_avg_grade = avg_display

    value = final_oz * 20.67 * 0.9
    if final_oz > 0.05:
        engine.add_message(
            f"Heavy black sand in the riffles... and GOLD. "
            f"{final_oz:.4f} oz (${value:.2f}) from {loads} loads!", "normal")
    elif final_oz > 0.005:
        engine.add_message(
            f"Fine gold in the riffles. {final_oz:.4f} oz (${value:.2f}) "
            f"from {loads} loads.", "normal")
    else:
        engine.add_message(
            f"Barely a trace. {final_oz:.4f} oz (${value:.2f}). "
            f"This ground may not be worth the effort.", "normal")

    # Nugget
    tile = lmap.tile_at(engine.player.local_x, engine.player.local_y)
    nugget = NuggetSystem.roll_nugget(
        dig_depth=getattr(tile, 'dig_depth', 0),
        gold_grade=getattr(tile, 'gold_grade', 0),
        region_name=lmap.world_map.get_region(lmap.world_x, lmap.world_y)
            if hasattr(lmap, 'world_map') and lmap.world_map else "",
        era_year=engine.time.year,
        placer_skill=engine.player.skills.get("placer", 0),
        rng=random.Random(rng.randint(0, 999999)))
    if nugget:
        engine.player.gold_oz += nugget.weight_oz * nugget.fineness
        engine.add_message(
            NuggetSystem.format_nugget_message(nugget), "normal")

    # Tailings
    sx, sy = sluice.x, sluice.y
    for tdy in range(-1, 2):
        for tdx in range(-1, 2):
            ttx, tty = sx + tdx, sy + tdy
            if (lmap.in_bounds(ttx, tty) and
                    lmap.tiles[tty][ttx].terrain in (
                        LocalTerrain.GROUND, LocalTerrain.GRASS,
                        LocalTerrain.MUD, LocalTerrain.WORKED_DIRT)):
                lmap.tiles[tty][ttx].terrain = LocalTerrain.TAILINGS
                lmap.invalidate_terrain_cache()
                break
        else:
            continue
        break
