"""
tests/test_always_listening.py
-------------------------------
Comprehensive unit tests for the Always Listening Engine.
"""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from voice.always_listening import AlwaysListeningEngine


# ─────────────────────────────────────────────────────────────────────────────
# Mocks & Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_voice_manager():
    vm = MagicMock()
    vm._safe_transcribe.return_value = "hello nova"
    vm._safe_engine.return_value = "engine response text"
    return vm


@pytest.fixture
def mock_wake_detector():
    wd = MagicMock()
    wd.detect.return_value = False
    return wd


@pytest.fixture
def mock_audio_recorder():
    ar = MagicMock()
    # Mock return temporary path
    ar.record_command.return_value = Path("mock_temp.wav")
    return ar


# ─────────────────────────────────────────────────────────────────────────────
# Test Suite
# ─────────────────────────────────────────────────────────────────────────────

class TestAlwaysListeningEngine:
    @patch("pathlib.Path.exists", return_value=True)
    @patch("pathlib.Path.unlink")
    def test_wake_word_match_transitions_state(
        self, mock_unlink, mock_exists, mock_voice_manager, mock_wake_detector, mock_audio_recorder
    ):
        # Set wake detector to match
        mock_wake_detector.detect.return_value = True
        
        on_wake = MagicMock()
        engine = AlwaysListeningEngine(
            voice_manager=mock_voice_manager,
            wake_detector=mock_wake_detector,
            audio_recorder=mock_audio_recorder,
            conversation_timeout=1.0,
            on_wake_callback=on_wake
        )

        assert engine.state == "WAKING"
        
        # Start and run one loop iteration manually to verify state transition
        # We avoid running thread in unit test by mocking run loop or calling
        # single execution cycles. Let's call the internal _run_loop steps
        # or execute with a thread that is stopped immediately.
        engine.start()
        time.sleep(0.3)
        engine.stop()

        assert engine.state == "LISTENING"
        on_wake.assert_called_once()
        mock_wake_detector.detect.assert_called_once()

    @patch("pathlib.Path.exists", return_value=True)
    @patch("pathlib.Path.unlink")
    def test_listening_executes_commands_and_speaks(
        self, mock_unlink, mock_exists, mock_voice_manager, mock_wake_detector, mock_audio_recorder
    ):
        mock_voice_manager._safe_transcribe.return_value = "what time is it"
        on_command = MagicMock()

        engine = AlwaysListeningEngine(
            voice_manager=mock_voice_manager,
            wake_detector=mock_wake_detector,
            audio_recorder=mock_audio_recorder,
            conversation_timeout=2.0,
            on_command_callback=on_command
        )
        engine.state = "LISTENING"

        engine.start()
        time.sleep(0.3)
        engine.stop()

        # Should verify command executed
        mock_voice_manager._safe_transcribe.assert_called_once()
        mock_voice_manager._safe_engine.assert_called_once_with("what time is it")
        mock_voice_manager._safe_speak.assert_called_once()
        on_command.assert_called_once_with("what time is it", "engine response text")

    @patch("pathlib.Path.exists", return_value=True)
    @patch("pathlib.Path.unlink")
    def test_conversation_timeout_returns_to_waking(
        self, mock_unlink, mock_exists, mock_voice_manager, mock_wake_detector, mock_audio_recorder
    ):
        # Set transcription to empty to simulate silence
        mock_voice_manager._safe_transcribe.return_value = ""

        # Set short conversation timeout
        engine = AlwaysListeningEngine(
            voice_manager=mock_voice_manager,
            wake_detector=mock_wake_detector,
            audio_recorder=mock_audio_recorder,
            conversation_timeout=0.1
        )
        engine.state = "LISTENING"

        engine.start()
        time.sleep(0.4)
        engine.stop()

        # Should transition back to WAKING due to silence timeout
        assert engine.state == "WAKING"

    def test_recorder_error_recovery(
        self, mock_voice_manager, mock_wake_detector, mock_audio_recorder
    ):
        # Setup recorder to raise an exception, verifying it is caught safely
        mock_audio_recorder.record_command.side_effect = RuntimeError("Mic disconnected")

        engine = AlwaysListeningEngine(
            voice_manager=mock_voice_manager,
            wake_detector=mock_wake_detector,
            audio_recorder=mock_audio_recorder,
            conversation_timeout=1.0
        )

        # Call record_safely and check that it returns None (graceful capture)
        path = engine._record_safely(2.0)
        assert path is None
