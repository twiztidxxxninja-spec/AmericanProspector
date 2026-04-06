"""
src/town_services.py

Economic consequences system: tracks which services are available in each
town based on which NPCs are present.  When NPCs die or leave, services
become unavailable and prices change due to scarcity or monopoly.

Integration:
    In engine.py (or wherever NPCs are spawned):
        from src.town_services import TownServiceRegistry, on_npc_death
        self.service_registry = TownServiceRegistry()

    When an NPC is placed in a settlement:
        self.service_registry.register_npc(wx, wy, npc.npc_id, npc.occupation)

    When an NPC dies:
        msgs = on_npc_death(self.service_registry, wx, wy,
                            npc.npc_id, npc.occupation, self.npc_mgr.npcs)

    When checking prices:
        mult = self.service_registry.price_multiplier(wx, wy, "tools")
        final_price = base_price * mult
"""

from typing import Dict, List, Optional, Tuple, Any


# ============================================================================
#  OCCUPATION -> SERVICE MAPPING
# ============================================================================

OCCUPATION_SERVICES: Dict[str, Dict[str, Any]] = {
    "Merchant": {
        "services": ["buy_supplies", "sell_goods"],
        "price_category": "general",
    },
    "Blacksmith": {
        "services": ["repair_tools", "buy_weapons", "buy_tools"],
        "price_category": "tools",
    },
    "Doctor": {
        "services": ["medical_treatment", "buy_medicine"],
        "price_category": "medical",
    },
    "Barber": {
        "services": ["haircut", "minor_surgery"],
        "price_category": "medical",
    },
    "Baker": {
        "services": ["buy_food"],
        "price_category": "food",
    },
    "Butcher": {
        "services": ["buy_meat", "process_game"],
        "price_category": "food",
    },
    "Assayer": {
        "services": ["assay_gold", "buy_gold"],
        "price_category": "gold",
    },
    "Banker": {
        "services": ["deposit", "loan", "buy_gold"],
        "price_category": "gold",
    },
    "Saloon Keeper": {
        "services": ["buy_drinks", "gambling", "entertainment"],
        "price_category": "drink",
    },
    "Teamster": {
        "services": ["buy_animals", "sell_animals", "freight"],
        "price_category": "transport",
    },
    "Tailor": {
        "services": ["buy_clothing", "repair_clothing"],
        "price_category": "clothing",
    },
    "Lawyer": {
        "services": ["legal_defense", "contracts"],
        "price_category": "legal",
    },
    "Land Agent": {
        "services": ["buy_lot", "file_claim"],
        "price_category": "land",
    },
    "Sheriff": {
        "services": ["report_crime", "bounty_board"],
        "price_category": None,
    },
    "Preacher": {
        "services": ["wedding", "funeral", "confession"],
        "price_category": None,
    },
}

# Reverse lookup: service name -> list of occupations that provide it
_SERVICE_TO_OCCUPATIONS: Dict[str, List[str]] = {}
for _occ, _info in OCCUPATION_SERVICES.items():
    for _svc in _info["services"]:
        _SERVICE_TO_OCCUPATIONS.setdefault(_svc, []).append(_occ)

# All known price categories (excluding None)
ALL_PRICE_CATEGORIES: List[str] = sorted(
    {info["price_category"] for info in OCCUPATION_SERVICES.values()
     if info["price_category"] is not None}
)

# Map price_category -> list of occupations that affect it
_CATEGORY_TO_OCCUPATIONS: Dict[str, List[str]] = {}
for _occ, _info in OCCUPATION_SERVICES.items():
    cat = _info["price_category"]
    if cat is not None:
        _CATEGORY_TO_OCCUPATIONS.setdefault(cat, []).append(_occ)


# ============================================================================
#  TOWN SERVICE REGISTRY
# ============================================================================

class TownServiceRegistry:
    """
    Tracks which NPCs provide services in each town (world tile).

    Internal structure:
        _services[(wx, wy)][occupation] = [npc_id, ...]
    """

    def __init__(self) -> None:
        # (wx, wy) -> {occupation: [npc_id, ...]}
        self._services: Dict[Tuple[int, int], Dict[str, List[str]]] = {}

    # ── Registration ───────────────────────────────────────────────────────

    def register_npc(self, wx: int, wy: int, npc_id: str,
                     occupation: str) -> None:
        """Register an NPC as a service provider in a town."""
        town = self._services.setdefault((wx, wy), {})
        providers = town.setdefault(occupation, [])
        if npc_id not in providers:
            providers.append(npc_id)

    def remove_npc(self, wx: int, wy: int, npc_id: str,
                   occupation: str) -> None:
        """Remove an NPC from the registry (death, departure, etc.)."""
        town = self._services.get((wx, wy))
        if town is None:
            return
        providers = town.get(occupation)
        if providers is None:
            return
        if npc_id in providers:
            providers.remove(npc_id)
        # Clean up empty lists
        if not providers:
            del town[occupation]
        if not town:
            del self._services[(wx, wy)]

    # ── Queries ────────────────────────────────────────────────────────────

    def is_available(self, wx: int, wy: int, occupation: str) -> bool:
        """True if at least one NPC of this occupation is present."""
        town = self._services.get((wx, wy), {})
        return len(town.get(occupation, [])) > 0

    def get_providers(self, wx: int, wy: int,
                      occupation: str) -> List[str]:
        """Return NPC IDs providing this occupation's services."""
        town = self._services.get((wx, wy), {})
        return list(town.get(occupation, []))

    def get_all_occupations(self, wx: int, wy: int) -> List[str]:
        """Return all occupations with at least one provider in town."""
        town = self._services.get((wx, wy), {})
        return [occ for occ, ids in town.items() if ids]

    def get_missing(self, wx: int, wy: int) -> List[str]:
        """
        Return occupations from OCCUPATION_SERVICES that have no provider
        in this town.  Useful for showing "services unavailable" to the
        player or for immigration logic.
        """
        town = self._services.get((wx, wy), {})
        missing = []
        for occ in OCCUPATION_SERVICES:
            if not town.get(occ):
                missing.append(occ)
        return missing

    def get_available_services(self, wx: int, wy: int) -> List[str]:
        """Return flat list of service names available in this town."""
        town = self._services.get((wx, wy), {})
        services: List[str] = []
        for occ, ids in town.items():
            if ids and occ in OCCUPATION_SERVICES:
                for svc in OCCUPATION_SERVICES[occ]["services"]:
                    if svc not in services:
                        services.append(svc)
        return services

    def get_competition_count(self, wx: int, wy: int,
                              occupation: str) -> int:
        """How many NPCs of the same occupation are in this town."""
        town = self._services.get((wx, wy), {})
        return len(town.get(occupation, []))

    # ── Pricing ────────────────────────────────────────────────────────────

    def price_multiplier(self, wx: int, wy: int,
                         price_category: Optional[str]) -> float:
        """
        Calculate price multiplier for a category based on provider count.

        Scarcity drives prices up; competition drives them down.
            0 providers  -> 2.5x  (goods imported from elsewhere at markup)
            1 provider   -> 1.0x  (monopoly but present — baseline)
            2+ providers -> 0.85x (competition drives prices down)

        Returns 1.0 for categories that are None (free services like
        Sheriff, Preacher).
        """
        if price_category is None:
            return 1.0

        # Count total providers across all occupations that serve this
        # price category
        occupations_for_cat = _CATEGORY_TO_OCCUPATIONS.get(
            price_category, [])
        town = self._services.get((wx, wy), {})
        total_providers = 0
        for occ in occupations_for_cat:
            total_providers += len(town.get(occ, []))

        if total_providers == 0:
            return 2.5
        elif total_providers == 1:
            return 1.0
        else:
            return 0.85

    def price_multiplier_for_occupation(self, wx: int, wy: int,
                                        occupation: str) -> float:
        """Convenience: get price multiplier by occupation name."""
        info = OCCUPATION_SERVICES.get(occupation)
        if info is None:
            return 1.0
        return self.price_multiplier(wx, wy, info["price_category"])

    # ── Serialization ──────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dict for save files."""
        data: Dict[str, Any] = {}
        for (wx, wy), town in self._services.items():
            key = f"{wx},{wy}"
            data[key] = {}
            for occ, ids in town.items():
                if ids:
                    data[key][occ] = list(ids)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TownServiceRegistry":
        """Reconstruct from saved dict."""
        reg = cls()
        for coord_str, town_data in data.items():
            parts = coord_str.split(",")
            wx, wy = int(parts[0]), int(parts[1])
            for occ, ids in town_data.items():
                for npc_id in ids:
                    reg.register_npc(wx, wy, npc_id, occ)
        return reg


# ============================================================================
#  EVENT HANDLERS
# ============================================================================

def _occupation_label(occupation: str) -> str:
    """Human-readable lowercase label for an occupation."""
    return occupation.lower()


def _services_label(occupation: str) -> str:
    """Human-readable description of what services this occupation provides."""
    info = OCCUPATION_SERVICES.get(occupation)
    if info is None:
        return "services"
    names = []
    for svc in info["services"]:
        # Convert snake_case to readable: "buy_supplies" -> "supply sales"
        readable = svc.replace("_", " ")
        names.append(readable)
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def on_npc_death(registry: TownServiceRegistry, wx: int, wy: int,
                 npc_id: str, occupation: str,
                 all_npcs: Any) -> List[str]:
    """
    Handle an NPC dying or permanently leaving a town.

    Removes the NPC from the registry and returns narrative messages
    describing the economic impact on the settlement.

    Parameters
    ----------
    registry : TownServiceRegistry
    wx, wy : int
        World tile coordinates of the town.
    npc_id : str
        ID of the departing/dead NPC.
    occupation : str
        Occupation of that NPC.
    all_npcs : dict or object
        NPC collection (used to look up names).  Expects either a dict
        mapping npc_id -> NPC, or an object with a .get(npc_id) method.

    Returns
    -------
    List[str]
        Narrative messages for the player's journal or message log.
    """
    # Look up NPC name before removal
    npc_name = None
    if isinstance(all_npcs, dict):
        npc_obj = all_npcs.get(npc_id)
        if npc_obj is not None:
            npc_name = getattr(npc_obj, "name", None)
    elif hasattr(all_npcs, "get"):
        npc_obj = all_npcs.get(npc_id)
        if npc_obj is not None:
            npc_name = getattr(npc_obj, "name", None)

    # How many providers existed before removal?
    count_before = registry.get_competition_count(wx, wy, occupation)

    # Remove from registry
    registry.remove_npc(wx, wy, npc_id, occupation)

    count_after = registry.get_competition_count(wx, wy, occupation)

    messages: List[str] = []

    # No entry in OCCUPATION_SERVICES means no economic impact message
    if occupation not in OCCUPATION_SERVICES:
        return messages

    occ_lower = _occupation_label(occupation)
    svc_desc = _services_label(occupation)
    name_str = npc_name or f"the {occ_lower}"

    if count_after == 0:
        # Last provider is gone — services unavailable
        messages.append(
            f"The town's only {occ_lower} is dead. "
            f"{svc_desc.capitalize()} {'is' if ',' not in svc_desc else 'are'} "
            f"no longer available here."
        )
    elif count_before > count_after and count_after >= 1:
        # Still have providers but lost one — reduced competition
        cat = OCCUPATION_SERVICES[occupation]["price_category"]
        if cat is not None:
            if count_after == 1:
                messages.append(
                    f"With {name_str} gone, the remaining {occ_lower} "
                    f"now has a monopoly. Prices may rise."
                )
            else:
                messages.append(
                    f"With {name_str} gone, there is less competition "
                    f"among the town's {occ_lower}s."
                )

    return messages


# ============================================================================
#  BUSINESS EVENTS (player-owned businesses)
# ============================================================================

# Maps player business types to the NPC occupations they compete with
_BUSINESS_TYPE_TO_OCCUPATION: Dict[str, str] = {
    "general_store": "Merchant",
    "blacksmith_shop": "Blacksmith",
    "saloon": "Saloon Keeper",
    "doctor_office": "Doctor",
    "assay_office": "Assayer",
    "bakery": "Baker",
    "butcher_shop": "Butcher",
    "livery": "Teamster",
    "tailor_shop": "Tailor",
    "law_office": "Lawyer",
    "bank": "Banker",
}


def on_business_event(registry: TownServiceRegistry, wx: int, wy: int,
                      business_type: str,
                      event_type: str) -> float:
    """
    Calculate price adjustment when a player's business is affected by
    competition changes.

    Parameters
    ----------
    registry : TownServiceRegistry
    wx, wy : int
        World tile of the town.
    business_type : str
        Key from _BUSINESS_TYPE_TO_OCCUPATION (e.g. "general_store").
    event_type : str
        One of:
        - "competitor_died"   — NPC competitor died or burned down
        - "competitor_left"   — NPC competitor departed town
        - "player_opened"     — player opened a business of this type
        - "player_closed"     — player closed their business

    Returns
    -------
    float
        Price adjustment multiplier for the player's business revenue.
        > 1.0 means more profit (monopoly bonus).
        < 1.0 means less profit (competition penalty).
        1.0 means no change.
    """
    occupation = _BUSINESS_TYPE_TO_OCCUPATION.get(business_type)
    if occupation is None:
        return 1.0

    info = OCCUPATION_SERVICES.get(occupation)
    if info is None:
        return 1.0

    npc_count = registry.get_competition_count(wx, wy, occupation)

    if event_type in ("competitor_died", "competitor_left"):
        # NPC competitor gone — player may now have monopoly
        if npc_count == 0:
            # Player is the only provider: monopoly bonus
            return 1.5
        elif npc_count == 1:
            # One NPC left, plus player: mild bonus from reduced competition
            return 1.15
        else:
            # Still several competitors
            return 1.05

    elif event_type == "player_opened":
        # Player entering the market — competition effect
        if npc_count == 0:
            # No NPC competition: player has the field to themselves
            return 1.3
        elif npc_count == 1:
            # One NPC competitor: split market
            return 0.85
        else:
            # Crowded market
            return 0.7

    elif event_type == "player_closed":
        # Player leaving the market — no adjustment needed for player
        return 1.0

    return 1.0
