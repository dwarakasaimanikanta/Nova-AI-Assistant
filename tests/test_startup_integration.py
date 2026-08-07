"""
tests/test_startup_integration.py
---------------------------------
Integration tests verifying the complete end-to-end startup experience and fallback matrices.
"""

import sys
from unittest.mock import MagicMock, patch
import pytest

import config
from core.session_manager import SessionManager, SessionState
from core.morning_engine import MorningEngine, MorningReport


def test_normal_startup_greeting_integration():
    """Verify that a successful morning report generates, speaks, and transitions VoiceManager state."""
    mock_startup = MagicMock()
    mock_morning = MagicMock()
    mock_voice = MagicMock()
    mock_voice.wake_word_enabled = True
    mock_voice.state = "WAKING"

    # Setup report
    mock_report = MorningReport(
        greeting="Good morning",
        date_str="2026-08-07",
        weekday="Friday",
        battery="91%",
        internet="Connected",
        weather="Sunny",
        calendar_events=[],
        pending_tasks=[],
        github_notifications=[],
        recommendations=[],
        summary="summary"
    )
    mock_morning.generate_report.return_value = mock_report

    with patch("config.STARTUP_GREETING_ENABLED", True):
        manager = SessionManager(
            startup_manager=mock_startup,
            morning_engine=mock_morning,
            voice_manager=mock_voice
        )
        
        session = manager.start_session("TEST_INTEG_SESS")
        
        # Verify state transition
        assert session.state == SessionState.READY
        
        # Check generated greeting content
        expected_greeting = (
            "Good morning Boss. Today is Friday. Battery is 91 percent. "
            "Internet is connected. I'm ready. What shall we build today?"
        )
        mock_voice._safe_speak.assert_called_once_with(expected_greeting)
        
        # Verify voice manager enters waiting state
        assert mock_voice.state == "WAITING"


def test_morning_engine_failure_fallback_greeting():
    """Verify that a MorningEngine crash falls back to a clean default greeting without crashing."""
    mock_startup = MagicMock()
    mock_morning = MagicMock()
    mock_morning.generate_report.side_effect = RuntimeError("Service unavailable")
    
    mock_voice = MagicMock()
    mock_voice.wake_word_enabled = False
    mock_voice.state = "LISTENING"

    with patch("config.STARTUP_GREETING_ENABLED", True), \
         patch("datetime.datetime") as mock_dt:
        
        # Lock time to morning (e.g. 9 AM)
        mock_now = MagicMock()
        mock_now.hour = 9
        mock_dt.datetime.now.return_value = mock_now
        mock_dt.now.return_value = mock_now

        manager = SessionManager(
            startup_manager=mock_startup,
            morning_engine=mock_morning,
            voice_manager=mock_voice
        )

        session = manager.start_session("TEST_FALLBACK_SESS")
        
        assert session.state == SessionState.READY
        # Should speak the morning fallback
        mock_voice._safe_speak.assert_called_once_with("Good Morning Boss. I'm ready.")
        assert mock_voice.state == "LISTENING"


def test_voice_disabled_integration():
    """Verify that system startups when voice manager is None run cleanly."""
    mock_morning = MagicMock()
    manager = SessionManager(
        startup_manager=MagicMock(),
        morning_engine=mock_morning,
        voice_manager=None
    )

    # Greet should not raise exceptions or crash
    session = manager.start_session("TEST_NO_VOICE_SESS")
    assert session.state == SessionState.READY


def test_greeting_disabled_integration():
    """Verify that disabling startup greetings bypasses speech but transitions listening state."""
    mock_morning = MagicMock()
    mock_voice = MagicMock()
    mock_voice.wake_word_enabled = True
    mock_voice.state = "WAKING"

    with patch("config.STARTUP_GREETING_ENABLED", False):
        manager = SessionManager(
            startup_manager=MagicMock(),
            morning_engine=mock_morning,
            voice_manager=mock_voice
        )

        session = manager.start_session("TEST_GREET_DISABLED_SESS")
        
        # Verify speech is bypassed
        mock_voice._safe_speak.assert_not_called()
        mock_voice.speak.assert_not_called()
        
        # Enters listening state
        assert mock_voice.state == "WAITING"
