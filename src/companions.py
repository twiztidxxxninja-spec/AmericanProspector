"""
src/companions.py

Companion and employee system for American Prospector.

Companions (mining partners, adventure allies) are loyal and flexible.
Employees (hired help) are transactional — they expect fair pay and
reasonable work conditions.

Key classes:
    CompanionRole       — role constants and properties
    CompanionLink       — relationship between player and an NPC ally
    DelegatedTask       — a task assigned to an NPC
    TaskResult          — outcome of a completed task
    CompanionManager    — manages all companions/employees and their tasks

Integration:
    Engine holds CompanionManager.
    Talk menu offers "Delegate Tasks" when talking to a companion/employee.
    Task outcomes feed into inventory, building progress, etc.
    NPC relationship/personality affects task acceptance and quality.
    LLM handles freeform custom tasks.
"""

import random
import tcod
import tcod.event
import tcod.console
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.npc import NPC
    from src.player import Player
    from src.llm_client import LLMClient


# ============================================================================
#  ROLE CONSTANTS
# ============================================================================

class Role:
    COMPANION = "companion"     # adventure partner, mining buddy — loyal
    PARTNER   = "partner"       # business partner — shared profits
    EMPLOYEE  = "employee"      # hired worker — transactional


ROLE_LABELS = {
    Role.COMPANION: "Companion",
    Role.PARTNER:   "Partner",
    Role.EMPLOYEE:  "Employee",
}

# Base loyalty by role (modifies willingness to accept tasks)
ROLE_LOYALTY = {
    Role.COMPANION: 0.85,    # very willing
    Role.PARTNER:   0.70,    # willing if fair
    Role.EMPLOYEE:  0.50,    # only if paid and reasonable
}


# ============================================================================
#  HARDCODED DELEGATE TASKS
# ============================================================================

@dataclass
class TaskDef:
    """Template for a delegatable task."""
    key: str
    label: str                  # menu display
    skill: str                  # governing skill
    base_minutes: int           # time to complete
    difficulty: int             # 1-20
    danger: float               # 0.0-1.0 (chance of injury)
    category: str               # "gather"|"build"|"combat"|"camp"|"haul"|"craft"
    description: str = ""
    requires_tool: str = ""     # tool_tag needed ("" = none)
    unpleasant: bool = False    # employees may refuse


TASK_DEFS: Dict[str, TaskDef] = {}

def _td(key, label, skill, mins, diff, danger, cat, desc="",
        tool="", unpleasant=False):
    TASK_DEFS[key] = TaskDef(key, label, skill, mins, diff, danger, cat,
                              desc, tool, unpleasant)

# Gathering
_td("fish",          "Go fishing",                "survival",   60, 6,  0.02, "gather",
    "Fish the nearest water for food.")
_td("chop_wood",     "Chop wood",                 "survival",   45, 5,  0.05, "gather",
    "Fell trees and split firewood.", tool="chop")
_td("gather_water",  "Fetch water",               "survival",   20, 3,  0.01, "gather",
    "Fill containers from the nearest water source.")
_td("forage",        "Forage for food",            "survival",   40, 7,  0.03, "gather",
    "Search for edible plants, roots, berries.")
_td("hunt",          "Hunt game",                  "tracking",   90, 10, 0.10, "gather",
    "Track and hunt wild game.", tool="firearm")
_td("gather_stone",  "Gather stones",              "survival",   30, 4,  0.02, "gather",
    "Collect rocks and stones for building.")

# Prospecting
_td("prospect_pan",  "Pan for gold",              "placer",     30, 8,  0.01, "gather",
    "Work the creek with a gold pan.", tool="pan")
_td("dig_test_pit",  "Dig a test pit",            "geology",    60, 7,  0.04, "gather",
    "Dig a test hole to check for gold-bearing ground.", tool="dig")

# Camp
_td("guard_camp",    "Guard the camp",             "firearms",   60, 5,  0.08, "combat",
    "Keep watch over camp and equipment.")
_td("cook_food",     "Cook food / clean game",     "survival",   30, 4,  0.01, "camp",
    "Prepare and cook available food.")
_td("tend_fire",     "Tend the fire",              "survival",   15, 2,  0.01, "camp",
    "Keep the campfire burning.")
_td("set_camp",      "Set up camp",                "survival",   30, 4,  0.02, "camp",
    "Pitch tent, lay bedrolls, organize gear.")
_td("clean_camp",    "Clean up camp",              "survival",   20, 3,  0.01, "camp",
    "Tidy camp, bury waste, organize supplies.", unpleasant=True)

# Construction
_td("build_cont",    "Continue building",          "engineering",60, 8,  0.05, "build",
    "Continue construction on the current project.")
_td("repair_equip",  "Repair equipment",           "engineering",40, 7,  0.02, "build",
    "Fix damaged tools and gear.")

# Hauling
_td("haul_supplies", "Haul supplies",              "survival",   45, 5,  0.03, "haul",
    "Move materials and supplies to/from stockpile.", unpleasant=True)
_td("haul_ore",      "Haul ore to camp",           "survival",   60, 6,  0.04, "haul",
    "Carry ore or gravel from the worksite.", unpleasant=True)

# Scouting
_td("scout_ahead",   "Scout ahead",                "tracking",   45, 8,  0.12, "combat",
    "Explore the surrounding area and report back.")
_td("scout_stream",  "Follow the stream upstream", "geology",    60, 7,  0.05, "gather",
    "Explore upstream for signs of gold or better ground.")

# Social
_td("trade_town",    "Go to town and trade",       "trading",   120, 6,  0.05, "haul",
    "Travel to the nearest town to buy or sell goods.")

# Business operations
_td("buy_goods",     "Buy goods for business",     "trading",    90, 7,  0.03, "haul",
    "Purchase stock from suppliers for the business.")
_td("sell_goods",    "Sell at the counter",         "trading",    60, 5,  0.01, "camp",
    "Man the counter and sell goods to customers.")
_td("process_goods", "Process materials",           "engineering",60, 6,  0.02, "build",
    "Work stretching frames, tan hides, craft goods.")
_td("haul_goods",    "Haul goods to town",          "survival",  120, 6,  0.08, "haul",
    "Transport business goods to another location.", unpleasant=True)
_td("manage_biz",    "Manage operations",           "trading",    60, 8,  0.01, "camp",
    "Run day-to-day business. Make decisions, handle customers.")
_td("guard_stock",   "Guard inventory",             "firearms",   60, 5,  0.06, "combat",
    "Protect stored goods and premises from theft.")
_td("scout_prices",  "Scout market prices",         "trading",    90, 7,  0.04, "haul",
    "Visit nearby merchants and report back on prices.")


# ============================================================================
#  COMPANION LINK
# ============================================================================

@dataclass
class CompanionLink:
    """
    Tracks the relationship between the player and an NPC who
    has been recruited as companion, partner, or employee.
    """
    npc_id: str
    name: str
    role: str                       # Role constant
    wage_daily: float = 0.0         # $ per day (employees); 0 = companions
    share_pct: float = 0.0          # profit share (partners); 0 = others
    days_with_player: int = 0
    tasks_completed: int = 0
    tasks_refused: int = 0
    morale: float = 70.0            # 0-100
    loyalty: float = 50.0           # 0-100 (starts at 50, builds over time)
    currently_tasked: bool = False
    current_task: Optional[str] = None   # task key or custom text
    task_started_minute: int = 0         # game total_minutes when task began
    task_duration: int = 0               # minutes until done

    @property
    def effective_loyalty(self) -> float:
        """Loyalty modified by role base."""
        base = ROLE_LOYALTY.get(self.role, 0.5)
        return min(1.0, base + self.loyalty * 0.005)

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role)


# ============================================================================
#  TASK ACCEPTANCE LOGIC
# ============================================================================

def will_accept_task(link: CompanionLink, npc: "NPC",
                      task_key: str, is_custom: bool = False
                      ) -> Tuple[bool, str]:
    """
    Determine if an NPC will accept a delegated task.
    Returns (accepted: bool, reason_message: str).

    Companions almost always accept (unless morale is rock-bottom).
    Employees refuse dangerous, unpleasant, or underpaid tasks.
    """
    task_def = TASK_DEFS.get(task_key)

    # Companions are loyal
    if link.role == Role.COMPANION:
        if link.morale < 15:
            return False, f"{link.name} shakes their head. \"I need a break.\""
        if task_def and task_def.danger > 0.3 and link.morale < 40:
            return False, f"{link.name} hesitates. \"That's too risky right now.\""
        return True, f"{link.name} nods. \"I'm on it.\""

    # Partners negotiate
    if link.role == Role.PARTNER:
        if task_def and task_def.unpleasant:
            if link.morale < 50:
                return False, f"{link.name} frowns. \"That's beneath a partner.\""
        if link.morale < 25:
            return False, f"{link.name} crosses arms. \"We need to talk about how this is going.\""
        return True, f"{link.name} agrees. \"Fair enough.\""

    # Employees are transactional
    if link.role == Role.EMPLOYEE:
        # No pay? No work
        if link.wage_daily <= 0:
            return False, f"{link.name} scoffs. \"You haven't paid me.\""

        # Refuse dangerous tasks if morale is low
        if task_def and task_def.danger > 0.15 and link.morale < 50:
            return False, (f"{link.name} shakes their head. "
                          f"\"That's not what I signed up for.\"")

        # Refuse unpleasant tasks if morale is low
        if task_def and task_def.unpleasant and link.morale < 40:
            return False, f"{link.name} grimaces. \"Find someone else for that.\""

        # Low morale = chance of refusal
        if link.morale < 30 and random.random() < 0.4:
            return False, f"{link.name} grumbles. \"I'm done for today.\""

        # Custom tasks employees are suspicious of
        if is_custom and link.morale < 60:
            return False, f"{link.name} looks skeptical. \"That's not in my job.\""

        return True, f"{link.name} gets to work."

    return True, f"{link.name} nods."


# ============================================================================
#  TASK RESOLUTION
# ============================================================================

@dataclass
class TaskResult:
    """Outcome of a completed delegated task."""
    task_key: str
    npc_name: str
    success: bool
    quality: float              # 0.0-1.0 (how well done)
    message: str                # narrative description
    items_produced: List[str] = field(default_factory=list)
    gold_found: float = 0.0
    time_taken: int = 0         # actual minutes
    npc_injured: bool = False
    injury_desc: str = ""
    for_business: bool = False  # if True, items go to business inventory
    cost: float = 0.0           # cash spent on purchases


def resolve_task(link: CompanionLink, npc: "NPC",
                  task_key: str, gold_bias: float = 0.3,
                  rng: Optional[random.Random] = None) -> TaskResult:
    """
    Resolve a completed task mechanically.
    Called when task_duration has elapsed.
    """
    if rng is None:
        rng = random.Random()

    task_def = TASK_DEFS.get(task_key)
    if not task_def:
        # Custom task — basic resolution
        return TaskResult(
            task_key=task_key, npc_name=link.name,
            success=True, quality=0.5,
            message=f"{link.name} finishes the task.",
            time_taken=60,
        )

    # Skill check: NPC skill + d20 vs difficulty × 2
    skill_val = npc.skills.get(task_def.skill, 0) if hasattr(npc, "skills") else 0
    roll = rng.randint(1, 20) + skill_val
    threshold = task_def.difficulty * 2
    success = roll >= threshold
    quality = min(1.0, max(0.1, (roll - threshold + 10) / 20.0))

    # Productivity bonus from loyalty/morale
    quality *= link.effective_loyalty

    # Items produced
    items = []
    if success:
        if task_key == "fish":
            if rng.random() < 0.7:
                items.append("Fresh Fish")
        elif task_key == "chop_wood":
            items.extend(["Log"] * rng.randint(1, 3))
        elif task_key == "forage":
            if rng.random() < 0.5:
                items.append("Wild Berries")
        elif task_key == "hunt":
            if rng.random() < 0.4 * quality:
                items.append("Fresh Venison")
        elif task_key == "cook_food":
            items.append("Cooked Meal")
        elif task_key == "gather_water":
            items.append("Water (quart)")
        elif task_key == "gather_stone":
            items.extend(["Stone"] * rng.randint(2, 5))
        elif task_key == "buy_goods":
            # Generate stock items based on quality — more skill = better deals
            count = max(1, int(3 * quality))
            stock_pool = [
                "Whiskey", "Flour", "Salt", "Coffee", "Tobacco",
                "Beans", "Sugar", "Hardtack", "Bacon", "Rope",
                "Nails", "Canvas", "Lamp Oil",
            ]
            items.extend(rng.choices(stock_pool, k=count))

    # Gold found (prospecting tasks)
    gold = 0.0
    if task_key in ("prospect_pan", "dig_test_pit") and success:
        gold = rng.uniform(0, gold_bias * 0.05) * quality

    # Injury check
    injured = False
    injury_desc = ""
    if rng.random() < task_def.danger:
        injured = True
        injuries = [
            "cut hand on a sharp rock",
            "twisted an ankle",
            "got a nasty splinter",
            "scraped up from a fall",
            "stung by something",
            "bruised from a falling branch",
        ]
        if task_def.danger > 0.10:
            injuries.extend([
                "took a bad fall and hurt their back",
                "caught a rock to the face",
                "gashed their leg on equipment",
            ])
        injury_desc = rng.choice(injuries)

    # Build message
    if success:
        item_str = f" Brought back: {', '.join(items)}." if items else ""
        gold_str = f" Found {gold:.4f} oz gold." if gold > 0 else ""
        inj_str = f" But {link.name} {injury_desc}." if injured else ""
        msg = f"{link.name} completed the task successfully.{item_str}{gold_str}{inj_str}"
    else:
        inj_str = f" {link.name} {injury_desc}." if injured else ""
        msg = f"{link.name} tried but didn't have much luck.{inj_str}"

    # Update link stats
    link.tasks_completed += 1
    link.currently_tasked = False
    link.current_task = None

    # Morale effects
    if success:
        link.morale = min(100, link.morale + 1)
    if injured:
        link.morale = max(0, link.morale - 5)
    if task_def.unpleasant:
        link.morale = max(0, link.morale - 2)

    # Business tasks: items go to business inventory
    is_biz_task = task_key in ("buy_goods", "sell_goods", "process_goods")
    purchase_cost = 0.0
    if task_key == "buy_goods" and items and success:
        # Only buy_goods has a purchase cost
        purchase_cost = len(items) * rng.uniform(0.50, 2.00)

    return TaskResult(
        task_key=task_key, npc_name=link.name,
        success=success, quality=quality, message=msg,
        items_produced=items, gold_found=gold,
        time_taken=task_def.base_minutes,
        npc_injured=injured, injury_desc=injury_desc,
        for_business=is_biz_task, cost=purchase_cost,
    )


# ============================================================================
#  COMPANION MANAGER
# ============================================================================

class CompanionManager:
    """
    Manages all companions and employees.
    Tracks links, assigns tasks, resolves completions.
    """

    def __init__(self):
        self.links: Dict[str, CompanionLink] = {}   # npc_id → link

    def recruit(self, npc_id: str, name: str, role: str,
                 wage: float = 0.0, share: float = 0.0) -> CompanionLink:
        """Add an NPC as companion, partner, or employee."""
        link = CompanionLink(
            npc_id=npc_id, name=name, role=role,
            wage_daily=wage, share_pct=share,
        )
        self.links[npc_id] = link
        return link

    def dismiss(self, npc_id: str) -> Optional[CompanionLink]:
        return self.links.pop(npc_id, None)

    def get(self, npc_id: str) -> Optional[CompanionLink]:
        return self.links.get(npc_id)

    def is_companion(self, npc_id: str) -> bool:
        link = self.links.get(npc_id)
        return link is not None and link.role in (Role.COMPANION, Role.PARTNER)

    def is_employee(self, npc_id: str) -> bool:
        link = self.links.get(npc_id)
        return link is not None and link.role == Role.EMPLOYEE

    def all_companions(self) -> List[CompanionLink]:
        return [l for l in self.links.values()
                if l.role in (Role.COMPANION, Role.PARTNER)]

    def all_employees(self) -> List[CompanionLink]:
        return [l for l in self.links.values() if l.role == Role.EMPLOYEE]

    def assign_task(self, npc_id: str, npc: "NPC",
                     task_key: str, current_minute: int,
                     is_custom: bool = False
                     ) -> Tuple[bool, str]:
        """
        Assign a task to a companion/employee.
        Returns (accepted, message).
        """
        link = self.links.get(npc_id)
        if not link:
            return False, "This person doesn't work with you."
        if link.currently_tasked:
            return False, f"{link.name} is already busy with something."

        accepted, msg = will_accept_task(link, npc, task_key, is_custom)
        if not accepted:
            link.tasks_refused += 1
            link.morale = max(0, link.morale - 2)
            return False, msg

        task_def = TASK_DEFS.get(task_key)
        duration = task_def.base_minutes if task_def else 60

        link.currently_tasked = True
        link.current_task = task_key
        link.task_started_minute = current_minute
        link.task_duration = duration

        return True, msg

    def check_completions(self, current_minute: int,
                           npc_lookup: dict,
                           gold_bias: float = 0.3
                           ) -> List[TaskResult]:
        """
        Check if any assigned tasks have completed.
        npc_lookup: dict of npc_id → NPC object for skill checks.
        Returns list of TaskResults for completed tasks.
        """
        results = []
        for link in self.links.values():
            if not link.currently_tasked:
                continue
            elapsed = current_minute - link.task_started_minute
            if elapsed >= link.task_duration:
                npc = npc_lookup.get(link.npc_id)
                if npc:
                    result = resolve_task(link, npc, link.current_task or "",
                                           gold_bias)
                    results.append(result)
                else:
                    # NPC not found — auto-complete
                    link.currently_tasked = False
                    link.current_task = None
        return results

    def tick_daily(self) -> List[str]:
        """Daily morale/loyalty updates and wage costs."""
        msgs = []
        for link in self.links.values():
            link.days_with_player += 1

            # Loyalty builds over time (companions faster)
            if link.role == Role.COMPANION:
                link.loyalty = min(100, link.loyalty + 0.5)
            elif link.role == Role.PARTNER:
                link.loyalty = min(100, link.loyalty + 0.3)
            else:
                link.loyalty = min(100, link.loyalty + 0.1)

            # Employees with no wage lose morale fast
            if link.role == Role.EMPLOYEE and link.wage_daily <= 0:
                link.morale = max(0, link.morale - 8)
                if link.morale <= 0:
                    msgs.append(f"{link.name} has had enough and leaves.")

        return msgs

    def total_daily_wages(self) -> float:
        return sum(l.wage_daily for l in self.links.values()
                   if l.role == Role.EMPLOYEE)

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> Dict:
        return {
            nid: {
                "npc_id": l.npc_id, "name": l.name, "role": l.role,
                "wage_daily": l.wage_daily, "share_pct": l.share_pct,
                "days_with_player": l.days_with_player,
                "tasks_completed": l.tasks_completed,
                "tasks_refused": l.tasks_refused,
                "morale": l.morale, "loyalty": l.loyalty,
                "currently_tasked": l.currently_tasked,
                "current_task": l.current_task,
                "task_started_minute": l.task_started_minute,
                "task_duration": l.task_duration,
            }
            for nid, l in self.links.items()
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "CompanionManager":
        mgr = cls()
        for nid, ld in d.items():
            mgr.links[nid] = CompanionLink(**ld)
        return mgr


# ============================================================================
#  DELEGATE TASKS MENU UI
# ============================================================================

WHITE  = (255, 255, 255)
YELLOW = (255, 220,  60)
CYAN   = ( 80, 200, 200)
GREEN  = ( 80, 180,  80)
GREY   = (120, 120, 120)
DGREY  = ( 60,  60,  60)
ORANGE = (210, 150,  50)
BG     = ( 15,  15,  30)
BG_SEL = ( 35,  35,  65)

# Task categories to section headers
_CAT_LABELS = {
    "gather": "GATHERING",
    "camp":   "CAMP",
    "build":  "BUILDING",
    "haul":   "HAULING",
    "combat": "SCOUTING & GUARD",
}

# Ordered categories
_CAT_ORDER = ["gather", "camp", "build", "haul", "combat"]


def delegate_menu(con: tcod.console.Console, ctx,
                   link: CompanionLink,
                   npc: "NPC",
                   current_minute: int,
                   companion_mgr: "CompanionManager"
                   ) -> Optional[Tuple[bool, str]]:
    """
    Show the delegate tasks menu for a companion/employee.
    Returns (accepted, message) or None if cancelled.

    Layout:
        ┌── DELEGATE TO: John Smith (Companion) ──┐
        │ GATHERING                                │
        │ > Go fishing                             │
        │   Chop wood                              │
        │   ...                                    │
        │ CAMP                                     │
        │   Cook food                              │
        │   ...                                    │
        │                                          │
        │── Type custom task: ___█ ────────────────│
        │ ↑↓=Select  Enter=Assign  Esc=Cancel      │
        └──────────────────────────────────────────┘
    """
    W, H = 52, 30
    SW, SH = con.width, con.height
    X = (SW - W) // 2
    Y = (SH - H) // 2
    VISIBLE = H - 9

    # Build task list with category headers
    entries: List[Tuple[str, str, bool]] = []   # (label, key_or_"header", is_header)
    for cat in _CAT_ORDER:
        tasks_in_cat = [td for td in TASK_DEFS.values() if td.category == cat]
        if not tasks_in_cat:
            continue
        entries.append((_CAT_LABELS.get(cat, cat), "", True))
        for td in tasks_in_cat:
            entries.append((td.label, td.key, False))

    selected = 0
    # Skip first entry if it's a header
    while selected < len(entries) and entries[selected][2]:
        selected += 1
    scroll = 0
    typing = False
    text_input = ""

    while True:
        # ── Draw ──────────────────────────────────────────────────────
        con.draw_rect(X, Y, W, H, ord(" "), fg=WHITE, bg=BG)
        for bx in range(X, X + W):
            con.print(bx, Y, "─", fg=DGREY, bg=BG)
            con.print(bx, Y+H-1, "─", fg=DGREY, bg=BG)
        for by in range(Y, Y + H):
            con.print(X, by, "│", fg=DGREY, bg=BG)
            con.print(X+W-1, by, "│", fg=DGREY, bg=BG)
        con.print(X, Y, "┌", fg=DGREY, bg=BG)
        con.print(X+W-1, Y, "┐", fg=DGREY, bg=BG)
        con.print(X, Y+H-1, "└", fg=DGREY, bg=BG)
        con.print(X+W-1, Y+H-1, "┘", fg=DGREY, bg=BG)

        title = f" DELEGATE TO: {link.name} ({link.role_label}) "
        con.print(X + max(1, (W - len(title)) // 2), Y, title[:W-2],
                  fg=YELLOW, bg=BG)

        # Status line
        status = (f"Morale: {link.morale:.0f}  "
                  f"Loyalty: {link.loyalty:.0f}  "
                  f"Tasks done: {link.tasks_completed}")
        con.print(X + 2, Y + 1, status[:W-4], fg=GREY, bg=BG)

        # Task list
        row = Y + 3
        drawn = 0
        for i in range(scroll, len(entries)):
            if drawn >= VISIBLE:
                break
            label, key, is_header = entries[i]

            if is_header:
                con.print(X + 2, row, label, fg=GREY, bg=BG)
            else:
                is_sel = (i == selected and not typing)
                fg = CYAN if is_sel else WHITE
                bg_c = BG_SEL if is_sel else BG
                marker = ">" if is_sel else " "
                con.print(X + 2, row, f"{marker} {label}"[:W-4], fg=fg, bg=bg_c)

            row += 1
            drawn += 1

        # Input line
        input_y = Y + H - 5
        for bx in range(X + 1, X + W - 1):
            con.print(bx, input_y, "─", fg=DGREY, bg=BG)

        if typing:
            caret = "█"
            full = f"Custom: {text_input}{caret}"
            max_w = W - 4
            con.print(X + 2, input_y + 1, full[:max_w], fg=YELLOW, bg=BG)
            if len(full) > max_w:
                con.print(X + 2, input_y + 2, full[max_w:max_w*2], fg=YELLOW, bg=BG)
        else:
            con.print(X + 2, input_y + 1,
                      "Type for custom task", fg=DGREY, bg=BG)

        help_text = ("Enter=Submit  Esc=Clear" if typing
                     else "↑↓=Select  Enter=Assign  Esc=Cancel")
        con.print(X + 2, Y + H - 2, help_text[:W-4], fg=DGREY, bg=BG)

        ctx.present(con)

        # ── Input ─────────────────────────────────────────────────────
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.TextInput) and typing:
                text_input += event.text
                continue

            if not isinstance(event, tcod.event.KeyDown):
                continue

            sym = event.sym
            K = tcod.event.KeySym

            if typing:
                if sym == K.ESCAPE:
                    if text_input:
                        text_input = ""
                    else:
                        typing = False
                        ctx.sdl_window.stop_text_input()
                elif sym == K.BACKSPACE:
                    if text_input:
                        text_input = text_input[:-1]
                    else:
                        typing = False
                        ctx.sdl_window.stop_text_input()
                elif sym in (K.RETURN, K.KP_ENTER) and text_input.strip():
                    ctx.sdl_window.stop_text_input()
                    # Custom task via LLM
                    accepted, msg = companion_mgr.assign_task(
                        link.npc_id, npc, text_input.strip(),
                        current_minute, is_custom=True)
                    return accepted, msg
            else:
                if sym == K.ESCAPE:
                    return None

                elif sym in (K.DOWN, K.KP_2):
                    selected += 1
                    while selected < len(entries) and entries[selected][2]:
                        selected += 1
                    selected = min(selected, len(entries) - 1)
                    if selected >= scroll + VISIBLE:
                        scroll += 1

                elif sym in (K.UP, K.KP_8):
                    selected -= 1
                    while selected >= 0 and entries[selected][2]:
                        selected -= 1
                    selected = max(0, selected)
                    if selected < scroll:
                        scroll = selected

                elif sym in (K.RETURN, K.KP_ENTER):
                    if selected < len(entries) and not entries[selected][2]:
                        _, task_key, _ = entries[selected]
                        accepted, msg = companion_mgr.assign_task(
                            link.npc_id, npc, task_key, current_minute)
                        return accepted, msg

                else:
                    typing = True
                    text_input = ""
                    ctx.sdl_window.start_text_input()
