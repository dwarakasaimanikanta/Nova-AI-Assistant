"""
plugins/voice_plugin.py
-----------------------
Plugin registration for the VoiceTool.
"""

from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.voice import VoiceTool


class VoicePlugin(BasePlugin):
    """Plugin providing text-to-speech voice output capabilities."""

    @property
    def name(self) -> str:
        return "voice"

    def get_tools(self) -> list[BaseTool]:
        """Expose the consolidated VoiceTool instance."""
        return [VoiceTool()]
