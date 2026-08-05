"""
tests/test_tools/test_permission_gate.py
-----------------------------------------
Unit tests for Nova's PermissionGate.
"""

from typing import Any

from tools.permission_gate import PermissionGate
from tools.base_tool import BaseTool, RiskLevel


class MockHighRiskTool(BaseTool):
    @property
    def name(self) -> str:
        return "high_risk_mock"

    @property
    def description(self) -> str:
        return "mock"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.HIGH

    def execute(self, **kwargs: Any) -> str:
        return "run"


class MockLowRiskTool(BaseTool):
    @property
    def name(self) -> str:
        return "low_risk_mock"

    @property
    def description(self) -> str:
        return "mock"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    def execute(self, **kwargs: Any) -> str:
        return "run"


def test_permission_gate_low_risk_auto_approve() -> None:
    """Ensure low-risk tools bypass checks and are approved automatically."""
    gate = PermissionGate()
    tool = MockLowRiskTool()
    assert gate.check_permission(tool, {}) is True


def test_permission_gate_high_risk_denied_by_default() -> None:
    """Ensure high-risk tools are denied if no handler callback is registered."""
    gate = PermissionGate()
    tool = MockHighRiskTool()
    assert gate.check_permission(tool, {}) is False


def test_permission_gate_high_risk_callback_approval() -> None:
    """Ensure high-risk tools route execution queries to the callback handler."""
    gate = PermissionGate()
    tool = MockHighRiskTool()

    # Callback approving the query
    gate.set_callback(lambda name, args: True)
    assert gate.check_permission(tool, {}) is True

    # Callback refusing the query
    gate.set_callback(lambda name, args: False)
    assert gate.check_permission(tool, {}) is False
