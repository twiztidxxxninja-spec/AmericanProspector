"""
src/movement.py

Swimming and climbing checks for the player.

These are standalone functions so they can be called from the engine
without modifying local_map.py.  They read player attributes, survival
stats, and inventory to resolve success/failure and side effects.
"""

from typing import List, Tuple


# Deep water terrain constant (to be added to LocalTerrain separately).
DEEP_WATER = 80


# ── Swimming ────────────────────────────────────────────────────────────

def swim_check(player, rng) -> Tuple[bool, str]:
    """Roll a swim check for *player*.

    Formula
    -------
    Roll  = d20 + CON/3 + survival_skill/2
    DC    = 12 + encumbrance_penalty

    Encumbrance penalty: +1 DC per 20 lbs over 50% of carry capacity.

    Returns
    -------
    (success, message) : (bool, str)
    """
    con = player.attributes.get("constitution", 10)
    survival_skill = player.skills.get("survival", 0)

    roll = rng.randint(1, 20) + con // 3 + survival_skill // 2

    # Encumbrance penalty
    half_cap = player.carry_capacity * 0.5
    excess = max(0.0, player.carried_weight - half_cap)
    enc_penalty = int(excess // 20)

    dc = 12 + enc_penalty
    name = getattr(player, "name", "You")

    if roll >= dc:
        msg = f"{name} swims across.  (roll {roll} vs DC {dc})"
        return (True, msg)
    else:
        msg = f"{name} struggles in the current!  (roll {roll} vs DC {dc})"
        return (False, msg)


def swim_tick(player, minutes: float) -> List[str]:
    """Apply per-tick effects while *player* is swimming.

    Fatigue drains at 5x the normal rate.  If fatigue drops to 5 or
    below, a drowning check is made each tick.

    Parameters
    ----------
    player : Player
        Modified in-place (fatigue, health).
    minutes : float
        In-game minutes elapsed this tick.

    Returns
    -------
    List of warning/damage messages (may be empty).
    """
    import random as _random  # fallback; callers may pass their own rng

    msgs: List[str] = []
    hours = minutes / 60.0

    # Accelerated fatigue drain (5x normal)
    drain = 5.0 * hours
    player.survival.fatigue = max(0.0, player.survival.fatigue - drain)

    if player.survival.fatigue <= 20:
        msgs.append("You are exhausted from swimming!")

    # Drowning risk when fatigue is critically low
    if player.survival.fatigue <= 5:
        con = player.attributes.get("constitution", 10)
        roll = _random.randint(1, 20) + con // 3
        dc = 15
        if roll < dc:
            damage = 5.0
            player.survival.health = max(0.0,
                                         player.survival.health - damage)
            msgs.append(
                f"You swallow water and choke!  "
                f"(roll {roll} vs DC {dc}, -{damage:.0f} health)"
            )
        else:
            msgs.append(
                "You gasp for air but keep your head above water."
            )

    return msgs


def can_swim(player) -> bool:
    """Quick check: does *player* have enough fatigue and health to swim?

    Returns ``False`` if the player is too exhausted or too wounded to
    attempt a water crossing.
    """
    if player.survival.fatigue <= 3:
        return False
    if player.survival.health <= 5:
        return False
    return True


# ── Climbing ────────────────────────────────────────────────────────────

def _has_rope(player) -> bool:
    """Return True if the player is carrying any kind of rope."""
    for item in player.inventory:
        item_name = ""
        if isinstance(item, str):
            item_name = item
        elif hasattr(item, "name"):
            item_name = item.name
        elif hasattr(item, "item_id"):
            item_name = item.item_id
        if "rope" in item_name.lower():
            return True
    return False


def climb_check(
    player, z_diff: int, rng
) -> Tuple[bool, int, str]:
    """Roll a climb check for *player* ascending/descending *z_diff* levels.

    Formula
    -------
    Roll  = d20 + STR/3 + AGI/3
    DC    = 10 + z_diff * 3   (rope in inventory: -5 DC)

    On failure the player falls and takes z_diff * d6 damage.

    Returns
    -------
    (success, fall_damage, message) : (bool, int, str)
    """
    str_attr = player.attributes.get("strength", 10)
    agi_attr = player.attributes.get("agility", 10)

    roll = rng.randint(1, 20) + str_attr // 3 + agi_attr // 3

    dc = 10 + z_diff * 3
    if _has_rope(player):
        dc = max(1, dc - 5)

    name = getattr(player, "name", "You")

    if roll >= dc:
        msg = (f"{name} climbs the {z_diff}-level face.  "
               f"(roll {roll} vs DC {dc})")
        return (True, 0, msg)
    else:
        # Fall damage: z_diff * d6
        fall_damage = sum(rng.randint(1, 6) for _ in range(z_diff))
        msg = (f"{name} slips and falls {z_diff} level(s)!  "
               f"(roll {roll} vs DC {dc}, {fall_damage} damage)")
        return (False, fall_damage, msg)
