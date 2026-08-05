"""
interface/cli.py
----------------
Command-line interface and terminal user interaction for Nova.
"""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from core.engine import NovaEngine
from utils.logger import get_logger

logger = get_logger(__name__)


class NovaCLI:
    """Handles the terminal-based interactive chat loop and layout styling."""

    def __init__(self, engine: NovaEngine) -> None:
        """
        Initialize the CLI with the core engine.

        Args:
            engine: An instance of NovaEngine.
        """
        self.engine = engine
        self.console = Console()

    def show_banner(self) -> None:
        """Render a premium starting banner for Nova AI Assistant."""
        from config import APP_NAME, APP_VERSION

        banner_text = Text()
        banner_text.append(f"{APP_NAME}\n", style="bold cyan")
        banner_text.append(f"Version {APP_VERSION} | Status: Online\n", style="dim white")
        banner_text.append("Type 'help' for commands or start typing to chat.", style="italic green")

        panel = Panel(
            banner_text,
            title="System Loaded",
            title_align="left",
            border_style="cyan",
            padding=(1, 2),
        )
        self.console.print(panel)

    def clear_screen(self) -> None:
        """Clear the console screen and print the welcome banner."""
        self.console.clear()
        self.show_banner()
        logger.info("Terminal screen cleared.")

    def run(self) -> None:
        """Start the continuous user chat loop."""
        self.show_banner()
        logger.info("CLI input loop started.")

        while True:
            try:
                # Prompt user for input using rich style
                self.console.print("\n[bold green]You[/bold green] [dim]>[/dim] ", end="")
                user_input = input().strip()

                if not user_input:
                    continue

                logger.debug("Received CLI input: '%s'", user_input)

                # Process system commands locally
                lower_input = user_input.lower()
                if lower_input == "exit":
                    self.console.print("\n[bold cyan]Nova:[/bold cyan] Goodbye! Shutting down...")
                    logger.info("CLI user initiated shutdown.")
                    break
                elif lower_input == "clear":
                    self.clear_screen()
                else:
                    # Check if Gemini Brain is configured to use streaming
                    use_stream = self.engine.conversation is not None

                    if use_stream:
                        status = self.console.status("[dim white]Nova is thinking...[/dim white]")
                        status.start()
                        try:
                            # 1. Fetch generator from the core engine
                            response_gen = self.engine.handle_input(user_input, stream=True)

                            # 2. Iterate and print chunks dynamically
                            first_chunk = True
                            console_encoding = self.console.file.encoding or "utf-8"

                            for chunk in response_gen:
                                if first_chunk:
                                    # Terminate spinner immediately when the first token arrives
                                    status.stop()
                                    self.console.print("[bold cyan]Nova:[/bold cyan] ", end="")
                                    first_chunk = False

                                # Filter unsupported characters (e.g. emojis)
                                safe_chunk = chunk.encode(console_encoding, errors="ignore").decode(console_encoding)
                                self.console.print(safe_chunk, end="")
                            self.console.print()
                        finally:
                            status.stop()
                    else:
                        # Fallback for local commands / echo skills
                        with self.console.status("[dim white]Nova is thinking...[/dim white]"):
                            response = self.engine.handle_input(user_input, stream=False)

                        console_encoding = self.console.file.encoding or "utf-8"
                        safe_response = response.encode(console_encoding, errors="ignore").decode(console_encoding)
                        self.console.print(f"[bold cyan]Nova:[/bold cyan] {safe_response}")

            except (KeyboardInterrupt, EOFError):
                # Clean exit on Ctrl+C or Ctrl+D
                self.console.print("\n[bold cyan]Nova:[/bold cyan] Shutdown requested. Goodbye!")
                logger.info("CLI loop terminated via interrupt.")
                break
            except Exception as e:
                logger.exception("An unhandled error occurred in CLI loop: %s", e)
                console_encoding = self.console.file.encoding or "utf-8"
                safe_err = str(e).encode(console_encoding, errors="ignore").decode(console_encoding)
                self.console.print(f"\n[bold red]Error:[/bold red] An unexpected error occurred: {safe_err}")
