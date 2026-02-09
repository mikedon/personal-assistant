# AGENTS.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

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

# Run the server
pa server --reload              # Via CLI
uvicorn src.api.main:app --reload  # Direct uvicorn

# CLI commands (pa is the main entry point)
pa tasks list                   # List tasks
pa agent start --foreground     # Start agent
pa summary                      # Daily summary
```

## Architecture Overview

This is a Python 3.11+ personal assistant with layered architecture:

```
API Layer (FastAPI)      → src/api/routes/*.py, src/api/main.py
Service Layer            → src/services/*.py (business logic)
Integration Layer        → src/integrations/*.py (Gmail, Slack, etc.)
Data Layer (SQLAlchemy)  → src/models/*.py (SQLite)
```

**Key entry points:**
- `src/api/main.py` - FastAPI app with routers
- `src/cli.py` - Click CLI (entry point: `pa`)
- `src/agent/core.py` - Autonomous agent with APScheduler

**Configuration:** YAML-based via `config.yaml` (see `config.example.yaml`). Pydantic validation in `src/utils/config.py`.

## Testing Patterns

- Tests use **in-memory SQLite** (no external dependencies)
- Fixtures in `tests/conftest.py` provide `client`, `test_db_session`, `test_config`
- API tests use `FastAPI TestClient` with dependency injection overrides
- Always reset global state (`reset_config()`, `reset_engine()`) in test fixtures

## Development Guide

- The specifications for the application can be found in the SPEC.md file at the root of the project
- A README.md should always be up to date with the latest information about how to install and run the project
- A ARCHITECTURE.md architecture decision log should be kept up to date throughout development
- We should build everything API first. Document the API for external consumption
- Keep an architecture change log that summarizes all of the major architectural decisions that you make along the way
- Keep a README of how to deploy the application, the key features of the application.
- This should be a project tracked in Git. Commit early and often and document the changes made clearly. Implement phases of implementation plans in new branches, always.
- **Comprehensive test coverage is required.** All API endpoints must have integration tests. Business logic and service functions must have unit tests. Tests should be runnable without external dependencies (use in-memory databases for testing).
