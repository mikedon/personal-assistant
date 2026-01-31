"""Gmail integration for reading and extracting actionable items from emails."""

import base64
import time
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.integrations.base import (
    ActionableItem,
    ActionableItemType,
    AuthenticationError,
    BaseIntegration,
    IntegrationType,
    PollError,
)
from src.integrations.oauth_utils import GoogleOAuthManager


class GmailIntegration(BaseIntegration):
    """Integration with Gmail to extract actionable items from emails."""

    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

    def __init__(self, config: dict[str, Any]):
        """Initialize Gmail integration.

        Args:
            config: Configuration dict with credentials_path, token_path, etc.
        """
        super().__init__(config)
        self.oauth_manager = GoogleOAuthManager(
            credentials_path=config.get("credentials_path", "credentials.json"),
            token_path=config.get("token_path", "token.json"),
            scopes=self.SCOPES,
        )
        self.service = None
        self.max_results = config.get("max_results", 10)
        self.lookback_days = config.get("lookback_days", 1)

    @property
    def integration_type(self) -> IntegrationType:
        """Return the integration type."""
        return IntegrationType.GMAIL

    async def authenticate(self) -> bool:
        """Authenticate with Gmail API.

        Returns:
            True if authentication successful.

        Raises:
            AuthenticationError: If authentication fails.
        """
        start_time = time.time()
        try:
            creds = self.oauth_manager.get_credentials()
            self.service = build("gmail", "v1", credentials=creds)

            # Log authentication HTTP call
            self._log_http_request(
                method="POST",
                url="https://oauth2.googleapis.com/token",
                status_code=200,
                duration_seconds=time.time() - start_time,
                request_type="oauth_token_refresh",
            )
            return True
        except Exception as e:
            self._log_http_request(
                method="POST",
                url="https://oauth2.googleapis.com/token",
                status_code=401,
                duration_seconds=time.time() - start_time,
                request_type="oauth_token_refresh",
            )
            raise AuthenticationError(f"Gmail authentication failed: {e}")

    async def poll(self) -> list[ActionableItem]:
        """Poll Gmail for unread emails that may contain actionable items.

        Returns:
            List of actionable items extracted from emails.

        Raises:
            PollError: If polling fails.
        """
        if not self.service:
            await self.authenticate()

        try:
            items = []

            # Calculate lookback time
            lookback_time = datetime.utcnow() - timedelta(days=self.lookback_days)
            query = f"is:unread after:{lookback_time.strftime('%Y/%m/%d')}"

            # Get list of unread messages
            list_start = time.time()
            results = (
                self.service.users()
                .messages()
                .list(userId="me", q=query, maxResults=self.max_results)
                .execute()
            )
            self._log_http_request(
                method="GET",
                url="https://gmail.googleapis.com/gmail/v1/users/me/messages",
                status_code=200,
                duration_seconds=time.time() - list_start,
                request_type="list_messages",
            )

            messages = results.get("messages", [])

            for msg in messages:
                # Get full message details
                get_start = time.time()
                message = (
                    self.service.users()
                    .messages()
                    .get(userId="me", id=msg["id"], format="full")
                    .execute()
                )
                self._log_http_request(
                    method="GET",
                    url=f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg['id']}",
                    status_code=200,
                    duration_seconds=time.time() - get_start,
                    request_type="get_message",
                )

                item = self._extract_actionable_item(message)
                if item:
                    items.append(item)

            self._update_last_poll()
            return items

        except HttpError as e:
            raise PollError(f"Failed to poll Gmail: {e}")
        except Exception as e:
            raise PollError(f"Unexpected error polling Gmail: {e}")

    def _extract_actionable_item(self, message: dict) -> ActionableItem | None:
        """Extract actionable item from a Gmail message.

        Args:
            message: Gmail message object

        Returns:
            ActionableItem if the email requires action, None otherwise.
        """
        headers = {h["name"]: h["value"] for h in message["payload"]["headers"]}
        
        subject = headers.get("Subject", "(No Subject)")
        sender = headers.get("From", "Unknown")
        date_str = headers.get("Date")
        message_id = message["id"]

        # Try to parse email body
        body = self._get_message_body(message["payload"])

        # Simple heuristic: emails are actionable if they:
        # 1. Have question marks (likely questions)
        # 2. Contain action words
        # 3. Are from specific senders (configurable)
        
        action_keywords = ["please", "could you", "can you", "need", "urgent", "asap", "action required"]
        question_marks = body.count("?") if body else 0
        has_action_words = any(keyword in body.lower() if body else False for keyword in action_keywords)

        if question_marks > 0 or has_action_words or self._is_priority_sender(sender):
            # Determine priority
            priority = "medium"
            if "urgent" in subject.lower() or "urgent" in (body.lower() if body else ""):
                priority = "high"
            elif "asap" in subject.lower() or "asap" in (body.lower() if body else ""):
                priority = "critical"

            # Parse due date (if any time-sensitive language)
            due_date = None
            if "today" in (body.lower() if body else "") or "today" in subject.lower():
                due_date = datetime.utcnow()
            elif "tomorrow" in (body.lower() if body else "") or "tomorrow" in subject.lower():
                due_date = datetime.utcnow() + timedelta(days=1)

            return ActionableItem(
                type=ActionableItemType.EMAIL_REPLY_NEEDED,
                title=f"Reply to: {subject}",
                description=f"From: {sender}\n\n{body[:200] if body else 'No preview available'}...",
                source=IntegrationType.GMAIL,
                source_reference=message_id,
                due_date=due_date,
                priority=priority,
                tags=["email", "reply-needed"],
                metadata={
                    "sender": sender,
                    "subject": subject,
                    "date": date_str,
                    "thread_id": message.get("threadId"),
                },
            )

        return None

    def _get_message_body(self, payload: dict) -> str | None:
        """Extract text body from message payload.

        Args:
            payload: Gmail message payload

        Returns:
            Decoded message body text or None.
        """
        if "parts" in payload:
            # Multi-part message
            for part in payload["parts"]:
                if part["mimeType"] == "text/plain":
                    data = part["body"].get("data")
                    if data:
                        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        elif "body" in payload:
            # Simple message
            data = payload["body"].get("data")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

        return None

    def _is_priority_sender(self, sender: str) -> bool:
        """Check if sender is in priority list.

        Args:
            sender: Email sender

        Returns:
            True if sender is priority.
        """
        priority_senders = self.config.get("priority_senders", [])
        return any(priority in sender.lower() for priority in priority_senders)

    async def mark_as_read(self, message_id: str) -> bool:
        """Mark an email as read.

        Args:
            message_id: Gmail message ID

        Returns:
            True if successful.
        """
        try:
            self.service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
            return True
        except Exception:
            return False
