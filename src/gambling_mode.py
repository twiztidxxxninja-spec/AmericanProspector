"""
Gambling mode — poker and card games at camps/saloons.

Simple but meaningful: not a full poker simulator, but a risk/reward
system where Charisma (bluffing), Intelligence (reading opponents),
and luck determine outcomes. Multiple rounds with escalating stakes.

Enter via action menu near a card_game location, or type "gamble"/"poker".

Controls:
  [1] Call (match the bet)
  [2] Raise (increase the bet — confidence play)
  [3] Fold (lose your ante, keep the rest)
  [4] Bluff (Charisma check — win big or get caught)
  [ESC] Leave the table
"""

import tcod
import tcod.event
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine import Engine


# ── Hand quality (determines base win probability) ────────────────────────

HANDS = [
    ("Nothing",        0.30),  # 30% of the time
    ("Pair",           0.25),
    ("Two Pair",       0.15),
    ("Three of a Kind",0.10),
    ("Straight",       0.08),
    ("Flush",          0.05),
    ("Full House",     0.04),
    ("Four of a Kind", 0.02),
    ("Straight Flush", 0.009),
    ("Royal Flush",    0.001),
]

HAND_NAMES = [h[0] for h in HANDS]


def _draw_hand(rng) -> int:
    """Draw a hand quality index (0=nothing, 9=royal flush)."""
    r = rng.random()
    cumulative = 0.0
    for i, (_, prob) in enumerate(HANDS):
        cumulative += prob
        if r < cumulative:
            return i
    return 0


def _opponent_personality(rng) -> dict:
    """Generate a random opponent's playing style."""
    styles = [
        {"name": "Careful Pete", "aggression": 0.2, "bluff_chance": 0.1,
         "tell": "scratches his ear when he's bluffing"},
        {"name": "Wild Bill", "aggression": 0.7, "bluff_chance": 0.5,
         "tell": "goes quiet when he has a real hand"},
        {"name": "Quiet Sam", "aggression": 0.3, "bluff_chance": 0.2,
         "tell": "taps the table when he's confident"},
        {"name": "Lucky Joe", "aggression": 0.5, "bluff_chance": 0.3,
         "tell": "orders another drink when he's nervous"},
        {"name": "The Stranger", "aggression": 0.6, "bluff_chance": 0.4,
         "tell": "never looks at his cards twice"},
        {"name": "Old Hank", "aggression": 0.1, "bluff_chance": 0.1,
         "tell": "chews his tobacco slower when thinking"},
    ]
    return rng.choice(styles)


# ── Main gambling loop ────────────────────────────────────────────────────

def _enter_poker(engine: "Engine", console, ctx) -> None:
    """Full poker/gambling session."""
    player = engine.player
    rng = random.Random()

    if player.cash < 1.0:
        engine.add_message("You need at least $1 to sit at the table.", "advisory")
        return

    # Generate opponents
    opponents = [_opponent_personality(rng) for _ in range(rng.randint(2, 4))]
    opp_names = [o["name"] for o in opponents]

    ante = 1.0  # starting ante
    round_num = 0
    total_won = 0.0
    total_lost = 0.0
    messages = []

    cha = player.attributes.get("charisma", 10)
    intel = player.attributes.get("intelligence", 10)

    def add_msg(text):
        messages.append(text)
        if len(messages) > 20:
            messages.pop(0)

    add_msg(f"You sit down at the table. {len(opponents)} players.")
    add_msg(f"Opponents: {', '.join(opp_names)}.")
    add_msg(f"Ante is ${ante:.2f}. You have ${player.cash:.2f}.")

    while True:
        round_num += 1
        pot = ante * (len(opponents) + 1)

        if player.cash < ante:
            add_msg("You can't cover the ante. Game over.")
            break

        player.cash -= ante

        # Draw hands
        player_hand = _draw_hand(rng)
        opp_hands = [(o, _draw_hand(rng)) for o in opponents]
        best_opp = max(opp_hands, key=lambda x: x[1])
        best_opp_hand = best_opp[1]
        best_opp_player = best_opp[0]

        # Can player read opponent? (Intelligence check)
        can_read = False
        if intel >= 8 and rng.random() < 0.3 + intel * 0.03:
            can_read = True

        # ── Render ────────────────────────────────────────────────
        console.clear()
        console.draw_rect(0, 0, 120, 1, ord(" "), fg=(255, 255, 255), bg=(40, 60, 30))
        console.print(2, 0, f"POKER  —  Round {round_num}  —  Pot: ${pot:.2f}",
                      fg=(255, 255, 200), bg=(40, 60, 30))

        # Player's hand
        y = 3
        console.print(4, y, f"Your hand: {HAND_NAMES[player_hand]}", fg=(255, 255, 255))
        y += 1
        hand_quality = "strong" if player_hand >= 4 else "decent" if player_hand >= 2 else "weak"
        hq_color = (100, 255, 100) if hand_quality == "strong" else \
                   (255, 255, 100) if hand_quality == "decent" else (255, 120, 120)
        console.print(4, y, f"  ({hand_quality})", fg=hq_color)
        y += 2

        # Opponents
        console.print(4, y, "── At the table ──", fg=(140, 140, 140))
        y += 1
        for o, h in opp_hands:
            if can_read:
                # Player can read tells
                if h >= 4:
                    tell_msg = f"  {o['name']} — {o['tell']}. Looks confident."
                    fg = (255, 200, 100)
                elif h <= 1 and o["bluff_chance"] > 0.3:
                    tell_msg = f"  {o['name']} — {o['tell']}. Might be bluffing."
                    fg = (200, 200, 255)
                else:
                    tell_msg = f"  {o['name']} — hard to read."
                    fg = (180, 180, 180)
            else:
                tell_msg = f"  {o['name']}"
                fg = (180, 180, 180)
            console.print(4, y, tell_msg, fg=fg)
            y += 1

        y += 1
        console.print(4, y, f"Cash: ${player.cash:.2f}   Won: ${total_won:.2f}   Lost: ${total_lost:.2f}",
                      fg=(200, 200, 200))
        y += 2

        # Check if player has cheating tools
        has_marked = any("cheat" in getattr(i, "tool_tags", []) for i in player.inventory)

        # Options
        console.print(4, y,     "[1] Call — match the bet (${:.2f})".format(ante), fg=(200, 200, 200))
        console.print(4, y + 1, "[2] Raise — double the pot (${:.2f})".format(ante * 2), fg=(200, 200, 200))
        console.print(4, y + 2, "[3] Fold — lose ante, keep the rest", fg=(200, 200, 200))
        console.print(4, y + 3, "[4] Bluff — Charisma check, win big or get caught", fg=(200, 200, 200))
        if has_marked:
            console.print(4, y + 4, "[5] Cheat — use marked cards/loaded dice", fg=(255, 100, 100))
        console.print(4, y + 5, "[ESC] Leave the table", fg=(140, 140, 140))

        # Message log
        log_y = 38
        for i, msg in enumerate(messages[-6:]):
            console.print(4, log_y + i, msg[:110], fg=(180, 180, 160))

        ctx.present(console)

        # ── Input ─────────────────────────────────────────────────
        action = None
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                raise SystemExit()
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                K = tcod.event.KeySym
                if sym == K.ESCAPE:
                    action = "leave"
                elif sym in (K.N1, K.KP_1):
                    action = "call"
                elif sym in (K.N2, K.KP_2):
                    action = "raise"
                elif sym in (K.N3, K.KP_3):
                    action = "fold"
                elif sym in (K.N4, K.KP_4):
                    action = "bluff"
                elif sym in (K.N5, K.KP_5) and has_marked:
                    action = "cheat"
                break

        if action == "leave":
            break

        if action == "fold":
            add_msg(f"Round {round_num}: You fold. Lost ${ante:.2f} ante.")
            total_lost += ante
            continue

        if action == "call":
            # Simple comparison — highest hand wins
            if player_hand > best_opp_hand:
                winnings = pot
                player.cash += winnings
                total_won += winnings - ante
                add_msg(f"Round {round_num}: {HAND_NAMES[player_hand]} beats "
                        f"{best_opp_player['name']}'s {HAND_NAMES[best_opp_hand]}! "
                        f"You win ${winnings:.2f}!")
            elif player_hand == best_opp_hand:
                # Tie — split pot
                split = pot / 2
                player.cash += split
                add_msg(f"Round {round_num}: Tie! Split the pot — ${split:.2f} back.")
            else:
                total_lost += ante
                add_msg(f"Round {round_num}: {best_opp_player['name']} shows "
                        f"{HAND_NAMES[best_opp_hand]}. Beats your {HAND_NAMES[player_hand]}. "
                        f"You lose ${ante:.2f}.")

        elif action == "raise":
            raise_amt = ante * 2
            if player.cash < raise_amt:
                add_msg("Not enough cash to raise.")
                player.cash += ante  # refund ante
                continue
            player.cash -= raise_amt
            pot += raise_amt

            # Opponents may fold based on hand strength
            remaining = []
            for o, h in opp_hands:
                fold_chance = 0.3 + (0.1 * (4 - h))  # weak hands fold more
                if rng.random() < fold_chance:
                    add_msg(f"  {o['name']} folds.")
                else:
                    pot += ante  # they call
                    remaining.append((o, h))

            if not remaining:
                player.cash += pot
                total_won += pot - ante - raise_amt
                add_msg(f"Round {round_num}: Everyone folds! You take ${pot:.2f}!")
            else:
                best_r = max(remaining, key=lambda x: x[1])
                if player_hand > best_r[1]:
                    player.cash += pot
                    total_won += pot - ante - raise_amt
                    add_msg(f"Round {round_num}: Your {HAND_NAMES[player_hand]} wins! "
                            f"${pot:.2f} pot!")
                else:
                    total_lost += ante + raise_amt
                    add_msg(f"Round {round_num}: {best_r[0]['name']} shows "
                            f"{HAND_NAMES[best_r[1]]}. You lose ${ante + raise_amt:.2f}.")

        elif action == "bluff":
            # Charisma check vs opponents' read
            bluff_roll = rng.randint(1, 20) + cha // 3
            # Best opponent tries to read the bluff
            read_diff = 10 + best_opp_player["aggression"] * 5
            if bluff_roll >= read_diff:
                # Bluff succeeds — everyone folds
                player.cash += pot
                total_won += pot - ante
                bluff_msgs = [
                    f"Round {round_num}: You stare {best_opp_player['name']} down. "
                    f"They fold. ${pot:.2f} yours.",
                    f"Round {round_num}: Stone cold bluff. Nobody calls. ${pot:.2f}.",
                    f"Round {round_num}: You push your chips in. Silence. They fold. ${pot:.2f}.",
                ]
                add_msg(rng.choice(bluff_msgs))
                player.gain_skill_xp("trading", 3.0)
            else:
                # Caught bluffing
                penalty = ante * 2
                total_lost += ante + penalty
                add_msg(f"Round {round_num}: {best_opp_player['name']} calls your bluff! "
                        f"\"I knew it.\" You lose ${ante + penalty:.2f}.")
                # Reputation hit if high stakes
                if ante >= 5:
                    add_msg(f"  Word gets around that you're a cheat.")

        elif action == "cheat":
            # Use marked cards / loaded dice to guarantee a win
            # Detection chance: opponents roll vs player's Charisma + Agility
            detect_roll = rng.randint(1, 20) + best_opp_player["aggression"] * 5
            stealth_roll = rng.randint(1, 20) + cha // 3 + player.attributes.get("agility", 10) // 4

            if stealth_roll > detect_roll:
                # Cheating succeeds — auto-win with a "natural" looking hand
                player_hand = rng.randint(5, 8)  # flush to four of a kind
                player.cash += pot
                total_won += pot - ante
                cheat_msgs = [
                    f"Round {round_num}: You palm a card under the table. "
                    f"Show {HAND_NAMES[player_hand]}. ${pot:.2f} yours.",
                    f"Round {round_num}: A little sleight of hand. "
                    f"{HAND_NAMES[player_hand]}. Nobody notices. ${pot:.2f}.",
                    f"Round {round_num}: You switch the deck. "
                    f"Your hand improves dramatically. ${pot:.2f}.",
                ]
                add_msg(rng.choice(cheat_msgs))
            else:
                # CAUGHT CHEATING — this is very bad
                penalty = pot * 2
                total_lost += ante + penalty
                player.cash = max(0, player.cash - penalty)
                caught_msgs = [
                    f"Round {round_num}: {best_opp_player['name']} grabs your wrist. "
                    f"\"What's that in your sleeve?\" The table goes silent.",
                    f"Round {round_num}: \"CHEAT!\" {best_opp_player['name']} flips the table. "
                    f"Cards scatter. Everyone stares at you.",
                    f"Round {round_num}: {best_opp_player['name']} catches the marked card. "
                    f"\"You son of a bitch.\" Hands go to guns.",
                ]
                add_msg(rng.choice(caught_msgs))
                add_msg(f"  You lose ${penalty:.2f}. Your reputation takes a hit.")

                # Reputation and legal consequences
                lmap = engine.current_local
                region = lmap._region_name if lmap else ""
                engine.reputation.adjust(region, -25)
                engine._record_gossip(f"Caught cheating at cards", -0.7)

                # 30% chance someone goes hostile
                if rng.random() < 0.3:
                    add_msg(f"  {best_opp_player['name']} goes for a weapon!")
                    # Make a nearby NPC hostile
                    for n in engine._tile_npcs():
                        if n.alive and n.combat_state == "neutral":
                            n.combat_state = "hostile"
                            break

        # (custom action removed — only available in player-as-house mode)

        # Advance time (30 min per round)
        engine.time.advance_seconds(30 * 60)

        # Stakes may increase
        if round_num % 3 == 0:
            old_ante = ante
            ante = min(ante * 1.5, player.cash * 0.25)
            ante = max(1.0, round(ante, 2))
            if ante > old_ante:
                add_msg(f"Stakes raised. Ante is now ${ante:.2f}.")

    # Session summary
    net = total_won - total_lost
    if net > 0:
        engine.add_message(
            f"You leave the table up ${net:.2f} after {round_num} rounds.", "normal")
        if net > 20:
            engine.player.gain_skill_xp("trading", 5.0)
    elif net < 0:
        engine.add_message(
            f"You leave the table down ${abs(net):.2f} after {round_num} rounds.", "normal")
    else:
        engine.add_message(f"You break even after {round_num} rounds.", "normal")


# ============================================================================
#  BLACKJACK (Twenty-One)
# ============================================================================

def _draw_card(rng) -> int:
    """Draw a card value (1-11, face cards = 10, ace = 11)."""
    card = rng.randint(1, 13)
    if card > 10:
        return 10
    if card == 1:
        return 11  # ace high (simplified)
    return card


def _hand_total(cards) -> int:
    total = sum(cards)
    # Soft ace: if over 21, convert an 11 to 1
    aces = cards.count(11)
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


def _card_name(val) -> str:
    names = {1: "Ace", 11: "Ace", 2: "2", 3: "3", 4: "4", 5: "5",
             6: "6", 7: "7", 8: "8", 9: "9", 10: "10"}
    return names.get(val, str(val))


def enter_blackjack(engine: "Engine", console, ctx) -> None:
    """Blackjack / Twenty-One gambling session."""
    player = engine.player
    rng = random.Random()
    bet = max(1.0, min(5.0, player.cash * 0.1))
    total_net = 0.0
    round_num = 0
    messages = []

    def add_msg(text):
        messages.append(text)
        if len(messages) > 15:
            messages.pop(0)

    add_msg(f"Twenty-One. Bet ${bet:.2f} per hand. You have ${player.cash:.2f}.")

    while True:
        round_num += 1
        if player.cash < bet:
            add_msg("Can't cover the bet. Game over.")
            break

        player.cash -= bet
        p_cards = [_draw_card(rng), _draw_card(rng)]
        d_cards = [_draw_card(rng), _draw_card(rng)]
        p_total = _hand_total(p_cards)
        d_showing = d_cards[0]

        # Render
        console.clear()
        console.draw_rect(0, 0, 120, 1, ord(" "), fg=(255, 255, 255), bg=(30, 50, 30))
        console.print(2, 0, f"TWENTY-ONE  —  Round {round_num}  —  Bet: ${bet:.2f}",
                      fg=(255, 255, 200), bg=(30, 50, 30))

        # Player loop — hit or stand
        standing = False
        busted = False
        while not standing and not busted:
            p_total = _hand_total(p_cards)

            console.clear()
            console.draw_rect(0, 0, 120, 1, ord(" "), fg=(255, 255, 255), bg=(30, 50, 30))
            console.print(2, 0, f"TWENTY-ONE  —  Round {round_num}  —  Bet: ${bet:.2f}  —  Cash: ${player.cash:.2f}",
                          fg=(255, 255, 200), bg=(30, 50, 30))

            y = 3
            console.print(4, y, f"Dealer shows: [{_card_name(d_showing)}] [?]", fg=(200, 200, 200))
            y += 2
            cards_str = " ".join(f"[{_card_name(c)}]" for c in p_cards)
            console.print(4, y, f"Your hand: {cards_str}  = {p_total}", fg=(255, 255, 255))
            y += 1
            if p_total == 21:
                console.print(4, y, "BLACKJACK!", fg=(255, 255, 100))
            elif p_total > 21:
                console.print(4, y, "BUST!", fg=(255, 80, 80))
            y += 2
            console.print(4, y,     "[1] Hit  [2] Stand  [ESC] Leave", fg=(150, 150, 150))

            log_y = 38
            for i, msg in enumerate(messages[-6:]):
                console.print(4, log_y + i, msg[:110], fg=(180, 180, 160))

            ctx.present(console)

            if p_total >= 21:
                busted = p_total > 21
                standing = p_total == 21
                if busted or standing:
                    import time; time.sleep(0.8)
                break

            for event in tcod.event.wait():
                if isinstance(event, tcod.event.Quit):
                    raise SystemExit()
                if isinstance(event, tcod.event.KeyDown):
                    sym = event.sym
                    K = tcod.event.KeySym
                    if sym == K.ESCAPE:
                        return
                    if sym in (K.N1, K.KP_1):
                        p_cards.append(_draw_card(rng))
                    elif sym in (K.N2, K.KP_2):
                        standing = True
                    break

        if busted:
            total_net -= bet
            add_msg(f"Round {round_num}: Bust with {p_total}. Lost ${bet:.2f}.")
            engine.time.advance_seconds(5 * 60)
            continue

        # Dealer plays (hits on 16 or less)
        d_total = _hand_total(d_cards)
        while d_total < 17:
            d_cards.append(_draw_card(rng))
            d_total = _hand_total(d_cards)

        # Resolve
        if d_total > 21:
            winnings = bet * 2
            player.cash += winnings
            total_net += bet
            add_msg(f"Round {round_num}: Dealer busts with {d_total}! You win ${winnings:.2f}!")
        elif p_total > d_total:
            winnings = bet * 2
            player.cash += winnings
            total_net += bet
            add_msg(f"Round {round_num}: {p_total} beats dealer's {d_total}. Win ${winnings:.2f}!")
        elif p_total == d_total:
            player.cash += bet  # push
            add_msg(f"Round {round_num}: Push. {p_total} ties dealer. Bet returned.")
        else:
            total_net -= bet
            add_msg(f"Round {round_num}: Dealer's {d_total} beats your {p_total}. Lost ${bet:.2f}.")

        engine.time.advance_seconds(5 * 60)

    net_str = f"+${total_net:.2f}" if total_net >= 0 else f"-${abs(total_net):.2f}"
    engine.add_message(f"Left the Twenty-One table. Net: {net_str}.", "normal")


# ============================================================================
#  FARO (most popular card game in 1840s-1880s saloons)
# ============================================================================

def enter_faro(engine: "Engine", console, ctx) -> None:
    """Faro bank — bet on which card turns up. The iconic Gold Rush game.
    Simple: pick a card rank (1-13), dealer flips two cards per turn.
    First card = banker wins, second card = player wins."""
    player = engine.player
    rng = random.Random()
    bet = max(1.0, min(5.0, player.cash * 0.1))
    total_net = 0.0
    round_num = 0
    messages = []

    rank_names = ["", "Ace", "2", "3", "4", "5", "6", "7",
                  "8", "9", "10", "Jack", "Queen", "King"]

    def add_msg(text):
        messages.append(text)
        if len(messages) > 15:
            messages.pop(0)

    add_msg(f"Faro bank. Bet ${bet:.2f} per turn. Pick a card rank.")
    add_msg(f"Dealer flips two: first = bank wins, second = you win.")

    while True:
        round_num += 1
        if player.cash < bet:
            add_msg("Can't cover the bet. Game over.")
            break

        # Render — pick a rank
        console.clear()
        console.draw_rect(0, 0, 120, 1, ord(" "), fg=(255, 255, 255), bg=(50, 30, 30))
        console.print(2, 0, f"FARO  —  Round {round_num}  —  Bet: ${bet:.2f}  —  Cash: ${player.cash:.2f}",
                      fg=(255, 255, 200), bg=(50, 30, 30))

        y = 3
        console.print(4, y, "Pick your card rank:", fg=(255, 255, 255))
        y += 1
        for i in range(1, 14):
            col = 4 + ((i - 1) % 7) * 10
            row = y + ((i - 1) // 7)
            console.print(col, row, f"[{i:2d}] {rank_names[i]}", fg=(200, 200, 200))
        y += 3
        console.print(4, y, "[ESC] Leave the table", fg=(140, 140, 140))

        log_y = 38
        for i, msg in enumerate(messages[-6:]):
            console.print(4, log_y + i, msg[:110], fg=(180, 180, 160))

        ctx.present(console)

        # Input — pick rank
        chosen = None
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                raise SystemExit()
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                K = tcod.event.KeySym
                if sym == K.ESCAPE:
                    net_str = f"+${total_net:.2f}" if total_net >= 0 else f"-${abs(total_net):.2f}"
                    engine.add_message(f"Left the Faro table. Net: {net_str}.", "normal")
                    return
                # Number keys 1-9
                num_map = {K.N1: 1, K.N2: 2, K.N3: 3, K.N4: 4, K.N5: 5,
                           K.N6: 6, K.N7: 7, K.N8: 8, K.N9: 9,
                           K.KP_1: 1, K.KP_2: 2, K.KP_3: 3, K.KP_4: 4, K.KP_5: 5,
                           K.KP_6: 6, K.KP_7: 7, K.KP_8: 8, K.KP_9: 9,
                           K.N0: 10, K.KP_0: 10}
                chosen = num_map.get(sym)
                # Also handle typing 10-13 via 0,j,q,k
                if sym == K.j: chosen = 11
                if sym == K.q: chosen = 12
                if sym == K.k: chosen = 13
                break

        if chosen is None or chosen < 1 or chosen > 13:
            continue

        player.cash -= bet

        # Dealer flips two cards
        banker_card = rng.randint(1, 13)
        player_card = rng.randint(1, 13)

        add_msg(f"You bet on {rank_names[chosen]}. "
                f"Dealer flips: {rank_names[banker_card]} (bank), "
                f"{rank_names[player_card]} (player).")

        if player_card == chosen:
            # Player wins
            winnings = bet * 2
            player.cash += winnings
            total_net += bet
            add_msg(f"  Your card comes up! Win ${winnings:.2f}!")
        elif banker_card == chosen:
            # Bank wins
            total_net -= bet
            add_msg(f"  Bank takes it. Lost ${bet:.2f}.")
        else:
            # Neither — push (get bet back)
            player.cash += bet
            add_msg(f"  Neither matches. Bet returned.")

        engine.time.advance_seconds(3 * 60)


# ============================================================================
#  PLAYER AS HOUSE — run a gambling table
# ============================================================================

# ── LLM-powered gambling actions ──────────────────────────────────────────

def _llm_cheat_action(engine, action_text: str, customers: list,
                      house_bank: float) -> dict:
    """Ask LLM to resolve a freeform cheating action at the gambling table.
    Returns dict with: success (bool), win_modifier (float 0-1),
    suspicion_increase (float 0-3), message (str), caught (bool)."""
    ctx = {
        "situation": "Player is running a card table as the house dealer.",
        "action": action_text,
        "player_charisma": engine.player.attributes.get("charisma", 10),
        "player_agility": engine.player.attributes.get("agility", 10),
        "customers": [{"name": c["name"], "cash": c["cash"],
                       "mood": c["mood"], "suspicion": c["suspicion"]}
                      for c in customers],
        "house_bank": house_bank,
        "instructions": (
            "The player is trying to cheat at cards. Evaluate whether this action "
            "is mechanically possible, how much it shifts the odds in the house's "
            "favor (win_modifier: 0.0 = no effect, 1.0 = guaranteed win), "
            "how suspicious it looks (suspicion_increase: 0 = undetectable, "
            "3 = obvious), and whether anyone catches them (caught: true/false). "
            "Return JSON with fields: success, win_modifier, suspicion_increase, "
            "caught, message (short narrative of what happens)."
        ),
    }
    if not engine.llm or not engine.llm.enabled:
        # Offline fallback — simple Charisma check
        import random
        cha = engine.player.attributes.get("charisma", 10)
        roll = random.randint(1, 20) + cha // 3
        success = roll >= 12
        return {
            "success": success,
            "win_modifier": 0.4 if success else 0.0,
            "suspicion_increase": 0.5 if success else 2.0,
            "caught": not success and roll < 8,
            "message": f"You try to {action_text.lower()}. "
                       + ("It works." if success else "It doesn't go as planned."),
        }

    import json
    try:
        prompt = (
            f"GAMBLING TABLE SITUATION:\n"
            f"Player action: \"{action_text}\"\n"
            f"Player Charisma: {ctx['player_charisma']}, Agility: {ctx['player_agility']}\n"
            f"Customers: {json.dumps(ctx['customers'])}\n"
            f"House bank: ${house_bank:.2f}\n\n"
            f"{ctx['instructions']}"
        )
        raw = engine.llm._chat(
            [{"role": "system", "content": "You are the game master for a Gold Rush era card game. "
              "Return JSON only."},
             {"role": "user", "content": prompt}],
            temperature=0.4, max_tokens=300, json_mode=True,
        )
        data = json.loads(raw)
        return {
            "success": bool(data.get("success", False)),
            "win_modifier": float(data.get("win_modifier", 0.0)),
            "suspicion_increase": float(data.get("suspicion_increase", 1.0)),
            "caught": bool(data.get("caught", False)),
            "message": str(data.get("message", "Something happens.")),
        }
    except Exception:
        return {
            "success": False, "win_modifier": 0.0,
            "suspicion_increase": 1.0, "caught": False,
            "message": "You fumble the attempt.",
        }


def _llm_talk_down(engine, player_said: str, accuser_name: str,
                   suspicion: int) -> dict:
    """Ask LLM to resolve a talk-down attempt with an angry gambler.
    Returns dict with: success (bool), message (str), mood (str)."""
    if not engine.llm or not engine.llm.enabled:
        import random
        cha = engine.player.attributes.get("charisma", 10)
        roll = random.randint(1, 20) + cha // 3
        success = roll >= 13
        return {
            "success": success,
            "message": f"You say: \"{player_said}\" "
                       + (f"{accuser_name} grumbles but sits back down."
                          if success else f"{accuser_name} isn't buying it."),
            "mood": "neutral" if success else "angry",
        }

    import json
    try:
        prompt = (
            f"CONFRONTATION AT CARD TABLE:\n"
            f"{accuser_name} has accused the player of cheating.\n"
            f"Suspicion level: {suspicion}/5\n"
            f"Player says: \"{player_said}\"\n"
            f"Player Charisma: {engine.player.attributes.get('charisma', 10)}\n\n"
            f"Determine if the player's words defuse the situation. "
            f"Return JSON: success (bool), message (narrative of what happens, "
            f"include both what player says and how the accuser reacts, "
            f"period-appropriate 1849 dialogue), mood (neutral/angry/violent)."
        )
        raw = engine.llm._chat(
            [{"role": "system", "content": "You are the game master for a Gold Rush era game. "
              "Write vivid, period-appropriate dialogue. Return JSON only."},
             {"role": "user", "content": prompt}],
            temperature=0.6, max_tokens=300, json_mode=True,
        )
        data = json.loads(raw)
        return {
            "success": bool(data.get("success", False)),
            "message": str(data.get("message", "")),
            "mood": str(data.get("mood", "angry")),
        }
    except Exception:
        return {"success": False, "message": f"{accuser_name} doesn't believe you.",
                "mood": "angry"}


_CUSTOMER_NAMES = [
    "Dusty Pete", "One-Eyed Jack", "Whiskey Tom", "Big Frank", "Slim",
    "Copper John", "Dutch", "Salty", "Red", "Missouri Bill",
    "Lucky", "Digger", "Bones", "Tex", "The Kid",
    "Old Timer", "Preach", "Doc", "Fancy Dan", "Shorty",
]


def enter_house_mode(engine: "Engine", console, ctx) -> None:
    """Player runs a gambling table. NPCs come to play, house takes a cut.
    Player can cheat, but if caught there are consequences.
    If player can't pay a winner, things get ugly."""
    player = engine.player
    rng = random.Random()

    # Need a card table or faro layout
    has_table = any("furniture" in getattr(i, "tool_tags", [])
                    for i in player.inventory)
    has_cards = any("gamble" in getattr(i, "tool_tags", [])
                    for i in player.inventory)
    has_cheat_tools = any("cheat" in getattr(i, "tool_tags", [])
                          for i in player.inventory)

    if not has_table:
        engine.add_message("You need a card table to run a gambling operation.", "advisory")
        return
    if not has_cards:
        engine.add_message("You need playing cards or a faro layout.", "advisory")
        return

    cha = player.attributes.get("charisma", 10)
    intel = player.attributes.get("intelligence", 10)
    house_bank = min(player.cash, 100.0)  # amount player puts up as bank
    if house_bank < 5:
        engine.add_message("You need at least $5 to bank a game.", "advisory")
        return

    messages = []
    total_profit = 0.0
    round_num = 0
    cheat_suspicion = 0  # builds up if player cheats repeatedly

    # Generate customers for the session
    n_customers = rng.randint(3, 6)
    customers = []
    for _ in range(n_customers):
        name = rng.choice(_CUSTOMER_NAMES)
        cash = rng.uniform(5, 50)
        customers.append({"name": name, "cash": cash, "mood": "neutral",
                          "suspicion": 0, "rounds_played": 0})

    def add_msg(text):
        messages.append(text)
        if len(messages) > 20:
            messages.pop(0)

    add_msg(f"You set up the table. {n_customers} men sit down.")
    add_msg(f"House bank: ${house_bank:.2f}. Your cut: 10% of every pot.")

    while True:
        round_num += 1

        # Customers may leave if mood is bad
        customers = [c for c in customers if c["mood"] != "left"]
        if not customers:
            add_msg("Everyone's left the table.")
            break

        # ── Render ────────────────────────────────────────────────
        console.clear()
        console.draw_rect(0, 0, 120, 1, ord(" "), fg=(255, 255, 255), bg=(50, 40, 20))
        console.print(2, 0, f"THE HOUSE  —  Round {round_num}  —  Bank: ${house_bank:.2f}  —  Cash: ${player.cash:.2f}",
                      fg=(255, 220, 140), bg=(50, 40, 20))

        y = 3
        console.print(4, y, "── Customers ──", fg=(180, 160, 120))
        y += 1
        for c in customers:
            mood_color = {"neutral": (200, 200, 200), "happy": (100, 255, 100),
                          "angry": (255, 100, 100), "suspicious": (255, 200, 100)
                          }.get(c["mood"], (180, 180, 180))
            console.print(4, y, f"  {c['name']:15s}  ${c['cash']:6.2f}  [{c['mood']}]",
                          fg=mood_color)
            y += 1

        y += 1
        console.print(4, y, f"Profit so far: ${total_profit:.2f}", fg=(200, 200, 200))
        if cheat_suspicion > 0:
            susp_color = (255, 200, 100) if cheat_suspicion < 3 else (255, 80, 80)
            console.print(4, y + 1, f"Suspicion level: {'*' * cheat_suspicion}",
                          fg=susp_color)
        y += 3

        console.print(4, y,     "[1] Deal fair — take house cut (10%)", fg=(200, 200, 200))
        console.print(4, y + 1, "[2] Rig the game — tilt odds to house (Charisma check)", fg=(200, 200, 200))
        if has_cheat_tools:
            console.print(4, y + 2, "[3] Cheat — use marked cards (big profit, risky)",
                          fg=(255, 120, 120))
        console.print(4, y + 3, "[5] Sleight of hand — subtly tilt the odds (Agility check)", fg=(200, 180, 120))
        console.print(4, y + 4, "[4] Close up  [ESC] Walk away", fg=(140, 140, 140))

        log_y = 38
        for i, msg in enumerate(messages[-6:]):
            console.print(4, log_y + i, msg[:110], fg=(180, 180, 160))

        ctx.present(console)

        # Input
        action = None
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                raise SystemExit()
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                K = tcod.event.KeySym
                if sym == K.ESCAPE or sym in (K.N4, K.KP_4):
                    action = "close"
                elif sym in (K.N1, K.KP_1):
                    action = "fair"
                elif sym in (K.N2, K.KP_2):
                    action = "rig"
                elif sym in (K.N3, K.KP_3) and has_cheat_tools:
                    action = "cheat_house"
                elif sym in (K.N5, K.KP_5):
                    action = "custom"
                break

        if action == "close":
            break

        # ── Resolve round ─────────────────────────────────────────
        # Each customer plays a hand against the house
        round_pot = 0.0
        round_payout = 0.0

        for c in customers:
            if c["mood"] == "left":
                continue
            c["rounds_played"] += 1
            bet = min(c["cash"], rng.uniform(1, 8))
            c["cash"] -= bet
            round_pot += bet

            # Customer win chance: normally ~45% (house edge)
            win_chance = 0.45
            if action == "fair":
                win_chance = 0.45
            elif action == "rig":
                # Rig: Charisma check to shift odds
                rig_roll = rng.randint(1, 20) + cha // 3
                if rig_roll >= 12:
                    win_chance = 0.35  # tilted
                else:
                    win_chance = 0.45  # failed to rig
                    cheat_suspicion += 0.3
            elif action == "cheat_house":
                win_chance = 0.20  # heavily rigged
                cheat_suspicion += 1
            elif action == "custom":
                # Hardcoded custom move — skill-based cheating
                agi = player.attributes.get("agility", 10)
                roll = rng.randint(1, 20) + agi // 3 + intel // 3
                if roll >= 14:
                    win_chance = 0.25
                    cheat_suspicion += 0.5
                else:
                    win_chance = 0.45
                    cheat_suspicion += 1.5

            if rng.random() < win_chance:
                # Customer wins — house must pay out
                payout = bet * 2
                round_payout += payout
                c["cash"] += payout
                c["mood"] = "happy"
                add_msg(f"  {c['name']} wins ${payout:.2f}!")
            else:
                c["mood"] = "neutral"

            # Suspicion check per customer
            if cheat_suspicion > 2 and rng.random() < cheat_suspicion * 0.1:
                c["suspicion"] += 1
                c["mood"] = "suspicious"

        # House profit = pot - payouts
        house_cut = round_pot * 0.10  # standard house cut
        if action == "fair":
            profit = round_pot - round_payout
        else:
            profit = round_pot - round_payout  # cheating just reduces payouts

        house_bank += profit
        total_profit += profit
        player.cash += house_cut  # house fee is separate from wins/losses

        if profit >= 0:
            add_msg(f"Round {round_num}: Pot ${round_pot:.2f}, "
                    f"payouts ${round_payout:.2f}. House profit: ${profit:.2f}")
        else:
            add_msg(f"Round {round_num}: Pot ${round_pot:.2f}, "
                    f"payouts ${round_payout:.2f}. House LOSS: ${abs(profit):.2f}")

        # ── Can't pay check ───────────────────────────────────────
        if house_bank < 0:
            deficit = abs(house_bank)
            if player.cash >= deficit:
                player.cash -= deficit
                house_bank = 0
                add_msg(f"Bank ran dry! You cover ${deficit:.2f} from your own pocket.")
            else:
                # CAN'T PAY — extremely bad
                add_msg(f"THE BANK IS EMPTY. You can't cover ${deficit:.2f}!")
                add_msg(f"The table erupts. Men are on their feet.")
                angry_msgs = [
                    "\"You owe me money, you crook!\"",
                    "\"Where's my winnings?!\"",
                    "\"This whole game was a scam!\"",
                ]
                for c in customers:
                    if c["mood"] == "happy":
                        add_msg(f"{c['name']} shouts: {rng.choice(angry_msgs)}")

                # Reputation destruction
                lmap = engine.current_local
                region = lmap._region_name if lmap else ""
                engine.reputation.adjust(region, -40)
                engine._record_gossip("Ran a crooked game and couldn't pay", -0.9)
                engine.legal.record_crime(
                    "fraud", engine.time.total_minutes // 1440,
                    engine.player.world_x, engine.player.world_y, region,
                    nearby_npcs=[])

                # Some customers may attack
                for n in engine._tile_npcs():
                    if n.alive and n.combat_state == "neutral" and rng.random() < 0.5:
                        n.combat_state = "hostile"

                add_msg("This is going to get ugly.")
                break

        # ── Suspicion consequences ────────────────────────────────
        if cheat_suspicion >= 4:
            suspicious_customers = [c for c in customers if c["suspicion"] >= 2]
            if suspicious_customers:
                accuser = rng.choice(suspicious_customers)
                add_msg(f"{accuser['name']} stands up: \"This game is rigged!\"")
                add_msg(f"\"I've been watching you. Those cards are marked!\"")
                # Charisma check to talk your way out
                talk_roll = rng.randint(1, 20) + cha // 3
                if talk_roll >= 14:
                    excuses = [
                        f"\"Rigged? You're just having a bad night, {accuser['name']}.\"",
                        f"\"I run an honest table. You can leave if you don't like it.\"",
                        f"\"Check the cards yourself.\" You gesture confidently. He sits down.",
                    ]
                    add_msg(rng.choice(excuses))
                    add_msg("He backs down. The table settles.")
                    cheat_suspicion = max(0, cheat_suspicion - 2)
                    accuser["mood"] = "neutral"
                    accuser["suspicion"] = 0
                elif talk_roll >= 10:
                    add_msg(f"{accuser['name']} grumbles but sits back down. "
                            f"He's watching you closely now.")
                    cheat_suspicion = max(0, cheat_suspicion - 1)
                    accuser["mood"] = "suspicious"
                else:
                    add_msg(f"{accuser['name']} flips the table! "
                            f"\"I KNEW it! This game is CROOKED!\"")
                    lmap = engine.current_local
                    region = lmap._region_name if lmap else ""
                    engine.reputation.adjust(region, -30)
                    engine._record_gossip("Caught running a crooked game", -0.8)
                    if rng.random() < 0.4:
                        add_msg(f"{accuser['name']} goes for a weapon!")
                        for n in engine._tile_npcs():
                            if n.alive and n.combat_state == "neutral":
                                n.combat_state = "hostile"
                                break
                    for c in customers:
                        c["mood"] = "left"
                    break

        # Customers with no money leave
        for c in customers:
            if c["cash"] <= 0.5:
                c["mood"] = "left"
                add_msg(f"  {c['name']} is tapped out. Leaves the table.")

        # New customer may join
        if rng.random() < 0.2 and len(customers) < 8:
            new_name = rng.choice([n for n in _CUSTOMER_NAMES
                                    if n not in [c["name"] for c in customers]])
            new_cash = rng.uniform(5, 40)
            customers.append({"name": new_name, "cash": new_cash,
                              "mood": "neutral", "suspicion": 0, "rounds_played": 0})
            add_msg(f"  {new_name} sits down with ${new_cash:.2f}.")

        engine.time.advance_seconds(20 * 60)

    # Session summary
    if total_profit > 0:
        engine.add_message(
            f"You close up the table. Profit: ${total_profit:.2f} over {round_num} rounds.",
            "normal")
        engine.player.gain_skill_xp("trading", 5.0)
    else:
        engine.add_message(
            f"You fold up the table. Loss: ${abs(total_profit):.2f}. "
            f"The house doesn't always win.", "normal")


# ============================================================================
#  GAME SELECTION MENU
# ============================================================================

def enter_gambling_mode(engine: "Engine", console, ctx) -> None:
    """Choose which game to play, or run the house."""
    from src.menus import pick_from_list

    has_table = any("furniture" in getattr(i, "tool_tags", [])
                    for i in engine.player.inventory)

    games = [
        "Poker — bluff, read, raise",
        "Twenty-One (Blackjack) — hit or stand",
        "Faro — pick a card, beat the bank",
    ]
    if has_table:
        games.append("Run the house — you're the dealer")
    idx = pick_from_list(console, ctx, "What's your game?", games)
    if idx is None:
        return
    if idx == 0:
        _enter_poker(engine, console, ctx)
    elif idx == 1:
        enter_blackjack(engine, console, ctx)
    elif idx == 2:
        enter_faro(engine, console, ctx)
    elif idx == 3:
        enter_house_mode(engine, console, ctx)
