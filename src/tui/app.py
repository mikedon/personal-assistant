"""Main TUI application for the Personal Assistant dashboard."""

from datetime import datetime
from typing import Optional

from textual.app import ComposeResult, App
from textual.containers import Horizontal
from textual.widgets import Header, Footer

from src.models.database import get_db_session
from src.services.task_service import TaskService
from src.tui.widgets import TaskTable, InitiativePanel, AgentStatusBar


class TaskDashboardApp(App):
    """Main application for the task management TUI."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-container {
        width: 1fr;
        height: 1fr;
        layout: horizontal;
    }

    #task-panel {
        width: 1fr;
        height: 1fr;
    }

    #sidebar-panel {
        width: 25;
        height: 1fr;
    }

    #status-bar {
        width: 1fr;
        height: 3;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("c", "complete_task", "Complete"),
        ("d", "delete_task", "Delete"),
        ("l", "show_task_list", "List All"),
        ("o", "open_link", "Open Link"),
        ("p", "poll_now", "Poll Now"),
        ("a", "toggle_polling", "Auto Poll"),
        ("?", "show_help", "Help"),
    ]

    TITLE = "Personal Assistant Tasks"

    def __init__(self):
        """Initialize the application."""
        super().__init__()
        self.task_table: Optional[TaskTable] = None
        self.initiative_panel: Optional[InitiativePanel] = None
        self.agent_status: Optional[AgentStatusBar] = None

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()

        # Main container with task table on left, initiatives on right
        with Horizontal(id="main-container"):
            self.task_table = TaskTable(id="task-panel")
            yield self.task_table

            self.initiative_panel = InitiativePanel(id="sidebar-panel")
            yield self.initiative_panel

        # Status bar at bottom
        self.agent_status = AgentStatusBar(id="status-bar")
        yield self.agent_status

        yield Footer()

    def on_mount(self) -> None:
        """Set up the application when mounted."""
        # Set up refresh timer (every 5 seconds)
        self.set_interval(self._refresh_data, 5.0)

    def _refresh_data(self) -> None:
        """Refresh all data from the database."""
        try:
            if self.task_table:
                self.task_table.refresh_tasks()

            if self.initiative_panel:
                self.initiative_panel.refresh_initiatives()

            if self.agent_status:
                self.agent_status.refresh_agent_status()

        except Exception as e:
            self.log(f"Error refreshing data: {e}")

    def action_complete_task(self) -> None:
        """Complete the currently selected task."""
        if not self.task_table:
            return

        task_data = self.task_table.get_selected_task()
        if not task_data:
            self.notify("No task selected", severity="warning")
            return

        task_id = task_data['id']
        task_title = task_data['title']

        # Show confirmation
        def do_complete():
            try:
                with get_db_session() as db:
                    service = TaskService(db)
                    task = service.get_task(task_id)
                    if task:
                        from src.models.task import TaskStatus
                        service.update_task(task, status=TaskStatus.COMPLETED)
                        self.notify(f"Completed: {task_title}", severity="information")
                    else:
                        self.notify("Task not found", severity="error")
                self._refresh_data()

            except Exception as e:
                self.notify(f"Error completing task: {e}", severity="error")

        self.notify(f"Complete '{task_title}'?", severity="information")
        # For now, just complete directly (we'll add proper confirmation in Phase 2)
        do_complete()

    def action_delete_task(self) -> None:
        """Delete the currently selected task."""
        if not self.task_table:
            return

        task_data = self.task_table.get_selected_task()
        if not task_data:
            self.notify("No task selected", severity="warning")
            return

        task_id = task_data['id']
        task_title = task_data['title']

        # For now, just do it (in Phase 2 we'll add confirmation modal)
        try:
            with get_db_session() as db:
                service = TaskService(db)
                task = service.get_task(task_id)
                if task:
                    service.delete_task(task)
                    self.notify(f"Deleted: {task_title}", severity="information")
                else:
                    self.notify("Task not found", severity="error")
            self._refresh_data()

        except Exception as e:
            self.notify(f"Error deleting task: {e}", severity="error")

    def action_show_task_list(self) -> None:
        """Show the full task list with search and filtering."""
        from src.tui.widgets.task_list_modal import TaskListModal
        modal = TaskListModal()
        self.mount(modal)
        self.notify("Full Task List: Type to search, Esc to close", severity="information")

    def action_open_link(self) -> None:
        """Open or show document links for the selected task."""
        if not self.task_table:
            return

        task_data = self.task_table.get_selected_task()
        if not task_data:
            self.notify("No task selected", severity="warning")
            return

        links = task_data.get('document_links', [])
        if not links:
            self.notify("Task has no document links", severity="warning")
            return

        # Show links modal
        from src.tui.widgets.document_links import DocumentLinksModal
        modal = DocumentLinksModal(links)
        self.mount(modal)
        msg = "Document Links: Press o+number to open, c+number to copy"
        self.notify(msg, severity="information")

    def action_poll_now(self) -> None:
        """Trigger an immediate poll."""
        try:
            from src.agent.core import get_agent
            import asyncio

            self.notify("Polling integrations...", severity="information")

            agent = get_agent()
            # Run poll asynchronously
            results = asyncio.run(agent.poll_now())

            if results:
                total_items = sum(len(r.items_found) for r in results)
                total_created = sum(len(r.tasks_created) for r in results)
                msg = f"Poll complete: {total_items} items, {total_created} tasks created"
                self.notify(msg, severity="information")
            else:
                self.notify("No integrations configured", severity="warning")

            # Update agent status and refresh data
            if self.agent_status:
                self.agent_status.set_last_poll_time(datetime.now())
            self._refresh_data()
        except Exception as e:
            self.notify(f"Poll failed: {e}", severity="error")

    def action_toggle_polling(self) -> None:
        """Toggle auto-polling on/off (Phase 3)."""
        if self.agent_status:
            self.agent_status.toggle_auto_polling()

    def action_show_help(self) -> None:
        """Show keyboard shortcuts help (Phase 4)."""
        help_text = """
        [bold]Keyboard Shortcuts[/bold]

        Navigation:
          ↑/↓ or j/k     Navigate tasks
          Enter          Expand task details
          Esc            Close modal

        Task Actions:
          c              Complete selected task
          d              Delete selected task
          m              Mark for merge (Phase 2)
          l              Show full task list
          o              Open document links

        Agent Control:
          p              Poll agent now (Phase 3)
          a              Toggle auto-polling

        Other:
          ?              Show this help
          q              Quit

        Coming in Phase 2:
          - Task filtering and search
          - Sort controls
          - Document link modal

        Coming in Phase 3:
          - Manual polling
          - Poll interval adjustment

        Coming in Phase 4:
          - Task merge
          - Mouse support
          - Theme support
        """

        self.notify(help_text, title="Help")

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()


def main():
    """Run the TUI application."""
    app = TaskDashboardApp()
    app.run()


if __name__ == "__main__":
    main()
