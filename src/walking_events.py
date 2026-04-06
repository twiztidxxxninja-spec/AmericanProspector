"""
Random events while walking — things happen TO the player without initiating.

Called from engine._do_move() every few steps. Events are environmental
discoveries, sounds, sightings, and minor encounters that make the world
feel alive.

Each event is a (message, severity) tuple or None. Some events modify
the game state (items found, tile changes, NPC spawns).
"""

import random
from typing import Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine import Engine
    from src.local_map import LocalMap


# ── Event chance per step ─────────────────────────────────────────────────
# Local movement: very rare (1 in 200 steps ≈ once per 10 min of walking)
# Fast travel / zoomed movement: much more common (pass frequency directly)

LOCAL_CHANCE = 200
TRAVEL_CHANCE = 8   # during fast travel, per world tile traversed


def roll_walking_event(engine: "Engine", lmap: "LocalMap",
                       px: int, py: int,
                       chance: int = LOCAL_CHANCE) -> Optional[Tuple[str, str]]:
    """Roll for a random walking event. Returns (message, severity) or None.
    chance: 1-in-N probability. Lower = more frequent."""
    rng = random.Random()
    if rng.randint(1, chance) != 1:
        return None

    from src.local_map import LocalTerrain
    tile = lmap.tile_at(px, py)
    terrain = tile.terrain
    period = engine.time.period
    season = engine.time.season

    # Build weighted event pool based on terrain and time
    events = []

    # ── Environmental observations (always available) ─────────────
    events.extend([
        (_env_sound, 10),
        (_env_sight, 10),
        (_env_weather, 5),
        (_env_smell, 5),
    ])

    # ── Terrain-specific discoveries ──────────────────────────────
    if terrain in (LocalTerrain.GRAVEL_BAR, LocalTerrain.WATER,
                   LocalTerrain.WORKED_GRAVEL):
        events.append((_find_gold_sign, 8))
    if terrain in (LocalTerrain.GRASS, LocalTerrain.GROUND,
                   LocalTerrain.MUD, LocalTerrain.SAND):
        events.append((_find_tracks, 8))
        events.append((_find_item, 3))
    if terrain in (LocalTerrain.PINE, LocalTerrain.OAK, LocalTerrain.CEDAR,
                   LocalTerrain.MAPLE, LocalTerrain.CHESTNUT):
        events.append((_forest_event, 8))
    if terrain == LocalTerrain.ROCK or terrain == LocalTerrain.BEDROCK:
        events.append((_rock_event, 6))
        events.append((_discover_mineral_outcrop, 2))

    # ── Chain events (gameplay consequences) ──────────────────────
    events.append((_find_abandoned_camp, 2))
    events.append((_find_prospector_note, 1))
    events.append((_encounter_injured_traveler, 1))
    if period in ("night", "dusk"):
        events.append((_robbery_encounter, 2))

    # ── Superstitions & frontier flavor ──────────────────────────
    events.append((_superstition_event, 2))

    # ── Drunk stumble events ─────────────────────────────────────
    if engine.player.survival.is_drunk:
        events.append((_drunk_event, 15))  # high weight when drunk

    # ── Animal mischief ──────────────────────────────────────────
    events.append((_animal_mischief, 3))

    # ── Wildfire (late summer/fall, dry conditions) ──────────────
    if season in ("summer", "fall") and terrain in (
            LocalTerrain.GRASS, LocalTerrain.BRUSH, LocalTerrain.FOREST,
            LocalTerrain.PINE, LocalTerrain.OAK):
        hot_days = getattr(engine, '_consecutive_hot_days', 0)
        if hot_days >= 5:
            events.append((_wildfire_event, 3))

    # ── Time-specific ─────────────────────────────────────────────
    if period == "night":
        events.append((_night_event, 12))
    if period == "dawn":
        events.append((_dawn_event, 8))

    # ── Pick weighted random event ────────────────────────────────
    if not events:
        return None
    funcs, weights = zip(*events)
    func = rng.choices(funcs, weights=weights, k=1)[0]
    return func(engine, lmap, px, py, terrain, period, season, rng)


# ── Event generators ──────────────────────────────────────────────────────

def _env_sound(engine, lmap, px, py, terrain, period, season, rng):
    from src.local_map import LocalTerrain
    sounds = {
        "day": [
            "A woodpecker drums on a dead tree somewhere above you.",
            "You hear the distant crack of an axe. Someone's working out there.",
            "A hawk screams overhead, circling on a thermal.",
            "Water splashes nearby — could be fish, could be nothing.",
            "The wind picks up, rattling through the brush.",
            "Somewhere far off, a gunshot. Then silence.",
            "You hear singing — a prospector, somewhere down the creek.",
            "A branch snaps in the timber. Something moving.",
            "Crows arguing in the treetops.",
            "The buzz of flies. Something dead nearby.",
        ],
        "night": [
            "An owl hoots close. Then again, further away.",
            "Coyotes yipping in the distance. Getting closer.",
            "Something moves in the brush. Probably nothing.",
            "A twig snaps behind you. When you turn, nothing's there.",
            "The creek sounds different at night. Louder.",
            "Stars are thick tonight. Milky Way like a river.",
            "A campfire glow on the next ridge. Someone else out here.",
            "You hear footsteps in the dark. They stop when you stop.",
        ],
        "dawn": [
            "First light hits the ridge. Mist rising off the water.",
            "Birds starting up. A whole orchestra of them.",
            "The air smells like cold water and pine sap.",
            "Frost on the grass. Your breath makes clouds.",
        ],
    }
    pool = sounds.get(period, sounds["day"])
    return rng.choice(pool), "normal"


def _env_sight(engine, lmap, px, py, terrain, period, season, rng):
    # Check for real things to reference
    # Dead animals nearby?
    dead_animals = []
    for a in engine.wildlife_mgr.get_animals(
            engine.player.world_x, engine.player.world_y,
            engine.player.area_x, engine.player.area_y):
        if a.state == "dead":
            dist = max(abs(a.local_x - px), abs(a.local_y - py))
            if 5 < dist <= 25:
                dx = a.local_x - px
                dy = a.local_y - py
                d = "south" if dy > 0 else "north" if dy < 0 else ""
                d += "east" if dx > 0 else "west" if dx < 0 else ""
                dead_animals.append((a, d or "nearby"))

    if dead_animals and rng.random() < 0.6:
        animal, direction = rng.choice(dead_animals)
        return (f"Vultures circling to the {direction}. "
                f"Something's dead over there."), "advisory"

    # Check for nearby NPCs to reference
    nearby = []
    for n in engine._tile_npcs():
        if n.alive and n.present:
            dist = max(abs(n.local_x - px), abs(n.local_y - py))
            if 10 < dist <= 35:
                dx = n.local_x - px
                d = "east" if dx > 0 else "west" if dx < 0 else ""
                dy = n.local_y - py
                d2 = "south" if dy > 0 else "north" if dy < 0 else ""
                nearby.append((n, (d2 + d) or "nearby"))

    if nearby and rng.random() < 0.4:
        npc, direction = rng.choice(nearby)
        sights = [
            f"A figure moving to the {direction}. Can't tell who from here.",
            f"Movement to the {direction}. Someone on foot.",
            f"A column of smoke rises to the {direction}. Campfire.",
        ]
        return rng.choice(sights), "advisory"

    # Generic flavor sights
    sights = [
        "A cairn of stacked rocks. Trail marker, or a grave.",
        "A torn piece of fabric caught on a branch. Red flannel.",
        f"Someone carved initials into a tree trunk. '{rng.choice(list('JWTRMHSADCB'))}.{rng.choice(list('WSMBHCDKLT'))}. {rng.randint(1847, engine.time.year)}.'",
        "An empty whiskey bottle by the trail. Label from St. Louis.",
        "A rusted tin can in the brush. Sign of civilization, past or present.",
        "You spot a deer trail cutting through the undergrowth.",
    ]
    return rng.choice(sights), "normal"


def _env_weather(engine, lmap, px, py, terrain, period, season, rng):
    weather = {
        "spring": [
            "A warm breeze. Spring is settling in.",
            "Dark clouds building to the west. Rain before nightfall.",
            "Wildflowers blooming in the meadow. Purple and yellow.",
        ],
        "summer": [
            "Heat shimmer rising from the rocks. Hot today.",
            "The air is dry and still. Grasshoppers everywhere.",
            "Thunderheads piling up. Could be a storm tonight.",
        ],
        "fall": [
            "The air has that autumn bite. Leaves turning.",
            "Geese heading south in a V-formation overhead.",
            "Frost on the ground this morning. Winter's coming.",
        ],
        "winter": [
            "Your breath hangs in the air. Cold enough to freeze spit.",
            "Snow dusting the higher peaks. Won't be long now.",
            "Ice on the puddles. The creek's running slow.",
        ],
    }
    pool = weather.get(season, weather["spring"])
    return rng.choice(pool), "normal"


def _env_smell(engine, lmap, px, py, terrain, period, season, rng):
    # Check for actual nearby NPCs to make smoke/coffee smells real
    nearby_npcs = []
    for n in engine._tile_npcs():
        if n.alive and n.present:
            dist = max(abs(n.local_x - px), abs(n.local_y - py))
            if 8 < dist <= 30:
                nearby_npcs.append(n)

    if nearby_npcs and rng.random() < 0.5:
        npc = rng.choice(nearby_npcs)
        dx = npc.local_x - px
        dy = npc.local_y - py
        _DIRS = {True: {True: "southwest", False: "northwest"},
                 False: {True: "southeast", False: "northeast"}}
        if abs(dx) > abs(dy):
            dir_name = "west" if dx < 0 else "east"
        elif abs(dy) > abs(dx):
            dir_name = "south" if dy > 0 else "north"
        else:
            dir_name = _DIRS[dx < 0][dy > 0]
        smells = [
            f"Wood smoke on the wind, drifting from the {dir_name}. Someone's camp.",
            f"Coffee. Someone's brewing coffee to the {dir_name}.",
            f"Cooking smell from the {dir_name}. Camp nearby.",
        ]
        return rng.choice(smells), "advisory"

    smells = [
        "The sharp tang of pine resin. Clean air up here.",
        "Rotting leaves and wet earth. The forest floor.",
        "Something dead nearby. The smell is strong.",
        "Sage and dust. The smell of the frontier.",
        "Damp earth and minerals. The ground is rich here.",
    ]
    return rng.choice(smells), "normal"


def _find_gold_sign(engine, lmap, px, py, terrain, period, season, rng):
    signs = [
        "Black sand in the gravel. Heavy minerals — could mean gold nearby.",
        "Quartz pebbles in the creek bed. Where there's quartz, there can be gold.",
        "You notice the gravel changes color here. Darker. Worth a test pan.",
        "An old worked section of streambed — somebody panned here before. "
        "They missed a spot.",
        "Rusty iron staining on the bedrock. Mineral-rich ground.",
    ]
    # Sometimes actually boost the tile's gold grade
    if rng.random() < 0.3:
        tile = lmap.tile_at(px, py)
        tile.gold_grade = max(tile.gold_grade, rng.uniform(0.15, 0.40))
    engine.player.gain_skill_xp("geology", 1.0)
    return rng.choice(signs), "advisory"


def _find_tracks(engine, lmap, px, py, terrain, period, season, rng):
    _DIRS = {(0, -1): "north", (0, 1): "south", (-1, 0): "west", (1, 0): "east",
             (-1, -1): "northwest", (1, -1): "northeast",
             (-1, 1): "southwest", (1, 1): "southeast"}

    def _delta_to_dir(dx, dy):
        # Normalize to -1/0/1
        ndx = (1 if dx > 0 else -1 if dx < 0 else 0)
        ndy = (1 if dy > 0 else -1 if dy < 0 else 0)
        return _DIRS.get((ndx, ndy), "ahead")

    # ── Try to base tracks on REAL nearby animals ──────────────────────
    animals = engine.wildlife_mgr.get_animals(
        engine.player.world_x, engine.player.world_y,
        engine.player.area_x, engine.player.area_y)
    nearby = [(a, max(abs(a.local_x - px), abs(a.local_y - py)))
              for a in animals if a.alive]
    # Animals within 30 tiles — close enough to leave tracks
    nearby = [(a, d) for a, d in nearby if d <= 30]

    # ── Try to base tracks on REAL nearby NPCs ─────────────────────────
    npcs_near = []
    for npc in engine._tile_npcs():
        if not npc.alive or not npc.present:
            continue
        d = max(abs(npc.local_x - px), abs(npc.local_y - py))
        if d <= 30:
            npcs_near.append((npc, d))

    tracking_skill = engine.player.skills.get("tracking", 0)

    # Build candidates from real entities
    candidates = []

    # Animal tracks
    _TRACK_SPECIES = {
        "black_bear": ("bear", "Bear tracks. Big ones. Fresh."),
        "grizzly_bear": ("bear", "Grizzly tracks. Massive. The claws gouged the dirt."),
        "mule_deer": ("deer", "Deer tracks, cloven hooves in the soft ground."),
        "whitetail_deer": ("deer", "Deer tracks heading {dir}."),
        "elk": ("elk", "Elk tracks. Deep prints — a big bull."),
        "moose": ("moose", "Moose tracks. Enormous splayed prints."),
        "wolf": ("wolf", "Wolf tracks. A pack passed through here."),
        "coyote": ("coyote", "Coyote tracks, trotting along the tree line."),
        "mountain_lion": ("cougar", "Cat tracks. Big paws, no claw marks. Cougar."),
        "beaver": ("beaver", "Beaver drag marks leading to the water."),
        "bison": ("bison", "Bison tracks. A small herd came through."),
        "pronghorn": ("pronghorn", "Pronghorn tracks, light and quick in the dust."),
        "rabbit": ("rabbit", "Rabbit tracks criss-crossing the brush."),
        "wild_horse": ("horse", "Unshod hoofprints. Wild horses."),
    }
    for animal, dist in nearby:
        sid = animal.species.id if hasattr(animal.species, 'id') else ""
        if sid in _TRACK_SPECIES:
            track_type, base_msg = _TRACK_SPECIES[sid]
            dx = animal.local_x - px
            dy = animal.local_y - py
            dir_name = _delta_to_dir(dx, dy)
            msg = base_msg.replace("{dir}", dir_name)
            if "{dir}" not in base_msg and "heading" not in base_msg:
                msg += f" Heading {dir_name}."
            candidates.append((msg, track_type, dx, dy, dist, animal))

    # NPC tracks
    for npc, dist in npcs_near:
        dx = npc.local_x - px
        dy = npc.local_y - py
        dir_name = _delta_to_dir(dx, dy)
        npc_tracks = [
            (f"Fresh boot prints in the soft ground, heading {dir_name}.", "human"),
            (f"Footprints heading {dir_name}. Someone passed here recently.", "human"),
        ]
        # Native NPCs get moccasin tracks
        if hasattr(npc, 'tribe') and npc.tribe:
            npc_tracks.append(
                (f"Moccasin tracks. Light tread, heading {dir_name}.", "human"))
        msg, ttype = rng.choice(npc_tracks)
        candidates.append((msg, ttype, dx, dy, dist, npc))

    # If we have real candidates, pick one (prefer closer)
    if candidates:
        # Weight by closeness
        candidates.sort(key=lambda c: c[4])
        # Pick from closest third
        top = max(1, len(candidates) // 3 + 1)
        chosen = rng.choice(candidates[:top])
        msg, track_type, dx, dy, dist, entity = chosen

        # Tracking skill adds detail
        if tracking_skill >= 3:
            dist_ft = dist * 5
            if track_type == "human":
                msg += f" {dist_ft}ft {_delta_to_dir(dx, dy)}."
            elif track_type == "bear" or track_type == "cougar":
                msg += " Recent. Watch yourself."
            else:
                msg += f" Fresh — the animal can't be far."

        engine.player.gain_skill_xp("tracking", 1.0)
        return msg, "advisory"

    # ── Fallback: no real entities nearby — old tracks, stale sign ─────
    dx, dy = rng.choice([(-1, 0), (1, 0), (0, -1), (0, 1),
                         (-1, -1), (1, -1), (-1, 1), (1, 1)])
    dir_name = _DIRS.get((dx, dy), "ahead")
    stale = [
        f"Old tracks in the mud heading {dir_name}. Days old at least.",
        f"Faded wagon ruts heading {dir_name}. Long gone.",
        f"Animal droppings. Cold. Whatever left them moved on.",
        "A game trail, well worn. Deer or elk use this regularly.",
        f"Scuffed earth heading {dir_name}. Something passed, hard to say when.",
    ]
    engine.player.gain_skill_xp("tracking", 0.5)
    return rng.choice(stale), "normal"


def _find_item(engine, lmap, px, py, terrain, period, season, rng):
    """Occasionally find a small item on the ground."""
    from src.items import make_item
    from src.local_map import LocalTerrain

    # Terrain-specific finds
    finds = [
        ("rope_10ft", "A coil of rope, half-buried in the dirt. Still good."),
        ("rifle_ball", "A lead ball in the mud. Unfired. Somebody dropped it."),
        ("hardtack", "A tin of hardtack wedged under a rock. Still sealed."),
    ]

    # Forest: berries, mint, brush, juniper
    if terrain in (LocalTerrain.PINE, LocalTerrain.OAK, LocalTerrain.CEDAR,
                   LocalTerrain.MAPLE, LocalTerrain.CHESTNUT):
        finds.extend([
            ("wild_berries", "Berry bushes heavy with fruit. You pick a handful."),
            ("wild_berries", "Ripe berries growing along the trail."),
            ("wild_mint", "Wild mint growing near the water. You gather some."),
            ("juniper_berries", "Juniper bush with blue berries. You strip a branch."),
            ("brush_bundle", "Dry brush and bark. Useful for cordage or kindling."),
        ])

    # Near water: clay, brush, mint
    if terrain in (LocalTerrain.MUD, LocalTerrain.SAND):
        finds.extend([
            ("clay", "Thick clay in the bank. Scoop some — good for pottery."),
            ("clay", "Fine river clay. Smooth, workable."),
            ("brush_bundle", "Driftwood and brush piled against the bank."),
        ])

    # Grass/ground: brush, berries
    if terrain in (LocalTerrain.GRASS, LocalTerrain.GROUND):
        finds.extend([
            ("brush_bundle", "Dry brush. Good for cordage or fire."),
            ("wild_berries", "Low bushes with berries. You pick some."),
            ("wild_mint", "A patch of wild mint. Fresh smell."),
        ])

    # Spring/summer bonus: honey
    if season in ("spring", "summer") and rng.random() < 0.15:
        finds.append(
            ("wild_honey", "A bee tree! You smoke the hive and take a comb of honey."))

    item_id, msg = rng.choice(finds)
    try:
        item = make_item(item_id)
        tile = lmap.tile_at(px, py)
        tile.ground_items.append(item)
        engine.player.gain_skill_xp("survival", 0.5)
        return msg, "advisory"
    except Exception:
        return msg, "normal"


def _forest_event(engine, lmap, px, py, terrain, period, season, rng):
    events = [
        "A squirrel chatters angrily at you from a branch.",
        "You push through a thicket and startle a grouse. Wings thunder.",
        "A fallen tree blocks the path. Old deadfall, covered in moss.",
        "Mushrooms growing at the base of an oak. Edible? Maybe.",
        "The canopy opens into a small clearing. Sunlight pools on the ground.",
        "You find a blaze mark on a tree trunk. Someone's marked a trail.",
        "Sap oozing from a slash in a pine. Someone tapped this tree.",
    ]
    return rng.choice(events), "normal"


def _rock_event(engine, lmap, px, py, terrain, period, season, rng):
    events = [
        "A rattlesnake coiled on a sun-warmed rock. It watches you pass.",
        "Mineral veins in the exposed rock face. Worth a closer look.",
        "Loose scree shifts under your feet. Careful on this slope.",
        "A small cave opening in the rock. Dark inside.",
        "Petroglyphs on the rock face. Ancient symbols.",
    ]
    chosen = rng.choice(events)
    if "mineral" in chosen.lower():
        engine.player.gain_skill_xp("geology", 1.0)
    return chosen, "normal"


def _night_event(engine, lmap, px, py, terrain, period, season, rng):
    events = [
        "Eyes reflect in the darkness ahead. Two points of light, low to the ground. "
        "They blink, then vanish.",
        "A light on the hillside. Lantern or campfire. Gone before you can fix on it.",
        "The temperature drops suddenly. Cold air pooling in the draw.",
        "Something large moves through the brush nearby. Heavy footsteps. "
        "Then quiet.",
        "A shooting star burns across the sky. Brief and bright.",
        "You hear a man shouting in the distance. Can't make out the words.",
        "The creek sounds like voices in the dark. It's just water. Probably.",
    ]
    return rng.choice(events), "advisory"


def _dawn_event(engine, lmap, px, py, terrain, period, season, rng):
    events = [
        "Mist hangs in the trees like smoke. Everything's quiet.",
        "A deer stands motionless at the tree line. Watching you.",
        "The first rays of sun hit the water. The creek glitters.",
        "Dew heavy on the grass. Your boots are soaked already.",
    ]
    return rng.choice(events), "normal"


# ── CHAIN EVENTS — events with actual gameplay consequences ──────────────

def _find_abandoned_camp(engine, lmap, px, py, terrain, period, season, rng):
    """Find an abandoned campsite with possible loot."""
    items_found = []
    loot_roll = rng.random()
    if loot_roll < 0.3:
        items_found.append("hardtack")
        msg = ("An abandoned campsite. The fire pit is cold. "
               "You find a tin of hardtack someone left behind.")
    elif loot_roll < 0.5:
        items_found.append("rope_10ft")
        msg = ("A collapsed lean-to. Nobody's been here in weeks. "
               "A length of rope is still tied to the frame — useful.")
    elif loot_roll < 0.65:
        items_found.append("candle")
        msg = ("An old camp hidden in the brush. Ashes, a broken crate, "
               "and half a candle. Someone left in a hurry.")
    elif loot_roll < 0.75:
        # Gold dust left behind
        dust = rng.uniform(0.01, 0.05)
        engine.player.gold_oz += dust
        msg = (f"A dead prospector's camp — bedroll rotting, tools rusted. "
               f"In a leather pouch: {dust:.3f} oz of gold dust. "
               f"His bad luck is your fortune.")
    else:
        msg = ("The remains of a campfire. Boot prints leading away. "
               "Whoever was here took everything worth taking.")

    # Drop loot items
    for item_id in items_found:
        try:
            from src.items import make_item
            item = make_item(item_id)
            tile = lmap.tile_at(px, py)
            tile.ground_items.append(item)
        except Exception:
            pass

    return msg, "advisory"


def _find_prospector_note(engine, lmap, px, py, terrain, period, season, rng):
    """Find a dead prospector's journal with gold location hints."""
    directions = ["north", "south", "east", "west",
                  "upstream", "over the ridge", "past the big pine"]
    features = ["a white quartz outcrop", "a waterfall", "a fork in the creek",
                "an old lightning-struck tree", "a bedrock shelf",
                "a gravel bar shaped like a horseshoe"]
    direction = rng.choice(directions)
    feature = rng.choice(features)

    # Boost gold grade in a nearby tile cluster
    for _ in range(3):
        bx = px + rng.randint(-15, 15)
        by = py + rng.randint(-15, 15)
        if lmap.in_bounds(bx, by):
            lmap.tile_at(bx, by).gold_grade = max(
                lmap.tile_at(bx, by).gold_grade, rng.uniform(0.3, 0.7))

    engine.player.gain_skill_xp("geology", 3.0)

    msg = (f"A leather journal wedged under a rock, pages water-stained. "
           f"The last entry reads: \"Good color {direction}, near "
           f"{feature}. Going back tomorrow.\" There is no tomorrow entry.")
    return msg, "advisory"


def _encounter_injured_traveler(engine, lmap, px, py, terrain, period, season, rng):
    """Find someone hurt on the trail. Help or ignore."""
    injuries = ["a broken leg", "a rattlesnake bite", "a knife wound",
                "heatstroke", "a badly infected hand"]
    injury = rng.choice(injuries)

    # Just the discovery — player can use first aid via action menu
    engine.player.gain_skill_xp("survival", 1.0)

    msg = (f"A man lying by the trail, barely conscious. {injury.capitalize()}. "
           f"He croaks: \"Water... please.\" He's in bad shape. "
           f"You could help, or keep walking.")
    return msg, "advisory"


def _robbery_encounter(engine, lmap, px, py, terrain, period, season, rng):
    """Bandit encounter — player can lose items or fight back."""
    p = engine.player
    firearms_skill = p.skills.get("firearms", 0)
    has_weapon = any(getattr(i, "weapon_type", "") == "firearm"
                     for i in p.inventory)

    # Bandit strength varies
    bandit_type = rng.choice([
        ("a lone highwayman", 1),
        ("two road agents", 2),
        ("a desperate-looking drifter", 1),
    ])
    desc, num_bandits = bandit_type

    # Resolution based on player readiness
    if has_weapon and firearms_skill >= 5:
        # Player is armed and skilled — bandits back off
        msgs = [
            f"A figure steps out of the brush — {desc}. "
            f"\"Stand and deliver!\" Then they see your rifle. "
            f"\"...Never mind.\" They fade back into the trees.",
            f"{desc.capitalize()} blocks the trail ahead. "
            f"You draw without breaking stride. "
            f"They reconsider their life choices and let you pass.",
        ]
        p.gain_skill_xp("firearms", 2.0)
        return rng.choice(msgs), "advisory"

    elif has_weapon:
        # Armed but not skilled — tense standoff, lose some cash
        cash_lost = min(p.cash, rng.uniform(2, 10))
        p.cash -= cash_lost
        p.gain_skill_xp("firearms", 1.0)
        return (f"{desc.capitalize()} appears with a gun drawn. "
                f"\"Your money or your life.\" You pay ${cash_lost:.2f} "
                f"and walk away breathing. Could've been worse.",
                "warning")

    else:
        # Unarmed — they take what they want
        stolen_items = []
        # Take cash
        cash_lost = min(p.cash, rng.uniform(5, 25))
        p.cash -= cash_lost

        # Take a random valuable item
        valuables = sorted(
            [i for i in p.inventory if i.base_value > 1.0],
            key=lambda i: -i.base_value)
        if valuables:
            stolen = valuables[0]
            p.inventory.remove(stolen)
            stolen_items.append(stolen.name)

        # Take gold dust
        gold_lost = 0.0
        if p.gold_oz > 0.01:
            gold_lost = min(p.gold_oz, rng.uniform(0.05, 0.2))
            p.gold_oz -= gold_lost

        parts = [f"${cash_lost:.2f}"]
        if stolen_items:
            parts.append(stolen_items[0])
        if gold_lost > 0:
            parts.append(f"{gold_lost:.3f} oz gold dust")
        taken = ", ".join(parts)

        return (f"{desc.capitalize()} steps out of the darkness. "
                f"A gun in your face. \"Empty your pockets.\" "
                f"They take {taken} and disappear into the night. "
                f"You're alive. That's something.",
                "critical")


def _discover_mineral_outcrop(engine, lmap, px, py, terrain, period, season, rng):
    """Find a significant mineral deposit — boosts large area."""
    from src.local_map import LocalTerrain
    mineral = rng.choice(["quartz vein", "iron-stained rock",
                          "exposed bedrock with heavy black sand",
                          "a seam of rusty quartz"])
    # Boost gold in a 20-tile radius
    boost = rng.uniform(0.15, 0.45)
    boosted = 0
    for dy in range(-10, 11):
        for dx in range(-10, 11):
            bx, by = px + dx, py + dy
            if lmap.in_bounds(bx, by) and dx*dx + dy*dy <= 100:
                t = lmap.tile_at(bx, by)
                if t.terrain in (LocalTerrain.GRAVEL_BAR, LocalTerrain.BEDROCK,
                                  LocalTerrain.ROCK):
                    old = t.gold_grade
                    t.gold_grade = max(t.gold_grade, boost * rng.uniform(0.5, 1.0))
                    if t.gold_grade > old:
                        boosted += 1

    engine.player.gain_skill_xp("geology", 5.0)

    msg = (f"You spot {mineral} — significant mineralization. "
           f"Your geology training tells you this area could be "
           f"productive. The ground around here just got more interesting.")
    return msg, "advisory"


def _superstition_event(engine, lmap, px, py, terrain, period, season, rng):
    """Frontier prospector superstitions and omens. Pure flavor, some with
    minor mechanical effects to make them feel real."""
    events = [
        # Pure flavor
        ("A magpie lands on a rock and watches you. Old miners say "
         "one magpie means sorrow, two means gold. Just the one today.",
         "normal", None),
        ("You find a horseshoe half-buried in the trail. "
         "You hang it on your pack, open end up. Can't hurt.",
         "normal", None),
        ("A crow follows you for a quarter mile, hopping from tree to tree. "
         "Some say that's a dead man's spirit. You walk faster.",
         "normal", None),
        ("You whistle while you walk. An old prospector once told you: "
         "\"Never whistle in a mine. Bad luck.\" You stop.",
         "normal", None),
        ("Three buzzards circling overhead. Old superstition says "
         "they know something you don't. Probably just a dead coyote.",
         "normal", None),
        ("You pass a grave marker on the trail — just a board with a name "
         "and a date. 1849. You tip your hat and keep walking.",
         "normal", None),
        ("A dust devil spins across the flat ground ahead. Some Mexican "
         "miners call them 'remolinos del diablo.' You give it room.",
         "normal", None),
        ("The campfire crackles and pops. An ember jumps toward you. "
         "\"That means a stranger's coming,\" your partner would say.",
         "normal", None),
        # Minor mechanical effects
        ("A raven drops a shiny pebble at your feet and flies off. "
         "Quartz with iron staining. Good omen — or good geology.",
         "advisory", "geo_xp"),
        ("You find a coin in the creek — an old Spanish real. "
         "Some say that means gold nearby. Worth a test pan, at least.",
         "advisory", "gold_hint"),
        ("Full moon tonight. Old miners swear gold pans better "
         "under a full moon. Nonsense, probably. But you feel lucky.",
         "advisory", "luck"),
        ("You stub your toe on a rock. When you look down, "
         "it's a chunk of quartz. Sometimes bad luck turns good.",
         "advisory", "geo_xp"),
    ]

    msg, severity, effect = rng.choice(events)

    if effect == "geo_xp":
        engine.player.gain_skill_xp("geology", 1.5)
    elif effect == "gold_hint":
        # Slightly boost gold grade on current tile
        tile = lmap.tile_at(px, py)
        tile.gold_grade = max(tile.gold_grade, rng.uniform(0.1, 0.3))
    elif effect == "luck":
        # Tiny gold boost to next few tiles
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                nx, ny = px + dx, py + dy
                if lmap.in_bounds(nx, ny) and rng.random() < 0.1:
                    lmap.tile_at(nx, ny).gold_grade += 0.05

    return msg, severity


# ═══════════════════════════════════════════════════════════════════════════
#  DRUNK EVENTS — only fire when player is intoxicated
# ═══════════════════════════════════════════════════════════════════════════

def _drunk_event(engine, lmap, px, py, terrain, period, season, rng):
    """Drunk player stumbles, drops things, talks to animals, etc."""
    drunk = engine.player.survival.drunk_level

    events_mild = [  # buzzed (3-5)
        "You stumble on a root. Catch yourself. Nobody saw.",
        "You sing a half-remembered hymn. The melody is wrong but the feeling is right.",
        "Everything is funnier than it should be. You laugh at a rock.",
        "You wave at a tree stump. For a moment you thought it was a person.",
        "The stars are doing something interesting. You stop to watch.",
        "You tell a nearby bush about your plans. It's a good listener.",
        "You hum a tune you don't know the words to. It's beautiful. You think.",
        "The trail is hilarious for some reason. You can't explain why.",
        "You feel like the best prospector who ever lived. This feeling will pass.",
        "You wink at a crow. It does not wink back.",
        "You walk with exaggerated confidence. Nobody is watching.",
        "Your feet feel like they belong to someone else. A talented someone.",
        "You consider writing a letter to your mother. Better wait until sober.",
        "The sunset is the most beautiful thing you've ever seen. It's noon.",
        "You practice a speech you'll never give. The trees are impressed.",
        "You decide this is a fine country. The finest. You say so out loud.",
    ]

    events_drunk = [  # drunk (6-8)
        "You trip over your own feet and land face-first in the dirt.",
        "You try to take a shortcut and walk directly into a tree.",
        "You're pretty sure that rock just moved. It didn't. Probably.",
        "You stop to piss and almost fall in the creek.",
        "You argue with a stump about land rights. You lose the argument.",
        "You realize you've been walking in a circle for the last ten minutes.",
        "You sit down to rest your eyes. You wake up twenty minutes later in the dirt.",
        "You yell 'GOLD!' at the top of your lungs. There is no gold. A bird flies away.",
        "You try to whistle. What comes out is not a whistle.",
        "You wave at someone in the distance. It's a tree.",
        "You give a long speech about the future of this great nation. To nobody.",
        "You try to count your fingers. You get a different number each time.",
        "You pick a fight with your own shadow. Your shadow wins.",
        "You decide to swim the creek. It's ankle deep. You nearly drown.",
        "You attempt to pet a cactus. You succeed. You regret it.",
        "You carve your initials into a tree. You misspell your own name.",
        "You sit on a rock and have a profound realization. By morning you won't remember what it was.",
        "You try to start a campfire. You start it on your bedroll instead.",
        "You announce to the wilderness that you could beat any man alive. The wilderness declines to comment.",
        "You try to take off your hat. It's not on your head. You've been carrying it for an hour.",
    ]

    events_hammered = [  # hammered (9+)
        "You fall down. Getting back up takes three attempts.",
        "You throw up. You feel slightly better. Slightly.",
        "You drop your pack and don't notice for fifty feet.",
        "You challenge a mule deer to a fistfight. It walks away. You declare victory.",
        "You try to reload your rifle. You put the ball in backwards. Twice.",
        "You sit in the creek. On purpose? You're not sure anymore.",
        "You confess your sins to a pine tree. It does not grant absolution.",
        "You lose a boot. You find it on the wrong foot.",
        "You propose marriage to a boulder. It doesn't say no.",
        "You fire your rifle at the moon. The moon is unimpressed.",
        "You take off your shirt because you're 'too hot.' It's snowing.",
        "You try to ride a log. The log is not cooperative.",
        "You wake up in a bush. You don't remember the bush.",
        "You tell a detailed story to a mule. The mule walks away during the climax.",
        "You cry about something that happened when you were eleven. You can't remember what.",
        "You try to cook a rock. When it doesn't work you blame the rock.",
        "You write your will on a piece of bark. It says 'everything to the tree.'",
        "You fall asleep standing up. Gravity finds you eventually.",
        "You lose an argument with a coyote. The coyote wasn't arguing.",
        "You try to punch the ground for being too far away. The ground wins.",
    ]

    if drunk >= 9:
        msg = rng.choice(events_hammered)
        # Hammered events can drop items
        if "drop" in msg and engine.player.inventory:
            lost = rng.choice(engine.player.inventory)
            if lost.weight < 5:
                engine.player.inventory.remove(lost)
                lmap.tile_at(px, py).ground_items.append(lost)
                msg += f" Your {lost.name} is on the ground behind you."
        return msg, "advisory"
    elif drunk >= 6:
        msg = rng.choice(events_drunk)
        # Drunk trips cost time
        if "trip" in msg or "fall" in msg or "circle" in msg:
            engine.advance_time(5)
        return msg, "advisory"
    else:
        return rng.choice(events_mild), "normal"


# ═══════════════════════════════════════════════════════════════════════════
#  ANIMAL MISCHIEF — raccoons steal, bears raid, skunks spray
# ═══════════════════════════════════════════════════════════════════════════

def _animal_mischief(engine, lmap, px, py, terrain, period, season, rng):
    """Animals interact with player items, camp, and each other."""
    animals = engine.wildlife_mgr.get_animals(
        engine.player.world_x, engine.player.world_y,
        engine.player.area_x, engine.player.area_y)

    nearby = [(a, max(abs(a.local_x - px), abs(a.local_y - py)))
              for a in animals if a.alive]

    for animal, dist in nearby:
        sid = animal.species.id if hasattr(animal.species, 'id') else ""

        # Raccoon steals food from pack (within 10 tiles, night)
        if sid == "raccoon" and dist <= 10 and period in ("night", "dusk"):
            food = [i for i in engine.player.inventory
                    if getattr(i, 'nutrition', 0) > 0 and i.weight < 2]
            if food and rng.random() < 0.4:
                stolen = rng.choice(food)
                engine.player.inventory.remove(stolen)
                msgs = [
                    f"A raccoon darts out of the brush with your {stolen.name}. "
                    f"It's gone before you can react.",
                    f"You hear rustling in your pack. A fat raccoon waddles away "
                    f"with your {stolen.name} in its mouth.",
                    f"A raccoon stares you dead in the eye, grabs your {stolen.name}, "
                    f"and sprints into the darkness.",
                    f"A raccoon has your {stolen.name}. You make eye contact. "
                    f"It does not feel shame.",
                    f"Something got into your pack. Your {stolen.name} is gone. "
                    f"Tiny handprints in the mud confirm the culprit.",
                    f"A raccoon the size of a small dog drags your {stolen.name} "
                    f"under a log. You hear chewing.",
                ]
                return rng.choice(msgs), "advisory"

        # Bear investigates food smell (within 15 tiles)
        if sid in ("black_bear", "grizzly_bear") and dist <= 15:
            food_count = sum(1 for i in engine.player.inventory
                             if getattr(i, 'nutrition', 0) > 0)
            if food_count > 3 and rng.random() < 0.3:
                dir_name = _delta_to_dir(animal.local_x - px, animal.local_y - py)
                bear_name = animal.species.display_name
                msgs = [
                    f"A {bear_name} is sniffing the air to the {dir_name}. "
                    f"It smells your food.",
                    f"You hear heavy breathing to the {dir_name}. A {bear_name} "
                    f"is following the scent of your pack.",
                    f"A {bear_name} to the {dir_name} stands on its hind legs "
                    f"and tests the air. It knows you have food.",
                    f"The {bear_name} to the {dir_name} has stopped what it was doing "
                    f"and is looking directly at your pack.",
                    f"Movement to the {dir_name}. Big. Brown. Interested in you.",
                ]
                return rng.choice(msgs), "critical"

        # Skunk sprays when startled (within 3 tiles)
        if sid == "skunk" and dist <= 3:
            if rng.random() < 0.5:
                msgs = [
                    "A skunk lifts its tail. You know what comes next. "
                    "The smell is indescribable. Your eyes burn.",
                    "You step too close to a skunk. It turns around, lifts its tail, "
                    "and ruins your entire week.",
                    "SKUNK. The spray hits you square in the chest. "
                    "Every animal within a mile knows where you are now.",
                    "The skunk doesn't even look at you. It just lifts its tail "
                    "and fires. Professional.",
                    "A skunk. Three feet away. You freeze. It doesn't. "
                    "The smell will be with you for days.",
                    "You didn't see the skunk. The skunk saw you. "
                    "Your clothes may never recover.",
                ]
                engine.player.survival.warmth = max(
                    0, engine.player.survival.warmth - 5)
                return rng.choice(msgs), "advisory"

        # Moose blocks the path (within 5 tiles, doesn't move)
        if sid == "moose" and dist <= 5 and rng.random() < 0.3:
            msgs = [
                f"A moose stands in your path. It does not move. "
                f"It does not care about you. It weighs 1,200 pounds.",
                f"A bull moose looks at you with total indifference. "
                f"Going around would be wise.",
                f"A moose is eating. You exist near it. This is its only concession.",
                f"The moose doesn't move. You don't move. This could take a while.",
                f"A moose blocks the trail. It stares at you the way you stare at furniture.",
            ]
            return rng.choice(msgs), "normal"

        # Squirrel drops things on you from trees
        if sid == "ground_squirrel" and dist <= 4 and \
                terrain in (LocalTerrain.PINE, LocalTerrain.OAK,
                            LocalTerrain.CEDAR, LocalTerrain.MAPLE):
            if rng.random() < 0.3:
                msgs = [
                    "A squirrel drops a pinecone on your head. It was deliberate.",
                    "Something small and hard bounces off your hat. "
                    "A squirrel chatters angrily from the branch above.",
                    "A squirrel throws an acorn at you and misses. "
                    "It throws another one. This one hits.",
                    "A squirrel screams at you from a branch. You have trespassed "
                    "on sacred squirrel ground.",
                    "A squirrel runs down a tree trunk, chatters furiously at you, "
                    "then runs back up. Its point is unclear but strongly felt.",
                    "Something hits your shoulder. Acorn. You look up. A squirrel "
                    "is already loading another one.",
                ]
                return rng.choice(msgs), "normal"

        # Coyote follows at a distance
        if sid == "coyote" and dist <= 12 and rng.random() < 0.3:
            msgs = [
                "A coyote trots along behind you at a safe distance. "
                "It's been following for a while.",
                "You turn around. A coyote sits fifty feet back, watching. "
                "You walk. It walks. You stop. It stops.",
                "A coyote yawns at you from the hillside. It's not afraid. "
                "It's just not impressed.",
            ]
            return rng.choice(msgs), "normal"

        # Beaver chewing sounds near water
        if sid == "beaver" and dist <= 8:
            if rng.random() < 0.4:
                msgs = [
                    "The sound of gnawing. Loud, rhythmic, relentless. "
                    "A beaver is remodeling the creek.",
                    "A beaver slaps its tail on the water. CRACK. "
                    "Your heart stops for a moment.",
                    "A beaver swims past dragging a branch twice its size. "
                    "It doesn't look at you. It has work to do.",
                ]
                return rng.choice(msgs), "normal"

    # No nearby animal did anything interesting
    # General animal flavor
    generic = [
        "A vulture circles overhead. It's not for you. Probably.",
        "A crow watches you from a dead tree. It caws once. Judgment.",
        "You step in something. Best not to look.",
        "A fish jumps in the creek. It's mocking you.",
        "Two crows argue on a branch. One of them is wrong.",
        "A lizard does push-ups on a rock. Showing off.",
        "An owl stares at you from a hollow. It blinks once. Slowly.",
        "A jackrabbit bolts out of nowhere and disappears. Your heart rate takes longer.",
        "Hoofprints in the mud. Something was here. Something big. Not anymore.",
        "A woodpecker hammers a dead tree. Loudly. Persistently. Judgmentally.",
        "A hawk screams overhead. It sounds exactly like how you feel.",
        "A frog croaks from the creek. It sounds disappointed in you.",
    ]
    if rng.random() < 0.3:
        return rng.choice(generic), "normal"
    return None


def _delta_to_dir(dx, dy):
    """Helper for animal mischief direction."""
    ndx = (1 if dx > 0 else -1 if dx < 0 else 0)
    ndy = (1 if dy > 0 else -1 if dy < 0 else 0)
    _DIRS = {(0, -1): "north", (0, 1): "south", (-1, 0): "west", (1, 0): "east",
             (-1, -1): "northwest", (1, -1): "northeast",
             (-1, 1): "southwest", (1, 1): "southeast"}
    return _DIRS.get((ndx, ndy), "nearby")


# ═══════════════════════════════════════════════════════════════════════════
#  WILDFIRE EVENT — late summer/fall dry conditions
# ═══════════════════════════════════════════════════════════════════════════

def _wildfire_event(engine, lmap, px, py, terrain, period, season, rng):
    """Wildfire during dry conditions. Burns nearby terrain."""
    # Pick a direction for the fire
    fire_dir = rng.choice(["north", "south", "east", "west"])
    dx = {"north": 0, "south": 0, "east": 1, "west": -1}[fire_dir]
    dy = {"north": -1, "south": 1, "east": 0, "west": 0}[fire_dir]

    # Burn some tiles in that direction
    burned = 0
    _BURNABLE = (LocalTerrain.GRASS, LocalTerrain.BRUSH, LocalTerrain.FOREST,
                 LocalTerrain.PINE, LocalTerrain.OAK, LocalTerrain.ASPEN,
                 LocalTerrain.CEDAR, LocalTerrain.MAPLE, LocalTerrain.CHESTNUT,
                 LocalTerrain.HICKORY, LocalTerrain.JUNIPER)

    for dist in range(5, 25):
        fx = px + dx * dist + rng.randint(-3, 3)
        fy = py + dy * dist + rng.randint(-3, 3)
        if not lmap.in_bounds(fx, fy):
            continue
        ft = lmap.tiles[fy][fx].terrain
        if ft in _BURNABLE:
            lmap.tiles[fy][fx].terrain = LocalTerrain.ASH_GROUND
            burned += 1
            # Spread to adjacent
            for sy in range(-1, 2):
                for sx in range(-1, 2):
                    nx, ny = fx + sx, fy + sy
                    if lmap.in_bounds(nx, ny) and \
                            lmap.tiles[ny][nx].terrain in _BURNABLE and \
                            rng.random() < 0.4:
                        lmap.tiles[ny][nx].terrain = LocalTerrain.ASH_GROUND
                        burned += 1

    if burned > 0:
        lmap.invalidate_terrain_cache()

    msgs = [
        f"Smoke to the {fire_dir}. Wildfire. The dry brush is burning.",
        f"The smell of smoke hits you. Fire to the {fire_dir}, moving fast. "
        f"The brush crackles and pops.",
        f"A wall of smoke rises to the {fire_dir}. Wildfire. "
        f"The heat builds. Animals are running.",
    ]
    return rng.choice(msgs), "critical"
