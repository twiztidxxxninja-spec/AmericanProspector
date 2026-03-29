"""
Business Ledger UI — tabbed management screen for player businesses.

Core principle: shows what you KNOW, not omniscient data.
Present = live data. Away = stale data from last manager letter.

B key opens this, or use Business Ledger item.
"""

import tcod
import tcod.event
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine import Engine


def open_business_ui(engine: "Engine", console, ctx) -> None:
    """Open the business management ledger."""
    from src.business import BusinessManager, TIER_LABELS, BUSINESS_BLUEPRINTS
    from src.menus import pick_from_list

    mgr = engine.business_mgr

    # If no businesses, offer to start one
    if not mgr.businesses:
        _start_business_flow(engine, console, ctx)
        return

    # If multiple businesses, pick one
    if len(mgr.businesses) > 1:
        labels = [f"{b.name} ({b.tier_label})" for b in mgr.businesses.values()]
        idx = pick_from_list(console, ctx, "Which business?", labels)
        if idx is None:
            return
        biz = list(mgr.businesses.values())[idx]
    else:
        biz = list(mgr.businesses.values())[0]

    _show_ledger(engine, console, ctx, biz)


def _start_business_flow(engine, console, ctx):
    """Flow for founding a new business."""
    from src.menus import pick_from_list
    from src.business import BUSINESS_BLUEPRINTS

    options = [
        "Fur Trading Company",
        "General Store",
        "Saloon",
        "Mining Operation",
        "Freight Line",
        "Blacksmith Shop",
        "Hotel / Boarding House",
        "Custom (describe your idea)",
    ]
    idx = pick_from_list(console, ctx, "Start what kind of business?", options)
    if idx is None:
        return

    _OPTION_TO_KEY = {
        0: "fur_trading", 1: "general_store", 2: "saloon",
        3: "mining_company", 4: "freight_line", 5: "blacksmith",
        6: "hotel",
    }

    wx, wy = engine.player.world_x, engine.player.world_y
    day = engine.time.total_minutes // 1440
    region = engine.world.get_region(wx, wy)
    loc = engine.world.get_location_at(wx, wy)
    stype = "small_town"
    if loc:
        from src.town_gen import classify_settlement
        stype = classify_settlement(loc.location_type, loc.population)

    if idx == 7:
        # Custom — type description
        engine.add_message("Type your business idea:", "advisory")
        # Use simple text input (reuse from gambling)
        console.print(4, 40, "> " + " " * 60, fg=(255, 255, 200), bg=(20, 20, 30))
        ctx.present(console)
        typed = ""
        typing = True
        while typing:
            for evt in tcod.event.wait():
                if isinstance(evt, tcod.event.Quit):
                    raise SystemExit()
                if isinstance(evt, tcod.event.KeyDown):
                    if evt.sym == tcod.event.KeySym.RETURN:
                        typing = False
                    elif evt.sym == tcod.event.KeySym.ESCAPE:
                        return
                    elif evt.sym == tcod.event.KeySym.BACKSPACE:
                        typed = typed[:-1]
                    break
                if isinstance(evt, tcod.event.TextInput):
                    typed += evt.text
                    break
            console.print(6, 40, typed[:55] + "_" + " " * 5,
                          fg=(255, 255, 255), bg=(20, 20, 30))
            ctx.present(console)
        if typed.strip():
            biz, desc = engine.business_mgr.found_custom(
                typed.strip(), typed.strip()[:30],
                wx, wy, day, region, stype)
            engine.add_message(f"Founded: {biz.name}. {desc}", "normal")
    else:
        bp_key = _OPTION_TO_KEY.get(idx, "general_store")
        # Add fur_trading as alias if not in blueprints
        if bp_key not in BUSINESS_BLUEPRINTS:
            bp_key = "general_store"
        name = options[idx]
        biz = engine.business_mgr.found(bp_key, name, wx, wy, day, region, stype)
        engine.add_message(f"Founded: {biz.name}!", "normal")


def _show_ledger(engine, console, ctx, biz):
    """Main tabbed ledger display."""
    from src.business import TIER_LABELS

    tabs = ["Overview", "Employees", "Inventory", "Finances", "Orders", "Market"]
    tab = 0
    W, H = 76, 40
    X = (console.width - W) // 2
    Y = (console.height - H) // 2
    BG = (12, 10, 8)

    # Check if player is at the business location
    is_present = (engine.player.world_x == biz.world_x and
                  engine.player.world_y == biz.world_y)

    while True:
        # ── Draw frame ────────────────────────────────────────────
        for sy in range(Y, Y + H):
            console.print(X, sy, " " * W, fg=(200, 200, 200), bg=BG)
        # Border
        console.print(X, Y, "+" + "-" * (W - 2) + "+", fg=(120, 100, 70), bg=BG)
        console.print(X, Y + H - 1, "+" + "-" * (W - 2) + "+", fg=(120, 100, 70), bg=BG)
        for sy in range(Y + 1, Y + H - 1):
            console.print(X, sy, "|", fg=(120, 100, 70), bg=BG)
            console.print(X + W - 1, sy, "|", fg=(120, 100, 70), bg=BG)

        # Title
        title = f"LEDGER: {biz.name}"
        console.print(X + (W - len(title)) // 2, Y, title,
                      fg=(255, 220, 140), bg=BG)

        # Tab bar
        tx = X + 2
        for i, tname in enumerate(tabs):
            fg = (255, 255, 200) if i == tab else (100, 90, 70)
            console.print(tx, Y + 1, f"[{tname}]", fg=fg, bg=BG)
            tx += len(tname) + 3

        # Status line
        status = "LIVE" if is_present else "FROM LAST LETTER"
        status_fg = (100, 255, 100) if is_present else (255, 200, 80)
        console.print(X + 2, Y + 2, f"Data: {status}", fg=status_fg, bg=BG)

        cy = Y + 4  # content start

        # ── Tab content ───────────────────────────────────────────
        if tab == 0:  # Overview
            console.print(X + 2, cy, f"Type: {biz.category}", fg=(200, 200, 200), bg=BG)
            console.print(X + 2, cy + 1, f"Tier: {biz.tier_label}", fg=(200, 200, 200), bg=BG)
            console.print(X + 2, cy + 2, f"Reputation: {biz.reputation:.0f}/100", fg=(200, 200, 200), bg=BG)
            console.print(X + 2, cy + 3, f"Days operating: {biz.days_operating}", fg=(200, 200, 200), bg=BG)
            console.print(X + 2, cy + 4, f"Employees: {biz.employee_count}", fg=(200, 200, 200), bg=BG)
            cy += 6
            # Quick financials
            net = biz.base_revenue - biz.base_expenses
            console.print(X + 2, cy, f"Revenue: ${biz.base_revenue:.2f}/day", fg=(100, 200, 100), bg=BG)
            console.print(X + 2, cy + 1, f"Expenses: ${biz.base_expenses:.2f}/day", fg=(200, 100, 100), bg=BG)
            console.print(X + 2, cy + 2, f"Net: ${net:.2f}/day", fg=(255, 255, 200), bg=BG)
            console.print(X + 2, cy + 3, f"Cash reserve: ${biz.cash_reserve:.2f}", fg=(220, 200, 100), bg=BG)
            # Events
            cy += 5
            if biz.events:
                console.print(X + 2, cy, "Active events:", fg=(180, 180, 180), bg=BG)
                for evt in biz.events[:3]:
                    cy += 1
                    console.print(X + 4, cy, f"- {evt.description[:60]}", fg=(180, 160, 100), bg=BG)

        elif tab == 1:  # Employees
            if not biz.employees:
                console.print(X + 2, cy, "No employees. Hire someone!", fg=(150, 150, 150), bg=BG)
            else:
                console.print(X + 2, cy, f"{'Name':20s} {'Role':12s} {'Wage':6s} {'Morale':7s}", fg=(180, 180, 180), bg=BG)
                cy += 1
                for emp in biz.employees:
                    console.print(X + 2, cy,
                        f"{emp.name[:20]:20s} {emp.role[:12]:12s} ${emp.wage:.0f}/d  {emp.morale:3.0f}%",
                        fg=(200, 200, 200), bg=BG)
                    cy += 1
            cy += 1
            total_wages = sum(e.wage for e in biz.employees)
            console.print(X + 2, cy, f"Total wages: ${total_wages:.2f}/day", fg=(200, 180, 100), bg=BG)

        elif tab == 2:  # Inventory
            console.print(X + 2, cy, "Business inventory:", fg=(180, 180, 180), bg=BG)
            cy += 1
            console.print(X + 2, cy, f"Stock value: ${biz.stock_value:.2f}", fg=(200, 200, 200), bg=BG)
            cy += 1
            if biz.custom_products:
                for prod in biz.custom_products[:10]:
                    console.print(X + 4, cy, f"- {prod}", fg=(200, 200, 200), bg=BG)
                    cy += 1
            else:
                console.print(X + 2, cy, "(No specific products tracked)", fg=(120, 120, 120), bg=BG)

        elif tab == 3:  # Finances
            console.print(X + 2, cy, "Financial History:", fg=(180, 180, 180), bg=BG)
            cy += 1
            console.print(X + 2, cy, f"Total invested: ${biz.total_invested:.2f}", fg=(200, 200, 200), bg=BG)
            console.print(X + 2, cy + 1, f"Total revenue: ${biz.total_revenue:.2f}", fg=(100, 200, 100), bg=BG)
            console.print(X + 2, cy + 2, f"Total expenses: ${biz.total_expenses:.2f}", fg=(200, 100, 100), bg=BG)
            profit = biz.total_revenue - biz.total_expenses
            pcolor = (100, 255, 100) if profit >= 0 else (255, 100, 100)
            console.print(X + 2, cy + 3, f"Total profit: ${profit:.2f}", fg=pcolor, bg=BG)
            console.print(X + 2, cy + 4, f"Cash reserve: ${biz.cash_reserve:.2f}", fg=(220, 200, 100), bg=BG)
            console.print(X + 2, cy + 5, f"Debt: ${biz.debt:.2f}", fg=(200, 100, 100), bg=BG)
            cy += 7
            # Recent daily history
            if biz.history:
                console.print(X + 2, cy, "Recent days:", fg=(140, 140, 140), bg=BG)
                cy += 1
                for df in biz.history[-5:]:
                    console.print(X + 4, cy,
                        f"Day {df.day}: rev=${df.revenue:.2f} exp=${df.expenses:.2f} "
                        f"net=${df.profit:.2f}",
                        fg=(180, 180, 180), bg=BG)
                    cy += 1

        elif tab == 4:  # Orders
            console.print(X + 2, cy, "STANDING ORDERS:", fg=(180, 180, 120), bg=BG)
            cy += 1
            if biz.standing_orders:
                for so in biz.standing_orders:
                    console.print(X + 4, cy, f"- {so.get('type','')}: {so}",
                                  fg=(200, 200, 200), bg=BG)
                    cy += 1
            else:
                console.print(X + 4, cy, "(none)", fg=(120, 120, 120), bg=BG)
                cy += 1
            cy += 1
            console.print(X + 2, cy, "PENDING ORDERS (unsent):", fg=(255, 200, 100), bg=BG)
            cy += 1
            if biz.pending_orders:
                for po in biz.pending_orders:
                    console.print(X + 4, cy, f"> {po[:60]}", fg=(255, 255, 200), bg=BG)
                    cy += 1
            else:
                console.print(X + 4, cy, "(none — press [N] to add)", fg=(120, 120, 120), bg=BG)
                cy += 1
            cy += 1
            if not is_present and biz.manager_npc_id:
                console.print(X + 2, cy, "[N] New order  [Enter] Send letter  [X] Clear",
                              fg=(140, 140, 140), bg=BG)
            elif is_present:
                console.print(X + 2, cy, "[N] Add instruction (immediate)",
                              fg=(140, 140, 140), bg=BG)

        elif tab == 5:  # Market
            console.print(X + 2, cy, "Known market prices:", fg=(180, 180, 180), bg=BG)
            cy += 1
            console.print(X + 2, cy, "(Market data system coming soon)", fg=(120, 120, 120), bg=BG)

        # Footer
        console.print(X + 2, Y + H - 2,
                      "[</> or 1-6] Tab  [ESC] Close",
                      fg=(100, 100, 100), bg=BG)

        ctx.present(console)

        # ── Input ─────────────────────────────────────────────────
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                raise SystemExit()
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                K = tcod.event.KeySym
                if sym == K.ESCAPE:
                    return

                # Add order (N key)
                if sym == K.n and tab == 4:
                    console.print(X + 2, Y + H - 4, "Order: " + " " * 60,
                                  fg=(255, 255, 200), bg=(20, 20, 30))
                    ctx.present(console)
                    typed = ""
                    typing = True
                    while typing:
                        for evt in tcod.event.wait():
                            if isinstance(evt, tcod.event.Quit):
                                raise SystemExit()
                            if isinstance(evt, tcod.event.KeyDown):
                                if evt.sym == K.RETURN:
                                    typing = False
                                elif evt.sym == K.ESCAPE:
                                    typed = ""
                                    typing = False
                                elif evt.sym == K.BACKSPACE:
                                    typed = typed[:-1]
                                break
                            if isinstance(evt, tcod.event.TextInput):
                                typed += evt.text
                                break
                        console.print(X + 9, Y + H - 4, typed[:55] + "_" + " " * 5,
                                      fg=(255, 255, 255), bg=(20, 20, 30))
                        ctx.present(console)
                    if typed.strip():
                        biz.add_pending_order(typed.strip())
                    break

                # Send letter with pending orders (Enter on Orders tab)
                if sym in (K.RETURN, K.KP_ENTER) and tab == 4:
                    if biz.pending_orders and biz.manager_npc_id and not is_present:
                        letter_body = biz.draft_order_letter()
                        engine.writing.mail.send_letter(
                            sender=engine.player.name,
                            recipient=f"Manager, {biz.name}",
                            body=letter_body,
                        )
                        engine.add_message(
                            f"Letter with {len(biz.pending_orders)} orders sent to manager.",
                            "normal")
                        biz.clear_pending_orders()
                    elif is_present and biz.pending_orders:
                        engine.add_message(
                            f"You give {len(biz.pending_orders)} instructions directly.",
                            "normal")
                        biz.clear_pending_orders()
                    break

                # Clear orders (X key)
                if sym == K.x and tab == 4:
                    biz.clear_pending_orders()
                    break

                if sym in (K.RIGHT, K.PERIOD):
                    tab = min(tab + 1, len(tabs) - 1)
                elif sym in (K.LEFT, K.COMMA):
                    tab = max(tab - 1, 0)
                elif sym in (K.N1, K.KP_1): tab = 0
                elif sym in (K.N2, K.KP_2): tab = 1
                elif sym in (K.N3, K.KP_3): tab = 2
                elif sym in (K.N4, K.KP_4): tab = 3
                elif sym in (K.N5, K.KP_5): tab = 4
                elif sym in (K.N6, K.KP_6): tab = 5
                break
