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

# Multi-word phrases Whisper commonly returns instead of "Hey Nova"
_PHRASE_MATCHES = {
    "hey nova", "hi nova", "ok nova", "okay nova",
    "hey noa", "hey noah", "hey noba", "hey over",
}


class WakeWordDetector:
    """Detects the wake word ('Hey Nova') in an audio file using Speech-to-Text."""

    def __init__(self, stt_engine: SpeechToTextEngine, wake_word: str = "hey nova") -> None:
        self.stt_engine = stt_engine
        self.wake_word = wake_word.strip().lower()

    def detect(self, audio_path: Path, stop_event=None) -> bool:
        """
        Transcribes the audio file (with language=en forced) and checks
        if the wake word is present.
        """
        if stop_event is not None and stop_event.is_set():
            return False

        logger.info("[WakeWord] Audio received for detection: %s (exists=%s)", audio_path, audio_path.exists())
        try:
            if stop_event is not None and stop_event.is_set():
                return False
                
            # Use wake-word-specific transcription (forces language=en)
            if hasattr(self.stt_engine, "transcribe_wake_word"):
                transcript = self.stt_engine.transcribe_wake_word(audio_path, stop_event=stop_event).strip()
            else:
                transcript = self.stt_engine.transcribe(audio_path, stop_event=stop_event).strip()

            if stop_event is not None and stop_event.is_set():
                return False

            # Normalize: lowercase, strip punctuation, collapse whitespace
            normalized = "".join(ch for ch in transcript.lower() if ch.isalnum() or ch.isspace()).strip()
            normalized = " ".join(normalized.split())  # collapse multiple spaces

            # ---------------------------------------------------------
            # Wake-Word Attempt Diagnostics Collection
            # ---------------------------------------------------------
            import wave
            import numpy as np

            device_name = "unknown"
            sample_rate = 16000
            channels = 1
            duration = 0.0
            frame_count = 0
            rms = 0.0
            peak = 0.0
            has_speech = False
            wav_size = 0

            if audio_path.exists():
                wav_size = audio_path.stat().st_size
                try:
                    with wave.open(str(audio_path), "rb") as wf:
                        channels = wf.getnchannels()
                        sample_rate = wf.getframerate()
                        frame_count = wf.getnframes()
                        duration = frame_count / sample_rate
                        frames = wf.readframes(frame_count)
                        audio_data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767.0
                        if len(audio_data) > 0:
                            peak = float(np.max(np.abs(audio_data)))
                            rms = float(np.sqrt(np.mean(audio_data**2)))
                            has_speech = peak > 0.0080
                except Exception as wav_err:
                    logger.error("Error reading WAV for diagnostics: %s", wav_err)

            try:
                import sounddevice as sd
                device_idx = sd.default.device[0]
                if device_idx is not None and device_idx >= 0:
                    dev_info = sd.query_devices(device_idx)
                    device_name = f"{device_idx}: {dev_info.get('name', 'unknown')}"
            except Exception:
                pass

            model_name = "unknown"
            if hasattr(self.stt_engine, "wake_model") and self.stt_engine.wake_model is not None:
                model_name = "tiny.en"
            elif hasattr(self.stt_engine, "model_size"):
                model_name = self.stt_engine.model_size

            logger.info(
                "[DIAGNOSTICS] Wake-Word Attempt:\n"
                "- input device: %s\n"
                "- sample rate: %d Hz\n"
                "- channels: %d\n"
                "- recorded duration: %.2f seconds\n"
                "- frame count: %d\n"
                "- RMS: %.6f\n"
                "- peak amplitude: %.6f\n"
                "- non-silent: %s\n"
                "- WAV size: %d bytes\n"
                "- Whisper model: %s\n"
                "- Whisper language parameter: en\n"
                "- VAD setting: False\n"
                "- resulting transcript: %r",
                device_name, sample_rate, channels, duration, frame_count, rms, peak, has_speech, wav_size, model_name, transcript
            )
            # ---------------------------------------------------------

            print(f'Raw transcript:\n"{transcript}"\n')
            print(f'Normalized:\n"{normalized}"\n')

            if not normalized:
                print("Similarity with nova:\n0%\n")
                logger.info("[WAKE] Empty transcript. Rejected.")
                return False

            # Strict wake-word matching check
            # Accepted target phrases:
            accepted_targets = {
                "hey nova", "hey no va", "hey novah", "hey noa", "hey noah", 
                "hey noba", "hey over", "hey novaa", "okay nova", "ok nova",
                "just nova", "nover", "novah", "no va", "tenoa"
            }
            
            # Reject targets specifically:
            rejected_targets = {
                "hello nova", "hello", "hey", "nova", "good morning nova", "hi nova", "hello over"
            }

            # Interruption keywords during active speech output playback
            from voice.audio_recorder import AudioRecorder
            if AudioRecorder.playback_active.is_set():
                # Echo check: if the transcript matches what Nova is currently speaking, it is echo.
                from voice.speech_controller import SpeechController
                if SpeechController._instance is not None:
                    active_tts = getattr(SpeechController._instance, "currently_speaking_text", "")
                    if active_tts:
                        import re as _re
                        t_words = [w for w in _re.sub(r'[^\w\s]', '', normalized).split() if len(w) > 1]
                        tts_words = set(w for w in _re.sub(r'[^\w\s]', '', active_tts.lower()).split() if len(w) > 1)
                        
                        # Do not reject actual stop/interrupt keywords if they were not part of the active TTS
                        interrupt_keywords = {"stop", "cancel", "wait", "enough", "chalu", "aapu", "stop speaking"}
                        has_interrupt = any(w in normalized for w in interrupt_keywords) and not any(w in active_tts.lower() for w in interrupt_keywords)
                        
                        if not has_interrupt and t_words:
                            matches = sum(1 for w in t_words if w in tts_words)
                            match_ratio = matches / len(t_words)
                            if match_ratio >= 0.50 or normalized in active_tts.lower():
                                logger.info("[WAKE] Rejecting wake word transcript %r as echo of active TTS: %r", normalized, active_tts)
                                print("Similarity with nova:\n0%\n")
                                print("Wake word rejected.")
                                return False
                
                interrupt_keywords = {"stop", "cancel", "wait", "enough", "chalu", "aapu", "stop speaking"}
                if any(w in normalized for w in interrupt_keywords):
                    print("Similarity with nova:\n100%\n")
                    print("Wake word accepted.")
                    logger.info("[WAKE] Interruption matched during active playback.")
                    return True

            # Match accepted target
            matched = False
            for target in accepted_targets:
                if target in normalized:
                    matched = True
                    break
                    
            # Explicit negation/rejection check
            for reject in rejected_targets:
                if normalized == reject or (reject in normalized and not any(acc in normalized for acc in accepted_targets)):
                    matched = False
                    break

            if matched:
                if stop_event is not None and stop_event.is_set():
                    return False
                print("Similarity with nova:\n100%\n")
                print("Wake word accepted.")
                logger.info("[WakeWord] Strict match accepted: %r", normalized)
                return True

            if stop_event is not None and stop_event.is_set():
                return False
            print("Similarity with nova:\n0%\n")
            print("Wake word rejected.")
            logger.info("[WAKE] Rejecting transcript '%s' as it does not match accepted wake words.", normalized)
            return False

        except Exception as e:
            logger.error("Error in wake word detection: %s", e)

        return False
