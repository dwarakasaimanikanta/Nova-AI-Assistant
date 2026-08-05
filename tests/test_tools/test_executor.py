"""
tests/test_tools/test_executor.py
---------------------------------
Unit tests for Nova's ToolExecutor.
"""

from tools.executor import ToolExecutor
from tools.builtin_tools import CalculateTool


def test_executor_successful_run() -> None:
    """Ensure executor runs tools successfully when arguments are valid."""
    executor = ToolExecutor()
    tool = CalculateTool()

    result = executor.execute_tool(tool, {"expression": "5 * 5"})
    assert result == "5 * 5 = 25"


def test_executor_missing_argument() -> None:
    """Ensure executor flags missing required arguments without running the tool."""
    executor = ToolExecutor()
    tool = CalculateTool()

    result = executor.execute_tool(tool, {})
    assert "missing required parameters" in result


def test_executor_runtime_exception() -> None:
    """Ensure executor catches tool exceptions and handles them gracefully."""
    executor = ToolExecutor()
    tool = CalculateTool()

    # Division by zero inside tool is handled by the tool itself or the executor
    result = executor.execute_tool(tool, {"expression": "10 / 0"})
    assert "Division by zero" in result
