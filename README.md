# Nova AI Assistant

Nova is a professional, portfolio-quality AI desktop assistant being built
from scratch in Python. The long-term goal is a system that can understand
voice commands, control a Windows machine, automate tasks, remember
conversations, help with coding, search the web, manage files, and support
agentic AI capabilities.

This project is being built in clearly defined phases rather than all at
once, so every part of the system is understood, tested, and stable before
the next layer is added. See [ROADMAP.md](./ROADMAP.md) for the full plan.

## Current Status

**Phase 4: AI Brain** ✅

At this stage, Nova is integrated with a generic, swappable LLM abstraction layer backed by the **Google Gemini API**. It features:
* A generic base provider interface ([llm/base_provider.py](file:///c:/Users/asus/OneDrive/Desktop/nova/llm/base_provider.py)).
* A concrete Google Gemini client backend wrapper ([llm/gemini_provider.py](file:///c:/Users/asus/OneDrive/Desktop/nova/llm/gemini_provider.py)) executing requests against the `gemini-3.6-flash` model.
* An extensible provider factory ([llm/provider_factory.py](file:///c:/Users/asus/OneDrive/Desktop/nova/llm/provider_factory.py)) to spawn vendors.
* A robust conversational coordinator ([llm/conversation.py](file:///c:/Users/asus/OneDrive/Desktop/nova/llm/conversation.py)) that synchronizes chat histories and intercepts API exception events to prevent Nova from crashing.
* Local fallback logic: if `GEMINI_API_KEY` is not present, Nova defaults back to `EchoSkill` offline mode with an operational setup reminder.

To configure the AI Brain:
1. Copy `.env.example` to `.env` (if not already done).
2. Fill in your `GEMINI_API_KEY`.
3. Run Nova:
```bash
python main.py
```

Expected output:
```text
===================================
System Loaded
Nova AI Assistant
Version 1.0.0 | Status: Online
Type 'help' for commands or start typing to chat.
===================================

You > help
Nova: Here are the skills I can perform:
  • Help: Lists every available skill dynamically.
  • Time: Shows current date and time.
  • Calculator: Supports simple arithmetic calculations (+, -, *, /).
  • SystemInfo: Shows OS, Python version and current working directory.
  • Echo: Echoes back the user's input.

You > 2 + 2 * 5
Nova: 2 + 2 * 5 = 12
```

## Project Structure

```
nova/
├── core/          # The "brain": engine, intent parsing, LLM client
├── skills/        # Pluggable capabilities (files, web search, code help, etc.)
├── memory/        # Short-term and long-term memory systems
├── voice/         # Speech-to-text, text-to-speech, wake word detection
├── interface/     # CLI and (later) GUI entry points
├── security/      # Auth and sandboxing for safe system control
├── utils/         # Shared helpers (logging, etc.)
├── tests/         # Unit tests, mirroring the source structure
├── data/          # Local runtime data (git-ignored)
├── logs/          # Application logs (git-ignored)
├── config.py      # Centralized app configuration
└── main.py        # Application entry point
```

## Getting Started

### Prerequisites

- Python 3.11 or newer
- pip (comes with Python)

### Setup

1. Clone the repository:
   ```bash
   git clone <your-repo-url>
   cd nova
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate      # Windows
   source venv/bin/activate   # macOS/Linux
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create your local environment file:
   ```bash
   cp .env.example .env
   ```
   Then open `.env` and fill in your own API keys (not required yet in
   Phase 1, but the file is set up now for future phases).

5. Run Nova:
   ```bash
   python main.py
   ```

## Development Roadmap

The project is being built in 8 phases, from foundation to a packaged
Windows application with voice, automation, memory, and agentic
capabilities. Full details are in [ROADMAP.md](./ROADMAP.md).

## Coding Standards

- PEP8 style, enforced with `black` and `flake8`
- Type hints on all function signatures
- Docstrings on all modules, classes, and functions
- Tests written alongside features, not after
- Small, descriptive commits (`feat:`, `fix:`, `docs:`, etc.)

## License

MIT
