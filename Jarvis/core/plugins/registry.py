"""
Plugin Registry — Discovery, loading, and hot-reload for Jarvis plugins.
==========================================================================
Scans a configurable directory for Python modules that export a `JarvisPlugin`
subclass. Supports:
  - Startup discovery
  - Hot-reload (re-import changed modules without restarting the app)
  - Plugin isolation (crash in a plugin doesn't kill the core)
"""

import importlib
import importlib.util
import logging
import os
import sys
import time
import threading
from pathlib import Path
from typing import Optional

from Jarvis.core.plugins.base import JarvisPlugin, PluginState, PluginMeta

logger = logging.getLogger("jarvis.plugins.registry")


class PluginRegistry:
    """
    Central plugin manager.

    Usage:
        registry = PluginRegistry(plugins_dir="path/to/plugins")
        registry.discover()           # scan & load all plugins
        registry.enable_all()         # activate all loaded plugins
        registry.hot_reload()         # re-import changed files
        registry.get("my_plugin")     # get a specific plugin instance
    """

    def __init__(self, plugins_dir: Optional[str] = None):
        if plugins_dir is None:
            plugins_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "..", "plugins"
            )
        self._dir = os.path.abspath(plugins_dir)
        self._plugins: dict[str, JarvisPlugin] = {}
        self._module_mtimes: dict[str, float] = {}  # path → last mtime
        self._lock = threading.Lock()

    @property
    def plugins(self) -> dict[str, JarvisPlugin]:
        return dict(self._plugins)

    @property
    def enabled_plugins(self) -> list[JarvisPlugin]:
        return [p for p in self._plugins.values() if p.state == PluginState.ENABLED]

    # ── Discovery ────────────────────────────────────────────────────────

    def discover(self) -> list[str]:
        """
        Scan the plugins directory for .py files exporting a JarvisPlugin subclass.
        Returns the list of newly discovered plugin names.
        """
        if not os.path.isdir(self._dir):
            os.makedirs(self._dir, exist_ok=True)
            logger.info("Created plugins directory: %s", self._dir)
            return []

        discovered: list[str] = []

        for filename in os.listdir(self._dir):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            filepath = os.path.join(self._dir, filename)
            module_name = f"jarvis_plugin_{filename[:-3]}"

            try:
                plugin_cls = self._load_plugin_class(filepath, module_name)
                if plugin_cls is None:
                    continue

                # Instantiate and load
                instance = plugin_cls()
                instance._do_load()

                with self._lock:
                    self._plugins[instance.name] = instance
                    self._module_mtimes[filepath] = os.path.getmtime(filepath)

                discovered.append(instance.name)

            except Exception as e:
                logger.error("Failed to discover plugin from %s: %s", filename, e)

        if discovered:
            logger.info("Discovered %d plugin(s): %s", len(discovered), ", ".join(discovered))
        return discovered

    def _load_plugin_class(self, filepath: str, module_name: str) -> Optional[type]:
        """
        Import a Python file and search for a JarvisPlugin subclass.
        Returns the class, or None if not found.
        """
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)

        # Isolate: catch import-time errors
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error("Import error in %s: %s", filepath, e)
            return None

        # Find the first JarvisPlugin subclass
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, JarvisPlugin)
                and attr is not JarvisPlugin
                and hasattr(attr, "META")
            ):
                return attr

        return None

    # ── Hot Reload ───────────────────────────────────────────────────────

    def hot_reload(self) -> list[str]:
        """
        Re-import any plugin files that have changed on disk.
        Returns names of reloaded plugins.
        """
        reloaded: list[str] = []

        if not os.path.isdir(self._dir):
            return reloaded

        for filename in os.listdir(self._dir):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            filepath = os.path.join(self._dir, filename)
            current_mtime = os.path.getmtime(filepath)
            previous_mtime = self._module_mtimes.get(filepath, 0)

            if current_mtime <= previous_mtime:
                continue

            module_name = f"jarvis_plugin_{filename[:-3]}"
            logger.info("Hot-reloading plugin: %s", filename)

            try:
                # Unload old instance if it exists
                plugin_cls = self._load_plugin_class(filepath, module_name)
                if plugin_cls is None:
                    continue

                new_instance = plugin_cls()

                with self._lock:
                    # Unload old version
                    old = self._find_by_filepath(filepath)
                    if old:
                        old._do_disable()
                        old._do_unload()
                        del self._plugins[old.name]

                    # Load new version
                    new_instance._do_load()
                    new_instance._do_enable()
                    self._plugins[new_instance.name] = new_instance
                    self._module_mtimes[filepath] = current_mtime

                reloaded.append(new_instance.name)

            except Exception as e:
                logger.error("Hot-reload failed for %s: %s", filename, e)

        return reloaded

    def _find_by_filepath(self, filepath: str) -> Optional[JarvisPlugin]:
        """Find a loaded plugin that came from this filepath."""
        # Simple lookup by checking module name
        for plugin in self._plugins.values():
            if hasattr(plugin, "__module__") and filepath in str(
                getattr(sys.modules.get(plugin.__module__, None), "__file__", "")
            ):
                return plugin
        return None

    # ── Lifecycle ────────────────────────────────────────────────────────

    def enable_all(self) -> None:
        """Enable all loaded plugins."""
        for plugin in self._plugins.values():
            if plugin.state == PluginState.LOADED:
                plugin._do_enable()

    def disable_all(self) -> None:
        """Disable all enabled plugins."""
        for plugin in self._plugins.values():
            if plugin.state == PluginState.ENABLED:
                plugin._do_disable()

    def get(self, name: str) -> Optional[JarvisPlugin]:
        """Get a plugin by name."""
        return self._plugins.get(name)

    def enable(self, name: str) -> bool:
        """Enable a specific plugin by name."""
        p = self._plugins.get(name)
        if p and p.state in (PluginState.LOADED, PluginState.DISABLED):
            p._do_enable()
            return True
        return False

    def disable(self, name: str) -> bool:
        """Disable a specific plugin by name."""
        p = self._plugins.get(name)
        if p and p.state == PluginState.ENABLED:
            p._do_disable()
            return True
        return False

    def unload(self, name: str) -> bool:
        """Completely unload and remove a plugin."""
        p = self._plugins.get(name)
        if not p:
            return False
        p._do_disable()
        p._do_unload()
        with self._lock:
            del self._plugins[name]
        return True

    # ── Hook Dispatch ────────────────────────────────────────────────────

    def dispatch_command(self, command: str) -> Optional[str]:
        """
        Run `on_command` across all enabled plugins.
        First plugin to return a non-None string wins (short-circuit).
        """
        for plugin in self.enabled_plugins:
            try:
                result = plugin.on_command(command)
                if result is not None:
                    return result
            except Exception as e:
                logger.error("Plugin [%s] on_command error: %s", plugin.name, e)
                plugin._state = PluginState.ERROR
                plugin._error = str(e)
        return None

    def dispatch_response(self, command: str, response: str) -> str:
        """Run `on_response` across all enabled plugins (chained)."""
        for plugin in self.enabled_plugins:
            try:
                response = plugin.on_response(command, response)
            except Exception as e:
                logger.error("Plugin [%s] on_response error: %s", plugin.name, e)
        return response

    def dispatch_tts_before(self, text: str) -> str:
        """Run `on_tts_before` across all enabled plugins (chained)."""
        for plugin in self.enabled_plugins:
            try:
                text = plugin.on_tts_before(text)
            except Exception as e:
                logger.error("Plugin [%s] on_tts_before error: %s", plugin.name, e)
        return text

    def dispatch_stt_after(self, transcript: str) -> str:
        """Run `on_stt_after` across all enabled plugins (chained)."""
        for plugin in self.enabled_plugins:
            try:
                transcript = plugin.on_stt_after(transcript)
            except Exception as e:
                logger.error("Plugin [%s] on_stt_after error: %s", plugin.name, e)
        return transcript

    # ── Status ───────────────────────────────────────────────────────────

    def status_report(self) -> list[dict]:
        """Return a summary of all plugins and their states."""
        return [
            {
                "name": p.name,
                "version": p.META.version,
                "state": p.state.value,
                "error": p.last_error,
                "author": p.META.author,
                "description": p.META.description,
            }
            for p in self._plugins.values()
        ]


# ── Module-level singleton ──────────────────────────────────────────────

_registry: Optional[PluginRegistry] = None


def get_plugin_registry(plugins_dir: Optional[str] = None) -> PluginRegistry:
    """Return the global PluginRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = PluginRegistry(plugins_dir)
    return _registry
