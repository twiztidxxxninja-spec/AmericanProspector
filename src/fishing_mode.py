"""
src/fishing_mode.py

Fishing mode — pick a spot, choose method, choose bait, fish.
Seasonal runs, spot degradation, species variety.

Enter from [A] actions → Fish, or type "fish".
"""

import tcod.event
import random
from typing import TYPE_CHECKING, Optional, List

if TYPE_CHECKING:
    from src.engine import Engine


# Bait items that improve catch chance
BAIT_ITEMS = {
    "worm":          0.15,   # dug from ground, common
    "insect":        0.10,   # caught from air
    "fresh_venison": 0.20,   # meat scraps
    "fresh_fish":    0.10,   # cut bait
    "wild_berries":  0.05,   # some fish like fruit
}

# Methods available to player
METHODS = [
    ("pole",  "Fishing pole",     "Sit and wait. Best all-around method."),
    ("spear", "Spear fishing",    "Fast but requires agility. Best in shallows."),
    ("hand",  "Bare hands",       "Desperation. Low chance but no gear needed."),
    ("net",   "Net",              "Wide catch. Requires a net or woven basket."),
]


def enter_fishing_mode(engine: "Engine", console, ctx) -> None:
    """Full fishing mode UI."""
    from src.fish_system import FishingMechanics, FISH_DB, FishSpecies
    from src.items import make_item
    from src.menus import draw_box, pick_from_list

    WHITE  = (255, 255, 255)
    YELLOW = (255, 255, 0)
    CYAN   = (0, 200, 200)
    GREEN  = (0, 200, 0)
    GREY   = (140, 140, 140)
    BLUE   = (80, 140, 220)
    RED    = (255, 80, 80)
    BG     = (10, 15, 30)

    player = engine.player
    lmap = engine.current_local
    rng = random.Random()

    region = lmap._region_name if lmap else "California"
    season = engine.time.season
    period = engine.time.period

    # Check for fishing gear
    has_pole = any("fish" in getattr(i, "tool_tags", []) for i in player.inventory)
    has_net = any(i.id in ("net", "fishing_net") for i in player.inventory)

    # Available methods
    available = [("hand", "Bare hands", "No gear needed. Low chance.")]
    if has_pole:
        available.insert(0, ("pole", "Fishing pole & line", "Best all-around. Sit and wait."))
    available.append(("spear", "Spear fishing", "Fast, needs agility. Works in shallows."))
    if has_net:
        available.append(("net", "Net", "Wide catch area. Good for small fish."))

    # What fish are available this season in this region?
    possible_fish = [f for f in FISH_DB.values()
                     if season in f.seasonal_availability
                     and any(r.lower() in region.lower() for r in f.core_regions)]
    if not possible_fish:
        possible_fish = [FISH_DB.get("channel_catfish"), FISH_DB.get("rainbow_trout")]
        possible_fish = [f for f in possible_fish if f]

    # Spot quality — degrades with use (track on tile)
    tile = lmap.tile_at(player.local_x, player.local_y)
    if not hasattr(tile, '_fish_pressure'):
        tile._fish_pressure = 0.0
    spot_quality = max(0.1, 1.0 - tile._fish_pressure * 0.15)

    # ── UI ────────────────────────────────────────────────────────
    W, H = 60, 32
    X = (console.width - W) // 2
    Y = (console.height - H) // 2

    total_caught = 0
    total_weight = 0.0
    session_messages = []
    fishing = True

    while fishing:
        draw_box(console, X, Y, W, H, "FISHING")

        # Info panel
        y = Y + 2
        console.print(X + 2, y, f"Location: {region}", fg=GREY, bg=BG)
        y += 1
        console.print(X + 2, y, f"Season: {season.capitalize()}", fg=GREY, bg=BG)
        night_str = " (night)" if period == "night" else ""
        console.print(X + 30, y, f"Time: {period}{night_str}", fg=GREY, bg=BG)
        y += 1

        # Spot quality bar
        sq_pct = int(spot_quality * 20)
        sq_bar = chr(0x2588) * sq_pct + chr(0x2591) * (20 - sq_pct)
        sq_color = GREEN if spot_quality > 0.6 else YELLOW if spot_quality > 0.3 else RED
        console.print(X + 2, y, f"Spot: [{sq_bar}]", fg=sq_color, bg=BG)
        y += 1

        # Available fish this season
        console.print(X + 2, y, f"Fish running: {len(possible_fish)} species", fg=BLUE, bg=BG)
        y += 1
        for f in possible_fish[:6]:
            dc_str = "*" * f.catch_difficulty
            console.print(X + 4, y, f"{f.display_name:20s} {f.avg_weight_lb:5.1f}lb  {dc_str}",
                          fg=WHITE, bg=BG)
            y += 1
        if len(possible_fish) > 6:
            console.print(X + 4, y, f"...and {len(possible_fish)-6} more", fg=GREY, bg=BG)
            y += 1

        y += 1

        # Session stats
        console.print(X + 2, y, f"Caught this session: {total_caught} ({total_weight:.1f} lb)",
                      fg=CYAN, bg=BG)
        y += 1

        # Methods
        y += 1
        console.print(X + 2, y, "METHOD:", fg=YELLOW, bg=BG)
        y += 1
        for i, (mid, mlabel, mdesc) in enumerate(available):
            console.print(X + 4, y, f"[{i+1}] {mlabel} — {mdesc}",
                          fg=WHITE, bg=BG)
            y += 1

        y += 1
        console.print(X + 2, y, "[ESC] Stop fishing", fg=GREY, bg=BG)

        # Messages
        y += 2
        for msg in session_messages[-4:]:
            console.print(X + 2, y, msg[:W-4], fg=WHITE, bg=BG)
            y += 1

        ctx.present(console)

        # ── Input ────────────────────────────────────────────────
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                raise SystemExit()
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                K = tcod.event.KeySym

                if sym == K.ESCAPE:
                    fishing = False
                    break

                # Pick method by number key
                method_idx = None
                if sym in (K.N1, K.KP_1): method_idx = 0
                elif sym in (K.N2, K.KP_2): method_idx = 1
                elif sym in (K.N3, K.KP_3): method_idx = 2
                elif sym in (K.N4, K.KP_4): method_idx = 3

                if method_idx is not None and method_idx < len(available):
                    method_key = available[method_idx][0]

                    # Check bait
                    bait_bonus = 0.0
                    for bait_id, bonus in BAIT_ITEMS.items():
                        for item in player.inventory:
                            if item.id == bait_id:
                                bait_bonus = bonus
                                break
                        if bait_bonus > 0:
                            break

                    # Attempt catch with spot quality modifier
                    fish = FishingMechanics.attempt_catch(
                        region, method_key,
                        player.skills.get("survival", 0),
                        season, rng)

                    # Apply spot quality and bait
                    if fish and rng.random() > (spot_quality + bait_bonus):
                        fish = None  # spot too degraded / no bait

                    # Night fishing — catfish and eels are easier
                    if fish and period == "night":
                        if fish.catch_difficulty <= 2:
                            pass  # easier fish caught more at night
                        elif rng.random() < 0.3:
                            fish = None  # harder fish harder to see at night

                    time_cost = FishingMechanics.time_cost(method_key)

                    if fish is None:
                        no_catch = [
                            "Nothing biting.",
                            "You wait... nothing. The water mocks you.",
                            "A nibble, but it got away.",
                            "Quiet water. No luck this time.",
                            "Something big swirled near your line, then vanished.",
                        ]
                        session_messages.append(rng.choice(no_catch))
                    else:
                        # Weight variation
                        weight = fish.avg_weight_lb * rng.uniform(0.5, 1.5)
                        total_caught += 1
                        total_weight += weight

                        # Create item
                        caught = make_item("fresh_fish")
                        caught.name = f"Fresh {fish.display_name}"
                        caught.nutrition = fish.nutrition
                        caught.weight = max(0.3, weight)
                        player.inventory.append(caught)

                        msg = FishingMechanics.get_catch_message(fish, method_key)
                        msg += f" ({weight:.1f} lb)"
                        session_messages.append(msg)

                        player.gain_skill_xp("survival", 1.5 + fish.catch_difficulty * 0.5)

                    # Degrade spot
                    tile._fish_pressure += 0.1
                    spot_quality = max(0.1, 1.0 - tile._fish_pressure * 0.15)

                    engine.advance_time(time_cost)
                    break

    # Session summary
    if total_caught > 0:
        engine.add_message(
            f"Fishing session: caught {total_caught} fish ({total_weight:.1f} lb total).",
            "normal")
        if engine.journal:
            engine.journal.add_diary(
                engine.time.date_string,
                f"Fished. Caught {total_caught} fish ({total_weight:.1f} lb).")
    else:
        engine.add_message("Didn't catch anything. Maybe try a different spot.", "normal")
