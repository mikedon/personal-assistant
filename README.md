# Personal Assistant

A personal assistant agent that helps track tasks, monitors multiple data sources (email, calendar, Slack, meeting notes), and provides productivity recommendations.

## Features

- **Task Management**: Create, update, and prioritize tasks with automatic scoring
- **Multi-Source Monitoring**: Track important information from email, Slack, calendar, and Google Drive
- **AI-Powered Agent**: Uses LLM to extract tasks and generate productivity recommendations
- **API-First Design**: RESTful API for programmatic access
- **Local Operation**: Runs entirely on your machine with SQLite storage
- **Configurable**: YAML-based configuration for easy customization

## Installation

### Prerequisites

- Python 3.11 or higher
- pip or uv for package management

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd personal-assistant
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows
```

3. Install dependencies:
```bash
pip install -e .
```

For development (includes testing tools):
```bash
pip install -e ".[dev]"
```

### Configuration

1. Copy the example configuration:
```bash
cp config.example.yaml config.yaml
```

2. Edit `config.yaml` with your settings:
   - Add your LLM API key (OpenAI-compatible)
   - Configure Google OAuth credentials (for Gmail, Calendar, Drive)
   - Add Slack tokens (for Slack integration)
   - Adjust agent behavior settings

## Usage

### Running the API Server

Start the FastAPI server:
```bash
uvicorn src.api.main:app --reload
```

The API will be available at `http://localhost:8000`

- API Documentation: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/health`

### API Endpoints

#### Tasks
- `GET /api/tasks` - List all tasks (with filtering, search, pagination)
- `GET /api/tasks/priority` - Get top priority tasks
- `GET /api/tasks/overdue` - Get overdue tasks
- `GET /api/tasks/due-soon` - Get tasks due within N days
- `GET /api/tasks/stats` - Get task statistics
- `GET /api/tasks/{id}` - Get a specific task
- `POST /api/tasks` - Create a new task
- `PUT /api/tasks/{id}` - Update a task
- `DELETE /api/tasks/{id}` - Delete a task

#### Batch Operations
- `POST /api/tasks/bulk/status` - Update status for multiple tasks
- `POST /api/tasks/bulk/delete` - Delete multiple tasks
- `POST /api/tasks/recalculate-priorities` - Recalculate all priority scores

#### Status
- `GET /health` - Health check
- `GET /api/status` - Agent status

### Query Parameters for Task Listing

The `GET /api/tasks` endpoint supports:
- `status` - Filter by status (pending, in_progress, completed, etc.)
- `priority` - Filter by priority (critical, high, medium, low)
- `source` - Filter by source (manual, email, slack, etc.)
- `search` - Search in title and description
- `tags` - Filter by tags (matches any)
- `due_before` / `due_after` - Filter by due date range
- `include_completed` - Include/exclude completed tasks (default: true)
- `limit` / `offset` - Pagination

### Example: Creating a Task

```bash
curl -X POST "http://localhost:8000/api/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Review PR #123",
    "description": "Review and approve the authentication feature PR",
    "priority": "high",
    "tags": ["code-review", "urgent"]
  }'
```

## Development

### Running Tests

Run all tests:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=src --cov-report=html
```

Run specific test types:
```bash
pytest tests/unit/          # Unit tests only
pytest tests/integration/   # Integration tests only
```

### Code Quality

Format and lint code:
```bash
ruff check src/ tests/
ruff format src/ tests/
```

## Project Status

**Current Phase**: Phase 2 - Core Task Management ✅

- [x] Project structure and dependencies
- [x] Configuration system
- [x] Database models (Task, Notification, AgentLog)
- [x] FastAPI application with task CRUD endpoints
- [x] Enhanced priority scoring (considers due date, age, source, tags)
- [x] Advanced filtering and search
- [x] Batch operations (bulk status update, bulk delete)
- [x] Task statistics endpoint
- [x] Comprehensive test coverage (56 tests)

**Next Steps**:
- Phase 3: Integration layer (Gmail, Calendar, Slack, Google Drive)
- Phase 4: Autonomous agent with LLM integration
- Phase 5: User interface and notifications
- Phase 6: Meeting scheduler

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed architectural decisions and design rationale.

## Contributing

1. Create a feature branch
2. Make your changes with tests
3. Ensure all tests pass: `pytest`
4. Commit with clear messages: `git commit -m "feat: add feature X"`
5. Push and create a pull request

## License

[Add license information]
