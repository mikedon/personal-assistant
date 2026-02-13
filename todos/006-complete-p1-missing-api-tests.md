---
status: pending
priority: p1
issue_id: "006"
tags: [code-review, testing, quality-assurance]
dependencies: []
---

# Missing API Tests for Document Links Feature

## Problem Statement

No API endpoint integration tests exist for the new document_links feature. Unit tests exist for service layer, but there are no tests validating the full HTTP request/response cycle, query parameter handling, or API schema validation.

**Why This Matters:** API tests ensure the full stack integration works correctly for external consumers. Without them, bugs in serialization, query parameters, or schema validation could reach production undetected.

## Findings

### Code Quality Review
- **Severity:** HIGH
- **Location:** `tests/integration/test_tasks_api.py`
- **Evidence:** Integration tests exist for document_links in unit tests only (`test_task_service.py`), but zero API endpoint tests

### DevOps Review
- **Severity:** MEDIUM
- **Issue:** End-to-end workflow not validated, risk of regression bugs

### Testing Gaps Identified:
- ✗ POST /api/tasks with document_links
- ✗ GET /api/tasks with document_links query param
- ✗ PUT /api/tasks updating document_links
- ✗ Response schema validation
- ✗ Query parameter edge cases

## Proposed Solutions

### Solution 1: Comprehensive API Test Suite (RECOMMENDED)
**Pros:**
- Full coverage of all API operations
- Tests actual HTTP behavior
- Validates serialization/deserialization
- Catches FastAPI-specific bugs

**Cons:**
- Takes time to write comprehensive tests

**Effort:** Medium (2-3 hours)
**Risk:** None (pure test addition)

**Implementation:**

```python
# tests/integration/test_tasks_api.py

def test_create_task_with_document_links(client, sample_task_data):
    """Test creating task with document links via API."""
    task_data = {
        **sample_task_data,
        "document_links": [
            "https://docs.google.com/document/d/abc123",
            "https://notion.so/My-Project-xyz"
        ]
    }
    response = client.post("/api/tasks", json=task_data)

    assert response.status_code == 201
    data = response.json()
    assert len(data["document_links"]) == 2
    assert "docs.google.com" in data["document_links"][0]
    assert data["id"] is not None


def test_create_task_with_empty_document_links(client, sample_task_data):
    """Test creating task with empty document_links list."""
    task_data = {**sample_task_data, "document_links": []}
    response = client.post("/api/tasks", json=task_data)

    assert response.status_code == 201
    assert response.json()["document_links"] == []


def test_filter_tasks_by_document_link(client, sample_task_data):
    """Test filtering tasks by document link via API."""
    # Create tasks
    client.post("/api/tasks", json={
        **sample_task_data,
        "title": "Task 1",
        "document_links": ["https://docs.google.com/doc1"]
    })
    client.post("/api/tasks", json={
        **sample_task_data,
        "title": "Task 2",
        "document_links": ["https://notion.so/page1"]
    })
    client.post("/api/tasks", json={
        **sample_task_data,
        "title": "Task 3",
        "document_links": []
    })

    # Filter by Google Docs
    response = client.get("/api/tasks", params={"document_links": ["docs.google.com"]})

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["tasks"][0]["title"] == "Task 1"


def test_filter_tasks_by_multiple_document_links(client, sample_task_data):
    """Test filtering by multiple links (OR logic)."""
    # Create tasks
    client.post("/api/tasks", json={
        **sample_task_data,
        "title": "Task 1",
        "document_links": ["https://docs.google.com/doc1"]
    })
    client.post("/api/tasks", json={
        **sample_task_data,
        "title": "Task 2",
        "document_links": ["https://notion.so/page1"]
    })

    # Filter by both (should return both tasks)
    response = client.get("/api/tasks", params={
        "document_links": ["docs.google.com", "notion.so"]
    })

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2


def test_update_task_document_links(client, sample_task_data):
    """Test updating document links via API."""
    # Create task
    response = client.post("/api/tasks", json=sample_task_data)
    task_id = response.json()["id"]

    # Update with document links
    response = client.put(f"/api/tasks/{task_id}", json={
        "document_links": ["https://new-link.com"]
    })

    assert response.status_code == 200
    data = response.json()
    assert len(data["document_links"]) == 1
    assert "new-link.com" in data["document_links"][0]


def test_update_task_clear_document_links(client, sample_task_data):
    """Test clearing document links by setting to empty list."""
    # Create task with links
    response = client.post("/api/tasks", json={
        **sample_task_data,
        "document_links": ["https://docs.google.com/doc1"]
    })
    task_id = response.json()["id"]

    # Clear links
    response = client.put(f"/api/tasks/{task_id}", json={
        "document_links": []
    })

    assert response.status_code == 200
    assert response.json()["document_links"] == []


def test_create_task_with_invalid_url(client, sample_task_data):
    """Test API rejects invalid URLs (after validation is added)."""
    task_data = {
        **sample_task_data,
        "document_links": ["not-a-url"]
    }
    response = client.post("/api/tasks", json=task_data)

    # Should return 422 validation error
    assert response.status_code == 422
    assert "url" in response.json()["detail"][0]["type"].lower()


def test_list_tasks_includes_document_links(client, sample_task_data):
    """Test that list endpoint returns document_links field."""
    client.post("/api/tasks", json={
        **sample_task_data,
        "document_links": ["https://docs.google.com/doc1"]
    })

    response = client.get("/api/tasks")

    assert response.status_code == 200
    data = response.json()
    assert len(data["tasks"]) >= 1
    assert "document_links" in data["tasks"][0]
    assert isinstance(data["tasks"][0]["document_links"], list)


def test_get_task_by_id_includes_document_links(client, sample_task_data):
    """Test that get-by-id endpoint returns document_links."""
    response = client.post("/api/tasks", json={
        **sample_task_data,
        "document_links": ["https://docs.google.com/doc1"]
    })
    task_id = response.json()["id"]

    response = client.get(f"/api/tasks/{task_id}")

    assert response.status_code == 200
    data = response.json()
    assert "document_links" in data
    assert len(data["document_links"]) == 1
```

### Solution 2: Minimal Smoke Tests
**Pros:**
- Fast to implement
- Covers happy path

**Cons:**
- Misses edge cases
- Incomplete coverage

**Effort:** Small (30 minutes)
**Risk:** Medium (gaps in coverage)

## Recommended Action

**Implement Solution 1** (comprehensive test suite). This ensures production readiness and prevents regressions.

## Technical Details

**Affected Files:**
- `tests/integration/test_tasks_api.py` - Add all tests above
- `tests/conftest.py` - May need fixtures for sample data with links

**Test Coverage Goals:**
- [x] Create task with document_links
- [x] Create task with empty document_links
- [x] Filter by single document link
- [x] Filter by multiple document links (OR logic)
- [x] Update task document links
- [x] Clear document links
- [x] Invalid URL validation (after #002)
- [x] List endpoint includes document_links
- [x] Get-by-id includes document_links

**Test Execution:**
```bash
pytest tests/integration/test_tasks_api.py::test_create_task_with_document_links -v
pytest tests/integration/test_tasks_api.py -k document_links -v
```

## Acceptance Criteria

- [ ] All 10+ API tests written and passing
- [ ] Tests cover CRUD operations with document_links
- [ ] Tests cover query parameter filtering
- [ ] Tests cover edge cases (empty lists, None, invalid URLs)
- [ ] Tests validate response schema
- [ ] Tests run in CI/CD pipeline
- [ ] Code coverage for API routes includes document_links paths

## Work Log

### 2026-02-11 - Issue Identified
- Code quality review found zero API tests for document_links
- Confirmed unit tests exist but not integration tests
- Listed 10+ missing test cases
- Prioritized as P1 (quality gate for production)

## Resources

- **PR:** #2 - feat: Add external document links to tasks
- **Existing Tests:** `tests/unit/test_task_service.py` (model/service tests)
- **API Test Reference:** `tests/integration/test_tasks_api.py` (existing patterns)
- **FastAPI Testing:** [TestClient docs](https://fastapi.tiangolo.com/tutorial/testing/)
