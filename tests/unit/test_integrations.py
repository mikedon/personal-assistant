"""Tests for integration base classes and manager."""

import base64
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.integrations.base import (
    ActionableItem,
    ActionableItemType,
    AuthenticationError,
    BaseIntegration,
    IntegrationType,
    PollError,
)
from src.integrations.gmail_integration import GmailIntegration
from src.integrations.manager import IntegrationManager
from src.integrations.slack_integration import SlackIntegration
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

    def test_slack_oauth_manager_no_app_token(self):
        """Test Slack OAuth manager raises error when app token missing."""
        from src.integrations.oauth_utils import SlackOAuthManager

        manager = SlackOAuthManager(bot_token="xoxb-test", app_token=None)

        with pytest.raises(ValueError):
            manager.get_app_token()

    def test_google_oauth_manager_missing_credentials(self, tmp_path):
        """Test GoogleOAuthManager raises error when credentials file missing."""
        from src.integrations.oauth_utils import GoogleOAuthManager

        manager = GoogleOAuthManager(
            credentials_path=tmp_path / "nonexistent_credentials.json",
            token_path=tmp_path / "token.json",
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        )

        with pytest.raises(FileNotFoundError):
            manager.get_credentials()

    def test_google_oauth_manager_is_authenticated_returns_false_on_error(self, tmp_path):
        """Test GoogleOAuthManager.is_authenticated returns False when credentials fail."""
        from src.integrations.oauth_utils import GoogleOAuthManager

        manager = GoogleOAuthManager(
            credentials_path=tmp_path / "nonexistent.json",
            token_path=tmp_path / "token.json",
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        )

        assert manager.is_authenticated() is False


class TestBaseIntegrationAuthenticationError:
    """Tests for BaseIntegration.authenticate() raising AuthenticationError."""

    @pytest.mark.asyncio
    async def test_authenticate_raises_authentication_error(self):
        """Test that authenticate() raises AuthenticationError on failure."""

        class FailingIntegration(BaseIntegration):
            @property
            def integration_type(self) -> IntegrationType:
                return IntegrationType.GMAIL

            async def authenticate(self) -> bool:
                raise AuthenticationError("Test authentication failure")

            async def poll(self) -> list[ActionableItem]:
                return []

        integration = FailingIntegration({"enabled": True})

        with pytest.raises(AuthenticationError) as exc_info:
            await integration.authenticate()

        assert "Test authentication failure" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_test_connection_returns_false_on_auth_error(self):
        """Test that test_connection() returns False when authentication fails."""

        class FailingIntegration(BaseIntegration):
            @property
            def integration_type(self) -> IntegrationType:
                return IntegrationType.GMAIL

            async def authenticate(self) -> bool:
                raise AuthenticationError("Auth failed")

            async def poll(self) -> list[ActionableItem]:
                return []

        integration = FailingIntegration({"enabled": True})
        result = await integration.test_connection()
        assert result is False


class TestGmailIntegrationPoll:
    """Tests for GmailIntegration.poll()."""

    @pytest.fixture
    def gmail_config(self):
        """Gmail integration config."""
        return {
            "enabled": True,
            "credentials_path": "credentials.json",
            "token_path": "token.json",
            "max_results": 10,
            "lookback_days": 1,
            "priority_senders": ["boss@example.com"],
        }

    def _create_mock_message(self, subject, sender, body, message_id="msg_123"):
        """Helper to create a mock Gmail message."""
        encoded_body = base64.urlsafe_b64encode(body.encode()).decode()
        return {
            "id": message_id,
            "threadId": "thread_123",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": subject},
                    {"name": "From", "value": sender},
                    {"name": "Date", "value": "Tue, 28 Jan 2026 10:00:00 +0000"},
                ],
                "body": {"data": encoded_body},
            },
        }

    @pytest.mark.asyncio
    async def test_poll_returns_actionable_items_list(self, gmail_config):
        """Test that poll() returns a list of ActionableItem."""
        integration = GmailIntegration(gmail_config)

        mock_service = MagicMock()
        mock_messages = MagicMock()
        mock_service.users.return_value.messages.return_value = mock_messages

        mock_messages.list.return_value.execute.return_value = {
            "messages": [{"id": "msg_1"}, {"id": "msg_2"}]
        }

        message1 = self._create_mock_message(
            subject="Can you help?",
            sender="colleague@example.com",
            body="Can you please review this document?",
            message_id="msg_1",
        )
        message2 = self._create_mock_message(
            subject="Question about project",
            sender="boss@example.com",
            body="What is the status?",
            message_id="msg_2",
        )

        mock_messages.get.return_value.execute.side_effect = [message1, message2]

        integration.service = mock_service

        items = await integration.poll()

        assert isinstance(items, list)
        assert len(items) == 2
        assert all(isinstance(item, ActionableItem) for item in items)

    @pytest.mark.asyncio
    async def test_poll_correctly_parses_email_content(self, gmail_config):
        """Test that poll() correctly parses email subject, sender, and body."""
        integration = GmailIntegration(gmail_config)

        mock_service = MagicMock()
        mock_messages = MagicMock()
        mock_service.users.return_value.messages.return_value = mock_messages

        mock_messages.list.return_value.execute.return_value = {
            "messages": [{"id": "msg_1"}]
        }

        message = self._create_mock_message(
            subject="Please review ASAP",
            sender="boss@example.com",
            body="Could you please review this by today?",
            message_id="msg_1",
        )
        mock_messages.get.return_value.execute.return_value = message

        integration.service = mock_service

        items = await integration.poll()

        assert len(items) == 1
        item = items[0]
        assert item.type == ActionableItemType.EMAIL_REPLY_NEEDED
        assert "Please review ASAP" in item.title
        assert item.source == IntegrationType.GMAIL
        assert item.source_reference == "msg_1"
        assert item.priority == "critical"  # Contains "asap"
        assert item.due_date is not None  # Contains "today"
        assert item.metadata["sender"] == "boss@example.com"
        assert item.metadata["subject"] == "Please review ASAP"
        assert "email" in item.tags

    @pytest.mark.asyncio
    async def test_poll_filters_non_actionable_emails(self, gmail_config):
        """Test that poll() filters out non-actionable emails."""
        integration = GmailIntegration(gmail_config)

        mock_service = MagicMock()
        mock_messages = MagicMock()
        mock_service.users.return_value.messages.return_value = mock_messages

        mock_messages.list.return_value.execute.return_value = {
            "messages": [{"id": "msg_1"}]
        }

        # Message with no action keywords and no question marks
        message = self._create_mock_message(
            subject="Newsletter",
            sender="newsletter@random.com",
            body="Here is your weekly update. Have a great week.",
            message_id="msg_1",
        )
        mock_messages.get.return_value.execute.return_value = message

        integration.service = mock_service

        items = await integration.poll()

        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_poll_authenticates_if_no_service(self, gmail_config):
        """Test that poll() calls authenticate() if service is not set."""
        integration = GmailIntegration(gmail_config)
        integration.service = None

        with patch.object(
            integration, "authenticate", new_callable=AsyncMock
        ) as mock_auth:
            mock_auth.return_value = True
            integration.service = MagicMock()
            mock_messages = MagicMock()
            integration.service.users.return_value.messages.return_value = mock_messages
            mock_messages.list.return_value.execute.return_value = {"messages": []}

            await integration.poll()


class TestSlackIntegrationPoll:
    """Tests for SlackIntegration.poll()."""

    @pytest.fixture
    def slack_config(self):
        """Slack integration config."""
        return {
            "enabled": True,
            "bot_token": "xoxb-test-token",
            "app_token": "xapp-test-token",
            "channels": ["C12345", "C67890"],
            "lookback_hours": 24,
        }

    @pytest.mark.asyncio
    async def test_poll_returns_actionable_items_list(self, slack_config):
        """Test that poll() returns a list of ActionableItem."""
        integration = SlackIntegration(slack_config)

        mock_client = MagicMock()
        mock_client.conversations_history.return_value = {
            "messages": [
                {"text": "Can you help me with this?", "user": "U123", "ts": "1234.5678"},
                {"text": "Please review the PR", "user": "U456", "ts": "1234.5679"},
            ]
        }

        integration.client = mock_client

        items = await integration.poll()

        assert isinstance(items, list)
        assert all(isinstance(item, ActionableItem) for item in items)
        # Should find actionable items from both channels
        assert len(items) >= 2

    @pytest.mark.asyncio
    async def test_poll_identifies_actionable_questions(self, slack_config):
        """Test that poll() identifies messages with question marks as actionable."""
        integration = SlackIntegration(slack_config)

        mock_client = MagicMock()
        mock_client.conversations_history.return_value = {
            "messages": [
                {"text": "What time is the meeting?", "user": "U123", "ts": "1234.5678"},
            ]
        }

        integration.client = mock_client

        items = await integration.poll()

        assert len(items) >= 1
        item = items[0]
        assert item.type == ActionableItemType.SLACK_RESPONSE
        assert "What time is the meeting?" in item.title or "What time is the meeting?" in item.description

    @pytest.mark.asyncio
    async def test_poll_identifies_actionable_keywords(self, slack_config):
        """Test that poll() identifies messages with action keywords."""
        slack_config["channels"] = ["C12345"]
        integration = SlackIntegration(slack_config)

        mock_client = MagicMock()
        mock_client.conversations_history.return_value = {
            "messages": [
                {"text": "Could you please update the docs", "user": "U123", "ts": "1234.5678"},
            ]
        }

        integration.client = mock_client

        items = await integration.poll()

        assert len(items) == 1
        assert items[0].type == ActionableItemType.SLACK_RESPONSE
        assert items[0].source == IntegrationType.SLACK

    @pytest.mark.asyncio
    async def test_poll_sets_high_priority_for_urgent(self, slack_config):
        """Test that poll() sets high priority for urgent messages."""
        slack_config["channels"] = ["C12345"]
        integration = SlackIntegration(slack_config)

        mock_client = MagicMock()
        mock_client.conversations_history.return_value = {
            "messages": [
                {"text": "Urgent: need help ASAP", "user": "U123", "ts": "1234.5678"},
            ]
        }

        integration.client = mock_client

        items = await integration.poll()

        assert len(items) == 1
        assert items[0].priority == "high"

    @pytest.mark.asyncio
    async def test_poll_filters_non_actionable_messages(self, slack_config):
        """Test that poll() filters out non-actionable messages."""
        slack_config["channels"] = ["C12345"]
        integration = SlackIntegration(slack_config)

        mock_client = MagicMock()
        mock_client.conversations_history.return_value = {
            "messages": [
                {"text": "Thanks for the update!", "user": "U123", "ts": "1234.5678"},
                {"text": "Sounds good.", "user": "U456", "ts": "1234.5679"},
            ]
        }

        integration.client = mock_client

        items = await integration.poll()

        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_poll_includes_correct_metadata(self, slack_config):
        """Test that poll() includes correct metadata in ActionableItem."""
        slack_config["channels"] = ["C12345"]
        integration = SlackIntegration(slack_config)

        mock_client = MagicMock()
        mock_client.conversations_history.return_value = {
            "messages": [
                {"text": "Can you review this?", "user": "U123", "ts": "1234.5678"},
            ]
        }

        integration.client = mock_client

        items = await integration.poll()

        assert len(items) == 1
        item = items[0]
        assert item.metadata["channel"] == "C12345"
        assert item.metadata["user"] == "U123"
        assert item.metadata["timestamp"] == "1234.5678"
        assert item.source_reference == "C12345:1234.5678"
        assert "slack" in item.tags


class TestIntegrationManagerPollAll:
    """Tests for IntegrationManager.poll_all()."""

    @pytest.mark.asyncio
    async def test_poll_all_returns_items_for_all_enabled_integrations(self):
        """Test that poll_all() returns actionable items for all enabled integrations."""
        manager = IntegrationManager({})

        # Create mock integrations
        gmail_items = [
            ActionableItem(
                type=ActionableItemType.EMAIL_REPLY_NEEDED,
                title="Reply to email",
                source=IntegrationType.GMAIL,
            )
        ]
        slack_items = [
            ActionableItem(
                type=ActionableItemType.SLACK_RESPONSE,
                title="Respond in Slack",
                source=IntegrationType.SLACK,
            )
        ]

        mock_gmail = AsyncMock()
        mock_gmail.enabled = True
        mock_gmail.poll = AsyncMock(return_value=gmail_items)

        mock_slack = AsyncMock()
        mock_slack.enabled = True
        mock_slack.poll = AsyncMock(return_value=slack_items)

        manager.integrations = {
            IntegrationType.GMAIL: mock_gmail,
            IntegrationType.SLACK: mock_slack,
        }

        results = await manager.poll_all()

        assert IntegrationType.GMAIL in results
        assert IntegrationType.SLACK in results
        assert len(results[IntegrationType.GMAIL]) == 1
        assert len(results[IntegrationType.SLACK]) == 1
        assert results[IntegrationType.GMAIL][0].title == "Reply to email"
        assert results[IntegrationType.SLACK][0].title == "Respond in Slack"

    @pytest.mark.asyncio
    async def test_poll_all_skips_disabled_integrations(self):
        """Test that poll_all() skips disabled integrations."""
        manager = IntegrationManager({})

        mock_gmail = AsyncMock()
        mock_gmail.enabled = False
        mock_gmail.poll = AsyncMock(return_value=[])

        mock_slack = AsyncMock()
        mock_slack.enabled = True
        mock_slack.poll = AsyncMock(
            return_value=[
                ActionableItem(
                    type=ActionableItemType.SLACK_RESPONSE,
                    title="Slack message",
                    source=IntegrationType.SLACK,
                )
            ]
        )

        manager.integrations = {
            IntegrationType.GMAIL: mock_gmail,
            IntegrationType.SLACK: mock_slack,
        }

        results = await manager.poll_all()

        # Gmail should not be polled (disabled)
        mock_gmail.poll.assert_not_called()
        # Slack should be polled
        mock_slack.poll.assert_called_once()
        # Only Slack results
        assert IntegrationType.GMAIL not in results
        assert IntegrationType.SLACK in results

    @pytest.mark.asyncio
    async def test_poll_all_handles_integration_errors_gracefully(self):
        """Test that poll_all() handles errors and returns empty list for failed integrations."""
        manager = IntegrationManager({})

        mock_gmail = AsyncMock()
        mock_gmail.enabled = True
        mock_gmail.poll = AsyncMock(side_effect=Exception("API Error"))

        mock_slack = AsyncMock()
        mock_slack.enabled = True
        mock_slack.poll = AsyncMock(
            return_value=[
                ActionableItem(
                    type=ActionableItemType.SLACK_RESPONSE,
                    title="Success",
                    source=IntegrationType.SLACK,
                )
            ]
        )

        manager.integrations = {
            IntegrationType.GMAIL: mock_gmail,
            IntegrationType.SLACK: mock_slack,
        }

        results = await manager.poll_all()

        # Gmail should have empty list due to error
        assert results[IntegrationType.GMAIL] == []
        # Slack should succeed
        assert len(results[IntegrationType.SLACK]) == 1

    @pytest.mark.asyncio
    async def test_poll_all_returns_empty_dict_when_no_integrations(self):
        """Test that poll_all() returns empty dict when no integrations configured."""
        manager = IntegrationManager({})

        results = await manager.poll_all()

        assert results == {}
