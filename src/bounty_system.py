"""Bounty hunting system for the Gold Rush roguelike.

Players can pick up bounties from town boards, track fugitives across the
world map using trail clues, and turn them in dead or alive for reward money.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import random
import math

# ---------------------------------------------------------------------------
# Data tables
# ---------------------------------------------------------------------------

FUGITIVE_NAMES: List[str] = [
    "Black Bart",
    "Rattlesnake Pete",
    "One-Eyed Jack",
    "Hatchet Jim",
    "Dead-Eye Dan",
    "Soapy Smith",
    "Dutch Henry",
    "Cherokee Bill",
    "Curly Bill Brocius",
    "Billy the Kid",
    "Joaquin Murieta",
    "Tom Bell",
    "Tiburcio Vasquez",
    "Jack Slade",
    "Boone Helm",
    "Red Cloud McGraw",
    "Whiskey Joe",
    "Iron Mike Donovan",
    "Coyote Cal",
    "Sidewinder Sam",
    "Crooked Eli",
    "Mad Dog Malone",
    "Preacher Cole",
    "Big Nose George",
    "Bloody Bill Anderson",
    "Dynamite Dave",
    "Leadville Lou",
    "Shanghai Kelly",
    "Muleskin Jack",
    "Peg-Leg Pete",
    "Gambler Gus",
    "Yellowknife Hank",
    "Scorpion Ed",
    "Tin Pan Charlie",
    "Flapjack Frank",
]

CRIME_REWARDS: Dict[str, tuple] = {
    "murder":         (200, 500),
    "robbery":        (100, 300),
    "horse_theft":    (50, 150),
    "arson":          (75, 200),
    "claim_jumping":  (25, 100),
    "counterfeiting": (100, 250),
}

# Difficulty floors per crime — more violent crimes attract tougher outlaws.
_CRIME_DIFFICULTY: Dict[str, tuple] = {
    "murder":         (3, 5),
    "robbery":        (2, 4),
    "horse_theft":    (1, 3),
    "arson":          (2, 4),
    "claim_jumping":  (1, 2),
    "counterfeiting": (2, 3),
}

PHYSICAL_DESCRIPTIONS: List[str] = [
    "tall with a scar across his left cheek",
    "stocky build, red beard",
    "thin and wiry, missing two front teeth",
    "heavyset, bald head, full black beard",
    "average height, pockmarked face",
    "short, dark complexion, gold tooth",
    "lanky, sandy hair, walks with a limp",
    "broad-shouldered, broken nose, tattoo on right hand",
    "slight build, spectacles, well-spoken",
    "barrel-chested, long grey hair tied back",
    "muscular, clean-shaven, burn marks on neck",
    "gaunt face, deep-set eyes, nervous twitch",
    "tall and lean, wears a duster, hawk nose",
    "squat, bowlegged, thick mustache",
    "young-looking, freckled, deceptively fast",
    "weathered skin, slouch hat, gravelly voice",
    "one-armed, carries a sawed-off shotgun",
    "olive-skinned, pencil mustache, silver spurs",
    "ruddy complexion, gap-toothed grin",
    "pale and gaunt, sunken cheeks, long sideburns",
]

# Clue templates — {name} and {dir} are filled at runtime.
_CLUE_TEMPLATES: List[str] = [
    "A miner saw someone matching {name}'s description heading {dir}.",
    "Fresh campfire ashes — someone passed through here recently.",
    "Boot prints in the mud, heading {dir}.",
    "A shopkeeper recalls selling ammunition to a stranger matching the poster.",
    "Discarded whiskey bottle and tobacco pouch found along the {dir} trail.",
    "Locals report a stranger asking about river crossings to the {dir}.",
    "A stagecoach driver remembers a lone rider heading {dir} two days ago.",
    "Wanted poster torn down here — someone doesn't want to be found.",
    "Horse droppings and a cold fire pit — the trail leads {dir}.",
    "A prospector heard gunshots to the {dir} last night.",
]

# Cardinal direction names keyed by (dx_sign, dy_sign).
_DIRECTION_NAMES: Dict[tuple, str] = {
    (0, -1):  "north",
    (1, -1):  "northeast",
    (1, 0):   "east",
    (1, 1):   "southeast",
    (0, 1):   "south",
    (-1, 1):  "southwest",
    (-1, 0):  "west",
    (-1, -1): "northwest",
}


def _sign(n: int) -> int:
    if n > 0:
        return 1
    if n < 0:
        return -1
    return 0


def _direction_toward(px: int, py: int, tx: int, ty: int) -> str:
    """Return a cardinal/ordinal direction string from (px,py) toward (tx,ty)."""
    dx = _sign(tx - px)
    dy = _sign(ty - py)
    if dx == 0 and dy == 0:
        return "nearby"
    return _DIRECTION_NAMES.get((dx, dy), "unknown")


# ---------------------------------------------------------------------------
# Bounty dataclass
# ---------------------------------------------------------------------------

@dataclass
class Bounty:
    """A single bounty poster."""

    bounty_id: int
    target_name: str
    target_npc_id: str
    crime: str
    reward: float
    posted_day: int
    posted_town: str
    last_seen_wx: int
    last_seen_wy: int
    difficulty: int
    description: str
    status: str = "active"
    trail_strength: float = 1.0
    clues: List[str] = field(default_factory=list)

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "bounty_id":    self.bounty_id,
            "target_name":  self.target_name,
            "target_npc_id": self.target_npc_id,
            "crime":        self.crime,
            "reward":       self.reward,
            "posted_day":   self.posted_day,
            "posted_town":  self.posted_town,
            "last_seen_wx": self.last_seen_wx,
            "last_seen_wy": self.last_seen_wy,
            "difficulty":   self.difficulty,
            "description":  self.description,
            "status":       self.status,
            "trail_strength": self.trail_strength,
            "clues":        list(self.clues),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Bounty":
        return cls(
            bounty_id=d["bounty_id"],
            target_name=d["target_name"],
            target_npc_id=d["target_npc_id"],
            crime=d["crime"],
            reward=d["reward"],
            posted_day=d["posted_day"],
            posted_town=d["posted_town"],
            last_seen_wx=d["last_seen_wx"],
            last_seen_wy=d["last_seen_wy"],
            difficulty=d["difficulty"],
            description=d["description"],
            status=d.get("status", "active"),
            trail_strength=d.get("trail_strength", 1.0),
            clues=list(d.get("clues", [])),
        )


# ---------------------------------------------------------------------------
# BountyBoard
# ---------------------------------------------------------------------------

class BountyBoard:
    """Manages all bounties across every town."""

    def __init__(self) -> None:
        self.bounties: List[Bounty] = []
        self._counter: int = 0

    # -- generation --------------------------------------------------------

    def generate_bounty(
        self,
        day: int,
        town: str,
        rng: Optional[random.Random] = None,
        year: int = 1849,
    ) -> Bounty:
        """Create a random bounty and add it to the board."""
        if rng is None:
            rng = random.Random()

        self._counter += 1

        # Era-appropriate crimes — claim jumping is a Gold Rush thing,
        # counterfeiting requires printing presses
        available_crimes = list(CRIME_REWARDS.keys())
        if year < 1840:
            available_crimes = [c for c in available_crimes
                                if c not in ("claim_jumping", "counterfeiting")]
        if year < 1800:
            # Frontier justice — simpler crimes
            available_crimes = ["murder", "robbery", "horse_theft", "arson"]
        crime = rng.choice(available_crimes)
        min_r, max_r = CRIME_REWARDS[crime]
        # Round reward to nearest $5 for a period-appropriate feel.
        reward = round(rng.uniform(min_r, max_r) / 5) * 5
        reward = float(max(min_r, min(max_r, reward)))

        diff_lo, diff_hi = _CRIME_DIFFICULTY[crime]
        difficulty = rng.randint(diff_lo, diff_hi)

        name = rng.choice(FUGITIVE_NAMES)
        desc = rng.choice(PHYSICAL_DESCRIPTIONS)
        npc_id = f"fugitive_{self._counter}"

        # Scatter the fugitive somewhere on the world map near the town.
        # Callers can override last_seen_wx/wy later if they have real data.
        last_wx = rng.randint(0, 59)
        last_wy = rng.randint(0, 59)

        bounty = Bounty(
            bounty_id=self._counter,
            target_name=name,
            target_npc_id=npc_id,
            crime=crime,
            reward=reward,
            posted_day=day,
            posted_town=town,
            last_seen_wx=last_wx,
            last_seen_wy=last_wy,
            difficulty=difficulty,
            description=desc,
        )
        self.bounties.append(bounty)
        return bounty

    # -- player actions ----------------------------------------------------

    def accept_bounty(self, bounty_id: int) -> Optional[Bounty]:
        """Mark a bounty as accepted by the player.

        Returns the bounty on success, or ``None`` if not found / not active.
        """
        for b in self.bounties:
            if b.bounty_id == bounty_id and b.status == "active":
                b.status = "accepted"
                return b
        return None

    def turn_in(self, bounty_id: int, day: int) -> Optional[float]:
        """Turn in a captured or killed fugitive.

        Returns the dollar reward on success, or ``None`` if the bounty cannot
        be turned in.
        """
        valid_statuses = ("captured", "killed")
        for b in self.bounties:
            if b.bounty_id == bounty_id and b.status in valid_statuses:
                b.status = "turned_in"
                return b.reward
        return None

    # -- queries -----------------------------------------------------------

    def get_active(self, town: Optional[str] = None) -> List[Bounty]:
        """Return all active (unclaimed) bounties, optionally for one town."""
        results = [b for b in self.bounties if b.status == "active"]
        if town is not None:
            results = [b for b in results if b.posted_town == town]
        return results

    def get_accepted(self) -> List[Bounty]:
        """Return bounties the player has accepted or is tracking."""
        return [
            b for b in self.bounties
            if b.status in ("accepted", "tracking")
        ]

    # -- daily tick --------------------------------------------------------

    def tick_daily(self, day: int, rng: Optional[random.Random] = None) -> None:
        """Advance one day: decay trails, expire old bounties, maybe spawn new ones."""
        if rng is None:
            rng = random.Random()

        for b in self.bounties:
            if b.status in ("active", "accepted", "tracking"):
                # Trail decays faster for harder targets.
                decay = 0.05 + (b.difficulty - 1) * 0.01
                b.trail_strength = max(0.0, b.trail_strength - decay)

                # Expire bounties older than 90 days.
                if day - b.posted_day > 90:
                    b.status = "expired"

    # -- tracking ----------------------------------------------------------

    def get_tracking_hint(
        self,
        bounty: Bounty,
        player_wx: int,
        player_wy: int,
        rng: Optional[random.Random] = None,
    ) -> Optional[str]:
        """Return a directional clue toward the fugitive.

        The chance of receiving a useful hint scales with ``trail_strength``
        and inversely with ``difficulty``.  A failed check returns ``None``.

        Parameters
        ----------
        bounty : Bounty
            The bounty being tracked.
        player_wx, player_wy : int
            Player's current world-map coordinates.
        rng : random.Random, optional
            RNG instance.

        Returns
        -------
        str or None
            A narrative hint string, or ``None`` if the trail is too cold.
        """
        if rng is None:
            rng = random.Random()

        # Chance of success: trail_strength * (1 - 0.1 * difficulty)
        # At difficulty 5 and trail 1.0 this gives 50 %; at trail 0.2 it's 10 %.
        chance = bounty.trail_strength * (1.0 - 0.1 * bounty.difficulty)
        if rng.random() > chance:
            return None

        direction = _direction_toward(
            player_wx, player_wy,
            bounty.last_seen_wx, bounty.last_seen_wy,
        )

        template = rng.choice(_CLUE_TEMPLATES)
        hint = template.format(name=bounty.target_name, dir=direction)

        # Record the clue on the bounty so the player can review later.
        bounty.clues.append(hint)
        if bounty.status == "accepted":
            bounty.status = "tracking"

        return hint

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "bounties": [b.to_dict() for b in self.bounties],
            "_counter": self._counter,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BountyBoard":
        board = cls()
        board._counter = d.get("_counter", 0)
        board.bounties = [Bounty.from_dict(bd) for bd in d.get("bounties", [])]
        return board
