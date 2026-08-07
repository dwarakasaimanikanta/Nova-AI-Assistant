# 📘 Nova AI Assistant: Development Standards Handbook

This document serves as the permanent engineering handbook and coding standards reference for the Nova AI Assistant project.

---

## 1. Project Coding Standards

- **Python Version**: Python 3.11+ is the baseline standard.
- **PEP 8 Compliance**: Strict adherence to PEP 8 style formatting.
- **Line Length**: Hard limit of 120 characters.
- **Type Annotations**: Mandatory type hinting on all public function signatures, method arguments, and return statements. E.g., `def handle_input(self, user_input: str, stream: bool = False) -> str:`
- **Imports Layout**: Group standard libraries, third-party libraries, and local modules clearly.

---

## 2. Directory & Folder Creation Rules

- New modules must reside in designated core directories: `/core`, `/plugins`, `/tools`, `/voice`, `/memory`, or `/utils`.
- Any custom directory creation must include an `__init__.py` file to enable namespace packaging.
- Temporary runtime file caches must be located inside the git-ignored `/data` or `/logs` directories.

---

## 3. Naming Conventions

* **Files & Packages**: Strict `snake_case` (e.g., `audio_recorder.py`, `contacts.json`).
* **Classes**: Strict `PascalCase` (e.g., `ShortTermMemory`).
* **Functions & Methods**: Strict `snake_case` (e.g., `correct_contact_names`).
* **Variables & Arguments**: Strict `snake_case` (e.g., `max_record_seconds`).
* **Constants**: Strict `UPPERCASE_SNAKE` (e.g., `CONTACTS_FILE`).

---

## 4. Logging Standards

- Use the unified project logger via `utils.logger.get_logger(__name__)`.
- **Level Constraints**:
  - `DEBUG`: Operational planning states, audio frames processing, and details of database hits.
  - `INFO`: Subsystem initializations, state machine transitions, and commands execution summaries.
  - `WARN`: Missing optional API keys, tool execution failures, or connection timeouts.
  - `ERROR`: Intercepted system errors, ADB connection failures, or SQLite read/write locks.
- **Secrets Redaction**: Do not log raw API keys, phone numbers, or text message contents.

---

## 5. Exception Handling Standards

- **No Silent Silencing**: Never use bare `except:` blocks. Always catch `Exception` and log details.
- **Thread Safety Isolation**: Protect background threads with try-except blocks to prevent process terminations from downstream exceptions.
- **Tool Failures**: Wrap tool executions in isolated try-except loops inside `ToolExecutor`, returning formatted failure messages rather than raising exceptions to the model planner.
- **Cleanup Gates**: Always use `try...finally` structures to release databases or unlink temporary wave files on disc.

---

## 6. Thread Safety & Async Coding Rules

- **Dedicated loops**: Asynchronous modules (like Playwright browser automation) must run in a dedicated event loop thread.
- **Thread Safety Flags**: Use thread-safe events (`threading.Event`) to check loop stop states across background processes.
- **SQLite Locking Guard**: When accessing SQLite databases from multiple threads, run with `check_same_thread=False` and use proper lock controls during write calls.

---

## 7. Dependency Rules

- Third-party packages must be registered inside `requirements.txt` with strict version bounds.
- System dependencies (like Android `adb` or Playwright engines) must check for presence on startup and provide descriptive guides on how to install them.
- Avoid introducing circular imports. Use local module imports inside functions where initialization dependencies overlap.

---

## 8. Plugin & Tool Development Rules

### Plugins
- Must inherit from `BasePlugin` and implement `name` and `get_tools()`.
- Must never implement execution logic directly; delegate actions to nested tools.

### Tools
- Must inherit from `BaseTool` and register schemas (`parameters_schema`) and risk classifications (`risk_level`).
- High-risk operations (e.g., terminal shell actions, local file overwrites) must specify `RiskLevel.HIGH` to invoke permission check gates.

---

## 9. Configuration Strategy

- Load environment parameters strictly via `.env` files on boot.
- Store static variables inside `config.py`.
- Dynamic structures (like contact mappings) should reside in JSON files under `/data`.

---

## 10. Documentation Standards

- Write descriptive docstrings for all classes and functions following the Google Python Style Guide.
- Every tool parameter must be documented inside the `parameters_schema` description block.
- Keep `README.md` updated with setup guides and command lists.

---

## 11. Testing Requirements

- Write unit tests for all new skills, tools, and plugins inside the `/tests` folder.
- Run tests using `pytest`.
- High-risk processes (ADB connections, microphone streams, LLM APIs) must be fully mocked to run tests offline.
- Aim for a minimum test coverage of 80% on all new code changes.

---

## 12. Git & Release Conventions

### Commit Messages
Follow semantic formats:
- `feat: <description>` (new features)
- `fix: <description>` (bug fixes)
- `test: <description>` (testing changes)
- `docs: <description>` (markdown updates)

### Versioning
Follow Semantic Versioning: `MAJOR.MINOR.PATCH`.

---

## 13. Definition of Done (DoD)

A task is considered complete only when:
1. All public signatures are typed and PEP 8 compliant.
2. The core logic executes without raising unhandled exceptions.
3. Unit tests cover success, edge cases, and failure scenarios.
4. Mocks are configured to run tests offline.
5. All tests pass successfully via `pytest`.
6. Code modifications are documented in `walkthrough.md` and the `README.md` is updated.

---

PROJECT STATUS

Architecture: LOCKED

Engineering Standards: LOCKED

Implementation: NOT STARTED
