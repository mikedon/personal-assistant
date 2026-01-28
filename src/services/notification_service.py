"""Notification service for macOS notifications and terminal alerts.

Supports native macOS notifications via osascript and fallback terminal alerts.
"""

import logging
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from src.models.task import Task, TaskStatus
from src.services.task_service import TaskService
from src.utils.config import NotificationConfig

logger = logging.getLogger(__name__)


class NotificationType(str, Enum):
    """Types of notifications."""

    INFO = "info"
    WARNING = "warning"
    URGENT = "urgent"
    REMINDER = "reminder"
    TASK_DUE = "task_due"
    TASK_OVERDUE = "task_overdue"
    TASK_CREATED = "task_created"


@dataclass
class Notification:
    """A notification to be sent."""

    title: str
    message: str
    type: NotificationType = NotificationType.INFO
    sound: bool = True
    subtitle: str | None = None
    url: str | None = None  # For clickable notifications


class NotificationService:
    """Service for sending notifications."""

    def __init__(self, config: NotificationConfig):
        """Initialize the notification service.

        Args:
            config: Notification configuration
        """
        self.config = config
        self._is_macos = sys.platform == "darwin"

    def send(self, notification: Notification) -> bool:
        """Send a notification.

        Args:
            notification: The notification to send

        Returns:
            True if notification was sent successfully
        """
        if not self.config.enabled:
            logger.debug("Notifications disabled, skipping")
            return False

        # Determine sound setting
        play_sound = notification.sound and self.config.sound

        if self._is_macos:
            return self._send_macos_notification(notification, play_sound)
        else:
            return self._send_terminal_notification(notification)

    def _send_macos_notification(
        self,
        notification: Notification,
        play_sound: bool,
    ) -> bool:
        """Send a macOS notification using osascript.

        Args:
            notification: The notification to send
            play_sound: Whether to play a sound

        Returns:
            True if successful
        """
        try:
            # Build AppleScript command
            script_parts = [
                f'display notification "{self._escape_applescript(notification.message)}"',
                f'with title "{self._escape_applescript(notification.title)}"',
            ]

            if notification.subtitle:
                script_parts.append(
                    f'subtitle "{self._escape_applescript(notification.subtitle)}"'
                )

            if play_sound:
                script_parts.append('sound name "default"')

            script = " ".join(script_parts)

            # Execute via osascript
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                logger.error(f"osascript failed: {result.stderr}")
                return False

            logger.debug(f"Sent macOS notification: {notification.title}")
            return True

        except subprocess.TimeoutExpired:
            logger.error("Notification timed out")
            return False
        except Exception as e:
            logger.error(f"Failed to send macOS notification: {e}")
            return False

    def _send_terminal_notification(self, notification: Notification) -> bool:
        """Send a terminal notification (fallback for non-macOS).

        Args:
            notification: The notification to send

        Returns:
            True (always succeeds for terminal output)
        """
        # Use ANSI colors for different notification types
        colors = {
            NotificationType.INFO: "\033[94m",  # Blue
            NotificationType.WARNING: "\033[93m",  # Yellow
            NotificationType.URGENT: "\033[91m",  # Red
            NotificationType.REMINDER: "\033[95m",  # Magenta
            NotificationType.TASK_DUE: "\033[93m",  # Yellow
            NotificationType.TASK_OVERDUE: "\033[91m",  # Red
            NotificationType.TASK_CREATED: "\033[92m",  # Green
        }
        reset = "\033[0m"
        color = colors.get(notification.type, "\033[0m")

        # Print notification
        print(f"\n{color}╔{'═' * 50}╗{reset}")
        print(f"{color}║ 🔔 {notification.title}{reset}")
        if notification.subtitle:
            print(f"{color}║    {notification.subtitle}{reset}")
        print(f"{color}║{reset}")
        print(f"{color}║ {notification.message}{reset}")
        print(f"{color}╚{'═' * 50}╝{reset}\n")

        # Ring terminal bell if sound enabled
        if notification.sound and self.config.sound:
            print("\a", end="", flush=True)

        return True

    def _escape_applescript(self, text: str) -> str:
        """Escape text for AppleScript.

        Args:
            text: Text to escape

        Returns:
            Escaped text safe for AppleScript
        """
        return text.replace("\\", "\\\\").replace('"', '\\"')

    def notify_task_due_soon(self, task: Task) -> bool:
        """Send notification for a task due soon.

        Args:
            task: The task that's due soon

        Returns:
            True if notification sent
        """
        if not self.config.on_due_soon:
            return False

        hours_until_due = 0
        if task.due_date:
            now = datetime.now(UTC).replace(tzinfo=None)
            hours_until_due = (task.due_date - now).total_seconds() / 3600

        notification = Notification(
            title="Task Due Soon",
            message=task.title[:100],
            subtitle=f"Due in {int(hours_until_due)} hours" if hours_until_due > 0 else "Due now",
            type=NotificationType.TASK_DUE,
        )
        return self.send(notification)

    def notify_task_overdue(self, task: Task) -> bool:
        """Send notification for an overdue task.

        Args:
            task: The overdue task

        Returns:
            True if notification sent
        """
        if not self.config.on_overdue:
            return False

        notification = Notification(
            title="⚠️ Overdue Task",
            message=task.title[:100],
            subtitle=f"Was due: {task.due_date.strftime('%Y-%m-%d %H:%M')}" if task.due_date else None,
            type=NotificationType.TASK_OVERDUE,
        )
        return self.send(notification)

    def notify_task_created(self, task: Task, source: str) -> bool:
        """Send notification for a newly created task.

        Args:
            task: The created task
            source: Source of the task (email, slack, etc.)

        Returns:
            True if notification sent
        """
        if not self.config.on_task_created:
            return False

        notification = Notification(
            title="New Task Created",
            message=task.title[:100],
            subtitle=f"From: {source}",
            type=NotificationType.TASK_CREATED,
            sound=False,  # Less intrusive for auto-created tasks
        )
        return self.send(notification)

    def notify_info(self, title: str, message: str) -> bool:
        """Send an informational notification.

        Args:
            title: Notification title
            message: Notification message

        Returns:
            True if notification sent
        """
        notification = Notification(
            title=title,
            message=message,
            type=NotificationType.INFO,
            sound=False,
        )
        return self.send(notification)

    def notify_warning(self, title: str, message: str) -> bool:
        """Send a warning notification.

        Args:
            title: Notification title
            message: Notification message

        Returns:
            True if notification sent
        """
        notification = Notification(
            title=f"⚠️ {title}",
            message=message,
            type=NotificationType.WARNING,
        )
        return self.send(notification)

    def notify_urgent(self, title: str, message: str) -> bool:
        """Send an urgent notification.

        Args:
            title: Notification title
            message: Notification message

        Returns:
            True if notification sent
        """
        notification = Notification(
            title=f"🚨 {title}",
            message=message,
            type=NotificationType.URGENT,
        )
        return self.send(notification)

    def check_and_notify_due_tasks(self, db: Session) -> int:
        """Check for due/overdue tasks and send notifications.

        Args:
            db: Database session

        Returns:
            Number of notifications sent
        """
        task_service = TaskService(db)
        notifications_sent = 0

        # Check overdue tasks
        if self.config.on_overdue:
            overdue = task_service.get_overdue_tasks()
            for task in overdue[:5]:  # Limit to avoid notification spam
                if self.notify_task_overdue(task):
                    notifications_sent += 1

        # Check tasks due soon
        if self.config.on_due_soon:
            # Get tasks due within configured hours
            hours = self.config.due_soon_hours
            due_soon = task_service.get_due_soon_tasks(days=0)

            now = datetime.now(UTC).replace(tzinfo=None)
            for task in due_soon:
                if task.due_date:
                    hours_until = (task.due_date - now).total_seconds() / 3600
                    if 0 < hours_until <= hours:
                        if self.notify_task_due_soon(task):
                            notifications_sent += 1

        return notifications_sent


def create_notification_service(config: NotificationConfig | None = None) -> NotificationService:
    """Create a notification service with config.

    Args:
        config: Optional notification config (uses default if not provided)

    Returns:
        NotificationService instance
    """
    if config is None:
        from src.utils.config import get_config
        config = get_config().notifications
    return NotificationService(config)
