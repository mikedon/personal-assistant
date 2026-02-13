"""Unit tests for Granola MCP integration."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.integrations.base import ActionableItemType, IntegrationType
from src.integrations.granola_integration import GranolaIntegration
from src.models import ProcessedGranolaNote


@pytest.fixture
def granola_config():
    """Sample Granola workspace configuration."""
    return {
        "workspace_id": "all",
        "lookback_days": 7,
    }


@pytest.fixture
def mock_oauth_manager():
    """Mock OAuth manager."""
    manager = MagicMock()
    manager.get_valid_token = AsyncMock(return_value="test_access_token")
    return manager


@pytest.fixture
def mock_mcp_client():
    """Mock MCP client."""
    client = MagicMock()
    client.list_meetings = AsyncMock(return_value=[])
    client.get_meetings = AsyncMock(return_value=[])
    return client


@pytest.fixture
def sample_mcp_meetings():
    """Sample meetings from MCP API."""
    return [
        {
            "id": "meeting1",
            "title": "Team Standup",
            "date": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
            "attendees": ["alice@example.com", "bob@example.com"],
            "workspace_id": "engineering",
        },
        {
            "id": "meeting2",
            "title": "Design Review",
            "date": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "attendees": ["charlie@example.com"],
            "workspace_id": "design",
        },
    ]


@pytest.fixture
def sample_mcp_meetings_with_content():
    """Sample meetings with content from MCP API."""
    return [
        {
            "id": "meeting1",
            "title": "Team Standup",
            "date": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
            "attendees": ["alice@example.com", "bob@example.com"],
            "workspace_id": "engineering",
            "content": "Discussed project timeline and upcoming milestones. Action items: update docs, review PR.",
        }
    ]


class TestGranolaIntegration:
    """Test Granola MCP integration functionality."""

    def test_initialization(self, granola_config):
        """Test Granola MCP integration initialization."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )

        assert integration.workspace_id == "all"
        assert integration.lookback_days == 7
        assert integration.integration_type == IntegrationType.GRANOLA
        assert integration.oauth_manager is not None
        assert integration.mcp_client is None  # Not initialized until authenticate()

    def test_get_token_path_default(self, granola_config):
        """Test default token path."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )

        expected_path = Path.home() / ".personal-assistant" / "token.granola.json"
        assert integration.oauth_manager.token_path == expected_path

    def test_get_token_path_custom(self):
        """Test custom token path from config."""
        config = {
            "workspace_id": "all",
            "lookback_days": 7,
            "token_path": "/custom/path/token.json",
        }
        integration = GranolaIntegration(config=config, account_id="all")

        assert integration.oauth_manager.token_path == Path("/custom/path/token.json")

    @pytest.mark.asyncio
    async def test_authenticate_success(self, granola_config, mock_oauth_manager, mock_mcp_client):
        """Test successful MCP authentication."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )
        integration.oauth_manager = mock_oauth_manager

        with patch("src.integrations.granola_integration.MCPClient") as mock_client_class:
            mock_client_class.return_value = mock_mcp_client

            result = await integration.authenticate()

            assert result is True
            assert integration.mcp_client is not None
            mock_oauth_manager.get_valid_token.assert_called_once()
            mock_mcp_client.list_meetings.assert_called_once_with(limit=1)

    @pytest.mark.asyncio
    async def test_authenticate_oauth_failure(self, granola_config):
        """Test authentication fails when OAuth fails."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )

        # Mock OAuth manager to raise error
        integration.oauth_manager.get_valid_token = AsyncMock(
            side_effect=RuntimeError("OAuth failed")
        )

        from src.integrations.base import AuthenticationError

        with pytest.raises(AuthenticationError, match="Failed to authenticate"):
            await integration.authenticate()

    @pytest.mark.asyncio
    async def test_authenticate_connection_failure(self, granola_config, mock_oauth_manager):
        """Test authentication fails when MCP server unreachable."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )
        integration.oauth_manager = mock_oauth_manager

        with patch("src.integrations.granola_integration.MCPClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.list_meetings = AsyncMock(side_effect=httpx.HTTPError("Connection failed"))
            mock_client_class.return_value = mock_client

            from src.integrations.base import AuthenticationError

            with pytest.raises(AuthenticationError, match="Failed to connect"):
                await integration.authenticate()

    @pytest.mark.asyncio
    async def test_poll_fetches_meetings(self, granola_config, mock_mcp_client, sample_mcp_meetings, sample_mcp_meetings_with_content):
        """Test poll fetches meetings from MCP server."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )
        integration.mcp_client = mock_mcp_client

        # Mock list_meetings to return sample meetings
        mock_mcp_client.list_meetings = AsyncMock(return_value=sample_mcp_meetings)

        # Mock get_meetings to return meetings with content
        mock_mcp_client.get_meetings = AsyncMock(return_value=sample_mcp_meetings_with_content)

        # Mock _filter_new_notes to return all meetings (none processed yet)
        with patch.object(integration, "_filter_new_notes", return_value=sample_mcp_meetings):
            items = await integration.poll()

            # Should have extracted one item from the meeting with content
            assert len(items) > 0
            assert items[0].title == "Review meeting: Team Standup"
            assert items[0].source == IntegrationType.GRANOLA

            # Verify API calls
            mock_mcp_client.list_meetings.assert_called_once()
            mock_mcp_client.get_meetings.assert_called_once()

    @pytest.mark.asyncio
    async def test_poll_filters_by_date(self, granola_config, mock_mcp_client):
        """Test poll filters meetings by lookback window."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )
        integration.mcp_client = mock_mcp_client

        # Create meetings: one recent, one old
        recent_meeting = {
            "id": "recent",
            "title": "Recent Meeting",
            "date": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
            "attendees": [],
            "workspace_id": "all",
        }
        old_meeting = {
            "id": "old",
            "title": "Old Meeting",
            "date": (datetime.now(UTC) - timedelta(days=10)).isoformat(),  # Outside 7-day window
            "attendees": [],
            "workspace_id": "all",
        }

        mock_mcp_client.list_meetings = AsyncMock(return_value=[recent_meeting, old_meeting])
        mock_mcp_client.get_meetings = AsyncMock(return_value=[])

        with patch.object(integration, "_filter_new_notes", side_effect=lambda meetings: meetings):
            await integration.poll()

            # Should only fetch content for recent meeting
            call_args = mock_mcp_client.get_meetings.call_args
            meeting_ids = call_args.kwargs["meeting_ids"]
            assert "recent" in meeting_ids
            assert "old" not in meeting_ids

    @pytest.mark.asyncio
    async def test_poll_filters_by_workspace(self, granola_config, mock_mcp_client, sample_mcp_meetings):
        """Test poll filters by workspace ID."""
        # Configure for specific workspace
        granola_config["workspace_id"] = "engineering"
        integration = GranolaIntegration(
            config=granola_config,
            account_id="engineering",
        )
        integration.mcp_client = mock_mcp_client

        mock_mcp_client.list_meetings = AsyncMock(return_value=sample_mcp_meetings)
        mock_mcp_client.get_meetings = AsyncMock(return_value=[])

        with patch.object(integration, "_filter_new_notes", return_value=[]):
            await integration.poll()

            # Should pass workspace filter to API
            call_args = mock_mcp_client.list_meetings.call_args
            assert call_args.kwargs["workspace_id"] == "engineering"

    @pytest.mark.asyncio
    async def test_poll_http_error(self, granola_config, mock_mcp_client):
        """Test poll raises PollError on HTTP errors."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )
        integration.mcp_client = mock_mcp_client

        mock_mcp_client.list_meetings = AsyncMock(side_effect=httpx.HTTPError("Connection error"))

        from src.integrations.base import PollError

        with pytest.raises(PollError, match="Failed to poll Granola MCP server"):
            await integration.poll()

    def test_parse_date_valid(self, granola_config):
        """Test date parsing with valid ISO format."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )

        # Test Z format
        date_str = "2026-02-10T10:00:00Z"
        result = integration._parse_date(date_str)
        assert result.year == 2026
        assert result.month == 2
        assert result.day == 10

        # Test +00:00 format
        date_str = "2026-02-10T10:00:00+00:00"
        result = integration._parse_date(date_str)
        assert result.year == 2026

    def test_parse_date_invalid(self, granola_config):
        """Test date parsing with invalid format returns minimum date."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )

        result = integration._parse_date("invalid-date")
        assert result == datetime.min.replace(tzinfo=UTC)

        result = integration._parse_date("")
        assert result == datetime.min.replace(tzinfo=UTC)

    @patch("src.models.database.get_db_session")
    def test_filter_new_notes(self, mock_get_db_session, granola_config, sample_mcp_meetings):
        """Test filtering of already-processed notes."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )

        # Mock database session to return meeting1 as processed
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [("meeting1",)]
        mock_db.query.return_value = mock_query
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_get_db_session.return_value = mock_db

        new_meetings = integration._filter_new_notes(sample_mcp_meetings)

        assert len(new_meetings) == 1
        assert new_meetings[0]["id"] == "meeting2"

    def test_extract_actionable_item_with_content(self, granola_config):
        """Test extraction of actionable item from meeting with content."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )

        meeting = {
            "id": "meeting123",
            "title": "Team Standup",
            "date": datetime.now(UTC).isoformat(),
            "attendees": ["alice@example.com", "bob@example.com"],
            "workspace_id": "engineering",
            "content": "Discussed project timeline and milestones.",
        }

        item = integration._extract_actionable_item(meeting)

        assert item is not None
        assert item.type == ActionableItemType.DOCUMENT_REVIEW
        assert item.title == "Review meeting: Team Standup"
        assert "Discussed project timeline" in item.description
        assert "alice@example.com, bob@example.com" in item.description
        assert item.source == IntegrationType.GRANOLA
        assert item.source_reference == "meeting123"
        assert item.account_id == "all"
        assert "meeting-notes" in item.tags
        assert "granola" in item.tags

    def test_extract_actionable_item_empty_content(self, granola_config):
        """Test extraction skips meetings with no content."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )

        meeting = {
            "id": "meeting456",
            "title": "Empty Meeting",
            "date": datetime.now(UTC).isoformat(),
            "attendees": [],
            "workspace_id": "engineering",
            "content": "",
        }

        item = integration._extract_actionable_item(meeting)

        assert item is None

    def test_extract_actionable_item_with_object_attendees(self, granola_config):
        """Test extraction handles attendees as objects (not just strings)."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )

        meeting = {
            "id": "meeting789",
            "title": "Design Review",
            "date": datetime.now(UTC).isoformat(),
            "attendees": [
                {"name": "Alice", "email": "alice@example.com"},
                {"name": "Bob", "email": "bob@example.com"},
            ],
            "workspace_id": "design",
            "content": "Reviewed mockups and feedback.",
        }

        item = integration._extract_actionable_item(meeting)

        assert item is not None
        assert "alice@example.com, bob@example.com" in item.description

    @patch("src.models.database.get_db_session")
    def test_mark_note_processed(self, mock_get_db_session, granola_config):
        """Test marking a note as processed."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="engineering",
        )

        # Mock database session
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None  # No existing record
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_get_db_session.return_value = mock_db

        note_created_at = datetime.now(UTC) - timedelta(days=1)

        integration.mark_note_processed(
            note_id="meeting999",
            note_title="Sprint Planning",
            note_created_at=note_created_at,
            tasks_created=2,
        )

        # Verify database session was used correctly
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

        # Verify the created object
        added_note = mock_db.add.call_args[0][0]
        assert isinstance(added_note, ProcessedGranolaNote)
        assert added_note.note_id == "meeting999"
        assert added_note.note_title == "Sprint Planning"
        assert added_note.workspace_id == "all"
        assert added_note.account_id == "engineering"
        assert added_note.tasks_created_count == 2
