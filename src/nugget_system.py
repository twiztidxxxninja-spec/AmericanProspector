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

    # ── Regional nugget profiles ──────────────────────────────────────
    # Each region has different:
    #   base_mult: multiplier on nugget chance (how nugget-rich the geology is)
    #   max_weight: largest nuggets found historically
    #   fineness: gold purity (varies by geological source)
    #   desc_prefix: flavor for the region's gold character

    _REGION_PROFILES = {
        # California Mother Lode — THE nugget region. Massive nuggets found.
        # Gold washed from Jurassic-era quartz veins into Sierra streams.
        "Sierra Nevada":     {"base_mult": 1.5, "max_weight": 25.0,
                              "fineness": (0.880, 0.920),
                              "desc": "bright Sierra gold"},
        "California":        {"base_mult": 1.3, "max_weight": 15.0,
                              "fineness": (0.875, 0.925),
                              "desc": "California placer gold"},
        # Rocky Mountains — good nugget potential, less than California
        "Rocky":             {"base_mult": 1.0, "max_weight": 8.0,
                              "fineness": (0.850, 0.910),
                              "desc": "mountain gold"},
        "Montana":           {"base_mult": 1.2, "max_weight": 10.0,
                              "fineness": (0.860, 0.920),
                              "desc": "Montana placer gold"},
        "Idaho":             {"base_mult": 1.0, "max_weight": 6.0,
                              "fineness": (0.840, 0.900),
                              "desc": "Idaho gold"},
        # Black Hills — rich but smaller nuggets
        "Black Hills":       {"base_mult": 1.3, "max_weight": 5.0,
                              "fineness": (0.870, 0.930),
                              "desc": "Black Hills gold"},
        # Alaska — good nuggets, medium size, lower purity
        "Alaska":            {"base_mult": 1.2, "max_weight": 8.0,
                              "fineness": (0.820, 0.880),
                              "desc": "Alaskan gold"},
        # Nevada — mostly lode/silver, nuggets rare
        "Nevada":            {"base_mult": 0.5, "max_weight": 3.0,
                              "fineness": (0.750, 0.850),
                              "desc": "Nevada gold"},
        # Appalachians — small but PURE nuggets. Carolina gold was famously fine.
        # Reed Gold Mine (1799) produced a 17-lb nugget, but that was exceptional.
        "Appalachian":       {"base_mult": 0.6, "max_weight": 4.0,
                              "fineness": (0.950, 0.990),
                              "desc": "pure Appalachian gold"},
        # Great Plains — almost no nuggets. Gold in plains is flour/dust only.
        "Great Plains":      {"base_mult": 0.05, "max_weight": 0.5,
                              "fineness": (0.800, 0.900),
                              "desc": "a tiny flake"},
        # Desert — rare, small
        "Desert":            {"base_mult": 0.3, "max_weight": 2.0,
                              "fineness": (0.800, 0.880),
                              "desc": "desert gold"},
        # Gulf Coast — essentially no gold
        "Gulf":              {"base_mult": 0.01, "max_weight": 0.2,
                              "fineness": (0.800, 0.900),
                              "desc": "a speck"},
    }

    @classmethod
    def _get_region_profile(cls, region_name: str) -> dict:
        """Match region name to nugget profile."""
        rn = region_name.lower()
        for key, profile in cls._REGION_PROFILES.items():
            if key.lower() in rn:
                return profile
        # Default — modest chance, typical purity
        return {"base_mult": 0.3, "max_weight": 3.0,
                "fineness": (0.850, 0.920), "desc": "gold"}

    @staticmethod
    def roll_nugget(dig_depth: int, gold_grade: float, region_name: str,
                    era_year: int, placer_skill: int, rng: random.Random,
                    pan_count: int = 0) -> Optional[Nugget]:
        """
        Decide if a nugget appears in this pan/dig.
        Geographically and historically accurate:
        - California has the most and biggest nuggets
        - Appalachian gold is small but extremely pure
        - Great Plains/Gulf Coast have almost no nuggets
        - Era affects virgin-ground bonus (diminishes with time)
        """
        profile = NuggetSystem._get_region_profile(region_name)
        region_mult = profile["base_mult"]
        max_weight = profile["max_weight"]
        fine_lo, fine_hi = profile["fineness"]

        # Base chance per pan — nuggets are RARE finds.
        # Historically, even in the richest California ground, a miner
        # might find 1 nugget per week of steady panning. At ~30 pans/day,
        # that's roughly 1 in 200 pans (0.5%).
        #
        # Expected nugget frequency by region and era:
        #   California 1849: ~1 per 100-150 pans (rich virgin ground)
        #   California 1860: ~1 per 300 pans
        #   Rockies 1860: ~1 per 200 pans
        #   Appalachians: ~1 per 500-1000 pans (rare, small)
        #   Great Plains: essentially never
        #
        if region_mult < 0.1:
            base_chance = 0.0002  # near-zero for goldless regions
        elif era_year <= 1855:
            base_chance = 0.006 * region_mult   # ~0.9% California
        elif era_year <= 1865:
            base_chance = 0.003 * region_mult   # ~0.45% California
        else:
            base_chance = 0.0015 * region_mult  # ~0.23% California

        # Depth bonus — nuggets concentrate at bedrock over millennia
        # This is the BIG payoff for digging deep
        depth_bonus = min(0.008, dig_depth / 12.0 * 0.008) * region_mult

        # Rich ground bonus — only very rich ground has nugget potential
        if gold_grade >= 0.6:
            richness_bonus = 0.005 * region_mult
        elif gold_grade >= 0.3:
            richness_bonus = 0.002 * region_mult
        else:
            richness_bonus = 0.0

        # Skill helps you notice and recover small nuggets
        skill_bonus = placer_skill * 0.001

        final_chance = base_chance + depth_bonus + richness_bonus + skill_bonus

        # Diminishing returns — working the same spot repeatedly
        if pan_count > 3:
            final_chance *= max(0.05, 1.0 - (pan_count - 3) * 0.08)

        if rng.random() > final_chance:
            return None

        # === Nugget size — capped by regional max ===
        roll = rng.random()
        desc_gold = profile["desc"]

        if roll < 0.45:
            # Small picker
            weight = rng.uniform(0.05, min(0.35, max_weight))
            desc = f"a small piece of {desc_gold}"
        elif roll < 0.75:
            # Medium nugget
            weight = rng.uniform(0.4, min(1.5, max_weight))
            desc = f"a solid thumb-sized nugget of {desc_gold}"
        elif roll < 0.92:
            # Large nugget
            weight = rng.uniform(1.5, min(4.0, max_weight))
            desc = f"a heavy, beautiful nugget of {desc_gold}"
        else:
            # Bonanza nugget — capped by region
            weight = rng.uniform(4.0, max_weight)
            if max_weight < 2.0:
                # Region doesn't produce big nuggets — downgrade
                weight = rng.uniform(0.1, max_weight)
                desc = f"a nice piece of {desc_gold}"
            else:
                desc = f"a massive nugget of {desc_gold}"

        # Regional fineness (purity)
        fineness = rng.uniform(fine_lo, fine_hi)

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