"""
src/ui_journal.py

[J] Journal menu — six tabs:
    Tab 1: Diary (existing entries)
    Tab 2: People (met NPCs)
    Tab 3: Places (discovered locations)
    Tab 4: Rumors (heard from NPCs)
    Tab 5: Mail (letters at post office + in transit)
    Tab 6: Write (compose diary/letter/poem/article/book)
"""

import tcod.event
from typing import Any

from src.ui_framework import (
    TabbedMenu, MenuTab, MenuState, draw_list_item, draw_text_input,
    wrap_text, WHITE, YELLOW, CYAN, GREEN, RED, GREY, DGREY, ORANGE, BG, BG2
)


# ============================================================================
#  TAB 1: DIARY
# ============================================================================

def _draw_diary(con, x, y, w, h, state: MenuState, ctx: dict):
    journal = ctx.get("journal")
    if not journal or not journal.diary:
        con.print(x + 1, y + 1, "No diary entries yet.", fg=GREY, bg=BG)
        return
    entries = list(reversed(journal.diary))
    row = y
    for entry in entries[state.scroll:]:
        if row >= y + h:
            break
        con.print(x + 1, row, entry.date_str, fg=YELLOW, bg=BG)
        row += 1
        for line in wrap_text(entry.text, w - 4):
            if row >= y + h:
                break
            con.print(x + 3, row, line, fg=WHITE, bg=BG)
            row += 1
        row += 1

def _handle_diary(sym, state, ctx):
    K = tcod.event.KeySym
    if sym in (K.DOWN, K.KP_2): state.scroll += 1; return True
    if sym in (K.UP, K.KP_8): state.scroll = max(0, state.scroll - 1); return True
    return False


# ============================================================================
#  TAB 2: PEOPLE
# ============================================================================

def _draw_people(con, x, y, w, h, state: MenuState, ctx: dict):
    npc_mgr = ctx.get("npc_manager")
    if not npc_mgr:
        con.print(x + 1, y + 1, "No NPC manager.", fg=GREY, bg=BG)
        return
    npcs = [n for n in npc_mgr.npcs.values() if n.memory.knows_name]
    if not npcs:
        con.print(x + 1, y + 1, "You haven't met anyone yet.", fg=GREY, bg=BG)
        return
    for i, npc in enumerate(npcs[state.scroll:state.scroll + h]):
        rel_color = GREEN if npc.relationship > 20 else \
                    RED if npc.relationship < -5 else WHITE
        con.print(x + 1, y + i,
                  f"{npc.name:<20} {npc.occupation:<14} {npc.rel_label()}",
                  fg=rel_color, bg=BG)

def _handle_people(sym, state, ctx):
    K = tcod.event.KeySym
    if sym in (K.DOWN, K.KP_2): state.scroll += 1; return True
    if sym in (K.UP, K.KP_8): state.scroll = max(0, state.scroll - 1); return True
    return False


# ============================================================================
#  TAB 3: PLACES
# ============================================================================

def _draw_places(con, x, y, w, h, state: MenuState, ctx: dict):
    journal = ctx.get("journal")
    if not journal or not journal.places:
        con.print(x + 1, y + 1, "No places noted.", fg=GREY, bg=BG)
        return
    for i, place in enumerate(journal.places[state.scroll:]):
        row = y + i * 2
        if row >= y + h:
            break
        con.print(x + 1, row,
                  f"{place.name}  [{place.world_x},{place.world_y}]",
                  fg=YELLOW, bg=BG)
        if place.notes and row + 1 < y + h:
            con.print(x + 3, row + 1, place.notes[:w - 4], fg=WHITE, bg=BG)

def _handle_places(sym, state, ctx):
    K = tcod.event.KeySym
    if sym in (K.DOWN, K.KP_2): state.scroll += 1; return True
    if sym in (K.UP, K.KP_8): state.scroll = max(0, state.scroll - 1); return True
    return False


# ============================================================================
#  TAB 4: RUMORS
# ============================================================================

def _draw_rumors(con, x, y, w, h, state: MenuState, ctx: dict):
    journal = ctx.get("journal")
    if not journal or not journal.rumors:
        con.print(x + 1, y + 1, "No rumors.", fg=GREY, bg=BG)
        return
    entries = list(reversed(journal.rumors))
    row = y
    for r in entries[state.scroll:]:
        if row >= y + h:
            break
        color = GREEN if r.verified else WHITE
        con.print(x + 1, row, f"{r.date_str}  (from {r.source})", fg=YELLOW, bg=BG)
        row += 1
        if row < y + h:
            con.print(x + 3, row, r.text[:w - 4], fg=color, bg=BG)
        row += 2

def _handle_rumors(sym, state, ctx):
    K = tcod.event.KeySym
    if sym in (K.DOWN, K.KP_2): state.scroll += 1; return True
    if sym in (K.UP, K.KP_8): state.scroll = max(0, state.scroll - 1); return True
    return False


# ============================================================================
#  TAB 5: MAIL
# ============================================================================

def _draw_mail(con, x, y, w, h, state: MenuState, ctx: dict):
    writing = ctx.get("writing")
    player = ctx.get("player")
    journal = ctx.get("journal")

    con.print(x + 1, y, "MAIL", fg=YELLOW, bg=BG)
    y += 1

    # Show pending mail count
    if writing:
        pname = player.name if player else ""
        day = ctx.get("current_day", 0)
        pending = writing.mail.pending_count(pname, day)
        transit = writing.mail.in_transit_count(pname, day)
        con.print(x + 1, y, f"Waiting at post office: {pending}  In transit: {transit}",
                  fg=GREY, bg=BG)
        y += 1
        con.print(x + 1, y, "(Visit a town post office to pick up mail)", fg=DGREY, bg=BG)
        y += 2

    # Show letters from journal (already picked up and read)
    if journal and journal.letters:
        entries = list(reversed(journal.letters))
        for letter in entries[state.scroll:]:
            if y >= ctx.get("_max_y", 999):
                break
            color = CYAN if not letter.read else GREY
            status = "[unread]" if not letter.read else "[read]"
            con.print(x + 1, y,
                      f"{letter.date_str}  From: {letter.sender}  {status}",
                      fg=color, bg=BG)
            y += 1
            for line in wrap_text(letter.body, w - 4):
                if y >= ctx.get("_max_y", 999):
                    break
                con.print(x + 3, y, line, fg=WHITE, bg=BG)
                y += 1
            letter.read = True
            y += 1
    elif not journal or not journal.letters:
        con.print(x + 1, y, "No letters received yet.", fg=GREY, bg=BG)

def _handle_mail(sym, state, ctx):
    K = tcod.event.KeySym
    if sym in (K.DOWN, K.KP_2): state.scroll += 1; return True
    if sym in (K.UP, K.KP_8): state.scroll = max(0, state.scroll - 1); return True
    return False


# ============================================================================
#  TAB 6: WRITE
# ============================================================================

_WRITE_OPTIONS = [
    ("Write diary entry",           "diary"),
    ("Write letter",                "letter"),
    ("Write poem",                  "poem"),
    ("Write article",               "article"),
    ("Start / continue book",       "book"),
    ("Write skill guide",           "skill_book"),
    ("Draw sketch",                 "sketch"),
    ("Paint",                       "painting"),
]


def _draw_write(con, x, y, w, h, state: MenuState, ctx: dict):
    con.print(x + 1, y, "WRITE / CREATE", fg=YELLOW, bg=BG)
    y += 1
    con.print(x + 1, y, "Requires writing materials in inventory.", fg=GREY, bg=BG)
    y += 2

    for i, (label, _) in enumerate(_WRITE_OPTIONS):
        sel = (i == state.selected)
        draw_list_item(con, x + 1, y + i, w - 2, label, sel)

    # Show what's needed
    from src.writing import check_materials, MATERIAL_REQS
    player = ctx.get("player")
    if player and state.selected < len(_WRITE_OPTIONS):
        _, wtype = _WRITE_OPTIONS[state.selected]
        mapping = {
            "diary": "diary_entry", "letter": "letter", "poem": "diary_entry",
            "article": "article", "book": "book_chapter",
            "skill_book": "book_chapter", "sketch": "sketch", "painting": "painting",
        }
        req_key = mapping.get(wtype, "diary_entry")
        has, missing = check_materials(player.inventory, req_key)
        info_y = y + len(_WRITE_OPTIONS) + 2
        if has:
            con.print(x + 1, info_y, "Materials: Ready", fg=GREEN, bg=BG)
        else:
            con.print(x + 1, info_y, f"Need: {', '.join(missing)}", fg=RED, bg=BG)

    # Book in progress
    writing = ctx.get("writing")
    if writing and writing.book_in_progress:
        bip = writing.book_in_progress
        by = y + len(_WRITE_OPTIONS) + 4
        con.print(x + 1, by,
                  f"Book in progress: \"{bip.title}\" "
                  f"({bip.chapters}/{bip.chapters_target} chapters)",
                  fg=ORANGE, bg=BG)

    con.print(x + 1, y + h - 1,
              "Enter=Select  (you can type content or let the GM write it)",
              fg=DGREY, bg=BG)


def _handle_write(sym, state: MenuState, ctx: dict) -> bool:
    K = tcod.event.KeySym

    if sym in (K.DOWN, K.KP_2):
        state.selected = min(state.selected + 1, len(_WRITE_OPTIONS) - 1)
        return True
    if sym in (K.UP, K.KP_8):
        state.selected = max(state.selected - 1, 0)
        return True

    if sym in (K.RETURN, K.KP_ENTER):
        if state.selected < len(_WRITE_OPTIONS):
            _, wtype = _WRITE_OPTIONS[state.selected]
            state.result = ("write", wtype)
            state.should_close = True
        return True

    return False


# ============================================================================
#  AAR (AFTER ACTION REPORT)
# ============================================================================

def _draw_aar(con, x, y, w, h, state, ctx):
    journal = ctx.get("journal")
    if not journal or not journal.combat_log:
        con.print(x + 2, y + 2, "No combat encounters recorded.", fg=GREY)
        return

    # Show latest report (or selected one)
    idx = getattr(state, '_aar_idx', len(journal.combat_log) - 1)
    idx = max(0, min(idx, len(journal.combat_log) - 1))
    state._aar_idx = idx
    aar = journal.combat_log[idx]

    # Header
    con.print(x + 2, y + 1,
              f"Report {idx + 1}/{len(journal.combat_log)}  [</>] navigate",
              fg=GREY)

    # Summary text
    lines = aar.summary.split("\n") if aar.summary else ["No summary."]
    scroll = getattr(state, '_aar_scroll', 0)
    max_lines = h - 4
    for i, line in enumerate(lines[scroll:scroll + max_lines]):
        fg = WHITE
        if "Killed:" in line:
            fg = (255, 80, 80)
        elif "Fled:" in line:
            fg = (200, 200, 80)
        elif "Wounds:" in line:
            fg = (255, 160, 60)
        elif "shouts:" in line or "snarls:" in line or "cries:" in line:
            fg = (180, 160, 120)
        con.print(x + 2, y + 3 + i, line[:w - 4], fg=fg)


def _handle_aar(sym, state, ctx):
    journal = ctx.get("journal")
    if not journal or not journal.combat_log:
        return False
    K = tcod.event.KeySym
    idx = getattr(state, '_aar_idx', len(journal.combat_log) - 1)

    if sym == K.COMMA or sym == K.LEFT:
        state._aar_idx = max(0, idx - 1)
        return True
    if sym == K.PERIOD or sym == K.RIGHT:
        state._aar_idx = min(len(journal.combat_log) - 1, idx + 1)
        return True
    # Scroll
    scroll = getattr(state, '_aar_scroll', 0)
    if sym == K.UP:
        state._aar_scroll = max(0, scroll - 1)
        return True
    if sym == K.DOWN:
        state._aar_scroll = scroll + 1
        return True
    return False


# ============================================================================
#  PUBLIC
# ============================================================================

def open_journal(con, ctx, journal, player, npc_manager,
                  writing=None, current_day=0) -> Any:
    # Badge for unread letters
    unread = journal.unread_letters() if journal else 0
    mail_badge = str(unread) if unread > 0 else ""

    tabs = [
        MenuTab("Diary", _draw_diary, _handle_diary),
        MenuTab("People", _draw_people, _handle_people),
        MenuTab("Places", _draw_places, _handle_places),
        MenuTab("Rumors", _draw_rumors, _handle_rumors),
        MenuTab("Mail", _draw_mail, _handle_mail, badge=mail_badge),
        MenuTab("Write", _draw_write, _handle_write),
        MenuTab("AAR", _draw_aar, _handle_aar),
    ]
    menu = TabbedMenu("JOURNAL", tabs, width=72, height=42)
    return menu.run(con, ctx, journal=journal, player=player,
                     npc_manager=npc_manager, writing=writing,
                     current_day=current_day)
