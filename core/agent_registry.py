"""
core/agent_registry.py
----------------------
Production-grade Agent Registry, dependency injection, and resolver subsystem.
"""

from __future__ import annotations

import importlib
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AgentMetadata:
    """Metadata detailing the agent identification, specifications and dependencies."""
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = "Nova Team"
    dependencies: Set[str] = field(default_factory=set)


@dataclass
class AgentDescriptor:
    """Internal registry descriptor containing runtime info for an agent."""
    metadata: AgentMetadata
    class_path: str  # Format: "module_name.ClassName"
    singleton: bool = True
    enabled: bool = True
    instance: Optional[Any] = None
    factory_func: Optional[Callable[[], Any]] = None
    loaded: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Agent Factory
# ─────────────────────────────────────────────────────────────────────────────

class AgentFactory:
    """Instantiates agents, injecting required dependencies."""

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    def create(self, descriptor: AgentDescriptor) -> Any:
        if descriptor.factory_func:
            return descriptor.factory_func()

        # Dynamically import module and class
        try:
            parts = descriptor.class_path.rsplit(".", 1)
            if len(parts) < 2:
                raise ValueError(f"Invalid class path format: '{descriptor.class_path}'")
            module_name, class_name = parts[0], parts[1]
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
        except Exception as err:
            logger.exception("Failed to import agent class '%s': %s", descriptor.class_path, err)
            raise RuntimeError(f"Failed to load agent class '{descriptor.class_path}': {err}")

        # Resolve dependencies to inject into constructor
        kwargs = {}
        # Simple injection: if the constructor accepts other agents, query the registry
        import inspect
        try:
            sig = inspect.signature(cls.__init__)
            params = sig.parameters
            for name, param in params.items():
                if name in ("self", "args", "kwargs"):
                    continue
                # If param matches a registered agent name, resolve it
                if self.registry.is_registered(name):
                    kwargs[name] = self.registry.resolve(name)
                elif name.endswith("_agent") and self.registry.is_registered(name[:-6]):
                    kwargs[name] = self.registry.resolve(name[:-6])
                # Special cases:
                elif name == "engine":
                    engine = self.registry.get_engine()
                    if engine:
                        kwargs[name] = engine
        except Exception as sig_err:
            logger.debug("Failed inspect signature of %s: %s", cls.__name__, sig_err)

        try:
            instance = cls(**kwargs)
            return instance
        except Exception as inst_err:
            logger.exception("Failed to instantiate agent '%s': %s", descriptor.metadata.name, inst_err)
            raise RuntimeError(f"Failed to instantiate agent '{descriptor.metadata.name}': {inst_err}")


# ─────────────────────────────────────────────────────────────────────────────
# Agent Loader & Discoverer
# ─────────────────────────────────────────────────────────────────────────────

class AgentLoader:
    """Discovers and auto-loads descriptors into the registry."""

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    def discover_and_register_defaults(self) -> None:
        """Registers default sub-agents using static descriptors for reliability."""
        default_agents = [
            (
                AgentMetadata("coding", description="Autonomous software generator"),
                "agents.coding_agent.CodingAgent"
            ),
            (
                AgentMetadata("browser", description="Autonomous web operator"),
                "agents.browser_agent.BrowserAgent"
            ),
            (
                AgentMetadata("android", description="Autonomous phone operator"),
                "agents.android_agent.AndroidAgent"
            ),
            (
                AgentMetadata("workspace", description="Local filesystem manager"),
                "agents.workspace_agent.WorkspaceAgent"
            ),
            (
                AgentMetadata("planner", description="Autonomous reasoning engine"),
                "agents.planner_agent.PlannerAgent"
            ),
            (
                AgentMetadata("memory", description="Persistent intelligence layer"),
                "agents.memory_agent.MemoryAgent"
            ),
        ]

        for meta, class_path in default_agents:
            # We don't overwrite if already registered manually
            if not self.registry.is_registered(meta.name):
                descriptor = AgentDescriptor(metadata=meta, class_path=class_path, singleton=True)
                self.registry.register(descriptor)


# ─────────────────────────────────────────────────────────────────────────────
# Agent Registry & Resolver
# ─────────────────────────────────────────────────────────────────────────────

class AgentRegistry:
    """Thread-safe Agent Registry and DI coordinator."""

    def __init__(self) -> None:
        self._descriptors: Dict[str, AgentDescriptor] = {}
        self._lock = threading.Lock()
        self._factory = AgentFactory(self)
        self._loader = AgentLoader(self)
        self._engine: Optional[Any] = None

    def set_engine(self, engine: Any) -> None:
        self._engine = engine

    def get_engine(self) -> Optional[Any]:
        return self._engine

    def register(self, descriptor: AgentDescriptor) -> None:
        with self._lock:
            name = descriptor.metadata.name.lower()
            self._descriptors[name] = descriptor
            logger.info("Registered agent descriptor: '%s'", name)

    def unregister(self, name: str) -> bool:
        with self._lock:
            name = name.lower()
            if name in self._descriptors:
                del self._descriptors[name]
                logger.info("Unregistered agent descriptor: '%s'", name)
                return True
            return False

    def is_registered(self, name: str) -> bool:
        with self._lock:
            return name.lower() in self._descriptors

    def enable(self, name: str) -> bool:
        with self._lock:
            name = name.lower()
            if name in self._descriptors:
                self._descriptors[name].enabled = True
                return True
            return False

    def disable(self, name: str) -> bool:
        with self._lock:
            name = name.lower()
            if name in self._descriptors:
                self._descriptors[name].enabled = False
                return True
            return False

    def get_descriptor(self, name: str) -> Optional[AgentDescriptor]:
        with self._lock:
            return self._descriptors.get(name.lower())

    def get_all_descriptors(self) -> List[AgentDescriptor]:
        with self._lock:
            return list(self._descriptors.values())

    def resolve(self, name: str) -> Any:
        """
        Resolves a dependency injection query.
        Returns the instantiated agent (creating it if lazy-loaded singleton).
        """
        name = name.lower()
        desc = self.get_descriptor(name)
        if not desc:
            raise ValueError(f"No agent registered with name '{name}'")

        if not desc.enabled:
            raise RuntimeError(f"Agent '{name}' is currently disabled")

        if desc.singleton:
            if desc.loaded and desc.instance is not None:
                return desc.instance

            with self._lock:
                # Double-checked locking
                if desc.loaded and desc.instance is not None:
                    return desc.instance
                logger.info("Lazy-loading agent instance: '%s'", name)
                desc.instance = self._factory.create(desc)
                desc.loaded = True
                return desc.instance
        else:
            return self._factory.create(desc)

    def load_defaults(self) -> None:
        self._loader.discover_and_register_defaults()

    def check_health(self, name: str) -> bool:
        """Executes a diagnostic health check on an agent."""
        try:
            agent = self.resolve(name)
            # Diagnostic check: verify handle_input or execute exists
            return hasattr(agent, "execute") or hasattr(agent, "handle_input")
        except Exception as e:
            logger.error("Health check failed for agent '%s': %s", name, e)
            return False
