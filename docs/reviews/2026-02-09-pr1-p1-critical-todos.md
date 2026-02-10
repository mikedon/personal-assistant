# P1 Critical TODOs - PR #1 Multi-Account Integration

**Status:** BLOCKING - Must fix before merge
**Created:** 2026-02-09
**PR:** #1 feat: Add multi-account Google integration support

## Overview

These 16 critical issues must be resolved before merging PR #1. Each issue has the potential to cause system crashes, security vulnerabilities, or data integrity problems.

---

## 1. Fix Agent Poll Cycle Crash ⚠️ BLOCKS DEPLOYMENT

**Category:** Performance/Bugs
**File:** `/Users/miked/workspace/personal-assistant/src/agent/core.py:330`

**Issue:**
IntegrationManager.poll_all() changed return type from `dict[IntegrationType, list[ActionableItem]]` to `list[ActionableItem]`, but agent code still calls `.items()` causing immediate AttributeError on agent startup.

**Impact:**
Agent cannot run at all. System will crash on first poll cycle.

**Fix:**
```python
# In src/agent/core.py _poll_cycle() method
# Change from:
all_items = await self.integration_manager.poll_all()
for integration_type, items in all_items.items():  # ❌ CRASHES
    # ...

# To:
all_items = await self.integration_manager.poll_all()
for item in all_items:  # ✅ Works with new list return
    integration_type = item.source  # Extract from ActionableItem
    # Or access metadata if needed: item.metadata.get("account_id")
```

---

## 2. Implement Authorization for Account Access ⚠️ SECURITY

**Category:** Security
**File:** `/Users/miked/workspace/personal-assistant/src/api/routes/tasks.py:37`

**Issue:**
No authentication or authorization checks on account_id parameter. Any API consumer can access tasks from any account by supplying different account_id values.

**Impact:**
Horizontal privilege escalation - users can view/modify tasks from accounts they don't own.

**Fix:**
1. Implement authentication middleware to identify current user
2. Add user-to-account ownership mapping in database
3. Validate user owns the requested account_id before filtering
```python
# Pseudo-code
@router.get("/api/tasks")
async def list_tasks(
    account_id: str | None = None,
    current_user: User = Depends(get_current_user)  # Add auth dependency
):
    if account_id:
        # Validate ownership
        if not await user_owns_account(current_user.id, account_id):
            raise HTTPException(status_code=403, detail="Access denied to account")

    tasks = service.get_tasks(account_id=account_id, user_id=current_user.id)
    # ...
```

---

## 3. Add Authorization for CLI Account Commands ⚠️ SECURITY

**Category:** Security
**File:** `/Users/miked/workspace/personal-assistant/src/cli.py:526-557`

**Issue:**
CLI commands "pa accounts authenticate" and "pa accounts list" have no authentication. Any user with CLI access can authenticate any configured account.

**Impact:**
In multi-user environments, unauthorized users can authenticate Google accounts they don't own.

**Fix:**
1. Implement user-level authentication for CLI
2. Store account ownership in user-specific config directories (~/.personal-assistant/)
3. Add audit logging for all authentication attempts
```bash
# Restrict config to user: chmod 600 ~/.personal-assistant/config.yaml
# Store tokens in user-specific directory: ~/.personal-assistant/tokens/
```

---

## 4. Make account_id First-Class Field in ActionableItem ⚠️ ARCHITECTURE

**Category:** Architecture/Type Safety
**Files:**
- `/Users/miked/workspace/personal-assistant/src/integrations/base.py:44`
- `/Users/miked/workspace/personal-assistant/src/integrations/manager.py:272-274`

**Issue:**
account_id is stored in untyped metadata dict and extracted with dict.get(). Loses type safety and makes account_id second-class citizen.

**Impact:**
No type checking, typos silently return None, refactoring tools won't find usages, harder to trace data flow.

**Fix:**
```python
# In src/integrations/base.py
@dataclass
class ActionableItem:
    source: IntegrationType
    title: str
    description: str
    priority: str | None = None
    metadata: dict[str, Any] | None = None
    account_id: str | None = None  # ✅ Add as first-class field

# Update all integrations to set account_id directly:
# In src/integrations/gmail_integration.py
return ActionableItem(
    source=IntegrationType.GMAIL,
    title=title_preview,
    description=body_preview,
    priority=priority_str,
    metadata=metadata,
    account_id=self.account_id,  # ✅ Set directly
)

# In src/integrations/manager.py actionable_item_to_task_params
account_id = item.account_id  # ✅ Type-safe access
```

---

## 5. Validate account_id References in TaskService ⚠️ DATA INTEGRITY

**Category:** Architecture/Validation
**File:** `/Users/miked/workspace/personal-assistant/src/services/task_service.py:152`

**Issue:**
TaskService.create_task() accepts account_id but doesn't validate it exists in configuration. Allows orphaned tasks with invalid account_ids.

**Impact:**
Tasks can reference non-existent accounts, breaking filters and reports.

**Fix:**
```python
# In src/services/task_service.py
def create_task(
    self,
    title: str,
    account_id: str | None = None,
    **kwargs
) -> Task:
    """Create a new task with validation."""

    # Validate account_id if provided
    if account_id:
        from src.integrations.manager import IntegrationManager
        manager = IntegrationManager()  # Or inject as dependency

        # Check if account exists
        all_accounts = []
        for itype in IntegrationType:
            all_accounts.extend(manager.list_accounts(itype))

        if account_id not in all_accounts:
            raise ValueError(
                f"Invalid account_id: {account_id}. "
                f"Configured accounts: {', '.join(all_accounts)}"
            )

    # Proceed with task creation
    task = Task(title=title, account_id=account_id, **kwargs)
    # ...
```

---

## 6. Validate Composite Key Uniqueness ⚠️ ARCHITECTURE

**Category:** Architecture/Validation
**File:** `/Users/miked/workspace/personal-assistant/src/integrations/manager.py:72-73`

**Issue:**
No check for duplicate keys when storing integrations. Duplicate account_ids silently overwrite earlier instances.

**Impact:**
Some accounts won't be polled, difficult to debug since no error is raised.

**Fix:**
```python
# In src/integrations/manager.py _initialize_integrations
key = (IntegrationType.GMAIL, account_id)

# Check for duplicates
if key in self.integrations:
    logger.error(
        f"Duplicate account_id '{account_id}' for {IntegrationType.GMAIL.value}. "
        f"Skipping duplicate configuration."
    )
    continue

self.integrations[key] = gmail_integration
```

---

## 7. Add Composite Database Index ⚠️ PERFORMANCE

**Category:** Performance
**File:** `/Users/miked/workspace/personal-assistant/alembic/versions/7cc4fcff7603_add_account_id_to_tasks_table.py:25`

**Issue:**
Single-column index on account_id is insufficient. Most queries filter by both account_id AND status, forcing full scans.

**Impact:**
With 1000+ tasks across multiple accounts, queries degrade 3-5x.

**Fix:**
```python
# Update Alembic migration
def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tasks', sa.Column('account_id', sa.String(length=100), nullable=True))

    # Add single-column index for simple filters
    op.create_index(op.f('ix_tasks_account_id'), 'tasks', ['account_id'], unique=False)

    # Add composite index for common query pattern
    op.create_index(
        'ix_tasks_account_status',
        'tasks',
        ['account_id', 'status'],
        unique=False
    )

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_tasks_account_status', table_name='tasks')
    op.drop_index(op.f('ix_tasks_account_id'), table_name='tasks')
    op.drop_column('tasks', 'account_id')
```

---

## 8. Fix N+1 Query Problem ⚠️ PERFORMANCE

**Category:** Performance
**File:** `/Users/miked/workspace/personal-assistant/src/api/routes/tasks.py:223`

**Issue:**
_task_to_response() accesses task.initiative.title for each task, triggering lazy loading. 50 tasks = 51 database queries.

**Impact:**
API response times increase linearly: 50 tasks at 100ms/query = 5 seconds added latency.

**Fix:**
```python
# In src/services/task_service.py get_tasks()
from sqlalchemy.orm import joinedload

def get_tasks(
    self,
    status: TaskStatus | None = None,
    account_id: str | None = None,
    # ...
) -> list[Task]:
    """Get tasks with optional filtering."""
    query = self.db.query(Task)

    # Add eager loading for initiative
    query = query.options(joinedload(Task.initiative))

    # Apply filters
    if status:
        query = query.filter(Task.status == status)
    if account_id:
        query = query.filter(Task.account_id == account_id)

    # ...
    return query.all()
```

Apply to all multi-task methods: get_prioritized_tasks(), get_overdue_tasks(), get_due_soon_tasks(), bulk_update_status().

---

## 9. Secure OAuth Token Storage ⚠️ SECURITY

**Category:** Security
**File:** `/Users/miked/workspace/personal-assistant/src/integrations/oauth_utils.py:72-77`

**Issue:**
OAuth tokens stored in plain text with default permissions (0644). Any process can read refresh tokens.

**Impact:**
Token theft = persistent access to user's Gmail, Calendar, Drive even after original session revoked.

**Fix:**
```python
# In src/integrations/oauth_utils.py
import os

def _save_credentials(self) -> None:
    """Save credentials to token file with restricted permissions."""
    if self._creds:
        self.token_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        # Write token file
        with open(self.token_path, "w") as token:
            token.write(self._creds.to_json())

        # Set restrictive permissions (owner read/write only)
        os.chmod(self.token_path, 0o600)

        logger.info(f"Saved OAuth token with secure permissions: {self.token_path}")
```

---

## 10. Add Type Annotation Simplification ⚠️ MAINTAINABILITY

**Category:** Code Simplicity
**File:** `/Users/miked/workspace/personal-assistant/src/integrations/manager.py:32`

**Issue:**
Composite key `tuple[IntegrationType, str]` requires unpacking 15+ times throughout file, increasing cognitive load.

**Impact:**
High maintenance burden, easy to make mistakes constructing keys.

**Fix:**
```python
# Create proper key class
from dataclasses import dataclass

@dataclass(frozen=True)
class IntegrationKey:
    """Key for integration lookup in multi-account setups."""
    type: IntegrationType
    account_id: str

    def __str__(self) -> str:
        return f"{self.type.value}:{self.account_id}"

# In IntegrationManager
class IntegrationManager:
    def __init__(self, config: Config):
        self.integrations: dict[IntegrationKey, BaseIntegration] = {}
        # ...

    def poll_account(self, integration_type: IntegrationType, account_id: str):
        key = IntegrationKey(integration_type, account_id)  # ✅ Clear intent
        integration = self.integrations.get(key)
        # ...
```

---

## 11-16. Critical Test Coverage Gaps ⚠️ TESTING

**Category:** Testing
**Files:** Test files missing

**Issues:**
11. No tests for migrate_legacy_google_config() - backwards compatibility untested
12. No GoogleAccountConfig validation tests - field validators untested
13. No IntegrationManager multi-account tests - poll_account, list_accounts untested
14. No account_id in ActionableItem metadata tests - core feature untested
15. No TaskService account_id filter tests - API filtering untested
16. No CLI accounts command tests - user-facing features untested

**Impact:**
Core multi-account functionality has zero test coverage. Regressions will not be caught.

**Fix:**
Create comprehensive test suite covering:

```python
# tests/unit/test_config.py
def test_migrate_legacy_google_config():
    """Test config migration preserves all fields."""
    legacy_config = {
        "google": {
            "enabled": True,
            "credentials_path": "credentials.json",
            "token_path": "token.json",
            # ...
        }
    }

    migrated = migrate_legacy_google_config(legacy_config)

    assert "accounts" in migrated["google"]
    assert migrated["google"]["accounts"][0]["account_id"] == "default"
    assert migrated["google"]["accounts"][0]["credentials_path"] == "credentials.json"

# tests/unit/test_integrations.py
def test_integration_manager_multiple_accounts():
    """Test IntegrationManager with multiple Gmail accounts."""
    # Create config with 2 accounts
    config = create_multi_account_config()
    manager = IntegrationManager(config)

    # Verify both accounts initialized
    accounts = manager.list_accounts(IntegrationType.GMAIL)
    assert len(accounts) == 2
    assert "personal" in accounts
    assert "work" in accounts

# tests/unit/test_task_service.py
def test_get_tasks_filter_by_account_id():
    """Test filtering tasks by account_id."""
    service = TaskService(db)

    # Create tasks with different account_ids
    service.create_task(title="Task 1", account_id="personal")
    service.create_task(title="Task 2", account_id="work")

    # Filter by account
    personal_tasks = service.get_tasks(account_id="personal")
    assert len(personal_tasks) == 1
    assert personal_tasks[0].title == "Task 1"
```

---

## Action Plan

1. **Immediate:** Fix agent crash (Issue #1) - blocks all functionality
2. **Security Pass:** Address issues #2, #3, #9 (authorization, token security)
3. **Architecture Pass:** Address issues #4, #5, #6, #10 (type safety, validation)
4. **Performance Pass:** Address issues #7, #8 (indexes, N+1 queries)
5. **Testing Pass:** Address issues #11-16 (comprehensive test coverage)

**Estimated Effort:** 2-3 days for all critical fixes

**Success Criteria:**
- ✅ Agent starts and polls without errors
- ✅ All API endpoints validate account_id authorization
- ✅ OAuth tokens stored with 0600 permissions
- ✅ ActionableItem has account_id as typed field
- ✅ Database queries use composite indexes
- ✅ Test coverage >70% for multi-account code
