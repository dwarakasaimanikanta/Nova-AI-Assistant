"""
tests/test_desktop_automation.py
--------------------------------
Unit tests for the Desktop Automation tool and security permissions gate.
Fully mocked to ensure headless execution without requiring GUI coordinates or windows platforms.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from tools.desktop_automation_tool import DesktopAutomationTool
from utils.desktop_automation_manager import DesktopAutomationManager
from tools.permission_gate import PermissionGate
from tools.base_tool import RiskLevel


@pytest.fixture
def mock_automation_manager():
    """Returns a mock DesktopAutomationManager."""
    return MagicMock(spec=DesktopAutomationManager)


@pytest.fixture
def real_manager_with_mocks():
    """Sets up a real manager with underlying pyautogui/pyperclip mocks."""
    with patch("utils.desktop_automation_manager.pyautogui") as mock_pyauto, \
         patch("utils.desktop_automation_manager.pyperclip") as mock_clip, \
         patch("utils.desktop_automation_manager.subprocess.Popen") as mock_popen, \
         patch("utils.desktop_automation_manager.subprocess.run") as mock_run:
         
        manager = DesktopAutomationManager()
        yield manager, mock_pyauto, mock_clip, mock_popen, mock_run


def test_manager_mouse_and_keys(real_manager_with_mocks) -> None:
    """Manager: verify mouse movements, clicks, typing, and hotkeys call pyautogui."""
    manager, mock_pyauto, _, _, _ = real_manager_with_mocks

    # 1. Mouse move
    res = manager.move_mouse(100, 200)
    assert "Success" in res
    mock_pyauto.moveTo.assert_called_with(100, 200)

    # 2. Mouse click
    res = manager.click_mouse(150, 250, button="right", clicks=2)
    assert "Success" in res
    mock_pyauto.moveTo.assert_called_with(150, 250)
    mock_pyauto.click.assert_called_with(button="right", clicks=2)

    # 3. Type text
    res = manager.type_text("Hello World")
    assert "Success" in res
    mock_pyauto.write.assert_called_with("Hello World", interval=0.01)

    # 4. Press hotkey
    res = manager.press_hotkey(["ctrl", "v"])
    assert "Success" in res
    mock_pyauto.hotkey.assert_called_with("ctrl", "v")


def test_manager_clipboard_and_apps(real_manager_with_mocks) -> None:
    """Manager: verify clipboard copy/paste and process spawning actions."""
    manager, _, mock_clip, mock_popen, mock_run = real_manager_with_mocks

    # 1. Clipboard write
    res = manager.write_clipboard("copied text data")
    assert "Success" in res
    mock_clip.copy.assert_called_with("copied text data")

    # 2. Clipboard read
    mock_clip.paste.return_value = "clipboard content"
    res = manager.read_clipboard()
    assert res == "clipboard content"

    # 3. Open application
    mock_popen.return_value.pid = 9988
    res = manager.open_application("notepad.exe")
    assert "Success" in res
    assert "9988" in res

    # 4. Close application (PID)
    with patch("sys.platform", "win32"):
        res = manager.close_application("9988")
        assert "Success" in res
        mock_run.assert_called_with("taskkill /F /PID 9988", shell=True, check=True)


def test_tool_routing(mock_automation_manager) -> None:
    """Tool: verify action arguments are correctly mapped and forwarded to the manager."""
    tool = DesktopAutomationTool(manager=mock_automation_manager)

    # test move_mouse
    tool.execute(action="move_mouse", x=400, y=300)
    mock_automation_manager.move_mouse.assert_called_with(400, 300)

    # test type_text
    tool.execute(action="type_text", text="automation text")
    mock_automation_manager.type_text.assert_called_with("automation text")

    # test search_files
    tool.execute(action="search_files", directory="C:\\data", pattern="*.log")
    mock_automation_manager.search_files.assert_called_with("C:\\data", "*.log")


def test_permission_gate_evaluations() -> None:
    """Security: verify gate permits LOW risk actions automatically and queries callback for HIGH risk."""
    tool = DesktopAutomationTool()
    callback_mock = MagicMock(return_value=True)
    gate = PermissionGate(callback=callback_mock)

    # 1. Verify LOW-risk action automatically approved (callback not called)
    assert gate.check_permission(tool, {"action": "read_clipboard"}) is True
    callback_mock.assert_not_called()

    assert gate.check_permission(tool, {"action": "search_files", "directory": ".", "pattern": "*.txt"}) is True
    callback_mock.assert_not_called()

    # 2. Verify HIGH-risk action calls the gate callback
    callback_mock.reset_mock()
    assert gate.check_permission(tool, {"action": "delete_file", "file_path": "secret.txt"}) is True
    callback_mock.assert_called_once_with("desktop_automation", {"action": "delete_file", "file_path": "secret.txt"})

    callback_mock.return_value = False
    assert gate.check_permission(tool, {"action": "type_text", "text": "typing"}) is False
