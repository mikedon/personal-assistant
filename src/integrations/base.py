"""Base integration interface and utilities."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable

# Type for HTTP logging callback
HttpLogCallback = Callable[[str, str, int | None, float | None, str | None, str | None], None]


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
        self._http_log_callback: HttpLogCallback | None = None

    def set_http_log_callback(self, callback: HttpLogCallback | None) -> None:
        """Set the HTTP logging callback.

        Args:
            callback: Callback function for logging HTTP requests
        """
        self._http_log_callback = callback

    def _log_http_request(
        self,
        method: str,
        url: str,
        status_code: int | None = None,
        duration_seconds: float | None = None,
        request_type: str | None = None,
    ) -> None:
        """Log an HTTP request using the configured callback.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            status_code: Response status code
            duration_seconds: Request duration
            request_type: Type of request
        """
        if self._http_log_callback:
            self._http_log_callback(
                method,
                url,
                status_code,
                duration_seconds,
                self.integration_type.value,
                request_type,
            )

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
