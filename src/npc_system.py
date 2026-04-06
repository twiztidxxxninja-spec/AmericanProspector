"""
src/npc_system.py

Core NPC system: generation, personality, relationships, social simulation,
background events, and LLM integration helpers.

Key classes:
    MemoryEntry         — a single remembered event
    NPCMemoryExpanded   — event-based memory with significance and decay
    NPCRelationship     — multi-axis relationship (affinity, trust, romantic, fear, respect)
    PregnancyState      — tracks pregnancy timeline
    NPCExpanded         — full NPC with personality, motivations, relationships
    NPCGenerator        — settlement-aware NPC generation from npc_data tables
    GossipEntry / GossipSystem — reputation propagation between NPCs
    BackgroundEvent / BackgroundSimulator — NPC actions during time passage
    build_npc_llm_context()  — context string for LLM dialogue
    insight_check()          — skill-gated NPC perception

Integration:
    In engine.py, create an NPCGenerator on init:
        from src.npc_system import NPCGenerator
        self.npc_gen = NPCGenerator(seed=self.world.seed)

    When entering a settlement (world tile with a location):
        npcs = self.npc_gen.populate_settlement(
            settlement_type, wx, wy, year, location_name)

    When entering wilderness:
        npcs = self.npc_gen.populate_wilderness(wx, wy, terrain, year)

    The returned NPCs are full NPCExpanded objects that are backward-
    compatible with the old NPC dataclass (same field names for the
    fields that exist in both).
"""

import random
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from src.health_system import HealthTracker, MAX_BLOOD, DmgType
from src.npc_data import (
    SETTLEMENTS, ORIGIN_WEIGHTS, ORIGIN_HOMELANDS,
    NAMES_M, NAMES_F, LAST_NAMES,
    PROF_WEIGHTS_M, PROF_WEIGHTS_F, PROF_ATTR_BIAS, PROF_SKILLS, PROF_KNOWLEDGE,
    PERSONAL_KNOWLEDGE_POOL, TRAIT_TIERS, TRAIT_CONTRADICTIONS,
    MOTIVATION_TIERS, QUIRK_POOL, BACKSTORY_HOOKS,
    REL_LABELS, ROMANTIC_LABELS, ROMANCE_TRAIT_BONUSES,
)


# ============================================================================
#  MEMORY SYSTEM
# ============================================================================

@dataclass
class MemoryEntry:
    """A single NPC memory of an event or interaction."""
    content: str
    day: int                         # game day when it happened
    significance: float = 0.5        # 0.0 trivial → 1.0 life-changing
    emotional_valence: float = 0.0   # -1.0 very negative → +1.0 very positive
    category: str = "interaction"    # interaction | witnessed | told | promise | event


class NPCMemoryExpanded:
    """
    Event-based memory with significance weighting and intelligent decay.
    High-significance memories persist longer.  INT determines capacity.
    """

    def __init__(self, intelligence: int = 10):
        self.entries: List[MemoryEntry] = []
        self.intelligence = intelligence
        # Backward-compat fields (old NPCMemory interface)
        self.facts: List[str] = []
        self.last_seen_location: Optional[str] = None
        self.last_seen_day: int = 0
        self.knows_name: bool = False

    @property
    def capacity(self) -> int:
        """Maximum distinct memories before decay kicks in."""
        return max(3, self.intelligence)

    def add(self, content: str, day: int, significance: float = 0.5,
            valence: float = 0.0, category: str = "interaction") -> None:
        entry = MemoryEntry(content, day, significance, valence, category)
        self.entries.append(entry)
        # Also add to old-style facts for backward compat
        if content not in self.facts:
            self.facts.append(content)
        self._trim()

    def add_fact(self, fact: str, int_score: int) -> None:
        """Backward-compat method matching old NPCMemory.add_fact."""
        self.add(fact, self.last_seen_day, significance=0.4)

    def _trim(self) -> None:
        """Drop lowest-significance memories when over capacity."""
        if len(self.entries) <= self.capacity:
            return
        # Sort: high significance and recent day survive
        self.entries.sort(
            key=lambda e: e.significance + min(1.0, e.day / max(1, self.last_seen_day)),
            reverse=True,
        )
        self.entries = self.entries[:self.capacity]
        self.facts = [e.content for e in self.entries]

    def decay(self, current_day: int, days_passed: int) -> None:
        """
        Reduce significance of old memories.
        Called during background simulation time passage.
        Significant memories (> 0.8) barely decay.
        """
        for entry in self.entries:
            age_days = current_day - entry.day
            if entry.significance > 0.8:
                continue  # major events never fade
            decay_rate = 0.01 * (1.0 - entry.significance)
            entry.significance = max(0.05, entry.significance - decay_rate * days_passed)
        self._trim()

    def get_important(self, n: int = 5) -> List[MemoryEntry]:
        """Return the n most significant memories."""
        return sorted(self.entries, key=lambda e: e.significance, reverse=True)[:n]

    def get_recent(self, n: int = 5) -> List[MemoryEntry]:
        return self.entries[-n:]

    def knows_about(self, keyword: str) -> bool:
        kl = keyword.lower()
        return any(kl in e.content.lower() for e in self.entries)


# ============================================================================
#  RELATIONSHIP SYSTEM
# ============================================================================

@dataclass
class NPCRelationship:
    """
    Multi-axis relationship between an NPC and the player.
    All values clamped to their respective ranges.
    """
    affinity: float = 0.0       # -100..100  how much they like the player
    trust: float = 0.0          # 0..100     separate from liking
    respect: float = 10.0       # 0..100     based on player's deeds
    fear: float = 0.0           # 0..100     intimidation / threats
    romantic: float = 0.0       # 0..100     romantic interest
    jealousy: float = 0.0       # 0..100     toward player's other relationships

    status: str = "stranger"
    # stranger → acquaintance → friend → close_friend
    # close_friend → courting → engaged → married
    # any → rival, enemy
    # married → separated → ex

    days_known: int = 0
    last_interaction_day: int = 0
    times_met: int = 0
    gifts_given: int = 0
    favors_done: int = 0
    favors_owed_by_npc: int = 0   # NPC owes player this many favors
    favors_owed_by_player: int = 0  # player owes NPC
    betrayals: int = 0
    debts: List[str] = field(default_factory=list)  # descriptions of active debts/favors

    def _clamp(self) -> None:
        self.affinity  = max(-100.0, min(100.0, self.affinity))
        self.trust     = max(0.0, min(100.0, self.trust))
        self.respect   = max(0.0, min(100.0, self.respect))
        self.fear      = max(0.0, min(100.0, self.fear))
        self.romantic  = max(0.0, min(100.0, self.romantic))
        self.jealousy  = max(0.0, min(100.0, self.jealousy))

    def adjust(self, affinity: float = 0, trust: float = 0,
               respect: float = 0, fear: float = 0,
               romantic: float = 0, jealousy: float = 0) -> None:
        """Apply deltas to all axes and clamp."""
        self.affinity  += affinity
        self.trust     += trust
        self.respect   += respect
        self.fear      += fear
        self.romantic  += romantic
        self.jealousy  += jealousy
        self._clamp()

    def record_meeting(self, day: int) -> None:
        self.times_met += 1
        self.last_interaction_day = day
        self._maybe_upgrade_status()

    def _maybe_upgrade_status(self) -> None:
        """Auto-promote status based on thresholds (never auto-demote)."""
        s = self.status
        if s == "stranger" and self.times_met >= 3 and self.affinity > 5:
            self.status = "acquaintance"
        elif s == "acquaintance" and self.affinity > 25 and self.trust > 15:
            self.status = "friend"
        elif s == "friend" and self.affinity > 50 and self.trust > 35:
            self.status = "close_friend"
        # Romantic promotions require explicit player action (not auto)

    def set_status(self, new_status: str) -> None:
        """Explicit status change (from player action or event)."""
        self.status = new_status

    def affinity_label(self) -> str:
        for (lo, hi), label in REL_LABELS.items():
            if lo <= self.affinity < hi:
                return label
        return "Trusted Companion" if self.affinity >= 100 else "Sworn Enemy"

    def romantic_label(self) -> str:
        for (lo, hi), label in ROMANTIC_LABELS.items():
            if lo <= self.romantic < hi:
                return label
        return "Devoted" if self.romantic >= 100 else ""


# ============================================================================
#  PREGNANCY TRACKER
# ============================================================================

@dataclass
class PregnancyState:
    """Tracks pregnancy for a married NPC spouse."""
    conceived_day: int        # game day of conception
    due_day: int              # conceived + ~270 days
    departed_day: int = 0     # day she left for safe town (0 = hasn't yet)
    safe_town: str = ""       # name of town she went to
    child_name: str = ""      # pre-generated
    child_gender: str = ""    # "M" or "F"
    delivered: bool = False

    def days_pregnant(self, current_day: int) -> int:
        return current_day - self.conceived_day

    def should_depart(self, current_day: int) -> bool:
        """Spouse leaves around month 2-3 (60-90 days)."""
        return (not self.departed_day and
                self.days_pregnant(current_day) >= 60)

    def is_due(self, current_day: int) -> bool:
        return current_day >= self.due_day and not self.delivered


# ============================================================================
#  EXPANDED NPC CLASS
# ============================================================================

class NPCExpanded:
    """
    Full NPC with personality, motivations, multi-axis relationships,
    expanded memory, and romance support.

    Backward-compatible: exposes the same field names as the old NPC
    dataclass so existing engine/talk/combat code works unchanged.
    """

    def __init__(self, npc_id: str, name: str, **kwargs):
        # ── Identity ──
        self.npc_id: str        = npc_id
        self.name: str          = name
        self.age: int           = kwargs.get("age", 35)
        self.gender: str        = kwargs.get("gender", "M")
        self.occupation: str    = kwargs.get("occupation", "Prospector")
        self.ethnicity: str     = kwargs.get("ethnicity", "american")
        self.origin: str        = kwargs.get("origin", "Ohio")
        self.home_region: str   = kwargs.get("home_region", "California")
        self.settlement_id: str = kwargs.get("settlement_id", "")

        # ── Attributes & Skills ──
        self.attributes: Dict[str, int] = kwargs.get("attributes", {
            "strength": 10, "agility": 10, "intelligence": 10,
            "wisdom": 10, "charisma": 10, "constitution": 10,
        })
        self.skills: Dict[str, int]     = kwargs.get("skills", {})
        self.knowledge: Dict[str, int]  = kwargs.get("knowledge", {})

        # ── Personality ──
        self.traits: List[str]      = kwargs.get("traits", [])
        self.trait_tier: str        = kwargs.get("trait_tier", "common")
        self.motivations: List[str] = kwargs.get("motivations", [])
        self.motivation_tier: str   = kwargs.get("motivation_tier", "common")
        self.quirks: List[str]      = kwargs.get("quirks", [])

        # ── Physical position & state ──
        self.local_x: int = kwargs.get("local_x", 0)
        self.local_y: int = kwargs.get("local_y", 0)
        self.local_z: int = kwargs.get("local_z", 0)
        self.world_x: int = kwargs.get("world_x", 0)
        self.world_y: int = kwargs.get("world_y", 0)
        self.alive: bool  = True
        self.present: bool = True

        # ── Combat ──
        self.health: float = 100.0
        self.combat_state: str = "neutral"
        self.wounds: HealthTracker = HealthTracker(MAX_BLOOD["human"])
        self.inventory: List[Any] = kwargs.get("inventory", [])
        self.equipped_weapon: Optional[str] = None  # item id of equipped weapon

        # ── Relationship (backward-compat: .relationship is a float) ──
        self.rel: NPCRelationship = NPCRelationship()
        self.expanded_memory: NPCMemoryExpanded = NPCMemoryExpanded(
            self.attributes.get("intelligence", 10))

        # Old-style simple memory (backward compat)
        self.memory = self.expanded_memory  # same object, has .knows_name etc.

        # ── Social / Romance ──
        self.marital_status: str = kwargs.get("marital_status", "single")
        self.spouse_id: Optional[str] = kwargs.get("spouse_id", None)
        self.romantic_eligible: bool = kwargs.get("romantic_eligible", True)
        self.pregnancy: Optional[PregnancyState] = None
        self.children: List[Dict[str, Any]] = []

        # ── Backstory ──
        self.backstory_revealed: List[str] = kwargs.get("backstory_revealed", [])
        self.backstory_hidden: List[str]   = kwargs.get("backstory_hidden", [])
        self.appearance: str = ""   # LLM-generated on first meeting

        # ── Tribal affiliation ──
        self.tribe: str = kwargs.get("tribe", "")

        # ── Language ──
        # Whether this NPC speaks English (regardless of ethnicity).
        # Native Guides, Native Traders, French-Canadian voyageurs, etc.
        # are bilingual — they speak English AND their native language.
        self.speaks_english: bool = kwargs.get("speaks_english",
            self._default_speaks_english())

        # ── Schedule ──
        self.schedule: Dict[str, str] = kwargs.get("schedule", {
            "dawn": "camp", "morning": "work", "afternoon": "work",
            "dusk": "camp", "night": "sleep",
        })

        # ── Opinions of other NPCs ──
        # {npc_id: {"opinion": float(-100..100), "reason": str}}
        self.npc_opinions: Dict[str, Dict[str, Any]] = kwargs.get(
            "npc_opinions", {})

        # ── Merchant credit/debt ──
        # How much the player owes this merchant (positive = player owes)
        self.player_debt: float = kwargs.get("player_debt", 0.0)

        # ── Life state (changes over time) ──
        self.fortune: str = kwargs.get("fortune", "average")
        # "destitute", "struggling", "average", "comfortable", "wealthy"

    # ── Backward-compat properties ──────────────────────────────────────

    @property
    def relationship(self) -> float:
        return self.rel.affinity

    @relationship.setter
    def relationship(self, value: float) -> None:
        self.rel.affinity = max(-100.0, min(100.0, value))

    def rel_label(self) -> str:
        return self.rel.affinity_label()

    def adjust_relationship(self, delta: float) -> None:
        self.rel.adjust(affinity=delta)

    # ── Combat ──────────────────────────────────────────────────────────

    def take_damage(self, amount: float,
                    damage_type: str = DmgType.BLUNT) -> bool:
        from src.combat import _check_npc_morale
        self.health = max(0.0, self.health - amount)
        self.wounds.apply_hit(amount, damage_type)
        _check_npc_morale(self)
        return not self.alive

    def go_hostile(self) -> None:
        if self.combat_state == "neutral":
            self.combat_state = "hostile"

    # ── Display ─────────────────────────────────────────────────────────

    def display_name(self) -> str:
        if self.memory.knows_name:
            return self.name
        return f"A {self.occupation.lower()}"

    def short_desc(self) -> str:
        return f"{self.display_name()} ({self.occupation}, {self.rel_label()})"

    # ── Inventory / Equipment ──────────────────────────────────────────

    def get_weapon(self):
        """Return the equipped weapon Item, or None."""
        if not self.inventory:
            return None
        if self.equipped_weapon:
            for item in self.inventory:
                if item.id == self.equipped_weapon:
                    return item
        # Fallback: first weapon in inventory
        for item in self.inventory:
            if getattr(item, 'weapon_type', '') in ('melee', 'firearm'):
                return item
        return None

    def equip_occupation_weapon(self):
        """Give this NPC gear based on their occupation. Call at spawn."""
        import random as _eq_rng
        from src.items import make_item
        rng = _eq_rng.Random(hash(self.npc_id))

        # Weapon by occupation
        OCC_WEAPONS = {
            "Scout": "percussion_rifle", "Trapper": "percussion_rifle",
            "Rancher": "percussion_rifle", "Drifter": "percussion_rifle",
            "Hunter": "percussion_rifle",
            "Gambler": "percussion_revolver", "Lawyer": "percussion_revolver",
            "Sheriff": "percussion_revolver", "Marshal": "percussion_revolver",
            "Deputy": "percussion_revolver", "Ranger": "percussion_revolver",
            "Miner": "pickaxe", "Blacksmith": "hammer",
            "Merchant": "percussion_revolver",
            "Prospector": "hunting_knife",
            "Soldier": "percussion_rifle",
        }
        weapon_id = OCC_WEAPONS.get(self.occupation)
        if not weapon_id and "hot-tempered" in self.traits:
            weapon_id = "hunting_knife"
        if weapon_id:
            try:
                weapon = make_item(weapon_id)
                self.inventory.append(weapon)
                self.equipped_weapon = weapon.id
            except (ValueError, KeyError):
                pass

        # Profession tools
        OCC_TOOLS = {
            "Prospector": ["gold_pan", "shovel"],
            "Miner": ["shovel", "candle"],
            "Trapper": ["hunting_knife", "rope_10ft"],
            "Doctor": ["laudanum"],
            "Merchant": ["candle"],
            "Blacksmith": ["hammer"],
            "Cook": ["hunting_knife"],
        }
        for tool_id in OCC_TOOLS.get(self.occupation, []):
            if tool_id == self.equipped_weapon:
                continue  # don't duplicate the weapon
            try:
                self.inventory.append(make_item(tool_id))
            except (ValueError, KeyError):
                pass

        # Everyday carry — most frontier people carry a few basics
        everyday = []
        if rng.random() < 0.6:
            everyday.append("hardtack")
        if rng.random() < 0.4:
            everyday.append("canteen")
        if rng.random() < 0.3:
            everyday.append("rope_10ft")
        if rng.random() < 0.2:
            everyday.append("candle")
        if rng.random() < 0.15:
            everyday.append("whiskey")
        # Ammo for weapon carriers
        if weapon_id and "rifle" in weapon_id:
            everyday.append("rifle_ball")
        elif weapon_id and "revolver" in weapon_id:
            everyday.append("revolver_ball")
        for eid in everyday:
            try:
                self.inventory.append(make_item(eid))
            except (ValueError, KeyError):
                pass

    # ── NPC Opinions ───────────────────────────────────────────────────

    def set_opinion(self, npc_id: str, opinion: float, reason: str,
                    name: str = "") -> None:
        """Set this NPC's opinion of another NPC."""
        self.npc_opinions[npc_id] = {
            "opinion": max(-100.0, min(100.0, opinion)),
            "reason": reason,
            "name": name,
        }

    def get_opinion(self, npc_id: str) -> Optional[Dict]:
        return self.npc_opinions.get(npc_id)

    def opinion_summary(self, all_npcs: Dict[str, "NPCExpanded"]) -> List[str]:
        """Return human-readable opinion strings for the LLM context."""
        lines = []
        for npc_id, data in self.npc_opinions.items():
            other = all_npcs.get(npc_id)
            name = other.name if other else npc_id
            op = data["opinion"]
            label = ("hates" if op < -50 else "dislikes" if op < -15
                     else "neutral toward" if op < 15
                     else "likes" if op < 50 else "greatly respects")
            lines.append(f"{label} {name}: {data['reason']}")
        return lines

    # ── Favors & Debts ─────────────────────────────────────────────────

    def record_favor(self, description: str, player_helped: bool,
                     day: int) -> None:
        """Record a favor. player_helped=True means player helped the NPC."""
        if player_helped:
            self.rel.favors_owed_by_npc += 1
            self.rel.adjust(affinity=8, trust=5, respect=3)
        else:
            self.rel.favors_owed_by_player += 1
            self.rel.adjust(affinity=5, trust=3)
        self.rel.debts.append(description)
        self.expanded_memory.add(
            content=description,
            day=day,
            significance=0.7,
            valence=0.3 if player_helped else -0.1,
            category="favor",
        )

    # ── NPC-Initiated Greeting ─────────────────────────────────────────

    def generate_greeting(self, player_name: str, days_since: int) -> Optional[str]:
        """Generate a greeting if the NPC would initiate conversation.
        Returns None if they wouldn't bother."""
        aff = self.rel.affinity
        status = self.rel.status
        traits = set(self.traits)

        # Enemies and strangers don't greet
        if aff < -30:
            hostile_greets = [
                f'*{self.name} glares at you.*',
                f'*{self.name} spits on the ground as you pass.*',
                f'{self.name} mutters, "Look who showed up."',
            ]
            import random
            return random.choice(hostile_greets) if random.random() < 0.4 else None
        if status == "stranger":
            return None

        # Friends and close friends greet warmly
        if aff > 40 or status in ("friend", "close_friend"):
            if days_since > 14:
                greetings = [
                    f'{self.name} calls out, "Well I\'ll be! Haven\'t seen you in weeks, {player_name}!"',
                    f'{self.name} waves. "Where\'ve you been? Thought the mountains got you."',
                    f'"Hey, {player_name}!" {self.name} looks glad to see you.',
                ]
            else:
                greetings = [
                    f'{self.name} nods. "Good to see you, {player_name}."',
                    f'"Morning, {player_name}." {self.name} tips his hat.',
                    f'{self.name} gives a friendly wave.',
                ]
            import random
            return random.choice(greetings)

        # Acquaintances — occasional nod
        if status == "acquaintance" and aff > 5:
            import random
            if random.random() < 0.3:
                return f'{self.name} gives you a nod of recognition.'
        return None

    # ── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> Dict:
        d = {
            "npc_id": self.npc_id, "name": self.name, "age": self.age,
            "gender": self.gender, "occupation": self.occupation,
            "ethnicity": self.ethnicity, "origin": self.origin,
            "home_region": self.home_region, "settlement_id": self.settlement_id,
            "attributes": self.attributes, "skills": self.skills,
            "knowledge": self.knowledge,
            "traits": self.traits, "trait_tier": self.trait_tier,
            "motivations": self.motivations, "motivation_tier": self.motivation_tier,
            "quirks": self.quirks,
            "local_x": self.local_x, "local_y": self.local_y,
            "world_x": self.world_x, "world_y": self.world_y,
            "alive": self.alive, "present": self.present,
            "health": self.health, "combat_state": self.combat_state,
            "marital_status": self.marital_status,
            "spouse_id": self.spouse_id,
            "romantic_eligible": self.romantic_eligible,
            "backstory_revealed": self.backstory_revealed,
            "backstory_hidden": self.backstory_hidden,
            "appearance": self.appearance,
            "tribe": self.tribe,
            "speaks_english": self.speaks_english,
            "schedule": self.schedule,
            "rel": {
                "affinity": self.rel.affinity, "trust": self.rel.trust,
                "respect": self.rel.respect, "fear": self.rel.fear,
                "romantic": self.rel.romantic, "jealousy": self.rel.jealousy,
                "status": self.rel.status, "days_known": self.rel.days_known,
                "last_interaction_day": self.rel.last_interaction_day,
                "times_met": self.rel.times_met, "gifts_given": self.rel.gifts_given,
                "favors_done": self.rel.favors_done, "betrayals": self.rel.betrayals,
                "favors_owed_by_npc": self.rel.favors_owed_by_npc,
                "favors_owed_by_player": self.rel.favors_owed_by_player,
                "debts": self.rel.debts,
            },
            "memory": {
                "knows_name": self.memory.knows_name,
                "last_seen_day": self.memory.last_seen_day,
                "entries": [
                    {"content": e.content, "day": e.day,
                     "significance": e.significance,
                     "emotional_valence": e.emotional_valence,
                     "category": e.category}
                    for e in self.expanded_memory.entries
                ],
            },
        }
        # Inventory (weapons, tools, everyday items)
        if self.inventory:
            inv_list = []
            for item in self.inventory:
                if hasattr(item, 'id'):
                    inv_list.append({"id": item.id, "name": item.name})
            d["inventory"] = inv_list
        if self.equipped_weapon:
            d["equipped_weapon"] = self.equipped_weapon
        if self.pregnancy:
            d["pregnancy"] = {
                "conceived_day": self.pregnancy.conceived_day,
                "due_day": self.pregnancy.due_day,
                "departed_day": self.pregnancy.departed_day,
                "safe_town": self.pregnancy.safe_town,
                "child_name": self.pregnancy.child_name,
                "child_gender": self.pregnancy.child_gender,
                "delivered": self.pregnancy.delivered,
            }
        if self.children:
            d["children"] = self.children
        if self.npc_opinions:
            d["npc_opinions"] = self.npc_opinions
        d["fortune"] = self.fortune
        if self.player_debt:
            d["player_debt"] = self.player_debt
        if self.tribe:
            d["tribe"] = self.tribe
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "NPCExpanded":
        npc = cls(d["npc_id"], d["name"])
        for k in ("age", "gender", "occupation", "ethnicity", "origin",
                   "home_region", "settlement_id", "attributes", "skills",
                   "knowledge", "traits", "trait_tier", "motivations",
                   "motivation_tier", "quirks", "local_x", "local_y",
                   "world_x", "world_y", "alive", "present", "health",
                   "combat_state", "marital_status", "spouse_id",
                   "romantic_eligible", "backstory_revealed", "backstory_hidden",
                   "appearance", "schedule"):
            if k in d:
                setattr(npc, k, d[k])
        # Restore relationship
        if "rel" in d:
            r = d["rel"]
            from dataclasses import fields as _dc_fields
            valid = {f.name for f in _dc_fields(NPCRelationship)}
            npc.rel = NPCRelationship(**{k: r[k] for k in r if k in valid})
        # Restore memory
        if "memory" in d:
            m = d["memory"]
            npc.memory.knows_name = m.get("knows_name", False)
            npc.memory.last_seen_day = m.get("last_seen_day", 0)
            for e in m.get("entries", []):
                npc.expanded_memory.entries.append(MemoryEntry(**e))
        # Restore pregnancy
        if "pregnancy" in d and d["pregnancy"]:
            npc.pregnancy = PregnancyState(**d["pregnancy"])
        if "children" in d:
            npc.children = d["children"]
        if "npc_opinions" in d:
            npc.npc_opinions = d["npc_opinions"]
        npc.fortune = d.get("fortune", "average")
        npc.player_debt = d.get("player_debt", 0.0)
        npc.tribe = d.get("tribe", "")
        npc.speaks_english = d.get("speaks_english", npc._default_speaks_english())
        npc.equipped_weapon = d.get("equipped_weapon", None)
        # Restore inventory items
        if "inventory" in d:
            from src.items import make_item
            for item_d in d["inventory"]:
                try:
                    npc.inventory.append(make_item(item_d["id"]))
                except (ValueError, KeyError):
                    pass
        # Sync memory intelligence with restored attributes
        npc.expanded_memory.intelligence = npc.attributes.get("intelligence", 10)
        return npc

    # ── Context builders for conversation system ──────────────────────

    _EDUCATED_OCCUPATIONS = {
        "Doctor", "Lawyer", "Teacher", "Newspaper Editor", "Banker",
        "Assayer", "Telegraph Operator", "Preacher", "Judge",
    }

    # Occupations that imply bilingualism (speak English + native language)
    _BILINGUAL_OCCUPATIONS = {
        "Native Guide", "Native Trader", "Scout", "Interpreter",
        "Voyageur", "Fur Factor", "Brigade Leader",
    }

    def _default_speaks_english(self) -> bool:
        """Determine if NPC speaks English by default based on ethnicity/occupation."""
        # English-native ethnicities always speak English
        if self.ethnicity in ("american", "irish", "british", "other"):
            return True
        # Bilingual occupations
        if self.occupation in self._BILINGUAL_OCCUPATIONS:
            return True
        # French-Canadians in the fur trade generally spoke workable English
        if self.ethnicity == "french_canadian":
            return True
        # Germans and Mexicans at settlements usually picked up English
        if self.ethnicity in ("german", "mexican"):
            # Those working trade/service roles speak English
            if self.occupation in ("Merchant", "Teamster", "Stable Hand",
                                   "Barber", "Cook", "Blacksmith",
                                   "Carpenter", "Bartender"):
                return True
        # Chinese merchants at established camps often spoke pidgin
        if self.ethnicity == "chinese" and self.occupation == "Merchant":
            return True
        return False

    def build_speech_direction(self, language_level: str = "fluent") -> str:
        """Generate LLM instruction for how this NPC speaks."""
        parts = []

        # Ethnicity-based speech
        eth = self.ethnicity
        if eth == "native_american":
            if language_level == "sign":
                parts.append(
                    "Communicate only through gestures and single English words. "
                    "You do not speak English.")
            elif language_level == "pidgin":
                parts.append(
                    "Speak very simple broken English. Short sentences. "
                    "Drop articles. Use gestures to fill gaps.")
            else:
                parts.append(
                    "You speak English well but with Native phrasing. "
                    "Speak with dignity and directness.")
        elif eth == "french_canadian":
            parts.append(
                "Speak broken English with French words mixed in. "
                "Drop 'h' at word starts ('ave instead of have). "
                "Use 'mon ami', 'oui', 'tabernac', 'sacre bleu'.")
        elif eth == "chinese":
            parts.append(
                "Speak simple English. Drop articles (the, a). "
                "Short sentences. Occasional Chinese words.")
        elif eth == "irish":
            parts.append(
                "Irish speech patterns. Use 'ye' for 'you', "
                "'meself', 'sure', 'aye', ''tis'.")
        elif eth == "mexican":
            parts.append(
                "Mix Spanish words into English. 'Amigo', 'si', "
                "'no bueno', 'comprende'. Slightly formal.")
        elif eth == "german":
            parts.append(
                "Occasional German words. 'Ja', 'nein', 'gut'. "
                "Formal sentence structure.")

        # Occupation speech
        if self.occupation == "Preacher":
            parts.append("Quote scripture. Reference the Bible.")
        elif self.occupation in self._EDUCATED_OCCUPATIONS and \
                self.attributes.get("intelligence", 10) >= 12:
            parts.append("Speak formally. No contractions. Educated vocabulary.")

        # Trait-based speech
        traits_lower = [t.lower() for t in self.traits]
        if "taciturn" in traits_lower or "quiet" in traits_lower:
            parts.append("Man of few words. Keep answers very short.")
        if "boastful" in traits_lower:
            parts.append("Brag and exaggerate your accomplishments.")
        if "nervous" in traits_lower:
            parts.append("Anxious. Stammer occasionally. Second-guess yourself.")
        if "cruel" in traits_lower:
            parts.append("Cold and mean-spirited. Enjoy others' misfortune.")
        if "melancholy" in traits_lower or "grief" in traits_lower:
            parts.append("Sad and weary. Speak with heavy resignation.")
        if "charming" in traits_lower:
            parts.append("Smooth and likeable. Easy wit.")

        return " ".join(parts) if parts else ""

    def build_mood_context(self, time_period: str = "day",
                           weather: str = "clear") -> str:
        """Describe NPC's current mood and situation for LLM."""
        parts = []

        # Wounds
        if hasattr(self, 'wounds') and self.wounds and \
                hasattr(self.wounds, 'wounds') and self.wounds.wounds:
            from src.health_system import PART_DATA
            worst = self.wounds.wounds[0]
            part_label = PART_DATA.get(worst.part, {}).get("label", worst.part)
            if worst.is_bleeding:
                parts.append(f"You are bleeding from a wound on your {part_label}.")
            elif worst.infected:
                parts.append(f"You have an infected wound on your {part_label}. You feel feverish.")
            else:
                parts.append(f"You are hurt — wounded on your {part_label}.")

        # Fortune
        if self.fortune == "destitute":
            parts.append("You are starving and desperate. You have nothing.")
        elif self.fortune == "struggling":
            parts.append("Times are hard. You are barely scraping by.")
        elif self.fortune == "wealthy":
            parts.append("Business is good. You are in high spirits.")

        # Weather + time combos
        if weather == "blizzard":
            parts.append("A blizzard howls outside. You are freezing.")
        elif weather == "snow" and time_period == "night":
            parts.append("It is a cold, snowy night.")
        elif weather == "rain":
            parts.append("Rain is falling. You are damp and uncomfortable.")
        elif weather == "thunderstorm":
            parts.append("Thunder rumbles. The storm makes you uneasy.")
        elif weather == "hot":
            parts.append("The heat is oppressive.")
        elif weather == "fog":
            parts.append("Fog hangs thick. Visibility is poor.")

        if time_period == "night" and weather not in ("blizzard", "snow"):
            parts.append("It is nighttime.")
        elif time_period == "dawn":
            parts.append("It is early morning.")

        # Recent negative memory
        if hasattr(self, 'expanded_memory'):
            for mem in self.expanded_memory.get_recent(3):
                if mem.emotional_valence < -0.5 and mem.significance > 0.5:
                    parts.append(f"Something weighs on you: {mem.content}")
                    break

        return " ".join(parts) if parts else ""

    def build_lying_instruction(self) -> str:
        """If NPC has secrets and trust is low, instruct LLM to be evasive."""
        trust = self.rel.trust if hasattr(self, 'rel') else 0
        traits_lower = [t.lower() for t in self.traits]

        # Find secret backstory items
        secrets = [b for b in self.backstory_hidden
                   if any(w in b.lower() for w in
                          ("warrant", "killed", "hidden gold", "addiction",
                           "laudanum", "bounty", "deserted", "prison",
                           "can't read", "phobia", "writes to dead"))]

        if not secrets and "pathological_liar" not in traits_lower:
            return ""

        if "pathological_liar" in traits_lower:
            return ("You are a pathological liar. Lie about everything — your past, "
                    "your name, your occupation. Make up stories. Never tell the truth "
                    "about yourself even if asked directly.")

        secret = secrets[0] if secrets else "a dark secret"

        if trust < 30:
            return (f"You have a secret: {secret}. Do NOT reveal it under any "
                    f"circumstances. If asked personal questions, change the subject, "
                    f"give a vague answer, or get uncomfortable. You are guarded.")
        elif trust < 60:
            return (f"You have something weighing on you: {secret}. You might "
                    f"hint at it vaguely if the conversation gets personal, "
                    f"but you will not give details.")
        else:
            return (f"You trust this person deeply. If they ask, you can confide "
                    f"your secret: {secret}. It is a relief to finally tell someone.")

    def is_wounded(self) -> bool:
        """Check for active wounds."""
        if not hasattr(self, 'wounds') or not self.wounds:
            return False
        return bool(hasattr(self.wounds, 'wounds') and self.wounds.wounds)

    def is_drunk(self, time_period: str = "day") -> bool:
        """Check if NPC is likely drunk."""
        traits_lower = [t.lower() for t in self.traits]
        if "drunk" in traits_lower or "drunkard" in traits_lower:
            return True
        # Check inventory for whiskey
        for item in self.inventory:
            if "whiskey" in item.name.lower() or "rum" in item.name.lower():
                if time_period in ("dusk", "night"):
                    return True
        return False


# ============================================================================
#  NPC GENERATOR
# ============================================================================

class NPCGenerator:
    """
    Settlement-aware NPC generation using npc_data tables.
    Produces NPCExpanded objects with full personality, motivations,
    backstory, and relationship scaffolding.
    """

    def __init__(self, seed: int = 42, year: int = 1849):
        self.seed = seed
        self.year = year
        self.npcs: Dict[str, NPCExpanded] = {}
        self._counter: int = 0

    def _next_id(self, prefix: str = "npc") -> str:
        self._counter += 1
        return f"{prefix}_{self._counter}"

    # ── Settlement population ──────────────────────────────────────────

    def populate_settlement(self, settlement_type: str,
                             wx: int, wy: int, year: int,
                             location_name: str = "",
                             ax: int = 7, ay: int = 7
                             ) -> List[NPCExpanded]:
        """
        Generate or retrieve NPCs for a settlement at (wx, wy, ax, ay).
        Deterministic per position — same patch always gets same NPCs.
        """
        tile_seed = self.seed + wx * 100007 + wy * 1000003 + ax * 101 + ay
        rng = random.Random(tile_seed)

        sett = SETTLEMENTS.get(settlement_type, SETTLEMENTS["mining_camp_small"])
        lo, hi = sett["named_npc_range"]
        count = rng.randint(lo, hi)

        spawned: List[NPCExpanded] = []
        for i in range(count):
            npc_id = f"sett_{wx}_{wy}_{ax}_{ay}_{i}"
            if npc_id in self.npcs:
                npc = self.npcs[npc_id]
                npc.present = True
                spawned.append(npc)
                continue

            npc = self._generate_one(npc_id, rng, settlement_type, sett,
                                      wx, wy, location_name)
            self.npcs[npc_id] = npc
            spawned.append(npc)

        return spawned

    def populate_wilderness(self, wx: int, wy: int,
                             terrain: int, year: int,
                             ax: int = 7, ay: int = 7
                             ) -> List[NPCExpanded]:
        """
        Sparse wilderness population — 0 to 3 NPCs (mostly lone prospectors).
        """
        tile_seed = self.seed + wx * 100007 + wy * 1000003 + ax * 101 + ay + 7
        rng = random.Random(tile_seed)

        count = rng.choices([0, 1, 2, 3], weights=[50, 30, 15, 5])[0]
        sett = SETTLEMENTS["mining_camp_small"]

        spawned: List[NPCExpanded] = []
        for i in range(count):
            npc_id = f"wild_{wx}_{wy}_{ax}_{ay}_{i}"
            if npc_id in self.npcs:
                npc = self.npcs[npc_id]
                npc.present = True
                spawned.append(npc)
                continue

            npc = self._generate_one(npc_id, rng, "mining_camp_small", sett,
                                      wx, wy, "")
            self.npcs[npc_id] = npc
            spawned.append(npc)

        return spawned

    # ── Core generation ────────────────────────────────────────────────

    def _generate_one(self, npc_id: str, rng: random.Random,
                       settlement_type: str, sett: dict,
                       wx: int, wy: int, location_name: str
                       ) -> NPCExpanded:
        """Generate a single NPC with all systems populated."""

        # Gender (from demographics)
        is_male = rng.random() < sett["male_ratio"]
        gender = "M" if is_male else "F"

        # Ethnicity — era-appropriate demographics
        from src.npc_data import ORIGIN_WEIGHTS_LONG_HUNTER, ORIGIN_WEIGHTS_MOUNTAIN_MEN
        if self.year < 1810:
            _weights = ORIGIN_WEIGHTS_LONG_HUNTER
        elif self.year < 1845:
            _weights = ORIGIN_WEIGHTS_MOUNTAIN_MEN
        else:
            _weights = ORIGIN_WEIGHTS
        ethnicity = _pick_weighted(rng, _weights)

        # Name
        if gender == "M":
            first = rng.choice(NAMES_M.get(ethnicity, NAMES_M["american"]))
        else:
            first = rng.choice(NAMES_F.get(ethnicity, NAMES_F["american"]))
        last = rng.choice(LAST_NAMES.get(ethnicity, LAST_NAMES["american"]))
        name = f"{first} {last}"

        # Age (gaussian, clamped)
        age = int(rng.gauss(sett["age_mean"], sett["age_std"]))
        age = max(sett["age_min"], min(sett["age_max"], age))

        # Origin homeland
        homeland = rng.choice(ORIGIN_HOMELANDS.get(ethnicity, ["Unknown"]))

        # Profession
        if gender == "M":
            weights = PROF_WEIGHTS_M.get(settlement_type,
                                          PROF_WEIGHTS_M["mining_camp_small"])
        else:
            weights = PROF_WEIGHTS_F.get(settlement_type,
                                          PROF_WEIGHTS_F["mining_camp_small"])
        occupation = _pick_profession(rng, weights)

        # Attributes: base 8 + 1d4 + profession bias
        attrs = {}
        for stat in ("strength", "agility", "intelligence",
                     "wisdom", "charisma", "constitution"):
            attrs[stat] = 8 + rng.randint(1, 4)
        for stat, bonus in PROF_ATTR_BIAS.get(occupation, {}).items():
            attrs[stat] = min(18, attrs.get(stat, 10) + bonus)

        # Skills
        skills = dict(PROF_SKILLS.get(occupation, {}))
        extra = rng.choice(list(PROF_SKILLS.get("Drifter", {"survival": 1}).keys()))
        skills[extra] = skills.get(extra, 0) + rng.randint(1, 2)

        # Knowledge
        knowledge = dict(PROF_KNOWLEDGE.get(occupation, {}))
        for k in rng.sample(PERSONAL_KNOWLEDGE_POOL,
                            k=min(len(PERSONAL_KNOWLEDGE_POOL), rng.randint(1, 3))):
            knowledge[k] = rng.randint(1, 2)

        # Personality traits (2-4 traits, tiered by rarity)
        trait_count = rng.randint(2, 4)
        traits: List[str] = []
        worst_tier = "common"
        for _ in range(trait_count):
            tier_name = _pick_trait_tier(rng)
            if TRAIT_TIERS[tier_name]["weight"] < TRAIT_TIERS[worst_tier]["weight"]:
                worst_tier = tier_name
            pool = [t for t in TRAIT_TIERS[tier_name]["traits"]
                    if t not in traits and not _contradicts(t, traits)]
            if pool:
                traits.append(rng.choice(pool))

        # Hidden motivations (1-2, tiered)
        mot_count = rng.randint(1, 2)
        motivations: List[str] = []
        mot_tier = "common"
        for _ in range(mot_count):
            tn = _pick_motivation_tier(rng)
            if MOTIVATION_TIERS[tn]["weight"] < MOTIVATION_TIERS[mot_tier]["weight"]:
                mot_tier = tn
            pool = [m for m in MOTIVATION_TIERS[tn]["motivations"]
                    if m not in motivations]
            if pool:
                motivations.append(rng.choice(pool))

        # Quirks (0-2)
        quirk_count = rng.choices([0, 1, 2], weights=[40, 45, 15])[0]
        quirks = rng.sample(QUIRK_POOL,
                            k=min(len(QUIRK_POOL), quirk_count))

        # Backstory hidden elements
        backstory_hidden = []
        for cat in ("family", "past"):
            pool = BACKSTORY_HOOKS.get(cat, [])
            if pool:
                entry = rng.choice(pool)
                backstory_hidden.append(entry.replace("{homeland}", homeland))
        if rng.random() < 0.25:  # 25% chance of a secret
            pool = BACKSTORY_HOOKS.get("secret", [])
            if pool:
                backstory_hidden.append(rng.choice(pool))

        # Marital status
        if gender == "F" and occupation == "Wife":
            marital = "married"
        elif age > 25 and rng.random() < 0.35:
            marital = "married"
        elif age > 30 and rng.random() < 0.15:
            marital = "widowed"
        else:
            marital = "single"

        # Romance eligibility
        romantic_eligible = (
            marital in ("single", "widowed") and
            age >= 18 and
            "psychopathic" not in traits
        )

        # Schedule by occupation
        schedule = _make_schedule(occupation)

        npc = NPCExpanded(
            npc_id=npc_id, name=name,
            age=age, gender=gender, occupation=occupation,
            ethnicity=ethnicity, origin=homeland,
            home_region=location_name or "frontier",
            settlement_id=f"{settlement_type}_{wx}_{wy}",
            attributes=attrs, skills=skills, knowledge=knowledge,
            traits=traits, trait_tier=worst_tier,
            motivations=motivations, motivation_tier=mot_tier,
            quirks=quirks,
            backstory_hidden=backstory_hidden,
            marital_status=marital,
            romantic_eligible=romantic_eligible,
            schedule=schedule,
        )
        npc.world_x = wx
        npc.world_y = wy
        return npc

    # ── Lookup ─────────────────────────────────────────────────────────

    def get(self, npc_id: str) -> Optional[NPCExpanded]:
        return self.npcs.get(npc_id)

    def get_at(self, x: int, y: int) -> Optional[NPCExpanded]:
        for npc in self.npcs.values():
            if npc.present and npc.local_x == x and npc.local_y == y:
                return npc
        return None

    def npcs_on_tile(self, wx: int, wy: int,
                     ax: int = 7, ay: int = 7) -> List[NPCExpanded]:
        prefix_sett = f"sett_{wx}_{wy}_{ax}_{ay}_"
        prefix_wild = f"wild_{wx}_{wy}_{ax}_{ay}_"
        return [n for n in self.npcs.values()
                if n.present and
                (n.npc_id.startswith(prefix_sett) or
                 n.npc_id.startswith(prefix_wild))]

    def npcs_on_map(self) -> List[NPCExpanded]:
        return [n for n in self.npcs.values() if n.present]


# ============================================================================
#  GOSSIP SYSTEM
# ============================================================================

@dataclass
class GossipEntry:
    """A piece of gossip circulating in a region."""
    content: str                # "That prospector stole from Johnson's store"
    day: int
    region: str                 # which region
    severity: float = 0.0       # -1.0 terrible → +1.0 heroic
    spread_count: int = 1       # how many NPCs have heard this
    source_npc_id: str = ""


class GossipSystem:
    """
    Tracks gossip by region.  When the player does something notable,
    add a GossipEntry.  When the player meets a new NPC in that region,
    there's a probability they've heard the gossip and it pre-adjusts
    their relationship.
    """

    def __init__(self):
        self.entries: List[GossipEntry] = []

    def add(self, content: str, day: int, region: str,
            severity: float, source_id: str = "") -> None:
        self.entries.append(GossipEntry(
            content=content, day=day, region=region,
            severity=severity, source_npc_id=source_id,
        ))

    def apply_to_new_npc(self, npc: NPCExpanded, region: str,
                          current_day: int, rng: random.Random) -> List[str]:
        """
        When first meeting an NPC, check if they've heard gossip about
        the player.  Returns list of gossip strings they mention.
        """
        heard: List[str] = []
        for g in self.entries:
            if g.region != region:
                continue
            # Probability of having heard it: based on severity, spread, age
            age_days = max(1, current_day - g.day)
            prob = min(0.8, abs(g.severity) * 0.3 + g.spread_count * 0.02)
            # Old gossip fades
            prob *= max(0.1, 1.0 - age_days / 360.0)
            if rng.random() < prob:
                # Pre-adjust relationship
                npc.rel.adjust(affinity=g.severity * 8,
                               trust=g.severity * 4,
                               respect=g.severity * 5)
                g.spread_count += 1
                heard.append(g.content)
        return heard

    def decay(self, current_day: int) -> None:
        """Remove gossip older than a year."""
        self.entries = [g for g in self.entries
                        if current_day - g.day < 365]


# ============================================================================
#  BACKGROUND SIMULATION
# ============================================================================

@dataclass
class BackgroundEvent:
    """Something that happened to an NPC during time passage."""
    npc_id: str
    npc_name: str
    event_type: str     # "letter" | "moved" | "sick" | "died" | "found_gold"
                        # | "gossip" | "pregnant_depart" | "child_born"
    description: str    # human-readable text for the player
    day: int
    affects_player: bool = False   # if True, show as a message/letter


class BackgroundSimulator:
    """
    Simulates what important NPCs do during time passage.
    Called from engine when significant time elapses (sleep, travel).

    Only simulates NPCs the player has a meaningful relationship with
    (affinity > 20 or < -20, or status beyond "stranger").
    """

    def simulate(self, days: int, current_day: int,
                  npcs: Dict[str, NPCExpanded],
                  rng: random.Random) -> List[BackgroundEvent]:
        events: List[BackgroundEvent] = []

        for npc in npcs.values():
            if not npc.alive:
                continue
            # Only simulate meaningful relationships
            if (abs(npc.rel.affinity) < 20 and
                npc.rel.status == "stranger"):
                continue

            # ── Spouse-specific events ──
            if npc.rel.status == "married":
                events.extend(self._sim_spouse(npc, days, current_day, rng))

            # ── Friend events ──
            if npc.rel.affinity > 30:
                events.extend(self._sim_friend(npc, days, current_day, rng))

            # ── Rival events ──
            if npc.rel.affinity < -30:
                events.extend(self._sim_rival(npc, days, current_day, rng))

            # ── Random life events (anyone important) ──
            events.extend(self._sim_random(npc, days, current_day, rng))

            # ── Memory decay ──
            npc.expanded_memory.decay(current_day, days)

        # ── NPC-to-NPC opinion formation ──
        events.extend(self._sim_npc_opinions(npcs, current_day, rng))

        return events

    def _sim_spouse(self, npc: NPCExpanded, days: int,
                     current_day: int, rng: random.Random
                     ) -> List[BackgroundEvent]:
        events = []

        # Check pregnancy departure
        if npc.pregnancy and npc.pregnancy.should_depart(current_day):
            npc.pregnancy.departed_day = current_day
            npc.pregnancy.safe_town = "Sacramento"  # engine should set real town
            npc.present = False
            events.append(BackgroundEvent(
                npc.npc_id, npc.name, "pregnant_depart",
                f"{npc.name} has departed for {npc.pregnancy.safe_town} "
                f"to stay with family until the baby is born.",
                current_day, affects_player=True,
            ))

        # Check birth
        if npc.pregnancy and npc.pregnancy.is_due(current_day):
            npc.pregnancy.delivered = True
            child = {
                "name": npc.pregnancy.child_name,
                "gender": npc.pregnancy.child_gender,
                "birth_day": current_day,
            }
            npc.children.append(child)
            events.append(BackgroundEvent(
                npc.npc_id, npc.name, "child_born",
                f"A letter arrives: {npc.name} has given birth to a healthy "
                f"{'boy' if child['gender'] == 'M' else 'girl'} "
                f"named {child['name']}.",
                current_day, affects_player=True,
            ))

        # Chance of letter from spouse (every ~30 days)
        if days >= 7 and rng.random() < days / 45.0:
            events.append(BackgroundEvent(
                npc.npc_id, npc.name, "letter",
                f"A letter from {npc.name}.",
                current_day, affects_player=True,
            ))

        return events

    def _sim_friend(self, npc: NPCExpanded, days: int,
                     current_day: int, rng: random.Random
                     ) -> List[BackgroundEvent]:
        events = []
        # Friends occasionally send word (every ~60 days)
        if days >= 14 and rng.random() < days / 90.0:
            events.append(BackgroundEvent(
                npc.npc_id, npc.name, "friend_letter",
                f"Word from {npc.name}: they've been "
                f"{rng.choice(['working a new claim', 'doing well', 'laid up sick but recovering', 'thinking of heading home'])}.",
                current_day, affects_player=True,
            ))
        return events

    def _sim_rival(self, npc: NPCExpanded, days: int,
                    current_day: int, rng: random.Random
                    ) -> List[BackgroundEvent]:
        events = []
        # Rivals occasionally cause trouble (every ~90 days)
        if days >= 20 and rng.random() < days / 120.0:
            actions = [
                "has been spreading ugly rumors about you",
                "was seen near your claim",
                "told the sheriff you owe money",
                "got into a fight at the saloon, mentioned your name",
            ]
            events.append(BackgroundEvent(
                npc.npc_id, npc.name, "gossip",
                f"You hear that {npc.name} {rng.choice(actions)}.",
                current_day, affects_player=True,
            ))
        return events

    def _sim_random(self, npc: NPCExpanded, days: int,
                     current_day: int, rng: random.Random
                     ) -> List[BackgroundEvent]:
        events = []
        # Small chance of major life event (per 30 days)
        if days < 7 or rng.random() > days / 300.0:
            return events

        roll = rng.random()
        if roll < 0.02:  # 2% death (accident, disease)
            npc.alive = False
            npc.present = False
            cause = rng.choice([
                "fever", "a mining accident", "cholera",
                "a gunshot wound", "drowning", "exposure",
            ])
            events.append(BackgroundEvent(
                npc.npc_id, npc.name, "died",
                f"Sad news: {npc.name} has died of {cause}.",
                current_day, affects_player=True,
            ))
        elif roll < 0.08:  # 6% sick — disease with type
            diseases = ["fever", "dysentery", "cholera", "ague"]
            disease = rng.choice(diseases)
            # Cholera/dysentery can become epidemic
            fatal = disease in ("cholera",) and rng.random() < 0.15
            if fatal:
                npc.alive = False
                npc.present = False
                events.append(BackgroundEvent(
                    npc.npc_id, npc.name, "died",
                    f"{npc.name} has died of {disease}.",
                    current_day, affects_player=True,
                ))
            else:
                events.append(BackgroundEvent(
                    npc.npc_id, npc.name, "sick",
                    f"{npc.name} has taken ill with {disease}.",
                    current_day, affects_player=False,
                ))
        elif roll < 0.14:  # 6% moved — NPC migrates to another area
            npc.present = False
            destinations = [
                "upriver", "downstream", "the next valley",
                "a new strike", "back east", "the nearest town",
                "the mountains", "California",
            ]
            dest = rng.choice(destinations)
            events.append(BackgroundEvent(
                npc.npc_id, npc.name, "moved",
                f"{npc.name} has packed up and headed for {dest}.",
                current_day, affects_player=True,
            ))
        elif roll < 0.20:  # 6% found gold
            if npc.fortune in ("destitute", "struggling", "average"):
                npc.fortune = rng.choice(["comfortable", "comfortable", "wealthy"])
            elif npc.fortune == "comfortable":
                npc.fortune = "wealthy"
            events.append(BackgroundEvent(
                npc.npc_id, npc.name, "found_gold",
                f"Word is {npc.name} made a nice find recently.",
                current_day, affects_player=False,
            ))
        elif roll < 0.26:  # 6% fortune change (decline)
            if npc.fortune in ("comfortable", "wealthy", "average"):
                prev = npc.fortune
                npc.fortune = {"wealthy": "comfortable", "comfortable": "average",
                               "average": "struggling"}.get(prev, "struggling")
                events.append(BackgroundEvent(
                    npc.npc_id, npc.name, "fortune_change",
                    f"{npc.name} has fallen on harder times lately.",
                    current_day, affects_player=False,
                ))
        elif roll < 0.40:  # 14% mishap — darkly comic frontier incidents
            traits_l = [t.lower() for t in npc.traits]
            occ = npc.occupation.lower()
            mishaps = [
                f"{npc.name} got drunk and fell in the creek. Lost his boots.",
                f"{npc.name} shot at a rabbit and hit somebody's mule. "
                f"The owner is furious.",
                f"{npc.name} got into a fistfight over a card game. "
                f"Both men lost teeth.",
                f"{npc.name} tried to ford the river with a loaded pack mule. "
                f"The mule refused. The supplies didn't.",
                f"{npc.name} accidentally set his tent on fire while cooking.",
                f"{npc.name} lost three days' worth of gold dust "
                f"in a poker game. Hasn't stopped talking about it.",
                f"{npc.name} was chased up a tree by a bear. "
                f"Stayed up there till morning.",
                f"{npc.name} ate something he shouldn't have. "
                f"Been behind a bush all day.",
                f"{npc.name}'s claim got jumped while he was in town "
                f"buying whiskey.",
                f"{npc.name} got his beard caught in a sluice box. "
                f"Had to cut himself free.",
                f"A raccoon got into {npc.name}'s supplies. "
                f"Ate everything except the hardtack.",
                f"{npc.name} told everyone he found a vein of gold. "
                f"It was iron pyrite. Nobody will let him forget it.",
                f"{npc.name} bet his best knife in a poker game and lost. "
                f"Won it back the next hand, then lost it again.",
                f"{npc.name} got spooked by a rattlesnake and fired his "
                f"rifle into the ground. Ruined his only pair of good pants.",
                f"{npc.name} tried to break a wild horse. "
                f"The horse broke {npc.name} instead. He's limping.",
                f"{npc.name} passed out drunk and somebody swapped his boots "
                f"for a pair two sizes too small.",
                f"{npc.name} tried to bluff at poker with a pair of twos. "
                f"The other man had a full house and a knife.",
                f"{npc.name} dug a privy too close to his tent. "
                f"Nobody will camp near him now.",
                f"{npc.name} bought a 'genuine treasure map' for five dollars. "
                f"It led to an empty hole somebody already dug.",
                f"{npc.name} accidentally fired his gun inside the saloon. "
                f"Hit the chandelier. Got banned.",
                f"{npc.name} fell asleep on watch. A coyote ate his dinner.",
                f"{npc.name} tried to distill his own whiskey. "
                f"The still exploded. He's missing an eyebrow.",
                f"{npc.name} got kicked by a mule. In the face. "
                f"He's fine but his pride isn't.",
                f"{npc.name} traded a good rifle for what he thought was a gold nugget. "
                f"It was brass.",
                f"{npc.name} tried to smoke out a skunk from under his tent. "
                f"Everyone within a hundred yards knows how that went.",
                f"{npc.name} staked a claim on land that turned out to be "
                f"somebody else's outhouse.",
                f"{npc.name} wrote a love letter to a woman back east. "
                f"The postmaster read it out loud to the whole camp.",
                f"{npc.name}'s pants split while climbing a hill. "
                f"He worked the rest of the day in a blanket.",
                f"{npc.name} challenged a man to a duel. The man laughed. "
                f"{npc.name} also laughed. Then they both went to the saloon.",
                f"A crow stole {npc.name}'s only spoon. He eats with a stick now.",
            ]
            # Trait-specific mishaps
            if "greedy" in traits_l:
                mishaps.append(
                    f"{npc.name} tried to steal from a sleeping man's claim. "
                    f"The man wasn't sleeping.")
            if "boastful" in traits_l:
                mishaps.append(
                    f"{npc.name} told everyone he could outshoot any man alive. "
                    f"Lost the contest to a schoolteacher. Hasn't spoken since.")
            if "nervous" in traits_l:
                mishaps.append(
                    f"{npc.name} heard a noise at night and shot a hole through "
                    f"his own tent. It was a squirrel.")
            if "devout" in traits_l:
                mishaps.append(
                    f"{npc.name} tried to baptize a miner in the creek. "
                    f"The miner punched him.")
            if "drunk" in traits_l or "drunkard" in traits_l:
                mishaps.append(
                    f"{npc.name} passed out drunk in the road. "
                    f"Someone drew a mustache on his face with axle grease.")

            msg = rng.choice(mishaps)
            events.append(BackgroundEvent(
                npc.npc_id, npc.name, "mishap", msg,
                current_day, affects_player=False,
            ))
            # Some mishaps affect fortune
            if "lost" in msg or "supplies" in msg or "gold dust" in msg:
                if npc.fortune in ("comfortable", "wealthy", "average"):
                    npc.fortune = {"wealthy": "comfortable",
                                   "comfortable": "average",
                                   "average": "struggling"}.get(npc.fortune,
                                                                "struggling")
        return events

    def _sim_npc_opinions(self, npcs: Dict[str, NPCExpanded],
                           current_day: int, rng: random.Random
                           ) -> List[BackgroundEvent]:
        """NPCs form opinions of each other based on proximity and traits."""
        events = []
        npc_list = [n for n in npcs.values() if n.alive and n.present]
        for npc in npc_list:
            if rng.random() > 0.1:  # only 10% chance per sim tick
                continue
            # Pick a random other NPC in the same area
            neighbors = [o for o in npc_list
                         if o.npc_id != npc.npc_id
                         and o.world_x == npc.world_x
                         and o.world_y == npc.world_y
                         and o.npc_id not in npc.npc_opinions]
            if not neighbors:
                continue
            other = rng.choice(neighbors)

            # Generate opinion based on trait compatibility
            npc_traits = set(npc.traits)
            other_traits = set(other.traits)
            opinion = rng.uniform(-15, 15)  # baseline random

            # Trait synergies
            if "generous" in other_traits:
                opinion += 15
            if "cruel" in other_traits or "psychopathic" in other_traits:
                opinion -= 25
            if "charming" in other_traits:
                opinion += 10
            if "greedy" in other_traits and "generous" in npc_traits:
                opinion -= 20
            if "devout" in npc_traits and "devout" in other_traits:
                opinion += 15
            if "suspicious" in npc_traits:
                opinion -= 10

            # Same occupation = rivalry or camaraderie
            if npc.occupation == other.occupation:
                opinion += rng.choice([-15, -10, 10, 15])

            opinion = max(-100, min(100, opinion))
            reasons = []
            if opinion > 30:
                reasons = [f"seems like good folk", f"we get along fine",
                           f"been helpful around camp"]
            elif opinion > 0:
                reasons = [f"decent enough", f"keeps to himself",
                           f"haven't had trouble"]
            elif opinion > -30:
                reasons = [f"something off about that one",
                           f"don't fully trust him", f"keeps odd hours"]
            else:
                reasons = [f"bad reputation", f"caused trouble around here",
                           f"wouldn't turn my back on him"]

            npc.set_opinion(other.npc_id, opinion, rng.choice(reasons),
                           name=other.name)
        return events


# ============================================================================
#  LLM CONTEXT BUILDER
# ============================================================================

def build_npc_llm_context(npc: NPCExpanded, player=None) -> str:
    """
    Build the NPC identity + personality block passed to the LLM for
    dialogue generation.  Extends the existing _npc_context_block with
    motivation hints, quirks, and expanded relationship data.
    """
    traits_str = ", ".join(npc.traits) or "unremarkable"
    known_str  = ", ".join(f"{k} ({v})" for k, v in npc.knowledge.items()) or "none"
    hidden_str = ". ".join(npc.backstory_hidden)
    quirks_str = "; ".join(npc.quirks) if npc.quirks else "none"
    motivations_str = "; ".join(npc.motivations) if npc.motivations else "undetermined"

    rel = npc.rel
    rel_str = (
        f"Affinity: {rel.affinity:.0f}/100 ({rel.affinity_label()})  "
        f"Trust: {rel.trust:.0f}  Respect: {rel.respect:.0f}  "
        f"Fear: {rel.fear:.0f}"
    )
    if rel.romantic > 10:
        rel_str += f"  Romantic: {rel.romantic:.0f} ({rel.romantic_label()})"
    rel_str += f"  Status: {rel.status}"

    # Important memories about the player
    important = npc.expanded_memory.get_important(3)
    mem_str = "; ".join(e.content for e in important) if important else "nothing notable"

    player_block = ""
    if player is not None:
        cha = player.attributes.get("charisma", 10)
        cha_desc = ("silver-tongued" if cha >= 16
                    else "personable" if cha >= 13
                    else "average" if cha >= 9
                    else "abrasive" if cha >= 6
                    else "deeply off-putting")
        player_block = (
            f"\nPLAYER CONTEXT:\n"
            f"  Charisma: {cha}/18 ({cha_desc})\n"
            f"  Trading: {player.skills.get('trading', 0)}  "
            f"Law: {player.skills.get('law', 0)}"
        )

    gender_str = {"M": "Male", "F": "Female"}.get(npc.gender, "Male")
    # Tribe and marital info
    tribe_str = f"  Tribe: {npc.tribe}\n" if npc.tribe else ""
    marital_str = ""
    ms = getattr(npc, 'marital_status', 'single')
    if ms != "single":
        spouse = getattr(npc, 'spouse_id', '')
        marital_str = f"  Marital status: {ms}"
        if spouse:
            marital_str += f" (spouse: {spouse})"
        marital_str += "\n"

    # Wounds
    wound_str = ""
    if hasattr(npc, 'wounds') and npc.wounds and \
            hasattr(npc.wounds, 'wounds') and npc.wounds.wounds:
        wound_parts = []
        for w in npc.wounds.wounds[:3]:
            from src.health_system import PART_DATA
            p_label = PART_DATA.get(w.part, {}).get("label", w.part)
            wound_parts.append(f"{w.description} on {p_label}")
        wound_str = f"  Current wounds: {'; '.join(wound_parts)}\n"

    context = (
        f"NPC IDENTITY:\n"
        f"  Name: {npc.name}\n"
        f"  Age: {npc.age}  Gender: {gender_str}\n"
        f"  Occupation: {npc.occupation}\n"
        f"  Ethnicity: {npc.ethnicity} (from {npc.origin})\n"
        f"{tribe_str}"
        f"  Personality traits: {traits_str}\n"
        f"  Behavioral quirks: {quirks_str}\n"
        f"  Hidden motivations (inform tone, don't state directly): {motivations_str}\n"
        f"  Knowledge: {known_str}\n"
        f"  Relationship with player: {rel_str}\n"
        f"  Memories of player: {mem_str}\n"
        f"  Background (not yet revealed): {hidden_str}\n"
        f"  Revealed backstory: {'. '.join(npc.backstory_revealed) or 'nothing yet'}\n"
        f"  Current fortune: {npc.fortune}\n"
        f"{marital_str}"
        f"{wound_str}"
        f"{player_block}"
    )

    # Add opinions of other NPCs
    if npc.npc_opinions:
        opinion_lines = []
        for oid, od in list(npc.npc_opinions.items())[:5]:
            op = od["opinion"]
            label = ("hates" if op < -50 else "dislikes" if op < -15
                     else "neutral toward" if op < 15
                     else "likes" if op < 50 else "respects")
            oname = od.get("name", oid)
            opinion_lines.append(f"  {label} {oname}: {od['reason']}")
        if opinion_lines:
            context += "\nOPINIONS OF OTHERS:\n" + "\n".join(opinion_lines)

    # Add favor/debt context
    if npc.rel.debts:
        context += "\nFAVORS/DEBTS:\n  " + "\n  ".join(npc.rel.debts[-3:])

    return context


# ============================================================================
#  INSIGHT CHECK  (player skill → NPC perception)
# ============================================================================

def insight_check(player, npc: NPCExpanded) -> str:
    """
    Based on player Wisdom + Intelligence, return what they can perceive
    about the NPC's hidden personality and motivations.

    Returns a string the engine can display as a message.
    Higher skill = more accurate and detailed read.
    """
    wis = player.attributes.get("wisdom", 10)
    intel = player.attributes.get("intelligence", 10)
    score = (wis + intel) // 2  # average of wisdom and intelligence

    lines: List[str] = []

    # Tier 1: basic read (score >= 8 — almost everyone)
    if score >= 8:
        tier = npc.trait_tier
        if tier == "rare":
            lines.append(f"Something feels deeply off about {npc.display_name()}.")
        elif tier == "uncommon":
            lines.append(f"{npc.display_name()} seems more complex than most.")
        else:
            lines.append(f"{npc.display_name()} seems like an ordinary sort.")

    # Tier 2: trait hints (score >= 11)
    if score >= 11 and npc.traits:
        # Reveal 1 trait
        lines.append(f"You sense they are {npc.traits[0]}.")

    # Tier 3: motivation hint (score >= 14)
    if score >= 14 and npc.motivations:
        mot = npc.motivations[0]
        # Vague version of the motivation
        if "gold" in mot or "rich" in mot:
            lines.append("Their eyes light up at any mention of gold.")
        elif "escape" in mot or "run" in mot or "flee" in mot:
            lines.append("They seem like someone running from something.")
        elif "revenge" in mot or "kill" in mot or "murder" in mot:
            lines.append("There's a dangerous edge behind their eyes.")
        elif "family" in mot or "provide" in mot:
            lines.append("They carry the weight of people depending on them.")
        elif "debt" in mot:
            lines.append("They have the hunted look of someone who owes money.")
        elif "religious" in mot or "mission" in mot:
            lines.append("They carry themselves with an unusual sense of purpose.")
        else:
            lines.append("You can't quite read their deeper motives.")

    # Tier 4: full read (score >= 17 — rare, very perceptive)
    if score >= 17:
        if len(npc.traits) > 1:
            lines.append(f"You also notice they are {npc.traits[1]}.")
        if len(npc.motivations) > 1:
            lines.append(f"You suspect they also want to {npc.motivations[1]}.")
        if npc.rel.fear > 20:
            lines.append("They seem afraid of you.")
        if npc.rel.romantic > 20:
            lines.append("You catch them looking at you with interest.")

    return " ".join(lines) if lines else f"You can't get a read on {npc.display_name()}."


# ============================================================================
#  PRIVATE HELPERS
# ============================================================================

def _pick_weighted(rng: random.Random,
                    weights: list) -> str:
    """Pick from a list of (key, cumulative_threshold) tuples."""
    if not weights:
        return ""
    roll = rng.random()
    for key, threshold in weights:
        if roll < threshold:
            return key
    return weights[-1][0]


def _pick_profession(rng: random.Random, weights: Dict[str, int]) -> str:
    """Weighted random profession selection."""
    if not weights:
        return "Prospector"
    items = list(weights.items())
    total = sum(w for _, w in items)
    if total <= 0:
        return items[0][0]
    roll = rng.random() * total
    cumul = 0
    for prof, w in items:
        cumul += w
        if roll < cumul:
            return prof
    return items[-1][0]


def _pick_trait_tier(rng: random.Random) -> str:
    roll = rng.random() * 100
    cumul = 0
    for tier_name, tier_data in TRAIT_TIERS.items():
        cumul += tier_data["weight"]
        if roll < cumul:
            return tier_name
    return "common"


def _pick_motivation_tier(rng: random.Random) -> str:
    roll = rng.random() * 100
    cumul = 0
    for tier_name, tier_data in MOTIVATION_TIERS.items():
        cumul += tier_data["weight"]
        if roll < cumul:
            return tier_name
    return "common"


def _contradicts(trait: str, existing: List[str]) -> bool:
    """Check if trait contradicts any existing trait."""
    for a, b in TRAIT_CONTRADICTIONS:
        if (trait == a and b in existing) or (trait == b and a in existing):
            return True
    return False


def _make_schedule(occupation: str) -> Dict[str, str]:
    """Generate a daily schedule based on occupation."""
    if occupation in ("Saloon Keeper", "Gambler", "Dancehall Girl", "Actress"):
        return {"dawn": "sleep", "morning": "sleep", "afternoon": "saloon",
                "dusk": "saloon", "night": "saloon"}
    if occupation in ("Merchant", "Banker", "Barber", "Assayer"):
        return {"dawn": "home", "morning": "shop", "afternoon": "shop",
                "dusk": "saloon", "night": "home"}
    if occupation in ("Sheriff",):
        return {"dawn": "patrol", "morning": "office", "afternoon": "patrol",
                "dusk": "saloon", "night": "patrol"}
    if occupation in ("Preacher", "Teacher"):
        return {"dawn": "home", "morning": "church", "afternoon": "visit",
                "dusk": "home", "night": "home"}
    if occupation in ("Doctor", "Healer", "Midwife"):
        return {"dawn": "home", "morning": "office", "afternoon": "visit",
                "dusk": "office", "night": "home"}
    if occupation in ("Farmer", "Rancher"):
        return {"dawn": "field", "morning": "field", "afternoon": "field",
                "dusk": "home", "night": "home"}
    if occupation in ("Wife", "Laundress", "Seamstress",
                      "Boarding House Keeper", "Cook"):
        return {"dawn": "home", "morning": "work", "afternoon": "work",
                "dusk": "home", "night": "home"}
    # Default: miner/prospector/laborer
    return {"dawn": "camp", "morning": "work", "afternoon": "work",
            "dusk": "camp", "night": "sleep"}
