"""Tests for agent log service including detailed activity logging."""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.models.agent_log import AgentAction, AgentLog, LogLevel
from src.services.agent_log_service import AgentLogService


class TestAgentLogServiceBasics:
    """Tests for basic AgentLogService functionality."""

    def test_log_creates_entry(self, test_db_session):
        """Test that log creates a database entry."""
        service = AgentLogService(test_db_session)
        log_entry = service.log("Test message")

        assert log_entry.id is not None
        assert log_entry.message == "Test message"
        assert log_entry.level == LogLevel.INFO

    def test_log_with_action(self, test_db_session):
        """Test log with action type."""
        service = AgentLogService(test_db_session)
        log_entry = service.log(
            "Poll completed",
            action=AgentAction.POLL_EMAIL,
        )

        assert log_entry.action == AgentAction.POLL_EMAIL

    def test_log_with_details_dict(self, test_db_session):
        """Test log with dict details (JSON serialized)."""
        service = AgentLogService(test_db_session)
        details = {"key": "value", "count": 42}
        log_entry = service.log("Test", details=details)

        assert log_entry.details == json.dumps(details)

    def test_log_info(self, test_db_session):
        """Test log_info helper."""
        service = AgentLogService(test_db_session)
        log_entry = service.log_info("Info message")

        assert log_entry.level == LogLevel.INFO

    def test_log_warning(self, test_db_session):
        """Test log_warning helper."""
        service = AgentLogService(test_db_session)
        log_entry = service.log_warning("Warning message")

        assert log_entry.level == LogLevel.WARNING

    def test_log_error(self, test_db_session):
        """Test log_error helper."""
        service = AgentLogService(test_db_session)
        log_entry = service.log_error("Error message")

        assert log_entry.level == LogLevel.ERROR

    def test_log_debug(self, test_db_session):
        """Test log_debug helper."""
        service = AgentLogService(test_db_session)
        log_entry = service.log_debug("Debug message")

        assert log_entry.level == LogLevel.DEBUG


class TestFileAccessLogging:
    """Tests for file access logging."""

    def test_log_file_read(self, test_db_session):
        """Test logging a file read operation."""
        service = AgentLogService(test_db_session)
        log_entry = service.log_file_read(
            file_path="/path/to/file.txt",
            bytes_read=1024,
            purpose="Loading configuration",
        )

        assert log_entry.action == AgentAction.FILE_READ
        assert log_entry.level == LogLevel.DEBUG
        assert "/path/to/file.txt" in log_entry.message

        details = json.loads(log_entry.details)
        assert details["file_path"] == "/path/to/file.txt"
        assert details["bytes_read"] == 1024
        assert details["purpose"] == "Loading configuration"

    def test_log_file_write(self, test_db_session):
        """Test logging a file write operation."""
        service = AgentLogService(test_db_session)
        log_entry = service.log_file_write(
            file_path="/path/to/output.md",
            bytes_written=2048,
            purpose="Writing summary document",
        )

        assert log_entry.action == AgentAction.FILE_WRITE
        assert log_entry.level == LogLevel.DEBUG
        assert "/path/to/output.md" in log_entry.message

        details = json.loads(log_entry.details)
        assert details["file_path"] == "/path/to/output.md"
        assert details["bytes_written"] == 2048
        assert details["purpose"] == "Writing summary document"

    def test_log_file_read_minimal(self, test_db_session):
        """Test logging a file read with minimal parameters."""
        service = AgentLogService(test_db_session)
        log_entry = service.log_file_read(file_path="/path/to/file.txt")

        assert log_entry.action == AgentAction.FILE_READ
        details = json.loads(log_entry.details)
        assert details["bytes_read"] is None
        assert details["purpose"] is None


class TestHttpRequestLogging:
    """Tests for HTTP request logging."""

    def test_log_http_request_basic(self, test_db_session):
        """Test logging a basic HTTP request."""
        service = AgentLogService(test_db_session)
        log_entry = service.log_http_request(
            method="GET",
            url="https://api.example.com/data",
            status_code=200,
            duration_seconds=0.5,
            service="example",
            request_type="fetch_data",
        )

        assert log_entry.action == AgentAction.HTTP_REQUEST
        assert log_entry.level == LogLevel.DEBUG
        assert "GET" in log_entry.message
        assert "200" in log_entry.message

        details = json.loads(log_entry.details)
        assert details["method"] == "GET"
        assert details["status_code"] == 200
        assert details["duration_seconds"] == 0.5
        assert details["service"] == "example"
        assert details["request_type"] == "fetch_data"

    def test_log_http_request_sanitizes_url(self, test_db_session):
        """Test that HTTP logging sanitizes sensitive URL parameters."""
        service = AgentLogService(test_db_session)
        log_entry = service.log_http_request(
            method="POST",
            url="https://api.example.com/data?api_key=secret123&other=value",
            status_code=200,
        )

        details = json.loads(log_entry.details)
        # api_key should be redacted (may be URL-encoded as %5BREDACTED%5D)
        assert "secret123" not in details["url"]
        assert "REDACTED" in details["url"]  # Check without brackets due to URL encoding
        # other params should be preserved
        assert "other=value" in details["url"]

    def test_log_http_request_sanitizes_multiple_sensitive_params(self, test_db_session):
        """Test sanitization of multiple sensitive parameters."""
        service = AgentLogService(test_db_session)
        log_entry = service.log_http_request(
            method="GET",
            url="https://api.example.com/data?token=abc123&secret=xyz789&key=test",
        )

        details = json.loads(log_entry.details)
        assert "abc123" not in details["url"]
        assert "xyz789" not in details["url"]
        assert "test" not in details["url"]

    def test_log_http_request_minimal(self, test_db_session):
        """Test logging HTTP request with minimal parameters."""
        service = AgentLogService(test_db_session)
        log_entry = service.log_http_request(
            method="POST",
            url="https://api.example.com/endpoint",
        )

        assert log_entry.action == AgentAction.HTTP_REQUEST
        details = json.loads(log_entry.details)
        assert details["status_code"] is None
        assert details["duration_seconds"] is None

    def test_log_http_request_llm_service(self, test_db_session):
        """Test logging an LLM service HTTP request."""
        service = AgentLogService(test_db_session)
        log_entry = service.log_http_request(
            method="POST",
            url="https://api.openai.com/v1/chat/completions",
            status_code=200,
            duration_seconds=2.5,
            service="llm",
            request_type="task_extraction",
        )

        details = json.loads(log_entry.details)
        assert details["service"] == "llm"
        assert details["request_type"] == "task_extraction"


class TestDecisionLogging:
    """Tests for decision logging."""

    def test_log_decision_approved(self, test_db_session):
        """Test logging an approved decision."""
        service = AgentLogService(test_db_session)
        log_entry = service.log_decision(
            decision="auto_create_task",
            reasoning="Confidence 0.9 exceeds threshold 0.8",
            outcome="approved",
            context={"task_title": "Reply to email", "confidence": 0.9},
        )

        assert log_entry.action == AgentAction.DECISION
        assert log_entry.level == LogLevel.INFO
        assert "auto_create_task" in log_entry.message
        assert "approved" in log_entry.message

        details = json.loads(log_entry.details)
        assert details["decision"] == "auto_create_task"
        assert details["reasoning"] == "Confidence 0.9 exceeds threshold 0.8"
        assert details["outcome"] == "approved"
        assert details["context"]["confidence"] == 0.9

    def test_log_decision_rejected(self, test_db_session):
        """Test logging a rejected decision."""
        service = AgentLogService(test_db_session)
        log_entry = service.log_decision(
            decision="auto_create_task",
            reasoning="Autonomy level is SUGGEST - all tasks require manual approval",
            outcome="rejected",
        )

        details = json.loads(log_entry.details)
        assert details["outcome"] == "rejected"
        assert details["context"] is None

    def test_log_decision_with_complex_context(self, test_db_session):
        """Test decision logging with complex context."""
        service = AgentLogService(test_db_session)
        context = {
            "task_title": "Review PR #123",
            "confidence": 0.85,
            "autonomy_level": "auto_low",
            "source": "gmail",
            "tags": ["engineering", "review"],
        }
        log_entry = service.log_decision(
            decision="auto_create_task",
            reasoning="High confidence task from email",
            outcome="approved",
            context=context,
        )

        details = json.loads(log_entry.details)
        assert details["context"]["tags"] == ["engineering", "review"]


class TestActivitySummary:
    """Tests for activity summary with new action types."""

    def test_activity_summary_includes_new_actions(self, test_db_session):
        """Test that activity summary includes new action types."""
        service = AgentLogService(test_db_session)

        # Create various log entries
        service.log_file_read("/path/to/file", purpose="test")
        service.log_file_write("/path/to/output", purpose="test")
        service.log_http_request("GET", "https://example.com", status_code=200)
        service.log_decision("test_decision", "test reason", "approved")

        summary = service.get_activity_summary(hours=1)

        assert "by_action" in summary
        assert "file_read" in summary["by_action"]
        assert "file_write" in summary["by_action"]
        assert "http_request" in summary["by_action"]
        assert "decision" in summary["by_action"]


class TestGetLogs:
    """Tests for retrieving logs."""

    def test_get_logs_by_action(self, test_db_session):
        """Test filtering logs by action type."""
        service = AgentLogService(test_db_session)

        # Create different types of logs
        service.log_file_read("/path1")
        service.log_file_write("/path2")
        service.log_http_request("GET", "https://example.com")

        # Filter by FILE_READ action
        logs, total = service.get_logs(action=AgentAction.FILE_READ)

        assert total == 1
        assert all(log.action == AgentAction.FILE_READ for log in logs)

    def test_get_logs_by_level(self, test_db_session):
        """Test filtering logs by level."""
        service = AgentLogService(test_db_session)

        service.log_info("Info message")
        service.log_error("Error message")
        service.log_debug("Debug message")

        # Filter by ERROR level
        logs, total = service.get_logs(level=LogLevel.ERROR)

        assert total == 1
        assert logs[0].level == LogLevel.ERROR


class TestUrlSanitization:
    """Tests for URL sanitization."""

    def test_sanitize_url_preserves_path(self, test_db_session):
        """Test that URL path is preserved during sanitization."""
        service = AgentLogService(test_db_session)
        sanitized = service._sanitize_url(
            "https://api.example.com/v1/users/123?api_key=secret"
        )

        assert "/v1/users/123" in sanitized
        assert "secret" not in sanitized

    def test_sanitize_url_handles_no_query_params(self, test_db_session):
        """Test sanitization with no query parameters."""
        service = AgentLogService(test_db_session)
        url = "https://api.example.com/data"
        sanitized = service._sanitize_url(url)

        assert sanitized == url

    def test_sanitize_url_handles_malformed_url(self, test_db_session):
        """Test sanitization handles malformed URLs gracefully."""
        service = AgentLogService(test_db_session)
        # Very long URL should be truncated
        long_url = "https://example.com/" + "a" * 200
        sanitized = service._sanitize_url(long_url)

        # Should either be truncated or returned as-is
        assert len(sanitized) <= len(long_url)


class TestPollLogging:
    """Tests for poll logging."""

    def test_log_poll(self, test_db_session):
        """Test logging a poll operation."""
        service = AgentLogService(test_db_session)
        log_entry = service.log_poll(
            integration="gmail",
            items_found=5,
            duration_seconds=1.234,
        )

        assert log_entry.action == AgentAction.POLL_EMAIL
        assert "5" in log_entry.message
        assert "gmail" in log_entry.message

        details = json.loads(log_entry.details)
        assert details["items_found"] == 5
        assert details["duration_seconds"] == 1.23  # Rounded to 2 decimals

    def test_log_poll_slack(self, test_db_session):
        """Test logging a Slack poll."""
        service = AgentLogService(test_db_session)
        log_entry = service.log_poll(
            integration="slack",
            items_found=3,
            duration_seconds=0.5,
        )

        assert log_entry.action == AgentAction.POLL_SLACK


class TestTaskCreationLogging:
    """Tests for task creation logging."""

    def test_log_task_creation(self, test_db_session):
        """Test logging task creation."""
        service = AgentLogService(test_db_session)
        log_entry = service.log_task_creation(
            task_id=42,
            task_title="Review PR #123",
            source="gmail",
        )

        assert log_entry.action == AgentAction.CREATE_TASK
        assert log_entry.reference_type == "task"
        assert log_entry.reference_id == "42"
        assert "Review PR #123" in log_entry.message

    def test_log_task_creation_long_title(self, test_db_session):
        """Test task creation logging truncates long titles."""
        service = AgentLogService(test_db_session)
        long_title = "A" * 200
        log_entry = service.log_task_creation(
            task_id=1,
            task_title=long_title,
            source="email",
        )

        # Title should be truncated in message (max 100 chars)
        assert len(log_entry.message) < len(long_title) + 50


class TestLlmRequestLogging:
    """Tests for LLM request logging."""

    def test_log_llm_request(self, test_db_session):
        """Test logging an LLM request."""
        service = AgentLogService(test_db_session)
        log_entry = service.log_llm_request(
            message="Task extraction from gmail",
            tokens_used=150,
            model="gpt-4",
            details={"source": "gmail", "tasks_extracted": 3},
        )

        assert log_entry.action == AgentAction.LLM_REQUEST
        assert log_entry.tokens_used == 150
        assert log_entry.model_used == "gpt-4"

        details = json.loads(log_entry.details)
        assert details["tasks_extracted"] == 3
