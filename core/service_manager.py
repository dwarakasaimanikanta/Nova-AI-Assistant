"""
core/service_manager.py
-----------------------
Coordinates service registration, status reporting, thread-safe lifecycles, and health checks.
"""

import time
import threading
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class ServiceStatus:
    """Status details container representing the runtime state of a registered service."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.state = "STOPPED"  # STOPPED, INITIALIZED, RUNNING, DEGRADED, FAILED
        self.start_time: Optional[float] = None
        self.last_error: Optional[str] = None
        self.restart_count = 0

    @property
    def uptime(self) -> float:
        """Returns uptime in seconds if the service is running, otherwise 0.0."""
        if self.state == "RUNNING" and self.start_time is not None:
            return time.time() - self.start_time
        return 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "uptime": self.uptime,
            "last_error": self.last_error,
            "restart_count": self.restart_count,
        }


class BaseService(ABC):
    """Abstract base service interface that all adapters must conform to."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def initialize(self) -> bool:
        pass

    @abstractmethod
    def start(self) -> bool:
        pass

    @abstractmethod
    def stop(self) -> bool:
        pass

    @abstractmethod
    def restart(self) -> bool:
        pass

    @abstractmethod
    def health(self) -> bool:
        pass


class ServiceRegistry:
    """Thread-safe catalog containing all registered BaseService instances."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._services: Dict[str, BaseService] = {}
        self._statuses: Dict[str, ServiceStatus] = {}

    def register(self, service: BaseService) -> None:
        with self._lock:
            name = service.name
            self._services[name] = service
            self._statuses[name] = ServiceStatus(name)
            logger.info("[ServiceRegistry] Registered service: %s", name)

    def get_service(self, name: str) -> Optional[BaseService]:
        with self._lock:
            return self._services.get(name)

    def get_status(self, name: str) -> Optional[ServiceStatus]:
        with self._lock:
            return self._statuses.get(name)

    def list_services(self) -> List[str]:
        with self._lock:
            return list(self._services.keys())

    def update_status(self, name: str, state: str, error: Optional[str] = None, reset_uptime: bool = False) -> None:
        with self._lock:
            status = self._statuses.get(name)
            if status:
                status.state = state
                if error is not None:
                    status.last_error = error
                if reset_uptime:
                    status.start_time = time.time()
                elif state in ("STOPPED", "FAILED"):
                    status.start_time = None


class ServiceManager:
    """Orchestrates system service lifecycles, dependencies, crash isolation, and state monitors."""

    def __init__(self, registry: Optional[ServiceRegistry] = None) -> None:
        self.registry = registry or ServiceRegistry()
        self._lock = threading.Lock()
        self._dependencies: Dict[str, List[str]] = {}

    def register_service(self, service: BaseService, dependencies: Optional[List[str]] = None) -> None:
        """Register a service with optional list of service name dependencies."""
        self.registry.register(service)
        with self._lock:
            self._dependencies[service.name] = dependencies or []

    def set_dependencies(self, name: str, dependencies: List[str]) -> None:
        with self._lock:
            if name in self._dependencies:
                self._dependencies[name] = dependencies

    def get_dependencies(self, name: str) -> List[str]:
        with self._lock:
            return self._dependencies.get(name, [])

    def validate_dependencies(self) -> bool:
        """Verify that all listed dependencies exist in the registry and there are no cycles."""
        with self._lock:
            all_services = set(self.registry.list_services())
            # 1. Existence check
            for name, deps in self._dependencies.items():
                for dep in deps:
                    if dep not in all_services:
                        logger.error("[ServiceManager] Validation failure: dependency %s of service %s is not registered", dep, name)
                        return False
            
            # 2. Cycle detection (DFS)
            visited = {}
            def has_cycle(node: str) -> bool:
                visited[node] = 1  # visiting
                for neighbor in self._dependencies.get(node, []):
                    if visited.get(neighbor, 0) == 1:
                        return True
                    if visited.get(neighbor, 0) == 0:
                        if has_cycle(neighbor):
                            return True
                visited[node] = 2  # visited
                return False

            for s in all_services:
                if visited.get(s, 0) == 0:
                    if has_cycle(s):
                        logger.error("[ServiceManager] Validation failure: circular dependency loop detected starting at %s", s)
                        return False
            return True

    def initialize_service(self, name: str) -> bool:
        """Initialize a service, ensuring dependencies are initialized first."""
        service = self.registry.get_service(name)
        if not service:
            return False

        # Verify dependencies are initialized or running
        for dep in self.get_dependencies(name):
            dep_status = self.registry.get_status(dep)
            if not dep_status or dep_status.state not in ("INITIALIZED", "RUNNING"):
                logger.error("[ServiceManager] Cannot initialize %s: dependency %s is not initialized/running", name, dep)
                self.registry.update_status(name, "FAILED", f"Dependency {dep} missing initialization")
                return False

        logger.info("[ServiceManager] Initializing service: %s", name)
        try:
            success = service.initialize()
            if success:
                self.registry.update_status(name, "INITIALIZED")
                return True
            else:
                self.registry.update_status(name, "FAILED", "Initialization method returned False")
                return False
        except Exception as e:
            logger.exception("[ServiceManager] Crash during initialization of service %s", name)
            self.registry.update_status(name, "FAILED", str(e))
            return False

    def start_service(self, name: str) -> bool:
        """Start a service, initializing if necessary, ensuring dependencies are running."""
        service = self.registry.get_service(name)
        status = self.registry.get_status(name)
        if not service or not status:
            return False

        # If already running, return success
        if status.state == "RUNNING":
            return True

        # Ensure dependencies are running
        for dep in self.get_dependencies(name):
            if not self.start_service(dep):
                logger.error("[ServiceManager] Cannot start %s: dependency %s failed to start", name, dep)
                self.registry.update_status(name, "FAILED", f"Dependency {dep} failed to start")
                return False

        # If not initialized, initialize
        if status.state not in ("INITIALIZED", "RUNNING"):
            if not self.initialize_service(name):
                return False

        logger.info("[ServiceManager] Starting service: %s", name)
        try:
            success = service.start()
            if success:
                self.registry.update_status(name, "RUNNING", reset_uptime=True)
                return True
            else:
                self.registry.update_status(name, "FAILED", "Start method returned False")
                return False
        except Exception as e:
            logger.exception("[ServiceManager] Crash during startup of service %s", name)
            self.registry.update_status(name, "FAILED", str(e))
            return False

    def stop_service(self, name: str) -> bool:
        """Stop a service, returning success/failure, logging errors."""
        service = self.registry.get_service(name)
        status = self.registry.get_status(name)
        if not service or not status:
            return False

        if status.state == "STOPPED":
            return True

        logger.info("[ServiceManager] Stopping service: %s", name)
        try:
            success = service.stop()
            if success:
                self.registry.update_status(name, "STOPPED")
                return True
            else:
                self.registry.update_status(name, "FAILED", "Stop method returned False")
                return False
        except Exception as e:
            logger.exception("[ServiceManager] Crash during shutdown of service %s", name)
            self.registry.update_status(name, "FAILED", str(e))
            return False

    def restart_service(self, name: str) -> bool:
        """Restart a service, incrementing restart_count, isolated from failures."""
        status = self.registry.get_status(name)
        if not status:
            return False

        logger.info("[ServiceManager] Restarting service: %s", name)
        status.restart_count += 1
        
        # Stop
        self.stop_service(name)
        # Start
        return self.start_service(name)

    def shutdown_all(self) -> None:
        """Gracefully shuts down all services in reverse registration/dependency order."""
        logger.info("[ServiceManager] Starting graceful shutdown of all services...")
        services = self.registry.list_services()
        # Simply reverse to stop last-initialized first
        for name in reversed(services):
            self.stop_service(name)
        logger.info("[ServiceManager] Graceful shutdown of all services complete.")

    def run_health_checks(self) -> Dict[str, str]:
        """Runs health evaluation across all registered services."""
        health_report = {}
        for name in self.registry.list_services():
            service = self.registry.get_service(name)
            status = self.registry.get_status(name)
            if not service or not status:
                continue
            
            if status.state != "RUNNING":
                health_report[name] = status.state
                continue

            try:
                healthy = service.health()
                if healthy:
                    health_report[name] = "HEALTHY"
                else:
                    self.registry.update_status(name, "DEGRADED", "Health check returned False")
                    health_report[name] = "DEGRADED"
            except Exception as e:
                logger.error("[ServiceManager] Health check crashed for %s: %s", name, e)
                self.registry.update_status(name, "FAILED", f"Health check crash: {e}")
                health_report[name] = "FAILED"
        return health_report


# ── Service Adapters ─────────────────────────────────────────────────────────

class MemoryService(BaseService):
    def __init__(self, memory_instance=None) -> None:
        self._memory = memory_instance

    @property
    def name(self) -> str:
        return "Memory"

    def initialize(self) -> bool:
        if self._memory is None:
            from memory.short_term import ShortTermMemory
            self._memory = ShortTermMemory()
        return True

    def start(self) -> bool:
        return True

    def stop(self) -> bool:
        return True

    def restart(self) -> bool:
        return True

    def health(self) -> bool:
        return True


class PluginManagerService(BaseService):
    def __init__(self, loader_instance=None) -> None:
        self._loader = loader_instance

    @property
    def name(self) -> str:
        return "Plugin Manager"

    def initialize(self) -> bool:
        if self._loader is None:
            from plugins.loader import PluginLoader
            self._loader = PluginLoader()
        return True

    def start(self) -> bool:
        self._loader.discover_and_load_plugins()
        return True

    def stop(self) -> bool:
        return True

    def restart(self) -> bool:
        return True

    def health(self) -> bool:
        return True


class StartupManagerService(BaseService):
    def __init__(self, manager_instance=None) -> None:
        self._manager = manager_instance

    @property
    def name(self) -> str:
        return "Startup Manager"

    def initialize(self) -> bool:
        if self._manager is None:
            from core.startup_manager import StartupManager
            self._manager = StartupManager()
        return True

    def start(self) -> bool:
        self._manager.initialize_startup()
        return True

    def stop(self) -> bool:
        return True

    def restart(self) -> bool:
        return True

    def health(self) -> bool:
        return True


class BrowserService(BaseService):
    def __init__(self, manager_instance=None) -> None:
        self._manager = manager_instance

    @property
    def name(self) -> str:
        return "Browser"

    def initialize(self) -> bool:
        if self._manager is None:
            from utils.browser_manager import BrowserManager
            self._manager = BrowserManager()
        return True

    def start(self) -> bool:
        return True

    def stop(self) -> bool:
        if self._manager:
            try:
                self._manager._loop.call_soon_threadsafe(self._manager._loop.stop)
            except Exception:
                pass
        return True

    def restart(self) -> bool:
        self.stop()
        return self.start()

    def health(self) -> bool:
        if self._manager and self._manager._thread.is_alive():
            return True
        return False


class AndroidService(BaseService):
    @property
    def name(self) -> str:
        return "Android"

    def initialize(self) -> bool:
        return True

    def start(self) -> bool:
        try:
            from tools.android_tool import _run_adb
            _, _ = _run_adb(["devices"], timeout=5)
        except Exception:
            pass
        return True

    def stop(self) -> bool:
        return True

    def restart(self) -> bool:
        return True

    def health(self) -> bool:
        return True


class VoiceService(BaseService):
    def __init__(self, voice_manager=None) -> None:
        self._vm = voice_manager

    @property
    def name(self) -> str:
        return "Voice"

    def initialize(self) -> bool:
        return True

    def start(self) -> bool:
        if self._vm:
            self._vm.start()
        return True

    def stop(self) -> bool:
        if self._vm:
            self._vm.stop()
        return True

    def restart(self) -> bool:
        self.stop()
        return self.start()

    def health(self) -> bool:
        if self._vm and self._vm.is_active:
            return True
        return False
