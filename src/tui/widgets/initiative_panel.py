"""Initiative panel widget displaying active initiatives with progress."""

from typing import Optional

from textual.reactive import reactive
from textual.widgets import Static
from rich.console import Console
from rich.text import Text

from src.models.database import get_db_session
from src.models.initiative import InitiativePriority
from src.services.initiative_service import InitiativeService


class InitiativePanel(Static):
    """Widget displaying active initiatives with progress bars."""

    DEFAULT_CSS = """
    InitiativePanel {
        width: 25;
        height: 1fr;
        border: solid $accent;
        padding: 1;
    }
    """

    initiative_count = reactive(0)

    def __init__(self, name: Optional[str] = None, id: Optional[str] = None):
        """Initialize the initiative panel."""
        super().__init__(name=name, id=id)
        self.initiatives = []
        self.console = Console()

    def on_mount(self) -> None:
        """Set up the panel when mounted."""
        self.refresh_initiatives()

    def refresh_initiatives(self) -> None:
        """Refresh the initiative list from the database."""
        try:
            with get_db_session() as db:
                service = InitiativeService(db)
                initiatives_data = service.get_initiatives_with_progress(
                    include_completed=False
                )

                # Eagerly load all data into dicts before session closes
                self.initiatives = []
                for item in initiatives_data:
                    initiative = item['initiative']
                    progress = item['progress']
                    self.initiatives.append({
                        'title': initiative.title,
                        'priority': initiative.priority,
                        'progress': progress,
                    })

            self.initiative_count = len(self.initiatives)
            self.update(self._render_initiatives())

        except Exception as e:
            self.update(f"Error loading initiatives: {e}")

    def _render_initiatives(self) -> str:
        """Render initiatives as rich text."""
        lines = ["[bold]Active Initiatives[/bold]"]

        if not self.initiatives:
            lines.append("[dim]No active initiatives[/dim]")
            return "\n".join(lines)

        for item in self.initiatives:
            # Priority emoji
            pri_emoji = {
                "high": "🔴",
                "medium": "🟡",
                "low": "🟢",
            }.get(item['priority'].value, "⚪")

            # Title
            title = item['title'][:20]

            # Progress bar
            progress = item['progress']
            pct = progress["progress_percent"]
            completed = progress["completed_tasks"]
            total = progress["total_tasks"]

            # Simple progress bar
            bar_length = 15
            filled = int(bar_length * pct / 100)
            bar = "█" * filled + "░" * (bar_length - filled)

            lines.append(f"\n{pri_emoji} {title}")
            lines.append(f"[cyan]{bar}[/cyan] {pct:.0f}%")
            lines.append(f"[dim]{completed}/{total}[/dim]")

        return "\n".join(lines)

    def get_initiative_count(self) -> int:
        """Get the number of active initiatives."""
        return len(self.initiatives)
