import difflib
from pathlib import Path
from utils.logger import get_logger
from voice.speech_to_text import SpeechToTextEngine

logger = get_logger(__name__)


# Direct-match variants: if ANY word in the transcript matches one of these,
# the wake word is accepted immediately (no fuzzy needed).
# NOTE: Only words that are phonetically close to "nova" AND unlikely to appear
# in normal conversation. "over", "newer", "rosa" removed to prevent false positives.
_EXACT_VARIANTS = {
    "nova", "novaa", "nover", "novah", "noba", "noah", "noa",
    "tenoa", "penoa", "nona", "novas", "seno", "senowa",
    "senova", "ova", "nava", "nobo", "novo", "nuova",
}

# Multi-word phrases Whisper commonly returns instead of "Hello Nova"
_PHRASE_MATCHES = {
    "10 over", "ten over", "hello nova", "hey nova", "hi nova",
    "hello over", "hallo nova", "halo nova", "nova assistant",
    "hello noa", "hello noah", "hey noa", "hey noah",
    "hello noba", "hey noba", "hello over", "hey over",
}


class WakeWordDetector:
    """Detects the wake word ('Hey Nova') in an audio file using Speech-to-Text."""

    def __init__(self, stt_engine: SpeechToTextEngine, wake_word: str = "hey nova") -> None:
        self.stt_engine = stt_engine
        self.wake_word = wake_word.strip().lower()

    def detect(self, audio_path: Path, stop_event=None) -> bool:
        """
        Transcribes the audio file (with language=en forced) and checks
        if the wake word is present using fuzzy matching.
        """
        if stop_event is not None and stop_event.is_set():
            return False

        logger.info("[WakeWord] Audio received for detection: %s (exists=%s)", audio_path, audio_path.exists())
        try:
            # Use wake-word-specific transcription (forces language=en)
            if hasattr(self.stt_engine, "transcribe_wake_word"):
                transcript = self.stt_engine.transcribe_wake_word(audio_path, stop_event=stop_event).strip()
            else:
                transcript = self.stt_engine.transcribe(audio_path, stop_event=stop_event).strip()

            # Normalize: lowercase, strip punctuation, collapse whitespace
            normalized = "".join(ch for ch in transcript.lower() if ch.isalnum() or ch.isspace()).strip()
            normalized = " ".join(normalized.split())  # collapse multiple spaces

            print(f'Raw transcript:\n"{transcript}"\n')
            print(f'Normalized:\n"{normalized}"\n')

            if not normalized:
                print("Similarity with nova:\n0%\n")
                logger.info("[WAKE] Empty transcript. Rejected.")
                return False

            # Guard: a wake word utterance is always short (1-4 words).
            # If Whisper returns a long sentence, it's conversation, not a wake word.
            words = normalized.split()
            
            # Interruption keywords during active speech output playback
            from voice.audio_recorder import AudioRecorder
            if AudioRecorder.playback_active.is_set():
                interrupt_keywords = {"stop", "cancel", "wait", "enough", "chalu", "aapu"}
                for word in words:
                    if word in interrupt_keywords:
                        print("Similarity with nova:\n100%\n")
                        print("Wake word accepted.")
                        logger.info("[WAKE] Interruption keyword '%s' matched during active playback.", word)
                        return True
            
            if len(words) > 4:
                print(f"Similarity with nova:\n0%\n")
                print("Wake word rejected.")
                logger.info("[WAKE] Transcript too long (%d words). Rejected as false positive.", len(words))
                return False

            # Accept ONLY: Nova, Hey Nova, Hello Nova, Hi Nova
            accepted_phrases = {"nova", "hey nova", "hello nova", "hi nova"}
            if normalized in accepted_phrases:
                print("Similarity with nova:\n100%\n")
                print("Wake word accepted.")
                logger.info("[WakeWord] Exact match '%s'. Wake word accepted.", normalized)
                return True

            print("Similarity with nova:\n0%\n")
            print("Wake word rejected.")
            logger.info("[WAKE] Rejecting transcript '%s' as it does not match accepted wake words.", normalized)
            return False

        except Exception as e:
            logger.error("Error in wake word detection: %s", e)

        return False
