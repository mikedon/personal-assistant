"""ProcessedGranolaNote model for tracking processed Granola notes."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.database import Base


class ProcessedGranolaNote(Base):
    """Track which Granola notes have been processed to avoid duplicates."""

    __tablename__ = "processed_granola_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    note_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(200), nullable=False)
    account_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    note_title: Mapped[str] = mapped_column(String(500), nullable=False)
    note_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    tasks_created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("note_id", "account_id", name="uix_note_account"),
        {"extend_existing": True},
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<ProcessedGranolaNote(id={self.id}, note_id={self.note_id}, "
            f"note_title={self.note_title}, tasks_created={self.tasks_created_count})>"
        )
