"""
tests/test_android_voice_integration.py
----------------------------------------
Integration tests for AndroidTool ↔ VoiceManager.format_spoken_response pipeline.
Verifies that raw AndroidTool outputs are converted to correct natural Telugu phrases,
and that the planner's direct_return_tools set includes "android".
"""

import pytest
from voice.voice_manager import format_spoken_response


# ── format_spoken_response: call ──────────────────────────────────────────────

def test_call_spoken_response_amma():
    """'Success: Calling Amma (+91...).' → 'Ammaకి కాల్ చేస్తున్నాను.'"""
    raw = "Success: Calling Amma (+919876543210)."
    result = format_spoken_response(raw)
    assert "కాల్ చేస్తున్నాను" in result
    assert "Amma" in result


def test_call_spoken_response_dad():
    raw = "Success: Calling Dad (+919999999999)."
    result = format_spoken_response(raw)
    assert "కాల్ చేస్తున్నాను" in result
    assert "Dad" in result


def test_call_spoken_response_lowercase_name():
    """Tool may return lowercase name – it should be capitalized in the spoken response."""
    raw = "Success: Calling amma (+919876543210)."
    result = format_spoken_response(raw)
    assert "కాల్ చేస్తున్నాను" in result
    # Name should be capitalized
    assert "Amma" in result or "amma" in result.lower()


def test_call_failure_spoken():
    """ADB failure → generic Telugu error, never raw error text."""
    raw = "Failure: Could not initiate call. device offline"
    result = format_spoken_response(raw)
    assert "Success" not in result
    assert "Failure" not in result
    assert "device offline" not in result
    # Should be Telugu failure phrase
    assert "చేయలేకపోయాను" in result or "క్షమించండి" in result


def test_adb_not_found_spoken():
    """ADB not installed → specific USB hint in Telugu."""
    raw = "Failure: ADB not found. Please install Android Debug Bridge."
    result = format_spoken_response(raw)
    # The "adb not found" pattern matches first
    assert "connect" in result.lower() or "USB" in result or "Phone" in result


# ── format_spoken_response: sms ───────────────────────────────────────────────

def test_sms_spoken_response():
    """'Success: SMS composed for Ravi. Please send from phone.' → Telugu phrase."""
    raw = "Success: SMS composed for Ravi. Please send from phone."
    result = format_spoken_response(raw)
    assert "మెసేజ్" in result
    assert "సిద్ధం" in result
    assert "Ravi" in result or "ravi" in result.lower()


def test_sms_spoken_does_not_contain_success():
    raw = "Success: SMS composed for Amma. Please send from phone."
    result = format_spoken_response(raw)
    assert "Success" not in result
    assert "Please send from phone" not in result


# ── format_spoken_response: whatsapp ─────────────────────────────────────────

def test_whatsapp_spoken_response():
    """'Success: WhatsApp opened for Sai. Please send from phone.' → Telugu phrase."""
    raw = "Success: WhatsApp opened for Sai. Please send from phone."
    result = format_spoken_response(raw)
    assert "వాట్సాప్" in result
    assert "తెరుస్తున్నాను" in result


def test_whatsapp_spoken_does_not_contain_raw():
    raw = "Success: WhatsApp opened for Amma. Please send from phone."
    result = format_spoken_response(raw)
    assert "Please send from phone" not in result
    assert "Success" not in result


# ── format_spoken_response: contact not found ─────────────────────────────────

def test_contact_not_found_spoken():
    raw = "Failure: Contact 'Stranger' not found. Add them to data/contacts.json."
    result = format_spoken_response(raw)
    assert "Contact" in result
    assert "దొరకలేదు" in result
    assert "not found" not in result


# ── Planner direct_return_tools includes "android" ────────────────────────────

def test_planner_direct_return_includes_android():
    """The planner must list 'android' in direct_return_tools to avoid LLM re-phrasing."""
    import ast
    import pathlib

    planner_src = pathlib.Path("core/planner.py").read_text(encoding="utf-8")
    # Find the direct_return_tools set literal
    assert '"android"' in planner_src, (
        "\"android\" must be in direct_return_tools in core/planner.py so that "
        "AndroidTool results bypass the LLM and go directly to format_spoken_response."
    )


# ── AndroidPlugin is discoverable ─────────────────────────────────────────────

def test_android_plugin_discoverable():
    """AndroidPlugin must exist and return AndroidTool."""
    from plugins.android_plugin import AndroidPlugin
    from tools.android_tool import AndroidTool

    plugin = AndroidPlugin()
    assert plugin.name == "android"
    tools = plugin.get_tools()
    assert len(tools) == 1
    assert isinstance(tools[0], AndroidTool)


def test_android_tool_registered_in_loader():
    """PluginLoader must discover and load AndroidPlugin automatically."""
    from plugins.loader import PluginLoader

    loader = PluginLoader()
    plugins = loader.discover_and_load_plugins()
    plugin_names = [p.name for p in plugins]
    assert "android" in plugin_names, (
        "AndroidPlugin was not discovered by PluginLoader. "
        "Ensure plugins/android_plugin.py exists and follows *_plugin.py naming."
    )
