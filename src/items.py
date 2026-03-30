"""
Item definitions and inventory management.
Items are data — dicts loaded from JSON or defined here as defaults.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class Item:
    id: str                          # unique identifier e.g. "gold_pan"
    name: str                        # display name
    weight: float                    # pounds
    category: str                    # tool / food / drink / material / weapon / clothing / misc
    description: str = ""

    # Food/drink properties
    nutrition: float = 0.0           # hunger restored (0–50)
    hydration: float = 0.0           # thirst restored (0–50)
    perishable: bool = False         # spoils over time
    days_until_spoil: Optional[int] = None

    # Tool properties
    tool_tags: List[str] = field(default_factory=list)  # e.g. ["dig", "chop", "pan"]
    condition: float = 100.0         # 0–100; degrades with use
    quality: str = "standard"        # improvised / poor / standard / good / excellent

    # Weapon properties
    damage_min: int = 0
    damage_max: int = 0
    weapon_type: str = ""            # melee / firearm / bow

    # Value
    base_value: float = 0.0         # dollars at fair market price

    # Stack
    stackable: bool = False
    quantity: int = 1

    # Extra data for special items (ammo count, map data, etc.)
    extra: Dict[str, Any] = field(default_factory=dict)

    # Theft tracking — True if picked up from a store without paying
    unpaid: bool = False

    def display_name(self) -> str:
        if self.stackable and self.quantity > 1:
            return f"{self.name} x{self.quantity}"
        if self.condition < 25:
            return f"{self.name} (worn)"
        return self.name

    def is_food(self) -> bool:
        return self.nutrition > 0

    def is_drink(self) -> bool:
        return self.hydration > 0

    def is_tool(self) -> bool:
        return bool(self.tool_tags)

    def is_weapon(self) -> bool:
        return self.weapon_type != ""

    def spoil_warning(self) -> Optional[str]:
        if self.perishable and self.days_until_spoil is not None:
            if self.days_until_spoil <= 0:
                return "spoiled"
            if self.days_until_spoil <= 1:
                return "spoiling soon"
        return None


# ── Starting item templates ────────────────────────────────────────────────

def make_item(template_id: str, quantity: int = 1) -> Item:
    """Create an item from a template."""
    t = ITEM_TEMPLATES.get(template_id)
    if t is None:
        raise ValueError(f"Unknown item template: {template_id}")
    item = Item(**{**t, "quantity": quantity})
    return item


ITEM_TEMPLATES: Dict[str, dict] = {
    # ── Tools ──────────────────────────────────────────────────────────────
    "gold_pan": {
        "id": "gold_pan", "name": "Gold Pan", "weight": 2.0,
        "category": "tool", "tool_tags": ["pan"],
        "description": "A wide sheet-iron pan for washing placer gold from gravel.",
        "base_value": 1.50, "quality": "standard",
    },
    "pickaxe": {
        "id": "pickaxe", "name": "Pickaxe", "weight": 7.0,
        "category": "tool", "tool_tags": ["dig", "break_rock"],
        "description": "A heavy iron pickaxe for breaking rock and moving earth.",
        "base_value": 2.00, "quality": "standard",
        "damage_min": 15, "damage_max": 35, "weapon_type": "melee",  # heavy iron spike
    },
    "shovel": {
        "id": "shovel", "name": "Shovel", "weight": 5.5,
        "category": "tool", "tool_tags": ["dig", "move_earth"],
        "description": "A long-handled iron shovel.",
        "base_value": 1.50, "quality": "standard",
        "damage_min": 8, "damage_max": 20, "weapon_type": "melee",  # heavy flat blade
    },
    "hand_axe": {
        "id": "hand_axe", "name": "Hand Axe", "weight": 3.0,
        "category": "tool", "tool_tags": ["chop", "cut"],
        "description": "A short-handled axe for felling trees and splitting wood.",
        "base_value": 1.25, "quality": "standard",
        "damage_min": 12, "damage_max": 30, "weapon_type": "melee",  # chopping blade
    },
    "hunting_knife": {
        "id": "hunting_knife", "name": "Hunting Knife", "weight": 0.5,
        "category": "tool", "tool_tags": ["cut", "butcher", "skin"],
        "description": "A heavy-bladed knife for field dressing game.",
        "base_value": 0.75, "quality": "standard",
        "damage_min": 8, "damage_max": 18, "weapon_type": "melee",  # stab wound
    },
    "flint_steel": {
        "id": "flint_steel", "name": "Flint & Steel", "weight": 0.1,
        "category": "tool", "tool_tags": ["fire"],
        "description": "Flint and steel for starting fires.",
        "base_value": 0.25, "quality": "standard",
    },
    "compass": {
        "id": "compass", "name": "Compass", "weight": 0.2,
        "category": "tool", "tool_tags": ["navigate"],
        "description": "A brass pocket compass.",
        "base_value": 2.00, "quality": "standard",
    },
    "canteen": {
        "id": "canteen", "name": "Canteen", "weight": 0.5,
        "category": "tool", "tool_tags": ["carry_water"],
        "description": "A tin canteen holding about a quart of water.",
        "base_value": 0.50, "quality": "standard",
        "extra": {"filled": True, "contents": "water"},
    },

    # ── Food ───────────────────────────────────────────────────────────────
    "hardtack": {
        "id": "hardtack", "name": "Hardtack", "weight": 0.1,
        "category": "food", "nutrition": 10.0,
        "description": "A hard, dry biscuit. Keeps indefinitely. Tastes like it.",
        "base_value": 0.03, "stackable": True, "perishable": False,
    },
    "salt_pork": {
        "id": "salt_pork", "name": "Salt Pork", "weight": 0.5,
        "category": "food", "nutrition": 25.0,
        "description": "Heavily salted cured pork. Lasts weeks without refrigeration.",
        "base_value": 0.10, "stackable": True, "perishable": True, "days_until_spoil": 60,
    },
    "jerky": {
        "id": "jerky", "name": "Beef Jerky", "weight": 0.1,
        "category": "food", "nutrition": 15.0,
        "description": "Dried and salted beef. Compact trail food.",
        "base_value": 0.08, "stackable": True, "perishable": True, "days_until_spoil": 60,
    },
    "dried_beans": {
        "id": "dried_beans", "name": "Dried Beans", "weight": 0.2,
        "category": "food", "nutrition": 20.0,
        "description": "Dried beans. Require soaking and cooking but filling and cheap.",
        "base_value": 0.02, "stackable": True, "perishable": False,
        "extra": {"requires_cooking": True},
    },
    "pemican": {
        "id": "pemican", "name": "Pemmican", "weight": 0.2,
        "category": "food", "nutrition": 30.0,
        "description": "Rendered fat mixed with dried meat and berries. Dense trail ration.",
        "base_value": 0.15, "stackable": True, "perishable": True, "days_until_spoil": 180,
    },
    "flour": {
        "id": "flour", "name": "Flour", "weight": 2.0,
        "category": "food", "nutrition": 12.0,
        "description": "Sack of wheat flour. Makes hardtack, bread, or thickens stew.",
        "base_value": 0.30, "stackable": True,
    },
    "wild_berries": {
        "id": "wild_berries", "name": "Wild Berries", "weight": 0.2,
        "category": "food", "nutrition": 8.0,
        "description": "Foraged berries. Eat fresh, mix into pemmican, or ferment into fruit beer.",
        "base_value": 0.05, "stackable": True, "perishable": True, "days_until_spoil": 3,
    },
    "juniper_berries": {
        "id": "juniper_berries", "name": "Juniper Berries", "weight": 0.1,
        "category": "food", "nutrition": 2.0,
        "description": "Aromatic juniper berries. Flavor spirits into gin. Also medicinal.",
        "base_value": 0.10, "stackable": True,
    },
    "wild_honey": {
        "id": "wild_honey", "name": "Wild Honey", "weight": 0.5,
        "category": "food", "nutrition": 12.0,
        "description": "Honey from a wild hive. Sweet, preservative, ferments into mead.",
        "base_value": 0.30, "stackable": True,
    },
    "corn": {
        "id": "corn", "name": "Corn", "weight": 1.0,
        "category": "food", "nutrition": 10.0,
        "description": "Dried corn. Eat it, grind it, or ferment it into corn whiskey.",
        "base_value": 0.15, "stackable": True,
    },
    # ── Brewing intermediates (outputs of fermentation, inputs to distillation)
    "beer": {
        "id": "beer", "name": "Grain Beer", "weight": 1.0,
        "category": "drink", "hydration": 10.0,
        "description": "Cloudy frontier beer from grain.",
        "base_value": 0.25, "stackable": True, "perishable": True, "days_until_spoil": 14,
    },
    "corn_beer": {
        "id": "corn_beer", "name": "Corn Beer", "weight": 1.0,
        "category": "drink", "hydration": 10.0,
        "description": "Sweet corn beer.",
        "base_value": 0.30, "stackable": True, "perishable": True, "days_until_spoil": 14,
    },
    "berry_beer": {
        "id": "berry_beer", "name": "Berry Beer", "weight": 1.0,
        "category": "drink", "hydration": 10.0,
        "description": "Fruity tart berry beer.",
        "base_value": 0.35, "stackable": True, "perishable": True, "days_until_spoil": 10,
    },
    "mead": {
        "id": "mead", "name": "Mead", "weight": 1.0,
        "category": "drink", "hydration": 8.0,
        "description": "Golden honey mead. Sweet and strong.",
        "base_value": 1.00, "stackable": True, "perishable": True, "days_until_spoil": 30,
    },
    "copper_still": {
        "id": "copper_still", "name": "Copper Still", "weight": 25.0,
        "category": "tool",
        "description": "A portable copper pot still. Distill fermented mash into "
                       "whiskey, brandy, gin, or any spirit. Place on the ground to use.",
        "base_value": 18.00,
        "tool_tags": ["distill", "brew"],
    },
    "mash_barrel": {
        "id": "mash_barrel", "name": "Mash Barrel", "weight": 15.0,
        "category": "tool",
        "description": "A small wooden barrel for fermenting grain, fruit, or honey. "
                       "Place on the ground to use.",
        "base_value": 6.00,
        "tool_tags": ["ferment"],
    },
    "wine": {
        "id": "wine", "name": "Berry Wine", "weight": 1.0,
        "category": "drink", "hydration": 8.0,
        "description": "Dark berry wine. Not French, but it'll do.",
        "base_value": 0.75, "stackable": True, "perishable": True, "days_until_spoil": 60,
    },
    "bowstring": {
        "id": "bowstring", "name": "Bowstring", "weight": 0.05,
        "category": "material",
        "description": "Twisted sinew cord. String a bow with this.",
        "base_value": 0.50, "stackable": True,
    },
    "gut_string": {
        "id": "gut_string", "name": "Gut String", "weight": 0.1,
        "category": "material",
        "description": "Twisted intestine cord. Strong for snares and bindings.",
        "base_value": 0.40, "stackable": True,
    },
    "hoof_glue": {
        "id": "hoof_glue", "name": "Hoof Glue", "weight": 0.5,
        "category": "material",
        "description": "Strong hide glue from boiled hooves. Repairs and woodwork.",
        "base_value": 0.30, "stackable": True,
    },

    "molasses": {
        "id": "molasses", "name": "Molasses", "weight": 2.0,
        "category": "food", "nutrition": 8.0,
        "description": "Thick dark syrup from sugar processing. "
                       "Baking, sweetening, or ferment into rum.",
        "base_value": 0.30, "stackable": True,
    },
    "wild_mint": {
        "id": "wild_mint", "name": "Wild Mint", "weight": 0.1,
        "category": "food", "nutrition": 1.0,
        "description": "Fresh mint leaves. Tea, flavoring, or medicinal.",
        "base_value": 0.05, "stackable": True, "perishable": True, "days_until_spoil": 5,
    },
    "smoked_meat": {
        "id": "smoked_meat", "name": "Smoked Meat", "weight": 0.5,
        "category": "food", "nutrition": 25.0,
        "description": "Meat hung over a smoky fire for hours. Rich flavor, keeps well.",
        "base_value": 0.12, "stackable": True, "perishable": True, "days_until_spoil": 21,
    },
    "fresh_venison": {
        "id": "fresh_venison", "name": "Fresh Venison", "weight": 1.0,
        "category": "food", "nutrition": 35.0,
        "description": "Fresh deer meat. Must be cooked. Spoils in 2 days.",
        "base_value": 0.05, "stackable": True, "perishable": True, "days_until_spoil": 2,
        "extra": {"requires_cooking": True},
    },
    "fresh_fish": {
        "id": "fresh_fish", "name": "Fresh Fish", "weight": 0.5,
        "category": "food", "nutrition": 22.0,
        "description": "A freshly caught fish. Can be eaten raw in a pinch; better cooked. Spoils in 1 day.",
        "base_value": 0.03, "stackable": True, "perishable": True, "days_until_spoil": 1,
    },
    "dried_fish": {
        "id": "dried_fish", "name": "Dried Fish", "weight": 0.25,
        "category": "food", "nutrition": 18.0,
        "description": "Fish dried over a fire. Lasts weeks on the trail.",
        "base_value": 0.05, "stackable": True, "perishable": True, "days_until_spoil": 30,
    },

    # ── Butcher yields — meat cuts ─────────────────────────────────────────
    # Names/weights are overridden per-animal at butcher time; these are templates.
    "backstraps": {
        "id": "backstraps", "name": "Backstraps", "weight": 2.0,
        "category": "food", "nutrition": 50.0,
        "description": "The prime tenderloin strips along the spine. Best cut on any animal.",
        "base_value": 0.30, "stackable": True, "perishable": True, "days_until_spoil": 2,
    },
    "hindquarter_meat": {
        "id": "hindquarter_meat", "name": "Hindquarter", "weight": 8.0,
        "category": "food", "nutrition": 40.0,
        "description": "The hind leg and haunch — most of the large muscle on a big animal.",
        "base_value": 0.08, "stackable": True, "perishable": True, "days_until_spoil": 2,
    },
    "shoulder_meat": {
        "id": "shoulder_meat", "name": "Shoulder", "weight": 5.0,
        "category": "food", "nutrition": 35.0,
        "description": "Front shoulder and leg meat. Tougher than hindquarter but plenty of it.",
        "base_value": 0.06, "stackable": True, "perishable": True, "days_until_spoil": 2,
    },
    "rib_meat": {
        "id": "rib_meat", "name": "Ribs", "weight": 3.0,
        "category": "food", "nutrition": 30.0,
        "description": "Rib section meat. Good over a fire.",
        "base_value": 0.05, "stackable": True, "perishable": True, "days_until_spoil": 2,
    },
    "neck_meat": {
        "id": "neck_meat", "name": "Neck Meat", "weight": 1.5,
        "category": "food", "nutrition": 25.0,
        "description": "Neck and jaw meat. Stringy but edible.",
        "base_value": 0.03, "stackable": True, "perishable": True, "days_until_spoil": 2,
    },
    "tongue": {
        "id": "tongue", "name": "Tongue", "weight": 1.0,
        "category": "food", "nutrition": 28.0,
        "description": "A frontier delicacy. Rich and tender when braised.",
        "base_value": 0.20, "stackable": True, "perishable": True, "days_until_spoil": 1,
    },
    "heart": {
        "id": "heart", "name": "Heart", "weight": 0.5,
        "category": "food", "nutrition": 35.0,
        "description": "Dense organ meat, very nutritious. Best eaten fresh.",
        "base_value": 0.10, "stackable": True, "perishable": True, "days_until_spoil": 1,
    },
    "liver": {
        "id": "liver", "name": "Liver", "weight": 1.5,
        "category": "food", "nutrition": 45.0,
        "description": "Highly nutritious organ. Spoils very fast — eat it first.",
        "base_value": 0.08, "stackable": True, "perishable": True, "days_until_spoil": 1,
    },
    "kidneys": {
        "id": "kidneys", "name": "Kidneys", "weight": 0.3,
        "category": "food", "nutrition": 20.0,
        "description": "Pair of kidneys. Strong flavor; nutritious.",
        "base_value": 0.05, "stackable": True, "perishable": True, "days_until_spoil": 1,
    },
    "breast_meat": {
        "id": "breast_meat", "name": "Breast Meat", "weight": 0.8,
        "category": "food", "nutrition": 38.0,
        "description": "Bird breast — lean and good eating.",
        "base_value": 0.10, "stackable": True, "perishable": True, "days_until_spoil": 1,
    },
    "bird_leg": {
        "id": "bird_leg", "name": "Bird Leg", "weight": 0.3,
        "category": "food", "nutrition": 22.0,
        "description": "A drumstick. Dark meat; takes longer to cook.",
        "base_value": 0.05, "stackable": True, "perishable": True, "days_until_spoil": 1,
    },
    "giblets": {
        "id": "giblets", "name": "Giblets", "weight": 0.2,
        "category": "food", "nutrition": 25.0,
        "description": "Heart, liver, and gizzard from a bird.",
        "base_value": 0.05, "stackable": True, "perishable": True, "days_until_spoil": 1,
    },
    "snake_meat": {
        "id": "snake_meat", "name": "Snake Meat", "weight": 0.3,
        "category": "food", "nutrition": 18.0,
        "description": "White, lean meat. Tastes a bit like chicken.",
        "base_value": 0.03, "stackable": True, "perishable": True, "days_until_spoil": 1,
    },

    # ── Butcher yields — non-food ───────────────────────────────────────────
    "raw_hide": {
        "id": "raw_hide", "name": "Raw Hide", "weight": 15.0,
        "category": "material",
        "description": "Untanned animal hide. Heavy and perishable. Needs to be stretched and dried or tanned.",
        "base_value": 3.00, "stackable": False, "perishable": True, "days_until_spoil": 5,
    },
    "small_hide": {
        "id": "small_hide", "name": "Small Hide", "weight": 1.0,
        "category": "material",
        "description": "Hide from a small animal. Useful for small leather goods once tanned.",
        "base_value": 0.75, "stackable": True, "perishable": True, "days_until_spoil": 5,
    },
    "tallow": {
        "id": "tallow", "name": "Tallow", "weight": 1.5,
        "category": "material",
        "description": "Rendered animal fat. Used for cooking, candles, waterproofing, and soap-making.",
        "base_value": 0.15, "stackable": True, "perishable": True, "days_until_spoil": 30,
    },
    "bear_fat": {
        "id": "bear_fat", "name": "Bear Fat", "weight": 1.5,
        "category": "material",
        "description": "Premium rendered fat. Excellent for cooking, lamp oil, and rubbing on leather.",
        "base_value": 0.50, "stackable": True, "perishable": True, "days_until_spoil": 60,
    },
    "sinew": {
        "id": "brain", "name": "Brain", "weight": 0.5,
        "category": "material",
        "description": "Animal brain. Mixed with water to tan hides into leather.",
        "base_value": 0.05,
    },
    "sinew": {
        "id": "sinew", "name": "Sinew", "weight": 0.05,
        "category": "material",
        "description": "Strong tendon fibers. Used for bowstrings, thread, and binding.",
        "base_value": 0.10, "stackable": True,
    },
    "animal_bones": {
        "id": "animal_bones", "name": "Bones", "weight": 2.0,
        "category": "material",
        "description": "Large bones. Marrow can be eaten; bones used for tools and handles.",
        "base_value": 0.02, "stackable": True,
    },
    "antlers": {
        "id": "antlers", "name": "Antlers", "weight": 3.0,
        "category": "material",
        "description": "Hard antler — excellent for tool handles, knife scales, and trade.",
        "base_value": 1.50, "stackable": False,
    },
    "animal_horn": {
        "id": "animal_horn", "name": "Horns", "weight": 1.5,
        "category": "material",
        "description": "Animal horns. Used for powder horns, drinking vessels, and trade.",
        "base_value": 1.00, "stackable": False,
    },
    "bear_claws": {
        "id": "bear_claws", "name": "Bear Claws", "weight": 0.5,
        "category": "material",
        "description": "A set of bear claws. Prized as jewelry and trade goods.",
        "base_value": 2.50, "stackable": True,
    },
    "bear_gallbladder": {
        "id": "bear_gallbladder", "name": "Bear Gallbladder", "weight": 0.05,
        "category": "material",
        "description": "Valuable for trade; believed to have medicinal properties. Sought by certain buyers.",
        "base_value": 5.00, "stackable": True,
    },
    "stomach_sac": {
        "id": "stomach_sac", "name": "Stomach", "weight": 0.5,
        "category": "material",
        "description": "The stomach sac. Cleaned and dried it can serve as a water container or cooking vessel.",
        "base_value": 0.05, "stackable": True,
    },
    "intestines": {
        "id": "intestines", "name": "Intestines", "weight": 1.0,
        "category": "material",
        "description": "Cleaned intestines used for sausage casings. Perishable.",
        "base_value": 0.02, "stackable": True, "perishable": True, "days_until_spoil": 1,
    },
    "bird_feathers": {
        "id": "bird_feathers", "name": "Feathers", "weight": 0.05,
        "category": "material",
        "description": "Flight feathers. Used for fletching arrows and pillow stuffing.",
        "base_value": 0.05, "stackable": True,
    },
    "rattlesnake_rattle": {
        "id": "rattlesnake_rattle", "name": "Rattlesnake Rattle", "weight": 0.01,
        "category": "misc",
        "description": "The rattle from a rattlesnake. Curiosity; used as a trinket.",
        "base_value": 0.10, "stackable": True,
    },
    "castoreum": {
        "id": "castoreum", "name": "Castoreum", "weight": 0.05,
        "category": "material",
        "description": "Oily secretion from a beaver's castor glands. Powerful trapping lure and perfume fixative.",
        "base_value": 2.00, "stackable": True,
    },
    "head": {
        "id": "head", "name": "Head", "weight": 4.0,
        "category": "material",
        "description": "The animal's head. Contains the brain (useful for hide tanning), cheek meat, and tongue if not removed.",
        "base_value": 0.05, "stackable": False, "perishable": True, "days_until_spoil": 2,
    },
    "hooves": {
        "id": "hooves", "name": "Hooves", "weight": 0.5,
        "category": "material",
        "description": "Hooves. Boiled down for hide glue.",
        "base_value": 0.02, "stackable": True,
    },

    # ── Drink ──────────────────────────────────────────────────────────────
    "water_quart": {
        "id": "water_quart", "name": "Water (quart)", "weight": 2.1,
        "category": "drink", "hydration": 25.0,
        "description": "A quart of water.",
        "base_value": 0.0, "stackable": True,
    },

    # ── Clothing / Gear ────────────────────────────────────────────────────
    "bedroll": {
        "id": "bedroll", "name": "Bedroll", "weight": 5.0,
        "category": "clothing",
        "description": "A wool blanket rolled and tied. Provides warmth while sleeping outdoors.",
        "base_value": 1.50,
        "extra": {"warmth_bonus": 20, "slot": "bedroll"},
    },
    "canvas_tent": {
        "id": "canvas_tent", "name": "Canvas Tent", "weight": 12.0,
        "category": "misc",
        "description": "A small canvas tent for one or two people. Can be pitched on the local map.",
        "base_value": 8.00, "tool_tags": ["pitch_tent"],
    },

    # ── Firearms ───────────────────────────────────────────────────────────
    "percussion_rifle": {
        "id": "percussion_rifle", "name": "Percussion Rifle", "weight": 9.0,
        "category": "weapon",
        "description": "A .50 caliber percussion rifle. Single shot; 30 second reload. "
                       "Requires both hands to fire accurately.",
        "base_value": 15.00, "weapon_type": "firearm",
        "damage_min": 35, "damage_max": 70,  # .50 cal ball — devastating
        "extra": {"loaded": False, "ammo_type": "rifle_ball", "reload_time": 30,
                  "two_handed": True, "capacity": 1},
    },
    "percussion_revolver": {
        "id": "percussion_revolver", "name": "Colt Dragoon", "weight": 4.0,
        "category": "weapon",
        "description": "A .44 caliber Colt Dragoon revolver. Six shots. "
                       "Heavy, powerful, the standard sidearm of 1848.",
        "base_value": 25.00, "weapon_type": "firearm",
        "damage_min": 25, "damage_max": 50,  # .44 cal — heavier than Navy
        "extra": {"loaded": 0, "ammo_type": "revolver_ball", "reload_time": 60,
                  "two_handed": False, "capacity": 6},
    },
    "shotgun": {
        "id": "shotgun", "name": "Double-Barrel Shotgun", "weight": 8.0,
        "category": "weapon",
        "description": "A 12-gauge side-by-side. Devastating at close range. Two shots.",
        "base_value": 20.00, "weapon_type": "firearm",
        "damage_min": 40, "damage_max": 80,  # buckshot — kills at close range
        "extra": {"loaded": 0, "ammo_type": "shotgun_shell", "reload_time": 20,
                  "two_handed": True, "capacity": 2},
    },

    # ── Ammunition ────────────────────────────────────────────────────────
    "rifle_ball": {
        "id": "rifle_ball", "name": "Rifle Ball & Powder", "weight": 0.05,
        "category": "material",
        "description": "A lead ball, powder charge, and percussion cap. One shot for a rifle.",
        "base_value": 0.05, "stackable": True,
    },
    "revolver_ball": {
        "id": "revolver_ball", "name": "Revolver Ball & Cap", "weight": 0.02,
        "category": "material",
        "description": "Paper cartridge with ball and cap for a percussion revolver.",
        "base_value": 0.03, "stackable": True,
    },
    "shotgun_shell": {
        "id": "shotgun_shell", "name": "Shotgun Shell", "weight": 0.06,
        "category": "material",
        "description": "A loaded shotshell with shot and powder.",
        "base_value": 0.08, "stackable": True,
    },

    # ── Melee Weapons ─────────────────────────────────────────────────────
    "bowie_knife": {
        "id": "bowie_knife", "name": "Bowie Knife", "weight": 0.8,
        "category": "weapon",
        "description": "A heavy clip-point knife, 9-inch blade. Formidable in a fight.",
        "base_value": 5.00, "weapon_type": "melee",
        "damage_min": 5, "damage_max": 12, "tool_tags": ["cut"],
    },

    # ── Bows & Arrows ─────────────────────────────────────────────────────
    "hunting_bow": {
        "id": "hunting_bow", "name": "Hunting Bow", "weight": 1.5,
        "category": "weapon",
        "description": "A simple wooden bow. Silent and deadly at short range.",
        "base_value": 3.00, "weapon_type": "firearm",  # uses ranged mechanics
        "damage_min": 12, "damage_max": 25,
        "extra": {"loaded": 0, "ammo_type": "arrow", "reload_time": 5,
                  "two_handed": True, "capacity": 1},
    },
    "arrow": {
        "id": "arrow", "name": "Arrow", "weight": 0.05,
        "category": "material",
        "description": "A wooden shaft with a stone or iron point. Silent killer.",
        "base_value": 0.10, "stackable": True,
    },

    # ── Gambling Items ─────────────────────────────────────────────────────
    "playing_cards": {
        "id": "playing_cards", "name": "Playing Cards", "weight": 0.2,
        "category": "misc",
        "description": "A deck of 52 playing cards. Well-worn but serviceable.",
        "base_value": 0.50, "tool_tags": ["gamble"],
    },
    "marked_cards": {
        "id": "marked_cards", "name": "Marked Cards", "weight": 0.2,
        "category": "misc",
        "description": "A deck with subtle markings on the backs. "
                       "For the dishonest gambler.",
        "base_value": 2.00, "tool_tags": ["gamble", "cheat"],
    },
    "dice_set": {
        "id": "dice_set", "name": "Dice Set", "weight": 0.1,
        "category": "misc",
        "description": "A pair of bone dice. Fair — as far as you know.",
        "base_value": 0.25, "tool_tags": ["gamble"],
    },
    "loaded_dice": {
        "id": "loaded_dice", "name": "Loaded Dice", "weight": 0.1,
        "category": "misc",
        "description": "Weighted dice. Subtle enough to fool most people.",
        "base_value": 1.50, "tool_tags": ["gamble", "cheat"],
    },
    "gambling_table": {
        "id": "gambling_table", "name": "Folding Card Table", "weight": 15.0,
        "category": "misc",
        "description": "A portable card table with green felt. "
                       "Set up shop anywhere there are men with money.",
        "base_value": 8.00, "tool_tags": ["gamble", "furniture"],
    },
    "faro_layout": {
        "id": "faro_layout", "name": "Faro Layout", "weight": 3.0,
        "category": "misc",
        "description": "An oilcloth faro layout showing all 13 card ranks. "
                       "Essential for running a faro bank.",
        "base_value": 5.00, "tool_tags": ["gamble", "faro"],
    },

    # ── Materials ──────────────────────────────────────────────────────────
    "rope_10ft": {
        "id": "rope_10ft", "name": "Rope (10 ft)", "weight": 1.0,
        "category": "material",
        "description": "Ten feet of hemp rope.",
        "base_value": 0.20, "stackable": True,
    },
    "gold_dust": {
        "id": "gold_dust", "name": "Gold Dust", "weight": 0.07,  # 1 troy oz
        "category": "material",
        "description": "Raw placer gold dust. Worth ~$20 per troy ounce at the assay office.",
        "base_value": 20.67, "stackable": True,
        "extra": {"troy_oz": 1.0, "fineness": 0.900},
    },

    # ── Construction Materials ─────────────────────────────────────────
    "log": {
        "id": "log", "name": "Log", "weight": 12.0,
        "category": "material",
        "description": "A felled tree trunk, rough-cut. Primary building material.",
        "base_value": 0.10, "stackable": True,
    },
    "plank": {
        "id": "plank", "name": "Plank", "weight": 4.0,
        "category": "material",
        "description": "A sawn plank of lumber. Smoother and lighter than raw logs.",
        "base_value": 0.25, "stackable": True,
    },
    "stone": {
        "id": "stone", "name": "Stone", "weight": 5.0,
        "category": "material",
        "description": "A rough fieldstone suitable for building walls, fireplaces, and foundations.",
        "base_value": 0.05, "stackable": True,
    },
    "nails": {
        "id": "nails", "name": "Nails", "weight": 0.5,
        "category": "material",
        "description": "A handful of cut iron nails. Essential for plank construction.",
        "base_value": 0.15, "stackable": True,
    },
    "iron_bar": {
        "id": "iron_bar", "name": "Iron Bar", "weight": 8.0,
        "category": "material",
        "description": "A bar of wrought iron. Used for heavy construction and toolmaking.",
        "base_value": 1.50, "stackable": True,
    },
    "copper_sheet": {
        "id": "copper_sheet", "name": "Copper Sheet", "weight": 5.0,
        "category": "material",
        "description": "A sheet of hammered copper. Used for stills, cookware, and roofing. "
                       "Copper doesn't rust and conducts heat evenly.",
        "base_value": 2.00, "stackable": True,
    },
    "canvas": {
        "id": "canvas", "name": "Canvas", "weight": 2.0,
        "category": "material",
        "description": "A bolt of heavy canvas cloth. Used for tents, tarps, and covers.",
        "base_value": 1.00, "stackable": True,
    },
    "brain": {
        "id": "brain", "name": "Brain", "weight": 0.5,
        "category": "material",
        "description": "Animal brain. Used for brain-tanning hides into leather.",
        "base_value": 0.05, "stackable": True, "perishable": True, "days_until_spoil": 2,
    },
    "leather": {
        "id": "leather", "name": "Tanned Leather", "weight": 4.0,
        "category": "material",
        "description": "Worked leather. Craft into clothing, bags, or sheaths.",
        "base_value": 3.00, "stackable": True,
    },
    "brush_bundle": {
        "id": "brush_bundle", "name": "Brush", "weight": 1.0,
        "category": "material",
        "description": "A bundle of cut brush and fibers. Twist into cordage or use for shelter.",
        "base_value": 0.02, "stackable": True,
    },
    "clay": {
        "id": "clay", "name": "Clay", "weight": 3.0,
        "category": "material",
        "description": "Wet clay dug from a riverbank. Used for chinking, mortar, and pottery.",
        "base_value": 0.03, "stackable": True,
    },

    # ── Writing & Art Supplies ─────────────────────────────────────────
    "paper": {
        "id": "paper", "name": "Paper", "weight": 0.02,
        "category": "material",
        "description": "A sheet of writing paper.",
        "base_value": 0.05, "stackable": True,
    },
    "parchment": {
        "id": "parchment", "name": "Parchment", "weight": 0.03,
        "category": "material",
        "description": "A sheet of treated animal skin. Durable writing surface.",
        "base_value": 0.15, "stackable": True,
    },
    "stationery": {
        "id": "stationery", "name": "Stationery", "weight": 0.03,
        "category": "material",
        "description": "Bordered letter paper. Proper for correspondence.",
        "base_value": 0.10, "stackable": True,
    },
    "ink": {
        "id": "ink", "name": "Ink", "weight": 0.2,
        "category": "material",
        "description": "A small bottle of iron gall ink. Standard writing ink.",
        "base_value": 0.25, "stackable": True,
    },
    "quill": {
        "id": "quill", "name": "Quill", "weight": 0.01,
        "category": "tool",
        "description": "A goose feather quill pen. Requires ink.",
        "base_value": 0.05, "tool_tags": ["write"],
    },
    "pen": {
        "id": "pen", "name": "Dip Pen", "weight": 0.05,
        "category": "tool",
        "description": "A pen with a metal nib. Requires ink. "
                       "Better than a quill for formal documents.",
        "base_value": 0.50, "tool_tags": ["write"],
    },
    "pencil": {
        "id": "pencil", "name": "Pencil", "weight": 0.02,
        "category": "tool",
        "description": "A graphite pencil. Writes without ink. Good for sketching.",
        "base_value": 0.10, "tool_tags": ["write", "draw"],
    },
    "charcoal_stick": {
        "id": "charcoal_stick", "name": "Charcoal Stick", "weight": 0.02,
        "category": "tool",
        "description": "A stick of charcoal for drawing. Can be made from any fire.",
        "base_value": 0.02, "tool_tags": ["draw"],
    },
    "paint_set": {
        "id": "paint_set", "name": "Paints", "weight": 0.5,
        "category": "tool",
        "description": "A small set of watercolor paints in pans. For painting on paper or canvas.",
        "base_value": 2.00, "tool_tags": ["paint"],
    },
    "art_canvas": {
        "id": "art_canvas", "name": "Canvas", "weight": 0.3,
        "category": "material",
        "description": "A stretched canvas for painting. Reusable writing surface.",
        "base_value": 0.75, "stackable": True,
    },

    # ── Survival Items ────────────────────────────────────────────────────
    "wool_blanket": {
        "id": "wool_blanket", "name": "Wool Blanket", "weight": 3.0,
        "category": "misc",
        "description": "A thick wool blanket. Drastically improves sleep quality and warmth.",
        "base_value": 4.00,
        "extra": {"warmth_bonus": 30, "sleep_bonus": 1.5},
    },
    "salt": {
        "id": "salt", "name": "Salt", "weight": 0.5,
        "category": "material",
        "description": "Rock salt. Preserves meat — triples time before spoiling.",
        "base_value": 0.30, "stackable": True,
    },
    "coffee_beans": {
        "id": "coffee_beans", "name": "Coffee Beans", "weight": 0.5,
        "category": "food",
        "description": "Roasted coffee beans. Brew at a fire to fight fatigue.",
        "base_value": 0.75, "stackable": True, "nutrition": 0,
    },
    "coffee_pot": {
        "id": "coffee_pot", "name": "Coffee Pot", "weight": 1.0,
        "category": "tool",
        "description": "A tin coffee pot. Required to brew coffee at a campfire.",
        "base_value": 1.50, "tool_tags": ["brew"],
    },
    "laudanum": {
        "id": "laudanum", "name": "Laudanum", "weight": 0.3,
        "category": "misc",
        "description": "Tincture of opium. Kills pain from wounds. "
                       "Highly addictive — use sparingly or pay the price.",
        "base_value": 2.00, "stackable": True,
        "tool_tags": ["medical", "painkiller"],
        "extra": {"pain_relief": 40, "addiction_risk": 0.15},
    },
    "whiskey": {
        "id": "whiskey", "name": "Whiskey", "weight": 1.5,
        "category": "drink",
        "description": "Frontier rotgut. Warmth, courage, and impaired aim. "
                       "Also useful as wound disinfectant.",
        "base_value": 0.50, "hydration": 5.0,
        "extra": {"warmth_bonus": 15, "aim_penalty": -3, "courage_bonus": 5,
                  "disinfect": True},
    },
    "tobacco": {
        "id": "tobacco", "name": "Tobacco Pouch", "weight": 0.2,
        "category": "misc",
        "description": "Pipe tobacco. Universal trade currency on the frontier. "
                       "Calms nerves, valued by everyone.",
        "base_value": 0.40, "stackable": True,
        "extra": {"trade_value": 0.5, "stress_relief": 10},
    },
    "fishing_line": {
        "id": "fishing_line", "name": "Fishing Line & Hook", "weight": 0.1,
        "category": "tool",
        "description": "Braided line with a steel hook. Much better than bone hooks.",
        "base_value": 0.30, "tool_tags": ["fish"],
        "extra": {"catch_bonus": 3},
    },

    # ── Weapons ───────────────────────────────────────────────────────────
    "tomahawk": {
        "id": "tomahawk", "name": "Tomahawk", "weight": 1.5,
        "category": "weapon",
        "description": "A light throwing axe. Effective in melee and at range. "
                       "Lands on the ground after a throw.",
        "base_value": 3.00, "weapon_type": "melee",
        "damage_min": 10, "damage_max": 22,
        "tool_tags": ["cut", "chop"],
        "extra": {"throwable": True, "throw_range": 8},
    },
    "derringer": {
        "id": "derringer", "name": "Derringer", "weight": 0.3,
        "category": "weapon",
        "description": "A tiny single-shot pocket pistol. Concealable. Deadly at "
                       "close range, useless beyond 10 feet.",
        "base_value": 8.00, "weapon_type": "firearm",
        "damage_min": 15, "damage_max": 35,
        "extra": {"loaded": 0, "ammo_type": "revolver_ball", "reload_time": 20,
                  "two_handed": False, "capacity": 1, "concealable": True},
    },
    "bear_trap": {
        "id": "bear_trap", "name": "Bear Trap", "weight": 8.0,
        "category": "tool",
        "description": "A heavy iron jaw trap. Place on the ground — immobilizes "
                       "anything that steps on it. Brutal.",
        "base_value": 5.00, "tool_tags": ["trap"],
        "extra": {"trap_damage": 20, "immobilize_turns": 10},
    },

    # ── Crafting Intermediates ────────────────────────────────────────────
    "charcoal": {
        "id": "charcoal", "name": "Charcoal", "weight": 0.5,
        "category": "material",
        "description": "Burned wood. Used for smelting, water filtration, and black powder.",
        "base_value": 0.10, "stackable": True,
    },
    "lye": {
        "id": "lye", "name": "Lye", "weight": 0.5,
        "category": "material",
        "description": "Caustic alkali from wood ash and water. Soap making, "
                       "hide processing, cleaning.",
        "base_value": 0.15, "stackable": True,
    },
    "cordage": {
        "id": "cordage", "name": "Cordage", "weight": 0.2,
        "category": "material",
        "description": "Twisted plant fiber rope. Free to make from grass and bark. "
                       "Weaker than hemp rope but gets the job done.",
        "base_value": 0.05, "stackable": True,
    },
    # ── Pelts (raw — spoils in 3 days unless stretched) ─────────────────
    "beaver_pelt":    {"id": "beaver_pelt",    "name": "Beaver Pelt",    "weight": 2.0, "category": "material", "base_value": 4.00, "perishable": True, "days_until_spoil": 3, "description": "Raw beaver pelt. Stretch to preserve."},
    "fox_pelt":       {"id": "fox_pelt",       "name": "Fox Pelt",       "weight": 1.0, "category": "material", "base_value": 2.00, "perishable": True, "days_until_spoil": 3, "description": "Raw fox fur. Red or gray."},
    "wolf_pelt":      {"id": "wolf_pelt",      "name": "Wolf Pelt",      "weight": 4.0, "category": "material", "base_value": 5.00, "perishable": True, "days_until_spoil": 3, "description": "Raw wolf pelt. Large, thick fur."},
    "coyote_pelt":    {"id": "coyote_pelt",    "name": "Coyote Pelt",    "weight": 1.5, "category": "material", "base_value": 1.00, "perishable": True, "days_until_spoil": 3, "description": "Raw coyote fur."},
    "raccoon_pelt":   {"id": "raccoon_pelt",   "name": "Raccoon Pelt",   "weight": 1.0, "category": "material", "base_value": 1.00, "perishable": True, "days_until_spoil": 3, "description": "Raw raccoon fur."},
    "bobcat_pelt":    {"id": "bobcat_pelt",    "name": "Bobcat Pelt",    "weight": 1.5, "category": "material", "base_value": 3.00, "perishable": True, "days_until_spoil": 3, "description": "Raw bobcat fur. Spotted."},
    "otter_pelt":     {"id": "otter_pelt",     "name": "Otter Pelt",     "weight": 1.5, "category": "material", "base_value": 4.00, "perishable": True, "days_until_spoil": 3, "description": "Raw river otter pelt. Waterproof."},
    "mink_pelt":      {"id": "mink_pelt",      "name": "Mink Pelt",      "weight": 0.3, "category": "material", "base_value": 3.00, "perishable": True, "days_until_spoil": 3, "description": "Raw mink fur. Small but premium."},
    "marten_pelt":    {"id": "marten_pelt",    "name": "Marten Pelt",    "weight": 0.5, "category": "material", "base_value": 3.50, "perishable": True, "days_until_spoil": 3, "description": "Raw pine marten fur."},
    "fisher_pelt":    {"id": "fisher_pelt",    "name": "Fisher Pelt",    "weight": 2.0, "category": "material", "base_value": 5.00, "perishable": True, "days_until_spoil": 3, "description": "Raw fisher fur. Rare, valuable."},
    "wolverine_pelt": {"id": "wolverine_pelt", "name": "Wolverine Pelt", "weight": 2.5, "category": "material", "base_value": 6.00, "perishable": True, "days_until_spoil": 3, "description": "Raw wolverine fur. Frost-resistant."},
    "lynx_pelt":      {"id": "lynx_pelt",      "name": "Lynx Pelt",      "weight": 2.0, "category": "material", "base_value": 4.00, "perishable": True, "days_until_spoil": 3, "description": "Raw lynx fur. Spotted."},
    "muskrat_pelt":   {"id": "muskrat_pelt",   "name": "Muskrat Pelt",   "weight": 0.3, "category": "material", "base_value": 0.75, "perishable": True, "days_until_spoil": 3, "description": "Raw muskrat fur. Common."},
    "skunk_pelt":     {"id": "skunk_pelt",     "name": "Skunk Pelt",     "weight": 0.5, "category": "material", "base_value": 0.50, "perishable": True, "days_until_spoil": 3, "description": "Raw skunk fur. Smells terrible."},
    "bear_pelt":      {"id": "bear_pelt",      "name": "Bear Pelt",      "weight": 8.0, "category": "material", "base_value": 5.00, "perishable": True, "days_until_spoil": 3, "description": "Raw bear hide with fur."},
    "buffalo_robe":   {"id": "buffalo_robe",   "name": "Buffalo Robe",   "weight": 15.0,"category": "material", "base_value": 12.00,"perishable": True, "days_until_spoil": 3, "description": "Raw buffalo hide. Massive."},
    "deer_pelt":      {"id": "deer_pelt",      "name": "Deer Pelt",      "weight": 3.0, "category": "material", "base_value": 2.00, "perishable": True, "days_until_spoil": 3, "description": "Raw deer hide with fur."},
    "elk_pelt":       {"id": "elk_pelt",       "name": "Elk Pelt",       "weight": 6.0, "category": "material", "base_value": 4.00, "perishable": True, "days_until_spoil": 3, "description": "Raw elk hide."},
    "cougar_pelt":    {"id": "cougar_pelt",    "name": "Cougar Pelt",    "weight": 4.0, "category": "material", "base_value": 6.00, "perishable": True, "days_until_spoil": 3, "description": "Raw mountain lion pelt."},

    # ── Trapping Tools ────────────────────────────────────────────────────
    "deadfall_trap": {
        "id": "deadfall_trap", "name": "Deadfall Trap", "weight": 3.0,
        "category": "tool", "base_value": 0.50, "tool_tags": ["trap"],
        "description": "A weighted log trap. Kills medium game instantly.",
    },
    "steel_trap": {
        "id": "steel_trap", "name": "Steel Trap", "weight": 4.0,
        "category": "tool", "base_value": 3.00, "tool_tags": ["trap"],
        "description": "A steel jaw trap. Catches medium and large furbearers.",
    },
    "skinning_knife": {
        "id": "skinning_knife", "name": "Skinning Knife", "weight": 0.3,
        "category": "tool", "base_value": 2.00, "weapon_type": "melee",
        "damage_min": 3, "damage_max": 8,
        "tool_tags": ["cut", "skin", "butcher"],
        "description": "A thin, curved blade for removing pelts cleanly. "
                       "+1 pelt quality grade vs regular knife.",
    },
    "pelt_frame": {
        "id": "pelt_frame", "name": "Pelt Stretching Frame", "weight": 5.0,
        "category": "tool", "base_value": 1.00,
        "tool_tags": ["stretch"],
        "description": "A wooden frame for drying pelts. Place on the ground. "
                       "Load a raw pelt and wait 24 hours.",
    },

    # ── Storage (increases carry capacity when in inventory) ────────────
    "rucksack": {
        "id": "rucksack", "name": "Rucksack", "weight": 2.0,
        "category": "misc",
        "description": "A canvas rucksack with shoulder straps. "
                       "The standard prospector's pack. +60lb carry capacity.",
        "base_value": 3.00,
        "extra": {"carry_capacity_lb": 60},
    },
    "leather_satchel": {
        "id": "leather_satchel", "name": "Leather Satchel", "weight": 1.0,
        "category": "misc",
        "description": "A shoulder bag for documents, small tools, and samples. +20lb.",
        "base_value": 2.00,
        "extra": {"carry_capacity_lb": 20},
    },
    "prospector_pack": {
        "id": "prospector_pack", "name": "Prospector's Pack", "weight": 3.0,
        "category": "misc",
        "description": "A large canvas and leather pack with external tool loops. "
                       "The serious miner's workhorse. +80lb carry capacity.",
        "base_value": 6.00,
        "extra": {"carry_capacity_lb": 80},
    },
    "saddlebags": {
        "id": "saddlebags", "name": "Saddlebags", "weight": 3.0,
        "category": "misc",
        "description": "Paired leather bags that drape over a mule or horse. +40lb. "
                       "Must be near a pack animal to use full capacity.",
        "base_value": 4.00,
        "extra": {"carry_capacity_lb": 40},
    },
    "belt_pouch": {
        "id": "belt_pouch", "name": "Belt Pouch", "weight": 0.3,
        "category": "misc",
        "description": "A small leather pouch worn on the belt. +5lb. "
                       "Good for gold dust, ammunition, and small items.",
        "base_value": 0.75,
        "extra": {"carry_capacity_lb": 5},
    },
    "ore_sack": {
        "id": "ore_sack", "name": "Ore Sack", "weight": 0.5,
        "category": "misc",
        "description": "A heavy canvas sack for hauling ore samples. +30lb.",
        "base_value": 0.50,
        "extra": {"carry_capacity_lb": 30},
    },
    "flour_sack": {
        "id": "flour_sack", "name": "Empty Flour Sack", "weight": 0.2,
        "category": "misc",
        "description": "A repurposed flour sack. Carries anything. +15lb.",
        "base_value": 0.05,
        "extra": {"carry_capacity_lb": 15},
    },

    "land_deed": {
        "id": "land_deed", "name": "Land Deed", "weight": 0.05,
        "category": "misc",
        "description": "A deed proving ownership of a town lot. "
                       "Required to build a business in established towns.",
        "base_value": 0.0,
        "extra": {"lot_wx": 0, "lot_wy": 0, "lot_x": 0, "lot_y": 0,
                  "lot_w": 10, "lot_h": 8},
    },
}


# ── Skill book item generation ─────────────────────────────────────────────

def make_skill_book(book_id: str) -> Optional[Item]:
    """Create a skill book Item from the SKILL_BOOKS catalog in writing.py."""
    try:
        from src.writing import SKILL_BOOKS
    except ImportError:
        return None
    bdef = SKILL_BOOKS.get(book_id)
    if not bdef:
        return None
    return Item(
        id=bdef.id, name=bdef.title, weight=bdef.weight,
        category="misc", description=bdef.description,
        base_value=bdef.base_value,
        extra={
            "teaches_skill": bdef.skill,
            "skill_depth": bdef.depth,
            "xp_per_read": bdef.xp_per_read,
            "readable": True,
        },
    )


def random_skill_books(rng, count: int = 1) -> List[Item]:
    """Generate random skill books for spawning in buildings/shelves."""
    try:
        from src.writing import SKILL_BOOKS
    except ImportError:
        return []
    books = []
    available = [(bid, bdef) for bid, bdef in SKILL_BOOKS.items()
                 if rng.random() < bdef.rarity]
    if not available:
        return []
    for _ in range(count):
        bid, bdef = rng.choice(available)
        book = make_skill_book(bid)
        if book:
            books.append(book)
    return books


# ── Starting loadout ────────────────────────────────────────────────────────

def starting_inventory() -> List[Item]:
    """Default starting gear for a Forty-Niner template."""
    return [
        make_item("rucksack"),          # +60lb carry capacity
        make_item("belt_pouch"),        # +5lb for small items
        make_item("gold_pan"),
        make_item("pickaxe"),
        make_item("shovel"),
        make_item("hunting_knife"),
        make_item("flint_steel"),
        make_item("compass"),
        make_item("canteen"),
        make_item("bedroll"),
        make_item("hardtack",  quantity=10),
        make_item("salt_pork", quantity=5),
        make_item("jerky",     quantity=3),
        make_item("percussion_rifle"),
        make_item("rifle_ball", quantity=20),
        make_item("rope_10ft", quantity=3),
    ]


# ── Food priority sorting ────────────────────────────────────────────────────

PERISHABILITY_ORDER = {
    "fresh_fish": 0,
    "fresh_venison": 1,
    "salt_pork": 2,
    "jerky": 2,
    "pemican": 3,
    "dried_beans": 4,
    "hardtack": 5,
}

def sort_food_by_perishability(items: List[Item]) -> List[Item]:
    """Sort food items most-perishable first."""
    food = [i for i in items if i.is_food()]
    food.sort(key=lambda i: (
        i.days_until_spoil if i.days_until_spoil is not None else 9999
    ))
    return food
