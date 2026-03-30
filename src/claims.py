"""
src/claims.py

Mining claim staking and management system.

Historical accuracy (1840s California):
- Placer claims: 100ft along the creek, bank to bank
- Staked with wooden stakes at corners + written notice
- Must be worked regularly (1 day per week minimum) or abandoned
- Register at land office in town for legal protection ($5 fee)
- Claim jumping is a crime (severity 3 in legal.py)
- Other prospectors respect staked claims (mostly)
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple


@dataclass
class MiningClaim:
    """A staked mining claim on the local map."""
    claim_id: int
    owner: str                  # player name or NPC name
    world_x: int
    world_y: int
    area_x: int
    area_y: int
    center_x: int               # center of claim on local map
    center_y: int
    radius: int = 10            # claim extends this many tiles from center
    staked_day: int = 0         # game day when staked
    registered: bool = False    # registered at land office?
    last_worked_day: int = 0    # must work regularly
    gold_extracted_oz: float = 0.0  # total gold pulled from this claim
    name: str = ""              # optional name ("Bridger's Bend")
    abandoned: bool = False

    def is_at(self, wx: int, wy: int, ax: int, ay: int) -> bool:
        return (self.world_x == wx and self.world_y == wy
                and self.area_x == ax and self.area_y == ay)

    def contains(self, local_x: int, local_y: int) -> bool:
        """Check if a local map position is within this claim."""
        return (abs(local_x - self.center_x) <= self.radius
                and abs(local_y - self.center_y) <= self.radius)

    def days_since_worked(self, current_day: int) -> int:
        return current_day - self.last_worked_day

    def is_abandoned(self, current_day: int) -> bool:
        """Claim is abandoned if not worked for 7+ days and not registered,
        or 30+ days if registered."""
        limit = 30 if self.registered else 7
        return self.days_since_worked(current_day) > limit

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "owner": self.owner,
            "world_x": self.world_x, "world_y": self.world_y,
            "area_x": self.area_x, "area_y": self.area_y,
            "center_x": self.center_x, "center_y": self.center_y,
            "radius": self.radius,
            "staked_day": self.staked_day,
            "registered": self.registered,
            "last_worked_day": self.last_worked_day,
            "gold_extracted_oz": self.gold_extracted_oz,
            "name": self.name,
            "abandoned": self.abandoned,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MiningClaim":
        return cls(**d)


class ClaimManager:
    """Manages all mining claims (player and NPC)."""

    def __init__(self):
        self.claims: List[MiningClaim] = []
        self._next_id = 1

    def stake_claim(self, owner: str, wx: int, wy: int, ax: int, ay: int,
                    cx: int, cy: int, current_day: int,
                    name: str = "") -> Tuple[Optional[MiningClaim], str]:
        """Attempt to stake a new claim. Returns (claim, message)."""
        # Check for existing claims at this spot
        for c in self.claims:
            if c.is_at(wx, wy, ax, ay) and c.contains(cx, cy) and not c.abandoned:
                if c.owner == owner:
                    return None, "You already have a claim here."
                return None, f"This ground is already claimed by {c.owner}."

        claim = MiningClaim(
            claim_id=self._next_id,
            owner=owner,
            world_x=wx, world_y=wy,
            area_x=ax, area_y=ay,
            center_x=cx, center_y=cy,
            staked_day=current_day,
            last_worked_day=current_day,
            name=name or f"Claim #{self._next_id}",
        )
        self._next_id += 1
        self.claims.append(claim)
        return claim, f"Claim staked! {claim.name} — {claim.radius*2}x{claim.radius*2} tiles centered here."

    def register_claim(self, claim_id: int) -> Tuple[bool, str]:
        """Register a claim at the land office. Provides legal protection."""
        claim = self.get(claim_id)
        if not claim:
            return False, "No such claim."
        if claim.registered:
            return False, "Already registered."
        claim.registered = True
        return True, f"{claim.name} registered. Legal protection for 30 days between workings."

    def work_claim(self, claim_id: int, current_day: int, gold_oz: float = 0):
        """Record that a claim was worked today."""
        claim = self.get(claim_id)
        if claim:
            claim.last_worked_day = current_day
            claim.gold_extracted_oz += gold_oz

    def get(self, claim_id: int) -> Optional[MiningClaim]:
        for c in self.claims:
            if c.claim_id == claim_id:
                return c
        return None

    def claim_at(self, wx: int, wy: int, ax: int, ay: int,
                 lx: int, ly: int) -> Optional[MiningClaim]:
        """Find the claim covering a specific local position."""
        for c in self.claims:
            if c.is_at(wx, wy, ax, ay) and c.contains(lx, ly) and not c.abandoned:
                return c
        return None

    def player_claims(self, owner: str) -> List[MiningClaim]:
        return [c for c in self.claims if c.owner == owner and not c.abandoned]

    def tick_daily(self, current_day: int) -> List[str]:
        """Daily check for abandoned claims. Returns messages."""
        msgs = []
        for c in self.claims:
            if c.abandoned:
                continue
            if c.is_abandoned(current_day):
                c.abandoned = True
                msgs.append(f"Claim \"{c.name}\" abandoned — not worked in "
                            f"{c.days_since_worked(current_day)} days.")
        return msgs

    def to_dict(self) -> dict:
        return {
            "next_id": self._next_id,
            "claims": [c.to_dict() for c in self.claims],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ClaimManager":
        mgr = cls()
        mgr._next_id = d.get("next_id", 1)
        for cd in d.get("claims", []):
            mgr.claims.append(MiningClaim.from_dict(cd))
        return mgr
