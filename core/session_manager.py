"""
core/session_manager.py
-----------------------
Session Manager orchestrating active user runtime sessions, state transitions,
briefing triggers, greetings, and lifetime statistics.
"""

import time
import threading
from enum import Enum
from typing import Any, Dict, List, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class SessionState(str, Enum):
    """Supported state phases during the Nova runtime lifecycle."""
    STARTING = "STARTING"
    READY = "READY"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    IDLE = "IDLE"
    SLEEPING = "SLEEPING"
    STOPPING = "STOPPING"
    SHUTDOWN = "SHUTDOWN"


class SessionReport:
    """Contains analytics data for a completed user session."""

    def __init__(
        self,
        session_id: str,
        start_time: float,
        end_time: float,
        states_visited: List[str],
        commands_processed: int,
    ) -> None:
        self.session_id = session_id
        self.start_time = start_time
        self.end_time = end_time
        self.states_visited = states_visited
        self.commands_processed = commands_processed

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "duration": self.duration,
            "states_visited": self.states_visited,
            "commands_processed": self.commands_processed,
        }


class Session:
    """Represents a unique user session instance."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.state = SessionState.STARTING
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.states_visited: List[str] = [SessionState.STARTING.value]
        self.commands_processed = 0
        self.last_activity_time = time.time()

    def update_state(self, new_state: SessionState) -> None:
        """Update session state and append to visited log."""
        self.state = new_state
        self.states_visited.append(new_state.value)
        self.last_activity_time = time.time()


class SessionManager:
    """Manages system session states, triggers daily briefings, and tracks usage statistics."""

    def __init__(
        self,
        startup_manager: Optional[Any] = None,
        morning_engine: Optional[Any] = None,
        voice_manager: Optional[Any] = None,
    ) -> None:
        self.startup_manager = startup_manager
        self.morning_engine = morning_engine
        self.voice_manager = voice_manager

        self.current_session: Optional[Session] = None
        self._lock = threading.Lock()
        self._idle_timeout = 600.0  # Default 10 minutes to idle

    def start_session(self, session_id: str) -> Session:
        """Starts a new runtime session, triggers greetings and briefings."""
        with self._lock:
            session = Session(session_id)
            self.current_session = session
            logger.info("[SessionManager] Starting session: %s", session_id)

            # 1. Trigger Startup Greeting
            self.trigger_startup_greeting()

            # 2. Trigger Morning Briefing
            self.trigger_morning_briefing()

            # 3. Transition to READY
            session.update_state(SessionState.READY)
            return session

    def trigger_startup_greeting(self) -> str:
        """Speaks or logs the standard startup greeting."""
        greeting = "Nova is online. Ready for commands."
        logger.info("[SessionManager] Greeting: %s", greeting)
        return greeting

    def trigger_morning_briefing(self) -> Optional[dict]:
        """Triggers the MorningEngine report compile sequence, speaks natural greeting, enters voice listening."""
        import datetime
        import config

        # Determine greeting prefix based on current time
        hour = datetime.datetime.now().hour
        greeting_time = "Good Morning"
        if 12 <= hour < 17:
            greeting_time = "Good Afternoon"
        elif 17 <= hour < 22:
            greeting_time = "Good Evening"
        elif hour >= 22 or hour < 5:
            greeting_time = "Good Night"

        greeting_text = f"{greeting_time} Boss. I'm ready."

        report_dict = None
        if self.morning_engine:
            try:
                report = self.morning_engine.generate_report()
                report_dict = report.to_dict()
                
                # Format battery percentage for text-to-speech
                battery_clean = report.battery
                if "%" in battery_clean:
                    battery_clean = battery_clean.replace("%", " percent")
                
                # Format natural spoken greeting
                greeting_text = (
                    f"{report.greeting} Boss. "
                    f"Today is {report.weekday}. "
                    f"Battery is {battery_clean}. "
                    f"Internet is {report.internet.lower()}. "
                    f"I'm ready. "
                    f"What shall we build today?"
                )
            except Exception as e:
                logger.error("[SessionManager] MorningEngine failed to generate report, falling back: %s", e)

        # Speak the greeting if enabled and voice manager is available
        if config.STARTUP_GREETING_ENABLED:
            logger.info("[SessionManager] Spoken greeting: %s", greeting_text)
            if self.voice_manager:
                if hasattr(self.voice_manager, "_safe_speak"):
                    self.voice_manager._safe_speak(greeting_text)
                elif hasattr(self.voice_manager, "speak"):
                    try:
                        self.voice_manager.speak(greeting_text)
                    except Exception:
                        pass
        else:
            logger.info("[SessionManager] Startup greeting disabled via configuration.")

        # Enter listening state in VoiceManager
        if self.voice_manager:
            if hasattr(self.voice_manager, "state"):
                self.voice_manager.state = "WAITING" if getattr(self.voice_manager, "wake_word_enabled", False) else "LISTENING"
                logger.info("[SessionManager] VoiceManager entered listening state (%s).", self.voice_manager.state)

        return report_dict

    def end_session(self) -> Optional[SessionReport]:
        """Gracefully ends the active session and compiles a SessionReport."""
        with self._lock:
            session = self.current_session
            if not session:
                return None

            session.update_state(SessionState.STOPPING)
            session.end_time = time.time()
            session.update_state(SessionState.SHUTDOWN)

            # Shutdown subsystem integrations if needed
            if self.voice_manager and hasattr(self.voice_manager, "stop"):
                try:
                    self.voice_manager.stop()
                except Exception:
                    pass

            report = SessionReport(
                session_id=session.session_id,
                start_time=session.start_time,
                end_time=session.end_time,
                states_visited=session.states_visited,
                commands_processed=session.commands_processed,
            )
            self.current_session = None
            logger.info("[SessionManager] Session %s ended. Duration: %.2fs", report.session_id, report.duration)
            return report

    def update_activity(self) -> None:
        """Called when a user action/command is processed, keeping session active."""
        with self._lock:
            session = self.current_session
            if session:
                session.last_activity_time = time.time()
                session.commands_processed += 1
                if session.state in (SessionState.IDLE, SessionState.SLEEPING):
                    session.update_state(SessionState.READY)

    def check_idle_state(self) -> None:
        """Transitions state to IDLE or SLEEPING if idle threshold is met."""
        with self._lock:
            session = self.current_session
            if not session:
                return

            idle_duration = time.time() - session.last_activity_time
            if idle_duration > self._idle_timeout:
                if session.state == SessionState.READY:
                    logger.info("[SessionManager] Session idling. Transitioning to IDLE.")
                    session.update_state(SessionState.IDLE)
                elif session.state == SessionState.IDLE:
                    logger.info("[SessionManager] Session deep sleep. Transitioning to SLEEPING.")
                    session.update_state(SessionState.SLEEPING)

    def set_state(self, state: SessionState) -> None:
        """Explicitly set the state of the session."""
        with self._lock:
            if self.current_session:
                self.current_session.update_state(state)
