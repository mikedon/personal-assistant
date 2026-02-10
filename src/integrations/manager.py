"""Integration manager to coordinate all external service integrations."""

import asyncio
import logging
from typing import Any, Callable

from src.integrations.base import ActionableItem, BaseIntegration, IntegrationType
from src.integrations.gmail_integration import GmailIntegration
from src.integrations.slack_integration import SlackIntegration
from src.models.task import TaskPriority, TaskSource
from src.services.task_service import TaskService

logger = logging.getLogger(__name__)

# Type for HTTP logging callback
HttpLogCallback = Callable[[str, str, int | None, float | None, str | None, str | None], None]


class IntegrationManager:
    """Manages all external service integrations with multi-account support."""

    def __init__(self, config: dict[str, Any], http_log_callback: HttpLogCallback | None = None):
        """Initialize integration manager.

        Args:
            config: Configuration dict with settings for all integrations
            http_log_callback: Optional callback for logging HTTP requests
        """
        self.config = config
        self._http_log_callback = http_log_callback
        # NEW: Composite key (IntegrationType, account_id) for multi-account support
        self.integrations: dict[tuple[IntegrationType, str], BaseIntegration] = {}
        self._initialize_integrations()

    def _initialize_integrations(self) -> None:
        """Initialize all configured integrations."""
        # Gmail - support multiple accounts
        google_config = self.config.get("google", {})
        if google_config.get("enabled", False):
            accounts = google_config.get("accounts", [])

            # Handle legacy single-account config (already migrated by config loader)
            if not accounts and "credentials_path" in google_config:
                # Fallback for unmigrated configs
                accounts = [{
                    "account_id": "default",
                    "credentials_path": google_config["credentials_path"],
                    "token_path": google_config.get("token_path", "token.json"),
                    "gmail": google_config.get("gmail", {}),
                }]

            for account_config in accounts:
                if not account_config.get("enabled", True):
                    logger.info(f"Skipping disabled Google account: {account_config.get('account_id')}")
                    continue

                try:
                    # Import GoogleAccountConfig for type checking
                    from src.utils.config import GoogleAccountConfig

                    # Convert dict to Pydantic model if needed
                    if isinstance(account_config, dict):
                        account = GoogleAccountConfig(**account_config)
                    else:
                        account = account_config

                    # Initialize Gmail integration for this account
                    integration = GmailIntegration(account_config=account)
                    integration.set_http_log_callback(self._http_log_callback)

                    # Store with composite key
                    key = (IntegrationType.GMAIL, account.account_id)
                    self.integrations[key] = integration

                    logger.info(f"Gmail integration initialized for account: {account.account_id}")

                except Exception as e:
                    logger.error(
                        f"Failed to initialize Gmail for {account_config.get('account_id')}: {e}"
                    )

        # Slack - single account for now (can be extended later)
        slack_config = self.config.get("slack", {})
        if slack_config.get("enabled", False):
            try:
                integration = SlackIntegration(slack_config)
                integration.set_http_log_callback(self._http_log_callback)
                # Use "default" as account_id for single-account integrations
                key = (IntegrationType.SLACK, "default")
                self.integrations[key] = integration
                logger.info("Slack integration initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Slack integration: {e}")

    async def poll_all(self) -> list[ActionableItem]:
        """Poll all enabled integrations for actionable items.

        Returns:
            Combined list of actionable items from all integrations.
        """
        all_items = []

        for key, integration in self.integrations.items():
            integration_type, account_id = key
            if not integration.enabled:
                continue

            try:
                logger.info(f"Polling {integration_type.value}:{account_id}...")
                items = await integration.poll()
                all_items.extend(items)
                logger.info(
                    f"Found {len(items)} actionable items from {integration_type.value}:{account_id}"
                )
            except Exception as e:
                logger.error(f"Error polling {integration_type.value}:{account_id}: {e}")

        return all_items

    async def poll_one(self, integration_type: IntegrationType, account_id: str = "default") -> list[ActionableItem]:
        """Poll a specific integration account.

        Args:
            integration_type: The integration to poll
            account_id: The account identifier (default: "default")

        Returns:
            List of actionable items found.

        Raises:
            ValueError: If integration is not configured
        """
        key = (integration_type, account_id)
        integration = self.integrations.get(key)
        if not integration:
            raise ValueError(
                f"Integration {integration_type.value}:{account_id} not configured"
            )

        return await integration.poll()

    async def poll_account(
        self,
        integration_type: IntegrationType,
        account_id: str,
    ) -> list[ActionableItem]:
        """Poll a specific account.

        Args:
            integration_type: The integration type
            account_id: The account identifier

        Returns:
            List of actionable items found.

        Raises:
            ValueError: If integration account not found
        """
        key = (integration_type, account_id)
        integration = self.integrations.get(key)

        if not integration:
            raise ValueError(
                f"Integration not found: {integration_type.value}:{account_id}"
            )

        logger.info(f"Polling {integration_type.value}:{account_id}")
        return await integration.poll()

    async def test_connections(self) -> dict[tuple[IntegrationType, str], bool]:
        """Test connections to all configured integrations.

        Returns:
            Dict mapping (integration_type, account_id) to connection status.
        """
        results = {}

        for key, integration in self.integrations.items():
            integration_type, account_id = key
            try:
                results[key] = await integration.test_connection()
            except Exception as e:
                logger.error(f"Error testing {integration_type.value}:{account_id}: {e}")
                results[key] = False

        return results

    def get_integration(
        self,
        integration_type: IntegrationType,
        account_id: str = "default",
    ) -> BaseIntegration | None:
        """Get a specific integration instance.

        Args:
            integration_type: The integration type
            account_id: The account identifier (default: "default")

        Returns:
            The integration instance or None if not configured.
        """
        key = (integration_type, account_id)
        return self.integrations.get(key)

    def list_accounts(self, integration_type: IntegrationType) -> list[str]:
        """List all account IDs for a given integration type.

        Args:
            integration_type: The integration type

        Returns:
            List of account IDs configured for this integration type.
        """
        return [
            account_id
            for (itype, account_id) in self.integrations.keys()
            if itype == integration_type
        ]

    def is_enabled(
        self,
        integration_type: IntegrationType,
        account_id: str | None = None,
    ) -> bool:
        """Check if an integration/account is enabled.

        Args:
            integration_type: The integration type
            account_id: Optional specific account ID. If None, checks if ANY account exists.

        Returns:
            True if enabled, False otherwise.
        """
        if account_id:
            key = (integration_type, account_id)
            integration = self.integrations.get(key)
            return integration is not None and integration.enabled
        else:
            # Check if ANY account exists for this integration type
            return any(
                itype == integration_type
                for (itype, _) in self.integrations.keys()
            )

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

        # Extract account_id from metadata if present
        account_id = None
        if item.metadata:
            account_id = item.metadata.get("account_id")

        return {
            "title": item.title,
            "description": item.description,
            "priority": priority_mapping.get(item.priority, TaskPriority.MEDIUM),
            "source": source_mapping.get(item.source, TaskSource.AGENT),
            "source_reference": item.source_reference,
            "account_id": account_id,  # NEW: Include account_id
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
