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


# ── Player attacks NPC ─────────────────────────────────────────────────────

# Aimed shot body part targets — (label, hit_penalty, damage_mult, special)
AIMED_SHOTS = [
    ("Center mass (normal)",  0, 1.0, None),
    ("Head — lethal",        -6, 2.0, "head"),
    ("Legs — slow them",     -3, 0.7, "legs"),
    ("Arms — disarm",        -4, 0.6, "arms"),
    ("Torso — heavy bleed",  -2, 1.2, "torso"),
]


def player_attack_npc(player: "Player", npc: "NPC",
                      weapon: Optional["Item"] = None,
                      distance: int = 1,
                      aimed_part: int = 0) -> CombatEvent:
    """Resolve one attack from player onto npc. Mutates npc state.
    aimed_part: index into AIMED_SHOTS (0 = center mass / no aim)."""

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
        weapon.extra["loaded"] = loaded - 1     # expend one round
        skill_val  = player.skills.get("firearms", 0)
        attr_val   = player.attributes.get("agility", 10)
        dmg_lo, dmg_hi = weapon.damage_min, weapon.damage_max
        weapon_name = weapon.name
        str_bonus = 0

        # One-handed penalty for firearms
        # Rifles need both hands; pistols get a slight penalty one-handed
        is_pistol = any(w in weapon.name.lower()
                        for w in ("pistol", "revolver", "derringer"))
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
        # Unarmed
        skill_val  = 0
        attr_val   = player.attributes.get("strength", 10)
        dmg_lo, dmg_hi = 1, 4
        weapon_name = "fists"
        str_bonus = (player.attributes.get("strength", 10) - 10) // 3

    # --- Hit roll vs NPC dodge ---
    npc_defense = 8 + _attr_bonus(npc.attributes.get("agility", 10))
    roll = _d20() + _skill_bonus(skill_val) + _attr_bonus(attr_val)
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

    if roll < npc_defense:
        miss_extra = f" (aimed: {aim_label})" if aimed_part > 0 else ""
        return CombatEvent(
            attacker=player.name, defender=npc.name,
            weapon_name=weapon_name, hit=False, damage=0,
            message=_miss_msg(player.name, npc.name, weapon_name) + miss_extra,
        )

    # --- Damage ---
    dmg = max(1, int((random.randint(dmg_lo, dmg_hi) + str_bonus) * aim_dmg_mult))

    # Aimed shot specials
    if aim_special == "head" and dmg >= 5:
        # Headshot: high chance of instant kill
        if random.random() < 0.6:
            dmg = max(dmg, int(npc.health) + 10)  # lethal
    elif aim_special == "legs":
        # Leg shot: halve NPC movement (via combat_state)
        npc.attributes["agility"] = max(1, npc.attributes.get("agility", 10) - 4)
    elif aim_special == "arms":
        # Arm shot: reduce NPC damage capability
        npc.attributes["strength"] = max(1, npc.attributes.get("strength", 10) - 4)

    # Apply wound through the wound system (creates DetailedWound if available)
    wound = npc.wounds.apply_hit(dmg, _weapon_damage_type(weapon_name))
    npc.health = max(0.0, npc.health - dmg)
    _check_npc_morale(npc)

    killed      = npc.combat_state == "dead"
    fled        = npc.combat_state == "fleeing"
    surrendered = npc.combat_state == "surrendered"

    wound_desc = f" ({wound.description})" if hasattr(wound, "description") else ""
    if killed:
        msg = _kill_msg(player.name, npc.name, weapon_name)
    else:
        msg = _hit_msg(player.name, npc.name, weapon_name, dmg, npc.health)
        msg += wound_desc
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

def npc_attack_player(npc: "NPC", player: "Player") -> CombatEvent:
    """Resolve one NPC attack onto the player. Mutates player.survival."""
    from src.player import Stance

    weapon_name, dmg_lo, dmg_hi, skill_name = _npc_weapon_profile(npc)
    skill_val = npc.skills.get(skill_name, 0)

    # Player defense: agility + stance modifier
    stance_bonus = {
        Stance.STANDING: 0, Stance.CROUCHED: 2,
        Stance.PRONE_DOWN: 4, Stance.PRONE_UP: 2,
    }
    player_defense = (8
                      + _attr_bonus(player.attributes.get("agility", 10))
                      + stance_bonus.get(player.stance, 0))

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
            pass

    # Apply wound through the wound system (pass actual body part)
    wound = player.wounds.apply_hit(dmg, _weapon_damage_type(weapon_name),
                                      target_part=hit_part if worn else None,
                                      worn_equipment=worn)
    player.survival.health = max(0.0, player.survival.health - dmg)
    killed = player.survival.health <= 0 or not player.wounds.alive

    wound_desc = ""
    if hasattr(wound, "description"):
        wound_desc = f" {wound.description}."
        if hasattr(wound, "bleed_level") and wound.is_bleeding:
            wound_desc += f" Bleeding: {wound.bleed_level}."

    if killed:
        msg = (f"{npc.name} drives the {weapon_name} home. "
               f"You collapse. Everything goes dark.")
    else:
        msg = _hit_msg(npc.name, "you", weapon_name, int(dmg), player.survival.health)
        if clothing_msg:
            msg += f" {clothing_msg}"
        msg += wound_desc

    return CombatEvent(
        attacker=npc.name, defender=player.name,
        weapon_name=weapon_name, hit=True, damage=int(dmg),
        killed=killed, message=msg,
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
                      victim_name: str, killed: bool) -> List[str]:
    """
    Bystanders react to observed violence.
    Mutates witness NPC states. Returns list of reaction messages.
    """
    msgs = []
    for npc in witnesses:
        if not npc.present or npc.name in (attacker_name, victim_name):
            continue
        rel_hit = -35 if killed else -18
        npc.adjust_relationship(rel_hit)
        if killed or "nervous" in npc.traits:
            if npc.combat_state == "neutral":
                npc.combat_state = "fleeing"
                msgs.append(f"{npc.name} backs away fast, eyes wide.")
        elif npc.combat_state == "neutral":
            msgs.append(f"{npc.name} reaches slowly for his weapon.")
    return msgs


# ── NPC morale ─────────────────────────────────────────────────────────────

def _check_npc_morale(npc: "NPC"):
    """Update NPC combat_state from health. Call after applying damage."""
    if npc.health <= 0:
        npc.health   = 0
        npc.alive    = False
        npc.present  = False
        npc.combat_state = "dead"
        return

    pct = npc.health / 100.0

    if pct <= 0.12:
        npc.combat_state = "surrendered" if "brave" in npc.traits else "fleeing"
    elif pct <= 0.30:
        if "coward" in npc.traits or "nervous" in npc.traits:
            npc.combat_state = "fleeing"
        elif random.random() < 0.45:
            npc.combat_state = "fleeing"
        # else stays hostile — set by engine when aggro'd


# ── NPC weapon profiles ────────────────────────────────────────────────────

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
    occ = npc.occupation
    if occ in ("Scout", "Trapper", "Rancher", "Drifter"):
        return "rifle",   12, 26, "firearms"
    if occ in ("Gambler", "Lawyer", "Merchant"):
        return "revolver", 8, 18, "firearms"
    if occ == "Miner":
        return "pickaxe",  5, 12, "survival"
    if occ == "Blacksmith":
        return "hammer",   6, 14, "survival"
    if "hot-tempered" in npc.traits:
        return "knife",    4,  9, "survival"
    return "fists", 1, 5, "survival"


# ── Message helpers ────────────────────────────────────────────────────────

def _is_ranged(weapon: str) -> bool:
    w = weapon.lower()
    return any(k in w for k in ("rifle", "revolver", "pistol", "shotgun", "gun"))


def _miss_msg(attacker: str, defender: str, weapon: str) -> str:
    if _is_ranged(weapon):
        opts = [
            f"{attacker} fires the {weapon} — the shot goes wide.",
            f"{attacker} shoots and misses {defender}.",
            f"The {weapon} cracks. The shot misses {defender}.",
        ]
    else:
        weapon_str = f" with the {weapon}" if weapon else ""
        opts = [
            f"{attacker} swings{weapon_str} — {defender} dodges aside.",
            f"{attacker}'s blow{weapon_str} goes wide.",
            f"{defender} sidesteps and {attacker} finds nothing.",
        ]
    return random.choice(opts)


def _hit_msg(attacker: str, defender: str, weapon: str,
             dmg: int, hp: float) -> str:
    condition = ("badly wounded" if hp < 25
                 else "wounded" if hp < 50
                 else "shaken")
    if _is_ranged(weapon):
        verb = "grazes" if dmg <= 5 else "shoots" if dmg <= 15 else "hits hard with"
        return (f"{attacker} {verb} {defender} with the {weapon} ({dmg} dmg). "
                f"{defender.capitalize()} is {condition}.")
    else:
        weapon_str = f" with the {weapon}" if weapon else ""
        verb = "grazes" if dmg <= 5 else "hits" if dmg <= 15 else "strikes hard"
        return (f"{attacker} {verb} {defender}{weapon_str} ({dmg} dmg). "
                f"{defender.capitalize()} is {condition}.")


def _kill_msg(attacker: str, defender: str, weapon: str) -> str:
    if _is_ranged(weapon):
        opts = [
            f"{attacker} puts a round through {defender}. Dead before hitting the ground.",
            f"The {weapon} cracks. {defender} drops.",
            f"{attacker} fires. {defender} goes down and doesn't move.",
        ]
    else:
        weapon_str = f" with the {weapon}" if weapon else ""
        opts = [
            f"{attacker} finishes it{weapon_str}. {defender} goes down and doesn't move.",
            f"The blow lands clean. {defender} collapses, dead.",
            f"{defender} drops. It's over.",
        ]
    return random.choice(opts)
