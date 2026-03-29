"""
src/npc_data.py

Pure data tables for the NPC system.
Settlement demographics, profession weights, name pools by ethnicity,
personality trait tiers, hidden motivations, and skill/attribute biases.

All tables grounded in 1849-1865 American Gold Rush demographics.
No game logic lives here — only constants and lookup tables.
"""

from typing import Dict, List, Tuple

# ============================================================================
#  SETTLEMENT TYPES & DEMOGRAPHICS
# ============================================================================

SETTLEMENTS: Dict[str, dict] = {
    "mining_camp_small": {
        "label":           "Small Mining Camp",
        "pop_range":       (5, 25),
        "named_npc_range": (3, 8),
        "male_ratio":      0.96,      # almost entirely men
        "age_mean":        31,
        "age_std":         7,
        "age_min":         18,
        "age_max":         55,
    },
    "mining_camp_medium": {
        "label":           "Medium Mining Camp",
        "pop_range":       (25, 150),
        "named_npc_range": (6, 20),
        "male_ratio":      0.91,
        "age_mean":        32,
        "age_std":         9,
        "age_min":         16,
        "age_max":         62,
    },
    "boomtown": {
        "label":           "Boomtown",
        "pop_range":       (200, 6000),
        "named_npc_range": (20, 55),
        "male_ratio":      0.83,
        "age_mean":        29,
        "age_std":         10,
        "age_min":         15,
        "age_max":         70,
    },
    "small_town": {
        "label":           "Established Small Town",
        "pop_range":       (400, 5000),
        "named_npc_range": (25, 65),
        "male_ratio":      0.62,      # families present
        "age_mean":        34,
        "age_std":         15,
        "age_min":         14,
        "age_max":         80,
    },
    "trading_post": {
        "label":           "Trading Post / Waystation",
        "pop_range":       (3, 18),
        "named_npc_range": (2, 7),
        "male_ratio":      0.88,
        "age_mean":        38,
        "age_std":         10,
        "age_min":         18,
        "age_max":         65,
    },
}


# ============================================================================
#  ORIGIN / ETHNICITY  (weighted probabilities)
# ============================================================================
# Gold Rush California demographics — approximate composition:
#   American-born ~60%, Irish ~12%, Chinese ~10%, Mexican ~6%,
#   German ~5%, British/Australian ~3%, Chilean ~2%, Other ~2%

ORIGIN_WEIGHTS: List[Tuple[str, float]] = [
    # (ethnicity_key, cumulative_weight)  — picked by rng.random() < threshold
    ("american",    0.60),
    ("irish",       0.72),
    ("chinese",     0.82),
    ("mexican",     0.88),
    ("german",      0.93),
    ("british",     0.96),
    ("chilean",     0.98),
    ("other",       1.00),
]

# Which US state or foreign country they hail from (for backstory)
ORIGIN_HOMELANDS: Dict[str, List[str]] = {
    "american": [
        "New York", "Ohio", "Pennsylvania", "Missouri", "Kentucky",
        "Virginia", "Tennessee", "Massachusetts", "Illinois", "Indiana",
        "Connecticut", "Vermont", "Maine", "New Jersey", "Georgia",
        "North Carolina", "South Carolina", "Michigan", "Wisconsin",
        "Iowa", "Maryland",
    ],
    "irish":    ["County Cork", "County Kerry", "Dublin", "Galway",
                 "Limerick", "Tipperary", "Donegal", "Wexford"],
    "chinese":  ["Guangdong Province", "Taishan", "Xinhui",
                 "Kaiping", "Enping", "Zhongshan"],
    "mexican":  ["Sonora", "Sinaloa", "Durango", "Chihuahua",
                 "Jalisco", "Guanajuato", "Zacatecas"],
    "german":   ["Bavaria", "Prussia", "Saxony", "Baden",
                 "Württemberg", "Hesse", "Hanover"],
    "british":  ["London", "Cornwall", "Yorkshire", "Lancashire",
                 "Wales", "Scotland", "Sydney (Australia)",
                 "Melbourne (Australia)"],
    "chilean":  ["Valparaíso", "Santiago", "Coquimbo", "Copiapó"],
    "other":    ["Paris (France)", "Honolulu (Hawaii)",
                 "Montreal (Canada)", "Stockholm (Sweden)",
                 "Genoa (Italy)", "New Orleans (Free Person of Color)"],
}


# ============================================================================
#  NAME TABLES
# ============================================================================

NAMES_M: Dict[str, List[str]] = {
    "american": [
        "James", "John", "William", "Thomas", "George", "Charles", "Henry",
        "Robert", "Edward", "Joseph", "Samuel", "Daniel", "Frank", "Walter",
        "Elijah", "Ezra", "Luther", "Silas", "Amos", "Cyrus", "Caleb",
        "Isaac", "Abraham", "Josiah", "Nathaniel", "Hiram", "Levi", "Enoch",
        "Rufus", "Jedidiah", "Solomon", "Cornelius", "Augustus", "Orville",
        "Jasper", "Uriah", "Phineas", "Obadiah", "Zebulon", "Tobias",
    ],
    "irish": [
        "Patrick", "Michael", "Sean", "Liam", "Connor", "Brian", "Declan",
        "Timothy", "Brendan", "Seamus", "Padraig", "Finbar", "Cormac",
        "Eamon", "Kieran", "Niall", "Ronan", "Colm", "Fergus", "Donal",
    ],
    "chinese": [
        "Ah Sam", "Ah Sing", "Ah Fook", "Ah Wing", "Ah Chew", "Ah Lum",
        "Ah Toy", "Ah Bing", "Ah Kee", "Ah Wah", "Ah Gum", "Ah You",
        "Ah Jim", "Ah Fat", "Ah Quong", "Ah Moon", "Ah Chin", "Ah Lee",
    ],
    "mexican": [
        "Juan", "Pedro", "Francisco", "José", "Manuel", "Antonio",
        "Miguel", "Carlos", "Ramón", "Luis", "Jesús", "Rafael",
        "Diego", "Tomás", "Esteban", "Alejandro", "Ignacio", "Salvador",
    ],
    "german": [
        "Friedrich", "Heinrich", "Wilhelm", "Karl", "Johann", "Hans",
        "Otto", "Ernst", "Gustav", "Franz", "Ludwig", "Konrad",
        "Herman", "Gottfried", "August", "Dietrich", "Rudolph", "Albrecht",
    ],
    "british": [
        "Arthur", "Alfred", "Reginald", "Nigel", "Edmund", "Geoffrey",
        "Cecil", "Basil", "Neville", "Rupert", "Percival", "Humphrey",
        "Archibald", "Cedric", "Douglas", "Gordon", "Malcolm", "Angus",
    ],
    "chilean": [
        "Arturo", "Bernardo", "Claudio", "Domingo", "Ernesto",
        "Felipe", "Gonzalo", "Héctor", "Isidoro", "Jacinto",
    ],
    "other": [
        "Pierre", "Jacques", "Lars", "Sven", "Kekoa", "Kanoa",
        "Giuseppe", "Antoine", "Nikolai", "Emile", "Manu", "Henrik",
    ],
}

NAMES_F: Dict[str, List[str]] = {
    "american": [
        "Mary", "Sarah", "Elizabeth", "Margaret", "Emma", "Clara", "Alice",
        "Hannah", "Martha", "Catherine", "Helen", "Ruth", "Ida", "Edith",
        "Abigail", "Louisa", "Prudence", "Mercy", "Patience", "Charity",
        "Virginia", "Caroline", "Harriet", "Josephine", "Frances", "Lydia",
        "Matilda", "Phoebe", "Cordelia", "Lucinda", "Sophronia", "Minerva",
    ],
    "irish": [
        "Bridget", "Nora", "Kathleen", "Eileen", "Siobhan", "Aoife",
        "Maeve", "Deirdre", "Fiona", "Colleen", "Sinead", "Roisin",
    ],
    "chinese": [
        "Ah Mei", "Ah Lan", "Ah Ying", "Ah Fong", "Ah Yee", "Ah Lin",
    ],
    "mexican": [
        "María", "Guadalupe", "Rosa", "Carmen", "Josefa", "Dolores",
        "Consuelo", "Esperanza", "Luz", "Soledad", "Elena", "Isabel",
    ],
    "german": [
        "Anna", "Greta", "Liesel", "Helga", "Frieda", "Ingrid",
        "Gertrude", "Brunhilde", "Wilhelmina", "Elsa", "Marta", "Hilde",
    ],
    "british": [
        "Victoria", "Florence", "Constance", "Millicent", "Winifred",
        "Mabel", "Beatrice", "Agnes", "Cecilia", "Daphne", "Enid",
    ],
    "chilean": ["Catalina", "Francisca", "Macarena", "Valentina", "Javiera"],
    "other":   ["Colette", "Astrid", "Leilani", "Giulia", "Natasha", "Amélie"],
}

LAST_NAMES: Dict[str, List[str]] = {
    "american": [
        "Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis",
        "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson", "White",
        "Harris", "Martin", "Thompson", "Robinson", "Clark", "Lewis",
        "Walker", "Young", "King", "Wright", "Hill", "Scott", "Adams",
        "Baker", "Nelson", "Carter", "Mitchell", "Peabody", "Aldrich",
        "Chadwick", "Hollister", "Thatcher", "Whitfield", "Prescott",
    ],
    "irish": [
        "O'Brien", "Murphy", "Kelly", "Sullivan", "Walsh", "Flynn",
        "McCarthy", "Callahan", "Brennan", "Gallagher", "Doyle", "Ryan",
        "Fitzgerald", "Connolly", "Quinn", "Doherty", "Malone", "Duffy",
    ],
    "chinese": [
        "Wong", "Lee", "Chan", "Chen", "Fong", "Lau", "Yee", "Chin",
        "Kwong", "Chew", "Gee", "Mah", "Tam", "Woo", "Tong", "Leung",
    ],
    "mexican": [
        "Garcia", "Martinez", "Lopez", "Hernandez", "Gonzalez", "Rodriguez",
        "Ramirez", "Torres", "Flores", "Rivera", "Morales", "Ortiz",
        "Cruz", "Reyes", "Mendoza", "Vega", "Sandoval", "Aguilar",
    ],
    "german": [
        "Mueller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer",
        "Wagner", "Becker", "Hoffmann", "Schaefer", "Koch", "Richter",
        "Klein", "Wolf", "Schroeder", "Neumann", "Schwartz", "Braun",
    ],
    "british": [
        "Ashworth", "Blackwell", "Chambers", "Darcy", "Ellsworth",
        "Fairfax", "Greyson", "Hartley", "Irvine", "Jameson",
        "Kensington", "Langley", "McTavish", "Campbell", "Stewart",
    ],
    "chilean": [
        "Vásquez", "Rojas", "Muñoz", "Araya", "Soto", "Contreras",
    ],
    "other": [
        "Dubois", "Johansson", "Petersen", "Rossi", "Volkov", "Lafleur",
        "Kalani", "Nakamura", "Beaumont", "Moreau", "Delacroix",
    ],
}


# ============================================================================
#  PROFESSIONS  (weighted per settlement type, split by gender)
# ============================================================================

# Male profession weights per settlement type
PROF_WEIGHTS_M: Dict[str, Dict[str, int]] = {
    "mining_camp_small": {
        "Prospector": 40, "Miner": 20, "Cook": 8, "Teamster": 7,
        "Drifter": 10, "Gambler": 5, "Hunter": 5, "Merchant": 5,
    },
    "mining_camp_medium": {
        "Prospector": 26, "Miner": 16, "Merchant": 8, "Blacksmith": 6,
        "Saloon Keeper": 5, "Cook": 5, "Teamster": 5, "Gambler": 6,
        "Doctor": 3, "Drifter": 5, "Chinese Laborer": 8, "Hunter": 3,
        "Barber": 2, "Preacher": 2,
    },
    "boomtown": {
        "Prospector": 15, "Miner": 12, "Merchant": 9, "Blacksmith": 5,
        "Saloon Keeper": 5, "Gambler": 6, "Doctor": 3, "Lawyer": 3,
        "Banker": 2, "Assayer": 2, "Teamster": 5, "Freighter": 4,
        "Carpenter": 4, "Chinese Laborer": 7, "Barber": 2, "Drifter": 3,
        "Sheriff": 1, "Newspaper Editor": 1, "Express Rider": 2,
        "Preacher": 2, "Hunter": 2, "Scout": 2, "Cook": 2,
    },
    "small_town": {
        "Merchant": 10, "Farmer": 10, "Rancher": 8, "Blacksmith": 6,
        "Carpenter": 6, "Doctor": 3, "Lawyer": 4, "Banker": 2,
        "Saloon Keeper": 4, "Teamster": 5, "Preacher": 3, "Sheriff": 2,
        "Newspaper Editor": 1, "Assayer": 2, "Telegraph Operator": 1,
        "Prospector": 6, "Miner": 5, "Gambler": 4, "Barber": 3,
        "Cook": 3, "Freighter": 3, "Scout": 2, "Drifter": 3,
        "Chinese Laborer": 4, "Land Agent": 1,
    },
    "trading_post": {
        "Merchant": 25, "Teamster": 12, "Scout": 10, "Hunter": 10,
        "Trapper": 15, "Mountain Man": 8,
        "Cook": 8, "Drifter": 5, "Freighter": 5, "Blacksmith": 2,
    },
    "city": {
        "Merchant": 8, "Farmer": 6, "Rancher": 4, "Blacksmith": 5,
        "Carpenter": 5, "Doctor": 4, "Lawyer": 5, "Banker": 3,
        "Saloon Keeper": 4, "Teamster": 4, "Preacher": 3, "Sheriff": 2,
        "Newspaper Editor": 2, "Assayer": 2, "Telegraph Operator": 2,
        "Prospector": 4, "Miner": 3, "Gambler": 4, "Barber": 3,
        "Cook": 3, "Freighter": 3, "Scout": 1, "Drifter": 2,
        "Trapper": 2, "Baker": 2, "Butcher": 2, "Tailor": 2,
        "Apothecary": 1, "Cobbler": 1, "Undertaker": 1,
        "Land Agent": 2,
    },
}

# Female profession weights per settlement type
PROF_WEIGHTS_F: Dict[str, Dict[str, int]] = {
    "mining_camp_small": {
        "Laundress": 40, "Cook": 30, "Wife": 20, "Dancehall Girl": 10,
    },
    "mining_camp_medium": {
        "Laundress": 30, "Cook": 20, "Wife": 15, "Dancehall Girl": 12,
        "Boarding House Keeper": 10, "Healer": 8, "Merchant": 5,
    },
    "boomtown": {
        "Laundress": 18, "Dancehall Girl": 14, "Cook": 12,
        "Boarding House Keeper": 10, "Wife": 10, "Merchant": 8,
        "Healer": 6, "Seamstress": 6, "Teacher": 4, "Saloon Keeper": 4,
        "Actress": 4, "Prospector": 4,
    },
    "small_town": {
        "Wife": 20, "Teacher": 10, "Seamstress": 10,
        "Boarding House Keeper": 10, "Cook": 8, "Laundress": 8,
        "Merchant": 8, "Healer": 6, "Midwife": 5, "Dancehall Girl": 5,
        "Saloon Keeper": 3, "Farmer": 4, "Actress": 3,
    },
    "trading_post": {
        "Wife": 35, "Cook": 30, "Merchant": 15, "Healer": 10,
        "Laundress": 10,
    },
}


# ============================================================================
#  PROFESSION → ATTRIBUTE BIASES  (added on top of base 8 + 1d4)
# ============================================================================

PROF_ATTR_BIAS: Dict[str, Dict[str, int]] = {
    "Prospector":         {"wisdom": 2, "constitution": 2},
    "Miner":              {"strength": 3, "constitution": 3},
    "Merchant":           {"charisma": 3, "intelligence": 2},
    "Blacksmith":         {"strength": 4, "constitution": 2},
    "Saloon Keeper":      {"charisma": 3, "wisdom": 2},
    "Gambler":            {"charisma": 3, "agility": 2, "intelligence": 1},
    "Doctor":             {"intelligence": 4, "wisdom": 2},
    "Lawyer":             {"intelligence": 3, "charisma": 3},
    "Banker":             {"intelligence": 3, "charisma": 2},
    "Farmer":             {"strength": 2, "constitution": 3},
    "Rancher":            {"constitution": 2, "strength": 2, "wisdom": 1},
    "Carpenter":          {"strength": 2, "agility": 2, "intelligence": 1},
    "Scout":              {"agility": 3, "wisdom": 3},
    "Hunter":             {"agility": 2, "wisdom": 2, "constitution": 1},
    "Cook":               {"wisdom": 2, "constitution": 1},
    "Teamster":           {"strength": 2, "constitution": 2},
    "Freighter":          {"strength": 2, "constitution": 2},
    "Sheriff":            {"charisma": 2, "agility": 2, "wisdom": 2},
    "Preacher":           {"charisma": 3, "wisdom": 3},
    "Assayer":            {"intelligence": 4, "wisdom": 2},
    "Barber":             {"agility": 2, "charisma": 2},
    "Drifter":            {"agility": 2, "constitution": 1},
    "Chinese Laborer":    {"constitution": 3, "wisdom": 2},
    "Laundress":          {"constitution": 3, "strength": 1},
    "Dancehall Girl":     {"charisma": 4, "agility": 2},
    "Boarding House Keeper": {"wisdom": 2, "charisma": 2},
    "Healer":             {"wisdom": 3, "intelligence": 2},
    "Midwife":            {"wisdom": 3, "intelligence": 2},
    "Seamstress":         {"agility": 3, "wisdom": 1},
    "Teacher":            {"intelligence": 3, "charisma": 2},
    "Wife":               {"wisdom": 2, "constitution": 1},
    "Actress":            {"charisma": 4, "agility": 1},
    "Newspaper Editor":   {"intelligence": 3, "charisma": 2},
    "Telegraph Operator": {"intelligence": 3, "agility": 2},
    "Express Rider":      {"agility": 3, "constitution": 3},
}


# ============================================================================
#  PROFESSION → SKILL/KNOWLEDGE TABLES
# ============================================================================

PROF_SKILLS: Dict[str, Dict[str, int]] = {
    "Prospector":         {"placer": 3, "geology": 2, "survival": 2},
    "Miner":              {"hardRock": 4, "engineering": 2, "geology": 1},
    "Merchant":           {"trading": 4, "law": 2},
    "Blacksmith":         {"engineering": 4, "trading": 1},
    "Saloon Keeper":      {"trading": 3, "firearms": 1},
    "Gambler":            {"trading": 2, "firearms": 1},
    "Doctor":             {"firstAid": 5, "chemistry": 3},
    "Lawyer":             {"law": 5, "trading": 2},
    "Banker":             {"trading": 4, "law": 3},
    "Farmer":             {"farming": 4, "survival": 2},
    "Rancher":            {"farming": 3, "survival": 3, "firearms": 2, "tracking": 1},
    "Carpenter":          {"engineering": 3, "survival": 1},
    "Scout":              {"tracking": 5, "survival": 4, "firearms": 4},
    "Hunter":             {"tracking": 4, "survival": 3, "firearms": 4},
    "Trapper":            {"trapping": 5, "tracking": 4, "survival": 4, "furriery": 3, "engineering": 2, "trading": 2},
    "Mountain Man":       {"trapping": 6, "tracking": 5, "survival": 5, "firearms": 4, "furriery": 4, "engineering": 3},
    "Cook":               {"survival": 2},
    "Teamster":           {"driving": 3, "survival": 2},
    "Freighter":          {"driving": 3, "trading": 2, "survival": 2},
    "Sheriff":            {"firearms": 4, "law": 3, "tracking": 2},
    "Preacher":           {"literacy": 2},
    "Assayer":            {"assaying": 5, "geology": 3, "chemistry": 2},
    "Barber":             {"firstAid": 2},
    "Drifter":            {"survival": 3, "firearms": 2},
    "Chinese Laborer":    {"placer": 3, "engineering": 1, "survival": 2},
    "Laundress":          {"survival": 1, "trading": 1},
    "Dancehall Girl":     {"trading": 1},
    "Boarding House Keeper": {"trading": 2, "survival": 1},
    "Healer":             {"firstAid": 4, "chemistry": 2, "survival": 2},
    "Midwife":            {"firstAid": 4},
    "Seamstress":         {"trading": 1},
    "Teacher":            {"literacy": 3, "law": 1},
    "Wife":               {"survival": 1, "farming": 1},
    "Actress":            {"trading": 1},
    "Newspaper Editor":   {"literacy": 4, "law": 2},
    "Telegraph Operator": {"literacy": 2, "engineering": 1},
    "Express Rider":      {"driving": 3, "firearms": 3, "survival": 3},
    "Land Agent":         {"law": 4, "trading": 3},
}

PROF_KNOWLEDGE: Dict[str, Dict[str, int]] = {
    "Prospector":   {"placer": 3, "geology": 2},
    "Miner":        {"hardRock": 3, "geology": 2, "assaying": 1},
    "Assayer":      {"assaying": 4, "geology": 3, "chemistry": 2},
    "Doctor":       {"firstAid": 4, "chemistry": 3},
    "Lawyer":       {"law": 4, "trading": 1},
    "Blacksmith":   {"engineering": 3},
    "Carpenter":    {"engineering": 2, "cabin building": 3},
    "Scout":        {"tracking": 4, "survival": 3, "navigation": 3},
    "Hunter":       {"tracking": 3, "survival": 3, "butchering": 2},
    "Trapper":      {"trapping": 4, "tracking": 3, "survival": 3, "furriery": 2},
    "Mountain Man": {"trapping": 5, "tracking": 4, "survival": 4, "furriery": 3, "geology": 2},
    "Farmer":       {"farming": 3},
    "Rancher":      {"farming": 2, "tracking": 1, "horse handling": 2},
    "Merchant":     {"trading": 3, "law": 1},
    "Saloon Keeper":{"trading": 2, "cooking": 1},
    "Healer":       {"firstAid": 3, "herbalism": 3},
    "Midwife":      {"firstAid": 3, "herbalism": 2},
    "Teacher":      {"literacy": 3, "history": 2},
    "Preacher":     {"literacy": 2},
    "Teamster":     {"horse handling": 3, "navigation": 1},
    "Chinese Laborer": {"placer": 2, "cooking": 2},
    "Land Agent":      {"law": 4, "trading": 2, "surveying": 3},
}

# Personal background knowledge — random extras added during generation
PERSONAL_KNOWLEDGE_POOL: List[str] = [
    "cabin building", "horse handling", "cooking", "navigation",
    "rope work", "carpentry", "hunting", "fishing", "blacksmithing",
    "leather work", "farming basics", "herbalism", "sewing",
    "music", "distilling", "animal husbandry", "masonry",
    "explosives", "surveying", "astronomy",
]


# ============================================================================
#  PERSONALITY TRAIT TIERS  (weighted by rarity)
# ============================================================================
# Each NPC gets 2-4 traits. Roll for tier, then pick randomly within tier.
# This produces a population that is mostly normal, with outliers being rare.

TRAIT_TIERS: Dict[str, dict] = {
    "common": {
        "weight": 70,
        "traits": [
            "hardworking", "quiet", "cautious", "practical", "stoic",
            "patient", "reliable", "plain-spoken", "reserved", "steady",
            "earnest", "devout", "thrifty", "mild", "decent",
        ],
    },
    "uncommon": {
        "weight": 25,
        "traits": [
            "boastful", "suspicious", "generous", "greedy", "hot-tempered",
            "nervous", "ambitious", "reckless", "charming", "melancholy",
            "superstitious", "bitter", "jovial", "cunning", "vain",
            "stubborn", "impulsive", "sly", "lecherous", "cowardly",
            "brave", "vindictive", "sentimental", "manipulative",
        ],
    },
    "rare": {
        "weight": 5,
        "traits": [
            "cruel", "fanatical", "paranoid", "saintly",
            "psychopathic", "pathological liar", "berserker",
            "visionary", "utterly fearless", "genius-level cunning",
        ],
    },
}

# Pairs that cannot coexist on the same NPC
TRAIT_CONTRADICTIONS: List[Tuple[str, str]] = [
    ("generous", "greedy"),
    ("brave", "cowardly"),
    ("patient", "impulsive"),
    ("quiet", "boastful"),
    ("reserved", "jovial"),
    ("cautious", "reckless"),
    ("saintly", "cruel"),
    ("saintly", "psychopathic"),
    ("devout", "psychopathic"),
    ("mild", "hot-tempered"),
    ("stoic", "nervous"),
    ("honest", "pathological liar"),
    ("honest", "sly"),
]


# ============================================================================
#  HIDDEN MOTIVATIONS  (weighted by rarity)
# ============================================================================
# Every NPC has 1-2 hidden motivations that drive their behavior.
# The player discovers these through high Wisdom / conversation / observation.

MOTIVATION_TIERS: Dict[str, dict] = {
    "common": {
        "weight": 60,
        "motivations": [
            "find gold and get rich",
            "earn enough to buy farmland back home",
            "provide for family back east",
            "start a new life out west",
            "make a steady living",
            "build a homestead",
            "see the country and have adventures",
            "follow a friend or relative who came first",
        ],
    },
    "uncommon": {
        "weight": 30,
        "motivations": [
            "escape a criminal past",
            "find a missing brother or father",
            "pay off crushing debt to a dangerous man",
            "prove themselves after a humiliation",
            "flee a failed or abusive marriage",
            "seek revenge against someone out here",
            "carry out a religious mission",
            "establish a business empire",
            "drink and gamble away grief",
            "looking for a spouse and family",
            "running from the law back east",
            "desperately avoiding starvation and ruin",
        ],
    },
    "rare": {
        "weight": 10,
        "motivations": [
            "on the run after killing a man",
            "hunting a specific person to murder",
            "building a criminal operation",
            "government agent sent to investigate",
            "escaped from slavery, will fight before going back",
            "slowly going mad from mercury exposure",
            "plans to rob the express office",
            "wants to start a utopian community",
        ],
    },
}


# ============================================================================
#  BEHAVIORAL QUIRKS  (LLM flavor — optional, 0-2 per NPC)
# ============================================================================
# These are passed to the LLM to make dialogue feel distinct.

QUIRK_POOL: List[str] = [
    "spits tobacco constantly",
    "quotes scripture in casual conversation",
    "can't stop talking about their mother's cooking",
    "hums while working",
    "always whittling something",
    "picks teeth with a knife",
    "has a nervous laugh",
    "tells the same three stories over and over",
    "never makes eye contact",
    "stares too long at people",
    "speaks extremely slowly",
    "talks fast and interrupts",
    "obsessively cleans their tools",
    "gives everything a nickname",
    "has an elaborate handshake",
    "refuses to work on Sundays",
    "keeps a worn daguerreotype in their pocket",
    "counts everything (steps, coins, people)",
    "addresses everyone as 'partner'",
    "won't eat anything they didn't cook themselves",
    "always carries a particular lucky charm",
    "scratches behind their ear when lying",
    "mutters calculations under their breath",
    "ends every other sentence with 'God willing'",
    "squints hard at everything, probably needs spectacles",
]


# ============================================================================
#  BACKSTORY ELEMENTS  (revealed through conversation)
# ============================================================================
# Hidden facts chosen per-NPC during generation. Revealed one at a time
# through conversation. The "Mr. Jenkins Rule" applies: unrevealed past
# is fair game for retroactive skill anchoring.

BACKSTORY_HOOKS: Dict[str, List[str]] = {
    "family": [
        "Married with children back home",
        "Widower — wife died of cholera two years ago",
        "Unmarried, never been interested in settling down",
        "Has a young wife waiting in {homeland}",
        "Left a fiancée behind and swore to return rich",
        "Has seven brothers, all scattered across the frontier",
        "Raised by grandparents after parents died young",
        "Estranged from father over an inheritance dispute",
    ],
    "past": [
        "Former soldier in the Mexican-American War",
        "Ran from debt back east",
        "Lost a partner to fever last winter",
        "Worked as a carpenter before coming west",
        "Was a schoolteacher who got bored",
        "Deserted from the Army",
        "Was a sailor on a whaling ship",
        "Former slave, freed themselves",
        "Served time in prison for theft",
        "Trained as a doctor but lost their nerve after a patient died",
        "Worked the Erie Canal before it got slow",
        "Was a preacher who lost their faith",
        "Ran a successful business that burned down",
    ],
    "secret": [
        "Has a warrant out for them under another name",
        "Killed a man in self-defense but nobody believes it",
        "Hiding a cache of gold nobody knows about",
        "Writes letters to a dead wife as though she's alive",
        "Can't actually read, pretends they can",
        "Terrified of going underground after a cave-in",
        "Addicted to laudanum",
        "Has a bounty on their head from back east",
    ],
}


# ============================================================================
#  RELATIONSHIP LABELS  (backward-compatible with existing npc.py)
# ============================================================================

REL_LABELS: Dict[Tuple[int, int], str] = {
    (-100, -60): "Sworn Enemy",
    (-60,  -30): "Hostile",
    (-30,  -10): "Unfriendly",
    (-10,    5): "Stranger",
    (  5,   20): "Acquaintance",
    ( 20,   40): "Friendly",
    ( 40,   60): "Friend",
    ( 60,   80): "Close Friend",
    ( 80,  100): "Trusted Companion",
}

ROMANTIC_LABELS: Dict[Tuple[int, int], str] = {
    (  0,  15): "",                # no visible interest
    ( 15,  30): "Curious",
    ( 30,  50): "Attracted",
    ( 50,  70): "Smitten",
    ( 70,  90): "Deeply in Love",
    ( 90, 100): "Devoted",
}


# ============================================================================
#  ROMANCE COMPATIBILITY FACTORS
# ============================================================================
# Charisma differences, shared traits, etc. affect romance speed.

ROMANCE_TRAIT_BONUSES: Dict[str, float] = {
    # Player trait → bonus to romantic interest gain per interaction
    "charming":    +2.0,
    "generous":    +1.5,
    "brave":       +1.0,
    "honest":      +1.0,
    "sentimental": +0.5,
    "cruel":       -3.0,
    "greedy":      -1.5,
    "cowardly":    -1.0,
    "lecherous":   -2.0,
    "psychopathic":-5.0,
}
