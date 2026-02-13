---
status: pending
priority: p1
issue_id: 005
tags:
  - data-integrity
  - database
  - granola
  - code-review
dependencies: []
---

# Missing Transaction Rollback in mark_note_processed

## Problem Statement

The `mark_note_processed()` method uses manual commit without proper transaction handling (try/except/rollback). If the commit fails, the session is left in an inconsistent state, potentially corrupting subsequent operations and violating the project's transaction safety patterns.

**Why This Matters:**
- **Data Consistency**: Failed commits leave session in undefined state
- **Cascading Failures**: Subsequent operations on corrupted session fail unexpectedly
- **No Atomicity Guarantee**: Can't rollback partial changes
- **Project Standards**: Violates established transaction pattern

## Findings

**Location:** `/Users/miked/workspace/personal-assistant/src/integrations/granola_integration.py:289-311`

**Current Code:**
```python
def mark_note_processed(
    self,
    note_id: str,
    note_title: str,
    note_created_at: datetime,
    tasks_created: int,
) -> None:
    processed_note = ProcessedGranolaNote(
        note_id=note_id,
        workspace_id=self.workspace_id,
        account_id=self.account_id,
        note_title=note_title,
        note_created_at=note_created_at,
        tasks_created_count=tasks_created,
    )

    self.db.add(processed_note)
    self.db.commit()  # ⚠️ NO ROLLBACK ON FAILURE
```

**Project Standard Pattern (from database.py:57-69):**
```python
def get_db_session() -> Generator[Session, None, None]:
    """Get a database session with automatic cleanup."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
        # Commit happens in calling code
    except Exception:
        db.rollback()  # ✅ Automatic rollback on error
        raise
    finally:
        db.close()
```

**From Data Integrity Review:**
- No rollback on commit failure
- Violates project transaction pattern
- Session corruption risk
- No guarantee of atomicity

**Failure Scenarios:**
1. **Unique constraint violation** (duplicate note_id) → IntegrityError → session corrupted
2. **Database connection lost** → OperationalError → session unusable
3. **Disk full** → OperationalError → partial write
4. **Lock timeout** → OperationalError → operation incomplete

## Proposed Solutions

### Solution 1: Add Try/Except/Rollback (Recommended if keeping method)
**Follow project transaction pattern:**

```python
def mark_note_processed(
    self,
    note_id: str,
    note_title: str,
    note_created_at: datetime,
    tasks_created: int,
) -> None:
    """Mark a note as processed in the database."""
    try:
        processed_note = ProcessedGranolaNote(
            note_id=note_id,
            workspace_id=self.workspace_id,
            account_id=self.account_id,
            note_title=note_title,
            note_created_at=note_created_at,
            tasks_created_count=tasks_created,
        )

        self.db.add(processed_note)
        self.db.commit()

        logger.debug(
            f"Marked Granola note '{note_title}' as processed ({tasks_created} tasks created)"
        )

    except IntegrityError:
        # Duplicate insert (race condition)
        self.db.rollback()
        logger.debug(f"Note {note_id} already marked as processed")
        # Don't raise - this is expected in race conditions

    except Exception as e:
        # Unexpected database error
        self.db.rollback()
        logger.error(f"Failed to mark note {note_id} as processed: {e}")
        raise  # Re-raise for caller to handle
```

**Pros:**
- Follows project patterns
- Handles race conditions gracefully
- Proper error recovery

**Cons:**
- Still using stored session (see todo #003)

**Effort:** Small (15 minutes)
**Risk:** Low

### Solution 2: Use Context Manager (Best - combine with #003)
**Migrate to per-operation session pattern:**

```python
def mark_note_processed(
    self,
    note_id: str,
    note_title: str,
    note_created_at: datetime,
    tasks_created: int,
) -> None:
    """Mark a note as processed in the database."""
    from src.models.database import get_db_session
    from sqlalchemy.exc import IntegrityError

    with get_db_session() as db:
        try:
            processed_note = ProcessedGranolaNote(
                note_id=note_id,
                workspace_id=self.workspace_id,
                account_id=self.account_id,
                note_title=note_title,
                note_created_at=note_created_at,
                tasks_created_count=tasks_created,
            )

            db.add(processed_note)
            db.commit()

            logger.debug(f"Marked note '{note_title}' as processed")

        except IntegrityError:
            db.rollback()
            logger.debug(f"Note {note_id} already processed (duplicate insert)")

        except Exception:
            db.rollback()
            raise
```

**Pros:**
- Automatic session cleanup
- Follows project pattern perfectly
- Solves #003 (session lifecycle) simultaneously

**Cons:**
- Requires removing db from constructor (see #003)

**Effort:** Small (20 minutes)
**Risk:** Low

### Solution 3: Defer to Caller
**Remove database logic from integration entirely:**

```python
# In GranolaIntegration - just return metadata
async def poll(self) -> list[ActionableItem]:
    # ... existing logic ...
    for note in new_notes:
        item = self._extract_actionable_item(note)
        if item:
            # Add processing metadata
            item.metadata["mark_processed_callback"] = {
                "note_id": note["id"],
                "note_title": note["title"],
                "note_created_at": note["created_at"],
            }
            items.append(item)
    return items

# In agent core - handle marking there
for item in granola_items:
    # Create tasks...
    # Then mark processed with proper transaction handling
    with get_db_session() as db:
        try:
            # ... mark logic ...
            db.commit()
        except Exception:
            db.rollback()
            raise
```

**Pros:**
- Complete separation of concerns
- Integration doesn't need database

**Cons:**
- Significant refactoring
- More complex flow

**Effort:** Large (2-3 hours)
**Risk:** Medium

## Recommended Action

**Implement Solution 2** - Use context manager pattern. This solves both this issue and #003 simultaneously with minimal code changes and aligns perfectly with project standards.

**Note:** Solution 2 depends on completing #003 (removing db_session from constructor). Alternatively, implement Solution 1 as a quick fix if #003 is deferred.

## Technical Details

**Affected Files:**
- `src/integrations/granola_integration.py` (`mark_note_processed` method, lines 289-311)

**Error Types to Handle:**
```python
from sqlalchemy.exc import IntegrityError, OperationalError, DatabaseError

try:
    db.commit()
except IntegrityError:
    # Duplicate key, constraint violation
    # Expected in race conditions - log and continue
except OperationalError:
    # Connection lost, lock timeout, disk full
    # Rollback and raise for retry logic
except DatabaseError:
    # Generic database error
    # Rollback and raise
```

**Transaction State Machine:**
```
BEGIN → [operations] → COMMIT (success)
                    → ROLLBACK (on exception) → Session clean
```

## Acceptance Criteria

- [ ] Add try/except around commit in `mark_note_processed()`
- [ ] Rollback on all exceptions
- [ ] Handle IntegrityError gracefully (log, don't raise)
- [ ] Re-raise unexpected exceptions for caller handling
- [ ] Add unit test: commit succeeds
- [ ] Add unit test: IntegrityError triggers rollback
- [ ] Add unit test: OperationalError triggers rollback and re-raises
- [ ] Verify session remains usable after rollback

## Work Log

**2026-02-11:**
- Issue identified during data integrity review
- Confirmed violation of project transaction pattern
- Researched SQLAlchemy exception types
- Documented solution aligning with get_db_session() pattern

## Resources

- **Review Finding**: Data Integrity Guardian Review - P1 Issue
- **PR**: https://github.com/mikedon/personal-assistant/pull/3
- **Project Pattern**: `src/models/database.py` lines 57-69
- **SQLAlchemy Exceptions**: https://docs.sqlalchemy.org/en/20/core/exceptions.html
- **Related Todo**: #003 (Database Session Lifecycle)
