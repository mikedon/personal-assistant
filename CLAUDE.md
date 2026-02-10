# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference

```bash
# Install (with dev dependencies)
pip install -e ".[dev]"

# Run tests
pytest                          # All tests
pytest tests/unit/              # Unit tests only
pytest tests/integration/       # Integration tests only
pytest tests/unit/test_task_service.py::test_function_name  # Single test
pytest --cov=src --cov-report=html  # With coverage

# Lint and format
ruff check src/ tests/
ruff format src/ tests/

# Run the API server
pa server --reload              # Via CLI
uvicorn src.api.main:app --reload  # Direct uvicorn

# CLI commands (pa is the main entry point)
pa tasks list                   # List tasks
pa tasks add "Task title" -p high -D tomorrow
pa agent start --foreground     # Start agent
pa agent status                 # Check agent status
pa summary                      # Daily summary
pa tasks voice                  # Create task from voice input

# Database migrations (using Alembic)
alembic revision --autogenerate -m "Description"  # Create migration
alembic upgrade head            # Apply migrations
alembic history                 # View migration history
alembic current                 # Check current status
```

## Architecture Overview

Personal Assistant is a Python 3.11+ AI-powered task management system with layered architecture:

```
API Layer (FastAPI)      → src/api/routes/*.py, src/api/main.py
CLI Layer (Click)        → src/cli.py (entry point: pa command)
Service Layer            → src/services/*.py (business logic)
Agent Layer              → src/agent/core.py (autonomous agent with APScheduler)
Integration Layer        → src/integrations/*.py (Gmail, Slack, etc.)
Data Layer (SQLAlchemy)  → src/models/*.py (SQLite database)
```

### Key Entry Points

- **`src/api/main.py`** - FastAPI application with routers mounted
- **`src/cli.py`** - Click CLI with command groups (entry point: `pa` command)
- **`src/agent/core.py`** - `AutonomousAgent` class that runs scheduled polling cycles
- **`src/models/database.py`** - Database engine and session management
- **`src/utils/config.py`** - Configuration system (Pydantic + YAML)

### Configuration

- YAML-based via `config.yaml` (see `config.example.yaml` for template)
- Pydantic validation in `src/utils/config.py`
- Environment variables supported with `PA_*` prefix
- Config file location: `~/.personal-assistant/config.yaml` or `./config.yaml`

## Core Architecture Patterns

### Layered Architecture with Clear Separation

The application follows strict layer separation:

1. **API Layer** (`src/api/`): FastAPI routes handle HTTP requests/responses, delegating to services
2. **Service Layer** (`src/services/`): All business logic lives here. Services never import from `src/api/`
3. **Integration Layer** (`src/integrations/`): External API integrations (Gmail, Slack) using `BaseIntegration` interface
4. **Data Layer** (`src/models/`): SQLAlchemy ORM models with mapped columns and relationships

**Critical Rule**: Business logic must be in service layer, not in API routes. Routes are thin wrappers that call services.

### Dependency Injection

- FastAPI's dependency injection used for database sessions (`get_db_session`) and config (`get_config`)
- Test fixtures override dependencies for isolated testing
- Always close sessions properly (dependencies handle this automatically in FastAPI)

### Testing Strategy

- Tests use **in-memory SQLite** (no external dependencies)
- Fixtures in `tests/conftest.py` provide `client`, `test_db_session`, `test_config`
- API tests use `FastAPI TestClient` with dependency injection overrides
- Always reset global state (`reset_config()`, `reset_engine()`) in test fixtures
- Unit tests in `tests/unit/`, integration tests in `tests/integration/`
- Target: comprehensive coverage of all API endpoints and service functions

## Multi-Account Architecture

### Overview

The application supports multiple Google accounts (Gmail, Calendar, Drive) simultaneously. This enables users to monitor both personal and work accounts with separate configurations.

**Key Design Patterns:**
- **Composite Keys**: IntegrationManager uses `(IntegrationType, account_id)` tuples as dictionary keys
- **Per-Account Config**: Each account has its own OAuth tokens, polling intervals, and Gmail filters
- **Account Tagging**: Tasks include `account_id` field to track which account sourced them
- **Backwards Compatible**: Legacy single-account configs automatically migrate on load

**File References:**
- Config Models: `src/utils/config.py:63-110` (GoogleAccountConfig, GoogleConfig)
- Integration Manager: `src/integrations/manager.py:19-220` (composite key architecture)
- Task Model: `src/models/task.py:77-79` (account_id field)
- Gmail Integration: `src/integrations/gmail_integration.py:35-95` (account-aware init)

**Adding a New Account:**
1. Add account config to `config.yaml` under `google.accounts[]`
2. Run `pa accounts authenticate <account_id>`
3. Restart agent to begin polling new account

## Key Components

### Autonomous Agent System

The agent (`src/agent/core.py`) is the orchestrator:

- Uses APScheduler for scheduled polling (default: every 5 minutes)
- Polls integrations via `IntegrationManager`
- Extracts tasks from emails/Slack using `LLMService`
- Creates tasks automatically based on **autonomy level**:
  - `SUGGEST`: Only logs suggestions, never auto-creates
  - `AUTO_LOW`: Auto-creates tasks with confidence ≥ 0.8
  - `AUTO`: Auto-creates all tasks extracted by LLM
  - `FULL`: Auto-creates tasks and applies LLM priority suggestions
- Logs all activity to `AgentLogService` for transparency
- Generates productivity recommendations via `RecommendationService`

**PID File Management**: Agent uses `~/.personal-assistant/agent.pid` for cross-process tracking. `PIDManager` class handles PID file operations and stale PID detection.

### LLM Integration

`LLMService` (`src/services/llm_service.py`) uses litellm for provider-agnostic LLM access:

- Task extraction from text (emails, Slack messages, voice transcriptions)
- Priority suggestions for existing tasks
- Productivity recommendations
- Calendar optimization suggestions (future)
- Initiative association suggestions for new tasks

**Configuration**: Supports OpenAI, Anthropic, and local models via litellm. Set `llm.api_base_url` and `llm.model` in config.yaml.

### Task Priority Scoring

Priority score (0-100) computed from five factors:

1. **Base Priority Level (0-40 pts)**: Critical=40, High=30, Medium=20, Low=10
2. **Due Date Urgency (0-25 pts)**: Overdue=25, Due in 4hrs=23, Today=20, 1-2 days=15, This week=10
3. **Task Age (0-15 pts)**: Older uncompleted tasks get a boost (14+ days=15pts)
4. **Source Importance (0-10 pts)**: Meeting notes=9, Email=8, Slack=7, Manual=5, Agent=4, Voice=6
5. **Special Tags (0-10 pts)**: Tags like "urgent", "blocker", "asap" add 10pts; "important" adds 5pts

Recalculate all scores: `pa tasks recalculate-priorities` or `POST /api/tasks/recalculate-priorities`

### Integrations

All integrations inherit from `BaseIntegration` (`src/integrations/base.py`):

- **Gmail** (`gmail_integration.py`): Polls inbox, extracts actionable items from emails
- **Slack** (`slack_integration.py`): Monitors channels for actionable messages
- Future: Google Calendar, Google Drive

**OAuth 2.0**: Google services use OAuth via `GoogleOAuthManager`. Slack uses token-based auth. Credentials stored in config.yaml (gitignored).

**IntegrationManager** (`src/integrations/manager.py`): Coordinates all integrations, polls them, converts `ActionableItem` objects to tasks.

### Voice Input System

Voice input (`src/services/voice_service.py`) enables task creation by speaking:

- Records audio via `sounddevice` (cross-platform)
- Transcribes using OpenAI Whisper API
- Extracts task from transcription using `LLMService.extract_tasks_from_text()`
- Falls back to using transcription as task title if no task detected
- CLI: `pa tasks voice [-d DURATION] [--transcribe-only]`
- API: `POST /api/tasks/voice` (multipart file upload)

### Initiatives System

Initiatives (`src/models/initiative.py`, `src/services/initiative_service.py`) are high-level goals that group related tasks:

- Tasks can be associated with initiatives via `task.initiative_id`
- List initiatives: `pa initiatives list` (alias: `pa itvs list`)
- Add tasks to initiative: `pa initiatives add-tasks INITIATIVE_ID TASK_ID...`
- When parsing natural language tasks, LLM suggests initiative associations if active initiatives exist

### Notification System

`NotificationService` (`src/services/notification_service.py`):

- **macOS**: Native notifications via `osascript` (Notification Center)
- **Other platforms**: Terminal fallback using rich panels
- Notification types: info, warning, success, error (with optional sound)
- Task-specific notifications: due soon, overdue, task created
- Configuration: `notifications.enabled`, `notifications.on_overdue`, etc.

## Database Schema

**Key Tables**:

- `tasks`: Title, description, status, priority, priority_score, due_date, tags (CSV), source, initiative_id
- `initiatives`: Title, description, priority, status, target_date
- `agent_logs`: Agent activity log with action type, details, token usage
- `pending_suggestions`: Tasks suggested by agent but not auto-created (for SUGGEST autonomy level)
- `notifications`: Notification history

**Migrations**: Managed by Alembic. After model changes, run `alembic revision --autogenerate -m "Description"` and `alembic upgrade head`.

## Development Guidelines

### Project Documentation

- **README.md**: Keep up to date with installation, usage, features, and project status
- **docs/ARCHITECTURE.md**: Architecture Decision Log (ADL) - document all major architectural decisions
- **SPEC.MD**: Original specifications for the application
- **MIGRATIONS.md**: Alembic migration workflow and common tasks

### Git Workflow

- Commit early and often with clear commit messages
- Implement new phases/features in feature branches
- Branch naming: `feat/feature-name`, `fix/bug-name`
- Keep commits focused and atomic

### API-First Development

- Document APIs for external consumption (FastAPI auto-generates OpenAPI docs at `/docs`)
- All business logic should be accessible via both API and CLI
- API endpoints should have corresponding CLI commands where appropriate

### Testing Requirements

**Comprehensive test coverage is required**:

- All API endpoints must have integration tests
- All service functions must have unit tests
- Tests must be runnable without external dependencies (use in-memory databases)
- Mock external API calls (LLM, Gmail, Slack) in tests
- Test fixtures reset global state to ensure isolation

**Test Execution**:
- Run `pytest` before committing
- Check coverage with `pytest --cov=src --cov-report=html`
- Aim for >80% coverage of service layer

### Code Quality

- Run `ruff check` and `ruff format` before committing
- Follow Python 3.11+ type hints (use `from __future__ import annotations` if needed)
- Use Pydantic for data validation
- Use SQLAlchemy 2.0 style (mapped columns, type hints)

## Common Development Patterns

### Adding a New Task Source

1. Add enum value to `TaskSource` in `src/models/task.py`
2. Update priority scoring in `TaskService.calculate_priority_score()` if needed
3. Add integration class inheriting from `BaseIntegration` in `src/integrations/`
4. Register integration in `IntegrationManager`

### Adding a New Agent Action

1. Add action type to `AgentAction` enum in `src/agent/core.py`
2. Implement action handler in `AutonomousAgent` class
3. Log activity using `AgentLogService.log_activity()`
4. Add unit and integration tests

### Adding a New API Endpoint

1. Create endpoint in appropriate router file (`src/api/routes/`)
2. Use Pydantic schemas from `src/api/schemas.py` for request/response validation
3. Delegate business logic to service layer
4. Add integration test in `tests/integration/`

### Adding a New CLI Command

1. Add command group or command to `src/cli.py`
2. Use Click decorators and Rich for styled output
3. Reuse service layer functions (don't duplicate logic)
4. Add unit test in `tests/unit/test_cli.py`

## macOS-Specific Features

### Menu Bar App

The project includes a macOS menu bar app (`src/macos/menu_app.py`):

- Native macOS integration using PyObjC
- Menu bar icon with dropdown menu
- Quick access to agent status, tasks, and controls
- Launcher script: `src/macos/launcher.py`

**Note**: Menu bar app is macOS-only and requires `pip install -e ".[macos]"` for PyObjC dependencies.

## LLM and Token Management

- LLM calls are logged to `agent_logs` table with token usage
- Model and provider configurable via config.yaml
- Use lower temperature (0.3) for extraction tasks, higher (0.7) for recommendations
- Always include token tracking in LLM service methods
- Cost monitoring: Query `agent_logs` table for token usage statistics

## Common Issues and Solutions

### Agent Not Starting

- Check if agent is already running: `pa agent status`
- Check PID file: `cat ~/.personal-assistant/agent.pid`
- Look for stale PID file (process no longer exists)
- Check logs in database: `SELECT * FROM agent_logs ORDER BY timestamp DESC LIMIT 10`

### Tests Failing Due to Global State

- Ensure `reset_config()` and `reset_engine()` are called in test fixtures
- Use `test_db_session` fixture instead of creating sessions directly
- Override FastAPI dependencies in `client` fixture

### Database Migration Issues

- Check current migration: `alembic current`
- View pending migrations: `alembic history`
- If autogenerate doesn't detect changes, ensure model is imported in `alembic/env.py`
- For manual migrations, use `alembic revision -m "Description"`

### LLM API Errors

- Verify API key in config.yaml: `llm.api_key`
- Check API base URL: `llm.api_base_url` (defaults to OpenAI)
- Review error in agent logs: `SELECT * FROM agent_logs WHERE action = 'LLM_REQUEST'`
- Test with: `pa summary` (triggers LLM for recommendations)
