"""Task API routes."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.schemas import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkStatusUpdate,
    RecalculatePrioritiesResponse,
    TaskCreate,
    TaskListResponse,
    TaskResponse,
    TaskStatistics,
    TaskUpdate,
)
from src.models import Task, TaskPriority, TaskSource, TaskStatus, get_db
from src.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_task_service(db: Session = Depends(get_db)) -> TaskService:
    """Dependency to get task service."""
    return TaskService(db)


@router.get("", response_model=TaskListResponse)
def list_tasks(
    service: Annotated[TaskService, Depends(get_task_service)],
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    source: TaskSource | None = None,
    search: str | None = Query(default=None, description="Search in title and description"),
    tags: list[str] | None = Query(default=None, description="Filter by tags (matches any)"),
    due_before: datetime | None = Query(default=None, description="Filter tasks due before this date"),
    due_after: datetime | None = Query(default=None, description="Filter tasks due after this date"),
    include_completed: bool = Query(default=True, description="Include completed tasks"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TaskListResponse:
    """List all tasks with advanced filtering."""
    tasks, total = service.get_tasks(
        status=status,
        priority=priority,
        source=source,
        search=search,
        tags=tags,
        due_before=due_before,
        due_after=due_after,
        include_completed=include_completed,
        limit=limit,
        offset=offset,
    )

    return TaskListResponse(
        tasks=[_task_to_response(t) for t in tasks],
        total=total,
    )


@router.get("/priority", response_model=TaskListResponse)
def get_prioritized_tasks(
    service: Annotated[TaskService, Depends(get_task_service)],
    limit: int = Query(default=10, ge=1, le=50),
) -> TaskListResponse:
    """Get top priority tasks (pending or in progress)."""
    tasks = service.get_prioritized_tasks(limit=limit)
    return TaskListResponse(tasks=[_task_to_response(t) for t in tasks], total=len(tasks))


@router.get("/overdue", response_model=TaskListResponse)
def get_overdue_tasks(
    service: Annotated[TaskService, Depends(get_task_service)],
) -> TaskListResponse:
    """Get all overdue tasks."""
    tasks = service.get_overdue_tasks()
    return TaskListResponse(tasks=[_task_to_response(t) for t in tasks], total=len(tasks))


@router.get("/due-soon", response_model=TaskListResponse)
def get_due_soon_tasks(
    service: Annotated[TaskService, Depends(get_task_service)],
    days: int = Query(default=3, ge=1, le=30, description="Number of days to look ahead"),
) -> TaskListResponse:
    """Get tasks due within the specified number of days."""
    tasks = service.get_due_soon_tasks(days=days)
    return TaskListResponse(tasks=[_task_to_response(t) for t in tasks], total=len(tasks))


@router.get("/stats", response_model=TaskStatistics)
def get_task_statistics(
    service: Annotated[TaskService, Depends(get_task_service)],
) -> TaskStatistics:
    """Get task statistics and metrics."""
    stats = service.get_statistics()
    return TaskStatistics(**stats)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: int,
    service: Annotated[TaskService, Depends(get_task_service)],
) -> TaskResponse:
    """Get a specific task by ID."""
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_response(task)


@router.post("", response_model=TaskResponse, status_code=201)
def create_task(
    task_data: TaskCreate,
    service: Annotated[TaskService, Depends(get_task_service)],
) -> TaskResponse:
    """Create a new task."""
    task = service.create_task(
        title=task_data.title,
        description=task_data.description,
        priority=task_data.priority,
        source=task_data.source,
        source_reference=task_data.source_reference,
        due_date=task_data.due_date,
        tags=task_data.tags,
    )
    return _task_to_response(task)


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    task_data: TaskUpdate,
    service: Annotated[TaskService, Depends(get_task_service)],
) -> TaskResponse:
    """Update an existing task."""
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task = service.update_task(
        task,
        title=task_data.title,
        description=task_data.description,
        status=task_data.status,
        priority=task_data.priority,
        due_date=task_data.due_date,
        tags=task_data.tags,
    )
    return _task_to_response(task)


@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: int,
    service: Annotated[TaskService, Depends(get_task_service)],
) -> None:
    """Delete a task."""
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    service.delete_task(task)


# Batch Operations
@router.post("/bulk/status", response_model=TaskListResponse)
def bulk_update_status(
    data: BulkStatusUpdate,
    service: Annotated[TaskService, Depends(get_task_service)],
) -> TaskListResponse:
    """Update status for multiple tasks at once."""
    tasks = service.bulk_update_status(data.task_ids, data.status)
    return TaskListResponse(
        tasks=[_task_to_response(t) for t in tasks],
        total=len(tasks),
    )


@router.post("/bulk/delete", response_model=BulkDeleteResponse)
def bulk_delete_tasks(
    data: BulkDeleteRequest,
    service: Annotated[TaskService, Depends(get_task_service)],
) -> BulkDeleteResponse:
    """Delete multiple tasks at once."""
    deleted_count = service.bulk_delete(data.task_ids)
    return BulkDeleteResponse(deleted_count=deleted_count)


@router.post("/recalculate-priorities", response_model=RecalculatePrioritiesResponse)
def recalculate_priorities(
    service: Annotated[TaskService, Depends(get_task_service)],
) -> RecalculatePrioritiesResponse:
    """Recalculate priority scores for all active tasks."""
    updated_count = service.recalculate_all_priorities()
    return RecalculatePrioritiesResponse(updated_count=updated_count)


def _task_to_response(task: Task) -> TaskResponse:
    """Convert Task model to response schema."""
    return TaskResponse(
        id=task.id,
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        source=task.source,
        source_reference=task.source_reference,
        priority_score=task.priority_score,
        due_date=task.due_date,
        created_at=task.created_at,
        updated_at=task.updated_at,
        completed_at=task.completed_at,
        tags=task.get_tags_list(),
    )
