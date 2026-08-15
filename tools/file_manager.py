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
from core.conversation_context import get_conversation_context

logger = get_logger(__name__)


def get_desktop_path() -> Path:
    onedrive_desktop = Path(os.path.expanduser("~")) / "OneDrive" / "Desktop"
    if onedrive_desktop.exists():
        return onedrive_desktop
    return Path(os.path.expanduser("~")) / "Desktop"


def resolve_path(p: str) -> Path:
    """Resolve Path object safely with Desktop support and traversal protection."""
    p_str = str(p).strip()
    desktop_path = get_desktop_path()
    
    # Check if it refers to Desktop
    if p_str.lower().startswith("desktop/"):
        target = (desktop_path / p_str[8:]).resolve()
    elif p_str.lower().startswith("desktop\\"):
        target = (desktop_path / p_str[8:]).resolve()
    elif p_str.lower() == "desktop":
        target = desktop_path.resolve()
    elif "desktop" in p_str.lower() and not os.path.isabs(p_str):
        # E.g. "NovaProject on my Desktop" -> extract folder name
        import re
        m = re.search(r"([\w_-]+)\s+(?:on\s+my\s+desktop|on\s+desktop|in\s+desktop)", p_str, re.IGNORECASE)
        if m:
            folder_name = m.group(1)
            target = (desktop_path / folder_name).resolve()
        else:
            parts = Path(p_str).parts
            if "desktop" in [pt.lower() for pt in parts]:
                idx = [pt.lower() for pt in parts].index("desktop")
                rel = Path(*parts[idx+1:])
                target = (desktop_path / rel).resolve()
            else:
                target = Path(p_str).resolve()
    else:
        target = Path(p_str).resolve()

    # Traversal Protection
    workspace_root = Path(r"c:\Users\asus\OneDrive\Desktop\nova").resolve()
    allowed = False
    for root in (workspace_root, desktop_path, Path(os.path.expanduser("~")).resolve()):
        try:
            target.relative_to(root)
            allowed = True
            break
        except ValueError:
            continue
            
    if not allowed:
        if "temp" in str(target).lower() or "tmp" in str(target).lower():
            allowed = True
            
    if not allowed:
        raise ValueError(f"Path traversal detected: {p_str} resolved to {target} which is outside allowed paths.")
        
    return target


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
                        "open_file",
                        "open_folder",
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

    def execute(self, **kwargs: Any) -> "ActionResult":
        from core.action_result import ActionResult
        action = kwargs.get("action")
        if not action:
            return ActionResult(success=False, action="unknown", target="", error="No action provided.")

        try:
            if action == "create_folder":
                path = kwargs.get("path")
                if not path:
                    return ActionResult(success=False, action=action, target="", error="Missing parameter 'path'.")
                p = resolve_path(path)
                p.mkdir(parents=True, exist_ok=True)
                verified = p.is_dir()
                if verified:
                    ctx = get_conversation_context()
                    ctx.last_created_path = str(p)
                    ctx.last_folder = p.name
                return ActionResult(
                    success=verified,
                    action=action,
                    target=path,
                    details=f"Folder created at '{path}'." if verified else "Failed to create folder.",
                    error=None if verified else "Folder creation failed verification.",
                    verification={"exists": verified, "is_dir": verified}
                )

            elif action == "create_file":
                path = kwargs.get("path")
                if not path:
                    return ActionResult(success=False, action=action, target="", error="Missing parameter 'path'.")
                p = resolve_path(path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.touch()
                verified = p.is_file()
                if verified:
                    ctx = get_conversation_context()
                    ctx.last_created_path = str(p)
                    ctx.last_file = p.name
                return ActionResult(
                    success=verified,
                    action=action,
                    target=path,
                    details=f"File created at '{path}'." if verified else "Failed to create file.",
                    error=None if verified else "File touch failed verification.",
                    verification={"exists": verified, "is_file": verified}
                )

            elif action == "open_folder":
                path = kwargs.get("path")
                if not path:
                    return ActionResult(success=False, action=action, target="", error="Missing parameter 'path'.")
                p = resolve_path(path)
                if not p.is_dir():
                    return ActionResult(success=False, action=action, target=path, error=f"Path '{path}' is not a directory.")
                try:
                    if hasattr(os, "startfile"):
                        os.startfile(p)
                    # Verification: check path exists
                    verified = p.exists()
                    if verified:
                        ctx = get_conversation_context()
                        ctx.last_opened_path = str(p)
                        ctx.last_folder = p.name
                    return ActionResult(
                        success=verified,
                        action=action,
                        target=path,
                        details=f"Opened folder '{path}'.",
                        verification={"exists": verified, "opened": verified}
                    )
                except Exception as e:
                    return ActionResult(success=False, action=action, target=path, error=f"Failed to open folder: {e}")

            elif action == "open_file":
                path = kwargs.get("path")
                if not path:
                    return ActionResult(success=False, action=action, target="", error="Missing parameter 'path'.")
                p = resolve_path(path)
                if not p.is_file():
                    return ActionResult(success=False, action=action, target=path, error=f"Path '{path}' is not a file.")
                try:
                    if hasattr(os, "startfile"):
                        os.startfile(p)
                    # Verification: check path exists
                    verified = p.exists()
                    if verified:
                        ctx = get_conversation_context()
                        ctx.last_opened_path = str(p)
                        ctx.last_file = p.name
                    return ActionResult(
                        success=verified,
                        action=action,
                        target=path,
                        details=f"Opened file '{path}'.",
                        verification={"exists": verified, "opened": verified}
                    )
                except Exception as e:
                    return ActionResult(success=False, action=action, target=path, error=f"Failed to open file: {e}")

            elif action == "write":
                path = kwargs.get("path")
                content = kwargs.get("content")
                if not path or content is None:
                    return ActionResult(success=False, action=action, target="", error="Missing parameter 'path' or 'content'.")
                p = resolve_path(path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
                verified = p.is_file() and p.read_text(encoding="utf-8") == content
                return ActionResult(
                    success=verified,
                    action=action,
                    target=path,
                    details=f"Wrote content to file at '{path}'." if verified else "Failed to write file.",
                    error=None if verified else "File write verification failed.",
                    verification={"exists": verified, "is_file": verified, "content_match": verified}
                )

            elif action == "append":
                path = kwargs.get("path")
                content = kwargs.get("content")
                if not path or content is None:
                    return ActionResult(success=False, action=action, target="", error="Missing parameter 'path' or 'content'.")
                p = resolve_path(path)
                p.parent.mkdir(parents=True, exist_ok=True)
                orig_size = p.stat().st_size if p.exists() else 0
                with open(p, "a", encoding="utf-8") as f:
                    f.write(content)
                new_size = p.stat().st_size if p.exists() else 0
                verified = new_size > orig_size or len(content) == 0
                return ActionResult(
                    success=verified,
                    action=action,
                    target=path,
                    details=f"Appended content to file at '{path}'." if verified else "Failed to append.",
                    error=None if verified else "Append verification failed.",
                    verification={"size_increased": verified}
                )

            elif action == "read":
                path = kwargs.get("path")
                if not path:
                    return ActionResult(success=False, action=action, target="", error="Missing parameter 'path'.")
                p = resolve_path(path)
                if not p.is_file():
                    return ActionResult(success=False, action=action, target=path, error=f"Path '{path}' is not a file.")
                text = p.read_text(encoding="utf-8")
                return ActionResult(
                    success=True,
                    action=action,
                    target=path,
                    details=text,
                    verification={"is_file": True}
                )

            elif action == "list":
                path = kwargs.get("path") or "."
                p = resolve_path(path)
                if not p.is_dir():
                    return ActionResult(success=False, action=action, target=path, error=f"Path '{path}' is not a directory.")
                items = os.listdir(p)
                lines = []
                for item in items:
                    suffix = "/" if (p / item).is_dir() else ""
                    lines.append(f"  • {item}{suffix}")
                details = f"Directory contents of '{path}':\n" + "\n".join(lines) if items else f"Directory '{path}' is empty."
                return ActionResult(
                    success=True,
                    action=action,
                    target=path,
                    details=details,
                    verification={"is_dir": True, "item_count": len(items)}
                )

            elif action == "delete":
                path = kwargs.get("path")
                if not path:
                    return ActionResult(success=False, action=action, target="", error="Missing parameter 'path'.")
                p = resolve_path(path)
                if not p.exists():
                    return ActionResult(success=False, action=action, target=path, error=f"Path '{path}' does not exist.")
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
                verified = not p.exists()
                return ActionResult(
                    success=verified,
                    action=action,
                    target=path,
                    details=f"Deleted path at '{path}'." if verified else "Failed to delete.",
                    error=None if verified else "Delete operation failed verification.",
                    verification={"deleted": verified}
                )

            elif action == "rename":
                src = kwargs.get("src")
                dest = kwargs.get("dest")
                if not src or not dest:
                    return ActionResult(success=False, action=action, target="", error="Missing parameter 'src' or 'dest'.")
                src_path = resolve_path(src)
                dest_path = resolve_path(dest)
                if not src_path.exists():
                    return ActionResult(success=False, action=action, target=src, error=f"Source path '{src}' does not exist.")
                src_path.rename(dest_path)
                verified = dest_path.exists() and not src_path.exists()
                if verified:
                    ctx = get_conversation_context()
                    ctx.last_created_path = str(dest_path)
                    if dest_path.is_file():
                        ctx.last_file = dest_path.name
                    else:
                        ctx.last_folder = dest_path.name
                return ActionResult(
                    success=verified,
                    action=action,
                    target=dest,
                    details=f"Renamed '{src}' to '{dest}'." if verified else "Failed to rename.",
                    error=None if verified else "Rename verification failed.",
                    verification={"dest_exists": verified, "src_removed": verified}
                )

            elif action == "move":
                src = kwargs.get("src")
                dest = kwargs.get("dest")
                if not src or not dest:
                    return ActionResult(success=False, action=action, target="", error="Missing parameter 'src' or 'dest'.")
                src_path = resolve_path(src)
                dest_path = resolve_path(dest)
                if not src_path.exists():
                    return ActionResult(success=False, action=action, target=src, error=f"Source path '{src}' does not exist.")
                shutil.move(src_path, dest_path)
                verified = dest_path.exists() and not src_path.exists()
                return ActionResult(
                    success=verified,
                    action=action,
                    target=dest,
                    details=f"Moved '{src}' to '{dest}'." if verified else "Failed to move.",
                    error=None if verified else "Move verification failed.",
                    verification={"dest_exists": verified, "src_removed": verified}
                )

            elif action == "copy":
                src = kwargs.get("src")
                dest = kwargs.get("dest")
                if not src or not dest:
                    return ActionResult(success=False, action=action, target="", error="Missing parameter 'src' or 'dest'.")
                src_path = resolve_path(src)
                dest_path = resolve_path(dest)
                if not src_path.exists():
                    return ActionResult(success=False, action=action, target=src, error=f"Source path '{src}' does not exist.")
                if src_path.is_dir():
                    shutil.copytree(src_path, dest_path)
                else:
                    shutil.copy2(src_path, dest_path)
                verified = dest_path.exists()
                return ActionResult(
                    success=verified,
                    action=action,
                    target=dest,
                    details=f"Copied '{src}' to '{dest}'." if verified else "Failed to copy.",
                    error=None if verified else "Copy verification failed.",
                    verification={"dest_exists": verified}
                )

            else:
                return ActionResult(success=False, action=action, target="", error=f"Unsupported action '{action}'.")

        except Exception as e:
            logger.exception("Error in FileManagerTool execution for action '%s': %s", action, e)
            return ActionResult(
                success=False,
                action=action or "unknown",
                target=kwargs.get("path") or kwargs.get("src") or "",
                error=str(e)
            )
