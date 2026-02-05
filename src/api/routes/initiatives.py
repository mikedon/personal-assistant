"""Initiative API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.schemas import (
    InitiativeCreate,
    InitiativeListResponse,
    InitiativeProgressResponse,
    InitiativeResponse,
    InitiativeUpdate,
    InitiativeWithTasksResponse,
    TaskResponse,
)
from src.models import Initiative, InitiativePriority, InitiativeStatus, get_db
from src.services.initiative_service import InitiativeService

router = APIRouter(prefix="/initiatives", tags=["initiatives"])


def get_initiative_service(db: Session = Depends(get_db)) -> InitiativeService:
    """Dependency to get initiative service."""
    return InitiativeService(db)


@router.get("", response_model=InitiativeListResponse)
def list_initiatives(
    service: Annotated[InitiativeService, Depends(get_initiative_service)],
    status: InitiativeStatus | None = None,
    priority: InitiativePriority | None = None,
    include_completed: bool = Query(default=False, description="Include completed initiatives"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> InitiativeListResponse:
    """List all initiatives with progress information."""
    initiatives, total = service.get_initiatives(
        status=status,
        priority=priority,
        include_completed=include_completed,
        limit=limit,
        offset=offset,
    )

    initiatives_with_progress = []
    for initiative in initiatives:
        progress = service.get_initiative_progress(initiative.id)
        initiatives_with_progress.append(
            InitiativeProgressResponse(
                initiative=_initiative_to_response(initiative),
                progress=progress,
            )
        )

    return InitiativeListResponse(
        initiatives=initiatives_with_progress,
        total=total,
    )


@router.get("/active", response_model=InitiativeListResponse)
def get_active_initiatives(
    service: Annotated[InitiativeService, Depends(get_initiative_service)],
) -> InitiativeListResponse:
    """Get all active initiatives with progress."""
    initiatives = service.get_active_initiatives()

    initiatives_with_progress = []
    for initiative in initiatives:
        progress = service.get_initiative_progress(initiative.id)
        initiatives_with_progress.append(
            InitiativeProgressResponse(
                initiative=_initiative_to_response(initiative),
                progress=progress,
            )
        )

    return InitiativeListResponse(
        initiatives=initiatives_with_progress,
        total=len(initiatives),
    )


@router.get("/{initiative_id}", response_model=InitiativeWithTasksResponse)
def get_initiative(
    initiative_id: int,
    service: Annotated[InitiativeService, Depends(get_initiative_service)],
    include_completed_tasks: bool = Query(default=True, description="Include completed tasks"),
) -> InitiativeWithTasksResponse:
    """Get a specific initiative by ID with linked tasks."""
    initiative = service.get_initiative(initiative_id)
    if not initiative:
        raise HTTPException(status_code=404, detail="Initiative not found")

    tasks = service.get_tasks_for_initiative(
        initiative_id, include_completed=include_completed_tasks
    )
    progress = service.get_initiative_progress(initiative_id)

    return InitiativeWithTasksResponse(
        id=initiative.id,
        title=initiative.title,
        description=initiative.description,
        priority=initiative.priority,
        target_date=initiative.target_date,
        status=initiative.status,
        created_at=initiative.created_at,
        updated_at=initiative.updated_at,
        tasks=[_task_to_response(t) for t in tasks],
        progress=progress,
    )


@router.post("", response_model=InitiativeResponse, status_code=201)
def create_initiative(
    initiative_data: InitiativeCreate,
    service: Annotated[InitiativeService, Depends(get_initiative_service)],
) -> InitiativeResponse:
    """Create a new initiative."""
    initiative = service.create_initiative(
        title=initiative_data.title,
        description=initiative_data.description,
        priority=initiative_data.priority,
        target_date=initiative_data.target_date,
    )
    return _initiative_to_response(initiative)


@router.put("/{initiative_id}", response_model=InitiativeResponse)
def update_initiative(
    initiative_id: int,
    initiative_data: InitiativeUpdate,
    service: Annotated[InitiativeService, Depends(get_initiative_service)],
) -> InitiativeResponse:
    """Update an existing initiative."""
    initiative = service.get_initiative(initiative_id)
    if not initiative:
        raise HTTPException(status_code=404, detail="Initiative not found")

    initiative = service.update_initiative(
        initiative,
        title=initiative_data.title,
        description=initiative_data.description,
        status=initiative_data.status,
        priority=initiative_data.priority,
        target_date=initiative_data.target_date,
    )
    return _initiative_to_response(initiative)


@router.delete("/{initiative_id}", status_code=204)
def delete_initiative(
    initiative_id: int,
    service: Annotated[InitiativeService, Depends(get_initiative_service)],
) -> None:
    """Delete an initiative.

    Note: Tasks linked to this initiative will be unlinked (initiative_id set to NULL).
    """
    initiative = service.get_initiative(initiative_id)
    if not initiative:
        raise HTTPException(status_code=404, detail="Initiative not found")
    service.delete_initiative(initiative)


@router.post("/{initiative_id}/complete", response_model=InitiativeResponse)
def complete_initiative(
    initiative_id: int,
    service: Annotated[InitiativeService, Depends(get_initiative_service)],
) -> InitiativeResponse:
    """Mark an initiative as completed."""
    initiative = service.get_initiative(initiative_id)
    if not initiative:
        raise HTTPException(status_code=404, detail="Initiative not found")

    initiative = service.update_initiative(initiative, status=InitiativeStatus.COMPLETED)
    return _initiative_to_response(initiative)


def _initiative_to_response(initiative: Initiative) -> InitiativeResponse:
    """Convert Initiative model to response schema."""
    return InitiativeResponse(
        id=initiative.id,
        title=initiative.title,
        description=initiative.description,
        priority=initiative.priority,
        target_date=initiative.target_date,
        status=initiative.status,
        created_at=initiative.created_at,
        updated_at=initiative.updated_at,
    )


def _task_to_response(task) -> TaskResponse:
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
        initiative_id=task.initiative_id,
        initiative_title=task.initiative.title if task.initiative else None,
    )
