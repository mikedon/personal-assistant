"""Unit tests for InitiativeService."""

from datetime import datetime, timedelta

import pytest

from src.models.initiative import Initiative, InitiativePriority, InitiativeStatus
from src.models.task import Task, TaskPriority, TaskStatus
from src.services.initiative_service import InitiativeService


@pytest.fixture
def initiative_service(test_db_session):
    """Create an initiative service with test session."""
    return InitiativeService(test_db_session)


def test_create_initiative(initiative_service):
    """Test creating an initiative."""
    initiative = initiative_service.create_initiative(
        title="Test Initiative",
        description="Test description",
        priority=InitiativePriority.HIGH,
    )

    assert initiative.id is not None
    assert initiative.title == "Test Initiative"
    assert initiative.description == "Test description"
    assert initiative.priority == InitiativePriority.HIGH
    assert initiative.status == InitiativeStatus.ACTIVE


def test_create_initiative_with_target_date(initiative_service):
    """Test creating initiative with target date."""
    target = datetime.now() + timedelta(days=30)
    initiative = initiative_service.create_initiative(
        title="Q1 Goals",
        target_date=target,
    )

    assert initiative.target_date is not None
    assert initiative.target_date.date() == target.date()


def test_get_initiative(initiative_service):
    """Test getting initiative by ID."""
    created = initiative_service.create_initiative(title="Find Me")

    found = initiative_service.get_initiative(created.id)
    assert found is not None
    assert found.id == created.id
    assert found.title == "Find Me"


def test_get_initiative_not_found(initiative_service):
    """Test getting non-existent initiative."""
    found = initiative_service.get_initiative(9999)
    assert found is None


def test_get_initiatives(initiative_service):
    """Test listing initiatives."""
    initiative_service.create_initiative(title="Initiative 1", priority=InitiativePriority.HIGH)
    initiative_service.create_initiative(title="Initiative 2", priority=InitiativePriority.MEDIUM)
    initiative_service.create_initiative(title="Initiative 3", priority=InitiativePriority.LOW)

    initiatives, total = initiative_service.get_initiatives()
    assert total == 3
    assert len(initiatives) == 3


def test_get_initiatives_filter_by_status(initiative_service):
    """Test filtering initiatives by status."""
    active = initiative_service.create_initiative(title="Active")
    completed = initiative_service.create_initiative(title="Completed")
    initiative_service.update_initiative(completed, status=InitiativeStatus.COMPLETED)

    # Get only active
    initiatives, total = initiative_service.get_initiatives(
        status=InitiativeStatus.ACTIVE,
        include_completed=True,
    )
    assert total == 1
    assert initiatives[0].title == "Active"


def test_get_initiatives_exclude_completed(initiative_service):
    """Test excluding completed initiatives."""
    initiative_service.create_initiative(title="Active")
    completed = initiative_service.create_initiative(title="Completed")
    initiative_service.update_initiative(completed, status=InitiativeStatus.COMPLETED)

    initiatives, total = initiative_service.get_initiatives(include_completed=False)
    assert total == 1
    assert all(i.status != InitiativeStatus.COMPLETED for i in initiatives)


def test_get_active_initiatives(initiative_service):
    """Test getting only active initiatives."""
    initiative_service.create_initiative(title="Active 1", priority=InitiativePriority.HIGH)
    initiative_service.create_initiative(title="Active 2", priority=InitiativePriority.LOW)
    completed = initiative_service.create_initiative(title="Completed")
    initiative_service.update_initiative(completed, status=InitiativeStatus.COMPLETED)

    active = initiative_service.get_active_initiatives()
    assert len(active) == 2
    assert all(i.status == InitiativeStatus.ACTIVE for i in active)


def test_update_initiative(initiative_service):
    """Test updating initiative."""
    initiative = initiative_service.create_initiative(title="Original")

    updated = initiative_service.update_initiative(
        initiative,
        title="Updated Title",
        description="New description",
        priority=InitiativePriority.HIGH,
        status=InitiativeStatus.PAUSED,
    )

    assert updated.title == "Updated Title"
    assert updated.description == "New description"
    assert updated.priority == InitiativePriority.HIGH
    assert updated.status == InitiativeStatus.PAUSED


def test_delete_initiative(initiative_service, test_db_session):
    """Test deleting initiative."""
    initiative = initiative_service.create_initiative(title="Delete Me")
    initiative_id = initiative.id

    initiative_service.delete_initiative(initiative)

    found = initiative_service.get_initiative(initiative_id)
    assert found is None


def test_get_tasks_for_initiative(initiative_service, test_db_session):
    """Test getting tasks linked to initiative."""
    initiative = initiative_service.create_initiative(title="Project Alpha")

    # Create tasks linked to initiative
    task1 = Task(title="Task 1", initiative_id=initiative.id, priority_score=80)
    task2 = Task(title="Task 2", initiative_id=initiative.id, priority_score=60)
    task3 = Task(title="Unrelated", priority_score=90)  # Not linked
    test_db_session.add_all([task1, task2, task3])
    test_db_session.commit()

    tasks = initiative_service.get_tasks_for_initiative(initiative.id)
    assert len(tasks) == 2
    assert all(t.initiative_id == initiative.id for t in tasks)


def test_get_tasks_for_initiative_exclude_completed(initiative_service, test_db_session):
    """Test excluding completed tasks from initiative."""
    initiative = initiative_service.create_initiative(title="Project Beta")

    task1 = Task(title="Active Task", initiative_id=initiative.id, priority_score=70)
    task2 = Task(
        title="Completed Task",
        initiative_id=initiative.id,
        status=TaskStatus.COMPLETED,
        priority_score=50,
    )
    test_db_session.add_all([task1, task2])
    test_db_session.commit()

    tasks = initiative_service.get_tasks_for_initiative(
        initiative.id, include_completed=False
    )
    assert len(tasks) == 1
    assert tasks[0].status != TaskStatus.COMPLETED


def test_get_initiative_progress(initiative_service, test_db_session):
    """Test calculating initiative progress."""
    initiative = initiative_service.create_initiative(title="Progress Test")

    # Create 3 tasks, 1 completed
    task1 = Task(title="Task 1", initiative_id=initiative.id, status=TaskStatus.PENDING)
    task2 = Task(title="Task 2", initiative_id=initiative.id, status=TaskStatus.COMPLETED)
    task3 = Task(title="Task 3", initiative_id=initiative.id, status=TaskStatus.IN_PROGRESS)
    test_db_session.add_all([task1, task2, task3])
    test_db_session.commit()

    progress = initiative_service.get_initiative_progress(initiative.id)
    assert progress["total_tasks"] == 3
    assert progress["completed_tasks"] == 1
    assert progress["progress_percent"] == pytest.approx(33.3, rel=0.1)


def test_get_initiative_progress_no_tasks(initiative_service):
    """Test progress for initiative with no tasks."""
    initiative = initiative_service.create_initiative(title="Empty Initiative")

    progress = initiative_service.get_initiative_progress(initiative.id)
    assert progress["total_tasks"] == 0
    assert progress["completed_tasks"] == 0
    assert progress["progress_percent"] == 0.0


def test_get_initiative_progress_all_completed(initiative_service, test_db_session):
    """Test progress when all tasks completed."""
    initiative = initiative_service.create_initiative(title="Done Initiative")

    task1 = Task(title="Task 1", initiative_id=initiative.id, status=TaskStatus.COMPLETED)
    task2 = Task(title="Task 2", initiative_id=initiative.id, status=TaskStatus.COMPLETED)
    test_db_session.add_all([task1, task2])
    test_db_session.commit()

    progress = initiative_service.get_initiative_progress(initiative.id)
    assert progress["total_tasks"] == 2
    assert progress["completed_tasks"] == 2
    assert progress["progress_percent"] == 100.0


def test_get_initiatives_with_progress(initiative_service, test_db_session):
    """Test getting initiatives with progress stats."""
    initiative1 = initiative_service.create_initiative(
        title="Initiative 1", priority=InitiativePriority.HIGH
    )
    initiative2 = initiative_service.create_initiative(
        title="Initiative 2", priority=InitiativePriority.LOW
    )

    # Add tasks to initiative1
    task1 = Task(title="Task 1", initiative_id=initiative1.id, status=TaskStatus.COMPLETED)
    task2 = Task(title="Task 2", initiative_id=initiative1.id, status=TaskStatus.PENDING)
    test_db_session.add_all([task1, task2])
    test_db_session.commit()

    results = initiative_service.get_initiatives_with_progress()
    assert len(results) == 2

    # Check that progress is included
    for result in results:
        assert "initiative" in result
        assert "progress" in result
        assert "total_tasks" in result["progress"]
        assert "completed_tasks" in result["progress"]
        assert "progress_percent" in result["progress"]


def test_delete_initiative_unlinks_tasks(initiative_service, test_db_session):
    """Test that deleting initiative unlinks but doesn't delete tasks."""
    initiative = initiative_service.create_initiative(title="Delete Test")

    task = Task(title="Linked Task", initiative_id=initiative.id, priority_score=50)
    test_db_session.add(task)
    test_db_session.commit()
    task_id = task.id

    initiative_service.delete_initiative(initiative)

    # Task should still exist but be unlinked
    task = test_db_session.query(Task).filter(Task.id == task_id).first()
    assert task is not None
    assert task.initiative_id is None
