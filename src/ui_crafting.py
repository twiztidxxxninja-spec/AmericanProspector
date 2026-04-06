"""
src/ui_crafting.py

[C] Crafting menu — tabbed interface organized by category.
Each tab shows recipes with availability, materials needed,
output description, and skill requirements.
"""

import tcod.event
from typing import Any, List

from src.ui_framework import (
    TabbedMenu, MenuTab, MenuState, draw_list_item, draw_separator,
    WHITE, YELLOW, CYAN, GREEN, RED, GREY, DGREY, ORANGE, BG, BG2
)


# ============================================================================
#  CATEGORY TABS
# ============================================================================

_CAT_ORDER = [
    "food", "tools", "materials", "medical", "leatherwork",
    "furwork", "bonework", "woodwork", "trapping", "shelter",
]

_CAT_LABELS = {
    "food": "Food",
    "tools": "Tools",
    "materials": "Mats",
    "medical": "Med",
    "leatherwork": "Leather",
    "furwork": "Fur",
    "bonework": "Bone",
    "woodwork": "Wood",
    "trapping": "Trap",
    "shelter": "Shelter",
}


def _draw_recipe_tab(con, x, y, w, h, state: MenuState, ctx: dict):
    """Draw a single category's recipes."""
    from src.crafting import RECIPE_CATEGORIES, can_craft
    from src.items import ITEM_TEMPLATES

    player = ctx.get("player")
    category = ctx.get("_active_category", "food")
    recipes = RECIPE_CATEGORIES.get(category, [])

    if not recipes:
        con.print(x + 1, y + 1, "No recipes in this category.", fg=GREY, bg=BG)
        return

    # Clamp selection
    state.selected = max(0, min(state.selected, len(recipes) - 1))

    # Recipe list (left side)
    list_w = w // 2 - 1
    for i in range(min(len(recipes), h - 4)):
        idx = state.scroll + i
        if idx >= len(recipes):
            break
        r = recipes[idx]
        ok, reason = can_craft(r, player.inventory)
        sel = (idx == state.selected)

        if ok:
            fg = GREEN if sel else CYAN
        else:
            fg = ORANGE if sel else GREY
        bg = BG2 if sel else BG
        prefix = ">" if sel else " "
        line = f"{prefix}{r.name}"[:list_w]
        con.print(x + 1, y + i, line, fg=fg, bg=bg)

    # Detail panel (right side)
    detail_x = x + list_w + 2
    detail_w = w - list_w - 3
    r = recipes[state.selected]
    ok, reason = can_craft(r, player.inventory)

    # Recipe name
    name_fg = GREEN if ok else RED
    con.print(detail_x, y, r.name[:detail_w], fg=name_fg, bg=BG)
    dy = y + 1

    # Description (word-wrapped)
    desc = r.description
    words = desc.split()
    line = ""
    for word in words:
        if len(line) + len(word) + 1 <= detail_w:
            line = (line + " " + word).strip()
        else:
            if dy < y + 4:
                con.print(detail_x, dy, line[:detail_w], fg=WHITE, bg=BG)
                dy += 1
            line = word
    if line and dy < y + 4:
        con.print(detail_x, dy, line[:detail_w], fg=WHITE, bg=BG)
        dy += 1

    dy += 1

    # Materials
    con.print(detail_x, dy, "Materials:", fg=YELLOW, bg=BG)
    dy += 1
    for mat_id, qty in r.materials:
        from src.items import ITEM_TEMPLATES
        tpl = ITEM_TEMPLATES.get(mat_id, {})
        mat_name = tpl.get("name", mat_id)
        # Count player has
        player_has = sum(getattr(i, 'quantity', 1)
                         for i in player.inventory if i.id == mat_id)
        have_fg = GREEN if player_has >= qty else RED
        con.print(detail_x + 1, dy,
                  f"{qty}x {mat_name} ", fg=GREY, bg=BG)
        con.print(detail_x + 1 + len(f"{qty}x {mat_name} "), dy,
                  f"(have {player_has})", fg=have_fg, bg=BG)
        dy += 1

    dy += 1

    # Requirements
    if r.tool_required:
        con.print(detail_x, dy, f"Tool: {r.tool_required}", fg=GREY, bg=BG)
        dy += 1
    con.print(detail_x, dy, f"Skill: {r.skill} DC{r.difficulty}", fg=GREY, bg=BG)
    dy += 1
    con.print(detail_x, dy, f"Time: {r.time_minutes} minutes", fg=GREY, bg=BG)
    dy += 1

    # Output
    dy += 1
    out_name = ""
    if r.output_custom:
        out_name = r.output_custom.get("name", "?")
    elif r.output_id:
        tpl = ITEM_TEMPLATES.get(r.output_id, {})
        out_name = tpl.get("name", r.output_id)
    con.print(detail_x, dy, f"Makes: {r.output_qty}x {out_name}",
              fg=CYAN, bg=BG)

    # Status
    dy += 2
    if ok:
        con.print(detail_x, dy, "[Enter] CRAFT", fg=GREEN, bg=BG)
    else:
        con.print(detail_x, dy, f"Missing: {reason}", fg=RED, bg=BG)


def _handle_recipe_tab(sym, state: MenuState, ctx: dict) -> bool:
    K = tcod.event.KeySym
    from src.crafting import RECIPE_CATEGORIES, can_craft, execute_craft

    player = ctx.get("player")
    category = ctx.get("_active_category", "food")
    recipes = RECIPE_CATEGORIES.get(category, [])

    if not recipes:
        return False

    count = len(recipes)

    if sym in (K.UP, K.KP_8):
        state.selected = max(0, state.selected - 1)
        if state.selected < state.scroll:
            state.scroll = state.selected
        return True
    if sym in (K.DOWN, K.KP_2):
        state.selected = min(count - 1, state.selected + 1)
        return True

    if sym in (K.RETURN, K.KP_ENTER):
        r = recipes[state.selected]
        ok, msg = execute_craft(r, player)
        state.result = ("crafted" if ok else "failed", msg,
                        r.time_minutes if ok else 5)
        # Stay in menu — accumulate results so player can craft multiples
        if not hasattr(state, '_craft_results'):
            state._craft_results = []
        state._craft_results.append(state.result)
        state._last_craft_msg = msg
        state._last_craft_ok = ok
        # Record recipe name for action menu repeat
        if ok:
            state._last_recipe_name = r.name
        return True

    return False


# ============================================================================
#  PUBLIC
# ============================================================================

_last_recipe_name = ""

def _get_last_recipe_name() -> str:
    return _last_recipe_name

def _save_recipe_name(state):
    global _last_recipe_name
    _last_recipe_name = getattr(state, '_last_recipe_name', "")

def open_crafting(con, ctx, player) -> Any:
    """Open the tabbed crafting menu. Returns (status, message, time) or None."""
    from src.crafting import RECIPE_CATEGORIES

    # Build tabs from available categories (only show categories with recipes)
    tabs = []
    cat_list = []
    for cat in _CAT_ORDER:
        recipes = RECIPE_CATEGORIES.get(cat, [])
        if recipes:
            label = _CAT_LABELS.get(cat, cat.capitalize())
            tabs.append(MenuTab(label, _draw_recipe_tab, _handle_recipe_tab))
            cat_list.append(cat)

    if not tabs:
        return None

    menu = TabbedMenu("CRAFTING", tabs, width=90, height=40)

    # Hack: inject active category via ctx — updates when tab changes
    class CraftCtx(dict):
        def __init__(self, base, cats):
            super().__init__(base)
            self._cats = cats
            self["_active_category"] = cats[0] if cats else "food"

    craft_ctx = CraftCtx({"player": player}, cat_list)

    # Override run to track active tab → category mapping
    import tcod.event as _evt
    from src.ui_framework import draw_box, draw_tabs, draw_separator, MenuState as _MS

    SW, SH = con.width, con.height
    W, H = 90, 40
    X = (SW - W) // 2
    Y = (SH - H) // 2
    active_tab = 0
    state = _MS()
    state.extra = craft_ctx

    while True:
        craft_ctx["_active_category"] = cat_list[active_tab] if active_tab < len(cat_list) else "food"

        draw_box(con, X, Y, W, H, "CRAFTING")
        draw_tabs(con, X, Y + 1, W, tabs, active_tab)
        draw_separator(con, X, Y + 2, W)

        tab = tabs[active_tab]
        tab.draw_fn(con, X + 1, Y + 3, W - 2, H - 6, state, craft_ctx)

        # Show last craft result if any
        last_msg = getattr(state, '_last_craft_msg', None)
        if last_msg:
            msg_fg = GREEN if getattr(state, '_last_craft_ok', False) else RED
            draw_separator(con, X, Y + H - 4, W)
            con.print(X + 2, Y + H - 3, last_msg[:W - 4], fg=msg_fg, bg=BG)
            draw_separator(con, X, Y + H - 2, W)
        else:
            draw_separator(con, X, Y + H - 3, W)

        con.print(X + 2, Y + H - 1,
                  "< > Tabs   Up/Dn Select   Enter Craft   Esc Close",
                  fg=DGREY, bg=BG)
        ctx.present(con)

        for event in _evt.wait():
            if isinstance(event, _evt.Quit):
                results = getattr(state, '_craft_results', None)
                _save_recipe_name(state)
                return results if results else None
            if isinstance(event, _evt.KeyDown):
                sym = event.sym
                K = _evt.KeySym
                if sym == K.ESCAPE:
                    results = getattr(state, '_craft_results', None)
                    _save_recipe_name(state)
                    return results if results else None
                if sym in (K.RIGHT, K.PERIOD, K.TAB):
                    active_tab = (active_tab + 1) % len(tabs)
                    state.selected = 0
                    state.scroll = 0
                    break
                if sym in (K.LEFT, K.COMMA):
                    active_tab = (active_tab - 1) % len(tabs)
                    state.selected = 0
                    state.scroll = 0
                    break
                if tab.handle_fn(sym, state, craft_ctx):
                    break
