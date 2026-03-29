"""
src/char_create.py

Character creation flow: Name → Era → Background → Attributes → Confirm.
Returns a dict of choices that Engine.run() applies to the player before
the main game loop starts.
"""

import tcod
import tcod.event
import tcod.console
from typing import Optional

from src.constants import SCREEN_WIDTH, SCREEN_HEIGHT

# ── Palette ────────────────────────────────────────────────────────────────────

BLACK  = (  0,   0,   0)
PAPER  = (200, 190, 170)   # aged-paper text
GOLD   = (212, 175,  55)   # title gold
GOLD2  = (160, 120,  30)   # dimmer gold
CYAN   = ( 80, 200, 200)   # selection
WHITE  = (255, 255, 255)
GREY   = (120, 120, 120)
DGREY  = ( 50,  50,  50)
GREEN  = ( 80, 180,  80)
RED    = (220,  60,  60)
AMBER  = (200, 140,  40)
BG     = (  8,   6,   4)   # near-black parchment background
BG_SEL = ( 25,  20,  10)   # selection row bg
BG_BOX = ( 12,  10,   8)   # box interior

ATTR_SHORT = {
    "strength":     "STR",
    "agility":      "AGI",
    "intelligence": "INT",
    "wisdom":       "WIS",
    "charisma":     "CHA",
    "constitution": "CON",
}

ATTR_ORDER = ["strength", "agility", "intelligence",
              "wisdom", "charisma", "constitution"]

ATTR_DESC = {
    "strength":     "Carry weight, melee damage, mining stamina.",
    "agility":      "Dodge, throwing accuracy, movement.",
    "intelligence": "Skill learning speed, reading, chemistry.",
    "wisdom":       "Geology intuition, reading terrain, NPC judgment.",
    "charisma":     "Trading prices, persuasion, reputation gains.",
    "constitution": "Max health, disease resistance, cold tolerance.",
}


# ── Era data ──────────────────────────────────────────────────────────────────

ERAS = [
    {
        "id":      "gold_rush",
        "name":    "1849 — California Gold Rush",
        "year":    1849,
        "month":   4,
        "region":  "Northern California",
        "world_x": 95, "world_y": 165,   # Sacramento
        "cash":    50.0,
        "desc": [
            "The hills are crawling with men and rumors.",
            "No regulations. No law west of Missouri.",
            "River bars and gold pans; everything is possible.",
            "",
            "Placer gold is king. Lode mining is primitive.",
            "Dynamite does not yet exist. Railroads stop at",
            "the Missouri River. The wilderness is vast.",
        ],
    },
    {
        "id":      "industrial",
        "name":    "1872 — Industrial Mining",
        "year":    1872,
        "month":   5,
        "region":  "Nevada / Colorado",
        "world_x": 113, "world_y": 160,  # Virginia City, NV area
        "cash":    120.0,
        "desc": [
            "The easy placer gold is largely played out.",
            "Dynamite, stamp mills, and the General Mining",
            "Act of 1872 define the era. Lode mining reigns.",
            "",
            "The transcontinental railroad opened in 1869.",
            "Comstock silver still flowing. Deadwood stirs.",
            "Corporate claim consolidation squeezes the solo",
            "prospector — but fortunes still exist.",
        ],
    },
    {
        "id":      "petroleum",
        "name":    "1901 — Petroleum Age",
        "year":    1901,
        "month":   1,
        "region":  "Texas / Oklahoma",
        "world_x": 310, "world_y": 220,  # Beaumont / Tulsa area
        "cash":    200.0,
        "desc": [
            "Spindletop blew in January 1901. Everything",
            "changed overnight.",
            "",
            "Oil drilling, cable tools, and gushers. The",
            "automobile is coming. Coal and gold still run,",
            "but black gold is the new frontier.",
            "",
            "Rotary drilling unlocks deeper formations.",
            "Corporate wildcatters and independents race",
            "across Texas and Oklahoma.",
        ],
    },
    {
        "id":      "depression",
        "name":    "1933 — Depression Era",
        "year":    1933,
        "month":   3,
        "region":  "Colorado / New Mexico",
        "world_x": 220, "world_y": 155,  # Denver / Cripple Creek area
        "cash":    15.0,
        "desc": [
            "The crash of 1929 left millions desperate.",
            "FDR raised the gold price from $20.67 to $35.",
            "Suddenly every stream and hillside looks",
            "worth prospecting again.",
            "",
            "Gasoline dredges appear on small creeks.",
            "Hard times breed hard men. The law is thin",
            "in the back country.",
        ],
    },
    {
        "id":      "atomic",
        "name":    "1948 — Atomic Age",
        "year":    1948,
        "month":   6,
        "region":  "Colorado Plateau",
        "world_x": 210, "world_y": 158,  # Grand Junction / Moab area
        "cash":    300.0,
        "desc": [
            "The AEC needs uranium. Desperately.",
            "Geiger counters replace gold pans on the",
            "Colorado Plateau. The government pays fixed",
            "prices — the surest money in a century.",
            "",
            "Jeep trails through canyon country. Carnotite",
            "and coffinite in the sandstone. Radiation",
            "nobody fully understands yet.",
        ],
    },
    {
        "id":      "regulated",
        "name":    "1972 — Regulated Era",
        "year":    1972,
        "month":   4,
        "region":  "Montana / Idaho",
        "world_x": 175, "world_y": 88,   # Butte, MT area
        "cash":    800.0,
        "desc": [
            "NEPA (1970) changed everything. Permits,",
            "environmental impact studies, and federal",
            "oversight now gate every significant operation.",
            "",
            "Nixon's gold shock (1971) sent gold to a free",
            "market for the first time since FDR.",
            "By 1980 it will hit $850/oz.",
            "",
            "Bureaucracy is the new wilderness to navigate.",
        ],
    },
]


# ── Background data ───────────────────────────────────────────────────────────

BACKGROUNDS = [
    {
        "id":    "forty_niner",
        "name":  "Forty-Niner",
        "era_min": None,
        "desc": [
            "You followed the rumor west with a pan and",
            "a mule. You have worked every creek between",
            "Georgia and Sacramento.",
            "",
            "Your hands know gravel. You can read a bar",
            "at a glance and smell pay dirt in a cut bank.",
        ],
        "bonuses": {"placer": 2, "survival": 1, "tracking": 1},
        "cash_mult": 1.0,
        "gear_note": "Start with: gold pan, bedroll, 3 days' provisions.",
    },
    {
        "id":    "soldier",
        "name":  "Former Soldier",
        "era_min": None,
        "desc": [
            "You mustered out after the war — which war",
            "depends on the year — and headed for the",
            "territories with a rifle and nothing else.",
            "",
            "You know how to endure, how to fight, and",
            "how to keep your mouth shut.",
        ],
        "bonuses": {"firearms": 2, "survival": 2, "firstAid": 1},
        "cash_mult": 0.8,
        "gear_note": "Start with: rifle, knife, military haversack.",
    },
    {
        "id":    "trader",
        "name":  "River Trader",
        "era_min": None,
        "desc": [
            "You have worked every river landing from",
            "St. Louis to the delta. You know prices,",
            "people, and the smell of a bad deal.",
            "",
            "A dollar buys more in your hands than in",
            "most men's. You also know when to walk.",
        ],
        "bonuses": {"trading": 3, "charisma": 1, "law": 1},
        "cash_mult": 1.5,
        "gear_note": "Start with: trade goods, ledger, good boots.",
    },
    {
        "id":    "assayer",
        "name":  "Assayer's Apprentice",
        "era_min": None,
        "desc": [
            "You spent three years in a back room running",
            "fire assays and acid tests. You know ore from",
            "gangue, and real color from fool's gold.",
            "",
            "Other men will pay you for that knowledge.",
            "Knowledge that most learn only by losing money.",
        ],
        "bonuses": {"assaying": 3, "geology": 2, "chemistry": 1},
        "cash_mult": 1.0,
        "gear_note": "Start with: acid test kit, field notebook.",
    },
    {
        "id":    "homesteader",
        "name":  "Homesteader",
        "era_min": None,
        "desc": [
            "You built two barns, dug a well, and lost",
            "the farm to drought or debt. You know how",
            "to make things from what is at hand.",
            "",
            "You are slower to strike than most men, but",
            "what you build tends to stand.",
        ],
        "bonuses": {"farming": 2, "engineering": 2, "survival": 1},
        "cash_mult": 0.7,
        "gear_note": "Start with: hand tools, axe, seed stock.",
    },
    {
        "id":    "scholar",
        "name":  "Scholar",
        "era_min": None,
        "desc": [
            "You read every USGS survey you could find.",
            "You can quote Silliman on petroleum seeps",
            "and Le Conte on placer formation.",
            "",
            "In the field your hands are soft. In an",
            "assay office, your mind is razor.",
        ],
        "bonuses": {"geology": 3, "assaying": 1, "literacy": 2},
        "cash_mult": 1.2,
        "gear_note": "Start with: survey maps, compass, field journal.",
    },
    {
        "id":    "wildcatter",
        "name":  "Wildcatter",
        "era_min": "petroleum",
        "desc": [
            "You have drilled seven dry holes and one",
            "gusher. The gusher paid for the dry holes",
            "and left enough to try again.",
            "",
            "You can smell an anticline. You know cable",
            "tool from rotary, and you know which crew",
            "chiefs to trust.",
        ],
        "bonuses": {"oilSensing": 3, "engineering": 2, "geology": 1},
        "cash_mult": 1.0,
        "gear_note": "Start with: drilling log, surface lease forms.",
    },
    {
        "id":    "geiger_man",
        "name":  "AEC Prospector",
        "era_min": "atomic",
        "desc": [
            "The Atomic Energy Commission gave you a",
            "Geiger counter and a price schedule and told",
            "you to find uranium. Simple as that.",
            "",
            "You have learned the Colorado Plateau like",
            "the back of your hand. The carnotite seams.",
            "The canyon walls that click and chatter.",
        ],
        "bonuses": {"geology": 2, "survival": 2, "tracking": 1},
        "cash_mult": 1.3,
        "gear_note": "Start with: Geiger counter, AEC field guide.",
    },
]

# Era unlock order (for checking era_min)
ERA_ORDER = ["gold_rush", "industrial", "petroleum",
             "depression", "atomic", "regulated"]


def _bg_available(bg: dict, era: dict) -> bool:
    if bg["era_min"] is None:
        return True
    era_idx    = ERA_ORDER.index(era["id"])
    min_idx    = ERA_ORDER.index(bg["era_min"])
    return era_idx >= min_idx


# ── Shared drawing helpers ─────────────────────────────────────────────────────

def _clear(con: tcod.console.Console):
    con.draw_rect(0, 0, con.width, con.height, ord(" "), fg=PAPER, bg=BG)


def _title_bar(con: tcod.console.Console, subtitle: str = ""):
    """Top two rows: game name + subtitle."""
    con.draw_rect(0, 0, con.width, 2, ord(" "), fg=GOLD, bg=(18, 12, 4))
    title = "AMERICAN  PROSPECTOR"
    con.print(con.width // 2 - len(title) // 2, 0, title, fg=GOLD, bg=(18, 12, 4))
    if subtitle:
        con.print(con.width // 2 - len(subtitle) // 2, 1,
                  subtitle, fg=GOLD2, bg=(18, 12, 4))


def _nav_bar(con: tcod.console.Console, hint: str):
    """Bottom row: navigation hint."""
    con.draw_rect(0, con.height - 1, con.width, 1,
                  ord(" "), fg=GREY, bg=(10, 8, 6))
    con.print(2, con.height - 1, hint, fg=GREY, bg=(10, 8, 6))


def _box(con: tcod.console.Console, x: int, y: int, w: int, h: int,
         title: str = "", bg=BG_BOX):
    con.draw_rect(x, y, w, h, ord(" "), fg=PAPER, bg=bg)
    for bx in range(w):
        con.print(x + bx, y,         "─", fg=GOLD2, bg=bg)
        con.print(x + bx, y + h - 1, "─", fg=GOLD2, bg=bg)
    for by in range(h):
        con.print(x,         y + by, "│", fg=GOLD2, bg=bg)
        con.print(x + w - 1, y + by, "│", fg=GOLD2, bg=bg)
    con.print(x,         y,         "┌", fg=GOLD2, bg=bg)
    con.print(x + w - 1, y,         "┐", fg=GOLD2, bg=bg)
    con.print(x,         y + h - 1, "└", fg=GOLD2, bg=bg)
    con.print(x + w - 1, y + h - 1, "┘", fg=GOLD2, bg=bg)
    if title:
        con.print(x + 2, y, f" {title} ", fg=GOLD, bg=bg)


def _attr_bar(val: int, width: int = 10) -> str:
    filled = max(0, min(width, round((val - 6) / 10 * width)))
    return "█" * filled + "░" * (width - filled)


# ── Screen 1: Name ─────────────────────────────────────────────────────────────

def _screen_name(con: tcod.console.Console, ctx) -> Optional[str]:
    """Text input for character name. Returns name string or None to quit."""
    name_buf = ""
    MAX_LEN  = 24

    LINES = [
        "The year is uncertain. The territory is dangerous.",
        "The gold is real.",
        "",
        "What is your name, stranger?",
    ]

    # tcod 19+ requires explicit text input activation
    ctx.sdl_window.start_text_input()
    try:
        while True:
            _clear(con)
            _title_bar(con, "A Hard Prospecting Simulator  ·  1849 – 2000")

            # Flavor text
            for i, line in enumerate(LINES):
                color = GOLD if line.startswith("The gold") else PAPER
                con.print(SCREEN_WIDTH // 2 - len(line) // 2,
                          14 + i, line, fg=color, bg=BG)

            # Input box
            bx = SCREEN_WIDTH // 2 - 18
            by = 20
            _box(con, bx, by, 36, 5, "Your Name")
            display = name_buf + ("█" if (len(name_buf) < MAX_LEN) else "")
            con.print(bx + 2, by + 2, display[:32], fg=WHITE, bg=BG_BOX)

            if len(name_buf) == 0:
                con.print(bx + 2, by + 3,
                          "Enter a name to continue.",
                          fg=DGREY, bg=BG_BOX)

            _nav_bar(con, "Enter — continue   Esc — quit")
            ctx.present(con)

            for event in tcod.event.wait():
                if isinstance(event, tcod.event.Quit):
                    return None

                if isinstance(event, tcod.event.TextInput):
                    if len(name_buf) < MAX_LEN:
                        name_buf += event.text

                if isinstance(event, tcod.event.KeyDown):
                    sym = event.sym
                    K   = tcod.event.KeySym
                    if sym == K.ESCAPE:
                        return None
                    elif sym in (K.RETURN, K.KP_ENTER):
                        if name_buf.strip():
                            return name_buf.strip()
                    elif sym == K.BACKSPACE:
                        name_buf = name_buf[:-1]
                    elif sym == K.DELETE:
                        name_buf = ""
    finally:
        ctx.sdl_window.stop_text_input()


# ── Screen 2: Era ──────────────────────────────────────────────────────────────

def _screen_era(con: tcod.console.Console, ctx) -> Optional[dict]:
    """Era selection. Returns era dict or None to go back."""
    selected = 0
    LW = 44   # left panel width
    RX = LW + 2
    RW = SCREEN_WIDTH - RX - 1

    while True:
        _clear(con)
        _title_bar(con, "Choose Your Era")

        # Left panel — era list (only Gold Rush era playable now)
        _box(con, 0, 2, LW, SCREEN_HEIGHT - 4)
        for i, era in enumerate(ERAS):
            is_sel = i == selected
            playable = (era["id"] == "gold_rush")
            if not playable:
                # Grey out unavailable eras
                fg = DGREY
                bg = BG_BOX
                prefix = " "
            else:
                fg = CYAN if is_sel else PAPER
                bg = BG_SEL if is_sel else BG_BOX
                prefix = "▶" if is_sel else " "
            year   = era["name"].split("—")[0].strip()
            label  = era["name"].split("—")[1].strip()
            y_fg = (GOLD if is_sel and playable else GOLD2 if playable else DGREY)
            con.print(2,  5 + i * 5,     f"{prefix} {year}", fg=y_fg, bg=bg)
            con.print(4,  6 + i * 5,     label[:LW - 6],    fg=fg,   bg=bg)
            if playable:
                con.print(4,  7 + i * 5, era["region"],      fg=GREY, bg=bg)
            else:
                con.print(4,  7 + i * 5, "— Coming Soon —",  fg=DGREY, bg=bg)

        # Right panel — era detail
        era = ERAS[selected]
        _box(con, RX, 2, RW, SCREEN_HEIGHT - 4, era["name"])

        ry = 5
        for line in era["desc"]:
            if ry >= SCREEN_HEIGHT - 5:
                break
            con.print(RX + 2, ry, line[:RW - 4], fg=PAPER, bg=BG_BOX)
            ry += 1

        ry += 1
        con.print(RX + 2, ry,     f"Starting region:  {era['region']}",
                  fg=AMBER, bg=BG_BOX)
        con.print(RX + 2, ry + 1, f"Starting cash:    ${era['cash']:,.2f}",
                  fg=GREEN, bg=BG_BOX)
        con.print(RX + 2, ry + 2,
                  f"Starting date:    {era['month']}/1/{era['year']}",
                  fg=GREY, bg=BG_BOX)

        _nav_bar(con, "↑↓ — choose era   Enter — select   Esc — back to name")
        ctx.present(con)

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return None
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                K   = tcod.event.KeySym
                if sym == K.ESCAPE:
                    return None
                elif sym in (K.UP, K.KP_8):
                    selected = (selected - 1) % len(ERAS)
                elif sym in (K.DOWN, K.KP_2):
                    selected = (selected + 1) % len(ERAS)
                elif sym in (K.RETURN, K.KP_ENTER):
                    if ERAS[selected]["id"] == "gold_rush":
                        return ERAS[selected]
                    # Can't select locked eras


# ── Screen 3: Background ───────────────────────────────────────────────────────

def _screen_background(con: tcod.console.Console, ctx,
                        era: dict) -> Optional[dict]:
    """Background selection. Returns background dict or None to go back."""
    selected  = 0
    available = [b for b in BACKGROUNDS if _bg_available(b, era)]
    LW = 36
    RX = LW + 2
    RW = SCREEN_WIDTH - RX - 1

    while True:
        _clear(con)
        _title_bar(con, "Choose Your Background")

        # Left — background list
        _box(con, 0, 2, LW, SCREEN_HEIGHT - 4)
        for i, bg in enumerate(available):
            is_sel = i == selected
            fg     = CYAN  if is_sel else PAPER
            bg_col = BG_SEL if is_sel else BG_BOX
            prefix = "▶" if is_sel else " "
            con.print(2, 5 + i * 3, f"{prefix} {bg['name']}", fg=fg, bg=bg_col)
            bonuses = "  ".join(
                f"+{v} {k[:6]}" for k, v in bg["bonuses"].items()
                if k in ("placer","survival","firearms","assaying","geology",
                         "trading","farming","engineering","oilSensing","literacy",
                         "firstAid","tracking","chemistry","charisma","law")
            )
            con.print(4, 6 + i * 3, bonuses[:LW - 6], fg=AMBER, bg=bg_col)

        # Right — detail
        sel_bg = available[selected]
        _box(con, RX, 2, RW, SCREEN_HEIGHT - 4, sel_bg["name"])

        ry = 5
        for line in sel_bg["desc"]:
            if ry >= SCREEN_HEIGHT - 12:
                break
            con.print(RX + 2, ry, line[:RW - 4], fg=PAPER, bg=BG_BOX)
            ry += 1

        ry += 1
        con.print(RX + 2, ry, "Skill bonuses:", fg=GOLD, bg=BG_BOX)
        ry += 1
        for skill, bonus in sel_bg["bonuses"].items():
            con.print(RX + 4, ry,
                      f"+{bonus}  {skill}",
                      fg=GREEN, bg=BG_BOX)
            ry += 1

        ry += 1
        con.print(RX + 2, ry, sel_bg["gear_note"], fg=AMBER, bg=BG_BOX)
        if sel_bg["cash_mult"] != 1.0:
            ry += 1
            adj = sel_bg["cash_mult"]
            sign = "+" if adj > 1.0 else ""
            pct  = (adj - 1.0) * 100
            con.print(RX + 2, ry,
                      f"Starting cash {sign}{pct:.0f}%",
                      fg=(GREEN if adj > 1.0 else RED), bg=BG_BOX)

        _nav_bar(con, "↑↓ — choose   Enter — select   Esc — back to era")
        ctx.present(con)

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return None
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                K   = tcod.event.KeySym
                if sym == K.ESCAPE:
                    return None
                elif sym in (K.UP, K.KP_8):
                    selected = (selected - 1) % len(available)
                elif sym in (K.DOWN, K.KP_2):
                    selected = (selected + 1) % len(available)
                elif sym in (K.RETURN, K.KP_ENTER):
                    return available[selected]


# ── Screen 4: Attributes ───────────────────────────────────────────────────────

def _screen_attributes(con: tcod.console.Console, ctx) -> Optional[dict]:
    """
    Point-buy attributes. All start at 10. Player distributes 10 bonus points.
    Min 6, max 16 per attribute.
    Returns the final attribute dict or None to go back.
    """
    attrs    = {a: 10 for a in ATTR_ORDER}
    pool     = 10
    selected = 0
    W, H     = 60, 26
    X        = (SCREEN_WIDTH  - W) // 2
    Y        = (SCREEN_HEIGHT - H) // 2

    while True:
        _clear(con)
        _title_bar(con, "Distribute Attributes")

        _box(con, X, Y, W, H, "Attributes")

        con.print(X + 2, Y + 2,
                  f"Points remaining:  {pool}",
                  fg=(GREEN if pool > 0 else GREY), bg=BG_BOX)
        con.print(X + 36, Y + 2,
                  "Min 6  ·  Max 16  ·  Base 10",
                  fg=DGREY, bg=BG_BOX)

        for i, attr in enumerate(ATTR_ORDER):
            val    = attrs[attr]
            is_sel = i == selected
            row    = Y + 5 + i * 3
            fg     = CYAN if is_sel else PAPER
            bg_row = BG_SEL if is_sel else BG_BOX

            con.draw_rect(X + 1, row, W - 2, 1, ord(" "), fg=fg, bg=bg_row)

            prefix = "▶" if is_sel else " "
            short  = ATTR_SHORT[attr]
            bar    = _attr_bar(val, 10)
            delta  = val - 10
            dsign  = f"+{delta}" if delta > 0 else (f"{delta}" if delta < 0 else " 0")
            left_col  = f"{prefix} {short}  [{bar}]  {val:2d}  ({dsign})"
            con.print(X + 1, row, left_col, fg=fg, bg=bg_row)

            # Description on right
            desc = ATTR_DESC[attr][:W - len(left_col) - 4]
            con.print(X + 2 + len(left_col), row, desc, fg=DGREY, bg=bg_row)

            if is_sel:
                hints = []
                if pool > 0 and val < 16:
                    hints.append("→ raise")
                if val > 6:
                    hints.append("← lower")
                con.print(X + 2, row + 1,
                          "  ".join(hints),
                          fg=GREY, bg=BG_BOX)

        _nav_bar(con, "↑↓ select   ← → adjust   Enter — done   Esc — back")
        ctx.present(con)

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return None
            if isinstance(event, tcod.event.KeyDown):
                sym  = event.sym
                K    = tcod.event.KeySym
                attr = ATTR_ORDER[selected]
                if sym == K.ESCAPE:
                    return None
                elif sym in (K.UP, K.KP_8):
                    selected = (selected - 1) % len(ATTR_ORDER)
                elif sym in (K.DOWN, K.KP_2):
                    selected = (selected + 1) % len(ATTR_ORDER)
                elif sym in (K.RIGHT, K.KP_6):
                    if pool > 0 and attrs[attr] < 16:
                        attrs[attr] += 1
                        pool -= 1
                elif sym in (K.LEFT, K.KP_4):
                    if attrs[attr] > 6:
                        attrs[attr] -= 1
                        pool += 1
                elif sym in (K.RETURN, K.KP_ENTER):
                    return attrs


# ── Skill descriptions ────────────────────────────────────────────────────

SKILL_DESC = {
    "placer":      "Pan for gold, work sluice boxes, read gravel bars.",
    "geology":     "Read terrain, identify minerals, assess ground.",
    "survival":    "Camp, forage, fish, endure weather, find water.",
    "tracking":    "Follow trails, hunt game, navigate wilderness.",
    "firearms":    "Shoot accurately, maintain weapons, reload fast.",
    "trading":     "Haggle prices, read markets, run a business.",
    "engineering": "Build structures, machines, repair equipment.",
    "firstAid":    "Treat wounds, set bones, fight infection.",
    "hardRock":    "Mine shafts, drill, blast, extract ore from rock.",
    "law":         "File claims, know your rights, argue in court.",
    "literacy":    "Read, write, keep books, publish articles.",
    # Coming soon — greyed out in UI
    "assaying":    "Test ore purity. (Coming soon)",
    "chemistry":   "Amalgamation, refining. (Coming soon)",
    "farming":     "Grow crops, raise animals. (Coming soon)",
    "driving":     "Handle wagons, pack animals. (Coming soon)",
    "oilSensing":  "Find oil deposits. (Coming soon)",
    "coalMining":  "Mine coal seams. (Coming soon)",
}

# Skills available for point allocation (active in gameplay)
SKILL_ORDER = [
    "placer", "geology", "survival", "tracking", "firearms",
    "trading", "engineering", "firstAid", "hardRock", "law",
    "literacy",
]

# Skills shown but greyed out (not yet implemented)
SKILL_LOCKED = [
    "assaying", "chemistry", "farming", "driving",
    "oilSensing", "coalMining",
]


# ── Screen 5: Skills ─────────────────────────────────────────────────────

def _screen_skills(con: tcod.console.Console, ctx,
                    bg_bonuses: dict) -> Optional[dict]:
    """
    Skill point-buy. Player distributes 8 points across all skills.
    Background bonuses shown but not editable. Min 0, max 5 per skill.
    Returns skill dict or None to go back.
    """
    skills   = {s: 0 for s in SKILL_ORDER}
    pool     = 8
    selected = 0
    W, H     = 74, 44
    X        = (SCREEN_WIDTH  - W) // 2
    Y        = (SCREEN_HEIGHT - H) // 2

    while True:
        _clear(con)
        _title_bar(con, "Distribute Starting Skills")

        _box(con, X, Y, W, H, "Skills")

        con.print(X + 2, Y + 2,
                  f"Points remaining:  {pool}",
                  fg=(GREEN if pool > 0 else GREY), bg=BG_BOX)
        con.print(X + 30, Y + 2,
                  "Max 5 per skill. Background bonuses in green.",
                  fg=DGREY, bg=BG_BOX)

        # Active skills
        for i, skill in enumerate(SKILL_ORDER):
            val     = skills[skill]
            bonus   = bg_bonuses.get(skill, 0)
            total   = val + bonus
            is_sel  = i == selected
            row     = Y + 4 + i * 2
            fg      = CYAN if is_sel else PAPER
            bg_row  = BG_SEL if is_sel else BG_BOX

            if row >= Y + H - 8:
                break

            con.draw_rect(X + 1, row, W - 2, 1, ord(" "), fg=fg, bg=bg_row)

            prefix = "▶" if is_sel else " "
            bar = "█" * total + "░" * (5 - total)

            name_str = f"{prefix} {skill:<14}"
            bar_str = f"[{bar}] {total}"
            bonus_str = f" (+{bonus} bg)" if bonus > 0 else ""

            con.print(X + 1, row, name_str, fg=fg, bg=bg_row)
            con.print(X + 18, row, bar_str, fg=fg, bg=bg_row)
            if bonus > 0:
                con.print(X + 26, row, bonus_str, fg=GREEN, bg=bg_row)

            desc = SKILL_DESC.get(skill, "")[:W - 36]
            con.print(X + 36, row, desc, fg=DGREY, bg=bg_row)

            if is_sel:
                hints = []
                if pool > 0 and val < 5:
                    hints.append("→ raise")
                if val > 0:
                    hints.append("← lower")
                if hints:
                    con.print(X + 2, row + 1,
                              "  ".join(hints), fg=GREY, bg=BG_BOX)

        # Locked skills (greyed out, not selectable)
        locked_y = Y + 4 + len(SKILL_ORDER) * 2 + 1
        if locked_y < Y + H - 3:
            con.print(X + 2, locked_y, "COMING SOON:", fg=DGREY, bg=BG_BOX)
            locked_y += 1
            for sk in SKILL_LOCKED:
                if locked_y >= Y + H - 2:
                    break
                desc = SKILL_DESC.get(sk, "")[:W - 20]
                con.print(X + 4, locked_y, f"  {sk:<14} {desc}",
                          fg=DGREY, bg=BG_BOX)
                locked_y += 1

        _nav_bar(con, "↑↓ select   ← → adjust   Enter — done   Esc — back")
        ctx.present(con)

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return None
            if isinstance(event, tcod.event.KeyDown):
                sym   = event.sym
                K     = tcod.event.KeySym
                skill = SKILL_ORDER[selected]
                if sym == K.ESCAPE:
                    return None
                elif sym in (K.UP, K.KP_8):
                    selected = (selected - 1) % len(SKILL_ORDER)
                elif sym in (K.DOWN, K.KP_2):
                    selected = (selected + 1) % len(SKILL_ORDER)
                elif sym in (K.RIGHT, K.KP_6):
                    if pool > 0 and skills[skill] < 5:
                        skills[skill] += 1
                        pool -= 1
                elif sym in (K.LEFT, K.KP_4):
                    if skills[skill] > 0:
                        skills[skill] -= 1
                        pool += 1
                elif sym in (K.RETURN, K.KP_ENTER):
                    # Merge with background bonuses
                    final = {}
                    for s in SKILL_ORDER:
                        final[s] = skills[s] + bg_bonuses.get(s, 0)
                    return final


# ── Screen 6: Confirm ─────────────────────────────────────────────────────────

def _screen_confirm(con: tcod.console.Console, ctx,
                    choices: dict) -> bool:
    """Summary screen. Returns True to begin, False to go back."""
    W, H = 70, 32
    X    = (SCREEN_WIDTH  - W) // 2
    Y    = (SCREEN_HEIGHT - H) // 2

    era  = choices["era"]
    bg   = choices["background"]
    name = choices["name"]
    attrs= choices["attributes"]
    cash = era["cash"] * bg["cash_mult"]

    while True:
        _clear(con)
        _title_bar(con, "Ready to Prospect?")

        _box(con, X, Y, W, H, "Character Summary")

        r = Y + 2
        con.print(X + 3, r, f"Name:        {name}", fg=WHITE,  bg=BG_BOX); r += 1
        con.print(X + 3, r, f"Era:         {era['name']}", fg=AMBER, bg=BG_BOX); r += 1
        con.print(X + 3, r, f"Background:  {bg['name']}",  fg=CYAN,  bg=BG_BOX); r += 1
        con.print(X + 3, r, f"Region:      {era['region']}", fg=PAPER, bg=BG_BOX); r += 1
        con.print(X + 3, r, f"Starting $:  ${cash:,.2f}", fg=GREEN,  bg=BG_BOX); r += 2

        # Attributes grid
        con.print(X + 3, r, "Attributes:", fg=GOLD, bg=BG_BOX); r += 1
        for i, attr in enumerate(ATTR_ORDER):
            val   = attrs[attr]
            short = ATTR_SHORT[attr]
            delta = val - 10
            dsign = f"+{delta}" if delta > 0 else (f"{delta}" if delta < 0 else "")
            color = GREEN if delta > 0 else (RED if delta < 0 else GREY)
            col   = X + 5 + (i % 3) * 20
            row   = r + i // 3
            con.print(col, row, f"{short} {val:2d} {dsign}", fg=color, bg=BG_BOX)
        r += 3

        # Skills
        skills = choices.get("skills", {})
        if skills:
            con.print(X + 3, r, "Skills:", fg=GOLD, bg=BG_BOX); r += 1
            sk_items = [(k, v) for k, v in skills.items() if v > 0]
            for i in range(0, len(sk_items), 3):
                chunk = sk_items[i:i+3]
                parts = [f"{k} {v}" for k, v in chunk]
                con.print(X + 5, r, "  ".join(parts)[:W - 8], fg=GREEN, bg=BG_BOX)
                r += 1
            r += 1
        else:
            con.print(X + 3, r, "Skill bonuses from background:", fg=GOLD, bg=BG_BOX); r += 1
            bonuses = bg["bonuses"]
            line = "  ".join(f"{k} +{v}" for k, v in bonuses.items())
            con.print(X + 5, r, line[:W - 8], fg=GREEN, bg=BG_BOX); r += 2

        # Gear note
        con.print(X + 3, r, bg["gear_note"], fg=AMBER, bg=BG_BOX); r += 2

        # Confirm prompt
        con.print(X + W // 2 - 12, r,
                  "[ Enter ] Begin Your Story",
                  fg=GOLD, bg=BG_BOX)
        con.print(X + W // 2 - 14, r + 1,
                  "[ Backspace ] Change Background",
                  fg=GREY, bg=BG_BOX)

        _nav_bar(con, "Enter — start game   Backspace — go back")
        ctx.present(con)

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return False
            if isinstance(event, tcod.event.KeyDown):
                sym = event.sym
                K   = tcod.event.KeySym
                if sym in (K.RETURN, K.KP_ENTER):
                    return True
                elif sym == K.BACKSPACE:
                    return False


# ── Main entry point ──────────────────────────────────────────────────────────

def run_character_creation(con: tcod.console.Console, ctx) -> Optional[dict]:
    """
    Run all five creation screens as a simple state machine.
    Each screen returns its value on confirm, or None to step back.
    Returns the completed character dict, or None if the player quits.
    """
    # States: name → era → background → attributes → skills → confirm → done
    state  = "name"
    name   = ""
    era    = None
    bg     = None
    attrs  = None
    skills = None

    while True:
        if state == "name":
            result = _screen_name(con, ctx)
            if result is None:
                return None
            name  = result
            state = "era"

        elif state == "era":
            result = _screen_era(con, ctx)
            if result is None:
                state = "name"
            else:
                era   = result
                state = "background"

        elif state == "background":
            result = _screen_background(con, ctx, era)
            if result is None:
                state = "era"
            else:
                bg    = result
                state = "attributes"

        elif state == "attributes":
            result = _screen_attributes(con, ctx)
            if result is None:
                state = "background"
            else:
                attrs = result
                state = "skills"

        elif state == "skills":
            result = _screen_skills(con, ctx, bg["bonuses"])
            if result is None:
                state = "attributes"
            else:
                skills = result
                state = "confirm"

        elif state == "confirm":
            choices = {"name": name, "era": era,
                       "background": bg, "attributes": attrs,
                       "skills": skills}
            if _screen_confirm(con, ctx, choices):
                return {
                    "name":          name,
                    "era":           era,
                    "background":    bg,
                    "attributes":    attrs,
                    "skills":        skills,
                    "cash":          era["cash"] * bg["cash_mult"],
                    "world_x":       era["world_x"],
                    "world_y":       era["world_y"],
                    "start_year":    era["year"],
                    "start_month":   era["month"],
                    "skill_bonuses": bg["bonuses"],
                }
            else:
                state = "skills"
