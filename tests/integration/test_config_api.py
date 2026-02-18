"""Integration tests for configuration API endpoints."""

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.utils.config import reset_config


@pytest.fixture
def client():
    """Create test client for the API."""
    app = create_app()
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_config_fixture():
    """Reset configuration before and after each test."""
    reset_config()
    yield
    reset_config()


def test_get_config(client):
    """Test GET /api/config returns current configuration."""
    response = client.get("/api/config")
    assert response.status_code == 200
    
    data = response.json()
    assert "agent" in data
    assert "notifications" in data
    assert "llm" in data
    assert "database" in data
    assert "google" in data
    assert "slack" in data


def test_get_config_has_agent_section(client):
    """Test GET /api/config returns agent configuration."""
    response = client.get("/api/config")
    assert response.status_code == 200
    
    data = response.json()
    agent = data.get("agent", {})
    assert "autonomy_level" in agent
    assert agent["autonomy_level"] in ["suggest", "auto_low", "auto", "full"]
    assert "poll_interval_minutes" in agent
    assert isinstance(agent["poll_interval_minutes"], int)


def test_get_config_has_notifications_section(client):
    """Test GET /api/config returns notification configuration."""
    response = client.get("/api/config")
    assert response.status_code == 200
    
    data = response.json()
    notif = data.get("notifications", {})
    assert "enabled" in notif
    assert isinstance(notif["enabled"], bool)
    assert "sound" in notif
    assert isinstance(notif["sound"], bool)
    assert "due_soon_hours" in notif
    assert isinstance(notif["due_soon_hours"], int)


def test_get_config_has_llm_section(client):
    """Test GET /api/config returns LLM configuration."""
    response = client.get("/api/config")
    assert response.status_code == 200
    
    data = response.json()
    llm = data.get("llm", {})
    assert "model" in llm
    assert "api_key" in llm


def test_put_config_update_autonomy_level(client):
    """Test PUT /api/config updates autonomy level."""
    # First get current config
    get_response = client.get("/api/config")
    config = get_response.json()
    
    # Update autonomy level
    config["agent"]["autonomy_level"] = "full"
    put_response = client.put("/api/config", json=config)
    assert put_response.status_code == 200
    
    # Verify update
    updated_response = client.get("/api/config")
    updated_config = updated_response.json()
    assert updated_config["agent"]["autonomy_level"] == "full"


def test_put_config_update_notifications(client):
    """Test PUT /api/config updates notification settings."""
    # First get current config
    get_response = client.get("/api/config")
    config = get_response.json()
    
    # Update notifications
    config["notifications"]["enabled"] = False
    config["notifications"]["due_soon_hours"] = 12
    put_response = client.put("/api/config", json=config)
    assert put_response.status_code == 200
    
    # Verify update
    updated_response = client.get("/api/config")
    updated_config = updated_response.json()
    assert updated_config["notifications"]["enabled"] is False
    assert updated_config["notifications"]["due_soon_hours"] == 12


def test_put_config_update_llm_model(client):
    """Test PUT /api/config updates LLM model."""
    # First get current config
    get_response = client.get("/api/config")
    config = get_response.json()
    
    # Update model
    config["llm"]["model"] = "gpt-4-turbo"
    put_response = client.put("/api/config", json=config)
    assert put_response.status_code == 200
    
    # Verify update
    updated_response = client.get("/api/config")
    updated_config = updated_response.json()
    assert updated_config["llm"]["model"] == "gpt-4-turbo"


def test_put_config_rejects_empty_api_key(client):
    """Test PUT /api/config rejects clearing a non-empty API key."""
    # First get current config
    get_response = client.get("/api/config")
    config = get_response.json()
    
    # Set a non-empty API key first
    config["llm"]["api_key"] = "test-key-12345"
    put_response = client.put("/api/config", json=config)
    assert put_response.status_code == 200
    
    # Now try to clear it
    config["llm"]["api_key"] = ""
    put_response = client.put("/api/config", json=config)
    assert put_response.status_code == 422  # Validation error
    
    # Verify original value is unchanged
    updated_response = client.get("/api/config")
    updated_config = updated_response.json()
    assert updated_config["llm"]["api_key"] == "test-key-12345"


def test_put_config_rejects_invalid_autonomy_level(client):
    """Test PUT /api/config rejects invalid autonomy level."""
    # First get current config
    get_response = client.get("/api/config")
    config = get_response.json()
    
    # Try to set invalid autonomy level
    config["agent"]["autonomy_level"] = "invalid_level"
    put_response = client.put("/api/config", json=config)
    assert put_response.status_code == 422  # Validation error


def test_put_config_partial_update(client):
    """Test PUT /api/config allows partial updates."""
    # First get current config
    get_response = client.get("/api/config")
    config = get_response.json()
    original_model = config["llm"]["model"]
    
    # Update only notifications
    partial_update = {"notifications": config["notifications"]}
    partial_update["notifications"]["due_soon_hours"] = 24
    put_response = client.put("/api/config", json=partial_update)
    assert put_response.status_code == 200
    
    # Verify notification updated but model unchanged
    updated_response = client.get("/api/config")
    updated_config = updated_response.json()
    assert updated_config["notifications"]["due_soon_hours"] == 24
    assert updated_config["llm"]["model"] == original_model


def test_put_config_persists_to_yaml(client, tmp_path):
    """Test PUT /api/config persists changes to YAML file."""
    # Get original config
    get_response = client.get("/api/config")
    config = get_response.json()
    
    # Update a value
    new_value = "full"
    config["agent"]["autonomy_level"] = new_value
    client.put("/api/config", json=config)
    
    # In a new client session, verify the change persists
    new_response = client.get("/api/config")
    new_config = new_response.json()
    assert new_config["agent"]["autonomy_level"] == new_value


def test_put_config_updates_integrations(client):
    """Test PUT /api/config updates integration settings."""
    # Get current config
    get_response = client.get("/api/config")
    config = get_response.json()
    
    # Update Slack integration
    config["slack"]["enabled"] = True
    config["slack"]["bot_token"] = "xoxb-test-token"
    put_response = client.put("/api/config", json=config)
    assert put_response.status_code == 200
    
    # Verify update
    updated_response = client.get("/api/config")
    updated_config = updated_response.json()
    assert updated_config["slack"]["enabled"] is True
    assert updated_config["slack"]["bot_token"] == "xoxb-test-token"


def test_get_config_multiple_calls_consistent(client):
    """Test GET /api/config returns consistent data across calls."""
    response1 = client.get("/api/config")
    response2 = client.get("/api/config")
    
    assert response1.json() == response2.json()


def test_put_config_validates_poll_interval(client):
    """Test PUT /api/config validates poll interval."""
    # Get current config
    get_response = client.get("/api/config")
    config = get_response.json()
    
    # Set reasonable poll interval
    config["agent"]["poll_interval_minutes"] = 30
    put_response = client.put("/api/config", json=config)
    assert put_response.status_code == 200
    
    # Verify update
    updated_response = client.get("/api/config")
    updated_config = updated_response.json()
    assert updated_config["agent"]["poll_interval_minutes"] == 30
