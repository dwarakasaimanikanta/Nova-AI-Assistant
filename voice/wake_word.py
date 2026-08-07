import difflib
from pathlib import Path
from utils.logger import get_logger
from voice.speech_to_text import SpeechToTextEngine

logger = get_logger(__name__)


class WakeWordDetector:
    """Detects the wake word ('Hey Nova') in an audio file using Speech-to-Text."""

    def __init__(self, stt_engine: SpeechToTextEngine, wake_word: str = "hey nova") -> None:
        self.stt_engine = stt_engine
        self.wake_word = wake_word.strip().lower()

    def _is_nova_match(self, word: str, len_words: int) -> bool:
        """
        Check if a word is a close variation or homophone of 'nova'.
        
        Justification:
        During low-volume, distant speech, or background noise conditions,
        Whisper often returns phonetical homophones or hallucinations like "hello",
        "penoa", "tenoa", "noa", "nona", "noba", "noah" instead of "nova".
        Accepting these variations ensures a reliable wake word detection.
        """
        word = word.strip().lower()
        if word == "hello":
            # Only match "hello" as a wake word variant if it is spoken in isolation
            # to prevent false triggering on longer conversational sentences.
            return len_words <= 2

        common_variants = {
            "nova",
            "novaa",
            "nover",
            "novah",
            "noba",
            "noah",
            "noa",
            "tenoa",
            "penoa",
            "nona",
            "novas",
            "seno",
            "senowa"
        }
        if word in common_variants:
            return True

        # Fuzzy matching using standard library difflib.SequenceMatcher
        ratio = difflib.SequenceMatcher(None, word, "nova").ratio()
        return ratio >= 0.80

    def detect(self, audio_path: Path, stop_event=None) -> bool:
        """
        Transcribes the audio file and checks if the wake word is present.
        """
        if stop_event is not None and stop_event.is_set():
            return False

        logger.info("[WakeWord] Audio received for detection: %s (exists=%s)", audio_path, audio_path.exists())
        try:
            transcript = self.stt_engine.transcribe(audio_path, stop_event=stop_event).strip()
            
            # Clean punctuation and normalize casing
            normalized_transcript = "".join(ch for ch in transcript.lower() if ch.isalnum() or ch.isspace()).strip()
            
            print(f"Raw transcript:\n\"{transcript}\"\n")
            print(f"Normalized:\n\"{normalized_transcript}\"\n")
            
            if not normalized_transcript:
                print("Similarity with nova:\n0%\n")
                logger.info("Empty transcript. Wake word rejected.")
                return False

            words = normalized_transcript.split()
            if not words:
                print("Similarity with nova:\n0%\n")
                logger.info("Empty words list. Wake word rejected.")
                return False

            target = "nova"
            common_variants = {
                "nova", "novaa", "nover", "novah", "noba", "noah", "noa", 
                "tenoa", "penoa", "nona", "novas", "seno", "senowa", 
                "hannover", "rosa", "senova"
            }

            # Helper to get similarity ratio with 'nova'
            def get_similarity(w: str) -> float:
                import difflib
                return difflib.SequenceMatcher(None, w, target).ratio()

            last_word = words[-1]
            similarity_last = get_similarity(last_word)
            
            # If the last word matches any common variants directly, or has ratio >= 80%
            matched = False
            matched_word = ""
            score = similarity_last

            if last_word in common_variants:
                matched = True
                matched_word = last_word
                score = max(score, 0.84) # Force at least 84% for known variants
            elif similarity_last >= 0.80:
                matched = True
                matched_word = last_word

            # If last word didn't match directly, check if combined adjacent words or no-spaces suffix matches
            if not matched:
                no_spaces = "".join(words)
                if no_spaces.endswith(target):
                    matched = True
                    matched_word = target
                    score = 1.0
                else:
                    for v in common_variants:
                        if no_spaces.endswith(v) or v in words:
                            matched = True
                            matched_word = v
                            score = max(score, 0.84)
                            break

            similarity_pct = int(score * 100)
            print(f"Similarity with nova:\n{similarity_pct}%\n")
            
            if matched:
                print("Wake word accepted.")
                logger.info("[WakeWord] Matched word '%s' (similarity: %d%%). Wake word accepted.", matched_word, similarity_pct)
                return True
            else:
                print("Wake word rejected.")
                logger.info("[WakeWord] Similarity: %d%%. Wake word rejected.", similarity_pct)
                return False

        except Exception as e:
            logger.error("Error in wake word detection: %s", e)
            
        return False
