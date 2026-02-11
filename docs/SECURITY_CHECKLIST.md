# Security & Quality Checklist

**Purpose**: Quick reference checklist for all features handling user input or external data.

**When to Use**: Before starting development, during implementation, and before requesting code review.

---

## Pre-Development Checklist

Before writing any code:

- [ ] **Security Analysis**: Identified all user input points and external data sources
- [ ] **Data Format Decision**: Chosen appropriate storage format (JSON vs CSV, STRING vs TEXT)
- [ ] **Validation Strategy**: Planned validation at all boundaries (API, CLI, service)
- [ ] **Agent Integration**: Considered if feature should be agent-accessible
- [ ] **Test Plan**: Listed required test cases (happy path, edge cases, security)

---

## Development Checklist

While implementing the feature:

### Input Validation

- [ ] **API Layer**: Pydantic validators for all inputs
  ```python
  from pydantic import field_validator, HttpUrl

  @field_validator('field_name')
  @classmethod
  def validate_field(cls, v):
      # Validation logic
      return v
  ```

- [ ] **CLI Layer**: Click parameter validation or custom validation
  ```python
  @click.option('--url', callback=validate_url)
  def command(url):
      pass
  ```

- [ ] **Service Layer**: Defensive checks even if validated upstream
  ```python
  def create_task(title: str, ...):
      if not title or len(title) > 500:
          raise ValueError("Invalid title")
  ```

### Data Storage

- [ ] **Use JSON for structured data in string columns**
  ```python
  import json

  def set_field(self, data: list) -> None:
      self.field = json.dumps(data) if data else None

  def get_field(self) -> list:
      if not self.field:
          return []
      return json.loads(self.field)
  ```

- [ ] **Add CSV fallback for backward compatibility** (if migrating from CSV)
  ```python
  def get_field(self) -> list:
      try:
          return json.loads(self.field)
      except json.JSONDecodeError:
          # Legacy CSV fallback
          return [x.strip() for x in self.field.split(",")]
  ```

- [ ] **Validate serialized length matches database column**
  ```python
  serialized = json.dumps(data)
  if len(serialized) > 5000:  # Match DB column size
      raise ValueError("Data exceeds storage limit")
  ```

### URL Validation

- [ ] **Use Pydantic HttpUrl type**
  ```python
  from pydantic import HttpUrl

  class Schema(BaseModel):
      urls: list[HttpUrl]
  ```

- [ ] **Enforce protocol whitelist** (http/https only)
  ```python
  @field_validator('urls')
  @classmethod
  def validate_protocols(cls, v):
      for url in v:
          if url.scheme not in ['http', 'https']:
              raise ValueError(f"Invalid protocol: {url.scheme}")
      return v
  ```

- [ ] **Block dangerous protocols**
  - `javascript:` (XSS)
  - `file://` (local file access)
  - `data:` (phishing)

### Command Execution Safety

- [ ] **Never use subprocess with user-controlled strings**

- [ ] **Use standard library alternatives**
  | Don't | Do |
  |-------|-----|
  | `subprocess.Popen(["open", url])` | `webbrowser.open(url)` |
  | `subprocess.run(["cat", path])` | `Path(path).read_text()` |
  | `subprocess.run(["curl", url])` | `requests.get(url)` |

- [ ] **If subprocess required**: Use `shell=False`, validate inputs, use list args

### Database Safety

- [ ] **Validate length before database insert** (SQLite doesn't enforce String(N))

- [ ] **Test on PostgreSQL**, not just SQLite

- [ ] **Use parameterized queries** (SQLAlchemy handles this)

- [ ] **Create migration for schema changes**
  ```bash
  alembic revision --autogenerate -m "Description"
  alembic upgrade head
  ```

### Agent Integration

If feature should be agent-accessible:

- [ ] **Update ActionableItem** (src/integrations/base.py)
  ```python
  @dataclass
  class ActionableItem:
      new_field: type | None = None
  ```

- [ ] **Update ExtractedTask** (src/services/llm_service.py)
  ```python
  @dataclass
  class ExtractedTask:
      new_field: type | None = None
  ```

- [ ] **Update LLM prompts** to extract new field
  ```python
  system_prompt = """
  Extract: title, description, new_field
  """
  ```

- [ ] **Update agent task creation** (src/agent/core.py)
  ```python
  task = task_service.create_task(
      ...,
      new_field=extracted.new_field
  )
  ```

---

## Testing Checklist

### Required Test Types

- [ ] **Unit Tests** (tests/unit/test_*_service.py)
  - [ ] Happy path (valid inputs)
  - [ ] Empty/None inputs
  - [ ] Maximum length inputs
  - [ ] Invalid inputs (should raise error)

- [ ] **Integration Tests** (tests/integration/test_*_api.py)
  - [ ] POST (create with new field)
  - [ ] GET (read includes new field)
  - [ ] PUT (update new field)
  - [ ] GET with filters (query by new field)
  - [ ] Validation errors (422 response)

- [ ] **Security Tests**
  - [ ] Injection attempts (SQL, CSV, command)
  - [ ] Protocol violations (javascript:, file://)
  - [ ] Malicious payloads
  - [ ] Oversized inputs

- [ ] **Edge Case Tests**
  - [ ] Special characters (commas, quotes, newlines)
  - [ ] Boundary values (0, max, max+1)
  - [ ] Unicode characters
  - [ ] Concurrent operations (if applicable)

- [ ] **Agent Tests** (if applicable)
  - [ ] Agent extracts field from email
  - [ ] Agent extracts field from Slack
  - [ ] Agent creates task with field

### Test Coverage Goals

- [ ] **Service layer**: >80% coverage
- [ ] **API endpoints**: 100% coverage (all CRUD operations)
- [ ] **Validation logic**: 100% coverage (all branches)

---

## Code Review Checklist

Before requesting review:

### Code Quality

- [ ] **Ran ruff check**: `ruff check src/ tests/`
- [ ] **Ran ruff format**: `ruff format src/ tests/`
- [ ] **All tests pass**: `pytest`
- [ ] **Coverage acceptable**: `pytest --cov=src --cov-report=html`

### Security Review

- [ ] **No user input directly in SQL/subprocess/shell**
- [ ] **All inputs validated at boundaries**
- [ ] **URLs validated with protocol whitelist**
- [ ] **No CSV storage without JSON encoding**
- [ ] **Length limits enforced programmatically**

### Documentation

- [ ] **Updated README.md** (features, usage examples)
- [ ] **Updated CLAUDE.md** (if architectural patterns changed)
- [ ] **Added code comments** (security-sensitive logic)
- [ ] **Created migration notes** (if schema changes)

### Agent Integration

- [ ] **Feature works autonomously** (if applicable)
- [ ] **LLM prompts updated**
- [ ] **Agent logs show new field**

---

## Security Red Flags

**Stop and get security review if:**

- [ ] Feature accepts file uploads
- [ ] Feature executes commands
- [ ] Feature accesses filesystem
- [ ] Feature makes HTTP requests based on user input
- [ ] Feature stores sensitive data (passwords, tokens)
- [ ] Feature parses user-provided JSON/XML/YAML
- [ ] Feature uses subprocess at all
- [ ] Feature implements authentication/authorization

---

## Common Mistakes to Avoid

### Input Validation
- ❌ Validating only at API layer (also validate in CLI/service)
- ❌ Trusting external data sources (Gmail, Slack, etc.)
- ❌ Using only database constraints (validate programmatically)

### Data Storage
- ❌ Using CSV for data with commas/quotes
- ❌ Assuming SQLite behavior matches PostgreSQL
- ❌ Forgetting backward compatibility when changing formats

### Command Execution
- ❌ Using subprocess when stdlib alternative exists
- ❌ Using shell=True ever
- ❌ String concatenation for commands

### Testing
- ❌ Only testing happy path
- ❌ Only testing on SQLite
- ❌ Forgetting edge cases (empty, max, special chars)
- ❌ Not testing validation error messages

### Agent Integration
- ❌ Adding feature without updating agent
- ❌ Forgetting to update LLM prompts
- ❌ Not testing agent extraction

---

## Quick Reference: Safe Patterns

### URL Validation
```python
from pydantic import HttpUrl, field_validator

class Schema(BaseModel):
    urls: list[HttpUrl] = Field(max_length=20)

    @field_validator('urls')
    @classmethod
    def validate_protocols(cls, v):
        for url in v:
            if url.scheme not in ['http', 'https']:
                raise ValueError(f"Invalid protocol: {url.scheme}")
        return v
```

### JSON Storage
```python
import json

def set_data(self, items: list[str]) -> None:
    self.data = json.dumps(items) if items else None

def get_data(self) -> list[str]:
    if not self.data:
        return []
    try:
        return json.loads(self.data)
    except json.JSONDecodeError:
        return []  # Or CSV fallback
```

### Length Validation
```python
@field_validator('field')
@classmethod
def validate_length(cls, v):
    if v:
        serialized = json.dumps([str(x) for x in v])
        if len(serialized) > 5000:
            raise ValueError("Exceeds 5000 char limit")
    return v
```

### Safe Command Execution
```python
import webbrowser
from pathlib import Path

# URLs
webbrowser.open(url)

# Files
Path(path).read_text()
Path(path).write_text(data)

# HTTP
import requests
requests.get(url)
```

---

## Emergency Contacts

**If you discover a security vulnerability:**

1. **DO NOT commit it to git**
2. **DO NOT create a public GitHub issue**
3. Create a private todo in `/todos/` with `priority: p0` tag
4. Tag with `[security, vulnerability, urgent]`
5. Request immediate security review

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-11 | Initial version based on document_links review |

---

**Print this checklist and keep it visible while coding!**
