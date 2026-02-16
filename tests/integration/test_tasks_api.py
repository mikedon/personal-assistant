"""Integration tests for task API endpoints."""

from datetime import datetime, timedelta

import pytest

from src.models.task import Task, TaskPriority, TaskStatus


def test_health_check(client):
    """Test basic health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_health_ready(client):
    """Test readiness health check endpoint."""
    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert "version" in data
    assert data["database"] == "connected"


def test_health_agent(client):
    """Test agent health check endpoint."""
    response = client.get("/health/agent")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ["running", "not_started"]
    assert "last_poll" in data
    assert "version" in data


def test_create_task(client, sample_task_data):
    """Test creating a task via API."""
    response = client.post("/api/tasks", json=sample_task_data)
    assert response.status_code == 201

    data = response.json()
    assert data["title"] == sample_task_data["title"]
    assert data["description"] == sample_task_data["description"]
    assert data["priority"] == sample_task_data["priority"]
    assert data["status"] == "pending"
    assert data["source"] == "manual"
    assert "id" in data
    assert "priority_score" in data


def test_get_task(client, sample_task_data):
    """Test retrieving a task by ID."""
    # Create a task first
    create_response = client.post("/api/tasks", json=sample_task_data)
    task_id = create_response.json()["id"]

    # Get the task
    response = client.get(f"/api/tasks/{task_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == task_id
    assert data["title"] == sample_task_data["title"]


def test_get_task_not_found(client):
    """Test getting a non-existent task."""
    response = client.get("/api/tasks/9999")
    assert response.status_code == 404


def test_list_tasks(client, sample_task_data):
    """Test listing all tasks."""
    # Create multiple tasks
    client.post("/api/tasks", json=sample_task_data)
    client.post("/api/tasks", json={**sample_task_data, "title": "Second Task"})

    response = client.get("/api/tasks")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] >= 2
    assert len(data["tasks"]) >= 2


def test_list_tasks_with_status_filter(client, sample_task_data):
    """Test listing tasks filtered by status."""
    # Create tasks
    client.post("/api/tasks", json=sample_task_data)

    # Get pending tasks
    response = client.get("/api/tasks?status=pending")
    assert response.status_code == 200

    data = response.json()
    assert all(task["status"] == "pending" for task in data["tasks"])


def test_update_task(client, sample_task_data):
    """Test updating a task."""
    # Create a task
    create_response = client.post("/api/tasks", json=sample_task_data)
    task_id = create_response.json()["id"]

    # Update the task
    update_data = {
        "title": "Updated Task Title",
        "status": "in_progress",
    }
    response = client.put(f"/api/tasks/{task_id}", json=update_data)
    assert response.status_code == 200

    data = response.json()
    assert data["title"] == "Updated Task Title"
    assert data["status"] == "in_progress"


def test_update_task_to_completed(client, sample_task_data):
    """Test marking a task as completed."""
    # Create a task
    create_response = client.post("/api/tasks", json=sample_task_data)
    task_id = create_response.json()["id"]

    # Mark as completed
    response = client.put(f"/api/tasks/{task_id}", json={"status": "completed"})
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "completed"
    assert data["completed_at"] is not None


def test_delete_task(client, sample_task_data):
    """Test deleting a task."""
    # Create a task
    create_response = client.post("/api/tasks", json=sample_task_data)
    task_id = create_response.json()["id"]

    # Delete the task
    response = client.delete(f"/api/tasks/{task_id}")
    assert response.status_code == 204

    # Verify it's deleted
    get_response = client.get(f"/api/tasks/{task_id}")
    assert get_response.status_code == 404


def test_get_prioritized_tasks(client, test_db_session):
    """Test getting tasks by priority score."""
    # Create tasks with different priorities
    high_priority_task = Task(
        title="Critical Task",
        priority=TaskPriority.CRITICAL,
        priority_score=90.0,
        status=TaskStatus.PENDING,
    )
    low_priority_task = Task(
        title="Low Priority Task",
        priority=TaskPriority.LOW,
        priority_score=30.0,
        status=TaskStatus.PENDING,
    )

    test_db_session.add(high_priority_task)
    test_db_session.add(low_priority_task)
    test_db_session.commit()

    response = client.get("/api/tasks/priority")
    assert response.status_code == 200

    data = response.json()
    tasks = data["tasks"]

    # Tasks should be sorted by priority score (highest first)
    assert len(tasks) >= 2
    assert tasks[0]["title"] == "Critical Task"
    assert tasks[0]["priority_score"] > tasks[1]["priority_score"]


def test_pagination(client, sample_task_data):
    """Test task list pagination."""
    # Create multiple tasks
    for i in range(15):
        client.post("/api/tasks", json={**sample_task_data, "title": f"Task {i}"})

    # Get first page
    response = client.get("/api/tasks?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["tasks"]) == 10
    assert data["total"] >= 15

    # Get second page
    response = client.get("/api/tasks?limit=10&offset=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["tasks"]) >= 5


# Phase 2 Tests
def test_search_tasks(client, sample_task_data):
    """Test searching tasks by title/description."""
    client.post("/api/tasks", json={**sample_task_data, "title": "Meeting with team"})
    client.post("/api/tasks", json={**sample_task_data, "title": "Other task", "description": "About the meeting"})
    client.post("/api/tasks", json={**sample_task_data, "title": "Unrelated"})

    response = client.get("/api/tasks?search=meeting")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2


def test_filter_by_priority(client, sample_task_data):
    """Test filtering tasks by priority."""
    client.post("/api/tasks", json={**sample_task_data, "priority": "critical"})
    client.post("/api/tasks", json={**sample_task_data, "priority": "low"})

    response = client.get("/api/tasks?priority=critical")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["tasks"][0]["priority"] == "critical"


def test_filter_exclude_completed(client, sample_task_data):
    """Test excluding completed tasks."""
    client.post("/api/tasks", json=sample_task_data)
    resp = client.post("/api/tasks", json={**sample_task_data, "title": "Complete me"})
    task_id = resp.json()["id"]
    client.put(f"/api/tasks/{task_id}", json={"status": "completed"})

    # With completed
    response = client.get("/api/tasks?include_completed=true")
    assert response.json()["total"] == 2

    # Without completed
    response = client.get("/api/tasks?include_completed=false")
    assert response.json()["total"] == 1


def test_get_overdue_tasks(client, sample_task_data):
    """Test getting overdue tasks endpoint."""
    from datetime import UTC, datetime, timedelta

    yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).isoformat()

    client.post("/api/tasks", json={**sample_task_data, "title": "Overdue", "due_date": yesterday})
    client.post("/api/tasks", json={**sample_task_data, "title": "Future", "due_date": tomorrow})

    response = client.get("/api/tasks/overdue")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["tasks"][0]["title"] == "Overdue"


def test_get_due_soon_tasks(client, sample_task_data):
    """Test getting tasks due soon endpoint."""
    from datetime import UTC, datetime, timedelta

    tomorrow = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    next_month = (datetime.now(UTC) + timedelta(days=30)).isoformat()

    client.post("/api/tasks", json={**sample_task_data, "title": "Soon", "due_date": tomorrow})
    client.post("/api/tasks", json={**sample_task_data, "title": "Later", "due_date": next_month})

    response = client.get("/api/tasks/due-soon?days=7")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["tasks"][0]["title"] == "Soon"


def test_get_task_statistics(client, sample_task_data):
    """Test getting task statistics."""
    client.post("/api/tasks", json={**sample_task_data, "priority": "high"})
    client.post("/api/tasks", json={**sample_task_data, "priority": "low"})
    resp = client.post("/api/tasks", json=sample_task_data)
    task_id = resp.json()["id"]
    client.put(f"/api/tasks/{task_id}", json={"status": "completed"})

    response = client.get("/api/tasks/stats")
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 3
    assert data["active"] == 2
    assert data["by_status"]["completed"] == 1
    assert data["by_status"]["pending"] == 2


def test_bulk_update_status(client, sample_task_data):
    """Test bulk status update."""
    resp1 = client.post("/api/tasks", json={**sample_task_data, "title": "Task 1"})
    resp2 = client.post("/api/tasks", json={**sample_task_data, "title": "Task 2"})
    client.post("/api/tasks", json={**sample_task_data, "title": "Task 3"})

    task_ids = [resp1.json()["id"], resp2.json()["id"]]

    response = client.post("/api/tasks/bulk/status", json={
        "task_ids": task_ids,
        "status": "completed"
    })

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert all(t["status"] == "completed" for t in data["tasks"])


def test_bulk_delete(client, sample_task_data):
    """Test bulk delete."""
    resp1 = client.post("/api/tasks", json={**sample_task_data, "title": "Delete 1"})
    resp2 = client.post("/api/tasks", json={**sample_task_data, "title": "Delete 2"})
    resp3 = client.post("/api/tasks", json={**sample_task_data, "title": "Keep"})

    task_ids = [resp1.json()["id"], resp2.json()["id"]]

    response = client.post("/api/tasks/bulk/delete", json={"task_ids": task_ids})

    assert response.status_code == 200
    assert response.json()["deleted_count"] == 2

    # Verify deletion
    assert client.get(f"/api/tasks/{resp1.json()['id']}").status_code == 404
    assert client.get(f"/api/tasks/{resp3.json()['id']}").status_code == 200


def test_recalculate_priorities(client, sample_task_data):
    """Test recalculating priorities."""
    client.post("/api/tasks", json=sample_task_data)
    client.post("/api/tasks", json=sample_task_data)

    response = client.post("/api/tasks/recalculate-priorities")

    assert response.status_code == 200
    assert response.json()["updated_count"] == 2


# Optional Initiatives Tests
def test_create_task_without_initiative(client, sample_task_data):
    """Test creating a task without an initiative."""
    response = client.post("/api/tasks", json=sample_task_data)
    assert response.status_code == 201

    data = response.json()
    assert data["initiative_id"] is None
    assert data["initiative_title"] is None


def test_create_task_with_initiative(client, test_db_session, sample_task_data):
    """Test creating a task linked to an initiative."""
    from src.models.initiative import Initiative, InitiativePriority

    # Create an initiative directly
    initiative = Initiative(
        title="Test Project",
        priority=InitiativePriority.HIGH,
    )
    test_db_session.add(initiative)
    test_db_session.commit()

    # Create task with initiative
    task_data = {**sample_task_data, "initiative_id": initiative.id}
    response = client.post("/api/tasks", json=task_data)
    assert response.status_code == 201

    data = response.json()
    assert data["initiative_id"] == initiative.id
    assert data["initiative_title"] == "Test Project"


def test_list_tasks_without_initiatives(client, sample_task_data):
    """Test listing tasks that don't have initiatives."""
    # Create multiple tasks without initiatives
    client.post("/api/tasks", json={**sample_task_data, "title": "Task 1"})
    client.post("/api/tasks", json={**sample_task_data, "title": "Task 2"})
    client.post("/api/tasks", json={**sample_task_data, "title": "Task 3"})

    response = client.get("/api/tasks")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] >= 3
    assert all(task["initiative_id"] is None for task in data["tasks"])


def test_update_task_remove_initiative(client, test_db_session, sample_task_data):
    """Test removing an initiative from a task."""
    from src.models.initiative import Initiative, InitiativePriority

    # Create an initiative
    initiative = Initiative(
        title="Project A",
        priority=InitiativePriority.MEDIUM,
    )
    test_db_session.add(initiative)
    test_db_session.commit()

    # Create task with initiative
    task_data = {**sample_task_data, "initiative_id": initiative.id}
    create_resp = client.post("/api/tasks", json=task_data)
    task_id = create_resp.json()["id"]

    # Verify it has initiative
    get_resp = client.get(f"/api/tasks/{task_id}")
    assert get_resp.json()["initiative_id"] == initiative.id

    # Remove initiative
    update_resp = client.put(f"/api/tasks/{task_id}", json={"clear_initiative": True})
    assert update_resp.status_code == 200
    assert update_resp.json()["initiative_id"] is None


def test_update_task_add_initiative(client, test_db_session, sample_task_data):
    """Test adding an initiative to a task that didn't have one."""
    from src.models.initiative import Initiative, InitiativePriority

    # Create an initiative
    initiative = Initiative(
        title="Project B",
        priority=InitiativePriority.HIGH,
    )
    test_db_session.add(initiative)
    test_db_session.commit()

    # Create task without initiative
    create_resp = client.post("/api/tasks", json=sample_task_data)
    task_id = create_resp.json()["id"]

    # Verify it has no initiative
    get_resp = client.get(f"/api/tasks/{task_id}")
    assert get_resp.json()["initiative_id"] is None

    # Add initiative
    update_resp = client.put(f"/api/tasks/{task_id}", json={"initiative_id": initiative.id})
    assert update_resp.status_code == 200
    assert update_resp.json()["initiative_id"] == initiative.id
    assert update_resp.json()["initiative_title"] == "Project B"


def test_mixed_tasks_with_and_without_initiatives(client, test_db_session, sample_task_data):
    """Test listing a mix of tasks with and without initiatives."""
    from src.models.initiative import Initiative, InitiativePriority

    # Create an initiative
    initiative = Initiative(
        title="Main Project",
        priority=InitiativePriority.HIGH,
    )
    test_db_session.add(initiative)
    test_db_session.commit()

    # Create tasks both with and without initiatives
    client.post("/api/tasks", json={**sample_task_data, "title": "Standalone 1"})
    client.post("/api/tasks", json={**sample_task_data, "title": "Project Task", "initiative_id": initiative.id})
    client.post("/api/tasks", json={**sample_task_data, "title": "Standalone 2"})

    response = client.get("/api/tasks")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] >= 3

    # Check mix of tasks
    tasks_with_initiative = [t for t in data["tasks"] if t["initiative_id"] is not None]
    tasks_without_initiative = [t for t in data["tasks"] if t["initiative_id"] is None]

    assert len(tasks_with_initiative) >= 1
    assert len(tasks_without_initiative) >= 2
    assert tasks_with_initiative[0]["initiative_title"] == "Main Project"


# ============================================================================
# Document Links API Tests
# ============================================================================


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
    assert "notion.so" in data["document_links"][1]
    assert data["id"] is not None


def test_create_task_with_empty_document_links(client, sample_task_data):
    """Test creating task with empty document_links list."""
    task_data = {**sample_task_data, "document_links": []}
    response = client.post("/api/tasks", json=task_data)

    assert response.status_code == 201
    assert response.json()["document_links"] == []


def test_create_task_without_document_links_field(client, sample_task_data):
    """Test creating task without document_links field (uses default empty list)."""
    response = client.post("/api/tasks", json=sample_task_data)

    assert response.status_code == 201
    data = response.json()
    assert "document_links" in data
    assert data["document_links"] == []


def test_filter_tasks_by_document_link(client, sample_task_data):
    """Test filtering tasks by document link via API."""
    # Create tasks with different links
    client.post("/api/tasks", json={
        **sample_task_data,
        "title": "Task 1",
        "document_links": ["https://docs.google.com/document/d/doc1"]
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
        "document_links": ["https://docs.google.com/document/d/doc1"]
    })
    client.post("/api/tasks", json={
        **sample_task_data,
        "title": "Task 2",
        "document_links": ["https://notion.so/page1"]
    })
    client.post("/api/tasks", json={
        **sample_task_data,
        "title": "Task 3",
        "document_links": ["https://github.com/org/repo/pull/123"]
    })

    # Filter by both Google Docs and Notion (should return both tasks)
    response = client.get("/api/tasks", params={
        "document_links": ["docs.google.com", "notion.so"]
    })

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    titles = {task["title"] for task in data["tasks"]}
    assert titles == {"Task 1", "Task 2"}


def test_update_task_document_links(client, sample_task_data):
    """Test updating document links via API."""
    # Create task without links
    response = client.post("/api/tasks", json=sample_task_data)
    task_id = response.json()["id"]

    # Update with document links
    response = client.put(f"/api/tasks/{task_id}", json={
        "document_links": ["https://new-link.com/doc123"]
    })

    assert response.status_code == 200
    data = response.json()
    assert len(data["document_links"]) == 1
    assert "new-link.com" in data["document_links"][0]


def test_update_task_add_document_links(client, sample_task_data):
    """Test adding links to existing task."""
    # Create task with one link
    response = client.post("/api/tasks", json={
        **sample_task_data,
        "document_links": ["https://docs.google.com/doc1"]
    })
    task_id = response.json()["id"]

    # Add more links
    response = client.put(f"/api/tasks/{task_id}", json={
        "document_links": [
            "https://docs.google.com/doc1",
            "https://notion.so/page1",
            "https://github.com/org/repo"
        ]
    })

    assert response.status_code == 200
    data = response.json()
    assert len(data["document_links"]) == 3


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
    """Test API rejects invalid URLs."""
    task_data = {
        **sample_task_data,
        "document_links": ["not-a-url"]
    }
    response = client.post("/api/tasks", json=task_data)

    # Should return 422 validation error
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any("url" in str(error).lower() for error in errors)


def test_create_task_with_javascript_url(client, sample_task_data):
    """Test API rejects javascript: URLs."""
    task_data = {
        **sample_task_data,
        "document_links": ["javascript:alert(1)"]
    }
    response = client.post("/api/tasks", json=task_data)

    # Should return 422 validation error
    assert response.status_code == 422


def test_create_task_with_file_url(client, sample_task_data):
    """Test API rejects file:// URLs."""
    task_data = {
        **sample_task_data,
        "document_links": ["file:///etc/passwd"]
    }
    response = client.post("/api/tasks", json=task_data)

    # Should return 422 validation error
    assert response.status_code == 422


def test_create_task_with_too_many_links(client, sample_task_data):
    """Test API rejects more than 20 links."""
    task_data = {
        **sample_task_data,
        "document_links": [f"https://example.com/doc{i}" for i in range(25)]
    }
    response = client.post("/api/tasks", json=task_data)

    # Should return 422 validation error
    assert response.status_code == 422
    assert "20" in str(response.json()["detail"])


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
    assert "docs.google.com" in data["document_links"][0]


def test_document_links_with_commas_in_url(client, sample_task_data):
    """Test that URLs with commas in query params are handled correctly."""
    url_with_commas = "https://example.com/doc?tags=work,urgent&id=123"
    task_data = {
        **sample_task_data,
        "document_links": [url_with_commas]
    }
    response = client.post("/api/tasks", json=task_data)

    assert response.status_code == 201
    data = response.json()
    assert len(data["document_links"]) == 1
    # URL should be intact, not split by commas
    assert data["document_links"][0] == url_with_commas


def test_document_links_with_special_characters(client, sample_task_data):
    """Test URLs with special characters are handled."""
    urls = [
        "https://example.com/doc?param=value&other=test",
        "https://example.com/doc#section",
        "https://example.com/doc?query=hello%20world"
    ]
    task_data = {
        **sample_task_data,
        "document_links": urls
    }
    response = client.post("/api/tasks", json=task_data)

    assert response.status_code == 201
    data = response.json()
    assert len(data["document_links"]) == 3
    for i, url in enumerate(urls):
        assert data["document_links"][i] == url


def test_pagination_with_document_links(client, sample_task_data):
    """Test pagination works correctly with document_links."""
    # Create 15 tasks with links
    for i in range(15):
        client.post("/api/tasks", json={
            **sample_task_data,
            "title": f"Task {i}",
            "document_links": [f"https://example.com/doc{i}"]
        })

    # Get first page
    response = client.get("/api/tasks?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["tasks"]) == 10
    assert all("document_links" in task for task in data["tasks"])

    # Get second page
    response = client.get("/api/tasks?limit=10&offset=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["tasks"]) >= 5
    assert all("document_links" in task for task in data["tasks"])
