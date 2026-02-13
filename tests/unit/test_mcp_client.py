"""Unit tests for Granola MCP client with JSON-RPC 2.0."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.integrations.mcp_client import MCPClient


@pytest.fixture
def mcp_client():
    """Sample MCP client."""
    return MCPClient(
        server_url="https://mcp.granola.ai/mcp",
        token="test_token",
    )


@pytest.fixture
def sample_meetings_list():
    """Sample JSON-RPC response from list_meetings."""
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "meetings": [
                {
                    "id": "meeting1",
                    "title": "Team Standup",
                    "date": "2026-02-10T10:00:00Z",
                    "attendees": ["alice@example.com", "bob@example.com"],
                    "workspace_id": "workspace1",
                },
                {
                    "id": "meeting2",
                    "title": "Design Review",
                    "date": "2026-02-09T14:00:00Z",
                    "attendees": ["charlie@example.com"],
                    "workspace_id": "workspace1",
                },
            ]
        },
    }


@pytest.fixture
def sample_meetings_with_content():
    """Sample JSON-RPC response from get_meetings with content."""
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "meetings": [
                {
                    "id": "meeting1",
                    "title": "Team Standup",
                    "date": "2026-02-10T10:00:00Z",
                    "attendees": ["alice@example.com", "bob@example.com"],
                    "workspace_id": "workspace1",
                    "content": "Discussed project timeline and upcoming milestones.",
                }
            ]
        },
    }


class TestMCPClient:
    """Test MCP client functionality with JSON-RPC 2.0."""

    def test_initialization(self):
        """Test MCP client initialization."""
        client = MCPClient(
            server_url="https://mcp.granola.ai/mcp",
            token="test_token",
            timeout=60.0,
        )

        assert client.server_url == "https://mcp.granola.ai/mcp"
        assert client.token == "test_token"
        assert client.timeout == 60.0
        assert "Authorization" in client.client.headers
        assert client.client.headers["Authorization"] == "Bearer test_token"

    def test_initialization_strips_trailing_slash(self):
        """Test server URL trailing slash handling."""
        client = MCPClient(
            server_url="https://mcp.granola.ai/mcp/",
            token="test_token",
        )

        assert client.server_url == "https://mcp.granola.ai/mcp"

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test MCP client as context manager."""
        async with MCPClient("https://mcp.granola.ai/mcp", "test_token") as client:
            assert client is not None

    @pytest.mark.asyncio
    async def test_list_meetings_success(self, mcp_client, sample_meetings_list):
        """Test successful list_meetings call with JSON-RPC."""
        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.json.return_value = sample_meetings_list
        mock_response.raise_for_status = MagicMock()

        with patch.object(mcp_client.client, "post", new=AsyncMock(return_value=mock_response)):
            meetings = await mcp_client.list_meetings(limit=100)

            assert len(meetings) == 2
            assert meetings[0]["id"] == "meeting1"
            assert meetings[0]["title"] == "Team Standup"
            assert meetings[1]["id"] == "meeting2"

            # Verify JSON-RPC call format
            mcp_client.client.post.assert_called_once()
            call_args = mcp_client.client.post.call_args
            assert call_args[0][0] == "https://mcp.granola.ai/mcp"
            request_payload = call_args[1]["json"]
            assert request_payload["jsonrpc"] == "2.0"
            assert request_payload["method"] == "tools/call"
            assert request_payload["params"]["name"] == "list_meetings"
            assert request_payload["params"]["arguments"]["limit"] == 100

    @pytest.mark.asyncio
    async def test_list_meetings_with_workspace_filter(self, mcp_client, sample_meetings_list):
        """Test list_meetings with workspace filtering."""
        mock_response = MagicMock()
        mock_response.json.return_value = sample_meetings_list
        mock_response.raise_for_status = MagicMock()

        with patch.object(mcp_client.client, "post", new=AsyncMock(return_value=mock_response)):
            meetings = await mcp_client.list_meetings(limit=50, workspace_id="workspace1")

            assert len(meetings) == 2

            # Verify workspace_id in arguments
            call_args = mcp_client.client.post.call_args
            request_payload = call_args[1]["json"]
            assert request_payload["params"]["arguments"]["workspace_id"] == "workspace1"

    @pytest.mark.asyncio
    async def test_list_meetings_http_error(self, mcp_client):
        """Test list_meetings handles HTTP errors."""
        # Mock HTTP error
        with patch.object(
            mcp_client.client,
            "post",
            new=AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "Server error",
                    request=MagicMock(),
                    response=MagicMock(status_code=500, text="Internal Server Error"),
                )
            ),
        ):
            with pytest.raises(httpx.HTTPStatusError):
                await mcp_client.list_meetings()

    @pytest.mark.asyncio
    async def test_list_meetings_jsonrpc_error(self, mcp_client):
        """Test list_meetings handles JSON-RPC errors."""
        # Mock JSON-RPC error response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32600, "message": "Invalid Request"},
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(mcp_client.client, "post", new=AsyncMock(return_value=mock_response)):
            with pytest.raises(RuntimeError, match="Invalid Request"):
                await mcp_client.list_meetings()

    @pytest.mark.asyncio
    async def test_get_meetings_with_ids(self, mcp_client, sample_meetings_with_content):
        """Test get_meetings with specific meeting IDs."""
        mock_response = MagicMock()
        mock_response.json.return_value = sample_meetings_with_content
        mock_response.raise_for_status = MagicMock()

        with patch.object(mcp_client.client, "post", new=AsyncMock(return_value=mock_response)):
            meetings = await mcp_client.get_meetings(meeting_ids=["meeting1"])

            assert len(meetings) == 1
            assert meetings[0]["id"] == "meeting1"
            assert "content" in meetings[0]
            assert "Discussed project timeline" in meetings[0]["content"]

            # Verify JSON-RPC call format
            call_args = mcp_client.client.post.call_args
            request_payload = call_args[1]["json"]
            assert request_payload["params"]["name"] == "get_meetings"
            assert request_payload["params"]["arguments"]["meeting_ids"] == ["meeting1"]

    @pytest.mark.asyncio
    async def test_get_meetings_with_query(self, mcp_client, sample_meetings_with_content):
        """Test get_meetings with search query."""
        mock_response = MagicMock()
        mock_response.json.return_value = sample_meetings_with_content
        mock_response.raise_for_status = MagicMock()

        with patch.object(mcp_client.client, "post", new=AsyncMock(return_value=mock_response)):
            meetings = await mcp_client.get_meetings(query="timeline", limit=50)

            assert len(meetings) == 1

            # Verify query in arguments
            call_args = mcp_client.client.post.call_args
            request_payload = call_args[1]["json"]
            assert request_payload["params"]["arguments"]["query"] == "timeline"
            assert request_payload["params"]["arguments"]["limit"] == 50

    @pytest.mark.asyncio
    async def test_get_meetings_http_error(self, mcp_client):
        """Test get_meetings handles HTTP errors."""
        with patch.object(
            mcp_client.client,
            "post",
            new=AsyncMock(side_effect=httpx.HTTPError("Network error")),
        ):
            with pytest.raises(httpx.HTTPError):
                await mcp_client.get_meetings(meeting_ids=["meeting1"])

    @pytest.mark.asyncio
    async def test_query_granola_meetings_success(self, mcp_client):
        """Test query_granola_meetings with LLM response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "answer": "The team discussed the Q1 roadmap and agreed to prioritize feature X.",
                "meetings": [
                    {"id": "meeting1", "title": "Planning Meeting"},
                ],
            },
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(mcp_client.client, "post", new=AsyncMock(return_value=mock_response)):
            result = await mcp_client.query_granola_meetings(
                query="What did the team decide about Q1?",
                limit=10,
            )

            assert "answer" in result
            assert "meetings" in result
            assert "Q1 roadmap" in result["answer"]

            # Verify JSON-RPC call format
            call_args = mcp_client.client.post.call_args
            request_payload = call_args[1]["json"]
            assert request_payload["params"]["name"] == "query_granola_meetings"
            assert request_payload["params"]["arguments"]["query"] == "What did the team decide about Q1?"

    @pytest.mark.asyncio
    async def test_get_meeting_transcript_success(self, mcp_client):
        """Test get_meeting_transcript for paid tier."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "meeting_id": "meeting1",
                "transcript": "Alice: Let's discuss the roadmap...",
                "segments": [
                    {"speaker": "Alice", "text": "Let's discuss the roadmap...", "timestamp": 0.0}
                ],
            },
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(mcp_client.client, "post", new=AsyncMock(return_value=mock_response)):
            result = await mcp_client.get_meeting_transcript(meeting_id="meeting1")

            assert result["meeting_id"] == "meeting1"
            assert "transcript" in result
            assert "segments" in result

            # Verify JSON-RPC call format
            call_args = mcp_client.client.post.call_args
            request_payload = call_args[1]["json"]
            assert request_payload["params"]["name"] == "get_meeting_transcript"
            assert request_payload["params"]["arguments"]["meeting_id"] == "meeting1"

    @pytest.mark.asyncio
    async def test_get_meeting_transcript_forbidden(self, mcp_client):
        """Test get_meeting_transcript raises 403 for free tier."""
        mock_response = MagicMock(status_code=403, text="Forbidden")
        mock_request = MagicMock()

        with patch.object(
            mcp_client.client,
            "post",
            new=AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "Forbidden", request=mock_request, response=mock_response
                )
            ),
        ):
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                await mcp_client.get_meeting_transcript(meeting_id="meeting1")

            assert exc_info.value.response.status_code == 403

    @pytest.mark.asyncio
    async def test_request_id_increments(self, mcp_client, sample_meetings_list):
        """Test JSON-RPC request IDs increment."""
        mock_response = MagicMock()
        mock_response.json.return_value = sample_meetings_list
        mock_response.raise_for_status = MagicMock()

        with patch.object(mcp_client.client, "post", new=AsyncMock(return_value=mock_response)):
            # Make two calls
            await mcp_client.list_meetings(limit=10)
            await mcp_client.list_meetings(limit=20)

            # Check that request IDs incremented
            calls = mcp_client.client.post.call_args_list
            assert calls[0][1]["json"]["id"] == 1
            assert calls[1][1]["json"]["id"] == 2
