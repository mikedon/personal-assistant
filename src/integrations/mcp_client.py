"""HTTP client for Granola MCP server.

Implements the Model Context Protocol (MCP) client for interacting with
Granola's official MCP server at https://mcp.granola.ai/mcp.

Uses JSON-RPC 2.0 protocol for all tool calls.
Handles both JSON and Server-Sent Events (SSE) responses.
Parses MCP content format (text/XML responses).
"""

import json
import logging
import re
from typing import Any
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger(__name__)


class MCPClient:
    """HTTP client for Granola MCP server using JSON-RPC 2.0.

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
        self._request_id = 0

        # Create async HTTP client with retry transport
        transport = httpx.AsyncHTTPTransport(retries=max_retries)
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                # MCP requires accepting both JSON and SSE (Server-Sent Events)
                "Accept": "application/json, text/event-stream",
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

    def _next_request_id(self) -> int:
        """Generate next JSON-RPC request ID."""
        self._request_id += 1
        return self._request_id

    def _parse_sse_response(self, sse_text: str) -> dict[str, Any]:
        """Parse Server-Sent Events (SSE) format response.

        SSE format:
            event: message
            data: {"result": {...}}

        Args:
            sse_text: Raw SSE response text

        Returns:
            Parsed JSON data from the SSE stream

        Raises:
            ValueError: If SSE format is invalid or contains no data
        """
        lines = sse_text.strip().split("\n")
        data_lines = []

        for line in lines:
            line = line.strip()
            if line.startswith("data: "):
                # Extract JSON after "data: " prefix
                data_lines.append(line[6:])  # Remove "data: " prefix

        if not data_lines:
            raise ValueError(f"No data lines found in SSE response: {sse_text[:200]}")

        # Combine all data lines (SSE can split data across multiple lines)
        json_str = "".join(data_lines)

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in SSE data: {e}\nData: {json_str[:500]}") from e

    def _parse_mcp_content(self, result: dict[str, Any]) -> str:
        """Parse MCP content format to extract text.

        MCP returns content as an array of typed blocks:
            {"content": [{"type": "text", "text": "..."}]}

        Args:
            result: The JSON-RPC result object

        Returns:
            Combined text content from all text blocks

        Raises:
            ValueError: If content format is invalid
        """
        content_blocks = result.get("content", [])

        if not content_blocks:
            raise ValueError(f"No content blocks in MCP result: {result}")

        text_parts = []
        for block in content_blocks:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))

        if not text_parts:
            raise ValueError(f"No text content in MCP result: {result}")

        return "\n".join(text_parts)

    def _parse_meetings_xml(self, xml_text: str, include_content: bool = False) -> list[dict[str, Any]]:
        """Parse meetings from XML-like format using regex.

        Granola returns meetings in XML format, but it often contains unescaped
        special characters that break XML parsing. We use regex to extract
        meetings more robustly.

        Format:
            <meetings_data count="120">
              <meeting id="..." title="..." date="...">
                <known_participants>...</known_participants>
                <notes>...</notes>
              </meeting>
            </meetings_data>

        Args:
            xml_text: XML text containing meetings data
            include_content: If True, extract meeting notes/content

        Returns:
            List of meeting dicts
        """
        meetings = []

        # Find all meeting tags using regex
        meeting_pattern = r'<meeting\s+([^>]+)>(.*?)</meeting>'
        for match in re.finditer(meeting_pattern, xml_text, re.DOTALL):
            attrs_str = match.group(1)
            content = match.group(2)

            # Extract attributes from meeting tag
            meeting = {}

            # Extract id
            id_match = re.search(r'id="([^"]+)"', attrs_str)
            meeting["id"] = id_match.group(1) if id_match else ""

            # Extract title
            title_match = re.search(r'title="([^"]+)"', attrs_str)
            meeting["title"] = title_match.group(1) if title_match else ""

            # Extract date
            date_match = re.search(r'date="([^"]+)"', attrs_str)
            meeting["date"] = date_match.group(1) if date_match else ""

            # Extract workspace_id (optional)
            workspace_match = re.search(r'workspace_id="([^"]+)"', attrs_str)
            meeting["workspace_id"] = workspace_match.group(1) if workspace_match else ""

            # Extract attendees from known_participants
            participants_match = re.search(
                r'<known_participants>(.*?)</known_participants>',
                content,
                re.DOTALL
            )
            if participants_match:
                participants_text = participants_match.group(1)
                # Extract email addresses (in angle brackets)
                emails = re.findall(r'<([^>]+@[^>]+)>', participants_text)
                meeting["attendees"] = emails
            else:
                meeting["attendees"] = []

            # Extract notes/content if requested
            if include_content:
                # Try <summary> tag first (newer format), then <notes> (legacy)
                summary_match = re.search(r'<summary>(.*?)</summary>', content, re.DOTALL)
                notes_match = re.search(r'<notes>(.*?)</notes>', content, re.DOTALL)

                if summary_match:
                    meeting["content"] = summary_match.group(1).strip()
                elif notes_match:
                    meeting["content"] = notes_match.group(1).strip()
                else:
                    meeting["content"] = ""

            meetings.append(meeting)

        logger.debug(f"Parsed {len(meetings)} meetings from XML-like format")
        return meetings

    async def _call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Call an MCP tool using JSON-RPC 2.0 protocol.

        Args:
            tool_name: Name of the MCP tool (e.g., "list_meetings")
            arguments: Tool arguments as dict

        Returns:
            Tool result (parsed from JSON-RPC response)

        Raises:
            httpx.HTTPError: On HTTP request failures
            RuntimeError: On JSON-RPC errors
        """
        # Build JSON-RPC 2.0 request
        request_payload = {
            "jsonrpc": "2.0",
            "id": self._next_request_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        try:
            logger.debug(f"Calling MCP tool '{tool_name}' with arguments: {arguments}")

            # POST to base MCP endpoint
            response = await self.client.post(
                self.server_url,
                json=request_payload,
            )
            response.raise_for_status()

            # Log response details for debugging
            content_type = response.headers.get("content-type", "unknown")
            logger.debug(f"Response status: {response.status_code}")
            logger.debug(f"Response content-type: {content_type}")
            logger.debug(f"Response content (first 500 chars): {response.text[:500]}")

            # Parse response based on content-type
            try:
                if "text/event-stream" in content_type:
                    # Parse Server-Sent Events (SSE) format
                    logger.debug("Parsing SSE response")
                    data = self._parse_sse_response(response.text)
                else:
                    # Parse regular JSON
                    logger.debug("Parsing JSON response")
                    data = response.json()
            except ValueError as e:
                logger.error(
                    f"Failed to parse response from MCP tool '{tool_name}': {e}\n"
                    f"Response status: {response.status_code}\n"
                    f"Content-Type: {content_type}\n"
                    f"Response content: {response.text[:1000]}"
                )
                raise RuntimeError(
                    f"Invalid response from MCP tool '{tool_name}': {e}\n"
                    f"Content-Type: {content_type}\n"
                    f"Response: {response.text[:500]}"
                ) from e

            # Check for JSON-RPC error
            if "error" in data:
                error = data["error"]
                raise RuntimeError(
                    f"MCP tool '{tool_name}' failed: "
                    f"{error.get('code', 'unknown')} - {error.get('message', 'Unknown error')}"
                )

            # Return result
            result = data.get("result", {})
            logger.debug(f"MCP tool '{tool_name}' completed successfully")
            return result

        except httpx.HTTPStatusError as e:
            logger.error(
                f"MCP tool '{tool_name}' HTTP error: {e.response.status_code} {e.response.text}"
            )
            raise
        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling MCP tool '{tool_name}': {e}")
            raise

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
        arguments = {"limit": limit}
        if workspace_id:
            arguments["workspace_id"] = workspace_id

        result = await self._call_tool("list_meetings", arguments)

        # Parse MCP content format
        try:
            xml_text = self._parse_mcp_content(result)
            meetings = self._parse_meetings_xml(xml_text)
        except ValueError as e:
            logger.error(f"Failed to parse list_meetings response: {e}")
            # Return empty list if parsing fails
            return []

        logger.debug(f"list_meetings returned {len(meetings)} meetings")
        return meetings

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
        arguments: dict[str, Any] = {"limit": limit}
        if query:
            arguments["query"] = query
        if meeting_ids:
            arguments["meeting_ids"] = meeting_ids

        result = await self._call_tool("get_meetings", arguments)

        # Parse MCP content format with meeting content
        try:
            xml_text = self._parse_mcp_content(result)
            meetings = self._parse_meetings_xml(xml_text, include_content=True)
        except ValueError as e:
            logger.error(f"Failed to parse get_meetings response: {e}")
            # Return empty list if parsing fails
            return []

        logger.debug(f"get_meetings returned {len(meetings)} meetings with content")
        return meetings

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
        arguments = {"query": query, "limit": limit}

        result = await self._call_tool("query_granola_meetings", arguments)
        logger.debug("query_granola_meetings completed successfully")
        return result

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
        arguments = {"meeting_id": meeting_id}

        try:
            result = await self._call_tool("get_meeting_transcript", arguments)
            logger.debug(f"get_meeting_transcript completed for meeting {meeting_id}")
            return result

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.warning(
                    f"Transcript not available for meeting {meeting_id}: "
                    "Requires paid Granola tier"
                )
            raise
