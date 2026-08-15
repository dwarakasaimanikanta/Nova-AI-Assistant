"""
voice/speech_controller.py
--------------------------
Central Speech Controller for managing TTS queue, audio processes, and interruption.
"""

import time
import threading
import queue
import ctypes
import platform
from typing import Optional, Any
from utils.logger import get_logger

logger = get_logger(__name__)


import atexit
import weakref

_active_speech_controllers = weakref.WeakSet()

def _cleanup_active_speech_controllers():
    for sc in list(_active_speech_controllers):
        try:
            sc.stop()
        except Exception:
            pass

atexit.register(_cleanup_active_speech_controllers)

class SpeechController:
    """Manages text-to-speech tasks, playback processes, queue management, and interruption."""

    _instance: Optional['SpeechController'] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            import os
            if os.getenv("ENVIRONMENT") == "test":
                inst = super(SpeechController, cls).__new__(cls)
                inst._initialized = False
                return inst
            if cls._instance is None:
                cls._instance = super(SpeechController, cls).__new__(cls)
            return cls._instance

    def __init__(self, voice_manager: Any = None) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            if voice_manager is not None:
                self.voice_manager = voice_manager
            self.stop_event.clear()
            self.speaking_state = "IDLE"
            self.speech_queue = queue.Queue()
            self.currently_speaking_text = ""
            return
        
        self.voice_manager = voice_manager
        self.current_tts_task: Optional[threading.Thread] = None
        self.current_audio_process: Optional[Any] = None
        self.current_response_stream: Optional[Any] = None
        self.speaking_state = "IDLE"  # "IDLE", "SPEAKING"
        self.stop_event = threading.Event()
        self.speech_queue = queue.Queue()
        self._queue_lock = threading.RLock()
        self._play_thread: Optional[threading.Thread] = None
        self.currently_speaking_text = ""
        self._initialized = True
        _active_speech_controllers.add(self)
        logger.info("[SpeechController] Centralized SpeechController initialized.")

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass

    def speak(self, text: str, response_language: str) -> None:
        """Enqueue speech text to be played."""
        with self._queue_lock:
            if self.stop_event.is_set():
                logger.info("[SpeechController] Speech rejected because stop_event is active.")
                return
            
            logger.info("[TTS] Enqueuing speech: %r (lang: %s)", text, response_language)
            self.speech_queue.put((text, response_language))
            self.speaking_state = "SPEAKING"
                
            import os
            if os.getenv("ENVIRONMENT") == "test":
                self._run_queue_loop()
                return

            if not self._play_thread or not self._play_thread.is_alive():
                self._play_thread = threading.Thread(
                    target=self._run_queue_loop,
                    daemon=True,
                    name="SpeechControllerThread"
                )
                self._play_thread.start()

    def _run_queue_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                # Poll queue
                item = self.speech_queue.get(timeout=0.1)
            except queue.Empty:
                break
            
            if self.stop_event.is_set():
                self.speech_queue.task_done()
                break
                
            text, lang = item
            logger.info("[TTS] Playing chunk: %r", text)
            self.currently_speaking_text = text
            
            try:
                from voice.audio_recorder import AudioRecorder
                AudioRecorder.playback_active.set()
                
                # Use voice manager's tts or default VoiceTool
                tts_tool = getattr(self.voice_manager, "tts", None)
                if not tts_tool:
                    from tools.voice import VoiceTool
                    tts_tool = VoiceTool()
                    
                # Call TTS execution
                import os
                if os.getenv("ENVIRONMENT") == "test":
                    tts_tool.execute(text=text)
                else:
                    tts_tool.execute(
                        text=text,
                        response_language=lang,
                        stop_event=self.stop_event
                    )
            except Exception as e:
                logger.error("[SpeechController] Playback exception: %s", e)
            finally:
                self.currently_speaking_text = ""
                self.speech_queue.task_done()
                from voice.audio_recorder import AudioRecorder
                AudioRecorder.playback_finished_time = time.time()
                AudioRecorder.playback_active.clear()

                
        with self._queue_lock:
            if self.speech_queue.empty():
                self.speaking_state = "IDLE"
                pass

    def is_speaking(self) -> bool:
        """Returns True if SpeechController is active or has queued speech."""
        return self.speaking_state == "SPEAKING" or not self.speech_queue.empty()

    def wait_for_complete(self) -> None:
        """Blocks until all queued speech items are played and playback is idle."""
        import time
        time.sleep(0.05)
        while self.is_speaking():
            time.sleep(0.05)

    def interrupt(self) -> None:
        """Cancel current audio playback, clear speech queue, prevent new TTS from starting, and reset stop_event."""
        logger.info("[SpeechController] Central STOP interruption requested.")
        
        # 1. Set the stop event
        self.stop_event.set()
        
        # 2. Clear queued speech
        with self._queue_lock:
            while not self.speech_queue.empty():
                try:
                    self.speech_queue.get_nowait()
                    self.speech_queue.task_done()
                except queue.Empty:
                    break
            self.speaking_state = "IDLE"
            self.currently_speaking_text = ""
            if self.voice_manager:
                self.voice_manager.state = "IDLE"


        # 3. Stop winmm MCI playback immediately on Windows
        if platform.system() == "Windows":
            try:
                winmm = ctypes.windll.winmm
                winmm.mciSendStringW(ctypes.c_wchar_p("stop my_mp3"), None, 0, 0)
                winmm.mciSendStringW(ctypes.c_wchar_p("close my_mp3"), None, 0, 0)
            except Exception as e:
                logger.debug("[SpeechController] WinMM mci stop failed: %s", e)
                
            # Stop SAPI fallback speaker
            try:
                from tools.voice import VoiceTool
                if VoiceTool._sapi_speaker is not None:
                    VoiceTool._sapi_speaker.Speak("", 2)  # SPF_PURGEBEFORESPEAK
            except Exception as sapi_err:
                logger.debug("[SpeechController] SAPI fallback purge failed: %s", sapi_err)
                
        # 4. Clear audio recorder playback flags
        from voice.audio_recorder import AudioRecorder
        AudioRecorder.playback_active.clear()
        AudioRecorder.playback_finished_time = time.time()

        # 5. Join play thread if it's active
        if self._play_thread and self._play_thread.is_alive():
            self._play_thread.join(timeout=0.3)
            
        # 6. Reset stop_event only after cleanup is done
        self.stop_event.clear()
        logger.info("[SpeechController] Central STOP cleanup complete.")

    def stop(self) -> None:
        """Permanently stop the SpeechController thread and clear the queue."""
        self.stop_event.set()
        with self._queue_lock:
            while not self.speech_queue.empty():
                try:
                    self.speech_queue.get_nowait()
                    self.speech_queue.task_done()
                except queue.Empty:
                    break
        if self._play_thread and self._play_thread.is_alive():
            self._play_thread.join(timeout=1.0)
