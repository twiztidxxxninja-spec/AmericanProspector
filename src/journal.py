"""
Player journal: Diary / People / Places / Rumors / Letters tabs.
"""

import tcod
import tcod.event
import tcod.console
from dataclasses import dataclass, field
from typing import List, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.player import Player
    from src.npc import NPC

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


@dataclass
class DiaryEntry:
    date_str: str
    text: str


@dataclass
class RumorEntry:
    date_str: str
    source: str     # who told you
    text: str
    verified: bool = False


@dataclass
class Letter:
    date_str: str
    sender: str
    recipient: str   # usually player name
    body: str
    read: bool = False
    replied: bool = False


@dataclass
class PlaceNote:
    name: str
    world_x: int
    world_y: int
    notes: str
    visited: bool = True


class Journal:
    def __init__(self):
        self.diary:   List[DiaryEntry]  = []
        self.rumors:  List[RumorEntry]  = []
        self.letters: List[Letter]      = []
        self.places:  List[PlaceNote]   = []
        # People tab is derived from npc manager

    def add_diary(self, date_str: str, text: str):
        self.diary.append(DiaryEntry(date_str, text))

    def add_rumor(self, date_str: str, source: str, text: str):
        self.rumors.append(RumorEntry(date_str, source, text))

    def add_letter(self, letter: Letter):
        self.letters.append(letter)

    def add_place(self, name: str, wx: int, wy: int, notes: str = ""):
        # Update if exists
        for p in self.places:
            if p.world_x == wx and p.world_y == wy:
                if notes:
                    p.notes = notes
                return
        self.places.append(PlaceNote(name, wx, wy, notes))

    def unread_letters(self) -> int:
        return sum(1 for l in self.letters if not l.read)


TABS = ["Diary", "People", "Places", "Rumors", "Letters"]


def journal_menu(con: tcod.console.Console, ctx,
                 journal: Journal, player: "Player",
                 npc_manager) -> None:
    W = 70
    H = 44
    X = (con.width  - W) // 2
    Y = (con.height - H) // 2

    tab     = 0
    scroll  = 0

    from src.menus import draw_box

    while True:
        draw_box(con, X, Y, W, H, "Journal")

        # Tab bar
        tx = X + 2
        for i, name in enumerate(TABS):
            label = f" {name} "
            if journal.unread_letters() > 0 and name == "Letters":
                label = f" Letters({journal.unread_letters()}) "
            color = YELLOW if i == tab else GREY
            bgc   = BG2    if i == tab else BG
            con.print(tx, Y + 1, label, fg=color, bg=bgc)
            tx += len(label) + 1

        con.draw_rect(X + 1, Y + 2, W - 2, 1, ord("─"), fg=DGREY, bg=BG)

        content_y = Y + 3
        content_h = H - 7

        if tab == 0:   # Diary
            _draw_diary(con, journal, X, content_y, W, content_h, scroll)
        elif tab == 1: # People
            _draw_people(con, npc_manager, X, content_y, W, content_h, scroll)
        elif tab == 2: # Places
            _draw_places(con, journal, X, content_y, W, content_h, scroll)
        elif tab == 3: # Rumors
            _draw_rumors(con, journal, X, content_y, W, content_h, scroll)
        elif tab == 4: # Letters
            _draw_letters(con, journal, X, content_y, W, content_h, scroll)

        con.draw_rect(X + 1, Y + H - 3, W - 2, 1, ord("─"), fg=DGREY, bg=BG)
        con.print(X + 2, Y + H - 2,
                  "←→ tabs   ↑↓ scroll   Esc/J close",
                  fg=GREY, bg=BG)

        ctx.present(con)

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                K   = tcod.event.KeySym
                if sym in (K.ESCAPE, K.j):
                    return
                if sym in (K.LEFT, K.KP_4):
                    tab    = (tab - 1) % len(TABS)
                    scroll = 0
                if sym in (K.RIGHT, K.KP_6):
                    tab    = (tab + 1) % len(TABS)
                    scroll = 0
                if sym in (K.DOWN, K.KP_2):
                    scroll += 1
                if sym in (K.UP, K.KP_8):
                    scroll = max(0, scroll - 1)


def _draw_diary(con, journal: Journal, X, Y, W, H, scroll):
    if not journal.diary:
        con.print(X + 2, Y + 1, "No diary entries yet.", fg=GREY, bg=BG)
        return
    entries = list(reversed(journal.diary))   # newest first
    row = Y
    for entry in entries[scroll:]:
        if row >= Y + H:
            break
        con.print(X + 2, row, entry.date_str, fg=YELLOW, bg=BG)
        row += 1
        words = entry.text.split()
        line = ""
        for w in words:
            if len(line) + len(w) + 1 <= W - 4:
                line = (line + " " + w).strip()
            else:
                if row < Y + H:
                    con.print(X + 4, row, line, fg=WHITE, bg=BG)
                row += 1
                line = w
        if line and row < Y + H:
            con.print(X + 4, row, line, fg=WHITE, bg=BG)
        row += 2


def _draw_people(con, npc_manager, X, Y, W, H, scroll):
    npcs = list(npc_manager.npcs.values())
    if not npcs:
        con.print(X + 2, Y + 1, "You haven't met anyone yet.", fg=GREY, bg=BG)
        return
    for i, npc in enumerate(npcs[scroll:scroll + H]):
        row = Y + i
        rel_color = GREEN if npc.relationship > 20 else \
                    RED   if npc.relationship < -5  else WHITE
        con.print(X + 2, row,
                  f"{npc.name:<20} {npc.occupation:<14} {npc.rel_label()}",
                  fg=rel_color, bg=BG)


def _draw_places(con, journal: Journal, X, Y, W, H, scroll):
    if not journal.places:
        con.print(X + 2, Y + 1, "No places noted yet.", fg=GREY, bg=BG)
        return
    for i, place in enumerate(journal.places[scroll:scroll + H]):
        row = Y + i * 2
        if row >= Y + H:
            break
        con.print(X + 2, row,
                  f"{place.name}  [{place.world_x},{place.world_y}]",
                  fg=YELLOW, bg=BG)
        if place.notes and row + 1 < Y + H:
            con.print(X + 4, row + 1, place.notes[:W - 6], fg=WHITE, bg=BG)


def _draw_rumors(con, journal: Journal, X, Y, W, H, scroll):
    if not journal.rumors:
        con.print(X + 2, Y + 1, "No rumors noted yet.", fg=GREY, bg=BG)
        return
    entries = list(reversed(journal.rumors))
    row = Y
    for r in entries[scroll:]:
        if row >= Y + H:
            break
        color = GREEN if r.verified else WHITE
        con.print(X + 2, row,
                  f"{r.date_str}  (from {r.source})", fg=YELLOW, bg=BG)
        row += 1
        if row < Y + H:
            con.print(X + 4, row, r.text[:W - 6], fg=color, bg=BG)
        row += 2


def _draw_letters(con, journal: Journal, X, Y, W, H, scroll):
    if not journal.letters:
        con.print(X + 2, Y + 1, "No letters.", fg=GREY, bg=BG)
        return
    entries = list(reversed(journal.letters))
    row = Y
    for letter in entries[scroll:]:
        if row >= Y + H:
            break
        color  = CYAN  if not letter.read else GREY
        status = "[unread]" if not letter.read else ("[replied]" if letter.replied else "[read]")
        con.print(X + 2, row,
                  f"{letter.date_str}  From: {letter.sender}  {status}",
                  fg=color, bg=BG)
        letter.read = True
        row += 1
        words = letter.body.split()
        line = ""
        for w in words:
            if len(line) + len(w) + 1 <= W - 6:
                line = (line + " " + w).strip()
            else:
                if row < Y + H:
                    con.print(X + 4, row, line, fg=WHITE, bg=BG)
                row += 1
                line = w
        if line and row < Y + H:
            con.print(X + 4, row, line, fg=WHITE, bg=BG)
        row += 2
