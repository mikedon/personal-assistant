"""Pending suggestion model for persisting task suggestions across processes."""

import enum
import json
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.database import Base


class SuggestionStatus(str, enum.Enum):
    """Status of a pending suggestion."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PendingSuggestionModel(Base):
    """Database model for pending task suggestions.

    Persists suggestions so they survive across CLI command invocations
    and can be reviewed later.
    """

    __tablename__ = "pending_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Task details
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)  # JSON array
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)

    # Source context
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)  # gmail, slack, etc.
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Reasoning and context
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_sender: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status tracking
    status: Mapped[SuggestionStatus] = mapped_column(
        Enum(SuggestionStatus), default=SuggestionStatus.PENDING, nullable=False
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # If approved, link to the created task
    created_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<PendingSuggestion(id={self.id}, title='{self.title[:30]}...', status={self.status.value})>"

    def get_tags_list(self) -> list[str]:
        """Get tags as a list."""
        if not self.tags:
            return []
        try:
            return json.loads(self.tags)
        except json.JSONDecodeError:
            return []

    def set_tags_list(self, tags: list[str] | None) -> None:
        """Set tags from a list."""
        self.tags = json.dumps(tags) if tags else None
