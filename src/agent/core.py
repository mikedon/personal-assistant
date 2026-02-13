"""Core autonomous agent that coordinates integrations, LLM processing, and task management.

The agent runs on a configurable schedule, polling integrations for actionable items,
using LLM to extract and prioritize tasks, and generating productivity recommendations.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from src.integrations.base import ActionableItem, IntegrationType
from src.integrations.manager import IntegrationKey, IntegrationManager
from src.models.database import get_db_session
from src.models.task import TaskPriority, TaskSource
from src.services.agent_log_service import AgentLogService
from src.services.initiative_service import InitiativeService
from src.services.llm_service import ExtractedTask, HttpLogCallback, LLMError, LLMService, ProductivityRecommendation
from src.services.pending_suggestion_service import PendingSuggestionService
from src.services.task_service import TaskService
from src.utils.config import AgentConfig, Config
from src.utils.pid_manager import get_pid_manager, PIDFileError

logger = logging.getLogger(__name__)


class AutonomyLevel(str, Enum):
    """Agent autonomy levels.

    - SUGGEST: Only suggest actions, don't create tasks automatically
    - AUTO_LOW: Auto-create tasks with high confidence (>0.8), suggest others
    - AUTO: Auto-create all tasks extracted by LLM
    - FULL: Auto-create tasks and apply priority suggestions
    """

    SUGGEST = "suggest"
    AUTO_LOW = "auto_low"
    AUTO = "auto"
    FULL = "full"


@dataclass
class AgentState:
    """Current state of the autonomous agent."""

    is_running: bool = False
    last_poll: datetime | None = None
    last_recommendation: datetime | None = None
    tasks_created_session: int = 0
    items_processed_session: int = 0
    errors_session: int = 0
    started_at: datetime | None = None


@dataclass
class PendingSuggestion:
    """A pending task suggestion with full context for review."""

    # Task details from LLM extraction
    title: str
    description: str | None = None
    priority: str = "medium"
    due_date: datetime | None = None
    tags: list[str] | None = None
    confidence: float = 0.5

    # Source context
    source: IntegrationType | None = None
    source_reference: str | None = None  # ID in source system (e.g., Gmail message ID)
    source_url: str | None = None  # Direct URL to source (e.g., Gmail URL)

    # Reasoning and context
    reasoning: str | None = None  # Why agent suggests this task
    original_title: str | None = None  # Original item title (e.g., email subject)
    original_sender: str | None = None  # Who sent the original item
    original_snippet: str | None = None  # Preview of original content

    def to_extracted_task(self) -> ExtractedTask:
        """Convert to ExtractedTask for task creation."""
        return ExtractedTask(
            title=self.title,
            description=self.description,
            priority=self.priority,
            due_date=self.due_date,
            tags=self.tags,
            confidence=self.confidence,
        )


@dataclass
class PollResult:
    """Result of a polling cycle."""

    integration: IntegrationType
    items_found: list[ActionableItem] = field(default_factory=list)
    tasks_created: list[int] = field(default_factory=list)
    tasks_suggested: list[PendingSuggestion] = field(default_factory=list)
    duration_seconds: float = 0.0
    error: str | None = None


class AutonomousAgent:
    """Autonomous agent that monitors integrations and manages tasks.

    The agent operates on a schedule, polling configured integrations,
    extracting tasks using LLM, and managing the user's task list.
    """

    def __init__(
        self,
        config: Config,
        db_session_factory: Callable[[], Session] | None = None,
    ):
        """Initialize the autonomous agent.

        Args:
            config: Application configuration
            db_session_factory: Optional factory for database sessions
        """
        self.config = config
        self.agent_config = config.agent
        self._db_session_factory = db_session_factory

        # Initialize components
        self.llm_service = LLMService(config.llm, http_log_callback=self._create_http_log_callback())
        self.integration_manager = IntegrationManager(
            config.model_dump(),
            http_log_callback=self._create_http_log_callback(),
        )

        # State
        self.state = AgentState()
        self._autonomy_level = AutonomyLevel(self.agent_config.autonomy_level)

        # Scheduler
        self._scheduler: AsyncIOScheduler | None = None

        # Pending recommendations (suggestions are now persisted to database)
        self._pending_recommendations: list[ProductivityRecommendation] = []

        # PID manager for process tracking
        self._pid_manager = get_pid_manager()

    @property
    def autonomy_level(self) -> AutonomyLevel:
        """Get the current autonomy level."""
        return self._autonomy_level

    @autonomy_level.setter
    def autonomy_level(self, level: AutonomyLevel | str) -> None:
        """Set the autonomy level."""
        if isinstance(level, str):
            level = AutonomyLevel(level)
        self._autonomy_level = level
        logger.info(f"Autonomy level set to: {level.value}")

    def _get_db_session(self) -> Session:
        """Get a database session."""
        if self._db_session_factory:
            return self._db_session_factory()
        # Use context manager from database module
        with get_db_session() as session:
            return session

    def _create_http_log_callback(self) -> HttpLogCallback:
        """Create an HTTP logging callback function.

        Returns:
            Callback function that logs HTTP requests to the database
        """
        def log_http_request(
            method: str,
            url: str,
            status_code: int | None,
            duration_seconds: float | None,
            service: str | None,
            request_type: str | None,
        ) -> None:
            """Log an HTTP request to the agent log."""
            try:
                with get_db_session() as db:
                    log_service = AgentLogService(db)
                    log_service.log_http_request(
                        method=method,
                        url=url,
                        status_code=status_code,
                        duration_seconds=duration_seconds,
                        service=service,
                        request_type=request_type,
                    )
            except Exception as e:
                logger.warning(f"Failed to log HTTP request: {e}")

        return log_http_request

    async def start(self) -> None:
        """Start the autonomous agent.

        Begins scheduled polling of integrations and recommendation generation.
        """
        if self.state.is_running:
            logger.warning("Agent is already running")
            return

        # Check if another agent process is already running
        existing_pid = self._pid_manager.get_agent_pid()
        if existing_pid is not None:
            logger.warning(f"Agent is already running in process {existing_pid}")
            raise RuntimeError(f"Agent is already running (PID: {existing_pid})")

        logger.info("Starting autonomous agent...")
        self.state = AgentState(
            is_running=True,
            started_at=datetime.now(UTC),
        )

        # Write PID file
        try:
            self._pid_manager.write_pid_file()
        except PIDFileError as e:
            logger.error(f"Failed to write PID file: {e}")
            self.state.is_running = False
            raise

        # Initialize scheduler
        self._scheduler = AsyncIOScheduler()

        # Add polling job
        poll_interval = self.agent_config.poll_interval_minutes
        self._scheduler.add_job(
            self._poll_cycle,
            trigger=IntervalTrigger(minutes=poll_interval),
            id="poll_integrations",
            name="Poll integrations for actionable items",
            replace_existing=True,
        )

        # Add recommendation job (less frequent)
        recommendation_interval = self.agent_config.reminder_interval_hours * 60
        self._scheduler.add_job(
            self._recommendation_cycle,
            trigger=IntervalTrigger(minutes=recommendation_interval),
            id="generate_recommendations",
            name="Generate productivity recommendations",
            replace_existing=True,
        )

        # Add priority recalculation job (hourly)
        self._scheduler.add_job(
            self._recalculate_priorities,
            trigger=IntervalTrigger(hours=1),
            id="recalculate_priorities",
            name="Recalculate task priorities",
            replace_existing=True,
        )

        self._scheduler.start()

        # Log start
        with get_db_session() as db:
            log_service = AgentLogService(db)
            log_service.log_info(
                f"Agent started with autonomy level: {self._autonomy_level.value}",
                details={
                    "poll_interval_minutes": poll_interval,
                    "autonomy_level": self._autonomy_level.value,
                },
            )

        # Run initial poll
        await self._poll_cycle()

        logger.info(
            f"Agent started. Polling every {poll_interval} minutes. "
            f"Autonomy: {self._autonomy_level.value}"
        )

    async def stop(self) -> None:
        """Stop the autonomous agent."""
        if not self.state.is_running:
            logger.warning("Agent is not running")
            return

        logger.info("Stopping autonomous agent...")

        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None

        # Log stop
        with get_db_session() as db:
            log_service = AgentLogService(db)
            log_service.log_info(
                "Agent stopped",
                details={
                    "tasks_created": self.state.tasks_created_session,
                    "items_processed": self.state.items_processed_session,
                    "errors": self.state.errors_session,
                },
            )

        self.state.is_running = False

        # Remove PID file
        self._pid_manager.remove_pid_file()

        logger.info("Agent stopped")

    async def _poll_cycle(self) -> list[PollResult]:
        """Execute a polling cycle across all integrations.

        Returns:
            List of poll results per integration
        """
        logger.info("Starting poll cycle...")
        results: list[PollResult] = []

        try:
            # Poll all integrations
            all_items = await self.integration_manager.poll_all()

            # Group items by integration type for processing
            from collections import defaultdict
            items_by_integration: dict[IntegrationType, list[ActionableItem]] = defaultdict(list)
            for item in all_items:
                if item.source:
                    items_by_integration[item.source].append(item)

            # Get all registered integration types to ensure we report on all of them
            registered_integrations = set()
            for key in self.integration_manager.integrations.keys():
                registered_integrations.add(key.type)

            # Process each integration (including those with 0 items)
            for integration_type in registered_integrations:
                start_time = time.time()
                items = items_by_integration.get(integration_type, [])

                result = PollResult(
                    integration=integration_type,
                    items_found=items,
                )

                if items:
                    # Process items through LLM and create/suggest tasks
                    try:
                        tasks_created, tasks_suggested = await self._process_actionable_items(
                            items, integration_type
                        )
                        result.tasks_created = tasks_created
                        result.tasks_suggested = tasks_suggested

                        # If this is Granola, mark notes as processed
                        if integration_type == IntegrationType.GRANOLA:
                            self._mark_granola_notes_processed(items, tasks_created)

                    except Exception as e:
                        logger.error(f"Error processing items from {integration_type}: {e}")
                        result.error = str(e)
                        self.state.errors_session += 1

                result.duration_seconds = time.time() - start_time
                results.append(result)

                # Log the poll
                with get_db_session() as db:
                    log_service = AgentLogService(db)
                    log_service.log_poll(
                        integration=integration_type.value,
                        items_found=len(items),
                        duration_seconds=result.duration_seconds,
                    )

            self.state.last_poll = datetime.now(UTC)

        except Exception as e:
            logger.error(f"Poll cycle failed: {e}")
            self.state.errors_session += 1

        return results

    def _generate_source_url(
        self,
        source: IntegrationType,
        source_reference: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Generate a URL to the source item.

        Args:
            source: The integration type
            source_reference: The source-specific reference ID
            metadata: Additional metadata that may contain thread_id etc.

        Returns:
            URL string or None if not available
        """
        if not source_reference:
            return None

        if source == IntegrationType.GMAIL:
            # Gmail URL format: https://mail.google.com/mail/u/0/#inbox/<message_id>
            # Or thread view: https://mail.google.com/mail/u/0/#inbox/<thread_id>
            thread_id = metadata.get("thread_id") if metadata else None
            ref_id = thread_id or source_reference
            return f"https://mail.google.com/mail/u/0/#inbox/{ref_id}"

        elif source == IntegrationType.SLACK:
            # Slack URL format: https://app.slack.com/client/<workspace>/<channel>/thread/<ts>
            # source_reference format: "channel_id:timestamp"
            if ":" in source_reference:
                channel, ts = source_reference.split(":", 1)
                # Note: This is a simplified URL; actual Slack URLs require workspace ID
                return f"https://app.slack.com/client/T0/C{channel}/thread/{ts}"
            return None

        elif source == IntegrationType.CALENDAR:
            # Google Calendar event URL
            return f"https://calendar.google.com/calendar/event?eid={source_reference}"

        elif source == IntegrationType.DRIVE:
            # Google Drive file URL
            return f"https://drive.google.com/file/d/{source_reference}/view"

        return None

    def _build_suggestion_reasoning(
        self,
        task: ExtractedTask,
        item: ActionableItem,
        source: IntegrationType,
    ) -> str:
        """Build reasoning text for why a task suggestion was created.

        Args:
            task: The extracted task
            item: The original actionable item
            source: Source integration type

        Returns:
            Reasoning string
        """
        reasons = []

        # Confidence-based reasoning
        if task.confidence >= 0.8:
            reasons.append(f"High confidence ({task.confidence:.0%}) that this requires action")
        elif task.confidence >= 0.6:
            reasons.append(f"Moderate confidence ({task.confidence:.0%}) that this may require action")
        else:
            reasons.append(f"Low confidence ({task.confidence:.0%}) - may need review")

        # Source-based reasoning
        source_reasons = {
            IntegrationType.GMAIL: "Found in email that appears to require a response or action",
            IntegrationType.SLACK: "Found in Slack message that may need follow-up",
            IntegrationType.CALENDAR: "Related to an upcoming calendar event",
            IntegrationType.DRIVE: "Found in document that contains action items",
        }
        if source in source_reasons:
            reasons.append(source_reasons[source])

        # Priority-based reasoning
        if task.priority == "critical":
            reasons.append("Marked as critical due to urgency indicators")
        elif task.priority == "high":
            reasons.append("Marked as high priority based on deadline or importance")

        # Due date reasoning
        if task.due_date:
            reasons.append(f"Has a detected deadline: {task.due_date.strftime('%Y-%m-%d')}")

        return ". ".join(reasons) + "."

    async def _process_actionable_items(
        self,
        items: list[ActionableItem],
        source: IntegrationType,
    ) -> tuple[list[int], list[PendingSuggestion]]:
        """Process actionable items and extract/create tasks.

        Args:
            items: List of actionable items from integration
            source: Source integration type

        Returns:
            Tuple of (created_task_ids, suggested_tasks)
        """
        created_task_ids: list[int] = []
        suggested_tasks: list[PendingSuggestion] = []

        for item in items:
            self.state.items_processed_session += 1

            # Build text for LLM extraction
            text = f"Subject: {item.title}\n"
            if item.description:
                text += f"\n{item.description}"
            if item.metadata:
                if item.metadata.get("sender"):
                    text += f"\nFrom: {item.metadata['sender']}"

            try:
                # Extract tasks using LLM
                extracted = await self.llm_service.extract_tasks_from_text(
                    text=text,
                    source=source.value,
                    context=f"Source reference: {item.source_reference}" if item.source_reference else None,
                )

                # Log LLM usage
                with get_db_session() as db:
                    log_service = AgentLogService(db)
                    log_service.log_llm_request(
                        message=f"Task extraction from {source.value}",
                        tokens_used=0,  # Would need to track this from LLM response
                        model=self.config.llm.model,
                        details={"source": source.value, "tasks_extracted": len(extracted)},
                    )

                # Process each extracted task based on autonomy level
                with get_db_session() as decision_db:
                    for task in extracted:
                        if self._should_auto_create_task(task, db=decision_db):
                            task_id = await self._create_task_from_extracted(task, source, item)
                            if task_id:
                                created_task_ids.append(task_id)
                        else:
                            # Create enhanced suggestion with full context
                            # Save suggestion to database for persistence across processes
                            with get_db_session() as suggestion_db:
                                suggestion_service = PendingSuggestionService(suggestion_db)
                                db_suggestion = suggestion_service.create_suggestion(
                                    title=task.title,
                                    description=task.description,
                                    priority=task.priority,
                                    due_date=task.due_date,
                                    tags=task.tags,
                                    confidence=task.confidence,
                                    source=source,
                                    source_reference=item.source_reference,
                                    source_url=self._generate_source_url(
                                        source, item.source_reference, item.metadata
                                    ),
                                    reasoning=self._build_suggestion_reasoning(task, item, source),
                                    original_title=item.title,
                                    original_sender=item.metadata.get("sender") if item.metadata else None,
                                    original_snippet=(
                                        item.description[:200] + "..."
                                        if item.description and len(item.description) > 200
                                        else item.description
                                    ),
                                )
                            
                            # Create dataclass for return value
                            suggestion = PendingSuggestion(
                                title=task.title,
                                description=task.description,
                                priority=task.priority,
                                due_date=task.due_date,
                                tags=task.tags,
                                confidence=task.confidence,
                                source=source,
                                source_reference=item.source_reference,
                                source_url=self._generate_source_url(
                                    source, item.source_reference, item.metadata
                                ),
                                reasoning=self._build_suggestion_reasoning(task, item, source),
                                original_title=item.title,
                                original_sender=item.metadata.get("sender") if item.metadata else None,
                                original_snippet=(
                                    item.description[:200] + "..."
                                    if item.description and len(item.description) > 200
                                    else item.description
                                ),
                            )
                            suggested_tasks.append(suggestion)

            except LLMError as e:
                logger.error(f"LLM extraction failed: {e}")
                # Fall back to creating basic task from actionable item
                if self._autonomy_level in [AutonomyLevel.AUTO, AutonomyLevel.FULL]:
                    task_id = await self._create_task_from_actionable_item(item)
                    if task_id:
                        created_task_ids.append(task_id)

        return created_task_ids, suggested_tasks

    def _mark_granola_notes_processed(
        self,
        items: list[ActionableItem],
        created_task_ids: list[int],
    ) -> None:
        """Mark Granola notes as processed in the database.

        Args:
            items: List of actionable items from Granola
            created_task_ids: List of task IDs that were created
        """
        # Build mapping of source_reference to task count
        tasks_per_note: dict[str, int] = {}
        for item in items:
            if item.source_reference:
                tasks_per_note[item.source_reference] = tasks_per_note.get(item.source_reference, 0) + len(
                    created_task_ids
                ) // len(items)  # Rough distribution

        # Mark each note as processed
        for item in items:
            if not item.source_reference or not item.account_id:
                continue

            # Get the Granola integration
            key = IntegrationKey(IntegrationType.GRANOLA, item.account_id)
            integration = self.integration_manager.integrations.get(key)

            if not integration:
                logger.warning(f"Granola integration not found for account: {item.account_id}")
                continue

            try:
                # Extract note metadata from actionable item
                note_title = item.title.replace("Review meeting: ", "")
                note_created_at = None
                if item.metadata and "created_at" in item.metadata:
                    note_created_at = datetime.fromisoformat(item.metadata["created_at"])

                if not note_created_at:
                    note_created_at = datetime.now(UTC)

                # Mark note as processed
                integration.mark_note_processed(
                    note_id=item.source_reference,
                    note_title=note_title,
                    note_created_at=note_created_at,
                    tasks_created=tasks_per_note.get(item.source_reference, 0),
                )
            except Exception as e:
                logger.error(f"Failed to mark Granola note {item.source_reference} as processed: {e}")

    def _should_auto_create_task(self, task: ExtractedTask, db: Session | None = None) -> bool:
        """Determine if a task should be auto-created based on autonomy level.

        Args:
            task: The extracted task
            db: Optional database session for logging

        Returns:
            True if task should be auto-created
        """
        should_create = False
        reasoning = ""

        if self._autonomy_level == AutonomyLevel.SUGGEST:
            should_create = False
            reasoning = "Autonomy level is SUGGEST - all tasks require manual approval"
        elif self._autonomy_level == AutonomyLevel.AUTO_LOW:
            should_create = task.confidence >= 0.8
            reasoning = f"Autonomy level is AUTO_LOW - confidence {task.confidence:.2f} {'>='}  0.8 threshold" if should_create else f"Autonomy level is AUTO_LOW - confidence {task.confidence:.2f} below 0.8 threshold"
        else:  # AUTO or FULL
            should_create = True
            reasoning = f"Autonomy level is {self._autonomy_level.value} - auto-creating all extracted tasks"

        # Log the decision
        if db:
            log_service = AgentLogService(db)
            log_service.log_decision(
                decision="auto_create_task",
                reasoning=reasoning,
                outcome="approved" if should_create else "rejected",
                context={
                    "task_title": task.title[:100],
                    "confidence": task.confidence,
                    "autonomy_level": self._autonomy_level.value,
                },
            )

        return should_create

    async def _create_task_from_extracted(
        self,
        extracted: ExtractedTask,
        source: IntegrationType,
        original_item: ActionableItem,
    ) -> int | None:
        """Create a task from an extracted task.

        Args:
            extracted: The extracted task
            source: Source integration type
            original_item: Original actionable item

        Returns:
            Created task ID or None if failed
        """
        # Map priority
        priority_map = {
            "critical": TaskPriority.CRITICAL,
            "high": TaskPriority.HIGH,
            "medium": TaskPriority.MEDIUM,
            "low": TaskPriority.LOW,
        }
        priority = priority_map.get(extracted.priority, TaskPriority.MEDIUM)

        # Map source
        source_map = {
            IntegrationType.GMAIL: TaskSource.EMAIL,
            IntegrationType.SLACK: TaskSource.SLACK,
            IntegrationType.CALENDAR: TaskSource.CALENDAR,
            IntegrationType.DRIVE: TaskSource.MEETING_NOTES,
        }
        task_source = source_map.get(source, TaskSource.AGENT)

        try:
            with get_db_session() as db:
                task_service = TaskService(db)
                task = task_service.create_task(
                    title=extracted.title,
                    description=extracted.description,
                    priority=priority,
                    source=task_source,
                    source_reference=original_item.source_reference,
                    due_date=extracted.due_date,
                    tags=extracted.tags or [],
                    document_links=extracted.document_links or [],
                )

                # Log task creation
                log_service = AgentLogService(db)
                log_service.log_task_creation(
                    task_id=task.id,
                    task_title=task.title,
                    source=source.value,
                )

                self.state.tasks_created_session += 1
                return task.id

        except Exception as e:
            logger.error(f"Failed to create task: {e}")
            return None

    async def _create_task_from_actionable_item(
        self,
        item: ActionableItem,
    ) -> int | None:
        """Create a task directly from an actionable item (fallback).

        Args:
            item: The actionable item

        Returns:
            Created task ID or None if failed
        """
        params = IntegrationManager.actionable_item_to_task_params(item)

        try:
            with get_db_session() as db:
                task_service = TaskService(db)
                task = task_service.create_task(**params)

                log_service = AgentLogService(db)
                log_service.log_task_creation(
                    task_id=task.id,
                    task_title=task.title,
                    source=item.source.value if item.source else "unknown",
                )

                self.state.tasks_created_session += 1
                return task.id

        except Exception as e:
            logger.error(f"Failed to create task from actionable item: {e}")
            return None

    async def _recommendation_cycle(self) -> list[ProductivityRecommendation]:
        """Generate productivity recommendations.

        Returns:
            List of generated recommendations
        """
        logger.info("Generating productivity recommendations...")

        try:
            with get_db_session() as db:
                task_service = TaskService(db)
                initiative_service = InitiativeService(db)

                # Get tasks and statistics
                tasks, _ = task_service.get_tasks(include_completed=False, limit=50)
                statistics = task_service.get_statistics()

                # Get active initiatives with progress
                initiatives_with_progress = initiative_service.get_initiatives_with_progress(
                    include_completed=False
                )

                # Convert tasks to dicts for LLM
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
                        "initiative": t.initiative.title if t.initiative else None,
                    }
                    for t in tasks
                ]

                # Convert initiatives to dicts for LLM
                initiative_dicts = [
                    {
                        "id": item["initiative"].id,
                        "title": item["initiative"].title,
                        "description": item["initiative"].description,
                        "priority": item["initiative"].priority.value,
                        "status": item["initiative"].status.value,
                        "target_date": item["initiative"].target_date.isoformat() if item["initiative"].target_date else None,
                        "progress": item["progress"],
                    }
                    for item in initiatives_with_progress
                ]

            # Generate recommendations with initiative context
            recommendations = await self.llm_service.generate_recommendations(
                tasks=task_dicts,
                statistics=statistics,
                initiatives=initiative_dicts,
            )

            # Store pending recommendations
            self._pending_recommendations = recommendations
            self.state.last_recommendation = datetime.now(UTC)

            # Generate summary document if configured
            output_path = Path(self.agent_config.output_document_path).expanduser()
            await self._write_summary_document(
                output_path, task_dicts, statistics, recommendations, initiative_dicts
            )

            logger.info(f"Generated {len(recommendations)} recommendations")
            return recommendations

        except Exception as e:
            logger.error(f"Recommendation cycle failed: {e}")
            self.state.errors_session += 1
            return []

    async def _recalculate_priorities(self) -> int:
        """Recalculate task priorities.

        Returns:
            Number of tasks updated
        """
        try:
            with get_db_session() as db:
                task_service = TaskService(db)
                updated = task_service.recalculate_all_priorities()

                if self._autonomy_level == AutonomyLevel.FULL:
                    # Also apply LLM priority suggestions
                    tasks, _ = task_service.get_tasks(include_completed=False, limit=20)
                    task_dicts = [
                        {
                            "id": t.id,
                            "title": t.title,
                            "priority": t.priority.value,
                            "due_date": t.due_date.isoformat() if t.due_date else None,
                        }
                        for t in tasks
                    ]

                    suggestions = await self.llm_service.suggest_priority_updates(task_dicts)

                    for suggestion in suggestions:
                        if suggestion.confidence >= 0.7:
                            task = task_service.get_task(suggestion.task_id)
                            if task:
                                priority_map = {
                                    "critical": TaskPriority.CRITICAL,
                                    "high": TaskPriority.HIGH,
                                    "medium": TaskPriority.MEDIUM,
                                    "low": TaskPriority.LOW,
                                }
                                new_priority = priority_map.get(suggestion.suggested_priority)
                                if new_priority and new_priority != task.priority:
                                    task_service.update_task(task, priority=new_priority)
                                    logger.info(
                                        f"Updated task {task.id} priority: "
                                        f"{task.priority.value} -> {suggestion.suggested_priority}"
                                    )

                logger.info(f"Recalculated priorities for {updated} tasks")
                return updated

        except Exception as e:
            logger.error(f"Priority recalculation failed: {e}")
            return 0

    async def _write_summary_document(
        self,
        output_path: Path,
        tasks: list[dict[str, Any]],
        statistics: dict[str, Any],
        recommendations: list[ProductivityRecommendation],
        initiatives: list[dict[str, Any]] | None = None,
    ) -> None:
        """Write a markdown summary document.

        Args:
            output_path: Path to write the document
            tasks: List of task dicts
            statistics: Task statistics
            recommendations: List of recommendations
            initiatives: List of initiative dicts with progress
        """
        try:
            # Log directory creation if needed
            created_dir = not output_path.parent.exists()
            output_path.parent.mkdir(parents=True, exist_ok=True)

            if created_dir:
                with get_db_session() as db:
                    log_service = AgentLogService(db)
                    log_service.log_file_write(
                        file_path=str(output_path.parent),
                        purpose="Created directory for summary document",
                    )

            now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

            content = f"""# Personal Assistant Summary

*Generated: {now}*

## Quick Stats

- **Active Tasks:** {statistics.get('active', 0)}
- **Overdue:** {statistics.get('overdue', 0)}
- **Due Today:** {statistics.get('due_today', 0)}
- **Due This Week:** {statistics.get('due_this_week', 0)}
- **Active Initiatives:** {len([i for i in (initiatives or []) if i.get('status') == 'active'])}

"""

            # Add initiatives section
            if initiatives:
                active_initiatives = [i for i in initiatives if i.get("status") == "active"]
                if active_initiatives:
                    content += "## Active Initiatives\n\n"
                    for initiative in active_initiatives:
                        priority_emoji = {
                            "high": "🔴",
                            "medium": "🟡",
                            "low": "🟢",
                        }.get(initiative.get("priority", "medium"), "⚪")

                        progress = initiative.get("progress", {})
                        progress_pct = progress.get("progress_percent", 0)
                        total_tasks = progress.get("total_tasks", 0)
                        completed_tasks = progress.get("completed_tasks", 0)

                        content += f"### {priority_emoji} {initiative['title']}\n"
                        content += f"Progress: **{progress_pct:.0f}%** ({completed_tasks}/{total_tasks} tasks)\n"
                        if initiative.get("target_date"):
                            content += f"Target: {initiative['target_date'][:10]}\n"
                        if initiative.get("description"):
                            content += f"\n{initiative['description'][:200]}{'...' if len(initiative.get('description', '')) > 200 else ''}\n"
                        content += "\n"

            content += "## Top Priority Tasks\n\n"
            # Add top 10 tasks
            top_tasks = sorted(
                [t for t in tasks if t.get("status") not in ["completed", "cancelled"]],
                key=lambda x: x.get("priority_score", 0),
                reverse=True,
            )[:10]

            for i, task in enumerate(top_tasks, 1):
                priority_emoji = {
                    "critical": "🔴",
                    "high": "🟠",
                    "medium": "🟡",
                    "low": "🟢",
                }.get(task.get("priority", "medium"), "⚪")

                content += f"{i}. {priority_emoji} **{task['title']}**"
                if task.get("due_date"):
                    content += f" (due: {task['due_date'][:10]})"
                content += "\n"

            content += "\n## Recommendations\n\n"

            for rec in recommendations:
                category_emoji = {
                    "focus": "🎯",
                    "scheduling": "📅",
                    "delegation": "👥",
                    "organization": "📁",
                }.get(rec.category, "💡")

                content += f"### {category_emoji} {rec.title}\n\n"
                content += f"{rec.description}\n\n"

                if rec.actionable_steps:
                    content += "**Action Steps:**\n"
                    for step in rec.actionable_steps:
                        content += f"- {step}\n"
                    content += "\n"

            content += f"""---

*Agent Status: {'Running' if self.state.is_running else 'Stopped'}*
*Last Poll: {self.state.last_poll.strftime('%Y-%m-%d %H:%M UTC') if self.state.last_poll else 'Never'}*
*Tasks Created This Session: {self.state.tasks_created_session}*
"""

            output_path.write_text(content)

            # Log file write
            with get_db_session() as db:
                log_service = AgentLogService(db)
                log_service.log_file_write(
                    file_path=str(output_path),
                    bytes_written=len(content.encode("utf-8")),
                    purpose="Generated productivity summary document",
                )

            logger.info(f"Wrote summary document to {output_path}")

        except Exception as e:
            logger.error(f"Failed to write summary document: {e}")

    def get_status(self) -> dict[str, Any]:
        """Get current agent status.

        Returns:
            Dict with agent status information
        """
        return {
            "is_running": self.state.is_running,
            "autonomy_level": self._autonomy_level.value,
            "last_poll": self.state.last_poll.isoformat() if self.state.last_poll else None,
            "last_recommendation": (
                self.state.last_recommendation.isoformat()
                if self.state.last_recommendation
                else None
            ),
            "started_at": self.state.started_at.isoformat() if self.state.started_at else None,
            "session_stats": {
                "tasks_created": self.state.tasks_created_session,
                "items_processed": self.state.items_processed_session,
                "errors": self.state.errors_session,
            },
            "pending_suggestions": self._get_pending_suggestion_count(),
            "pending_recommendations": len(self._pending_recommendations),
            "integrations": {
                itype.value: self.integration_manager.is_enabled(itype)
                for itype in IntegrationType
            },
        }

    def _get_pending_suggestion_count(self) -> int:
        """Get count of pending suggestions from database.

        Returns:
            Number of pending suggestions
        """
        try:
            with get_db_session() as db:
                suggestion_service = PendingSuggestionService(db)
                return suggestion_service.get_pending_count()
        except Exception as e:
            logger.warning(f"Failed to get pending suggestion count: {e}")
            return 0

    def _model_to_suggestion(self, model: Any) -> PendingSuggestion:
        """Convert a database model to a PendingSuggestion dataclass.

        Args:
            model: PendingSuggestionModel instance

        Returns:
            PendingSuggestion dataclass
        """
        # Convert source string back to IntegrationType if present
        source = None
        if model.source:
            try:
                source = IntegrationType(model.source)
            except ValueError:
                pass

        return PendingSuggestion(
            title=model.title,
            description=model.description,
            priority=model.priority,
            due_date=model.due_date,
            tags=model.get_tags_list(),
            confidence=model.confidence,
            source=source,
            source_reference=model.source_reference,
            source_url=model.source_url,
            reasoning=model.reasoning,
            original_title=model.original_title,
            original_sender=model.original_sender,
            original_snippet=model.original_snippet,
        )

    def get_pending_suggestions(self) -> list[PendingSuggestion]:
        """Get pending task suggestions from database.

        Returns:
            List of suggested tasks not yet created
        """
        try:
            with get_db_session() as db:
                suggestion_service = PendingSuggestionService(db)
                models = suggestion_service.get_pending_suggestions()
                return [self._model_to_suggestion(m) for m in models]
        except Exception as e:
            logger.error(f"Failed to get pending suggestions: {e}")
            return []

    def clear_pending_suggestions(self) -> None:
        """Clear pending task suggestions from database."""
        try:
            with get_db_session() as db:
                suggestion_service = PendingSuggestionService(db)
                suggestion_service.clear_pending_suggestions()
        except Exception as e:
            logger.error(f"Failed to clear pending suggestions: {e}")

    def approve_suggestion(self, index: int) -> int | None:
        """Approve a pending suggestion and create the task.

        Args:
            index: Index of the suggestion in pending list

        Returns:
            Created task ID or None if failed
        """
        try:
            with get_db_session() as db:
                suggestion_service = PendingSuggestionService(db)
                suggestion_model = suggestion_service.get_suggestion_by_index(index)

                if not suggestion_model:
                    logger.warning(f"Invalid suggestion index: {index}")
                    return None

                suggestion_id = suggestion_model.id

                # Convert source string back to IntegrationType if present
                source_integration = None
                if suggestion_model.source:
                    try:
                        source_integration = IntegrationType(suggestion_model.source)
                    except ValueError:
                        pass

                # Map priority
                priority_map = {
                    "critical": TaskPriority.CRITICAL,
                    "high": TaskPriority.HIGH,
                    "medium": TaskPriority.MEDIUM,
                    "low": TaskPriority.LOW,
                }
                priority = priority_map.get(suggestion_model.priority, TaskPriority.MEDIUM)

                # Map source
                source_map = {
                    IntegrationType.GMAIL: TaskSource.EMAIL,
                    IntegrationType.SLACK: TaskSource.SLACK,
                    IntegrationType.CALENDAR: TaskSource.CALENDAR,
                    IntegrationType.DRIVE: TaskSource.MEETING_NOTES,
                }
                task_source = source_map.get(source_integration, TaskSource.AGENT) if source_integration else TaskSource.AGENT

                # Create the task
                task_service = TaskService(db)
                task = task_service.create_task(
                    title=suggestion_model.title,
                    description=suggestion_model.description,
                    priority=priority,
                    source=task_source,
                    source_reference=suggestion_model.source_reference,
                    due_date=suggestion_model.due_date,
                    tags=suggestion_model.get_tags_list() or [],
                )

                # Log task creation
                log_service = AgentLogService(db)
                log_service.log_task_creation(
                    task_id=task.id,
                    task_title=task.title,
                    source=suggestion_model.source or "manual",
                )

                # Log the approval decision
                log_service.log_decision(
                    decision="approve_suggestion",
                    reasoning="User approved the suggested task",
                    outcome="approved",
                    context={
                        "task_title": suggestion_model.title[:100],
                        "task_id": task.id,
                        "source": suggestion_model.source,
                    },
                )

                # Mark as approved in database
                suggestion_service.approve_suggestion(suggestion_id, task.id)

                self.state.tasks_created_session += 1
                return task.id

        except Exception as e:
            logger.error(f"Failed to create task from suggestion: {e}")
            return None

    def reject_suggestion(self, index: int) -> bool:
        """Reject a pending suggestion.

        Args:
            index: Index of the suggestion in pending list

        Returns:
            True if rejected successfully
        """
        try:
            with get_db_session() as db:
                suggestion_service = PendingSuggestionService(db)
                suggestion_model = suggestion_service.get_suggestion_by_index(index)

                if not suggestion_model:
                    logger.warning(f"Invalid suggestion index: {index}")
                    return False

                suggestion_id = suggestion_model.id

                # Log the rejection decision
                log_service = AgentLogService(db)
                log_service.log_decision(
                    decision="reject_suggestion",
                    reasoning="User rejected the suggested task",
                    outcome="rejected",
                    context={
                        "task_title": suggestion_model.title[:100],
                        "source": suggestion_model.source,
                    },
                )

                # Mark as rejected in database
                suggestion_service.reject_suggestion(suggestion_id)
                return True

        except Exception as e:
            logger.error(f"Failed to reject suggestion: {e}")
            return False

    def get_pending_recommendations(self) -> list[ProductivityRecommendation]:
        """Get pending recommendations.

        Returns:
            List of current recommendations
        """
        return self._pending_recommendations.copy()

    async def poll_now(self) -> list[PollResult]:
        """Trigger an immediate poll cycle.

        Returns:
            List of poll results
        """
        return await self._poll_cycle()

    async def generate_recommendations_now(self) -> list[ProductivityRecommendation]:
        """Trigger immediate recommendation generation.

        Returns:
            List of recommendations
        """
        return await self._recommendation_cycle()


# Global agent instance
_agent: AutonomousAgent | None = None


def get_agent(config: Config | None = None) -> AutonomousAgent:
    """Get the global agent instance.

    Args:
        config: Configuration (required on first call)

    Returns:
        The global AutonomousAgent instance
    """
    global _agent
    if _agent is None:
        if config is None:
            from src.utils.config import get_config
            config = get_config()
        _agent = AutonomousAgent(config)
    return _agent


def reset_agent() -> None:
    """Reset the global agent instance."""
    global _agent
    _agent = None
