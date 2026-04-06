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
        # Use floats for smooth sub-tile tracking
        fx, fy = float(cx), float(cy)

        for step in range(max(width, height) * 2):
            # Add natural meandering
            twist_amount = self.rng.uniform(-twist, twist)
            dx = direction_bias[0] * 1.2 + twist_amount
            dy = direction_bias[1] * 1.2 + self.rng.uniform(-twist * 0.8, twist * 0.8)

            # Walk from current position to next, filling every tile along the way
            nx, ny = fx + dx, fy + dy
            # Clamp to bounds
            nx = max(8.0, min(width - 9.0, nx))
            ny = max(8.0, min(height - 9.0, ny))

            # Bresenham-style interpolation so there are no gaps
            ix0, iy0 = int(fx), int(fy)
            ix1, iy1 = int(nx), int(ny)
            steps_x = abs(ix1 - ix0)
            steps_y = abs(iy1 - iy0)
            n_steps = max(steps_x, steps_y, 1)
            for i in range(n_steps + 1):
                t = i / n_steps
                px = int(fx + (nx - fx) * t)
                py = int(fy + (ny - fy) * t)
                px = max(8, min(width - 9, px))
                py = max(8, min(height - 9, py))
                if (px, py) not in points:
                    points.append((px, py))
                # Paint water at every interpolated tile
                if local_map.in_bounds(px, py):
                    local_map.tiles[py][px].terrain = LocalTerrain.WATER

            fx, fy = nx, ny
            cx, cy = int(fx), int(fy)

            # Occasionally change main direction slightly
            if self.rng.random() < 0.08:
                direction_bias = (direction_bias[0] + self.rng.uniform(-0.5, 0.5),
                                  direction_bias[1] + self.rng.uniform(-0.5, 0.5))

            # Gravel bars on inside bends (higher chance on tighter turns)
            if local_map.in_bounds(cx, cy):
                if self.rng.random() < 0.75:
                    for ddx, ddy in [(-1,0), (1,0), (0,-1), (0,1)]:
                        gx, gy = cx + ddx, cy + ddy
                        if local_map.in_bounds(gx, gy):
                            if local_map.tiles[gy][gx].terrain != LocalTerrain.WATER:
                                local_map.tiles[gy][gx].terrain = LocalTerrain.GRAVEL_BAR
                                # Boost gold on gravel bars
                                local_map.tiles[gy][gx].gold_grade = max(
                                    local_map.tiles[gy][gx].gold_grade,
                                    0.35 + self.rng.random() * 0.45
                                )

                # Occasional bedrock exposure near stream
                if self.rng.random() < 0.12:
                    for ddx, ddy in [(-1,-1), (-1,1), (1,-1), (1,1)]:
                        bx, by = cx + ddx, cy + ddy
                        if local_map.in_bounds(bx, by):
                            if local_map.tiles[by][bx].terrain not in (LocalTerrain.WATER, LocalTerrain.GRAVEL_BAR):
                                local_map.tiles[by][bx].terrain = LocalTerrain.BEDROCK
                                local_map.tiles[by][bx].gold_grade = min(1.0, 0.6 + self.rng.random() * 0.4)

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

    def place_beaver_dams(self, local_map, year: int = 1849):
        """Place beaver dams across narrow stream sections.

        Scans for horizontal rows where WATER tiles form a narrow crossing
        (1-3 tiles wide with non-water banks on both sides). Places up to
        2 dams per map with at least 60 tiles spacing between them.
        """
        from src.wildlife_manager import _era_wildlife_mult

        dam_prob = 0.15 * _era_wildlife_mult("beaver", year)
        max_dams = 2
        min_spacing = 60

        # Collect candidate dam sites: look for narrow stream crossings.
        # A candidate is a horizontal run of 1-3 WATER tiles in a row where
        # the tiles immediately left and right of the run are non-water (banks).
        candidates: List[Tuple[int, int, int]] = []  # (cx, cy, width_of_crossing)

        margin = 15
        for y in range(margin, local_map.height - margin):
            x = margin
            while x < local_map.width - margin:
                if local_map.tiles[y][x].terrain == LocalTerrain.WATER:
                    # Measure horizontal run of water
                    run_start = x
                    run_len = 0
                    while (x < local_map.width - margin
                           and local_map.tiles[y][x].terrain == LocalTerrain.WATER):
                        run_len += 1
                        x += 1
                    # Narrow enough for a dam (1-3 tiles)
                    if 1 <= run_len <= 3:
                        # Check banks: tile before run and tile after run must be non-water
                        left_x = run_start - 1
                        right_x = run_start + run_len
                        if (local_map.in_bounds(left_x, y)
                                and local_map.in_bounds(right_x, y)):
                            left_t = local_map.tiles[y][left_x].terrain
                            right_t = local_map.tiles[y][right_x].terrain
                            if (left_t != LocalTerrain.WATER
                                    and left_t != LocalTerrain.DEEP_WATER
                                    and right_t != LocalTerrain.WATER
                                    and right_t != LocalTerrain.DEEP_WATER):
                                cx = run_start + run_len // 2
                                candidates.append((cx, y, run_len))
                else:
                    x += 1

        # Shuffle candidates deterministically and pick dam sites
        self.rng.shuffle(candidates)

        placed: List[Tuple[int, int]] = []
        for cx, cy, crossing_w in candidates:
            if len(placed) >= max_dams:
                break

            # Check spacing from already-placed dams
            too_close = False
            for px, py in placed:
                if abs(cx - px) + abs(cy - py) < min_spacing:
                    too_close = True
                    break
            if too_close:
                continue

            # Roll probability
            if self.rng.random() > dam_prob:
                continue

            # ── Place the dam ────────────────────────────────────────────
            # Set 2-3 tiles across the stream to BEAVER_DAM
            run_start_x = cx - crossing_w // 2
            dam_width = max(2, crossing_w)
            for dx in range(dam_width):
                bx = run_start_x + dx
                if local_map.in_bounds(bx, cy):
                    local_map.tiles[cy][bx].terrain = LocalTerrain.BEAVER_DAM

            # Upstream (lower y = north/upstream): set 3-5 WATER tiles to BEAVER_POND
            pond_count = self.rng.randint(3, 5)
            placed_pond = 0
            for dy in range(1, pond_count + 3):
                uy = cy - dy
                if uy < 0:
                    break
                for dx in range(-1, crossing_w + 1):
                    px = run_start_x + dx
                    if (local_map.in_bounds(px, uy)
                            and local_map.tiles[uy][px].terrain == LocalTerrain.WATER
                            and placed_pond < pond_count):
                        local_map.tiles[uy][px].terrain = LocalTerrain.BEAVER_POND
                        placed_pond += 1

            # Set 1-2 adjacent bank tiles to ASPEN (beaver chew marks)
            aspen_count = self.rng.randint(1, 2)
            placed_aspen = 0
            for dx, dy in [(-1, 0), (crossing_w, 0), (-1, -1), (crossing_w, -1),
                           (-1, 1), (crossing_w, 1)]:
                ax = run_start_x + dx
                ay = cy + dy
                if placed_aspen >= aspen_count:
                    break
                if local_map.in_bounds(ax, ay):
                    t = local_map.tiles[ay][ax].terrain
                    if t in (LocalTerrain.GRASS, LocalTerrain.GROUND):
                        local_map.tiles[ay][ax].terrain = LocalTerrain.ASPEN
                        placed_aspen += 1

            # Record the dam center
            local_map.beaver_dams.append((cx, cy))
            placed.append((cx, cy))