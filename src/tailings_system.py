"""
src/tailings_system.py

Tailings pile mechanic for American Prospector.
Fully factors in:
- Stream vs player-built pile
- Gravity-fed vs pump-fed sluice
- Settling pond option
- Gold lost in tails (recoverable by re-panning)
- Efficiency calculation (player can math it out)
"""

from dataclasses import dataclass
import random
from typing import Optional, Tuple

from src.volume_gold import VolumeGoldSystem, GoldColumn
from src.fluid_system import FluidSystem, FluidType


@dataclass
class TailingsPile:
    """A visible tailings/spoil pile on the local map."""
    x: int
    y: int
    volume_cy: float = 0.0          # cubic yards of material
    trapped_gold_oz: float = 0.0    # gold lost in the tails
    pile_type: str = "dry"          # "dry", "stream", "settling_pond"
    is_settling_pond: bool = False
    depletion: float = 0.0          # 0.0 = fresh tails, 1.0 = fully re-worked


class TailingsSystem:
    """
    Handles tailings from sluices and digging.
    Player can re-pan tailings to recover lost gold and evaluate sluice efficiency.
    """

    @staticmethod
    def create_from_sluice(local_map, sluice_x: int, sluice_y: int, 
                           volume_cy: float, gold_lost_oz: float,
                           is_stream: bool = False, has_settling_pond: bool = False) -> int:
        """
        Creates a tailings pile at/near the sluice output.
        Returns the pile ID in local_map.structures
        """
        # Decide pile location
        if is_stream:
            # Dump into the actual stream
            px, py = sluice_x, sluice_y + 1   # downstream
            pile_type = "stream"
        else:
            # Player-built dry pile (adjacent tile)
            px, py = sluice_x + 1, sluice_y
            pile_type = "dry"

        # Adjust for settling pond
        if has_settling_pond:
            pile_type = "settling_pond"

        pile_id = local_map._next_id
        local_map.structures[pile_id] = TailingsPile(
            x=px,
            y=py,
            volume_cy=volume_cy,
            trapped_gold_oz=gold_lost_oz,
            pile_type=pile_type,
            is_settling_pond=has_settling_pond,
        )
        local_map._next_id += 1

        # If dumped in stream, some gold is permanently lost
        if pile_type == "stream":
            local_map.structures[pile_id].trapped_gold_oz *= 0.65   # 35% lost to river

        return pile_id

    @staticmethod
    def re_pan_tailings(local_map, pile_id: int, volume_cy: float, placer_skill: int, rng: random.Random) -> float:
        """
        Player re-pans a tailings pile.
        Returns recovered gold.
        """
        pile = local_map.structures.get(pile_id)
        if not pile or not isinstance(pile, TailingsPile):
            return 0.0

        if pile.volume_cy <= 0:
            return 0.0

        # Take the requested volume
        take = min(volume_cy, pile.volume_cy)
        fraction = take / pile.volume_cy

        raw_gold = pile.trapped_gold_oz * fraction

        # Deplete the pile by the raw fraction (before skill/pond bonuses)
        pile.volume_cy -= take
        pile.trapped_gold_oz -= raw_gold
        pile.trapped_gold_oz = max(0.0, pile.trapped_gold_oz)
        pile.depletion = min(1.0, pile.depletion + fraction * 0.8)

        # Skill helps recover more from tails (applied to returned amount only)
        gold_recovered = raw_gold * (1.0 + placer_skill * 0.11)

        # If it's a settling pond, recovery is higher
        if pile.is_settling_pond:
            gold_recovered *= 1.25

        return max(0.0, gold_recovered)

    @staticmethod
    def get_tailings_status(pile: TailingsPile) -> str:
        if pile.volume_cy <= 0:
            return "The tailings pile has been fully reworked."
        
        remaining_gold = pile.trapped_gold_oz
        if remaining_gold > 0.5:
            return f"Rich tailings pile — {remaining_gold:.3f} oz still recoverable."
        elif remaining_gold > 0.1:
            return f"Visible color in the tailings — {remaining_gold:.3f} oz left."
        else:
            return f"Tailings pile ({pile.volume_cy:.1f} cy) — lean but pannable."

    @staticmethod
    def calculate_sluice_efficiency(original_gold: float, recovered_from_tails: float, sluice_gold: float) -> float:
        """
        Player can do the math:
        Efficiency = (sluice_gold) / (sluice_gold + gold_lost_in_tails)
        """
        total_gold = sluice_gold + recovered_from_tails
        if total_gold == 0:
            return 0.0
        return (sluice_gold / total_gold) * 100.0
    