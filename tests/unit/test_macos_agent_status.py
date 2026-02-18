"""Unit tests for macOS agent status manager."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.macos.agent_status import AgentLog, AgentStatus, AgentStatusManager, CachedData


class TestCachedData:
    """Tests for CachedData cache validation."""

    def test_cache_valid_within_ttl(self):
        """Test that cache is valid within TTL."""
        from datetime import UTC
        now = datetime.now(UTC).replace(tzinfo=None)
        cache = CachedData("test_data", now, ttl_seconds=30)
        assert cache.is_valid()

    def test_cache_invalid_after_ttl(self):
        """Test that cache is invalid after TTL expires."""
        from datetime import UTC
        old_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=35)
        cache = CachedData("test_data", old_time, ttl_seconds=30)
        assert not cache.is_valid()


class TestAgentStatus:
    """Tests for AgentStatus dataclass."""

    def test_agent_status_creation(self):
        """Test creating AgentStatus instance."""
        status = AgentStatus(
            is_running=True,
            autonomy_level="auto",
            pending_suggestions=5,
            session_stats={"tasks_created": 10},
        )
        assert status.is_running is True
        assert status.autonomy_level == "auto"
        assert status.pending_suggestions == 5
        assert status.session_stats["tasks_created"] == 10

    def test_agent_status_defaults(self):
        """Test AgentStatus defaults."""
        status = AgentStatus(is_running=False, autonomy_level="suggest")
        assert status.last_poll is None
        assert status.pending_suggestions == 0
        assert status.session_stats == {}


class TestAgentLog:
    """Tests for AgentLog dataclass."""

    def test_agent_log_creation(self):
        """Test creating AgentLog instance."""
        log = AgentLog(
            id=1,
            level="INFO",
            action="POLL_COMPLETED",
            message="Poll cycle completed",
            tokens_used=150,
        )
        assert log.id == 1
        assert log.level == "INFO"
        assert log.action == "POLL_COMPLETED"
        assert log.tokens_used == 150


class TestAgentStatusManager:
    """Tests for AgentStatusManager."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create a manager instance with temporary state file."""
        with patch.object(Path, "home", return_value=tmp_path):
            manager = AgentStatusManager(api_url="http://localhost:8000")
            yield manager
            manager.close()

    @patch("src.macos.agent_status.httpx.Client")
    def test_get_status_success(self, mock_client_class, manager):
        """Test successful status retrieval."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "is_running": True,
            "autonomy_level": "auto",
            "last_poll": "2026-02-16T18:00:00",
            "session_stats": {"tasks_created": 5},
            "pending_suggestions": 0,
            "pending_recommendations": 0,
            "integrations": {"gmail": True},
        }
        mock_client.request.return_value = mock_response
        manager.client = mock_client

        status = manager.get_status(use_cache=False)

        assert status.is_running is True
        assert status.autonomy_level == "auto"
        mock_client.request.assert_called_once()

    @patch("src.macos.agent_status.httpx.Client")
    def test_get_status_uses_cache(self, mock_client_class, manager):
        """Test that get_status uses cache when available and valid."""
        from datetime import UTC
        cached_status = AgentStatus(is_running=True, autonomy_level="auto")
        now = datetime.now(UTC).replace(tzinfo=None)
        manager._status_cache = CachedData(cached_status, now, ttl_seconds=30)

        mock_client = MagicMock()
        manager.client = mock_client

        status = manager.get_status(use_cache=True)

        assert status.is_running == cached_status.is_running
        assert status.autonomy_level == cached_status.autonomy_level
        mock_client.request.assert_not_called()

    @patch("src.macos.agent_status.httpx.Client")
    def test_get_logs_success(self, mock_client_class, manager):
        """Test successful logs retrieval."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "logs": [
                {
                    "id": 1,
                    "level": "INFO",
                    "action": "POLL_COMPLETED",
                    "message": "Poll completed",
                    "created_at": "2026-02-16T18:00:00",
                },
            ],
            "total": 1,
        }
        mock_client.request.return_value = mock_response
        manager.client = mock_client

        logs = manager.get_logs(limit=5, hours=24)

        assert len(logs) == 1
        assert logs[0].message == "Poll completed"

    @patch("src.macos.agent_status.httpx.Client")
    def test_retry_logic(self, mock_client_class, manager):
        """Test exponential backoff retry logic."""
        import httpx
        mock_client = MagicMock()
        manager.client = mock_client

        # Simulate first two failures, then success
        failure = httpx.RequestError("Connection failed")
        success_response = MagicMock()
        success_response.json.return_value = {
            "is_running": False,
            "autonomy_level": "unknown",
            "session_stats": {},
            "pending_suggestions": 0,
            "pending_recommendations": 0,
            "integrations": {},
        }

        mock_client.request.side_effect = [failure, failure, success_response]

        status = manager.get_status(use_cache=False)

        assert status.is_running is False
        assert mock_client.request.call_count == 3

    def test_save_and_load_state(self, manager, tmp_path):
        """Test state persistence to disk."""
        status = AgentStatus(
            is_running=True,
            autonomy_level="auto",
            last_poll="2026-02-16T18:00:00",
        )

        manager._save_state(status)
        loaded = manager.load_cached_state()

        assert loaded is not None
        assert loaded["is_running"] is True
        assert loaded["autonomy_level"] == "auto"

    @patch("src.macos.agent_status.httpx.Client")
    def test_api_url_construction(self, mock_client_class, manager):
        """Test that API URL is correctly constructed."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "is_running": False,
            "autonomy_level": "suggest",
            "session_stats": {},
            "pending_suggestions": 0,
            "pending_recommendations": 0,
            "integrations": {},
        }
        mock_client.request.return_value = mock_response
        manager.client = mock_client

        manager.get_status(use_cache=False)

        # Check that the URL was constructed correctly
        call_args = mock_client.request.call_args
        assert "/api/agent/status" in call_args[0][1]

    @patch("src.macos.agent_status.httpx.Client")
    def test_graceful_degradation_on_api_error(self, mock_client_class, manager):
        """Test that manager returns default status on API error."""
        mock_client = MagicMock()
        mock_client.request.side_effect = Exception("API unreachable")
        manager.client = mock_client

        # Should not raise, should return default status
        status = manager.get_status(use_cache=False)

        assert status.is_running is False
        assert status.autonomy_level == "unknown"

    def test_client_cleanup(self, manager):
        """Test that client is properly closed."""
        mock_client = MagicMock()
        manager.client = mock_client

        manager.close()

        mock_client.close.assert_called_once()
