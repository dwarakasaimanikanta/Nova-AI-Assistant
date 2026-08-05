"""
voice/wake_word.py
------------------
Detects wake words in audio captures using Speech-to-Text transcription.
"""

from pathlib import Path
from utils.logger import get_logger
from voice.speech_to_text import SpeechToTextEngine

logger = get_logger(__name__)


class WakeWordDetector:
    """Detects the wake word ('Hey Nova') in an audio file."""

    def __init__(self, stt_engine: SpeechToTextEngine, wake_word: str = "hey nova") -> None:
        self.stt_engine = stt_engine
        self.wake_word = wake_word.strip().lower()

    def detect(self, audio_path: Path) -> bool:
        """
        Transcribes the audio file and checks if the wake word is present.
        """
        try:
            transcript = self.stt_engine.transcribe(audio_path).strip().lower()
            
            # Clean punctuation to improve detection robustness
            clean_transcript = "".join(ch for ch in transcript if ch.isalnum() or ch.isspace())
            logger.debug("Wake word detection transcript check: '%s'", clean_transcript)
            
            # Match wake word or variations
            if self.wake_word in clean_transcript or "nova" in clean_transcript:
                logger.info("Wake word '%s' detected in transcript!", self.wake_word)
                return True
        except Exception as e:
            logger.error("Error in wake word detection: %s", e)
            
        return False
