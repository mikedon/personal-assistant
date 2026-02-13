---
status: pending
priority: p2
issue_id: "009"
tags: [code-review, devops, migration, testing]
dependencies: []
---

# No Database Migration Testing

## Problem Statement

No automated tests verify migration success or rollback behavior. Production database has 100K+ tasks - migration runs during deployment without validation that existing tasks are unaffected or that the downgrade path works.

**Why This Matters:** Undetected migration failures could leave schema inconsistent or cause production outages. Large tables may experience long lock times.

## Findings

### DevOps Harmony Analyst
- **Severity:** HIGH
- **Category:** Migration
- **Risk:** Undetected migration failures, schema inconsistencies, production outages

**Missing Tests:**
- ✗ Migration upgrade with existing data
- ✗ Verify existing tasks unaffected
- ✗ Verify new column exists and is nullable
- ✗ Migration downgrade preserves task data
- ✗ Column removal is clean
- ✗ Migration performance on large datasets

## Proposed Solutions

### Solution 1: Comprehensive Migration Test Suite (RECOMMENDED)
**Pros:**
- Validates all migration scenarios
- Prevents production surprises
- Documents expected behavior

**Cons:**
- Takes time to write

**Effort:** Medium (2 hours)
**Risk:** None (pure test addition)

**Implementation:**
```python
# tests/integration/test_migrations.py

def test_document_links_migration_upgrade(test_db_session):
    """Test upgrade migration with existing data."""
    # Create tasks BEFORE migration
    service = TaskService(test_db_session)
    task1 = service.create_task(title="Task 1")
    task2 = service.create_task(title="Task 2", tags=["important"])

    # Run migration upgrade
    from alembic.command import upgrade
    from alembic.config import Config
    alembic_cfg = Config("alembic.ini")
    upgrade(alembic_cfg, "fb0591259fd8")  # document_links migration

    # Verify existing tasks unaffected
    test_db_session.refresh(task1)
    test_db_session.refresh(task2)
    assert task1.title == "Task 1"
    assert task2.get_tags_list() == ["important"]

    # Verify new column exists
    assert hasattr(task1, "document_links")
    assert task1.document_links is None  # Nullable

    # Verify can add document links
    service.update_task(task1, document_links=["https://example.com"])
    assert task1.get_document_links_list() == ["https://example.com"]


def test_document_links_migration_downgrade(test_db_session):
    """Test downgrade migration preserves task data."""
    # Create task with document links
    service = TaskService(test_db_session)
    task = service.create_task(
        title="Task",
        document_links=["https://example.com"]
    )
    task_id = task.id

    # Run migration downgrade
    from alembic.command import downgrade
    from alembic.config import Config
    alembic_cfg = Config("alembic.ini")
    downgrade(alembic_cfg, "-1")  # Down one revision

    # Verify task still exists
    task = test_db_session.get(Task, task_id)
    assert task is not None
    assert task.title == "Task"

    # Verify document_links column removed
    assert not hasattr(task, "document_links")


def test_migration_performance_large_dataset():
    """Test migration performance with 10K tasks."""
    import time

    # Create 10,000 tasks
    service = TaskService(test_db_session)
    for i in range(10000):
        service.create_task(title=f"Task {i}")

    # Measure migration time
    start = time.time()
    # Run migration
    from alembic.command import upgrade
    from alembic.config import Config
    alembic_cfg = Config("alembic.ini")
    upgrade(alembic_cfg, "fb0591259fd8")
    duration = time.time() - start

    # Should complete in < 5 seconds for 10K rows
    assert duration < 5.0, f"Migration took {duration:.2f}s (too slow)"


def test_migration_idempotent():
    """Test migration can be run multiple times safely."""
    from alembic.command import upgrade
    from alembic.config import Config
    alembic_cfg = Config("alembic.ini")

    # Run migration twice
    upgrade(alembic_cfg, "fb0591259fd8")
    upgrade(alembic_cfg, "fb0591259fd8")  # Should be no-op

    # Verify schema is correct
    from sqlalchemy import inspect
    inspector = inspect(test_db_session.get_bind())
    columns = {col["name"]: col for col in inspector.get_columns("tasks")}

    assert "document_links" in columns
    assert columns["document_links"]["type"].length == 1000
    assert columns["document_links"]["nullable"] is True
```

### Solution 2: Manual Testing Checklist
**Pros:**
- Fast to create
- Documents procedure

**Cons:**
- Manual, error-prone
- Not automated

**Effort:** Small (30 minutes)
**Risk:** Medium

## Recommended Action

**Implement Solution 1** (automated migration tests) to ensure production safety.

## Technical Details

**Affected Files:**
- `tests/integration/test_migrations.py` (NEW)
- `tests/conftest.py` (fixtures for Alembic testing)

**Migration Details:**
- **Revision:** fb0591259fd8
- **Changes:** Adds `document_links VARCHAR(1000) NULL`
- **Backward Compatible:** Yes (nullable column)
- **Expected Duration:** <1 second for small databases, 1-5 seconds for 10K+ tasks

## Acceptance Criteria

- [ ] Migration upgrade test passes
- [ ] Migration downgrade test passes
- [ ] Existing tasks unaffected by migration
- [ ] Performance test with 10K tasks completes in <5s
- [ ] Idempotency test passes
- [ ] Tests run in CI/CD pipeline

## Resources

- **PR:** #2
- **Migration File:** `alembic/versions/fb0591259fd8_add_document_links_to_tasks_table.py`
- **Alembic Docs:** [Testing Migrations](https://alembic.sqlalchemy.org/en/latest/cookbook.html#test-current-database-revision-is-at-head-s)
