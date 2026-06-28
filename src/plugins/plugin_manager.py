import structlog
from typing import List, Dict, Any, Type
import importlib
import pkgutil
from src.plugins.base_plugin import BasePlugin
from src.utils.config_loader import AppConfig
import src.plugins.ingestion

logger = structlog.get_logger(__name__)

class PluginManager:
    """
    Discovers, loads, and manages lifecycle of plugins.
    Registers plugins with the EventBus based on their subscriptions.
    """
    def __init__(self, config: AppConfig, event_bus: Any):
        self.config = config
        self.event_bus = event_bus
        self.plugins: Dict[str, BasePlugin] = {}
        self._load_plugins()

    def _load_plugins(self):
        """Discover and load all plugins in specified packages."""
        logger.info("Discovering plugins...")
        
        # We need to import the packages so pkgutil can find them
        import src.plugins.ingestion
        import src.plugins.analytics
        import src.plugins.rendering
        import src.plugins.notifications
        import src.plugins.publishing
        
        packages_to_scan = [
            src.plugins.ingestion,
            src.plugins.analytics,
            src.plugins.rendering,
            src.plugins.notifications,
            src.plugins.publishing
        ]
        
        for package in packages_to_scan:
            if not hasattr(package, '__path__'):
                continue
                
            for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
                if is_pkg:
                    continue
                
                full_module_name = f"{package.__name__}.{module_name}"
                module = importlib.import_module(full_module_name)
                
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    # Check if it's a class and a subclass of BasePlugin (but not BasePlugin itself)
                    if isinstance(attr, type) and issubclass(attr, BasePlugin) and attr is not BasePlugin:
                        # Instantiate the plugin
                        try:
                            plugin_instance = attr(self.config)
                            self.register_plugin(plugin_instance)
                        except Exception as e:
                            logger.error("Failed to load plugin", plugin=attr_name, error=str(e))

    def register_plugin(self, plugin: BasePlugin):
        name = plugin.name()
        self.plugins[name] = plugin
        
        subs = plugin.subscriptions()
        for event_type, handler in subs.items():
            self.event_bus.subscribe(event_type, handler)
            
        logger.info("Plugin registered", name=name, subscriptions=list(subs.keys()))

