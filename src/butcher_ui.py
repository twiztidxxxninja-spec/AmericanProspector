"""
src/butcher_ui.py

Butcher planning UI — interactive checklist for harvesting parts from a carcass.
Player toggles options with spacebar, sees running time/weight estimates,
then commits with ENTER.  Replaces the old fast/normal/extensive menu.

Organ and offal items added here for sausage, haggis, and stomach-cooking recipes.
"""

import math
import random
from dataclasses import dataclass, field
from typing import List, Tuple, Callable, Optional, TYPE_CHECKING

import tcod
import tcod.event

if TYPE_CHECKING:
    from src.wildlife_manager import WildlifeInstance
    from src.engine import Engine

# ---------------------------------------------------------------------------
# New item templates (organ_meat, offal, teeth_claws) — registered once
# ---------------------------------------------------------------------------

_NEW_ITEM_TEMPLATES = {
    "organ_meat": {
        "id": "organ_meat", "name": "Organ Meat", "weight": 1.0,
        "category": "food", "nutrition": 30.0,
        "description": "Heart, liver, and kidneys combined.  Very nutritious, "
                       "spoils fast.",
        "base_value": 0.08, "stackable": True,
        "perishable": True, "days_until_spoil": 2,
    },
    "offal": {
        "id": "offal", "name": "Offal", "weight": 1.0,
        "category": "food", "nutrition": 10.0,
        "description": "Intestines, stomach, and lungs.  Low nutrition raw but "
                       "used in sausage, haggis, and stomach-cooking.",
        "base_value": 0.03, "stackable": True,
        "perishable": True, "days_until_spoil": 1,
    },
    "teeth_claws": {
        "id": "teeth_claws", "name": "Teeth & Claws", "weight": 0.3,
        "category": "material",
        "description": "Predator teeth and claws.  Crafting material for "
                       "jewelry and decoration.",
        "base_value": 1.50, "stackable": True,
    },
}

_templates_registered = False


def _ensure_templates():
    """Lazily inject new item templates into ITEM_TEMPLATES if not present."""
    global _templates_registered
    if _templates_registered:
        return
    from src.items import ITEM_TEMPLATES
    for key, tmpl in _NEW_ITEM_TEMPLATES.items():
        if key not in ITEM_TEMPLATES:
            ITEM_TEMPLATES[key] = tmpl
    _templates_registered = True


# ---------------------------------------------------------------------------
# Butcher option definition
# ---------------------------------------------------------------------------

# Yield function signature:
#   (species_id, meat_yield_lb, size) -> list[(item_id, qty, weight_lb)]

@dataclass
class ButcherOption:
    id: str                 # "skin", "backstraps", "all_meat", ...
    label: str              # display name shown in UI
    base_time_min: int      # base time in minutes
    requires_tool: bool     # needs a knife / sharp tool
    # Which species IDs can use this option (None = all)
    species_filter: Optional[Callable[[str, str], bool]] = None
    # Yield function: (species_id, meat_yield_lb, size) -> [(item_id, qty, wt)]
    yield_fn: Optional[Callable] = None


# ---------------------------------------------------------------------------
# Yield helpers
# ---------------------------------------------------------------------------

# Mapping from species id -> specific pelt item (furbearers and others)
_PELT_MAP = {
    "beaver":            "beaver_pelt",
    "red_fox":           "fox_pelt",
    "gray_fox":          "fox_pelt",
    "gray_wolf":         "wolf_pelt",
    "coyote":            "coyote_pelt",
    "raccoon":           "raccoon_pelt",
    "bobcat":            "bobcat_pelt",
    "river_otter":       "otter_pelt",
    "mink":              "mink_pelt",
    "pine_marten":       "marten_pelt",
    "fisher":            "fisher_pelt",
    "wolverine":         "wolverine_pelt",
    "lynx":              "lynx_pelt",
    "muskrat":           "muskrat_pelt",
    "skunk":             "skunk_pelt",
    "opossum":           "raccoon_pelt",   # no dedicated pelt; reuse raccoon
    "grizzly_bear":      "bear_pelt",
    "black_bear":        "bear_pelt",
    "mountain_lion":     "cougar_pelt",
    "mule_deer":         "deer_pelt",
    "black_tailed_deer": "deer_pelt",
    "elk":               "elk_pelt",
    "moose":             "raw_hide",
    "buffalo":           "raw_hide",
    "pronghorn":         "raw_hide",
    "bighorn_sheep":     "raw_hide",
    "badger":            "raccoon_pelt",
}


def _yield_skin(sp_id, meat_yield_lb, size):
    """Skin / hide."""
    item_id = _PELT_MAP.get(sp_id, "raw_hide")
    if size == "small":
        item_id = _PELT_MAP.get(sp_id, "small_hide")
    return [(item_id, 1, None)]  # weight=None -> use template default


def _yield_backstraps(sp_id, meat_yield_lb, size):
    meat_lb = round(meat_yield_lb * 0.20, 1)
    return [("fresh_venison", 1, meat_lb)]


def _yield_all_meat(sp_id, meat_yield_lb, size):
    meat_lb = round(meat_yield_lb * 0.80, 1)
    return [("fresh_venison", 1, meat_lb)]


def _yield_brain(sp_id, meat_yield_lb, size):
    return [("brain", 1, None)]


def _yield_organs(sp_id, meat_yield_lb, size):
    """Heart, liver, kidneys — specific items."""
    results = [("liver", 1, None), ("heart", 1, None), ("kidneys", 1, None)]
    return results


def _yield_offal(sp_id, meat_yield_lb, size):
    """Intestines, stomach, lungs — specific items."""
    results = [("intestines", 1, None), ("stomach_lining", 1, None), ("lungs", 1, None)]
    return results


def _yield_bones(sp_id, meat_yield_lb, size):
    qty = min(8, 2 + int(meat_yield_lb / 50))
    return [("animal_bones", qty, None)]


def _yield_sinew(sp_id, meat_yield_lb, size):
    qty = min(4, 1 + int(meat_yield_lb / 80))
    return [("sinew", qty, None)]


def _yield_tallow(sp_id, meat_yield_lb, size):
    qty = min(5, 1 + int(meat_yield_lb / 60))
    return [("tallow", qty, None)]


def _yield_antlers(sp_id, meat_yield_lb, size):
    return [("antlers", 1, None)]


def _yield_horns(sp_id, meat_yield_lb, size):
    return [("animal_horn", 1, None)]


def _yield_teeth_claws(sp_id, meat_yield_lb, size):
    return [("teeth_claws", 1, None)]


# ---------------------------------------------------------------------------
# Species filters
# ---------------------------------------------------------------------------

_ANTLER_SPECIES = frozenset(["mule_deer", "black_tailed_deer", "elk", "moose"])
_HORN_SPECIES = frozenset(["buffalo", "bighorn_sheep"])
_PREDATOR_SPECIES = frozenset([
    "grizzly_bear", "black_bear", "mountain_lion", "gray_wolf", "wolverine",
])
_SMALL_SIZE = frozenset(["small"])


def _filter_antlers(sp_id, size):
    return sp_id in _ANTLER_SPECIES


def _filter_horns(sp_id, size):
    return sp_id in _HORN_SPECIES


def _filter_teeth_claws(sp_id, size):
    return sp_id in _PREDATOR_SPECIES


def _filter_not_small(sp_id, size):
    return size not in _SMALL_SIZE


# ---------------------------------------------------------------------------
# Master option list
# ---------------------------------------------------------------------------

BUTCHER_OPTIONS: List[ButcherOption] = [
    ButcherOption("skin",        "Skin hide",      15, True,  None,                  _yield_skin),
    ButcherOption("backstraps",  "Backstraps",       5, True,  None,                  _yield_backstraps),
    ButcherOption("all_meat",    "All meat",        30, True,  None,                  _yield_all_meat),
    ButcherOption("brain",       "Brain",            3, True,  None,                  _yield_brain),
    ButcherOption("organs",      "Organs (heart/liver/kidneys)", 5, True,  None,        _yield_organs),
    ButcherOption("offal",       "Guts (intestines/stomach/lungs)", 8, True,  _filter_not_small, _yield_offal),
    ButcherOption("bones",       "Bones",           10, True,  None,                  _yield_bones),
    ButcherOption("sinew",       "Sinew",            5, True,  None,                  _yield_sinew),
    ButcherOption("tallow",      "Tallow",          10, True,  None,                  _yield_tallow),
    ButcherOption("antlers",     "Antlers",          3, True,  _filter_antlers,       _yield_antlers),
    ButcherOption("horns",       "Horns",            3, True,  _filter_horns,         _yield_horns),
    ButcherOption("teeth_claws", "Teeth & Claws",    2, True,  _filter_teeth_claws,   _yield_teeth_claws),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _available_options(species_id: str, size: str) -> List[ButcherOption]:
    """Return only options valid for this species."""
    out = []
    for opt in BUTCHER_OPTIONS:
        if opt.species_filter is not None and not opt.species_filter(species_id, size):
            continue
        out.append(opt)
    return out


def _compute_yields(opt: ButcherOption, species_id: str,
                    meat_yield_lb: float, size: str,
                    skill_level: int) -> List[Tuple[str, int, float]]:
    """Compute (item_id, qty, weight_lb) list for one option.
    skill_level boosts meat yields."""
    from src.items import ITEM_TEMPLATES
    raw = opt.yield_fn(species_id, meat_yield_lb, size)
    results = []
    skill_mult = 1.0 + skill_level * 0.03
    for item_id, qty, wt in raw:
        tmpl = ITEM_TEMPLATES.get(item_id)
        if tmpl is None:
            continue
        if wt is None:
            wt = tmpl.get("weight", 1.0)
        # Skill bonus on meat yields
        if item_id == "fresh_venison":
            wt = round(wt * skill_mult, 1)
        results.append((item_id, qty, wt))
    return results


def _effective_time(base_min: int, skill_level: int) -> int:
    """Apply butchering skill time reduction."""
    factor = max(0.5, 1.0 - skill_level * 0.05)
    return max(1, round(base_min * factor))


def _yield_summary(yields: List[Tuple[str, int, float]]) -> str:
    """Short description for the right column."""
    from src.items import ITEM_TEMPLATES
    parts = []
    for item_id, qty, wt in yields:
        tmpl = ITEM_TEMPLATES.get(item_id, {})
        name = tmpl.get("name", item_id)
        if item_id == "fresh_venison":
            parts.append(f"{wt:.0f} lb meat")
        elif item_id in ("organ_meat", "offal"):
            parts.append(f"{wt:.0f} lb {name.lower()}")
        elif qty > 1:
            parts.append(f"{qty}x {name}")
        else:
            parts.append(f"1x {name}")
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------

def open_butcher_ui(engine: "Engine", console, ctx,
                    animal: "WildlifeInstance") -> List[str]:
    """
    Interactive butcher planning UI.

    Returns list of log-message strings (empty if cancelled).
    Creates items, marks animal butchered, advances time.
    """
    _ensure_templates()

    from src.items import make_item, ITEM_TEMPLATES
    from src.butcher import has_sharp_tool

    sp = animal.species
    species_id = sp.id
    size = sp.size
    meat_yield_lb = sp.meat_yield_lb

    player = engine.player
    skill = player.skills.get("butchering", 0)
    has_tool = has_sharp_tool(player)

    options = _available_options(species_id, size)
    n_opts = len(options)
    if n_opts == 0:
        return ["Nothing to harvest from this animal."]

    # State: which options are checked, and cursor position
    checked = [False] * n_opts
    # Default: skin + backstraps checked
    for i, opt in enumerate(options):
        if opt.id in ("skin", "backstraps"):
            checked[i] = True
    cursor = 0

    # Mutual-exclusion pairs
    _MUTEX = {"backstraps": "all_meat", "all_meat": "backstraps"}
    # Build id -> index map
    id_to_idx = {opt.id: i for i, opt in enumerate(options)}

    # Pre-compute yields for all options (doesn't change during UI)
    all_yields = []
    for opt in options:
        all_yields.append(_compute_yields(opt, species_id, meat_yield_lb,
                                          size, skill))

    # ── UI constants ──────────────────────────────────────────────────────
    W = 52
    H = n_opts + 14   # header + options + footer
    BG = (15, 12, 10)
    FG = (200, 190, 160)
    FG_DIM = (100, 90, 70)
    FG_BRIGHT = (255, 255, 255)
    FG_TITLE = (255, 220, 140)
    FG_OK = (100, 200, 100)
    FG_WARN = (200, 80, 80)
    SEL_BG = (40, 35, 25)

    while True:
        X = (console.width - W) // 2
        Y = max(1, (console.height - H) // 2)

        # ── Compute totals ────────────────────────────────────────
        total_time = 0
        total_weight = 0.0
        for i, opt in enumerate(options):
            if checked[i]:
                total_time += _effective_time(opt.base_time_min, skill)
                for _, qty, wt in all_yields[i]:
                    total_weight += wt * qty

        # ── Draw background ───────────────────────────────────────
        for sy in range(Y, Y + H):
            console.print(X, sy, " " * W, fg=FG, bg=BG)

        # Borders (top / bottom)
        bar = "\u2501" * (W - 2)
        console.print(X + 1, Y + 3, bar, fg=FG_DIM, bg=BG)
        console.print(X + 1, Y + n_opts + 6, bar, fg=FG_DIM, bg=BG)
        console.print(X + 1, Y + n_opts + 10, bar, fg=FG_DIM, bg=BG)

        # Title
        title = f"BUTCHER \u2014 {sp.display_name} ({meat_yield_lb:.0f} lb)"
        console.print(X + (W - len(title)) // 2, Y + 1, title,
                      fg=FG_TITLE, bg=BG)

        # Tool line
        if has_tool:
            console.print(X + 2, Y + 2, "Requires: sharp tool  \u2713",
                          fg=FG_OK, bg=BG)
        else:
            console.print(X + 2, Y + 2, "Requires: sharp tool  X  (none!)",
                          fg=FG_WARN, bg=BG)

        # Controls hint
        console.print(X + 2, Y + 4,
                      "[Space] toggle  [Enter] commit  [Esc] cancel",
                      fg=FG_DIM, bg=BG)

        # ── Option rows ──────────────────────────────────────────
        list_y = Y + 6
        for i, opt in enumerate(options):
            row_y = list_y + i
            is_sel = (i == cursor)
            bg = SEL_BG if is_sel else BG
            fg = FG_BRIGHT if is_sel else FG

            check = "\u2611" if checked[i] else "\u2610"

            label = opt.label
            t = _effective_time(opt.base_time_min, skill)
            time_str = f"~{t} min"
            yld_str = _yield_summary(all_yields[i])

            # Layout: checkbox + label (left), time (middle), yield (right)
            left = f" {check} {label}"
            # Pad label to fixed column
            left = left.ljust(22)
            mid = time_str.rjust(8)
            right = yld_str

            # Truncate right if too wide
            avail = W - 22 - 8 - 4
            if len(right) > avail:
                right = right[:avail - 1] + "\u2026"

            line = f"{left}{mid}  {right}"
            line = line[:W - 2]
            console.print(X + 1, row_y, line.ljust(W - 2), fg=fg, bg=bg)

        # ── Footer: totals ────────────────────────────────────────
        foot_y = Y + n_opts + 7
        console.print(X + 2, foot_y,
                      f"Est. time: {total_time} min  |  "
                      f"Est. weight: {total_weight:.1f} lb",
                      fg=FG, bg=BG)

        if skill > 0:
            pct = round((1.0 - max(0.5, 1.0 - skill * 0.05)) * 100)
            console.print(X + 2, foot_y + 1,
                          f"Skill: Survival {skill} (-{pct}% time)",
                          fg=(180, 200, 120), bg=BG)
        else:
            console.print(X + 2, foot_y + 1,
                          "Skill: Survival 0 (no bonus)",
                          fg=FG_DIM, bg=BG)

        # Carry capacity warning
        cap = player.carry_capacity
        cur = player.carried_weight
        if cur + total_weight > cap:
            overflow = cur + total_weight - cap
            console.print(X + 2, foot_y + 2,
                          f"OVER CAPACITY by {overflow:.1f} lb! "
                          f"Excess left on ground.",
                          fg=FG_WARN, bg=BG)

        ctx.present(console)

        # ── Input ─────────────────────────────────────────────────
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                raise SystemExit()

            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                K = tcod.event.KeySym

                if sym == K.ESCAPE:
                    return []

                # Navigation
                if sym in (K.UP, K.KP_8, K.k):
                    cursor = max(0, cursor - 1)
                    break
                if sym in (K.DOWN, K.KP_2, K.j):
                    cursor = min(n_opts - 1, cursor + 1)
                    break

                # Toggle
                if sym == K.SPACE:
                    if not has_tool:
                        # Can't toggle anything without a blade
                        break
                    idx = cursor
                    checked[idx] = not checked[idx]
                    # Mutual exclusion: backstraps vs all_meat
                    opt_id = options[idx].id
                    if checked[idx] and opt_id in _MUTEX:
                        other_id = _MUTEX[opt_id]
                        if other_id in id_to_idx:
                            checked[id_to_idx[other_id]] = False
                    break

                # Commit
                if sym in (K.RETURN, K.KP_ENTER):
                    if not has_tool:
                        break
                    if not any(checked):
                        break  # nothing selected
                    return _commit_butcher(
                        engine, animal, options, checked, all_yields,
                        skill, total_time)


# ---------------------------------------------------------------------------
# Commit: create items, mark animal, advance time
# ---------------------------------------------------------------------------

def _commit_butcher(engine: "Engine",
                    animal: "WildlifeInstance",
                    options: List[ButcherOption],
                    checked: List[bool],
                    all_yields: List[List[Tuple[str, int, float]]],
                    skill: int,
                    total_time_min: int) -> List[str]:
    """Create the selected items, place in inventory or on ground."""
    from src.items import make_item

    player = engine.player
    lmap = engine.current_local
    sp = animal.species

    items_out = []
    animal_name = sp.display_name

    for i, opt in enumerate(options):
        if not checked[i]:
            continue
        for item_id, qty, wt in all_yields[i]:
            for _ in range(qty):
                it = make_item(item_id)
                # Name prefix with animal species
                if animal_name.lower() not in it.name.lower():
                    it.name = f"{animal_name} {it.name}"
                it.weight = round(wt, 2)
                items_out.append(it)

    # Place items: in inventory if capacity allows, else on ground
    cap = player.carry_capacity
    cur = player.carried_weight
    inv_items = []
    ground_items = []

    for it in items_out:
        if cur + it.weight <= cap:
            inv_items.append(it)
            cur += it.weight
        else:
            ground_items.append(it)

    player.inventory.extend(inv_items)
    player.recalc_weight()

    if ground_items:
        tile = lmap.tile_at(animal.local_x, animal.local_y)
        tile.ground_items.extend(ground_items)
        lmap.mark_dirty(animal.local_x, animal.local_y)

    # Mark animal as butchered
    animal.state = "butchered"
    animal.butchered = True

    # Advance time
    engine.advance_time(total_time_min)

    # Skill XP: base 2 + 0.5 per checked option
    xp = 2.0 + sum(0.5 for c in checked if c)
    player.gain_skill_xp("butchering", xp)

    # Build summary messages
    total_weight = sum(it.weight for it in items_out)
    msgs = [
        f"You butcher the {animal_name} "
        f"({len(items_out)} items, {total_weight:.1f} lb total, "
        f"{total_time_min} min)."
    ]

    meat_items = [it for it in items_out if it.category == "food"]
    mat_items = [it for it in items_out if it.category != "food"]

    if meat_items:
        names = ", ".join(dict.fromkeys(it.name for it in meat_items[:4]))
        if len(meat_items) > 4:
            names += f" + {len(meat_items) - 4} more"
        msgs.append(f"  Meat: {names}.")

    if mat_items:
        names = ", ".join(dict.fromkeys(it.name for it in mat_items[:4]))
        if len(mat_items) > 4:
            names += f" + {len(mat_items) - 4} more"
        msgs.append(f"  Materials: {names}.")

    if inv_items and not ground_items:
        msgs.append("All items added to inventory.")
    elif ground_items and inv_items:
        msgs.append(
            f"{len(inv_items)} items to inventory; "
            f"{len(ground_items)} left on ground (over capacity).")
    elif ground_items:
        msgs.append("Items left on the ground. Walk over them to pick up.")

    return msgs
