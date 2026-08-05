"""
tools/system_control.py
------------------------
Consolidated system control tool conforming to the BaseTool interface.
Supports power states (shutdown, restart, sleep), locking, and launching utilities.
"""

import os
import subprocess
from typing import Any

from tools.base_tool import BaseTool, RiskLevel
from utils.logger import get_logger

logger = get_logger(__name__)


class SystemControlTool(BaseTool):
    """Consolidated tool for triggering Windows system level commands and utility applications."""

    @property
    def name(self) -> str:
        return "system_control"

    @property
    def description(self) -> str:
        return (
            "Controls system actions on the Windows machine. Supported actions: "
            "'lock_workstation' (locks the screen), 'shutdown' (shuts down the PC in 60s), "
            "'restart' (restarts the PC in 60s), 'sleep' (puts the PC to sleep), and "
            "'launch_app' (opens a system utility by name like notepad, calc, mspaint, explorer, taskmgr)."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["lock_workstation", "shutdown", "restart", "sleep", "launch_app"],
                    "description": "The system control action to perform.",
                },
                "app_name": {
                    "type": "string",
                    "description": "The name of the application to launch (required when action is 'launch_app').",
                },
            },
            "required": ["action"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        # Default risk to HIGH. PermissionGate will override or evaluate dynamically.
        return RiskLevel.HIGH

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "").strip()
        if not action:
            return "Failure: No action parameter specified."

        logger.info("Executing SystemControlTool action: '%s'", action)

        if action == "lock_workstation":
            try:
                subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=True)
                return "Success: Workstation locked."
            except Exception as e:
                logger.error("Failed to lock workstation: %s", e)
                return f"Failure: Failed to lock screen: {e}"

        elif action == "shutdown":
            try:
                subprocess.run(["shutdown", "/s", "/t", "60"], check=True)
                return "Success: System shutdown scheduled in 60 seconds."
            except Exception as e:
                logger.error("Failed to schedule shutdown: %s", e)
                return f"Failure: Failed to schedule shutdown: {e}"

        elif action == "restart":
            try:
                subprocess.run(["shutdown", "/r", "/t", "60"], check=True)
                return "Success: System restart scheduled in 60 seconds."
            except Exception as e:
                logger.error("Failed to schedule restart: %s", e)
                return f"Failure: Failed to schedule restart: {e}"

        elif action == "sleep":
            try:
                subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], check=True)
                return "Success: System put to sleep."
            except Exception as e:
                logger.error("Failed to suspend system: %s", e)
                return f"Failure: Failed to put system to sleep: {e}"

        elif action == "launch_app":
            app_name = kwargs.get("app_name", "").strip().lower()
            if not app_name:
                return "Failure: Action 'launch_app' requires an 'app_name' parameter."

            # Common Windows system tools mapping
            app_map = {
                "notepad": "notepad.exe",
                "calc": "calc.exe",
                "calculator": "calc.exe",
                "mspaint": "mspaint.exe",
                "paint": "mspaint.exe",
                "explorer": "explorer.exe",
                "taskmgr": "taskmgr.exe",
                "task manager": "taskmgr.exe",
            }

            if app_name not in app_map:
                # Sanitization check to prevent command injection
                if not app_name.replace("_", "").isalnum():
                    return f"Failure: Application '{app_name}' contains invalid characters."
                cmd = f"{app_name}.exe"
            else:
                cmd = app_map[app_name]

            try:
                # Start process in background asynchronously so the tool call returns instantly
                subprocess.Popen([cmd], shell=True)
                return f"Success: Launched application '{app_name}'."
            except Exception as e:
                logger.error("Failed to launch application '%s': %s", app_name, e)
                return f"Failure: Failed to launch '{app_name}': {e}"

        else:
            return f"Failure: Unknown system action '{action}'."
