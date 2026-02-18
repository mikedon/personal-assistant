"""Task table widget displaying the top priority tasks."""

from datetime import datetime
from typing import Optional

from textual.containers import Container
from textual.reactive import reactive
from textual.widgets import DataTable, Static

from src.models.database import get_db_session
from src.models.task import TaskStatus, TaskPriority
from src.services.task_service import TaskService


class TaskTable(Static):
    """Widget displaying a table of top priority tasks."""

    DEFAULT_CSS = """
    TaskTable {
        width: 1fr;
        height: 1fr;
        border: solid $accent;
    }

    TaskTable > DataTable {
        width: 1fr;
        height: 1fr;
    }
    """

    task_count = reactive(0)
    selected_task_id = reactive(None)

    def __init__(self, name: Optional[str] = None, id: Optional[str] = None):
        """Initialize the task table."""
        super().__init__(name=name, id=id)
        self.table = DataTable()
        self.tasks = []

    def compose(self):
        """Compose the widget."""
        yield self.table

    def on_mount(self) -> None:
        """Set up the table when mounted."""
        # Add columns
        self.table.add_columns(
            "Pri",
            "Title",
            "Status",
            "Due",
            "Initiative",
            "Links",
        )

        # Load initial data
        self.refresh_tasks()

        # Set up key bindings
        self.table.focus()

    def refresh_tasks(self) -> None:
        """Refresh the task list from the database."""
        try:
            with get_db_session() as db:
                service = TaskService(db)
                self.tasks = service.get_prioritized_tasks(limit=10)

            self.table.clear()

            for task in self.tasks:
                # Priority emoji
                pri_emoji = {
                    TaskPriority.CRITICAL: "🔴",
                    TaskPriority.HIGH: "🟠",
                    TaskPriority.MEDIUM: "🟡",
                    TaskPriority.LOW: "🟢",
                }.get(task.priority, "⚪")

                # Title (truncate if too long)
                title = task.title[:30] if task.title else "(no title)"

                # Status
                status = task.status.value if task.status else "unknown"

                # Due date (relative format)
                due_str = self._format_due_date(task.due_date) if task.due_date else "-"

                # Initiative
                initiative = task.initiative.title[:15] if task.initiative else "-"

                # Links count
                links_count = len(task.get_document_links_list()) if task.document_links else 0
                links_str = f"🔗 {links_count}" if links_count > 0 else ""

                # Add row
                self.table.add_row(
                    pri_emoji,
                    title,
                    status,
                    due_str,
                    initiative,
                    links_str,
                    key=str(task.id),
                )

            self.task_count = len(self.tasks)

        except Exception as e:
            self.log(f"Error refreshing tasks: {e}")

    def _format_due_date(self, due_date: Optional[datetime]) -> str:
        """Format a due date in relative format."""
        if not due_date:
            return "-"

        now = datetime.now()
        if due_date.tzinfo:
            due_date = due_date.replace(tzinfo=None)

        diff = due_date - now

        if diff.total_seconds() < 0:
            days_overdue = abs(diff.days)
            if days_overdue == 0:
                return "Overdue"
            return f"Overdue {days_overdue}d"
        elif diff.days == 0:
            return "Today"
        elif diff.days == 1:
            return "Tomorrow"
        elif diff.days <= 7:
            return f"{diff.days}d"
        else:
            return due_date.strftime("%m/%d")

    def get_selected_task_id(self) -> Optional[int]:
        """Get the ID of the currently selected task."""
        if self.table.cursor_row >= 0 and self.table.cursor_row < len(self.tasks):
            return self.tasks[self.table.cursor_row].id
        return None

    def get_selected_task(self):
        """Get the currently selected task object."""
        task_id = self.get_selected_task_id()
        if task_id:
            return next((t for t in self.tasks if t.id == task_id), None)
        return None
