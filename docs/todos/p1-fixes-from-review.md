# P1 Critical Fixes from Code Review (2026-02-09)

Status: **PENDING**
Created: 2026-02-09
PR: #1 (feat: Add multi-account Google integration support)
Review: docs/reviews/2026-02-09-pr1-comprehensive-review.md

## Overview

This todo tracks 8 critical (P1) issues identified in the comprehensive code review of the multi-account Google integration. These must be fixed before merging PR #1.

---

## P1-1: Fix OAuth Token Race Condition ⚠️ SECURITY

**File**: `src/integrations/oauth_utils.py:79-83`
**Priority**: CRITICAL (Security)
**Effort**: 15 minutes

### Issue
File is created with default permissions (0644) before chmod to 0600, creating a brief window where OAuth tokens are world-readable.

### Current Code
```python
with open(self.token_path, "w") as token:
    token.write(self._creds.to_json())

os.chmod(self.token_path, 0o600)  # Race condition: file already exists
```

### Fix Required
Use `os.open()` with mode parameter for atomic creation:

```python
def _save_credentials(self) -> None:
    """Save credentials to token file with restricted permissions."""
    if self._creds:
        # Create parent directory with restricted permissions
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.token_path.parent, 0o700)  # Ensure directory permissions

        # Atomically create file with secure permissions
        fd = os.open(self.token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, 'w') as token:
                token.write(self._creds.to_json())
        except:
            os.close(fd)  # Clean up fd if fdopen fails
            raise
```

### Verification
- [ ] File created with 0600 permissions from start
- [ ] Parent directory has 0700 permissions
- [ ] Test on Linux/macOS to verify no race condition
- [ ] Add test: `test_oauth_token_permissions()`

---

## P1-2: Verify Composite Database Index Applied

**File**: `alembic/versions/7cc4fcff7603_add_account_id_to_tasks_table.py:31`
**Priority**: CRITICAL (Performance)
**Effort**: 5 minutes

### Issue
Migration file defines composite index `ix_tasks_account_status` but it may not be applied to production database.

### Verification Required
```bash
# Check if index exists in database
sqlite3 personal_assistant.db "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tasks';"

# Should see: ix_tasks_account_status
```

### Fix if Missing
```bash
# Re-run migration
alembic upgrade head

# OR manually create index
sqlite3 personal_assistant.db "CREATE INDEX ix_tasks_account_status ON tasks (account_id, status);"
```

### Verification
- [ ] Index `ix_tasks_account_status` exists in database
- [ ] Index is on columns (account_id, status) in that order
- [ ] Query plan uses index for account_id+status filters
- [ ] Consider adding integration test to verify indexes

---

## P1-3: Fix N+1 Query in recalculate_all_priorities()

**File**: `src/services/task_service.py:327-343`
**Priority**: CRITICAL (Performance)
**Effort**: 5 minutes

### Issue
Missing `joinedload(Task.initiative)` but `calculate_priority_score()` accesses `task.initiative` on line 548, causing N+1 queries.

### Current Code
```python
def recalculate_all_priorities(self) -> int:
    tasks = (
        self.db.query(Task)
        .filter(Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]))
        .all()
    )  # NO joinedload!

    for task in tasks:
        task.priority_score = self.calculate_priority_score(task)  # Accesses task.initiative
```

### Fix Required
```python
def recalculate_all_priorities(self) -> int:
    tasks = (
        self.db.query(Task)
        .options(joinedload(Task.initiative))  # ADD THIS LINE
        .filter(Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]))
        .all()
    )

    for task in tasks:
        task.priority_score = self.calculate_priority_score(task)
```

### Verification
- [ ] Add `joinedload(Task.initiative)` on line 334
- [ ] Test with tasks that have initiatives
- [ ] Verify SQL query log shows JOIN instead of separate queries
- [ ] Add test: `test_recalculate_priorities_uses_joinedload()`

---

## P1-4: Refactor get_statistics() to Use SQL Aggregation

**File**: `src/services/task_service.py:420-438`
**Priority**: CRITICAL (Performance + Memory)
**Effort**: 20 minutes

### Issue
Loads ALL completed tasks into memory to calculate average completion time. Unbounded memory usage.

### Current Code
```python
completed_with_dates = (
    self.db.query(Task)  # Loads ALL completed tasks
    .filter(
        and_(
            Task.status == TaskStatus.COMPLETED,
            Task.completed_at.isnot(None),
        )
    )
    .all()
)

if completed_with_dates:
    total_hours = sum(
        (task.completed_at - task.created_at).total_seconds() / 3600
        for task in completed_with_dates
    )
    avg_completion_hours = total_hours / len(completed_with_dates)
```

### Fix Required
```python
# Use SQL aggregation instead of loading all tasks
avg_completion_seconds = (
    self.db.query(
        func.avg(
            func.julianday(Task.completed_at) - func.julianday(Task.created_at)
        ) * 86400  # Convert days to seconds
    )
    .filter(
        and_(
            Task.status == TaskStatus.COMPLETED,
            Task.completed_at.isnot(None),
            Task.created_at.isnot(None),
        )
    )
    .scalar()
)

avg_completion_hours = avg_completion_seconds / 3600 if avg_completion_seconds else None
```

### Verification
- [ ] Replace memory loading with SQL aggregation
- [ ] Test with 0, 1, and 100+ completed tasks
- [ ] Verify memory usage is constant regardless of completed task count
- [ ] Check SQL query returns same result as old method

---

## P1-5: Refactor Account Validation to Eliminate Performance Bottleneck

**File**: `src/services/task_service.py:207-233`
**Priority**: CRITICAL (Performance + Architecture)
**Effort**: 45 minutes

### Issue
`_validate_account_id()` creates new `IntegrationManager` on EVERY task creation, causing severe performance overhead (loads config, initializes all integrations).

### Current Code
```python
def _validate_account_id(self, account_id: str) -> None:
    from src.integrations.base import IntegrationType
    from src.integrations.manager import IntegrationManager
    from src.utils.config import load_config

    config = load_config()  # EXPENSIVE: reads from disk
    manager = IntegrationManager(config)  # EXPENSIVE: initializes all integrations

    all_accounts = []
    for integration_type in IntegrationType:
        all_accounts.extend(manager.list_accounts(integration_type))

    if account_id not in all_accounts:
        raise ValueError(...)
```

### Fix Options

**Option A: Pass IntegrationManager to TaskService (Recommended)**
```python
# In TaskService.__init__
def __init__(self, db: Session, integration_manager: IntegrationManager | None = None):
    self.db = db
    self._integration_manager = integration_manager
    self._valid_accounts: set[str] | None = None

def _get_valid_accounts(self) -> set[str]:
    """Lazy-load and cache valid account IDs."""
    if self._valid_accounts is None:
        if self._integration_manager is None:
            # Lazy-load manager if not provided
            from src.integrations.manager import IntegrationManager
            from src.utils.config import load_config
            config = load_config()
            self._integration_manager = IntegrationManager(config)

        all_accounts = []
        from src.integrations.base import IntegrationType
        for integration_type in IntegrationType:
            all_accounts.extend(self._integration_manager.list_accounts(integration_type))
        self._valid_accounts = set(all_accounts)

    return self._valid_accounts

def _validate_account_id(self, account_id: str) -> None:
    valid_accounts = self._get_valid_accounts()
    if account_id not in valid_accounts:
        raise AccountNotFoundError(
            f"Invalid account_id: {account_id}. "
            f"Configured accounts: {', '.join(sorted(valid_accounts)) if valid_accounts else 'none'}"
        )
```

**Option B: Validate at API/CLI Layer**
Move validation out of TaskService entirely, validate at presentation layer.

### Verification
- [ ] Choose and implement option (recommend Option A)
- [ ] Update all TaskService instantiations to optionally pass IntegrationManager
- [ ] Test validation is cached across multiple task creations
- [ ] Benchmark: create 100 tasks, verify no performance degradation
- [ ] Create custom exception: `AccountNotFoundError`

---

## P1-6: Fix test_connections() Return Type Mismatch

**File**: `src/integrations/manager.py:195-210`
**Priority**: CRITICAL (Type Safety)
**Effort**: 5 minutes

### Issue
Method signature says it returns `dict[tuple[IntegrationType, str], bool]` but actually stores results with `IntegrationKey` objects.

### Current Code
```python
async def test_connections(self) -> dict[tuple[IntegrationType, str], bool]:
    results = {}
    for key, integration in self.integrations.items():  # key is IntegrationKey
        try:
            results[key] = await integration.test_connection()  # Type mismatch!
```

### Fix Required
```python
async def test_connections(self) -> dict[IntegrationKey, bool]:
    """Test connections for all integrations.

    Returns:
        Dictionary mapping IntegrationKey to connection test result (True=success).
    """
    results = {}
    for key, integration in self.integrations.items():
        try:
            results[key] = await integration.test_connection()
        except Exception as e:
            logger.error(f"Connection test failed for {key}: {e}")
            results[key] = False

    return results
```

### Verification
- [ ] Update return type annotation to `dict[IntegrationKey, bool]`
- [ ] Update any callers to expect IntegrationKey instead of tuple
- [ ] Run mypy/type checker to verify no errors
- [ ] Test with multiple accounts

---

## P1-7: Add Error Handling to OAuth Token Save

**File**: `src/integrations/oauth_utils.py:72-83`
**Priority**: CRITICAL (Reliability + UX)
**Effort**: 20 minutes

### Issue
No error handling for file operations (mkdir, open, chmod). Could lose credentials on disk full, permission errors.

### Current Code
```python
def _save_credentials(self) -> None:
    if self._creds:
        self.token_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(self.token_path, "w") as token:
            token.write(self._creds.to_json())
        os.chmod(self.token_path, 0o600)
```

### Fix Required
```python
def _save_credentials(self) -> None:
    """Save credentials to token file with restricted permissions.

    Raises:
        IOError: If unable to create directory or save token file.
    """
    if not self._creds:
        return

    try:
        # Create parent directory with restricted permissions
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.token_path.parent, 0o700)

        # Atomically create file with secure permissions (combines with P1-1 fix)
        fd = os.open(self.token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, 'w') as token:
                token.write(self._creds.to_json())
        except:
            os.close(fd)
            raise
    except PermissionError as e:
        raise IOError(
            f"Permission denied saving OAuth token to {self.token_path}. "
            f"Ensure the directory is writable: {self.token_path.parent}"
        ) from e
    except OSError as e:
        raise IOError(
            f"Failed to save OAuth token to {self.token_path}. "
            f"Check disk space and permissions. Error: {e}"
        ) from e
```

### Verification
- [ ] Add try/except around file operations
- [ ] Provide user-friendly error messages with resolution steps
- [ ] Test with read-only filesystem (should raise IOError)
- [ ] Test with full disk (should raise IOError)
- [ ] Add test: `test_save_credentials_handles_permission_error()`

---

## P1-8: Fix Database Rollback in Account Validation

**File**: `src/services/task_service.py:182-184`
**Priority**: CRITICAL (Data Integrity)
**Effort**: 15 minutes

### Issue
Validation creates separate sessions inside `create_task()`. If task creation fails after validation, no proper rollback.

### Current Code
```python
def create_task(self, ..., account_id: str | None = None, ...) -> Task:
    # Validate account_id if provided
    if account_id:
        self._validate_account_id(account_id)  # Creates separate session inside!

    task = Task(...)  # Could fail here
    self.db.add(task)
    self.db.commit()  # What if this fails?
```

### Fix Required
Move validation BEFORE any database operations begin:

```python
def create_task(self, ..., account_id: str | None = None, ...) -> Task:
    """Create a new task with calculated priority score.

    Args:
        ...
        account_id: Account identifier (validated before any DB operations)

    Raises:
        AccountNotFoundError: If account_id is invalid
    """
    # Validate FIRST, before touching database
    if account_id:
        self._validate_account_id(account_id)

    # Now proceed with database operations
    task = Task(
        title=title,
        description=description,
        priority=priority,
        source=source,
        source_reference=source_reference,
        account_id=account_id,
        due_date=due_date,
        initiative_id=initiative_id,
    )

    if tags:
        task.set_tags_list(tags)

    task.priority_score = self.calculate_priority_score(task)

    self.db.add(task)
    self.db.commit()
    self.db.refresh(task)

    return task
```

**Note**: This is already the case in current code! Validation is on line 184, task creation on line 186. But with the refactor from P1-5 (caching), this ensures validation doesn't create new sessions.

### Verification
- [ ] Ensure validation happens before Task() instantiation
- [ ] After P1-5 refactor, verify no nested sessions created
- [ ] Test: validation failure doesn't leave DB in inconsistent state
- [ ] Add test: `test_create_task_validation_failure_rolls_back()`

---

## Summary Checklist

- [ ] **P1-1**: OAuth token race condition fixed with atomic creation
- [ ] **P1-2**: Composite database index verified/applied
- [ ] **P1-3**: N+1 query fixed in recalculate_all_priorities()
- [ ] **P1-4**: get_statistics() refactored to use SQL aggregation
- [ ] **P1-5**: Account validation refactored with caching
- [ ] **P1-6**: test_connections() return type fixed
- [ ] **P1-7**: Error handling added to OAuth token save
- [ ] **P1-8**: Database rollback verified after P1-5 refactor

## Testing Requirements

After all fixes:
- [ ] All existing tests pass (35 tests)
- [ ] Add 3 new critical tests:
  - `test_oauth_token_permissions()`
  - `test_recalculate_priorities_uses_joinedload()`
  - `test_save_credentials_handles_errors()`
- [ ] Performance test: Create 100 tasks with account_id validation
- [ ] Manual verification: OAuth token file has 0600 permissions
- [ ] Database index verification query

## Estimated Total Effort

- **Total Time**: ~2.5 hours
- **High Impact**: Performance improvements will be immediately noticeable
- **Security**: Closes critical OAuth token exposure window

## Related Issues

- P2 issues tracked in: docs/reviews/2026-02-09-pr1-comprehensive-review.md
- Original P1 fixes completed: docs/reviews/2026-02-09-pr1-review-complete.md
