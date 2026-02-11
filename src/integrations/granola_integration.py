"""Granola meeting notes integration via local cache access."""

import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from src.integrations.base import (
    ActionableItem,
    ActionableItemType,
    AuthenticationError,
    BaseIntegration,
    IntegrationType,
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
        "win32": Path(os.environ.get("APPDATA", "")) / "Granola/cache-v3.json",
        "linux": Path.home() / ".config/Granola/cache-v3.json",
    }

    def __init__(
        self,
        config: dict[str, Any],
        account_id: str,
        db_session: Session,
    ):
        """Initialize Granola integration.

        Args:
            config: Workspace configuration dict
            account_id: Workspace identifier
            db_session: Database session for querying processed notes
        """
        super().__init__(config, account_id)
        self.db = db_session
        self.workspace_id = config.get("workspace_id", "default")
        self.lookback_days = config.get("lookback_days", 7)
        self.cache_path = self._get_cache_path()

    @property
    def integration_type(self) -> IntegrationType:
        """Return integration type."""
        return IntegrationType.GRANOLA

    def _get_cache_path(self) -> Path:
        """Get cache file path for current platform."""
        platform = sys.platform
        cache_path = self.CACHE_PATHS.get(platform)

        if not cache_path:
            raise ValueError(f"Unsupported platform: {platform}")

        return cache_path

    async def authenticate(self) -> bool:
        """Verify cache file exists and is readable."""
        if not self.cache_path.exists():
            raise AuthenticationError(
                f"Granola cache file not found at {self.cache_path}. "
                "Ensure Granola desktop app is installed and has synced notes."
            )

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
        """Poll for new meeting notes from local cache."""
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

        except Exception as e:
            logger.error(f"Error polling Granola: {e}")
            return []

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
        """Filter out notes that have already been processed."""
        note_ids = [note["id"] for note in notes]

        # Query processed notes
        processed = set(
            row[0]
            for row in self.db.query(ProcessedGranolaNote.note_id)
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
        """Mark a note as processed in the database."""
        processed_note = ProcessedGranolaNote(
            note_id=note_id,
            workspace_id=self.workspace_id,
            account_id=self.account_id,
            note_title=note_title,
            note_created_at=note_created_at,
            tasks_created_count=tasks_created,
        )

        self.db.add(processed_note)
        self.db.commit()

        logger.debug(
            f"Marked Granola note '{note_title}' as processed ({tasks_created} tasks created)"
        )
