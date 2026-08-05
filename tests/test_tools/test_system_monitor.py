"""
tests/test_tools/test_system_monitor.py
---------------------------------------
Unit tests for Nova's consolidated system monitor tool and plugin.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from tools.system_monitor import SystemMonitorTool
from tools.base_tool import RiskLevel
from core.engine import NovaEngine
from memory.short_term import ShortTermMemory
from plugins.loader import PluginLoader


def test_system_monitor_schema() -> None:
    """Ensure SystemMonitorTool defines correct parameters schema and is LOW risk."""
    tool = SystemMonitorTool()
    assert tool.name == "system_monitor"
    assert tool.risk_level == RiskLevel.LOW
    assert "action" in tool.parameters_schema["required"]
    assert "enum" in tool.parameters_schema["properties"]["action"]


def test_system_monitor_plugin_discovery() -> None:
    """Ensure PluginLoader automatically scans and registers the SystemMonitorPlugin."""
    loader = PluginLoader()
    discovered_plugins = loader.discover_and_load_plugins()

    assert any(p.name == "system_monitor" for p in discovered_plugins)


def test_engine_system_monitor_registration() -> None:
    """Ensure engine dynamically registers system monitor tools."""
    memory = ShortTermMemory()
    engine = NovaEngine(memory=memory)

    assert any(p.name == "system_monitor" for p in engine.plugins)
    assert engine.registry.get_tool("system_monitor") is not None


@patch("platform.system")
def test_system_monitor_execution_fallback(mock_system: MagicMock) -> None:
    """Ensure non-Windows systems run graceful mock outputs."""
    mock_system.return_value = "Linux"
    tool = SystemMonitorTool()

    stats_res = tool.execute(action="get_system_stats")
    assert "CPU Load" in stats_res
    assert "Memory Usage" in stats_res

    proc_res = tool.execute(action="list_top_processes")
    assert "python" in proc_res
    assert "node" in proc_res


@patch("platform.system")
@patch("subprocess.run")
def test_system_monitor_execution_windows(mock_run: MagicMock, mock_system: MagicMock) -> None:
    """Ensure Windows platform triggers PowerShell queries successfully."""
    mock_system.return_value = "Windows"
    mock_run.return_value = MagicMock(returncode=0, stdout="Mocked Output\n", stderr="")

    tool = SystemMonitorTool()

    stats_res = tool.execute(action="get_system_stats")
    assert "Live System Resource Stats:" in stats_res
    assert "CPU Load" in stats_res
    assert "Physical Memory" in stats_res
    assert "Disk Space (C:)" in stats_res
    assert "Battery Status" in stats_res
    assert mock_run.call_count == 4

    # Reset mock and test list processes
    mock_run.reset_mock()
    mock_run.return_value = MagicMock(returncode=0, stdout="ProcessTable\n", stderr="")
    proc_res = tool.execute(action="list_top_processes")
    assert "Top 8 CPU-consuming processes:" in proc_res
    assert "ProcessTable" in proc_res
    mock_run.assert_called_once()
    assert "Get-Process" in mock_run.call_args[0][0][2]


def test_system_monitor_missing_params() -> None:
    """Ensure system monitor handles missing or unknown parameters gracefully."""
    tool = SystemMonitorTool()
    assert "Failure" in tool.execute()
    assert "Failure" in tool.execute(action="")
    assert "Failure" in tool.execute(action="unknown_action")
