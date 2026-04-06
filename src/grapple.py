"""
src/grapple.py

Wrestling / grappling combat subsystem for American Prospector.

Grappling is a close-quarters alternative to striking or shooting.
Once initiated, both combatants are locked together and take turns
choosing grapple-specific actions until one breaks free or is subdued.

Integration:
    combat_mode.py:  offer "Grapple" alongside Strike / Shoot
    engine.py:       store active GrappleState on the combat context
    player.py:       uses player.attributes, player.skills
    npc.py:          uses npc.attributes, npc.health, npc.combat_state
    health_system.py: wounds via player.wounds.apply_hit / npc.wounds.apply_hit
"""

from dataclasses import dataclass
from typing import Optional, Tuple, TYPE_CHECKING

from src.health_system import BP, DmgType, PART_DATA

if TYPE_CHECKING:
    from random import Random
    from src.player import Player
    from src.npc import NPC


# ============================================================================
#  Constants
# ============================================================================

GRAPPLE_ACTIONS = [
    "shove", "trip", "disarm", "arm_lock", "chokehold",
    "headbutt", "release",
]

GRAPPLE_LABELS = {
    "shove":     "Shove Away",
    "trip":      "Trip / Sweep",
    "disarm":    "Strip Weapon",
    "arm_lock":  "Arm Lock",
    "chokehold": "Chokehold",
    "headbutt":  "Headbutt",
    "release":   "Release",
}

# Internal tuning
_CONTROL_DRIFT_RATE = 3          # per tick, control drifts toward 50
_CHOKEHOLD_DMG_LO = 2
_CHOKEHOLD_DMG_HI = 3
_CHOKEHOLD_KO_THRESHOLD = 10     # NPC passes out below this HP
_HEADBUTT_DMG_LO = 3
_HEADBUTT_DMG_HI = 8
_HEADBUTT_SELF_DMG = 2           # minor damage to player's own head
_ARM_LOCK_CONTROL_BONUS = 15
_SURVIVAL_SKILL_THRESHOLD = 5    # skill level for grapple initiation bonus
_SURVIVAL_GRAPPLE_BONUS = 3


# ============================================================================
#  GrappleState
# ============================================================================

@dataclass
class GrappleState:
    """Tracks an active grapple between the player and an NPC."""
    grappler_is_player: bool
    target_npc_id: str
    hold_type: str = "clinch"       # clinch | arm_lock | chokehold | pin
    held_part: str = ""             # BP enum value of held body part
    control: int = 50               # 0-100; higher = player dominates
    turns: int = 0


# ============================================================================
#  Helpers
# ============================================================================

def _d20(rng: "Random") -> int:
    return rng.randint(1, 20)


def _str_score(entity) -> int:
    """Read strength from a Player or NPC."""
    return entity.attributes.get("strength", 10)


def _agi_score(entity) -> int:
    """Read agility from a Player or NPC."""
    return entity.attributes.get("agility", 10)


def _con_score(entity) -> int:
    """Read constitution from a Player or NPC."""
    return entity.attributes.get("constitution", 10)


def _clamp(value: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, value))


# ============================================================================
#  1. Initiate grapple
# ============================================================================

def initiate_grapple(
    player: "Player",
    npc: "NPC",
    rng: "Random",
) -> Tuple[bool, str, Optional[GrappleState]]:
    """
    Attempt to grab an NPC and enter a grapple.

    Roll: player STR + d20  vs  NPC STR + d20.
    Bonus +3 if player survival skill >= 5 (frontier wrestling know-how).

    Returns (success, narrative_message, state_or_None).
    On failure the NPC gets a free counter-attack opportunity (the caller
    in combat_mode should resolve that separately).
    """
    p_str = _str_score(player)
    n_str = _str_score(npc)

    bonus = 0
    if player.skills.get("survival", 0) >= _SURVIVAL_SKILL_THRESHOLD:
        bonus = _SURVIVAL_GRAPPLE_BONUS

    p_roll = p_str + _d20(rng) + bonus
    n_roll = n_str + _d20(rng)

    if p_roll >= n_roll:
        state = GrappleState(
            grappler_is_player=True,
            target_npc_id=npc.npc_id,
            hold_type="clinch",
            held_part=BP.CHEST,
            control=55,          # slight advantage for initiator
            turns=0,
        )
        msg = (
            f"You lunge at {npc.name} and lock into a clinch. "
            f"Your arms wrap around their torso."
        )
        return True, msg, state
    else:
        msg = (
            f"You reach for {npc.name}, but they twist away and shove you "
            f"off balance. {npc.name} has an opening for a free strike!"
        )
        return False, msg, None


# ============================================================================
#  2. Grapple actions
# ============================================================================

def grapple_action(
    state: GrappleState,
    action: str,
    player: "Player",
    npc: "NPC",
    rng: "Random",
) -> Tuple[str, bool]:
    """
    Execute a grapple action chosen by the player.

    Returns (narrative_message, grapple_still_active).
    """
    state.turns += 1

    if action == "release":
        return _action_release(state, npc)

    if action == "shove":
        return _action_shove(state, player, npc, rng)

    if action == "trip":
        return _action_trip(state, player, npc, rng)

    if action == "disarm":
        return _action_disarm(state, player, npc, rng)

    if action == "arm_lock":
        return _action_arm_lock(state, player, npc, rng)

    if action == "chokehold":
        return _action_chokehold(state, player, npc, rng)

    if action == "headbutt":
        return _action_headbutt(state, player, npc, rng)

    return f"Unknown grapple action: {action}.", True


# -- Individual actions -----------------------------------------------------

def _action_release(state: GrappleState, npc: "NPC") -> Tuple[str, bool]:
    msg = f"You release your grip on {npc.name} and step back."
    return msg, False


def _action_shove(
    state: GrappleState, player: "Player", npc: "NPC", rng: "Random",
) -> Tuple[str, bool]:
    """Push NPC 1-2 tiles away.  STR check.  Breaks grapple."""
    p_roll = _str_score(player) + _d20(rng)
    n_roll = _str_score(npc) + _d20(rng)

    if p_roll >= n_roll:
        tiles = rng.randint(1, 2)
        msg = (
            f"You plant your feet and shove {npc.name} hard. "
            f"They stumble back {tiles} {'pace' if tiles == 1 else 'paces'}."
        )
        return msg, False   # grapple ends
    else:
        state.control = _clamp(state.control - 10)
        msg = (
            f"You try to shove {npc.name} away, but they brace against you. "
            f"Your grip loosens in the struggle."
        )
        return msg, True    # grapple continues, worse control


def _action_trip(
    state: GrappleState, player: "Player", npc: "NPC", rng: "Random",
) -> Tuple[str, bool]:
    """Sweep NPC's legs.  AGI check.  NPC loses next turn.  Breaks grapple."""
    p_roll = _agi_score(player) + _d20(rng)
    n_roll = _agi_score(npc) + _d20(rng)

    if p_roll >= n_roll:
        npc.combat_state = "prone"   # engine should skip NPC's next action
        msg = (
            f"You hook your leg behind {npc.name}'s ankle and wrench. "
            f"They crash to the ground, stunned."
        )
        return msg, False   # grapple ends
    else:
        state.control = _clamp(state.control - 5)
        msg = (
            f"You try to sweep {npc.name}'s legs but they keep their footing. "
            f"The failed attempt costs you leverage."
        )
        return msg, True


def _action_disarm(
    state: GrappleState, player: "Player", npc: "NPC", rng: "Random",
) -> Tuple[str, bool]:
    """Strip the NPC's weapon. STR check. Weapon drops to ground."""
    from src.combat import _npc_weapon_profile
    weapon_name, _, _, _ = _npc_weapon_profile(npc)
    if weapon_name == "fists":
        msg = f"{npc.name} isn't holding a weapon. You wrench at empty air."
        return msg, True

    if getattr(npc, '_disarmed', False):
        msg = f"{npc.name} is already disarmed."
        return msg, True

    p_roll = _str_score(player) + _d20(rng)
    n_roll = _str_score(npc) + _d20(rng)

    if p_roll >= n_roll:
        # Remove actual weapon from NPC inventory if they have one
        weapon_item = None
        if hasattr(npc, 'get_weapon'):
            weapon_item = npc.get_weapon()
        if weapon_item and hasattr(npc, 'inventory'):
            npc.inventory.remove(weapon_item)
            npc.equipped_weapon = None
            # Store the dropped weapon so the engine can place it on the ground
            npc._dropped_weapon = weapon_item
        npc._disarmed = True
        state.control = _clamp(state.control + 10)
        msg = (
            f"You grab {npc.name}'s wrist and twist hard. The {weapon_name} "
            f"clatters to the ground."
        )
        return msg, True   # grapple continues, NPC now unarmed
    else:
        state.control = _clamp(state.control - 5)
        msg = (
            f"You grab for {npc.name}'s weapon but they wrench it away from "
            f"your grip."
        )
        return msg, True


def _action_arm_lock(
    state: GrappleState, player: "Player", npc: "NPC", rng: "Random",
) -> Tuple[str, bool]:
    """Transition to arm lock.  CON damage per turn.  Control +15."""
    # Pick an arm to grab
    arm = rng.choice([BP.R_UPPER_ARM, BP.L_UPPER_ARM])
    arm_label = PART_DATA[arm]["label"]

    p_roll = _str_score(player) + _d20(rng)
    n_roll = _agi_score(npc) + _d20(rng)

    if p_roll >= n_roll:
        state.hold_type = "arm_lock"
        state.held_part = arm
        state.control = _clamp(state.control + _ARM_LOCK_CONTROL_BONUS)
        msg = (
            f"You seize {npc.name}'s {arm_label.lower()} and crank it behind "
            f"their back. You feel the joint straining. They grunt in pain."
        )
        return msg, True
    else:
        state.control = _clamp(state.control - 5)
        msg = (
            f"You reach for {npc.name}'s arm but they pull free before you "
            f"can lock the joint."
        )
        return msg, True


def _action_chokehold(
    state: GrappleState, player: "Player", npc: "NPC", rng: "Random",
) -> Tuple[str, bool]:
    """Transition to chokehold.  CON drain each turn (2 hp/turn via tick)."""
    p_roll = _str_score(player) + _d20(rng)
    n_roll = _str_score(npc) + _d20(rng)

    if p_roll >= n_roll:
        state.hold_type = "chokehold"
        state.held_part = BP.NECK
        state.control = _clamp(state.control + 10)
        msg = (
            f"You snake your arm around {npc.name}'s neck and squeeze. "
            f"Their breathing turns ragged."
        )
        return msg, True
    else:
        state.control = _clamp(state.control - 10)
        msg = (
            f"You try to get your arm around {npc.name}'s throat but they "
            f"tuck their chin and block you."
        )
        return msg, True


def _action_headbutt(
    state: GrappleState, player: "Player", npc: "NPC", rng: "Random",
) -> Tuple[str, bool]:
    """Quick STR-based strike.  3-8 damage to NPC HEAD.  Both take minor dmg."""
    dmg = rng.randint(_HEADBUTT_DMG_LO, _HEADBUTT_DMG_HI)
    # Strength modifier
    str_mod = (_str_score(player) - 10) // 3
    dmg = max(1, dmg + str_mod)

    # Apply damage to NPC head
    npc.wounds.apply_hit(dmg, DmgType.BLUNT, target_part=BP.HEAD)
    npc.health = max(0, npc.health - dmg)

    # Minor self-damage (you headbutt someone, your head hurts too)
    player.wounds.apply_hit(_HEADBUTT_SELF_DMG, DmgType.BLUNT,
                            target_part=BP.HEAD)

    if npc.health <= 0:
        npc.alive = False
        npc.combat_state = "dead"
        msg = (
            f"You slam your forehead into {npc.name}'s face with brutal "
            f"force. {dmg} damage. Their eyes roll back and they go limp. "
            f"{npc.name} is dead."
        )
        return msg, False
    else:
        msg = (
            f"You crack your forehead into {npc.name}'s nose. {dmg} damage. "
            f"Blood sprays. Your own skull rings from the impact."
        )
        return msg, True


# ============================================================================
#  3. NPC escape attempt
# ============================================================================

def npc_escape_attempt(
    state: GrappleState,
    player: "Player",
    npc: "NPC",
    rng: "Random",
) -> Tuple[str, bool]:
    """
    NPC tries to break free.  Called each NPC turn while grappled.

    Roll: NPC (AGI + STR) / 2 + d20  vs  player control score / 2 + d20.
    Higher control makes escape harder.

    Returns (message, escaped: bool).
    """
    npc_power = (_agi_score(npc) + _str_score(npc)) // 2 + _d20(rng)
    player_hold = state.control // 2 + _d20(rng)

    # Arm lock and chokehold are harder to escape
    if state.hold_type in ("arm_lock", "chokehold"):
        player_hold += 3

    if npc_power > player_hold:
        msg = (
            f"{npc.name} wrenches free of your {state.hold_type.replace('_', ' ')}!"
        )
        return msg, True
    else:
        # Failed escape costs NPC control ground
        state.control = _clamp(state.control + 3)
        msgs = [
            f"{npc.name} struggles but can't break your hold.",
            f"{npc.name} thrashes wildly. You tighten your grip.",
            f"{npc.name} tries to twist free. You wrench them back.",
            f"{npc.name} bucks against you. Your hold stays firm.",
        ]
        msg = rng.choice(msgs)
        return msg, False


# ============================================================================
#  4. Grapple tick (per-turn upkeep)
# ============================================================================

def grapple_tick(
    state: GrappleState,
    player: "Player",
    npc: "NPC",
) -> str:
    """
    Called each combat tick while the grapple is active.

    - Chokehold:  drain NPC health 2-3/tick, KO check.
    - Arm lock:   pain reduces NPC combat effectiveness.
    - Control drift: naturally moves toward 50 (neither side dominates forever).

    Returns a flavor message (may be empty string if nothing notable happens).
    """
    messages = []

    # -- Hold-type effects --------------------------------------------------

    if state.hold_type == "chokehold":
        # Deterministic 2-3 damage based on control level
        choke_dmg = _CHOKEHOLD_DMG_HI if state.control >= 60 else _CHOKEHOLD_DMG_LO
        npc.wounds.apply_hit(choke_dmg, DmgType.BLUNT, target_part=BP.NECK)
        npc.health = max(0, npc.health - choke_dmg)

        if npc.health < _CHOKEHOLD_KO_THRESHOLD:
            npc.combat_state = "unconscious"
            messages.append(
                f"{npc.name}'s struggles weaken. Their body goes limp. "
                f"They've passed out."
            )
        else:
            messages.append(
                f"{npc.name} gasps for air. Their face darkens. "
                f"({choke_dmg} damage)"
            )

    elif state.hold_type == "arm_lock":
        # Pain penalty — reduce NPC's effective combat stats
        # (flagged via combat_state so engine can apply penalty)
        if npc.combat_state not in ("dead", "unconscious", "surrendered"):
            npc.combat_state = "impaired"
        arm_label = PART_DATA.get(state.held_part, {}).get("label", "arm")
        messages.append(
            f"You torque {npc.name}'s {arm_label.lower()} further. "
            f"They hiss through clenched teeth."
        )

    # -- Control drift toward 50 -------------------------------------------

    if state.control > 50:
        state.control = max(50, state.control - _CONTROL_DRIFT_RATE)
    elif state.control < 50:
        state.control = min(50, state.control + _CONTROL_DRIFT_RATE)

    return " ".join(messages)
