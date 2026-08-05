"""
voice/audio_recorder.py
-----------------------
Captures audio input stream and handles silence detection to save spoken commands as WAV.
"""

import os
import queue
import tempfile
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

    def __init__(
        self,
        samplerate: int = 16000,
        channels: int = 1,
        blocksize: int = 1024,
        threshold: float = 0.015,
        silence_duration: float = 1.5,
    ) -> None:
        self.samplerate = samplerate
        self.channels = channels
        self.blocksize = blocksize
        self.threshold = threshold
        self.silence_duration = silence_duration
        self.audio_queue: queue.Queue = queue.Queue()

    def record_command(self, stop_event=None) -> Path | None:
        """
        Record from microphone until silence is detected, saving the output as a temporary WAV file.
        Returns the Path to the temporary WAV file, or None if failed/cancelled.
        """
        if not SOUNDDEVICE_AVAILABLE:
            logger.info("Mocking microphone command recording.")
            return self._create_mock_wav()

        logger.info("Listening for spoken command...")
        
        recorded_chunks = []
        silence_blocks = int(self.silence_duration * self.samplerate / self.blocksize)
        silent_count = 0
        has_spoken = False

        def callback(indata, frames, time, status):
            if status:
                logger.warning("PortAudio status warning: %s", status)
            self.audio_queue.put(indata.copy())

        # Clean queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

        try:
            with sd.InputStream(
                samplerate=self.samplerate,
                channels=self.channels,
                blocksize=self.blocksize,
                callback=callback
            ):
                while stop_event is None or not stop_event.is_set():
                    try:
                        chunk = self.audio_queue.get(timeout=0.1)
                    except queue.Empty:
                        continue

                    recorded_chunks.append(chunk)
                    
                    # Compute RMS energy of the chunk
                    rms = np.sqrt(np.mean(chunk**2))
                    
                    if rms > self.threshold:
                        if not has_spoken:
                            logger.info("Voice activity detected, capturing command...")
                            has_spoken = True
                        silent_count = 0
                    else:
                        if has_spoken:
                            silent_count += 1
                            if silent_count >= silence_blocks:
                                logger.info("Silence detected. Speech capture finished.")
                                break
                        else:
                            # Keep only the last 1.0 second of audio before speech starts
                            max_pre_speech = int(1.0 * self.samplerate / self.blocksize)
                            if len(recorded_chunks) > max_pre_speech:
                                recorded_chunks.pop(0)

            if not recorded_chunks or not has_spoken:
                return None

            # Concatenate chunks and save to temporary WAV file
            audio_data = np.concatenate(recorded_chunks, axis=0)
            return self._save_wav(audio_data)

        except Exception as e:
            logger.error("Failed to capture audio from sounddevice: %s", e)
            return self._create_mock_wav()

    def _save_wav(self, audio_data: Any) -> Path:
        temp_dir = Path(tempfile.gettempdir())
        file_path = temp_dir / f"nova_command_{os.urandom(4).hex()}.wav"
        
        # Scale float32 normalized samples to 16-bit PCM integer values
        scaled_data = (audio_data * 32767).astype(np.int16)
        
        with wave.open(str(file_path), "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(self.samplerate)
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
