"""
Trapping mode [Y key] — dedicated interface for managing trap lines.

Shows trap locations, animal signs, quick-access to all trapping actions.
Similar to mining/hunting modes — full takeover with dedicated HUD.

Controls:
  S     Set new trap (pick from inventory, place adjacent)
  C     Check nearest trap (harvest/reset)
  R     Reset/re-bait a sprung trap
  P     Pick up nearest trap (retrieve to inventory)
  F     Craft trap (quick access to trapping recipes)
  TAB   Cycle between placed traps (move toward selected)
  Arrows Move (shows animal signs overlay as you walk)
  ESC/Y Exit trapping mode
"""

import tcod
import tcod.event
import random
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine import Engine


def enter_trapping_mode(engine: "Engine", console, ctx) -> None:
    """Full trapping mode — manage trap lines with overlay."""
    from src.trapping import (TrapManager, TRAP_SPECIES, SPECIES_PELT,
                               calculate_pelt_quality, grade_name, grade_multiplier,
                               PELT_GRADES)
    from src.local_map import LocalTerrain
    from src.constants import VIEWPORT_W, VIEWPORT_H

    lmap = engine.current_local
    player = engine.player
    rng = random.Random()
    messages = []
    selected_trap = 0

    def add_msg(text, sev="normal"):
        messages.append((text, sev))
        if len(messages) > 20:
            messages.pop(0)
        engine.add_message(text, sev)

    # Animal sign detection based on tracking + trapping skill
    def _detect_signs():
        """Find animal signs near player based on skill."""
        signs = []
        skill = player.skills.get("tracking", 0) + player.skills.get("trapping", 0)
        if skill < 2:
            return signs
        px, py = player.local_x, player.local_y
        radius = min(15, 5 + skill)
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                nx, ny = px + dx, py + dy
                if not lmap.in_bounds(nx, ny):
                    continue
                # Use position hash to deterministically place signs
                h = (nx * 7919 + ny * 6271 + lmap.seed) & 0xFFFF
                # Signs near water = aquatic animals
                t = lmap.tiles[ny][nx].terrain
                near_water = t == LocalTerrain.WATER
                if h % 100 < skill * 2:  # more skill = more signs visible
                    if near_water:
                        sign_type = "tracks (water)"
                    elif t in (LocalTerrain.MUD, LocalTerrain.SAND):
                        sign_type = "tracks"
                    elif t == LocalTerrain.BRUSH:
                        sign_type = "den"
                    elif t in (LocalTerrain.GRASS, LocalTerrain.GROUND):
                        sign_type = "scat"
                    else:
                        continue
                    signs.append((nx, ny, sign_type))
        return signs

    add_msg("Trapping mode. [S]et [C]heck [R]eset [P]ickup [F]craft [TAB]cycle")

    while True:
        px, py = player.local_x, player.local_y
        half_w, half_h = VIEWPORT_W // 2, VIEWPORT_H // 2
        cam_x = px - half_w
        cam_y = py - half_h

        # Get traps in current area
        traps = engine.trap_mgr.traps_at(
            player.world_x, player.world_y,
            player.area_x, player.area_y)
        if selected_trap >= len(traps):
            selected_trap = 0

        # Detect animal signs
        signs = _detect_signs()

        # ── Render base map ───────────────────────────────────────
        engine.recompute_fov()
        engine.renderer.render_all(
            lmap, engine.world, player, engine.messages,
            state="local_map", locals_dict=engine.locals,
            gold_overlay=False)
        _on_map = engine._tile_npcs()
        engine.renderer.draw_npcs(_on_map, lmap, player)
        _animals = engine.wildlife_mgr.get_animals(
            player.world_x, player.world_y,
            player.area_x, player.area_y)
        engine.renderer.draw_wildlife(_animals, lmap, player)

        # ── Draw animal signs overlay ─────────────────────────────
        for sx_w, sy_w, stype in signs:
            sx = sx_w - cam_x
            sy = sy_w - cam_y + 1
            if 0 <= sx < VIEWPORT_W and 1 <= sy < VIEWPORT_H + 1:
                if stype == "tracks":
                    console.print(sx, sy, "~", fg=(140, 120, 80), bg=(30, 25, 15))
                elif stype == "tracks (water)":
                    console.print(sx, sy, "~", fg=(80, 140, 180), bg=(20, 40, 60))
                elif stype == "den":
                    console.print(sx, sy, "o", fg=(120, 100, 60), bg=(30, 25, 15))
                elif stype == "scat":
                    console.print(sx, sy, ".", fg=(100, 80, 40), bg=(25, 20, 10))

        # ── Draw trap markers on map ──────────────────────────────
        for i, trap in enumerate(traps):
            sx = trap.x - cam_x
            sy = trap.y - cam_y + 1
            if 0 <= sx < VIEWPORT_W and 1 <= sy < VIEWPORT_H + 1:
                is_sel = (i == selected_trap)
                if trap.caught_species:
                    glyph = "%"
                    fg = (255, 200, 50)
                elif trap.sprung:
                    glyph = "_"
                    fg = (150, 100, 60)
                else:
                    glyph = "^" if trap.trap_type in ("snare", "deadfall_trap") else "v"
                    fg = (100, 200, 100)
                bg = (60, 40, 20) if is_sel else (20, 15, 8)
                console.print(sx, sy, glyph, fg=fg, bg=bg)
            else:
                # Off-screen — show directional arrow at edge
                dx = trap.x - px
                dy = trap.y - py
                if abs(dx) > abs(dy):
                    arrow = ">" if dx > 0 else "<"
                    edge_x = VIEWPORT_W - 1 if dx > 0 else 0
                    edge_y = max(1, min(VIEWPORT_H, half_h + dy * half_w // max(abs(dx), 1))) + 1
                else:
                    arrow = "v" if dy > 0 else "^"
                    edge_y = VIEWPORT_H if dy > 0 else 1
                    edge_x = max(0, min(VIEWPORT_W - 1, half_w + dx * half_h // max(abs(dy), 1)))
                fg = (255, 200, 50) if trap.caught_species else (100, 180, 100)
                console.print(edge_x, edge_y, arrow, fg=fg, bg=(40, 30, 15))

        # ── Trapping banner ───────────────────────────────────────
        console.draw_rect(0, 0, 120, 1, ord(" "), fg=(255, 255, 255), bg=(50, 40, 20))
        console.print(2, 0, "TRAPPING MODE", fg=(255, 220, 140), bg=(50, 40, 20))
        caught_count = sum(1 for t in traps if t.caught_species)
        console.print(40, 0, f"Traps: {len(traps)}  Caught: {caught_count}",
                      fg=(200, 200, 180), bg=(50, 40, 20))

        # ── Sidebar HUD ──────────────────────────────────────────
        x = 82
        for sy in range(8, 38):
            console.print(x, sy, " " * 36, bg=(0, 0, 0))

        y = 8
        console.print(x, y, "── Traps ───────────────────", fg=(180, 150, 100))
        y += 1
        for i, trap in enumerate(traps[:8]):
            sel = ">>" if i == selected_trap else "  "
            dist = max(abs(trap.x - px), abs(trap.y - py))
            if trap.caught_species:
                status = trap.caught_species[:12]
                fg = (255, 200, 50)
            elif trap.sprung:
                status = "sprung"
                fg = (150, 100, 60)
            else:
                status = "set"
                fg = (100, 200, 100)
            line = f"{sel}#{trap.id} {trap.trap_type[:8]:8s} {status[:12]:12s} {dist:3d}t"
            console.print(x, y, line[:35], fg=fg)
            y += 1

        if not traps:
            console.print(x, y, "  No traps set.", fg=(120, 120, 120))
            y += 1

        # Animal signs count
        y += 1
        t_skill = player.skills.get("tracking", 0) + player.skills.get("trapping", 0)
        if t_skill >= 2:
            console.print(x, y, f"Animal signs nearby: {len(signs)}", fg=(160, 140, 100))
            y += 1
            # Highlight best trapping spots
            water_signs = sum(1 for _, _, st in signs if "water" in st)
            den_signs = sum(1 for _, _, st in signs if st == "den")
            if water_signs > 0:
                console.print(x, y, f"  Water tracks: {water_signs} (beaver/otter)", fg=(100, 160, 200))
                y += 1
            if den_signs > 0:
                console.print(x, y, f"  Dens: {den_signs} (fox/raccoon)", fg=(140, 120, 80))
                y += 1
        else:
            console.print(x, y, "  (Need tracking+trapping 2+ to see signs)", fg=(80, 80, 80))
            y += 1

        # Skills
        y += 1
        console.print(x, y, f"Trapping: {player.skills.get('trapping', 0)}/10  "
                      f"Furriery: {player.skills.get('furriery', 0)}/10",
                      fg=(180, 170, 140))
        y += 2

        # Controls
        console.print(x, y,     "[S]et trap  [C]heck  [R]eset", fg=(120, 120, 120))
        console.print(x, y + 1, "[P]ickup  [F] Craft  [TAB] Cycle", fg=(120, 120, 120))
        console.print(x, y + 2, "[arrows] Move  [ESC/Y] Exit", fg=(120, 120, 120))

        # Messages
        log_y = 44
        for i, (msg, sev) in enumerate(messages[-4:]):
            fg = (255, 200, 100) if sev == "advisory" else (200, 200, 200)
            console.print(1, log_y + i, msg[:78], fg=fg, bg=(0, 0, 0))

        ctx.present(console)

        # ── Input ─────────────────────────────────────────────────
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                raise SystemExit()
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                K = tcod.event.KeySym

                if sym in (K.ESCAPE, K.y):
                    return

                # Set trap
                if sym == K.s:
                    from src.menus import pick_from_list, pick_direction_menu
                    trap_items = [i for i in player.inventory
                                  if "trap" in getattr(i, "tool_tags", [])]
                    if not trap_items:
                        add_msg("No traps in inventory. [F] to craft.", "advisory")
                        break
                    labels = [f"{t.name}" for t in trap_items]
                    tidx = pick_from_list(console, ctx, "Set which trap?", labels)
                    if tidx is None:
                        break
                    trap_item = trap_items[tidx]
                    direction = pick_direction_menu(console, ctx, "Place where?")
                    if direction is None:
                        break
                    dx, dy = direction
                    tx, ty = px + dx, py + dy
                    if not lmap.in_bounds(tx, ty) or not lmap.is_passable(tx, ty):
                        add_msg("Can't place there.", "advisory")
                        break
                    # Bait
                    bait_items = [i for i in player.inventory
                                  if i.is_food() or i.id == "castoreum"]
                    bait = ""
                    if bait_items:
                        bait_labels = ["No bait"] + [i.name for i in bait_items]
                        bidx = pick_from_list(console, ctx, "Bait?", bait_labels)
                        if bidx and bidx > 0:
                            bi = bait_items[bidx - 1]
                            bait = bi.name
                            if bi.stackable and bi.quantity > 1:
                                bi.quantity -= 1
                            else:
                                player.inventory.remove(bi)
                    skill = player.skills.get("trapping", 0)
                    sq = max(0, min(10, skill + rng.randint(-2, 2)))
                    player.inventory.remove(trap_item)
                    engine.trap_mgr.place_trap(
                        trap_item.id, tx, ty,
                        player.world_x, player.world_y,
                        player.area_x, player.area_y,
                        bait, sq, engine.time.total_seconds)
                    bait_str = f" (baited: {bait})" if bait else ""
                    add_msg(f"Set {trap_item.name}{bait_str}. Quality: {sq}/10.")
                    engine.time.advance_seconds(15 * 60)
                    player.gain_skill_xp("trapping", 3.0)
                    break

                # Check selected trap
                if sym == K.c:
                    if not traps:
                        add_msg("No traps to check.", "advisory")
                        break
                    trap = traps[selected_trap]
                    if trap.caught_species:
                        hours = (engine.time.total_seconds - trap.caught_time) / 3600
                        has_sk = any("skin" in getattr(i, "tool_tags", [])
                                     for i in player.inventory)
                        quality = calculate_pelt_quality(
                            engine.time.season, hours,
                            player.skills.get("trapping", 0),
                            "trap_kill", has_sk, rng)
                        gn = grade_name(quality)
                        pelt_id = SPECIES_PELT.get(trap.caught_species, "")
                        if pelt_id:
                            from src.items import make_item
                            pelt = make_item(pelt_id)
                            pelt.name = f"{gn} {pelt.name}"
                            pelt.base_value *= grade_multiplier(quality)
                            player.inventory.append(pelt)
                            add_msg(f"Caught {trap.caught_species}! "
                                    f"Skinned: {pelt.name} (${pelt.base_value:.2f})")
                        else:
                            add_msg(f"Caught {trap.caught_species}!")
                        player.gain_skill_xp("trapping", 5.0)
                        player.gain_skill_xp("furriery", 2.0)
                        trap.caught_species = ""
                        trap.caught_time = 0
                        engine.time.advance_seconds(15 * 60)
                    elif trap.sprung:
                        add_msg("Trap sprung empty. Reset it.")
                        trap.sprung = False
                    else:
                        add_msg(f"Trap #{trap.id} still set. Nothing yet.")
                    break

                # Reset/rebait
                if sym == K.r:
                    if not traps:
                        break
                    trap = traps[selected_trap]
                    if trap.sprung:
                        trap.sprung = False
                        add_msg(f"Trap #{trap.id} reset.")
                    else:
                        add_msg("Trap doesn't need resetting.")
                    break

                # Pickup trap
                if sym == K.p:
                    if not traps:
                        break
                    trap = traps[selected_trap]
                    from src.items import make_item
                    try:
                        item = make_item(trap.trap_type)
                        player.inventory.append(item)
                        engine.trap_mgr.remove_trap(trap.id)
                        add_msg(f"Retrieved {item.name}.")
                    except Exception:
                        add_msg("Can't retrieve that trap.")
                    break

                # Craft
                if sym == K.f:
                    engine._open_crafting()
                    break

                # Cycle trap
                if sym == K.TAB:
                    if traps:
                        selected_trap = (selected_trap + 1) % len(traps)
                        t = traps[selected_trap]
                        dist = max(abs(t.x - px), abs(t.y - py))
                        add_msg(f"Selected trap #{t.id} ({dist} tiles away)")
                    break

                # Movement
                moves = {K.UP: (0, -1), K.DOWN: (0, 1),
                         K.LEFT: (-1, 0), K.RIGHT: (1, 0),
                         K.KP_8: (0, -1), K.KP_2: (0, 1),
                         K.KP_4: (-1, 0), K.KP_6: (1, 0)}
                if sym in moves:
                    dx, dy = moves[sym]
                    nx, ny = px + dx, py + dy
                    if lmap.in_bounds(nx, ny) and lmap.is_passable(nx, ny):
                        player.move(dx, dy)
                        cur_z = player.local_z
                        target_z = int(lmap.surface_z[ny][nx])
                        if abs(target_z - cur_z) < 2:
                            player.local_z = target_z
                        engine.time.advance_seconds(3)
                        engine.recompute_fov()
                    break
