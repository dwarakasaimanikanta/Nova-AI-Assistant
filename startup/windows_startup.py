"""
startup/windows_startup.py
--------------------------
Handles Windows Registry startup registration and query actions.
"""

import sys
import winreg
from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)

REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "NovaAIAssistant"


class WindowsStartup:
    """Manages system startup configuration for Nova via Windows Registry."""

    def register(self) -> bool:
        """Register the Nova background process to run at Windows startup."""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE)
            executable = sys.executable
            script_path = Path(__file__).parent.parent / "main.py"
            # Command to launch Python with main script in background mode
            cmd = f'"{executable}" "{script_path.resolve()}" --background'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
            winreg.CloseKey(key)
            logger.info("Successfully registered Nova in Windows Startup Registry.")
            return True
        except Exception as e:
            logger.error("Failed to register Nova in Windows Startup: %s", e)
            return False

    def remove(self) -> bool:
        """Remove Nova from the Windows Startup Registry."""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, APP_NAME)
            winreg.CloseKey(key)
            logger.info("Successfully removed Nova from Windows Startup Registry.")
            return True
        except FileNotFoundError:
            return True
        except Exception as e:
            logger.error("Failed to remove Nova from Windows Startup: %s", e)
            return False

    def is_registered(self) -> bool:
        """Query if Nova is currently registered in Windows Startup Registry."""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, APP_NAME)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            return False
        except Exception as e:
            logger.error("Failed to check Windows Startup status: %s", e)
            return False

    def enable(self) -> bool:
        return self.register()

    def disable(self) -> bool:
        return self.remove()
