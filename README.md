# Personal Assistant

A personal assistant agent that helps track tasks, monitors multiple data sources (email, calendar, Slack, meeting notes), and provides productivity recommendations.

## Features

- **Task Management**: Create, update, and prioritize tasks with automatic scoring
- **Voice Input**: Create tasks by speaking - uses Whisper for transcription and LLM for task extraction
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

### Command-Line Interface (CLI)

The Personal Assistant provides a full-featured CLI for managing tasks and controlling the agent.

#### Quick Start
```bash
# Initialize configuration
pa config init

# Add a task
pa tasks add "Review PR #123" -p high -D tomorrow

# List tasks
pa tasks list

# View daily summary
pa summary

# Start the agent (foreground)
pa agent start --foreground
```

#### Agent Commands
```bash
pa agent start [--autonomy LEVEL] [--foreground]  # Start the agent
pa agent stop                                       # Stop the agent
pa agent status                                     # Show agent status
pa agent poll                                       # Trigger immediate poll
```

Autonomy levels: `suggest`, `auto_low`, `auto`, `full`

**Agent Process Management:**
- The agent uses a PID file (`~/.personal-assistant/agent.pid`) to track running instances
- `pa agent status` accurately shows if the agent is running across different terminal sessions
- `pa agent start` prevents starting duplicate agents
- `pa agent stop` gracefully stops the agent process using the PID file

#### Task Commands
```bash
pa tasks list [--status STATUS] [--priority PRIORITY] [--all] [--limit N]
pa tasks add TITLE [-d DESCRIPTION] [-p PRIORITY] [-D DUE] [-t TAG]...
pa tasks voice [-d DURATION] [--transcribe-only]  # Create task from voice
pa tasks complete TASK_ID
pa tasks delete TASK_ID [--yes]
pa tasks show TASK_ID
pa tasks priority [--limit N]   # Show top priority tasks
pa tasks stats                  # Show task statistics
```

**Due date formats**: `YYYY-MM-DD`, `today`, `tomorrow`, `+3d` (3 days), `+2w` (2 weeks)

#### Voice Input
```bash
# Record and create a task from voice (default 10 seconds)
pa tasks voice

# Record for 15 seconds
pa tasks voice -d 15

# Just transcribe, don't create a task
pa tasks voice --transcribe-only
```

Voice input requires a microphone and an OpenAI API key (for Whisper transcription).

#### Other Commands
```bash
pa summary                       # Daily summary with recommendations
pa config show                   # Show current configuration
pa config path                   # Show config file path
pa config init [--force]         # Create default config file
pa server [--host HOST] [--port PORT] [--reload]  # Start API server
pa notify MESSAGE [--title TITLE]  # Send test notification
```

### Running the API Server

Start the FastAPI server:
```bash
pa server --reload
# or
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

#### Voice
- `POST /api/tasks/voice` - Create task from audio file upload
- `POST /api/tasks/voice/transcribe` - Transcribe audio without creating a task
- `GET /api/tasks/voice/status` - Check voice feature status

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

**Current Phase**: Phase 8 - Voice Input for Task Creation ✅

- [x] Project structure and dependencies
- [x] Configuration system
- [x] Database models (Task, Notification, AgentLog)
- [x] FastAPI application with task CRUD endpoints
- [x] Enhanced priority scoring (considers due date, age, source, tags)
- [x] Advanced filtering and search
- [x] Batch operations (bulk status update, bulk delete)
- [x] Task statistics endpoint
- [x] Integration framework with OAuth 2.0 support
- [x] Gmail integration (extracts actionable items from emails)
- [x] Slack integration (monitors channels for actionable messages)
- [x] Integration manager to coordinate polling
- [x] Autonomous agent with LLM integration
- [x] Four configurable autonomy levels
- [x] Productivity recommendations with caching
- [x] CLI with Click and rich formatting
- [x] macOS native notifications (osascript)
- [x] PID file management for agent process tracking
- [x] Cross-process agent status detection
- [x] **Voice input for task creation (Whisper + LLM)**
- [x] **Voice API endpoints and CLI command**

**Next Steps**:
- Phase 7: Meeting scheduler and calendar optimization

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
