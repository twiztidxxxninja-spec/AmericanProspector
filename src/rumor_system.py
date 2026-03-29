"""
src/rumor_system.py

Generates map-grounded rumors from real world tile data.
Every rumor references an actual world coordinate derived from
gold_bias, terrain, and known locations near the player.

Specificity scales with NPC relationship and knowledge:
  vague       — direction only, no map reveal
  directional — area + distance, small fog-of-war reveal
  specific    — named landmark, full reveal + journal place note
"""

import random
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.world_map import WorldMap
    from src.npc import NPC
    from src.player import Player


# ── Rumor result ───────────────────────────────────────────────────────────────

@dataclass
class Rumor:
    text:             str             # what the NPC says out loud
    wx:               int  = -1       # world tile X (-1 = truly vague)
    wy:               int  = -1       # world tile Y (-1 = truly vague)
    category:         str  = "gold"   # gold | location | water | trail | danger
    specificity:      str  = "vague"  # vague | directional | specific
    reveal_radius:    int  = 0        # tiles of fog to lift (0 = none)
    journal_text:     str  = ""       # added to Rumors tab (empty = skip)
    place_name:       str  = ""       # added to Places tab (empty = skip)


# ── Direction / distance helpers ───────────────────────────────────────────────

def _dir(dx: int, dy: int) -> str:
    ax, ay = abs(dx), abs(dy)
    if ax < 1 and ay < 1:
        return "right here"
    if ax > ay * 2:
        return "east" if dx > 0 else "west"
    if ay > ax * 2:
        return "south" if dy > 0 else "north"
    if dx > 0:
        return "southeast" if dy > 0 else "northeast"
    return "southwest" if dy > 0 else "northwest"


def _dist_text(tiles: int) -> str:
    miles = tiles * 5
    if miles < 15:   return "just a short ways"
    if miles < 40:   return "about a day's ride"
    if miles < 80:   return "two days out"
    if miles < 150:  return "three or four days"
    return "a good week's travel"


def _terrain_phrase(terrain: int) -> str:
    from src.world_map import Terrain
    return {
        Terrain.MOUNTAINS: "up in the mountains",
        Terrain.HILLS:     "in the hill country",
        Terrain.RIVER:     "along the river",
        Terrain.FOREST:    "back in the timber",
        Terrain.CONIFER:   "deep in the pines",
        Terrain.DESERT:    "out in the desert",
        Terrain.PLAINS:    "on the flats",
        Terrain.PRAIRIE:   "out on the prairie",
        Terrain.SCRUB:     "in the scrublands",
        Terrain.SWAMP:     "in the swamp country",
        Terrain.COAST:     "near the coast",
    }.get(terrain, "out there")


# Deterministic creek/place name from coordinates
_CREEK_FIRST = ["Bear", "Willow", "Clear", "Dry", "Slate", "Lost", "Cold",
                "Copper", "Silver", "Dead", "Pine", "Blue", "Gravel", "Eagle"]
_CREEK_LAST  = ["Creek", "Fork", "Run", "Branch", "Draw", "Gulch", "Wash",
                "Canyon", "Ravine", "Hollow"]
_PEAK_NAMES  = ["Bald", "Black", "Red", "Lone", "Broken", "Thunder", "Iron",
                "Copper", "Table", "Sentinel"]

def _place_name_from_coords(wx: int, wy: int, terrain: int) -> str:
    from src.world_map import Terrain
    seed = wx * 7919 + wy * 6271
    rng  = random.Random(seed)
    if terrain in (Terrain.MOUNTAINS, Terrain.HILLS):
        return f"{rng.choice(_PEAK_NAMES)} Peak"
    return f"{rng.choice(_CREEK_FIRST)} {rng.choice(_CREEK_LAST)}"


# ── NPC occupation → preferred rumor categories ───────────────────────────────

# ── Event rumor categories (create situations when visited) ──────────────────

# These are rumors that generate an encounter/situation at the referenced tile.
# When the player visits, the dynamic location system spawns the scenario.
EVENT_CATEGORIES = [
    # Violence / danger
    "bandits", "claim_jumpers", "bounty", "duel_challenge", "rustlers",
    "ambush_site", "feuding_camps", "lynch_mob",
    # Opportunity (good)
    "lost_traveler", "abandoned_claim", "wagon_wreck", "rich_strike",
    "stolen_goods", "sick_camp", "stranded_family", "injured_miner",
    # Commerce / social
    "card_game", "horse_sale", "traveling_preacher", "medicine_show",
    "auction", "land_dispute",
    # Mystery / exploration
    "cave_entrance", "old_bones", "native_artifacts", "ghost_camp",
    "hidden_spring", "prospector_journal",
    # Outlaw opportunities
    "unguarded_shipment", "corrupt_official", "moonshine_still",
    "counterfeiter",
]

_OCC_CATEGORIES = {
    "prospector":   ["gold", "gold", "gold", "water", "abandoned_claim", "claim_jumpers",
                     "rich_strike", "prospector_journal", "cave_entrance"],
    "miner":        ["gold", "gold", "gold", "trail", "rich_strike", "claim_jumpers",
                     "injured_miner", "cave_entrance", "feuding_camps"],
    "assayer":      ["gold", "gold", "location", "gold", "rich_strike", "counterfeiter"],
    "trader":       ["location", "trail", "gold", "wagon_wreck", "stolen_goods",
                     "horse_sale", "auction", "unguarded_shipment"],
    "merchant":     ["location", "trail", "danger", "stolen_goods", "bandits",
                     "auction", "medicine_show", "horse_sale"],
    "trapper":      ["water", "trail", "gold", "danger", "lost_traveler",
                     "hidden_spring", "old_bones", "cave_entrance"],
    "hunter":       ["water", "trail", "danger", "gold", "lost_traveler",
                     "bounty", "ambush_site", "native_artifacts"],
    "scout":        ["trail", "location", "water", "danger", "bandits",
                     "wagon_wreck", "ghost_camp", "stranded_family", "hidden_spring"],
    "farmer":       ["water", "location", "trail", "gold", "rustlers",
                     "land_dispute", "stranded_family", "traveling_preacher"],
    "rancher":      ["water", "trail", "location", "danger", "rustlers", "rustlers",
                     "horse_sale", "land_dispute", "feuding_camps"],
    "sheriff":      ["danger", "location", "trail", "bandits", "bounty",
                     "duel_challenge", "lynch_mob", "rustlers", "moonshine_still",
                     "corrupt_official", "counterfeiter"],
    "lawman":       ["danger", "location", "trail", "bandits", "bounty",
                     "lynch_mob", "corrupt_official"],
    "bartender":    ["gold", "location", "danger", "card_game", "duel_challenge",
                     "bandits", "moonshine_still", "medicine_show", "bounty",
                     "feuding_camps", "ghost_camp"],
    "engineer":     ["trail", "location", "gold", "water", "cave_entrance",
                     "land_dispute"],
    "doctor":       ["danger", "location", "water", "trail", "sick_camp",
                     "injured_miner", "medicine_show"],
    "preacher":     ["traveling_preacher", "sick_camp", "lost_traveler",
                     "stranded_family", "lynch_mob", "ghost_camp"],
}
_DEFAULT_CATS = ["gold", "location", "trail", "water", "bandits", "lost_traveler",
                 "abandoned_claim", "card_game"]


def _pick_category(npc: "NPC", rng: random.Random) -> str:
    occ  = npc.occupation.lower()
    cats = _OCC_CATEGORIES.get(occ, _DEFAULT_CATS)
    # Knowledge boosts: geology/placer → gold; law → danger; etc.
    if any(k in npc.knowledge for k in ("geology", "placer", "hardRock", "assaying")):
        cats = ["gold"] + cats
    if "law" in npc.knowledge:
        cats = ["danger"] + cats
    return rng.choice(cats)


# ── Tile finders ───────────────────────────────────────────────────────────────

def _find_gold_tile(player: "Player", world_map: "WorldMap",
                    rng: random.Random,
                    search_radius: int = 30) -> Optional[Tuple[int, int]]:
    """Find a high gold-bias tile the player hasn't visited."""
    px, py = player.world_x, player.world_y
    candidates = []
    for dy in range(-search_radius, search_radius + 1):
        for dx in range(-search_radius, search_radius + 1):
            wx, wy = px + dx, py + dy
            if not world_map.in_bounds(wx, wy):
                continue
            if world_map.visited[wy, wx]:
                continue
            from src.world_map import Terrain
            terrain = int(world_map.tiles[wy, wx])
            if terrain == Terrain.OCEAN:
                continue
            bias = float(world_map.gold_bias[wy, wx])
            dist = max(abs(dx), abs(dy))
            if bias > 0.3 and dist > 3:
                candidates.append((bias - dist * 0.01, wx, wy))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    # Pick from top 5 with some randomness
    top = candidates[:min(5, len(candidates))]
    _, wx, wy = rng.choice(top)
    return wx, wy


def _find_location_tile(player: "Player", world_map: "WorldMap",
                        rng: random.Random) -> Optional[Tuple[int, int]]:
    """Point toward a known location (town) or interesting terrain feature."""
    px, py = player.world_x, player.world_y
    # Known locations first
    locs = [loc for loc in world_map.locations.values()
            if not loc.discovered]
    if locs:
        loc = rng.choice(locs)
        return loc.x, loc.y
    # Fall back to a river or mountain tile
    from src.world_map import Terrain
    interesting = [Terrain.RIVER, Terrain.MOUNTAINS, Terrain.COAST]
    candidates  = []
    for dy in range(-40, 41):
        for dx in range(-40, 41):
            wx, wy = px + dx, py + dy
            if not world_map.in_bounds(wx, wy):
                continue
            if world_map.visited[wy, wx]:
                continue
            if int(world_map.tiles[wy, wx]) in interesting and max(abs(dx), abs(dy)) > 5:
                candidates.append((wx, wy))
    if candidates:
        return rng.choice(candidates)
    return None


def _find_water_tile(player: "Player", world_map: "WorldMap",
                     rng: random.Random) -> Optional[Tuple[int, int]]:
    """Find an unvisited river or water-adjacent tile."""
    from src.world_map import Terrain
    px, py = player.world_x, player.world_y
    candidates = []
    for dy in range(-25, 26):
        for dx in range(-25, 26):
            wx, wy = px + dx, py + dy
            if not world_map.in_bounds(wx, wy):
                continue
            if int(world_map.tiles[wy, wx]) == Terrain.RIVER and max(abs(dx), abs(dy)) > 4:
                candidates.append((wx, wy))
    return rng.choice(candidates) if candidates else None


def _find_danger_tile(player: "Player", world_map: "WorldMap",
                      rng: random.Random) -> Optional[Tuple[int, int]]:
    """Find a difficult-terrain tile to warn about."""
    from src.world_map import Terrain
    px, py = player.world_x, player.world_y
    hard   = [Terrain.MOUNTAINS, Terrain.DESERT, Terrain.SWAMP]
    candidates = []
    for dy in range(-20, 21):
        for dx in range(-20, 21):
            wx, wy = px + dx, py + dy
            if not world_map.in_bounds(wx, wy):
                continue
            if int(world_map.tiles[wy, wx]) in hard and max(abs(dx), abs(dy)) > 5:
                candidates.append((wx, wy))
    return rng.choice(candidates) if candidates else None


# ── Text builders ──────────────────────────────────────────────────────────────

def _gold_rumor_text(dx: int, dy: int, dist: int,
                     terrain: int, place: str, spec: str) -> str:
    direction  = _dir(dx, dy)
    dist_txt   = _dist_text(dist)
    terr_txt   = _terrain_phrase(terrain)

    if spec == "vague":
        options = [
            f"Heard there's color {direction} of here. Couldn't say exactly where.",
            f"Men are talking about something {direction}. Gold, maybe. Nobody's saying much.",
            f"Somebody came back with dust in their poke. Headed {direction} when they left.",
            f"Word is there's pay dirt {direction}. Take it for what it's worth.",
        ]
    elif spec == "directional":
        options = [
            f"{dist_txt} {direction}, {terr_txt}. Fellow I know pulled good color there last season.",
            f"There's a creek {direction} of here, {dist_txt} out. Worth panning if you get the chance.",
            f"{dist_txt} {direction} — {terr_txt}. Saw color in the gravel bars myself, passing through.",
            f"Old worked ground {direction}, {dist_txt}. Whoever was there left in a hurry. Might still be color.",
        ]
    else:  # specific
        options = [
            f"{place}, {dist_txt} {direction}. Coarse gold in the black sand, inside the big bend. "
            f"I pulled two ounces off that bar two seasons back.",
            f"You want gold, go to {place} — {dist_txt} {direction}. Float gold in the gravel, "
            f"bedrock crevices packed tight. Don't tell everyone.",
            f"{dist_txt} {direction} — {place}. The color runs fine but there's a lot of it. "
            f"You'll need to work a bar for a week minimum, but it pays.",
        ]
    return random.choice(options)


def _location_rumor_text(dx: int, dy: int, dist: int,
                         terrain: int, place: str, spec: str,
                         loc_name: str = "") -> str:
    direction = _dir(dx, dy)
    dist_txt  = _dist_text(dist)
    terr_txt  = _terrain_phrase(terrain)
    name_str  = loc_name if loc_name else place

    if spec == "vague":
        options = [
            f"There's a settlement {direction} of here somewhere. Don't know much about it.",
            f"Heard there's a trading post {direction}. Couldn't tell you how far.",
        ]
    elif spec == "directional":
        options = [
            f"{dist_txt} {direction} there's a camp. Supply prices are decent, from what I hear.",
            f"Town {direction}, {dist_txt}. Small, but they've got an assay office.",
            f"There's a river crossing {direction}, {dist_txt} out — {terr_txt}. "
            f"Fellow runs a ferry there.",
        ]
    else:
        options = [
            f"{name_str} is {dist_txt} {direction}. They've got a store, a saloon, and "
            f"a blacksmith last I checked.",
            f"Follow the trail {direction}, {dist_txt} — you'll hit {name_str}. "
            f"Tell them I sent you.",
        ]
    return random.choice(options)


def _water_rumor_text(dx: int, dy: int, dist: int, spec: str, place: str) -> str:
    direction = _dir(dx, dy)
    dist_txt  = _dist_text(dist)
    if spec == "vague":
        return (f"There's water {direction} of here, somewhere. In this country "
                f"that's worth knowing.")
    if spec == "directional":
        return (f"River {direction}, {dist_txt} out. Good water, runs year-round "
                f"far as I know.")
    return (f"{place} runs clear {dist_txt} {direction}. "
            f"Spring-fed — never goes dry, not even in August.")


def _danger_rumor_text(dx: int, dy: int, dist: int,
                       terrain: int, spec: str) -> str:
    direction = _dir(dx, dy)
    dist_txt  = _dist_text(dist)
    terr_txt  = _terrain_phrase(terrain)
    if spec == "vague":
        return f"Watch yourself {direction} of here. Lost a man that way last summer."
    if spec == "directional":
        return (f"{dist_txt} {direction}, {terr_txt} — rough country. "
                f"Men have come back short a horse, or not at all.")
    return (f"{terr_txt}, {dist_txt} {direction}. "
            f"Passes close in by November. Don't get caught in there late in the season.")


def _find_event_tile(player: "Player", world_map: "WorldMap",
                     rng: random.Random) -> Optional[Tuple[int, int]]:
    """Find a suitable tile for an event rumor (5-25 tiles away, not ocean)."""
    from src.world_map import Terrain
    px, py = player.world_x, player.world_y
    candidates = []
    for dy in range(-25, 26):
        for dx in range(-25, 26):
            wx, wy = px + dx, py + dy
            if not world_map.in_bounds(wx, wy):
                continue
            dist = max(abs(dx), abs(dy))
            if dist < 5 or dist > 25:
                continue
            terrain = int(world_map.tiles[wy, wx])
            if terrain == Terrain.OCEAN:
                continue
            candidates.append((wx, wy))
    if candidates:
        return rng.choice(candidates)
    return None


# ── Event rumor text builders ──────────────────────────────────────────────────

def _event_rumor_text(category: str, dx: int, dy: int, dist: int,
                      terrain: int, place: str, spec: str,
                      rng: random.Random) -> str:
    direction = _dir(dx, dy)
    dist_txt = _dist_text(dist)
    terr_txt = _terrain_phrase(terrain)

    _TEMPLATES = {
        "bandits": [
            f"Road agents working {direction} of here. Three men, armed. They hit a wagon last week.",
            f"Watch the trail {direction}, {dist_txt} out. Bandits jumped two miners there.",
            f"Heard gunshots {direction} last Tuesday. Somebody found a body near {place}.",
            f"There's a gang camped {terr_txt}, {dist_txt} {direction}. They're robbing anyone who passes.",
        ],
        "claim_jumpers": [
            f"Man named Harlan staked over somebody's claim near {place}. The original prospector ain't happy.",
            f"Claim dispute {direction}, {dist_txt} out. Two parties both say it's theirs. Could get bloody.",
            f"Somebody's been working another man's ground near {place}. Word is they're armed.",
            f"There's trouble at {place} — claim jumpers moved in while the owner went to town for supplies.",
        ],
        "lost_traveler": [
            f"Family went {direction} two weeks back. Nobody's seen 'em since. Wagon and all.",
            f"Old man wandered off from camp {direction} of here. Probably lost in the hills.",
            f"A woman came through asking about her husband. He went prospecting {direction} and didn't come back.",
            f"Some greenhorn from back East headed {direction} alone. No supplies, no sense. Probably dead.",
        ],
        "abandoned_claim": [
            f"There's a worked claim near {place}, {dist_txt} {direction}. Owner took sick and left. "
            f"Might still be color there.",
            f"Fellow packed up and left his diggings near {place}. Sluice box still standing.",
            f"Abandoned camp {direction}, {dist_txt}. Tools scattered, tent still up. Don't know what happened.",
        ],
        "wagon_wreck": [
            f"Wagon broke an axle {direction} of here, {dist_txt} out. Driver couldn't save the load.",
            f"Supply wagon turned over near {place}. Goods scattered everywhere. First come, first serve.",
            f"Heard there's a wrecked freight wagon {direction}. Supplies for the taking, if you get there first.",
        ],
        "bounty": [
            f"Sheriff's offering twenty dollars for a man called Slade. Last seen heading {direction}.",
            f"There's paper on a horse thief {direction} of here. Fifty dollar reward, dead or alive.",
            f"Wanted man hiding out near {place}. Law's too busy to chase him. Could be money in it.",
        ],
        "rustlers": [
            f"Cattle going missing {direction} of here. Ranchers are getting organized.",
            f"Horse thieves working the area near {place}. Somebody's gonna get hung.",
            f"Livestock disappearing {direction}, {dist_txt}. Trail leads {terr_txt}.",
        ],
        "sick_camp": [
            f"Camp {direction} of here got the cholera. Nobody goes near it now.",
            f"Miners at {place} are down sick. Could be bad water, could be worse.",
            f"There's a fever camp {direction}, {dist_txt}. They need medicine and clean water.",
        ],
        "rich_strike": [
            f"Somebody pulled a two-pound nugget out of {place}. Men are heading there now.",
            f"New strike {direction}, {dist_txt} — coarse gold on the surface. Won't last long.",
            f"They're finding gold by the handful near {place}. By the time you get there it'll be staked.",
        ],
        "card_game": [
            f"Big stakes poker game at {place}. Three hundred dollars on the table last I heard.",
            f"Miners up at {place} play cards every Saturday. High stakes if you've got the nerve.",
            f"A gambler at {place} has been cleaning everyone out. Somebody needs to take him down a peg.",
        ],
        "duel_challenge": [
            f"Man at {place} says he'll fight anyone who calls him a cheat. He means it.",
            f"Two men arguing over a claim near {place}. They've agreed to settle it with pistols.",
            f"Heard a prospector near {place} challenged the whole camp. Says his gun speaks for him.",
        ],
        "stolen_goods": [
            f"Somebody robbed the supply train {direction} of here. Goods hidden {terr_txt} somewhere.",
            f"Stolen merchandise cached near {place}. Trader's offering a cut to anyone who finds it.",
            f"A thief stashed what he took {direction}, {dist_txt}. Find it and it's yours — or return it for the reward.",
        ],
    }

    _TEMPLATES_2 = {
        "ambush_site": [
            f"Two men got shot from the rocks near {place}. Somebody's set up a kill box.",
            f"Found blood and shell casings {direction}, {dist_txt}. Ambush spot.",
            f"Trail near {place} has been quiet. Too quiet. Smart men go around.",
        ],
        "feuding_camps": [
            f"Two camps near {place} been shooting at each other all week over water rights.",
            f"Bad blood between miners {direction} of here. One camp says the other poisoned the stream.",
            f"Feud {direction}, {dist_txt}. Started over a woman. Now it's about pride and bullets.",
        ],
        "lynch_mob": [
            f"Miners near {place} strung up a man for claim jumping. Didn't wait for a trial.",
            f"Mob justice {direction}. They caught a horse thief and dealt with him frontier-style.",
            f"Vigilance committee at {place} is hanging people. Some deserved it. Some didn't.",
        ],
        "stranded_family": [
            f"Family with children stuck {direction}, {dist_txt}. Wagon axle broke, father's hurt.",
            f"Woman and three kids camped near {place}. Husband went for help and never came back.",
            f"Emigrants ran out of water {direction}. Somebody ought to bring them a canteen.",
        ],
        "injured_miner": [
            f"Miner got his leg crushed in a cave-in near {place}. Can't walk.",
            f"Fellow {direction} fell down a shaft. Broken bones, nobody to help.",
            f"Man at {place} got bit by a rattlesnake. Needs medicine bad.",
        ],
        "horse_sale": [
            f"Man near {place} selling horses cheap. Moving back East, needs cash quick.",
            f"Good mules for sale {direction}, {dist_txt}. Former army stock.",
            f"Horse trader at {place} has pack animals. Fair prices if you haggle.",
        ],
        "traveling_preacher": [
            f"Circuit preacher setting up {direction}. Doing marriages, funerals, the works.",
            f"Reverend at {place} is collecting for a church. Also patches wounds if you're hurt.",
            f"Preacher {direction} says he'll pray over your claim for a dollar. Worth a shot.",
        ],
        "medicine_show": [
            f"Traveling medicine show near {place}. Cure-all tonics. Most of it's whiskey.",
            f"Doc with a wagon {direction} selling patent medicine. Some of it actually works.",
            f"Snake oil salesman at {place}. But he's also got real laudanum and bandages.",
        ],
        "auction": [
            f"Dead man's goods being auctioned at {place}. Mining equipment, tools, the works.",
            f"Estate sale {direction}. Entire claim operation — sluice, tools, cabin — going cheap.",
            f"Foreclosure auction near {place}. Bank's selling everything. Good deals to be had.",
        ],
        "land_dispute": [
            f"Two families fighting over a parcel near {place}. County line runs right through it.",
            f"Land dispute {direction}. Both men have papers. Somebody forged something.",
            f"Squatter at {place} won't move. Legal owner's looking for help.",
        ],
        "cave_entrance": [
            f"Found a cave {direction}, {dist_txt}. Goes deep. Might be silver in those rocks.",
            f"Opening in the hillside near {place}. Nobody's explored it yet.",
            f"Cave {direction} that the Indians avoided. Old timers say there's ore in there.",
        ],
        "old_bones": [
            f"Somebody found bones near {place}. Old ones. Indian burial, maybe.",
            f"Human skeleton {direction}, half-buried. Still wearing a gold watch.",
            f"Bones and a rusted rifle {direction}, {dist_txt}. Been there years. Wonder what happened.",
        ],
        "native_artifacts": [
            f"Arrowheads and pottery near {place}. Old camp site, long abandoned.",
            f"Found carvings on the rocks {direction}. Ancient. Nobody knows who made them.",
            f"Indian trail markers {direction}. Follow them and you find water every time.",
        ],
        "ghost_camp": [
            f"Camp near {place} — everything still set up. Food on the table. Nobody there. "
            f"Clothes hanging on the line.",
            f"Ghost camp {direction}. Twelve tents, no people. Tools in the ground mid-dig.",
            f"Place near {place} the Indians call cursed. Three different groups tried to work it. "
            f"All left in the night.",
        ],
        "hidden_spring": [
            f"Spring-fed pool {direction}, {dist_txt}. Crystal clear, never dries up.",
            f"Hidden water source near {place}. In the rocks, hard to find unless you know.",
            f"Natural spring {direction}. Good water, shady spot. Nobody's claimed it.",
        ],
        "prospector_journal": [
            f"Found a dead man's journal near {place}. Last entry says he found the mother lode "
            f"but couldn't carry it out alone.",
            f"Old prospector's diary {direction}. Maps and notes about a vein he never worked.",
            f"Pages scattered in an abandoned tent near {place}. Somebody was tracking gold deposits. "
            f"Detailed notes.",
        ],
        "unguarded_shipment": [
            f"Supply wagon broke down {direction}. Driver went for help. Goods just sitting there.",
            f"Gold shipment coming through {place} next week. Only two guards.",
            f"Payroll wagon {direction}, {dist_txt}. Thin escort. Just saying.",
        ],
        "corrupt_official": [
            f"Assayer at {place} is shaving weights. Cheating every miner who walks in.",
            f"Land office clerk {direction} is selling claims that aren't his to sell.",
            f"Sheriff near {place} is in the pocket of a mining company. Justice ain't blind there — it's bought.",
        ],
        "moonshine_still": [
            f"Somebody's running a still {direction}, {dist_txt}. Good whiskey if you can find it.",
            f"Moonshine operation {terr_txt} near {place}. They don't take kindly to visitors.",
            f"Illegal spirits {direction}. The law doesn't go out that far. Profitable if you're discrete.",
        ],
        "counterfeiter": [
            f"Bad coins circulating near {place}. Somebody's making them.",
            f"Counterfeiter working {direction}. Gold-plated lead. Been fooling merchants.",
            f"Fake gold dust mixed with brass filings turning up at {place}. Assayer caught it.",
        ],
    }

    all_templates = {**_TEMPLATES, **_TEMPLATES_2}
    templates = all_templates.get(category, all_templates.get("bandits"))
    return rng.choice(templates)


# ── Main entry point ───────────────────────────────────────────────────────────

def generate_rumor(player: "Player", npc: "NPC",
                   world_map: "WorldMap",
                   rng: Optional[random.Random] = None) -> Rumor:
    """
    Generate one map-grounded rumor. Called when player asks an NPC about rumors.
    Returns a Rumor with text, coordinates, and reveal/journal metadata.
    """
    if rng is None:
        rng = random.Random()

    if world_map is None:
        return Rumor(
            text="\"I got nothing for you. Ask someone else.\"",
            category="none", specificity="vague",
        )

    rel = npc.relationship

    # Specificity by relationship + NPC knowledge depth
    npc_knows_topic = bool(npc.knowledge)
    if rel < 5:
        spec = "vague"
    elif rel < 30 or not npc_knows_topic:
        spec = "directional"
    else:
        spec = "specific"

    category = _pick_category(npc, rng)

    # Find reference tile
    tile: Optional[Tuple[int, int]] = None
    if category == "gold" or category == "rich_strike":
        tile = _find_gold_tile(player, world_map, rng)
    elif category == "location":
        tile = _find_location_tile(player, world_map, rng)
    elif category == "water":
        tile = _find_water_tile(player, world_map, rng)
    elif category == "danger":
        tile = _find_danger_tile(player, world_map, rng)
    elif category in EVENT_CATEGORIES:
        # Event rumors: find any unvisited passable tile at moderate distance
        tile = _find_event_tile(player, world_map, rng)

    # Fall back to gold if the specific finder came up empty
    if tile is None:
        tile = _find_gold_tile(player, world_map, rng, search_radius=50)
    if tile is None:
        # Truly nothing found — return a generic atmospheric rumor
        return Rumor(
            text=rng.choice([
                "\"Quiet lately. Nothing much moving out there.\"",
                "\"Been a slow season. Ask someone who's been farther out than me.\"",
                "\"I got nothing for you. Talk to the assayer.\"",
            ]),
            category="none",
            specificity="vague",
        )

    wx, wy   = tile
    dx, dy   = wx - player.world_x, wy - player.world_y
    dist     = max(abs(dx), abs(dy))
    terrain  = int(world_map.tiles[wy, wx])
    place    = _place_name_from_coords(wx, wy, terrain)

    # Known location name override
    loc_obj  = world_map.get_location_at(wx, wy)
    loc_name = loc_obj.name if loc_obj else ""

    # Build text
    if category in EVENT_CATEGORIES:
        text = _event_rumor_text(category, dx, dy, dist, terrain, place, spec, rng)
    elif category == "gold":
        text = _gold_rumor_text(dx, dy, dist, terrain, place, spec)
    elif category == "location":
        text = _location_rumor_text(dx, dy, dist, terrain, place, spec, loc_name)
    elif category == "water":
        text = _water_rumor_text(dx, dy, dist, spec, place)
    else:
        text = _danger_rumor_text(dx, dy, dist, terrain, spec)

    # Map reveal radius
    reveal = {"vague": 0, "directional": 3, "specific": 6}.get(spec, 0)

    # Journal text and place note
    direction = _dir(dx, dy)
    display = loc_name or place

    # Event category label for journal
    _EVENT_LABELS = {
        "bandits": "Bandits reported", "claim_jumpers": "Claim dispute",
        "lost_traveler": "Missing person", "abandoned_claim": "Abandoned claim",
        "wagon_wreck": "Wagon wreck", "bounty": "Bounty",
        "rustlers": "Rustlers", "sick_camp": "Sick camp",
        "rich_strike": "Rich strike", "card_game": "Card game",
        "duel_challenge": "Duel", "stolen_goods": "Stolen goods",
    }

    if spec == "vague":
        j_text = f"{npc.name}: \"{text.strip('\"')}\""
        p_name = ""
    elif spec == "directional":
        label = _EVENT_LABELS.get(category, category.capitalize())
        j_text = (f"{npc.name}: {label} {_dist_text(dist)} "
                  f"{direction}. Unverified.")
        p_name = ""
    else:
        label = _EVENT_LABELS.get(category, category.capitalize())
        j_text = (f"{npc.name} told me about {display} — "
                  f"{_dist_text(dist)} {direction}. "
                  f"{label}. Worth investigating.")
        p_name = display

    return Rumor(
        text=f"\"{text.strip('\"')}\"",
        wx=wx, wy=wy,
        category=category,
        specificity=spec,
        reveal_radius=reveal,
        journal_text=j_text,
        place_name=p_name,
    )
