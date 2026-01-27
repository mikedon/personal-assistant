"""Configuration management with YAML support and Pydantic validation."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseModel):
    """LLM configuration for the router service."""

    base_url: str = Field(default="https://api.openai.com/v1", description="OpenAI-compatible API base URL")
    api_key: str = Field(default="", description="API key for the LLM service")
    model: str = Field(default="gpt-4", description="Model to use for LLM requests")
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=2000, gt=0)


class DatabaseConfig(BaseModel):
    """Database configuration."""

    url: str = Field(default="sqlite:///personal_assistant.db", description="Database connection URL")
    echo: bool = Field(default=False, description="Echo SQL statements for debugging")


class GoogleConfig(BaseModel):
    """Google API configuration for Gmail, Calendar, and Drive."""

    credentials_path: str = Field(default="credentials.json", description="Path to OAuth credentials file")
    token_path: str = Field(default="token.json", description="Path to store OAuth token")
    scopes: list[str] = Field(
        default=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
    )


class SlackConfig(BaseModel):
    """Slack API configuration."""

    bot_token: str = Field(default="", description="Slack bot token")
    app_token: str = Field(default="", description="Slack app token for socket mode")
    channels: list[str] = Field(default=[], description="Channels to monitor")


class AgentConfig(BaseModel):
    """Agent behavior configuration."""

    poll_interval_minutes: int = Field(default=15, description="Interval for polling integrations")
    autonomy_level: str = Field(
        default="suggest",
        description="Agent autonomy: 'suggest' (recommend only), 'auto' (act automatically)",
    )
    output_document_path: str = Field(default="~/personal_assistant_summary.md", description="Path for markdown output")
    reminder_interval_hours: int = Field(default=2, description="Reminder interval in hours")


class Config(BaseSettings):
    """Main application configuration."""

    model_config = SettingsConfigDict(
        env_prefix="PA_",
        env_nested_delimiter="__",
    )

    llm: LLMConfig = Field(default_factory=LLMConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    google: GoogleConfig = Field(default_factory=GoogleConfig)
    slack: SlackConfig = Field(default_factory=SlackConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)


def load_config(config_path: str | Path | None = None) -> Config:
    """Load configuration from YAML file.

    Args:
        config_path: Path to the YAML configuration file. Defaults to config.yaml in CWD.

    Returns:
        Validated Config object.
    """
    if config_path is None:
        config_path = Path("config.yaml")
    else:
        config_path = Path(config_path)

    config_data: dict[str, Any] = {}

    if config_path.exists():
        with open(config_path) as f:
            loaded = yaml.safe_load(f)
            if loaded:
                config_data = loaded

    return Config(**config_data)


# Global config instance - initialized lazily
_config: Config | None = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config() -> None:
    """Reset the global configuration (useful for testing)."""
    global _config
    _config = None
