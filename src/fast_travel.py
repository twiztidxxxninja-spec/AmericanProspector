"""
src/fast_travel.py

Fast travel system for American Prospector.
Player selects a destination from zoomed-out map views, sees trip
estimate (time, food, encounters), chooses travel style, then
time-skips to the destination.

Food consumed upfront. Water assumed from streams (except desert).
Random encounters capped at ~3 per trip regardless of distance.
"""

import random
import tcod
import tcod.event
import tcod.console
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine import Engine
    from src.world_map import WorldMap
    from src.player import Player


# ============================================================================
#  TRIP ESTIMATE
# ============================================================================

@dataclass
class TripEstimate:
    total_minutes: int
    total_miles: float
    meals_needed: float          # nutrition units worth of food
    water_needed: bool           # True if desert route requires carried water
    path: List[Tuple[int, int]]  # world tiles along the route
    terrain_summary: str         # "mostly plains and hills"
    has_desert: bool
    warnings: List[str] = field(default_factory=list)


# ============================================================================
#  TRAVEL STYLE
# ============================================================================

class TravelStyle:
    NORMAL    = "normal"       # use food from pack
    HUNT      = "hunt"         # hunt along the way, +30% time
    FORAGE    = "forage"       # forage, +20% time, half food
    HUNGRY    = "hungry"       # no food, arrive weakened


# ============================================================================
#  CALCULATE TRIP
# ============================================================================

def calculate_trip(player: "Player", world_map: "WorldMap",
                    to_wx: int, to_wy: int) -> TripEstimate:
    """
    Calculate a trip from player's current position to (to_wx, to_wy).
    Returns a TripEstimate with cost, food needs, path, and warnings.
    """
    from src.world_map import Terrain, TERRAIN_NAME

    from_wx, from_wy = player.world_x, player.world_y
    total_minutes = 0
    path = []
    terrain_counts = {}
    has_desert = False
    has_ocean = False

    # Manhattan path: x first, then y
    cx, cy = from_wx, from_wy
    while cx != to_wx:
        cx += 1 if to_wx > cx else -1
        if world_map.in_bounds(cx, cy):
            cost = world_map.travel_cost(cx, cy)
            terrain = int(world_map.tiles[cy][cx])
            tname = TERRAIN_NAME.get(terrain, "unknown")
            terrain_counts[tname] = terrain_counts.get(tname, 0) + 1
            if terrain == Terrain.DESERT:
                has_desert = True
            if terrain == Terrain.OCEAN:
                has_ocean = True
            total_minutes += int(cost)
            path.append((cx, cy))

    while cy != to_wy:
        cy += 1 if to_wy > cy else -1
        if world_map.in_bounds(cx, cy):
            cost = world_map.travel_cost(cx, cy)
            terrain = int(world_map.tiles[cy][cx])
            tname = TERRAIN_NAME.get(terrain, "unknown")
            terrain_counts[tname] = terrain_counts.get(tname, 0) + 1
            if terrain == Terrain.DESERT:
                has_desert = True
            if terrain == Terrain.OCEAN:
                has_ocean = True
            total_minutes += int(cost)
            path.append((cx, cy))

    # Mount bonus — new pack animal system or legacy
    has_mount = False
    if hasattr(player, '_animal_mgr') and player._animal_mgr:
        has_mount = player._animal_mgr.has_rideable()
    else:
        has_mount = any(pa.get("type_id") in ("horse", "mule")
                        for pa in player.pack_animals)
    if has_mount:
        total_minutes = int(total_minutes * 0.4)

    total_hours = total_minutes / 60.0
    total_miles = len(path) * 5.0  # ~5 miles per world tile

    # Food needs: ~2 hunger/hour, ~20 nutrition per meal = 1 meal per 10 hours
    meals_needed = total_hours / 10.0

    # Terrain summary
    if terrain_counts:
        sorted_terrains = sorted(terrain_counts.items(), key=lambda kv: -kv[1])
        top = [f"{n}" for n, _ in sorted_terrains[:3]]
        terrain_summary = "mostly " + ", ".join(top)
    else:
        terrain_summary = "unknown terrain"

    warnings = []
    if has_ocean:
        warnings.append("Route crosses ocean — impassable!")
    if has_desert:
        warnings.append("Desert terrain — bring water!")

    # Check food supply
    food_nutrition = sum(getattr(i, "nutrition", 0) * getattr(i, "quantity", 1)
                          for i in player.inventory if getattr(i, "nutrition", 0) > 0)
    if food_nutrition < meals_needed * 20:
        warnings.append(f"Not enough food! Need ~{meals_needed:.0f} meals, "
                        f"have ~{food_nutrition / 20:.0f}")

    return TripEstimate(
        total_minutes=total_minutes,
        total_miles=total_miles,
        meals_needed=meals_needed,
        water_needed=has_desert,
        path=path,
        terrain_summary=terrain_summary,
        has_desert=has_desert,
        warnings=warnings,
    )


# ============================================================================
#  EXECUTE TRIP
# ============================================================================

def execute_trip(engine: "Engine", estimate: TripEstimate,
                  style: str = TravelStyle.NORMAL) -> Tuple[str, Tuple[int, int]]:
    """
    Execute the fast travel. Consumes food, advances time, marks tiles,
    rolls encounters, teleports player.

    Returns (result, (final_wx, final_wy)) where result is:
    "arrived", "encounter", "ocean_blocked"
    """
    player = engine.player
    world_map = engine.world

    # Check for ocean in path
    from src.world_map import Terrain
    for wx, wy in estimate.path:
        if int(world_map.tiles[wy][wx]) == Terrain.OCEAN:
            return "ocean_blocked", (player.world_x, player.world_y)

    # Time modifier by style
    time_mult = {
        TravelStyle.NORMAL: 1.0,
        TravelStyle.HUNT:   1.3,
        TravelStyle.FORAGE: 1.2,
        TravelStyle.HUNGRY: 1.0,
    }.get(style, 1.0)

    total_minutes = int(estimate.total_minutes * time_mult)

    # Consume food from inventory
    if style == TravelStyle.NORMAL:
        _consume_food(player, estimate.meals_needed * 20)
    elif style == TravelStyle.FORAGE:
        _consume_food(player, estimate.meals_needed * 10)  # half
    # HUNT and HUNGRY consume nothing

    # Mark all tiles along path as visited + travel events + discoveries
    from src.walking_events import roll_walking_event, TRAVEL_CHANCE
    from src.discovery import roll_location_discovery
    travel_events = []
    discoveries = []
    for wx, wy in estimate.path:
        was_visited = world_map.visited[wy][wx]
        world_map.mark_visited(wx, wy)
        # Roll for location discovery on previously unvisited tiles
        if not was_visited and len(discoveries) < 3:
            disc = roll_location_discovery(engine, wx, wy)
            if disc:
                discoveries.append(disc)
        # Roll for atmospheric travel events (frequent)
        lmap_key = (wx, wy, 7, 7)
        if lmap_key in engine.locals:
            evt = roll_walking_event(engine, engine.locals[lmap_key], 192, 192,
                                     chance=TRAVEL_CHANCE)
            if evt and len(travel_events) < 5:
                travel_events.append(evt[0])
    for msg in travel_events:
        engine.add_message(msg, "normal")
    for disc_msg in discoveries:
        engine.add_message(disc_msg, "advisory")

    # Roll for encounters (max 3)
    rng = random.Random()
    encounter_count = min(3, len(estimate.path) // 10 + 1)
    encounter_tile = None
    for _ in range(encounter_count):
        if rng.random() < 0.15:  # 15% per roll
            idx = rng.randint(0, len(estimate.path) - 1)
            encounter_tile = estimate.path[idx]
            break

    if encounter_tile:
        # Travel to encounter point, then pause
        enc_wx, enc_wy = encounter_tile
        enc_idx = estimate.path.index(encounter_tile)
        # Advance partial time
        partial_frac = (enc_idx + 1) / len(estimate.path)
        partial_minutes = int(total_minutes * partial_frac)
        _advance_days(engine, partial_minutes)
        _teleport_player(engine, enc_wx, enc_wy)
        return "encounter", encounter_tile

    # Full travel — advance time and teleport
    _advance_days(engine, total_minutes)
    dest_wx, dest_wy = estimate.path[-1]
    _teleport_player(engine, dest_wx, dest_wy)

    # Set post-journey survival stats
    s = player.survival
    if style == TravelStyle.NORMAL:
        s.hunger, s.thirst, s.fatigue = 65, 70, 35
    elif style == TravelStyle.HUNT:
        s.hunger, s.thirst, s.fatigue = 55, 70, 30
    elif style == TravelStyle.FORAGE:
        s.hunger, s.thirst, s.fatigue = 45, 65, 30
    elif style == TravelStyle.HUNGRY:
        s.hunger, s.thirst, s.fatigue = 10, 60, 20
        s.health = max(10, s.health - 15)

    if estimate.has_desert and style != TravelStyle.NORMAL:
        s.thirst = max(15, s.thirst - 40)
        s.health = max(10, s.health - 10)

    s.warmth = 70  # assumed campfires

    return "arrived", (dest_wx, dest_wy)


def _consume_food(player, nutrition_needed: float) -> None:
    """Consume food items from inventory, most perishable first."""
    food = sorted(
        [i for i in player.inventory if getattr(i, "nutrition", 0) > 0],
        key=lambda i: getattr(i, "days_until_spoil", 9999) or 9999)
    remaining = nutrition_needed
    for item in list(food):
        if remaining <= 0:
            break
        nut = item.nutrition * getattr(item, "quantity", 1)
        if nut <= remaining:
            remaining -= nut
            player.inventory.remove(item)
        else:
            # Partial consumption
            meals_to_eat = int(remaining / item.nutrition) + 1
            if item.stackable and item.quantity > meals_to_eat:
                item.quantity -= meals_to_eat
            else:
                player.inventory.remove(item)
            remaining = 0


def _advance_days(engine, minutes: int) -> None:
    """Advance game time by minutes, triggering daily ticks but NOT survival drain."""
    # Save current survival stats — we'll restore them after
    # (fast travel handles survival separately)
    s = engine.player.survival
    saved = (s.hunger, s.thirst, s.warmth, s.fatigue, s.health)

    engine.time.advance(minutes)
    # Run daily ticks for each day passed
    days = minutes // 1440
    for d in range(days):
        engine._run_daily_ticks(engine.time.total_minutes // 1440 - days + d + 1)

    # Restore survival stats (fast travel handles these separately)
    s.hunger, s.thirst, s.warmth, s.fatigue, s.health = saved


def _teleport_player(engine, wx: int, wy: int) -> None:
    """Move player to a world tile's center patch and generate the local map."""
    from src.constants import AREAS_PER_WORLD
    center = AREAS_PER_WORLD // 2
    engine.player.world_x = wx
    engine.player.world_y = wy
    engine.player.area_x = center
    engine.player.area_y = center
    engine.world.mark_visited(wx, wy)
    lmap = engine._ensure_local(wx, wy, center, center)
    # Place at center of local map
    engine.player.local_x = lmap.width // 2
    engine.player.local_y = lmap.height // 2
    engine.player.local_z = lmap.ground_z(
        engine.player.local_x, engine.player.local_y)
    engine._preload_neighbors()
    engine.recompute_fov()
    # Place pack animals near player
    if hasattr(engine, 'animal_mgr') and engine.animal_mgr.animals:
        engine.animal_mgr.place_all_near(
            engine.player.local_x, engine.player.local_y, lmap)


# ============================================================================
#  STAGECOACH & STEAMBOAT ROUTES (1840s California)
# ============================================================================

@dataclass
class TransportRoute:
    """A scheduled transport route between two towns."""
    route_id: str
    origin: str                 # town name
    destination: str
    method: str                 # "stagecoach" | "steamboat"
    fare: float                 # one-way fare in dollars
    travel_hours: int           # total travel time
    era_start: int = 1849       # year route becomes available
    luggage_limit_lb: float = 30.0  # max personal luggage


# Historical routes for 1840s-1850s California
TRANSPORT_ROUTES: List[TransportRoute] = [
    # Steamboat routes (Sacramento River)
    TransportRoute("steam_sf_sac", "San Francisco", "Sacramento",
                   "steamboat", 25.0, 8, era_start=1849, luggage_limit_lb=100),
    TransportRoute("steam_sac_sf", "Sacramento", "San Francisco",
                   "steamboat", 25.0, 8, era_start=1849, luggage_limit_lb=100),
    TransportRoute("steam_sac_mary", "Sacramento", "Marysville",
                   "steamboat", 15.0, 6, era_start=1850, luggage_limit_lb=100),
    TransportRoute("steam_mary_sac", "Marysville", "Sacramento",
                   "steamboat", 15.0, 6, era_start=1850, luggage_limit_lb=100),

    # Stagecoach routes
    TransportRoute("stage_sac_plac", "Sacramento", "Placerville",
                   "stagecoach", 10.0, 8, era_start=1849),
    TransportRoute("stage_plac_sac", "Placerville", "Sacramento",
                   "stagecoach", 10.0, 8, era_start=1849),
    TransportRoute("stage_sac_aub", "Sacramento", "Auburn",
                   "stagecoach", 8.0, 6, era_start=1849),
    TransportRoute("stage_aub_sac", "Auburn", "Sacramento",
                   "stagecoach", 8.0, 6, era_start=1849),
    TransportRoute("stage_stock_son", "Stockton", "Sonora",
                   "stagecoach", 12.0, 10, era_start=1850),
    TransportRoute("stage_son_stock", "Sonora", "Stockton",
                   "stagecoach", 12.0, 10, era_start=1850),
    TransportRoute("stage_sac_mary", "Sacramento", "Marysville",
                   "stagecoach", 15.0, 12, era_start=1850),
    TransportRoute("stage_mary_sac", "Marysville", "Sacramento",
                   "stagecoach", 15.0, 12, era_start=1850),
    TransportRoute("stage_sf_sj", "San Francisco", "San Jose",
                   "stagecoach", 8.0, 6, era_start=1849),
    TransportRoute("stage_sj_sf", "San Jose", "San Francisco",
                   "stagecoach", 8.0, 6, era_start=1849),
]


def get_available_routes(town_name: str, year: int) -> List[TransportRoute]:
    """Get transport routes departing from a town in the given year."""
    return [r for r in TRANSPORT_ROUTES
            if r.origin == town_name and year >= r.era_start]


def take_transport(engine: "Engine", route: TransportRoute) -> str:
    """Execute a transport route. Deducts fare, advances time, teleports.
    Returns result message."""
    player = engine.player

    if player.cash < route.fare:
        return f"You can't afford the ${route.fare:.0f} fare."

    # Check luggage
    carry_weight = player.carried_weight
    if carry_weight > route.luggage_limit_lb:
        return (f"Too much luggage — {route.method} allows "
                f"{route.luggage_limit_lb:.0f}lb, you're carrying {carry_weight:.0f}lb. "
                f"Leave some with your animals or store it.")

    # Deduct fare
    player.cash -= route.fare

    # Find destination world coordinates
    dest_loc = None
    for name, loc in engine.world.locations.items():
        if loc.name == route.destination:
            dest_loc = loc
            break

    if not dest_loc:
        player.cash += route.fare  # refund
        return f"Can't find {route.destination} on the map."

    # Advance time
    total_minutes = route.travel_hours * 60
    _advance_days(engine, total_minutes)

    # Teleport
    _teleport_player(engine, dest_loc.x, dest_loc.y)

    # Set arrival condition (well-rested from riding)
    s = player.survival
    s.hunger = max(s.hunger, 60)
    s.thirst = max(s.thirst, 70)
    s.fatigue = max(s.fatigue, 50)
    s.warmth = 75

    method_name = "Steamboat" if route.method == "steamboat" else "Stagecoach"
    return (f"{method_name} to {route.destination} — ${route.fare:.0f}, "
            f"{route.travel_hours} hours. You arrive tired but intact.")
    engine.state = "local_map"
    engine.map_level_index = 0

    loc = engine.world.get_location_at(wx, wy)
    if loc:
        engine.add_message(f"You arrive at {loc.name}.", "normal")
    else:
        engine.add_message("You arrive at your destination.", "normal")


# ============================================================================
#  FAST TRAVEL UI
# ============================================================================

WHITE  = (255, 255, 255)
YELLOW = (255, 220,  60)
CYAN   = ( 80, 200, 200)
GREEN  = ( 80, 180,  80)
RED    = (220,  50,  50)
GREY   = (120, 120, 120)
DGREY  = ( 60,  60,  60)
BG     = ( 15,  15,  30)
BG_SEL = ( 35,  35,  65)


def fast_travel_ui(con: tcod.console.Console, ctx,
                    estimate: TripEstimate, player: "Player",
                    dest_name: str = "",
                    transport_routes: Optional[List[TransportRoute]] = None
                    ) -> Optional[str]:
    """
    Show trip confirmation screen. Returns TravelStyle, "transport_N"
    (where N is route index), or None if cancelled.
    """
    W, H = 56, 28
    X = (con.width - W) // 2
    Y = (con.height - H) // 2
    K = tcod.event.KeySym

    # Build options
    firearms = player.skills.get("firearms", 0)
    tracking = player.skills.get("tracking", 0)
    survival = player.skills.get("survival", 0)
    can_hunt = max(firearms, tracking) >= 2
    can_forage = survival >= 2

    days = estimate.total_minutes / 1440
    hours = (estimate.total_minutes % 1440) / 60

    options = [
        (TravelStyle.NORMAL,  f"Travel with supplies ({estimate.meals_needed:.0f} meals)", True),
        (TravelStyle.HUNT,    f"Hunt along the way (+30% time)", can_hunt),
        (TravelStyle.FORAGE,  f"Forage along the way (+20% time)", can_forage),
        (TravelStyle.HUNGRY,  f"Go hungry (arrive weakened)", True),
    ]

    # Add available transport routes
    if transport_routes:
        for i, route in enumerate(transport_routes):
            method = "Steamboat" if route.method == "steamboat" else "Stage"
            can_afford = player.cash >= route.fare
            label = (f"{method} to {route.destination} — ${route.fare:.0f}, "
                     f"{route.travel_hours}hr")
            if not can_afford:
                label += " (can't afford)"
            options.append((f"transport_{i}", label, can_afford))
    selected = 0

    while True:
        con.draw_rect(X, Y, W, H, ord(" "), fg=WHITE, bg=BG)
        # Border
        for bx in range(X, X + W):
            con.print(bx, Y, "─", fg=DGREY, bg=BG)
            con.print(bx, Y+H-1, "─", fg=DGREY, bg=BG)
        for by in range(Y, Y + H):
            con.print(X, by, "│", fg=DGREY, bg=BG)
            con.print(X+W-1, by, "│", fg=DGREY, bg=BG)

        title = f" TRAVEL TO {dest_name.upper()[:30]} " if dest_name else " FAST TRAVEL "
        con.print(X + (W - len(title)) // 2, Y, title, fg=YELLOW, bg=BG)

        # Trip info
        row = Y + 2
        con.print(X+2, row, f"Distance: {len(estimate.path)} tiles (~{estimate.total_miles:.0f} miles)",
                  fg=WHITE, bg=BG)
        row += 1
        con.print(X+2, row, f"Terrain: {estimate.terrain_summary}", fg=GREY, bg=BG)
        row += 1
        con.print(X+2, row, f"Est. time: {int(days)} days, {int(hours)} hours",
                  fg=WHITE, bg=BG)
        row += 1
        con.print(X+2, row, f"Food needed: ~{estimate.meals_needed:.0f} meals",
                  fg=WHITE, bg=BG)
        row += 1

        # Warnings
        for warn in estimate.warnings:
            con.print(X+2, row, warn, fg=RED, bg=BG)
            row += 1

        row += 1
        con.print(X+2, row, "TRAVEL OPTIONS:", fg=GREY, bg=BG)
        row += 1

        for i, (style, label, enabled) in enumerate(options):
            sel = (i == selected)
            fg = CYAN if sel else (WHITE if enabled else DGREY)
            bg_c = BG_SEL if sel else BG
            marker = ">" if sel else " "
            suffix = "" if enabled else " (skill too low)"
            con.print(X+2, row + i, f"{marker} {label}{suffix}"[:W-4], fg=fg, bg=bg_c)

        # Footer
        con.print(X+2, Y+H-2, "↑↓ Select  Enter Confirm  Esc Cancel",
                  fg=DGREY, bg=BG)

        ctx.present(con)

        for event in tcod.event.wait():
            if not isinstance(event, tcod.event.KeyDown):
                continue
            sym = event.sym
            if sym == K.ESCAPE:
                return None
            if sym in (K.UP, K.KP_8):
                selected = (selected - 1) % len(options)
            if sym in (K.DOWN, K.KP_2):
                selected = (selected + 1) % len(options)
            if sym in (K.RETURN, K.KP_ENTER):
                style, label, enabled = options[selected]
                if enabled:
                    return style


# ============================================================================
#  ENCOUNTER UI
# ============================================================================

def encounter_ui(con: tcod.console.Console, ctx,
                  wx: int, wy: int, world_map) -> str:
    """
    Show encounter options during fast travel.
    Returns: "investigate", "avoid", "run"
    """
    W, H = 44, 14
    X = (con.width - W) // 2
    Y = (con.height - H) // 2
    K = tcod.event.KeySym

    from src.world_map import TERRAIN_NAME
    terrain = int(world_map.tiles[wy][wx])
    tname = TERRAIN_NAME.get(terrain, "wilderness")
    loc = world_map.get_location_at(wx, wy)
    loc_name = loc.name if loc else f"the {tname}"

    options = [
        ("investigate", "Investigate (enter local map)"),
        ("avoid",       "Go around (+1-2 hours)"),
        ("run",         "Run past (Agility check)"),
    ]
    selected = 0

    while True:
        con.draw_rect(X, Y, W, H, ord(" "), fg=WHITE, bg=BG)
        for bx in range(X, X + W):
            con.print(bx, Y, "─", fg=DGREY, bg=BG)
            con.print(bx, Y+H-1, "─", fg=DGREY, bg=BG)

        con.print(X+2, Y, " ENCOUNTER ", fg=YELLOW, bg=BG)
        con.print(X+2, Y+2, f"Something ahead near {loc_name}.", fg=WHITE, bg=BG)
        con.print(X+2, Y+3, "What do you do?", fg=GREY, bg=BG)

        for i, (key, label) in enumerate(options):
            sel = (i == selected)
            fg = CYAN if sel else WHITE
            bg_c = BG_SEL if sel else BG
            marker = ">" if sel else " "
            con.print(X+2, Y+5+i, f"{marker} {label}", fg=fg, bg=bg_c)

        con.print(X+2, Y+H-2, "↑↓ Select  Enter Confirm", fg=DGREY, bg=BG)
        ctx.present(con)

        for event in tcod.event.wait():
            if not isinstance(event, tcod.event.KeyDown):
                continue
            sym = event.sym
            if sym in (K.UP, K.KP_8):
                selected = (selected - 1) % len(options)
            if sym in (K.DOWN, K.KP_2):
                selected = (selected + 1) % len(options)
            if sym in (K.RETURN, K.KP_ENTER):
                return options[selected][0]
