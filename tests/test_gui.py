"""
tests/test_gui.py
-----------------
Unit tests for the Desktop PyQt6 GUI application.
Designed to run headlessly in testing/CI environments without display servers.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from tools.voice import VoiceTool


def test_nova_worker_execution() -> None:
    """Ensure NovaWorker threads correctly parse streaming chunk generators and emit PyQt signals."""
    mock_engine = MagicMock()
    
    # Mock engine handle_input to return a generator of tokens
    def mock_generator(*args, **kwargs):
        yield "token1 "
        yield "token2"
        
    mock_engine.handle_input.return_value = mock_generator()

    from interface.gui.gui_app import NovaWorker
    worker = NovaWorker(engine=mock_engine, user_input="hello test")

    chunks = []
    def on_chunk(chunk):
        chunks.append(chunk)

    finished_data = []
    def on_finished(res):
        finished_data.append(res)

    worker.chunk_received.connect(on_chunk)
    worker.finished.connect(on_finished)

    # Trigger run directly headlessly without spinning standard QThread loops
    worker.run()

    assert chunks == ["token1 ", "token2"]
    assert finished_data == ["token1 token2"]
    mock_engine.handle_input.assert_called_with("hello test", stream=True)


def test_gui_app_voice_callback_binding() -> None:
    """Ensure the GUI app binds background voice events and dispatches update signals safely."""
    from PyQt6.QtWidgets import QApplication
    qt_app = QApplication.instance()
    if not qt_app:
        qt_app = QApplication(["-platform", "offscreen"])

    mock_engine = MagicMock()
    
    # Mock voice plugin structure
    mock_voice_manager = MagicMock()
    mock_voice_manager.is_active = True
    
    mock_voice_plugin = MagicMock()
    mock_voice_plugin.name = "voice"
    mock_voice_plugin.voice_manager = mock_voice_manager
    
    mock_engine.plugins = [mock_voice_plugin]

    # Patch GUI visual initializers to prevent graphical instantiation errors in headless pytest run
    with patch("interface.gui.gui_app.NovaGUIApp.init_ui"), \
         patch("interface.gui.gui_app.NovaGUIApp.show"):
         
        from interface.gui.gui_app import NovaGUIApp
        app = NovaGUIApp(engine=mock_engine)
        
        # Verify VoiceManager callback gets bound to GUI dispatcher
        assert mock_voice_manager.on_command_callback == app.dispatch_voice_command

        # Test dispatching a voice command triggers signal emission
        with patch.object(app, "voice_command_received") as mock_signal:
            app.dispatch_voice_command("voice command text", "response text")
            mock_signal.emit.assert_called_with("voice command text", "response text")
            
        # Clean up
        app.close()
