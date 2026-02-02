"""LLM service for intelligent task extraction and recommendations.

Uses litellm for OpenAI API-compatible calls, supporting any provider.
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

import litellm
from litellm import acompletion

from src.utils.config import LLMConfig

# Type for HTTP logging callback
HttpLogCallback = Callable[[str, str, int | None, float | None, str | None, str | None], None]

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Response from an LLM call."""

    content: str
    tokens_used: int
    model: str
    raw_response: dict[str, Any] | None = None


@dataclass
class ExtractedTask:
    """A task extracted from text by the LLM."""

    title: str
    description: str | None = None
    priority: str = "medium"  # critical, high, medium, low
    due_date: datetime | None = None
    tags: list[str] | None = None
    confidence: float = 0.5  # 0.0 to 1.0


@dataclass
class PrioritySuggestion:
    """A prioritization suggestion from the LLM."""

    task_id: int
    current_priority: str
    suggested_priority: str
    reason: str
    confidence: float = 0.5


@dataclass
class ProductivityRecommendation:
    """A productivity recommendation from the LLM."""

    title: str
    description: str
    category: str  # focus, scheduling, delegation, organization
    priority: str = "medium"
    actionable_steps: list[str] | None = None


class LLMService:
    """Service for LLM-powered task extraction and recommendations."""

    def __init__(self, config: LLMConfig, http_log_callback: HttpLogCallback | None = None):
        """Initialize the LLM service.

        Args:
            config: LLM configuration with API key, model, etc.
            http_log_callback: Optional callback for logging HTTP requests.
                Signature: (method, url, status_code, duration, service, request_type) -> None
        """
        self.config = config
        self._http_log_callback = http_log_callback
        self._configure_litellm()

    def set_http_log_callback(self, callback: HttpLogCallback | None) -> None:
        """Set the HTTP logging callback.

        Args:
            callback: Callback function for logging HTTP requests
        """
        self._http_log_callback = callback

    def _configure_litellm(self) -> None:
        """Configure litellm with API settings."""
        # Set API base if provided (for non-OpenAI providers)
        if self.config.base_url and self.config.base_url != "https://api.openai.com/v1":
            litellm.api_base = self.config.base_url

        # Disable litellm's verbose logging
        litellm.set_verbose = False

    async def _call_llm(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        request_type: str = "completion",
    ) -> LLMResponse:
        """Make an async LLM call.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Override default temperature
            max_tokens: Override default max tokens
            request_type: Type of request for logging (e.g., 'task_extraction', 'recommendations')

        Returns:
            LLMResponse with content and metadata

        Raises:
            LLMError: If the API call fails
        """
        start_time = time.time()
        status_code = None

        # Determine the API URL being called
        api_url = self.config.base_url or "https://api.openai.com/v1"
        if not api_url.endswith("/chat/completions"):
            api_url = f"{api_url.rstrip('/')}/chat/completions"

        try:
            response = await acompletion(
                model=self.config.model,
                messages=messages,
                api_key=self.config.api_key,
                temperature=temperature or self.config.temperature,
                max_tokens=max_tokens or self.config.max_tokens,
            )

            content = response.choices[0].message.content or ""
            tokens_used = response.usage.total_tokens if response.usage else 0
            status_code = 200  # Successful completion

            duration = time.time() - start_time

            # Log HTTP request if callback is set
            if self._http_log_callback:
                self._http_log_callback(
                    "POST",
                    api_url,
                    status_code,
                    duration,
                    "llm",
                    request_type,
                )

            return LLMResponse(
                content=content,
                tokens_used=tokens_used,
                model=self.config.model,
                raw_response=response.model_dump() if hasattr(response, "model_dump") else None,
            )

        except Exception as e:
            duration = time.time() - start_time
            # Try to extract status code from exception if available
            if hasattr(e, "status_code"):
                status_code = e.status_code
            else:
                status_code = 500  # Default to 500 for unknown errors

            # Log failed HTTP request if callback is set
            if self._http_log_callback:
                self._http_log_callback(
                    "POST",
                    api_url,
                    status_code,
                    duration,
                    "llm",
                    request_type,
                )

            logger.error(f"LLM call failed: {e}")
            raise LLMError(f"LLM call failed: {e}") from e

    async def extract_tasks_from_text(
        self,
        text: str,
        source: str = "unknown",
        context: str | None = None,
    ) -> list[ExtractedTask]:
        """Extract actionable tasks from text using LLM.

        Args:
            text: The text to extract tasks from
            source: Source of the text (email, slack, meeting_notes, etc.)
            context: Additional context about the text

        Returns:
            List of extracted tasks
        """
        today = datetime.now()
        today_str = today.strftime("%Y-%m-%d")
        weekday = today.strftime("%A")

        system_prompt = f"""You are a task extraction assistant. Analyze the given text and extract any actionable tasks or requests.

Today's date is {today_str} ({weekday}). Use this to interpret relative dates correctly.

For each task, determine:
- title: A clear, concise task title (max 100 chars)
- description: Additional context if needed
- priority: "critical", "high", "medium", or "low" based on urgency indicators
- due_date: If a deadline is mentioned, extract it in ISO format (YYYY-MM-DDTHH:MM:SS). For relative dates like "this Sunday", "tomorrow", "next week", calculate the actual future date based on today's date.
- tags: Relevant tags for categorization
- confidence: Your confidence in this being a real task (0.0 to 1.0)

Return a JSON array of tasks. If no actionable tasks are found, return an empty array [].

Priority guidelines:
- critical: Contains "ASAP", "urgent", "immediately", "emergency", or blocking issues
- high: Has a deadline within 1-2 days, or explicitly marked important
- medium: Normal requests without urgency indicators
- low: "when you get a chance", "no rush", or informational items

IMPORTANT: All due dates must be in the future. If someone says "this Sunday" and today is {weekday}, calculate the next upcoming Sunday.

Example output:
[{{"title": "Review PR #123", "description": "Code review requested by John", "priority": "high", "due_date": "2026-01-29T17:00:00", "tags": ["code-review", "engineering"], "confidence": 0.9}}]"""

        user_prompt = f"""Source: {source}
{f"Context: {context}" if context else ""}

Text to analyze:
{text}

Extract all actionable tasks as JSON:"""

        try:
            response = await self._call_llm(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,  # Lower temperature for more consistent extraction
                request_type="task_extraction",
            )

            # Parse JSON response
            tasks_data = self._parse_json_response(response.content)
            if not isinstance(tasks_data, list):
                tasks_data = [tasks_data] if tasks_data else []

            tasks = []
            for task_data in tasks_data:
                try:
                    due_date = None
                    if task_data.get("due_date"):
                        try:
                            due_date = datetime.fromisoformat(task_data["due_date"].replace("Z", ""))
                        except (ValueError, TypeError):
                            pass

                    tasks.append(
                        ExtractedTask(
                            title=task_data.get("title", "Untitled Task")[:500],
                            description=task_data.get("description"),
                            priority=task_data.get("priority", "medium"),
                            due_date=due_date,
                            tags=task_data.get("tags", []),
                            confidence=float(task_data.get("confidence", 0.5)),
                        )
                    )
                except (KeyError, TypeError) as e:
                    logger.warning(f"Failed to parse task data: {e}")
                    continue

            logger.info(f"Extracted {len(tasks)} tasks from {source}")
            return tasks

        except LLMError:
            raise
        except Exception as e:
            logger.error(f"Task extraction failed: {e}")
            return []

    async def suggest_priority_updates(
        self,
        tasks: list[dict[str, Any]],
    ) -> list[PrioritySuggestion]:
        """Suggest priority updates for existing tasks.

        Args:
            tasks: List of task dicts with id, title, description, priority, due_date, etc.

        Returns:
            List of priority suggestions
        """
        if not tasks:
            return []

        system_prompt = """You are a task prioritization assistant. Analyze the given tasks and suggest priority adjustments.

Consider:
- Due dates and urgency
- Task dependencies (blocking items should be higher priority)
- Current workload balance
- Task titles/descriptions for importance indicators

Return a JSON array of suggestions. Only include tasks that should change priority.

Output format:
[{"task_id": 1, "current_priority": "medium", "suggested_priority": "high", "reason": "Due in 2 days", "confidence": 0.8}]

If no changes are needed, return an empty array []."""

        tasks_summary = "\n".join(
            f"- ID {t['id']}: [{t['priority']}] {t['title']}"
            + (f" (due: {t['due_date']})" if t.get("due_date") else "")
            for t in tasks[:20]  # Limit to 20 tasks to manage context
        )

        user_prompt = f"""Current tasks:
{tasks_summary}

Today's date: {datetime.now().strftime("%Y-%m-%d")}

Suggest priority changes as JSON:"""

        try:
            response = await self._call_llm(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                request_type="priority_suggestion",
            )

            suggestions_data = self._parse_json_response(response.content)
            if not isinstance(suggestions_data, list):
                suggestions_data = [suggestions_data] if suggestions_data else []

            suggestions = []
            for s in suggestions_data:
                try:
                    suggestions.append(
                        PrioritySuggestion(
                            task_id=int(s["task_id"]),
                            current_priority=s.get("current_priority", "medium"),
                            suggested_priority=s.get("suggested_priority", "medium"),
                            reason=s.get("reason", ""),
                            confidence=float(s.get("confidence", 0.5)),
                        )
                    )
                except (KeyError, TypeError, ValueError) as e:
                    logger.warning(f"Failed to parse priority suggestion: {e}")
                    continue

            return suggestions

        except LLMError:
            raise
        except Exception as e:
            logger.error(f"Priority suggestion failed: {e}")
            return []

    async def generate_recommendations(
        self,
        tasks: list[dict[str, Any]],
        statistics: dict[str, Any] | None = None,
    ) -> list[ProductivityRecommendation]:
        """Generate productivity recommendations based on task state.

        Args:
            tasks: List of task dicts
            statistics: Optional task statistics dict

        Returns:
            List of productivity recommendations
        """
        system_prompt = """You are a productivity assistant. Analyze the user's task list and statistics to provide actionable recommendations.

Categories:
- focus: Help user focus on what matters most
- scheduling: Suggestions for better time management
- delegation: Tasks that could be delegated or deprioritized
- organization: Ways to better organize and categorize work

Return a JSON array of 2-5 recommendations.

Output format:
[{
  "title": "Focus on overdue tasks",
  "description": "You have 3 overdue tasks. Consider blocking time to complete them.",
  "category": "focus",
  "priority": "high",
  "actionable_steps": ["Block 2 hours tomorrow morning", "Start with the oldest task"]
}]"""

        # Build context
        task_summary = f"Total tasks: {len(tasks)}\n"

        if statistics:
            task_summary += f"""Active tasks: {statistics.get('active', 0)}
Overdue: {statistics.get('overdue', 0)}
Due today: {statistics.get('due_today', 0)}
Due this week: {statistics.get('due_this_week', 0)}
By priority: {statistics.get('by_priority', {})}
By source: {statistics.get('by_source', {})}
"""

        # Add top priority tasks
        top_tasks = sorted(
            [t for t in tasks if t.get("status") not in ["completed", "cancelled"]],
            key=lambda x: x.get("priority_score", 0),
            reverse=True,
        )[:10]

        if top_tasks:
            task_summary += "\nTop priority tasks:\n"
            for t in top_tasks:
                task_summary += f"- [{t.get('priority', 'medium')}] {t.get('title', 'Untitled')}"
                if t.get("due_date"):
                    task_summary += f" (due: {t['due_date']})"
                task_summary += "\n"

        user_prompt = f"""Task Analysis:
{task_summary}

Today's date: {datetime.now().strftime("%Y-%m-%d %H:%M")}

Generate productivity recommendations as JSON:"""

        try:
            response = await self._call_llm(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.5,
                request_type="recommendations",
            )

            recommendations_data = self._parse_json_response(response.content)
            if not isinstance(recommendations_data, list):
                recommendations_data = [recommendations_data] if recommendations_data else []

            recommendations = []
            for r in recommendations_data:
                try:
                    recommendations.append(
                        ProductivityRecommendation(
                            title=r.get("title", "Recommendation"),
                            description=r.get("description", ""),
                            category=r.get("category", "organization"),
                            priority=r.get("priority", "medium"),
                            actionable_steps=r.get("actionable_steps"),
                        )
                    )
                except (KeyError, TypeError) as e:
                    logger.warning(f"Failed to parse recommendation: {e}")
                    continue

            return recommendations

        except LLMError:
            raise
        except Exception as e:
            logger.error(f"Recommendation generation failed: {e}")
            return []

    async def analyze_calendar_for_optimization(
        self,
        events: list[dict[str, Any]],
        tasks: list[dict[str, Any]],
    ) -> list[ProductivityRecommendation]:
        """Analyze calendar and suggest optimizations.

        Args:
            events: List of calendar event dicts
            tasks: List of task dicts

        Returns:
            List of calendar optimization recommendations
        """
        system_prompt = """You are a calendar optimization assistant. Analyze the user's calendar events and tasks to suggest improvements.

Consider:
- Meeting-free time blocks for deep work
- Back-to-back meetings that could use buffer time
- Tasks that need dedicated calendar time
- Potential meeting conflicts or overload

Return a JSON array of 1-3 calendar-specific recommendations.

Output format:
[{
  "title": "Schedule focus time",
  "description": "You have 5 high-priority tasks but no dedicated focus time this week.",
  "category": "scheduling",
  "priority": "high",
  "actionable_steps": ["Block Tuesday morning 9-11am", "Block Thursday afternoon 2-4pm"]
}]"""

        # Build context
        context = f"Today: {datetime.now().strftime('%Y-%m-%d %A')}\n\n"

        if events:
            context += "Upcoming events:\n"
            for e in events[:15]:
                context += f"- {e.get('start', 'TBD')}: {e.get('title', 'Event')} ({e.get('duration_minutes', '?')} min)\n"
        else:
            context += "No calendar events provided.\n"

        context += f"\nHigh priority tasks: {len([t for t in tasks if t.get('priority') in ['critical', 'high']])}"

        user_prompt = f"""{context}

Suggest calendar optimizations as JSON:"""

        try:
            response = await self._call_llm(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.5,
                request_type="calendar_optimization",
            )

            recommendations_data = self._parse_json_response(response.content)
            if not isinstance(recommendations_data, list):
                recommendations_data = [recommendations_data] if recommendations_data else []

            recommendations = []
            for r in recommendations_data:
                try:
                    recommendations.append(
                        ProductivityRecommendation(
                            title=r.get("title", "Calendar Suggestion"),
                            description=r.get("description", ""),
                            category="scheduling",
                            priority=r.get("priority", "medium"),
                            actionable_steps=r.get("actionable_steps"),
                        )
                    )
                except (KeyError, TypeError):
                    continue

            return recommendations

        except LLMError:
            raise
        except Exception as e:
            logger.error(f"Calendar optimization failed: {e}")
            return []

    async def parse_date(self, date_string: str) -> datetime | None:
        """Parse a natural language date string into a datetime.

        Args:
            date_string: Natural language date like "next Friday", "end of month", etc.

        Returns:
            Parsed datetime or None if parsing fails.
        """
        today = datetime.now()
        today_str = today.strftime("%Y-%m-%d")
        weekday = today.strftime("%A")

        system_prompt = f"""You are a date parsing assistant. Convert natural language date expressions to ISO format datetime.

Today's date is {today_str} ({weekday}). The current time is {today.strftime("%H:%M")}.

Rules:
- Return ONLY the datetime in ISO format: YYYY-MM-DDTHH:MM:SS
- If no time is specified, use 23:59:00 (end of day)
- For relative dates like "next Friday", calculate the actual date
- For "end of month", use the last day of the current month
- For "end of week", use Sunday
- If the date is ambiguous or cannot be parsed, return "INVALID"

Examples:
- "tomorrow" -> {(today + timedelta(days=1)).strftime("%Y-%m-%d")}T23:59:00
- "next Friday" -> [calculate the next Friday from today]
- "in 3 days" -> {(today + timedelta(days=3)).strftime("%Y-%m-%d")}T23:59:00
- "February 15th" -> 2026-02-15T23:59:00
- "this Sunday at 5pm" -> [next Sunday]T17:00:00

Respond with ONLY the ISO datetime string, nothing else."""

        user_prompt = f"Parse this date: {date_string}"

        try:
            response = await self._call_llm(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,  # Very low temperature for consistent parsing
                max_tokens=50,  # Short response expected
                request_type="date_parsing",
            )

            date_str = response.content.strip()

            # Check for invalid response
            if date_str.upper() == "INVALID":
                logger.warning(f"LLM could not parse date: {date_string}")
                return None

            # Parse the ISO format datetime
            try:
                # Handle various ISO formats
                date_str = date_str.replace("Z", "")
                parsed = datetime.fromisoformat(date_str)
                logger.info(f"Parsed '{date_string}' -> {parsed}")
                return parsed
            except ValueError as e:
                logger.warning(f"Failed to parse LLM date response '{date_str}': {e}")
                return None

        except LLMError:
            raise
        except Exception as e:
            logger.error(f"Date parsing failed: {e}")
            return None

    def _parse_json_response(self, content: str) -> Any:
        """Parse JSON from LLM response, handling markdown code blocks.

        Args:
            content: Raw LLM response content

        Returns:
            Parsed JSON data
        """
        # Strip markdown code blocks if present
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first line (```json or ```)
            lines = lines[1:]
            # Remove last line (```)
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw content: {content}")
            return []


class LLMError(Exception):
    """Exception raised for LLM service errors."""

    pass
