"""
src/world_gen.py

Expanded world generation for American Prospector.
Provides 100+ historical US locations with era data, mining significance,
and gold-bias hotspot overrides around known mining districts.

Integration — in WorldMap._generate(), after _place_terrain():
    from src.world_gen import WorldGenerator
    WorldGenerator(self.seed).populate(self)
"""

from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.world_map import WorldMap


@dataclass
class HistoricalLocation:
    name: str
    x: int
    y: int
    loc_type: str           # "city" | "town" | "camp" | "fort" | "outpost"
    population: int
    era_founded: int        # first year this location meaningfully exists
    significance: str       # one-line NPC knowledge hook
    mining: bool = False    # NPCs know gold/silver/oil/coal here
    gold_bias_override: Optional[float] = None   # None = use regional default


HISTORICAL_LOCATIONS: List[HistoricalLocation] = [

    # ── CALIFORNIA ──────────────────────────────────────────────────────────
    HistoricalLocation("Sacramento",     95, 165, "city",  25000, 1849,
        "Capital of California and gateway to the mines.", mining=True),
    HistoricalLocation("San Francisco",  72, 172, "city",  60000, 1849,
        "The great port — all ships come and go through here."),
    HistoricalLocation("Coloma",        102, 162, "camp",    500, 1848,
        "Sutter's Mill — first gold found here, January 1848.", mining=True,
        gold_bias_override=0.90),
    HistoricalLocation("Stockton",       88, 170, "town",   4000, 1849,
        "Supply hub for the Southern Mines."),
    HistoricalLocation("Marysville",     93, 158, "town",   2500, 1849,
        "Gateway to the Northern Mines on the Yuba.", mining=True),
    HistoricalLocation("Grass Valley",   97, 157, "town",   3000, 1850,
        "Hard rock gold — the Empire Mine.", mining=True,
        gold_bias_override=0.85),
    HistoricalLocation("Nevada City",    97, 154, "town",   2800, 1849,
        "Rich quartz veins and placer diggings.", mining=True,
        gold_bias_override=0.80),
    HistoricalLocation("Downieville",    98, 152, "camp",    500, 1849,
        "Remote Sierra camp, rich in placer gold.", mining=True,
        gold_bias_override=0.75),
    HistoricalLocation("Auburn CA",      99, 162, "town",   1500, 1848,
        "One of the first mining settlements.", mining=True),
    HistoricalLocation("Placerville",   101, 165, "town",   2000, 1848,
        "Hangtown — named for its swift frontier justice.", mining=True),
    HistoricalLocation("Angels Camp",    92, 171, "camp",    800, 1849,
        "Mark Twain country — Calaveras County gold.", mining=True),
    HistoricalLocation("Sonora CA",      93, 173, "town",   2000, 1849,
        "Heart of the Southern Mines.", mining=True),
    HistoricalLocation("Columbia CA",    92, 174, "town",   1500, 1850,
        "The Gem of the Southern Mines — rich flat placers.", mining=True,
        gold_bias_override=0.82),
    HistoricalLocation("Jackson CA",     93, 170, "town",   1200, 1849,
        "Amador County — placer and quartz mining.", mining=True),
    HistoricalLocation("Weaverville",    62, 145, "town",   2000, 1850,
        "Trinity County — Chinese miners worked these rivers.", mining=True),
    HistoricalLocation("Shasta City",    75, 142, "town",   1500, 1849,
        "Northern California supply hub.", mining=True),
    HistoricalLocation("Yreka",          68, 132, "town",   1000, 1851,
        "Siskiyou County seat — Scott River gold.", mining=True),
    HistoricalLocation("Oroville",       88, 152, "town",   2500, 1849,
        "Feather River dredging country.", mining=True,
        gold_bias_override=0.80),
    HistoricalLocation("Los Angeles",    80, 188, "town",   5000, 1849,
        "Sleepy rancho town, far from the diggings."),
    HistoricalLocation("San Jose CA",    68, 177, "town",   3500, 1849,
        "Mission town in the Santa Clara Valley."),
    HistoricalLocation("Monterey CA",    64, 181, "town",   1800, 1849,
        "Old capital of Alta California."),
    HistoricalLocation("Kern County",    87, 182, "camp",    200, 1865,
        "Late-era oil seeps — early California petroleum.", mining=True),

    # ── NEVADA ──────────────────────────────────────────────────────────────
    HistoricalLocation("Virginia City NV", 114, 158, "city", 15000, 1859,
        "The Comstock Lode — richest silver strike in history.", mining=True,
        gold_bias_override=0.95),
    HistoricalLocation("Carson City",   115, 161, "town",   5000, 1858,
        "Nevada capital, near the Comstock."),
    HistoricalLocation("Reno",          110, 153, "town",   5000, 1868,
        "Truckee Meadows — railroad town."),
    HistoricalLocation("Elko NV",       147, 148, "town",   1500, 1868,
        "Central Nevada ranching and mining."),
    HistoricalLocation("Eureka NV",     150, 165, "town",   3000, 1864,
        "Lead-silver smelting town, mid-Nevada.", mining=True),
    HistoricalLocation("Austin NV",     148, 162, "town",   2000, 1862,
        "Reese River silver — boom and bust.", mining=True),
    HistoricalLocation("Tonopah",       132, 172, "town",   3000, 1900,
        "Late silver strike — Jim Butler's discovery 1900.", mining=True,
        gold_bias_override=0.85),
    HistoricalLocation("Goldfield NV",  130, 175, "town",   4000, 1902,
        "Richest gold camp of the 20th century in Nevada.", mining=True,
        gold_bias_override=0.90),

    # ── UTAH ────────────────────────────────────────────────────────────────
    HistoricalLocation("Salt Lake City", 172, 150, "city", 20000, 1849,
        "Brigham Young's Zion — Mormons control the supply chains."),
    HistoricalLocation("Provo",         175, 155, "town",   3000, 1849,
        "Utah Valley — farm country under the Wasatch."),
    HistoricalLocation("Ogden",         172, 147, "town",   4000, 1849,
        "Junction City — Union Pacific meets Central Pacific 1869."),
    HistoricalLocation("Park City UT",  178, 152, "town",   4000, 1869,
        "Silver mining on the Wasatch front.", mining=True),
    HistoricalLocation("Moab",          195, 162, "camp",    500, 1880,
        "Remote canyon country — uranium boom in the 1950s.", mining=True),
    HistoricalLocation("Helper UT",     182, 158, "camp",   1000, 1882,
        "Carbon County coal — railroad helper engines.", mining=True),

    # ── COLORADO ────────────────────────────────────────────────────────────
    HistoricalLocation("Denver",        222, 155, "city", 35000, 1858,
        "Queen City of the Plains — supply hub for Colorado mining."),
    HistoricalLocation("Leadville",     214, 163, "city", 14000, 1877,
        "Two Miles High — silver and lead at 10,000 feet.", mining=True,
        gold_bias_override=0.90),
    HistoricalLocation("Cripple Creek", 224, 165, "town", 10000, 1890,
        "Last great gold rush — $340 million at its peak.", mining=True,
        gold_bias_override=0.92),
    HistoricalLocation("Central City CO", 220, 158, "town", 4000, 1859,
        "Richest Square Mile on Earth — first Colorado lode gold.", mining=True,
        gold_bias_override=0.88),
    HistoricalLocation("Idaho Springs", 218, 158, "town",  2000, 1859,
        "First Colorado gold discovery — Chicago Creek.", mining=True,
        gold_bias_override=0.82),
    HistoricalLocation("Georgetown CO", 216, 160, "town",  3000, 1864,
        "Silver queen of the Rockies.", mining=True),
    HistoricalLocation("Aspen CO",      208, 162, "town",  5000, 1880,
        "Silver boom, then bust — richest Colorado mine history.", mining=True),
    HistoricalLocation("Telluride",     200, 168, "town",  3000, 1878,
        "Box canyon silver — Butch Cassidy's first bank robbery.", mining=True),
    HistoricalLocation("Silverton CO",  200, 170, "town",  2000, 1874,
        "San Juan Mountains silver.", mining=True),
    HistoricalLocation("Durango CO",    200, 175, "town",  4000, 1880,
        "Denver and Rio Grande terminus — smelter city."),
    HistoricalLocation("Pueblo CO",     224, 168, "town",  8000, 1858,
        "Colorado Fuel and Iron — steel mills on the Arkansas."),
    HistoricalLocation("Grand Junction", 207, 158, "town",  3000, 1881,
        "Western Slope hub — coal and uranium country.", mining=True),
    HistoricalLocation("Colorado Springs", 224, 163, "town", 8000, 1871,
        "Health resort at the foot of Pikes Peak."),

    # ── MONTANA ─────────────────────────────────────────────────────────────
    HistoricalLocation("Butte",         178,  88, "city", 30000, 1864,
        "The Richest Hill on Earth — copper, silver, gold.", mining=True,
        gold_bias_override=0.92),
    HistoricalLocation("Helena MT",     188,  90, "town",  4000, 1864,
        "Last Chance Gulch gold — Montana capital.", mining=True,
        gold_bias_override=0.85),
    HistoricalLocation("Missoula",      172,  86, "town",  3000, 1860,
        "Fort Missoula — western Montana trade hub."),
    HistoricalLocation("Bozeman",       198,  95, "town",  2000, 1864,
        "Gallatin Valley farming — Bozeman Trail gateway."),
    HistoricalLocation("Billings",      215, 100, "town",  3000, 1882,
        "Yellowstone River — Northern Pacific Railroad town."),
    HistoricalLocation("Bannack MT",    183,  95, "camp",   500, 1862,
        "First Montana gold — outlaw sheriff Henry Plummer.", mining=True,
        gold_bias_override=0.80),
    HistoricalLocation("Virginia City MT", 190, 96, "town", 2000, 1863,
        "Montana's first capital — Alder Gulch placer gold.", mining=True,
        gold_bias_override=0.88),
    HistoricalLocation("Fort Benton",   195,  87, "town",  1500, 1847,
        "Head of navigation on the Missouri — fur trade post."),

    # ── WYOMING ─────────────────────────────────────────────────────────────
    HistoricalLocation("Cheyenne",      222, 128, "town",  8000, 1867,
        "Magic City of the Plains — Union Pacific division point."),
    HistoricalLocation("Laramie WY",    228, 132, "town",  3000, 1868,
        "Territorial capital — railroad and range cattle."),
    HistoricalLocation("Casper",        220, 118, "town",  2500, 1888,
        "Fort Caspar on the North Platte — oil later.", mining=True),
    HistoricalLocation("Rock Springs",  205, 135, "town",  2500, 1869,
        "Union Pacific coal mines — Chinese miners 1875.", mining=True),
    HistoricalLocation("Sheridan WY",   225, 107, "town",  2000, 1882,
        "Northern Wyoming coal and cattle."),

    # ── SOUTH DAKOTA ────────────────────────────────────────────────────────
    HistoricalLocation("Deadwood",      268, 108, "town",  4000, 1876,
        "Black Hills gold — Wild Bill Hickok's grave.", mining=True,
        gold_bias_override=0.90),
    HistoricalLocation("Lead SD",       266, 108, "town",  2000, 1876,
        "Homestake Mine — largest gold producer in western hemisphere.", mining=True,
        gold_bias_override=0.95),
    HistoricalLocation("Rapid City",    263, 113, "town",  1500, 1876,
        "Gateway to the Black Hills."),

    # ── IDAHO ───────────────────────────────────────────────────────────────
    HistoricalLocation("Boise",         152, 125, "town",  5000, 1863,
        "Snake River capital — supply hub for Idaho mining."),
    HistoricalLocation("Idaho City",    152, 120, "town",  4000, 1862,
        "Boise Basin gold — briefly largest city in Pacific NW.", mining=True,
        gold_bias_override=0.88),
    HistoricalLocation("Silver City ID", 148, 138, "camp",  800, 1864,
        "Owyhee Mountains silver — War Eagle Mountain.", mining=True),
    HistoricalLocation("Coeur d'Alene", 158,  88, "town",  2000, 1881,
        "Silver Valley — Bunker Hill, Morning Mine.", mining=True,
        gold_bias_override=0.85),
    HistoricalLocation("Wallace ID",    163,  92, "town",  2000, 1884,
        "Heart of the Coeur d'Alene silver belt.", mining=True),
    HistoricalLocation("Lewiston ID",   155, 108, "town",  2000, 1861,
        "First Idaho capital — head of navigation on the Snake."),

    # ── OREGON ──────────────────────────────────────────────────────────────
    HistoricalLocation("Portland",       78, 108, "city", 20000, 1845,
        "Stumptown — Columbia River trade hub."),
    HistoricalLocation("Salem OR",       73, 112, "town",  3000, 1842,
        "Oregon capital — Willamette Valley farms."),
    HistoricalLocation("Eugene OR",      72, 118, "town",  1500, 1846,
        "Southern Willamette Valley."),
    HistoricalLocation("Astoria",        65, 104, "town",  2000, 1811,
        "Oldest American settlement west of the Rockies."),
    HistoricalLocation("Jacksonville OR", 70, 127, "town", 1500, 1851,
        "Southern Oregon gold rush.", mining=True),

    # ── WASHINGTON ──────────────────────────────────────────────────────────
    HistoricalLocation("Seattle",        78,  98, "town",  8000, 1851,
        "Puget Sound — timber, coal, gateway to Alaska."),
    HistoricalLocation("Olympia WA",     74, 102, "town",  2000, 1846,
        "Washington territorial capital."),
    HistoricalLocation("Tacoma",         78, 101, "town",  4000, 1873,
        "Northern Pacific terminus."),
    HistoricalLocation("Spokane",       125,  97, "town",  4000, 1881,
        "Inland Empire — near Coeur d'Alene mines."),
    HistoricalLocation("Walla Walla",   120, 108, "town",  4000, 1856,
        "Eastern Washington farming and Fort Walla Walla."),

    # ── ARIZONA ─────────────────────────────────────────────────────────────
    HistoricalLocation("Tucson",        152, 193, "town",  7000, 1849,
        "Old Pueblo — Mexican adobe town on the Camino Real."),
    HistoricalLocation("Tombstone",     158, 197, "town",  5000, 1877,
        "Too Tough to Die — Ed Schieffelin's silver strike.", mining=True,
        gold_bias_override=0.88),
    HistoricalLocation("Prescott AZ",   143, 188, "town",  2000, 1863,
        "First Arizona territorial capital — Walker Party gold.", mining=True),
    HistoricalLocation("Flagstaff",     150, 185, "town",  1000, 1876,
        "Ponderosa pine plateau — railroad junction."),
    HistoricalLocation("Yuma",          130, 202, "town",  2000, 1849,
        "Colorado River crossing — brutal desert heat."),
    HistoricalLocation("Globe AZ",      155, 196, "town",  5000, 1876,
        "Old Dominion copper mine.", mining=True),
    HistoricalLocation("Jerome AZ",     148, 190, "town",  5000, 1876,
        "Billion dollar copper camp — Verde Valley.", mining=True),

    # ── NEW MEXICO ──────────────────────────────────────────────────────────
    HistoricalLocation("Santa Fe",      192, 190, "town", 10000, 1849,
        "Ancient capital — Santa Fe Trail terminus."),
    HistoricalLocation("Albuquerque",   192, 192, "town",  5000, 1706,
        "Rio Grande valley — adobe and the railroad."),
    HistoricalLocation("Silver City NM", 183, 200, "town", 3000, 1870,
        "Grant County silver and copper.", mining=True),
    HistoricalLocation("Elizabethtown NM", 200, 179, "camp", 1000, 1867,
        "First New Mexico gold rush — Ute Creek.", mining=True),

    # ── TEXAS ───────────────────────────────────────────────────────────────
    HistoricalLocation("El Paso",       228, 200, "town",  5000, 1849,
        "Pass of the North — junction of three nations."),
    HistoricalLocation("San Antonio",   272, 215, "city", 37000, 1849,
        "The Alamo — frontier military hub and cattle country."),
    HistoricalLocation("Austin TX",     282, 213, "town", 10000, 1839,
        "Texas capital on the Colorado River."),
    HistoricalLocation("Houston",       298, 220, "town", 16000, 1849,
        "Bayou City — cotton and cattle port."),
    HistoricalLocation("Galveston",     300, 225, "town", 12000, 1838,
        "Wealthiest city in Texas — the Island."),
    HistoricalLocation("Dallas",        290, 210, "town",  5000, 1841,
        "North Texas trade hub on the Trinity River."),
    HistoricalLocation("Fort Worth",    287, 210, "town",  4000, 1849,
        "Where the West begins — cattle drive terminus."),
    HistoricalLocation("Beaumont TX",   308, 218, "city",  9000, 1838,
        "Spindletop gusher 1901 — birth of the petroleum age.", mining=True),
    HistoricalLocation("Laredo",        268, 222, "town",  4000, 1755,
        "Rio Grande crossing — Texas-Mexico border trade."),
    HistoricalLocation("Amarillo",      255, 200, "town",  2000, 1887,
        "Texas Panhandle cattle — XIT Ranch country."),

    # ── OKLAHOMA ────────────────────────────────────────────────────────────
    HistoricalLocation("Tulsa",         300, 192, "town",  7000, 1898,
        "Creek Nation land — oil boom turns it into the Oil Capital.", mining=True),
    HistoricalLocation("Oklahoma City", 290, 198, "town",  5000, 1889,
        "Land Run city — grew from a tent camp overnight."),
    HistoricalLocation("Guthrie OK",    288, 195, "town",  3000, 1889,
        "First Oklahoma territorial capital."),

    # ── KANSAS ──────────────────────────────────────────────────────────────
    HistoricalLocation("Wichita",       283, 155, "town",  5000, 1868,
        "Cowtown — Chisholm Trail cattle drives."),
    HistoricalLocation("Dodge City",    258, 155, "town",  3000, 1872,
        "The Wickedest City in the West — cattle, buffalo, lawmen."),
    HistoricalLocation("Topeka",        285, 148, "town",  8000, 1854,
        "Kansas capital on the Santa Fe Trail."),
    HistoricalLocation("Abilene KS",    277, 148, "town",  3000, 1858,
        "First cattle railhead — Wild Bill Hickok town marshal 1871."),

    # ── NEBRASKA ────────────────────────────────────────────────────────────
    HistoricalLocation("Omaha",         282, 128, "town", 15000, 1854,
        "Eastern terminus Union Pacific — Missouri River crossing."),
    HistoricalLocation("Lincoln NE",    280, 132, "town",  5000, 1867,
        "Nebraska capital."),
    HistoricalLocation("North Platte",  255, 128, "town",  3000, 1866,
        "Union Pacific division point — Buffalo Bill's home."),

    # ── NORTH DAKOTA ────────────────────────────────────────────────────────
    HistoricalLocation("Bismarck",      267,  93, "town",  3000, 1872,
        "Northern Pacific terminus — Fort Abraham Lincoln nearby."),
    HistoricalLocation("Fargo",         295,  93, "town",  4000, 1871,
        "Red River wheat country."),

    # ── MINNESOTA ───────────────────────────────────────────────────────────
    HistoricalLocation("Minneapolis",   303, 100, "city", 15000, 1849,
        "Mill City — St. Anthony Falls powers the flour mills."),
    HistoricalLocation("Duluth",        315,  87, "town",  5000, 1870,
        "Head of the Great Lakes — iron ore gateway.", mining=True),

    # ── IOWA ────────────────────────────────────────────────────────────────
    HistoricalLocation("Des Moines",    302, 130, "town",  8000, 1843,
        "Iowa capital — coal country in the south."),

    # ── MISSOURI ────────────────────────────────────────────────────────────
    HistoricalLocation("St. Louis",     318, 140, "city", 160000, 1849,
        "Gateway to the West — Missouri River departure point."),
    HistoricalLocation("Kansas City",   298, 143, "city",  15000, 1838,
        "Westport Landing — outfitting point for overland trails."),

    # ── ILLINOIS ────────────────────────────────────────────────────────────
    HistoricalLocation("Chicago",       313, 115, "city", 500000, 1833,
        "Rail hub of America — grain, cattle, and money markets."),

    # ── MICHIGAN ────────────────────────────────────────────────────────────
    HistoricalLocation("Detroit",       352, 115, "city",  21000, 1849,
        "Straits city — copper and iron from the Upper Peninsula."),
    HistoricalLocation("Marquette MI",  335,  92, "town",   4000, 1849,
        "Upper Peninsula iron and copper — Lake Superior ore docks.", mining=True),
    HistoricalLocation("Calumet MI",    333,  88, "town",   5000, 1864,
        "Copper Country — Keweenaw Peninsula copper mines.", mining=True),

    # ── OHIO ────────────────────────────────────────────────────────────────
    HistoricalLocation("Cleveland",     362, 115, "city",  17000, 1849,
        "Lake Erie industrial city — iron and oil refining."),
    HistoricalLocation("Cincinnati",    358, 135, "city",  80000, 1849,
        "Porkopolis — hog processing capital of America."),

    # ── PENNSYLVANIA ────────────────────────────────────────────────────────
    HistoricalLocation("Philadelphia",  408, 125, "city", 120000, 1849,
        "The Quaker City — finance and manufacturing."),
    HistoricalLocation("Pittsburgh",    385, 127, "city",  46000, 1849,
        "Steel city — Carnegie's mills on the three rivers."),
    HistoricalLocation("Titusville",    350, 112, "town",   6000, 1859,
        "Drake's Well — first commercial oil well in America 1859.", mining=True),
    HistoricalLocation("Bradford PA",   385, 115, "town",   8000, 1871,
        "Pennsylvania's richest oil field — 1870s boom.", mining=True),
    HistoricalLocation("Scranton",      405, 118, "city",  35000, 1840,
        "Anthracite coal — the Black Diamond.", mining=True),

    # ── NEW YORK ────────────────────────────────────────────────────────────
    HistoricalLocation("New York City", 425, 122, "city", 515000, 1849,
        "The great American metropolis."),
    HistoricalLocation("Buffalo NY",    393, 112, "city",  42000, 1849,
        "Erie Canal terminus — Great Lakes gateway."),
    HistoricalLocation("Albany",        418, 113, "town",  25000, 1849,
        "New York capital — northern terminus of the Hudson."),

    # ── NEW ENGLAND & MID-ATLANTIC ──────────────────────────────────────────
    HistoricalLocation("Boston",        440, 110, "city", 137000, 1849,
        "Athens of America — finance, culture, and abolitionism."),
    HistoricalLocation("Washington DC", 408, 133, "city",  51000, 1849,
        "The federal capital — land office, patent office, treasury."),
    HistoricalLocation("Baltimore",     410, 130, "city",  96000, 1849,
        "B&O Railroad terminus — Chesapeake Bay port."),

    # ── SOUTHEAST ───────────────────────────────────────────────────────────
    HistoricalLocation("Richmond VA",   413, 138, "city",  28000, 1849,
        "Virginia capital — tobacco and iron."),
    HistoricalLocation("Nashville",     348, 153, "city",  17000, 1849,
        "Athens of the South — Cumberland River hub."),
    HistoricalLocation("Louisville",    350, 143, "city",  43000, 1849,
        "Falls of the Ohio — bourbon and shipping."),
    HistoricalLocation("Memphis",       330, 160, "city",  23000, 1849,
        "Bluff City on the Mississippi — cotton king."),
    HistoricalLocation("Atlanta",       375, 162, "town",  10000, 1847,
        "Railroad junction — rebuilt after Sherman, boomed fast."),
    HistoricalLocation("New Orleans",   325, 218, "city", 116000, 1849,
        "The Crescent City — greatest port in the South."),
    HistoricalLocation("Charleston SC", 400, 165, "city",  20000, 1849,
        "South Carolina rice port — first shots of the Civil War."),

    # ── ALASKA ──────────────────────────────────────────────────────────────
    HistoricalLocation("Juneau",         45,  35, "town",   1000, 1880,
        "Gold Creek discovery — Alaska capital.", mining=True,
        gold_bias_override=0.85),
    HistoricalLocation("Skagway",        40,  38, "camp",   8000, 1897,
        "Gateway to the Klondike — Soapy Smith's town.", mining=True),
    HistoricalLocation("Nome AK",        30,  38, "town",   5000, 1899,
        "Beach placer gold — Nome gold rush 1899.", mining=True,
        gold_bias_override=0.90),
    HistoricalLocation("Fairbanks",      68,  28, "town",   3500, 1902,
        "Felix Pedro's gold strike — interior Alaska hub.", mining=True,
        gold_bias_override=0.88),
    HistoricalLocation("Sitka",          55,  40, "town",    600, 1799,
        "Old Russian capital of Alaska."),
    HistoricalLocation("Anchorage",      60,  50, "town",    300, 1914,
        "Alaska Railroad town — Cook Inlet."),

    # ── FORTS & TRAIL WAYPOINTS ─────────────────────────────────────────────
    HistoricalLocation("Fort Laramie",  235, 125, "fort",   500, 1834,
        "Oregon Trail waypoint — Army post controlling the Platte route."),
    HistoricalLocation("Fort Bridger",  200, 140, "fort",   200, 1843,
        "Jim Bridger's trading post — Oregon and California trails."),
    HistoricalLocation("Bent's Fort",   225, 170, "fort",   300, 1833,
        "Adobe trading post on the Santa Fe Trail."),
    HistoricalLocation("Fort Hall",     162, 132, "fort",   200, 1834,
        "Oregon Trail fort on the Snake River — crucial resupply point."),
]


class WorldGenerator:
    """
    Populates a WorldMap with the full historical location set and
    applies per-district gold bias hotspot overrides.

    Call after world_map._place_terrain() and _assign_regions_and_gold_bias().
    """

    def __init__(self, seed: int = 42):
        self.seed = seed

    def populate(self, world_map: "WorldMap") -> None:
        self._place_locations(world_map)
        self._apply_gold_overrides(world_map)

    def _place_locations(self, world_map: "WorldMap") -> None:
        from src.world_map import WorldLocation, Terrain

        for hloc in HISTORICAL_LOCATIONS:
            x, y = hloc.x, hloc.y
            if not world_map.in_bounds(x, y):
                continue
            # Don't duplicate if world_map._place_fixed_locations already ran
            if hloc.name in world_map.locations:
                continue
            loc = WorldLocation(
                name=hloc.name,
                x=x, y=y,
                location_type=hloc.loc_type,
                population=hloc.population,
                discovered=False,
            )
            world_map.locations[hloc.name] = loc
            if int(world_map.tiles[y, x]) == Terrain.OCEAN:
                world_map.tiles[y, x] = Terrain.PLAINS

        # Rebuild position index (merge with any existing entries)
        world_map._loc_by_pos = {
            (loc.x, loc.y): name
            for name, loc in world_map.locations.items()
        }

    def _apply_gold_overrides(self, world_map: "WorldMap") -> None:
        """Smear a radius-2 hotspot around each mining district location."""
        import numpy as np
        for hloc in HISTORICAL_LOCATIONS:
            if hloc.gold_bias_override is None:
                continue
            cx, cy = hloc.x, hloc.y
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    nx, ny = cx + dx, cy + dy
                    if world_map.in_bounds(nx, ny):
                        cur = float(world_map.gold_bias[ny, nx])
                        world_map.gold_bias[ny, nx] = max(cur, hloc.gold_bias_override)


# ── Query helpers used by NPC / rumor systems ──────────────────────────────

def era_locations(year: int) -> List[HistoricalLocation]:
    """All locations that exist by *year*."""
    return [loc for loc in HISTORICAL_LOCATIONS if loc.era_founded <= year]


def mining_locations(year: int) -> List[HistoricalLocation]:
    """Mining locations that exist by *year*."""
    return [loc for loc in HISTORICAL_LOCATIONS
            if loc.mining and loc.era_founded <= year]


def nearest_known_mining(player_x: int, player_y: int,
                          year: int, radius: int = 80
                          ) -> Optional[HistoricalLocation]:
    """
    Return the nearest mining location within *radius* world tiles,
    or None. Used by NPC rumor system to ground tips geographically.
    """
    best: Optional[HistoricalLocation] = None
    best_dist = float("inf")
    for loc in mining_locations(year):
        d = abs(loc.x - player_x) + abs(loc.y - player_y)
        if d < best_dist and d <= radius:
            best_dist = d
            best = loc
    return best
