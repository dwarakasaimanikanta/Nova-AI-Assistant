"""
tests/test_voice_input.py
-------------------------
Unit tests for Nova's hands-free voice input system (Speech-to-Text & Wake Word).
"""

import os
import queue
import time
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import numpy as np

from voice.audio_recorder import AudioRecorder, SOUNDDEVICE_AVAILABLE
from voice.speech_to_text import MockSTT, FasterWhisperSTT
from voice.wake_word import WakeWordDetector
from voice.voice_manager import VoiceManager
from tools.voice import VoiceTool


def test_audio_recorder_mock_fallback(tmp_path: Path) -> None:
    """Ensure AudioRecorder creates a valid mock silent WAV file if sounddevice is unavailable/mocked."""
    recorder = AudioRecorder(samplerate=16000)
    
    # We patch SOUNDDEVICE_AVAILABLE to False to force fallback/mock behavior
    with patch("voice.audio_recorder.SOUNDDEVICE_AVAILABLE", False):
        wav_path = recorder.record_command()
        
        assert wav_path is not None
        assert wav_path.exists()
        
        # Verify it's a valid WAV file with correct parameters
        with wave.open(str(wav_path), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000
            
        # Clean up
        if wav_path.exists():
            wav_path.unlink()


@patch("voice.audio_recorder.SOUNDDEVICE_AVAILABLE", True)
@patch("sounddevice.InputStream")
def test_audio_recorder_active_recording(mock_input_stream: MagicMock, tmp_path: Path) -> None:
    """Ensure AudioRecorder monitors amplitude and returns recording when speech ends."""
    recorder = AudioRecorder(samplerate=16000, blocksize=512, silence_duration=0.2, threshold=0.01)
    
    silent_chunk = np.zeros((512, 1), dtype=np.float32)
    loud_chunk = np.ones((512, 1), dtype=np.float32) * 0.1
    
    chunks = [silent_chunk, loud_chunk] + [silent_chunk] * 8
    chunk_iter = iter(chunks)
    
    def mock_get(timeout=None):
        try:
            return next(chunk_iter)
        except StopIteration:
            raise queue.Empty
            
    recorder.audio_queue.get = mock_get
        
    wav_path = recorder.record_command()
    assert wav_path is not None
    assert wav_path.exists()
    
    with wave.open(str(wav_path), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 16000
        
    if wav_path.exists():
        wav_path.unlink()


def test_speech_to_text_mock() -> None:
    """Ensure MockSTT returns the configured transcription string."""
    stt = MockSTT(predefined_response="hey nova activate")
    res = stt.transcribe(Path("dummy.wav"))
    assert res == "hey nova activate"


@patch("faster_whisper.WhisperModel")
def test_faster_whisper_transcription(mock_whisper_model: MagicMock, tmp_path: Path) -> None:
    """Ensure FasterWhisperSTT transcribes audio segments correctly."""
    # Setup mock segment iterator
    mock_segment = MagicMock()
    mock_segment.text = "hello world from voice"
    
    mock_model_instance = MagicMock()
    mock_model_instance.transcribe.return_value = ([mock_segment], None)
    mock_whisper_model.return_value = mock_model_instance
    
    stt = FasterWhisperSTT(model_size="tiny")
    
    # Create temporary WAV to transcribe
    audio_file = tmp_path / "test.wav"
    with wave.open(str(audio_file), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00" * 3200)
        
    res = stt.transcribe(audio_file)
    assert res == "hello world from voice"
    
    if audio_file.exists():
        audio_file.unlink()


def test_wake_word_detector() -> None:
    """Ensure WakeWordDetector flags positive and negative wake word triggers."""
    stt = MockSTT("Hey Nova, what time is it?")
    detector = WakeWordDetector(stt_engine=stt, wake_word="hey nova")
    
    assert detector.detect(Path("dummy.wav")) is True
    
    stt_neg = MockSTT("Hello, what is the weather today?")
    detector_neg = WakeWordDetector(stt_engine=stt_neg, wake_word="hey nova")
    
    assert detector_neg.detect(Path("dummy.wav")) is False


def test_voice_manager_lifecycle(tmp_path: Path) -> None:
    """Ensure VoiceManager starts and stops cleanly, and runs processing logic on capture."""
    mock_engine = MagicMock()
    mock_engine.handle_input.return_value = "Responding to spoken command."
    
    stt = MockSTT("tell me a joke")
    
    # Set ENVIRONMENT to test to avoid loading FasterWhisperSTT during manager init
    with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
        manager = VoiceManager(
            engine=mock_engine,
            stt_engine=stt,
            wake_word_enabled=False,
            voice_input_enabled=True
        )
        
        # Mock recorder to return a valid temp file, then stop loop to prevent infinite loop
        dummy_wav = tmp_path / "test_lifecycle.wav"
        with wave.open(str(dummy_wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00" * 3200)
            
        manager.recorder.record_command = MagicMock(return_value=dummy_wav)
        
        # Patch VoiceTool.execute to prevent sound synthesis in test runs
        with patch.object(VoiceTool, "execute") as mock_tts:
            # We want to check that it executes handle_input, then stops
            # We mock the loop to run once and then stop the manager
            orig_run_loop = manager._run_loop
            
            def run_once():
                # Run the state machine block once
                manager._run_loop()
                
            # Set stop event after first record
            def mock_record_side_effect(*args, **kwargs):
                manager.stop()
                return dummy_wav
                
            manager.recorder.record_command.side_effect = mock_record_side_effect
            
            # Start manager background thread
            manager.start()
            
            # Wait for thread to finish since recorder stops it
            time.sleep(0.5)
            
            # Verify clean shutdown
            assert manager.is_active is False
            
            # Verify engine was called with text from MockSTT
            mock_engine.handle_input.assert_called_with("tell me a joke", stream=False)
            
            # Verify speech synthesis tool spoke response back
            mock_tts.assert_called_with(text="Responding to spoken command.")
            
        if dummy_wav.exists():
            dummy_wav.unlink()
