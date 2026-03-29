"""
NPC conversation system.
Preset topics use rule-based responses; free text goes through the LLM.
"""

import tcod
import tcod.event
import tcod.console
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from src.npc import NPC
    from src.player import Player
    from src.llm_client import LLMClient

def _wrap(text: str, width: int) -> List[str]:
    """Word-wrap text into lines of at most *width* characters."""
    if len(text) <= width:
        return [text]
    lines: List[str] = []
    current = ""
    for word in text.split(" "):
        candidate = (current + " " + word) if current else word
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            # word alone longer than width — hard-break it
            while len(word) > width:
                lines.append(word[:width])
                word = word[width:]
            current = word
    if current:
        lines.append(current)
    return lines


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


def _npc_greeting(npc: "NPC", player: "Player") -> str:
    """Generate a contextual greeting based on relationship and traits."""
    rel = npc.relationship
    name_str = f", {player.name}" if npc.memory.knows_name else ""
    trait    = npc.traits[0] if npc.traits else "neutral"

    if rel < -20:
        return f"*{npc.name} eyes you coldly and says nothing.*"
    if rel < 5:
        if "suspicious" in npc.traits:
            return f"*{npc.name} looks you over warily.* \"What do you want?\""
        if "taciturn" in npc.traits:
            return f"*{npc.name} nods once.*"
        return f"\"Howdy{name_str}.\" *{npc.name} gives a short nod.*"
    if rel < 30:
        return f"\"Good to see you{name_str}.\" *{npc.name} looks up from their work.*"
    return f"\"Hey{name_str}! Good timing.\" *{npc.name} greets you warmly.*"


def _reveal_backstory(npc: "NPC") -> Optional[str]:
    """Reveal one hidden backstory element if any remain."""
    if npc.backstory_hidden:
        fact = npc.backstory_hidden.pop(0)
        npc.backstory_revealed.append(fact)
        return fact
    return None


def _npc_context_block(npc: "NPC", player: "Player" = None) -> str:
    """Build the NPC identity block passed to the LLM."""
    traits = ", ".join(npc.traits) or "unremarkable"
    known  = ", ".join(f"{k} ({v})" for k, v in npc.knowledge.items()) or "none"
    hidden = ". ".join(npc.backstory_hidden)

    player_block = ""
    if player is not None:
        cha      = player.attributes.get("charisma", 10)
        trading  = player.skills.get("trading", 0)
        law      = player.skills.get("law", 0)
        # Plain-English read of charisma for the LLM
        cha_desc = ("silver-tongued" if cha >= 16
                    else "personable" if cha >= 13
                    else "average" if cha >= 9
                    else "abrasive" if cha >= 6
                    else "deeply off-putting")
        player_block = (
            f"\nPLAYER CONTEXT:\n"
            f"  Charisma: {cha}/18 ({cha_desc})\n"
            f"  Trading skill: {trading}   Law skill: {law}\n"
            f"  (High charisma + high trading = smoother social outcomes;"
            f" low charisma = foot-in-mouth even when trying to be friendly)"
        )

    gender_str = {"M": "Male", "F": "Female"}.get(getattr(npc, "gender", "M"), "Male")
    return (
        f"Name: {npc.name}\n"
        f"Age: {npc.age}\n"
        f"Gender: {gender_str}\n"
        f"Occupation: {npc.occupation}\n"
        f"Traits: {traits}\n"
        f"Knowledge: {known}\n"
        f"Relationship with player: {npc.relationship:.0f}/100 ({npc.rel_label()})\n"
        f"Background (not yet revealed): {hidden}\n"
        f"Revealed backstory: {'. '.join(npc.backstory_revealed) or 'nothing yet'}"
        f"{player_block}"
    )


def _npc_response(npc: "NPC", topic: str, player: "Player") -> str:
    """Rule-based responses for preset menu topics."""
    rel   = npc.relationship
    intel = npc.attributes.get("intelligence", 10)

    if topic == "introduce_self":
        npc.memory.knows_name = True
        npc.adjust_relationship(3)
        return (f"\"Name's {npc.name}. {npc.occupation} by trade. "
                f"Been out here {npc.age - 20} years or so.\"")

    if topic == "ask_name":
        npc.memory.knows_name = True
        fact = _reveal_backstory(npc)
        extra = f" {fact}." if fact else ""
        return f"\"Name's {npc.name}.{extra} And you are?\""

    if topic == "ask_work":
        occ = npc.occupation.lower()
        k   = list(npc.knowledge.keys())
        know_str = f" Know a bit about {k[0]}." if k else ""
        return f"\"I'm a {occ}.{know_str} Yourself?\""

    if topic == "ask_region":
        fact = _reveal_backstory(npc)
        if fact:
            return f"\"Well... {fact.lower()}. Don't talk about it much.\""
        return "\"Been around. Nothing worth telling.\""

    if topic == "ask_rumors":
        npc.adjust_relationship(1)
        # Placeholder — real rumor generation handled in talk_menu
        return "__RUMOR__"

    if topic == "sell_gold":
        return "__SELL_GOLD__"

    if topic == "check_mail":
        return "__CHECK_MAIL__"

    if topic == "ask_trade":
        return "\"Not looking to trade right now. Maybe later.\""

    if topic == "trade":
        return "__TRADE__"

    if topic == "delegate":
        return "__DELEGATE__"

    if topic == "dismiss":
        return "__DISMISS__"

    if topic == "recruit_companion":
        if rel > 30:
            return "__RECRUIT_COMPANION__"
        return f"*{npc.name} shakes their head.* \"I barely know you.\""

    if topic == "recruit_employee":
        return "__RECRUIT_EMPLOYEE__"

    if topic == "buy_lot":
        return "__BUY_LOT__"

    if topic == "ask_gold":
        if "placer" in npc.knowledge or "geology" in npc.knowledge:
            npc.adjust_relationship(2)
            return ("\"Watch the inside bends and below the falls. "
                    "Gold's heavy — it drops where the water slows. "
                    "Bedrock crevices too, if you can get to them.\"")
        return "\"Don't know much about it myself. Ask someone at the assay office.\""

    if topic == "goodbye":
        npc.adjust_relationship(1)
        if "friendly" in npc.traits:
            return f"\"Take care out there. Rough country.\""
        return "\"Right. Good luck.\""

    # Free text fallback (pre-LLM placeholder)
    return (f"*{npc.name} considers your words.* "
            f"\"Hmm. I don't rightly know what to make of that.\"")


def _handle_buy_lot(con, ctx, npc, player, kwargs) -> str:
    """Show available lots and let the player buy one, receiving a land deed."""
    from src.menus import draw_box
    import tcod.event

    # Get settlement layout from kwargs or engine state
    settlement_layout = kwargs.get("settlement_layout")
    if not settlement_layout:
        return f'*{npc.name} frowns.* "No lots surveyed in this area yet."'

    # Filter to available (unowned) lots
    lots = [lot for lot in settlement_layout.available_lots if not lot.owner]
    if not lots:
        return f'*{npc.name} shakes his head.* "All lots in town are spoken for."'

    WHITE = (255, 255, 255)
    GREY  = (140, 140, 140)
    CYAN  = (0, 200, 200)
    YELLOW = (255, 255, 0)
    GREEN = (0, 200, 0)
    BG    = (10, 10, 30)
    BG2   = (30, 30, 60)

    selected = 0
    X, Y, W, H = 4, 2, 52, 30
    town_name = settlement_layout.settlement_name or "this town"

    while True:
        draw_box(con, X, Y, W, H, f"Available Lots — {town_name}")
        con.print(X + 2, Y + 1,
                  f"Your cash: ${player.cash:.2f}", fg=YELLOW, bg=BG)
        con.print(X + 2, Y + 2,
                  f"{len(lots)} lot{'s' if len(lots) != 1 else ''} available",
                  fg=GREY, bg=BG)

        # Column headers
        con.print(X + 2, Y + 4, " #  Size       Price    Location", fg=GREY, bg=BG)
        con.draw_rect(X + 1, Y + 5, W - 2, 1, ord("─"), fg=GREY, bg=BG)

        # List lots
        vis_start = max(0, selected - 18)
        for i in range(vis_start, min(len(lots), vis_start + 20)):
            lot = lots[i]
            is_sel = (i == selected)
            fg = CYAN if is_sel else WHITE
            bg = BG2 if is_sel else BG
            prefix = ">" if is_sel else " "
            dist_cx = abs(lot.x + lot.w // 2 - settlement_layout.center_x)
            dist_cy = abs(lot.y + lot.h // 2 - settlement_layout.center_y)
            loc_str = "central" if dist_cx < 15 and dist_cy < 15 else "outer"
            line = (f"{prefix}{i + 1:2d}  {lot.w}x{lot.h} tiles  "
                    f"${lot.price:6.0f}    {loc_str}")
            con.print(X + 2, Y + 6 + (i - vis_start), line[:W - 4],
                      fg=fg, bg=bg)

        # Footer
        con.draw_rect(X + 1, Y + H - 3, W - 2, 1, ord("─"), fg=GREY, bg=BG)
        con.print(X + 2, Y + H - 2,
                  "↑↓ select   Enter buy   Esc cancel", fg=GREY, bg=BG)
        ctx.present(con)

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return ""
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                K = tcod.event.KeySym
                if sym == K.ESCAPE:
                    return f'"No problem. Come back when you\'re ready."'
                elif sym in (K.UP, K.KP_8):
                    selected = max(0, selected - 1)
                elif sym in (K.DOWN, K.KP_2):
                    selected = min(len(lots) - 1, selected + 1)
                elif sym in (K.RETURN, K.KP_ENTER):
                    lot = lots[selected]
                    if player.cash < lot.price:
                        # Can't afford — show message and stay in menu
                        con.print(X + 2, Y + H - 4,
                                  f"You can't afford ${lot.price:.0f}!",
                                  fg=(255, 80, 80), bg=BG)
                        ctx.present(con)
                        tcod.event.wait()  # wait for any key
                        break
                    # Purchase the lot
                    player.cash -= lot.price
                    lot.owner = getattr(player, "name", "player")
                    # Create land deed item
                    from src.items import make_item
                    deed = make_item("land_deed")
                    deed.name = f"Land Deed — {town_name} Lot #{selected + 1}"
                    deed.base_value = lot.price
                    if hasattr(deed, "extra") and deed.extra:
                        deed.extra["lot_wx"] = getattr(player, "world_x", 0)
                        deed.extra["lot_wy"] = getattr(player, "world_y", 0)
                        deed.extra["lot_x"] = lot.x
                        deed.extra["lot_y"] = lot.y
                        deed.extra["lot_w"] = lot.w
                        deed.extra["lot_h"] = lot.h
                    player.inventory.append(deed)
                    return (f'*{npc.name} fills out the paperwork and hands you '
                            f'a deed.* "Congratulations. Lot #{selected + 1}, '
                            f'{lot.w}x{lot.h} tiles, is yours. ${lot.price:.0f}."')


def _handle_rumor(npc: "NPC", player: "Player",
                  world_map, journal, date_str: str,
                  log: list, **kwargs) -> str:
    """
    Generate a map-grounded rumor, apply fog-of-war reveal and journal effects,
    and return the NPC's dialogue string.
    """
    from src.rumor_system import generate_rumor
    import random as _rnd

    rumor = generate_rumor(player, npc, world_map, _rnd.Random())

    # Reveal map tiles around the referenced location
    if world_map and rumor.reveal_radius > 0 and rumor.wx >= 0:
        world_map.mark_visited_radius(rumor.wx, rumor.wy, rumor.reveal_radius)
        # If there's a known location there, mark it discovered
        loc = world_map.get_location_at(rumor.wx, rumor.wy)
        if loc:
            loc.discovered = True

    # Generate a dynamic location from the rumor
    dynamic_locs = kwargs.get("dynamic_locs")
    from src.rumor_system import EVENT_CATEGORIES
    if dynamic_locs and rumor.wx >= 0:
        region = world_map.get_region(rumor.wx, rumor.wy) if world_map else ""
        year = kwargs.get("year", 1849)
        if rumor.category == "gold" or rumor.category == "rich_strike":
            dl = dynamic_locs.from_npc_rumor(
                player.world_x, player.world_y, region, year, _rnd.Random())
            if dl:
                dl.discovered = True
        elif rumor.category in EVENT_CATEGORIES:
            # Create an event location at the referenced tile
            _EVENT_LOC_TYPES = {
                "bandits": "outlaw_camp", "claim_jumpers": "prospector_camp",
                "lost_traveler": "abandoned_camp", "abandoned_claim": "abandoned_camp",
                "wagon_wreck": "waystation", "bounty": "outlaw_camp",
                "rustlers": "outlaw_camp", "sick_camp": "prospector_camp",
                "rich_strike": "mining_camp", "card_game": "prospector_camp",
                "duel_challenge": "prospector_camp", "stolen_goods": "abandoned_camp",
                "ambush_site": "outlaw_camp", "feuding_camps": "mining_camp",
                "lynch_mob": "mining_camp", "stranded_family": "abandoned_camp",
                "injured_miner": "prospector_camp", "horse_sale": "waystation",
                "traveling_preacher": "waystation", "medicine_show": "waystation",
                "auction": "waystation", "land_dispute": "prospector_camp",
                "cave_entrance": "abandoned_camp", "old_bones": "abandoned_camp",
                "native_artifacts": "native_camp", "ghost_camp": "abandoned_camp",
                "hidden_spring": "waystation", "prospector_journal": "abandoned_camp",
                "unguarded_shipment": "waystation", "corrupt_official": "waystation",
                "moonshine_still": "outlaw_camp", "counterfeiter": "outlaw_camp",
            }
            loc_type = _EVENT_LOC_TYPES.get(rumor.category, "prospector_camp")
            from src.dynamic_locations import DynamicLocation
            evt_name = rumor.place_name or f"Rumored {rumor.category.replace('_', ' ')}"
            event_loc = DynamicLocation(
                id="",  # filled by add()
                name=evt_name,
                world_x=rumor.wx, world_y=rumor.wy,
                loc_type=loc_type, stage="active",
                discovered=True,
                notes=f"Rumor: {rumor.category}. Source: {npc.name}.",
            )
            dynamic_locs.add(event_loc)

    # Add to journal rumors tab
    if journal and rumor.journal_text:
        journal.add_rumor(date_str, npc.name, rumor.journal_text)

    # Add a place note for specific tips
    if journal and rumor.place_name and rumor.wx >= 0:
        cat_note = {
            "gold":     "Gold reported here. Unverified.",
            "location": "Settlement or waypoint.",
            "water":    "Reliable water source.",
            "trail":    "Trail or crossing.",
            "danger":   "Dangerous terrain or hostile area.",
            "bandits":  "DANGER: Bandits reported in the area.",
            "claim_jumpers": "Claim dispute — could be violent.",
            "lost_traveler":  "Missing person — may need help.",
            "abandoned_claim": "Abandoned claim — could still have gold.",
            "wagon_wreck":    "Wrecked wagon — salvageable goods.",
            "bounty":         "Wanted fugitive in the area.",
            "rustlers":       "Livestock thieves operating here.",
            "sick_camp":      "Disease outbreak — approach with caution.",
            "rich_strike":    "New gold strike — rush conditions.",
            "card_game":      "High-stakes gambling.",
            "duel_challenge": "Gunfight brewing.",
            "stolen_goods":   "Stolen goods cached nearby.",
            "ambush_site":    "DANGER: Ambush site, armed attackers.",
            "feuding_camps":  "Feud between miners — dangerous.",
            "lynch_mob":      "Vigilante justice — volatile.",
            "stranded_family": "Stranded family needs help.",
            "injured_miner":  "Injured person needs medical aid.",
            "horse_sale":     "Horses/mules for sale.",
            "traveling_preacher": "Circuit preacher visiting.",
            "medicine_show":  "Traveling medicine seller.",
            "auction":        "Estate/foreclosure auction.",
            "land_dispute":   "Property dispute — legal trouble.",
            "cave_entrance":  "Unexplored cave — potential ore.",
            "old_bones":      "Human remains found.",
            "native_artifacts": "Ancient artifacts.",
            "ghost_camp":     "Mysteriously abandoned camp.",
            "hidden_spring":  "Hidden water source.",
            "prospector_journal": "Dead prospector's notes — possible gold.",
            "unguarded_shipment": "Vulnerable supply shipment.",
            "corrupt_official": "Corrupt official — opportunity or justice.",
            "moonshine_still": "Illegal still — whiskey for sale.",
            "counterfeiter":  "Counterfeit gold/coins circulating.",
        }.get(rumor.category, "Point of interest.")
        journal.add_place(rumor.place_name, rumor.wx, rumor.wy, cat_note)

    # Append a meta-note to the conversation log for directional/specific tips
    if rumor.specificity == "directional" and rumor.wx >= 0:
        dx = rumor.wx - player.world_x
        dy = rumor.wy - player.world_y
        from src.rumor_system import _dir, _dist_text
        log.append(f"  [Area revealed on map — {_dist_text(max(abs(dx), abs(dy)))} "
                   f"{_dir(dx, dy)}]")
    elif rumor.specificity == "specific" and rumor.wx >= 0:
        log.append(f"  [Location added to journal — {rumor.place_name}]")

    return rumor.text


def talk_menu(con: tcod.console.Console, ctx,
              npc: "NPC", player: "Player",
              llm: "Optional[LLMClient]" = None,
              world_map=None, journal=None, date_str: str = "",
              **kwargs) -> List[str]:
    """
    Conversation with an NPC.
    Returns list of log messages for the message log.
    """
    W = 66
    H = 36
    X = (con.width  - W) // 2
    Y = (con.height - H) // 2

    log: List[str] = []          # conversation lines for this session
    llm_history: List[tuple] = []  # (speaker, text) for LLM context
    selected = 0
    input_mode = False
    text_input = ""
    waiting_llm = False          # True while blocking on LLM reply
    state_extra_cache = {}       # per-session cache for merchant stock etc.

    # Opening greeting
    greeting = _npc_greeting(npc, player)
    log.append(greeting)
    npc.adjust_relationship(0.5)

    # Insight check — player reads the NPC based on Wisdom + Intelligence
    from src.npc_system import insight_check
    insight = insight_check(player, npc)
    if insight:
        log.append(f"  [{insight}]")

    PRESET_TOPICS = [
        ("Introduce yourself",    "introduce_self"),
        ("Ask their name",        "ask_name"),
        ("Ask what they do",      "ask_work"),
        ("Ask where they're from","ask_region"),
        ("Ask about rumors",      "ask_rumors"),
        ("Ask about gold",        "ask_gold"),
    ]

    # Dynamic topics based on NPC and player state
    npc_id = getattr(npc, "npc_id", "")

    # Trading — if NPC is a merchant type
    from src.economy import OCCUPATION_TO_MERCHANT
    if npc.occupation in OCCUPATION_TO_MERCHANT:
        PRESET_TOPICS.append(("Trade / Buy / Sell", "trade"))

    # Mail pickup — available at merchant NPCs in towns
    writing_mgr = kwargs.get("writing")
    if writing_mgr and npc.occupation in OCCUPATION_TO_MERCHANT:
        player_name = getattr(player, "name", "")
        current_day = kwargs.get("current_day", 0)
        # Check if this town has mail for the player
        _wm = world_map or kwargs.get("world_map")
        if _wm:
            loc = _wm.get_location_at(
                getattr(player, "world_x", 0), getattr(player, "world_y", 0))
            if loc:
                available = writing_mgr.mail.check_mail(loc.name, current_day, player_name)
                count = len(available)
                if count > 0:
                    PRESET_TOPICS.append((f"Check for mail ({count} letter{'s' if count != 1 else ''})", "check_mail"))
                else:
                    PRESET_TOPICS.append(("Check for mail", "check_mail"))

    # Sell gold dust — available at merchants and bankers
    if npc.occupation in OCCUPATION_TO_MERCHANT and player.gold_oz > 0:
        from src.economy import GOLD_PRICE_PER_OZ, RAW_DUST_FINENESS
        dust_value = player.gold_oz * GOLD_PRICE_PER_OZ * RAW_DUST_FINENESS
        PRESET_TOPICS.append((
            f"Sell gold dust ({player.gold_oz:.3f} oz ≈ ${dust_value:.2f})",
            "sell_gold"))

    # Land Agent — buy a lot
    if npc.occupation == "Land Agent":
        PRESET_TOPICS.append(("Buy a town lot", "buy_lot"))

    # Companion system
    from src.companions import CompanionManager
    comp_mgr = kwargs.get("companion_mgr")
    if comp_mgr and comp_mgr.get(npc_id):
        link = comp_mgr.get(npc_id)
        PRESET_TOPICS.append((f"Delegate task to {npc.name}", "delegate"))
        PRESET_TOPICS.append((f"Dismiss {npc.name}", "dismiss"))
    elif comp_mgr and npc.relationship > 20:
        PRESET_TOPICS.append(("Ask to join you (companion)", "recruit_companion"))
    elif comp_mgr and npc.relationship > 5:
        PRESET_TOPICS.append(("Offer employment", "recruit_employee"))

    PRESET_TOPICS.append(("Say goodbye", "goodbye"))

    from src.menus import draw_box

    while True:
        draw_box(con, X, Y, W, H,
                 f"Talking to {npc.display_name()} [{npc.rel_label()}]")

        # NPC info strip
        con.print(X + 2, Y + 1,
                  f"{npc.occupation}  |  {npc.age}y  |  {', '.join(npc.traits[:2])}",
                  fg=GREY, bg=BG)

        # Conversation log (upper portion) — word-wrapped
        log_h = 14
        con.draw_rect(X + 1, Y + 2, W - 2, log_h, ord(" "), fg=WHITE, bg=(10, 10, 20))
        wrapped_log: List[str] = []
        for entry in log:
            wrapped_log.extend(_wrap(entry, W - 4))
        visible_log = wrapped_log[-(log_h):]
        for i, line in enumerate(visible_log):
            con.print(X + 2, Y + 2 + i, line, fg=WHITE, bg=(10, 10, 20))

        # Divider
        con.draw_rect(X + 1, Y + 2 + log_h, W - 2, 1, ord("─"), fg=DGREY, bg=BG)

        # Preset options
        opts_y = Y + 3 + log_h
        for i, (label, _) in enumerate(PRESET_TOPICS):
            if opts_y + i >= Y + H - 5:
                break
            is_sel = (not input_mode) and i == selected
            color  = CYAN if is_sel else WHITE
            bgc    = BG2  if is_sel else BG
            prefix = ">" if is_sel else " "
            con.print(X + 2, opts_y + i,
                      f"{prefix} {label}"[:W - 4], fg=color, bg=bgc)

        # Free text input
        input_y = Y + H - 5
        con.draw_rect(X + 1, input_y - 1, W - 2, 1, ord("─"), fg=DGREY, bg=BG)
        cursor = "_" if input_mode else " "
        fg_input = YELLOW if input_mode else GREY
        full = f"Say: {text_input}{cursor}"
        max_w = W - 4
        con.print(X + 2, input_y, full[:max_w], fg=fg_input, bg=BG)
        if len(full) > max_w:
            con.print(X + 2, input_y + 1, full[max_w:max_w * 2], fg=fg_input, bg=BG)

        # Footer
        con.draw_rect(X + 1, Y + H - 3, W - 2, 1, ord("─"), fg=DGREY, bg=BG)
        if input_mode:
            con.print(X + 2, Y + H - 2,
                      "Type what you say   Enter send   Esc cancel",
                      fg=GREY, bg=BG)
        else:
            con.print(X + 2, Y + H - 2,
                      "↑↓ select   Enter say   T type freely   Esc leave",
                      fg=GREY, bg=BG)

        ctx.present(con)

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return log
            if isinstance(event, tcod.event.TextInput) and input_mode:
                text_input += event.text
                continue
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                K   = tcod.event.KeySym

                if input_mode:
                    if sym == K.ESCAPE:
                        input_mode = False
                        text_input = ""
                        ctx.sdl_window.stop_text_input()
                    elif sym == K.BACKSPACE and text_input:
                        text_input = text_input[:-1]
                    elif sym in (K.RETURN, K.KP_ENTER) and text_input.strip():
                        said = text_input.strip()
                        text_input = ""
                        input_mode = False
                        ctx.sdl_window.stop_text_input()
                        log.append(f'You: "{said}"')
                        llm_history.append(("player", said))

                        # Intercept buy/sell commands during trade
                        said_low = said.lower().strip()
                        trade_handled = False
                        if said_low.startswith("buy ") and npc.occupation in OCCUPATION_TO_MERCHANT:
                            item_name = said[4:].strip()
                            stock_key = f"_stock_{npc_id}"
                            stock = state_extra_cache.get(stock_key)
                            if stock:
                                entry = None
                                for e in stock.items:
                                    if e.name.lower() == item_name.lower() and e.quantity > 0:
                                        entry = e
                                        break
                                if entry:
                                    te = kwargs.get("trade_engine")
                                    w_map = kwargs.get("world_map")
                                    region = w_map.get_region(player.world_x, player.world_y) if w_map else ""
                                    price = entry.base_price * 1.4
                                    if te:
                                        from src.items import Item as _BItem
                                        tmp = _BItem(id=entry.item_id, name=entry.name,
                                                      weight=0, category=entry.category,
                                                      base_value=entry.base_price, condition=entry.condition)
                                        price = te.get_buy_price(tmp, region, "small_town",
                                                                  OCCUPATION_TO_MERCHANT.get(npc.occupation, "general_store"))
                                    if player.cash >= price:
                                        player.cash -= price
                                        entry.quantity -= 1
                                        from src.items import make_item, Item as _MItem
                                        try:
                                            bought = make_item(entry.item_id)
                                        except (ValueError, KeyError):
                                            bought = _MItem(id=entry.item_id, name=entry.name,
                                                             weight=1.0, category=entry.category,
                                                             base_value=entry.base_price)
                                        player.inventory.append(bought)
                                        resp = f'"That\'ll be ${price:.2f}." *{npc.name} hands you the {entry.name}.*'
                                    else:
                                        resp = f'"That\'s ${price:.2f}. You don\'t have enough."'
                                else:
                                    resp = f'"I don\'t have any {item_name}."'
                                log.append(resp)
                                llm_history.append((npc.name, resp))
                                trade_handled = True

                        elif said_low.startswith("sell ") and npc.occupation in OCCUPATION_TO_MERCHANT:
                            item_name = said[5:].strip()
                            found_item = None
                            found_idx = -1
                            for ii, inv_item in enumerate(player.inventory):
                                if inv_item.name.lower() == item_name.lower():
                                    found_item = inv_item
                                    found_idx = ii
                                    break
                            if found_item:
                                te = kwargs.get("trade_engine")
                                w_map = kwargs.get("world_map")
                                region = w_map.get_region(player.world_x, player.world_y) if w_map else ""
                                price = found_item.base_value * 0.35
                                if te:
                                    price = te.get_sell_price(found_item, region, "small_town",
                                                              OCCUPATION_TO_MERCHANT.get(npc.occupation, "general_store"))
                                player.cash += price
                                player.inventory.pop(found_idx)
                                resp = f'*{npc.name} examines the {found_item.name}.* "I\'ll give you ${price:.2f} for it."'
                            else:
                                resp = f'"You don\'t seem to have any {item_name}."'
                            log.append(resp)
                            llm_history.append((npc.name, resp))
                            trade_handled = True

                        if trade_handled:
                            continue

                        if llm is not None and llm.available:
                            # Show "thinking" indicator
                            log.append(f"*{npc.name} considers...*")
                            draw_box(con, X, Y, W, H,
                                     f"Talking to {npc.display_name()} [{npc.rel_label()}]")
                            ctx.present(con)
                            # Use expanded NPC context if available
                            try:
                                from src.npc_system import build_npc_llm_context
                                npc_ctx = build_npc_llm_context(npc, player)
                            except (ImportError, AttributeError):
                                npc_ctx = _npc_context_block(npc, player)
                            resp = llm.npc_reply(
                                npc_name=npc.name,
                                npc_context=npc_ctx,
                                player_said=said,
                                history=llm_history,
                            )
                            log.pop()   # remove "thinking" line
                        else:
                            resp = _npc_response(npc, said, player)

                        log.append(resp)
                        llm_history.append((npc.name, resp))
                    continue

                if sym == K.ESCAPE or sym == K.t and not input_mode:
                    if sym == K.ESCAPE:
                        return log
                if sym == K.t:
                    input_mode = True
                    text_input = ""
                    ctx.sdl_window.start_text_input()
                elif sym in (K.UP, K.KP_8):
                    selected = max(0, selected - 1)
                elif sym in (K.DOWN, K.KP_2):
                    selected = min(len(PRESET_TOPICS) - 1, selected + 1)
                elif sym in (K.RETURN, K.KP_ENTER):
                    label, topic = PRESET_TOPICS[selected]
                    log.append(f'You: "{label}"')
                    resp = _npc_response(npc, topic, player)

                    if resp == "__RUMOR__":
                        resp = _handle_rumor(
                            npc, player, world_map, journal, date_str, log,
                            dynamic_locs=kwargs.get("dynamic_locs"),
                            year=kwargs.get("year", 1849))
                    elif resp == "__SELL_GOLD__":
                        if player.gold_oz > 0:
                            from src.economy import GOLD_PRICE_PER_OZ, RAW_DUST_FINENESS
                            oz = player.gold_oz
                            # Merchant takes a cut (lowball based on type)
                            mtype_key = OCCUPATION_TO_MERCHANT.get(npc.occupation, "general_store")
                            from src.economy import MERCHANT_TYPES
                            mtype = MERCHANT_TYPES.get(mtype_key)
                            cut = mtype.lowball if mtype else 0.80
                            value = oz * GOLD_PRICE_PER_OZ * RAW_DUST_FINENESS * cut
                            player.cash += value
                            player.gold_oz = 0.0
                            resp = (f'*{npc.name} weighs the dust on a small scale.* '
                                    f'"That\'s {oz:.3f} ounces. I\'ll give you ${value:.2f}."')
                            npc.adjust_relationship(2)
                        else:
                            resp = f'"You don\'t have any gold dust to sell."'
                    elif resp == "__CHECK_MAIL__":
                        writing_mgr = kwargs.get("writing")
                        w_map = kwargs.get("world_map")
                        p_name = player.name
                        c_day = kwargs.get("current_day", 0)
                        town_name = ""
                        if w_map:
                            loc_here = w_map.get_location_at(player.world_x, player.world_y)
                            if loc_here:
                                town_name = loc_here.name
                        if writing_mgr and town_name:
                            available = writing_mgr.mail.check_mail(town_name, c_day, p_name)
                            if available:
                                resp = f'*{npc.name} rummages through a stack of letters.*'
                                log.append(resp)
                                for mail_item in available:
                                    writing_mgr.mail.pickup(mail_item.id)
                                    log.append(f'  Letter from {mail_item.sender}:')
                                    # Add to journal
                                    journal_obj = kwargs.get("journal") or journal
                                    if journal_obj:
                                        from src.journal import Letter as JLetter
                                        journal_obj.add_letter(JLetter(
                                            date_str=kwargs.get("date_str", ""),
                                            sender=mail_item.sender,
                                            recipient=p_name,
                                            body=mail_item.body,
                                        ))
                                    # Check for enclosed payment
                                    if "$" in mail_item.body:
                                        import re
                                        amounts = re.findall(r'\$(\d+\.?\d*)', mail_item.body)
                                        for amt_str in amounts:
                                            try:
                                                player.cash += float(amt_str)
                                                log.append(f'  [Enclosed: ${float(amt_str):.2f}]')
                                            except ValueError:
                                                pass
                                    for line in mail_item.body.split('\n')[:4]:
                                        log.append(f'    {line.strip()}')
                                resp = ""
                            else:
                                resp = f'*{npc.name} checks.* "Nothing for you today."'
                        else:
                            resp = f'*{npc.name} shrugs.* "No mail service here."'
                    elif resp == "__TRADE__" or resp == "__DO_TRADE__":
                        # Open visual trade UI
                        from src.economy import OCCUPATION_TO_MERCHANT
                        from src.economy import generate_stock
                        from src.trade_ui import open_trade_ui
                        mtype_key = OCCUPATION_TO_MERCHANT.get(npc.occupation, "general_store")
                        trade_engine = kwargs.get("trade_engine")
                        region = ""
                        stype = "small_town"
                        w_map = world_map or kwargs.get("world_map")
                        if w_map:
                            region = w_map.get_region(player.world_x, player.world_y)
                            loc_here = w_map.get_location_at(player.world_x, player.world_y)
                            if loc_here:
                                from src.town_gen import classify_settlement
                                stype = classify_settlement(loc_here.location_type, loc_here.population)

                        stock_key = f"_stock_{npc_id}"
                        if stock_key not in state_extra_cache:
                            stock = generate_stock(mtype_key, npc_id,
                                                    hash(npc_id) & 0x7FFFFFFF, stype)
                            state_extra_cache[stock_key] = stock
                        stock = state_extra_cache[stock_key]

                        trade_msgs = open_trade_ui(
                            con, ctx, player, npc, stock,
                            trade_engine=trade_engine, region=region,
                            settlement_type=stype, merchant_type=mtype_key)
                        for tm in trade_msgs[-3:]:
                            log.append(tm)
                        resp = ""
                    elif resp == "__DELEGATE__":
                        comp_mgr = kwargs.get("companion_mgr")
                        if comp_mgr:
                            link = comp_mgr.get(npc_id)
                            if link:
                                from src.companions import delegate_menu
                                current_min = kwargs.get("current_minute", 0)
                                result = delegate_menu(
                                    con, ctx, link, npc, current_min, comp_mgr)
                                if result:
                                    accepted, msg = result
                                    resp = msg
                                else:
                                    resp = "(Cancelled.)"
                            else:
                                resp = "They don't work with you."
                        else:
                            resp = ""
                    elif resp == "__DISMISS__":
                        comp_mgr = kwargs.get("companion_mgr")
                        if comp_mgr:
                            dismissed = comp_mgr.dismiss(npc_id)
                            if dismissed:
                                resp = f"*{npc.name} nods slowly.* \"Fair enough. Good luck out there.\""
                                npc.adjust_relationship(-5)
                            else:
                                resp = ""
                        else:
                            resp = ""
                    elif resp == "__RECRUIT_COMPANION__":
                        comp_mgr = kwargs.get("companion_mgr")
                        if comp_mgr:
                            from src.companions import Role
                            comp_mgr.recruit(npc_id, npc.name, Role.COMPANION)
                            npc.adjust_relationship(10)
                            resp = (f'*{npc.name} grins.* "Alright, partner. '
                                    f'I\'m with you. Let\'s see what we find."')
                        else:
                            resp = ""
                    elif resp == "__RECRUIT_EMPLOYEE__":
                        comp_mgr = kwargs.get("companion_mgr")
                        if comp_mgr:
                            from src.companions import Role
                            comp_mgr.recruit(npc_id, npc.name, Role.EMPLOYEE,
                                              wage=1.0)
                            resp = (f'*{npc.name} considers.* "A dollar a day? '
                                    f'I can do that. When do I start?"')
                        else:
                            resp = ""
                    elif resp == "__BUY_LOT__":
                        resp = _handle_buy_lot(
                            con, ctx, npc, player, kwargs)

                    if resp:
                        log.append(resp)
                        llm_history.append(("player", label))
                        llm_history.append((npc.name, resp))
                    if topic == "goodbye":
                        return log
                elif sym == K.ESCAPE:
                    return log
