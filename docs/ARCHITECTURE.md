# Architecture Decision Log

This document tracks major architectural decisions made during the development of the Personal Assistant application.

## Overview

The Personal Assistant is a locally-run AI agent designed to help users manage tasks, monitor multiple information sources, and improve productivity. It follows an API-first design approach with a focus on modularity, testability, and extensibility.

## Technology Stack

### Language: Python 3.11+
**Decision**: Use Python as the primary language
**Rationale**:
- Excellent ecosystem for AI/ML integrations (OpenAI, LiteLLM)
- Strong support for async operations (critical for agent polling)
- Rich libraries for API development (FastAPI)
- Easy integration with Google APIs and Slack SDK
- Familiar to most developers

### Web Framework: FastAPI
**Decision**: Use FastAPI for the REST API
**Rationale**:
- Built-in OpenAPI documentation (automatic `/docs` endpoint)
- Excellent performance with async support
- Type hints and Pydantic integration for validation
- Modern Python features (Python 3.11+ compatibility)
- Easy testing with TestClient
- API-first development aligns with project requirements

### Database: SQLite
**Decision**: Use SQLite for local data persistence
**Rationale**:
- Zero configuration - no separate database server needed
- Perfect for single-user local applications
- ACID compliance for data integrity
- Easy backup (single file)
- Sufficient performance for the expected data volume
- Simplifies testing (in-memory databases)

### ORM: SQLAlchemy 2.0
**Decision**: Use SQLAlchemy as the database ORM
**Rationale**:
- Industry standard ORM for Python
- Type-safe with Python 3.11+ type hints
- Excellent support for SQLite
- Migration support (via Alembic if needed later)
- Testability with in-memory databases

### Configuration: Pydantic Settings + YAML
**Decision**: Use Pydantic for config validation with YAML files
**Rationale**:
- Type-safe configuration with validation
- YAML is human-readable and easy to edit
- Environment variable support (12-factor app)
- Clear error messages for invalid config
- Integrates seamlessly with FastAPI

### LLM Integration: LiteLLM
**Decision**: Use LiteLLM for LLM routing
**Rationale**:
- OpenAI API-compatible interface
- Supports multiple providers (OpenAI, Anthropic, local models)
- Easy to switch between models without code changes
- Cost tracking and observability
- Retry logic and error handling built-in

## Architecture Patterns

### Layered Architecture
The application follows a clean layered architecture:

```
┌─────────────────────────┐
│   API Layer (FastAPI)   │  - HTTP endpoints, request/response
├─────────────────────────┤
│   Service Layer         │  - Business logic, orchestration
├─────────────────────────┤
│   Integration Layer     │  - External APIs (Gmail, Slack, etc.)
├─────────────────────────┤
│   Data Layer (ORM)      │  - Database models, queries
└─────────────────────────┘
```

**Rationale**:
- Clear separation of concerns
- Easy to test each layer independently
- Business logic isolated from API and data access
- Supports future UI additions (CLI, web interface)

### Dependency Injection
**Decision**: Use FastAPI's dependency injection for database sessions and config
**Rationale**:
- Makes testing easier (can override dependencies)
- Explicit dependencies in function signatures
- Automatic cleanup (session closing)
- Follows FastAPI best practices

### Repository Pattern (Implicit)
**Decision**: Encapsulate database queries in service functions
**Rationale**:
- Business logic doesn't depend on ORM details
- Easier to mock for testing
- Query logic can be reused across endpoints
- Supports future caching layer

## Data Model Decisions

### Task Priority Scoring
**Decision**: Use a computed `priority_score` (0-100) based on multiple factors
**Implementation** (Phase 2):
The priority score is calculated from five factors:
1. **Base Priority Level (0-40 pts)**: Critical=40, High=30, Medium=20, Low=10
2. **Due Date Urgency (0-25 pts)**: Overdue=25, Due in 4hrs=23, Today=20, 1-2 days=15, This week=10
3. **Task Age (0-15 pts)**: Older uncompleted tasks get a boost (14+ days=15pts)
4. **Source Importance (0-10 pts)**: Meeting notes=9, Email=8, Slack=7, Manual=5, Agent=4
5. **Special Tags (0-10 pts)**: Tags like "urgent", "blocker", "asap" add 10pts; "important" adds 5pts

**Rationale**:
- Allows fine-grained prioritization
- Automatically surfaces important tasks
- Considers context beyond just priority label
- LLM can suggest score adjustments in future phases

### Task Tags as CSV String
**Decision**: Store tags as comma-separated string rather than separate table
**Rationale**:
- Simpler schema for initial version
- Sufficient for expected tag volumes
- No need for complex joins in queries
- Helper methods (`get_tags_list`, `set_tags_list`) provide clean API
- Can migrate to separate table later if needed

### Enums for Status/Priority
**Decision**: Use Python Enums for task status, priority, and source
**Rationale**:
- Type safety at application level
- Clear allowed values in API docs
- Database-level constraints (via SQLAlchemy Enum)
- Auto-completion in IDEs
- Validation in Pydantic schemas

## Testing Strategy

### Test Isolation with In-Memory Database
**Decision**: Use SQLite in-memory database for tests
**Rationale**:
- Fast test execution
- No test data pollution
- True isolation between tests
- No need for cleanup/teardown
- Matches production database (SQLite)

### Separation of Unit and Integration Tests
**Decision**: Separate tests into `tests/unit/` and `tests/integration/`
**Rationale**:
- Run fast unit tests during development
- Run slower integration tests before commits
- Clear distinction between test types
- Follows project requirements for comprehensive coverage

### TestClient for API Tests
**Decision**: Use FastAPI's TestClient for integration tests
**Rationale**:
- Tests entire request/response cycle
- No need to run separate server
- Synchronous test interface (simpler)
- Catches serialization issues

## Security Decisions

### OAuth 2.0 for Google Services
**Decision**: Use OAuth 2.0 flow for Google API authentication
**Rationale**:
- Industry standard for API authentication
- User controls permissions
- Tokens can be revoked
- Google's recommended approach
- Official libraries handle token refresh

### Secrets in Configuration
**Decision**: Store API keys in config.yaml (gitignored)
**Rationale**:
- Simple for single-user local application
- config.yaml is in .gitignore
- Can override with environment variables (PA_*)
- Future: support secret managers (macOS Keychain)

## Future Considerations

### Agent Scheduling
**Planning**: Use APScheduler for periodic polling
**Rationale**: Lightweight, no external dependencies, supports cron-like schedules

### Document Output
**Planning**: Generate markdown files for daily summaries
**Rationale**: Human-readable, version-controllable, works with Obsidian

### Observability
**Planning**: Store agent logs in database
**Rationale**: Track agent decisions, debug issues, analyze patterns

### CLI Interface
**Planning**: Add CLI commands using Click or Typer
**Rationale**: Easy task management from terminal, fits developer workflow

## Changelog

### 2026-01-27 - Phase 2 Complete
- Added TaskService with enhanced priority scoring algorithm
- Implemented advanced task filtering (status, priority, source, tags, search, date ranges)
- Added batch operations (bulk status update, bulk delete, recalculate priorities)
- Added task statistics endpoint with metrics (by status, priority, source, overdue, due soon)
- Added specialized endpoints: `/overdue`, `/due-soon`, `/stats`
- Moved business logic from routes to service layer
- Extended test coverage to 56 tests

### 2026-01-27 - Phase 1 Complete
- Initialized project structure
- Set up configuration system with Pydantic + YAML
- Created database models (Task, Notification, AgentLog)
- Implemented FastAPI application with task CRUD endpoints
- Added comprehensive test coverage (unit + integration)
- Established development guidelines and tooling (pytest, ruff)
