"""Document links modal widget for opening and managing links."""

import subprocess
import platform
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, Label
from textual.binding import Binding


class DocumentLinksModal(Static):
    """Modal for viewing and opening document links."""

    DEFAULT_CSS = """
    DocumentLinksModal {
        width: 70;
        height: auto;
        border: solid $accent;
        padding: 1;
        background: $panel;
    }

    DocumentLinksModal > Vertical {
        width: 1fr;
        height: auto;
    }

    DocumentLinksModal Label {
        width: 1fr;
        margin: 0 0 1 0;
    }

    DocumentLinksModal Button {
        margin-right: 1;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
    ]

    def __init__(self, links: list[str], name: Optional[str] = None, id: Optional[str] = None):
        """Initialize the modal with document links."""
        super().__init__(name=name, id=id)
        self.links = links

    def compose(self) -> ComposeResult:
        """Compose the modal."""
        with Vertical():
            yield Label(f"[bold]Document Links ({len(self.links)})[/bold]")

            if not self.links:
                yield Label("[dim]No document links[/dim]")
            else:
                for i, link in enumerate(self.links, 1):
                    # Truncate long URLs
                    display_url = link[:60] + "..." if len(link) > 60 else link
                    yield Label(f"[cyan]{i}.[/cyan] {display_url}")

                yield Label("")
                help_text = (
                    "[dim]Keyboard:[/dim] [cyan]o+number[/cyan] to open, "
                    "[cyan]c+number[/cyan] to copy, [cyan]esc[/cyan] to close"
                )
                yield Label(help_text)

    def action_close(self) -> None:
        """Close the modal."""
        self.display = False

    def open_link(self, index: int) -> None:
        """Open a link with system default."""
        if 0 <= index < len(self.links):
            url = self.links[index]
            try:
                if platform.system() == "Darwin":  # macOS
                    subprocess.run(["open", url], check=True)
                elif platform.system() == "Linux":
                    subprocess.run(["xdg-open", url], check=True)
                elif platform.system() == "Windows":
                    subprocess.run(["start", url], check=True, shell=True)
                self.app.notify(f"Opened: {url[:50]}...", severity="information")
            except Exception as e:
                self.app.notify(f"Failed to open link: {e}", severity="error")

    def copy_link(self, index: int) -> None:
        """Copy a link to clipboard."""
        if 0 <= index < len(self.links):
            url = self.links[index]
            try:
                if platform.system() == "Darwin":
                    subprocess.run(["pbcopy"], input=url.encode(), check=True)
                # Add Linux/Windows clipboard support if needed
                self.app.notify(f"Copied: {url[:50]}...", severity="information")
            except Exception as e:
                self.app.notify(f"Failed to copy: {e}", severity="error")
