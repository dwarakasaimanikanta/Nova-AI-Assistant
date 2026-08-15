"""
tests/test_shutdown_regression.py
----------------------------------
Regression tests to verify clean and immediate shutdown (within 2 seconds) when stop_event
is set or KeyboardInterrupt occurs during recording, STT, TTS, and engine execution.
"""

import os
import time
import threading
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from voice.audio_recorder import AudioRecorder
from voice.speech_to_text import FasterWhisperSTT
from voice.voice_manager import VoiceManager
from tools.voice import VoiceTool
from tools.android_tool import AndroidTool


@patch("sounddevice.InputStream")
def test_ctrl_c_during_recording(mock_input_stream):
    """Verify that recording aborts immediately when stop_event is set (Ctrl+C emulation)."""
    recorder = AudioRecorder()
    stop_event = threading.Event()

    # Set stop_event immediately
    stop_event.set()

    start_time = time.time()
    # Should exit immediately and return None or mock wav because stop_event is set
    res = recorder.record_command(stop_event=stop_event)
    duration = time.time() - start_time

    assert duration < 2.0
    # Res should be None because stop_event was set before/during active recording
    assert res is None or isinstance(res, Path)


def test_ctrl_c_during_stt():
    """Verify that transcription generator consumption is cancellable mid-generation via stop_event."""
    stt = FasterWhisperSTT(model_size="tiny")
    
    # Mock WhisperModel behavior
    mock_model = MagicMock()
    
    # Define a generator that simulates yielding transcription segments,
    # but we set the stop event after the first segment is yielded.
    stop_event = threading.Event()
    
    class MockSegment:
        def __init__(self, text):
            self.text = text
            self.no_speech_prob = 0.0
            self.avg_logprob = 0.0
            self.start = 0.0
            self.end = 1.0

    def mock_transcribe_gen(*args, **kwargs):
        yield MockSegment("first segment")
        stop_event.set()  # Emulate Ctrl+C/shutdown mid-iteration
        yield MockSegment("second segment")

    mock_model.transcribe.return_value = (mock_transcribe_gen(), MagicMock(language="en"))
    stt.model = mock_model

    start_time = time.time()
    result = stt.transcribe(Path("dummy.wav"), stop_event=stop_event)
    duration = time.time() - start_time

    assert duration < 2.0
    # Because stop_event was set, it should have returned early (empty string) or partial abort
    assert result == ""


def test_ctrl_c_during_tts():
    """Verify that TTS terminate/kill is triggered immediately on stop_event."""
    tts = VoiceTool()
    stop_event = threading.Event()
    
    with patch("tools.voice.platform.system", return_value="Linux"):
        with patch("shutil.which", return_value="aplay"):
            with patch.object(VoiceTool, "_generate_audio_sync") as mock_gen:
                # Create a dummy file to satisfy existence/size check
                def side_effect(text, voice, path):
                    with open(path, "w") as f:
                        f.write("dummy")
                mock_gen.side_effect = side_effect

                # We patch Popen to monitor termination/kill
                with patch("subprocess.Popen") as mock_popen:
                    mock_proc = MagicMock()
                    # Simulate process running
                    mock_proc.poll.side_effect = [None] * 50 + [0]
                    mock_popen.return_value = mock_proc
                    
                    # Trigger stop event in background after 50ms
                    def trigger_stop():
                        time.sleep(0.05)
                        stop_event.set()
                    
                    threading.Thread(target=trigger_stop, daemon=True).start()
                    
                    start_time = time.time()
                    res = tts.execute(text="Testing shutdown logic.", stop_event=stop_event)
                    duration = time.time() - start_time
                    
                    assert duration < 2.0
                    # Should call terminate/kill on the process when stop_event is set
                    mock_proc.terminate.assert_called_once()


def test_android_tool_timeout_and_no_hang():
    """Verify that ADB subprocess does not hang the caller forever."""
    tool = AndroidTool()
    
    with patch("subprocess.run") as mock_run:
        # Simulate subprocess timeout
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["adb"], timeout=10)
        
        start_time = time.time()
        res = tool.execute(action="call", contact="Amma")
        duration = time.time() - start_time
        
        assert duration < 2.0
        assert "timed out" in res.lower() or "failure" in res.lower()


def test_always_listening_shutdown_teardown():
    """Verify that AlwaysListeningEngine shutdown stops and joins the background thread successfully."""
    from voice.always_listening import AlwaysListeningEngine
    
    mock_vm = MagicMock()
    mock_wd = MagicMock()
    mock_rec = MagicMock()
    
    # We want it to loop at least once
    mock_rec.record_command.return_value = None
    
    engine = AlwaysListeningEngine(
        voice_manager=mock_vm,
        wake_detector=mock_wd,
        audio_recorder=mock_rec,
        conversation_timeout=1.0
    )
    
    engine.start()
    assert engine.running is True
    assert engine._thread is not None
    assert engine._thread.is_alive()
    
    active_thread_names = [t.name for t in threading.enumerate()]
    assert "AlwaysListeningThread" in active_thread_names
    
    engine.stop()
    
    assert engine.running is False
    assert engine._thread is None
    
    active_thread_names = [t.name for t in threading.enumerate()]
    assert "AlwaysListeningThread" not in active_thread_names


def test_wake_word_detect_honors_stop_event():
    """Verify that WakeWordDetector.detect() immediately exits and does not log when stop_event is set."""
    from voice.wake_word import WakeWordDetector
    import logging
    
    stt = MagicMock()
    detector = WakeWordDetector(stt_engine=stt)
    
    stop_event = threading.Event()
    stop_event.set()
    
    logger = logging.getLogger("voice.wake_word")
    log_spy = MagicMock()
    
    class SpyHandler(logging.Handler):
        def emit(self, record):
            log_spy(record.getMessage())
            
    handler = SpyHandler()
    logger.addHandler(handler)
    
    try:
        res = detector.detect(Path("dummy.wav"), stop_event=stop_event)
        assert res is False
        assert stt.transcribe.call_count == 0
        assert log_spy.call_count == 0
    finally:
        logger.removeHandler(handler)
