"""
tools/permission_gate.py
-------------------------
Security middleware intercepting high-risk tool actions.
"""

from typing import Any, Callable

from tools.base_tool import BaseTool, RiskLevel
from utils.logger import get_logger

logger = get_logger(__name__)


class PermissionGate:
    """Intercepts tool executions and requests approval for hazardous actions."""

    def __init__(self, callback: Callable[[str, dict[str, Any]], bool] | None = None) -> None:
        """
        Initialize the PermissionGate.

        Args:
            callback: Optional Callable taking (tool_name, args) and returning boolean permission.
        """
        self._callback = callback

    def set_callback(self, callback: Callable[[str, dict[str, Any]], bool]) -> None:
        """
        Register a permission handler callback.

        Args:
            callback: Callable taking (tool_name, args) and returning bool.
        """
        self._callback = callback

    def check_permission(self, tool: BaseTool, args: dict[str, Any]) -> bool:
        """
        Evaluate if tool execution is permitted.

        Args:
            tool: The target BaseTool.
            args: The arguments passed to the tool.

        Returns:
            True if execution is permitted, False otherwise.
        """
        if tool.risk_level != RiskLevel.HIGH:
            # Low and Medium risk tools are approved automatically
            return True

        logger.warning("High-risk tool execution request detected: '%s'", tool.name)

        if self._callback:
            try:
                allowed = self._callback(tool.name, args)
                logger.info("Permission check result for tool '%s': %s", tool.name, allowed)
                return allowed
            except Exception as e:
                logger.exception("Error executing permission callback: %s", e)
                return False

        # If no callback is registered, deny High risk tools by default for security
        logger.error("No permission callback registered. High-risk tool '%s' execution denied.", tool.name)
        return False
