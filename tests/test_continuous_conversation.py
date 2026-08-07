"""
tests/test_continuous_conversation.py
--------------------------------------
Unit and integration tests verifying continuous conversation mode in VoiceManager.
"""

import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from voice.voice_manager import VoiceManager
from voice.speech_to_text import MockSTT
from tools.voice import VoiceTool


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.handle_input.return_value = "Success: Done."
    return engine


@pytest.fixture
def dummy_wav(tmp_path):
    wav = tmp_path / "continuous_test.wav"
    wav.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80\x3e\x00\x00\x00\x7d\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
    yield wav
    if wav.exists():
        try:
            wav.unlink()
        except Exception:
            pass


def _wait_for_stop(manager, timeout=2.0):
    start_t = time.time()
    while manager.is_active and time.time() - start_t < timeout:
        time.sleep(0.05)


def test_conversation_wake_word_leads_to_cheppandi(mock_engine, dummy_wav):
    """Verify that wake word detection triggers 'చెప్పండి.' and transitions to WAITING state."""
    stt = MockSTT("hey nova")
    
    with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
        manager = VoiceManager(
            engine=mock_engine,
            stt_engine=stt,
            wake_word_enabled=True,
            voice_input_enabled=True
        )
        
        # Mock recorder to return dummy_wav for wake word, then stop in second call (to avoid loop)
        call_count = 0
        def mock_record(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Recreate dummy file because VoiceManager unlinks it after processing
                dummy_wav.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80\x3e\x00\x00\x00\x7d\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
                return dummy_wav
            else:
                # Inside WAITING state, exit loop
                manager.stop()
                return None
                
        manager.recorder.record_command = MagicMock(side_effect=mock_record)
        
        with patch.object(VoiceTool, "execute") as mock_speak:
            manager.start()
            _wait_for_stop(manager)
            
            # Should have stopped
            assert manager.is_active is False
            # Verify the wake word detection spoke "చెప్పండి."
            mock_speak.assert_any_call(text="చెప్పండి.")


def test_conversation_mode_multiple_commands(mock_engine, dummy_wav):
    """Verify that in Conversation Mode, multiple commands are executed and followed by 'ఇంకేమైనా?'."""
    stt_responses = ["hey nova", "open chrome", "open notepad", ""]
    stt_iter = iter(stt_responses)
    
    class IterSTT(MockSTT):
        def transcribe(self, audio_path, stop_event=None):
            val = next(stt_iter)
            return val

    stt = IterSTT()
    
    with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
        manager = VoiceManager(
            engine=mock_engine,
            stt_engine=stt,
            wake_word_enabled=True,
            voice_input_enabled=True
        )
        
        call_count = 0
        def mock_record(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                # Recreate dummy file because VoiceManager unlinks it after processing
                dummy_wav.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80\x3e\x00\x00\x00\x7d\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
                return dummy_wav
            else:
                manager.stop()
                return None
                
        manager.recorder.record_command = MagicMock(side_effect=mock_record)
        
        with patch.object(VoiceTool, "execute") as mock_speak:
            manager.start()
            _wait_for_stop(manager, timeout=3.0)
            
            assert manager.is_active is False
            # Verify engine was called for the actual commands
            mock_engine.handle_input.assert_any_call("open chrome", stream=False)
            mock_engine.handle_input.assert_any_call("open notepad", stream=False)
            
            # Verify 'ఇంకేమైనా?' was spoken after first successful command
            mock_speak.assert_any_call(text="ఇంకేమైనా?")


@pytest.mark.parametrize("exit_word", ["bye", "goodbye", "stop listening", "thank you", "cancel", "సరే", "చాలు", "బై"])
def test_conversation_mode_exit_commands(mock_engine, dummy_wav, exit_word):
    """Verify that saying any exit command speaks 'సరే.' and returns to WAKING mode."""
    stt_responses = ["hey nova", exit_word, ""]
    stt_iter = iter(stt_responses)
    
    class IterSTT(MockSTT):
        def transcribe(self, audio_path, stop_event=None):
            val = next(stt_iter)
            return val

    stt = IterSTT()
    
    with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
        manager = VoiceManager(
            engine=mock_engine,
            stt_engine=stt,
            wake_word_enabled=True,
            voice_input_enabled=True
        )
        
        call_count = 0
        def mock_record(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                # Recreate dummy file because VoiceManager unlinks it after processing
                dummy_wav.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80\x3e\x00\x00\x00\x7d\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
                return dummy_wav
            else:
                manager.stop()
                return None
                
        manager.recorder.record_command = MagicMock(side_effect=mock_record)
        
        with patch.object(VoiceTool, "execute") as mock_speak:
            manager.start()
            _wait_for_stop(manager)
            
            assert manager.is_active is False
            # Verify 'సరే.' was spoken on exit
            mock_speak.assert_any_call(text="సరే.")


def test_conversation_mode_timeout(mock_engine, dummy_wav):
    """Verify that 20 seconds timeout is used in WAITING state, and returns to WAKING if no input."""
    # First call: WAKING state detects "hey nova"
    # Second call: WAITING state times out (returns None)
    stt = MockSTT("hey nova")
    
    with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
        manager = VoiceManager(
            engine=mock_engine,
            stt_engine=stt,
            wake_word_enabled=True,
            voice_input_enabled=True
        )
        
        call_count = 0
        def mock_record(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Recreate dummy file because VoiceManager unlinks it after processing
                dummy_wav.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80\x3e\x00\x00\x00\x7d\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
                return dummy_wav
            else:
                # Timeout / empty input simulation
                manager.stop()
                return None
                
        manager.recorder.record_command = MagicMock(side_effect=mock_record)
        
        with patch.object(VoiceTool, "execute") as mock_speak:
            manager.start()
            _wait_for_stop(manager)
            
            assert manager.is_active is False
            
            # Verify that the WAITING state record_command was called with max_record_seconds=20.0
            manager.recorder.record_command.assert_any_call(stop_event=manager._stop_event, max_record_seconds=20.0)
