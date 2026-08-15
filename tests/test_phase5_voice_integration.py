import os
import shutil
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.boot_manager import BootManager
from core.language_session import LanguageSession
from core.conversation_context import get_conversation_context
from core.executive_agent import ExecutiveAgent, ExecutionStatus
from voice.conversation_engine import VoiceConversationEngine
from voice.speech_controller import SpeechController
from tools.permission_gate import PermissionGate
from tools.terminal import TerminalTool
from tools.file_manager import FileManagerTool
from tools.browser import BrowserTool

@pytest.fixture(autouse=True)
def setup_test_env():
    # Force test environment
    old_env = os.environ.get("ENVIRONMENT")
    os.environ["ENVIRONMENT"] = "test"
    ExecutiveAgent._processed_requests.clear()
    LanguageSession().selected_language = "en"
    ctx = get_conversation_context()
    ctx.reset()
    yield
    if old_env is not None:
        os.environ["ENVIRONMENT"] = old_env
    else:
        os.environ.pop("ENVIRONMENT", None)
    ExecutiveAgent._processed_requests.clear()
    LanguageSession().selected_language = "en"
    ctx.reset()


# 1. Voice transcript → Open Chrome
def test_voice_to_open_chrome():
    boot_mgr = BootManager()
    boot_mgr.boot()
    
    # Mock subprocess Popen for safe launching
    with patch("shutil.which", return_value="C:\\chrome.exe"), \
         patch("os.path.exists", return_value=True), \
         patch("subprocess.Popen") as mock_popen, \
         patch.object(boot_mgr.voice_manager, "_safe_speak") as mock_speak:
         
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        
        # Simulate voice command
        boot_mgr.conversation_engine.process_speech("Hey Nova, open Chrome")
        
        # Verify launch occurred
        mock_popen.assert_called_once()
        # Verify response spoken
        mock_speak.assert_called()
        spoken_res = mock_speak.call_args[0][0]
        assert "Chrome" in spoken_res or "Done" in spoken_res or "Opening" in spoken_res


# 2. Voice transcript → Open YouTube
def test_voice_to_open_youtube():
    boot_mgr = BootManager()
    boot_mgr.boot()
    
    # Mock web opening and agent routing
    with patch("webbrowser.open") as mock_web_open, \
         patch.object(boot_mgr.executive_agent.agent_registry.resolve("browser"), "execute") as mock_agent_exec, \
         patch.object(boot_mgr.voice_manager, "_safe_speak") as mock_speak:
         
        from core.executive_agent import ExecutionResult, ExecutionStatus
        mock_agent_exec.return_value = ExecutionResult(
            plan_id="test",
            status=ExecutionStatus.SUCCESS,
            final_response="Opened YouTube"
        )
        
        # Simulate voice command
        boot_mgr.conversation_engine.process_speech("Open YouTube")
        
        # Verify execution or speak
        mock_speak.assert_called()
        spoken_res = mock_speak.call_args[0][0]
        assert "YouTube" in spoken_res or "Opened" in spoken_res or "Done" in spoken_res


# 3. Voice transcript → Create folder
def test_voice_to_create_folder(tmp_path):
    boot_mgr = BootManager()
    boot_mgr.boot()
    
    test_folder = tmp_path / "NovaProject"
    
    with patch.object(boot_mgr.voice_manager, "_safe_speak") as mock_speak:
        # Simulate command
        boot_mgr.conversation_engine.process_speech(f"Create a folder called {test_folder.name} inside {test_folder.parent}")
        
        # Verify folder created
        assert test_folder.is_dir()
        # Verify spoken response
        mock_speak.assert_called()
        spoken_res = mock_speak.call_args[0][0]
        assert "Created" in spoken_res or "Done" in spoken_res


# 4. Voice transcript → Create file
def test_voice_to_create_file(tmp_path):
    boot_mgr = BootManager()
    boot_mgr.boot()
    
    test_file = tmp_path / "README.txt"
    
    with patch.object(boot_mgr.voice_manager, "_safe_speak") as mock_speak:
        # Simulate command
        boot_mgr.conversation_engine.process_speech(f"Create a file called {test_file.name} inside {test_file.parent}")
        
        # Verify file created
        assert test_file.is_file()
        # Verify spoken response
        mock_speak.assert_called()
        spoken_res = mock_speak.call_args[0][0]
        assert "Created" in spoken_res or "Done" in spoken_res


# 5. Voice transcript → Contextual "open it"
def test_voice_to_contextual_open_it(tmp_path):
    boot_mgr = BootManager()
    boot_mgr.boot()
    
    test_folder = tmp_path / "TargetFolder"
    test_folder.mkdir()
    
    # Preset context path
    ctx = get_conversation_context()
    ctx.last_created_path = str(test_folder)
    
    with patch("shutil.which", return_value="C:\\explorer.exe"), \
         patch("os.path.exists", return_value=True), \
         patch("subprocess.Popen") as mock_popen, \
         patch.object(boot_mgr.voice_manager, "_safe_speak") as mock_speak:
         
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        
        # Simulate follow-up command
        boot_mgr.conversation_engine.process_speech("Open it")
        
        # Verify launcher ran with explorer and the context folder path
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert str(test_folder) in args or any(str(test_folder) in a for a in args)


# 6. Voice transcript → General Python question
def test_voice_general_python_question():
    boot_mgr = BootManager()
    boot_mgr.boot()
    
    # Mock LLM engine call
    with patch.object(boot_mgr.executive_agent.engine, "handle_input") as mock_engine_handle, \
         patch.object(boot_mgr.voice_manager, "_safe_speak") as mock_speak:
         
        mock_engine_handle.return_value = "Python is a high-level programming language."
        
        # Simulate command
        boot_mgr.conversation_engine.process_speech("What is Python?")
        
        # Verify routed to LLM and not tool execution
        mock_engine_handle.assert_called_once()
        mock_speak.assert_called()
        spoken_res = mock_speak.call_args[0][0]
        assert "Python" in spoken_res


# 7. Voice transcript → Telugu response
def test_voice_telugu_response():
    boot_mgr = BootManager()
    boot_mgr.boot()
    
    # Set to Telugu mode
    LanguageSession().selected_language = "te"
    
    with patch.object(boot_mgr.executive_agent.engine, "handle_input") as mock_engine_handle, \
         patch.object(boot_mgr.voice_manager, "_safe_speak") as mock_speak:
         
        mock_engine_handle.return_value = "పైథాన్ అనేది ఒక ప్రోగ్రామింగ్ భాష."
        
        # Simulate query
        boot_mgr.conversation_engine.process_speech("What is Python?")
        
        # Verify engine received telugu instruction
        kwargs = mock_engine_handle.call_args.kwargs
        assert kwargs.get("selected_language") == "te"
        
        # Verify Telugu response spoken
        mock_speak.assert_called()
        spoken_res = mock_speak.call_args[0][0]
        assert "పైథాన్" in spoken_res


# 8. Voice transcript → English response (does not auto-overwrite)
def test_voice_english_response_no_auto_overwrite():
    boot_mgr = BootManager()
    boot_mgr.boot()
    
    # Set to English mode
    LanguageSession().selected_language = "en"
    
    with patch.object(boot_mgr.executive_agent.engine, "handle_input") as mock_engine_handle, \
         patch.object(boot_mgr.voice_manager, "_safe_speak") as mock_speak:
         
        mock_engine_handle.return_value = "Python is a programming language."
        
        # Simulate Telugu query
        boot_mgr.conversation_engine.process_speech("Python ante enti?")
        
        # Verify language did not switch automatically (remains English)
        assert LanguageSession().selected_language == "en"
        mock_speak.assert_called()
        spoken_res = mock_speak.call_args[0][0]
        assert "Python" in spoken_res


# 9. Explicit language switch
def test_explicit_language_switch():
    boot_mgr = BootManager()
    boot_mgr.boot()
    
    # Initially English
    LanguageSession().selected_language = "en"
    
    with patch.object(boot_mgr.voice_manager, "_safe_speak") as mock_speak:
        # Send explicit language switch command
        boot_mgr.conversation_engine.process_speech("switch to Telugu")
        
        # Verify language switched
        assert LanguageSession().selected_language == "te"
        mock_speak.assert_called()
        spoken_res = mock_speak.call_args[0][0]
        assert "తెలుగులో" in spoken_res or "Telugu" in spoken_res


# 10. Stop during TTS
def test_stop_during_tts():
    controller = SpeechController()
    
    # Mock speech player / tool
    mock_tts_tool = MagicMock()
    controller.voice_manager = MagicMock()
    controller.voice_manager.tts = mock_tts_tool
    
    # Enqueue a long speech item
    controller.speak("This is a very long speech task that needs to be interrupted.", "en")
    
    # Trigger stop / interrupt
    controller.interrupt()
    
    # Verify queue cleared and state reset
    assert controller.speech_queue.empty()
    assert controller.speaking_state == "IDLE"
    assert controller.currently_speaking_text == ""


# 11. Nova self-capture protection
def test_self_capture_protection():
    boot_mgr = BootManager()
    boot_mgr.boot()
    
    # Simulate active TTS
    boot_mgr.voice_manager.speech_controller.currently_speaking_text = "Okay Boss, I will speak in Hindi."
    
    # Simulate always listening engine
    from voice.always_listening import AlwaysListeningEngine
    engine = AlwaysListeningEngine(
        voice_manager=boot_mgr.voice_manager,
        wake_detector=MagicMock(),
        audio_recorder=MagicMock()
    )
    
    # Check if the echo check rejects it
    assert engine._is_echo("Hindi") is True
    assert engine._is_echo("Okay Boss, I will speak in Hindi.") is True
    
    # Check that a normal stop word is NOT rejected (allowed for barge-in)
    assert engine._is_echo("Stop") is False
    assert engine._is_echo("Cancel") is False


# 12. Duplicate voice command prevention
def test_duplicate_voice_command_prevention():
    boot_mgr = BootManager()
    boot_mgr.boot()
    
    with patch("shutil.which", return_value="C:\\chrome.exe"), \
         patch("os.path.exists", return_value=True), \
         patch("subprocess.Popen") as mock_popen, \
         patch.object(boot_mgr.voice_manager, "_safe_speak") as mock_speak:
         
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        
        # Send first query
        boot_mgr.conversation_engine.process_speech("Hey Nova, open Chrome")
        cache_keys_1 = list(boot_mgr.executive_agent._processed_requests.keys())
        
        # Send duplicate immediately
        boot_mgr.conversation_engine.process_speech("Hey Nova, open Chrome")
        cache_keys_2 = list(boot_mgr.executive_agent._processed_requests.keys())
        
        debug_path = r"C:\Users\asus\.gemini\antigravity-ide\brain\edd0ba98-b186-412c-92c5-0f91c19c47a1\scratch\debug_dup.txt"
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(f"Cache keys 1: {cache_keys_1}\n")
            f.write(f"Cache keys 2: {cache_keys_2}\n")
            f.write(f"Class Cache: {list(ExecutiveAgent._processed_requests.keys())}\n")
            f.write(f"mock_popen call_count: {mock_popen.call_count}\n")
            
        # Verify Popen called exactly once
        assert mock_popen.call_count == 1


# 13. Failed desktop action → truthful failure response
def test_failed_desktop_action_failure_response():
    boot_mgr = BootManager()
    boot_mgr.boot()
    
    from core.executive_agent import ExecutionResult, ExecutionStatus
    res = ExecutionResult(
        plan_id="test",
        status=ExecutionStatus.FAILED,
        final_response="Sorry Boss, I couldn't open nonexistentapp."
    )
    with patch.object(boot_mgr.executive_agent, "execute", return_value=res), \
         patch.object(boot_mgr.voice_manager, "_safe_speak") as mock_speak:
         
        # Simulate command to open nonexistent app
        boot_mgr.conversation_engine.process_speech("Hey Nova, open nonexistentapp")
        
        # Verify failure response was spoken
        mock_speak.assert_called()
        spoken_res = mock_speak.call_args[0][0]
        assert "Sorry Boss" in spoken_res or "couldn't" in spoken_res or "fail" in spoken_res.lower()


# 14. Direct deduplication verification
def test_direct_deduplication():
    boot_mgr = BootManager()
    boot_mgr.boot()
    
    agent = boot_mgr.executive_agent
    
    with patch("shutil.which", return_value="C:\\chrome.exe"), \
         patch("os.path.exists", return_value=True), \
         patch("subprocess.Popen") as mock_popen:
         
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        
        # Send first
        agent.execute("Hey Nova, open Chrome")
        # Check cache
        assert "Hey Nova, open Chrome" in agent._processed_requests


# 15. Unresolved close target prompt
def test_close_unresolved_prompt():
    boot_mgr = BootManager()
    boot_mgr.boot()
    
    with patch.object(boot_mgr.voice_manager, "_safe_speak") as mock_speak:
        # Resolve follow-up context with no prior app
        boot_mgr.conversation_engine.process_speech("Close it")
        
        # Verify it asks "Which application should I close?"
        mock_speak.assert_called_once()
        spoken_res = mock_speak.call_args[0][0]
        assert "Which application should I close?" in spoken_res


# 16. Safe Explorer closing (COM instead of taskkill)
def test_safe_explorer_closing():
    from utils.desktop_automation_manager import DesktopAutomationManager
    manager = DesktopAutomationManager()
    
    with patch("subprocess.run") as mock_run:
        # Trigger explorer close
        res = manager.close_application("explorer")
        
        # Verify COM powershell command was run instead of taskkill
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "Shell.Application" in args
        assert "taskkill" not in args.lower()
        assert "Success" in res


# 17. Forced Whisper Multilingual Decoding
def test_forced_whisper_multilingual_decoding():
    from voice.speech_to_text import FasterWhisperSTT
    stt = FasterWhisperSTT()
    stt.model = MagicMock()
    stt.multilingual_model = MagicMock()
    
    # Lock language to Telugu
    LanguageSession().selected_language = "te"
    
    with patch("pathlib.Path.exists", return_value=True):
        stt.transcribe(Path("dummy.wav"), multilingual=True)
        
        # Verify Telugu was passed as the forced language parameter to Whisper
        stt.multilingual_model.transcribe.assert_called_once()
        kwargs = stt.multilingual_model.transcribe.call_args[1]
        assert kwargs.get("language") == "te"


# 18. Queue draining on completion and interrupt
def test_queue_draining_on_interrupt_and_completion():
    from voice.always_listening import AlwaysListeningEngine
    engine = AlwaysListeningEngine(
        voice_manager=MagicMock(),
        wake_detector=MagicMock(),
        audio_recorder=MagicMock()
    )
    engine.recorder.audio_queue = MagicMock()
    engine.recorder.audio_queue.empty.side_effect = [False, True] # simulate 1 item in queue
    
    # Trigger interrupt
    engine.interrupt()
    
    # Verify queue was drained
    assert engine.recorder.audio_queue.get_nowait.call_count == 1
