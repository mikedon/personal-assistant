---
status: pending
priority: p1
issue_id: 002
tags:
  - security
  - granola
  - code-review
  - privacy
dependencies: []
---

# Insufficient File Permission and Symlink Validation

## Problem Statement

The `authenticate()` method verifies cache file existence and JSON validity but does NOT check file ownership, permissions, or symlink targets. This creates privacy and security risks where attackers could manipulate the filesystem to read sensitive files or leak cache contents.

**Why This Matters:**
- **Privacy Risk**: World-readable cache files expose meeting notes to all users on system
- **Symlink Attack**: Attacker could create symlink to sensitive files (`/etc/passwd`, `.ssh/id_rsa`)
- **File Ownership**: Cache could belong to different user, leaking their data

## Findings

**Location:** `/Users/miked/workspace/personal-assistant/src/integrations/granola_integration.py:73-93`

**Current Code:**
```python
async def authenticate(self) -> bool:
    if not self.cache_path.exists():
        raise AuthenticationError(...)

    with open(self.cache_path) as f:  # ❌ No permission/ownership checks
        data = json.load(f)
```

**Attack Scenarios:**

1. **Symlink Attack:**
```bash
ln -s /etc/passwd ~/Library/Application\ Support/Granola/cache-v3.json
# App attempts to parse passwd file, error messages may leak content
```

2. **World-Readable Cache:**
```bash
chmod 644 ~/Library/Application\ Support/Granola/cache-v3.json
# Any user on system can read meeting notes
```

3. **File Ownership:**
```bash
# Attacker creates cache file owned by their user
# App reads attacker's data instead of legitimate user's data
```

**From Security Review:**
- No symlink detection
- No permission checks (world-readable warning)
- No ownership validation
- Error messages could leak file contents

## Proposed Solutions

### Solution 1: Comprehensive Security Checks (Recommended)
```python
async def authenticate(self) -> bool:
    """Verify cache file exists and is readable with security checks."""
    if not self.cache_path.exists():
        raise AuthenticationError(
            f"Granola cache file not found at {self.cache_path}. "
            "Ensure Granola desktop app is installed and has synced notes."
        )

    # Check if symlink
    if self.cache_path.is_symlink():
        raise AuthenticationError(
            f"Cache file {self.cache_path} is a symbolic link. "
            "For security reasons, symlinks are not allowed."
        )

    # Check file permissions and ownership (Unix-like systems)
    if hasattr(os, 'stat'):
        import stat
        file_stat = self.cache_path.stat()

        # Warn if world-readable
        if file_stat.st_mode & stat.S_IROTH:
            logger.warning(
                f"Cache file {self.cache_path} is world-readable. "
                "Consider setting permissions to 600 for privacy."
            )

        # Verify ownership on Unix systems
        if hasattr(file_stat, 'st_uid') and hasattr(os, 'getuid'):
            if file_stat.st_uid != os.getuid():
                raise AuthenticationError(
                    f"Cache file {self.cache_path} does not belong to current user. "
                    "This could indicate a security issue."
                )

    try:
        with open(self.cache_path) as f:
            data = json.load(f)

        # Verify cache structure
        if "cache" not in data:
            raise AuthenticationError("Invalid cache file structure")

        logger.info(f"Successfully authenticated Granola cache at {self.cache_path}")
        return True

    except (json.JSONDecodeError, PermissionError) as e:
        raise AuthenticationError(f"Failed to read Granola cache: {e}")
```

**Pros:**
- Comprehensive security coverage
- Clear error messages for each failure mode
- Warns about privacy issues (world-readable)
- Works on Unix-like systems (macOS, Linux)

**Cons:**
- More code
- Platform-specific (Unix stat module)

**Effort:** Medium (45 minutes)
**Risk:** Low (defensive checks)

### Solution 2: Basic Symlink Check Only
```python
# Minimal fix - just prevent symlink attacks
if self.cache_path.is_symlink():
    raise AuthenticationError("Cache file cannot be a symbolic link")
```

**Pros:**
- Simple, focused fix
- Prevents primary attack vector

**Cons:**
- Doesn't address permission/ownership issues

**Effort:** Small (10 minutes)
**Risk:** Low

### Solution 3: Strict Mode with Environment Variable
```python
# Add strict security mode controlled by env var
strict_mode = os.environ.get("PA_STRICT_SECURITY", "false").lower() == "true"

if strict_mode:
    # Run all security checks from Solution 1
    pass
else:
    # Run basic checks only
    if self.cache_path.is_symlink():
        raise AuthenticationError(...)
```

**Pros:**
- Configurable security level
- Default behavior unchanged

**Cons:**
- More complex
- Security should be default, not opt-in

**Effort:** Medium (60 minutes)
**Risk:** Medium (complexity)

## Recommended Action

**Implement Solution 1** - Comprehensive security checks with clear logging. Security should be default, and the checks are platform-aware (gracefully skip on Windows if stat unavailable).

## Technical Details

**Affected Files:**
- `src/integrations/granola_integration.py` (lines 73-93, `authenticate()` method)

**Security Impact:**
- **Attack Surface**: Local filesystem manipulation
- **Exploitability**: Low (requires filesystem access)
- **Impact**: Medium (privacy breach, data leakage)
- **Risk Score**: P1 (High - privacy-sensitive meeting notes)

**Platform Support:**
- **macOS**: Full support (stat, ownership checks)
- **Linux**: Full support
- **Windows**: Partial (symlink check works, ownership checks may not)

## Acceptance Criteria

- [ ] Symlink detection added to `authenticate()`
- [ ] File ownership validation on Unix systems
- [ ] World-readable permission warning logged
- [ ] Clear error messages for each failure mode
- [ ] Platform-aware checks (graceful degradation)
- [ ] Unit test: symlink rejection
- [ ] Unit test: wrong owner rejection (Unix)
- [ ] Unit test: warning logged for world-readable
- [ ] Documentation updated with security model

## Work Log

**2026-02-11:**
- Issue identified during security review
- Confirmed multiple attack vectors
- Researched pathlib symlink detection
- Documented comprehensive solution

## Resources

- **Review Finding**: Security Sentinel Review - Finding #2
- **PR**: https://github.com/mikedon/personal-assistant/pull/3
- **Python pathlib docs**: https://docs.python.org/3/library/pathlib.html#pathlib.Path.is_symlink
- **stat module docs**: https://docs.python.org/3/library/stat.html
- **Similar pattern**: Many security-conscious apps validate file ownership (ssh, gpg)
