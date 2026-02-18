"""Full task list modal with filtering and search capabilities."""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, DataTable, Input, Label
from textual.binding import Binding

from src.models.database import get_db_session
from src.models.task import TaskPriority
from src.services.task_service import TaskService


class TaskListModal(Static):
    """Modal showing all tasks with filtering and search."""

    DEFAULT_CSS = """
    TaskListModal {
        width: 100;
        height: 90%;
        border: solid $accent;
        padding: 1;
        background: $panel;
    }

    TaskListModal > Vertical {
        width: 1fr;
        height: 1fr;
    }

    TaskListModal #search-input {
        width: 1fr;
        height: 3;
        border: solid $accent;
        margin-bottom: 1;
    }

    TaskListModal DataTable {
        width: 1fr;
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("slash", "search_focus", "Search"),
    ]

    def __init__(self, name: Optional[str] = None, id: Optional[str] = None):
        """Initialize the full task list modal."""
        super().__init__(name=name, id=id)
        self.all_tasks = []
        self.filtered_tasks = []
        self.search_term = ""

    def compose(self) -> ComposeResult:
        """Compose the modal."""
        with Vertical():
            msg = "[bold]All Tasks[/bold] (Press '/' to search, Esc to close)"
            yield Label(msg)

            # Search input
            search = Input(
                placeholder="Search tasks by title...",
                id="search-input"
            )
            yield search

            # Task table with columns pre-added
            table = DataTable(id="task-table")
            table.add_columns("Task", "Status", "Priority", "Due", "Initiative")
            yield table

    def on_mount(self) -> None:
        """Set up the modal when mounted."""
        # Load tasks into the table
        self.load_tasks()

        # Focus the search input
        search = self.query_one(Input, "#search-input")
        search.focus()

    def load_tasks(self) -> None:
        """Load all tasks from database."""
        try:
            with get_db_session() as db:
                service = TaskService(db)
                db_tasks = service.get_tasks(limit=500)[0]

                # Eagerly load all data
                self.all_tasks = []
                for task in db_tasks:
                    self.all_tasks.append({
                        'id': task.id,
                        'title': task.title,
                        'priority': task.priority,
                        'status': task.status,
                        'due_date': task.due_date,
                        'initiative_title': (
                            task.initiative.title if task.initiative else None
                        ),
                    })

            self.refresh_display()
        except Exception as e:
            self.app.notify(f"Error loading tasks: {e}", severity="error")

    def refresh_display(self) -> None:
        """Refresh the task table display."""
        table = self.query_one(DataTable)

        # Clear and repopulate
        while len(table.rows) > 0:
            table.remove_row(next(iter(table.rows)))

        # Filter tasks by search term
        if self.search_term:
            self.filtered_tasks = [
                t for t in self.all_tasks
                if self.search_term.lower() in t['title'].lower()
            ]
        else:
            self.filtered_tasks = self.all_tasks

        # Add rows
        for task in self.filtered_tasks:
            pri_emoji = {
                TaskPriority.CRITICAL: "🔴",
                TaskPriority.HIGH: "🟠",
                TaskPriority.MEDIUM: "🟡",
                TaskPriority.LOW: "🟢",
            }.get(task['priority'], "⚪")

            title = task['title'][:40] if task['title'] else "(no title)"
            status = task['status'].value if task['status'] else "unknown"
            due_str = (
                task['due_date'].strftime("%m/%d") if task['due_date'] else "-"
            )
            initiative = (
                task['initiative_title'][:12]
                if task['initiative_title'] else "-"
            )

            table.add_row(
                f"{pri_emoji} {title}",
                status,
                task['priority'].value if task['priority'] else "unknown",
                due_str,
                initiative,
                key=str(task['id']),
            )

    def action_close(self) -> None:
        """Close the modal."""
        self.display = False

    def action_search_focus(self) -> None:
        """Focus the search input."""
        search = self.query_one(Input, "#search-input")
        search.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "search-input":
            self.search_term = event.value
            self.refresh_display()
