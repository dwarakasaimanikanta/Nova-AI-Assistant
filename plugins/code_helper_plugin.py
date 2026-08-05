"""
plugins/code_helper_plugin.py
-----------------------------
Plugin registration for the CodeHelperTool.
"""

from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.code_helper import CodeHelperTool


class CodeHelperPlugin(BasePlugin):
    """Plugin providing code parsing and isolated Python code execution."""

    @property
    def name(self) -> str:
        return "code_helper"

    def get_tools(self) -> list[BaseTool]:
        """Expose the consolidated CodeHelperTool instance."""
        return [CodeHelperTool()]
