"""Slack integration for monitoring channels and extracting actionable items."""

import time
from datetime import datetime, timedelta
from typing import Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from src.integrations.base import (
    ActionableItem,
    ActionableItemType,
    AuthenticationError,
    BaseIntegration,
    IntegrationType,
    PollError,
)
from src.integrations.oauth_utils import SlackOAuthManager


class SlackIntegration(BaseIntegration):
    """Integration with Slack to extract actionable items from messages."""

    def __init__(self, config: dict[str, Any]):
        """Initialize Slack integration.

        Args:
            config: Configuration dict with bot_token, app_token, channels, etc.
        """
        super().__init__(config)
        self.oauth_manager = SlackOAuthManager(
            bot_token=config.get("bot_token", ""),
            app_token=config.get("app_token"),
        )
        self.client: WebClient | None = None
        self.channels = config.get("channels", [])
        self.lookback_hours = config.get("lookback_hours", 24)

    @property
    def integration_type(self) -> IntegrationType:
        """Return the integration type."""
        return IntegrationType.SLACK

    async def authenticate(self) -> bool:
        """Authenticate with Slack API.

        Returns:
            True if authentication successful.

        Raises:
            AuthenticationError: If authentication fails.
        """
        start_time = time.time()
        try:
            bot_token = self.oauth_manager.get_bot_token()
            self.client = WebClient(token=bot_token)
            # Test the authentication
            response = self.client.auth_test()
            self._log_http_request(
                method="POST",
                url="https://slack.com/api/auth.test",
                status_code=200 if response["ok"] else 401,
                duration_seconds=time.time() - start_time,
                request_type="auth_test",
            )
            return response["ok"]
        except Exception as e:
            self._log_http_request(
                method="POST",
                url="https://slack.com/api/auth.test",
                status_code=401,
                duration_seconds=time.time() - start_time,
                request_type="auth_test",
            )
            raise AuthenticationError(f"Slack authentication failed: {e}")

    async def poll(self) -> list[ActionableItem]:
        """Poll Slack for messages that may contain actionable items.

        Returns:
            List of actionable items extracted from Slack messages.

        Raises:
            PollError: If polling fails.
        """
        if not self.client:
            await self.authenticate()

        try:
            items = []
            oldest_ts = (datetime.utcnow() - timedelta(hours=self.lookback_hours)).timestamp()

            for channel in self.channels:
                # Get channel history
                history_start = time.time()
                response = self.client.conversations_history(
                    channel=channel,
                    oldest=str(oldest_ts),
                    limit=100,
                )
                self._log_http_request(
                    method="POST",
                    url="https://slack.com/api/conversations.history",
                    status_code=200 if response.get("ok") else 400,
                    duration_seconds=time.time() - history_start,
                    request_type="conversations_history",
                )

                for message in response.get("messages", []):
                    item = self._extract_actionable_item(message, channel)
                    if item:
                        items.append(item)

            self._update_last_poll()
            return items

        except SlackApiError as e:
            raise PollError(f"Failed to poll Slack: {e}")
        except Exception as e:
            raise PollError(f"Unexpected error polling Slack: {e}")

    def _extract_actionable_item(self, message: dict, channel: str) -> ActionableItem | None:
        """Extract actionable item from a Slack message.

        Args:
            message: Slack message object
            channel: Channel ID

        Returns:
            ActionableItem if the message requires action, None otherwise.
        """
        text = message.get("text", "")
        user = message.get("user", "Unknown")
        ts = message.get("ts")

        # Simple heuristics for actionable messages:
        # 1. Direct mentions (would need to get bot user ID)
        # 2. Questions
        # 3. Action keywords
        
        action_keywords = ["can you", "could you", "please", "need help", "urgent"]
        has_question = "?" in text
        has_action_words = any(keyword in text.lower() for keyword in action_keywords)

        if has_question or has_action_words:
            priority = "medium"
            if "urgent" in text.lower() or "asap" in text.lower():
                priority = "high"

            return ActionableItem(
                type=ActionableItemType.SLACK_RESPONSE,
                title=f"Respond in Slack: {text[:50]}...",
                description=f"Channel: {channel}\nFrom: {user}\n\n{text}",
                source=IntegrationType.SLACK,
                source_reference=f"{channel}:{ts}",
                priority=priority,
                tags=["slack", "response-needed"],
                metadata={
                    "channel": channel,
                    "user": user,
                    "timestamp": ts,
                },
            )

        return None
