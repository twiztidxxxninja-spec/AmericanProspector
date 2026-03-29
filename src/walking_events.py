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
    sights = [
        "A column of smoke rises from the next valley. Campfire or forest fire.",
        "Wagon tracks in the dirt. Fresh — within the last day.",
        "A cairn of stacked rocks. Trail marker, or a grave.",
        "Bootprints in the mud. Several sets, all heading the same direction.",
        "A torn piece of fabric caught on a branch. Red flannel.",
        "Someone carved initials into a tree trunk. 'J.W. 1849.'",
        "An empty whiskey bottle by the trail. Label from St. Louis.",
        "Vultures circling to the south. Something's dead over there.",
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
    smells = [
        "Wood smoke on the wind. Someone's camp, not far.",
        "The sharp tang of pine resin. Clean air up here.",
        "Rotting leaves and wet earth. The forest floor.",
        "Something dead. You don't investigate.",
        "Coffee. Someone's brewing coffee nearby.",
        "Sage and dust. The smell of the frontier.",
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
    tracks = [
        "Fresh boot prints in the soft ground. Someone passed through recently.",
        "Moccasin tracks. Light tread, heading east.",
        "Horse hooves in the mud. Shod — not wild.",
        "Bear tracks. Big ones. Fresh.",
        "Deer tracks leading to water. Game trail.",
        "Wagon wheel ruts. A heavy load passed this way.",
        "Drag marks through the dirt. Something heavy pulled toward the creek.",
    ]
    engine.player.gain_skill_xp("tracking", 1.0)
    return rng.choice(tracks), "advisory"


def _find_item(engine, lmap, px, py, terrain, period, season, rng):
    """Occasionally find a small item on the ground."""
    from src.items import make_item
    finds = [
        ("rope_10ft", "A coil of rope, half-buried in the dirt. Still good."),
        ("rifle_ball", "A lead ball in the mud. Unfired. Somebody dropped it."),
        ("hardtack", "A tin of hardtack wedged under a rock. Still sealed."),
    ]
    item_id, msg = rng.choice(finds)
    try:
        item = make_item(item_id)
        tile = lmap.tile_at(px, py)
        tile.ground_items.append(item)
        return msg + " [P] to pick up.", "advisory"
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
    if "mineral" in rng.choice(events).lower():
        engine.player.gain_skill_xp("geology", 1.0)
    return rng.choice(events), "normal"


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
