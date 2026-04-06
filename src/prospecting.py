"""
Placer gold extraction loop.
Pan → assess → sample → work ground → clean up → recover gold.
"""

import random
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.player import Player
    from src.local_map import LocalMap


@dataclass
class PanResult:
    success: bool
    gold_oz: float          # troy ounces recovered
    grade_seen: str         # what player sees: "barren"/"trace"/"color"/"rich"/"bonanza"
    time_minutes: int
    xp_placer: float
    xp_geology: float
    message: str


# Grade thresholds (gold_grade tile value 0–1)
GRADE_LABELS = [
    (0.0,  0.05, "barren"),
    (0.05, 0.20, "trace"),
    (0.20, 0.45, "color"),
    (0.45, 0.75, "rich"),
    (0.75, 1.00, "bonanza"),
]

# Oz per successful pan by grade
GRADE_OZ = {
    "barren":  0.0,
    "trace":   0.001,    # $0.02 — barely anything
    "color":   0.005,    # $0.10 per pan — worth working
    "rich":    0.020,    # $0.41 per pan — good ground
    "bonanza": 0.080,    # $1.65 per pan — exceptional
}

FINENESS = 0.900   # California gold ~900 fine
GOLD_PRICE_PER_OZ = 20.67   # 1849 fixed price


def tile_grade_label(gold_grade: float) -> str:
    for lo, hi, label in GRADE_LABELS:
        if lo <= gold_grade < hi:
            return label
    return "bonanza"


def _skill_roll(player: "Player", skill: str, difficulty: int) -> bool:
    """d20 + floor(skill/2) + floor(attr/3) vs difficulty."""
    import random
    governing = {"placer": "wisdom", "geology": "intelligence",
                 "survival": "constitution", "fishing": "wisdom",
                 "cooking": "wisdom"}.get(skill, "wisdom")
    skill_val = player.skills.get(skill, 0)
    attr_val  = player.attributes.get(governing, 10)
    roll = random.randint(1, 20) + skill_val // 2 + attr_val // 3
    return roll >= difficulty


def test_pan(player: "Player", local_map: "LocalMap") -> PanResult:
    """
    Quick 5-minute test pan — reveals gold grade of current spot
    without extracting gold. Core prospecting mechanic: you sample
    before committing to work an area.
    """
    from src.local_map import LocalTerrain
    tile = local_map.tile_at(player.local_x, player.local_y)

    has_pan = any("pan" in getattr(item, 'tool_tags', []) for item in player.inventory)
    if not has_pan:
        return PanResult(
            success=False, gold_oz=0, grade_seen="barren",
            time_minutes=2, xp_placer=0, xp_geology=0,
            message="You need a gold pan to test this ground.",
        )

    # Assign gold grade if not yet set (tiles missed by feature placer)
    if tile.gold_grade == 0.0:
        rng = random.Random(local_map.seed + player.local_x * 100 + player.local_y)
        if tile.terrain == LocalTerrain.GRAVEL_BAR:
            # Gravel bars should always have at least trace gold
            tile.gold_grade = 0.08 + rng.betavariate(2.0, 3.0) * 0.50
        elif tile.terrain == LocalTerrain.BEDROCK:
            # Bedrock traps gold — consistently richer
            tile.gold_grade = 0.20 + rng.betavariate(2.5, 2.5) * 0.60
        elif tile.terrain in (LocalTerrain.WATER, LocalTerrain.MUD,
                               LocalTerrain.SAND):
            tile.gold_grade = rng.betavariate(1.0, 4.0) * 0.30
        else:
            # Dirt, grass — very unlikely but not impossible
            tile.gold_grade = rng.betavariate(0.5, 6.0) * 0.15

    grade_label = tile_grade_label(tile.gold_grade)
    placer_skill = player.skills.get("placer", 0)
    geo_skill = player.skills.get("geology", 0)

    # What the player learns depends on combined skill
    total_skill = placer_skill + geo_skill
    if total_skill >= 12:
        # Expert: exact grade + estimated oz/pan
        base_oz = GRADE_OZ.get(grade_label, 0)
        grade_seen = grade_label
        if base_oz > 0:
            est = base_oz * random.uniform(0.8, 1.2)
            msg = (f"Test pan: {grade_label}. Estimated ~{est:.3f} oz/pan "
                   f"(~${est * GOLD_PRICE_PER_OZ * FINENESS:.2f}). "
                   f"{'Worth setting up here.' if grade_label in ('color', 'rich', 'bonanza') else 'Marginal ground.'}")
        else:
            msg = "Test pan: barren. No color at all. Move on."
    elif total_skill >= 8:
        # Good: accurate grade label
        grade_seen = grade_label
        msg_map = {
            "barren": "Test pan: nothing. Dead ground.",
            "trace": "Test pan: faintest hint of color. Barely worth it.",
            "color": "Test pan: definite color. There's gold here.",
            "rich": "Test pan: good color! Fat flakes in the black sand. Promising.",
            "bonanza": "Test pan: heavy gold settles immediately. This is exceptional ground.",
        }
        msg = msg_map.get(grade_label, "Test pan complete.")
    elif total_skill >= 4:
        # Moderate: rough classification
        if grade_label in ("barren", "trace"):
            grade_seen = "barren" if random.random() < 0.7 else "trace"
            msg = "Test pan: looks pretty lean. Maybe a trace, maybe nothing."
        elif grade_label in ("color", "rich"):
            grade_seen = "color"
            msg = "Test pan: there's color. How much, hard to say."
        else:
            grade_seen = "rich"
            msg = "Test pan: definitely gold here. Lots of it."
    else:
        # Novice: binary — gold or no gold
        if grade_label == "barren":
            grade_seen = "barren"
            msg = "You swirl the dirt around. You have no idea what you're looking at. Seems empty."
        else:
            grade_seen = "color"
            msg = "You see... something shiny? Could be gold. Could be mica. You're not sure."

    tile.mineral_hint = grade_seen

    return PanResult(
        success=True, gold_oz=0.0, grade_seen=grade_seen,
        time_minutes=5, xp_placer=2.0, xp_geology=3.0,
        message=msg,
    )


def assess_ground(player: "Player", local_map: "LocalMap",
                  x: int, y: int) -> str:
    """
    Read geological indicators at a tile. Free action — just looking.
    Higher geology skill reveals more useful information.
    """
    from src.local_map import LocalTerrain
    tile = local_map.tile_at(x, y)
    geo_skill = player.skills.get("geology", 0)

    observations = []

    # Basic terrain observation (anyone can see)
    terrain_obs = {
        LocalTerrain.GRAVEL_BAR: "Gravel bar — loose alluvial material.",
        LocalTerrain.BEDROCK: "Exposed bedrock — potential gold trap.",
        LocalTerrain.WATER: "Flowing water.",
        LocalTerrain.MUD: "Wet mud — recent water activity.",
        LocalTerrain.SAND: "Sandy ground.",
    }
    t_obs = terrain_obs.get(tile.terrain)
    if t_obs:
        observations.append(t_obs)

    # Skill-gated observations
    if geo_skill >= 1:
        # Check nearby water (inside bend indicator)
        has_water_adj = False
        water_count = 0
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                nx, ny = x + dx, y + dy
                if local_map.in_bounds(nx, ny):
                    if local_map.tile_at(nx, ny).terrain == LocalTerrain.WATER:
                        water_count += 1
                        has_water_adj = True
        if has_water_adj:
            observations.append("Near running water — placer deposits possible.")
        if water_count >= 3:
            observations.append("Inside bend of creek — gold concentrates here.")

    if geo_skill >= 3:
        # Check for black sand (high gold_grade nearby)
        rich_nearby = 0
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                nx, ny = x + dx, y + dy
                if local_map.in_bounds(nx, ny):
                    if local_map.tile_at(nx, ny).gold_grade > 0.3:
                        rich_nearby += 1
        if rich_nearby >= 2:
            observations.append("Heavy black sand in the area — good sign.")

    if geo_skill >= 5:
        # Read the gold grade directly
        if tile.gold_grade > 0:
            gl = tile_grade_label(tile.gold_grade)
            observations.append(f"Your experienced eye reads this as: {gl}.")
        elif tile.mineral_hint:
            observations.append(f"Previously tested: {tile.mineral_hint}.")

    if geo_skill >= 7:
        # Identify pay streaks
        if tile.gold_grade >= 0.45:
            observations.append("PAY STREAK — this is working ground. Set up here.")
        # Identify bedrock crevices
        if tile.terrain == LocalTerrain.BEDROCK and tile.gold_grade > 0.3:
            observations.append("Bedrock crevice — gold trapped in the cracks. Clean it out.")

    if not observations:
        observations.append("Nothing stands out about this ground.")

    return " ".join(observations)


_SEASON_GOLD_MULT = {
    "spring": 1.3,   # spring runoff washes new gold down from mountains
    "summer": 0.8,   # low water, less material moving
    "fall":   1.0,   # normal
    "winter": 0.6,   # frozen ground, cold hands, less efficient
}


def pan_for_gold(player: "Player", local_map: "LocalMap",
                 season: str = "summer",
                 partner_count: int = 0) -> PanResult:
    """
    One panning cycle at the player's current tile.
    Takes ~20 minutes. Uses Placer skill.
    """
    from src.local_map import LocalTerrain
    tile = local_map.tile_at(player.local_x, player.local_y)

    # Check if tile is valid panning ground
    if tile.terrain not in (LocalTerrain.GRAVEL_BAR, LocalTerrain.BEDROCK,
                             LocalTerrain.WATER):
        return PanResult(
            success=False, gold_oz=0, grade_seen="barren",
            time_minutes=5, xp_placer=0.5, xp_geology=0,
            message="This ground isn't worth panning — find a gravel bar or bedrock exposure.",
        )

    # Check for pan in inventory
    has_pan = any("pan" in getattr(item, 'tool_tags', []) for item in player.inventory)
    if not has_pan:
        return PanResult(
            success=False, gold_oz=0, grade_seen="barren",
            time_minutes=2, xp_placer=0, xp_geology=0,
            message="You need a gold pan.",
        )

    # Assign gold grade to tile if not yet set (missed by feature placer)
    if tile.gold_grade == 0.0:
        rng = random.Random(local_map.seed + player.local_x * 100 + player.local_y)
        if tile.terrain == LocalTerrain.GRAVEL_BAR:
            tile.gold_grade = 0.08 + rng.betavariate(2.0, 3.0) * 0.50
        elif tile.terrain == LocalTerrain.BEDROCK:
            tile.gold_grade = 0.20 + rng.betavariate(2.5, 2.5) * 0.60
        elif tile.terrain in (LocalTerrain.WATER, LocalTerrain.MUD,
                               LocalTerrain.SAND):
            tile.gold_grade = rng.betavariate(1.0, 4.0) * 0.30
        else:
            tile.gold_grade = rng.betavariate(0.5, 6.0) * 0.15
        tile.mineral_hint = tile_grade_label(tile.gold_grade)

    grade_label = tile_grade_label(tile.gold_grade)

    # Skill check: higher skill = better read of what you're seeing + more efficient
    placer_skill = player.skills.get("placer", 0)
    geo_skill    = player.skills.get("geology", 0)
    time_cost    = max(10, 20 - placer_skill)   # skill reduces time per pan

    # Success roll: difficulty scales with how poor the ground is
    difficulty = {"barren": 5, "trace": 8, "color": 10, "rich": 8, "bonanza": 6}[grade_label]
    success = _skill_roll(player, "placer", difficulty)

    gold_recovered = 0.0
    if success and grade_label != "barren":
        base_oz = GRADE_OZ[grade_label]
        # Skill multiplier: up to 2× at skill 10
        skill_mult = 1.0 + placer_skill * 0.1
        # Seasonal variation — spring runoff best, winter worst
        season_mult = _SEASON_GOLD_MULT.get(season, 1.0)
        # Partnership bonus — more hands = more throughput
        partner_mult = 1.0 + partner_count * 0.4  # each partner adds 40%
        # Random variation ±30%
        variation = random.uniform(0.7, 1.3)
        gold_recovered = base_oz * skill_mult * season_mult * partner_mult * variation
        # Deplete tile slightly
        tile.gold_grade = max(0.0, tile.gold_grade - 0.005)

    # What the player sees depends on skill
    if placer_skill >= 4:
        grade_seen = grade_label   # accurate read
    elif placer_skill >= 2:
        # May misread trace/color
        if grade_label == "trace" and random.random() < 0.3:
            grade_seen = "color"
        elif grade_label == "color" and random.random() < 0.3:
            grade_seen = "trace"
        else:
            grade_seen = grade_label
    else:
        # Novice: can only tell barren vs not-barren
        grade_seen = "barren" if grade_label == "barren" else "color"

    # XP
    xp_placer  = 5.0 + (tile.gold_grade * 10.0)
    xp_geology = 2.0 if geo_skill < 6 else 1.0

    # Build message
    value = gold_recovered * GOLD_PRICE_PER_OZ * FINENESS
    if not success or grade_label == "barren":
        msg = _barren_message(placer_skill, grade_label)
    else:
        msg = _success_message(gold_recovered, value, grade_seen, placer_skill)

    return PanResult(
        success=success and gold_recovered > 0,
        gold_oz=gold_recovered,
        grade_seen=grade_seen,
        time_minutes=time_cost,
        xp_placer=xp_placer,
        xp_geology=xp_geology,
        message=msg,
    )


def _barren_message(skill: int, actual_grade: str) -> str:
    if actual_grade == "barren":
        msgs = [
            "You swirl the pan and tip it slowly. Nothing. Just gravel and grit.",
            "Black sand settles at the bottom. You stare at it. No color. Not a speck.",
            "Pan after pan of cold river water. Your fingers are numb. Nothing.",
            "The pan comes up empty. This ground is dead.",
            "You scrape a crevice clean and wash it. Sand, pebbles. No gold.",
        ]
    else:
        msgs = [
            "You lose what little was there — washed over the rim. Careful next time.",
            "Empty pan. The gold's here somewhere, but you missed it this round.",
            "A clumsy wash. If there was color, it went over the edge.",
        ]
    return random.choice(msgs)


def _success_message(oz: float, value: float, grade: str, skill: int) -> str:
    if grade == "bonanza":
        msgs = [
            f"Your hands are shaking. The bottom of the pan is YELLOW. "
            f"Coarse flakes, a small picker — {oz:.3f} oz. ${value:.2f}. Lord almighty.",
            f"You tip the pan and your breath catches. Heavy gold, thick as paint. "
            f"{oz:.3f} oz recovered — ${value:.2f}. This is the real thing.",
        ]
        return random.choice(msgs)
    if grade == "rich":
        msgs = [
            f"Good color! Fat flakes sitting in the black sand. "
            f"{oz:.3f} oz (${value:.2f}). This ground pays.",
            f"The crescent fills with bright yellow. Solid pan. "
            f"{oz:.3f} oz — ${value:.2f}. Worth setting up here.",
        ]
        return random.choice(msgs)
    if grade == "color":
        msgs = [
            f"You see it — fine gold, catching the light in the black sand. "
            f"{oz:.3f} oz (${value:.2f}). There's gold here.",
            f"Color! Tiny flakes, but they're real. {oz:.3f} oz — ${value:.2f}. "
            f"Keep working this spot.",
            f"A dusting of fine flour gold in the pan. Not much, but it's honest color. "
            f"{oz:.3f} oz (${value:.2f}).",
        ]
        return random.choice(msgs)
    # trace
    msgs = [
        f"You almost miss it — the faintest gleam in the sand. "
        f"{oz:.4f} oz (${value:.2f}). Barely a trace, but it's gold.",
        f"Squinting at the bottom of the pan... a few specks. Maybe. "
        f"{oz:.4f} oz — ${value:.2f}. Lean ground.",
    ]
    return random.choice(msgs)


def depletion_message(old_grade: float, new_grade: float) -> str:
    """Return a message about how the ground is changing, or empty string."""
    if old_grade <= 0.05:
        return ""
    drop = old_grade - new_grade
    ratio = new_grade / max(old_grade, 0.001)
    if ratio < 0.3:
        return "The color's nearly gone. This spot is played out."
    if ratio < 0.6:
        return "The pans are thinning out. Not as much color as before."
    if ratio < 0.85:
        return "A little leaner than your first pans here."
    return ""


# Old assess_ground (2-arg) kept as backward-compat wrapper
def _assess_ground_compat(player: "Player", local_map: "LocalMap") -> str:
    return assess_ground(player, local_map, player.local_x, player.local_y)
