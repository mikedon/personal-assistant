"""Pydantic schemas for API request/response models."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from src.models.initiative import InitiativePriority, InitiativeStatus
from src.models.task import TaskPriority, TaskSource, TaskStatus


# Task Schemas
class TaskBase(BaseModel):
    """Base schema for task data."""

    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    document_links: list[HttpUrl] = Field(
        default_factory=list,
        description="External document URLs (HTTP/HTTPS only)",
        max_length=20
    )

    @field_validator('document_links')
    @classmethod
    def validate_document_links(cls, v):
        """Validate document links: protocol whitelist, length limits."""
        if not v:
            return v

        # Check max count
        if len(v) > 20:
            raise ValueError("Maximum 20 document links allowed per task")

        # Validate each URL
        for url in v:
            # HttpUrl already validates format, but check protocol
            if url.scheme not in ['http', 'https']:
                raise ValueError(f"Only http/https URLs allowed, got: {url.scheme}")

        # Check total serialized length (after JSON encoding)
        import json
        serialized = json.dumps([str(url) for url in v])
        if len(serialized) > 5000:
            raise ValueError(
                f"Total document links length ({len(serialized)} chars) exceeds "
                f"limit (5000 chars). Please reduce number or length of URLs."
            )

        return v


class TaskCreate(TaskBase):
    """Schema for creating a new task."""

    source: TaskSource = TaskSource.MANUAL
    source_reference: str | None = None
    initiative_id: int | None = None


class TaskUpdate(BaseModel):
    """Schema for updating a task."""

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: datetime | None = None
    tags: list[str] | None = None
    document_links: list[HttpUrl] | None = None
    initiative_id: int | None = None
    clear_initiative: bool = False

    @field_validator('document_links')
    @classmethod
    def validate_document_links(cls, v):
        """Validate document links: protocol whitelist, length limits."""
        if v is None:
            return v

        # Check max count
        if len(v) > 20:
            raise ValueError("Maximum 20 document links allowed per task")

        # Validate each URL
        for url in v:
            # HttpUrl already validates format, but check protocol
            if url.scheme not in ['http', 'https']:
                raise ValueError(f"Only http/https URLs allowed, got: {url.scheme}")

        # Check total serialized length
        import json
        serialized = json.dumps([str(url) for url in v])
        if len(serialized) > 5000:
            raise ValueError(
                f"Total document links length ({len(serialized)} chars) exceeds "
                f"limit (5000 chars). Please reduce number or length of URLs."
            )

        return v


class TaskResponse(BaseModel):
    """Schema for task response.

    Note: Inherits from BaseModel (not TaskBase) to avoid HttpUrl validation
    on output. Input validation happens in TaskCreate/TaskUpdate.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    source: TaskSource
    source_reference: str | None
    account_id: str | None
    priority_score: float
    due_date: datetime | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    tags: list[str]
    document_links: list[str]  # Plain strings on output (already validated on input)
    initiative_id: int | None = None
    initiative_title: str | None = None


class TaskListResponse(BaseModel):
    """Schema for list of tasks response."""

    tasks: list[TaskResponse]
    total: int


# Batch Operations Schemas
class BulkStatusUpdate(BaseModel):
    """Schema for bulk status update."""

    task_ids: list[int] = Field(..., min_length=1)
    status: TaskStatus


class BulkDeleteRequest(BaseModel):
    """Schema for bulk delete request."""

    task_ids: list[int] = Field(..., min_length=1)


class BulkDeleteResponse(BaseModel):
    """Schema for bulk delete response."""

    deleted_count: int


class RecalculatePrioritiesResponse(BaseModel):
    """Schema for recalculate priorities response."""

    updated_count: int


# Statistics Schemas
class TaskStatistics(BaseModel):
    """Schema for task statistics."""

    total: int
    active: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
    by_source: dict[str, int]
    overdue: int
    due_today: int
    due_this_week: int
    avg_completion_hours: float | None


# Health/Status Schemas
class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    database: str


class AgentStatusResponse(BaseModel):
    """Agent status response."""

    status: str
    last_poll: datetime | None
    tasks_pending: int
    notifications_unread: int


# Voice Schemas
class TranscriptionResponse(BaseModel):
    """Response for audio transcription."""

    text: str
    language: str | None = None
    duration_seconds: float | None = None


class VoiceTaskResponse(BaseModel):
    """Response for voice task creation."""

    transcription: str
    task: "TaskResponse | None" = None
    extracted_tasks_count: int = 0


# Initiative Schemas
class InitiativeBase(BaseModel):
    """Base schema for initiative data."""

    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    priority: InitiativePriority = InitiativePriority.MEDIUM
    target_date: datetime | None = None


class InitiativeCreate(InitiativeBase):
    """Schema for creating a new initiative."""

    pass


class InitiativeUpdate(BaseModel):
    """Schema for updating an initiative."""

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    status: InitiativeStatus | None = None
    priority: InitiativePriority | None = None
    target_date: datetime | None = None


class InitiativeResponse(InitiativeBase):
    """Schema for initiative response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: InitiativeStatus
    created_at: datetime
    updated_at: datetime


class InitiativeProgressResponse(BaseModel):
    """Schema for initiative with progress."""

    initiative: InitiativeResponse
    progress: dict


class InitiativeWithTasksResponse(InitiativeResponse):
    """Schema for initiative with linked tasks."""

    tasks: list[TaskResponse] = Field(default_factory=list)
    progress: dict


class InitiativeListResponse(BaseModel):
    """Schema for list of initiatives response."""

    initiatives: list[InitiativeProgressResponse]
    total: int
