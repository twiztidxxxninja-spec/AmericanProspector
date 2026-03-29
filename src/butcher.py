"""
src/butcher.py

Butchering system for American Prospector.
Anatomy organized by animal size class; species-specific extras added on top.
Three methods (fast/normal/extensive) are cumulative — each adds to the previous.

Requires a sharp tool (knife, axe, hatchet).
Time costs: Fast 15 min, Normal 45 min, Extensive 90 min.
"""

import random
from typing import List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.wildlife_manager import WildlifeInstance
    from src.local_map import LocalMap

# ── Method constants ─────────────────────────────────────────────────────────

FAST      = "fast"
NORMAL    = "normal"
EXTENSIVE = "extensive"

TIME_COST = {FAST: 15, NORMAL: 45, EXTENSIVE: 90}

METHODS = [
    (FAST,      "Fast   (~15 min) — backstraps, tongue, prime organs only"),
    (NORMAL,    "Normal (~45 min) — hide, major cuts, all organs"),
    (EXTENSIVE, "Full   (~90 min) — everything: bones, fat, stomach, sinew, head"),
]

# ── Part entry format ────────────────────────────────────────────────────────
# (item_id, display_name_override, qty_min, qty_max, weight_lb_each, nutrition_override)
# nutrition_override=None → use item default from ITEM_DB
# weight_lb_each is the template weight; scaled by animal size ratio at generation time

# ── Reference meat yields for scaling ───────────────────────────────────────
_REF_YIELD = {"very_large": 400.0, "large": 200.0, "medium": 80.0, "small": 8.0}


# ── Core anatomy by size class ───────────────────────────────────────────────

_BASE_ANATOMY = {
    "very_large": {
        FAST: [
            ("backstraps",       "Backstraps",    2, 2,  8.0,  55.0),
            ("tongue",           "Tongue",        1, 1,  3.0,  30.0),
        ],
        NORMAL: [
            ("raw_hide",         "Large Hide",    1, 1, 40.0,  None),
            ("hindquarter_meat", "Hindquarter",   2, 2, 28.0,  40.0),
            ("shoulder_meat",    "Shoulder",      2, 2, 20.0,  35.0),
            ("rib_meat",         "Ribs",          2, 2, 10.0,  30.0),
            ("heart",            "Heart",         1, 1,  2.0,  35.0),
            ("liver",            "Liver",         1, 1,  8.0,  45.0),
            ("kidneys",          "Kidneys",       2, 2,  0.5,  20.0),
        ],
        EXTENSIVE: [
            ("neck_meat",        "Neck Meat",     1, 1,  5.0,  25.0),
            ("tallow",           "Tallow",        3, 5,  2.0,  None),
            ("stomach_sac",      "Stomach",       1, 1,  0.5,  None),
            ("intestines",       "Intestines",    1, 1,  1.5,  None),
            ("animal_bones",     "Bones",         6,10,  2.5,  None),
            ("sinew",            "Sinew",         3, 5,  0.10, None),
            ("hooves",           "Hooves",        4, 4,  0.8,  None),
            ("head",             "Head",          1, 1,  8.0,  None),
            ("brain",            "Brain",         1, 1,  0.5,  None),
        ],
    },
    "large": {
        FAST: [
            ("backstraps",       "Backstraps",    2, 2,  4.0,  50.0),
            ("tongue",           "Tongue",        1, 1,  1.5,  25.0),
        ],
        NORMAL: [
            ("raw_hide",         "Large Hide",    1, 1, 20.0,  None),
            ("hindquarter_meat", "Hindquarter",   2, 2, 14.0,  38.0),
            ("shoulder_meat",    "Shoulder",      2, 2,  9.0,  32.0),
            ("rib_meat",         "Ribs",          2, 2,  5.0,  28.0),
            ("heart",            "Heart",         1, 1,  1.0,  35.0),
            ("liver",            "Liver",         1, 1,  4.0,  42.0),
            ("kidneys",          "Kidneys",       2, 2,  0.3,  18.0),
        ],
        EXTENSIVE: [
            ("neck_meat",        "Neck Meat",     1, 1,  2.5,  22.0),
            ("tallow",           "Tallow",        2, 3,  1.5,  None),
            ("stomach_sac",      "Stomach",       1, 1,  0.4,  None),
            ("intestines",       "Intestines",    1, 1,  1.0,  None),
            ("animal_bones",     "Bones",         4, 6,  2.0,  None),
            ("sinew",            "Sinew",         2, 3,  0.10, None),
            ("hooves",           "Hooves",        4, 4,  0.5,  None),
            ("head",             "Head",          1, 1,  5.0,  None),
        ],
    },
    "medium": {
        FAST: [
            ("backstraps",       "Backstraps",    2, 2,  1.5,  45.0),
            ("tongue",           "Tongue",        1, 1,  0.5,  20.0),
        ],
        NORMAL: [
            ("raw_hide",         "Medium Hide",   1, 1,  8.0,  None),
            ("hindquarter_meat", "Hindquarter",   2, 2,  5.0,  35.0),
            ("shoulder_meat",    "Shoulder",      2, 2,  3.0,  30.0),
            ("rib_meat",         "Ribs",          2, 2,  2.0,  25.0),
            ("heart",            "Heart",         1, 1,  0.4,  32.0),
            ("liver",            "Liver",         1, 1,  1.5,  40.0),
            ("kidneys",          "Kidneys",       2, 2,  0.15, 15.0),
        ],
        EXTENSIVE: [
            ("neck_meat",        "Neck Meat",     1, 1,  1.0,  20.0),
            ("tallow",           "Tallow",        1, 2,  0.5,  None),
            ("stomach_sac",      "Stomach",       1, 1,  0.2,  None),
            ("intestines",       "Intestines",    1, 1,  0.3,  None),
            ("animal_bones",     "Bones",         2, 4,  1.0,  None),
            ("sinew",            "Sinew",         1, 2,  0.05, None),
            ("hooves",           "Hooves",        4, 4,  0.2,  None),
            ("head",             "Head",          1, 1,  2.0,  None),
        ],
    },
    "small": {
        FAST: [
            ("backstraps",       "Loin",          1, 1,  0.3,  30.0),
        ],
        NORMAL: [
            ("small_hide",       "Small Hide",    1, 1,  1.0,  None),
            ("shoulder_meat",    "Meat",          1, 2,  0.4,  20.0),
            ("heart",            "Heart",         1, 1,  0.05, 18.0),
            ("liver",            "Liver",         1, 1,  0.2,  28.0),
        ],
        EXTENSIVE: [
            ("animal_bones",     "Bones",         1, 2,  0.3,  None),
            ("intestines",       "Intestines",    1, 1,  0.05, None),
            ("sinew",            "Sinew",         0, 1,  0.02, None),
        ],
    },
}

# ── Species-specific extras (added on top of base anatomy) ───────────────────
# key = WildlifeSpecies.id string

_SPECIES_EXTRAS = {
    "grizzly_bear": {
        NORMAL:    [("bear_claws",       "Bear Claws",      10,10, 0.05, None)],
        EXTENSIVE: [("bear_fat",         "Bear Fat",         3, 5, 1.5,  None),
                    ("bear_gallbladder", "Bear Gallbladder", 1, 1, 0.05, None)],
    },
    "black_bear": {
        NORMAL:    [("bear_claws",       "Bear Claws",      10,10, 0.05, None)],
        EXTENSIVE: [("bear_fat",         "Bear Fat",         2, 4, 1.5,  None),
                    ("bear_gallbladder", "Bear Gallbladder", 1, 1, 0.05, None)],
    },
    "elk": {
        NORMAL:    [("antlers",          "Elk Antlers",      1, 1, 8.0,  None)],
    },
    "mule_deer": {
        NORMAL:    [("antlers",          "Deer Antlers",     1, 1, 1.5,  None)],
    },
    "black_tailed_deer": {
        NORMAL:    [("antlers",          "Deer Antlers",     1, 1, 1.2,  None)],
    },
    "bighorn_sheep": {
        NORMAL:    [("animal_horn",      "Bighorn Horns",    2, 2, 3.0,  None)],
    },
    "moose": {
        NORMAL:    [("antlers",          "Moose Antlers",    1, 1,25.0,  None)],
    },
    "buffalo": {
        NORMAL:    [("animal_horn",      "Bison Horns",      2, 2, 2.0,  None)],
        EXTENSIVE: [("sinew",            "Sinew",            3, 5, 0.10, None)],
    },
    "beaver": {
        NORMAL:    [("castoreum",        "Castoreum",        1, 1, 0.05, None)],
    },
    # Snakes and birds override base anatomy entirely
    "rattlesnake": {
        FAST:      [("snake_meat",       "Snake Meat",       1, 1, 0.3,  18.0)],
        NORMAL:    [("small_hide",       "Rattlesnake Hide", 1, 1, 0.1,  None),
                    ("rattlesnake_rattle","Rattlesnake Rattle",1,1,0.01, None)],
        EXTENSIVE: [],
    },
    "wild_turkey": {
        FAST:      [("breast_meat",      "Breast Meat",      2, 2, 0.8,  38.0)],
        NORMAL:    [("bird_leg",         "Turkey Leg",       2, 2, 0.4,  22.0),
                    ("bird_feathers",    "Feathers",        15,25, 0.01, None)],
        EXTENSIVE: [("giblets",          "Giblets",          1, 1, 0.2,  22.0)],
    },
    "bald_eagle": {
        FAST:      [],
        NORMAL:    [("bird_feathers",    "Eagle Feathers",   5,10, 0.02, None)],
        EXTENSIVE: [],
    },
    "mountain_lion": {
        NORMAL:    [("small_hide",       "Cougar Pelt",      1, 1,10.0,  None)],
    },
    "gray_wolf": {
        NORMAL:    [("small_hide",       "Wolf Pelt",        1, 1, 8.0,  None)],
    },
}

# Species that use overrides instead of their base anatomy
_OVERRIDE_SPECIES = frozenset(["rattlesnake", "wild_turkey", "bald_eagle"])


# ── Main butcher function ────────────────────────────────────────────────────

def butcher(animal: "WildlifeInstance", method: str,
            lmap: "LocalMap", rng: random.Random) -> Tuple[List, List[str]]:
    """
    Butcher a downed/dead animal.
    Returns (list_of_items, list_of_messages).
    Items are placed on the animal's tile in lmap.
    The animal's state is set to "butchered".
    """
    from src.items import make_item, ITEM_TEMPLATES as ITEM_DB

    sp_id  = animal.species.id
    size   = animal.species.size
    m_yield = animal.species.meat_yield_lb

    # Scale factor vs reference animal of this size
    ref    = _REF_YIELD.get(size, 80.0)
    scale  = m_yield / ref

    # Build part list for this method (cumulative)
    all_parts: List[Tuple] = []

    # Species override (snakes, birds) ignore base anatomy
    if sp_id in _OVERRIDE_SPECIES:
        extras = _SPECIES_EXTRAS.get(sp_id, {})
        for m in [FAST, NORMAL, EXTENSIVE]:
            if m in extras:
                all_parts += extras[m]
            if m == method:
                break
    else:
        # Base anatomy
        base = _BASE_ANATOMY.get(size, _BASE_ANATOMY["small"])
        for m in [FAST, NORMAL, EXTENSIVE]:
            all_parts += base.get(m, [])
            if m == method:
                break
        # Species extras (on top)
        extras = _SPECIES_EXTRAS.get(sp_id, {})
        for m in [FAST, NORMAL, EXTENSIVE]:
            all_parts += extras.get(m, [])
            if m == method:
                break

    # Generate actual items
    items_out = []
    for (item_id, display_name, qty_min, qty_max, w_each, nutrition_ov) in all_parts:
        if item_id not in ITEM_DB:
            continue
        qty = rng.randint(qty_min, qty_max)
        if qty == 0:
            continue

        for _ in range(qty):
            it = make_item(item_id)
            # Prefix with species name unless the display_name already contains it
            animal_name = animal.species.display_name
            if animal_name.lower() in display_name.lower():
                it.name = display_name
            else:
                it.name = f"{animal_name} {display_name}"

            # Scale weight by animal size ratio
            it.weight = round(w_each * scale, 2)

            # Override nutrition if specified
            if nutrition_ov is not None:
                it.nutrition = nutrition_ov

            items_out.append(it)

    # Place on tile
    tile = lmap.tile_at(animal.local_x, animal.local_y)
    tile.ground_items.extend(items_out)

    # Mark as butchered
    animal.state = "butchered"
    animal.butchered = True

    # Build summary message
    meat_items = [i for i in items_out if i.category == "food"]
    mat_items  = [i for i in items_out if i.category != "food"]
    total_weight = sum(i.weight for i in items_out)

    msgs = [
        f"You butcher the {animal.species.display_name} "
        f"({len(items_out)} items, {total_weight:.1f} lb total)."
    ]
    if meat_items:
        names = ", ".join(dict.fromkeys(i.name for i in meat_items[:4]))
        if len(meat_items) > 4:
            names += f" + {len(meat_items)-4} more"
        msgs.append(f"  Meat: {names}.")
    if mat_items:
        names = ", ".join(dict.fromkeys(i.name for i in mat_items[:3]))
        if len(mat_items) > 3:
            names += f" + {len(mat_items)-3} more"
        msgs.append(f"  Materials: {names}.")
    msgs.append("Items left on the ground. Walk over them to pick up.")

    return items_out, msgs


def has_sharp_tool(player) -> bool:
    """Returns True if player has a knife, axe, or hatchet in inventory or hands."""
    SHARP_TAGS = {"sharp", "butcher", "chop"}
    SHARP_NAMES = {"knife", "axe", "hatchet", "cleaver", "blade"}
    for item in player.inventory:
        tags = set(getattr(item, "tool_tags", []))
        if tags & SHARP_TAGS:
            return True
        if any(s in item.name.lower() for s in SHARP_NAMES):
            return True
    return False
