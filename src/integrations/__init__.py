"""Integrations module for external services."""

from src.integrations.base import (
    ActionableItem,
    ActionableItemType,
    AuthenticationError,
    BaseIntegration,
    IntegrationError,
    IntegrationType,
    PollError,
)
from src.integrations.gmail_integration import GmailIntegration
from src.integrations.manager import IntegrationManager
from src.integrations.oauth_utils import GoogleOAuthManager, SlackOAuthManager
from src.integrations.slack_integration import SlackIntegration

__all__ = [
    "ActionableItem",
    "ActionableItemType",
    "AuthenticationError",
    "BaseIntegration",
    "GmailIntegration",
    "GoogleOAuthManager",
    "IntegrationError",
    "IntegrationManager",
    "IntegrationType",
    "PollError",
    "SlackIntegration",
    "SlackOAuthManager",
]
