import os
import sys
import pytest
from unittest.mock import MagicMock, patch

from voice.voice_manager import VoiceManager, format_spoken_response
from tools.voice import VoiceTool

class DummyEngine:
    def __init__(self):
        self.last_query = None

    def handle_input(self, query: str, stream: bool = False) -> str:
        self.last_query = query
        # Simple simulated response mapping
        if "Respond in Telugu language please" in query:
            if "what time is it" in query.lower():
                return "ఇప్పుడు సమయం 10:00 AM"
            return "సరే బాస్"
        else:
            if "what time is it" in query.lower():
                return "Current time is 10:00 AM"
            return "Sure Boss"

def test_prompt_propagation_and_telugu_unicode():
    """Verify that when telugu_mode=True:
    1. Prompt propagation adds the Telugu instruction to the LLM.
    2. The generated text is not English and contains Telugu Unicode.
    """
    engine = DummyEngine()
    vm = VoiceManager(engine=engine, voice_input_enabled=True)
    
    # 1. Test telugu_mode = True
    vm.telugu_mode = True
    
    # Simulate routing command via _safe_engine
    res = vm._safe_engine("What time is it?")
    
    # Verify instruction propagation
    assert "Respond in Telugu language please" in engine.last_query
    
    # Verify Telugu Unicode is present in the response
    has_telugu_unicode = any("\u0c00" <= ch <= "\u0c7f" for ch in res)
    assert has_telugu_unicode, f"Response should contain Telugu Unicode characters: {res}"
    assert "What time is it?" not in res, "Response should not be the original English prompt"
    assert "Current time is" not in res, "Response should not remain English"
    
    # 2. Test telugu_mode = False (English mode preserved)
    vm.telugu_mode = False
    res_en = vm._safe_engine("What time is it?")
    
    assert "Respond in Telugu language please" not in engine.last_query
    assert "10:00 AM" in res_en
    # Verify NO Telugu Unicode in standard English response
    has_telugu_unicode_en = any("\u0c00" <= ch <= "\u0c7f" for ch in res_en)
    assert not has_telugu_unicode_en, f"English response should not contain Telugu Unicode: {res_en}"

def test_voice_selection_fails_when_english_only_selected():
    """Verify that VoiceTool fails when telugu_mode=True but SAPI only has English voices.
    This guarantees that the test fails on an English-only environment.
    """
    tool = VoiceTool()
    
    # We patch platform to Windows and bypass pytest check in tools/voice.py
    with patch("tools.voice.platform.system", return_value="Windows"):
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            with patch.object(VoiceTool, "_generate_audio_sync", side_effect=RuntimeError("Simulated edge-tts failure")):
                with patch("win32com.client.Dispatch") as mock_dispatch:
                    mock_speaker = MagicMock()
                    mock_dispatch.return_value = mock_speaker
                    
                    # Mock speaker GetVoices to return ONLY English voices
                    mock_voices = MagicMock()
                    mock_speaker.GetVoices.return_value = mock_voices
                    
                    mock_voice_eng = MagicMock()
                    mock_voice_eng.GetAttribute.return_value = "409" # English
                    mock_voice_eng.GetDescription.return_value = "Microsoft David Desktop"
                    
                    mock_voices.Item.return_value = mock_voice_eng
                    mock_voices.__len__.return_value = 1
                    
                    VoiceTool._sapi_speaker = None
                    # Execute with telugu_mode=True must FAIL if only English voices are available
                    res = tool.execute(text="సరే బాస్", telugu_mode=True)
                    assert res.startswith("Failure"), f"Should fail when only English voice is selected under telugu_mode=True: {res}"
                    assert "No Telugu-capable SAPI voice" in res

def test_voice_selection_passes_when_telugu_voice_available():
    """Verify that VoiceTool successfully selects a Telugu SAPI voice when available."""
    tool = VoiceTool()
    
    with patch("tools.voice.platform.system", return_value="Windows"):
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            with patch.object(VoiceTool, "_generate_audio_sync", side_effect=RuntimeError("Simulated edge-tts failure")):
                with patch("win32com.client.Dispatch") as mock_dispatch:
                    mock_speaker = MagicMock()
                    mock_dispatch.return_value = mock_speaker
                    mock_speaker.Status.RunningState = 0
                    
                    # Mock speaker GetVoices to return a Telugu voice
                    mock_voices = MagicMock()
                    mock_speaker.GetVoices.return_value = mock_voices
                    
                    mock_voice_tel = MagicMock()
                    mock_voice_tel.GetAttribute.return_value = "44a" # Telugu
                    mock_voice_tel.GetDescription.return_value = "Microsoft Speech Telugu Voice"
                    
                    mock_voices.Item.return_value = mock_voice_tel
                    mock_voices.__len__.return_value = 1
                    
                    VoiceTool._sapi_speaker = None
                    res = tool.execute(text="సరే బాస్", telugu_mode=True)
                    assert res.startswith("Success"), f"Should succeed when Telugu voice is available: {res}"
                    # Verify speaker.Voice was set to the Telugu voice
                    assert mock_speaker.Voice == mock_voice_tel

def test_english_voice_restoration():
    """Verify that VoiceTool restores/selects an English voice when telugu_mode=False."""
    tool = VoiceTool()
    
    with patch("tools.voice.platform.system", return_value="Windows"):
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            with patch.object(VoiceTool, "_generate_audio_sync", side_effect=RuntimeError("Simulated edge-tts failure")):
                with patch("win32com.client.Dispatch") as mock_dispatch:
                    mock_speaker = MagicMock()
                    mock_dispatch.return_value = mock_speaker
                    mock_speaker.Status.RunningState = 0
                    
                    mock_voices = MagicMock()
                    mock_speaker.GetVoices.return_value = mock_voices
                    
                    mock_voice_eng = MagicMock()
                    mock_voice_eng.GetAttribute.return_value = "409"
                    mock_voice_eng.GetDescription.return_value = "Microsoft David Desktop"
                    
                    mock_voices.Item.return_value = mock_voice_eng
                    mock_voices.__len__.return_value = 1
                    
                    VoiceTool._sapi_speaker = None
                    res = tool.execute(text="Hello", telugu_mode=False)
                    assert res.startswith("Success")
                    # Verify speaker.Voice was set to the English voice
                    assert mock_speaker.Voice == mock_voice_eng
