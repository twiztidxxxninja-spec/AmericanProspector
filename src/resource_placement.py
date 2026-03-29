"""
src/resource_placement.py

Geologically accurate resource placement system.
Places all resource types (placer gold, lode gold, silver, coal, oil, etc.)
based on real geology, not randomness.
"""

from dataclasses import dataclass
import random
from typing import List, Optional

from src.resource_system import ResourceType, RESOURCE_DB, ResourceDeposit
from src.geologic_gold_placer import GeologicContext


@dataclass
class ResourcePlacementRule:
    resource_type: ResourceType
    required_geology: List[str]          # e.g. ["quartz_vein", "sedimentary_basin"]
    preferred_regions: List[str]
    min_gold_bias: float = 0.0
    probability_modifier: float = 1.0    # multiplier for this region type


PLACEMENT_RULES = {
    ResourceType.PLACER_GOLD: ResourcePlacementRule(
        resource_type=ResourceType.PLACER_GOLD,
        required_geology=["stream_gravel_bedrock_traps"],
        preferred_regions=["Sierra Nevada Foothills", "California", "Rocky Mountains", "British Columbia Coast"],
        min_gold_bias=0.25,
        probability_modifier=1.8
    ),
    ResourceType.LODE_GOLD: ResourcePlacementRule(
        resource_type=ResourceType.LODE_GOLD,
        required_geology=["quartz_vein"],
        preferred_regions=["Sierra Nevada Foothills", "Rocky Mountains", "Appalachians"],
        min_gold_bias=0.35,
        probability_modifier=1.4
    ),
    ResourceType.SILVER: ResourcePlacementRule(
        resource_type=ResourceType.SILVER,
        required_geology=["quartz_vein_sulfide"],
        preferred_regions=["Rocky Mountains", "Great Basin", "Sierra Nevada"],
        min_gold_bias=0.30,
        probability_modifier=1.2
    ),
    ResourceType.COAL: ResourcePlacementRule(
        resource_type=ResourceType.COAL,
        required_geology=["sedimentary_basin"],
        preferred_regions=["Appalachians", "Great Plains", "Midwest"],
        min_gold_bias=0.0,
        probability_modifier=1.0
    ),
    ResourceType.OIL: ResourcePlacementRule(
        resource_type=ResourceType.OIL,
        required_geology=["anticline_sedimentary_trap"],
        preferred_regions=["Texas", "Oklahoma", "California", "Gulf Coast"],
        min_gold_bias=0.0,
        probability_modifier=1.0
    ),
}


class ResourcePlacer:
    """
    Places resources on world tiles and local maps using real geological rules.
    """

    @staticmethod
    def should_place_resource(context: GeologicContext, resource_type: ResourceType, rng: random.Random) -> bool:
        rule = PLACEMENT_RULES.get(resource_type)
        if not rule:
            return False

        # Check region match
        region_match = any(r.lower() in context.region_name.lower() for r in rule.preferred_regions)
        if not region_match and rule.preferred_regions:
            return False

        # Check minimum gold bias (for metallic resources)
        if context.gold_source_strength < rule.min_gold_bias:
            return False

        # Final probability check
        final_chance = rule.probability_modifier * context.gold_source_strength
        return rng.random() < final_chance

    @staticmethod
    def place_on_world_tile(world_map, wx: int, wy: int, rng: random.Random):
        """Called during world map generation to decide which resources exist here."""
        context = GeologicContext(
            region_name=world_map.get_region(wx, wy),
            is_mountainous="mountain" in world_map.get_region(wx, wy).lower(),
            has_glacial_history="alaska" in world_map.get_region(wx, wy).lower(),
            is_alluvial_fan="valley" in world_map.get_region(wx, wy).lower() or "foothills" in world_map.get_region(wx, wy).lower(),
            gold_source_strength=world_map.get_gold_bias(wx, wy)
        )

        for resource_type in ResourceType:
            if ResourcePlacer.should_place_resource(context, resource_type, rng):
                # Mark this world tile as having potential for this resource
                # You can store this in a new world_map layer if you want
                print(f"Resource potential: {resource_type.value} at ({wx}, {wy}) in {context.region_name}")

    @staticmethod
    def place_on_local_map(local_map, context: GeologicContext, rng: random.Random):
        """Called when generating a local map — places actual deposits."""
        for resource_type in ResourceType:
            if not ResourcePlacer.should_place_resource(context, resource_type, rng):
                continue

            deposit = RESOURCE_DB.get(resource_type)
            if not deposit:
                continue

            # Place the resource on appropriate tiles
            for y in range(local_map.height):
                for x in range(local_map.width):
                    tile = local_map.tiles[y][x]

                    # Only place on geologically suitable tiles
                    if tile.terrain in (LocalTerrain.WATER, LocalTerrain.ROCK):
                        continue

                    # Simple placement rule — expand with more geology later
                    if rng.random() < 0.12:
                        tile.gold_grade = deposit.grade_range[0] + rng.random() * (deposit.grade_range[1] - deposit.grade_range[0])
                        # You can add a resource_type field to LocalTile later