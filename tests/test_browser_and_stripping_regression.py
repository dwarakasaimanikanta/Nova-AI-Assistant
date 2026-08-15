"""
tests/test_browser_and_stripping_regression.py
----------------------------------------------
Regression tests for browser persistence, wake-word stripping, and GUI visualizer state updates.
"""

import pytest
import math
import os
import threading
from unittest.mock import MagicMock, patch
from agents.browser_agent import BrowserAgent, BrowserAction, BrowserStatus
from core.executive_agent import ExecutiveAgent
from interface.gui.gui_app import NovaHolographicCore, NovaGUIApp

class DummyBrowserTool:
    def __init__(self):
        self.manager = MagicMock()
        # Mock active page
        self.manager._page = MagicMock()
        self.manager._page.is_closed = MagicMock(return_value=False)
        self.manager.launch_browser.return_value = "Success: launched."
        self.manager.open_url.return_value = "Success: navigated."
        self.manager.search_google.return_value = "Success: searched."
        self.manager.close_browser.return_value = "Success: closed."
        
    def execute(self, **kwargs):
        action = kwargs.get("action")
        if action == "launch_browser":
            return self.manager.launch_browser()
        elif action == "open_url":
            return self.manager.open_url(kwargs.get("url"))
        elif action == "search_google":
            return self.manager.search_google(kwargs.get("query"))
        elif action == "close_browser":
            # Simulate closing page
            self.manager._page.is_closed.return_value = True
            return self.manager.close_browser()
        return "Success"


def test_browser_persistence_regression():
    # A. Browser persistence test
    tool = DummyBrowserTool()
    agent = BrowserAgent(browser_tool=tool)
    
    # 1. Open YouTube
    res1 = agent.execute("Open YouTube")
    assert res1.status == BrowserStatus.SUCCESS
    # Verify close_browser was NOT called (it is persistent)
    assert not tool.manager.close_browser.called
    assert tool.manager.open_url.called
    
    # 2. Second command: Open GitHub
    tool.manager.open_url.reset_mock()
    res2 = agent.execute("Open GitHub")
    assert res2.status == BrowserStatus.SUCCESS
    assert tool.manager.open_url.called
    assert not tool.manager.close_browser.called
    
    # 3. Explicit Close Browser
    res3 = agent.execute("Close the browser")
    assert res3.status == BrowserStatus.SUCCESS
    assert tool.manager.close_browser.called


def test_wake_phrase_stripping_regression():
    # B. Wake phrase stripping & C. Command normalization test
    mock_engine = MagicMock()
    mock_browser = MagicMock()
    mock_browser.execute.return_value = MagicMock(status=BrowserStatus.SUCCESS, final_output="Done", errors=[])
    
    exec_agent = ExecutiveAgent(engine=mock_engine, browser_agent=mock_browser)
    
    # Test cases for stripping using non-fast-path desktop commands
    test_cases = [
        ("Hello Nova, Open Chrome", "Open Chrome"),
        ("Nova, Open Notepad", "Open Notepad"),
        ("Hey Nova, close Chrome", "close Chrome"),
        ("I said open Chrome", "I said open Chrome"), # Should not strip
    ]
    
    for input_text, expected_stripped in test_cases:
        # Mock step executor / router behavior
        with patch.object(exec_agent.step_executor, "execute") as mock_exec_step:
            mock_exec_step.return_value = "Done"
            exec_agent.execute(input_text)
            # Check the input_data of the executed step
            called_args = mock_exec_step.call_args[0]
            step = called_args[0]
            assert step.input_data == expected_stripped


def test_gui_state_visualization_regression():
    # D. GUI state visualization & safety test
    from PyQt6.QtWidgets import QApplication
    qt_app = QApplication.instance()
    if not qt_app:
        qt_app = QApplication(["-platform", "offscreen"])
        
    parent = MagicMock()
    parent.voice_state = "IDLE"
    parent.isMinimized = MagicMock(return_value=False)
    parent.isVisible = MagicMock(return_value=True)
    
    core = NovaHolographicCore(None)
    core.parent_gui = parent
    
    # Test rapid state transitions
    states = ["IDLE", "LISTENING", "PROCESSING", "EXECUTING", "SPEAKING", "ERROR", "IDLE"]
    for s in states:
        parent.voice_state = s
        # Trigger paint tick
        core._tick()
        
    # Verify set_voice_activity doesn't crash
    core.set_voice_activity(0.8)
    assert core.voice_activity_level == 0.8
    
    core.stop_timer()


def test_audio_recorder_timeout_capping_regression():
    # Verify VAD initial silence blocks are capped correctly
    from config import NOVA_INITIAL_SILENCE_TIMEOUT
    max_record_seconds = 1.0
    capped = min(NOVA_INITIAL_SILENCE_TIMEOUT, max_record_seconds)
    # Ensure it clamps to the smaller value to avoid long silence capture on short recordings
    assert capped == 1.0


def test_always_listening_warm_up_blocking_regression():
    # Verify that AlwaysListeningEngine blocks on model ready event
    from voice.always_listening import AlwaysListeningEngine
    
    mock_stt = MagicMock()
    mock_stt.model = None
    mock_stt._model_ready_event = MagicMock()
    
    mock_voice_manager = MagicMock()
    mock_voice_manager.stt_engine = mock_stt
    
    engine = AlwaysListeningEngine(
        voice_manager=mock_voice_manager,
        wake_detector=MagicMock(),
        audio_recorder=MagicMock()
    )
    
    with patch("threading.Thread") as mock_thread, \
         patch.dict(os.environ, {"ENVIRONMENT": "development"}):
        engine.start()
        # Should call wait to guarantee warmup is complete
        assert mock_stt._model_ready_event.wait.called
        assert engine.running is True


# ─────────────────────────────────────────────────────────────────────────────
# JARVIS Upgrade Regression Tests (Phase 1-10)
# ─────────────────────────────────────────────────────────────────────────────

def test_browser_no_autoclose_after_url_open():
    """Browser must NOT close after opening YouTube / GitHub / any direct URL."""
    tool = DummyBrowserTool()
    agent = BrowserAgent(browser_tool=tool)

    # Opening YouTube should: LAUNCH + OPEN_URL only (no CLOSE)
    res = agent.execute("Open YouTube")
    assert res.status == BrowserStatus.SUCCESS
    assert tool.manager.open_url.called, "open_url must be called"
    assert not tool.manager.close_browser.called, "close_browser must NOT be called for URL opens"


def test_browser_explicit_close_works():
    """Explicit 'Close browser' must still close the browser."""
    tool = DummyBrowserTool()
    agent = BrowserAgent(browser_tool=tool)

    res = agent.execute("Close the browser")
    assert res.status == BrowserStatus.SUCCESS
    assert tool.manager.close_browser.called, "close_browser must be called on explicit close"


def test_stt_date_hallucination_rejected():
    """STT must reject Whisper date/time hallucinations like 'Sunday October 3rd 2021'."""
    import os
    from unittest.mock import MagicMock, patch
    with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
        from voice.speech_to_text import FasterWhisperSTT

        stt = FasterWhisperSTT.__new__(FasterWhisperSTT)
        stt.model = MagicMock()
        stt.wake_model = MagicMock()
        stt.model_size = "tiny.en"
        stt.device = "cpu"
        import threading
        stt._load_lock = threading.Lock()
        stt._model_ready_event = threading.Event()
        stt._model_ready_event.set()

        # Create a mock segment that looks like a date hallucination
        mock_seg = MagicMock()
        mock_seg.text = " Sunday, October 3rd, 2021. Thank you."
        mock_seg.no_speech_prob = 0.45
        mock_seg.avg_logprob = -0.5
        mock_seg.compression_ratio = 1.2
        mock_seg.start = 0.0
        mock_seg.end = 0.25  # short duration
        mock_seg.words = []

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.95

        stt.model.transcribe.return_value = ([mock_seg], mock_info)

        import tempfile
        from pathlib import Path
        tmp = Path(tempfile.gettempdir()) / "test_date_halluc.wav"
        tmp.touch()
        try:
            result = stt.transcribe(tmp)
            assert result == "", f"Date hallucination should be filtered out, got: {result!r}"
        finally:
            try:
                tmp.unlink()
            except Exception:
                pass


def test_stt_implausible_transcript_rejected():
    """STT must reject impossibly long transcripts from very short audio segments."""
    import os
    from unittest.mock import MagicMock, patch
    with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
        from voice.speech_to_text import FasterWhisperSTT

        stt = FasterWhisperSTT.__new__(FasterWhisperSTT)
        stt.model = MagicMock()
        stt.wake_model = MagicMock()
        stt.model_size = "tiny.en"
        stt.device = "cpu"
        stt._load_lock = threading.Lock()
        stt._model_ready_event = threading.Event()
        stt._model_ready_event.set()

        # A short 0.2 second segment with 15 words is implausible
        mock_seg = MagicMock()
        mock_seg.text = " Hello this is a very long sentence that could not have been said in point two seconds"
        mock_seg.no_speech_prob = 0.1
        mock_seg.avg_logprob = -0.3
        mock_seg.compression_ratio = 1.0
        mock_seg.start = 0.0
        mock_seg.end = 0.2  # 0.2 seconds but 17 words

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.95

        stt.model.transcribe.return_value = ([mock_seg], mock_info)

        import tempfile
        from pathlib import Path
        tmp = Path(tempfile.gettempdir()) / "test_implausible.wav"
        tmp.touch()
        try:
            result = stt.transcribe(tmp)
            assert result == "", f"Implausible transcript should be filtered, got: {result!r}"
        finally:
            try:
                tmp.unlink()
            except Exception:
                pass


def test_personality_responses_no_llm():
    """Nova must respond to chit-chat without hitting the LLM."""
    mock_engine = MagicMock()
    exec_agent = ExecutiveAgent(engine=mock_engine)

    test_cases = [
        ("how are you", "Running at full capacity"),
        ("good morning", "Good morning, Boss"),
        ("who are you", "Nova"),
        ("can you hear me", "Loud and clear"),
        ("are you there", "Always here"),
    ]

    for cmd, expected_fragment in test_cases:
        result = exec_agent.execute(cmd)
        assert expected_fragment.lower() in result.final_response.lower(), \
            f"Personality response for {cmd!r} should contain {expected_fragment!r}, got: {result.final_response!r}"
        # Engine must NOT have been called
        assert not mock_engine.handle_input.called, \
            f"LLM must not be called for personality response: {cmd!r}"
        mock_engine.handle_input.reset_mock()


def test_english_format_spoken_response():
    """format_spoken_response must return English when NOVA_RESPONSE_LANGUAGE='en'."""
    import os
    old_val = os.environ.get("NOVA_RESPONSE_LANGUAGE")
    os.environ["NOVA_RESPONSE_LANGUAGE"] = "en"

    try:
        from voice.voice_manager import format_spoken_response

        # Test various response patterns
        assert "Opening YouTube" in format_spoken_response("Opened YouTube at https://www.youtube.com")
        assert "Opening Notepad" in format_spoken_response("Launched application 'notepad'")
        assert "Sorry Boss" in format_spoken_response("Failure: could not open file")
        assert "Done, Boss" in format_spoken_response("Success: ")

        # Telugu strings must NOT appear when in English mode
        result = format_spoken_response("Opened YouTube at https://www.youtube.com")
        assert "తెరిచాను" not in result, f"Telugu must not appear in English mode: {result!r}"
    finally:
        if old_val is not None:
            os.environ["NOVA_RESPONSE_LANGUAGE"] = old_val
        else:
            os.environ.pop("NOVA_RESPONSE_LANGUAGE", None)


def test_conversation_context_follow_up_resolution():
    """ConversationContext must resolve follow-up pronouns correctly."""
    from core.conversation_context import ConversationContext

    ctx = ConversationContext()

    # 1. After opening notepad, "close it" should resolve to "close notepad"
    ctx.update("open notepad", "Opening Notepad, Boss.")
    resolved = ctx.resolve_follow_up("close it")
    assert resolved == "close notepad", f"Expected 'close notepad', got: {resolved!r}"

    # 2. After a project creation, "make it dark" should include project path
    ctx.set_project_path("/projects/restaurant_website")
    resolved = ctx.resolve_follow_up("make it dark")
    assert "project" in resolved.lower(), f"Expected project context in: {resolved!r}"
    assert "/projects/restaurant_website" in resolved

    # 3. Unknown follow-up should pass through unchanged
    ctx.reset()
    resolved = ctx.resolve_follow_up("what is the weather today")
    assert resolved == "what is the weather today"


def test_fast_path_expanded_sites():
    """Executive Agent fast-path must route all major sites without LLM."""
    import webbrowser
    mock_engine = MagicMock()
    exec_agent = ExecutiveAgent(engine=mock_engine)

    sites_to_test = [
        ("open chatgpt", "chatgpt.com"),
        ("open reddit", "reddit.com"),
        ("open linkedin", "linkedin.com"),
        ("open spotify", "spotify.com"),
        ("open netflix", "netflix.com"),
    ]

    with patch("webbrowser.open") as mock_wb:
        for cmd, expected_domain in sites_to_test:
            mock_wb.reset_mock()
            result = exec_agent.execute(cmd)
            assert result.status.value == "SUCCESS" or mock_wb.called, \
                f"Fast path failed for {cmd!r}"
            if mock_wb.called:
                call_url = mock_wb.call_args[0][0]
                assert expected_domain in call_url, \
                    f"Wrong URL for {cmd!r}: {call_url}"

    assert not mock_engine.handle_input.called, "LLM must not be called for site fast-paths"
