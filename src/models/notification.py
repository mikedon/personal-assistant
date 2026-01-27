"""Notification model for tracking alerts and reminders."""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.database import Base


class NotificationType(str, enum.Enum):
    """Type of notification."""

    REMINDER = "reminder"
    TASK_DUE = "task_due"
    DOCUMENT_REVIEW = "document_review"
    MEETING_UPCOMING = "meeting_upcoming"
    EMAIL_IMPORTANT = "email_important"
    SLACK_MENTION = "slack_mention"
    RECOMMENDATION = "recommendation"


class Notification(Base):
    """Notification model for alerts and reminders."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    notification_type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType), nullable=False
    )

    # Whether the notification has been shown/delivered
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # When to show the notification (for scheduled notifications)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Reference to related entity (task_id, document_id, etc.)
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, type={self.notification_type.value}, read={self.is_read})>"
