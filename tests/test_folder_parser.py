import sys
import os

# Append project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from nova_ep8 import _parse_create_folder, _is_create_folder_cmd, _extract_name_from_reply

def test_folder_parsing_cases():
    initial_cases = [
        ("Create a folder in my desktop named Pushpa", "Pushpa", "desktop"),
        ("Create your folder in my desktop name it as Pushparaj", "Pushparaj", "desktop"),
        ("Hold her name is Pushparaj", "Pushparaj", "desktop"),
        ("Create a folder on my desktop called Nova", "Nova", "desktop"),
        ("Create a folder in desktop Pushparaj", "Pushparaj", "desktop"),
        ("Create Pushparaj folder on my desktop", "Pushparaj", "desktop"),
    ]

    for input_str, expected_name, expected_loc in initial_cases:
        # Check command is recognized
        assert _is_create_folder_cmd(input_str.lower()), f"Failed command recognition: '{input_str}'"
        # Check extraction is correct
        name, loc = _parse_create_folder(input_str.lower(), input_str)
        assert name == expected_name, f"Failed name extraction for '{input_str}': expected '{expected_name}', got '{name}'"
        assert loc == expected_loc, f"Failed location extraction for '{input_str}': expected '{expected_loc}', got '{loc}'"

    follow_up_cases = [
        ("Name it as Push-Paw", "Push-Paw"),
        ("Hold her name is Pushparaj", "Pushparaj"),
        ("Pushparaj", "Pushparaj"),
    ]

    for input_str, expected_name in follow_up_cases:
        name = _extract_name_from_reply(input_str)
        assert name == expected_name, f"Failed name extraction from follow-up '{input_str}': expected '{expected_name}', got '{name}'"

    print("SUCCESS: All folder parser and follow-up tests passed successfully!")

if __name__ == "__main__":
    test_folder_parsing_cases()
