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


def format_spoken_response(text: str, telugu_mode: bool = False) -> str:
    """Convert raw tool result text into a natural spoken response.
    
    Terminal logs always retain the raw text. This function produces
    only what is spoken aloud – never 'Success:', 'Failure:', etc.
    """
    import re
    text_lower = text.lower()

    # ── Browser / web ──────────────────────────────────────────────────────
    if "opened youtube" in text_lower:
        return "YouTube తెరిచాను."
    if "performed youtube search" in text_lower or "youtube search" in text_lower:
        return "YouTubeలో వెతుకుతున్నాను."
    if "opened whatsapp" in text_lower or "web.whatsapp" in text_lower:
        return "WhatsApp తెరిచాను."
    if "opened" in text_lower and "browser" in text_lower:
        return "Browser తెరిచాను."
    if "browser" in text_lower and "not launched" in text_lower:
        return "Browser తెరవలేదు. మళ్ళీ ప్రయత్నించండి."

    # ── System Control – launched apps ────────────────────────────────────
    if "launched application" in text_lower:
        m = re.search(r"application '([^']+)'", text_lower)
        app = m.group(1).capitalize() if m else ""
        app_telugu = {
            "chrome": "Chrome",
            "calc": "Calculator",
            "notepad": "Notepad",
            "explorer": "File Explorer",
            "taskmgr": "Task Manager",
            "mspaint": "Paint",
        }.get(app.lower(), app)
        return f"{app_telugu} తెరిచాను."

    # ── Android actions ───────────────────────────────────────────────────
    if "adb not found" in text_lower:
        return "Phone connect చేయబడలేదు. USB debug enable చేయండి."
    if "calling" in text_lower:
        m = re.search(r"calling (.+?) \(", text, re.IGNORECASE)
        name = m.group(1).strip().capitalize() if m else "contact"
        return f"{name}కి కాల్ చేస్తున్నాను."
    if "sms composed" in text_lower:
        m = re.search(r"sms composed for (.+?)\.", text, re.IGNORECASE)
        name = m.group(1).strip().capitalize() if m else "contact"
        return f"{name}కి మెసేజ్ సిద్ధం చేస్తున్నాను."
    if "whatsapp opened" in text_lower:
        m = re.search(r"whatsapp opened for (.+?)\.", text, re.IGNORECASE)
        name = m.group(1).strip().capitalize() if m else "contact"
        return f"వాట్సాప్ తెరుస్తున్నాను."
    if "contact" in text_lower and "not found" in text_lower:
        return "Contact దొరకలేదు. Contacts listలో add చేయండి."

    # ── Time / date ───────────────────────────────────────────────────────
    # Pass time responses through unchanged – they are already natural language
    if "current" in text_lower and ("time" in text_lower or "date" in text_lower):
        return text

    # ── Failure / error patterns – never speak raw error text ─────────────
    if text_lower.startswith("failure:"):
        return "క్షమించండి, అది చేయలేకపోయాను."
    if text_lower.startswith("permission denied:"):
        return "అనుమతి లేదు."
    if text_lower.startswith("success:"):
        return "సరే."

    # ── Default: return as-is (LLM text responses are already natural) ─────
    return text


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
            from config import VOICE_MODEL_SIZE
            # If in tests, default to MockSTT
            if os.getenv("ENVIRONMENT") == "test":
                self.stt_engine = MockSTT()
            else:
                self.stt_engine = FasterWhisperSTT(model_size=VOICE_MODEL_SIZE or "tiny")
                
        self.recorder = AudioRecorder(threshold=0.015, silence_duration=1.5)
        self.wake_detector = WakeWordDetector(stt_engine=self.stt_engine)
        self.tts = VoiceTool()
        
        self._thread = None
        self._stop_event = threading.Event()
        self.tts.stop_event = self._stop_event
        self.is_active = False
        self.state = "WAKING" if self.wake_word_enabled else "LISTENING"

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

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _transition(self, new_state: str, current_state: str) -> str:
        """Log every state transition and return the new state."""
        logger.info("[Watchdog] %s -> %s", current_state, new_state)
        _safe_print(f"[VoiceManager] State: {current_state} -> {new_state}")
        self.state = new_state
        return new_state

    def _safe_speak(self, text: str, fallback: str = "") -> None:
        """Speak text via TTS. On failure, log and continue – never raise."""
        try:
            self.tts.execute(text=text)
        except Exception as tts_err:
            logger.error("[Watchdog] TTS failure (text=%r): %s", text, tts_err)
            if fallback:
                try:
                    self.tts.execute(text=fallback)
                except Exception:
                    pass

    def _safe_transcribe(self, audio_path) -> str:
        """Transcribe audio. On failure log and return empty string – never raise."""
        try:
            return self.stt_engine.transcribe(audio_path, stop_event=self._stop_event).strip()
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
        """Call engine.handle_input. On ANY failure return a safe Telugu error string."""
        try:
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
        telugu_mode = False
        is_first_waiting = False

        logger.info("[Watchdog] Initial state: %s", state)
        _safe_print(f"[VoiceManager] Initial state: {state}")

        while not self._stop_event.is_set():
            # Synchronize state from self.state in case it was changed externally
            if self.state != state:
                state = self.state
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
                                cmd_lower = command_text.lower()

                                # Language mode switches
                                if any(p in cmd_lower for p in [
                                    "తెలుగులో మాట్లాడు", "speak in telugu", "switch to telugu",
                                    "telugu lo matlaadu", "speak telugu"
                                ]):
                                    telugu_mode = True
                                    logger.info("[Watchdog] Switched to Telugu mode.")
                                    self._safe_speak("సరే, తెలుగులో మాట్లాడతాను.")
                                    state = self._transition("WAITING", state)
                                    continue

                                if any(p in cmd_lower for p in [
                                    "speak in english", "switch to english", "english lo matlaadu"
                                ]):
                                    telugu_mode = False
                                    logger.info("[Watchdog] Switched to English mode.")
                                    self._safe_speak("Okay, switching to English.")
                                    state = self._transition("WAITING", state)
                                    continue

                                # Execute command
                                logger.info("[Watchdog] Executing command via engine.")
                                res = self._safe_engine(command_text)
                                _safe_print(f"[Voice Response] > {res}")
                                spoken_res = format_spoken_response(res, telugu_mode=telugu_mode)
                                self._safe_speak(spoken_res)

                                if self.on_command_callback:
                                    try:
                                        self.on_command_callback(command_text, res)
                                    except Exception as cb_err:
                                        logger.error("[Watchdog] on_command_callback error: %s", cb_err)

                                state = self._transition("WAITING", state)

                            else:
                                # Empty / rejected transcript
                                logger.info("[Watchdog] Transcript empty or rejected.")
                                retry_msg = ("అర్థం కాలేదు. మళ్ళీ చెప్పండి."
                                             if telugu_mode else "I didn't catch that. Could you repeat?")
                                _safe_print(f"[Voice Response] > {retry_msg}")
                                self._safe_speak(retry_msg)
                                # Stay in LISTENING
                        else:
                            # Silence timeout or recording failed
                            logger.debug("[Watchdog] No audio in LISTENING. Returning to idle.")
                            state = self._transition(self._idle_state(), state)

                    except Exception as listening_err:
                        logger.error("[Watchdog] Error in LISTENING state: %s", listening_err, exc_info=True)
                        self._safe_unlink(audio_path)
                        self._safe_speak(
                            "క్షమించండి, సమస్య వచ్చింది." if telugu_mode
                            else "Sorry, something went wrong. Please try again."
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
                            self._safe_speak(prompt_text)
                        
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
                                    self._safe_speak(farewell)
                                    state = self._transition(self._idle_state(), state)
                                    got_input = True
                                    is_exit = True

                            if is_exit:
                                continue

                            if command_text and not is_ignored_transcript(command_text):
                                _safe_print(f"\n[Voice Input] > {command_text}")
                                logger.info("[Watchdog] WAITING command: %r", command_text)
                                cmd_lower = command_text.lower()
                                got_input = True

                                # Language mode switches
                                if any(p in cmd_lower for p in [
                                    "తెలుగులో మాట్లాడు", "speak in telugu", "switch to telugu",
                                    "telugu lo matlaadu", "speak telugu"
                                ]):
                                    telugu_mode = True
                                    self._safe_speak("సరే, తెలుగులో మాట్లాడతాను.")
                                    state = self._transition("WAITING", state)

                                elif any(p in cmd_lower for p in [
                                    "speak in english", "switch to english", "english lo matlaadu"
                                ]):
                                    telugu_mode = False
                                    self._safe_speak("Okay, switching to English.")
                                    state = self._transition("WAITING", state)

                                else:
                                    # Execute command via engine (Layer 1: never raises)
                                    logger.info("[Watchdog] Executing WAITING command via engine.")
                                    res = self._safe_engine(command_text)
                                    _safe_print(f"[Voice Response] > {res}")
                                    spoken_res = format_spoken_response(res, telugu_mode=telugu_mode)
                                    self._safe_speak(spoken_res)

                                    if self.on_command_callback:
                                        try:
                                            self.on_command_callback(command_text, res)
                                        except Exception as cb_err:
                                            logger.error("[Watchdog] on_command_callback error: %s", cb_err)

                                        state = self._transition("WAITING", state)

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
