"""Configuration management with YAML support and Pydantic validation."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator
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


class GmailQueryConfig(BaseModel):
    """Gmail query configuration for filtering emails."""

    inbox_type: str = Field(
        default="unread",
        description="Inbox filter type: 'all', 'unread', 'not_spam', 'important'",
    )
    lookback_hours: int | None = Field(
        default=None,
        description="Hours to look back (takes precedence over lookback_days if set)",
    )
    lookback_days: int = Field(default=1, ge=1, description="Days to look back for emails")
    max_results: int = Field(default=10, ge=1, le=100, description="Maximum emails to fetch per poll")
    include_senders: list[str] = Field(
        default=[],
        description="Only process emails from these senders (empty = all senders)",
    )
    exclude_senders: list[str] = Field(
        default=[],
        description="Ignore emails from these senders",
    )
    include_subjects: list[str] = Field(
        default=[],
        description="Only process emails with subjects containing these patterns (empty = all subjects)",
    )
    exclude_subjects: list[str] = Field(
        default=[],
        description="Skip emails with subjects containing these patterns",
    )
    priority_senders: list[str] = Field(
        default=[],
        description="Emails from these senders are marked high priority",
    )


class GoogleAccountConfig(BaseModel):
    """Configuration for a single Google account."""

    account_id: str = Field(description="Unique identifier (e.g., 'personal', 'work')")
    display_name: str = Field(description="Human-readable name")
    enabled: bool = Field(default=True, description="Enable this account")
    credentials_path: str = Field(default="credentials.json", description="Path to OAuth credentials file")
    token_path: str = Field(default="token.json", description="Path to store OAuth token")
    scopes: list[str] = Field(
        default=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
    )
    polling_interval_minutes: int = Field(default=5, ge=1, description="Per-account polling interval")
    gmail: GmailQueryConfig = Field(default_factory=GmailQueryConfig, description="Gmail query settings")

    @field_validator("account_id")
    @classmethod
    def validate_account_id(cls, v: str) -> str:
        """Ensure account_id is lowercase, alphanumeric + underscores."""
        if not v.islower() or not v.replace("_", "").isalnum():
            raise ValueError(
                "account_id must be lowercase alphanumeric with underscores only"
            )
        return v


class GoogleConfig(BaseModel):
    """Google API configuration for Gmail, Calendar, and Drive."""

    enabled: bool = Field(default=False, description="Enable Google integrations")
    accounts: list[GoogleAccountConfig] = Field(default=[], description="List of Google accounts")

    @field_validator("accounts")
    @classmethod
    def validate_unique_account_ids(cls, v: list[GoogleAccountConfig]) -> list[GoogleAccountConfig]:
        """Ensure account_id values are unique."""
        account_ids = [acc.account_id for acc in v]
        if len(account_ids) != len(set(account_ids)):
            raise ValueError("account_id values must be unique")
        return v


class SlackConfig(BaseModel):
    """Slack API configuration."""

    enabled: bool = Field(default=False, description="Enable Slack integration")
    bot_token: str = Field(default="", description="Slack bot token")
    app_token: str = Field(default="", description="Slack app token for socket mode")
    channels: list[str] = Field(default=[], description="Channels to monitor")


class GranolaWorkspaceConfig(BaseModel):
    """Configuration for a Granola workspace."""

    workspace_id: str = Field(..., description="Workspace ID or 'all' to scan all workspaces")
    display_name: str = Field(default="", description="Friendly name for this workspace")
    enabled: bool = Field(default=True, description="Enable/disable this workspace")
    lookback_days: int = Field(
        default=7,
        ge=1,
        le=90,
        description="How many days back to scan for new notes",
    )
    polling_interval_minutes: int = Field(
        default=15,
        ge=1,
        le=1440,
        description="Polling frequency in minutes",
    )
    token_path: str | None = Field(
        default=None,
        description="Path to OAuth token file (default: ~/.personal-assistant/token.granola.json)",
    )

    @field_validator("workspace_id")
    @classmethod
    def validate_workspace_id(cls, v: str) -> str:
        """Validate workspace ID format."""
        if v != "all" and not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("workspace_id must be 'all' or alphanumeric with - and _")
        return v.lower()


class GranolaConfig(BaseModel):
    """Granola integration configuration."""

    enabled: bool = Field(default=False, description="Enable Granola integration")
    workspaces: list[GranolaWorkspaceConfig] = Field(
        default=[],
        description="List of Granola workspaces to monitor",
    )

    @field_validator("workspaces")
    @classmethod
    def validate_unique_workspace_ids(cls, v: list[GranolaWorkspaceConfig]) -> list[GranolaWorkspaceConfig]:
        """Ensure workspace IDs are unique."""
        ids = [w.workspace_id for w in v]
        if len(ids) != len(set(ids)):
            raise ValueError("workspace_id values must be unique")
        return v


class NotificationConfig(BaseModel):
    """Notification configuration."""

    enabled: bool = Field(default=True, description="Enable notifications")
    sound: bool = Field(default=True, description="Play sound with notifications")
    # Notification triggers
    on_overdue: bool = Field(default=True, description="Notify when tasks become overdue")
    on_due_soon: bool = Field(default=True, description="Notify when tasks are due soon")
    on_task_created: bool = Field(default=False, description="Notify when agent creates tasks")
    due_soon_hours: int = Field(default=4, description="Hours before due date to notify")


class VoiceConfig(BaseModel):
    """Voice input configuration."""

    enabled: bool = Field(default=True, description="Enable voice input features")
    recording_duration_seconds: int = Field(default=10, ge=1, le=60, description="Default recording duration")
    sample_rate: int = Field(default=16000, description="Audio sample rate (16000 recommended for Whisper)")
    whisper_model: str = Field(default="whisper-1", description="Whisper model variant")


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
    granola: GranolaConfig = Field(default_factory=GranolaConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)


def migrate_legacy_google_config(config_dict: dict) -> dict:
    """Migrate old single-account config to new multi-account format.

    Old format:
        google:
          enabled: true
          credentials_path: "credentials.json"
          token_path: "token.json"
          scopes: [...]
          gmail: {...}

    New format:
        google:
          enabled: true
          accounts:
            - account_id: "default"
              credentials_path: "credentials.json"
              ...
    """
    if "google" not in config_dict:
        return config_dict

    google_config = config_dict["google"]

    # Check if already using new format
    if "accounts" in google_config:
        return config_dict

    # Migrate to new format
    if "credentials_path" in google_config:
        # Wrap existing config in accounts array
        legacy_account = {
            "account_id": "default",
            "display_name": "Default Account",
            "enabled": google_config.get("enabled", True),
            "credentials_path": google_config["credentials_path"],
            "token_path": google_config.get("token_path", "token.json"),
            "scopes": google_config.get("scopes", [
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/drive.readonly",
            ]),
            "polling_interval_minutes": google_config.get("polling_interval_minutes", 5),
            "gmail": google_config.get("gmail", {}),
        }
        config_dict["google"] = {
            "enabled": google_config.get("enabled", True),
            "accounts": [legacy_account],
        }

    return config_dict


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

    # Migrate legacy config if needed
    config_data = migrate_legacy_google_config(config_data)

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
