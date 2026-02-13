---
status: pending
priority: p1
issue_id: 001
tags:
  - security
  - granola
  - code-review
  - windows
dependencies: []
---

# Path Traversal Risk via APPDATA Environment Variable

## Problem Statement

The Granola integration uses `os.environ.get("APPDATA", "")` on Windows without validation, creating a path traversal vulnerability. If the `APPDATA` environment variable is missing, maliciously set, or contains path traversal sequences, this could result in unauthorized file system access.

**Why This Matters:**
- **Security Risk**: Attacker with environment control could redirect cache path to read sensitive files
- **Production Impact**: Empty APPDATA would cause relative path resolution from CWD
- **Platform Specific**: Only affects Windows systems

## Findings

**Location:** `/Users/miked/workspace/personal-assistant/src/integrations/granola_integration.py:35`

**Current Code:**
```python
"win32": Path(os.environ.get("APPDATA", "")) / "Granola/cache-v3.json",
```

**Exploitation Scenario:**
```bash
export APPDATA="../../etc"
# Could access /etc/Granola/cache-v3.json or other unintended paths
```

**From Security Review:**
- If `APPDATA` is empty → relative path from CWD
- If `APPDATA` contains `../` → path traversal
- If `APPDATA` points to attacker-controlled location → data exfiltration risk

## Proposed Solutions

### Solution 1: Validate and Normalize APPDATA (Recommended)
```python
# In _get_cache_path() method
appdata = os.environ.get("APPDATA")
if platform == "win32":
    if not appdata or not Path(appdata).is_absolute():
        raise ValueError(
            "APPDATA environment variable not set or invalid. "
            "This is required on Windows for Granola cache access."
        )
    cache_path = Path(appdata).resolve() / "Granola/cache-v3.json"
else:
    cache_path = self.CACHE_PATHS.get(platform)
```

**Pros:**
- Prevents path traversal with `.resolve()`
- Clear error message for users
- Validates absolute path requirement

**Cons:**
- Slightly more verbose

**Effort:** Small (15 minutes)
**Risk:** Low (defensive validation)

### Solution 2: Use Default Windows Path
```python
from pathlib import Path
import os

"win32": Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "Granola/cache-v3.json",
```

**Pros:**
- Fallback to standard location
- More user-friendly

**Cons:**
- May not work in all Windows configurations
- Hides misconfiguration issues

**Effort:** Small (5 minutes)
**Risk:** Medium (silent fallback)

### Solution 3: Strict Validation with No Defaults
```python
if platform == "win32":
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise EnvironmentError("APPDATA environment variable is required on Windows")
    cache_path = Path(appdata).resolve()
    if not cache_path.is_absolute():
        raise ValueError(f"APPDATA must be absolute path, got: {appdata}")
    return cache_path / "Granola/cache-v3.json"
```

**Pros:**
- Most secure
- Fails fast on misconfiguration

**Cons:**
- Strictest approach may break edge cases

**Effort:** Small (20 minutes)
**Risk:** Low

## Recommended Action

**Implement Solution 1** - Validate and normalize with clear error messages. This balances security, user experience, and maintainability.

## Technical Details

**Affected Files:**
- `src/integrations/granola_integration.py` (line 35, method `_get_cache_path`)

**Security Impact:**
- **Attack Surface**: Local environment manipulation
- **Exploitability**: Low (requires environment access)
- **Impact**: High (unauthorized file access)
- **Risk Score**: P1 (High)

**Testing Requirements:**
- Test with empty APPDATA
- Test with relative path in APPDATA
- Test with path traversal sequences (`../`, `..\\`)
- Test on actual Windows system

## Acceptance Criteria

- [ ] APPDATA validation added to `_get_cache_path()`
- [ ] Empty APPDATA raises clear error
- [ ] Non-absolute paths raise error
- [ ] Path normalized with `.resolve()` to prevent traversal
- [ ] Unit test added for empty APPDATA case
- [ ] Unit test added for relative path case
- [ ] Error message guides user to fix

## Work Log

**2026-02-11:**
- Issue identified during security review
- Confirmed Windows-specific vulnerability
- Documented exploitation scenario

## Resources

- **Review Finding**: Security Sentinel Review - Finding #1
- **PR**: https://github.com/mikedon/personal-assistant/pull/3
- **Related Pattern**: Gmail integration handles credentials.json path validation similarly
- **Python Docs**: https://docs.python.org/3/library/pathlib.html#pathlib.Path.resolve
