"""Agent status manager for macOS menu bar application.

Provides a high-level interface for checking agent status, triggering polls,
starting/stopping the agent, and fetching agent logs with built-in caching
and retry logic.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class AgentLog:
    """Represents a single agent log entry."""

    id: int
    level: str
    action: Optional[str]
    message: str
    details: Optional[str] = None
    tokens_used: Optional[int] = None
    model_used: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class AgentStatus:
    """Current agent status."""

    is_running: bool
    autonomy_level: str
    last_poll: Optional[str] = None
    last_recommendation: Optional[str] = None
    started_at: Optional[str] = None
    session_stats: dict[str, int] = field(default_factory=dict)
    pending_suggestions: int = 0
    pending_recommendations: int = 0
    integrations: dict[str, bool] = field(default_factory=dict)


@dataclass
class CachedData:
    """Cached API response with timestamp."""

    data: Any
    timestamp: datetime
    ttl_seconds: int = 30

    def is_valid(self) -> bool:
        """Check if cache is still valid."""
        return datetime.now(UTC).replace(tzinfo=None) - self.timestamp < timedelta(seconds=self.ttl_seconds)


class AgentStatusManager:
    """Manages agent status and control via API with caching.

    This class handles:
    - Fetching agent status with exponential backoff retry
    - Caching status to reduce API calls
    - Starting/stopping agent
    - Triggering immediate polls
    - Fetching recent agent logs
    - Persistent state tracking
    """

    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        cache_ttl: int = 30,
        timeout: float = 5.0,
        max_retries: int = 3,
    ):
        """Initialize agent status manager.

        Args:
            api_url: Base URL of the personal assistant API
            cache_ttl: Cache time-to-live in seconds
            timeout: HTTP request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.api_url = api_url
        self.cache_ttl = cache_ttl
        self.timeout = timeout
        self.max_retries = max_retries
        self.client = httpx.Client(timeout=timeout)

        # Caches
        self._status_cache: Optional[CachedData] = None
        self._logs_cache: Optional[CachedData] = None

        # State file for persistence
        self._state_file = Path.home() / ".personal-assistant" / "menu-app-state.json"

    def get_status(self, use_cache: bool = True) -> AgentStatus:
        """Get current agent status.

        Args:
            use_cache: Whether to use cached status if available

        Returns:
            Current agent status

        Raises:
            httpx.RequestError: If API call fails after retries
        """
        # Check cache first
        if use_cache and self._status_cache and self._status_cache.is_valid():
            return self._status_cache.data

        try:
            status_data = self._call_api_with_retry("GET", "/agent/status")
            status = AgentStatus(**status_data)

            # Cache the result
            self._status_cache = CachedData(status, datetime.now(UTC).replace(tzinfo=None), self.cache_ttl)

            return status
        except Exception as e:
            logger.warning(f"Failed to fetch agent status: {e}")
            # Return cached data if available, even if expired
            if self._status_cache:
                return self._status_cache.data
            # Return unknown status
            return AgentStatus(is_running=False, autonomy_level="unknown")

    def get_logs(self, limit: int = 5, hours: int = 24) -> list[AgentLog]:
        """Get recent agent logs.

        Args:
            limit: Maximum number of logs to return
            hours: How many hours back to fetch logs

        Returns:
            List of recent agent logs

        Raises:
            httpx.RequestError: If API call fails after retries
        """
        # Check cache first
        if self._logs_cache and self._logs_cache.is_valid():
            return self._logs_cache.data

        try:
            logs_data = self._call_api_with_retry(
                "GET", "/agent/logs", params={"limit": limit, "hours": hours}
            )

            logs = [AgentLog(**log) for log in logs_data.get("logs", [])]

            # Cache the result
            self._logs_cache = CachedData(logs, datetime.now(UTC).replace(tzinfo=None), self.cache_ttl)

            return logs
        except Exception as e:
            logger.warning(f"Failed to fetch agent logs: {e}")
            return []

    async def start_agent(self, autonomy_level: Optional[str] = None) -> AgentStatus:
        """Start the autonomous agent.

        Args:
            autonomy_level: Optional autonomy level (suggest, auto_low, auto, full)

        Returns:
            Updated agent status

        Raises:
            httpx.RequestError: If API call fails after retries
        """
        payload = {}
        if autonomy_level:
            payload["autonomy_level"] = autonomy_level

        try:
            status_data = self._call_api_with_retry("POST", "/agent/start", json=payload)
            status = AgentStatus(**status_data)

            # Clear caches
            self._status_cache = None
            self._logs_cache = None

            # Persist state
            self._save_state(status)

            return status
        except Exception as e:
            logger.error(f"Failed to start agent: {e}")
            raise

    async def stop_agent(self) -> AgentStatus:
        """Stop the autonomous agent.

        Returns:
            Updated agent status

        Raises:
            httpx.RequestError: If API call fails after retries
        """
        try:
            status_data = self._call_api_with_retry("POST", "/agent/stop")
            status = AgentStatus(**status_data)

            # Clear caches
            self._status_cache = None
            self._logs_cache = None

            # Persist state
            self._save_state(status)

            return status
        except Exception as e:
            logger.error(f"Failed to stop agent: {e}")
            raise

    async def poll_now(self) -> dict:
        """Trigger an immediate agent poll cycle.

        Returns:
            Poll results

        Raises:
            httpx.RequestError: If API call fails after retries
        """
        try:
            results = self._call_api_with_retry("POST", "/agent/poll")

            # Clear status cache to force refresh
            self._status_cache = None
            self._logs_cache = None

            return results
        except Exception as e:
            logger.error(f"Failed to trigger poll: {e}")
            raise

    def _call_api_with_retry(
        self,
        method: str,
        endpoint: str,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        """Call API with exponential backoff retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (e.g., /agent/status)
            json: Request body as JSON
            params: Query parameters

        Returns:
            Parsed response JSON

        Raises:
            httpx.RequestError: If all retries fail
        """
        url = f"{self.api_url}/api{endpoint}"
        last_error = None

        for attempt in range(self.max_retries):
            try:
                response = self.client.request(method, url, json=json, params=params)
                response.raise_for_status()
                return response.json()
            except httpx.RequestError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    # Exponential backoff: 0.1s, 0.2s, 0.4s
                    wait_time = 0.1 * (2 ** attempt)
                    logger.debug(f"API call failed, retrying in {wait_time}s: {e}")
                    import time
                    time.sleep(wait_time)
                else:
                    logger.error(f"API call failed after {self.max_retries} attempts: {e}")

        if last_error:
            raise last_error

        raise RuntimeError("Unknown error in API retry loop")

    def _save_state(self, status: AgentStatus) -> None:
        """Persist agent state to disk.

        Args:
            status: Current agent status
        """
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "is_running": status.is_running,
                "autonomy_level": status.autonomy_level,
                "last_poll": status.last_poll,
                "timestamp": datetime.now(UTC).replace(tzinfo=None).isoformat(),
            }
            self._state_file.write_text(json.dumps(state, indent=2))
        except Exception as e:
            logger.warning(f"Failed to save state: {e}")

    def load_cached_state(self) -> Optional[dict]:
        """Load last known agent state from disk.

        Returns:
            Cached state dict if available, None otherwise
        """
        try:
            if self._state_file.exists():
                return json.loads(self._state_file.read_text())
        except Exception as e:
            logger.warning(f"Failed to load cached state: {e}")
        return None

    def close(self) -> None:
        """Close HTTP client."""
        self.client.close()

    def __del__(self) -> None:
        """Cleanup on deletion."""
        try:
            self.close()
        except Exception:
            pass
