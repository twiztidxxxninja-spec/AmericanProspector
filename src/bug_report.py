"""
src/bug_report.py

In-game bug reporting system. Players press "Report Bug" in the ESC menu,
type a description, and the report is:
  1. Saved locally to bug_reports.json (always)
  2. Sent to a Discord webhook if configured in config.json (optional)

Reports include: description, game state snapshot, recent messages,
player position, version, timestamp.

Config (config.json):
  "bug_report_webhook": "https://discord.com/api/webhooks/..."
"""

import json
import os
import time
import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.engine import Engine

BUG_REPORT_FILE = "bug_reports.json"


def _collect_state(engine: "Engine") -> dict:
    """Snapshot current game state for the report."""
    p = engine.player
    from src.version import VERSION, VERSION_NAME

    # Recent messages (last 20)
    recent = []
    for text, sev in engine.messages[-20:]:
        recent.append(f"[{sev}] {text}")

    # Inventory summary (just names, not full items)
    inv_summary = []
    for item in p.inventory[:15]:
        qty = f" x{item.quantity}" if getattr(item, 'stackable', False) and item.quantity > 1 else ""
        inv_summary.append(f"{item.name}{qty}")

    # Wounds
    wounds = []
    if hasattr(p, 'wounds'):
        for w in p.wounds.active_wounds:
            wounds.append(f"{w.description} on {w.part}")

    # Current map info
    map_info = ""
    if engine.current_local and hasattr(engine.current_local, 'town_layout'):
        layout = engine.current_local.town_layout
        if layout:
            map_info = f"{layout.settlement_name} ({layout.settlement_type})"
        else:
            map_info = "wilderness"
    else:
        map_info = f"world ({p.world_x}, {p.world_y})"

    return {
        "version": VERSION,
        "version_name": VERSION_NAME,
        "timestamp": time.time(),
        "datetime": datetime.datetime.now().isoformat(),
        "player": {
            "name": p.name,
            "age": p.age,
            "position": {
                "world": f"({p.world_x}, {p.world_y})",
                "area": f"({p.area_x}, {p.area_y})",
                "local": f"({p.local_x}, {p.local_y}, z={p.local_z})",
            },
            "health": p.survival.health,
            "hunger": p.survival.hunger,
            "thirst": p.survival.thirst,
            "cash": p.cash,
            "gold_oz": p.gold_oz,
        },
        "location": map_info,
        "game_day": engine.time.total_minutes // 1440,
        "game_date": getattr(engine.time, 'date_string', ''),
        "wounds": wounds,
        "inventory_count": len(p.inventory),
        "inventory_sample": inv_summary,
        "recent_messages": recent,
        "businesses": len(engine.business_mgr.businesses) if hasattr(engine, 'business_mgr') else 0,
        "npcs_present": sum(1 for n in engine.npc_mgr.npcs.values()
                           if n.present and n.alive) if hasattr(engine, 'npc_mgr') else 0,
    }


def save_bug_report(engine: "Engine", description: str) -> str:
    """Save a bug report locally and optionally send to webhook.
    Returns status message."""
    state = _collect_state(engine)
    report = {
        "description": description,
        "state": state,
    }

    # ── Save locally ─────────────────────────────────────────────────
    existing = []
    if os.path.exists(BUG_REPORT_FILE):
        try:
            with open(BUG_REPORT_FILE) as f:
                existing = json.load(f)
        except (json.JSONDecodeError, IOError):
            existing = []

    existing.append(report)
    with open(BUG_REPORT_FILE, "w") as f:
        json.dump(existing, f, indent=2)

    # ── Send to Discord webhook ──────────────────────────────────────
    webhook_url = ""
    try:
        with open("config.json") as f:
            cfg = json.load(f)
        webhook_url = cfg.get("bug_report_webhook", "")
    except Exception:
        pass

    webhook_sent = False
    if webhook_url:
        webhook_sent = _send_discord_webhook(webhook_url, description, state)

    # Status
    if webhook_sent:
        return "Bug report saved and sent to developer!"
    else:
        return "Bug report saved locally."


def _send_discord_webhook(url: str, description: str, state: dict) -> bool:
    """Send bug report to Discord webhook. Returns True on success."""
    try:
        import urllib.request
        import urllib.error

        # Build Discord embed
        player = state.get("player", {})
        pos = player.get("position", {})

        # Truncate recent messages to fit Discord limits
        recent = state.get("recent_messages", [])[-8:]
        recent_text = "\n".join(recent) if recent else "(none)"
        if len(recent_text) > 800:
            recent_text = recent_text[-800:]

        embed = {
            "title": f"Bug Report — {state.get('version', '?')}",
            "description": description[:2000],
            "color": 0xFF4444,  # red
            "fields": [
                {"name": "Player", "value": f"{player.get('name', '?')}, age {player.get('age', '?')}", "inline": True},
                {"name": "Location", "value": state.get("location", "?"), "inline": True},
                {"name": "Game Date", "value": state.get("game_date", "?"), "inline": True},
                {"name": "Health", "value": f"{player.get('health', 0):.0f}%", "inline": True},
                {"name": "Cash", "value": f"${player.get('cash', 0):.2f}", "inline": True},
                {"name": "Position", "value": f"W{pos.get('world', '?')} A{pos.get('area', '?')} L{pos.get('local', '?')}", "inline": True},
                {"name": "Recent Messages", "value": f"```\n{recent_text}\n```", "inline": False},
            ],
            "footer": {"text": f"v{state.get('version', '?')} {state.get('version_name', '')} | {state.get('datetime', '')}"},
        }

        # Wounds if any
        wounds = state.get("wounds", [])
        if wounds:
            embed["fields"].insert(5, {
                "name": "Wounds",
                "value": "\n".join(wounds[:5]),
                "inline": False,
            })

        payload = json.dumps({
            "embeds": [embed],
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "AmericanProspector/0.3.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status in (200, 204)
    except Exception:
        return False


def open_bug_report_ui(engine: "Engine", console, ctx) -> Optional[str]:
    """Full-screen bug report text input. Returns status message or None."""
    import tcod.event
    from src.menus import draw_box
    WHITE = (255, 255, 255)
    GREY = (140, 140, 140)
    YELLOW = (255, 255, 0)
    RED = (255, 80, 80)
    BG = (15, 15, 30)

    W, H = 60, 16
    X = (console.width - W) // 2
    Y = (console.height - H) // 2
    K = tcod.event.KeySym

    typed = ""
    cursor_blink = 0

    while True:
        draw_box(console, X, Y, W, H, "REPORT A BUG")
        console.print(X + 2, Y + 2,
                      "Describe the bug you found:", fg=YELLOW, bg=BG)
        console.print(X + 2, Y + 3,
                      "(What happened? What did you expect?)", fg=GREY, bg=BG)

        # Text display area (multi-line)
        max_w = W - 6
        display_lines = []
        line = ""
        for ch in typed:
            if ch == "\n":
                display_lines.append(line)
                line = ""
            elif len(line) >= max_w:
                display_lines.append(line)
                line = ch
            else:
                line += ch
        display_lines.append(line)

        for i, dline in enumerate(display_lines[-6:]):
            row = Y + 5 + i
            if row < Y + H - 4:
                cursor = "_" if i == len(display_lines[-6:]) - 1 else ""
                console.print(X + 3, row, (dline + cursor)[:max_w],
                              fg=WHITE, bg=(20, 20, 40))

        # Character count
        console.print(X + 2, Y + H - 3,
                      f"{len(typed)}/500 characters", fg=GREY, bg=BG)
        console.print(X + 2, Y + H - 2,
                      "Enter = Submit   Esc = Cancel", fg=GREY, bg=BG)

        ctx.present(console)

        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return None
            if isinstance(event, tcod.event.TextInput):
                if len(typed) < 500:
                    typed += event.text
                continue
            if isinstance(event, tcod.event.KeyDown):
                if event.sym == K.ESCAPE:
                    return None
                elif event.sym == K.BACKSPACE:
                    typed = typed[:-1]
                elif event.sym in (K.RETURN, K.KP_ENTER):
                    if typed.strip():
                        return save_bug_report(engine, typed.strip())
                    else:
                        return None
                break
