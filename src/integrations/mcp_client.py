"""HTTP client for Granola MCP server.

Implements the Model Context Protocol (MCP) client for interacting with
Granola's official MCP server at https://mcp.granola.ai/mcp.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MCPClient:
    """HTTP client for Granola MCP server.

    Provides typed methods for calling Granola MCP tools:
    - list_meetings: Scan meetings by ID, title, date, attendees
    - get_meetings: Search meeting content including transcripts and notes
    - query_granola_meetings: Chat with meeting notes
    - get_meeting_transcript: Access raw transcripts (paid tiers only)

    Uses httpx for async HTTP requests with automatic retry and timeout handling.
    """

    def __init__(
        self,
        server_url: str,
        token: str,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """Initialize MCP client.

        Args:
            server_url: MCP server URL (https://mcp.granola.ai/mcp)
            token: OAuth access token
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
        """
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.timeout = timeout

        # Create async HTTP client with retry transport
        transport = httpx.AsyncHTTPTransport(retries=max_retries)
        self.client = httpx.AsyncClient(
            base_url=self.server_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=timeout,
            transport=transport,
        )

    async def close(self) -> None:
        """Close HTTP client and cleanup resources."""
        await self.client.aclose()

    async def __aenter__(self):
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources."""
        await self.close()

    async def list_meetings(
        self,
        limit: int = 100,
        workspace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Call list_meetings tool to scan meetings.

        Lists meetings by ID, title, date, and attendees. Does not return
        full meeting content (use get_meetings for content).

        Args:
            limit: Maximum number of meetings to return (default: 100)
            workspace_id: Filter by workspace ID (None = all workspaces)

        Returns:
            List of meeting metadata dicts with keys:
            - id: Meeting ID
            - title: Meeting title
            - date: Meeting date (ISO format)
            - attendees: List of attendee email addresses
            - workspace_id: Workspace ID

        Raises:
            httpx.HTTPError: On HTTP request failures
        """
        payload = {"limit": limit}
        if workspace_id:
            payload["workspace_id"] = workspace_id

        try:
            logger.debug(f"Calling list_meetings with limit={limit}, workspace_id={workspace_id}")
            response = await self.client.post("/tools/list_meetings", json=payload)
            response.raise_for_status()

            data = response.json()
            meetings = data.get("meetings", [])

            logger.debug(f"list_meetings returned {len(meetings)} meetings")
            return meetings

        except httpx.HTTPStatusError as e:
            logger.error(f"MCP list_meetings failed: {e.response.status_code} {e.response.text}")
            raise
        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling list_meetings: {e}")
            raise

    async def get_meetings(
        self,
        query: str | None = None,
        meeting_ids: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Call get_meetings tool to retrieve full meeting content.

        Searches meeting content including transcripts and notes. Returns
        full meeting data with content field.

        Args:
            query: Search query string (optional)
            meeting_ids: List of specific meeting IDs to retrieve (optional)
            limit: Maximum number of meetings to return (default: 100)

        Returns:
            List of full meeting dicts with keys:
            - id: Meeting ID
            - title: Meeting title
            - date: Meeting date (ISO format)
            - attendees: List of attendee email addresses
            - workspace_id: Workspace ID
            - content: Meeting notes content (string)
            - transcript: Meeting transcript if available (paid tiers)

        Raises:
            httpx.HTTPError: On HTTP request failures
        """
        payload: dict[str, Any] = {"limit": limit}
        if query:
            payload["query"] = query
        if meeting_ids:
            payload["meeting_ids"] = meeting_ids

        try:
            logger.debug(
                f"Calling get_meetings with query={query}, "
                f"meeting_ids={meeting_ids}, limit={limit}"
            )
            response = await self.client.post("/tools/get_meetings", json=payload)
            response.raise_for_status()

            data = response.json()
            meetings = data.get("meetings", [])

            logger.debug(f"get_meetings returned {len(meetings)} meetings with content")
            return meetings

        except httpx.HTTPStatusError as e:
            logger.error(f"MCP get_meetings failed: {e.response.status_code} {e.response.text}")
            raise
        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling get_meetings: {e}")
            raise

    async def query_granola_meetings(
        self,
        query: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Call query_granola_meetings tool to chat with meeting notes.

        Uses LLM to answer questions about meeting notes.

        Args:
            query: Natural language question about meetings
            limit: Maximum number of meetings to search (default: 10)

        Returns:
            Dict with keys:
            - answer: LLM-generated answer to the query
            - meetings: List of relevant meetings used for answer

        Raises:
            httpx.HTTPError: On HTTP request failures
        """
        payload = {"query": query, "limit": limit}

        try:
            logger.debug(f"Calling query_granola_meetings with query='{query}'")
            response = await self.client.post("/tools/query_granola_meetings", json=payload)
            response.raise_for_status()

            data = response.json()
            logger.debug("query_granola_meetings completed successfully")
            return data

        except httpx.HTTPStatusError as e:
            logger.error(
                f"MCP query_granola_meetings failed: {e.response.status_code} {e.response.text}"
            )
            raise
        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling query_granola_meetings: {e}")
            raise

    async def get_meeting_transcript(
        self,
        meeting_id: str,
    ) -> dict[str, Any]:
        """Call get_meeting_transcript tool to retrieve raw transcript.

        Retrieves the raw meeting transcript. Requires paid Granola tier.

        Args:
            meeting_id: Meeting ID

        Returns:
            Dict with keys:
            - meeting_id: Meeting ID
            - transcript: Raw transcript text
            - segments: List of transcript segments with timestamps

        Raises:
            httpx.HTTPError: On HTTP request failures
            httpx.HTTPStatusError: 403 if not available on current tier
        """
        payload = {"meeting_id": meeting_id}

        try:
            logger.debug(f"Calling get_meeting_transcript for meeting {meeting_id}")
            response = await self.client.post("/tools/get_meeting_transcript", json=payload)
            response.raise_for_status()

            data = response.json()
            logger.debug(f"get_meeting_transcript completed for meeting {meeting_id}")
            return data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.warning(
                    f"Transcript not available for meeting {meeting_id}: "
                    "Requires paid Granola tier"
                )
            else:
                logger.error(
                    f"MCP get_meeting_transcript failed: "
                    f"{e.response.status_code} {e.response.text}"
                )
            raise
        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling get_meeting_transcript: {e}")
            raise
