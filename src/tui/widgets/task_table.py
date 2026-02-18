"""Task table widget displaying the top priority tasks."""

from datetime import datetime
from typing import Optional

from textual.containers import Container
from textual.reactive import reactive
from textual.widgets import DataTable, Static
from textual.binding import Binding

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

    BINDINGS = [
        Binding("enter", "show_details", "Details"),
    ]

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
                db_tasks = service.get_prioritized_tasks(limit=10)

                # Eagerly load all data into dicts before session closes
                self.tasks = []
                for task in db_tasks:
                    self.tasks.append({
                        'id': task.id,
                        'title': task.title,
                        'priority': task.priority,
                        'status': task.status,
                        'due_date': task.due_date,
                        'initiative_title': task.initiative.title if task.initiative else None,
                        'document_links': task.get_document_links_list(),
                    })

            # Clear rows but keep columns
            # Get current row indices and delete them
            while len(self.table.rows) > 0:
                self.table.remove_row(next(iter(self.table.rows)))

            for task_data in self.tasks:
                # Priority emoji
                pri_emoji = {
                    TaskPriority.CRITICAL: "🔴",
                    TaskPriority.HIGH: "🟠",
                    TaskPriority.MEDIUM: "🟡",
                    TaskPriority.LOW: "🟢",
                }.get(task_data['priority'], "⚪")

                # Title (truncate if too long)
                title = task_data['title'][:30] if task_data['title'] else "(no title)"

                # Status
                status = task_data['status'].value if task_data['status'] else "unknown"

                # Due date (relative format)
                due_str = self._format_due_date(task_data['due_date']) if task_data['due_date'] else "-"

                # Initiative
                initiative = task_data['initiative_title'][:15] if task_data['initiative_title'] else "-"

                # Links count
                links_count = len(task_data['document_links']) if task_data['document_links'] else 0
                links_str = f"🔗 {links_count}" if links_count > 0 else ""

                # Add row
                self.table.add_row(
                    pri_emoji,
                    title,
                    status,
                    due_str,
                    initiative,
                    links_str,
                    key=str(task_data['id']),
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
            return self.tasks[self.table.cursor_row]['id']
        return None

    def get_selected_task(self):
        """Get the currently selected task data dict."""
        task_id = self.get_selected_task_id()
        if task_id:
            return next((t for t in self.tasks if t['id'] == task_id), None)
        return None

    def action_show_details(self) -> None:
        """Show details for the selected task."""
        task = self.get_selected_task()
        if task:
            self.post_message(self.TaskSelected(task))

    class TaskSelected:
        """Message posted when a task is selected to show details."""

        def __init__(self, task):
            self.task = task
