"""Agent API routes for autonomous agent control and monitoring."""

from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agent.core import AutonomyLevel, get_agent, reset_agent
from src.models import get_db
from src.models.agent_log import AgentAction, LogLevel
from src.services.agent_log_service import AgentLogService
from src.services.recommendation_service import RecommendationService
from src.utils.config import get_config

router = APIRouter(prefix="/agent", tags=["agent"])


# --- Schemas ---


class AgentStatusResponse(BaseModel):
    """Agent status response."""

    is_running: bool
    autonomy_level: str
    last_poll: datetime | None
    last_recommendation: datetime | None
    started_at: datetime | None
    session_stats: dict[str, int]
    pending_suggestions: int
    pending_recommendations: int
    integrations: dict[str, bool]


class AgentControlRequest(BaseModel):
    """Request to control agent."""

    autonomy_level: str | None = Field(
        default=None,
        description="Autonomy level: suggest, auto_low, auto, full",
    )


class RecommendationResponse(BaseModel):
    """Productivity recommendation."""

    title: str
    description: str
    category: str
    priority: str
    actionable_steps: list[str] | None = None


class RecommendationsResponse(BaseModel):
    """List of recommendations."""

    recommendations: list[RecommendationResponse]
    generated_at: datetime | None = None
    from_cache: bool = False


class DailySummaryResponse(BaseModel):
    """Daily summary response."""

    date: str
    statistics: dict[str, int]
    due_today: list[dict[str, Any]]
    coming_up: list[dict[str, Any]]
    top_priorities: list[dict[str, Any]]
    overdue_count: int
    recommendations: list[dict[str, Any]]


class QuickWinsResponse(BaseModel):
    """Quick wins response."""

    quick_wins: list[dict[str, Any]]


class OverdueActionPlanResponse(BaseModel):
    """Overdue action plan response."""

    overdue_count: int
    message: str
    tasks: list[dict[str, Any]]
    suggested_actions: list[str]


class AgentLogResponse(BaseModel):
    """Agent log entry."""

    id: int
    level: str
    action: str | None
    message: str
    details: str | None
    tokens_used: int | None
    model_used: str | None
    reference_type: str | None
    reference_id: str | None
    created_at: datetime


class AgentLogsResponse(BaseModel):
    """List of agent logs."""

    logs: list[AgentLogResponse]
    total: int


class ActivitySummaryResponse(BaseModel):
    """Agent activity summary."""

    period_hours: int
    tasks_created: int
    polls_completed: int
    by_action: dict[str, int]
    by_level: dict[str, int]
    llm_usage: dict[str, Any]
    errors: int
    warnings: int


class SuggestionResponse(BaseModel):
    """Task suggestion from LLM."""

    title: str
    description: str | None
    priority: str
    due_date: datetime | None
    tags: list[str] | None
    confidence: float


class SuggestionsResponse(BaseModel):
    """List of pending task suggestions."""

    suggestions: list[SuggestionResponse]
    count: int


# --- Dependencies ---


def get_agent_log_service(db: Session = Depends(get_db)) -> AgentLogService:
    """Dependency to get agent log service."""
    return AgentLogService(db)


def get_recommendation_service(db: Session = Depends(get_db)) -> RecommendationService:
    """Dependency to get recommendation service."""
    config = get_config()
    return RecommendationService(db, config.llm)


# --- Routes ---


@router.get("/status", response_model=AgentStatusResponse)
def get_agent_status() -> AgentStatusResponse:
    """Get current agent status."""
    agent = get_agent()
    status = agent.get_status()
    return AgentStatusResponse(**status)


@router.post("/start", response_model=AgentStatusResponse)
async def start_agent(
    background_tasks: BackgroundTasks,
    request: AgentControlRequest | None = None,
) -> AgentStatusResponse:
    """Start the autonomous agent.

    Optionally set the autonomy level when starting.
    """
    agent = get_agent()

    if agent.state.is_running:
        raise HTTPException(status_code=400, detail="Agent is already running")

    if request and request.autonomy_level:
        try:
            agent.autonomy_level = AutonomyLevel(request.autonomy_level)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid autonomy level: {request.autonomy_level}. "
                f"Valid values: {[l.value for l in AutonomyLevel]}",
            )

    # Start agent in background
    background_tasks.add_task(agent.start)

    # Return current status (will show is_running=False until start completes)
    return AgentStatusResponse(**agent.get_status())


@router.post("/stop", response_model=AgentStatusResponse)
async def stop_agent() -> AgentStatusResponse:
    """Stop the autonomous agent."""
    agent = get_agent()

    if not agent.state.is_running:
        raise HTTPException(status_code=400, detail="Agent is not running")

    await agent.stop()
    return AgentStatusResponse(**agent.get_status())


@router.post("/poll", response_model=dict)
async def trigger_poll() -> dict:
    """Trigger an immediate poll cycle."""
    agent = get_agent()

    results = await agent.poll_now()

    return {
        "poll_completed": True,
        "results": [
            {
                "integration": r.integration.value,
                "items_found": len(r.items_found),
                "tasks_created": len(r.tasks_created),
                "tasks_suggested": len(r.tasks_suggested),
                "duration_seconds": r.duration_seconds,
                "error": r.error,
            }
            for r in results
        ],
    }


@router.put("/autonomy", response_model=AgentStatusResponse)
def set_autonomy_level(request: AgentControlRequest) -> AgentStatusResponse:
    """Update the agent autonomy level.

    Levels:
    - suggest: Only suggest actions, don't create tasks automatically
    - auto_low: Auto-create tasks with high confidence (>0.8)
    - auto: Auto-create all tasks extracted by LLM
    - full: Auto-create tasks and apply priority suggestions
    """
    if not request.autonomy_level:
        raise HTTPException(status_code=400, detail="autonomy_level is required")

    agent = get_agent()

    try:
        agent.autonomy_level = AutonomyLevel(request.autonomy_level)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid autonomy level: {request.autonomy_level}. "
            f"Valid values: {[l.value for l in AutonomyLevel]}",
        )

    return AgentStatusResponse(**agent.get_status())


# --- Recommendations ---


@router.get("/recommendations", response_model=RecommendationsResponse)
async def get_recommendations(
    service: Annotated[RecommendationService, Depends(get_recommendation_service)],
    force_refresh: bool = Query(default=False, description="Force refresh recommendations"),
) -> RecommendationsResponse:
    """Get productivity recommendations.

    Recommendations are cached for 30 minutes unless force_refresh is True.
    """
    recommendations = await service.generate_recommendations(force_refresh=force_refresh)

    return RecommendationsResponse(
        recommendations=[
            RecommendationResponse(
                title=r.title,
                description=r.description,
                category=r.category,
                priority=r.priority,
                actionable_steps=r.actionable_steps,
            )
            for r in recommendations
        ],
        generated_at=service._cache_timestamp,
        from_cache=not force_refresh and service._is_cache_valid(30),
    )


@router.get("/summary", response_model=DailySummaryResponse)
async def get_daily_summary(
    service: Annotated[RecommendationService, Depends(get_recommendation_service)],
) -> DailySummaryResponse:
    """Get daily summary with tasks, statistics, and recommendations."""
    summary = await service.get_daily_summary()
    return DailySummaryResponse(**summary)


@router.get("/quick-wins", response_model=QuickWinsResponse)
async def get_quick_wins(
    service: Annotated[RecommendationService, Depends(get_recommendation_service)],
) -> QuickWinsResponse:
    """Get quick win task suggestions.

    Quick wins are tasks that can likely be completed quickly based on heuristics.
    """
    quick_wins = await service.get_quick_wins()
    return QuickWinsResponse(quick_wins=quick_wins)


@router.get("/overdue-plan", response_model=OverdueActionPlanResponse)
async def get_overdue_action_plan(
    service: Annotated[RecommendationService, Depends(get_recommendation_service)],
) -> OverdueActionPlanResponse:
    """Get an action plan for handling overdue tasks."""
    plan = await service.get_overdue_action_plan()
    return OverdueActionPlanResponse(**plan)


# --- Suggestions ---


@router.get("/suggestions", response_model=SuggestionsResponse)
def get_pending_suggestions() -> SuggestionsResponse:
    """Get pending task suggestions (from SUGGEST mode)."""
    agent = get_agent()
    suggestions = agent.get_pending_suggestions()

    return SuggestionsResponse(
        suggestions=[
            SuggestionResponse(
                title=s.title,
                description=s.description,
                priority=s.priority,
                due_date=s.due_date,
                tags=s.tags,
                confidence=s.confidence,
            )
            for s in suggestions
        ],
        count=len(suggestions),
    )


@router.delete("/suggestions")
def clear_pending_suggestions() -> dict:
    """Clear all pending task suggestions."""
    agent = get_agent()
    count = len(agent.get_pending_suggestions())
    agent.clear_pending_suggestions()
    return {"cleared": count}


# --- Logs ---


@router.get("/logs", response_model=AgentLogsResponse)
def get_agent_logs(
    service: Annotated[AgentLogService, Depends(get_agent_log_service)],
    level: LogLevel | None = Query(default=None, description="Filter by log level"),
    action: AgentAction | None = Query(default=None, description="Filter by action type"),
    hours: int = Query(default=24, ge=1, le=168, description="Hours to look back"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AgentLogsResponse:
    """Get agent activity logs."""
    from datetime import UTC, timedelta

    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=hours)

    logs, total = service.get_logs(
        level=level,
        action=action,
        since=since,
        limit=limit,
        offset=offset,
    )

    return AgentLogsResponse(
        logs=[
            AgentLogResponse(
                id=log.id,
                level=log.level.value,
                action=log.action.value if log.action else None,
                message=log.message,
                details=log.details,
                tokens_used=log.tokens_used,
                model_used=log.model_used,
                reference_type=log.reference_type,
                reference_id=log.reference_id,
                created_at=log.created_at,
            )
            for log in logs
        ],
        total=total,
    )


@router.get("/activity", response_model=ActivitySummaryResponse)
def get_activity_summary(
    service: Annotated[AgentLogService, Depends(get_agent_log_service)],
    hours: int = Query(default=24, ge=1, le=168, description="Hours to summarize"),
) -> ActivitySummaryResponse:
    """Get a summary of agent activity."""
    summary = service.get_activity_summary(hours=hours)
    return ActivitySummaryResponse(**summary)


@router.delete("/logs")
def cleanup_old_logs(
    service: Annotated[AgentLogService, Depends(get_agent_log_service)],
    days: int = Query(default=30, ge=1, le=365, description="Keep logs newer than this many days"),
) -> dict:
    """Delete old agent logs."""
    deleted = service.cleanup_old_logs(days=days)
    return {"deleted": deleted}
