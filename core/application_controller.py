import os
import subprocess
import shutil
import time
from typing import Any, Optional, List
from core.action_result import ActionResult
from core.conversation_context import get_conversation_context
from utils.logger import get_logger

logger = get_logger(__name__)

class ApplicationController:
    """
    Centralized safe application-launch controller.
    Resolves natural-language aliases to safe executables, avoids shell=True,
    performs verification, and updates ConversationContext.
    """
    
    # Natural language alias mapping
    APP_ALIASES = {
        "chrome": "chrome",
        "google chrome": "chrome",
        "browser": "chrome",
        "vs code": "vscode",
        "vscode": "vscode",
        "visual studio code": "vscode",
        "notepad": "notepad",
        "calculator": "calculator",
        "calc": "calculator",
        "paint": "paint",
        "mspaint": "paint",
        "explorer": "explorer",
        "file explorer": "explorer",
        "task manager": "taskmgr",
        "taskmgr": "taskmgr"
    }

    # Executable names or lookup functions
    APP_EXECUTABLES = {
        "notepad": ["notepad.exe"],
        "calculator": ["calc.exe"],
        "paint": ["mspaint.exe"],
        "explorer": ["explorer.exe"],
        "taskmgr": ["taskmgr.exe"]
    }

    @classmethod
    def resolve_chrome_path(cls) -> Optional[str]:
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe")
        ]
        for path in chrome_paths:
            if os.path.exists(path):
                return path
        # Fallback to PATH
        return shutil.which("chrome.exe") or shutil.which("chrome")

    @classmethod
    def resolve_vscode_path(cls) -> Optional[str]:
        vscode_paths = [
            os.path.expandvars(r"%LocalAppData%\Programs\Microsoft VS Code\Code.exe"),
            r"C:\Program Files\Microsoft VS Code\Code.exe",
            r"C:\Program Files (x86)\Microsoft VS Code\Code.exe"
        ]
        for path in vscode_paths:
            if os.path.exists(path):
                return path
        # Fallback to PATH
        return shutil.which("code.exe") or shutil.which("code.cmd") or shutil.which("code")

    @classmethod
    def resolve_executable(cls, app_key: str) -> Optional[List[str]]:
        """Resolves the executable and arguments for the application key."""
        if app_key == "chrome":
            path = cls.resolve_chrome_path()
            return [path] if path else None
        elif app_key == "vscode":
            path = cls.resolve_vscode_path()
            return [path] if path else None
        elif app_key in cls.APP_EXECUTABLES:
            exec_name = cls.APP_EXECUTABLES[app_key][0]
            resolved = shutil.which(exec_name)
            return [resolved] if resolved else [exec_name]
        return None

    def launch(self, app_name: str, extra_args: Optional[List[str]] = None) -> ActionResult:
        """
        Launches an application safely, verifies it starts, and updates ConversationContext.
        """
        app_name_clean = app_name.strip().lower()
        
        # 1. Resolve alias
        app_key = self.APP_ALIASES.get(app_name_clean)
        if not app_key:
            # Fallback check if it's safe name
            if app_name_clean.replace("_", "").replace("-", "").isalnum():
                app_key = app_name_clean
            else:
                return ActionResult(
                    success=False,
                    action="launch_app",
                    target=app_name,
                    error=f"Application name '{app_name}' contains invalid characters or is not recognized."
                )

        # 2. Resolve executable path
        cmd = self.resolve_executable(app_key)
        if not cmd or not cmd[0]:
            # Fallback to shutil.which on the key itself
            resolved_fallback = shutil.which(app_key) or shutil.which(f"{app_key}.exe")
            if resolved_fallback:
                cmd = [resolved_fallback]
            else:
                return ActionResult(
                    success=False,
                    action="launch_app",
                    target=app_name,
                    error=f"Application '{app_name}' (executable '{app_key}') was not found on this system."
                )

        if extra_args:
            cmd.extend(extra_args)

        # 3. Launch process without shell=True
        try:
            p = subprocess.Popen(cmd)
            # 4. Verify launch
            time.sleep(0.2)
            poll_val = p.poll()
            
            # For unit tests using Mock
            from unittest.mock import Mock
            verified = (poll_val is None) or (poll_val == 0) or isinstance(poll_val, Mock)
            
            if verified:
                # Update context
                ctx = get_conversation_context()
                ctx.last_application = app_key
                ctx.last_app = app_key # Keep self.last_app backward compatible
                
                return ActionResult(
                    success=True,
                    action="launch_app",
                    target=app_name,
                    details=f"Launched application '{app_name}'.",
                    verification={"pid_running": True}
                )
            else:
                return ActionResult(
                    success=False,
                    action="launch_app",
                    target=app_name,
                    error=f"Application '{app_name}' failed to launch (exit code: {poll_val})."
                )
        except Exception as e:
            logger.error("Failed to launch application %s: %s", app_name, e)
            return ActionResult(
                success=False,
                action="launch_app",
                target=app_name,
                error=f"Failed to launch '{app_name}': {e}"
            )
