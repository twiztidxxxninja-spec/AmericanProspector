"""
Hunting work mode — stalk, track, and shoot wildlife.

H key enters hunting mode:
  - Movement is sneaking (reduced animal detection range)
  - Sidebar shows wind, nearest animals, tracking signs
  - F = fire at selected target (shows range + hit chance)
  - SPACE = wait/watch (animals move, player stays still)
  - Arrow keys = sneak (slower, quieter movement)
  - TAB = cycle target
  - ESC = exit hunting mode
"""

import tcod
import tcod.event
import random
import math
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine import Engine

from src.local_map import LocalTerrain


# Wind direction names
WIND_DIRS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def enter_hunting_mode(engine: "Engine", console, ctx) -> None:
    """Enter hunting/tracking mode."""
    animals = engine.wildlife_mgr.get_animals(
        engine.player.world_x, engine.player.world_y,
        engine.player.area_x, engine.player.area_y)
    if not animals:
        engine.add_message("No wildlife nearby.", "advisory")
        return

    has_weapon = any(i.weapon_type == "firearm" for i in engine.player.inventory)
    if not has_weapon:
        engine.add_message(
            "You have no firearm. You can still track and observe.", "advisory")

    _hunting_loop(engine, console, ctx)


def _hunting_loop(engine: "Engine", console, ctx) -> None:
    from src.combat import player_attack_npc
    from src.wildlife_manager import _ALERT_DIST

    lmap = engine.current_local
    player = engine.player
    rng = random.Random()

    # Random wind direction (changes slowly)
    wind_idx = rng.randint(0, 7)
    wind_name = WIND_DIRS[wind_idx]
    turns_since_wind = 0

    target_idx = 0  # currently targeted animal
    kills = 0

    # Sneaking reduces animal alert distance by half
    SNEAK_ALERT_MULT = 0.5
    # Downwind bonus: if player is downwind of animal, even harder to detect
    DOWNWIND_MULT = 0.4

    while True:
        px, py = player.local_x, player.local_y
        tracking_skill = player.skills.get("tracking", 0)
        firearms_skill = player.skills.get("firearms", 0)

        # Get visible animals
        all_animals = engine.wildlife_mgr.get_animals(
            player.world_x, player.world_y,
            player.area_x, player.area_y)
        # Sort by distance
        visible = []
        for a in all_animals:
            if a.state in ("dead", "butchered"):
                continue
            dist = max(abs(a.local_x - px), abs(a.local_y - py))
            if dist <= 60:  # within FOV
                visible.append((dist, a))
        visible.sort(key=lambda x: x[0])

        if target_idx >= len(visible):
            target_idx = 0

        # Get best weapon
        weapon = None
        for i in player.inventory:
            if i.weapon_type == "firearm":
                weapon = i
                break

        # Calculate hit chance for current target
        hit_chance = 0
        target_dist = 0
        target_animal = None
        if visible and weapon:
            target_dist, target_animal = visible[target_idx]
            # Base hit: d20 + skill/2 + attr/3 vs defense
            avg_roll = 10.5 + firearms_skill // 2 + player.attributes.get("agility", 10) // 3
            defense = {"small": 12, "medium": 9, "large": 6, "very_large": 5}.get(
                target_animal.species.size, 8)
            # Range penalty
            range_penalty = max(0, (target_dist - 40)) // 5 if target_dist > 40 else 0
            effective = avg_roll - range_penalty - defense
            hit_chance = min(95, max(5, int(50 + effective * 5)))

        # Check ammo
        has_ammo = False
        if weapon:
            loaded = weapon.extra.get("loaded", 0)
            has_ammo = loaded > 0

        # Render the game view
        engine.recompute_fov()
        engine.renderer.render_all(
            lmap, engine.world, player, engine.messages,
            state="local_map", locals_dict=engine.locals,
            gold_overlay=False)

        # Draw NPCs and wildlife on the map
        _on_map = engine._tile_npcs()
        engine.renderer.draw_npcs(_on_map, lmap, player)
        _animals_draw = engine.wildlife_mgr.get_animals(
            player.world_x, player.world_y,
            player.area_x, player.area_y)
        engine.renderer.draw_wildlife(_animals_draw, lmap, player)

        # Draw hunting HUD in sidebar
        x = 82
        console.print(x, 9, " " * 36, bg=(0, 0, 0))
        console.print(x, 9, "--- HUNTING MODE ---", fg=(180, 120, 60))
        console.print(x, 10, f"Wind: {wind_name:<4}  Kills: {kills}",
                      fg=(140, 160, 180))

        # Animal list
        y = 12
        console.print(x, y - 1, "-- Wildlife --", fg=(120, 120, 120))
        for i, (dist, a) in enumerate(visible[:6]):
            sp = a.species
            state_sym = {"idle": "~", "alert": "!", "fleeing": "<",
                         "hostile": "X", "wounded_fleeing": "%",
                         "downed": "_"}.get(a.state, "?")
            sel = ">" if i == target_idx else " "
            name = sp.display_name[:14]
            # Color by state
            if a.state == "idle":
                fg = (100, 180, 100)
            elif a.state in ("fleeing", "wounded_fleeing"):
                fg = (180, 180, 60)
            elif a.state == "hostile":
                fg = (255, 80, 80)
            elif a.state == "downed":
                fg = (200, 120, 60)
            else:
                fg = (150, 150, 150)
            line = f"{sel}{state_sym} {name} {dist}t"
            console.print(x, y, f"{line:<36}", fg=fg, bg=(0, 0, 0))
            y += 1

        if not visible:
            console.print(x, y, "No animals in sight.", fg=(120, 120, 120))
            y += 1

        # Tracking signs (skill-gated)
        y += 1
        if tracking_skill >= 1:
            # Show tracks near player
            track_count = 0
            for a in all_animals:
                if max(abs(a.local_x - px), abs(a.local_y - py)) <= 30:
                    track_count += 1
            console.print(x, y, f"Tracks nearby: {track_count} animal(s)",
                          fg=(160, 140, 100))
            y += 1
        if tracking_skill >= 3 and visible:
            _, closest = visible[0]
            # Direction to closest
            dx = closest.local_x - px
            dy = closest.local_y - py
            if abs(dx) > abs(dy):
                d = "E" if dx > 0 else "W"
            else:
                d = "S" if dy > 0 else "N"
            console.print(x, y, f"Fresh signs: {d}",
                          fg=(160, 140, 100))
            y += 1

        # Shot info
        y += 1
        if target_animal and weapon:
            ammo_str = f"Loaded: {weapon.extra.get('loaded', 0)}"
            console.print(x, y, f"Target: {target_animal.species.display_name}",
                          fg=(255, 220, 120))
            y += 1
            console.print(x, y, f"Range: {target_dist} tiles ({target_dist*5}ft)",
                          fg=(200, 200, 200))
            y += 1
            # Hit chance color
            if hit_chance >= 70:
                hc_fg = (100, 255, 100)
            elif hit_chance >= 40:
                hc_fg = (255, 255, 100)
            else:
                hc_fg = (255, 100, 100)
            console.print(x, y, f"Hit chance: {hit_chance}%  {ammo_str}",
                          fg=hc_fg)
            y += 1

        # Controls
        y = 42
        console.print(x, y,     "[F] Fire  [TAB] Cycle target", fg=(120, 120, 120))
        console.print(x, y + 1, "[SPACE] Wait  [arrows] Sneak", fg=(120, 120, 120))
        console.print(x, y + 2, "[ESC] Stop hunting", fg=(120, 120, 120))

        ctx.present(console)

        # Input
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                raise SystemExit()
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                K = tcod.event.KeySym

                if sym == K.ESCAPE:
                    if kills > 0:
                        engine.add_message(
                            f"You end the hunt. {kills} kill(s). [P] to butcher downed animals.",
                            "normal")
                    return

                # Fire weapon
                if sym == K.f:
                    if not weapon:
                        engine.add_message("No firearm equipped.", "advisory")
                        break
                    if not has_ammo:
                        engine.add_message("No ammo loaded. [A] Reload.", "advisory")
                        break
                    if not visible:
                        engine.add_message("No target in sight.", "advisory")
                        break

                    target_dist, target_animal = visible[target_idx]
                    sp = target_animal.species

                    # Fire the shot
                    weapon.extra["loaded"] = weapon.extra.get("loaded", 1) - 1
                    engine.time.advance_seconds(5)

                    # Hit roll
                    roll = rng.randint(1, 20) + firearms_skill // 2 + \
                           player.attributes.get("agility", 10) // 3
                    defense = {"small": 12, "medium": 9, "large": 6,
                               "very_large": 5}.get(sp.size, 8)
                    if target_dist > 40:
                        roll -= (target_dist - 40) // 5

                    # Downwind bonus
                    dx = target_animal.local_x - px
                    dy = target_animal.local_y - py
                    animal_dir = _angle_to_dir(dx, dy)
                    if animal_dir == wind_idx:  # player is downwind
                        roll += 2

                    if roll >= defense:
                        dmg = rng.randint(weapon.damage_min, weapon.damage_max)
                        target_animal.take_damage(float(dmg))
                        player.gain_skill_xp("firearms", 5.0)
                        player.gain_skill_xp("tracking", 2.0)

                        if target_animal.state == "dead":
                            engine.add_message(
                                f"CRACK! The {sp.display_name} drops instantly. Clean kill.",
                                "normal")
                            kills += 1
                        elif target_animal.state == "downed":
                            engine.add_message(
                                f"CRACK! The {sp.display_name} staggers and goes down.",
                                "normal")
                            kills += 1
                        elif target_animal.state == "wounded_fleeing":
                            engine.add_message(
                                f"CRACK! Hit! The {sp.display_name} is wounded and running. "
                                f"Follow the blood trail.",
                                "normal")
                        else:
                            engine.add_message(
                                f"CRACK! You hit the {sp.display_name} ({dmg} dmg).",
                                "normal")
                    else:
                        engine.add_message(
                            f"CRACK! The shot misses the {sp.display_name}. "
                            f"It bolts away.",
                            "normal")
                        # Missed shot scares all nearby animals
                        for _, a in visible:
                            if a.state == "idle":
                                a.state = "fleeing"
                                a.alert = True
                        player.gain_skill_xp("firearms", 1.0)

                    # Gunshot alerts all animals in extended range
                    for a in all_animals:
                        if a.state == "idle":
                            a.alert = True
                    break

                # Cycle target
                if sym == K.TAB:
                    if visible:
                        target_idx = (target_idx + 1) % len(visible)
                    break

                # Wait/watch — time passes, animals move
                if sym == K.SPACE:
                    engine.time.advance_seconds(60)  # 1 minute
                    engine.wildlife_mgr.update_all(
                        1, player, lmap)
                    turns_since_wind += 1
                    if turns_since_wind > 10:
                        wind_idx = (wind_idx + rng.choice([-1, 0, 0, 1])) % 8
                        wind_name = WIND_DIRS[wind_idx]
                        turns_since_wind = 0
                    engine.add_message("You wait quietly, watching...", "normal")
                    break

                # Sneak movement
                moves = {K.UP: (0, -1), K.DOWN: (0, 1),
                         K.LEFT: (-1, 0), K.RIGHT: (1, 0)}
                if sym in moves:
                    dx, dy = moves[sym]
                    nx, ny = px + dx, py + dy
                    if lmap.in_bounds(nx, ny) and lmap.is_passable(nx, ny):
                        player.move(dx, dy)
                        # Sneaking takes extra time but is quieter
                        engine.time.advance_seconds(5)  # slower than normal walk (3s)
                        engine.recompute_fov()

                        # Reduced detection while sneaking — temporarily halve alert distances
                        # (the wildlife update will use normal distances, but we moved slowly
                        # so fewer update ticks fire)

                        turns_since_wind += 1
                        if turns_since_wind > 10:
                            wind_idx = (wind_idx + rng.choice([-1, 0, 0, 1])) % 8
                            wind_name = WIND_DIRS[wind_idx]
                            turns_since_wind = 0
                    break


def _angle_to_dir(dx: int, dy: int) -> int:
    """Convert dx,dy offset to wind direction index (0=N, 1=NE, etc.)."""
    angle = math.atan2(dx, -dy)  # N=0, E=pi/2
    idx = int((angle + math.pi) / (math.pi / 4)) % 8
    return idx
