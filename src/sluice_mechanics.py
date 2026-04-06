"""
src/sluice_mechanics.py

Sluice box — buildable object.
Player feeds paydirt → sluice processes it → player does clean-out.
Recovery = actual tile concentration × sluice efficiency.
"""

from dataclasses import dataclass
import random
from typing import Optional, Tuple

from src.volume_gold import GoldColumn
from src.fluid_system import FluidSystem


@dataclass
class SluiceBox:
    """A placed sluice box."""
    x: int
    y: int
    length: int = 12                    # feet
    riffle_type: str = "wooden"         # "wooden", "blanket", "mercury"
    accumulated_paydirt: float = 0.0    # cubic yards fed in
    accumulated_gold: float = 0.0       # gold currently trapped (not cleaned out yet)

    @property
    def riffle_capacity(self) -> float:
        """Max gold (oz) the riffles can hold before overflow.

        Historical basis:
        - A 12-ft sluice with wooden riffles (1-inch crossbars every 6 inches)
          traps gold in the dead zones behind each riffle. Each riffle pocket
          holds roughly 1-2 cubic inches of heavy concentrate (gold + black
          sand + mercury if used). With 24 riffles, total capacity is about
          1.0-1.5 troy oz of gold before the pockets are full and new gold
          washes over.
        - Blanket (carpet/burlap under riffles) catches fine flour gold that
          wooden riffles miss. Adds ~30% capacity.
        - Mercury (quicksilver in riffle pockets) amalgamates gold on contact.
          Dramatically increases capacity — mercury can hold 2-3× its weight
          in gold. But mercury poisoning is the price.
        - Rockers are smaller (4-5 ft), fewer riffles, need cleanout more often.
        - Long toms (16-20 ft) have more riffles and a perforated grizzly plate
          that pre-sorts material. Higher capacity.
        """
        base = 0.08 * self.length  # ~1.0 oz for 12-ft sluice
        if self.riffle_type == "blanket":
            base *= 1.3
        elif self.riffle_type == "mercury":
            base *= 2.5  # mercury dramatically increases capacity
        return base

    @property
    def riffles_full_pct(self) -> float:
        """How full the riffles are (0.0 to 1.0+)."""
        cap = self.riffle_capacity
        if cap <= 0:
            return 1.0
        return self.accumulated_gold / cap

    @property
    def riffles_need_cleanout(self) -> bool:
        """True when riffles are near capacity — gold starting to wash over."""
        return self.riffles_full_pct >= 0.85


class SluiceMechanics:
    """
    Gold recovery = (gold in fed material) × sluice efficiency.
    Efficiency depends on length, riffles, water flow, and skill.
    """

    @staticmethod
    def calculate_efficiency(sluice: SluiceBox, water_flow: int, placer_skill: int) -> float:
        """Efficiency = base (length + riffles) × water flow × skill."""
        # Base efficiency from construction
        base = 0.55 + (sluice.length / 20.0) * 0.35          # longer sluice = better
        if sluice.riffle_type == "blanket":
            base += 0.12
        elif sluice.riffle_type == "mercury":
            base += 0.25

        # Water flow factor (needs good flow)
        flow_factor = min(1.0, water_flow / 7.0) * 0.95 + 0.05

        # Skill bonus
        skill_factor = 1.0 + (placer_skill * 0.085)

        return base * flow_factor * skill_factor

    @staticmethod
    def feed_paydirt(local_map, sluice_id: int, volume_cy: float, placer_skill: int) -> float:
        """
        Player shovels paydirt into the sluice.
        Gold is trapped based on actual tile concentration and current efficiency.
        """
        sluice = local_map.structures.get(sluice_id)
        if not sluice or not isinstance(sluice, SluiceBox):
            return 0.0

        tile = local_map.tile_at(sluice.x, sluice.y)
        if not tile.gold_column:
            return 0.0

        # Get water flow
        water_flow = 0
        if local_map.fluid_system:
            for dx, dy in [(0,1),(0,-1),(1,0),(-1,0)]:
                nx, ny = sluice.x + dx, sluice.y + dy
                if local_map.in_bounds(nx, ny):
                    water_flow = max(water_flow, local_map.fluid_system.get_fluid_level(nx, ny))

        # Calculate efficiency for this run
        efficiency = SluiceMechanics.calculate_efficiency(sluice, water_flow, placer_skill)

        # Extract gold from the column at current depth
        gold_in_material = tile.gold_column.remove_volume(volume_cy)

        # Riffle overflow — if riffles are near capacity, efficiency drops
        # Gold starts washing over the end. This is the historical reason
        # you clean out frequently in rich ground.
        overflow_penalty = 1.0
        if sluice.riffles_full_pct >= 1.0:
            overflow_penalty = 0.2  # 80% of gold washing away
        elif sluice.riffles_full_pct >= 0.85:
            overflow_penalty = 0.6  # losing 40%
        elif sluice.riffles_full_pct >= 0.7:
            overflow_penalty = 0.85  # losing 15%

        # Gold actually trapped in sluice
        gold_trapped = gold_in_material * efficiency * overflow_penalty

        sluice.accumulated_paydirt += volume_cy
        sluice.accumulated_gold += gold_trapped

        # Consume water
        if local_map.fluid_system and water_flow > 0:
            local_map.fluid_system.remove_fluid(sluice.x, sluice.y, amount=3)

        return gold_trapped

    @staticmethod
    def clean_out(local_map, sluice_id: int, placer_skill: int) -> float:
        """Player cleans out the sluice and recovers the trapped gold."""
        sluice = local_map.structures.get(sluice_id)
        if not sluice or not isinstance(sluice, SluiceBox):
            return 0.0

        gold_recovered = sluice.accumulated_gold

        # Final skill bonus on clean-out
        gold_recovered *= (1.0 + placer_skill * 0.07)

        # Reset sluice
        sluice.accumulated_gold = 0.0
        sluice.accumulated_paydirt = 0.0

        return gold_recovered

    @staticmethod
    def get_status_message(sluice: SluiceBox) -> str:
        pct = sluice.riffles_full_pct
        if pct >= 1.0:
            return (f"Riffles are OVERLOADED — gold is washing over the end! "
                    f"Clean out immediately!")
        if pct >= 0.85:
            return (f"Riffles are nearly full — you can see gold piling up "
                    f"against the crossbars. Clean out soon or lose gold.")
        if pct >= 0.5:
            return (f"Good concentrates building in the riffles. "
                    f"{sluice.accumulated_paydirt:.1f} yards processed.")
        if sluice.accumulated_paydirt > 0:
            return (f"Sluice running. {sluice.accumulated_paydirt:.1f} yards "
                    f"processed. Riffles look fine.")
        return "Sluice is clean and ready."