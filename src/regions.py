"""
src/regions.py

Historical and geographic region definitions for American Prospector (1849–2000).
Used to guide procedural generation at Area and Local levels.
"""

from dataclasses import dataclass
from typing import List, Dict


@dataclass
class GameRegion:
    name: str
    description: str
    gold_bias: float          # 0.0–1.0 — how gold-rich this region is in 1849
    terrain_bias: List[str]   # dominant terrain types
    stream_density: float     # 0.0–1.0 — how many streams/creeks to generate
    feature_richness: float   # how many special placer features (bends, bedrock, etc.)
    common_features: List[str]
    notes: str = ""


REGIONS: Dict[str, GameRegion] = {
    "Sierra Nevada Foothills": GameRegion(
        name="Sierra Nevada Foothills",
        description="Classic 1849 Gold Rush country. Steep canyons, fast streams, and rich placer deposits.",
        gold_bias=0.85,
        terrain_bias=["hills", "mountains", "forest"],
        stream_density=0.75,
        feature_richness=0.90,
        common_features=["inside_bend", "bedrock_exposure", "gravel_bar", "black_sand"],
        notes="Highest gold potential in the early game. Many rich strikes occurred here."
    ),
    "California Central Valley": GameRegion(
        name="California Central Valley",
        description="Flat farmland and river corridors. Some placer gold near rivers.",
        gold_bias=0.35,
        terrain_bias=["plains", "river"],
        stream_density=0.60,
        feature_richness=0.45,
        common_features=["gravel_bar", "side_channel"],
        notes="Good for travel and farming, but poorer placer ground than the foothills."
    ),
    "California Coast Ranges": GameRegion(
        name="California Coast Ranges",
        description="Rugged coastal mountains with some gold-bearing streams.",
        gold_bias=0.40,
        terrain_bias=["hills", "mountains"],
        stream_density=0.65,
        feature_richness=0.60,
        common_features=["inside_bend", "bedrock_exposure"],
        notes="Moderate gold potential."
    ),
    "Nevada Great Basin": GameRegion(
        name="Nevada Great Basin",
        description="Dry basin-and-range country. Silver and gold lode deposits.",
        gold_bias=0.65,
        terrain_bias=["desert", "scrub", "mountains"],
        stream_density=0.35,
        feature_richness=0.60,
        common_features=["lode_outcrop", "dry_wash", "bedrock_exposure"],
        notes="Comstock Lode country. Lode silver and gold."
    ),
    "Rocky Mountains": GameRegion(
        name="Rocky Mountains",
        description="High, rugged peaks. Lode gold, silver, and placer in valleys.",
        gold_bias=0.55,
        terrain_bias=["mountains"],
        stream_density=0.70,
        feature_richness=0.65,
        common_features=["bedrock_exposure", "boulder_field", "lode_outcrop"],
        notes="Leadville, Cripple Creek — major late-era strikes."
    ),
    "Black Hills": GameRegion(
        name="Black Hills",
        description="Isolated forested granite hills. Rich placer and lode gold.",
        gold_bias=0.78,
        terrain_bias=["hills", "forest"],
        stream_density=0.55,
        feature_richness=0.80,
        common_features=["inside_bend", "bedrock_exposure", "gravel_bar"],
        notes="Deadwood. Homestake Mine. Major gold region from 1875 onward."
    ),
    "Montana Goldfields": GameRegion(
        name="Montana Goldfields",
        description="Mountain creeks and copper districts. Placer then hard rock.",
        gold_bias=0.65,
        terrain_bias=["mountains", "conifer"],
        stream_density=0.60,
        feature_richness=0.70,
        common_features=["gravel_bar", "bedrock_exposure"],
        notes="Butte copper, Helena gold."
    ),
    "Idaho Silver Belt": GameRegion(
        name="Idaho Silver Belt",
        description="Rugged mountains with silver and placer gold deposits.",
        gold_bias=0.55,
        terrain_bias=["mountains", "conifer"],
        stream_density=0.60,
        feature_richness=0.65,
        common_features=["lode_outcrop", "bedrock_exposure"],
    ),
    "Great Plains": GameRegion(
        name="Great Plains",
        description="Vast open grasslands. Very little gold.",
        gold_bias=0.05,
        terrain_bias=["prairie", "plains"],
        stream_density=0.30,
        feature_richness=0.10,
        common_features=["river", "dry_wash"],
        notes="Buffalo country. Almost no placer gold."
    ),
    "Gulf Coast": GameRegion(
        name="Gulf Coast",
        description="Lowlands and swamps. Oil seeps in Texas. Almost no gold.",
        gold_bias=0.02,
        terrain_bias=["swamp", "plains", "coast"],
        stream_density=0.50,
        feature_richness=0.10,
        common_features=["river", "swamp"],
        notes="Oil country from 1901 onward."
    ),
    "Alaska Interior": GameRegion(
        name="Alaska Interior",
        description="Remote, harsh wilderness. Placer gold in the creek beds.",
        gold_bias=0.70,
        terrain_bias=["tundra", "mountains", "conifer"],
        stream_density=0.55,
        feature_richness=0.65,
        common_features=["gravel_bar", "bedrock_exposure"],
        notes="Fairbanks, Klondike gateway. Becomes critical post-1896."
    ),
    "Pacific Northwest": GameRegion(
        name="Pacific Northwest",
        description="Dense forests, rivers. Some placer gold in streams.",
        gold_bias=0.30,
        terrain_bias=["mountains", "conifer", "coast"],
        stream_density=0.80,
        feature_richness=0.40,
        common_features=["inside_bend", "gravel_bar"],
    ),
    "Appalachians": GameRegion(
        name="Appalachians",
        description="Old mountains. Coal, iron, and some old gold workings.",
        gold_bias=0.20,
        terrain_bias=["hills", "mountains", "forest"],
        stream_density=0.65,
        feature_richness=0.35,
        common_features=["bedrock_exposure"],
        notes="Coal and oil (Titusville PA) more important than gold."
    ),
}

# ── Coordinate-based region lookup ────────────────────────────────────────────
# World grid: 400×200, approximately 10 mi/tile
# Anchor towns:  Sacramento (95,165)  Virginia City (114,158)  Denver (222,155)
#                Butte (178,88)  Deadwood (268,108)  Sacramento area y≈145-185

def get_region_for_world_tile(wx: int, wy: int) -> str:
    """Return the most appropriate region name for a world tile."""

    # Alaska / high north
    if wy < 55:
        if wx < 95:
            return "Alaska Interior"
        return "Pacific Northwest"

    # Pacific Northwest coast (Oregon / Washington)
    if wx < 90 and 55 <= wy < 120:
        return "Pacific Northwest"

    # California — split into coast, valley, and foothills/Nevada
    if wy >= 145:
        if wx < 80:
            return "California Coast Ranges"
        if wx < 96:
            return "California Central Valley"   # Sacramento valley floor
        if wx < 112:
            return "Sierra Nevada Foothills"     # gold country east of Sacramento

    # Nevada / Great Basin  (Reno, Virginia City, and basin-and-range east of Sierra)
    if 108 <= wx < 170 and 130 <= wy < 185:
        return "Nevada Great Basin"

    # Idaho silver belt
    if 140 <= wx < 165 and 110 <= wy < 150:
        return "Idaho Silver Belt"

    # Montana goldfields  (Butte ~178,88  Helena ~188,90)
    if 160 <= wx < 210 and 75 <= wy < 110:
        return "Montana Goldfields"

    # Rocky Mountains and Colorado mineral belt (Denver ~222,155  Leadville ~214,163)
    if 165 <= wx < 240 and 110 <= wy < 180:
        return "Rocky Mountains"

    # Black Hills — isolated high-gold region (Deadwood ~268,108)
    if 255 <= wx < 285 and 95 <= wy < 125:
        return "Black Hills"

    # Gulf Coast / Texas lowlands
    if wy >= 195:
        return "Gulf Coast"

    # Appalachians and eastern US
    if wx >= 295 and wy < 160:
        return "Appalachians"

    # Default: Great Plains
    return "Great Plains"


def get_gold_bias(wx: int, wy: int) -> float:
    """Return base gold potential for a world tile."""
    region = get_region_for_world_tile(wx, wy)
    return REGIONS.get(region, REGIONS["Great Plains"]).gold_bias