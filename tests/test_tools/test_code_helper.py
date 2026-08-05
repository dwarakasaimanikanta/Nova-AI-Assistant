"""
tests/test_tools/test_code_helper.py
-----------------------------------
Unit tests for Nova's consolidated code helper tool and plugin.
"""

from typing import Any
import os
from unittest.mock import MagicMock, patch

from tools.code_helper import CodeHelperTool
from tools.base_tool import RiskLevel
from core.engine import NovaEngine
from memory.short_term import ShortTermMemory
from plugins.loader import PluginLoader
from tools.permission_gate import PermissionGate


def test_code_helper_schema() -> None:
    """Ensure CodeHelperTool defines correct parameters schema and is HIGH risk by default."""
    tool = CodeHelperTool()
    assert tool.name == "code_helper"
    assert tool.risk_level == RiskLevel.HIGH
    assert "action" in tool.parameters_schema["required"]
    assert "code" in tool.parameters_schema["required"]


def test_code_helper_plugin_discovery() -> None:
    """Ensure PluginLoader automatically scans and registers the CodeHelperPlugin."""
    loader = PluginLoader()
    discovered_plugins = loader.discover_and_load_plugins()

    assert any(p.name == "code_helper" for p in discovered_plugins)


def test_engine_code_helper_registration() -> None:
    """Ensure engine dynamically registers code helper tools."""
    memory = ShortTermMemory()
    engine = NovaEngine(memory=memory)

    assert any(p.name == "code_helper" for p in engine.plugins)
    assert engine.registry.get_tool("code_helper") is not None


def test_permission_gate_code_helper_risk() -> None:
    """Ensure PermissionGate accurately assigns risk levels dynamically based on action."""
    gate = PermissionGate()
    tool = CodeHelperTool()

    # parse_code is LOW risk
    assert gate.check_permission(tool, {"action": "parse_code", "code": "print(1)"}) is True

    # execute_code is HIGH risk
    assert gate.check_permission(tool, {"action": "execute_code", "code": "print(2)"}) is False


def test_code_helper_parse_action() -> None:
    """Ensure parse_code correctly runs syntax AST checks."""
    tool = CodeHelperTool()

    # Valid syntax
    res_valid = tool.execute(action="parse_code", code="def hello():\n    print('world')")
    assert "Success" in res_valid
    assert "AST" in res_valid

    # Syntax Error
    res_invalid = tool.execute(action="parse_code", code="def hello(\n    print('world')")
    assert "Failure" in res_invalid
    assert "Syntax error" in res_invalid


@patch("subprocess.run")
def test_code_helper_execute_action(mock_run: MagicMock) -> None:
    """Ensure execute_code writes to file, calls subprocess python, and cleans up."""
    mock_run.return_value = MagicMock(returncode=0, stdout="hello world\n", stderr="")

    tool = CodeHelperTool()
    res = tool.execute(action="execute_code", code="print('hello world')")

    assert "hello world" in res
    assert "--- Standard Output ---" in res

    # Check subprocess.run call
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    # Python binary path should be in args list
    assert "temp_run.py" in args[0][1]


def test_code_helper_missing_params() -> None:
    """Ensure code helper handles missing or unknown parameters gracefully."""
    tool = CodeHelperTool()

    assert "Failure" in tool.execute()
    assert "Failure" in tool.execute(action="")
    assert "Failure" in tool.execute(action="parse_code")  # Missing code
    assert "Failure" in tool.execute(action="execute_code", code="")  # Missing code
    assert "Failure" in tool.execute(action="invalid", code="print(1)")
