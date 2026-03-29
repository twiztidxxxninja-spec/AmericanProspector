"""
src/vertical_gold.py

Geologically accurate vertical gold distribution for placer mining.
Real-world placer gold sinks through gravel over time and concentrates at bedrock.
"""

from dataclasses import dataclass
import random
from typing import Optional


@dataclass
class VerticalGoldProfile:
    """
    Represents the vertical distribution of gold in a single tile.
    Surface = easy panning (often disappointing)
    Deeper layers = richer pay streaks revealed by digging
    """
    surface_grade: float = 0.0      # What you get from shallow panning (0.0-1.0)
    mid_grade: float = 0.0          # 2-5 digs deep
    pay_grade: float = 0.0          # Near bedrock — the real prize
    bedrock_trap: float = 0.0       # Extra concentration in cracks/pockets
    depletion: float = 0.0          # 0.0 = virgin ground, 1.0 = worked out
    has_nugget_pocket: bool = False # Chance of larger nuggets at depth


class VerticalGoldSystem:
    """
    Models real placer gold behavior:
    - Gold is heavy → sinks through gravel over geological time
    - Richest concentrations are usually at or near bedrock
    - Surface gravel is often "lean" or "color only"
    - Digging test pits reveals whether there's a pay streak below
    """

    @staticmethod
    def generate_profile(region_name: str, gold_bias: float, rng: random.Random) -> VerticalGoldProfile:
        profile = VerticalGoldProfile()

        # Base richness from region
        base = gold_bias

        if "Sierra Nevada" in region_name or "California" in region_name:
            base *= 1.35   # Historically very rich
        elif "Rocky Mountains" in region_name:
            base *= 0.85
        elif "Great Plains" in region_name:
            base *= 0.15
        elif "Alaska" in region_name:
            base *= 0.65

        # Surface layer — usually disappointing (what most casual panning finds)
        profile.surface_grade = base * rng.uniform(0.25, 0.65)

        # Mid layer — improves with digging
        profile.mid_grade = base * rng.uniform(0.55, 0.95)

        # Pay layer (near bedrock) — the real prize
        profile.pay_grade = base * rng.uniform(0.85, 1.45)

        # Bedrock traps — gold collects in cracks and pockets
        profile.bedrock_trap = base * rng.uniform(1.1, 2.0)

        # Some tiles have nugget pockets (more common in early 1849 California)
        if "Sierra Nevada" in region_name or "California" in region_name:
            profile.has_nugget_pocket = rng.random() < 0.28
        else:
            profile.has_nugget_pocket = rng.random() < 0.09

        return profile

    @staticmethod
    def get_effective_grade(profile: VerticalGoldProfile, dig_depth: int, placer_skill: int, rng: random.Random) -> float:
        """
        Returns the gold grade revealed at current dig depth.
        dig_depth = 0 → surface panning
        dig_depth = 3–6 → mid layer
        dig_depth = 8+ → near bedrock
        """
        if dig_depth <= 1:
            grade = profile.surface_grade
        elif dig_depth <= 5:
            # Linear interpolation from surface to mid
            t = (dig_depth - 1) / 4.0
            grade = profile.surface_grade * (1 - t) + profile.mid_grade * t
        else:
            # Approaching pay layer + bedrock trap
            t = min(1.0, (dig_depth - 5) / 8.0)
            grade = profile.mid_grade * (1 - t) + profile.pay_grade * t
            # Bonus for reaching bedrock
            if dig_depth >= 9:
                grade = (grade + profile.bedrock_trap) * 0.75

        # Skill helps read and recover better
        skill_mult = 1.0 + (placer_skill * 0.09)

        # Random daily variation
        variation = rng.uniform(0.75, 1.25)

        # Depletion reduces yield over time
        final_grade = grade * skill_mult * variation * (1.0 - profile.depletion * 0.7)

        return max(0.0, final_grade)

    @staticmethod
    def extract_gold(profile: VerticalGoldProfile, dig_depth: int, placer_skill: int, rng: random.Random) -> float:
        """Calculate actual ounces recovered from one pan at current depth."""
        grade = VerticalGoldSystem.get_effective_grade(profile, dig_depth, placer_skill, rng)

        # Base ounces per pan (very small numbers)
        base_oz = grade * rng.uniform(0.001, 0.085)

        # Nugget chance at depth
        if profile.has_nugget_pocket and dig_depth >= 4 and rng.random() < 0.22:
            nugget_size = rng.uniform(0.12, 2.5)   # bigger nuggets deeper
            base_oz += nugget_size

        # Deplete the tile slightly
        profile.depletion = min(1.0, profile.depletion + 0.012)

        return max(0.0, base_oz)

    @staticmethod
    def get_nugget_chance(profile: VerticalGoldProfile, dig_depth: int, era_year: int) -> float:
        """Higher nugget chance in early Gold Rush years."""
        if era_year > 1855:
            base_chance = 0.08
        else:
            base_chance = 0.25   # 1849-1855 was the golden era for surface nuggets

        depth_bonus = min(1.0, dig_depth / 10.0) * 0.35
        return base_chance + depth_bonus