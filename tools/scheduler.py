"""
tools/scheduler.py
------------------
Task automation and scheduling tool conforming to the BaseTool interface.
Manages background timer tasks in a thread-safe, non-blocking manner.
"""

import subprocess
import threading
from typing import Any

from tools.base_tool import BaseTool, RiskLevel
from utils.logger import get_logger

logger = get_logger(__name__)


class SchedulerTool(BaseTool):
    """Consolidated task scheduler tool allowing background command triggers after delays."""

    def __init__(self) -> None:
        super().__init__()
        self.active_tasks: dict[str, dict[str, Any]] = {}
        self.task_counter = 0
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "scheduler"

    @property
    def description(self) -> str:
        return (
            "Schedules terminal commands to execute in the background after a specific delay. "
            "Supported actions: 'schedule_after_delay' (starts background timer), "
            "'list_scheduled_tasks' (lists all active pending timers), and "
            "'cancel_scheduled_task' (cancels a pending timer by ID)."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["schedule_after_delay", "list_scheduled_tasks", "cancel_scheduled_task"],
                    "description": "The scheduling action to perform.",
                },
                "delay_seconds": {
                    "type": "integer",
                    "description": "The delay in seconds before executing the command (required for 'schedule_after_delay').",
                },
                "command": {
                    "type": "string",
                    "description": "The command string to execute after the delay (required for 'schedule_after_delay').",
                },
                "task_id": {
                    "type": "string",
                    "description": "The ID of the scheduled task to cancel (required for 'cancel_scheduled_task').",
                },
            },
            "required": ["action"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        # Scheduling operations are LOW risk; permission gate will check actual executed command risk if required.
        return RiskLevel.LOW

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "").strip()
        if not action:
            return "Failure: No action parameter specified."

        logger.info("Executing SchedulerTool action: '%s'", action)

        if action == "schedule_after_delay":
            delay = kwargs.get("delay_seconds")
            command = kwargs.get("command", "").strip()

            if delay is None or not command:
                return "Failure: Action 'schedule_after_delay' requires 'delay_seconds' and 'command' parameters."

            try:
                delay_secs = int(delay)
                if delay_secs < 0:
                    return "Failure: Delay cannot be negative."
            except (ValueError, TypeError):
                return "Failure: Invalid delay_seconds parameter (must be an integer)."

            with self._lock:
                self.task_counter += 1
                task_id = f"task_{self.task_counter}"

                def worker() -> None:
                    # Thread-safe cleanup
                    with self._lock:
                        self.active_tasks.pop(task_id, None)

                    logger.info("Starting scheduled execution for task '%s': '%s'", task_id, command)
                    try:
                        res = subprocess.run(command, shell=True, capture_output=True, text=True)
                        logger.info(
                            "Scheduled task '%s' completed with exit code %d. Stdout: %s, Stderr: %s",
                            task_id,
                            res.returncode,
                            res.stdout.strip(),
                            res.stderr.strip(),
                        )
                    except Exception as e:
                        logger.error("Error executing scheduled command '%s': %s", command, e)

                timer = threading.Timer(delay_secs, worker)
                timer.daemon = True
                timer.start()

                self.active_tasks[task_id] = {
                    "command": command,
                    "delay_seconds": delay_secs,
                    "timer": timer,
                }

                return (
                    f"Success: Command '{command}' scheduled successfully as task ID '{task_id}' "
                    f"to run in {delay_secs} seconds."
                )

        elif action == "list_scheduled_tasks":
            with self._lock:
                if not self.active_tasks:
                    return "No active scheduled tasks."

                lines = []
                for tid, info in self.active_tasks.items():
                    lines.append(f"- ID: {tid} | Delay: {info['delay_seconds']}s | Command: '{info['command']}'")

                return "Active Scheduled Tasks:\n" + "\n".join(lines)

        elif action == "cancel_scheduled_task":
            tid = kwargs.get("task_id", "").strip()
            if not tid:
                return "Failure: Action 'cancel_scheduled_task' requires a 'task_id' parameter."

            with self._lock:
                if tid not in self.active_tasks:
                    return f"Failure: Scheduled task '{tid}' not found."

                info = self.active_tasks.pop(tid)
                info["timer"].cancel()

                return f"Success: Scheduled task '{tid}' has been cancelled."

        else:
            return f"Failure: Unknown scheduler action '{action}'."
