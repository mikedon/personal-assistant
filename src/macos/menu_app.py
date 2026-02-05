"""macOS menu bar application for displaying task summaries.

Creates a status item in the macOS menu bar that shows the count of
tasks due today or overdue, with a dropdown menu for quick access.
"""

import signal
import threading
from typing import Any

import httpx
from AppKit import (
    NSApp,
    NSApplication,
    NSMenu,
    NSMenuItem,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSTimer


class TaskMenuApp:
    """macOS menu bar application for task display and management."""

    def __init__(self, api_url: str = "http://localhost:8000", refresh_interval: int = 300):
        """Initialize the menu bar app.

        Args:
            api_url: Base URL of the personal assistant API
            refresh_interval: How often to refresh task data (seconds)
        """
        self.api_url = api_url
        self.refresh_interval = refresh_interval
        self.status_bar = NSStatusBar.systemStatusBar()
        self.status_item = None
        self.menu = None
        self.client = httpx.Client(timeout=10.0)

        # Task data cache
        self.overdue_count = 0
        self.due_today_count = 0
        self.total_count = 0
        self.tasks = []

    def setup_menu_bar(self) -> None:
        """Set up the menu bar item and menu."""
        # Create status bar item
        self.status_item = self.status_bar.statusItemWithLength_(NSVariableStatusItemLength)
        self.status_item.setHighlightMode_(True)

        # Initial title
        self._update_menu_bar_title()

        # Create menu
        self.menu = NSMenu.alloc().init()
        self.status_item.setMenu_(self.menu)

        # Add a refresh timer
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            self.refresh_interval,
            self,
            "refresh_tasks:",
            None,
            True,
        )

    def _update_menu_bar_title(self) -> None:
        """Update the menu bar title with current counts."""
        if self.total_count == 0:
            title = "✓"
        else:
            title = f"{self.total_count}"

        self.status_item.setTitle_(title)

    def refresh_tasks(self, sender: Any = None) -> None:
        """Refresh task data from API (called by timer).

        Args:
            sender: Timer object (unused)
        """
        # Run API call in background thread to avoid blocking UI
        thread = threading.Thread(target=self._fetch_and_update_tasks)
        thread.daemon = True
        thread.start()

    def _fetch_and_update_tasks(self) -> None:
        """Fetch task data from API and update menu (runs in background thread)."""
        try:
            response = self.client.get(f"{self.api_url}/api/status/tasks/today-due")
            response.raise_for_status()

            data = response.json()
            self.overdue_count = data.get("overdue_count", 0)
            self.due_today_count = data.get("due_today_count", 0)
            self.total_count = data.get("total_count", 0)
            self.tasks = data.get("tasks", [])

            # Update UI on main thread
            self._update_ui()

        except Exception as e:
            # Log but don't crash - menu will show last known state
            print(f"Error fetching tasks: {e}")

    def _update_ui(self) -> None:
        """Update menu bar title and menu items (must run on main thread).

        This is called from the background thread, so we dispatch to main thread.
        """
        # Update title
        self._update_menu_bar_title()

        # Update menu
        self._rebuild_menu()

    def _rebuild_menu(self) -> None:
        """Rebuild the menu with current task data."""
        self.menu.removeAllItems()

        # Title section
        if self.total_count == 0:
            title_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "No tasks due today or overdue", None, ""
            )
            title_item.setEnabled_(False)
            self.menu.addItem_(title_item)
        else:
            # Summary item
            summary_text = self._build_summary_text()
            summary_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                summary_text, None, ""
            )
            summary_item.setEnabled_(False)
            self.menu.addItem_(summary_item)

            # Separator
            self.menu.addItem_(NSMenuItem.separatorItem())

            # Task items
            for task in self.tasks:
                self._add_task_menu_item(task)

        # Separator
        self.menu.addItem_(NSMenuItem.separatorItem())

        # Open in Browser item
        open_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Open Dashboard", self, "open_dashboard:"
        )
        self.menu.addItem_(open_item)

        # Refresh item
        refresh_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Refresh", self, "refresh_tasks:"
        )
        self.menu.addItem_(refresh_item)

        # Separator
        self.menu.addItem_(NSMenuItem.separatorItem())

        # Quit item (with Cmd+Q keyboard shortcut)
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit Personal Assistant", self, "q"
        )
        quit_item.setKeyEquivalentModifierMask_(0x100000)  # Cmd key
        quit_item.setTarget_(self)
        quit_item.setAction_("quit_app:")
        self.menu.addItem_(quit_item)

    def _build_summary_text(self) -> str:
        """Build summary text for menu title."""
        parts = []
        if self.overdue_count > 0:
            parts.append(f"{self.overdue_count} overdue")
        if self.due_today_count > 0:
            parts.append(f"{self.due_today_count} due today")

        return " • ".join(parts) if parts else f"{self.total_count} tasks"

    def _add_task_menu_item(self, task: dict) -> None:
        """Add a task as a menu item.

        Args:
            task: Task dictionary from API response
        """
        task_id = task.get("id", "?")
        title = task.get("title", "Untitled")
        priority = task.get("priority", "medium").upper()

        # Format: Priority indicator + Title
        priority_symbol = self._get_priority_symbol(priority)
        menu_title = f"{priority_symbol} {title}"

        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            menu_title, self, f"task_clicked:{task_id}"
        )

        self.menu.addItem_(item)

    def _get_priority_symbol(self, priority: str) -> str:
        """Get a visual symbol for priority level.

        Args:
            priority: Priority level string

        Returns:
            Visual symbol
        """
        symbols = {
            "CRITICAL": "🔴",
            "HIGH": "🟠",
            "MEDIUM": "🟡",
            "LOW": "🟢",
        }
        return symbols.get(priority, "○")

    def open_dashboard(self, sender: Any = None) -> None:
        """Open the dashboard in a browser.

        Args:
            sender: Menu item (unused)
        """
        import subprocess

        subprocess.Popen(["open", f"{self.api_url}/docs"])

    def task_clicked(self, sender: Any = None) -> None:
        """Handle task menu item click.

        Args:
            sender: Menu item
        """
        # Placeholder for future task action handling
        print(f"Task clicked: {sender}")

    def quit_app(self, sender: Any = None) -> None:
        """Quit the application.

        Args:
            sender: Menu item (unused)
        """
        self.client.close()
        NSApp.terminate_(self)

    def run(self) -> None:
        """Run the application main loop."""
        # Set up signal handler for graceful shutdown
        def signal_handler(sig, frame):
            print("\n[Shutting down...]")
            self.quit_app()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        self.setup_menu_bar()

        # Initial fetch
        self.refresh_tasks()

        # Start the app
        NSApplication.sharedApplication().run()


def run_menu_app(api_url: str = "http://localhost:8000", refresh_interval: int = 300) -> None:
    """Start the menu bar application.

    Args:
        api_url: Base URL of the personal assistant API
        refresh_interval: How often to refresh task data (seconds)
    """
    app = TaskMenuApp(api_url=api_url, refresh_interval=refresh_interval)
    app.run()


if __name__ == "__main__":
    run_menu_app()
