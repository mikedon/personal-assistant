"""Status and dashboard API routes.

Provides endpoints for:
- Dashboard summary
- Tasks due today or overdue
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.models import TaskPriority, TaskStatus, get_db
from src.services.task_service import TaskService

router = APIRouter(prefix="/status", tags=["status"])


class TodayDueTaskResponse(BaseModel):
    """Response schema for a task due today or overdue."""

    id: int
    title: str
    description: str | None
    priority: TaskPriority
    due_date: datetime | None
    status: TaskStatus
    priority_score: float


class TodayDueResponse(BaseModel):
    """Response schema for today-due endpoint."""

    overdue_count: int
    due_today_count: int
    total_count: int
    tasks: list[TodayDueTaskResponse] = Field(default_factory=list)


def get_task_service(db: Session = Depends(get_db)) -> TaskService:
    """Dependency to get task service."""
    return TaskService(db)


@router.get("/tasks/today-due", response_model=TodayDueResponse)
def get_today_due_tasks(
    service: Annotated[TaskService, Depends(get_task_service)],
) -> TodayDueResponse:
    """Get tasks that are due today or overdue.

    Returns both counts and detailed task list for menu bar display.
    """
    # Get overdue tasks
    overdue_tasks = service.get_overdue_tasks()
    overdue_count = len(overdue_tasks)

    # Get tasks due today
    now = datetime.now(UTC).replace(tzinfo=None)
    today_end = now.replace(hour=23, minute=59, second=59)

    due_today_tasks = service.get_tasks(
        status=[TaskStatus.PENDING, TaskStatus.IN_PROGRESS],
        due_after=now.replace(hour=0, minute=0, second=0),
        due_before=today_end,
        include_completed=False,
    )[0]

    # Combine and deduplicate by task ID
    task_ids_included = {t.id for t in overdue_tasks}
    all_tasks = list(overdue_tasks)

    for task in due_today_tasks:
        if task.id not in task_ids_included:
            all_tasks.append(task)
            task_ids_included.add(task.id)

    # Sort by priority score descending
    all_tasks.sort(key=lambda t: t.priority_score, reverse=True)

    return TodayDueResponse(
        overdue_count=overdue_count,
        due_today_count=len(due_today_tasks),
        total_count=len(all_tasks),
        tasks=[
            TodayDueTaskResponse(
                id=t.id,
                title=t.title,
                description=t.description,
                priority=t.priority,
                due_date=t.due_date,
                status=t.status,
                priority_score=t.priority_score,
            )
            for t in all_tasks
        ],
    )
