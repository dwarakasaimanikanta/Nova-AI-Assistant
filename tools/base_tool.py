"""
tools/base_tool.py
------------------
Abstract base class and structures for tools in Nova.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    """Safety and verification levels for tools."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class BaseTool(ABC):
    """Abstract base class that all tools must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The unique machine-readable name of the tool."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Natural language description explaining when and how to use the tool."""
        pass

    @property
    @abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """
        JSON schema describing parameters expected by the tool.
        
        Must return standard JSON Schema object structure, e.g.:
        {
            "type": "object",
            "properties": {
                "param_name": {
                    "type": "string",
                    "description": "helpful explanation"
                }
            },
            "required": ["param_name"]
        }
        """
        pass

    @property
    def risk_level(self) -> RiskLevel:
        """The safety category of this tool. Defaults to LOW."""
        return RiskLevel.LOW

    @abstractmethod
    def execute(self, **kwargs: Any) -> str:
        """
        Execute the tool action with parameters passed as keyword args.

        Args:
            **kwargs: Arbitrary parameter arguments parsed by the planner.

        Returns:
            The string result of the tool invocation.
        """
        pass
