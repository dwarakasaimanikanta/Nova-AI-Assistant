"""
startup/tray_manager.py
-----------------------
System tray interface for control of the Nova background process.
"""

import threading
from typing import Callable, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class TrayManager:
    """Manages the lifecycle and menus of the Nova System Tray icon."""

    def __init__(
        self,
        on_open: Optional[Callable[[], None]] = None,
        on_hide: Optional[Callable[[], None]] = None,
        on_restart: Optional[Callable[[], None]] = None,
        on_exit: Optional[Callable[[], None]] = None,
    ) -> None:
        self.on_open = on_open
        self.on_hide = on_hide
        self.on_restart = on_restart
        self.on_exit = on_exit
        self._icon = None

    def run(self) -> None:
        """Start the system tray icon loop in a background thread."""
        try:
            import pystray
            from PIL import Image, ImageDraw

            # Create simple icon image dynamically
            image = Image.new('RGB', (64, 64), color=(60, 63, 65))
            d = ImageDraw.Draw(image)
            d.rectangle([(16, 16), (48, 48)], fill=(0, 120, 215))

            menu = pystray.Menu(
                pystray.MenuItem("Open Nova", self._handle_open),
                pystray.MenuItem("Hide Nova", self._handle_hide),
                pystray.MenuItem("Restart Nova", self._handle_restart),
                pystray.MenuItem("Exit", self._handle_exit)
            )

            self._icon = pystray.Icon("Nova", image, "Nova AI Assistant", menu)
            threading.Thread(target=self._icon.run, daemon=True).start()
            logger.info("Nova system tray icon started successfully.")
        except ImportError:
            logger.warning("pystray or PIL is not installed. System tray started in stub mode.")

    def stop(self) -> None:
        """Stop the system tray icon loop."""
        if self._icon:
            self._icon.stop()
            logger.info("Nova system tray icon stopped.")

    def _handle_open(self, icon, item) -> None:
        if self.on_open:
            self.on_open()

    def _handle_hide(self, icon, item) -> None:
        if self.on_hide:
            self.on_hide()

    def _handle_restart(self, icon, item) -> None:
        if self.on_restart:
            self.on_restart()

    def _handle_exit(self, icon, item) -> None:
        self.stop()
        if self.on_exit:
            self.on_exit()
