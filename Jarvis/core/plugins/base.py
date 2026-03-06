"""
Plugin Base — Abstract interface for all Jarvis plugins.
=========================================================
Every plugin must subclass `JarvisPlugin` and implement the required hooks.
Plugins are discovered from the `plugins/` directory at startup and can be
hot-reloaded at runtime without restarting the main application.

Lifecycle:
    load()   → called once when the plugin is first discovered
    enable() → called each time the plugin is activated
    disable() → called each time the plugin is deactivated
    unload() → called when the plugin is removed from the registry
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("jarvis.plugins")


class PluginState(Enum):
    UNLOADED = "unloaded"
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


@dataclass
class PluginMeta:
    """Metadata descriptor for a plugin."""
    name: str
    version: str = "0.1.0"
    author: str = "Unknown"
    description: str = ""
    dependencies: list[str] = field(default_factory=list)
    min_jarvis_version: str = "2.0.0"
    tags: list[str] = field(default_factory=list)


class JarvisPlugin(ABC):
    """
    Base class for all Jarvis plugins.

    Subclasses MUST define a `META` class attribute of type PluginMeta,
    and implement `on_load()` at minimum.

    All plugin code runs in an isolated context — uncaught exceptions
    are caught by the registry and will move the plugin to ERROR state
    without killing the core application.
    """

    META: PluginMeta  # subclass must set this

    def __init__(self):
        self._state = PluginState.UNLOADED
        self._error: Optional[str] = None

    @property
    def state(self) -> PluginState:
        return self._state

    @property
    def name(self) -> str:
        return self.META.name

    @property
    def last_error(self) -> Optional[str]:
        return self._error

    # ── Lifecycle Hooks (override in subclass) ──────────────────────────

    @abstractmethod
    def on_load(self) -> None:
        """Called once when the plugin is first discovered and loaded.
        Use this for heavy initialization (model loading, file reads, etc.)."""
        ...

    def on_enable(self) -> None:
        """Called when the plugin is activated. Default: no-op."""
        pass

    def on_disable(self) -> None:
        """Called when the plugin is deactivated. Default: no-op."""
        pass

    def on_unload(self) -> None:
        """Called when the plugin is removed from the system. Clean up resources."""
        pass

    # ── Event Hooks (optional, override to subscribe) ───────────────────

    def on_command(self, command: str) -> Optional[str]:
        """
        Called before the orchestrator processes a command.
        Return a string to short-circuit (plugin handles it), or None to pass through.
        """
        return None

    def on_response(self, command: str, response: str) -> str:
        """
        Called after the orchestrator produces a response.
        Can modify the response text. Default: pass through unchanged.
        """
        return response

    def on_tts_before(self, text: str) -> str:
        """Hook to modify text before TTS synthesis. Default: pass through."""
        return text

    def on_stt_after(self, transcript: str) -> str:
        """Hook to modify STT transcript before processing. Default: pass through."""
        return transcript

    # ── Internal lifecycle (called by PluginRegistry) ───────────────────

    def _do_load(self) -> None:
        try:
            self.on_load()
            self._state = PluginState.LOADED
            self._error = None
            logger.info("Plugin loaded: %s v%s", self.name, self.META.version)
        except Exception as e:
            self._state = PluginState.ERROR
            self._error = str(e)
            logger.error("Plugin load failed [%s]: %s", self.name, e)

    def _do_enable(self) -> None:
        try:
            self.on_enable()
            self._state = PluginState.ENABLED
            self._error = None
        except Exception as e:
            self._state = PluginState.ERROR
            self._error = str(e)
            logger.error("Plugin enable failed [%s]: %s", self.name, e)

    def _do_disable(self) -> None:
        try:
            self.on_disable()
            self._state = PluginState.DISABLED
            self._error = None
        except Exception as e:
            self._state = PluginState.ERROR
            self._error = str(e)
            logger.error("Plugin disable failed [%s]: %s", self.name, e)

    def _do_unload(self) -> None:
        try:
            self.on_unload()
            self._state = PluginState.UNLOADED
        except Exception as e:
            logger.error("Plugin unload failed [%s]: %s", self.name, e)
        finally:
            self._state = PluginState.UNLOADED
