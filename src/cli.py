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
from src.models.initiative import InitiativePriority, InitiativeStatus
from src.models.task import TaskPriority, TaskSource, TaskStatus
from src.services.initiative_service import InitiativeService
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
    from src.utils.pid_manager import get_pid_manager

    config = ctx.obj["config"]
    pid_manager = get_pid_manager()

    # Check if agent is already running via PID file
    existing_pid = pid_manager.get_agent_pid()
    if existing_pid is not None:
        console.print(f"[yellow]Agent is already running (PID: {existing_pid}).[/yellow]")
        console.print("[dim]Use 'pa agent stop' to stop it first.[/dim]")
        return

    agent = get_agent(config)

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
        except RuntimeError as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)
    else:
        # Just start (for API mode)
        try:
            run_async(agent.start())
            console.print("[green]Agent started.[/green]")
        except RuntimeError as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)


@agent.command("stop")
def agent_stop():
    """Stop the autonomous agent."""
    from src.utils.pid_manager import get_pid_manager, PIDFileError

    pid_manager = get_pid_manager()
    
    # Check if agent is running
    pid = pid_manager.get_agent_pid()
    if pid is None:
        console.print("[yellow]Agent is not running.[/yellow]")
        return

    # Stop the agent process
    try:
        if pid_manager.stop_agent():
            console.print(f"[green]Agent stopped (PID: {pid}).[/green]")
        else:
            console.print("[yellow]Agent process not found.[/yellow]")
    except PIDFileError as e:
        console.print(f"[red]Error stopping agent: {e}[/red]")
        sys.exit(1)


@agent.command("status")
def agent_status():
    """Show agent status."""
    from src.agent.core import get_agent
    from src.utils.pid_manager import get_pid_manager

    pid_manager = get_pid_manager()
    agent_pid = pid_manager.get_agent_pid()
    
    # Check if agent is running via PID file
    is_running = agent_pid is not None
    
    if is_running:
        # Agent is running - try to get real status from database/logs
        agent = get_agent()
        status = agent.get_status()
        
        # Override is_running with PID-based check
        status["is_running"] = True
        status["pid"] = agent_pid
    else:
        # Agent is not running - show basic status
        agent = get_agent()
        status = agent.get_status()
        status["is_running"] = False
        status["pid"] = None

    # Build status panel
    status_color = "green" if status["is_running"] else "red"
    status_text = "Running" if status["is_running"] else "Stopped"

    info_lines = [
        f"Status: [{status_color}]{status_text}[/{status_color}]",
        f"Autonomy Level: [cyan]{status['autonomy_level']}[/cyan]",
    ]

    if status.get("pid"):
        info_lines.append(f"PID: {status['pid']}")

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

    # Prompt to review if there are suggestions
    suggestions = agent.get_pending_suggestions()
    if suggestions:
        console.print(f"\n[cyan]💡 {len(suggestions)} suggestion(s) pending review.[/cyan]")
        console.print("[dim]Run 'pa agent review' to review them.[/dim]")


@agent.command("review")
@click.option("--auto-approve", "-a", is_flag=True, help="Auto-approve all suggestions")
@click.option("--auto-reject", "-r", is_flag=True, help="Auto-reject all suggestions")
def agent_review(auto_approve, auto_reject):
    """Review and approve/reject pending task suggestions.

    Interactively review each suggestion with options to:
    - [a]pprove: Create the task
    - [r]eject: Discard the suggestion
    - [s]kip: Skip for now (keep in pending)
    - [q]uit: Stop reviewing
    """
    from src.agent.core import get_agent, PendingSuggestion

    agent = get_agent()
    suggestions = agent.get_pending_suggestions()

    if not suggestions:
        console.print("[dim]No pending suggestions to review.[/dim]")
        return

    console.print(Panel(
        f"[bold]Reviewing {len(suggestions)} pending suggestion(s)[/bold]\n\n"
        "For each suggestion, you can:\n"
        "  [green][a]pprove[/green] - Create the task\n"
        "  [red][r]eject[/red] - Discard the suggestion\n"
        "  [yellow][s]kip[/yellow] - Keep for later\n"
        "  [dim][q]uit[/dim] - Stop reviewing",
        title="Suggestion Review",
    ))

    if auto_approve and auto_reject:
        console.print("[red]Cannot use both --auto-approve and --auto-reject[/red]")
        return

    approved_count = 0
    rejected_count = 0
    skipped_count = 0

    # Process suggestions (iterate while we have any, but use index 0 since approved/rejected get removed)
    index = 0
    while index < len(agent.get_pending_suggestions()):
        suggestions = agent.get_pending_suggestions()
        if index >= len(suggestions):
            break

        suggestion = suggestions[index]
        remaining = len(suggestions) - index

        console.print(f"\n[bold cyan]━━━ Suggestion {index + 1} of {len(suggestions)} ━━━[/bold cyan]")

        # Display suggestion details
        _display_suggestion(suggestion, index + 1, remaining)

        # Get user action
        if auto_approve:
            action = "a"
        elif auto_reject:
            action = "r"
        else:
            action = click.prompt(
                "\n[a]pprove / [r]eject / [s]kip / [q]uit",
                type=click.Choice(["a", "r", "s", "q"], case_sensitive=False),
                default="s",
                show_choices=False,
            )

        if action == "a":
            task_id = agent.approve_suggestion(index)
            if task_id:
                console.print(f"[green]✓ Created task #{task_id}[/green]")
                approved_count += 1
            else:
                console.print("[red]Failed to create task[/red]")
                index += 1
        elif action == "r":
            if agent.reject_suggestion(index):
                console.print("[red]✗ Suggestion rejected[/red]")
                rejected_count += 1
            else:
                console.print("[red]Failed to reject suggestion[/red]")
                index += 1
        elif action == "s":
            console.print("[yellow]→ Skipped[/yellow]")
            skipped_count += 1
            index += 1
        elif action == "q":
            console.print("[dim]Stopping review...[/dim]")
            break

    # Summary
    console.print(f"\n[bold]Review Complete[/bold]")
    console.print(f"  [green]Approved:[/green] {approved_count}")
    console.print(f"  [red]Rejected:[/red] {rejected_count}")
    console.print(f"  [yellow]Skipped:[/yellow] {skipped_count}")

    remaining = len(agent.get_pending_suggestions())
    if remaining > 0:
        console.print(f"  [dim]Remaining:[/dim] {remaining}")


def _display_suggestion(suggestion, number: int, remaining: int) -> None:
    """Display a single suggestion in a rich panel."""
    # Priority emoji and style
    pri_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
        suggestion.priority, "⚪"
    )
    pri_style = {"critical": "bold red", "high": "red", "medium": "yellow", "low": "green"}.get(
        suggestion.priority, "white"
    )

    # Build content
    lines = [
        f"[bold]{pri_emoji} {suggestion.title}[/bold]",
        "",
        f"[{pri_style}]Priority: {suggestion.priority.upper()}[/{pri_style}]   "
        f"Confidence: {suggestion.confidence:.0%}",
    ]

    if suggestion.description:
        lines.append(f"\n[dim]Description:[/dim] {suggestion.description[:200]}{'...' if len(suggestion.description or '') > 200 else ''}")

    if suggestion.due_date:
        lines.append(f"[cyan]Due:[/cyan] {format_due_date(suggestion.due_date)}")

    if suggestion.tags:
        tags_str = ", ".join(f"#{t}" for t in suggestion.tags)
        lines.append(f"[dim]Tags:[/dim] {tags_str}")

    # Source information
    lines.append("")
    lines.append("[bold dim]Source Information[/bold dim]")

    if suggestion.source:
        source_emoji = {
            "gmail": "📧", "slack": "💬", "calendar": "📅", "drive": "📁"
        }.get(suggestion.source.value, "📌")
        lines.append(f"{source_emoji} Source: [cyan]{suggestion.source.value.title()}[/cyan]")

    if suggestion.original_sender:
        lines.append(f"   From: {suggestion.original_sender}")

    if suggestion.original_title:
        lines.append(f"   Subject: {suggestion.original_title[:60]}{'...' if len(suggestion.original_title or '') > 60 else ''}")

    if suggestion.source_url:
        lines.append(f"   [link={suggestion.source_url}]🔗 Open in browser[/link]")
        lines.append(f"   [dim]{suggestion.source_url}[/dim]")

    # Reasoning
    if suggestion.reasoning:
        lines.append("")
        lines.append("[bold dim]Why this suggestion?[/bold dim]")
        lines.append(f"[italic]{suggestion.reasoning}[/italic]")

    # Original content snippet
    if suggestion.original_snippet:
        lines.append("")
        lines.append("[bold dim]Original Content Preview[/bold dim]")
        lines.append(f"[dim]{suggestion.original_snippet}[/dim]")

    console.print(Panel("\n".join(lines), title=f"Suggestion #{number}", border_style="cyan"))


# --- Account Commands ---


@cli.group()
def accounts():
    """Manage Google account connections."""
    pass


@accounts.command("list")
def accounts_list():
    """List all connected Google accounts."""
    config = get_config()
    google_config = config.google

    if not google_config.enabled or not google_config.accounts:
        console.print("[yellow]No Google accounts configured[/yellow]")
        return

    table = Table(title="Connected Google Accounts")
    table.add_column("Account ID", style="cyan")
    table.add_column("Display Name", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Polling Interval", style="magenta")

    for account in google_config.accounts:
        status = "✓ Enabled" if account.enabled else "✗ Disabled"
        table.add_row(
            account.account_id,
            account.display_name,
            status,
            f"{account.polling_interval_minutes} min",
        )

    console.print(table)


@accounts.command("authenticate")
@click.argument("account_type")
@click.argument("account_id")
def accounts_authenticate(account_type: str, account_id: str):
    """Run OAuth flow for a specific account.

    Examples:
        pa accounts authenticate google personal
        pa accounts authenticate granola all
    """
    config = get_config()

    if account_type == "google":
        # Find Google account config
        account_config = next(
            (acc for acc in config.google.accounts if acc.account_id == account_id),
            None,
        )

        if not account_config:
            console.print(f"[red]Account not found: {account_id}[/red]")
            console.print("[yellow]Available Google accounts:[/yellow]")
            for acc in config.google.accounts:
                console.print(f"  - {acc.account_id} ({acc.display_name})")
            return

        # Run Google OAuth flow
        from src.integrations.oauth_utils import GoogleOAuthManager

        try:
            oauth_manager = GoogleOAuthManager(
                credentials_path=account_config.credentials_path,
                token_path=account_config.token_path,
                scopes=account_config.scopes,
            )

            creds = oauth_manager.get_credentials()
            if creds:
                console.print(f"[green]✓ Successfully authenticated Google account: {account_id}[/green]")
            else:
                console.print(f"[red]✗ Authentication failed for {account_id}[/red]")
        except Exception as e:
            console.print(f"[red]✗ Authentication error: {e}[/red]")

    elif account_type == "granola":
        # Find Granola workspace config
        workspace_config = next(
            (ws for ws in config.granola.workspaces if ws.workspace_id == account_id),
            None,
        )

        if not workspace_config:
            console.print(f"[red]Workspace not found: {account_id}[/red]")
            console.print("[yellow]Available Granola workspaces:[/yellow]")
            for ws in config.granola.workspaces:
                display_name = ws.display_name or ws.workspace_id
                console.print(f"  - {ws.workspace_id} ({display_name})")
            return

        # Run Granola OAuth flow
        from pathlib import Path
        from src.integrations.granola_oauth import GranolaOAuthManager

        try:
            # Get token path
            if workspace_config.token_path:
                token_path = Path(workspace_config.token_path)
            else:
                token_path = Path.home() / ".personal-assistant" / "token.granola.json"

            console.print("[bold]Starting Granola OAuth authentication...[/bold]")
            console.print("A browser window will open for you to authorize access.")
            console.print()

            oauth_manager = GranolaOAuthManager(token_path)

            # Run async authentication
            import asyncio
            token = asyncio.run(oauth_manager.authenticate())

            if token:
                console.print()
                console.print(f"[green]✓ Successfully authenticated Granola workspace: {account_id}[/green]")
                console.print(f"[dim]Token saved to: {token_path}[/dim]")
            else:
                console.print(f"[red]✗ Authentication failed for {account_id}[/red]")
        except Exception as e:
            console.print(f"[red]✗ Authentication error: {e}[/red]")

    else:
        console.print(f"[red]Unknown account type: {account_type}[/red]")
        console.print("[yellow]Supported account types: google, granola[/yellow]")


@accounts.command("granola-notes")
@click.option("--limit", "-n", default=20, help="Number of notes to show")
@click.option("--workspace", "-w", help="Filter by workspace ID")
def accounts_granola_notes(limit: int, workspace: str | None):
    """Show processed Granola meeting notes.

    Displays which Granola meetings have been processed for actionable items.

    Examples:
        pa accounts granola-notes
        pa accounts granola-notes --limit 50
        pa accounts granola-notes --workspace all
    """
    from src.models import ProcessedGranolaNote

    with get_db_session() as db:
        query = db.query(ProcessedGranolaNote).order_by(
            ProcessedGranolaNote.processed_at.desc()
        )

        if workspace:
            query = query.filter(ProcessedGranolaNote.workspace_id == workspace)

        notes = query.limit(limit).all()

        if not notes:
            console.print("[yellow]No Granola notes have been processed yet.[/yellow]")
            return

        table = Table(title=f"Processed Granola Meeting Notes (showing {len(notes)})")
        table.add_column("Title", style="cyan", no_wrap=False, max_width=40)
        table.add_column("Workspace", style="green")
        table.add_column("Meeting Date", style="blue")
        table.add_column("Processed", style="magenta")
        table.add_column("Tasks", style="yellow", justify="right")

        for note in notes:
            meeting_date = note.note_created_at.strftime("%b %d, %Y %I:%M %p")
            processed_date = note.processed_at.strftime("%b %d %I:%M %p")

            table.add_row(
                note.note_title[:40],
                note.workspace_id,
                meeting_date,
                processed_date,
                str(note.tasks_created_count),
            )

        console.print(table)
        console.print(f"\n[dim]Total processed notes: {len(notes)}[/dim]")

        # Show summary stats
        total_tasks = sum(note.tasks_created_count for note in notes)
        console.print(f"[dim]Total tasks created: {total_tasks}[/dim]")


@accounts.command("granola-reprocess")
@click.argument("search", required=False)
@click.option("--id", "meeting_id", help="Meeting ID to reprocess")
@click.option("--title", help="Search for meeting by title")
@click.option("--all", "reprocess_all", is_flag=True, help="Reprocess all meetings")
def accounts_granola_reprocess(search: str | None, meeting_id: str | None, title: str | None, reprocess_all: bool):
    """Mark Granola meeting(s) for reprocessing.

    Removes meeting(s) from the processed list so they will be picked up
    on the next agent poll and reprocessed for action items.

    Examples:
        pa accounts granola-reprocess --id 4e4d36e7-a98c-4ab6-a8b1-6431d9fbffdd
        pa accounts granola-reprocess --title "Docker desktop"
        pa accounts granola-reprocess "Roberta"
        pa accounts granola-reprocess --all
    """
    from src.models import ProcessedGranolaNote

    with get_db_session() as db:
        # Build query
        if reprocess_all:
            # Confirm before deleting all
            count = db.query(ProcessedGranolaNote).count()
            if count == 0:
                console.print("[yellow]No processed meetings found.[/yellow]")
                return

            console.print(f"[yellow]⚠️  This will mark {count} meeting(s) for reprocessing.[/yellow]")
            confirm = click.confirm("Are you sure?", default=False)
            if not confirm:
                console.print("[dim]Cancelled.[/dim]")
                return

            db.query(ProcessedGranolaNote).delete()
            db.commit()
            console.print(f"[green]✓ Marked {count} meeting(s) for reprocessing.[/green]")
            console.print("[dim]Run 'pa agent poll' to reprocess meetings.[/dim]")
            return

        # Find by meeting ID
        if meeting_id:
            note = db.query(ProcessedGranolaNote).filter(
                ProcessedGranolaNote.note_id == meeting_id
            ).first()

            if not note:
                console.print(f"[red]✗ No processed meeting found with ID: {meeting_id}[/red]")
                return

            console.print(f"[cyan]Meeting:[/cyan] {note.note_title}")
            console.print(f"[dim]ID: {note.note_id}[/dim]")
            console.print(f"[dim]Processed: {note.processed_at.strftime('%b %d, %Y %I:%M %p')}[/dim]")
            console.print(f"[dim]Tasks created: {note.tasks_created_count}[/dim]")

            confirm = click.confirm("\nMark this meeting for reprocessing?", default=True)
            if not confirm:
                console.print("[dim]Cancelled.[/dim]")
                return

            db.delete(note)
            db.commit()
            console.print("[green]✓ Meeting marked for reprocessing.[/green]")
            console.print("[dim]Run 'pa agent poll' to reprocess.[/dim]")
            return

        # Find by title search (either --title or positional argument)
        search_term = title or search
        if not search_term:
            console.print("[red]✗ Please provide a search term, --id, --title, or --all[/red]")
            console.print("[dim]Example: pa accounts granola-reprocess 'Docker desktop'[/dim]")
            return

        # Search for matching meetings
        notes = db.query(ProcessedGranolaNote).filter(
            ProcessedGranolaNote.note_title.ilike(f"%{search_term}%")
        ).order_by(ProcessedGranolaNote.processed_at.desc()).all()

        if not notes:
            console.print(f"[yellow]No processed meetings found matching: {search_term}[/yellow]")
            return

        if len(notes) == 1:
            # Single match - show details and confirm
            note = notes[0]
            console.print(f"[cyan]Found:[/cyan] {note.note_title}")
            console.print(f"[dim]ID: {note.note_id}[/dim]")
            console.print(f"[dim]Processed: {note.processed_at.strftime('%b %d, %Y %I:%M %p')}[/dim]")
            console.print(f"[dim]Tasks created: {note.tasks_created_count}[/dim]")

            confirm = click.confirm("\nMark this meeting for reprocessing?", default=True)
            if not confirm:
                console.print("[dim]Cancelled.[/dim]")
                return

            db.delete(note)
            db.commit()
            console.print("[green]✓ Meeting marked for reprocessing.[/green]")
            console.print("[dim]Run 'pa agent poll' to reprocess.[/dim]")
        else:
            # Multiple matches - show list and let user choose
            console.print(f"[cyan]Found {len(notes)} matching meetings:[/cyan]\n")

            table = Table(show_header=True, header_style="bold")
            table.add_column("#", style="dim", width=3)
            table.add_column("Title", style="cyan", no_wrap=False)
            table.add_column("Date", style="blue")
            table.add_column("Tasks", style="yellow", justify="right")

            for i, note in enumerate(notes, 1):
                meeting_date = note.note_created_at.strftime("%b %d, %Y")
                table.add_row(
                    str(i),
                    note.note_title[:60],
                    meeting_date,
                    str(note.tasks_created_count),
                )

            console.print(table)

            # Ask user to choose
            console.print("\n[dim]Enter number to reprocess, 'all' for all matches, or 'cancel' to abort:[/dim]")
            choice = click.prompt("Choice", type=str, default="cancel")

            if choice.lower() == "cancel":
                console.print("[dim]Cancelled.[/dim]")
                return

            if choice.lower() == "all":
                confirm = click.confirm(f"Mark all {len(notes)} meeting(s) for reprocessing?", default=False)
                if not confirm:
                    console.print("[dim]Cancelled.[/dim]")
                    return

                for note in notes:
                    db.delete(note)
                db.commit()
                console.print(f"[green]✓ Marked {len(notes)} meeting(s) for reprocessing.[/green]")
                console.print("[dim]Run 'pa agent poll' to reprocess.[/dim]")
                return

            # Single choice by number
            try:
                idx = int(choice) - 1
                if idx < 0 or idx >= len(notes):
                    console.print("[red]✗ Invalid choice.[/red]")
                    return

                note = notes[idx]
                db.delete(note)
                db.commit()
                console.print(f"[green]✓ Meeting '{note.note_title}' marked for reprocessing.[/green]")
                console.print("[dim]Run 'pa agent poll' to reprocess.[/dim]")
            except ValueError:
                console.print("[red]✗ Invalid choice.[/red]")


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
@click.option("--account", "-a", "account_id", help="Filter by source account ID")
@click.option("--link", "-l", help="Filter by document link URL")
@click.option("--initiative", "-i", type=int, help="Filter by initiative ID")
@click.option("--all", "show_all", is_flag=True, help="Include completed tasks")
@click.option("--limit", "-n", default=20, help="Number of tasks to show")
def tasks_list(status, priority, account_id, link, initiative, show_all, limit):
    """List tasks."""
    with get_db_session() as db:
        service = TaskService(db)

        # Build filters
        status_filter = TaskStatus(status) if status else None
        priority_filter = TaskPriority(priority) if priority else None

        tasks, total = service.get_tasks(
            status=status_filter,
            priority=priority_filter,
            account_id=account_id,
            document_links=[link] if link else None,
            include_completed=show_all,
            limit=limit,
        )

        # Filter by initiative if specified
        if initiative is not None:
            tasks = [t for t in tasks if t.initiative_id == initiative]
            total = len(tasks)

        if not tasks:
            console.print("[dim]No tasks found.[/dim]")
            return

        table = Table(title=f"Tasks ({len(tasks)} of {total})")
        table.add_column("ID", style="dim", width=4)
        table.add_column("Pri", width=3)
        table.add_column("Title", style="white", min_width=20, max_width=40)
        table.add_column("Status", width=12)
        table.add_column("Due", width=15)
        table.add_column("Initiative", style="cyan", width=15)
        table.add_column("Links", style="cyan", width=5)

        for task in tasks:
            pri_style = get_priority_style(task.priority)
            status_style = get_status_style(task.status)
            pri_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                task.priority.value, "⚪"
            )

            title_text = task.title[:40] if task.title else "(no title)"
            initiative_text = task.initiative.title[:15] if task.initiative else "-"
            link_icon = "🔗" if task.get_document_links_list() else ""
            table.add_row(
                str(task.id),
                pri_emoji,
                f"[{pri_style}]{title_text}[/{pri_style}]",
                Text(task.status.value, style=status_style),
                format_due_date(task.due_date),
                initiative_text,
                link_icon,
            )

        console.print(table)


@tasks.command("add")
@click.argument("title")
@click.option("--description", "-d", help="Task description")
@click.option("--priority", "-p", type=click.Choice([p.value for p in TaskPriority]),
              default="medium", help="Priority level")
@click.option("--due", "-D", help="Due date (YYYY-MM-DD or 'tomorrow', '+3d')")
@click.option("--tags", "-t", multiple=True, help="Tags (can specify multiple)")
@click.option("--link", "-l", multiple=True, help="Document link URL (can specify multiple)")
@click.option("--initiative", "-i", type=int, help="Link to initiative by ID")
def tasks_add(title, description, priority, due, tags, link, initiative):
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

        # Validate initiative if provided
        if initiative:
            initiative_service = InitiativeService(db)
            if not initiative_service.get_initiative(initiative):
                console.print(f"[red]Initiative #{initiative} not found.[/red]")
                return

        task = service.create_task(
            title=title,
            description=description,
            priority=TaskPriority(priority),
            source=TaskSource.MANUAL,
            due_date=due_date,
            tags=list(tags) if tags else None,
            document_links=list(link) if link else None,
            initiative_id=initiative,
        )

        console.print(f"[green]✓[/green] Created task #{task.id}: {task.title}")
        if task.initiative:
            console.print(f"  [cyan]Initiative:[/cyan] {task.initiative.title}")
        if task.document_links:
            console.print(f"  [cyan]Document Links:[/cyan]")
            for doc_link in task.get_document_links_list():
                console.print(f"    • {doc_link}")


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


@tasks.command("link-add")
@click.argument("task_id", type=int)
@click.argument("url")
def tasks_link_add(task_id, url):
    """Add a document link to a task."""
    # Validate URL format
    import urllib.parse

    try:
        parsed = urllib.parse.urlparse(url)
        if not all([parsed.scheme, parsed.netloc]):
            console.print(f"[red]Invalid URL format: {url}[/red]")
            console.print("[yellow]URL must include scheme and domain (e.g., https://example.com)[/yellow]")
            return

        if parsed.scheme not in ['http', 'https']:
            console.print(f"[red]Only http:// and https:// URLs are allowed[/red]")
            console.print(f"[yellow]Got: {parsed.scheme}://[/yellow]")
            return
    except Exception as e:
        console.print(f"[red]Invalid URL: {e}[/red]")
        return

    with get_db_session() as db:
        service = TaskService(db)
        task = service.get_task(task_id)

        if not task:
            console.print(f"[red]Task #{task_id} not found.[/red]")
            return

        links = task.get_document_links_list()
        if url in links:
            console.print(f"[yellow]Link already exists on task #{task_id}[/yellow]")
            return

        links.append(url)
        service.update_task(task, document_links=links)
        console.print(f"[green]✓[/green] Added link to task #{task_id}")
        console.print(f"  {url}")


@tasks.command("link-remove")
@click.argument("task_id", type=int)
@click.argument("url")
def tasks_link_remove(task_id, url):
    """Remove a document link from a task."""
    with get_db_session() as db:
        service = TaskService(db)
        task = service.get_task(task_id)

        if not task:
            console.print(f"[red]Task #{task_id} not found.[/red]")
            return

        links = task.get_document_links_list()
        if url not in links:
            console.print(f"[yellow]Link not found on task #{task_id}[/yellow]")
            return

        links.remove(url)
        service.update_task(task, document_links=links)
        console.print(f"[green]✓[/green] Removed link from task #{task_id}")


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

        if task.initiative:
            info_lines.append(f"Initiative: [cyan]{task.initiative.title}[/cyan] (#{task.initiative.id})")

        if task.description:
            info_lines.extend(["", f"Description: {task.description}"])

        if task.due_date:
            info_lines.append(f"Due: {format_due_date(task.due_date)}")

        tags = task.get_tags_list()
        if tags:
            info_lines.append(f"Tags: {', '.join(tags)}")

        doc_links = task.get_document_links_list()
        if doc_links:
            info_lines.append("")
            info_lines.append("[bold cyan]Document Links:[/bold cyan]")
            for link in doc_links:
                info_lines.append(f"  • {link}")

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


@tasks.command("due")
@click.argument("task_id", type=int)
@click.argument("date", required=False)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option("--clear", "-c", is_flag=True, help="Clear the due date")
def tasks_due(task_id, date, yes, clear):
    """Update a task's due date.

    Supports natural language dates like "tomorrow", "next Friday",
    "end of month", or standard formats like "2026-02-15".

    Examples:

        pa tasks due 5 tomorrow

        pa tasks due 5 "next Friday"

        pa tasks due 5 --clear
    """
    # Validate arguments
    if not date and not clear:
        console.print("[red]Please provide a date or use --clear to remove the due date.[/red]")
        return

    if date and clear:
        console.print("[red]Cannot specify both a date and --clear.[/red]")
        return

    with get_db_session() as db:
        service = TaskService(db)
        task = service.get_task(task_id)

        if not task:
            console.print(f"[red]Task #{task_id} not found.[/red]")
            return

        # Show current task info
        current_due = format_due_date(task.due_date) if task.due_date else "[dim]None[/dim]"

        if clear:
            # Clear the due date
            new_due_date = None
            new_due_display = "[dim]None[/dim]"
        else:
            # Try simple parsing first
            new_due_date = parse_due_date(date)

            # If simple parsing fails, try LLM
            if new_due_date is None:
                config = get_config()

                if not config.llm.api_key:
                    console.print(f"[red]Could not parse date: {date}[/red]")
                    console.print("[dim]Simple formats: 'today', 'tomorrow', '+3d', '+2w', 'YYYY-MM-DD'[/dim]")
                    console.print("[dim]For complex dates like 'next Friday', configure an LLM API key.[/dim]")
                    return

                # Use LLM to parse complex date
                from src.services.llm_service import LLMService, LLMError

                llm_service = LLMService(config.llm)

                try:
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        console=console,
                    ) as progress:
                        progress.add_task("Parsing date...", total=None)
                        new_due_date = run_async(llm_service.parse_date(date))

                    if new_due_date is None:
                        console.print(f"[red]Could not parse date: {date}[/red]")
                        return

                except LLMError as e:
                    console.print(f"[red]LLM error: {e}[/red]")
                    return

            new_due_display = format_due_date(new_due_date)

        # Show change summary
        console.print(f"\n[bold]Task #{task_id}:[/bold] {task.title}")
        console.print(f"  Current due: {current_due}")
        console.print(f"  New due:     {new_due_display}")

        # Confirm unless --yes
        if not yes:
            if not click.confirm("\nUpdate due date?", default=True):
                console.print("[dim]Cancelled.[/dim]")
                return

        # Update the task
        service.update_task(task, due_date=new_due_date)
        console.print(f"[green]✓[/green] Updated due date for task #{task_id}")


@tasks.command("merge")
@click.argument("task_ids", type=int, nargs=-1, required=True)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option("--keep", "-k", is_flag=True, help="Keep original tasks instead of deleting them")
def tasks_merge(task_ids, yes, keep):
    """Merge multiple tasks into a single task.

    Combines tasks using AI to create a unified title, takes the highest
    priority, earliest due date, and merges descriptions and tags.

    Examples:

        pa tasks merge 1 2 3

        pa tasks merge 5 6 --keep

        pa tasks merge 10 11 12 --yes
    """
    from src.services.llm_service import LLMService, LLMError

    # Validate at least 2 tasks
    if len(task_ids) < 2:
        console.print("[red]Please provide at least 2 task IDs to merge.[/red]")
        return

    config = get_config()

    # Check if LLM is configured
    if not config.llm.api_key:
        console.print("[red]LLM API key not configured.[/red]")
        console.print("[dim]Set llm.api_key in config.yaml or PA_LLM__API_KEY env var.[/dim]")
        return

    with get_db_session() as db:
        service = TaskService(db)

        # Fetch all tasks
        tasks_to_merge = []
        for task_id in task_ids:
            task = service.get_task(task_id)
            if not task:
                console.print(f"[red]Task #{task_id} not found.[/red]")
                return
            tasks_to_merge.append(task)

        # Display tasks being merged
        console.print("\n[bold]Tasks to merge:[/bold]")
        for task in tasks_to_merge:
            pri_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                task.priority.value, "⚪"
            )
            due_str = f" - {format_due_date(task.due_date)}" if task.due_date else ""
            console.print(f"  #{task.id}: {pri_emoji} {task.title}{due_str}")

        # Use LLM to merge titles
        llm_service = LLMService(config.llm)
        titles = [task.title for task in tasks_to_merge]

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task("Merging titles...", total=None)
                merged_title = run_async(llm_service.merge_titles(titles))
        except LLMError as e:
            console.print(f"[red]LLM error: {e}[/red]")
            return

        # Determine highest priority (CRITICAL > HIGH > MEDIUM > LOW)
        priority_order = [TaskPriority.CRITICAL, TaskPriority.HIGH, TaskPriority.MEDIUM, TaskPriority.LOW]
        highest_priority = TaskPriority.LOW
        for task in tasks_to_merge:
            if priority_order.index(task.priority) < priority_order.index(highest_priority):
                highest_priority = task.priority

        # Determine earliest due date (ignoring None)
        due_dates = [task.due_date for task in tasks_to_merge if task.due_date]
        earliest_due = min(due_dates) if due_dates else None

        # Combine descriptions (newline separated, skip None/empty)
        descriptions = [task.description for task in tasks_to_merge if task.description]
        merged_description = "\n\n".join(descriptions) if descriptions else None

        # Combine tags (deduplicated)
        all_tags = set()
        for task in tasks_to_merge:
            all_tags.update(task.get_tags_list())
        merged_tags = list(all_tags) if all_tags else None

        # Show preview
        pri_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
            highest_priority.value, "⚪"
        )
        console.print("\n[bold]Merged task preview:[/bold]")
        console.print(f"  Title: {merged_title}")
        console.print(f"  Priority: {pri_emoji} {highest_priority.value}")
        console.print(f"  Due: {format_due_date(earliest_due) if earliest_due else '[dim]None[/dim]'}")
        if merged_tags:
            console.print(f"  Tags: {', '.join(f'#{t}' for t in merged_tags)}")
        if not keep:
            console.print("\n[dim]Original tasks will be deleted.[/dim]")
        else:
            console.print("\n[dim]Original tasks will be kept.[/dim]")

        # Confirm unless --yes
        if not yes:
            if not click.confirm("\nCreate merged task?", default=True):
                console.print("[dim]Cancelled.[/dim]")
                return

        # Create merged task
        merged_task = service.create_task(
            title=merged_title,
            description=merged_description,
            priority=highest_priority,
            source=TaskSource.MANUAL,
            due_date=earliest_due,
            tags=merged_tags,
        )

        console.print(f"\n[green]✓[/green] Created merged task #{merged_task.id}: {merged_title}")

        # Delete original tasks unless --keep
        if not keep:
            for task in tasks_to_merge:
                service.delete_task(task)
            console.print(f"[dim]Deleted {len(tasks_to_merge)} original tasks.[/dim]")


@tasks.command("voice")
@click.option("--duration", "-d", default=10, type=int, help="Recording duration in seconds (1-60)")
@click.option("--transcribe-only", "-t", is_flag=True, help="Only transcribe, don't create a task")
def tasks_voice(duration, transcribe_only):
    """Create a task from voice input.

    Records audio from your microphone, transcribes it using Whisper,
    and creates a task from the transcription.
    """
    from src.services.voice_service import (
        MicrophoneNotFoundError,
        TranscriptionError,
        VoiceError,
        VoiceService,
    )

    config = get_config()

    # Check if voice is enabled
    if not config.voice.enabled:
        console.print("[red]Voice features are disabled in configuration.[/red]")
        console.print("[dim]Set voice.enabled: true in config.yaml to enable.[/dim]")
        return

    # Validate duration
    if duration < 1 or duration > 60:
        console.print("[red]Duration must be between 1 and 60 seconds.[/red]")
        return

    # Initialize voice service
    voice_service = VoiceService(
        voice_config=config.voice,
        llm_config=config.llm,
    )

    # Check microphone availability
    if not voice_service.check_microphone_available():
        console.print("[red]No microphone found.[/red]")
        console.print("[dim]Please connect a microphone and try again.[/dim]")
        return

    try:
        # Recording phase with countdown
        console.print(Panel(
            f"[bold cyan]Recording for {duration} seconds...[/bold cyan]\n"
            "[dim]Speak your task now![/dim]",
            title="🎤 Voice Input",
        ))

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Recording ({duration}s)...", total=None)

            # Record audio
            audio_data = voice_service.record_audio(duration_seconds=duration)

            progress.update(task, description="Transcribing...")

            # Transcribe
            transcription_result = voice_service.transcribe_audio(audio_data)

        if not transcription_result.text:
            console.print("[yellow]No speech detected in the recording.[/yellow]")
            console.print("[dim]Try speaking more clearly or increasing the duration.[/dim]")
            return

        # Show transcription
        console.print(f"\n[bold]Transcription:[/bold]")
        console.print(Panel(transcription_result.text, border_style="cyan"))

        if transcribe_only:
            return

        # Extract and create task
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Analyzing and creating task...", total=None)

            with get_db_session() as db:
                task_service = TaskService(db)

                # Extract task using LLM
                extracted_tasks = run_async(
                    voice_service.extract_task_from_transcription(transcription_result.text)
                )

                if extracted_tasks:
                    task_data = extracted_tasks[0]
                    from src.models.task import TaskPriority, TaskSource

                    created_task = task_service.create_task(
                        title=task_data.title,
                        description=task_data.description,
                        priority=TaskPriority(task_data.priority),
                        source=TaskSource.VOICE,
                        due_date=task_data.due_date,
                        tags=task_data.tags,
                    )
                else:
                    # Fallback: create simple task from transcription
                    from src.models.task import TaskPriority, TaskSource

                    created_task = task_service.create_task(
                        title=transcription_result.text[:200],
                        description=None,
                        priority=TaskPriority.MEDIUM,
                        source=TaskSource.VOICE,
                    )

                # Capture task info while session is still open
                task_id = created_task.id
                task_title = created_task.title
                task_priority = created_task.priority.value
                task_due_date = created_task.due_date
                task_tags = created_task.get_tags_list()

        # Show created task (using captured values)
        pri_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
            task_priority, "⚪"
        )
        console.print(f"\n[green]✓[/green] Created task #{task_id}: {pri_emoji} {task_title}")

        if task_due_date:
            console.print(f"  Due: {format_due_date(task_due_date)}")

        if task_tags:
            console.print(f"  Tags: {', '.join(task_tags)}")

    except MicrophoneNotFoundError:
        console.print("[red]No microphone found.[/red]")
        console.print("[dim]Please connect a microphone and try again.[/dim]")
    except TranscriptionError as e:
        console.print(f"[red]Transcription failed: {e}[/red]")
        console.print("[dim]Check your API key and try again.[/dim]")
    except VoiceError as e:
        console.print(f"[red]Voice error: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")


@tasks.command("associate")
@click.argument("task_id", type=int)
@click.argument("initiative_id", type=int)
def tasks_associate(task_id, initiative_id):
    """Associate a task with an initiative.

    Links a task to an initiative by ID. The task's priority score will
    be recalculated to account for the initiative's priority.

    Examples:

        pa tasks associate 5 2     # Link task #5 to initiative #2
    """
    with get_db_session() as db:
        task_service = TaskService(db)
        initiative_service = InitiativeService(db)

        # Get the task
        task = task_service.get_task(task_id)
        if not task:
            console.print(f"[red]Task #{task_id} not found.[/red]")
            return

        # Get the initiative
        initiative = initiative_service.get_initiative(initiative_id)
        if not initiative:
            console.print(f"[red]Initiative #{initiative_id} not found.[/red]")
            return

        # Show current state
        current_initiative = f"[cyan]{task.initiative.title}[/cyan] (#{task.initiative.id})" if task.initiative else "[dim]None[/dim]"
        console.print(f"\n[bold]Task #{task_id}:[/bold] {task.title}")
        console.print(f"  Current initiative: {current_initiative}")
        console.print(f"  New initiative:     [cyan]{initiative.title}[/cyan] (#{initiative.id})")

        # Update the task
        task_service.update_task(task, initiative_id=initiative_id)
        console.print(f"\n[green]✓[/green] Associated task #{task_id} with initiative #{initiative_id}")


@tasks.command("parse")
@click.argument("text")
@click.option("--dry-run", "-n", is_flag=True, help="Show what would be created without creating")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def tasks_parse(text, dry_run, yes):
    """Create a task from natural language text.

    Uses AI to parse the text and extract task details including
    title, priority, due date, and tags.

    Examples:

        pa tasks parse "call John tomorrow about the project"

        pa tasks parse "urgent: fix production bug ASAP" --yes

        pa tasks parse "send report by Friday" --dry-run
    """
    from src.services.llm_service import LLMService, LLMError

    config = get_config()

    # Check if LLM is configured
    if not config.llm.api_key:
        console.print("[red]LLM API key not configured.[/red]")
        console.print("[dim]Set llm.api_key in config.yaml or PA_LLM__API_KEY env var.[/dim]")
        return

    # Initialize LLM service
    llm_service = LLMService(config.llm)

    # Get active initiatives for LLM context
    initiatives_for_llm = []
    with get_db_session() as db:
        initiative_service = InitiativeService(db)
        active_initiatives = initiative_service.get_active_initiatives()
        initiatives_for_llm = [
            {
                "id": init.id,
                "title": init.title,
                "priority": init.priority.value,
                "description": init.description,
            }
            for init in active_initiatives
        ]

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Analyzing text...", total=None)

            # Extract tasks from text with initiative context
            extracted_tasks = run_async(
                llm_service.extract_tasks_from_text(
                    text=text,
                    source="cli",
                    context="User entered this text via command line to create a task.",
                    initiatives=initiatives_for_llm if initiatives_for_llm else None,
                )
            )

        if not extracted_tasks:
            console.print("[yellow]No tasks could be extracted from the text.[/yellow]")
            if not dry_run:
                # Offer to create a simple task
                if yes or click.confirm("Create a simple task with this text as the title?"):
                    with get_db_session() as db:
                        service = TaskService(db)
                        task = service.create_task(
                            title=text[:200],
                            description=None,
                            priority=TaskPriority.MEDIUM,
                            source=TaskSource.MANUAL,
                        )
                        console.print(f"[green]✓[/green] Created task #{task.id}: {task.title}")
            return

        # Process each extracted task
        created_count = 0
        for i, extracted in enumerate(extracted_tasks, 1):
            # Display extracted task details
            pri_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                extracted.priority, "⚪"
            )
            pri_style = {"critical": "bold red", "high": "red", "medium": "yellow", "low": "green"}.get(
                extracted.priority, "white"
            )

            lines = [
                f"[bold]{pri_emoji} {extracted.title}[/bold]",
                "",
                f"[{pri_style}]Priority: {extracted.priority.upper()}[/{pri_style}]   "
                f"Confidence: {extracted.confidence:.0%}",
            ]

            if extracted.description:
                lines.append(f"[dim]Description:[/dim] {extracted.description[:150]}{'...' if len(extracted.description or '') > 150 else ''}")

            if extracted.due_date:
                lines.append(f"[cyan]Due:[/cyan] {format_due_date(extracted.due_date)}")

            if extracted.tags:
                tags_str = ", ".join(f"#{t}" for t in extracted.tags)
                lines.append(f"[dim]Tags:[/dim] {tags_str}")

            # Show suggested initiative if present
            suggested_initiative_name = None
            if extracted.suggested_initiative_id and initiatives_for_llm:
                suggested = next(
                    (i for i in initiatives_for_llm if i["id"] == extracted.suggested_initiative_id),
                    None,
                )
                if suggested:
                    suggested_initiative_name = suggested["title"]
                    lines.append(f"[cyan]💡 Suggested Initiative:[/cyan] {suggested_initiative_name}")

            title = "Extracted Task" if len(extracted_tasks) == 1 else f"Extracted Task {i}/{len(extracted_tasks)}"
            console.print(Panel("\n".join(lines), title=title, border_style="cyan"))

            if dry_run:
                console.print("[dim]Dry run - task not created.[/dim]")
                continue

            # Confirm creation (unless --yes)
            if not yes and len(extracted_tasks) > 1:
                action = click.prompt(
                    "Create this task?",
                    type=click.Choice(["y", "n", "q"], case_sensitive=False),
                    default="y",
                    show_choices=True,
                )
                if action == "q":
                    console.print("[dim]Stopped.[/dim]")
                    break
                if action == "n":
                    console.print("[dim]Skipped.[/dim]")
                    continue
            elif not yes:
                if not click.confirm("Create this task?", default=True):
                    console.print("[dim]Task not created.[/dim]")
                    continue

            # Ask about initiative association if suggested
            initiative_id = None
            if extracted.suggested_initiative_id and not dry_run:
                if yes or click.confirm(
                    f"Link to initiative '{suggested_initiative_name}'?",
                    default=True,
                ):
                    initiative_id = extracted.suggested_initiative_id

            # Create the task
            with get_db_session() as db:
                service = TaskService(db)
                task = service.create_task(
                    title=extracted.title,
                    description=extracted.description,
                    priority=TaskPriority(extracted.priority),
                    source=TaskSource.MANUAL,
                    due_date=extracted.due_date,
                    tags=extracted.tags,
                    initiative_id=initiative_id,
                )
                console.print(f"[green]✓[/green] Created task #{task.id}: {task.title}")
                if initiative_id:
                    console.print(f"  [cyan]Initiative:[/cyan] {suggested_initiative_name}")
                created_count += 1

        if len(extracted_tasks) > 1 and not dry_run:
            console.print(f"\n[bold]Created {created_count} of {len(extracted_tasks)} task(s).[/bold]")

    except LLMError as e:
        console.print(f"[red]LLM error: {e}[/red]")
        console.print("[dim]Check your API key and try again.[/dim]")
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")


# --- Initiatives Commands ---


def _do_list_initiatives(show_all, priority):
    """Helper function for listing initiatives."""
    with get_db_session() as db:
        service = InitiativeService(db)

        priority_filter = InitiativePriority(priority) if priority else None
        initiatives_data = service.get_initiatives_with_progress(
            include_completed=show_all
        )

        # Filter by priority if specified
        if priority_filter:
            initiatives_data = [
                item for item in initiatives_data
                if item["initiative"].priority == priority_filter
            ]

        if not initiatives_data:
            console.print("[dim]No initiatives found.[/dim]")
            return

        table = Table(title=f"Initiatives ({len(initiatives_data)})")
        table.add_column("ID", style="dim", width=4)
        table.add_column("Pri", width=3)
        table.add_column("Title", style="white", min_width=20, max_width=40)
        table.add_column("Status", width=10)
        table.add_column("Progress", width=12)
        table.add_column("Target", width=12)

        for item in initiatives_data:
            initiative = item["initiative"]
            progress = item["progress"]

            pri_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                initiative.priority.value, "⚪"
            )

            status_style = {
                InitiativeStatus.ACTIVE: "green",
                InitiativeStatus.PAUSED: "yellow",
                InitiativeStatus.COMPLETED: "dim",
            }.get(initiative.status, "white")

            progress_pct = progress["progress_percent"]
            progress_str = f"{progress_pct:.0f}% ({progress['completed_tasks']}/{progress['total_tasks']})"

            target_str = initiative.target_date.strftime("%Y-%m-%d") if initiative.target_date else "-"

            table.add_row(
                str(initiative.id),
                pri_emoji,
                initiative.title[:40],
                Text(initiative.status.value, style=status_style),
                progress_str,
                target_str,
            )

        console.print(table)


@cli.group()
def initiatives():
    """Initiative management commands."""
    pass


@cli.group(name="itvs")
def itvs():
    """Initiative management commands (alias: itvs)."""
    pass


@initiatives.command("list")
@click.option("--all", "-a", "show_all", is_flag=True, help="Include completed initiatives")
@click.option("--priority", "-p", type=click.Choice([p.value for p in InitiativePriority]),
              help="Filter by priority")
def initiatives_list(show_all, priority):
    """List initiatives."""
    _do_list_initiatives(show_all, priority)


@initiatives.command("add")
@click.argument("title")
@click.option("--description", "-d", help="Initiative description")
@click.option("--priority", "-p", type=click.Choice([p.value for p in InitiativePriority]),
              default="medium", help="Priority level")
@click.option("--target", "-t", help="Target date (YYYY-MM-DD)")
def initiatives_add(title, description, priority, target):
    """Add a new initiative."""
    # Parse target date
    target_date = None
    if target:
        target_date = parse_due_date(target)
        if not target_date:
            console.print(f"[red]Invalid target date format: {target}[/red]")
            return

    with get_db_session() as db:
        service = InitiativeService(db)
        initiative = service.create_initiative(
            title=title,
            description=description,
            priority=InitiativePriority(priority),
            target_date=target_date,
        )

        console.print(f"[green]✓[/green] Created initiative #{initiative.id}: {initiative.title}")


@initiatives.command("show")
@click.argument("initiative_id", type=int)
def initiatives_show(initiative_id):
    """Show initiative details."""
    with get_db_session() as db:
        service = InitiativeService(db)
        initiative = service.get_initiative(initiative_id)

        if not initiative:
            console.print(f"[red]Initiative #{initiative_id} not found.[/red]")
            return

        progress = service.get_initiative_progress(initiative_id)
        tasks = service.get_tasks_for_initiative(initiative_id, include_completed=False)

        pri_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
            initiative.priority.value, "⚪"
        )

        info_lines = [
            f"[bold]{pri_emoji} {initiative.title}[/bold]",
            "",
            f"Status: {initiative.status.value}",
            f"Priority: {initiative.priority.value}",
            f"Progress: {progress['progress_percent']:.0f}% ({progress['completed_tasks']}/{progress['total_tasks']} tasks)",
        ]

        if initiative.target_date:
            info_lines.append(f"Target: {format_due_date(initiative.target_date)}")

        if initiative.description:
            info_lines.extend(["", f"Description: {initiative.description}"])

        info_lines.extend([
            "",
            f"Created: {initiative.created_at.strftime('%Y-%m-%d %H:%M')}",
        ])

        console.print(Panel("\n".join(info_lines), title=f"Initiative #{initiative.id}"))

        # Show linked tasks
        if tasks:
            console.print(f"\n[bold]Active Tasks ({len(tasks)}):[/bold]")
            for task in tasks[:10]:
                pri_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                    task.priority.value, "⚪"
                )
                console.print(f"  {pri_emoji} #{task.id} {task.title[:50]}")
            if len(tasks) > 10:
                console.print(f"  [dim]... and {len(tasks) - 10} more[/dim]")


@initiatives.command("complete")
@click.argument("initiative_id", type=int)
def initiatives_complete(initiative_id):
    """Mark an initiative as completed."""
    with get_db_session() as db:
        service = InitiativeService(db)
        initiative = service.get_initiative(initiative_id)

        if not initiative:
            console.print(f"[red]Initiative #{initiative_id} not found.[/red]")
            return

        service.update_initiative(initiative, status=InitiativeStatus.COMPLETED)
        console.print(f"[green]✓[/green] Completed initiative #{initiative_id}: {initiative.title}")


@initiatives.command("delete")
@click.argument("initiative_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def initiatives_delete(initiative_id, yes):
    """Delete an initiative."""
    with get_db_session() as db:
        service = InitiativeService(db)
        initiative = service.get_initiative(initiative_id)

        if not initiative:
            console.print(f"[red]Initiative #{initiative_id} not found.[/red]")
            return

        if not yes:
            if not click.confirm(f"Delete initiative '{initiative.title}'? Tasks will be unlinked."):
                return

        service.delete_initiative(initiative)
        console.print(f"[green]✓[/green] Deleted initiative #{initiative_id}")


@initiatives.command("add-tasks")
@click.argument("initiative_id", type=int)
@click.argument("task_ids", type=int, nargs=-1, required=True)
def initiatives_add_tasks(initiative_id, task_ids):
    """Associate multiple tasks with an initiative.

    Links one or more tasks to an initiative. The tasks' priority scores
    will be recalculated to account for the initiative's priority.

    Examples:

        pa initiatives add-tasks 2 5 6 7      # Link tasks #5, #6, #7 to initiative #2

        pa itvs add-tasks 1 10 11 12 13       # Link tasks to initiative #1 (alias: itvs)
    """
    with get_db_session() as db:
        task_service = TaskService(db)
        initiative_service = InitiativeService(db)

        # Get the initiative
        initiative = initiative_service.get_initiative(initiative_id)
        if not initiative:
            console.print(f"[red]Initiative #{initiative_id} not found.[/red]")
            return

        # Fetch all tasks and check they exist
        tasks_to_link = []
        invalid_ids = []

        for task_id in task_ids:
            task = task_service.get_task(task_id)
            if not task:
                invalid_ids.append(task_id)
            else:
                tasks_to_link.append(task)

        if invalid_ids:
            console.print(f"[red]Task(s) not found: {', '.join(f'#{id}' for id in invalid_ids)}[/red]")
            if not tasks_to_link:
                return
            console.print(f"[yellow]Continuing with {len(tasks_to_link)} valid task(s)...[/yellow]")

        # Display what we're doing
        console.print(f"\n[bold]Initiative #{initiative_id}:[/bold] {initiative.title}")
        console.print(f"[bold]Tasks to associate:[/bold]")
        for task in tasks_to_link:
            pri_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                task.priority.value, "⚪"
            )
            current_init = f" (currently in {task.initiative.title})" if task.initiative else ""
            console.print(f"  {pri_emoji} #{task.id}: {task.title[:50]}{current_init}")

        # Update all tasks
        updated_count = 0
        for task in tasks_to_link:
            task_service.update_task(task, initiative_id=initiative_id)
            updated_count += 1

        console.print(f"\n[green]✓[/green] Associated {updated_count} task(s) with initiative #{initiative_id}")


# --- Alias commands (itvs) --- 
@itvs.command("list")
@click.option("--all", "-a", "show_all", is_flag=True, help="Include completed initiatives")
@click.option("--priority", "-p", type=click.Choice([p.value for p in InitiativePriority]),
              help="Filter by priority")
def itvs_list(show_all, priority):
    """List initiatives."""
    _do_list_initiatives(show_all, priority)


@itvs.command("add")
@click.argument("title")
@click.option("--description", "-d", help="Initiative description")
@click.option("--priority", "-p", type=click.Choice([p.value for p in InitiativePriority]),
              default="medium", help="Priority level")
@click.option("--target", "-t", help="Target date (YYYY-MM-DD)")
def itvs_add(title, description, priority, target):
    """Add a new initiative."""
    initiatives_add(title, description, priority, target)


@itvs.command("show")
@click.argument("initiative_id", type=int)
def itvs_show(initiative_id):
    """Show initiative details."""
    initiatives_show(initiative_id)


@itvs.command("complete")
@click.argument("initiative_id", type=int)
def itvs_complete(initiative_id):
    """Mark an initiative as completed."""
    initiatives_complete(initiative_id)


@itvs.command("delete")
@click.argument("initiative_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def itvs_delete(initiative_id, yes):
    """Delete an initiative."""
    initiatives_delete(initiative_id, yes)


@itvs.command("add-tasks")
@click.argument("initiative_id", type=int)
@click.argument("task_ids", type=int, nargs=-1, required=True)
def itvs_add_tasks(initiative_id, task_ids):
    """Associate multiple tasks with an initiative."""
    initiatives_add_tasks(initiative_id, task_ids)


# --- Summary Command ---


@cli.command()
def summary():
    """Show daily summary and recommendations."""
    with get_db_session() as db:
        task_service = TaskService(db)
        initiative_service = InitiativeService(db)

        stats = task_service.get_statistics()
        top_tasks = task_service.get_prioritized_tasks(limit=5)
        overdue = task_service.get_overdue_tasks()
        initiatives_data = initiative_service.get_initiatives_with_progress(include_completed=False)

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
        console.print(f"  🎯 Active Initiatives: [cyan]{len(initiatives_data)}[/cyan]")

        # Active initiatives
        if initiatives_data:
            console.print("\n[bold]Active Initiatives:[/bold]")
            for item in initiatives_data[:5]:
                initiative = item["initiative"]
                progress = item["progress"]
                pri_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                    initiative.priority.value, "⚪"
                )
                console.print(
                    f"  {pri_emoji} {initiative.title[:40]} - "
                    f"[cyan]{progress['progress_percent']:.0f}%[/cyan]"
                )

        # Top priorities
        if top_tasks:
            console.print("\n[bold]Top Priorities:[/bold]")
            for i, task in enumerate(top_tasks, 1):
                pri_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                    task.priority.value, "⚪"
                )
                initiative_str = f" [{task.initiative.title[:15]}]" if task.initiative else ""
                console.print(f"  {i}. {pri_emoji} {task.title[:50]}{initiative_str}")

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


# --- macOS Menu Bar Command ---


@cli.command(name="macos-menu")
@click.option("--api-url", default="http://localhost:8000",
              help="Base URL of the personal assistant API (default: http://localhost:8000)")
@click.option("--start-api", is_flag=True, default=True,
              help="Start the API server if not running (default: True)")
@click.option("--no-start-api", is_flag=True,
              help="Don't start the API server automatically")
@click.option("--refresh-interval", "-r", default=300, type=int,
              help="How often to refresh task data in seconds (default: 300)")
def macos_menu(api_url, start_api, no_start_api, refresh_interval):
    """Start the macOS menu bar task counter (macOS only).

    Displays a menu bar icon showing the count of tasks due today or overdue,
    with a dropdown menu to view the task list.

    Examples:

        pa macos-menu                    # Start with default settings

        pa macos-menu --refresh-interval 120  # Update every 2 minutes

        pa macos-menu --api-url http://localhost:9000  # Custom API URL
    """
    import sys
    import platform

    # Check if running on macOS
    if platform.system() != "Darwin":
        console.print("[red]✗[/red] This command is only available on macOS.")
        sys.exit(1)

    # Try to import macOS modules
    try:
        from src.macos.launcher import launch
    except ImportError:
        console.print(
            "[red]✗ macOS integration not available.[/red]\n"
            "[yellow]Install PyObjC:[/yellow]\n"
            "  pip install -e '.[macos]'"
        )
        sys.exit(1)

    # Launch the menu bar app
    try:
        launch(
            api_url=api_url,
            start_api=(not no_start_api) and start_api,
            refresh_interval=refresh_interval,
        )
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        sys.exit(1)


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
