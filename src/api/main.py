"""Main FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from src import __version__
from src.api.dependencies import get_db_session
from src.api.routes import agent_router, initiatives_router, status_router, tasks_router, voice_router
from src.api.schemas import HealthResponse
from src.models import init_db
from src.services.agent_log_service import AgentLogService


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    init_db()
    yield
    # Shutdown (cleanup if needed)


app = FastAPI(
    title="Personal Assistant API",
    description="A personal assistant agent that helps track tasks, monitors data sources, and provides productivity recommendations.",
    version=__version__,
    lifespan=lifespan,
)

# Include routers
app.include_router(tasks_router, prefix="/api")
app.include_router(initiatives_router, prefix="/api")
app.include_router(status_router, prefix="/api")
app.include_router(agent_router, prefix="/api")
app.include_router(voice_router, prefix="/api")


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health_check() -> HealthResponse:
    """Basic health check endpoint.

    Returns 200 OK if the service is running.
    Does not check dependencies.
    """
    return HealthResponse(
        status="healthy",
        version=__version__,
        database="unknown",
    )


@app.get("/health/ready", response_model=HealthResponse, tags=["health"])
def readiness_check(db: Session = Depends(get_db_session)) -> HealthResponse:
    """Readiness check endpoint.

    Verifies:
    - Database connectivity
    - Configuration loaded

    Returns 200 if ready to serve traffic, 503 otherwise.
    """
    try:
        # Test database connection
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Database connection failed: {str(e)}"
        )

    return HealthResponse(
        status="ready",
        version=__version__,
        database=db_status,
    )


@app.get("/health/agent", tags=["health"])
def agent_health_check(db: Session = Depends(get_db_session)) -> dict:
    """Agent health check endpoint.

    Returns agent status:
    - Whether agent is configured to run
    - Last poll time
    - Agent activity status

    Returns 200 with agent details.
    """
    agent_log_service = AgentLogService(db)

    # Check if agent has ever polled
    last_log = agent_log_service.get_recent_logs(limit=1)
    last_poll = last_log[0].timestamp if last_log else None

    return {
        "status": "running" if last_poll else "not_started",
        "last_poll": last_poll.isoformat() if last_poll else None,
        "version": __version__,
    }


@app.get("/api/status", tags=["status"])
def get_status():
    """Get agent status."""
    # TODO: Implement actual status tracking
    return {
        "status": "running",
        "last_poll": None,
        "tasks_pending": 0,
        "notifications_unread": 0,
    }
