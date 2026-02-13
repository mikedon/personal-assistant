"""Granola meeting notes integration via official MCP server."""

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.exc import IntegrityError

from src.integrations.base import (
    ActionableItem,
    ActionableItemType,
    AuthenticationError,
    BaseIntegration,
    IntegrationType,
    PollError,
)
from src.integrations.granola_oauth import GranolaOAuthManager
from src.integrations.mcp_client import MCPClient
from src.models import ProcessedGranolaNote

logger = logging.getLogger(__name__)


class GranolaIntegration(BaseIntegration):
    """Integration for Granola meeting notes using official MCP server.

    Uses Granola's Model Context Protocol (MCP) server at https://mcp.granola.ai/mcp
    for OAuth-based authentication and HTTP API access to meeting notes.

    Note: workspace_id is used as account_id for multi-account consistency.
    This allows multiple Granola workspaces to be treated as separate accounts
    in the integration manager.
    """

    MCP_SERVER_URL = "https://mcp.granola.ai/mcp"

    def __init__(
        self,
        config: dict[str, Any],
        account_id: str,
    ):
        """Initialize Granola MCP integration.

        Args:
            config: Workspace configuration dict
            account_id: Workspace identifier
        """
        super().__init__(config, account_id)
        self.workspace_id = config.get("workspace_id", "default")
        self.lookback_days = config.get("lookback_days", 7)

        # OAuth setup
        token_path = self._get_token_path(config)
        self.oauth_manager = GranolaOAuthManager(token_path)
        self.mcp_client: MCPClient | None = None

    @property
    def integration_type(self) -> IntegrationType:
        """Return integration type."""
        return IntegrationType.GRANOLA

    def _get_token_path(self, config: dict[str, Any]) -> Path:
        """Get OAuth token storage path.

        Args:
            config: Workspace configuration

        Returns:
            Path to token file
        """
        # Allow custom token path from config
        if "token_path" in config and config["token_path"]:
            return Path(config["token_path"])

        # Default: ~/.personal-assistant/token.granola.json
        return Path.home() / ".personal-assistant" / "token.granola.json"

    async def authenticate(self) -> bool:
        """Authenticate via OAuth and initialize MCP client.

        Runs browser-based OAuth flow if no valid token exists, then
        initializes HTTP client for MCP API calls.

        Returns:
            True if authentication successful

        Raises:
            AuthenticationError: If OAuth flow fails or MCP server unreachable
        """
        try:
            # Get valid OAuth token (may trigger browser flow)
            token = await self.oauth_manager.get_valid_token()

            # Initialize MCP client
            self.mcp_client = MCPClient(
                server_url=self.MCP_SERVER_URL,
                token=token,
            )

            # Test connection with minimal API call
            await self.mcp_client.list_meetings(limit=1)

            logger.info(
                f"Successfully authenticated with Granola MCP server "
                f"(workspace: {self.workspace_id})"
            )
            return True

        except RuntimeError as e:
            raise AuthenticationError(f"Failed to authenticate with Granola: {e}") from e
        except httpx.HTTPError as e:
            raise AuthenticationError(
                f"Failed to connect to Granola MCP server: {e}"
            ) from e
        except Exception as e:
            logger.error(f"Unexpected authentication error: {e}", exc_info=True)
            raise AuthenticationError(f"Authentication failed: {e}") from e

    async def poll(self) -> list[ActionableItem]:
        """Poll MCP server for new meeting notes.

        Fetches meetings from MCP API, filters out already-processed notes,
        and extracts actionable items for the agent.

        Returns:
            List of actionable items from unprocessed meetings

        Raises:
            PollError: If polling fails for any reason
        """
        try:
            # Ensure authenticated
            if not self.mcp_client:
                await self.authenticate()

            # Calculate date filter
            cutoff_date = datetime.now(UTC) - timedelta(days=self.lookback_days)

            # Fetch meetings list from MCP
            workspace_filter = None if self.workspace_id == "all" else self.workspace_id
            all_meetings = await self.mcp_client.list_meetings(
                limit=100,
                workspace_id=workspace_filter,
            )

            logger.debug(f"Fetched {len(all_meetings)} meetings from MCP server")

            # Filter by date
            recent_meetings = [
                m
                for m in all_meetings
                if self._parse_date(m.get("date", "")) > cutoff_date
            ]

            logger.debug(
                f"Filtered to {len(recent_meetings)} meetings within lookback window "
                f"({self.lookback_days} days)"
            )

            # Filter out already-processed notes
            new_meetings = self._filter_new_notes(recent_meetings)

            # Fetch full content for new meetings
            if new_meetings:
                meeting_ids = [m["id"] for m in new_meetings]
                meetings_with_content = await self.mcp_client.get_meetings(
                    meeting_ids=meeting_ids
                )
            else:
                meetings_with_content = []

            # Extract actionable items
            items = []
            for meeting in meetings_with_content:
                item = self._extract_actionable_item(meeting)
                if item:
                    items.append(item)

            self._update_last_poll()
            logger.info(
                f"Polled Granola MCP workspace '{self.workspace_id}': "
                f"{len(items)} actionable items from {len(new_meetings)} new meetings"
            )

            return items

        except httpx.HTTPError as e:
            # Expected HTTP errors
            logger.error(f"HTTP error polling Granola MCP: {e}")
            raise PollError(f"Failed to poll Granola MCP server: {e}") from e

        except Exception as e:
            # Unexpected errors - programming bugs, database issues
            logger.error(f"Unexpected error polling Granola MCP: {e}", exc_info=True)
            raise PollError(f"Unexpected error polling Granola: {e}") from e

    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime.

        Handles multiple formats:
        - ISO format: "2026-02-12T20:30:00Z"
        - Human-readable: "Feb 12, 2026 8:30 PM"

        Args:
            date_str: Date string in various formats

        Returns:
            Datetime object (UTC)
        """
        if not date_str:
            return datetime.min.replace(tzinfo=UTC)

        try:
            # Try ISO format first (most common/fastest)
            normalized = date_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            # Ensure UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except (ValueError, AttributeError):
            pass

        try:
            # Try parsing Granola's human-readable format: "Feb 12, 2026 8:30 PM"
            dt = datetime.strptime(date_str, "%b %d, %Y %I:%M %p")
            # Add UTC timezone
            dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            logger.warning(f"Failed to parse date: {date_str}")
            return datetime.min.replace(tzinfo=UTC)

    def _filter_new_notes(self, notes: list[dict]) -> list[dict]:
        """Filter out notes that have already been processed.

        P1 Fix #003: Uses per-operation session instead of stored session.

        Args:
            notes: List of note dictionaries from MCP API

        Returns:
            List of notes that haven't been processed yet
        """
        from src.models.database import get_db_session

        if not notes:
            return []

        note_ids = [note["id"] for note in notes]

        # P1 Fix #003: Use context manager for proper session lifecycle
        with get_db_session() as db:
            # Query processed notes
            processed = set(
                row[0]
                for row in db.query(ProcessedGranolaNote.note_id)
                .filter(ProcessedGranolaNote.note_id.in_(note_ids))
                .filter(ProcessedGranolaNote.account_id == self.account_id)
                .all()
            )

        # Return only new notes
        new_notes = [note for note in notes if note["id"] not in processed]

        logger.debug(
            f"Filtered {len(notes)} notes: {len(new_notes)} new, "
            f"{len(processed)} already processed"
        )

        return new_notes

    def _extract_actionable_item(self, meeting: dict) -> ActionableItem | None:
        """Extract actionable item from MCP meeting response.

        Expected MCP response structure:
        {
            "id": "note123",
            "title": "Team Standup",
            "date": "2026-02-11T10:00:00Z",
            "attendees": ["alice@example.com", "bob@example.com"],
            "content": "Meeting notes content...",
            "workspace_id": "workspace123"
        }

        Args:
            meeting: Meeting dict from MCP API

        Returns:
            ActionableItem or None if content is empty
        """
        content = meeting.get("content", "")
        title = meeting.get("title", "Untitled Meeting")

        # Skip meetings with no content
        if not content or not content.strip():
            logger.debug(f"Skipping meeting '{title}' - no content")
            return None

        # Add attendee context
        attendees = meeting.get("attendees", [])
        if attendees:
            # Handle both email strings and potential object format
            attendee_list = []
            for attendee in attendees[:5]:
                if isinstance(attendee, str):
                    attendee_list.append(attendee)
                elif isinstance(attendee, dict):
                    attendee_list.append(attendee.get("email", attendee.get("name", "Unknown")))

            if attendee_list:
                attendee_str = ", ".join(attendee_list)
                content += f"\n\n**Attendees:** {attendee_str}"

        # Parse date for metadata
        meeting_date = self._parse_date(meeting.get("date", ""))

        return ActionableItem(
            type=ActionableItemType.DOCUMENT_REVIEW,
            title=f"Review meeting: {title}",
            description=content[:1000],  # Limit length for LLM context
            source=IntegrationType.GRANOLA,
            source_reference=meeting["id"],
            due_date=None,
            priority="medium",
            tags=["meeting-notes", "granola"],
            metadata={
                "note_id": meeting["id"],
                "workspace_id": meeting.get("workspace_id"),
                "date": meeting.get("date"),
                "attendees": attendees,
            },
            account_id=self.account_id,
        )

    def mark_note_processed(
        self,
        note_id: str,
        note_title: str,
        note_created_at: datetime,
        tasks_created: int,
    ) -> None:
        """Mark a note as processed in the database.

        P1 Fixes #003, #004, #005: Uses per-operation session with proper
        transaction handling and race condition prevention.

        Args:
            note_id: Unique identifier for the note
            note_title: Title of the note
            note_created_at: When the note was created
            tasks_created: Number of tasks created from this note
        """
        from src.models.database import get_db_session

        # P1 Fix #003: Use context manager for proper session lifecycle
        with get_db_session() as db:
            # P1 Fix #004: Check if already processed (prevents race condition)
            existing = db.query(ProcessedGranolaNote).filter(
                ProcessedGranolaNote.note_id == note_id,
                ProcessedGranolaNote.account_id == self.account_id,
            ).first()

            if existing:
                logger.debug(
                    f"Note '{note_id}' already marked as processed "
                    f"(original processing: {existing.processed_at})"
                )
                return

            # P1 Fix #005: Proper transaction handling with rollback
            try:
                processed_note = ProcessedGranolaNote(
                    note_id=note_id,
                    workspace_id=self.workspace_id,
                    account_id=self.account_id,
                    note_title=note_title,
                    note_created_at=note_created_at,
                    tasks_created_count=tasks_created,
                )

                db.add(processed_note)
                db.commit()

                logger.debug(
                    f"Marked Granola note '{note_title}' as processed "
                    f"({tasks_created} tasks created)"
                )

            except IntegrityError:
                # Race condition: another agent inserted between our check and insert
                db.rollback()
                logger.debug(
                    f"Note '{note_id}' was marked processed by another agent "
                    "during insertion (race condition handled)"
                )

            except Exception:
                # Unexpected database error - rollback and re-raise
                db.rollback()
                raise
