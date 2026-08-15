import pytest
from unittest.mock import patch, MagicMock
import sys
import os

# Append project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import speak and handle_command from nova_ep8
import nova_ep8

@pytest.fixture
def mock_dependencies():
    with patch("nova_ep8.get_tts_engine") as mock_tts, \
         patch("nova_ep8.speak") as mock_speak, \
         patch("webbrowser.open") as mock_web_open, \
         patch("subprocess.Popen") as mock_sub_popen, \
         patch("subprocess.run") as mock_sub_run, \
         patch("nova_ep8.close_by_window_title") as mock_close_win, \
         patch("nova_ep8.wikipedia_answer") as mock_wiki, \
         patch("nova_ep8.web_search_answer") as mock_web_search, \
         patch("nova_ep8.ask_ollama") as mock_ollama:
        
        # Default mock returns
        mock_close_win.return_value = True
        mock_wiki.return_value = "Python is a high-level programming language that is widely used for web development."
        mock_web_search.return_value = "Python 3.12 is the latest stable version of Python."
        mock_ollama.return_value = "I'm Nova, a research assistant."
        
        yield {
            "speak": mock_speak,
            "webbrowser_open": mock_web_open,
            "subprocess_popen": mock_sub_popen,
            "subprocess_run": mock_sub_run,
            "close_by_window_title": mock_close_win,
            "wikipedia_answer": mock_wiki,
            "web_search_answer": mock_web_search,
            "ask_ollama": mock_ollama
        }

def test_open_youtube(mock_dependencies):
    nova_ep8.handle_command("Open YouTube", None)
    mock_dependencies["speak"].assert_called_once_with("YouTube is open, Boss.")
    mock_dependencies["webbrowser_open"].assert_called_once_with("https://www.youtube.com")

def test_close_youtube(mock_dependencies):
    nova_ep8.handle_command("Close YouTube", None)
    mock_dependencies["speak"].assert_called_once_with("YouTube is closed, Boss.")
    mock_dependencies["close_by_window_title"].assert_called_once_with("youtube")

def test_open_chrome(mock_dependencies):
    nova_ep8.handle_command("Open Chrome", None)
    mock_dependencies["speak"].assert_called_once_with("Chrome is open, Boss.")
    mock_dependencies["webbrowser_open"].assert_called_once_with("https://www.google.com")

def test_create_folder_pushpa(mock_dependencies):
    # Mock do_create_folder directly to verify exact return reaches speak
    with patch("nova_ep8.do_create_folder") as mock_do_create:
        mock_do_create.return_value = "The Pushpa folder has been created on your desktop, Boss."
        nova_ep8.handle_command("Create a folder named Pushpa on my desktop", None)
        mock_do_create.assert_called_once_with("Pushpa", "desktop")
        mock_dependencies["speak"].assert_called_once_with("The Pushpa folder has been created on your desktop, Boss.")

def test_what_is_python(mock_dependencies):
    nova_ep8.handle_command("What is Python?", None)
    mock_dependencies["wikipedia_answer"].assert_called_once_with("Python")
    mock_dependencies["speak"].assert_called_once_with("Python is a high-level programming language that is widely used for web development.")

def test_search_google_latest_python(mock_dependencies):
    nova_ep8.handle_command("Search Google for latest Python version", None)
    mock_dependencies["web_search_answer"].assert_called_once_with("latest Python version", "latest Python version")
    mock_dependencies["speak"].assert_called_once_with("Python 3.12 is the latest stable version of Python.")

def test_invalid_command_ollama_offline(mock_dependencies):
    mock_dependencies["ask_ollama"].return_value = "OLLAMA_OFFLINE"
    nova_ep8.handle_command("Gibberish unhandled command structure", None)
    mock_dependencies["speak"].assert_called_once_with("Ollama is offline, Boss.")

def test_invalid_command_ollama_online(mock_dependencies):
    mock_dependencies["ask_ollama"].return_value = "I did not understand that command, Boss."
    nova_ep8.handle_command("Gibberish unhandled command structure", None)
    mock_dependencies["speak"].assert_called_once_with("I did not understand that command, Boss.")

def test_time_command(mock_dependencies):
    nova_ep8.handle_command("what is the time?", None)
    mock_dependencies["speak"].assert_called_once()
    spoken = mock_dependencies["speak"].call_args[0][0]
    assert spoken.startswith("It is ")
    assert spoken.endswith(", Boss.")

def test_speech_normalization(mock_dependencies):
    with patch("nova_ep8.do_create_folder") as mock_do_create:
        mock_do_create.return_value = "The pushpa folder has been created on your desktop, Boss."
        nova_ep8.handle_command("Create a folder named Pishpah on my desktop", None)
        mock_do_create.assert_called_once_with("pushpa", "desktop")
        mock_dependencies["speak"].assert_called_once_with("The pushpa folder has been created on your desktop, Boss.")
