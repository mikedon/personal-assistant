"""Agent log service for tracking agent activity and decisions."""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.agent_log import AgentAction, AgentLog, LogLevel

logger = logging.getLogger(__name__)


class AgentLogService:
    """Service for logging and querying agent activity."""

    def __init__(self, db: Session):
        """Initialize the agent log service.

        Args:
            db: Database session
        """
        self.db = db

    def log(
        self,
        message: str,
        *,
        level: LogLevel = LogLevel.INFO,
        action: AgentAction | None = None,
        details: dict[str, Any] | str | None = None,
        tokens_used: int | None = None,
        model_used: str | None = None,
        reference_type: str | None = None,
        reference_id: str | None = None,
    ) -> AgentLog:
        """Create a log entry.

        Args:
            message: Log message
            level: Log level (DEBUG, INFO, WARNING, ERROR)
            action: Type of agent action
            details: Additional details (dict will be JSON serialized)
            tokens_used: LLM tokens used (if applicable)
            model_used: LLM model used (if applicable)
            reference_type: Type of related entity (task, email, etc.)
            reference_id: ID of related entity

        Returns:
            The created AgentLog entry
        """
        # Convert dict details to JSON string
        if isinstance(details, dict):
            details = json.dumps(details)

        log_entry = AgentLog(
            level=level,
            action=action,
            message=message,
            details=details,
            tokens_used=tokens_used,
            model_used=model_used,
            reference_type=reference_type,
            reference_id=reference_id,
        )

        self.db.add(log_entry)
        self.db.commit()
        self.db.refresh(log_entry)

        # Also log to Python logger
        log_method = getattr(logger, level.value)
        log_method(f"[{action.value if action else 'GENERAL'}] {message}")

        return log_entry

    def log_info(self, message: str, **kwargs) -> AgentLog:
        """Log an info message."""
        return self.log(message, level=LogLevel.INFO, **kwargs)

    def log_warning(self, message: str, **kwargs) -> AgentLog:
        """Log a warning message."""
        return self.log(message, level=LogLevel.WARNING, **kwargs)

    def log_error(self, message: str, **kwargs) -> AgentLog:
        """Log an error message."""
        return self.log(message, level=LogLevel.ERROR, **kwargs)

    def log_debug(self, message: str, **kwargs) -> AgentLog:
        """Log a debug message."""
        return self.log(message, level=LogLevel.DEBUG, **kwargs)

    def log_llm_request(
        self,
        message: str,
        tokens_used: int,
        model: str,
        details: dict[str, Any] | None = None,
    ) -> AgentLog:
        """Log an LLM request with token usage.

        Args:
            message: Description of the LLM request
            tokens_used: Total tokens used
            model: Model used for the request
            details: Additional request details

        Returns:
            The created AgentLog entry
        """
        return self.log(
            message,
            level=LogLevel.INFO,
            action=AgentAction.LLM_REQUEST,
            tokens_used=tokens_used,
            model_used=model,
            details=details,
        )

    def log_task_creation(
        self,
        task_id: int,
        task_title: str,
        source: str,
    ) -> AgentLog:
        """Log automatic task creation.

        Args:
            task_id: ID of the created task
            task_title: Title of the task
            source: Source of the task (email, slack, etc.)

        Returns:
            The created AgentLog entry
        """
        return self.log(
            f"Created task from {source}: {task_title[:100]}",
            level=LogLevel.INFO,
            action=AgentAction.CREATE_TASK,
            reference_type="task",
            reference_id=str(task_id),
            details={"source": source, "title": task_title},
        )

    def log_poll(
        self,
        integration: str,
        items_found: int,
        duration_seconds: float,
    ) -> AgentLog:
        """Log an integration poll.

        Args:
            integration: Integration name (gmail, slack, etc.)
            items_found: Number of actionable items found
            duration_seconds: Duration of the poll

        Returns:
            The created AgentLog entry
        """
        action_map = {
            "gmail": AgentAction.POLL_EMAIL,
            "email": AgentAction.POLL_EMAIL,
            "slack": AgentAction.POLL_SLACK,
            "calendar": AgentAction.POLL_CALENDAR,
            "drive": AgentAction.POLL_DRIVE,
        }
        action = action_map.get(integration.lower())

        return self.log(
            f"Polled {integration}: found {items_found} actionable items",
            level=LogLevel.INFO,
            action=action,
            details={
                "integration": integration,
                "items_found": items_found,
                "duration_seconds": round(duration_seconds, 2),
            },
        )

    def log_file_read(
        self,
        file_path: str,
        bytes_read: int | None = None,
        purpose: str | None = None,
    ) -> AgentLog:
        """Log a file read operation.

        Args:
            file_path: Path to the file being read
            bytes_read: Number of bytes read (if known)
            purpose: Why the file is being read

        Returns:
            The created AgentLog entry
        """
        return self.log(
            f"Read file: {file_path}",
            level=LogLevel.DEBUG,
            action=AgentAction.FILE_READ,
            details={
                "file_path": file_path,
                "bytes_read": bytes_read,
                "purpose": purpose,
            },
        )

    def log_file_write(
        self,
        file_path: str,
        bytes_written: int | None = None,
        purpose: str | None = None,
    ) -> AgentLog:
        """Log a file write operation.

        Args:
            file_path: Path to the file being written
            bytes_written: Number of bytes written (if known)
            purpose: Why the file is being written

        Returns:
            The created AgentLog entry
        """
        return self.log(
            f"Wrote file: {file_path}",
            level=LogLevel.DEBUG,
            action=AgentAction.FILE_WRITE,
            details={
                "file_path": file_path,
                "bytes_written": bytes_written,
                "purpose": purpose,
            },
        )

    def log_http_request(
        self,
        method: str,
        url: str,
        status_code: int | None = None,
        duration_seconds: float | None = None,
        service: str | None = None,
        request_type: str | None = None,
    ) -> AgentLog:
        """Log an HTTP request.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL (may be sanitized)
            status_code: Response status code
            duration_seconds: Request duration
            service: Service name (e.g., 'openai', 'gmail', 'slack')
            request_type: Type of request (e.g., 'llm_completion', 'fetch_emails')

        Returns:
            The created AgentLog entry
        """
        # Sanitize URL to avoid logging sensitive data
        sanitized_url = self._sanitize_url(url)

        status_str = f" -> {status_code}" if status_code else ""
        duration_str = f" ({duration_seconds:.2f}s)" if duration_seconds else ""

        return self.log(
            f"HTTP {method} {sanitized_url}{status_str}{duration_str}",
            level=LogLevel.DEBUG,
            action=AgentAction.HTTP_REQUEST,
            details={
                "method": method,
                "url": sanitized_url,
                "status_code": status_code,
                "duration_seconds": round(duration_seconds, 3) if duration_seconds else None,
                "service": service,
                "request_type": request_type,
            },
        )

    def log_decision(
        self,
        decision: str,
        reasoning: str,
        outcome: str,
        context: dict[str, Any] | None = None,
    ) -> AgentLog:
        """Log an agent decision.

        Args:
            decision: The decision being made (e.g., 'auto_create_task')
            reasoning: Why this decision was made
            outcome: The result of the decision (e.g., 'approved', 'rejected')
            context: Additional context about the decision

        Returns:
            The created AgentLog entry
        """
        return self.log(
            f"Decision: {decision} -> {outcome}",
            level=LogLevel.INFO,
            action=AgentAction.DECISION,
            details={
                "decision": decision,
                "reasoning": reasoning,
                "outcome": outcome,
                "context": context,
            },
        )

    def _sanitize_url(self, url: str) -> str:
        """Sanitize a URL to remove sensitive query parameters.

        Args:
            url: The URL to sanitize

        Returns:
            Sanitized URL with sensitive params redacted
        """
        from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

        sensitive_params = {"api_key", "apikey", "key", "token", "secret", "password", "auth"}

        try:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)

            # Redact sensitive parameters
            for param in query_params:
                if param.lower() in sensitive_params:
                    query_params[param] = ["[REDACTED]"]

            # Reconstruct URL
            sanitized_query = urlencode(query_params, doseq=True)
            sanitized = urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                sanitized_query,
                "",  # Remove fragment
            ))
            return sanitized
        except Exception:
            # If parsing fails, return a truncated version
            return url[:100] + "..." if len(url) > 100 else url

    def get_logs(
        self,
        *,
        level: LogLevel | None = None,
        action: AgentAction | None = None,
        since: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AgentLog], int]:
        """Query log entries.

        Args:
            level: Filter by log level
            action: Filter by action type
            since: Filter logs after this datetime
            limit: Maximum number of logs to return
            offset: Offset for pagination

        Returns:
            Tuple of (logs, total_count)
        """
        query = self.db.query(AgentLog)

        if level is not None:
            query = query.filter(AgentLog.level == level)

        if action is not None:
            query = query.filter(AgentLog.action == action)

        if since is not None:
            query = query.filter(AgentLog.created_at >= since)

        total = query.count()

        logs = (
            query.order_by(AgentLog.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return logs, total

    def get_recent_logs(self, hours: int = 24, limit: int = 50) -> list[AgentLog]:
        """Get recent log entries.

        Args:
            hours: Number of hours to look back
            limit: Maximum number of logs

        Returns:
            List of recent AgentLog entries
        """
        since = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=hours)
        logs, _ = self.get_logs(since=since, limit=limit)
        return logs

    def get_llm_usage_stats(
        self,
        since: datetime | None = None,
    ) -> dict[str, Any]:
        """Get LLM usage statistics.

        Args:
            since: Calculate stats since this datetime (default: last 24 hours)

        Returns:
            Dict with usage statistics
        """
        if since is None:
            since = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)

        query = (
            self.db.query(AgentLog)
            .filter(AgentLog.action == AgentAction.LLM_REQUEST)
            .filter(AgentLog.created_at >= since)
        )

        # Get totals
        total_requests = query.count()
        total_tokens = (
            self.db.query(func.sum(AgentLog.tokens_used))
            .filter(AgentLog.action == AgentAction.LLM_REQUEST)
            .filter(AgentLog.created_at >= since)
            .scalar()
        ) or 0

        # Get breakdown by model
        model_breakdown = (
            self.db.query(
                AgentLog.model_used,
                func.count(AgentLog.id),
                func.sum(AgentLog.tokens_used),
            )
            .filter(AgentLog.action == AgentAction.LLM_REQUEST)
            .filter(AgentLog.created_at >= since)
            .group_by(AgentLog.model_used)
            .all()
        )

        return {
            "period_hours": (datetime.now(UTC).replace(tzinfo=None) - since).total_seconds() / 3600,
            "total_requests": total_requests,
            "total_tokens": total_tokens,
            "by_model": {
                model: {"requests": count, "tokens": tokens or 0}
                for model, count, tokens in model_breakdown
                if model
            },
        }

    def get_activity_summary(
        self,
        hours: int = 24,
    ) -> dict[str, Any]:
        """Get a summary of agent activity.

        Args:
            hours: Number of hours to summarize

        Returns:
            Dict with activity summary
        """
        since = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=hours)

        # Count by action type
        action_counts = dict(
            self.db.query(AgentLog.action, func.count(AgentLog.id))
            .filter(AgentLog.created_at >= since)
            .filter(AgentLog.action.isnot(None))
            .group_by(AgentLog.action)
            .all()
        )

        # Count by level
        level_counts = dict(
            self.db.query(AgentLog.level, func.count(AgentLog.id))
            .filter(AgentLog.created_at >= since)
            .group_by(AgentLog.level)
            .all()
        )

        # Get tasks created
        tasks_created = (
            self.db.query(func.count(AgentLog.id))
            .filter(AgentLog.action == AgentAction.CREATE_TASK)
            .filter(AgentLog.created_at >= since)
            .scalar()
        ) or 0

        # Get polls
        poll_actions = [
            AgentAction.POLL_EMAIL,
            AgentAction.POLL_SLACK,
            AgentAction.POLL_CALENDAR,
            AgentAction.POLL_DRIVE,
        ]
        polls_completed = (
            self.db.query(func.count(AgentLog.id))
            .filter(AgentLog.action.in_(poll_actions))
            .filter(AgentLog.created_at >= since)
            .scalar()
        ) or 0

        # LLM stats
        llm_stats = self.get_llm_usage_stats(since)

        return {
            "period_hours": hours,
            "tasks_created": tasks_created,
            "polls_completed": polls_completed,
            "by_action": {
                action.value: count for action, count in action_counts.items()
            },
            "by_level": {
                level.value: count for level, count in level_counts.items()
            },
            "llm_usage": llm_stats,
            "errors": level_counts.get(LogLevel.ERROR, 0),
            "warnings": level_counts.get(LogLevel.WARNING, 0),
        }

    def cleanup_old_logs(self, days: int = 30) -> int:
        """Delete logs older than specified days.

        Args:
            days: Number of days to keep

        Returns:
            Number of logs deleted
        """
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)

        deleted = (
            self.db.query(AgentLog)
            .filter(AgentLog.created_at < cutoff)
            .delete(synchronize_session=False)
        )

        self.db.commit()
        logger.info(f"Cleaned up {deleted} logs older than {days} days")

        return deleted
