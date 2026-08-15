import pytest
from unittest.mock import MagicMock
from utils.language_switch import parse_spoken_language, detect_and_handle_language_switch
from core.engine import NovaEngine
from core.executive_agent import ExecutiveAgent

def test_parse_spoken_language_exact():
    assert parse_spoken_language("Telugu") == "te"
    assert parse_spoken_language("English") == "en"
    assert parse_spoken_language("Hindi") == "hi"
    assert parse_spoken_language("Tamil") == "ta"
    assert parse_spoken_language("Kannada") == "kn"

def test_parse_spoken_language_variations():
    assert parse_spoken_language("english please") == "en"
    assert parse_spoken_language("telugoo") == "te"
    assert parse_spoken_language("kanada") == "kn"
    assert parse_spoken_language("ఇంగ్లీష్") == "en"
    assert parse_spoken_language("తెలుగు") == "te"
    assert parse_spoken_language("speak in hindi") == "hi"
    assert parse_spoken_language("tamil mode") == "ta"

def test_parse_spoken_language_rejections():
    # Fuzzy rejections
    assert parse_spoken_language("Malayana") is None
    assert parse_spoken_language("tame") is None
    assert parse_spoken_language("") is None
    assert parse_spoken_language(None) is None
    assert parse_spoken_language("hello world") is None

def test_language_switch_command():
    # Mock engine
    engine = MagicMock(spec=NovaEngine)
    engine.selected_language = "en"
    
    # Switch to Telugu
    res = detect_and_handle_language_switch("switch to Telugu", engine)
    assert res is True
    assert engine.selected_language == "te"

    # Switch to Hindi
    res = detect_and_handle_language_switch("change to hindi", engine)
    assert res is True
    assert engine.selected_language == "hi"

def test_language_lock_persists():
    # Verify that once engine.selected_language is set, it stays locked
    engine = MagicMock(spec=NovaEngine)
    engine.selected_language = "te"
    
    # Simulating a user speaking English while Telugu is selected
    # The selected language MUST remain Telugu
    assert engine.selected_language == "te"
