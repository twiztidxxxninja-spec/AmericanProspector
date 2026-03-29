"""
src/ui_inventory.py

[I] Inventory menu — three tabs:
    Tab 1: Carried Items (browse, drop, use)
    Tab 2: Worn Clothing (view outfit, equip/unequip)
    Tab 3: Hands (equip items to L/R hand)
"""

import tcod.event
from typing import Any

from src.ui_framework import (
    TabbedMenu, MenuTab, MenuState,
    draw_list_item, draw_separator, wrap_text,
    WHITE, YELLOW, CYAN, GREEN, RED, GREY, DGREY, ORANGE, BG, BG2
)


# ============================================================================
#  TAB 1: CARRIED ITEMS
# ============================================================================

def _draw_items(con, x, y, w, h, state: MenuState, ctx: dict):
    player = ctx.get("player")
    if not player:
        con.print(x + 1, y, "No player.", fg=GREY, bg=BG)
        return

    inv = player.inventory
    if not inv:
        con.print(x + 1, y + 1, "Your pack is empty.", fg=GREY, bg=BG)
        return

    # Weight summary
    cap = player.carry_capacity
    wt = player.carried_weight
    wt_color = RED if player.overloaded else ORANGE if player.encumbered else GREEN
    con.print(x + 1, y, f"Weight: {wt:.1f} / {cap:.1f} lb", fg=wt_color, bg=BG)
    y += 1

    visible = h - 2
    for i in range(visible):
        idx = state.scroll + i
        if idx >= len(inv):
            break
        item = inv[idx]
        sel = (idx == state.selected)
        name = item.display_name()
        cond = f" [{item.condition:.0f}%]" if item.condition < 80 else ""
        val = f" ${item.base_value:.2f}" if item.base_value > 0 else ""
        wt_str = f" {item.weight:.1f}lb"
        tag = f"{wt_str}{cond}{val}"
        fg = GREEN if item.is_food() else CYAN if item.is_tool() else \
             RED if item.is_weapon() else WHITE
        draw_list_item(con, x + 1, y + 1 + i, w - 2, name, sel, fg, tag)

    # Footer hint
    con.print(x + 1, y + visible + 1,
              "D=Drop  U=Use  R=Read  Enter=Examine", fg=DGREY, bg=BG)


def _handle_items(sym, state: MenuState, ctx: dict) -> bool:
    K = tcod.event.KeySym
    player = ctx.get("player")
    if not player:
        return False
    inv = player.inventory
    count = len(inv)

    if sym in (K.DOWN, K.KP_2):
        state.selected = min(state.selected + 1, count - 1)
        if state.selected >= state.scroll + 30:
            state.scroll += 1
        return True
    if sym in (K.UP, K.KP_8):
        state.selected = max(state.selected - 1, 0)
        if state.selected < state.scroll:
            state.scroll = state.selected
        return True

    if sym == K.d and count > 0:
        # Drop item
        item = inv.pop(state.selected)
        state.selected = min(state.selected, len(inv) - 1)
        state.extra["dropped"] = item
        return True

    return False


# ============================================================================
#  TAB 2: WORN CLOTHING
# ============================================================================

def _draw_clothing(con, x, y, w, h, state: MenuState, ctx: dict):
    player = ctx.get("player")
    worn = getattr(player, "worn", None) if player else None
    if not worn:
        con.print(x + 1, y + 1, "No clothing system.", fg=GREY, bg=BG)
        return

    from src.clothing import SLOT_ORDER, SLOT_LABELS

    con.print(x + 1, y, "OUTFIT", fg=YELLOW, bg=BG)
    y += 1

    total_warmth = worn.total_warmth()
    total_weight = worn.total_weight()
    con.print(x + 1, y, f"Warmth: {total_warmth:.0f}  Weight: {total_weight:.1f}lb",
              fg=GREY, bg=BG)
    y += 1

    for i, slot in enumerate(SLOT_ORDER):
        sel = (i == state.selected)
        label = SLOT_LABELS[slot]
        item = worn.get(slot)
        if item:
            cond_color = GREEN if item.condition >= 60 else \
                         ORANGE if item.condition >= 30 else RED
            display = f"{label:<14} {item.name} ({item.condition_label})"
            if item.wet:
                display += " [WET]"
            draw_list_item(con, x + 1, y + i, w - 2, display, sel, cond_color)
        else:
            draw_list_item(con, x + 1, y + i, w - 2,
                           f"{label:<14} -- empty --", sel, DGREY)

    footer_y = y + len(SLOT_ORDER) + 1
    con.print(x + 1, footer_y, "Enter=Equip from inventory  U=Unequip",
              fg=DGREY, bg=BG)


def _handle_clothing(sym, state: MenuState, ctx: dict) -> bool:
    K = tcod.event.KeySym
    player = ctx.get("player")
    worn = getattr(player, "worn", None) if player else None
    if not worn:
        return False

    from src.clothing import SLOT_ORDER, WornItem, GARMENT_CATALOG

    slot_count = len(SLOT_ORDER)

    if sym in (K.DOWN, K.KP_2):
        state.selected = min(state.selected + 1, slot_count - 1)
        return True
    if sym in (K.UP, K.KP_8):
        state.selected = max(state.selected - 1, 0)
        return True

    if sym == K.u:
        # Unequip from selected slot
        slot = SLOT_ORDER[state.selected]
        item = worn.unequip(slot)
        if item:
            # Convert WornItem back to inventory Item
            from src.items import Item
            inv_item = Item(
                id=item.garment_id, name=item.name,
                weight=item.weight, category="clothing",
                condition=item.condition, base_value=item.base_value,
                extra={"clothing_slot": item.slot, "warmth": item.warmth,
                       "protection": item.protection},
            )
            player.inventory.append(inv_item)
        return True

    if sym in (K.RETURN, K.KP_ENTER):
        # Equip — find clothing items in inventory for this slot
        slot = SLOT_ORDER[state.selected]
        clothing_items = []
        for i, item in enumerate(player.inventory):
            item_slot = getattr(item, "extra", {}).get("clothing_slot", "")
            if item_slot == slot:
                clothing_items.append((i, item))
            # Also check garment catalog
            elif item.category == "clothing":
                gdef = GARMENT_CATALOG.get(item.id)
                if gdef and gdef.slot == slot:
                    clothing_items.append((i, item))
        if clothing_items:
            # Auto-equip the first matching item
            idx, inv_item = clothing_items[0]
            player.inventory.pop(idx)
            new_worn = WornItem.from_garment(inv_item.id,
                                              condition=inv_item.condition)
            old = worn.equip(new_worn)
            if old:
                from src.items import Item
                player.inventory.append(Item(
                    id=old.garment_id, name=old.name,
                    weight=old.weight, category="clothing",
                    condition=old.condition, base_value=old.base_value,
                ))
        return True

    return False


# ============================================================================
#  TAB 3: HANDS
# ============================================================================

def _draw_hands(con, x, y, w, h, state: MenuState, ctx: dict):
    player = ctx.get("player")
    if not player:
        return

    con.print(x + 1, y, "HANDS", fg=YELLOW, bg=BG)
    y += 2

    rh = player.right_hand or "-- empty --"
    lh = player.left_hand or "-- empty --"
    rh_color = WHITE if player.right_hand else DGREY
    lh_color = WHITE if player.left_hand else DGREY

    sel_r = (state.selected == 0)
    sel_l = (state.selected == 1)
    draw_list_item(con, x + 1, y, w - 2, f"Right Hand: {rh}", sel_r, rh_color)
    draw_list_item(con, x + 1, y + 1, w - 2, f"Left Hand:  {lh}", sel_l, lh_color)

    y += 4
    con.print(x + 1, y, "EQUIPPABLE ITEMS:", fg=GREY, bg=BG)
    y += 1

    equippable = [(i, item) for i, item in enumerate(player.inventory)
                  if item.is_weapon() or item.is_tool()]
    for j, (idx, item) in enumerate(equippable):
        if j >= h - 10:
            break
        sel = (state.selected == j + 2)
        draw_list_item(con, x + 1, y + j, w - 2, item.display_name(), sel)

    footer_y = y + min(len(equippable), h - 10) + 1
    con.print(x + 1, footer_y, "Enter=Equip to selected hand  D=Drop from hand",
              fg=DGREY, bg=BG)


def _handle_hands(sym, state: MenuState, ctx: dict) -> bool:
    K = tcod.event.KeySym
    player = ctx.get("player")
    if not player:
        return False

    equippable = [(i, item) for i, item in enumerate(player.inventory)
                  if item.is_weapon() or item.is_tool()]
    max_sel = 1 + len(equippable)

    if sym in (K.DOWN, K.KP_2):
        state.selected = min(state.selected + 1, max_sel)
        return True
    if sym in (K.UP, K.KP_8):
        state.selected = max(state.selected - 1, 0)
        return True

    if sym == K.d:
        if state.selected == 0:
            player.right_hand = None
        elif state.selected == 1:
            player.left_hand = None
        return True

    if sym in (K.RETURN, K.KP_ENTER):
        if state.selected >= 2:
            item_idx = state.selected - 2
            if item_idx < len(equippable):
                _, item = equippable[item_idx]
                # Equip to right hand (default), or left if right is full
                if not player.right_hand:
                    player.right_hand = item.name
                elif not player.left_hand:
                    player.left_hand = item.name
                else:
                    player.right_hand = item.name
        return True

    return False


# ============================================================================
#  PUBLIC: open the inventory menu
# ============================================================================

def open_inventory(con, ctx, player) -> None:
    tabs = [
        MenuTab("Items", _draw_items, _handle_items),
        MenuTab("Clothing", _draw_clothing, _handle_clothing),
        MenuTab("Hands", _draw_hands, _handle_hands),
    ]
    menu = TabbedMenu("INVENTORY", tabs, width=72, height=40)
    menu.run(con, ctx, player=player)
