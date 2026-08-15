import sys
import os

# Append project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Enforce production environment to bypass any test mocks in VoiceTool
os.environ["ENVIRONMENT"] = "production"

from nova_ep8 import speak

print("=== Running Real Production TTS Test (edge-tts) ===")
speak("Hello Boss. This is Nova speaking.")
print("=== Test Completed ===")
