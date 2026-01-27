"""Tests for integration base classes and manager."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.integrations.base import (
    ActionableItem,
    ActionableItemType,
    BaseIntegration,
    IntegrationType,
)
from src.integrations.manager import IntegrationManager
from src.models.task import TaskPriority, TaskSource


class MockIntegration(BaseIntegration):
    """Mock integration for testing."""

    @property
    def integration_type(self) -> IntegrationType:
        return IntegrationType.GMAIL

    async def authenticate(self) -> bool:
        return True

    async def poll(self) -> list[ActionableItem]:
        return [
            ActionableItem(
                type=ActionableItemType.TASK,
                title="Test Task",
                description="Test Description",
                source=IntegrationType.GMAIL,
                priority="high",
            )
        ]


class TestActionableItem:
    """Tests for ActionableItem."""

    def test_create_actionable_item(self):
        """Test creating an actionable item."""
        item = ActionableItem(
            type=ActionableItemType.EMAIL_REPLY_NEEDED,
            title="Reply to email",
            description="Important email from boss",
            source=IntegrationType.GMAIL,
            source_reference="msg_123",
            priority="high",
            tags=["urgent", "email"],
        )

        assert item.type == ActionableItemType.EMAIL_REPLY_NEEDED
        assert item.title == "Reply to email"
        assert item.source == IntegrationType.GMAIL
        assert item.priority == "high"
        assert "urgent" in item.tags


class TestBaseIntegration:
    """Tests for BaseIntegration."""

    @pytest.mark.asyncio
    async def test_mock_integration(self):
        """Test mock integration."""
        integration = MockIntegration({"enabled": True})

        assert integration.integration_type == IntegrationType.GMAIL
        assert integration.enabled

        # Test authentication
        result = await integration.authenticate()
        assert result is True

        # Test polling
        items = await integration.poll()
        assert len(items) == 1
        assert items[0].title == "Test Task"

    @pytest.mark.asyncio
    async def test_test_connection(self):
        """Test connection testing."""
        integration = MockIntegration({"enabled": True})
        result = await integration.test_connection()
        assert result is True

    def test_last_poll_tracking(self):
        """Test last poll timestamp tracking."""
        integration = MockIntegration({"enabled": True})
        assert integration.last_poll is None

        integration._update_last_poll()
        assert integration.last_poll is not None


class TestIntegrationManager:
    """Tests for IntegrationManager."""

    def test_initialize_empty_manager(self):
        """Test initializing manager with no integrations."""
        manager = IntegrationManager({})
        assert len(manager.integrations) == 0

    def test_actionable_item_to_task_params(self):
        """Test converting actionable item to task parameters."""
        item = ActionableItem(
            type=ActionableItemType.EMAIL_REPLY_NEEDED,
            title="Test Email",
            description="Test Description",
            source=IntegrationType.GMAIL,
            source_reference="msg_123",
            priority="high",
            tags=["urgent"],
            due_date=datetime(2026, 1, 28),
        )

        params = IntegrationManager.actionable_item_to_task_params(item)

        assert params["title"] == "Test Email"
        assert params["description"] == "Test Description"
        assert params["priority"] == TaskPriority.HIGH
        assert params["source"] == TaskSource.EMAIL
        assert params["source_reference"] == "msg_123"
        assert params["tags"] == ["urgent"]
        assert params["due_date"] == datetime(2026, 1, 28)

    def test_priority_mapping(self):
        """Test priority string to TaskPriority mapping."""
        test_cases = [
            ("critical", TaskPriority.CRITICAL),
            ("high", TaskPriority.HIGH),
            ("medium", TaskPriority.MEDIUM),
            ("low", TaskPriority.LOW),
            ("unknown", TaskPriority.MEDIUM),  # Default
        ]

        for priority_str, expected in test_cases:
            item = ActionableItem(
                type=ActionableItemType.TASK,
                title="Test",
                source=IntegrationType.GMAIL,
                priority=priority_str,
            )
            params = IntegrationManager.actionable_item_to_task_params(item)
            assert params["priority"] == expected

    def test_source_mapping(self):
        """Test integration type to TaskSource mapping."""
        test_cases = [
            (IntegrationType.GMAIL, TaskSource.EMAIL),
            (IntegrationType.SLACK, TaskSource.SLACK),
            (IntegrationType.CALENDAR, TaskSource.CALENDAR),
        ]

        for integration_type, expected_source in test_cases:
            item = ActionableItem(
                type=ActionableItemType.TASK,
                title="Test",
                source=integration_type,
            )
            params = IntegrationManager.actionable_item_to_task_params(item)
            assert params["source"] == expected_source

    @pytest.mark.asyncio
    async def test_create_tasks_from_items(self, test_db_session):
        """Test creating tasks from actionable items."""
        from src.services.task_service import TaskService

        manager = IntegrationManager({})
        service = TaskService(test_db_session)

        items = [
            ActionableItem(
                type=ActionableItemType.EMAIL_REPLY_NEEDED,
                title="Reply to email 1",
                source=IntegrationType.GMAIL,
                priority="high",
            ),
            ActionableItem(
                type=ActionableItemType.SLACK_RESPONSE,
                title="Respond in Slack",
                source=IntegrationType.SLACK,
                priority="medium",
            ),
        ]

        task_ids = await manager.create_tasks_from_items(items, service)

        assert len(task_ids) == 2
        assert all(isinstance(task_id, int) for task_id in task_ids)

        # Verify tasks were created
        for task_id in task_ids:
            task = service.get_task(task_id)
            assert task is not None

    def test_is_enabled(self):
        """Test checking if integration is enabled."""
        manager = IntegrationManager({})
        assert not manager.is_enabled(IntegrationType.GMAIL)
        assert not manager.is_enabled(IntegrationType.SLACK)


class TestOAuthManagers:
    """Tests for OAuth managers."""

    def test_slack_oauth_manager(self):
        """Test Slack OAuth manager."""
        from src.integrations.oauth_utils import SlackOAuthManager

        manager = SlackOAuthManager(bot_token="xoxb-test", app_token="xapp-test")

        assert manager.is_authenticated()
        assert manager.get_bot_token() == "xoxb-test"
        assert manager.get_app_token() == "xapp-test"

    def test_slack_oauth_manager_no_token(self):
        """Test Slack OAuth manager without token."""
        from src.integrations.oauth_utils import SlackOAuthManager

        manager = SlackOAuthManager(bot_token="")
        assert not manager.is_authenticated()

        with pytest.raises(ValueError):
            manager.get_bot_token()
