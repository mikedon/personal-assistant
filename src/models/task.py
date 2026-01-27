"""Task model for tracking tasks and priorities."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

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

    # Tags for categorization (stored as comma-separated string)
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)

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
