"""Tests for configuration system."""

from pathlib import Path

import pytest

from src.utils.config import Config, load_config


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
