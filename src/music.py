"""
Background music system. Folder-based categories, context-aware switching.

Folder structure:
  music/
    theme/      ← character creation, menus
    explore/    ← daytime walking (default)
    night/      ← nighttime
    work/       ← mining, panning, crafting
    combat/     ← combat mode
    tense/      ← hostile nearby, low health
    triumph/    ← gold find, big kill
    town/       ← in settlement

Tracks play to completion before switching. Category changes only happen
when a song ends, EXCEPT combat — combat interrupts immediately.
"""

import os
import random
import json
from typing import List, Dict, Optional


MUSIC_DIR = "music"
CONFIG_PATH = "config.json"

# Recognized category folder names
CATEGORY_NAMES = ["theme", "explore", "night", "work", "combat",
                  "tense", "triumph", "town"]


class MusicManager:
    def __init__(self, music_dir: str = MUSIC_DIR):
        self.music_dir = music_dir
        self.volume = 0.5
        self.enabled = True
        self.current_track: str = ""
        self.current_category: str = ""
        self.desired_category: str = "explore"  # what we WANT to play next
        self._initialized = False
        self._categories: Dict[str, List[str]] = {}
        self._queue: List[str] = []

        self._load_config()
        self._scan_tracks()
        self._init_mixer()

    def _init_mixer(self) -> None:
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2,
                                   buffer=4096)
            pygame.mixer.music.set_volume(self.volume)
            self._initialized = True
        except (ImportError, Exception):
            self._initialized = False

    def _scan_tracks(self) -> None:
        """Scan music directory for category subfolders and loose files."""
        if not os.path.isdir(self.music_dir):
            return

        # Scan subfolders
        for cat in CATEGORY_NAMES:
            cat_dir = os.path.join(self.music_dir, cat)
            if os.path.isdir(cat_dir):
                tracks = [os.path.join(cat_dir, f) for f in os.listdir(cat_dir)
                          if f.lower().endswith((".mp3", ".ogg", ".wav"))]
                self._categories[cat] = tracks

        # Loose files in root go to "explore" (or categorize by name)
        _KEYWORD_MAP = {
            "theme": "theme", "night": "night", "tense": "combat",
            "combat": "combat", "work": "work", "hardwork": "work",
            "panning": "work", "triumph": "triumph", "town": "town",
            "color": "triumph", "wilderness": "explore",
        }
        for fname in os.listdir(self.music_dir):
            fpath = os.path.join(self.music_dir, fname)
            if os.path.isdir(fpath):
                continue
            if not fname.lower().endswith((".mp3", ".ogg", ".wav")):
                continue
            # Categorize by keyword in filename
            cat = "explore"
            for keyword, mapped in _KEYWORD_MAP.items():
                if keyword in fname.lower():
                    cat = mapped
                    break
            self._categories.setdefault(cat, []).append(fpath)

    def _load_config(self) -> None:
        try:
            with open(CONFIG_PATH, "r") as f:
                cfg = json.load(f)
            self.volume = float(cfg.get("music_volume", 0.5))
            self.enabled = bool(cfg.get("music_enabled", True))
        except Exception:
            pass

    def _save_config(self) -> None:
        try:
            cfg = {}
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r") as f:
                    cfg = json.load(f)
            cfg["music_volume"] = self.volume
            cfg["music_enabled"] = self.enabled
            with open(CONFIG_PATH, "w") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

    # ── Category control ──────────────────────────────────────────────

    def set_category(self, category: str, immediate: bool = False) -> None:
        """Request a category change.
        immediate=True: interrupt current track (for combat).
        immediate=False: switch when current track ends (normal transitions)."""
        if category == self.desired_category and not immediate:
            return
        self.desired_category = category
        if immediate and category != self.current_category:
            self._switch_now(category)

    def _switch_now(self, category: str) -> None:
        """Immediately switch to a track from the given category."""
        tracks = self._categories.get(category, [])
        if not tracks:
            # Fall back to explore, then any available
            tracks = self._categories.get("explore", [])
        if not tracks:
            for cat_tracks in self._categories.values():
                if cat_tracks:
                    tracks = cat_tracks
                    break
        if not tracks:
            return
        self.current_category = category
        self._queue = list(tracks)
        random.shuffle(self._queue)
        self._play_next()

    # ── Playback ──────────────────────────────────────────────────────

    def play_shuffle(self) -> None:
        """Start playing. Uses desired_category or explore."""
        if not self._initialized or not self.enabled:
            return
        self._switch_now(self.desired_category or "explore")

    def play_category(self, category: str) -> None:
        """Play a random track from a specific category."""
        if not self._initialized or not self.enabled:
            return
        self._switch_now(category)

    def _play_track(self, path: str, loops: int = 0) -> None:
        if not self._initialized:
            return
        try:
            import pygame
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self.volume)
            pygame.mixer.music.play(loops=loops)
            self.current_track = os.path.basename(path)
        except Exception:
            pass

    def _play_next(self) -> None:
        """Play next track in queue. Reshuffle if empty."""
        if not self._queue:
            tracks = self._categories.get(self.current_category, [])
            if not tracks:
                return
            self._queue = list(tracks)
            random.shuffle(self._queue)
        if self._queue:
            self._play_track(self._queue.pop(0))

    def check_advance(self) -> None:
        """Called every frame. When track ends, play next from desired category."""
        if not self._initialized or not self.enabled:
            return
        try:
            import pygame
            if not pygame.mixer.music.get_busy():
                # Song ended — switch category if desired changed
                if self.desired_category != self.current_category:
                    self._switch_now(self.desired_category)
                else:
                    self._play_next()
        except Exception:
            pass

    # ── Standard controls ─────────────────────────────────────────────

    def stop(self) -> None:
        if not self._initialized:
            return
        try:
            import pygame
            pygame.mixer.music.stop()
            self.current_track = ""
        except Exception:
            pass

    def pause(self) -> None:
        if not self._initialized:
            return
        try:
            import pygame
            pygame.mixer.music.pause()
        except Exception:
            pass

    def unpause(self) -> None:
        if not self._initialized:
            return
        try:
            import pygame
            pygame.mixer.music.unpause()
        except Exception:
            pass

    def status_line(self) -> str:
        if not self.enabled:
            return "Music: OFF"
        if not self.current_track:
            return "Music: No track playing"
        return f"Now playing: {self.current_track}"

    def set_volume(self, vol: float) -> None:
        self.volume = max(0.0, min(1.0, vol))
        if self._initialized:
            try:
                import pygame
                pygame.mixer.music.set_volume(self.volume)
            except Exception:
                pass
        self._save_config()

    def volume_up(self, step: float = 0.1) -> float:
        self.set_volume(self.volume + step)
        return self.volume

    def volume_down(self, step: float = 0.1) -> float:
        self.set_volume(self.volume - step)
        return self.volume

    def is_playing(self) -> bool:
        try:
            import pygame
            return pygame.mixer.music.get_busy()
        except Exception:
            return False

    def track_count(self) -> int:
        return sum(len(t) for t in self._categories.values())

    def category_counts(self) -> Dict[str, int]:
        return {k: len(v) for k, v in self._categories.items() if v}
