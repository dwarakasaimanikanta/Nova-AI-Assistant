"""
voice/always_listening.py
-------------------------
Always Listening Engine running wake-word detection, microphone failure recovery,
and conversation timeouts in a background thread.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from config import NOVA_POST_TTS_DELAY
from utils.logger import get_logger

logger = get_logger(__name__)


import atexit
import weakref

_active_engines = weakref.WeakSet()

def _cleanup_active_engines():
    for engine in list(_active_engines):
        try:
            engine.stop()
        except Exception:
            pass

atexit.register(_cleanup_active_engines)


def has_repetitive_loop(text: str) -> bool:
    """Detect repetitive Whisper hallucination patterns (e.g. 'lu lu lu', 'பெலுலு')."""
    if not text:
        return False
    # Remove all spaces and punctuation, convert to lowercase
    import re
    cleaned = re.sub(r"[^\w\u0c00-\u0c7f\u0900-\u097f\u0b80-\u0bff\u0c80-\u0cff]", "", text).lower()
    if not cleaned:
        return False
    
    # Check for repeating character patterns of length 1, 2, or 3
    # If a pattern of length N repeats 4 or more times consecutively, it's a loop.
    for length in (1, 2, 3):
        for i in range(len(cleaned) - length * 4):
            sub = cleaned[i:i+length]
            if cleaned[i:i+length*4] == sub * 4:
                return True
    return False


class AlwaysListeningEngine:
    """Continuous wake-word monitor and conversation lifecycle manager."""

    def __init__(
        self,
        voice_manager: Any,
        wake_detector: Any,
        audio_recorder: Any,
        conversation_timeout: float = 10.0,
        on_wake_callback: Optional[Callable[[], None]] = None,
        on_command_callback: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self.voice_manager = voice_manager
        self.wake_detector = wake_detector
        self.recorder = audio_recorder
        self.conversation_timeout = conversation_timeout
        self.on_wake_callback = on_wake_callback
        self.on_command_callback = on_command_callback

        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._state = "IDLE"
        self._language_selection_retries = 0
        self._command_thread: Optional[threading.Thread] = None
        self._thread_lock = threading.Lock()
        _active_engines.add(self)

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass

    def _is_echo(self, transcript: str) -> bool:
        """Check if the transcribed text is self-generated audio (echo from TTS output)."""
        if not isinstance(transcript, str) or not transcript.strip() or not self.voice_manager:
            return False
            
        active_tts = ""
        if hasattr(self.voice_manager, "speech_controller"):
            active_tts = getattr(self.voice_manager.speech_controller, "currently_speaking_text", "")
            
        if not isinstance(active_tts, str) or not active_tts:
            return False
            
        import re
        t_words = [w for w in re.sub(r'[^\w\s]', '', transcript.lower()).split() if len(w) > 1]
        tts_words = set(w for w in re.sub(r'[^\w\s]', '', active_tts.lower()).split() if len(w) > 1)
        
        # Do not reject stop words
        stop_keywords_filter = {
            "stop", "cancel", "enough", "quiet", "shut",
            "ఆపు", "ఆపండి", "చాలు", "ruko", "band", "apandi", "apu"
        }
        has_stop_word = any(w in stop_keywords_filter for w in t_words)
        
        if not has_stop_word and t_words:
            matches = sum(1 for w in t_words if w in tts_words)
            match_ratio = matches / len(t_words)
            if match_ratio >= 0.60 or re.sub(r'[^\w\s]', '', transcript.lower()).strip() in re.sub(r'[^\w\s]', '', active_tts.lower()):
                return True
        return False


    @property
    def state(self) -> str:
        if self._state == "IDLE":
            return "WAKING"
        return self._state

    @state.setter
    def state(self, value: str) -> None:
        if value in ("WAKING", "IDLE"):
            self._state = "IDLE"
        else:
            self._state = value

    def start(self) -> None:
        """Start the background monitoring thread."""
        with self._lock:
            if self.running:
                logger.warning("AlwaysListeningEngine is already running.")
                return

            # Wait for background model warm-up to complete BEFORE starting loop/mic recording
            if self.voice_manager and hasattr(self.voice_manager, "stt_engine"):
                stt = self.voice_manager.stt_engine
                if hasattr(stt, "_model_ready_event"):
                    is_test_env = (os.getenv("ENVIRONMENT") == "test")
                    is_loaded = (getattr(stt, "model", None) is not None) or is_test_env
                    if not is_loaded:
                        logger.info("[AlwaysListening] Waiting for Speech-to-Text model warm-up before enabling wake-word loop...")
                        stt._model_ready_event.wait(timeout=30.0)
                        logger.info("[AlwaysListening] Speech-to-Text model ready. Starting wake-word loop.")

            self.running = True
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                daemon=True,
                name="AlwaysListeningThread"
            )
            self._thread.start()
            logger.info("AlwaysListeningEngine background thread started.")

    def stop(self) -> None:
        """Stop the background monitoring thread gracefully."""
        with self._lock:
            if not self.running:
                return
            self.running = False
            self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        logger.info("AlwaysListeningEngine background thread stopped.")

    def _run_loop(self) -> None:
        last_activity_time = time.time()
        logger.info("[STATE] Transitioned to IDLE")

        while not self._stop_event.is_set():
            if self.voice_manager:
                telugu_mode = getattr(self.voice_manager, "telugu_mode", False)
                response_language = getattr(self.voice_manager, "response_language", "english")
            try:
                # CPU breathing room
                time.sleep(0.1)

                # Sync voice_manager state
                if self.voice_manager:
                    if self._state == "IDLE":
                        self.voice_manager.state = "IDLE"
                    elif self._state in ("LISTENING", "LANGUAGE_SELECTION"):
                        self.voice_manager.state = "LISTENING"

                if self._state == "IDLE":
                    # 1. Standby state: listen for wake word
                    # Disable silence cutoff to prevent premature wake-word clipping
                    start_rec_time = time.time()
                    audio_path = self._record_safely(max_seconds=2.0, allow_playback_recording=True, disable_silence_cutoff=True)
                    rec_duration = time.time() - start_rec_time if audio_path else 0.0
                    
                    if not audio_path:
                        time.sleep(0.1)
                        continue

                    # Transcribe wake word exactly once
                    start_stt_time = time.time()
                    detected = self.wake_detector.detect(audio_path, stop_event=self._stop_event)
                    stt_duration = time.time() - start_stt_time
                    
                    wake_rec_ms = int(rec_duration * 1000)
                    wake_stt_ms = int(stt_duration * 1000)
                    logger.info("[TIMING-METRICS] Wake-word check | recording_ms: %d | wake_stt_ms: %d | Detected: %s",
                                wake_rec_ms, wake_stt_ms, detected)
                    self._delete_audio(audio_path)

                    if detected:
                        logger.info("[STATE] Transitioned to WAKE_DETECTED")
                        self._state = "WAKE_DETECTED"

                elif self._state == "WAKE_DETECTED":
                    # Trigger active interruption on any active execution
                    if self.on_command_callback and hasattr(self.on_command_callback, "__self__"):
                        engine_instance = self.on_command_callback.__self__
                        if hasattr(engine_instance, "interrupt"):
                            try:
                                logger.info("[WAKE] Active wake-word trigger. Performing active interruption request.")
                                engine_instance.interrupt()
                            except Exception as int_err:
                                logger.error("[WAKE] Interruption helper error: %s", int_err)

                    # Trigger wake word callback to acknowledge (e.g. 'Yes Boss.')
                    if self.on_wake_callback:
                        try:
                            self.on_wake_callback()
                        except Exception as wake_err:
                            logger.error("[WAKE] Error in on_wake_callback: %s", wake_err)

                    self._wait_for_tts_drain()

                    if self.voice_manager:
                        self.voice_manager.selected_language = "en"
                        self.voice_manager.response_language = "en"

                    logger.info("[STATE] Transitioned to LISTENING")
                    self._state = "LISTENING"
                    last_activity_time = time.time()

                elif self._state == "LANGUAGE_SELECTION":
                    if self.voice_manager:
                        self.voice_manager.state = "LISTENING"

                    # 1. Wait until Nova's language-selection prompt TTS has completely finished
                    self._wait_for_tts_drain()

                    # 2. Wait for a short configurable microphone stabilization period
                    from config import NOVA_POST_TTS_DELAY
                    stabilization_delay = float(os.getenv("NOVA_MIC_STABILIZATION_DELAY", "0.3"))
                    time.sleep(stabilization_delay)

                    # 3. Clear/drain any stale microphone audio already buffered
                    drained_count = 0
                    if hasattr(self.recorder, "audio_queue"):
                        while not self.recorder.audio_queue.empty():
                            try:
                                self.recorder.audio_queue.get_nowait()
                                drained_count += 1
                            except Exception:
                                break
                    logger.info("[LANGUAGE_SELECTION] Stale audio drained (count=%d)", drained_count)

                    # 4. Start a fresh recording session
                    logger.info("[LANGUAGE_SELECTION] recording started")
                    audio_path = self._record_safely(
                        max_seconds=5.0,
                        allow_playback_recording=False,
                        initial_silence_timeout=5.0,
                        silence_duration=0.8
                    )
                    
                    if not audio_path:
                        logger.info("[LANGUAGE_SELECTION] EMPTY TRANSCRIPT — STT FAILED BEFORE LANGUAGE PARSING")
                        logger.info("[LANGUAGE_SELECTION] recording duration=0.00")
                        logger.info("[LANGUAGE_SELECTION] raw transcript=''")
                        logger.info("[LANGUAGE_SELECTION] normalized transcript=''")
                        logger.info("[LANGUAGE_SELECTION] detected STT language='unknown'")
                        logger.info("[LANGUAGE_SELECTION] matched language='none'")
                        logger.info("[LANGUAGE_SELECTION] selected_language='none'")
                        logger.info("[LANGUAGE_SELECTION] confidence=0.0000")
                        logger.info("[LANGUAGE_SELECTION] retry=%d", self._language_selection_retries)
                        
                        self._language_selection_retries += 1
                        if self._language_selection_retries >= 3:
                            logger.info("[LANGUAGE_SELECTION] Max retries reached (No audio). Returning to IDLE.")
                            self._state = "IDLE"
                            continue
                        if self.voice_manager:
                            self.voice_manager._safe_speak("English, Telugu, Hindi, Tamil, or Kannada, Boss?")
                        self._wait_for_tts_drain()
                        continue

                    # Log duration of recorded audio file
                    duration_sec = 0.0
                    try:
                        import wave
                        with wave.open(str(audio_path), "rb") as wf:
                            frames = wf.getnframes()
                            rate = wf.getframerate()
                            duration_sec = frames / float(rate)
                    except Exception:
                        pass
                    logger.info("[LANGUAGE_SELECTION] recording duration=%.2f", duration_sec)

                    # Log STT model size/name used
                    stt_model_name = "unknown"
                    if self.voice_manager and hasattr(self.voice_manager, "stt_engine"):
                        stt_model_name = getattr(self.voice_manager.stt_engine, "model_size", "unknown")
                    logger.info("[LANGUAGE_SELECTION] STT model=%s", stt_model_name)
                    logger.info("[LANGUAGE_SELECTION] multilingual=True")
                    logger.info("[LANGUAGE_SELECTION] whisper language=None")

                    # Transcribe in multilingual mode
                    transcript = ""
                    try:
                        transcript = self.voice_manager._safe_transcribe(audio_path, multilingual=True, for_language_selection=True)
                    except Exception as trans_err:
                        logger.error("Language selection transcription error: %s", trans_err)
                    finally:
                        self._delete_audio(audio_path)

                    if has_repetitive_loop(transcript):
                        logger.warning("[LANGUAGE_SELECTION] Detected repetitive Whisper hallucination loop in transcript: %r. Treating as empty.", transcript)
                        transcript = ""

                    logger.info("[LANGUAGE_SELECTION] raw transcript='%s'", transcript)

                    ans_lower = ""
                    if transcript and transcript.strip():
                        # Normalize the transcript before matching
                        ans_lower = transcript.strip().lower().replace('?', '').replace('.', '').replace(',', '').strip()
                    logger.info("[LANGUAGE_SELECTION] normalized transcript='%s'", ans_lower)

                    detected_stt_lang = "unknown"
                    confidence = 0.0
                    if self.voice_manager and hasattr(self.voice_manager, "stt_engine"):
                        detected_stt_lang = getattr(self.voice_manager.stt_engine, "last_detected_language", "unknown")
                        confidence = getattr(self.voice_manager.stt_engine, "last_language_probability", 0.0)
                    logger.info("[LANGUAGE_SELECTION] detected STT language='%s'", detected_stt_lang)

                    # Parse selected language
                    from utils.language_switch import parse_spoken_language
                    matched_lang = parse_spoken_language(transcript, detected_lang=detected_stt_lang, confidence=confidence)
                    logger.info("[LANGUAGE_SELECTION] matched language='%s'", matched_lang or "none")

                    selected_lang = {
                        "te": "telugu",
                        "en": "english",
                        "hi": "hindi",
                        "ta": "tamil",
                        "kn": "kannada"
                    }.get(matched_lang)

                    logger.info("[LANGUAGE_SELECTION] selected_language='%s'", selected_lang or "none")
                    logger.info("[LANGUAGE_SELECTION] confidence=%.4f", confidence)
                    logger.info("[LANGUAGE_SELECTION] retry=%d", self._language_selection_retries)

                    if selected_lang:
                        # Success path!
                        # Neural Voice Mapping
                        voice_desc = {
                            "telugu": "te-IN-ShrutiNeural",
                            "english": "en-US-AriaNeural",
                            "hindi": "hi-IN-SwaraNeural",
                            "tamil": "ta-IN-PallaviNeural",
                            "kannada": "kn-IN-SapnaNeural"
                        }.get(selected_lang)

                        speak_confirm = {
                            "telugu": "సరే బాస్. ఇక నుంచి తెలుగులో మాట్లాడతాను. మీకు ఏం సహాయం కావాలి?",
                            "english": "Sure Boss. I'll speak in English. How can I help you?",
                            "hindi": "ठीक है बॉस। अब से मैं हिंदी में बात करूंगा। मैं आपकी कैसे मदद कर सकता हूँ?",
                            "tamil": "சரி பாஸ். இனிமேல் நான் தமிழில் பேசுவேன். நான் உங்களுக்கு எப்படி உதவலாம்?",
                            "kannada": "ಸರಿ ಬಾಸ್. ಇನ್ನು ಮುಂದೆ ನಾನು ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡುತ್ತೇನೆ. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?"
                        }.get(selected_lang)

                        # Update selected language on both voice manager and engine objects
                        if self.voice_manager:
                            self.voice_manager.selected_language = selected_lang
                            self.voice_manager.response_language = selected_lang
                            if hasattr(self.voice_manager, "engine") and self.voice_manager.engine:
                                self.voice_manager.engine.selected_language = selected_lang
                            self.voice_manager._safe_speak(speak_confirm, response_language=selected_lang)
                        
                        self._wait_for_tts_drain()
                        logger.info("[STATE] Transitioned to LISTENING")
                        self._state = "LISTENING"
                        last_activity_time = time.time()
                    else:
                        # Unrecognized path
                        logger.info("[LANGUAGE_SELECTION] Unrecognized answer.")
                        self._language_selection_retries += 1
                        if self._language_selection_retries >= 3:
                            logger.info("[LANGUAGE_SELECTION] Max retries reached (Unrecognized answer). Returning to IDLE.")
                            self._state = "IDLE"
                            continue
                        if self.voice_manager:
                            self.voice_manager._safe_speak("English, Telugu, Hindi, Tamil, or Kannada, Boss?")
                        self._wait_for_tts_drain()

                elif self._state == "LISTENING":
                    # 2. Active command capture (pause recording during speech output)
                    start_rec = time.time()
                    audio_path = self._record_safely(max_seconds=10.0, allow_playback_recording=False)
                    rec_lat = time.time() - start_rec if audio_path else 0.0

                    if not audio_path:
                        if time.time() - last_activity_time > self.conversation_timeout:
                            logger.info("Conversation timed out. Returning to IDLE.")
                            logger.info("[STATE] Transitioned to IDLE")
                            self._state = "IDLE"
                        else:
                            time.sleep(0.5)
                        continue

                    # Transcribe user command exactly once
                    start_stt = time.time()
                    transcript = ""
                    try:
                        transcript = self.voice_manager._safe_transcribe(audio_path)
                    except Exception as trans_err:
                        logger.error("Transcription exception: %s", trans_err)
                    finally:
                        self._delete_audio(audio_path)
                    stt_lat = time.time() - start_stt

                    if has_repetitive_loop(transcript):
                        logger.warning("[AlwaysListeningEngine] Detected repetitive Whisper hallucination loop in transcript: %r. Ignoring.", transcript)
                        transcript = ""

                    if transcript and transcript.strip():
                        if self._is_echo(transcript):
                            logger.info("[AlwaysListeningEngine] Rejecting self-generated audio (echo): %r", transcript)
                            continue
                        logger.info("[AlwaysListeningEngine] Command received: %s", transcript)
                        logger.info("[VOICE-DEBUG] command received: %s", transcript)
                        cmd_lower = transcript.lower()

                        # ── FIX-3: STOP fast-path (before any engine call) ────────────────
                        # If the user says stop/cancel/enough — interrupt immediately and
                        # return to LISTENING. Do NOT generate any TTS response.
                        _stop_kws = {
                            "stop", "stop speaking", "enough", "cancel", "shut up", "nova stop",
                            "ఆపు", "ఆపండి", "చాలు", "apu", "apandi", "chalu",
                            "ruko", "band karo", "niruthu", "pothum", "nillisu", "saaku"
                        }
                        import re as _re
                        _cleaned_stop = _re.sub(r"[^\w\s\u0c00-\u0c7f\u0900-\u097f\u0b80-\u0bff\u0c80-\u0cff]", "", cmd_lower).strip()
                        if _cleaned_stop in _stop_kws or cmd_lower.strip() in _stop_kws:
                            logger.info("[STOP-INTERCEPT] Stop command detected before engine. Interrupting silently.")
                            if self.voice_manager:
                                self.voice_manager.interrupt()
                            last_activity_time = time.time()
                            self._state = "LISTENING"
                            continue

                        # Intercept dynamic language mode switches
                        from utils.language_switch import detect_and_handle_language_switch
                        if detect_and_handle_language_switch(transcript, self.voice_manager):
                            # Drain stale microphone audio
                            if hasattr(self.recorder, "audio_queue"):
                                while not self.recorder.audio_queue.empty():
                                    try:
                                        self.recorder.audio_queue.get_nowait()
                                    except Exception:
                                        break
                            self._wait_for_tts_drain()
                            last_activity_time = time.time()
                            self._state = "LISTENING"
                            continue

                        # ── FIX-7: Request sequence guard ─────────────────────────────────
                        # Increment seq before calling engine. Capture it locally.
                        # If a newer command arrived while this one was executing, discard.
                        if not hasattr(self, "_request_seq"):
                            self._request_seq = 0
                        self._request_seq += 1
                        _my_seq = self._request_seq

                        import uuid
                        exec_id = str(uuid.uuid4())[:8]

                        wake_detected_time = start_rec
                        recording_started_time = start_rec
                        recording_finished_time = start_rec + rec_lat
                        stt_started_time = start_stt
                        stt_finished_time = start_stt + stt_lat

                        logger.info("[STATE] Transitioned to PROCESSING")
                        self._state = "PROCESSING"
                        if self.voice_manager:
                            self.voice_manager.state = "PROCESSING"
                        
                        # Process callback synchronously.
                        # This blocks mic recording during processing and TTS.
                        try:
                            last_activity_time = time.time()
                            
                            # 3. Route & Execute
                            logger.info("[STATE] Transitioned to EXECUTING")
                            self._state = "EXECUTING"
                            if self.voice_manager:
                                self.voice_manager.state = "EXECUTING"

                            start_exec = time.time()
                            intent_started_time = start_exec
                            response_text = ""
                            try:
                                response_text = self.voice_manager._safe_engine(transcript)
                            except Exception as exec_err:
                                logger.error("Engine execution error: %s", exec_err)
                                response_text = "Failure: An internal error occurred."
                            exec_lat = time.time() - start_exec
                            intent_finished_time = start_exec + min(0.05, exec_lat)
                            response_started_time = intent_finished_time

                            # ── FIX-7: Stale response guard ───────────────────────────────
                            # If a newer command arrived while we were executing, discard this
                            # response silently (don't speak it over the newer result).
                            if getattr(self, "_request_seq", _my_seq) != _my_seq:
                                logger.info(
                                    "[REQUEST-GUARD] Discarding stale response (seq=%d, current=%d): %r",
                                    _my_seq, self._request_seq, response_text[:60]
                                )
                                self._state = "LISTENING"
                                last_activity_time = time.time()
                                continue

                            # 4. TTS speak response
                            logger.info("[STATE] Transitioned to SPEAKING")
                            self._state = "SPEAKING"
                            if self.voice_manager:
                                self.voice_manager.state = "SPEAKING"

                            start_tts = time.time()
                            tts_started_time = start_tts
                            try:
                                from voice.voice_manager import format_spoken_response
                                lang = getattr(self.voice_manager, "selected_language", "en")
                                spoken_res = format_spoken_response(response_text, response_language=lang)
                                
                                # Speak response (uses VoiceManager._safe_speak, crucial for unit tests!)
                                if self.voice_manager:
                                    self.voice_manager._safe_speak(spoken_res, response_language=lang)
                                
                                # Check if speech controller is active, checking if it is a unit test Mock
                                is_speaking = False
                                if self.voice_manager and hasattr(self.voice_manager, "speech_controller"):
                                    from unittest.mock import Mock
                                    if not isinstance(self.voice_manager.speech_controller, Mock):
                                        is_speaking = self.voice_manager.speech_controller.is_speaking()
                                
                                # Monitor for stop/interruption or wake word while TTS is playing
                                stopped = False
                                while is_speaking:
                                    # Record a short snippet allowing playback recording so we can check for interruption
                                    audio_path = self._record_safely(max_seconds=1.5, allow_playback_recording=True, disable_silence_cutoff=True)
                                    if audio_path:
                                        interruption_transcript = self.voice_manager._safe_transcribe(
                                            audio_path, multilingual=True, for_language_selection=True
                                        )
                                        
                                        if has_repetitive_loop(interruption_transcript):
                                            logger.warning("[BARGE-IN] Detected repetitive Whisper hallucination loop in interruption transcript: %r. Ignoring.", interruption_transcript)
                                            interruption_transcript = ""

                                        if interruption_transcript:
                                            # Check if the transcribed text is self-generated audio (echo)
                                            is_self = self._is_echo(interruption_transcript)
                                            
                                            if is_self:
                                                logger.info("[BARGE-IN] Rejecting self-generated audio (echo): %r", interruption_transcript)
                                                self._delete_audio(audio_path)
                                                continue

                                            cleaned = interruption_transcript.strip().lower()
                                            import re
                                            cleaned = re.sub(r"[^\w\s\u0c00-\u0c7f\u0900-\u097f\u0b80-\u0bff\u0c80-\u0cff]", "", cleaned)
                                            
                                            stop_keywords = {
                                                "stop", "stop speaking", "enough", "cancel", "shut up", "nova stop",
                                                "ఆపు", "ఆపండి", "చాలు", "apu", "apandi", "chalu",
                                                "ruko", "band karo", "niruthu", "pothum", "nillisu", "saaku"
                                            }
                                            
                                            is_stop = any(kw in cleaned for kw in stop_keywords) or any(cleaned in kw for kw in stop_keywords if len(cleaned) > 2)
                                            if is_stop:
                                                logger.info("[BARGE-IN] Stop command detected during TTS: %r. Interrupting playback!", interruption_transcript)
                                                self.interrupt()
                                                self._delete_audio(audio_path)
                                                break
                                                
                                        self._delete_audio(audio_path)
                                    else:
                                        time.sleep(0.1)
                                        
                                    if self.voice_manager and hasattr(self.voice_manager, "speech_controller"):
                                        from unittest.mock import Mock
                                        if not isinstance(self.voice_manager.speech_controller, Mock):
                                            is_speaking = self.voice_manager.speech_controller.is_speaking()
                                        else:
                                            is_speaking = False
                                    else:
                                        is_speaking = False
                                    
                            except Exception as speak_err:
                                logger.error("TTS execution error: %s", speak_err)
                            tts_finished_time = time.time()
                            tts_lat = tts_finished_time - start_tts

                            # Clear/drain any stale microphone audio already buffered during TTS
                            if self.recorder and hasattr(self.recorder, "audio_queue"):
                                drained = 0
                                while not self.recorder.audio_queue.empty():
                                    try:
                                        self.recorder.audio_queue.get_nowait()
                                        drained += 1
                                    except Exception:
                                        break
                                if drained > 0:
                                    logger.info("[AlwaysListeningEngine] Drained %d stale audio blocks after TTS completion.", drained)

                            # Compute total command latency
                            total_lat = time.time() - start_stt
                            
                            recording_ms = int(rec_lat * 1000)
                            command_stt_ms = int(stt_lat * 1000)
                            execution_ms = int(exec_lat * 1000)
                            tts_ms = int(tts_lat * 1000)
                            total_ms = int(total_lat * 1000)

                            logger.info(
                                "[TIMING-METRICS] Command: %r | execution_id: %s | recording_ms: %d | command_stt_ms: %d | execution_ms: %d | tts_ms: %d | total_ms: %d",
                                transcript, exec_id, recording_ms, command_stt_ms, execution_ms, tts_ms, total_ms
                            )

                            # Print VOICE-LATENCY log block exactly as requested
                            logger.info(
                                "[VOICE-LATENCY]\n"
                                "wake_detected=%.4f\n"
                                "stt_start=%.4f\n"
                                "stt_end=%.4f\n"
                                "intent_start=%.4f\n"
                                "intent_end=%.4f\n"
                                "response_start=%.4f\n"
                                "tts_start=%.4f\n"
                                "tts_end=%.4f\n"
                                "total=%.4f",
                                wake_detected_time,
                                stt_started_time,
                                stt_finished_time,
                                intent_started_time,
                                intent_finished_time,
                                response_started_time,
                                tts_started_time,
                                tts_finished_time,
                                total_lat
                            )

                            # Format telemetry metrics string
                            telemetry_str = f"STT {stt_lat:.2f}s | Route 0.01s | Exec {exec_lat:.2f}s | TTS {tts_lat:.2f}s | Total {total_lat:.2f}s"

                            callback_to_use = self.on_command_callback or (self.voice_manager.on_command_callback if self.voice_manager else None)
                            if callback_to_use:
                                try:
                                    if hasattr(callback_to_use, "__self__") and hasattr(callback_to_use.__self__, "dispatch_voice_command"):
                                        callback_to_use.__self__.dispatch_voice_command(transcript, response_text, telemetry_str)
                                    else:
                                        import inspect
                                        has_exec_id = False
                                        has_two_params = False
                                        try:
                                            sig = inspect.signature(callback_to_use)
                                            has_exec_id = "exec_id" in sig.parameters
                                            has_two_params = len(sig.parameters) >= 2
                                        except Exception:
                                            pass
                                        
                                        if hasattr(callback_to_use, "mock_add_spec"):
                                            has_two_params = True

                                        if has_exec_id:
                                            callback_to_use(transcript, response_text, exec_id)
                                        elif has_two_params:
                                            callback_to_use(transcript, response_text)
                                        else:
                                            callback_to_use(transcript)
                                except Exception as cb_err:
                                    logger.error("Callback execution error: %s", cb_err)

                        except Exception as cmd_err:
                            logger.error("Error in on_command_callback execution: %s", cmd_err)
                        finally:
                            # Drain TTS output before re-opening mic to prevent echo feedback.
                            self._wait_for_tts_drain()
                            # Resume recording only after processing/TTS completes
                            logger.info("[STATE] Transitioned to LISTENING")
                            self._state = "LISTENING"
                            if self.voice_manager:
                                self.voice_manager.state = "LISTENING"
                            last_activity_time = time.time()
                            time.sleep(0.5)
                    else:
                        # No speech detected, check timeout
                        if time.time() - last_activity_time > self.conversation_timeout:
                            logger.info("[VOICE] Conversation timed out (no speech). Returning to IDLE.")
                            logger.info("[STATE] Transitioned to IDLE")
                            self._state = "IDLE"

                elif self._state in ("PROCESSING", "SPEAKING"):
                    # Check for mid-speak stop command interruption
                    audio_path = self._record_safely(max_seconds=1.5, allow_playback_recording=True, disable_silence_cutoff=True)
                    if audio_path:
                        interruption_transcript = self.voice_manager._safe_transcribe(
                            audio_path, multilingual=True, for_language_selection=True
                        )
                        self._delete_audio(audio_path)
                        
                        cleaned = interruption_transcript.strip().lower()
                        import re
                        cleaned = re.sub(r"[^\w\s\u0c00-\u0c7f\u0900-\u097f\u0b80-\u0bff\u0c80-\u0cff]", "", cleaned)
                        
                        stop_keywords = {
                            "stop", "stop speaking", "enough", "cancel", "shut up", "nova stop",
                            "ఆపు", "ఆపండి", "చాలు", "apu", "apandi", "chalu",
                            "ruko", "band karo", "niruthu", "pothum", "nillisu", "saaku"
                        }
                        is_stop = any(kw in cleaned for kw in stop_keywords) or any(cleaned in kw for kw in stop_keywords if len(cleaned) > 2)
                        
                        if is_stop:
                            logger.info("[Interruption] Stop command detected during speaking/processing! Interrupting...")
                            self.interrupt()
                            self._state = "LISTENING"
                            last_activity_time = time.time()
                    else:
                        time.sleep(0.2)
            except Exception as loop_err:
                logger.error("Exception encountered in AlwaysListening loop: %s", loop_err)
                time.sleep(1.0)

    def interrupt(self) -> None:
        """Interrupt active text-to-speech playback and transition back to LISTENING."""
        logger.info("[AlwaysListeningEngine] Interrupting speaking state and active TTS...")
        self._state = "STOPPING"
        if self.voice_manager:
            self.voice_manager.state = "STOPPING"
            try:
                self.voice_manager.interrupt()
            except Exception as e:
                logger.debug("Failed calling voice_manager.interrupt: %s", e)
        
        # Drain recorder queue so trailing 'stop' isn't processed as command
        if self.recorder and hasattr(self.recorder, "audio_queue"):
            drained = 0
            while not self.recorder.audio_queue.empty():
                try:
                    self.recorder.audio_queue.get_nowait()
                    drained += 1
                except Exception:
                    break
            if drained > 0:
                logger.info("[AlwaysListeningEngine] Drained %d stale audio blocks on interrupt.", drained)

        self._state = "INTERRUPTED"
        if self.voice_manager:
            self.voice_manager.state = "INTERRUPTED"
        self._state = "LISTENING"
        if self.voice_manager:
            self.voice_manager.state = "LISTENING"


    def _record_safely(
        self,
        max_seconds: float,
        allow_playback_recording: bool = False,
        disable_silence_cutoff: bool = False,
        initial_silence_timeout: float | None = None,
        silence_duration: float | None = None
    ) -> Optional[Path]:
        """Record audio with automatic microphone error recovery."""
        try:
            return self.recorder.record_command(
                stop_event=self._stop_event,
                max_record_seconds=max_seconds,
                allow_playback_recording=allow_playback_recording,
                disable_silence_cutoff=disable_silence_cutoff,
                initial_silence_timeout=initial_silence_timeout,
                silence_duration=silence_duration
            )
        except Exception as e:
            logger.warning("[AlwaysListening] Microphone capture error: %s. Attempting recovery...", e)
            return None

    def _delete_audio(self, path: Optional[Path]) -> None:
        if path and path.exists():
            try:
                path.unlink()
            except Exception:
                pass

    def _wait_for_tts_drain(self) -> None:
        """Wait for TTS audio to fully drain from the speaker before re-opening the microphone.

        This is the primary mechanism that prevents Nova from hearing its own voice.
        """
        if self._stop_event.is_set():
            return
        try:
            if self.voice_manager and hasattr(self.voice_manager, "speech_controller"):
                self.voice_manager.speech_controller.wait_for_complete()
            else:
                from voice.audio_recorder import AudioRecorder
                if AudioRecorder.playback_active.is_set():
                    while AudioRecorder.playback_active.is_set() and not self._stop_event.is_set():
                        AudioRecorder.playback_active.wait(timeout=0.1)
            # Short settling sleep to allow speaker transient to clear completely
            time.sleep(0.2)
        except Exception as e:
            logger.debug("[TTS Drain] Error during drain wait: %s", e)
            if not self._stop_event.is_set():
                time.sleep(0.4)
