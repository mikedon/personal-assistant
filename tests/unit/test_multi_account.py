"""Tests for multi-account integration functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.integrations.base import ActionableItem, ActionableItemType, IntegrationType
from src.integrations.manager import IntegrationKey, IntegrationManager
from src.models.task import TaskPriority, TaskSource, TaskStatus
from src.services.task_service import TaskService
from src.utils.config import GoogleAccountConfig


class TestIntegrationKey:
    """Tests for IntegrationKey dataclass."""

    def test_integration_key_creation(self):
        """Test creating IntegrationKey."""
        key = IntegrationKey(IntegrationType.GMAIL, "personal")

        assert key.type == IntegrationType.GMAIL
        assert key.account_id == "personal"

    def test_integration_key_string_representation(self):
        """Test IntegrationKey string conversion."""
        key = IntegrationKey(IntegrationType.GMAIL, "work")

        assert str(key) == "gmail:work"

    def test_integration_key_frozen(self):
        """Test IntegrationKey is immutable (frozen)."""
        key = IntegrationKey(IntegrationType.GMAIL, "personal")

        with pytest.raises(AttributeError):
            key.account_id = "work"  # Should fail - frozen dataclass

    def test_integration_key_hashable(self):
        """Test IntegrationKey can be used as dict key."""
        key1 = IntegrationKey(IntegrationType.GMAIL, "personal")
        key2 = IntegrationKey(IntegrationType.GMAIL, "personal")
        key3 = IntegrationKey(IntegrationType.GMAIL, "work")

        # Same keys should be equal
        assert key1 == key2
        assert hash(key1) == hash(key2)

        # Different keys should not be equal
        assert key1 != key3

        # Should work as dict key
        test_dict = {key1: "value1", key3: "value2"}
        assert test_dict[key2] == "value1"


class TestActionableItemAccountId:
    """Tests for ActionableItem with account_id field."""

    def test_actionable_item_with_account_id(self):
        """Test creating ActionableItem with account_id."""
        item = ActionableItem(
            type=ActionableItemType.TASK,
            title="Test Task",
            description="Test Description",
            source=IntegrationType.GMAIL,
            priority="high",
            account_id="personal",
        )

        assert item.account_id == "personal"
        assert item.title == "Test Task"

    def test_actionable_item_without_account_id(self):
        """Test ActionableItem with None account_id (backward compat)."""
        item = ActionableItem(
            type=ActionableItemType.TASK,
            title="Test Task",
            source=IntegrationType.SLACK,
        )

        assert item.account_id is None

    def test_actionable_item_account_id_is_typed(self):
        """Test account_id is a first-class typed field, not in metadata."""
        item = ActionableItem(
            type=ActionableItemType.TASK,
            title="Test Task",
            account_id="work",
            metadata={"some_key": "some_value"},
        )

        # account_id should be accessible as attribute
        assert hasattr(item, "account_id")
        assert item.account_id == "work"

        # account_id should not be in metadata
        assert item.metadata is not None
        assert "account_id" not in item.metadata


class TestIntegrationManagerMultiAccount:
    """Tests for IntegrationManager multi-account support."""

    @patch("src.integrations.manager.GmailIntegration")
    def test_initialize_multiple_gmail_accounts(self, mock_gmail_class):
        """Test IntegrationManager initializes multiple Gmail accounts."""
        mock_integration1 = Mock()
        mock_integration1.enabled = True
        mock_integration2 = Mock()
        mock_integration2.enabled = True

        mock_gmail_class.side_effect = [mock_integration1, mock_integration2]

        config = {
            "google": {
                "enabled": True,
                "accounts": [
                    {
                        "account_id": "personal",
                        "display_name": "Personal",
                        "enabled": True,
                        "credentials_path": "creds.personal.json",
                        "token_path": "token.personal.json",
                        "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
                        "polling_interval_minutes": 15,
                        "gmail": {
                            "inbox_type": "unread",
                            "max_results": 10,
                            "lookback_days": 1,
                        },
                    },
                    {
                        "account_id": "work",
                        "display_name": "Work",
                        "enabled": True,
                        "credentials_path": "creds.work.json",
                        "token_path": "token.work.json",
                        "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
                        "polling_interval_minutes": 5,
                        "gmail": {
                            "inbox_type": "important",
                            "max_results": 20,
                            "lookback_days": 1,
                        },
                    },
                ],
            }
        }

        manager = IntegrationManager(config)

        # Should have 2 integrations
        assert len(manager.integrations) == 2

        # Verify keys use IntegrationKey
        keys = list(manager.integrations.keys())
        assert all(isinstance(key, IntegrationKey) for key in keys)

        # Verify both accounts present
        key1 = IntegrationKey(IntegrationType.GMAIL, "personal")
        key2 = IntegrationKey(IntegrationType.GMAIL, "work")
        assert key1 in manager.integrations
        assert key2 in manager.integrations

    @patch("src.integrations.manager.GmailIntegration")
    def test_list_accounts_returns_account_ids(self, mock_gmail_class):
        """Test list_accounts returns all account IDs for an integration type."""
        mock_integration1 = Mock()
        mock_integration1.enabled = True
        mock_integration2 = Mock()
        mock_integration2.enabled = True

        mock_gmail_class.side_effect = [mock_integration1, mock_integration2]

        config = {
            "google": {
                "enabled": True,
                "accounts": [
                    {"account_id": "personal", "enabled": True, "display_name": "Personal", "credentials_path": "c.json", "token_path": "t.json", "scopes": [], "gmail": {}},
                    {"account_id": "work", "enabled": True, "display_name": "Work", "credentials_path": "c.json", "token_path": "t.json", "scopes": [], "gmail": {}},
                ],
            }
        }

        manager = IntegrationManager(config)
        accounts = manager.list_accounts(IntegrationType.GMAIL)

        assert "personal" in accounts
        assert "work" in accounts
        assert len(accounts) == 2

    @patch("src.integrations.manager.GmailIntegration")
    def test_get_integration_with_account_id(self, mock_gmail_class):
        """Test get_integration retrieves specific account integration."""
        mock_integration = Mock()
        mock_integration.enabled = True
        mock_gmail_class.return_value = mock_integration

        config = {
            "google": {
                "enabled": True,
                "accounts": [
                    {"account_id": "personal", "enabled": True, "display_name": "Personal", "credentials_path": "c.json", "token_path": "t.json", "scopes": [], "gmail": {}},
                ],
            }
        }

        manager = IntegrationManager(config)
        integration = manager.get_integration(IntegrationType.GMAIL, "personal")

        assert integration is not None
        assert integration == mock_integration

    @patch("src.integrations.manager.GmailIntegration")
    def test_get_integration_nonexistent_account(self, mock_gmail_class):
        """Test get_integration returns None for nonexistent account."""
        mock_integration = Mock()
        mock_integration.enabled = True
        mock_gmail_class.return_value = mock_integration

        config = {
            "google": {
                "enabled": True,
                "accounts": [
                    {"account_id": "personal", "enabled": True, "display_name": "Personal", "credentials_path": "c.json", "token_path": "t.json", "scopes": [], "gmail": {}},
                ],
            }
        }

        manager = IntegrationManager(config)
        integration = manager.get_integration(IntegrationType.GMAIL, "nonexistent")

        assert integration is None

    @patch("src.integrations.manager.GmailIntegration")
    def test_duplicate_account_id_skipped(self, mock_gmail_class):
        """Test duplicate account_ids are detected and skipped."""
        mock_integration1 = Mock()
        mock_integration1.enabled = True
        mock_integration2 = Mock()
        mock_integration2.enabled = True

        mock_gmail_class.side_effect = [mock_integration1, mock_integration2]

        config = {
            "google": {
                "enabled": True,
                "accounts": [
                    {"account_id": "personal", "enabled": True, "display_name": "Personal 1", "credentials_path": "c1.json", "token_path": "t1.json", "scopes": [], "gmail": {}},
                    {"account_id": "personal", "enabled": True, "display_name": "Personal 2", "credentials_path": "c2.json", "token_path": "t2.json", "scopes": [], "gmail": {}},
                ],
            }
        }

        manager = IntegrationManager(config)

        # Should only have 1 integration (duplicate skipped)
        assert len(manager.integrations) == 1

        key = IntegrationKey(IntegrationType.GMAIL, "personal")
        assert key in manager.integrations


class TestTaskServiceAccountIdValidation:
    """Tests for TaskService account_id validation."""

    def test_create_task_with_valid_account_id(self):
        """Test creating task with valid account_id succeeds."""
        # Mock database
        db = Mock()
        db.add = Mock()
        db.commit = Mock()
        db.refresh = Mock()

        with patch("src.integrations.manager.IntegrationManager") as mock_manager_class, \
             patch("src.utils.config.load_config"):
            # Mock IntegrationManager to return valid accounts
            mock_manager = Mock()
            mock_manager.list_accounts.return_value = ["personal", "work"]
            mock_manager_class.return_value = mock_manager

            service = TaskService(db)

            # Should succeed with valid account_id
            try:
                service.create_task(
                    title="Test Task",
                    account_id="personal",
                )
                # If we get here, validation passed
                assert True
            except ValueError:
                pytest.fail("Should not raise ValueError for valid account_id")

    def test_create_task_with_invalid_account_id(self):
        """Test creating task with invalid account_id raises ValueError."""
        db = Mock()

        with patch("src.integrations.manager.IntegrationManager") as mock_manager_class, \
             patch("src.utils.config.load_config"):
            # Mock IntegrationManager to return valid accounts
            mock_manager = Mock()
            mock_manager.list_accounts.return_value = ["personal", "work"]
            mock_manager_class.return_value = mock_manager

            service = TaskService(db)

            # Should raise ValueError for invalid account_id
            with pytest.raises(ValueError, match="Invalid account_id"):
                service.create_task(
                    title="Test Task",
                    account_id="nonexistent",
                )

    def test_create_task_without_account_id(self):
        """Test creating task without account_id succeeds (optional field)."""
        db = Mock()
        db.add = Mock()
        db.commit = Mock()
        db.refresh = Mock()

        service = TaskService(db)

        # Should succeed without account_id (it's optional)
        try:
            service.create_task(title="Test Task")
            assert True
        except ValueError:
            pytest.fail("Should not raise ValueError when account_id is None")


class TestIntegrationManagerActionableItemConversion:
    """Tests for converting ActionableItem to task parameters."""

    def test_actionable_item_to_task_params_with_account_id(self):
        """Test actionable_item_to_task_params extracts account_id correctly."""
        item = ActionableItem(
            type=ActionableItemType.TASK,
            title="Test Task",
            description="Test Description",
            source=IntegrationType.GMAIL,
            priority="high",
            account_id="personal",
        )

        params = IntegrationManager.actionable_item_to_task_params(item)

        assert params["account_id"] == "personal"
        assert params["title"] == "Test Task"
        assert params["priority"] == TaskPriority.HIGH
        assert params["source"] == TaskSource.EMAIL

    def test_actionable_item_to_task_params_without_account_id(self):
        """Test actionable_item_to_task_params handles None account_id."""
        item = ActionableItem(
            type=ActionableItemType.TASK,
            title="Test Task",
            source=IntegrationType.SLACK,
            account_id=None,
        )

        params = IntegrationManager.actionable_item_to_task_params(item)

        assert params["account_id"] is None
        assert params["source"] == TaskSource.SLACK
