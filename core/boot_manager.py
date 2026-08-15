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
    _instance: Optional[BootManager] = None

    def __init__(self) -> None:
        BootManager._instance = self
        self.config_service: Optional[Any] = None
        self.agent_registry: Optional[Any] = None
        self.memory_agent: Optional[Any] = None
        self.short_term: Optional[Any] = None
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

        logger.info("[SYSTEM] Starting real startup integration pipeline...")

        # Avoid duplicate initialization
        if self.initialized:
            logger.info("[SYSTEM] Already initialized. Returning cached boot report.")
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
            from memory.short_term import ShortTermMemory
            self.short_term = ShortTermMemory()
            engine = NovaEngine(memory=self.short_term)
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

            # 7. Initialize VoiceManager with config values
            from voice.voice_manager import VoiceManager
            from config import VOICE_INPUT_ENABLED, WAKE_WORD_ENABLED
            self.voice_manager = VoiceManager(
                engine=self.executive_agent,
                wake_word_enabled=WAKE_WORD_ENABLED,
                voice_input_enabled=VOICE_INPUT_ENABLED,
            )
            
            # Associate with the loaded voice plugin if present
            voice_plugin = None
            for p in getattr(engine, "plugins", []):
                if getattr(p, "name", "") == "voice":
                    voice_plugin = p
                    break
            if voice_plugin:
                voice_plugin.voice_manager = self.voice_manager
                
            self.session_manager.voice_manager = self.voice_manager
            initialized_components.append("VoiceManager")

            # 8. Initialize AlwaysListeningEngine
            from voice.always_listening import AlwaysListeningEngine
            from config import CONVERSATION_TIMEOUT_SECONDS
            self.always_listening = AlwaysListeningEngine(
                voice_manager=self.voice_manager,
                wake_detector=self.voice_manager.wake_detector,
                audio_recorder=self.voice_manager.recorder,
                conversation_timeout=CONVERSATION_TIMEOUT_SECONDS,
                on_wake_callback=lambda: self.voice_manager._safe_speak("Yes Boss.")
            )
            self.voice_manager.always_listening = self.always_listening
            initialized_components.append("AlwaysListeningEngine")

            # 9. Initialize ConversationEngine
            from voice.conversation_engine import VoiceConversationEngine
            self.conversation_engine = VoiceConversationEngine(
                executive_agent=self.executive_agent,
                voice_manager=self.voice_manager,
                memory_agent=self.memory_agent
            )
            
            def handle_wake():
                self.voice_manager._safe_speak("Yes Boss.")
                
            self.always_listening.on_wake_callback = handle_wake
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
            self.executive_agent.execution_pipeline = self.execution_pipeline
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

        # 11. Generate startup greeting
        greeting = "Hello Boss.\nAll core systems are online.\nI'm ready."

        # Speak greeting if voice is enabled
        if self.voice_manager and getattr(self.voice_manager, "voice_input_enabled", False):
            try:
                self.voice_manager._safe_speak(greeting)
                logger.info("[BootManager] Startup greeting spoken.")
            except Exception as tts_err:
                logger.debug("Failed speaking startup greeting: %s", tts_err)

        # 12. Start Always Listening mode (Jarvis-style continuous wake-word)
        if self.voice_manager:
            self.voice_manager.wake_word_enabled = True
            self.voice_manager.state = "WAKING"
            self.always_listening.start()
            logger.info("[BootManager] Always Listening background thread started.")

        # 12.5 Windows Startup Registration
        import sys
        if sys.platform == "win32":
            try:
                from config import NOVA_START_WITH_WINDOWS
                from startup.windows_startup import WindowsStartup
                win_startup = WindowsStartup()
                if NOVA_START_WITH_WINDOWS:
                    if not win_startup.is_registered():
                        win_startup.register()
                else:
                    if win_startup.is_registered():
                        win_startup.remove()
            except Exception as e:
                logger.warning("[SYSTEM] Failed setting startup configuration: %s", e)

        self.initialized = True
        duration = time.time() - started
        logger.info("[SYSTEM] Startup bootstrap completed successfully in %.2fs.", duration)
        
        return BootReport(
            success=True,
            session_id=session_id,
            duration=duration,
            initialized_components=initialized_components,
            skipped_components=skipped_components,
            errors=errors,
            greeting=greeting
        )

    def shutdown_system(self) -> None:
        """Cleanly terminates all background threads, managers, loops, and exits the application."""
        logger.info("[SYSTEM] Initiating clean shutdown sequence...")
        
        # 1. Stop AlwaysListeningEngine
        if self.always_listening:
            try:
                logger.info("[SYSTEM] Stopping AlwaysListeningEngine...")
                self.always_listening.stop()
            except Exception as e:
                logger.error("[SYSTEM] Error stopping always_listening: %s", e)
                
        # 2. Stop VoiceManager
        if self.voice_manager:
            try:
                logger.info("[SYSTEM] Stopping VoiceManager...")
                self.voice_manager.stop()
            except Exception as e:
                logger.error("[SYSTEM] Error stopping voice_manager: %s", e)
                
            # 3. Stop SpeechController (TTS)
            if hasattr(self.voice_manager, "speech_controller") and self.voice_manager.speech_controller:
                try:
                    logger.info("[SYSTEM] Stopping SpeechController...")
                    self.voice_manager.speech_controller.stop_event.set()
                    self.voice_manager.speech_controller.interrupt()
                except Exception as e:
                    logger.error("[SYSTEM] Error stopping speech_controller: %s", e)
                    
        # 4. Stop BrowserManager
        try:
            from utils.browser_manager import BrowserManager
            bm_inst = getattr(BrowserManager, "_instance", None)
            if bm_inst:
                logger.info("[SYSTEM] Stopping BrowserManager...")
                bm_inst.shutdown()
        except Exception as e:
            logger.error("[SYSTEM] Error shutting down BrowserManager: %s", e)

        # 5. Stop MCPManager if active in plugins
        try:
            if self.agent_registry and self.agent_registry.is_registered("mcp"):
                mcp_pl = self.agent_registry.resolve("mcp")
                if hasattr(mcp_pl, "manager") and mcp_pl.manager:
                    logger.info("[SYSTEM] Stopping MCPManager...")
                    mcp_pl.manager.shutdown()
        except Exception as e:
            logger.error("[SYSTEM] Error shutting down MCP: %s", e)

        logger.info("[SYSTEM] Shutdown complete. Exiting process.")
