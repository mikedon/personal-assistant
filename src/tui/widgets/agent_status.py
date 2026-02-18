"""Agent status bar widget showing agent polling status and controls."""

from datetime import datetime
from typing import Optional

from textual.reactive import reactive
from textual.widgets import Static

from src.utils.pid_manager import get_pid_manager


class AgentStatusBar(Static):
    """Widget displaying agent status and polling controls."""

    DEFAULT_CSS = """
    AgentStatusBar {
        width: 1fr;
        height: 3;
        border: solid $accent;
        padding: 0 1;
    }
    """

    agent_running = reactive(False)
    last_poll_time = reactive(None)
    poll_count = reactive(0)

    def __init__(self, name: Optional[str] = None, id: Optional[str] = None):
        """Initialize the agent status bar."""
        super().__init__(name=name, id=id)
        self.autonomy_level = "suggest"
        self.auto_polling = True

    def on_mount(self) -> None:
        """Set up the status bar when mounted."""
        self.refresh_agent_status()

    def refresh_agent_status(self) -> None:
        """Refresh agent status from PID file."""
        try:
            pid_manager = get_pid_manager()
            pid = pid_manager.get_agent_pid()
            self.agent_running = pid is not None

            # For now, just update the display
            self.update(self._render_status())

        except Exception as e:
            self.log(f"Error refreshing agent status: {e}")

    def _render_status(self) -> str:
        """Render the agent status with real-time relative timestamps."""
        status_indicator = "[green]●[/green]" if self.agent_running else "[red]●[/red]"
        status_text = "Running" if self.agent_running else "Stopped"

        # First line: status and polling state
        lines = [
            f"[bold]Agent[/bold] {status_indicator} {status_text}  "
            f"Autonomy: [cyan]{self.autonomy_level}[/cyan]  "
            f"Auto: {'[green]ON[/green]' if self.auto_polling else '[red]OFF[/red]'}"
        ]

        # Second line: poll timing and stats
        if self.last_poll_time:
            elapsed = datetime.now() - self.last_poll_time
            if elapsed.total_seconds() < 60:
                time_str = "just now"
            elif elapsed.total_seconds() < 3600:
                mins = int(elapsed.total_seconds() / 60)
                time_str = f"{mins}m ago"
            else:
                hours = int(elapsed.total_seconds() / 3600)
                time_str = f"{hours}h ago"

            lines.append(f"Last poll: {time_str}  |  {self.poll_count} polls this session")
        else:
            lines.append("Last poll: never  |  0 polls this session")

        # Third line: shortcuts
        lines.append("[dim]p:poll • a:auto • ?:help[/dim]")

        return "\n".join(lines)

    def set_last_poll_time(self, time: Optional[datetime]) -> None:
        """Set the last poll time."""
        self.last_poll_time = time
        self.poll_count += 1
        self.update(self._render_status())

    def toggle_auto_polling(self) -> None:
        """Toggle auto-polling mode."""
        self.auto_polling = not self.auto_polling
        self.update(self._render_status())

    def set_autonomy_level(self, level: str) -> None:
        """Set the autonomy level."""
        self.autonomy_level = level
        self.update(self._render_status())
