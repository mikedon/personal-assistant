"""API routes."""

from src.api.routes.agent import router as agent_router
from src.api.routes.initiatives import router as initiatives_router
from src.api.routes.status import router as status_router
from src.api.routes.tasks import router as tasks_router
from src.api.routes.voice import router as voice_router

__all__ = ["agent_router", "initiatives_router", "status_router", "tasks_router", "voice_router"]
