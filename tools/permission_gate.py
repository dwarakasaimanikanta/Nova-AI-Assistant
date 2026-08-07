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
        effective_risk = tool.risk_level
        if tool.name == "file_manager":
            action = args.get("action")
            if action in ("read", "list"):
                effective_risk = RiskLevel.LOW
            else:
                effective_risk = RiskLevel.HIGH
        elif tool.name == "terminal":
            command = args.get("command", "").strip().lower()
            parts = command.split()
            base_cmd = parts[0] if parts else ""
            
            # Identify low-risk status and read-only commands
            low_risk_commands = {"pwd", "dir"}
            low_risk_git_subcommands = {"status", "log", "diff", "branch", "show"}
            
            if base_cmd == "git" and len(parts) > 1 and parts[1] in low_risk_git_subcommands:
                effective_risk = RiskLevel.LOW
            elif base_cmd in low_risk_commands:
                effective_risk = RiskLevel.LOW
            else:
                effective_risk = RiskLevel.HIGH
        elif tool.name == "system_control":
            action = args.get("action")
            if action == "launch_app":
                effective_risk = RiskLevel.LOW
            else:
                effective_risk = RiskLevel.HIGH
        elif tool.name == "code_helper":
            action = args.get("action")
            if action == "parse_code":
                effective_risk = RiskLevel.LOW
            else:
                effective_risk = RiskLevel.HIGH
        elif tool.name == "desktop_automation":
            action = args.get("action")
            if action in ("open_application", "search_files", "read_clipboard"):
                effective_risk = RiskLevel.LOW
            else:
                effective_risk = RiskLevel.HIGH
        elif tool.name == "browser_agent":
            action = args.get("action")
            if action in ("open_url", "search_google", "extract_text"):
                effective_risk = RiskLevel.LOW
            else:
                effective_risk = RiskLevel.HIGH
        elif tool.name == "calendar":
            action = args.get("action")
            if action == "list_events":
                effective_risk = RiskLevel.LOW
            else:
                effective_risk = RiskLevel.HIGH
        elif tool.name == "android":
            action = args.get("action", "")
            # call/sms/whatsapp/read_contacts are initiated by the user's own voice command
            # and are safe to auto-approve (LOW risk).
            # read_notifications accesses private device data and stays HIGH.
            if action in ("call", "sms", "whatsapp", "read_contacts"):
                effective_risk = RiskLevel.LOW
            else:
                effective_risk = RiskLevel.HIGH

        if effective_risk != RiskLevel.HIGH:
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
