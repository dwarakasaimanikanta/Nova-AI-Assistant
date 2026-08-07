"""
tests/test_windows_startup.py
------------------------------
Comprehensive unit tests for the Windows Startup Service.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from startup.background_service import BackgroundService
from startup.tray_manager import TrayManager
from startup.windows_startup import WindowsStartup


# ─────────────────────────────────────────────────────────────────────────────
# WindowsStartup Registry Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestWindowsStartup:
    @patch("winreg.OpenKey")
    @patch("winreg.SetValueEx")
    def test_register_writes_to_registry(self, mock_set_val, mock_open_key):
        startup = WindowsStartup()
        success = startup.register()
        assert success is True
        mock_open_key.assert_called_once()
        mock_set_val.assert_called_once()

    @patch("winreg.OpenKey")
    @patch("winreg.DeleteValue")
    def test_remove_deletes_registry_value(self, mock_del_val, mock_open_key):
        startup = WindowsStartup()
        success = startup.remove()
        assert success is True
        mock_open_key.assert_called_once()
        mock_del_val.assert_called_once()

    @patch("winreg.OpenKey")
    @patch("winreg.QueryValueEx")
    def test_is_registered_queries_registry(self, mock_query_val, mock_open_key):
        startup = WindowsStartup()
        mock_query_val.return_value = ("cmd", 1)
        assert startup.is_registered() is True
        mock_open_key.assert_called_once()
        mock_query_val.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# BackgroundService Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestBackgroundService:
    def test_health_checks_pass(self):
        service = BackgroundService()
        assert service.run_health_checks() is True

    @patch("socket.socket")
    def test_acquire_single_instance_lock_success(self, mock_socket_cls):
        mock_socket = MagicMock()
        mock_socket_cls.return_value = mock_socket

        service = BackgroundService(lock_port=12345)
        locked = service.acquire_single_instance_lock()
        assert locked is True
        mock_socket.bind.assert_called_once_with(('127.0.0.1', 12345))

    @patch("socket.socket")
    def test_acquire_single_instance_lock_failure(self, mock_socket_cls):
        import socket
        mock_socket = MagicMock()
        mock_socket.bind.side_effect = socket.error("Port in use")
        mock_socket_cls.return_value = mock_socket

        service = BackgroundService(lock_port=12345)
        locked = service.acquire_single_instance_lock()
        assert locked is False


# ─────────────────────────────────────────────────────────────────────────────
# TrayManager Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTrayManager:
    def test_callbacks_fired_correctly(self):
        on_open = MagicMock()
        on_hide = MagicMock()
        on_restart = MagicMock()
        on_exit = MagicMock()

        manager = TrayManager(
            on_open=on_open,
            on_hide=on_hide,
            on_restart=on_restart,
            on_exit=on_exit
        )

        # Trigger internal handle callbacks manually
        manager._handle_open(None, None)
        manager._handle_hide(None, None)
        manager._handle_restart(None, None)
        manager._handle_exit(None, None)

        on_open.assert_called_once()
        on_hide.assert_called_once()
        on_restart.assert_called_once()
        on_exit.assert_called_once()
