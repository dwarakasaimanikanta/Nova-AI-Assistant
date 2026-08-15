import pytest
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch
from voice.always_listening import AlwaysListeningEngine
from voice.voice_manager import VoiceManager

class DummyRecorder:
    def __init__(self):
        self.audio_queue = MagicMock()
    def record_command(self, *args, **kwargs):
        return Path("dummy.wav")

class DummyWakeDetector:
    pass

@pytest.fixture
def dummy_engine():
    m = MagicMock()
    m.handle_input.return_value = "Done"
    return m

def test_short_language_selection_simulations(dummy_engine):
    vm = VoiceManager(engine=dummy_engine, voice_input_enabled=True)
    recorder = DummyRecorder()
    wd = DummyWakeDetector()
    
    engine = AlwaysListeningEngine(
        voice_manager=vm,
        wake_detector=wd,
        audio_recorder=recorder,
    )
    engine._stop_event = threading.Event()

    def set_stop_event(*args, **kwargs):
        engine._stop_event.set()
        return Path("dummy.wav")

    # A. "Telugu" -> selected_language="te"
    engine._state = "LANGUAGE_SELECTION"
    engine._language_selection_retries = 0
    engine._stop_event.clear()
    with patch.object(engine, "_record_safely", side_effect=set_stop_event):
        with patch.object(vm, "_safe_transcribe", return_value="Telugu") as mock_trans:
            with patch.object(vm, "_safe_speak"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.unlink"):
                        engine._run_loop()
                        assert vm.selected_language == "te"
                        assert engine._state == "LISTENING"

    # B. "English" -> selected_language="en"
    engine._state = "LANGUAGE_SELECTION"
    engine._language_selection_retries = 0
    engine._stop_event.clear()
    with patch.object(engine, "_record_safely", side_effect=set_stop_event):
        with patch.object(vm, "_safe_transcribe", return_value="English") as mock_trans:
            with patch.object(vm, "_safe_speak"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.unlink"):
                        engine._run_loop()
                        assert vm.selected_language == "en"
                        assert engine._state == "LISTENING"

    # C. "Hindi" -> selected_language="hi"
    engine._state = "LANGUAGE_SELECTION"
    engine._language_selection_retries = 0
    engine._stop_event.clear()
    with patch.object(engine, "_record_safely", side_effect=set_stop_event):
        with patch.object(vm, "_safe_transcribe", return_value="Hindi") as mock_trans:
            with patch.object(vm, "_safe_speak"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.unlink"):
                        engine._run_loop()
                        assert vm.selected_language == "hi"
                        assert engine._state == "LISTENING"

    # D. "Tamil" -> selected_language="ta"
    engine._state = "LANGUAGE_SELECTION"
    engine._language_selection_retries = 0
    engine._stop_event.clear()
    with patch.object(engine, "_record_safely", side_effect=set_stop_event):
        with patch.object(vm, "_safe_transcribe", return_value="Tamil") as mock_trans:
            with patch.object(vm, "_safe_speak"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.unlink"):
                        engine._run_loop()
                        assert vm.selected_language == "ta"
                        assert engine._state == "LISTENING"

    # E. "Kannada" -> selected_language="kn"
    engine._state = "LANGUAGE_SELECTION"
    engine._language_selection_retries = 0
    engine._stop_event.clear()
    with patch.object(engine, "_record_safely", side_effect=set_stop_event):
        with patch.object(vm, "_safe_transcribe", return_value="Kannada") as mock_trans:
            with patch.object(vm, "_safe_speak"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.unlink"):
                        engine._run_loop()
                        assert vm.selected_language == "kn"
                        assert engine._state == "LISTENING"

    # F. empty transcript -> retry
    engine._state = "LANGUAGE_SELECTION"
    engine._language_selection_retries = 0
    engine._stop_event.clear()
    with patch.object(engine, "_record_safely", side_effect=set_stop_event):
        with patch.object(vm, "_safe_transcribe", return_value="") as mock_trans:
            with patch.object(vm, "_safe_speak"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.unlink"):
                        engine._run_loop()
                        assert engine._state == "LANGUAGE_SELECTION"
                        assert engine._language_selection_retries == 1

    # G. unrelated transcript -> retry
    engine._state = "LANGUAGE_SELECTION"
    engine._language_selection_retries = 0
    engine._stop_event.clear()
    with patch.object(engine, "_record_safely", side_effect=set_stop_event):
        with patch.object(vm, "_safe_transcribe", return_value="something completely different") as mock_trans:
            with patch.object(vm, "_safe_speak"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.unlink"):
                        engine._run_loop()
                        assert engine._state == "LANGUAGE_SELECTION"
                        assert engine._language_selection_retries == 1

    # H. maximum retries -> IDLE
    engine._state = "LANGUAGE_SELECTION"
    engine._language_selection_retries = 2
    engine._stop_event.clear()
    with patch.object(engine, "_record_safely", side_effect=set_stop_event):
        with patch.object(vm, "_safe_transcribe", return_value="") as mock_trans:
            with patch.object(vm, "_safe_speak"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.unlink"):
                        engine._run_loop()
                        assert engine._state == "IDLE"
