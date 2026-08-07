"""
tests/test_conversation_engine.py
---------------------------------
Comprehensive unit tests for the Voice Conversation Engine.
"""

import time
from unittest.mock import MagicMock

import pytest

from voice.conversation_engine import VoiceConversationEngine


# ─────────────────────────────────────────────────────────────────────────────
# Mocks & Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_exec_agent():
    ea = MagicMock()
    # Mock handle_input returning a generator
    def handle_input_gen(text, stream=False):
        yield "response "
        yield "chunk"
    ea.handle_input.side_effect = handle_input_gen
    return ea


@pytest.fixture
def mock_voice_manager():
    vm = MagicMock()
    vm._stop_event = MagicMock()
    vm.tts = MagicMock()
    vm.tts.stop_event = MagicMock()
    return vm


@pytest.fixture
def mock_memory_agent():
    return MagicMock()


# ─────────────────────────────────────────────────────────────────────────────
# Test Suite
# ─────────────────────────────────────────────────────────────────────────────

class TestVoiceConversationEngine:
    def test_process_speech_executes_and_speaks(
        self, mock_exec_agent, mock_voice_manager, mock_memory_agent
    ):
        engine = VoiceConversationEngine(
            executive_agent=mock_exec_agent,
            voice_manager=mock_voice_manager,
            memory_agent=mock_memory_agent,
            conversation_timeout=5.0
        )

        engine.process_speech("hello world")

        # Verify ExecutiveAgent was called with stream=True
        mock_exec_agent.handle_input.assert_called_once_with("hello world", stream=True)
        # Verify VoiceManager TTS was called for chunks (response chunk)
        assert len(mock_voice_manager._safe_speak.call_args_list) == 2
        # Verify history logs
        assert len(engine.history) == 2
        assert engine.history[0] == {"role": "user", "content": "hello world"}
        assert engine.history[1] == {"role": "assistant", "content": "response chunk"}

    def test_interruption_signals_sent(
        self, mock_exec_agent, mock_voice_manager, mock_memory_agent
    ):
        engine = VoiceConversationEngine(
            executive_agent=mock_exec_agent,
            voice_manager=mock_voice_manager,
            memory_agent=mock_memory_agent
        )

        engine.interrupt()

        # Verify cancellation called on ExecutiveAgent
        mock_exec_agent.cancel.assert_called_once()
        # Verify stop event set on VoiceManager
        mock_voice_manager._stop_event.set.assert_called_once()
        mock_voice_manager._stop_event.clear.assert_called_once()

    def test_conversation_timeout_resets_history(
        self, mock_exec_agent, mock_voice_manager, mock_memory_agent
    ):
        engine = VoiceConversationEngine(
            executive_agent=mock_exec_agent,
            voice_manager=mock_voice_manager,
            memory_agent=mock_memory_agent,
            conversation_timeout=0.1
        )

        engine.history.append({"role": "user", "content": "previous message"})
        
        # Wait until timeout expires
        time.sleep(0.2)

        # Send new speech
        engine.process_speech("new message")

        # Verify old history was cleared, only new conversation entries remain
        assert len(engine.history) == 2
        assert engine.history[0] == {"role": "user", "content": "new message"}
