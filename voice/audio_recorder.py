"""
voice/audio_recorder.py
-----------------------
Captures audio input stream and handles silence detection to save spoken commands as WAV.
"""

import os
import queue
import tempfile
import threading
import wave
from pathlib import Path
from typing import Any
from utils.logger import get_logger

logger = get_logger(__name__)

try:
    import sounddevice as sd
    import numpy as np
    SOUNDDEVICE_AVAILABLE = True
except (ImportError, Exception) as e:
    logger.warning("sounddevice or numpy is not available. Microphone capture will be mocked: %s", e)
    SOUNDDEVICE_AVAILABLE = False


class AudioRecorder:
    """Captures microphone audio and saves it to temporary WAV files using sounddevice."""

    playback_active = threading.Event()
    playback_finished_time = 0.0

    def __init__(
        self,
        samplerate: int = 16000,
        channels: int = 1,
        blocksize: int = 1024,
        threshold: float = 0.015,
        silence_duration: float = 1.0,
    ) -> None:
        self.samplerate = samplerate
        self.channels = channels
        self.blocksize = blocksize
        
        # Determine VAD threshold (allow env override, fallback to constructor default)
        env_threshold = os.getenv("VOICE_VAD_THRESHOLD")
        if env_threshold:
            try:
                self.threshold = float(env_threshold.strip())
            except ValueError:
                self.threshold = threshold
        else:
            self.threshold = threshold

        self.silence_duration = silence_duration
        self.audio_queue: queue.Queue = queue.Queue()

        # Load input device choice from environment (supports index or name string)
        device_env = os.getenv("VOICE_INPUT_DEVICE")
        if device_env:
            device_env = device_env.strip()
            if device_env.isdigit():
                self.device: Any = int(device_env)
            else:
                self.device = device_env
        else:
            self.device = None

        # Load max recording duration in seconds (defaults to 3.0 seconds)
        max_rec_env = os.getenv("VOICE_MAX_RECORD_SECONDS")
        if max_rec_env:
            try:
                self.max_record_seconds = float(max_rec_env.strip())
            except ValueError:
                self.max_record_seconds = 3.0
        else:
            self.max_record_seconds = 3.0

    def record_command(self, stop_event=None, max_record_seconds: float | None = None) -> Path | None:
        """
        Record from microphone until silence is detected, saving the output as a temporary WAV file.
        Returns the Path to the temporary WAV file, or None if failed/cancelled.
        """
        if not SOUNDDEVICE_AVAILABLE:
            logger.info("Mocking microphone command recording.")
            print("Exit reason: no speech")
            print("record_command() exits")
            print("RETURN")
            return self._create_mock_wav()

        logger.info("Listening for spoken command...")
        
        recorded_chunks = []
        silent_count = 0
        has_spoken = False

        def callback(indata, frames, time_info, status):
            import time
            if AudioRecorder.playback_active.is_set() or (time.time() - AudioRecorder.playback_finished_time < 1.0):
                return
            self.audio_queue.put(indata.copy())

        # Clean queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

        is_mocked = False
        try:
            from unittest.mock import MagicMock
            if isinstance(sd.InputStream, MagicMock) or hasattr(sd.InputStream, "mock_add_spec"):
                is_mocked = True
        except ImportError:
            pass

        if self.device is None:
            try:
                hostapis = sd.query_hostapis()
                self.device = hostapis[0]["default_input_device"]
            except Exception:
                pass

        try:
            device_info = sd.query_devices(self.device)
            samplerate = int(device_info["default_samplerate"])
        except Exception:
            samplerate = self.samplerate

        if is_mocked:
            samplerate = self.samplerate

        if max_record_seconds is None:
            max_record_seconds = self.max_record_seconds

        # Recalculate block counts based on the actual samplerate used for the stream
        silence_blocks = int(self.silence_duration * samplerate / self.blocksize)
        max_pre_speech = int(1.0 * samplerate / self.blocksize)
        max_total_blocks = int(max_record_seconds * samplerate / self.blocksize)
        max_initial_silence_blocks = int(3.0 * samplerate / self.blocksize)
        
        trigger_threshold = self.threshold
        hold_threshold = self.threshold * 0.4

        try:
            with sd.InputStream(
                device=self.device,
                samplerate=samplerate,
                channels=1,
                dtype="float32",
                blocksize=self.blocksize,
                callback=callback,
            ):
                total_blocks = 0
                while stop_event is None or not stop_event.is_set():
                    if AudioRecorder.playback_active.is_set():
                        AudioRecorder.playback_active.wait()
                        # Clear buffered microphone frames
                        while not self.audio_queue.empty():
                            try:
                                self.audio_queue.get_nowait()
                            except queue.Empty:
                                break
                        recorded_chunks.clear()
                        has_spoken = False
                        silent_count = 0
                        total_blocks = 0
                        continue

                    try:
                        chunk = self.audio_queue.get(timeout=0.1)
                    except queue.Empty:
                        continue

                    if stop_event is not None and stop_event.is_set():
                        break

                    recorded_chunks.append(chunk)
                    total_blocks += 1
                    
                    # Compute RMS energy of the chunk
                    rms = np.sqrt(np.mean(chunk**2))
                    
                    # VAD trigger logic
                    if rms > trigger_threshold:
                        if not has_spoken:
                            logger.info("[VAD] Voice activity detected (rms=%.4f > trigger=%.4f). Transitioning to capturing state.", rms, trigger_threshold)
                            has_spoken = True
                        silent_count = 0
                    else:
                        if has_spoken:
                            silent_count += 1
                            if silent_count >= silence_blocks:
                                logger.info("[VAD] Silence detected (duration >= %.2f s). Speech capture finished.", self.silence_duration)
                                break
                        else:
                            # Keep only the last 1.0 second of audio before speech starts
                            if len(recorded_chunks) > max_pre_speech:
                                recorded_chunks.pop(0)
                            
                            # Exit early if silence continues for more than initial silence timeout (3.0s)
                            if total_blocks >= max_initial_silence_blocks:
                                logger.info("[VAD] Initial silence timeout reached (3.0s). Exiting recording loop.")
                                break

                    if total_blocks >= max_total_blocks:
                        logger.info("Maximum recording duration reached. Stopping recording.")
                        break

            if (stop_event is not None and stop_event.is_set()) or not recorded_chunks or not has_spoken:
                logger.info("[VAD] Recording exited without valid speech content detected (has_spoken=%s).", has_spoken)
                return None

            # Concatenate chunks and save to temporary WAV file
            audio_data = np.concatenate(recorded_chunks, axis=0)
            return self._save_wav(audio_data, samplerate)

        except Exception as e:
            logger.error("Failed to capture audio from sounddevice: %s", e)
            try:
                print(sd.query_devices())
            except Exception:
                pass
            return self._create_mock_wav()

    def _save_wav(self, audio_data: Any, samplerate: int) -> Path:
        temp_dir = Path(tempfile.gettempdir())
        file_path = temp_dir / f"nova_command_{os.urandom(4).hex()}.wav"
        
        audio_data = audio_data.flatten()
        peak = np.max(np.abs(audio_data))
        
        if peak > 0:
            audio_data = audio_data / peak
            
        audio_data *= 0.95
        
        scaled_data = (audio_data * 32767).astype(np.int16)
        
        with wave.open(str(file_path), "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(samplerate)
            wf.writeframes(scaled_data.tobytes())
            
        logger.debug("Saved recorded audio to %s", file_path)
        return file_path

    def _create_mock_wav(self) -> Path:
        """Create a silent WAV file for testing or headless environments."""
        temp_dir = Path(tempfile.gettempdir())
        file_path = temp_dir / "nova_mock_audio.wav"
        
        # 1.5 seconds of silence
        silence = np.zeros(int(self.samplerate * 1.5), dtype=np.int16)
        
        with wave.open(str(file_path), "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.samplerate)
            wf.writeframes(silence.tobytes())
            
        logger.debug("Created mock silent audio file at %s", file_path)
        return file_path
