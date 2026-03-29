"""
src/domesticated.py

Domesticated, tamable, feral, and trainable animals for American Prospector.
Includes livestock, pack animals, and animals that can become feral or be tamed.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class DomesticType(Enum):
    # Common Livestock & Working Animals
    HORSE = "horse"
    MULE = "mule"
    DONKEY = "donkey"
    OX = "ox"
    COW = "cow"                    # beef or dairy
    STEER = "steer"
    PIG = "pig"
    SHEEP = "sheep"
    GOAT = "goat"
    CHICKEN = "chicken"
    DOG = "dog"                    # herding, guard, hunting

    # Less common but possible
    LLAMA = "llama"                # rare, post-1850s
    CAMEL = "camel"                # experimental in Southwest deserts


@dataclass
class DomesticSpecies:
    id: str
    display_name: str
    category: str                  # "pack", "livestock", "poultry", "working", "pet"
    danger_level: int              # 0 = harmless, 1 = can kick/bite, 2 = dangerous when provoked
    size: str                      # small, medium, large, very_large
    primary_use: List[str]         # "riding", "packing", "meat", "milk", "wool", "guard", "hunting"
    base_value: float              # approximate purchase price in 1849–1850s dollars
    meat_yield_lb: float
    carrying_capacity_lb: Optional[float] = None   # for pack animals
    temperament: str = "docile"    # docile, skittish, stubborn, aggressive
    can_be_tamed: bool = True
    can_go_feral: bool = True
    notes: str = ""


DOMESTIC_DB = {
    DomesticType.HORSE: DomesticSpecies(
        id="horse",
        display_name="Horse",
        category="pack",
        danger_level=1,
        size="large",
        primary_use=["riding", "packing"],
        base_value=65.0,
        meat_yield_lb=400.0,
        carrying_capacity_lb=150.0,
        temperament="skittish",
        can_be_tamed=True,
        can_go_feral=True,
        notes="Essential for fast travel and packing. Expensive to maintain."
    ),
    DomesticType.MULE: DomesticSpecies(
        id="mule",
        display_name="Mule",
        category="pack",
        danger_level=1,
        size="large",
        primary_use=["packing", "riding"],
        base_value=45.0,
        meat_yield_lb=350.0,
        carrying_capacity_lb=250.0,
        temperament="stubborn",
        can_be_tamed=True,
        can_go_feral=True,
        notes="Superior pack animal for mountains. Tougher and more sure-footed than horses."
    ),
    DomesticType.DONKEY: DomesticSpecies(
        id="donkey",
        display_name="Donkey",
        category="pack",
        danger_level=1,
        size="medium",
        primary_use=["packing"],
        base_value=25.0,
        meat_yield_lb=180.0,
        carrying_capacity_lb=100.0,
        temperament="stubborn",
        can_be_tamed=True,
        can_go_feral=True,
        notes="Cheap and hardy pack animal."
    ),
    DomesticType.COW: DomesticSpecies(
        id="cow",
        display_name="Cow",
        category="livestock",
        danger_level=1,
        size="large",
        primary_use=["meat", "milk"],
        base_value=18.0,
        meat_yield_lb=450.0,
        carrying_capacity_lb=None,
        temperament="docile",
        can_be_tamed=True,
        can_go_feral=True,
        notes="Source of milk and beef. Can be driven in small herds."
    ),
    DomesticType.PIG: DomesticSpecies(
        id="pig",
        display_name="Pig",
        category="livestock",
        danger_level=1,
        size="medium",
        primary_use=["meat"],
        base_value=8.0,
        meat_yield_lb=120.0,
        carrying_capacity_lb=None,
        temperament="docile",
        can_be_tamed=True,
        can_go_feral=True,
        notes="Excellent for clearing land and producing meat. Can go feral quickly."
    ),
    DomesticType.DOG: DomesticSpecies(
        id="dog",
        display_name="Dog",
        category="working",
        danger_level=1,
        size="medium",
        primary_use=["guard", "hunting", "herding"],
        base_value=12.0,
        meat_yield_lb=25.0,
        carrying_capacity_lb=None,
        temperament="loyal",
        can_be_tamed=True,
        can_go_feral=True,
        notes="Extremely useful for guarding camp and hunting. Breeds matter."
    ),
    DomesticType.CHICKEN: DomesticSpecies(
        id="chicken",
        display_name="Chicken",
        category="poultry",
        danger_level=0,
        size="small",
        primary_use=["meat", "eggs"],
        base_value=0.5,
        meat_yield_lb=4.0,
        carrying_capacity_lb=None,
        temperament="docile",
        can_be_tamed=True,
        can_go_feral=True,
        notes="Easy source of eggs and meat. Can be kept in coops."
    ),
    # Add more as needed (sheep, goat, ox, etc.)
}


def get_starting_livestock() -> List[dict]:
    """Return reasonable starting animals for a new prospector."""
    return [
        {"type": DomesticType.MULE, "name": "Bessie", "condition": 85},
        {"type": DomesticType.DOG, "name": "Ranger", "condition": 90},
    ]
