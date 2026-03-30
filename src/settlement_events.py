"""
src/settlement_events.py

Interactive settlement events — NPCs with motives, player choices,
and consequences. Every event involves real named NPCs from the
settlement and gives the player agency.

Called from engine daily tick. The event presents a situation and
the player picks how to respond. Outcomes depend on player skills,
attributes, relationships, and choices.
"""

import random
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine import Engine
    from src.npc import NPC

# ============================================================================
#  DATA STRUCTURES
# ============================================================================

@dataclass
class EventChoice:
    """A player choice in a settlement event."""
    label: str
    skill: str = ""             # skill checked (empty = auto-success)
    difficulty: int = 0         # DC for skill check
    attribute: str = ""         # attribute checked
    attr_min: int = 0           # minimum attribute value needed


@dataclass
class EventOutcome:
    """What happens after the player chooses."""
    message: str
    reputation_delta: float = 0.0
    cash_delta: float = 0.0
    health_delta: float = 0.0
    relationship_delta: float = 0.0   # applied to involved NPC
    item_id: str = ""                 # item given to player
    price_mult: float = 1.0
    price_duration: int = 0
    npc_hostile: bool = False         # NPC turns hostile
    npc_leaves: bool = False          # NPC leaves town
    xp_skill: str = ""               # skill XP gained
    xp_amount: float = 0.0


@dataclass
class SettlementEvent:
    """A complete interactive event."""
    title: str
    description: str
    npc_id: str = ""            # primary NPC involved
    npc_name: str = ""
    severity: str = "normal"
    choices: List[EventChoice] = field(default_factory=list)
    # Filled after player chooses:
    outcome: Optional[EventOutcome] = None


# ============================================================================
#  HELPERS
# ============================================================================

def _pick_npc(npcs: List["NPC"], exclude: set = None,
              occupation: str = "", alive_only: bool = True) -> Optional["NPC"]:
    """Pick a random NPC from the settlement, optionally filtered."""
    candidates = [n for n in npcs
                  if n.present and (not alive_only or n.alive)
                  and (not exclude or n.npc_id not in exclude)
                  and (not occupation or n.occupation == occupation)]
    return random.choice(candidates) if candidates else None


def _pick_any_npc(npcs: List["NPC"], exclude: set = None) -> Optional["NPC"]:
    """Pick any living, present NPC."""
    return _pick_npc(npcs, exclude)


def _skill_check(player, skill: str, difficulty: int, rng) -> bool:
    """d20 + skill/2 + attr/3 >= difficulty."""
    skill_val = player.skills.get(skill, 0)
    # Map skill to governing attribute
    attr_map = {"trading": "charisma", "law": "intelligence",
                "firstAid": "wisdom", "firearms": "agility",
                "survival": "wisdom", "tracking": "wisdom",
                "engineering": "intelligence", "geology": "intelligence",
                "placer": "wisdom", "chemistry": "intelligence",
                "fishing": "wisdom", "cooking": "wisdom",
                "trapping": "wisdom", "furriery": "agility"}
    attr_name = attr_map.get(skill, "intelligence")
    attr_val = player.attributes.get(attr_name, 10)
    roll = rng.randint(1, 20) + skill_val // 2 + attr_val // 3
    return roll >= difficulty


def _present_event(engine: "Engine", event: SettlementEvent,
                   rng) -> Optional[EventOutcome]:
    """Show event to player and get their choice. Returns outcome."""
    from src.menus import pick_from_list

    con = engine._console
    ctx = engine._ctx

    labels = [c.label for c in event.choices]
    title = f"{event.title}"
    if event.npc_name:
        title += f" [{event.npc_name}]"

    # Show description as message first
    engine.add_message(event.description, event.severity)

    idx = pick_from_list(con, ctx, title, labels)
    if idx is None:
        return None
    return idx


# ============================================================================
#  EVENT CHANCE
# ============================================================================

EVENT_CHANCE: Dict[str, float] = {
    "mining_camp_small":  0.30,
    "mining_camp_medium": 0.35,
    "boomtown":           0.45,
    "small_town":         0.25,
    "trading_post":       0.20,
    "city":               0.40,
}


# ============================================================================
#  EVENT DEFINITIONS
#  Each is a function: (engine, npcs, rng) -> Optional[SettlementEvent]
#  Returns None if preconditions not met (e.g. no suitable NPC).
# ============================================================================

# ── SALOON & SOCIAL ──────────────────────────────────────────────────────

def _evt_bar_fight(engine, npcs, rng):
    a = _pick_npc(npcs)
    b = _pick_npc(npcs, exclude={a.npc_id} if a else set())
    if not a or not b:
        return None
    motive = rng.choice(["a card game", "a spilled drink",
                         "an old grudge", "a woman's name",
                         "who owns the last bottle of whiskey"])
    evt = SettlementEvent(
        title="Bar Fight",
        description=(f"{a.name} and {b.name} are throwing punches in the "
                     f"saloon over {motive}. Chairs are flying. "
                     f"The barkeep is yelling for help."),
        npc_id=a.npc_id, npc_name=a.name,
        choices=[
            EventChoice("Break it up", skill="strength", difficulty=10,
                        attribute="strength", attr_min=8),
            EventChoice("Bet on a winner", skill="trading"),
            EventChoice("Stay out of it"),
            EventChoice("Join in (side with " + a.name + ")",
                        skill="firearms", difficulty=8),
        ])
    return evt

def _resolve_bar_fight(engine, evt, choice_idx, npcs, rng):
    a_npc = next((n for n in npcs if n.npc_id == evt.npc_id), None)
    b_npc = _pick_npc(npcs, exclude={evt.npc_id})
    p = engine.player

    if choice_idx == 0:  # Break it up
        if _skill_check(p, "survival", 10, rng):
            if a_npc: a_npc.adjust_relationship(5)
            if b_npc: b_npc.adjust_relationship(5)
            return EventOutcome(
                f"You step between them and shove them apart. "
                f"Both men cool down. The barkeep buys you a drink.",
                reputation_delta=3, relationship_delta=5,
                xp_skill="survival", xp_amount=2.0)
        else:
            return EventOutcome(
                f"You catch a wild fist to the jaw stepping in. "
                f"They stop fighting, at least — over you being hurt.",
                health_delta=-8, reputation_delta=1)
    elif choice_idx == 1:  # Bet
        if rng.random() < 0.5:
            return EventOutcome(
                f"You bet $2 on {evt.npc_name}. He wins — barely. "
                f"You collect $4.",
                cash_delta=4.0, reputation_delta=-1)
        else:
            return EventOutcome(
                f"You bet $2 on {evt.npc_name}. He goes down hard. "
                f"There goes your money.",
                cash_delta=-2.0)
    elif choice_idx == 2:  # Stay out
        return EventOutcome(
            f"You watch from the corner. {evt.npc_name} takes a "
            f"bottle to the head. The sheriff arrives and arrests both.",
            reputation_delta=0)
    else:  # Join in
        if a_npc: a_npc.adjust_relationship(10)
        if b_npc: b_npc.adjust_relationship(-15)
        if _skill_check(p, "firearms", 8, rng):
            return EventOutcome(
                f"You and {evt.npc_name} make short work of it. "
                f"He claps you on the back. \"I owe you one.\"",
                reputation_delta=-2, relationship_delta=10,
                health_delta=-3)
        else:
            return EventOutcome(
                f"You swing and miss. Someone hits you with a chair leg. "
                f"The sheriff arrests everyone including you.",
                health_delta=-15, reputation_delta=-5, cash_delta=-5.0)


def _evt_drunk_prospector(engine, npcs, rng):
    npc = _pick_npc(npcs)
    if not npc:
        return None
    claim = rng.choice(["a mother lode up in the hills",
                        "a creek running with gold dust",
                        "a nugget big as his fist",
                        "an abandoned Spanish mine full of silver",
                        "a seam of quartz thick with wire gold"])
    return SettlementEvent(
        title="Drunk's Tale",
        description=(f"{npc.name} is drunk and loud in the saloon, "
                     f"claiming to have found {claim}. "
                     f"Most people are ignoring him. He's looking for "
                     f"a partner — or money for another bottle."),
        npc_id=npc.npc_id, npc_name=npc.name,
        choices=[
            EventChoice("Buy him a drink and listen closely",
                        skill="trading", difficulty=8),
            EventChoice("Tell him to shut up"),
            EventChoice("Offer to be his partner"),
            EventChoice("Ignore him"),
        ])

def _resolve_drunk_prospector(engine, evt, choice_idx, npcs, rng):
    npc = next((n for n in npcs if n.npc_id == evt.npc_id), None)
    p = engine.player

    if choice_idx == 0:  # Buy drink and listen
        if _skill_check(p, "trading", 8, rng):
            return EventOutcome(
                f"A $0.50 whiskey loosens his tongue. Between the "
                f"slurring, you catch a real direction — northeast of "
                f"the big bend. Could be something. Could be nothing.",
                cash_delta=-0.50, relationship_delta=8,
                xp_skill="geology", xp_amount=3.0)
        else:
            return EventOutcome(
                f"He drinks your whiskey, tells three contradictory "
                f"stories, and passes out. Waste of fifty cents.",
                cash_delta=-0.50, relationship_delta=3)
    elif choice_idx == 1:  # Tell him to shut up
        if npc: npc.adjust_relationship(-10)
        return EventOutcome(
            f"\"Who the hell are you?\" He takes a swing but misses "
            f"by a mile. The barkeep throws him out.",
            reputation_delta=1, relationship_delta=-10)
    elif choice_idx == 2:  # Partner up
        if rng.random() < 0.3:
            return EventOutcome(
                f"He sobers up enough to shake on it. \"Tomorrow. "
                f"Dawn. Bring a pan.\" He might actually know something.",
                relationship_delta=15, xp_skill="placer", xp_amount=2.0)
        else:
            return EventOutcome(
                f"\"Partners? You and me?\" He laughs himself off the "
                f"stool. \"I don't need no partner.\" In the morning "
                f"he won't remember any of it.",
                relationship_delta=2)
    else:
        return EventOutcome(
            f"You mind your own business. He's asleep on the bar "
            f"within the hour.",
            reputation_delta=0)


def _evt_gambling_dispute(engine, npcs, rng):
    a = _pick_npc(npcs)
    b = _pick_npc(npcs, exclude={a.npc_id} if a else set())
    if not a or not b:
        return None
    amount = rng.choice([5, 10, 20, 50])
    return SettlementEvent(
        title="Gambling Dispute",
        description=(f"{a.name} accuses {b.name} of cheating at cards. "
                     f"${amount} on the table. {b.name} says it was a "
                     f"fair hand. Both men have their hands near their belts."),
        npc_id=a.npc_id, npc_name=a.name,
        choices=[
            EventChoice("Mediate — examine the cards", skill="trading",
                        difficulty=12),
            EventChoice("Back " + a.name + " — he was cheated"),
            EventChoice("Back " + b.name + " — it was fair"),
            EventChoice("Grab the pot and run"),
            EventChoice("Walk away"),
        ])

def _resolve_gambling_dispute(engine, evt, choice_idx, npcs, rng):
    a_npc = next((n for n in npcs if n.npc_id == evt.npc_id), None)
    others = [n for n in npcs if n.npc_id != evt.npc_id and n.present and n.alive]
    b_npc = others[0] if others else None
    p = engine.player

    if choice_idx == 0:  # Mediate
        if _skill_check(p, "trading", 12, rng):
            cheated = rng.random() < 0.5
            cheater = b_npc if cheated else a_npc
            name = cheater.name if cheater else "someone"
            return EventOutcome(
                f"You flip the cards. Marked — ace of spades has a "
                f"bent corner. {name} was cheating. The pot goes to "
                f"the honest player. Both men respect your judgment.",
                reputation_delta=5, xp_skill="trading", xp_amount=3.0)
        else:
            return EventOutcome(
                f"You look at the cards but can't spot anything wrong. "
                f"Both men tell you to mind your own business.",
                reputation_delta=-1)
    elif choice_idx == 1:  # Back A
        if a_npc: a_npc.adjust_relationship(10)
        if b_npc: b_npc.adjust_relationship(-15)
        return EventOutcome(
            f"You vouch for {evt.npc_name}. {b_npc.name if b_npc else 'The other man'} "
            f"throws down the cards and storms out.",
            reputation_delta=1, relationship_delta=10)
    elif choice_idx == 2:  # Back B
        if a_npc: a_npc.adjust_relationship(-15)
        if b_npc: b_npc.adjust_relationship(10)
        return EventOutcome(
            f"You say the hand looked fair to you. {evt.npc_name} "
            f"glares at you and leaves. Made an enemy today.",
            reputation_delta=1, relationship_delta=-15)
    elif choice_idx == 3:  # Grab pot
        return EventOutcome(
            f"You snatch the bills and bolt for the door. Behind you, "
            f"both men are too surprised to react. By the time they do, "
            f"you're gone. That'll come back around.",
            cash_delta=float(rng.choice([5, 10, 20])),
            reputation_delta=-15, relationship_delta=-20)
    else:
        return EventOutcome(
            f"You leave them to sort it out. A gunshot rings out "
            f"behind you. You don't look back.")


# ── LAW & ORDER ──────────────────────────────────────────────────────────

def _evt_wanted_man(engine, npcs, rng):
    npc = _pick_npc(npcs)
    if not npc:
        return None
    bounty = rng.choice([25, 50, 100, 200])
    crime = rng.choice(["stage robbery", "horse theft", "murder",
                        "claim jumping", "bank robbery"])
    return SettlementEvent(
        title="Wanted Man",
        description=(f"You spot {npc.name} on the street — and you're "
                     f"sure you saw that face on a wanted poster. "
                     f"${bounty} for {crime}. He hasn't noticed you yet."),
        npc_id=npc.npc_id, npc_name=npc.name, severity="advisory",
        choices=[
            EventChoice("Confront him directly", skill="firearms",
                        difficulty=12),
            EventChoice("Tell the sheriff"),
            EventChoice("Approach friendly, confirm identity",
                        skill="trading", difficulty=10),
            EventChoice("None of your business"),
        ])

def _resolve_wanted_man(engine, evt, choice_idx, npcs, rng):
    npc = next((n for n in npcs if n.npc_id == evt.npc_id), None)
    p = engine.player

    if choice_idx == 0:  # Confront
        if _skill_check(p, "firearms", 12, rng):
            return EventOutcome(
                f"\"Don't move.\" Your hand is on your gun. "
                f"{evt.npc_name} sees you mean it and puts his hands up. "
                f"The sheriff takes him. Bounty's yours.",
                cash_delta=float(rng.choice([25, 50, 100])),
                reputation_delta=10, npc_leaves=True,
                xp_skill="firearms", xp_amount=4.0)
        else:
            if npc: npc.go_hostile()
            return EventOutcome(
                f"{evt.npc_name} draws faster than you expected. "
                f"A bullet creases your arm before he bolts. "
                f"He's gone before the sheriff arrives.",
                health_delta=-15, npc_hostile=True)
    elif choice_idx == 1:  # Tell sheriff
        return EventOutcome(
            f"The sheriff and two deputies move in quietly. "
            f"{evt.npc_name} is arrested without a shot. "
            f"The sheriff promises you a share of the bounty.",
            cash_delta=float(rng.choice([10, 25, 50])),
            reputation_delta=5, npc_leaves=True)
    elif choice_idx == 2:  # Approach friendly
        if _skill_check(p, "trading", 10, rng):
            return EventOutcome(
                f"You buy him a drink, get him talking. He admits "
                f"he's running from the law. \"I didn't kill nobody. "
                f"It was self-defense.\" He offers you $20 to forget "
                f"his face.",
                cash_delta=20.0, relationship_delta=5,
                xp_skill="trading", xp_amount=3.0)
        else:
            return EventOutcome(
                f"He gets suspicious of your questions. \"You asking "
                f"a lot for a stranger.\" He leaves town that night.",
                npc_leaves=True)
    else:
        return EventOutcome(
            f"You keep walking. Not your problem. A week later "
            f"you hear the sheriff caught him anyway.")


def _evt_theft_accusation(engine, npcs, rng):
    victim = _pick_npc(npcs)
    accused = _pick_npc(npcs, exclude={victim.npc_id} if victim else set())
    if not victim or not accused:
        return None
    stolen = rng.choice(["gold dust", "a pocket watch", "a pistol",
                         "a sack of flour", "a mule"])
    return SettlementEvent(
        title="Theft Accusation",
        description=(f"{victim.name} is shouting that {accused.name} "
                     f"stole {stolen}. {accused.name} denies it. "
                     f"A crowd is gathering. Both look to you — "
                     f"you're known to be fair."),
        npc_id=accused.npc_id, npc_name=accused.name,
        choices=[
            EventChoice("Investigate — search " + accused.name + "'s tent",
                        skill="tracking", difficulty=10),
            EventChoice("Side with " + victim.name),
            EventChoice("Side with " + accused.name),
            EventChoice("Suggest they settle it themselves"),
        ])

def _resolve_theft_accusation(engine, evt, choice_idx, npcs, rng):
    accused = next((n for n in npcs if n.npc_id == evt.npc_id), None)
    others = [n for n in npcs if n.npc_id != evt.npc_id and n.present and n.alive]
    victim = others[0] if others else None
    p = engine.player

    if choice_idx == 0:  # Investigate
        if _skill_check(p, "tracking", 10, rng):
            guilty = rng.random() < 0.6
            if guilty:
                return EventOutcome(
                    f"You find the goods hidden under a blanket. "
                    f"{evt.npc_name} hangs his head. The crowd's "
                    f"verdict is swift — banishment.",
                    reputation_delta=8, npc_leaves=True,
                    xp_skill="tracking", xp_amount=3.0)
            else:
                return EventOutcome(
                    f"Nothing in {evt.npc_name}'s belongings. {victim.name if victim else 'The accuser'} "
                    f"looks embarrassed. Turns out a raccoon got into "
                    f"the supplies. False alarm.",
                    reputation_delta=5,
                    xp_skill="tracking", xp_amount=2.0)
        else:
            return EventOutcome(
                f"You look around but can't find anything conclusive. "
                f"Both men are disgusted. The dispute festers.",
                reputation_delta=-2)
    elif choice_idx == 1:  # Side with victim
        if accused: accused.adjust_relationship(-20)
        if victim: victim.adjust_relationship(10)
        return EventOutcome(
            f"You back {victim.name if victim else 'the accuser'}. "
            f"{evt.npc_name} is made to pay restitution. "
            f"He stares daggers at you as he counts out the coins.",
            reputation_delta=2, relationship_delta=-20)
    elif choice_idx == 2:  # Side with accused
        if accused: accused.adjust_relationship(10)
        if victim: victim.adjust_relationship(-15)
        return EventOutcome(
            f"You defend {evt.npc_name}. {victim.name if victim else 'The accuser'} "
            f"sputters and storms off. May have made the wrong call — "
            f"or saved an innocent man.",
            reputation_delta=1, relationship_delta=10)
    else:
        return EventOutcome(
            f"\"Sort it out yourselves.\" The argument continues "
            f"for another hour before the sheriff intervenes.")


# ── ECONOMY & TRADE ──────────────────────────────────────────────────────

def _evt_merchant_deal(engine, npcs, rng):
    npc = _pick_npc(npcs, occupation="Merchant")
    if not npc:
        npc = _pick_npc(npcs)
    if not npc:
        return None
    goods = rng.choice(["a crate of rifles", "fifty pounds of coffee",
                        "a barrel of whiskey", "mining tools",
                        "a wagonload of flour and salt"])
    return SettlementEvent(
        title="Merchant's Offer",
        description=(f"{npc.name} pulls you aside. \"I got {goods} coming "
                     f"in cheap — supplier owes me a favor. I need a "
                     f"partner with cash. You put in $30, I double "
                     f"your money when they sell.\""),
        npc_id=npc.npc_id, npc_name=npc.name,
        choices=[
            EventChoice("Invest $30"),
            EventChoice("Negotiate for a better split",
                        skill="trading", difficulty=12),
            EventChoice("Ask around about his reputation first",
                        skill="trading", difficulty=8),
            EventChoice("Decline — too risky"),
        ])

def _resolve_merchant_deal(engine, evt, choice_idx, npcs, rng):
    npc = next((n for n in npcs if n.npc_id == evt.npc_id), None)
    p = engine.player

    if choice_idx == 0:  # Invest
        if p.cash < 30:
            return EventOutcome("You don't have $30 to invest.", cash_delta=0)
        if rng.random() < 0.6:
            return EventOutcome(
                f"A week later, {evt.npc_name} finds you. \"Sold the lot.\" "
                f"He hands you $60. The man's word is good.",
                cash_delta=30.0, relationship_delta=10,
                reputation_delta=2)
        else:
            return EventOutcome(
                f"The shipment never arrives. Bandits, {evt.npc_name} says. "
                f"Your $30 is gone. Whether he's lying or not, "
                f"you'll never know.",
                cash_delta=-30.0, relationship_delta=-5)
    elif choice_idx == 1:  # Negotiate
        if _skill_check(p, "trading", 12, rng):
            if p.cash < 20:
                return EventOutcome("You don't have enough to invest.")
            if rng.random() < 0.65:
                return EventOutcome(
                    f"You talk him down to $20 for a 60% share. "
                    f"When the goods sell, you get $48 back. Smart dealing.",
                    cash_delta=28.0, reputation_delta=3,
                    xp_skill="trading", xp_amount=4.0)
            else:
                return EventOutcome(
                    f"Good deal — $20 in, but the shipment was robbed. "
                    f"At least you negotiated a smaller loss.",
                    cash_delta=-20.0, xp_skill="trading", xp_amount=2.0)
        else:
            return EventOutcome(
                f"\"Take it or leave it,\" {evt.npc_name} says. "
                f"He finds another investor.",
                relationship_delta=-3)
    elif choice_idx == 2:  # Ask around
        if _skill_check(p, "trading", 8, rng):
            honest = rng.random() < 0.5
            if honest:
                return EventOutcome(
                    f"People say {evt.npc_name} is straight as an arrow. "
                    f"Been trading here for years. Might be worth the risk.",
                    xp_skill="trading", xp_amount=2.0)
            else:
                return EventOutcome(
                    f"\"That one? He sold a man a mule that died the "
                    f"next day.\" Good thing you checked. You decline.",
                    reputation_delta=1, xp_skill="trading", xp_amount=2.0)
        else:
            return EventOutcome(
                f"Nobody wants to talk about {evt.npc_name}'s business. "
                f"That's either very good or very bad.")
    else:
        return EventOutcome(
            f"\"Your loss,\" {evt.npc_name} shrugs and moves on.",
            reputation_delta=0)


def _evt_supply_shortage(engine, npcs, rng):
    item = rng.choice(["flour", "salt", "ammunition", "coffee", "whiskey",
                        "lamp oil", "rope", "nails"])
    npc = _pick_npc(npcs)
    if not npc:
        return None
    return SettlementEvent(
        title="Supply Shortage",
        description=(f"The town is running low on {item}. Prices are climbing. "
                     f"{npc.name} asks if you have any to sell — "
                     f"\"I'll pay triple.\""),
        npc_id=npc.npc_id, npc_name=npc.name, severity="advisory",
        choices=[
            EventChoice("Sell some from your supplies"),
            EventChoice("Organize a supply run yourself"),
            EventChoice("Suggest rationing at a town meeting",
                        skill="trading", difficulty=10),
            EventChoice("Not your problem"),
        ])

def _resolve_supply_shortage(engine, evt, choice_idx, npcs, rng):
    npc = next((n for n in npcs if n.npc_id == evt.npc_id), None)
    p = engine.player

    if choice_idx == 0:  # Sell supplies
        # Check if player actually has trade goods
        sellable = [i for i in p.inventory if i.category in ("supply", "food", "misc")
                    and i.base_value > 0]
        if sellable:
            item = rng.choice(sellable)
            price = item.base_value * 3.0
            p.inventory.remove(item)
            return EventOutcome(
                f"You sell your {item.name} for ${price:.2f} — "
                f"triple the usual price. {evt.npc_name} is grateful.",
                cash_delta=price, reputation_delta=3, relationship_delta=8)
        else:
            return EventOutcome(
                f"You check your pack — nothing useful to sell. "
                f"{evt.npc_name} looks disappointed.")
    elif choice_idx == 1:  # Supply run
        return EventOutcome(
            f"You offer to ride to the next town for supplies. "
            f"Several people chip in — $15 travel fund. "
            f"If you bring goods back, you'll be a hero.",
            cash_delta=15.0, reputation_delta=5)
    elif choice_idx == 2:  # Town meeting
        if _skill_check(p, "trading", 10, rng):
            return EventOutcome(
                f"You call a meeting and propose fair rationing. "
                f"People grumble but agree. Order is maintained. "
                f"The sheriff nods approvingly.",
                reputation_delta=8, xp_skill="trading", xp_amount=3.0,
                price_mult=1.3, price_duration=7)
        else:
            return EventOutcome(
                f"Nobody wants to be told what they can and can't buy. "
                f"The meeting breaks up in arguments.",
                reputation_delta=-2)
    else:
        return EventOutcome(
            f"People manage. Prices stay high for a while.",
            price_mult=1.5, price_duration=10)


# ── HEALTH & DISEASE ─────────────────────────────────────────────────────

def _evt_sick_person(engine, npcs, rng):
    npc = _pick_npc(npcs)
    if not npc:
        return None
    illness = rng.choice(["cholera", "dysentery", "fever", "a bad wound",
                          "what looks like scurvy", "mining lung"])
    return SettlementEvent(
        title="Someone Sick",
        description=(f"{npc.name} is sick — {illness}. "
                     f"Lying in a tent, pale and shaking. "
                     f"The camp doctor is three towns away. "
                     f"Someone should do something."),
        npc_id=npc.npc_id, npc_name=npc.name,
        choices=[
            EventChoice("Try to help — you know some first aid",
                        skill="firstAid", difficulty=10),
            EventChoice("Bring them water and food"),
            EventChoice("Warn people to keep distance — it might spread"),
            EventChoice("Move along — you're no doctor"),
        ])

def _resolve_sick_person(engine, evt, choice_idx, npcs, rng):
    npc = next((n for n in npcs if n.npc_id == evt.npc_id), None)
    p = engine.player

    if choice_idx == 0:  # First aid
        if _skill_check(p, "firstAid", 10, rng):
            if npc: npc.adjust_relationship(20)
            return EventOutcome(
                f"You clean the wound, brew willow bark tea, keep them "
                f"hydrated. By morning {evt.npc_name} is sitting up. "
                f"\"You saved my life.\" Word spreads.",
                reputation_delta=8, relationship_delta=20,
                xp_skill="firstAid", xp_amount=5.0)
        else:
            return EventOutcome(
                f"You do what you can but it's beyond your skill. "
                f"{evt.npc_name} doesn't improve. At least you tried.",
                reputation_delta=2, health_delta=-3,
                xp_skill="firstAid", xp_amount=2.0)
    elif choice_idx == 1:  # Water and food
        if npc: npc.adjust_relationship(10)
        return EventOutcome(
            f"You bring a blanket, clean water, and what food you can "
            f"spare. Basic kindness. {evt.npc_name} squeezes your hand "
            f"in thanks.",
            reputation_delta=3, relationship_delta=10)
    elif choice_idx == 2:  # Warn people
        return EventOutcome(
            f"You post warnings and keep people away from the sick tent. "
            f"Nobody else gets ill. Practical, if not compassionate.",
            reputation_delta=2, health_delta=5)
    else:
        return EventOutcome(
            f"You pass by. Nobody else helps either. "
            f"{evt.npc_name} pulls through — barely — on their own.",
            reputation_delta=-1)


# ── MINING & CLAIMS ──────────────────────────────────────────────────────

def _evt_claim_dispute(engine, npcs, rng):
    a = _pick_npc(npcs)
    b = _pick_npc(npcs, exclude={a.npc_id} if a else set())
    if not a or not b:
        return None
    return SettlementEvent(
        title="Claim Dispute",
        description=(f"{a.name} and {b.name} both claim the same stretch "
                     f"of creek. {a.name} says he staked first. {b.name} "
                     f"says the stakes were down when he arrived. "
                     f"Both have tools on the ground."),
        npc_id=a.npc_id, npc_name=a.name,
        choices=[
            EventChoice("Help survey the claim boundaries",
                        skill="geology", difficulty=10),
            EventChoice("Suggest they split the claim"),
            EventChoice("Side with " + a.name + " — first stake wins"),
            EventChoice("Stay out of it"),
        ])

def _resolve_claim_dispute(engine, evt, choice_idx, npcs, rng):
    a_npc = next((n for n in npcs if n.npc_id == evt.npc_id), None)
    others = [n for n in npcs if n.npc_id != evt.npc_id and n.present and n.alive]
    b_npc = others[0] if others else None
    p = engine.player

    if choice_idx == 0:  # Survey
        if _skill_check(p, "geology", 10, rng):
            return EventOutcome(
                f"You pace off the boundaries, check the original stakes. "
                f"Clear as day — {evt.npc_name} was here first. The claim "
                f"is his. Both men accept your judgment.",
                reputation_delta=8, xp_skill="geology", xp_amount=4.0)
        else:
            return EventOutcome(
                f"The boundary markers are a mess. You can't sort it out. "
                f"They'll need to take it to the mining recorder.",
                reputation_delta=1, xp_skill="geology", xp_amount=1.0)
    elif choice_idx == 1:  # Split
        if a_npc: a_npc.adjust_relationship(3)
        if b_npc: b_npc.adjust_relationship(3)
        return EventOutcome(
            f"\"Half each. Fair is fair.\" Both men grumble but neither "
            f"wants to fight. They start digging on opposite ends.",
            reputation_delta=5, relationship_delta=3)
    elif choice_idx == 2:  # Side with A
        if a_npc: a_npc.adjust_relationship(10)
        if b_npc: b_npc.adjust_relationship(-15)
        return EventOutcome(
            f"You back {evt.npc_name}. {b_npc.name if b_npc else 'The other man'} "
            f"curses and kicks dirt but walks away. ",
            reputation_delta=2, relationship_delta=10)
    else:
        return EventOutcome(
            f"The argument escalates all afternoon. Eventually "
            f"the bigger man wins by intimidation. Not exactly justice.")


def _evt_gold_strike_rumor(engine, npcs, rng):
    npc = _pick_npc(npcs)
    if not npc:
        return None
    direction = rng.choice(["north", "south", "east", "west",
                            "up the mountain", "down the valley"])
    return SettlementEvent(
        title="Strike Rumor",
        description=(f"{npc.name} rushes into camp, breathless. "
                     f"\"They hit it big, {direction}! Nuggets laying "
                     f"on the ground!\" Half the camp is already packing."),
        npc_id=npc.npc_id, npc_name=npc.name,
        choices=[
            EventChoice("Rush out with everyone else"),
            EventChoice("Ask {name} for details first".format(name=npc.name),
                        skill="geology", difficulty=8),
            EventChoice("Stay put — work your own claim"),
            EventChoice("Use the chaos to buy abandoned gear cheap",
                        skill="trading", difficulty=8),
        ])

def _resolve_gold_strike_rumor(engine, evt, choice_idx, npcs, rng):
    p = engine.player

    if choice_idx == 0:  # Rush out
        real = rng.random() < 0.25
        if real:
            return EventOutcome(
                f"It's real. Small but real — you find color in "
                f"the first pan. Got here before the crowd.",
                xp_skill="placer", xp_amount=4.0, reputation_delta=0)
        else:
            return EventOutcome(
                f"Nothing. Rumors were overblown or someone salted "
                f"the ground. You wasted a whole day walking.",
                health_delta=-5)
    elif choice_idx == 1:  # Ask details
        if _skill_check(p, "geology", 8, rng):
            real = rng.random() < 0.3
            if real:
                return EventOutcome(
                    f"The details check out — right kind of terrain, "
                    f"right geology. Worth investigating carefully. "
                    f"You take note of the location.",
                    xp_skill="geology", xp_amount=5.0)
            else:
                return EventOutcome(
                    f"His description doesn't add up — the rock type "
                    f"he describes doesn't carry gold. You save yourself "
                    f"a trip. Good instinct.",
                    xp_skill="geology", xp_amount=3.0)
        else:
            return EventOutcome(
                f"He's talking too fast, you can't evaluate the claim. "
                f"Could be real, could be nonsense.")
    elif choice_idx == 2:  # Stay
        return EventOutcome(
            f"You keep working while half the camp runs off. "
            f"Peace and quiet. The creek's all yours today.",
            xp_skill="placer", xp_amount=2.0)
    else:  # Buy gear
        if _skill_check(p, "trading", 8, rng):
            return EventOutcome(
                f"Men abandoning their camp gear in the rush. You buy "
                f"a good pan and rocker for $3 total. Worth ten.",
                cash_delta=-3.0, item_id="gold_pan",
                xp_skill="trading", xp_amount=3.0)
        else:
            return EventOutcome(
                f"Everyone took their gear with them. Nothing left "
                f"worth buying.")


# ── ARRIVALS & STRANGERS ────────────────────────────────────────────────

def _evt_stranger_arrives(engine, npcs, rng):
    look = rng.choice([
        ("scarred and silent", "a gunfighter"),
        ("well-dressed in a city suit", "a con man or a businessman"),
        ("dusty with a heavy pack", "a prospector who's been walking for weeks"),
        ("nervous, looking over his shoulder", "someone running from something"),
        ("with a badge and a stern look", "a federal marshal"),
    ])
    name = rng.choice(["McCready", "Faulkner", "The Swede", "Jones",
                        "Silvers", "Hartley", "One-Eye", "Whitmore"])
    return SettlementEvent(
        title="Stranger in Town",
        description=(f"A stranger walks in — {look[0]}. People whisper "
                     f"he might be {look[1]}. He calls himself {name}. "
                     f"He's asking about you."),
        npc_name=name,
        choices=[
            EventChoice("Go introduce yourself"),
            EventChoice("Ask around about him first",
                        skill="trading", difficulty=8),
            EventChoice("Avoid him"),
            EventChoice("Watch from a distance",
                        skill="tracking", difficulty=8),
        ])

def _resolve_stranger_arrives(engine, evt, choice_idx, npcs, rng):
    p = engine.player

    if choice_idx == 0:  # Introduce
        intent = rng.choices(
            ["friendly", "business", "threat"],
            weights=[40, 40, 20], k=1)[0]
        if intent == "friendly":
            return EventOutcome(
                f"\"{evt.npc_name}. Heard you know this country.\" "
                f"He's looking for a reliable guide. Offers $10/day.",
                cash_delta=0, reputation_delta=2)
        elif intent == "business":
            return EventOutcome(
                f"He's a buyer — looking for gold dust at a fair price. "
                f"\"I pay better than the assay office,\" he says. "
                f"Could be useful.",
                reputation_delta=1)
        else:
            return EventOutcome(
                f"\"I think you're working a claim that belongs to my "
                f"associate.\" His hand rests on his holster. "
                f"This could go badly.",
                reputation_delta=-2)
    elif choice_idx == 1:  # Ask around
        if _skill_check(p, "trading", 8, rng):
            dangerous = rng.random() < 0.3
            if dangerous:
                return EventOutcome(
                    f"The bartender leans close: \"That man killed two "
                    f"people in Sonora. Stay clear.\" Good to know.",
                    xp_skill="trading", xp_amount=2.0)
            else:
                return EventOutcome(
                    f"\"Seems straight,\" people say. A trader from "
                    f"Sacramento. Pays fair. Nothing to worry about.",
                    xp_skill="trading", xp_amount=1.0)
        else:
            return EventOutcome(
                f"Nobody knows anything — or nobody's talking.")
    elif choice_idx == 2:  # Avoid
        return EventOutcome(
            f"You steer clear. {evt.npc_name} stays a few days, "
            f"then moves on. You'll never know what he wanted.")
    else:  # Watch
        if _skill_check(p, "tracking", 8, rng):
            return EventOutcome(
                f"You observe from the shadows. He meets with the "
                f"merchant, exchanges something — a letter? Money? "
                f"Then he rides out before dawn.",
                xp_skill="tracking", xp_amount=3.0)
        else:
            return EventOutcome(
                f"He notices you watching. Tips his hat. Unsettling.")


# ── WEATHER & DISASTER ───────────────────────────────────────────────────

def _evt_fire_in_town(engine, npcs, rng):
    npc = _pick_npc(npcs)
    building = rng.choice(["the general store", "a cabin on the edge of camp",
                           "the saloon's kitchen", "a woodpile behind the hotel",
                           "the livery stable"])
    return SettlementEvent(
        title="Fire!",
        description=(f"Fire! {building.capitalize()} is burning. "
                     f"Smoke billowing. People screaming. "
                     f"The bucket brigade is forming up but they need "
                     f"every hand."),
        npc_name=npc.name if npc else "", severity="warning",
        choices=[
            EventChoice("Join the bucket brigade"),
            EventChoice("Run in and save what you can",
                        skill="survival", difficulty=12),
            EventChoice("Help evacuate people"),
            EventChoice("Protect your own property"),
        ])

def _resolve_fire_in_town(engine, evt, choice_idx, npcs, rng):
    p = engine.player

    if choice_idx == 0:  # Bucket brigade
        return EventOutcome(
            f"You haul water until your arms burn. The fire is contained "
            f"after an hour. The building's gutted but the ones next "
            f"to it survived. Everyone's soot-black and exhausted.",
            reputation_delta=5, health_delta=-5,
            xp_skill="survival", xp_amount=3.0)
    elif choice_idx == 1:  # Run in
        if _skill_check(p, "survival", 12, rng):
            return EventOutcome(
                f"You dash through the smoke and drag out supplies — "
                f"tools, blankets, a strongbox. The owner is in tears "
                f"of gratitude. \"Everything I had was in there.\"",
                reputation_delta=10, health_delta=-10,
                item_id="rope_10ft",
                xp_skill="survival", xp_amount=5.0)
        else:
            return EventOutcome(
                f"The smoke is too thick. You stumble out coughing, "
                f"singed, gasping. Nearly didn't make it. "
                f"The building collapses behind you.",
                health_delta=-20, reputation_delta=3)
    elif choice_idx == 2:  # Evacuate
        return EventOutcome(
            f"You help families move their belongings to safety. "
            f"Children crying, dogs barking, total chaos. "
            f"But everyone gets out. That's what matters.",
            reputation_delta=8, xp_skill="survival", xp_amount=2.0)
    else:  # Protect own
        return EventOutcome(
            f"You stand guard over your own camp with wet blankets "
            f"ready. The fire doesn't reach you. Others notice "
            f"you didn't help.",
            reputation_delta=-5)


def _evt_flood_warning(engine, npcs, rng):
    npc = _pick_npc(npcs)
    return SettlementEvent(
        title="Rising Water",
        description=(f"The creek is rising fast after upstream rain. "
                     f"Water's already at the porch level. "
                     f"{npc.name if npc else 'Someone'} is yelling to "
                     f"move equipment to high ground."),
        npc_name=npc.name if npc else "", severity="warning",
        choices=[
            EventChoice("Help move camp equipment to higher ground"),
            EventChoice("Dam the water with sandbags",
                        skill="engineering", difficulty=12),
            EventChoice("Secure only your own gear"),
            EventChoice("Head for high ground immediately"),
        ])

def _resolve_flood_warning(engine, evt, choice_idx, npcs, rng):
    p = engine.player

    if choice_idx == 0:  # Help move
        return EventOutcome(
            f"You and a dozen others haul sluice boxes, rockers, "
            f"and supplies up the bank. Backbreaking work. The flood "
            f"takes the lower claims but the equipment is saved.",
            reputation_delta=6, health_delta=-8,
            xp_skill="survival", xp_amount=3.0)
    elif choice_idx == 1:  # Dam
        if _skill_check(p, "engineering", 12, rng):
            return EventOutcome(
                f"You organize a sandbag wall across the low point. "
                f"It holds — barely. The water diverts around camp. "
                f"People are calling you an engineer now.",
                reputation_delta=12, health_delta=-5,
                xp_skill="engineering", xp_amount=6.0)
        else:
            return EventOutcome(
                f"The sandbag wall collapses under the pressure. "
                f"Water everywhere. Worse than if you'd done nothing — "
                f"the redirected flow hit the dry side of camp.",
                reputation_delta=-3, health_delta=-10)
    elif choice_idx == 2:  # Secure own
        return EventOutcome(
            f"You grab your pack and tools and move to high ground. "
            f"Your gear is safe. Others weren't as quick.",
            reputation_delta=-3, health_delta=-2)
    else:  # Run
        return EventOutcome(
            f"You get out fast. Smart — the flood is worse than "
            f"expected. Several claims are washed out completely. "
            f"Those who stayed are soaked and cursing.",
            health_delta=-2)


# ── ANIMALS ──────────────────────────────────────────────────────────────

def _evt_bear_in_camp(engine, npcs, rng):
    npc = _pick_npc(npcs)
    where = rng.choice(["the meat cache", "behind the general store",
                        "the garbage pit", "someone's tent"])
    return SettlementEvent(
        title="Bear!",
        description=(f"A bear is rummaging through {where}. Big one — "
                     f"grizzly, maybe 600 pounds. "
                     f"{npc.name if npc else 'People'} backed away slowly. "
                     f"It hasn't charged anyone. Yet."),
        npc_name=npc.name if npc else "", severity="advisory",
        choices=[
            EventChoice("Shoot it", skill="firearms", difficulty=14),
            EventChoice("Make noise to scare it off"),
            EventChoice("Throw food away from camp to lure it out",
                        skill="survival", difficulty=8),
            EventChoice("Stay very still and wait"),
        ])

def _resolve_bear_in_camp(engine, evt, choice_idx, npcs, rng):
    p = engine.player

    if choice_idx == 0:  # Shoot
        if _skill_check(p, "firearms", 14, rng):
            return EventOutcome(
                f"One shot. Clean kill. 600 pounds of bear hits the dirt. "
                f"The camp eats well tonight. \"Hell of a shot,\" "
                f"someone says.",
                reputation_delta=8, item_id="fresh_venison",
                xp_skill="firearms", xp_amount=5.0)
        else:
            return EventOutcome(
                f"You wound it. Now it's angry. It charges — you dive "
                f"behind a barrel. Others open fire. It goes down, "
                f"but not before ripping through a tent.",
                health_delta=-12, reputation_delta=2,
                xp_skill="firearms", xp_amount=3.0)
    elif choice_idx == 1:  # Make noise
        if rng.random() < 0.6:
            return EventOutcome(
                f"You bang pots and yell. The bear looks up, annoyed, "
                f"then lumbers off into the trees. Worked this time.",
                reputation_delta=2, xp_skill="survival", xp_amount=2.0)
        else:
            return EventOutcome(
                f"The bear doesn't care about your noise. It finishes "
                f"eating and leaves on its own schedule. You feel foolish "
                f"standing there with a pot.",
                reputation_delta=-1)
    elif choice_idx == 2:  # Lure with food
        if _skill_check(p, "survival", 8, rng):
            return EventOutcome(
                f"You toss jerky and hardtack in a trail leading "
                f"away from camp. The bear follows the food. "
                f"Slow, but effective. No one got hurt.",
                reputation_delta=4, xp_skill="survival", xp_amount=4.0)
        else:
            return EventOutcome(
                f"The bear ignores your food offering and goes for "
                f"the better stuff in the tent. Can't blame it.",
                reputation_delta=0)
    else:  # Wait
        return EventOutcome(
            f"You freeze. Everyone freezes. The bear eats its fill "
            f"and wanders off after twenty tense minutes. "
            f"Feels like twenty hours.",
            xp_skill="survival", xp_amount=1.0)


# ── GOSSIP & SOCIAL ──────────────────────────────────────────────────────

def _evt_npc_asks_favor(engine, npcs, rng):
    npc = _pick_npc(npcs)
    if not npc:
        return None
    favor = rng.choice([
        ("deliver a letter to his wife back east", "a letter"),
        ("lend him $5 until payday", "$5"),
        ("teach him to pan for gold", "prospecting lessons"),
        ("look at a map and tell him if the geology makes sense",
         "geological advice"),
        ("help him fix a broken sluice box", "carpentry help"),
        ("stand watch over his claim while he sleeps", "guard duty"),
    ])
    return SettlementEvent(
        title="Favor Asked",
        description=(f"{npc.name} approaches you. He needs a favor — "
                     f"{favor[0]}. He's {rng.choice(['desperate', 'polite but insistent', 'clearly embarrassed to ask', 'offering to pay you back double'])}. "
                     f"\"I wouldn't ask if I had anyone else.\""),
        npc_id=npc.npc_id, npc_name=npc.name,
        choices=[
            EventChoice("Help him out"),
            EventChoice("Help, but ask for something in return",
                        skill="trading", difficulty=8),
            EventChoice("Decline politely"),
            EventChoice("Decline rudely"),
        ])

def _resolve_npc_asks_favor(engine, evt, choice_idx, npcs, rng):
    npc = next((n for n in npcs if n.npc_id == evt.npc_id), None)
    p = engine.player

    if choice_idx == 0:  # Help freely
        if npc: npc.adjust_relationship(15)
        return EventOutcome(
            f"You help {evt.npc_name} without asking anything in return. "
            f"He's genuinely grateful. \"I won't forget this.\" "
            f"And he means it.",
            reputation_delta=3, relationship_delta=15)
    elif choice_idx == 1:  # Help for payment
        if _skill_check(p, "trading", 8, rng):
            if npc: npc.adjust_relationship(5)
            return EventOutcome(
                f"\"Fair enough.\" {evt.npc_name} agrees to return the "
                f"favor — information, labor, or cash. A useful contact.",
                reputation_delta=1, relationship_delta=5,
                cash_delta=rng.uniform(2, 8),
                xp_skill="trading", xp_amount=2.0)
        else:
            if npc: npc.adjust_relationship(-5)
            return EventOutcome(
                f"\"I'm asking for help and you want to haggle?\" "
                f"{evt.npc_name} walks away disgusted.",
                relationship_delta=-5)
    elif choice_idx == 2:  # Decline politely
        return EventOutcome(
            f"\"Sorry, can't right now.\" {evt.npc_name} nods and "
            f"moves on to ask someone else. No hard feelings.",
            reputation_delta=0)
    else:  # Decline rudely
        if npc: npc.adjust_relationship(-10)
        return EventOutcome(
            f"\"Not my problem.\" {evt.npc_name}'s face hardens. "
            f"He walks away without a word. People nearby overheard.",
            reputation_delta=-3, relationship_delta=-10)


def _evt_npc_offers_info(engine, npcs, rng):
    npc = _pick_npc(npcs)
    if not npc:
        return None
    info_type = rng.choice([
        ("where the best prospecting ground is",
         "geology", "xp_skill", "geology", 4.0),
        ("which merchants cheat on weights",
         "trading", "reputation_delta", "", 3.0),
        ("where a wanted man is hiding",
         "law", "reputation_delta", "", 5.0),
        ("a shortcut through the mountains",
         "tracking", "xp_skill", "tracking", 3.0),
        ("how to build a better sluice box",
         "engineering", "xp_skill", "engineering", 4.0),
    ])
    topic = info_type[0]
    return SettlementEvent(
        title="Information Offered",
        description=(f"{npc.name} sidles up to you quietly. "
                     f"\"I know {topic}. Worth something to you?\" "
                     f"He wants $3 for the information."),
        npc_id=npc.npc_id, npc_name=npc.name,
        choices=[
            EventChoice("Pay $3 for the information"),
            EventChoice("Negotiate the price down",
                        skill="trading", difficulty=10),
            EventChoice("Refuse — could be worthless"),
            EventChoice("Intimidate him into telling you free",
                        attribute="strength", attr_min=12),
        ])

def _resolve_npc_offers_info(engine, evt, choice_idx, npcs, rng):
    npc = next((n for n in npcs if n.npc_id == evt.npc_id), None)
    p = engine.player
    good_info = rng.random() < 0.65

    if choice_idx == 0:  # Pay
        if p.cash < 3:
            return EventOutcome("You don't have $3.")
        if good_info:
            return EventOutcome(
                f"Worth every penny. {evt.npc_name} draws a map on "
                f"a scrap of paper. Detailed, specific. This is real.",
                cash_delta=-3.0, relationship_delta=5,
                xp_skill="geology", xp_amount=4.0)
        else:
            return EventOutcome(
                f"Vague directions, obvious advice. You paid $3 for "
                f"common knowledge. {evt.npc_name} is already gone.",
                cash_delta=-3.0, relationship_delta=-3)
    elif choice_idx == 1:  # Negotiate
        if _skill_check(p, "trading", 10, rng):
            if good_info:
                return EventOutcome(
                    f"Talked him down to $1. And the information is solid — "
                    f"specific locations, tested by {evt.npc_name} himself.",
                    cash_delta=-1.0, xp_skill="trading", xp_amount=3.0)
            else:
                return EventOutcome(
                    f"$1 for garbage. At least you didn't pay full price.",
                    cash_delta=-1.0, xp_skill="trading", xp_amount=1.0)
        else:
            return EventOutcome(
                f"\"$3 or nothing.\" He walks. The information walks "
                f"with him.",
                reputation_delta=-1)
    elif choice_idx == 2:  # Refuse
        return EventOutcome(
            f"\"Suit yourself.\" {evt.npc_name} shrugs and finds "
            f"another buyer.",
            reputation_delta=0)
    else:  # Intimidate
        str_val = p.attributes.get("strength", 10)
        if str_val >= 12 and rng.random() < 0.6:
            if npc: npc.adjust_relationship(-15)
            return EventOutcome(
                f"You lean in close. \"Tell me. Free.\" "
                f"{evt.npc_name} pales and talks. Fast. "
                f"The information might even be good.",
                relationship_delta=-15, reputation_delta=-3,
                xp_skill="geology", xp_amount=2.0)
        else:
            return EventOutcome(
                f"{evt.npc_name} doesn't scare easy. "
                f"\"Touch me and the sheriff hears about it.\" "
                f"He walks away with your dignity.",
                reputation_delta=-5, relationship_delta=-10)


# ── CAMP/BOOMTOWN SPECIFIC ──────────────────────────────────────────────

def _evt_newcomer_lost(engine, npcs, rng):
    name = rng.choice(["a young man", "an older fellow", "a woman",
                        "a boy barely sixteen", "a foreigner"])
    return SettlementEvent(
        title="Lost Newcomer",
        description=(f"{name.capitalize()} wanders into camp looking lost. "
                     f"No supplies, no tools, no idea what they're doing. "
                     f"They came west to find gold and clearly have "
                     f"no plan beyond that."),
        choices=[
            EventChoice("Take them under your wing — show them the basics"),
            EventChoice("Point them to the general store and wish them luck"),
            EventChoice("Warn them this isn't a place for beginners"),
            EventChoice("Offer to hire them as labor"),
        ])

def _resolve_newcomer_lost(engine, evt, choice_idx, npcs, rng):
    if choice_idx == 0:  # Mentor
        return EventOutcome(
            f"You spend an afternoon teaching basic panning, how to "
            f"read the creek, where to camp. They're a quick learner. "
            f"Could have a friend for life.",
            reputation_delta=5, xp_skill="placer", xp_amount=2.0)
    elif choice_idx == 1:  # Point to store
        return EventOutcome(
            f"\"That way. Buy a pan, a shovel, and some flour. "
            f"Then find a spot nobody's working.\" Simple advice. "
            f"Better than nothing.",
            reputation_delta=1)
    elif choice_idx == 2:  # Warn
        return EventOutcome(
            f"\"People die out here. Go home.\" They look at you "
            f"with big eyes. By morning they've either left or "
            f"staked a claim. You said your piece.",
            reputation_delta=1)
    else:  # Hire
        return EventOutcome(
            f"\"Work for me, $1 a day and food. You'll learn the "
            f"trade.\" They accept immediately. Eager labor, "
            f"though unskilled.",
            cash_delta=-1.0, reputation_delta=2)


# ── CITY SPECIFIC ────────────────────────────────────────────────────────

def _evt_newspaper_reporter(engine, npcs, rng):
    npc = _pick_npc(npcs)
    return SettlementEvent(
        title="Reporter",
        description=(f"A newspaper reporter is in town writing a story "
                     f"about the mining district. She's asking everyone "
                     f"for quotes. Now she's headed your way with a "
                     f"pencil and notepad."),
        choices=[
            EventChoice("Give an honest interview about conditions"),
            EventChoice("Exaggerate — make the place sound amazing",
                        skill="trading", difficulty=8),
            EventChoice("Complain about everything — corruption, "
                        "unsafe conditions"),
            EventChoice("Decline to comment"),
        ])

def _resolve_newspaper_reporter(engine, evt, choice_idx, npcs, rng):
    if choice_idx == 0:  # Honest
        return EventOutcome(
            f"You tell it straight. The good, the bad, the mud. "
            f"She writes it all down. A fair article runs next week — "
            f"your name in print. People respect honesty.",
            reputation_delta=5)
    elif choice_idx == 1:  # Exaggerate
        if _skill_check(engine.player, "trading", 8, rng):
            return EventOutcome(
                f"\"Gold everywhere! Richest ground in California!\" "
                f"She prints it. Next month, a flood of newcomers "
                f"arrive. Prices rise. You started something.",
                reputation_delta=3, price_mult=1.3, price_duration=14,
                xp_skill="trading", xp_amount=2.0)
        else:
            return EventOutcome(
                f"Your tall tales are obviously fake. She writes "
                f"a piece about liars in mining camps instead. "
                f"Your name is mentioned. Unfavorably.",
                reputation_delta=-5)
    elif choice_idx == 2:  # Complain
        return EventOutcome(
            f"You unload — bad water, crooked merchants, dangerous "
            f"conditions. She writes it all. The article brings "
            f"attention — and eventually, inspectors.",
            reputation_delta=2, price_mult=0.9, price_duration=7)
    else:
        return EventOutcome(
            f"\"No comment.\" She moves on to the next person. "
            f"Your story goes untold.")


# ── NEWSPAPER ────────────────────────────────────────────────────────

def _evt_read_newspaper(engine, npcs, rng):
    headlines = [
        "GOLD STRIKE REPORTED UP NORTH — dozens rushing to new diggings",
        "STAGE ROBBED ON PLACERVILLE ROAD — $2,000 in gold dust taken",
        "NEW ASSAY OFFICE OPENS — promises fair weights and honest readings",
        "CHOLERA FEARS — three deaths in camp downstream, boil your water",
        "FREIGHT PRICES RISING — teamsters demand higher rates",
        "CLAIM DISPUTE ENDS IN SHOOTING — two men dead over 50 feet of creek",
        "SHIP ARRIVES FROM EAST — fresh supplies expected within the week",
        "PRICE OF FLOUR DOUBLES — drought in valley reduces harvest",
        "VIGILANCE COMMITTEE FORMS — three hangings this month already",
        "CHINESE MINERS DISCOVER NEW CREEK — working abandoned claims profitably",
    ]
    headline = rng.choice(headlines)
    return SettlementEvent(
        title="Newspaper",
        description=f"A copy of the local gazette is posted on the board. "
                    f"The headline reads: \"{headline}\"",
        choices=[
            EventChoice("Read the whole paper carefully",
                        skill="trading", difficulty=6),
            EventChoice("Glance at it and move on"),
            EventChoice("Ask someone about the headline"),
        ])

def _resolve_read_newspaper(engine, evt, choice_idx, npcs, rng):
    if choice_idx == 0:  # Read carefully
        if _skill_check(engine.player, "trading", 6, rng):
            return EventOutcome(
                "You read every column — prices, arrivals, wanted notices, "
                "classifieds. A merchant is selling a claim cheap. "
                "An assayer is offering free tests this week. "
                "Knowledge is currency out here.",
                xp_skill="trading", xp_amount=3.0, reputation_delta=1)
        else:
            return EventOutcome(
                "The small print blurs. You get the gist but miss the details. "
                "Should've paid more attention in school.")
    elif choice_idx == 1:
        return EventOutcome("You note the headline and keep walking.")
    else:
        return EventOutcome(
            "An old-timer fills you in. Half gossip, half fact. "
            "Hard to tell which is which.",
            xp_skill="trading", xp_amount=1.0)


# ── SUPPLY CHAIN DISRUPTION ──────────────────────────────────────────

def _evt_supply_disruption(engine, npcs, rng):
    cause = rng.choice([
        "Bandits hit a freight wagon on the road in.",
        "The bridge washed out in the storm.",
        "Teamsters are on strike — no deliveries this week.",
        "A mule train lost half its load crossing the river.",
    ])
    return SettlementEvent(
        title="Supply Disruption",
        description=f"{cause} The camp store is running low. "
                    f"Prices are climbing. People are hoarding.",
        severity="advisory",
        choices=[
            EventChoice("Buy what you can before prices spike"),
            EventChoice("Offer to help bring supplies in",
                        skill="survival", difficulty=8),
            EventChoice("Wait it out — supplies will come"),
            EventChoice("Sell your surplus at the markup",
                        skill="trading", difficulty=8),
        ])

def _resolve_supply_disruption(engine, evt, choice_idx, npcs, rng):
    if choice_idx == 0:  # Buy early
        return EventOutcome(
            "Smart move. You stock up before the rush. "
            "By tomorrow, flour costs triple.",
            cash_delta=-5.0, price_mult=1.5, price_duration=7)
    elif choice_idx == 1:  # Help
        if _skill_check(engine.player, "survival", 8, rng):
            return EventOutcome(
                "You help haul emergency supplies from the next town. "
                "Hard work but the camp remembers who stepped up.",
                reputation_delta=8, health_delta=-5,
                xp_skill="survival", xp_amount=4.0)
        else:
            return EventOutcome(
                "You try but the road is worse than expected. "
                "You turn back exhausted, empty-handed.",
                health_delta=-8)
    elif choice_idx == 2:
        return EventOutcome(
            "You wait. Prices spike for a week. "
            "Some men go hungry. The supply wagon finally arrives.",
            price_mult=1.5, price_duration=7)
    else:  # Sell surplus
        if _skill_check(engine.player, "trading", 8, rng):
            return EventOutcome(
                "You sell your extra flour and salt at triple markup. "
                "The desperate pay. Good business, questionable morals.",
                cash_delta=15.0, reputation_delta=-3,
                xp_skill="trading", xp_amount=3.0)
        else:
            return EventOutcome(
                "Nobody's buying from you — the store's still got some. "
                "Your markup was too aggressive.",
                reputation_delta=-1)


# ── COMPETING PROSPECTOR ─────────────────────────────────────────────

def _evt_competing_prospector(engine, npcs, rng):
    npc = _pick_npc(npcs)
    if not npc:
        return None
    spot = rng.choice(["the same creek you've been working",
                       "the ridge you've had your eye on",
                       "ground right next to your claim",
                       "a gravel bar you tested last week"])
    return SettlementEvent(
        title="Competition",
        description=f"{npc.name} has started working {spot}. "
                    f"He's got a rocker box and two helpers. "
                    f"The good ground is getting crowded.",
        npc_id=npc.npc_id, npc_name=npc.name,
        choices=[
            EventChoice("Talk to him — propose splitting the area"),
            EventChoice("Work harder — outpace him",
                        skill="placer", difficulty=10),
            EventChoice("Stake your claim formally to protect it"),
            EventChoice("Let it go — plenty of creek to work"),
        ])

def _resolve_competing_prospector(engine, evt, choice_idx, npcs, rng):
    npc = next((n for n in npcs if n.npc_id == evt.npc_id), None)

    if choice_idx == 0:  # Split
        if npc: npc.adjust_relationship(10)
        return EventOutcome(
            f"You work it out over coffee. He takes upstream, "
            f"you take downstream. Handshake deal. "
            f"\"Fair is fair,\" {evt.npc_name} says.",
            reputation_delta=3, relationship_delta=10)
    elif choice_idx == 1:  # Outwork
        if _skill_check(engine.player, "placer", 10, rng):
            return EventOutcome(
                "You're up before dawn, working every inch. "
                "By the end of the week he moves on — can't keep up. "
                "The ground is yours.",
                xp_skill="placer", xp_amount=5.0)
        else:
            return EventOutcome(
                "He's faster. More helpers. Better equipment. "
                "You exhaust yourself and he's still pulling more color.",
                health_delta=-5, xp_skill="placer", xp_amount=2.0)
    elif choice_idx == 2:  # Stake claim
        return EventOutcome(
            "You drive stakes at the corners and post your notice. "
            "Legal protection — if he crosses the line, it's claim jumping. "
            "He eyes the stakes but stays on his side.",
            reputation_delta=2, xp_skill="law", xp_amount=2.0)
    else:
        return EventOutcome(
            "You shrug and move upstream. Plenty of creek. "
            "No point fighting over dirt.",
            reputation_delta=1)


# ============================================================================
#  EVENT REGISTRY — maps event functions to their resolvers
# ============================================================================

# (event_func, resolve_func, weight, required_settlement_types or None for all)
_EVENT_REGISTRY: List[tuple] = [
    # Saloon & Social
    (_evt_bar_fight,        _resolve_bar_fight,        10, None),
    (_evt_drunk_prospector, _resolve_drunk_prospector,   8, None),
    (_evt_gambling_dispute, _resolve_gambling_dispute,   7, None),

    # Law & Order
    (_evt_wanted_man,       _resolve_wanted_man,         5, None),
    (_evt_theft_accusation, _resolve_theft_accusation,   6, None),

    # Economy
    (_evt_merchant_deal,    _resolve_merchant_deal,      7, None),
    (_evt_supply_shortage,  _resolve_supply_shortage,    5, None),

    # Health
    (_evt_sick_person,      _resolve_sick_person,        6, None),

    # Mining
    (_evt_claim_dispute,    _resolve_claim_dispute,      8,
     {"mining_camp_small", "mining_camp_medium", "boomtown"}),
    (_evt_gold_strike_rumor,_resolve_gold_strike_rumor,   7,
     {"mining_camp_small", "mining_camp_medium", "boomtown", "small_town"}),

    # Arrivals
    (_evt_stranger_arrives, _resolve_stranger_arrives,   6, None),

    # Disaster
    (_evt_fire_in_town,     _resolve_fire_in_town,       4, None),
    (_evt_flood_warning,    _resolve_flood_warning,      4,
     {"mining_camp_small", "mining_camp_medium", "boomtown"}),

    # Animals
    (_evt_bear_in_camp,     _resolve_bear_in_camp,       5,
     {"mining_camp_small", "mining_camp_medium", "boomtown", "trading_post"}),

    # Social
    (_evt_npc_asks_favor,   _resolve_npc_asks_favor,     8, None),
    (_evt_npc_offers_info,  _resolve_npc_offers_info,    7, None),

    # Camp-specific
    (_evt_newcomer_lost,    _resolve_newcomer_lost,      6,
     {"mining_camp_small", "mining_camp_medium", "boomtown"}),

    # City-specific
    (_evt_newspaper_reporter, _resolve_newspaper_reporter, 5,
     {"city", "small_town"}),

    # Newspaper — read headlines (cities/towns with newspaper buildings)
    (_evt_read_newspaper, _resolve_read_newspaper, 6,
     {"city", "small_town"}),

    # Supply chain disruption
    (_evt_supply_disruption, _resolve_supply_disruption, 4,
     {"mining_camp_small", "mining_camp_medium", "boomtown"}),

    # Competing prospector
    (_evt_competing_prospector, _resolve_competing_prospector, 6,
     {"mining_camp_small", "mining_camp_medium", "boomtown"}),
]


# ============================================================================
#  MAIN ENTRY POINT
# ============================================================================

def roll_settlement_event(engine: "Engine", settlement_type: str,
                          season: str = "summer",
                          year: int = 1849) -> Optional[SettlementEvent]:
    """
    Roll for and present an interactive settlement event.
    Called once per day from engine daily tick.
    Returns the completed event (with outcome) or None.
    """
    rng = random.Random()

    # Check if an event fires
    chance = EVENT_CHANCE.get(settlement_type, 0.25)
    if rng.random() > chance:
        return None

    # Get available NPCs
    npcs = []
    if engine:
        wx, wy = engine.player.world_x, engine.player.world_y
        ax, ay = engine.player.area_x, engine.player.area_y
        prefixes = (f"sett_{wx}_{wy}_{ax}_{ay}_",
                    f"wild_{wx}_{wy}_{ax}_{ay}_")
        npcs = [n for n in engine.npc_mgr.npcs.values()
                if n.present and n.alive
                and any(n.npc_id.startswith(p) for p in prefixes)]

    # Filter events by settlement type
    eligible = []
    for evt_func, resolve_func, weight, stypes in _EVENT_REGISTRY:
        if stypes is None or settlement_type in stypes:
            eligible.append((evt_func, resolve_func, weight))

    if not eligible:
        return None

    # Try events in weighted random order until one succeeds
    rng.shuffle(eligible)
    funcs, resolvers, weights = zip(*eligible)
    order = rng.choices(range(len(eligible)), weights=weights, k=min(5, len(eligible)))

    for idx in order:
        evt_func, resolve_func, _ = eligible[idx]
        evt = evt_func(engine, npcs, rng)
        if evt is None:
            continue

        # Present choices to player
        choice_idx = _present_event(engine, evt, rng)
        if choice_idx is None:
            # Player cancelled — still show the description but no interaction
            return evt

        # Resolve the outcome
        outcome = resolve_func(engine, evt, choice_idx, npcs, rng)
        evt.outcome = outcome

        # Apply effects
        if outcome and engine:
            _apply_outcome(engine, evt, outcome, npcs)

        return evt

    return None


def _apply_outcome(engine: "Engine", evt: SettlementEvent,
                   outcome: EventOutcome, npcs: list):
    """Apply all outcome effects to game state."""
    p = engine.player
    region = ""
    if engine.current_local:
        region = getattr(engine.current_local, '_region_name', '')

    # Show outcome message
    engine.add_message(outcome.message, "normal")

    # Cash
    if outcome.cash_delta:
        p.cash += outcome.cash_delta
        if outcome.cash_delta > 0:
            engine.add_message(f"  [+${outcome.cash_delta:.2f}]", "advisory")
        elif outcome.cash_delta < 0:
            engine.add_message(f"  [-${abs(outcome.cash_delta):.2f}]", "advisory")

    # Health
    if outcome.health_delta:
        p.survival.health = max(0, min(100,
            p.survival.health + outcome.health_delta))
        if outcome.health_delta < 0:
            engine.add_message(
                f"  [Health {outcome.health_delta:+.0f}]", "advisory")

    # Reputation
    if outcome.reputation_delta and region:
        engine.reputation.adjust(region, outcome.reputation_delta)

    # Skill XP
    if outcome.xp_skill and outcome.xp_amount > 0:
        p.gain_skill_xp(outcome.xp_skill, outcome.xp_amount)

    # Item
    if outcome.item_id:
        try:
            from src.items import make_item
            item = make_item(outcome.item_id)
            p.inventory.append(item)
            engine.add_message(f"  [Received: {item.name}]", "advisory")
        except Exception:
            pass

    # NPC effects
    if evt.npc_id:
        npc = next((n for n in npcs if n.npc_id == evt.npc_id), None)
        if npc:
            if outcome.npc_hostile:
                npc.go_hostile()
            if outcome.npc_leaves:
                npc.present = False

    # Price effects
    if outcome.price_mult != 1.0 and outcome.price_duration > 0:
        if not hasattr(engine, '_settlement_price_effects'):
            engine._settlement_price_effects = []
        current_day = engine.time.total_minutes // 1440
        engine._settlement_price_effects.append({
            "mult": outcome.price_mult,
            "expires": current_day + outcome.price_duration,
        })
