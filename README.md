# 🤖 Nova AI Assistant

Nova is a highly responsive, professional AI desktop assistant built in Python. Designed to orchestrate memory, modular skills, and specialized tools, Nova seamlessly interfaces with the physical and digital worlds through natural voice interaction. Powered by Google Gemini and offline voice processing, Nova offers intelligent desktop automation, browser control, and Android phone integration.

---

## ✨ Features

- **🗣️ Wake Word Detection**: High-performance wake word engine supporting rapid, fuzzy-matching ("Nova", "Noba", "Nover", etc.) with sub-second latency.
- **🔄 Continuous Conversation**: Multi-turn conversation mode where "Hey Nova" is required only once. It prompts in natural Telugu and continues listening until explicitly stopped or timed out.
- **🇮🇳 Bilingual Voice Support**: Detects and responds in English and Telugu seamlessly.
- **📱 Android Phone Integration**: Extensible bridge to run Android actions including Call, SMS, and WhatsApp messaging via verified automation tools.
- **🔌 Wireless ADB Support**: Auto-connects to saved wireless debugging targets on startup.
- **🌐 Browser Automation**: Native capabilities to launch web pages, perform Google searches, and extract information.
- **🔍 Contact Name Correction**: Integrated fuzzy-matching layer that auto-corrects spoken contact names (e.g., *Emma -> Amma*, *Ama -> Amma*, *Ravy -> Ravi*, *అమ్మ -> Amma*) using similarity scoring prior to execution.
- **⚙️ Graceful Shutdown**: Complete lifecycle management that safely terminates background loops, thread pools, and active sessions on `Ctrl+C`.
- **🧩 Modular Plugin Architecture**: Dynamically discovers and loads external plugins to extend Nova's tool registry.

---

## 🛠️ Tech Stack

- **Core Engine**: Python 3.11+
- **AI Planning & Chat**: Google Gemini API (`gemini-3.5-flash-lite`) / Local Ollama (e.g. `llama3`)
- **Speech-to-Text**: Faster Whisper / Whisper API
- **Web Automation**: Playwright
- **Android Bridging**: Android Debug Bridge (ADB)
- **Fuzzy Matching**: RapidFuzz / Difflib

---

## 📂 Project Structure

```text
nova/
├── core/          # Central orchestration (NovaEngine, AgentPlanner, Tool registry)
├── plugins/       # Extensible plugin directory (AndroidPlugin, BrowserPlugin, etc.)
├── skills/        # Pluggable offline capabilities (Calculator, SystemInfo, Help)
├── voice/         # Audio recording, wake word detection, speech-to-text, and TTS
├── memory/        # Short-term and SQLite vector database memory stores
├── tools/         # Integrated tools (ADB, Playwright, Terminal, Permission Gate)
├── interface/     # Command line and interactive loop interfaces
├── data/          # Application configuration templates and contacts databases
├── tests/         # Unit and integration test suites
├── main.py        # Main entry point
└── config.py      # Environment and global configuration variables
```

---

## 🚀 Installation

### Prerequisites
- Python 3.11 or newer
- Android Debug Bridge (ADB) in system PATH (for phone automation)
- Sound Card / Microphone input devices

### Step-by-Step Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/dwarakasaimanikanta/Nova-AI-Assistant.git
   cd nova
   ```

2. **Configure a Python virtual environment**:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate      # Windows PowerShell/Command Prompt
   source .venv/bin/activate   # macOS/Linux
   ```

3. **Install project dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Prepare local environment variables**:
   Create a `.env` file in the root directory:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   VOICE_INPUT_ENABLED=True
   WAKE_WORD_ENABLED=True
   VOICE_MODEL_SIZE=tiny
   ```

5. **Prepare contacts configuration**:
   Ensure `data/contacts.json` is set up with your mobile contacts list:
   ```json
   {
     "amma": "+917842209762",
     "Dad": "+919247475161"
   }
   ```

---

## 💻 Usage

Start Nova in interactive mode:
```bash
python main.py
```

### Example Voice Commands
* `"Hey Nova"` (Triggers wake mode)
* `"Open Chrome"`
* `"Call Amma"` / `"Ammaకి కాల్ చేయి"`
* `"YouTube open cheyi"`
* `"Search AI news"`
* `"Message Ravi Hello"`
* `"Bye"` / `"సరే"` (Exits continuous mode)

---

## 📸 Screenshots

*Coming Soon.*

---

## 🗺️ Roadmap

- **🧠 Memory**: Vector-backed semantic memory integration to remember user preferences across sessions.
- **👁️ Vision**: Image description and multi-modal integration.
- **📧 Email**: Direct email creation, routing, and checking plugins.
- **📅 Calendar**: Google and Outlook calendar task scheduling and event sync.
- **🦙 Local LLM**: Offline execution fallback utilizing local Ollama instances.
- **👥 Multi-Agent Support**: Distributed agent delegation for complex workflows.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
