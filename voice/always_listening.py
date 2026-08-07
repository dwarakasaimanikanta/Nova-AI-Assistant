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

from utils.logger import get_logger

logger = get_logger(__name__)


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
        self.state = "WAKING"  # "WAKING" (wake-word detection) or "LISTENING" (active conversation)

    def start(self) -> None:
        """Start the background monitoring thread."""
        with self._lock:
            if self.running:
                logger.warning("AlwaysListeningEngine is already running.")
                return
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

        while not self._stop_event.is_set():
            try:
                # CPU breathing room
                time.sleep(0.1)

                if self.state == "WAKING":
                    # 1. Wake word detection state
                    audio_path = self._record_safely(max_seconds=2.0)
                    if not audio_path:
                        # Mic error or cancelled -> recover and try again
                        time.sleep(1.0)
                        continue

                    detected = self.wake_detector.detect(audio_path, stop_event=self._stop_event)
                    self._delete_audio(audio_path)

                    if detected:
                        logger.info("Wake word matched! Transitioning to LISTENING.")
                        self.state = "LISTENING"
                        last_activity_time = time.time()
                        if self.on_wake_callback:
                            try:
                                self.on_wake_callback()
                            except Exception as wake_err:
                                logger.error("Error in on_wake_callback: %s", wake_err)

                elif self.state == "LISTENING":
                    # 2. Active conversation state
                    audio_path = self._record_safely(max_seconds=5.0)
                    if not audio_path:
                        # Mic error or cancelled -> check timeout and recover
                        if time.time() - last_activity_time > self.conversation_timeout:
                            logger.info("Conversation timed out. Returning to WAKING.")
                            self.state = "WAKING"
                        else:
                            time.sleep(0.5)
                        continue

                    # Transcribe
                    transcript = ""
                    try:
                        transcript = self.voice_manager._safe_transcribe(audio_path)
                    except Exception as trans_err:
                        logger.error("Transcription exception: %s", trans_err)
                    finally:
                        self._delete_audio(audio_path)

                    if transcript and transcript.strip():
                        logger.info("Received command: %r", transcript)
                        # Reset timeout activity
                        last_activity_time = time.time()
                        
                        # Process command
                        response = self.voice_manager._safe_engine(transcript)
                        
                        # Speak response
                        try:
                            from voice.voice_manager import format_spoken_response
                            spoken_res = format_spoken_response(response)
                            self.voice_manager._safe_speak(spoken_res)
                        except Exception as speak_err:
                            logger.error("TTS execution error: %s", speak_err)

                        # Callback trigger
                        if self.on_command_callback:
                            try:
                                self.on_command_callback(transcript, response)
                            except Exception as cmd_cb_err:
                                logger.error("Error in on_command_callback: %s", cmd_cb_err)
                    else:
                        # No speech matching, check timeout
                        if time.time() - last_activity_time > self.conversation_timeout:
                            logger.info("Conversation timed out (no speech). Returning to WAKING.")
                            self.state = "WAKING"

            except Exception as loop_err:
                logger.error("Exception encountered in AlwaysListening loop: %s", loop_err)
                time.sleep(1.0)

    def _record_safely(self, max_seconds: float) -> Optional[Path]:
        """Record audio with automatic microphone error recovery."""
        try:
            return self.recorder.record_command(
                stop_event=self._stop_event,
                max_record_seconds=max_seconds
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
