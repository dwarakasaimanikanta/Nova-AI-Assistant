import sys
import os
from unittest.mock import patch, MagicMock

# Append project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import nova_ep8

def test_long_filmography_chunking():
    # Mock speak to track the calls
    with patch("nova_ep8.speak") as mock_speak:
        # Request Mahesh Babu movies list
        nova_ep8.handle_command("Mahesh Babu all movies", None)
        
        # Verify that speak was called multiple times with segmented chunks of the list
        assert mock_speak.call_count > 1, f"Expected Mahesh Babu filmography list to be spoken in multiple chunks, but got {mock_speak.call_count} calls."
        
        calls = [c[0][0] for c in mock_speak.call_args_list]
        print(f"Number of chunks spoken: {len(calls)}")
        for idx, text in enumerate(calls, 1):
            print(f"Chunk {idx}: {text[:80]}...")
            
        # Verify that the first chunk contains the header
        assert "major filmography" in calls[0].lower()
        # Verify that it is not truncated (contains the final movies from the list)
        assert "Guntur Kaaram" in calls[-1] or "Guntur" in calls[-1]

    print("SUCCESS: Filmography list parsing and speak_long chunking verified successfully!")

if __name__ == "__main__":
    test_long_filmography_chunking()
