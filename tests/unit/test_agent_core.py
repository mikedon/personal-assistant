"""Tests for autonomous agent core."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.core import (
    AgentState,
    AutonomousAgent,
    AutonomyLevel,
    PollResult,
    get_agent,
    reset_agent,
)
from src.integrations.base import ActionableItem, ActionableItemType, IntegrationType
from src.services.llm_service import ExtractedTask
from src.utils.config import AgentConfig, Config, LLMConfig


@pytest.fixture
def test_config():
    """Create a test configuration."""
    return Config(
        llm=LLMConfig(api_key="test-key", model="gpt-4"),
        agent=AgentConfig(
            poll_interval_minutes=15,
            autonomy_level="suggest",
            output_document_path="/tmp/test_summary.md",
        ),
    )


@pytest.fixture
def agent(test_config, test_db_session):
    """Create an agent for testing."""
    reset_agent()
    return AutonomousAgent(test_config)


class TestAutonomyLevel:
    """Tests for AutonomyLevel enum."""

    def test_autonomy_levels(self):
        """Test all autonomy levels exist."""
        assert AutonomyLevel.SUGGEST.value == "suggest"
        assert AutonomyLevel.AUTO_LOW.value == "auto_low"
        assert AutonomyLevel.AUTO.value == "auto"
        assert AutonomyLevel.FULL.value == "full"

    def test_autonomy_from_string(self):
        """Test creating autonomy level from string."""
        assert AutonomyLevel("suggest") == AutonomyLevel.SUGGEST
        assert AutonomyLevel("auto") == AutonomyLevel.AUTO


class TestAgentState:
    """Tests for AgentState dataclass."""

    def test_default_state(self):
        """Test default agent state."""
        state = AgentState()
        assert state.is_running is False
        assert state.last_poll is None
        assert state.tasks_created_session == 0
        assert state.items_processed_session == 0
        assert state.errors_session == 0

    def test_state_with_values(self):
        """Test agent state with values."""
        now = datetime.now()
        state = AgentState(
            is_running=True,
            last_poll=now,
            tasks_created_session=5,
        )
        assert state.is_running is True
        assert state.last_poll == now
        assert state.tasks_created_session == 5


class TestPollResult:
    """Tests for PollResult dataclass."""

    def test_default_poll_result(self):
        """Test default poll result."""
        result = PollResult(integration=IntegrationType.GMAIL)
        assert result.integration == IntegrationType.GMAIL
        assert result.items_found == []
        assert result.tasks_created == []
        assert result.duration_seconds == 0.0
        assert result.error is None

    def test_poll_result_with_items(self):
        """Test poll result with items."""
        items = [
            ActionableItem(
                type=ActionableItemType.EMAIL_REPLY_NEEDED,
                title="Test email",
                source=IntegrationType.GMAIL,
            )
        ]
        result = PollResult(
            integration=IntegrationType.GMAIL,
            items_found=items,
            tasks_created=[1, 2],
            duration_seconds=1.5,
        )
        assert len(result.items_found) == 1
        assert len(result.tasks_created) == 2


class TestAutonomousAgentInit:
    """Tests for AutonomousAgent initialization."""

    def test_init_with_config(self, test_config):
        """Test agent initialization."""
        agent = AutonomousAgent(test_config)
        assert agent.config == test_config
        assert agent.state.is_running is False
        assert agent.autonomy_level == AutonomyLevel.SUGGEST

    def test_init_sets_autonomy_from_config(self, test_config):
        """Test autonomy level from config."""
        test_config.agent.autonomy_level = "auto"
        agent = AutonomousAgent(test_config)
        assert agent.autonomy_level == AutonomyLevel.AUTO


class TestAutonomyLevelProperty:
    """Tests for autonomy level property."""

    def test_set_autonomy_level_enum(self, agent):
        """Test setting autonomy level with enum."""
        agent.autonomy_level = AutonomyLevel.AUTO
        assert agent.autonomy_level == AutonomyLevel.AUTO

    def test_set_autonomy_level_string(self, agent):
        """Test setting autonomy level with string."""
        agent.autonomy_level = "full"
        assert agent.autonomy_level == AutonomyLevel.FULL

    def test_invalid_autonomy_level(self, agent):
        """Test invalid autonomy level raises error."""
        with pytest.raises(ValueError):
            agent.autonomy_level = "invalid"


class TestShouldAutoCreateTask:
    """Tests for _should_auto_create_task."""

    def test_suggest_mode_never_auto_creates(self, agent):
        """Test SUGGEST mode never auto-creates tasks."""
        agent.autonomy_level = AutonomyLevel.SUGGEST
        task = ExtractedTask(title="Test", confidence=0.99)
        assert agent._should_auto_create_task(task) is False

    def test_auto_low_mode_high_confidence(self, agent):
        """Test AUTO_LOW mode creates high confidence tasks."""
        agent.autonomy_level = AutonomyLevel.AUTO_LOW
        
        high_confidence = ExtractedTask(title="Test", confidence=0.85)
        assert agent._should_auto_create_task(high_confidence) is True
        
        low_confidence = ExtractedTask(title="Test", confidence=0.75)
        assert agent._should_auto_create_task(low_confidence) is False

    def test_auto_mode_creates_all(self, agent):
        """Test AUTO mode creates all tasks."""
        agent.autonomy_level = AutonomyLevel.AUTO
        task = ExtractedTask(title="Test", confidence=0.5)
        assert agent._should_auto_create_task(task) is True

    def test_full_mode_creates_all(self, agent):
        """Test FULL mode creates all tasks."""
        agent.autonomy_level = AutonomyLevel.FULL
        task = ExtractedTask(title="Test", confidence=0.3)
        assert agent._should_auto_create_task(task) is True


class TestGetStatus:
    """Tests for get_status."""

    def test_get_status_not_running(self, agent):
        """Test status when not running."""
        status = agent.get_status()
        assert status["is_running"] is False
        assert status["autonomy_level"] == "suggest"
        assert status["last_poll"] is None
        assert status["session_stats"]["tasks_created"] == 0

    def test_get_status_includes_integrations(self, agent):
        """Test status includes integration info."""
        status = agent.get_status()
        assert "integrations" in status
        assert "gmail" in status["integrations"]
        assert "slack" in status["integrations"]


class TestPendingSuggestions:
    """Tests for pending suggestions management."""

    def test_get_pending_suggestions_empty(self, agent):
        """Test getting empty suggestions."""
        suggestions = agent.get_pending_suggestions()
        assert suggestions == []

    def test_clear_pending_suggestions(self, agent):
        """Test clearing suggestions."""
        agent._pending_suggestions = [
            ExtractedTask(title="Test 1"),
            ExtractedTask(title="Test 2"),
        ]
        agent.clear_pending_suggestions()
        assert len(agent._pending_suggestions) == 0

    def test_get_pending_suggestions_returns_copy(self, agent):
        """Test that get_pending_suggestions returns a copy."""
        task = ExtractedTask(title="Test")
        agent._pending_suggestions = [task]
        
        suggestions = agent.get_pending_suggestions()
        suggestions.append(ExtractedTask(title="New"))
        
        assert len(agent._pending_suggestions) == 1


class TestGetAgent:
    """Tests for get_agent singleton."""

    def test_get_agent_creates_singleton(self, test_config):
        """Test get_agent creates a singleton."""
        reset_agent()
        agent1 = get_agent(test_config)
        agent2 = get_agent()
        assert agent1 is agent2

    def test_reset_agent(self, test_config):
        """Test reset_agent clears singleton."""
        agent1 = get_agent(test_config)
        reset_agent()
        agent2 = get_agent(test_config)
        assert agent1 is not agent2


class TestProcessActionableItems:
    """Tests for _process_actionable_items."""

    @pytest.mark.asyncio
    async def test_process_items_suggest_mode(self, agent, test_db_session):
        """Test processing items in SUGGEST mode adds to pending."""
        agent.autonomy_level = AutonomyLevel.SUGGEST
        
        items = [
            ActionableItem(
                type=ActionableItemType.EMAIL_REPLY_NEEDED,
                title="Reply to email",
                description="Important email",
                source=IntegrationType.GMAIL,
                source_reference="msg_123",
            )
        ]
        
        mock_extracted = [ExtractedTask(title="Reply to email", confidence=0.9)]
        
        with patch.object(agent.llm_service, "extract_tasks_from_text", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = mock_extracted
            
            with patch("src.agent.core.get_db_session") as mock_db:
                mock_db.return_value.__enter__ = MagicMock(return_value=test_db_session)
                mock_db.return_value.__exit__ = MagicMock(return_value=False)
                
                created, suggested = await agent._process_actionable_items(items, IntegrationType.GMAIL)
        
        assert len(created) == 0
        assert len(suggested) == 1
        assert len(agent._pending_suggestions) == 1

    @pytest.mark.asyncio
    async def test_process_items_auto_mode_creates_tasks(self, agent, test_db_session):
        """Test processing items in AUTO mode creates tasks."""
        agent.autonomy_level = AutonomyLevel.AUTO
        
        items = [
            ActionableItem(
                type=ActionableItemType.EMAIL_REPLY_NEEDED,
                title="Reply to email",
                source=IntegrationType.GMAIL,
                source_reference="msg_123",
            )
        ]
        
        mock_extracted = [ExtractedTask(title="Reply to email", confidence=0.9)]
        
        with patch.object(agent.llm_service, "extract_tasks_from_text", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = mock_extracted
            
            with patch("src.agent.core.get_db_session") as mock_db:
                mock_session = MagicMock()
                mock_db.return_value.__enter__ = MagicMock(return_value=mock_session)
                mock_db.return_value.__exit__ = MagicMock(return_value=False)
                
                with patch("src.agent.core.TaskService") as mock_task_service:
                    mock_task = MagicMock()
                    mock_task.id = 1
                    mock_task.title = "Reply to email"
                    mock_task_service.return_value.create_task.return_value = mock_task
                    
                    with patch("src.agent.core.AgentLogService"):
                        created, suggested = await agent._process_actionable_items(items, IntegrationType.GMAIL)
        
        assert len(created) == 1
        assert len(suggested) == 0


class TestAgentStartStop:
    """Tests for agent start/stop."""

    @pytest.mark.asyncio
    async def test_start_sets_running(self, agent):
        """Test start sets is_running."""
        mock_db_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_db_session)
        mock_context.__exit__ = MagicMock(return_value=False)
        
        with patch.object(agent, "_poll_cycle", new_callable=AsyncMock):
            with patch("src.agent.core.get_db_session", return_value=mock_context):
                with patch("src.agent.core.AgentLogService"):
                    await agent.start()
        
        assert agent.state.is_running is True
        assert agent.state.started_at is not None
        
        # Cleanup - also mock stop's db access
        agent._scheduler = MagicMock()
        with patch("src.agent.core.get_db_session", return_value=mock_context):
            with patch("src.agent.core.AgentLogService"):
                await agent.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_running(self, agent):
        """Test stop clears is_running."""
        agent.state.is_running = True
        agent._scheduler = MagicMock()
        
        mock_db_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_db_session)
        mock_context.__exit__ = MagicMock(return_value=False)
        
        with patch("src.agent.core.get_db_session", return_value=mock_context):
            with patch("src.agent.core.AgentLogService"):
                await agent.stop()
        
        assert agent.state.is_running is False

    @pytest.mark.asyncio
    async def test_start_when_already_running(self, agent):
        """Test start when already running does nothing."""
        agent.state.is_running = True
        original_started_at = agent.state.started_at
        
        await agent.start()
        
        assert agent.state.started_at == original_started_at

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, agent):
        """Test stop when not running does nothing."""
        agent.state.is_running = False
        await agent.stop()
        assert agent.state.is_running is False


class TestPollNow:
    """Tests for poll_now."""

    @pytest.mark.asyncio
    async def test_poll_now_triggers_poll_cycle(self, agent):
        """Test poll_now triggers _poll_cycle."""
        with patch.object(agent, "_poll_cycle", new_callable=AsyncMock) as mock_poll:
            mock_poll.return_value = []
            results = await agent.poll_now()
            mock_poll.assert_called_once()


class TestRecommendationsNow:
    """Tests for generate_recommendations_now."""

    @pytest.mark.asyncio
    async def test_recommendations_now_triggers_cycle(self, agent):
        """Test generate_recommendations_now triggers _recommendation_cycle."""
        with patch.object(agent, "_recommendation_cycle", new_callable=AsyncMock) as mock_rec:
            mock_rec.return_value = []
            results = await agent.generate_recommendations_now()
            mock_rec.assert_called_once()
