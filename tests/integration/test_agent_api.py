"""Integration tests for agent API endpoints."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src import __version__
from src.api.routes import agent_router, tasks_router
from src.api.schemas import HealthResponse
from src.models.database import Base, get_db, reset_engine
from src.services.llm_service import ProductivityRecommendation
from src.utils.config import Config, reset_config


@pytest.fixture(scope="function")
def agent_test_client(test_db_engine, monkeypatch):
    """Create a test client with agent routes."""
    from src.agent.core import reset_agent
    
    # Reset global state
    reset_config()
    reset_engine()
    reset_agent()
    
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
    app.include_router(agent_router, prefix="/api")
    
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
    test_config = Config(
        database={"url": "sqlite:///:memory:", "echo": False},
        llm={"api_key": "test-key", "model": "gpt-4"},
        agent={"autonomy_level": "suggest"},
    )
    
    def override_get_config():
        return test_config
    
    monkeypatch.setattr("src.utils.config.get_config", override_get_config)
    monkeypatch.setattr("src.api.routes.agent.get_config", override_get_config)
    
    with TestClient(app) as test_client:
        yield test_client
    
    transaction.rollback()
    connection.close()
    reset_agent()


class TestAgentStatusEndpoint:
    """Tests for GET /api/agent/status."""
    
    def test_get_status(self, agent_test_client):
        """Test getting agent status."""
        response = agent_test_client.get("/api/agent/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "is_running" in data
        assert "autonomy_level" in data
        assert "integrations" in data
        assert data["is_running"] is False

    def test_status_includes_session_stats(self, agent_test_client):
        """Test status includes session statistics."""
        response = agent_test_client.get("/api/agent/status")
        data = response.json()
        
        assert "session_stats" in data
        assert "tasks_created" in data["session_stats"]
        assert "items_processed" in data["session_stats"]
        assert "errors" in data["session_stats"]


class TestAgentAutonomyEndpoint:
    """Tests for PUT /api/agent/autonomy."""
    
    def test_set_autonomy_level(self, agent_test_client):
        """Test setting autonomy level."""
        response = agent_test_client.put(
            "/api/agent/autonomy",
            json={"autonomy_level": "auto"},
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["autonomy_level"] == "auto"
    
    def test_set_invalid_autonomy_level(self, agent_test_client):
        """Test setting invalid autonomy level."""
        response = agent_test_client.put(
            "/api/agent/autonomy",
            json={"autonomy_level": "invalid"},
        )
        assert response.status_code == 400
        assert "Invalid autonomy level" in response.json()["detail"]
    
    def test_set_autonomy_missing_level(self, agent_test_client):
        """Test setting autonomy without level."""
        response = agent_test_client.put(
            "/api/agent/autonomy",
            json={},
        )
        assert response.status_code == 400


class TestAgentSuggestionsEndpoint:
    """Tests for GET/DELETE /api/agent/suggestions."""
    
    def test_get_suggestions_empty(self, agent_test_client):
        """Test getting empty suggestions."""
        response = agent_test_client.get("/api/agent/suggestions")
        assert response.status_code == 200
        
        data = response.json()
        assert data["suggestions"] == []
        assert data["count"] == 0
    
    def test_clear_suggestions(self, agent_test_client):
        """Test clearing suggestions."""
        response = agent_test_client.delete("/api/agent/suggestions")
        assert response.status_code == 200
        
        data = response.json()
        assert "cleared" in data


class TestAgentLogsEndpoint:
    """Tests for GET /api/agent/logs."""
    
    def test_get_logs_empty(self, agent_test_client):
        """Test getting logs when empty."""
        response = agent_test_client.get("/api/agent/logs")
        assert response.status_code == 200
        
        data = response.json()
        assert "logs" in data
        assert "total" in data
        assert data["logs"] == []
    
    def test_get_logs_with_filters(self, agent_test_client):
        """Test getting logs with filters."""
        response = agent_test_client.get(
            "/api/agent/logs",
            params={"level": "info", "hours": 48, "limit": 10},
        )
        assert response.status_code == 200
    
    def test_delete_old_logs(self, agent_test_client):
        """Test deleting old logs."""
        response = agent_test_client.delete(
            "/api/agent/logs",
            params={"days": 30},
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "deleted" in data


class TestAgentActivityEndpoint:
    """Tests for GET /api/agent/activity."""
    
    def test_get_activity_summary(self, agent_test_client):
        """Test getting activity summary."""
        response = agent_test_client.get("/api/agent/activity")
        assert response.status_code == 200
        
        data = response.json()
        assert "period_hours" in data
        assert "tasks_created" in data
        assert "polls_completed" in data
        assert "llm_usage" in data
    
    def test_get_activity_custom_hours(self, agent_test_client):
        """Test getting activity with custom hours."""
        response = agent_test_client.get(
            "/api/agent/activity",
            params={"hours": 48},
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["period_hours"] == 48


class TestRecommendationsEndpoint:
    """Tests for GET /api/agent/recommendations."""
    
    def test_get_recommendations_mocked(self, agent_test_client, monkeypatch):
        """Test getting recommendations with mocked LLM."""
        mock_recommendations = [
            ProductivityRecommendation(
                title="Focus on priorities",
                description="You have overdue tasks",
                category="focus",
                priority="high",
                actionable_steps=["Block time", "Start with oldest"],
            )
        ]
        
        async def mock_generate(*args, **kwargs):
            return mock_recommendations
        
        with patch("src.services.recommendation_service.LLMService") as mock_llm:
            mock_llm.return_value.generate_recommendations = AsyncMock(return_value=mock_recommendations)
            
            response = agent_test_client.get("/api/agent/recommendations")
        
        assert response.status_code == 200
        data = response.json()
        assert "recommendations" in data


class TestQuickWinsEndpoint:
    """Tests for GET /api/agent/quick-wins."""
    
    def test_get_quick_wins_empty(self, agent_test_client):
        """Test getting quick wins when no tasks."""
        response = agent_test_client.get("/api/agent/quick-wins")
        assert response.status_code == 200
        
        data = response.json()
        assert "quick_wins" in data
        assert data["quick_wins"] == []


class TestOverduePlanEndpoint:
    """Tests for GET /api/agent/overdue-plan."""
    
    def test_get_overdue_plan_no_overdue(self, agent_test_client):
        """Test overdue plan when no overdue tasks."""
        response = agent_test_client.get("/api/agent/overdue-plan")
        assert response.status_code == 200
        
        data = response.json()
        assert data["overdue_count"] == 0
        assert "No overdue" in data["message"]


class TestDailySummaryEndpoint:
    """Tests for GET /api/agent/summary."""
    
    def test_get_daily_summary_mocked(self, agent_test_client):
        """Test getting daily summary."""
        with patch("src.services.recommendation_service.LLMService") as mock_llm:
            mock_llm.return_value.generate_recommendations = AsyncMock(return_value=[])
            
            response = agent_test_client.get("/api/agent/summary")
        
        assert response.status_code == 200
        
        data = response.json()
        assert "date" in data
        assert "statistics" in data
        assert "due_today" in data
        assert "top_priorities" in data


class TestAgentStartStopEndpoints:
    """Tests for POST /api/agent/start and /api/agent/stop."""
    
    def test_stop_when_not_running(self, agent_test_client):
        """Test stopping agent when not running."""
        response = agent_test_client.post("/api/agent/stop")
        assert response.status_code == 400
        assert "not running" in response.json()["detail"]


class TestPollEndpoint:
    """Tests for POST /api/agent/poll."""
    
    def test_trigger_poll(self, agent_test_client):
        """Test triggering a poll."""
        with patch("src.agent.core.AutonomousAgent.poll_now", new_callable=AsyncMock) as mock_poll:
            mock_poll.return_value = []
            
            response = agent_test_client.post("/api/agent/poll")
        
        assert response.status_code == 200
        data = response.json()
        assert data["poll_completed"] is True
        assert "results" in data
