"""
Player character: position, attributes, skills, knowledge, stance, survival stats.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from src.survival import SurvivalStats
from src.health_system import HealthTracker, MAX_BLOOD


# Stance
class Stance:
    STANDING = "Standing"
    CROUCHED = "Crouched"
    PRONE_DOWN = "Prone (face down)"
    PRONE_UP   = "Prone (face up)"

STANCE_LIST = [Stance.STANDING, Stance.CROUCHED, Stance.PRONE_DOWN, Stance.PRONE_UP]

# Speed
class Speed:
    WALK  = "Walk"
    JOG   = "Jog"
    RUN   = "Run"
    CRAWL = "Crawl"

SPEED_LIST = [Speed.WALK, Speed.JOG, Speed.RUN, Speed.CRAWL]

# Time cost multipliers per speed (relative to walk baseline)
SPEED_TIME_MULT = {
    Speed.WALK:  1.0,
    Speed.JOG:   0.6,
    Speed.RUN:   0.3,
    Speed.CRAWL: 3.0,
}

# Fatigue drain multipliers per speed
SPEED_FATIGUE_MULT = {
    Speed.WALK:  1.0,
    Speed.JOG:   1.8,
    Speed.RUN:   3.5,
    Speed.CRAWL: 1.2,
}

# Default starting attributes
DEFAULT_ATTRIBUTES = {
    "strength":     10,
    "agility":      10,
    "intelligence": 10,
    "wisdom":       10,
    "charisma":     10,
    "constitution": 10,
}

# Default skills (all start at 0)
ALL_SKILLS = [
    "geology", "placer", "hardRock", "assaying", "oilSensing",
    "coalMining", "survival", "tracking", "firstAid", "trading",
    "law", "engineering", "chemistry", "firearms", "driving",
    "farming", "literacy", "trapping", "furriery",
]


@dataclass
class Player:
    name: str = "Unnamed"
    age:  int = 24

    # World map position (Sacramento — overridden by character creation)
    world_x: int = 95
    world_y: int = 165

    # Area patch within world tile (0–13, center = 7)
    area_x: int = 7
    area_y: int = 7

    # Local map position within patch (start at center of patch)
    local_x: int = 192
    local_y: int = 192
    local_z: int = 0       # current z-level (set to surface_z after map gen)

    # On which map are we?
    on_world_map: bool = False

    # Attributes
    attributes: Dict[str, int] = field(default_factory=lambda: dict(DEFAULT_ATTRIBUTES))

    # Skills: 0–10
    skills: Dict[str, int] = field(default_factory=lambda: {s: 0 for s in ALL_SKILLS})
    skill_xp: Dict[str, float] = field(default_factory=lambda: {s: 0.0 for s in ALL_SKILLS})

    # Knowledge: 0=None, 1=Partial, 2=Working, 3=Expert, 4=Mastery
    knowledge: Dict[str, int] = field(default_factory=dict)

    # Survival
    survival: SurvivalStats = field(default_factory=SurvivalStats)

    # Wound system
    wounds: HealthTracker = field(
        default_factory=lambda: HealthTracker(MAX_BLOOD["human"]))

    # Stance & movement
    stance: str = Stance.STANDING
    speed:  str = Speed.WALK

    # Tactical status (updated by engine)
    in_cover:  str = "none"      # 'none', 'partial', 'full'
    hidden:    str = "no"        # 'no', 'possible', 'yes'

    # Inventory
    inventory: list = field(default_factory=list)
    left_hand:  Optional[str] = None
    right_hand: Optional[str] = None
    carried_weight: float = 0.0

    # Worn clothing/equipment (separate from inventory)
    worn: Any = None  # WornEquipment — initialized in __post_init__

    # Type annotation is Any to avoid circular import; actual type is WornEquipment

    # Gold carried (troy oz)
    gold_oz: float = 0.0
    cash:    float = 150.0  # starting cash — a Forty-Niner's savings

    # Pack animals: each entry is a dict with keys:
    #   type_id (str), name (str), condition (0-100), carrying_capacity_lb (float)
    pack_animals: list = field(default_factory=list)

    # Panning state — pan can be filled away from water then washed later
    pan_loaded: bool = False   # True = pan holds raw material, needs water to wash
    pan_source_x: int = -1     # source tile coords (where material came from)
    pan_source_y: int = -1

    def __post_init__(self):
        if self.worn is None:
            try:
                from src.clothing import starting_outfit
                self.worn = starting_outfit()
            except ImportError:
                self.worn = None

        # Constitution affects max health and blood volume
        con = self.attributes.get("constitution", 10)
        # Health: 80 at CON 6, 100 at CON 10, 130 at CON 16
        self.survival.health = 80.0 + (con - 6) * 5.0
        # Blood volume scales similarly
        self.wounds.max_blood = 80.0 + (con - 6) * 5.0
        self.wounds.blood = self.wounds.max_blood

    def move(self, dx: int, dy: int) -> int:
        """
        Move on the local map. Returns SECONDS consumed.
        Encumbrance slows movement. Wounds slow movement.
        """
        from src.constants import WALK_TIME
        self.local_x += dx
        self.local_y += dy
        base = WALK_TIME  # seconds per tile
        time_cost = max(1, int(base * SPEED_TIME_MULT[self.speed]))
        # Encumbrance penalty
        if self.overloaded:
            time_cost = int(time_cost * 2.5)
        elif self.encumbered:
            time_cost = int(time_cost * 1.5)
        # Weather penalty (set by engine each tick)
        weather_mult = getattr(self, '_weather_move_penalty', 1.0)
        if weather_mult > 1.0:
            time_cost = int(time_cost * weather_mult)
        # Wound/pain penalty
        if hasattr(self, 'wounds') and self.wounds:
            pain = self.wounds.total_pain
            if pain > 50:
                time_cost = int(time_cost * 2.0)  # severe pain = half speed
            elif pain > 25:
                time_cost = int(time_cost * 1.5)  # moderate pain
            elif pain > 10:
                time_cost = int(time_cost * 1.2)  # mild pain
            # Leg wounds specifically
            from src.health_system import BP
            leg_parts = (BP.L_THIGH, BP.R_THIGH, BP.L_LOWER_LEG,
                         BP.R_LOWER_LEG, BP.GROIN)
            for part in leg_parts:
                state = self.wounds.part_state.get(part, "intact")
                if state == "disabled":
                    time_cost = int(time_cost * 3.0)
                    break
                elif state == "impaired":
                    time_cost = int(time_cost * 1.5)
        return time_cost

    def move_world(self, dx: int, dy: int, world_map) -> int:
        """Move on the world map. Returns minutes consumed."""
        nx, ny = self.world_x + dx, self.world_y + dy
        if not world_map.in_bounds(nx, ny):
            return 0
        cost = world_map.travel_cost(nx, ny)
        self.world_x = nx
        self.world_y = ny
        world_map.mark_visited(nx, ny)
        return int(cost)

    def cycle_stance(self):
        idx = STANCE_LIST.index(self.stance)
        self.stance = STANCE_LIST[(idx + 1) % len(STANCE_LIST)]

    def cycle_speed(self):
        # Filter crawl to prone only
        available = SPEED_LIST if self.stance in (Stance.PRONE_DOWN, Stance.PRONE_UP) \
                    else [s for s in SPEED_LIST if s != Speed.CRAWL]
        idx = available.index(self.speed) if self.speed in available else 0
        self.speed = available[(idx + 1) % len(available)]

    def gain_skill_xp(self, skill: str, xp: float) -> str:
        """Add XP to a skill. Returns level-up message or empty string.
        Also queues the message in _pending_levelups for engine to flush."""
        if skill not in self.skills:
            return ""
        # INT multiplier: faster learning
        int_mult = 1.0 + (self.attributes.get("intelligence", 10) - 10) * 0.05
        effective_xp = xp * int_mult
        self.skill_xp[skill] = self.skill_xp.get(skill, 0.0) + effective_xp
        threshold = 100 + 10 * self.skills[skill]
        if self.skill_xp[skill] >= threshold and self.skills[skill] < 10:
            old = self.skills[skill]
            self.skills[skill] += 1
            self.skill_xp[skill] = 0.0
            msg = f"SKILL UP: {skill} improved ({old} -> {self.skills[skill]})"
            if not hasattr(self, '_pending_levelups'):
                self._pending_levelups = []
            self._pending_levelups.append(msg)
            return msg
        return ""

    def flush_levelups(self) -> list:
        """Return and clear any pending skill level-up messages."""
        msgs = getattr(self, '_pending_levelups', [])
        self._pending_levelups = []
        return msgs

    def recalc_weight(self):
        """Recalculate carried_weight from inventory + hands."""
        total = 0.0
        for item in self.inventory:
            w = getattr(item, 'weight', 0.0)
            qty = getattr(item, 'quantity', 1)
            total += w * qty
        self.carried_weight = total

    @property
    def carry_capacity(self) -> float:
        """Max carry weight in pounds.
        Base: pockets + hands (~15lb).
        Gear: backpack, satchel, saddlebags add capacity.
        Strength: +2lb per point above 8.
        Pack animals: their capacity added on top."""
        # Pockets and hands — what you can carry with no bag
        base = 15.0 + max(0, self.attributes["strength"] - 8) * 2.0

        # Storage containers in inventory add capacity
        for item in self.inventory:
            extra = getattr(item, 'extra', {}) or {}
            carry_bonus = extra.get("carry_capacity_lb", 0)
            if carry_bonus:
                base += carry_bonus

        # Worn equipment with storage (e.g. belt pouches, vest pockets)
        if self.worn:
            for slot_name, worn_item in vars(self.worn).items():
                if worn_item and hasattr(worn_item, 'garment_def'):
                    gd = worn_item.garment_def
                    if gd and "storage" in (gd.tags or []):
                        # Storage garments add ~5-10lb capacity
                        base += gd.warmth * 0.5 + 5.0

        # Pack animals
        if hasattr(self, '_animal_mgr') and self._animal_mgr:
            base += self._animal_mgr.total_carry_capacity
        else:
            for pa in self.pack_animals:
                cond  = pa.get("condition", 100) / 100.0
                cap   = pa.get("carrying_capacity_lb", 0.0)
                if cond > 0.2:
                    base += cap * cond
        return base

    @property
    def encumbered(self) -> bool:
        return self.carried_weight > self.carry_capacity * 0.75

    @property
    def overloaded(self) -> bool:
        return self.carried_weight > self.carry_capacity
