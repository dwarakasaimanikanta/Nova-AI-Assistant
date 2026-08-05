"""
main.py
--------
Entry point for the Nova AI Assistant.

At this stage (Phase 1 - Foundation), Nova does not yet have any
AI, voice, or automation capabilities. This file only verifies that
the project skeleton runs correctly and prints a status banner.

In later phases, this file will:
    - Load configuration (core/config.py)
    - Initialize logging (utils/logger.py)
    - Start the Core Engine (core/engine.py)
    - Launch the CLI or GUI interface
"""

from config import APP_NAME, APP_VERSION


def print_banner() -> None:
    """Print Nova's startup status banner to the console."""
    print("===================================")
    print(f"{APP_NAME}")
    print("Status : Online")
    print(f"Version : {APP_VERSION}")
    print("===================================")


def main() -> None:
    """Main entry point of the application."""
    print_banner()


if __name__ == "__main__":
    main()
