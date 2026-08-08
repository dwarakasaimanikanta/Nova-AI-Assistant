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
            logger.info("[STT] Initializing faster-whisper model '%s' on %s...", self.model_size, self.device)
            try:
                from faster_whisper import WhisperModel
                self.model = WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type="int8",
                    cpu_threads=2,
                    num_workers=1,
                )
                logger.info("[STT] faster-whisper model '%s' loaded successfully.", self.model_size)
            except Exception as e:
                logger.error("[STT] Failed to load faster-whisper model: %s", e)
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
            logger.info("[STT] Transcribing command (vad_filter=False, language=auto)...")
            segments, info = self.model.transcribe(
                str(audio_path),
                beam_size=3,
                vad_filter=False,
                temperature=0.0,
                condition_on_previous_text=False,
                language=None,
                initial_prompt="Hello Nova. Open Chrome. What time is it? Create a website.",
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
                compression_ratio = getattr(seg, "compression_ratio", 0.0)
                duration = seg.end - seg.start
                
                # Check for MagicMock or non-numeric types in tests
                if not isinstance(no_speech_prob, (int, float)):
                    no_speech_prob = 0.0
                if not isinstance(avg_logprob, (int, float)):
                    avg_logprob = 0.0
                if not isinstance(compression_ratio, (int, float)):
                    compression_ratio = 0.0

                # Log segment details (text, avg_logprob, no_speech_prob, compression_ratio, language, duration)
                logger.info(
                    "[STT] Segment text='%s', avg_logprob=%0.4f, no_speech_prob=%0.4f, compression_ratio=%0.4f, language='%s', duration=%0.2fs",
                    seg.text, avg_logprob, no_speech_prob, compression_ratio, detected_lang, duration
                )
                
                cleaned = "".join(ch for ch in seg.text.lower() if ch.isalnum() or ch.isspace()).strip()
                ignored_segments = {
                    "thank you", "thank you very much", "thanks for watching", "please subscribe",
                    "subscribed", "you", "bye", "go to", "and yeah", "oh", "so",
                    "thanks for watching and ill see you in the next one", "ill see you in the next video"
                }
                
                # Relaxed adaptive filtering: only reject genuine silence/high-probability noise
                is_silence = False
                reason = ""
                if no_speech_prob > 0.95:
                    is_silence = True
                    reason = f"no_speech_prob={no_speech_prob:.4f} > 0.95 (genuine silence)"
                
                if is_silence:
                    logger.info("[STT] Segment discarded: %s", reason)
                    rejected_reasons.append((seg.text, reason))
                elif cleaned in ignored_segments:
                    reason = "matches common hallucinated phrase list"
                    logger.info("[STT] Segment discarded: %s", reason)
                    rejected_reasons.append((seg.text, reason))
                else:
                    text_segments.append(seg.text)
                    
            full_text = " ".join(text_segments).strip()
            full_text = _clean_transcript(full_text)
            logger.info("[STT] Final combined transcript: '%s'", full_text)
            if rejected_reasons:
                logger.info("[STT] Rejected segments log: %s", rejected_reasons)
                
            return full_text
        except Exception as e:
            logger.exception("Error during faster-whisper transcription: %s", e)
            return ""

    def transcribe_wake_word(self, audio_path: Path, stop_event=None) -> str:
        """Transcribe short audio specifically for wake-word detection.
        
        Forces language='en' to prevent Whisper from misdetecting
        short clips as Japanese/Chinese/other languages.
        """
        if stop_event is not None and stop_event.is_set():
            return ""

        try:
            self._lazy_load_model()
        except Exception as e:
            logger.warning("Falling back to MockSTT for wake-word: %s", e)
            return MockSTT().transcribe(audio_path)

        if not audio_path.exists():
            return ""

        try:
            logger.debug("[STT] Wake-word transcription (language=en forced, vad_filter=False)...")
            segments, info = self.model.transcribe(
                str(audio_path),
                beam_size=5,
                vad_filter=False,
                temperature=0.0,
                condition_on_previous_text=False,
                language="en",
                initial_prompt="Hello Nova. Hey Nova.",
            )

            text_parts = []
            for seg in segments:
                if stop_event is not None and stop_event.is_set():
                    return ""
                no_speech_prob = getattr(seg, "no_speech_prob", 0.0)
                avg_logprob = getattr(seg, "avg_logprob", 0.0)
                compression_ratio = getattr(seg, "compression_ratio", 0.0)
                duration = seg.end - seg.start
                
                if not isinstance(no_speech_prob, (int, float)):
                    no_speech_prob = 0.0
                if not isinstance(avg_logprob, (int, float)):
                    avg_logprob = 0.0
                if not isinstance(compression_ratio, (int, float)):
                    compression_ratio = 0.0

                logger.info(
                    "[STT] Wake-word segment text='%s', avg_logprob=%0.4f, no_speech_prob=%0.4f, compression_ratio=%0.4f, duration=%0.2fs",
                    seg.text, avg_logprob, no_speech_prob, compression_ratio, duration
                )

                # Only reject very high no-speech segments for wake word
                if no_speech_prob > 0.95:
                    continue
                text_parts.append(seg.text)

            result = " ".join(text_parts).strip()
            result = _clean_transcript(result)
            logger.info("[STT] Wake-word transcript: '%s'", result)
            return result
        except Exception as e:
            logger.error("Error in wake-word transcription: %s", e)
            return ""


def _clean_transcript(text: str) -> str:
    """Trim repeated syllables, deduplicate repeated words/phrases, and remove unwanted trailing Telugu fragments."""
    if not text:
        return ""
    import re
    
    # 1. Deduplicate consecutive repeated words (case-insensitive duplicate check, preserve original casing)
    words = text.strip().split()
    cleaned_words = []
    for w in words:
        if not cleaned_words or w.lower() != cleaned_words[-1].lower():
            cleaned_words.append(w)
    text = " ".join(cleaned_words)

    # 2. Deduplicate consecutive repeated phrase sequences (e.g. "thank you thank you" -> "thank you")
    # Matches up to 3-word repeated sequences
    for n in range(3, 0, -1):
        pattern = r"\b(" + r"\s+".join([r"\w+"] * n) + r")(?:\s+\1\b)+"
        text = re.sub(pattern, r"\1", text, flags=re.IGNORECASE)

    # 3. Strip trailing Telugu words if the transcript started with English words
    # and has mixed content, to avoid appending unwanted Telugu fragments.
    words = text.split()
    if len(words) > 1:
        has_telugu = any(re.search(r"[\u0c00-\u0c7f]", w) for w in words)
        has_english = any(re.search(r"[a-zA-Z]", w) for w in words)
        if has_telugu and has_english:
            while words and re.search(r"[\u0c00-\u0c7f]", words[-1]) and not re.search(r"[a-zA-Z]", words[-1]):
                words.pop()
            text = " ".join(words)

    # 4. Filter common Whisper hallucinations on low/silent audio
    cleaned = "".join(ch for ch in text.lower() if ch.isalnum() or ch.isspace()).strip()
    garbage_phrases = {
        "thank you", "thank you very much", "please subscribe", "subscribed",
        "thanks for watching", "bye bye", "bye", "you", "oh", "so", "and yeah"
    }
    if cleaned in garbage_phrases:
        return ""

    return text.strip()


class MockSTT(SpeechToTextEngine):
    """Mock Speech-To-Text engine for tests and offline fallback without downloading model binary weights."""

    def __init__(self, predefined_response: str = "hello") -> None:
        self.predefined_response = predefined_response

    def transcribe(self, audio_path: Path, stop_event=None) -> str:
        logger.info("[MockSTT] Transcribing %s -> '%s'", audio_path, self.predefined_response)
        return self.predefined_response
