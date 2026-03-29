"""
NPC system — lazy instantiation, schedules, relationship tracking.
NPCs are generated on demand; only named/met NPCs are persisted.
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from src.health_system import HealthTracker, MAX_BLOOD, DmgType


# Relationship value: -100 (enemy) to 100 (trusted)
# 0 = stranger, negative = hostile, positive = friendly
REL_LABELS = {
    (-100, -50): "Enemy",
    ( -50, -20): "Hostile",
    ( -20,  -5): "Unfriendly",
    (  -5,   5): "Stranger",
    (   5,  20): "Acquaintance",
    (  20,  50): "Friend",
    (  50,  80): "Good Friend",
    (  80, 100): "Trusted",
}

def rel_label(value: float) -> str:
    for (lo, hi), label in REL_LABELS.items():
        if lo <= value < hi:
            return label
    return "Trusted" if value >= 100 else "Enemy"


# NPC memory capacity by INT
def memory_capacity(intelligence: int) -> int:
    """How many distinct facts an NPC can reliably remember about the player."""
    return max(1, intelligence // 3)


@dataclass
class NPCMemory:
    """What an NPC remembers about the player."""
    facts: List[str] = field(default_factory=list)   # things told/shown
    last_seen_location: Optional[str] = None
    last_seen_day: int = 0
    knows_name: bool = False

    def add_fact(self, fact: str, int_score: int):
        cap = memory_capacity(int_score)
        if fact not in self.facts:
            self.facts.append(fact)
        # Trim to capacity (oldest facts fade)
        if len(self.facts) > cap:
            self.facts = self.facts[-cap:]


@dataclass
class NPC:
    npc_id: str
    name: str
    age: int = 35
    gender: str = "M"              # "M" or "F"
    occupation: str = "Prospector"
    home_region: str = "California"

    # Attributes (same 6 as player)
    attributes: Dict[str, int] = field(default_factory=lambda: {
        "strength": 10, "agility": 10, "intelligence": 10,
        "wisdom": 10, "charisma": 10, "constitution": 10,
    })

    # Skills (subset relevant to NPC)
    skills: Dict[str, int] = field(default_factory=dict)

    # Knowledge areas (things they know how to do / about)
    knowledge: Dict[str, int] = field(default_factory=dict)  # topic -> level 0-4

    # Personality traits (affect dialogue tone)
    traits: List[str] = field(default_factory=list)
    # e.g. "taciturn", "boastful", "friendly", "suspicious", "religious", "drunk"

    # Current state
    local_x: int = 0
    local_y: int = 0
    local_z: int = 0
    alive: bool  = True
    present: bool = True   # currently on this local map

    # Combat
    health: float = 100.0
    # neutral | hostile | fleeing | surrendered | dead
    combat_state: str = "neutral"
    wounds: HealthTracker = field(
        default_factory=lambda: HealthTracker(MAX_BLOOD["human"]))

    # Relationship with player
    relationship: float = 0.0
    memory: NPCMemory = field(default_factory=NPCMemory)

    # Backstory — generated lazily on first conversation
    backstory_revealed: List[str] = field(default_factory=list)
    backstory_hidden: List[str] = field(default_factory=list)

    # Schedule (simple)
    schedule: Dict[str, str] = field(default_factory=dict)
    # {"morning": "store", "afternoon": "saloon", "evening": "home"}

    def rel_label(self) -> str:
        return rel_label(self.relationship)

    def adjust_relationship(self, delta: float):
        self.relationship = max(-100.0, min(100.0, self.relationship + delta))

    def take_damage(self, amount: float,
                    damage_type: str = DmgType.BLUNT) -> bool:
        """Apply damage and a wound. Returns True if NPC was killed."""
        from src.combat import _check_npc_morale
        self.health = max(0.0, self.health - amount)
        self.wounds.apply_hit(amount, damage_type)
        _check_npc_morale(self)
        return not self.alive

    def go_hostile(self):
        if self.combat_state == "neutral":
            self.combat_state = "hostile"

    def display_name(self) -> str:
        if self.memory.knows_name:
            return self.name
        return f"A {self.occupation.lower()}"

    def short_desc(self) -> str:
        """One-line description for map tile examine."""
        rel = self.rel_label()
        return f"{self.display_name()} ({self.occupation}, {rel})"


# ── NPC Generation ──────────────────────────────────────────────────────────

FIRST_NAMES_M = [
    "James", "John", "William", "Thomas", "George", "Charles", "Henry",
    "Robert", "Edward", "Joseph", "Samuel", "Daniel", "Frank", "Walter",
    "Elijah", "Ezra", "Luther", "Silas", "Amos", "Cyrus",
]
FIRST_NAMES_F = [
    "Mary", "Sarah", "Elizabeth", "Margaret", "Emma", "Clara", "Alice",
    "Hannah", "Martha", "Catherine", "Helen", "Ruth", "Ida", "Edith",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis",
    "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson", "White",
    "Harris", "Martin", "Thompson", "Garcia", "Martinez", "Robinson",
    "McGee", "O'Brien", "Flynn", "Callahan", "Murphy", "Brennan",
    "Kowalski", "Mueller", "Johansson", "Petersen",
]

OCCUPATIONS = [
    "Prospector", "Miner", "Trapper", "Farmer", "Rancher",
    "Merchant", "Blacksmith", "Doctor", "Lawyer", "Saloon Keeper",
    "Freighter", "Scout", "Drifter", "Gambler", "Preacher",
]

TRAITS_POOL = [
    "taciturn", "friendly", "boastful", "suspicious", "religious",
    "hardworking", "lazy", "generous", "greedy", "honest",
    "weathered", "nervous", "calm", "hot-tempered", "wry",
]

OCCUPATION_ATTR_BIAS = {
    "Blacksmith":   {"strength": 4, "constitution": 2},
    "Doctor":       {"intelligence": 4, "wisdom": 2},
    "Lawyer":       {"charisma": 3, "intelligence": 3},
    "Merchant":     {"charisma": 3, "wisdom": 2},
    "Farmer":       {"constitution": 3, "strength": 2},
    "Rancher":      {"constitution": 3, "strength": 2},
    "Scout":        {"agility": 3, "wisdom": 3},
    "Trapper":      {"agility": 2, "wisdom": 2, "constitution": 2},
    "Gambler":      {"charisma": 3, "agility": 2},
    "Saloon Keeper":{"charisma": 3, "wisdom": 2},
}

OCCUPATION_SKILLS = {
    "Prospector":  {"placer": 3, "geology": 2, "survival": 2},
    "Miner":       {"hardRock": 4, "engineering": 2},
    "Trapper":     {"tracking": 4, "survival": 4, "firearms": 3},
    "Farmer":      {"farming": 4, "survival": 2},
    "Rancher":     {"farming": 3, "survival": 3, "firearms": 2},
    "Merchant":    {"trading": 4, "law": 2},
    "Blacksmith":  {"engineering": 4},
    "Doctor":      {"firstAid": 5, "chemistry": 3},
    "Lawyer":      {"law": 5, "charisma": 3},
    "Scout":       {"tracking": 5, "survival": 4, "firearms": 4},
    "Saloon Keeper":{"trading": 3},
    "Gambler":     {"trading": 2},
    "Drifter":     {"survival": 3, "firearms": 2},
}

# Domain knowledge by occupation — keys match what rumor_system and talk.py check for
OCCUPATION_KNOWLEDGE = {
    "Prospector":   {"placer": 3, "geology": 2},
    "Miner":        {"hardRock": 3, "geology": 2, "assaying": 1},
    "Assayer":      {"assaying": 4, "geology": 3},
    "Trapper":      {"tracking": 3, "survival": 3},
    "Farmer":       {"farming": 3},
    "Rancher":      {"farming": 2, "tracking": 1},
    "Merchant":     {"trading": 3, "law": 1},
    "Blacksmith":   {"engineering": 3},
    "Doctor":       {"firstAid": 4, "chemistry": 2},
    "Lawyer":       {"law": 4},
    "Scout":        {"tracking": 4, "survival": 3},
    "Saloon Keeper":{"trading": 2},
    "Gambler":      {"trading": 1},
    "Drifter":      {"survival": 2},
    "Freighter":    {"driving": 2, "trading": 1},
    "Preacher":     {},
}


def generate_npc(npc_id: str, seed: int, occupation: Optional[str] = None,
                 location_context: Optional[str] = None) -> NPC:
    """Generate a full NPC from seed. Deterministic for same seed."""
    rng = random.Random(seed)

    gender    = rng.choice(["M", "F"])
    first     = rng.choice(FIRST_NAMES_M if gender == "M" else FIRST_NAMES_F)
    last      = rng.choice(LAST_NAMES)
    name      = f"{first} {last}"
    age       = rng.randint(18, 65)   # 18 is the hard floor — no minors ever spawn
    occ       = occupation or rng.choice(OCCUPATIONS)
    traits    = rng.sample(TRAITS_POOL, k=rng.randint(1, 3))

    # Attributes: base 8, +1d4, then occupation bias
    attrs = {}
    for stat in ("strength","agility","intelligence","wisdom","charisma","constitution"):
        attrs[stat] = 8 + rng.randint(1, 4)
    bias = OCCUPATION_ATTR_BIAS.get(occ, {})
    for stat, bonus in bias.items():
        attrs[stat] = min(18, attrs[stat] + bonus)

    # Skills from occupation
    skills = dict(OCCUPATION_SKILLS.get(occ, {}))
    # Random extra skill
    extra_skill = rng.choice(list(OCCUPATION_SKILLS.get("Drifter", {"survival": 1}).keys()))
    skills[extra_skill] = skills.get(extra_skill, 0) + rng.randint(1, 2)

    # Knowledge: occupation domain knowledge + 1-2 personal topics
    knowledge = dict(OCCUPATION_KNOWLEDGE.get(occ, {}))
    # Add personal background knowledge
    personal_k = rng.sample([
        "cabin building", "horse handling", "cooking", "navigation",
        "rope work", "carpentry", "hunting", "fishing",
        "blacksmithing", "leather work", "farming basics",
    ], k=rng.randint(1, 2))
    for k in personal_k:
        knowledge[k] = rng.randint(1, 2)

    # Backstory (hidden until conversation reveals it)
    backstory_hidden = [
        f"Originally from {rng.choice(['Ohio', 'Missouri', 'New York', 'Pennsylvania', 'Kentucky', 'Tennessee', 'Ireland', 'Germany', 'England'])}",
        f"{'Married' if rng.random() < 0.5 else 'Unmarried'}",
        f"Has been in California {rng.randint(0, 5)} years",
    ]
    if rng.random() < 0.3:
        backstory_hidden.append(rng.choice([
            "Former soldier",
            "Ran from debt back east",
            "Looking for a missing brother",
            "Lost a partner to fever last winter",
            "Worked as a carpenter before coming west",
        ]))

    # Simple schedule
    schedule = {"dawn": "camp", "morning": "work", "afternoon": "work",
                "dusk": "camp", "night": "sleep"}

    npc = NPC(
        npc_id=npc_id, name=name, age=age, gender=gender, occupation=occ,
        attributes=attrs, skills=skills, knowledge=knowledge,
        traits=traits, backstory_hidden=backstory_hidden,
        schedule=schedule,
    )
    return npc


# ── NPC Manager ─────────────────────────────────────────────────────────────

class NPCManager:
    """Tracks all instantiated NPCs. Handles placement on local maps."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.npcs: Dict[str, NPC] = {}
        self._next_id = 1

    def _new_id(self) -> str:
        nid = f"npc_{self._next_id}"
        self._next_id += 1
        return nid

    def spawn_for_local(self, wx: int, wy: int, local_map,
                        population_hint: int = 2) -> List[NPC]:
        """
        Spawn 0–population_hint NPCs for a local map tile.
        Uses tile position as seed so same tile always generates same NPCs.
        """
        seed = self.seed + wx * 10000 + wy
        rng  = random.Random(seed)
        count = rng.randint(0, min(population_hint, 3))
        spawned = []

        for i in range(count):
            npc_id = f"local_{wx}_{wy}_{i}"
            if npc_id in self.npcs:
                npc = self.npcs[npc_id]
            else:
                npc = generate_npc(npc_id, seed + i)
                npc.local_x = rng.randint(5, local_map.width  - 5)
                npc.local_y = rng.randint(5, local_map.height - 5)
                self.npcs[npc_id] = npc
            npc.present = True
            spawned.append(npc)

        return spawned

    def get_at(self, x: int, y: int, z: int = None) -> Optional[NPC]:
        """Return NPC at given local map position, or None.
        If z is None, matches any z-level (backward compat)."""
        for npc in self.npcs.values():
            if npc.present and npc.local_x == x and npc.local_y == y:
                if z is None or npc.local_z == z:
                    return npc
        return None

    def npcs_on_map(self) -> List[NPC]:
        return [n for n in self.npcs.values() if n.present]


