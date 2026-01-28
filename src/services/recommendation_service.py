"""Recommendation service for productivity recommendations.

Provides a high-level interface for generating and retrieving recommendations
without requiring direct access to the agent or LLM service.
"""

import logging
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from src.services.llm_service import LLMService, ProductivityRecommendation
from src.services.task_service import TaskService
from src.utils.config import LLMConfig

logger = logging.getLogger(__name__)


class RecommendationService:
    """Service for generating and managing productivity recommendations."""

    def __init__(self, db: Session, llm_config: LLMConfig):
        """Initialize the recommendation service.

        Args:
            db: Database session
            llm_config: LLM configuration
        """
        self.db = db
        self.llm_service = LLMService(llm_config)
        self.task_service = TaskService(db)
        self._cached_recommendations: list[ProductivityRecommendation] = []
        self._cache_timestamp: datetime | None = None

    async def generate_recommendations(
        self,
        force_refresh: bool = False,
        cache_minutes: int = 30,
    ) -> list[ProductivityRecommendation]:
        """Generate productivity recommendations.

        Args:
            force_refresh: Force regeneration even if cache is valid
            cache_minutes: Cache duration in minutes

        Returns:
            List of productivity recommendations
        """
        # Check cache
        if not force_refresh and self._is_cache_valid(cache_minutes):
            return self._cached_recommendations

        # Get task data
        tasks, _ = self.task_service.get_tasks(include_completed=False, limit=50)
        statistics = self.task_service.get_statistics()

        # Convert to dicts
        task_dicts = [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "status": t.status.value,
                "priority": t.priority.value,
                "priority_score": t.priority_score,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "source": t.source.value,
                "tags": t.get_tags_list(),
            }
            for t in tasks
        ]

        # Generate recommendations
        recommendations = await self.llm_service.generate_recommendations(
            tasks=task_dicts,
            statistics=statistics,
        )

        # Update cache
        self._cached_recommendations = recommendations
        self._cache_timestamp = datetime.now(UTC)

        return recommendations

    def _is_cache_valid(self, cache_minutes: int) -> bool:
        """Check if cached recommendations are still valid.

        Args:
            cache_minutes: Cache duration in minutes

        Returns:
            True if cache is valid
        """
        if not self._cache_timestamp or not self._cached_recommendations:
            return False

        age = (datetime.now(UTC) - self._cache_timestamp).total_seconds() / 60
        return age < cache_minutes

    def get_cached_recommendations(self) -> list[ProductivityRecommendation]:
        """Get cached recommendations without regenerating.

        Returns:
            List of cached recommendations (may be empty)
        """
        return self._cached_recommendations.copy()

    async def get_focus_recommendations(self) -> list[ProductivityRecommendation]:
        """Get recommendations focused on task prioritization.

        Returns:
            List of focus-related recommendations
        """
        all_recs = await self.generate_recommendations()
        return [r for r in all_recs if r.category == "focus"]

    async def get_scheduling_recommendations(self) -> list[ProductivityRecommendation]:
        """Get recommendations focused on scheduling.

        Returns:
            List of scheduling-related recommendations
        """
        all_recs = await self.generate_recommendations()
        return [r for r in all_recs if r.category == "scheduling"]

    async def get_quick_wins(self) -> list[dict[str, Any]]:
        """Get quick win suggestions based on task analysis.

        Quick wins are low-effort, high-impact tasks that can be completed quickly.

        Returns:
            List of quick win task dicts
        """
        tasks, _ = self.task_service.get_tasks(
            include_completed=False,
            limit=50,
        )

        # Filter for potentially quick tasks
        # (no explicit duration info, so use heuristics)
        quick_wins = []
        for task in tasks:
            tags = task.get_tags_list()
            title_lower = task.title.lower()

            # Heuristics for quick wins
            is_quick = any([
                "quick" in tags,
                "easy" in tags,
                len(task.title) < 50,  # Short titles often = simple tasks
                "reply" in title_lower,
                "respond" in title_lower,
                "review" in title_lower and "document" not in title_lower,
                "approve" in title_lower,
                "confirm" in title_lower,
            ])

            if is_quick and task.priority_score > 30:
                quick_wins.append({
                    "id": task.id,
                    "title": task.title,
                    "priority": task.priority.value,
                    "priority_score": task.priority_score,
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                })

        # Sort by priority score
        quick_wins.sort(key=lambda x: x["priority_score"], reverse=True)
        return quick_wins[:5]

    async def get_overdue_action_plan(self) -> dict[str, Any]:
        """Get an action plan for handling overdue tasks.

        Returns:
            Dict with overdue tasks and suggested approach
        """
        overdue = self.task_service.get_overdue_tasks()

        if not overdue:
            return {
                "overdue_count": 0,
                "message": "No overdue tasks! Great job staying on top of things.",
                "tasks": [],
                "suggested_actions": [],
            }

        # Group by age
        task_details = []
        for task in overdue:
            days_overdue = (datetime.now(UTC).replace(tzinfo=None) - task.due_date).days
            task_details.append({
                "id": task.id,
                "title": task.title,
                "priority": task.priority.value,
                "days_overdue": days_overdue,
                "source": task.source.value,
            })

        # Sort by days overdue (most overdue first)
        task_details.sort(key=lambda x: x["days_overdue"], reverse=True)

        # Generate suggested actions
        suggested_actions = []
        critical_overdue = [t for t in task_details if t["days_overdue"] > 7]
        if critical_overdue:
            suggested_actions.append(
                f"Urgent: {len(critical_overdue)} tasks are more than a week overdue. "
                "Consider renegotiating deadlines or delegating."
            )

        if len(overdue) > 5:
            suggested_actions.append(
                "You have many overdue tasks. Consider blocking 2-3 hours to focus on clearing the backlog."
            )

        suggested_actions.append(
            f"Start with: '{task_details[0]['title']}' (oldest overdue task)"
        )

        return {
            "overdue_count": len(overdue),
            "message": f"You have {len(overdue)} overdue task{'s' if len(overdue) > 1 else ''}.",
            "tasks": task_details,
            "suggested_actions": suggested_actions,
        }

    async def get_daily_summary(self) -> dict[str, Any]:
        """Get a daily summary with key metrics and recommendations.

        Returns:
            Dict with daily summary data
        """
        statistics = self.task_service.get_statistics()
        due_today = self.task_service.get_due_soon_tasks(days=0)
        due_soon = self.task_service.get_due_soon_tasks(days=3)
        overdue = self.task_service.get_overdue_tasks()
        top_priority = self.task_service.get_prioritized_tasks(limit=5)

        # Get recommendations
        recommendations = await self.generate_recommendations()

        return {
            "date": datetime.now(UTC).strftime("%Y-%m-%d"),
            "statistics": {
                "active_tasks": statistics.get("active", 0),
                "overdue": statistics.get("overdue", 0),
                "due_today": statistics.get("due_today", 0),
                "due_this_week": statistics.get("due_this_week", 0),
            },
            "due_today": [
                {"id": t.id, "title": t.title, "priority": t.priority.value}
                for t in due_today
            ],
            "coming_up": [
                {"id": t.id, "title": t.title, "due_date": t.due_date.isoformat() if t.due_date else None}
                for t in due_soon[:5]
            ],
            "top_priorities": [
                {
                    "id": t.id,
                    "title": t.title,
                    "priority": t.priority.value,
                    "priority_score": t.priority_score,
                }
                for t in top_priority
            ],
            "overdue_count": len(overdue),
            "recommendations": [
                asdict(r) for r in recommendations[:3]
            ],
        }

    def clear_cache(self) -> None:
        """Clear the recommendation cache."""
        self._cached_recommendations = []
        self._cache_timestamp = None
