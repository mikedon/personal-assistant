---
status: pending
priority: p2
issue_id: "007"
tags: [code-review, security, sql, filtering]
dependencies: []
---

# SQL Injection Risk in CONTAINS Filter

## Problem Statement

The document_links filtering uses SQLAlchemy's `contains()` method for substring matching without explicit escaping of SQL wildcards (`%`, `_`). While SQLAlchemy should handle escaping, this could lead to logic bypasses or performance issues.

**Why This Matters:** Unescaped wildcards can match unintended records or cause slow queries. Could be exploited for DoS or information disclosure.

## Findings

### Security Review Agent
- **Severity:** HIGH (Security)
- **Location:** `src/services/task_service.py:88-91`
- **Risk:** SQL injection, performance degradation, logic bypasses

### Data Integrity Guardian
- **Severity:** HIGH
- **Issue:** False positives - searching "work" matches "https://example.com/doc?tags=work,urgent"

**Evidence:**
```python
if document_links:
    link_conditions = [Task.document_links.contains(link) for link in document_links]
    query = query.filter(or_(*link_conditions))
```

## Proposed Solutions

### Solution 1: Explicit Wildcard Escaping
**Pros:**
- Prevents SQL wildcard injection
- Maintains substring matching
- Low impact change

**Cons:**
- Still does substring matching (may not be desired)

**Effort:** Small (30 minutes)
**Risk:** Low

**Implementation:**
```python
if document_links:
    link_conditions = []
    for link in document_links:
        # Escape SQL wildcards
        escaped_link = link.replace('%', '\\%').replace('_', '\\_')
        link_conditions.append(Task.document_links.contains(escaped_link))
    query = query.filter(or_(*link_conditions))
```

### Solution 2: Exact URL Matching (RECOMMENDED after JSON migration)
**Pros:**
- Most accurate
- No false positives
- Works well with JSON storage

**Cons:**
- Requires JSON storage (Issue #001)
- Less flexible than substring

**Effort:** Medium (depends on #001)
**Risk:** Low

**Implementation:**
```python
from sqlalchemy import func

if document_links:
    # After JSON migration
    link_conditions = [
        func.json_contains(Task.document_links, json.dumps(link))
        for link in document_links
    ]
    query = query.filter(or_(*link_conditions))
```

### Solution 3: Document Substring Behavior
**Pros:**
- No code changes
- Substring matching is feature, not bug

**Cons:**
- Still has false positive risk
- No wildcard protection

**Effort:** Trivial (5 minutes - add comment)
**Risk:** None

## Recommended Action

**Implement Solution 1** as immediate fix, then migrate to **Solution 2** after JSON storage migration (Issue #001).

## Technical Details

**Affected Files:**
- `src/services/task_service.py:88-91` - Add wildcard escaping

**Test Cases:**
```python
def test_document_links_filter_escapes_wildcards():
    """Wildcard characters should be escaped."""
    # Create task with URL containing underscore
    service.create_task(title="Task", document_links=["https://example.com/doc_123"])

    # Search with wildcard should NOT match all
    tasks, total = service.get_tasks(document_links=["%"])
    assert total == 0  # Should not match everything
```

## Acceptance Criteria

- [ ] SQL wildcards (`%`, `_`) escaped in filter
- [ ] Tests verify wildcard escaping
- [ ] No false positive matches
- [ ] Performance acceptable (<100ms for 1000 tasks)

## Resources

- **PR:** #2
- **SQLAlchemy Security:** [SQL Injection Prevention](https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.literal)
- **Dependency:** Issue #001 (JSON migration)
