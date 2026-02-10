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

## Security Architecture

### Single-User Local Operation Model
**Decision**: Design the application for single-user local operation without multi-user authentication
**Date**: 2026-02-09
**Status**: Implemented

**Context**:
The Personal Assistant is designed to run locally on a user's personal machine, similar to desktop applications like text editors or note-taking apps. During PR #1 code review, questions arose about authentication and authorization for multi-account Google integration.

**Decision**:
- No user authentication or authorization implemented
- API endpoints do not validate account_id ownership
- CLI commands operate without authentication
- OAuth tokens stored locally with file-system permissions (0600) for access control
- Multi-account support allows one user to configure multiple Google accounts (personal, work)

**Rationale**:
1. **Use Case Alignment**: The tool is designed for personal productivity on a single user's machine
2. **Simplicity**: Avoids complexity of user management, sessions, password storage
3. **OS-Level Security**: Relies on OS file permissions and user accounts for access control
4. **Deployment Model**: Not intended for shared servers or multi-user environments
5. **Development Speed**: Allows faster iteration on core productivity features

**Security Implications**:
- ✅ **Acceptable for single-user desktops**: Standard model for desktop productivity tools
- ⚠️ **Not suitable for shared servers**: Anyone with system access can use the tool
- ⚠️ **No audit trail**: Cannot track which OS user performed actions
- ✅ **OAuth tokens protected**: File permissions (0600) prevent other OS users from reading tokens

**Future Considerations**:
If the tool evolves to support multi-user or hosted deployments, authentication and authorization must be added:
- User authentication (password, SSO, etc.)
- Account ownership mapping (user_id → account_id associations)
- API authentication (API keys, JWT tokens)
- Audit logging with user context

**Documentation**:
- README.md includes "Security Model" section explaining single-user design
- API documentation notes lack of authentication
- Security assumptions clearly documented

**Related Issues**:
- Code review P1 issues #2 and #3 noted authorization gaps - resolved by documenting single-user model

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

### CLI Interface
**Decision**: Use Click with rich for CLI implementation
**Implementation** (Phase 5):
- Full command hierarchy: agent, tasks, config, summary, server, notify
- Rich library for styled output (tables, panels, colored text)
- Agent commands control the autonomous agent lifecycle
- Task commands provide full CRUD operations with filtering
- Smart due date parsing: "today", "tomorrow", "+3d", "+2w", ISO format
- Priority emoji indicators for visual scanning

**Rationale**:
- Click provides robust command parsing and argument handling
- Rich enables professional terminal UI with colors and formatting
- Clear command hierarchy matches user mental model
- Smart date parsing reduces friction in task entry

### Agent Process Management (Phase 6)
**Decision**: Use PID file for tracking agent across processes
**Implementation**:
- PID file stored at `~/.personal-assistant/agent.pid`
- `PIDManager` class handles all PID file operations
- Automatic cleanup of stale PID files (process no longer running)
- Cross-platform process checking using `os.kill(pid, 0)`
- CLI commands check PID file to determine agent status
- Agent writes PID file on start, removes on clean shutdown

**Rationale**:
- Solves the problem of `pa agent status` not detecting agents in other processes
- Simple Unix pattern - no additional dependencies
- Cross-platform compatible (macOS, Linux, adaptable for Windows)
- Handles crashes gracefully (stale PID file detection)
- More appropriate for personal app than process managers (systemd/launchd)
- Validates process actually exists before reporting as running

**Alternative Considered**: Database flag with timestamp
- Rejected because it requires heartbeat updates and doesn't handle crashes well
- PID file is simpler and more reliable

**Rationale**:
- Click provides robust argument parsing and help generation
- Rich enables beautiful terminal output without complexity
- Subcommand groups organize related functionality
- Consistent with developer workflow expectations

### Notification Service
**Decision**: Platform-native notifications with fallback
**Implementation** (Phase 5):
- macOS: osascript for native Notification Center integration
- Non-macOS: Terminal-based fallback using rich panels
- Configurable notification types and triggers
- Sound support on macOS

**Configuration Options**:
- `enabled`: Master toggle for notifications
- `sound`: Enable/disable notification sound
- `on_overdue`: Notify when tasks become overdue
- `on_due_soon`: Notify when tasks are due within N hours
- `on_task_created`: Notify when agent creates new tasks

**Rationale**:
- Native notifications are less intrusive than terminal popups
- Configuration allows users to control notification volume
- Fallback ensures functionality across platforms

## Autonomous Agent Architecture

### Agent Core Design
**Decision**: Implement `AutonomousAgent` class as central coordinator
**Implementation** (Phase 4):
- Agent runs on configurable schedule using APScheduler
- Polls all enabled integrations for actionable items
- Uses LLM to extract tasks from text content
- Creates tasks automatically based on autonomy level
- Generates productivity recommendations
- Writes markdown summary documents

**Architecture**:
```
┌──────────────────────────────────────────────────────────────┐
│                    AutonomousAgent                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  Scheduler   │  │ Integration  │  │   LLM Service    │   │
│  │ (APScheduler)│  │   Manager    │  │   (litellm)      │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
│          │                 │                   │             │
│          ▼                 ▼                   ▼             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                    Poll Cycle                            ││
│  │  1. Poll integrations for ActionableItems                ││
│  │  2. Extract tasks using LLM                              ││
│  │  3. Create/suggest tasks based on autonomy level         ││
│  │  4. Log activity to database                             ││
│  └─────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

**Rationale**:
- Single point of coordination for agent behavior
- Scheduled operations don't block API
- Clear separation between polling, processing, and action
- State tracking for session statistics

### Autonomy Levels
**Decision**: Implement four configurable autonomy levels
**Levels**:
1. **SUGGEST** (default): Only suggest tasks, never auto-create
2. **AUTO_LOW**: Auto-create tasks with confidence ≥ 0.8
3. **AUTO**: Auto-create all tasks extracted by LLM
4. **FULL**: Auto-create tasks and apply LLM priority suggestions

**Rationale**:
- Users control how much automation they want
- Conservative default (suggest only)
- Gradual trust-building with the agent
- Enterprise users may want more control

### LLM Service Design
**Decision**: Dedicated `LLMService` class using litellm
**Capabilities**:
- Task extraction from text (emails, Slack messages)
- Priority suggestions for existing tasks
- Productivity recommendations based on task state
- Calendar optimization suggestions

**Design Principles**:
- Lower temperature (0.3) for extraction tasks
- JSON output format with schema guidance
- Markdown code block parsing for responses
- Graceful degradation on errors
- Token usage tracking for cost monitoring

**Rationale**:
- litellm provides provider-agnostic interface
- Can switch between OpenAI, Anthropic, local models
- Structured output reduces parsing errors
- Cost visibility for budget management

### Agent Logging
**Decision**: Comprehensive logging to database
**Implementation**:
- `AgentLogService` for all agent activities
- Tracks: polls, task creations, LLM requests, errors
- Token usage and model information stored
- Activity summaries for monitoring
- Automatic cleanup of old logs

**Detailed Activity Logging** (added for transparency and debugging):
- **File Access Logging**: All file reads/writes during poll cycles are logged with path, bytes, and purpose
- **HTTP Request Logging**: All HTTP calls (LLM API, Gmail API, Slack API) are tracked with method, URL (sanitized), status code, duration, and request type
- **Decision Logging**: Agent decisions (e.g., auto_create_task) are logged with reasoning, outcome, and context
- **URL Sanitization**: Sensitive query parameters (api_key, token, secret) are automatically redacted in logs

**Log Action Types**:
- `POLL_EMAIL`, `POLL_SLACK`, `POLL_CALENDAR`, `POLL_DRIVE`: Integration polling
- `CREATE_TASK`, `UPDATE_TASK`: Task management
- `LLM_REQUEST`: LLM API calls with token tracking
- `FILE_READ`, `FILE_WRITE`: File system operations
- `HTTP_REQUEST`: External HTTP calls
- `DECISION`: Agent decision points

**Rationale**:
- Debug agent behavior over time
- Track LLM costs and usage patterns
- Identify integration issues
- Build user trust through transparency
- Complete audit trail of all agent activity during polls

### Recommendation Service
**Decision**: High-level service for productivity recommendations
**Features**:
- Daily summary with statistics
- Quick wins identification (heuristic-based)
- Overdue action plans
- Focus and scheduling recommendations
- Caching to reduce LLM calls

**Rationale**:
- Abstracts LLM complexity from API layer
- Caching reduces costs and latency
- Multiple recommendation types for different needs
- Non-LLM features work without API key

### Document Output
**Decision**: Generate markdown summary documents
**Implementation**:
- Path configurable via `output_document_path`
- Generated during recommendation cycles
- Contains: stats, top tasks, recommendations, agent status
- Emoji indicators for priority levels

**Rationale**:
- Human-readable daily digest
- Works with note-taking apps (Obsidian, etc.)
- No UI needed for basic functionality
- Version-controllable if desired

## Integration Layer Design

### Base Integration Interface
**Decision**: Create abstract base class for all integrations
**Implementation** (Phase 3):
- `BaseIntegration` abstract class with `authenticate()` and `poll()` methods
- `ActionableItem` dataclass for items extracted from integrations
- Integration-specific implementations (Gmail, Slack, Calendar, Drive)

**Rationale**:
- Consistent interface across all integrations
- Easy to add new integrations
- Testable with mock implementations
- Supports both polling and webhook patterns

### Integration Manager
**Decision**: Centralized manager to coordinate all integrations
**Rationale**:
- Single point to poll all integrations
- Automatic conversion of ActionableItems to Tasks
- Connection testing and health checks
- Can be extended with scheduling (APScheduler in Phase 4)

### OAuth 2.0 Handling
**Decision**: Dedicated OAuth managers for Google and Slack
**Rationale**:
- Google services (Gmail, Calendar, Drive) share OAuth flow
- Automatic token refresh
- Secure credential storage
- User controls permissions through OAuth consent

### Gmail Query Configuration
**Decision**: Configurable email filtering via `google.gmail` config section
**Implementation**:
- `inbox_type`: Filter by inbox type (`all`, `unread`, `not_spam`, `important`)
- `lookback_hours`/`lookback_days`: Time period for email queries (hours takes precedence)
- `include_senders`/`exclude_senders`: Sender whitelist/blacklist (partial match)
- `include_subjects`/`exclude_subjects`: Subject pattern whitelist/blacklist
- `priority_senders`: Senders whose emails are marked high priority

**Query Building**:
- Inbox type maps to Gmail operators: `is:unread`, `-in:spam`, `is:important`
- Small sender lists (≤5) are added to Gmail query with `from:` operator
- Larger lists rely on post-fetch filtering for performance

**Filter Behavior**:
- Exclude filters take precedence over include filters
- All pattern matching is case-insensitive
- Partial string matching (e.g., `@domain.com` matches any email from that domain)
- Backwards compatible: root-level config still works, nested `gmail` config takes precedence

**Rationale**:
- Users need control over which emails generate tasks
- Reduces noise from automated emails, newsletters, etc.
- Gmail API query optimization reduces API calls
- Flexible filtering covers diverse use cases

## Voice Input System

### Voice Service Design
**Decision**: Dedicated `VoiceService` for voice-to-task conversion
**Implementation** (Phase 8):
- Audio recording via `sounddevice` library (cross-platform)
- Transcription via OpenAI Whisper API
- Task extraction via existing `LLMService.extract_tasks_from_text()`
- Fallback: if no task extracted, uses transcription as task title

**Architecture**:
```
Microphone → sounddevice → WAV bytes → Whisper API → Text → LLM → Task
```

**Rationale**:
- Whisper provides high-accuracy transcription
- Reuses existing LLM infrastructure for task extraction
- Cross-platform audio recording (macOS, Linux, Windows)
- Graceful degradation when no task is detected

### Voice Configuration
**Settings** (`voice` section in config.yaml):
- `enabled`: Enable/disable voice features
- `recording_duration_seconds`: Default recording length (1-60 seconds)
- `sample_rate`: Audio sample rate (16000 recommended for Whisper)
- `whisper_model`: Whisper model variant (default: "whisper-1")

### Voice API Endpoints
- `POST /api/tasks/voice` - Upload audio, creates task
- `POST /api/tasks/voice/transcribe` - Upload audio, returns transcription only
- `GET /api/tasks/voice/status` - Check voice capabilities

### CLI Voice Command
- `pa tasks voice` - Record and create task from voice
- Options: `--duration`, `--transcribe-only`
- Interactive UI with progress indicator during recording

## Changelog

### 2026-01-31 - Gmail Configuration Enhancements
- Added `GmailQueryConfig` Pydantic model for Gmail-specific settings
- Implemented configurable inbox type filtering (`all`, `unread`, `not_spam`, `important`)
- Added `lookback_hours` option (takes precedence over `lookback_days`)
- Added sender include/exclude filtering with partial match support
- Added subject include/exclude filtering for topic-based filtering
- Dynamic Gmail query building with sender optimization
- Backwards compatible with existing root-level config
- Added 16 new unit tests for query building and filtering

### 2026-01-31 - Phase 8 Complete
- Added voice input feature for task creation
- Created `VoiceService` with audio recording, Whisper transcription, and task extraction
- Added voice API endpoints (`/api/tasks/voice`, `/api/tasks/voice/transcribe`)
- Added CLI command `pa tasks voice` with duration and transcribe-only options
- Added `VOICE` to TaskSource enum
- Added `VoiceConfig` to configuration system
- Extended test coverage with unit and integration tests for voice features

### 2026-01-28 - Phase 5 Complete
- Created full-featured CLI using Click with rich formatting
- Implemented agent control commands (start, stop, status, poll)
- Implemented task management commands (list, add, complete, delete, show, priority, stats)
- Added configuration commands (show, path, init)
- Added summary command for daily productivity overview
- Created notification service with macOS osascript integration
- Added terminal fallback for non-macOS platforms
- Notification types: info, warning, success, error with sound support
- Task-specific notifications: due soon, overdue, task created
- Extended test coverage to 194 tests (36 new CLI tests)

### 2026-01-28 - Phase 4 Complete
- Implemented `AutonomousAgent` core with APScheduler integration
- Created `LLMService` with litellm for task extraction and recommendations
- Added four configurable autonomy levels (suggest, auto_low, auto, full)
- Built `AgentLogService` for activity tracking and LLM usage monitoring
- Created `RecommendationService` with caching and multiple recommendation types
- Added agent API endpoints: status, start/stop, poll, recommendations, logs
- Implemented markdown summary document generation
- Extended test coverage with unit tests for LLM and agent services
- Added integration tests for agent API endpoints

### 2026-01-27 - Phase 3 Complete
- Created integration framework with base classes and interfaces
- Implemented OAuth 2.0 utilities for Google and Slack
- Built Gmail integration with email parsing and actionable item extraction
- Built Slack integration with channel monitoring
- Added IntegrationManager to coordinate all integrations
- Automatic conversion of ActionableItems to Tasks
- Extended test coverage to 68 tests

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


## Multi-Account Google Integration Architecture

### Decision: Support Multiple Google Accounts Simultaneously
**Date**: 2026-02-09  
**Status**: Implemented

### Context
Users often have multiple Google accounts (personal, work, side projects) and need to monitor all of them for important tasks and information. The original architecture only supported a single Google account connection.

### Decision
Refactor the integration architecture to support multiple accounts per integration type using composite keys.

**Key Changes:**
1. **Configuration**: Changed GoogleConfig from single object to array of GoogleAccountConfig objects
2. **Integration Manager**: Changed from `dict[IntegrationType, BaseIntegration]` to `dict[tuple[IntegrationType, str], BaseIntegration]`
3. **Task Model**: Added `account_id` field to track which account sourced each task
4. **OAuth Tokens**: Each account uses separate token file (e.g., token.personal.json, token.work.json)
5. **Per-Account Settings**: Each account has its own polling interval, Gmail filters, and enable/disable toggle

### Consequences

**Positive:**
- Users can monitor multiple Gmail accounts without switching configs
- Per-account polling intervals allow prioritizing important accounts
- Per-account filters enable fine-grained control over what generates tasks
- Account tagging enables work/life task separation
- Backwards compatible via automatic config migration

**Negative:**
- More complex configuration structure
- Multiple OAuth flows required (one per account)
- Increased complexity in IntegrationManager
- More token files to manage

**Trade-offs:**
- Chose composite keys over nested data structures for simplicity and performance
- Prioritized explicit configuration over automatic account discovery
- Used account_id string instead of integer ID to make configs more readable

### Implementation Files
- `src/utils/config.py`: GoogleAccountConfig and migration logic
- `src/integrations/manager.py`: Composite key architecture
- `src/models/task.py`: account_id field
- `src/integrations/gmail_integration.py`: Account-aware initialization
- `src/cli.py`: Account management commands

### Future Considerations
- Extend multi-account pattern to Slack (multiple workspaces)
- Cross-account task deduplication
- Account-specific priority weighting
- Account activity dashboard

