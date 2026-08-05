"""
tests/test_tools/test_scheduler.py
----------------------------------
Unit tests for Nova's consolidated scheduler tool and plugin.
"""

from typing import Any
import time
from unittest.mock import MagicMock, patch

from tools.scheduler import SchedulerTool
from tools.base_tool import RiskLevel
from core.engine import NovaEngine
from memory.short_term import ShortTermMemory
from plugins.loader import PluginLoader


def test_scheduler_schema() -> None:
    """Ensure SchedulerTool defines correct parameters schema and is LOW risk."""
    tool = SchedulerTool()
    assert tool.name == "scheduler"
    assert tool.risk_level == RiskLevel.LOW
    assert "action" in tool.parameters_schema["required"]
    assert "delay_seconds" in tool.parameters_schema["properties"]


def test_scheduler_plugin_discovery() -> None:
    """Ensure PluginLoader automatically scans and registers the SchedulerPlugin."""
    loader = PluginLoader()
    discovered_plugins = loader.discover_and_load_plugins()

    assert any(p.name == "scheduler" for p in discovered_plugins)


def test_engine_scheduler_registration() -> None:
    """Ensure engine dynamically registers scheduler tools."""
    memory = ShortTermMemory()
    engine = NovaEngine(memory=memory)

    assert any(p.name == "scheduler" for p in engine.plugins)
    assert engine.registry.get_tool("scheduler") is not None


@patch("threading.Timer")
def test_scheduler_schedule_action(mock_timer_class: MagicMock) -> None:
    """Ensure scheduling action starts a timer and updates active task dictionary."""
    mock_timer_inst = MagicMock()
    mock_timer_class.return_value = mock_timer_inst

    tool = SchedulerTool()
    res = tool.execute(action="schedule_after_delay", delay_seconds=10, command="echo test")

    assert "Success" in res
    assert "task_1" in res
    assert "task_1" in tool.active_tasks

    # Check Timer initialization arguments: delay=10, function=worker
    mock_timer_class.assert_called_once()
    args, kwargs = mock_timer_class.call_args
    assert args[0] == 10

    # Check timer start
    mock_timer_inst.start.assert_called_once()


@patch("threading.Timer")
def test_scheduler_list_and_cancel_actions(mock_timer_class: MagicMock) -> None:
    """Ensure active tasks can be listed and cancelled successfully."""
    mock_timer_inst = MagicMock()
    mock_timer_class.return_value = mock_timer_inst

    tool = SchedulerTool()

    # Empty list check
    assert "no active scheduled tasks" in tool.execute(action="list_scheduled_tasks").lower()

    # Schedule task
    tool.execute(action="schedule_after_delay", delay_seconds=5, command="dir")

    # List check
    list_res = tool.execute(action="list_scheduled_tasks")
    assert "task_1" in list_res
    assert "dir" in list_res

    # Cancel check
    cancel_res = tool.execute(action="cancel_scheduled_task", task_id="task_1")
    assert "Success" in cancel_res
    assert "task_1" not in tool.active_tasks

    # Check that cancel was called on Timer instance
    mock_timer_inst.cancel.assert_called_once()


def test_scheduler_invalid_actions() -> None:
    """Ensure invalid parameters are rejected gracefully."""
    tool = SchedulerTool()

    assert "Failure" in tool.execute()
    assert "Failure" in tool.execute(action="")
    assert "Failure" in tool.execute(action="schedule_after_delay")  # Missing parameters
    assert "Failure" in tool.execute(action="schedule_after_delay", delay_seconds=-10, command="echo")  # Negative delay
    assert "Failure" in tool.execute(action="schedule_after_delay", delay_seconds="abc", command="echo")  # Invalid type
    assert "Failure" in tool.execute(action="cancel_scheduled_task")  # Missing task_id
    assert "Failure" in tool.execute(action="cancel_scheduled_task", task_id="nonexistent")
    assert "Failure" in tool.execute(action="unknown")
