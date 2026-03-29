"""
src/wildlife.py

North American Wildlife for American Prospector (1849–2000)
Animals are regionally restricted and behave realistically.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List


class WildlifeType(Enum):
    # === LARGE / DANGEROUS ===
    GRIZZLY_BEAR = "grizzly_bear"
    BLACK_BEAR = "black_bear"
    MOUNTAIN_LION = "mountain_lion"
    GRAY_WOLF = "gray_wolf"
    BUFFALO = "buffalo"                    # American Bison

    # === MEDIUM GAME ===
    ELK = "elk"
    MULE_DEER = "mule_deer"
    BLACK_TAILED_DEER = "black_tailed_deer"
    PRONGHORN = "pronghorn"
    BIGHORN_SHEEP = "bighorn_sheep"
    MOOSE = "moose"

    # === SMALL / COMMON ===
    COYOTE = "coyote"
    GRAY_FOX = "gray_fox"
    RED_FOX = "red_fox"
    BEAVER = "beaver"
    RACCOON = "raccoon"
    BOBCAT = "bobcat"
    JACKRABBIT = "jackrabbit"
    GROUND_SQUIRREL = "ground_squirrel"

    # === FUR-BEARERS (trapping targets) ===
    RIVER_OTTER = "river_otter"
    MINK = "mink"
    PINE_MARTEN = "pine_marten"
    FISHER = "fisher"
    WOLVERINE = "wolverine"
    BADGER = "badger"
    SKUNK = "skunk"
    MUSKRAT = "muskrat"
    OPOSSUM = "opossum"
    LYNX = "lynx"

    # === REPTILES & BIRDS ===
    RATTLESNAKE = "rattlesnake"
    BALD_EAGLE = "bald_eagle"
    CALIFORNIA_CONDOR = "california_condor"   # very rare
    WILD_TURKEY = "wild_turkey"


@dataclass
class WildlifeSpecies:
    id: str
    display_name: str
    danger_level: int          # 0 = harmless, 1 = minor threat, 2 = serious danger
    size: str                  # small, medium, large, very_large
    primary_habitats: List[str]
    core_regions: List[str]    # Will almost never spawn outside these
    base_spawn_chance: float   # Base probability, modified by terrain/season
    meat_yield_lb: float
    hide_value: float          # approximate 1849–1850s trade value in dollars
    notes: str = ""


WILDLIFE_DB = {
    WildlifeType.GRIZZLY_BEAR: WildlifeSpecies(
        id="grizzly_bear", display_name="Grizzly Bear",
        danger_level=2, size="very_large",
        primary_habitats=["mountains", "foothills", "dense forest", "gravel bars"],
        core_regions=["Sierra Nevada", "California Coast Ranges", "Northern California", "Rocky Mountains"],
        base_spawn_chance=0.07,
        meat_yield_lb=350.0, hide_value=15.0,
        notes="Extremely dangerous and still common in California during the early Gold Rush."
    ),
    WildlifeType.BLACK_BEAR: WildlifeSpecies(
        id="black_bear", display_name="American Black Bear",
        danger_level=1, size="large",
        primary_habitats=["forest", "mountains", "brush", "river valleys"],
        core_regions=["Sierra Nevada", "California", "Pacific Northwest", "Appalachians", "most wooded areas"],
        base_spawn_chance=0.18,
        meat_yield_lb=180.0, hide_value=6.5,
        notes="Widespread and generally less aggressive than grizzlies."
    ),
    WildlifeType.MOUNTAIN_LION: WildlifeSpecies(
        id="mountain_lion", display_name="Mountain Lion",
        danger_level=2, size="large",
        primary_habitats=["mountains", "foothills", "dense brush"],
        core_regions=["Sierra Nevada", "California Coast Ranges", "Rockies", "Western mountains"],
        base_spawn_chance=0.09,
        meat_yield_lb=80.0, hide_value=8.0,
        notes="Stealthy ambush predator. Rarely seen until it's too late."
    ),
    WildlifeType.BUFFALO: WildlifeSpecies(
        id="buffalo", display_name="Plains Bison",
        danger_level=2, size="very_large",
        primary_habitats=["prairie", "plains", "open grassland", "river valleys"],
        core_regions=["Great Plains", "Central Plains", "Northern Plains", "Eastern Colorado", "Montana plains"],
        base_spawn_chance=0.25,
        meat_yield_lb=500.0, hide_value=18.0,
        notes="Iconic Great Plains animal. Huge food source but dangerous when provoked."
    ),
    WildlifeType.ELK: WildlifeSpecies(
        id="elk", display_name="Elk",
        danger_level=1, size="large",
        primary_habitats=["mountains", "foothills", "open woodland"],
        core_regions=["Sierra Nevada", "Rockies", "Pacific Northwest"],
        base_spawn_chance=0.15,
        meat_yield_lb=300.0, hide_value=12.0,
        notes="Major game animal in mountainous regions."
    ),
    WildlifeType.MULE_DEER: WildlifeSpecies(
        id="mule_deer", display_name="Mule Deer",
        danger_level=0, size="medium",
        primary_habitats=["foothills", "mountains", "brush"],
        core_regions=["Sierra Nevada", "California", "Western mountains"],
        base_spawn_chance=0.35,
        meat_yield_lb=90.0, hide_value=4.0,
        notes="Very common in California mining country."
    ),
    WildlifeType.BLACK_TAILED_DEER: WildlifeSpecies(
        id="black_tailed_deer", display_name="Black-tailed Deer",
        danger_level=0, size="medium",
        primary_habitats=["coastal forest", "brush"],
        core_regions=["California Coast", "Pacific Northwest"],
        base_spawn_chance=0.28,
        meat_yield_lb=75.0, hide_value=3.5,
        notes="Common along the California coast."
    ),
    WildlifeType.PRONGHORN: WildlifeSpecies(
        id="pronghorn", display_name="Pronghorn Antelope",
        danger_level=0, size="medium",
        primary_habitats=["open plains", "prairie", "scrub"],
        core_regions=["Great Plains", "Great Basin", "Eastern Rockies"],
        base_spawn_chance=0.20,
        meat_yield_lb=70.0, hide_value=5.0,
        notes="Fastest land animal in North America. Plains specialist."
    ),
    WildlifeType.BIGHORN_SHEEP: WildlifeSpecies(
        id="bighorn_sheep", display_name="Bighorn Sheep",
        danger_level=0, size="medium",
        primary_habitats=["rocky mountains", "steep cliffs"],
        core_regions=["Sierra Nevada", "Rockies", "Desert Southwest"],
        base_spawn_chance=0.12,
        meat_yield_lb=80.0, hide_value=7.0,
        notes="Lives on steep rocky terrain."
    ),
    WildlifeType.COYOTE: WildlifeSpecies(
        id="coyote", display_name="Coyote",
        danger_level=0, size="medium",
        primary_habitats=["open terrain", "prairie", "scrub", "foothills"],
        core_regions=["Most of North America"],
        base_spawn_chance=0.25,
        meat_yield_lb=25.0, hide_value=1.5,
        notes="Widespread and adaptable."
    ),
    WildlifeType.RATTLESNAKE: WildlifeSpecies(
        id="rattlesnake", display_name="Rattlesnake",
        danger_level=1, size="small",
        primary_habitats=["dry grass", "rocky slopes", "scrub"],
        core_regions=["California", "Southwest", "Great Plains", "Rockies"],
        base_spawn_chance=0.18,
        meat_yield_lb=2.0, hide_value=0.5,
        notes="Common near rocks and gravel bars in warm weather."
    ),
    WildlifeType.BEAVER: WildlifeSpecies(
        id="beaver", display_name="Beaver",
        danger_level=0, size="medium",
        primary_habitats=["streams", "rivers", "ponds"],
        core_regions=["Most of North America with water"],
        base_spawn_chance=0.14,
        meat_yield_lb=35.0, hide_value=4.0,
        notes="Valuable fur animal. Good indicator of water."
    ),
    WildlifeType.GRAY_WOLF: WildlifeSpecies(
        id="gray_wolf", display_name="Gray Wolf",
        danger_level=2, size="large",
        primary_habitats=["mountains", "forest", "foothills"],
        core_regions=["Rocky Mountains", "Montana Goldfields", "Idaho Silver Belt",
                      "Pacific Northwest", "Alaska Interior"],
        base_spawn_chance=0.10,
        meat_yield_lb=55.0, hide_value=8.0,
        notes="Pack predator. Dangerous in groups."
    ),
    WildlifeType.MOOSE: WildlifeSpecies(
        id="moose", display_name="Moose",
        danger_level=1, size="very_large",
        primary_habitats=["forest", "streams", "brush", "tundra"],
        core_regions=["Alaska Interior", "Montana Goldfields", "Idaho Silver Belt",
                      "Pacific Northwest", "Rocky Mountains"],
        base_spawn_chance=0.08,
        meat_yield_lb=500.0, hide_value=14.0,
        notes="Largest deer. Defensive — will charge if provoked."
    ),
    WildlifeType.RED_FOX: WildlifeSpecies(
        id="red_fox", display_name="Red Fox",
        danger_level=0, size="small",
        primary_habitats=["forest", "brush", "foothills", "open terrain"],
        core_regions=["Most of North America"],
        base_spawn_chance=0.18,
        meat_yield_lb=8.0, hide_value=3.0,
        notes="Widespread. Shy and rarely seen."
    ),
    WildlifeType.GRAY_FOX: WildlifeSpecies(
        id="gray_fox", display_name="Gray Fox",
        danger_level=0, size="small",
        primary_habitats=["forest", "brush", "rocky slopes"],
        core_regions=["California Coast Ranges", "Sierra Nevada Foothills",
                      "Appalachians", "Pacific Northwest"],
        base_spawn_chance=0.15,
        meat_yield_lb=7.0, hide_value=2.5,
        notes="Can climb trees. Prefers wooded terrain."
    ),
    WildlifeType.RACCOON: WildlifeSpecies(
        id="raccoon", display_name="Raccoon",
        danger_level=0, size="small",
        primary_habitats=["forest", "streams", "brush"],
        core_regions=["Most of North America"],
        base_spawn_chance=0.22,
        meat_yield_lb=12.0, hide_value=1.5,
        notes="Nocturnal. Will raid camps for food."
    ),
    WildlifeType.BOBCAT: WildlifeSpecies(
        id="bobcat", display_name="Bobcat",
        danger_level=0, size="medium",
        primary_habitats=["brush", "rocky slopes", "forest", "scrub"],
        core_regions=["Most of North America"],
        base_spawn_chance=0.10,
        meat_yield_lb=18.0, hide_value=4.0,
        notes="Solitary. Rarely attacks humans."
    ),
    WildlifeType.JACKRABBIT: WildlifeSpecies(
        id="jackrabbit", display_name="Black-tailed Jackrabbit",
        danger_level=0, size="small",
        primary_habitats=["scrub", "prairie", "open terrain"],
        core_regions=["California Central Valley", "Nevada Great Basin",
                      "Great Plains", "Sierra Nevada Foothills"],
        base_spawn_chance=0.40,
        meat_yield_lb=4.0, hide_value=0.25,
        notes="Very common. Fast runner."
    ),
    WildlifeType.GROUND_SQUIRREL: WildlifeSpecies(
        id="ground_squirrel", display_name="California Ground Squirrel",
        danger_level=0, size="small",
        primary_habitats=["open terrain", "scrub", "foothills"],
        core_regions=["California Central Valley", "California Coast Ranges",
                      "Sierra Nevada Foothills", "Nevada Great Basin"],
        base_spawn_chance=0.45,
        meat_yield_lb=1.0, hide_value=0.10,
        notes="Ubiquitous. Barely worth hunting."
    ),
    WildlifeType.BALD_EAGLE: WildlifeSpecies(
        id="bald_eagle", display_name="Bald Eagle",
        danger_level=0, size="medium",
        primary_habitats=["rivers", "streams", "coast", "mountains"],
        core_regions=["Pacific Northwest", "Alaska Interior", "Montana Goldfields",
                      "Rocky Mountains", "Appalachians"],
        base_spawn_chance=0.06,
        meat_yield_lb=6.0, hide_value=0.50,
        notes="Majestic raptor. Prized feathers."
    ),
    WildlifeType.CALIFORNIA_CONDOR: WildlifeSpecies(
        id="california_condor", display_name="California Condor",
        danger_level=0, size="large",
        primary_habitats=["mountains", "rocky cliffs"],
        core_regions=["California Coast Ranges", "Sierra Nevada Foothills"],
        base_spawn_chance=0.02,
        meat_yield_lb=15.0, hide_value=1.0,
        notes="Extremely rare even in 1849. Largest NA land bird."
    ),
    WildlifeType.WILD_TURKEY: WildlifeSpecies(
        id="wild_turkey", display_name="Wild Turkey",
        danger_level=0, size="small",
        primary_habitats=["forest", "open woodland", "brush"],
        core_regions=["Appalachians", "California Coast Ranges",
                      "Sierra Nevada Foothills", "Pacific Northwest"],
        base_spawn_chance=0.20,
        meat_yield_lb=10.0, hide_value=0.25,
        notes="Good eating. Found in flocks near oak woodland."
    ),

    # === FUR-BEARERS ===
    WildlifeType.RIVER_OTTER: WildlifeSpecies(
        id="river_otter", display_name="River Otter",
        danger_level=0, size="medium",
        primary_habitats=["rivers", "streams", "coast"],
        core_regions=["Pacific Northwest", "Sierra Nevada", "Appalachians",
                      "Alaska Interior", "Rocky Mountains"],
        base_spawn_chance=0.10,
        meat_yield_lb=15.0, hide_value=6.00,
        notes="Playful, fast swimmer. Prized waterproof fur."
    ),
    WildlifeType.MINK: WildlifeSpecies(
        id="mink", display_name="Mink",
        danger_level=0, size="small",
        primary_habitats=["rivers", "streams", "brush"],
        core_regions=["Pacific Northwest", "Appalachians", "Great Lakes",
                      "Rocky Mountains", "Sierra Nevada"],
        base_spawn_chance=0.08,
        meat_yield_lb=2.0, hide_value=4.00,
        notes="Small, fierce. Premium dark fur."
    ),
    WildlifeType.PINE_MARTEN: WildlifeSpecies(
        id="pine_marten", display_name="Pine Marten",
        danger_level=0, size="small",
        primary_habitats=["mountains", "forest", "dense forest"],
        core_regions=["Rocky Mountains", "Pacific Northwest",
                      "Sierra Nevada", "Alaska Interior"],
        base_spawn_chance=0.07,
        meat_yield_lb=3.0, hide_value=5.00,
        notes="Arboreal. Soft, thick fur. Elusive."
    ),
    WildlifeType.FISHER: WildlifeSpecies(
        id="fisher", display_name="Fisher",
        danger_level=0, size="medium",
        primary_habitats=["dense forest", "forest", "mountains"],
        core_regions=["Pacific Northwest", "Appalachians",
                      "Rocky Mountains", "Sierra Nevada"],
        base_spawn_chance=0.05,
        meat_yield_lb=8.0, hide_value=7.00,
        notes="Large weasel. Rare. Extremely valuable fur."
    ),
    WildlifeType.WOLVERINE: WildlifeSpecies(
        id="wolverine", display_name="Wolverine",
        danger_level=2, size="medium",
        primary_habitats=["mountains", "tundra", "dense forest"],
        core_regions=["Rocky Mountains", "Alaska Interior",
                      "Montana Goldfields", "Pacific Northwest"],
        base_spawn_chance=0.03,
        meat_yield_lb=20.0, hide_value=8.00,
        notes="Fearless, powerful. Will fight anything. Premium fur."
    ),
    WildlifeType.BADGER: WildlifeSpecies(
        id="badger", display_name="Badger",
        danger_level=1, size="medium",
        primary_habitats=["prairie", "scrub", "open terrain"],
        core_regions=["Great Plains", "Central Plains", "Rocky Mountains",
                      "Nevada Great Basin", "Sierra Nevada Foothills"],
        base_spawn_chance=0.10,
        meat_yield_lb=12.0, hide_value=2.00,
        notes="Aggressive when cornered. Tough hide."
    ),
    WildlifeType.SKUNK: WildlifeSpecies(
        id="skunk", display_name="Striped Skunk",
        danger_level=0, size="small",
        primary_habitats=["brush", "forest", "open terrain"],
        core_regions=["California", "Great Plains", "Appalachians",
                      "Pacific Northwest", "Rocky Mountains"],
        base_spawn_chance=0.15,
        meat_yield_lb=3.0, hide_value=1.00,
        notes="Unmistakable smell. Low-value fur but easy to trap."
    ),
    WildlifeType.MUSKRAT: WildlifeSpecies(
        id="muskrat", display_name="Muskrat",
        danger_level=0, size="small",
        primary_habitats=["rivers", "streams", "brush"],
        core_regions=["Appalachians", "Great Plains", "Pacific Northwest",
                      "Great Lakes", "Rocky Mountains"],
        base_spawn_chance=0.18,
        meat_yield_lb=2.0, hide_value=1.50,
        notes="Common in marshes. Bread-and-butter trapping."
    ),
    WildlifeType.OPOSSUM: WildlifeSpecies(
        id="opossum", display_name="Opossum",
        danger_level=0, size="small",
        primary_habitats=["forest", "brush", "open terrain"],
        core_regions=["Appalachians", "Gulf Coast", "California Coast Ranges",
                      "Central Plains"],
        base_spawn_chance=0.15,
        meat_yield_lb=4.0, hide_value=0.50,
        notes="Plays dead. Low-value fur."
    ),
    WildlifeType.LYNX: WildlifeSpecies(
        id="lynx", display_name="Canada Lynx",
        danger_level=1, size="medium",
        primary_habitats=["forest", "mountains", "dense forest"],
        core_regions=["Rocky Mountains", "Alaska Interior",
                      "Montana Goldfields", "Pacific Northwest"],
        base_spawn_chance=0.05,
        meat_yield_lb=18.0, hide_value=6.00,
        notes="Elusive cat. Valuable spotted fur. Hunts snowshoe hare."
    ),
}


def get_possible_wildlife(world_region: str, terrain_hint: str = "") -> List[WildlifeSpecies]:
    """Return list of wildlife that could plausibly appear in this region."""
    candidates = []
    for species in WILDLIFE_DB.values():
        # Check if region matches any core region
        if any(r.lower() in world_region.lower() for r in species.core_regions):
            if not terrain_hint or any(h.lower() in terrain_hint.lower() for h in species.primary_habitats):
                candidates.append(species)
    return candidates