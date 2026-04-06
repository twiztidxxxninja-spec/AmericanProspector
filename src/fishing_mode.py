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


# Bait → bonus AND which species it attracts
BAIT_ITEMS = {
    "worm":          (0.15, {"trout", "bass", "perch", "sunfish", "bluegill"}),
    "insect":        (0.12, {"trout", "bass", "perch"}),
    "fresh_venison": (0.20, {"catfish", "pike", "eel"}),    # blood/meat = catfish bait
    "fresh_fish":    (0.15, {"bass", "pike", "catfish", "sturgeon"}),  # cut bait
    "fish_guts":     (0.25, {"catfish", "eel", "pike", "sturgeon", "bass"}),  # best bait
    "fish_fillet":   (0.15, {"bass", "pike", "catfish"}),   # cut bait
    "wild_berries":  (0.05, {"trout", "sucker"}),
    "castoreum_lure":(0.20, {"trout", "bass", "pike", "walleye"}),  # trapping lure works for fish too
}

# Method definitions with what they can realistically catch
# method_id, label, description, tool_tag needed, species_tags catchable, size_max_lb
METHODS = {
    "pole": {
        "label": "Pole & line",
        "desc": "Sit and wait. Trout, bass, catfish, perch bite on bait.",
        "tool": "fish",        # needs fishing_line or pole in inventory
        "time": 30,
        "base_chance": 0.50,
        "species_tags": {"trout", "bass", "catfish", "perch", "sunfish",
                         "bluegill", "walleye", "minnow", "sucker", "whitefish"},
        "max_weight": 30,      # can't land a 60lb sturgeon on a line
    },
    "spear": {
        "label": "Spear",
        "desc": "Stab visible fish in shallows. Salmon runs, sturgeon, lamprey.",
        "tool": "",            # any sharp stick works
        "time": 15,
        "base_chance": 0.30,
        "species_tags": {"salmon", "steelhead", "sturgeon", "lamprey",
                         "pike", "sucker", "blackfish"},
        "max_weight": 80,      # can spear a sturgeon if strong enough
    },
    "hand": {
        "label": "Bare hands",
        "desc": "Noodling for catfish in mud holes. Tickling trout under rocks.",
        "tool": "",
        "time": 20,
        "base_chance": 0.15,
        "species_tags": {"catfish", "trout", "sucker", "eel", "lamprey"},
        "max_weight": 15,
    },
    "dip_net": {
        "label": "Dip net",
        "desc": "Scoop small fish from shallows. Fast, catches many small ones.",
        "tool": "net",
        "time": 10,
        "base_chance": 0.60,
        "species_tags": {"minnow", "perch", "sunfish", "bluegill", "sucker",
                         "lamprey", "hitch"},
        "max_weight": 5,       # small net, small fish
    },
    "gill_net": {
        "label": "Gill net",
        "desc": "Stretch across stream. Set and wait. Catches everything swimming through.",
        "tool": "gill_net",
        "time": 120,           # set and come back
        "base_chance": 0.75,
        "species_tags": {"salmon", "steelhead", "trout", "bass", "catfish",
                         "pike", "walleye", "sturgeon", "perch", "whitefish",
                         "sucker", "blackfish", "striped_bass"},
        "max_weight": 60,      # catches anything
    },
    "weir": {
        "label": "Fish weir/trap",
        "desc": "Block the stream with rocks and stakes. Fish pile up. "
                "Best during spawning runs.",
        "tool": "",            # build from rocks and sticks
        "time": 180,           # build + wait
        "base_chance": 0.85,
        "species_tags": {"salmon", "steelhead", "lamprey", "sucker"},
        "max_weight": 40,
    },
}

# Map fish species to method tags (what method groups can catch them)
SPECIES_METHOD_TAGS = {
    "chinook_salmon":     {"salmon"},
    "coho_salmon":        {"salmon"},
    "sockeye_salmon":     {"salmon"},
    "pink_salmon":        {"salmon"},
    "chum_salmon":        {"salmon"},
    "steelhead_trout":    {"steelhead", "trout"},
    "rainbow_trout":      {"trout"},
    "cutthroat_trout":    {"trout"},
    "brook_trout":        {"trout"},
    "atlantic_salmon":    {"salmon"},
    "lake_trout":         {"trout"},
    "largemouth_bass":    {"bass"},
    "smallmouth_bass":    {"bass"},
    "bluegill":           {"bluegill", "sunfish"},
    "channel_catfish":    {"catfish"},
    "flathead_catfish":   {"catfish"},
    "northern_pike":      {"pike"},
    "walleye":            {"walleye", "perch"},
    "yellow_perch":       {"perch"},
    "white_sturgeon":     {"sturgeon"},
    "green_sturgeon":     {"sturgeon"},
    "american_eel":       {"eel"},
    "sacramento_pikeminnow": {"minnow", "sucker"},
    "sacramento_sucker":  {"sucker"},
    "tule_perch":         {"perch", "minnow"},
    "hardhead_minnow":    {"minnow"},
    "sacramento_blackfish": {"blackfish", "sucker"},
    "hitch":              {"minnow", "hitch"},
    "mountain_whitefish": {"whitefish", "trout"},
    "bull_trout":         {"trout"},
    "dolly_varden":       {"trout"},
    "green_sunfish":      {"sunfish", "bluegill"},
    "white_catfish":      {"catfish"},
    "striped_bass":       {"bass", "striped_bass"},
    "pacific_lamprey":    {"lamprey"},
}


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

    # Check for fishing gear in inventory
    has_pole = any("fish" in getattr(i, "tool_tags", []) for i in player.inventory)
    has_dip_net = any("net" in getattr(i, "tool_tags", []) for i in player.inventory)
    has_gill_net = any("gill_net" in getattr(i, "tool_tags", []) for i in player.inventory)

    # Check for sharp tool (spear needs it)
    has_sharp = any(any(t in getattr(i, "tool_tags", [])
                        for t in ("cut", "butcher", "chop"))
                    for i in player.inventory)

    # Build available methods based on gear
    available = []
    if has_pole:
        available.append("pole")
    if has_sharp:
        available.append("spear")
    available.append("hand")
    if has_dip_net:
        available.append("dip_net")
    if has_gill_net:
        available.append("gill_net")
    # Weir needs 3+ logs
    log_count = sum(getattr(i, 'quantity', 1) for i in player.inventory if i.id == "log")
    if log_count >= 3:
        available.append("weir")

    # Gill net state — set and return later
    gill_net_set = False
    gill_net_set_time = 0

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
        console.print(X + 30, y, f"Time: {period}", fg=GREY, bg=BG)
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
        for i, mid in enumerate(available):
            m = METHODS[mid]
            console.print(X + 4, y, f"[{i+1}] {m['label']} — {m['desc'][:40]}",
                          fg=WHITE, bg=BG)
            y += 1

        if not has_sharp and "spear" not in available:
            y += 1
            console.print(X + 4, y, "(Spear needs a knife or sharp tool)",
                          fg=GREY, bg=BG)
        if gill_net_set:
            y += 1
            elapsed = engine.time.total_minutes - gill_net_set_time
            console.print(X + 4, y, f"Gill net set: {elapsed} min ago "
                          f"({'ready!' if elapsed >= 90 else 'waiting...'})",
                          fg=GREEN if elapsed >= 90 else YELLOW, bg=BG)

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
                elif sym in (K.N5, K.KP_5): method_idx = 4
                elif sym in (K.N6, K.KP_6): method_idx = 5

                if method_idx is not None and method_idx < len(available):
                    method_key = available[method_idx]
                    method = METHODS[method_key]

                    # Weir consumes 3 logs on first build
                    if method_key == "weir" and not hasattr(tile, '_weir_built'):
                        logs_used = 0
                        for item in list(player.inventory):
                            if item.id == "log" and logs_used < 3:
                                qty = getattr(item, 'quantity', 1)
                                take = min(qty, 3 - logs_used)
                                if item.stackable and qty > take:
                                    item.quantity -= take
                                else:
                                    player.inventory.remove(item)
                                logs_used += take
                        tile._weir_built = True
                        session_messages.append(
                            "You stack rocks and logs across the stream. "
                            "The weir is set. Fish will pile up.")

                    # Gill net — set it and wait, don't catch instantly
                    if method_key == "gill_net" and not gill_net_set:
                        gill_net_set = True
                        gill_net_set_time = engine.time.total_minutes
                        session_messages.append(
                            "You stretch the gill net across the stream "
                            "and tie it off. Come back in 2 hours to check it.")
                        engine.advance_time(10)  # 10 min to set
                        break
                    if method_key == "gill_net" and gill_net_set:
                        elapsed = engine.time.total_minutes - gill_net_set_time
                        if elapsed < 90:
                            session_messages.append(
                                f"Net has only been set {elapsed} minutes. "
                                f"Give it at least 90 minutes.")
                            break

                    # Ice fishing check — winter + frozen water
                    if season == "winter" and method_key in ("pole", "hand"):
                        session_messages.append(
                            "You chop a hole in the ice and drop your line. "
                            "Cold work. Patience required.")
                        # Fewer species in winter, but some are available
                        # (already handled by seasonal filter)

                    # Check bait — what species does it attract?
                    bait_bonus = 0.0
                    bait_species_tags = set()
                    for bait_id, (bonus, btags) in BAIT_ITEMS.items():
                        for item in player.inventory:
                            if item.id == bait_id:
                                bait_bonus = bonus
                                bait_species_tags = btags
                                break
                        if bait_bonus > 0:
                            break

                    # Filter possible fish by:
                    # 1. Season and region (already filtered in possible_fish)
                    # 2. Method can catch them (species tags match)
                    # 3. Not too big for the method
                    method_tags = method["species_tags"]
                    catchable = []
                    for f in possible_fish:
                        fish_tags = SPECIES_METHOD_TAGS.get(f.id, set())
                        if fish_tags & method_tags:  # intersection
                            if f.avg_weight_lb <= method["max_weight"]:
                                catchable.append(f)

                    if not catchable:
                        session_messages.append(
                            f"Nothing that a {method['label'].lower()} can catch here "
                            f"this time of year.")
                        engine.advance_time(method["time"] // 2)
                        break

                    # Base catch chance from fishing skill
                    skill = player.skills.get("fishing", 0)
                    catch_chance = method["base_chance"] + skill * 0.05

                    # Bait bonus if species match
                    if bait_species_tags:
                        bait_match = any(
                            SPECIES_METHOD_TAGS.get(f.id, set()) & bait_species_tags
                            for f in catchable)
                        if bait_match:
                            catch_chance += bait_bonus

                    # Spot quality
                    catch_chance *= spot_quality

                    # Canoe bonus — fishing from a boat is better
                    if getattr(player, '_in_canoe', False):
                        catch_chance *= 1.5

                    # Night modifier
                    if period == "night":
                        # Catfish/eel better at night, others worse
                        night_species = {"catfish", "eel", "lamprey"}
                        has_night_fish = any(
                            SPECIES_METHOD_TAGS.get(f.id, set()) & night_species
                            for f in catchable)
                        if has_night_fish:
                            catch_chance *= 1.3
                        else:
                            catch_chance *= 0.6

                    # Roll
                    fish = None
                    if rng.random() < catch_chance:
                        # Weight by inverse difficulty
                        weights = [max(1, 6 - f.catch_difficulty) for f in catchable]
                        fish = rng.choices(catchable, weights=weights, k=1)[0]

                    time_cost = method["time"]

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

                        # Create species-specific item with real trade value
                        caught = make_item("fresh_fish")
                        caught.name = f"Fresh {fish.display_name}"
                        caught.nutrition = fish.nutrition
                        caught.weight = max(0.3, weight)
                        # Base trade value — fish is cheap at the river
                        # Regional price multiplier handles markup in camps/towns
                        caught.base_value = round(weight * 0.02, 2)  # ~$0.44 for a 22lb salmon
                        # Tag with species for smoking/drying recipes
                        if not caught.extra:
                            caught.extra = {}
                        caught.extra["fish_species"] = fish.id
                        caught.extra["fish_weight"] = round(weight, 1)
                        player.inventory.append(caught)

                        msg = FishingMechanics.get_catch_message(fish, method_key)
                        msg += f" ({weight:.1f} lb, ${caught.base_value:.2f})"
                        session_messages.append(msg)

                        player.gain_skill_xp("fishing", 2.0 + fish.catch_difficulty * 0.5)

                        # Gill net catches multiple fish per check
                        if method_key == "gill_net" and rng.random() < 0.6:
                            bonus = rng.choices(catchable,
                                                weights=[max(1, 6 - f.catch_difficulty) for f in catchable],
                                                k=1)[0]
                            bw = bonus.avg_weight_lb * rng.uniform(0.5, 1.2)
                            bc = make_item("fresh_fish")
                            bc.name = f"Fresh {bonus.display_name}"
                            bc.nutrition = bonus.nutrition
                            bc.weight = max(0.3, bw)
                            bc.base_value = round(bw * 0.02, 2)
                            if not bc.extra: bc.extra = {}
                            bc.extra["fish_species"] = bonus.id
                            player.inventory.append(bc)
                            total_caught += 1
                            total_weight += bw
                            session_messages.append(
                                f"  Also in the net: {bonus.display_name} ({bw:.1f} lb)")

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
