"""
Preferences Module — User Preferences Manager for Jarvis
==========================================================
Key-value preference store backed by SQLite, organized by category.
Provides in-memory caching, default values, and a Qt signal for
live-updating components when preferences change.

Categories:
  tts      — voice, engine, speed, pitch, volume
  ui       — theme, window_opacity, always_on_top, start_minimized
  llm      — default_provider, temperature, response_style, max_tokens
  persona  — default_persona, greeting_enabled
  privacy  — auto_memory_enabled, memory_confidence_threshold, save_history
  system   — startup_with_windows, notification_sounds, wake_word_sensitivity

Usage:
    from Jarvis.core.preferences import get_preferences
    prefs = get_preferences()
    voice = prefs.get("tts", "voice", "en-GB-SoniaNeural")
    prefs.set("tts", "voice", "en-US-GuyNeural")
"""

import json
import logging
import time
import threading
from typing import Any, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from Jarvis.core.database import get_database

logger = logging.getLogger("jarvis.preferences")

# ─────────────────────────── Defaults ───────────────────────────────────────

PREFERENCE_DEFAULTS: dict[str, dict[str, Any]] = {
    "tts": {
        "voice": "en-GB-SoniaNeural",
        "engine": "auto",
        "speed": 1.0,
        "pitch": 0,
        "volume": 100,
    },
    "ui": {
        "theme": "dark",
        "window_opacity": 1.0,
        "always_on_top": False,
        "start_minimized": False,
    },
    "llm": {
        "default_provider": "gemini",
        "temperature": 0.7,
        "response_style": "concise",
        "max_tokens": 512,
    },
    "persona": {
        "default_persona": "jarvis",
        "greeting_enabled": True,
    },
    "privacy": {
        "auto_memory_enabled": True,
        "memory_confidence_threshold": 0.7,
        "save_history": True,
    },
    "system": {
        "startup_with_windows": False,
        "notification_sounds": True,
        "wake_word_sensitivity": 0.5,
    },
}

# ─────────────────────────── Singleton ──────────────────────────────────────

_instance: Optional["PreferencesManager"] = None
_instance_lock = threading.Lock()


def get_preferences() -> "PreferencesManager":
    """Return the global PreferencesManager singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = PreferencesManager()
    return _instance


# ─────────────────────────── PreferencesManager ─────────────────────────────

class PreferencesManager(QObject):
    """
    Cached key-value preference store.

    Reads defaults from PREFERENCE_DEFAULTS, overrides from SQLite.
    Emits `preference_changed(category, key, value)` on every write
    so UI components can live-update.
    """

    # Signal: (category: str, key: str, json_value: str)
    preference_changed = pyqtSignal(str, str, str)

    def __init__(self, user_id: str | None = None):
        super().__init__()
        self._db = get_database()
        self._user_id = user_id  # resolved lazily
        self._cache: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._loaded = False

    # ── Lazy user resolution ─────────────────────────────────────────────

    def _ensure_user(self) -> str:
        if not self._user_id:
            from Jarvis.core.user_profile import get_profile_manager
            pm = get_profile_manager()
            self._user_id = pm.current_user_id
        return self._user_id

    # ── Cache Loading ────────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        """Load all preferences from DB into cache (once)."""
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return

            uid = self._ensure_user()

            # Start with defaults
            for cat, keys in PREFERENCE_DEFAULTS.items():
                self._cache[cat] = dict(keys)

            # Overlay DB values
            rows = self._db.fetch_all(
                "SELECT category, key, value FROM preferences WHERE user_id = ?",
                (uid,),
            )
            for row in rows:
                cat = row["category"]
                key = row["key"]
                raw = row["value"]
                if cat not in self._cache:
                    self._cache[cat] = {}
                self._cache[cat][key] = self._deserialize(raw)

            self._loaded = True
            logger.info("Loaded %d preference overrides for user %s", len(rows), uid)

    # ── Public API ───────────────────────────────────────────────────────

    def get(self, category: str, key: str, default: Any = None) -> Any:
        """
        Get a preference value.
        Falls back to PREFERENCE_DEFAULTS, then to the provided default.
        """
        self._ensure_loaded()
        cat_dict = self._cache.get(category, {})
        if key in cat_dict:
            return cat_dict[key]
        # Check defaults
        defaults = PREFERENCE_DEFAULTS.get(category, {})
        return defaults.get(key, default)

    def set(self, category: str, key: str, value: Any) -> None:
        """
        Set a preference value (upsert to DB + update cache + emit signal).
        """
        self._ensure_loaded()
        uid = self._ensure_user()
        serialized = self._serialize(value)

        with self._lock:
            if category not in self._cache:
                self._cache[category] = {}
            self._cache[category][key] = value

        now = time.time()
        self._db.execute(
            "INSERT INTO preferences (user_id, category, key, value, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, category, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (uid, category, key, serialized, now),
        )

        # Emit signal for live UI updates
        try:
            self.preference_changed.emit(category, key, serialized)
        except RuntimeError:
            pass  # Qt object may not be in an event loop yet

        logger.debug("Preference set: %s.%s = %s", category, key, value)

    def get_all(self, category: str) -> dict[str, Any]:
        """Return all preferences in a category as a dict."""
        self._ensure_loaded()
        return dict(self._cache.get(category, PREFERENCE_DEFAULTS.get(category, {})))

    def get_all_categories(self) -> dict[str, dict[str, Any]]:
        """Return all preferences across all categories."""
        self._ensure_loaded()
        return {cat: dict(vals) for cat, vals in self._cache.items()}

    def reset_category(self, category: str) -> None:
        """Reset a category to defaults."""
        uid = self._ensure_user()
        self._db.execute(
            "DELETE FROM preferences WHERE user_id = ? AND category = ?",
            (uid, category),
        )
        with self._lock:
            if category in PREFERENCE_DEFAULTS:
                self._cache[category] = dict(PREFERENCE_DEFAULTS[category])
            elif category in self._cache:
                del self._cache[category]

        logger.info("Reset preferences category: %s", category)

    def reset_all(self) -> None:
        """Reset all preferences to defaults."""
        uid = self._ensure_user()
        self._db.execute(
            "DELETE FROM preferences WHERE user_id = ?", (uid,)
        )
        with self._lock:
            self._cache.clear()
            for cat, keys in PREFERENCE_DEFAULTS.items():
                self._cache[cat] = dict(keys)
        logger.info("Reset all preferences to defaults")

    # ── Serialization ────────────────────────────────────────────────────

    @staticmethod
    def _serialize(value: Any) -> str:
        """Serialize a Python value to a JSON string for storage."""
        return json.dumps(value)

    @staticmethod
    def _deserialize(raw: str) -> Any:
        """Deserialize a JSON string back to a Python value."""
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    # ── Convenience typed getters ────────────────────────────────────────

    def get_bool(self, category: str, key: str, default: bool = False) -> bool:
        val = self.get(category, key, default)
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes")
        return bool(val)

    def get_float(self, category: str, key: str, default: float = 0.0) -> float:
        val = self.get(category, key, default)
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    def get_int(self, category: str, key: str, default: int = 0) -> int:
        val = self.get(category, key, default)
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    def get_str(self, category: str, key: str, default: str = "") -> str:
        val = self.get(category, key, default)
        return str(val) if val is not None else default
