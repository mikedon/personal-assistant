"""Base integration interface and utilities."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class IntegrationType(str, Enum):
    """Types of integrations."""

    GMAIL = "gmail"
    CALENDAR = "calendar"
    SLACK = "slack"
    DRIVE = "drive"


class ActionableItemType(str, Enum):
    """Types of actionable items found in integrations."""

    TASK = "task"
    EMAIL_REPLY_NEEDED = "email_reply_needed"
    DOCUMENT_REVIEW = "document_review"
    MEETING_PREP = "meeting_prep"
    SLACK_RESPONSE = "slack_response"


@dataclass
class ActionableItem:
    """An actionable item extracted from an integration."""

    type: ActionableItemType
    title: str
    description: str | None = None
    source: IntegrationType | None = None
    source_reference: str | None = None  # ID in source system
    due_date: datetime | None = None
    priority: str = "medium"  # Will be mapped to TaskPriority
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None  # Additional context


class BaseIntegration(ABC):
    """Base class for all integrations."""

    def __init__(self, config: dict[str, Any]):
        """Initialize the integration with configuration.

        Args:
            config: Integration-specific configuration
        """
        self.config = config
        self.enabled = config.get("enabled", True)
        self._last_poll: datetime | None = None

    @property
    @abstractmethod
    def integration_type(self) -> IntegrationType:
        """Return the integration type."""
        pass

    @abstractmethod
    async def authenticate(self) -> bool:
        """Authenticate with the external service.

        Returns:
            True if authentication successful, False otherwise.
        """
        pass

    @abstractmethod
    async def poll(self) -> list[ActionableItem]:
        """Poll the integration for new actionable items.

        Returns:
            List of actionable items found since last poll.
        """
        pass

    async def test_connection(self) -> bool:
        """Test if the integration is properly configured and connected.

        Returns:
            True if connection is working, False otherwise.
        """
        try:
            return await self.authenticate()
        except Exception:
            return False

    @property
    def last_poll(self) -> datetime | None:
        """Return the timestamp of the last poll."""
        return self._last_poll

    def _update_last_poll(self) -> None:
        """Update the last poll timestamp to now."""
        self._last_poll = datetime.utcnow()


class IntegrationError(Exception):
    """Base exception for integration errors."""

    pass


class AuthenticationError(IntegrationError):
    """Raised when authentication fails."""

    pass


class PollError(IntegrationError):
    """Raised when polling fails."""

    pass
