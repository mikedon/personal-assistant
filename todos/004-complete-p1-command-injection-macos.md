---
status: pending
priority: p1
issue_id: "004"
tags: [code-review, security, macos, command-injection]
dependencies: []
---

# Command Injection via subprocess.Popen in macOS Menu Bar

## Problem Statement

The macOS menu bar app uses `subprocess.Popen` with string interpolation of `api_url`, which could enable command injection if the URL is user-controlled or comes from an untrusted configuration source.

**Why This Matters:** If `api_url` can be influenced by config or API response, an attacker could inject shell commands that execute with the user's privileges.

## Findings

### Security Review Agent
- **Severity:** HIGH
- **Location:** `src/macos/menu_app.py:353`
- **Risk:** Command injection via malicious URL in config
- **Evidence:**
  ```python
  def open_dashboard(self, sender: Any = None) -> None:
      """Open the dashboard in a browser."""
      import subprocess
      subprocess.Popen(["open", f"{self.api_url}/docs"])
  ```
- **Example Attack:** `api_url = "http://evil.com; rm -rf / #"` → `subprocess.Popen(["open", "http://evil.com; rm -rf / #/docs"])`

## Proposed Solutions

### Solution 1: Use webbrowser.open() (RECOMMENDED)
**Pros:**
- Cross-platform standard library
- No subprocess or shell involvement
- Properly handles URL escaping
- Safer by design

**Cons:**
- None (this is best practice)

**Effort:** Trivial (5 minutes)
**Risk:** None

**Implementation:**
```python
def open_dashboard(self, sender: Any = None) -> None:
    """Open the dashboard in a browser."""
    import webbrowser
    webbrowser.open(f"{self.api_url}/docs")
```

### Solution 2: Validate api_url Before Use
**Pros:**
- Defense in depth
- Catches malicious URLs early

**Cons:**
- Still using subprocess (unnecessary)
- More complex

**Effort:** Small (30 minutes)
**Risk:** Low

**Implementation:**
```python
import urllib.parse

def open_dashboard(self, sender: Any = None) -> None:
    """Open the dashboard in a browser."""
    # Validate URL format
    parsed = urllib.parse.urlparse(self.api_url)
    if parsed.scheme not in ['http', 'https']:
        print(f"Invalid API URL scheme: {parsed.scheme}")
        return

    import webbrowser
    webbrowser.open(f"{self.api_url}/docs")
```

### Solution 3: Validate api_url in configure() Method
**Pros:**
- Fails fast at startup
- Prevents invalid config

**Cons:**
- Doesn't prevent runtime changes
- Still should use webbrowser

**Effort:** Small (30 minutes)
**Risk:** Low

## Recommended Action

**Implement Solution 1** (use `webbrowser.open()`). This is a simple, safe, cross-platform solution that eliminates the vulnerability entirely. Optionally add Solution 3 for defense in depth.

## Technical Details

**Affected Files:**
- `src/macos/menu_app.py:353` - Replace subprocess with webbrowser
- `src/macos/menu_app.py:~150` (configure method) - Add URL validation

**Code Changes:**
```python
# Current (vulnerable)
import subprocess
subprocess.Popen(["open", f"{self.api_url}/docs"])

# Fixed (safe)
import webbrowser
webbrowser.open(f"{self.api_url}/docs")
```

**Additional Hardening (optional):**
```python
def configure(self):
    """Load configuration from file."""
    # ... existing code ...

    # Validate api_url format
    import urllib.parse
    parsed = urllib.parse.urlparse(self.api_url)
    if not parsed.scheme or not parsed.netloc:
        print(f"Invalid API URL in config: {self.api_url}")
        self.api_url = "http://localhost:8000"  # Fallback to safe default
```

**Attack Surface Analysis:**
- **api_url source:** config.yaml file (`api.url` setting)
- **User control:** User edits config.yaml (trusted input in single-user app)
- **Risk:** Low for single-user desktop app, but still best practice to fix

## Acceptance Criteria

- [ ] Replace `subprocess.Popen` with `webbrowser.open()`
- [ ] Verify "Open Dashboard" menu item still works
- [ ] Test with various api_url values:
  - `http://localhost:8000` ✓
  - `http://192.168.1.100:8000` ✓
  - `https://api.example.com` ✓
- [ ] (Optional) Add URL validation in configure()
- [ ] No regression in menu bar functionality

## Work Log

### 2026-02-11 - Issue Identified
- Security review agent identified subprocess command injection risk
- Analyzed attack surface: api_url comes from config.yaml
- Risk assessment: Low for single-user app, but easy fix
- Prioritized as P1 (security vulnerability with trivial fix)

## Resources

- **PR:** #2 - feat: Add external document links to tasks
- **Python Docs:** [webbrowser module](https://docs.python.org/3/library/webbrowser.html)
- **OWASP:** [Command Injection](https://owasp.org/www-community/attacks/Command_Injection)
- **Best Practice:** Never use subprocess for opening URLs
- **Similar Issues:** Check other subprocess.Popen calls in codebase
