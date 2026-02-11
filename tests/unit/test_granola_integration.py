"""Unit tests for Granola integration."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

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
def sample_cache_data():
    """Sample Granola cache data structure."""
    note_id = "note123"
    created_at = (datetime.now(UTC) - timedelta(days=2)).isoformat()

    cache_content = {
        "state": {
            "documents": {
                note_id: {
                    "id": note_id,
                    "title": "Team Standup",
                    "created_at": created_at,
                    "updated_at": created_at,
                    "workspace_id": "engineering",
                    "panels": {
                        "enhanced_notes": {
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Action items discussed"}],
                                }
                            ]
                        },
                        "my_notes": {
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Follow up with design team"}],
                                }
                            ]
                        },
                    },
                    "people": ["Alice", "Bob"],
                }
            }
        }
    }

    return {
        "cache": json.dumps(cache_content)
    }


class TestGranolaIntegration:
    """Test Granola integration functionality."""

    def test_initialization(self, granola_config):
        """Test Granola integration initialization."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )

        assert integration.workspace_id == "all"
        assert integration.lookback_days == 7
        assert integration.integration_type == IntegrationType.GRANOLA

    def test_get_cache_path_macos(self, granola_config):
        """Test cache path detection on macOS."""
        with patch("sys.platform", "darwin"):
            integration = GranolaIntegration(
                config=granola_config,
                account_id="all",
                )

            expected_path = Path.home() / "Library/Application Support/Granola/cache-v3.json"
            assert integration.cache_path == expected_path

    def test_get_cache_path_unsupported_platform(self, granola_config):
        """Test cache path raises error on unsupported platform."""
        with patch("sys.platform", "freebsd"):
            with pytest.raises(ValueError, match="Unsupported platform"):
                GranolaIntegration(
                    config=granola_config,
                    account_id="all",
                        )

    @pytest.mark.asyncio
    async def test_authenticate_success(self, granola_config, sample_cache_data):
        """Test successful authentication."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )

        cache_content = json.dumps(sample_cache_data)

        with patch.object(Path, "exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=cache_content)):
                result = await integration.authenticate()
                assert result is True

    @pytest.mark.asyncio
    async def test_authenticate_missing_file(self, granola_config):
        """Test authentication fails when cache file missing."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )

        with patch.object(Path, "exists", return_value=False):
            from src.integrations.base import AuthenticationError

            with pytest.raises(AuthenticationError, match="Granola cache file not found"):
                await integration.authenticate()

    @pytest.mark.asyncio
    async def test_authenticate_invalid_json(self, granola_config):
        """Test authentication fails with invalid JSON."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )

        with patch.object(Path, "exists", return_value=True):
            with patch("builtins.open", mock_open(read_data="invalid json")):
                from src.integrations.base import AuthenticationError

                with pytest.raises(AuthenticationError, match="Failed to read Granola cache"):
                    await integration.authenticate()

    def test_prosemirror_to_text_simple(self, granola_config):
        """Test ProseMirror JSON to text conversion with simple content."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )

        panel_data = {
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "This is a test"}],
                }
            ]
        }

        result = integration._prosemirror_to_text(panel_data)
        assert "This is a test" in result

    def test_prosemirror_to_text_with_heading(self, granola_config):
        """Test ProseMirror conversion with headings."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )

        panel_data = {
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Important Section"}],
                }
            ]
        }

        result = integration._prosemirror_to_text(panel_data)
        assert "## Important Section" in result

    def test_prosemirror_to_text_with_list(self, granola_config):
        """Test ProseMirror conversion with bullet lists."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )

        panel_data = {
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "First item"}],
                                }
                            ],
                        }
                    ],
                }
            ]
        }

        result = integration._prosemirror_to_text(panel_data)
        assert "• First item" in result

    def test_prosemirror_to_text_empty(self, granola_config):
        """Test ProseMirror conversion with empty content."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )

        assert integration._prosemirror_to_text({}) == ""
        assert integration._prosemirror_to_text(None) == ""
        assert integration._prosemirror_to_text({"content": []}) == ""

    @patch("src.models.database.get_db_session")
    def test_filter_new_notes(self, mock_get_db_session, granola_config):
        """Test filtering of already-processed notes."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )

        notes = [
            {"id": "note1", "title": "Meeting 1"},
            {"id": "note2", "title": "Meeting 2"},
            {"id": "note3", "title": "Meeting 3"},
        ]

        # Mock database session and query to return note2 as already processed
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [("note2",)]
        mock_db.query.return_value = mock_query
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_get_db_session.return_value = mock_db

        new_notes = integration._filter_new_notes(notes)

        assert len(new_notes) == 2
        assert new_notes[0]["id"] == "note1"
        assert new_notes[1]["id"] == "note3"

    def test_extract_actionable_item(self, granola_config):
        """Test extraction of actionable item from note."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )

        note = {
            "id": "note123",
            "title": "Team Standup",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "workspace_id": "engineering",
            "panels": {
                "enhanced_notes": {
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Discussed project timeline"}],
                        }
                    ]
                }
            },
            "people": ["Alice", "Bob"],
            "url": "granola://note/note123",
        }

        item = integration._extract_actionable_item(note)

        assert item is not None
        assert item.type == ActionableItemType.DOCUMENT_REVIEW
        assert item.title == "Review meeting: Team Standup"
        assert "Discussed project timeline" in item.description
        assert "Alice, Bob" in item.description
        assert item.source == IntegrationType.GRANOLA
        assert item.source_reference == "note123"
        assert item.account_id == "all"
        assert "meeting-notes" in item.tags
        assert "granola" in item.tags

    def test_extract_actionable_item_with_object_people(self, granola_config):
        """Test extraction handles people as objects (not just strings)."""
        integration = GranolaIntegration(
            config=granola_config,
            account_id="all",
        )

        note = {
            "id": "note456",
            "title": "Design Review",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "workspace_id": "design",
            "panels": {},
            "people": [
                {"name": "Alice", "email": "alice@example.com"},
                {"name": "Bob", "email": "bob@example.com"},
            ],
            "url": "granola://note/note456",
        }

        item = integration._extract_actionable_item(note)

        assert item is not None
        assert "Alice, Bob" in item.description

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
            note_id="note789",
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
        assert added_note.note_id == "note789"
        assert added_note.note_title == "Sprint Planning"
        assert added_note.workspace_id == "all"
        assert added_note.account_id == "engineering"
        assert added_note.tasks_created_count == 2
