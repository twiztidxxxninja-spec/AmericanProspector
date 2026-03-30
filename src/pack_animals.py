"""
src/pack_animals.py

Pack animal system — horses, mules, donkeys, oxen.
Animals carry inventory, need feeding, affect travel speed,
and can be bought/sold at livery stables.
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.items import Item


# ============================================================================
#  SPECIES DATA
# ============================================================================

@dataclass
class AnimalSpecies:
    type_id: str
    name: str
    carry_capacity: float       # lbs
    base_speed: float           # multiplier (1.0 = human walk)
    forage_efficiency: float    # 0-1, how well it feeds from grass
    grain_per_day: float        # lbs of grain needed if no forage
    base_price: float           # 1849 California dollars
    mountain_bonus: float       # speed multiplier in mountains (lower = better)
    road_bonus: float           # speed multiplier on roads
    temperament: str            # "docile", "stubborn", "skittish"
    rideable: bool              # can player ride it?
    spook_chance: float         # chance to panic from gunfire/bears (0-1)
    glyph: str                  # ASCII character
    color: Tuple[int, int, int]


SPECIES: Dict[str, AnimalSpecies] = {
    "mule": AnimalSpecies(
        type_id="mule", name="Mule",
        carry_capacity=250.0, base_speed=0.8,
        forage_efficiency=0.8, grain_per_day=0.0,
        base_price=45.0,
        mountain_bonus=0.7, road_bonus=0.9,
        temperament="stubborn", rideable=True, spook_chance=0.05,
        glyph="m", color=(160, 130, 80),
    ),
    "horse": AnimalSpecies(
        type_id="horse", name="Horse",
        carry_capacity=150.0, base_speed=0.5,
        forage_efficiency=0.5, grain_per_day=5.0,
        base_price=65.0,
        mountain_bonus=1.0, road_bonus=0.4,
        temperament="skittish", rideable=True, spook_chance=0.25,
        glyph="h", color=(180, 140, 100),
    ),
    "donkey": AnimalSpecies(
        type_id="donkey", name="Donkey",
        carry_capacity=100.0, base_speed=0.9,
        forage_efficiency=0.9, grain_per_day=0.0,
        base_price=25.0,
        mountain_bonus=0.75, road_bonus=1.0,
        temperament="stubborn", rideable=False, spook_chance=0.05,
        glyph="d", color=(140, 120, 90),
    ),
    "ox": AnimalSpecies(
        type_id="ox", name="Ox",
        carry_capacity=350.0, base_speed=1.4,
        forage_efficiency=1.0, grain_per_day=0.0,
        base_price=50.0,
        mountain_bonus=1.2, road_bonus=1.1,
        temperament="docile", rideable=False, spook_chance=0.02,
        glyph="O", color=(160, 140, 110),
    ),
}

# Random names by species
_NAMES = {
    "mule":   ["Bessie", "Sal", "Jenny", "Dusty", "Pete", "Stubbs",
               "Molly", "Buck", "Daisy", "Grit"],
    "horse":  ["Thunder", "Blaze", "Shadow", "Star", "Duke", "Lady",
               "Copper", "Scout", "Whiskey", "Sage"],
    "donkey": ["Jack", "Pedro", "Sancho", "Burrito", "Rocky", "Pebbles",
               "Rusty", "Bean", "Patches", "Dusty"],
    "ox":     ["Blue", "Red", "Big Jim", "Brindle", "Hercules", "Tank",
               "Lumber", "Boulder", "Iron", "Mud"],
}


# ============================================================================
#  PACK ANIMAL
# ============================================================================

@dataclass
class PackAnimal:
    """A single pack animal owned by the player."""
    animal_id: str
    type_id: str                    # key into SPECIES
    name: str
    health: float = 100.0           # 0-100, dies at 0
    hunger: float = 100.0           # 0-100, starves at 0
    fatigue: float = 100.0          # 0-100, collapses at 0
    condition: float = 100.0        # overall, degrades from overload/injury
    inventory: List["Item"] = field(default_factory=list)
    # Map position (follows player)
    local_x: int = 0
    local_y: int = 0
    local_z: int = 0

    @property
    def species(self) -> AnimalSpecies:
        return SPECIES.get(self.type_id, SPECIES["mule"])

    @property
    def carry_capacity(self) -> float:
        """Effective capacity based on condition."""
        base = self.species.carry_capacity
        cond_mult = max(0, self.condition / 100.0)
        return base * cond_mult

    @property
    def current_load(self) -> float:
        return sum(getattr(i, 'weight', 0) * getattr(i, 'quantity', 1)
                   for i in self.inventory)

    @property
    def overloaded(self) -> bool:
        return self.current_load > self.carry_capacity

    @property
    def alive(self) -> bool:
        return self.health > 0

    @property
    def can_travel(self) -> bool:
        return self.alive and self.fatigue > 5 and self.health > 10

    def speed_modifier(self, terrain: str = "grass") -> float:
        """Movement speed multiplier for this animal on given terrain."""
        sp = self.species
        base = sp.base_speed

        # Terrain bonuses
        if terrain in ("road", "trail"):
            base *= sp.road_bonus
        elif terrain in ("mountain", "rock", "cliff"):
            base *= sp.mountain_bonus

        # Load penalty
        load_pct = self.current_load / max(1, self.carry_capacity)
        if load_pct > 1.0:
            base *= 1.5 + (load_pct - 1.0)  # dramatically slower when overloaded
        elif load_pct > 0.8:
            base *= 1.0 + (load_pct - 0.8) * 0.5

        # Fatigue penalty
        if self.fatigue < 30:
            base *= 1.3
        if self.fatigue < 10:
            base *= 2.0

        return base

    def tick_hourly(self, is_traveling: bool, terrain: str = "grass"):
        """Called every game hour. Animals graze automatically and
        need minimal maintenance. Only overloading causes problems."""
        if not self.alive:
            return

        # Animals graze automatically — hunger stays topped up
        # Only drains if in a desert/barren area with no forage
        if terrain not in ("desert", "rock", "bedrock", "snow"):
            self.hunger = min(100, self.hunger + 1.0)
        else:
            self.hunger = max(0, self.hunger - 0.3)

        # Fatigue
        if is_traveling:
            fatigue_rate = 0.8
            if self.overloaded:
                fatigue_rate *= 2.5
            self.fatigue = max(0, self.fatigue - fatigue_rate)
        else:
            self.fatigue = min(100, self.fatigue + 5.0)

        # Overload condition damage (only real maintenance issue)
        if self.overloaded:
            self.condition = max(0, self.condition - 0.3)

        # Only take health damage from extreme overload or zero fatigue
        if self.fatigue <= 0:
            self.health -= 0.5
        if self.hunger <= 0:
            self.health -= 1.0

        self.health = max(0, self.health)

    def tick_daily(self, on_grassland: bool, has_grain: bool,
                   rng: random.Random) -> List[str]:
        """Daily tick. Animals are low-maintenance — they graze on their own.
        Returns list of messages."""
        msgs = []
        if not self.alive:
            return msgs

        # Auto-forage — animals find their own food
        self.hunger = min(100, self.hunger + 20)

        # Condition recovery (natural healing)
        if not self.overloaded and self.fatigue > 40:
            self.condition = min(100, self.condition + 2.0)
            self.health = min(100, self.health + 1.0)

        # Death check
        if self.health <= 0:
            msgs.append(f"{self.name} the {self.species.name} has died.")

        return msgs

    def feed(self, food_item: "Item") -> str:
        """Feed an item to the animal. Returns message."""
        restore = 0
        name = food_item.name.lower()
        if any(w in name for w in ("hay", "oats", "grain", "barley", "corn")):
            restore = 40
        elif any(w in name for w in ("grass", "forage")):
            restore = 25
        elif any(w in name for w in ("apple", "carrot", "vegetable")):
            restore = 15
        elif food_item.nutrition > 0:
            restore = food_item.nutrition * 0.3  # animals can eat human food poorly
        else:
            return f"{self.name} won't eat that."

        self.hunger = min(100, self.hunger + restore)
        return f"{self.name} eats the {food_item.name}. ({restore:.0f}% hunger restored)"

    def spook_check(self, rng: random.Random) -> bool:
        """Check if animal spooks from loud noise. Returns True if spooked."""
        return rng.random() < self.species.spook_chance

    # ── Serialization ────────────────────────────────────────────────

    def move_toward(self, target_x: int, target_y: int, local_map,
                    rng: random.Random):
        """Move one step toward target position. Called each player move."""
        if not self.alive or not self.can_travel:
            return
        dx = target_x - self.local_x
        dy = target_y - self.local_y
        dist = max(abs(dx), abs(dy))
        # Only move if more than 3 tiles away, stay within ~8 tiles
        if dist <= 3:
            return
        # Normalize to single step
        sx = (1 if dx > 0 else -1 if dx < 0 else 0)
        sy = (1 if dy > 0 else -1 if dy < 0 else 0)
        # Add slight wander
        if rng.random() < 0.2:
            sx += rng.choice([-1, 0, 1])
            sy += rng.choice([-1, 0, 1])
        nx, ny = self.local_x + sx, self.local_y + sy
        if local_map and local_map.in_bounds(nx, ny) and local_map.is_passable(nx, ny):
            self.local_x = nx
            self.local_y = ny

    def place_near(self, x: int, y: int, local_map, rng: random.Random):
        """Place animal near a position (on spawn or map entry)."""
        for _ in range(20):
            ox = x + rng.randint(-5, 5)
            oy = y + rng.randint(-5, 5)
            if local_map and local_map.in_bounds(ox, oy) and local_map.is_passable(ox, oy):
                self.local_x = ox
                self.local_y = oy
                return
        # Fallback — just put them at player position
        self.local_x = x
        self.local_y = y

    def to_dict(self) -> dict:
        from src.save_load import _serialize_item
        return {
            "animal_id": self.animal_id,
            "type_id": self.type_id,
            "name": self.name,
            "health": self.health,
            "hunger": self.hunger,
            "fatigue": self.fatigue,
            "condition": self.condition,
            "local_x": self.local_x,
            "local_y": self.local_y,
            "local_z": self.local_z,
            "inventory": [_serialize_item(i) for i in self.inventory],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PackAnimal":
        from src.save_load import _deserialize_item
        animal = cls(
            animal_id=d["animal_id"],
            type_id=d["type_id"],
            name=d["name"],
            health=d.get("health", 100),
            hunger=d.get("hunger", 100),
            fatigue=d.get("fatigue", 100),
            condition=d.get("condition", 100),
        )
        animal.local_x = d.get("local_x", 0)
        animal.local_y = d.get("local_y", 0)
        animal.local_z = d.get("local_z", 0)
        animal.inventory = [_deserialize_item(i) for i in d.get("inventory", [])]
        return animal


# ============================================================================
#  PACK ANIMAL MANAGER
# ============================================================================

class PackAnimalManager:
    """Manages all player-owned pack animals."""

    def __init__(self):
        self.animals: List[PackAnimal] = []
        self._next_id = 1

    def buy(self, type_id: str, name: str = "") -> PackAnimal:
        """Create and add a new animal. Returns the animal."""
        sp = SPECIES.get(type_id)
        if not sp:
            sp = SPECIES["mule"]
            type_id = "mule"
        if not name:
            name = random.choice(_NAMES.get(type_id, ["Animal"]))
        animal = PackAnimal(
            animal_id=f"animal_{self._next_id}",
            type_id=type_id,
            name=name,
        )
        self._next_id += 1
        self.animals.append(animal)
        return animal

    def remove(self, animal_id: str) -> Optional[PackAnimal]:
        """Remove an animal (sell, die, stolen). Returns the animal or None."""
        for i, a in enumerate(self.animals):
            if a.animal_id == animal_id:
                return self.animals.pop(i)
        return None

    def get(self, animal_id: str) -> Optional[PackAnimal]:
        for a in self.animals:
            if a.animal_id == animal_id:
                return a
        return None

    @property
    def total_carry_capacity(self) -> float:
        return sum(a.carry_capacity for a in self.animals if a.alive)

    @property
    def total_load(self) -> float:
        return sum(a.current_load for a in self.animals if a.alive)

    @property
    def slowest_speed(self) -> float:
        """Return speed of slowest animal (determines caravan pace)."""
        if not self.animals:
            return 1.0
        speeds = [a.speed_modifier() for a in self.animals if a.can_travel]
        return max(speeds) if speeds else 1.0  # higher = slower

    def has_rideable(self) -> bool:
        """Player has at least one rideable animal in good shape."""
        return any(a.species.rideable and a.can_travel
                   for a in self.animals)

    def move_animals(self, player_x: int, player_y: int, local_map,
                     rng: random.Random = None):
        """Move all animals one step toward the player. Called on player move."""
        if rng is None:
            rng = random.Random()
        for a in self.animals:
            a.move_toward(player_x, player_y, local_map, rng)

    def place_all_near(self, x: int, y: int, local_map,
                       rng: random.Random = None):
        """Place all animals near a position (on map entry)."""
        if rng is None:
            rng = random.Random()
        for a in self.animals:
            a.place_near(x, y, local_map, rng)

    def tick_hourly(self, is_traveling: bool, terrain: str = "grass"):
        for a in self.animals:
            a.tick_hourly(is_traveling, terrain)

    def tick_daily(self, on_grassland: bool, player_inventory: list,
                   rng: random.Random) -> List[str]:
        """Daily care tick. Returns messages."""
        msgs = []
        # Check if player has grain
        has_grain = any(i.id in ("oats", "grain", "hay", "barley")
                        for i in player_inventory)

        for a in list(self.animals):
            for msg in a.tick_daily(on_grassland, has_grain, rng):
                msgs.append(msg)

            # Drop inventory of dead animals
            if not a.alive:
                msgs.append(f"{a.name}'s load falls to the ground.")
                # Inventory should be moved to ground in engine

        # Remove dead animals
        self.animals = [a for a in self.animals if a.alive]
        return msgs

    # ── Serialization ────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "next_id": self._next_id,
            "animals": [a.to_dict() for a in self.animals],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PackAnimalManager":
        mgr = cls()
        mgr._next_id = d.get("next_id", 1)
        for ad in d.get("animals", []):
            mgr.animals.append(PackAnimal.from_dict(ad))
        return mgr


# ============================================================================
#  LIVERY STABLE UI
# ============================================================================

def open_livery_ui(console, ctx, player, animal_mgr: PackAnimalManager,
                   region: str = "", settlement_type: str = "small_town"
                   ) -> List[str]:
    """Buy/sell animals at a livery stable. Returns log messages."""
    import tcod.event
    from src.menus import draw_box, pick_from_list

    WHITE  = (255, 255, 255)
    YELLOW = (255, 255, 0)
    CYAN   = (0, 200, 200)
    GREY   = (140, 140, 140)
    GREEN  = (0, 200, 0)
    RED    = (255, 80, 80)
    BG     = (15, 12, 10)

    messages = []

    # Price multiplier by settlement type
    price_mult = {"mining_camp_small": 2.5, "mining_camp_medium": 2.0,
                  "boomtown": 1.8, "small_town": 1.3,
                  "trading_post": 1.0, "city": 1.2}.get(settlement_type, 1.5)

    options = ["Buy an animal", "Sell an animal", "View your animals", "Leave"]
    while True:
        idx = pick_from_list(console, ctx, "LIVERY STABLE", options)
        if idx is None or idx == 3:
            break

        if idx == 0:  # Buy
            buy_options = []
            buy_data = []
            for type_id, sp in SPECIES.items():
                price = sp.base_price * price_mult
                buy_options.append(f"{sp.name:8s}  ${price:.0f}  "
                                   f"(carries {sp.carry_capacity:.0f} lbs)")
                buy_data.append((type_id, price))

            bidx = pick_from_list(console, ctx,
                                  f"Buy — Your cash: ${player.cash:.2f}", buy_options)
            if bidx is not None:
                type_id, price = buy_data[bidx]
                if player.cash < price:
                    messages.append(f"Can't afford ${price:.0f}.")
                else:
                    player.cash -= price
                    animal = animal_mgr.buy(type_id)
                    messages.append(
                        f"Bought {animal.name} the {animal.species.name} "
                        f"for ${price:.0f}.")

        elif idx == 1:  # Sell
            if not animal_mgr.animals:
                messages.append("You have no animals to sell.")
                continue
            sell_options = []
            for a in animal_mgr.animals:
                sell_price = a.species.base_price * price_mult * 0.5 * (a.condition / 100)
                sell_options.append(
                    f"{a.name} ({a.species.name}) — ${sell_price:.0f}")
            sidx = pick_from_list(console, ctx, "Sell which animal?", sell_options)
            if sidx is not None:
                animal = animal_mgr.animals[sidx]
                sell_price = animal.species.base_price * price_mult * 0.5 * (animal.condition / 100)
                # Move animal inventory to player
                for item in animal.inventory:
                    player.inventory.append(item)
                animal.inventory.clear()
                animal_mgr.remove(animal.animal_id)
                player.cash += sell_price
                messages.append(
                    f"Sold {animal.name} for ${sell_price:.0f}.")

        elif idx == 2:  # View
            if not animal_mgr.animals:
                messages.append("You have no animals.")
                continue
            view_options = []
            for a in animal_mgr.animals:
                status = "OK" if a.can_travel else "EXHAUSTED" if a.fatigue < 10 else "INJURED"
                view_options.append(
                    f"{a.name} ({a.species.name}) HP:{a.health:.0f} "
                    f"HGR:{a.hunger:.0f} FTG:{a.fatigue:.0f} "
                    f"Load:{a.current_load:.0f}/{a.carry_capacity:.0f}lb [{status}]")
            pick_from_list(console, ctx, "Your Animals", view_options)

    return messages
