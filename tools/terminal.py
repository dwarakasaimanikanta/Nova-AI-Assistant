"""
tools/terminal.py
-----------------
Consolidated terminal automation tool executing commands via subprocess.
Conforms to the BaseTool interface.
"""

import os
from pathlib import Path
import subprocess
from typing import Any

from tools.base_tool import BaseTool, RiskLevel
from utils.logger import get_logger

logger = get_logger(__name__)


class TerminalTool(BaseTool):
    """Consolidated terminal execution tool with working directory persistence."""

    def __init__(self) -> None:
        """Initialize the TerminalTool, setting working directory state to current cwd."""
        self._cwd = os.getcwd()

    @property
    def name(self) -> str:
        return "terminal"

    @property
    def description(self) -> str:
        return (
            "Executes shell commands on the local machine and returns "
            "their outputs (stdout and stderr)."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The exact shell command to execute, e.g., 'git status' or 'dir'.",
                }
            },
            "required": ["command"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        # Default to HIGH risk. Overridden dynamically in PermissionGate for low-risk status commands.
        return RiskLevel.HIGH

    def execute(self, **kwargs: Any) -> str:
        command = kwargs.get("command", "").strip()
        if not command:
            return "Failure: No command provided."

        # Parse and intercept CWD directory changes
        parts = command.split()
        if parts and parts[0].lower() == "cd":
            # Extract target directory
            if len(parts) > 1:
                # Merge the remainder parts back to support spaces in directory names
                target_dir = command[3:].strip().strip('"').strip("'")
            else:
                target_dir = "~"

            # Resolve directory path
            if target_dir == "~":
                resolved_path = Path.home()
            else:
                # Resolve relative to current virtual CWD
                resolved_path = Path(self._cwd).joinpath(target_dir).resolve()

            if not resolved_path.exists():
                return f"Failure: Directory '{target_dir}' does not exist."
            if not resolved_path.is_dir():
                return f"Failure: Path '{target_dir}' is not a directory."

            # Persist the virtual CWD
            self._cwd = str(resolved_path)
            logger.info("Terminal working directory changed to: %s", self._cwd)
            return f"Success: Changed working directory to '{self._cwd}'."

        try:
            # Run command under subprocess using the persistent virtual CWD
            res = subprocess.run(
                command,
                shell=True,
                text=True,
                capture_output=True,
                cwd=self._cwd,
                timeout=30.0,
            )

            # Consolidate standard output and standard error results
            output = res.stdout
            if res.stderr:
                if output:
                    output += "\n" + res.stderr
                else:
                    output = res.stderr

            return output or "(No output returned)"

        except subprocess.TimeoutExpired:
            logger.warning("Command '%s' timed out after 30 seconds.", command)
            return "Failure: Command execution timed out after 30 seconds."
        except Exception as e:
            logger.exception("Error executing command '%s': %s", command, e)
            return f"Failure: Command execution failed: {e}"
