"""
tools/voice.py
--------------
Consolidated text-to-speech voice tool conforming to the BaseTool interface.
Synthesizes speech using edge-tts neural voices.
"""

import os
import sys
import platform
import subprocess
import tempfile
import uuid
import ctypes
import asyncio
import shutil
from typing import Any

from tools.base_tool import BaseTool, RiskLevel
from utils.logger import get_logger

logger = get_logger(__name__)


def get_voice_for_language(selected_language: str) -> str:
    """Centralized mapping of selected response language to neural voice."""
    lang = str(selected_language).strip().lower()
    mapping = {
        "en": "en-US-AriaNeural",
        "te": "te-IN-ShrutiNeural",
        "hi": "hi-IN-SwaraNeural",
        "ta": "ta-IN-PallaviNeural",
        "kn": "kn-IN-SapnaNeural",
        # For backward compatibility
        "english": "en-US-AriaNeural",
        "telugu": "te-IN-ShrutiNeural",
        "hindi": "hi-IN-SwaraNeural",
        "tamil": "ta-IN-PallaviNeural",
        "kannada": "kn-IN-SapnaNeural"
    }
    return mapping.get(lang, "en-US-AriaNeural")


class VoiceTool(BaseTool):
    """Consolidated text-to-speech voice synthesis tool using edge-tts neural voices."""

    # Class-level SAPI speaker cache (for English fallback)
    _sapi_speaker = None

    @property
    def name(self) -> str:
        return "voice_tts"

    @property
    def description(self) -> str:
        return (
            "Uses the system text-to-speech engine to speak out loud the provided text message. "
            "Use this to output spoken statements to the user."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text content to speak out loud.",
                }
            },
            "required": ["text"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    def _generate_audio_sync(self, text: str, voice: str, temp_file_path: str) -> None:
        import edge_tts
        communicate = edge_tts.Communicate(text, voice)
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, communicate.save(temp_file_path))
                future.result()
        else:
            loop.run_until_complete(communicate.save(temp_file_path))

    def execute(self, **kwargs: Any) -> str:
        text = kwargs.get("text", "").strip()
        # Strip any characters outside the Basic Multilingual Plane (BMP) to prevent SAPI hangs/crashes
        text = "".join(ch for ch in text if ord(ch) <= 0xFFFF).strip()
        if not text:
            return "Failure: No text content provided to speak."

        from core.language_session import LanguageSession
        session = LanguageSession()

        response_language = kwargs.get("response_language")
        if not response_language:
            response_language = "te" if kwargs.get("telugu_mode", False) else session.selected_language

        response_language = str(response_language).strip().lower()
        normal_map = {
            "en": "en", "english": "en",
            "te": "te", "telugu": "te",
            "hi": "hi", "hindi": "hi",
            "ta": "ta", "tamil": "ta",
            "kn": "kn", "kannada": "kn"
        }
        response_language = normal_map.get(response_language, "en")
        
        if response_language == session.selected_language:
            selected_voice = session.tts_voice
        else:
            selected_voice = get_voice_for_language(response_language)

        logger.info("[RESPONSE]")
        logger.info("Response language: %s", response_language)
        logger.info("[TTS]")
        logger.info("Voice: %s", selected_voice)

        lang_log_map = {
            "en": "english",
            "te": "telugu",
            "hi": "hindi",
            "ta": "tamil",
            "kn": "kannada"
        }
        log_lang = lang_log_map.get(response_language, response_language)
        logger.info("[VOICE-LANGUAGE] Selected Language: %s | Neural Voice: %s", log_lang, selected_voice)
        logger.info("[VOICE-LANGUAGE] telugu_mode=%s", response_language in ("te", "telugu"))
        logger.info("[VOICE-LANGUAGE] TTS input text: %s", text)

        os_platform = platform.system()

        from voice.audio_recorder import AudioRecorder
        AudioRecorder.playback_active.set()

        stop_event = kwargs.get("stop_event", None)
        if stop_event is None:
            stop_event = getattr(self, "stop_event", None)

        # Check if environment is test (pytest/CI) or if edge-tts should be mocked
        is_test_env = os.getenv("ENVIRONMENT") == "test"
        if is_test_env:
            logger.info("[TTS-MOCK] Bypassing actual audio output in test environment.")
            return f"Success: Spoke message out loud: '{text}'"

        import time
        import hashlib
        import threading
        
        request_id = uuid.uuid4().hex
        text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
        process_id = os.getpid()
        thread_id = threading.get_ident()

        generation_started = 0.0
        generation_completed = 0.0
        playback_started = 0.0
        playback_completed = 0.0
        fallback_used = False

        temp_audio_path = os.path.join(tempfile.gettempdir(), f"nova_tts_{request_id}.mp3")

        try:
            logger.info("Synthesizing speech via edge-tts voice=%s", selected_voice)
            generation_started = time.time()
            self._generate_audio_sync(text, selected_voice, temp_audio_path)
            generation_completed = time.time()
            
            if not os.path.exists(temp_audio_path) or os.path.getsize(temp_audio_path) == 0:
                raise RuntimeError("Failed to generate edge-tts speech audio file.")

            playback_started = time.time()
            # Play generated audio
            if os_platform == "Windows":
                winmm = ctypes.windll.winmm
                quoted_path = f'"{temp_audio_path}"'
                
                # Close any stale alias first
                winmm.mciSendStringW(ctypes.c_wchar_p("close my_mp3"), None, 0, 0)
                
                # Open audio file
                open_cmd = f"open {quoted_path} type mpegvideo alias my_mp3"
                ret = winmm.mciSendStringW(ctypes.c_wchar_p(open_cmd), None, 0, 0)
                if ret != 0:
                    raise RuntimeError(f"MCI failed to open MP3 file: error code {ret}")

                # Play asynchronously
                winmm.mciSendStringW(ctypes.c_wchar_p("play my_mp3"), None, 0, 0)

                # Poll and support interruption
                start_time = time.time()
                timeout = max(15.0, len(text) / 10.0)
                buffer = ctypes.create_unicode_buffer(256)
                
                while True:
                    if stop_event is not None and stop_event.is_set():
                        logger.info("[Watchdog] edge-tts TTS playback cancelled mid-speak.")
                        winmm.mciSendStringW(ctypes.c_wchar_p("stop my_mp3"), None, 0, 0)
                        winmm.mciSendStringW(ctypes.c_wchar_p("close my_mp3"), None, 0, 0)
                        playback_completed = time.time()
                        logger.info(
                            "\n[TTS-TRACE]\n"
                            "request_id=%s\n"
                            "response_language=%s\n"
                            "selected_voice=%s\n"
                            "text_hash=%s\n"
                            "audio_path=%s\n"
                            "generation_started=%.6f\n"
                            "generation_completed=%.6f\n"
                            "playback_started=%.6f\n"
                            "playback_completed=%.6f\n"
                            "fallback_used=%s\n"
                            "process_id=%d\n"
                            "thread_id=%d",
                            request_id, response_language, selected_voice, text_hash, temp_audio_path,
                            generation_started, generation_completed, playback_started, playback_completed,
                            str(fallback_used), process_id, thread_id
                        )
                        return "Failure: Spoke message cancelled."
                    
                    if time.time() - start_time > timeout:
                        logger.warning("[Watchdog] edge-tts playback timed out.")
                        winmm.mciSendStringW(ctypes.c_wchar_p("stop my_mp3"), None, 0, 0)
                        winmm.mciSendStringW(ctypes.c_wchar_p("close my_mp3"), None, 0, 0)
                        break

                    winmm.mciSendStringW(ctypes.c_wchar_p("status my_mp3 mode"), buffer, 256, 0)
                    if buffer.value != "playing":
                        break
                    time.sleep(0.05)

                winmm.mciSendStringW(ctypes.c_wchar_p("close my_mp3"), None, 0, 0)

            elif os_platform == "Darwin":  # macOS
                proc = subprocess.Popen(["afplay", temp_audio_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                while proc.poll() is None:
                    if stop_event is not None and stop_event.is_set():
                        logger.info("[Watchdog] edge-tts TTS synthesis cancelled mid-speak.")
                        proc.terminate()
                        try:
                            proc.wait(timeout=1.0)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                        playback_completed = time.time()
                        logger.info(
                            "\n[TTS-TRACE]\n"
                            "request_id=%s\n"
                            "response_language=%s\n"
                            "selected_voice=%s\n"
                            "text_hash=%s\n"
                            "audio_path=%s\n"
                            "generation_started=%.6f\n"
                            "generation_completed=%.6f\n"
                            "playback_started=%.6f\n"
                            "playback_completed=%.6f\n"
                            "fallback_used=%s\n"
                            "process_id=%d\n"
                            "thread_id=%d",
                            request_id, response_language, selected_voice, text_hash, temp_audio_path,
                            generation_started, generation_completed, playback_started, playback_completed,
                            str(fallback_used), process_id, thread_id
                        )
                        return "Failure: Spoke message cancelled."
                    time.sleep(0.05)

            elif os_platform == "Linux":
                # Play using aplay, paplay, mpg123, or play
                player_cmd = None
                for cmd in ["paplay", "mpg123", "play", "ffplay", "aplay"]:
                    if shutil.which(cmd):
                        player_cmd = cmd
                        break
                
                if player_cmd:
                    args = [player_cmd, temp_audio_path]
                    if player_cmd == "ffplay":
                        args.extend(["-nodisp", "-autoexit"])
                    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    while proc.poll() is None:
                        if stop_event is not None and stop_event.is_set():
                            logger.info("[Watchdog] edge-tts TTS synthesis cancelled mid-speak.")
                            proc.terminate()
                            try:
                                proc.wait(timeout=1.0)
                            except subprocess.TimeoutExpired:
                                proc.kill()
                            playback_completed = time.time()
                            logger.info(
                                "\n[TTS-TRACE]\n"
                                "request_id=%s\n"
                                "response_language=%s\n"
                                "selected_voice=%s\n"
                                "text_hash=%s\n"
                                "audio_path=%s\n"
                                "generation_started=%.6f\n"
                                "generation_completed=%.6f\n"
                                "playback_started=%.6f\n"
                                "playback_completed=%.6f\n"
                                "fallback_used=%s\n"
                                "process_id=%d\n"
                                "thread_id=%d",
                                request_id, response_language, selected_voice, text_hash, temp_audio_path,
                                generation_started, generation_completed, playback_started, playback_completed,
                                str(fallback_used), process_id, thread_id
                            )
                            return "Failure: Spoke message cancelled."
                        time.sleep(0.05)
                else:
                    logger.warning("No audio player command found on Linux system.")

            else:
                logger.warning("Unsupported platform for edge-tts playback.")

            playback_completed = time.time()
            logger.info(
                "\n[TTS-TRACE]\n"
                "request_id=%s\n"
                "response_language=%s\n"
                "selected_voice=%s\n"
                "text_hash=%s\n"
                "audio_path=%s\n"
                "generation_started=%.6f\n"
                "generation_completed=%.6f\n"
                "playback_started=%.6f\n"
                "playback_completed=%.6f\n"
                "fallback_used=%s\n"
                "process_id=%d\n"
                "thread_id=%d",
                request_id, response_language, selected_voice, text_hash, temp_audio_path,
                generation_started, generation_completed, playback_started, playback_completed,
                str(fallback_used), process_id, thread_id
            )
            return f"Success: Spoke message out loud: '{text}'"

        except Exception as e:
            fallback_used = True
            logger.exception("Error executing neural edge-tts: %s", e)
            
            if os_platform == "Windows":
                is_english = response_language in ("en", "english")
                try:
                    if VoiceTool._sapi_speaker is None:
                        import win32com.client
                        VoiceTool._sapi_speaker = win32com.client.Dispatch("SAPI.SpVoice")
                        logger.info("[TTS] Fallback SAPI SpVoice initialized and cached.")
                    speaker = VoiceTool._sapi_speaker
                    
                    voices = speaker.GetVoices()
                    selected_voice_obj = None
                    for i in range(len(voices)):
                        v = voices.Item(i)
                        lang_attr = v.GetAttribute("Language")
                        desc = v.GetDescription().lower()
                        
                        if is_english:
                            if lang_attr == "409" or "english" in desc or "en-us" in desc:
                                selected_voice_obj = v
                                break
                        else:
                            lang_mapping = {
                                "te": "44a", "telugu": "44a",
                                "hi": "439", "hindi": "439",
                                "ta": "449", "tamil": "449",
                                "kn": "44b", "kannada": "44b"
                            }
                            target_code = lang_mapping.get(response_language, "unknown_code")
                            if lang_attr == target_code or response_language in desc:
                                selected_voice_obj = v
                                break
                    
                    if selected_voice_obj:
                        logger.info("Falling back to local Windows SAPI voice: %s", selected_voice_obj.GetDescription())
                        speaker.Voice = selected_voice_obj
                        playback_started = time.time()
                        speaker.Speak(text, 1)
                        
                        start_time = time.time()
                        timeout = max(15.0, len(text) / 10.0)
                        while True:
                            if stop_event is not None and stop_event.is_set():
                                logger.info("[Watchdog] SAPI Fallback synthesis cancelled.")
                                speaker.Speak("", 2)
                                playback_completed = time.time()
                                logger.info(
                                    "\n[TTS-TRACE]\n"
                                    "request_id=%s\n"
                                    "response_language=%s\n"
                                    "selected_voice=%s\n"
                                    "text_hash=%s\n"
                                    "audio_path=%s\n"
                                    "generation_started=%.6f\n"
                                    "generation_completed=%.6f\n"
                                    "playback_started=%.6f\n"
                                    "playback_completed=%.6f\n"
                                    "fallback_used=%s\n"
                                    "process_id=%d\n"
                                    "thread_id=%d",
                                    request_id, response_language, selected_voice, text_hash, temp_audio_path,
                                    generation_started, generation_completed, playback_started, playback_completed,
                                    str(fallback_used), process_id, thread_id
                                )
                                return "Failure: Spoke message cancelled."
                            if time.time() - start_time > timeout:
                                speaker.Speak("", 2)
                                break
                            try:
                                if speaker.Status.RunningState == 0:
                                    break
                            except Exception:
                                break
                            time.sleep(0.05)
                            
                        playback_completed = time.time()
                        logger.info(
                            "\n[TTS-TRACE]\n"
                            "request_id=%s\n"
                            "response_language=%s\n"
                            "selected_voice=%s\n"
                            "text_hash=%s\n"
                            "audio_path=%s\n"
                            "generation_started=%.6f\n"
                            "generation_completed=%.6f\n"
                            "playback_started=%.6f\n"
                            "playback_completed=%.6f\n"
                            "fallback_used=%s\n"
                            "process_id=%d\n"
                            "thread_id=%d",
                            request_id, response_language, selected_voice, text_hash, temp_audio_path,
                            generation_started, generation_completed, playback_started, playback_completed,
                            str(fallback_used), process_id, thread_id
                        )
                        return f"Success: Spoke message out loud (SAPI fallback): '{text}'"
                    else:
                        logger.warning("No Telugu-capable SAPI voice" if not is_english else "No English-capable SAPI voice")
                        if not is_english:
                            playback_completed = time.time()
                            logger.info(
                                "\n[TTS-TRACE]\n"
                                "request_id=%s\n"
                                "response_language=%s\n"
                                "selected_voice=%s\n"
                                "text_hash=%s\n"
                                "audio_path=%s\n"
                                "generation_started=%.6f\n"
                                "generation_completed=%.6f\n"
                                "playback_started=%.6f\n"
                                "playback_completed=%.6f\n"
                                "fallback_used=%s\n"
                                "process_id=%d\n"
                                "thread_id=%d",
                                request_id, response_language, selected_voice, text_hash, temp_audio_path,
                                generation_started, generation_completed, playback_started, playback_completed,
                                str(fallback_used), process_id, thread_id
                            )
                            return f"Failure executing text-to-speech: No Telugu-capable SAPI voice"
                except Exception as sapi_err:
                    logger.error("SAPI Fallback failed: %s", sapi_err)
            
            # Non-English failure
            playback_completed = time.time()
            logger.info(
                "\n[TTS-TRACE]\n"
                "request_id=%s\n"
                "response_language=%s\n"
                "selected_voice=%s\n"
                "text_hash=%s\n"
                "audio_path=%s\n"
                "generation_started=%.6f\n"
                "generation_completed=%.6f\n"
                "playback_started=%.6f\n"
                "playback_completed=%.6f\n"
                "fallback_used=%s\n"
                "process_id=%d\n"
                "thread_id=%d",
                request_id, response_language, selected_voice, text_hash, temp_audio_path,
                generation_started, generation_completed, playback_started, playback_completed,
                str(fallback_used), process_id, thread_id
            )
            return f"Failure executing text-to-speech: {e}"

        finally:
            # Clean up temp file
            try:
                if os.path.exists(temp_audio_path):
                    os.unlink(temp_audio_path)
            except Exception:
                pass
            import time
            AudioRecorder.playback_finished_time = time.time()
            AudioRecorder.playback_active.clear()
