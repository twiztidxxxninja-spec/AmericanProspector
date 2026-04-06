"""
src/vehicles.py

Wagon and cart system for the Gold Rush.
Vehicles extend cargo capacity beyond pack animals and provide
different trade-offs between cost, speed, terrain handling, and
carrying capacity. Integrates with pack_animals.py — most vehicles
require a hitched animal to move.
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.items import Item


# ============================================================================
#  VEHICLE TYPE DATA
# ============================================================================

@dataclass
class VehicleType:
    type_id: str
    name: str
    carry_capacity: float       # lbs
    requires_animal: bool       # must hitch a pack animal to move
    required_species: List[str] # which animal species can pull it (empty = any)
    required_count: int         # how many animals needed (0 = none)
    base_speed: float           # movement multiplier (higher = slower)
    road_bonus: float           # speed mult on roads (lower = faster)
    offroad_penalty: float      # speed mult off-road (higher = slower)
    mountain_passable: bool     # can it go through mountains?
    base_price: float           # 1849 California dollars
    condition_rate_road: float  # condition loss per day on road
    condition_rate_offroad: float
    condition_rate_mountain: float
    glyph: str
    color: Tuple[int, int, int]
    description: str = ""
    water_vehicle: bool = False     # operates on water (rivers, lakes)
    portable: bool = False          # can be carried overland (portage)
    portage_weight: float = 0.0     # weight in lbs when carried
    downstream_speed: float = 1.0   # speed mult going downstream (lower = faster)
    upstream_speed: float = 1.0     # speed mult going upstream (higher = slower)
    one_way: bool = False           # flatboats can't go upstream
    year_available: int = 0         # 0 = always available


VEHICLE_TYPES: Dict[str, VehicleType] = {
    "handcart": VehicleType(
        type_id="handcart",
        name="Handcart",
        carry_capacity=200.0,
        requires_animal=False,
        required_species=[],
        required_count=0,
        base_speed=1.3,           # slow — player pushes it
        road_bonus=1.0,
        offroad_penalty=1.4,
        mountain_passable=True,
        base_price=15.0,
        condition_rate_road=1.0,
        condition_rate_offroad=3.0,
        condition_rate_mountain=5.0,
        glyph="c",
        color=(160, 140, 100),
        description="A simple two-wheeled cart pushed by hand. Slow but goes anywhere.",
    ),
    "mule_cart": VehicleType(
        type_id="mule_cart",
        name="Mule Cart",
        carry_capacity=500.0,
        requires_animal=True,
        required_species=["mule", "donkey"],
        required_count=1,
        base_speed=1.0,           # moderate
        road_bonus=0.85,
        offroad_penalty=1.3,
        mountain_passable=True,
        base_price=40.0,
        condition_rate_road=1.0,
        condition_rate_offroad=3.0,
        condition_rate_mountain=5.0,
        glyph="C",
        color=(180, 150, 90),
        description="A sturdy two-wheeled cart pulled by a mule or donkey.",
    ),
    "wagon": VehicleType(
        type_id="wagon",
        name="Wagon",
        carry_capacity=1500.0,
        requires_animal=True,
        required_species=["horse", "ox"],
        required_count=1,
        base_speed=0.9,
        road_bonus=0.7,
        offroad_penalty=1.5,
        mountain_passable=False,
        base_price=120.0,
        condition_rate_road=1.0,
        condition_rate_offroad=3.0,
        condition_rate_mountain=5.0,   # won't go there, but just in case
        glyph="W",
        color=(140, 100, 60),
        description="A four-wheeled covered wagon. Good on roads, can't cross mountains.",
    ),
    "freight_wagon": VehicleType(
        type_id="freight_wagon",
        name="Freight Wagon",
        carry_capacity=3000.0,
        requires_animal=True,
        required_species=["ox"],
        required_count=2,
        base_speed=1.1,
        road_bonus=0.7,
        offroad_penalty=2.5,          # very slow off-road
        mountain_passable=False,
        base_price=300.0,
        condition_rate_road=1.0,
        condition_rate_offroad=5.0,
        condition_rate_mountain=5.0,
        glyph="F",
        color=(120, 80, 40),
        description="A massive freight wagon needing two oxen. Road only for practical use.",
    ),

    # ── Water Vehicles ────────────────────────────────────────────────
    "birchbark_canoe": VehicleType(
        type_id="birchbark_canoe",
        name="Birchbark Canoe",
        carry_capacity=300.0,
        requires_animal=False,
        required_species=[],
        required_count=0,
        base_speed=0.8,
        road_bonus=1.0,
        offroad_penalty=1.0,
        mountain_passable=False,
        base_price=10.0,
        condition_rate_road=0.5,
        condition_rate_offroad=0.5,
        condition_rate_mountain=0.0,
        glyph="c",
        color=(160, 120, 60),
        description="Light bark canoe. Fast on rivers, portable for portage. "
                    "Fragile — rapids and rocks damage it.",
        water_vehicle=True,
        portable=True,
        portage_weight=60.0,
        downstream_speed=0.3,      # very fast downstream (current carries you)
        upstream_speed=1.8,         # hard work poling upstream
    ),
    "dugout_canoe": VehicleType(
        type_id="dugout_canoe",
        name="Dugout Canoe",
        carry_capacity=500.0,
        requires_animal=False,
        required_species=[],
        required_count=0,
        base_speed=0.9,
        road_bonus=1.0,
        offroad_penalty=1.0,
        mountain_passable=False,
        base_price=5.0,              # cheap — carve from a log
        condition_rate_road=0.3,      # very durable
        condition_rate_offroad=0.3,
        condition_rate_mountain=0.0,
        glyph="c",
        color=(100, 70, 40),
        description="A heavy canoe carved from a single log. Durable but hard to portage. "
                    "Can carry more than birchbark.",
        water_vehicle=True,
        portable=True,
        portage_weight=200.0,          # very heavy — need two men or a horse
        downstream_speed=0.4,
        upstream_speed=2.0,
    ),
    "pirogue": VehicleType(
        type_id="pirogue",
        name="Pirogue",
        carry_capacity=800.0,
        requires_animal=False,
        required_species=[],
        required_count=0,
        base_speed=1.0,
        road_bonus=1.0,
        offroad_penalty=1.0,
        mountain_passable=False,
        base_price=15.0,
        condition_rate_road=0.3,
        condition_rate_offroad=0.3,
        condition_rate_mountain=0.0,
        glyph="P",
        color=(120, 80, 40),
        description="A large dugout or planked boat. The fur trade workhorse. "
                    "Carries heavy loads on major rivers.",
        water_vehicle=True,
        portable=False,               # too heavy to portage
        portage_weight=400.0,
        downstream_speed=0.4,
        upstream_speed=2.2,
    ),
    "flatboat": VehicleType(
        type_id="flatboat",
        name="Flatboat",
        carry_capacity=5000.0,
        requires_animal=False,
        required_species=[],
        required_count=0,
        base_speed=0.6,               # drifts with current
        road_bonus=1.0,
        offroad_penalty=1.0,
        mountain_passable=False,
        base_price=30.0,
        condition_rate_road=1.0,
        condition_rate_offroad=1.0,
        condition_rate_mountain=0.0,
        glyph="F",
        color=(140, 100, 50),
        description="A flat-bottomed barge built for one-way downstream trips. "
                    "Carries enormous loads. Broken up for lumber at destination. "
                    "Cannot go upstream.",
        water_vehicle=True,
        portable=False,
        portage_weight=2000.0,         # can't portage a flatboat
        downstream_speed=0.3,          # fast downstream — current does the work
        upstream_speed=99.0,           # cannot go upstream
        one_way=True,
    ),
    "keelboat": VehicleType(
        type_id="keelboat",
        name="Keelboat",
        carry_capacity=2000.0,
        requires_animal=False,
        required_species=[],
        required_count=0,
        base_speed=1.0,
        road_bonus=1.0,
        offroad_penalty=1.0,
        mountain_passable=False,
        base_price=100.0,
        condition_rate_road=0.5,
        condition_rate_offroad=0.5,
        condition_rate_mountain=0.0,
        glyph="K",
        color=(130, 90, 50),
        description="A keeled river boat that can go upstream (poled or cordelled). "
                    "The commercial freight vessel of the river era. Needs a crew.",
        water_vehicle=True,
        portable=False,
        portage_weight=3000.0,
        downstream_speed=0.35,
        upstream_speed=1.5,            # slow but possible upstream
        year_available=1790,
    ),
}


# ============================================================================
#  VEHICLE
# ============================================================================

@dataclass
class Vehicle:
    """A single vehicle owned by the player."""
    vehicle_id: str
    type_id: str                        # key into VEHICLE_TYPES
    name: str
    condition: float = 100.0            # 0-100, breaks at 0
    inventory: List["Item"] = field(default_factory=list)
    hitched_animal_ids: List[str] = field(default_factory=list)

    @property
    def vtype(self) -> VehicleType:
        return VEHICLE_TYPES.get(self.type_id, VEHICLE_TYPES["handcart"])

    @property
    def carry_capacity(self) -> float:
        """Effective capacity based on condition."""
        base = self.vtype.carry_capacity
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
    def operational(self) -> bool:
        """Vehicle can move — not broken and has required animals hitched."""
        if self.condition <= 0:
            return False
        vt = self.vtype
        if vt.requires_animal and len(self.hitched_animal_ids) < vt.required_count:
            return False
        return True

    def speed_mult(self, terrain: str = "grass") -> float:
        """Movement speed multiplier on given terrain (higher = slower)."""
        vt = self.vtype
        base = vt.base_speed

        if terrain in ("road", "trail"):
            base *= vt.road_bonus
        elif terrain in ("mountain", "rock", "cliff"):
            if not vt.mountain_passable:
                return 99.0     # effectively impassable
            base *= vt.offroad_penalty
        elif terrain not in ("grass", "forest", "field", "clearing"):
            base *= vt.offroad_penalty

        # Load penalty
        load_pct = self.current_load / max(1, self.carry_capacity)
        if load_pct > 1.0:
            base *= 1.5 + (load_pct - 1.0)
        elif load_pct > 0.8:
            base *= 1.0 + (load_pct - 0.8) * 0.5

        # Condition penalty
        if self.condition < 20:
            base *= 2.0
        elif self.condition < 50:
            base *= 1.3

        return base

    # ── Serialization ────────────────────────────────────────────────

    def to_dict(self) -> dict:
        from src.save_load import _serialize_item
        return {
            "vehicle_id": self.vehicle_id,
            "type_id": self.type_id,
            "name": self.name,
            "condition": self.condition,
            "inventory": [_serialize_item(i) for i in self.inventory],
            "hitched_animal_ids": list(self.hitched_animal_ids),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Vehicle":
        from src.save_load import _deserialize_item
        v = cls(
            vehicle_id=d["vehicle_id"],
            type_id=d["type_id"],
            name=d["name"],
            condition=d.get("condition", 100.0),
        )
        v.inventory = [_deserialize_item(i) for i in d.get("inventory", [])]
        v.hitched_animal_ids = d.get("hitched_animal_ids", [])
        return v


# ============================================================================
#  VEHICLE MANAGER
# ============================================================================

# Default names for vehicles
_VEHICLE_NAMES: Dict[str, List[str]] = {
    "handcart":      ["Old Faithful", "The Mule", "Lucky Push", "Creaky",
                      "Dusty", "Ironside", "The Barrow"],
    "mule_cart":     ["Prairie Runner", "Rattlebox", "Pathfinder",
                      "The Wobbler", "Trailblazer", "Dustcloud"],
    "wagon":         ["Providence", "Westward Ho", "Bonanza", "The Pioneer",
                      "Gold Seeker", "Fortune's Wheel", "Promised Land"],
    "freight_wagon": ["Leviathan", "The Behemoth", "Iron Horse", "Big Bertha",
                      "Colossus", "Thunder Road", "The Hauler"],
}


class VehicleManager:
    """Manages all player-owned vehicles."""

    def __init__(self):
        self.vehicles: List[Vehicle] = []
        self._counter: int = 0

    def buy_vehicle(self, type_id: str, name: str = "") -> Vehicle:
        """Create and add a new vehicle. Returns the vehicle."""
        vt = VEHICLE_TYPES.get(type_id)
        if not vt:
            vt = VEHICLE_TYPES["handcart"]
            type_id = "handcart"
        if not name:
            name = random.choice(_VEHICLE_NAMES.get(type_id, ["Vehicle"]))
        self._counter += 1
        vehicle = Vehicle(
            vehicle_id=f"vehicle_{self._counter}",
            type_id=type_id,
            name=name,
        )
        self.vehicles.append(vehicle)
        return vehicle

    def get(self, vehicle_id: str) -> Optional[Vehicle]:
        for v in self.vehicles:
            if v.vehicle_id == vehicle_id:
                return v
        return None

    def remove(self, vehicle_id: str) -> Optional[Vehicle]:
        """Remove a vehicle (sold, destroyed). Returns it or None."""
        for i, v in enumerate(self.vehicles):
            if v.vehicle_id == vehicle_id:
                return self.vehicles.pop(i)
        return None

    def hitch(self, vehicle_id: str, animal_id: str,
              animal_species: str = "") -> Tuple[bool, str]:
        """Hitch a pack animal to a vehicle.
        Caller should pass animal_species so we can validate compatibility.
        """
        vehicle = self.get(vehicle_id)
        if not vehicle:
            return False, "No such vehicle."
        vt = vehicle.vtype

        if not vt.requires_animal:
            return False, f"The {vt.name} doesn't need an animal."

        if len(vehicle.hitched_animal_ids) >= vt.required_count:
            return False, f"The {vt.name} already has enough animals hitched."

        # Check that the animal isn't hitched elsewhere
        for v in self.vehicles:
            if animal_id in v.hitched_animal_ids:
                return False, "That animal is already hitched to another vehicle."

        # Species check
        if vt.required_species and animal_species not in vt.required_species:
            allowed = ", ".join(vt.required_species)
            return False, f"The {vt.name} requires: {allowed}."

        vehicle.hitched_animal_ids.append(animal_id)
        return True, f"Animal hitched to {vehicle.name}."

    def unhitch(self, vehicle_id: str,
                animal_id: str = "") -> Tuple[bool, str]:
        """Unhitch an animal from a vehicle.
        If animal_id is empty, unhitch all."""
        vehicle = self.get(vehicle_id)
        if not vehicle:
            return False, "No such vehicle."

        if not vehicle.hitched_animal_ids:
            return False, "No animals hitched."

        if animal_id:
            if animal_id not in vehicle.hitched_animal_ids:
                return False, "That animal isn't hitched to this vehicle."
            vehicle.hitched_animal_ids.remove(animal_id)
            return True, f"Animal unhitched from {vehicle.name}."
        else:
            vehicle.hitched_animal_ids.clear()
            return True, f"All animals unhitched from {vehicle.name}."

    def load_item(self, vehicle_id: str,
                  item: "Item") -> Tuple[bool, str]:
        """Load an item onto a vehicle. Checks weight capacity."""
        vehicle = self.get(vehicle_id)
        if not vehicle:
            return False, "No such vehicle."

        item_weight = getattr(item, 'weight', 0) * getattr(item, 'quantity', 1)
        if vehicle.current_load + item_weight > vehicle.carry_capacity:
            return False, (f"Too heavy. {vehicle.name} can carry "
                           f"{vehicle.carry_capacity - vehicle.current_load:.0f} more lbs.")

        vehicle.inventory.append(item)
        return True, f"Loaded {getattr(item, 'name', 'item')} onto {vehicle.name}."

    def unload_item(self, vehicle_id: str, idx: int) -> Optional[Any]:
        """Remove an item from a vehicle by index. Returns the item or None."""
        vehicle = self.get(vehicle_id)
        if not vehicle:
            return None
        if 0 <= idx < len(vehicle.inventory):
            return vehicle.inventory.pop(idx)
        return None

    def tick_daily(self, terrain: str = "grass") -> List[str]:
        """Daily wear on all vehicles. Returns messages about breakdowns."""
        msgs = []
        for v in self.vehicles:
            vt = v.vtype
            if terrain in ("road", "trail"):
                wear = vt.condition_rate_road
            elif terrain in ("mountain", "rock", "cliff"):
                wear = vt.condition_rate_mountain
            else:
                wear = vt.condition_rate_offroad

            # Overloaded vehicles degrade faster
            if v.overloaded:
                wear *= 2.0

            v.condition = max(0, v.condition - wear)

            if v.condition <= 0:
                msgs.append(f"{v.name} has broken down completely! "
                            f"It needs repair before it can move.")
            elif v.condition < 20:
                msgs.append(f"{v.name} is in very poor condition "
                            f"({v.condition:.0f}%). Needs repair soon.")
            elif v.condition < 40:
                msgs.append(f"{v.name} is wearing out ({v.condition:.0f}%).")

        return msgs

    def repair(self, vehicle_id: str, amount: float) -> Tuple[bool, str]:
        """Repair a vehicle's condition. Returns (success, message)."""
        vehicle = self.get(vehicle_id)
        if not vehicle:
            return False, "No such vehicle."
        old = vehicle.condition
        vehicle.condition = min(100.0, vehicle.condition + amount)
        restored = vehicle.condition - old
        return True, f"Repaired {vehicle.name} by {restored:.0f}% (now {vehicle.condition:.0f}%)."

    def total_carry_capacity(self) -> float:
        """Total carrying capacity across all operational vehicles."""
        return sum(v.carry_capacity for v in self.vehicles
                   if v.condition > 0)

    def total_load(self) -> float:
        """Total weight loaded across all vehicles."""
        return sum(v.current_load for v in self.vehicles)

    def slowest_speed(self, terrain: str = "grass") -> float:
        """Movement penalty from the heaviest/slowest vehicle.
        Returns the worst (highest) speed_mult among operational vehicles.
        If no vehicles, returns 1.0 (no penalty)."""
        operational = [v for v in self.vehicles if v.operational]
        if not operational:
            return 1.0
        return max(v.speed_mult(terrain) for v in operational)

    # ── Serialization ────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "counter": self._counter,
            "vehicles": [v.to_dict() for v in self.vehicles],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VehicleManager":
        mgr = cls()
        mgr._counter = d.get("counter", 0)
        for vd in d.get("vehicles", []):
            mgr.vehicles.append(Vehicle.from_dict(vd))
        return mgr
