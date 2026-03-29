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
            },
            "stance":     p.stance,
            "speed":      p.speed,
            "cash":       p.cash,
            "gold_oz":    p.gold_oz,
            "left_hand":  p.left_hand,
            "right_hand": p.right_hand,
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
        },
        "messages": engine.messages[-50:],  # last 50
    }

    # ── NPC state ─────────────────────────────────────────────────────
    npc_data = {}
    for npc_id, npc in engine.npc_mgr.npcs.items():
        npc_data[npc_id] = {
            "npc_id": npc.npc_id, "name": npc.name, "age": npc.age,
            "gender": npc.gender, "occupation": npc.occupation,
            "attributes": npc.attributes, "skills": npc.skills,
            "knowledge": npc.knowledge, "traits": npc.traits,
            "local_x": npc.local_x, "local_y": npc.local_y,
            "alive": npc.alive, "present": npc.present,
            "health": npc.health, "combat_state": npc.combat_state,
            "relationship": npc.relationship,
            "knows_name": npc.memory.knows_name,
            "last_seen_day": npc.memory.last_seen_day,
            "facts": npc.memory.facts,
            "backstory_revealed": npc.backstory_revealed,
            "backstory_hidden": npc.backstory_hidden,
            "schedule": npc.schedule,
        }
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

    # Writing / mail system
    if hasattr(engine, "writing") and engine.writing:
        data["writing"] = engine.writing.to_dict()

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
    p.stance     = pd.get("stance", "Standing")
    p.speed      = pd.get("speed",  "Walk")

    s = p.survival
    sd = pd["survival"]
    s.health  = sd["health"]
    s.hunger  = sd["hunger"]
    s.thirst  = sd["thirst"]
    s.warmth  = sd["warmth"]
    s.fatigue = sd["fatigue"]

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
        from src.npc import NPC, NPCMemory
        for npc_id, nd in data["npcs"].items():
            if npc_id in engine.npc_mgr.npcs:
                npc = engine.npc_mgr.npcs[npc_id]
            else:
                npc = NPC(npc_id=nd["npc_id"], name=nd["name"])
                engine.npc_mgr.npcs[npc_id] = npc
            npc.age = nd.get("age", 35)
            npc.gender = nd.get("gender", "M")
            npc.occupation = nd.get("occupation", "Prospector")
            npc.attributes = nd.get("attributes", npc.attributes)
            npc.skills = nd.get("skills", {})
            npc.knowledge = nd.get("knowledge", {})
            npc.traits = nd.get("traits", [])
            npc.local_x = nd.get("local_x", 0)
            npc.local_y = nd.get("local_y", 0)
            npc.alive = nd.get("alive", True)
            npc.present = nd.get("present", True)
            npc.health = nd.get("health", 100.0)
            npc.combat_state = nd.get("combat_state", "neutral")
            npc.relationship = nd.get("relationship", 0.0)
            npc.memory.knows_name = nd.get("knows_name", False)
            npc.memory.last_seen_day = nd.get("last_seen_day", 0)
            npc.memory.facts = nd.get("facts", [])
            npc.backstory_revealed = nd.get("backstory_revealed", [])
            npc.backstory_hidden = nd.get("backstory_hidden", [])
            npc.schedule = nd.get("schedule", {})

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
    if "writing" in data:
        from src.writing import WritingManager
        engine.writing = WritingManager.from_dict(data["writing"])

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


def _serialize_local(lmap) -> dict:
    tiles = []
    for row in lmap.tiles:
        tiles.append([{
            "terrain":  t.terrain,
            "explored": t.explored,
            "gold_grade": t.gold_grade,
        } for t in row])
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


def _deserialize_local(lmap, data: dict):
    for y, row in enumerate(data.get("tiles", [])):
        for x, td in enumerate(row):
            if y < lmap.height and x < lmap.width:
                lmap.tiles[y][x].terrain   = td.get("terrain", 0)
                lmap.tiles[y][x].explored  = td.get("explored", False)
                lmap.tiles[y][x].gold_grade = td.get("gold_grade", 0.0)

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
