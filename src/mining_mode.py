"""
Mining work mode — streamlined repetitive mining with visual feedback.

Two modes:
1. PAN MODE — stand at water, pan repeatedly. One key per pan.
2. SLUICE MODE — shovel loads to sluice, clean out for big payout.

Entered via action menu or 'M' key. Minimal keystrokes for repetitive labor.
"""

import tcod
import tcod.event
import random
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine import Engine

from src.local_map import LocalTerrain


def enter_mining_mode(engine: "Engine", console, ctx) -> None:
    """Determine which mining mode to enter based on surroundings."""
    lmap = engine.current_local
    tile = lmap.tile_at(engine.player.local_x, engine.player.local_y)

    # Check for sluice/rocker nearby
    sluice = engine._nearby_structure("pan_gold", radius=4)

    # Check for water nearby
    px, py = engine.player.local_x, engine.player.local_y
    water_near = False
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            tx, ty = px + dx, py + dy
            if lmap.in_bounds(tx, ty) and lmap.tiles[ty][tx].terrain == LocalTerrain.WATER:
                water_near = True
                break
        if water_near:
            break

    has_pan = any("pan" in getattr(i, "tool_tags", []) for i in engine.player.inventory)
    has_shovel = any("dig" in getattr(i, "tool_tags", []) for i in engine.player.inventory)

    if sluice and water_near and has_shovel:
        _sluice_mode(engine, console, ctx, sluice)
    elif water_near and has_pan:
        _pan_mode(engine, console, ctx)
    elif has_pan and not water_near:
        engine.add_message("No water nearby. Find a stream to pan.", "advisory")
    elif not has_pan:
        engine.add_message("You need a gold pan.", "advisory")
    else:
        engine.add_message("Need water and a pan, or a sluice with a shovel.", "advisory")


def _pan_mode(engine: "Engine", console, ctx) -> None:
    """Repetitive panning at current location.
    SPACE = pan one cycle, arrows = move to adjacent tile, ESC = stop."""
    from src.prospecting import pan_for_gold, depletion_message, tile_grade_label
    from src.nugget_system import NuggetSystem
    from src.volume_gold import VolumeGoldSystem
    from src.constants import VIEWPORT_W

    lmap = engine.current_local
    total_gold = 0.0
    pan_count = 0
    rng = random.Random()

    while True:
        tile = lmap.tile_at(engine.player.local_x, engine.player.local_y)

        # Draw mining HUD at bottom of sidebar
        console.print(82, 10, " " * 36, fg=(0,0,0), bg=(0,0,0))
        console.print(82, 11, " " * 36, fg=(0,0,0), bg=(0,0,0))
        console.print(82, 12, " " * 36, fg=(0,0,0), bg=(0,0,0))
        console.print(82, 13, " " * 36, fg=(0,0,0), bg=(0,0,0))
        console.print(82, 14, " " * 36, fg=(0,0,0), bg=(0,0,0))
        console.print(82, 15, " " * 36, fg=(0,0,0), bg=(0,0,0))

        console.print(82, 10, "--- PAN MODE ---", fg=(255, 200, 50))
        console.print(82, 11, f"Pans: {pan_count}  Gold: {total_gold:.4f} oz",
                      fg=(220, 200, 140))
        console.print(82, 12, f"Value: ${total_gold * 20.67 * 0.9:.2f}",
                      fg=(200, 180, 100))
        grade_label = tile_grade_label(tile.gold_grade) if tile.gold_grade > 0 else "unknown"
        grade_colors = {
            "barren": (100, 100, 100), "trace": (140, 130, 100),
            "color": (200, 180, 80), "rich": (255, 220, 50),
            "bonanza": (255, 255, 100), "unknown": (120, 120, 120),
        }
        console.print(82, 13, f"Ground: {grade_label}",
                      fg=grade_colors.get(grade_label, (150, 150, 150)))
        console.print(82, 14, "[SPACE] Pan  [arrows] Move", fg=(150, 150, 150))
        console.print(82, 15, "[ESC] Stop working", fg=(150, 150, 150))

        # Redraw the local map + present
        engine.renderer.render_all(
            lmap, engine.world, engine.player, engine.messages,
            state="local_map", locals_dict=engine.locals,
            gold_overlay=engine.show_gold_overlay)
        # Re-draw HUD on top
        console.print(82, 10, "--- PAN MODE ---", fg=(255, 200, 50))
        console.print(82, 11, f"Pans: {pan_count}  Gold: {total_gold:.4f} oz",
                      fg=(220, 200, 140))
        console.print(82, 12, f"Value: ${total_gold * 20.67 * 0.9:.2f}",
                      fg=(200, 180, 100))
        console.print(82, 13, f"Ground: {grade_label}",
                      fg=grade_colors.get(grade_label, (150, 150, 150)))
        console.print(82, 14, "[SPACE] Pan  [arrows] Move", fg=(150, 150, 150))
        console.print(82, 15, "[ESC] Stop working", fg=(150, 150, 150))

        ctx.present(console)

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                raise SystemExit()
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                if sym == tcod.event.KeySym.ESCAPE:
                    if total_gold > 0:
                        engine.add_message(
                            f"You stop panning. Session total: {pan_count} pans, "
                            f"{total_gold:.4f} oz (${total_gold * 20.67 * 0.9:.2f}).",
                            "normal")
                    return

                if sym == tcod.event.KeySym.SPACE:
                    # Do one pan cycle
                    tile = lmap.tile_at(engine.player.local_x, engine.player.local_y)
                    can_pan = tile.terrain in (
                        LocalTerrain.GRAVEL_BAR, LocalTerrain.BEDROCK,
                        LocalTerrain.WATER, LocalTerrain.WORKED_GRAVEL,
                        LocalTerrain.WORKED_DIRT)
                    if not can_pan:
                        engine.add_message("Can't pan here. Move to gravel or water.", "advisory")
                        break

                    # Lazy column
                    if tile.gold_column is None:
                        _col_bias = max(tile.gold_grade, lmap._gold_bias * 0.5)
                        _col_rng = random.Random(
                            lmap.seed + engine.player.local_x * 100 + engine.player.local_y)
                        tile.gold_column = VolumeGoldSystem.create_column(
                            lmap._region_name, _col_bias, _col_rng)

                    grade_before = tile.gold_grade
                    tile.gold_grade = max(tile.gold_column.get_current_grade(), 0.001)
                    VolumeGoldSystem.pan_volume(
                        tile.gold_column,
                        placer_skill=engine.player.skills.get("placer", 0))

                    result = pan_for_gold(engine.player, lmap)
                    engine.player.gold_oz += result.gold_oz
                    total_gold += result.gold_oz
                    pan_count += 1
                    engine.player.gain_skill_xp("placer", result.xp_placer)
                    engine.player.gain_skill_xp("geology", result.xp_geology)
                    engine.time.advance_seconds(result.time_minutes * 60)
                    tile.panned = True

                    # Visual terrain change
                    if tile.terrain == LocalTerrain.GRAVEL_BAR:
                        tile.terrain = LocalTerrain.WORKED_GRAVEL
                    elif tile.terrain in (LocalTerrain.GROUND, LocalTerrain.GRASS,
                                          LocalTerrain.MUD, LocalTerrain.SAND):
                        tile.terrain = LocalTerrain.WORKED_DIRT

                    engine.add_message(result.message, "normal")

                    # Depletion
                    if grade_before > 0.05:
                        dep_msg = depletion_message(grade_before, tile.gold_grade)
                        if dep_msg:
                            engine.add_message(dep_msg, "advisory")

                    # Nugget
                    nugget = NuggetSystem.roll_nugget(
                        dig_depth=tile.dig_depth,
                        gold_grade=tile.gold_grade,
                        region_name=lmap.world_map.get_region(lmap.world_x, lmap.world_y),
                        era_year=engine.time.year,
                        placer_skill=engine.player.skills.get("placer", 0),
                        rng=random.Random(rng.randint(0, 999999)))
                    if nugget:
                        engine.player.gold_oz += nugget.weight_oz * nugget.fineness
                        total_gold += nugget.weight_oz * nugget.fineness
                        engine.add_message(
                            NuggetSystem.format_nugget_message(nugget), "normal")

                    engine.recompute_fov()
                    break

                # Arrow movement within pan mode
                K = tcod.event.KeySym
                moves = {K.UP: (0,-1), K.DOWN: (0,1),
                         K.LEFT: (-1,0), K.RIGHT: (1,0)}
                if sym in moves:
                    dx, dy = moves[sym]
                    nx = engine.player.local_x + dx
                    ny = engine.player.local_y + dy
                    if lmap.in_bounds(nx, ny) and lmap.is_passable(nx, ny):
                        engine.player.move(dx, dy)
                        engine.time.advance_seconds(3)
                        engine.recompute_fov()
                    break


def _sluice_mode(engine: "Engine", console, ctx, sluice) -> None:
    """Sluice work mode. Shovel loads, dump at sluice, clean out for gold.
    SPACE = shovel+dump one load, ENTER = clean out, ESC = stop."""
    from src.prospecting import pan_for_gold, tile_grade_label
    from src.volume_gold import VolumeGoldSystem
    from src.nugget_system import NuggetSystem

    lmap = engine.current_local
    is_sluice = "sluice" in sluice.name.lower()
    max_loads = 12 if is_sluice else 8
    load_time = 7   # minutes per shovel-carry-dump cycle
    cleanout_time = 15  # minutes to clean out

    loads = 0
    accumulated_oz = 0.0
    rng = random.Random()

    while True:
        tile = lmap.tile_at(engine.player.local_x, engine.player.local_y)

        # Draw sluice HUD
        bar_full = int(loads / max_loads * 20)
        bar_str = "#" * bar_full + "." * (20 - bar_full)
        grade_label = tile_grade_label(tile.gold_grade) if tile.gold_grade > 0 else "?"

        engine.renderer.render_all(
            lmap, engine.world, engine.player, engine.messages,
            state="local_map", locals_dict=engine.locals,
            gold_overlay=engine.show_gold_overlay)

        console.print(82, 10, f"--- {sluice.name.upper()} ---", fg=(255, 200, 50))
        console.print(82, 11, f"Loads: {loads}/{max_loads} [{bar_str}]",
                      fg=(220, 200, 140))
        console.print(82, 12, f"Ground: {grade_label}", fg=(200, 180, 100))
        console.print(82, 13, f"Total gold: {engine.player.gold_oz:.4f} oz",
                      fg=(220, 200, 140))
        console.print(82, 15, "[SPACE] Shovel a load", fg=(150, 150, 150))
        console.print(82, 16, "[ENTER] Clean out (recover gold)", fg=(150, 150, 150))
        console.print(82, 17, "[arrows] Move  [ESC] Stop", fg=(150, 150, 150))

        if loads >= max_loads:
            console.print(82, 14, "SLUICE FULL - clean out!", fg=(255, 100, 100))

        ctx.present(console)

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                raise SystemExit()
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                if sym == tcod.event.KeySym.ESCAPE:
                    if accumulated_oz > 0:
                        engine.add_message(
                            f"You leave {accumulated_oz:.4f} oz worth of material "
                            f"sitting in the {sluice.name}. Clean it out first!",
                            "advisory")
                    return

                if sym == tcod.event.KeySym.SPACE and loads < max_loads:
                    # Shovel one load from current tile into sluice
                    can_shovel = tile.terrain in (
                        LocalTerrain.GRAVEL_BAR, LocalTerrain.BEDROCK,
                        LocalTerrain.GROUND, LocalTerrain.GRASS,
                        LocalTerrain.MUD, LocalTerrain.SAND,
                        LocalTerrain.WORKED_GRAVEL, LocalTerrain.WORKED_DIRT)
                    if not can_shovel:
                        engine.add_message(
                            "Can't shovel here. Stand on dirt or gravel.", "advisory")
                        break

                    # Lazy column
                    if tile.gold_column is None:
                        _col_bias = max(tile.gold_grade, lmap._gold_bias * 0.5)
                        _col_rng = random.Random(
                            lmap.seed + engine.player.local_x * 100 + engine.player.local_y)
                        tile.gold_column = VolumeGoldSystem.create_column(
                            lmap._region_name, _col_bias, _col_rng)

                    tile.gold_grade = max(tile.gold_column.get_current_grade(), 0.001)
                    # Sluice processes more volume per load than a pan
                    for _ in range(3):  # ~3 pan volumes per shovel load
                        VolumeGoldSystem.pan_volume(
                            tile.gold_column,
                            placer_skill=engine.player.skills.get("placer", 0))

                    result = pan_for_gold(engine.player, lmap)
                    accumulated_oz += result.gold_oz
                    loads += 1
                    engine.player.gain_skill_xp("placer", 2.0)
                    engine.time.advance_seconds(load_time * 60)

                    # Visual terrain change
                    if tile.terrain == LocalTerrain.GRAVEL_BAR:
                        tile.terrain = LocalTerrain.WORKED_GRAVEL
                    elif tile.terrain in (LocalTerrain.GROUND, LocalTerrain.GRASS):
                        tile.terrain = LocalTerrain.WORKED_DIRT
                    tile.panned = True

                    # Feedback per load
                    if result.gold_oz > 0.01:
                        engine.add_message(
                            f"Load {loads}: good material going in.", "normal")
                    elif result.gold_oz > 0.001:
                        engine.add_message(
                            f"Load {loads}: some color in this batch.", "normal")
                    else:
                        engine.add_message(
                            f"Load {loads}: lean material.", "normal")

                    if loads >= max_loads:
                        engine.add_message(
                            f"{sluice.name} is full. Clean it out! [ENTER]",
                            "advisory")

                    engine.recompute_fov()
                    break

                if sym == tcod.event.KeySym.RETURN and loads > 0:
                    # Clean out the sluice — this is where the gold is recovered
                    engine.time.advance_seconds(cleanout_time * 60)
                    engine.player.gold_oz += accumulated_oz
                    engine.player.gain_skill_xp("placer", 5.0 + accumulated_oz * 30)

                    value = accumulated_oz * 20.67 * 0.9
                    if accumulated_oz > 0.05:
                        engine.add_message(
                            f"You pull the riffles and wash down the concentrates. "
                            f"Heavy black sand... and GOLD. "
                            f"{accumulated_oz:.4f} oz (${value:.2f}) from {loads} loads!",
                            "normal")
                    elif accumulated_oz > 0.005:
                        engine.add_message(
                            f"You clean out the {sluice.name}. Fine gold in the riffles. "
                            f"{accumulated_oz:.4f} oz (${value:.2f}) from {loads} loads.",
                            "normal")
                    else:
                        engine.add_message(
                            f"You clean the {sluice.name} carefully. "
                            f"Barely a trace. {accumulated_oz:.4f} oz (${value:.2f}). "
                            f"This ground may not be worth the effort.",
                            "normal")

                    # Nugget chance on cleanout
                    nugget = NuggetSystem.roll_nugget(
                        dig_depth=tile.dig_depth,
                        gold_grade=tile.gold_grade,
                        region_name=lmap.world_map.get_region(lmap.world_x, lmap.world_y),
                        era_year=engine.time.year,
                        placer_skill=engine.player.skills.get("placer", 0),
                        rng=random.Random(rng.randint(0, 999999)))
                    if nugget:
                        engine.player.gold_oz += nugget.weight_oz * nugget.fineness
                        engine.add_message(
                            NuggetSystem.format_nugget_message(nugget), "normal")

                    # Drop tailings near sluice
                    sx, sy = sluice.x, sluice.y
                    for tdy in range(-1, 2):
                        for tdx in range(-1, 2):
                            ttx, tty = sx + tdx, sy + tdy
                            if (lmap.in_bounds(ttx, tty) and
                                lmap.tiles[tty][ttx].terrain in (
                                    LocalTerrain.GROUND, LocalTerrain.GRASS,
                                    LocalTerrain.MUD, LocalTerrain.WORKED_DIRT)):
                                lmap.tiles[tty][ttx].terrain = LocalTerrain.TAILINGS
                                break
                        else:
                            continue
                        break

                    loads = 0
                    accumulated_oz = 0.0
                    engine.recompute_fov()
                    break

                # Arrow movement
                K = tcod.event.KeySym
                moves = {K.UP: (0,-1), K.DOWN: (0,1),
                         K.LEFT: (-1,0), K.RIGHT: (1,0)}
                if sym in moves:
                    dx, dy = moves[sym]
                    nx = engine.player.local_x + dx
                    ny = engine.player.local_y + dy
                    if lmap.in_bounds(nx, ny) and lmap.is_passable(nx, ny):
                        engine.player.move(dx, dy)
                        engine.time.advance_seconds(3)
                        engine.recompute_fov()
                    break
