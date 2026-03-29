"""
src/volume_gold.py

Volumetric 3D gold depletion system.
Each tile is a vertical column with variable gold by depth.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import random


@dataclass
class DepthLayer:
    """One vertical slice of a tile's material."""
    gold_grade: float          # 0.0 - 1.0
    remaining_volume: float    # cubic yards left in this layer
    is_bedrock: bool = False


@dataclass
class GoldColumn:
    """A full vertical column under one local map tile."""
    layers: List[DepthLayer] = field(default_factory=list)
    total_dug_depth: int = 0          # how many "dig actions" have been performed
    tailings_volume: float = 0.0      # material moved to spoil pile

    def get_current_grade(self) -> float:
        """What grade you get at current digging depth."""
        if not self.layers:
            return 0.0
        current_layer = min(self.total_dug_depth, len(self.layers) - 1)
        return self.layers[current_layer].gold_grade

    def remove_volume(self, volume_removed: float) -> float:
        """Remove material and return gold recovered from that volume.

        Drains remaining_volume from each layer starting at total_dug_depth.
        Does NOT change total_dug_depth — that is controlled by the dig handler
        so that panning and sluicing don't artificially advance the dig depth.
        """
        gold_recovered = 0.0
        remaining = volume_removed

        for layer in self.layers[self.total_dug_depth:]:
            if remaining <= 0:
                break
            take = min(remaining, layer.remaining_volume)
            gold_recovered += take * layer.gold_grade
            layer.remaining_volume -= take
            remaining -= take

        return gold_recovered


class VolumeGoldSystem:
    """
    Creates and manages volumetric gold columns with realistic placer distribution.
    """

    @staticmethod
    def create_column(region_name: str, gold_bias: float, rng: random.Random) -> GoldColumn:
        column = GoldColumn()

        # Typical column has 8–12 layers (roughly 24–36 feet deep before true bedrock)
        num_layers = rng.randint(8, 12)

        base = gold_bias * 0.75

        for i in range(num_layers):
            depth_factor = i / num_layers

            # Gold increases with depth (classic placer behavior)
            grade = base * (0.3 + depth_factor * 1.8)

            # Surface layer is lean
            if i < 2:
                grade *= 0.45
            # Near bedrock gets a big bonus
            elif i >= num_layers - 3:
                grade *= 1.6

            # Small random variation per layer
            grade *= rng.uniform(0.85, 1.15)

            layer = DepthLayer(
                gold_grade=max(0.0, min(1.0, grade)),
                remaining_volume=1.0,          # 1 unit = 1 "shovel load" worth of material
                is_bedrock=(i == num_layers - 1)
            )
            column.layers.append(layer)

        return column

    @staticmethod
    def pan_volume(column: GoldColumn, volume: float = 0.02, placer_skill: int = 0) -> float:
        """One pan removes a very small volume."""
        return column.remove_volume(volume)

    @staticmethod
    def shovel_volume(column: GoldColumn, volume: float = 0.15, placer_skill: int = 0) -> float:
        """Shovel dig removes more material."""
        return column.remove_volume(volume)

    @staticmethod
    def sluice_volume(column: GoldColumn, volume: float = 1.2, placer_skill: int = 0) -> float:
        """Sluice processes much larger volume per run."""
        return column.remove_volume(volume)