"""
src/nugget_system.py

Nugget generation system for American Prospector.
Higher nugget frequency in the early Gold Rush (1849–1855) to match history.
"""

from dataclasses import dataclass
import random
from typing import Tuple, Optional


@dataclass
class Nugget:
    """A single gold nugget."""
    weight_oz: float          # troy ounces
    fineness: float           # purity (0.900 typical for California gold)
    description: str          # flavor text for the player


class NuggetSystem:
    """
    Controls nugget generation with strong historical grounding.
    - Much higher chance in 1849–1855 (the "easy gold" period)
    - Nuggets are more common at depth and in rich bedrock pockets
    - Size distribution feels exciting but realistic
    """

    @staticmethod
    def roll_nugget(dig_depth: int, gold_grade: float, region_name: str, 
                    era_year: int, placer_skill: int, rng: random.Random) -> Optional[Nugget]:
        """
        Decide if a nugget appears in this pan/dig.
        Returns Nugget object or None.
        """

        # Base chance — significantly higher in early years
        if era_year <= 1855:
            base_chance = 0.22          # Very high during the initial Rush
        elif era_year <= 1865:
            base_chance = 0.12
        else:
            base_chance = 0.06          # Becomes rare as easy gold is worked out

        # Depth bonus — nuggets are heavier and sink
        depth_bonus = min(1.0, dig_depth / 12.0) * 0.45

        # Rich ground bonus
        richness_bonus = min(1.0, gold_grade * 1.8)

        # Skill helps you notice and recover small nuggets
        skill_bonus = placer_skill * 0.025

        final_chance = base_chance + depth_bonus + richness_bonus + skill_bonus

        if rng.random() > final_chance:
            return None

        # === Nugget size distribution (heavier nuggets are rarer) ===
        roll = rng.random()

        if roll < 0.45:
            # Small "picker" nugget — common
            weight = rng.uniform(0.08, 0.35)
            desc = "a small bright nugget"
        elif roll < 0.75:
            # Medium "good" nugget
            weight = rng.uniform(0.4, 1.2)
            desc = "a solid thumb-sized nugget"
        elif roll < 0.92:
            # Large "exciting" nugget
            weight = rng.uniform(1.3, 3.5)
            desc = "a heavy, beautiful nugget"
        else:
            # Rare "bonanza" nugget (very exciting)
            weight = rng.uniform(4.0, 12.0)
            desc = "a massive, spectacular nugget"

        # Slight purity variation (California gold was typically ~900 fine)
        fineness = rng.uniform(0.875, 0.935)

        return Nugget(
            weight_oz=round(weight, 3),
            fineness=round(fineness, 3),
            description=desc
        )

    @staticmethod
    def get_nugget_value(nugget: Nugget) -> float:
        """Calculate dollar value using 1849 fixed price."""
        GOLD_PRICE_PER_OZ = 20.67
        return nugget.weight_oz * GOLD_PRICE_PER_OZ * nugget.fineness

    @staticmethod
    def format_nugget_message(nugget: Nugget) -> str:
        """Nice message for the player when they find a nugget."""
        value = NuggetSystem.get_nugget_value(nugget)
        
        if nugget.weight_oz >= 5.0:
            return (f"**BONANZA!** You pull out a massive {nugget.weight_oz:.2f} oz nugget "
                    f"({nugget.description}). Worth about ${value:.2f}!")
        elif nugget.weight_oz >= 1.5:
            return (f"Excellent! A solid {nugget.weight_oz:.2f} oz nugget "
                    f"({nugget.description}) — about ${value:.2f}.")
        else:
            return (f"You find a nice {nugget.weight_oz:.2f} oz nugget "
                    f"({nugget.description}). Worth ${value:.2f}.")