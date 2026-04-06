"""
Saloon entertainment mini-games: Arm Wrestling, Drinking Contest, Storytelling.
Period-appropriate diversions for a Gold Rush roguelike.
"""

import random
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine import Engine

from src.menus import pick_from_list


# ── Helpers ─────────────────────────────────────────────────────────────────

def _attr_mod(score: int) -> int:
    """D&D-style attribute modifier: (score - 10) // 2."""
    return (score - 10) // 2


def _d20() -> int:
    return random.randint(1, 20)


def _pick_opponent(engine, console, ctx) -> Optional[object]:
    """Let the player choose an NPC from the current tile to challenge."""
    npcs = [n for n in engine._tile_npcs() if n.alive and n.present]
    if not npcs:
        engine.add_message("There's nobody around to play with.", "advisory")
        return None
    names = [f"{n.name} (rel: {n.rel_label()})" for n in npcs]
    idx = pick_from_list(console, ctx, "Choose an opponent", names)
    if idx is None:
        return None
    return npcs[idx]


# ── Main menu ───────────────────────────────────────────────────────────────

def saloon_menu(engine, console, ctx) -> List[str]:
    """
    Main saloon entertainment menu.  Returns a list of message strings
    describing what happened.
    """
    options = [
        "Arm Wrestling  (STR, bet money)",
        "Drinking Contest  (CON, bet money)",
        "Tell a Story  (CHA + literacy)",
        "Leave",
    ]
    while True:
        idx = pick_from_list(console, ctx, "Saloon Entertainment", options)
        if idx is None or idx == 3:
            return []

        if idx == 0:
            npc = _pick_opponent(engine, console, ctx)
            if npc:
                return arm_wrestling(engine, console, ctx, npc)

        elif idx == 1:
            npc = _pick_opponent(engine, console, ctx)
            if npc:
                return drinking_contest(engine, console, ctx, npc)

        elif idx == 2:
            npcs = [n for n in engine._tile_npcs() if n.alive and n.present]
            if not npcs:
                engine.add_message(
                    "There's nobody around to listen.", "advisory")
            else:
                return storytelling(engine, console, ctx, npcs)


# ── Arm Wrestling ───────────────────────────────────────────────────────────

def arm_wrestling(engine, console, ctx, npc) -> List[str]:
    """
    Best-of-3 strength contest.  Player and NPC each wager money.
    Each round: d20 + STR modifier.  Winner takes the pot.
    """
    messages: List[str] = []

    # --- Determine bet ---
    bet_options = ["$1", "$2", "$5", "$10", "Nevermind"]
    bet_amounts = [1.0, 2.0, 5.0, 10.0]
    idx = pick_from_list(console, ctx, "How much to wager?", bet_options)
    if idx is None or idx == 4:
        return []
    bet = bet_amounts[idx]

    if engine.player.cash < bet:
        engine.add_message("You don't have enough money.", "advisory")
        return []

    # NPC might decline if relationship is very bad
    if npc.relationship < -50:
        msg = f"{npc.name} scowls and refuses to play with you."
        engine.add_message(msg, "advisory")
        messages.append(msg)
        return messages

    player_str = engine.player.attributes.get("strength", 10)
    npc_str = npc.attributes.get("strength", 10)
    p_mod = _attr_mod(player_str)
    n_mod = _attr_mod(npc_str)

    player_wins = 0
    npc_wins = 0

    msg = (f"You sit across from {npc.name} and clasp hands. "
           f"${bet:.0f} on the table.")
    engine.add_message(msg, "normal")
    messages.append(msg)

    for rd in range(1, 6):  # max 5 rounds to break ties, normally 3
        p_roll = _d20() + p_mod
        n_roll = _d20() + n_mod

        if p_roll > n_roll:
            player_wins += 1
            msg = (f"Round {rd}: You strain and push {npc.name}'s arm down! "
                   f"({p_roll} vs {n_roll})")
        elif n_roll > p_roll:
            npc_wins += 1
            msg = (f"Round {rd}: {npc.name} overpowers you! "
                   f"({p_roll} vs {n_roll})")
        else:
            msg = (f"Round {rd}: A dead heat — arms tremble but neither "
                   f"gives ground. ({p_roll} vs {n_roll})")

        engine.add_message(msg, "normal")
        messages.append(msg)

        if player_wins >= 2:
            break
        if npc_wins >= 2:
            break

    # Resolve outcome
    if player_wins > npc_wins:
        engine.player.cash += bet
        msg = (f"You win the arm wrestling match! "
               f"{npc.name} slides ${bet:.0f} across the table.")
        engine.add_message(msg, "advisory")
        npc.adjust_relationship(-2)  # sore loser, mild
    else:
        engine.player.cash -= bet
        msg = (f"{npc.name} wins! You grudgingly hand over ${bet:.0f}.")
        engine.add_message(msg, "advisory")
        npc.adjust_relationship(1)  # respects a good sport
    messages.append(msg)

    # Gain a little XP for physical exertion — survival skill
    engine.player.gain_skill_xp("survival", 2)

    engine.advance_time(10)
    return messages


# ── Drinking Contest ────────────────────────────────────────────────────────

def drinking_contest(engine, console, ctx, npc) -> List[str]:
    """
    CON-based endurance drinking.  Each round the difficulty rises.
    Player's thirst goes up (drinking!) but fatigue drops (alcohol).
    5% gut sickness risk per round.  Loser passes out.
    """
    messages: List[str] = []

    # --- Determine bet ---
    bet_options = ["$1", "$2", "$5", "$10", "Nevermind"]
    bet_amounts = [1.0, 2.0, 5.0, 10.0]
    idx = pick_from_list(console, ctx, "How much to wager?", bet_options)
    if idx is None or idx == 4:
        return []
    bet = bet_amounts[idx]

    if engine.player.cash < bet:
        engine.add_message("You don't have enough money.", "advisory")
        return []

    if npc.relationship < -50:
        msg = f"{npc.name} wants nothing to do with you."
        engine.add_message(msg, "advisory")
        messages.append(msg)
        return messages

    player_con = engine.player.attributes.get("constitution", 10)
    npc_con = npc.attributes.get("constitution", 10)
    p_mod = _attr_mod(player_con)
    n_mod = _attr_mod(npc_con)

    msg = (f"You and {npc.name} line up the whiskey glasses. "
           f"${bet:.0f} says you can't keep up.")
    engine.add_message(msg, "normal")
    messages.append(msg)

    difficulty = 10
    rd = 0
    player_standing = True
    npc_standing = True

    while player_standing and npc_standing:
        rd += 1
        p_roll = _d20() + p_mod
        n_roll = _d20() + n_mod

        msg = (f"Round {rd} (DC {difficulty}): "
               f"You roll {p_roll}, {npc.name} rolls {n_roll}.")
        engine.add_message(msg, "normal")
        messages.append(msg)

        if p_roll < difficulty:
            player_standing = False
        if n_roll < difficulty:
            npc_standing = False

        # Both fail same round — whoever rolled lower loses;
        # if tied, both pass out
        if not player_standing and not npc_standing:
            if p_roll > n_roll:
                # player recovers
                player_standing = True
                msg = (f"You both waver, but {npc.name} hits the floor first!")
            elif n_roll > p_roll:
                npc_standing = True
                msg = (f"You both waver, but you hit the floor first!")
            else:
                msg = "You both keel over at the same time. It's a draw!"
            engine.add_message(msg, "normal")
            messages.append(msg)

        # Survival effects per round
        # Drinking reduces thirst (good) but adds fatigue (bad)
        engine.player.survival.thirst = min(
            100.0, engine.player.survival.thirst + 5)
        engine.player.survival.fatigue = max(
            0.0, engine.player.survival.fatigue - 8)

        # Gut sickness risk — 5% per round
        if random.random() < 0.05:
            engine.player.survival.gut_sick_hours += 4.0
            msg = "Your stomach lurches ominously. That whiskey was rough."
            engine.add_message(msg, "critical")
            messages.append(msg)

        difficulty += 2

        # Safety valve — after 8 rounds somebody is going down
        if rd >= 8 and player_standing and npc_standing:
            msg = "After far too many drinks, the barkeep cuts you both off."
            engine.add_message(msg, "advisory")
            messages.append(msg)
            break

    # Resolve outcome
    if player_standing and not npc_standing:
        engine.player.cash += bet
        msg = (f"You win the drinking contest! {npc.name} slides off the "
               f"bench. You pocket ${bet:.0f}.")
        engine.add_message(msg, "advisory")
        npc.adjust_relationship(-1)
    elif npc_standing and not player_standing:
        engine.player.cash -= bet
        engine.player.survival.fatigue = 0.0
        msg = (f"You pass out. When you come to, your ${bet:.0f} is gone "
               f"and {npc.name} is grinning.")
        engine.add_message(msg, "advisory")
        npc.adjust_relationship(2)  # they had fun
    else:
        # Draw — money returned
        msg = "A draw! The bet is off. You both stagger away."
        engine.add_message(msg, "advisory")
        npc.adjust_relationship(3)  # bonding experience
    messages.append(msg)

    engine.player.gain_skill_xp("survival", 3)
    engine.advance_time(30)
    return messages


# ── Storytelling ────────────────────────────────────────────────────────────

def storytelling(engine, console, ctx, npcs) -> List[str]:
    """
    CHA + literacy performance.  Player tells a tale to nearby NPCs.
    Score determines audience reaction, relationship changes, and tips.
    """
    messages: List[str] = []

    cha = engine.player.attributes.get("charisma", 10)
    cha_mod = _attr_mod(cha)
    literacy = engine.player.skills.get("literacy", 0)

    # Topic selection for flavour
    topics = [
        "a harrowing tale of crossing the Sierra Nevada",
        "a yarn about a bear the size of a barn",
        "the legend of a lost Spanish gold mine",
        "a bawdy story about a mule and a preacher",
        "a ghost story set in an abandoned mine shaft",
        "the time you outran a band of road agents",
    ]
    topic = random.choice(topics)

    msg = f"You stand up and launch into {topic}."
    engine.add_message(msg, "normal")
    messages.append(msg)

    # Score: d20 + CHA mod + literacy skill level
    roll = _d20()
    score = roll + cha_mod + literacy
    msg = (f"Performance roll: {roll} + {cha_mod} (CHA) + {literacy} "
           f"(literacy) = {score}")
    engine.add_message(msg, "normal")
    messages.append(msg)

    # Determine audience reaction
    if score >= 20:
        # Outstanding performance — reputation boost
        tips = random.uniform(1.5, 2.0)
        tips = round(tips, 2)
        engine.player.cash += tips
        for n in npcs:
            n.adjust_relationship(3)
        msg = (f"The saloon erupts in cheers and applause! Someone buys you "
               f"a drink. Tips: ${tips:.2f}. Your reputation grows.")
        engine.add_message(msg, "advisory")
        messages.append(msg)
        # Bonus XP for a great performance
        engine.player.gain_skill_xp("trading", 8)
        engine.player.gain_skill_xp("literacy", 5)

    elif score >= 15:
        # Good performance
        tips = random.uniform(0.5, 1.5)
        tips = round(tips, 2)
        engine.player.cash += tips
        for n in npcs:
            n.adjust_relationship(3)
        msg = (f"The crowd listens with rapt attention. A few men nod "
               f"approvingly. Tips: ${tips:.2f}.")
        engine.add_message(msg, "advisory")
        messages.append(msg)
        engine.player.gain_skill_xp("trading", 5)
        engine.player.gain_skill_xp("literacy", 3)

    elif score >= 10:
        # Mediocre — polite silence
        tips = random.uniform(0.0, 0.25)
        tips = round(tips, 2)
        if tips > 0:
            engine.player.cash += tips
        msg = (f"The audience listens politely but nobody seems particularly "
               f"moved. Tips: ${tips:.2f}.")
        engine.add_message(msg, "normal")
        messages.append(msg)
        engine.player.gain_skill_xp("literacy", 2)

    else:
        # Embarrassing flop
        for n in npcs:
            n.adjust_relationship(-2)
        msg = (f"You lose the thread halfway through. Someone heckles you. "
               f"The crowd turns back to their drinks. Embarrassing.")
        engine.add_message(msg, "advisory")
        messages.append(msg)
        # Still learn from failure
        engine.player.gain_skill_xp("literacy", 1)

    engine.advance_time(15)
    return messages
