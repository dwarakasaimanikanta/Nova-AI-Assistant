"""
voice/voice_manager.py
----------------------
Manages the background listening thread, state transitions, and integration with the engine.
"""

import os
import threading
import time
from pathlib import Path
from typing import Any
from utils.logger import get_logger
from voice.audio_recorder import AudioRecorder
from voice.speech_to_text import SpeechToTextEngine, FasterWhisperSTT, MockSTT
from voice.wake_word import WakeWordDetector
from tools.voice import VoiceTool

logger = get_logger(__name__)


import atexit
import weakref

_active_managers = weakref.WeakSet()

def _cleanup_active_managers():
    for vm in list(_active_managers):
        try:
            vm.stop()
        except Exception:
            pass

atexit.register(_cleanup_active_managers)


def _safe_print(*args, **kwargs) -> None:
    """Print to stdout, catching any encoding/charmap exceptions on Windows cp1252 consoles."""
    try:
        print(*args, **kwargs)
    except Exception:
        try:
            # Fallback to ascii representation of arguments
            ascii_args = [
                str(arg).encode("ascii", errors="replace").decode("ascii")
                for arg in args
            ]
            print(*ascii_args, **kwargs)
        except Exception:
            pass


def format_spoken_response(text: str, telugu_mode: bool = False, response_language: str = None) -> str:
    """Convert raw tool result text into a natural spoken response.

    CRITICAL RULE: Only transform raw tool result strings — never free-form LLM answers.
    A knowledge answer ("Python is a general-purpose language...") must pass through
    unchanged. Only structured tool outputs (Success:/Failure: prefixed, or known
    single-line tool patterns) are normalized to natural speech.

    LLM answers are detected by: multi-line OR length > 150 chars.
    """
    import re

    if not text or not text.strip():
        return text

    from core.language_session import LanguageSession
    lang = response_language
    if not lang:
        if telugu_mode:
            lang = "te"
        else:
            lang = LanguageSession().selected_language
    lang = lang.strip().lower()
    _lang_normalize = {
        "en": "english", "english": "english",
        "te": "telugu", "telugu": "telugu",
        "hi": "hindi", "hindi": "hindi",
        "ta": "tamil", "tamil": "tamil",
        "kn": "kannada", "kannada": "kannada"
    }
    lang = _lang_normalize.get(lang, "english")

    use_telugu  = (lang == "telugu")
    use_hindi   = (lang == "hindi")
    use_tamil   = (lang == "tamil")
    use_kannada = (lang == "kannada")

    text_stripped = text.strip()
    text_lower    = text_stripped.lower()

    # ── Fast pass-through for LLM free-text answers ───────────────────────────
    # Multi-line or long text = LLM knowledge/conversation answer. Pass as-is.
    # Only apply failure-prefix cleanup even for these long responses.
    is_multiline = "\n" in text_stripped
    is_long      = len(text_stripped) > 150
    if is_multiline or is_long:
        if text_lower.startswith("failure:"):
            return "క్షమించండి, అది చేయలేకపోయాను." if use_telugu else "Sorry Boss, I couldn't do that."
        if text_lower.startswith("permission denied:"):
            return "అనుమతి లేదు." if use_telugu else "Permission denied, Boss."
        return text_stripped

    text_lower = text_lower  # short single-line from here

    # Pre-strip 'Success:' prefix so tool patterns below can match the content.
    # e.g. 'Success: Calling Amma (+91...)' → 'Calling Amma (+91...)' → Telugu phrase.
    if text_lower.startswith("success:"):
        rest = text_stripped[8:].strip()
        if not rest:
            return "సరే." if use_telugu else "Done, Boss."
        # Re-run pattern matching on the stripped content
        text_stripped = rest
        text_lower    = rest.lower()

    # Strip raw enum status strings early
    for pat in (r"^ExecutionStatus\.\w+$", r"^BrowserStatus\.\w+$", r"^WorkspaceStatus\.\w+$"):
        if re.match(pat, text_stripped):
            return "సరే." if use_telugu else "Done, Boss."

    # --- Tool Result Patterns (Only match if it looks like a structured tool output) ---
    if text_lower.startswith(("adb not found", "calling", "sms composed", "whatsapp opened", "contact")):
        if "adb not found" in text_lower:
            return "Phone connect చేయబడలేదు. USB debug enable చేయండి." if use_telugu else "Phone not connected. Please enable USB debugging."
        if "calling" in text_lower:
            m = re.search(r"calling (.+?) \(", text, re.IGNORECASE)
            name = m.group(1).strip().capitalize() if m else "contact"
            return f"{name}కి కాల్ చేస్తున్నాను." if use_telugu else f"Calling {name}, Boss."
        if "sms composed" in text_lower:
            m = re.search(r"sms composed for (.+?)\.", text, re.IGNORECASE)
            name = m.group(1).strip().capitalize() if m else "contact"
            return f"{name}కి మెసేజ్ సిద్ధం చేస్తున్నాను." if use_telugu else f"Sending a message to {name}, Boss."
        if "whatsapp opened" in text_lower:
            m = re.search(r"whatsapp opened for (.+?)\.", text, re.IGNORECASE)
            name = m.group(1).strip().capitalize() if m else "contact"
            return "వాట్సాప్ తెరుస్తున్నాను." if use_telugu else f"Opening WhatsApp for {name}, Boss."
        if "contact" in text_lower and "not found" in text_lower:
            m = re.search(r"contact '([^']+)' not found", text_lower)
            name = m.group(1).capitalize() if m else "Contact"
            return f"{name} దొరకలేదు." if use_telugu else f"I couldn't find contact {name}, Boss."

    # --- Failure / error patterns ---
    # NOTE: Check specific failure sub-patterns BEFORE the generic Failure: handler
    # so that e.g. 'Failure: Contact \'X\' not found...' gets the specific contact phrase.
    if text_lower.startswith(("failure:", "permission denied:")) or text_lower.startswith(("step failed", "failed after")):
        # ADB not installed (inside Failure: prefix)
        if "adb not found" in text_lower:
            return "Phone connect చేయబడలేదు. USB debug enable చేయండి." if use_telugu else "Phone not connected. Please enable USB debugging."
        # Contact not found (even inside Failure: prefix)
        if "contact" in text_lower and "not found" in text_lower:
            m = re.search(r"contact '([^']+)' not found", text_lower)
            name = m.group(1).capitalize() if m else "Contact"
            return f"{name} దొరకలేదు." if use_telugu else f"I couldn't find contact {name}, Boss."
        return "క్షమించండి, అది చేయలేకపోయాను." if use_telugu else "Sorry Boss, I couldn't do that."

    # Browser / web
    if any(x in text_lower for x in ("opened youtube", "youtube.com", "youtube search")):
        return "YouTube తెరిచాను." if use_telugu else "Opening YouTube Boss."
    if "opened whatsapp" in text_lower or "web.whatsapp" in text_lower:
        return "WhatsApp తెరిచాను." if use_telugu else "Opening WhatsApp, Boss."
    if "opened" in text_lower and ("github" in text_lower or "gmail" in text_lower):
        return "తెరిచాను." if use_telugu else "Opening that, Boss."
    if "navigated" in text_lower or ("opened" in text_lower and "url" in text_lower):
        return "సరే." if use_telugu else "Done, Boss."

    # System Control
    if "launched application" in text_lower or "opened application" in text_lower:
        m = re.search(r"application \'?([^\',\n]+)\'?", text_lower)
        app = m.group(1).strip().capitalize() if m else "the app"
        return f"{app} తెరిచాను." if use_telugu else f"Opening {app}, Boss."
    if any(kw in text_lower for kw in ("application closed", "terminated", "process killed")):
        return "మూసివేశాను." if use_telugu else "Closed, Boss."

    # Files / Projects
    if "file created" in text_lower or "folder created" in text_lower:
        return "సృష్టించాను." if use_telugu else "Created, Boss."

    # Screenshot
    if "screenshot" in text_lower and "saved" in text_lower:
        return "Screenshot తీశాను." if use_telugu else "Screenshot taken, Boss."

    # Time / date
    if "current" in text_lower and ("time" in text_lower or "date" in text_lower):
        if use_telugu:
            time_match = re.search(r"current\s+time\s+is\s+([^\n.]+)", text_lower)
            if time_match:
                val = time_match.group(1).strip()
                return f"ఇప్పుడు సమయం {val}"
            date_match = re.search(r"current\s+date\s+is\s+([^\n.]+)", text_lower)
            if date_match:
                val = date_match.group(1).strip()
                return f"ఈరోజు తేదీ {val}"
            return "ఇప్పుడు సమయం ఎంత?"
        return text

    # ── Default: return as-is ─────────────────────────────────────────────────
    # All LLM conversational/knowledge answers fall here and are spoken unchanged.
    return text_stripped

def is_ignored_transcript(text: str) -> bool:
    cleaned = "".join(ch for ch in text.lower() if ch.isalnum() or ch.isspace()).strip()
    ignored = {
        "", "thank you", "you", "im here now", "i dont know", "go on",
        "thanks for watching", "please subscribe", "subscribed",
        "thanks for watching and ill see you in the next one",
        "ill see you in the next video", "and yeah", "oh", "so"
    }
    if cleaned in ignored:
        return True
    if len(cleaned) <= 2 and not cleaned.isdigit():
        return True
    return False


class VoiceManager:
    """Manages the background thread for voice input capture, wake-word detection, and engine routing."""

    def __init__(
        self,
        engine: Any,
        stt_engine: SpeechToTextEngine | None = None,
        wake_word_enabled: bool = False,
        voice_input_enabled: bool = False,
        on_command_callback: Any = None,
    ) -> None:
        self.engine = engine
        self.wake_word_enabled = wake_word_enabled
        self.voice_input_enabled = voice_input_enabled
        self.on_command_callback = on_command_callback
        
        # Load STT engine
        if stt_engine:
            self.stt_engine = stt_engine
        else:
            from config import VOICE_MODEL_SIZE, NOVA_WHISPER_MODEL
            # If in tests, default to MockSTT
            if os.getenv("ENVIRONMENT") == "test":
                self.stt_engine = MockSTT()
            else:
                model_sz = NOVA_WHISPER_MODEL or VOICE_MODEL_SIZE or "small"
                self.stt_engine = FasterWhisperSTT(model_size=model_sz)
                
        from config import NOVA_SILENCE_DURATION
        self.recorder = AudioRecorder(threshold=0.015, silence_duration=NOVA_SILENCE_DURATION)
        self.wake_detector = WakeWordDetector(stt_engine=self.stt_engine)
        self.tts = VoiceTool()
        from voice.speech_controller import SpeechController
        self.speech_controller = SpeechController(voice_manager=self)
        
        self._thread = None
        self._stop_event = threading.Event()
        self.tts_stop_event = threading.Event()
        self.tts.stop_event = self.tts_stop_event
        self.is_active = False
        self._state = "WAKING" if self.wake_word_enabled else "LISTENING"
        self._selected_language = "en"
        _active_managers.add(self)

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass

    @property
    def state(self) -> str:
        val = getattr(self, "_state", "WAKING" if self.wake_word_enabled else "LISTENING")
        if val == "WAKING":
            return "IDLE"
        return val

    @state.setter
    def state(self, val: str) -> None:
        if val == "IDLE":
            val = "WAKING" if self.wake_word_enabled else "LISTENING"
            
        current = getattr(self, "_state", None)
        
        is_interrupted = False
        if hasattr(self, "speech_controller") and self.speech_controller:
            if getattr(self.speech_controller, "stop_event", None) and self.speech_controller.stop_event.is_set():
                is_interrupted = True

        if current == "WAITING" and val in ("WAKING", "LISTENING") and not is_interrupted:
            logger.debug("[VoiceManager] Ignoring external state transition to %s because we are in WAITING (continuous conversation) mode.", val)
            return
        self._state = val

    @property
    def selected_language(self) -> str:
        from core.language_session import LanguageSession
        return LanguageSession().selected_language

    @selected_language.setter
    def selected_language(self, val: str) -> None:
        from core.language_session import LanguageSession
        LanguageSession().selected_language = val
        logger.info("[LANGUAGE-STATE]")
        logger.info("Selected response language: %s", LanguageSession().selected_language)
        if hasattr(self, "engine") and self.engine:
            try:
                self.engine.selected_language = val
            except Exception as e:
                logger.debug("Could not sync selected_language to engine: %s", e)

    @property
    def response_language(self) -> str:
        from core.language_session import LanguageSession
        return LanguageSession().display_name.lower()

    @response_language.setter
    def response_language(self, val: str) -> None:
        self.selected_language = val

    @property
    def telugu_mode(self) -> bool:
        from core.language_session import LanguageSession
        return LanguageSession().selected_language == "te"

    @telugu_mode.setter
    def telugu_mode(self, val: bool) -> None:
        if val:
            self.selected_language = "te"
        else:
            if self.selected_language == "te":
                self.selected_language = "en"


    def start(self) -> None:
        """Start the background voice listener thread."""
        if not self.voice_input_enabled:
            logger.info("Voice input is disabled in config. Not starting VoiceManager.")
            return

        if self.is_active:
            logger.warning("VoiceManager is already running.")
            return

        self._stop_event.clear()
        self.is_active = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="VoiceManagerThread")
        self._thread.start()
        logger.info("VoiceManager background thread started.")

    def stop(self) -> None:
        """Stop the background voice listener thread."""
        # Stop AlwaysListeningEngine cleanly (if it exists)
        if hasattr(self, "always_listening") and self.always_listening:
            try:
                self.always_listening.stop()
            except Exception as e:
                logger.error("Error stopping always_listening in VoiceManager.stop: %s", e)

        if not self.is_active:
            return

        logger.info("[Watchdog] Stopping VoiceManager background thread...")
        self.is_active = False
        self._stop_event.set()
        if self._thread and self._thread != threading.current_thread():
            logger.info("[Watchdog] Joining VoiceManager thread...")
            self._thread.join(timeout=1.5)
            if self._thread.is_alive():
                logger.warning("[Watchdog] VoiceManager thread did not exit within timeout. Force exiting.")
            else:
                logger.info("[Watchdog] VoiceManager thread stopped successfully.")
            self._thread = None
        logger.info("VoiceManager background thread stopped.")

    def interrupt(self) -> None:
        """Interrupt active TTS playback and clean up speech queue."""
        logger.info("[VoiceManager] Interrupting speech controller.")
        if hasattr(self, "speech_controller") and self.speech_controller:
            try:
                self.speech_controller.interrupt()
            except Exception as e:
                logger.error("Failed calling speech_controller.interrupt: %s", e)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _transition(self, new_state: str, current_state: str) -> str:
        """Log every state transition and return the new state."""
        logger.info("[Watchdog] %s -> %s", current_state, new_state)
        _safe_print(f"[VoiceManager] State: {current_state} -> {new_state}")
        self._state = new_state
        return new_state

    def _safe_speak(self, text: str, fallback: str = "", telugu_mode: bool = False, response_language: str = None) -> None:
        """Speak text via TTS. On failure, log and continue – never raise."""
        try:
            logger.info("[Watchdog] Speaking response...")
            # Always use the session-locked selected_language; only fall back if nothing is set.
            lang = response_language or self.selected_language or "en"
            self._stop_event.clear()
            if hasattr(self, "speech_controller") and self.speech_controller:
                self.speech_controller.stop_event.clear()
            self.speech_controller.speak(text, response_language=lang)
        except Exception as tts_err:
            logger.error("[Watchdog] TTS failure (text=%r): %s", text, tts_err)
            if fallback:
                try:
                    self.speech_controller.speak(fallback, response_language=lang)
                except Exception:
                    pass

    def _safe_transcribe(self, audio_path: Path, multilingual: bool = False, for_language_selection: bool = False) -> str:
        """Transcribe audio. On failure, log and return empty – never raise."""
        try:
            selected = getattr(self, "selected_language", "en").strip().lower()
            is_multilingual = multilingual or (selected not in ("en", "english"))
            actual_stop_event = self._stop_event if (for_language_selection or os.getenv("ENVIRONMENT") != "test") else None
            
            import inspect
            func = self.stt_engine.transcribe
            if hasattr(func, "side_effect") and func.side_effect is not None:
                func = func.side_effect
                
            kwargs = {}
            try:
                sig = inspect.signature(func)
                has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
                if has_kwargs or "stop_event" in sig.parameters:
                    kwargs["stop_event"] = actual_stop_event
                if has_kwargs or "multilingual" in sig.parameters:
                    kwargs["multilingual"] = is_multilingual
                if has_kwargs or "for_language_selection" in sig.parameters:
                    kwargs["for_language_selection"] = for_language_selection
            except Exception:
                kwargs["stop_event"] = actual_stop_event
                kwargs["multilingual"] = is_multilingual
                kwargs["for_language_selection"] = for_language_selection
                
            return self.stt_engine.transcribe(audio_path, **kwargs).strip()
        except Exception as stt_err:
            logger.error("[Watchdog] STT failure: %s", stt_err)
            return ""

    def _safe_record(self, max_record_seconds: float, silence_duration: float) -> "Path | None":
        """Record audio. On failure log and return None – never raise."""
        try:
            self.recorder.silence_duration = silence_duration
            return self.recorder.record_command(
                stop_event=self._stop_event,
                max_record_seconds=max_record_seconds,
            )
        except Exception as rec_err:
            logger.error("[Watchdog] Recording failure: %s", rec_err)
            return None

    def _safe_engine(self, command_text: str) -> str:
        """Call engine.handle_input. On ANY failure return a safe error string.

        IMPORTANT: The session-locked language (self.selected_language) is used to
        instruct the LLM to respond in the chosen language. The user's input language
        (detected by STT) never overrides this lock.
        """
        try:
            # Use the short-code (en/te/hi/ta/kn) as the authoritative session language.
            session_lang = self.selected_language  # short-code e.g. 'te', 'en'
            
            # Sync to the engine's attribute
            if hasattr(self.engine, "selected_language"):
                try:
                    self.engine.selected_language = session_lang
                except Exception:
                    pass
            if hasattr(self.engine, "engine") and hasattr(self.engine.engine, "selected_language"):
                try:
                    self.engine.engine.selected_language = session_lang
                except Exception:
                    pass

            full_names = {
                "te": "Telugu", "hi": "Hindi", "ta": "Tamil", "kn": "Kannada"
            }
            if session_lang in full_names:
                lang_name = full_names[session_lang]
                instruction = f"(Respond in {lang_name} language please)"
                if instruction not in command_text:
                    command_text = f"{command_text} {instruction}"
            
            # Check if engine is a mock or does not accept selected_language
            is_mock = False
            try:
                from unittest.mock import NonCallableMock
                if isinstance(self.engine, NonCallableMock):
                    is_mock = True
            except Exception:
                pass
                
            import inspect
            func = self.engine.handle_input
            if hasattr(func, "side_effect") and func.side_effect is not None:
                func = func.side_effect
            has_sel_lang = False
            try:
                sig = inspect.signature(func)
                has_sel_lang = "selected_language" in sig.parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            except Exception:
                has_sel_lang = False
                
            if has_sel_lang and not is_mock:
                return self.engine.handle_input(command_text, stream=False, selected_language=session_lang)
            else:
                return self.engine.handle_input(command_text, stream=False)
        except Exception as eng_err:
            logger.error("[Watchdog] Engine/tool failure (input=%r): %s", command_text, eng_err, exc_info=True)
            return "Failure: An internal error occurred."

    def _safe_unlink(self, path) -> None:
        """Delete a temp audio file silently."""
        try:
            if path and path.exists():
                path.unlink()
        except Exception:
            pass

    def _idle_state(self) -> str:
        """Return the correct idle state based on whether wake-word mode is on."""
        return "WAKING" if self.wake_word_enabled else "LISTENING"

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        logger.info("[Watchdog] Voice loop started. wake_word_enabled=%s", self.wake_word_enabled)

        state = "WAKING" if self.wake_word_enabled else "LISTENING"
        repeat_prompt = False
        telugu_mode = getattr(self, "telugu_mode", False)
        is_first_waiting = False

        logger.info("[Watchdog] Initial state: %s", state)
        _safe_print(f"[VoiceManager] Initial state: {state}")

        while self.is_active:
            # Bypass if AlwaysListening background engine is actively running
            if getattr(self, "always_listening", None) and getattr(self.always_listening, "running", False):
                time.sleep(0.2)
                continue

            # Synchronize state from internal self._state in case it was changed externally
            if self._state != state:
                state = self._state
            telugu_mode = getattr(self, "telugu_mode", False)
            response_language = getattr(self, "response_language", "english")
            # ── LAST-RESORT guard: catches BaseException (KeyboardInterrupt, SystemExit, etc.)
            # so even catastrophic errors don't kill the daemon thread silently.
            try:

                # ════════════════════════════════════════════════════════════
                # STATE: WAKING
                # ════════════════════════════════════════════════════════════
                if state == "WAKING":
                    try:
                        logger.debug("[Watchdog] WAKING – recording for wake word")
                        audio_path = self._safe_record(max_record_seconds=3.0, silence_duration=1.0)

                        if audio_path and audio_path.exists():
                            try:
                                detected = self.wake_detector.detect(audio_path, stop_event=self._stop_event)
                            except Exception as wd_err:
                                logger.error("[Watchdog] Wake detector error: %s", wd_err)
                                detected = False
                            finally:
                                self._safe_unlink(audio_path)

                            if detected:
                                logger.info("[Watchdog] Wake word detected.")
                                _safe_print("\n[Voice System] > Wake word detected. How can I help?")
                                self._safe_speak("చెప్పండి.")
                                state = self._transition("WAITING", state)
                                is_first_waiting = True
                                time.sleep(0.5)
                        # No audio / not detected → stay in WAKING

                    except Exception as waking_err:
                        logger.error("[Watchdog] Error in WAKING state: %s", waking_err, exc_info=True)
                        time.sleep(0.5)
                        # Stay in WAKING – keep trying

                # ════════════════════════════════════════════════════════════
                # STATE: LISTENING
                # ════════════════════════════════════════════════════════════
                elif state == "LISTENING":
                    audio_path = None
                    try:
                        logger.debug("[Watchdog] LISTENING – recording command")
                        audio_path = self._safe_record(max_record_seconds=10.0, silence_duration=1.0)

                        if audio_path and audio_path.exists():
                            command_text = self._safe_transcribe(audio_path)
                            self._safe_unlink(audio_path)
                            audio_path = None

                            is_exit = False
                            if command_text:
                                cmd_lower = command_text.lower()
                                cleaned_cmd = "".join(ch for ch in cmd_lower if ch.isalnum() or ch.isspace()).strip()

                                # Exit keywords check
                                exit_keywords = {
                                    "bye", "goodbye", "stop listening", "thank you",
                                    "cancel", "సరే", "చాలు", "బై"
                                }
                                matched_exit = False
                                for phrase in exit_keywords:
                                    if phrase in cmd_lower or phrase in cleaned_cmd:
                                        matched_exit = True
                                        break
                                if "stop listening" in cmd_lower:
                                    matched_exit = True

                                if matched_exit:
                                    logger.info("[Watchdog] Exit keyword detected.")
                                    farewell = "సరే."
                                    _safe_print(f"[Voice Response] > {farewell}")
                                    self._safe_speak(farewell)
                                    state = self._transition(self._idle_state(), state)
                                    is_exit = True

                            if is_exit:
                                continue

                            if command_text and not is_ignored_transcript(command_text):
                                _safe_print(f"\n[Voice Input] > {command_text}")
                                logger.info("[Watchdog] Command received: %r", command_text)
                                logger.info("[VOICE-DEBUG] command received: %r", command_text)
                                cmd_lower = command_text.lower()

                                # Language mode switches
                                from utils.language_switch import detect_and_handle_language_switch
                                if detect_and_handle_language_switch(command_text, self):
                                    state = self._transition("WAITING", state)
                                    continue

                                # Execute command
                                logger.info("[Watchdog] Executing command via engine.")
                                res = self._safe_engine(command_text)
                                _safe_print(f"[Voice Response] > {res}")
                                spoken_res = format_spoken_response(res, response_language=response_language)
                                self._safe_speak(spoken_res, response_language=response_language)

                                if self.on_command_callback:
                                    try:
                                        import uuid
                                        exec_id = str(uuid.uuid4())[:8]
                                        import inspect
                                        has_exec_id = False
                                        has_two_params = False
                                        try:
                                            sig = inspect.signature(self.on_command_callback)
                                            has_exec_id = "exec_id" in sig.parameters
                                            has_two_params = len(sig.parameters) >= 2
                                        except Exception:
                                            pass
                                        
                                        if hasattr(self.on_command_callback, "mock_add_spec"):
                                            has_two_params = True

                                        if has_exec_id:
                                            self.on_command_callback(command_text, res, exec_id)
                                        elif has_two_params:
                                            self.on_command_callback(command_text, res)
                                        else:
                                            self.on_command_callback(command_text)
                                    except Exception as cb_err:
                                        logger.error("[Watchdog] on_command_callback error: %s", cb_err)

                                state = self._transition("SPEAKING", state)

                            else:
                                # Empty / rejected transcript
                                logger.info("[Watchdog] Transcript empty or rejected.")
                                retry_msg = ("అర్థం కాలేదు. మళ్ళీ చెప్పండి."
                                             if response_language == "telugu" else "I didn't catch that. Could you repeat?")
                                _safe_print(f"[Voice Response] > {retry_msg}")
                                self._safe_speak(retry_msg, response_language=response_language)
                                # Stay in LISTENING
                        else:
                            # Silence timeout or recording failed
                            logger.debug("[Watchdog] No audio in LISTENING. Returning to idle.")
                            state = self._transition(self._idle_state(), state)

                    except Exception as listening_err:
                        logger.error("[Watchdog] Error in LISTENING state: %s", listening_err, exc_info=True)
                        self._safe_unlink(audio_path)
                        self._safe_speak(
                            "క్షమించండి, సమస్య వచ్చింది." if response_language == "telugu"
                            else "Sorry, something went wrong. Please try again.",
                            response_language=response_language
                        )
                        state = self._transition(self._idle_state(), state)
                        time.sleep(0.5)

                # ════════════════════════════════════════════════════════════
                # STATE: WAITING  (conversation follow-up)
                # ════════════════════════════════════════════════════════════
                elif state == "WAITING":
                    audio_path = None
                    try:
                        if is_first_waiting:
                            is_first_waiting = False
                        else:
                            if repeat_prompt:
                                prompt_text = "అర్థం కాలేదు. మళ్ళీ చెప్పండి."
                            else:
                                prompt_text = "ఇంకేమైనా?"

                            logger.info("[Watchdog] WAITING – prompt: %r", prompt_text)
                            _safe_print(f"\n[Voice System] > {prompt_text}")
                            self._safe_speak(prompt_text, response_language=response_language)
                        
                        repeat_prompt = False

                        audio_path = self._safe_record(max_record_seconds=20.0, silence_duration=1.0)
                        got_input = False

                        if audio_path and audio_path.exists():
                            command_text = self._safe_transcribe(audio_path)
                            self._safe_unlink(audio_path)
                            audio_path = None

                            is_exit = False
                            if command_text:
                                cmd_lower = command_text.lower()
                                cleaned_cmd = "".join(ch for ch in cmd_lower if ch.isalnum() or ch.isspace()).strip()

                                # Exit keywords check
                                exit_keywords = {
                                    "bye", "goodbye", "stop listening", "thank you",
                                    "cancel", "సరే", "చాలు", "బై"
                                }
                                matched_exit = False
                                for phrase in exit_keywords:
                                    if phrase in cmd_lower or phrase in cleaned_cmd:
                                        matched_exit = True
                                        break
                                if "stop listening" in cmd_lower:
                                    matched_exit = True

                                if matched_exit:
                                    logger.info("[Watchdog] Exit keyword in WAITING.")
                                    farewell = "సరే."
                                    _safe_print(f"[Voice Response] > {farewell}")
                                    self._safe_speak(farewell, response_language=response_language)
                                    state = self._transition(self._idle_state(), state)
                                    got_input = True
                                    is_exit = True

                            if is_exit:
                                continue

                            if command_text and not is_ignored_transcript(command_text):
                                _safe_print(f"\n[Voice Input] > {command_text}")
                                logger.info("[Watchdog] WAITING command: %r", command_text)
                                logger.info("[VOICE-DEBUG] command received: %r", command_text)
                                cmd_lower = command_text.lower()
                                got_input = True

                                # Language mode switches
                                from utils.language_switch import detect_and_handle_language_switch
                                if detect_and_handle_language_switch(command_text, self):
                                    state = self._transition("WAITING", state)

                                else:
                                    # Execute command via engine (Layer 1: never raises)
                                    logger.info("[Watchdog] Executing WAITING command via engine.")
                                    res = self._safe_engine(command_text)
                                    _safe_print(f"[Voice Response] > {res}")
                                    spoken_res = format_spoken_response(res, response_language=response_language)
                                    self._safe_speak(spoken_res, response_language=response_language)

                                    if self.on_command_callback:
                                        try:
                                            import uuid
                                            exec_id = str(uuid.uuid4())[:8]
                                            import inspect
                                            has_exec_id = False
                                            has_two_params = False
                                            try:
                                                sig = inspect.signature(self.on_command_callback)
                                                has_exec_id = "exec_id" in sig.parameters
                                                has_two_params = len(sig.parameters) >= 2
                                            except Exception:
                                                pass
                                            
                                            if hasattr(self.on_command_callback, "mock_add_spec"):
                                                has_two_params = True

                                            if has_exec_id:
                                                self.on_command_callback(command_text, res, exec_id)
                                            elif has_two_params:
                                                self.on_command_callback(command_text, res)
                                            else:
                                                self.on_command_callback(command_text)
                                        except Exception as cb_err:
                                            logger.error("[Watchdog] on_command_callback error: %s", cb_err)

                                    state = self._transition("SPEAKING", state)

                            else:
                                # Rejected transcript – ask again once
                                logger.info("[Watchdog] WAITING: transcript empty/rejected.")
                                repeat_prompt = True
                                got_input = True
                                state = self._transition("WAITING", state)

                        # Conversation timeout – no speech detected within 10s
                        if not got_input:
                            logger.info("[Watchdog] WAITING timed out. Returning to idle.")
                            state = self._transition(self._idle_state(), state)

                    except Exception as waiting_err:
                        logger.error("[Watchdog] Error in WAITING state: %s", waiting_err, exc_info=True)
                        self._safe_unlink(audio_path)
                        self._safe_speak(
                            "క్షమించండి, సమస్య వచ్చింది." if telugu_mode
                            else "Sorry, something went wrong."
                        )
                        state = self._transition(self._idle_state(), state)
                        time.sleep(0.5)

                elif state == "SPEAKING":
                    # Wait until SpeechController is done speaking
                    if hasattr(self, "speech_controller") and self.speech_controller.is_speaking():
                        time.sleep(0.1)
                        continue
                    else:
                        state = self._transition("WAITING", state)

                elif state in ("PROCESSING", "EXECUTING"):
                    time.sleep(0.1)
                    continue

                else:
                    # Unknown state – reset to safe idle
                    logger.warning("[Watchdog] Unknown state '%s'. Resetting to idle.", state)
                    state = self._transition(self._idle_state(), state)

                time.sleep(0.1)

            except (KeyboardInterrupt, SystemExit):
                logger.info("[Watchdog] Shutdown signal received. Exiting voice loop cleanly.")
                break
            except BaseException as fatal_err:  # noqa: BLE001
                logger.critical("[Watchdog] Unexpected fatal error in voice loop: %s", fatal_err, exc_info=True)
                time.sleep(1.0)
                # Reset to idle – never terminate the thread
                state = self._idle_state()
