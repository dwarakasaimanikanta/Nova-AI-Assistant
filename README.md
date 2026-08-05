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

**Phase 1: Project Foundation** ✅

At this stage, Nova is just a clean, professional project skeleton. There
are no AI, voice, or automation features yet -- only the folder structure,
configuration system, and logging system that every future phase will be
built on top of.

Running the app currently just confirms the skeleton works:

```
===================================
Nova AI Assistant
Status : Online
Version : 1.0.0
===================================
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
