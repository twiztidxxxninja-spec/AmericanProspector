"""
src/action_menu.py

Redesigned action menu for American Prospector.

Layout (default view):
    ┌───────── ACTIONS ──────────────┐
    │ RECENT                         │
    │ > Cut down tree                │  ← auto-highlighted
    │   Chop firewood                │
    │                                │
    │ COMMON                         │
    │   Pan for gold                 │
    │   Dig here                     │
    │   Fill canteen                 │
    │   ...                          │
    │   ▸ Show more...               │  ← expands full action list
    │                                │
    │── Type action: ___█ ───────────│
    │ ↑↓=Select  Enter=Confirm       │
    │ Type=Search  Esc=Close         │
    └────────────────────────────────┘

When typing, suggestions from ALL actions appear:
    ┌───────── ACTIONS ──────────────┐
    │ SUGGESTIONS                    │
    │ > Pan for gold                 │  ← matching hardcoded
    │   Pan bedrock crevices         │  ← from "more" list
    │   Load pan from adjacent pile  │
    │                                │
    │── Type action: pan█ ───────────│
    │ ↑↓=Select  Enter=Submit        │
    └────────────────────────────────┘

If no suggestions match, Enter submits as custom LLM action.

Also provides fixed item consumption (durable items degrade, not vanish).
"""

import tcod
import tcod.event
import tcod.console
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.player import Player
    from src.items import Item


# ============================================================================
#  COLORS
# ============================================================================

WHITE  = (255, 255, 255)
YELLOW = (255, 220,  60)
CYAN   = ( 80, 200, 200)
GREEN  = ( 80, 180,  80)
GREY   = (120, 120, 120)
DGREY  = ( 60,  60,  60)
ORANGE = (210, 150,  50)
BLACK  = (  0,   0,   0)
BG     = ( 15,  15,  30)
BG2    = ( 25,  25,  50)
BG_SEL = ( 35,  35,  65)


# ============================================================================
#  HARDCODED ACTIONS — two tiers
# ============================================================================

# Always visible in the default menu
COMMON_ACTIONS: List[str] = [
    "Eat",
    "Drink",
    "Forage",
    "Make camp",
    "Rest",
    "Sleep until dawn",
    "Craft",
    "Chop wood",
    "Dig",
    "Reload",
]

# Shown when "Show more" is expanded
MORE_ACTIONS: List[str] = [
    # Survival
    "Light a fire",
    "Bandage wounds",
    "Inspect wounds",
    "Throw item",
    "Read sign / Scout",
    # Prospecting
    "Pan for gold",
    "Stake a claim",
    # Ground work
    "Move rocks",
    "Clear brush",
    # Hide processing
    "Process hide",
    "Stretch pelt",
    # Social
    "Rob someone",
    "Investigate nearby",
]

# Combined for search matching
ALL_HARDCODED: List[str] = COMMON_ACTIONS + MORE_ACTIONS


# ============================================================================
#  ACTION HISTORY
# ============================================================================

MAX_RECENT = 10


class ActionHistory:
    """Tracks recently used actions for quick repeat access."""

    def __init__(self):
        self.recent: List[str] = []
        self.last_action: str = ""

    def record(self, action: str) -> None:
        self.last_action = action
        a = action.strip()
        if a in self.recent:
            self.recent.remove(a)
        self.recent.insert(0, a)
        if len(self.recent) > MAX_RECENT:
            self.recent = self.recent[:MAX_RECENT]

    def get_recent_custom(self) -> List[str]:
        """Recent actions that are NOT in the hardcoded lists."""
        return [a for a in self.recent if a not in ALL_HARDCODED]

    def to_dict(self) -> Dict:
        return {"recent": self.recent, "last_action": self.last_action}

    @classmethod
    def from_dict(cls, d: Dict) -> "ActionHistory":
        h = cls()
        h.recent = d.get("recent", [])
        h.last_action = d.get("last_action", "")
        return h


# ============================================================================
#  MENU ENTRY
# ============================================================================

@dataclass
class MenuEntry:
    label: str
    section: str      # "context" | "recent" | "common" | "more" | "suggestion"
    is_custom: bool   # True = custom LLM action from history
    is_toggle: bool = False
    is_context: bool = False  # True = context-sensitive action (highlighted)


# ============================================================================
#  BUILD ENTRIES
# ============================================================================

def _build_default_entries(history: ActionHistory,
                            expanded: bool,
                            context_actions: List[str] = None
                            ) -> List[MenuEntry]:
    """Build the default (non-searching) entry list."""
    entries: List[MenuEntry] = []

    # Recent actions first — what the player did last is most likely what they want
    recent = history.get_recent_custom()
    for a in recent:
        entries.append(MenuEntry(a, "recent", True))

    # Context-sensitive actions (nearby objects)
    if context_actions:
        for a in context_actions:
            if a not in recent:  # don't duplicate
                entries.append(MenuEntry(a, "context", False, is_context=True))

    # Common hardcoded
    for a in COMMON_ACTIONS:
        entries.append(MenuEntry(a, "common", False))

    # Show more toggle
    if not expanded:
        entries.append(MenuEntry(
            "▸ Show more...", "common", False, is_toggle=True))
    else:
        entries.append(MenuEntry(
            "▾ Show less", "common", False, is_toggle=True))
        for a in MORE_ACTIONS:
            entries.append(MenuEntry(a, "more", False))

    return entries


def _build_search_entries(history: ActionHistory,
                           filter_text: str) -> List[MenuEntry]:
    """Build filtered suggestion list from ALL actions + recent customs."""
    ft = filter_text.lower().strip()
    if not ft:
        return []

    entries: List[MenuEntry] = []
    seen = set()

    # Search recent custom actions first
    for a in history.get_recent_custom():
        if ft in a.lower() and a not in seen:
            entries.append(MenuEntry(a, "suggestion", True))
            seen.add(a)

    # Search all hardcoded actions
    for a in ALL_HARDCODED:
        if ft in a.lower() and a not in seen:
            entries.append(MenuEntry(a, "suggestion", False))
            seen.add(a)

    return entries


def _find_last_index(entries: List[MenuEntry], last: str) -> int:
    if not last:
        return 0
    ll = last.strip().lower()
    for i, e in enumerate(entries):
        if not e.is_toggle and e.label.lower() == ll:
            return i
    return 0


# ============================================================================
#  ACTION MENU UI
# ============================================================================

def open_action_menu(con: tcod.console.Console,
                      ctx,
                      history: ActionHistory,
                      context_actions: List[str] = None) -> Optional[str]:
    """
    Display the action menu.  Returns chosen action string or None.

    Behavior:
    - Default: shows RECENT + COMMON + "Show more" toggle
    - Most recent action auto-highlighted
    - Typing starts search mode — suggestions from ALL actions appear
    - Arrow down to select a suggestion, Enter to confirm
    - Keep typing past suggestions → Enter submits as custom LLM action
    - Enter with nothing selected repeats last action
    """
    W, H = 56, 38
    SW, SH = con.width, con.height
    X = (SW - W) // 2
    Y = (SH - H) // 2
    VISIBLE = H - 8

    text_input = ""
    typing = False
    expanded = False

    entries = _build_default_entries(history, expanded, context_actions)
    selected = _find_last_index(entries, history.last_action)
    scroll = max(0, selected - VISIBLE // 2)

    while True:
        # ── Rebuild entry list ────────────────────────────────────────
        if typing and text_input:
            entries = _build_search_entries(history, text_input)
            if selected >= len(entries):
                selected = max(0, len(entries) - 1)
        elif typing:
            # Typing mode but empty text — show all
            entries = _build_default_entries(history, expanded, context_actions)
        else:
            entries = _build_default_entries(history, expanded, context_actions)

        # ── Draw ──────────────────────────────────────────────────────
        con.draw_rect(X, Y, W, H, ord(" "), fg=WHITE, bg=BG)

        # Border
        for bx in range(X, X + W):
            con.print(bx, Y,     "─", fg=DGREY, bg=BG)
            con.print(bx, Y+H-1, "─", fg=DGREY, bg=BG)
        for by in range(Y, Y + H):
            con.print(X,     by, "│", fg=DGREY, bg=BG)
            con.print(X+W-1, by, "│", fg=DGREY, bg=BG)
        con.print(X, Y, "┌", fg=DGREY, bg=BG)
        con.print(X+W-1, Y, "┐", fg=DGREY, bg=BG)
        con.print(X, Y+H-1, "└", fg=DGREY, bg=BG)
        con.print(X+W-1, Y+H-1, "┘", fg=DGREY, bg=BG)

        title = " ACTIONS "
        con.print(X + (W - len(title)) // 2, Y, title, fg=YELLOW, bg=BG)

        # ── Ensure selected entry is visible (auto-scroll) ─────────
        # Count display rows needed for entries up to 'selected'
        # so scroll accounts for section headers too.
        def _rows_for_range(start, end):
            """Count display rows consumed by entries[start:end]."""
            rows = 0
            sec = "" if start == 0 else entries[start - 1].section if start > 0 else ""
            for idx in range(start, end):
                e = entries[idx]
                if not typing and e.section != sec:
                    sec = e.section
                    header = {"context": "NEARBY", "recent": "RECENT",
                              "common": "ACTIONS", "suggestion": "SUGGESTIONS"
                              }.get(e.section)
                    if header:
                        if rows > 0:
                            rows += 1  # blank line
                        rows += 1      # header
                rows += 1  # the entry itself
            return rows

        # Scroll down if selected is past visible area
        while True:
            rows_used = _rows_for_range(scroll, min(selected + 1, len(entries)))
            if rows_used <= VISIBLE:
                break
            scroll += 1
            if scroll >= len(entries):
                break

        # Scroll up if selected is above scroll
        if selected < scroll:
            scroll = selected

        # Entry list with section headers
        cur_section = "" if scroll == 0 else (
            entries[scroll - 1].section if scroll > 0 else "")
        row = Y + 2
        drawn = 0

        has_more_above = scroll > 0
        has_more_below = False

        for i in range(scroll, len(entries)):
            if drawn >= VISIBLE:
                has_more_below = (i < len(entries))
                break
            e = entries[i]

            # Section header (only in non-search mode)
            if not typing and e.section != cur_section:
                cur_section = e.section
                header_map = {
                    "context": "NEARBY",
                    "recent": "RECENT",
                    "common": "ACTIONS",
                    "more":   None,
                    "suggestion": "SUGGESTIONS",
                }
                header = header_map.get(e.section)
                if header:
                    if drawn > 0:
                        row += 1
                        drawn += 1
                        if drawn >= VISIBLE:
                            has_more_below = True
                            break
                    con.print(X + 2, row, header, fg=GREY, bg=BG)
                    row += 1
                    drawn += 1
                    if drawn >= VISIBLE:
                        has_more_below = True
                        break

            # Search mode header (once)
            if typing and text_input and drawn == 0 and i == 0:
                con.print(X + 2, row, "SUGGESTIONS", fg=GREY, bg=BG)
                row += 1
                drawn += 1
                if drawn >= VISIBLE:
                    break

            is_sel = (i == selected)

            # Toggle row styling
            if e.is_toggle:
                fg = CYAN if is_sel else ORANGE
                bg_c = BG_SEL if is_sel else BG
                con.print(X + 4, row, e.label[:W - 6], fg=fg, bg=bg_c)
                row += 1
                drawn += 1
                continue

            # Normal entry
            if e.is_context:
                fg = CYAN if is_sel else YELLOW
            elif e.is_custom:
                fg = CYAN if is_sel else GREEN
            else:
                fg = CYAN if is_sel else WHITE
            bg_c = BG_SEL if is_sel else BG
            marker = ">" if is_sel else " "

            label_str = f"{marker} {e.label}"
            if e.is_custom and not typing:
                label_str += "  (recent)"

            con.print(X + 2, row, label_str[:W - 4], fg=fg, bg=bg_c)
            row += 1
            drawn += 1

        # Scroll indicators
        if has_more_above:
            con.print(X + W - 4, Y + 2, " ▲ ", fg=GREY, bg=BG)
        if has_more_below:
            con.print(X + W - 4, Y + H - 6, " ▼ ", fg=GREY, bg=BG)

        # No matches message
        if typing and text_input and not entries:
            con.print(X + 2, Y + 3,
                      "(No match — Enter sends custom action to GM)",
                      fg=GREY, bg=BG)

        # Separator
        input_y = Y + H - 5
        for bx in range(X + 1, X + W - 1):
            con.print(bx, input_y, "─", fg=DGREY, bg=BG)

        # Input line
        if typing:
            caret = "█"
            full = f"Type: {text_input}{caret}"
            max_w = W - 4
            # Wrap long text across multiple lines
            line1 = full[:max_w]
            con.print(X + 2, input_y + 1, line1, fg=YELLOW, bg=BG)
            if len(full) > max_w:
                line2 = full[max_w:max_w * 2]
                con.print(X + 2, input_y + 2, line2, fg=YELLOW, bg=BG)
            if len(full) > max_w * 2:
                line3 = full[max_w * 2:max_w * 3]
                con.print(X + 2, input_y + 3, line3, fg=YELLOW, bg=BG)
        else:
            con.print(X + 2, input_y + 1,
                      "Start typing to search or enter custom action",
                      fg=DGREY, bg=BG)

        # Help line
        if typing:
            help_text = "↑↓=Select suggestion  Enter=Submit  Esc=Clear"
        else:
            help_text = "↑↓=Select  Enter=Confirm  Esc=Close"
        con.print(X + 2, Y + H - 2, help_text[:W - 4], fg=DGREY, bg=BG)

        ctx.present(con)

        # ── Input ─────────────────────────────────────────────────────
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.TextInput) and typing:
                text_input += event.text
                selected = 0
                scroll = 0
                continue

            if not isinstance(event, tcod.event.KeyDown):
                continue

            sym = event.sym
            K = tcod.event.KeySym

            if typing:
                if sym == K.ESCAPE:
                    if text_input:
                        text_input = ""
                        selected = 0
                        scroll = 0
                    else:
                        typing = False
                        ctx.sdl_window.stop_text_input()
                        entries = _build_default_entries(history, expanded, context_actions)
                        selected = _find_last_index(entries, history.last_action)
                        scroll = max(0, selected - VISIBLE // 2)

                elif sym == K.BACKSPACE:
                    if text_input:
                        text_input = text_input[:-1]
                        selected = 0
                        scroll = 0
                    else:
                        typing = False
                        ctx.sdl_window.stop_text_input()
                        entries = _build_default_entries(history, expanded, context_actions)
                        selected = _find_last_index(entries, history.last_action)
                        scroll = max(0, selected - VISIBLE // 2)

                elif sym in (K.RETURN, K.KP_ENTER):
                    ctx.sdl_window.stop_text_input()
                    if entries and selected < len(entries) and not entries[selected].is_toggle:
                        # Selected a suggestion
                        result = entries[selected].label
                    elif text_input.strip():
                        # No match or user ignored suggestions — custom action
                        result = text_input.strip()
                    else:
                        continue
                    history.record(result)
                    return result

                elif sym in (K.DOWN, K.KP_2):
                    if entries:
                        selected = min(selected + 1, len(entries) - 1)

                elif sym in (K.UP, K.KP_8):
                    selected = max(selected - 1, 0)

                elif sym == K.TAB:
                    # Tab = accept current suggestion into text field
                    if entries and selected < len(entries) and not entries[selected].is_toggle:
                        text_input = entries[selected].label
                        selected = 0
                        scroll = 0

            else:
                # List navigation mode
                if sym == K.ESCAPE or sym == K.a:
                    return None

                elif sym in (K.DOWN, K.KP_2):
                    selected = min(selected + 1, len(entries) - 1)

                elif sym in (K.UP, K.KP_8):
                    selected = max(selected - 1, 0)

                elif sym in (K.RETURN, K.KP_ENTER):
                    if entries and selected < len(entries):
                        e = entries[selected]
                        if e.is_toggle:
                            # Toggle show more / show less
                            expanded = not expanded
                            entries = _build_default_entries(history, expanded, context_actions)
                            # Keep selection near the toggle
                            selected = min(selected, len(entries) - 1)
                            scroll = max(0, selected - VISIBLE // 2)
                        else:
                            history.record(e.label)
                            return e.label
                    elif history.last_action:
                        history.record(history.last_action)
                        return history.last_action

                elif sym == K.HOME:
                    selected = 0
                    scroll = 0

                elif sym == K.END:
                    selected = max(0, len(entries) - 1)
                    scroll = max(0, selected - VISIBLE + 1)

                else:
                    # Any printable key starts typing/search mode
                    typing = True
                    text_input = ""
                    ctx.sdl_window.start_text_input()


# ============================================================================
#  FIXED ITEM CONSUMPTION
# ============================================================================

_DURABLE_CATEGORIES = frozenset(["tool", "weapon"])
_CONSUMABLE_CATEGORIES = frozenset(["food", "drink"])


def is_consumable(item: "Item") -> bool:
    """
    Consumable: food, drink, stackable materials, ammo.
    Durable: tools, weapons — degrade condition instead.
    """
    cat = getattr(item, "category", "misc").lower()
    if cat in _DURABLE_CATEGORIES:
        return False
    if cat in _CONSUMABLE_CATEGORIES:
        return True
    if getattr(item, "stackable", False):
        return True
    if cat == "material":
        return True
    return True


def apply_item_use_safe(player: "Player", items_used: List[str]) -> List[str]:
    """
    Safely consume items from LLM actions.
    Durable items degrade condition; consumables are removed.
    Also checks worn clothing for items not in inventory.
    Returns list of UI messages.
    """
    msgs: List[str] = []
    inv = player.inventory

    for name in items_used:
        name_clean = name.strip()
        if not name_clean:
            continue
        name_low = name_clean.lower()

        # Search inventory
        found_item = None
        found_idx = -1
        for i, item in enumerate(inv):
            if item.name.lower() == name_low:
                found_item = item
                found_idx = i
                break

        if found_item:
            if is_consumable(found_item):
                if found_item.stackable and found_item.quantity > 1:
                    found_item.quantity -= 1
                    msgs.append(f"  Used: {name_clean} (x{found_item.quantity} left).")
                else:
                    inv.pop(found_idx)
                    msgs.append(f"  Used up: {name_clean}.")
                    _clear_from_hands(player, name_low)
            else:
                found_item.condition = max(0.0, found_item.condition - 5.0)
                msgs.append(f"  {name_clean} used (condition: "
                            f"{found_item.condition:.0f}%).")
            continue

        # Check worn equipment
        worn = getattr(player, "worn", None)
        if worn:
            worn_item = worn.find_by_name(name_clean)
            if worn_item:
                worn.remove_by_name(name_clean)
                msgs.append(f"  Removed: {name_clean} (from worn clothing).")
                continue

    return msgs


def _clear_from_hands(player: "Player", name_low: str) -> None:
    if player.right_hand and player.right_hand.lower() == name_low:
        player.right_hand = None
    if player.left_hand and player.left_hand.lower() == name_low:
        player.left_hand = None
