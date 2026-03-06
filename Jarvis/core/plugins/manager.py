"""
Plugin Manager
==============

High-level plugin management interface for the Jarvis application.
"""

from typing import Dict, List, Optional, Any, TYPE_CHECKING
from pathlib import Path
import logging
import threading

from .base import JarvisPlugin, PluginState, PluginError
from .registry import PluginRegistry
from .hooks import HookManager, HookType, get_hook_manager, set_hook_manager

if TYPE_CHECKING:
    from Jarvis.core.agent import ToolRegistry
    from Jarvis.core.system.action_router import ActionRouter

logger = logging.getLogger(__name__)


class PluginManager:
    """
    High-level plugin management interface.
    
    Provides a simplified API for plugin operations and integrates
    with the Jarvis application lifecycle.
    
    Usage:
        # Initialize
        manager = PluginManager()
        
        # Discover and load all plugins
        manager.discover_plugins()
        manager.load_all()
        
        # Register with tool system
        manager.register_with_tools(tool_registry, action_router)
        
        # Emit hooks during operation
        manager.emit_hook(HookType.PRE_ACTION, data={...})
        
        # Shutdown
        manager.shutdown()
    """
    
    _instance: Optional['PluginManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern to ensure only one plugin manager exists."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
            
    def __init__(
        self,
        plugins_dir: Optional[Path] = None,
        auto_load: bool = False
    ):
        """
        Initialize the plugin manager.
        
        Args:
            plugins_dir: Directory containing plugins
            auto_load: If True, automatically load plugins on init
        """
        if self._initialized:
            return
            
        self._hook_manager = HookManager()
        set_hook_manager(self._hook_manager)
        
        self._registry = PluginRegistry(
            plugins_dir=plugins_dir,
            hook_manager=self._hook_manager
        )
        
        self._tool_registry: Optional['ToolRegistry'] = None
        self._action_router: Optional['ActionRouter'] = None
        self._initialized = True
        
        logger.info(f"Plugin manager initialized (plugins_dir={self._registry.plugins_dir})")
        
        if auto_load:
            self.discover_plugins()
            self.load_all()
            
    @property
    def hooks(self) -> HookManager:
        """Get the hook manager."""
        return self._hook_manager
        
    @property
    def registry(self) -> PluginRegistry:
        """Get the plugin registry."""
        return self._registry
        
    @property
    def plugins_dir(self) -> Path:
        """Get the plugins directory path."""
        return self._registry.plugins_dir
        
    def discover_plugins(self) -> List[str]:
        """
        Discover available plugins.
        
        Returns:
            List of discovered plugin names
        """
        plugins = self._registry.discover()
        logger.info(f"Discovered {len(plugins)} plugins: {plugins}")
        return plugins
        
    def load(self, plugin_name: str, auto_install_deps: bool = False) -> JarvisPlugin:
        """
        Load a single plugin.
        
        Args:
            plugin_name: Name of the plugin to load
            auto_install_deps: Auto-install missing dependencies
            
        Returns:
            Loaded plugin instance
        """
        plugin = self._registry.load(plugin_name, auto_install_deps)
        
        # Register tools if tool registry is available
        if self._tool_registry:
            try:
                plugin.register_tools(self._tool_registry)
            except Exception as e:
                logger.error(f"Failed to register tools for {plugin_name}: {e}")
                
        # Register actions if action router is available
        if self._action_router:
            try:
                plugin.register_actions(self._action_router)
            except Exception as e:
                logger.error(f"Failed to register actions for {plugin_name}: {e}")
                
        return plugin
        
    def unload(self, plugin_name: str) -> bool:
        """
        Unload a plugin.
        
        Args:
            plugin_name: Name of the plugin to unload
            
        Returns:
            True if unloaded successfully
        """
        return self._registry.unload(plugin_name)
        
    def reload(self, plugin_name: str) -> JarvisPlugin:
        """
        Reload a plugin.
        
        Args:
            plugin_name: Name of the plugin to reload
            
        Returns:
            Reloaded plugin instance
        """
        plugin = self._registry.reload(plugin_name)
        
        # Re-register tools and actions
        if self._tool_registry:
            plugin.register_tools(self._tool_registry)
        if self._action_router:
            plugin.register_actions(self._action_router)
            
        return plugin
        
    def load_all(self, auto_install_deps: bool = False) -> Dict[str, bool]:
        """
        Load all discovered plugins.
        
        Args:
            auto_install_deps: Auto-install missing dependencies
            
        Returns:
            Dictionary of plugin_name -> success
        """
        results = self._registry.load_all(auto_install_deps)
        
        loaded = sum(1 for success in results.values() if success)
        failed = sum(1 for success in results.values() if not success)
        
        logger.info(f"Loaded {loaded} plugins ({failed} failed)")
        
        return results
        
    def enable(self, plugin_name: str) -> bool:
        """Enable a plugin."""
        return self._registry.enable(plugin_name)
        
    def disable(self, plugin_name: str) -> bool:
        """Disable a plugin."""
        return self._registry.disable(plugin_name)
        
    def get_plugin(self, plugin_name: str) -> Optional[JarvisPlugin]:
        """Get a loaded plugin by name."""
        return self._registry.get(plugin_name)
        
    def get_all_plugins(self) -> List[JarvisPlugin]:
        """Get all loaded plugins."""
        return self._registry.get_all()
        
    def get_enabled_plugins(self) -> List[JarvisPlugin]:
        """Get all enabled plugins."""
        return self._registry.get_enabled()
        
    def is_loaded(self, plugin_name: str) -> bool:
        """Check if a plugin is loaded."""
        return self._registry.is_loaded(plugin_name)
        
    def is_enabled(self, plugin_name: str) -> bool:
        """Check if a plugin is enabled."""
        return self._registry.is_enabled(plugin_name)
        
    def register_with_tools(
        self,
        tool_registry: 'ToolRegistry',
        action_router: Optional['ActionRouter'] = None
    ) -> None:
        """
        Register all enabled plugins with the tool system.
        
        Args:
            tool_registry: The ToolRegistry to register tools with
            action_router: The ActionRouter to register actions with
        """
        self._tool_registry = tool_registry
        self._action_router = action_router
        
        self._registry.register_tool_provider(tool_registry, action_router)
        
        logger.info("Registered plugins with tool system")
        
    def emit_hook(
        self,
        hook_type: HookType,
        source: str = "core",
        data: Optional[Dict[str, Any]] = None,
        sync: bool = True
    ) -> Any:
        """
        Emit a hook event.
        
        Args:
            hook_type: Type of hook to emit
            source: Source of the event
            data: Event data
            sync: Wait for handlers to complete
            
        Returns:
            HookContext with any modifications
        """
        return self._hook_manager.emit(hook_type, source, data, sync)
        
    async def emit_hook_async(
        self,
        hook_type: HookType,
        source: str = "core",
        data: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Emit a hook event asynchronously.
        
        Args:
            hook_type: Type of hook to emit
            source: Source of the event
            data: Event data
            
        Returns:
            HookContext with any modifications
        """
        return await self._hook_manager.emit_async(hook_type, source, data)
        
    def get_status(self) -> Dict[str, Any]:
        """
        Get comprehensive plugin system status.
        
        Returns:
            Status dictionary
        """
        return {
            "registry": self._registry.get_status(),
            "hooks": self._hook_manager.get_stats(),
            "tool_registry_connected": self._tool_registry is not None,
            "action_router_connected": self._action_router is not None,
        }
        
    def shutdown(self) -> None:
        """
        Shutdown the plugin system.
        
        Unloads all plugins and cleans up resources.
        """
        logger.info("Shutting down plugin system...")
        
        # Emit shutdown hook
        self._hook_manager.emit(HookType.ON_SHUTDOWN, source="plugin_manager")
        
        # Unload all plugins
        self._registry.unload_all()
        
        # Shutdown hook manager
        self._hook_manager.shutdown()
        
        logger.info("Plugin system shutdown complete")
        
    @classmethod
    def get_instance(cls) -> Optional['PluginManager']:
        """Get the singleton instance if it exists."""
        return cls._instance
        
    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (for testing)."""
        with cls._lock:
            if cls._instance:
                cls._instance.shutdown()
            cls._instance = None


# Convenience function for getting the global plugin manager
def get_plugin_manager() -> PluginManager:
    """Get the global plugin manager instance."""
    return PluginManager()
