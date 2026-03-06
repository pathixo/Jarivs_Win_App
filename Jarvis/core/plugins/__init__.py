"""
Jarvis Plugin Ecosystem
=======================

A modular plugin system for extending Jarvis functionality without modifying core code.

Usage:
    from Jarvis.core.plugins import PluginRegistry, JarvisPlugin, PluginMeta
    
    # Initialize plugin registry
    registry = PluginRegistry()
    registry.discover()
    registry.enable_all()
"""

from .base import JarvisPlugin, PluginMeta, PluginState
from .registry import PluginRegistry
from .hooks import HookManager

__all__ = [
    'JarvisPlugin',
    'PluginMeta',
    'PluginState',
    'PluginRegistry',
    'HookManager',
]
