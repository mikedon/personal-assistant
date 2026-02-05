"""Main FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src import __version__
from src.api.routes import agent_router, initiatives_router, tasks_router, voice_router
from src.api.schemas import HealthResponse
from src.models import init_db


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
app.include_router(agent_router, prefix="/api")
app.include_router(voice_router, prefix="/api")


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version=__version__,
        database="connected",
    )


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
