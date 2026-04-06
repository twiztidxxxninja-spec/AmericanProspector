"""
src/war_system.py

Historical war system for American Prospector.
Wars are background events that affect the world — supply shortages, refugees,
military patrols, destroyed settlements. The player can choose to participate
(enlist, scout, fight, serve as medic) or stay neutral (trade, avoid, profit).

Battles are historically accurate — right date, right place, right factions.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
import random


# ============================================================================
#  WAR EVENT
# ============================================================================

@dataclass
class WarEvent:
    """A historical war or conflict."""
    war_id: str
    name: str
    start_year: int
    end_year: int
    regions: List[str]          # affected game regions
    factions: List[str]         # e.g. ["Continental", "British"]
    intensity: float = 0.5      # 0.0-1.0, scales all effects
    description: str = ""

    def is_active(self, year: int) -> bool:
        return self.start_year <= year <= self.end_year

    def phase(self, year: int) -> str:
        if year < self.start_year:
            return "peace"
        if year == self.start_year:
            return "buildup"
        if year == self.end_year:
            return "winding_down"
        if year > self.end_year and year <= self.end_year + 3:
            return "aftermath"
        if self.start_year < year < self.end_year:
            return "active"
        return "peace"

    def affects_region(self, region_name: str) -> bool:
        rn = region_name.lower()
        return any(r.lower() in rn for r in self.regions)


# ============================================================================
#  HISTORICAL WARS DATABASE
# ============================================================================

WARS: List[WarEvent] = [
    # ── Long Hunter era (1770s-1790s) ─────────────────────────────────
    WarEvent("dunmores_war", "Lord Dunmore's War",
        1774, 1774, ["Appalachians", "Ohio Valley"],
        ["Virginia Militia", "Shawnee"], intensity=0.6,
        description="Virginia's war against the Shawnee for Kentucky."),
    WarEvent("revolution", "American Revolution",
        1775, 1783, ["Appalachians", "Ohio Valley", "Gulf Coast"],
        ["Continental", "British", "Loyalist"], intensity=0.8,
        description="War for independence. The frontier is a second theater."),
    WarEvent("northwest_indian", "Northwest Indian War",
        1785, 1795, ["Ohio Valley", "Appalachians"],
        ["US Army", "Western Confederacy"], intensity=0.7,
        description="The new republic fights the tribal confederation for Ohio."),

    # ── Mountain Men era (1810s-1830s) ────────────────────────────────
    WarEvent("war_1812", "War of 1812",
        1812, 1815, ["Great Plains", "Appalachians", "Gulf Coast"],
        ["American", "British", "Tecumseh Confederacy"], intensity=0.6,
        description="Second war with Britain. Tecumseh rallies the tribes."),
    WarEvent("creek_war", "Creek War",
        1813, 1814, ["Gulf Coast", "Appalachians"],
        ["US Army", "Red Stick Creek"], intensity=0.5,
        description="Andrew Jackson's campaign against the Creek Nation."),
    WarEvent("black_hawk", "Black Hawk War",
        1832, 1832, ["Great Plains"],
        ["US Army", "Sauk-Fox"], intensity=0.4,
        description="Black Hawk leads a doomed return to Illinois homeland."),

    # ── Gold Rush era (1846-1865) ─────────────────────────────────────
    WarEvent("mexican_american", "Mexican-American War",
        1846, 1848, ["California", "Desert Southwest"],
        ["American", "Mexican"], intensity=0.5,
        description="War with Mexico. California and the Southwest change hands."),
    WarEvent("civil_war", "American Civil War",
        1861, 1865, ["Appalachians", "Great Plains", "Gulf Coast"],
        ["Union", "Confederate"], intensity=1.0,
        description="The nation tears itself apart. Border states burn."),

    # ── Industrial era (1866-1890) ────────────────────────────────────
    WarEvent("red_clouds_war", "Red Cloud's War",
        1866, 1868, ["Montana Goldfields", "Great Plains"],
        ["US Army", "Lakota-Cheyenne-Arapaho"], intensity=0.6,
        description="Red Cloud fights the Bozeman Trail forts."),
    WarEvent("great_sioux_war", "Great Sioux War",
        1876, 1877, ["Montana Goldfields", "Great Plains", "Black Hills"],
        ["US Army", "Lakota-Northern Cheyenne"], intensity=0.8,
        description="Custer's Last Stand. The last great Indian war."),
    WarEvent("nez_perce_war", "Nez Perce War",
        1877, 1877, ["Idaho Silver Belt", "Montana Goldfields"],
        ["US Army", "Nez Perce"], intensity=0.5,
        description="Chief Joseph's fighting retreat across 1,170 miles."),
    WarEvent("apache_wars", "Apache Wars",
        1849, 1886, ["Desert Southwest"],
        ["US Army", "Apache"], intensity=0.4,
        description="Geronimo. Cochise. Decades of guerrilla warfare."),
]


# ============================================================================
#  HISTORICAL BATTLES — specific date and location
# ============================================================================

@dataclass
class HistoricalBattle:
    """A specific battle at a specific place and time."""
    battle_id: str
    name: str
    year: int
    month: int
    day: int
    world_x: int               # world map coordinates
    world_y: int
    war_id: str                # which WarEvent this belongs to
    factions: List[str]        # exactly 2: [attacker, defender]
    strength: List[int]        # [attacker_count, defender_count]
    victor: int = 0            # 0=attacker, 1=defender (historical outcome)
    patches: int = 1           # how many local map patches the battle spans
    description: str = ""
    player_swing: float = 0.0  # 0.0 = fixed outcome, 1.0 = fully swingable
    # Artillery — cannons per side [side0, side1]. 0 = no artillery.
    # Cannons create danger zones on the battlefield. Can be spiked.
    artillery: List[int] = field(default_factory=lambda: [0, 0])


# ── Player impact tracking during a battle ──────────────────────────────

@dataclass
class BattleState:
    """Tracks an active battle the player is participating in."""
    battle: HistoricalBattle
    player_side: int = -1          # 0 or 1 (faction index), -1 = not joined
    player_role: str = "fighter"   # "fighter" | "medic" | "observer"
    # Player's contribution — these shift the outcome
    enemies_killed: int = 0
    allies_saved: int = 0          # wounded dragged to safety / healed
    officers_killed: int = 0       # killing enemy officers has outsized effect
    supplies_destroyed: int = 0    # blowing up ammo/supply wagons
    flanks_held: int = 0           # patches where player's side held despite odds
    # Casualties tracked per side
    side_casualties: List[int] = field(default_factory=lambda: [0, 0])
    patches_fought: int = 0
    resolved: bool = False
    outcome: int = -1              # -1=unresolved, 0=side0 wins, 1=side1 wins
    cannons_spiked: int = 0        # enemy cannons sabotaged

    @property
    def player_impact_score(self) -> float:
        """How much the player shifted the battle.
        Each action contributes to swinging the historical outcome."""
        score = 0.0
        score += self.enemies_killed * 2.0
        score += self.allies_saved * 3.0         # saving lives matters more
        score += self.officers_killed * 10.0      # decapitation strike
        score += self.supplies_destroyed * 5.0
        score += self.flanks_held * 8.0
        score += self.cannons_spiked * 15.0       # spiking a cannon is huge
        return score

    def resolve_outcome(self) -> int:
        """Determine battle outcome. Historical result is the baseline,
        player impact can shift it for smaller battles."""
        battle = self.battle
        # How swingable is this battle?
        # Small battles (< 200 total troops) are highly swingable
        total_troops = sum(battle.strength)
        if total_troops < 100:
            swing = 0.8   # player can absolutely change this
        elif total_troops < 500:
            swing = 0.5   # significant influence
        elif total_troops < 2000:
            swing = 0.25  # moderate influence
        elif total_troops < 10000:
            swing = 0.1   # marginal influence
        else:
            swing = 0.03  # almost none — you can't change Gettysburg alone

        # Override with battle-specific swing if set
        if battle.player_swing > 0:
            swing = battle.player_swing

        # Calculate shift — positive = favors player's side
        if self.player_side < 0:
            # Observer/neutral — no influence
            self.outcome = battle.victor
            return self.outcome

        impact = self.player_impact_score
        # Normalize: 50 impact points at full swing = guaranteed flip
        shift = (impact / 50.0) * swing

        # Historical outcome probability
        # victor=0 means side 0 won historically
        if self.player_side == battle.victor:
            # Player is on the winning side — they just make it more decisive
            win_chance = 0.85 + shift * 0.15  # 85-100%
        else:
            # Player is on the losing side — can they change history?
            win_chance = 0.15 + shift * 0.85  # 15% base, up to 100% with enough impact

        import random as _brng
        if _brng.random() < win_chance:
            self.outcome = self.player_side
        else:
            self.outcome = 1 - self.player_side

        self.resolved = True
        return self.outcome

    # ── Artillery mechanics ──────────────────────────────────────────

    def roll_cannon_fire(self, player_x: int, player_y: int,
                         rng: random.Random) -> Optional[Dict[str, Any]]:
        """Roll for cannon fire hitting near the player during battle.
        Returns hit info dict or None if no strike this round."""
        b = self.battle
        total_guns = sum(b.artillery)
        if total_guns == 0:
            return None

        # Chance of cannon fire each combat round — more guns = more fire
        fire_chance = min(0.4, total_guns * 0.03)
        if rng.random() > fire_chance:
            return None

        # Which side fires?
        if rng.random() < b.artillery[0] / max(total_guns, 1):
            firing_side = 0
        else:
            firing_side = 1

        # Impact point — random scatter around player's area
        scatter = rng.randint(3, 15)
        impact_x = player_x + rng.randint(-scatter, scatter)
        impact_y = player_y + rng.randint(-scatter, scatter)
        dist_to_player = abs(impact_x - player_x) + abs(impact_y - player_y)

        # Damage based on proximity
        if dist_to_player <= 2:
            # Direct hit area — devastating
            hit_type = "direct"
            damage = rng.randint(40, 80)
        elif dist_to_player <= 5:
            # Close — shrapnel and debris
            hit_type = "near_miss"
            damage = rng.randint(10, 30)
        elif dist_to_player <= 8:
            # Felt it — concussion, dirt shower
            hit_type = "concussion"
            damage = rng.randint(0, 5)
        else:
            # Distant — just noise and smoke
            hit_type = "distant"
            damage = 0

        # Canister shot at close range (under 300 yards / ~60 tiles)
        # Like a giant shotgun — devastating to infantry
        is_canister = rng.random() < 0.2 and dist_to_player <= 10

        faction_name = b.factions[firing_side]
        return {
            "firing_side": firing_side,
            "faction": faction_name,
            "impact_x": impact_x,
            "impact_y": impact_y,
            "dist": dist_to_player,
            "hit_type": hit_type,
            "damage": damage,
            "is_canister": is_canister,
        }

    @staticmethod
    def cannon_fire_message(hit: Dict[str, Any]) -> str:
        """Generate a message for a cannon strike."""
        ht = hit["hit_type"]
        faction = hit["faction"]
        is_canister = hit.get("is_canister", False)

        if is_canister:
            return (f"CANISTER! A {faction} cannon fires canister shot — "
                    f"a wall of lead balls shreds everything in front of it. "
                    f"Men scream and fall.")

        if ht == "direct":
            msgs = [
                f"A cannonball hits the ground ten feet away. "
                f"Dirt and shrapnel blast outward. You're thrown sideways.",
                f"The {faction} artillery finds your position. "
                f"A round shot tears through a tree and keeps going. "
                f"Splinters everywhere.",
                f"BOOM. The ground erupts. A cannonball buries itself "
                f"in the earth right next to you. Your ears ring.",
                f"A {faction} shell explodes overhead. Iron fragments "
                f"rain down. You taste blood.",
                f"A cannonball bounces off the ground and passes through "
                f"a man five feet from you. He comes apart.",
                f"The {faction} guns bracket your position. Dirt rains down. "
                f"Your mouth is full of earth.",
                f"A round shot skips along the ground like a stone on water. "
                f"It takes a man's legs from under him on the bounce.",
                f"CRACK. A tree beside you explodes. The cannonball passed "
                f"through the trunk. Splinters the size of knives.",
                f"The ground heaves. You're lifted off your feet. When you "
                f"land everything is ringing and red.",
                f"A shell bursts in the air above you. Hot iron fragments "
                f"hiss into the ground all around you.",
                f"A solid shot hits a supply wagon behind the line. "
                f"It disintegrates. Boards and barrel staves fly.",
                f"The {faction} gunners have your range. The next shot "
                f"buries itself in the earth two yards away. Too close.",
                f"A cannonball carves a furrow through the ground at your feet. "
                f"An inch higher and you'd have no feet.",
                f"The concussion from a near hit throws you flat. "
                f"When you stand your ears are bleeding.",
            ]
        elif ht == "near_miss":
            msgs = [
                f"A cannonball crashes into the brush thirty feet away. "
                f"Branches fly. Someone screams.",
                f"The {faction} guns open up. A round hits a fence line "
                f"nearby — splinters and iron everywhere.",
                f"Earth showers over you as a shot impacts just past "
                f"your position. Too close.",
                f"A solid shot hits a tree forty feet to your right. "
                f"The trunk snaps. The tree falls slowly.",
                f"A cannonball bounces past and buries in the hillside "
                f"behind you. The ground shakes.",
                f"The shot falls short. Dirt sprays up in a fan. "
                f"Next one won't be short.",
                f"A shell bursts in the air to your left. Fragments whine "
                f"past. Not aimed at you. Not this time.",
                f"A round shot plows through the grass twenty yards out. "
                f"You can feel the wind of it.",
                f"The {faction} battery fires a ranging shot. It's close. "
                f"They're adjusting.",
                f"BOOM. A geyser of earth erupts nearby. When it clears "
                f"there's a crater where a man was standing.",
            ]
        elif ht == "concussion":
            msgs = [
                f"A distant BOOM, then the ground shakes. {faction} "
                f"artillery working the field.",
                f"Cannon fire. You feel the concussion in your chest "
                f"even at this distance.",
                f"The air thumps. Smoke rises from where the {faction} "
                f"guns are hitting. Not here. Not yet.",
                f"The {faction} battery fires a salvo. The impacts walk "
                f"across the field like giant footsteps.",
                f"You feel each shot through the soles of your boots. "
                f"The {faction} guns are busy.",
                f"Smoke billows from the {faction} position. Three guns "
                f"fire in sequence. The noise rolls over you.",
                f"A shell bursts somewhere to the rear. Shouts of alarm. "
                f"Then silence.",
                f"The {faction} guns are finding the range. Each shot "
                f"lands closer than the last.",
                f"BOOM. A pause. BOOM. Another pause. They're aiming "
                f"carefully. That's worse.",
                f"The ground vibrates with each discharge. Even at this "
                f"distance you feel your teeth rattle.",
            ]
        else:
            msgs = [
                f"Distant cannon fire. The {faction} guns are working "
                f"the far end of the field.",
                f"BOOM. BOOM. The {faction} artillery speaks. "
                f"You hear it but don't feel it.",
                f"Smoke on the ridge — {faction} battery firing. "
                f"The sound rolls across the valley.",
                f"Thunder that isn't weather. The {faction} guns are at "
                f"work somewhere out of sight.",
                f"A low rumble from the {faction} position. The ground "
                f"carries the vibration.",
                f"Puffs of white smoke on the distant ridge. The boom "
                f"arrives a moment later.",
                f"You hear cannon fire but can't tell where it's aimed. "
                f"Not here. Not yet.",
                f"The {faction} battery opens up on something to the east. "
                f"You can see the smoke.",
                f"Distant booming. Regular as a clock. The {faction} gunners "
                f"have found a target.",
                f"A faint whistle overhead — a shot passing high. "
                f"Aimed at someone else. For now.",
            ]
        import random as _mrng
        return _mrng.choice(msgs)

    def outcome_message(self) -> str:
        """Generate a message describing the battle's result."""
        b = self.battle
        if self.outcome < 0:
            return f"The Battle of {b.name} is still underway."

        winner = b.factions[self.outcome]
        loser = b.factions[1 - self.outcome]
        historical = (self.outcome == b.victor)

        if historical:
            if self.player_side == self.outcome:
                # Player won, history unchanged
                msgs = [
                    f"Victory! The {winner} carry the day at {b.name}. "
                    f"You fought well.",
                    f"The {loser} break and run. {b.name} belongs to the {winner}. "
                    f"History will remember this.",
                ]
            elif self.player_side >= 0:
                # Player lost, history unchanged
                msgs = [
                    f"Defeat. The {winner} overwhelm your position at {b.name}. "
                    f"You retreat with the survivors.",
                    f"The battle is lost. The {loser} fall back from {b.name}. "
                    f"It was not enough.",
                ]
            else:
                msgs = [f"The {winner} win the Battle of {b.name}."]
        else:
            # Player CHANGED THE OUTCOME
            if self.player_side == self.outcome:
                msgs = [
                    f"AGAINST ALL ODDS — the {winner} win at {b.name}! "
                    f"They'll talk about this one for a hundred years. "
                    f"You turned the tide.",
                    f"The {winner} carry the field at {b.name}. "
                    f"Nobody expected this. You were there. "
                    f"You made the difference.",
                    f"Victory at {b.name} — and it shouldn't have happened. "
                    f"The {loser} had every advantage. "
                    f"Except you.",
                ]
            else:
                msgs = [
                    f"Despite your efforts, the {winner} prevail at {b.name}. "
                    f"History took a different turn than expected.",
                ]

        import random as _mrng
        msg = _mrng.choice(msgs)

        # Add casualty report
        if sum(self.side_casualties) > 0:
            msg += (f"\nCasualties — {b.factions[0]}: {self.side_casualties[0]}, "
                    f"{b.factions[1]}: {self.side_casualties[1]}.")

        # Player contribution
        if self.enemies_killed > 0 or self.allies_saved > 0:
            parts = []
            if self.enemies_killed > 0:
                parts.append(f"{self.enemies_killed} enemies killed")
            if self.allies_saved > 0:
                parts.append(f"{self.allies_saved} wounded saved")
            if self.officers_killed > 0:
                parts.append(f"{self.officers_killed} officers killed")
            if self.cannons_spiked > 0:
                parts.append(f"{self.cannons_spiked} cannons spiked")
            msg += f"\nYour contribution: {', '.join(parts)}."

        return msg


HISTORICAL_BATTLES: List[HistoricalBattle] = [
    # ── Long Hunter era ──────────────────────────────────────────────
    HistoricalBattle("point_pleasant", "Battle of Point Pleasant",
        1774, 10, 10, 355, 180, "dunmores_war",
        ["Virginia Militia", "Shawnee"], [1000, 500], victor=0, patches=2,
        description="Decisive battle of Lord Dunmore's War at the Ohio River.",
        artillery=[1, 0]),  # militia had a small cannon, Shawnee had none
    HistoricalBattle("blue_licks", "Battle of Blue Licks",
        1782, 8, 19, 343, 189, "revolution",
        ["Kentucky Militia", "British+Shawnee"], [180, 300], victor=1, patches=1,
        description="Last battle of the Revolution in Kentucky. A disaster.",
        player_swing=0.5),  # small enough that a skilled fighter matters
    HistoricalBattle("fallen_timbers", "Battle of Fallen Timbers",
        1794, 8, 20, 348, 178, "northwest_indian",
        ["US Army", "Western Confederacy"], [3000, 1500], victor=0, patches=4,
        description="General Wayne's victory ends the Northwest Indian War.",
        artillery=[4, 0]),  # Wayne had 4 field pieces

    # ── War of 1812 ──────────────────────────────────────────────────
    HistoricalBattle("tippecanoe", "Battle of Tippecanoe",
        1811, 11, 7, 340, 175, "war_1812",
        ["US Army", "Tecumseh Confederacy"], [1000, 700], victor=0, patches=2,
        description="Harrison destroys Prophetstown. Tecumseh's dream broken.",
        artillery=[2, 0]),
    HistoricalBattle("new_orleans", "Battle of New Orleans",
        1815, 1, 8, 300, 240, "war_1812",
        ["American", "British"], [4700, 8000], victor=0, patches=6,
        description="Jackson's greatest victory — fought after peace was signed.",
        artillery=[8, 12]),  # both sides heavily armed

    # ── Gold Rush era ────────────────────────────────────────────────
    HistoricalBattle("bear_flag", "Bear Flag Revolt",
        1846, 6, 14, 90, 160, "mexican_american",
        ["American Settlers", "Mexican"], [30, 50], victor=0, patches=1,
        description="American settlers seize Sonoma. California changes hands.",
        player_swing=0.9),  # tiny battle — one fighter changes everything

    # ── Civil War ────────────────────────────────────────────────────
    HistoricalBattle("wilson_creek", "Battle of Wilson's Creek",
        1861, 8, 10, 290, 180, "civil_war",
        ["Union", "Confederate"], [5400, 12000], victor=1, patches=8,
        description="First major battle west of the Mississippi.",
        artillery=[6, 15]),  # Confederates had more guns
    HistoricalBattle("pea_ridge", "Battle of Pea Ridge",
        1862, 3, 7, 285, 185, "civil_war",
        ["Union", "Confederate"], [10500, 16000], victor=0, patches=10,
        description="Secures Missouri for the Union.",
        artillery=[12, 18]),

    # ── Indian Wars ──────────────────────────────────────────────────
    HistoricalBattle("fetterman", "Fetterman Fight",
        1866, 12, 21, 230, 115, "red_clouds_war",
        ["US Army", "Lakota-Cheyenne"], [81, 2000], victor=1, patches=2,
        description="81 soldiers killed to the last man. Red Cloud's greatest victory.",
        player_swing=0.3),  # small US force, player could save some lives
    HistoricalBattle("little_bighorn", "Battle of the Little Bighorn",
        1876, 6, 25, 225, 100, "great_sioux_war",
        ["US Army", "Lakota-Northern Cheyenne"], [700, 2500], victor=1, patches=6,
        description="Custer's Last Stand. The most famous defeat in US Army history.",
        artillery=[3, 0]),  # Custer left his Gatling guns behind — fatal mistake
    HistoricalBattle("bear_paw", "Battle of Bear Paw",
        1877, 9, 30, 195, 85, "nez_perce_war",
        ["US Army", "Nez Perce"], [600, 700], victor=0, patches=3,
        description="Chief Joseph surrenders. 'I will fight no more forever.'"),
]


# ============================================================================
#  WAR SYSTEM — tracks active conflicts and their effects
# ============================================================================

class WarSystem:
    """Manages active wars, their effects on the world, and player participation."""

    def __init__(self):
        self.player_faction: str = ""       # "" = neutral/civilian
        self.player_enlisted: bool = False
        self.player_enlist_war: str = ""    # war_id of enlistment
        self.days_served: int = 0
        self.kills_in_war: int = 0
        self.wounded_treated: int = 0
        self._active_cache: List[WarEvent] = []
        self._active_battles: List[HistoricalBattle] = []

    def get_active_wars(self, year: int, region: str = "") -> List[WarEvent]:
        """Return wars active in this year, optionally filtered by region."""
        active = [w for w in WARS if w.is_active(year)]
        if region:
            active = [w for w in active if w.affects_region(region)]
        return active

    def get_todays_battle(self, year: int, month: int, day: int,
                          player_wx: int, player_wy: int,
                          detection_range: int = 20
                          ) -> Optional[HistoricalBattle]:
        """Check if a historical battle is happening today near the player."""
        for b in HISTORICAL_BATTLES:
            if b.year == year and b.month == month and b.day == day:
                dist = abs(b.world_x - player_wx) + abs(b.world_y - player_wy)
                if dist <= detection_range:
                    return b
        return None

    def enlist(self, war_id: str, faction: str) -> str:
        """Player enlists in a faction for a war."""
        self.player_faction = faction
        self.player_enlisted = True
        self.player_enlist_war = war_id
        self.days_served = 0
        self.kills_in_war = 0
        war = next((w for w in WARS if w.war_id == war_id), None)
        war_name = war.name if war else "the conflict"
        return (f"You enlist with the {faction}. "
                f"The {war_name} needs men who know the frontier.")

    def desert(self) -> str:
        """Player deserts their enlistment."""
        faction = self.player_faction
        self.player_faction = ""
        self.player_enlisted = False
        self.player_enlist_war = ""
        return (f"You desert the {faction}. If they catch you, "
                f"you'll hang.")

    def discharge(self) -> str:
        """Honorable discharge at war's end."""
        faction = self.player_faction
        days = self.days_served
        self.player_faction = ""
        self.player_enlisted = False
        self.player_enlist_war = ""
        return (f"You are honorably discharged from the {faction} "
                f"after {days} days of service.")

    def is_enemy_combatant(self, npc_faction: str) -> bool:
        """Check if an NPC's faction is the enemy of the player's faction."""
        if not self.player_faction or not npc_faction:
            return False
        # Same faction = friendly
        if npc_faction == self.player_faction:
            return False
        # Different faction during same war = enemy
        for war in WARS:
            if self.player_faction in war.factions and \
                    npc_faction in war.factions:
                return True
        return False

    def tick_daily(self, year: int, region: str,
                   rng: random.Random) -> List[Tuple[str, str]]:
        """Daily war tick. Returns (message, severity) pairs."""
        msgs = []
        if self.player_enlisted:
            self.days_served += 1

        # Check if any enlisted war has ended
        if self.player_enlist_war:
            war = next((w for w in WARS if w.war_id == self.player_enlist_war), None)
            if war and not war.is_active(year):
                msgs.append((self.discharge(), "normal"))

        # Update active wars cache
        self._active_cache = self.get_active_wars(year, region)

        return msgs

    def spawn_battle_npcs(self, battle: HistoricalBattle,
                          side: int, count: int,
                          lmap, area_x: int, area_y: int,
                          npc_gen, rng: random.Random
                          ) -> list:
        """Spawn soldier NPCs for one side of a battle on the local map.
        Returns list of spawned NPC objects."""
        faction = battle.factions[side]
        spawned = []

        # Determine occupation and weapon based on faction/era
        is_native = any(t in faction.lower() for t in
                        ("shawnee", "creek", "confederacy", "lakota",
                         "cheyenne", "nez perce", "apache", "sauk",
                         "fox", "arapaho"))

        for i in range(count):
            npc_id = f"battle_{battle.battle_id}_{side}_{i}"
            # Avoid duplicates
            if npc_id in npc_gen.npcs:
                spawned.append(npc_gen.npcs[npc_id])
                continue

            from src.npc_system import NPCExpanded
            if is_native:
                occ = rng.choice(["Warrior", "Warrior", "Warrior", "Chief"])
                ethnicity = "native_american"
            else:
                occ = rng.choice(["Soldier", "Soldier", "Soldier",
                                  "Soldier", "Militia Captain"])
                ethnicity = "american"

            # Random position on the map — spread out
            x = rng.randint(30, lmap.width - 30)
            y = rng.randint(30, lmap.height - 30)

            npc = NPCExpanded(
                npc_id=npc_id,
                name=f"{faction} {occ}",
                age=rng.randint(18, 45),
                gender="M",
                occupation=occ,
                ethnicity=ethnicity,
                traits=rng.sample(["brave", "stoic", "nervous",
                                   "hot-tempered", "quiet"], 2),
            )
            npc.local_x = x
            npc.local_y = y
            npc.combat_state = "hostile"
            npc.faction = faction
            npc.present = True
            npc.alive = True

            # Give them a weapon
            try:
                npc.equip_occupation_weapon()
            except (AttributeError, Exception):
                pass

            npc_gen.npcs[npc_id] = npc
            spawned.append(npc)

        return spawned

    def get_wartime_price_mult(self, year: int, region: str,
                               item_category: str) -> float:
        """Price multiplier during wartime for affected goods."""
        active = self.get_active_wars(year, region)
        if not active:
            return 1.0
        max_intensity = max(w.intensity for w in active)
        # Military goods spike during war
        if item_category in ("weapon", "tool"):
            return 1.0 + max_intensity * 1.5  # up to 2.5x
        if item_category == "food":
            return 1.0 + max_intensity * 0.5  # up to 1.5x
        if item_category == "material":
            return 1.0 + max_intensity * 0.8  # up to 1.8x
        return 1.0 + max_intensity * 0.2      # mild increase for everything

    def tick_battle_round(self, battle_state: "BattleState",
                          all_npcs: list, player_x: int, player_y: int,
                          rng: random.Random) -> List[Tuple[str, str]]:
        """Process one round of NPC-vs-NPC battle combat.
        Returns (message, severity) pairs for display."""
        from src.combat import npc_attack_npc
        msgs = []
        b = battle_state.battle

        # Separate NPCs by faction
        side0 = [n for n in all_npcs if n.alive and n.present
                 and getattr(n, 'faction', '') == b.factions[0]
                 and n.combat_state == "hostile"]
        side1 = [n for n in all_npcs if n.alive and n.present
                 and getattr(n, 'faction', '') == b.factions[1]
                 and n.combat_state == "hostile"]

        if not side0 or not side1:
            return msgs  # one side eliminated on this patch

        # Each soldier picks a random enemy and attacks
        pairs = []
        for attacker in side0[:8]:  # cap per round for performance
            if side1:
                target = rng.choice(side1)
                pairs.append((attacker, target))
        for attacker in side1[:8]:
            if side0:
                target = rng.choice(side0)
                pairs.append((attacker, target))

        rng.shuffle(pairs)
        # Sort pairs by proximity to player — only show messages for closest action
        pairs.sort(key=lambda p: min(
            abs(p[0].local_x - player_x) + abs(p[0].local_y - player_y),
            abs(p[1].local_x - player_x) + abs(p[1].local_y - player_y)))

        shown_this_round = 0  # cap messages per round to avoid spam
        for attacker, defender in pairs:
            if not attacker.alive or not defender.alive:
                continue
            a_dist = abs(attacker.local_x - player_x) + \
                     abs(attacker.local_y - player_y)
            d_dist = abs(defender.local_x - player_x) + \
                     abs(defender.local_y - player_y)
            nearest = min(a_dist, d_dist)

            evt = npc_attack_npc(attacker, defender)
            if evt is None:
                # Reloading — visible only at close range
                if a_dist <= 5 and rng.random() < 0.15 and shown_this_round < 3:
                    reload_msgs = [
                        f"{attacker.name} rams a ball down the barrel.",
                        f"{attacker.name} bites a cartridge and pours powder.",
                        f"{attacker.name} fumbles with his powder horn.",
                        f"{attacker.name} measures powder with shaking hands.",
                        f"{attacker.name} drops a ball, curses, fishes for another.",
                        f"{attacker.name} blows on his match. Priming the pan.",
                        f"{attacker.name} yanks the ramrod and seats the ball.",
                        f"{attacker.name} tears a paper cartridge with his teeth.",
                        f"{attacker.name} pats his pouch for another ball.",
                        f"{attacker.name} spills powder on his boots. Tries again.",
                        f"{attacker.name} works the loading drill. Hands bloody.",
                        f"{attacker.name} rams home another round. Fourth time today.",
                        f"{attacker.name}'s hands shake too much to prime the pan.",
                        f"{attacker.name} uncorks his powder horn. The smell is sharp.",
                        f"{attacker.name} looks at the barrel of his gun like "
                        f"he forgot what comes next.",
                    ]
                    msgs.append((rng.choice(reload_msgs), "normal"))
                    shown_this_round += 1
                continue

            if evt.killed:
                if getattr(defender, 'faction', '') == b.factions[0]:
                    battle_state.side_casualties[0] += 1
                else:
                    battle_state.side_casualties[1] += 1
                if nearest <= 15 and shown_this_round < 4:
                    kill_msgs = [
                        f"A ball catches {defender.name} in the chest. "
                        f"He drops his weapon and falls.",
                        f"{defender.name} takes a shot through the head. "
                        f"His hat flies off. He crumples.",
                        f"{defender.name} is hit in the gut. He doubles over, "
                        f"clutching himself. He doesn't get up.",
                        f"A round tears through {defender.name}'s throat. "
                        f"Blood sprays. He goes down choking.",
                        f"{defender.name} spins sideways from the impact. "
                        f"Dead before he hits the ground.",
                        f"A ball shatters {defender.name}'s shin. The leg "
                        f"folds the wrong way. He falls screaming.",
                        f"{defender.name} catches a ball square in the face. "
                        f"The back of his head comes off.",
                        f"The shot hits {defender.name} below the ribs. "
                        f"He sits down carefully. Then he dies.",
                        f"{defender.name} is hit three times in quick succession. "
                        f"He was dead after the first.",
                        f"A ball bounces off a rock and catches {defender.name} "
                        f"in the temple. He drops like a stone.",
                        f"{defender.name} takes it standing. He looks confused "
                        f"for a moment. Then he falls.",
                        f"The ball enters {defender.name}'s eye socket. "
                        f"He was looking the wrong direction.",
                        f"{defender.name} is hit in the hip. The bone shatters. "
                        f"He falls and bleeds out in the dirt.",
                        f"A ball punches through {defender.name}'s chest. "
                        f"The exit wound paints the man behind him.",
                        f"{defender.name} takes a shot through the lung. "
                        f"He coughs blood and sinks to his knees.",
                        f"The ball hits {defender.name}'s powder horn. "
                        f"It explodes. He goes down in fire and smoke.",
                        f"{defender.name} is shot through the heart. "
                        f"He takes one step. Then nothing.",
                        f"A ball catches {defender.name} in the neck. "
                        f"He grabs at it. Blood between his fingers. He falls.",
                        f"{defender.name} turns to run. The ball catches him "
                        f"between the shoulder blades.",
                        f"The shot takes {defender.name}'s jaw off. He stands "
                        f"there a moment, mouth gone. Then he drops.",
                    ]
                    msgs.append((rng.choice(kill_msgs), "critical"))
                    shown_this_round += 1
            elif evt.hit:
                if nearest <= 10 and shown_this_round < 4:
                    if evt.defender_fled:
                        flee_msgs = [
                            f"{defender.name} takes a hit and breaks for the rear.",
                            f"{defender.name} is hit. He drops his rifle and runs.",
                            f"A ball catches {defender.name} in the leg. "
                            f"He limps away as fast as he can.",
                            f"{defender.name} is grazed. He decides he's had enough "
                            f"and runs.",
                            f"The shot hits {defender.name}'s canteen. Water sprays. "
                            f"He turns and bolts.",
                            f"{defender.name} takes a ball through the hand. "
                            f"He screams, drops his weapon, and flees.",
                            f"A round clips {defender.name}'s ear. Blood runs down "
                            f"his neck. He breaks and runs.",
                            f"{defender.name} is hit in the thigh. He hobbles toward "
                            f"the rear, cursing.",
                            f"The ball grazes {defender.name}'s scalp. He thinks "
                            f"he's dying. He runs.",
                            f"{defender.name} takes a hit. Looks at the blood. "
                            f"Looks at the enemy line. Runs.",
                            f"A ball shatters {defender.name}'s rifle stock. "
                            f"Unarmed, he turns and flees.",
                            f"{defender.name}'s nerve breaks. He throws down his "
                            f"weapon and runs for the trees.",
                            f"The shot catches {defender.name} in the shoulder. "
                            f"His arm goes limp. He retreats.",
                            f"{defender.name} sees the man next to him die. "
                            f"He decides to live. He runs.",
                            f"A ball punches through {defender.name}'s hat. "
                            f"Close enough. He retreats at speed.",
                        ]
                        msgs.append((rng.choice(flee_msgs), "normal"))
                    else:
                        wound_msgs = [
                            f"{defender.name} takes a ball in the shoulder. "
                            f"Blood runs down his arm. He stays up.",
                            f"A shot clips {defender.name}'s ear. He flinches, "
                            f"curses, keeps fighting.",
                            f"{defender.name} is hit in the side. He staggers "
                            f"but doesn't fall.",
                            f"A ball punches through {defender.name}'s coat. "
                            f"Blood, but he's still standing.",
                            f"{defender.name}'s arm snaps backward from the impact. "
                            f"Something broke. He switches hands.",
                            f"A ball takes a chunk out of {defender.name}'s thigh. "
                            f"He grits his teeth and keeps loading.",
                            f"{defender.name} is grazed across the ribs. "
                            f"He looks down, sees blood, ignores it.",
                            f"The shot hits {defender.name}'s belt buckle. Sparks. "
                            f"Bruised but alive.",
                            f"A ball passes through {defender.name}'s coat sleeve. "
                            f"An inch to the right and he'd be done.",
                            f"{defender.name} takes a ball in the forearm. "
                            f"The bone holds. He wraps it with his teeth.",
                            f"A round catches {defender.name} in the calf. "
                            f"He stumbles, catches himself, keeps fighting.",
                            f"{defender.name}'s hat is shot off his head. "
                            f"He doesn't stop to pick it up.",
                            f"The ball clips {defender.name}'s cheekbone. "
                            f"Blood sheets down his face. He doesn't stop.",
                            f"A shot grazes {defender.name}'s neck. An inch lower "
                            f"and he'd be dead. He knows it.",
                            f"{defender.name} takes a ball through the meat of "
                            f"his left arm. He's right-handed. Lucky.",
                            f"The shot hits {defender.name}'s powder horn. "
                            f"It cracks but doesn't explode. Powder everywhere.",
                            f"A ball bounces off a rock and catches {defender.name} "
                            f"in the shin. He limps but stays in line.",
                            f"{defender.name} is hit in the hip. He leans on his "
                            f"rifle like a crutch and keeps shooting.",
                            f"The ball tears through {defender.name}'s cartridge "
                            f"box. Paper and lead scatter. He's alive.",
                            f"A round punches through {defender.name}'s canteen. "
                            f"Water and blood mix on his shirt.",
                        ]
                        msgs.append((rng.choice(wound_msgs), "normal"))
                    shown_this_round += 1

        # Artillery fire
        cannon_hit = battle_state.roll_cannon_fire(player_x, player_y, rng)
        if cannon_hit:
            msg = BattleState.cannon_fire_message(cannon_hit)
            sev = "critical" if cannon_hit["hit_type"] in ("direct", "near_miss") \
                  else "normal"
            msgs.append((msg, sev))

        # Ambient battle sounds — only if no close combat shown this round
        if shown_this_round == 0 and rng.random() < 0.5:
            ambient = [
                "Smoke drifts across the field. Men shout and fire.",
                "The rattle of musketry rises and falls.",
                "Screaming. Orders shouted. The crash of a volley.",
                "A bugle sounds somewhere to the left. Cavalry?",
                "The ground trembles. Another volley.",
                "White smoke rolls across the ground like fog.",
                "A horse without a rider gallops past, eyes wild.",
                "Someone is calling for his mother. You can't see who.",
                "A drummer boy beats the advance. He can't be more than fourteen.",
                "The line wavers. An officer rides forward, waving his sword.",
                "A wounded man crawls past you, leaving a red trail in the grass.",
                "Volleys crash back and forth. The noise is beyond anything you've heard.",
                "A flag goes down. Someone picks it up. He goes down too.",
                "The smoke is so thick you can barely see thirty feet.",
                "A man near you is praying. His lips move but no sound comes out.",
                "Cartridge paper litters the ground like snow.",
                "The air smells of sulfur, blood, and something worse.",
                "An officer's horse goes down thrashing. The officer rolls free.",
                "A stretcher party dashes through the line carrying a screaming man.",
                "The enemy line fires a volley. You hear the balls buzz past like hornets.",
                "Somewhere a man is singing. It stops mid-verse.",
            ]
            msgs.append((rng.choice(ambient), "normal"))

        return msgs

    # ── Serialization ────────────────────────────────────────────────

    def to_dict(self) -> Dict:
        return {
            "player_faction": self.player_faction,
            "player_enlisted": self.player_enlisted,
            "player_enlist_war": self.player_enlist_war,
            "days_served": self.days_served,
            "kills_in_war": self.kills_in_war,
            "wounded_treated": self.wounded_treated,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "WarSystem":
        ws = cls()
        ws.player_faction = d.get("player_faction", "")
        ws.player_enlisted = d.get("player_enlisted", False)
        ws.player_enlist_war = d.get("player_enlist_war", "")
        ws.days_served = d.get("days_served", 0)
        ws.kills_in_war = d.get("kills_in_war", 0)
        ws.wounded_treated = d.get("wounded_treated", 0)
        return ws
