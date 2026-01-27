"""Agent log model for tracking agent activity and decisions."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.database import Base


class LogLevel(str, enum.Enum):
    """Log level for agent activity."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class AgentAction(str, enum.Enum):
    """Types of actions the agent can take."""

    POLL_EMAIL = "poll_email"
    POLL_CALENDAR = "poll_calendar"
    POLL_SLACK = "poll_slack"
    POLL_DRIVE = "poll_drive"
    CREATE_TASK = "create_task"
    UPDATE_TASK = "update_task"
    SEND_NOTIFICATION = "send_notification"
    GENERATE_SUMMARY = "generate_summary"
    LLM_REQUEST = "llm_request"
    SCHEDULE_MEETING = "schedule_meeting"
    CALENDAR_OPTIMIZATION = "calendar_optimization"


class AgentLog(Base):
    """Log entry for agent activity."""

    __tablename__ = "agent_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    level: Mapped[LogLevel] = mapped_column(Enum(LogLevel), default=LogLevel.INFO, nullable=False)
    action: Mapped[AgentAction | None] = mapped_column(Enum(AgentAction), nullable=True)

    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    # For tracking LLM usage
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # For tracking related entities
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<AgentLog(id={self.id}, level={self.level.value}, action={self.action})>"
