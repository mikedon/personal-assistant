"""Granola meeting notes integration via local cache access."""

import json
import logging
import os
import stat
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError

from src.integrations.base import (
    ActionableItem,
    ActionableItemType,
    AuthenticationError,
    BaseIntegration,
    IntegrationType,
    PollError,
)
from src.models import ProcessedGranolaNote

logger = logging.getLogger(__name__)


class GranolaIntegration(BaseIntegration):
    """Integration for Granola meeting notes using local cache.

    Note: workspace_id is used as account_id for multi-account consistency.
    This allows multiple Granola workspaces to be treated as separate accounts
    in the integration manager.
    """

    CACHE_PATHS = {
        "darwin": Path.home() / "Library/Application Support/Granola/cache-v3.json",
        "linux": Path.home() / ".config/Granola/cache-v3.json",
    }

    def __init__(
        self,
        config: dict[str, Any],
        account_id: str,
    ):
        """Initialize Granola integration.

        Args:
            config: Workspace configuration dict
            account_id: Workspace identifier
        """
        super().__init__(config, account_id)
        self.workspace_id = config.get("workspace_id", "default")
        self.lookback_days = config.get("lookback_days", 7)
        self.cache_path = self._get_cache_path()

    @property
    def integration_type(self) -> IntegrationType:
        """Return integration type."""
        return IntegrationType.GRANOLA

    def _get_cache_path(self) -> Path:
        """Get cache file path for current platform with validation.

        Returns:
            Validated cache file path

        Raises:
            ValueError: If platform unsupported or APPDATA invalid on Windows
        """
        platform = sys.platform

        # Handle Windows with APPDATA validation (P1 Fix #001)
        if platform == "win32":
            appdata = os.environ.get("APPDATA")
            if not appdata:
                raise ValueError(
                    "APPDATA environment variable not set. "
                    "This is required on Windows for Granola cache access."
                )

            appdata_path = Path(appdata)
            if not appdata_path.is_absolute():
                raise ValueError(
                    f"APPDATA must be an absolute path, got: {appdata}. "
                    "This could indicate a security issue."
                )

            # Normalize path to prevent traversal attacks
            cache_path = appdata_path.resolve() / "Granola/cache-v3.json"
            return cache_path

        # Handle macOS and Linux
        cache_path = self.CACHE_PATHS.get(platform)
        if not cache_path:
            raise ValueError(f"Unsupported platform: {platform}")

        return cache_path

    async def authenticate(self) -> bool:
        """Verify cache file exists and is readable with security checks.

        Returns:
            True if authentication successful

        Raises:
            AuthenticationError: If cache file missing, invalid, or insecure
        """
        if not self.cache_path.exists():
            raise AuthenticationError(
                f"Granola cache file not found at {self.cache_path}. "
                "Ensure Granola desktop app is installed and has synced notes."
            )

        # P1 Fix #002: Security checks for symlinks and permissions
        # Check if symlink (security risk)
        if self.cache_path.is_symlink():
            raise AuthenticationError(
                f"Cache file {self.cache_path} is a symbolic link. "
                "For security reasons, symlinks are not allowed."
            )

        # Check file permissions and ownership (Unix-like systems)
        if hasattr(os, 'stat'):
            try:
                file_stat = self.cache_path.stat()

                # Warn if world-readable (privacy concern)
                if file_stat.st_mode & stat.S_IROTH:
                    logger.warning(
                        f"Cache file {self.cache_path} is world-readable. "
                        "Consider setting permissions to 600 for privacy: "
                        f"chmod 600 {self.cache_path}"
                    )

                # Verify ownership on Unix systems (not Windows)
                if hasattr(file_stat, 'st_uid') and hasattr(os, 'getuid'):
                    if file_stat.st_uid != os.getuid():
                        raise AuthenticationError(
                            f"Cache file {self.cache_path} does not belong to current user. "
                            "This could indicate a security issue or misconfiguration."
                        )
            except OSError as e:
                logger.warning(f"Could not check file permissions: {e}")

        try:
            with open(self.cache_path) as f:
                data = json.load(f)

            # Verify cache structure
            if "cache" not in data:
                raise AuthenticationError("Invalid cache file structure")

            logger.info(f"Successfully authenticated Granola cache at {self.cache_path}")
            return True

        except (json.JSONDecodeError, PermissionError) as e:
            raise AuthenticationError(f"Failed to read Granola cache: {e}")

    async def poll(self) -> list[ActionableItem]:
        """Poll for new meeting notes from local cache.

        Returns:
            List of actionable items from unprocessed notes

        Raises:
            PollError: If polling fails for any reason
        """
        try:
            # Read cache file
            notes = self._read_cache()

            # Filter to new notes (not yet processed)
            new_notes = self._filter_new_notes(notes)

            # Extract actionable items
            items = []
            for note in new_notes:
                item = self._extract_actionable_item(note)
                if item:
                    items.append(item)

            self._update_last_poll()
            logger.info(
                f"Polled Granola workspace '{self.workspace_id}': "
                f"{len(items)} actionable items from {len(new_notes)} new notes"
            )

            return items

        except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
            # Expected errors - cache file issues
            raise PollError(f"Failed to read Granola cache: {e}")

        except Exception as e:
            # Unexpected errors - programming bugs, database issues
            logger.error(f"Unexpected error polling Granola: {e}", exc_info=True)
            raise PollError(f"Unexpected error polling Granola: {e}")

    def _read_cache(self) -> list[dict]:
        """Read and parse Granola cache file."""
        with open(self.cache_path) as f:
            data = json.load(f)

        # Parse nested cache structure
        cache_data = json.loads(data["cache"])
        state = cache_data.get("state", {})

        # Extract documents
        documents = state.get("documents", {})

        # Filter by workspace and date
        cutoff_date = datetime.now(UTC) - timedelta(days=self.lookback_days)

        notes = []
        for doc_id, doc in documents.items():
            # Parse created_at timestamp
            created_at = datetime.fromisoformat(doc.get("created_at", "").replace("Z", "+00:00"))

            # Filter by lookback window
            if created_at < cutoff_date:
                continue

            # Filter by workspace if specified
            workspace = doc.get("workspace_id", "default")
            if self.workspace_id != "all" and workspace != self.workspace_id:
                continue

            notes.append(
                {
                    "id": doc_id,
                    "title": doc.get("title", "Untitled Meeting"),
                    "created_at": created_at,
                    "updated_at": datetime.fromisoformat(
                        doc.get("updated_at", doc.get("created_at", "")).replace("Z", "+00:00")
                    ),
                    "workspace_id": workspace,
                    "panels": doc.get("panels", {}),
                    "people": doc.get("people", []),
                    "url": f"granola://note/{doc_id}",
                }
            )

        return notes

    def _filter_new_notes(self, notes: list[dict]) -> list[dict]:
        """Filter out notes that have already been processed.

        P1 Fix #003: Uses per-operation session instead of stored session.

        Args:
            notes: List of note dictionaries from cache

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
            f"Filtered {len(notes)} notes: {len(new_notes)} new, {len(processed)} already processed"
        )

        return new_notes

    def _extract_actionable_item(self, note: dict) -> ActionableItem | None:
        """Extract actionable item from Granola note."""
        # Build description from panels (ProseMirror JSON content)
        content_parts = []

        # Extract enhanced notes (AI-generated summary)
        panels = note.get("panels", {})
        if "enhanced_notes" in panels:
            enhanced = self._prosemirror_to_text(panels["enhanced_notes"])
            if enhanced:
                content_parts.append(f"**AI Summary:**\n{enhanced}")

        # Extract user notes
        if "my_notes" in panels:
            my_notes = self._prosemirror_to_text(panels["my_notes"])
            if my_notes:
                content_parts.append(f"**My Notes:**\n{my_notes}")

        # Combine content
        description = "\n\n".join(content_parts) if content_parts else ""

        # Add attendee context
        people = note.get("people", [])
        if people and isinstance(people, list):
            # Handle both string names and potential object format
            attendee_names = [
                p if isinstance(p, str) else p.get("name", "Unknown") for p in people[:5]
            ]
            attendees = ", ".join(attendee_names)
            description += f"\n\n**Attendees:** {attendees}"

        # Create actionable item
        return ActionableItem(
            type=ActionableItemType.DOCUMENT_REVIEW,
            title=f"Review meeting: {note['title']}",
            description=description[:1000],  # Limit length for LLM context
            source=IntegrationType.GRANOLA,
            source_reference=note["id"],
            due_date=None,
            priority="medium",
            tags=["meeting-notes", "granola"],
            metadata={
                "note_id": note["id"],
                "workspace_id": note.get("workspace_id"),
                "created_at": note["created_at"].isoformat(),
                "updated_at": note["updated_at"].isoformat(),
                "url": note["url"],
                "attendees": people,
            },
            account_id=self.account_id,
        )

    def _prosemirror_to_text(self, panel_data: dict) -> str:
        """Convert ProseMirror JSON format to plain text."""
        if not panel_data or not isinstance(panel_data, dict):
            return ""

        content = panel_data.get("content", [])
        if not content:
            return ""

        lines = []

        def extract_text(node: dict) -> str:
            """Recursively extract text from ProseMirror node."""
            node_type = node.get("type", "")

            # Text nodes
            if node_type == "text":
                return node.get("text", "")

            # Container nodes - recurse
            if "content" in node:
                parts = [extract_text(child) for child in node["content"]]
                text = "".join(parts)

                # Add formatting based on node type
                if node_type == "heading":
                    level = node.get("attrs", {}).get("level", 1)
                    return f"\n{'#' * level} {text}\n"
                elif node_type == "paragraph":
                    return f"{text}\n"
                elif node_type in ["bulletList", "orderedList"]:
                    return text
                elif node_type == "listItem":
                    return f"• {text}"
                else:
                    return text

            return ""

        for node in content:
            text = extract_text(node)
            if text.strip():
                lines.append(text)

        return "\n".join(lines).strip()

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
                ProcessedGranolaNote.account_id == self.account_id
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
