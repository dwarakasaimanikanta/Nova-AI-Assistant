"""
core/boot_manager.py
--------------------
Boot Experience Manager coordinating complete startup sequence,
service health checks, session recovery, and voice activation.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class BootManager:
    """Coordinates startup sequences, session restoration, and subsystem readiness checks."""

    def __init__(
        self,
        service_manager: Any,
        session_manager: Any,
        voice_manager: Optional[Any] = None,
        memory_agent: Optional[Any] = None,
    ) -> None:
        self.service_manager = service_manager
        self.session_manager = session_manager
        self.voice_manager = voice_manager
        self.memory_agent = memory_agent

    def boot(self, session_id: Optional[str] = None) -> bool:
        """
        Executes the entire boot lifecycle sequence.
        
        Steps:
        1. Initialize/Verify MemoryAgent and VoiceManager.
        2. Wait/start mandatory services.
        3. Gracefully skip optional services.
        4. Restore or create session.
        5. Speak/trigger startup greeting.
        6. Enter Always Listening mode.
        """
        logger.info("[BootManager] Commencing boot sequence...")

        # ── 1. Initialize core services ────────────────────────────────────
        if self.memory_agent:
            try:
                # Ensure the DB schema is valid
                self.memory_agent.remember("working", "boot_check", "ok")
                logger.info("[BootManager] MemoryAgent verified successfully.")
            except Exception as e:
                logger.error("[BootManager] MemoryAgent initialization failed: %s", e)
                raise RuntimeError(f"MemoryAgent failed startup health check: {e}")

        # ── 2. Wait for mandatory/optional services to be healthy ────────
        mandatory_services = ["Memory", "Voice"]
        optional_services = ["Browser", "Android"]

        # First verify and startup mandatory
        for service_name in mandatory_services:
            if not self._ensure_service_healthy(service_name):
                logger.error("[BootManager] Mandatory service '%s' is not healthy. Aborting.", service_name)
                raise RuntimeError(f"Mandatory service '{service_name}' failed to boot.")

        # Gracefully handle optional services
        for service_name in optional_services:
            if not self._ensure_service_healthy(service_name):
                logger.warning("[BootManager] Optional service '%s' is degraded/unavailable. Skipping.", service_name)

        # ── 3. Restore previous session or create new one ─────────────────
        if not session_id and self.memory_agent:
            try:
                session_id = self.memory_agent.recall("short_term", "last_session_id")
                if session_id:
                    logger.info("[BootManager] Restoring previous session ID: %s", session_id)
            except Exception as recall_err:
                logger.warning("[BootManager] Failed to recall last session ID: %s", recall_err)

        if not session_id:
            session_id = f"session_{int(time.time())}"
            logger.info("[BootManager] Starting new session: %s", session_id)

        try:
            self.session_manager.start_session(session_id)
            if self.memory_agent:
                self.memory_agent.remember("short_term", "last_session_id", session_id)
        except Exception as sess_err:
            logger.error("[BootManager] SessionManager failed to start/restore session: %s", sess_err)
            return False

        # ── 4. Generate and speak startup greeting ────────────────────────
        greeting = self.session_manager.trigger_startup_greeting()
        if self.voice_manager and getattr(self.voice_manager, "voice_input_enabled", False):
            try:
                # Speak greeting
                if hasattr(self.voice_manager, "tts") and hasattr(self.voice_manager.tts, "execute"):
                    self.voice_manager.tts.execute(text=greeting)
                elif hasattr(self.voice_manager, "speak"):
                    self.voice_manager.speak(greeting)
            except Exception as tts_err:
                logger.warning("[BootManager] Failed to speak greeting text: %s", tts_err)

        # ── 5. Prepare always listening mode ──────────────────────────────
        if self.voice_manager and getattr(self.voice_manager, "voice_input_enabled", False):
            self.voice_manager.wake_word_enabled = True
            # Transition state of voice manager
            self.voice_manager.state = "WAITING"
            # Start listener background thread
            self.voice_manager.start()
            logger.info("[BootManager] Always Listening mode activated.")

        logger.info("[BootManager] Boot sequence completed successfully.")
        return True

    def _ensure_service_healthy(self, name: str) -> bool:
        """Verify service health state, attempting to start it if not running."""
        registry = self.service_manager.registry
        service = registry.get_service(name)
        if not service:
            return False

        # Check existing status state
        status = registry.get_status(name)
        if status and status.state == "RUNNING":
            return service.health()

        # Try to initialize and start the service
        try:
            logger.info("[BootManager] Service '%s' not running. Attempting boot...", name)
            self.service_manager.start_service(name)
            status = registry.get_status(name)
            return status is not None and status.state == "RUNNING" and service.health()
        except Exception as e:
            logger.error("[BootManager] Service '%s' failed to start: %s", name, e)
            return False
