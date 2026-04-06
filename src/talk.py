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


def _npc_greeting(npc: "NPC", player: "Player",
                   player_rep: float = 0.0) -> str:
    """Generate a contextual greeting based on relationship, traits, and reputation."""
    rel = npc.relationship
    name_str = f", {player.name}" if npc.memory.knows_name else ""

    # Regional reputation affects strangers' first impression
    if rel == 0 and player_rep != 0:
        if player_rep > 50:
            return (f"*{npc.name} straightens up when they see you.* "
                    f"\"You're {player.name}, aren't you? Heard good things.\"")
        if player_rep > 20:
            return (f"\"Heard your name around town{name_str}. "
                    f"Good reputation.\" *{npc.name} nods respectfully.*")
        if player_rep < -30:
            return (f"*{npc.name} tenses up.* \"I know who you are. "
                    f"Don't want any trouble.\"")
        if player_rep < -10:
            return (f"*{npc.name} gives you a guarded look.* "
                    f"\"...Yeah?\"")

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

    if topic == "livery":
        return "__LIVERY__"

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

    # ── Sign language / gesture topics ────────────────────────────────
    if topic == "peace_greeting":
        npc.adjust_relationship(2)
        import random as _srng
        from src.npc_speech import SIGN_RESPONSES
        pool = SIGN_RESPONSES.get("peace_greeting", [
            f"*{npc.name} holds up an open palm.* Peace."])
        return _srng.choice(pool).format(name=npc.name)

    if topic == "ask_directions_sign":
        import random as _srng
        from src.npc_speech import SIGN_RESPONSES
        pool = SIGN_RESPONSES.get("directions", [
            f"*{npc.name} points and holds up fingers.*"])
        dirs = ["north", "south", "east", "west"]
        return _srng.choice(pool).format(
            name=npc.name, direction=_srng.choice(dirs),
            count=_srng.randint(1, 5))

    if topic == "territory_sign":
        import random as _srng
        from src.npc_speech import SIGN_RESPONSES
        pool = SIGN_RESPONSES.get("territory_warn", [
            f"*{npc.name} sweeps their arm across the land.*"])
        return _srng.choice(pool).format(name=npc.name)

    # ── Pidgin-level tribal topics ────────────────────────────────────
    if topic == "hunt_request":
        import random as _srng
        from src.npc_speech import PIDGIN_RESPONSES
        pool = PIDGIN_RESPONSES.get("hunt_request", [
            f"\"You want hunt? Ask chief.\""])
        tribe = getattr(npc, 'tribe', 'the tribe')
        return _srng.choice(pool).format(name=npc.name, tribe=tribe)

    if topic == "safe_passage":
        import random as _srng
        from src.npc_speech import PIDGIN_RESPONSES
        pool = PIDGIN_RESPONSES.get("safe_passage", [
            f"\"Pass through? Maybe. Bring gift.\""])
        return _srng.choice(pool).format(name=npc.name)

    if topic == "guide_hire":
        import random as _srng
        from src.npc_speech import PIDGIN_RESPONSES
        pool = PIDGIN_RESPONSES.get("guide_hire", [
            f"\"I show you way. You pay.\""])
        return _srng.choice(pool).format(name=npc.name)

    if topic == "trapping_rights":
        import random as _srng
        from src.npc_speech import PIDGIN_RESPONSES
        pool = PIDGIN_RESPONSES.get("trapping_rights", [
            f"\"Trap here? This our water.\""])
        return _srng.choice(pool).format(name=npc.name)

    # ── Enlist in war ─────────────────────────────────────────────────
    if topic == "enlist_war":
        return "__ENLIST_WAR__"

    # ── Barter ─────────────────────────────────────────────────────────
    if topic == "barter":
        return "__BARTER__"

    # ── Learn language ────────────────────────────────────────────────
    if topic == "learn_language":
        return "__LEARN_LANGUAGE__"

    # ── Fluent tribal topics (use LLM or template) ────────────────────
    if topic in ("tribal_history", "sacred_places", "alliance", "marriage_tribal"):
        return f"__TRIBAL_{topic.upper()}__"

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

    # Sometimes also share an opinion about another NPC (gossip)
    if hasattr(npc, 'npc_opinions') and npc.npc_opinions and _rnd.random() < 0.4:
        # Pick a random opinion to share
        oid = _rnd.choice(list(npc.npc_opinions.keys()))
        od = npc.npc_opinions[oid]
        other_name = od.get("name", oid)
        op = od["opinion"]
        reason = od["reason"]
        if op > 30:
            gossip = _rnd.choice([
                f'"You know {other_name}? {reason.capitalize()}. Good sort."',
                f'"If you see {other_name}, tell him I said hello. {reason.capitalize()}."',
            ])
        elif op > -15:
            gossip = _rnd.choice([
                f'"That {other_name}... {reason}. Take it how you will."',
                f'*{npc.name} shrugs about {other_name}.* "{reason.capitalize()}."',
            ])
        else:
            gossip = _rnd.choice([
                f'"Watch yourself around {other_name}. {reason.capitalize()}."',
                f'"I wouldn\'t trust {other_name}. {reason.capitalize()}."',
                f'*{npc.name} lowers his voice.* "{other_name}? {reason.capitalize()}."',
            ])
        log.append(gossip)

    return rumor.text


def talk_menu(con: tcod.console.Console, ctx,
              npc: "NPC", player: "Player",
              llm: "Optional[LLMClient]" = None,
              world_map=None, journal=None, date_str: str = "",
              **kwargs):
    """
    Conversation with an NPC.
    Returns (log, llm_history) — log messages and conversation history.
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

    # Record NPC in journal
    if journal and npc.memory.knows_name:
        journal.add_person(npc.name, npc.occupation,
                           notes=f"Met {date_str}" if date_str else "")

    # ── Language barrier detection ──────────────────────────────────────
    npc_tribe = getattr(npc, 'tribe', '')
    npc_ethnicity = getattr(npc, 'ethnicity', '')
    tribal = kwargs.get("tribal")
    weather = kwargs.get("weather", "clear")
    time_period = kwargs.get("time_period", "day")
    current_day = kwargs.get("current_day", 0)

    # Determine shared language level
    # If the NPC speaks English (bilingual or native English), full conversation.
    # Otherwise, check player's knowledge of the NPC's language.
    npc_speaks_english = getattr(npc, 'speaks_english', True)
    language_level = "fluent"  # default

    if npc_speaks_english:
        # NPC speaks English — full conversation always available.
        # They're bilingual: can also teach their native language.
        language_level = "fluent"
    elif npc_tribe and tribal:
        language_level = tribal.get_language_level(npc_tribe)
    elif npc_ethnicity == "chinese":
        language_level = player.languages.get("chinese", "none")
    elif npc_ethnicity == "mexican":
        language_level = player.languages.get("spanish", "none")
    elif npc_ethnicity == "french_canadian":
        language_level = player.languages.get("french", "none")
    elif npc_ethnicity == "german":
        language_level = player.languages.get("german", "none")

    # ── Opening greeting ─────────────────────────────────────────────
    _rep = 0.0
    _rep_tracker = kwargs.get("reputation")
    if _rep_tracker:
        _wm = world_map or kwargs.get("world_map")
        if _wm:
            _region = _wm.get_region(player.world_x, player.world_y)
            _rep = _rep_tracker.get(_region) if _region else 0.0

    # Use memory-informed greeting if available
    if language_level == "none":
        # Untranslated greeting
        from src.npc_speech import UNTRANSLATED
        lang_key = npc_tribe.lower().replace(" ", "_") if npc_tribe else npc_ethnicity
        pool = UNTRANSLATED.get(lang_key, UNTRANSLATED.get(npc_ethnicity, [
            f"*{npc.name} speaks in a language you do not understand.*"]))
        import random as _grng
        greeting = _grng.choice(pool).format(name=npc.name)
        log.append(greeting)
        log.append("  [You share no common language. Only gestures.]")
    elif language_level == "sign":
        from src.npc_speech import SIGN_RESPONSES
        pool = SIGN_RESPONSES.get("peace_greeting", [
            f"*{npc.name} holds up an open palm.* Peace."])
        import random as _grng
        greeting = _grng.choice(pool).format(name=npc.name)
        log.append(greeting)
        log.append("  [Sign language only. Limited topics available.]")
    else:
        try:
            from src.npc_speech import select_memory_greeting
            import random as _grng
            greeting = select_memory_greeting(npc, player.name, current_day,
                                              rng=_grng.Random())
        except (ImportError, Exception):
            greeting = _npc_greeting(npc, player, player_rep=_rep)
        log.append(greeting)
    npc.adjust_relationship(0.5)

    # ── NPC-initiated topics (inject before player menu) ─────────────
    if language_level in ("pidgin", "fluent"):
        try:
            from src.npc_speech import generate_npc_topics
            import random as _trng
            npc_topics = generate_npc_topics(
                npc, player, time_period, weather, current_day,
                tribal=tribal, rng=_trng.Random())
            for urgency, line in npc_topics[:2]:
                log.append(line)
        except (ImportError, Exception):
            pass

    # Schedule check — NPCs not available outside their work hours
    schedule = getattr(npc, 'schedule', {})
    if schedule and time_period in ("night", "dusk"):
        activity = schedule.get(time_period, "home")
        if activity in ("home", "sleep") and npc.occupation in (
                "Merchant", "Banker", "Barber", "Assayer", "Baker",
                "Butcher", "Tailor", "Cobbler", "Apothecary"):
            log.append(f"*{npc.name}'s shop is closed for the night.*")
            return log, llm_history

    # Warrant check — law NPCs react to wanted player
    legal = kwargs.get("legal")
    if legal and hasattr(legal, 'has_active_warrant') and legal.has_active_warrant():
        if npc.occupation in ("Sheriff", "Marshal", "Deputy",
                              "Militia Captain", "Fort Commander"):
            log.append(f'*{npc.name} narrows his eyes.* '
                       f'"Hold it right there. There\'s a warrant out for you."')
            npc.adjust_relationship(-10)
            return log, llm_history

    # Insight check — player reads the NPC based on Wisdom + Intelligence
    from src.npc_system import insight_check
    insight = insight_check(player, npc)
    if insight:
        log.append(f"  [{insight}]")

    # ── Build preset topics based on language level ─────────────────────
    if language_level == "none":
        # Gesture-only: trade and leave
        PRESET_TOPICS = [
            ("Trade (gesture at goods)", "trade"),
            ("Leave", "goodbye"),
        ]
    elif language_level == "sign":
        # Sign language: limited topics
        PRESET_TOPICS = [
            ("Peace greeting (sign)", "peace_greeting"),
            ("Trade (gesture)", "trade"),
            ("Ask directions (point)", "ask_directions_sign"),
        ]
        # Tribal-specific sign topics
        if npc_tribe and tribal:
            standing = tribal.get_standing(npc_tribe).standing
            if standing >= 0:
                PRESET_TOPICS.append(("Territory? (gesture)", "territory_sign"))
        PRESET_TOPICS.append(("Learn words (gesture, point at things)", "learn_language"))
        PRESET_TOPICS.append(("Leave", "goodbye"))
    elif language_level == "pidgin":
        # Broken shared language: most topics, simplified
        PRESET_TOPICS = [
            ("Introduce yourself",    "introduce_self"),
            ("Ask their name",        "ask_name"),
            ("Ask what they do",      "ask_work"),
            ("Ask about rumors",      "ask_rumors"),
        ]
        # Tribal pidgin topics
        if npc_tribe and tribal:
            standing = tribal.get_standing(npc_tribe).standing
            PRESET_TOPICS.append(("Ask about hunting here", "hunt_request"))
            PRESET_TOPICS.append(("Ask for safe passage", "safe_passage"))
            if standing >= 10:
                PRESET_TOPICS.append(("Hire as guide", "guide_hire"))
                PRESET_TOPICS.append(("Ask about trapping rights", "trapping_rights"))
        PRESET_TOPICS.append(("Practice their language", "learn_language"))
    else:
        # Fluent: full conversation
        PRESET_TOPICS = [
            ("Introduce yourself",    "introduce_self"),
            ("Ask their name",        "ask_name"),
            ("Ask what they do",      "ask_work"),
            ("Ask where they're from","ask_region"),
            ("Ask about rumors",      "ask_rumors"),
            ("Ask about gold",        "ask_gold"),
            ("▸ Ask about knowledge...", "show_knowledge"),
        ]
        # Fluent tribal topics
        if npc_tribe and tribal:
            standing = tribal.get_standing(npc_tribe).standing
            if standing >= 20:
                PRESET_TOPICS.append(("Ask about tribal history", "tribal_history"))
                PRESET_TOPICS.append(("Ask about sacred places", "sacred_places"))
            if standing >= 30:
                PRESET_TOPICS.append(("Discuss alliance", "alliance"))
            if standing >= 40 and getattr(npc, 'romantic_eligible', False):
                PRESET_TOPICS.append(("Discuss marriage", "marriage_tribal"))

    # Bilingual NPC can teach their native language even when you're fluent
    # in your shared language (English). E.g. a French-Canadian trapper speaks
    # English but can teach you French. A Native Guide speaks English but can
    # teach you Crow.
    if language_level in ("pidgin", "fluent"):
        _teach_lang = None
        _teach_label = None
        if npc_tribe:
            # Native NPC who speaks English — can teach tribal language
            tribal_lvl = tribal.get_language_level(npc_tribe) if tribal else "fluent"
            if tribal_lvl != "fluent":
                _teach_lang = npc_tribe
                _teach_label = f"{npc_tribe} language"
        elif npc_ethnicity == "french_canadian":
            if player.languages.get("french", "none") != "fluent":
                _teach_lang = "french"
                _teach_label = "French"
        elif npc_ethnicity == "chinese":
            if player.languages.get("chinese", "none") != "fluent":
                _teach_lang = "chinese"
                _teach_label = "Chinese"
        elif npc_ethnicity == "mexican":
            if player.languages.get("spanish", "none") != "fluent":
                _teach_lang = "spanish"
                _teach_label = "Spanish"
        elif npc_ethnicity == "german":
            if player.languages.get("german", "none") != "fluent":
                _teach_lang = "german"
                _teach_label = "German"
        if _teach_lang:
            PRESET_TOPICS.append((f"Ask for {_teach_label} lesson", "learn_language"))

    # Dynamic topics based on NPC and player state
    npc_id = getattr(npc, "npc_id", "")

    # Trading — if NPC is a merchant type
    from src.economy import OCCUPATION_TO_MERCHANT
    if npc.occupation in OCCUPATION_TO_MERCHANT:
        PRESET_TOPICS.append(("Trade / Buy / Sell", "trade"))
        PRESET_TOPICS.append(("Barter (trade items directly)", "barter"))

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

    # Teamster / livery — buy/sell animals
    if npc.occupation in ("Teamster", "Stable Hand", "Livery Keeper"):
        PRESET_TOPICS.append(("Buy / sell animals", "livery"))

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

    # Wartime enlistment — military NPCs offer enlistment during active wars
    if npc_ethnicity != "native_american" and \
            npc.occupation in ("Militia Captain", "Fort Commander", "Soldier",
                               "Officer", "Ranger"):
        try:
            from src.war_system import WarSystem
            _ws = kwargs.get("war_system")
            if _ws:
                _active = _ws.get_active_wars(
                    kwargs.get("year", 1849),
                    kwargs.get("region", ""))
                if _active and not _ws.player_enlisted:
                    war = _active[0]
                    PRESET_TOPICS.append(
                        (f"Enlist ({war.factions[0]})", "enlist_war"))

        except (ImportError, Exception):
            pass

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
                return log, llm_history
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

                        # Try hardcoded knowledge before LLM
                        knowledge_handled = False
                        try:
                            from src.npc_knowledge import match_topic, get_npc_response
                            topic = match_topic(said)
                            if topic:
                                occ = getattr(npc, 'occupation', '')
                                _npc_traits = getattr(npc, 'traits', [])
                                resp = get_npc_response(topic, occ, npc.name,
                                                        npc_traits=_npc_traits)
                                log.append(resp)
                                llm_history.append((npc.name, resp))
                                # Teach plants
                                for plant_id in topic.teaches_plants:
                                    if plant_id not in player.knowledge:
                                        player.knowledge[plant_id] = 1
                                        log.append(f"  [Learned to identify: {plant_id.replace('_', ' ')}]")
                                # Grant skill XP
                                if topic.teaches_skill_xp[1] > 0:
                                    player.gain_skill_xp(
                                        topic.teaches_skill_xp[0],
                                        topic.teaches_skill_xp[1])
                                knowledge_handled = True
                        except ImportError:
                            pass

                        if knowledge_handled:
                            # Store in NPC memory
                            if hasattr(npc, 'expanded_memory'):
                                current_day = kwargs.get("current_day", 0)
                                npc.expanded_memory.add(
                                    content=f'Player asked: "{said}" — {npc.name} replied: "{resp[:120]}"',
                                    day=current_day,
                                    significance=0.5,
                                    valence=0.0,
                                    category="dialogue",
                                )
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
                            # Build speech/mood/lying context for LLM
                            _speech_dir = ""
                            _mood_ctx = ""
                            _lying_inst = ""
                            try:
                                _speech_dir = npc.build_speech_direction(
                                    language_level=language_level)
                                _mood_ctx = npc.build_mood_context(
                                    time_period=time_period, weather=weather)
                                _lying_inst = npc.build_lying_instruction()
                            except (AttributeError, Exception):
                                pass
                            resp = llm.npc_reply(
                                npc_name=npc.name,
                                npc_context=npc_ctx,
                                player_said=said,
                                history=llm_history,
                                speech_direction=_speech_dir,
                                mood_context=_mood_ctx,
                                lying_instruction=_lying_inst,
                            )
                            log.pop()   # remove "thinking" line
                        else:
                            resp = _npc_response(npc, said, player)

                        log.append(resp)
                        llm_history.append((npc.name, resp))

                        # Store each free-text exchange in NPC memory
                        if hasattr(npc, 'expanded_memory'):
                            current_day = kwargs.get("current_day", 0)
                            npc.expanded_memory.add(
                                content=f'Player said: "{said}" — {npc.name} replied: "{resp[:120]}"',
                                day=current_day,
                                significance=0.5,
                                valence=0.0,
                                category="dialogue",
                            )

                        # ── Provocation check ─────────────────────────
                        # Insults, threats, and aggressive language can
                        # anger NPCs. Hot-tempered ones may attack.
                        _PROVOKE_WORDS = {
                            "insult": ("idiot", "fool", "coward", "bastard",
                                       "ugly", "stupid", "worthless", "pathetic",
                                       "scum", "trash", "pig", "worm", "dog"),
                            "threat": ("kill you", "shoot you", "gut you",
                                       "cut you", "murder", "i'll end you",
                                       "die", "throat", "bury you"),
                            "slur": ("chink", "redskin", "greaser", "paddy",
                                     "kraut", "squaw", "savage", "half-breed"),
                        }
                        said_l = said.lower()
                        provoke_level = 0  # 0=none, 1=insult, 2=threat, 3=slur
                        for cat, words in _PROVOKE_WORDS.items():
                            if any(w in said_l for w in words):
                                if cat == "threat":
                                    provoke_level = max(provoke_level, 2)
                                elif cat == "slur":
                                    provoke_level = max(provoke_level, 3)
                                else:
                                    provoke_level = max(provoke_level, 1)

                        if provoke_level > 0:
                            import random as _prng
                            npc.adjust_relationship(-provoke_level * 5)
                            traits_l = [t.lower() for t in getattr(npc, 'traits', [])]
                            # Hot-tempered NPCs react strongly
                            anger_threshold = 12  # d20 roll needed to stay calm
                            if "hot-tempered" in traits_l:
                                anger_threshold = 6
                            elif "patient" in traits_l or "stoic" in traits_l:
                                anger_threshold = 16
                            if "brave" in traits_l:
                                anger_threshold -= 2
                            if "coward" in traits_l or "nervous" in traits_l:
                                anger_threshold += 4
                            # Threats are harder to ignore than insults
                            anger_threshold -= provoke_level * 2

                            calm_roll = _prng.randint(1, 20)
                            if calm_roll < anger_threshold:
                                # NPC snaps
                                if provoke_level >= 2:
                                    snap_msgs = [
                                        f'*{npc.name}\'s face goes dark.* "You just made a mistake."',
                                        f'*{npc.name} reaches for his belt.* "Say that again."',
                                        f'"That\'s it." *{npc.name} stands up, fists clenched.*',
                                    ]
                                else:
                                    snap_msgs = [
                                        f'*{npc.name} shoves you.* "Watch your mouth."',
                                        f'*{npc.name} stands up fast, knocking over his chair.* "You want trouble?"',
                                        f'"Outside. Now." *{npc.name} is done talking.*',
                                    ]
                                log.append(_prng.choice(snap_msgs))
                                npc.combat_state = "hostile"
                                return log, llm_history  # exit talk → engine handles combat
                            elif calm_roll < anger_threshold + 4:
                                # NPC is angry but holds back
                                warn_msgs = [
                                    f'*{npc.name}\'s jaw tightens.* "Careful."',
                                    f'"You\'re pushing your luck." *{npc.name} glares.*',
                                    f'*{npc.name} takes a slow breath.* "Don\'t say that again."',
                                ]
                                log.append(_prng.choice(warn_msgs))
                            # else: NPC ignores it
                    continue

                if sym == K.ESCAPE or sym == K.t and not input_mode:
                    if sym == K.ESCAPE:
                        return log, llm_history
                if sym == K.t:
                    if language_level in ("none", "sign"):
                        log.append("  [You cannot converse — no shared language.]")
                        continue
                    input_mode = True
                    text_input = ""
                    ctx.sdl_window.start_text_input()
                elif sym in (K.UP, K.KP_8):
                    selected = max(0, selected - 1)
                elif sym in (K.DOWN, K.KP_2):
                    selected = min(len(PRESET_TOPICS) - 1, selected + 1)
                elif sym in (K.RETURN, K.KP_ENTER):
                    label, topic = PRESET_TOPICS[selected]

                    # Knowledge menu — show expandable topic list
                    if topic == "show_knowledge":
                        try:
                            from src.npc_knowledge import get_topic_menu, get_npc_response
                            from src.npc_knowledge import KNOWLEDGE_DB
                            from src.menus import pick_from_list
                            occ = getattr(npc, 'occupation', '')
                            topic_list = get_topic_menu(occ)
                            if not topic_list:
                                log.append(f'*{npc.name} shrugs.* "Can\'t help you there."')
                                continue
                            labels = [f"[{cat}] {lbl}" for lbl, cat in topic_list]
                            kidx = pick_from_list(con, ctx,
                                f"Ask {npc.name} about...", labels)
                            if kidx is not None:
                                chosen_label = topic_list[kidx][0]
                                # Find matching topic
                                kt = None
                                for t in KNOWLEDGE_DB:
                                    if t.label == chosen_label:
                                        kt = t
                                        break
                                if kt:
                                    _npc_traits = getattr(npc, 'traits', [])
                                    resp = get_npc_response(kt, occ, npc.name,
                                                            npc_traits=_npc_traits)
                                    log.append(f'You: "{chosen_label}"')
                                    log.append(resp)
                                    llm_history.append(("player", chosen_label))
                                    llm_history.append((npc.name, resp))
                                    for plant_id in kt.teaches_plants:
                                        if plant_id not in player.knowledge:
                                            player.knowledge[plant_id] = 1
                                            log.append(f"  [Learned: {plant_id.replace('_', ' ')}]")
                                    if kt.teaches_skill_xp[1] > 0:
                                        player.gain_skill_xp(
                                            kt.teaches_skill_xp[0],
                                            kt.teaches_skill_xp[1])
                        except ImportError:
                            log.append(f'*{npc.name} has nothing to say about that.*')
                        continue

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
                            _trade_year = kwargs.get("year", 1849)
                            stock = generate_stock(mtype_key, npc_id,
                                                    hash(npc_id) & 0x7FFFFFFF, stype,
                                                    year=_trade_year)
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
                    elif resp == "__LIVERY__":
                        animal_mgr = kwargs.get("animal_mgr")
                        if animal_mgr:
                            w_map = world_map or kwargs.get("world_map")
                            region = w_map.get_region(player.world_x, player.world_y) if w_map else ""
                            loc = w_map.get_location_at(player.world_x, player.world_y) if w_map else None
                            stype = "small_town"
                            if loc:
                                from src.town_gen import classify_settlement
                                stype = classify_settlement(loc.location_type, loc.population)
                            from src.pack_animals import open_livery_ui
                            msgs = open_livery_ui(con, ctx, player, animal_mgr,
                                                   region, stype)
                            for m in msgs:
                                log.append(m)
                            resp = ""
                        else:
                            resp = f'"Sorry, can\'t help you with animals right now."'

                    elif resp == "__ENLIST_WAR__":
                        _ws = kwargs.get("war_system")
                        if _ws:
                            _active = _ws.get_active_wars(
                                kwargs.get("year", 1849),
                                kwargs.get("region", ""))
                            if _active:
                                war = _active[0]
                                from src.menus import pick_from_list
                                roles = [
                                    f"Scout/Guide (${1 + player.skills.get('tracking', 0) * 0.5:.0f}/day)",
                                    f"Soldier (${1:.0f}/day)",
                                    f"Medic (${1 + player.skills.get('firstAid', 0) * 0.5:.0f}/day)",
                                ]
                                ridx = pick_from_list(con, ctx,
                                    f"Enlist with the {war.factions[0]} as:", roles)
                                if ridx is not None:
                                    enlist_msg = _ws.enlist(
                                        war.war_id, war.factions[0])
                                    log.append(enlist_msg)
                                    role_names = ["scout", "soldier", "medic"]
                                    log.append(
                                        f'*{npc.name} nods.* "Good man. '
                                        f'We need {role_names[ridx]}s. '
                                        f'Report at dawn."')
                                    npc.adjust_relationship(10)
                                resp = ""
                        else:
                            resp = f'"No war to enlist in right now."'

                    elif resp == "__BARTER__":
                        # Simple barter: player picks items to offer,
                        # NPC picks items to trade. Values compared.
                        from src.menus import pick_from_list
                        # Player offers
                        offer_items = [i for i in player.inventory
                                       if i.base_value > 0 and i.weight < 50]
                        if not offer_items:
                            resp = f'"You have nothing worth trading."'
                        else:
                            labels = [f"{i.name} (${i.base_value:.2f})"
                                      for i in offer_items]
                            oidx = pick_from_list(con, ctx,
                                "Offer what?", labels)
                            if oidx is not None:
                                offered = offer_items[oidx]
                                # NPC offers items of similar value
                                npc_inv = getattr(npc, 'inventory', [])
                                if not npc_inv:
                                    resp = f'"I don\'t have anything to trade right now."'
                                else:
                                    match = [i for i in npc_inv
                                             if abs(i.base_value - offered.base_value) < offered.base_value * 0.5]
                                    if not match:
                                        match = list(npc_inv)
                                    nlabels = [f"{i.name} (${i.base_value:.2f})"
                                               for i in match]
                                    nidx = pick_from_list(con, ctx,
                                        f"Trade {offered.name} for what?", nlabels)
                                    if nidx is not None:
                                        received = match[nidx]
                                        player.inventory.remove(offered)
                                        npc.inventory.remove(received)
                                        player.inventory.append(received)
                                        npc.inventory.append(offered)
                                        resp = (f'You trade your {offered.name} for '
                                                f'{npc.name}\'s {received.name}.')
                                        npc.adjust_relationship(2)
                                    else:
                                        resp = ""
                            else:
                                resp = ""

                    elif resp == "__LEARN_LANGUAGE__":
                        # Active language learning — grants exposure days
                        import random as _lrng
                        _lang_key = None
                        _lang_label = ""
                        if npc_tribe and tribal:
                            _lang_key = "tribal"
                            _lang_label = npc_tribe
                        elif npc_ethnicity == "chinese":
                            _lang_key = "chinese"
                            _lang_label = "Chinese"
                        elif npc_ethnicity == "mexican":
                            _lang_key = "spanish"
                            _lang_label = "Spanish"
                        elif npc_ethnicity == "french_canadian":
                            _lang_key = "french"
                            _lang_label = "French"

                        if _lang_key == "tribal" and tribal:
                            # Tribal language — add days to tribal system
                            ts = tribal.get_standing(npc_tribe)
                            ts.days_near_tribe += 3
                            old_lvl = ts.language_level
                            adv_msg = tribal._advance_language(npc_tribe)
                            if adv_msg:
                                log.append(f"  [{adv_msg}]")
                                language_level = ts.language_level
                            # Bilingual NPC teaches in English
                            _bilingual = (language_level == "fluent")
                            if _bilingual:
                                _teach_msgs = [
                                    f"*{npc.name} switches to {_lang_label} and translates each phrase.* \"Say it again. Slower.\"",
                                    f"*{npc.name} names things in {_lang_label}, then English, back and forth.* \"You're getting it.\"",
                                    f"*{npc.name} tells a short story in {_lang_label}, stopping to explain each word.*",
                                    f"\"Listen —\" *{npc.name} speaks a sentence in {_lang_label}.* \"Now you try.\"",
                                    f"*{npc.name} teaches you the {_lang_label} words for trade goods, animals, and directions.*",
                                ]
                            else:
                                _teach_msgs = [
                                    f"*{npc.name} points at objects, naming each one slowly. You repeat after them.*",
                                    f"*{npc.name} teaches you words for water, fire, food, friend. You practice.*",
                                    f"*{npc.name} speaks slowly, gesturing. Some words start to stick.*",
                                    f"*{npc.name} draws in the dirt and names things. You begin to understand.*",
                                ]
                            resp = _lrng.choice(_teach_msgs)
                            npc.adjust_relationship(3)
                        elif _lang_key:
                            # Non-tribal language
                            _bilingual = (language_level == "fluent")
                            player._lang_exposure[_lang_key] = \
                                player._lang_exposure.get(_lang_key, 0) + 3
                            days = player._lang_exposure[_lang_key]
                            cur_lvl = player.languages.get(_lang_key, "none")
                            lvl_up = False
                            if cur_lvl == "none" and days >= 7:
                                player.languages[_lang_key] = "sign"
                                log.append(f"  [You've learned basic {_lang_label} gestures.]")
                                language_level = "sign"
                                lvl_up = True
                            elif cur_lvl == "sign" and days >= 21:
                                player.languages[_lang_key] = "pidgin"
                                log.append(f"  [You can now speak pidgin {_lang_label}.]")
                                language_level = "pidgin"
                                lvl_up = True
                            elif cur_lvl == "pidgin" and days >= 90:
                                player.languages[_lang_key] = "fluent"
                                log.append(f"  [You are now fluent in {_lang_label}!]")
                                language_level = "fluent"
                                lvl_up = True

                            if _bilingual:
                                _teach_msgs = [
                                    f"*{npc.name} teaches you {_lang_label} over coffee.* \"Repeat after me...\"",
                                    f"\"You want to learn {_lang_label}? Alright.\" *{npc.name} starts with greetings and numbers.*",
                                    f"*{npc.name} corrects your pronunciation patiently.* \"No, no. Like this —\"",
                                    f"*{npc.name} tells you the {_lang_label} names for everything in sight.*",
                                    f"\"Your {_lang_label} is getting better,\" *{npc.name} says.* \"Keep practicing.\"",
                                ]
                            else:
                                _teach_msgs = [
                                    f"*{npc.name} patiently names objects, correcting your pronunciation.*",
                                    f"*You spend time learning {_lang_label} words. Some stick, some don't.*",
                                    f"*{npc.name} teaches you useful phrases. The language starts making sense.*",
                                ]
                            resp = _lrng.choice(_teach_msgs)
                            npc.adjust_relationship(2)
                        else:
                            resp = f"*{npc.name} doesn't seem to understand what you want.*"

                        # Show progress
                        if _lang_key == "tribal" and tribal:
                            ts = tribal.get_standing(npc_tribe)
                            log.append(f"  [{npc_tribe} language: {ts.language_level} "
                                       f"({ts.days_near_tribe} days exposure)]")
                        elif _lang_key:
                            days = player._lang_exposure.get(_lang_key, 0)
                            lvl = player.languages.get(_lang_key, "none")
                            log.append(f"  [{_lang_label}: {lvl} ({days} days exposure)]")

                    if resp:
                        log.append(resp)
                        llm_history.append(("player", label))
                        llm_history.append((npc.name, resp))
                    if topic == "goodbye":
                        return log, llm_history
                elif sym == K.ESCAPE:
                    return log, llm_history
