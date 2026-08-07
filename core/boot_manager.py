"""
core/boot_manager.py
--------------------
Real Startup Integration Boot Manager acting as the single entry point
for system bootstrap, component wiring, health checks, and session restoration.
"""

from __future__ import annotations

import datetime
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Boot Report
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BootReport:
    """Detailed startup diagnostics and wiring outcomes report."""
    success: bool
    session_id: str
    duration: float
    initialized_components: List[str] = field(default_factory=list)
    skipped_components: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    greeting: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Boot Manager
# ─────────────────────────────────────────────────────────────────────────────

class BootManager:
    """Single entry point coordinating the real startup pipeline initialization and wiring."""

    def __init__(self) -> None:
        self.config_service: Optional[Any] = None
        self.agent_registry: Optional[Any] = None
        self.memory_agent: Optional[Any] = None
        self.session_manager: Optional[Any] = None
        self.voice_manager: Optional[Any] = None
        self.always_listening: Optional[Any] = None
        self.conversation_engine: Optional[Any] = None
        self.execution_pipeline: Optional[Any] = None
        self.executive_agent: Optional[Any] = None
        self.initialized = False

    def boot(self, session_id: Optional[str] = None) -> BootReport:
        """
        Runs the complete real startup integration sequence.
        Wires all services and pipelines together, returning a BootReport.
        """
        started = time.time()
        initialized_components = []
        skipped_components = []
        errors = []

        logger.info("[BootManager] Starting real startup integration pipeline...")

        # Avoid duplicate initialization
        if self.initialized:
            logger.info("[BootManager] Already initialized. Returning cached boot report.")
            duration = time.time() - started
            return BootReport(
                success=True,
                session_id=getattr(self.session_manager.current_session, "session_id", "cached_session") if self.session_manager else "cached",
                duration=duration,
                initialized_components=["CacheRestore"],
                greeting="Nova is already online."
            )

        try:
            # 1. Initialize ConfigService
            from core.config_service import ConfigService
            self.config_service = ConfigService()
            self.config_service.initialize()
            initialized_components.append("ConfigService")

            # 2. Initialize AgentRegistry & register defaults
            from core.agent_registry import AgentRegistry
            self.agent_registry = AgentRegistry()
            self.agent_registry.load_defaults()
            initialized_components.append("AgentRegistry")

            # 3. Initialize MemoryAgent
            try:
                self.memory_agent = self.agent_registry.resolve("memory")
                # Trigger a mock call to verify schema
                self.memory_agent.remember("working", "boot_check", "ok")
                initialized_components.append("MemoryAgent")
            except Exception as e:
                errors.append(f"MemoryAgent init failed: {e}")
                logger.error("[BootManager] MemoryAgent failed startup check: %s", e)

            # 4. Initialize Core Engine & ExecutiveAgent
            from core.engine import NovaEngine
            from core.executive_agent import ExecutiveAgent
            engine = NovaEngine()
            self.executive_agent = ExecutiveAgent(engine=engine, agent_registry=self.agent_registry)
            self.agent_registry.set_engine(engine)
            initialized_components.append("ExecutiveAgent")

            # 5. Initialize SessionManager
            from core.session_manager import SessionManager
            self.session_manager = SessionManager(voice_manager=None)
            initialized_components.append("SessionManager")

            # 6. Restore previous session if available
            if not session_id and self.memory_agent:
                try:
                    session_id = self.memory_agent.recall("short_term", "last_session_id")
                except Exception as recall_err:
                    logger.debug("Failed recalling last session ID: %s", recall_err)

            if not session_id:
                session_id = f"session_{int(time.time())}"
            
            self.session_manager.start_session(session_id)
            if self.memory_agent:
                self.memory_agent.remember("short_term", "last_session_id", session_id)

            # 7. Initialize VoiceManager
            from voice.voice_manager import VoiceManager
            self.voice_manager = VoiceManager(engine=engine)
            self.session_manager.voice_manager = self.voice_manager
            initialized_components.append("VoiceManager")

            # 8. Initialize AlwaysListeningEngine
            from voice.always_listening import AlwaysListeningEngine
            self.always_listening = AlwaysListeningEngine(
                voice_manager=self.voice_manager,
                wake_detector=self.voice_manager.wake_detector,
                audio_recorder=self.voice_manager.recorder
            )
            initialized_components.append("AlwaysListeningEngine")

            # 9. Initialize ConversationEngine
            from voice.conversation_engine import VoiceConversationEngine
            self.conversation_engine = VoiceConversationEngine(
                executive_agent=self.executive_agent,
                voice_manager=self.voice_manager,
                memory_agent=self.memory_agent
            )
            self.always_listening.on_command_callback = self.conversation_engine.process_speech
            initialized_components.append("ConversationEngine")

            # 10. Initialize ExecutionPipeline
            from core.execution_pipeline import ExecutionPipeline
            planner_agent = None
            if self.agent_registry.is_registered("planner"):
                planner_agent = self.agent_registry.resolve("planner")
            
            self.execution_pipeline = ExecutionPipeline(
                executive_agent=self.executive_agent,
                agent_registry=self.agent_registry,
                planner_agent=planner_agent,
                memory_agent=self.memory_agent
            )
            initialized_components.append("ExecutionPipeline")

            # Resolve optional agents and log status
            optional_agents = ["browser", "android", "coding", "workspace"]
            for opt in optional_agents:
                if self.agent_registry.is_registered(opt):
                    try:
                        self.agent_registry.resolve(opt)
                        initialized_components.append(f"Agent:{opt.capitalize()}")
                    except Exception as opt_err:
                        skipped_components.append(opt)
                        logger.warning("[BootManager] Optional agent '%s' failed to resolve: %s", opt, opt_err)
                else:
                    skipped_components.append(opt)

        except Exception as startup_err:
            logger.exception("Critical system bootstrap error: %s", startup_err)
            errors.append(str(startup_err))
            duration = time.time() - started
            return BootReport(
                success=False,
                session_id=session_id or "failed",
                duration=duration,
                initialized_components=initialized_components,
                skipped_components=skipped_components,
                errors=errors
            )

        # 11. Generate startup greeting prefix based on time of day
        hour = datetime.datetime.now().hour
        greeting_time = "Good morning"
        if 12 <= hour < 17:
            greeting_time = "Good afternoon"
        elif 17 <= hour < 22:
            greeting_time = "Good evening"
        elif hour >= 22 or hour < 5:
            greeting_time = "Good night"

        greeting = f"{greeting_time} Boss.\nAll core systems are online.\nI'm ready."

        # Speak greeting if voice outputs are supported
        if self.voice_manager and getattr(self.voice_manager, "voice_input_enabled", False):
            try:
                if hasattr(self.voice_manager, "tts") and hasattr(self.voice_manager.tts, "execute"):
                    self.voice_manager.tts.execute(text=greeting)
            except Exception as tts_err:
                logger.debug("Failed speaking startup greeting: %s", tts_err)

        # 12. Switch to Always Listening mode
        if self.voice_manager:
            self.voice_manager.wake_word_enabled = True
            self.voice_manager.state = "WAITING"
            if getattr(self.voice_manager, "voice_input_enabled", False):
                self.always_listening.start()
                logger.info("[BootManager] Always Listening background thread started.")

        self.initialized = True
        duration = time.time() - started
        logger.info("[BootManager] Startup bootstrap completed successfully in %.2fs.", duration)
        
        return BootReport(
            success=True,
            session_id=session_id,
            duration=duration,
            initialized_components=initialized_components,
            skipped_components=skipped_components,
            errors=errors,
            greeting=greeting
        )
