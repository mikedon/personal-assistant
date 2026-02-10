"""Gmail integration for reading and extracting actionable items from emails."""

import base64
import time
from datetime import datetime, timedelta
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

    # Mapping of inbox_type config to Gmail query operators
    INBOX_TYPE_QUERIES = {
        "all": "",
        "unread": "is:unread",
        "not_spam": "-in:spam",
        "important": "is:important",
    }

    def __init__(self, account_config: Any = None, config: dict[str, Any] | None = None):
        """Initialize Gmail integration.

        Args:
            account_config: GoogleAccountConfig object (preferred) for multi-account support
            config: Legacy dict configuration for backwards compatibility
        """
        # Handle both new (GoogleAccountConfig) and old (dict) formats
        if account_config is not None and hasattr(account_config, "account_id"):
            # New multi-account format with GoogleAccountConfig
            super().__init__({}, account_id=account_config.account_id)
            self.account_config = account_config
            credentials_path = account_config.credentials_path
            token_path = account_config.token_path
            scopes = account_config.scopes
            gmail_config = account_config.gmail
        else:
            # Legacy dict format for backwards compatibility
            if account_config is not None and isinstance(account_config, dict):
                config = account_config
            if config is None:
                config = {}
            super().__init__(config)
            self.account_config = None
            credentials_path = config.get("credentials_path", "credentials.json")
            token_path = config.get("token_path", "token.json")
            scopes = config.get("scopes", self.SCOPES)
            gmail_config = config.get("gmail", {})

        self.oauth_manager = GoogleOAuthManager(
            credentials_path=credentials_path,
            token_path=token_path,
            scopes=scopes,
        )
        self.service = None

        # Get gmail-specific config
        if hasattr(gmail_config, "max_results"):
            # Pydantic model
            self.max_results = gmail_config.max_results
            self.lookback_days = gmail_config.lookback_days
            self.lookback_hours = gmail_config.lookback_hours
            self.inbox_type = gmail_config.inbox_type
            self.include_senders = [s.lower() for s in gmail_config.include_senders]
            self.exclude_senders = [s.lower() for s in gmail_config.exclude_senders]
            self.include_subjects = [s.lower() for s in gmail_config.include_subjects]
            self.exclude_subjects = [s.lower() for s in gmail_config.exclude_subjects]
            self.priority_senders = [s.lower() for s in gmail_config.priority_senders]
        else:
            # Dict format - check both nested gmail config and root config for backwards compatibility
            # Nested config takes precedence over root-level config
            root_config = config if config else {}
            self.max_results = gmail_config.get("max_results") or root_config.get("max_results", 10)
            self.lookback_days = gmail_config.get("lookback_days") or root_config.get("lookback_days", 1)
            self.lookback_hours = gmail_config.get("lookback_hours") or root_config.get("lookback_hours")
            self.inbox_type = gmail_config.get("inbox_type") or root_config.get("inbox_type", "unread")
            self.include_senders = [s.lower() for s in (gmail_config.get("include_senders") or root_config.get("include_senders", []))]
            self.exclude_senders = [s.lower() for s in (gmail_config.get("exclude_senders") or root_config.get("exclude_senders", []))]
            self.include_subjects = [s.lower() for s in (gmail_config.get("include_subjects") or root_config.get("include_subjects", []))]
            self.exclude_subjects = [s.lower() for s in (gmail_config.get("exclude_subjects") or root_config.get("exclude_subjects", []))]
            self.priority_senders = [s.lower() for s in (gmail_config.get("priority_senders") or root_config.get("priority_senders", []))]

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

    def _build_query(self) -> str:
        """Build Gmail search query based on configuration.

        Returns:
            Gmail search query string.
        """
        query_parts = []

        # Add inbox type filter
        inbox_query = self.INBOX_TYPE_QUERIES.get(self.inbox_type, "is:unread")
        if inbox_query:
            query_parts.append(inbox_query)

        # Calculate lookback time (hours takes precedence over days)
        if self.lookback_hours is not None:
            lookback_time = datetime.utcnow() - timedelta(hours=self.lookback_hours)
        else:
            lookback_time = datetime.utcnow() - timedelta(days=self.lookback_days)
        query_parts.append(f"after:{lookback_time.strftime('%Y/%m/%d')}")

        # Add sender filters to query if possible (Gmail supports from: operator)
        # Note: We still do post-fetch filtering for more precise matching
        if self.include_senders and len(self.include_senders) <= 5:
            # Gmail OR syntax: from:(addr1 OR addr2)
            sender_query = " OR ".join(self.include_senders)
            query_parts.append(f"from:({sender_query})")

        return " ".join(query_parts)

    async def poll(self) -> list[ActionableItem]:
        """Poll Gmail for emails that may contain actionable items.

        Returns:
            List of actionable items extracted from emails.

        Raises:
            PollError: If polling fails.
        """
        if not self.service:
            await self.authenticate()

        try:
            items = []

            # Build query from configuration
            query = self._build_query()

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

    def _should_include_email(self, sender: str, subject: str) -> bool:
        """Check if an email should be included based on filter configuration.

        Args:
            sender: Email sender address
            subject: Email subject line

        Returns:
            True if email passes all filters, False if it should be excluded.
        """
        sender_lower = sender.lower()
        subject_lower = subject.lower()

        # Check sender exclusion (exclude takes precedence)
        if self.exclude_senders:
            if any(excluded in sender_lower for excluded in self.exclude_senders):
                return False

        # Check sender inclusion (if specified, sender must match)
        if self.include_senders:
            if not any(included in sender_lower for included in self.include_senders):
                return False

        # Check subject exclusion
        if self.exclude_subjects:
            if any(excluded in subject_lower for excluded in self.exclude_subjects):
                return False

        # Check subject inclusion (if specified, subject must match)
        if self.include_subjects:
            if not any(included in subject_lower for included in self.include_subjects):
                return False

        return True

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

        # Apply sender/subject filters
        if not self._should_include_email(sender, subject):
            return None

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

            metadata = {
                "sender": sender,
                "subject": subject,
                "date": date_str,
                "thread_id": message.get("threadId"),
            }

            return ActionableItem(
                type=ActionableItemType.EMAIL_REPLY_NEEDED,
                title=f"Reply to: {subject}",
                description=f"From: {sender}\n\n{body[:200] if body else 'No preview available'}...",
                source=IntegrationType.GMAIL,
                source_reference=message_id,
                due_date=due_date,
                priority=priority,
                tags=["email", "reply-needed"],
                metadata=metadata,
                account_id=self.account_id,
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
        return any(priority in sender.lower() for priority in self.priority_senders)

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
