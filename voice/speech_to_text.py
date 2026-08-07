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

    def __init__(self, model_size: str = "small", device: str = "cpu") -> None:
        self.model_size = model_size
        self.device = device
        self.model = None

    def _lazy_load_model(self) -> None:
        if self.model is None:
            logger.info("Initializing faster-whisper model '%s' on %s...", self.model_size, self.device)
            try:
                from faster_whisper import WhisperModel
                # Using cpu, int8, cpu_threads=1 and num_workers=1 to prevent deadlocks on background threads
                self.model = WhisperModel(self.model_size, device=self.device, compute_type="int8", cpu_threads=1, num_workers=1)
                logger.info("faster-whisper model loaded successfully.")
            except Exception as e:
                logger.error("Failed to load faster-whisper model: %s", e)
                raise

    def transcribe(self, audio_path: Path, stop_event=None) -> str:
        if stop_event is not None and stop_event.is_set():
            logger.info("Transcription aborted due to stop_event.")
            return ""
            
        logger.info("[STT] Audio file received: %s (exists=%s)", audio_path, audio_path.exists())
        try:
            self._lazy_load_model()
        except Exception as e:
            logger.warning("Falling back to MockSTT due to model load failure: %s", e)
            return MockSTT().transcribe(audio_path)

        if not audio_path.exists():
            logger.error("Audio file does not exist: %s", audio_path)
            return ""

        if stop_event is not None and stop_event.is_set():
            logger.info("Transcription aborted due to stop_event.")
            return ""

        try:
            logger.info("[STT] Starting transcription using faster-whisper (vad_filter=True, language=auto)...")
            segments, info = self.model.transcribe(
                str(audio_path),
                beam_size=5,
                vad_filter=True,
                temperature=0.0,
                condition_on_previous_text=False
            )
            detected_lang = getattr(info, "language", "unknown")
            detected_prob = getattr(info, "language_probability", 0.0)
            logger.info("[STT] Detected language: '%s' (probability=%.2f)", detected_lang, detected_prob)
            
            # Consume the segments generator while checking stop_event for cancellation
            segments_list = []
            for seg in segments:
                if stop_event is not None and stop_event.is_set():
                    logger.info("[STT] Transcription cancelled mid-generation.")
                    return ""
                segments_list.append(seg)
            
            text_segments = []
            rejected_reasons = []
            
            for seg in segments_list:
                no_speech_prob = getattr(seg, "no_speech_prob", 0.0)
                avg_logprob = getattr(seg, "avg_logprob", 0.0)
                
                # Check for MagicMock or non-numeric types in tests
                if not isinstance(no_speech_prob, (int, float)):
                    no_speech_prob = 0.0
                if not isinstance(avg_logprob, (int, float)):
                    avg_logprob = 0.0

                # Log segment details (confidence, text, no_speech_prob)
                logger.info(
                    "[STT] Whisper segment text='%s', avg_logprob=%0.4f, no_speech_prob=%0.4f, start=%0.2fs, end=%0.2fs",
                    seg.text, avg_logprob, no_speech_prob, seg.start, seg.end
                )
                
                cleaned = "".join(ch for ch in seg.text.lower() if ch.isalnum() or ch.isspace()).strip()
                ignored_segments = {
                    "thank you", "thank you very much", "thanks for watching", "please subscribe",
                    "subscribed", "you", "bye", "go to", "and yeah", "oh", "so",
                    "thanks for watching and ill see you in the next one", "ill see you in the next video"
                }
                
                # Adaptive STT filtering
                is_silence = False
                reason = ""
                if no_speech_prob > 0.9:
                    is_silence = True
                    reason = f"no_speech_prob={no_speech_prob:.4f} > 0.9 (genuine silence)"
                elif no_speech_prob > 0.6:
                    # For moderate no_speech_prob, only reject if it is short noise/hallucination text
                    if len(cleaned) <= 5 or cleaned in ignored_segments:
                        is_silence = True
                        reason = f"no_speech_prob={no_speech_prob:.4f} > 0.6 with short/noise text ('{cleaned}')"
                
                if is_silence:
                    logger.info("[STT] Segment rejected: %s", reason)
                    rejected_reasons.append((seg.text, reason))
                elif avg_logprob < -1.5:
                    reason = f"avg_logprob={avg_logprob:.4f} < -1.5"
                    logger.info("[STT] Segment rejected: %s", reason)
                    rejected_reasons.append((seg.text, reason))
                elif cleaned in ignored_segments:
                    reason = "matches common hallucinated phrase list"
                    logger.info("[STT] Segment rejected: %s", reason)
                    rejected_reasons.append((seg.text, reason))
                else:
                    text_segments.append(seg.text)
                    
            full_text = " ".join(text_segments).strip()
            logger.info("[STT] Final combined transcript: '%s'", full_text)
            if rejected_reasons:
                logger.info("[STT] Rejected segments log: %s", rejected_reasons)
                
            return full_text
        except Exception as e:
            logger.exception("Error during faster-whisper transcription: %s", e)
            return ""


class MockSTT(SpeechToTextEngine):
    """Mock Speech-To-Text engine for tests and offline fallback without downloading model binary weights."""

    def __init__(self, predefined_response: str = "hello") -> None:
        self.predefined_response = predefined_response

    def transcribe(self, audio_path: Path, stop_event=None) -> str:
        logger.info("[MockSTT] Transcribing %s -> '%s'", audio_path, self.predefined_response)
        return self.predefined_response
