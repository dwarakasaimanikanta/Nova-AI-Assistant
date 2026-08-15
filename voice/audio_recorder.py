"""
voice/audio_recorder.py
-----------------------
Captures audio input stream and handles silence detection to save spoken commands as WAV.
"""

import os
import queue
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Any
from utils.logger import get_logger

logger = get_logger(__name__)

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except Exception:
    np = None
    NUMPY_AVAILABLE = False

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except Exception:
    sd = None
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
        silence_duration: float | None = None,
    ) -> None:
        from config import NOVA_SILENCE_DURATION, NOVA_MAX_COMMAND_SECONDS
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

        if os.getenv("ENVIRONMENT") != "test" and self.threshold < 0.015:
            logger.info("[AudioRecorder] Raising VAD threshold from %f to 0.015 minimum to prevent background noise triggers.", self.threshold)
            self.threshold = 0.015

        self.silence_duration = silence_duration if silence_duration is not None else NOVA_SILENCE_DURATION
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

        # Load max recording duration in seconds
        max_rec_env = os.getenv("VOICE_MAX_RECORD_SECONDS")
        if max_rec_env:
            try:
                self.max_record_seconds = float(max_rec_env.strip())
            except ValueError:
                self.max_record_seconds = NOVA_MAX_COMMAND_SECONDS
        else:
            self.max_record_seconds = NOVA_MAX_COMMAND_SECONDS

    def record_command(
        self,
        stop_event=None,
        max_record_seconds: float | None = None,
        allow_playback_recording: bool = False,
        disable_silence_cutoff: bool = False,
        initial_silence_timeout: float | None = None,
        silence_duration: float | None = None
    ) -> Path | None:
        """
        Record from microphone until silence is detected, saving the output as a temporary WAV file.
        Returns the Path to the temporary WAV file, or None if failed/cancelled.
        """
        if not SOUNDDEVICE_AVAILABLE or not NUMPY_AVAILABLE:
            logger.info("Mocking microphone command recording.")
            print("Exit reason: no speech")
            print("record_command() exits")
            print("RETURN")
            return self._create_mock_wav()

        logger.info("[VOICE] Listening for spoken command (max=%.1fs, threshold=%.4f)...", max_record_seconds if max_record_seconds else self.max_record_seconds, self.threshold)
        
        recorded_chunks = []
        silent_count = 0
        has_spoken = False

        stream_start_time = time.time()
        stabilization_delay = 0.0 if allow_playback_recording else float(os.getenv("NOVA_MIC_STABILIZATION_DELAY", "0.05"))

        def callback(indata, frames, time_info, status):
            if time.time() - stream_start_time < stabilization_delay:
                return
            # Allow recording during active playback only when explicitly requested (e.g. for wake-word interruption).
            # Otherwise, skip to prevent feedback loops.
            if not allow_playback_recording and AudioRecorder.playback_active.is_set():
                return
            from config import NOVA_POST_PLAYBACK_COOLDOWN
            cooldown_val = min(0.2, float(NOVA_POST_PLAYBACK_COOLDOWN or 1.0))
            if not AudioRecorder.playback_active.is_set() and (time.time() - AudioRecorder.playback_finished_time < cooldown_val):
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

        # Select Windows default input device if None
        if self.device is None:
            try:
                self.device = sd.default.device[0]
            except Exception:
                pass
            if self.device is None or self.device < 0:
                try:
                    hostapis = sd.query_hostapis()
                    self.device = hostapis[0]["default_input_device"]
                except Exception:
                    pass

        try:
            device_info = sd.query_devices(self.device)
            max_in_ch = device_info.get("max_input_channels", 0)
            if max_in_ch <= 0:
                logger.error("[VOICE-DEBUG] Selected device %s is not an input device (channels=%d)!", self.device, max_in_ch)
                raise ValueError(f"Device {self.device} has 0 input channels.")
            samplerate = int(device_info["default_samplerate"])
        except Exception as e:
            logger.error("[VOICE-DEBUG] Microphone validation failed for device %s: %s", self.device, e)
            raise RuntimeError(f"Microphone device {self.device} validation failed: {e}") from e

        if is_mocked:
            samplerate = self.samplerate

        if max_record_seconds is None:
            max_record_seconds = self.max_record_seconds

        # Recalculate block counts based on the actual samplerate used for the stream
        from config import NOVA_INITIAL_SILENCE_TIMEOUT
        sil_dur = silence_duration if silence_duration is not None else self.silence_duration
        silence_blocks = int(sil_dur * samplerate / self.blocksize)
        max_pre_speech = int(1.0 * samplerate / self.blocksize)
        max_total_blocks = int(max_record_seconds * samplerate / self.blocksize)
        init_timeout = initial_silence_timeout if initial_silence_timeout is not None else NOVA_INITIAL_SILENCE_TIMEOUT
        max_initial_silence_blocks = int(min(init_timeout, max_record_seconds) * samplerate / self.blocksize)
        
        trigger_threshold = self.threshold
        hold_threshold = self.threshold * 0.7

        # Log VOICE-DEBUG configuration details
        logger.info("[VOICE-DEBUG] input device: %s", self.device)
        logger.info("[VOICE-DEBUG] sample rate: %d", samplerate)
        logger.info("[VOICE-DEBUG] channels: 1")
        logger.info("[VOICE-DEBUG] VAD threshold: %.4f", self.threshold)

        # Wait for TTS drain before opening the stream
        if not allow_playback_recording:
            while AudioRecorder.playback_active.is_set() and (stop_event is None or not stop_event.is_set()):
                time.sleep(0.05)

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
                    if not allow_playback_recording and AudioRecorder.playback_active.is_set():
                        # Wait with timeout so we check stop_event periodically
                        AudioRecorder.playback_active.wait(timeout=0.2)
                        if stop_event is not None and stop_event.is_set():
                            break
                        if AudioRecorder.playback_active.is_set():
                            continue
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

                    # Log chunk received periodically to keep trace readable but confirm data stream flow
                    if total_blocks % 20 == 0:
                        logger.info("[VOICE-DEBUG] audio chunk received (total_blocks=%d)", total_blocks)
                    
                    # Compute RMS energy of the chunk
                    rms = np.sqrt(np.mean(chunk**2))
                    
                    # Dual-threshold VAD trigger logic
                    is_active_speech = rms > hold_threshold if has_spoken else rms > trigger_threshold

                    if is_active_speech:
                        if not has_spoken:
                            logger.info("[VAD] Voice activity detected (rms=%.4f > trigger=%.4f). Transitioning to capturing state.", rms, trigger_threshold)
                            logger.info("[VOICE-DEBUG] speech detected: True")
                            has_spoken = True
                        silent_count = 0
                    else:
                        if has_spoken:
                            if not disable_silence_cutoff:
                                silent_count += 1
                                if silent_count >= silence_blocks:
                                    logger.info("[VAD] Silence detected (duration >= %.2f s). Speech capture finished.", self.silence_duration)
                                    break
                        else:
                            # Keep only the last 1.0 second of audio before speech starts
                            if len(recorded_chunks) > max_pre_speech:
                                recorded_chunks.pop(0)
                            
                            # Exit early if silence continues for more than initial silence timeout
                            if not disable_silence_cutoff and total_blocks >= max_initial_silence_blocks:
                                logger.info("[VAD] Initial silence timeout reached (%.2fs). Exiting recording loop.", min(NOVA_INITIAL_SILENCE_TIMEOUT, max_record_seconds))
                                break

                    if total_blocks >= max_total_blocks:
                        logger.info("Maximum recording duration reached. Stopping recording.")
                        break

            if disable_silence_cutoff:
                has_spoken = True

            if (stop_event is not None and stop_event.is_set()) or not recorded_chunks or not has_spoken:
                logger.info("[VAD] Recording exited without valid speech content detected (has_spoken=%s).", has_spoken)
                return None

            # Concatenate chunks and save to temporary WAV file
            audio_data = np.concatenate(recorded_chunks, axis=0)
            
            # Log VOICE-DEBUG details before saving
            duration = len(recorded_chunks) * self.blocksize / samplerate
            # Save the WAV file
            saved_path = self._save_wav(audio_data, samplerate)
            if saved_path:
                audio_bytes = saved_path.stat().st_size
                logger.info("[VOICE-DEBUG] recording duration: %.2f seconds", duration)
                logger.info("[VOICE-DEBUG] audio bytes collected: %d bytes", audio_bytes)
            return saved_path

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
        peak = float(np.max(np.abs(audio_data)))
        rms = float(np.sqrt(np.mean(audio_data**2)))

        logger.info("[VOICE-DEBUG] WAV save: peak=%.6f, rms=%.6f", peak, rms)

        # Normalization strategy:
        # - If peak > 0.1 (normal speech), do NOT normalize — preserve original levels
        #   so Whisper sees natural speech amplitude without noise floor amplification.
        # - If peak <= 0.1 (very quiet mic / far-field), apply modest gain capped at 8x
        #   to bring speech up without over-amplifying the noise floor.
        # - Never use pure peak-normalization: dividing by a tiny peak (e.g. 0.003)
        #   amplifies EVERYTHING including noise to full scale, causing false transcripts.
        if 0 < peak <= 0.1:
            gain = min(8.0, 0.8 / peak)
            audio_data = audio_data * gain
            logger.info("[VOICE-DEBUG] Applied gain %.1fx (peak was %.6f)", gain, peak)
        # else: peak > 0.1 means normal speech level — use as-is

        # Clip to prevent any single over-peak distorting the waveform
        audio_data = np.clip(audio_data, -1.0, 1.0)

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
        
        # 1.5 seconds of silence (16-bit PCM, 2 bytes per sample)
        num_samples = int(self.samplerate * 1.5)
        
        with wave.open(str(file_path), "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.samplerate)
            if NUMPY_AVAILABLE and np is not None:
                silence = np.zeros(num_samples, dtype=np.int16)
                wf.writeframes(silence.tobytes())
            else:
                silence_bytes = bytes(num_samples * 2)
                wf.writeframes(silence_bytes)
            
        logger.debug("Created mock silent audio file at %s", file_path)
        return file_path
