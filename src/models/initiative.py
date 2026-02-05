"""Initiative model for tracking longer-term projects."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.database import Base


class InitiativeStatus(str, enum.Enum):
    """Status of an initiative."""

    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"


class InitiativePriority(str, enum.Enum):
    """Priority level of an initiative."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Initiative(Base):
    """Initiative model for tracking longer-term projects that tasks roll up to."""

    __tablename__ = "initiatives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[InitiativeStatus] = mapped_column(
        Enum(InitiativeStatus), default=InitiativeStatus.ACTIVE, nullable=False
    )
    priority: Mapped[InitiativePriority] = mapped_column(
        Enum(InitiativePriority), default=InitiativePriority.MEDIUM, nullable=False
    )

    # Target completion date
    target_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationship to tasks (back_populates will be set in Task model)
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="initiative")

    def __repr__(self) -> str:
        return f"<Initiative(id={self.id}, title='{self.title[:30]}...', status={self.status.value})>"
