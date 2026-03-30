"""
src/settlement_events.py

Random events that happen in towns and settlements — things the player
witnesses, hears about, or is affected by while present.

Called from engine daily tick when player is at a settlement.
Events range from atmospheric flavor to gameplay-affecting incidents.

Two categories:
    1. Ambient events — flavor text, no state change
    2. Active events — modify NPCs, prices, reputation, spawn items, etc.
"""

import random
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine import Engine

# ============================================================================
#  SETTLEMENT EVENT
# ============================================================================

@dataclass
class SettlementEvent:
    """Result of a settlement event roll."""
    message: str
    severity: str = "normal"        # normal, advisory, warning, critical
    # Optional gameplay effects
    reputation_delta: float = 0.0   # player reputation change
    price_mult: float = 1.0         # temporary price multiplier
    price_duration: int = 0         # days the price effect lasts
    npc_spawned: str = ""           # NPC type to spawn
    item_spawned: str = ""          # item to drop near player
    cash_delta: float = 0.0         # direct cash gain/loss
    health_delta: float = 0.0       # survival health change
    law_alert: bool = False         # triggers law enforcement attention


# ============================================================================
#  EVENT CHANCE
# ============================================================================

# Base chance per day of an event firing (by settlement type)
EVENT_CHANCE: Dict[str, float] = {
    "mining_camp_small":  0.30,   # small camps — things happen constantly
    "mining_camp_medium": 0.35,
    "boomtown":           0.45,   # boomtowns are chaotic
    "small_town":         0.25,
    "trading_post":       0.20,
    "city":               0.40,   # cities have lots going on
}


# ============================================================================
#  EVENT POOLS — organized by category
# ============================================================================
# Each entry: (message_template, severity, weight, effects_dict)
# message_template can use {settlement}, {npc_name}, {year}

# ── SALOON & SOCIAL ──────────────────────────────────────────────────────

_SALOON_EVENTS = [
    ("A fistfight breaks out in the saloon. Chairs fly. "
     "The barkeep pulls a shotgun and everyone settles down.",
     "normal", 10, {}),

    ("Two miners argue over a card game. One accuses the other of cheating. "
     "Knives come out before the sheriff steps in.",
     "normal", 8, {}),

    ("A drunk prospector staggers out of the saloon yelling "
     "about a \"mother lode\" up in the hills. Nobody believes him.",
     "normal", 8, {}),

    ("Someone is playing a fiddle in the saloon tonight. "
     "The whole town seems to have gathered to listen.",
     "normal", 6, {}),

    ("A traveling showman has set up in the saloon — card tricks, "
     "fortune telling, and \"genuine Egyptian mysteries.\"",
     "normal", 5, {}),

    ("The saloon has run dry. No whiskey for a week, they say. "
     "Men are drinking coffee and looking miserable.",
     "advisory", 4, {"price_mult": 1.5, "price_duration": 7}),

    ("A woman walks into the saloon and the whole room goes quiet. "
     "Turns out she's looking for her husband. He's under a table.",
     "normal", 5, {}),

    ("Gambling fever tonight. A miner just lost his entire claim "
     "on a hand of faro. He sits on the porch staring at nothing.",
     "normal", 6, {}),

    ("A stranger buys drinks for the whole saloon. People are suspicious "
     "but not suspicious enough to refuse free whiskey.",
     "normal", 5, {}),

    ("The piano player quit. The saloon owner is offering $2/day "
     "for anyone who can play. Nobody can.",
     "normal", 4, {}),
]

# ── LAW & ORDER ──────────────────────────────────────────────────────────

_LAW_EVENTS = [
    ("The sheriff drags a man down Main Street in irons. "
     "Caught stealing from the assay office.",
     "normal", 8, {}),

    ("A hanging scheduled for noon. The whole town turns out. "
     "The condemned man says nothing.",
     "normal", 4, {}),

    ("A wanted poster goes up on the bulletin board. "
     "$200 reward for a stage robber working the road south.",
     "normal", 6, {}),

    ("Vigilance committee riding through town at dawn. "
     "They're looking for claim jumpers.",
     "advisory", 5, {}),

    ("The sheriff got shot last night. Town's without law "
     "until they can find a replacement.",
     "advisory", 4, {"law_alert": True}),

    ("A prisoner escaped from the jail. Armed and dangerous, they say. "
     "People are locking their doors early tonight.",
     "advisory", 5, {}),

    ("A trial underway at the courthouse. The defendant is accused "
     "of salting a mine to sell it. Half the town's been swindled.",
     "normal", 4, {}),

    ("Two men dueling at dawn outside town. One walks away. "
     "The other doesn't.",
     "normal", 5, {}),

    ("The marshal rode in from the county seat. Something big "
     "must be happening — he doesn't visit for nothing.",
     "normal", 4, {}),

    ("A lynch mob forming outside the jail. The sheriff stands alone "
     "on the steps with a double-barrel. The crowd disperses. Slowly.",
     "normal", 3, {}),
]

# ── ECONOMY & TRADE ──────────────────────────────────────────────────────

_ECONOMY_EVENTS = [
    ("A freight wagon rolled in loaded with supplies. "
     "Prices on flour and salt drop noticeably.",
     "advisory", 8, {"price_mult": 0.7, "price_duration": 5}),

    ("Supply wagon broke an axle on the pass. No deliveries this week. "
     "Prices are climbing.",
     "advisory", 6, {"price_mult": 1.4, "price_duration": 7}),

    ("A merchant is auctioning off a bankrupt prospector's gear "
     "in the town square. Tools going for cheap.",
     "advisory", 5, {}),

    ("News of a strike upriver. Prospectors flooding in. "
     "The general store can't keep shelves stocked.",
     "advisory", 7, {"price_mult": 1.3, "price_duration": 14}),

    ("A Chinese merchant has set up a stand selling vegetables "
     "and dried fish. First fresh food in weeks.",
     "normal", 5, {}),

    ("The bank is offering loans at 3% monthly. Several men line up. "
     "The fine print is in very small letters.",
     "normal", 4, {}),

    ("An assayer was caught giving false readings — cheating miners "
     "out of fair value. He's been run out of town.",
     "advisory", 4, {}),

    ("Mule train just arrived from Sacramento. "
     "Twenty animals loaded with everything from boots to bacon.",
     "normal", 6, {"price_mult": 0.8, "price_duration": 5}),

    ("Gold dust is circulating as currency again. "
     "The merchants are biting coins to check if they're real.",
     "normal", 4, {}),

    ("A peddler in the square is selling \"genuine California gold maps\" "
     "for $5 each. They're hand-drawn on butcher paper.",
     "normal", 5, {}),

    ("The freight company raised its rates. Everything shipped in "
     "costs more now.",
     "advisory", 4, {"price_mult": 1.2, "price_duration": 14}),

    ("Auction today — an old miner passed away and left no kin. "
     "His gear is going under the hammer.",
     "normal", 4, {}),
]

# ── GOLD & MINING ────────────────────────────────────────────────────────

_MINING_EVENTS = [
    ("Word spreading through camp: someone pulled a two-ounce nugget "
     "from the creek yesterday. The excitement is palpable.",
     "normal", 8, {}),

    ("A claim dispute turned violent last night. One man shot, "
     "one in hiding. The claim's been roped off.",
     "advisory", 6, {}),

    ("Old timer says the creek's been worked out. \"Ain't enough color "
     "left to fill a tooth.\" Some men are packing up.",
     "normal", 5, {}),

    ("A miner found quartz with visible gold on the ridge above town. "
     "Half the camp rushed up there this morning.",
     "normal", 7, {}),

    ("Cave-in at a shaft mine east of town. Two men trapped. "
     "Volunteers organizing a rescue.",
     "advisory", 5, {}),

    ("The assay office posted results: ore from the new lode "
     "runs $40 to the ton. That's real money.",
     "normal", 5, {}),

    ("Someone staked a claim right on the road into town. "
     "People have to walk around it. Nobody's happy.",
     "normal", 4, {}),

    ("A hydraulic operation started upriver. The creek is running "
     "brown and muddy. Downstream claims are furious.",
     "advisory", 5, {}),

    ("An old-timer demonstrates proper panning technique to newcomers "
     "at the creek. Some of them are hopeless.",
     "normal", 4, {}),

    ("The stamp mill's running day and night. The pounding echoes "
     "through the whole valley. Nobody's sleeping well.",
     "normal", 5, {}),

    ("A miner hit bedrock and found nothing. Three months of digging "
     "for empty ground. He sits on his tailings pile, staring.",
     "normal", 4, {}),

    ("Someone's selling placer claims for $50 each — pre-tested, "
     "they say. Experienced miners are skeptical.",
     "normal", 5, {}),
]

# ── WEATHER & NATURAL ────────────────────────────────────────────────────

_WEATHER_EVENTS = [
    ("Flash flood warning. The creek is rising fast. Men scrambling "
     "to pull equipment out of the water.",
     "warning", 5, {"health_delta": -5}),

    ("Wildfire smoke drifting in from the east. The sun is red "
     "and the air tastes like ash. Hard to breathe.",
     "advisory", 5, {"health_delta": -3}),

    ("Heavy snow overnight. The pass is closed. Nobody's going "
     "anywhere for a while.",
     "advisory", 4, {"price_mult": 1.3, "price_duration": 10}),

    ("Earthquake tremor shakes the buildings. Bottles fall off shelves. "
     "Everyone runs outside, then sheepishly walks back in.",
     "advisory", 3, {}),

    ("Lightning struck the big pine on the hill. It's burning "
     "like a torch. Beautiful and terrifying.",
     "normal", 4, {}),

    ("Spring thaw flooding the lower claims. Water's knee-deep "
     "in the main street. Mud everywhere.",
     "normal", 5, {}),

    ("Frost last night killed the garden plots outside town. "
     "Fresh vegetables just got more expensive.",
     "normal", 4, {"price_mult": 1.2, "price_duration": 7}),

    ("Perfect weather. Clear sky, warm sun, cool breeze. "
     "Everyone seems to be in a better mood today.",
     "normal", 6, {}),

    ("Dust storm rolling in from the flats. Visibility dropping. "
     "People covering their faces with bandanas.",
     "normal", 4, {}),

    ("River's so low you can walk across on the rocks. "
     "Good for prospecting, bad for the water supply.",
     "normal", 4, {}),
]

# ── HEALTH & DISEASE ─────────────────────────────────────────────────────

_HEALTH_EVENTS = [
    ("Cholera scare. Three people sick down by the creek. "
     "The doctor says boil your water.",
     "warning", 5, {"health_delta": -5}),

    ("A miner collapsed in the street. Heatstroke, they say. "
     "Someone pours water over him.",
     "normal", 4, {}),

    ("The doctor is drunk again. If you get hurt, you're on your own.",
     "normal", 4, {}),

    ("Dysentery going around camp. Half the men are too sick to work. "
     "The latrines are too close to the water source.",
     "advisory", 5, {"health_delta": -8}),

    ("A dentist has arrived in town. He's set up under a canvas "
     "awning and the screaming can be heard all afternoon.",
     "normal", 5, {}),

    ("Someone brought smallpox into camp. The doctor is quarantining "
     "the affected tent. Everyone's nervous.",
     "warning", 3, {"health_delta": -10}),

    ("The barber is advertising \"surgical services\" alongside "
     "haircuts. His hands are surprisingly steady.",
     "normal", 4, {}),

    ("A traveling medicine show rolled in. \"Dr. Pemberton's Genuine "
     "Cure-All\" — mostly alcohol and opium, probably.",
     "normal", 5, {}),

    ("Spring water from the new well is clear and cold. "
     "Best water in camp, people say.",
     "normal", 4, {"health_delta": 3}),

    ("Scurvy cases appearing. No fresh fruit for months. "
     "Someone's selling wild onions for a dollar each.",
     "advisory", 4, {"health_delta": -5}),
]

# ── ARRIVALS & DEPARTURES ────────────────────────────────────────────────

_ARRIVAL_EVENTS = [
    ("A wagon train pulled in at dusk. Forty people, dead tired, "
     "half-starved. They've been on the trail three months.",
     "normal", 7, {}),

    ("A lone rider came in from the south. Weathered, quiet, "
     "asking no questions. The kind of man you don't ask questions of.",
     "normal", 5, {}),

    ("A family arrived with a farm wagon. Father, mother, three children. "
     "They're looking for land, not gold.",
     "normal", 5, {}),

    ("Stage coach arrived — first one in two weeks. "
     "Mail, newspapers, and two passengers who look lost.",
     "normal", 6, {}),

    ("Half the camp packed up and left overnight. "
     "Heard about a new strike at another creek.",
     "normal", 5, {}),

    ("A preacher arrived. Set up a tent church on the edge of town. "
     "Sunday services for sinners, which is everyone.",
     "normal", 5, {}),

    ("A woman arrived alone on horseback. She says she's a reporter "
     "from a San Francisco newspaper. People don't know what to make of it.",
     "normal", 4, {}),

    ("A group of Chinese miners set up camp on the downstream claims. "
     "Some of the white miners are grumbling.",
     "normal", 5, {}),

    ("An old mountain man wandered in from the wilderness. "
     "He trades beaver pelts and tells stories nobody believes.",
     "normal", 5, {}),

    ("A photographer has arrived with his equipment. "
     "He's offering daguerreotypes for $3 each.",
     "normal", 4, {}),

    ("An army patrol passed through, headed north. "
     "The lieutenant asked about hostile activity. There hasn't been any.",
     "normal", 4, {}),

    ("A troupe of actors arrived and are performing Shakespeare "
     "in the saloon. The audience is mostly confused but entertained.",
     "normal", 3, {}),
]

# ── CONSTRUCTION & GROWTH ────────────────────────────────────────────────

_GROWTH_EVENTS = [
    ("A new building going up on Main Street. "
     "The sound of hammering starts at dawn and doesn't stop.",
     "normal", 6, {}),

    ("The town council voted to build a proper schoolhouse. "
     "Taxes going up a nickel.",
     "normal", 4, {}),

    ("Someone's digging a well in the town square. "
     "About time — hauling water from the creek was getting old.",
     "normal", 5, {}),

    ("The road into town is being graded. Men with picks and shovels "
     "filling ruts and moving rocks.",
     "normal", 4, {}),

    ("A bridge is being built across the creek. Logs and rope. "
     "It'll save a quarter mile of walking.",
     "normal", 4, {}),

    ("The general store expanded. Added a second room in the back. "
     "Now carries hardware alongside groceries.",
     "normal", 5, {}),

    ("Talk of a telegraph line coming through. The poles are already "
     "set on the road east. Another month, they say.",
     "normal", 4, {}),

    ("An assay office just opened — the town's first. "
     "No more riding two days to get ore tested.",
     "normal", 5, {}),

    ("A fire company organized. Twelve volunteers with buckets. "
     "Better than nothing.",
     "normal", 4, {}),

    ("The livery stable doubled its rates. Only stable in town "
     "and they know it.",
     "normal", 4, {"price_mult": 1.1, "price_duration": 14}),
]

# ── FIRE & DISASTER ──────────────────────────────────────────────────────

_DISASTER_EVENTS = [
    ("Fire! A cabin caught fire from an unattended stove. "
     "The bucket brigade saved the neighbors but the cabin's gone.",
     "warning", 4, {}),

    ("A building collapsed on Main Street. Shoddy construction. "
     "Nobody hurt, but it blocked the road for a day.",
     "advisory", 3, {}),

    ("The dam upstream broke. Water surging down the creek. "
     "Claims along the bottom are flooded out.",
     "warning", 3, {}),

    ("A runaway horse and wagon tore through town. "
     "Knocked over a hitching post and scattered a fruit stand.",
     "normal", 4, {}),

    ("Explosion at the powder magazine. Windows shattered across town. "
     "Miraculously, nobody killed. This time.",
     "warning", 2, {}),

    ("A chimney fire spread to the roof. Half the block turned out "
     "with buckets. They saved it, barely.",
     "advisory", 4, {}),

    ("Rock slide on the cliff above town. Boulders the size of wagons "
     "came down. Missed the buildings by twenty yards.",
     "advisory", 3, {}),
]

# ── GOSSIP & RUMOR ───────────────────────────────────────────────────────

_GOSSIP_EVENTS = [
    ("Rumor going around that the merchant's been watering the whiskey. "
     "He denies it. The whiskey tastes the same as always.",
     "normal", 7, {}),

    ("People whispering about a ghost in the old shaft mine. "
     "The dead miner's spirit, they say. Superstitious nonsense. Probably.",
     "normal", 5, {}),

    ("The blacksmith's wife left him. Rode off with a peddler "
     "in the middle of the night. Whole town's talking.",
     "normal", 5, {}),

    ("Word is the railroad survey crew passed through last month. "
     "If the railroad comes here, everything changes.",
     "normal", 5, {}),

    ("Old Jake swears he saw a grizzly just outside town last night. "
     "Nobody else saw it. But Jake doesn't usually lie.",
     "normal", 5, {}),

    ("The assayer and the banker haven't spoken in a week. "
     "Some kind of personal dispute. People are choosing sides.",
     "normal", 4, {}),

    ("A letter from back east says the President signed something "
     "about mining claims. Nobody's sure what it means yet.",
     "normal", 4, {}),

    ("Someone found a human skeleton in a dry wash outside town. "
     "No identification. Could've been there for years.",
     "normal", 4, {}),

    ("The schoolteacher is teaching the children to read using "
     "wanted posters. Practical education.",
     "normal", 4, {}),

    ("There's talk of incorporating as a proper town. "
     "Elections, a mayor, ordinances. The old-timers hate the idea.",
     "normal", 4, {}),

    ("A man claims to have found an ancient Spanish mine entrance "
     "in the hills. He's selling shares in the venture.",
     "normal", 5, {}),

    ("The laundress found a gold nugget in a miner's shirt pocket "
     "while washing. She returned it. The miner tipped her a dollar.",
     "normal", 4, {}),
]

# ── ANIMALS & WILDLIFE ───────────────────────────────────────────────────

_ANIMAL_EVENTS = [
    ("A bear got into the meat cache behind the general store. "
     "Cleaned it out. The storekeeper is furious.",
     "normal", 5, {}),

    ("Pack of wolves howling on the ridge above town all night. "
     "Nobody slept well.",
     "normal", 5, {}),

    ("A rattlesnake found under the porch of the hotel. "
     "Took three men and a shovel to deal with it.",
     "normal", 5, {}),

    ("Deer wandered right into the middle of town at dawn. "
     "Stood in the street for a minute, then bolted.",
     "normal", 5, {}),

    ("A mule kicked through the wall of the livery stable. "
     "It's still standing there looking pleased with itself.",
     "normal", 4, {}),

    ("Crows have been following the camp dogs all morning. "
     "Something dead in the brush, probably.",
     "normal", 4, {}),

    ("A cougar took somebody's dog last night. "
     "Men organizing a hunt.",
     "normal", 5, {}),

    ("Prairie dog holes everywhere outside town. "
     "A horse stepped in one and threw its rider. Broken arm.",
     "normal", 4, {}),

    ("Eagles nesting on the cliff above town. "
     "Watching everything with those cold yellow eyes.",
     "normal", 4, {}),

    ("Skunk got under the church. Services canceled until "
     "the smell clears. Could be a while.",
     "normal", 4, {}),
]

# ── RELIGION & CULTURE ───────────────────────────────────────────────────

_CULTURE_EVENTS = [
    ("Sunday services well-attended today. The preacher gave "
     "a sermon about greed. Nobody made eye contact.",
     "normal", 5, {}),

    ("A camp meeting tent revival started on the edge of town. "
     "Singing and shouting all night. Opinions are divided.",
     "normal", 4, {}),

    ("Someone donated a piano to the town hall. "
     "Now they just need someone who can play it.",
     "normal", 4, {}),

    ("Fourth of July celebration. Gunfire at midnight, "
     "whiskey flowing, and someone lit the outhouse on fire.",
     "normal", 3, {}),

    ("A funeral procession down Main Street. "
     "The whole town walks behind the coffin. Hats off.",
     "normal", 5, {}),

    ("A wedding at the church. The bride wore calico. "
     "The groom wore a clean shirt. First wedding in this town.",
     "normal", 4, {}),

    ("Christmas Eve. Candles in every window. The saloon "
     "is serving hot cider. Even the rough men seem quieter tonight.",
     "normal", 3, {}),

    ("A traveling preacher challenges the local preacher to "
     "a theological debate. The saloon serves as venue. Standing room only.",
     "normal", 3, {}),
]

# ── CONFLICT & TENSION ───────────────────────────────────────────────────

_CONFLICT_EVENTS = [
    ("Tensions between the hill miners and the creek miners. "
     "Something about water rights. Getting ugly.",
     "advisory", 5, {}),

    ("A group of men ran a family out of town for reasons nobody "
     "will explain clearly. The air is tense.",
     "advisory", 4, {"reputation_delta": -2}),

    ("Gunshots after dark. In the morning, bloodstains on the "
     "street but nobody's talking.",
     "advisory", 5, {}),

    ("The saloon keeper barred a group of miners. Now they're "
     "drinking outside and making threats.",
     "normal", 5, {}),

    ("Two businesses on Main Street in a price war. "
     "Flour down to nothing. Customers benefit, for now.",
     "normal", 4, {"price_mult": 0.7, "price_duration": 7}),

    ("A claim-jumping dispute is headed for the mining district court. "
     "Both sides hiring lawyers. Going to be expensive.",
     "normal", 4, {}),

    ("Night riders rode through camp last night. Fired shots in the air. "
     "Nobody knows what they wanted. Nobody wants to find out.",
     "advisory", 4, {}),

    ("The teamsters are threatening to strike. No freight deliveries "
     "until their demands are met. Prices will rise.",
     "advisory", 4, {"price_mult": 1.3, "price_duration": 10}),
]

# ── ODD & COLORFUL ──────────────────────────────────────────────────────

_ODD_EVENTS = [
    ("A man walked into town wearing nothing but a barrel. "
     "Lost everything at cards, including his clothes.",
     "normal", 4, {}),

    ("Someone painted \"WELCOME TO HELL\" on the sign at the edge of town. "
     "The mayor had it scrubbed off. It was back the next morning.",
     "normal", 4, {}),

    ("A prospector named his mule \"Senator\" and insists on introducing "
     "it to everyone. The mule seems indifferent to the honor.",
     "normal", 4, {}),

    ("A chess tournament at the general store. The prize is a ham. "
     "Competition is fierce.",
     "normal", 4, {}),

    ("Someone built a hot tub from a half-barrel and charges "
     "two bits for a soak. Line's around the block.",
     "normal", 4, {}),

    ("A parrot showed up in town. Nobody knows where it came from. "
     "It sits on the saloon porch and swears at passersby.",
     "normal", 4, {}),

    ("Two men having a spitting contest in the street. "
     "A crowd has gathered. Bets are being placed.",
     "normal", 4, {}),

    ("Somebody's rooster crows at all hours, not just dawn. "
     "The owner says it's \"artistic.\" Neighbors disagree.",
     "normal", 4, {}),

    ("A man just ate 47 hardtack biscuits on a bet. "
     "He won $5. He does not look well.",
     "normal", 4, {}),

    ("A prospector is panning for gold in the horse trough. "
     "The livery owner is not amused, but there IS color in there.",
     "normal", 4, {}),
]

# ── CAMP-SPECIFIC (mining camps only) ────────────────────────────────────

_CAMP_EVENTS = [
    ("The creek shifted course after last night's rain. "
     "Some claims just got better. Others just got worthless.",
     "normal", 6, {}),

    ("Somebody's tent collapsed in the wind. "
     "He's standing there holding a canvas sheet looking defeated.",
     "normal", 5, {}),

    ("A campfire got away from someone. Burned a patch of brush "
     "before it was stomped out. No real damage.",
     "normal", 5, {}),

    ("New arrivals staking claims too close to existing ones. "
     "Arguments about claim boundaries all afternoon.",
     "normal", 6, {}),

    ("The water's gone muddy from all the upstream digging. "
     "Can't drink it. Can't wash in it. Camp morale is low.",
     "normal", 5, {}),

    ("Someone strung a rope line between the tents and hung "
     "wet clothes. The whole camp looks like laundry day.",
     "normal", 4, {}),

    ("A newcomer set up his pan right on someone's tailings pile. "
     "He's either very clever or very ignorant.",
     "normal", 4, {}),

    ("Camp meeting tonight around the fire. Talk of organizing "
     "a miners' committee to settle disputes.",
     "normal", 5, {}),
]

# ── CITY-SPECIFIC (cities only) ──────────────────────────────────────────

_CITY_EVENTS = [
    ("The newspaper published an editorial against the mine operators. "
     "Calling for safety regulations. The operators are furious.",
     "normal", 5, {}),

    ("A bank robbery! Two armed men rode in, shot the guard, "
     "and took the vault. Posse forming up.",
     "warning", 3, {"law_alert": True}),

    ("City council meeting got heated. The mayor and the sheriff "
     "nearly came to blows over the tax rate.",
     "normal", 4, {}),

    ("Gas street lamps installed on Main Street. "
     "The town looks different at night now. Almost civilized.",
     "normal", 4, {}),

    ("A fire department organized with a proper hand-pump engine. "
     "Demonstration in the square. Impressive.",
     "normal", 4, {}),

    ("Opera house opened its doors. First show is next week. "
     "Tickets are $1. The miners are bewildered by the concept.",
     "normal", 3, {}),

    ("The telegraph office received 47 messages today. "
     "The operator hasn't slept. News travels fast now.",
     "normal", 4, {}),

    ("A suffragist gave a speech in the square. Mixed reception. "
     "The women applauded. Most of the men walked away.",
     "normal", 3, {}),

    ("Real estate speculation heating up. Lots on Main Street "
     "selling for ten times what they cost a year ago.",
     "normal", 4, {}),

    ("The railroad announced a spur line to this town. "
     "If it comes through, land values will explode.",
     "advisory", 3, {}),
]

# ── SEASONAL ─────────────────────────────────────────────────────────────

_SPRING_EVENTS = [
    ("Wildflowers carpeting the hills above town. "
     "Even the hardest men stop to look.",
     "normal", 5, {}),

    ("Spring runoff swelling the creek. Good for panning, "
     "dangerous for crossing.",
     "normal", 5, {}),

    ("The snow line is receding up the mountains. "
     "High country will be passable again soon.",
     "normal", 4, {}),
]

_SUMMER_EVENTS = [
    ("Heat so fierce the dogs won't leave the shade. "
     "Work slows to nothing after noon.",
     "normal", 5, {"health_delta": -3}),

    ("The creek is drying up. Barely a trickle where it used to run "
     "waist-deep. Claims along the upper stretches are bone-dry.",
     "normal", 5, {}),

    ("Grasshoppers everywhere. They're eating everything green "
     "within a mile of town.",
     "normal", 4, {}),
]

_FALL_EVENTS = [
    ("First frost of the season. Ice on the water bucket this morning. "
     "Winter's coming.",
     "normal", 5, {}),

    ("Aspen turning gold on the hillsides. "
     "The whole mountain looks like it's on fire.",
     "normal", 5, {}),

    ("Men stacking firewood against every wall in town. "
     "Nobody wants to be caught short when the snow comes.",
     "normal", 5, {}),
]

_WINTER_EVENTS = [
    ("Snow piling up. The pass is closed. "
     "This town is on its own until spring.",
     "advisory", 5, {"price_mult": 1.4, "price_duration": 30}),

    ("Frozen pipes, frozen ground, frozen everything. "
     "Mining's suspended. Men huddled around stoves.",
     "normal", 5, {}),

    ("Someone's still out there digging in the frozen creek bed. "
     "Dedicated or crazy. Maybe both.",
     "normal", 4, {}),

    ("Cabin fever setting in. Arguments over nothing. "
     "The saloon's doing good business though.",
     "normal", 5, {}),

    ("A man froze to death in his tent last night. "
     "Found him in the morning. Nobody knew his real name.",
     "advisory", 3, {}),
]


# ============================================================================
#  MAIN ROLL FUNCTION
# ============================================================================

def roll_settlement_event(engine: "Engine", settlement_type: str,
                          season: str = "summer",
                          year: int = 1849) -> Optional[SettlementEvent]:
    """
    Roll for a random settlement event. Called once per day from engine.
    Returns a SettlementEvent or None.
    """
    rng = random.Random()

    # Check if an event fires
    chance = EVENT_CHANCE.get(settlement_type, 0.25)
    if rng.random() > chance:
        return None

    # Build the weighted event pool based on settlement type + season
    pool: List[Tuple] = []

    # Universal events (all settlements)
    pool.extend(_SALOON_EVENTS)
    pool.extend(_GOSSIP_EVENTS)
    pool.extend(_WEATHER_EVENTS)
    pool.extend(_HEALTH_EVENTS)
    pool.extend(_ANIMAL_EVENTS)
    pool.extend(_ODD_EVENTS)
    pool.extend(_ARRIVAL_EVENTS)

    # Events requiring some infrastructure
    if settlement_type not in ("mining_camp_small",):
        pool.extend(_LAW_EVENTS)
        pool.extend(_ECONOMY_EVENTS)
        pool.extend(_GROWTH_EVENTS)
        pool.extend(_CONFLICT_EVENTS)
        pool.extend(_CULTURE_EVENTS)

    # Mining-focused settlements
    if settlement_type in ("mining_camp_small", "mining_camp_medium", "boomtown"):
        pool.extend(_MINING_EVENTS)
        pool.extend(_CAMP_EVENTS)

    # Boomtowns get disaster events (overcrowded, poorly built)
    if settlement_type in ("boomtown", "city"):
        pool.extend(_DISASTER_EVENTS)

    # Cities only
    if settlement_type == "city":
        pool.extend(_CITY_EVENTS)

    # Seasonal
    season_pools = {
        "spring": _SPRING_EVENTS,
        "summer": _SUMMER_EVENTS,
        "fall": _FALL_EVENTS,
        "winter": _WINTER_EVENTS,
    }
    pool.extend(season_pools.get(season, []))

    if not pool:
        return None

    # Weighted selection
    messages, severities, weights, effects_list = zip(*pool)
    idx = rng.choices(range(len(pool)), weights=weights, k=1)[0]
    msg, sev, _, effects = pool[idx]

    return SettlementEvent(
        message=msg,
        severity=sev,
        reputation_delta=effects.get("reputation_delta", 0.0),
        price_mult=effects.get("price_mult", 1.0),
        price_duration=effects.get("price_duration", 0),
        npc_spawned=effects.get("npc_spawned", ""),
        item_spawned=effects.get("item_spawned", ""),
        cash_delta=effects.get("cash_delta", 0.0),
        health_delta=effects.get("health_delta", 0.0),
        law_alert=effects.get("law_alert", False),
    )
