"""
Survival stats: hunger, thirst, warmth, fatigue, health.
All stats 0–100. Drain rates per real in-game hour, modified by activity.
"""

from dataclasses import dataclass, field
from typing import List, Tuple
from src.constants import (HUNGER_RATE, THIRST_RATE, WARMTH_RATE,
                            FATIGUE_RATE, STAT_WARNING, STAT_CRITICAL)


@dataclass
class SurvivalStats:
    health:  float = 100.0
    hunger:  float = 100.0   # 100 = full, 0 = starving
    thirst:  float = 100.0   # 100 = hydrated, 0 = dehydrated
    warmth:  float = 80.0    # 100 = warm, 0 = freezing
    fatigue: float = 100.0   # 100 = rested, 0 = exhausted

    # Gut sickness — from stagnant water, bad food, etc.
    # Duration in hours remaining. 0 = healthy.
    gut_sick_hours: float = 0.0

    def tick(self, minutes: float, activity_mult: float = 1.0,
             temp_mod: float = 0.0, sheltered: bool = False,
             constitution: int = 10):
        """
        Advance survival stats by `minutes` of in-game time.
        activity_mult: 1.0 normal, 2.0 hard labor, 0.5 resting
        temp_mod: degrees below comfortable (negative = cold, positive = hot)
        sheltered: reduces warmth drain
        constitution: CON attribute — reduces hunger/thirst drain, cold resistance
        """
        hours = minutes / 60.0

        # CON reduces hunger/thirst drain (CON 16 = 20% less, CON 6 = 15% more)
        con_efficiency = 1.0 - (constitution - 10) * 0.03
        self.hunger  = max(0.0, self.hunger  - HUNGER_RATE  * hours * activity_mult * con_efficiency)
        self.thirst  = max(0.0, self.thirst  - THIRST_RATE  * hours * activity_mult * con_efficiency)
        self.fatigue = max(0.0, self.fatigue - FATIGUE_RATE * hours * activity_mult)

        # Warmth drain — CON provides cold resistance
        cold_mult = max(0.0, -temp_mod / 10.0)
        if sheltered:
            cold_mult *= 0.2
        # CON 16 = 30% less warmth drain, CON 6 = 20% more
        con_cold = 1.0 - (constitution - 10) * 0.05
        self.warmth = max(0.0, self.warmth - WARMTH_RATE * hours * (1.0 + cold_mult) * con_cold)

        # Gut sickness — drains hunger/thirst faster, slows you down
        if self.gut_sick_hours > 0:
            self.gut_sick_hours = max(0, self.gut_sick_hours - hours)
            self.hunger = max(0, self.hunger - 1.5 * hours)   # vomiting/diarrhea
            self.thirst = max(0, self.thirst - 2.0 * hours)   # dehydration
            self.fatigue = max(0, self.fatigue - 1.0 * hours)  # exhaustion

        # Damage from critical stats (CON reduces damage rate)
        deprivation_resist = max(0.5, 1.0 - (constitution - 10) * 0.05)
        if self.hunger == 0:
            self.health = max(0.0, self.health - 1.0 * hours * deprivation_resist)
        if self.thirst == 0:
            self.health = max(0.0, self.health - 3.0 * hours * deprivation_resist)
        if self.warmth == 0:
            self.health = max(0.0, self.health - 2.0 * hours * deprivation_resist)

    def eat(self, nutrition: float):
        self.hunger = min(100.0, self.hunger + nutrition)

    def drink(self, hydration: float):
        self.thirst = min(100.0, self.thirst + hydration)

    def rest(self, minutes: float):
        """Sleeping restores fatigue; small warmth recovery if sheltered."""
        hours = minutes / 60.0
        self.fatigue = min(100.0, self.fatigue + 12.0 * hours)  # ~8hrs = full restore

    def warnings(self) -> List[Tuple[str, str]]:
        """
        Returns list of (stat_name, severity) for any stats needing attention.
        severity: 'advisory' or 'critical'
        """
        checks = [
            ("hunger",  self.hunger),
            ("thirst",  self.thirst),
            ("warmth",  self.warmth),
            ("fatigue", self.fatigue),
            ("health",  self.health),
        ]
        result = []
        if self.gut_sick_hours > 0:
            if self.gut_sick_hours > 48:
                result.append(("gut sick", "critical"))
            else:
                result.append(("gut sick", "advisory"))
        for name, val in checks:
            if val <= STAT_CRITICAL:
                result.append((name, "critical"))
            elif val <= STAT_WARNING:
                result.append((name, "advisory"))
        return result

    @property
    def alive(self) -> bool:
        return self.health > 0

    def contract_gut_sickness(self, severity: float = 1.0):
        """Contract gut sickness. Duration 72-120 hours (3-5 days).
        Survivable without treatment, clears faster with medicine."""
        import random
        duration = random.uniform(72, 120) * severity
        self.gut_sick_hours = max(self.gut_sick_hours, duration)

    def treat_gut_sickness(self):
        """Treat with medicine — reduces remaining duration to ~24 hours."""
        self.gut_sick_hours = min(self.gut_sick_hours, 24)

    @property
    def is_gut_sick(self) -> bool:
        return self.gut_sick_hours > 0

    def bar(self, stat: str, width: int = 10) -> str:
        """ASCII bar for display: ████████░░"""
        val = getattr(self, stat)
        filled = round((val / 100.0) * width)
        return "\u2588" * filled + "\u2591" * (width - filled)
