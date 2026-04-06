"""
src/rival_prospectors.py

NPC prospector competition system.
Rival prospectors stake claims, extract gold, upgrade their equipment,
sell at towns, and occasionally attempt to jump the player's claim.
Provides the sense of a living, competitive Gold Rush world.
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple


# ============================================================================
#  RIVAL EVENTS — flavor text for journal / message log
# ============================================================================

RIVAL_EVENTS: Dict[str, List[str]] = {
    "find_gold": [
        "{name} whoops with excitement — looks like he struck color!",
        "Word spreads: {name} pulled a nice nugget from the creek.",
        "{name} is keeping quiet, but you see him grinning at his pan.",
        "You hear {name} found a good pocket of dust upstream.",
        "{name} is being secretive about his latest take.",
    ],
    "sell_gold": [
        "{name} heads to town to cash in his dust.",
        "You see {name} loading up to sell his gold at the assay office.",
        "{name} rides off toward town, saddlebags heavy.",
        "{name} is celebrating tonight — just sold a fine batch of dust.",
    ],
    "upgrade_equipment": [
        "{name} sets up a rocker box on his claim. He's getting serious.",
        "{name} has built himself a sluice — that claim must be paying off.",
        "{name} upgraded his gear. Competition's getting stiffer.",
        "You see {name} hauling lumber for a new sluice box.",
    ],
    "abandon_claim": [
        "{name} packs up and moves on. Another bust.",
        "{name} has given up on his claim. The ground played out.",
        "You watch {name} pull his stakes and head downstream.",
        "{name} is done — says there's better diggings elsewhere.",
    ],
    "claim_jump_attempt": [
        "{name} is eyeing your claim. Watch your back.",
        "{name} disputes your claim boundary — says you're over the line.",
        "{name} tried to stake over your ground while you were away!",
        "{name} and some friends are crowding your claim. Trouble brewing.",
        "You catch {name} panning inside your claim markers.",
    ],
    "new_arrival": [
        "A prospector named {name} has staked a claim nearby.",
        "{name} rolled in with a pack mule and a gold pan.",
        "New competition: {name} is setting up camp not far from here.",
        "{name} showed up asking about the diggings in these parts.",
    ],
}


# Equipment multipliers — how much more gold per day at each level
_EQUIPMENT_MULT: Dict[int, float] = {
    1: 1.0,     # gold pan
    2: 2.5,     # rocker box
    3: 5.0,     # sluice box
}

_EQUIPMENT_NAMES: Dict[int, str] = {
    1: "gold pan",
    2: "rocker box",
    3: "sluice box",
}


# ============================================================================
#  RIVAL CLAIM
# ============================================================================

@dataclass
class RivalClaim:
    """An NPC prospector's mining claim."""
    npc_id: str
    npc_name: str
    world_x: int
    world_y: int
    area_x: int
    area_y: int
    daily_yield_oz: float               # base yield (gold_grade * skill)
    gold_stockpile_oz: float = 0.0      # accumulated, unsold gold
    equipment_level: int = 1            # 1=pan, 2=rocker, 3=sluice
    days_active: int = 0
    abandoned: bool = False
    last_sold_day: int = 0              # day they last sold gold
    total_earned: float = 0.0           # lifetime earnings in dollars
    skill: float = 0.5                  # 0-1 prospecting skill

    @property
    def effective_yield(self) -> float:
        """Daily yield with equipment multiplier."""
        mult = _EQUIPMENT_MULT.get(self.equipment_level, 1.0)
        return self.daily_yield_oz * mult

    @property
    def equipment_name(self) -> str:
        return _EQUIPMENT_NAMES.get(self.equipment_level, "gold pan")

    # ── Serialization ────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "npc_id": self.npc_id,
            "npc_name": self.npc_name,
            "world_x": self.world_x,
            "world_y": self.world_y,
            "area_x": self.area_x,
            "area_y": self.area_y,
            "daily_yield_oz": self.daily_yield_oz,
            "gold_stockpile_oz": self.gold_stockpile_oz,
            "equipment_level": self.equipment_level,
            "days_active": self.days_active,
            "abandoned": self.abandoned,
            "last_sold_day": self.last_sold_day,
            "total_earned": self.total_earned,
            "skill": self.skill,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RivalClaim":
        return cls(
            npc_id=d["npc_id"],
            npc_name=d["npc_name"],
            world_x=d["world_x"],
            world_y=d["world_y"],
            area_x=d["area_x"],
            area_y=d["area_y"],
            daily_yield_oz=d["daily_yield_oz"],
            gold_stockpile_oz=d.get("gold_stockpile_oz", 0.0),
            equipment_level=d.get("equipment_level", 1),
            days_active=d.get("days_active", 0),
            abandoned=d.get("abandoned", False),
            last_sold_day=d.get("last_sold_day", 0),
            total_earned=d.get("total_earned", 0.0),
            skill=d.get("skill", 0.5),
        )


# ============================================================================
#  RIVAL PROSPECTOR SYSTEM
# ============================================================================

# Gold price per oz in 1849 California (~$16-$20)
_GOLD_PRICE_PER_OZ = 18.0

# Names for randomly generated rivals
_RIVAL_FIRST_NAMES = [
    "Jebediah", "Silas", "Ezekiel", "Cornelius", "Amos", "Hank",
    "Caleb", "Josiah", "Obadiah", "Rufus", "Levi", "Elijah",
    "Abel", "Solomon", "Bartholomew", "Jasper", "Cyrus", "Enoch",
    "Zeke", "Otis", "Hiram", "Thaddeus", "Gideon", "Phineas",
    "Claude", "Dutch", "Slim", "Red", "Big Tom", "Tennessee",
    "Pike", "Frenchy", "Lucky", "Whiskey", "Grizzly", "Stump",
]

_RIVAL_LAST_NAMES = [
    "McGraw", "Hawkins", "Bridger", "Sutter", "Boone", "Crockett",
    "Tanner", "Flint", "Garrett", "Holliday", "Earp", "Carson",
    "Donner", "Fremont", "Clemens", "Beckwourth", "Sublette",
    "Vasquez", "O'Brien", "Sullivan", "Johannsen", "Schmidt",
    "Larsen", "Chen", "Wong", "Garcia", "Gutierrez", "Moreno",
    "Kowalski", "Swenson", "Petrov", "MacTavish", "Finnegan",
]


class RivalProspectorSystem:
    """Manages NPC prospectors who compete with the player for gold."""

    def __init__(self):
        self.claims: List[RivalClaim] = []
        self._counter: int = 0

    def generate_rival(self, npc_id: str, npc_name: str,
                       wx: int, wy: int, ax: int, ay: int,
                       gold_grade: float, skill: float,
                       rng: random.Random) -> RivalClaim:
        """Create a new rival claim at the given location.
        gold_grade is the local richness (oz/day base), skill is 0-1."""
        self._counter += 1
        # Base yield: gold_grade scaled by skill, with some randomness
        base_yield = gold_grade * (0.5 + skill) * rng.uniform(0.6, 1.4)
        # Minimum yield so they at least get something
        base_yield = max(base_yield, 0.0001)

        claim = RivalClaim(
            npc_id=npc_id or f"rival_{self._counter}",
            npc_name=npc_name,
            world_x=wx,
            world_y=wy,
            area_x=ax,
            area_y=ay,
            daily_yield_oz=base_yield,
            skill=skill,
        )
        self.claims.append(claim)
        return claim

    def generate_random_rival(self, wx: int, wy: int, ax: int, ay: int,
                              gold_grade: float,
                              rng: random.Random) -> RivalClaim:
        """Generate a rival with a random name and skill level."""
        first = rng.choice(_RIVAL_FIRST_NAMES)
        last = rng.choice(_RIVAL_LAST_NAMES)
        name = f"{first} {last}"
        skill = rng.uniform(0.2, 0.9)
        return self.generate_rival("", name, wx, wy, ax, ay,
                                   gold_grade, skill, rng)

    def get_claims_near(self, wx: int, wy: int,
                        radius: int = 5) -> List[RivalClaim]:
        """Return all active rival claims within radius of world position."""
        nearby = []
        for c in self.claims:
            if c.abandoned:
                continue
            dx = abs(c.world_x - wx)
            dy = abs(c.world_y - wy)
            if dx <= radius and dy <= radius:
                nearby.append(c)
        return nearby

    def get_claim(self, npc_id: str) -> Optional[RivalClaim]:
        for c in self.claims:
            if c.npc_id == npc_id:
                return c
        return None

    def active_claims(self) -> List[RivalClaim]:
        return [c for c in self.claims if not c.abandoned]

    def tick_daily(self, day: int,
                   rng: random.Random) -> List[str]:
        """Daily simulation for all rival prospectors.
        Returns list of event messages for the player's log."""
        msgs = []

        for claim in self.claims:
            if claim.abandoned:
                continue

            claim.days_active += 1

            # ── Extract gold ──────────────────────────────────────────
            # Daily yield with random variance
            daily = claim.effective_yield * rng.uniform(0.3, 1.8)
            claim.gold_stockpile_oz += daily

            # Rare big find (1% chance per day)
            if rng.random() < 0.01:
                bonus = claim.effective_yield * rng.uniform(5, 20)
                claim.gold_stockpile_oz += bonus
                event = rng.choice(RIVAL_EVENTS["find_gold"])
                msgs.append(event.format(name=claim.npc_name))

            # ── Upgrade equipment (10% per month ~ 0.33% per day) ─────
            if claim.equipment_level < 3:
                upgrade_chance = 0.0033 * claim.days_active
                # More likely if they're making good money
                if claim.gold_stockpile_oz > 1.0:
                    upgrade_chance *= 2.0
                upgrade_chance = min(upgrade_chance, 0.10)
                if rng.random() < upgrade_chance:
                    claim.equipment_level += 1
                    event = rng.choice(RIVAL_EVENTS["upgrade_equipment"])
                    msgs.append(event.format(name=claim.npc_name))

            # ── Sell gold at town (roughly weekly) ────────────────────
            days_since_sold = day - claim.last_sold_day
            if days_since_sold >= 7 and claim.gold_stockpile_oz > 0.05:
                # Sell chance increases the longer they wait
                sell_chance = min(0.5, 0.1 * (days_since_sold - 6))
                if rng.random() < sell_chance:
                    sold_oz = claim.gold_stockpile_oz
                    earnings = sold_oz * _GOLD_PRICE_PER_OZ
                    claim.gold_stockpile_oz = 0.0
                    claim.last_sold_day = day
                    claim.total_earned += earnings
                    event = rng.choice(RIVAL_EVENTS["sell_gold"])
                    msgs.append(event.format(name=claim.npc_name))

            # ── Abandon poor claim ────────────────────────────────────
            # If yield is terrible and they've been at it a while
            if (claim.days_active > 14
                    and claim.effective_yield < 0.001
                    and rng.random() < 0.05):
                claim.abandoned = True
                event = rng.choice(RIVAL_EVENTS["abandon_claim"])
                msgs.append(event.format(name=claim.npc_name))
                continue

            # Also abandon if they've been here too long with poor returns
            if (claim.days_active > 60
                    and claim.total_earned < 20.0
                    and rng.random() < 0.10):
                claim.abandoned = True
                event = rng.choice(RIVAL_EVENTS["abandon_claim"])
                msgs.append(event.format(name=claim.npc_name))

        return msgs

    def check_claim_jump(self, player_wx: int, player_wy: int,
                         player_ax: int, player_ay: int,
                         day: int,
                         rng: random.Random) -> Optional[dict]:
        """Check if any nearby rival attempts to jump the player's claim.
        Returns an event dict if it happens, or None.

        Event dict keys:
            npc_id, npc_name, event_type ("claim_jump"),
            message, aggression (1-5), day
        """
        # Only rivals in the same world tile or adjacent
        nearby = self.get_claims_near(player_wx, player_wy, radius=2)
        if not nearby:
            return None

        for claim in nearby:
            if claim.abandoned:
                continue
            # Only desperate or greedy prospectors jump claims
            # Higher chance if: low yield, high skill, been around a while
            base_chance = 0.002  # ~0.2% per rival per day

            # Desperate — own claim is poor
            if claim.effective_yield < 0.01:
                base_chance *= 3.0

            # Greedy — thinks player's area is richer
            if claim.world_x == player_wx and claim.world_y == player_wy:
                base_chance *= 2.0
                if claim.area_x == player_ax and claim.area_y == player_ay:
                    base_chance *= 3.0  # same area — very tempting

            # Experienced prospectors more likely
            if claim.skill > 0.7:
                base_chance *= 1.5

            # Long timers get more desperate
            if claim.days_active > 30:
                base_chance *= 1.5

            base_chance = min(base_chance, 0.10)  # cap at 10%

            if rng.random() < base_chance:
                aggression = rng.randint(1, 5)
                event_msg = rng.choice(RIVAL_EVENTS["claim_jump_attempt"])
                return {
                    "npc_id": claim.npc_id,
                    "npc_name": claim.npc_name,
                    "event_type": "claim_jump",
                    "message": event_msg.format(name=claim.npc_name),
                    "aggression": aggression,
                    "day": day,
                    "world_x": claim.world_x,
                    "world_y": claim.world_y,
                    "area_x": claim.area_x,
                    "area_y": claim.area_y,
                }

        return None

    # ── Serialization ────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "counter": self._counter,
            "claims": [c.to_dict() for c in self.claims],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RivalProspectorSystem":
        system = cls()
        system._counter = d.get("counter", 0)
        for cd in d.get("claims", []):
            system.claims.append(RivalClaim.from_dict(cd))
        return system
