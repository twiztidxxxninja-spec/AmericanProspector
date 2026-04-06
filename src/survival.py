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

    # Mercury exposure — accumulates from gold amalgamation.
    # 0-100 scale. Causes tremors, confusion, madness at high levels.
    mercury_exposure: float = 0.0

    days_meat_only: int = 0  # scurvy risk after 30+ days

    # Intoxication — from whiskey, rum, etc.
    # 0 = sober, 1-3 = buzzed, 4-6 = drunk, 7-9 = hammered, 10+ = blackout
    drunk_level: float = 0.0

    # Disease system — each disease is a dict with:
    #   "id": str, "name": str, "hours_remaining": float,
    #   "severity": float (0-1), "treated": bool
    # Empty list = healthy.
    diseases: List = field(default_factory=list)

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

        # Mercury poisoning damage (slow, chronic)
        if self.mercury_exposure >= 80:
            self.health = max(0, self.health - 0.5 * hours)
        elif self.mercury_exposure >= 60:
            self.fatigue = max(0, self.fatigue - 0.5 * hours)

        # Mercury slowly dissipates (very slowly — 0.1/day)
        if self.mercury_exposure > 0:
            self.mercury_exposure = max(0, self.mercury_exposure - 0.004 * hours)

        # Intoxication — metabolizes at ~1 level per hour
        # Drunk gives warmth but drains fatigue and coordination
        if self.drunk_level > 0:
            self.drunk_level = max(0, self.drunk_level - 0.8 * hours)
            # Warmth bonus (whiskey makes you FEEL warm — historically dangerous)
            self.warmth = min(100.0, self.warmth + 0.5 * hours * min(self.drunk_level, 5))
            # Fatigue drain from drunk (body working to metabolize)
            self.fatigue = max(0, self.fatigue - 0.3 * hours * self.drunk_level)
            # Blackout threshold
            if self.drunk_level >= 10:
                self.fatigue = 0  # pass out

        # Scurvy — gradual health drain from all-meat diet
        # Historically took 6-12 weeks to become serious
        if self.days_meat_only >= 30:
            # Starts mild (0.05/hr at day 30), worsens over time
            severity = min(1.0, (self.days_meat_only - 30) / 60.0)
            drain = 0.05 + severity * 0.15  # 0.05-0.20 per hour
            self.health = max(10.0, self.health - drain * hours)  # won't kill outright

        # Disease progression
        if self.diseases:
            self.tick_diseases(hours, constitution)

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

    def log_food(self, is_meat: bool, day: int = -1):
        """Track meat-only diet for scurvy risk."""
        if is_meat:
            if day != getattr(self, '_last_food_day', -1):
                self.days_meat_only += 1
                self._last_food_day = day
        else:
            self.days_meat_only = 0

    @property
    def has_scurvy_risk(self) -> bool:
        return self.days_meat_only >= 30

    @property
    def is_drunk(self) -> bool:
        return self.drunk_level >= 3

    @property
    def drunk_aim_penalty(self) -> int:
        """Penalty to firearm accuracy while drunk."""
        if self.drunk_level < 2:
            return 0
        return min(8, int(self.drunk_level))  # -2 to -8

    @property
    def drunk_label(self) -> str:
        if self.drunk_level < 1: return ""
        if self.drunk_level < 3: return "buzzed"
        if self.drunk_level < 6: return "drunk"
        if self.drunk_level < 9: return "hammered"
        return "blackout drunk"

    def drink_alcohol(self, strength: float = 2.0):
        """Consume alcohol. strength: whiskey=2.0, beer=0.5, wine=1.0"""
        self.drunk_level += strength
        self.thirst = min(100.0, self.thirst + 3.0)
        # Warmth surge
        self.warmth = min(100.0, self.warmth + strength * 3)

    def rest(self, minutes: float):
        """Sleeping restores fatigue; small warmth recovery if sheltered."""
        hours = minutes / 60.0
        self.fatigue = min(100.0, self.fatigue + 12.0 * hours)  # ~8hrs = full restore

    # ── Disease System ────────────────────────────────────────────────

    # Disease definitions: id → {name, base_duration_hours, lethality,
    #   health_drain_per_hour, hunger_drain, thirst_drain, fatigue_drain,
    #   symptoms, treatment_items, cure_hours_with_treatment}
    DISEASE_DEFS = {
        "cholera": {
            "name": "Cholera",
            "base_duration_hours": 72,       # 3 days untreated
            "lethality": 0.15,               # fatal only if completely ignored
            "health_drain": 0.8,             # serious but survivable
            "hunger_drain": 2.0,             # vomiting
            "thirst_drain": 4.0,             # dehydration is the real danger
            "fatigue_drain": 2.0,
            "symptoms": "violent cramping, vomiting, watery diarrhea",
            "treatment_items": ["willow_tea", "clean_water"],
            "cure_hours": 36,                # halved with treatment
        },
        "dysentery": {
            "name": "Dysentery",
            "base_duration_hours": 120,      # 5 days
            "lethality": 0.15,
            "health_drain": 0.5,
            "hunger_drain": 2.0,
            "thirst_drain": 3.0,
            "fatigue_drain": 1.5,
            "symptoms": "bloody stool, cramping, fever",
            "treatment_items": ["willow_tea"],
            "cure_hours": 72,
        },
        "malaria": {
            "name": "Malaria",
            "base_duration_hours": 168,      # 7 days per episode
            "lethality": 0.10,
            "health_drain": 0.4,
            "hunger_drain": 1.0,
            "thirst_drain": 1.5,
            "fatigue_drain": 3.0,            # crushing fatigue
            "symptoms": "chills, sweating, high fever, shaking",
            "treatment_items": ["quinine", "willow_tea"],
            "cure_hours": 48,
            "recurring": True,               # can relapse
        },
        "smallpox": {
            "name": "Smallpox",
            "base_duration_hours": 336,      # 14 days
            "lethality": 0.10,               # survivable with rest and water
            "health_drain": 0.5,
            "hunger_drain": 1.5,
            "thirst_drain": 2.0,
            "fatigue_drain": 2.5,
            "symptoms": "high fever, pustules covering the body, delirium",
            "treatment_items": [],            # no treatment in this era
            "cure_hours": 336,               # just have to survive it
        },
        "typhoid": {
            "name": "Typhoid Fever",
            "base_duration_hours": 240,      # 10 days
            "lethality": 0.08,
            "health_drain": 0.6,
            "hunger_drain": 1.5,
            "thirst_drain": 2.0,
            "fatigue_drain": 2.0,
            "symptoms": "sustained fever, headache, rose-colored spots on belly",
            "treatment_items": ["willow_tea"],
            "cure_hours": 120,
        },
        "mountain_fever": {
            "name": "Mountain Fever",
            "base_duration_hours": 96,       # 4 days — tick-borne
            "lethality": 0.05,
            "health_drain": 0.3,
            "hunger_drain": 0.5,
            "thirst_drain": 1.0,
            "fatigue_drain": 2.0,
            "symptoms": "fever, joint pain, headache, rash",
            "treatment_items": ["willow_tea"],
            "cure_hours": 48,
        },
        "wound_infection": {
            "name": "Wound Infection",
            "base_duration_hours": 168,      # 7 days
            "lethality": 0.10,
            "health_drain": 0.7,
            "hunger_drain": 0.5,
            "thirst_drain": 1.0,
            "fatigue_drain": 1.5,
            "symptoms": "red streaks from wound, swelling, fever, pus",
            "treatment_items": ["whiskey", "willow_tea", "bandage"],
            "cure_hours": 72,
        },
    }

    def contract_disease(self, disease_id: str, constitution: int = 10) -> str:
        """Contract a disease. Returns symptom message. CON reduces severity."""
        if disease_id not in self.DISEASE_DEFS:
            return ""
        # Don't stack same disease
        if any(d["id"] == disease_id for d in self.diseases):
            return ""
        defn = self.DISEASE_DEFS[disease_id]
        # CON resistance: higher CON = milder case
        severity = max(0.3, 1.0 - (constitution - 10) * 0.05)
        self.diseases.append({
            "id": disease_id,
            "name": defn["name"],
            "hours_remaining": defn["base_duration_hours"],
            "severity": severity,
            "treated": False,
        })
        return (f"You've contracted {defn['name']}. "
                f"Symptoms: {defn['symptoms']}.")

    def treat_disease(self, disease_id: str) -> bool:
        """Mark a disease as treated. Returns True if found."""
        for d in self.diseases:
            if d["id"] == disease_id and not d["treated"]:
                d["treated"] = True
                defn = self.DISEASE_DEFS.get(disease_id, {})
                d["hours_remaining"] = min(
                    d["hours_remaining"],
                    defn.get("cure_hours", d["hours_remaining"]))
                return True
        return False

    def tick_diseases(self, hours: float, constitution: int = 10):
        """Advance all active diseases. Called from tick()."""
        import random as _drng
        for d in list(self.diseases):
            defn = self.DISEASE_DEFS.get(d["id"], {})
            sev = d["severity"]
            d["hours_remaining"] -= hours

            # Apply drains scaled by severity
            self.health = max(0, self.health - defn.get("health_drain", 0) * hours * sev)
            self.hunger = max(0, self.hunger - defn.get("hunger_drain", 0) * hours * sev)
            self.thirst = max(0, self.thirst - defn.get("thirst_drain", 0) * hours * sev)
            self.fatigue = max(0, self.fatigue - defn.get("fatigue_drain", 0) * hours * sev)

            # Disease resolved
            if d["hours_remaining"] <= 0:
                # Disease runs its course. The player dies from the EFFECTS
                # (dehydration, starvation, exhaustion) not from a random roll.
                # Only add a small final health hit if they're already very weak
                # AND untreated — this represents the body giving out.
                if not d["treated"] and self.health < 25:
                    lethality = defn.get("lethality", 0) * sev
                    lethality *= max(0.3, 1.0 - (constitution - 10) * 0.04)
                    final_hit = lethality * 20  # up to ~5 HP
                    self.health = max(0, self.health - final_hit)
                self.diseases.remove(d)

    @property
    def has_disease(self) -> bool:
        return len(self.diseases) > 0

    @property
    def disease_names(self) -> List[str]:
        return [d["name"] for d in self.diseases]

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
        if self.mercury_exposure >= 60:
            result.append(("mercury poisoning", "critical"))
        elif self.mercury_exposure >= 20:
            result.append(("mercury tremors", "advisory"))
        if self.days_meat_only >= 30:
            result.append(("malnourished \u2014 eat plants or berries", "critical"))
        elif self.days_meat_only >= 20:
            result.append(("craving something other than meat", "advisory"))
        if self.drunk_level >= 9:
            result.append(("about to black out", "critical"))
        elif self.drunk_level >= 6:
            result.append(("hammered \u2014 vision swimming", "advisory"))
        elif self.drunk_level >= 3:
            result.append(("drunk \u2014 aim impaired", "advisory"))
        # Disease warnings
        for d in self.diseases:
            defn = self.DISEASE_DEFS.get(d["id"], {})
            if d["severity"] >= 0.7:
                result.append((f"sick with {d['name']} \u2014 {defn.get('symptoms', 'ill')}", "critical"))
            else:
                result.append((f"{d['name']} \u2014 feeling unwell", "advisory"))
        for name, val in checks:
            if val <= STAT_CRITICAL:
                result.append((name, "critical"))
            elif val <= STAT_WARNING:
                result.append((name, "advisory"))
        return result

    @property
    def alive(self) -> bool:
        return self.health > 0

    def add_mercury_exposure(self, amount: float = 2.0):
        """Add mercury exposure from handling quicksilver. Accumulates over time.
        Effects at thresholds: 20=tremors, 40=confusion, 60=madness, 80=dying."""
        self.mercury_exposure = min(100, self.mercury_exposure + amount)

    @property
    def mercury_symptoms(self) -> str:
        """Current mercury poisoning symptoms."""
        if self.mercury_exposure >= 80:
            return "severe mercury poisoning — dying"
        if self.mercury_exposure >= 60:
            return "mercury madness — hallucinations, paranoia"
        if self.mercury_exposure >= 40:
            return "mercury confusion — memory loss, slurred speech"
        if self.mercury_exposure >= 20:
            return "mercury tremors — shaking hands"
        return ""

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
