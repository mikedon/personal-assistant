"""Initiative service with business logic for initiative management."""

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.initiative import Initiative, InitiativePriority, InitiativeStatus
from src.models.task import Task, TaskStatus


class InitiativeService:
    """Service for initiative management operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_initiative(self, initiative_id: int) -> Initiative | None:
        """Get an initiative by ID."""
        return self.db.query(Initiative).filter(Initiative.id == initiative_id).first()

    def get_initiatives(
        self,
        *,
        status: InitiativeStatus | list[InitiativeStatus] | None = None,
        priority: InitiativePriority | list[InitiativePriority] | None = None,
        include_completed: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Initiative], int]:
        """Get initiatives with filtering.

        Returns:
            Tuple of (initiatives, total_count)
        """
        query = self.db.query(Initiative)

        # Status filter
        if status is not None:
            if isinstance(status, list):
                query = query.filter(Initiative.status.in_(status))
            else:
                query = query.filter(Initiative.status == status)
        elif not include_completed:
            query = query.filter(Initiative.status != InitiativeStatus.COMPLETED)

        # Priority filter
        if priority is not None:
            if isinstance(priority, list):
                query = query.filter(Initiative.priority.in_(priority))
            else:
                query = query.filter(Initiative.priority == priority)

        # Get total count before pagination
        total = query.count()

        # Order by priority (high first) and created_at
        priority_order = {
            InitiativePriority.HIGH: 1,
            InitiativePriority.MEDIUM: 2,
            InitiativePriority.LOW: 3,
        }
        initiatives = (
            query.order_by(Initiative.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        # Sort by priority in Python since SQLite doesn't support CASE in ORDER BY well
        initiatives.sort(key=lambda i: (priority_order.get(i.priority, 2), -i.created_at.timestamp()))

        return initiatives, total

    def get_active_initiatives(self) -> list[Initiative]:
        """Get all active initiatives ordered by priority."""
        initiatives = (
            self.db.query(Initiative)
            .filter(Initiative.status == InitiativeStatus.ACTIVE)
            .all()
        )
        priority_order = {
            InitiativePriority.HIGH: 1,
            InitiativePriority.MEDIUM: 2,
            InitiativePriority.LOW: 3,
        }
        initiatives.sort(key=lambda i: (priority_order.get(i.priority, 2), -i.created_at.timestamp()))
        return initiatives

    def create_initiative(
        self,
        title: str,
        description: str | None = None,
        priority: InitiativePriority = InitiativePriority.MEDIUM,
        target_date: datetime | None = None,
    ) -> Initiative:
        """Create a new initiative."""
        initiative = Initiative(
            title=title,
            description=description,
            priority=priority,
            target_date=target_date,
        )

        self.db.add(initiative)
        self.db.commit()
        self.db.refresh(initiative)

        return initiative

    def update_initiative(
        self,
        initiative: Initiative,
        *,
        title: str | None = None,
        description: str | None = None,
        status: InitiativeStatus | None = None,
        priority: InitiativePriority | None = None,
        target_date: datetime | None = None,
    ) -> Initiative:
        """Update an initiative."""
        if title is not None:
            initiative.title = title
        if description is not None:
            initiative.description = description
        if status is not None:
            initiative.status = status
        if priority is not None:
            initiative.priority = priority
        if target_date is not None:
            initiative.target_date = target_date

        self.db.commit()
        self.db.refresh(initiative)

        return initiative

    def delete_initiative(self, initiative: Initiative) -> None:
        """Delete an initiative.

        Note: Tasks linked to this initiative will have their initiative_id set to NULL
        due to the ON DELETE SET NULL constraint.
        """
        self.db.delete(initiative)
        self.db.commit()

    def get_tasks_for_initiative(
        self,
        initiative_id: int,
        *,
        include_completed: bool = True,
    ) -> list[Task]:
        """Get all tasks linked to an initiative."""
        query = self.db.query(Task).filter(Task.initiative_id == initiative_id)

        if not include_completed:
            query = query.filter(Task.status != TaskStatus.COMPLETED)

        return query.order_by(Task.priority_score.desc()).all()

    def get_initiative_progress(self, initiative_id: int) -> dict:
        """Calculate progress for an initiative.

        Returns:
            Dict with total_tasks, completed_tasks, and progress_percent
        """
        total_tasks = (
            self.db.query(func.count(Task.id))
            .filter(Task.initiative_id == initiative_id)
            .scalar()
        )

        if total_tasks == 0:
            return {
                "total_tasks": 0,
                "completed_tasks": 0,
                "progress_percent": 0.0,
            }

        completed_tasks = (
            self.db.query(func.count(Task.id))
            .filter(
                Task.initiative_id == initiative_id,
                Task.status == TaskStatus.COMPLETED,
            )
            .scalar()
        )

        progress_percent = (completed_tasks / total_tasks) * 100

        return {
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "progress_percent": round(progress_percent, 1),
        }

    def get_initiatives_with_progress(
        self,
        *,
        status: InitiativeStatus | None = None,
        include_completed: bool = True,
    ) -> list[dict]:
        """Get initiatives with their progress stats.

        Returns:
            List of dicts with initiative data and progress info
        """
        if status:
            initiatives, _ = self.get_initiatives(status=status, include_completed=include_completed)
        else:
            initiatives, _ = self.get_initiatives(include_completed=include_completed)

        result = []
        for initiative in initiatives:
            progress = self.get_initiative_progress(initiative.id)
            result.append({
                "initiative": initiative,
                "progress": progress,
            })

        return result
