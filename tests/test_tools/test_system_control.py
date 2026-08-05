"""
tests/test_tools/test_system_control.py
---------------------------------------
Unit tests for Nova's consolidated system control tool and plugin.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from tools.system_control import SystemControlTool
from tools.base_tool import RiskLevel
from core.engine import NovaEngine
from memory.short_term import ShortTermMemory
from plugins.loader import PluginLoader
from tools.permission_gate import PermissionGate


def test_system_control_schema() -> None:
    """Ensure SystemControlTool defines correct parameter schema and defaults to HIGH risk."""
    tool = SystemControlTool()
    assert tool.name == "system_control"
    assert tool.risk_level == RiskLevel.HIGH
    assert "action" in tool.parameters_schema["required"]
    assert "app_name" in tool.parameters_schema["properties"]


def test_system_control_plugin_discovery() -> None:
    """Ensure PluginLoader automatically scans and registers the SystemControlPlugin."""
    loader = PluginLoader()
    discovered_plugins = loader.discover_and_load_plugins()

    assert any(p.name == "system_control" for p in discovered_plugins)


def test_engine_system_control_registration() -> None:
    """Ensure engine dynamically registers system control tools."""
    memory = ShortTermMemory()
    engine = NovaEngine(memory=memory)

    assert any(p.name == "system_control" for p in engine.plugins)
    assert engine.registry.get_tool("system_control") is not None


def test_permission_gate_system_control_risk() -> None:
    """Ensure PermissionGate accurately assigns risk levels dynamically based on action."""
    gate = PermissionGate()
    tool = SystemControlTool()

    # launch_app is LOW risk
    assert gate.check_permission(tool, {"action": "launch_app", "app_name": "notepad"}) is True

    # lock, shutdown, restart, sleep are HIGH risk
    # (Without callback, it defaults to False for high risk tools)
    assert gate.check_permission(tool, {"action": "lock_workstation"}) is False
    assert gate.check_permission(tool, {"action": "shutdown"}) is False
    assert gate.check_permission(tool, {"action": "restart"}) is False
    assert gate.check_permission(tool, {"action": "sleep"}) is False


@patch("subprocess.run")
def test_system_control_lock_execution(mock_run: MagicMock) -> None:
    """Ensure lock workstation triggers correct subprocess call."""
    tool = SystemControlTool()
    res = tool.execute(action="lock_workstation")

    assert "Success" in res
    mock_run.assert_called_once_with(["rundll32.exe", "user32.dll,LockWorkStation"], check=True)


@patch("subprocess.run")
def test_system_control_power_execution(mock_run: MagicMock) -> None:
    """Ensure shutdown, restart, and sleep trigger correct subprocess calls."""
    tool = SystemControlTool()

    # Shutdown
    res_shutdown = tool.execute(action="shutdown")
    assert "Success" in res_shutdown
    mock_run.assert_any_call(["shutdown", "/s", "/t", "60"], check=True)

    # Restart
    res_restart = tool.execute(action="restart")
    assert "Success" in res_restart
    mock_run.assert_any_call(["shutdown", "/r", "/t", "60"], check=True)

    # Sleep
    res_sleep = tool.execute(action="sleep")
    assert "Success" in res_sleep
    mock_run.assert_any_call(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], check=True)


@patch("subprocess.Popen")
def test_system_control_launch_app_execution(mock_popen: MagicMock) -> None:
    """Ensure launch_app uses Popen asynchronously."""
    tool = SystemControlTool()

    # Safe Notepad launch
    res = tool.execute(action="launch_app", app_name="notepad")
    assert "Success" in res
    mock_popen.assert_any_call(["notepad.exe"], shell=True)

    # Safe custom launch
    res_custom = tool.execute(action="launch_app", app_name="calc")
    assert "Success" in res_custom
    mock_popen.assert_any_call(["calc.exe"], shell=True)


def test_system_control_invalid_and_empty() -> None:
    """Ensure invalid commands are rejected gracefully."""
    tool = SystemControlTool()

    assert "Failure" in tool.execute()
    assert "Failure" in tool.execute(action="")
    assert "Failure" in tool.execute(action="launch_app")  # Missing app_name
    assert "Failure" in tool.execute(action="launch_app", app_name="bad_app; rm -rf")  # Invalid characters
    assert "Failure" in tool.execute(action="invalid_action")
