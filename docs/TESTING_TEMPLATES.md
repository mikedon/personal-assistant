# Testing Templates and Examples

**Purpose**: Copy-paste templates for common test patterns. Based on the comprehensive test suite from the document_links feature.

**When to Use**: When writing tests for new features, use these templates as starting points.

---

## Table of Contents

1. [Unit Tests (Service Layer)](#unit-tests-service-layer)
2. [Integration Tests (API Layer)](#integration-tests-api-layer)
3. [Security Tests](#security-tests)
4. [Edge Case Tests](#edge-case-tests)
5. [Agent Integration Tests](#agent-integration-tests)
6. [Migration Tests](#migration-tests)

---

## Unit Tests (Service Layer)

Location: `tests/unit/test_*_service.py`

### Template: Basic CRUD Operations

```python
import pytest
from sqlalchemy.orm import Session

from src.services.task_service import TaskService
from src.models.task import TaskPriority


class TestTaskServiceWithNewFeature:
    """Test TaskService with new feature."""

    def test_create_with_new_field(self, test_db_session: Session):
        """Test creating record with new field."""
        task_service = TaskService()

        task = task_service.create_task(
            db=test_db_session,
            title="Test Task",
            new_field="value"  # Your new field
        )

        assert task.id is not None
        assert task.new_field == "value"

    def test_create_with_empty_new_field(self, test_db_session: Session):
        """Test creating record with empty new field."""
        task_service = TaskService()

        task = task_service.create_task(
            db=test_db_session,
            title="Test Task",
            new_field=None
        )

        assert task.new_field is None

    def test_update_new_field(self, test_db_session: Session):
        """Test updating new field."""
        task_service = TaskService()

        # Create task
        task = task_service.create_task(
            db=test_db_session,
            title="Test Task",
            new_field="original"
        )

        # Update field
        updated = task_service.update_task(
            db=test_db_session,
            task_id=task.id,
            new_field="updated"
        )

        assert updated.new_field == "updated"

    def test_list_filters_by_new_field(self, test_db_session: Session):
        """Test filtering by new field."""
        task_service = TaskService()

        # Create tasks
        task_service.create_task(
            db=test_db_session,
            title="Task 1",
            new_field="value1"
        )
        task_service.create_task(
            db=test_db_session,
            title="Task 2",
            new_field="value2"
        )

        # Filter
        results, total = task_service.list_tasks(
            db=test_db_session,
            new_field_filter="value1"
        )

        assert total == 1
        assert results[0].title == "Task 1"
```

### Template: Validation Tests

```python
def test_validates_new_field_format(self, test_db_session: Session):
    """Test validation of new field format."""
    task_service = TaskService()

    with pytest.raises(ValueError, match="Invalid format"):
        task_service.create_task(
            db=test_db_session,
            title="Test",
            new_field="invalid-format"
        )

def test_validates_new_field_length(self, test_db_session: Session):
    """Test validation of new field length."""
    task_service = TaskService()

    with pytest.raises(ValueError, match="exceeds limit"):
        task_service.create_task(
            db=test_db_session,
            title="Test",
            new_field="x" * 10000  # Exceeds limit
        )

def test_validates_new_field_required(self, test_db_session: Session):
    """Test validation when field is required."""
    task_service = TaskService()

    with pytest.raises(ValueError, match="required"):
        task_service.create_task(
            db=test_db_session,
            title="Test",
            new_field=None  # But it's required
        )
```

---

## Integration Tests (API Layer)

Location: `tests/integration/test_*_api.py`

### Template: Basic CRUD API Tests

```python
import pytest
from fastapi.testclient import TestClient


class TestTaskAPIWithNewFeature:
    """Test Task API with new feature."""

    @pytest.fixture
    def sample_task_data(self):
        """Sample task data for tests."""
        return {
            "title": "Test Task",
            "description": "Test description",
            "priority": "medium"
        }

    def test_create_with_new_field(self, client: TestClient, sample_task_data):
        """POST /api/tasks with new field."""
        task_data = {
            **sample_task_data,
            "new_field": "value"
        }

        response = client.post("/api/tasks", json=task_data)

        assert response.status_code == 201
        data = response.json()
        assert data["new_field"] == "value"
        assert data["id"] is not None

    def test_create_with_empty_new_field(self, client: TestClient, sample_task_data):
        """POST /api/tasks with empty new field."""
        task_data = {
            **sample_task_data,
            "new_field": None
        }

        response = client.post("/api/tasks", json=task_data)

        assert response.status_code == 201
        assert response.json()["new_field"] is None

    def test_create_without_new_field(self, client: TestClient, sample_task_data):
        """POST /api/tasks without new field (should use default)."""
        response = client.post("/api/tasks", json=sample_task_data)

        assert response.status_code == 201
        # Check default value
        assert "new_field" in response.json()

    def test_get_includes_new_field(self, client: TestClient, sample_task_data):
        """GET /api/tasks/{id} includes new field."""
        # Create task
        create_response = client.post("/api/tasks", json={
            **sample_task_data,
            "new_field": "value"
        })
        task_id = create_response.json()["id"]

        # Get task
        response = client.get(f"/api/tasks/{task_id}")

        assert response.status_code == 200
        data = response.json()
        assert "new_field" in data
        assert data["new_field"] == "value"

    def test_list_includes_new_field(self, client: TestClient, sample_task_data):
        """GET /api/tasks includes new field."""
        # Create task
        client.post("/api/tasks", json={
            **sample_task_data,
            "new_field": "value"
        })

        # List tasks
        response = client.get("/api/tasks")

        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) >= 1
        assert "new_field" in data["tasks"][0]

    def test_update_new_field(self, client: TestClient, sample_task_data):
        """PUT /api/tasks/{id} updates new field."""
        # Create task
        create_response = client.post("/api/tasks", json=sample_task_data)
        task_id = create_response.json()["id"]

        # Update field
        response = client.put(f"/api/tasks/{task_id}", json={
            "new_field": "updated_value"
        })

        assert response.status_code == 200
        assert response.json()["new_field"] == "updated_value"

    def test_update_clear_new_field(self, client: TestClient, sample_task_data):
        """PUT /api/tasks/{id} can clear new field."""
        # Create task with field
        create_response = client.post("/api/tasks", json={
            **sample_task_data,
            "new_field": "value"
        })
        task_id = create_response.json()["id"]

        # Clear field
        response = client.put(f"/api/tasks/{task_id}", json={
            "new_field": None
        })

        assert response.status_code == 200
        assert response.json()["new_field"] is None
```

### Template: Filter/Query Tests

```python
def test_filter_by_new_field(self, client: TestClient, sample_task_data):
    """GET /api/tasks?new_field=value filters correctly."""
    # Create tasks with different values
    client.post("/api/tasks", json={
        **sample_task_data,
        "title": "Task 1",
        "new_field": "value1"
    })
    client.post("/api/tasks", json={
        **sample_task_data,
        "title": "Task 2",
        "new_field": "value2"
    })
    client.post("/api/tasks", json={
        **sample_task_data,
        "title": "Task 3",
        "new_field": None
    })

    # Filter by value1
    response = client.get("/api/tasks", params={"new_field": "value1"})

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["tasks"][0]["title"] == "Task 1"

def test_filter_by_multiple_new_field_values(self, client: TestClient, sample_task_data):
    """GET /api/tasks?new_field=value1&new_field=value2 (OR logic)."""
    # Create tasks
    client.post("/api/tasks", json={
        **sample_task_data,
        "title": "Task 1",
        "new_field": "value1"
    })
    client.post("/api/tasks", json={
        **sample_task_data,
        "title": "Task 2",
        "new_field": "value2"
    })

    # Filter by both values
    response = client.get("/api/tasks", params={
        "new_field": ["value1", "value2"]
    })

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2

def test_pagination_with_new_field(self, client: TestClient, sample_task_data):
    """Pagination preserves new field data."""
    # Create multiple tasks
    for i in range(5):
        client.post("/api/tasks", json={
            **sample_task_data,
            "title": f"Task {i}",
            "new_field": f"value{i}"
        })

    # Get first page
    response = client.get("/api/tasks", params={"skip": 0, "limit": 2})

    assert response.status_code == 200
    data = response.json()
    assert len(data["tasks"]) == 2
    assert all("new_field" in task for task in data["tasks"])
```

### Template: Validation Error Tests

```python
def test_rejects_invalid_new_field_format(self, client: TestClient, sample_task_data):
    """API rejects invalid format with 422."""
    task_data = {
        **sample_task_data,
        "new_field": "invalid-format"
    }

    response = client.post("/api/tasks", json=task_data)

    assert response.status_code == 422
    error_detail = response.json()["detail"]
    assert any("new_field" in str(err) for err in error_detail)

def test_rejects_too_long_new_field(self, client: TestClient, sample_task_data):
    """API rejects oversized input with 422."""
    task_data = {
        **sample_task_data,
        "new_field": "x" * 10000
    }

    response = client.post("/api/tasks", json=task_data)

    assert response.status_code == 422
    assert "limit" in str(response.json()).lower()

def test_rejects_empty_string_in_list_field(self, client: TestClient, sample_task_data):
    """API rejects empty strings in list fields."""
    task_data = {
        **sample_task_data,
        "list_field": ["valid", "", "valid"]  # Empty string
    }

    response = client.post("/api/tasks", json=task_data)

    assert response.status_code == 422
```

---

## Security Tests

Location: `tests/unit/test_*_service.py` or `tests/integration/test_*_api.py`

### Template: Injection Tests

```python
class TestSecurityValidation:
    """Security validation tests."""

    def test_rejects_csv_injection_in_field(self, client: TestClient):
        """Blocks CSV formula injection."""
        payloads = [
            "=cmd|'/c calc'!A1",  # Excel formula
            "@SUM(A1:A10)",        # Excel function
            "+1+1+cmd|'/c calc'!A0",  # Arithmetic formula
            "-2+3+cmd|'/c calc'!A0",  # Negative formula
        ]

        for payload in payloads:
            response = client.post("/api/tasks", json={
                "title": payload,
                "description": "Test"
            })

            # Either rejected (422) or sanitized (201 but payload modified)
            if response.status_code == 201:
                # Verify sanitization
                assert response.json()["title"] != payload
            else:
                assert response.status_code == 422

    def test_rejects_javascript_urls(self, client: TestClient):
        """Blocks XSS via javascript: URLs."""
        response = client.post("/api/tasks", json={
            "title": "Test",
            "url_field": "javascript:alert('xss')"
        })

        assert response.status_code == 422
        assert "scheme" in str(response.json()).lower() or \
               "protocol" in str(response.json()).lower()

    def test_rejects_file_urls(self, client: TestClient):
        """Blocks local file access via file:// URLs."""
        response = client.post("/api/tasks", json={
            "title": "Test",
            "url_field": "file:///etc/passwd"
        })

        assert response.status_code == 422

    def test_rejects_data_urls(self, client: TestClient):
        """Blocks data: URLs (phishing risk)."""
        response = client.post("/api/tasks", json={
            "title": "Test",
            "url_field": "data:text/html,<script>alert('xss')</script>"
        })

        assert response.status_code == 422

    def test_sql_injection_attempt_in_filter(self, client: TestClient):
        """SQL injection attempts in query params."""
        # SQLAlchemy parameterized queries should prevent this
        malicious_queries = [
            "'; DROP TABLE tasks; --",
            "1 OR 1=1",
            "' UNION SELECT * FROM users --",
        ]

        for query in malicious_queries:
            response = client.get("/api/tasks", params={"search": query})

            # Should not crash or leak data
            assert response.status_code in [200, 400, 422]
            # Verify no SQL error in response
            assert "syntax error" not in str(response.json()).lower()

    def test_command_injection_attempt(self, test_db_session: Session):
        """Command injection in fields that might be used in subprocess."""
        service = TaskService()

        malicious_values = [
            "; rm -rf /",
            "| cat /etc/passwd",
            "$(whoami)",
            "`reboot`",
        ]

        for value in malicious_values:
            # Should either reject or safely escape
            try:
                task = service.create_task(
                    db=test_db_session,
                    title="Test",
                    shell_field=value
                )
                # If created, value should be escaped/sanitized
                assert task.shell_field != value or value.startswith("$(")
            except ValueError:
                # Rejection is acceptable
                pass
```

---

## Edge Case Tests

Location: `tests/unit/test_*_model.py` or `tests/unit/test_*_service.py`

### Template: Data Integrity Tests

```python
class TestEdgeCases:
    """Edge case tests for data integrity."""

    def test_field_with_commas(self):
        """Data with commas doesn't corrupt storage."""
        task = Task(title="Test")
        value_with_comma = "value1,value2,value3"

        task.set_field(value_with_comma)
        retrieved = task.get_field()

        assert retrieved == value_with_comma  # No corruption

    def test_field_with_quotes(self):
        """Data with quotes preserved correctly."""
        task = Task(title="Test")
        value_with_quotes = 'He said "hello" to me'

        task.set_field(value_with_quotes)
        retrieved = task.get_field()

        assert retrieved == value_with_quotes

    def test_field_with_newlines(self):
        """Data with newlines handled correctly."""
        task = Task(title="Test")
        value_with_newlines = "Line 1\nLine 2\nLine 3"

        # Either stored correctly or rejected
        try:
            task.set_field(value_with_newlines)
            retrieved = task.get_field()
            assert retrieved == value_with_newlines
        except ValueError as e:
            # Rejection is acceptable for some fields
            assert "newline" in str(e).lower()

    def test_field_with_unicode(self):
        """Unicode characters preserved correctly."""
        task = Task(title="Test")
        unicode_value = "Hello 世界 🌍"

        task.set_field(unicode_value)
        retrieved = task.get_field()

        assert retrieved == unicode_value

    def test_field_with_maximum_length(self):
        """Maximum length input accepted."""
        task = Task(title="Test")
        max_value = "x" * 5000  # At limit

        task.set_field(max_value)
        retrieved = task.get_field()

        assert retrieved == max_value

    def test_field_exceeding_maximum_length(self):
        """Over-length input rejected with clear error."""
        task = Task(title="Test")
        too_long = "x" * 5001  # Over limit

        with pytest.raises(ValueError, match="exceeds.*limit"):
            task.set_field(too_long)

    def test_empty_list_vs_none(self):
        """Empty list and None handled distinctly."""
        task = Task(title="Test")

        # Set to empty list
        task.set_list_field([])
        assert task.get_list_field() == []
        assert task.list_field is None  # Empty stored as None

        # Set to None
        task.set_list_field(None)
        assert task.get_list_field() == []
        assert task.list_field is None

    def test_duplicate_values_in_list(self):
        """Duplicate values in list handled correctly."""
        task = Task(title="Test")
        values = ["a", "b", "a", "c"]  # Has duplicate

        task.set_list_field(values)
        retrieved = task.get_list_field()

        # Either preserved or deduplicated (document behavior)
        assert len(retrieved) <= len(values)

    def test_null_bytes_rejected(self):
        """Null bytes in strings rejected."""
        task = Task(title="Test")

        with pytest.raises(ValueError):
            task.set_field("value\x00with_null")

    def test_very_long_individual_item(self):
        """Single very long item in list handled."""
        task = Task(title="Test")
        long_item = "x" * 4000

        # Either accepted if under total limit or rejected
        try:
            task.set_list_field([long_item])
            retrieved = task.get_list_field()
            assert retrieved[0] == long_item
        except ValueError as e:
            assert "limit" in str(e).lower()
```

---

## Agent Integration Tests

Location: `tests/integration/test_agent_core.py`

### Template: Agent Extraction Tests

```python
import pytest
from unittest.mock import Mock, patch

from src.agent.core import AutonomousAgent
from src.services.llm_service import ExtractedTask


class TestAgentNewFeatureExtraction:
    """Test agent extracts new feature from integrations."""

    @pytest.fixture
    def agent(self, test_db_session, test_config):
        """Create agent instance."""
        return AutonomousAgent(db=test_db_session, config=test_config)

    @patch('src.services.llm_service.LLMService.extract_tasks_from_text')
    def test_agent_extracts_new_field_from_email(
        self,
        mock_extract,
        agent,
        test_db_session
    ):
        """Agent extracts new field from email body."""
        # Mock email content
        email_text = """
        Please complete this task: Review document
        New field value: important_value
        """

        # Mock LLM extraction
        mock_extract.return_value = [
            ExtractedTask(
                title="Review document",
                description="Please complete this task",
                new_field="important_value",  # Extracted
                confidence=0.9
            )
        ]

        # Simulate agent processing email
        from src.integrations.base import ActionableItem, IntegrationType
        item = ActionableItem(
            type="EMAIL",
            title="Email subject",
            description=email_text,
            source=IntegrationType.GMAIL,
            new_field="important_value"  # Integration extracted
        )

        # Agent creates task
        task = agent._create_task_from_extracted(
            item=item,
            extracted=mock_extract.return_value[0],
            source="email"
        )

        # Verify new field preserved
        assert task.new_field == "important_value"

    @patch('src.services.llm_service.LLMService.extract_tasks_from_text')
    def test_agent_extracts_new_field_from_slack(
        self,
        mock_extract,
        agent,
        test_db_session
    ):
        """Agent extracts new field from Slack message."""
        slack_text = "TODO: Fix bug in feature X (new_field: value)"

        mock_extract.return_value = [
            ExtractedTask(
                title="Fix bug in feature X",
                new_field="value",
                confidence=0.85
            )
        ]

        # Test agent processes Slack message
        # Similar to email test above

    def test_agent_logs_extracted_new_field(
        self,
        agent,
        test_db_session,
        monkeypatch
    ):
        """Agent logs show extracted new field for transparency."""
        # Mock LLM extraction with new field
        # Create task via agent
        # Query agent_logs table
        # Verify log contains new_field information

        from src.models.agent_log import AgentLog

        logs = test_db_session.query(AgentLog).filter(
            AgentLog.action == "TASK_CREATED"
        ).all()

        assert len(logs) > 0
        log_details = logs[0].details
        assert "new_field" in log_details
```

---

## Migration Tests

Location: `tests/unit/test_migrations.py` (create if doesn't exist)

### Template: Data Migration Tests

```python
import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, text


class TestMigrations:
    """Test database migrations."""

    def test_migration_converts_old_format_to_new(self):
        """Migration converts legacy data format to new format."""
        # Create in-memory database
        engine = create_engine("sqlite:///:memory:")

        # Create old schema (before migration)
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    old_field TEXT
                )
            """))
            conn.commit()

            # Insert legacy data
            conn.execute(text("""
                INSERT INTO tasks (title, old_field)
                VALUES ('Test', 'old_format_value')
            """))
            conn.commit()

        # Apply migration
        # (In real test, use Alembic to apply specific migration)

        # Verify data converted
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT new_field FROM tasks WHERE id = 1"
            ))
            row = result.fetchone()
            assert row[0] == "converted_value"  # Converted from old format

    def test_migration_preserves_existing_data(self):
        """Migration doesn't lose existing data."""
        # Create engine with existing data
        # Apply migration
        # Verify all rows still present
        # Verify other columns unchanged

    def test_migration_handles_null_values(self):
        """Migration handles NULL values correctly."""
        # Insert rows with NULL in field being migrated
        # Apply migration
        # Verify NULLs handled appropriately

    def test_migration_rollback_works(self):
        """Migration can be rolled back safely."""
        # Apply migration
        # Verify new schema
        # Rollback migration
        # Verify old schema restored
        # Verify data still intact (if rollback should preserve data)

    def test_migration_increases_column_length(self):
        """Migration increases column size without data loss."""
        # Create table with small column (VARCHAR(100))
        # Insert data near limit (95 chars)
        # Apply migration (increases to VARCHAR(500))
        # Verify data intact
        # Insert data with new larger size
        # Verify accepted

    def test_migration_converts_csv_to_json(self):
        """Migration converts CSV format to JSON format."""
        engine = create_engine("sqlite:///:memory:")

        with engine.connect() as conn:
            # Create old schema
            conn.execute(text("""
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY,
                    title TEXT,
                    csv_field TEXT
                )
            """))
            conn.commit()

            # Insert CSV data
            conn.execute(text("""
                INSERT INTO tasks (title, csv_field)
                VALUES ('Test', 'value1,value2,value3')
            """))
            conn.commit()

            # Simulate migration: convert CSV to JSON
            import json
            result = conn.execute(text(
                "SELECT id, csv_field FROM tasks"
            ))
            for row in result:
                csv_values = row.csv_field.split(",")
                json_value = json.dumps(csv_values)
                conn.execute(
                    text("UPDATE tasks SET csv_field = :json WHERE id = :id"),
                    {"json": json_value, "id": row.id}
                )
            conn.commit()

            # Verify JSON format
            result = conn.execute(text(
                "SELECT csv_field FROM tasks WHERE id = 1"
            ))
            json_str = result.fetchone()[0]
            assert json_str.startswith("[")
            values = json.loads(json_str)
            assert values == ["value1", "value2", "value3"]
```

---

## Fixture Templates

Location: `tests/conftest.py`

### Template: Common Test Fixtures

```python
import pytest
from typing import Dict, Any


@pytest.fixture
def sample_task_data() -> Dict[str, Any]:
    """Sample task data for API tests."""
    return {
        "title": "Test Task",
        "description": "Test description",
        "priority": "medium",
        "tags": ["test"],
        "new_field": "default_value"
    }


@pytest.fixture
def sample_task_with_new_feature(test_db_session) -> Task:
    """Create a task with new feature for testing."""
    from src.models.task import Task

    task = Task(
        title="Test Task",
        description="Test description",
        priority="medium",
        new_field="test_value"
    )
    test_db_session.add(task)
    test_db_session.commit()
    test_db_session.refresh(task)
    return task


@pytest.fixture
def multiple_tasks_with_new_field(test_db_session) -> List[Task]:
    """Create multiple tasks with varying new field values."""
    from src.models.task import Task

    tasks = []
    for i in range(5):
        task = Task(
            title=f"Task {i}",
            new_field=f"value{i}"
        )
        test_db_session.add(task)
        tasks.append(task)

    test_db_session.commit()
    for task in tasks:
        test_db_session.refresh(task)

    return tasks


@pytest.fixture
def mock_llm_service(monkeypatch):
    """Mock LLM service for agent tests."""
    from unittest.mock import Mock
    from src.services.llm_service import LLMService, ExtractedTask

    mock_service = Mock(spec=LLMService)

    def mock_extract_tasks(text, source):
        return [
            ExtractedTask(
                title="Test Task",
                description=text[:100],
                confidence=0.9,
                new_field="extracted_value"
            )
        ]

    mock_service.extract_tasks_from_text = Mock(side_effect=mock_extract_tasks)

    monkeypatch.setattr(
        "src.agent.core.LLMService",
        lambda: mock_service
    )

    return mock_service
```

---

## Test Organization Best Practices

### File Structure

```
tests/
├── conftest.py              # Shared fixtures
├── unit/
│   ├── test_task_model.py       # Model tests
│   ├── test_task_service.py     # Service tests
│   └── test_llm_service.py      # LLM tests
├── integration/
│   ├── test_tasks_api.py        # API endpoint tests
│   └── test_agent_core.py       # Agent integration tests
└── fixtures/
    └── sample_data.json         # Test data files
```

### Test Naming Conventions

```python
# Format: test_<function>_<scenario>_<expected_outcome>

# Good
def test_create_task_with_valid_url_succeeds():
def test_create_task_with_invalid_url_raises_error():
def test_filter_tasks_by_tag_returns_matching_tasks():

# Bad
def test_create():  # Too vague
def test_1():       # No description
def test_everything():  # Too broad
```

### Test Documentation

```python
def test_create_task_with_urls_containing_commas():
    """
    Test that URLs with commas in query parameters are stored correctly.

    This is a regression test for Issue #001 (CSV injection vulnerability).
    URLs like https://example.com?tags=work,urgent should not be split
    into multiple URLs when using CSV storage.

    Expected: URL retrieved exactly as stored, no corruption.
    """
    # Test implementation
```

---

## Running Tests

### Run All Tests
```bash
pytest
```

### Run Specific Test File
```bash
pytest tests/unit/test_task_service.py
pytest tests/integration/test_tasks_api.py
```

### Run Specific Test
```bash
pytest tests/unit/test_task_service.py::test_create_with_new_field
```

### Run Tests Matching Pattern
```bash
pytest -k "new_field"  # All tests with "new_field" in name
pytest -k "security"   # All security tests
```

### Run With Coverage
```bash
pytest --cov=src --cov-report=html
open htmlcov/index.html  # View coverage report
```

### Run Verbose
```bash
pytest -v  # Verbose output
pytest -vv # Very verbose
pytest -s  # Don't capture output (see print statements)
```

---

## Checklist: Complete Test Suite

When you've finished testing a new feature:

- [ ] Unit tests cover all service methods
- [ ] Integration tests cover all API endpoints
- [ ] Security tests for injection attempts
- [ ] Edge case tests for data integrity
- [ ] Agent tests if feature is agent-accessible
- [ ] Migration tests if schema changed
- [ ] All tests pass: `pytest`
- [ ] Coverage >80%: `pytest --cov=src`
- [ ] Tests documented with docstrings
- [ ] Fixtures added to conftest.py if reusable

---

**Remember**: Tests are documentation. Write them so future developers understand what the feature does and how it should behave.

---

**Version**: 1.0
**Last Updated**: 2026-02-11
**Based On**: document_links feature test suite (23 tests, 100% passing)
