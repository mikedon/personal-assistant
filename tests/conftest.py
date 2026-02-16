"""Pytest configuration and fixtures."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models.database import Base, get_db, reset_engine
from src.utils.config import Config, reset_config


@pytest.fixture(scope="function")
def test_config():
    """Create a test configuration."""
    config = Config(
        database={"url": "sqlite:///:memory:", "echo": False},
        llm={"api_key": "test-key", "model": "gpt-4"},
    )
    return config


@pytest.fixture(scope="function")
def test_db_engine():
    """Create an in-memory SQLite engine for testing.
    
    Uses StaticPool to ensure the same connection is used throughout,
    which is required for in-memory SQLite databases.
    """
    # Import models to ensure they're registered with Base
    from src.models import agent_log, initiative, notification, pending_suggestion, task  # noqa: F401

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def test_db_session(test_db_engine):
    """Create a database session for testing."""
    connection = test_db_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = SessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(test_db_engine, test_config, monkeypatch):
    """Create a test client with dependency overrides."""
    from src import __version__
    from src.api.routes import tasks_router
    from src.api.schemas import HealthResponse
    from src.services.agent_log_service import AgentLogService
    from fastapi import Depends, HTTPException
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    # Reset global state
    reset_config()
    reset_engine()

    # Create a fresh connection for this test
    connection = test_db_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)

    # Create a test app without lifespan
    app = FastAPI(
        title="Personal Assistant API (Test)",
        version=__version__,
    )
    app.include_router(tasks_router, prefix="/api")

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health_check() -> HealthResponse:
        return HealthResponse(
            status="healthy",
            version=__version__,
            database="connected",
        )

    @app.get("/health/ready", response_model=HealthResponse, tags=["health"])
    def readiness_check(db: Session = Depends(get_db)) -> HealthResponse:
        """Readiness check endpoint for testing."""
        try:
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
    def agent_health_check(db: Session = Depends(get_db)) -> dict:
        """Agent health check endpoint for testing."""
        agent_log_service = AgentLogService(db)
        last_log = agent_log_service.get_recent_logs(limit=1)
        last_poll = last_log[0].timestamp if last_log else None
        return {
            "status": "running" if last_poll else "not_started",
            "last_poll": last_poll.isoformat() if last_poll else None,
            "version": __version__,
        }

    @app.get("/api/status", tags=["status"])
    def get_status():
        return {
            "status": "running",
            "last_poll": None,
            "tasks_pending": 0,
            "notifications_unread": 0,
        }

    # Override get_db dependency to use the test session
    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    # Override get_config
    def override_get_config():
        return test_config

    monkeypatch.setattr("src.models.database.get_config", override_get_config)
    monkeypatch.setattr("src.utils.config.get_config", override_get_config)

    with TestClient(app) as test_client:
        yield test_client

    transaction.rollback()
    connection.close()


@pytest.fixture
def sample_task_data():
    """Sample task data for testing."""
    return {
        "title": "Test Task",
        "description": "This is a test task",
        "priority": "high",
        "tags": ["test", "important"],
    }
