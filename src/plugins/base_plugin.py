from abc import ABC, abstractmethod
from typing import Callable, Any, Dict
import structlog

logger = structlog.get_logger(__name__)

class BasePlugin(ABC):
    """
    Base class for all ingestion plugins.
    """

    @abstractmethod
    def name(self) -> str:
        """Return the unique name of the plugin."""
        pass

    @abstractmethod
    def subscriptions(self) -> Dict[str, Callable]:
        """
        Return a dict mapping event types to handler functions.
        Example: {'PipelineStarted': self.on_start}
        """
        pass
