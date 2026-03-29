"""
src/stream_generator.py

Realistic stream / creek generation for placer gold prospecting.
Creates meandering streams with good gold-trapping features.
"""

import random
from typing import List, Tuple

from src.local_map import LocalTerrain


class StreamGenerator:
    """
    Generates natural-looking streams with placer-friendly geology.
    """

    def __init__(self, rng: random.Random):
        self.rng = rng

    def generate_streams(self, local_map, count: int = 1, base_twist: float = 0.7):
        """
        Generate one or more streams on the local map.
        count: number of main streams
        base_twist: how windy the streams are (0.4 = gentle, 1.0 = very twisty)
        """
        for _ in range(count):
            self._generate_single_stream(local_map, base_twist)

    def _generate_single_stream(self, local_map, twist: float):
        """Generate one meandering stream with good placer features."""
        width = local_map.width
        height = local_map.height

        # Start the stream somewhere on the top or left side
        if self.rng.random() < 0.6:
            # Start from top, flow generally downward
            cx = self.rng.randint(width // 5, width * 4 // 5)
            cy = 5
            direction_bias = (0, 1)   # mostly down
        else:
            # Start from left, flow generally rightward
            cx = 5
            cy = self.rng.randint(height // 5, height * 4 // 5)
            direction_bias = (1, 0)   # mostly right

        points = []

        for step in range(max(width, height) * 2):
            points.append((cx, cy))

            # Add natural meandering
            twist_amount = self.rng.uniform(-twist, twist)
            cx += int(direction_bias[0] * 1.2 + twist_amount)
            cy += int(direction_bias[1] * 1.2 + self.rng.uniform(-twist * 0.8, twist * 0.8))

            # Keep stream inside bounds with soft margins
            cx = max(8, min(width - 9, cx))
            cy = max(8, min(height - 9, cy))

            # Occasionally change main direction slightly
            if self.rng.random() < 0.08:
                direction_bias = (direction_bias[0] + self.rng.uniform(-0.5, 0.5),
                                  direction_bias[1] + self.rng.uniform(-0.5, 0.5))

            # Place water and gravel features
            if local_map.in_bounds(cx, cy):
                local_map.tiles[cy][cx].terrain = LocalTerrain.WATER

                # Gravel bars on inside bends (higher chance on tighter turns)
                if self.rng.random() < 0.75:
                    for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
                        nx, ny = cx + dx, cy + dy
                        if local_map.in_bounds(nx, ny):
                            if local_map.tiles[ny][nx].terrain != LocalTerrain.WATER:
                                local_map.tiles[ny][nx].terrain = LocalTerrain.GRAVEL_BAR
                                # Boost gold on gravel bars
                                local_map.tiles[ny][nx].gold_grade = max(
                                    local_map.tiles[ny][nx].gold_grade, 
                                    0.35 + self.rng.random() * 0.45
                                )

                # Occasional bedrock exposure near stream
                if self.rng.random() < 0.12:
                    for dx, dy in [(-1,-1), (-1,1), (1,-1), (1,1)]:
                        nx, ny = cx + dx, cy + dy
                        if local_map.in_bounds(nx, ny):
                            if local_map.tiles[ny][nx].terrain not in (LocalTerrain.WATER, LocalTerrain.GRAVEL_BAR):
                                local_map.tiles[ny][nx].terrain = LocalTerrain.BEDROCK
                                local_map.tiles[ny][nx].gold_grade = 0.6 + self.rng.random() * 0.6

            # Stop if we reach the opposite side
            if (direction_bias[0] > 0 and cx > width * 0.85) or \
               (direction_bias[1] > 0 and cy > height * 0.85):
                break

    def add_side_channels(self, local_map, probability: float = 0.35):
        """Add small side channels and pools for extra placer variety."""
        for y in range(10, local_map.height - 10):
            for x in range(10, local_map.width - 10):
                if local_map.tiles[y][x].terrain == LocalTerrain.WATER:
                    if self.rng.random() < probability:
                        # Small side pool or channel
                        for dx, dy in [(1,0), (-1,0), (0,1), (0,-1)]:
                            nx, ny = x + dx, y + dy
                            if local_map.in_bounds(nx, ny):
                                if self.rng.random() < 0.7:
                                    local_map.tiles[ny][nx].terrain = LocalTerrain.WATER
                                elif self.rng.random() < 0.5:
                                    local_map.tiles[ny][nx].terrain = LocalTerrain.GRAVEL_BAR