---
status: pending
priority: p1
issue_id: 003
tags:
  - performance
  - architecture
  - granola
  - code-review
  - database
dependencies: []
---

# Database Session Lifecycle Management Issue

## Problem Statement

The Granola integration is initialized with a database session from `get_db()` generator that is **never closed**. The session lives for the entire lifetime of the agent process (potentially days/weeks), causing connection pool exhaustion, stale connections, and memory leaks.

**Why This Matters:**
- **Memory Leaks**: Unclosed sessions accumulate in memory
- **Connection Pool Exhaustion**: Long-lived sessions prevent connection reuse
- **Stale Data**: Session cache not refreshed, queries return outdated data
- **Production Stability**: Agent processes run 24/7, compounding the issue

## Findings

**Location:** `/Users/miked/workspace/personal-assistant/src/integrations/manager.py:138-146`

**Current Code:**
```python
# Get database session for duplicate tracking
db_session = next(get_db())  # ❌ Generator's finally block NEVER executes

integration = GranolaIntegration(
    config=workspace_config,
    account_id=workspace_id,
    db_session=db_session,  # Session stored indefinitely
)
```

**Session Lifecycle in database.py:**
```python
def get_db() -> Generator[Session, None, None]:
    """Get a database session for dependency injection."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()  # ⚠️ NEVER CALLED when using next()
```

**From Performance Review:**
- Session created once at `IntegrationManager` initialization
- Lives for entire agent process lifetime (days/weeks)
- No close() or commit() lifecycle management
- Session can become stale for read queries
- Connection pool never released

**From Data Integrity Review:**
- Session corruption risk on transaction failures
- No rollback mechanism for long-lived sessions
- Subsequent operations can fail unexpectedly

## Proposed Solutions

### Solution 1: Remove Session from Constructor (Recommended)
**Move to per-operation session pattern matching project conventions:**

```python
# In granola_integration.py
class GranolaIntegration(BaseIntegration):
    def __init__(self, config: dict[str, Any], account_id: str):
        super().__init__(config, account_id)
        self.workspace_id = config.get("workspace_id", "default")
        self.lookback_days = config.get("lookback_days", 7)
        # No db_session stored

    def _filter_new_notes(self, notes: list[dict]) -> list[dict]:
        """Filter out notes that have already been processed."""
        from src.models.database import get_db_session

        with get_db_session() as db:
            note_ids = [note["id"] for note in notes]
            processed = set(
                row[0]
                for row in db.query(ProcessedGranolaNote.note_id)
                .filter(ProcessedGranolaNote.note_id.in_(note_ids))
                .filter(ProcessedGranolaNote.account_id == self.account_id)
                .all()
            )

        return [note for note in notes if note["id"] not in processed]

    def mark_note_processed(self, note_id: str, note_title: str, ...):
        """Mark a note as processed in the database."""
        from src.models.database import get_db_session

        with get_db_session() as db:
            processed_note = ProcessedGranolaNote(...)
            db.add(processed_note)
            db.commit()
```

**In manager.py:**
```python
# Remove db_session parameter entirely
integration = GranolaIntegration(
    config=workspace_config,
    account_id=workspace_id,
)
```

**Pros:**
- Follows project conventions (context manager pattern)
- Automatic session cleanup
- Fresh session per operation
- Matches Gmail/Slack pattern (no db dependency)
- Proper transaction boundaries

**Cons:**
- More database connections per poll cycle (negligible overhead)
- Slightly more code

**Effort:** Medium (1-2 hours including tests)
**Risk:** Low (well-established pattern)

### Solution 2: Scoped Session with Refresh
**Keep session in constructor but refresh periodically:**

```python
# In IntegrationManager._initialize_integrations()
for workspace in workspaces:
    db_session = next(get_db())
    integration = GranolaIntegration(..., db_session=db_session)
    integration._session_created_at = datetime.now()

# In IntegrationManager.poll_all()
for key, integration in self.integrations.items():
    if key[0] == IntegrationType.GRANOLA:
        # Refresh session if older than 1 hour
        if datetime.now() - integration._session_created_at > timedelta(hours=1):
            integration.db.close()
            integration.db = next(get_db())
            integration._session_created_at = datetime.now()
```

**Pros:**
- Minimal code changes
- Addresses staleness

**Cons:**
- Still doesn't fix unclosed session
- Adds complexity to manager
- Doesn't follow project patterns

**Effort:** Medium (1 hour)
**Risk:** Medium (hacky solution)

### Solution 3: Callback Pattern
**Pass database operations as callbacks:**

```python
# In GranolaIntegration.__init__
def __init__(
    self,
    config: dict[str, Any],
    account_id: str,
    check_processed: Callable[[list[str]], set[str]] | None = None,
    mark_processed: Callable[[str, str, datetime, int], None] | None = None,
):
    self._check_processed = check_processed
    self._mark_processed = mark_processed

# In manager
def _check_granola_processed(note_ids: list[str]) -> set[str]:
    with get_db_session() as db:
        # ... query logic
        return processed_set

integration = GranolaIntegration(
    config=workspace_config,
    account_id=workspace_id,
    check_processed=_check_granola_processed,
    mark_processed=_mark_granola_processed,
)
```

**Pros:**
- Complete separation of concerns
- No database dependency in integration
- Testable with simple mocks

**Cons:**
- Most complex solution
- Significant refactoring

**Effort:** Large (3-4 hours)
**Risk:** Medium (architectural change)

## Recommended Action

**Implement Solution 1** - Remove session from constructor and use per-operation context managers. This follows project conventions, ensures proper cleanup, and matches the pattern used elsewhere in the codebase.

## Technical Details

**Affected Files:**
- `src/integrations/granola_integration.py` (constructor, `_filter_new_notes`, `mark_note_processed`)
- `src/integrations/manager.py` (initialization, line 138-146)

**Database Impact:**
- **Current**: 1 connection per workspace, held indefinitely
- **After Fix**: 2-3 connections per poll cycle (filter + mark), properly closed
- **Connection Pool**: Default pool size usually 5-10, more than sufficient

**Performance Impact:**
- **Overhead**: ~5-10ms per poll to create/close session
- **Benefit**: Prevents memory leaks, ensures fresh data

## Acceptance Criteria

- [ ] Remove `db_session` parameter from `GranolaIntegration.__init__()`
- [ ] Update `_filter_new_notes()` to use context manager
- [ ] Update `mark_note_processed()` to use context manager
- [ ] Remove `db_session = next(get_db())` from manager
- [ ] Update unit tests to not pass db_session
- [ ] Add integration test verifying session cleanup
- [ ] Verify no unclosed session warnings in logs
- [ ] Run agent for 1 hour, check connection pool metrics

## Work Log

**2026-02-11:**
- Issue identified during performance review
- Confirmed session never closed
- Researched project patterns for session management
- Found `get_db_session()` context manager pattern
- Documented solution aligning with existing patterns

## Resources

- **Review Finding**: Performance Oracle Review - P1 Issue #3
- **PR**: https://github.com/mikedon/personal-assistant/pull/3
- **Project Pattern**: `src/models/database.py` lines 57-69 (`get_db_session` context manager)
- **SQLAlchemy Docs**: https://docs.sqlalchemy.org/en/20/orm/session_basics.html#closing
- **Similar Issue**: Gmail integration doesn't use database at all (good pattern)
