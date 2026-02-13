---
status: pending
priority: p1
issue_id: "002"
tags: [code-review, security, validation, critical]
dependencies: []
---

# No URL Validation or Sanitization

## Problem Statement

The application accepts arbitrary strings as document links without validating they are legitimate URLs. No checks for protocol, domain validity, or dangerous schemes exist at any layer (API, service, or model).

**Why This Matters:** Attackers could store malicious URLs (`javascript:`, `file://`, etc.) that could lead to XSS, local file access, or SSRF vulnerabilities if links are ever rendered in browsers or fetched by servers.

## Findings

### Security Review Agent
- **Severity:** HIGH
- **Location:** `src/api/schemas.py:20`, `src/services/task_service.py:217`
- **Risk:** SSRF, XSS via javascript: URLs, data exfiltration, local file access
- **Evidence:**
  ```python
  # schemas.py:20 - No validation
  document_links: list[str] = Field(default_factory=list, description="External document URLs")
  ```

### Data Integrity Guardian
- **Severity:** HIGH
- **Issue:** Any string accepted as "document link" - `"not-a-url"`, `"javascript:alert(1)"`, `"file:///etc/passwd"`, etc.

### Code Quality Review
- **Severity:** HIGH
- **Missing:** Pydantic `HttpUrl` type validation
- **Impact:** Poor data quality, security risks if rendered in UI

## Proposed Solutions

### Solution 1: Pydantic HttpUrl Validation (RECOMMENDED)
**Pros:**
- Built-in validation from Pydantic
- Automatic protocol checking
- Clear error messages to API consumers
- Prevents malformed URLs at API boundary

**Cons:**
- Strict validation may reject some edge case URLs
- CLI validation needs separate implementation

**Effort:** Small (1 hour)
**Risk:** Low

**Implementation:**
```python
from pydantic import HttpUrl, field_validator

class TaskBase(BaseModel):
    document_links: list[HttpUrl] = Field(
        default_factory=list,
        description="External document URLs (HTTP/HTTPS only)"
    )

    @field_validator('document_links')
    @classmethod
    def validate_protocols(cls, v):
        """Ensure only safe protocols are allowed."""
        for url in v:
            if url.scheme not in ['http', 'https']:
                raise ValueError(f"Only http/https URLs allowed, got: {url.scheme}")
        return v
```

### Solution 2: Custom Validation Function
**Pros:**
- More flexible than Pydantic HttpUrl
- Can allow specific non-HTTP protocols if needed
- Consistent validation across API and CLI

**Cons:**
- Requires maintaining custom validation logic
- More code to test

**Effort:** Medium (2 hours)
**Risk:** Medium (bugs in custom validation)

### Solution 3: URL Allowlist/Blocklist
**Pros:**
- Can restrict to specific domains (docs.google.com, notion.so, etc.)
- Maximum security

**Cons:**
- Too restrictive for general use
- Requires maintaining allowlist

**Effort:** Medium
**Risk:** Low

## Recommended Action

**Implement Solution 1 (Pydantic HttpUrl)** with protocol whitelist. This provides strong validation with minimal code and leverages Pydantic's battle-tested URL parsing.

## Technical Details

**Affected Files:**
- `src/api/schemas.py` - Update `TaskBase.document_links` type
- `src/cli.py` - Add URL validation to `link-add` command
- `tests/unit/test_task_service.py` - Add validation tests
- `tests/integration/test_tasks_api.py` - Add API validation tests

**API Changes:**
- **Breaking Change:** API will now reject invalid URLs with 422 status
- **Client Impact:** Clients sending malformed URLs will get validation errors
- **Migration:** Existing invalid URLs in database should be audited

**Example Error Response:**
```json
{
  "detail": [
    {
      "loc": ["body", "document_links", 0],
      "msg": "invalid or missing URL scheme",
      "type": "value_error.url.scheme"
    }
  ]
}
```

## Acceptance Criteria

- [ ] Only valid HTTP/HTTPS URLs accepted via API
- [ ] `javascript:`, `file:`, `data:` protocols rejected
- [ ] Malformed URLs rejected with clear error messages
- [ ] Empty strings in document_links list rejected
- [ ] CLI `link-add` command validates URL format
- [ ] API returns 422 for invalid URLs
- [ ] Tests cover:
  - Valid HTTP/HTTPS URLs (pass)
  - javascript: URLs (reject)
  - file:// URLs (reject)
  - Malformed URLs (reject)
  - Empty strings (reject)
  - Very long URLs (handle gracefully)

## Work Log

### 2026-02-11 - Issue Identified
- Multi-agent security review identified missing URL validation
- Confirmed XSS and SSRF risks
- Prioritized as P1 (security vulnerability)

## Resources

- **PR:** #2 - feat: Add external document links to tasks
- **Pydantic Docs:** [URL Types](https://docs.pydantic.dev/latest/api/networks/)
- **OWASP:** [Unvalidated Redirects and Forwards](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html)
- **Related:** Issue #001 (CSV injection) should be fixed first
