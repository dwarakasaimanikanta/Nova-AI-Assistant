"""
startup/background_service.py
-----------------------------
Coordinator for the persistent background service lifecycle.
"""

import socket
import sys
import time
from typing import Any, Callable, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class BackgroundService:
    """Manages single-instance protection, auto-restart, and background orchestration."""

    def __init__(self, lock_port: int = 49168) -> None:
        self.lock_port = lock_port
        self._lock_socket: Optional[socket.socket] = None
        self.running = False

    def acquire_single_instance_lock(self) -> bool:
        """Secure a local port bind to enforce only one background instance of Nova."""
        try:
            self._lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._lock_socket.bind(('127.0.0.1', self.lock_port))
            self._lock_socket.listen(1)
            logger.info("Single instance lock successfully acquired on port %d.", self.lock_port)
            return True
        except socket.error:
            logger.warning("Another instance of Nova background service is already running. Shutting down.")
            return False

    def run_health_checks(self) -> bool:
        """Check essential configuration and directories on startup."""
        logger.info("Running system startup diagnostic checks...")
        try:
            from config import DATA_DIR
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            logger.error("Startup health checks failed: %s", e)
            return False

    def start(self, runner_callback: Callable[[BackgroundService], None]) -> None:
        """Initialize lock protection, verify health status and start execution loop."""
        if not self.acquire_single_instance_lock():
            sys.exit(1)

        if not self.run_health_checks():
            logger.error("System health status is invalid. Halting startup.")
            sys.exit(1)

        self.running = True
        logger.info("Nova background service loop started.")
        
        try:
            runner_callback(self)
        except Exception as e:
            logger.exception("Background execution raised an exception: %s", e)
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Gracefully release locks and terminate background processes."""
        if self.running:
            self.running = False
            if self._lock_socket:
                try:
                    self._lock_socket.close()
                except Exception:
                    pass
            logger.info("Nova background service gracefully stopped.")
