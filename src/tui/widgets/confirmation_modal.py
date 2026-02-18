"""Confirmation modal for task actions."""

from typing import Callable, Optional

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button, Label
from textual.binding import Binding


class ConfirmationModal(Static):
    """Modal for confirming actions."""

    DEFAULT_CSS = """
    ConfirmationModal {
        width: 60;
        height: auto;
        border: solid $accent;
        padding: 1;
        background: $panel;
    }

    ConfirmationModal > Vertical {
        width: 1fr;
        height: auto;
    }

    ConfirmationModal Label {
        width: 1fr;
        margin: 1 0;
    }

    ConfirmationModal .buttons {
        width: 1fr;
        height: auto;
        margin-top: 1;
    }

    ConfirmationModal Button {
        margin-right: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        title: str,
        message: str,
        on_confirm: Callable[[], None],
        on_cancel: Callable[[], None] = None,
        name: Optional[str] = None,
        id: Optional[str] = None,
    ):
        """Initialize the confirmation modal."""
        super().__init__(name=name, id=id)
        self.title_text = title
        self.message = message
        self.on_confirm_callback = on_confirm
        self.on_cancel_callback = on_cancel or (lambda: None)

    def compose(self) -> ComposeResult:
        """Compose the modal."""
        with Vertical():
            yield Label(f"[bold]{self.title_text}[/bold]")
            yield Label(self.message)

            with Horizontal(classes="buttons"):
                yield Button("Confirm", id="btn-confirm", variant="primary")
                yield Button("Cancel", id="btn-cancel", variant="default")

    def action_cancel(self) -> None:
        """Cancel the action."""
        self.on_cancel_callback()
        self.display = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-confirm":
            self.on_confirm_callback()
            self.display = False
        elif event.button.id == "btn-cancel":
            self.action_cancel()
