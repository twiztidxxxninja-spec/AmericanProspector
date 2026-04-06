"""
src/combat.py

Turn-based combat resolution for American Prospector.
Handles player↔NPC melee, ranged, and environmental attacks.
NPC morale, surrender, and flight. Witness reactions.

Resolution formula (from design doc):
  d20 + floor(skill/2) + floor(governing_attribute/3)  vs  defense threshold
"""

import random
from dataclasses import dataclass
from typing import Optional, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.player import Player
    from src.npc import NPC
    from src.items import Item


# ── Helpers ────────────────────────────────────────────────────────────────

def _d20() -> int:
    return random.randint(1, 20)

def _skill_bonus(v: int) -> int:
    return v // 2

def _attr_bonus(v: int) -> int:
    return v // 3


def _dismember_msg(part_label: str, weapon: str, npc_name: str,
                   gender: str = "M") -> str:
    """Generate a graphic dismemberment message when a body part is destroyed."""
    is_firearm = any(w in weapon.lower() for w in
                     ("rifle", "pistol", "shotgun", "revolver", "musket",
                      "carbine", "derringer", "gun"))
    is_shotgun = "shotgun" in weapon.lower()
    is_blade = any(w in weapon.lower() for w in
                   ("knife", "axe", "machete", "sword", "hatchet", "bowie"))
    is_male = gender in ("M", "m", "male", "Male")

    # Groin-specific messages
    if "groin" in part_label:
        if is_male:
            if is_shotgun:
                return (f"{npc_name}'s dick is obliterated by the blast. "
                        f"What's left sprays across the dirt.")
            if is_firearm:
                msgs = [
                    f"{npc_name}'s dick is shot clean off. "
                    f"The severed part tumbles through the air and lands in the dust.",
                    f"The bullet tears {npc_name}'s dick off. "
                    f"It hits the ground with a wet slap.",
                    f"{npc_name}'s dick explodes in a spray of blood. "
                    f"He looks down. He screams.",
                ]
                return random.choice(msgs)
            if is_blade:
                return (f"The blade cleaves through {npc_name}'s groin. "
                        f"His dick falls to the ground. "
                        f"The screaming is inhuman.")
            return (f"{npc_name}'s dick is destroyed by the impact. "
                    f"He doubles over, shrieking.")
        else:
            if is_firearm:
                return (f"The shot tears through {npc_name}'s groin. "
                        f"She collapses, screaming.")
            return (f"{npc_name}'s groin is destroyed. "
                    f"She goes down, shrieking.")

    # Hand messages
    if "hand" in part_label:
        side = "left" if "left" in part_label else "right"
        if is_firearm:
            return (f"{npc_name}'s {side} hand disintegrates. "
                    f"Fingers fly in different directions.")
        if is_blade:
            return (f"The {side} hand separates at the wrist and "
                    f"drops to the ground, fingers still twitching.")
        return f"{npc_name}'s {side} hand is destroyed."

    # Arm messages
    if "arm" in part_label:
        side = "left" if "left" in part_label else "right"
        if is_shotgun:
            return (f"{npc_name}'s {side} arm is blown off at the elbow. "
                    f"It cartwheels through the air trailing blood.")
        if is_firearm:
            return (f"The bone in {npc_name}'s {side} arm shatters. "
                    f"The forearm hangs by a strip of flesh, useless.")
        return (f"{npc_name}'s {side} arm is mangled beyond use. "
                f"It dangles at a wrong angle.")

    # Leg messages
    if "leg" in part_label or "thigh" in part_label:
        side = "left" if "left" in part_label else "right"
        if is_shotgun:
            return (f"The shotgun blast takes {npc_name}'s {side} leg "
                    f"clean off below the knee. He goes down hard.")
        if is_firearm:
            return (f"{npc_name}'s {side} leg buckles — the bone is "
                    f"shattered. A shard of femur pokes through the skin.")
        return (f"{npc_name}'s {side} leg is destroyed. "
                f"He collapses, clutching the stump.")

    # Generic
    if is_firearm:
        return (f"{npc_name}'s {part_label} is blown apart. "
                f"Chunks of flesh scatter.")
    return f"{npc_name}'s {part_label} is destroyed."


def _dismember_msg_player(part_label: str, weapon: str) -> str:
    """Dismemberment message when the PLAYER loses a body part."""
    is_firearm = any(w in weapon.lower() for w in
                     ("rifle", "pistol", "shotgun", "revolver", "musket",
                      "carbine", "derringer", "gun"))
    is_shotgun = "shotgun" in weapon.lower()

    if "groin" in part_label:
        if is_shotgun:
            return ("Your dick is obliterated by the shotgun blast. "
                    "The shredded remains paint the dirt behind you.")
        if is_firearm:
            msgs = [
                "Your dick is shot off. You watch it arc through the air "
                "and land in the dust three feet away.",
                "The bullet tears your dick clean off. It hits the ground "
                "with a wet thud. The pain hasn't hit yet. It will.",
                "Your manhood explodes in a spray of blood. "
                "You look down. You scream.",
            ]
            return random.choice(msgs)
        return ("A devastating blow to your groin. Your dick is gone. "
                "The shock is total.")

    if "hand" in part_label:
        side = "left" if "left" in part_label else "right"
        if is_firearm:
            return (f"Your {side} hand disintegrates. Fingers scatter. "
                    f"Where your hand was there's a ragged stump spraying red.")
        return f"Your {side} hand is severed. It falls to the ground."

    if "arm" in part_label:
        side = "left" if "left" in part_label else "right"
        if is_shotgun:
            return (f"Your {side} arm is blown off at the elbow. "
                    f"It spins through the air trailing a ribbon of blood.")
        return (f"Your {side} arm is shattered beyond saving. "
                f"It hangs by a strip of skin.")

    if "leg" in part_label or "thigh" in part_label:
        side = "left" if "left" in part_label else "right"
        return (f"Your {side} leg gives way — the bone is gone. "
                f"You go down screaming.")

    return f"Your {part_label} is destroyed."


# ── Result dataclass ───────────────────────────────────────────────────────

@dataclass
class CombatEvent:
    attacker: str
    defender: str
    weapon_name: str
    hit: bool
    damage: int
    message: str
    killed: bool = False
    defender_fled: bool = False
    defender_surrendered: bool = False
    stray_bullet: bool = False   # missed shot continues past target
    player_captured: bool = False  # tribal capture instead of death


# ── Player attacks NPC ─────────────────────────────────────────────────────

# Aimed shot body part targets — (label, hit_penalty, damage_mult, special)
AIMED_SHOTS = [
    ("Center mass (normal)",  0, 1.0, None),
    ("Head — lethal",        -6, 2.0, "head"),
    ("Legs — slow them",     -3, 0.7, "legs"),
    ("Arms — disarm",        -4, 0.6, "arms"),
    ("Torso — heavy bleed",  -2, 1.2, "torso"),
    ("Groin — cripple",      -5, 1.0, "groin"),
]


def player_attack_npc(player: "Player", npc: "NPC",
                      weapon: Optional["Item"] = None,
                      distance: int = 1,
                      aimed_part: int = 0,
                      accuracy_bonus: int = 0,
                      target_cover: int = 0,
                      weather: str = "clear") -> CombatEvent:
    """Resolve one attack from player onto npc. Mutates npc state.
    aimed_part: index into AIMED_SHOTS (0 = center mass / no aim).
    accuracy_bonus: extra roll bonus from careful aim (+5 typical).
    target_cover: 0=none, 1=partial (-4), 2=full (can't hit)."""

    # --- Weapon selection ---
    if weapon and weapon.weapon_type == "firearm":
        # Check ammo — "loaded" is now an int (rounds loaded) or bool for compat
        loaded = weapon.extra.get("loaded", 0)
        if isinstance(loaded, bool):
            loaded = 1 if loaded else 0
        if loaded <= 0:
            return CombatEvent(
                attacker=player.name, defender=npc.name,
                weapon_name=weapon.name, hit=False, damage=0,
                message=f"*click* — the {weapon.name} isn't loaded. "
                        f"Reload with [A]ctions.",
            )
        # Flintlock misfire check
        if getattr(weapon, 'extra', {}).get('ignition') == 'flintlock':
            import random as _mf_rng
            misfire_chance = {"clear": 0.05, "overcast": 0.05, "rain": 0.15,
                              "snow": 0.20, "blizzard": 0.25, "fog": 0.08,
                              "thunderstorm": 0.20, "hot": 0.05, "cold": 0.07,
                              }.get(weather, 0.05)
            if _mf_rng.random() < misfire_chance:
                # Misfire! Shot wasted, no damage
                if weapon.extra.get("loaded", 0) > 0:
                    weapon.extra["loaded"] -= 1
                return CombatEvent(
                    attacker=player.name, defender=npc.name,
                    weapon_name=weapon.name, hit=False, damage=0,
                    message=f"{player.name}'s flintlock misfires! The powder flashes in the pan but the shot doesn't fire.",
                )

        weapon.extra["loaded"] = loaded - 1     # expend one round
        skill_val  = player.skills.get("firearms", 0)
        attr_val   = player.attributes.get("agility", 10)
        dmg_lo, dmg_hi = weapon.damage_min, weapon.damage_max
        weapon_name = weapon.name
        str_bonus = 0

        # One-handed penalty for firearms
        # Rifles need both hands; pistols get a slight penalty one-handed
        is_pistol = any(w in weapon.name.lower()
                        for w in ("pistol", "revolver", "derringer", "dragoon"))
        other_hand_full = False
        if player.right_hand and player.right_hand.lower() == weapon.name.lower():
            other_hand_full = player.left_hand is not None
        elif player.left_hand and player.left_hand.lower() == weapon.name.lower():
            other_hand_full = player.right_hand is not None

        if other_hand_full:
            if is_pistol:
                skill_val = max(0, skill_val - 1)   # slight penalty
                dmg_hi = max(dmg_lo, dmg_hi - 2)
            else:
                # Rifle/shotgun one-handed = massive penalty
                skill_val = max(0, skill_val - 4)
                dmg_lo = max(1, dmg_lo // 2)
                dmg_hi = max(dmg_lo, dmg_hi // 2)

    elif weapon and weapon.weapon_type == "melee":
        skill_val  = player.skills.get("survival", 0)
        attr_val   = player.attributes.get("strength", 10)
        dmg_lo, dmg_hi = weapon.damage_min, weapon.damage_max
        weapon_name = weapon.name
        str_bonus = (player.attributes.get("strength", 10) - 10) // 3

    else:
        # Unarmed — uses survival skill, not zero
        skill_val  = player.skills.get("survival", 0)
        attr_val   = player.attributes.get("strength", 10)
        dmg_lo, dmg_hi = 1, 4
        weapon_name = "fists"
        str_bonus = (player.attributes.get("strength", 10) - 10) // 3

    # --- Hit roll vs NPC dodge ---
    npc_defense = 8 + _attr_bonus(npc.attributes.get("agility", 10))
    roll = _d20() + _skill_bonus(skill_val) + _attr_bonus(attr_val) + accuracy_bonus
    # Drunk penalty — impaired aim and coordination
    roll -= player.survival.drunk_aim_penalty
    # Range penalty: at 5ft/tile, firearms accurate to ~40 tiles (200ft),
    # penalty kicks in beyond that. Melee penalized beyond adjacent (1 tile).
    if weapon and weapon.weapon_type == "firearm":
        if distance > 40:
            roll -= (distance - 40) // 5   # -1 per 25ft beyond 200ft
    elif distance > 1:
        # Melee / unarmed — heavy penalty beyond adjacent
        roll -= (distance - 1) * 3

    # Aimed shot penalty
    aim = AIMED_SHOTS[aimed_part] if 0 <= aimed_part < len(AIMED_SHOTS) else AIMED_SHOTS[0]
    aim_label, aim_penalty, aim_dmg_mult, aim_special = aim
    roll += aim_penalty  # negative = harder to hit

    # Cover penalty — target behind cover is harder to hit
    # partial cover = -4, full cover = can't be hit by ranged
    if target_cover >= 2 and distance > 1:
        return CombatEvent(
            attacker=player.name, defender=npc.name,
            weapon_name=weapon_name, hit=False, damage=0,
            message=f"{npc.name} is behind full cover. Can't get a clean shot.",
        )
    if target_cover == 1:
        roll -= 4

    if roll < npc_defense:
        miss_extra = f" (aimed: {aim_label})" if aimed_part > 0 else ""
        is_firearm = weapon and weapon.weapon_type == "firearm"
        return CombatEvent(
            attacker=player.name, defender=npc.name,
            weapon_name=weapon_name, hit=False, damage=0,
            message=_miss_msg(player.name, npc.name, weapon_name) + miss_extra,
            stray_bullet=is_firearm,
        )

    # --- Damage ---
    dmg = max(1, int((random.randint(dmg_lo, dmg_hi) + str_bonus) * aim_dmg_mult))

    # Aimed shot specials
    _orig_agi = getattr(npc, '_base_agility', npc.attributes.get("agility", 10))
    _orig_str = getattr(npc, '_base_strength', npc.attributes.get("strength", 10))
    if not hasattr(npc, '_base_agility'):
        npc._base_agility = _orig_agi
    if not hasattr(npc, '_base_strength'):
        npc._base_strength = _orig_str

    if aim_special == "head" and dmg >= 5:
        # Headshot: instant kill only on heavy hits (rifle/shotgun damage)
        # Light damage headshots wound badly but don't always kill
        kill_chance = 0.3 if dmg < 15 else 0.5 if dmg < 25 else 0.7
        if random.random() < kill_chance:
            dmg = max(dmg, int(npc.health) + 10)
    elif aim_special == "legs":
        # Leg shot: cripple movement, capped at -6 from base
        npc.attributes["agility"] = max(
            max(1, _orig_agi - 6),
            npc.attributes.get("agility", 10) - 4)
    elif aim_special == "arms":
        # Arm shot: reduce damage, capped at -6 from base
        npc.attributes["strength"] = max(
            max(1, _orig_str - 6),
            npc.attributes.get("strength", 10) - 4)
    elif aim_special == "groin":
        # Groin shot: cripple, capped at -6 from base
        npc.attributes["agility"] = max(
            max(1, _orig_agi - 6),
            npc.attributes.get("agility", 10) - 5)

    # Map aim_special to target body part for wound system
    _AIM_TO_PART = {
        "head": "head", "torso": "chest", "legs": "r_thigh",
        "arms": "r_upper_arm", "groin": "groin",
    }
    wound_target = _AIM_TO_PART.get(aim_special, "chest")  # center mass → chest

    # Apply wound through the wound system (creates DetailedWound if available)
    wound = npc.wounds.apply_hit(dmg, _weapon_damage_type(weapon_name),
                                 target_part=wound_target,
                                 weapon_key=_weapon_key(weapon_name))
    # Body part HP caps — extremities can only absorb so much before the
    # damage "overflows" to the body. Excess becomes bleed damage, not HP loss.
    # A hand can't absorb a .50 cal — it's destroyed, but you're still alive.
    # The bleeding from the stump is what kills you.
    from src.health_system import PART_HP, PART_DATA, BP
    part_hit = wound.part if hasattr(wound, 'part') else ""
    part_cap = PART_HP.get(part_hit, 100)
    hp_dmg = min(dmg, part_cap)
    npc.health = max(0.0, npc.health - hp_dmg)
    _check_npc_morale(npc)

    # Dismemberment check — damage exceeds part HP cap by 50%+
    dismember_msg = ""
    part_info = PART_DATA.get(part_hit, {})
    part_label = part_info.get("label", part_hit).lower()
    is_vital = part_info.get("vital", True)
    if dmg > part_cap * 1.5 and not is_vital and part_hit:
        npc.wounds.part_state[part_hit] = "disabled"
        npc_gender = getattr(npc, "gender", "M")
        dismember_msg = _dismember_msg(part_label, weapon_name, npc.name, npc_gender)

    killed      = npc.combat_state == "dead"
    fled        = npc.combat_state == "fleeing"
    surrendered = npc.combat_state == "surrendered"

    wound_desc = f" ({wound.description})" if hasattr(wound, "description") else ""
    if killed:
        msg = _kill_msg(player.name, npc.name, weapon_name,
                        part=part_label, wound_desc=wound_desc)
    else:
        msg = _hit_msg(player.name, npc.name, weapon_name, dmg, npc.health)
        msg += wound_desc
        if dismember_msg:
            msg += f" {dismember_msg}"
        if fled:
            msg += f" {npc.name} breaks and runs."
        elif surrendered:
            msg += f' {npc.name} throws up his hands. "Enough! I give!"'

    return CombatEvent(
        attacker=player.name, defender=npc.name,
        weapon_name=weapon_name, hit=True, damage=dmg,
        killed=killed, defender_fled=fled, defender_surrendered=surrendered,
        message=msg,
    )


# ── NPC attacks player ─────────────────────────────────────────────────────

def npc_attack_player(npc: "NPC", player: "Player",
                      player_cover: int = 0) -> CombatEvent:
    """Resolve one NPC attack onto the player. Mutates player.survival.
    player_cover: 0=none, 1=partial (-4 to NPC roll), 2=full (auto-miss)."""
    from src.player import Stance

    # Full cover = can't be hit at range
    dist = max(abs(npc.local_x - player.local_x), abs(npc.local_y - player.local_y))
    if player_cover >= 2 and dist > 1:
        return CombatEvent(
            attacker=npc.name, defender=player.name,
            weapon_name="", hit=False, damage=0,
            message=f"{npc.name} fires but you're behind cover.",
        )

    weapon_name, dmg_lo, dmg_hi, skill_name = _npc_weapon_profile(npc)
    skill_val = npc.skills.get(skill_name, 0)

    # Flintlock misfire check for NPC weapons
    npc_weapon_item = getattr(npc, 'get_weapon', lambda: None)()
    if npc_weapon_item and getattr(npc_weapon_item, 'extra', {}).get('ignition') == 'flintlock':
        import random as _mf_rng
        misfire_chance = 0.05  # 5% base
        if _mf_rng.random() < misfire_chance:
            # Misfire! Shot wasted, no damage
            if npc_weapon_item.extra.get("loaded", 0) > 0:
                npc_weapon_item.extra["loaded"] -= 1
            return CombatEvent(
                attacker=npc.name, defender=player.name,
                weapon_name=weapon_name, hit=False, damage=0,
                message=f"{npc.name}'s flintlock misfires! The powder flashes in the pan but the shot doesn't fire.",
            )

    # Player defense: agility + stance + cover
    stance_bonus = {
        Stance.STANDING: 0, Stance.CROUCHED: 2,
        Stance.PRONE_DOWN: 4, Stance.PRONE_UP: 2,
    }
    cover_bonus = {0: 0, 1: 4, 2: 99}  # partial cover = +4 defense
    player_defense = (8
                      + _attr_bonus(player.attributes.get("agility", 10))
                      + stance_bonus.get(player.stance, 0)
                      + cover_bonus.get(player_cover, 0))

    roll = _d20() + _skill_bonus(skill_val) + _attr_bonus(npc.attributes.get("agility", 10))

    if roll < player_defense:
        return CombatEvent(
            attacker=npc.name, defender=player.name,
            weapon_name=weapon_name, hit=False, damage=0,
            message=_miss_msg(npc.name, "you", weapon_name),
        )

    raw_dmg = random.randint(dmg_lo, dmg_hi)

    # Clothing reduces damage
    dmg = raw_dmg
    clothing_msg = ""
    worn = getattr(player, "worn", None)
    if worn:
        try:
            from src.clothing import damage_after_clothing
            # Pick a random body part for hit location
            # Pick a random body part weighted toward center mass
            from src.health_system import BP, PART_DATA, ALL_BODY_PARTS
            hit_parts = list(ALL_BODY_PARTS)
            hit_weights = [PART_DATA[p]["hit_w"] for p in hit_parts]
            hit_part = random.choices(hit_parts, weights=hit_weights, k=1)[0]
            # Get clothing slot for that body part
            clothing_slot = PART_DATA[hit_part].get("clothing", "torso")
            dmg, clothing_msg = damage_after_clothing(raw_dmg, clothing_slot, worn)
        except ImportError:
            hit_part = None

    # Apply wound through the wound system (pass actual body part)
    wound = player.wounds.apply_hit(dmg, _weapon_damage_type(weapon_name),
                                      target_part=hit_part if worn else None,
                                      weapon_key=_weapon_key(weapon_name),
                                      worn_equipment=worn)
    player.survival.health = max(0.0, player.survival.health - dmg)
    killed = player.survival.health <= 0 or not player.wounds.alive

    wound_desc = ""
    if hasattr(wound, "description"):
        wound_desc = f" {wound.description}."
        if hasattr(wound, "bleed_level") and wound.is_bleeding:
            wound_desc += f" Bleeding: {wound.bleed_level}."

    # Dismemberment check for player
    dismember_msg = ""
    part_hit_p = wound.part if hasattr(wound, 'part') else ""
    from src.health_system import PART_HP as _PHP
    p_cap = _PHP.get(part_hit_p, 100)
    p_info = PART_DATA.get(part_hit_p, {})
    p_label = p_info.get("label", part_hit_p).lower()
    p_vital = p_info.get("vital", True)
    if dmg > p_cap * 1.5 and not p_vital and part_hit_p:
        player.wounds.part_state[part_hit_p] = "disabled"
        dismember_msg = _dismember_msg_player(p_label, weapon_name)

    # Tribal capture — some tribes capture instead of killing
    captured = False
    if killed:
        tribe = getattr(npc, 'tribe', '')
        if tribe:
            # Look up tribe's actual temperament from territory definitions
            from src.tribal_system import TRIBAL_TERRITORIES
            _terr = TRIBAL_TERRITORIES.get(tribe)
            temperament = _terr.temperament if _terr else 'aggressive'
            import random as _cap_rng
            capture_chance = 0.8 if temperament in ('cautious', 'welcoming', 'neutral') else 0.4
            if _cap_rng.random() < capture_chance:
                captured = True
                killed = False
                player.survival.health = max(5.0, player.survival.health)

    if captured:
        msg = (f"{npc.name} strikes you down. Everything goes dark. "
               f"When you wake, your hands are bound.")
    elif killed:
        msg = (f"{npc.name} drives the {weapon_name} home. "
               f"You collapse. Everything goes dark.")
    else:
        msg = _hit_msg(npc.name, "you", weapon_name, int(dmg), player.survival.health)
        if clothing_msg:
            msg += f" {clothing_msg}"
        msg += wound_desc
        if dismember_msg:
            msg += f" {dismember_msg}"

    return CombatEvent(
        attacker=npc.name, defender=player.name,
        weapon_name=weapon_name, hit=True, damage=int(dmg),
        killed=killed, message=msg,
        player_captured=captured,
    )


# ── Environmental / explosive damage ──────────────────────────────────────

def apply_blast_damage(targets: list, damage: int,
                        player: "Player") -> List[str]:
    """
    Apply explosive/environmental damage to a list of NPCs and/or player.
    targets: list of NPC objects (player handled separately via damage param).
    Returns list of result messages.
    """
    msgs = []
    for npc in targets:
        npc.health = max(0.0, npc.health - damage)
        _check_npc_morale(npc)
        if npc.combat_state == "dead":
            msgs.append(_kill_msg("The blast", npc.name, ""))
        else:
            msgs.append(_hit_msg("The blast", npc.name, "", damage, npc.health))
    return msgs


# ── Witness reactions ──────────────────────────────────────────────────────

def witness_reactions(witnesses: list, attacker_name: str,
                      victim_name: str, killed: bool,
                      current_day: int = 0) -> List[str]:
    """
    Bystanders react to observed violence based on personality.
    Mutates witness NPC states and memories. Returns reaction messages.

    Personality-driven responses:
    - Brave/hot-tempered/law NPCs → go hostile (confront the killer)
    - Nervous/cowardly/mild → flee
    - Cruel/psychopathic → watch with interest, minor respect gain
    - Most others → flee if killed, tense standoff if just a fight
    """
    msgs = []

    for npc in witnesses:
        if not npc.present or npc.name in (attacker_name, victim_name):
            continue
        if npc.combat_state != "neutral":
            continue

        traits = set(getattr(npc, 'traits', []))
        is_law = getattr(npc, 'occupation', '') in (
            "Sheriff", "Marshal", "Deputy", "Ranger", "Soldier")

        # Relationship impact
        rel_hit = -35 if killed else -15
        npc.adjust_relationship(rel_hit)

        # Store the memory
        if hasattr(npc, 'expanded_memory'):
            event_desc = (f"Saw {attacker_name} kill {victim_name}."
                          if killed else
                          f"Saw {attacker_name} attack {victim_name}.")
            npc.expanded_memory.add(
                content=event_desc,
                day=current_day,
                significance=0.9 if killed else 0.7,
                valence=-0.8 if killed else -0.4,
                category="witnessed_violence",
            )

        # Decide reaction based on personality
        # 1. Law enforcement always confronts
        if is_law:
            npc.combat_state = "hostile"
            if killed:
                msgs.append(
                    f'{npc.name} draws his weapon. "You\'re under arrest!"')
            else:
                msgs.append(
                    f'{npc.name} steps forward. "Break it up. Now."')
            continue

        # 2. Brave / hot-tempered / vindictive → confront
        confronters = {"brave", "hot-tempered", "utterly fearless",
                       "vindictive", "berserker", "stubborn"}
        if traits & confronters:
            npc.combat_state = "hostile"
            if killed:
                msgs.append(
                    f'{npc.name} goes for his weapon. "You murderin\' bastard!"')
            else:
                msgs.append(
                    f'{npc.name} shoves forward. "Hey! Back off!"')
            continue

        # 3. Friend of the victim → confront (if they know them)
        knows_victim = (hasattr(npc, 'expanded_memory') and
                        npc.expanded_memory.knows_about(victim_name))
        if knows_victim:
                npc.combat_state = "hostile"
                msgs.append(
                    f'{npc.name} snarls. "{victim_name} was a friend of mine."')
                continue

        # 4. Cruel / psychopathic → watch with dark interest
        dark_traits = {"cruel", "psychopathic", "sadistic"}
        if traits & dark_traits:
            if hasattr(npc, 'rel'):
                npc.rel.adjust(respect=5, fear=10)
            msgs.append(
                f"*{npc.name} watches with cold interest, unmoved.*")
            continue

        # 5. Nervous / cowardly / mild → flee
        flee_traits = {"nervous", "cowardly", "mild", "cautious",
                       "reserved", "sentimental", "timid"}
        if traits & flee_traits or killed:
            npc.combat_state = "fleeing"
            if killed:
                msgs.append(f"{npc.name} turns and runs, terrified.")
            else:
                msgs.append(f"{npc.name} backs away, hands up.")
            continue

        # 6. Default — tense standoff (not hostile, not fleeing)
        if hasattr(npc, 'rel'):
            npc.rel.adjust(fear=15)
        msgs.append(f"{npc.name} freezes, watching you warily.")

    return msgs


# ── NPC morale ─────────────────────────────────────────────────────────────

def _check_npc_morale(npc: "NPC"):
    """Update NPC combat_state from health. Call after applying damage."""
    if npc.health <= 0:
        npc.health   = 0
        npc.alive    = False
        npc.present  = True   # keep present so body can be butchered/looted
        npc.combat_state = "dead"
        return

    pct = npc.health / getattr(npc.wounds, 'max_blood', 100.0)

    if pct <= 0.12:
        npc.combat_state = "surrendered" if "brave" in npc.traits else "fleeing"
    elif pct <= 0.30:
        if "coward" in npc.traits or "nervous" in npc.traits:
            npc.combat_state = "fleeing"
        elif random.random() < 0.45:
            npc.combat_state = "fleeing"
        # else stays hostile — set by engine when aggro'd


# ── NPC-vs-NPC combat (battlefield group fighting) ────────────────────────

def npc_attack_npc(attacker: "NPC", defender: "NPC") -> Optional[CombatEvent]:
    """Resolve one NPC attacking another NPC. Used during battles.
    NPCs must reload — they track ammo. Slightly less accurate than player.
    Returns None if NPC is reloading this round."""
    weapon_name, dmg_lo, dmg_hi, skill_name = _npc_weapon_profile(attacker)
    skill_val = attacker.skills.get(skill_name, 0)

    # ── Reload check — NPCs must reload like the player ──────────
    # Track loaded state on NPC. Flintlocks = 1 shot then ~30 sec reload.
    weapon_item = getattr(attacker, 'get_weapon', lambda: None)()
    if weapon_item and getattr(weapon_item, 'weapon_type', '') == "firearm":
        loaded = weapon_item.extra.get("loaded", 0)
        if loaded <= 0:
            # Reloading — NPC spends this round reloading instead of firing
            # NPCs reload slower than players (fumble chance)
            reload_roll = random.random()
            if reload_roll < 0.15:
                # Fumble — dropped ball, spilled powder, misfire
                return CombatEvent(
                    attacker=attacker.name, defender=defender.name,
                    weapon_name=weapon_name, hit=False, damage=0,
                    message=f"{attacker.name} fumbles the reload.",
                )
            cap = weapon_item.extra.get("capacity", 1)
            weapon_item.extra["loaded"] = cap
            return None  # spent the round reloading, no attack
        else:
            weapon_item.extra["loaded"] = loaded - 1

    # ── NPC accuracy penalty — slightly worse than player ────────
    # NPCs are trained but not as precise under stress
    npc_accuracy_penalty = -2  # flat penalty vs player baseline

    # Defense
    defender_defense = 8 + _attr_bonus(defender.attributes.get("agility", 10))
    dist = max(abs(attacker.local_x - defender.local_x),
               abs(attacker.local_y - defender.local_y))

    # Roll — slightly worse than player
    roll = _d20() + _skill_bonus(skill_val) + \
           _attr_bonus(attacker.attributes.get("agility", 10)) + \
           npc_accuracy_penalty

    if dist > 1 and not _is_ranged(weapon_name):
        roll -= (dist - 1) * 3

    if roll < defender_defense:
        return CombatEvent(
            attacker=attacker.name, defender=defender.name,
            weapon_name=weapon_name, hit=False, damage=0,
            message=f"{attacker.name} fires at {defender.name} — misses.",
        )

    # Damage
    dmg = max(1, random.randint(dmg_lo, dmg_hi))

    # Apply damage
    defender.health = max(0.0, defender.health - dmg)
    _check_npc_morale(defender)

    killed = defender.combat_state == "dead"
    fled = defender.combat_state == "fleeing"

    if killed:
        msg = f"{attacker.name} shoots {defender.name}. {defender.name} drops."
    elif fled:
        msg = (f"{attacker.name} hits {defender.name}. "
               f"{defender.name} breaks and runs.")
    else:
        msg = f"{attacker.name} hits {defender.name}."

    return CombatEvent(
        attacker=attacker.name, defender=defender.name,
        weapon_name=weapon_name, hit=True, damage=dmg,
        killed=killed, defender_fled=fled,
        message=msg,
    )


# ── NPC weapon profiles ────────────────────────────────────────────────────

def _weapon_key(weapon_name: str) -> str:
    """Map weapon display name to WEAPON_WOUND_MAP key for lodged objects."""
    w = weapon_name.lower()
    if "rifle" in w: return "rifle"
    if "revolver" in w or "pistol" in w: return "revolver"
    if "shotgun" in w: return "shotgun"
    if "bowie" in w: return "bowie_knife"
    if "knife" in w: return "knife"
    if "pickaxe" in w: return "pickaxe"
    if "hatchet" in w or "axe" in w: return "hatchet"
    if "hammer" in w: return "hammer"
    if "arrow" in w: return "arrow"
    return ""


def _weapon_damage_type(weapon_name: str) -> str:
    """Infer damage type from weapon name for the wound system."""
    w = weapon_name.lower()
    if any(k in w for k in ("rifle", "revolver", "pistol", "shotgun", "gun")):
        try:
            from src.health_system import DmgType
            return DmgType.GUNSHOT
        except ImportError:
            return "piercing"
    if any(k in w for k in ("knife", "blade", "axe", "hatchet")):
        try:
            from src.health_system import DmgType
            return DmgType.SLASH
        except ImportError:
            return "edged"
    try:
        from src.health_system import DmgType
        return DmgType.BLUNT
    except ImportError:
        return "blunt"


def _npc_weapon_profile(npc: "NPC") -> Tuple[str, int, int, str]:
    """Return (weapon_name, dmg_min, dmg_max, governing_skill)."""
    if getattr(npc, '_disarmed', False):
        return "fists", 1, 5, "survival"

    # Check actual inventory for a real weapon item
    weapon = getattr(npc, 'get_weapon', lambda: None)()
    if weapon is not None:
        wtype = getattr(weapon, 'weapon_type', '')
        skill = "firearms" if wtype == "firearm" else "survival"
        return (weapon.name, weapon.damage_min or 3, weapon.damage_max or 8, skill)

    # Fallback: occupation-based profile (for NPCs without inventory)
    occ = getattr(npc, 'occupation', '')
    if occ in ("Scout", "Trapper", "Rancher", "Drifter"):
        return "rifle",   12, 26, "firearms"
    if occ in ("Gambler", "Lawyer", "Merchant"):
        return "revolver", 8, 18, "firearms"
    if occ == "Miner":
        return "pickaxe",  5, 12, "survival"
    if occ == "Blacksmith":
        return "hammer",   6, 14, "survival"
    if "hot-tempered" in getattr(npc, 'traits', []):
        return "knife",    4,  9, "survival"
    return "fists", 1, 5, "survival"


# ── Message helpers ────────────────────────────────────────────────────────

# No-repeat system: tracks seen messages per category. Once all are exhausted,
# the pool resets. A player will see every unique message before any repeats.
_seen_messages: dict = {}  # {category: set_of_seen_indices}


def _pick_unseen(opts: list, category: str) -> str:
    """Pick a message from opts that hasn't been used this playthrough.
    Once all are exhausted, reset the pool."""
    seen = _seen_messages.get(category)
    if seen is None:
        seen = set()
        _seen_messages[category] = seen
    # Find unseen indices
    unseen = [i for i in range(len(opts)) if i not in seen]
    if not unseen:
        # All seen — reset pool
        seen.clear()
        unseen = list(range(len(opts)))
    idx = random.choice(unseen)
    seen.add(idx)
    return opts[idx]


def _is_ranged(weapon: str) -> bool:
    w = weapon.lower()
    return any(k in w for k in ("rifle", "revolver", "pistol", "shotgun", "gun"))


def _miss_msg(attacker: str, defender: str, weapon: str) -> str:
    w = weapon.lower()
    is_shotgun = "shotgun" in w
    is_pistol = any(k in w for k in ("pistol", "revolver", "derringer", "dragoon"))
    is_rifle = _is_ranged(weapon) and not is_shotgun and not is_pistol
    is_bow = "bow" in w

    if is_shotgun:
        opts = [
            f"The shotgun roars. Bark flies off a tree. {defender} is untouched.",
            f"Both barrels go wide. The dirt explodes six feet from {defender}.",
            f"{attacker} fires. The pattern goes high. {defender} ducks, unhurt.",
            f"The blast tears a hole in the scenery. {defender} was not part of the scenery.",
            f"The shotgun booms. A bush disintegrates. {defender} was behind a different bush.",
            f"Smoke and thunder. The shot goes left. {defender} was right.",
            f"The scatter shreds a fence post. {defender} was not the fence post.",
            f"{attacker} pulls both triggers. The recoil throws the pattern into the sky.",
            f"The shotgun roars. A crow explodes mid-flight. {defender} is unimpressed.",
            f"Buckshot peppers the ground around {defender}'s feet. He dances backward.",
            f"The blast goes wide enough to miss a barn. {defender} is smaller than a barn.",
            f"The shotgun kicks. {attacker}'s aim goes with it. {defender} is lucky.",
            f"{attacker} fires from the hip. The pattern misses {defender} and hits everything else.",
            f"The shot goes through {defender}'s hat. The hat was an inch above his head.",
            f"The shotgun belches fire. The noise alone is impressive. The aim is not.",
            f"A cloud of smoke. When it clears, {defender} is still standing. Annoyed.",
            f"The blast goes high. A branch falls on {defender}. Not the same as a hit.",
            f"{attacker} jerks the trigger. The shot goes into the canopy.",
            f"Both barrels. Neither connects. {defender} is either fast or blessed.",
            f"The shotgun removes a section of tree trunk. {defender} was not in it.",
        ]
    elif is_pistol:
        opts = [
            f"{attacker} fires the pistol. The shot goes wide.",
            f"The pistol cracks. {defender} flinches but the shot misses.",
            f"{attacker} squeezes off a round. It hits a rock behind {defender}.",
            f"The bullet whines past {defender}'s ear. Close. Not close enough.",
            f"{attacker} shoots and misses. Powder smoke hangs in the air.",
            f"The pistol barks. The ball sparks off a stone near {defender}'s boot.",
            f"{attacker}'s hand shakes. The shot goes two feet left.",
            f"The shot punches a hole in the air where {defender} used to be.",
            f"{defender} moves. The bullet doesn't follow.",
            f"The pistol cracks. {defender} is no longer where {attacker} aimed.",
            f"A miss. The ball buries itself in a log. Sawdust puffs.",
            f"{attacker} fires wild. The bullet doesn't find anyone.",
            f"The shot goes through {defender}'s coat sleeve. Didn't touch skin.",
            f"Smoke. Noise. No blood. {defender} is still there.",
            f"The ball ricochets off a rock and disappears singing into the trees.",
            f"{attacker} cocks and fires. The ball buries in the dirt at {defender}'s feet.",
            f"The shot clips {defender}'s belt buckle. Sparks. No wound.",
            f"A misfire — no, it fired. Just missed. The powder smoke tastes like failure.",
            f"{attacker} fans the hammer. Speed without accuracy is just noise.",
            f"The bullet parts {defender}'s hair. That's all it parts.",
        ]
    elif is_rifle:
        opts = [
            f"The rifle cracks across the valley. The ball kicks up dirt "
            f"a foot from {defender}.",
            f"{attacker} fires. The shot goes through the space {defender} "
            f"was standing a moment ago.",
            f"The rifle roars. A branch snaps behind {defender}. He's unhurt.",
            f"{attacker}'s shot misses {defender} by inches. "
            f"The sound echoes off the hills.",
            f"The rifle speaks. The ball hits a tree. {defender} thanks the tree.",
            f"The ball buries in the dirt at {defender}'s feet. Dust kicks up.",
            f"A clean miss. The ball disappears into the distance without hitting anything important.",
            f"{attacker} aims too long. {defender} moves. The ball hits where he was.",
            f"The rifle cracks. A stone splits behind {defender}. Wrong target.",
            f"The shot goes high. An eagle screams in complaint.",
            f"The ball passes close enough to {defender} to ruffle his collar.",
            f"{attacker} holds, squeezes, fires. Misses. The fundamentals were all there.",
            f"The rifle ball hums past {defender} and punches a hole in someone's tent. Sorry.",
            f"The recoil throws {attacker}'s aim. The ball goes into the hillside.",
            f"A clean miss. {defender} doesn't even flinch. He heard it go past.",
            f"The shot kicks up gravel near {defender}'s left foot. He moves his foot.",
            f"{attacker}'s shot parts the smoke and finds nothing but air.",
            f"The ball clips a rock and ricochets into the creek. Gone.",
            f"The rifle booms. {defender} drops flat. The ball sails over him.",
            f"Close enough that {defender} feels the wind of it. Not close enough to bleed.",
        ]
    elif is_bow:
        opts = [
            f"The arrow whistles past {defender} and sticks in the dirt.",
            f"{attacker} looses an arrow. It misses {defender} and vanishes into the brush.",
            f"The arrow flies wide. {defender} doesn't even flinch.",
            f"The arrow sticks in a tree trunk six inches from {defender}'s head.",
            f"The shaft goes wide. {defender} watches it fly past with professional interest.",
            f"The arrow sails over {defender}'s shoulder and disappears.",
            f"A miss. The arrow stands quivering in the ground between {defender}'s feet.",
            f"The bowstring snaps back. The arrow buries in a log. {defender} is not the log.",
            f"{attacker} draws and looses. The arrow goes left. {defender} was right.",
            f"The arrow misses and clatters off a rock somewhere behind {defender}.",
            f"The shaft clips {defender}'s sleeve but doesn't draw blood.",
            f"A near miss. The arrow passes close enough to cut air.",
            f"The arrow skitters across the ground past {defender}'s boots.",
            f"The bowstring hums. The arrow flies true — toward the wrong target. A tree.",
            f"{attacker} looses. The arrow fishtails in flight and misses by a body width.",
            f"The arrow sinks into the mud at {defender}'s feet. Not quite.",
            f"The shaft goes high, arcing over {defender}'s head.",
            f"{attacker}'s fingers slip on the release. The arrow goes nowhere useful.",
            f"The arrow passes so close that {defender} feels the fletching brush his cheek.",
            f"A miss. The arrow is recoverable. The dignity isn't.",
        ]
    elif _is_ranged(weapon):
        opts = [
            f"{attacker} fires the {weapon}. The shot goes wide.",
            f"The {weapon} cracks. Misses {defender}.",
        ]
    elif "fist" in w or not weapon:
        opts = [
            f"{attacker} swings. {defender} ducks. Air.",
            f"{attacker} throws a punch. {defender} leans back just enough.",
            f"The fist whistles past {defender}'s chin. That was close.",
            f"{attacker} swings wild. Hits nothing but his own dignity.",
            f"{attacker} throws a haymaker. {defender} is not where the hay goes.",
            f"A big swing. Too big. {defender} steps inside it.",
            f"{attacker} lunges. {defender} sidesteps. {attacker} stumbles.",
            f"The punch goes wide. {attacker}'s shoulder pops. Overcommitted.",
            f"{attacker} jabs. {defender} weaves. Not even close.",
            f"A headbutt attempt. {attacker} catches nothing but air and regret.",
            f"{attacker} swings for the jaw. Misses the jaw. Misses the man.",
            f"The punch sails past. {defender} grins. That's worse than the punch.",
            f"{attacker} goes for the gut. {defender}'s gut is elsewhere.",
            f"A roundhouse that rounds nothing. {defender} watches it go by.",
            f"{attacker} kicks. {defender} steps back. The boot fans air.",
            f"Fists fly. None of them land. Both men circle.",
            f"{attacker} throws an elbow. {defender} dips under it.",
            f"A wild right. {defender} leans. The fist passes his nose by an inch.",
            f"{attacker} charges. {defender} pivots. {attacker} hits a wall instead.",
            f"The swing catches nothing but the smell of whiskey on {attacker}'s breath.",
        ]
    else:
        weapon_str = f" with the {weapon}" if weapon else ""
        opts = [
            f"{attacker} swings{weapon_str}. {defender} dodges aside.",
            f"{attacker}'s blow{weapon_str} goes wide.",
            f"{defender} sidesteps. {attacker} hits dirt.",
            f"The {weapon} cuts air. {defender} was elsewhere.",
            f"{attacker} puts everything into the swing. "
            f"{defender} isn't where the swing lands.",
            f"The {weapon} whistles past {defender}'s ear. Lucky.",
            f"{attacker} chops at {defender}. Misses. The {weapon} bites into the ground.",
            f"A wild swing. The {weapon} hits a barrel instead. The barrel loses.",
            f"{attacker} overcommits. The {weapon} goes past {defender} by a mile.",
            f"The blow sails over {defender}'s head. He ducked faster than expected.",
            f"The {weapon} catches nothing. {defender} dances back.",
            f"{attacker} swings the {weapon} like a man chopping wood. "
            f"{defender} is not wood.",
            f"The {weapon} hits the ground. Sparks. {defender} was a foot to the left.",
            f"{attacker} lunges{weapon_str}. {defender} twists. Clean miss.",
            f"A big overhand. The {weapon} buries in a post. "
            f"{attacker} has to yank it free.",
            f"{defender} jumps back. The {weapon} clips his belt and nothing else.",
            f"The {weapon} connects with a fence rail. The rail was not the target.",
            f"{attacker} brings the {weapon} down hard. On empty ground.",
            f"A savage swing. All power, no aim. {defender} steps aside.",
            f"The {weapon} whistles through the space {defender} just vacated.",
        ]
    # Determine weapon category for no-repeat tracking
    _wcat = "miss_fist"
    if is_shotgun: _wcat = "miss_shotgun"
    elif is_pistol: _wcat = "miss_pistol"
    elif is_rifle: _wcat = "miss_rifle"
    elif is_bow: _wcat = "miss_bow"
    elif _is_ranged(weapon): _wcat = "miss_ranged"
    elif weapon: _wcat = "miss_melee"
    return _pick_unseen(opts, _wcat)


def _hit_msg(attacker: str, defender: str, weapon: str,
             dmg: int, hp: float) -> str:
    """No HP numbers. Describe the physical reality. Weapon-specific."""
    w = weapon.lower()
    is_shotgun = "shotgun" in w
    is_pistol = any(k in w for k in ("pistol", "revolver", "derringer", "dragoon"))
    is_rifle = _is_ranged(weapon) and not is_shotgun and not is_pistol
    is_bow = "bow" in w
    is_axe = any(k in w for k in ("axe", "hatchet", "tomahawk"))
    is_knife = any(k in w for k in ("knife", "bowie"))
    is_pick = "pick" in w
    is_shovel = "shovel" in w

    if is_shotgun:
        if dmg <= 10:
            opts = [
                f"A few pellets clip {defender}. Stings but he's still moving.",
                f"The scatter catches {defender}'s arm. Blood spots his sleeve.",
                f"Wide pattern. Only a couple pellets find {defender}.",
            ]
        elif dmg <= 30:
            opts = [
                f"The shotgun blast hits {defender}. He staggers, bleeding from a dozen holes.",
                f"Buckshot tears into {defender}'s side. He screams.",
                f"{defender} catches half the pattern. His shirt turns red.",
                f"The blast rakes across {defender}. He spins, stays up somehow.",
            ]
        else:
            opts = [
                f"The shotgun hits {defender} at close range. "
                f"Chunks of flesh fly. He's still alive. Somehow.",
                f"Both barrels catch {defender}. He looks like hamburger but won't go down.",
                f"The blast opens {defender} up. He staggers. Blood everywhere.",
            ]
    elif is_pistol:
        if dmg <= 10:
            opts = [
                f"The pistol barks. A graze — {defender} flinches.",
                f"The bullet clips {defender}. He curses and keeps fighting.",
                f"The shot nicks {defender}. Blood, but he's seen worse.",
            ]
        elif dmg <= 25:
            opts = [
                f"The pistol cracks. {defender} grabs at the wound.",
                f"{attacker} puts a round into {defender}. He stumbles back.",
                f"The bullet punches through {defender}'s coat. Blood follows.",
                f"{defender} takes a pistol ball. He grunts. Keeps his feet.",
            ]
        else:
            opts = [
                f"The .44 ball hits {defender} like a fist from God. He staggers.",
                f"The pistol roars. {defender} spins from the impact. "
                f"Stays up by willpower alone.",
                f"The bullet goes through {defender}'s shoulder. "
                f"Bone fragments exit with it.",
            ]
    elif is_rifle:
        if dmg <= 10:
            opts = [
                f"The rifle cracks. The ball grazes {defender}.",
                f"A flesh wound. {defender} flinches but keeps moving.",
                f"The shot catches {defender}'s sleeve. Close.",
            ]
        elif dmg <= 25:
            opts = [
                f"The rifle ball hits {defender}. Blood sprays.",
                f"{attacker}'s shot connects. {defender} stumbles.",
                f"The .50 caliber ball punches into {defender}. "
                f"He grabs the wound. Blood between his fingers.",
                f"The rifle speaks. {defender} listens. He's bleeding.",
            ]
        else:
            opts = [
                f"The rifle ball hits {defender} like a sledgehammer. "
                f"The exit wound is the size of a fist.",
                f"The shot goes through {defender}. You can see daylight "
                f"through the hole. He doesn't fall. Not yet.",
                f"{defender} takes the rifle ball center. Something inside "
                f"him ruptures. He staggers but won't go down.",
                f"The ball shatters bone on the way through. "
                f"{defender} makes a sound like a stepped-on dog.",
            ]
    elif is_bow:
        if dmg <= 10:
            opts = [
                f"The arrow glances off {defender}'s coat.",
                f"A shallow hit. The arrow sticks in {defender}'s arm.",
            ]
        else:
            opts = [
                f"The arrow buries itself in {defender}. He looks down at the shaft.",
                f"The arrow punches through {defender}'s side. He grabs at it.",
                f"The arrow hits {defender} with a wet thud. He tries to pull it out. Bad idea.",
            ]
    elif is_axe:
        if dmg <= 10:
            opts = [
                f"The {weapon} catches {defender}'s arm. A shallow cut.",
                f"A glancing blow with the {weapon}. {defender} jumps back.",
            ]
        elif dmg <= 20:
            opts = [
                f"The {weapon} bites into {defender}'s shoulder. He screams.",
                f"{attacker} connects with the {weapon}. {defender} staggers. "
                f"Blood runs down his arm.",
                f"The {weapon} catches {defender} in the ribs. Something cracks.",
            ]
        else:
            opts = [
                f"The {weapon} hits {defender} in the chest. The blade sticks. "
                f"{attacker} has to yank it free.",
                f"The {weapon} splits {defender}'s collarbone. He drops to one knee.",
                f"A savage chop with the {weapon}. {defender}'s shirt opens up red.",
            ]
    elif is_knife:
        if dmg <= 8:
            opts = [
                f"The {weapon} catches {defender}. A shallow cut.",
                f"{attacker} nicks {defender} with the blade. Blood beads.",
                f"The knife slices {defender}'s forearm. He jerks away.",
            ]
        else:
            opts = [
                f"{attacker} buries the {weapon} in {defender}'s side.",
                f"The {weapon} goes in deep. {defender} gasps.",
                f"{attacker} opens {defender} up with the {weapon}. "
                f"Intestines peek through.",
                f"The knife finds a rib, scrapes along it, goes deeper.",
                f"{attacker} stabs {defender} in the gut. {defender} looks "
                f"down at the knife like he can't believe it.",
            ]
    elif is_pick:
        if dmg <= 15:
            opts = [
                f"The pickaxe catches {defender}'s leg. He howls.",
                f"{attacker} swings the pickaxe. The spike tears {defender}'s coat.",
            ]
        else:
            opts = [
                f"The pickaxe spike punches through {defender}'s thigh. "
                f"He screams. {attacker} has to put a boot on him to pull it out.",
                f"The pickaxe hits {defender} in the shoulder. "
                f"The spike goes in three inches. The sound is terrible.",
                f"{attacker} buries the pickaxe in {defender}. "
                f"This is not what it was designed for. It works anyway.",
            ]
    elif is_shovel:
        if dmg <= 10:
            opts = [
                f"{attacker} cracks {defender} with the flat of the shovel.",
                f"The shovel catches {defender} in the arm. He swears.",
            ]
        else:
            opts = [
                f"{attacker} hits {defender} in the face with the shovel. "
                f"The clang echoes.",
                f"The shovel edge catches {defender} in the neck. "
                f"Blood sprays. That's not a tool anymore.",
                f"{attacker} brings the shovel down on {defender}'s head. "
                f"The sound is like dropping a watermelon.",
            ]
    elif weapon == "fists" or not weapon:
        if dmg <= 5:
            opts = [
                f"{attacker} catches {defender} with a jab. More insult than injury.",
                f"A glancing punch. {defender} shakes it off.",
                f"{attacker} connects. {defender}'s lip splits.",
            ]
        elif dmg <= 10:
            opts = [
                f"{attacker} lands a solid right. {defender}'s head snaps back.",
                f"The punch catches {defender} in the jaw. Something pops.",
                f"{attacker} drives a fist into {defender}'s gut. "
                f"He doubles over, wheezing.",
                f"A clean hit to the nose. {defender}'s eyes water. Blood runs.",
            ]
        else:
            opts = [
                f"{attacker} hits {defender} so hard his ancestors feel it.",
                f"The punch sends {defender} reeling. A tooth bounces off a rock.",
                f"{attacker} beats {defender}'s face like it owes him money.",
                f"The blow breaks something in {defender}'s face. "
                f"The shape of his jaw changes.",
            ]
    else:
        # Generic melee fallback
        weapon_str = f" with the {weapon}" if weapon else ""
        if dmg <= 8:
            opts = [
                f"{attacker} catches {defender}{weapon_str}. A glancing blow.",
                f"The blow lands{weapon_str}. {defender} rolls with it.",
            ]
        else:
            opts = [
                f"{attacker} connects{weapon_str}. {defender} reels.",
                f"A solid hit{weapon_str}. Something in {defender} crunches.",
                f"The blow catches {defender} clean. He spits blood.",
            ]
    _wcat = "hit_fist"
    if is_shotgun: _wcat = "hit_shotgun"
    elif is_pistol: _wcat = "hit_pistol"
    elif is_rifle: _wcat = "hit_rifle"
    elif is_bow: _wcat = "hit_bow"
    elif is_axe: _wcat = "hit_axe"
    elif is_knife: _wcat = "hit_knife"
    elif is_pick: _wcat = "hit_pick"
    elif is_shovel: _wcat = "hit_shovel"
    elif weapon: _wcat = "hit_melee"
    return _pick_unseen(opts, _wcat)


def _kill_msg(attacker: str, defender: str, weapon: str,
              part: str = "", wound_desc: str = "") -> str:
    w = weapon.lower()
    is_shotgun = "shotgun" in w
    is_pistol = any(k in w for k in ("pistol", "revolver", "derringer", "dragoon"))
    is_rifle = _is_ranged(weapon) and not is_shotgun and not is_pistol
    is_bow = "bow" in w
    is_axe = any(k in w for k in ("axe", "hatchet", "tomahawk"))
    is_knife = any(k in w for k in ("knife", "bowie"))
    is_pick = "pick" in w
    is_shovel = "shovel" in w
    p = part.lower() if part else "chest"

    if is_shotgun:
        opts = [
            f"The shotgun removes most of {defender}'s {p}. He was alive, then he wasn't.",
            f"{defender} takes both barrels. What's left wouldn't fill a bucket.",
            f"The blast picks {defender} up and sets him down. Messily.",
            f"{attacker} fires. {defender} comes apart. His hat lands six feet away.",
            f"The shotgun does what shotguns do to a man's {p}. {defender} is done.",
            f"{defender}'s {p} catches the full pattern. The wall behind him is red.",
            f"The shotgun paints the dirt with {defender}. Quick, at least.",
            f"Both barrels to the {p}. {defender} leaves the conversation permanently.",
            f"The blast turns {defender}'s {p} inside out. The crows will eat well tonight.",
            f"{defender} catches the full pattern at ten feet. Open casket is not an option.",
            f"The shotgun turns {defender}'s {p} into a cautionary tale.",
            f"The blast lifts {defender} off his feet. He lands wrong. Everything is wrong.",
            f"Close range. Both barrels. {defender}'s {p} becomes abstract.",
            f"The shotgun rewrites {defender}'s anatomy. He drops in two places.",
            f"{defender} takes both barrels in the {p} and sits down in the middle of himself.",
            f"The pattern hits {defender}'s {p} like a swarm of angry hornets. Metal ones.",
            f"The blast kills {defender}. Also his {p}. Also his dignity.",
            f"{attacker} gives both barrels. {defender}'s {p} is cancelled.",
            f"The shot hits {defender}'s {p} so hard his boots stay where he was standing.",
            f"The shotgun makes a short argument with {defender}'s {p}. The {p} concedes.",
        ]
    elif is_pistol:
        opts = [
            f"{attacker} puts one through {defender}'s {p}. He sits down, surprised. Then dies.",
            f"The pistol cracks. {defender} touches his {p}, looks at his hand, falls.",
            f"A small hole in the {p}. A larger hole in back. {defender} is finished.",
            f"{defender} takes the bullet in the {p} standing. Tips his hat. Tips over.",
            f"The pistol barks. {defender}'s legs give out. Dead before he lands.",
            f"{attacker} shoots {defender} in the {p} at close range. "
            f"Not much {p} left to identify.",
            f"One shot to the {p}. {defender} stops. Everything stops.",
            f"{defender} looks surprised. Then he looks at nothing at all.",
            f"The pistol says one word to {defender}'s {p}. He hears it forever.",
            f"{attacker} pulls the trigger. {defender}'s {p} takes the ball. "
            f"He begins his new career as a corpse.",
            f"The ball goes in through {defender}'s {p} and takes its time leaving.",
            f"{defender} drops his weapon. Then himself. In that order.",
            f"The pistol cracks. {defender} was mid-sentence. The ball finds his {p}. "
            f"He finishes the sentence on the ground.",
            f"A single shot to the {p}. {defender} sits down like a man who found a "
            f"good place to sit. Then falls over.",
            f"The ball enters {defender}'s {p}. He makes a face like he ate something bad. "
            f"Then he dies.",
            f"{defender} takes one in the {p}. He looks at {attacker} like this is unfair. "
            f"It is. He dies anyway.",
            f"The pistol does its work on {defender}'s {p}. He joins the majority.",
            f"{attacker} shoots {defender} in the {p}. {defender} takes it personally. Briefly.",
            f"Clean shot to the {p}. {defender} folds up like paper.",
            f"The bullet finds {defender}'s {p}. The {p} was not expecting company.",
        ]
    elif is_rifle:
        # Body-part-specific rifle kills
        _head = "head" in p
        _neck = "neck" in p
        _chest = "chest" in p or "torso" in p or "sternum" in p
        _gut = "abdomen" in p or "gut" in p or "belly" in p or "groin" in p
        _arm = "arm" in p or "shoulder" in p
        _leg = "leg" in p or "thigh" in p or "knee" in p

        opts = []
        if _head:
            opts = [
                f"The rifle ball takes the top of {defender}'s head off. His hat goes with it.",
                f"The shot enters {defender}'s left eye and exits through the back of his skull. "
                f"His hat is ruined.",
                f"{defender}'s skull cracks open like a walnut. The ball keeps going.",
                f"The rifle ball hits {defender} in the forehead. He falls backward. "
                f"The back of his head stays where he was standing.",
                f"A head shot. {defender}'s face changes shape, then changes address. The ground.",
                f"The ball enters below {defender}'s ear. He drops mid-stride. "
                f"Didn't even flinch.",
                f"{defender}'s head snaps back. Something red and grey exits the far side. "
                f"He crumples.",
                f"The shot hits {defender} in the mouth. He was talking. He stops.",
                f"Clean. Through the temple. {defender} is dead before the sound reaches him.",
                f"The ball takes {defender}'s jaw off. He stands there a moment, confused. "
                f"Then gravity.",
            ]
        elif _neck:
            opts = [
                f"The ball tears through {defender}'s throat. Blood sprays six feet. He drops.",
                f"The shot catches {defender} in the neck. His head lolls. He falls.",
                f"{defender}'s neck opens up. He grabs at it. Blood runs through his fingers. "
                f"He falls.",
                f"The ball severs {defender}'s spine at the neck. He drops like a puppet.",
                f"Through the throat. {defender} makes a sound like a drain. Then nothing.",
            ]
        elif _gut:
            opts = [
                f"The ball hits {defender} in the belly. He doubles over, sits down, dies. "
                f"It takes about thirty seconds.",
                f"A gut shot. {defender} grabs his stomach. Something's leaking. "
                f"He lies down. He doesn't get up.",
                f"The ball goes through {defender}'s intestines. He screams. "
                f"Then he doesn't. Then he's dead.",
                f"{defender} takes a rifle ball in the guts. The exit wound is obscene. "
                f"He falls into it.",
                f"Low shot. The ball opens {defender}'s abdomen. He tries to hold himself "
                f"together. Fails.",
            ]
        elif _arm:
            opts = [
                f"The ball shatters {defender}'s shoulder. He spins, falls, bleeds out in the dirt.",
                f"The shot takes {defender}'s arm off at the elbow. He stares at the stump. "
                f"Shock kills him before the blood loss does.",
                f"{defender}'s arm is destroyed. The ball fragments through his chest on the way. "
                f"He was dead from the secondary damage.",
                f"The ball passes through {defender}'s upper arm and into his ribcage. Two wounds "
                f"for the price of one. He drops.",
                f"The shot shatters {defender}'s shoulder blade. Bone fragments tear through his lung. "
                f"He drowns in his own blood.",
            ]
        elif _leg:
            opts = [
                f"The ball shatters {defender}'s femur. He goes down screaming. "
                f"The arterial bleed kills him in under a minute.",
                f"The shot takes {defender}'s knee apart. He falls. The blood comes fast. "
                f"Too fast.",
                f"{defender}'s thigh explodes. The femoral artery sprays like a fountain. "
                f"He's dead before anyone can help.",
                f"A leg shot. The ball hits the femoral. Blood pumps out in rhythm with his heart. "
                f"Six pumps. Seven. Eight. Done.",
                f"The ball goes through {defender}'s thigh and takes the artery with it. "
                f"He sits down in a spreading pool of himself.",
            ]
        # General rifle kills (always available, mixed in)
        opts.extend([
            f"The rifle cracks across the valley. {defender} drops. His hat rolls away.",
            f"{attacker} fires. {defender} goes down like God pushed him.",
            f"The ball punches through {defender}'s {p}. He takes two steps, then falls. "
            f"He was dead after one.",
            f"{defender} was saying something. The rifle interrupts. Permanently.",
            f"The shot catches {defender} in the {p}. He folds like a letter.",
            f"{attacker}'s rifle speaks once. {defender} listens forever.",
            f"The ball goes through {defender}'s {p} and into the tree behind him. "
            f"{defender} doesn't notice. He's busy dying.",
            f"A clean shot to the {p}. {defender} drops. Flies find him in minutes.",
            f"The rifle does its work from fifty yards. {defender} never hears the shot.",
            f"The .50 cal ball hits {defender}'s {p} and keeps going. "
            f"{defender} does not keep going.",
            f"The rifle roars. {defender} spins half around and falls face-first.",
            f"The ball catches {defender} in the {p}. The exit wound paints the "
            f"ground behind him.",
            f"{defender} takes a rifle ball in the {p}. His expression changes "
            f"from angry to confused to nothing.",
            f"The rifle fires. {defender} takes a step toward {attacker}, reconsiders, dies.",
            f"One shot. {defender} drops like his strings were cut.",
            f"The ball hits {defender}'s {p} with the force of a kicked mule.",
            f"The rifle cracks. {defender} flinches, crumples. The echo outlasts him.",
            f"{defender} catches a .50 caliber ball in the {p}. He coughs once. "
            f"What comes out isn't air.",
            f"The shot takes {defender} off his feet. Dead before he's horizontal.",
            f"The ball enters {defender}'s {p}. He looks at {attacker} like this is personal. "
            f"It is. He dies.",
            f"The rifle ball hits {defender}'s {p} and stops somewhere inside him. "
            f"So does he.",
            f"A .50 cal ball through the {p}. The sound it makes going in is not "
            f"the worst sound. The sound it makes coming out is.",
            f"{defender} catches lead in the {p}. He sits down like a man who just "
            f"remembered something sad. Then he dies.",
            f"The rifle cracks. Smoke. Then {defender} is on the ground with a hole "
            f"in his {p} and nothing in his eyes.",
            f"Through the {p}. Through and through. {defender} touches the wound, "
            f"looks at his red hand, and falls.",
            f"One shot to the {p}. {defender} joins the majority.",
            f"The ball finds {defender}'s {p}. He was not expecting visitors.",
            f"The rifle speaks to {defender}'s {p}. The {p} has no rebuttal.",
            f"Dead. The ball went through the {p}. {defender} went through the ground.",
            f"A killing shot to the {p}. The frontier has one less mouth to feed.",
        ])
    elif is_bow:
        opts = [
            f"The arrow takes {defender} through the throat. He makes a gurgling sound. "
            f"Then no sound.",
            f"The shaft buries to the fletching. {defender} grabs at it. Too late.",
            f"The arrow punches through {defender}'s chest. He looks down at it. Falls.",
            f"A silent kill. The arrow finds {defender}'s heart. He drops without a word.",
            f"The arrow hits {defender} in the eye. He was looking the wrong way.",
            f"The shaft goes through {defender}'s neck. He reaches for it. Misses. Dies.",
            f"No gunshot. No warning. Just an arrow and then {defender} is face-down.",
            f"The arrow catches {defender} between the ribs. He sits down and bleeds out.",
            f"Silent. Quick. The arrow does its work and {defender} drops.",
            f"The shaft pins {defender} to the tree behind him. He hangs there a moment.",
            f"The arrow enters {defender} and doesn't come out the other side. "
            f"It stays. He doesn't.",
            f"A whisper of fletching. Then {defender} has an arrow in his chest "
            f"and a confused expression.",
            f"The bowstring hums. {defender} looks down at the shaft in his gut. "
            f"\"Huh,\" he says. Then he dies.",
            f"The arrow takes {defender} in the back. He arches. Falls face-first.",
            f"One arrow. Center mass. {defender} drops like a sack of grain.",
            f"The shaft goes through {defender}'s hand and into his chest. Two for one.",
            f"The arrow punches into {defender}'s side. He tries to pull it out. "
            f"That makes it worse. He stops trying. He stops everything.",
            f"Silent death. The arrow finds {defender} before the sound of the "
            f"bowstring does.",
            f"The shaft hits {defender} in the liver. He has about thirty seconds. "
            f"He uses them to fall down.",
            f"An arrow sprouts from {defender}'s chest like a bad flower. He wilts.",
        ]
    elif is_axe:
        opts = [
            f"The {weapon} splits {defender}'s skull like a melon. He was already falling.",
            f"{attacker} buries the {weapon} in {defender}. Getting it out is a different problem.",
            f"The {weapon} catches {defender} in the neck. The fight is over.",
            f"{defender} takes the {weapon} between the shoulder blades. He arches. Then nothing.",
            f"The {weapon} hits {defender} so hard it sticks. He falls with it still in him.",
            f"{attacker} puts the {weapon} through {defender}'s collarbone. "
            f"The sound is like splitting kindling.",
            f"The {weapon} takes the top of {defender}'s head off. Clean. Professional.",
            f"{defender} catches the {weapon} in the chest. He looks at it. "
            f"He looks at {attacker}. He dies.",
            f"One chop. {defender} drops. {attacker} puts a boot on him to retrieve the {weapon}.",
            f"The {weapon} enters {defender}'s skull and stops at the jaw. "
            f"He stands there a moment. Then gravity.",
            f"{attacker} swings the {weapon} overhand. {defender}'s arm separates at the "
            f"shoulder. He dies watching it fall.",
            f"The blade catches {defender} in the throat. His head goes back. "
            f"Way back. Too far back.",
            f"{defender} takes the {weapon} in the forehead. His expression freezes. "
            f"The rest of him follows.",
            f"The {weapon} hits {defender} so hard it passes through and hits the air behind him.",
            f"A savage downward chop. The {weapon} buries to the handle. "
            f"{defender} is done standing.",
            f"The {weapon} opens {defender} from shoulder to sternum. "
            f"The inside of a man looks worse than you'd think.",
            f"{attacker} plants the {weapon} in {defender}'s chest like a flag. "
            f"This land is claimed.",
            f"One swing. The {weapon} finds {defender}'s skull and stays there.",
            f"The {weapon} goes in sideways. {defender} goes down permanent.",
            f"Timber. The {weapon} fells {defender} like a diseased elm.",
        ]
    elif is_knife:
        opts = [
            f"{attacker} puts the {weapon} into {defender}. Twice. Three times. He stops counting.",
            f"The blade goes in clean and comes out red. {defender} sinks to his knees.",
            f"{attacker} opens {defender} up with the {weapon}. Quick and ugly.",
            f"The knife finds something vital. {defender}'s eyes go wide, then empty.",
            f"{defender} looks down at the knife in his belly. \"Oh,\" he says. Then nothing.",
            f"The {weapon} goes in under the ribs. {defender} grabs {attacker}'s wrist. "
            f"Too late. Way too late.",
            f"{attacker} drives the {weapon} in to the hilt. Twists. {defender} makes "
            f"a sound like a stepped-on cat.",
            f"The blade opens {defender}'s throat. He tries to hold it closed. He can't.",
            f"One thrust. The {weapon} goes through {defender}'s liver. He sits down "
            f"and dies quietly.",
            f"{attacker} stabs {defender} in the heart. It's over fast. "
            f"The knife did all the work.",
            f"The {weapon} catches {defender} in the kidney. He arches backward. "
            f"The scream is brief.",
            f"{defender} didn't see the knife. Didn't feel it at first. "
            f"Then he felt everything.",
            f"{attacker} guts {defender} like a fish. Efficient. Horrible.",
            f"The {weapon} goes in through the belly and doesn't come out. "
            f"{defender} falls with it still in him.",
            f"The blade finds the gap between {defender}'s ribs. He breathes in. "
            f"He doesn't breathe out.",
            f"{attacker} opens a second mouth in {defender}'s throat. "
            f"This one doesn't talk.",
            f"The knife does ugly work. {defender} dies holding his guts in. "
            f"He fails at that too.",
            f"In close. The {weapon} goes in four times before {defender} can react. "
            f"He reacts by dying.",
            f"Quiet. Fast. The {weapon} finds {defender}'s neck. "
            f"Blood runs down the blade and over {attacker}'s hand.",
            f"{defender} grabs the blade. Cuts his fingers. Doesn't save his life.",
        ]
    elif is_pick:
        opts = [
            f"The pickaxe spike goes through {defender}'s chest and out his back. "
            f"A new use for a mining tool.",
            f"{attacker} buries the pickaxe in {defender}'s skull. It makes the same sound "
            f"as hitting rock. Almost.",
            f"The pickaxe catches {defender} in the ribs. Breaks three. "
            f"He goes down and stays down.",
            f"{attacker} swings the pickaxe like he's breaking rock. "
            f"{defender} breaks easier than rock.",
            f"The spike punches through {defender}'s back. He arches, stiffens, falls.",
            f"The pickaxe finds {defender}'s spine. The sound is terrible. "
            f"He drops like a puppet with cut strings.",
            f"One overhead swing. The pick enters {defender}'s skull. "
            f"{attacker} has to use his boot to pull it out.",
            f"The pickaxe was designed for ore. It works on people too. "
            f"{defender} confirms this.",
            f"{defender} takes the pick through the shoulder and into the chest cavity. "
            f"He dies standing, pinned to a post.",
            f"The spike goes through {defender}'s neck. The mining tool has found "
            f"a new vocation.",
            f"{attacker} drives the pick through {defender} like he's staking a claim. "
            f"In a way, he is.",
            f"The pickaxe hits {defender} in the temple. Instant. Ugly.",
            f"The sound of the pickaxe hitting {defender} is identical to the sound "
            f"of it hitting sandstone. Nature is efficient.",
            f"{defender} catches the pick in the sternum. He looks at it like "
            f"a puzzle he can't solve. Then he dies.",
            f"The pickaxe goes in at an angle. {defender} falls sideways, "
            f"held up briefly by the spike.",
            f"A miner's weapon for a miner's murder. The pick goes through "
            f"{defender} and into the dirt.",
            f"The pick hits {defender} so hard it lifts him. Briefly.",
            f"{attacker} puts the pick through {defender}'s jaw. Upward. "
            f"The point exits near his ear.",
            f"The spike enters {defender}'s gut. He curls around it like "
            f"a question mark. A final question.",
            f"One swing. The pickaxe embeds in {defender}. {attacker} leaves it there.",
        ]
    elif is_shovel:
        opts = [
            f"{attacker} caves in {defender}'s skull with the shovel. "
            f"The sound is memorable.",
            f"The shovel catches {defender} in the temple. He drops. "
            f"He was dead before the echo.",
            f"{attacker} brings the shovel down on {defender}'s head. "
            f"The clang rings across the camp.",
            f"The shovel edge catches {defender} in the neck. Nearly takes his head off.",
            f"{attacker} hits {defender} in the face with a shovel. "
            f"His face changes shape. Permanently.",
            f"The shovel breaks over {defender}'s skull. {defender} also breaks.",
            f"Death by shovel. There's a first time for everything. "
            f"This is {defender}'s.",
            f"The flat of the shovel catches {defender} across the jaw. "
            f"The jaw goes one way. {defender} goes the other.",
            f"{attacker} shovels {defender} into the ground. Literally.",
            f"The shovel meets {defender}'s forehead. The forehead loses. "
            f"The sound is like a church bell.",
            f"An undignified death. The shovel does its work. "
            f"{defender} won't need a headstone. He needs a coroner.",
            f"The shovel catches {defender} behind the ear. He drops like a stone. "
            f"He is a stone now.",
            f"{attacker} swings the shovel like he's clearing snow. "
            f"{defender} is cleared.",
            f"The business end of the shovel opens {defender}'s head up. "
            f"It wasn't designed for this. It works anyway.",
            f"A man killed by a shovel. The frontier has no poetry in it. "
            f"{defender} confirms.",
            f"The shovel connects with {defender}'s skull at full swing. "
            f"The vibration travels up {attacker}'s arms. Worth it.",
            f"{defender} takes a shovel to the bridge of the nose. "
            f"His face becomes a before-and-after.",
            f"The shovel rings like a bell against {defender}'s head. "
            f"The congregation is dead.",
            f"Iron on bone. The shovel ends the argument. "
            f"{defender} had a rebuttal but forgot it.",
            f"{attacker} digs {defender}'s grave with the same shovel. Efficient.",
        ]
    elif _is_ranged(weapon):
        opts = [
            f"The {weapon} cracks. {defender} goes down and doesn't move.",
            f"{attacker} fires. Dead before hitting the ground.",
            f"The shot catches {defender} somewhere important. He sits down, then falls over.",
        ]
    else:
        # Unarmed / blunt / other melee
        weapon_str = f" with the {weapon}" if weapon else ""
        opts = [
            f"{attacker} finishes it{weapon_str}. {defender} hits the ground "
            f"and doesn't get back up.",
            f"The last blow lands. {defender} collapses. Quieter now.",
            f"{defender} drops. It's over. Quick, which is more than most get.",
            f"{attacker} beats {defender} to death{weapon_str}. "
            f"It takes longer than either of them expected.",
            f"{defender} goes down. A tooth bounces off a rock. "
            f"He won't be needing it.",
            f"The sound of the last hit is wet. {defender} doesn't move again.",
            f"{attacker} puts {defender} down{weapon_str}. "
            f"He lies there like he was always going to end up there.",
            f"The final blow snaps {defender}'s neck. He drops like a marionette.",
            f"{attacker} hits {defender} so hard his mother feels it back east.",
            f"One last punch. {defender}'s lights go out. The lights are not coming back.",
            f"{defender} catches the last one on the chin. His eyes roll. He folds.",
            f"The sound of fist on skull. {defender} goes down and stays. "
            f"Teeth on the ground.",
            f"{attacker} pounds {defender} into the dirt{weapon_str}. "
            f"The dirt is complicit.",
            f"A final blow{weapon_str}. {defender} is done fighting. "
            f"Done everything.",
            f"{defender} crumples. The last thing he sees is {attacker}'s boot. "
            f"Mercy? No. Mud.",
            f"Beat to death{weapon_str} in the dirt. The frontier writes "
            f"no obituaries for this.",
            f"{attacker} ends it{weapon_str}. {defender} dies making "
            f"a noise nobody wants to remember.",
            f"The killing blow lands{weapon_str}. {defender} was already "
            f"halfway to dead. Now he's all the way.",
            f"Beaten to death. No glory in it. {defender} goes still.",
            f"The last hit disconnects something important in {defender}'s "
            f"skull. He crumples. Done.",
        ]
    _wcat = "kill_fist"
    if is_shotgun: _wcat = "kill_shotgun"
    elif is_pistol: _wcat = "kill_pistol"
    elif is_rifle: _wcat = "kill_rifle"
    elif is_bow: _wcat = "kill_bow"
    elif is_axe: _wcat = "kill_axe"
    elif is_knife: _wcat = "kill_knife"
    elif is_pick: _wcat = "kill_pick"
    elif is_shovel: _wcat = "kill_shovel"
    elif weapon: _wcat = "kill_melee"
    return _pick_unseen(opts, _wcat)


# ── Incapacitation flavor — wounded/dying behavior ────────────────────────

INCAP_FLAVOR = [
    # Physical reactions
    " presses a hand against the wound. Blood runs between the fingers.",
    " doubles over, retching. Dark blood spatters the ground.",
    " sucks air through clenched teeth, shaking hard.",
    " slides down to one knee. Eyes glassy.",
    " grabs a fistful of dirt, squeezing until the knuckles go white.",
    " makes a wet, rattling sound with every breath.",
    " drags one leg behind, leaving a smear of red in the dust.",
    " sits down heavily, like the strings were cut.",
    " holds the wound with both hands. It doesn't help.",
    " spits a mouthful of blood and wipes a lip.",
    " collapses to all fours, head hanging.",
    " leans hard against a tree, breathing in shallow bursts.",
    " presses a palm flat against the dirt, trembling.",
    " pulls at a collar, gasping. Face gone grey.",
    " curls into a ball, knees to chest.",
    " rocks back and forth, arms wrapped tight.",
    # Vocal
    " calls out for someone not here. The name is garbled.",
    " whispers a prayer. The words come out wrong.",
    " says something about a farm, a wife. Trails off.",
    " mutters the same word over and over. Can't make it out.",
    " laughs once — a short, ugly sound. Then quiet.",
    " says 'I don't want to die here.'",
    " whispers 'Tell my boy...' The rest is lost.",
    " asks what day it is. Doesn't seem to hear the answer.",
    " says 'It's cold.' It isn't.",
    " recites a Bible verse. Gets it wrong halfway through.",
    " keeps saying 'okay' under their breath. Over and over.",
    " moans low and steady, like a hurt animal.",
    " tries to say something. Just blood.",
    " whispers 'I can see the river.'",
    # Behavioral
    " fumbles for a weapon. Can't close the hand.",
    " tries to stand. Makes it halfway. Falls.",
    " looks at the sky with an expression that is hard to describe.",
    " reaches toward something only they can see.",
    " goes very still. Just the chest moving, barely.",
    " blinks slowly. Seems to be looking through the ground.",
    " folds the hands neatly. A strange, quiet gesture.",
    " tries to crawl somewhere. Gives up after two feet.",
    " pulls a photograph from a pocket. Holds it against the chest.",
    " turns the head away. Doesn't want to see the blood.",
]


def incap_message(name: str) -> str:
    """Random incapacitation flavor text for a badly wounded character."""
    return name + random.choice(INCAP_FLAVOR)


# ── Combat taunts (1849 Gold Rush era) ────────────────────────────────────

COMBAT_TAUNTS_HOSTILE = [
    "\"I'll put you in a shallow grave and nobody'll know your name!\"",
    "\"You picked the wrong camp to walk into, friend.\"",
    "\"I been killing men since before you could walk!\"",
    "\"Come on then! Let's see what you're made of!\"",
    "\"That claim is mine. Die for it or walk away.\"",
    "\"You think you're the first man I've shot?\"",
    "\"I'll leave you for the coyotes!\"",
    "\"You're dumber than you look, and that's saying something!\"",
    "\"I've buried three men this month. You'll make four.\"",
    "\"Your mother should've drowned you!\"",
    "\"Stand still so I can shoot you proper!\"",
    "\"You fight like a schoolmarm!\"",
    "\"That gold dust on you? It's already mine.\"",
    "\"The buzzards are gonna eat good tonight!\"",
    "\"I'll tan your hide and sell it in Sacramento!\"",
    "\"You yellow-bellied son of a mule!\"",
    "\"Pray fast, boy. You ain't got long.\"",
    "\"I'll carve my name in your skull!\"",
    "\"Nobody out here to save you. Nobody out here to care.\"",
    "\"This is the last face you're ever gonna see.\"",
]

COMBAT_TAUNTS_WOUNDED = [
    "\"That the best you can do?!\"",
    "\"I've cut myself worse shaving!\"",
    "\"You'll have to hit harder than that, you bastard!\"",
    "\"I'm still standing! What does that tell you?\"",
    "\"God damn you to hell and back!\"",
    "\"I'll kill you with one arm if I have to!\"",
    "\"Blood don't bother me none!\"",
    "\"Flesh wound. I've had worse from a mule kick.\"",
    "\"You're gonna regret not finishing me!\"",
    "\"I ain't done. Not by a long shot.\"",
    "\"Come closer. I dare you. COME CLOSER.\"",
    "\"My grandpa hit harder than you, and he was blind!\"",
]

COMBAT_TAUNTS_SCARED = [
    "\"Wait — hold on — I didn't mean none of it!\"",
    "\"Don't shoot! Christ, don't shoot!\"",
    "\"Take the dust, take all of it, just let me walk!\"",
    "\"I got children back East! They need me!\"",
    "\"Hold on now, let's be reasonable about this!\"",
    "\"I yield! I yield, damn you!\"",
    "\"Mercy! For the love of God!\"",
    "\"Please — I ain't worth the bullet!\"",
    "\"I was just bluffing! I wasn't really gonna!\"",
    "\"You win! You win, alright?!\"",
    "\"I'll leave! I'll leave the territory, I swear it!\"",
]

COMBAT_INSULTS = [
    "\"You smell worse than a dead mule in July!\"",
    "\"Your claim is worthless and so are you!\"",
    "\"I've seen better men crawl out of a whiskey bottle!\"",
    "\"You couldn't find gold in a jewelry store!\"",
    "\"Your pan technique is an embarrassment to prospectors everywhere!\"",
    "\"Did your mama teach you to shoot? Because she did a terrible job!\"",
    "\"I've met smarter rocks!\"",
    "\"You're about as useful as a screen door on a submarine!\"",
    "\"Even the mules don't respect you!\"",
    "\"I heard your last claim yielded nothing but disappointment!\"",
]


def combat_taunt(name: str, health_pct: float, is_hostile: bool) -> str:
    """Return a combat taunt from an NPC. health_pct = current/max (0-1)."""
    if health_pct < 0.25 and random.random() < 0.5:
        return f"{name} cries: {random.choice(COMBAT_TAUNTS_SCARED)}"
    elif health_pct < 0.5:
        return f"{name} snarls: {random.choice(COMBAT_TAUNTS_WOUNDED)}"
    elif is_hostile:
        if random.random() < 0.3:
            return f"{name} sneers: {random.choice(COMBAT_INSULTS)}"
        return f"{name} shouts: {random.choice(COMBAT_TAUNTS_HOSTILE)}"
    return ""
