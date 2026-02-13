---
status: pending
priority: p2
issue_id: 006
tags:
  - architecture
  - error-handling
  - granola
  - code-review
  - pattern-consistency
dependencies: []
---

# Missing PollError Exception in poll() Method

## Problem Statement

The `poll()` method catches generic `Exception` and returns an empty list instead of raising `PollError` like Gmail and Slack integrations. This breaks the established error handling contract where `IntegrationManager` expects exceptions to be propagated for proper logging and handling.

**Why This Matters:**
- **Breaks Pattern Consistency**: Gmail/Slack raise `PollError`, Granola silently fails
- **Error Visibility**: Silent failures make debugging production issues difficult
- **Contract Violation**: Manager expects exceptions for error handling
- **Masking Bugs**: Programming errors (KeyError, AttributeError) are hidden

## Findings

**Location:** `/Users/miked/workspace/personal-assistant/src/integrations/granola_integration.py:95-121`

**Current Code (Granola):**
```python
async def poll(self) -> list[ActionableItem]:
    try:
        notes = self._read_cache()
        new_notes = self._filter_new_notes(notes)
        # ... extract items ...
        return items
    except Exception as e:
        logger.error(f"Error polling Granola: {e}")
        return []  # ❌ Silent failure
```

**Gmail Pattern (src/integrations/gmail_integration.py:224-227):**
```python
except HttpError as e:
    raise PollError(f"Failed to poll Gmail: {e}")
except Exception as e:
    raise PollError(f"Unexpected error polling Gmail: {e}")
```

**Slack Pattern (src/integrations/slack_integration.py:117-120):**
```python
except SlackApiError as e:
    raise PollError(f"Failed to poll Slack: {e}")
except Exception as e:
    raise PollError(f"Unexpected error polling Slack: {e}")
```

**From Pattern Review:**
- Gmail/Slack raise `PollError` for all failures
- `IntegrationManager.poll_all()` expects exceptions (lines 185-186)
- Manager logs exceptions properly and continues with other integrations
- Returning empty list bypasses error handling infrastructure

**From Architecture Review:**
- Violates integration contract
- Breaks error handling abstraction
- Makes debugging production issues difficult

## Proposed Solutions

### Solution 1: Raise PollError for Expected Errors (Recommended)
**Distinguish between expected and unexpected failures:**

```python
from src.integrations.base import PollError

async def poll(self) -> list[ActionableItem]:
    """Poll for new meeting notes from local cache."""
    try:
        notes = self._read_cache()
        new_notes = self._filter_new_notes(notes)

        items = []
        for note in new_notes:
            item = self._extract_actionable_item(note)
            if item:
                items.append(item)

        self._update_last_poll()
        logger.info(
            f"Polled Granola workspace '{self.workspace_id}': "
            f"{len(items)} actionable items from {len(new_notes)} new notes"
        )

        return items

    except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
        # Expected errors - cache file issues
        raise PollError(f"Failed to read Granola cache: {e}")

    except Exception as e:
        # Unexpected errors - programming bugs, database issues
        logger.error(f"Unexpected error polling Granola: {e}", exc_info=True)
        raise PollError(f"Unexpected error polling Granola: {e}")
```

**Pros:**
- Matches Gmail/Slack pattern exactly
- Distinguishes expected vs unexpected errors
- Provides full stack trace for unexpected errors (exc_info=True)
- Integrates properly with manager's error handling

**Cons:**
- None - this is the correct pattern

**Effort:** Small (15 minutes)
**Risk:** Low

### Solution 2: Return Empty List for Expected Errors Only
**Only catch file system errors:**

```python
async def poll(self) -> list[ActionableItem]:
    try:
        notes = self._read_cache()
        # ... rest of logic ...
        return items
    except (FileNotFoundError, json.JSONDecodeError) as e:
        # Cache unavailable - expected condition
        logger.warning(f"Granola cache unavailable: {e}")
        return []
    # Let all other exceptions propagate
```

**Pros:**
- Differentiates availability errors from bugs
- Still allows manager to handle programming errors

**Cons:**
- Inconsistent with Gmail/Slack pattern
- Manager doesn't expect empty list for "cache not found"

**Effort:** Small (10 minutes)
**Risk:** Medium (pattern deviation)

### Solution 3: Wrap All Errors in PollError
**Simplest approach - match pattern exactly:**

```python
async def poll(self) -> list[ActionableItem]:
    try:
        # ... all polling logic ...
        return items
    except Exception as e:
        raise PollError(f"Failed to poll Granola: {e}")
```

**Pros:**
- Simplest solution
- Matches Gmail/Slack

**Cons:**
- Loses distinction between error types
- Less informative error messages

**Effort:** Small (5 minutes)
**Risk:** Low

## Recommended Action

**Implement Solution 1** - Distinguish expected from unexpected errors with clear error messages and full logging. This provides the best debugging experience while maintaining pattern consistency.

## Technical Details

**Affected Files:**
- `src/integrations/granola_integration.py` (poll method, lines 95-121)

**Error Handling Flow:**
```
GranolaIntegration.poll()
    ↓ raises PollError
IntegrationManager.poll_all()
    ↓ catches exception, logs it
    ↓ continues with next integration
AutonomousAgent.poll_cycle()
    ↓ receives results from manager
```

**Expected Errors:**
- `FileNotFoundError`: Cache file doesn't exist (Granola not installed/synced)
- `json.JSONDecodeError`: Cache file corrupted
- `PermissionError`: Can't read cache file
- `KeyError`: Cache structure changed (Granola API update)

**Unexpected Errors:**
- `AttributeError`: Programming bug
- `TypeError`: Programming bug
- `DatabaseError`: Database connection issue in _filter_new_notes

## Acceptance Criteria

- [ ] Import `PollError` from `src.integrations.base`
- [ ] Catch expected errors (file system, JSON) specifically
- [ ] Raise `PollError` with descriptive message for expected errors
- [ ] Catch all other exceptions and raise `PollError` with full logging
- [ ] Add `exc_info=True` to logger for unexpected errors
- [ ] Update unit tests to expect `PollError` instead of empty list
- [ ] Add integration test: manager handles PollError correctly
- [ ] Verify error appears in agent logs when cache unavailable

## Work Log

**2026-02-11:**
- Issue identified during pattern review
- Compared with Gmail/Slack implementations
- Confirmed IntegrationManager expects exceptions
- Documented solution matching existing patterns

## Resources

- **Review Finding**: Pattern Recognition Review - P2 Issue
- **PR**: https://github.com/mikedon/personal-assistant/pull/3
- **Gmail Pattern**: `src/integrations/gmail_integration.py` lines 224-227
- **Slack Pattern**: `src/integrations/slack_integration.py` lines 117-120
- **Manager Code**: `src/integrations/manager.py` lines 185-186 (exception handling)
- **Base Exception**: `src/integrations/base.py` (`PollError` definition)
