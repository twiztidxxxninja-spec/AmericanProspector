"""
src/business.py

Entrepreneurship and business empire system for American Prospector.

The player can start and run ANY kind of business — general store, saloon,
mining company, newspaper, invention workshop, ferry service, freight line.
Businesses grow through 5 tiers from startup to empire. Long-term tycoon
play (Carnegie / Rothschild style) is a viable win path.

Key classes:
    BusinessBlueprint   — LLM-categorized template for a business type
    BusinessEntity      — a running business instance with full simulation
    Employee            — an NPC assigned to work at a business
    FinancialRecord     — daily/monthly P&L tracking
    BusinessManager     — manages all player businesses, daily ticks, events
    BusinessEvent       — random events that affect business operations

Growth tiers:
    1. Startup     — 0-1 employees, minimal revenue, hand-run
    2. Established — 2-5 employees, regular customers, stable
    3. Prosperous  — 6-15 employees, expanding, good reputation
    4. Enterprise  — 16-50 employees, multiple operations, regional influence
    5. Empire      — 50+ employees, political power, legacy wealth

Integration:
    Engine holds BusinessManager.
    Economy.ReputationTracker feeds into business revenue.
    NPC system provides employees (NPCExpanded assigned to business).
    Town buildings can be player-owned (BuildingDef from town_gen.py).
    Item factory produces goods the business sells.
"""

import json
import random
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.llm_client import LLMClient


# ============================================================================
#  GROWTH TIERS
# ============================================================================

class Tier:
    STARTUP     = 1
    ESTABLISHED = 2
    PROSPEROUS  = 3
    ENTERPRISE  = 4
    EMPIRE      = 5


TIER_LABELS = {
    1: "Startup",
    2: "Established",
    3: "Prosperous",
    4: "Enterprise",
    5: "Empire",
}

TIER_THRESHOLDS = {
    # (min_employees, min_reputation, min_revenue_daily, min_days_operating)
    2: (2,   10,   2.0,   30),
    3: (6,   30,   8.0,   90),
    4: (16,  50,  30.0,  180),
    5: (50,  75, 100.0,  365),
}


# ============================================================================
#  PRICING STRATEGIES
# ============================================================================

PRICE_STRATEGIES = {
    "undercut": {
        "revenue_mult": 0.7,
        "customer_mult": 1.5,
        "rep_delta": 1,           # builds goodwill
        "label": "Low prices — high volume",
    },
    "standard": {
        "revenue_mult": 1.0,
        "customer_mult": 1.0,
        "rep_delta": 0,
        "label": "Fair market price",
    },
    "premium": {
        "revenue_mult": 1.4,
        "customer_mult": 0.6,
        "rep_delta": 0,
        "label": "High prices — fewer customers",
    },
    "gouging": {
        "revenue_mult": 2.0,
        "customer_mult": 0.3,
        "rep_delta": -2,          # people resent price gouging
        "label": "Extreme markup — risk of backlash",
    },
}


# ============================================================================
#  PREDEFINED BUSINESS TYPES
# ============================================================================

@dataclass
class BusinessBlueprint:
    """Template for a business type. Predefined or LLM-generated."""
    key: str
    name: str                       # "General Store"
    description: str
    category: str                   # "retail"|"service"|"production"|"transport"|"extraction"|"custom"
    startup_cost: float             # minimum dollars to get started
    daily_base_revenue: float       # base revenue per day at tier 1
    daily_base_expenses: float      # base expenses per day at tier 1
    revenue_per_employee: float     # additional revenue per employee
    wage_per_employee: float        # daily wage per employee
    skill_used: str                 # primary skill ("trading", "engineering", etc.)
    building_required: str          # "" or building key from town_gen
    inventory_categories: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    source: str = "builtin"         # "builtin" | "llm"
    # Production chains — what this business consumes and produces daily
    consumes: List[Tuple[str, int]] = field(default_factory=list)  # [(item_id, qty_per_day)]
    produces: List[Tuple[str, int]] = field(default_factory=list)  # [(item_id, qty_per_day)]


BUSINESS_BLUEPRINTS: Dict[str, BusinessBlueprint] = {}

def _bb(key, name, desc, cat, startup, rev, exp, rev_emp, wage, skill,
        bldg="", inv_cats=None, tags=None):
    BUSINESS_BLUEPRINTS[key] = BusinessBlueprint(
        key=key, name=name, description=desc, category=cat,
        startup_cost=startup, daily_base_revenue=rev,
        daily_base_expenses=exp, revenue_per_employee=rev_emp,
        wage_per_employee=wage, skill_used=skill,
        building_required=bldg,
        inventory_categories=inv_cats or [],
        tags=tags or [],
    )

# Retail
_bb("general_store", "General Store",
    "Supply store selling tools, food, and provisions to miners.",
    "retail", 200, 3.0, 0.8, 1.5, 1.0, "trading",
    bldg="general_store", inv_cats=["tool", "food", "material"])
_bb("outfitter", "Outfitter",
    "Clothing and outdoor equipment for miners and travelers.",
    "retail", 150, 2.5, 0.6, 1.2, 1.0, "trading",
    bldg="clothing_store", inv_cats=["clothing"])
_bb("gun_shop", "Gun Shop",
    "Firearms, ammunition, and weapon repair.",
    "retail", 300, 2.0, 0.5, 1.0, 1.2, "firearms",
    bldg="general_store", inv_cats=["weapon"])

# Service
_bb("saloon", "Saloon",
    "Liquor, gambling, entertainment, and gossip.",
    "service", 250, 4.0, 1.5, 2.0, 0.8, "trading",
    bldg="saloon", tags=["social_hub", "gossip_source"])
_bb("hotel", "Hotel / Boarding House",
    "Room and board for travelers and miners.",
    "service", 300, 3.5, 1.2, 1.5, 0.8, "trading",
    bldg="hotel")
_bb("laundry", "Laundry Service",
    "Washing and mending clothes. Always in demand at the diggings.",
    "service", 20, 1.5, 0.3, 0.8, 0.5, "survival")
_bb("barbershop", "Barbershop",
    "Haircuts, shaves, and minor surgery.",
    "service", 30, 1.2, 0.2, 0.6, 0.6, "firstAid",
    bldg="barber")
_bb("ferry", "Ferry Service",
    "River crossing service. Monopoly potential at key fords.",
    "service", 100, 3.0, 0.5, 1.0, 0.8, "driving",
    tags=["location_dependent"])
_bb("stable", "Livery Stable",
    "Horse boarding, mule rental, and animal care.",
    "service", 200, 2.5, 1.0, 1.0, 0.8, "survival",
    bldg="livery")

# Production
_bb("blacksmith_shop", "Blacksmith Shop",
    "Tool making, repair, and horseshoeing.",
    "production", 150, 3.0, 0.8, 1.5, 1.2, "engineering",
    bldg="blacksmith", inv_cats=["tool", "weapon"])
_bb("sawmill", "Sawmill",
    "Lumber production. Critical near new settlements.",
    "production", 500, 5.0, 2.0, 2.5, 1.0, "engineering",
    tags=["resource_dependent"])
_bb("bakery", "Bakery",
    "Bread and baked goods. Always in demand.",
    "production", 80, 2.0, 0.8, 1.0, 0.6, "cooking",
    inv_cats=["food"])
_bb("workshop", "Invention Workshop",
    "Custom manufacturing and experimental devices.",
    "production", 200, 1.0, 0.5, 2.0, 1.5, "engineering",
    tags=["custom_items", "invention"])

# Extraction
_bb("mining_company", "Mining Company",
    "Organized mining operation with hired labor.",
    "extraction", 500, 5.0, 3.0, 3.0, 1.5, "geology",
    tags=["resource_dependent", "high_risk"])
_bb("logging_outfit", "Logging Outfit",
    "Timber cutting and hauling operation.",
    "extraction", 300, 4.0, 1.5, 2.0, 1.2, "survival")

# Transport
_bb("freight_line", "Freight Line",
    "Hauling goods between towns by wagon or mule train.",
    "transport", 400, 4.0, 2.0, 2.0, 1.0, "driving",
    tags=["multi_location"])
_bb("express_service", "Express / Mail Service",
    "Fast delivery of letters, gold, and small packages.",
    "transport", 200, 3.0, 1.0, 2.0, 1.5, "driving",
    tags=["multi_location"])

# Information
_bb("newspaper", "Newspaper",
    "Printing news, advertisements, and public notices.",
    "service", 400, 2.0, 1.0, 1.0, 1.0, "literacy",
    bldg="newspaper", tags=["influence", "gossip_source"])
_bb("assay_office", "Assay Office",
    "Testing and certifying ore and gold purity.",
    "service", 300, 3.0, 0.5, 2.0, 1.5, "assaying",
    bldg="assay_office")

# Production chains — what each business consumes and produces per day.
# A full day of work with employees. Quantities scale with tier/employees.
BUSINESS_BLUEPRINTS["sawmill"].consumes = [("log", 5)]
BUSINESS_BLUEPRINTS["sawmill"].produces = [("plank", 12)]
BUSINESS_BLUEPRINTS["bakery"].consumes = [("hardtack", 3)]  # flour stand-in
BUSINESS_BLUEPRINTS["bakery"].produces = [("bread", 15)]
BUSINESS_BLUEPRINTS["blacksmith_shop"].consumes = [("iron_ingot", 2)]
BUSINESS_BLUEPRINTS["blacksmith_shop"].produces = [("nails", 20), ("horseshoe", 4)]


# ============================================================================
#  EMPLOYEE
# ============================================================================

@dataclass
class Employee:
    """An NPC assigned to work at a player business."""
    npc_id: str
    name: str
    role: str                   # "clerk"|"laborer"|"manager"|"guard"|"specialist"
    skill_level: int = 0        # relevant skill (0-10)
    wage_daily: float = 1.0     # dollars per day
    morale: float = 70.0        # 0-100, affects productivity
    days_employed: int = 0
    productivity: float = 1.0   # 0.0-2.0 multiplier on revenue contribution

    def tick_morale(self, on_time_pay: bool, good_conditions: bool) -> None:
        if on_time_pay:
            self.morale = min(100, self.morale + 1)
        else:
            self.morale = max(0, self.morale - 5)
        if good_conditions:
            self.morale = min(100, self.morale + 0.5)
        # Productivity tracks morale
        self.productivity = max(0.2, self.morale / 70.0)


# ============================================================================
#  FINANCIAL RECORD
# ============================================================================

@dataclass
class DailyFinance:
    day: int
    revenue: float = 0.0
    expenses: float = 0.0
    wages: float = 0.0
    supplies: float = 0.0
    other_costs: float = 0.0

    @property
    def profit(self) -> float:
        return self.revenue - self.expenses - self.wages - self.supplies - self.other_costs


# ============================================================================
#  BUSINESS EVENT
# ============================================================================

@dataclass
class BusinessEvent:
    """A random event affecting a business."""
    event_type: str             # "boom"|"bust"|"theft"|"fire"|"competitor"|"opportunity"
    description: str
    revenue_mult: float = 1.0   # temporary multiplier (1.0 = no change)
    expense_delta: float = 0.0  # one-time cost
    reputation_delta: float = 0.0
    duration_days: int = 1      # how long the effect lasts
    day_started: int = 0


# Event templates by category
_EVENT_POOL: Dict[str, List[dict]] = {
    "positive": [
        {"type": "boom", "desc": "A new gold strike nearby brings a flood of customers.",
         "rev_mult": 1.8, "rep": +5, "dur": 14},
        {"type": "opportunity", "desc": "A large freight order comes in from a nearby camp.",
         "rev_mult": 1.5, "rep": +3, "dur": 7},
        {"type": "opportunity", "desc": "A traveling newspaperman writes a favorable article.",
         "rev_mult": 1.3, "rep": +8, "dur": 21},
        {"type": "boom", "desc": "Winter sets in and your supplies are the only ones around.",
         "rev_mult": 2.0, "rep": +2, "dur": 30},
    ],
    "negative": [
        {"type": "theft", "desc": "Someone broke in overnight. Goods are missing.",
         "exp": -25.0, "rep": -2, "dur": 1},
        {"type": "competitor", "desc": "A new competitor opens up down the street.",
         "rev_mult": 0.7, "rep": 0, "dur": 30},
        {"type": "fire", "desc": "A small fire damages part of the building.",
         "exp": -50.0, "rev_mult": 0.5, "rep": -3, "dur": 14},
        {"type": "bust", "desc": "The local diggings are playing out. Miners are leaving.",
         "rev_mult": 0.5, "rep": 0, "dur": 30},
        {"type": "theft", "desc": "An employee was caught skimming from the till.",
         "exp": -15.0, "rep": -5, "dur": 1},
    ],
    "neutral": [
        {"type": "opportunity", "desc": "A merchant offers a bulk supply deal.",
         "exp": -30.0, "rev_mult": 1.2, "dur": 14},
        {"type": "competitor", "desc": "The town sheriff asks you to extend credit to deputies.",
         "exp": -5.0, "rep": +5, "dur": 7},
    ],
}


# ============================================================================
#  BUSINESS ENTITY
# ============================================================================

class BusinessEntity:
    """
    A running business instance with full simulation.
    Grows through tiers, tracks employees, finances, events.
    """

    def __init__(self, blueprint_key: str, name: str,
                 world_x: int, world_y: int, day_founded: int,
                 region: str = "", settlement_type: str = "small_town"):
        bp = BUSINESS_BLUEPRINTS.get(blueprint_key)
        if not bp:
            bp = BUSINESS_BLUEPRINTS.get("general_store")

        self.id: str = f"biz_{id(self)}"
        self.blueprint_key: str = blueprint_key
        self.name: str = name
        self.world_x: int = world_x
        self.world_y: int = world_y
        self.region: str = region
        self.settlement_type: str = settlement_type
        self.day_founded: int = day_founded
        self.active: bool = True

        # Blueprint stats
        self.category: str = bp.category
        self.description: str = bp.description
        self.skill_used: str = bp.skill_used
        self.base_revenue: float = bp.daily_base_revenue
        self.base_expenses: float = bp.daily_base_expenses
        self.rev_per_employee: float = bp.revenue_per_employee
        self.wage_per_employee: float = bp.wage_per_employee
        self.tags: List[str] = list(bp.tags)

        # Growth
        self.tier: int = Tier.STARTUP
        self.reputation: float = 5.0    # business rep (0-100)
        self.days_operating: int = 0

        # Financials
        self.total_invested: float = bp.startup_cost
        self.total_revenue: float = 0.0
        self.total_expenses: float = 0.0
        self.cash_reserve: float = 0.0
        self.debt: float = 0.0
        self.history: List[DailyFinance] = []

        # Employees
        self.employees: List[Employee] = []

        # Active events
        self.events: List[BusinessEvent] = []

        # Inventory (for retail/production businesses)
        self.stock_value: float = 0.0
        self.custom_products: List[str] = []  # item IDs the business sells
        self.inventory: List[Any] = []       # actual Item objects stored at business

        # Remote management
        self.manager_npc_id: str = ""         # NPC running things when player is away
        self.standing_orders: List[Dict] = [] # always-active rules
        self.pending_orders: List[str] = []   # unsent instructions
        self.last_report_day: int = 0         # day of last manager letter
        self.last_update_day: int = day_founded  # day player last had fresh data
        self.paused: bool = False             # no manager + player away = paused

        # Pricing strategy
        self.price_strategy: str = "standard"  # key into PRICE_STRATEGIES

        # Market knowledge (prices player has learned)
        self.known_prices: Dict[str, Dict[str, float]] = {}  # item_id → {location: price}

        # Active shipments in transit
        self.shipments: List[Dict] = []  # each is a ship_goods() result dict

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def tier_label(self) -> str:
        return TIER_LABELS.get(self.tier, "Unknown")

    @property
    def employee_count(self) -> int:
        return len(self.employees)

    @property
    def avg_productivity(self) -> float:
        if not self.employees:
            return 1.0
        return sum(e.productivity for e in self.employees) / len(self.employees)

    @property
    def daily_wages(self) -> float:
        return sum(e.wage_daily for e in self.employees)

    @property
    def net_daily(self) -> float:
        """Estimated daily profit."""
        return self._calc_revenue() - self._calc_expenses()

    # ── Employee management ────────────────────────────────────────────

    def hire(self, npc_id: str, name: str, role: str = "laborer",
             skill: int = 0, wage: float = 1.0) -> Employee:
        emp = Employee(npc_id=npc_id, name=name, role=role,
                       skill_level=skill, wage_daily=wage)
        self.employees.append(emp)
        return emp

    def fire(self, npc_id: str) -> Optional[Employee]:
        for i, e in enumerate(self.employees):
            if e.npc_id == npc_id:
                return self.employees.pop(i)
        return None

    def get_employee(self, npc_id: str) -> Optional[Employee]:
        for e in self.employees:
            if e.npc_id == npc_id:
                return e
        return None

    # ── Revenue / Expense calculation ──────────────────────────────────

    def _calc_revenue(self) -> float:
        """Calculate today's gross revenue from two sources:
        1. Service revenue (drinks, rooms — consumes supplies from inventory)
        2. Inventory sales (NPC customers buy actual items from stock)"""
        # ── Service revenue (consumes supplies if available) ──────
        rev = self.base_revenue
        # Bars/saloons need whiskey to make drink money
        # Hotels need bedrolls/blankets, bakeries need ingredients
        supply_bonus = self._consume_supplies()
        rev += supply_bonus

        # Employee contribution
        for emp in self.employees:
            rev += self.rev_per_employee * emp.productivity

        # ── Inventory-driven revenue (NPC customers) ──────────────
        customer_rev = self._process_customers()
        rev += customer_rev

        # ── Pricing strategy ──────────────────────────────────────
        strategy = PRICE_STRATEGIES.get(self.price_strategy,
                                         PRICE_STRATEGIES["standard"])
        rev *= strategy["revenue_mult"]

        # Pricing affects reputation
        rep_delta = strategy.get("rep_delta", 0)
        if rep_delta:
            self.reputation = max(0, min(100, self.reputation + rep_delta * 0.1))

        # ── Modifiers ─────────────────────────────────────────────
        # Reputation bonus (0-100 → 0.5x to 2.0x)
        rep_mult = 0.5 + (self.reputation / 100.0) * 1.5
        rev *= rep_mult

        # Tier scaling
        rev *= 1.0 + (self.tier - 1) * 0.3

        # Active event modifiers
        for evt in self.events:
            rev *= evt.revenue_mult

        # Settlement size matters
        sett_mult = {
            "mining_camp_small": 0.4, "mining_camp_medium": 0.7,
            "boomtown": 1.2, "small_town": 1.0,
            "trading_post": 0.5, "city": 1.5,
        }.get(self.settlement_type, 1.0)
        rev *= sett_mult

        # Competition penalty on base revenue (not just customer sales)
        if self._all_businesses:
            competitors = sum(1 for b in self._all_businesses
                              if b.id != self.id and b.active and not b.paused
                              and b.world_x == self.world_x and b.world_y == self.world_y
                              and b.category == self.category)
            if competitors > 0:
                rev *= 1.0 / (1.0 + competitors * 0.3)

        # Randomness (±15%)
        rev *= random.uniform(0.85, 1.15)

        return round(max(0, rev), 2)

    def _manager_auto_decisions(self):
        """Manager makes autonomous decisions based on skill and standing orders.
        Higher skill managers make better decisions."""
        if not self.manager_npc_id:
            return
        # Find manager's skill level
        mgr_skill = 3  # default
        for emp in self.employees:
            if emp.npc_id == self.manager_npc_id:
                mgr_skill = emp.skill_level
                break

        # ── Execute standing orders ──────────────────────────────────
        for order in self.standing_orders:
            otype = order.get("type", "")
            if otype == "maintain_stock":
                item_id = order.get("item_id", "")
                min_qty = order.get("min_qty", 5)
                max_price = order.get("max_price", 2.0)
                current = sum(1 for i in self.inventory if i.id == item_id)
                if current < min_qty:
                    price_mult = max(0.7, 1.3 - mgr_skill * 0.06)
                    qty = min_qty - current
                    cost = qty * max_price * price_mult
                    if self.cash_reserve >= cost:
                        self.cash_reserve -= cost
                        try:
                            from src.items import make_item
                            for _ in range(qty):
                                self.inventory.append(make_item(item_id))
                        except Exception:
                            pass
            elif otype == "set_price":
                strategy_key = order.get("strategy", "standard")
                if strategy_key in PRICE_STRATEGIES:
                    self.price_strategy = strategy_key

            elif otype == "hire_if_busy" and mgr_skill >= 4:
                # Hire a laborer if revenue exceeds threshold
                rev_threshold = order.get("revenue_threshold", 5.0)
                max_employees = order.get("max_employees", 10)
                if len(self.employees) < max_employees:
                    avg_rev = sum(h.revenue for h in self.history[-7:]
                                 ) / max(len(self.history[-7:]), 1)
                    if avg_rev > rev_threshold:
                        # Auto-hire at standard wage
                        wage = self.wage_per_employee
                        self.employees.append(Employee(
                            npc_id=f"hired_{len(self.employees)}",
                            name=f"Laborer #{len(self.employees) + 1}",
                            role="laborer", skill_level=2,
                            wage_daily=wage, morale=50.0,
                            days_employed=0, productivity=0.8,
                        ))

            elif otype == "fire_if_slow" and mgr_skill >= 5:
                # Fire worst employee if revenue drops
                rev_threshold = order.get("revenue_threshold", 2.0)
                if len(self.employees) > 1:
                    avg_rev = sum(h.revenue for h in self.history[-7:]
                                 ) / max(len(self.history[-7:]), 1)
                    if avg_rev < rev_threshold:
                        # Fire lowest productivity non-manager
                        non_mgr = [e for e in self.employees
                                   if e.npc_id != self.manager_npc_id]
                        if non_mgr:
                            worst = min(non_mgr, key=lambda e: e.productivity)
                            self.employees.remove(worst)

        # ── Auto-restock if low on key supplies and has cash ─────────
        _RESTOCK_MAP = {
            "saloon": [("whiskey", 10, 0.50)],
            "bakery": [("hardtack", 10, 0.15)],
            "general_store": [("hardtack", 5, 0.15), ("salt", 3, 0.30),
                              ("rope_10ft", 3, 0.20)],
            "hotel": [("candle", 3, 0.10)],
            "brothel": [("whiskey", 5, 0.50)],
            "dancehall": [("whiskey", 5, 0.50)],
            "blacksmith_shop": [("iron_ingot", 3, 1.00)],
            "fur_trading": [("salt", 5, 0.30)],
            "freight_line": [("rope_10ft", 3, 0.20)],
            "mining_company": [("dynamite", 5, 1.50), ("candle", 5, 0.10)],
        }
        restock_list = _RESTOCK_MAP.get(self.blueprint_key, [])
        for item_id, min_qty, buy_price in restock_list:
            current = sum(1 for i in self.inventory if i.id == item_id)
            if current < min_qty and self.cash_reserve > buy_price * 5:
                # Manager buys stock (better skill = better prices)
                price_mult = max(0.7, 1.3 - mgr_skill * 0.06)
                qty_to_buy = min_qty - current + 5  # buffer
                cost = qty_to_buy * buy_price * price_mult
                if self.cash_reserve >= cost:
                    self.cash_reserve -= cost
                    try:
                        from src.items import make_item
                        for _ in range(qty_to_buy):
                            self.inventory.append(make_item(item_id))
                    except Exception:
                        pass

    def _consume_supplies(self) -> float:
        """Consume inventory supplies to generate service revenue.
        Saloons use whiskey, bakeries use ingredients, etc.
        Returns bonus revenue from consumed supplies."""
        if not self.inventory:
            return 0.0

        # What each business type consumes and how much revenue it generates
        _SUPPLY_MAP = {
            "saloon": [("whiskey", 3.0)],        # 1 whiskey → $3 in drinks
            "hotel": [("bedroll", 0.5), ("candle", 0.2)],
            "bakery": [("hardtack", 1.5)],        # uses flour/grain → bread sales
            "brewery": [("whiskey", 0.0)],         # produces whiskey, doesn't consume
            "boarding_house": [("hardtack", 0.8)],
            "dancehall": [("whiskey", 2.5)],
            "brothel": [("whiskey", 2.0)],
        }

        bp_key = self.blueprint_key
        supplies = _SUPPLY_MAP.get(bp_key, [])
        if not supplies:
            return 0.0

        bonus = 0.0
        customers = {
            "mining_camp_small": 2, "mining_camp_medium": 4,
            "boomtown": 8, "small_town": 6,
            "trading_post": 3, "city": 15,
        }.get(self.settlement_type, 4)

        for supply_id, rev_per_unit in supplies:
            if rev_per_unit <= 0:
                continue
            # Consume up to customer count of this supply
            consumed = 0
            for _ in range(customers):
                for i, item in enumerate(self.inventory):
                    if item.id == supply_id:
                        if getattr(item, 'stackable', False) and item.quantity > 1:
                            item.quantity -= 1
                        else:
                            self.inventory.pop(i)
                        consumed += 1
                        break
            bonus += consumed * rev_per_unit

        # Gambling revenue — if business has playing cards or dice
        has_cards = any(i.id in ("playing_cards", "dice_set", "marked_cards",
                                 "gambling_table", "faro_layout")
                        for i in self.inventory)
        if has_cards and bp_key in ("saloon", "dancehall", "brothel", "hotel"):
            # House take from NPC gambling (~$0.50-2.00 per gambler)
            gamblers = max(1, customers // 3)
            house_take = gamblers * random.uniform(0.50, 2.00)
            bonus += house_take

        return round(bonus, 2)

    _all_businesses = None  # set by BusinessManager before tick

    def _process_customers(self) -> float:
        """Simulate NPC customers buying from inventory.
        Returns revenue from actual item sales."""
        if not self.inventory:
            return 0.0

        # Customer count based on settlement type (proxy for population)
        base_customers = {
            "mining_camp_small": 2, "mining_camp_medium": 5,
            "boomtown": 12, "small_town": 8,
            "trading_post": 4, "city": 25,
        }.get(self.settlement_type, 5)

        # Need a clerk/seller employee to actually make sales
        has_seller = any(e.role in ("clerk", "manager", "specialist")
                         for e in self.employees)
        if not has_seller and not self.manager_npc_id:
            # No one at the counter — drastically fewer sales
            base_customers = max(1, base_customers // 5)

        # Competition — split customers with same-type businesses at same location
        if self._all_businesses:
            competitors = sum(1 for b in self._all_businesses
                              if b.id != self.id and b.active and not b.paused
                              and b.world_x == self.world_x and b.world_y == self.world_y
                              and b.category == self.category)
            if competitors > 0:
                base_customers = max(1, base_customers // (competitors + 1))

        # Reputation affects foot traffic
        traffic_mult = 0.3 + (self.reputation / 100.0) * 1.4
        customers = max(1, int(base_customers * traffic_mult))

        revenue = 0.0
        rng = random.Random()

        for _ in range(customers):
            if not self.inventory:
                break
            # Each customer has a 40% chance of buying something
            if rng.random() < 0.4:
                # Pick a random item from inventory
                idx = rng.randint(0, len(self.inventory) - 1)
                item = self.inventory[idx]
                # Sell at marked-up price (1.3-2.0x base value)
                markup = 1.3 + (self.reputation / 200.0)
                sell_price = item.base_value * markup
                revenue += sell_price
                # Remove from inventory
                if getattr(item, 'stackable', False) and getattr(item, 'quantity', 1) > 1:
                    item.quantity -= 1
                else:
                    self.inventory.pop(idx)
                # Track stock value change
                self.stock_value = sum(getattr(i, 'base_value', 0) * getattr(i, 'quantity', 1)
                                       for i in self.inventory)

        return round(revenue, 2)

    def _calc_expenses(self) -> float:
        """Calculate today's total expenses."""
        exp = self.base_expenses
        exp += self.daily_wages

        # Tier scaling (bigger business = more overhead)
        exp *= 1.0 + (self.tier - 1) * 0.2

        return round(max(0, exp), 2)

    # ── Daily tick ─────────────────────────────────────────────────────

    def tick_daily(self, current_day: int,
                    player_rep: float = 0.0) -> DailyFinance:
        """
        Process one day of business operations.
        Returns the day's financial record.
        """
        self.days_operating += 1

        # Calculate financials
        revenue = self._calc_revenue()
        expenses = self._calc_expenses()
        wages = self.daily_wages

        record = DailyFinance(
            day=current_day, revenue=revenue,
            expenses=expenses - wages,  # separate wages from other expenses
            wages=wages,
        )

        self.total_revenue += revenue
        self.total_expenses += expenses
        self.cash_reserve += record.profit

        self.history.append(record)
        if len(self.history) > 90:
            self.history = self.history[-90:]

        # Manager autonomous decisions
        if self.manager_npc_id and not self.paused:
            self._manager_auto_decisions()

        # Production chains — consume inputs, produce outputs
        bp = BUSINESS_BLUEPRINTS.get(self.blueprint_key)
        if bp and bp.consumes and bp.produces:
            # Check if we have all inputs
            can_produce = True
            for item_id, qty in bp.consumes:
                available = sum(1 for i in self.inventory if i.id == item_id)
                if available < qty:
                    can_produce = False
                    break
            if can_produce:
                # Consume inputs
                for item_id, qty in bp.consumes:
                    consumed = 0
                    for item in list(self.inventory):
                        if item.id == item_id and consumed < qty:
                            self.inventory.remove(item)
                            consumed += 1
                # Produce outputs
                from src.items import make_item
                for item_id, qty in bp.produces:
                    for _ in range(qty):
                        try:
                            self.inventory.append(make_item(item_id))
                        except Exception:
                            pass

        # Employee morale — wages already deducted via profit calculation
        can_pay = self.cash_reserve >= self.daily_wages
        for emp in self.employees:
            emp.days_employed += 1
            emp.tick_morale(can_pay, self.tier >= Tier.ESTABLISHED)

        # Reputation drift (slowly toward player regional rep)
        if player_rep > self.reputation:
            self.reputation = min(100, self.reputation + 0.2)
        elif player_rep < self.reputation:
            self.reputation = max(0, self.reputation - 0.1)

        # Expire old events
        self.events = [e for e in self.events
                       if current_day - e.day_started < e.duration_days]

        # Check tier upgrade
        self._check_tier()

        # Bankruptcy check — if cash negative for 7+ consecutive days
        if self.cash_reserve < 0:
            self.debt += abs(self.cash_reserve)
            self.cash_reserve = 0
            # Count consecutive loss days
            loss_streak = 0
            for h in reversed(self.history[-7:]):
                if h.profit < 0:
                    loss_streak += 1
                else:
                    break
            if loss_streak >= 7:
                self.active = False  # business shuts down

        return record

    def _check_tier(self) -> None:
        """Promote to next tier if thresholds met."""
        next_tier = self.tier + 1
        if next_tier > Tier.EMPIRE:
            return
        thresholds = TIER_THRESHOLDS.get(next_tier)
        if not thresholds:
            return
        min_emp, min_rep, min_rev, min_days = thresholds
        if (self.employee_count >= min_emp and
            self.reputation >= min_rep and
            self._avg_daily_revenue(30) >= min_rev and
            self.days_operating >= min_days):
            self.tier = next_tier

    def _avg_daily_revenue(self, days: int) -> float:
        recent = self.history[-days:] if self.history else []
        if not recent:
            return 0.0
        return sum(r.revenue for r in recent) / len(recent)

    # ── Random events ──────────────────────────────────────────────────

    def roll_event(self, current_day: int,
                    rng: Optional[random.Random] = None) -> Optional[BusinessEvent]:
        """
        Random chance of a business event (call daily, ~5% chance).
        Returns event or None.
        """
        if rng is None:
            rng = random.Random()
        if rng.random() > 0.05:
            return None

        # Weight: 40% positive, 40% negative, 20% neutral
        category = rng.choices(
            ["positive", "negative", "neutral"],
            weights=[40, 40, 20])[0]

        # Good reputation tilts toward positive
        if self.reputation > 60:
            category = rng.choices(
                ["positive", "negative", "neutral"],
                weights=[55, 25, 20])[0]

        pool = _EVENT_POOL.get(category, _EVENT_POOL["neutral"])
        template = rng.choice(pool)

        evt = BusinessEvent(
            event_type=template["type"],
            description=template["desc"],
            revenue_mult=template.get("rev_mult", 1.0),
            expense_delta=template.get("exp", 0.0),
            reputation_delta=template.get("rep", 0.0),
            duration_days=template.get("dur", 1),
            day_started=current_day,
        )

        self.events.append(evt)
        self.reputation = max(0, min(100, self.reputation + evt.reputation_delta))
        if evt.expense_delta < 0:
            self.cash_reserve += evt.expense_delta  # losses

        return evt

    # ── Remote Management ─────────────────────────────────────────────

    def record_price(self, item_id: str, location: str, price: float):
        """Record a market price the player has observed."""
        if item_id not in self.known_prices:
            self.known_prices[item_id] = {}
        self.known_prices[item_id][location] = round(price, 2)

    def add_standing_order(self, order_type: str, **params):
        """Add a persistent rule: buy X at Y price, maintain Z stock, etc."""
        self.standing_orders.append({"type": order_type, **params})

    def add_pending_order(self, instruction: str):
        """Queue an instruction to send to manager via letter."""
        self.pending_orders.append(instruction)

    def clear_pending_orders(self):
        self.pending_orders.clear()

    def generate_weekly_report(self, current_day: int) -> str:
        """Generate a manager's weekly report as letter text."""
        recent = self.history[-7:] if self.history else []
        total_rev = sum(d.revenue for d in recent)
        total_exp = sum(d.expenses + d.wages for d in recent)
        total_net = sum(d.profit for d in recent)

        lines = [
            f"Weekly Report — {self.name}",
            f"",
            f"This week's figures:",
            f"  Revenue:  ${total_rev:.2f}",
            f"  Expenses: ${total_exp:.2f}",
            f"  Net:      ${total_net:.2f}",
            f"  Cash on hand: ${self.cash_reserve:.2f}",
            f"",
            f"Employees: {self.employee_count}",
        ]
        for emp in self.employees:
            lines.append(f"  {emp.name} — morale {emp.morale:.0f}%")

        if self.events:
            lines.append("")
            lines.append("Notable events:")
            for evt in self.events[-3:]:
                lines.append(f"  - {evt.description}")

        lines.append("")
        lines.append(f"Reputation: {self.reputation:.0f}/100")
        lines.append(f"Tier: {self.tier_label}")

        if self.inventory:
            lines.append("")
            lines.append(f"Inventory: {len(self.inventory)} items")

        lines.append("")
        lines.append("Awaiting your instructions.")
        self.last_report_day = current_day
        return "\n".join(lines)

    def should_send_report(self, current_day: int) -> bool:
        """Manager sends weekly reports when player is away."""
        return (self.manager_npc_id and
                current_day - self.last_report_day >= 7)

    def draft_order_letter(self) -> str:
        """Convert pending orders into a letter body for the manager."""
        if not self.pending_orders:
            return ""
        lines = [f"To the manager of {self.name}:", ""]
        for i, order in enumerate(self.pending_orders, 1):
            lines.append(f"{i}. {order}")
        lines.append("")
        lines.append("Execute these at your earliest convenience.")
        return "\n".join(lines)

    # ── Display ────────────────────────────────────────────────────────

    def summary_lines(self) -> List[str]:
        lines = [
            f"{self.name} ({self.tier_label})",
            f"  Type: {BUSINESS_BLUEPRINTS.get(self.blueprint_key, BusinessBlueprint('', '', '', '', 0, 0, 0, 0, 0, '')).name}",
            f"  Days operating: {self.days_operating}",
            f"  Employees: {self.employee_count}",
            f"  Reputation: {self.reputation:.0f}/100",
            f"  Est. daily profit: ${self.net_daily:.2f}",
            f"  Cash reserve: ${self.cash_reserve:.2f}",
            f"  Total invested: ${self.total_invested:.2f}",
            f"  Total revenue: ${self.total_revenue:.2f}",
        ]
        if self.debt > 0:
            lines.append(f"  Outstanding debt: ${self.debt:.2f}")
        if self.events:
            lines.append(f"  Active events: {len(self.events)}")
        return lines

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "blueprint_key": self.blueprint_key,
            "name": self.name, "world_x": self.world_x, "world_y": self.world_y,
            "region": self.region, "settlement_type": self.settlement_type,
            "day_founded": self.day_founded, "active": self.active,
            "category": self.category, "description": self.description,
            "skill_used": self.skill_used,
            "base_revenue": self.base_revenue, "base_expenses": self.base_expenses,
            "rev_per_employee": self.rev_per_employee,
            "wage_per_employee": self.wage_per_employee,
            "tags": self.tags, "tier": self.tier,
            "price_strategy": self.price_strategy,
            "reputation": self.reputation, "days_operating": self.days_operating,
            "total_invested": self.total_invested,
            "total_revenue": self.total_revenue,
            "total_expenses": self.total_expenses,
            "cash_reserve": self.cash_reserve, "debt": self.debt,
            "stock_value": self.stock_value,
            "custom_products": self.custom_products,
            "employees": [
                {"npc_id": e.npc_id, "name": e.name, "role": e.role,
                 "skill_level": e.skill_level, "wage_daily": e.wage_daily,
                 "morale": e.morale, "days_employed": e.days_employed,
                 "productivity": e.productivity}
                for e in self.employees
            ],
            # Remote management
            "manager_npc_id": self.manager_npc_id,
            "standing_orders": self.standing_orders,
            "pending_orders": self.pending_orders,
            "last_report_day": self.last_report_day,
            "last_update_day": self.last_update_day,
            "paused": self.paused,
            "known_prices": self.known_prices,
            # Inventory
            "inventory": [_serialize_biz_item(i) for i in self.inventory],
            # Active shipments
            "shipments": getattr(self, 'shipments', []),
            # History
            "history": [
                {"day": h.day, "revenue": h.revenue, "expenses": h.expenses,
                 "wages": h.wages, "supplies": h.supplies, "other_costs": h.other_costs}
                for h in self.history
            ],
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "BusinessEntity":
        biz = cls.__new__(cls)
        for k, v in d.items():
            if k == "employees":
                biz.employees = [Employee(**ed) for ed in v]
            elif k == "inventory":
                biz.inventory = [_deserialize_biz_item(i) for i in v]
            elif k == "history":
                biz.history = [DailyFinance(**h) for h in v] if v else []
            elif k != "events":
                setattr(biz, k, v)
        if not hasattr(biz, 'history'):
            biz.history = []
        biz.events = []  # events are transient, don't persist
        # Ensure new fields exist on old saves
        for attr, default in [("manager_npc_id", ""), ("standing_orders", []),
                              ("pending_orders", []), ("last_report_day", 0),
                              ("last_update_day", 0), ("paused", False),
                              ("known_prices", {}), ("inventory", []),
                              ("shipments", []),
                              ("price_strategy", "standard")]:
            if not hasattr(biz, attr):
                setattr(biz, attr, default)
        return biz


def _serialize_biz_item(item) -> dict:
    """Serialize a business inventory item."""
    from src.save_load import _serialize_item
    return _serialize_item(item)


def _deserialize_biz_item(d: dict):
    """Deserialize a business inventory item."""
    from src.save_load import _deserialize_item
    return _deserialize_item(d)


# ============================================================================
#  BUSINESS MANAGER
# ============================================================================

class BusinessManager:
    """
    Manages all player-owned businesses.
    Handles daily simulation, events, hiring, and LLM-categorized custom types.
    """

    def __init__(self, llm: Optional["LLMClient"] = None):
        self.llm = llm
        self.businesses: Dict[str, BusinessEntity] = {}
        self._counter = 0
        self._custom_blueprints: Dict[str, BusinessBlueprint] = {}

    def _next_id(self) -> str:
        self._counter += 1
        return f"biz_{self._counter}"

    # ── Founding ───────────────────────────────────────────────────────

    def found(self, blueprint_key: str, name: str,
               wx: int, wy: int, day: int,
               region: str = "", settlement_type: str = "small_town",
               investment: float = 0.0) -> Optional[BusinessEntity]:
        """Found a new business from a known blueprint."""
        # Limit: max 3 businesses per world tile
        at_loc = sum(1 for b in self.businesses.values()
                     if b.world_x == wx and b.world_y == wy and b.active)
        if at_loc >= 3:
            return None
        biz = BusinessEntity(blueprint_key, name, wx, wy, day,
                              region, settlement_type)
        biz.id = self._next_id()
        biz.total_invested = investment
        biz.cash_reserve = investment * 0.5  # half of investment becomes working capital
        self.businesses[biz.id] = biz
        return biz

    def found_custom(self, idea: str, name: str,
                      wx: int, wy: int, day: int,
                      region: str = "", settlement_type: str = "small_town",
                      context: Optional[Dict] = None,
                      investment: float = 0.0) -> Tuple[BusinessEntity, str]:
        """
        Found a custom business by describing it to the LLM.
        Returns (business, llm_description).
        """
        bp = self._categorize_custom(idea, context or {})
        if bp:
            self._custom_blueprints[bp.key] = bp
            BUSINESS_BLUEPRINTS[bp.key] = bp
        else:
            bp = BUSINESS_BLUEPRINTS["general_store"]

        biz = BusinessEntity(bp.key, name, wx, wy, day,
                              region, settlement_type)
        biz.id = self._next_id()
        biz.total_invested = max(investment, bp.startup_cost)
        biz.cash_reserve = investment * 0.5
        biz.description = bp.description
        self.businesses[biz.id] = biz
        return biz, bp.description

    # ── Daily simulation ───────────────────────────────────────────────

    def tick_daily(self, current_day: int,
                    player_rep: float = 0.0) -> List[Tuple[str, DailyFinance, Optional[BusinessEvent]]]:
        """
        Process one day for all active businesses.
        Returns list of (biz_name, finance, event_or_None).
        """
        results = []
        all_biz = list(self.businesses.values())
        for biz in all_biz:
            if not biz.active or biz.paused:
                continue
            biz._all_businesses = all_biz  # for competition check
            finance = biz.tick_daily(current_day, player_rep)
            event = biz.roll_event(current_day)
            results.append((biz.name, finance, event))
        return results

    def resolve_shipments(self, current_day: int, world_map) -> List[Tuple[str, str]]:
        """Check for shipments that have arrived. Returns list of (biz_name, message)."""
        import random
        results = []
        for biz in self.businesses.values():
            arrived = []
            for i, ship in enumerate(biz.shipments):
                if current_day >= ship.get("arrival_day", 99999):
                    arrived.append(i)
            # Process in reverse to not mess up indices
            for i in reversed(arrived):
                ship = biz.shipments.pop(i)
                rng = random.Random(current_day + i)
                # Risk checks
                raw_items = ship.get("items", [])
                # Items are serialized dicts — get value from them
                def _item_value(it):
                    if isinstance(it, dict):
                        return it.get("base_value", 1.0)
                    return getattr(it, 'base_value', 1.0)
                num_items = len(raw_items)

                if rng.random() < ship.get("risk_robbery", 0):
                    results.append((biz.name,
                        f"ROBBERY: Shipment was robbed! {num_items} items lost."))
                    continue
                if rng.random() < ship.get("risk_accident", 0):
                    lost = num_items // 3
                    surviving_value = sum(_item_value(it) for it in raw_items[lost:])
                    biz.cash_reserve += surviving_value * 1.5
                    results.append((biz.name,
                        f"ACCIDENT: {lost} items lost, rest sold for "
                        f"${surviving_value * 1.5:.2f}."))
                    continue
                total_value = sum(_item_value(it) for it in raw_items)
                # Destination premium (items worth more at destination)
                sell_value = total_value * 2.0  # rough 2x markup at destination
                biz.cash_reserve += sell_value
                results.append((biz.name,
                    f"Shipment arrived! {len(raw_items)} items sold for "
                    f"${sell_value:.2f} at destination."))
        return results

    def get_pending_reports(self, current_day: int) -> List[Tuple[str, str]]:
        """Get weekly reports ready to send as letters.
        Returns list of (business_name, report_text)."""
        reports = []
        for biz in self.businesses.values():
            if biz.should_send_report(current_day):
                text = biz.generate_weekly_report(current_day)
                reports.append((biz.name, text))
        return reports

    def assign_npc_to_business(self, biz_id: str, npc_id: str, name: str,
                              role: str = "clerk", skill_level: int = 3,
                              wage: float = 1.0) -> bool:
        """Bridge: add an NPC (hired via companion system) as business employee."""
        biz = self.businesses.get(biz_id)
        if not biz:
            return False
        # Don't double-add
        if any(e.npc_id == npc_id for e in biz.employees):
            return True
        emp = Employee(npc_id=npc_id, name=name, role=role,
                       skill_level=skill_level, wage_daily=wage)
        biz.employees.append(emp)
        return True

    def set_manager(self, biz_id: str, npc_id: str) -> bool:
        """Assign an existing employee as the business manager."""
        biz = self.businesses.get(biz_id)
        if not biz:
            return False
        biz.manager_npc_id = npc_id
        for emp in biz.employees:
            if emp.npc_id == npc_id:
                emp.role = "manager"
        return True

    def total_daily_income(self) -> float:
        return sum(b.net_daily for b in self.businesses.values() if b.active)

    # ── Logistics ─────────────────────────────────────────────────────

    def ship_goods(self, biz_id: str, items: List[Any], dest_wx: int, dest_wy: int,
                   method: str, world_map, current_day: int) -> Dict:
        """
        Ship items from business to a destination.
        method: 'teamster', 'freight', 'river'
        Returns shipment info dict.
        """
        biz = self.businesses.get(biz_id)
        if not biz:
            return {"error": "Business not found"}

        # Calculate distance
        dist_tiles = abs(dest_wx - biz.world_x) + abs(dest_wy - biz.world_y)
        dist_miles = dist_tiles * 5

        # Weight
        total_weight = sum(getattr(i, 'weight', 1.0) for i in items)

        # Cost and time by method
        if method == "teamster":
            cost = 0.0  # teamster is an employee, wage covers it
            travel_days = max(1, dist_tiles // 20)  # ~100 miles/day by wagon
            risk_robbery = 0.05
            risk_accident = 0.03
        elif method == "freight":
            cost = total_weight * dist_miles * 0.001  # $0.10/lb/100mi
            travel_days = max(2, dist_tiles // 15)
            risk_robbery = 0.02
            risk_accident = 0.02
        elif method == "river":
            cost = total_weight * dist_miles * 0.0005  # $0.05/lb/100mi
            travel_days = max(1, dist_tiles // 25)  # faster downstream
            risk_robbery = 0.01
            risk_accident = 0.04  # capsizing
        else:
            return {"error": "Unknown shipping method"}

        # Remove items from business inventory
        for item in items:
            if item in biz.inventory:
                biz.inventory.remove(item)

        # Deduct cost from business cash
        biz.cash_reserve -= cost

        arrival_day = current_day + travel_days

        shipment = {
            "items": [_serialize_biz_item(i) for i in items],  # serialize for persistence
            "dest_wx": dest_wx, "dest_wy": dest_wy,
            "method": method,
            "cost": cost,
            "travel_days": travel_days,
            "arrival_day": arrival_day,
            "risk_robbery": risk_robbery,
            "risk_accident": risk_accident,
            "total_weight": total_weight,
            "dist_miles": dist_miles,
        }
        biz.shipments.append(shipment)
        return shipment

    def total_empire_value(self) -> float:
        """Total value of all business assets + cash reserves."""
        return sum(
            b.total_invested + b.cash_reserve + b.stock_value
            for b in self.businesses.values() if b.active)

    def highest_tier(self) -> int:
        if not self.businesses:
            return 0
        return max((b.tier for b in self.businesses.values() if b.active), default=0)

    # ── Lookup ─────────────────────────────────────────────────────────

    def get(self, biz_id: str) -> Optional[BusinessEntity]:
        return self.businesses.get(biz_id)

    def get_at(self, wx: int, wy: int) -> List[BusinessEntity]:
        return [b for b in self.businesses.values()
                if b.world_x == wx and b.world_y == wy and b.active]

    def all_active(self) -> List[BusinessEntity]:
        return [b for b in self.businesses.values() if b.active]

    # ── LLM custom business categorization ─────────────────────────────

    def _categorize_custom(self, idea: str,
                            context: Dict) -> Optional[BusinessBlueprint]:
        if not self.llm or not self.llm.available:
            return _keyword_categorize(idea)

        self.llm._load()
        if not self.llm.available:
            return _keyword_categorize(idea)

        prompt = _build_biz_prompt(idea, context)
        try:
            raw = self.llm._chat(
                [{"role": "system", "content": _BIZ_CATEGORIZE_SYSTEM},
                 {"role": "user",   "content": prompt}],
                temperature=0.30, max_tokens=500, json_mode=True,
            )
            return _parse_biz_blueprint(raw, idea)
        except Exception:
            return None

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> Dict:
        return {
            "counter": self._counter,
            "businesses": {
                bid: b.to_dict() for bid, b in self.businesses.items()
            },
            "custom_blueprints": {
                k: {
                    "key": bp.key, "name": bp.name, "description": bp.description,
                    "category": bp.category, "startup_cost": bp.startup_cost,
                    "daily_base_revenue": bp.daily_base_revenue,
                    "daily_base_expenses": bp.daily_base_expenses,
                    "revenue_per_employee": bp.revenue_per_employee,
                    "wage_per_employee": bp.wage_per_employee,
                    "skill_used": bp.skill_used,
                    "building_required": bp.building_required,
                    "inventory_categories": bp.inventory_categories,
                    "tags": bp.tags, "source": "llm",
                }
                for k, bp in self._custom_blueprints.items()
            },
        }

    @classmethod
    def from_dict(cls, d: Dict, llm=None) -> "BusinessManager":
        mgr = cls(llm)
        mgr._counter = d.get("counter", 0)
        for k, bpd in d.get("custom_blueprints", {}).items():
            bp = BusinessBlueprint(**bpd)
            mgr._custom_blueprints[k] = bp
            BUSINESS_BLUEPRINTS[k] = bp
        for bid, bd in d.get("businesses", {}).items():
            mgr.businesses[bid] = BusinessEntity.from_dict(bd)
        return mgr


# ============================================================================
#  LLM CUSTOM BUSINESS CATEGORIZATION
# ============================================================================

def _keyword_categorize(idea: str) -> Optional[BusinessBlueprint]:
    """Keyword-match a business idea to the closest existing blueprint.
    Used when LLM is unavailable."""
    low = idea.lower()

    _KEYWORD_MAP = {
        "saloon":     ("saloon",        {"bar", "saloon", "tavern", "pub", "drink", "whiskey", "beer"}),
        "hotel":      ("hotel",         {"hotel", "boarding", "inn", "lodging", "room", "bed"}),
        "general_store": ("general_store", {"store", "shop", "mercantile", "supply", "goods", "provisions"}),
        "blacksmith_shop": ("blacksmith_shop", {"blacksmith", "forge", "anvil", "iron", "horseshoe", "metalwork"}),
        "bakery":     ("bakery",        {"bakery", "bread", "bake", "pastry", "oven", "flour"}),
        "laundry":    ("laundry",       {"laundry", "wash", "clothes", "cleaning"}),
        "barbershop": ("barbershop",    {"barber", "haircut", "shave", "dentist"}),
        "stable":     ("stable",        {"stable", "livery", "horse", "mule", "animal", "corral"}),
        "sawmill":    ("sawmill",       {"sawmill", "lumber", "timber", "wood", "plank"}),
        "mining_company": ("mining_company", {"mine", "mining", "shaft", "ore", "tunnel", "dig"}),
        "freight_line": ("freight_line", {"freight", "haul", "wagon", "transport", "teamster", "delivery"}),
        "newspaper":  ("newspaper",     {"newspaper", "press", "print", "gazette", "editor", "news"}),
        "assay_office": ("assay_office", {"assay", "test", "ore test", "gold test"}),
        "ferry":      ("ferry",         {"ferry", "boat", "river crossing", "crossing"}),
        "gun_shop":   ("gun_shop",      {"gun", "rifle", "pistol", "ammunition", "ammo", "weapon"}),
        "outfitter":  ("outfitter",     {"outfit", "clothing", "tailor", "sew", "boots", "hat"}),
        "workshop":   ("workshop",      {"workshop", "invent", "craft", "build", "machine", "repair"}),
        "express_service": ("express_service", {"express", "mail", "courier", "post", "delivery", "letter"}),
        "logging_outfit": ("logging_outfit", {"logging", "chop", "fell", "timber", "forest"}),
    }

    # Score each blueprint by keyword matches
    best_key = None
    best_score = 0
    for bp_key, (_, keywords) in _KEYWORD_MAP.items():
        score = sum(1 for kw in keywords if kw in low)
        if score > best_score:
            best_score = score
            best_key = bp_key

    if best_key and best_score > 0:
        # Clone the matched blueprint with the custom name
        base = BUSINESS_BLUEPRINTS.get(best_key)
        if base:
            custom_key = f"custom_{idea.lower().replace(' ', '_')[:20]}"
            return BusinessBlueprint(
                key=custom_key,
                name=idea[:30],
                description=f"A {base.category} business: {idea}.",
                category=base.category,
                startup_cost=base.startup_cost,
                daily_base_revenue=base.daily_base_revenue,
                daily_base_expenses=base.daily_base_expenses,
                revenue_per_employee=base.revenue_per_employee,
                wage_per_employee=base.wage_per_employee,
                skill_used=base.skill_used,
                building_required=base.building_required,
                inventory_categories=base.inventory_categories,
                tags=base.tags + ["custom"],
                source="keyword",
            )
    return None


_BIZ_CATEGORIZE_SYSTEM = """\
You are a business analyst in 1849 frontier America. A prospector wants \
to start a business. Analyze the idea and assign realistic economic parameters.

Any business the player can justify with available resources and skills is \
valid. Unusual or inventive businesses are fine — the frontier rewards \
creativity. But the numbers must be realistic for the era.

Return ONLY valid JSON. No commentary.
"""


def _build_biz_prompt(idea: str, context: Dict) -> str:
    region = context.get("region", "California")
    year = context.get("year", 1849)
    skills = ", ".join(f"{k}:{v}" for k, v in context.get("skills", {}).items()
                       if v > 0) or "untrained"
    cash = context.get("cash", 50)

    return f"""\
BUSINESS IDEA: "{idea}"
LOCATION: {region}, year {year}
PLAYER SKILLS: {skills}
PLAYER CASH: ${cash:.2f}

Return JSON:
{{
  "key": "<short_snake_case_id>",
  "name": "<business type name>",
  "description": "<1-2 sentence description>",
  "category": "<retail|service|production|transport|extraction|custom>",
  "startup_cost": <float, realistic startup cost in 1849 dollars>,
  "daily_base_revenue": <float, expected daily revenue at startup>,
  "daily_base_expenses": <float, daily overhead costs>,
  "revenue_per_employee": <float, additional daily revenue per worker>,
  "wage_per_employee": <float, daily wage per worker>,
  "skill_used": "<primary skill: trading|engineering|survival|geology|etc>",
  "building_required": "<building type or empty string>",
  "tags": [<list of relevant tags>],
  "risks": "<1 sentence about main business risk>",
  "growth_potential": "<low|medium|high|very_high>"
}}"""


def _parse_biz_blueprint(raw: str, fallback_idea: str) -> Optional[BusinessBlueprint]:
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return None

    key = str(d.get("key", fallback_idea.lower().replace(" ", "_")))[:32]

    return BusinessBlueprint(
        key=f"custom_{key}",
        name=str(d.get("name", fallback_idea)),
        description=str(d.get("description", "")),
        category=str(d.get("category", "custom")),
        startup_cost=max(5, float(d.get("startup_cost", 100))),
        daily_base_revenue=max(0.1, float(d.get("daily_base_revenue", 1.0))),
        daily_base_expenses=max(0, float(d.get("daily_base_expenses", 0.5))),
        revenue_per_employee=max(0, float(d.get("revenue_per_employee", 1.0))),
        wage_per_employee=max(0.25, float(d.get("wage_per_employee", 1.0))),
        skill_used=str(d.get("skill_used", "trading")),
        building_required=str(d.get("building_required", "")),
        tags=d.get("tags", []) if isinstance(d.get("tags"), list) else [],
        source="llm",
    )
