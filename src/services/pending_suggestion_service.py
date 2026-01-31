"""Service for managing pending task suggestions."""

import logging
from datetime import datetime, UTC
from typing import Any

from sqlalchemy.orm import Session

from src.integrations.base import IntegrationType
from src.models.pending_suggestion import PendingSuggestionModel, SuggestionStatus

logger = logging.getLogger(__name__)


class PendingSuggestionService:
    """Service for CRUD operations on pending suggestions."""

    def __init__(self, db: Session):
        """Initialize the service.

        Args:
            db: Database session
        """
        self.db = db

    def create_suggestion(
        self,
        title: str,
        description: str | None = None,
        priority: str = "medium",
        due_date: datetime | None = None,
        tags: list[str] | None = None,
        confidence: float = 0.5,
        source: IntegrationType | str | None = None,
        source_reference: str | None = None,
        source_url: str | None = None,
        reasoning: str | None = None,
        original_title: str | None = None,
        original_sender: str | None = None,
        original_snippet: str | None = None,
    ) -> PendingSuggestionModel:
        """Create a new pending suggestion.

        Args:
            title: Suggested task title
            description: Task description
            priority: Priority level
            due_date: Suggested due date
            tags: List of tags
            confidence: LLM confidence score
            source: Source integration type
            source_reference: ID in source system
            source_url: URL to source
            reasoning: Why this task was suggested
            original_title: Original item title
            original_sender: Who sent the original item
            original_snippet: Preview of original content

        Returns:
            Created suggestion model
        """
        suggestion = PendingSuggestionModel(
            title=title,
            description=description,
            priority=priority,
            due_date=due_date,
            confidence=confidence,
            source=source.value if isinstance(source, IntegrationType) else source,
            source_reference=source_reference,
            source_url=source_url,
            reasoning=reasoning,
            original_title=original_title,
            original_sender=original_sender,
            original_snippet=original_snippet,
            status=SuggestionStatus.PENDING,
        )
        suggestion.set_tags_list(tags)

        self.db.add(suggestion)
        self.db.commit()
        self.db.refresh(suggestion)

        logger.info(f"Created pending suggestion: {title[:50]}")
        return suggestion

    def get_pending_suggestions(self) -> list[PendingSuggestionModel]:
        """Get all pending (unresolved) suggestions.

        Returns:
            List of pending suggestions ordered by creation date (oldest first)
        """
        return (
            self.db.query(PendingSuggestionModel)
            .filter(PendingSuggestionModel.status == SuggestionStatus.PENDING)
            .order_by(PendingSuggestionModel.created_at.asc())
            .all()
        )

    def get_suggestion_by_id(self, suggestion_id: int) -> PendingSuggestionModel | None:
        """Get a suggestion by ID.

        Args:
            suggestion_id: The suggestion ID

        Returns:
            Suggestion model or None if not found
        """
        return self.db.query(PendingSuggestionModel).filter(
            PendingSuggestionModel.id == suggestion_id
        ).first()

    def get_suggestion_by_index(self, index: int) -> PendingSuggestionModel | None:
        """Get a pending suggestion by its index in the list.

        Args:
            index: Zero-based index

        Returns:
            Suggestion model or None if index out of range
        """
        suggestions = self.get_pending_suggestions()
        if 0 <= index < len(suggestions):
            return suggestions[index]
        return None

    def approve_suggestion(
        self,
        suggestion_id: int,
        created_task_id: int,
    ) -> bool:
        """Mark a suggestion as approved.

        Args:
            suggestion_id: The suggestion ID
            created_task_id: ID of the task that was created

        Returns:
            True if updated successfully
        """
        suggestion = self.get_suggestion_by_id(suggestion_id)
        if not suggestion:
            return False

        suggestion.status = SuggestionStatus.APPROVED
        suggestion.resolved_at = datetime.now(UTC).replace(tzinfo=None)
        suggestion.created_task_id = created_task_id

        self.db.commit()
        logger.info(f"Approved suggestion {suggestion_id}, created task {created_task_id}")
        return True

    def reject_suggestion(self, suggestion_id: int) -> bool:
        """Mark a suggestion as rejected.

        Args:
            suggestion_id: The suggestion ID

        Returns:
            True if updated successfully
        """
        suggestion = self.get_suggestion_by_id(suggestion_id)
        if not suggestion:
            return False

        suggestion.status = SuggestionStatus.REJECTED
        suggestion.resolved_at = datetime.now(UTC).replace(tzinfo=None)

        self.db.commit()
        logger.info(f"Rejected suggestion {suggestion_id}")
        return True

    def clear_pending_suggestions(self) -> int:
        """Delete all pending suggestions.

        Returns:
            Number of suggestions deleted
        """
        count = (
            self.db.query(PendingSuggestionModel)
            .filter(PendingSuggestionModel.status == SuggestionStatus.PENDING)
            .delete(synchronize_session=False)
        )
        self.db.commit()
        logger.info(f"Cleared {count} pending suggestions")
        return count

    def get_pending_count(self) -> int:
        """Get count of pending suggestions.

        Returns:
            Number of pending suggestions
        """
        return (
            self.db.query(PendingSuggestionModel)
            .filter(PendingSuggestionModel.status == SuggestionStatus.PENDING)
            .count()
        )

    def cleanup_old_suggestions(self, days: int = 30) -> int:
        """Delete resolved suggestions older than specified days.

        Args:
            days: Number of days to keep

        Returns:
            Number of suggestions deleted
        """
        from datetime import timedelta

        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)

        count = (
            self.db.query(PendingSuggestionModel)
            .filter(PendingSuggestionModel.status != SuggestionStatus.PENDING)
            .filter(PendingSuggestionModel.resolved_at < cutoff)
            .delete(synchronize_session=False)
        )

        self.db.commit()
        logger.info(f"Cleaned up {count} old suggestions")
        return count

    def to_dict(self, suggestion: PendingSuggestionModel) -> dict[str, Any]:
        """Convert suggestion model to dictionary.

        Args:
            suggestion: The suggestion model

        Returns:
            Dictionary representation
        """
        return {
            "id": suggestion.id,
            "title": suggestion.title,
            "description": suggestion.description,
            "priority": suggestion.priority,
            "due_date": suggestion.due_date,
            "tags": suggestion.get_tags_list(),
            "confidence": suggestion.confidence,
            "source": suggestion.source,
            "source_reference": suggestion.source_reference,
            "source_url": suggestion.source_url,
            "reasoning": suggestion.reasoning,
            "original_title": suggestion.original_title,
            "original_sender": suggestion.original_sender,
            "original_snippet": suggestion.original_snippet,
            "status": suggestion.status.value,
            "created_at": suggestion.created_at,
        }
