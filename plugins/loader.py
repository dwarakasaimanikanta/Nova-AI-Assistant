"""
plugins/loader.py
-----------------
Dynamic plugin loader scanning, importing, and instantiating subclasses of BasePlugin.
"""

import importlib
import inspect
import os
from pathlib import Path

from plugins.base import BasePlugin
from utils.logger import get_logger

logger = get_logger(__name__)


class PluginLoader:
    """Discovers and instantiates plugins dynamically from the plugins folder."""

    def __init__(self, plugins_dir: str | None = None) -> None:
        """
        Initialize the loader.

        Args:
            plugins_dir: Target path to scan. Defaults to the plugins/ sibling folder.
        """
        if plugins_dir is None:
            self.plugins_dir = Path(__file__).parent.resolve()
        else:
            self.plugins_dir = Path(plugins_dir).resolve()

    def discover_and_load_plugins(self) -> list[BasePlugin]:
        """
        Scan directory, import matching *_plugin.py modules, and instantiate BasePlugin subclasses.

        Returns:
            List of instantiated BasePlugin subclasses.
        """
        plugins = []
        if not self.plugins_dir.is_dir():
            logger.error("Plugins directory not found: %s", self.plugins_dir)
            return plugins

        logger.info("Scanning plugins directory: %s", self.plugins_dir)

        for filename in os.listdir(self.plugins_dir):
            if filename.endswith("_plugin.py"):
                module_name = filename[:-3]  # Strip .py extension
                try:
                    full_module_path = f"plugins.{module_name}"
                    module = importlib.import_module(full_module_path)

                    # Scan for subclasses of BasePlugin defined in the imported module
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if issubclass(obj, BasePlugin) and obj is not BasePlugin:
                            try:
                                plugin_instance = obj()
                                plugins.append(plugin_instance)
                                logger.info(
                                    "Successfully loaded and instantiated plugin: %s (%s)",
                                    plugin_instance.name,
                                    obj.__name__,
                                )
                            except Exception as inst_err:
                                logger.error("Failed to instantiate plugin class %s: %s", name, inst_err)
                except Exception as imp_err:
                    logger.error("Failed to dynamically import plugin module %s: %s", module_name, imp_err)

        return plugins
