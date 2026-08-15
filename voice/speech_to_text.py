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
    def transcribe(self, audio_path: Path, stop_event=None, multilingual: bool = False, for_language_selection: bool = False) -> str:
        """Transcribe audio from file path and return text."""
        pass


class FasterWhisperSTT(SpeechToTextEngine):
    """Speech-to-text using faster-whisper model."""

    def __init__(self, model_size: str = "small", device: str = "cpu") -> None:
        import threading
        self.model_size = model_size
        self.device = device
        self.model = None
        self.wake_model = None
        self.multilingual_model = None
        self._load_lock = threading.Lock()
        # Event set when the model is fully loaded and warmed up
        self._model_ready_event = threading.Event()
        self._lazy_load_started = False

        # Background load model on startup if not under testing
        import os
        if os.getenv("ENVIRONMENT") != "test":
            logger.info("[STT] Warming up STT and Wake-word models in background...")
            self._lazy_load_started = True
            threading.Thread(target=self._lazy_load_model, daemon=True, name="STTBackgroundInitThread").start()

    def _lazy_load_model(self) -> None:
        # Fast path: if both are already loaded, mark ready and return
        if self.model is not None and self.wake_model is not None:
            self._model_ready_event.set()
            return
        with self._load_lock:
            # Re-check inside lock to handle concurrent initialization
            if self.model is not None and self.wake_model is not None:
                self._model_ready_event.set()
                return

            try:
                from faster_whisper import WhisperModel
                import tempfile, wave, struct

                # 1. Load lightweight wake-word model 'tiny.en' for fast hot-word detection
                logger.info("[STT] Initializing wake-word model 'tiny.en' on %s...", self.device)
                self.wake_model = WhisperModel(
                    "tiny.en",
                    device=self.device,
                    compute_type="int8",
                    cpu_threads=2,
                    num_workers=1,
                )
                logger.info("[STT] Wake-word model loaded. Running warm-up inference...")
                try:
                    tmp = Path(tempfile.gettempdir()) / "nova_warmup_wake.wav"
                    with wave.open(str(tmp), "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(16000)
                        wf.writeframes(struct.pack("<" + "h" * 8000, *([0] * 8000)))
                    list(self.wake_model.transcribe(str(tmp), beam_size=1, language="en", vad_filter=True)[0])
                    try:
                        tmp.unlink()
                    except Exception:
                        pass
                    logger.info("[STT] Wake-word model warm-up complete.")
                except Exception as warm_err:
                    logger.warning("[STT] Wake-word model warm-up skipped: %s", warm_err)

                # 2. Load main command model
                # NOTE: model_size should default to 'base' (multilingual) per config.py.
                # 'base.en' must NOT be used as it cannot decode Telugu/Hindi/Tamil/Kannada.
                is_english_only = self.model_size.lower().endswith(".en") or self.model_size.lower() == "tiny.en"
                # For multilingual models, warm up with language=None (auto) to avoid language mismatch.
                warmup_lang = "en" if is_english_only else None

                logger.info("[STT] Initializing main command model '%s' on %s (multilingual=%s)...",
                            self.model_size, self.device, not is_english_only)
                self.model = WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type="int8",
                    cpu_threads=2,
                    num_workers=1,
                )
                # If the main model is multilingual, assign it as the multilingual_model immediately.
                # This ensures language-selection calls do NOT need to lazy-load a separate model.
                if not is_english_only:
                    self.multilingual_model = self.model
                    logger.info("[STT] Main model '%s' is multilingual — set as multilingual_model.", self.model_size)

                logger.info("[STT] Main model '%s' loaded. Running warm-up inference...", self.model_size)
                try:
                    tmp = Path(tempfile.gettempdir()) / "nova_warmup_main.wav"
                    with wave.open(str(tmp), "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(16000)
                        wf.writeframes(struct.pack("<" + "h" * 8000, *([0] * 8000)))
                    list(self.model.transcribe(str(tmp), beam_size=1, language=warmup_lang, vad_filter=True)[0])
                    try:
                        tmp.unlink()
                    except Exception:
                        pass
                    logger.info("[STT] READY — main model warm-up complete.")
                except Exception as warm_err:
                    logger.warning("[STT] Main model warm-up failed (non-fatal): %s", warm_err)
                    logger.info("[STT] READY — main model loaded (warm-up skipped).")

            except Exception as e:
                logger.error("[STT] Failed to load STT models: %s", e)
                self._model_ready_event.set()  # Unblock waiters even on failure
                raise
            finally:
                self._model_ready_event.set()

    def transcribe(self, audio_path: Path, stop_event=None, multilingual: bool = False, for_language_selection: bool = False) -> str:
        if stop_event is not None and stop_event.is_set():
            logger.info("Transcription aborted due to stop_event.")
            return ""

        logger.info("[STT] Audio file received: %s (exists=%s)", audio_path, audio_path.exists())
        logger.info("[VOICE-DEBUG] STT started on file: %s", audio_path)

        # 1. Resolve which model to use
        if multilingual:
            if not getattr(self, "multilingual_model", None) or self.multilingual_model is None:
                from config import NOVA_MULTILINGUAL_MODEL
                multilingual_model_sz = NOVA_MULTILINGUAL_MODEL or "base"
                logger.info("[STT] Loading multilingual Whisper model '%s' on %s...", multilingual_model_sz, self.device)
                from faster_whisper import WhisperModel
                try:
                    self.multilingual_model = WhisperModel(
                        multilingual_model_sz,
                        device=self.device,
                        compute_type="int8",
                        cpu_threads=2,
                        num_workers=1,
                    )
                except Exception as e:
                    logger.error("Failed to load multilingual model '%s': %s. Falling back to main model.", multilingual_model_sz, e)
                    self.multilingual_model = self.model
            model_to_use = self.multilingual_model
        else:
            model_to_use = self.model

        # 2. Wait for main model if it's the one we are using and it's not ready
        if model_to_use is None:
            if not getattr(self, "_model_ready_event", None):
                try:
                    self._lazy_load_model()
                except Exception as e:
                    logger.warning("Falling back to MockSTT due to model load failure: %s", e)
                    return MockSTT().transcribe(audio_path)
            else:
                if not getattr(self, "_lazy_load_started", False):
                    import threading
                    self._lazy_load_started = True
                    threading.Thread(target=self._lazy_load_model, daemon=True, name="STTBackgroundInitThread").start()
                logger.info("[STT] Waiting for background model warm-up...")
                ready = self._model_ready_event.wait(timeout=90.0)
            
            # Re-resolve after waiting
            if multilingual:
                if not getattr(self, "multilingual_model", None) or self.multilingual_model is None:
                    from config import NOVA_MULTILINGUAL_MODEL
                    multilingual_model_sz = NOVA_MULTILINGUAL_MODEL or "base"
                    logger.info("[STT] Loading multilingual Whisper model '%s' on %s...", multilingual_model_sz, self.device)
                    from faster_whisper import WhisperModel
                    try:
                        self.multilingual_model = WhisperModel(
                            multilingual_model_sz,
                            device=self.device,
                            compute_type="int8",
                            cpu_threads=2,
                            num_workers=1,
                        )
                    except Exception as e:
                        logger.error("Failed loading multilingual model: %s", e)
                        self.multilingual_model = self.model
                model_to_use = self.multilingual_model
            else:
                model_to_use = self.model

            if model_to_use is None:
                logger.warning("[STT] Model not ready. Falling back to MockSTT.")
                return MockSTT().transcribe(audio_path)

        # Ensure we are using a true multilingual model if multilingual is requested
        if multilingual:
            model_sz = "base"
            from config import NOVA_MULTILINGUAL_MODEL
            if NOVA_MULTILINGUAL_MODEL:
                model_sz = NOVA_MULTILINGUAL_MODEL
            
            current_model_name = getattr(self, "model_size", "")
            if model_to_use == self.model and (current_model_name.endswith(".en") or current_model_name == "tiny.en"):
                if not self.multilingual_model:
                    logger.info("[STT] Main model '%s' is English-only. Loading true multilingual model '%s'...", current_model_name, model_sz)
                    from faster_whisper import WhisperModel
                    try:
                        self.multilingual_model = WhisperModel(
                            model_sz,
                            device=self.device,
                            compute_type="int8",
                            cpu_threads=2,
                            num_workers=1,
                        )
                    except Exception as e:
                        logger.error("[STT] Failed to load multilingual model: %s", e)
                        self.multilingual_model = self.model
                model_to_use = self.multilingual_model

        # Log details about the STT model used
        active_model_name = "unknown"
        if model_to_use == self.model:
            active_model_name = getattr(self, "model_size", "unknown")
        elif model_to_use == self.multilingual_model:
            from config import NOVA_MULTILINGUAL_MODEL
            active_model_name = NOVA_MULTILINGUAL_MODEL or "base"
            
        is_active_multilingual = not (active_model_name.endswith(".en") or active_model_name == "tiny.en")
        logger.info("[STT] STT Model: %s | Multilingual: %s", active_model_name, is_active_multilingual)

        if not audio_path.exists():
            logger.error("Audio file does not exist: %s", audio_path)
            return ""

        if stop_event is not None and stop_event.is_set():
            logger.info("Transcription aborted due to stop_event.")
            return ""

        # Determine language parameter
        from core.language_session import LanguageSession
        session_lang = LanguageSession().selected_language

        if for_language_selection:
            whisper_lang = None
            initial_prompt = "English, Telugu, Hindi, Tamil, Kannada. Speak in English. English lo matladu. Telugu lo matladu. Hindi me bolo."
        else:
            if session_lang and session_lang != "en":
                whisper_lang = session_lang
                if session_lang == "te":
                    initial_prompt = "హే నోవా. క్రోమ్ ఓపెన్ చెయ్యి. సమయం ఎంత? ఒక వెబ్‌సైట్‌ను సృష్టించండి."
                elif session_lang == "hi":
                    initial_prompt = "हे नोवा। क्रोम खोलो। समय क्या हुआ है? एक वेबसाइट बनाओ।"
                elif session_lang == "ta":
                    initial_prompt = "ஹே நோவா. குரோம் திறக்கவும். மணி என்ன? ஒரு வலைத்தளத்தை உருவாக்கவும்."
                elif session_lang == "kn":
                    initial_prompt = "ಹೇ ನೋವಾ. ಕ್ರೋಮ್ ತೆರೆಯಿರಿ. ಸಮಯ ಎಷ್ಟಾಗಿದೆ? ಒಂದು ವೆಬ್‌ಸೈಟ್ ರಚಿಸಿ."
                else:
                    initial_prompt = "Hey Nova. Open Chrome."
            else:
                whisper_lang = "en"
                initial_prompt = "Hey Nova. Open Chrome. What time is it? Create a website."

        try:
            beam_sz = 5 if for_language_selection else 1
            logger.info("[STT] Transcribing (beam=%d, vad=True, lang=%s)...", beam_sz, whisper_lang or "auto")
            segments, info = model_to_use.transcribe(
                str(audio_path),
                beam_size=beam_sz,
                vad_filter=True,
                temperature=0.0,
                condition_on_previous_text=False,
                language=whisper_lang,
                initial_prompt=initial_prompt,
            )
            detected_lang = getattr(info, "language", "unknown")
            detected_prob = getattr(info, "language_probability", 0.0)
            
            # Cache metadata for hardware log auditing
            self.last_detected_language = detected_lang
            self.last_language_probability = detected_prob
            
            logger.info("[STT] Detected language: '%s' (probability=%.2f)", detected_lang, detected_prob)
            
            if for_language_selection:
                logger.info("[LANGUAGE_SELECTION] detected language='%s'", detected_lang)

            logger.info("[STT]")
            logger.info("Detected input language: %s", detected_lang)
            
            # Consume the segments generator while checking stop_event for cancellation
            segments_list = []
            for seg in segments:
                # Check BEFORE appending so cancellation from inside the generator is respected
                if stop_event is not None and stop_event.is_set():
                    logger.info("[STT] Transcription cancelled mid-generation.")
                    return ""
                segments_list.append(seg)
                # Also check AFTER append for cancellations that happen post-yield
                if stop_event is not None and stop_event.is_set():
                    logger.info("[STT] Transcription cancelled after segment yield.")
                    return ""
            
            text_segments = []
            rejected_reasons = []
            
            for seg in segments_list:
                val_no_speech = getattr(seg, "no_speech_prob", 0.0)
                no_speech_prob = float(val_no_speech) if isinstance(val_no_speech, (int, float)) else 0.0

                val_avg = getattr(seg, "avg_logprob", 0.0)
                avg_logprob = float(val_avg) if isinstance(val_avg, (int, float)) else 0.0

                val_comp = getattr(seg, "compression_ratio", 0.0)
                compression_ratio = float(val_comp) if isinstance(val_comp, (int, float)) else 0.0

                start_val = getattr(seg, "start", 0.0)
                end_val = getattr(seg, "end", 0.0)
                if isinstance(start_val, (int, float)) and isinstance(end_val, (int, float)):
                    duration = float(end_val - start_val)
                else:
                    duration = 1.0

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

                if for_language_selection:
                    # Lenient transcription: never reject any segment for language selection, let keyword matching handle it
                    is_rejected = False
                    reason = ""
                    
                    logger.info(
                        "[LANGUAGE_SELECTION_SEGMENT] text=%r, start=%0.2fs, end=%0.2fs, duration=%0.2fs, avg_logprob=%0.4f, no_speech_prob=%0.4f, detected_language=%r, rejected=%s, reason=%r",
                        seg.text, start_val, end_val, duration, avg_logprob, no_speech_prob, detected_lang, is_rejected, reason
                    )
                    text_segments.append(seg.text)
                else:
                    # Strict adaptive filtering: reject silence, low confidence, and hallucinations
                    is_silence = False
                    reason = ""
                    seg_text_clean = "".join(ch for ch in seg.text.lower() if ch.isalnum() or ch.isspace()).strip()

                    # Detect common Whisper date/time hallucination patterns
                    import re as _re
                    _date_words = (
                        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
                        "january", "february", "march", "april", "may", "june", "july",
                        "august", "september", "october", "november", "december",
                    )
                    _year_pat = _re.compile(r"\b(19|20)\d{2}\b")
                    _time_pat = _re.compile(r"\b([01]?[0-9]|2[0-3]):[0-5][0-9]\s*(am|pm)?\b", _re.IGNORECASE)
                    _words_in_seg = seg_text_clean.split()
                    _has_date_word = any(w in _date_words for w in _words_in_seg)
                    _has_year = bool(_year_pat.search(seg_text_clean))
                    _is_date_halluc = (_has_date_word or _has_year) and len(_words_in_seg) >= 3
                    _is_time_halluc = bool(_time_pat.search(seg.text)) and no_speech_prob > 0.3

                    if no_speech_prob > 0.65:
                        is_silence = True
                        reason = f"no_speech_prob={no_speech_prob:.4f} > 0.65 (silence)"
                    elif avg_logprob < -1.1:
                        is_silence = True
                        reason = f"avg_logprob={avg_logprob:.4f} < -1.1 (low confidence)"
                    elif compression_ratio > 2.2:
                        is_silence = True
                        reason = f"compression_ratio={compression_ratio:.4f} > 2.2 (hallucination)"
                    elif _is_date_halluc:
                        is_silence = True
                        reason = f"date/time hallucination detected: {seg_text_clean!r}"
                    elif _is_time_halluc:
                        is_silence = True
                        reason = f"time hallucination detected: {seg.text!r}"
                    elif duration < 0.3 and len(_words_in_seg) > 8:
                        is_silence = True
                        reason = f"implausible: {duration:.2f}s audio with {len(_words_in_seg)} words"

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
            logger.info("[VOICE-DEBUG] STT result: %r", full_text)
            if not full_text:
                logger.info("[VOICE-DEBUG] STT result was empty. Rejected segments: %s", rejected_reasons)
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

        # Use self.wake_model if available, fallback to self.model
        model_to_use = self.wake_model if self.wake_model is not None else self.model

        if not getattr(self, "_model_ready_event", None):
            try:
                self._lazy_load_model()
                model_to_use = self.wake_model if self.wake_model is not None else self.model
            except Exception as e:
                logger.warning("Falling back to MockSTT for wake-word: %s", e)
                return MockSTT().transcribe(audio_path)
        elif model_to_use is None:
            logger.info("[STT] Wake-word waiting for background model warm-up...")
            ready = self._model_ready_event.wait(timeout=20.0)
            model_to_use = self.wake_model if self.wake_model is not None else self.model
            if not ready or model_to_use is None:
                logger.warning("[STT] Model not ready after 20s timeout. Falling back to MockSTT.")
                return MockSTT().transcribe(audio_path)

        if not audio_path.exists():
            return ""

        try:
            logger.debug("[STT] Wake-word transcription (language=en forced, vad_filter=False)...")
            segments, info = model_to_use.transcribe(
                str(audio_path),
                beam_size=3,
                vad_filter=False,
                temperature=0.0,
                condition_on_previous_text=False,
                language="en",
                initial_prompt="Hey Nova. Nova.",
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
    
    # Global sentence/clause-level deduplicator to prevent repeated overlapping segments (e.g. "What time is it? Yes. What time is it?")
    parts = [p.strip() for p in re.split(r'(?<=[.?!,])\s+', text) if p.strip()]
    if parts:
        cleaned_parts = ["".join(ch for ch in p.lower() if ch.isalnum()).strip() for p in parts]
        to_keep = [True] * len(parts)
        for i in range(len(parts)):
            if not to_keep[i]:
                continue
            for j in range(i + 1, len(parts)):
                if not to_keep[j]:
                    continue
                ci = cleaned_parts[i]
                cj = cleaned_parts[j]
                if ci == cj or (len(ci) > 8 and (ci in cj or cj in ci)):
                    to_keep[j] = False
                    # Check if everything in between i and j is short/filler
                    middle_ok = True
                    for k in range(i + 1, j):
                        ck = cleaned_parts[k]
                        if len(ck) > 6 or ck not in ("yes", "no", "ok", "okay", "yeah", "oh", "ah", "uh", "um", "so", "and", "then"):
                            middle_ok = False
                            break
                    if middle_ok:
                        for k in range(i + 1, j):
                            to_keep[k] = False
        text = " ".join(parts[idx] for idx, keep in enumerate(to_keep) if keep)

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

    def transcribe(self, audio_path: Path, stop_event=None, multilingual: bool = False, for_language_selection: bool = False) -> str:
        logger.info("[MockSTT] Transcribing %s -> '%s'", audio_path, self.predefined_response)
        return self.predefined_response
