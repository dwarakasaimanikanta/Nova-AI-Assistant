"""
tools/desktop_automation_tool.py
--------------------------------
Desktop automation tool supporting mouse control, keyboard inputs, application management,
clipboard operations, and filesystem CRUD operations.
Conforms to the BaseTool interface.
"""

from typing import Any, Optional
from tools.base_tool import BaseTool, RiskLevel
from utils.desktop_automation_manager import DesktopAutomationManager
from utils.logger import get_logger

logger = get_logger(__name__)


class DesktopAutomationTool(BaseTool):
    """System-level automation tool exposing mouse, keyboard, and OS controls."""

    def __init__(self, manager: Optional[DesktopAutomationManager] = None) -> None:
        self.manager = manager or DesktopAutomationManager()

    @property
    def name(self) -> str:
        return "desktop_automation"

    @property
    def description(self) -> str:
        return (
            "Performs system-level desktop automation actions. "
            "Supported actions: "
            "action='move_mouse' (requires x, y), "
            "action='click_mouse' (optional x, y, button, clicks), "
            "action='type_text' (requires text), "
            "action='press_hotkey' (requires keys list), "
            "action='read_clipboard', "
            "action='write_clipboard' (requires text), "
            "action='open_application' (requires command_or_path; do NOT use this for notepad, calculator, paint, explorer, task manager, calendar, chrome, or google chrome. Use system_control launch_app instead), "
            "action='close_application' (requires process_name_or_pid), "
            "action='focus_window' (requires window_title), "
            "action='create_folder' (requires folder_path), "
            "action='move_file' (requires src, dst), "
            "action='copy_file' (requires src, dst), "
            "action='delete_file' (requires file_path), "
            "action='search_files' (requires directory, pattern)."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "move_mouse", "click_mouse", "type_text", "press_hotkey",
                        "read_clipboard", "write_clipboard",
                        "open_application", "close_application", "focus_window",
                        "create_folder", "move_file", "copy_file", "delete_file", "search_files"
                    ],
                    "description": "The desktop automation action to execute.",
                },
                "x": {
                    "type": "integer",
                    "description": "X screen coordinate.",
                },
                "y": {
                    "type": "integer",
                    "description": "Y screen coordinate.",
                },
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "middle"],
                    "description": "Mouse button (default: left)."
                },
                "clicks": {
                    "type": "integer",
                    "description": "Number of mouse clicks (default: 1)."
                },
                "text": {
                    "type": "string",
                    "description": "Text content to write or type.",
                },
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of key names for hotkey combinations (e.g. ['ctrl', 'alt', 'del']).",
                },
                "command_or_path": {
                    "type": "string",
                    "description": "Application startup filepath or shell command (required for open_application).",
                },
                "process_name_or_pid": {
                    "type": "string",
                    "description": "Target PID integer or executable name (required for close_application).",
                },
                "window_title": {
                    "type": "string",
                    "description": "Window title search substring (required for focus_window).",
                },
                "folder_path": {
                    "type": "string",
                    "description": "Target folder directory path (required for create_folder).",
                },
                "src": {
                    "type": "string",
                    "description": "Source file or directory path (required for move_file/copy_file).",
                },
                "dst": {
                    "type": "string",
                    "description": "Destination file or directory path (required for move_file/copy_file).",
                },
                "file_path": {
                    "type": "string",
                    "description": "Target path to delete (required for delete_file).",
                },
                "directory": {
                    "type": "string",
                    "description": "File search start directory (required for search_files).",
                },
                "pattern": {
                    "type": "string",
                    "description": "File search glob pattern filter (required for search_files, e.g. '*.txt').",
                },
            },
            "required": ["action"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        # Base risk level is HIGH since this tool has the ability to click, type, and modify files.
        # PermissionGate evaluates the specific action dynamically to distinguish between LOW and HIGH.
        return RiskLevel.HIGH

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        if not action:
            return "Failure: Missing parameter 'action'."

        try:
            if action == "move_mouse":
                x, y = kwargs.get("x"), kwargs.get("y")
                if x is None or y is None:
                    return "Failure: Coordinates 'x' and 'y' are required for move_mouse."
                return self.manager.move_mouse(x, y)

            elif action == "click_mouse":
                x, y = kwargs.get("x"), kwargs.get("y")
                button = kwargs.get("button", "left")
                clicks = kwargs.get("clicks", 1)
                return self.manager.click_mouse(x, y, button, clicks)

            elif action == "type_text":
                text = kwargs.get("text")
                if text is None:
                    return "Failure: Parameter 'text' is required for type_text."
                return self.manager.type_text(text)

            elif action == "press_hotkey":
                keys = kwargs.get("keys")
                if not keys:
                    return "Failure: Parameter 'keys' list is required for press_hotkey."
                return self.manager.press_hotkey(keys)

            elif action == "read_clipboard":
                return self.manager.read_clipboard()

            elif action == "write_clipboard":
                text = kwargs.get("text")
                if text is None:
                    return "Failure: Parameter 'text' is required for write_clipboard."
                return self.manager.write_clipboard(text)

            elif action == "open_application":
                cmd = kwargs.get("command_or_path")
                if not cmd:
                    return "Failure: Parameter 'command_or_path' is required for open_application."
                return self.manager.open_application(cmd)

            elif action == "close_application":
                proc = kwargs.get("process_name_or_pid")
                if not proc:
                    return "Failure: Parameter 'process_name_or_pid' is required for close_application."
                return self.manager.close_application(proc)

            elif action == "focus_window":
                title = kwargs.get("window_title")
                if not title:
                    return "Failure: Parameter 'window_title' is required for focus_window."
                return self.manager.focus_window(title)

            elif action == "create_folder":
                path = kwargs.get("folder_path")
                if not path:
                    return "Failure: Parameter 'folder_path' is required for create_folder."
                return self.manager.create_folder(path)

            elif action == "move_file":
                src, dst = kwargs.get("src"), kwargs.get("dst")
                if not src or not dst:
                    return "Failure: Both 'src' and 'dst' parameters are required for move_file."
                return self.manager.move_file(src, dst)

            elif action == "copy_file":
                src, dst = kwargs.get("src"), kwargs.get("dst")
                if not src or not dst:
                    return "Failure: Both 'src' and 'dst' parameters are required for copy_file."
                return self.manager.copy_file(src, dst)

            elif action == "delete_file":
                path = kwargs.get("file_path")
                if not path:
                    return "Failure: Parameter 'file_path' is required for delete_file."
                return self.manager.delete_file(path)

            elif action == "search_files":
                directory = kwargs.get("directory")
                pattern = kwargs.get("pattern")
                if not directory or not pattern:
                    return "Failure: Both 'directory' and 'pattern' parameters are required for search_files."
                return self.manager.search_files(directory, pattern)

            else:
                return f"Failure: Unsupported automation action '{action}'."

        except Exception as e:
            logger.error("DesktopAutomationTool execute error: %s", e)
            return f"Failure: Desktop automation execution error: {e}"
