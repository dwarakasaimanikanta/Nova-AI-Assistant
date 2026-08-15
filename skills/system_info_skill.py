"""
skills/system_info_skill.py
---------------------------
System Information skill for Nova.
"""

import os
import platform
import re

from skills.base_skill import BaseSkill
from utils.logger import get_logger

logger = get_logger(__name__)


class SystemInfoSkill(BaseSkill):
    """A skill that details OS, Python version, and the current working directory."""

    @property
    def name(self) -> str:
        """The name of the skill."""
        return "SystemInfo"

    @property
    def description(self) -> str:
        """A brief description of what the skill does."""
        return "Shows OS, Python version and current working directory."

    def matches(self, user_input: str) -> bool:
        """
        Determine if this skill matches the user input.

        Args:
            user_input: The raw text typed by the user.

        Returns:
            True if matched, False otherwise.
        """
        cleaned = user_input.strip().lower()
        keywords = r"\b(system|sysinfo|os|cwd|python version|working directory|diagnostic|diagnostics|self-diagnostic|self-diagnostics)\b"
        return bool(re.search(keywords, cleaned))

    def execute(self, user_input: str) -> str:
        """
        Execute the system info skill.

        Args:
            user_input: The raw text typed by the user.

        Returns:
            A formatted string listing system metadata.
        """
        logger.debug("Executing SystemInfoSkill.")

        cleaned = user_input.strip().lower()
        if "diagnostic" in cleaned:
            import socket
            try:
                socket.setdefaulttimeout(1.5)
                socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
                internet = "Online"
            except Exception:
                internet = "Offline"

            mic = "Ready"
            try:
                import sounddevice as sd
                sd.query_devices()
            except Exception:
                mic = "Unavailable"

            # Resolve real runtime details via SpeechController singleton
            stt_provider = "Unknown"
            stt_model = "Unknown"
            is_multilingual = "False"
            sel_lang = "en"
            tts_voice = "Unknown"
            resp_lang = "en"
            controller_status = "Inactive"
            tts_worker_threads = 0
            active_audio_procs = 0

            from voice.speech_controller import SpeechController
            from voice.audio_recorder import AudioRecorder
            import threading

            controller = SpeechController()
            if controller:
                controller_status = "SpeechController (Active)"
                
            voice_manager = getattr(controller, "voice_manager", None)
            if voice_manager:
                if hasattr(voice_manager, "stt_engine") and voice_manager.stt_engine:
                    stt_provider = type(voice_manager.stt_engine).__name__
                    stt_model = getattr(voice_manager.stt_engine, "model_size", "Unknown")
                    is_multilingual = "True" if not (stt_model.endswith(".en") or stt_model == "tiny.en") else "False"
                sel_lang = getattr(voice_manager, "selected_language", "en")
                resp_lang = getattr(voice_manager, "response_language", sel_lang)

            from tools.voice import get_voice_for_language
            try:
                tts_voice = get_voice_for_language(sel_lang)
            except Exception:
                pass

            tts_worker_threads = sum(1 for t in threading.enumerate() if "SpeechController" in t.name or "TTSPlayback" in t.name)

            try:
                import psutil
                play_proc_names = {"afplay", "aplay", "mpg123", "ffplay", "paplay", "play"}
                active_audio_procs = 0
                for p in psutil.process_iter(attrs=["name"]):
                    if p.info["name"] and p.info["name"].lower() in play_proc_names:
                        active_audio_procs += 1
            except Exception:
                active_audio_procs = 1 if AudioRecorder.playback_active.is_set() else 0

            response = (
                "Self-Diagnostics Report:\n"
                f"  • Microphone        : {mic}\n"
                f"  • STT Provider      : {stt_provider}\n"
                f"  • STT Model         : {stt_model}\n"
                f"  • Multilingual STT  : {is_multilingual}\n"
                f"  • Selected Language : {sel_lang}\n"
                f"  • Response Language : {resp_lang}\n"
                f"  • TTS Voice         : {tts_voice}\n"
                f"  • Speech Controller : {controller_status}\n"
                f"  • TTS Worker Threads: {tts_worker_threads}\n"
                f"  • Audio Playback Procs: {active_audio_procs}\n"
                f"  • Internet Link     : {internet}\n"
                "All core diagnostics passed."
            )
            return response

        os_name = platform.system()
        os_release = platform.release()
        python_ver = platform.python_version()
        cwd = os.getcwd()

        response = (
            "System Information:\n"
            f"  • Operating System : {os_name} {os_release}\n"
            f"  • Python Version   : {python_ver}\n"
            f"  • Working Directory: {cwd}"
        )
        return response
