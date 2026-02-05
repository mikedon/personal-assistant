"""Integration tests for initiatives API endpoints."""

from datetime import datetime, timedelta

import pytest

from src.models.initiative import Initiative, InitiativePriority, InitiativeStatus
from src.models.task import Task, TaskStatus


@pytest.fixture
def sample_initiative_data():
    """Sample initiative data for testing."""
    return {
        "title": "Q1 Product Launch",
        "description": "Launch new product features in Q1",
        "priority": "high",
    }


@pytest.fixture
def initiatives_client(test_db_engine, test_config, monkeypatch):
    """Create a test client with initiatives routes."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from src import __version__
    from src.api.routes import initiatives_router, tasks_router
    from src.api.schemas import HealthResponse
    from src.models.database import get_db, reset_engine
    from src.utils.config import reset_config

    # Reset global state
    reset_config()
    reset_engine()

    # Create a fresh connection for this test
    connection = test_db_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)

    # Create a test app
    app = FastAPI(
        title="Personal Assistant API (Test)",
        version=__version__,
    )
    app.include_router(tasks_router, prefix="/api")
    app.include_router(initiatives_router, prefix="/api")

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health_check() -> HealthResponse:
        return HealthResponse(
            status="healthy",
            version=__version__,
            database="connected",
        )

    # Override get_db dependency
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


def test_create_initiative(initiatives_client, sample_initiative_data):
    """Test creating an initiative via API."""
    response = initiatives_client.post("/api/initiatives", json=sample_initiative_data)
    assert response.status_code == 201

    data = response.json()
    assert data["title"] == sample_initiative_data["title"]
    assert data["description"] == sample_initiative_data["description"]
    assert data["priority"] == sample_initiative_data["priority"]
    assert data["status"] == "active"
    assert "id" in data


def test_create_initiative_with_target_date(initiatives_client):
    """Test creating initiative with target date."""
    target = (datetime.now() + timedelta(days=90)).isoformat()
    data = {
        "title": "Quarterly Goals",
        "target_date": target,
    }

    response = initiatives_client.post("/api/initiatives", json=data)
    assert response.status_code == 201

    result = response.json()
    assert result["target_date"] is not None


def test_get_initiative(initiatives_client, sample_initiative_data):
    """Test retrieving an initiative by ID."""
    # Create initiative first
    create_response = initiatives_client.post("/api/initiatives", json=sample_initiative_data)
    initiative_id = create_response.json()["id"]

    # Get the initiative
    response = initiatives_client.get(f"/api/initiatives/{initiative_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == initiative_id
    assert data["title"] == sample_initiative_data["title"]
    assert "tasks" in data  # Should include tasks list
    assert "progress" in data  # Should include progress


def test_get_initiative_not_found(initiatives_client):
    """Test getting non-existent initiative."""
    response = initiatives_client.get("/api/initiatives/9999")
    assert response.status_code == 404


def test_list_initiatives(initiatives_client, sample_initiative_data):
    """Test listing all initiatives."""
    # Create multiple initiatives
    initiatives_client.post("/api/initiatives", json=sample_initiative_data)
    initiatives_client.post("/api/initiatives", json={
        **sample_initiative_data,
        "title": "Second Initiative"
    })

    response = initiatives_client.get("/api/initiatives")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] >= 2
    assert len(data["initiatives"]) >= 2

    # Each initiative should have progress info
    for initiative_data in data["initiatives"]:
        assert "initiative" in initiative_data
        assert "progress" in initiative_data


def test_list_initiatives_exclude_completed(initiatives_client, sample_initiative_data):
    """Test listing initiatives excludes completed by default."""
    # Create active initiative
    initiatives_client.post("/api/initiatives", json=sample_initiative_data)

    # Create and complete another
    response = initiatives_client.post("/api/initiatives", json={
        **sample_initiative_data,
        "title": "Completed Initiative"
    })
    initiative_id = response.json()["id"]
    initiatives_client.post(f"/api/initiatives/{initiative_id}/complete")

    # List without completed
    response = initiatives_client.get("/api/initiatives")
    data = response.json()

    # Should only have the active one
    assert data["total"] == 1


def test_list_initiatives_include_completed(initiatives_client, sample_initiative_data):
    """Test listing initiatives with completed included."""
    # Create and complete an initiative
    response = initiatives_client.post("/api/initiatives", json=sample_initiative_data)
    initiative_id = response.json()["id"]
    initiatives_client.post(f"/api/initiatives/{initiative_id}/complete")

    # List with completed
    response = initiatives_client.get("/api/initiatives?include_completed=true")
    data = response.json()

    assert data["total"] >= 1


def test_get_active_initiatives(initiatives_client, sample_initiative_data):
    """Test getting only active initiatives."""
    # Create active initiative
    initiatives_client.post("/api/initiatives", json=sample_initiative_data)

    response = initiatives_client.get("/api/initiatives/active")
    assert response.status_code == 200

    data = response.json()
    for item in data["initiatives"]:
        assert item["initiative"]["status"] == "active"


def test_update_initiative(initiatives_client, sample_initiative_data):
    """Test updating an initiative."""
    # Create initiative
    create_response = initiatives_client.post("/api/initiatives", json=sample_initiative_data)
    initiative_id = create_response.json()["id"]

    # Update it
    update_data = {
        "title": "Updated Title",
        "priority": "low",
        "status": "paused",
    }
    response = initiatives_client.put(f"/api/initiatives/{initiative_id}", json=update_data)
    assert response.status_code == 200

    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["priority"] == "low"
    assert data["status"] == "paused"


def test_delete_initiative(initiatives_client, sample_initiative_data):
    """Test deleting an initiative."""
    # Create initiative
    create_response = initiatives_client.post("/api/initiatives", json=sample_initiative_data)
    initiative_id = create_response.json()["id"]

    # Delete it
    response = initiatives_client.delete(f"/api/initiatives/{initiative_id}")
    assert response.status_code == 204

    # Verify it's gone
    get_response = initiatives_client.get(f"/api/initiatives/{initiative_id}")
    assert get_response.status_code == 404


def test_complete_initiative(initiatives_client, sample_initiative_data):
    """Test marking an initiative as completed."""
    # Create initiative
    create_response = initiatives_client.post("/api/initiatives", json=sample_initiative_data)
    initiative_id = create_response.json()["id"]

    # Complete it
    response = initiatives_client.post(f"/api/initiatives/{initiative_id}/complete")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "completed"


def test_create_task_with_initiative(initiatives_client, sample_initiative_data):
    """Test creating a task linked to an initiative."""
    # Create initiative
    init_response = initiatives_client.post("/api/initiatives", json=sample_initiative_data)
    initiative_id = init_response.json()["id"]

    # Create task with initiative
    task_data = {
        "title": "Task for initiative",
        "priority": "high",
        "initiative_id": initiative_id,
    }
    task_response = initiatives_client.post("/api/tasks", json=task_data)
    assert task_response.status_code == 201

    task = task_response.json()
    assert task["initiative_id"] == initiative_id
    assert task["initiative_title"] == sample_initiative_data["title"]


def test_initiative_progress_with_tasks(initiatives_client, sample_initiative_data):
    """Test initiative progress calculation with linked tasks."""
    # Create initiative
    init_response = initiatives_client.post("/api/initiatives", json=sample_initiative_data)
    initiative_id = init_response.json()["id"]

    # Create tasks linked to initiative
    for i in range(3):
        initiatives_client.post("/api/tasks", json={
            "title": f"Task {i}",
            "initiative_id": initiative_id,
        })

    # Complete one task
    tasks_response = initiatives_client.get(f"/api/initiatives/{initiative_id}")
    task_id = tasks_response.json()["tasks"][0]["id"]
    initiatives_client.put(f"/api/tasks/{task_id}", json={"status": "completed"})

    # Check progress
    response = initiatives_client.get(f"/api/initiatives/{initiative_id}")
    data = response.json()

    assert data["progress"]["total_tasks"] == 3
    assert data["progress"]["completed_tasks"] == 1
    assert 30 < data["progress"]["progress_percent"] < 40  # ~33.3%


def test_filter_initiatives_by_priority(initiatives_client):
    """Test filtering initiatives by priority."""
    initiatives_client.post("/api/initiatives", json={"title": "High Pri", "priority": "high"})
    initiatives_client.post("/api/initiatives", json={"title": "Low Pri", "priority": "low"})

    # Filter by high priority
    response = initiatives_client.get("/api/initiatives?priority=high")
    assert response.status_code == 200

    data = response.json()
    for item in data["initiatives"]:
        assert item["initiative"]["priority"] == "high"
