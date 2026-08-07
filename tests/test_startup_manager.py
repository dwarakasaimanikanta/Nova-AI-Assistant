"""
tests/test_startup_manager.py
-----------------------------
Unit tests verifying the StartupManager registration, unregistration, mode detection, and error handling.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import config
from core.startup_manager import StartupManager


def test_is_auto_start_registered_non_windows():
    """Verify is_auto_start_registered returns False and skips check on non-Windows platforms."""
    with patch("sys.platform", "linux"):
        manager = StartupManager()
        assert manager.is_auto_start_registered() is False


def test_is_auto_start_registered_windows_found():
    """Verify is_auto_start_registered returns True when winreg QueryValueEx succeeds on Windows."""
    mock_key = MagicMock()
    with patch("sys.platform", "win32"), \
         patch("winreg.OpenKey", return_value=mock_key), \
         patch("winreg.QueryValueEx", return_value=("cmd --minimized", 1)):
        manager = StartupManager()
        assert manager.is_auto_start_registered() is True


def test_is_auto_start_registered_windows_missing():
    """Verify is_auto_start_registered returns False when winreg QueryValueEx raises FileNotFoundError."""
    mock_key = MagicMock()
    with patch("sys.platform", "win32"), \
         patch("winreg.OpenKey", return_value=mock_key), \
         patch("winreg.QueryValueEx", side_effect=FileNotFoundError):
        manager = StartupManager()
        assert manager.is_auto_start_registered() is False


def test_register_auto_start_non_windows():
    """Verify register_auto_start returns False and does nothing on non-Windows platforms."""
    with patch("sys.platform", "darwin"):
        manager = StartupManager()
        assert manager.register_auto_start() is False


def test_register_auto_start_windows_success():
    """Verify register_auto_start writes the correct command line and flags to the registry key."""
    mock_key = MagicMock()
    with patch("sys.platform", "win32"), \
         patch("winreg.OpenKey", return_value=mock_key), \
         patch("winreg.SetValueEx") as mock_set_val, \
         patch("sys.executable", "python.exe"):
        manager = StartupManager()
        assert manager.register_auto_start() is True
        mock_set_val.assert_called_once()
        args = mock_set_val.call_args[0]
        # First arg is key, second is value name, third is reserved, fourth is type, fifth is the string command
        assert args[0] == mock_key.__enter__()
        assert args[1] == "NovaAIAssistant"
        assert args[4].endswith("--minimized")


def test_unregister_auto_start_non_windows():
    """Verify unregister_auto_start returns False and does nothing on non-Windows platforms."""
    with patch("sys.platform", "linux"):
        manager = StartupManager()
        assert manager.unregister_auto_start() is False


def test_unregister_auto_start_windows_success():
    """Verify unregister_auto_start deletes the correct value from the registry."""
    mock_key = MagicMock()
    with patch("sys.platform", "win32"), \
         patch("winreg.OpenKey", return_value=mock_key), \
         patch("winreg.DeleteValue") as mock_delete_val:
        manager = StartupManager()
        assert manager.unregister_auto_start() is True
        mock_delete_val.assert_called_once_with(mock_key.__enter__(), "NovaAIAssistant")


def test_detect_startup_mode_auto():
    """Verify detect_startup_mode returns 'auto' when --minimized argument is present."""
    with patch.object(sys, "argv", ["main.py", "--minimized"]):
        manager = StartupManager()
        assert manager.detect_startup_mode() == "auto"


def test_detect_startup_mode_manual():
    """Verify detect_startup_mode returns 'manual' when --minimized argument is absent."""
    with patch.object(sys, "argv", ["main.py", "--gui"]):
        manager = StartupManager()
        assert manager.detect_startup_mode() == "manual"


def test_initialize_startup_register_if_needed():
    """Verify initialize_startup registers auto-start if configuration is enabled and not registered."""
    with patch("config.AUTO_START", True), \
         patch.object(StartupManager, "is_auto_start_registered", return_value=False) as mock_check, \
         patch.object(StartupManager, "register_auto_start") as mock_register:
        manager = StartupManager()
        manager.initialize_startup()
        mock_check.assert_called_once()
        mock_register.assert_called_once()


def test_initialize_startup_unregister_if_needed():
    """Verify initialize_startup unregisters auto-start if configuration is disabled and registered."""
    with patch("config.AUTO_START", False), \
         patch.object(StartupManager, "is_auto_start_registered", return_value=True) as mock_check, \
         patch.object(StartupManager, "unregister_auto_start") as mock_unregister:
        manager = StartupManager()
        manager.initialize_startup()
        mock_check.assert_called_once()
        mock_unregister.assert_called_once()


def test_run_lifecycle_success():
    """Verify run_lifecycle succeeds, matches deterministic order, and generates a valid report."""
    mock_args = MagicMock()
    mock_args.gui = False
    
    manager = StartupManager()
    
    # We patch the imports inside run_lifecycle to return dummies
    with patch("core.engine.NovaEngine") as mock_engine, \
         patch("memory.short_term.ShortTermMemory") as mock_memory, \
         patch("utils.browser_manager.BrowserManager") as mock_browser, \
         patch("tools.android_tool._run_adb", return_value=(True, "device")), \
         patch("plugins.loader.PluginLoader.discover_and_load_plugins", return_value=[]):
        
        report, engine = manager.run_lifecycle(mock_args)
        
        # Verify engine was instantiated and returned
        mock_engine.assert_called_once()
        assert engine is not None
        
        # Verify report structure
        assert report.startup_duration > 0.0
        assert len(report.initialized_modules) == 10
        assert len(report.failed_modules) == 0
        assert len(report.warnings) == 0
        
        # Verify deterministic order matches standard checklist
        expected_order = [
            "Configuration", "Logging", "Memory", "Plugin Loader", 
            "Permission Gate", "Browser Manager", "Android Manager", 
            "LLM Provider", "Voice Manager", "User Interface"
        ]
        assert report.initialized_modules == expected_order


def test_run_lifecycle_optional_failures():
    """Verify run_lifecycle recovers gracefully if optional browser/android subsystems fail."""
    mock_args = MagicMock()
    mock_args.gui = False
    
    manager = StartupManager()
    
    # We force failures on Browser and Android
    with patch("core.engine.NovaEngine"), \
         patch("memory.short_term.ShortTermMemory"), \
         patch("utils.browser_manager.BrowserManager", side_effect=ValueError("Playwright driver failed")), \
         patch("tools.android_tool._run_adb", side_effect=RuntimeError("adb not found")), \
         patch("plugins.loader.PluginLoader.discover_and_load_plugins", return_value=[]):
        
        report, engine = manager.run_lifecycle(mock_args)
        
        # Verify startup completed and returned engine despite browser/android crashes
        assert engine is not None
        
        # Check failed modules
        assert "Browser Manager" in report.failed_modules
        assert "Android Manager" in report.failed_modules
        
        # Warnings and successful modules must exist
        assert len(report.warnings) >= 2
        assert "Memory" in report.initialized_modules
        assert "Permission Gate" in report.initialized_modules
