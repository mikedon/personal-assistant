"""Integration manager to coordinate all external service integrations."""

import asyncio
import logging
from typing import Any

from src.integrations.base import ActionableItem, BaseIntegration, IntegrationType
from src.integrations.gmail_integration import GmailIntegration
from src.integrations.slack_integration import SlackIntegration
from src.models.task import TaskPriority, TaskSource
from src.services.task_service import TaskService

logger = logging.getLogger(__name__)


class IntegrationManager:
    """Manages all external service integrations."""

    def __init__(self, config: dict[str, Any]):
        """Initialize integration manager.

        Args:
            config: Configuration dict with settings for all integrations
        """
        self.config = config
        self.integrations: dict[IntegrationType, BaseIntegration] = {}
        self._initialize_integrations()

    def _initialize_integrations(self) -> None:
        """Initialize all configured integrations."""
        # Gmail
        gmail_config = self.config.get("google", {})
        if gmail_config.get("enabled", False):
            try:
                self.integrations[IntegrationType.GMAIL] = GmailIntegration(gmail_config)
                logger.info("Gmail integration initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Gmail integration: {e}")

        # Slack
        slack_config = self.config.get("slack", {})
        if slack_config.get("enabled", False):
            try:
                self.integrations[IntegrationType.SLACK] = SlackIntegration(slack_config)
                logger.info("Slack integration initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Slack integration: {e}")

        # Calendar and Drive would be added similarly
        # self.integrations[IntegrationType.CALENDAR] = CalendarIntegration(...)
        # self.integrations[IntegrationType.DRIVE] = DriveIntegration(...)

    async def poll_all(self) -> dict[IntegrationType, list[ActionableItem]]:
        """Poll all enabled integrations for actionable items.

        Returns:
            Dict mapping integration type to list of actionable items found.
        """
        results = {}

        for integration_type, integration in self.integrations.items():
            if not integration.enabled:
                continue

            try:
                logger.info(f"Polling {integration_type.value}...")
                items = await integration.poll()
                results[integration_type] = items
                logger.info(f"Found {len(items)} actionable items from {integration_type.value}")
            except Exception as e:
                logger.error(f"Error polling {integration_type.value}: {e}")
                results[integration_type] = []

        return results

    async def poll_one(self, integration_type: IntegrationType) -> list[ActionableItem]:
        """Poll a specific integration.

        Args:
            integration_type: The integration to poll

        Returns:
            List of actionable items found.

        Raises:
            ValueError: If integration is not configured
        """
        integration = self.integrations.get(integration_type)
        if not integration:
            raise ValueError(f"Integration {integration_type.value} not configured")

        return await integration.poll()

    async def test_connections(self) -> dict[IntegrationType, bool]:
        """Test connections to all configured integrations.

        Returns:
            Dict mapping integration type to connection status.
        """
        results = {}

        for integration_type, integration in self.integrations.items():
            try:
                results[integration_type] = await integration.test_connection()
            except Exception as e:
                logger.error(f"Error testing {integration_type.value}: {e}")
                results[integration_type] = False

        return results

    def get_integration(self, integration_type: IntegrationType) -> BaseIntegration | None:
        """Get a specific integration.

        Args:
            integration_type: The integration type

        Returns:
            The integration instance or None if not configured.
        """
        return self.integrations.get(integration_type)

    def is_enabled(self, integration_type: IntegrationType) -> bool:
        """Check if an integration is enabled.

        Args:
            integration_type: The integration type

        Returns:
            True if enabled, False otherwise.
        """
        integration = self.integrations.get(integration_type)
        return integration is not None and integration.enabled

    @staticmethod
    def actionable_item_to_task_params(item: ActionableItem) -> dict[str, Any]:
        """Convert an ActionableItem to task creation parameters.

        Args:
            item: The actionable item

        Returns:
            Dict of parameters for TaskService.create_task
        """
        # Map item source to TaskSource
        source_mapping = {
            IntegrationType.GMAIL: TaskSource.EMAIL,
            IntegrationType.SLACK: TaskSource.SLACK,
            IntegrationType.CALENDAR: TaskSource.CALENDAR,
            IntegrationType.DRIVE: TaskSource.MEETING_NOTES,  # Approximate
        }

        # Map priority string to TaskPriority
        priority_mapping = {
            "critical": TaskPriority.CRITICAL,
            "high": TaskPriority.HIGH,
            "medium": TaskPriority.MEDIUM,
            "low": TaskPriority.LOW,
        }

        return {
            "title": item.title,
            "description": item.description,
            "priority": priority_mapping.get(item.priority, TaskPriority.MEDIUM),
            "source": source_mapping.get(item.source, TaskSource.AGENT),
            "source_reference": item.source_reference,
            "due_date": item.due_date,
            "tags": item.tags or [],
        }

    async def create_tasks_from_items(
        self,
        items: list[ActionableItem],
        task_service: TaskService,
    ) -> list[int]:
        """Create tasks from actionable items.

        Args:
            items: List of actionable items
            task_service: TaskService instance

        Returns:
            List of created task IDs.
        """
        task_ids = []

        for item in items:
            try:
                params = self.actionable_item_to_task_params(item)
                task = task_service.create_task(**params)
                task_ids.append(task.id)
                logger.info(f"Created task {task.id} from {item.source.value}: {item.title}")
            except Exception as e:
                logger.error(f"Failed to create task from item {item.title}: {e}")

        return task_ids
