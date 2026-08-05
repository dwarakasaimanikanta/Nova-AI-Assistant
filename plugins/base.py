"""
plugins/base.py
---------------
Core abstraction interface for all Nova plugins.
"""

from abc import ABC, abstractmethod
from tools.base_tool import BaseTool


class BasePlugin(ABC):
    """Abstract base class representing a plugin supplying tools to the agent."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The distinct identifying name of the plugin."""
        pass

    @abstractmethod
    def get_tools(self) -> list[BaseTool]:
        """Exposes the list of tool instances provided by the plugin."""
        pass
