---
status: pending
priority: p1
issue_id: 004
tags:
  - data-integrity
  - concurrency
  - granola
  - code-review
  - database
dependencies: []
---

# Race Condition in Duplicate Note Prevention

## Problem Statement

The duplicate check (`_filter_new_notes`) and processing flow have no transaction isolation, creating a race condition where multiple agents can process the same note simultaneously. This leads to duplicate tasks and database integrity errors when both try to mark the note as processed.

**Why This Matters:**
- **Duplicate Tasks**: Same meeting note processed twice = duplicate action items
- **User Experience**: Confusing to see identical tasks from same meeting
- **Data Consistency**: One agent succeeds, other fails with IntegrityError
- **Production Risk**: Likely with 15-minute polling if processing takes >1 minute

## Findings

**Location:** `/Users/miked/workspace/personal-assistant/src/integrations/granola_integration.py:169-189`

**Vulnerable Code Flow:**
```python
def _filter_new_notes(self, notes: list[dict]) -> list[dict]:
    # 1. Read processed notes
    processed = set(
        row[0]
        for row in self.db.query(ProcessedGranolaNote.note_id)
        .filter(...)
        .all()
    )
    # 2. Return unprocessed notes
    return [note for note in notes if note["id"] not in processed]

# Later...
def mark_note_processed(self, note_id: str, ...):
    # 3. Insert without checking again
    processed_note = ProcessedGranolaNote(...)
    self.db.add(processed_note)
    self.db.commit()  # ❌ Can fail with IntegrityError
```

**Race Condition Timeline:**
```
10:00:00 - Agent A polls, finds note ABC123
10:00:01 - Agent B polls, finds note ABC123 (not yet marked)
10:00:05 - Agent A creates tasks for ABC123
10:00:06 - Agent B creates tasks for ABC123 (duplicates!)
10:00:10 - Agent A marks ABC123 processed (success)
10:00:11 - Agent B marks ABC123 processed (IntegrityError - violates unique constraint)
```

**From Data Integrity Review:**
- No transaction isolation between read check and write
- `mark_note_processed()` doesn't check for existing records
- Database unique constraint `uix_note_account` will fail on duplicate
- Exception caught but data inconsistency remains

**Production Scenarios:**
- Multiple agent processes running (horizontal scaling)
- Polling interval shorter than LLM processing time
- High note volume causing processing delays
- System slowdown during peak hours

## Proposed Solutions

### Solution 1: Check-Then-Insert Pattern (Recommended)
**Add pre-insert check to prevent duplicates:**

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

    with get_db_session() as db:
        # Check if already processed (prevents race condition)
        existing = db.query(ProcessedGranolaNote).filter(
            ProcessedGranolaNote.note_id == note_id,
            ProcessedGranolaNote.account_id == self.account_id
        ).first()

        if existing:
            logger.debug(
                f"Note '{note_id}' already marked as processed by another agent. "
                f"Original processing: {existing.processed_at}"
            )
            return

        # Insert new record
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
            logger.debug(f"Marked note '{note_title}' as processed ({tasks_created} tasks)")
        except IntegrityError:
            # Race condition: another agent inserted between our check and insert
            db.rollback()
            logger.debug(
                f"Note '{note_id}' was marked processed by another agent during insertion"
            )
        except Exception:
            db.rollback()
            raise
```

**Pros:**
- Handles race condition gracefully
- Clear logging for debugging
- No duplicate task creation (returns early)
- Proper rollback on errors

**Cons:**
- Two database queries instead of one (check + insert)

**Effort:** Small (30 minutes)
**Risk:** Low

### Solution 2: INSERT OR IGNORE with SQLAlchemy
**Use database-level duplicate handling:**

```python
from sqlalchemy.dialects.sqlite import insert

def mark_note_processed(self, note_id: str, ...):
    from src.models.database import get_db_session

    with get_db_session() as db:
        stmt = insert(ProcessedGranolaNote).values(
            note_id=note_id,
            workspace_id=self.workspace_id,
            account_id=self.account_id,
            note_title=note_title,
            note_created_at=note_created_at,
            tasks_created_count=tasks_created,
        ).on_conflict_do_nothing(  # SQLite: INSERT OR IGNORE
            index_elements=['note_id', 'account_id']
        )

        result = db.execute(stmt)
        db.commit()

        if result.rowcount == 0:
            logger.debug(f"Note '{note_id}' already processed (duplicate insert ignored)")
        else:
            logger.debug(f"Marked note '{note_title}' as processed")
```

**Pros:**
- Database-atomic operation
- Single query
- Most efficient solution

**Cons:**
- SQLite-specific syntax (though supported)
- Less portable to other databases without adjustment

**Effort:** Medium (1 hour + testing)
**Risk:** Low

### Solution 3: Row-Level Locking
**Use SELECT FOR UPDATE to lock rows:**

```python
def _filter_new_notes(self, notes: list[dict]) -> list[dict]:
    from src.models.database import get_db_session

    with get_db_session() as db:
        note_ids = [note["id"] for note in notes]

        # Lock rows to prevent concurrent processing
        processed = set(
            row[0]
            for row in db.query(ProcessedGranolaNote.note_id)
            .filter(ProcessedGranolaNote.note_id.in_(note_ids))
            .filter(ProcessedGranolaNote.account_id == self.account_id)
            .with_for_update()  # Row-level lock
            .all()
        )

    return [note for note in notes if note["id"] not in processed]
```

**Pros:**
- Prevents race at read level
- Standard SQL pattern

**Cons:**
- Not supported in SQLite (will fail)
- Blocks other agents (reduces concurrency)
- More complex

**Effort:** Medium (1-2 hours)
**Risk:** High (SQLite doesn't support FOR UPDATE)

## Recommended Action

**Implement Solution 1** - Check-then-insert with proper error handling. This is the most robust solution that works with SQLite and handles race conditions gracefully.

## Technical Details

**Affected Files:**
- `src/integrations/granola_integration.py` (`mark_note_processed` method, lines 289-311)

**Database Schema:**
```sql
CREATE TABLE processed_granola_notes (
    ...
    UNIQUE (note_id, account_id) -- Constraint name: uix_note_account
);
```

**Concurrency Scenarios:**
| Scenario | Current Behavior | After Fix |
|----------|------------------|-----------|
| Single agent | ✅ Works | ✅ Works |
| Two agents, 1-minute gap | ✅ Second filtered out | ✅ Second filtered out |
| Two agents, same time | ❌ Duplicate tasks, error | ✅ First succeeds, second skips |

## Acceptance Criteria

- [ ] Add pre-insert existence check to `mark_note_processed()`
- [ ] Return early if note already processed
- [ ] Add try/except for IntegrityError with rollback
- [ ] Log race condition detection clearly
- [ ] Add unit test: concurrent mark_note_processed calls
- [ ] Add integration test: simulate race condition
- [ ] Verify no duplicate tasks created in race scenario
- [ ] Verify clear log messages for debugging

## Work Log

**2026-02-11:**
- Issue identified during data integrity review
- Confirmed no transaction isolation
- Researched SQLAlchemy INSERT OR IGNORE patterns
- Documented check-then-insert solution
- Verified unique constraint name in migration

## Resources

- **Review Finding**: Data Integrity Guardian Review - P1 Issue
- **PR**: https://github.com/mikedon/personal-assistant/pull/3
- **Migration**: `alembic/versions/d98864ddf865_add_granola_integration_support.py` (unique constraint)
- **SQLAlchemy Docs**: https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#insert-on-conflict-upsert
- **Pattern**: Check-then-act with exception handling (idempotent operations)
