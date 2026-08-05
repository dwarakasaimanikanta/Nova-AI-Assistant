"""
plugins/calculator_plugin.py
----------------------------
Plugin registration for the CalculateTool.
"""

from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.builtin_tools import CalculateTool


class CalculatorPlugin(BasePlugin):
    """Plugin providing calculator capabilities."""

    @property
    def name(self) -> str:
        return "calculator"

    def get_tools(self) -> list[BaseTool]:
        """Expose the consolidated CalculateTool instance."""
        return [CalculateTool()]
