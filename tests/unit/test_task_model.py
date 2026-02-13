"""Tests for Task model."""

from datetime import UTC, datetime, timedelta

import pytest

from src.models.task import Task, TaskPriority, TaskSource, TaskStatus


def test_task_creation(test_db_session):
    """Test creating a task."""
    task = Task(
        title="Test Task",
        description="Test description",
        priority=TaskPriority.HIGH,
        source=TaskSource.MANUAL,
    )

    test_db_session.add(task)
    test_db_session.commit()

    assert task.id is not None
    assert task.title == "Test Task"
    assert task.status == TaskStatus.PENDING
    assert task.priority == TaskPriority.HIGH
    assert task.created_at is not None


def test_task_tags(test_db_session):
    """Test task tags functionality."""
    task = Task(title="Test Task")
    task.set_tags_list(["urgent", "work", "meeting"])

    test_db_session.add(task)
    test_db_session.commit()

    assert task.tags == "urgent,work,meeting"
    assert task.get_tags_list() == ["urgent", "work", "meeting"]


def test_task_tags_empty(test_db_session):
    """Test task with no tags."""
    task = Task(title="Test Task")

    assert task.get_tags_list() == []

    task.set_tags_list([])
    assert task.tags is None


def test_task_document_links(test_db_session):
    """Test task document links functionality (JSON format)."""
    task = Task(title="Test Task")
    links = ["https://docs.google.com/doc1", "https://example.com/doc2"]
    task.set_document_links_list(links)

    test_db_session.add(task)
    test_db_session.commit()

    # Now stored as JSON array
    import json
    assert json.loads(task.document_links) == links
    assert task.get_document_links_list() == links


def test_task_document_links_empty(test_db_session):
    """Test task with no document links."""
    task = Task(title="Test Task")

    assert task.get_document_links_list() == []

    task.set_document_links_list([])
    assert task.document_links is None


def test_task_document_links_single(test_db_session):
    """Test task with single document link (JSON format)."""
    task = Task(title="Test Task")
    link = "https://docs.google.com/document/d/123"
    task.set_document_links_list([link])

    test_db_session.add(task)
    test_db_session.commit()

    # Stored as JSON array even for single link
    import json
    assert json.loads(task.document_links) == [link]
    assert task.get_document_links_list() == [link]


def test_task_document_links_with_commas(test_db_session):
    """Test URLs containing commas are handled correctly (CSV injection prevention)."""
    task = Task(title="Test Task")
    # URL with commas in query parameters
    url_with_commas = "https://example.com/doc?tags=work,urgent&id=123"
    task.set_document_links_list([url_with_commas])

    test_db_session.add(task)
    test_db_session.commit()
    test_db_session.refresh(task)

    # Should retrieve URL intact, not split by commas
    retrieved = task.get_document_links_list()
    assert len(retrieved) == 1, f"Expected 1 URL, got {len(retrieved)}"
    assert retrieved[0] == url_with_commas, "URL was corrupted"


def test_task_document_links_csv_formula_injection_prevention(test_db_session):
    """Test that CSV formula injection attacks are neutralized."""
    task = Task(title="Test Task")
    # Malicious formula injection attempts
    malicious_urls = [
        "=cmd|'/c calc'!A1",
        "@SUM(A1:A10)",
        "+2+5+cmd|'/c calc'!A0"
    ]

    # These should be stored safely as JSON strings
    task.set_document_links_list(malicious_urls)

    test_db_session.add(task)
    test_db_session.commit()
    test_db_session.refresh(task)

    # Should retrieve exactly what was stored, no execution risk
    retrieved = task.get_document_links_list()
    assert len(retrieved) == 3
    assert retrieved == malicious_urls


def test_task_document_links_csv_backward_compatibility(test_db_session):
    """Test backward compatibility with legacy CSV format."""
    task = Task(title="Test Task")

    # Simulate legacy CSV storage (directly set the field)
    task.document_links = "https://docs.google.com/doc1,https://example.com/doc2"

    test_db_session.add(task)
    test_db_session.commit()
    test_db_session.refresh(task)

    # Should still parse CSV format correctly
    retrieved = task.get_document_links_list()
    assert len(retrieved) == 2
    assert "docs.google.com/doc1" in retrieved[0]
    assert "example.com/doc2" in retrieved[1]


def test_task_repr():
    """Test task string representation."""
    task = Task(
        id=1,
        title="A very long task title that should be truncated",
        status=TaskStatus.IN_PROGRESS,
    )

    repr_str = repr(task)
    assert "Task(id=1" in repr_str
    assert "in_progress" in repr_str


def test_task_due_date(test_db_session):
    """Test task with due date."""
    due_date = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
    task = Task(
        title="Task with deadline",
        due_date=due_date,
    )

    test_db_session.add(task)
    test_db_session.commit()

    assert task.due_date == due_date


def test_task_completion(test_db_session):
    """Test marking task as completed."""
    task = Task(title="Test Task")
    test_db_session.add(task)
    test_db_session.commit()

    # Mark as completed
    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.now(UTC)
    test_db_session.commit()

    assert task.status == TaskStatus.COMPLETED
    assert task.completed_at is not None
