"""
Combat mode — tick-based real-time combat with dedicated HUD.

Time flows independently for all actors. Each action costs seconds.
NPCs decide and act on their own timers, not in response to the player.

Controls:
  F       Snap shot (fast, less accurate)
  G       Careful aim (slow, +25% accuracy)
  R       Reload weapon
  TAB     Cycle target
  1-5     Set aimed body part
  Arrows  Move (costs time — enemies may act while you move)
  SPACE   Wait 1 second (watch what happens)
  V       Free look (snap camera to target)
  ESC     Exit combat mode
"""

import tcod
import tcod.event
import random
import math
from typing import List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine import Engine

from src.combat import (
    player_attack_npc, AIMED_SHOTS, combat_taunt, incap_message,
    _check_npc_morale, npc_attack_player,
)
from src.health_system import PART_HP


# ── Action costs in seconds ───────────────────────────────────────────────

ACTION_TIME = {
    "snap_shot":    3,   # fast hip shot — lower accuracy
    "aimed_shot":   6,   # normal aimed shot
    "careful_aim":  10,  # slow careful aim — +25% hit bonus
    "reload":       15,  # reload firearm (modified by weapon reload_time)
    "move":         3,   # one tile movement
    "wait":         1,   # hold position
    "melee":        2,   # melee swing
}

# NPC action costs
NPC_ACTION_TIME = {
    "shoot":        5,
    "careful_aim":  8,
    "move_toward":  3,
    "move_away":    3,
    "take_cover":   4,
    "reload":       12,
    "wait":         2,
}


# ── Condition descriptions (no HP numbers) ────────────────────────────────

def _condition(health: float, max_blood: float, state: str = "") -> tuple:
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
    firearms = [i for i in player.inventory
                if i.weapon_type == "firearm" and i.extra.get("loaded", 0) > 0]
    if firearms:
        for f in firearms:
            if f.name == player.right_hand or f.name == player.left_hand:
                return f
        return firearms[0]
    melee = [i for i in player.inventory if i.weapon_type == "melee"]
    if melee:
        for m in melee:
            if m.name == player.right_hand or m.name == player.left_hand:
                return m
        return melee[0]
    return None


def _calc_hit_chance(player, target, weapon, dist, aimed_part, accuracy_bonus=0):
    if weapon is None:
        return 0
    if weapon.weapon_type == "firearm":
        skill = player.skills.get("firearms", 0)
        attr = player.attributes.get("agility", 10)
    else:
        skill = player.skills.get("survival", 0)
        attr = player.attributes.get("strength", 10)

    avg_roll = 10.5 + skill // 2 + attr // 3 + accuracy_bonus

    if hasattr(target, 'attributes'):
        defense = 8 + target.attributes.get("agility", 10) // 3
    else:
        size_def = {"small": 12, "medium": 9, "large": 6, "very_large": 5}
        defense = size_def.get(getattr(target, 'species', None) and target.species.size, 8)

    if weapon.weapon_type == "firearm" and dist > 40:
        avg_roll -= (dist - 40) // 5
    elif weapon.weapon_type != "firearm" and dist > 1:
        avg_roll -= (dist - 1) * 3

    aim = AIMED_SHOTS[aimed_part] if 0 <= aimed_part < len(AIMED_SHOTS) else AIMED_SHOTS[0]
    avg_roll += aim[1]

    effective = avg_roll - defense
    return min(95, max(5, int(50 + effective * 5)))


# ── NPC AI decisions ──────────────────────────────────────────────────────

def _npc_decide(npc, player, lmap, rng) -> Tuple[str, int]:
    """NPC chooses an action and returns (action_name, time_cost).
    Called when NPC's action timer expires."""
    dist = max(abs(npc.local_x - player.local_x),
               abs(npc.local_y - player.local_y))
    hp_pct = npc.health / max(getattr(npc.wounds, 'max_blood', 100), 1)

    # Check if NPC has a ranged weapon (simplified)
    has_gun = rng.random() < 0.4  # 40% of hostile NPCs are armed

    # Badly hurt — try to flee or surrender
    if hp_pct < 0.2:
        _check_npc_morale(npc)
        if npc.combat_state in ("fleeing", "surrendered"):
            return "flee", NPC_ACTION_TIME["move_away"]
        return "shoot", NPC_ACTION_TIME["shoot"]

    # Wounded and exposed — seek cover
    current_cover = lmap.best_adjacent_cover(npc.local_x, npc.local_y)
    if hp_pct < 0.5 and current_cover == 0 and rng.random() < 0.6:
        return "take_cover", NPC_ACTION_TIME["take_cover"]

    # At range with gun — shoot or careful aim
    if has_gun and dist > 3:
        if hp_pct > 0.7 and rng.random() < 0.3 and current_cover > 0:
            # Only careful aim if in cover (safe to take time)
            return "careful_aim", NPC_ACTION_TIME["careful_aim"]
        return "shoot", NPC_ACTION_TIME["shoot"]

    # Close range — melee or close shot
    if dist <= 1:
        return "melee", 2

    # Mid range without gun — close distance
    if not has_gun and dist > 1:
        return "move_toward", NPC_ACTION_TIME["move_toward"]

    # Default — shoot or move
    if has_gun:
        return "shoot", NPC_ACTION_TIME["shoot"]
    return "move_toward", NPC_ACTION_TIME["move_toward"]


def _npc_execute(engine, npc, action, player, lmap, add_msg, rng):
    """Execute an NPC's chosen action."""
    if action == "flee":
        dx = 1 if npc.local_x > player.local_x else -1
        dy = 1 if npc.local_y > player.local_y else -1
        npc.local_x += dx * 2
        npc.local_y += dy * 2
        if (abs(npc.local_x - player.local_x) > 25 or
                abs(npc.local_y - player.local_y) > 25):
            npc.present = False
            add_msg(f"{npc.name} flees into the distance.")
        return

    if action == "take_cover":
        # Find nearest tile with cover value > 0
        best_cx, best_cy, best_d = npc.local_x, npc.local_y, 999
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                nx, ny = npc.local_x + dx, npc.local_y + dy
                if not lmap.in_bounds(nx, ny) or not lmap.is_passable(nx, ny):
                    continue
                if lmap.cover_at(nx, ny) > 0 or lmap.best_adjacent_cover(nx, ny) > 0:
                    d = abs(dx) + abs(dy)
                    if d < best_d and d > 0:
                        best_d = d
                        best_cx, best_cy = nx, ny
        if best_d < 999:
            # Move one step toward cover
            dx = 1 if best_cx > npc.local_x else (-1 if best_cx < npc.local_x else 0)
            dy = 1 if best_cy > npc.local_y else (-1 if best_cy < npc.local_y else 0)
            nx, ny = npc.local_x + dx, npc.local_y + dy
            if lmap.in_bounds(nx, ny) and lmap.is_passable(nx, ny):
                npc.local_x, npc.local_y = nx, ny
                add_msg(f"{npc.name} dives for cover!")
        return

    if action == "move_toward":
        dx = 1 if player.local_x > npc.local_x else (-1 if player.local_x < npc.local_x else 0)
        dy = 1 if player.local_y > npc.local_y else (-1 if player.local_y < npc.local_y else 0)
        nx, ny = npc.local_x + dx, npc.local_y + dy
        if lmap.in_bounds(nx, ny) and lmap.is_passable(nx, ny):
            npc.local_x, npc.local_y = nx, ny
        return

    if action in ("shoot", "careful_aim", "melee"):
        # Calculate player's cover from NPC's perspective
        p_cover = lmap.cover_between(
            npc.local_x, npc.local_y,
            player.local_x, player.local_y)
        event = npc_attack_player(npc, player, player_cover=p_cover)
        sev = "critical" if event.hit else "normal"
        add_msg(event.message, sev)
        if event.hit:
            engine._splatter_blood(lmap, player.local_x, player.local_y, 1)
        if event.killed:
            engine.journal.end_combat()
            engine._trigger_death(f"Killed by {npc.name}.")
        return


# ── Main combat loop ─────────────────────────────────────────────────────

def enter_combat_mode(engine: "Engine", console, ctx) -> None:
    """Tick-based combat event loop. Time flows for all actors."""
    aimed_part = 0
    target_idx = 0
    combat_messages = []
    rng = random.Random()

    lmap = engine.current_local
    region = lmap._region_name if lmap else ""
    engine.journal.begin_combat(engine.time.date_string, region)

    # NPC action timers: {npc_id: seconds_until_next_action}
    npc_timers = {}

    def add_msg(text, severity="normal"):
        combat_messages.append((text, severity))
        if len(combat_messages) > 30:
            combat_messages.pop(0)
        engine.add_message(text, severity)
        engine.journal.log_combat_event(text, severity)

    def tick_time(seconds):
        """Advance time and let NPCs act if their timers expire."""
        remaining = seconds
        while remaining > 0:
            # Find soonest NPC action
            soonest = remaining
            for npc in engine._tile_npcs():
                if not npc.alive or npc.combat_state not in ("hostile", "fleeing"):
                    continue
                timer = npc_timers.get(npc.npc_id, 0)
                if timer < soonest:
                    soonest = timer

            # Advance to soonest event or remaining time
            step = max(1, min(soonest, remaining))

            # Tick all NPC timers
            for npc in engine._tile_npcs():
                if not npc.alive or npc.combat_state not in ("hostile", "fleeing"):
                    continue
                nid = npc.npc_id
                npc_timers[nid] = npc_timers.get(nid, 0) - step
                if npc_timers[nid] <= 0:
                    # NPC acts
                    action, cost = _npc_decide(npc, engine.player, lmap, rng)

                    # Taunt before acting (30% chance)
                    if rng.random() < 0.3:
                        hp_pct = npc.health / max(npc.wounds.max_blood, 1)
                        taunt = combat_taunt(npc.name, hp_pct, True)
                        if taunt:
                            add_msg(taunt)

                    # Incap flavor if badly wounded
                    if npc.health < 25 and npc.health > 0 and rng.random() < 0.3:
                        add_msg(incap_message(npc.name))
                        engine._splatter_blood(lmap, npc.local_x, npc.local_y, 1)

                    _npc_execute(engine, npc, action, engine.player, lmap, add_msg, rng)
                    npc_timers[nid] = cost

            engine.time.advance_seconds(step)
            remaining -= step

            # Check if player died during NPC actions
            if engine.player.survival.health <= 0:
                return

    add_msg("COMBAT!", "critical")

    while True:
        lmap = engine.current_local
        px, py = engine.player.local_x, engine.player.local_y

        hostiles = _get_all_hostiles(engine)
        if not hostiles:
            add_msg("The fight is over.", "normal")
            engine.journal.end_combat()
            return

        if target_idx >= len(hostiles):
            target_idx = 0
        dist, kind, target = hostiles[target_idx]

        weapon = _best_weapon(engine.player)
        hit_chance = _calc_hit_chance(engine.player, target, weapon, dist, aimed_part) if weapon else 0
        careful_chance = _calc_hit_chance(engine.player, target, weapon, dist, aimed_part, accuracy_bonus=5) if weapon else 0

        # ── Render ────────────────────────────────────────────────────
        engine.recompute_fov()
        engine.renderer.render_all(
            lmap, engine.world, engine.player, engine.messages,
            state="local_map", locals_dict=engine.locals, gold_overlay=False)

        _on_map = engine._tile_npcs()
        engine.renderer.draw_npcs(_on_map, lmap, engine.player)
        _animals = engine.wildlife_mgr.get_animals(
            engine.player.world_x, engine.player.world_y,
            engine.player.area_x, engine.player.area_y)
        engine.renderer.draw_wildlife(_animals, lmap, engine.player)

        # Red banner
        console.draw_rect(0, 0, 120, 1, ord(" "), fg=(255, 255, 255), bg=(100, 15, 15))
        console.print(2, 0, "IN COMBAT", fg=(255, 255, 255), bg=(100, 15, 15))
        aim_label = AIMED_SHOTS[aimed_part][0] if 0 <= aimed_part < len(AIMED_SHOTS) else "Center"
        console.print(60, 0, f"Aim: {aim_label}", fg=(255, 200, 100), bg=(100, 15, 15))

        # Combat sidebar
        x = 82
        for sy in range(8, 44):
            console.print(x, sy, " " * 36, fg=(0, 0, 0), bg=(0, 0, 0))

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

        if weapon:
            if hit_chance >= 70: hc_fg = (100, 255, 100)
            elif hit_chance >= 40: hc_fg = (255, 255, 100)
            else: hc_fg = (255, 100, 100)
            console.print(x, y, f"   Snap:  {hit_chance}%  (3s)", fg=hc_fg)
            y += 1
            if careful_chance >= 70: cc_fg = (100, 255, 100)
            elif careful_chance >= 40: cc_fg = (255, 255, 100)
            else: cc_fg = (255, 100, 100)
            console.print(x, y, f"   Aimed: {careful_chance}% (10s)", fg=cc_fg)
        else:
            console.print(x, y, "   No weapon!", fg=(255, 80, 80))
        y += 2

        # Weapon
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
                console.print(x, y, "   Melee", fg=(180, 180, 180))
        else:
            console.print(x, y, "   Unarmed", fg=(180, 100, 100))
        y += 2

        # Player cover status
        p_cover = lmap.best_adjacent_cover(px, py)
        if p_cover >= 2:
            console.print(x, y, "   Cover: FULL (behind rock)", fg=(100, 200, 255))
        elif p_cover == 1:
            console.print(x, y, "   Cover: Partial (tree/brush)", fg=(180, 220, 140))
        else:
            console.print(x, y, "   Cover: EXPOSED", fg=(255, 120, 80))
        y += 2

        # All hostiles
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
        console.print(x, y,     "[F] Snap shot (3s)", fg=(120, 120, 120))
        console.print(x, y + 1, "[G] Careful aim (10s, +25%)", fg=(120, 120, 120))
        console.print(x, y + 2, "[R]eload  [TAB] target", fg=(120, 120, 120))
        console.print(x, y + 3, "[1-5] Aim part  [SPACE] Wait", fg=(120, 120, 120))
        console.print(x, y + 4, "[V]iew  [arrows] Move", fg=(120, 120, 120))
        console.print(x, y + 5, "[ESC] Exit combat", fg=(120, 120, 120))

        # Combat log
        log_y = 44
        for i, (msg, sev) in enumerate(combat_messages[-4:]):
            fg = (255, 80, 80) if sev == "critical" else (200, 200, 200)
            console.print(1, log_y + i, msg[:78], fg=fg, bg=(0, 0, 0))

        # Target highlight
        tx = getattr(target, 'local_x', 0)
        ty = getattr(target, 'local_y', 0)
        half_w, half_h = 40, 19
        sx = tx - (px - half_w)
        sy = ty - (py - half_h) + 1
        if 0 <= sx < 80 and 1 <= sy < 40:
            console.print(sx, sy, "X", fg=(255, 40, 40), bg=(80, 10, 10))
        elif sx >= 80:
            console.print(79, max(1, min(39, sy)), ">", fg=(255, 40, 40))

        ctx.present(console)

        # ── Input ─────────────────────────────────────────────────────
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                raise SystemExit()
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                K = tcod.event.KeySym

                if sym == K.ESCAPE:
                    return

                # Snap shot (F) — fast, normal accuracy
                if sym == K.f:
                    if not weapon:
                        add_msg("No weapon!", "advisory")
                        break
                    if weapon.weapon_type == "firearm":
                        if weapon.extra.get("loaded", 0) <= 0:
                            add_msg(f"*click* — not loaded. [R] to reload.", "advisory")
                            break
                    _do_player_attack(engine, target, kind, weapon, aimed_part,
                                      dist, 0, add_msg, lmap, rng)
                    tick_time(ACTION_TIME["snap_shot"])
                    break

                # Careful aim (G) — slow, +5 roll bonus
                if sym == K.g:
                    if not weapon:
                        add_msg("No weapon!", "advisory")
                        break
                    if weapon.weapon_type == "firearm":
                        if weapon.extra.get("loaded", 0) <= 0:
                            add_msg(f"*click* — not loaded. [R] to reload.", "advisory")
                            break
                    add_msg("You take careful aim...", "normal")
                    tick_time(ACTION_TIME["careful_aim"] - ACTION_TIME["snap_shot"])
                    # Re-check target still alive/present
                    if kind == "npc" and (not target.alive or not target.present):
                        add_msg("Target gone.", "advisory")
                        break
                    if kind == "animal" and not target.alive:
                        add_msg("Target down.", "advisory")
                        break
                    dist = max(abs(getattr(target, 'local_x', 0) - engine.player.local_x),
                               abs(getattr(target, 'local_y', 0) - engine.player.local_y))
                    _do_player_attack(engine, target, kind, weapon, aimed_part,
                                      dist, 5, add_msg, lmap, rng)
                    tick_time(ACTION_TIME["snap_shot"])
                    break

                # Reload
                if sym == K.r:
                    if weapon and weapon.weapon_type == "firearm":
                        loaded = weapon.extra.get("loaded", 0)
                        cap = weapon.extra.get("capacity", 1)
                        if loaded >= cap:
                            add_msg("Already loaded.", "advisory")
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
                                reload_t = weapon.extra.get("reload_time", 15)
                                add_msg(f"Reloading... ({reload_t}s)", "normal")
                                tick_time(reload_t)
                                add_msg(f"Loaded {rounds}. ({weapon.extra['loaded']}/{cap})", "normal")
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

                # Aimed body part
                if sym in (K.N1, K.N2, K.N3, K.N4, K.N5,
                           K.KP_1, K.KP_2, K.KP_3, K.KP_4, K.KP_5):
                    idx_map = {K.N1: 0, K.N2: 1, K.N3: 2, K.N4: 3, K.N5: 4,
                               K.KP_1: 0, K.KP_2: 1, K.KP_3: 2, K.KP_4: 3, K.KP_5: 4}
                    aimed_part = idx_map.get(sym, 0)
                    add_msg(f"Aim: {AIMED_SHOTS[aimed_part][0]}", "advisory")
                    break

                # Wait
                if sym == K.SPACE:
                    add_msg("You hold.", "normal")
                    tick_time(ACTION_TIME["wait"])
                    break

                # Free look
                if sym == K.v:
                    _free_look(engine, console, ctx, target, lmap, _on_map, _animals)
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
                    nx = engine.player.local_x + dx
                    ny = engine.player.local_y + dy
                    if lmap.in_bounds(nx, ny) and lmap.is_passable(nx, ny):
                        engine.player.local_x = nx
                        engine.player.local_y = ny
                        engine.recompute_fov()
                        tick_time(ACTION_TIME["move"])
                    break


def _do_player_attack(engine, target, kind, weapon, aimed_part, dist,
                      accuracy_bonus, add_msg, lmap, rng):
    """Execute a player attack (shared by snap and careful aim)."""
    if kind == "npc":
        # Calculate cover between player and target
        t_cover = lmap.cover_between(
            engine.player.local_x, engine.player.local_y,
            target.local_x, target.local_y)
        evt = player_attack_npc(engine.player, target, weapon,
                                distance=dist, aimed_part=aimed_part,
                                accuracy_bonus=accuracy_bonus,
                                target_cover=t_cover)
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
        sp = target.species
        roll = rng.randint(1, 20)
        roll += engine.player.skills.get("firearms" if weapon.weapon_type == "firearm" else "survival", 0) // 2
        roll += engine.player.attributes.get("agility" if weapon.weapon_type == "firearm" else "strength", 10) // 3
        roll += accuracy_bonus
        aim = AIMED_SHOTS[aimed_part]
        roll += aim[1]
        defense = {"small": 12, "medium": 9, "large": 6, "very_large": 5}.get(sp.size, 8)
        if weapon.weapon_type == "firearm":
            if dist > 40:
                roll -= (dist - 40) // 5
            weapon.extra["loaded"] = weapon.extra.get("loaded", 1) - 1
        if roll >= defense:
            dmg = max(1, int(rng.randint(weapon.damage_min, weapon.damage_max) * aim[2]))
            if aim[3] == "head" and dmg >= 5 and rng.random() < 0.6:
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
        engine.player.gain_skill_xp(
            "firearms" if weapon.weapon_type == "firearm" else "survival", 2.0)


def _free_look(engine, console, ctx, target, lmap, on_map, animals):
    """Snap camera to target position temporarily."""
    px, py = engine.player.local_x, engine.player.local_y
    tx = getattr(target, 'local_x', px)
    ty = getattr(target, 'local_y', py)
    engine.player.local_x, engine.player.local_y = tx, ty
    engine.renderer.render_all(
        lmap, engine.world, engine.player, engine.messages,
        state="local_map", locals_dict=engine.locals)
    engine.renderer.draw_npcs(on_map, lmap, engine.player)
    engine.renderer.draw_wildlife(animals, lmap, engine.player)
    console.print(40, 20, "@", fg=(100, 100, 255))
    console.print(2, 0, "FREE LOOK — press any key", fg=(255, 255, 100), bg=(40, 40, 80))
    ctx.present(console)
    engine.player.local_x, engine.player.local_y = px, py
    for evt in tcod.event.wait():
        if isinstance(evt, (tcod.event.KeyDown, tcod.event.Quit)):
            break
