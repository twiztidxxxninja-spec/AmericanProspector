"""
src/npc_speech.py

Template pools for NPC conversation — untranslated foreign speech,
NPC-initiated topics, memory-informed greetings, personality suffixes.
All pure data — no LLM calls. Functions here select and format templates.
"""

import random
from typing import List, Tuple, Optional, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from src.npc_system import NPCExpanded
    from src.player import Player


# ============================================================================
#  UNTRANSLATED SPEECH — when player shares no language with NPC
# ============================================================================

UNTRANSLATED: Dict[str, List[str]] = {
    # Native tribes
    "crow": [
        "*{name} speaks.* \"Ahó. Báaleetche kaashée.\"",
        "*{name} gestures and speaks rapidly in Crow. You understand nothing.*",
        "*{name} says something in Crow, watching your face for comprehension.*",
        "*{name} speaks at length, then stops when they see your blank expression.*",
    ],
    "shoshone": [
        "*{name} speaks.* \"Taikka. Sundaiko nüümü.\"",
        "*{name} gestures and speaks Shoshone. The words mean nothing to you.*",
        "*{name} says something carefully in Shoshone, pointing as they talk.*",
    ],
    "blackfeet": [
        "*{name} speaks.* \"Oki. Nitsiniiyi'taki.\"",
        "*{name} speaks sharply in Blackfoot. The tone is clear even if the words are not.*",
        "*{name} watches you with hard eyes and says something in Blackfoot.*",
    ],
    "flathead": [
        "*{name} speaks.* \"Qe ci yóu.\"",
        "*{name} gestures and speaks Salish. You catch nothing.*",
    ],
    "nez_perce": [
        "*{name} speaks.* \"Tááks. Wéetes hiwéhyem.\"",
        "*{name} says something in Nez Perce, their expression patient.*",
    ],
    "ute": [
        "*{name} speaks.* \"Tuvuci. Marúgway.\"",
        "*{name} speaks Ute, gesturing broadly toward the mountains.*",
    ],
    "arapaho": [
        "*{name} speaks.* \"Háahe. Heetíini.\"",
        "*{name} says something in Arapaho. You have no idea what.*",
    ],
    "cheyenne": [
        "*{name} speaks.* \"Néá'eše. Hová'âháne.\"",
        "*{name} speaks Cheyenne, their voice low and measured.*",
    ],
    "lakota_sioux": [
        "*{name} speaks.* \"Háu. Mitákuye Oyás'iŋ.\"",
        "*{name} speaks Lakota. The words carry weight you cannot parse.*",
    ],
    # Non-English settlers
    "chinese": [
        "*{name} shakes their head.* \"Bù dǒng. Bù dǒng.\"",
        "*{name} speaks.* \"Wǒ bù huì shuō yīngyǔ.\" *They gesture apologetically.*",
        "*{name} tries to communicate.* \"Nǐ hǎo...\" *But trails off, unable to go further.*",
        "*{name} speaks rapidly in Cantonese. You catch nothing.*",
    ],
    "spanish": [
        "*{name} shrugs.* \"No hablo inglés, amigo.\"",
        "*{name} speaks.* \"No entiendo. ¿Habla usted español?\"",
        "*{name} gestures helplessly.* \"Inglés... no. Lo siento.\"",
        "*{name} tries slowly.* \"Yo... no... speak.\" *They give up and switch to Spanish.*",
    ],
    "french": [
        "*{name} speaks.* \"Je ne parle pas anglais, monsieur.\"",
        "*{name} shakes their head.* \"Non, non. Français seulement.\"",
        "*{name} tries.* \"I... no... parler.\" *They lapse back into French.*",
    ],
    "german": [
        "*{name} speaks.* \"Ich verstehe nicht. Sprechen Sie Deutsch?\"",
        "*{name} shakes their head.* \"Nein... kein Englisch.\"",
    ],
}

# Sign-language level responses — gestures and single words
SIGN_RESPONSES: Dict[str, List[str]] = {
    "trade": [
        "*{name} holds up a beaver pelt and points at your pack, then rubs fingers together.*",
        "*{name} lays out goods on a blanket and gestures for you to do the same.*",
        "*{name} holds up items one by one, watching your face for interest.*",
    ],
    "directions": [
        "*{name} points {direction} and holds up {count} fingers.* {count} days.",
        "*{name} draws in the dirt — a river, mountains, a trail heading {direction}.*",
        "*{name} points firmly {direction}, then makes a walking motion with two fingers.*",
    ],
    "weather": [
        "*{name} looks at the sky and makes a shivering motion.* Cold coming.",
        "*{name} points at the clouds and mimics rain with their fingers.*",
        "*{name} sweeps their hand across the horizon. Clear skies, they seem to say.*",
    ],
    "peace_greeting": [
        "*{name} holds up an open palm. Peace.*",
        "*{name} touches their chest, then extends their hand toward you.* Friend.",
        "*{name} makes the sign for peace — palm out, fingers up.*",
    ],
    "territory_warn": [
        "*{name} sweeps their arm across the land and taps their chest firmly.* Our land.",
        "*{name} draws a line in the dirt and points at you, then behind the line.* Stay back.",
        "*{name} points at the ground, then at you, and shakes their head slowly.* Not welcome.",
    ],
    "leave": [
        "*{name} waves dismissively. The conversation is over.*",
        "*{name} turns away. There is nothing more to say without words.*",
    ],
}

# Pidgin-level responses — broken shared language
PIDGIN_RESPONSES: Dict[str, List[str]] = {
    "trade": [
        "*{name} nods.* \"Trade. Yes. You have... good things?\"",
        "\"We trade. Show what you bring.\"",
    ],
    "directions": [
        "\"That way —\" *{name} points {direction}.* \"{count} day walk. River there.\"",
        "\"Go {direction}. Not far. Maybe {count} day.\"",
    ],
    "hunt_request": [
        "\"You want hunt here? Must ask chief. Bring gift.\"",
        "\"Hunt — maybe. You good with {tribe}? Chief say yes, you hunt.\"",
    ],
    "tribal_news": [
        "\"Bad thing happen. White men come, take land. Chief angry.\"",
        "\"Good hunting this moon. Elk many. Buffalo come back.\"",
        "\"Other tribe — {other_tribe} — they move camp. Trouble maybe.\"",
    ],
    "guide_hire": [
        "\"I show you way. You pay — tobacco, beads, knife. Fair?\"",
        "\"Guide? I know this land. My people walk it since grandfathers.\"",
    ],
    "trapping_rights": [
        "\"Trap here? This our water. Our beaver. You give gift to chief first.\"",
        "\"You want trap? Must share. Half pelts for tribe. Fair?\"",
    ],
    "safe_passage": [
        "\"You pass through. No trouble. But no hunt, no trap. Just walk.\"",
        "\"Safe? If chief say yes. Bring gift. Show respect.\"",
    ],
}


# ============================================================================
#  NPC-INITIATED TOPICS — NPC brings up their own concerns
# ============================================================================

NPC_INITIATIVE_TEMPLATES: Dict[str, List[str]] = {
    "wounded": [
        "*{name} winces and clutches their side.* \"You wouldn't have any bandages? Got cut up bad.\"",
        "*{name} grimaces.* \"Don't suppose you know any doctoring? This wound's going sour.\"",
        "*{name} leans against a post, breathing hard.* \"I need help. It ain't healing right.\"",
        "*{name} shows you a bloody rag wrapped around their arm.* \"Won't stop bleeding.\"",
        "*{name} is pale and sweating.* \"I ain't doing good. You got anything for the pain?\"",
    ],
    "destitute": [
        "*{name} looks hollow-eyed.* \"Friend, I ain't eaten in two days. Could you spare anything?\"",
        "*{name}'s clothes are ragged.* \"I'm in a bad way. Any work you need done? Anything at all?\"",
        "*{name} eyes your pack hungrily.* \"I hate to beg, but... I got nothing left.\"",
        "*{name} shivers.* \"Lost everything. Claim went dry, supplies ran out. I'm done for.\"",
    ],
    "jealous": [
        "\"You know that {other_name}? {reason}. Watch yourself around that one.\"",
        "\"I wouldn't trust {other_name} far as I could throw him. {reason}.\"",
        "*{name} lowers their voice.* \"{other_name}? He ain't what he seems. {reason}.\"",
        "\"Between you and me — {other_name} is no good. {reason}.\"",
    ],
    "wealthy": [
        "*{name}'s eyes gleam.* \"Had a real good strike last week. Things are finally looking up.\"",
        "\"Business has been fine. Real fine. Can't complain.\" *{name} grins.*",
        "*{name} pats their pocket.* \"Made more this month than the last six put together.\"",
        "\"The Lord provides, friend. And lately He's been generous.\"",
    ],
    "danger_warning": [
        "\"Be careful out there. {detail}\"",
        "\"I wouldn't go {direction} if I were you. {detail}\"",
        "*{name} grabs your arm.* \"Listen — {detail}. I'm telling you.\"",
        "\"Word is {detail}. Watch yourself.\"",
    ],
    "favor_reminder": [
        "\"Say — you still owe me for {detail}. Ain't forgotten.\"",
        "*{name} gives you a look.* \"About that favor... {detail}. We square?\"",
        "\"Don't mean to press, but {detail}. A man's word is his bond out here.\"",
    ],
    "gossip": [
        "\"Did you hear? {detail}\"",
        "*{name} leans in.* \"You ain't gonna believe this — {detail}\"",
        "\"Everybody's talking about it. {detail}\"",
        "\"Word around camp is {detail}. Take it for what it's worth.\"",
    ],
    "motivation_plea": [
        "*{name} looks troubled.* \"Can I tell you something? {detail}\"",
        "*{name} hesitates, then speaks quietly.* \"{detail}\"",
        "\"I ain't told nobody this, but... {detail}\"",
        "*{name} stares into the distance.* \"{detail}. That's why I'm really out here.\"",
    ],
    "tribal_tension": [
        "*{name} looks wary.* \"The {tribe} are not happy. Tread careful in their land.\"",
        "\"You been through {tribe} territory? They don't take kindly to trappers right now.\"",
        "*{name} shakes their head.* \"Bad blood with the {tribe}. Stay clear if you can.\"",
    ],
}


# ============================================================================
#  MEMORY-INFORMED GREETINGS
# ============================================================================

MEMORY_GREETINGS: Dict[str, List[str]] = {
    "positive_recent": [
        "*{name} brightens when they see you.* \"Good to see you again, friend.\"",
        "\"Well, look who it is. How've you been?\" *{name} smiles.*",
        "*{name} waves you over.* \"Come sit down. Been hoping you'd pass through.\"",
        "\"Ah, {player}! Just the person I wanted to see.\"",
    ],
    "negative_recent": [
        "*{name} stiffens when they see you.* \"Back again? What do you want?\"",
        "*{name} gives you a cold look.* \"I remember you.\"",
        "\"Hmph.\" *{name} doesn't look pleased to see you.*",
        "*{name}'s jaw tightens.* \"Didn't think you'd show your face again.\"",
    ],
    "helped_npc": [
        "*{name} clasps your hand.* \"I won't forget what you did for me.\"",
        "\"Friend! Good to see you. I still owe you for last time.\"",
        "*{name} looks genuinely grateful.* \"You're a good man, {player}. Few enough of those out here.\"",
    ],
    "npc_owes_debt": [
        "*{name} looks uncomfortable when they see you.*",
        "*{name} avoids your eyes at first.* \"Oh. It's you.\"",
        "*{name} shifts their weight.* \"I ain't forgot what I owe you. Just... give me time.\"",
    ],
    "first_meeting": [
        "*{name} looks you over.* \"Don't think we've met. I'm {name}.\"",
        "\"You're new around here, ain't you? Name's {name}.\"",
        "*{name} nods at you.* \"Howdy, stranger.\"",
        "*{name} tips their hat.* \"Don't believe I've seen you before.\"",
    ],
    "close_friend": [
        "*{name} grins wide.* \"There he is! Get over here, {player}.\"",
        "\"Lord, it's good to see a friendly face. How are you, {player}?\"",
        "*{name} claps you on the shoulder.* \"Been too long, friend.\"",
    ],
    "enemy": [
        "*{name} goes very still.* \"You got nerve showing up here.\"",
        "*{name}'s hand moves toward their belt.* \"We ain't friends. Say your piece.\"",
        "\"What do you want?\" *{name}'s voice is flat and hostile.*",
    ],
}


# ============================================================================
#  PERSONALITY SUFFIXES — appended to knowledge/preset responses
# ============================================================================

PERSONALITY_SUFFIXES: Dict[str, List[str]] = {
    "boastful": [
        " I'm the best there is at this. Ask anyone.",
        " Nobody knows this better than me.",
        " I could do this in my sleep.",
        " Learned from the best — and I mean me.",
    ],
    "cautious": [
        " But be careful. I've seen men get killed doing it wrong.",
        " Mind yourself, though. It ain't as simple as it sounds.",
        " Take it slow. Rushing gets men buried.",
    ],
    "greedy": [
        " Course, I wouldn't tell just anyone. Information ain't free.",
        " That's worth knowing. You owe me one.",
        " Don't go spreading that around. That's between us.",
    ],
    "generous": [
        " Happy to help. We're all in this together.",
        " Ask me anything. I got no secrets about the work.",
    ],
    "suspicious": [
        " Why do you want to know? You working for someone?",
        " Don't go telling people I told you this.",
    ],
    "devout": [
        " The Lord willing, it'll work out for you.",
        " Say a prayer before you try it. Can't hurt.",
    ],
    "pessimistic": [
        " Not that it matters. We'll all be dead or broke by winter.",
        " Don't get your hopes up, though.",
    ],
    "cheerful": [
        " It's a fine thing to know. Makes the work worthwhile!",
        " Ain't that something? I love this country.",
    ],
}


# ============================================================================
#  DEFLECTION TEMPLATES — when NPC is lying or evading
# ============================================================================

DEFLECTION_TEMPLATES: Dict[str, List[str]] = {
    "change_subject": [
        "\"Hmm? Never mind that. You hear what happened downriver?\"",
        "\"That ain't important. Let's talk about something else.\"",
        "*{name} suddenly finds something interesting on the ground.*",
        "\"Why do you care about that? Let me tell you about...\"",
    ],
    "vague_denial": [
        "\"I don't rightly recall.\"",
        "\"That was a long time ago. Don't matter now.\"",
        "*{name} looks away.* \"Ain't much to tell.\"",
        "\"My memory ain't what it used to be.\"",
    ],
    "nervous_evasion": [
        "*{name} shifts uncomfortably.* \"Why do you ask?\"",
        "*{name}'s eyes dart to the side.* \"I'd rather not say.\"",
        "\"That's... let's talk about something else.\" *{name} won't meet your eyes.*",
        "*{name} scratches behind their ear.* \"I don't know nothing about that.\"",
    ],
    "flat_lie": [
        "\"Nothing to hide, friend. Just a {occupation} trying to make a living.\"",
        "\"My past? Boring as dirt. Grew up on a farm, came west.\"",
        "\"I'm an open book.\" *{name} smiles a little too quickly.*",
    ],
}


# ============================================================================
#  TOPIC GENERATOR — selects NPC-initiated lines from game state
# ============================================================================

def generate_npc_topics(npc: "NPCExpanded", player: "Player",
                        time_period: str, weather: str,
                        current_day: int,
                        tribal=None,
                        rng: random.Random = None,
                        ) -> List[Tuple[float, str]]:
    """
    Check NPC state and return 0-N priority-scored initiative topics.
    Returns list of (urgency, formatted_line).
    Caller should pick the top 0-2 and inject into conversation.
    """
    if rng is None:
        rng = random.Random()

    topics: List[Tuple[float, str]] = []
    name = npc.name

    # -- Wounded NPC asks for help --
    if hasattr(npc, 'wounds') and npc.wounds and hasattr(npc.wounds, 'wounds'):
        active = [w for w in npc.wounds.wounds if w.is_bleeding or w.infected]
        if active:
            msg = rng.choice(NPC_INITIATIVE_TEMPLATES["wounded"])
            topics.append((0.9, msg.format(name=name)))
        elif npc.wounds.wounds:
            msg = rng.choice(NPC_INITIATIVE_TEMPLATES["wounded"])
            topics.append((0.6, msg.format(name=name)))

    # -- Destitute NPC begs --
    fortune = getattr(npc, 'fortune', 'average')
    if fortune == "destitute":
        msg = rng.choice(NPC_INITIATIVE_TEMPLATES["destitute"])
        topics.append((0.8, msg.format(name=name)))

    # -- Wealthy NPC brags --
    if fortune == "wealthy":
        msg = rng.choice(NPC_INITIATIVE_TEMPLATES["wealthy"])
        topics.append((0.3, msg.format(name=name)))

    # -- Jealous NPC badmouths --
    opinions = getattr(npc, 'npc_opinions', {})
    for npc_id, op_data in opinions.items():
        opinion_val = op_data.get("opinion", 0)
        if opinion_val < -30:
            other_name = op_data.get("name", "someone")
            reason = op_data.get("reason", "He's no good")
            msg = rng.choice(NPC_INITIATIVE_TEMPLATES["jealous"])
            topics.append((0.5, msg.format(
                name=name, other_name=other_name, reason=reason)))
            break  # only one badmouth per conversation

    # -- Favor reminder --
    if hasattr(npc, 'rel'):
        debts = getattr(npc.rel, 'debts', [])
        player_debts = [d for d in debts if "player" in d.lower() or "owe" in d.lower()]
        if player_debts:
            msg = rng.choice(NPC_INITIATIVE_TEMPLATES["favor_reminder"])
            topics.append((0.7, msg.format(name=name, detail=player_debts[0])))

    # -- Gossip from recent memory --
    if hasattr(npc, 'expanded_memory'):
        recent = npc.expanded_memory.get_recent(3)
        for mem in recent:
            age = current_day - mem.day
            if age <= 7 and mem.category in ("witnessed", "event", "told"):
                msg = rng.choice(NPC_INITIATIVE_TEMPLATES["gossip"])
                topics.append((0.4, msg.format(name=name, detail=mem.content)))
                break

    # -- Motivation plea (trust-gated) --
    trust = npc.rel.trust if hasattr(npc, 'rel') else 0
    if trust >= 30:
        motivations = getattr(npc, 'motivations', [])
        if motivations:
            msg = rng.choice(NPC_INITIATIVE_TEMPLATES["motivation_plea"])
            topics.append((0.5, msg.format(name=name, detail=motivations[0])))

    # -- Danger warning from negative memories --
    if hasattr(npc, 'expanded_memory'):
        for mem in npc.expanded_memory.get_recent(5):
            age = current_day - mem.day
            if age <= 14 and mem.emotional_valence < -0.5:
                msg = rng.choice(NPC_INITIATIVE_TEMPLATES["danger_warning"])
                topics.append((0.6, msg.format(
                    name=name, detail=mem.content, direction="out there")))
                break

    # -- Tribal tension warning --
    tribe = getattr(npc, 'tribe', '')
    if tribal and tribe:
        standing = tribal.get_standing(tribe).standing
        if standing < -20:
            msg = rng.choice(NPC_INITIATIVE_TEMPLATES["tribal_tension"])
            topics.append((0.5, msg.format(name=name, tribe=tribe)))

    # Sort by urgency and return top candidates
    topics.sort(key=lambda t: -t[0])
    return topics[:3]


# ============================================================================
#  GREETING SELECTOR — picks greeting based on NPC memory/relationship
# ============================================================================

def select_memory_greeting(npc: "NPCExpanded", player_name: str,
                           current_day: int,
                           rng: random.Random = None) -> str:
    """Pick a greeting informed by NPC's memory and relationship with player."""
    if rng is None:
        rng = random.Random()

    name = npc.name
    rel = getattr(npc, 'rel', None)

    # Check relationship status
    affinity = rel.affinity if rel else 0
    trust = rel.trust if rel else 0
    status = rel.status if rel else "stranger"
    meetings = getattr(rel, 'times_met', 0) if rel else 0

    # Enemy
    if affinity < -40 or status in ("rival", "enemy"):
        pool = MEMORY_GREETINGS["enemy"]
    # Close friend
    elif status in ("close_friend", "married") or affinity > 60:
        pool = MEMORY_GREETINGS["close_friend"]
    # First meeting
    elif meetings <= 1 and status == "stranger":
        pool = MEMORY_GREETINGS["first_meeting"]
    else:
        # Check recent memories for tone
        pool = None
        if hasattr(npc, 'expanded_memory'):
            recent = npc.expanded_memory.get_recent(3)
            for mem in recent:
                age = current_day - mem.day
                if age > 30:
                    continue
                if mem.category == "conversation_summary":
                    if mem.emotional_valence > 0.3:
                        pool = MEMORY_GREETINGS["positive_recent"]
                    elif mem.emotional_valence < -0.3:
                        pool = MEMORY_GREETINGS["negative_recent"]

        # Check debts
        if pool is None and rel:
            debts = getattr(rel, 'debts', [])
            if debts:
                pool = MEMORY_GREETINGS["npc_owes_debt"]

        # Check if player helped NPC (favor owed)
        if pool is None and rel:
            favors = getattr(rel, 'favors_owed_by_npc', 0)
            if favors and favors > 0:
                pool = MEMORY_GREETINGS["helped_npc"]

        # Default to positive/neutral based on affinity
        if pool is None:
            if affinity > 20:
                pool = MEMORY_GREETINGS["positive_recent"]
            else:
                pool = MEMORY_GREETINGS["first_meeting"]

    greeting = rng.choice(pool)
    return greeting.format(name=name, player=player_name)


# ============================================================================
#  NPC-TO-NPC OVERHEARD CONVERSATIONS
# ============================================================================

# Each entry is (speaker_a_line, speaker_b_line) — a 2-line exchange.
# Placeholders: {a} = first speaker name, {b} = second speaker name,
# {target} = someone they're gossiping about, {reason} = opinion reason

# Actionable chatter — references real game mechanics, investigable leads
NPC_CHATTER_ACTIONABLE: List[Tuple[str, str, str]] = [
    # (line_a, line_b, hint_type) — hint_type helps engine tag for investigation
    # Gold leads
    ("{a}: \"Man came through yesterday. Said he pulled a two-ounce nugget out of the east fork.\"",
     "{b}: \"East fork? That ground's supposed to be worked out.\"",
     "gold_hint"),
    ("{a}: \"I been watching the gravel bars after the flood. Color everywhere.\"",
     "{b}: \"Where?\"  {a}: \"North of here. Where the creek bends.\"",
     "gold_hint"),
    ("{a}: \"You ever dig down to bedrock? That's where the real gold sits.\"",
     "{b}: \"Too much work for one man.\"  {a}: \"Not if you find the right crevice.\"",
     "gold_hint"),
    ("{a}: \"Saw flakes in the black sand upstream. Didn't have time to pan proper.\"",
     "{b}: \"Show me where. I'll split what we find.\"",
     "gold_hint"),
    # Danger warnings
    ("{a}: \"There's a grizzly working the creek south of camp. Saw tracks this morning.\"",
     "{b}: \"How big?\"  {a}: \"Big enough I came back.\"",
     "danger"),
    ("{a}: \"Don't go west alone. Two men got robbed on the trail last week.\"",
     "{b}: \"Bandits?\"  {a}: \"Or worse.\"",
     "danger"),
    ("{a}: \"Found a dead man on the south trail. Shot in the back. Pockets turned out.\"",
     "{b}: \"Lord. Did you tell the sheriff?\"  {a}: \"What sheriff?\"",
     "danger"),
    ("{a}: \"The river's rising. Another day of rain and that ford won't be crossable.\"",
     "{b}: \"Better get your supplies across while you can.\"",
     "danger"),
    ("{a}: \"Rattlesnakes thick this time of year. Watch the rocks.\"",
     "{b}: \"Lost a dog to one last summer. Mean country.\"",
     "danger"),
    # Survival tips
    ("{a}: \"You boiling your water?\"",
     "{b}: \"Should I be?\"  {a}: \"Half the camp's got the runs. Boil it.\"",
     "survival"),
    ("{a}: \"Pine needle tea. Keeps the scurvy off.\"",
     "{b}: \"Tastes like turpentine.\"  {a}: \"Better than losing your teeth.\"",
     "survival"),
    ("{a}: \"Cache your extra supplies. Bury 'em deep. Animals will dig shallow.\"",
     "{b}: \"Where do you cache yours?\"  {a}: \"Nice try.\"",
     "survival"),
    ("{a}: \"You can eat cattail root. Tastes like nothing but it fills you up.\"",
     "{b}: \"How do you know what's safe to eat out here?\"  {a}: \"Trial and error. Mostly error.\"",
     "survival"),
    # Trade & economy
    ("{a}: \"Flour's three dollars a pound now. Three dollars!\"",
     "{b}: \"Remember when it was fifty cents? That was six months ago.\"",
     "economy"),
    ("{a}: \"The Chinese are undercutting everybody. Work twice as hard for half the dust.\"",
     "{b}: \"Can't blame a man for working.\"  {a}: \"I can when it lowers my price.\"",
     "economy"),
    ("{a}: \"Heard the merchant's buying beaver pelts at double. Fur market must be up.\"",
     "{b}: \"Or he knows something we don't.\"",
     "economy"),
    # NPC stories / character
    ("{a}: \"I was a schoolteacher back in Ohio. Can you believe that?\"",
     "{b}: \"What happened?\"  {a}: \"Gold fever. Same as everybody.\"",
     "character"),
    ("{a}: \"My wife thinks I'm dead. Might be better that way.\"",
     "{b}: *{b} says nothing for a long moment.*",
     "character"),
    ("{a}: \"I killed a man in Missouri. That's why I came west.\"",
     "{b}: \"You telling me that why?\"  {a}: \"'Cause you asked why I don't sleep.\"",
     "character"),
    ("{a}: \"You ever think about going home?\"",
     "{b}: \"Every day.\"  {a}: \"Me too. But there's nothing to go back to.\"",
     "character"),
    ("{a}: \"I found a vein of quartz with visible gold in it. Real hardrock.\"",
     "{b}: \"Where?\"  {a}: \"Ha. Like I'd tell you.\"",
     "gold_hint"),
    # Location hints
    ("{a}: \"There's an old cabin up the north trail. Roof's half gone but the walls are solid.\"",
     "{b}: \"Anybody living there?\"  {a}: \"Not anymore.\"",
     "location"),
    ("{a}: \"I saw smoke from a Native camp east of here. Looked peaceful.\"",
     "{b}: \"Best leave them be unless you know the tribe.\"",
     "location"),
    ("{a}: \"There's a natural hot spring two valleys over. Good for the bones.\"",
     "{b}: \"And the rattlesnakes that sun on the warm rocks around it.\"",
     "location"),
    # Trapping
    ("{a}: \"Beaver dam upstream. Big one. Must be ten lodges.\"",
     "{b}: \"That's prime trapping. Who's working it?\"  {a}: \"Nobody yet.\"",
     "trapping"),
    ("{a}: \"Winter pelts are worth triple. Wait for the cold.\"",
     "{b}: \"If I live that long.\"",
     "trapping"),
    ("{a}: \"Set your traps in the runs, not the still water. That's where they swim.\"",
     "{b}: \"How deep?\"  {a}: \"Hand's depth below the surface. Weight 'em down.\"",
     "trapping"),
]

NPC_CHATTER_GOSSIP: List[Tuple[str, str]] = [
    ("{a}: \"You know {target}? {reason}.\"",
     "{b}: \"I heard the same. Watch your back around that one.\""),
    ("{a}: \"Did you hear about {target}? {reason}.\"",
     "{b}: \"Doesn't surprise me one bit.\""),
    ("{a}: \"{target}'s been acting strange lately. Looking over his shoulder.\"",
     "{b}: \"Man with something to hide. Mark my words.\""),
    ("{a}: \"I don't trust {target}. {reason}.\"",
     "{b}: \"Me neither. But what can you do.\""),
    ("{a}: \"{target} struck color, they say. Won't tell anybody where.\"",
     "{b}: \"Good for him. I'm still eating dirt.\""),
    ("{a}: \"{target}'s drinking heavy. Every night at the saloon.\"",
     "{b}: \"Seen it before. He's running from something.\""),
    ("{a}: \"Somebody said {target} ain't who he says he is.\"",
     "{b}: \"Out here, who is?\""),
    ("{a}: \"{target}'s wife sent a letter. He won't open it.\"",
     "{b}: \"That's between him and God.\""),
]

NPC_CHATTER_OCCUPATION: Dict[str, List[Tuple[str, str]]] = {
    "Prospector": [
        ("{a}: \"What's the ground like upriver?\"",
         "{b}: \"Sandy. Some color in the pan but nothing to stake on.\""),
        ("{a}: \"You tried the east fork yet?\"",
         "{b}: \"Nah. Heard it's all worked out. But I don't believe everything I hear.\""),
        ("{a}: \"I found a good crevice in the bedrock. Pulled eight dollars in two hours.\"",
         "{b}: \"Show me?\"  {a}: \"You got a bottle of whiskey?\""),
    ],
    "Merchant": [
        ("{a}: \"Supply wagon's late again.\"",
         "{b}: \"Figures. Last one lost a wheel on the pass.\""),
        ("{a}: \"Prices going up or down?\"",
         "{b}: \"Up. Always up. Until everybody leaves, then they crash.\""),
    ],
    "Trapper": [
        ("{a}: \"Beaver still running?\"",
         "{b}: \"Some. But the easy water's trapped out. Gotta go deeper in.\""),
        ("{a}: \"What are pelts going for?\"",
         "{b}: \"Less every year. Silk hats replacing beaver felt, they say.\""),
        ("{a}: \"You skin your own or have somebody do it?\"",
         "{b}: \"Do it myself. Can't trust anybody else not to nick the hide.\""),
    ],
    "Doctor": [
        ("{a}: \"Third case of dysentery this week.\"",
         "{b}: \"They're drinking from the same stream they're digging in. What do they expect.\""),
    ],
    "Preacher": [
        ("{a}: \"There's wickedness in this camp. I can feel it.\"",
         "{b}: \"There's wickedness everywhere, reverend.\""),
    ],
}

NPC_CHATTER_UNTRANSLATED: Dict[str, List[str]] = {
    "chinese": [
        "*Two Chinese miners talk rapidly in Cantonese. You catch nothing.*",
        "*You overhear Cantonese — animated, fast. Something about the river.*",
        "*The Chinese miners argue quietly. One points upstream.*",
    ],
    "mexican": [
        "*Two men speak Spanish nearby. Laughter. Something about a horse.*",
        "*You hear rapid Spanish. One man gestures south. The other nods.*",
        "*Spanish voices drift over — low, serious. You can't follow it.*",
    ],
    "french_canadian": [
        "*French drifts over from two voyageurs. Something about pelts.*",
        "*You hear French — \"tabernac\" followed by laughter.*",
        "*Two men speak rapid French. One mimes paddling a canoe.*",
    ],
    "native_american": [
        "*Two Native men speak in their own tongue. They glance your way.*",
        "*You hear a conversation in a language you don't understand. Calm and measured.*",
        "*Native voices nearby — rhythmic, unhurried. The words mean nothing to you.*",
    ],
}


def generate_overheard(npc_a: "NPCExpanded", npc_b: "NPCExpanded",
                       player_languages: Dict[str, str],
                       tribal=None,
                       rng: random.Random = None,
                       ) -> Optional[List[str]]:
    """
    Generate an overheard NPC-to-NPC conversation exchange.
    Returns list of 1-3 message strings, or None if no conversation.
    Language barrier applies — if both NPCs share a non-English language
    the player doesn't know, show untranslated.
    """
    if rng is None:
        rng = random.Random()

    a_name = npc_a.name
    b_name = npc_b.name
    a_eth = getattr(npc_a, 'ethnicity', 'american')
    b_eth = getattr(npc_b, 'ethnicity', 'american')
    a_tribe = getattr(npc_a, 'tribe', '')
    b_tribe = getattr(npc_b, 'tribe', '')

    # Check if both NPCs share a non-English language the player can't understand
    shared_foreign = None
    if a_tribe and a_tribe == b_tribe:
        # Same tribe — speak tribal language
        lang_lvl = "none"
        if tribal:
            lang_lvl = tribal.get_language_level(a_tribe)
        if lang_lvl in ("none", "sign"):
            shared_foreign = "native_american"
    elif a_eth == b_eth and a_eth in ("chinese", "mexican", "french_canadian"):
        player_lvl = player_languages.get(
            {"chinese": "chinese", "mexican": "spanish",
             "french_canadian": "french"}.get(a_eth, ""), "none")
        if player_lvl in ("none", "sign"):
            shared_foreign = a_eth

    if shared_foreign:
        pool = NPC_CHATTER_UNTRANSLATED.get(shared_foreign, [])
        if pool:
            return [rng.choice(pool)]
        return None

    # Both speak English (or player understands) — generate dialogue
    lines = []

    # 35% chance of gossip about a third party (from real opinions)
    if rng.random() < 0.35:
        opinions_a = getattr(npc_a, 'npc_opinions', {})
        opinions_b = getattr(npc_b, 'npc_opinions', {})
        all_targets = {}
        for oid, od in opinions_a.items():
            all_targets[oid] = od
        for oid, od in opinions_b.items():
            if oid not in all_targets:
                all_targets[oid] = od
        if all_targets:
            target_id, target_data = rng.choice(list(all_targets.items()))
            target_name = target_data.get("name", "someone")
            reason = target_data.get("reason", "Something about him bothers me")
            template = rng.choice(NPC_CHATTER_GOSSIP)
            lines.append(template[0].format(
                a=a_name, b=b_name, target=target_name, reason=reason))
            lines.append(template[1].format(
                a=a_name, b=b_name, target=target_name, reason=reason))
            return lines

    # 25% chance of occupation-specific chatter
    if rng.random() < 0.38:
        for occ in (npc_a.occupation, npc_b.occupation):
            if occ in NPC_CHATTER_OCCUPATION:
                template = rng.choice(NPC_CHATTER_OCCUPATION[occ])
                lines.append(template[0].format(a=a_name, b=b_name))
                lines.append(template[1].format(a=a_name, b=b_name))
                return lines

    # 60%+ — actionable chatter (gold hints, dangers, tips, stories)
    entry = rng.choice(NPC_CHATTER_ACTIONABLE)
    line_a, line_b, hint_type = entry
    lines.append(line_a.format(a=a_name, b=b_name))
    lines.append(line_b.format(a=a_name, b=b_name))
    return lines
