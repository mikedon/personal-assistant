# Prevention Strategies: Avoiding Critical Security and Quality Issues

**Document Purpose**: This document provides actionable strategies to prevent the types of critical issues identified during the document_links feature code review. It serves as a reference for all future feature development.

**Context**: During the document_links feature review (PR #2), a multi-agent code review identified 6 critical (P1) issues:
1. CSV injection vulnerability
2. Missing URL validation
3. No length validation
4. Command injection via subprocess
5. Missing agent integration
6. Incomplete test coverage

All issues were resolved in commit a0c805f. This document ensures similar issues don't recur.

---

## 1. Prevention Strategies

### 1.1 Security Review Checklist

**Use this checklist before merging any feature that handles user input:**

#### Input Validation
- [ ] **All user inputs validated at API boundary** (Pydantic validators)
- [ ] **CLI inputs validated** (Click validators or custom validation)
- [ ] **Length limits enforced programmatically** (not just database constraints)
- [ ] **Type validation** (strings, URLs, dates, etc.)
- [ ] **Range validation** (numbers, dates within acceptable ranges)

#### Injection Prevention
- [ ] **No CSV storage without JSON encoding** (use JSON for structured data in string columns)
- [ ] **No formula characters in CSV exports** (`=`, `@`, `+`, `-` at start of cell)
- [ ] **No subprocess with user-controlled strings** (use stdlib alternatives)
- [ ] **No string interpolation in SQL** (use parameterized queries only)
- [ ] **URL validation with protocol whitelist** (http/https only for external links)
- [ ] **No javascript:, file://, data: protocols** in user-provided URLs

#### Command Execution Safety
- [ ] **Prefer stdlib over subprocess** (webbrowser.open vs subprocess for URLs)
- [ ] **Never use shell=True** with subprocess
- [ ] **Validate all paths** before filesystem operations
- [ ] **Use pathlib for path operations** (safer than string concatenation)

#### Database Safety
- [ ] **Length limits match database schema** (programmatic validation <= DB column size)
- [ ] **Test on PostgreSQL**, not just SQLite (SQLite ignores length limits)
- [ ] **Migration tested with existing data** (backward compatibility)
- [ ] **No silent truncation** (validation errors instead)

#### External Data Handling
- [ ] **Sanitize data from integrations** (Gmail, Slack, APIs)
- [ ] **Validate before storage** (don't trust external sources)
- [ ] **Log suspicious patterns** (attempted injections, malformed data)

### 1.2 Code Review Process Improvements

**When to Use Multi-Agent Code Review:**
- [ ] New features handling user input (forms, file uploads, API endpoints)
- [ ] Security-sensitive features (auth, file access, external integrations)
- [ ] Database schema changes (migrations, new columns)
- [ ] Features with subprocess/shell execution
- [ ] Integration with external services (APIs, OAuth)

**Reviewer Focus Areas:**

| Review Type | Focus |
|------------|-------|
| **Security Review** | Input validation, injection risks, unsafe operations |
| **Data Integrity** | Length limits, type safety, database constraints |
| **Code Quality** | Test coverage, code patterns, maintainability |
| **Performance** | Database queries, N+1 problems, scalability |
| **Agent-Native** | LLM integration, autonomous operation, extraction gaps |

**Required Approvals:**
- Security-sensitive features: 2+ reviewer sign-offs
- Database migrations: Test on non-SQLite database
- Agent integration: Verify LLM prompt updates

### 1.3 Testing Requirements

**Mandatory Test Types for New Features:**

#### 1. Unit Tests (Service Layer)
```python
# Example: tests/unit/test_task_service.py
def test_create_task_with_document_links(test_db_session):
    """Test service layer handles document links."""
    task = task_service.create_task(
        db=test_db_session,
        title="Test",
        document_links=["https://example.com"]
    )
    assert len(task.get_document_links_list()) == 1
```

**Coverage Requirements:**
- [ ] Happy path (valid inputs)
- [ ] Edge cases (empty, None, max length)
- [ ] Error cases (invalid inputs, database errors)
- [ ] Boundary conditions (min/max values)

#### 2. Integration Tests (API Layer)
```python
# Example: tests/integration/test_tasks_api.py
def test_create_task_with_invalid_url(client):
    """Test API rejects invalid URLs."""
    response = client.post("/api/tasks", json={
        "title": "Test",
        "document_links": ["not-a-url"]
    })
    assert response.status_code == 422
```

**Coverage Requirements:**
- [ ] All CRUD operations (create, read, update, delete)
- [ ] Query parameters and filtering
- [ ] Validation errors (400/422 responses)
- [ ] Authentication/authorization (if applicable)
- [ ] Pagination and sorting

#### 3. Edge Case Tests
```python
# Example: tests/unit/test_task_model.py
def test_document_links_with_commas():
    """Test URLs with commas don't corrupt data."""
    url = "https://example.com?tags=work,urgent"
    task.set_document_links_list([url])
    retrieved = task.get_document_links_list()
    assert retrieved[0] == url  # No corruption
```

**Required Edge Cases:**
- [ ] Special characters in input (commas, quotes, newlines)
- [ ] Maximum length inputs
- [ ] Empty collections ([], None, "")
- [ ] Malicious inputs (injection attempts)
- [ ] Concurrent operations (race conditions)

#### 4. Security Tests
```python
def test_rejects_javascript_urls(client):
    """Test XSS protection via protocol validation."""
    response = client.post("/api/tasks", json={
        "title": "Test",
        "document_links": ["javascript:alert('xss')"]
    })
    assert response.status_code == 422
    assert "scheme" in str(response.json())
```

**Required Security Tests:**
- [ ] Injection attempts (SQL, CSV, command)
- [ ] Protocol violations (javascript:, file://)
- [ ] Path traversal attempts (../, /etc/passwd)
- [ ] Length overflow attacks
- [ ] Invalid character encoding

### 1.4 Documentation Requirements

**Before Merging Any Feature:**

1. **Update README.md**
   - [ ] Add feature to features list
   - [ ] Update CLI usage examples
   - [ ] Update API endpoint documentation

2. **Update CLAUDE.md**
   - [ ] Add architectural patterns used
   - [ ] Document new service/integration patterns
   - [ ] Update test examples if new patterns introduced

3. **Create Migration Notes** (if applicable)
   - [ ] Document breaking changes
   - [ ] Provide upgrade path
   - [ ] List database migrations required

4. **Add Code Comments**
   - [ ] Security-sensitive code (why it's safe)
   - [ ] Complex validation logic (what it checks)
   - [ ] Performance optimizations (why this approach)

---

## 2. Best Practices

### 2.1 Data Storage Patterns

#### When to Use JSON vs CSV in String Columns

**Use JSON when:**
- Structured data with potential special characters (URLs, names with commas)
- Need to add metadata in future (e.g., `{"url": "...", "title": "..."}`)
- Data contains commas, quotes, or newlines
- Forward compatibility is important

**Use CSV when:**
- Simple tag lists with controlled vocabulary (no special chars)
- Human readability in database is critical
- Backward compatibility with existing CSV required

**Pattern:**
```python
import json

# JSON storage (recommended for complex data)
def set_document_links_list(self, links: list[str]) -> None:
    """Store links as JSON array."""
    self.document_links = json.dumps(links) if links else None

def get_document_links_list(self) -> list[str]:
    """Retrieve links from JSON, with CSV fallback for legacy data."""
    if not self.document_links:
        return []
    try:
        return json.loads(self.document_links)
    except json.JSONDecodeError:
        # Fallback for legacy CSV format
        return [link.strip() for link in self.document_links.split(",") if link.strip()]
```

**Key Points:**
- Always include fallback for backward compatibility
- Validate on read, not just write
- Use try/except for robust error handling

### 2.2 URL Validation Best Practices

**Pattern: Pydantic HttpUrl with Protocol Whitelist**
```python
from pydantic import BaseModel, Field, HttpUrl, field_validator

class TaskBase(BaseModel):
    document_links: list[HttpUrl] = Field(
        default_factory=list,
        description="External document URLs (HTTP/HTTPS only)",
        max_length=20
    )

    @field_validator('document_links')
    @classmethod
    def validate_protocols(cls, v):
        """Enforce safe protocols only."""
        for url in v:
            if url.scheme not in ['http', 'https']:
                raise ValueError(f"Only http/https URLs allowed, got: {url.scheme}")
        return v
```

**Dangerous Protocols to Block:**
- `javascript:` - XSS attacks
- `file://` - Local file access
- `data:` - Embedded data (can be used for phishing)
- `ftp://` - Uncommon, may indicate attack
- `tel:` / `mailto:` - Usually not needed in document links

**When to Allow Additional Protocols:**
- Document use case explicitly requires it (e.g., `mailto:` for contact links)
- Add to whitelist explicitly, never just "allow all"
- Document security implications in code comments

### 2.3 Subprocess Safety

**Never Do This:**
```python
# DANGEROUS: Command injection risk
import subprocess
url = config.get("api_url")  # User-controlled
subprocess.Popen(["open", f"{url}/docs"])  # url can contain "; rm -rf /"
```

**Do This Instead:**
```python
# SAFE: Use standard library alternatives
import webbrowser
url = config.get("api_url")
webbrowser.open(f"{url}/docs")  # No shell involvement
```

**Safe Alternatives to Subprocess:**
| Task | Bad (subprocess) | Good (stdlib) |
|------|-----------------|---------------|
| Open URL | `subprocess.Popen(["open", url])` | `webbrowser.open(url)` |
| Read file | `subprocess.check_output(["cat", path])` | `pathlib.Path(path).read_text()` |
| Write file | `subprocess.run(["echo", data, ">", path])` | `pathlib.Path(path).write_text(data)` |
| HTTP request | `subprocess.run(["curl", url])` | `requests.get(url)` or `httpx.get(url)` |

**If Subprocess is Unavoidable:**
- Use `shell=False` (default)
- Pass arguments as list, never concatenate strings
- Validate all inputs with strict whitelist
- Use `shlex.quote()` for shell escaping (last resort)

### 2.4 Agent Integration Checklist

**Making Features Agent-Accessible:**

When adding a feature that should work autonomously:

1. **Update Data Models**
   ```python
   # src/integrations/base.py
   @dataclass
   class ActionableItem:
       # ... existing fields ...
       document_links: list[str] | None = None  # ADD THIS
   ```

2. **Update LLM Service**
   ```python
   # src/services/llm_service.py
   @dataclass
   class ExtractedTask:
       # ... existing fields ...
       document_links: list[str] | None = None  # ADD THIS
   ```

3. **Update LLM Prompts**
   ```python
   # src/services/llm_service.py - extract_tasks_from_text()
   system_prompt = """
   Extract actionable tasks with:
   - title, description, priority, due_date
   - document_links: Array of URLs mentioned (Google Docs, Notion, GitHub, etc.)
   """
   ```

4. **Update Agent Logic**
   ```python
   # src/agent/core.py - _create_task_from_extracted()
   task = task_service.create_task(
       # ... existing params ...
       document_links=extracted.document_links or [],  # PASS THIS
   )
   ```

5. **Test Agent Extraction**
   ```python
   # tests/integration/test_agent_core.py
   def test_agent_extracts_document_links_from_email():
       """Test agent automatically extracts URLs from emails."""
       # Test implementation
   ```

**Verification:**
- Agent logs show extracted data: `SELECT * FROM agent_logs WHERE action = 'TASK_CREATED'`
- Test with real-world examples: email with Google Docs link
- Check all integration sources: Gmail, Slack, Voice

### 2.5 Length Validation Pattern

**Problem:** Database column limits (e.g., `String(1000)`) are not enforced in SQLite (dev) but cause errors in PostgreSQL/MySQL (prod).

**Solution: Validate Before Database**
```python
from pydantic import field_validator

class TaskBase(BaseModel):
    document_links: list[HttpUrl] = Field(max_length=20)

    @field_validator('document_links')
    @classmethod
    def validate_total_length(cls, v):
        """Ensure serialized data fits in database column."""
        if v:
            import json
            serialized = json.dumps([str(url) for url in v])
            if len(serialized) > 5000:  # Match DB column size
                raise ValueError(
                    f"Total length ({len(serialized)} chars) exceeds "
                    f"database limit (5000 chars). Reduce URL count."
                )
        return v
```

**Key Points:**
- Calculate serialized length (JSON, not Python list)
- Leave headroom (validate to 5000 if DB is 5000, but consider 4500 safer)
- Provide actionable error message (user knows what to fix)
- Test on PostgreSQL, not just SQLite

### 2.6 Backward Compatibility Pattern

**When changing data formats (CSV → JSON):**

1. **Add Fallback in Read Method**
   ```python
   def get_document_links_list(self) -> list[str]:
       if not self.document_links:
           return []
       try:
           # Try new format first
           return json.loads(self.document_links)
       except json.JSONDecodeError:
           # Fall back to legacy format
           return [link.strip() for link in self.document_links.split(",")]
   ```

2. **Create Data Migration**
   ```python
   # alembic/versions/xxx_migrate_csv_to_json.py
   def upgrade():
       # Convert existing CSV data to JSON
       connection = op.get_bind()
       result = connection.execute(text(
           "SELECT id, document_links FROM tasks WHERE document_links IS NOT NULL"
       ))
       for row in result:
           csv_links = row.document_links.split(",")
           json_links = json.dumps([link.strip() for link in csv_links if link.strip()])
           connection.execute(
               text("UPDATE tasks SET document_links = :json WHERE id = :id"),
               {"json": json_links, "id": row.id}
           )
   ```

3. **Test Both Formats**
   ```python
   def test_backward_compatibility_csv_format():
       """Test legacy CSV data still readable."""
       task.document_links = "https://a.com,https://b.com"  # Old format
       links = task.get_document_links_list()
       assert len(links) == 2
   ```

---

## 3. Testing Checklist for Similar Features

Use this checklist when adding features that handle user input or external data:

### 3.1 Validation Tests

**Required for ALL Input Fields:**
- [ ] Valid input (happy path)
- [ ] Empty input (None, "", [])
- [ ] Maximum length input
- [ ] Input exceeding max length (should reject)
- [ ] Invalid format (wrong type, malformed)
- [ ] Special characters (commas, quotes, newlines)
- [ ] Unicode characters (emoji, non-ASCII)

**Example Test Names:**
```python
test_create_with_valid_urls()
test_create_with_empty_list()
test_create_with_max_length_urls()
test_create_with_too_many_urls()  # Exceeds limit
test_create_with_invalid_url_format()
test_create_with_javascript_url()  # Security
test_create_with_commas_in_url()  # Edge case
```

### 3.2 API Tests

**Required for ALL Endpoints:**
- [ ] Create with new field (POST)
- [ ] Read with new field (GET)
- [ ] Update existing record (PUT/PATCH)
- [ ] Delete record (if applicable)
- [ ] List/filter by new field (GET with query params)
- [ ] Pagination includes new field
- [ ] Validation errors return 422
- [ ] Schema matches response

**Example Test Structure:**
```python
def test_create_task_with_document_links(client, sample_task_data):
    """POST /api/tasks with document_links"""
    response = client.post("/api/tasks", json={
        **sample_task_data,
        "document_links": ["https://example.com"]
    })
    assert response.status_code == 201
    assert "document_links" in response.json()

def test_filter_tasks_by_document_link(client):
    """GET /api/tasks?document_links=example.com"""
    # Create tasks
    # Filter
    # Assert results
```

### 3.3 Security Tests

**Required for Security-Sensitive Features:**
- [ ] Injection attempts (SQL, CSV, command)
- [ ] Path traversal (../, /etc/passwd)
- [ ] Protocol violations (javascript:, file://)
- [ ] Malicious payloads (XSS, CSRF tokens)
- [ ] Oversized inputs (DoS via memory)
- [ ] Invalid encoding (UTF-8 violations)

**Example Tests:**
```python
def test_rejects_csv_injection():
    """Test CSV formula injection blocked."""
    task = task_service.create_task(
        title="=cmd|'/c calc'!A1",  # CSV injection
        ...
    )
    # Verify sanitization or rejection

def test_rejects_javascript_url():
    """Test XSS protection."""
    with pytest.raises(ValidationError):
        TaskBase(document_links=["javascript:alert('xss')"])

def test_rejects_file_url():
    """Test local file access blocked."""
    with pytest.raises(ValidationError):
        TaskBase(document_links=["file:///etc/passwd"])
```

### 3.4 Edge Case Tests

**Required for Data Integrity:**
- [ ] Boundary values (0, max, max+1)
- [ ] Special characters in data
- [ ] Concurrent updates
- [ ] Duplicate entries
- [ ] Null vs empty string
- [ ] Database transaction rollback

**Example Edge Cases:**
```python
def test_url_with_comma_in_query_params():
    """URLs with commas don't corrupt data."""
    url = "https://example.com?tags=work,urgent"
    task.set_document_links_list([url])
    assert task.get_document_links_list()[0] == url

def test_very_long_url():
    """Single URL approaching length limit."""
    url = "https://example.com/" + "a" * 4000
    # Should succeed if under limit
    # Should fail with clear error if over

def test_twenty_one_urls():
    """Exceeding max count limit."""
    urls = [f"https://example.com/{i}" for i in range(21)]
    with pytest.raises(ValidationError, match="Maximum 20"):
        TaskBase(document_links=urls)
```

### 3.5 Integration Tests

**Required for Agent Features:**
- [ ] Agent extracts data from email
- [ ] Agent extracts data from Slack
- [ ] LLM prompt includes new field
- [ ] ExtractedTask includes new field
- [ ] Agent creates task with new field
- [ ] Agent logs show new field

**Example:**
```python
def test_agent_extracts_document_links_from_email():
    """Agent autonomously extracts URLs from emails."""
    email_text = """
    Please review this document:
    https://docs.google.com/document/d/abc123
    """

    # Mock LLM response
    mock_llm.return_value = ExtractedTask(
        title="Review document",
        document_links=["https://docs.google.com/document/d/abc123"]
    )

    # Run agent
    agent.poll_integrations()

    # Verify task created with link
    tasks = task_service.list_tasks()
    assert len(tasks[0].get_document_links_list()) == 1
```

### 3.6 Migration Tests

**Required for Database Schema Changes:**
- [ ] Migration applies successfully
- [ ] Existing data preserved
- [ ] Backward compatibility maintained
- [ ] Rollback works correctly
- [ ] Test on PostgreSQL (not just SQLite)

**Example:**
```python
def test_migration_converts_csv_to_json():
    """Test data migration from CSV to JSON format."""
    # Insert legacy CSV data
    connection.execute(
        "INSERT INTO tasks (title, document_links) VALUES (?, ?)",
        ("Test", "https://a.com,https://b.com")
    )

    # Apply migration
    alembic.upgrade("head")

    # Verify JSON format
    task = task_service.get_task(1)
    links = task.get_document_links_list()
    assert links == ["https://a.com", "https://b.com"]
    assert task.document_links.startswith("[")  # JSON array
```

---

## 4. Quick Reference: Security Checklist

Print this and keep at your desk:

```
┌─────────────────────────────────────────────────────────────┐
│ SECURITY CHECKLIST - Before Merging ANY Feature            │
├─────────────────────────────────────────────────────────────┤
│ INPUT VALIDATION                                            │
│  □ All inputs validated at API layer (Pydantic)            │
│  □ Length limits enforced programmatically                 │
│  □ Type validation (URLs, dates, etc.)                     │
│  □ Special character handling (commas, quotes)             │
│                                                             │
│ INJECTION PREVENTION                                        │
│  □ No CSV without JSON encoding                            │
│  □ No subprocess with user strings                         │
│  □ URLs validated with protocol whitelist                  │
│  □ No javascript:, file://, data: protocols                │
│  □ Parameterized SQL queries only                          │
│                                                             │
│ TESTING                                                     │
│  □ Unit tests for service layer                            │
│  □ Integration tests for API                               │
│  □ Security tests (injection attempts)                     │
│  □ Edge cases (empty, max, special chars)                  │
│  □ Agent integration tests (if applicable)                 │
│                                                             │
│ DOCUMENTATION                                               │
│  □ README.md updated                                        │
│  □ CLAUDE.md updated (if patterns changed)                 │
│  □ Code comments for security-sensitive logic              │
│  □ Migration notes (if schema changes)                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Lessons Learned from document_links Review

### What Went Wrong
1. **Feature added without security analysis** - CSV storage chosen without considering injection risks
2. **No validation at boundaries** - API accepted any string as "URL"
3. **SQLite masked production issues** - Length limits ignored in development
4. **Agent integration forgotten** - Feature not designed for autonomous operation
5. **Tests incomplete** - Only happy path tested, no edge cases or security tests

### What Went Right
1. **Multi-agent code review caught all issues** - Different perspectives identified different problems
2. **Structured issue tracking** - Each issue documented with priority, solutions, acceptance criteria
3. **Comprehensive fix** - All issues addressed together with full test coverage
4. **Backward compatibility** - Changes didn't break existing data or APIs
5. **Documentation created** - This document ensures learning is captured

### Key Takeaways
- **Security is not optional** - Even "simple" features need security review
- **Test edge cases early** - Don't wait for code review to find issues
- **Design for the agent** - If humans use it, the agent should too
- **SQLite is not production** - Always test on PostgreSQL or MySQL
- **Validate at boundaries** - API layer is first line of defense

---

## 6. Implementation Timeline

**For Future Features:**

| Phase | Activities | Duration |
|-------|-----------|----------|
| **Design** | Security analysis, data format decisions | 10% of dev time |
| **Development** | Feature implementation with validation | 60% of dev time |
| **Testing** | Unit, integration, security, edge cases | 20% of dev time |
| **Review** | Multi-agent code review if needed | 5% of dev time |
| **Documentation** | README, CLAUDE.md, comments | 5% of dev time |

**Example: 10-hour feature**
- Design/Security: 1 hour
- Development: 6 hours
- Testing: 2 hours
- Review: 0.5 hours
- Documentation: 0.5 hours

**Don't Skip Testing or Security** - They prevent much larger time costs later:
- Security incident response: 40+ hours
- Production data corruption: 20+ hours
- Regression bug fixes: 10+ hours
- Lost customer trust: Immeasurable

---

## 7. Tools and Resources

### Recommended Tools
- **Pydantic**: Input validation (`HttpUrl`, validators)
- **Ruff**: Linting and code quality
- **Pytest**: Comprehensive testing framework
- **Alembic**: Database migrations
- **SQLAlchemy**: ORM with type safety

### Security References
- [OWASP CSV Injection](https://owasp.org/www-community/attacks/CSV_Injection)
- [OWASP Command Injection](https://owasp.org/www-community/attacks/Command_Injection)
- [OWASP Input Validation](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html)
- [Pydantic Security Best Practices](https://docs.pydantic.dev/latest/concepts/validators/)

### Internal Documentation
- `/Users/miked/workspace/personal-assistant/CLAUDE.md` - Architecture patterns
- `/Users/miked/workspace/personal-assistant/docs/ARCHITECTURE.md` - ADL
- `/Users/miked/workspace/personal-assistant/tests/conftest.py` - Test patterns
- `/Users/miked/workspace/personal-assistant/todos/*.md` - Code review findings

---

## 8. Contact and Questions

If you have questions about these prevention strategies:
1. Review the completed issue documents in `/todos/`
2. Check commit a0c805f for implementation examples
3. Review test files for testing patterns
4. Ask during code review if uncertain

**Remember**: It's always better to ask during development than to fix in production.

---

**Document Version**: 1.0
**Last Updated**: 2026-02-11
**Based On**: document_links feature code review (PR #2, commit a0c805f)
**Authors**: Multi-agent code review team + Claude Sonnet 4.5
