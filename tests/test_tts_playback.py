import sys
import os
import time

# Append project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pyttsx3
from nova_ep8 import speak, get_tts_engine

# Tracking callback invocations
started_called = False
word_called = False
finished_called = False

def onStart(name):
    global started_called
    started_called = True
    print("[TEST] Callback: started-utterance fired.")

def onWord(name, location, length):
    global word_called
    word_called = True
    # Avoid printing too many lines, just trace
    pass

def onEnd(name, completed):
    global finished_called
    finished_called = True
    print(f"[TEST] Callback: finished-utterance fired. Completed={completed}")

try:
    # Connect callbacks to the production engine instance
    engine = get_tts_engine()
    engine.connect('started-utterance', onStart)
    engine.connect('started-word', onWord)
    engine.connect('finished-utterance', onEnd)
except Exception as e:
    print(f"[TEST ERROR] Failed to connect pyttsx3 callbacks: {e}")

print("--- Running Direct TTS Playback Test ---")
test_phrase = "Hello Boss. This is Nova voice test."
speak(test_phrase)

print("\n--- Playback Verification ---")
print(f"Callback 'started-utterance' fired: {started_called}")
print(f"Callback 'finished-utterance' fired: {finished_called}")

if started_called and finished_called:
    print("SUCCESS: Actual audio playback path was successfully invoked!")
    sys.exit(0)
else:
    print("FAILURE: TTS callbacks did not fire. The audio playback path was not invoked.")
    sys.exit(1)
