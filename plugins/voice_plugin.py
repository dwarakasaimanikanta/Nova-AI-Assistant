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
        import os
        import sys
        if "pytest" in sys.modules or os.getenv("ENVIRONMENT") == "test":
            logger.info("Testing environment detected (pytest or ENVIRONMENT=test). Skipping VoiceManager background thread start.")
            return

        from config import VOICE_INPUT_ENABLED, WAKE_WORD_ENABLED
        from voice.voice_manager import VoiceManager
        
        self.voice_manager = VoiceManager(
            engine=engine,
            wake_word_enabled=WAKE_WORD_ENABLED,
            voice_input_enabled=VOICE_INPUT_ENABLED,
        )
        self.voice_manager.start()

    def shutdown(self) -> None:
        """Stop background threads."""
        if self.voice_manager:
            self.voice_manager.stop()

    def __del__(self) -> None:
        self.shutdown()
