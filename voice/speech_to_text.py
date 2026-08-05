"""
voice/speech_to_text.py
-----------------------
Speech-to-text engines including faster-whisper implementation and mock fallback.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from utils.logger import get_logger

logger = get_logger(__name__)


class SpeechToTextEngine(ABC):
    """Abstract base class for Speech-To-Text engines."""

    @abstractmethod
    def transcribe(self, audio_path: Path) -> str:
        """Transcribe audio from file path and return text."""
        pass


class FasterWhisperSTT(SpeechToTextEngine):
    """Speech-to-text using faster-whisper model."""

    def __init__(self, model_size: str = "tiny", device: str = "cpu") -> None:
        self.model_size = model_size
        self.device = device
        self.model = None

    def _lazy_load_model(self) -> None:
        if self.model is None:
            logger.info("Initializing faster-whisper model '%s' on %s...", self.model_size, self.device)
            try:
                from faster_whisper import WhisperModel
                # Using cpu and int8 for high compatibility and speed
                self.model = WhisperModel(self.model_size, device=self.device, compute_type="int8")
                logger.info("faster-whisper model loaded successfully.")
            except Exception as e:
                logger.error("Failed to load faster-whisper model: %s", e)
                raise

    def transcribe(self, audio_path: Path) -> str:
        try:
            self._lazy_load_model()
        except Exception as e:
            logger.warning("Falling back to MockSTT due to model load failure: %s", e)
            return MockSTT().transcribe(audio_path)

        if not audio_path.exists():
            logger.error("Audio file does not exist: %s", audio_path)
            return ""

        try:
            logger.info("Transcribing audio file %s...", audio_path.name)
            # Transcribe returns a generator of segments, and transcription info
            segments, info = self.model.transcribe(str(audio_path), beam_size=5)
            text_segments = [seg.text for seg in segments]
            full_text = " ".join(text_segments).strip()
            logger.info("Transcription completed. Text: '%s'", full_text)
            return full_text
        except Exception as e:
            logger.exception("Error during faster-whisper transcription: %s", e)
            return ""


class MockSTT(SpeechToTextEngine):
    """Mock Speech-To-Text engine for tests and offline fallback without downloading model binary weights."""

    def __init__(self, predefined_response: str = "hello") -> None:
        self.predefined_response = predefined_response

    def transcribe(self, audio_path: Path) -> str:
        logger.info("[MockSTT] Transcribing %s -> '%s'", audio_path, self.predefined_response)
        return self.predefined_response
