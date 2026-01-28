"""Tests for LLM service."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.llm_service import (
    ExtractedTask,
    LLMError,
    LLMResponse,
    LLMService,
    PrioritySuggestion,
    ProductivityRecommendation,
)
from src.utils.config import LLMConfig


@pytest.fixture
def llm_config():
    """Create a test LLM config."""
    return LLMConfig(
        base_url="https://api.openai.com/v1",
        api_key="test-api-key",
        model="gpt-4",
        temperature=0.7,
        max_tokens=2000,
    )


@pytest.fixture
def llm_service(llm_config):
    """Create an LLM service with test config."""
    return LLMService(llm_config)


class TestLLMServiceInit:
    """Tests for LLMService initialization."""

    def test_init_with_config(self, llm_config):
        """Test initialization with config."""
        service = LLMService(llm_config)
        assert service.config == llm_config

    def test_init_configures_litellm(self, llm_config):
        """Test that litellm is configured."""
        with patch("src.services.llm_service.litellm") as mock_litellm:
            service = LLMService(llm_config)
            # Default OpenAI URL should not set api_base
            assert service.config.base_url == "https://api.openai.com/v1"


class TestExtractTasksFromText:
    """Tests for extract_tasks_from_text."""

    @pytest.mark.asyncio
    async def test_extract_single_task(self, llm_service):
        """Test extracting a single task."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps([
                        {
                            "title": "Review PR #123",
                            "description": "Code review needed",
                            "priority": "high",
                            "due_date": "2026-01-29T17:00:00",
                            "tags": ["code-review"],
                            "confidence": 0.9,
                        }
                    ])
                )
            )
        ]
        mock_response.usage = MagicMock(total_tokens=150)
        mock_response.model_dump = MagicMock(return_value={})

        with patch("src.services.llm_service.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response

            tasks = await llm_service.extract_tasks_from_text(
                text="Please review PR #123 by tomorrow",
                source="email",
            )

            assert len(tasks) == 1
            assert tasks[0].title == "Review PR #123"
            assert tasks[0].priority == "high"
            assert tasks[0].confidence == 0.9
            assert "code-review" in tasks[0].tags

    @pytest.mark.asyncio
    async def test_extract_multiple_tasks(self, llm_service):
        """Test extracting multiple tasks."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps([
                        {"title": "Task 1", "priority": "high", "confidence": 0.9},
                        {"title": "Task 2", "priority": "medium", "confidence": 0.8},
                        {"title": "Task 3", "priority": "low", "confidence": 0.7},
                    ])
                )
            )
        ]
        mock_response.usage = MagicMock(total_tokens=200)
        mock_response.model_dump = MagicMock(return_value={})

        with patch("src.services.llm_service.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response

            tasks = await llm_service.extract_tasks_from_text(
                text="Do task 1, task 2, and task 3",
                source="slack",
            )

            assert len(tasks) == 3
            assert tasks[0].title == "Task 1"
            assert tasks[1].title == "Task 2"
            assert tasks[2].title == "Task 3"

    @pytest.mark.asyncio
    async def test_extract_no_tasks(self, llm_service):
        """Test when no tasks are found."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="[]"))
        ]
        mock_response.usage = MagicMock(total_tokens=50)
        mock_response.model_dump = MagicMock(return_value={})

        with patch("src.services.llm_service.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response

            tasks = await llm_service.extract_tasks_from_text(
                text="Thanks for the update!",
                source="email",
            )

            assert len(tasks) == 0

    @pytest.mark.asyncio
    async def test_extract_with_context(self, llm_service):
        """Test extraction with additional context."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps([
                        {"title": "Follow up with client", "priority": "high", "confidence": 0.85}
                    ])
                )
            )
        ]
        mock_response.usage = MagicMock(total_tokens=100)
        mock_response.model_dump = MagicMock(return_value={})

        with patch("src.services.llm_service.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response

            tasks = await llm_service.extract_tasks_from_text(
                text="Please follow up",
                source="email",
                context="Important client meeting",
            )

            # Verify context was included in the call
            call_args = mock_acompletion.call_args
            messages = call_args.kwargs["messages"]
            assert any("Important client meeting" in str(m) for m in messages)

    @pytest.mark.asyncio
    async def test_extract_handles_markdown_response(self, llm_service):
        """Test extraction handles markdown code blocks."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='```json\n[{"title": "Task from markdown", "priority": "medium", "confidence": 0.8}]\n```'
                )
            )
        ]
        mock_response.usage = MagicMock(total_tokens=100)
        mock_response.model_dump = MagicMock(return_value={})

        with patch("src.services.llm_service.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response

            tasks = await llm_service.extract_tasks_from_text(
                text="Some text",
                source="slack",
            )

            assert len(tasks) == 1
            assert tasks[0].title == "Task from markdown"

    @pytest.mark.asyncio
    async def test_extract_handles_llm_error(self, llm_service):
        """Test extraction raises LLMError on API failure."""
        with patch("src.services.llm_service.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.side_effect = Exception("API Error")

            with pytest.raises(LLMError) as exc_info:
                await llm_service.extract_tasks_from_text(
                    text="Some text",
                    source="email",
                )

            assert "API Error" in str(exc_info.value)


class TestSuggestPriorityUpdates:
    """Tests for suggest_priority_updates."""

    @pytest.mark.asyncio
    async def test_suggest_priority_changes(self, llm_service):
        """Test suggesting priority changes."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps([
                        {
                            "task_id": 1,
                            "current_priority": "medium",
                            "suggested_priority": "high",
                            "reason": "Due in 2 days",
                            "confidence": 0.85,
                        }
                    ])
                )
            )
        ]
        mock_response.usage = MagicMock(total_tokens=150)
        mock_response.model_dump = MagicMock(return_value={})

        with patch("src.services.llm_service.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response

            suggestions = await llm_service.suggest_priority_updates([
                {"id": 1, "title": "Task 1", "priority": "medium", "due_date": "2026-01-30"},
                {"id": 2, "title": "Task 2", "priority": "low"},
            ])

            assert len(suggestions) == 1
            assert suggestions[0].task_id == 1
            assert suggestions[0].current_priority == "medium"
            assert suggestions[0].suggested_priority == "high"
            assert suggestions[0].reason == "Due in 2 days"

    @pytest.mark.asyncio
    async def test_suggest_no_changes_needed(self, llm_service):
        """Test when no priority changes are needed."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="[]"))
        ]
        mock_response.usage = MagicMock(total_tokens=50)
        mock_response.model_dump = MagicMock(return_value={})

        with patch("src.services.llm_service.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response

            suggestions = await llm_service.suggest_priority_updates([
                {"id": 1, "title": "Task 1", "priority": "high"},
            ])

            assert len(suggestions) == 0

    @pytest.mark.asyncio
    async def test_suggest_empty_task_list(self, llm_service):
        """Test with empty task list."""
        suggestions = await llm_service.suggest_priority_updates([])
        assert len(suggestions) == 0


class TestGenerateRecommendations:
    """Tests for generate_recommendations."""

    @pytest.mark.asyncio
    async def test_generate_recommendations(self, llm_service):
        """Test generating recommendations."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps([
                        {
                            "title": "Focus on overdue tasks",
                            "description": "You have 3 overdue tasks.",
                            "category": "focus",
                            "priority": "high",
                            "actionable_steps": ["Block time", "Start with oldest"],
                        },
                        {
                            "title": "Review task priorities",
                            "description": "Some tasks may need reprioritization.",
                            "category": "organization",
                            "priority": "medium",
                        },
                    ])
                )
            )
        ]
        mock_response.usage = MagicMock(total_tokens=250)
        mock_response.model_dump = MagicMock(return_value={})

        with patch("src.services.llm_service.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response

            recommendations = await llm_service.generate_recommendations(
                tasks=[
                    {"id": 1, "title": "Overdue task", "status": "pending", "priority": "high"},
                ],
                statistics={"active": 10, "overdue": 3, "due_today": 2},
            )

            assert len(recommendations) == 2
            assert recommendations[0].title == "Focus on overdue tasks"
            assert recommendations[0].category == "focus"
            assert recommendations[0].actionable_steps is not None
            assert len(recommendations[0].actionable_steps) == 2

    @pytest.mark.asyncio
    async def test_generate_recommendations_uses_statistics(self, llm_service):
        """Test that statistics are included in the prompt."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="[]"))
        ]
        mock_response.usage = MagicMock(total_tokens=100)
        mock_response.model_dump = MagicMock(return_value={})

        with patch("src.services.llm_service.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response

            await llm_service.generate_recommendations(
                tasks=[],
                statistics={"active": 25, "overdue": 5, "due_today": 3},
            )

            call_args = mock_acompletion.call_args
            messages = call_args.kwargs["messages"]
            # Check that statistics appear in the prompt
            prompt_text = str(messages)
            assert "25" in prompt_text  # active
            assert "5" in prompt_text  # overdue


class TestAnalyzeCalendarForOptimization:
    """Tests for analyze_calendar_for_optimization."""

    @pytest.mark.asyncio
    async def test_calendar_optimization(self, llm_service):
        """Test calendar optimization suggestions."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps([
                        {
                            "title": "Schedule focus time",
                            "description": "Block time for deep work.",
                            "category": "scheduling",
                            "priority": "high",
                            "actionable_steps": ["Block Tuesday 9-11am"],
                        }
                    ])
                )
            )
        ]
        mock_response.usage = MagicMock(total_tokens=150)
        mock_response.model_dump = MagicMock(return_value={})

        with patch("src.services.llm_service.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response

            recommendations = await llm_service.analyze_calendar_for_optimization(
                events=[
                    {"title": "Meeting 1", "start": "2026-01-28T10:00:00", "duration_minutes": 60},
                    {"title": "Meeting 2", "start": "2026-01-28T14:00:00", "duration_minutes": 30},
                ],
                tasks=[
                    {"id": 1, "title": "High priority task", "priority": "high"},
                ],
            )

            assert len(recommendations) == 1
            assert recommendations[0].category == "scheduling"


class TestParseJsonResponse:
    """Tests for _parse_json_response helper."""

    def test_parse_valid_json(self, llm_service):
        """Test parsing valid JSON."""
        result = llm_service._parse_json_response('[{"key": "value"}]')
        assert result == [{"key": "value"}]

    def test_parse_markdown_json(self, llm_service):
        """Test parsing JSON in markdown code block."""
        result = llm_service._parse_json_response('```json\n[{"key": "value"}]\n```')
        assert result == [{"key": "value"}]

    def test_parse_markdown_without_language(self, llm_service):
        """Test parsing markdown code block without language specifier."""
        result = llm_service._parse_json_response('```\n[{"key": "value"}]\n```')
        assert result == [{"key": "value"}]

    def test_parse_invalid_json(self, llm_service):
        """Test parsing invalid JSON returns empty list."""
        result = llm_service._parse_json_response("not valid json")
        assert result == []


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_llm_response_creation(self):
        """Test creating an LLMResponse."""
        response = LLMResponse(
            content="Test content",
            tokens_used=100,
            model="gpt-4",
            raw_response={"test": "data"},
        )

        assert response.content == "Test content"
        assert response.tokens_used == 100
        assert response.model == "gpt-4"


class TestExtractedTask:
    """Tests for ExtractedTask dataclass."""

    def test_extracted_task_defaults(self):
        """Test ExtractedTask default values."""
        task = ExtractedTask(title="Test task")

        assert task.title == "Test task"
        assert task.description is None
        assert task.priority == "medium"
        assert task.due_date is None
        assert task.tags is None
        assert task.confidence == 0.5

    def test_extracted_task_with_all_fields(self):
        """Test ExtractedTask with all fields."""
        due = datetime(2026, 1, 30)
        task = ExtractedTask(
            title="Complete task",
            description="Description",
            priority="high",
            due_date=due,
            tags=["urgent", "work"],
            confidence=0.95,
        )

        assert task.title == "Complete task"
        assert task.description == "Description"
        assert task.priority == "high"
        assert task.due_date == due
        assert task.tags == ["urgent", "work"]
        assert task.confidence == 0.95


class TestProductivityRecommendation:
    """Tests for ProductivityRecommendation dataclass."""

    def test_recommendation_defaults(self):
        """Test ProductivityRecommendation default values."""
        rec = ProductivityRecommendation(
            title="Test",
            description="Description",
            category="focus",
        )

        assert rec.title == "Test"
        assert rec.priority == "medium"
        assert rec.actionable_steps is None

    def test_recommendation_with_steps(self):
        """Test ProductivityRecommendation with actionable steps."""
        rec = ProductivityRecommendation(
            title="Focus on priorities",
            description="You have too many tasks",
            category="focus",
            priority="high",
            actionable_steps=["Step 1", "Step 2"],
        )

        assert len(rec.actionable_steps) == 2
