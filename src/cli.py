"""Command-line interface for the Personal Assistant.

Provides commands for:
- Starting/stopping the agent
- Viewing and managing tasks
- Viewing status and recommendations
- Configuration management
"""

import asyncio
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from src import __version__
from src.models import init_db
from src.models.database import get_db_session
from src.models.task import TaskPriority, TaskSource, TaskStatus
from src.services.task_service import TaskService
from src.utils.config import get_config, load_config

console = Console()


# --- Utility Functions ---


def get_priority_style(priority: TaskPriority) -> str:
    """Get rich style for priority level."""
    styles = {
        TaskPriority.CRITICAL: "bold red",
        TaskPriority.HIGH: "red",
        TaskPriority.MEDIUM: "yellow",
        TaskPriority.LOW: "green",
    }
    return styles.get(priority, "white")


def get_status_style(status: TaskStatus) -> str:
    """Get rich style for task status."""
    styles = {
        TaskStatus.PENDING: "white",
        TaskStatus.IN_PROGRESS: "cyan",
        TaskStatus.COMPLETED: "green",
        TaskStatus.DEFERRED: "dim",
        TaskStatus.CANCELLED: "dim strikethrough",
    }
    return styles.get(status, "white")


def format_due_date(due_date: datetime | None) -> str:
    """Format due date with relative time."""
    if not due_date:
        return "-"

    now = datetime.now()
    # Handle timezone-naive comparison
    if due_date.tzinfo:
        due_date = due_date.replace(tzinfo=None)

    diff = due_date - now

    if diff.total_seconds() < 0:
        days_overdue = abs(diff.days)
        if days_overdue == 0:
            return "[red]Overdue (today)[/red]"
        return f"[red]Overdue ({days_overdue}d)[/red]"
    elif diff.days == 0:
        hours = int(diff.total_seconds() / 3600)
        return f"[yellow]Today ({hours}h)[/yellow]"
    elif diff.days == 1:
        return "[yellow]Tomorrow[/yellow]"
    elif diff.days <= 7:
        return f"[cyan]{diff.days} days[/cyan]"
    else:
        return due_date.strftime("%Y-%m-%d")


def run_async(coro):
    """Run an async coroutine."""
    return asyncio.get_event_loop().run_until_complete(coro)


# --- Main CLI Group ---


@click.group()
@click.version_option(version=__version__, prog_name="Personal Assistant")
@click.option("--config", "-c", type=click.Path(exists=True), help="Path to config file")
@click.pass_context
def cli(ctx, config):
    """Personal Assistant - AI-powered task management and productivity.

    Use 'pa <command> --help' for more information about a command.
    """
    ctx.ensure_object(dict)

    # Load configuration
    config_path = config if config else None
    ctx.obj["config"] = load_config(config_path)

    # Initialize database
    init_db()


# --- Agent Commands ---


@cli.group()
def agent():
    """Agent control commands."""
    pass


@agent.command("start")
@click.option("--autonomy", "-a", type=click.Choice(["suggest", "auto_low", "auto", "full"]),
              help="Autonomy level")
@click.option("--foreground", "-f", is_flag=True, help="Run in foreground (don't daemonize)")
@click.pass_context
def agent_start(ctx, autonomy, foreground):
    """Start the autonomous agent."""
    from src.agent.core import get_agent

    config = ctx.obj["config"]
    agent = get_agent(config)

    if agent.state.is_running:
        console.print("[yellow]Agent is already running.[/yellow]")
        return

    if autonomy:
        agent.autonomy_level = autonomy

    console.print(Panel(
        f"[green]Starting Personal Assistant Agent[/green]\n"
        f"Autonomy Level: [cyan]{agent.autonomy_level.value}[/cyan]\n"
        f"Poll Interval: [cyan]{config.agent.poll_interval_minutes} minutes[/cyan]",
        title="Agent Starting",
    ))

    if foreground:
        # Run in foreground with graceful shutdown
        def signal_handler(sig, frame):
            console.print("\n[yellow]Shutting down...[/yellow]")
            run_async(agent.stop())
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            run_async(agent.start())
            console.print("[green]Agent started. Press Ctrl+C to stop.[/green]")

            # Keep running
            while agent.state.is_running:
                asyncio.get_event_loop().run_until_complete(asyncio.sleep(1))

        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down...[/yellow]")
            run_async(agent.stop())
    else:
        # Just start (for API mode)
        run_async(agent.start())
        console.print("[green]Agent started.[/green]")


@agent.command("stop")
def agent_stop():
    """Stop the autonomous agent."""
    from src.agent.core import get_agent

    agent = get_agent()

    if not agent.state.is_running:
        console.print("[yellow]Agent is not running.[/yellow]")
        return

    run_async(agent.stop())
    console.print("[green]Agent stopped.[/green]")


@agent.command("status")
def agent_status():
    """Show agent status."""
    from src.agent.core import get_agent

    agent = get_agent()
    status = agent.get_status()

    # Build status panel
    status_color = "green" if status["is_running"] else "red"
    status_text = "Running" if status["is_running"] else "Stopped"

    info_lines = [
        f"Status: [{status_color}]{status_text}[/{status_color}]",
        f"Autonomy Level: [cyan]{status['autonomy_level']}[/cyan]",
    ]

    if status["started_at"]:
        info_lines.append(f"Started: {status['started_at']}")
    if status["last_poll"]:
        info_lines.append(f"Last Poll: {status['last_poll']}")

    info_lines.extend([
        "",
        f"Tasks Created (session): {status['session_stats']['tasks_created']}",
        f"Items Processed: {status['session_stats']['items_processed']}",
        f"Errors: {status['session_stats']['errors']}",
        f"Pending Suggestions: {status['pending_suggestions']}",
    ])

    console.print(Panel("\n".join(info_lines), title="Agent Status"))

    # Integration status
    table = Table(title="Integrations")
    table.add_column("Integration", style="cyan")
    table.add_column("Enabled", style="white")

    for name, enabled in status["integrations"].items():
        enabled_str = "[green]Yes[/green]" if enabled else "[dim]No[/dim]"
        table.add_row(name.title(), enabled_str)

    console.print(table)


@agent.command("poll")
def agent_poll():
    """Trigger an immediate poll cycle."""
    from src.agent.core import get_agent

    agent = get_agent()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Polling integrations...", total=None)
        results = run_async(agent.poll_now())
        progress.update(task, completed=True)

    if not results:
        console.print("[yellow]No integrations configured or enabled.[/yellow]")
        return

    for result in results:
        items = len(result.items_found)
        created = len(result.tasks_created)
        suggested = len(result.tasks_suggested)

        if result.error:
            console.print(f"[red]✗[/red] {result.integration.value}: Error - {result.error}")
        elif items > 0:
            console.print(
                f"[green]✓[/green] {result.integration.value}: "
                f"{items} items, {created} tasks created, {suggested} suggestions"
            )
        else:
            console.print(f"[dim]✓[/dim] {result.integration.value}: No new items")


# --- Task Commands ---


@cli.group()
def tasks():
    """Task management commands."""
    pass


@tasks.command("list")
@click.option("--status", "-s", type=click.Choice([s.value for s in TaskStatus]),
              help="Filter by status")
@click.option("--priority", "-p", type=click.Choice([p.value for p in TaskPriority]),
              help="Filter by priority")
@click.option("--all", "-a", "show_all", is_flag=True, help="Include completed tasks")
@click.option("--limit", "-n", default=20, help="Number of tasks to show")
def tasks_list(status, priority, show_all, limit):
    """List tasks."""
    with get_db_session() as db:
        service = TaskService(db)

        # Build filters
        status_filter = TaskStatus(status) if status else None
        priority_filter = TaskPriority(priority) if priority else None

        tasks, total = service.get_tasks(
            status=status_filter,
            priority=priority_filter,
            include_completed=show_all,
            limit=limit,
        )

        if not tasks:
            console.print("[dim]No tasks found.[/dim]")
            return

        table = Table(title=f"Tasks ({len(tasks)} of {total})")
        table.add_column("ID", style="dim", width=4)
        table.add_column("Pri", width=4)
        table.add_column("Title", style="white", max_width=50)
        table.add_column("Status", width=12)
        table.add_column("Due", width=15)
        table.add_column("Source", style="dim", width=8)

        for task in tasks:
            pri_style = get_priority_style(task.priority)
            status_style = get_status_style(task.status)
            pri_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                task.priority.value, "⚪"
            )

            table.add_row(
                str(task.id),
                pri_emoji,
                Text(task.title[:50], style=pri_style),
                Text(task.status.value, style=status_style),
                format_due_date(task.due_date),
                task.source.value[:8],
            )

        console.print(table)


@tasks.command("add")
@click.argument("title")
@click.option("--description", "-d", help="Task description")
@click.option("--priority", "-p", type=click.Choice([p.value for p in TaskPriority]),
              default="medium", help="Priority level")
@click.option("--due", "-D", help="Due date (YYYY-MM-DD or 'tomorrow', '+3d')")
@click.option("--tags", "-t", multiple=True, help="Tags (can specify multiple)")
def tasks_add(title, description, priority, due, tags):
    """Add a new task."""
    # Parse due date
    due_date = None
    if due:
        due_date = parse_due_date(due)
        if not due_date:
            console.print(f"[red]Invalid due date format: {due}[/red]")
            return

    with get_db_session() as db:
        service = TaskService(db)
        task = service.create_task(
            title=title,
            description=description,
            priority=TaskPriority(priority),
            source=TaskSource.MANUAL,
            due_date=due_date,
            tags=list(tags) if tags else None,
        )

        console.print(f"[green]✓[/green] Created task #{task.id}: {task.title}")


@tasks.command("complete")
@click.argument("task_id", type=int)
def tasks_complete(task_id):
    """Mark a task as completed."""
    with get_db_session() as db:
        service = TaskService(db)
        task = service.get_task(task_id)

        if not task:
            console.print(f"[red]Task #{task_id} not found.[/red]")
            return

        service.update_task(task, status=TaskStatus.COMPLETED)
        console.print(f"[green]✓[/green] Completed task #{task_id}: {task.title}")


@tasks.command("delete")
@click.argument("task_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def tasks_delete(task_id, yes):
    """Delete a task."""
    with get_db_session() as db:
        service = TaskService(db)
        task = service.get_task(task_id)

        if not task:
            console.print(f"[red]Task #{task_id} not found.[/red]")
            return

        if not yes:
            if not click.confirm(f"Delete task '{task.title}'?"):
                return

        service.delete_task(task)
        console.print(f"[green]✓[/green] Deleted task #{task_id}")


@tasks.command("show")
@click.argument("task_id", type=int)
def tasks_show(task_id):
    """Show task details."""
    with get_db_session() as db:
        service = TaskService(db)
        task = service.get_task(task_id)

        if not task:
            console.print(f"[red]Task #{task_id} not found.[/red]")
            return

        pri_style = get_priority_style(task.priority)
        info_lines = [
            f"[bold]{task.title}[/bold]",
            "",
            f"Status: {task.status.value}",
            f"Priority: [{pri_style}]{task.priority.value}[/{pri_style}]",
            f"Score: {task.priority_score:.1f}",
            f"Source: {task.source.value}",
        ]

        if task.description:
            info_lines.extend(["", f"Description: {task.description}"])

        if task.due_date:
            info_lines.append(f"Due: {format_due_date(task.due_date)}")

        tags = task.get_tags_list()
        if tags:
            info_lines.append(f"Tags: {', '.join(tags)}")

        info_lines.extend([
            "",
            f"Created: {task.created_at.strftime('%Y-%m-%d %H:%M')}",
            f"Updated: {task.updated_at.strftime('%Y-%m-%d %H:%M')}",
        ])

        if task.completed_at:
            info_lines.append(f"Completed: {task.completed_at.strftime('%Y-%m-%d %H:%M')}")

        console.print(Panel("\n".join(info_lines), title=f"Task #{task.id}"))


@tasks.command("priority")
@click.option("--limit", "-n", default=10, help="Number of tasks to show")
def tasks_priority(limit):
    """Show top priority tasks."""
    with get_db_session() as db:
        service = TaskService(db)
        tasks = service.get_prioritized_tasks(limit=limit)

        if not tasks:
            console.print("[dim]No active tasks found.[/dim]")
            return

        console.print(Panel("[bold]Top Priority Tasks[/bold]"))

        for i, task in enumerate(tasks, 1):
            pri_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                task.priority.value, "⚪"
            )
            due_str = f" - {format_due_date(task.due_date)}" if task.due_date else ""

            console.print(f"  {i}. {pri_emoji} [{task.priority_score:.0f}] {task.title}{due_str}")


@tasks.command("stats")
def tasks_stats():
    """Show task statistics."""
    with get_db_session() as db:
        service = TaskService(db)
        stats = service.get_statistics()

        info_lines = [
            f"Total Tasks: [cyan]{stats['total']}[/cyan]",
            f"Active: [green]{stats['active']}[/green]",
            f"Overdue: [red]{stats['overdue']}[/red]",
            f"Due Today: [yellow]{stats['due_today']}[/yellow]",
            f"Due This Week: [cyan]{stats['due_this_week']}[/cyan]",
        ]

        if stats.get("avg_completion_hours"):
            info_lines.append(f"Avg Completion: {stats['avg_completion_hours']:.1f} hours")

        console.print(Panel("\n".join(info_lines), title="Task Statistics"))

        # Status breakdown
        table = Table(title="By Status")
        table.add_column("Status", style="cyan")
        table.add_column("Count", justify="right")

        for status, count in stats["by_status"].items():
            table.add_row(status, str(count))

        console.print(table)


# --- Summary Command ---


@cli.command()
def summary():
    """Show daily summary and recommendations."""
    from src.services.recommendation_service import RecommendationService

    config = get_config()

    with get_db_session() as db:
        service = TaskService(db)
        stats = service.get_statistics()
        top_tasks = service.get_prioritized_tasks(limit=5)
        overdue = service.get_overdue_tasks()

        # Header
        console.print(Panel(
            f"[bold]Personal Assistant Summary[/bold]\n"
            f"[dim]{datetime.now().strftime('%A, %B %d, %Y')}[/dim]",
        ))

        # Quick stats
        console.print()
        console.print(f"  📋 Active Tasks: [cyan]{stats['active']}[/cyan]")
        console.print(f"  ⚠️  Overdue: [red]{stats['overdue']}[/red]")
        console.print(f"  📅 Due Today: [yellow]{stats['due_today']}[/yellow]")
        console.print(f"  📆 Due This Week: [cyan]{stats['due_this_week']}[/cyan]")

        # Top priorities
        if top_tasks:
            console.print("\n[bold]Top Priorities:[/bold]")
            for i, task in enumerate(top_tasks, 1):
                pri_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                    task.priority.value, "⚪"
                )
                console.print(f"  {i}. {pri_emoji} {task.title[:60]}")

        # Overdue warning
        if overdue:
            console.print(f"\n[red bold]⚠️ {len(overdue)} Overdue Task(s):[/red bold]")
            for task in overdue[:3]:
                console.print(f"  [red]• {task.title[:60]}[/red]")

        console.print()


# --- Config Commands ---


@cli.group()
def config():
    """Configuration commands."""
    pass


@config.command("show")
@click.pass_context
def config_show(ctx):
    """Show current configuration."""
    cfg = ctx.obj["config"]

    sections = [
        ("Agent", [
            f"Poll Interval: {cfg.agent.poll_interval_minutes} minutes",
            f"Autonomy Level: {cfg.agent.autonomy_level}",
            f"Output Path: {cfg.agent.output_document_path}",
        ]),
        ("Notifications", [
            f"Enabled: {cfg.notifications.enabled}",
            f"Sound: {cfg.notifications.sound}",
            f"On Overdue: {cfg.notifications.on_overdue}",
            f"On Due Soon: {cfg.notifications.on_due_soon} ({cfg.notifications.due_soon_hours}h)",
        ]),
        ("LLM", [
            f"Model: {cfg.llm.model}",
            f"API Key: {'*' * 8 if cfg.llm.api_key else '[not set]'}",
        ]),
    ]

    for title, items in sections:
        console.print(f"\n[bold]{title}[/bold]")
        for item in items:
            console.print(f"  {item}")


@config.command("path")
def config_path():
    """Show config file path."""
    default_path = Path("config.yaml")
    if default_path.exists():
        console.print(f"Config file: [cyan]{default_path.absolute()}[/cyan]")
    else:
        console.print("[dim]No config.yaml found. Using defaults.[/dim]")
        console.print("[dim]Create config.yaml to customize settings.[/dim]")


@config.command("init")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing config")
def config_init(force):
    """Create a default config file."""
    config_path = Path("config.yaml")

    if config_path.exists() and not force:
        console.print("[yellow]config.yaml already exists. Use --force to overwrite.[/yellow]")
        return

    default_config = """# Personal Assistant Configuration
# See documentation for all available options

# Agent settings
agent:
  poll_interval_minutes: 15
  autonomy_level: suggest  # suggest, auto_low, auto, full
  output_document_path: ~/personal_assistant_summary.md
  reminder_interval_hours: 2

# Notification settings
notifications:
  enabled: true
  sound: true
  on_overdue: true
  on_due_soon: true
  due_soon_hours: 4
  on_task_created: false

# LLM settings (required for AI features)
llm:
  model: gpt-4
  api_key: ""  # Set your API key here or use PA_LLM__API_KEY env var

# Database settings
database:
  url: sqlite:///personal_assistant.db

# Google integration (optional)
google:
  enabled: false
  credentials_path: credentials.json
  token_path: token.json

# Slack integration (optional)
slack:
  enabled: false
  bot_token: ""
  channels: []
"""

    config_path.write_text(default_config)
    console.print(f"[green]✓[/green] Created {config_path}")
    console.print("[dim]Edit the file to configure your settings.[/dim]")


# --- Server Command ---


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", "-p", default=8000, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload (dev mode)")
def server(host, port, reload):
    """Start the API server."""
    import uvicorn

    console.print(Panel(
        f"Starting API server at [cyan]http://{host}:{port}[/cyan]\n"
        f"API docs at [cyan]http://{host}:{port}/docs[/cyan]",
        title="Personal Assistant API",
    ))

    uvicorn.run(
        "src.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


# --- Notify Command ---


@cli.command()
@click.argument("message")
@click.option("--title", "-t", default="Personal Assistant", help="Notification title")
def notify(message, title):
    """Send a test notification."""
    from src.services.notification_service import NotificationService, Notification, NotificationType

    config = get_config()
    service = NotificationService(config.notifications)

    notification = Notification(
        title=title,
        message=message,
        type=NotificationType.INFO,
    )

    if service.send(notification):
        console.print("[green]✓[/green] Notification sent")
    else:
        console.print("[yellow]Notification not sent (may be disabled)[/yellow]")


# --- Helper Functions ---


def parse_due_date(due_str: str) -> datetime | None:
    """Parse due date from various formats.

    Supports:
    - YYYY-MM-DD
    - YYYY-MM-DD HH:MM
    - 'today', 'tomorrow'
    - '+Nd' (N days from now)
    - '+Nw' (N weeks from now)
    """
    due_str = due_str.lower().strip()
    now = datetime.now()

    if due_str == "today":
        return now.replace(hour=23, minute=59, second=0, microsecond=0)
    elif due_str == "tomorrow":
        return (now + timedelta(days=1)).replace(hour=23, minute=59, second=0, microsecond=0)
    elif due_str.startswith("+"):
        # Relative date
        try:
            num = int(due_str[1:-1])
            unit = due_str[-1]
            if unit == "d":
                return (now + timedelta(days=num)).replace(hour=23, minute=59, second=0, microsecond=0)
            elif unit == "w":
                return (now + timedelta(weeks=num)).replace(hour=23, minute=59, second=0, microsecond=0)
        except (ValueError, IndexError):
            return None
    else:
        # Try parsing as date
        for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d"]:
            try:
                parsed = datetime.strptime(due_str, fmt)
                if fmt == "%Y-%m-%d":
                    parsed = parsed.replace(hour=23, minute=59, second=0)
                return parsed
            except ValueError:
                continue

    return None


# --- Entry Point ---


def main():
    """Main entry point for the CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
