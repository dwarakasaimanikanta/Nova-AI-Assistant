"""
tests/test_contact_name_correction.py
--------------------------------------
Unit tests verifying the Contact Name Correction layer inside NovaEngine.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.engine import NovaEngine
from memory.short_term import ShortTermMemory


@pytest.fixture
def mock_memory():
    return MagicMock(spec=ShortTermMemory)


@pytest.fixture
def mock_contacts():
    return {
        "amma": "+917842209762",
        "Dad": "+919247475161",
        "Gnana": "+919553973270",
        "Ahamed": "+919392649549",
        "Deepak": "+919483272589",
        "Pradeep": "+919032222556",
        "Ravi": "+919999999999"
    }


def test_exact_matches(mock_memory, mock_contacts):
    """Verify that exact matched names remain identical or normalized correctly to stored case."""
    with patch("core.engine.NovaEngine._load_contacts", return_value=mock_contacts), \
         patch("plugins.loader.PluginLoader.discover_and_load_plugins", return_value=[]):
        engine = NovaEngine(memory=mock_memory)
        
        # Test exact match
        res = engine.correct_contact_names("Call Dad")
        assert res == "Call Dad"
        
        res = engine.correct_contact_names("Message Gnana Hello")
        assert res == "Message Gnana Hello"


def test_fuzzy_matches(mock_memory, mock_contacts):
    """Verify that spoken variations (like Emma, Ama, Nana, Ravy) resolve to correct contacts."""
    with patch("core.engine.NovaEngine._load_contacts", return_value=mock_contacts), \
         patch("plugins.loader.PluginLoader.discover_and_load_plugins", return_value=[]):
        engine = NovaEngine(memory=mock_memory)
        
        # Emma -> amma (similarity >= 80% via phonetic normalization)
        assert engine.correct_contact_names("Call Emma") == "Call amma"
        
        # Ama -> amma
        assert engine.correct_contact_names("Call Ama") == "Call amma"
        
        # Ravy -> Ravi
        assert engine.correct_contact_names("Message Ravy Hello") == "Message Ravi Hello"
        
        # Gnyana -> Gnana
        assert engine.correct_contact_names("WhatsApp Gnyana Hello") == "WhatsApp Gnana Hello"


def test_telugu_matches(mock_memory, mock_contacts):
    """Verify that Telugu transcribed contact names resolve to correct English contacts with proper Telugu suffixes."""
    with patch("core.engine.NovaEngine._load_contacts", return_value=mock_contacts), \
         patch("plugins.loader.PluginLoader.discover_and_load_plugins", return_value=[]):
        engine = NovaEngine(memory=mock_memory)
        
        # "అమ్మకి" -> "ammaకి" (Telugu suffix కి is stripped during match and appended back)
        assert engine.correct_contact_names("అమ్మకి కాల్ చేయి") == "ammaకి కాల్ చేయి"
        
        # "రవికి" -> "Raviకి"
        assert engine.correct_contact_names("రవికి మెసేజ్ పంపు") == "Raviకి మెసేజ్ పంపు"
        
        # "జ్ఞానకి" -> "Gnanaకి"
        assert engine.correct_contact_names("జ్ఞానకి వాట్సాప్ పంపు") == "Gnanaకి వాట్సాప్ పంపు"


def test_unknown_names_remain_unchanged(mock_memory, mock_contacts):
    """Verify that names not matching any contact closely (< 80%) are left unaltered."""
    with patch("core.engine.NovaEngine._load_contacts", return_value=mock_contacts), \
         patch("plugins.loader.PluginLoader.discover_and_load_plugins", return_value=[]):
        engine = NovaEngine(memory=mock_memory)
        
        # "John" is not in contacts and doesn't sound like any contact, so it remains unchanged
        assert engine.correct_contact_names("Call John") == "Call John"
        
        # "Srinivas" remains unchanged
        assert engine.correct_contact_names("Message Srinivas Hello") == "Message Srinivas Hello"


def test_non_action_keywords_not_corrected(mock_memory, mock_contacts):
    """Verify that name correction is not applied to normal search sentences or non-action requests."""
    with patch("core.engine.NovaEngine._load_contacts", return_value=mock_contacts), \
         patch("plugins.loader.PluginLoader.discover_and_load_plugins", return_value=[]):
        engine = NovaEngine(memory=mock_memory)
        
        # No action keyword (like call/message/whatsapp/etc.), so Emma is not corrected to amma
        assert engine.correct_contact_names("Who is Emma?") == "Who is Emma?"
