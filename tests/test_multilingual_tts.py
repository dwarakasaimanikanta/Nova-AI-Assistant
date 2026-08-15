import os
import sys
import pytest
from unittest.mock import MagicMock, patch

from voice.voice_manager import VoiceManager
from tools.voice import VoiceTool

class DummyEngine:
    def __init__(self):
        self.last_query = None

    def handle_input(self, query: str, stream: bool = False) -> str:
        self.last_query = query
        return "Sure Boss"

def test_language_voice_mapping():
    """Verify that all 5 language keys exist and map to the correct Edge voice."""
    tool = VoiceTool()
    
    # We can mock _generate_audio_sync to avoid any network requests
    with patch.object(tool, "_generate_audio_sync") as mock_gen:
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}): # trigger SAPI or edge-tts path
            with patch("tools.voice.platform.system", return_value="Windows"):
                with patch("ctypes.windll.winmm.mciSendStringW", return_value=0):
                    with patch("os.path.exists", return_value=True):
                        with patch("os.path.getsize", return_value=100):
                            
                            # Test English -> en-US-AriaNeural
                            with patch("tools.voice.logger") as mock_logger:
                                tool.execute(text="Hello", response_language="english")
                                mock_logger.info.assert_any_call(
                                    "[VOICE-LANGUAGE] Selected Language: %s | Neural Voice: %s",
                                    "english", "en-US-AriaNeural"
                                )
                                
                            # Test Telugu -> te-IN-ShrutiNeural
                            with patch("tools.voice.logger") as mock_logger:
                                tool.execute(text="హలో", response_language="telugu")
                                mock_logger.info.assert_any_call(
                                    "[VOICE-LANGUAGE] Selected Language: %s | Neural Voice: %s",
                                    "telugu", "te-IN-ShrutiNeural"
                                )
                                
                            # Test Hindi -> hi-IN-SwaraNeural
                            with patch("tools.voice.logger") as mock_logger:
                                tool.execute(text="नमस्ते", response_language="hindi")
                                mock_logger.info.assert_any_call(
                                    "[VOICE-LANGUAGE] Selected Language: %s | Neural Voice: %s",
                                    "hindi", "hi-IN-SwaraNeural"
                                )

                            # Test Tamil -> ta-IN-PallaviNeural
                            with patch("tools.voice.logger") as mock_logger:
                                tool.execute(text="வணக்கம்", response_language="tamil")
                                mock_logger.info.assert_any_call(
                                    "[VOICE-LANGUAGE] Selected Language: %s | Neural Voice: %s",
                                    "tamil", "ta-IN-PallaviNeural"
                                )

                            # Test Kannada -> kn-IN-SapnaNeural
                            with patch("tools.voice.logger") as mock_logger:
                                tool.execute(text="ನಮಸ್ಕಾರ", response_language="kannada")
                                mock_logger.info.assert_any_call(
                                    "[VOICE-LANGUAGE] Selected Language: %s | Neural Voice: %s",
                                    "kannada", "kn-IN-SapnaNeural"
                                )

def test_response_language_changes_and_propagation():
    """Verify that response_language changes correctly and propagates properly."""
    from core.language_session import LanguageSession
    LanguageSession().selected_language = "en"
    
    engine = DummyEngine()
    vm = VoiceManager(engine=engine, voice_input_enabled=True)

    
    # 1. Default should be english
    assert vm.response_language in ("en", "english")
    assert not vm.telugu_mode
    
    # 2. Change response_language to telugu and assert telugu_mode compatibility
    vm.response_language = "telugu"
    assert vm.selected_language == "te"
    assert vm.telugu_mode
    
    # 3. Change telugu_mode back and assert response_language updates
    vm.telugu_mode = False
    assert vm.selected_language == "en"
    
    # 4. Change response_language to hindi
    vm.response_language = "hindi"
    assert vm.selected_language == "hi"

def test_no_actual_network_calls_during_unit_tests():
    """Verify that no actual network calls are made when ENVIRONMENT is 'test'."""
    tool = VoiceTool()
    
    with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
        with patch.object(tool, "_generate_audio_sync") as mock_gen:
            res = tool.execute(text="Hello", response_language="telugu")
            assert "Success" in res
            # Ensure edge-tts save was NOT called
            mock_gen.assert_not_called()
