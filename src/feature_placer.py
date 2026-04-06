"""
src/feature_placer.py

Places special placer gold features on local maps based on region and geology.
Creates believable "hot spots" where gold concentrates in discoverable patterns:
  - Pay streaks: connected runs of rich ground along/near streams
  - Inside bends: gravel bars on the inside of stream curves
  - Bedrock traps: exposed bedrock that catches gold in crevices
  - Boulder traps: large rocks that create eddies and trap gold
  - Black sand: heavy mineral deposits that indicate gold presence
"""

import random
from typing import List, Tuple

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
    Gold follows geological rules:
      - Concentrates on inside bends of streams
      - Settles behind boulders and in bedrock crevices
      - Forms pay streaks: connected runs of rich ground
      - Grades from rich to poor away from the streak center
    """

    def __init__(self, rng: random.Random):
        self.rng = rng

    def place_features(self, local_map, region_name: str, gold_bias: float):
        """Place appropriate placer features based on region."""
        # Step 1: Find all water tiles and identify stream geometry
        water_tiles = self._find_water_tiles(local_map)
        bends = self._find_inside_bends(local_map, water_tiles)

        # Step 2: Place pay streaks along streams (the main discoverable pattern)
        num_streaks = max(1, int(3 * gold_bias))
        self._place_pay_streaks(local_map, water_tiles, bends,
                                num_streaks, gold_bias, region_name)

        # Step 3: Enrich inside bends that weren't part of a pay streak
        self._enrich_bends(local_map, bends, gold_bias)

        # Step 4: Bedrock traps near water
        self._place_bedrock_traps(local_map, water_tiles, gold_bias)

        # Step 5: Boulder traps
        self._place_boulder_traps(local_map, water_tiles, gold_bias)

        # Step 6: Enhance all stream-adjacent gravel (baseline)
        self._enhance_stream_gravel(local_map, water_tiles, gold_bias)

    # ── Water geometry ────────────────────────────────────────────────

    def _find_water_tiles(self, local_map) -> List[Tuple[int, int]]:
        """Find all water tiles on the map."""
        water = []
        for y in range(local_map.height):
            for x in range(local_map.width):
                if local_map.tiles[y][x].terrain == LocalTerrain.WATER:
                    water.append((x, y))
        return water

    def _find_inside_bends(self, local_map,
                            water_tiles: List[Tuple[int, int]]
                            ) -> List[Tuple[int, int, float]]:
        """Find tiles on inside bends of streams.
        Returns (x, y, bend_score) where bend_score 0-1 indicates
        how tight the bend is (tighter = more gold)."""
        water_set = set(water_tiles)
        bends = []

        for wx, wy in water_tiles:
            # Count water neighbors in a 5x5 area
            water_nearby = 0
            water_dirs = set()
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    if dx == 0 and dy == 0:
                        continue
                    if (wx + dx, wy + dy) in water_set:
                        water_nearby += 1
                        # Track which quadrants have water
                        if dx < 0:
                            water_dirs.add("W")
                        if dx > 0:
                            water_dirs.add("E")
                        if dy < 0:
                            water_dirs.add("N")
                        if dy > 0:
                            water_dirs.add("S")

            # A bend has water on 2+ non-opposing sides
            is_bend = (len(water_dirs) >= 2 and
                       not (water_dirs == {"N", "S"} or
                            water_dirs == {"E", "W"}))

            if is_bend:
                # Find inside of bend: non-water tile closest to
                # the center of curvature
                bend_score = min(1.0, water_nearby / 12.0)
                for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0),
                                (1, 1), (1, -1), (-1, 1), (-1, -1)]:
                    ix, iy = wx + dx, wy + dy
                    if (local_map.in_bounds(ix, iy) and
                            (ix, iy) not in water_set):
                        tile = local_map.tiles[iy][ix]
                        if tile.terrain not in (LocalTerrain.ROCK,
                                                 LocalTerrain.WATER):
                            bends.append((ix, iy, bend_score))
        return bends

    # ── Pay streaks ───────────────────────────────────────────────────

    def _place_pay_streaks(self, local_map, water_tiles, bends,
                            num_streaks, gold_bias, region_name):
        """Place connected pay streaks along streams.
        A pay streak is a run of 8-25 rich tiles that follows the
        stream course. Gold grades from bonanza at center to color
        at edges. This is the main pattern players discover."""

        if not water_tiles:
            return

        # Pick starting points: prefer bends, fall back to random water-adj
        starts = []
        if bends:
            scored = sorted(bends, key=lambda b: b[2], reverse=True)
            starts = [(b[0], b[1]) for b in scored[:num_streaks * 2]]
        if len(starts) < num_streaks:
            # Fill from water-adjacent tiles
            for _ in range(num_streaks * 3):
                wx, wy = self.rng.choice(water_tiles)
                for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    nx, ny = wx + dx, wy + dy
                    if (local_map.in_bounds(nx, ny) and
                            local_map.tiles[ny][nx].terrain != LocalTerrain.WATER):
                        starts.append((nx, ny))
                        break

        self.rng.shuffle(starts)
        water_set = set(water_tiles)
        placed_streaks = 0

        for sx, sy in starts:
            if placed_streaks >= num_streaks:
                break

            # Walk along the stream to create a connected pay streak
            streak_len = self.rng.randint(8, 25)
            streak_tiles = [(sx, sy)]
            cx, cy = sx, sy

            # Determine streak richness based on region
            if "Sierra" in region_name or "California" in region_name:
                center_grade = 0.65 + self.rng.random() * 0.35  # 0.65-1.0
            elif "Appalachian" in region_name:
                center_grade = 0.40 + self.rng.random() * 0.35  # 0.40-0.75
            elif "Great Plains" in region_name:
                center_grade = 0.15 + self.rng.random() * 0.20  # 0.15-0.35
            else:
                center_grade = 0.50 + self.rng.random() * 0.40  # 0.50-0.90

            for _ in range(streak_len):
                # Find next tile: prefer following water course
                candidates = []
                for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0),
                                (1, 1), (1, -1), (-1, 1), (-1, -1)]:
                    nx, ny = cx + dx, cy + dy
                    if not local_map.in_bounds(nx, ny):
                        continue
                    if (nx, ny) in set(streak_tiles):
                        continue
                    tile = local_map.tiles[ny][nx]
                    if tile.terrain == LocalTerrain.ROCK:
                        continue
                    # Prefer tiles adjacent to water
                    near_water = any(
                        (nx + ddx, ny + ddy) in water_set
                        for ddx, ddy in [(0, 1), (0, -1), (1, 0), (-1, 0)]
                    )
                    weight = 5 if near_water else 1
                    # Prefer gravel bars
                    if tile.terrain == LocalTerrain.GRAVEL_BAR:
                        weight *= 3
                    candidates.extend([(nx, ny)] * weight)

                if not candidates:
                    break
                cx, cy = self.rng.choice(candidates)
                streak_tiles.append((cx, cy))

            if len(streak_tiles) < 4:
                continue  # too short, skip

            # Apply gold grades: richest at center, tapering to edges
            mid = len(streak_tiles) // 2
            for i, (tx, ty) in enumerate(streak_tiles):
                tile = local_map.tiles[ty][tx]

                # Distance from center of streak (0.0 = center, 1.0 = edge)
                dist = abs(i - mid) / max(1, mid)
                # Grade tapers from center_grade to ~40% of it at edges
                grade = center_grade * (1.0 - dist * 0.6)
                # Add small random variation
                grade += self.rng.uniform(-0.05, 0.05)
                grade = max(0.10, min(1.0, grade))

                # Set terrain to gravel bar if it's plain ground
                if tile.terrain in (LocalTerrain.GRASS, LocalTerrain.GROUND,
                                     LocalTerrain.DIRT):
                    tile.terrain = LocalTerrain.GRAVEL_BAR
                tile.gold_grade = max(tile.gold_grade, grade)

            # Halo: tiles adjacent to the streak get moderate gold
            streak_set = set(streak_tiles)
            for tx, ty in streak_tiles:
                for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    hx, hy = tx + dx, ty + dy
                    if not local_map.in_bounds(hx, hy):
                        continue
                    if (hx, hy) in streak_set:
                        continue
                    htile = local_map.tiles[hy][hx]
                    if htile.terrain in (LocalTerrain.WATER, LocalTerrain.ROCK):
                        continue
                    halo_grade = center_grade * self.rng.uniform(0.15, 0.35)
                    htile.gold_grade = max(htile.gold_grade, halo_grade)
                    if htile.terrain in (LocalTerrain.GRASS, LocalTerrain.GROUND,
                                          LocalTerrain.DIRT):
                        htile.terrain = LocalTerrain.GRAVEL_BAR

            placed_streaks += 1

    # ── Inside bends ──────────────────────────────────────────────────

    def _enrich_bends(self, local_map, bends, gold_bias):
        """Enrich inside bends that weren't already in a pay streak."""
        for bx, by, score in bends:
            tile = local_map.tiles[by][bx]
            # Only enrich if not already rich from a streak
            if tile.gold_grade >= 0.45:
                continue
            bend_grade = (0.35 + score * 0.45) * gold_bias
            bend_grade = min(1.0, bend_grade + self.rng.uniform(-0.05, 0.10))
            tile.gold_grade = max(tile.gold_grade, bend_grade)
            if tile.terrain in (LocalTerrain.GRASS, LocalTerrain.GROUND,
                                 LocalTerrain.DIRT):
                tile.terrain = LocalTerrain.GRAVEL_BAR

    # ── Bedrock traps ─────────────────────────────────────────────────

    def _place_bedrock_traps(self, local_map, water_tiles, gold_bias):
        """Place bedrock exposures near streams that trap gold in crevices.
        Bedrock always has good gold — that's the whole point."""
        water_set = set(water_tiles)
        num = max(2, int(8 * gold_bias))

        placed = 0
        attempts = 0
        while placed < num and attempts < num * 10:
            attempts += 1
            if not water_tiles:
                break
            wx, wy = self.rng.choice(water_tiles)
            # 1-3 tiles from water
            dist = self.rng.randint(1, 3)
            dx = self.rng.choice([-1, 0, 1])
            dy = self.rng.choice([-1, 0, 1])
            bx, by = wx + dx * dist, wy + dy * dist
            if not local_map.in_bounds(bx, by):
                continue
            tile = local_map.tiles[by][bx]
            if tile.terrain in (LocalTerrain.WATER, LocalTerrain.ROCK):
                continue

            tile.terrain = LocalTerrain.BEDROCK
            # Bedrock traps are consistently rich — that's why prospectors
            # look for them. Grade 0.50-1.0
            tile.gold_grade = max(tile.gold_grade,
                                   0.50 + self.rng.random() * 0.50)

            # Adjacent bedrock tiles (bedrock outcrops are 2-4 tiles)
            for ddx, ddy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                if self.rng.random() < 0.5:
                    nx, ny = bx + ddx, by + ddy
                    if local_map.in_bounds(nx, ny):
                        ntile = local_map.tiles[ny][nx]
                        if ntile.terrain not in (LocalTerrain.WATER,
                                                   LocalTerrain.ROCK):
                            ntile.terrain = LocalTerrain.BEDROCK
                            ntile.gold_grade = max(
                                ntile.gold_grade,
                                0.40 + self.rng.random() * 0.40)
            placed += 1

    # ── Boulder traps ─────────────────────────────────────────────────

    def _place_boulder_traps(self, local_map, water_tiles, gold_bias):
        """Boulders in/near streams create eddies that trap gold downstream."""
        water_set = set(water_tiles)
        num = max(1, int(5 * gold_bias))

        for _ in range(num):
            if not water_tiles:
                break
            wx, wy = self.rng.choice(water_tiles)
            # Gold settles just downstream of boulders
            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                tx, ty = wx + dx, wy + dy
                if not local_map.in_bounds(tx, ty):
                    continue
                tile = local_map.tiles[ty][tx]
                if tile.terrain in (LocalTerrain.WATER, LocalTerrain.ROCK):
                    continue
                tile.gold_grade = max(tile.gold_grade,
                                       0.40 + self.rng.random() * 0.40)
                if tile.terrain in (LocalTerrain.GRASS, LocalTerrain.GROUND,
                                     LocalTerrain.DIRT):
                    tile.terrain = LocalTerrain.GRAVEL_BAR
                break

    # ── Stream-adjacent gravel baseline ───────────────────────────────

    def _enhance_stream_gravel(self, local_map, water_tiles, gold_bias):
        """All gravel bars adjacent to water get at least some gold.
        This ensures players can always find SOMETHING near water,
        even if it's just trace/color. The good stuff is in pay streaks."""
        water_set = set(water_tiles)
        for wx, wy in water_tiles:
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                gx, gy = wx + dx, wy + dy
                if not local_map.in_bounds(gx, gy):
                    continue
                tile = local_map.tiles[gy][gx]
                if tile.terrain == LocalTerrain.WATER:
                    continue
                # Convert to gravel bar if plain ground next to water
                if tile.terrain in (LocalTerrain.GRASS, LocalTerrain.GROUND,
                                     LocalTerrain.DIRT):
                    tile.terrain = LocalTerrain.GRAVEL_BAR
                # Baseline gold for stream-adjacent gravel
                if tile.terrain == LocalTerrain.GRAVEL_BAR:
                    if tile.gold_grade < 0.15:
                        tile.gold_grade = max(
                            tile.gold_grade,
                            0.10 + self.rng.random() * 0.20 * gold_bias)

    # Legacy compatibility
    def enhance_streams(self, local_map):
        """Called by stream_generator after stream placement."""
        water = self._find_water_tiles(local_map)
        self._enhance_stream_gravel(local_map, water, 0.5)
