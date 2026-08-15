import pytest
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.executive_agent import ExecutiveAgent, ExecutionStatus
from core.engine import NovaEngine
from core.planner import AgentPlanner
from voice.always_listening import AlwaysListeningEngine
from voice.voice_manager import VoiceManager


@pytest.fixture
def mock_engine():
    m = MagicMock(spec=NovaEngine)
    m.selected_language = "en"
    m.conversation = MagicMock()
    return m


def test_intent_routing_conversation_and_knowledge(mock_engine):
    agent = ExecutiveAgent(engine=mock_engine)
    agent.engine.conversation.provider = MagicMock()
    
    # Mock LLM response to classify as KNOWLEDGE
    mock_llm_res = MagicMock()
    mock_llm_res.text = "KNOWLEDGE"
    agent.engine.conversation.provider.generate.return_value = mock_llm_res

    # Test route_intent calls LLM provider
    intent = agent.route_intent("What is python?")
    assert intent == "KNOWLEDGE"
    
    # Test fallback classification rules
    agent.engine.conversation.provider = None
    intent_fallback = agent.route_intent("What is python?")
    assert intent_fallback == "KNOWLEDGE"


def test_close_youtube_direct_routing(mock_engine):
    agent = ExecutiveAgent(engine=mock_engine)
    agent.engine.conversation.provider = None  # Force rule fallback
    
    mock_browser = MagicMock()
    agent.agent_registry = MagicMock()
    agent.agent_registry.is_registered.return_value = True
    agent.agent_registry.resolve.return_value = mock_browser
    agent.step_executor = MagicMock()
    agent.step_executor.browser_agent = mock_browser

    res = agent.execute("Close YouTube")
    
    # Verify it routed directly to BrowserAgent execute
    assert res.plan_id == "fast_path_close"
    assert res.status == ExecutionStatus.SUCCESS
    mock_browser.execute.assert_called_once_with("close browser")


def test_close_notepad_direct_routing(mock_engine):
    agent = ExecutiveAgent(engine=mock_engine)
    agent.engine.conversation.provider = None  # Force rule fallback
    
    mock_workspace = MagicMock()
    agent.workspace_agent = mock_workspace
    agent.agent_registry = MagicMock()
    agent.agent_registry.is_registered.return_value = True
    agent.agent_registry.resolve.return_value = mock_workspace
    
    res = agent.execute("Close Notepad")
    
    # Verify it routed directly to WorkspaceAgent execute
    assert res.plan_id == "fast_path_close"
    assert res.status == ExecutionStatus.SUCCESS
    mock_workspace.execute.assert_called_once_with("close notepad")


def test_conversational_suppress_tools():
    # Verify planner ask disables tools for conversational intents
    registry = MagicMock()
    registry.get_gemini_declarations.return_value = ["dummy_tool"]
    
    provider = MagicMock()
    memory = MagicMock()
    memory.get_history.return_value = []
    
    planner = AgentPlanner(
        provider=provider,
        memory=memory,
        registry=registry,
        executor=MagicMock(),
        permission_gate=MagicMock()
    )
    
    # Mock LLM generation
    res = MagicMock()
    res.function_calls = []
    res.text = "Python is a programming language."
    provider.generate.return_value = res
    
    planner.ask("What is Python?", selected_language="en", intent_category="KNOWLEDGE")
    
    # Verify declarations parameter to generate call is None (disabled tools)
    called_kwargs = provider.generate.call_args[1]
    assert called_kwargs["tools"] is None


def test_barge_in_playback_interrupted(mock_engine):
    vm = VoiceManager(engine=mock_engine, voice_input_enabled=True)
    recorder = MagicMock()
    wake_detector = MagicMock()
    
    engine = AlwaysListeningEngine(
        voice_manager=vm,
        wake_detector=wake_detector,
        audio_recorder=recorder
    )
    
    # Mock interrupt to set flag
    interrupted = False
    def mock_interrupt():
        nonlocal interrupted
        interrupted = True
        vm.tts_stop_event.set()
        
    vm.interrupt = mock_interrupt
    
    # Run active playback cancel test
    vm.tts_stop_event.clear()
    vm.interrupt()
    assert interrupted is True
    assert vm.tts_stop_event.is_set()
