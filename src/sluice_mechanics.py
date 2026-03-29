"""
src/sluice_mechanics.py

Sluice box — buildable object.
Player feeds paydirt → sluice processes it → player does clean-out.
Recovery = actual tile concentration × sluice efficiency.
"""

from dataclasses import dataclass
import random
from typing import Optional, Tuple

from src.volume_gold import VolumeGoldSystem, GoldColumn
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
        gold_in_material = VolumeGoldSystem.remove_volume(tile.gold_column, volume_cy)

        # Gold actually trapped in sluice
        gold_trapped = gold_in_material * efficiency

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
        if sluice.accumulated_gold > 1.0:
            return f"Sluice is heavy — {sluice.accumulated_gold:.3f} oz of gold trapped inside."
        elif sluice.accumulated_gold > 0.3:
            return f"Good accumulation — {sluice.accumulated_gold:.3f} oz ready for clean-out."
        elif sluice.accumulated_paydirt > 0:
            return f"Sluice has processed {sluice.accumulated_paydirt:.1f} cubic yards of paydirt."
        return "Sluice is clean and ready to be fed."