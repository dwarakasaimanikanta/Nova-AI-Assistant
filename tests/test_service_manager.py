"""
tests/test_service_manager.py
-----------------------------
Unit tests verifying the ServiceManager lifecycle orchestration, registry, adapters, and isolation properties.
"""

import time
from unittest.mock import MagicMock, patch
import pytest

from core.service_manager import (
    ServiceManager, ServiceRegistry, ServiceStatus, BaseService,
    MemoryService, PluginManagerService, StartupManagerService,
    BrowserService, AndroidService, VoiceService
)


class MockSimpleService(BaseService):
    def __init__(self, name: str, init_ok: bool = True, start_ok: bool = True) -> None:
        self._name = name
        self.init_ok = init_ok
        self.start_ok = start_ok
        self.initialized_calls = 0
        self.started_calls = 0
        self.stopped_calls = 0

    @property
    def name(self) -> str:
        return self._name

    def initialize(self) -> bool:
        self.initialized_calls += 1
        return self.init_ok

    def start(self) -> bool:
        self.started_calls += 1
        return self.start_ok

    def stop(self) -> bool:
        self.stopped_calls += 1
        return True

    def restart(self) -> bool:
        return True

    def health(self) -> bool:
        return True


def test_service_status_fields():
    """Verify ServiceStatus tracks names, states, uptime, and restart counts accurately."""
    status = ServiceStatus("TestService")
    assert status.name == "TestService"
    assert status.state == "STOPPED"
    assert status.uptime == 0.0
    assert status.restart_count == 0

    status.state = "RUNNING"
    status.start_time = time.time() - 10.0
    assert status.uptime >= 9.9
    assert status.to_dict()["state"] == "RUNNING"


def test_registry_registration():
    """Verify ServiceRegistry registers services, status records, and returns them."""
    reg = ServiceRegistry()
    srv = MockSimpleService("S1")
    reg.register(srv)

    assert reg.get_service("S1") is srv
    assert reg.get_status("S1") is not None
    assert reg.get_status("S1").name == "S1"
    assert "S1" in reg.list_services()


def test_dependency_validation_ok():
    """Verify validate_dependencies passes with clean acyclic configurations."""
    sm = ServiceManager()
    s1 = MockSimpleService("S1")
    s2 = MockSimpleService("S2")
    sm.register_service(s1)
    sm.register_service(s2, dependencies=["S1"])

    assert sm.validate_dependencies() is True


def test_dependency_validation_missing_dependency():
    """Verify validate_dependencies catches missing dependency errors."""
    sm = ServiceManager()
    s1 = MockSimpleService("S1")
    sm.register_service(s1, dependencies=["MissingService"])

    assert sm.validate_dependencies() is False


def test_dependency_validation_circular():
    """Verify validate_dependencies catches dependency cycles."""
    sm = ServiceManager()
    s1 = MockSimpleService("S1")
    s2 = MockSimpleService("S2")
    sm.register_service(s1)
    sm.register_service(s2)
    sm.set_dependencies("S1", ["S2"])
    sm.set_dependencies("S2", ["S1"])

    assert sm.validate_dependencies() is False


def test_service_startup_sequence():
    """Verify service startup runs step initialization and changes state accurately."""
    sm = ServiceManager()
    s1 = MockSimpleService("S1")
    sm.register_service(s1)

    # Initialize
    assert sm.initialize_service("S1") is True
    assert sm.registry.get_status("S1").state == "INITIALIZED"
    assert s1.initialized_calls == 1

    # Start
    assert sm.start_service("S1") is True
    assert sm.registry.get_status("S1").state == "RUNNING"
    assert s1.started_calls == 1


def test_service_startup_cascades_dependencies():
    """Verify starting a service automatically initializes and starts all registered dependencies first."""
    sm = ServiceManager()
    s1 = MockSimpleService("S1")
    s2 = MockSimpleService("S2")
    sm.register_service(s1)
    sm.register_service(s2, dependencies=["S1"])

    # Directly start S2; S1 must auto-start
    assert sm.start_service("S2") is True
    assert sm.registry.get_status("S1").state == "RUNNING"
    assert sm.registry.get_status("S2").state == "RUNNING"
    assert s1.started_calls == 1
    assert s2.started_calls == 1


def test_crash_isolation_on_initialization():
    """Verify ServiceManager intercepts exceptions gracefully and logs failures without crashing."""
    sm = ServiceManager()
    s1 = MockSimpleService("S1")
    s1.initialize = MagicMock(side_effect=RuntimeError("Hardware error"))
    sm.register_service(s1)

    assert sm.initialize_service("S1") is False
    status = sm.registry.get_status("S1")
    assert status.state == "FAILED"
    assert "Hardware error" in status.last_error


def test_restart_service():
    """Verify restart_service stops and starts services, incrementing restart counters."""
    sm = ServiceManager()
    s1 = MockSimpleService("S1")
    sm.register_service(s1)

    sm.start_service("S1")
    assert sm.registry.get_status("S1").state == "RUNNING"
    assert sm.registry.get_status("S1").restart_count == 0

    assert sm.restart_service("S1") is True
    assert sm.registry.get_status("S1").state == "RUNNING"
    assert sm.registry.get_status("S1").restart_count == 1
    assert s1.stopped_calls == 1


def test_shutdown_all_in_reverse_order():
    """Verify shutdown_all stops services in reverse order of their registration."""
    sm = ServiceManager()
    s1 = MockSimpleService("S1")
    s2 = MockSimpleService("S2")
    sm.register_service(s1)
    sm.register_service(s2)

    sm.start_service("S1")
    sm.start_service("S2")

    order_stopped = []
    
    # Patch stop methods to record ordering
    s1.stop = MagicMock(side_effect=lambda: order_stopped.append("S1") or True)
    s2.stop = MagicMock(side_effect=lambda: order_stopped.append("S2") or True)

    sm.shutdown_all()
    assert order_stopped == ["S2", "S1"]


def test_health_checks_report():
    """Verify run_health_checks evaluates service statuses and detects failures."""
    sm = ServiceManager()
    s1 = MockSimpleService("S1")
    s2 = MockSimpleService("S2")
    s2.health = MagicMock(side_effect=ValueError("Degraded"))
    
    sm.register_service(s1)
    sm.register_service(s2)

    sm.start_service("S1")
    sm.start_service("S2")

    report = sm.run_health_checks()
    assert report["S1"] == "HEALTHY"
    assert report["S2"] == "FAILED"
