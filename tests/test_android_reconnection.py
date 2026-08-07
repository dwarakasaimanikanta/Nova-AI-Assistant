"""
tests/test_android_reconnection.py
-----------------------------------
Unit tests verifying automatic wireless ADB reconnection logic in AndroidPlugin on startup.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from plugins.android_plugin import AndroidPlugin


@pytest.fixture
def plugin():
    return AndroidPlugin()


@pytest.fixture
def config_file(tmp_path):
    # Patch config_path inside initialize_plugin to point to a temporary test file
    test_path = tmp_path / "android_config.json"
    return test_path


def test_reconnection_does_nothing_if_usb_connected(plugin, config_file):
    """Verify that if a USB device is present, no adb connect is triggered."""
    # Setup mock adb output with a USB device connected
    mock_devices_output = (
        "List of devices attached\n"
        "9889db474f374737\tdevice\n"
    )

    with patch("tools.android_tool._run_adb") as mock_run_adb, \
         patch("pathlib.Path", return_value=config_file):
        
        mock_run_adb.return_value = (True, mock_devices_output)
        
        plugin.initialize_plugin(None)
        
        # Should call devices once
        mock_run_adb.assert_called_once_with(["devices"], timeout=5)
        # Should NOT call connect because USB is connected
        for call in mock_run_adb.call_args_list:
            assert "connect" not in call[0][0]


def test_reconnection_saves_connected_wireless_device(plugin, config_file):
    """Verify that if a wireless device is already active on startup, it is saved to android_config.json."""
    mock_devices_output = (
        "List of devices attached\n"
        "192.168.0.102:5555\tdevice\n"
    )

    with patch("tools.android_tool._run_adb") as mock_run_adb, \
         patch("pathlib.Path", return_value=config_file), \
         patch("utils.logger.get_logger") as mock_get_logger:
        
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_run_adb.return_value = (True, mock_devices_output)
        
        plugin.initialize_plugin(None)
        
        # Verify it wrote to config_file
        assert config_file.exists()
        with open(config_file, encoding="utf-8") as f:
            data = json.load(f)
        assert data["last_device"] == "192.168.0.102:5555"
        
        # Verify it logged connection
        mock_logger.info.assert_called_with("[Android] Wireless device connected.")


def test_reconnection_connects_if_previously_used(plugin, config_file):
    """Verify that if no USB is present but a wireless device was previously saved, adb connect is run."""
    # Write saved last_device to config
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump({"last_device": "192.168.0.102:5555"}, f)

    # First call: devices returns no devices
    # Second call: connect returns connected successfully
    devices_output = "List of devices attached\n"
    connect_output = "connected to 192.168.0.102:5555"

    with patch("tools.android_tool._run_adb") as mock_run_adb, \
         patch("pathlib.Path", return_value=config_file), \
         patch("utils.logger.get_logger") as mock_get_logger:
        
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        mock_run_adb.side_effect = [
            (True, devices_output),  # devices
            (True, connect_output)   # connect
        ]
        
        plugin.initialize_plugin(None)
        
        # Assert call sequence
        assert mock_run_adb.call_count == 2
        mock_run_adb.assert_any_call(["devices"], timeout=5)
        mock_run_adb.assert_any_call(["connect", "192.168.0.102:5555"], timeout=5)
        
        # Check logger success output
        mock_logger.info.assert_called_with("[Android] Wireless device connected.")


def test_reconnection_fails_gracefully(plugin, config_file):
    """Verify that if the adb commands fail or raise exceptions, initialize_plugin continues normally without raising."""
    with patch("tools.android_tool._run_adb", side_effect=RuntimeError("ADB crashed")), \
         patch("pathlib.Path", return_value=config_file), \
         patch("utils.logger.get_logger") as mock_get_logger:
        
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        # Should not raise exception
        plugin.initialize_plugin(None)
        
        mock_logger.error.assert_called_once()
        assert "Wireless ADB reconnection encountered error" in mock_logger.error.call_args[0][0]
