"""
src/legal.py

Legal system, crime, and punishment for American Prospector.

Frontier justice: fast, imperfect, often harsh. Hybrid design —
structured hard-coded trial flow with LLM only for player dialogue
(defense arguments, cross-examination, custom pleas).

Systems:
    CrimeRecord     — what happened, who saw it, evidence
    Witness         — NPC who saw the crime, with observation quality
    Evidence        — physical proof (weapon, stolen goods, blood)
    CourtType       — miners' court, town court, military tribunal
    Trial           — structured trial flow with phases
    Sentence        — punishment data
    LegalSystem     — manages all active cases, warrants, reputation

Crime → Investigation → Arrest → Trial → Sentence → Punishment
   ↑                                          ↓
   └── escape/bribe/intimidate ←──────────────┘

Integration:
    Engine holds LegalSystem.
    NPC witness system uses NPC memory + relationship.
    Reputation from economy.py feeds into trial outcomes.
    Clothing system checked for evidence (bloody clothes).
    LLM generates dialogue during player defense phases.
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from src.llm_client import LLMClient


# ============================================================================
#  CRIME DEFINITIONS
# ============================================================================

class CrimeType:
    THEFT         = "theft"
    ROBBERY       = "robbery"         # theft + force/threat
    ASSAULT       = "assault"
    MURDER        = "murder"
    CLAIM_JUMPING = "claim_jumping"
    FRAUD         = "fraud"           # cheating at cards, false assay, etc.
    TRESPASS      = "trespass"
    VANDALISM     = "vandalism"
    ARSON         = "arson"
    HORSE_THEFT   = "horse_theft"     # hanged for this
    DEBT_DEFAULT  = "debt_default"
    DISTURBING    = "disturbing_peace"
    SMUGGLING     = "smuggling"
    BRIBERY       = "bribery"         # if caught


CRIME_SEVERITY: Dict[str, int] = {
    # 1=minor, 2=moderate, 3=serious, 4=capital
    CrimeType.DISTURBING:    1,
    CrimeType.TRESPASS:      1,
    CrimeType.VANDALISM:     1,
    CrimeType.DEBT_DEFAULT:  2,
    CrimeType.THEFT:         2,
    CrimeType.FRAUD:         2,
    CrimeType.SMUGGLING:     2,
    CrimeType.BRIBERY:       2,
    CrimeType.ASSAULT:       3,
    CrimeType.ROBBERY:       3,
    CrimeType.CLAIM_JUMPING: 3,
    CrimeType.ARSON:         3,
    CrimeType.HORSE_THEFT:   4,
    CrimeType.MURDER:        4,
}

CRIME_LABELS: Dict[str, str] = {
    CrimeType.THEFT:         "Theft",
    CrimeType.ROBBERY:       "Robbery",
    CrimeType.ASSAULT:       "Assault",
    CrimeType.MURDER:        "Murder",
    CrimeType.CLAIM_JUMPING: "Claim Jumping",
    CrimeType.FRAUD:         "Fraud",
    CrimeType.TRESPASS:      "Trespass",
    CrimeType.VANDALISM:     "Vandalism",
    CrimeType.ARSON:         "Arson",
    CrimeType.HORSE_THEFT:   "Horse Theft",
    CrimeType.DEBT_DEFAULT:  "Debt Default",
    CrimeType.DISTURBING:    "Disturbing the Peace",
    CrimeType.SMUGGLING:     "Smuggling",
    CrimeType.BRIBERY:       "Bribery",
}


# ============================================================================
#  WITNESS
# ============================================================================

@dataclass
class Witness:
    """An NPC who observed a crime."""
    npc_id: str
    npc_name: str
    knows_player: bool          # can name the accused directly
    observation_quality: float  # 0.0-1.0 (how clearly they saw it)
    relationship: float         # toward the player at time of crime
    bias: float                 # -1=hostile witness, +1=sympathetic
    willing_to_testify: bool    # may refuse if afraid or friendly
    testimony: str              # what they'll say in court
    intimidated: bool = False   # player intimidated them into silence
    bribed: bool = False        # player bribed them to change story

    @property
    def credibility(self) -> float:
        """How believable this witness is (0-1)."""
        base = self.observation_quality
        if self.bribed or self.intimidated:
            base *= 0.3
        if abs(self.bias) > 0.5:
            base *= 0.7  # extreme bias reduces credibility
        return min(1.0, max(0.05, base))


def create_witness(npc, player_rel: float, crime_type: str,
                    distance: int = 1, line_of_sight: bool = True,
                    rng: Optional[random.Random] = None) -> Witness:
    """
    Create a witness record from an NPC who observed a crime.

    distance: tiles away when it happened
    line_of_sight: whether they had clear view
    """
    if rng is None:
        rng = random.Random()

    knows = getattr(npc, "memory", None) and getattr(npc.memory, "knows_name", False)
    npc_name = getattr(npc, "name", "Unknown")
    npc_id = getattr(npc, "npc_id", "")

    # Observation quality based on distance and conditions
    obs = 1.0
    if distance > 1:
        obs -= (distance - 1) * 0.15
    if not line_of_sight:
        obs *= 0.4  # heard it but didn't see clearly
    # NPC wisdom/intelligence affects memory
    wis = 10
    if hasattr(npc, "attributes"):
        wis = npc.attributes.get("wisdom", 10)
    obs *= min(1.2, wis / 10.0)
    obs = max(0.1, min(1.0, obs))

    # Bias from relationship
    bias = 0.0
    if player_rel > 40:
        bias = 0.3 + rng.uniform(0, 0.3)       # sympathetic
    elif player_rel < -20:
        bias = -0.3 - rng.uniform(0, 0.3)      # hostile

    # Willingness to testify
    willing = True
    if player_rel > 60:
        willing = rng.random() < 0.4   # good friends may refuse to testify
    traits = getattr(npc, "traits", [])
    if "cowardly" in traits or "nervous" in traits:
        willing = rng.random() < 0.6

    # Build testimony
    if knows:
        who = f"I saw the accused"
    else:
        who = "I saw a man"

    crime_verb = {
        CrimeType.THEFT: "take something that wasn't theirs",
        CrimeType.ROBBERY: "threaten and rob someone",
        CrimeType.ASSAULT: "attack someone",
        CrimeType.MURDER: "kill",
        CrimeType.CLAIM_JUMPING: "work someone else's claim",
        CrimeType.FRAUD: "cheat",
        CrimeType.ARSON: "set fire to",
        CrimeType.HORSE_THEFT: "ride off on a horse that wasn't theirs",
    }.get(crime_type, "do something unlawful")

    clarity = "clear as day" if obs > 0.8 else "from a ways off" if obs > 0.5 else "but it was dark"
    testimony = f'"{who} {crime_verb}. I saw it {clarity}."'

    return Witness(
        npc_id=npc_id, npc_name=npc_name, knows_player=knows,
        observation_quality=obs, relationship=player_rel,
        bias=bias, willing_to_testify=willing, testimony=testimony,
    )


# ============================================================================
#  EVIDENCE
# ============================================================================

@dataclass
class Evidence:
    """Physical evidence connected to a crime."""
    item_name: str              # "Bloody Hunting Knife"
    evidence_type: str          # "weapon"|"stolen_goods"|"clothing"|"document"|"tool"
    description: str
    strength: float             # 0.0-1.0 (how damning)
    found: bool = True          # has it been found/presented
    planted: bool = False       # player planted it on someone else
    disposed: bool = False      # player got rid of it


# ============================================================================
#  CRIME RECORD
# ============================================================================

@dataclass
class CrimeRecord:
    """A single criminal act tracked by the system."""
    id: int
    crime_type: str             # CrimeType
    day: int                    # game day it happened
    world_x: int                # where
    world_y: int
    region: str
    victim_name: str            # "" if victimless
    victim_npc_id: str = ""
    self_defense: bool = False  # player claims self-defense

    # Witnesses and evidence
    witnesses: List[Witness] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)

    # Investigation state
    reported: bool = False      # someone told the law
    investigated: bool = False
    warrant_issued: bool = False
    suspect_identified: bool = False  # law knows it was the player

    # Trial state
    tried: bool = False
    verdict: str = ""           # ""|"guilty"|"not_guilty"|"hung_jury"|"dismissed"
    sentence: Optional["Sentence"] = None

    # Escape
    escaped: bool = False       # player escaped custody

    @property
    def severity(self) -> int:
        return CRIME_SEVERITY.get(self.crime_type, 2)

    @property
    def label(self) -> str:
        return CRIME_LABELS.get(self.crime_type, self.crime_type)

    @property
    def has_strong_case(self) -> bool:
        """Prosecution has enough to convict."""
        witness_strength = sum(w.credibility for w in self.witnesses
                                if w.willing_to_testify and not w.intimidated)
        evidence_strength = sum(e.strength for e in self.evidence
                                 if e.found and not e.disposed)
        return (witness_strength + evidence_strength) > 0.8


# ============================================================================
#  COURT TYPES
# ============================================================================

class CourtType:
    MINERS_COURT  = "miners_court"    # informal, same-day, crowd votes
    TOWN_COURT    = "town_court"      # judge + jury, more formal
    MILITARY      = "military_court"  # martial law areas, very harsh


COURT_DATA: Dict[str, dict] = {
    CourtType.MINERS_COURT: {
        "label": "Miners' Court",
        "formality": 0.3,       # low formality = more sway from personality
        "corruption": 0.4,      # easier to bribe
        "speed_days": 0,        # same day
        "jury_size": 0,         # crowd votes, no formal jury
        "severity_mult": 1.0,
        "desc": "The camp gathers in a rough circle. No judge — just men with opinions.",
    },
    CourtType.TOWN_COURT: {
        "label": "Town Court",
        "formality": 0.7,
        "corruption": 0.2,
        "speed_days": 3,        # few days wait
        "jury_size": 12,
        "severity_mult": 0.9,   # slightly more lenient (due process)
        "desc": "The courtroom is a timber building with a raised bench for the judge.",
    },
    CourtType.MILITARY: {
        "label": "Military Tribunal",
        "formality": 0.9,
        "corruption": 0.1,
        "speed_days": 1,
        "jury_size": 5,         # panel of officers
        "severity_mult": 1.4,   # harsher sentences
        "desc": "Officers in blue sit behind a long table. This is Army justice.",
    },
}


def determine_court_type(settlement_type: str, has_sheriff: bool) -> str:
    """Pick court type based on where the crime is being tried."""
    if settlement_type in ("mining_camp_small", "mining_camp_medium"):
        return CourtType.MINERS_COURT
    if has_sheriff or settlement_type in ("small_town", "boomtown", "city"):
        return CourtType.TOWN_COURT
    return CourtType.MINERS_COURT


# ============================================================================
#  SENTENCE / PUNISHMENT
# ============================================================================

class PunishmentType:
    FINE          = "fine"
    FLOGGING      = "flogging"
    STOCKS        = "stocks"          # public humiliation
    BRANDING      = "branding"        # marked as criminal
    FORCED_LABOR  = "forced_labor"
    BANISHMENT    = "banishment"
    PRISON        = "prison"
    HANGING       = "hanging"


@dataclass
class Sentence:
    """Punishment assigned after conviction."""
    punishment: str             # PunishmentType
    fine_amount: float = 0.0    # dollars
    duration_days: int = 0      # for prison, forced labor, stocks
    description: str = ""
    served: bool = False
    day_started: int = 0

    @property
    def is_lethal(self) -> bool:
        return self.punishment == PunishmentType.HANGING


# Punishment tables by severity
PUNISHMENT_TABLE: Dict[int, List[Tuple[str, float]]] = {
    # severity → [(punishment_type, weight), ...]
    1: [
        (PunishmentType.FINE, 60),
        (PunishmentType.STOCKS, 25),
        (PunishmentType.FLOGGING, 15),
    ],
    2: [
        (PunishmentType.FINE, 40),
        (PunishmentType.FLOGGING, 25),
        (PunishmentType.STOCKS, 15),
        (PunishmentType.FORCED_LABOR, 15),
        (PunishmentType.BANISHMENT, 5),
    ],
    3: [
        (PunishmentType.PRISON, 35),
        (PunishmentType.FLOGGING, 20),
        (PunishmentType.FORCED_LABOR, 20),
        (PunishmentType.BANISHMENT, 15),
        (PunishmentType.BRANDING, 10),
    ],
    4: [
        (PunishmentType.HANGING, 50),
        (PunishmentType.PRISON, 30),
        (PunishmentType.BANISHMENT, 10),
        (PunishmentType.FORCED_LABOR, 10),
    ],
}

FINE_RANGES: Dict[int, Tuple[float, float]] = {
    1: (2.0, 20.0),
    2: (10.0, 100.0),
    3: (50.0, 500.0),
    4: (100.0, 1000.0),
}

PRISON_RANGES: Dict[int, Tuple[int, int]] = {
    1: (1, 3),
    2: (3, 14),
    3: (14, 90),
    4: (30, 365),
}


def determine_sentence(crime: CrimeRecord, court_type: str,
                         player_rep: float = 0.0,
                         rng: Optional[random.Random] = None) -> Sentence:
    """Generate a sentence based on crime severity, court, and reputation."""
    if rng is None:
        rng = random.Random()

    court = COURT_DATA.get(court_type, COURT_DATA[CourtType.TOWN_COURT])
    sev = crime.severity

    # Self-defense reduces effective severity
    if crime.self_defense and sev > 1:
        sev = max(1, sev - 1)

    # Good reputation reduces effective severity (slightly)
    if player_rep > 30 and sev > 1:
        if rng.random() < 0.3:
            sev = max(1, sev - 1)

    # Pick punishment type
    pool = PUNISHMENT_TABLE.get(sev, PUNISHMENT_TABLE[2])
    types = [p[0] for p in pool]
    weights = [p[1] for p in pool]
    punishment = rng.choices(types, weights=weights, k=1)[0]

    # Court severity multiplier
    sev_mult = court.get("severity_mult", 1.0)

    # Generate specifics
    fine = 0.0
    duration = 0
    if punishment == PunishmentType.FINE:
        lo, hi = FINE_RANGES.get(sev, (5, 50))
        fine = round(rng.uniform(lo, hi) * sev_mult, 2)
    elif punishment in (PunishmentType.PRISON, PunishmentType.FORCED_LABOR):
        lo, hi = PRISON_RANGES.get(sev, (3, 30))
        duration = int(rng.randint(lo, hi) * sev_mult)
    elif punishment == PunishmentType.STOCKS:
        duration = rng.randint(1, 3)
    elif punishment == PunishmentType.FLOGGING:
        duration = 1  # one session

    desc_map = {
        PunishmentType.FINE: f"Fined ${fine:.2f}.",
        PunishmentType.FLOGGING: f"Sentenced to {rng.randint(10, 40)} lashes.",
        PunishmentType.STOCKS: f"Sentenced to {duration} day{'s' if duration > 1 else ''} in the stocks.",
        PunishmentType.BRANDING: "Branded on the hand as a criminal.",
        PunishmentType.FORCED_LABOR: f"Sentenced to {duration} days hard labor.",
        PunishmentType.BANISHMENT: "Banished from the settlement. Return means hanging.",
        PunishmentType.PRISON: f"Sentenced to {duration} days in jail.",
        PunishmentType.HANGING: "Sentenced to hang by the neck until dead.",
    }

    return Sentence(
        punishment=punishment, fine_amount=fine, duration_days=duration,
        description=desc_map.get(punishment, "Punishment undetermined."),
    )


# ============================================================================
#  TRIAL RESOLUTION
# ============================================================================

def resolve_trial(crime: CrimeRecord, court_type: str,
                   player_charisma: int = 10,
                   player_intelligence: int = 10,
                   player_law_skill: int = 0,
                   player_rep: float = 0.0,
                   defense_quality: float = 0.5,
                   rng: Optional[random.Random] = None) -> str:
    """
    Resolve the verdict mechanically.

    defense_quality: 0.0-1.0 from LLM evaluation of player's defense speech.
    Returns: "guilty" | "not_guilty" | "hung_jury" | "dismissed"
    """
    if rng is None:
        rng = random.Random()

    court = COURT_DATA.get(court_type, COURT_DATA[CourtType.TOWN_COURT])

    # Prosecution strength
    prosecution = 0.0
    for w in crime.witnesses:
        if w.willing_to_testify and not w.intimidated:
            prosecution += w.credibility * 0.3
    for e in crime.evidence:
        if e.found and not e.disposed:
            prosecution += e.strength * 0.3

    # Defense strength
    defense = defense_quality * 0.4
    defense += player_law_skill * 0.03
    defense += max(0, (player_charisma - 10)) * 0.02
    defense += max(0, (player_intelligence - 10)) * 0.01

    # Self-defense claim
    if crime.self_defense:
        defense += 0.25

    # Reputation effect
    if player_rep > 30:
        defense += 0.10
    elif player_rep < -30:
        prosecution += 0.10

    # Formality affects how much personality matters
    formality = court.get("formality", 0.5)
    # Low formality = charisma matters more
    cha_bonus = max(0, (player_charisma - 10) * 0.02) * (1.0 - formality)
    defense += cha_bonus

    # Final calculation
    net = prosecution - defense + rng.uniform(-0.15, 0.15)

    if net > 0.5:
        return "guilty"
    if net > 0.2:
        # Borderline — chance of hung jury
        if rng.random() < 0.3:
            return "hung_jury"
        return "guilty"
    if net > -0.1:
        return "not_guilty"  # reasonable doubt
    return "not_guilty"


# ============================================================================
#  CORRUPTION & BRIBERY
# ============================================================================

def attempt_bribe(target_type: str, amount: float,
                   court_type: str, player_charisma: int,
                   rng: Optional[random.Random] = None
                   ) -> Tuple[bool, str]:
    """
    Attempt to bribe a witness, judge, or jailer.
    target_type: "witness"|"judge"|"jailer"|"sheriff"
    Returns (success, message).
    """
    if rng is None:
        rng = random.Random()

    court = COURT_DATA.get(court_type, COURT_DATA[CourtType.TOWN_COURT])
    corruption = court.get("corruption", 0.2)

    # Base chance from corruption level and money
    base = corruption * 0.5
    # Money matters — more = more likely
    money_factor = min(0.4, amount / 200.0)
    # Charisma helps
    cha_bonus = max(0, (player_charisma - 10)) * 0.02

    chance = min(0.85, base + money_factor + cha_bonus)

    # Targets have different susceptibility
    target_mod = {
        "witness": 0.10,
        "jailer":  0.05,
        "sheriff": -0.10,
        "judge":   -0.15,
    }.get(target_type, 0.0)
    chance += target_mod

    if rng.random() < chance:
        msgs = {
            "witness": "The witness pockets the money and nods slowly.",
            "judge":   "The judge's eyes flicker. A barely perceptible nod.",
            "jailer":  "The jailer glances both ways and unlocks the door.",
            "sheriff": "The sheriff takes the money with a hard look.",
        }
        return True, msgs.get(target_type, "The bribe is accepted.")

    # Failed — caught?
    if rng.random() < 0.4:
        return False, (f"\"You dare try to bribe me?\" "
                       f"The {target_type} is furious. This will be reported.")
    return False, f"The {target_type} shakes their head and pushes the money back."


def attempt_intimidate(witness: Witness, player_str: int,
                        player_charisma: int,
                        rng: Optional[random.Random] = None
                        ) -> Tuple[bool, str]:
    """Attempt to intimidate a witness into silence."""
    if rng is None:
        rng = random.Random()

    # Strength and charisma both contribute
    score = player_str * 0.04 + player_charisma * 0.02
    # Easier if witness relationship is positive (they want to help)
    if witness.relationship > 20:
        score += 0.15
    # Harder if witness is brave
    score -= 0.10  # base difficulty

    if rng.random() < max(0.05, min(0.80, score)):
        witness.intimidated = True
        witness.willing_to_testify = False
        return True, f"{witness.npc_name} swallows hard. \"I... I didn't see anything.\""

    return False, (f"{witness.npc_name} stands firm. "
                   f"\"I know what I saw.\" They look ready to tell the sheriff.")


# ============================================================================
#  ESCAPE
# ============================================================================

def attempt_jailbreak(player_agility: int, player_strength: int,
                       has_tools: bool = False,
                       guard_alert: float = 0.5,
                       rng: Optional[random.Random] = None
                       ) -> Tuple[bool, str]:
    """
    Attempt to escape from jail or custody.
    Returns (success, narrative).
    """
    if rng is None:
        rng = random.Random()

    base = 0.15
    base += (player_agility - 10) * 0.03
    base += (player_strength - 10) * 0.02
    if has_tools:
        base += 0.20
    base -= guard_alert * 0.15

    if rng.random() < max(0.05, min(0.70, base)):
        methods = [
            "You work a bar loose in the window and squeeze through into the night.",
            "When the guard dozes off, you slip the lock with a bent nail.",
            "You overpower the guard when he brings supper and take his keys.",
            "You dig through the sod wall with your bare hands and crawl free.",
        ]
        return True, rng.choice(methods)

    fails = [
        "The guard catches you in the act. Extra days added to your sentence.",
        "The window bar won't budge. You're stuck.",
        "You almost make it but the door is heavier than expected. The guard wakes up.",
    ]
    return False, rng.choice(fails)


# ============================================================================
#  LLM DEFENSE EVALUATION
# ============================================================================

_DEFENSE_SYSTEM = """\
You are a frontier judge in 1849 America evaluating a defendant's argument. \
Based on the crime, evidence, and the defendant's words, rate how convincing \
the defense is.

Consider: Is the argument plausible? Does it address the evidence? Is it \
emotionally compelling? Would a jury of miners and townsmen believe it?

The defendant's Charisma is {cha}/18 and Intelligence is {int}/18 — \
factor this into how articulate and persuasive they sound. Low charisma \
means even a good argument comes out poorly. High charisma can sell a \
mediocre argument.

Return ONLY JSON: {{"quality": <float 0.0-1.0>, "reaction": "<1 sentence \
judge/jury reaction>"}}
"""


def evaluate_defense(llm: "LLMClient",
                      crime_summary: str,
                      evidence_summary: str,
                      player_speech: str,
                      player_cha: int = 10,
                      player_int: int = 10) -> Tuple[float, str]:
    """
    LLM evaluates the player's defense argument.
    Returns (quality 0-1, judge_reaction_text).
    """
    if not llm or not llm.available:
        # Heuristic fallback: longer + more specific = better
        words = len(player_speech.split())
        quality = min(0.8, words * 0.03 + 0.1)
        return quality, "The court considers your words."

    system = _DEFENSE_SYSTEM.format(cha=player_cha, int=player_int)
    prompt = (
        f"CRIME: {crime_summary}\n"
        f"EVIDENCE AGAINST: {evidence_summary}\n"
        f"DEFENDANT SAYS: \"{player_speech}\"\n\n"
        f"Rate this defense 0.0-1.0 and give a jury reaction."
    )

    try:
        import json
        raw = llm._chat(
            [{"role": "system", "content": system},
             {"role": "user",   "content": prompt}],
            temperature=0.35, max_tokens=150, json_mode=True,
        )
        data = json.loads(raw)
        quality = max(0.0, min(1.0, float(data.get("quality", 0.3))))
        reaction = str(data.get("reaction", ""))
        return quality, reaction
    except Exception:
        return 0.3, "The court listens impassively."


# ============================================================================
#  LEGAL SYSTEM — manages all crime state
# ============================================================================

class LegalSystem:
    """
    Manages all crimes, warrants, investigations, and sentences.
    Integrates with NPC memory (witnesses), reputation, and economy (fines).
    """

    def __init__(self):
        self.crimes: List[CrimeRecord] = []
        self.active_warrants: List[int] = []    # crime IDs with active warrants
        self.sentences_active: List[Sentence] = []
        self._counter = 0

    def _next_id(self) -> int:
        self._counter += 1
        return self._counter

    # ── Record a crime ─────────────────────────────────────────────────

    def record_crime(self, crime_type: str, day: int,
                      wx: int, wy: int, region: str,
                      victim_name: str = "",
                      victim_npc_id: str = "",
                      self_defense: bool = False,
                      nearby_npcs: Optional[list] = None,
                      player_rel_map: Optional[Dict[str, float]] = None,
                      wartime_kill: bool = False,
                      ) -> Optional["CrimeRecord"]:
        """
        Record a crime and automatically generate witnesses from nearby NPCs.
        Returns None if the kill is a legitimate wartime action.
        """
        # Wartime kills are not crimes
        if wartime_kill:
            return None

        crime = CrimeRecord(
            id=self._next_id(), crime_type=crime_type, day=day,
            world_x=wx, world_y=wy, region=region,
            victim_name=victim_name, victim_npc_id=victim_npc_id,
            self_defense=self_defense,
        )

        # Generate witnesses from nearby NPCs
        if nearby_npcs:
            rel_map = player_rel_map or {}
            for npc in nearby_npcs:
                npc_id = getattr(npc, "npc_id", "")
                if npc_id == victim_npc_id:
                    continue  # victim is not a witness
                if not getattr(npc, "alive", True):
                    continue
                rel = rel_map.get(npc_id, getattr(npc, "relationship", 0.0))
                w = create_witness(npc, rel, crime_type)
                crime.witnesses.append(w)

        # Auto-report based on witness count and type
        if crime.witnesses:
            crime.reported = True
            # If any witness knows the player, suspect identified
            if any(w.knows_player for w in crime.witnesses):
                crime.suspect_identified = True

        self.crimes.append(crime)

        # Issue warrant for serious crimes with identified suspect
        if crime.suspect_identified and crime.severity >= 3:
            crime.warrant_issued = True
            self.active_warrants.append(crime.id)

        return crime

    # ── Add evidence ───────────────────────────────────────────────────

    def add_evidence(self, crime_id: int, item_name: str,
                      evidence_type: str, description: str,
                      strength: float = 0.5) -> None:
        for crime in self.crimes:
            if crime.id == crime_id:
                crime.evidence.append(Evidence(
                    item_name=item_name, evidence_type=evidence_type,
                    description=description, strength=strength,
                ))
                return

    # ── Query ──────────────────────────────────────────────────────────

    def has_active_warrant(self) -> bool:
        return len(self.active_warrants) > 0

    def warrants_in_region(self, region: str) -> List[CrimeRecord]:
        return [c for c in self.crimes
                if c.id in self.active_warrants and c.region == region]

    def untried_crimes(self) -> List[CrimeRecord]:
        return [c for c in self.crimes if c.reported and not c.tried]

    def serving_sentence(self) -> Optional[Sentence]:
        for s in self.sentences_active:
            if not s.served:
                return s
        return None

    def criminal_record(self) -> List[CrimeRecord]:
        return [c for c in self.crimes if c.verdict == "guilty"]

    # ── Resolve trial ──────────────────────────────────────────────────

    def run_trial(self, crime_id: int, court_type: str,
                   player_cha: int, player_int: int,
                   player_law: int, player_rep: float,
                   defense_quality: float) -> Tuple[str, Optional[Sentence]]:
        """
        Run a full trial and return (verdict, sentence_or_None).
        """
        crime = None
        for c in self.crimes:
            if c.id == crime_id:
                crime = c
                break
        if not crime:
            return "dismissed", None

        verdict = resolve_trial(
            crime, court_type, player_cha, player_int,
            player_law, player_rep, defense_quality)

        crime.tried = True
        crime.verdict = verdict

        if crime.id in self.active_warrants:
            self.active_warrants.remove(crime.id)

        if verdict == "guilty":
            sentence = determine_sentence(crime, court_type, player_rep)
            crime.sentence = sentence
            self.sentences_active.append(sentence)
            return "guilty", sentence

        return verdict, None

    # ── Serving sentences ──────────────────────────────────────────────

    def tick_sentence(self, current_day: int) -> Optional[str]:
        """Check if any active sentence has been served."""
        for s in self.sentences_active:
            if s.served:
                continue
            if s.punishment in (PunishmentType.PRISON, PunishmentType.FORCED_LABOR,
                                 PunishmentType.STOCKS):
                if s.day_started > 0 and current_day - s.day_started >= s.duration_days:
                    s.served = True
                    return f"Your {s.punishment.replace('_', ' ')} sentence is complete. You are free."
        return None

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> Dict:
        return {
            "counter": self._counter,
            "active_warrants": self.active_warrants,
            "crimes": [
                {
                    "id": c.id, "crime_type": c.crime_type, "day": c.day,
                    "world_x": c.world_x, "world_y": c.world_y,
                    "region": c.region, "victim_name": c.victim_name,
                    "self_defense": c.self_defense,
                    "reported": c.reported, "investigated": c.investigated,
                    "warrant_issued": c.warrant_issued,
                    "suspect_identified": c.suspect_identified,
                    "tried": c.tried, "verdict": c.verdict,
                    "escaped": c.escaped,
                    "witnesses": [
                        {"npc_id": w.npc_id, "npc_name": w.npc_name,
                         "knows_player": w.knows_player,
                         "observation_quality": w.observation_quality,
                         "credibility": w.credibility,
                         "willing_to_testify": w.willing_to_testify,
                         "intimidated": w.intimidated, "bribed": w.bribed}
                        for w in c.witnesses
                    ],
                    "evidence": [
                        {"item_name": e.item_name, "evidence_type": e.evidence_type,
                         "description": e.description,
                         "strength": e.strength, "found": e.found,
                         "planted": e.planted, "disposed": e.disposed}
                        for e in c.evidence
                    ],
                }
                for c in self.crimes
            ],
            "sentences": [
                {"punishment": s.punishment, "fine_amount": s.fine_amount,
                 "duration_days": s.duration_days, "description": s.description,
                 "served": s.served, "day_started": s.day_started}
                for s in self.sentences_active
            ],
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "LegalSystem":
        ls = cls()
        ls._counter = d.get("counter", 0)
        ls.active_warrants = d.get("active_warrants", [])
        for cd in d.get("crimes", []):
            crime = CrimeRecord(
                id=cd["id"], crime_type=cd["crime_type"], day=cd["day"],
                world_x=cd["world_x"], world_y=cd["world_y"],
                region=cd["region"], victim_name=cd.get("victim_name", ""),
                self_defense=cd.get("self_defense", False),
                reported=cd.get("reported", False),
                investigated=cd.get("investigated", False),
                warrant_issued=cd.get("warrant_issued", False),
                suspect_identified=cd.get("suspect_identified", False),
                tried=cd.get("tried", False), verdict=cd.get("verdict", ""),
                escaped=cd.get("escaped", False),
            )
            for wd in cd.get("witnesses", []):
                crime.witnesses.append(Witness(
                    npc_id=wd["npc_id"], npc_name=wd["npc_name"],
                    knows_player=wd.get("knows_player", False),
                    observation_quality=wd.get("observation_quality", 0.5),
                    relationship=wd.get("relationship", 0.0),
                    bias=wd.get("bias", 0.0),
                    willing_to_testify=wd.get("willing_to_testify", True),
                    testimony=wd.get("testimony", ""),
                    intimidated=wd.get("intimidated", False),
                    bribed=wd.get("bribed", False),
                ))
            for ed in cd.get("evidence", []):
                crime.evidence.append(Evidence(
                    item_name=ed["item_name"],
                    evidence_type=ed.get("evidence_type", ed.get("type", "")),
                    description=ed.get("description", ""),
                    strength=ed.get("strength", 0.5),
                    found=ed.get("found", True),
                    planted=ed.get("planted", False),
                    disposed=ed.get("disposed", False),
                ))
            ls.crimes.append(crime)
        for sd in d.get("sentences", []):
            ls.sentences_active.append(Sentence(**sd))
        return ls
