"""
Save/load game state as JSON.
Saves go in saves/ directory. Autosave on sleep.
"""

import json
import os
import time
from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine import Engine

SAVE_DIR = "saves"


def _ensure_save_dir():
    os.makedirs(SAVE_DIR, exist_ok=True)


def save_game(engine: "Engine", slot: str = "autosave") -> str:
    """Serialize engine state to JSON. Returns save file path."""
    _ensure_save_dir()

    p = engine.player
    data = {
        "version": 1,
        "timestamp": time.time(),
        "time": {"total_minutes": engine.time.total_minutes},
        "player": {
            "name":       p.name,
            "age":        p.age,
            "world_x":    p.world_x,
            "world_y":    p.world_y,
            "area_x":     p.area_x,
            "area_y":     p.area_y,
            "local_x":    p.local_x,
            "local_y":    p.local_y,
            "local_z":    p.local_z,
            "attributes": p.attributes,
            "skills":     p.skills,
            "skill_xp":   p.skill_xp,
            "knowledge":  p.knowledge,
            "survival": {
                "health":  p.survival.health,
                "hunger":  p.survival.hunger,
                "thirst":  p.survival.thirst,
                "warmth":  p.survival.warmth,
                "fatigue": p.survival.fatigue,
                "drunk_level": p.survival.drunk_level,
                "gut_sick_hours": p.survival.gut_sick_hours,
                "mercury_exposure": p.survival.mercury_exposure,
                "days_meat_only": p.survival.days_meat_only,
                "diseases": p.survival.diseases,
            },
            "stance":     p.stance,
            "speed":      p.speed,
            "cash":       p.cash,
            "gold_oz":    p.gold_oz,
            "left_hand":  p.left_hand,
            "right_hand": p.right_hand,
            "pan_loaded":    p.pan_loaded,
            "pan_source_x":  p.pan_source_x,
            "pan_source_y":  p.pan_source_y,
            "mounted":       p.mounted,
            "mount_animal_id": p.mount_animal_id,
            "languages":     getattr(p, 'languages', {"english": "fluent"}),
            "lang_exposure":  getattr(p, '_lang_exposure', {}),
            "in_canoe":      getattr(p, '_in_canoe', False),
            "canoe_type":    getattr(p, '_canoe_type', ""),
            "inventory":  [_serialize_item(i) for i in p.inventory],
        },
        "world": {
            "seed":    engine.world.seed,
            "visited": engine.world.visited.tolist(),
            "discovered_locations": [
                name for name, loc in engine.world.locations.items()
                if loc.discovered
            ],
        },
        "local_maps": {
            f"{wx},{wy},{ax},{ay}": _serialize_local(lmap)
            for (wx, wy, ax, ay), lmap in engine.locals.items()
            if getattr(lmap, '_dirty', True)  # skip pristine maps
        },
        "messages": engine.messages[-50:],  # last 50
    }

    # ── NPC state ─────────────────────────────────────────────────────
    npc_data = {}
    for npc_id, npc in engine.npc_mgr.npcs.items():
        if hasattr(npc, 'to_dict'):
            npc_data[npc_id] = npc.to_dict()
        else:
            # Legacy NPC fallback
            npc_data[npc_id] = {
                "npc_id": npc.npc_id, "name": npc.name, "age": npc.age,
                "gender": npc.gender, "occupation": npc.occupation,
                "attributes": npc.attributes, "skills": npc.skills,
                "knowledge": npc.knowledge, "traits": npc.traits,
                "local_x": npc.local_x, "local_y": npc.local_y,
                "local_z": getattr(npc, 'local_z', 0),
                "alive": npc.alive, "present": npc.present,
                "health": npc.health, "combat_state": npc.combat_state,
                "relationship": npc.relationship,
                "knows_name": npc.memory.knows_name,
                "last_seen_day": npc.memory.last_seen_day,
                "facts": npc.memory.facts,
                "backstory_revealed": getattr(npc, 'backstory_revealed', []),
                "backstory_hidden": getattr(npc, 'backstory_hidden', []),
                "schedule": getattr(npc, 'schedule', {}),
            }
    # Also save NPCs from the generator (persistent NPCs not on current map)
    if hasattr(engine, '_npc_gen') and engine._npc_gen:
        for npc_id, npc in engine._npc_gen.npcs.items():
            if npc_id not in npc_data and hasattr(npc, 'to_dict'):
                npc_data[npc_id] = npc.to_dict()
    data["npcs"] = npc_data

    # ── New systems ───────────────────────────────────────────────────
    # Worn clothing
    if hasattr(p, "worn") and p.worn:
        try:
            data["player"]["worn"] = p.worn.to_dict()
        except Exception:
            pass

    # Wounds (new health system)
    try:
        data["player"]["wounds"] = p.wounds.to_dict()
    except Exception:
        pass

    # Dynamic locations
    if hasattr(engine, "dynamic_locs") and engine.dynamic_locs:
        try:
            data["dynamic_locations"] = engine.dynamic_locs.to_dict()
        except Exception:
            pass

    # Reputation
    if hasattr(engine, "reputation") and engine.reputation:
        try:
            data["reputation"] = engine.reputation.to_dict()
        except Exception:
            pass

    # Companions
    if hasattr(engine, "companion_mgr") and engine.companion_mgr:
        try:
            data["companions"] = engine.companion_mgr.to_dict()
        except Exception:
            pass

    # Legal
    if hasattr(engine, "legal") and engine.legal:
        try:
            data["legal"] = engine.legal.to_dict()
        except Exception:
            pass

    # Businesses
    if hasattr(engine, "business_mgr") and engine.business_mgr:
        try:
            data["businesses"] = engine.business_mgr.to_dict()
        except Exception:
            pass

    # Action history
    if hasattr(engine, "action_history") and engine.action_history:
        try:
            data["action_history"] = engine.action_history.to_dict()
        except Exception:
            pass

    # Journal
    if hasattr(engine, "journal") and engine.journal:
        try:
            data["journal"] = engine.journal.to_dict()
        except Exception:
            pass

    # Writing / mail system
    if hasattr(engine, "writing") and engine.writing:
        data["writing"] = engine.writing.to_dict()

    # Trapping system
    if hasattr(engine, "trap_mgr") and engine.trap_mgr:
        try:
            data["traps"] = engine.trap_mgr.to_dict()
        except Exception:
            pass

    # Pack animals
    if hasattr(engine, "animal_mgr") and engine.animal_mgr:
        try:
            data["pack_animals"] = engine.animal_mgr.to_dict()
        except Exception:
            pass

    # Mining claims
    if hasattr(engine, "claim_mgr") and engine.claim_mgr:
        try:
            data["claims"] = engine.claim_mgr.to_dict()
        except Exception:
            pass

    # Vehicles
    if hasattr(engine, "vehicle_mgr") and engine.vehicle_mgr:
        try:
            data["vehicles"] = engine.vehicle_mgr.to_dict()
        except Exception:
            pass

    # Bounty board
    if hasattr(engine, "bounty_board") and engine.bounty_board:
        try:
            data["bounty_board"] = engine.bounty_board.to_dict()
        except Exception:
            pass

    # Newspaper
    if hasattr(engine, "newspaper") and engine.newspaper:
        try:
            data["newspaper"] = engine.newspaper.to_dict()
        except Exception:
            pass

    # Property
    if hasattr(engine, "property_mgr") and engine.property_mgr:
        try:
            data["property"] = engine.property_mgr.to_dict()
        except Exception:
            pass

    # Rival prospectors
    if hasattr(engine, "rival_system") and engine.rival_system:
        try:
            data["rivals"] = engine.rival_system.to_dict()
        except Exception:
            pass

    # Town services
    if hasattr(engine, "town_services") and engine.town_services:
        try:
            data["town_services"] = engine.town_services.to_dict()
        except Exception:
            pass

    # Era
    data["era_id"] = getattr(engine, "era_id", "gold_rush")
    data["start_minutes"] = getattr(engine, "_start_minutes", engine.time.total_minutes)

    # Combat seen messages (no-repeat system)
    try:
        from src.combat import _seen_messages
        data["seen_combat_msgs"] = {k: list(v) for k, v in _seen_messages.items()}
    except ImportError:
        pass

    # Tribal system
    if hasattr(engine, "tribal") and engine.tribal:
        try:
            data["tribal"] = engine.tribal.to_dict()
        except Exception:
            pass

    # War system
    if hasattr(engine, "war_system") and engine.war_system:
        data["war_system"] = engine.war_system.to_dict()

    # Marriage
    if engine.marriage_state:
        from src.marriage import to_dict as _marriage_to_dict
        data["marriage"] = _marriage_to_dict(engine.marriage_state)

    # Settlement price effects
    if hasattr(engine, "_settlement_price_effects"):
        data["settlement_price_effects"] = engine._settlement_price_effects

    # Item factory catalog (also saves to its own file)
    if hasattr(engine, "item_factory") and engine.item_factory:
        try:
            engine.item_factory.save()
        except Exception:
            pass

    # Construction (per local map — wall grids, build queues, zones)
    # Saved inside local_maps serialization below

    path = os.path.join(SAVE_DIR, f"{slot}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


def load_game(engine: "Engine", slot: str = "autosave") -> bool:
    """Load state into existing engine. Returns True on success."""
    path = os.path.join(SAVE_DIR, f"{slot}.json")
    if not os.path.exists(path):
        return False

    with open(path) as f:
        data = json.load(f)

    # Time
    engine.time.total_minutes = data["time"]["total_minutes"]

    # Player
    pd = data["player"]
    p  = engine.player
    p.name       = pd["name"]
    p.age        = pd["age"]
    p.world_x    = pd["world_x"]
    p.world_y    = pd["world_y"]
    p.area_x     = pd.get("area_x", 7)
    p.area_y     = pd.get("area_y", 7)
    p.local_x    = pd["local_x"]
    p.local_y    = pd["local_y"]
    p.local_z    = pd.get("local_z", 0)
    p.attributes = pd["attributes"]
    p.skills     = pd["skills"]
    p.skill_xp   = pd["skill_xp"]
    p.knowledge  = pd["knowledge"]
    p.cash       = pd["cash"]
    p.gold_oz    = pd.get("gold_oz", 0.0)
    p.left_hand  = pd.get("left_hand")
    p.right_hand = pd.get("right_hand")
    p.pan_loaded   = pd.get("pan_loaded", False)
    p.pan_source_x = pd.get("pan_source_x", 0)
    p.pan_source_y = pd.get("pan_source_y", 0)
    p.mounted      = pd.get("mounted", False)
    p.mount_animal_id = pd.get("mount_animal_id", None)
    p.languages    = pd.get("languages", {"english": "fluent"})
    p._lang_exposure = pd.get("lang_exposure", {})
    p._in_canoe    = pd.get("in_canoe", False)
    p._canoe_type  = pd.get("canoe_type", "")
    p.stance     = pd.get("stance", "Standing")
    p.speed      = pd.get("speed",  "Walk")

    s = p.survival
    sd = pd["survival"]
    s.health  = sd["health"]
    s.hunger  = sd["hunger"]
    s.thirst  = sd["thirst"]
    s.warmth  = sd["warmth"]
    s.fatigue = sd["fatigue"]
    s.drunk_level = sd.get("drunk_level", 0.0)
    s.gut_sick_hours = sd.get("gut_sick_hours", 0.0)
    s.mercury_exposure = sd.get("mercury_exposure", 0.0)
    s.days_meat_only = sd.get("days_meat_only", 0)
    s.diseases = sd.get("diseases", [])

    from src.items import Item
    p.inventory = [_deserialize_item(i) for i in pd.get("inventory", [])]

    # World
    import numpy as np
    wd = data["world"]
    engine.world = engine.world.__class__(seed=wd["seed"])
    engine.world.visited = np.array(wd["visited"], dtype=bool)
    for name in wd.get("discovered_locations", []):
        if name in engine.world.locations:
            engine.world.locations[name].discovered = True

    # Local maps (supports both old "wx,wy" and new "wx,wy,ax,ay" keys)
    engine.locals = {}
    for key_str, ldata in data.get("local_maps", {}).items():
        parts = list(map(int, key_str.split(",")))
        if len(parts) == 4:
            wx, wy, ax, ay = parts
        else:
            wx, wy = parts[0], parts[1]
            ax, ay = 7, 7  # legacy saves default to center patch
        lmap = engine._ensure_local(wx, wy, ax, ay)
        _deserialize_local(lmap, ldata)

    engine.messages = [tuple(m) for m in data.get("messages", [])]

    # ── Restore NPC state ─────────────────────────────────────────────
    if "npcs" in data:
        from src.npc_system import NPCExpanded
        from src.npc import NPC, NPCMemory
        for npc_id, nd in data["npcs"].items():
            # Use NPCExpanded.from_dict if data has expanded fields
            if "rel" in nd or "memory" in nd:
                npc = NPCExpanded.from_dict(nd)
            else:
                # Legacy save — build NPCExpanded from old fields
                npc = NPCExpanded(nd.get("npc_id", npc_id), nd.get("name", ""))
                for k in ("age", "gender", "occupation", "attributes", "skills",
                           "knowledge", "traits", "local_x", "local_y", "local_z",
                           "alive", "present", "health", "combat_state",
                           "backstory_revealed", "backstory_hidden", "schedule"):
                    if k in nd:
                        setattr(npc, k, nd[k])
                npc.rel.affinity = nd.get("relationship", 0.0)
                npc.memory.knows_name = nd.get("knows_name", False)
                npc.memory.last_seen_day = nd.get("last_seen_day", 0)
                for fact in nd.get("facts", []):
                    npc.expanded_memory.add(fact, 0, significance=0.4)
            engine.npc_mgr.npcs[npc_id] = npc
            # Also restore into _npc_gen for background simulation
            if hasattr(engine, '_npc_gen'):
                engine._npc_gen.npcs[npc_id] = npc

    # ── Restore new systems ───────────────────────────────────────────
    from src.clothing import WornEquipment
    from src.health_system import HealthTracker
    from src.dynamic_locations import DynamicLocationDB
    from src.economy import ReputationTracker
    from src.companions import CompanionManager
    from src.legal import LegalSystem
    from src.business import BusinessManager
    from src.action_menu import ActionHistory

    if "worn" in pd:
        p.worn = WornEquipment.from_dict(pd["worn"])
    if "wounds" in pd:
        p.wounds = HealthTracker.from_dict(pd["wounds"])
    if "dynamic_locations" in data:
        engine.dynamic_locs = DynamicLocationDB.from_dict(data["dynamic_locations"])
    if "reputation" in data:
        engine.reputation = ReputationTracker.from_dict(data["reputation"])
    if "companions" in data:
        engine.companion_mgr = CompanionManager.from_dict(data["companions"])
    if "legal" in data:
        engine.legal = LegalSystem.from_dict(data["legal"])
    if "businesses" in data:
        engine.business_mgr = BusinessManager.from_dict(data["businesses"], engine.llm)
    if "action_history" in data:
        engine.action_history = ActionHistory.from_dict(data["action_history"])
    if "journal" in data:
        from src.journal import Journal
        engine.journal = Journal.from_dict(data["journal"])
    if "writing" in data:
        from src.writing import WritingManager
        engine.writing = WritingManager.from_dict(data["writing"])

    # Traps
    if "traps" in data:
        from src.trapping import TrapManager
        engine.trap_mgr = TrapManager.from_dict(data["traps"])

    # Pack animals
    if "pack_animals" in data:
        from src.pack_animals import PackAnimalManager
        engine.animal_mgr = PackAnimalManager.from_dict(data["pack_animals"])
        engine.player._animal_mgr = engine.animal_mgr

    # Mining claims
    if "claims" in data:
        from src.claims import ClaimManager
        engine.claim_mgr = ClaimManager.from_dict(data["claims"])

    # Vehicles
    if "vehicles" in data:
        from src.vehicles import VehicleManager
        engine.vehicle_mgr = VehicleManager.from_dict(data["vehicles"])

    # Bounty board
    if "bounty_board" in data:
        from src.bounty_system import BountyBoard
        engine.bounty_board = BountyBoard.from_dict(data["bounty_board"])

    # Newspaper
    if "newspaper" in data:
        from src.newspaper import NewspaperSystem
        engine.newspaper = NewspaperSystem.from_dict(data["newspaper"])

    # Property
    if "property" in data:
        from src.property import PropertyManager
        engine.property_mgr = PropertyManager.from_dict(data["property"])

    # Combat seen messages (no-repeat system)
    if "seen_combat_msgs" in data:
        try:
            from src.combat import _seen_messages
            _seen_messages.clear()
            for k, v in data["seen_combat_msgs"].items():
                _seen_messages[k] = set(v)
        except ImportError:
            pass

    # Rival prospectors
    if "rivals" in data:
        from src.rival_prospectors import RivalProspectorSystem
        engine.rival_system = RivalProspectorSystem.from_dict(data["rivals"])

    # Era
    engine.era_id = data.get("era_id", "gold_rush")
    engine._start_minutes = data.get("start_minutes", engine.time.total_minutes)

    # Tribal system
    if "tribal" in data:
        from src.tribal_system import TribalSystem
        engine.tribal = TribalSystem.from_dict(data["tribal"])

    # War system
    if "war_system" in data:
        from src.war_system import WarSystem
        engine.war_system = WarSystem.from_dict(data["war_system"])

    # Town services
    if "town_services" in data:
        from src.town_services import TownServiceRegistry
        engine.town_services = TownServiceRegistry.from_dict(data["town_services"])

    # Marriage
    if "marriage" in data:
        from src.marriage import from_dict as _marriage_from_dict
        engine.marriage_state = _marriage_from_dict(data["marriage"])

    # Settlement price effects
    if "settlement_price_effects" in data:
        engine._settlement_price_effects = data["settlement_price_effects"]

    return True


def list_saves() -> list:
    _ensure_save_dir()
    saves = []
    for fname in os.listdir(SAVE_DIR):
        if fname.endswith(".json"):
            path = os.path.join(SAVE_DIR, fname)
            try:
                with open(path) as f:
                    d = json.load(f)
                saves.append({
                    "slot": fname[:-5],
                    "name": d["player"]["name"],
                    "date": d["time"],
                    "timestamp": d.get("timestamp", 0),
                })
            except Exception:
                pass
    saves.sort(key=lambda s: s["timestamp"], reverse=True)
    return saves


# ── Serialization helpers ───────────────────────────────────────────────────

def _serialize_item(item) -> dict:
    return {
        "id":            item.id,
        "name":          item.name,
        "weight":        item.weight,
        "category":      item.category,
        "description":   item.description,
        "nutrition":     item.nutrition,
        "hydration":     item.hydration,
        "perishable":    item.perishable,
        "days_until_spoil": item.days_until_spoil,
        "tool_tags":     item.tool_tags,
        "condition":     item.condition,
        "quality":       item.quality,
        "damage_min":    item.damage_min,
        "damage_max":    item.damage_max,
        "weapon_type":   item.weapon_type,
        "base_value":    item.base_value,
        "stackable":     item.stackable,
        "quantity":      item.quantity,
        "extra":         item.extra,
        "unpaid":        item.unpaid,
    }


def _deserialize_item(d: dict):
    from src.items import Item
    return Item(
        id=d["id"], name=d["name"], weight=d["weight"],
        category=d["category"], description=d.get("description", ""),
        nutrition=d.get("nutrition", 0.0), hydration=d.get("hydration", 0.0),
        perishable=d.get("perishable", False),
        days_until_spoil=d.get("days_until_spoil"),
        tool_tags=d.get("tool_tags", []),
        condition=d.get("condition", 100.0), quality=d.get("quality", "standard"),
        damage_min=d.get("damage_min", 0), damage_max=d.get("damage_max", 0),
        weapon_type=d.get("weapon_type", ""),
        base_value=d.get("base_value", 0.0),
        stackable=d.get("stackable", False), quantity=d.get("quantity", 1),
        extra=d.get("extra", {}),
        unpaid=d.get("unpaid", False),
    )


def _serialize_tile(t) -> dict:
    """Serialize a single tile to dict, including only non-default fields."""
    td = {
        "terrain":  t.terrain,
        "explored": t.explored,
        "gold_grade": t.gold_grade,
    }
    if t.dig_depth:
        td["dig_depth"] = t.dig_depth
    if t.panned:
        td["panned"] = True
    if getattr(t, 'sluiced', False):
        td["sluiced"] = True
    if getattr(t, 'sluice_avg_grade', -1) >= 0:
        td["sluice_avg_grade"] = t.sluice_avg_grade
    if t.mineral_hint:
        td["mineral_hint"] = t.mineral_hint
    if t.blood:
        td["blood"] = t.blood
    if t.ground_items:
        td["ground_items"] = [_serialize_item(i) for i in t.ground_items]
    if t.gold_column:
        td["gold_column"] = {
            "total_dug_depth": t.gold_column.total_dug_depth,
            "tailings_volume": t.gold_column.tailings_volume,
            "layers": [
                {"gold_grade": l.gold_grade,
                 "remaining_volume": l.remaining_volume,
                 "is_bedrock": l.is_bedrock}
                for l in t.gold_column.layers
            ],
        }
    return td


def _serialize_local(lmap) -> dict:
    # Use sparse format: only save modified tiles to reduce file size
    is_dirty = getattr(lmap, '_dirty', False)

    if is_dirty and hasattr(lmap, '_original_terrain'):
        # Sparse format: only save tiles that differ from generated state
        modified_tiles = []
        for y in range(lmap.height):
            for x in range(lmap.width):
                if lmap.is_tile_modified(x, y):
                    td = _serialize_tile(lmap.tiles[y][x])
                    td["_x"] = x
                    td["_y"] = y
                    modified_tiles.append(td)
        result = {"format": "sparse", "modified_tiles": modified_tiles,
                  "seed": lmap.seed}
    else:
        # Dense format (legacy): save all tiles
        tiles = []
        for row in lmap.tiles:
            row_data = [_serialize_tile(t) for t in row]
            tiles.append(row_data)
        result = {"tiles": tiles}

    # Z-level elevation
    if hasattr(lmap, "surface_z") and lmap.surface_z is not None:
        result["surface_z"] = lmap.surface_z.tolist()
    if hasattr(lmap, "z_tiles") and lmap.z_tiles:
        result["z_tiles"] = {
            f"{x},{y},{z}": {"terrain": zt.terrain, "explored": zt.explored,
                              "gold_grade": zt.gold_grade}
            for (x, y, z), zt in lmap.z_tiles.items()
        }

    # Construction overlays
    if hasattr(lmap, "wall_grid") and lmap.wall_grid:
        try:
            result["wall_grid"] = lmap.wall_grid.to_dict()
        except Exception:
            pass
    if hasattr(lmap, "floor_overlay") and lmap.floor_overlay:
        try:
            result["floor_overlay"] = lmap.floor_overlay.to_dict()
        except Exception:
            pass
    if hasattr(lmap, "build_queue") and lmap.build_queue:
        try:
            result["build_queue"] = lmap.build_queue.to_dict()
        except Exception:
            pass
    if hasattr(lmap, "zones") and lmap.zones:
        try:
            result["zones"] = [
                {"id": z.id, "zone_type": z.zone_type,
                 "x": z.x, "y": z.y, "width": z.width, "height": z.height,
                 "label": z.label}
                for z in lmap.zones
            ]
        except Exception:
            pass

    # Placed structures
    if lmap.structures:
        try:
            from src.construction import PlacedEquipment
            struct_list = []
            for sid, s in lmap.structures.items():
                if isinstance(s, PlacedEquipment):
                    struct_list.append({
                        "id": s.id, "blueprint_key": s.blueprint_key,
                        "name": s.name, "x": s.x, "y": s.y,
                        "width": s.width, "height": s.height,
                        "condition": s.condition, "progress": s.progress,
                        "functional_tags": s.functional_tags,
                    })
            if struct_list:
                result["structures"] = struct_list
        except Exception:
            pass

    return result


def _apply_tile_data(tile, td):
    """Apply saved data to a single tile."""
    tile.terrain      = td.get("terrain", tile.terrain)
    tile.explored     = td.get("explored", False)
    tile.gold_grade   = td.get("gold_grade", tile.gold_grade)
    tile.dig_depth    = td.get("dig_depth", 0)
    tile.panned       = td.get("panned", False)
    tile.sluiced      = td.get("sluiced", False)
    tile.sluice_avg_grade = td.get("sluice_avg_grade", -1.0)
    tile.mineral_hint = td.get("mineral_hint", "")
    tile.blood        = td.get("blood", 0)
    if "ground_items" in td:
        tile.ground_items = [_deserialize_item(i) for i in td["ground_items"]]
    if "gold_column" in td:
        from src.volume_gold import GoldColumn, DepthLayer
        gc = td["gold_column"]
        tile.gold_column = GoldColumn(
            total_dug_depth=gc.get("total_dug_depth", 0),
            tailings_volume=gc.get("tailings_volume", 0.0),
            layers=[DepthLayer(**ld) for ld in gc.get("layers", [])],
        )


def _deserialize_local(lmap, data: dict):
    fmt = data.get("format", "dense")

    if fmt == "sparse":
        # Sparse format: map was regenerated from seed, apply only modified tiles
        for td in data.get("modified_tiles", []):
            x, y = td["_x"], td["_y"]
            if y < lmap.height and x < lmap.width:
                _apply_tile_data(lmap.tiles[y][x], td)
        lmap._dirty = True
    else:
        # Dense format (legacy): overwrite all tiles
        for y, row in enumerate(data.get("tiles", [])):
            for x, td in enumerate(row):
                if y < lmap.height and x < lmap.width:
                    _apply_tile_data(lmap.tiles[y][x], td)

    # Restore z-level elevation
    if "surface_z" in data:
        import numpy as np
        lmap.surface_z = np.array(data["surface_z"], dtype=np.int8)
    if "z_tiles" in data:
        from src.local_map import ZTile
        for key_str, ztd in data["z_tiles"].items():
            x, y, z = map(int, key_str.split(","))
            lmap.z_tiles[(x, y, z)] = ZTile(**ztd)

    # Restore construction overlays
    if "wall_grid" in data:
        try:
            from src.construction import WallGrid
            lmap.wall_grid = WallGrid.from_dict(data["wall_grid"])
        except Exception:
            pass
    if "floor_overlay" in data:
        try:
            from src.construction import FloorOverlay
            lmap.floor_overlay = FloorOverlay.from_dict(data["floor_overlay"])
        except Exception:
            pass
    if "build_queue" in data:
        try:
            from src.construction import BuildQueue
            lmap.build_queue = BuildQueue.from_dict(data["build_queue"])
        except Exception:
            pass
    if "zones" in data:
        try:
            from src.construction import DesignatedZone
            lmap.zones = [DesignatedZone(**zd) for zd in data["zones"]]
        except Exception:
            pass
    if "structures" in data:
        try:
            from src.construction import PlacedEquipment
            for sd in data["structures"]:
                equip = PlacedEquipment(**sd)
                lmap.structures[equip.id] = equip
        except Exception:
            pass
