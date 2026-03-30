"""
src/economy.py

Economy, trading, and business system for American Prospector.

Historical context:
    Gold dust is de-facto currency in mining camps ($20.67/oz fixed 1834-1933).
    Prices in remote camps are 5-10x city prices due to freight.
    Merchants weigh gold dust on small scales; pinches and pennyweights.
    Bartering is common, especially for goods that are scarce.
    Reputation spreads slowly — a cheat in Sacramento is unknown in Deadwood.

Key classes:
    PriceTable          — regional price multipliers and supply/demand
    MerchantStock       — what a specific merchant has for sale
    MerchantType        — archetype data (general store, blacksmith, etc.)
    TradeEngine         — buy/sell/barter resolution with haggling
    ReputationTracker   — per-region reputation affecting prices
    BusinessLedger      — player-owned business tracking

Integration:
    Engine holds TradeEngine + ReputationTracker.
    NPC merchants get MerchantStock generated from their MerchantType.
    ItemFactory blueprints provide base_value; PriceTable applies modifiers.
    LLM evaluates custom items merchants haven't seen before.
"""

import random
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.items import Item
    from src.llm_client import LLMClient


# ============================================================================
#  CONSTANTS
# ============================================================================

# Fixed gold price (US government rate 1834-1933)
GOLD_PRICE_PER_OZ = 20.67

# Assay office fee (percentage taken)
ASSAY_FEE_PCT = 0.05    # 5% — standard for the era

# Gold fineness discount — raw dust is ~90% pure, refined is 99%+
RAW_DUST_FINENESS = 0.90
REFINED_FINENESS  = 0.99


# ============================================================================
#  REGIONAL PRICE MULTIPLIERS
# ============================================================================
# Remote locations = higher prices.  Major cities = near base.
# These multiply item base_value for buy price; sell price is further discounted.

REGION_PRICE_MULT: Dict[str, float] = {
    "Sierra Nevada Foothills":   3.5,   # everything hauled by mule
    "California Central Valley": 1.8,   # closer to Sacramento
    "California Coast Ranges":   2.2,
    "Nevada Great Basin":        4.0,   # very remote
    "Rocky Mountains":           4.5,   # extreme remoteness
    "Black Hills":               3.8,
    "Montana Goldfields":        4.2,
    "Idaho Silver Belt":         3.5,
    "Great Plains":              1.5,   # flat, easy freight
    "Gulf Coast":                1.3,   # port access
    "Alaska Interior":           6.0,   # most remote
    "Pacific Northwest":         2.0,
    "Appalachians":              1.4,   # near eastern industry
}

# Settlement type modifiers (multiply on top of region)
SETTLEMENT_PRICE_MULT: Dict[str, float] = {
    "mining_camp_small":   2.0,    # markup from scarcity
    "mining_camp_medium":  1.6,
    "boomtown":            1.3,    # competitive merchants
    "small_town":          1.0,    # baseline
    "trading_post":        1.8,    # remote but stocked
    "city":                0.85,   # bulk supply, lower prices
}


# ============================================================================
#  SUPPLY / DEMAND CATEGORIES
# ============================================================================
# Each category has a regional demand multiplier.
# High demand = higher buy price and lower sell price (merchants want to keep stock).
# Low demand = lower buy price and merchants pay better for what they want.

@dataclass
class DemandLevel:
    """Supply/demand state for an item category in a region."""
    buy_mult: float = 1.0      # multiplier on buy price (player buying)
    sell_mult: float = 1.0     # multiplier on sell price (player selling)
    label: str = "normal"


DEMAND_PRESETS: Dict[str, DemandLevel] = {
    "scarce":    DemandLevel(buy_mult=2.5, sell_mult=1.5, label="scarce"),
    "high":      DemandLevel(buy_mult=1.5, sell_mult=1.2, label="high demand"),
    "normal":    DemandLevel(buy_mult=1.0, sell_mult=1.0, label="normal"),
    "surplus":   DemandLevel(buy_mult=0.7, sell_mult=0.6, label="surplus"),
    "glut":      DemandLevel(buy_mult=0.4, sell_mult=0.3, label="glut"),
}

# Default demand by region (category → demand_preset_key)
REGIONAL_DEMAND: Dict[str, Dict[str, str]] = {
    "Sierra Nevada Foothills": {
        "food": "scarce", "tool": "high", "weapon": "high",
        "clothing": "high", "material": "normal", "drink": "scarce",
    },
    "Alaska Interior": {
        "food": "scarce", "tool": "scarce", "weapon": "high",
        "clothing": "scarce", "drink": "scarce",
    },
    "Great Plains": {
        "food": "surplus", "tool": "normal", "weapon": "normal",
        "clothing": "normal",
    },
    "California Central Valley": {
        "food": "surplus", "tool": "normal",
    },
}


# ============================================================================
#  MERCHANT TYPES
# ============================================================================

@dataclass
class MerchantType:
    """Archetype definition for a type of merchant."""
    key: str
    label: str
    # Which item categories they buy/sell
    buys: List[str]          # categories they'll buy from player
    sells: List[str]         # categories they stock
    # Pricing personality
    markup: float = 1.3      # multiplier on buy price (how much over base)
    lowball: float = 0.35    # fraction of value they offer for player's goods
    haggle_floor: float = 0.5   # minimum sell ratio after haggling
    # Attitude toward unusual items
    curiosity: float = 0.5   # 0=refuses strange items, 1=loves them
    # Stock size
    stock_min: int = 5
    stock_max: int = 15


MERCHANT_TYPES: Dict[str, MerchantType] = {
    "general_store": MerchantType(
        "general_store", "General Store",
        buys=["tool", "food", "drink", "material", "clothing", "misc"],
        sells=["tool", "food", "drink", "material", "clothing"],
        markup=1.4, lowball=0.35, curiosity=0.3,
        stock_min=10, stock_max=25,
    ),
    "blacksmith": MerchantType(
        "blacksmith", "Blacksmith",
        buys=["tool", "weapon", "material"],
        sells=["tool", "weapon"],
        markup=1.2, lowball=0.40, curiosity=0.6,
        stock_min=5, stock_max=12,
    ),
    "saloon": MerchantType(
        "saloon", "Saloon",
        buys=["drink", "food"],
        sells=["drink", "food"],
        markup=2.0, lowball=0.25, curiosity=0.2,
        stock_min=4, stock_max=10,
    ),
    "assay_office": MerchantType(
        "assay_office", "Assay Office",
        buys=["material"],   # tests ore samples, does NOT buy placer dust
        sells=[],
        markup=1.0, lowball=0.85,   # fair rate for ore assaying
        curiosity=0.8,
        stock_min=0, stock_max=2,
    ),
    "chinese_merchant": MerchantType(
        "chinese_merchant", "Chinese Merchant",
        buys=["food", "material", "tool", "clothing", "misc"],
        sells=["food", "tool", "material", "clothing"],
        markup=1.1, lowball=0.45,   # better prices both ways
        curiosity=0.7,
        stock_min=6, stock_max=15,
    ),
    "traveling_peddler": MerchantType(
        "traveling_peddler", "Traveling Peddler",
        buys=["tool", "weapon", "material", "clothing", "misc"],
        sells=["tool", "weapon", "material", "clothing", "misc"],
        markup=1.6, lowball=0.30, curiosity=0.9,   # will buy anything
        stock_min=4, stock_max=10,
    ),
    "gun_shop": MerchantType(
        "gun_shop", "Gunsmith",
        buys=["weapon"],
        sells=["weapon"],
        markup=1.3, lowball=0.45, curiosity=0.4,
        stock_min=3, stock_max=8,
    ),
    "clothing_store": MerchantType(
        "clothing_store", "Outfitter",
        buys=["clothing"],
        sells=["clothing"],
        markup=1.3, lowball=0.35, curiosity=0.3,
        stock_min=6, stock_max=15,
    ),
    "bank": MerchantType(
        "bank", "Bank",
        buys=[],
        sells=[],
        markup=1.0, lowball=0.95,   # gold conversion at near-par
        curiosity=0.0,
        stock_min=0, stock_max=0,
    ),
}

# Map NPC occupation → merchant type
OCCUPATION_TO_MERCHANT: Dict[str, str] = {
    "Merchant":           "general_store",
    "Blacksmith":         "blacksmith",
    "Saloon Keeper":      "saloon",
    "Assayer":            "assay_office",
    "Chinese Laborer":    "chinese_merchant",
    "Chinese Merchant":   "chinese_merchant",
    "Barber":             "general_store",
    "Banker":             "bank",
    "Gunsmith":           "gun_shop",
    "Traveling Peddler":  "traveling_peddler",
    "Baker":              "general_store",
    "Butcher":            "general_store",
    "Tailor":             "general_store",
    "Apothecary":         "general_store",
    "Cobbler":            "general_store",
    "Brewmaster":         "saloon",
    "Madam":              "saloon",
    "Trapper":            "general_store",
    "Mountain Man":       "general_store",
    "Fur Trader":         "general_store",
}


# ============================================================================
#  STOCK TEMPLATES — what merchants carry by category
# ============================================================================
# item_template_id → probability of being stocked (0-1)

STOCK_POOLS: Dict[str, Dict[str, float]] = {
    "general_store": {
        "gold_pan": 0.9, "pickaxe": 0.8, "shovel": 0.9,
        "hand_axe": 0.7, "hunting_knife": 0.8, "flint_steel": 0.9,
        "compass": 0.5, "canteen": 0.9,
        "hardtack": 1.0, "salt_pork": 0.9, "jerky": 0.8,
        "dried_beans": 0.9, "pemican": 0.4,
        "rope_10ft": 0.9, "bedroll": 0.6, "canvas_tent": 0.3,
        "water_quart": 0.5,
        # Crafting materials
        "flour": 0.9, "salt": 0.9, "coffee_beans": 0.8,
        "canvas": 0.5, "nails": 0.7, "iron_bar": 0.4,
        "corn": 0.6, "molasses": 0.4,
        # Storage
        "rucksack": 0.4, "belt_pouch": 0.6,
        "prospector_pack": 0.2, "ore_sack": 0.5,
        # Medical
        "laudanum": 0.3,
        # Ammo
        "rifle_ball": 0.9, "revolver_ball": 0.7,
        "shotgun_shell": 0.5,
        # Wool blanket & tobacco
        "wool_blanket": 0.4, "tobacco": 0.6,
    },
    "blacksmith": {
        "pickaxe": 0.9, "shovel": 0.9, "hand_axe": 0.8,
        "hunting_knife": 0.7, "skinning_knife": 0.5,
        "iron_bar": 0.8, "nails": 0.9,
        "steel_trap": 0.4,
    },
    "saloon": {
        "hardtack": 0.5, "jerky": 0.6,
        "whiskey": 0.9, "tobacco": 0.7,
        "playing_cards": 0.3,
    },
    "gun_shop": {
        "percussion_rifle": 0.7, "percussion_revolver": 0.5,
        "shotgun": 0.3, "bowie_knife": 0.8,
        "rifle_ball": 1.0, "revolver_ball": 0.9,
        "shotgun_shell": 0.8,
    },
}


# ============================================================================
#  MERCHANT STOCK (per-NPC instance)
# ============================================================================

@dataclass
class StockEntry:
    """A single item for sale in a merchant's stock."""
    item_id: str
    name: str
    category: str
    base_price: float       # base_value from template
    quantity: int = 1
    condition: float = 100.0


@dataclass
class MerchantStock:
    """Generated inventory for a specific merchant NPC."""
    merchant_type: str
    npc_id: str
    items: List[StockEntry] = field(default_factory=list)
    cash_on_hand: float = 50.0      # how much the merchant can pay
    last_restock_day: int = 0

    def has_item(self, item_id: str) -> Optional[StockEntry]:
        for e in self.items:
            if e.item_id == item_id and e.quantity > 0:
                return e
        return None


def generate_stock(merchant_type: str, npc_id: str, seed: int,
                    settlement_type: str = "small_town") -> MerchantStock:
    """Generate merchant inventory from type + randomization."""
    mtype = MERCHANT_TYPES.get(merchant_type, MERCHANT_TYPES["general_store"])
    rng = random.Random(seed)
    from src.items import ITEM_TEMPLATES

    stock = MerchantStock(
        merchant_type=merchant_type,
        npc_id=npc_id,
        cash_on_hand=rng.uniform(30, 200),
    )

    pool = STOCK_POOLS.get(merchant_type, {})
    for item_id, prob in pool.items():
        if rng.random() < prob:
            tpl = ITEM_TEMPLATES.get(item_id)
            if not tpl:
                continue
            qty = 1
            if tpl.get("stackable"):
                qty = rng.randint(2, 15)
            stock.items.append(StockEntry(
                item_id=item_id,
                name=tpl["name"],
                category=tpl.get("category", "misc"),
                base_price=tpl.get("base_value", 1.0),
                quantity=qty,
                condition=rng.uniform(70, 100),
            ))

    return stock


# ============================================================================
#  PRICE CALCULATION
# ============================================================================

class PriceEngine:
    """
    Calculates buy/sell prices considering region, settlement, demand,
    merchant type, item condition, and reputation.
    """

    def __init__(self, reputation: Optional["ReputationTracker"] = None):
        self.reputation = reputation

    def buy_price(self, item_base_value: float, item_category: str,
                   region: str, settlement_type: str,
                   merchant_type: str,
                   item_condition: float = 100.0,
                   player_region_rep: float = 0.0) -> float:
        """
        What the player pays to BUY an item from a merchant.
        Higher = more expensive for the player.
        """
        mtype = MERCHANT_TYPES.get(merchant_type, MERCHANT_TYPES["general_store"])

        price = item_base_value
        price *= REGION_PRICE_MULT.get(region, 1.5)
        price *= SETTLEMENT_PRICE_MULT.get(settlement_type, 1.0)
        price *= mtype.markup

        # Supply/demand
        demand = self._get_demand(region, item_category)
        price *= demand.buy_mult

        # Condition discount (damaged goods cheaper)
        if item_condition < 80:
            price *= max(0.3, item_condition / 100.0)

        # Reputation discount: good rep = slight discount
        rep_mod = 1.0 - (player_region_rep * 0.002)  # ±20% at extreme rep
        price *= max(0.8, min(1.2, rep_mod))

        return round(max(0.01, price), 2)

    def sell_price(self, item_base_value: float, item_category: str,
                    region: str, settlement_type: str,
                    merchant_type: str,
                    item_condition: float = 100.0,
                    player_region_rep: float = 0.0,
                    item_is_custom: bool = False) -> float:
        """
        What the merchant pays the player for their item.
        Lower = less money for the player.
        """
        mtype = MERCHANT_TYPES.get(merchant_type, MERCHANT_TYPES["general_store"])

        # Does this merchant even buy this category?
        if item_category not in mtype.buys and item_category != "material":
            return 0.0   # won't buy it

        price = item_base_value
        price *= mtype.lowball   # merchant's standard cut

        # Supply/demand
        demand = self._get_demand(region, item_category)
        price *= demand.sell_mult

        # Condition affects sale value
        price *= max(0.1, item_condition / 100.0)

        # Custom/unknown items get lowballed harder
        if item_is_custom:
            price *= max(0.3, mtype.curiosity)

        # Good rep = slightly better sell price
        rep_mod = 1.0 + (player_region_rep * 0.001)
        price *= max(0.9, min(1.1, rep_mod))

        return round(max(0.01, price), 2)

    def gold_to_cash(self, troy_oz: float, fineness: float = RAW_DUST_FINENESS,
                      assay: bool = False) -> float:
        """
        Convert gold to dollars.
        Raw dust at raw fineness; assayed gold at refined value.
        Assay office takes a fee.
        """
        value = troy_oz * GOLD_PRICE_PER_OZ * fineness
        if assay:
            value *= (1.0 - ASSAY_FEE_PCT)
        return round(value, 2)

    def _get_demand(self, region: str, category: str) -> DemandLevel:
        regional = REGIONAL_DEMAND.get(region, {})
        preset_key = regional.get(category, "normal")
        return DEMAND_PRESETS.get(preset_key, DEMAND_PRESETS["normal"])


# ============================================================================
#  HAGGLING
# ============================================================================

def haggle(base_offer: float, player_charisma: int,
            player_trading_skill: int, merchant_haggle_floor: float,
            is_buying: bool, rng: Optional[random.Random] = None
            ) -> Tuple[float, str]:
    """
    Resolve a haggling attempt.

    Returns (final_price, flavor_message).

    is_buying=True: player wants a lower price (discount).
    is_buying=False: player wants a higher price (better payout).
    """
    if rng is None:
        rng = random.Random()

    # Skill check: d20 + trading_skill + CHA bonus
    roll = rng.randint(1, 20) + player_trading_skill + max(0, (player_charisma - 10) // 2)
    threshold = 12   # moderate difficulty

    if roll >= threshold + 8:
        # Excellent haggle
        shift = 0.25
        msg = "You drive a hard bargain. The merchant looks pained but agrees."
    elif roll >= threshold + 3:
        # Good haggle
        shift = 0.15
        msg = "After some back-and-forth, you get a fair deal."
    elif roll >= threshold:
        # Marginal success
        shift = 0.08
        msg = "You talk them down a little."
    elif roll >= threshold - 5:
        # Failure
        shift = 0.0
        msg = "The merchant doesn't budge."
    else:
        # Bad failure — offended
        shift = -0.05
        msg = "\"You insult me.\" The merchant's face hardens."

    if is_buying:
        # Discount off buy price
        final = base_offer * (1.0 - shift)
        final = max(base_offer * merchant_haggle_floor, final)
    else:
        # Bonus on sell price
        final = base_offer * (1.0 + shift)

    return round(max(0.01, final), 2), msg


# ============================================================================
#  REPUTATION TRACKER (per-region)
# ============================================================================

class ReputationTracker:
    """
    Tracks player reputation by region.
    Reputation is -100 to +100, starts at 0 (unknown).
    Affects prices, NPC willingness to trade, and random encounters.
    News spreads slowly — adjacent regions get a fraction of rep changes.
    """

    def __init__(self):
        self.regions: Dict[str, float] = {}   # region_name → rep value

    def get(self, region: str) -> float:
        return self.regions.get(region, 0.0)

    def adjust(self, region: str, delta: float, spread: bool = True) -> None:
        """
        Adjust reputation in a region.
        If spread=True, adjacent regions get 20% of the change (slow news).
        """
        current = self.regions.get(region, 0.0)
        self.regions[region] = max(-100, min(100, current + delta))

        if spread:
            for adj_region in _ADJACENT_REGIONS.get(region, []):
                adj_current = self.regions.get(adj_region, 0.0)
                self.regions[adj_region] = max(-100, min(100,
                    adj_current + delta * 0.2))

    def label(self, region: str) -> str:
        v = self.get(region)
        if v >= 60:  return "Respected"
        if v >= 30:  return "Well-Regarded"
        if v >= 10:  return "Known"
        if v >= -10: return "Unknown"
        if v >= -30: return "Suspect"
        if v >= -60: return "Disliked"
        return "Notorious"

    def price_modifier(self, region: str) -> float:
        """Returns reputation value for price calculations."""
        return self.get(region)

    def to_dict(self) -> Dict:
        return dict(self.regions)

    @classmethod
    def from_dict(cls, d: Dict) -> "ReputationTracker":
        t = cls()
        t.regions = {str(k): float(v) for k, v in d.items()}
        return t


# Region adjacency for slow news spread
_ADJACENT_REGIONS: Dict[str, List[str]] = {
    "Sierra Nevada Foothills": ["California Central Valley", "California Coast Ranges",
                                 "Nevada Great Basin"],
    "California Central Valley": ["Sierra Nevada Foothills", "California Coast Ranges"],
    "California Coast Ranges": ["Sierra Nevada Foothills", "California Central Valley"],
    "Nevada Great Basin": ["Sierra Nevada Foothills", "Rocky Mountains", "Idaho Silver Belt"],
    "Rocky Mountains": ["Nevada Great Basin", "Great Plains", "Montana Goldfields"],
    "Black Hills": ["Great Plains", "Montana Goldfields"],
    "Montana Goldfields": ["Rocky Mountains", "Idaho Silver Belt", "Black Hills"],
    "Idaho Silver Belt": ["Montana Goldfields", "Nevada Great Basin", "Pacific Northwest"],
    "Great Plains": ["Rocky Mountains", "Black Hills", "Appalachians"],
    "Gulf Coast": ["Great Plains", "Appalachians"],
    "Alaska Interior": [],   # isolated
    "Pacific Northwest": ["Idaho Silver Belt", "California Coast Ranges"],
    "Appalachians": ["Great Plains", "Gulf Coast"],
}


# ============================================================================
#  REPUTATION EVENTS — what changes rep
# ============================================================================

REP_EVENTS: Dict[str, float] = {
    "pay_debt_on_time":     +5,
    "generous_trade":       +3,
    "help_stranger":        +8,
    "save_life":           +15,
    "discover_gold":       +10,    # "that prospector who found the strike"
    "win_fair_fight":       +5,
    "cheat_merchant":      -10,
    "steal":               -15,
    "murder":              -40,
    "skip_debt":            -8,
    "abandon_partner":     -12,
    "claim_jump":          -20,
    "help_law":             +8,
    "resist_law":          -10,
    "start_business":       +5,
    "employ_locals":       +10,
}


# ============================================================================
#  LLM CUSTOM ITEM VALUATION
# ============================================================================

_VALUATION_SYSTEM = """\
You are a frontier merchant in 1849 America evaluating an item a \
prospector is trying to sell you. You must assign a fair dollar value \
based on what you could resell it for in a mining camp or town.

Consider: materials, craftsmanship, practical utility on the frontier, \
and how many people would actually want to buy it. Exotic or strange \
items that have no practical use are nearly worthless. Well-made tools \
are always in demand. Food is always valuable in remote camps.

Return ONLY a JSON object: {"value": <float>, "reaction": "<string>"}
The reaction is 1 sentence of in-character merchant dialogue.
"""


def evaluate_custom_item(llm: "LLMClient", item_name: str,
                          item_description: str,
                          merchant_curiosity: float = 0.5) -> Tuple[float, str]:
    """
    Ask the LLM to value a custom item from the merchant's perspective.
    Returns (dollar_value, merchant_reaction_text).
    Falls back to heuristic if LLM unavailable.
    """
    if not llm or not llm.available:
        return _heuristic_value(item_name), ""

    prompt = (
        f'ITEM: "{item_name}"\n'
        f'DESCRIPTION: {item_description}\n'
        f'MERCHANT CURIOSITY: {merchant_curiosity:.1f} '
        f'(0=refuses oddities, 1=loves novelty)\n\n'
        f'What is this worth in 1849 dollars? Return JSON: '
        f'{{"value": <float>, "reaction": "<string>"}}'
    )

    try:
        import json
        raw = llm._chat(
            [{"role": "system", "content": _VALUATION_SYSTEM},
             {"role": "user",   "content": prompt}],
            temperature=0.30, max_tokens=150, json_mode=True,
        )
        data = json.loads(raw)
        value = max(0.0, float(data.get("value", 0)))
        reaction = str(data.get("reaction", ""))
        return round(value, 2), reaction
    except Exception:
        return _heuristic_value(item_name), ""


def _heuristic_value(name: str) -> float:
    """Rough value estimate when LLM unavailable.
    Based on 1849 frontier pricing."""
    low = name.lower()
    # Precious metals
    if any(w in low for w in ("gold nugget", "gold bar", "gold dust")):
        return 20.0
    if any(w in low for w in ("silver", "nugget")):
        return 10.0
    if "gold" in low:
        return 15.0
    # Firearms & weapons
    if any(w in low for w in ("rifle", "musket", "carbine")):
        return 15.0
    if any(w in low for w in ("pistol", "revolver", "derringer")):
        return 10.0
    if "shotgun" in low:
        return 12.0
    if any(w in low for w in ("dynamite", "black powder", "blasting")):
        return 3.0
    if any(w in low for w in ("ammunition", "ammo", "cartridge", "bullet")):
        return 1.0
    # Tools
    if any(w in low for w in ("pickaxe", "shovel", "hammer", "drill")):
        return 2.50
    if any(w in low for w in ("knife", "axe", "saw", "tool", "pliers")):
        return 2.00
    if any(w in low for w in ("pan", "sluice", "rocker")):
        return 3.00
    if any(w in low for w in ("compass", "telescope", "spyglass")):
        return 5.00
    if any(w in low for w in ("lantern", "lamp", "candle")):
        return 0.50
    # Pelts & leather
    if any(w in low for w in ("beaver", "otter", "mink", "marten")):
        return 5.00
    if any(w in low for w in ("bear", "buffalo", "elk")):
        return 4.00
    if any(w in low for w in ("deer", "hide", "pelt", "fur", "skin")):
        return 3.00
    if "leather" in low:
        return 2.50
    # Clothing & gear
    if any(w in low for w in ("coat", "jacket", "boots", "hat", "blanket")):
        return 3.00
    if any(w in low for w in ("shirt", "pants", "trousers", "gloves")):
        return 1.50
    if any(w in low for w in ("saddle", "bridle", "harness")):
        return 8.00
    if any(w in low for w in ("rope", "canvas", "tent")):
        return 1.50
    # Food & provisions
    if any(w in low for w in ("whiskey", "brandy", "wine", "spirits")):
        return 1.00
    if any(w in low for w in ("coffee", "tea", "tobacco")):
        return 0.75
    if any(w in low for w in ("flour", "sugar", "salt", "beans", "rice")):
        return 0.40
    if any(w in low for w in ("meat", "venison", "bacon", "jerky")):
        return 0.60
    if any(w in low for w in ("bread", "biscuit", "hardtack")):
        return 0.20
    if any(w in low for w in ("food", "ration", "meal")):
        return 0.50
    # Medical
    if any(w in low for w in ("medicine", "tonic", "laudanum", "quinine")):
        return 2.00
    if any(w in low for w in ("bandage", "splint", "poultice")):
        return 0.50
    # Raw materials
    if any(w in low for w in ("iron", "steel", "copper", "lead")):
        return 1.50
    if any(w in low for w in ("log", "plank", "board", "lumber")):
        return 0.30
    if any(w in low for w in ("stone", "rock", "gravel")):
        return 0.10
    if any(w in low for w in ("nail", "screw", "bolt")):
        return 0.15
    # Books & paper
    if any(w in low for w in ("book", "manual", "guide", "map")):
        return 1.50
    if any(w in low for w in ("paper", "pencil", "ink")):
        return 0.25
    # Jewelry & valuables
    if any(w in low for w in ("watch", "ring", "jewelry", "gem")):
        return 8.00
    if any(w in low for w in ("deed", "claim", "certificate")):
        return 5.00
    # Animals
    if any(w in low for w in ("horse", "pony")):
        return 50.0
    if any(w in low for w in ("mule", "donkey", "burro")):
        return 30.0
    if any(w in low for w in ("ox", "cow", "cattle")):
        return 25.0
    # Default — minor trinket
    return 0.25


# ============================================================================
#  BUSINESS SYSTEM
# ============================================================================

@dataclass
class Business:
    """
    A player-owned business. Can be any type — store, saloon, workshop,
    newspaper, ferry service, invention shop, anything the player establishes.
    """
    id: str
    name: str                       # "Zack's General Store"
    business_type: str              # "general_store"|"saloon"|"workshop"|"custom"
    world_x: int                    # location
    world_y: int
    established_day: int            # game day founded
    investment: float = 0.0         # total dollars invested
    revenue_daily: float = 0.0      # estimated daily revenue
    expenses_daily: float = 0.0     # rent, supplies, wages
    reputation: float = 0.0         # business-specific rep (0-100)
    employees: List[str] = field(default_factory=list)  # NPC IDs
    inventory_value: float = 0.0    # value of goods in stock
    description: str = ""           # LLM-generated business description
    active: bool = True


class BusinessLedger:
    """Tracks all player-owned businesses."""

    def __init__(self):
        self.businesses: Dict[str, Business] = {}
        self._counter = 0

    def establish(self, name: str, btype: str, wx: int, wy: int,
                   day: int, investment: float = 0.0,
                   description: str = "") -> Business:
        self._counter += 1
        bid = f"biz_{self._counter}"
        biz = Business(
            id=bid, name=name, business_type=btype,
            world_x=wx, world_y=wy,
            established_day=day, investment=investment,
            description=description,
        )
        self.businesses[bid] = biz
        return biz

    def tick_daily(self, current_day: int) -> List[Tuple[str, float]]:
        """
        Process daily revenue/expenses for all active businesses.
        Returns list of (business_name, net_income).
        """
        results = []
        for biz in self.businesses.values():
            if not biz.active:
                continue
            net = biz.revenue_daily - biz.expenses_daily
            results.append((biz.name, net))
        return results

    def total_daily_income(self) -> float:
        return sum(b.revenue_daily - b.expenses_daily
                   for b in self.businesses.values() if b.active)

    def total_investment(self) -> float:
        return sum(b.investment for b in self.businesses.values())

    def get_at(self, wx: int, wy: int) -> List[Business]:
        return [b for b in self.businesses.values()
                if b.world_x == wx and b.world_y == wy and b.active]

    def to_dict(self) -> Dict:
        return {
            "counter": self._counter,
            "businesses": {
                bid: {
                    "id": b.id, "name": b.name, "business_type": b.business_type,
                    "world_x": b.world_x, "world_y": b.world_y,
                    "established_day": b.established_day,
                    "investment": b.investment,
                    "revenue_daily": b.revenue_daily,
                    "expenses_daily": b.expenses_daily,
                    "reputation": b.reputation,
                    "employees": b.employees,
                    "inventory_value": b.inventory_value,
                    "description": b.description,
                    "active": b.active,
                }
                for bid, b in self.businesses.items()
            },
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "BusinessLedger":
        ledger = cls()
        ledger._counter = d.get("counter", 0)
        for bid, bd in d.get("businesses", {}).items():
            ledger.businesses[bid] = Business(**bd)
        return ledger


# ============================================================================
#  TRADE ENGINE — ties everything together
# ============================================================================

class TradeEngine:
    """
    Main interface for all economic transactions.

    Usage:
        engine.trade = TradeEngine(engine.llm)
        engine.reputation = ReputationTracker()
        engine.businesses = BusinessLedger()

        # Buy from merchant
        price = engine.trade.get_buy_price(item, region, stype, mtype, rep)

        # Sell to merchant
        offer = engine.trade.get_sell_price(item, region, stype, mtype, rep)

        # Haggle
        final, msg = engine.trade.haggle_price(offer, player, mtype, is_buying)

        # Convert gold
        cash = engine.trade.sell_gold(oz, assayed=False)
    """

    def __init__(self, llm: Optional["LLMClient"] = None):
        self.llm = llm
        self.price_engine = PriceEngine()

    def get_buy_price(self, item: "Item", region: str,
                       settlement_type: str, merchant_type: str,
                       player_rep: float = 0.0) -> float:
        return self.price_engine.buy_price(
            item.base_value, item.category, region, settlement_type,
            merchant_type, item.condition, player_rep)

    def get_sell_price(self, item: "Item", region: str,
                        settlement_type: str, merchant_type: str,
                        player_rep: float = 0.0) -> float:
        is_custom = item.id.startswith("llm_") or item.quality == "improvised"
        return self.price_engine.sell_price(
            item.base_value, item.category, region, settlement_type,
            merchant_type, item.condition, player_rep, is_custom)

    def haggle_price(self, base_price: float, player,
                      merchant_type: str, is_buying: bool
                      ) -> Tuple[float, str]:
        mtype = MERCHANT_TYPES.get(merchant_type, MERCHANT_TYPES["general_store"])
        return haggle(
            base_price,
            player.attributes.get("charisma", 10),
            player.skills.get("trading", 0),
            mtype.haggle_floor,
            is_buying,
        )

    def sell_gold(self, troy_oz: float, assayed: bool = False,
                   fineness: float = RAW_DUST_FINENESS) -> float:
        return self.price_engine.gold_to_cash(troy_oz, fineness, assayed)

    def evaluate_unknown_item(self, item: "Item",
                                merchant_type: str) -> Tuple[float, str]:
        mtype = MERCHANT_TYPES.get(merchant_type, MERCHANT_TYPES["general_store"])
        return evaluate_custom_item(
            self.llm, item.name, item.description, mtype.curiosity)
