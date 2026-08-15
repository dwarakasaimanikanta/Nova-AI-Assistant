"""
plugins/voice_plugin.py
-----------------------
Plugin registration for the VoiceTool.
"""

from typing import Any
from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.voice import VoiceTool
from utils.logger import get_logger

logger = get_logger(__name__)


class VoicePlugin(BasePlugin):
    """Plugin providing text-to-speech voice output and background voice input capabilities."""

    def __init__(self) -> None:
        self.voice_manager = None

    @property
    def name(self) -> str:
        return "voice"

    def get_tools(self) -> list[BaseTool]:
        """Expose the consolidated VoiceTool instance."""
        return [VoiceTool()]

    def initialize_plugin(self, engine: Any) -> None:
        """Initialize the background voice input manager if enabled."""
        # Managed exclusively by BootManager to prevent duplicate instances
        pass

    def shutdown(self) -> None:
        """Stop background threads."""
        if self.voice_manager:
            self.voice_manager.stop()

    def __del__(self) -> None:
        self.shutdown()
