"""
interface/gui/gui_app.py
------------------------
Desktop Conversating GUI for Nova AI Assistant built with PyQt6.
Features a modern dark-themed user interface, asynchronous command execution,
collapsible settings sidebar, and live voice manager feedback synchronization.
"""

import sys
from pathlib import Path
from typing import Any
from utils.logger import get_logger

logger = get_logger(__name__)

try:
    from PyQt6.QtCore import QThread, pyqtSignal, Qt, QSize
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QScrollArea, QLineEdit, QPushButton, QLabel, QFrame, QCheckBox,
        QComboBox, QSplitter
    )
    from PyQt6.QtGui import QFont, QPalette, QColor
    PYQT6_AVAILABLE = True
except ImportError as e:
    logger.warning("PyQt6 is not available. GUI app will not be startable: %s", e)
    PYQT6_AVAILABLE = False


class NovaWorker(QThread):
    """Asynchronous worker to process engine commands in a background thread."""
    chunk_received = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, engine: Any, user_input: str) -> None:
        super().__init__()
        self.engine = engine
        self.user_input = user_input

    def run(self) -> None:
        try:
            # Query the core engine with streaming enabled
            response_gen = self.engine.handle_input(self.user_input, stream=True)
            
            # Check if it returns a generator or a string
            if hasattr(response_gen, "__next__") or hasattr(response_gen, "__iter__"):
                full_response = ""
                for chunk in response_gen:
                    self.chunk_received.emit(chunk)
                    full_response += chunk
                self.finished.emit(full_response)
            else:
                self.finished.emit(str(response_gen))
        except Exception as e:
            logger.exception("Error executing engine command in GUI worker: %s", e)
            self.error.emit(str(e))


class ChatBubble(QFrame):
    """Custom widget representing a chat bubble for messages."""

    def __init__(self, text: str, is_user: bool = True) -> None:
        super().__init__()
        self.is_user = is_user
        self.init_ui(text)

    def init_ui(self, text: str) -> None:
        layout = QVBoxLayout(self)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        
        # Typography
        self.label.setFont(QFont("Segoe UI", 11))
        
        # Color schemes & Stylesheet
        if self.is_user:
            self.label.setStyleSheet("color: #ffffff;")
            self.setStyleSheet(
                "background-color: #6200ee; "
                "border-radius: 12px; "
                "margin-left: 50px; "
                "padding: 10px;"
            )
        else:
            self.label.setStyleSheet("color: #e0e0e0;")
            self.setStyleSheet(
                "background-color: #2c2c2c; "
                "border-radius: 12px; "
                "margin-right: 50px; "
                "padding: 10px;"
            )
            
        layout.addWidget(self.label)
        self.setLayout(layout)

    def append_text(self, text: str) -> None:
        """Append streamed chunks to the bubble."""
        self.label.setText(self.label.text() + text)


class NovaGUIApp(QMainWindow):
    """The central Desktop MainWindow managing layout, signals, and states."""

    voice_command_received = pyqtSignal(str, str)

    def __init__(self, engine: Any) -> None:
        super().__init__()
        self.engine = engine
        self.current_worker = None
        self.active_bubble = None

        if not PYQT6_AVAILABLE:
            raise RuntimeError("PyQt6 dependencies are missing or uninstalled.")

        self.init_ui()
        self.bind_voice_callback()

    def init_ui(self) -> None:
        self.setWindowTitle("Nova AI Assistant")
        self.setMinimumSize(900, 600)
        
        # Apply QSS Dark Stylesheet
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121212;
            }
            QWidget {
                color: #e0e0e0;
                font-family: 'Segoe UI', sans-serif;
            }
            QLineEdit {
                background-color: #1e1e1e;
                border: 1px solid #333333;
                border-radius: 8px;
                padding: 10px;
                color: #ffffff;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #6200ee;
            }
            QPushButton {
                background-color: #6200ee;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 18px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #7716f6;
            }
            QPushButton:pressed {
                background-color: #3700b3;
            }
            QScrollArea {
                border: none;
                background-color: #121212;
            }
            QCheckBox {
                spacing: 8px;
            }
            QComboBox {
                background-color: #1e1e1e;
                border: 1px solid #333333;
                border-radius: 6px;
                padding: 6px;
                color: #ffffff;
            }
        """)

        # Main splitter (separates side panel and main chat area)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        # 1. Left Sidebar Settings Panel
        sidebar = QFrame()
        sidebar.setStyleSheet("background-color: #1a1a1a; border-right: 1px solid #2d2d2d;")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(15, 20, 15, 20)
        sidebar_layout.setSpacing(15)

        sidebar_title = QLabel("System Settings")
        sidebar_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        sidebar_layout.addWidget(sidebar_title)

        # Voice Settings
        self.voice_enabled_cb = QCheckBox("Enable Voice Input")
        from config import VOICE_INPUT_ENABLED, WAKE_WORD_ENABLED, VOICE_MODEL_SIZE
        self.voice_enabled_cb.setChecked(VOICE_INPUT_ENABLED)
        self.voice_enabled_cb.stateChanged.connect(self.apply_settings)
        sidebar_layout.addWidget(self.voice_enabled_cb)

        self.wake_word_cb = QCheckBox("Wake Word ('Hey Nova')")
        self.wake_word_cb.setChecked(WAKE_WORD_ENABLED)
        self.wake_word_cb.stateChanged.connect(self.apply_settings)
        sidebar_layout.addWidget(self.wake_word_cb)

        # Model Config
        model_label = QLabel("Speech Model Size:")
        sidebar_layout.addWidget(model_label)
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small"])
        self.model_combo.setCurrentText(VOICE_MODEL_SIZE or "tiny")
        self.model_combo.currentTextChanged.connect(self.apply_settings)
        sidebar_layout.addWidget(self.model_combo)

        sidebar_layout.addStretch()

        # Build Version
        from config import APP_VERSION
        version_label = QLabel(f"Version {APP_VERSION}")
        version_label.setStyleSheet("color: #666666; font-size: 11px;")
        sidebar_layout.addWidget(version_label)

        # 2. Main Conversational Frame
        chat_frame = QWidget()
        chat_layout = QVBoxLayout(chat_frame)
        chat_layout.setContentsMargins(10, 10, 10, 10)

        # Scroll viewport for chat bubbles
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.chat_container = QWidget()
        self.chat_container_layout = QVBoxLayout(self.chat_container)
        self.chat_container_layout.setSpacing(12)
        self.chat_container_layout.addStretch()  # Forces messages to start at the top
        self.scroll_area.setWidget(self.chat_container)
        chat_layout.addWidget(self.scroll_area)

        # Auto-scroll mapping
        self.scroll_area.verticalScrollBar().rangeChanged.connect(self.scroll_to_bottom)

        # Input horizontal bar
        input_bar = QHBoxLayout()
        input_bar.setSpacing(10)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Send a message to Nova...")
        self.input_field.returnPressed.connect(self.send_message)
        input_bar.addWidget(self.input_field)

        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.send_message)
        input_bar.addWidget(self.send_btn)

        # Microphone Toggle Button
        self.mic_btn = QPushButton("Mic Off")
        self.mic_btn.setMinimumWidth(90)
        self._update_mic_button_style()
        self.mic_btn.clicked.connect(self.toggle_mic)
        input_bar.addWidget(self.mic_btn)

        chat_layout.addLayout(input_bar)

        # Assemble Splitting Frames
        splitter.addWidget(sidebar)
        splitter.addWidget(chat_frame)
        splitter.setSizes([220, 680])
        splitter.setCollapsible(0, False)

        # Render Start Banner
        self.add_message_bubble("System Loaded: Nova is online.", is_user=False)

    def scroll_to_bottom(self) -> None:
        """Autoscrolls viewport area to display new tokens."""
        self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        )

    def add_message_bubble(self, text: str, is_user: bool = True) -> ChatBubble:
        """Dynamically instantiates and renders bubble widget."""
        bubble = ChatBubble(text, is_user=is_user)
        # Insert bubble right before the stretch space at the bottom
        count = self.chat_container_layout.count()
        self.chat_container_layout.insertWidget(count - 1, bubble)
        return bubble

    def send_message(self) -> None:
        """Send input and trigger async background worker."""
        text = self.input_field.text().strip()
        if not text:
            return

        self.input_field.clear()
        self.add_message_bubble(text, is_user=True)

        # Disable fields during processing
        self.send_btn.setEnabled(False)
        self.input_field.setEnabled(False)

        # Setup assistant thinking bubble
        self.active_bubble = self.add_message_bubble("", is_user=False)

        # Spin worker QThread
        self.current_worker = NovaWorker(self.engine, text)
        self.current_worker.chunk_received.connect(self.handle_chunk)
        self.current_worker.finished.connect(self.handle_finished)
        self.current_worker.error.connect(self.handle_error)
        self.current_worker.start()

    def handle_chunk(self, chunk: str) -> None:
        """Appends streamed token chunk to active bubble."""
        if self.active_bubble:
            self.active_bubble.append_text(chunk)

    def handle_finished(self, full_response: str) -> None:
        """Re-enables input states and cleans up thread states."""
        if self.active_bubble and not self.active_bubble.label.text():
            self.active_bubble.label.setText(full_response)
        
        self.send_btn.setEnabled(True)
        self.input_field.setEnabled(True)
        self.input_field.setFocus()
        self.current_worker = None
        self.active_bubble = None

    def handle_error(self, error_str: str) -> None:
        """Renders error text on failure."""
        if self.active_bubble:
            self.active_bubble.append_text(f"Error: {error_str}")
        self.send_btn.setEnabled(True)
        self.input_field.setEnabled(True)
        self.current_worker = None
        self.active_bubble = None

    def toggle_mic(self) -> None:
        """Toggle microphone listening state in VoiceManager."""
        voice_plugin = next((p for p in self.engine.plugins if p.name == "voice"), None)
        if not voice_plugin or not voice_plugin.voice_manager:
            self.add_message_bubble("Voice Input is not initialized or configured in this system.", is_user=False)
            return

        manager = voice_plugin.voice_manager
        if manager.is_active:
            manager.stop()
            self.voice_enabled_cb.setChecked(False)
        else:
            manager.voice_input_enabled = True
            manager.start()
            self.voice_enabled_cb.setChecked(True)
        self._update_mic_button_style()

    def _update_mic_button_style(self) -> None:
        voice_plugin = next((p for p in self.engine.plugins if p.name == "voice"), None)
        is_active = False
        if voice_plugin and voice_plugin.voice_manager:
            is_active = voice_plugin.voice_manager.is_active

        if is_active:
            self.mic_btn.setText("Mic On")
            self.mic_btn.setStyleSheet("""
                QPushButton {
                    background-color: #03dac6;
                    color: black;
                }
                QPushButton:hover {
                    background-color: #01bca9;
                }
            """)
        else:
            self.mic_btn.setText("Mic Off")
            self.mic_btn.setStyleSheet("""
                QPushButton {
                    background-color: #cf6679;
                    color: black;
                }
                QPushButton:hover {
                    background-color: #b24d5f;
                }
            """)

    def apply_settings(self) -> None:
        """Dynamic settings updater syncs sidebar adjustments directly to runtime variables."""
        voice_plugin = next((p for p in self.engine.plugins if p.name == "voice"), None)
        if not voice_plugin or not voice_plugin.voice_manager:
            return

        manager = voice_plugin.voice_manager
        
        # Read checkbox states
        enable_voice = self.voice_enabled_cb.isChecked()
        enable_wake = self.wake_word_cb.isChecked()
        model_size = self.model_combo.currentText()

        # Update manager parameters
        manager.wake_word_enabled = enable_wake
        
        # If enabled state changed, start/stop manager thread
        if enable_voice != manager.is_active:
            if enable_voice:
                manager.voice_input_enabled = True
                manager.start()
            else:
                manager.stop()
                
        # If model changes, configure new STT backend size
        if model_size != manager.stt_engine.model_size and hasattr(manager.stt_engine, "model_size"):
            # Update parameters dynamically
            manager.stt_engine.model_size = model_size
            if hasattr(manager.stt_engine, "model") and manager.stt_engine.model is not None:
                # Trigger reload on next transcription
                manager.stt_engine.model = None

        self._update_mic_button_style()

    def bind_voice_callback(self) -> None:
        """Connects voice manager callback back into PyQt6 event thread."""
        voice_plugin = next((p for p in self.engine.plugins if p.name == "voice"), None)
        if voice_plugin and voice_plugin.voice_manager:
            # Bind callback
            voice_plugin.voice_manager.on_command_callback = self.dispatch_voice_command
            self.voice_command_received.connect(self.handle_voice_command)

    def dispatch_voice_command(self, text: str, response: str) -> None:
        """Safely dispatches callback data to GUI thread using PyQt signals."""
        self.voice_command_received.emit(text, response)

    def handle_voice_command(self, text: str, response: str) -> None:
        """Adds bubbles for background-transcribed commands to scroll view."""
        self.add_message_bubble(text, is_user=True)
        self.add_message_bubble(response, is_user=False)

    def closeEvent(self, event: Any) -> None:
        """Clean shutdown hooks on close."""
        voice_plugin = next((p for p in self.engine.plugins if p.name == "voice"), None)
        if voice_plugin:
            voice_plugin.shutdown()
        event.accept()
