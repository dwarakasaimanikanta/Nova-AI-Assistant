"""
tests/test_tools/test_terminal.py
---------------------------------
Unit tests for Nova's consolidated terminal tool and plugin system.
"""

import os
from pathlib import Path
import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

from tools.terminal import TerminalTool
from tools.permission_gate import PermissionGate
from tools.base_tool import RiskLevel
from core.engine import NovaEngine
from memory.short_term import ShortTermMemory
from plugins.loader import PluginLoader


def test_terminal_schema() -> None:
    """Ensure TerminalTool defines required parameters schema and defaults to HIGH risk."""
    tool = TerminalTool()
    assert tool.name == "terminal"
    assert tool.risk_level == RiskLevel.HIGH
    assert "command" in tool.parameters_schema["required"]
    assert "type" in tool.parameters_schema["properties"]["command"]


def test_terminal_plugin_discovery() -> None:
    """Ensure PluginLoader automatically scans and loads the TerminalPlugin."""
    loader = PluginLoader()
    discovered_plugins = loader.discover_and_load_plugins()

    # TerminalPlugin, BrowserPlugin, FileManagerPlugin should be loaded
    assert len(discovered_plugins) >= 3
    assert any(p.name == "terminal" for p in discovered_plugins)


def test_engine_terminal_registration() -> None:
    """Ensure engine dynamically registers terminal tools."""
    memory = ShortTermMemory()
    engine = NovaEngine(memory=memory)

    # TerminalPlugin should be loaded
    assert any(p.name == "terminal" for p in engine.plugins)

    # TerminalTool should be registered in registry
    assert engine.registry.get_tool("terminal") is not None


def test_permission_gate_terminal_overrides() -> None:
    """Ensure permission gate overrides risk level dynamically based on terminal command type."""
    gate = PermissionGate()
    tool = TerminalTool()

    # Read-only/Status commands should be LOW risk (auto-approved)
    assert gate.check_permission(tool, {"command": "pwd"}) is True
    assert gate.check_permission(tool, {"command": "dir"}) is True
    assert gate.check_permission(tool, {"command": "git status"}) is True
    assert gate.check_permission(tool, {"command": "git log"}) is True
    assert gate.check_permission(tool, {"command": "git diff"}) is True

    # State-altering or execution commands should trigger security prompts (HIGH risk)
    assert gate.check_permission(tool, {"command": "git add ."}) is False
    assert gate.check_permission(tool, {"command": "git commit -m 'initial'"}) is False
    assert gate.check_permission(tool, {"command": "mkdir new_folder"}) is False
    assert gate.check_permission(tool, {"command": "rmdir old_folder"}) is False
    assert gate.check_permission(tool, {"command": "python script.py"}) is False
    assert gate.check_permission(tool, {"command": "pip install requests"}) is False


@patch("subprocess.run")
def test_terminal_execution_success(mock_run: Any) -> None:
    """Ensure TerminalTool executes command and returns captured outputs correctly."""
    tool = TerminalTool()

    # Mock successful response
    mock_res = MagicMock()
    mock_res.stdout = "Hello from stdout"
    mock_res.stderr = ""
    mock_run.return_value = mock_res

    res = tool.execute(command="echo 'Hello'")
    assert res == "Hello from stdout"
    mock_run.assert_called_with(
        "echo 'Hello'",
        shell=True,
        text=True,
        capture_output=True,
        cwd=tool._cwd,
        timeout=30.0,
    )


@patch("subprocess.run")
def test_terminal_execution_with_stderr(mock_run: Any) -> None:
    """Ensure stdout and stderr are merged correctly in execution results."""
    tool = TerminalTool()

    mock_res = MagicMock()
    mock_res.stdout = "Output data"
    mock_res.stderr = "Error message"
    mock_run.return_value = mock_res

    res = tool.execute(command="invalid_cmd")
    assert "Output data" in res
    assert "Error message" in res


@patch("subprocess.run")
def test_terminal_execution_timeout(mock_run: Any) -> None:
    """Ensure execution timeouts are caught and reported safely."""
    tool = TerminalTool()
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="echo", timeout=30.0)

    res = tool.execute(command="sleep 100")
    assert "timed out" in res.lower()


def test_terminal_cwd_virtual_persistence() -> None:
    """Ensure cd command changes persist virtual directory state without running subprocesses."""
    tool = TerminalTool()
    original_cwd = tool._cwd

    # Target path to navigate to (must be a real folder, e.g. parent folder or plugins folder)
    target_path = Path(original_cwd).parent.resolve()

    res = tool.execute(command=f"cd {target_path}")
    assert "Success" in res
    assert tool._cwd == str(target_path)

    # Navigating to non-existent folder should fail
    res = tool.execute(command="cd non_existent_folder_abc_123")
    assert "Failure" in res
    assert tool._cwd == str(target_path)
