"""Unit tests for CLI commands."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from src.cli import cli, parse_due_date, format_due_date, get_priority_style, get_status_style
from src.models.task import TaskPriority, TaskSource, TaskStatus


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    config = MagicMock()
    config.agent.poll_interval_minutes = 15
    config.agent.autonomy_level = "suggest"
    config.agent.output_document_path = "~/summary.md"
    config.notifications.enabled = True
    config.notifications.sound = True
    config.notifications.on_overdue = True
    config.notifications.on_due_soon = True
    config.notifications.due_soon_hours = 4
    config.llm.model = "gpt-4"
    config.llm.api_key = "test-key"
    return config


@pytest.fixture
def mock_task():
    """Create a mock task."""
    task = MagicMock()
    task.id = 1
    task.title = "Test Task"
    task.description = "Test description"
    task.status = TaskStatus.PENDING
    task.priority = TaskPriority.HIGH
    task.priority_score = 75.0
    task.source = TaskSource.MANUAL
    task.due_date = datetime.now() + timedelta(days=1)
    task.created_at = datetime.now()
    task.updated_at = datetime.now()
    task.completed_at = None
    task.get_tags_list.return_value = ["urgent", "work"]
    return task


# --- Helper Function Tests ---


class TestParseDueDate:
    """Tests for due date parsing."""

    def test_parse_today(self):
        """Test parsing 'today'."""
        result = parse_due_date("today")
        assert result is not None
        assert result.date() == datetime.now().date()
        assert result.hour == 23
        assert result.minute == 59

    def test_parse_tomorrow(self):
        """Test parsing 'tomorrow'."""
        result = parse_due_date("tomorrow")
        assert result is not None
        expected = datetime.now() + timedelta(days=1)
        assert result.date() == expected.date()

    def test_parse_relative_days(self):
        """Test parsing '+Nd' format."""
        result = parse_due_date("+3d")
        assert result is not None
        expected = datetime.now() + timedelta(days=3)
        assert result.date() == expected.date()

    def test_parse_relative_weeks(self):
        """Test parsing '+Nw' format."""
        result = parse_due_date("+2w")
        assert result is not None
        expected = datetime.now() + timedelta(weeks=2)
        assert result.date() == expected.date()

    def test_parse_iso_date(self):
        """Test parsing YYYY-MM-DD format."""
        result = parse_due_date("2025-06-15")
        assert result is not None
        assert result.year == 2025
        assert result.month == 6
        assert result.day == 15

    def test_parse_datetime(self):
        """Test parsing YYYY-MM-DD HH:MM format."""
        result = parse_due_date("2025-06-15 14:30")
        assert result is not None
        assert result.hour == 14
        assert result.minute == 30

    def test_parse_invalid(self):
        """Test parsing invalid format."""
        result = parse_due_date("invalid-date")
        assert result is None

    def test_parse_case_insensitive(self):
        """Test that parsing is case insensitive."""
        result = parse_due_date("TODAY")
        assert result is not None
        assert result.date() == datetime.now().date()


class TestFormatDueDate:
    """Tests for due date formatting."""

    def test_format_none(self):
        """Test formatting None due date."""
        assert format_due_date(None) == "-"

    def test_format_overdue(self):
        """Test formatting overdue date."""
        past = datetime.now() - timedelta(days=2)
        result = format_due_date(past)
        assert "Overdue" in result

    def test_format_today(self):
        """Test formatting date due today."""
        today = datetime.now() + timedelta(hours=3)
        result = format_due_date(today)
        assert "Today" in result

    def test_format_tomorrow(self):
        """Test formatting date due tomorrow."""
        tomorrow = datetime.now() + timedelta(days=1, hours=12)
        result = format_due_date(tomorrow)
        assert "Tomorrow" in result

    def test_format_this_week(self):
        """Test formatting date due this week."""
        future = datetime.now() + timedelta(days=5)
        result = format_due_date(future)
        assert "days" in result


class TestStyleFunctions:
    """Tests for styling helper functions."""

    def test_priority_styles(self):
        """Test priority styling."""
        assert "red" in get_priority_style(TaskPriority.CRITICAL)
        assert "red" in get_priority_style(TaskPriority.HIGH)
        assert "yellow" in get_priority_style(TaskPriority.MEDIUM)
        assert "green" in get_priority_style(TaskPriority.LOW)

    def test_status_styles(self):
        """Test status styling."""
        assert "white" in get_status_style(TaskStatus.PENDING)
        assert "cyan" in get_status_style(TaskStatus.IN_PROGRESS)
        assert "green" in get_status_style(TaskStatus.COMPLETED)


# --- CLI Command Tests ---


class TestVersionCommand:
    """Tests for version command."""

    def test_version(self, runner):
        """Test --version flag."""
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "Personal Assistant" in result.output


class TestTasksCommands:
    """Tests for task management commands."""

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_db_session")
    def test_tasks_list(self, mock_session, mock_load_config, mock_init_db, runner, mock_config, mock_task):
        """Test tasks list command."""
        mock_load_config.return_value = mock_config
        
        # Setup mock session and service
        mock_db = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        
        with patch("src.cli.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_tasks.return_value = ([mock_task], 1)
            mock_service_class.return_value = mock_service
            
            result = runner.invoke(cli, ["tasks", "list"])
            
            assert result.exit_code == 0
            assert "Test Task" in result.output

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_db_session")
    def test_tasks_list_empty(self, mock_session, mock_load_config, mock_init_db, runner, mock_config):
        """Test tasks list with no tasks."""
        mock_load_config.return_value = mock_config
        
        mock_db = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        
        with patch("src.cli.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_tasks.return_value = ([], 0)
            mock_service_class.return_value = mock_service
            
            result = runner.invoke(cli, ["tasks", "list"])
            
            assert result.exit_code == 0
            assert "No tasks found" in result.output

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_db_session")
    def test_tasks_add(self, mock_session, mock_load_config, mock_init_db, runner, mock_config, mock_task):
        """Test tasks add command."""
        mock_load_config.return_value = mock_config
        
        mock_db = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        
        with patch("src.cli.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create_task.return_value = mock_task
            mock_service_class.return_value = mock_service
            
            result = runner.invoke(cli, ["tasks", "add", "New Task"])
            
            assert result.exit_code == 0
            assert "Created task" in result.output
            mock_service.create_task.assert_called_once()

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_db_session")
    def test_tasks_add_with_options(self, mock_session, mock_load_config, mock_init_db, runner, mock_config, mock_task):
        """Test tasks add with all options."""
        mock_load_config.return_value = mock_config
        
        mock_db = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        
        with patch("src.cli.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create_task.return_value = mock_task
            mock_service_class.return_value = mock_service
            
            result = runner.invoke(cli, [
                "tasks", "add", "New Task",
                "-d", "Description",
                "-p", "high",
                "-D", "tomorrow",
                "-t", "urgent",
                "-t", "work",
            ])
            
            assert result.exit_code == 0
            mock_service.create_task.assert_called_once()
            call_kwargs = mock_service.create_task.call_args[1]
            assert call_kwargs["priority"] == TaskPriority.HIGH
            assert call_kwargs["tags"] == ["urgent", "work"]

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_db_session")
    def test_tasks_complete(self, mock_session, mock_load_config, mock_init_db, runner, mock_config, mock_task):
        """Test tasks complete command."""
        mock_load_config.return_value = mock_config
        
        mock_db = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        
        with patch("src.cli.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_task.return_value = mock_task
            mock_service_class.return_value = mock_service
            
            result = runner.invoke(cli, ["tasks", "complete", "1"])
            
            assert result.exit_code == 0
            assert "Completed task" in result.output
            mock_service.update_task.assert_called_once()

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_db_session")
    def test_tasks_complete_not_found(self, mock_session, mock_load_config, mock_init_db, runner, mock_config):
        """Test tasks complete with nonexistent task."""
        mock_load_config.return_value = mock_config
        
        mock_db = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        
        with patch("src.cli.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_task.return_value = None
            mock_service_class.return_value = mock_service
            
            result = runner.invoke(cli, ["tasks", "complete", "999"])
            
            assert result.exit_code == 0
            assert "not found" in result.output

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_db_session")
    def test_tasks_delete(self, mock_session, mock_load_config, mock_init_db, runner, mock_config, mock_task):
        """Test tasks delete command with --yes flag."""
        mock_load_config.return_value = mock_config
        
        mock_db = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        
        with patch("src.cli.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_task.return_value = mock_task
            mock_service_class.return_value = mock_service
            
            result = runner.invoke(cli, ["tasks", "delete", "1", "--yes"])
            
            assert result.exit_code == 0
            assert "Deleted task" in result.output
            mock_service.delete_task.assert_called_once()

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_db_session")
    def test_tasks_show(self, mock_session, mock_load_config, mock_init_db, runner, mock_config, mock_task):
        """Test tasks show command."""
        mock_load_config.return_value = mock_config
        
        mock_db = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        
        with patch("src.cli.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_task.return_value = mock_task
            mock_service_class.return_value = mock_service
            
            result = runner.invoke(cli, ["tasks", "show", "1"])
            
            assert result.exit_code == 0
            assert "Test Task" in result.output
            assert "high" in result.output.lower()

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_db_session")
    def test_tasks_priority(self, mock_session, mock_load_config, mock_init_db, runner, mock_config, mock_task):
        """Test tasks priority command."""
        mock_load_config.return_value = mock_config
        
        mock_db = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        
        with patch("src.cli.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_prioritized_tasks.return_value = [mock_task]
            mock_service_class.return_value = mock_service
            
            result = runner.invoke(cli, ["tasks", "priority"])
            
            assert result.exit_code == 0
            assert "Test Task" in result.output

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_db_session")
    def test_tasks_stats(self, mock_session, mock_load_config, mock_init_db, runner, mock_config):
        """Test tasks stats command."""
        mock_load_config.return_value = mock_config
        
        mock_db = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        
        with patch("src.cli.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_statistics.return_value = {
                "total": 10,
                "active": 5,
                "overdue": 2,
                "due_today": 1,
                "due_this_week": 3,
                "by_status": {"pending": 5, "completed": 5},
            }
            mock_service_class.return_value = mock_service
            
            result = runner.invoke(cli, ["tasks", "stats"])
            
            assert result.exit_code == 0
            assert "10" in result.output
            assert "Overdue" in result.output


class TestSummaryCommand:
    """Tests for summary command."""

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_config")
    @patch("src.cli.get_db_session")
    def test_summary(self, mock_session, mock_get_config, mock_load_config, mock_init_db, runner, mock_config, mock_task):
        """Test summary command."""
        mock_load_config.return_value = mock_config
        mock_get_config.return_value = mock_config
        
        mock_db = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        
        with patch("src.cli.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_statistics.return_value = {
                "total": 10,
                "active": 5,
                "overdue": 2,
                "due_today": 1,
                "due_this_week": 3,
            }
            mock_service.get_prioritized_tasks.return_value = [mock_task]
            mock_service.get_overdue_tasks.return_value = []
            mock_service_class.return_value = mock_service
            
            result = runner.invoke(cli, ["summary"])
            
            assert result.exit_code == 0
            assert "Personal Assistant Summary" in result.output
            assert "Active Tasks" in result.output


class TestConfigCommands:
    """Tests for config commands."""

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    def test_config_show(self, mock_load_config, mock_init_db, runner, mock_config):
        """Test config show command."""
        mock_load_config.return_value = mock_config
        
        result = runner.invoke(cli, ["config", "show"])
        
        assert result.exit_code == 0
        assert "Agent" in result.output
        assert "15 minutes" in result.output

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    def test_config_path(self, mock_load_config, mock_init_db, runner, mock_config):
        """Test config path command."""
        mock_load_config.return_value = mock_config
        
        result = runner.invoke(cli, ["config", "path"])
        
        assert result.exit_code == 0

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    def test_config_init(self, mock_load_config, mock_init_db, runner, mock_config):
        """Test config init command."""
        mock_load_config.return_value = mock_config
        
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["config", "init"])
            
            assert result.exit_code == 0
            assert "Created" in result.output

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    def test_config_init_exists(self, mock_load_config, mock_init_db, runner, mock_config):
        """Test config init when file exists."""
        mock_load_config.return_value = mock_config
        
        with runner.isolated_filesystem():
            # Create existing config
            with open("config.yaml", "w") as f:
                f.write("existing: config")
            
            result = runner.invoke(cli, ["config", "init"])
            
            assert result.exit_code == 0
            assert "already exists" in result.output

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    def test_config_init_force(self, mock_load_config, mock_init_db, runner, mock_config):
        """Test config init --force overwrites."""
        mock_load_config.return_value = mock_config
        
        with runner.isolated_filesystem():
            # Create existing config
            with open("config.yaml", "w") as f:
                f.write("existing: config")
            
            result = runner.invoke(cli, ["config", "init", "--force"])
            
            assert result.exit_code == 0
            assert "Created" in result.output


class TestAgentCommands:
    """Tests for agent commands."""

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.agent.core.get_agent")
    def test_agent_status(self, mock_get_agent, mock_load_config, mock_init_db, runner, mock_config):
        """Test agent status command."""
        mock_load_config.return_value = mock_config
        
        mock_agent = MagicMock()
        mock_agent.get_status.return_value = {
            "is_running": False,
            "autonomy_level": "suggest",
            "started_at": None,
            "last_poll": None,
            "session_stats": {
                "tasks_created": 0,
                "items_processed": 0,
                "errors": 0,
            },
            "pending_suggestions": 0,
            "integrations": {
                "gmail": False,
                "slack": False,
            },
        }
        mock_get_agent.return_value = mock_agent
        
        result = runner.invoke(cli, ["agent", "status"])
        
        assert result.exit_code == 0
        assert "Agent Status" in result.output
        assert "Stopped" in result.output

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.agent.core.get_agent")
    def test_agent_stop_not_running(self, mock_get_agent, mock_load_config, mock_init_db, runner, mock_config):
        """Test agent stop when not running."""
        mock_load_config.return_value = mock_config
        
        mock_agent = MagicMock()
        mock_agent.state.is_running = False
        mock_get_agent.return_value = mock_agent
        
        result = runner.invoke(cli, ["agent", "stop"])
        
        assert result.exit_code == 0
        assert "not running" in result.output


class TestNotifyCommand:
    """Tests for notify command."""

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_config")
    @patch("src.services.notification_service.NotificationService")
    def test_notify(self, mock_service_class, mock_get_config, mock_load_config, mock_init_db, runner, mock_config):
        """Test notify command."""
        mock_load_config.return_value = mock_config
        mock_get_config.return_value = mock_config
        
        mock_service = MagicMock()
        mock_service.send.return_value = True
        mock_service_class.return_value = mock_service
        
        result = runner.invoke(cli, ["notify", "Test message"])
        
        assert result.exit_code == 0
        assert "sent" in result.output

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_config")
    @patch("src.services.notification_service.NotificationService")
    def test_notify_disabled(self, mock_service_class, mock_get_config, mock_load_config, mock_init_db, runner, mock_config):
        """Test notify when notifications disabled."""
        mock_load_config.return_value = mock_config
        mock_get_config.return_value = mock_config
        
        mock_service = MagicMock()
        mock_service.send.return_value = False
        mock_service_class.return_value = mock_service
        
        result = runner.invoke(cli, ["notify", "Test message"])
        
        assert result.exit_code == 0
        assert "disabled" in result.output or "not sent" in result.output


class TestTasksParseCommand:
    """Tests for tasks parse command."""

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_config")
    @patch("src.cli.get_db_session")
    def test_tasks_parse_creates_task(self, mock_session, mock_get_config, mock_load_config, mock_init_db, runner, mock_config, mock_task):
        """Test tasks parse creates task from extracted data."""
        mock_load_config.return_value = mock_config
        mock_get_config.return_value = mock_config

        mock_db = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)

        # Create mock extracted task
        from src.services.llm_service import ExtractedTask
        from datetime import datetime, timedelta

        extracted = ExtractedTask(
            title="Call John about quarterly review",
            description="Discuss Q4 results",
            priority="high",
            due_date=datetime.now() + timedelta(days=1),
            tags=["call", "work"],
            confidence=0.9,
        )

        with patch("src.cli.TaskService") as mock_service_class, \
             patch("src.services.llm_service.LLMService") as mock_llm_class:
            mock_service = MagicMock()
            mock_service.create_task.return_value = mock_task
            mock_service_class.return_value = mock_service

            # Mock LLM to return extracted task (async method)
            mock_llm = MagicMock()
            mock_llm.extract_tasks_from_text = AsyncMock(return_value=[extracted])
            mock_llm_class.return_value = mock_llm

            # Use --yes to skip confirmation
            result = runner.invoke(cli, [
                "tasks", "parse",
                "call John tomorrow about quarterly review, high priority",
                "--yes"
            ])

            assert result.exit_code == 0
            assert "Created task" in result.output
            mock_service.create_task.assert_called_once()

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_config")
    def test_tasks_parse_dry_run(self, mock_get_config, mock_load_config, mock_init_db, runner, mock_config):
        """Test tasks parse with --dry-run shows task but doesn't create."""
        mock_load_config.return_value = mock_config
        mock_get_config.return_value = mock_config

        from src.services.llm_service import ExtractedTask

        extracted = ExtractedTask(
            title="Send report by Friday",
            priority="medium",
            confidence=0.85,
        )

        with patch("src.services.llm_service.LLMService") as mock_llm_class:
            mock_llm = MagicMock()
            mock_llm.extract_tasks_from_text = AsyncMock(return_value=[extracted])
            mock_llm_class.return_value = mock_llm

            result = runner.invoke(cli, [
                "tasks", "parse",
                "send report by Friday",
                "--dry-run"
            ])

            assert result.exit_code == 0
            assert "Send report by Friday" in result.output
            assert "Dry run" in result.output

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_config")
    @patch("src.cli.get_db_session")
    def test_tasks_parse_no_extraction_creates_simple_task(self, mock_session, mock_get_config, mock_load_config, mock_init_db, runner, mock_config, mock_task):
        """Test tasks parse creates simple task when LLM extracts nothing."""
        mock_load_config.return_value = mock_config
        mock_get_config.return_value = mock_config

        mock_db = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)

        with patch("src.cli.TaskService") as mock_service_class, \
             patch("src.services.llm_service.LLMService") as mock_llm_class:
            mock_service = MagicMock()
            mock_service.create_task.return_value = mock_task
            mock_service_class.return_value = mock_service

            # Mock LLM to return empty list (async method)
            mock_llm = MagicMock()
            mock_llm.extract_tasks_from_text = AsyncMock(return_value=[])
            mock_llm_class.return_value = mock_llm

            # Use --yes to auto-confirm simple task creation
            result = runner.invoke(cli, [
                "tasks", "parse",
                "some text that fails parsing",
                "--yes"
            ])

            assert result.exit_code == 0
            assert "No tasks could be extracted" in result.output
            assert "Created task" in result.output

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_config")
    def test_tasks_parse_no_api_key(self, mock_get_config, mock_load_config, mock_init_db, runner):
        """Test tasks parse shows error when API key not configured."""
        mock_config = MagicMock()
        mock_config.llm.api_key = ""  # No API key
        mock_load_config.return_value = mock_config
        mock_get_config.return_value = mock_config

        result = runner.invoke(cli, ["tasks", "parse", "some task"])

        assert result.exit_code == 0
        assert "API key not configured" in result.output

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_config")
    def test_tasks_parse_displays_extracted_details(self, mock_get_config, mock_load_config, mock_init_db, runner, mock_config):
        """Test tasks parse displays all extracted task details."""
        mock_load_config.return_value = mock_config
        mock_get_config.return_value = mock_config

        from src.services.llm_service import ExtractedTask
        from datetime import datetime, timedelta

        extracted = ExtractedTask(
            title="Fix production bug",
            description="Critical issue in payment module",
            priority="critical",
            due_date=datetime.now() + timedelta(hours=4),
            tags=["bug", "urgent"],
            confidence=0.95,
        )

        with patch("src.services.llm_service.LLMService") as mock_llm_class:
            mock_llm = MagicMock()
            mock_llm.extract_tasks_from_text = AsyncMock(return_value=[extracted])
            mock_llm_class.return_value = mock_llm

            result = runner.invoke(cli, [
                "tasks", "parse",
                "urgent: fix production bug ASAP",
                "--dry-run"
            ])

            assert result.exit_code == 0
            assert "Fix production bug" in result.output
            assert "CRITICAL" in result.output
            assert "95%" in result.output
            assert "#bug" in result.output or "#urgent" in result.output


class TestTasksDueCommand:
    """Tests for the tasks due command."""

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_config")
    @patch("src.cli.get_db_session")
    def test_tasks_due_simple_format(self, mock_session, mock_get_config, mock_load_config, mock_init_db, runner, mock_config, mock_task):
        """Test tasks due with simple date format like 'tomorrow'."""
        mock_load_config.return_value = mock_config
        mock_get_config.return_value = mock_config

        mock_db = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)

        with patch("src.cli.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_task.return_value = mock_task
            mock_service_class.return_value = mock_service

            result = runner.invoke(cli, [
                "tasks", "due", "1", "tomorrow", "--yes"
            ])

            assert result.exit_code == 0
            assert "Updated due date" in result.output
            mock_service.update_task.assert_called_once()

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_config")
    @patch("src.cli.get_db_session")
    def test_tasks_due_llm_parsing(self, mock_session, mock_get_config, mock_load_config, mock_init_db, runner, mock_config, mock_task):
        """Test tasks due with complex date that requires LLM parsing."""
        mock_load_config.return_value = mock_config
        mock_get_config.return_value = mock_config

        mock_db = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)

        from datetime import datetime, timedelta
        parsed_date = datetime.now() + timedelta(days=5)

        with patch("src.cli.TaskService") as mock_service_class, \
             patch("src.services.llm_service.LLMService") as mock_llm_class:
            mock_service = MagicMock()
            mock_service.get_task.return_value = mock_task
            mock_service_class.return_value = mock_service

            mock_llm = MagicMock()
            mock_llm.parse_date = AsyncMock(return_value=parsed_date)
            mock_llm_class.return_value = mock_llm

            result = runner.invoke(cli, [
                "tasks", "due", "1", "next Friday", "--yes"
            ])

            assert result.exit_code == 0
            assert "Updated due date" in result.output

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_config")
    @patch("src.cli.get_db_session")
    def test_tasks_due_clear(self, mock_session, mock_get_config, mock_load_config, mock_init_db, runner, mock_config, mock_task):
        """Test tasks due --clear removes the due date."""
        mock_load_config.return_value = mock_config
        mock_get_config.return_value = mock_config

        mock_db = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)

        with patch("src.cli.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_task.return_value = mock_task
            mock_service_class.return_value = mock_service

            result = runner.invoke(cli, [
                "tasks", "due", "1", "--clear", "--yes"
            ])

            assert result.exit_code == 0
            assert "Updated due date" in result.output
            # Verify update was called with due_date=None
            mock_service.update_task.assert_called_once()
            call_kwargs = mock_service.update_task.call_args[1]
            assert call_kwargs["due_date"] is None

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_config")
    @patch("src.cli.get_db_session")
    def test_tasks_due_task_not_found(self, mock_session, mock_get_config, mock_load_config, mock_init_db, runner, mock_config):
        """Test tasks due shows error when task not found."""
        mock_load_config.return_value = mock_config
        mock_get_config.return_value = mock_config

        mock_db = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)

        with patch("src.cli.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_task.return_value = None  # Task not found
            mock_service_class.return_value = mock_service

            result = runner.invoke(cli, [
                "tasks", "due", "999", "tomorrow"
            ])

            assert result.exit_code == 0
            assert "not found" in result.output

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_config")
    @patch("src.cli.get_db_session")
    def test_tasks_due_confirmation_cancelled(self, mock_session, mock_get_config, mock_load_config, mock_init_db, runner, mock_config, mock_task):
        """Test tasks due cancellation when user declines confirmation."""
        mock_load_config.return_value = mock_config
        mock_get_config.return_value = mock_config

        mock_db = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)

        with patch("src.cli.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_task.return_value = mock_task
            mock_service_class.return_value = mock_service

            # User types 'n' to decline
            result = runner.invoke(cli, [
                "tasks", "due", "1", "tomorrow"
            ], input="n\n")

            assert result.exit_code == 0
            assert "Cancelled" in result.output
            mock_service.update_task.assert_not_called()

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    def test_tasks_due_no_date_or_clear(self, mock_load_config, mock_init_db, runner, mock_config):
        """Test tasks due requires either date or --clear."""
        mock_load_config.return_value = mock_config

        result = runner.invoke(cli, [
            "tasks", "due", "1"
        ])

        assert result.exit_code == 0
        assert "Please provide a date" in result.output

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    def test_tasks_due_both_date_and_clear(self, mock_load_config, mock_init_db, runner, mock_config):
        """Test tasks due rejects both date and --clear."""
        mock_load_config.return_value = mock_config

        result = runner.invoke(cli, [
            "tasks", "due", "1", "tomorrow", "--clear"
        ])

        assert result.exit_code == 0
        assert "Cannot specify both" in result.output

    @patch("src.cli.init_db")
    @patch("src.cli.load_config")
    @patch("src.cli.get_config")
    @patch("src.cli.get_db_session")
    def test_tasks_due_no_api_key_complex_date(self, mock_session, mock_get_config, mock_load_config, mock_init_db, runner, mock_task):
        """Test tasks due shows help when complex date used without API key."""
        mock_config = MagicMock()
        mock_config.llm.api_key = ""  # No API key
        mock_load_config.return_value = mock_config
        mock_get_config.return_value = mock_config

        mock_db = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)

        with patch("src.cli.TaskService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_task.return_value = mock_task
            mock_service_class.return_value = mock_service

            # "next Friday" can't be parsed without LLM
            result = runner.invoke(cli, [
                "tasks", "due", "1", "next Friday"
            ])

            assert result.exit_code == 0
            assert "Could not parse date" in result.output
            assert "configure an LLM API key" in result.output
