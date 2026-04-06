"""
src/tribal_system.py

Native American tribal interaction system for American Prospector.

Manages tribal standings, territory, language progression, trade modifiers,
raid checks, patrol encounters, camp population, and whiskey-trade
consequences.  Designed for the fur-trade era (1830s-1850s) setting.

Integration — in engine.py, create on init:
    from src.tribal_system import TribalSystem
    self.tribal = TribalSystem(seed=self.world.seed)

Daily tick:
    messages = self.tribal.tick_daily(player.world_x, player.world_y, day, rng)

Territory entry:
    msg = self.tribal.check_territory_entry(wx, wy, last_tribes)

Serialization:
    save_data["tribal"] = self.tribal.to_dict()
    self.tribal = TribalSystem.from_dict(save_data["tribal"])
"""

import math
import random as _r
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.player import Player


# ============================================================================
#  DATA STRUCTURES
# ============================================================================

@dataclass
class TribalStanding:
    """Player's relationship with a single tribe."""
    standing: int = 0                     # -100 (blood enemy) to +100 (adopted kin)
    language_level: str = "sign"          # "sign" | "pidgin" | "fluent"
    days_near_tribe: int = 0
    has_trapping_rights: bool = False
    has_safe_passage: bool = False
    adopted: bool = False
    captive: bool = False              # player is held captive by this tribe
    captive_days: int = 0              # days in captivity
    escape_attempts: int = 0           # failed escapes increase guard alertness
    bride_price_paid: bool = False
    last_contact_day: int = 0
    whiskey_units_traded: int = 0
    whiskey_debt_standing: int = 0        # accumulated negative delta not yet applied
    events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "standing": self.standing,
            "language_level": self.language_level,
            "days_near_tribe": self.days_near_tribe,
            "has_trapping_rights": self.has_trapping_rights,
            "has_safe_passage": self.has_safe_passage,
            "adopted": self.adopted,
            "captive": self.captive,
            "captive_days": self.captive_days,
            "escape_attempts": self.escape_attempts,
            "bride_price_paid": self.bride_price_paid,
            "last_contact_day": self.last_contact_day,
            "whiskey_units_traded": self.whiskey_units_traded,
            "whiskey_debt_standing": self.whiskey_debt_standing,
            "events": list(self.events),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TribalStanding":
        return cls(
            standing=d.get("standing", 0),
            language_level=d.get("language_level", "sign"),
            days_near_tribe=d.get("days_near_tribe", 0),
            has_trapping_rights=d.get("has_trapping_rights", False),
            has_safe_passage=d.get("has_safe_passage", False),
            adopted=d.get("adopted", False),
            captive=d.get("captive", False),
            captive_days=d.get("captive_days", 0),
            escape_attempts=d.get("escape_attempts", 0),
            bride_price_paid=d.get("bride_price_paid", False),
            last_contact_day=d.get("last_contact_day", 0),
            whiskey_units_traded=d.get("whiskey_units_traded", 0),
            whiskey_debt_standing=d.get("whiskey_debt_standing", 0),
            events=list(d.get("events", [])),
        )


# ============================================================================
#  STANDING THRESHOLDS & LABELS
# ============================================================================

STANDING_ENEMY    = -50
STANDING_HOSTILE  = -20
STANDING_WARY     =   0
STANDING_NEUTRAL  =  20
STANDING_FRIENDLY =  50

_LABELS = [
    (STANDING_ENEMY,        "Blood Enemy"),
    (STANDING_HOSTILE,      "Hostile"),
    (STANDING_WARY + 1,     "Wary"),       # standing <= 0 is Wary
    (STANDING_NEUTRAL,      "Neutral"),
    (STANDING_FRIENDLY,     "Friendly"),
    (101,                   "Honored Ally"),  # sentinel — anything >= FRIENDLY
]


def standing_label(standing: int) -> str:
    """Human-readable label for a numeric standing value."""
    for threshold, label in _LABELS:
        if standing < threshold:
            return label
    return "Honored Ally"


# ============================================================================
#  STANDING DELTAS — how actions change standing
# ============================================================================

STANDING_DELTAS: Dict[str, int] = {
    "kill_member":        -50,
    "steal_horse":        -30,
    "trespass":           -10,
    "desecrate_burial":   -40,
    "break_promise":      -15,
    "attack_ally":        -20,
    "sell_weapons_enemy":  -25,
    "whiskey_trade":        3,
    "whiskey_aftermath":   -8,
    "trade":                5,
    "gift":                10,
    "gift_tobacco":        12,
    "gift_blanket":        15,
    "return_horse":        20,
    "save_life":           30,
    "marriage":            40,
    "share_meat":           8,
    "help_hunt":           10,
    "give_medicine":       15,
    "guide_service":        5,
    "attend_ceremony":     10,
    "learn_language":       3,
    "betray_trust":       -35,
}


# ============================================================================
#  TRIBAL TERRITORIES  (world-map coordinates, 520 x 340 grid)
# ============================================================================

@dataclass
class TerritoryDef:
    center_x: int
    center_y: int
    radius: int
    temperament: str      # "aggressive" | "cautious" | "welcoming" | "neutral"
    regions: List[str]    # region names this tribe inhabits


TRIBAL_TERRITORIES: Dict[str, TerritoryDef] = {
    "Blackfeet": TerritoryDef(190, 85, 35, "aggressive",
        ["Montana Goldfields", "Rocky Mountains"]),
    "Crow": TerritoryDef(215, 100, 30, "neutral",
        ["Montana Goldfields", "Great Plains"]),
    "Shoshone": TerritoryDef(185, 135, 35, "cautious",
        ["Rocky Mountains", "Idaho Silver Belt"]),
    "Flathead": TerritoryDef(165, 95, 25, "welcoming",
        ["Montana Goldfields", "Idaho Silver Belt"]),
    "Nez Perce": TerritoryDef(150, 100, 30, "welcoming",
        ["Idaho Silver Belt", "Pacific Northwest"]),
    "Ute": TerritoryDef(210, 160, 30, "cautious",
        ["Rocky Mountains", "Nevada Great Basin"]),
    "Arapaho": TerritoryDef(240, 140, 30, "neutral",
        ["Rocky Mountains", "Great Plains"]),
    "Cheyenne": TerritoryDef(260, 130, 35, "aggressive",
        ["Great Plains", "Rocky Mountains"]),
    "Lakota Sioux": TerritoryDef(280, 110, 40, "aggressive",
        ["Great Plains", "Black Hills"]),
    # ── Eastern tribes (Long Hunter era) ──────────────────────────────
    "Shawnee": TerritoryDef(340, 185, 25, "aggressive",
        ["Appalachians", "Ohio Valley"]),
    "Cherokee": TerritoryDef(350, 205, 30, "cautious",
        ["Appalachians", "Gulf Coast"]),
    "Chickasaw": TerritoryDef(320, 210, 20, "aggressive",
        ["Gulf Coast", "Great Plains"]),
    "Creek": TerritoryDef(340, 220, 25, "cautious",
        ["Gulf Coast", "Appalachians"]),
    "Delaware": TerritoryDef(360, 178, 15, "neutral",
        ["Appalachians"]),
    "Iroquois": TerritoryDef(370, 165, 25, "cautious",
        ["Appalachians"]),
    "Miami": TerritoryDef(340, 178, 15, "aggressive",
        ["Appalachians", "Ohio Valley"]),
    "Mingo": TerritoryDef(350, 180, 10, "aggressive",
        ["Appalachians"]),
}


# ============================================================================
#  TRIBAL RELATIONS — historical alliances and enmities
# ============================================================================

TRIBAL_RELATIONS: Dict[Tuple[str, str], int] = {
    ("Blackfeet", "Crow"):            -60,
    ("Blackfeet", "Flathead"):        -40,
    ("Blackfeet", "Shoshone"):        -50,
    ("Blackfeet", "Nez Perce"):       -30,
    ("Crow", "Shoshone"):              30,
    ("Crow", "Nez Perce"):             20,
    ("Crow", "Lakota Sioux"):         -50,
    ("Flathead", "Nez Perce"):         40,
    ("Flathead", "Shoshone"):          30,
    ("Shoshone", "Ute"):               20,
    ("Cheyenne", "Arapaho"):           50,
    ("Cheyenne", "Lakota Sioux"):      40,
    ("Arapaho", "Lakota Sioux"):       30,
    ("Lakota Sioux", "Crow"):         -50,
    ("Lakota Sioux", "Shoshone"):     -30,
    ("Ute", "Arapaho"):              -20,
    ("Ute", "Cheyenne"):             -20,
}


def _get_relation(tribe_a: str, tribe_b: str) -> int:
    """Look up the relation between two tribes (order-independent)."""
    if (tribe_a, tribe_b) in TRIBAL_RELATIONS:
        return TRIBAL_RELATIONS[(tribe_a, tribe_b)]
    if (tribe_b, tribe_a) in TRIBAL_RELATIONS:
        return TRIBAL_RELATIONS[(tribe_b, tribe_a)]
    return 0


# ============================================================================
#  NATIVE TRADE DEMAND — item_id -> price multiplier
# ============================================================================

NATIVE_DEMAND: Dict[str, float] = {
    "trade_beads":       2.0,
    "trade_blanket":     2.5,
    "tobacco":           3.0,
    "percussion_rifle":  4.0,
    "flintlock_rifle":   3.5,
    "trade_gun":         2.0,
    "hunting_knife":     2.5,
    "hand_axe":          3.0,
    "gunpowder":         3.0,
    "rifle_ball":        2.0,
    "rifle_ball_flint":  2.0,
    "whiskey":           1.5,
    "flour":             1.5,
}


# ============================================================================
#  NATIVE NAMES — by tribe, male and female
# ============================================================================

NATIVE_NAMES: Dict[str, Dict[str, List[str]]] = {
    "Blackfeet": {
        "male":   ["Running Eagle", "Heavy Runner", "Mountain Chief",
                   "Low Horn", "Big Lake", "Calf Shirt", "Iron Shirt",
                   "Seen From Afar"],
        "female": ["Natawista", "Double Strike Woman", "Elk Woman",
                   "Running Antelope Woman", "Singing Water", "Morning Star"],
    },
    "Crow": {
        "male":   ["Rotten Belly", "Long Hair", "Plenty Coups", "Iron Bull",
                   "Sits In The Middle", "Bear Wolf", "Two Leggings",
                   "White Man Runs Him"],
        "female": ["Pretty Shield", "The Other Magpie", "Pine Leaf",
                   "Comes Toward", "Bird Woman", "Otter Woman"],
    },
    "Shoshone": {
        "male":   ["Washakie", "Pocatello", "Bear Hunter", "Tendoy",
                   "Sagwitch", "Sharp Nose", "Bazil"],
        "female": ["Sacagawea", "Wadze-Wipe", "Sheepeater Woman",
                   "Crying Wind", "Antelope Girl", "Dawn Mist"],
    },
    "Flathead": {
        "male":   ["Victor", "Charlot", "Big Face", "Ambrose",
                   "Three Eagles", "Red Hawk", "Bear Looking Back"],
        "female": ["Louise", "Josephine", "Catherine", "Running Deer",
                   "Quiet Stream", "Willow Branch"],
    },
    "Nez Perce": {
        "male":   ["Old Joseph", "Young Joseph", "Looking Glass", "White Bird",
                   "Toohoolhoolzote", "Ollokot", "Yellow Wolf", "Poker Joe"],
        "female": ["Wetatommi", "Springtime", "About Sleep", "Helping Another",
                   "Sound Of Running Feet", "Fair Land"],
    },
    "Ute": {
        "male":   ["Walkara", "Ouray", "Kanosh", "Tabeguache",
                   "Colorow", "Piah", "Nicaagat"],
        "female": ["Chipeta", "Susan", "Morning Cloud", "Dancing Fawn",
                   "Gentle Rain", "Bright Moon"],
    },
    "Arapaho": {
        "male":   ["Little Raven", "Left Hand", "Friday", "Sharp Nose",
                   "Black Coal", "Yellow Calf", "Broken Horn"],
        "female": ["Grass Woman", "Yellow Bead Woman", "Feather On Head",
                   "Pretty Nose", "Singing Bird", "Moon Shadow"],
    },
    "Cheyenne": {
        "male":   ["Black Kettle", "Dull Knife", "Little Wolf",
                   "Roman Nose", "Tall Bull", "White Antelope",
                   "Two Moons", "Morning Star Chief"],
        "female": ["Buffalo Calf Road Woman", "Ehyophsta", "Island Woman",
                   "Monahsetah", "White Buffalo Woman", "Blue Bead"],
    },
    "Lakota Sioux": {
        "male":   ["Sitting Bull", "Crazy Horse", "Red Cloud", "Spotted Tail",
                   "Rain In The Face", "Gall", "American Horse",
                   "Touch The Clouds", "Crow Dog"],
        "female": ["Moving Robe Woman", "Brown Weasel Woman", "Walks Pretty",
                   "Good Elk Woman", "Red Whirlwind", "Blue Blanket Woman"],
    },
    # ── Eastern tribes ────────────────────────────────────────────────
    "Shawnee": {
        "male":   ["Cornstalk", "Blue Jacket", "Tecumseh", "Black Hoof",
                   "Black Fish", "Puckeshinwa", "Chiksika", "Captain Johnny"],
        "female": ["Nonhelema", "Methoataske", "Tecumapease",
                   "Grenadier Squaw", "Silver Heels", "Corn Flower"],
    },
    "Cherokee": {
        "male":   ["Dragging Canoe", "Attakullakulla", "Oconostota",
                   "Old Tassel", "Doublehead", "The Raven", "Sequoyah",
                   "Bloody Fellow"],
        "female": ["Nancy Ward", "Nanyehi", "Ahyoka", "Katahdin",
                   "Morning Dew", "Running Water", "Corn Blossom"],
    },
    "Chickasaw": {
        "male":   ["Piomingo", "Tishomingo", "Levi Colbert", "Wolf's Friend",
                   "Ugulayacabe", "Mingo Houma", "Red Shoes"],
        "female": ["Aiminta", "Morning Star", "Shell Shaker",
                   "Quiet Water", "Dancing Wind"],
    },
    "Creek": {
        "male":   ["Alexander McGillivray", "William Weatherford",
                   "Red Eagle", "Menawa", "Opothle Yoholo",
                   "Mad Dog", "Emistisiguo"],
        "female": ["Sehoy", "Wind Clan Woman", "Polly Colbert",
                   "River Song", "Tall Grass Woman"],
    },
    "Delaware": {
        "male":   ["Teedyuscung", "White Eyes", "Killbuck",
                   "Captain Pipe", "Buckongahelas", "Gelelemend"],
        "female": ["Weeping Willow", "Bright Moon", "Still Water",
                   "Red Berry", "Snow Bird"],
    },
    "Iroquois": {
        "male":   ["Joseph Brant", "Cornplanter", "Red Jacket",
                   "Handsome Lake", "Hiawatha", "Sayenqueraghta"],
        "female": ["Molly Brant", "Jigonhsasee", "Sky Woman",
                   "She Who Watches", "Clan Mother"],
    },
    "Miami": {
        "male":   ["Little Turtle", "Pacanne", "Le Gris",
                   "Jean Baptiste Richardville", "Owl"],
        "female": ["Tacumwah", "Sweet Breeze", "Morning Rain",
                   "Wren Song", "Moon Face"],
    },
    "Mingo": {
        "male":   ["Logan", "Half King", "Scarouady",
                   "Pluggy", "Captain Pipe"],
        "female": ["Koonay", "Autumn Leaf", "Clear Stream",
                   "Falling Star", "White Cloud"],
    },
}


# ============================================================================
#  CAMP ROLES — NPC composition for a native camp
# ============================================================================

CAMP_ROLES: List[Tuple[str, int, int]] = [
    ("Chief",          1, 1),   # (occupation, min_count, max_count)
    ("Warrior",        2, 5),
    ("Native Trader",  0, 1),
    ("Native Guide",   0, 1),
    ("Hunter",         1, 2),
]


# ============================================================================
#  TALK TOPICS — filtered by language level
# ============================================================================

_TOPIC_LEVELS: Dict[str, str] = {
    "trade":            "sign",
    "directions":       "sign",
    "weather":          "sign",
    "peace_greeting":   "sign",
    "territory_warn":   "sign",
    "hunt_request":     "pidgin",
    "tribal_news":      "pidgin",
    "guide_hire":       "pidgin",
    "trapping_rights":  "pidgin",
    "safe_passage":     "pidgin",
    "ceremony":         "pidgin",
    "alliance":         "fluent",
    "marriage":         "fluent",
    "adoption":         "fluent",
    "war_council":      "fluent",
    "tribal_history":   "fluent",
    "sacred_places":    "fluent",
    "medicine":         "fluent",
}

_LANG_ORDER = {"sign": 0, "pidgin": 1, "fluent": 2}


# ============================================================================
#  TRIBAL SYSTEM — main class
# ============================================================================

class TribalSystem:
    """Manages all tribal interactions, standings, and territory checks."""

    def __init__(self, seed: int = 0):
        self.seed = seed
        self.standings: Dict[str, TribalStanding] = {}
        self.territories = TRIBAL_TERRITORIES
        self._last_tribes: List[str] = []

    # -- standing access -----------------------------------------------------

    def get_standing(self, tribe: str) -> TribalStanding:
        """Return the standing for *tribe*, creating a default if new."""
        if tribe not in self.standings:
            # Start wary-to-neutral depending on tribe temperament
            default = 0
            terr = self.territories.get(tribe)
            if terr:
                default = {"aggressive": -10, "cautious": 5,
                           "welcoming": 15, "neutral": 0}.get(
                               terr.temperament, 0)
            self.standings[tribe] = TribalStanding(standing=default)
        return self.standings[tribe]

    def adjust_standing(self, tribe: str, delta: int, reason: str,
                        day: int) -> None:
        """Change standing, clamp, log event, and cascade to allies/enemies."""
        ts = self.get_standing(tribe)
        old = ts.standing
        ts.standing = max(-100, min(100, ts.standing + delta))
        ts.last_contact_day = day
        ts.events.append({
            "day": day, "delta": delta, "reason": reason,
            "old": old, "new": ts.standing,
        })
        # Trim event log to last 50 entries
        if len(ts.events) > 50:
            ts.events = ts.events[-50:]

        # Threshold crossings — grant/revoke privileges
        if ts.standing >= STANDING_FRIENDLY and not ts.has_safe_passage:
            ts.has_safe_passage = True
        if ts.standing < STANDING_WARY:
            ts.has_safe_passage = False
            ts.has_trapping_rights = False

        # Cascade: allied/enemy tribes feel 30 % of the delta
        cascade = int(delta * 0.3)
        if cascade == 0:
            return
        for other_tribe in self.territories:
            if other_tribe == tribe:
                continue
            rel = _get_relation(tribe, other_tribe)
            if rel == 0:
                continue
            # Allies share sentiment; enemies invert it
            if rel > 0:
                cdelta = cascade
            else:
                cdelta = -cascade
            ots = self.get_standing(other_tribe)
            ots.standing = max(-100, min(100, ots.standing + cdelta))

    # -- territory -----------------------------------------------------------

    def get_territory_at(self, wx: int, wy: int) -> List[str]:
        """Return names of tribes whose territory covers (wx, wy)."""
        result: List[str] = []
        for name, td in self.territories.items():
            dx = wx - td.center_x
            dy = wy - td.center_y
            if dx * dx + dy * dy <= td.radius * td.radius:
                result.append(name)
        return result

    def check_territory_entry(self, wx: int, wy: int,
                              last_tribes: List[str]) -> Optional[str]:
        """Return a message if the player entered a new tribe's territory."""
        current = self.get_territory_at(wx, wy)
        new_entries = [t for t in current if t not in last_tribes]
        if not new_entries:
            return None
        parts = []
        for t in new_entries:
            ts = self.get_standing(t)
            lbl = standing_label(ts.standing)
            parts.append(f"You have entered {t} territory. ({lbl})")
            if ts.standing < STANDING_WARY:
                parts.append("  Travel here is dangerous.")
            elif ts.has_safe_passage:
                parts.append("  You have safe passage.")
        return " ".join(parts)

    # -- language ------------------------------------------------------------

    def get_language_level(self, tribe: str) -> str:
        return self.get_standing(tribe).language_level

    def _advance_language(self, tribe: str) -> Optional[str]:
        """Check for language level-up based on days near tribe."""
        ts = self.get_standing(tribe)
        lvl = ts.language_level
        days = ts.days_near_tribe
        msg = None
        if lvl == "sign" and days >= 14:
            ts.language_level = "pidgin"
            msg = f"You can now speak pidgin {tribe} — basic conversation is possible."
        elif lvl == "pidgin" and days >= 60:
            ts.language_level = "fluent"
            msg = f"You are now fluent in the {tribe} language."
        return msg

    # -- talk topics ---------------------------------------------------------

    def get_talk_topics(self, npc_tribe: str, standing: int) -> List[str]:
        """Filter available conversation topics by language level and standing."""
        lvl = self.get_language_level(npc_tribe)
        lvl_idx = _LANG_ORDER.get(lvl, 0)
        topics: List[str] = []
        for topic, req_lvl in _TOPIC_LEVELS.items():
            if _LANG_ORDER.get(req_lvl, 0) <= lvl_idx:
                # Some topics require positive standing
                if topic in ("alliance", "war_council", "adoption") and \
                        standing < STANDING_FRIENDLY:
                    continue
                if topic in ("marriage", "sacred_places") and \
                        standing < STANDING_NEUTRAL:
                    continue
                topics.append(topic)
        return topics

    # -- trade modifier ------------------------------------------------------

    def get_trade_modifier(self, tribe: str) -> float:
        """Price modifier for trading with this tribe.  Lower = better deal."""
        ts = self.get_standing(tribe)
        # Language bonus: sign=0, pidgin=0.15, fluent=0.30
        lang_bonus = {"sign": 0.0, "pidgin": 0.15, "fluent": 0.30}.get(
            ts.language_level, 0.0)
        # Standing bonus: -0.2 to +0.3 mapped from -100..100
        stand_bonus = (ts.standing / 100.0) * 0.3
        # Base modifier 1.0; lower is better for the player
        return max(0.4, 1.0 - lang_bonus - stand_bonus)

    # -- raids ---------------------------------------------------------------

    def check_raids(self, player_wx: int, player_wy: int,
                    player_horses: int, player_pelts: int,
                    day: int, rng: _r.Random) -> Optional[dict]:
        """Check whether a raid occurs.  Returns a raid dict or None."""
        tribes = self.get_territory_at(player_wx, player_wy)
        if not tribes:
            return None
        for tribe in tribes:
            ts = self.get_standing(tribe)
            if ts.standing >= STANDING_WARY:
                continue  # friendly tribes don't raid
            # Base chance scales with how hostile they are
            hostility = max(0, -ts.standing)  # 0..100
            base_chance = hostility / 1000.0  # 0..0.10 per day
            # More horses/pelts attract more raids
            loot_factor = 1.0 + (player_horses * 0.05) + (player_pelts * 0.01)
            chance = base_chance * loot_factor
            if rng.random() < chance:
                warriors = rng.randint(3, 6 + hostility // 20)
                raid_type = "horse_raid" if player_horses > 0 else "supply_raid"
                return {
                    "raid_type": raid_type,
                    "tribe": tribe,
                    "warriors": warriors,
                    "hostility": hostility,
                }
        return None

    # -- patrol encounter ----------------------------------------------------

    def roll_patrol_encounter(self, wx: int, wy: int,
                              rng: _r.Random) -> Optional[dict]:
        """Roll for a patrol encounter at (wx, wy).  Returns dict or None."""
        tribes = self.get_territory_at(wx, wy)
        if not tribes:
            return None
        tribe = rng.choice(tribes)
        ts = self.get_standing(tribe)
        # Encounter chance: 8 % per tile in territory
        if rng.random() > 0.08:
            return None
        warriors = rng.randint(2, 5)
        # Disposition based on standing
        if ts.standing >= STANDING_FRIENDLY:
            disposition = "friendly"
        elif ts.standing >= STANDING_NEUTRAL:
            disposition = "curious"
        elif ts.standing >= STANDING_WARY:
            disposition = "wary"
        elif ts.standing >= STANDING_HOSTILE:
            disposition = "hostile"
        else:
            disposition = "attack"
        return {
            "tribe": tribe,
            "warriors": warriors,
            "disposition": disposition,
            "standing": ts.standing,
        }

    # -- camp population -----------------------------------------------------

    def populate_native_camp(self, tribe: str,
                             rng: _r.Random) -> List[dict]:
        """Generate NPC definition dicts for a native camp.

        Returns a list of dicts; the engine creates NPCExpanded objects from
        these specs.  No game imports to avoid circular dependencies.
        """
        name_pool = NATIVE_NAMES.get(tribe, NATIVE_NAMES["Shoshone"])
        male_names = list(name_pool["male"])
        female_names = list(name_pool["female"])
        rng.shuffle(male_names)
        rng.shuffle(female_names)
        m_idx = 0
        f_idx = 0
        npcs: List[dict] = []

        for occupation, lo, hi in CAMP_ROLES:
            count = rng.randint(lo, hi)
            for _ in range(count):
                # Most camp roles are male in this era; trader can be female
                if occupation == "Native Trader" and rng.random() < 0.3:
                    gender = "F"
                else:
                    gender = "M"

                if gender == "M" and m_idx < len(male_names):
                    name = male_names[m_idx]; m_idx += 1
                elif gender == "F" and f_idx < len(female_names):
                    name = female_names[f_idx]; f_idx += 1
                elif m_idx < len(male_names):
                    name = male_names[m_idx]; m_idx += 1; gender = "M"
                else:
                    name = f"{tribe} {occupation}"

                # Attribute biases by role
                attrs = {
                    "strength": 10, "agility": 10, "intelligence": 10,
                    "wisdom": 10, "charisma": 10, "constitution": 10,
                }
                if occupation == "Warrior":
                    attrs["strength"] += rng.randint(1, 4)
                    attrs["agility"] += rng.randint(1, 3)
                    attrs["constitution"] += rng.randint(1, 3)
                elif occupation == "Chief":
                    attrs["charisma"] += rng.randint(2, 5)
                    attrs["wisdom"] += rng.randint(2, 5)
                elif occupation == "Hunter":
                    attrs["agility"] += rng.randint(1, 4)
                    attrs["wisdom"] += rng.randint(1, 3)
                elif occupation == "Native Guide":
                    attrs["wisdom"] += rng.randint(2, 4)
                    attrs["intelligence"] += rng.randint(1, 3)

                traits: List[str] = []
                if occupation == "Chief":
                    traits.append("Stoic")
                elif occupation == "Warrior":
                    traits.append(rng.choice(["Brave", "Fierce", "Vigilant"]))

                inv: List[str] = []
                if occupation == "Warrior":
                    inv.extend(["bow", "arrows", "knife"])
                elif occupation == "Hunter":
                    inv.extend(["bow", "arrows", "dried_meat"])
                elif occupation == "Native Trader":
                    inv.extend(["pemmican", "beaver_pelt", "trade_beads"])
                elif occupation == "Chief":
                    inv.extend(["pipe", "tobacco"])

                npcs.append({
                    "name": name,
                    "gender": gender,
                    "occupation": occupation,
                    "ethnicity": "native_american",
                    "tribe": tribe,
                    "age": rng.randint(20, 55) if occupation != "Chief"
                           else rng.randint(40, 65),
                    "attributes": attrs,
                    "traits": traits,
                    "inventory_ids": inv,
                })

        return npcs

    # -- capture / adoption --------------------------------------------------

    def capture_player(self, tribe: str, day: int) -> str:
        """Player captured by tribal warriors. Sets captive state."""
        ts = self.get_standing(tribe)
        ts.captive = True
        ts.captive_days = 0
        ts.escape_attempts = 0
        ts.last_contact_day = day
        return (f"The {tribe} warriors bind your hands. You are their prisoner. "
                f"They take your weapons and march you to their camp.")

    def tick_captivity(self, tribe: str, day: int,
                       rng: random.Random) -> List[Tuple[str, str]]:
        """Daily tick while captive. Standing slowly improves.
        Returns list of (message, severity) pairs."""
        ts = self.get_standing(tribe)
        if not ts.captive:
            return []
        msgs = []
        ts.captive_days += 1
        ts.days_near_tribe += 2  # accelerated language exposure

        # Standing improves slowly through compliant behavior
        ts.standing = min(100, ts.standing + 1)

        # Language advancement (faster in captivity — immersion)
        lang_msg = self._advance_language(tribe)
        if lang_msg:
            msgs.append((lang_msg, "advisory"))

        # Daily events
        if ts.captive_days == 3:
            msgs.append(("They put you to work carrying water and "
                         "gathering firewood.", "normal"))
        elif ts.captive_days == 7:
            msgs.append(("The children are less afraid of you now. "
                         "One brings you extra food.", "normal"))
        elif ts.captive_days == 14:
            msgs.append(("You begin to understand some of what they say. "
                         "They seem less hostile.", "normal"))

        # Adoption offer — if standing reaches neutral and language is pidgin+
        if ts.standing >= 0 and ts.language_level in ("pidgin", "fluent") \
                and ts.captive_days >= 21:
            msgs.append((f"The {tribe} chief approaches. He speaks slowly. "
                         f"He offers you a place in the tribe — adoption. "
                         f"You can accept or refuse.", "normal"))
            # Engine handles the choice

        return msgs

    def attempt_escape(self, tribe: str, tracking_skill: int,
                       agility: int, rng: random.Random) -> Tuple[bool, str]:
        """Player attempts to escape captivity.
        Returns (success, message)."""
        ts = self.get_standing(tribe)
        if not ts.captive:
            return False, "You are not a captive."

        # Base difficulty: 14. Guards get more alert after failed attempts.
        difficulty = 14 + ts.escape_attempts * 3
        roll = rng.randint(1, 20) + tracking_skill // 2 + agility // 3

        if roll >= difficulty:
            ts.captive = False
            ts.standing -= 10  # they're angry you escaped
            return True, (
                "You slip away in the darkness. The camp falls behind. "
                "You're free — but they'll be looking for you.")
        else:
            ts.escape_attempts += 1
            ts.standing -= 5
            damage_msg = ""
            if ts.escape_attempts >= 3:
                damage_msg = " They beat you badly this time."
            return False, (
                f"Caught. The guards drag you back.{damage_msg} "
                f"They won't trust you for a while.")

    def accept_adoption(self, tribe: str, day: int) -> str:
        """Player accepts tribal adoption. Full membership."""
        ts = self.get_standing(tribe)
        ts.captive = False
        ts.adopted = True
        ts.standing = max(ts.standing, 50)
        ts.language_level = "fluent"
        ts.has_safe_passage = True
        ts.has_trapping_rights = True
        ts.last_contact_day = day
        return (f"The {tribe} adopt you into their people. "
                f"You are given a name in their tongue. "
                f"You are one of them now.")

    def refuse_adoption(self, tribe: str) -> str:
        """Player refuses adoption. Remains captive."""
        ts = self.get_standing(tribe)
        ts.standing -= 10  # they're insulted
        return (f"The chief's face hardens. "
                f"You remain a prisoner. Perhaps you will reconsider.")

    # -- marriage ------------------------------------------------------------

    def native_marriage_check(self, player: Any, npc_tribe: str,
                              standing: int) -> Tuple[bool, str]:
        """Check whether the player can marry into a tribe."""
        ts = self.get_standing(npc_tribe)
        if ts.language_level != "fluent":
            return False, "You must speak the language fluently."
        if standing < STANDING_FRIENDLY:
            return False, "The tribe does not know you well enough."
        if ts.bride_price_paid:
            return False, "You have already paid a bride price to this tribe."
        return True, "The chief is willing to discuss a marriage."

    def native_marriage_cost(self, tribe: str) -> List[Tuple[str, int]]:
        """Return the bride price items for a tribe."""
        base = [
            ("horse", 3),
            ("trade_blanket", 5),
            ("percussion_rifle", 1),
            ("tobacco", 10),
        ]
        terr = self.territories.get(tribe)
        if terr and terr.temperament == "aggressive":
            # More demanding
            base.append(("gunpowder", 5))
            base[0] = ("horse", 5)
        return base

    # -- whiskey trade -------------------------------------------------------

    def process_whiskey_trade(self, tribe: str, units: int,
                              day: int) -> None:
        """Record whiskey traded; immediate +3 per unit, deferred -8 per unit."""
        ts = self.get_standing(tribe)
        ts.whiskey_units_traded += units
        # Immediate goodwill
        immediate = units * STANDING_DELTAS["whiskey_trade"]
        self.adjust_standing(tribe, immediate, "whiskey trade", day)
        # Accumulate deferred debt (applied over next several days)
        ts.whiskey_debt_standing += units * abs(STANDING_DELTAS["whiskey_aftermath"])

    def _apply_whiskey_debt(self, tribe: str, day: int) -> Optional[str]:
        """Drip-apply accumulated whiskey debt, 2-4 points per day."""
        ts = self.get_standing(tribe)
        if ts.whiskey_debt_standing <= 0:
            return None
        chunk = min(ts.whiskey_debt_standing, 3)
        ts.whiskey_debt_standing -= chunk
        self.adjust_standing(tribe, -chunk,
                             "whiskey aftermath — sickness and strife", day)
        return (f"The {tribe} suffer from the whiskey you traded. "
                f"Standing drops.")

    # -- daily tick ----------------------------------------------------------

    def tick_daily(self, player_wx: int, player_wy: int, day: int,
                   rng: _r.Random) -> List[Tuple[str, str]]:
        """Daily update.  Returns list of (category, message) tuples."""
        messages: List[Tuple[str, str]] = []
        current_tribes = self.get_territory_at(player_wx, player_wy)

        # Territory entry notification
        entry_msg = self.check_territory_entry(
            player_wx, player_wy, self._last_tribes)
        if entry_msg:
            messages.append(("territory", entry_msg))
        self._last_tribes = current_tribes

        # Language progression and days-near for tribes in range
        for tribe in current_tribes:
            ts = self.get_standing(tribe)
            ts.days_near_tribe += 1
            ts.last_contact_day = day
            lang_msg = self._advance_language(tribe)
            if lang_msg:
                messages.append(("language", lang_msg))

        # Whiskey debt application (all tribes, not just nearby)
        for tribe in list(self.standings):
            debt_msg = self._apply_whiskey_debt(tribe, day)
            if debt_msg:
                messages.append(("whiskey", debt_msg))

        # Standing decay toward neutral for tribes not contacted recently
        for tribe, ts in self.standings.items():
            days_since = day - ts.last_contact_day
            if days_since > 30 and ts.standing != 0:
                # Drift 1 point toward 0 every 10 days past 30
                if days_since % 10 == 0:
                    drift = 1 if ts.standing < 0 else -1
                    ts.standing = max(-100, min(100, ts.standing + drift))

        return messages

    # -- serialization -------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "standings": {k: v.to_dict() for k, v in self.standings.items()},
            "last_tribes": list(self._last_tribes),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TribalSystem":
        ts = cls(seed=d.get("seed", 0))
        for tribe, sd in d.get("standings", {}).items():
            ts.standings[tribe] = TribalStanding.from_dict(sd)
        ts._last_tribes = list(d.get("last_tribes", []))
        return ts
