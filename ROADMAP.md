# Nova AI Assistant — Development Roadmap

This document tracks the phased build plan for Nova. Each phase adds one
new dimension of capability on top of a stable, working foundation, rather
than building everything at once.

- [x] **Phase 0 — Foundation (Setup)**
- [x] **Phase 1 — Project Foundation / Skeleton** *(current)*
- [ ] **Phase 2 — Text-Based Core Assistant (CLI)**
- [ ] **Phase 3 — Persistent Memory**
- [ ] **Phase 4 — Voice Interface**
- [ ] **Phase 5 — System & File Automation**
- [ ] **Phase 6 — Coding Assistant Skill**
- [ ] **Phase 7 — Agentic Capabilities**
- [ ] **Phase 8 — GUI + Packaging**

---

## Phase 1 — Project Foundation *(current phase)*

**Goal:** A clean, professional, empty project skeleton that runs and
proves the base configuration/logging systems work. No AI logic yet.

Delivered:
- Full folder structure (`core/`, `skills/`, `memory/`, `voice/`,
  `interface/`, `security/`, `utils/`, `tests/`, `data/`, `logs/`)
- `config.py` — centralized configuration loaded from `.env`
- `utils/logger.py` — centralized logging (console + rotating file)
- `main.py` — entry point that prints a status banner
- `requirements.txt`, `.gitignore`, `.env.example`, `README.md`

## Phase 2 — Text-Based Core Assistant (CLI)

- Build `core/engine.py`: the main command loop
- Integrate an LLM API (Claude/OpenAI) for conversational responses
- Basic intent detection (question vs. command vs. chit-chat)
- First real skills: `web_search`, `file_manager` (list/read/create files)
- Short-term memory: remembers the current conversation only
- **Outcome:** You can type to Nova in a terminal and get intelligent
  responses, plus basic web search and file reading.

## Phase 3 — Persistent Memory

- SQLite for structured data (history, tasks, settings)
- ChromaDB (vector database) for semantic long-term memory
- Nova recalls facts and preferences across restarts
- **Outcome:** Nova remembers you between sessions.

## Phase 4 — Voice Interface

- Speech-to-text via `faster-whisper`
- Text-to-speech via `pyttsx3` (later upgradeable)
- Wake word detection ("Hey Nova")
- **Outcome:** Fully hands-free interaction.

## Phase 5 — System & File Automation

- Open/close applications
- Automated file organization (sort downloads, batch rename)
- System info (battery, RAM, running processes)
- Scheduled/triggered tasks
- **Outcome:** Nova can act on the machine, not just talk.

## Phase 6 — Coding Assistant Skill

- Code explanation, generation, and debugging via LLM
- Read/write project files
- Run scripts and capture their output
- **Outcome:** Nova becomes a development sidekick.

## Phase 7 — Agentic Capabilities

- Multi-step task planning (break a goal into sub-tasks)
- Tool-use framework: Nova chooses and chains skills automatically
- Self-correction / retry loops on failure
- **Outcome:** Nova can handle compound instructions like "organize my
  downloads folder and summarize what you moved."

## Phase 8 — GUI + Packaging

- Desktop GUI (chat window, mic button, settings panel) via PyQt6
- Package into a distributable Windows `.exe` with PyInstaller
- Polish, error handling, first-run onboarding
- **Outcome:** A shareable, installable, portfolio-ready application.

---

## Guiding Principles Across All Phases

- **Separation of concerns:** interface, core logic, skills, memory, and
  system integration stay in distinct layers.
- **Security first:** no destructive action runs without explicit
  confirmation; no secrets are ever committed to source control.
- **Incremental, tested growth:** each phase must run and be verified
  before the next phase begins.
- **Swappable components:** LLM provider, STT/TTS engine, and storage
  backend are all abstracted so they can be replaced without rewriting
  the core engine.
