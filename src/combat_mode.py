"""
Combat mode — full takeover event loop for active combat.

Auto-enters when hostiles detected. Provides one-key fire, target cycling,
aimed shots, live hit chance, and descriptive condition readouts.
ESC exits to normal game; re-enters automatically if hostiles remain.

Controls:
  F       Fire at current target
  R       Reload weapon
  TAB     Cycle target
  1-5     Set aimed body part (1=center, 2=head, 3=legs, 4=arms, 5=torso)
  Arrows  Move (triggers enemy turn)
  SPACE   Wait/hold (enemy turn passes)
  ESC     Exit combat mode
"""

import tcod
import tcod.event
import random
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine import Engine

from src.combat import (
    player_attack_npc, AIMED_SHOTS, combat_taunt, incap_message,
)


# ── Condition descriptions (no HP numbers) ────────────────────────────────

def _condition(health: float, max_blood: float, state: str = "") -> tuple:
    """Return (description, fg_color) based on health percentage."""
    if state == "dead":
        return "Dead", (100, 100, 100)
    if state in ("downed", "surrendered"):
        return "Collapsed", (140, 50, 50)
    pct = health / max(max_blood, 1)
    if pct >= 0.9:
        return "Uninjured", (200, 200, 200)
    if pct >= 0.7:
        return "Hurt", (220, 220, 100)
    if pct >= 0.5:
        return "Wounded", (220, 180, 60)
    if pct >= 0.25:
        return "Bleeding heavily", (220, 120, 40)
    return "Barely standing", (220, 50, 50)


def _npc_condition(npc) -> tuple:
    return _condition(npc.health, getattr(npc.wounds, 'max_blood', 100),
                      npc.combat_state)


def _animal_condition(a) -> tuple:
    return _condition(a.health, 100.0, a.state)


# ── Helpers ───────────────────────────────────────────────────────────────

def _get_all_hostiles(engine):
    """Return list of (dist, kind, obj) for all hostile NPCs + animals."""
    px, py = engine.player.local_x, engine.player.local_y
    targets = []
    for n in engine._tile_npcs():
        if n.alive and n.combat_state == "hostile":
            d = max(abs(n.local_x - px), abs(n.local_y - py))
            targets.append((d, "npc", n))
    for a in engine.wildlife_mgr.get_animals(
            engine.player.world_x, engine.player.world_y,
            engine.player.area_x, engine.player.area_y):
        if a.alive and a.state == "hostile":
            d = max(abs(a.local_x - px), abs(a.local_y - py))
            targets.append((d, "animal", a))
    targets.sort(key=lambda t: t[0])
    return targets


def _best_weapon(player):
    """Find the best equipped weapon (prefer firearm with ammo)."""
    firearms = [i for i in player.inventory
                if i.weapon_type == "firearm" and i.extra.get("loaded", 0) > 0]
    if firearms:
        # Prefer the one in hand
        for f in firearms:
            if f.name == player.right_hand or f.name == player.left_hand:
                return f
        return firearms[0]
    # Fall back to melee
    melee = [i for i in player.inventory if i.weapon_type == "melee"]
    if melee:
        for m in melee:
            if m.name == player.right_hand or m.name == player.left_hand:
                return m
        return melee[0]
    return None


def _calc_hit_chance(player, target, weapon, dist, aimed_part):
    """Estimate hit chance as a percentage."""
    if weapon is None:
        return 0
    if weapon.weapon_type == "firearm":
        skill = player.skills.get("firearms", 0)
        attr = player.attributes.get("agility", 10)
    else:
        skill = player.skills.get("survival", 0)
        attr = player.attributes.get("strength", 10)

    avg_roll = 10.5 + skill // 2 + attr // 3

    # Target defense
    if hasattr(target, 'attributes'):
        defense = 8 + target.attributes.get("agility", 10) // 3
    else:
        size_def = {"small": 12, "medium": 9, "large": 6, "very_large": 5}
        defense = size_def.get(getattr(target, 'species', None) and target.species.size, 8)

    # Range penalty
    if weapon.weapon_type == "firearm" and dist > 40:
        avg_roll -= (dist - 40) // 5
    elif weapon.weapon_type != "firearm" and dist > 1:
        avg_roll -= (dist - 1) * 3

    # Aimed penalty
    aim = AIMED_SHOTS[aimed_part] if 0 <= aimed_part < len(AIMED_SHOTS) else AIMED_SHOTS[0]
    avg_roll += aim[1]  # penalty (negative)

    effective = avg_roll - defense
    return min(95, max(5, int(50 + effective * 5)))


# ── Main combat loop ─────────────────────────────────────────────────────

def enter_combat_mode(engine: "Engine", console, ctx) -> None:
    """Full-takeover combat event loop."""
    aimed_part = 0
    target_idx = 0
    combat_messages = []  # local combat log

    lmap = engine.current_local
    region = lmap._region_name if lmap else ""
    engine.journal.begin_combat(engine.time.date_string, region)

    def add_msg(text, severity="normal"):
        combat_messages.append((text, severity))
        if len(combat_messages) > 30:
            combat_messages.pop(0)
        engine.add_message(text, severity)
        engine.journal.log_combat_event(text, severity)

    add_msg("COMBAT!", "critical")

    while True:
        lmap = engine.current_local
        px, py = engine.player.local_x, engine.player.local_y

        # Get hostiles
        hostiles = _get_all_hostiles(engine)
        if not hostiles:
            add_msg("The fight is over.", "normal")
            engine.journal.end_combat()
            return

        # Clamp target index
        if target_idx >= len(hostiles):
            target_idx = 0
        dist, kind, target = hostiles[target_idx]

        # Current weapon
        weapon = _best_weapon(engine.player)
        hit_chance = _calc_hit_chance(engine.player, target, weapon, dist, aimed_part) if weapon else 0

        # ── Render ────────────────────────────────────────────────────
        engine.recompute_fov()
        engine.renderer.render_all(
            lmap, engine.world, engine.player, engine.messages,
            state="local_map", locals_dict=engine.locals,
            gold_overlay=False)

        # Draw NPCs and wildlife
        _on_map = engine._tile_npcs()
        engine.renderer.draw_npcs(_on_map, lmap, engine.player)
        _animals = engine.wildlife_mgr.get_animals(
            engine.player.world_x, engine.player.world_y,
            engine.player.area_x, engine.player.area_y)
        engine.renderer.draw_wildlife(_animals, lmap, engine.player)

        # ── Red banner (row 0) ────────────────────────────────────────
        console.draw_rect(0, 0, 120, 1, ord(" "), fg=(255, 255, 255), bg=(100, 15, 15))
        console.print(2, 0, "IN COMBAT", fg=(255, 255, 255), bg=(100, 15, 15))
        aim_label = AIMED_SHOTS[aimed_part][0] if 0 <= aimed_part < len(AIMED_SHOTS) else "Center"
        console.print(60, 0, f"Aim: {aim_label}", fg=(255, 200, 100), bg=(100, 15, 15))

        # ── Combat sidebar ────────────────────────────────────────────
        x = 82
        # Clear sidebar area
        for sy in range(8, 44):
            console.print(x, sy, " " * 36, fg=(0, 0, 0), bg=(0, 0, 0))

        # Target info
        y = 8
        console.print(x, y, "── Target ──────────────────", fg=(180, 60, 60))
        y += 1
        if kind == "npc":
            tname = target.display_name()
            cond_text, cond_color = _npc_condition(target)
        else:
            tname = target.species.display_name
            cond_text, cond_color = _animal_condition(target)

        console.print(x, y, f">> {tname[:30]}", fg=(255, 255, 255))
        y += 1
        console.print(x, y, f"   {cond_text}", fg=cond_color)
        y += 1
        console.print(x, y, f"   Range: {dist} tiles ({dist * 5}ft)", fg=(180, 180, 180))
        y += 1

        # Hit chance
        if weapon:
            if hit_chance >= 70:
                hc_fg = (100, 255, 100)
            elif hit_chance >= 40:
                hc_fg = (255, 255, 100)
            else:
                hc_fg = (255, 100, 100)
            console.print(x, y, f"   Hit chance: {hit_chance}%", fg=hc_fg)
        else:
            console.print(x, y, "   No weapon!", fg=(255, 80, 80))
        y += 2

        # Weapon info
        console.print(x, y, "── Weapon ──────────────────", fg=(140, 140, 140))
        y += 1
        if weapon:
            console.print(x, y, f"   {weapon.name}", fg=(200, 200, 200))
            y += 1
            if weapon.weapon_type == "firearm":
                loaded = weapon.extra.get("loaded", 0)
                cap = weapon.extra.get("capacity", 1)
                ammo_fg = (100, 255, 100) if loaded > 0 else (255, 80, 80)
                console.print(x, y, f"   Loaded: {loaded}/{cap}", fg=ammo_fg)
            else:
                console.print(x, y, f"   Melee", fg=(180, 180, 180))
        else:
            console.print(x, y, "   Unarmed", fg=(180, 100, 100))
        y += 2

        # All hostiles list
        console.print(x, y, "── Hostiles ────────────────", fg=(180, 60, 60))
        y += 1
        for i, (d, k, t) in enumerate(hostiles[:6]):
            sel = ">>" if i == target_idx else "  "
            if k == "npc":
                nm = t.display_name()[:18]
                _, c = _npc_condition(t)
            else:
                nm = t.species.display_name[:18]
                _, c = _animal_condition(t)
            console.print(x, y, f" {sel} {nm} ({d}t)", fg=c)
            y += 1

        y += 1
        # Quick keys
        console.print(x, y,     "[F]ire  [R]eload  [TAB]target", fg=(120, 120, 120))
        console.print(x, y + 1, "[1-5] Aim  [SPACE] Wait", fg=(120, 120, 120))
        console.print(x, y + 2, "[V]iew target  [arrows] Move", fg=(120, 120, 120))
        console.print(x, y + 3, "[ESC] Exit combat mode", fg=(120, 120, 120))

        # ── Combat log at bottom ──────────────────────────────────────
        log_y = 44
        for i, (msg, sev) in enumerate(combat_messages[-4:]):
            fg = (255, 80, 80) if sev == "critical" else (200, 200, 200)
            console.print(1, log_y + i, msg[:78], fg=fg, bg=(0, 0, 0))

        # ── Target highlight on map ───────────────────────────────────
        tx = getattr(target, 'local_x', 0)
        ty = getattr(target, 'local_y', 0)
        half_w = 40  # VIEWPORT_W // 2
        half_h = 19  # VIEWPORT_H // 2
        sx = tx - (px - half_w)
        sy = ty - (py - half_h) + 1  # +1 for hotbar
        if 0 <= sx < 80 and 1 <= sy < 40:
            # Draw red X on target
            console.print(sx, sy, "X", fg=(255, 40, 40), bg=(80, 10, 10))
        # If target is under sidebar, show direction arrow at edge
        elif sx >= 80:
            arrow_y = max(1, min(39, sy))
            console.print(79, arrow_y, ">", fg=(255, 40, 40))

        ctx.present(console)

        # ── Input ─────────────────────────────────────────────────────
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                raise SystemExit()
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                K = tcod.event.KeySym

                if sym == K.ESCAPE:
                    return  # exit combat mode

                # Fire
                if sym == K.f:
                    if not weapon:
                        add_msg("No weapon!", "advisory")
                        break
                    if weapon.weapon_type == "firearm":
                        loaded = weapon.extra.get("loaded", 0)
                        if loaded <= 0:
                            add_msg(f"*click* — {weapon.name} isn't loaded. [R] to reload.", "advisory")
                            break
                    # Execute attack
                    if kind == "npc":
                        evt = player_attack_npc(engine.player, target, weapon,
                                                distance=dist, aimed_part=aimed_part)
                        add_msg(evt.message, "critical" if evt.killed else "normal")
                        if evt.hit:
                            skill = "firearms" if weapon.weapon_type == "firearm" else "survival"
                            engine.player.gain_skill_xp(skill, 3.0 if evt.killed else 1.5)
                            engine._splatter_blood(lmap, target.local_x, target.local_y,
                                                   2 if evt.killed else 1)
                            if evt.killed:
                                engine._blood_pool(lmap, target.local_x, target.local_y, 2, True)
                                engine.journal.log_enemy_killed(target.name)
                                lmap.invalidate_terrain_cache()
                            if evt.defender_fled:
                                engine.journal.log_enemy_fled(target.name)
                    else:
                        # Animal attack
                        sp = target.species
                        roll = random.randint(1, 20)
                        roll += engine.player.skills.get("firearms" if weapon.weapon_type == "firearm" else "survival", 0) // 2
                        roll += engine.player.attributes.get("agility" if weapon.weapon_type == "firearm" else "strength", 10) // 3
                        aim = AIMED_SHOTS[aimed_part]
                        roll += aim[1]
                        defense = {"small": 12, "medium": 9, "large": 6, "very_large": 5}.get(sp.size, 8)
                        if weapon.weapon_type == "firearm" and dist > 40:
                            roll -= (dist - 40) // 5
                        if roll >= defense:
                            dmg = max(1, int(random.randint(weapon.damage_min, weapon.damage_max) * aim[2]))
                            if aim[3] == "head" and dmg >= 5 and random.random() < 0.6:
                                dmg = max(dmg, int(target.health) + 10)
                            target.take_damage(float(dmg))
                            engine._splatter_blood(lmap, target.local_x, target.local_y,
                                                   2 if target.state == "dead" else 1)
                            if target.state == "dead":
                                add_msg(f"The {sp.display_name} drops.", "normal")
                                engine._blood_pool(lmap, target.local_x, target.local_y, 2, True)
                                engine.journal.log_enemy_killed(sp.display_name)
                            elif target.state == "downed":
                                add_msg(f"The {sp.display_name} collapses.", "normal")
                            else:
                                add_msg(f"You hit the {sp.display_name}.", "normal")
                        else:
                            add_msg(f"The shot misses the {sp.display_name}.", "normal")
                        engine.player.gain_skill_xp("firearms" if weapon.weapon_type == "firearm" else "survival", 2.0)

                    # Enemy turn after firing
                    engine._npc_combat_tick()
                    engine.time.advance_seconds(5)
                    break

                # Reload
                if sym == K.r:
                    if weapon and weapon.weapon_type == "firearm":
                        loaded = weapon.extra.get("loaded", 0)
                        cap = weapon.extra.get("capacity", 1)
                        if loaded >= cap:
                            add_msg("Already fully loaded.", "advisory")
                        else:
                            ammo_type = weapon.extra.get("ammo_type", "")
                            ammo_item = None
                            for it in engine.player.inventory:
                                if it.id == ammo_type and getattr(it, 'quantity', 0) > 0:
                                    ammo_item = it
                                    break
                            if ammo_item:
                                rounds = min(cap - loaded, ammo_item.quantity)
                                weapon.extra["loaded"] = loaded + rounds
                                if ammo_item.stackable:
                                    ammo_item.quantity -= rounds
                                    if ammo_item.quantity <= 0:
                                        engine.player.inventory.remove(ammo_item)
                                else:
                                    engine.player.inventory.remove(ammo_item)
                                add_msg(f"Loaded {rounds} round(s). ({weapon.extra['loaded']}/{cap})", "normal")
                                engine._npc_combat_tick()
                                engine.time.advance_seconds(weapon.extra.get("reload_time", 15))
                            else:
                                add_msg(f"No {ammo_type} ammo!", "advisory")
                    else:
                        add_msg("No firearm to reload.", "advisory")
                    break

                # Cycle target
                if sym == K.TAB:
                    target_idx = (target_idx + 1) % len(hostiles)
                    d, k, t = hostiles[target_idx]
                    nm = t.display_name() if k == "npc" else t.species.display_name
                    add_msg(f"Target: {nm} ({d} tiles)", "advisory")
                    break

                # Aimed body part 1-5
                if sym in (K.N1, K.N2, K.N3, K.N4, K.N5,
                           K.KP_1, K.KP_2, K.KP_3, K.KP_4, K.KP_5):
                    idx_map = {K.N1: 0, K.N2: 1, K.N3: 2, K.N4: 3, K.N5: 4,
                               K.KP_1: 0, K.KP_2: 1, K.KP_3: 2, K.KP_4: 3, K.KP_5: 4}
                    aimed_part = idx_map.get(sym, 0)
                    aim_name = AIMED_SHOTS[aimed_part][0]
                    add_msg(f"Aim: {aim_name}", "advisory")
                    break

                # Wait/hold
                if sym == K.SPACE:
                    add_msg("You hold position.", "normal")
                    engine._npc_combat_tick()
                    engine.time.advance_seconds(5)
                    break

                # Free look — center viewport on target temporarily
                if sym == K.v:
                    # Snap view to target for one frame
                    old_x, old_y = engine.player.local_x, engine.player.local_y
                    t_x = getattr(target, 'local_x', px)
                    t_y = getattr(target, 'local_y', py)
                    add_msg(f"Looking at target ({t_x},{t_y})...", "advisory")
                    # Temporarily move camera by shifting player pos for render
                    engine.player.local_x = t_x
                    engine.player.local_y = t_y
                    engine.renderer.render_all(
                        lmap, engine.world, engine.player, engine.messages,
                        state="local_map", locals_dict=engine.locals)
                    engine.renderer.draw_npcs(_on_map, lmap, engine.player)
                    engine.renderer.draw_wildlife(_animals, lmap, engine.player)
                    console.print(40, 20, "@", fg=(100, 100, 255))  # player marker
                    console.print(2, 0, "FREE LOOK — press any key", fg=(255, 255, 100), bg=(40, 40, 80))
                    ctx.present(console)
                    engine.player.local_x = old_x
                    engine.player.local_y = old_y
                    # Wait for any key
                    for evt2 in tcod.event.wait():
                        if isinstance(evt2, (tcod.event.KeyDown, tcod.event.Quit)):
                            break
                    break

                # Movement
                moves = {K.UP: (0, -1), K.DOWN: (0, 1),
                         K.LEFT: (-1, 0), K.RIGHT: (1, 0),
                         K.KP_8: (0, -1), K.KP_2: (0, 1),
                         K.KP_4: (-1, 0), K.KP_6: (1, 0),
                         K.KP_7: (-1, -1), K.KP_9: (1, -1),
                         K.KP_1: (-1, 1), K.KP_3: (1, 1)}
                if sym in moves:
                    dx, dy = moves[sym]
                    engine._do_move(dx, dy)
                    # Combat tick happens in _do_move via normal flow
                    break
