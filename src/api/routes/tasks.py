"""Task API routes."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
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
from src.services.llm_service import LLMService
from src.utils.config import get_config
from src.services.initiative_service import InitiativeService


class ParseTaskRequest(BaseModel):
    """Request to parse natural language text into tasks."""
    text: str
    

class ParsedTaskInfo(BaseModel):
    """Information about a parsed task."""
    title: str
    description: str | None = None
    priority: str
    confidence: float
    due_date: datetime | None = None
    tags: list[str] | None = None
    suggested_initiative_id: int | None = None


class ParseTaskResponse(BaseModel):
    """Response from parsing natural language text."""
    parsed_tasks: list[ParsedTaskInfo]
    created_tasks: list[TaskResponse] = []

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
    account_id: str | None = Query(default=None, description="Filter by source account ID"),
    search: str | None = Query(default=None, description="Search in title and description"),
    tags: list[str] | None = Query(default=None, description="Filter by tags (matches any)"),
    document_links: list[str] | None = Query(default=None, description="Filter by document links (matches any)"),
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
        account_id=account_id,
        search=search,
        tags=tags,
        document_links=document_links,
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
    # Convert HttpUrl objects to strings
    document_links = None
    if task_data.document_links:
        document_links = [str(url) for url in task_data.document_links]

    task = service.create_task(
        title=task_data.title,
        description=task_data.description,
        priority=task_data.priority,
        source=task_data.source,
        source_reference=task_data.source_reference,
        due_date=task_data.due_date,
        tags=task_data.tags,
        document_links=document_links,
        initiative_id=task_data.initiative_id,
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

    # Convert HttpUrl objects to strings
    document_links = task_data.document_links
    if document_links is not None:
        document_links = [str(url) for url in document_links]

    task = service.update_task(
        task,
        title=task_data.title,
        description=task_data.description,
        status=task_data.status,
        priority=task_data.priority,
        due_date=task_data.due_date,
        tags=task_data.tags,
        document_links=document_links,
        initiative_id=task_data.initiative_id,
        clear_initiative=task_data.clear_initiative,
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


@router.post("/parse", response_model=ParseTaskResponse)
def parse_text_to_tasks(
    request: ParseTaskRequest,
    db: Session = Depends(get_db),
    service: Annotated[TaskService, Depends(get_task_service)] = None,
) -> ParseTaskResponse:
    """Parse natural language text to extract and create tasks.
    
    Uses LLM to analyze text and extract task details including:
    - Title
    - Priority
    - Due date
    - Tags
    - Suggested initiative
    
    Then automatically creates the extracted tasks.
    """
    config = get_config()
    
    # Check if LLM is configured
    if not config.llm.api_key:
        raise HTTPException(
            status_code=400,
            detail="LLM API key not configured"
        )
    
    try:
        # Initialize LLM service
        llm_service = LLMService(config.llm)
        
        # Get active initiatives for LLM context
        initiatives_for_llm = []
        initiative_service = InitiativeService(db)
        active_initiatives = initiative_service.get_active_initiatives()
        initiatives_for_llm = [
            {
                "id": init.id,
                "title": init.title,
                "priority": init.priority.value,
                "description": init.description,
            }
            for init in active_initiatives
        ]
        
        # Extract tasks from text with initiative context
        import asyncio
        extracted_tasks = asyncio.run(
            llm_service.extract_tasks_from_text(
                text=request.text,
                source="api",
                context="User submitted this text via API to create tasks.",
                initiatives=initiatives_for_llm if initiatives_for_llm else None,
            )
        )
        
        # Convert extracted tasks to response format
        parsed_tasks = [
            ParsedTaskInfo(
                title=task.title,
                description=task.description,
                priority=task.priority,
                confidence=task.confidence,
                due_date=task.due_date,
                tags=task.tags,
                suggested_initiative_id=task.suggested_initiative_id,
            )
            for task in extracted_tasks
        ]
        
        # Create tasks automatically
        created_tasks = []
        for extracted in extracted_tasks:
            initiative_id = None
            if extracted.suggested_initiative_id:
                initiative_id = extracted.suggested_initiative_id
            
            task = service.create_task(
                title=extracted.title,
                description=extracted.description,
                priority=TaskPriority(extracted.priority),
                source=TaskSource.MANUAL,
                due_date=extracted.due_date,
                tags=extracted.tags,
                document_links=extracted.document_links,
                initiative_id=initiative_id,
            )
            created_tasks.append(_task_to_response(task))
        
        return ParseTaskResponse(
            parsed_tasks=parsed_tasks,
            created_tasks=created_tasks,
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse tasks: {str(e)}"
        )


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
        account_id=task.account_id,
        priority_score=task.priority_score,
        due_date=task.due_date,
        created_at=task.created_at,
        updated_at=task.updated_at,
        completed_at=task.completed_at,
        tags=task.get_tags_list(),
        document_links=task.get_document_links_list(),
        initiative_id=task.initiative_id,
        initiative_title=task.initiative.title if task.initiative else None,
    )
