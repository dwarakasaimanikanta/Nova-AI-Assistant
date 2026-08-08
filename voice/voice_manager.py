"""
voice/voice_manager.py
----------------------
Manages the consolidated helper interfaces for voice input, transcription, text-to-speech, and commands.
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

    # ── PART 4: Better Voice Replies (English Web Sites) ──────────────────
    if not telugu_mode:
        if "youtube.com/results" in text_lower or "search flask on youtube" in text_lower or "search python tutorials on youtube" in text_lower:
            return "Searching YouTube Boss."
        if "google.com/search" in text_lower or "search python tutorials" in text_lower:
            return "Searching Google Boss."
        if "youtube.com" in text_lower or "opened youtube" in text_lower:
            return "Opening YouTube Boss."
        if "mail.google.com" in text_lower or "gmail" in text_lower:
            return "Opening Gmail Boss."
        if "github.com" in text_lower or "github" in text_lower:
            return "Opening GitHub Boss."
        if "chatgpt.com" in text_lower or "chatgpt" in text_lower:
            return "Opening ChatGPT Boss."
        if "linkedin.com" in text_lower or "linkedin" in text_lower:
            return "Opening LinkedIn Boss."
        if "google.com" in text_lower or "google" in text_lower:
            return "Opening Google Boss."
        if "netflix.com" in text_lower or "netflix" in text_lower:
            return "Opening Netflix Boss."
        if "amazon.in" in text_lower or "amazon" in text_lower:
            return "Opening Amazon Boss."
        if "vscode" in text_lower or "vs code" in text_lower or "visual studio" in text_lower or "launched application 'code'" in text_lower or "launched application 'vscode'" in text_lower:
            return "Opening VS Code Boss."
        if "chrome" in text_lower or "launched playwright browser 'chrome'" in text_lower:
            return "Launching Chrome Boss."

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
    if "current" in text_lower and ("time" in text_lower or "date" in text_lower):
        return text

    # ── Failure / error patterns ──────────────────────────────────────────
    if text_lower.startswith("failure:"):
        return "క్షమించండి, అది చేయలేకపోయాను."
    if text_lower.startswith("permission denied:"):
        return "అనుమతి లేదు."
    if text_lower.startswith("success:"):
        return "సరే." if telugu_mode else "Okay Boss."

    # ── Default: return as-is (LLM text responses are already natural) ─────
    return text


class VoiceManager:
    """Manages the background state transitions and low-level wrappers for audio/STT/TTS services."""

    def __init__(
        self,
        engine: Any,
        stt_engine: SpeechToTextEngine | None = None,
        wake_word_enabled: bool = False,
        voice_input_enabled: bool = False,
        on_command_callback: Any = None,
    ) -> None:
        # Check recording dependencies
        from voice.audio_recorder import SOUNDDEVICE_AVAILABLE, NUMPY_AVAILABLE
        if not SOUNDDEVICE_AVAILABLE or not NUMPY_AVAILABLE:
            logger.warning("[VOICE] Voice recording dependencies (sounddevice/numpy) are missing. Disabling voice input.")
            voice_input_enabled = False

        self.engine = engine
        self.wake_word_enabled = wake_word_enabled
        self.voice_input_enabled = voice_input_enabled
        self.on_command_callback = on_command_callback
        
        # Load STT engine
        if stt_engine:
            self.stt_engine = stt_engine
        else:
            from config import VOICE_MODEL_SIZE
            if os.getenv("ENVIRONMENT") == "test":
                self.stt_engine = MockSTT()
            else:
                self.stt_engine = FasterWhisperSTT(model_size=VOICE_MODEL_SIZE or "tiny")
                
        # Set silence_duration to 0.8s to stop recording immediately after silence.
        self.recorder = AudioRecorder(threshold=0.015, silence_duration=0.8)
        self.wake_detector = WakeWordDetector(stt_engine=self.stt_engine)
        self.tts = VoiceTool()
        
        self._stop_event = threading.Event()
        self.tts.stop_event = self._stop_event
        self.state = "WAKING" if self.wake_word_enabled else "LISTENING"

    def stop(self) -> None:
        """Signal stops to active tasks."""
        logger.info("[VOICE] Stopping VoiceManager processes...")
        self._stop_event.set()

    def _safe_speak(self, text: str, fallback: str = "") -> None:
        """Speak text via TTS. On failure, log and continue – never raise."""
        try:
            self.tts.execute(text=text)
        except Exception as tts_err:
            logger.error("[VOICE] TTS failure (text=%r): %s", text, tts_err)
            if fallback:
                try:
                    self.tts.execute(text=fallback)
                except Exception:
                    pass

    def _safe_transcribe(self, audio_path) -> str:
        """Transcribe audio. On failure log and return empty string – never raise."""
        try:
            text = self.stt_engine.transcribe(audio_path, stop_event=self._stop_event).strip()
            if text:
                logger.info("[VOICE] Transcribed text: %s", text)
            return text
        except Exception as stt_err:
            logger.error("[VOICE] STT failure: %s", stt_err)
            return ""

    def _safe_engine(self, command_text: str) -> str:
        """Call engine.handle_input. On ANY failure return a safe error string."""
        try:
            return self.engine.handle_input(command_text, stream=False)
        except Exception as eng_err:
            logger.error("[VOICE] Engine failure (input=%r): %s", command_text, eng_err, exc_info=True)
            return "Failure: An internal error occurred."
