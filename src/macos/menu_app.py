"""macOS menu bar application for displaying task summaries.

Creates a status item in the macOS menu bar that shows the count of
tasks due today or overdue, with a dropdown menu for quick access.
"""

import signal
import threading
from typing import Any

import httpx
import objc
from AppKit import (
    NSApp,
    NSApplication,
    NSMenu,
    NSMenuItem,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSBundle, NSObject, NSTimer


class MenuDelegate(NSObject):
    """Delegate object for handling menu actions."""

    def init(self):
        """Initialize the delegate."""
        self = objc.super(MenuDelegate, self).init()
        if self is None:
            return None
        self.app = None
        return self

    def setApp_(self, app):
        """Set the app reference."""
        self.app = app

    def testAction_(self, sender):
        """Test action."""
        print("hello world")
        if self.app:
            self.app.on_test_action()

    def refreshTasks_(self, sender):
        """Refresh tasks action."""
        if self.app:
            self.app.refresh_tasks(sender)

    def openDashboard_(self, sender):
        """Open dashboard action."""
        if self.app:
            self.app.open_dashboard(sender)

    def quitApp_(self, sender):
        """Quit app action."""
        if self.app:
            self.app.quit_app(sender)


class TaskMenuApp(NSObject):
    """macOS menu bar application for task display and management."""

    def init(self):
        """Initialize the menu bar app."""
        self = objc.super(TaskMenuApp, self).init()
        if self is None:
            return None

        # Initialize with defaults - will be set by configure method
        self.api_url = "http://localhost:8000"
        self.refresh_interval = 30
        self.status_bar = NSStatusBar.systemStatusBar()
        self.status_item = None
        self.menu = None
        self.client = httpx.Client(timeout=10.0)

        # Task data cache
        self.overdue_count = 0
        self.due_today_count = 0
        self.total_count = 0
        self.tasks = []
        
        # Create a helper object to handle menu actions
        self.menu_delegate = MenuDelegate.alloc().init()
        self.menu_delegate.setApp_(self)
        return self

    @objc.python_method
    def configure(self, api_url: str, refresh_interval: int) -> None:
        """Configure the app after initialization.

        Args:
            api_url: Base URL of the personal assistant API
            refresh_interval: How often to refresh task data (seconds)
        """
        self.api_url = api_url
        self.refresh_interval = refresh_interval

    def setup_menu_bar(self) -> None:
        """Set up the menu bar item and menu."""
        # Set the application name for System Preferences
        app = NSApplication.sharedApplication()
        bundle = NSBundle.mainBundle()
        bundle.infoDictionary()["CFBundleName"] = "Personal Assistant"
        
        # Create status bar item
        self.status_item = self.status_bar.statusItemWithLength_(NSVariableStatusItemLength)
        self.status_item.setHighlightMode_(True)

        # Initial title
        self._update_menu_bar_title()

        # Create menu
        self.menu = NSMenu.alloc().init()
        self.status_item.setMenu_(self.menu)

        # Build the initial menu (even before first data fetch)
        self._rebuild_menu()

        # Add a refresh timer - use refresh_tasks_timer: selector instead of refresh_tasks:
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            self.refresh_interval,
            self,
            "refreshTasksTimer:",
            None,
            True,
        )

    @objc.python_method
    def _update_menu_bar_title(self) -> None:
        """Update the menu bar title with current counts."""
        if self.total_count == 0:
            title = "✓"
        else:
            title = f"{self.total_count}"

        self.status_item.setTitle_(title)

    def refreshTasksTimer_(self, sender: Any = None) -> None:
        """Refresh task data from API (called by NSTimer).

        Args:
            sender: Timer object (unused)
        """
        # Run API call in background thread to avoid blocking UI
        thread = threading.Thread(target=self._fetch_and_update_tasks)
        thread.daemon = True
        thread.start()
    
    @objc.python_method
    def refresh_tasks(self, sender: Any = None) -> None:
        """Refresh task data from API (called by menu item or programmatically).

        Args:
            sender: Menu item or None (unused)
        """
        self.refreshTasksTimer_(sender)

    @objc.python_method
    def _fetch_and_update_tasks(self) -> None:
        """Fetch task data from API and update menu (runs in background thread)."""
        try:
            response = self.client.get(f"{self.api_url}/api/status/tasks/today-due")
            response.raise_for_status()

            data = response.json()
            self.overdue_count = int(data.get("overdue_count", 0))
            self.due_today_count = int(data.get("due_today_count", 0))
            self.total_count = int(data.get("total_count", 0))
            self.tasks = list(data.get("tasks", []))

            # Update UI on main thread
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "updateUIOnMainThread:", None, False
            )

        except Exception as e:
            # Log but don't crash - menu will show last known state
            print(f"Error fetching tasks: {e}")
            import traceback
            traceback.print_exc()


    def updateUIOnMainThread_(self, _: Any = None) -> None:
        """Update menu bar title and menu items on the main thread.

        This method is exposed to Objective-C (no @objc.python_method) so it can be
        called via performSelectorOnMainThread.

        Args:
            _: Unused parameter (required by PyObjC selector)
        """
        # Update title
        if self.status_item is not None:
            self._update_menu_bar_title()

            # Update menu
            if self.menu is not None:
                self._rebuild_menu()

    @objc.python_method
    def _rebuild_menu(self) -> None:
        """Rebuild the menu with current task data."""
        if self.menu is None:
            return
            
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

        # Task items (only show if total_count > 0)
            for task in self.tasks:
                task_id = task.get("id", "?")
                title = task.get("title", "Untitled")
                priority = task.get("priority", "medium")

                # Normalize priority to uppercase for symbol lookup
                if isinstance(priority, str):
                    priority = priority.upper()
                else:
                    priority = str(priority).upper()

                # Format: Priority indicator + Title
                priority_symbol = self._get_priority_symbol(priority)
                menu_title = f"{priority_symbol} {title}"

                item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    menu_title, None, ""
                )
                # Create a closure that captures task_id
                def make_task_handler(tid):
                    def handler(sender=None):
                        self.task_item_clicked_with_id(tid)
                    return handler
                
                item.setTarget_(self)
                item.setAction_(objc.selector(make_task_handler(task_id), signature=b'v@:'))
                item.setEnabled_(True)
                self.menu.addItem_(item)

        # Separator
        self.menu.addItem_(NSMenuItem.separatorItem())

        # Test item
        test_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Test", None, ""
        )
        test_item.setTarget_(self.menu_delegate)
        test_item.setAction_("testAction:")
        test_item.setEnabled_(True)
        self.menu.addItem_(test_item)

        # Open in Browser item
        open_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Open Dashboard", None, ""
        )
        open_item.setTarget_(self.menu_delegate)
        open_item.setAction_("openDashboard:")
        open_item.setEnabled_(True)
        self.menu.addItem_(open_item)

        # Refresh item
        refresh_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Refresh", None, ""
        )
        refresh_item.setTarget_(self.menu_delegate)
        refresh_item.setAction_("refreshTasks:")
        refresh_item.setEnabled_(True)
        self.menu.addItem_(refresh_item)

        # Separator
        self.menu.addItem_(NSMenuItem.separatorItem())

        # Quit item (with Cmd+Q keyboard shortcut)
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit Personal Assistant", None, "q"
        )
        quit_item.setKeyEquivalentModifierMask_(0x100000)  # Cmd key
        quit_item.setTarget_(self.menu_delegate)
        quit_item.setAction_("quitApp:")
        quit_item.setEnabled_(True)
        self.menu.addItem_(quit_item)

    @objc.python_method
    def _build_summary_text(self) -> str:
        """Build summary text for menu title."""
        parts = []
        if self.overdue_count > 0:
            parts.append(f"{self.overdue_count} overdue")
        if self.due_today_count > 0:
            parts.append(f"{self.due_today_count} due today")

        return " • ".join(parts) if parts else f"{self.total_count} tasks"

    def task_item_clicked_with_id(self, task_id: int) -> None:
        """Handle task menu item click with specific task ID.

        Args:
            task_id: ID of the clicked task
        """
        print(f"Task clicked: {task_id}")

    @objc.python_method
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

    def on_test_action(self) -> None:
        """Handle test action."""
        print("Test action executed!")

    def open_dashboard(self, sender: Any = None) -> None:
        """Open the dashboard in a browser.

        Args:
            sender: Menu item (unused)
        """
        import subprocess

        subprocess.Popen(["open", f"{self.api_url}/docs"])

    def task_item_clicked(self, sender: Any = None) -> None:
        """Handle task menu item click.

        Args:
            sender: Menu item
        """
        # Placeholder for future task action handling
        if sender and hasattr(sender, "representedObject"):
            task_id = sender.representedObject()
            print(f"Task clicked: {task_id}")
        else:
            print(f"Task clicked: {sender}")

    def quit_app(self, sender: Any = None) -> None:
        """Quit the application.

        Args:
            sender: Menu item (unused)
        """
        self.client.close()
        NSApp.terminate_(self)

    @objc.python_method
    def run(self) -> None:
        """Run the application main loop. Pure Python, not called as Objective-C selector."""
        # Set up signal handler for graceful shutdown
        def signal_handler(sig, frame):
            print("\n[Shutting down...]")
            self.quit_app()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        self.setup_menu_bar()

        # Initial fetch
        self.refresh_tasks()

        # Run NSApplication on the main thread (required for macOS Cocoa)
        NSApplication.sharedApplication().run()


def run_menu_app(api_url: str = "http://localhost:8000", refresh_interval: int = 300) -> None:
    """Start the menu bar application.

    Args:
        api_url: Base URL of the personal assistant API
        refresh_interval: How often to refresh task data (seconds)
    """
    app = TaskMenuApp.alloc().init()
    app.configure(api_url, refresh_interval)
    app.run()


if __name__ == "__main__":
    run_menu_app()
