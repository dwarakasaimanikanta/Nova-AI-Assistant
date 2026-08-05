"""
tools/voice.py
--------------
Consolidated text-to-speech voice tool conforming to the BaseTool interface.
Asynchronously synthesizes voice backends based on operating system platform.
"""

import platform
import subprocess
from typing import Any

from tools.base_tool import BaseTool, RiskLevel
from utils.logger import get_logger

logger = get_logger(__name__)


class VoiceTool(BaseTool):
    """Consolidated text-to-speech voice synthesis tool."""

    @property
    def name(self) -> str:
        return "voice_tts"

    @property
    def description(self) -> str:
        return (
            "Uses the system text-to-speech engine to speak out loud the provided text message. "
            "Use this to output spoken statements to the user."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text content to speak out loud.",
                }
            },
            "required": ["text"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        # Output operations are LOW risk and auto-approved
        return RiskLevel.LOW

    def execute(self, **kwargs: Any) -> str:
        text = kwargs.get("text", "").strip()
        if not text:
            return "Failure: No text content provided to speak."

        logger.info("Executing text-to-speech synthesis: '%s'", text)
        os_platform = platform.system()

        try:
            if os_platform == "Windows":
                # Escape single quotes for PowerShell string literal format
                escaped_text = text.replace("'", "''")
                ps_cmd = (
                    f"Add-Type -AssemblyName System.Speech; "
                    f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{escaped_text}')"
                )
                # Execute asynchronously so it returns immediately and speaks in the background
                subprocess.Popen(["powershell", "-Command", ps_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"Success: Speaking message out loud in the background: '{text}'"

            elif os_platform == "Darwin":  # macOS
                subprocess.Popen(["say", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"Success: Speaking message out loud in the background: '{text}'"

            elif os_platform == "Linux":
                try:
                    subprocess.Popen(["espeak", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return f"Success: Speaking message out loud in the background: '{text}'"
                except FileNotFoundError:
                    logger.warning("espeak not installed on Linux system. Falling back to log print.")
                    return f"Unsupported platform/tool missing: Logged voice message: '{text}'"

            else:
                return f"Unsupported platform: Logged voice message: '{text}'"

        except Exception as e:
            logger.exception("Error executing voice text-to-speech: %s", e)
            return f"Failure executing text-to-speech: {e}"
