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
