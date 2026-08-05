"""
main.py
--------
Entry point for the Nova AI Assistant.

Wires together short-term memory, core engine, and CLI interface,
then runs the interactive user loop.
"""

from core.engine import NovaEngine
from interface.cli import NovaCLI
from memory.short_term import ShortTermMemory
from utils.logger import get_logger

logger = get_logger(__name__)


def main() -> None:
    """Main entry point of the application."""
    logger.info("Initializing Nova application components...")

    # 1. Instantiate Core Layers
    memory = ShortTermMemory()
    engine = NovaEngine(memory=memory)

    # 2. Instantiate and run Interface CLI
    cli = NovaCLI(engine=engine)

    try:
        cli.run()
    except Exception as e:
        logger.critical("Critical error occurred while running Nova: %s", e, exc_info=True)
        print(f"Critical System Error: {e}")


if __name__ == "__main__":
    main()
