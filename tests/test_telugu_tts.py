import pytest
import logging
from unittest.mock import MagicMock, patch
from voice.voice_manager import format_spoken_response
from tools.voice import VoiceTool

def test_format_spoken_response_telugu():
    # Verify time/date patterns still format correctly in Telugu mode
    res_time = format_spoken_response("current time is 04:20 PM", telugu_mode=True)
    assert "ఇప్పుడు సమయం" in res_time

    # 'what time is it' is a free-text phrase — not a tool result pattern.
    # It should pass through unchanged (the LLM already writes in Telugu when selected).
    res_what_time = format_spoken_response("what time is it", telugu_mode=True)
    assert res_what_time == "what time is it"  # pass-through: short LLM answer

    # 'what can i help you with today' is also LLM free text — pass through
    res_general = format_spoken_response("what can i help you with today", telugu_mode=True)
    assert res_general == "what can i help you with today"

def test_voice_tool_logging_and_selection():
    # Verify that VoiceTool logs telugu_mode and text before speaking
    tool = VoiceTool()
    
    # We patch logging to capture logs and speaker to mock SAPI calls
    with patch("tools.voice.logger") as mock_logger:
        # Mock SAPI speaker execution to avoid actual output during test
        with patch("tools.voice.platform.system", return_value="Windows"):
            with patch("win32com.client.Dispatch") as mock_dispatch:
                mock_speaker = MagicMock()
                mock_dispatch.return_value = mock_speaker
                mock_speaker.Status.RunningState = 0
                
                # Mock GetVoices returning a dummy list
                mock_voices = MagicMock()
                mock_speaker.GetVoices.return_value = mock_voices
                mock_voices.Item.return_value.GetAttribute.return_value = "409"
                mock_voices.Item.return_value.GetDescription.return_value = "English Voice"
                mock_voices.__len__.return_value = 1
                
                tool.execute(text="సరే బాస్", telugu_mode=True)
                
                # Check that logging occurred
                mock_logger.info.assert_any_call("[VOICE-LANGUAGE] telugu_mode=%s", True)
                mock_logger.info.assert_any_call("[VOICE-LANGUAGE] TTS input text: %s", "సరే బాస్")
