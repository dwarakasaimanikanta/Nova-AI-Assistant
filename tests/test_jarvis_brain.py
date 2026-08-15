"""
tests/test_jarvis_brain.py
--------------------------
Integration tests for the Phase 3 Jarvis-level execution brain.
Validates the authoritative unified pipeline, structured ActionResult responses,
contextual pronoun resolution, language locks, and safety mechanisms.
"""

import pytest
import os
import shutil
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.executive_agent import ExecutiveAgent, ExecutionStatus
from core.action_result import ActionResult
from core.language_session import LanguageSession
from core.conversation_context import get_conversation_context
from tools.file_manager import FileManagerTool
from tools.system_control import SystemControlTool
from tools.browser import BrowserTool
from core.engine import NovaEngine
from memory.short_term import ShortTermMemory


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset singletons and global contexts between tests."""
    LanguageSession().selected_language = "en"
    get_conversation_context().reset()
    yield


# 1. "What is Python?"
def test_what_is_python():
    """Verify that general AI questions route directly to conversational LLM fallback."""
    mock_engine = MagicMock()
    mock_engine.handle_input.return_value = "Python is a high-level programming language."
    mock_engine.selected_language = "en"
    mock_engine.telugu_mode = False
    
    executive = ExecutiveAgent(engine=mock_engine)
    res = executive.execute("What is Python?")
    
    mock_engine.handle_input.assert_called_with("What is Python?", stream=False, intent_category="KNOWLEDGE")


# 2. "Open YouTube"
def test_open_youtube():
    """Verify 'Open YouTube' triggers the browser automation tool via BrowserManager."""
    mock_manager = MagicMock()
    mock_manager.open_url.return_value = "Success: Navigated to 'https://www.youtube.com'."
    
    tool = BrowserTool(manager=mock_manager)
    res = tool.execute(action="open_youtube")
    
    assert isinstance(res, ActionResult)
    assert res.success is True
    assert res.action == "open_youtube"
    assert res.target == "youtube"
    assert "Success" in res.details
    mock_manager.open_url.assert_called_with("https://www.youtube.com")


# 3. "Open Chrome"
@patch("subprocess.Popen")
@patch("shutil.which")
@patch("os.path.exists")
def test_open_chrome(mock_exists, mock_which, mock_popen):
    """Verify 'Open Chrome' correctly detects and launches the chrome executable."""
    mock_exists.return_value = True
    mock_which.return_value = "chrome.exe"
    mock_popen.return_value.poll.return_value = None  # running
    
    tool = SystemControlTool()
    res = tool.execute(action="launch_app", app_name="chrome")
    
    assert isinstance(res, ActionResult)
    assert res.success is True
    assert res.action == "launch_app"
    assert res.target == "chrome"
    assert res.verification["pid_running"] is True


# 4. "Create folder NovaTest"
def test_create_folder_novatest(tmp_path):
    """Verify folder creation is executed and post-verified using the ActionResult structure."""
    test_dir = tmp_path / "NovaTest"
    assert not test_dir.exists()
    
    with patch("tools.file_manager.resolve_path", return_value=test_dir):
        tool = FileManagerTool()
        res = tool.execute(action="create_folder", path=str(test_dir))
        
        assert isinstance(res, ActionResult)
        assert res.success is True
        assert res.action == "create_folder"
        assert res.target == str(test_dir)
        assert test_dir.exists()
        assert test_dir.is_dir()


# 5. "Create README.txt inside NovaTest"
def test_create_readme_inside_novatest(tmp_path):
    """Verify file creation is executed and verified inside the target folder."""
    test_dir = tmp_path / "NovaTest"
    test_dir.mkdir()
    readme = test_dir / "README.txt"
    
    with patch("tools.file_manager.resolve_path", return_value=readme):
        tool = FileManagerTool()
        res = tool.execute(action="create_file", path=str(readme))
        
        assert isinstance(res, ActionResult)
        assert res.success is True
        assert readme.exists()
        assert readme.is_file()


# 6. Multi-step folder + files
def test_multi_step_plan():
    """Verify that composite goals generate plans, execute sequentially, and verify step outcomes."""
    mock_engine = MagicMock()
    mock_engine.handle_input.side_effect = [
        ActionResult(success=True, action="create_folder", target="NovaProject", details="Folder created."),
        ActionResult(success=True, action="create_file", target="README.md", details="File created.")
    ]
    mock_engine.selected_language = "en"
    mock_engine.telugu_mode = False
    
    executive = ExecutiveAgent(engine=mock_engine)
    res = executive.execute("Create a project folder NovaProject and then create README.md inside it.")
    
    assert res.status == ExecutionStatus.SUCCESS
    assert res.steps_executed == 2
    assert res.steps_succeeded == 2
    assert "Success" in res.final_response


# 7. Failed application launch
@patch("shutil.which")
def test_failed_app_launch(mock_which):
    """Verify that launching a non-existent application returns a verified failure ActionResult."""
    mock_which.return_value = None  # app not found in system path
    
    tool = SystemControlTool()
    res = tool.execute(action="launch_app", app_name="nonexistent_app")
    
    assert isinstance(res, ActionResult)
    assert res.success is False
    assert "not found" in res.error


# 8. Failed filesystem operation
def test_failed_file_op(tmp_path):
    """Verify that trying to write to an invalid or read-only path returns a verified failure ActionResult."""
    invalid_path = tmp_path / "nonexistent_dir" / "README.txt"
    # We patch resolve_path to point to an unreachable location without parent folder creation
    with patch("tools.file_manager.resolve_path", return_value=invalid_path):
        with patch("pathlib.Path.parent") as mock_parent:
            # force mkdir to throw permission error
            mock_parent.mkdir.side_effect = PermissionError("Access Denied")
            tool = FileManagerTool()
            res = tool.execute(action="write", path=str(invalid_path), content="Test")
            
            assert isinstance(res, ActionResult)
            assert res.success is False
            assert "Access Denied" in res.error


# 9. Stop/cancellation
def test_stop_cancellation():
    """Verify that the STOP priority command cancels sequential execution immediately."""
    mock_engine = MagicMock()
    mock_engine.selected_language = "en"
    mock_engine.telugu_mode = False
    
    executive = ExecutiveAgent(engine=mock_engine)
    
    # Send a STOP command directly to execute
    res = executive.execute("Stop")
    
    assert res.plan_id == "stop_interrupt"
    assert res.status == ExecutionStatus.SUCCESS
    assert "Stopped" in res.final_response


# 10. Contextual command "open it"
def test_contextual_open_it():
    """Verify pronoun resolution resolves 'open it' using last folder or app in ConversationContext."""
    ctx = get_conversation_context()
    ctx.update("create folder NovaTest", "Success")
    
    resolved = ctx.resolve_follow_up("open it")
    assert resolved == "open folder NovaTest"
    
    ctx.reset()
    ctx.update("launch notepad", "Success")
    resolved = ctx.resolve_follow_up("open it")
    assert resolved == "open notepad"


# 11. Telugu response-language persistence
def test_telugu_persistence():
    """Verify that selected output language remains locked across sequential queries."""
    LanguageSession().selected_language = "te"
    assert LanguageSession().selected_language == "te"
    
    # Assert persistence behaves correctly under singleton lock
    mock_engine = MagicMock()
    mock_engine.selected_language = "te"
    mock_engine.telugu_mode = True
    
    executive = ExecutiveAgent(engine=mock_engine)
    
    # User asks in English, but engine persists in Telugu
    res = executive.execute("What is Python?")
    assert LanguageSession().selected_language == "te"


# 12. Explicit language switching
def test_explicit_language_switch():
    """Verify explicit switch phrasing updates the LanguageSession singleton language lock."""
    mock_engine = MagicMock()
    mock_engine.selected_language = "en"
    
    executive = ExecutiveAgent(engine=mock_engine)
    res = executive.execute("Switch to Telugu.")
    
    assert LanguageSession().selected_language == "te"
    assert "తెలుగులో మాట్లాడతాను" in res.final_response


# 13. Nova TTS self-capture protection
def test_tts_self_capture():
    """Verify that spoken TTS output containing high word overlap suppresses activation loops."""
    from voice.always_listening import AlwaysListeningEngine
    
    # Mocking AlwaysListeningEngine and SpeechController
    mock_speech = MagicMock()
    mock_speech.currently_speaking_text = "I will speak in English now"
    
    mock_voice = MagicMock()
    mock_voice.speech_controller = mock_speech
    
    mock_wake = MagicMock()
    mock_recorder = MagicMock()
    
    # If users say the exact same words, AlwaysListening suppresses it
    listening = AlwaysListeningEngine(
        voice_manager=mock_voice,
        wake_detector=mock_wake,
        audio_recorder=mock_recorder
    )
    
    # 1. Exact overlap should return True (is echo)
    assert listening._is_echo("I will speak in English now") is True
    
    # 2. Overlap of stop word should return False (allow barge-in)
    assert listening._is_echo("Stop") is False
    assert listening._is_echo("Cancel") is False
    
    # 3. Random phrase should return False (allow command)
    assert listening._is_echo("create a folder") is False
