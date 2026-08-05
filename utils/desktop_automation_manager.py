"""
utils/desktop_automation_manager.py
-----------------------------------
DesktopAutomationManager implements cross-platform UI automation operations (mouse, keyboard, clipboard)
via pyautogui/pyperclip, launches/closes application subprocesses, focuses foreground window controls
on Windows using pywin32, and handles filesystem CRUD operations.
"""

import os
import shutil
import subprocess
import sys
import fnmatch
from pathlib import Path
from typing import Any, List, Dict, Optional, Tuple
from utils.logger import get_logger

logger = get_logger(__name__)

try:
    import pyautogui
    # Configure safety fail-safe to trigger on moving mouse to corner
    pyautogui.FAILSAFE = True
except ImportError:
    pyautogui = None

try:
    import pyperclip
except ImportError:
    pyperclip = None


class DesktopAutomationManager:
    """Core manager wrapping system-level input controls, process lifecycles, and filesystem actions."""

    # --- Mouse Controls ---

    def move_mouse(self, x: int, y: int) -> str:
        """Moves mouse pointer to (x, y) coordinates."""
        if not pyautogui:
            return "Failure: pyautogui is not installed."
        try:
            pyautogui.moveTo(x, y)
            logger.info("Moved mouse to (%d, %d)", x, y)
            return f"Success: Moved mouse to ({x}, {y})."
        except Exception as e:
            logger.error("Failed mouse move: %s", e)
            return f"Failure: Mouse move error: {e}"

    def click_mouse(self, x: Optional[int] = None, y: Optional[int] = None, button: str = "left", clicks: int = 1) -> str:
        """Triggers left, right, or double clicks. Optionally moves to (x, y) first."""
        if not pyautogui:
            return "Failure: pyautogui is not installed."
        try:
            if x is not None and y is not None:
                pyautogui.moveTo(x, y)
            
            pyautogui.click(button=button, clicks=clicks)
            logger.info("Clicked mouse: %s at current location %s times", button, clicks)
            return f"Success: Clicked '{button}' button {clicks} times."
        except Exception as e:
            logger.error("Failed mouse click: %s", e)
            return f"Failure: Mouse click error: {e}"

    # --- Keyboard Controls ---

    def type_text(self, text: str) -> str:
        """Types string text input at the active focus cursor."""
        if not pyautogui:
            return "Failure: pyautogui is not installed."
        try:
            pyautogui.write(text, interval=0.01)
            logger.info("Typed text: %s", text)
            return "Success: Text typed successfully."
        except Exception as e:
            logger.error("Failed to type text: %s", e)
            return f"Failure: Keyboard typing error: {e}"

    def press_hotkey(self, keys: List[str]) -> str:
        """Presses key combination hotkeys (e.g. ['ctrl', 'c'])."""
        if not pyautogui:
            return "Failure: pyautogui is not installed."
        try:
            pyautogui.hotkey(*keys)
            logger.info("Pressed hotkey combination: %s", keys)
            return f"Success: Hotkey combination {keys} pressed."
        except Exception as e:
            logger.error("Failed to press hotkey: %s", e)
            return f"Failure: Hotkey combination error: {e}"

    # --- Clipboard Controls ---

    def read_clipboard(self) -> str:
        """Reads contents copied in the system clipboard."""
        if not pyperclip:
            return "Failure: pyperclip is not installed."
        try:
            text = pyperclip.paste()
            return text or "(Clipboard is empty)"
        except Exception as e:
            logger.error("Failed to read clipboard: %s", e)
            return f"Failure: Clipboard read error: {e}"

    def write_clipboard(self, text: str) -> str:
        """Copies text onto the system clipboard."""
        if not pyperclip:
            return "Failure: pyperclip is not installed."
        try:
            pyperclip.copy(text)
            logger.info("Copied text to clipboard.")
            return "Success: Text copied to clipboard."
        except Exception as e:
            logger.error("Failed to write clipboard: %s", e)
            return f"Failure: Clipboard write error: {e}"

    # --- Process and Window Controls ---

    def open_application(self, command_or_path: str) -> str:
        """Launches an application process in the background."""
        try:
            # Spawns process asynchronously
            proc = subprocess.Popen(command_or_path, shell=True)
            logger.info("Opened application: %s (PID: %d)", command_or_path, proc.pid)
            return f"Success: Application launched successfully (PID: {proc.pid})."
        except Exception as e:
            logger.error("Failed to open application '%s': %s", command_or_path, e)
            return f"Failure: Open application error: {e}"

    def close_application(self, process_name_or_pid: str) -> str:
        """Terminates an application process."""
        try:
            # Check if PID or name
            if process_name_or_pid.isdigit():
                pid = int(process_name_or_pid)
                if sys.platform == "win32":
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, check=True)
                else:
                    os.kill(pid, 15)
                logger.info("Closed application with PID: %d", pid)
                return f"Success: Application with PID {pid} has been closed."
            else:
                # Close by process image name
                name = process_name_or_pid
                if sys.platform == "win32":
                    # Ensure suffix .exe is appended if missing
                    if not name.lower().endswith(".exe"):
                        name += ".exe"
                    subprocess.run(f"taskkill /F /IM {name}", shell=True, check=True)
                else:
                    subprocess.run(f"pkill -f {name}", shell=True, check=True)
                logger.info("Closed application with process name: %s", name)
                return f"Success: Application process '{name}' has been closed."
        except Exception as e:
            logger.error("Failed to close application '%s': %s", process_name_or_pid, e)
            return f"Failure: Close application error: {e}"

    def focus_window(self, window_title: str) -> str:
        """Brings an existing window to the foreground on Windows."""
        if sys.platform != "win32":
            return "Failure: Window focus is only supported on Windows platform."

        try:
            import win32gui
            import win32con

            hwnd_list = []
            
            # Find matching window title substring
            def enum_window_callback(hwnd, extra):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if window_title.lower() in title.lower():
                        hwnd_list.append((hwnd, title))

            win32gui.EnumWindows(enum_window_callback, None)

            if not hwnd_list:
                return f"Failure: No window found containing title: '{window_title}'."

            # Fetch the first match
            hwnd, title = hwnd_list[0]
            
            # If minimized, restore it
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                
            win32gui.SetForegroundWindow(hwnd)
            logger.info("Brought window '%s' to foreground.", title)
            return f"Success: Window '{title}' focused successfully."
        except Exception as e:
            logger.error("Failed to focus window '%s': %s", window_title, e)
            return f"Failure: Focus window error: {e}"

    # --- Filesystem CRUD Operations ---

    def create_folder(self, folder_path: str) -> str:
        """Create folder directory."""
        try:
            path = Path(folder_path).resolve()
            path.mkdir(parents=True, exist_ok=True)
            logger.info("Created folder: %s", path)
            return f"Success: Folder created at '{path}'."
        except Exception as e:
            logger.error("Failed to create folder '%s': %s", folder_path, e)
            return f"Failure: Create folder error: {e}"

    def move_file(self, src: str, dst: str) -> str:
        """Moves a file or folder directory."""
        try:
            src_path = Path(src).resolve()
            dst_path = Path(dst).resolve()
            shutil.move(str(src_path), str(dst_path))
            logger.info("Moved file from %s to %s", src_path, dst_path)
            return f"Success: Moved file from '{src_path}' to '{dst_path}'."
        except Exception as e:
            logger.error("Failed to move file from '%s' to '%s': %s", src, dst, e)
            return f"Failure: Move file error: {e}"

    def copy_file(self, src: str, dst: str) -> str:
        """Copies a file or folder directory."""
        try:
            src_path = Path(src).resolve()
            dst_path = Path(dst).resolve()
            
            if src_path.is_dir():
                shutil.copytree(str(src_path), str(dst_path), dirs_exist_ok=True)
            else:
                shutil.copy2(str(src_path), str(dst_path))
                
            logger.info("Copied file from %s to %s", src_path, dst_path)
            return f"Success: Copied file from '{src_path}' to '{dst_path}'."
        except Exception as e:
            logger.error("Failed to copy file from '%s' to '%s': %s", src, dst, e)
            return f"Failure: Copy file error: {e}"

    def delete_file(self, file_path: str) -> str:
        """Deletes a file or directory tree recursively."""
        try:
            path = Path(file_path).resolve()
            if not path.exists():
                return f"Failure: Target path '{path}' does not exist."

            if path.is_dir():
                shutil.rmtree(path)
                logger.info("Deleted directory: %s", path)
                return f"Success: Folder '{path}' deleted recursively."
            else:
                path.unlink()
                logger.info("Deleted file: %s", path)
                return f"Success: File '{path}' deleted successfully."
        except Exception as e:
            logger.error("Failed to delete path '%s': %s", file_path, e)
            return f"Failure: Delete file error: {e}"

    def search_files(self, directory: str, pattern: str) -> str:
        """Searches files by glob name patterns recursively."""
        try:
            search_dir = Path(directory).resolve()
            if not search_dir.exists() or not search_dir.is_dir():
                return f"Failure: Search directory '{search_dir}' is invalid."

            matches = []
            for root, _, files in os.walk(search_dir):
                for filename in fnmatch.filter(files, pattern):
                    matches.append(str(Path(root) / filename))

            if not matches:
                return f"No files matching '{pattern}' in directory '{search_dir}'."

            lines = [f"Found {len(matches)} files matching '{pattern}':"]
            for m in matches[:50]:  # Limit output log lines
                lines.append(f"- {m}")
            if len(matches) > 50:
                lines.append(f"...and {len(matches) - 50} more matches.")
            return "\n".join(lines)
        except Exception as e:
            logger.error("Failed to search files in '%s' with pattern '%s': %s", directory, pattern, e)
            return f"Failure: Search files error: {e}"
