# 🤖 NOVA — AI Desktop Voice Assistant

NOVA is a Python-based desktop AI voice assistant designed to provide natural voice interaction, intelligent task execution, desktop automation, browser control, and a modern holographic user interface.

NOVA combines AI reasoning, speech processing, automation tools, and a visual desktop interface into a single assistant.

---

## ✨ Features

- 🎙️ Voice-based interaction
- 🧠 AI-powered conversational responses
- 🔊 Text-to-Speech responses
- 👂 Speech-to-Text input
- 🖥️ Desktop application control
- 📁 File and folder operations
- 🌐 Browser automation
- 🔎 Web search and information retrieval
- 🤖 Gemini API support
- 🦙 Ollama / local LLM support
- 💾 Conversation and session memory
- 🧩 Modular agent and tool architecture
- ⚡ Real-time assistant state handling
- 🎨 Animated holographic NOVA interface
- 🛑 Voice interruption / stop handling
- 🧪 Automated tests for core functionality

---

## 🖥️ NOVA Interface

NOVA includes a custom desktop interface with a futuristic holographic visualizer designed to react to assistant states such as:

- **READY**
- **LISTENING**
- **THINKING**
- **SPEAKING**

The visual interface provides animated feedback while NOVA processes commands and responds to the user.

---

## 🧠 Architecture

NOVA is organized into modular components:

```text
nova/
│
├── agents/              # Autonomous and specialized agents
├── core/                # Core engine, planning, memory and orchestration
├── interface/           # Desktop GUI and user interface
├── llm/                 # Gemini, Ollama and LLM providers
├── skills/              # Assistant skills
├── startup/             # Windows startup integration
├── tools/               # System, browser, file and voice tools
├── utils/               # Supporting utilities
├── voice/               # STT, TTS, recording and wake-word systems
├── resources/           # NOVA visual assets
│
├── nova_ep8.py          # NOVA desktop application launcher
├── nova_ui.py           # NOVA holographic interface
├── main.py              # Core application entry point
├── config.py            # Configuration
└── requirements.txt     # Python dependencies