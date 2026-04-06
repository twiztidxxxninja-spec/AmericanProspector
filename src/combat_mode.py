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
  Q       Flee combat (enemies get parting shot)
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


def _in_hand(player, item) -> bool:
    """Check if an item is held in either hand (case-insensitive)."""
    name = item.name.lower()
    rh = (player.right_hand or "").lower()
    lh = (player.left_hand or "").lower()
    return name == rh or name == lh


def _get_held_weapon(player):
    """Return the weapon currently in the player's hand, if any.
    Respects what the player has equipped — does NOT auto-swap."""
    rh = (player.right_hand or "").lower()
    lh = (player.left_hand or "").lower()
    # Check right hand first (primary)
    for i in player.inventory:
        if i.name.lower() == rh and i.weapon_type in ("firearm", "melee"):
            return i
    # Then left hand
    for i in player.inventory:
        if i.name.lower() == lh and i.weapon_type in ("firearm", "melee"):
            return i
    return None


def _best_weapon(player, auto_equip=True, prefer_ranged=True):
    """Find best weapon for initial combat entry.
    Only call this once at the start — after that use _get_held_weapon
    so the player's swap choice is respected."""
    # Loaded firearms in hand first
    for i in player.inventory:
        if _in_hand(player, i) and i.weapon_type == "firearm" \
                and i.extra.get("loaded", 0) > 0:
            return i

    # Loaded firearms in inventory
    firearms = [i for i in player.inventory
                if i.weapon_type == "firearm" and i.extra.get("loaded", 0) > 0]
    if firearms:
        weapon = firearms[0]
        if auto_equip:
            player.right_hand = weapon.name
        return weapon

    # Any firearm in hand (even unloaded — player may want to reload)
    for i in player.inventory:
        if _in_hand(player, i) and i.weapon_type == "firearm":
            return i

    # Melee in hand
    for i in player.inventory:
        if _in_hand(player, i) and i.weapon_type == "melee":
            return i

    # Melee in inventory
    melee = [i for i in player.inventory if i.weapon_type == "melee"]
    if melee:
        # Prefer actual weapons over tools (knife > pickaxe)
        real_weapons = [m for m in melee if m.category == "weapon"]
        weapon = real_weapons[0] if real_weapons else melee[0]
        if auto_equip:
            player.right_hand = weapon.name
        return weapon

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

def _npc_has_ranged(npc) -> bool:
    """Check if NPC actually has a ranged weapon."""
    from src.combat import _npc_weapon_profile, _is_ranged
    weapon_name, _, _, _ = _npc_weapon_profile(npc)
    return _is_ranged(weapon_name)


def _npc_decide(npc, player, lmap, rng) -> Tuple[str, int]:
    """NPC chooses an action and returns (action_name, time_cost).
    Called when NPC's action timer expires.

    Escalation rules:
    - If combat started as melee (fists/brawl), NPCs stay melee unless:
      1. Player pulls a firearm
      2. Someone gets badly hurt (< 30% HP)
      3. NPC has 'cruel' or 'psychopathic' trait
    - This prevents barfights from becoming shootouts.
    """
    dist = max(abs(npc.local_x - player.local_x),
               abs(npc.local_y - player.local_y))
    hp_pct = npc.health / max(getattr(npc.wounds, 'max_blood', 100), 1)

    has_gun = _npc_has_ranged(npc)

    # ── Escalation check ──────────────────────────────────────────
    # Track whether firearms have been introduced to this fight
    combat_escalated = getattr(npc, '_combat_escalated', False)
    if not combat_escalated and has_gun:
        # Check if player is using a firearm
        player_rh = (player.right_hand or "").lower()
        player_using_gun = any(
            i.weapon_type == "firearm" and i.name.lower() == player_rh
            for i in player.inventory)
        # Check if someone is badly hurt (fight got serious)
        badly_hurt = hp_pct < 0.30
        player_hp_pct = player.survival.health / max(100, 1)
        player_badly_hurt = player_hp_pct < 0.30
        # Cruel/psychopathic NPCs escalate immediately
        traits_lower = [t.lower() for t in getattr(npc, 'traits', [])]
        is_vicious = any(t in traits_lower for t in
                         ("cruel", "psychopathic", "hot-tempered"))
        if player_using_gun or badly_hurt or player_badly_hurt or is_vicious:
            npc._combat_escalated = True
            combat_escalated = True

    # If not escalated, suppress gun use — stay melee
    use_gun = has_gun and combat_escalated

    # Badly hurt — try to flee or surrender
    if hp_pct < 0.2:
        _check_npc_morale(npc)
        if npc.combat_state in ("fleeing", "surrendered"):
            return "flee", NPC_ACTION_TIME["move_away"]
        if use_gun:
            return "shoot", NPC_ACTION_TIME["shoot"]
        if dist <= 1:
            return "melee", 2
        return "flee", NPC_ACTION_TIME["move_away"]

    # Wounded and exposed — seek cover (only if guns drawn)
    current_cover = lmap.best_adjacent_cover(npc.local_x, npc.local_y)
    if use_gun and hp_pct < 0.5 and current_cover == 0 and rng.random() < 0.6:
        return "take_cover", NPC_ACTION_TIME["take_cover"]

    # At range with gun — shoot or careful aim
    if use_gun and dist > 3:
        if hp_pct > 0.7 and rng.random() < 0.3 and current_cover > 0:
            return "careful_aim", NPC_ACTION_TIME["careful_aim"]
        return "shoot", NPC_ACTION_TIME["shoot"]

    # Close range — melee
    if dist <= 1:
        return "melee", 2

    # Has gun at mid range and escalated — shoot
    if use_gun:
        return "shoot", NPC_ACTION_TIME["shoot"]

    # No gun or not escalated — close distance for melee
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
        # Only animate projectile for ranged attacks
        if action in ("shoot", "careful_aim") and _npc_has_ranged(npc):
            _play_sound("bang")
            half_w, half_h = 40, 19
            cam_x = player.local_x - half_w
            cam_y = player.local_y - half_h
            _animate_bullet(engine._console, engine._ctx,
                            npc.local_x, npc.local_y,
                            player.local_x, player.local_y,
                            cam_x, cam_y)
        # Calculate player's cover from NPC's perspective
        # Crouching behind partial cover = full cover
        p_cover = lmap.cover_between(
            npc.local_x, npc.local_y,
            player.local_x, player.local_y)
        from src.player import Stance
        if player.stance == Stance.CROUCHED and p_cover >= 1:
            p_cover = 2
        event = npc_attack_player(npc, player, player_cover=p_cover)
        sev = "critical" if event.hit else "normal"
        add_msg(event.message, sev)
        if action in ("shoot", "careful_aim"):
            _play_sound("hit" if event.hit else "miss")
            # NPC stray bullets on miss
            if not event.hit:
                import random as _sr
                if _sr.random() < 0.4:  # 40% chance stray hits something
                    _check_stray_bullet(engine, lmap,
                        npc.local_x, npc.local_y,
                        player.local_x, player.local_y,
                        15, add_msg,
                        console=engine._console, ctx=engine._ctx)
        if event.hit:
            engine._splatter_blood(lmap, player.local_x, player.local_y, 1)
        if getattr(event, 'player_captured', False):
            # Captured by tribal warriors — not dead
            engine.journal.end_combat()
            tribe = getattr(npc, 'tribe', '')
            if tribe and hasattr(engine, 'tribal'):
                day = engine.time.total_minutes // 1440
                cap_msg = engine.tribal.capture_player(tribe, day)
                engine.add_message(cap_msg, "critical")
            return  # exit combat — player is now captive
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

    engine.music.set_category("combat", immediate=True)
    add_msg("COMBAT!", "critical")

    # Auto-equip best weapon ONCE at combat start
    _best_weapon(engine.player, auto_equip=True)

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

        # Use whatever the player has equipped — respect their swap choice
        weapon = _get_held_weapon(engine.player)
        if weapon is None:
            # Nothing in hand at all — try to auto-equip
            weapon = _best_weapon(engine.player, auto_equip=True)
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

        # Player stance & cover
        stance = getattr(engine.player, 'stance', 'Standing')
        stance_fg = (180, 220, 140) if stance == "Crouched" else \
                    (100, 200, 255) if stance == "Prone" else (200, 200, 200)
        console.print(x, y, f"   Stance: {stance}", fg=stance_fg)
        y += 1
        p_cover = lmap.best_adjacent_cover(px, py)
        # Crouching behind partial cover = full cover
        effective_cover = p_cover
        if stance == "Crouched" and p_cover >= 1:
            effective_cover = 2
        if effective_cover >= 2:
            console.print(x, y, "   Cover: FULL", fg=(100, 200, 255))
        elif effective_cover == 1:
            console.print(x, y, "   Cover: Partial", fg=(180, 220, 140))
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
        console.print(x, y,     "[F] Snap shot  [G] Careful aim", fg=(120, 120, 120))
        console.print(x, y + 1, "[X] Melee  [Z] Grapple (adjacent)", fg=(120, 120, 120))
        console.print(x, y + 2, "[R]eload  [TAB] target", fg=(120, 120, 120))
        console.print(x, y + 3, "[1-5] Aim part  [SPACE] Wait", fg=(120, 120, 120))
        console.print(x, y + 4, "[T]hrow  [W] Swap  [C] Crouch/Stand", fg=(120, 120, 120))
        console.print(x, y + 5, "[X] Take cover  [I] Intimidate", fg=(120, 120, 120))
        # Show surrender option if target has surrendered
        if kind == "npc" and getattr(target, 'combat_state', '') == "surrendered":
            console.print(x, y + 6, "[S] Accept surrender", fg=(100, 255, 100))
            console.print(x, y + 7, "[V]iew  [arrows] Move  [Q] Flee", fg=(120, 120, 120))
        else:
            console.print(x, y + 6, "[V]iew  [arrows] Move  [Q] Flee", fg=(120, 120, 120))

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

                if sym in (K.ESCAPE, K.k):
                    return

                # Retreat — run away, hostiles get one free shot
                if sym == K.q:
                    # Flee combat — enemies get a parting shot
                    add_msg("You turn and run!", "critical")
                    for _d, _k, npc in hostiles:
                        if _k != "npc":
                            continue
                        if npc.alive and npc.combat_state == "hostile":
                            from src.combat import npc_attack_player
                            cover = 0  # running = no cover
                            evt = npc_attack_player(npc, engine.player, cover)
                            if evt.hit:
                                add_msg(f"  {evt.message}", "critical")
                            else:
                                add_msg(f"  {npc.name} fires — misses!", "advisory")
                    add_msg("You break contact and flee.", "advisory")
                    return

                # Melee attack (X) — move to target if within 3, attack adjacent
                if sym == K.x:
                    if dist <= 1:
                        # Adjacent — attack directly
                        melee_w = None
                        for i in engine.player.inventory:
                            if i.weapon_type == "melee" and (
                                i.name == engine.player.right_hand or
                                i.name == engine.player.left_hand):
                                melee_w = i
                                break
                        if not melee_w:
                            for i in engine.player.inventory:
                                if i.weapon_type == "melee":
                                    melee_w = i
                                    engine.player.right_hand = i.name
                                    break
                        _do_player_attack(engine, target, kind, melee_w, aimed_part,
                                          1, 0, add_msg, lmap, rng)
                        tick_time(ACTION_TIME["melee"])
                    elif dist <= 3:
                        # Close — rush toward target then attack
                        tx = getattr(target, 'local_x', px)
                        ty = getattr(target, 'local_y', py)
                        steps = dist - 1
                        for _ in range(steps):
                            dx = 1 if tx > engine.player.local_x else (-1 if tx < engine.player.local_x else 0)
                            dy = 1 if ty > engine.player.local_y else (-1 if ty < engine.player.local_y else 0)
                            nx = engine.player.local_x + dx
                            ny = engine.player.local_y + dy
                            if lmap.in_bounds(nx, ny) and lmap.is_passable(nx, ny):
                                engine.player.local_x = nx
                                engine.player.local_y = ny
                                cur_z = engine.player.local_z
                                target_z = int(lmap.surface_z[ny][nx])
                                if abs(target_z - cur_z) < 2:
                                    engine.player.local_z = target_z
                        add_msg("You rush forward!")
                        melee_w = None
                        for i in engine.player.inventory:
                            if i.weapon_type == "melee" and (
                                i.name == engine.player.right_hand or
                                i.name == engine.player.left_hand):
                                melee_w = i
                                break
                        _do_player_attack(engine, target, kind, melee_w, aimed_part,
                                          1, 0, add_msg, lmap, rng)
                        tick_time(ACTION_TIME["melee"] + steps * ACTION_TIME["move"])
                    else:
                        add_msg("Too far for melee. Get closer or use [F] to shoot.", "advisory")
                    break

                # Grapple (Z) — initiate wrestling at melee range
                if sym == K.z:
                    if kind != "npc":
                        add_msg("Can't grapple an animal.", "advisory")
                        break
                    if dist > 1:
                        add_msg("Too far to grapple. Get adjacent first.", "advisory")
                        break
                    try:
                        from src.grapple import (initiate_grapple, grapple_action,
                                                  npc_escape_attempt, grapple_tick,
                                                  GRAPPLE_ACTIONS, GRAPPLE_LABELS)
                        ok, msg, g_state = initiate_grapple(
                            engine.player, target, rng)
                        add_msg(msg)
                        if ok and g_state:
                            # Enter grapple sub-loop
                            while g_state:
                                # Draw grapple HUD
                                add_msg(f"  GRAPPLE [{g_state.hold_type}] "
                                        f"Control: {g_state.control}/100")
                                # Show options
                                from src.menus import pick_from_list
                                labels = [GRAPPLE_LABELS.get(a, a) for a in GRAPPLE_ACTIONS]
                                idx = pick_from_list(console, ctx,
                                    f"Grappling {target.name}", labels)
                                if idx is None:
                                    break
                                action_id = GRAPPLE_ACTIONS[idx]
                                g_msg, still_active = grapple_action(
                                    g_state, action_id, engine.player, target, rng)
                                add_msg(g_msg)
                                if not still_active:
                                    g_state = None
                                    break
                                # NPC escape attempt
                                esc_msg, escaped = npc_escape_attempt(
                                    g_state, engine.player, target, rng)
                                add_msg(esc_msg)
                                if escaped:
                                    g_state = None
                                    break
                                # Per-tick effects
                                tick_msg = grapple_tick(g_state, engine.player, target)
                                if tick_msg:
                                    add_msg(tick_msg)
                                if not target.alive:
                                    add_msg(f"{target.name} goes limp.")
                                    g_state = None
                                    break
                                tick_time(ACTION_TIME["melee"])
                    except ImportError:
                        add_msg("Grapple system not available.", "advisory")
                    break

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
                if sym in (K.N1, K.N2, K.N3, K.N4, K.N5, K.N6,
                           K.KP_1, K.KP_2, K.KP_3, K.KP_4, K.KP_5, K.KP_6):
                    idx_map = {K.N1: 0, K.N2: 1, K.N3: 2, K.N4: 3, K.N5: 4, K.N6: 5,
                               K.KP_1: 0, K.KP_2: 1, K.KP_3: 2, K.KP_4: 3, K.KP_5: 4, K.KP_6: 5}
                    aimed_part = idx_map.get(sym, 0)
                    add_msg(f"Aim: {AIMED_SHOTS[aimed_part][0]}", "advisory")
                    break

                # Wait
                if sym == K.SPACE:
                    add_msg("You hold.", "normal")
                    tick_time(ACTION_TIME["wait"])
                    break

                # Throw item at target
                if sym == K.t:
                    from src.menus import pick_from_list
                    throwables = [i for i in engine.player.inventory
                                  if getattr(i, "weight", 0) > 0]
                    if not throwables:
                        add_msg("Nothing to throw.", "advisory")
                        break
                    labels = [f"{i.name} ({i.weight:.1f} lb)" for i in throwables]
                    idx = pick_from_list(console, ctx, "Throw what?", labels)
                    if idx is None:
                        break
                    item = throwables[idx]
                    engine.player.inventory.remove(item)

                    try:
                        from src.wounds import throw_damage, throw_hit_chance
                        dmg, dtype = throw_damage(item)
                    except ImportError:
                        # Base damage from weight + sharpness bonus
                        base_dmg = max(1, int(item.weight * 2))
                        tags = getattr(item, "tool_tags", [])
                        is_sharp = any(t in tags for t in ("cut", "butcher", "skin", "chop"))
                        is_weapon = item.weapon_type in ("melee", "firearm")
                        if is_sharp or is_weapon:
                            # Sharp/pointed items do 3x weight + weapon damage
                            base_dmg = max(item.damage_max, int(item.weight * 3))
                            dtype = "slash"
                        else:
                            dtype = "blunt"
                        dmg = base_dmg

                    # Hit check: agility + strength vs distance
                    hit_roll = random.randint(1, 20) + \
                        engine.player.attributes.get("agility", 10) // 3 + \
                        engine.player.attributes.get("strength", 10) // 4
                    if kind == "npc":
                        defense = 8 + target.attributes.get("agility", 10) // 3
                    else:
                        defense = {"small": 12, "medium": 9, "large": 6,
                                   "very_large": 5}.get(target.species.size, 8)
                    hit_roll -= max(0, (dist - 5)) // 3  # range penalty

                    if hit_roll >= defense:
                        if kind == "npc":
                            wkey = ""
                            if dtype == "slash":
                                wkey = "knife"  # sharp thrown = knife-type wound
                            wound = target.wounds.apply_hit(
                                dmg, dtype, weapon_key=wkey)
                            from src.health_system import PART_HP
                            hp_dmg = min(dmg, PART_HP.get(
                                wound.part if hasattr(wound, 'part') else '', 100))
                            target.health -= hp_dmg
                            _check_npc_morale(target)
                            engine._splatter_blood(lmap, target.local_x,
                                                   target.local_y, 1)
                            if dtype == "slash":
                                add_msg(f"The {item.name} buries itself in "
                                        f"{target.display_name()}. {wound.description}")
                            else:
                                add_msg(f"You hurl the {item.name} at "
                                        f"{target.display_name()}. It connects hard.")
                            if target.combat_state == "dead":
                                add_msg(f"{target.name} drops.", "critical")
                                engine.journal.log_enemy_killed(target.name)
                        else:
                            target.take_damage(float(dmg))
                            if dtype == "slash":
                                add_msg(f"The {item.name} sticks in the "
                                        f"{target.species.display_name}.")
                            else:
                                add_msg(f"The {item.name} hits the "
                                        f"{target.species.display_name}.")
                    else:
                        add_msg(f"You throw the {item.name}. It misses.")

                    # Item lands on ground (miss or blunt hit) or lodges (sharp hit)
                    if hit_roll < defense or dtype != "slash":
                        tx = getattr(target, 'local_x', px)
                        ty = getattr(target, 'local_y', py)
                        if lmap.in_bounds(tx, ty):
                            lmap.tiles[ty][tx].ground_items.append(item)
                    # Sharp hits that connect: item is lodged in target (gone)

                    tick_time(ACTION_TIME["snap_shot"])
                    break

                # Swap weapon
                if sym == K.w:
                    from src.menus import pick_from_list
                    weapons = [i for i in engine.player.inventory if i.is_weapon()]
                    if not weapons:
                        add_msg("No weapons in inventory.", "advisory")
                        break
                    labels = []
                    for w in weapons:
                        eq = ""
                        if w.name == engine.player.right_hand:
                            eq = " [R.Hand]"
                        elif w.name == engine.player.left_hand:
                            eq = " [L.Hand]"
                        ammo = ""
                        if w.weapon_type == "firearm":
                            ammo = f" ({w.extra.get('loaded', 0)}/{w.extra.get('capacity', 1)})"
                        labels.append(f"{w.name}{ammo}{eq}")
                    idx = pick_from_list(console, ctx, "Equip which weapon?", labels)
                    if idx is not None and idx < len(weapons):
                        chosen = weapons[idx]
                        hand = pick_from_list(console, ctx,
                            f"Equip {chosen.name} to which hand?",
                            [f"Right hand (current: {engine.player.right_hand or 'empty'})",
                             f"Left hand (current: {engine.player.left_hand or 'empty'})",
                             "Both hands"])
                        if hand == 0:
                            engine.player.right_hand = chosen.name
                        elif hand == 1:
                            engine.player.left_hand = chosen.name
                        elif hand == 2:
                            engine.player.right_hand = chosen.name
                            engine.player.left_hand = chosen.name
                        if hand is not None:
                            add_msg(f"You ready the {chosen.name}.", "normal")
                    break

                # Crouch / Stand — toggle stance
                if sym == K.c:
                    from src.player import Stance
                    if engine.player.stance == Stance.STANDING:
                        engine.player.stance = Stance.CROUCHED
                        add_msg("You crouch low.", "normal")
                    elif engine.player.stance == Stance.CROUCHED:
                        engine.player.stance = Stance.STANDING
                        add_msg("You stand up.", "normal")
                    tick_time(1)
                    break

                # Take cover — auto-move to nearest cover tile
                if sym == K.x:
                    best_cx, best_cy, best_d = px, py, 999
                    for _dy in range(-5, 6):
                        for _dx in range(-5, 6):
                            _nx, _ny = px + _dx, py + _dy
                            if not lmap.in_bounds(_nx, _ny) or \
                                    not lmap.is_passable(_nx, _ny):
                                continue
                            cv = lmap.cover_at(_nx, _ny) + \
                                 lmap.best_adjacent_cover(_nx, _ny)
                            if cv > 0:
                                _d = abs(_dx) + abs(_dy)
                                if _d < best_d and _d > 0:
                                    best_d = _d
                                    best_cx, best_cy = _nx, _ny
                    if best_d < 999:
                        # Rush to cover — move up to 3 tiles toward it
                        steps = min(3, best_d)
                        for _ in range(steps):
                            _sdx = (1 if best_cx > engine.player.local_x else
                                    -1 if best_cx < engine.player.local_x else 0)
                            _sdy = (1 if best_cy > engine.player.local_y else
                                    -1 if best_cy < engine.player.local_y else 0)
                            _snx = engine.player.local_x + _sdx
                            _sny = engine.player.local_y + _sdy
                            if lmap.in_bounds(_snx, _sny) and \
                                    lmap.is_passable(_snx, _sny):
                                engine.player.local_x = _snx
                                engine.player.local_y = _sny
                        from src.player import Stance
                        engine.player.stance = Stance.CROUCHED
                        add_msg("You dive for cover!", "normal")
                        tick_time(ACTION_TIME["move"] + 1)
                        engine.recompute_fov()
                    else:
                        add_msg("No cover nearby!", "advisory")
                    break

                # Accept surrender — disarm and release
                if sym == K.s and kind == "npc" and \
                        getattr(target, 'combat_state', '') == "surrendered":
                    from src.menus import pick_from_list
                    choices = ["Disarm and release", "Take their gear",
                               "Let them go"]
                    sidx = pick_from_list(console, ctx,
                        f"{target.name} has surrendered.", choices)
                    if sidx == 0:
                        # Disarm — take weapon, release
                        if hasattr(target, 'inventory') and target.inventory:
                            weapons = [i for i in target.inventory
                                       if getattr(i, 'weapon_type', '')]
                            for w in weapons:
                                target.inventory.remove(w)
                                engine.player.inventory.append(w)
                                add_msg(f"You take {target.name}'s {w.name}.")
                        target.combat_state = "neutral"
                        target.present = True
                        add_msg(f"{target.name} backs away, hands up. "
                                f"The fight is over.")
                        if hasattr(target, 'rel'):
                            target.rel.fear = min(100, target.rel.fear + 30)
                        engine.journal.end_combat()
                        return
                    elif sidx == 1:
                        # Loot all gear
                        if hasattr(target, 'inventory'):
                            for item in list(target.inventory):
                                engine.player.inventory.append(item)
                            target.inventory.clear()
                        add_msg(f"You strip {target.name} of everything.")
                        target.combat_state = "neutral"
                        if hasattr(target, 'rel'):
                            target.rel.affinity -= 40
                            target.rel.fear = min(100, target.rel.fear + 40)
                        engine.journal.end_combat()
                        return
                    elif sidx == 2:
                        target.combat_state = "neutral"
                        add_msg(f"You let {target.name} go.")
                        if hasattr(target, 'rel'):
                            target.rel.affinity += 10
                        engine.journal.end_combat()
                        return
                    break

                # Intimidate — force morale check on target
                if sym == K.i:
                    if kind != "npc":
                        add_msg("You can't intimidate an animal.", "advisory")
                        break
                    cha = engine.player.attributes.get("charisma", 10)
                    fear = getattr(target.rel, 'fear', 0) if hasattr(target, 'rel') else 0
                    # Roll: d20 + charisma/3 + fear/10 vs NPC willpower
                    import random as _irng
                    i_roll = _irng.randint(1, 20) + cha // 3 + fear // 10
                    npc_will = 10 + target.attributes.get("wisdom", 10) // 3
                    # Weapon in hand helps — pointing a gun is scarier
                    if weapon and weapon.weapon_type == "firearm":
                        loaded = weapon.extra.get("loaded", 0)
                        if loaded > 0:
                            i_roll += 4  # loaded gun pointed at them
                    # Being wounded helps (their fear)
                    t_hp_pct = target.health / max(
                        getattr(target.wounds, 'max_blood', 100), 1)
                    if t_hp_pct < 0.5:
                        i_roll += 3
                    # Brave NPCs resist, cowardly ones fold
                    if "brave" in target.traits:
                        npc_will += 4
                    if "coward" in target.traits or "nervous" in target.traits:
                        npc_will -= 4
                    if i_roll >= npc_will:
                        target.combat_state = "surrendered"
                        surrender_msgs = [
                            f'*{target.name} throws up his hands.* "Alright! Alright! Don\'t shoot!"',
                            f'*{target.name} drops his weapon.* "I give! I give!"',
                            f'*{target.name} goes pale.* "Please... I got a family."',
                            f'*{target.name} backs away, hands up.* "Take what you want. Just let me go."',
                        ]
                        add_msg(_irng.choice(surrender_msgs), "normal")
                        if hasattr(target, 'rel'):
                            target.rel.fear = min(100, fear + 20)
                    elif i_roll >= npc_will - 3:
                        add_msg(f"*{target.name} hesitates.* "
                                f"He's scared but not ready to give up yet.", "normal")
                        if hasattr(target, 'rel'):
                            target.rel.fear = min(100, fear + 10)
                    else:
                        taunt_backs = [
                            f'*{target.name} spits.* "Go to hell."',
                            f'"You don\'t scare me." *{target.name} raises his weapon.*',
                            f'*{target.name} laughs.* "That the best you got?"',
                        ]
                        add_msg(_irng.choice(taunt_backs), "normal")
                    tick_time(2)
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
                    if engine.check_edge_transition(nx, ny):
                        add_msg("You leave the fight behind.", "normal")
                        return  # exited combat via map edge
                    if lmap.in_bounds(nx, ny) and lmap.is_passable(nx, ny):
                        cur_z = engine.player.local_z
                        target_z = int(lmap.surface_z[ny][nx])
                        if abs(target_z - cur_z) >= 2:
                            break  # cliff
                        engine.player.local_x = nx
                        engine.player.local_y = ny
                        if target_z != cur_z:
                            engine.player.local_z = target_z
                        engine.recompute_fov()
                        # Crouched movement costs double
                        move_cost = ACTION_TIME["move"]
                        if engine.player.stance == "Crouched":
                            move_cost = int(move_cost * 1.5)
                        tick_time(move_cost)
                    break


def _do_player_attack(engine, target, kind, weapon, aimed_part, dist,
                      accuracy_bonus, add_msg, lmap, rng):
    """Execute a player attack (shared by snap and careful aim)."""
    # Projectile animation for ranged weapons
    is_firearm = weapon and weapon.weapon_type == "firearm"
    is_shotgun = is_firearm and weapon and "shotgun" in weapon.name.lower()
    is_bow = is_firearm and weapon and "bow" in weapon.name.lower()
    if is_firearm:
        if not is_bow:
            _play_sound("bang")
        # Bows are silent — no sound
        half_w = 40
        half_h = 19
        cam_x = engine.player.local_x - half_w
        cam_y = engine.player.local_y - half_h
        _animate_bullet(engine._console, engine._ctx,
                        engine.player.local_x, engine.player.local_y,
                        getattr(target, 'local_x', 0), getattr(target, 'local_y', 0),
                        cam_x, cam_y, weapon=weapon)

    # Shotgun pellet mechanics
    if is_shotgun:
        import math
        from src.health_system import BP, ALL_BODY_PARTS
        num_pellets = 8
        if dist <= 4:
            # Close range: all pellets hit same area — devastating
            add_msg(f"Full blast at close range.")
        elif dist <= 15:
            # Medium range: pellets hit different body parts
            hit_parts = random.choices(ALL_BODY_PARTS, k=min(num_pellets, 4))
            part_counts = {}
            for p in hit_parts:
                part_counts[p] = part_counts.get(p, 0) + 1
            from src.health_system import PART_DATA
            hit_desc = ", ".join(f"{PART_DATA[p]['label']}x{c}" if c > 1
                                 else PART_DATA[p]['label']
                                 for p, c in part_counts.items())
            add_msg(f"Pellets scatter: {hit_desc}.")
        else:
            # Long range: pellets spread wide, only 1-2 hit
            add_msg(f"At this range the shot pattern is wide. Weak hits.")

        # Cone collateral — check for other targets in the spread
        if dist > 4:
            tx = getattr(target, 'local_x', 0)
            ty = getattr(target, 'local_y', 0)
            base_angle = math.atan2(ty - engine.player.local_y,
                                    tx - engine.player.local_x)
            for n in engine._tile_npcs():
                if n is target or not n.alive:
                    continue
                ndx = n.local_x - engine.player.local_x
                ndy = n.local_y - engine.player.local_y
                n_angle = math.atan2(ndy, ndx)
                angle_diff = abs(n_angle - base_angle)
                if angle_diff > math.pi:
                    angle_diff = 2 * math.pi - angle_diff
                n_dist = max(abs(ndx), abs(ndy))
                if angle_diff < 0.25 and n_dist <= dist + 5:
                    pellet_dmg = max(1, weapon.damage_max // 4)
                    n.health -= pellet_dmg
                    from src.combat import _check_npc_morale
                    _check_npc_morale(n)
                    engine._splatter_blood(lmap, n.local_x, n.local_y, 1)
                    add_msg(f"Stray pellets hit {n.display_name()}!")

    if kind == "npc":
        # Calculate cover between player and target
        t_cover = lmap.cover_between(
            engine.player.local_x, engine.player.local_y,
            target.local_x, target.local_y)
        evt = player_attack_npc(engine.player, target, weapon,
                                distance=dist, aimed_part=aimed_part,
                                accuracy_bonus=accuracy_bonus,
                                target_cover=t_cover,
                                weather=engine.time.weather)
        add_msg(evt.message, "critical" if evt.killed else "normal")
        # Sound effect
        if is_firearm:
            _play_sound("hit" if evt.hit else "miss")
        # Stray bullet on miss — check for collateral
        if not evt.hit and evt.stray_bullet:
            dmg = weapon.damage_max if weapon else 10
            _check_stray_bullet(engine, lmap,
                engine.player.local_x, engine.player.local_y,
                target.local_x, target.local_y, dmg, add_msg,
                console=engine._console, ctx=engine._ctx)
        if evt.hit:
            skill = "firearms" if weapon and weapon.weapon_type == "firearm" else "survival"
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
        # ── Animal attack — uses wound system like NPCs ──────────────
        sp = target.species
        roll = rng.randint(1, 20)
        w_type = weapon.weapon_type if weapon else "melee"
        w_name = weapon.name if weapon else "fists"
        roll += engine.player.skills.get("firearms" if w_type == "firearm" else "survival", 0) // 2
        roll += engine.player.attributes.get("agility" if w_type == "firearm" else "strength", 10) // 3
        roll += accuracy_bonus
        aim = AIMED_SHOTS[aimed_part]
        roll += aim[1]
        defense = {"small": 12, "medium": 9, "large": 6, "very_large": 5}.get(sp.size, 8)
        if weapon and weapon.weapon_type == "firearm":
            if dist > 40:
                roll -= (dist - 40) // 5
            weapon.extra["loaded"] = weapon.extra.get("loaded", 0) - 1

        if roll >= defense:
            if weapon:
                raw = rng.randint(weapon.damage_min, weapon.damage_max)
            else:
                raw = rng.randint(1, 4)
            dmg = max(1, int(raw * aim[2]))

            # Headshot instant kill
            if aim[3] == "head" and dmg >= 5 and rng.random() < 0.6:
                dmg = max(dmg, int(target.health) + 10)

            # Map aimed part to animal body part
            from src.combat import _weapon_damage_type, _weapon_key
            _AIM_TO_ANIMAL = {
                "head": "head", "torso": "chest",
                "legs": "r_hindleg", "arms": "r_foreleg", "groin": "abdomen",
            }
            aim_special = aim[3]
            wound_part = _AIM_TO_ANIMAL.get(aim_special)
            # For small quadrupeds, map chest→body
            if wound_part == "chest" and target.wounds.body_plan_name == "small_quadruped":
                wound_part = "body"

            # Apply wound through wound system (generates DetailedWound)
            dmg_type = _weapon_damage_type(w_name)
            wound = target.wounds.apply_hit(
                dmg, dmg_type,
                target_part=wound_part,
                weapon_key=_weapon_key(w_name))
            target.health = max(0.0, target.health - dmg)

            # Update state from health
            if target.health <= 0:
                target.state = "dead"
            elif target.health < target.species.meat_yield_lb * 0.2:
                target.state = "downed"
            elif target.health < target.species.meat_yield_lb * 0.55:
                target.state = "wounded_fleeing"
                target.wound_flee_steps = rng.randint(10, 30)

            # Get wound description for the message
            part_hit = wound.part if hasattr(wound, 'part') else ""
            wound_desc = wound.description if hasattr(wound, 'description') else ""
            from src.health_system import PART_DATA, BODY_PLANS
            plan = BODY_PLANS.get(target.wounds.body_plan_name, BODY_PLANS.get("quadruped", {}))
            plan_data = plan.get("part_data", PART_DATA)
            part_label = plan_data.get(part_hit, {}).get("label", part_hit)

            engine._splatter_blood(lmap, target.local_x, target.local_y,
                                   2 if target.state == "dead" else 1)

            # Build visceral message
            name = sp.display_name
            is_firearm = weapon and weapon.weapon_type == "firearm"
            is_shotgun = is_firearm and "shotgun" in w_name.lower()

            if target.state == "dead":
                if aim_special == "head" and dmg >= 8:
                    kill_msgs = [
                        f"The shot takes the {name}'s head apart. It drops instantly.",
                        f"The {name}'s skull explodes. Dead before it hits the ground.",
                        f"A clean head shot. The {name} crumples without a sound.",
                    ]
                elif is_shotgun:
                    kill_msgs = [
                        f"The shotgun blast tears the {name} open. It's done.",
                        f"The {name} is blown sideways by the blast. It doesn't get up.",
                    ]
                elif is_firearm:
                    kill_msgs = [
                        f"The ball punches through the {name}'s {part_label.lower()}. "
                        f"It staggers, then drops.",
                        f"The {name} takes the shot in the {part_label.lower()} and goes down hard.",
                        f"A killing shot to the {part_label.lower()}. The {name} folds.",
                    ]
                else:
                    kill_msgs = [
                        f"The {w_name} catches the {name} in the {part_label.lower()}. "
                        f"It drops.",
                        f"A killing blow to the {part_label.lower()}. The {name} is dead.",
                    ]
                add_msg(rng.choice(kill_msgs), "normal")
                engine._blood_pool(lmap, target.local_x, target.local_y, 2, True)
                engine.journal.log_enemy_killed(name)

            elif target.state == "downed":
                down_msgs = [
                    f"The shot shatters the {name}'s {part_label.lower()}. "
                    f"It collapses, breathing hard.",
                    f"The {name}'s {part_label.lower()} gives out. "
                    f"It goes down, thrashing.",
                    f"A solid hit to the {part_label.lower()}. The {name} drops, "
                    f"legs kicking.",
                ]
                add_msg(rng.choice(down_msgs), "normal")

            elif target.state == "wounded_fleeing":
                flee_msgs = [
                    f"The shot hits the {name} in the {part_label.lower()}. "
                    f"{wound_desc}. It bolts, bleeding.",
                    f"You catch the {name} in the {part_label.lower()}. "
                    f"Blood sprays. It runs, stumbling.",
                    f"The {name} takes the hit in the {part_label.lower()} and "
                    f"breaks into a panicked run, leaving a blood trail.",
                ]
                add_msg(rng.choice(flee_msgs), "normal")

            else:
                # Hit but not critical
                hit_msgs = [
                    f"The shot catches the {name} in the {part_label.lower()}. "
                    f"{wound_desc}.",
                    f"You hit the {name}'s {part_label.lower()}. {wound_desc}. "
                    f"It snarls.",
                    f"A hit to the {part_label.lower()}. {wound_desc}. "
                    f"The {name} flinches but stays up.",
                ]
                add_msg(rng.choice(hit_msgs), "normal")
        else:
            miss_msgs = [
                f"The shot misses the {sp.display_name}.",
                f"The {sp.display_name} dodges. The shot kicks up dirt behind it.",
                f"You fire — the {sp.display_name} flinches but you missed.",
            ]
            add_msg(rng.choice(miss_msgs), "normal")
        engine.player.gain_skill_xp(
            "firearms" if weapon and weapon.weapon_type == "firearm" else "survival", 2.0)


def _play_sound(sound_type: str):
    """Play a short combat sound effect via pygame mixer."""
    try:
        import pygame
        if not pygame.mixer.get_init():
            return
        # Generate simple sound from frequency
        import numpy as np
        sample_rate = 22050
        if sound_type == "bang":
            # Gunshot: sharp noise burst
            duration = 0.15
            t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
            wave = np.random.uniform(-0.8, 0.8, len(t)).astype(np.float32)
            wave *= np.exp(-t * 20)  # fast decay
        elif sound_type == "hit":
            # Meaty thud
            duration = 0.1
            t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
            wave = np.sin(2 * np.pi * 120 * t).astype(np.float32) * 0.5
            wave *= np.exp(-t * 15)
        elif sound_type == "miss":
            # Whizz/ricochet
            duration = 0.2
            t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
            freq = 800 + t * 2000  # rising pitch
            wave = np.sin(2 * np.pi * freq * t).astype(np.float32) * 0.3
            wave *= np.exp(-t * 8)
        else:
            return
        # Convert to 16-bit
        wave_int = (wave * 32767).astype(np.int16)
        sound = pygame.mixer.Sound(wave_int)
        sound.set_volume(0.4)
        sound.play()
    except Exception:
        pass


def _animate_bullet(console, ctx, px, py, tx, ty, cam_x, cam_y,
                    weapon=None):
    """Draw a projectile traveling from (px,py) to (tx,ty) on screen.
    Shotguns fire a spreading cone of pellets."""
    import time, math

    is_shotgun = weapon and "shotgun" in weapon.name.lower()
    is_bow = weapon and "bow" in weapon.name.lower()

    dx = tx - px
    dy = ty - py
    steps = max(abs(dx), abs(dy))
    if steps == 0:
        return

    if is_bow:
        # Arrow: slower flight, consistent arrow glyph by direction
        if abs(dx) > abs(dy) * 2:
            glyph = ">" if dx > 0 else "<"
        elif abs(dy) > abs(dx) * 2:
            glyph = "v" if dy > 0 else "^"
        elif (dx > 0) == (dy > 0):
            glyph = "\\"
        else:
            glyph = "/"
        for i in range(1, steps + 1):
            frac = i / steps
            bx = int(px + dx * frac)
            by = int(py + dy * frac)
            sx = bx - cam_x
            sy = by - cam_y + 1
            if 0 <= sx < 80 and 1 <= sy < 40:
                console.print(sx, sy, glyph, fg=(180, 140, 80), bg=(30, 20, 10))
                ctx.present(console)
                time.sleep(0.035)  # slower than bullets
        return

    if is_shotgun:
        # Shotgun: single slug for first 4 tiles, then pellets spread
        spread_start = 4  # tiles before shot pattern opens up
        base_angle = math.atan2(dy, dx)
        # Direction glyph for the slug phase
        if abs(dx) > abs(dy) * 2:
            slug_glyph = "-"
        elif abs(dy) > abs(dx) * 2:
            slug_glyph = "|"
        elif (dx > 0) == (dy > 0):
            slug_glyph = "\\"
        else:
            slug_glyph = "/"

        for i in range(1, steps + 1):
            if i <= spread_start:
                # Tight group — render as single projectile
                bx = int(px + math.cos(base_angle) * i)
                by = int(py + math.sin(base_angle) * i)
                sx = bx - cam_x
                sy = by - cam_y + 1
                if 0 <= sx < 80 and 1 <= sy < 40:
                    console.print(sx, sy, slug_glyph, fg=(255, 255, 200), bg=(80, 40, 10))
            else:
                # Spread — 5 pellets fanning out
                pellet_angles = [base_angle + a for a in (-0.12, -0.06, 0, 0.06, 0.12)]
                for pa in pellet_angles:
                    bx = int(px + math.cos(pa) * i)
                    by = int(py + math.sin(pa) * i)
                    sx = bx - cam_x
                    sy = by - cam_y + 1
                    if 0 <= sx < 80 and 1 <= sy < 40:
                        console.print(sx, sy, ".", fg=(255, 200, 100), bg=(60, 30, 5))
            ctx.present(console)
            time.sleep(0.02)
    else:
        # Single projectile — consistent bullet glyph
        # Direction determines glyph: - horizontal, | vertical, / \ diagonal
        if abs(dx) > abs(dy) * 2:
            glyph = "-"
        elif abs(dy) > abs(dx) * 2:
            glyph = "|"
        elif (dx > 0) == (dy > 0):
            glyph = "\\"
        else:
            glyph = "/"

        for i in range(1, steps + 1):
            frac = i / steps
            bx = int(px + dx * frac)
            by = int(py + dy * frac)
            sx = bx - cam_x
            sy = by - cam_y + 1
            if 0 <= sx < 80 and 1 <= sy < 40:
                console.print(sx, sy, glyph, fg=(255, 255, 200), bg=(80, 40, 10))
                ctx.present(console)
                time.sleep(0.02)


def _check_stray_bullet(engine, lmap, px, py, tx, ty, dmg, add_msg,
                        console=None, ctx=None):
    """Trace bullet path past target with scatter angle, check for collateral."""
    import math
    dx = tx - px
    dy = ty - py
    length = max(abs(dx), abs(dy))
    if length == 0:
        return

    # Add scatter angle — wider miss = bigger angle (up to ±15 degrees)
    base_angle = math.atan2(dy, dx)
    scatter = random.uniform(-0.26, 0.26)  # ±15 degrees in radians
    angle = base_angle + scatter
    ndx = math.cos(angle)
    ndy = math.sin(angle)

    # Animate the stray bullet path
    half_w, half_h = 40, 19
    cam_x = engine.player.local_x - half_w
    cam_y = engine.player.local_y - half_h

    for step in range(1, 25):
        bx = int(tx + ndx * step)
        by = int(ty + ndy * step)
        if not lmap.in_bounds(bx, by):
            break
        # Animate stray bullet with direction-consistent glyph
        if console and ctx:
            sx = bx - cam_x
            sy = by - cam_y + 1
            if 0 <= sx < 80 and 1 <= sy < 40:
                import time
                if abs(ndx) > abs(ndy) * 2:
                    g = "-"
                elif abs(ndy) > abs(ndx) * 2:
                    g = "|"
                elif (ndx > 0) == (ndy > 0):
                    g = "\\"
                else:
                    g = "/"
                console.print(sx, sy, g, fg=(255, 180, 60), bg=(40, 20, 5))
                ctx.present(console)
                time.sleep(0.015)
        # Hit terrain that blocks?
        from src.local_map import LocalTerrain
        t = lmap.tiles[by][bx].terrain
        if t == LocalTerrain.ROCK:
            add_msg("The stray bullet ricochets off rock.")
            break

        # Hit a tree?
        tree_terrains = (LocalTerrain.PINE, LocalTerrain.OAK, LocalTerrain.CEDAR,
                         LocalTerrain.MAPLE, LocalTerrain.FOREST)
        if t in tree_terrains:
            if random.random() < 0.3:
                add_msg("The bullet thuds into a tree trunk.")
                break

        # Hit an NPC?
        for n in engine._tile_npcs():
            if n.alive and n.local_x == bx and n.local_y == by:
                n.health -= dmg * 0.7  # reduced damage
                from src.combat import _check_npc_morale
                _check_npc_morale(n)
                engine._splatter_blood(lmap, bx, by, 2)
                add_msg(f"The stray bullet hits {n.name}!", "critical")
                return

        # Hit an animal?
        for a in engine.wildlife_mgr.get_animals(
                engine.player.world_x, engine.player.world_y,
                engine.player.area_x, engine.player.area_y):
            if a.alive and a.local_x == bx and a.local_y == by:
                a.take_damage(dmg * 0.7)
                engine._splatter_blood(lmap, bx, by, 1)
                add_msg(f"The stray bullet hits a {a.species.display_name}!")
                return


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
