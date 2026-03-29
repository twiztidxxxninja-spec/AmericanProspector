"""
Trade UI — visual buy/sell interface with merchant NPCs.

Two-column layout: merchant stock on left, player inventory on right.
Arrow keys navigate, Enter buys/sells, TAB switches columns.
"""

import tcod
import tcod.event
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.player import Player
    from src.npc import NPC


def open_trade_ui(console, ctx, player: "Player", npc: "NPC",
                  stock, trade_engine=None, region: str = "",
                  settlement_type: str = "small_town",
                  merchant_type: str = "general_store") -> list:
    """Full-screen trade interface. Returns list of log messages."""
    from src.items import Item, make_item

    W = 78
    H = 40
    X = (console.width - W) // 2
    Y = (console.height - H) // 2

    COL_LEFT = X + 2       # merchant stock
    COL_RIGHT = X + W // 2 + 1  # player inventory
    COL_W = W // 2 - 3
    HEADER_Y = Y + 2
    LIST_Y = Y + 4
    MAX_ROWS = H - 8

    GOLD_RATE = 20.67 * 0.90  # $18.60/oz — merchant cut on raw dust

    selected = 0
    column = 0   # 0 = merchant (buy), 1 = player (sell)
    scroll_l = 0
    scroll_r = 0
    pay_with_gold = False  # G key toggles
    messages = []

    def _get_merchant_items():
        items = []
        for entry in stock.items:
            if entry.quantity <= 0:
                continue
            price = entry.base_price
            if trade_engine:
                tmp = Item(id=entry.item_id, name=entry.name, weight=0,
                           category=entry.category, base_value=entry.base_price,
                           condition=entry.condition)
                price = trade_engine.get_buy_price(tmp, region, settlement_type,
                                                    merchant_type)
            items.append({
                "name": entry.name, "price": price, "qty": entry.quantity,
                "entry": entry, "item_id": entry.item_id,
                "category": entry.category,
            })
        return items

    def _get_player_items():
        items = []
        seen = set()
        for item in player.inventory:
            key = item.id
            if key in seen and item.stackable:
                continue
            seen.add(key)
            price = item.base_value * 0.35  # default sell price
            if trade_engine:
                price = trade_engine.get_sell_price(item, region, settlement_type,
                                                     merchant_type)
            qty = item.quantity if item.stackable else 1
            items.append({
                "name": item.display_name(), "price": price, "qty": qty,
                "item": item,
            })
        return items

    while True:
        m_items = _get_merchant_items()
        p_items = _get_player_items()

        active_list = m_items if column == 0 else p_items
        scroll = scroll_l if column == 0 else scroll_r
        if selected >= len(active_list):
            selected = max(0, len(active_list) - 1)

        # ── Draw ──────────────────────────────────────────────────
        # Background box
        for sy in range(Y, Y + H):
            console.print(X, sy, " " * W, fg=(200, 200, 200), bg=(15, 12, 10))

        # Border
        console.print(X, Y, "+" + "-" * (W - 2) + "+", fg=(120, 100, 70), bg=(15, 12, 10))
        console.print(X, Y + H - 1, "+" + "-" * (W - 2) + "+", fg=(120, 100, 70), bg=(15, 12, 10))
        for sy in range(Y + 1, Y + H - 1):
            console.print(X, sy, "|", fg=(120, 100, 70), bg=(15, 12, 10))
            console.print(X + W - 1, sy, "|", fg=(120, 100, 70), bg=(15, 12, 10))
            console.print(X + W // 2, sy, "|", fg=(80, 70, 50), bg=(15, 12, 10))

        # Title
        title = f"TRADE — {npc.display_name()} ({npc.occupation})"
        console.print(X + (W - len(title)) // 2, Y, title,
                      fg=(255, 220, 140), bg=(15, 12, 10))

        # Column headers
        buy_fg = (255, 255, 200) if column == 0 else (140, 130, 100)
        sell_fg = (255, 255, 200) if column == 1 else (140, 130, 100)
        console.print(COL_LEFT, HEADER_Y, "FOR SALE (Buy)", fg=buy_fg, bg=(15, 12, 10))
        console.print(COL_RIGHT, HEADER_Y, "YOUR ITEMS (Sell)", fg=sell_fg, bg=(15, 12, 10))

        # Cash bar + payment mode
        cash_y = Y + H - 4
        console.print(COL_LEFT, cash_y,
                      f"Cash: ${player.cash:.2f}   Gold: {player.gold_oz:.3f} oz "
                      f"(${player.gold_oz * GOLD_RATE:.2f} value)",
                      fg=(220, 200, 100), bg=(15, 12, 10))
        if pay_with_gold:
            console.print(COL_LEFT, cash_y + 1,
                          "Paying with: GOLD DUST  [G] switch to cash",
                          fg=(255, 220, 50), bg=(15, 12, 10))
        else:
            console.print(COL_LEFT, cash_y + 1,
                          "Paying with: CASH  [G] switch to gold",
                          fg=(200, 200, 200), bg=(15, 12, 10))

        # Controls
        console.print(COL_LEFT, Y + H - 2,
                      "[Enter] Buy/Sell  [TAB] Switch  [G] Payment  [Esc] Close",
                      fg=(100, 100, 100), bg=(15, 12, 10))

        # ── Merchant stock (left column) ──────────────────────────
        for i, mi in enumerate(m_items[scroll_l:scroll_l + MAX_ROWS]):
            idx = i + scroll_l
            row_y = LIST_Y + i
            is_sel = (column == 0 and idx == selected)
            bg = (40, 35, 25) if is_sel else (15, 12, 10)
            fg = (255, 255, 255) if is_sel else (200, 190, 160)

            name = mi["name"][:COL_W - 12]
            qty_str = f"x{mi['qty']}" if mi["qty"] > 1 else ""
            price_str = f"${mi['price']:.2f}"
            if pay_with_gold:
                can_afford = (player.gold_oz * GOLD_RATE) >= mi["price"]
            else:
                can_afford = player.cash >= mi["price"]
            price_fg = (100, 200, 100) if can_afford else (200, 80, 80)
            if is_sel:
                price_fg = (150, 255, 150) if can_afford else (255, 100, 100)

            console.print(COL_LEFT, row_y, f"{name} {qty_str}", fg=fg, bg=bg)
            console.print(COL_LEFT + COL_W - len(price_str), row_y,
                          price_str, fg=price_fg, bg=bg)

        if not m_items:
            console.print(COL_LEFT, LIST_Y, "Nothing for sale.",
                          fg=(100, 100, 100), bg=(15, 12, 10))

        # ── Player inventory (right column) ───────────────────────
        for i, pi in enumerate(p_items[scroll_r:scroll_r + MAX_ROWS]):
            idx = i + scroll_r
            row_y = LIST_Y + i
            is_sel = (column == 1 and idx == selected)
            bg = (40, 35, 25) if is_sel else (15, 12, 10)
            fg = (255, 255, 255) if is_sel else (200, 190, 160)

            name = pi["name"][:COL_W - 10]
            price_str = f"${pi['price']:.2f}"

            console.print(COL_RIGHT, row_y, name, fg=fg, bg=bg)
            console.print(COL_RIGHT + COL_W - len(price_str), row_y,
                          price_str, fg=(180, 200, 100), bg=bg)

        if not p_items:
            console.print(COL_RIGHT, LIST_Y, "Nothing to sell.",
                          fg=(100, 100, 100), bg=(15, 12, 10))

        # Message
        if messages:
            msg = messages[-1][:W - 4]
            console.print(COL_LEFT, cash_y - 1, msg,
                          fg=(255, 220, 100), bg=(15, 12, 10))

        ctx.present(console)

        # ── Input ─────────────────────────────────────────────────
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                raise SystemExit()
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                K = tcod.event.KeySym

                if sym == K.ESCAPE:
                    return messages

                if sym == K.TAB:
                    column = 1 - column
                    selected = 0
                    break

                if sym in (K.UP, K.KP_8):
                    selected = max(0, selected - 1)
                    if column == 0 and selected < scroll_l:
                        scroll_l = selected
                    elif column == 1 and selected < scroll_r:
                        scroll_r = selected
                    break

                if sym in (K.DOWN, K.KP_2):
                    max_idx = len(active_list) - 1
                    selected = min(max_idx, selected + 1)
                    if column == 0 and selected >= scroll_l + MAX_ROWS:
                        scroll_l = selected - MAX_ROWS + 1
                    elif column == 1 and selected >= scroll_r + MAX_ROWS:
                        scroll_r = selected - MAX_ROWS + 1
                    break

                if sym == K.g:
                    pay_with_gold = not pay_with_gold
                    mode = "gold dust" if pay_with_gold else "cash"
                    messages.append(f"Now paying with {mode}.")
                    break

                if sym in (K.RETURN, K.KP_ENTER):
                    if column == 0 and m_items:
                        # BUY
                        mi = m_items[selected]
                        price = mi["price"]
                        if pay_with_gold:
                            oz_needed = price / GOLD_RATE
                            if player.gold_oz >= oz_needed:
                                player.gold_oz -= oz_needed
                                mi["entry"].quantity -= 1
                                try:
                                    bought = make_item(mi["item_id"])
                                    player.inventory.append(bought)
                                    messages.append(
                                        f"Bought {mi['name']} for {oz_needed:.3f} oz gold")
                                except Exception:
                                    messages.append(f"Bought {mi['name']}")
                            else:
                                messages.append(f"Not enough gold ({oz_needed:.3f} oz needed)")
                        else:
                            if player.cash >= price:
                                player.cash -= price
                                mi["entry"].quantity -= 1
                                try:
                                    bought = make_item(mi["item_id"])
                                    player.inventory.append(bought)
                                    messages.append(
                                        f"Bought {mi['name']} for ${price:.2f}")
                                except Exception:
                                    messages.append(f"Bought {mi['name']}")
                            else:
                                messages.append(f"Can't afford ${price:.2f}")
                    elif column == 1 and p_items:
                        # SELL
                        pi = p_items[selected]
                        item = pi["item"]
                        price = pi["price"]
                        player.cash += price
                        if item.stackable and item.quantity > 1:
                            item.quantity -= 1
                        else:
                            player.inventory.remove(item)
                        messages.append(
                            f"Sold {pi['name']} for ${price:.2f}")
                    break
