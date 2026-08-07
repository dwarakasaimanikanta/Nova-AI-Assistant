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
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="Nova AI Assistant")
    parser.add_argument("--gui", action="store_true", help="Launch the Desktop PyQt6 Conversational GUI")
    parser.add_argument("--minimized", action="store_true", help="Start the application minimized to system tray")
    args = parser.parse_args()

    logger.info("Initializing Nova application components...")

    # 1. Instantiate Core Layers and run Startup Lifecycle via BootManager
    from core.boot_manager import BootManager
    boot_mgr = BootManager()
    try:
        boot_report = boot_mgr.boot()
        if not boot_report.success:
            logger.critical("Critical: BootManager failed to boot: %s", boot_report.errors)
            sys.exit(1)
    except Exception as boot_err:
        logger.critical("Critical: BootManager raised exception: %s", boot_err, exc_info=True)
        sys.exit(1)

    engine = boot_mgr.executive_agent.engine


    try:
        if args.gui:
            logger.info("Launching Desktop PyQt6 Conversational GUI...")
            try:
                from PyQt6.QtWidgets import QApplication
                from interface.gui.gui_app import NovaGUIApp
                
                app = QApplication(sys.argv)
                gui = NovaGUIApp(engine=engine)
                gui.show()
                sys.exit(app.exec())
            except Exception as e:
                logger.critical("Failed to launch GUI: %s. Falling back to CLI...", e)
                print(f"Error launching GUI: {e}")
                print("Falling back to CLI interface...\n")
                args.gui = False

        if not args.gui:
            # 2. Instantiate and run Interface CLI
            cli = NovaCLI(engine=engine)
            try:
                cli.run()
            except Exception as e:
                logger.critical("Critical error occurred while running Nova CLI: %s", e, exc_info=True)
                print(f"Critical System Error: {e}")
    finally:
        engine.shutdown()
        import threading
        logger.info("[Watchdog] Engine shutdown complete.")
        active_threads = threading.enumerate()
        logger.info("[Watchdog] Final active thread count before process exit: %d", len(active_threads))
        for t in active_threads:
            logger.info("[Watchdog] Active thread on exit: name=%s, daemon=%s, ident=%s", t.name, t.daemon, t.ident)


if __name__ == "__main__":
    main()
