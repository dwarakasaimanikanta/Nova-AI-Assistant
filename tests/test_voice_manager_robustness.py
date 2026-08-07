"""
tests/test_voice_manager_robustness.py
---------------------------------------
Unit and regression tests verifying that VoiceManager background thread recovers
from AndroidTool failures, Browser failures, STT exceptions, TTS exceptions,
and recording timeouts/exceptions without terminating.
"""

import os
import queue
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from voice.audio_recorder import AudioRecorder
from voice.speech_to_text import MockSTT
from voice.voice_manager import VoiceManager
from tools.voice import VoiceTool


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.handle_input.return_value = "Success: Done."
    return engine


@pytest.fixture
def mock_stt():
    return MockSTT("hello mock command")


@pytest.fixture
def dummy_wav(tmp_path):
    wav = tmp_path / "robustness_test.wav"
    wav.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80\x3e\x00\x00\x00\x7d\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
    yield wav
    if wav.exists():
        try:
            wav.unlink()
        except Exception:
            pass


def test_voice_manager_recovers_on_tts_failure(mock_engine, mock_stt, dummy_wav):
    """Verify that if TTS fails (e.g. raising an exception), VoiceManager recovers and does not terminate."""
    with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
        manager = VoiceManager(
            engine=mock_engine,
            stt_engine=mock_stt,
            wake_word_enabled=False,
            voice_input_enabled=True
        )
        
        # Mock recorder to yield dummy_wav once, then stop
        def mock_record(*args, **kwargs):
            manager.stop()
            return dummy_wav
        
        manager.recorder.record_command = MagicMock(side_effect=mock_record)
        
        # Make TTS throw exception
        with patch.object(VoiceTool, "execute", side_effect=RuntimeError("TTS Device Locked")):
            manager.start()
            # Let it run
            time.sleep(0.3)
            
            # The manager shouldn't crash and should still be stopped gracefully
            assert manager.is_active is False
            # Engine handle_input should still have been called because execution is independent of TTS speaking
            mock_engine.handle_input.assert_called_with("hello mock command", stream=False)


def test_voice_manager_recovers_on_stt_failure(mock_engine, dummy_wav):
    """Verify that if STT raises an exception, VoiceManager recovers and prompts retry/continues."""
    failing_stt = MockSTT("error")
    # Force transcribe to throw exception
    failing_stt.transcribe = MagicMock(side_effect=ValueError("Model load failed"))
    
    with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
        manager = VoiceManager(
            engine=mock_engine,
            stt_engine=failing_stt,
            wake_word_enabled=False,
            voice_input_enabled=True
        )
        
        def mock_record(*args, **kwargs):
            manager.stop()
            return dummy_wav
            
        manager.recorder.record_command = MagicMock(side_effect=mock_record)
        
        with patch.object(VoiceTool, "execute") as mock_speak:
            manager.start()
            time.sleep(0.3)
            
            # Verify manager did not raise/terminate thread prematurely
            assert manager.is_active is False
            # Because STT failed, transcription returns empty, and it transitions via empty transcript logic
            mock_speak.assert_any_call(text="I didn't catch that. Could you repeat?")


def test_voice_manager_recovers_on_engine_failure(mock_stt, dummy_wav):
    """Verify that if the Engine handle_input raises an exception (e.g. subprocess error in tool), VoiceManager recovers."""
    failing_engine = MagicMock()
    failing_engine.handle_input.side_effect = RuntimeError("ADB tool crash / process timeout")
    
    with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
        manager = VoiceManager(
            engine=failing_engine,
            stt_engine=mock_stt,
            wake_word_enabled=False,
            voice_input_enabled=True
        )
        
        def mock_record(*args, **kwargs):
            manager.stop()
            return dummy_wav
            
        manager.recorder.record_command = MagicMock(side_effect=mock_record)
        
        with patch.object(VoiceTool, "execute") as mock_speak:
            manager.start()
            time.sleep(0.3)
            
            assert manager.is_active is False
            # It should have caught the exception and spoken a safe default formatted response or generic fallback
            # In LISTENING state, _safe_engine catches it and returns "Failure: An internal error occurred."
            # Which format_spoken_response turns into "క్షమించండి, అది చేయలేకపోయాను." (Sorry, couldn't do that)
            mock_speak.assert_any_call(text="క్షమించండి, అది చేయలేకపోయాను.")


def test_voice_manager_recovers_on_recorder_failure(mock_engine, mock_stt):
    """Verify that if the audio recorder itself raises an exception, the state machine continues to try."""
    with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
        manager = VoiceManager(
            engine=mock_engine,
            stt_engine=mock_stt,
            wake_word_enabled=False,
            voice_input_enabled=True
        )
        
        # First call fails, second call stops
        call_count = 0
        def mock_record(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("Audio Device Disconnected")
            else:
                manager.stop()
                return None
                
        manager.recorder.record_command = MagicMock(side_effect=mock_record)
        
        with patch.object(VoiceTool, "execute") as mock_speak:
            manager.start()
            time.sleep(0.3)
            
            assert manager.is_active is False
            # Verify the manager recovered from the OSError and ran the second time to stop cleanly.
            assert call_count == 2
