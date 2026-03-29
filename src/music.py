"""
src/music.py

Background music system for American Prospector.
Uses pygame.mixer for MP3 playback.

Features:
    - Shuffle playback of all tracks
    - Main menu plays a fixed theme song
    - Category-aware: night, combat, work, tense tracks can be
      selected by context (future feature — currently all shuffle)
    - Volume control (0.0-1.0), saved to config.json
    - Tracks auto-advance when one finishes

Usage:
    from src.music import MusicManager
    music = MusicManager("music/")
    music.play_menu_theme()       # fixed song for main menu
    music.play_shuffle()          # random gameplay music
    music.set_volume(0.5)
    music.stop()
"""

import os
import random
import json
from typing import List, Optional, Dict


MUSIC_DIR = "music"
CONFIG_PATH = "config.json"

# Track categories — matched by filename prefix/keyword
CATEGORIES: Dict[str, List[str]] = {
    "theme":   [],    # main menu / title screen
    "night":   [],    # nighttime ambient
    "combat":  [],    # tense combat music (mapped from "tense")
    "work":    [],    # working / panning / mining
    "general": [],    # everything else
}

# Map filename keywords to categories
_KEYWORD_MAP = {
    "theme":     "theme",
    "night":     "night",
    "tense":     "combat",
    "combat":    "combat",
    "work":      "work",
    "hardwork":  "work",
    "panning":   "work",
}


class MusicManager:
    """
    Manages background music playback.
    Requires pygame.mixer — gracefully does nothing if unavailable.
    """

    def __init__(self, music_dir: str = MUSIC_DIR):
        self.music_dir = music_dir
        self.volume = 0.5
        self.enabled = True
        self.current_track: str = ""
        self._initialized = False
        self._tracks: List[str] = []
        self._shuffle_queue: List[str] = []
        self._category_tracks: Dict[str, List[str]] = {k: [] for k in CATEGORIES}
        self._menu_theme: str = ""

        self._load_config()
        self._scan_tracks()
        self._init_mixer()

    def _init_mixer(self) -> None:
        """Initialize pygame.mixer. Silent failure if not available."""
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
        """Scan music directory and categorize tracks."""
        if not os.path.isdir(self.music_dir):
            return

        for fname in os.listdir(self.music_dir):
            if not fname.lower().endswith((".mp3", ".ogg", ".wav")):
                continue
            path = os.path.join(self.music_dir, fname)
            self._tracks.append(path)

            # Categorize by filename keywords
            name_lower = fname.lower()
            categorized = False
            for keyword, cat in _KEYWORD_MAP.items():
                if keyword in name_lower:
                    self._category_tracks[cat].append(path)
                    categorized = True
                    break
            if not categorized:
                self._category_tracks["general"].append(path)

        # Pick a menu theme (first "theme" track, or first track)
        themes = self._category_tracks.get("theme", [])
        if themes:
            self._menu_theme = themes[0]
        elif self._tracks:
            self._menu_theme = self._tracks[0]

    def _load_config(self) -> None:
        """Load volume setting from config.json."""
        try:
            with open(CONFIG_PATH, "r") as f:
                cfg = json.load(f)
            self.volume = float(cfg.get("music_volume", 0.5))
            self.enabled = bool(cfg.get("music_enabled", True))
        except Exception:
            pass

    def _save_config(self) -> None:
        """Save volume setting to config.json."""
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

    # ── Playback control ───────────────────────────────────────────────

    def play_menu_theme(self) -> None:
        """Play the fixed main menu theme song."""
        if not self._initialized or not self.enabled or not self._menu_theme:
            return
        self._play_track(self._menu_theme, loops=-1)  # loop forever

    def play_shuffle(self) -> None:
        """Start shuffled playback of all non-theme tracks."""
        if not self._initialized or not self.enabled:
            return
        # Build shuffle queue from non-theme tracks
        pool = [t for t in self._tracks
                if t not in self._category_tracks.get("theme", [])]
        if not pool:
            pool = list(self._tracks)
        if not pool:
            return
        random.shuffle(pool)
        self._shuffle_queue = pool
        self._play_next()

    def play_category(self, category: str) -> None:
        """Play a random track from a specific category (future use)."""
        if not self._initialized or not self.enabled:
            return
        tracks = self._category_tracks.get(category, [])
        if not tracks:
            tracks = self._category_tracks.get("general", self._tracks)
        if tracks:
            self._play_track(random.choice(tracks))

    def _play_track(self, path: str, loops: int = 0) -> None:
        """Play a specific track file."""
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
        """Play the next track in the shuffle queue."""
        if not self._shuffle_queue:
            # Reshuffle
            pool = [t for t in self._tracks
                    if t not in self._category_tracks.get("theme", [])]
            if not pool:
                return
            random.shuffle(pool)
            self._shuffle_queue = pool
        track = self._shuffle_queue.pop(0)
        self._play_track(track)

    def check_advance(self) -> None:
        """
        Check if the current track has finished playing.
        Does NOT touch the event queue — pygame.event.get() would
        steal events from tcod's SDL event loop.
        Instead, just check if music is still playing.
        """
        if not self._initialized or not self.enabled:
            return
        try:
            import pygame
            if not pygame.mixer.music.get_busy() and self._shuffle_queue:
                self._play_next()
        except Exception:
            pass

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

    # ── Volume ─────────────────────────────────────────────────────────

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

    def toggle_mute(self) -> bool:
        self.enabled = not self.enabled
        if self.enabled:
            self.play_shuffle()
        else:
            self.stop()
        self._save_config()
        return self.enabled

    # ── Status ─────────────────────────────────────────────────────────

    def is_playing(self) -> bool:
        if not self._initialized:
            return False
        try:
            import pygame
            return pygame.mixer.music.get_busy()
        except Exception:
            return False

    def track_count(self) -> int:
        return len(self._tracks)

    def status_line(self) -> str:
        """One-line status for UI display."""
        if not self.enabled:
            return "Music: OFF"
        if not self._initialized:
            return "Music: unavailable"
        vol_pct = int(self.volume * 100)
        if self.current_track:
            name = os.path.splitext(self.current_track)[0]
            return f"Music: {name} ({vol_pct}%)"
        return f"Music: idle ({vol_pct}%)"
