"""
tests/test_tools/test_android_permission.py
--------------------------------------------
Unit tests for AndroidTool PermissionGate integration.
Verifies that call/sms/whatsapp/read_contacts are auto-approved (LOW risk)
and read_notifications is blocked without a callback (HIGH risk).
"""

from typing import Any

import pytest

from tools.permission_gate import PermissionGate
from tools.android_tool import AndroidTool
from tools.base_tool import RiskLevel


@pytest.fixture()
def gate() -> PermissionGate:
    return PermissionGate()


@pytest.fixture()
def tool() -> AndroidTool:
    return AndroidTool()


# ── call is auto-approved ────────────────────────────────────────────────────

def test_android_call_auto_approved(gate, tool):
    """action=call must be auto-approved regardless of callback (voice-safe)."""
    result = gate.check_permission(tool, {"action": "call", "contact": "Amma"})
    assert result is True


def test_android_call_no_callback_approved(gate, tool):
    """action=call must be approved even when no CLI callback is registered."""
    assert gate._callback is None  # Confirm no callback
    result = gate.check_permission(tool, {"action": "call", "contact": "Amma"})
    assert result is True


# ── sms is auto-approved ─────────────────────────────────────────────────────

def test_android_sms_auto_approved(gate, tool):
    result = gate.check_permission(tool, {"action": "sms", "contact": "Ravi", "message": "Hi"})
    assert result is True


# ── whatsapp is auto-approved ─────────────────────────────────────────────────

def test_android_whatsapp_auto_approved(gate, tool):
    result = gate.check_permission(tool, {"action": "whatsapp", "contact": "Sai", "message": "Hello"})
    assert result is True


# ── read_contacts is auto-approved ───────────────────────────────────────────

def test_android_read_contacts_auto_approved(gate, tool):
    result = gate.check_permission(tool, {"action": "read_contacts"})
    assert result is True


# ── read_notifications stays HIGH (private data) ─────────────────────────────

def test_android_read_notifications_denied_without_callback(gate, tool):
    """read_notifications must be HIGH risk – denied without a callback."""
    result = gate.check_permission(tool, {"action": "read_notifications"})
    assert result is False


def test_android_read_notifications_approved_with_callback(gate, tool):
    """read_notifications is approved when a CLI callback confirms."""
    gate.set_callback(lambda name, args: True)
    result = gate.check_permission(tool, {"action": "read_notifications"})
    assert result is True


def test_android_read_notifications_denied_with_denying_callback(gate, tool):
    gate.set_callback(lambda name, args: False)
    result = gate.check_permission(tool, {"action": "read_notifications"})
    assert result is False


# ── CLI callback does NOT affect call/sms/whatsapp (already LOW) ──────────────

def test_android_call_approved_even_with_denying_callback(gate, tool):
    """A CLI callback that returns False must NOT block call/sms/whatsapp.
    They are resolved as LOW risk before the callback is ever consulted."""
    gate.set_callback(lambda name, args: False)
    # call is LOW risk → callback is never consulted → True
    result = gate.check_permission(tool, {"action": "call", "contact": "Amma"})
    assert result is True


def test_android_sms_approved_even_with_denying_callback(gate, tool):
    gate.set_callback(lambda name, args: False)
    result = gate.check_permission(tool, {"action": "sms", "contact": "Ravi", "message": "Hi"})
    assert result is True


def test_android_whatsapp_approved_even_with_denying_callback(gate, tool):
    gate.set_callback(lambda name, args: False)
    result = gate.check_permission(tool, {"action": "whatsapp", "contact": "Sai", "message": "Hey"})
    assert result is True


# ── Unknown action falls through to HIGH ─────────────────────────────────────

def test_android_unknown_action_high_risk(gate, tool):
    """An unknown action should be treated as HIGH risk (denied without callback)."""
    result = gate.check_permission(tool, {"action": "unknown_action"})
    assert result is False
