"""
tests/test_boot_manager.py
--------------------------
Comprehensive unit and integration tests for the real startup BootManager.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.boot_manager import BootManager, BootReport


# ─────────────────────────────────────────────────────────────────────────────
# Test Suite
# ─────────────────────────────────────────────────────────────────────────────

class TestBootManager:
    @patch("core.config_service.ConfigService")
    @patch("core.agent_registry.AgentRegistry")
    @patch("core.executive_agent.ExecutiveAgent")
    @patch("core.session_manager.SessionManager")
    @patch("voice.voice_manager.VoiceManager")
    @patch("voice.always_listening.AlwaysListeningEngine")
    @patch("voice.conversation_engine.VoiceConversationEngine")
    @patch("core.execution_pipeline.ExecutionPipeline")
    def test_boot_integration_pipeline_success(
        self,
        mock_pipeline_cls,
        mock_conv_cls,
        mock_listening_cls,
        mock_voice_cls,
        mock_session_cls,
        mock_exec_cls,
        mock_registry_cls,
        mock_config_cls
    ):
        # Configure registry mock
        mock_registry = MagicMock()
        mock_registry_cls.return_value = mock_registry
        
        mock_memory = MagicMock()
        mock_memory.recall.return_value = "restored_session_xyz"
        mock_registry.resolve.side_effect = lambda name: mock_memory if name == "memory" else MagicMock()
        mock_registry.is_registered.return_value = True

        # Configure session mock
        mock_session_mgr = MagicMock()
        mock_session_cls.return_value = mock_session_mgr

        # Configure voice manager mock
        mock_voice_mgr = MagicMock()
        mock_voice_mgr.voice_input_enabled = True
        mock_voice_cls.return_value = mock_voice_mgr

        # Configure always listening mock
        mock_listening = MagicMock()
        mock_listening_cls.return_value = mock_listening

        # Run boot
        boot_mgr = BootManager()
        report = boot_mgr.boot()

        # Verify BootReport structure
        assert report.success is True
        assert report.session_id == "restored_session_xyz"
        assert len(report.initialized_components) > 5
        assert len(report.errors) == 0
        assert "Boss" in report.greeting

        # Verify interaction wiring
        mock_session_mgr.start_session.assert_called_once_with("restored_session_xyz")
        mock_listening.start.assert_called_once()
        assert mock_voice_mgr.wake_word_enabled is True
        assert mock_voice_mgr.state == "WAITING"

    @patch("core.config_service.ConfigService")
    @patch("core.agent_registry.AgentRegistry")
    def test_boot_failure_returns_failed_report(self, mock_registry_cls, mock_config_cls):
        # Configure config service to raise exception
        mock_config = MagicMock()
        mock_config.initialize.side_effect = RuntimeError("Database corrupt")
        mock_config_cls.return_value = mock_config

        boot_mgr = BootManager()
        report = boot_mgr.boot()

        assert report.success is False
        assert len(report.errors) > 0
        assert "Database corrupt" in report.errors[0]

    @patch("core.config_service.ConfigService")
    @patch("core.agent_registry.AgentRegistry")
    @patch("core.executive_agent.ExecutiveAgent")
    @patch("core.session_manager.SessionManager")
    @patch("voice.voice_manager.VoiceManager")
    @patch("voice.always_listening.AlwaysListeningEngine")
    @patch("voice.conversation_engine.VoiceConversationEngine")
    @patch("core.execution_pipeline.ExecutionPipeline")
    def test_boot_duplicate_initialization_safety(
        self,
        mock_pipeline_cls,
        mock_conv_cls,
        mock_listening_cls,
        mock_voice_cls,
        mock_session_cls,
        mock_exec_cls,
        mock_registry_cls,
        mock_config_cls
    ):
        mock_registry = MagicMock()
        mock_registry_cls.return_value = mock_registry
        mock_registry.is_registered.return_value = True

        boot_mgr = BootManager()
        report1 = boot_mgr.boot()
        assert report1.success is True

        # Second boot call
        report2 = boot_mgr.boot()
        assert report2.success is True
        assert "CacheRestore" in report2.initialized_components
        
        # Verify config was initialized only once
        mock_config_cls.return_value.initialize.assert_called_once()
