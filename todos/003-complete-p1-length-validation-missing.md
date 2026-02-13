---
status: pending
priority: p1
issue_id: "003"
tags: [code-review, data-integrity, validation, critical]
dependencies: []
---

# Length Limit Not Enforced Programmatically

## Problem Statement

Database column has `String(1000)` limit, but no validation enforces this before database insertion. Application could crash on oversized input, or silently truncate data in production (MySQL), or fail with database errors (PostgreSQL).

**Why This Matters:** Tests pass in development (SQLite ignores limits) but fail in production. Users get no feedback that their data was truncated or rejected.

## Findings

### Data Integrity Guardian
- **Severity:** CRITICAL
- **Location:** `src/models/task.py:87`
- **Scenario:**
  - SQLite (dev): Accepts 2000 char string ✓
  - PostgreSQL (prod): Raises DataError ✗
  - MySQL (prod): Silently truncates to 1000 chars (data loss) ✗
- **Evidence:**
  ```python
  document_links: Mapped[str | None] = mapped_column(String(1000), nullable=True)
  # No validation in set_document_links_list() or Pydantic schema
  ```

### Security Review Agent
- **Severity:** MEDIUM
- **Risk:** DoS potential by causing repeated database errors, data loss without warning

### Performance Oracle
- **Severity:** HIGH
- **Issue:** 1000 char limit ≈ 3-10 URLs depending on length, easily exceeded by typical URLs

## Proposed Solutions

### Solution 1: Pydantic Validator + Increased Limit (RECOMMENDED)
**Pros:**
- Validates at API boundary before database
- Clear error messages to users
- Increases limit to realistic value (2000 or 5000)
- Prevents production failures

**Cons:**
- Requires database migration to increase limit
- Still has a limit (but more realistic)

**Effort:** Small (1 hour)
**Risk:** Low

**Implementation:**
```python
from pydantic import field_validator

class TaskBase(BaseModel):
    document_links: list[HttpUrl] = Field(default_factory=list, max_length=20)

    @field_validator('document_links')
    @classmethod
    def validate_total_length(cls, v):
        """Ensure total CSV/JSON length doesn't exceed database limit."""
        if v:
            # Calculate serialized length (JSON format after fix #001)
            serialized = json.dumps([str(url) for url in v])
            if len(serialized) > 5000:  # New limit after migration
                raise ValueError(
                    f"Total document links length ({len(serialized)} chars) "
                    f"exceeds limit (5000 chars). Please reduce number or length of URLs."
                )
        return v

# Migration: ALTER TABLE tasks ALTER COLUMN document_links TYPE VARCHAR(5000);
```

### Solution 2: Move to TEXT Column (Unlimited)
**Pros:**
- No length limit
- Future-proof

**Cons:**
- Can't create index on TEXT columns (some databases)
- Unlimited growth could cause issues
- Still need reasonable limit for UX

**Effort:** Medium (2 hours)
**Risk:** Low

### Solution 3: Separate Links Table (Proper Normalization)
**Pros:**
- No length limits
- Proper database design
- Each link indexed individually
- Can add metadata (title, preview, etc.)

**Cons:**
- Significant refactor
- More complex queries
- Breaks existing CSV pattern

**Effort:** Large (8+ hours)
**Risk:** Medium

## Recommended Action

**Implement Solution 1**: Add validation + increase limit to 5000 chars. This is pragmatic and fixes the immediate issue while maintaining the simple CSV/JSON approach.

## Technical Details

**Affected Files:**
- `src/api/schemas.py` - Add `@field_validator` for length checking
- `alembic/versions/` - New migration to increase column size
- `src/models/task.py` - Update `String(1000)` → `String(5000)`
- `tests/` - Add length validation tests

**Database Migration:**
```sql
-- PostgreSQL
ALTER TABLE tasks ALTER COLUMN document_links TYPE VARCHAR(5000);

-- SQLite (requires table rebuild)
-- Handle in Alembic with op.alter_column()
```

**Validation Logic:**
```python
# Calculate actual storage size
if document_links:
    # After JSON migration (Issue #001), check JSON length
    serialized = json.dumps([str(url) for url in document_links])
    if len(serialized) > 5000:
        raise ValueError("Total links exceed 5000 character limit")

    # Also limit number of links for UX
    if len(document_links) > 20:
        raise ValueError("Maximum 20 document links per task")
```

## Acceptance Criteria

- [ ] API validates total serialized length before database insert
- [ ] Clear error message when limit exceeded: "Total document links exceed X character limit"
- [ ] Database column size increased to 5000 (or TEXT)
- [ ] Tests verify:
  - 10 typical URLs (150 chars each) = ~1500 chars ✓
  - 20 long URLs (300 chars each) = ~6000 chars ✗ (rejected with error)
  - Single very long URL (6000 chars) ✗ (rejected with error)
- [ ] Migration tested on PostgreSQL (not just SQLite)
- [ ] Existing data unaffected by migration

## Work Log

### 2026-02-11 - Issue Identified
- Multi-agent data integrity review found missing length validation
- Confirmed SQLite doesn't enforce String(1000) limit
- Calculated realistic URL counts: 1000 chars ≈ 3-5 typical Google Docs URLs
- Prioritized as P1 (production failure risk)

## Resources

- **PR:** #2 - feat: Add external document links to tasks
- **SQLAlchemy Docs:** [Column Types](https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.String)
- **Database Compatibility:** SQLite vs PostgreSQL vs MySQL string length handling
- **Dependencies:** Should be fixed after Issue #001 (JSON migration)
- **Typical URL Lengths:**
  - Google Docs: 80-150 chars
  - Notion: 60-180 chars
  - GitHub PR: 40-80 chars
  - Confluence: 100-200 chars
