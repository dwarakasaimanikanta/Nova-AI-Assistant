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


class VoiceManager:
    """Manages the background thread for voice input capture, wake-word detection, and engine routing."""

    def __init__(
        self,
        engine: Any,
        stt_engine: SpeechToTextEngine | None = None,
        wake_word_enabled: bool = False,
        voice_input_enabled: bool = False,
    ) -> None:
        self.engine = engine
        self.wake_word_enabled = wake_word_enabled
        self.voice_input_enabled = voice_input_enabled
        
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
        self.is_active = False

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

        logger.info("Stopping VoiceManager background thread...")
        self.is_active = False
        self._stop_event.set()
        if self._thread and self._thread != threading.current_thread():
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("VoiceManager background thread stopped.")

    def _run_loop(self) -> None:
        logger.info("Voice input background loop is now active. Wake word enabled = %s", self.wake_word_enabled)
        
        state = "WAKING" if self.wake_word_enabled else "LISTENING"

        while not self._stop_event.is_set():
            try:
                if state == "WAKING":
                    # Capture short audio for wake word check
                    self.recorder.silence_duration = 1.0
                    audio_path = self.recorder.record_command(stop_event=self._stop_event)
                    
                    if audio_path and audio_path.exists():
                        detected = self.wake_detector.detect(audio_path)
                        try:
                            audio_path.unlink()
                        except Exception:
                            pass
                            
                        if detected:
                            logger.info("Wake word detected! Transitioning to LISTENING state.")
                            print("\n[Voice System] > Wake word detected. How can I help?")
                            self.tts.execute(text="Yes, I am listening.")
                            state = "LISTENING"
                            time.sleep(0.5)

                elif state == "LISTENING":
                    # Capture actual user command
                    self.recorder.silence_duration = 1.5
                    audio_path = self.recorder.record_command(stop_event=self._stop_event)
                    
                    if audio_path and audio_path.exists():
                        command_text = self.stt_engine.transcribe(audio_path).strip()
                        try:
                            audio_path.unlink()
                        except Exception:
                            pass

                        if command_text:
                            print(f"\n[Voice Input] > {command_text}")
                            
                            # Execute command via engine
                            res = self.engine.handle_input(command_text, stream=False)
                            print(f"[Voice Response] > {res}")
                            
                            # Speak response back to user
                            self.tts.execute(text=res)
                            
                        if self.wake_word_enabled:
                            state = "WAKING"
                        else:
                            state = "LISTENING"
                    else:
                        if self.wake_word_enabled:
                            state = "WAKING"

                time.sleep(0.1)

            except Exception as e:
                logger.error("Error in VoiceManager background loop: %s", e, exc_info=True)
                time.sleep(1.0)
