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

        # Options
        console.print(4, y,     "[1] Call — match the bet (${:.2f})".format(ante), fg=(200, 200, 200))
        console.print(4, y + 1, "[2] Raise — double the pot (${:.2f})".format(ante * 2), fg=(200, 200, 200))
        console.print(4, y + 2, "[3] Fold — lose ante, keep the rest", fg=(200, 200, 200))
        console.print(4, y + 3, "[4] Bluff — Charisma check, win big or get caught", fg=(200, 200, 200))
        console.print(4, y + 4, "[ESC] Leave the table", fg=(140, 140, 140))

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
#  GAME SELECTION MENU
# ============================================================================

def enter_gambling_mode(engine: "Engine", console, ctx) -> None:
    """Choose which game to play."""
    from src.menus import pick_from_list
    games = [
        "Poker — bluff, read, raise",
        "Twenty-One (Blackjack) — hit or stand",
        "Faro — pick a card, beat the bank",
    ]
    idx = pick_from_list(console, ctx, "What's your game?", games)
    if idx is None:
        return
    if idx == 0:
        _enter_poker(engine, console, ctx)
    elif idx == 1:
        enter_blackjack(engine, console, ctx)
    elif idx == 2:
        enter_faro(engine, console, ctx)
