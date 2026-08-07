"""
plugins/android_plugin.py
--------------------------
Plugin registration for AndroidTool – Android phone control via ADB.
"""

from plugins.base import BasePlugin
from tools.base_tool import BaseTool
from tools.android_tool import AndroidTool


class AndroidPlugin(BasePlugin):
    """Plugin providing Android phone control via ADB."""

    @property
    def name(self) -> str:
        return "android"

    def get_tools(self) -> list[BaseTool]:
        return [AndroidTool()]

    def initialize_plugin(self, engine) -> None:
        """On startup, automatically check and connect to the last used wireless ADB device."""
        import json
        from pathlib import Path
        from tools.android_tool import _run_adb
        from utils.logger import get_logger

        plugin_logger = get_logger(__name__)
        config_path = Path("data/android_config.json")

        try:
            # 1. Automatically execute adb devices
            success, output = _run_adb(["devices"], timeout=5)
            if not success:
                plugin_logger.debug("[Android] adb devices check failed at startup.")
                return

            # Parse connected devices
            lines = output.splitlines()
            has_usb = False
            connected_wireless_devices = []

            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    device_name = parts[0]
                    if ":" in device_name:
                        connected_wireless_devices.append(device_name)
                    else:
                        has_usb = True

            # If a wireless device is connected, save it as the last used device
            if connected_wireless_devices:
                last_dev = connected_wireless_devices[0]
                config_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with open(config_path, "w", encoding="utf-8") as f:
                        json.dump({"last_device": last_dev}, f)
                except Exception as write_err:
                    plugin_logger.warning("[Android] Failed to write android_config.json: %s", write_err)

            # 6. If USB is connected, do nothing
            if has_usb:
                return

            # If wireless is already connected, log and finish
            if connected_wireless_devices:
                plugin_logger.info("[Android] Wireless device connected.")
                return

            # 2. If no USB device exists but an IP device was previously used
            if config_path.exists():
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    last_device = config.get("last_device")
                    
                    if last_device and ":" in last_device:
                        # Attempt to connect to the saved wireless device with 5s timeout
                        conn_success, conn_output = _run_adb(["connect", last_device], timeout=5)
                        if conn_success and "connected to" in conn_output.lower():
                            plugin_logger.info("[Android] Wireless device connected.")
                        else:
                            plugin_logger.debug("[Android] Failed to connect to wireless device %s: %s", last_device, conn_output)
                except Exception as read_err:
                    plugin_logger.warning("[Android] Error reading android_config.json or reconnecting: %s", read_err)

        except Exception as e:
            # 5. If connection fails, continue startup normally. Do NOT crash Nova.
            plugin_logger.error("[Android] Wireless ADB reconnection encountered error: %s", e)
