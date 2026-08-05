"""
tools/builtin_tools.py
----------------------
Ported built-in system tools for Nova, conforming to the BaseTool interface.
"""

from datetime import datetime
import os
import platform
import re
from typing import Any

from tools.base_tool import BaseTool, RiskLevel
from utils.logger import get_logger

logger = get_logger(__name__)


class CalculateTool(BaseTool):
    """A tool that evaluates basic arithmetic calculations (+, -, *, /)."""

    @property
    def name(self) -> str:
        return "calculate_expression"

    @property
    def description(self) -> str:
        return (
            "Safely evaluates a basic mathematical calculation expression. "
            "Supports standard operators +, -, *, /, parenthesis (), and decimals."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "The mathematical expression to evaluate, e.g., '2.5 * (10 - 3)'",
                }
            },
            "required": ["expression"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    def execute(self, **kwargs: Any) -> str:
        expr = kwargs.get("expression", "").strip()
        if not expr:
            return "Error: Empty expression passed."

        # Validate that characters are strictly mathematical
        if not re.match(r"^[\d\s\+\-\*/\(\)\.]+$", expr):
            logger.warning("Rejected CalculateTool expression: '%s' due to invalid characters.", expr)
            return "Error: Expression contains invalid characters. Only numbers and +, -, *, / are supported."

        try:
            # Safe evaluation with isolated environment (no built-ins)
            result = eval(expr, {"__builtins__": None}, {})
            logger.info("Successfully evaluated expression: %s = %s", expr, result)
            return f"{expr} = {result}"
        except ZeroDivisionError:
            logger.warning("Zero division error in expression: %s", expr)
            return "Error: Division by zero is not allowed."
        except Exception as e:
            logger.warning("Failed to evaluate expression: %s, error: %s", expr, e)
            return f"Error: Invalid arithmetic expression. Details: {e}"


class TimeTool(BaseTool):
    """A tool that provides the current system date and time."""

    @property
    def name(self) -> str:
        return "get_system_time"

    @property
    def description(self) -> str:
        return "Returns the current system date and time."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    def execute(self, **kwargs: Any) -> str:
        logger.debug("Executing TimeTool.")
        now = datetime.now()
        formatted_now = now.strftime("%Y-%m-%d %H:%M:%S")
        return f"The current date and time is {formatted_now}."


class SystemInfoTool(BaseTool):
    """A tool that details OS, Python version, and the current working directory."""

    @property
    def name(self) -> str:
        return "get_system_info"

    @property
    def description(self) -> str:
        return "Shows operating system, Python version and current working directory."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    def execute(self, **kwargs: Any) -> str:
        logger.debug("Executing SystemInfoTool.")
        os_name = platform.system()
        os_release = platform.release()
        python_ver = platform.python_version()
        cwd = os.getcwd()

        response = (
            "System Information:\n"
            f"  • Operating System : {os_name} {os_release}\n"
            f"  • Python Version   : {python_ver}\n"
            f"  • Working Directory: {cwd}"
        )
        return response
