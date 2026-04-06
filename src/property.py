"""
src/property.py

Town property ownership system: lot purchase, deed management, building,
and persistent item storage.

Historical accuracy (1840s-1850s California):
- Town lots sold by alcaldes or land commissioners
- Prices ranged from $10 in camps to hundreds in San Francisco
- Lot ownership proved by a deed document
- Owners could build homes, shops, warehouses, or saloons
- Property values fluctuated wildly with gold rush booms and busts
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

from src.items import Item


# ============================================================================
#  LOT PRICING BY SETTLEMENT TYPE
# ============================================================================

LOT_PRICES: Dict[str, float] = {
    "camp":       10,
    "small_town": 50,
    "boomtown":   150,
    "city":       500,
}

PROPERTY_TYPES = ("vacant", "home", "shop", "warehouse", "saloon")


# ============================================================================
#  OWNED PROPERTY
# ============================================================================

@dataclass
class OwnedProperty:
    """A single town lot owned by the player."""
    lot_id: str
    deed_item_id: str               # id of the deed Item in player inventory

    # World tile where the town sits
    world_x: int
    world_y: int

    # Position and size on the local map
    lot_x: int
    lot_y: int
    width: int
    height: int

    town_name: str

    property_type: str = "vacant"    # vacant | home | shop | warehouse | saloon
    stored_items: List = field(default_factory=list)  # persistent storage
    built: bool = False
    build_progress: float = 0.0      # 0.0 → 1.0
    value: float = 0.0               # current market value in dollars

    def to_dict(self) -> dict:
        return {
            "lot_id":         self.lot_id,
            "deed_item_id":   self.deed_item_id,
            "world_x":        self.world_x,
            "world_y":        self.world_y,
            "lot_x":          self.lot_x,
            "lot_y":          self.lot_y,
            "width":          self.width,
            "height":         self.height,
            "town_name":      self.town_name,
            "property_type":  self.property_type,
            "stored_items":   [
                i.to_dict() if hasattr(i, "to_dict") else i
                for i in self.stored_items
            ],
            "built":          self.built,
            "build_progress": self.build_progress,
            "value":          self.value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OwnedProperty":
        raw_items = d.get("stored_items", [])
        # Deserialize stored items back into Item objects
        stored = []
        for si in raw_items:
            if isinstance(si, dict):
                try:
                    from src.save_load import _deserialize_item
                    stored.append(_deserialize_item(si))
                except Exception:
                    pass  # skip corrupt items
            else:
                stored.append(si)
        return cls(
            lot_id=d["lot_id"],
            deed_item_id=d["deed_item_id"],
            world_x=d["world_x"],
            world_y=d["world_y"],
            lot_x=d["lot_x"],
            lot_y=d["lot_y"],
            width=d["width"],
            height=d["height"],
            town_name=d["town_name"],
            property_type=d.get("property_type", "vacant"),
            stored_items=stored,
            built=d.get("built", False),
            build_progress=d.get("build_progress", 0.0),
            value=d.get("value", 0.0),
        )


# ============================================================================
#  PROPERTY MANAGER
# ============================================================================

class PropertyManager:
    """Manages all player-owned town lots."""

    def __init__(self):
        self.properties: Dict[str, OwnedProperty] = {}
        self._counter: int = 0

    # ── Purchase ───────────────────────────────────────────────────────────

    def buy_lot(self, town_name: str, lot_x: int, lot_y: int,
                width: int, height: int, wx: int, wy: int,
                price: float, player) -> Tuple[bool, str]:
        """
        Attempt to buy a town lot.

        Deducts cash from the player, creates a deed Item in their inventory,
        and registers the property.  Returns (success, message).
        """
        if player.cash < price:
            return False, f"Not enough cash. Need ${price:.2f}, have ${player.cash:.2f}."

        # Check for overlap with existing lots at this location
        for prop in self.properties.values():
            if prop.world_x == wx and prop.world_y == wy:
                if _lots_overlap(lot_x, lot_y, width, height,
                                 prop.lot_x, prop.lot_y, prop.width, prop.height):
                    return False, f"That lot overlaps with your property \"{prop.lot_id}\"."

        # Deduct cash
        player.cash -= price

        # Generate unique lot id
        self._counter += 1
        lot_id = f"lot_{town_name}_{self._counter}"

        # Create deed item
        deed_id = f"deed_{lot_id}"
        deed = Item(
            id=deed_id,
            name=f"Deed — {town_name} Lot #{self._counter}",
            weight=0.05,
            category="misc",
            description=(
                f"Property deed for a {width}x{height} lot in {town_name}. "
                f"Purchased for ${price:.2f}."
            ),
            base_value=price,
        )
        player.inventory.append(deed)

        # Register property
        prop = OwnedProperty(
            lot_id=lot_id,
            deed_item_id=deed_id,
            world_x=wx,
            world_y=wy,
            lot_x=lot_x,
            lot_y=lot_y,
            width=width,
            height=height,
            town_name=town_name,
            value=price,
        )
        self.properties[lot_id] = prop

        return True, (
            f"Purchased lot in {town_name} for ${price:.2f}. "
            f"Deed added to inventory."
        )

    # ── Queries ────────────────────────────────────────────────────────────

    def get_at(self, wx: int, wy: int) -> List[OwnedProperty]:
        """Return all properties at the given world tile."""
        return [p for p in self.properties.values()
                if p.world_x == wx and p.world_y == wy]

    def get_by_town(self, town_name: str) -> List[OwnedProperty]:
        """Return all properties in the named town."""
        return [p for p in self.properties.values()
                if p.town_name == town_name]

    def is_player_home(self, wx: int, wy: int) -> bool:
        """Does the player own a home at this world tile?"""
        return any(
            p.property_type == "home" and p.built
            for p in self.get_at(wx, wy)
        )

    # ── Storage ────────────────────────────────────────────────────────────

    def store_item(self, lot_id: str, item) -> Tuple[bool, str]:
        """Store an item in a property's persistent storage."""
        prop = self.properties.get(lot_id)
        if prop is None:
            return False, "No such property."
        if not prop.built:
            return False, "Must build on the lot before storing items."
        prop.stored_items.append(item)
        return True, f"Stored {item.name} at {prop.town_name} lot."

    def retrieve_item(self, lot_id: str, item_idx: int) -> Optional[Item]:
        """Remove and return an item from property storage by index."""
        prop = self.properties.get(lot_id)
        if prop is None:
            return None
        if item_idx < 0 or item_idx >= len(prop.stored_items):
            return None
        return prop.stored_items.pop(item_idx)

    # ── Serialization ─────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "counter": self._counter,
            "properties": {
                lid: prop.to_dict()
                for lid, prop in self.properties.items()
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PropertyManager":
        mgr = cls()
        mgr._counter = d.get("counter", 0)
        for lid, pd in d.get("properties", {}).items():
            mgr.properties[lid] = OwnedProperty.from_dict(pd)
        return mgr


# ============================================================================
#  HELPERS
# ============================================================================

def _lots_overlap(x1: int, y1: int, w1: int, h1: int,
                  x2: int, y2: int, w2: int, h2: int) -> bool:
    """Return True if two axis-aligned rectangles overlap."""
    return not (x1 + w1 <= x2 or x2 + w2 <= x1 or
                y1 + h1 <= y2 or y2 + h2 <= y1)
