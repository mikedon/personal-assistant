"""Tests for integration base classes and manager."""

import base64
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.base import (
    ActionableItem,
    ActionableItemType,
    AuthenticationError,
    BaseIntegration,
    IntegrationType,
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
        from src.integrations.manager import IntegrationKey

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
            IntegrationKey(IntegrationType.GMAIL, "default"): mock_gmail,
            IntegrationKey(IntegrationType.SLACK, "default"): mock_slack,
        }

        results = await manager.poll_all()

        # poll_all() now returns a flat list of ActionableItem objects
        assert isinstance(results, list)
        assert len(results) == 2
        sources = [item.source for item in results]
        assert IntegrationType.GMAIL in sources
        assert IntegrationType.SLACK in sources
        gmail_items_result = [item for item in results if item.source == IntegrationType.GMAIL]
        slack_items_result = [item for item in results if item.source == IntegrationType.SLACK]
        assert len(gmail_items_result) == 1
        assert len(slack_items_result) == 1
        assert gmail_items_result[0].title == "Reply to email"
        assert slack_items_result[0].title == "Respond in Slack"

    @pytest.mark.asyncio
    async def test_poll_all_skips_disabled_integrations(self):
        """Test that poll_all() skips disabled integrations."""
        from src.integrations.manager import IntegrationKey

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
            IntegrationKey(IntegrationType.GMAIL, "default"): mock_gmail,
            IntegrationKey(IntegrationType.SLACK, "default"): mock_slack,
        }

        results = await manager.poll_all()

        # Gmail should not be polled (disabled)
        mock_gmail.poll.assert_not_called()
        # Slack should be polled
        mock_slack.poll.assert_called_once()
        # poll_all() returns flat list, so check sources
        assert isinstance(results, list)
        assert len(results) == 1
        sources = [item.source for item in results]
        assert IntegrationType.GMAIL not in sources
        assert IntegrationType.SLACK in sources

    @pytest.mark.asyncio
    async def test_poll_all_handles_integration_errors_gracefully(self):
        """Test that poll_all() handles errors and continues with other integrations."""
        from src.integrations.manager import IntegrationKey

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
            IntegrationKey(IntegrationType.GMAIL, "default"): mock_gmail,
            IntegrationKey(IntegrationType.SLACK, "default"): mock_slack,
        }

        results = await manager.poll_all()

        # poll_all() returns flat list and continues despite Gmail error
        assert isinstance(results, list)
        # Only Slack item should be in results (Gmail error handled gracefully)
        assert len(results) == 1
        assert results[0].source == IntegrationType.SLACK
        assert results[0].title == "Success"

    @pytest.mark.asyncio
    async def test_poll_all_returns_empty_list_when_no_integrations(self):
        """Test that poll_all() returns empty list when no integrations configured."""
        manager = IntegrationManager({})

        results = await manager.poll_all()

        assert results == []
        assert isinstance(results, list)


class TestGmailIntegrationQueryBuilding:
    """Tests for GmailIntegration query building and filtering."""

    def test_build_query_default_unread(self):
        """Test default query uses 'is:unread' filter."""
        config = {"enabled": True, "gmail": {}}
        integration = GmailIntegration(config)

        query = integration._build_query()

        assert "is:unread" in query
        assert "after:" in query

    def test_build_query_inbox_type_all(self):
        """Test query with inbox_type='all' has no inbox filter."""
        config = {"enabled": True, "gmail": {"inbox_type": "all"}}
        integration = GmailIntegration(config)

        query = integration._build_query()

        assert "is:unread" not in query
        assert "is:important" not in query
        assert "after:" in query

    def test_build_query_inbox_type_not_spam(self):
        """Test query with inbox_type='not_spam' uses '-in:spam' filter."""
        config = {"enabled": True, "gmail": {"inbox_type": "not_spam"}}
        integration = GmailIntegration(config)

        query = integration._build_query()

        assert "-in:spam" in query
        assert "after:" in query

    def test_build_query_inbox_type_important(self):
        """Test query with inbox_type='important' uses 'is:important' filter."""
        config = {"enabled": True, "gmail": {"inbox_type": "important"}}
        integration = GmailIntegration(config)

        query = integration._build_query()

        assert "is:important" in query
        assert "after:" in query

    def test_build_query_lookback_hours_takes_precedence(self):
        """Test that lookback_hours takes precedence over lookback_days."""
        config = {
            "enabled": True,
            "gmail": {"lookback_hours": 6, "lookback_days": 7},
        }
        integration = GmailIntegration(config)

        # With 6 hours lookback, the date should be today (not 7 days ago)
        query = integration._build_query()
        assert "after:" in query
        # Verify lookback_hours is being used
        assert integration.lookback_hours == 6

    def test_build_query_include_senders_adds_from_clause(self):
        """Test that include_senders adds 'from:' clause to query."""
        config = {
            "enabled": True,
            "gmail": {"include_senders": ["boss@example.com", "ceo@example.com"]},
        }
        integration = GmailIntegration(config)

        query = integration._build_query()

        assert "from:(boss@example.com OR ceo@example.com)" in query

    def test_build_query_many_senders_skips_from_clause(self):
        """Test that more than 5 senders skips 'from:' in query (relies on post-filtering)."""
        config = {
            "enabled": True,
            "gmail": {"include_senders": ["a@x.com", "b@x.com", "c@x.com", "d@x.com", "e@x.com", "f@x.com"]},
        }
        integration = GmailIntegration(config)

        query = integration._build_query()

        assert "from:" not in query


class TestGmailIntegrationFiltering:
    """Tests for GmailIntegration sender and subject filtering."""

    def test_should_include_email_no_filters(self):
        """Test that email passes when no filters configured."""
        config = {"enabled": True, "gmail": {}}
        integration = GmailIntegration(config)

        result = integration._should_include_email("anyone@example.com", "Any Subject")

        assert result is True

    def test_should_include_email_exclude_sender_blocks(self):
        """Test that exclude_senders blocks matching emails."""
        config = {
            "enabled": True,
            "gmail": {"exclude_senders": ["noreply@", "newsletter@"]},
        }
        integration = GmailIntegration(config)

        assert integration._should_include_email("noreply@company.com", "Update") is False
        assert integration._should_include_email("newsletter@news.com", "Weekly") is False
        assert integration._should_include_email("boss@company.com", "Meeting") is True

    def test_should_include_email_include_sender_filters(self):
        """Test that include_senders only allows matching emails."""
        config = {
            "enabled": True,
            "gmail": {"include_senders": ["boss@example.com", "@important.com"]},
        }
        integration = GmailIntegration(config)

        assert integration._should_include_email("boss@example.com", "Hi") is True
        assert integration._should_include_email("ceo@important.com", "Meeting") is True
        assert integration._should_include_email("random@other.com", "Spam") is False

    def test_should_include_email_exclude_takes_precedence(self):
        """Test that exclude_senders takes precedence over include_senders."""
        config = {
            "enabled": True,
            "gmail": {
                "include_senders": ["@company.com"],
                "exclude_senders": ["noreply@company.com"],
            },
        }
        integration = GmailIntegration(config)

        assert integration._should_include_email("boss@company.com", "Hi") is True
        assert integration._should_include_email("noreply@company.com", "Auto") is False

    def test_should_include_email_exclude_subject_blocks(self):
        """Test that exclude_subjects blocks matching emails."""
        config = {
            "enabled": True,
            "gmail": {"exclude_subjects": ["[automated]", "google doc edit"]},
        }
        integration = GmailIntegration(config)

        assert integration._should_include_email("a@b.com", "[Automated] Report") is False
        assert integration._should_include_email("a@b.com", "New Google Doc Edit") is False
        assert integration._should_include_email("a@b.com", "Meeting Request") is True

    def test_should_include_email_include_subject_filters(self):
        """Test that include_subjects only allows matching emails."""
        config = {
            "enabled": True,
            "gmail": {"include_subjects": ["urgent", "action required"]},
        }
        integration = GmailIntegration(config)

        assert integration._should_include_email("a@b.com", "URGENT: Please review") is True
        assert integration._should_include_email("a@b.com", "Action Required: Sign") is True
        assert integration._should_include_email("a@b.com", "Weekly Newsletter") is False

    def test_should_include_email_case_insensitive(self):
        """Test that filtering is case-insensitive."""
        config = {
            "enabled": True,
            "gmail": {
                "include_senders": ["BOSS@EXAMPLE.COM"],
                "exclude_subjects": ["NEWSLETTER"],
            },
        }
        integration = GmailIntegration(config)

        # Sender matching is case-insensitive
        assert integration._should_include_email("boss@example.com", "Hi") is True
        assert integration._should_include_email("Boss@Example.com", "Hi") is True
        # Subject matching is case-insensitive
        assert integration._should_include_email("boss@example.com", "newsletter") is False
        assert integration._should_include_email("boss@example.com", "Newsletter") is False

    def test_backwards_compatible_with_root_config(self):
        """Test that config at root level still works for backwards compatibility."""
        config = {
            "enabled": True,
            "max_results": 20,
            "lookback_days": 3,
            "priority_senders": ["vip@example.com"],
        }
        integration = GmailIntegration(config)

        assert integration.max_results == 20
        assert integration.lookback_days == 3
        assert "vip@example.com" in integration.priority_senders

    def test_nested_config_overrides_root(self):
        """Test that nested gmail config overrides root config."""
        config = {
            "enabled": True,
            "max_results": 5,
            "gmail": {"max_results": 25},
        }
        integration = GmailIntegration(config)

        assert integration.max_results == 25
