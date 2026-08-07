# 📐 Nova AI Assistant: Architecture Specification (Version 1.0)

This document serves as the permanent, locked architectural reference and single source of truth for the Nova AI Assistant project.

---

## 1. Overall System Vision
Nova is designed as a highly reliable, modular, voice-first desktop agent capable of orchestrating complex workflows. The system bridges local desktop processes, browser automation, and connected Android mobile devices through an extensible tool-calling architecture. By combining sub-second wake word detection, continuous bilingual conversations, and automated reasoning, Nova behaves as an intelligent physical companion and terminal-level automation engine.

---

## 2. Long-term 7-Month Roadmap

* **Month 1: Foundation & Voice (Complete)**: Wake-word engine, VAD, continuous conversation loops, bilingual support, and local CLI/GUI shells.
* **Month 2: Core Integrations (Complete)**: Basic browser automation and local terminal, calendar, and file system tools.
* **Month 3: Device Bridges (Complete)**: Android phone support over ADB (Wi-Fi/USB auto-connect) for SMS, Calls, and WhatsApp.
* **Month 4: Semantic Memory**: SQLite-based vector storage for session memories and long-term user profile facts.
* **Month 5: Vision & Multi-Modality**: Screenshot analysis, visual accessibility, and local/remote multimodal LLM routing.
* **Month 6: Personal Services**: Secure email dispatch, Google/Outlook calendar synchronization, and automated notification handling.
* **Month 7: Multi-Agent Delegation**: Orchestration of autonomous subagents executing tasks concurrently over isolated sandboxes.

---

## 3. Architectural Principles

1. **Strict Modular Decoupling**: Core assistant pipelines must remain decoupled from specific tool or plugin implementations.
2. **Crash-Resistant Execution**: Background daemon threads (speech, Playwright) must run in isolated blocks so that failures in individual tools never terminate parent orchestrator loops.
3. **Privacy First & Permission Gated**: High-risk system tools must intercept execution using validation gates, requiring explicit user confirmations before execution.
4. **Offline First Fallbacks**: System-level commands (e.g., calculations, system metrics, time queries) must fall back to local offline skills when network connections are down.

---

## 4. Folder Responsibilities

* **`/core`**: Core engine coordination (`NovaEngine`) and agent tool planning loop (`AgentPlanner`).
* **`/plugins`**: Scanned directory for discovery and loading of dynamic tools.
* **`/tools`**: Operational blocks executing physical processes (ADB, Playwright, shell commands).
* **`/voice`**: Recording manager, wake word detection, STT engines, and TTS speech synthesis.
* **`/memory`**: Current session database structures and long-term profile data stores.
* **`/interface`**: Interactivity shells (terminal-based CLI and conversational desktop GUI).
* **`/utils`**: Logging configurations, system checks, and helper functions.
* **`/data`**: System databases, contact lists, and persistent configurations.
* **`/tests`**: Mock structures, unit tests, and integration test suites.

---

## 5. Plugin Architecture

Plugins act as the dynamic extension mechanism of Nova. Every plugin inherits from `BasePlugin` and implements:
* `name`: Standard identifying string.
* `get_tools()`: List of associated tool instances.
* `initialize_plugin(engine)`: Startup lifecycle hook for automatic configurations (e.g., auto-detecting wireless adb devices).

The engine scans directories, dynamically imports classes via `inspect`, and registers their tools with the main registry during startup.

---

## 6. Tool Architecture

Every capability exposed to the LLM router inherits from `BaseTool`:
* `name`: Unique identification keyword.
* `description`: Verbose guidance detailing parameters and capabilities.
* `parameters_schema`: JSON Schema representing argument types and required values.
* `risk_level`: Security indicator (LOW, MEDIUM, HIGH).
* `execute(**kwargs)`: Main synchronous execution logic.

---

## 7. Memory Architecture

Memory is split into two distinct tiers:
* **Short-Term Memory**: Conversation history array managed in-memory per session. Sliced to the last 10 turns to avoid context buffer overflow.
* **Long-Term Memory**: Fact store using a local SQLite database (`data/long_term_memory.db`) mapping facts to embeddings. Utilizes `check_same_thread=False` to safely process concurrent thread operations.

---

## 8. Voice Architecture

The Voice manager coordinates four core stages:
1. **Standby**: `AudioRecorder` captures microphone streams.
2. **Wake Detection**: `WakeWordDetector` matches incoming audios against "Nova" (and phonetic variations) at $\ge 80\%$ similarity.
3. **Continuous Conversation**: Transition to `WAITING` state, querying transcripts via `SpeechToTextEngine` continuously for commands without requiring wake words.
4. **Synthesizer**: TTS engine outputting Telugu or English spoken audio streams.

---

## 9. Android Architecture

Android integration uses ADB (Android Debug Bridge) via subprocess pipes:
* Coordinates calls (`action=call`), texts (`action=sms`), and WhatsApp messages (`action=whatsapp`).
* Dynamically resolves contact names from `data/contacts.json`.
* Startup routine checks for USB devices and reconnects to last saved Wi-Fi target automatically.

---

## 10. Browser Architecture

The web browser framework consists of two layers:
1. **Default Browser**: Uses the native standard library `webbrowser` for simple URL actions.
2. **Browser Agent**: Integrates async Playwright automation through `BrowserManager`. This module manages actions like screenshots, extraction, and key presses via a dedicated background loop thread.

---

## 11. Agent Architecture

* **Orchestrator**: `NovaEngine` registers plugins, controls memory access, and routes commands.
* **Reasoning loop**: `AgentPlanner` coordinates iterative reasoning. It loops LLM calls, checks permissions, executes matched tools, and updates chat contexts until a terminal response is resolved.

---

## 12. Future Multi-Agent Architecture

Nova's future roadmap targets a multi-agent framework:
* **Orchestrator Agent**: Breaks user input into structured subtasks.
* **Specialist Subagents**: Spawns isolated execution instances (e.g., Coding Agent, Browser Agent) running in virtual sandboxes.
* **Coordinator Bus**: Syncs state and aggregates subtask reports back to the master planner.

---

## 13. Startup Sequence

1. Initialize config manager and logger.
2. Instantiate `ShortTermMemory` and long-term `MemoryTool` database.
3. Instantiate `NovaEngine`.
4. Scan and register dynamic plugins (running ADB auto-connect).
5. Setup `AgentPlanner` routing client.
6. Start `VoiceManager` listener thread.
7. Launch PyQt6 GUI app or command-line CLI thread.

---

## 14. Shutdown Sequence

1. Catch `KeyboardInterrupt` / window close events.
2. Broadcast termination signal across active thread groups via `stop_event.set()`.
3. Join background threads (Speech, Playwright) with timeout parameters.
4. Cleanly close SQLite database connections.
5. Unlink temporary audio cache files.
6. Verify active thread count and exit process.

---

## 15. Threading Model

Nova uses a multi-threaded architecture to maintain UI responsiveness:
* **UI Thread**: Runs main shell console loops or PyQt6 window loops.
* **Voice Daemon Thread**: Listens for wake words, STT transcripts, and coordinates engine queries.
* **Playwright Loop Thread**: Dedicated thread running async browser operations to avoid blocking synchronous callers.

---

## 16. Event Bus Design (Future)

To support fully concurrent execution, a future event bus model will be integrated:
* **Pub/Sub Broker**: A central bus managing asynchronous system messages.
* **Event Definitions**: Standardized schemas for system triggers (e.g., `VoiceDetectedEvent`, `ToolExecutedEvent`).
* **Listeners**: Registered listeners (speech, logs, UI) receiving updates asynchronously.

---

## 17. Configuration Strategy

- Environment values (tokens, thresholds, sizes) are read from `.env` on startup.
- Constants are mapped in `config.py`.
- Private configurations (ADB Wi-Fi, Contacts) are stored as JSON in the `data/` folder.

---

## 18. Error Handling Strategy

1. **Speech Loops**: Caught exceptions in WAKING/WAITING states log error details and fall back to idle states without crashing the daemon thread.
2. **Tool Runs**: Executions run in `try/except` wraps. Tool failures return a structured error message (`Execution Error`) rather than raising errors to the planner.
3. **API Outages**: Gemini API errors fall back to offline skill processing or print a clean connection error.

---

## 19. Logging Strategy

- Unified logging utilizing custom handlers configured in `utils/logger.py`.
- Level constraints: `DEBUG` for planning stages, `INFO` for state transitions, `ERROR`/`CRITICAL` for database and system exceptions.
- Output: Standard error console streams and rolling logs in `logs/nova.log`.

---

## 20. Testing Strategy

- **Pytest**: Standard framework for unit and integration testing.
- **Mocking**: System utilities (ADB processes, audio recorders, speech engines) are mocked to bypass hardware requirements.
- **Pre-Commit Checks**: Full tests must run clean prior to codebase commits.

---

## 21. Coding Standards

- Type annotations must be used on every public module function and class method.
- Docstrings: Follow Google style conventions.
- Line length: Strict limit of 120 characters.
- Imports: Group standard libraries, third-party libraries, and local modules clearly.

---

## 22. Naming Conventions

* **Files & Packages**: snake_case (e.g., `voice_manager.py`).
* **Classes**: PascalCase (e.g., `AgentPlanner`).
* **Functions & Methods**: snake_case (e.g., `correct_contact_names`).
* **Constants**: UPPERCASE (e.g., `CONTACTS_FILE`).

---

## 23. Performance Goals

- **Wake Word Latency**: Sub-second wake detection response times.
- **Audio Processing**: Recording and VAD detection latency under 1.5 seconds.
- **Memory Footprint**: System RAM usage under 150MB when idle (excluding LLM loads).

---

## 24. Security Goals

- **Permission Interception**: High-risk commands must be gated and confirmed by the user.
- **API Key Protection**: Secrets are loaded from `.env` and must never be committed to repository control.
- **Sandboxing**: Execution boundaries restrict terminal/filesystem actions to user-approved locations.

---

## 25. Scalability Goals

- **Decoupled Extensions**: New tools should be registrable by adding plugin files without modifying core engine logic.
- **Thread Scaling**: Thread structures must remain light and clean to support concurrent agent operations.
- **LLM Independence**: A swappable provider interface ensures simple backend switching (Gemini, Claude, local models).

---

Architecture Status:
LOCKED
