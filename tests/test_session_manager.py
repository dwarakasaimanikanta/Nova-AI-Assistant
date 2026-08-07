"""
tests/test_session_manager.py
-----------------------------
Unit tests verifying the SessionManager transitions, report generation, timeouts, and bindings.
"""

import time
from unittest.mock import MagicMock, patch
import pytest

from core.session_manager import (
    SessionManager, Session, SessionState, SessionReport
)


def test_session_report_fields():
    """Verify SessionReport tracks times, durations, and commands accurately."""
    report = SessionReport(
        session_id="SESS_456",
        start_time=100.0,
        end_time=150.0,
        states_visited=["STARTING", "READY", "SHUTDOWN"],
        commands_processed=5
    )

    assert report.session_id == "SESS_456"
    assert report.duration == 50.0
    assert report.commands_processed == 5
    
    data = report.to_dict()
    assert data["session_id"] == "SESS_456"
    assert data["duration"] == 50.0
    assert data["commands_processed"] == 5


def test_session_manager_start_lifecycle():
    """Verify session starts in STARTING, triggers greeting and briefing, and transitions to READY."""
    mock_startup = MagicMock()
    mock_morning = MagicMock()
    mock_voice = MagicMock()

    mock_report = MagicMock()
    mock_report.summary = "Daily summary text"
    mock_morning.generate_report.return_value = mock_report

    manager = SessionManager(
        startup_manager=mock_startup,
        morning_engine=mock_morning,
        voice_manager=mock_voice
    )

    session = manager.start_session("SESS_123")

    assert manager.current_session is session
    assert session.session_id == "SESS_123"
    assert session.state == SessionState.READY
    
    # Assert integrations were triggered
    mock_voice._safe_speak.assert_called_once()
    mock_morning.generate_report.assert_called_once()


def test_session_activity_updates():
    """Verify user actions reset idle timers and increment command counters."""
    manager = SessionManager()
    session = manager.start_session("SESS_1")

    assert session.commands_processed == 0
    time.sleep(0.01)

    manager.update_activity()
    assert session.commands_processed == 1
    assert session.state == SessionState.READY


def test_session_idle_timeout_transitions():
    """Verify session state transitions to IDLE and SLEEPING after idle periods."""
    manager = SessionManager()
    session = manager.start_session("SESS_1")
    manager._idle_timeout = 0.05  # Set a tiny idle timeout for testing

    # Initially READY
    assert session.state == SessionState.READY

    # Wait for idle timeout
    time.sleep(0.06)
    manager.check_idle_state()
    assert session.state == SessionState.IDLE

    # Update session last activity to trigger sleep check transition
    session.last_activity_time = time.time() - 1.0
    manager.check_idle_state()
    assert session.state == SessionState.SLEEPING


def test_session_end_lifecycle():
    """Verify ending session compiles details into report and terminates subprocesses."""
    mock_voice = MagicMock()
    manager = SessionManager(voice_manager=mock_voice)
    session = manager.start_session("SESS_1")

    report = manager.end_session()
    
    assert manager.current_session is None
    assert report is not None
    assert report.session_id == "SESS_1"
    assert "STOPPING" in report.states_visited
    assert "SHUTDOWN" in report.states_visited
    mock_voice.stop.assert_called_once()
