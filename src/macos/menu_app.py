"""macOS menu bar application with agent status and control.

Displays task information and provides agent management features via menu bar:
- Task counts (overdue, due today)
- Agent status (running/stopped with visual indicators)
- Quick actions (Start/Stop Agent, Poll Now)
- Recent agent activity logs
"""

import asyncio
import logging
import signal
import threading
from datetime import datetime
from typing import Any, Optional

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

from src.macos.agent_status import AgentStatusManager
from src.macos.quick_input import QuickInputManager
from src.macos.settings_window import SettingsWindowController

logger = logging.getLogger(__name__)


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

    def refreshTasks_(self, sender):
        """Refresh tasks action."""
        if self.app:
            self.app.refresh_tasks(sender)

    def openDashboard_(self, sender):
        """Open dashboard action."""
        if self.app:
            self.app.open_dashboard(sender)

    def startAgent_(self, sender):
        """Start agent action."""
        if self.app:
            self.app.start_agent_action(sender)

    def stopAgent_(self, sender):
        """Stop agent action."""
        if self.app:
            self.app.stop_agent_action(sender)

    def pollNow_(self, sender):
        """Poll now action."""
        if self.app:
            self.app.poll_now_action(sender)

    def showSettings_(self, sender):
        """Show settings window action."""
        if self.app:
            self.app.show_settings(sender)

    def showQuickInput_(self, sender):
        """Show quick input popup action."""
        if self.app:
            self.app.show_quick_input(sender)

    def quitApp_(self, sender):
        """Quit app action."""
        if self.app:
            self.app.quit_app(sender)


class TaskMenuApp(NSObject):
    """macOS menu bar application with task display and agent control."""

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
        self.agent_manager = None

        # Task data cache
        self.overdue_count = 0
        self.due_today_count = 0
        self.total_count = 0
        self.tasks = []

        # Agent data cache
        self.agent_status = None
        self.agent_logs = []
        self.last_agent_status_update = None

        # Create a helper object to handle menu actions
        self.menu_delegate = MenuDelegate.alloc().init()
        self.menu_delegate.setApp_(self)
        
        # Settings window controller
        self.settings_window = None
        
        # Quick input manager
        self.quick_input_manager = None
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
        self.agent_manager = AgentStatusManager(api_url=api_url)
        self.settings_window = SettingsWindowController.alloc().init(api_url=api_url)
        self.quick_input_manager = QuickInputManager(api_url=api_url)
        self.quick_input_manager.setup()

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

        # Add refresh timers
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            self.refresh_interval,
            self,
            "refreshTasksTimer:",
            None,
            True,
        )

        # Update agent status more frequently (every 10 seconds)
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            10.0,
            self,
            "refreshAgentStatusTimer:",
            None,
            True,
        )

    @objc.python_method
    def _update_menu_bar_title(self) -> None:
        """Update the menu bar title with current counts."""
        if self.total_count == 0 and (self.agent_status is None or not self.agent_status.is_running):
            title = "✓"
        elif self.agent_status and self.agent_status.is_running:
            # Show agent indicator if running
            agent_indicator = "▶"  # Running indicator
            task_count = f" {self.total_count}" if self.total_count > 0 else ""
            title = f"{agent_indicator}{task_count}"
        else:
            title = f"{self.total_count}" if self.total_count > 0 else "✓"

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

    def refreshAgentStatusTimer_(self, sender: Any = None) -> None:
        """Refresh agent status from API (called by NSTimer).

        Args:
            sender: Timer object (unused)
        """
        # Run API call in background thread
        thread = threading.Thread(target=self._fetch_and_update_agent_status)
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
            logger.warning(f"Error fetching tasks: {e}")

    @objc.python_method
    def _fetch_and_update_agent_status(self) -> None:
        """Fetch agent status from API (runs in background thread)."""
        if not self.agent_manager:
            return

        try:
            # Get agent status (uses caching)
            status = self.agent_manager.get_status(use_cache=False)
            self.agent_status = status
            self.last_agent_status_update = datetime.now()

            # Get recent logs
            self.agent_logs = self.agent_manager.get_logs(limit=5, hours=24)

            # Update UI on main thread
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "updateUIOnMainThread:", None, False
            )

        except Exception as e:
            logger.warning(f"Error fetching agent status: {e}")

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
        """Rebuild the menu with current task and agent data."""
        if self.menu is None:
            return

        self.menu.removeAllItems()

        # --- Quick Input Section ---
        quick_input_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "✏ Quick Input", None, "a"
        )
        quick_input_item.setKeyEquivalentModifierMask_(0x180000)  # Cmd+Shift
        quick_input_item.setTarget_(self.menu_delegate)
        quick_input_item.setAction_("showQuickInput:")
        quick_input_item.setEnabled_(True)
        self.menu.addItem_(quick_input_item)

        # Settings
        settings_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "⚙ Settings", None, ","
        )
        settings_item.setKeyEquivalentModifierMask_(0x100000)  # Cmd key
        settings_item.setTarget_(self.menu_delegate)
        settings_item.setAction_("showSettings:")
        settings_item.setEnabled_(True)
        self.menu.addItem_(settings_item)

        # Separator after quick input/settings
        self.menu.addItem_(NSMenuItem.separatorItem())

        # --- Agent Status Section ---
        if self.agent_status:
            agent_status_text = self._get_agent_status_text()
            agent_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                agent_status_text, None, ""
            )
            agent_item.setEnabled_(False)
            self.menu.addItem_(agent_item)

            # Start/Stop Agent
            if self.agent_status.is_running:
                stop_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "■ Stop Agent", None, ""
                )
                stop_item.setTarget_(self.menu_delegate)
                stop_item.setAction_("stopAgent:")
                stop_item.setEnabled_(True)
                self.menu.addItem_(stop_item)
            else:
                start_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "▶ Start Agent", None, ""
                )
                start_item.setTarget_(self.menu_delegate)
                start_item.setAction_("startAgent:")
                start_item.setEnabled_(True)
                self.menu.addItem_(start_item)

            # Poll Now (only if agent is running)
            if self.agent_status.is_running:
                poll_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "⟳ Poll Now", None, ""
                )
                poll_item.setTarget_(self.menu_delegate)
                poll_item.setAction_("pollNow:")
                poll_item.setEnabled_(True)
                self.menu.addItem_(poll_item)

            # Last Poll timestamp
            if self.agent_status.last_poll:
                last_poll_text = f"Last poll: {self.agent_status.last_poll}"
                last_poll_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    last_poll_text, None, ""
                )
                last_poll_item.setEnabled_(False)
                self.menu.addItem_(last_poll_item)

            # Recent logs
            if self.agent_logs:
                logs_separator = NSMenuItem.separatorItem()
                self.menu.addItem_(logs_separator)

                logs_header = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "Recent Activity", None, ""
                )
                logs_header.setEnabled_(False)
                self.menu.addItem_(logs_header)

                for log in self.agent_logs[:5]:  # Show max 5 logs
                    log_text = f"• {log.message}"
                    log_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        log_text, None, ""
                    )
                    log_item.setEnabled_(False)
                    self.menu.addItem_(log_item)

            # Separator after agent section
            self.menu.addItem_(NSMenuItem.separatorItem())

        # --- Tasks Section ---
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
                document_links = task.get("document_links", [])

                # Normalize priority to uppercase for symbol lookup
                if isinstance(priority, str):
                    priority = priority.upper()
                else:
                    priority = str(priority).upper()

                # Format: Priority indicator + Title + Link indicator (if has links)
                priority_symbol = self._get_priority_symbol(priority)
                link_indicator = " 🔗" if document_links else ""
                menu_title = f"{priority_symbol} {title}{link_indicator}"

                item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    menu_title, None, ""
                )
                # Create a closure that captures task_id
                def make_task_handler(tid):
                    def handler(sender=None):
                        self.task_item_clicked_with_id(tid)
                    return handler

                item.setTarget_(self)
                item.setAction_(objc.selector(make_task_handler(task_id), signature=b"v@:"))
                item.setEnabled_(True)
                self.menu.addItem_(item)

        # --- Actions Section ---
        # Separator
        self.menu.addItem_(NSMenuItem.separatorItem())

        # Open Dashboard item
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

    @objc.python_method
    def _get_agent_status_text(self) -> str:
        """Get formatted agent status text."""
        if not self.agent_status:
            return "Agent status unknown"

        status = "🟢 Running" if self.agent_status.is_running else "⚫ Stopped"
        autonomy = self.agent_status.autonomy_level or "unknown"
        return f"{status} • {autonomy}"

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

    def start_agent_action(self, sender: Any = None) -> None:
        """Start agent action handler.

        Args:
            sender: Menu item (unused)
        """
        if not self.agent_manager:
            return

        # Run in background thread to avoid blocking UI
        thread = threading.Thread(target=self._start_agent_thread)
        thread.daemon = True
        thread.start()

    def stop_agent_action(self, sender: Any = None) -> None:
        """Stop agent action handler.

        Args:
            sender: Menu item (unused)
        """
        if not self.agent_manager:
            return

        # Run in background thread to avoid blocking UI
        thread = threading.Thread(target=self._stop_agent_thread)
        thread.daemon = True
        thread.start()

    def poll_now_action(self, sender: Any = None) -> None:
        """Poll now action handler.

        Args:
            sender: Menu item (unused)
        """
        if not self.agent_manager or not self.agent_status or not self.agent_status.is_running:
            return

        # Run in background thread to avoid blocking UI
        thread = threading.Thread(target=self._poll_now_thread)
        thread.daemon = True
        thread.start()

    def show_settings(self, sender: Any = None) -> None:
        """Show settings window.

        Args:
            sender: Menu item (unused)
        """
        if self.settings_window:
            self.settings_window.show_window()

    def show_quick_input(self, sender: Any = None) -> None:
        """Show quick input popup.

        Args:
            sender: Menu item (unused)
        """
        if self.quick_input_manager:
            self.quick_input_manager.show_popup()

    @objc.python_method
    def _start_agent_thread(self) -> None:
        """Start agent in background thread."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.agent_manager.start_agent())
            loop.close()

            # Refresh status
            self._fetch_and_update_agent_status()
        except Exception as e:
            logger.error(f"Failed to start agent: {e}")

    @objc.python_method
    def _stop_agent_thread(self) -> None:
        """Stop agent in background thread."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.agent_manager.stop_agent())
            loop.close()

            # Refresh status
            self._fetch_and_update_agent_status()
        except Exception as e:
            logger.error(f"Failed to stop agent: {e}")

    @objc.python_method
    def _poll_now_thread(self) -> None:
        """Poll now in background thread."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.agent_manager.poll_now())
            loop.close()

            # Refresh status
            self._fetch_and_update_agent_status()
        except Exception as e:
            logger.error(f"Failed to poll: {e}")

    def task_item_clicked_with_id(self, task_id: int) -> None:
        """Handle task menu item click with specific task ID.

        Args:
            task_id: ID of the clicked task
        """
        logger.debug(f"Task clicked: {task_id}")

    def open_dashboard(self, sender: Any = None) -> None:
        """Open the dashboard in a browser.

        Args:
            sender: Menu item (unused)
        """
        import webbrowser

        webbrowser.open(f"{self.api_url}/docs")

    def quit_app(self, sender: Any = None) -> None:
        """Quit the application.

        Args:
            sender: Menu item (unused)
        """
        if self.agent_manager:
            self.agent_manager.close()
        self.client.close()
        NSApp.terminate_(self)

    @objc.python_method
    def run(self) -> None:
        """Run the application main loop."""
        # Set up signal handler for graceful shutdown
        def signal_handler(sig, frame):
            logger.info("Shutting down...")
            self.quit_app()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        self.setup_menu_bar()

        # Initial fetch
        self.refresh_tasks()
        self._fetch_and_update_agent_status()

        # Run NSApplication on the main thread (required for macOS Cocoa)
        NSApplication.sharedApplication().run()


def run_menu_app(api_url: str = "http://localhost:8000", refresh_interval: int = 30) -> None:
    """Start the enhanced menu bar application.

    Args:
        api_url: Base URL of the personal assistant API
        refresh_interval: How often to refresh task data (seconds)
    """
    app = TaskMenuApp.alloc().init()
    app.configure(api_url, refresh_interval)
    app.run()


if __name__ == "__main__":
    run_menu_app()
