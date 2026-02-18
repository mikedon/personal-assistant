"""Task details modal widget."""

import platform
import subprocess

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Label, Static

from src.models.task import Task, TaskPriority


class TaskDetailsModal(Static):
    """Modal displaying full task details."""

    DEFAULT_CSS = """
    Screen {
        align: center middle;
    }

    TaskDetailsModal {
        width: 90;
        height: auto;
        border: solid $accent;
        padding: 1;
        background: $panel;
        layer: overlay;
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
        Binding("1", "open_link_0", "Open 1"),
        Binding("2", "open_link_1", "Open 2"),
        Binding("3", "open_link_2", "Open 3"),
        Binding("4", "open_link_3", "Open 4"),
        Binding("5", "open_link_4", "Open 5"),
    ]

    def __init__(self, task: Task | dict, name: str | None = None, id: str | None = None):
        """Initialize the modal with a task (model or dict)."""
        super().__init__(name=name, id=id)
        self._task_data = task
        self.task_id = task.id if isinstance(task, Task) else task.get('id')
        self.links = (
            task.get('document_links', [])
            if isinstance(task, dict)
            else task.get_document_links_list()
        )

    def compose(self) -> ComposeResult:
        """Compose the modal."""
        is_dict = isinstance(self._task_data, dict)
        title = (
            self._task_data.get('title')
            if is_dict
            else self._task_data.title
        )
        priority = (
            self._task_data.get('priority')
            if is_dict
            else self._task_data.priority
        )
        status = (
            self._task_data.get('status')
            if is_dict
            else self._task_data.status
        )
        due_date = (
            self._task_data.get('due_date')
            if is_dict
            else self._task_data.due_date
        )
        if is_dict:
            initiative = self._task_data.get('initiative_title')
        else:
            initiative = (
                self._task_data.initiative.title
                if self._task_data.initiative
                else None
            )
        description = (
            self._task_data.get('description')
            if is_dict
            else self._task_data.description
        )
        tags = (
            self._task_data.get('tags', '')
            if is_dict
            else self._task_data.get_tags_list()
        )
        links = (
            self._task_data.get('document_links', [])
            if is_dict
            else self._task_data.get_document_links_list()
        )

        with Vertical():
            # Title
            yield Label(f"[bold]{title}[/bold]", classes="title-section")

            # Status and priority
            if isinstance(priority, TaskPriority):
                priority_value = priority.value
            else:
                priority_value = priority if isinstance(priority, str) else str(priority)

            pri_emoji = {
                "critical": "🔴",
                "high": "🟠",
                "medium": "🟡",
                "low": "🟢",
            }.get(priority_value, "⚪")

            if isinstance(status, type):
                status_value = status.value
            else:
                status_value = status if isinstance(status, str) else str(status)

            yield Label(
                f"Priority: {pri_emoji} {priority_value.upper()}  Status: {status_value}",
                classes="info-section"
            )

            # Due date
            if due_date:
                if hasattr(due_date, 'strftime'):
                    due_str = due_date.strftime('%Y-%m-%d')
                else:
                    due_str = str(due_date)
                yield Label(f"Due: {due_str}", classes="info-section")

            # Initiative
            if initiative:
                yield Label(f"Initiative: {initiative}", classes="info-section")

            # Description
            if description:
                yield Label("[bold dim]Description[/bold dim]")
                yield Label(description, classes="info-section")

            # Tags
            if tags:
                if isinstance(tags, str):
                    tags_str = tags
                else:
                    tags_str = ", ".join(f"#{t}" for t in tags)
                yield Label("[bold dim]Tags[/bold dim]")
                yield Label(tags_str, classes="info-section")

            # Document links
            if links:
                msg = "[bold dim]Document Links (Press 1-5 to open)[/bold dim]"
                yield Label(msg)
                for i, link in enumerate(links, 1):
                    if len(link) > 55:
                        link_display = f"  [{i}] {link[:55]}..."
                    else:
                        link_display = f"  [{i}] {link}"
                    yield Label(link_display, classes="info-section")

            # Buttons
            with Horizontal(classes="buttons"):
                yield Button("Complete", id="btn-complete", variant="primary")
                yield Button("Delete", id="btn-delete", variant="error")
                yield Button("Close", id="btn-close", variant="default")

    def on_mount(self) -> None:
        """Set up the modal when mounted."""
        # Focus the widget so it can receive key events
        self.focus()

    def action_close(self) -> None:
        """Close the modal."""
        self.remove()

    def action_open_link_0(self) -> None:
        """Open link 1."""
        self._open_link(0)

    def action_open_link_1(self) -> None:
        """Open link 2."""
        self._open_link(1)

    def action_open_link_2(self) -> None:
        """Open link 3."""
        self._open_link(2)

    def action_open_link_3(self) -> None:
        """Open link 4."""
        self._open_link(3)

    def action_open_link_4(self) -> None:
        """Open link 5."""
        self._open_link(4)

    def _open_link(self, index: int) -> None:
        """Open a link with the system default browser."""
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

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-complete":
            self.post_message(self.Completed(self._task_data))
        elif event.button.id == "btn-delete":
            self.post_message(self.Deleted(self._task_data))
        elif event.button.id == "btn-close":
            self.action_close()

    class Completed(Message):
        """Message sent when task is completed."""

        def __init__(self, task: Task | dict):
            super().__init__()
            self.task = task

    class Deleted(Message):
        """Message sent when task is deleted."""

        def __init__(self, task: Task | dict):
            super().__init__()
            self.task = task
