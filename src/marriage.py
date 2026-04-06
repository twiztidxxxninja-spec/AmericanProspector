"""
src/marriage.py

Marriage ceremony and spouse management system.

Integrates with the NPC relationship system (npc_system.py):
    NPCRelationship — multi-axis relationship with romantic, affinity, trust,
                      status progression (stranger -> courting -> engaged -> married)
    PregnancyState  — pregnancy tracking for married NPC spouse
    BackgroundSimulator._sim_spouse() — handles spouse events during time passage

Historical accuracy (1840s California):
- Marriages performed by preachers, ministers, or justices of the peace
- Weddings were community events — attending NPCs form stronger bonds
- Rings were desired but not always available on the frontier
- Miners often left wives behind; long separations strained marriages
- Anniversary traditions mattered even in rough mining camps
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple


# ============================================================================
#  MARRIAGE STATE
# ============================================================================

@dataclass
class MarriageState:
    """Persistent state for the player's marriage."""
    spouse_npc_id: str
    spouse_name: str
    wedding_day: int                     # game day of the ceremony
    wedding_town: str

    home_lot_id: Optional[str] = None    # property.py lot id, if they have a home
    happiness: float = 80.0              # 0–100
    days_apart: int = 0
    anniversary_day: int = 0             # set to wedding_day for yearly checks

    def to_dict(self) -> dict:
        return {
            "spouse_npc_id":  self.spouse_npc_id,
            "spouse_name":    self.spouse_name,
            "wedding_day":    self.wedding_day,
            "wedding_town":   self.wedding_town,
            "home_lot_id":    self.home_lot_id,
            "happiness":      self.happiness,
            "days_apart":     self.days_apart,
            "anniversary_day": self.anniversary_day,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MarriageState":
        return cls(
            spouse_npc_id=d["spouse_npc_id"],
            spouse_name=d["spouse_name"],
            wedding_day=d["wedding_day"],
            wedding_town=d["wedding_town"],
            home_lot_id=d.get("home_lot_id"),
            happiness=d.get("happiness", 80.0),
            days_apart=d.get("days_apart", 0),
            anniversary_day=d.get("anniversary_day", d.get("wedding_day", 0)),
        )


# ============================================================================
#  PROPOSAL
# ============================================================================

def can_propose(player, npc) -> Tuple[bool, str]:
    """
    Check whether the player can propose marriage to an NPC.

    Requirements:
    - NPC romantic interest >= 60
    - NPC affinity >= 50
    - NPC relationship status is "close_friend" or "courting"
    - NPC is romantically eligible (not already married, etc.)

    Returns (ok, reason).
    """
    rel = npc.rel

    if not getattr(npc, "romantic_eligible", False):
        return False, f"{npc.name} is not available for romance."

    if rel.status not in ("close_friend", "courting"):
        if rel.status in ("engaged", "married"):
            return False, f"You are already {rel.status} to {npc.name}."
        return False, (
            f"You don't know {npc.name} well enough to propose. "
            f"(Status: {rel.status})"
        )

    if rel.romantic < 60:
        return False, (
            f"{npc.name} doesn't have strong enough romantic feelings yet. "
            f"(Romantic: {rel.romantic:.0f}/60)"
        )

    if rel.affinity < 50:
        return False, (
            f"{npc.name} doesn't feel close enough to you yet. "
            f"(Affinity: {rel.affinity:.0f}/50)"
        )

    return True, "You may propose."


def propose(player, npc, day: int) -> Tuple[bool, str]:
    """
    Attempt a marriage proposal.

    Performs a CHA-weighted check plus relationship modifiers.
    On success: NPC status set to "engaged".

    Returns (accepted, message).
    """
    ok, reason = can_propose(player, npc)
    if not ok:
        return False, reason

    rel = npc.rel
    cha = player.attributes.get("charisma", 10)

    # Base acceptance chance: CHA bonus + relationship quality
    chance = 0.40
    chance += (cha - 10) * 0.03          # +/- 3% per CHA point
    chance += (rel.romantic - 60) * 0.005  # bonus for high romantic
    chance += (rel.affinity - 50) * 0.004  # bonus for high affinity
    chance += (rel.trust / 100) * 0.15     # trust is important
    chance = max(0.10, min(0.95, chance))

    if random.random() < chance:
        rel.set_status("engaged")
        rel.adjust(affinity=10, romantic=10, trust=5)
        npc.expanded_memory.add(
            f"{player.name} proposed marriage and I accepted.",
            day, significance=1.0, valence=1.0, category="event",
        )
        return True, (
            f"{npc.name} accepts your proposal! "
            f"\"Yes! Oh, yes!\" You are now engaged."
        )
    else:
        # Rejection — doesn't ruin relationship, but stings
        rel.adjust(romantic=-5)
        npc.expanded_memory.add(
            f"{player.name} proposed but I wasn't ready.",
            day, significance=0.7, valence=-0.3, category="event",
        )
        return False, (
            f"{npc.name} looks down. \"I... I'm not ready for that. "
            f"Not yet.\" The proposal is declined, but hope remains."
        )


# ============================================================================
#  WEDDING CEREMONY
# ============================================================================

def can_wed(player, npc, nearby_npcs: list) -> Tuple[bool, str]:
    """
    Check whether a wedding can proceed right now.

    Requirements:
    - NPC relationship status is "engaged"
    - A preacher or minister is present among nearby NPCs
    - Optionally, player has a ring (checked but not required)

    Returns (ok, reason).
    """
    rel = npc.rel

    if rel.status != "engaged":
        if rel.status == "married":
            return False, f"You are already married to {npc.name}."
        return False, (
            f"You must be engaged to {npc.name} before holding a wedding. "
            f"(Status: {rel.status})"
        )

    # Look for an officiant
    officiant = _find_officiant(nearby_npcs)
    if officiant is None:
        return False, (
            "No preacher or minister is present to perform the ceremony. "
            "Find a settlement with a man of the cloth."
        )

    return True, "The wedding may proceed."


def conduct_wedding(player, npc, preacher, day: int,
                    town: str) -> MarriageState:
    """
    Perform the wedding ceremony.

    - Sets NPC status to "married"
    - Creates and returns a MarriageState
    - Preacher witnesses the marriage
    - Boosts relationships with all attending NPCs

    The caller should store the returned MarriageState on the engine/player.
    """
    rel = npc.rel

    # Official union
    rel.set_status("married")
    rel.adjust(affinity=20, romantic=15, trust=10)
    npc.marital_status = "married"
    npc.spouse_id = "player"

    # Memory for spouse
    npc.expanded_memory.add(
        f"Married {player.name} in {town}. "
        f"{preacher.name} officiated.",
        day, significance=1.0, valence=1.0, category="event",
    )

    # Memory for preacher
    if hasattr(preacher, "expanded_memory"):
        preacher.expanded_memory.add(
            f"Officiated the wedding of {player.name} and {npc.name} in {town}.",
            day, significance=0.7, valence=0.6, category="event",
        )
        preacher.rel.adjust(affinity=5, trust=3, respect=5)

    # Create marriage state
    state = MarriageState(
        spouse_npc_id=npc.npc_id,
        spouse_name=npc.name,
        wedding_day=day,
        wedding_town=town,
        anniversary_day=day,
    )

    return state


# ============================================================================
#  DAILY MARRIAGE TICK
# ============================================================================

def tick_marriage(state: MarriageState,
                  player_wx: int, player_wy: int,
                  spouse_wx: int, spouse_wy: int,
                  day: int) -> List[str]:
    """
    Daily marriage update. Call once per game day.

    - Happiness decays when apart, recovers when together
    - Tracks consecutive days apart
    - Checks for anniversary

    Returns a list of narrative messages (may be empty).
    """
    msgs: List[str] = []
    together = (player_wx == spouse_wx and player_wy == spouse_wy)

    # ── Proximity effects ──────────────────────────────────────────────
    if together:
        state.days_apart = 0
        # Happiness recovers when together
        recovery = 2.0
        state.happiness = min(100.0, state.happiness + recovery)
    else:
        state.days_apart += 1
        # Happiness decays when apart — faster the longer the separation
        if state.days_apart <= 7:
            decay = 0.5
        elif state.days_apart <= 30:
            decay = 1.0
        elif state.days_apart <= 90:
            decay = 1.5
        else:
            decay = 2.5
        state.happiness = max(0.0, state.happiness - decay)

    # ── Milestone messages ─────────────────────────────────────────────
    if state.days_apart == 7:
        msgs.append(
            f"You miss {state.spouse_name}. It's been a week apart."
        )
    elif state.days_apart == 30:
        msgs.append(
            f"A month without {state.spouse_name}. "
            f"You wonder how they're getting on."
        )
    elif state.days_apart == 90:
        msgs.append(
            f"Three months apart from {state.spouse_name}. "
            f"The loneliness weighs heavy."
        )

    # ── Happiness warnings ─────────────────────────────────────────────
    if state.happiness <= 20 and state.days_apart > 0:
        msgs.append(
            f"Your marriage to {state.spouse_name} is deeply strained."
        )
    elif state.happiness <= 40 and state.days_apart > 14:
        msgs.append(
            f"{state.spouse_name} is unhappy. You should visit soon."
        )

    # ── Anniversary ────────────────────────────────────────────────────
    if state.anniversary_day > 0:
        days_since_wedding = day - state.wedding_day
        if days_since_wedding > 0 and days_since_wedding % 365 == 0:
            years = days_since_wedding // 365
            msgs.append(
                f"Today is your {_ordinal(years)} wedding anniversary "
                f"with {state.spouse_name}!"
            )
            if together:
                state.happiness = min(100.0, state.happiness + 10.0)
                msgs.append(
                    f"Spending the anniversary together lifts both your spirits."
                )

    return msgs


# ============================================================================
#  SERIALIZATION (module-level convenience wrappers)
# ============================================================================

def to_dict(state: MarriageState) -> dict:
    """Serialize a MarriageState to a plain dict."""
    return state.to_dict()


def from_dict(d: dict) -> MarriageState:
    """Deserialize a MarriageState from a plain dict."""
    return MarriageState.from_dict(d)


# ============================================================================
#  HELPERS
# ============================================================================

def _find_officiant(nearby_npcs: list, year: int = 1849):
    """Return the first NPC who can officiate a wedding, or None.
    Pre-1800: preachers were rare on the frontier. Fort commanders,
    any elder, or even just witnesses would do."""
    officiant_occupations = {"Preacher", "Minister", "Priest", "Justice of the Peace"}
    # Pre-1800: anyone in authority can officiate
    if year < 1800:
        officiant_occupations.update({
            "Fort Commander", "Militia Captain", "Trader",
            "Chief", "Elder",
        })
    for npc in nearby_npcs:
        occ = getattr(npc, "occupation", "")
        if occ in officiant_occupations:
            return npc
    # Pre-1800 fallback: any NPC with high relationship can witness
    if year < 1800 and nearby_npcs:
        for npc in nearby_npcs:
            if hasattr(npc, 'rel') and npc.rel.affinity > 30:
                return npc
    return None


def _ordinal(n: int) -> str:
    """Return ordinal string for an integer (1st, 2nd, 3rd, ...)."""
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
