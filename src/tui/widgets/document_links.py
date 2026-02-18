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
        Binding("1", "open_link_0", "Open 1"),
        Binding("2", "open_link_1", "Open 2"),
        Binding("3", "open_link_2", "Open 3"),
        Binding("4", "open_link_3", "Open 4"),
        Binding("5", "open_link_4", "Open 5"),
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
                    "[dim]Press [yellow]1-5[/yellow] to open link, "
                    "[yellow]esc[/yellow] to close[/dim]"
                )
                yield Label(help_text)

    def action_close(self) -> None:
        """Close the modal."""
        self.remove()

    def action_open_link_0(self) -> None:
        """Open link 1."""
        self.open_link(0)

    def action_open_link_1(self) -> None:
        """Open link 2."""
        self.open_link(1)

    def action_open_link_2(self) -> None:
        """Open link 3."""
        self.open_link(2)

    def action_open_link_3(self) -> None:
        """Open link 4."""
        self.open_link(3)

    def action_open_link_4(self) -> None:
        """Open link 5."""
        self.open_link(4)

    def open_link(self, index: int) -> None:
        """Open a link with system default (helper method)."""
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
        """Copy a link to clipboard (helper method)."""
        if 0 <= index < len(self.links):
            url = self.links[index]
            try:
                if platform.system() == "Darwin":
                    subprocess.run(["pbcopy"], input=url.encode(), check=True)
                # Add Linux/Windows clipboard support if needed
                self.app.notify(f"Copied: {url[:50]}...", severity="information")
            except Exception as e:
                self.app.notify(f"Failed to copy: {e}", severity="error")
