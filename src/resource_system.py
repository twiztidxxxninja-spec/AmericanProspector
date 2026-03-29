"""
src/resource_system.py

Unified resource system for all mining types across 1849–2000.
Geologically driven and era-aware.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Optional, Tuple


class ResourceType(Enum):
    PLACER_GOLD = "placer_gold"
    LODE_GOLD = "lode_gold"
    SILVER = "silver"
    LEAD = "lead"
    MERCURY = "mercury"
    COAL = "coal"
    OIL = "oil"
    NATURAL_GAS = "natural_gas"
    URANIUM = "uranium"          # later eras


class ExtractionMethod(Enum):
    PANNING = "panning"
    ROCKER = "rocker"
    SLUICE = "sluice"
    HYDRAULIC = "hydraulic"
    HARD_ROCK_DRIFT = "hard_rock_drift"
    HARD_ROCK_SHAFT = "hard_rock_shaft"
    COAL_ROOM_PILLAR = "coal_room_pillar"
    OIL_CABLE_TOOL = "oil_cable_tool"
    OIL_ROTARY = "oil_rotary"


@dataclass
class ResourceDeposit:
    resource_type: ResourceType
    primary_geology: str          # e.g. "quartz_vein", "sedimentary_basin", "anticline"
    typical_depth: int            # feet to main deposit
    grade_range: Tuple[float, float]   # 0.0-1.0
    extraction_methods: List[ExtractionMethod]
    era_availability: Tuple[int, int]  # start_year, end_year (or None)
    base_value_per_unit: float         # dollars per ton/oz/barrel etc.
    notes: str = ""


RESOURCE_DB: Dict[ResourceType, ResourceDeposit] = {
    ResourceType.PLACER_GOLD: ResourceDeposit(
        resource_type=ResourceType.PLACER_GOLD,
        primary_geology="stream_gravel_bedrock_traps",
        typical_depth=6,
        grade_range=(0.1, 0.9),
        extraction_methods=[ExtractionMethod.PANNING, ExtractionMethod.ROCKER, ExtractionMethod.SLUICE, ExtractionMethod.HYDRAULIC],
        era_availability=(1849, 2000),
        base_value_per_unit=20.67,   # 1849 price per oz
        notes="Concentrates in inside bends, bedrock cracks, behind boulders."
    ),
    ResourceType.LODE_GOLD: ResourceDeposit(
        resource_type=ResourceType.LODE_GOLD,
        primary_geology="quartz_vein",
        typical_depth=80,
        grade_range=(0.3, 0.95),
        extraction_methods=[ExtractionMethod.HARD_ROCK_DRIFT, ExtractionMethod.HARD_ROCK_SHAFT],
        era_availability=(1850, 2000),
        base_value_per_unit=20.67,
        notes="Veins in hard rock. Requires drilling, blasting, mucking."
    ),
    ResourceType.SILVER: ResourceDeposit(
        resource_type=ResourceType.SILVER,
        primary_geology="quartz_vein_sulfide",
        typical_depth=120,
        grade_range=(0.4, 0.85),
        extraction_methods=[ExtractionMethod.HARD_ROCK_DRIFT, ExtractionMethod.HARD_ROCK_SHAFT],
        era_availability=(1859, 2000),
        base_value_per_unit=1.25,   # historical silver price per oz
        notes="Often associated with gold (Comstock Lode style)."
    ),
    ResourceType.COAL: ResourceDeposit(
        resource_type=ResourceType.COAL,
        primary_geology="sedimentary_basin",
        typical_depth=200,
        grade_range=(0.6, 0.95),
        extraction_methods=[ExtractionMethod.COAL_ROOM_PILLAR],
        era_availability=(1870, 2000),
        base_value_per_unit=0.08,   # per ton
        notes="Large volume, requires timbering and ventilation."
    ),
    ResourceType.OIL: ResourceDeposit(
        resource_type=ResourceType.OIL,
        primary_geology="anticline_sedimentary_trap",
        typical_depth=800,
        grade_range=(0.4, 0.9),
        extraction_methods=[ExtractionMethod.OIL_CABLE_TOOL, ExtractionMethod.OIL_ROTARY],
        era_availability=(1901, 2000),
        base_value_per_unit=2.50,   # per barrel early 1900s
        notes="Requires drilling rigs. Spindletop-style booms possible."
    ),
    # Add mercury, lead, uranium, natural gas as needed
}


class ResourceSystem:
    """
    Central system for all resources.
    """

    @staticmethod
    def get_deposit_for_region(region_name: str, resource_type: ResourceType) -> Optional[ResourceDeposit]:
        """Return whether this region can host this resource and with what strength."""
        deposit = RESOURCE_DB.get(resource_type)
        if not deposit:
            return None

        # Simple region matching (expand with more rules)
        if resource_type == ResourceType.PLACER_GOLD and any(x in region_name.lower() for x in ["sierra", "california", "foothills"]):
            return deposit
        if resource_type == ResourceType.LODE_GOLD and "mountain" in region_name.lower():
            return deposit
        if resource_type == ResourceType.COAL and "basin" in region_name.lower():
            return deposit
        if resource_type == ResourceType.OIL and any(x in region_name.lower() for x in ["texas", "oklahoma", "california"]):
            return deposit

        return deposit  # default — allow everywhere with low probability

    @staticmethod
    def is_era_compatible(resource_type: ResourceType, year: int) -> bool:
        deposit = RESOURCE_DB.get(resource_type)
        if not deposit:
            return False
        start, end = deposit.era_availability
        return start <= year <= (end or 9999)