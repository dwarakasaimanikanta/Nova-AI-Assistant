"""
tests/test_tools/test_voice.py
------------------------------
Unit tests for Nova's consolidated voice TTS tool and plugin.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from tools.voice import VoiceTool
from tools.base_tool import RiskLevel
from core.engine import NovaEngine
from memory.short_term import ShortTermMemory
from plugins.loader import PluginLoader


def test_voice_schema() -> None:
    """Ensure VoiceTool defines correct parameters schema and is LOW risk."""
    tool = VoiceTool()
    assert tool.name == "voice_tts"
    assert tool.risk_level == RiskLevel.LOW
    assert "text" in tool.parameters_schema["required"]
    assert "type" in tool.parameters_schema["properties"]["text"]


def test_voice_plugin_discovery() -> None:
    """Ensure PluginLoader automatically scans and registers the VoicePlugin."""
    loader = PluginLoader()
    discovered_plugins = loader.discover_and_load_plugins()

    assert any(p.name == "voice" for p in discovered_plugins)


def test_engine_voice_registration() -> None:
    """Ensure engine dynamically registers voice tools."""
    memory = ShortTermMemory()
    engine = NovaEngine(memory=memory)

    assert any(p.name == "voice" for p in engine.plugins)
    assert engine.registry.get_tool("voice_tts") is not None


@patch("platform.system")
@patch("subprocess.Popen")
def test_voice_execution_windows(mock_popen: MagicMock, mock_system: MagicMock) -> None:
    """Ensure Windows platform triggers PowerShell System.Speech call."""
    mock_system.return_value = "Windows"
    tool = VoiceTool()
    res = tool.execute(text="hello")

    assert "Success" in res
    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    # First argument should be list with powershell
    assert args[0][0] == "powershell"
    assert "SpeechSynthesizer" in args[0][2]


@patch("platform.system")
@patch("subprocess.Popen")
def test_voice_execution_macos(mock_popen: MagicMock, mock_system: MagicMock) -> None:
    """Ensure macOS platform triggers say call."""
    mock_system.return_value = "Darwin"
    tool = VoiceTool()
    res = tool.execute(text="hello world")

    assert "Success" in res
    mock_popen.assert_called_once_with(["say", "hello world"], stdout=-3, stderr=-3)


def test_voice_missing_text() -> None:
    """Ensure voice tool handles empty texts gracefully."""
    tool = VoiceTool()
    assert "Failure" in tool.execute()
    assert "Failure" in tool.execute(text="")
