"""
tools/file_manager.py
---------------------
Consolidated file manager tool supporting read, write, append, rename, copy, move, delete, list.
Conforms to the BaseTool interface.
"""

import os
from pathlib import Path
import shutil
from typing import Any

from tools.base_tool import BaseTool, RiskLevel
from utils.logger import get_logger

logger = get_logger(__name__)


def resolve_path(p: str) -> Path:
    """Resolve Path object safely."""
    return Path(p).resolve()


class FileManagerTool(BaseTool):
    """Consolidated file system management tool handling file/folder CRUD operations."""

    @property
    def name(self) -> str:
        return "file_manager"

    @property
    def description(self) -> str:
        return (
            "Performs file system operations like read, write, append, delete, "
            "rename, copy, move, and directory listing."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "create_file",
                        "create_folder",
                        "delete",
                        "rename",
                        "move",
                        "copy",
                        "read",
                        "write",
                        "append",
                        "list",
                    ],
                    "description": "The specific file system action to execute.",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Target folder or file path (required for create_file, "
                        "create_folder, delete, read, write, append, list)."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "String contents to write or append (required for write, append).",
                },
                "src": {
                    "type": "string",
                    "description": "Source path (required for rename, move, copy).",
                },
                "dest": {
                    "type": "string",
                    "description": "Destination path (required for rename, move, copy).",
                },
            },
            "required": ["action"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        # Defaults to HIGH. Overridden dynamically in PermissionGate for read/list actions.
        return RiskLevel.HIGH

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        if not action:
            return "Failure: No action provided."

        try:
            if action == "create_folder":
                path = kwargs.get("path")
                if not path:
                    return "Failure: Missing parameter 'path'."
                p = resolve_path(path)
                p.mkdir(parents=True, exist_ok=True)
                return f"Success: Folder created at '{path}'."

            elif action == "create_file":
                path = kwargs.get("path")
                if not path:
                    return "Failure: Missing parameter 'path'."
                p = resolve_path(path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.touch()
                return f"Success: File created at '{path}'."

            elif action == "write":
                path = kwargs.get("path")
                content = kwargs.get("content")
                if not path or content is None:
                    return "Failure: Missing parameter 'path' or 'content'."
                p = resolve_path(path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
                return f"Success: Wrote content to file at '{path}'."

            elif action == "append":
                path = kwargs.get("path")
                content = kwargs.get("content")
                if not path or content is None:
                    return "Failure: Missing parameter 'path' or 'content'."
                p = resolve_path(path)
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "a", encoding="utf-8") as f:
                    f.write(content)
                return f"Success: Appended content to file at '{path}'."

            elif action == "read":
                path = kwargs.get("path")
                if not path:
                    return "Failure: Missing parameter 'path'."
                p = resolve_path(path)
                if not p.is_file():
                    return f"Failure: Path '{path}' is not a file."
                return p.read_text(encoding="utf-8")

            elif action == "list":
                path = kwargs.get("path") or "."
                p = resolve_path(path)
                if not p.is_dir():
                    return f"Failure: Path '{path}' is not a directory."
                items = os.listdir(p)
                if not items:
                    return f"Directory '{path}' is empty."
                lines = []
                for item in items:
                    item_path = p / item
                    suffix = "/" if item_path.is_dir() else ""
                    lines.append(f"  • {item}{suffix}")
                return f"Directory contents of '{path}':\n" + "\n".join(lines)

            elif action == "delete":
                path = kwargs.get("path")
                if not path:
                    return "Failure: Missing parameter 'path'."
                p = resolve_path(path)
                if not p.exists():
                    return f"Failure: Path '{path}' does not exist."
                if p.is_dir():
                    shutil.rmtree(p)
                    return f"Success: Folder deleted recursively at '{path}'."
                else:
                    p.unlink()
                    return f"Success: File deleted at '{path}'."

            elif action == "rename":
                src = kwargs.get("src")
                dest = kwargs.get("dest")
                if not src or not dest:
                    return "Failure: Missing parameter 'src' or 'dest'."
                src_path = resolve_path(src)
                dest_path = resolve_path(dest)
                if not src_path.exists():
                    return f"Failure: Source path '{src}' does not exist."
                src_path.rename(dest_path)
                return f"Success: Renamed '{src}' to '{dest}'."

            elif action == "move":
                src = kwargs.get("src")
                dest = kwargs.get("dest")
                if not src or not dest:
                    return "Failure: Missing parameter 'src' or 'dest'."
                src_path = resolve_path(src)
                dest_path = resolve_path(dest)
                if not src_path.exists():
                    return f"Failure: Source path '{src}' does not exist."
                shutil.move(src_path, dest_path)
                return f"Success: Moved '{src}' to '{dest}'."

            elif action == "copy":
                src = kwargs.get("src")
                dest = kwargs.get("dest")
                if not src or not dest:
                    return "Failure: Missing parameter 'src' or 'dest'."
                src_path = resolve_path(src)
                dest_path = resolve_path(dest)
                if not src_path.exists():
                    return f"Failure: Source path '{src}' does not exist."
                if src_path.is_dir():
                    shutil.copytree(src_path, dest_path)
                else:
                    shutil.copy2(src_path, dest_path)
                return f"Success: Copied '{src}' to '{dest}'."

            else:
                return f"Failure: Unsupported action '{action}'."

        except Exception as e:
            logger.exception("Error in FileManagerTool execution for action '%s': %s", action, e)
            return f"Failure executing file action '{action}': {e}"
