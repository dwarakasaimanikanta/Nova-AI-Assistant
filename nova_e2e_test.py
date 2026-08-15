import sounddevice as sd
import numpy as np
import wave
from faster_whisper import WhisperModel
from nova_command_router import execute_command

RATE = 16000
DURATION = 5
DEVICE = 1
AUDIO_FILE = "scratch_voice_command.wav"

print("========================================")
print("NOVA END-TO-END VOICE TEST")
print("Say: Hey Nova, close Notepad")
print("========================================")

audio = sd.rec(
    int(RATE * DURATION),
    samplerate=RATE,
    channels=1,
    dtype="int16",
    device=DEVICE
)

sd.wait()

with wave.open(AUDIO_FILE, "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(RATE)
    wf.writeframes(np.asarray(audio).tobytes())

print("Audio recorded.")
print("Loading Whisper...")

model = WhisperModel(
    "base",
    device="cpu",
    compute_type="int8"
)

segments, info = model.transcribe(
    AUDIO_FILE,
    beam_size=5,
    vad_filter=False
)

transcript = " ".join(
    s.text.strip() for s in segments
).strip()

print("Detected language:", info.language)
print("Transcript:", repr(transcript))

if not transcript:
    print("ERROR: EMPTY TRANSCRIPT")
    raise SystemExit(1)

print("Sending transcript to Ollama...")

import subprocess

prompt = f"""You are NOVA's deterministic command parser.

Return ONLY one line.

Allowed intents: OPEN, CLOSE
Allowed targets: YOUTUBE, NOTEPAD

Required format:
INTENT=OPEN|TARGET=YOUTUBE
or
INTENT=CLOSE|TARGET=NOTEPAD

Never explain.
Never add punctuation.

User said:
{transcript}
"""

result = subprocess.run(
    ["ollama", "run", "llama3.2:3b", prompt],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace"
)

intent_line = result.stdout.strip()

print("Ollama:", repr(intent_line))

if not intent_line:
    print("ERROR: Ollama returned empty result")
    raise SystemExit(1)

print("Executing router directly...")

router_result = execute_command(intent_line)

print("Router:", router_result)

print("========================================")
print("NOVA END-TO-END TEST COMPLETE")
print("========================================")
