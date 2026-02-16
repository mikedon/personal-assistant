"""Configuration API routes for reading and updating app settings.

Provides endpoints for:
- GET /api/config - Read current configuration
- PUT /api/config - Update configuration and persist to YAML
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.utils.config import get_config, load_config_from_yaml, save_config_to_yaml

router = APIRouter(prefix="/config", tags=["config"])


class ConfigResponse(BaseModel):
    """Configuration response with all settings."""

    agent: dict[str, Any] = Field(..., description="Agent configuration")
    notifications: dict[str, Any] = Field(..., description="Notification settings")
    llm: dict[str, Any] = Field(..., description="LLM configuration")
    database: dict[str, Any] = Field(..., description="Database configuration")
    google: dict[str, Any] = Field(..., description="Google integration config")
    slack: dict[str, Any] = Field(..., description="Slack integration config")
    granola: dict[str, Any] = Field(..., description="Granola integration config")
    voice: dict[str, Any] = Field(..., description="Voice input configuration")


class ConfigUpdateRequest(BaseModel):
    """Request body for updating configuration."""

    agent: dict[str, Any] | None = None
    notifications: dict[str, Any] | None = None
    llm: dict[str, Any] | None = None
    database: dict[str, Any] | None = None
    google: dict[str, Any] | None = None
    slack: dict[str, Any] | None = None
    granola: dict[str, Any] | None = None
    voice: dict[str, Any] | None = None


@router.get("/", response_model=ConfigResponse)
def get_configuration() -> ConfigResponse:
    """Get current application configuration.

    Returns all settings from config.yaml as JSON for UI population.
    """
    config = get_config()

    return ConfigResponse(
        agent={
            "poll_interval_minutes": config.agent.poll_interval_minutes,
            "autonomy_level": config.agent.autonomy_level,
            "output_document_path": config.agent.output_document_path,
            "reminder_interval_hours": config.agent.reminder_interval_hours,
        },
        notifications={
            "enabled": config.notifications.enabled,
            "sound": config.notifications.sound,
            "on_overdue": config.notifications.on_overdue,
            "on_due_soon": config.notifications.on_due_soon,
            "on_task_created": config.notifications.on_task_created,
            "due_soon_hours": config.notifications.due_soon_hours,
        },
        llm={
            "model": config.llm.model,
            "api_key": config.llm.api_key,
            "base_url": config.llm.base_url,
            "temperature": config.llm.temperature,
            "max_tokens": config.llm.max_tokens,
        },
        database={
            "url": config.database.url,
            "echo": config.database.echo,
        },
        google={
            "enabled": config.google.enabled,
            "accounts": [
                {
                    "account_id": acc.account_id,
                    "display_name": acc.display_name,
                    "enabled": acc.enabled,
                    "polling_interval_minutes": acc.polling_interval_minutes,
                }
                for acc in config.google.accounts
            ],
        },
        slack={
            "enabled": config.slack.enabled,
            "bot_token": config.slack.bot_token,
            "app_token": config.slack.app_token,
            "channels": config.slack.channels,
        },
        granola={
            "enabled": config.granola.enabled,
            "workspaces": [
                {
                    "workspace_id": ws.workspace_id,
                    "display_name": ws.display_name,
                    "enabled": ws.enabled,
                    "lookback_days": ws.lookback_days,
                    "polling_interval_minutes": ws.polling_interval_minutes,
                }
                for ws in config.granola.workspaces
            ],
        },
        voice={
            "enabled": config.voice.enabled,
            "recording_duration_seconds": config.voice.recording_duration_seconds,
            "sample_rate": config.voice.sample_rate,
            "whisper_model": config.voice.whisper_model,
        },
    )


@router.put("/", response_model=ConfigResponse)
def update_configuration(request: ConfigUpdateRequest) -> ConfigResponse:
    """Update application configuration.

    Accepts partial updates. Only provided fields are updated.
    Changes are persisted to config.yaml immediately.

    Args:
        request: Configuration updates

    Returns:
        Updated configuration

    Raises:
        HTTPException: If validation fails or config cannot be saved
    """
    try:
        # Load current config
        config_dict = load_config_from_yaml()

        # Update agent settings
        if request.agent:
            if "autonomy_level" in request.agent:
                level = request.agent["autonomy_level"]
                if level not in ["suggest", "auto_low", "auto", "full"]:
                    raise ValueError(
                        f"Invalid autonomy_level: {level}. Must be one of: suggest, auto_low, auto, full"
                    )
            config_dict["agent"].update(request.agent)

        # Update notification settings
        if request.notifications:
            config_dict["notifications"].update(request.notifications)

        # Update LLM settings (validate non-empty API key if changed)
        if request.llm:
            if "api_key" in request.llm and not request.llm["api_key"]:
                raise ValueError("api_key cannot be empty")
            config_dict["llm"].update(request.llm)

        # Update database settings
        if request.database:
            config_dict["database"].update(request.database)

        # Update integration settings
        if request.google:
            config_dict["google"].update(request.google)
        if request.slack:
            config_dict["slack"].update(request.slack)
        if request.granola:
            config_dict["granola"].update(request.granola)
        if request.voice:
            config_dict["voice"].update(request.voice)

        # Save to YAML
        save_config_to_yaml(config_dict)

        # Force reload of config
        from src.utils.config import reset_config

        reset_config()

        # Return updated configuration
        return get_configuration()

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update configuration: {str(e)}")
