"""Task service with business logic for task management."""

from datetime import UTC, datetime, timedelta
from typing import Sequence

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from src.models.initiative import InitiativePriority, InitiativeStatus
from src.models.task import Task, TaskPriority, TaskSource, TaskStatus


class TaskService:
    """Service for task management operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_task(self, task_id: int) -> Task | None:
        """Get a task by ID."""
        return self.db.query(Task).filter(Task.id == task_id).first()

    def get_tasks(
        self,
        *,
        status: TaskStatus | list[TaskStatus] | None = None,
        priority: TaskPriority | list[TaskPriority] | None = None,
        source: TaskSource | None = None,
        account_id: str | None = None,
        tags: list[str] | None = None,
        search: str | None = None,
        due_before: datetime | None = None,
        due_after: datetime | None = None,
        include_completed: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Task], int]:
        """Get tasks with advanced filtering.

        Returns:
            Tuple of (tasks, total_count)
        """
        query = self.db.query(Task)

        # Add eager loading for initiative to avoid N+1 queries
        query = query.options(joinedload(Task.initiative))

        # Status filter
        if status is not None:
            if isinstance(status, list):
                query = query.filter(Task.status.in_(status))
            else:
                query = query.filter(Task.status == status)
        elif not include_completed:
            query = query.filter(Task.status != TaskStatus.COMPLETED)

        # Priority filter
        if priority is not None:
            if isinstance(priority, list):
                query = query.filter(Task.priority.in_(priority))
            else:
                query = query.filter(Task.priority == priority)

        # Source filter
        if source is not None:
            query = query.filter(Task.source == source)

        # Account ID filter
        if account_id is not None:
            query = query.filter(Task.account_id == account_id)

        # Tags filter (matches any of the provided tags)
        if tags:
            tag_conditions = [Task.tags.contains(tag) for tag in tags]
            query = query.filter(or_(*tag_conditions))

        # Search in title and description
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    Task.title.ilike(search_pattern),
                    Task.description.ilike(search_pattern),
                )
            )

        # Due date range
        if due_before is not None:
            query = query.filter(Task.due_date <= due_before)
        if due_after is not None:
            query = query.filter(Task.due_date >= due_after)

        # Get total count before pagination
        total = query.count()

        # Order by priority score (descending) and created_at
        tasks = (
            query.order_by(Task.priority_score.desc(), Task.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return tasks, total

    def get_prioritized_tasks(self, limit: int = 10) -> list[Task]:
        """Get top priority tasks that are actionable (pending or in progress)."""
        return (
            self.db.query(Task)
            .options(joinedload(Task.initiative))
            .filter(Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]))
            .order_by(Task.priority_score.desc())
            .limit(limit)
            .all()
        )

    def get_overdue_tasks(self) -> list[Task]:
        """Get all overdue tasks."""
        now = datetime.now(UTC).replace(tzinfo=None)
        return (
            self.db.query(Task)
            .options(joinedload(Task.initiative))
            .filter(
                and_(
                    Task.due_date < now,
                    Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]),
                )
            )
            .order_by(Task.due_date.asc())
            .all()
        )

    def get_due_soon_tasks(self, days: int = 3) -> list[Task]:
        """Get tasks due within the specified number of days."""
        now = datetime.now(UTC).replace(tzinfo=None)
        soon = now + timedelta(days=days)
        return (
            self.db.query(Task)
            .options(joinedload(Task.initiative))
            .filter(
                and_(
                    Task.due_date >= now,
                    Task.due_date <= soon,
                    Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]),
                )
            )
            .order_by(Task.due_date.asc())
            .all()
        )

    def create_task(
        self,
        title: str,
        description: str | None = None,
        priority: TaskPriority = TaskPriority.MEDIUM,
        source: TaskSource = TaskSource.MANUAL,
        source_reference: str | None = None,
        account_id: str | None = None,
        due_date: datetime | None = None,
        tags: list[str] | None = None,
        initiative_id: int | None = None,
    ) -> Task:
        """Create a new task with calculated priority score.

        Args:
            title: Task title
            description: Task description
            priority: Task priority level
            source: Source of the task (email, manual, etc.)
            source_reference: Reference ID in source system
            account_id: Account identifier (must exist in configuration if provided)
            due_date: Task due date
            tags: List of tags
            initiative_id: Associated initiative ID

        Returns:
            Created task

        Raises:
            ValueError: If account_id is provided but not configured
        """
        # Validate account_id if provided
        if account_id:
            self._validate_account_id(account_id)

        task = Task(
            title=title,
            description=description,
            priority=priority,
            source=source,
            source_reference=source_reference,
            account_id=account_id,
            due_date=due_date,
            initiative_id=initiative_id,
        )
        if tags:
            task.set_tags_list(tags)

        task.priority_score = self.calculate_priority_score(task)

        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)

        return task

    def _validate_account_id(self, account_id: str) -> None:
        """Validate that account_id exists in configuration.

        Args:
            account_id: Account identifier to validate

        Raises:
            ValueError: If account_id is not configured
        """
        from src.integrations.base import IntegrationType
        from src.integrations.manager import IntegrationManager
        from src.utils.config import load_config

        # Load config to initialize IntegrationManager
        config = load_config()
        manager = IntegrationManager(config)

        # Collect all configured account_ids
        all_accounts = []
        for integration_type in IntegrationType:
            all_accounts.extend(manager.list_accounts(integration_type))

        if account_id not in all_accounts:
            raise ValueError(
                f"Invalid account_id: {account_id}. "
                f"Configured accounts: {', '.join(all_accounts) if all_accounts else 'none'}"
            )

    def update_task(
        self,
        task: Task,
        *,
        title: str | None = None,
        description: str | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        due_date: datetime | None = None,
        tags: list[str] | None = None,
        initiative_id: int | None = None,
        clear_initiative: bool = False,
    ) -> Task:
        """Update a task and recalculate priority score.

        Args:
            task: Task to update
            title: New title
            description: New description
            status: New status
            priority: New priority
            due_date: New due date
            tags: New tags list
            initiative_id: Initiative to link task to
            clear_initiative: If True, unlink task from any initiative
        """
        if title is not None:
            task.title = title
        if description is not None:
            task.description = description
        if status is not None:
            task.status = status
            if status == TaskStatus.COMPLETED:
                task.completed_at = datetime.now(UTC)
        if priority is not None:
            task.priority = priority
        if due_date is not None:
            task.due_date = due_date
        if tags is not None:
            task.set_tags_list(tags)
        if clear_initiative:
            task.initiative_id = None
        elif initiative_id is not None:
            task.initiative_id = initiative_id

        task.priority_score = self.calculate_priority_score(task)

        self.db.commit()
        self.db.refresh(task)

        return task

    def delete_task(self, task: Task) -> None:
        """Delete a task."""
        self.db.delete(task)
        self.db.commit()

    def bulk_update_status(
        self, task_ids: list[int], status: TaskStatus
    ) -> list[Task]:
        """Update status for multiple tasks."""
        tasks = (
            self.db.query(Task)
            .options(joinedload(Task.initiative))
            .filter(Task.id.in_(task_ids))
            .all()
        )

        now = datetime.now(UTC) if status == TaskStatus.COMPLETED else None

        for task in tasks:
            task.status = status
            if status == TaskStatus.COMPLETED:
                task.completed_at = now
            task.priority_score = self.calculate_priority_score(task)

        self.db.commit()

        # Refresh all tasks
        for task in tasks:
            self.db.refresh(task)

        return tasks

    def bulk_delete(self, task_ids: list[int]) -> int:
        """Delete multiple tasks. Returns count of deleted tasks."""
        deleted = (
            self.db.query(Task).filter(Task.id.in_(task_ids)).delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted

    def recalculate_all_priorities(self) -> int:
        """Recalculate priority scores for all active tasks.

        Returns:
            Number of tasks updated.
        """
        tasks = (
            self.db.query(Task)
            .filter(Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]))
            .all()
        )

        for task in tasks:
            task.priority_score = self.calculate_priority_score(task)

        self.db.commit()
        return len(tasks)

    def get_statistics(self) -> dict:
        """Get task statistics."""
        now = datetime.now(UTC).replace(tzinfo=None)

        # Count by status
        status_counts = dict(
            self.db.query(Task.status, func.count(Task.id))
            .group_by(Task.status)
            .all()
        )

        # Count by priority (active tasks only)
        priority_counts = dict(
            self.db.query(Task.priority, func.count(Task.id))
            .filter(Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]))
            .group_by(Task.priority)
            .all()
        )

        # Count by source
        source_counts = dict(
            self.db.query(Task.source, func.count(Task.id))
            .group_by(Task.source)
            .all()
        )

        # Overdue count
        overdue_count = (
            self.db.query(func.count(Task.id))
            .filter(
                and_(
                    Task.due_date < now,
                    Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]),
                )
            )
            .scalar()
        )

        # Due today
        tomorrow = now + timedelta(days=1)
        due_today_count = (
            self.db.query(func.count(Task.id))
            .filter(
                and_(
                    Task.due_date >= now,
                    Task.due_date < tomorrow,
                    Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]),
                )
            )
            .scalar()
        )

        # Due this week
        week_from_now = now + timedelta(days=7)
        due_this_week_count = (
            self.db.query(func.count(Task.id))
            .filter(
                and_(
                    Task.due_date >= now,
                    Task.due_date < week_from_now,
                    Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]),
                )
            )
            .scalar()
        )

        # Total counts
        total = self.db.query(func.count(Task.id)).scalar()
        active = (
            self.db.query(func.count(Task.id))
            .filter(Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]))
            .scalar()
        )

        # Average completion time (for completed tasks with timestamps)
        completed_with_dates = (
            self.db.query(Task)
            .filter(
                and_(
                    Task.status == TaskStatus.COMPLETED,
                    Task.completed_at.isnot(None),
                )
            )
            .all()
        )

        avg_completion_hours = None
        if completed_with_dates:
            total_hours = sum(
                (task.completed_at - task.created_at).total_seconds() / 3600
                for task in completed_with_dates
                if task.completed_at and task.created_at
            )
            avg_completion_hours = total_hours / len(completed_with_dates)

        return {
            "total": total,
            "active": active,
            "by_status": {s.value: status_counts.get(s, 0) for s in TaskStatus},
            "by_priority": {p.value: priority_counts.get(p, 0) for p in TaskPriority},
            "by_source": {s.value: source_counts.get(s, 0) for s in TaskSource},
            "overdue": overdue_count,
            "due_today": due_today_count,
            "due_this_week": due_this_week_count,
            "avg_completion_hours": avg_completion_hours,
        }

    @staticmethod
    def calculate_priority_score(task: Task) -> float:
        """Calculate priority score based on multiple factors.

        Scoring factors (0-100 scale):
        - Base priority level: 0-40 points
        - Due date urgency: 0-25 points
        - Task age: 0-15 points
        - Source importance: 0-10 points
        - Special tags: 0-10 points
        - Initiative priority: 0-10 points

        Higher score = higher priority.
        """
        score = 0.0

        # 1. Base priority level (0-40 points)
        priority_scores = {
            TaskPriority.CRITICAL: 40,
            TaskPriority.HIGH: 30,
            TaskPriority.MEDIUM: 20,
            TaskPriority.LOW: 10,
        }
        score += priority_scores.get(task.priority, 20)

        # 2. Due date urgency (0-25 points)
        if task.due_date:
            now = datetime.now(UTC).replace(tzinfo=None)
            # Handle timezone-aware due dates
            due_date = task.due_date
            if due_date.tzinfo is not None:
                due_date = due_date.replace(tzinfo=None)

            days_until_due = (due_date - now).days
            hours_until_due = (due_date - now).total_seconds() / 3600

            if days_until_due < 0:
                # Overdue - maximum urgency
                score += 25
            elif hours_until_due <= 4:
                # Due within 4 hours
                score += 23
            elif hours_until_due <= 24:
                # Due today
                score += 20
            elif days_until_due <= 2:
                # Due in 1-2 days
                score += 15
            elif days_until_due <= 7:
                # Due this week
                score += 10
            elif days_until_due <= 14:
                # Due in 2 weeks
                score += 5

        # 3. Task age bonus (0-15 points) - older uncompleted tasks get slight boost
        if task.status in [TaskStatus.PENDING, TaskStatus.IN_PROGRESS]:
            if task.created_at:
                now = datetime.now(UTC).replace(tzinfo=None)
                created = task.created_at
                if created.tzinfo is not None:
                    created = created.replace(tzinfo=None)
                days_old = (now - created).days

                if days_old >= 14:
                    score += 15
                elif days_old >= 7:
                    score += 10
                elif days_old >= 3:
                    score += 5
                elif days_old >= 1:
                    score += 2

        # 4. Source importance (0-10 points)
        source_scores = {
            TaskSource.MANUAL: 5,  # User explicitly created
            TaskSource.EMAIL: 8,  # Email often contains important requests
            TaskSource.SLACK: 7,  # Direct communication
            TaskSource.CALENDAR: 6,  # Calendar-related
            TaskSource.MEETING_NOTES: 9,  # Action items from meetings
            TaskSource.AGENT: 4,  # Auto-generated
        }
        score += source_scores.get(task.source, 5)

        # 5. Special tags bonus (0-10 points)
        tags = task.get_tags_list()
        urgent_tags = {"urgent", "asap", "critical", "blocking", "blocker"}
        important_tags = {"important", "priority", "key"}

        if any(tag.lower() in urgent_tags for tag in tags):
            score += 10
        elif any(tag.lower() in important_tags for tag in tags):
            score += 5

        # 6. Initiative priority bonus (0-10 points)
        # Tasks linked to active high-priority initiatives get a boost
        if task.initiative_id and task.initiative:
            initiative = task.initiative
            if initiative.status == InitiativeStatus.ACTIVE:
                initiative_scores = {
                    InitiativePriority.HIGH: 10,
                    InitiativePriority.MEDIUM: 5,
                    InitiativePriority.LOW: 2,
                }
                score += initiative_scores.get(initiative.priority, 0)

        # Cap at 100
        return min(score, 100.0)
