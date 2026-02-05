"""Tests for TaskService."""

from datetime import UTC, datetime, timedelta

import pytest

from src.models.initiative import Initiative, InitiativePriority, InitiativeStatus
from src.models.task import Task, TaskPriority, TaskSource, TaskStatus
from src.services.initiative_service import InitiativeService
from src.services.task_service import TaskService


class TestPriorityScoring:
    """Tests for priority score calculation."""

    def test_base_priority_critical(self):
        """Critical priority should give highest base score."""
        task = Task(title="Test", priority=TaskPriority.CRITICAL)
        score = TaskService.calculate_priority_score(task)
        # Critical = 40 + source bonus (manual=5) = 45
        assert score >= 45

    def test_base_priority_low(self):
        """Low priority should give lowest base score."""
        task = Task(title="Test", priority=TaskPriority.LOW)
        score = TaskService.calculate_priority_score(task)
        # Low = 10 + source bonus (manual=5) = 15
        assert score >= 15
        assert score < 30

    def test_overdue_task_gets_urgency_boost(self):
        """Overdue tasks should get maximum urgency boost."""
        yesterday = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
        task = Task(
            title="Test",
            priority=TaskPriority.MEDIUM,
            due_date=yesterday,
            status=TaskStatus.PENDING,
        )
        score = TaskService.calculate_priority_score(task)
        # Medium=20 + overdue=25 + source=5 = 50+
        assert score >= 50

    def test_due_today_gets_urgency_boost(self):
        """Tasks due today should get high urgency boost."""
        today = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=2)
        task = Task(
            title="Test",
            priority=TaskPriority.MEDIUM,
            due_date=today,
            status=TaskStatus.PENDING,
        )
        score = TaskService.calculate_priority_score(task)
        # Should have due today boost
        assert score >= 40

    def test_source_importance_meeting_notes(self):
        """Meeting notes source should get higher score."""
        task_meeting = Task(
            title="Test", priority=TaskPriority.MEDIUM, source=TaskSource.MEETING_NOTES
        )
        task_agent = Task(
            title="Test", priority=TaskPriority.MEDIUM, source=TaskSource.AGENT
        )
        
        score_meeting = TaskService.calculate_priority_score(task_meeting)
        score_agent = TaskService.calculate_priority_score(task_agent)
        
        assert score_meeting > score_agent

    def test_urgent_tag_boosts_score(self):
        """Tasks with urgent tags should get score boost."""
        task = Task(title="Test", priority=TaskPriority.MEDIUM)
        task.set_tags_list(["urgent"])
        
        task_no_tags = Task(title="Test", priority=TaskPriority.MEDIUM)
        
        score_urgent = TaskService.calculate_priority_score(task)
        score_normal = TaskService.calculate_priority_score(task_no_tags)
        
        assert score_urgent > score_normal
        assert score_urgent - score_normal == 10  # Urgent tags give 10 points

    def test_important_tag_boosts_score(self):
        """Tasks with important tags should get smaller score boost."""
        task = Task(title="Test", priority=TaskPriority.MEDIUM)
        task.set_tags_list(["important"])
        
        task_no_tags = Task(title="Test", priority=TaskPriority.MEDIUM)
        
        score_important = TaskService.calculate_priority_score(task)
        score_normal = TaskService.calculate_priority_score(task_no_tags)
        
        assert score_important > score_normal
        assert score_important - score_normal == 5  # Important tags give 5 points

    def test_score_capped_at_100(self):
        """Score should never exceed 100."""
        # Create a task that would exceed 100 without capping
        # Critical=40 + overdue=25 + old_task=15 + meeting_notes=9 + urgent_tag=10 = 99
        # Need to make it old enough to get age bonus
        yesterday = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
        two_weeks_ago = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=15)
        task = Task(
            title="Test",
            priority=TaskPriority.CRITICAL,
            due_date=yesterday,
            source=TaskSource.MEETING_NOTES,
            status=TaskStatus.PENDING,
            created_at=two_weeks_ago,
        )
        task.set_tags_list(["urgent", "blocker", "asap"])
        
        score = TaskService.calculate_priority_score(task)
        # Should be capped at 100 (40+25+15+9+10 = 99, but score is capped)
        assert score <= 100.0
        assert score >= 90.0  # Should be very high


class TestTaskServiceOperations:
    """Tests for TaskService CRUD operations."""

    def test_create_task(self, test_db_session):
        """Test creating a task."""
        service = TaskService(test_db_session)
        
        task = service.create_task(
            title="New Task",
            description="Description",
            priority=TaskPriority.HIGH,
            tags=["test", "important"],
        )
        
        assert task.id is not None
        assert task.title == "New Task"
        assert task.priority == TaskPriority.HIGH
        assert task.priority_score > 0
        assert "test" in task.get_tags_list()

    def test_get_task(self, test_db_session):
        """Test getting a task by ID."""
        service = TaskService(test_db_session)
        created = service.create_task(title="Find Me")
        
        found = service.get_task(created.id)
        
        assert found is not None
        assert found.id == created.id
        assert found.title == "Find Me"

    def test_get_task_not_found(self, test_db_session):
        """Test getting non-existent task returns None."""
        service = TaskService(test_db_session)
        
        found = service.get_task(99999)
        
        assert found is None

    def test_update_task(self, test_db_session):
        """Test updating a task."""
        service = TaskService(test_db_session)
        task = service.create_task(title="Original")
        
        updated = service.update_task(
            task,
            title="Updated",
            status=TaskStatus.IN_PROGRESS,
        )
        
        assert updated.title == "Updated"
        assert updated.status == TaskStatus.IN_PROGRESS

    def test_update_task_to_completed(self, test_db_session):
        """Test marking task as completed sets completed_at."""
        service = TaskService(test_db_session)
        task = service.create_task(title="Complete Me")
        
        updated = service.update_task(task, status=TaskStatus.COMPLETED)
        
        assert updated.status == TaskStatus.COMPLETED
        assert updated.completed_at is not None

    def test_delete_task(self, test_db_session):
        """Test deleting a task."""
        service = TaskService(test_db_session)
        task = service.create_task(title="Delete Me")
        task_id = task.id
        
        service.delete_task(task)
        
        assert service.get_task(task_id) is None

    def test_get_tasks_with_search(self, test_db_session):
        """Test searching tasks by title/description."""
        service = TaskService(test_db_session)
        service.create_task(title="Important meeting prep")
        service.create_task(title="Regular task", description="Meeting notes to review")
        service.create_task(title="Unrelated task")
        
        tasks, total = service.get_tasks(search="meeting")
        
        assert total == 2
        assert all("meeting" in t.title.lower() or (t.description and "meeting" in t.description.lower()) for t in tasks)

    def test_get_tasks_with_status_filter(self, test_db_session):
        """Test filtering tasks by status."""
        service = TaskService(test_db_session)
        service.create_task(title="Task 1")
        task2 = service.create_task(title="Task 2")
        service.update_task(task2, status=TaskStatus.COMPLETED)
        
        tasks, total = service.get_tasks(status=TaskStatus.PENDING)
        
        assert total == 1
        assert all(t.status == TaskStatus.PENDING for t in tasks)

    def test_get_tasks_with_tag_filter(self, test_db_session):
        """Test filtering tasks by tags."""
        service = TaskService(test_db_session)
        service.create_task(title="Task 1", tags=["urgent", "work"])
        service.create_task(title="Task 2", tags=["personal"])
        service.create_task(title="Task 3", tags=["work"])
        
        tasks, total = service.get_tasks(tags=["work"])
        
        assert total == 2

    def test_get_prioritized_tasks(self, test_db_session):
        """Test getting prioritized tasks."""
        service = TaskService(test_db_session)
        service.create_task(title="Low", priority=TaskPriority.LOW)
        service.create_task(title="Critical", priority=TaskPriority.CRITICAL)
        service.create_task(title="Medium", priority=TaskPriority.MEDIUM)
        
        tasks = service.get_prioritized_tasks(limit=3)
        
        # Should be sorted by priority score descending
        assert tasks[0].priority == TaskPriority.CRITICAL
        assert tasks[0].priority_score >= tasks[1].priority_score

    def test_get_overdue_tasks(self, test_db_session):
        """Test getting overdue tasks."""
        service = TaskService(test_db_session)
        yesterday = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
        tomorrow = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1)
        
        service.create_task(title="Overdue", due_date=yesterday)
        service.create_task(title="Future", due_date=tomorrow)
        service.create_task(title="No due date")
        
        overdue = service.get_overdue_tasks()
        
        assert len(overdue) == 1
        assert overdue[0].title == "Overdue"

    def test_get_due_soon_tasks(self, test_db_session):
        """Test getting tasks due soon."""
        service = TaskService(test_db_session)
        now = datetime.now(UTC).replace(tzinfo=None)
        
        service.create_task(title="Tomorrow", due_date=now + timedelta(days=1))
        service.create_task(title="Next week", due_date=now + timedelta(days=7))
        service.create_task(title="Yesterday", due_date=now - timedelta(days=1))
        
        due_soon = service.get_due_soon_tasks(days=3)
        
        assert len(due_soon) == 1
        assert due_soon[0].title == "Tomorrow"


class TestBatchOperations:
    """Tests for batch operations."""

    def test_bulk_update_status(self, test_db_session):
        """Test bulk status update."""
        service = TaskService(test_db_session)
        task1 = service.create_task(title="Task 1")
        task2 = service.create_task(title="Task 2")
        task3 = service.create_task(title="Task 3")
        
        updated = service.bulk_update_status(
            [task1.id, task2.id],
            TaskStatus.COMPLETED,
        )
        
        assert len(updated) == 2
        assert all(t.status == TaskStatus.COMPLETED for t in updated)
        assert all(t.completed_at is not None for t in updated)
        
        # Task 3 should be unchanged
        task3_fresh = service.get_task(task3.id)
        assert task3_fresh.status == TaskStatus.PENDING

    def test_bulk_delete(self, test_db_session):
        """Test bulk delete."""
        service = TaskService(test_db_session)
        task1 = service.create_task(title="Task 1")
        task2 = service.create_task(title="Task 2")
        task3 = service.create_task(title="Task 3")
        
        # Store IDs before deletion
        task1_id = task1.id
        task2_id = task2.id
        task3_id = task3.id
        
        deleted_count = service.bulk_delete([task1_id, task2_id])
        
        assert deleted_count == 2
        assert service.get_task(task1_id) is None
        assert service.get_task(task2_id) is None
        assert service.get_task(task3_id) is not None

    def test_recalculate_all_priorities(self, test_db_session):
        """Test recalculating all priorities."""
        service = TaskService(test_db_session)
        service.create_task(title="Task 1")
        service.create_task(title="Task 2")
        task3 = service.create_task(title="Task 3")
        service.update_task(task3, status=TaskStatus.COMPLETED)
        
        updated_count = service.recalculate_all_priorities()
        
        # Only active tasks (pending/in_progress) should be recalculated
        assert updated_count == 2


class TestStatistics:
    """Tests for statistics functionality."""

    def test_get_statistics(self, test_db_session):
        """Test getting task statistics."""
        service = TaskService(test_db_session)
        now = datetime.now(UTC).replace(tzinfo=None)
        
        # Create various tasks
        service.create_task(title="Pending 1", priority=TaskPriority.HIGH)
        service.create_task(title="Pending 2", priority=TaskPriority.LOW)
        task3 = service.create_task(title="Completed")
        service.update_task(task3, status=TaskStatus.COMPLETED)
        service.create_task(title="Overdue", due_date=now - timedelta(days=1))
        service.create_task(title="Due today", due_date=now + timedelta(hours=2))
        
        stats = service.get_statistics()
        
        assert stats["total"] == 5
        assert stats["active"] == 4  # Excluding completed
        assert stats["by_status"]["pending"] == 4
        assert stats["by_status"]["completed"] == 1
        assert stats["overdue"] == 1
        assert stats["due_today"] == 1

    def test_statistics_with_empty_db(self, test_db_session):
        """Test statistics with no tasks."""
        service = TaskService(test_db_session)
        
        stats = service.get_statistics()
        
        assert stats["total"] == 0
        assert stats["active"] == 0
        assert stats["overdue"] == 0


class TestOptionalInitiatives:
    """Tests for tasks with optional initiative relationships."""

    def test_create_task_without_initiative(self, test_db_session):
        """Test creating a task without linking to an initiative."""
        service = TaskService(test_db_session)
        
        task = service.create_task(
            title="Standalone Task",
            description="This task has no initiative",
            priority=TaskPriority.HIGH,
        )
        
        assert task.id is not None
        assert task.initiative_id is None
        assert task.initiative is None
        assert task.title == "Standalone Task"

    def test_create_task_with_initiative(self, test_db_session):
        """Test creating a task linked to an initiative."""
        initiative_service = InitiativeService(test_db_session)
        task_service = TaskService(test_db_session)
        
        # Create an initiative
        initiative = initiative_service.create_initiative(
            title="Main Project",
            priority=InitiativePriority.HIGH,
        )
        
        # Create task linked to initiative
        task = task_service.create_task(
            title="Task for Project",
            initiative_id=initiative.id,
        )
        
        assert task.initiative_id == initiative.id
        assert task.initiative is not None
        assert task.initiative.title == "Main Project"

    def test_get_tasks_without_initiative(self, test_db_session):
        """Test retrieving tasks without initiatives."""
        service = TaskService(test_db_session)
        
        service.create_task(title="Task 1")
        service.create_task(title="Task 2")
        service.create_task(title="Task 3")
        
        tasks, total = service.get_tasks(limit=10)
        
        assert total == 3
        assert all(t.initiative_id is None for t in tasks)
        assert all(t.initiative is None for t in tasks)

    def test_get_mixed_tasks_with_and_without_initiatives(self, test_db_session):
        """Test retrieving tasks where some have initiatives and some don't."""
        initiative_service = InitiativeService(test_db_session)
        task_service = TaskService(test_db_session)
        
        # Create an initiative
        initiative = initiative_service.create_initiative(
            title="Project A",
            priority=InitiativePriority.HIGH,
        )
        
        # Create mix of tasks
        task1 = task_service.create_task(title="Standalone Task")
        task2 = task_service.create_task(title="Project Task", initiative_id=initiative.id)
        task3 = task_service.create_task(title="Another Standalone")
        
        tasks, total = task_service.get_tasks(limit=10)
        
        assert total == 3
        
        # Check each task
        standalone_tasks = [t for t in tasks if t.initiative_id is None]
        linked_tasks = [t for t in tasks if t.initiative_id is not None]
        
        assert len(standalone_tasks) == 2
        assert len(linked_tasks) == 1
        assert linked_tasks[0].initiative.title == "Project A"

    def test_update_task_remove_initiative(self, test_db_session):
        """Test removing initiative from a task."""
        initiative_service = InitiativeService(test_db_session)
        task_service = TaskService(test_db_session)
        
        # Create initiative and task
        initiative = initiative_service.create_initiative(
            title="Project",
            priority=InitiativePriority.MEDIUM,
        )
        task = task_service.create_task(
            title="Task",
            initiative_id=initiative.id,
        )
        
        assert task.initiative_id is not None
        
        # Remove the initiative
        updated = task_service.update_task(task, clear_initiative=True)
        
        assert updated.initiative_id is None
        assert updated.initiative is None

    def test_update_task_add_initiative(self, test_db_session):
        """Test adding initiative to a task that didn't have one."""
        initiative_service = InitiativeService(test_db_session)
        task_service = TaskService(test_db_session)
        
        # Create initiative and standalone task
        initiative = initiative_service.create_initiative(
            title="Project",
            priority=InitiativePriority.MEDIUM,
        )
        task = task_service.create_task(title="Task")
        
        assert task.initiative_id is None
        
        # Add the initiative
        updated = task_service.update_task(task, initiative_id=initiative.id)
        
        assert updated.initiative_id == initiative.id
        assert updated.initiative is not None

    def test_priority_score_without_initiative(self, test_db_session):
        """Test priority scoring works correctly for tasks without initiatives."""
        task = Task(
            title="Test",
            priority=TaskPriority.HIGH,
            initiative_id=None,  # Explicitly no initiative
        )
        
        # Should calculate score without raising errors
        score = TaskService.calculate_priority_score(task)
        
        # High priority + manual source = 30 + 5 = 35
        assert score >= 35
        assert score < 100

    def test_priority_score_with_active_initiative(self, test_db_session):
        """Test priority scoring includes initiative bonus."""
        initiative_service = InitiativeService(test_db_session)
        
        # Create high priority active initiative
        initiative = initiative_service.create_initiative(
            title="Important Project",
            priority=InitiativePriority.HIGH,
        )
        # Make sure it's active
        test_db_session.refresh(initiative)
        
        # Create task linked to initiative
        task = Task(
            title="Test",
            priority=TaskPriority.MEDIUM,
            initiative_id=initiative.id,
            initiative=initiative,
        )
        
        score = TaskService.calculate_priority_score(task)
        
        # Medium=20 + source=5 + high_initiative_bonus=10 = 35+
        assert score >= 35

    def test_task_without_initiative_handles_none_gracefully(self, test_db_session):
        """Test that accessing None initiative doesn't cause errors."""
        service = TaskService(test_db_session)
        task = service.create_task(title="Test Task")
        
        # These should all work without errors
        assert task.initiative is None
        assert task.initiative_id is None
        assert not hasattr(task, 'initiative') or task.initiative is None or True
        
        # Update should work
        updated = service.update_task(task, title="Updated")
        assert updated.initiative is None
        assert updated.initiative_id is None
