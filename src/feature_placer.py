"""
src/feature_placer.py

Places special placer gold features on local maps based on region and geology.
Creates believable "hot spots" where gold concentrates.
"""

import random
from typing import List

from src.local_map import LocalTerrain
from src.regions import REGIONS


class FeatureType:
    INSIDE_BEND = "inside_bend"
    GRAVEL_BAR = "gravel_bar"
    BEDROCK_EXPOSURE = "bedrock_exposure"
    BLACK_SAND_DEPOSIT = "black_sand_deposit"
    PAY_STREAK = "pay_streak"
    BOULDER_TRAP = "boulder_trap"


class FeaturePlacer:
    """
    Places gold-rich features intelligently on the local map.
    """

    def __init__(self, rng: random.Random):
        self.rng = rng

    def place_features(self, local_map, region_name: str, gold_bias: float):
        """Place appropriate placer features based on region."""
        num_features = int(18 * gold_bias)

        if "Sierra Nevada" in region_name or "California" in region_name:
            self._place_sierra_features(local_map, num_features)
        elif "Great Plains" in region_name:
            self._place_plains_features(local_map, num_features // 2)
        elif "Alaska" in region_name:
            self._place_alaska_features(local_map, num_features // 2)
        else:
            self._place_default_features(local_map, num_features)

    def _place_sierra_features(self, local_map, count: int):
        """Rich placer country — lots of bends, bedrock, and gravel bars."""
        for _ in range(count):
            x = self.rng.randint(15, local_map.width - 15)
            y = self.rng.randint(15, local_map.height - 15)

            tile = local_map.tiles[y][x]

            roll = self.rng.random()
            if roll < 0.35:
                # Inside bend / rich gravel bar
                tile.terrain = LocalTerrain.GRAVEL_BAR
                tile.gold_grade = 0.55 + self.rng.random() * 0.45
            elif roll < 0.65:
                # Bedrock exposure with cracks
                tile.terrain = LocalTerrain.BEDROCK
                tile.gold_grade = 0.70 + self.rng.random() * 0.5
            elif roll < 0.85:
                # Black sand deposit
                tile.terrain = LocalTerrain.GRAVEL_BAR
                tile.gold_grade = 0.45 + self.rng.random() * 0.35
            else:
                # Boulder trap
                tile.gold_grade = 0.6 + self.rng.random() * 0.4

    def _place_plains_features(self, local_map, count: int):
        """Sparse features — occasional river bars."""
        for _ in range(count):
            x = self.rng.randint(20, local_map.width - 20)
            y = self.rng.randint(20, local_map.height - 20)
            if local_map.tiles[y][x].terrain != LocalTerrain.WATER:
                local_map.tiles[y][x].terrain = LocalTerrain.GRAVEL_BAR
                local_map.tiles[y][x].gold_grade = 0.15 + self.rng.random() * 0.25

    def _place_alaska_features(self, local_map, count: int):
        """Colder, steeper streams with fewer but richer pockets."""
        for _ in range(count):
            x = self.rng.randint(20, local_map.width - 20)
            y = self.rng.randint(20, local_map.height - 20)
            tile = local_map.tiles[y][x]
            if tile.terrain != LocalTerrain.WATER:
                tile.terrain = LocalTerrain.BEDROCK
                tile.gold_grade = 0.4 + self.rng.random() * 0.6

    def _place_default_features(self, local_map, count: int):
        """Fallback for other regions."""
        for _ in range(count):
            x = self.rng.randint(25, local_map.width - 25)
            y = self.rng.randint(25, local_map.height - 25)
            if local_map.tiles[y][x].terrain not in (LocalTerrain.WATER, LocalTerrain.ROCK):
                local_map.tiles[y][x].gold_grade = 0.2 + self.rng.random() * 0.4

    # Bonus: Place features along existing streams
    def enhance_streams(self, local_map):
        """Add extra placer features near water after streams are placed."""
        for y in range(1, local_map.height - 1):
            for x in range(1, local_map.width - 1):
                if local_map.tiles[y][x].terrain == LocalTerrain.WATER:
                    # Check adjacent tiles for gravel/bedrock enhancement
                    for dx, dy in [(0,1),(0,-1),(1,0),(-1,0)]:
                        nx, ny = x + dx, y + dy
                        if local_map.in_bounds(nx, ny):
                            tile = local_map.tiles[ny][nx]
                            if tile.terrain in (LocalTerrain.GRASS, LocalTerrain.GROUND):
                                if self.rng.random() < 0.65:
                                    tile.terrain = LocalTerrain.GRAVEL_BAR
                                    tile.gold_grade = max(tile.gold_grade, 0.35 + self.rng.random() * 0.45)