"""
src/ui_character.py

[C] Character menu — three tabs:
    Tab 1: Stats & Skills (attributes, skills with XP bars, knowledge)
    Tab 2: Health & Wounds (blood, pain, shock, detailed wound list)
    Tab 3: Reputation (per-region reputation display)
"""

import tcod.event
from typing import Any

from src.ui_framework import (
    TabbedMenu, MenuTab, MenuState, draw_list_item, draw_separator,
    WHITE, YELLOW, CYAN, GREEN, RED, GREY, DGREY, ORANGE, BG, BG2
)


# ============================================================================
#  TAB 1: STATS & SKILLS
# ============================================================================

def _draw_stats(con, x, y, w, h, state: MenuState, ctx: dict):
    player = ctx.get("player")
    if not player:
        return

    con.print(x + 1, y, f"{player.name}, age {player.age}", fg=YELLOW, bg=BG)
    y += 2

    # Attributes
    con.print(x + 1, y, "ATTRIBUTES", fg=GREY, bg=BG)
    y += 1
    for attr, val in player.attributes.items():
        bar_len = val
        bar = "█" * min(bar_len, 18) + "░" * max(0, 18 - bar_len)
        color = GREEN if val >= 12 else YELLOW if val >= 8 else RED
        con.print(x + 1, y, f"  {attr:<14} {val:>2}  {bar}", fg=color, bg=BG)
        y += 1

    y += 1
    con.print(x + 1, y, "SKILLS", fg=GREY, bg=BG)
    y += 1

    skills_sorted = sorted(player.skills.items(), key=lambda kv: -kv[1])
    for skill, level in skills_sorted:
        if level == 0 and player.skill_xp.get(skill, 0) == 0:
            continue  # hide completely unused skills
        xp = player.skill_xp.get(skill, 0)
        threshold = 100 + 10 * level
        xp_pct = min(1.0, xp / threshold) if threshold > 0 else 0
        bar_filled = int(xp_pct * 10)
        bar = "█" * bar_filled + "░" * (10 - bar_filled)
        color = GREEN if level >= 5 else YELLOW if level >= 2 else WHITE
        con.print(x + 1, y, f"  {skill:<14} {level:>2}  {bar}  ({xp:.0f}/{threshold})",
                  fg=color, bg=BG)
        y += 1
        if y >= ctx.get("_max_y", 999):
            break

    y += 1
    if player.knowledge:
        con.print(x + 1, y, "KNOWLEDGE", fg=GREY, bg=BG)
        y += 1
        k_labels = {0: "None", 1: "Partial", 2: "Working", 3: "Expert", 4: "Mastery"}
        for topic, level in sorted(player.knowledge.items()):
            label = k_labels.get(level, "?")
            color = GREEN if level >= 3 else YELLOW if level >= 1 else DGREY
            con.print(x + 1, y, f"  {topic:<20} {label}", fg=color, bg=BG)
            y += 1


def _handle_stats(sym, state: MenuState, ctx: dict) -> bool:
    K = tcod.event.KeySym
    if sym in (K.DOWN, K.KP_2):
        state.scroll += 1
        return True
    if sym in (K.UP, K.KP_8):
        state.scroll = max(0, state.scroll - 1)
        return True
    return False


# ============================================================================
#  TAB 2: HEALTH & WOUNDS
# ============================================================================

def _draw_health(con, x, y, w, h, state: MenuState, ctx: dict):
    player = ctx.get("player")
    if not player:
        return

    wounds = player.wounds
    survival = player.survival

    # Vitals
    con.print(x + 1, y, "VITALS", fg=YELLOW, bg=BG)
    y += 1
    vitals = [
        ("Health",  survival.health,  100),
        ("Hunger",  survival.hunger,  100),
        ("Thirst",  survival.thirst,  100),
        ("Warmth",  survival.warmth,  100),
        ("Fatigue", survival.fatigue, 100),
    ]
    for name, val, mx in vitals:
        pct = val / mx
        bar_len = int(pct * 15)
        bar = "█" * bar_len + "░" * (15 - bar_len)
        color = GREEN if pct > 0.6 else YELLOW if pct > 0.3 else RED
        con.print(x + 1, y, f"  {name:<10} {bar} {val:.0f}%", fg=color, bg=BG)
        y += 1

    y += 1

    # Blood / wounds
    lines = wounds.summary_lines()
    for line_text, line_color in lines:
        if y >= h + ctx.get("_start_y", 0):
            break
        con.print(x + 1, y, line_text[:w - 2], fg=line_color, bg=BG)
        y += 1

    # Treatment hint
    y += 1
    if wounds.wounds:
        con.print(x + 1, y, "Use [A]ctions to treat wounds (bandage, clean, etc.)",
                  fg=DGREY, bg=BG)


def _handle_health(sym, state: MenuState, ctx: dict) -> bool:
    K = tcod.event.KeySym
    if sym in (K.DOWN, K.KP_2):
        state.scroll += 1
        return True
    if sym in (K.UP, K.KP_8):
        state.scroll = max(0, state.scroll - 1)
        return True
    return False


# ============================================================================
#  TAB 3: REPUTATION
# ============================================================================

def _draw_reputation(con, x, y, w, h, state: MenuState, ctx: dict):
    rep_tracker = ctx.get("reputation")
    writing_mgr = ctx.get("writing")

    con.print(x + 1, y, "REGIONAL REPUTATION", fg=YELLOW, bg=BG)
    y += 2

    if not rep_tracker:
        con.print(x + 1, y, "No reputation data.", fg=GREY, bg=BG)
        return

    regions_with_rep = [(r, v) for r, v in sorted(rep_tracker.regions.items())
                        if abs(v) > 0.5]
    if not regions_with_rep:
        con.print(x + 1, y, "You are unknown everywhere.", fg=GREY, bg=BG)
        y += 2
    else:
        for region, val in regions_with_rep:
            label = rep_tracker.label(region)
            bar_center = 15
            bar = list("─" * 30)
            pos = int(bar_center + val * bar_center / 100)
            pos = max(0, min(29, pos))
            bar[pos] = "█"
            bar[bar_center] = "│"
            bar_str = "".join(bar)

            color = GREEN if val > 20 else RED if val < -20 else WHITE
            con.print(x + 1, y, f"  {region:<28} {bar_str} {label}",
                      fg=color, bg=BG)
            y += 1

    y += 1

    # Writer fame
    if writing_mgr:
        fame = writing_mgr.writer_fame()
        published = writing_mgr.published_count()
        royalties = writing_mgr.total_royalties_earned()
        if fame > 0 or published > 0:
            con.print(x + 1, y, "WRITER", fg=YELLOW, bg=BG)
            y += 1
            con.print(x + 1, y, f"  Published works: {published}", fg=WHITE, bg=BG)
            y += 1
            con.print(x + 1, y, f"  Writer fame: {fame:.0f}/100", fg=WHITE, bg=BG)
            y += 1
            con.print(x + 1, y, f"  Total royalties: ${royalties:.2f}", fg=GREEN, bg=BG)


def _handle_reputation(sym, state: MenuState, ctx: dict) -> bool:
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

def open_character(con, ctx, player, reputation=None, writing=None) -> None:
    tabs = [
        MenuTab("Stats", _draw_stats, _handle_stats),
        MenuTab("Health", _draw_health, _handle_health),
        MenuTab("Reputation", _draw_reputation, _handle_reputation),
    ]
    menu = TabbedMenu("CHARACTER", tabs, width=80, height=44)
    menu.run(con, ctx, player=player, reputation=reputation, writing=writing)
