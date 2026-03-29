"""
src/ui_framework.py

Shared UI framework for all tabbed menus in American Prospector.
Provides consistent rendering, tab navigation, scrolling, and
text input across all game screens.

Usage:
    from src.ui_framework import TabbedMenu, MenuTab

    tabs = [
        MenuTab("Items", draw_items, handle_items),
        MenuTab("Clothing", draw_clothing, handle_clothing),
    ]
    menu = TabbedMenu("INVENTORY", tabs, width=70, height=40)
    menu.run(console, context)
"""

import tcod
import tcod.event
import tcod.console
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Any, Tuple


# ============================================================================
#  COLORS
# ============================================================================

WHITE   = (255, 255, 255)
YELLOW  = (255, 220,  60)
CYAN    = ( 80, 200, 200)
GREEN   = ( 80, 180,  80)
RED     = (220,  50,  50)
ORANGE  = (210, 150,  50)
GREY    = (120, 120, 120)
DGREY   = ( 60,  60,  60)
BLACK   = (  0,   0,   0)
BG      = ( 15,  15,  30)
BG2     = ( 25,  25,  50)
BG_SEL  = ( 35,  35,  65)
BG_HEAD = ( 20,  20,  45)


# ============================================================================
#  MENU TAB
# ============================================================================

@dataclass
class MenuTab:
    """
    A single tab in a tabbed menu.

    draw_fn(con, x, y, w, h, state, ctx) — renders tab content
    handle_fn(sym, state, ctx) → bool — handles key input, returns True if consumed
    """
    name: str
    draw_fn: Callable       # (con, x, y, w, h, state, ctx) -> None
    handle_fn: Callable     # (sym, state, ctx) -> bool
    badge: str = ""         # e.g. "3" for unread count


# ============================================================================
#  MENU STATE (shared between tabs)
# ============================================================================

class MenuState:
    """Mutable state shared across tabs during a menu session."""
    def __init__(self):
        self.scroll: int = 0
        self.selected: int = 0
        self.text_input: str = ""
        self.typing: bool = False
        self.result: Any = None     # set by handle_fn to return a value
        self.should_close: bool = False
        self.dirty: bool = True     # force redraw
        self.extra: dict = {}       # tab-specific state


# ============================================================================
#  DRAWING HELPERS
# ============================================================================

def draw_box(con: tcod.console.Console, x: int, y: int,
              w: int, h: int, title: str = "", bg=BG) -> None:
    """Draw a bordered box with optional title."""
    con.draw_rect(x, y, w, h, ord(" "), fg=WHITE, bg=bg)
    for bx in range(x, x + w):
        con.print(bx, y,     "─", fg=DGREY, bg=bg)
        con.print(bx, y+h-1, "─", fg=DGREY, bg=bg)
    for by in range(y, y + h):
        con.print(x,     by, "│", fg=DGREY, bg=bg)
        con.print(x+w-1, by, "│", fg=DGREY, bg=bg)
    con.print(x, y, "┌", fg=DGREY, bg=bg)
    con.print(x+w-1, y, "┐", fg=DGREY, bg=bg)
    con.print(x, y+h-1, "└", fg=DGREY, bg=bg)
    con.print(x+w-1, y+h-1, "┘", fg=DGREY, bg=bg)
    if title:
        con.print(x + (w - len(title) - 2) // 2, y, f" {title} ",
                  fg=YELLOW, bg=bg)


def draw_tabs(con: tcod.console.Console, x: int, y: int, w: int,
               tabs: List[MenuTab], active: int) -> None:
    """Draw the tab bar."""
    tx = x + 1
    for i, tab in enumerate(tabs):
        label = tab.name
        if tab.badge:
            label = f"{tab.name}({tab.badge})"
        label = f" {label} "
        if tx + len(label) >= x + w - 1:
            break
        fg = YELLOW if i == active else GREY
        bg = BG2 if i == active else BG
        con.print(tx, y, label, fg=fg, bg=bg)
        tx += len(label)


def draw_separator(con: tcod.console.Console, x: int, y: int, w: int) -> None:
    for bx in range(x + 1, x + w - 1):
        con.print(bx, y, "─", fg=DGREY, bg=BG)


def draw_scrollbar(con: tcod.console.Console, x: int, y: int,
                     h: int, scroll: int, total: int) -> None:
    """Draw a simple scrollbar indicator."""
    if total <= h:
        return
    pos = min(h - 1, int(scroll / max(1, total - h) * (h - 1)))
    for sy in range(h):
        char = "█" if sy == pos else "░"
        con.print(x, y + sy, char, fg=DGREY, bg=BG)


def draw_text_input(con: tcod.console.Console, x: int, y: int,
                      w: int, text: str, active: bool,
                      prompt: str = "Type: ") -> None:
    """Draw a text input line."""
    fg = YELLOW if active else DGREY
    caret = "█" if active else ""
    display = f"{prompt}{text}{caret}"
    con.print(x, y, display[:w], fg=fg, bg=BG)


def draw_list_item(con: tcod.console.Console, x: int, y: int, w: int,
                     text: str, selected: bool = False,
                     fg_color=WHITE, tag: str = "") -> None:
    """Draw a single list item with optional selection highlight."""
    fg = CYAN if selected else fg_color
    bg = BG_SEL if selected else BG
    marker = ">" if selected else " "
    line = f"{marker} {text}"
    if tag:
        line = f"{marker} {text}  {tag}"
    con.print(x, y, line[:w], fg=fg, bg=bg)


def wrap_text(text: str, width: int) -> List[str]:
    """Word-wrap text into lines of at most width characters."""
    if len(text) <= width:
        return [text]
    lines = []
    current = ""
    for word in text.split(" "):
        candidate = (current + " " + word) if current else word
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            while len(word) > width:
                lines.append(word[:width])
                word = word[width:]
            current = word
    if current:
        lines.append(current)
    return lines


# ============================================================================
#  TABBED MENU
# ============================================================================

class TabbedMenu:
    """
    A full-screen tabbed menu with consistent navigation.

    Controls:
        ←→ or Tab/Shift+Tab: switch tabs
        ↑↓: scroll / select within tab
        Enter: confirm selection
        Esc: close menu
        Any letter: starts text input (if tab supports it)

    Each tab provides its own draw_fn and handle_fn.
    """

    def __init__(self, title: str, tabs: List[MenuTab],
                 width: int = 70, height: int = 42):
        self.title = title
        self.tabs = tabs
        self.width = width
        self.height = height

    def run(self, con: tcod.console.Console, ctx, **kwargs) -> Any:
        """Run the menu. Returns whatever state.result is set to."""
        SW, SH = con.width, con.height
        X = (SW - self.width) // 2
        Y = (SH - self.height) // 2
        W, H = self.width, self.height

        active_tab = 0
        state = MenuState()
        state.extra = kwargs

        content_y = Y + 3       # after title + tab bar + separator
        content_h = H - 6       # leave room for footer
        footer_y = Y + H - 2

        while True:
            # Draw frame
            draw_box(con, X, Y, W, H, self.title)
            draw_tabs(con, X, Y + 1, W, self.tabs, active_tab)
            draw_separator(con, X, Y + 2, W)

            # Draw active tab content
            tab = self.tabs[active_tab]
            tab.draw_fn(con, X + 1, content_y, W - 2, content_h, state, state.extra)

            # Footer
            draw_separator(con, X, footer_y - 1, W)
            help_text = "←→ Tabs   ↑↓ Scroll   Enter Select   Esc Close"
            con.print(X + 2, footer_y, help_text[:W - 4], fg=DGREY, bg=BG)

            ctx.present(con)

            if state.should_close:
                return state.result

            # Input
            for event in tcod.event.wait():
                if isinstance(event, tcod.event.TextInput) and state.typing:
                    state.text_input += event.text
                    continue

                if not isinstance(event, tcod.event.KeyDown):
                    continue

                sym = event.sym
                K = tcod.event.KeySym

                # Global navigation
                if sym == K.ESCAPE:
                    if state.typing:
                        state.typing = False
                        state.text_input = ""
                        ctx.sdl_window.stop_text_input()
                    else:
                        return state.result

                elif sym in (K.RIGHT, K.KP_6) and not state.typing:
                    active_tab = (active_tab + 1) % len(self.tabs)
                    state.scroll = 0
                    state.selected = 0

                elif sym in (K.LEFT, K.KP_4) and not state.typing:
                    active_tab = (active_tab - 1) % len(self.tabs)
                    state.scroll = 0
                    state.selected = 0

                elif sym == K.TAB:
                    if event.mod & tcod.event.KMOD_SHIFT:
                        active_tab = (active_tab - 1) % len(self.tabs)
                    else:
                        active_tab = (active_tab + 1) % len(self.tabs)
                    state.scroll = 0
                    state.selected = 0

                else:
                    # Let the active tab handle the key
                    consumed = tab.handle_fn(sym, state, state.extra)
                    if state.should_close:
                        return state.result
