"""Tests for configuration system."""

from pathlib import Path

import pytest

from src.utils.config import Config, GoogleAccountConfig, load_config, migrate_legacy_google_config


def test_config_defaults():
    """Test that config has sensible defaults."""
    config = Config()

    assert config.llm.model == "gpt-4"
    assert config.database.url == "sqlite:///personal_assistant.db"
    assert config.agent.poll_interval_minutes == 15
    assert config.agent.autonomy_level == "suggest"


def test_config_from_dict():
    """Test creating config from dictionary."""
    config_data = {
        "llm": {"api_key": "test-key", "model": "gpt-3.5-turbo"},
        "database": {"url": "sqlite:///test.db"},
    }

    config = Config(**config_data)

    assert config.llm.api_key == "test-key"
    assert config.llm.model == "gpt-3.5-turbo"
    assert config.database.url == "sqlite:///test.db"


def test_load_config_nonexistent_file(tmp_path):
    """Test loading config when file doesn't exist returns defaults."""
    config_path = tmp_path / "nonexistent.yaml"
    config = load_config(config_path)

    assert isinstance(config, Config)
    assert config.llm.model == "gpt-4"


def test_load_config_from_yaml(tmp_path):
    """Test loading config from YAML file."""
    config_path = tmp_path / "config.yaml"
    yaml_content = """
llm:
  api_key: "my-api-key"
  model: "gpt-4-turbo"
  temperature: 0.5

database:
  url: "sqlite:///custom.db"

agent:
  poll_interval_minutes: 30
  autonomy_level: "auto"
"""
    config_path.write_text(yaml_content)

    config = load_config(config_path)

    assert config.llm.api_key == "my-api-key"
    assert config.llm.model == "gpt-4-turbo"
    assert config.llm.temperature == 0.5
    assert config.database.url == "sqlite:///custom.db"
    assert config.agent.poll_interval_minutes == 30
    assert config.agent.autonomy_level == "auto"


def test_config_validation():
    """Test that config validation works."""
    # Test invalid temperature (must be 0-2)
    with pytest.raises(Exception):
        Config(llm={"temperature": 3.0})

    # Test invalid max_tokens (must be positive)
    with pytest.raises(Exception):
        Config(llm={"max_tokens": -1})


def test_migrate_legacy_google_config_with_legacy_format():
    """Test migration of legacy single-account Google config."""
    legacy_config = {
        "google": {
            "enabled": True,
            "credentials_path": "credentials.json",
            "token_path": "token.json",
            "scopes": [
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/calendar.readonly",
            ],
            "polling_interval_minutes": 10,
            "gmail": {
                "inbox_type": "important",
                "max_results": 20,
                "lookback_days": 2,
            },
        }
    }

    migrated = migrate_legacy_google_config(legacy_config)

    # Should convert to multi-account format
    assert "accounts" in migrated["google"]
    assert len(migrated["google"]["accounts"]) == 1

    account = migrated["google"]["accounts"][0]
    assert account["account_id"] == "default"
    assert account["display_name"] == "Default Account"
    assert account["enabled"] is True
    assert account["credentials_path"] == "credentials.json"
    assert account["token_path"] == "token.json"
    assert account["polling_interval_minutes"] == 10
    assert account["scopes"] == [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/calendar.readonly",
    ]
    assert account["gmail"]["inbox_type"] == "important"
    assert account["gmail"]["max_results"] == 20


def test_migrate_legacy_google_config_already_migrated():
    """Test migration with already-migrated multi-account config."""
    multi_account_config = {
        "google": {
            "enabled": True,
            "accounts": [
                {
                    "account_id": "personal",
                    "display_name": "Personal Gmail",
                    "enabled": True,
                    "credentials_path": "credentials.personal.json",
                    "token_path": "token.personal.json",
                    "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
                    "polling_interval_minutes": 15,
                    "gmail": {
                        "inbox_type": "unread",
                        "max_results": 10,
                        "lookback_days": 1,
                    },
                }
            ],
        }
    }

    migrated = migrate_legacy_google_config(multi_account_config)

    # Should return unchanged
    assert migrated == multi_account_config
    assert "accounts" in migrated["google"]
    assert len(migrated["google"]["accounts"]) == 1
    assert migrated["google"]["accounts"][0]["account_id"] == "personal"


def test_migrate_legacy_google_config_no_google_section():
    """Test migration with no Google config section."""
    config = {"llm": {"api_key": "test-key"}}

    migrated = migrate_legacy_google_config(config)

    # Should return unchanged
    assert migrated == config
    assert "google" not in migrated


def test_migrate_legacy_google_config_minimal():
    """Test migration with minimal legacy config."""
    legacy_config = {
        "google": {
            "enabled": False,
            "credentials_path": "creds.json",
        }
    }

    migrated = migrate_legacy_google_config(legacy_config)

    # Should convert to multi-account with defaults
    assert "accounts" in migrated["google"]
    assert len(migrated["google"]["accounts"]) == 1

    account = migrated["google"]["accounts"][0]
    assert account["account_id"] == "default"
    assert account["enabled"] is False  # Inherits from top-level enabled flag
    assert account["credentials_path"] == "creds.json"
    # Should have default values for missing fields
    assert "token_path" in account
    assert "scopes" in account


def test_google_account_config_validation_valid():
    """Test GoogleAccountConfig validation with valid account_id."""
    # Valid account IDs
    valid_ids = ["personal", "work", "account_1", "my_account"]

    for account_id in valid_ids:
        config = GoogleAccountConfig(
            account_id=account_id,
            display_name="Test Account",
            credentials_path="creds.json",
            token_path="token.json",
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            gmail={
                "inbox_type": "unread",
                "max_results": 10,
                "lookback_days": 1,
            },
        )
        assert config.account_id == account_id


def test_google_account_config_validation_invalid():
    """Test GoogleAccountConfig validation with invalid account_id."""
    # Invalid account IDs (uppercase, special chars, hyphens)
    invalid_ids = ["Personal", "work-account", "acc@unt", "My Account", "account-1"]

    for account_id in invalid_ids:
        with pytest.raises(Exception):  # Pydantic ValidationError
            GoogleAccountConfig(
                account_id=account_id,
                display_name="Test Account",
                credentials_path="creds.json",
                token_path="token.json",
                scopes=["https://www.googleapis.com/auth/gmail.readonly"],
                gmail={
                    "inbox_type": "unread",
                    "max_results": 10,
                    "lookback_days": 1,
                },
            )
