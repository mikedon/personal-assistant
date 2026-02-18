"""Task details modal widget."""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button, Label
from textual.binding import Binding

from src.models.task import Task


class TaskDetailsModal(Static):
    """Modal displaying full task details."""

    DEFAULT_CSS = """
    TaskDetailsModal {
        width: 80;
        height: auto;
        border: solid $accent;
        padding: 1;
        background: $panel;
    }

    TaskDetailsModal > Vertical {
        width: 1fr;
        height: auto;
    }

    TaskDetailsModal Label {
        width: 1fr;
        margin: 0;
    }

    TaskDetailsModal .title-section {
        margin-bottom: 1;
    }

    TaskDetailsModal .info-section {
        margin: 1 0;
    }

    TaskDetailsModal .buttons {
        width: 1fr;
        height: auto;
        margin-top: 1;
    }

    TaskDetailsModal Button {
        margin-right: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
    ]

    def __init__(self, task: Task, name: Optional[str] = None, id: Optional[str] = None):
        """Initialize the modal with a task."""
        super().__init__(name=name, id=id)
        self.task = task

    def compose(self) -> ComposeResult:
        """Compose the modal."""
        with Vertical():
            # Title
            yield Label(f"[bold]{self.task.title}[/bold]", classes="title-section")

            # Status and priority
            pri_emoji = {
                "critical": "🔴",
                "high": "🟠",
                "medium": "🟡",
                "low": "🟢",
            }.get(self.task.priority.value, "⚪")

            yield Label(
                f"Priority: {pri_emoji} {self.task.priority.value.upper()}  "
                f"Status: {self.task.status.value}",
                classes="info-section"
            )

            # Due date
            if self.task.due_date:
                due_str = self.task.due_date.strftime('%Y-%m-%d')
                yield Label(f"Due: {due_str}", classes="info-section")

            # Initiative
            if self.task.initiative:
                yield Label(f"Initiative: {self.task.initiative.title}", classes="info-section")

            # Description
            if self.task.description:
                yield Label("[bold dim]Description[/bold dim]")
                yield Label(self.task.description, classes="info-section")

            # Tags
            tags = self.task.get_tags_list()
            if tags:
                yield Label("[bold dim]Tags[/bold dim]")
                yield Label(", ".join(f"#{t}" for t in tags), classes="info-section")

            # Document links
            links = self.task.get_document_links_list()
            if links:
                yield Label("[bold dim]Document Links[/bold dim]")
                for link in links:
                    link_display = f"  • {link[:60]}..." if len(link) > 60 else f"  • {link}"
                    yield Label(link_display, classes="info-section")

            # Buttons
            with Horizontal(classes="buttons"):
                yield Button("Complete", id="btn-complete", variant="primary")
                yield Button("Delete", id="btn-delete", variant="error")
                yield Button("Close", id="btn-close", variant="default")

    def action_close(self) -> None:
        """Close the modal."""
        self.display = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-complete":
            self.post_message(self.Completed(self.task))
        elif event.button.id == "btn-delete":
            self.post_message(self.Deleted(self.task))
        elif event.button.id == "btn-close":
            self.action_close()

    class Completed:
        """Message sent when task is completed."""

        def __init__(self, task: Task):
            self.task = task

    class Deleted:
        """Message sent when task is deleted."""

        def __init__(self, task: Task):
            self.task = task
