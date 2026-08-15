import sys
import os
import time

# Append project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nova_ep8 import speak

print("=== Running Direct SAPI5 Production TTS Test ===")
speak("Hello Boss. This is Nova speaking.")
print("=== Test Execution Finished ===")
