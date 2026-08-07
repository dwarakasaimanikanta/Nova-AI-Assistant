"""
tests/test_android_tool.py
---------------------------
Unit tests for the AndroidTool – Android phone integration via ADB.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.android_tool import AndroidTool, _load_contacts, _resolve_contact, CONTACTS_FILE


@pytest.fixture()
def tool() -> AndroidTool:
    return AndroidTool()


@pytest.fixture()
def sample_contacts(tmp_path: Path, monkeypatch):
    """Patch CONTACTS_FILE to point at a temp file with sample contacts."""
    contacts = {"amma": "+919876543210", "ravi": "+919123456789"}
    contacts_path = tmp_path / "contacts.json"
    contacts_path.write_text(json.dumps(contacts), encoding="utf-8")
    import tools.android_tool as mod
    monkeypatch.setattr(mod, "CONTACTS_FILE", contacts_path)
    return contacts_path


# ── Tool metadata ──────────────────────────────────────────────────────────────

def test_tool_name(tool):
    assert tool.name == "android"


def test_tool_description_contains_actions(tool):
    desc = tool.description
    assert "call" in desc
    assert "sms" in desc
    assert "whatsapp" in desc


def test_tool_parameters_schema(tool):
    schema = tool.parameters_schema
    assert "action" in schema["properties"]
    assert "contact" in schema["properties"]
    assert "message" in schema["properties"]


# ── Contact resolution ────────────────────────────────────────────────────────

def test_load_contacts_returns_empty_when_missing():
    """If contacts.json doesn't exist, return empty dict."""
    import tools.android_tool as mod
    original = mod.CONTACTS_FILE
    try:
        mod.CONTACTS_FILE = Path("/nonexistent/contacts.json")
        result = _load_contacts()
        assert result == {}
    finally:
        mod.CONTACTS_FILE = original


def test_load_contacts_reads_file(sample_contacts):
    contacts = _load_contacts()
    assert "amma" in contacts
    assert contacts["amma"] == "+919876543210"


def test_resolve_contact_found(sample_contacts):
    phone = _resolve_contact("Amma")
    assert phone == "+919876543210"


def test_resolve_contact_case_insensitive(sample_contacts):
    phone = _resolve_contact("RAVI")
    assert phone == "+919123456789"


def test_resolve_contact_not_found(sample_contacts):
    phone = _resolve_contact("unknown_person")
    assert phone is None


# ── Action: read_contacts ─────────────────────────────────────────────────────

def test_read_contacts_lists_entries(tool, sample_contacts):
    result = tool.execute(action="read_contacts")
    assert "Amma" in result or "amma" in result.lower()
    assert "+919876543210" in result


# ── Action: call ─────────────────────────────────────────────────────────────

def test_call_requires_contact(tool):
    result = tool.execute(action="call")
    assert "Failure" in result


def test_call_unknown_contact(tool, sample_contacts):
    result = tool.execute(action="call", contact="Stranger")
    assert "Failure" in result or "not found" in result.lower()


def test_call_known_contact_invokes_adb(tool, sample_contacts):
    with patch("tools.android_tool._run_adb", return_value=(True, "")) as mock_adb:
        result = tool.execute(action="call", contact="amma")
        assert "Success" in result or "Calling" in result
        mock_adb.assert_called_once()
        call_args = mock_adb.call_args[0][0]
        assert "android.intent.action.CALL" in call_args


def test_call_adb_failure(tool, sample_contacts):
    with patch("tools.android_tool._run_adb", return_value=(False, "device offline")):
        result = tool.execute(action="call", contact="amma")
        assert "Failure" in result


# ── Action: sms ──────────────────────────────────────────────────────────────

def test_sms_requires_contact(tool):
    result = tool.execute(action="sms", message="hello")
    assert "Failure" in result


def test_sms_requires_message(tool, sample_contacts):
    result = tool.execute(action="sms", contact="amma")
    assert "Failure" in result


def test_sms_success(tool, sample_contacts):
    with patch("tools.android_tool._run_adb", return_value=(True, "")):
        result = tool.execute(action="sms", contact="ravi", message="Hello Ravi")
        assert "Success" in result or "SMS" in result


# ── Action: whatsapp ──────────────────────────────────────────────────────────

def test_whatsapp_requires_contact(tool):
    result = tool.execute(action="whatsapp", message="hi")
    assert "Failure" in result


def test_whatsapp_requires_message(tool, sample_contacts):
    result = tool.execute(action="whatsapp", contact="amma")
    assert "Failure" in result


def test_whatsapp_success(tool, sample_contacts):
    with patch("tools.android_tool._run_adb", return_value=(True, "")):
        result = tool.execute(action="whatsapp", contact="amma", message="Hi Amma")
        assert "Success" in result or "WhatsApp" in result


# ── Action: read_notifications ────────────────────────────────────────────────

def test_read_notifications_success(tool):
    adb_output = "android.title=Gmail\nandroid.text=You have a new message"
    with patch("tools.android_tool._run_adb", return_value=(True, adb_output)):
        result = tool.execute(action="read_notifications")
        assert "notification" in result.lower() or "gmail" in result.lower()


def test_read_notifications_adb_failure(tool):
    with patch("tools.android_tool._run_adb", return_value=(False, "no devices")):
        result = tool.execute(action="read_notifications")
        assert "Failure" in result


# ── Unknown action ────────────────────────────────────────────────────────────

def test_unknown_action(tool):
    result = tool.execute(action="fly_to_moon")
    assert "Failure" in result or "Unknown" in result
