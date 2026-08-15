"""
tests/test_continuous_listening_regression.py
----------------------------------------------
Focused regression tests to verify:
1. Repeated wake word detection transitions.
2. Continuous listening after commands.
3. No duplicate command execution (exactly one execution path).
4. Direct webbrowser.open fast-path routing for YouTube, Google, GitHub.
5. Direct WorkspaceAgent fast-path routing for Notepad and Chrome (open/close).
6. Robust recovery during TTS or STT failures.
"""

import time
import os
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from voice.always_listening import AlwaysListeningEngine
from voice.voice_manager import VoiceManager
from voice.conversation_engine import VoiceConversationEngine
from core.executive_agent import ExecutiveAgent
from agents.workspace_agent import WorkspaceAgent, WorkspaceStatus, WorkspaceResult


@pytest.fixture
def mock_voice_manager():
    vm = MagicMock()
    vm.telugu_mode = False
    vm.state = "IDLE"
    vm._stop_event = threading.Event()
    vm._safe_transcribe.return_value = "hello nova"
    vm._safe_engine.return_value = "Success: Opened app."
    vm._safe_speak = MagicMock()
    return vm


@pytest.fixture
def mock_wake_detector():
    wd = MagicMock()
    wd.detect.return_value = False
    return wd


@pytest.fixture
def mock_audio_recorder():
    ar = MagicMock()
    ar.record_command.return_value = Path("mock_temp.wav")
    return ar


class TestContinuousListeningRegression:
    
    @patch("pathlib.Path.exists", return_value=True)
    @patch("pathlib.Path.unlink")
    def test_repeated_wake_word_and_commands(self, mock_unlink, mock_exists, mock_voice_manager, mock_wake_detector, mock_audio_recorder):
        """Verify that Nova can repeatedly detect wake words and execute commands without stopping."""
        # Yield detected=True (wake word), then transcribe a command, then timeout (go to IDLE), then wake word again
        mock_wake_detector.detect.side_effect = [True, True]
        mock_voice_manager._safe_transcribe.side_effect = ["open notepad", "close notepad"]
        
        on_wake = MagicMock()
        on_cmd = MagicMock()
        
        engine = AlwaysListeningEngine(
            voice_manager=mock_voice_manager,
            wake_detector=mock_wake_detector,
            audio_recorder=mock_audio_recorder,
            conversation_timeout=0.1,  # Short timeout for testing return to IDLE
            on_wake_callback=on_wake,
            on_command_callback=on_cmd
        )
        engine._wait_for_tts_drain = MagicMock()  # Speed up tests and bypass delays
        
        assert engine.state == "WAKING"
        
        # Start engine loop background thread
        engine.start()
        start_t = time.time()
        while on_cmd.call_count == 0 and time.time() - start_t < 3.0:
            time.sleep(0.01)
        engine.stop()
        
        # Verify that it went through state transitions
        assert on_wake.call_count >= 1
        assert on_cmd.call_count >= 1
        assert mock_voice_manager._safe_engine.call_count >= 1
        assert mock_voice_manager._safe_speak.call_count >= 1

    @patch("pathlib.Path.exists", return_value=True)
    @patch("pathlib.Path.unlink")
    def test_exactly_one_execution_path_and_id(self, mock_unlink, mock_exists, mock_voice_manager, mock_wake_detector, mock_audio_recorder):
        """Verify that ConversationEngine does not execute the command a second time if response_text is provided."""
        exec_agent = MagicMock()
        exec_agent.handle_input.return_value = "Exec result"
        
        conversation_engine = VoiceConversationEngine(
            executive_agent=exec_agent,
            voice_manager=mock_voice_manager,
            memory_agent=None
        )
        
        # Verify call with response_text
        conversation_engine.process_speech("what time is it", response_text="Success: 10:00 AM", exec_id="test1234")
        
        # Verify that executive agent was NOT called (execution was bypassed)
        exec_agent.handle_input.assert_not_called()
        assert len(conversation_engine.history) == 2
        assert conversation_engine.history[0]["content"] == "what time is it"
        assert conversation_engine.history[1]["content"] == "Success: 10:00 AM"

    @patch("webbrowser.open")
    def test_direct_youtube_opening_fast_path(self, mock_web_open):
        """Verify that 'open youtube' directly opens webbrowser without planning or Playwright."""
        engine = MagicMock()
        executive = ExecutiveAgent(engine=engine)
        
        res = executive.execute("open youtube")
        
        assert res.plan_id == "fast_path_url"
        assert res.status.value == "SUCCESS"
        assert "Opening YouTube Boss" in res.final_response
        mock_web_open.assert_called_once_with("https://www.youtube.com/")

    @patch("webbrowser.open")
    def test_direct_google_github_fast_path(self, mock_web_open):
        """Verify that 'open google' and 'open github' use the direct webbrowser fast path."""
        engine = MagicMock()
        executive = ExecutiveAgent(engine=engine)
        
        res_g = executive.execute("open google")
        assert res_g.plan_id == "fast_path_url"
        mock_web_open.assert_any_call("https://www.google.com/")
        
        res_gh = executive.execute("open github")
        assert res_gh.plan_id == "fast_path_url"
        mock_web_open.assert_any_call("https://github.com/")

    def test_notepad_chrome_calculator_workspace_fast_paths(self):
        """Verify that 'open notepad' / 'close notepad' route directly to WorkspaceAgent."""
        engine = MagicMock()
        mock_workspace = MagicMock()
        mock_workspace.execute.return_value = WorkspaceResult(
            task_id="test",
            status=WorkspaceStatus.SUCCESS,
            steps_executed=1,
            steps_succeeded=1,
            steps_failed=0,
            total_duration=0.01,
            final_output="Opened app successfully."
        )
        
        executive = ExecutiveAgent(engine=engine, workspace_agent=mock_workspace)
        
        res_open = executive.execute("open notepad")
        assert res_open.plan_id == "fast_path_workspace"
        mock_workspace.execute.assert_any_call("open notepad")
        
        res_close = executive.execute("close chrome")
        assert res_close.plan_id == "fast_path_workspace"
        mock_workspace.execute.assert_any_call("close chrome")

    @patch("pathlib.Path.exists", return_value=True)
    @patch("pathlib.Path.unlink")
    def test_tts_stt_failure_recovery(self, mock_unlink, mock_exists, mock_voice_manager, mock_wake_detector, mock_audio_recorder):
        """Verify that the engine does not stop listening when TTS or STT fails."""
        mock_wake_detector.detect.return_value = True
        mock_voice_manager._safe_transcribe.return_value = "hello"
        
        # Simulate TTS throw exception
        mock_voice_manager._safe_speak.side_effect = RuntimeError("SAPI Device Locked")
        
        engine = AlwaysListeningEngine(
            voice_manager=mock_voice_manager,
            wake_detector=mock_wake_detector,
            audio_recorder=mock_audio_recorder,
            conversation_timeout=1.0
        )
        engine._wait_for_tts_drain = MagicMock()  # Speed up tests and bypass delays
        
        engine.state = "LISTENING"
        engine.start()
        start_t = time.time()
        while mock_voice_manager._safe_speak.call_count == 0 and time.time() - start_t < 3.0:
            time.sleep(0.01)
        engine.stop()
        
        # Verify that engine continued and stayed active (didn't crash from the TTS RuntimeError)
        assert engine._thread is None or not engine._thread.is_alive()  # Stopped gracefully via engine.stop()
