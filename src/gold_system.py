"""
src/gold_system.py

Gold generation, depletion, and placer mechanics for American Prospector.
"""

from dataclasses import dataclass
from typing import Tuple, Optional
import random


@dataclass
class GoldTileData:
    """Per-tile gold information (stored on LocalTile or separately)."""
    surface_grade: float = 0.0      # What you see from surface panning
    pay_grade: float = 0.0          # Deeper, richer layer revealed by digging
    depleted: float = 0.0           # How much has been worked out (0.0 = pristine)
    has_nugget_potential: bool = False


class GoldSystem:
    """Handles gold placement, depletion, nuggets, and pay streaks."""

    @staticmethod
    def generate_initial_gold(region_name: str, local_x: int, local_y: int, rng: random.Random) -> GoldTileData:
        """Generate realistic gold for a tile based on region."""
        data = GoldTileData()

        base = 0.0
        if "Sierra Nevada" in region_name or "California" in region_name:
            base = 0.65
        elif "Rocky Mountains" in region_name:
            base = 0.35
        elif "Great Plains" in region_name:
            base = 0.05
        elif "Alaska" in region_name:
            base = 0.15
        else:
            base = 0.20

        # Surface grade is usually lower
        data.surface_grade = base * rng.uniform(0.3, 0.8)

        # Pay grade (revealed by digging) is higher, especially in good regions
        data.pay_grade = base * rng.uniform(0.8, 1.4)

        # Some tiles have nugget potential (much higher in 1840s California)
        if "Sierra Nevada" in region_name or "California" in region_name:
            data.has_nugget_potential = rng.random() < 0.25
        else:
            data.has_nugget_potential = rng.random() < 0.08

        return data

    @staticmethod
    def pan_result(tile_data: GoldTileData, placer_skill: int, rng: random.Random) -> Tuple[float, bool]:
        """Calculate gold from one pan."""
        # Surface panning gets mostly surface grade
        grade = tile_data.surface_grade * (1.0 - tile_data.depleted * 0.6)

        if grade < 0.05:
            return 0.0, False

        # Skill helps
        skill_mult = 1.0 + (placer_skill * 0.12)

        # Random variation
        variation = rng.uniform(0.65, 1.35)

        oz = grade * skill_mult * variation * rng.uniform(0.001, 0.08)

        # Nugget chance
        if tile_data.has_nugget_potential and rng.random() < 0.18:
            nugget = rng.uniform(0.1, 1.8)
            oz += nugget

        # Slight depletion
        tile_data.depleted = min(1.0, tile_data.depleted + 0.008)

        return max(0.0, oz), oz > 0.0005

    @staticmethod
    def dig_reveal(tile_data: GoldTileData, dig_depth: int, rng: random.Random) -> float:
        """When player digs deeper, reveal more of the pay grade."""
        if dig_depth < 2:
            return tile_data.surface_grade

        reveal = min(1.0, (dig_depth - 1) * 0.25)
        effective_grade = (tile_data.surface_grade * (1 - reveal)) + (tile_data.pay_grade * reveal)

        # Depletion also applies to deeper layers
        effective_grade *= (1.0 - tile_data.depleted * 0.4)

        return effective_grade