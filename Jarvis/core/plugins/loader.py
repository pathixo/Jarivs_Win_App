"""
Plugin Loader
=============

Safe dynamic loading of plugin modules with dependency checking.
"""

import os
import sys
import importlib
import importlib.util
from pathlib import Path
from typing import Optional, Type, Dict, Any, List, Tuple
import logging
import subprocess
import yaml

from .base import JarvisPlugin, PluginLoadError, PluginDependencyError, PluginMetadata

logger = logging.getLogger(__name__)


class PluginLoader:
    """
    Handles safe dynamic loading of plugin modules.
    
    Supports loading from:
    - Single .py files
    - Package directories with __init__.py
    - Installed packages (pip)
    """
    
    def __init__(self, plugins_dir: Optional[Path] = None):
        """
        Initialize the plugin loader.
        
        Args:
            plugins_dir: Directory containing plugins (default: Jarvis/plugins/)
        """
        if plugins_dir is None:
            # Default to Jarvis/plugins/ relative to this file
            plugins_dir = Path(__file__).parent.parent.parent / "plugins"
            
        self.plugins_dir = Path(plugins_dir)
        self._loaded_modules: Dict[str, Any] = {}
        
    def ensure_plugins_dir(self) -> None:
        """Create plugins directory if it doesn't exist."""
        if not self.plugins_dir.exists():
            self.plugins_dir.mkdir(parents=True)
            logger.info(f"Created plugins directory: {self.plugins_dir}")
            
            # Create a README
            readme = self.plugins_dir / "README.md"
            readme.write_text("""# Jarvis Plugins

Place your plugins here. Each plugin should be either:
- A single Python file (e.g., `my_plugin.py`)
- A directory with `__init__.py` (e.g., `my_plugin/__init__.py`)

## Plugin Structure

```python
from Jarvis.core.plugins import JarvisPlugin

class MyPlugin(JarvisPlugin):
    name = "my_plugin"
    version = "1.0.0"
    description = "My awesome plugin"
    
    def on_load(self):
        print("Plugin loaded!")
        
    def on_unload(self):
        print("Plugin unloaded!")
```

## Plugin Configuration

Create a `plugin.yaml` in your plugin directory:

```yaml
name: my_plugin
version: 1.0.0
description: My awesome plugin
author: Your Name
dependencies:
  - requests>=2.28.0
config:
  some_option: default_value
```
""")
            
    def discover(self) -> List[Tuple[str, Path]]:
        """
        Discover available plugins in the plugins directory.
        
        Returns:
            List of (plugin_name, plugin_path) tuples
        """
        self.ensure_plugins_dir()
        plugins = []
        
        for item in self.plugins_dir.iterdir():
            if item.name.startswith('_') or item.name.startswith('.'):
                continue
                
            if item.is_file() and item.suffix == '.py':
                # Single file plugin
                plugin_name = item.stem
                plugins.append((plugin_name, item))
                logger.debug(f"Discovered plugin file: {plugin_name}")
                
            elif item.is_dir():
                # Package plugin
                init_file = item / "__init__.py"
                if init_file.exists():
                    plugin_name = item.name
                    plugins.append((plugin_name, item))
                    logger.debug(f"Discovered plugin package: {plugin_name}")
                    
        return plugins
        
    def load_plugin_config(self, plugin_path: Path) -> Dict[str, Any]:
        """
        Load plugin configuration from plugin.yaml.
        
        Args:
            plugin_path: Path to plugin file or directory
            
        Returns:
            Configuration dictionary
        """
        if plugin_path.is_file():
            config_path = plugin_path.parent / f"{plugin_path.stem}.yaml"
        else:
            config_path = plugin_path / "plugin.yaml"
            
        if config_path.exists():
            try:
                with open(config_path) as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Failed to load plugin config: {config_path}: {e}")
                
        return {}
        
    def check_dependencies(self, dependencies: List[str]) -> Tuple[bool, List[str]]:
        """
        Check if plugin dependencies are satisfied.
        
        Args:
            dependencies: List of pip package requirements
            
        Returns:
            (all_satisfied, missing_packages) tuple
        """
        missing = []
        
        for dep in dependencies:
            # Parse package name from requirement string
            package_name = dep.split('>=')[0].split('==')[0].split('<')[0].strip()
            
            try:
                importlib.import_module(package_name.replace('-', '_'))
            except ImportError:
                missing.append(dep)
                
        return len(missing) == 0, missing
        
    def install_dependencies(self, dependencies: List[str]) -> bool:
        """
        Install missing plugin dependencies.
        
        Args:
            dependencies: List of pip package requirements
            
        Returns:
            True if all dependencies installed successfully
        """
        if not dependencies:
            return True
            
        logger.info(f"Installing plugin dependencies: {dependencies}")
        
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install"] + dependencies,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                logger.error(f"Dependency installation failed: {result.stderr}")
                return False
                
            logger.info("Dependencies installed successfully")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("Dependency installation timed out")
            return False
        except Exception as e:
            logger.error(f"Dependency installation error: {e}")
            return False
            
    def load_module(self, plugin_name: str, plugin_path: Path) -> Any:
        """
        Load a plugin module from path.
        
        Args:
            plugin_name: Name for the module
            plugin_path: Path to .py file or package directory
            
        Returns:
            Loaded module object
        """
        if plugin_name in self._loaded_modules:
            return self._loaded_modules[plugin_name]
            
        try:
            if plugin_path.is_file():
                # Load single file plugin
                spec = importlib.util.spec_from_file_location(
                    f"jarvis_plugins.{plugin_name}",
                    plugin_path
                )
                if spec is None or spec.loader is None:
                    raise PluginLoadError(f"Failed to create module spec for {plugin_path}")
                    
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
                
            else:
                # Load package plugin
                if str(plugin_path.parent) not in sys.path:
                    sys.path.insert(0, str(plugin_path.parent))
                    
                module = importlib.import_module(plugin_name)
                
            self._loaded_modules[plugin_name] = module
            logger.debug(f"Loaded module: {plugin_name}")
            return module
            
        except Exception as e:
            raise PluginLoadError(f"Failed to load plugin module '{plugin_name}': {e}")
            
    def find_plugin_class(self, module: Any) -> Optional[Type[JarvisPlugin]]:
        """
        Find the JarvisPlugin subclass in a module.
        
        Args:
            module: Loaded module to search
            
        Returns:
            Plugin class or None if not found
        """
        for name in dir(module):
            obj = getattr(module, name)
            
            if (isinstance(obj, type) and 
                issubclass(obj, JarvisPlugin) and 
                obj is not JarvisPlugin):
                return obj
                
        return None
        
    def load(
        self,
        plugin_name: str,
        plugin_path: Path,
        auto_install_deps: bool = False
    ) -> JarvisPlugin:
        """
        Load and instantiate a plugin.
        
        Args:
            plugin_name: Name of the plugin
            plugin_path: Path to plugin file or directory
            auto_install_deps: If True, automatically install missing dependencies
            
        Returns:
            Instantiated plugin object
            
        Raises:
            PluginLoadError: If plugin fails to load
            PluginDependencyError: If dependencies are not satisfied
        """
        logger.info(f"Loading plugin: {plugin_name} from {plugin_path}")
        
        # Load configuration
        config = self.load_plugin_config(plugin_path)
        
        # Check dependencies
        dependencies = config.get('dependencies', [])
        satisfied, missing = self.check_dependencies(dependencies)
        
        if not satisfied:
            if auto_install_deps:
                if not self.install_dependencies(missing):
                    raise PluginDependencyError(
                        f"Failed to install dependencies for '{plugin_name}': {missing}"
                    )
            else:
                raise PluginDependencyError(
                    f"Plugin '{plugin_name}' has missing dependencies: {missing}"
                )
                
        # Load the module
        module = self.load_module(plugin_name, plugin_path)
        
        # Find plugin class
        plugin_class = self.find_plugin_class(module)
        
        if plugin_class is None:
            raise PluginLoadError(
                f"No JarvisPlugin subclass found in '{plugin_name}'"
            )
            
        # Instantiate plugin
        try:
            plugin = plugin_class()
            
            # Apply configuration
            plugin_config = config.get('config', {})
            if plugin_config:
                plugin.configure(plugin_config)
                
            return plugin
            
        except Exception as e:
            raise PluginLoadError(
                f"Failed to instantiate plugin '{plugin_name}': {e}"
            )
            
    def unload(self, plugin_name: str) -> bool:
        """
        Unload a plugin module.
        
        Args:
            plugin_name: Name of the plugin to unload
            
        Returns:
            True if unloaded successfully
        """
        if plugin_name not in self._loaded_modules:
            return False
            
        # Remove from sys.modules
        module_name = f"jarvis_plugins.{plugin_name}"
        if module_name in sys.modules:
            del sys.modules[module_name]
            
        if plugin_name in sys.modules:
            del sys.modules[plugin_name]
            
        # Remove from our cache
        del self._loaded_modules[plugin_name]
        
        logger.debug(f"Unloaded module: {plugin_name}")
        return True
        
    def reload(self, plugin_name: str, plugin_path: Path) -> JarvisPlugin:
        """
        Reload a plugin (unload then load).
        
        Args:
            plugin_name: Name of the plugin
            plugin_path: Path to plugin file or directory
            
        Returns:
            Newly instantiated plugin object
        """
        self.unload(plugin_name)
        return self.load(plugin_name, plugin_path)
