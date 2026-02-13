"""Task model for tracking tasks and priorities."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.database import Base


class TaskStatus(str, enum.Enum):
    """Status of a task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DEFERRED = "deferred"
    CANCELLED = "cancelled"


class TaskPriority(str, enum.Enum):
    """Priority level of a task."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskSource(str, enum.Enum):
    """Source where the task was created from."""

    MANUAL = "manual"
    EMAIL = "email"
    SLACK = "slack"
    CALENDAR = "calendar"
    MEETING_NOTES = "meeting_notes"
    AGENT = "agent"
    VOICE = "voice"


class Task(Base):
    """Task model for tracking work items."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority), default=TaskPriority.MEDIUM, nullable=False
    )
    source: Mapped[TaskSource] = mapped_column(
        Enum(TaskSource), default=TaskSource.MANUAL, nullable=False
    )

    # Computed priority score (0-100) based on various factors
    priority_score: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)

    # Dates
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Reference to source (e.g., email ID, Slack message ID)
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Account identifier for multi-account integrations (e.g., "personal", "work")
    account_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )

    # Tags for categorization (stored as comma-separated string)
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Document links (stored as JSON array of URLs)
    document_links: Mapped[str | None] = mapped_column(String(5000), nullable=True)

    # Initiative relationship (optional - task can belong to an initiative)
    initiative_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("initiatives.id", ondelete="SET NULL"), nullable=True
    )
    initiative: Mapped["Initiative | None"] = relationship(
        "Initiative", back_populates="tasks"
    )

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, title='{self.title[:30]}...', status={self.status.value})>"

    def get_tags_list(self) -> list[str]:
        """Get tags as a list."""
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    def set_tags_list(self, tags: list[str]) -> None:
        """Set tags from a list."""
        self.tags = ",".join(tags) if tags else None

    def get_document_links_list(self) -> list[str]:
        """Get document links as a list.

        Supports both JSON format (new) and CSV format (legacy) for backward compatibility.
        """
        if not self.document_links:
            return []

        # Try JSON format first (new storage method)
        try:
            import json
            links = json.loads(self.document_links)
            if isinstance(links, list):
                return links
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback to CSV format (legacy)
        return [link.strip() for link in self.document_links.split(",") if link.strip()]

    def set_document_links_list(self, links: list[str] | None) -> None:
        """Set document links from a list.

        Stores as JSON array to prevent CSV injection and handle URLs with special characters.
        """
        if not links:
            self.document_links = None
        else:
            import json
            self.document_links = json.dumps(links)
