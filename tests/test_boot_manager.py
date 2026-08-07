"""
tests/test_boot_manager.py
--------------------------
Comprehensive unit and integration tests for the Boot Experience Manager.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.boot_manager import BootManager


# ─────────────────────────────────────────────────────────────────────────────
# Mocks & Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_service_manager():
    sm = MagicMock()
    # Mock registry list_services, get_service, get_status
    sm.registry = MagicMock()
    
    # Set default values for list_services
    sm.registry.list_services.return_value = ["Memory", "Voice", "Browser", "Android"]
    
    # Mock get_service
    mock_service = MagicMock()
    mock_service.health.return_value = True
    sm.registry.get_service.return_value = mock_service
    
    # Mock get_status
    mock_status = MagicMock()
    mock_status.state = "RUNNING"
    sm.registry.get_status.return_value = mock_status
    
    return sm


@pytest.fixture
def mock_session_manager():
    sm = MagicMock()
    sm.trigger_startup_greeting.return_value = "Nova is online. Ready for commands."
    return sm


@pytest.fixture
def mock_voice_manager():
    vm = MagicMock()
    vm.voice_input_enabled = True
    vm.wake_word_enabled = False
    vm.state = "WAKING"
    vm.tts = MagicMock()
    return vm


@pytest.fixture
def mock_memory_agent():
    ma = MagicMock()
    ma.recall.return_value = None
    return ma


# ─────────────────────────────────────────────────────────────────────────────
# BootManager Test Suite
# ─────────────────────────────────────────────────────────────────────────────

class TestBootManager:
    def test_boot_success_with_all_services(
        self, mock_service_manager, mock_session_manager, mock_voice_manager, mock_memory_agent
    ):
        boot_mgr = BootManager(
            service_manager=mock_service_manager,
            session_manager=mock_session_manager,
            voice_manager=mock_voice_manager,
            memory_agent=mock_memory_agent,
        )

        success = boot_mgr.boot()
        assert success is True
        
        # Verify startup greeting generated and spoken
        mock_session_manager.trigger_startup_greeting.assert_called_once()
        mock_voice_manager.tts.execute.assert_called_once_with(text="Nova is online. Ready for commands.")
        
        # Verify voice manager enters always listening mode
        assert mock_voice_manager.wake_word_enabled is True
        assert mock_voice_manager.state == "WAITING"
        mock_voice_manager.start.assert_called_once()

    def test_boot_restores_session_from_memory(
        self, mock_service_manager, mock_session_manager, mock_voice_manager, mock_memory_agent
    ):
        mock_memory_agent.recall.return_value = "restored_session_abc"
        
        boot_mgr = BootManager(
            service_manager=mock_service_manager,
            session_manager=mock_session_manager,
            voice_manager=mock_voice_manager,
            memory_agent=mock_memory_agent,
        )

        success = boot_mgr.boot()
        assert success is True
        
        # Verify we restored the session
        mock_session_manager.start_session.assert_called_once_with("restored_session_abc")
        # Verify we stored the session in memory again
        mock_memory_agent.remember.assert_any_call("short_term", "last_session_id", "restored_session_abc")

    def test_boot_mandatory_service_failure_raises_error(
        self, mock_service_manager, mock_session_manager, mock_voice_manager, mock_memory_agent
    ):
        # Make mandatory service "Memory" unhealthy/fail to start
        def mock_get_status(name):
            if name == "Memory":
                status = MagicMock()
                status.state = "FAILED"
                return status
            status = MagicMock()
            status.state = "RUNNING"
            return status

        mock_service_manager.registry.get_status.side_effect = mock_get_status
        # Mock health check to return False for Memory
        mock_service = MagicMock()
        mock_service.health.side_effect = lambda: False
        mock_service_manager.registry.get_service.return_value = mock_service

        boot_mgr = BootManager(
            service_manager=mock_service_manager,
            session_manager=mock_session_manager,
            voice_manager=mock_voice_manager,
            memory_agent=mock_memory_agent,
        )

        with pytest.raises(RuntimeError, match="Memory"):
            boot_mgr.boot()

    def test_boot_optional_service_failure_ignored(
        self, mock_service_manager, mock_session_manager, mock_voice_manager, mock_memory_agent
    ):
        # Make optional service "Browser" unhealthy/fail to start
        def mock_get_status(name):
            status = MagicMock()
            if name == "Browser":
                status.state = "FAILED"
            else:
                status.state = "RUNNING"
            return status

        mock_service_manager.registry.get_status.side_effect = mock_get_status

        boot_mgr = BootManager(
            service_manager=mock_service_manager,
            session_manager=mock_session_manager,
            voice_manager=mock_voice_manager,
            memory_agent=mock_memory_agent,
        )

        # Boot should succeed because Browser is optional
        success = boot_mgr.boot()
        assert success is True
