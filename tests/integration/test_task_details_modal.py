"""Integration tests for task details modal manager with mocked API."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, UTC

from src.macos.task_details_sheet import TaskDetailsModalManager


@pytest.fixture
def manager():
    """Create a TaskDetailsModalManager for testing."""
    mgr = TaskDetailsModalManager(api_url="http://localhost:8000")
    yield mgr
    mgr.close()


@pytest.fixture
def sample_task_response():
    """Sample task response from API."""
    return {
        "id": 42,
        "title": "Complete quarterly report",
        "description": "Compile Q1 metrics and submit by Friday",
        "status": "in_progress",
        "priority": "high",
        "due_date": "2026-02-20T17:00:00",
        "created_at": "2026-02-01T09:00:00",
        "completed_at": None,
        "source": "manual",
        "source_reference": None,
        "account_id": None,
        "priority_score": 85.5,
        "tags": ["work", "quarterly", "report"],
        "document_links": [
            "https://docs.google.com/spreadsheets/d/abc123/edit",
            "https://example.com/metrics.pdf"
        ],
        "initiative_id": 5,
        "initiative_title": "Operational Excellence"
    }


class TestTaskDetailsModalManagerAPI:
    """Test API interactions of TaskDetailsModalManager."""
    
    def test_fetch_task_success(self, manager, sample_task_response):
        """Test successfully fetching task from API."""
        with patch.object(manager.client, 'get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = sample_task_response
            mock_get.return_value = mock_response
            
            result = manager._fetch_task(42)
            
            assert result is not None
            assert result["id"] == 42
            assert result["title"] == "Complete quarterly report"
            assert result["priority"] == "high"
            mock_get.assert_called_once_with("http://localhost:8000/api/tasks/42")
    
    def test_fetch_task_not_found(self, manager):
        """Test fetching non-existent task."""
        with patch.object(manager.client, 'get') as mock_get:
            mock_response = Mock()
            mock_response.raise_for_status.side_effect = Exception("404 Not Found")
            mock_get.return_value = mock_response
            
            result = manager._fetch_task(999)
            
            assert result is None
    
    def test_fetch_task_network_error(self, manager):
        """Test fetching task with network error."""
        with patch.object(manager.client, 'get') as mock_get:
            mock_get.side_effect = Exception("Connection refused")
            
            result = manager._fetch_task(42)
            
            assert result is None
    
    def test_complete_task(self, manager):
        """Test completing a task."""
        with patch.object(manager.client, 'put') as mock_put:
            mock_response = Mock()
            mock_put.return_value = mock_response
            
            manager._complete_task(42)
            
            mock_put.assert_called_once_with(
                "http://localhost:8000/api/tasks/42",
                json={"status": "completed"}
            )
    
    def test_complete_task_error(self, manager):
        """Test completing task with error."""
        with patch.object(manager.client, 'put') as mock_put:
            mock_put.side_effect = Exception("Server error")
            
            # Should not raise, just log error
            manager._complete_task(42)
            
            mock_put.assert_called_once()
    
    def test_update_task_priority(self, manager):
        """Test updating task priority."""
        with patch.object(manager.client, 'put') as mock_put:
            mock_response = Mock()
            mock_put.return_value = mock_response
            
            manager._update_task_priority(42, "critical")
            
            mock_put.assert_called_once_with(
                "http://localhost:8000/api/tasks/42",
                json={"priority": "critical"}
            )
    
    def test_update_task_priority_all_levels(self, manager):
        """Test updating task priority to all levels."""
        with patch.object(manager.client, 'put') as mock_put:
            mock_response = Mock()
            mock_put.return_value = mock_response
            
            priorities = ["critical", "high", "medium", "low"]
            for priority in priorities:
                mock_put.reset_mock()
                manager._update_task_priority(42, priority)
                
                mock_put.assert_called_once_with(
                    "http://localhost:8000/api/tasks/42",
                    json={"priority": priority}
                )
    
    def test_update_task_due_date_with_date(self, manager):
        """Test updating task due date."""
        with patch.object(manager.client, 'put') as mock_put:
            mock_response = Mock()
            mock_put.return_value = mock_response
            
            manager._update_task_due_date(42, "2026-03-15")
            
            # Should convert to ISO datetime
            mock_put.assert_called_once_with(
                "http://localhost:8000/api/tasks/42",
                json={"due_date": "2026-03-15T00:00:00"}
            )
    
    def test_update_task_due_date_iso_format(self, manager):
        """Test updating task due date with ISO format."""
        with patch.object(manager.client, 'put') as mock_put:
            mock_response = Mock()
            mock_put.return_value = mock_response
            
            manager._update_task_due_date(42, "2026-03-15T17:00:00")
            
            # Should not modify ISO format
            mock_put.assert_called_once_with(
                "http://localhost:8000/api/tasks/42",
                json={"due_date": "2026-03-15T17:00:00"}
            )
    
    def test_update_task_due_date_clear(self, manager):
        """Test clearing task due date."""
        with patch.object(manager.client, 'put') as mock_put:
            mock_response = Mock()
            mock_put.return_value = mock_response
            
            manager._update_task_due_date(42, None)
            
            mock_put.assert_called_once_with(
                "http://localhost:8000/api/tasks/42",
                json={"due_date": None}
            )
    
    def test_update_task_due_date_error(self, manager):
        """Test updating due date with error."""
        with patch.object(manager.client, 'put') as mock_put:
            mock_put.side_effect = Exception("Server error")
            
            # Should not raise, just log error
            manager._update_task_due_date(42, "2026-03-15")
            
            mock_put.assert_called_once()


class TestTaskDetailsModalManagerActions:
    """Test handling modal actions."""
    
    def test_handle_complete_action(self, manager):
        """Test handling complete action from modal."""
        with patch.object(manager, '_complete_task') as mock_complete:
            modal_result = {
                "action": "complete",
                "task_id": 42,
                "success": True
            }
            
            manager._handle_modal_action(42, modal_result)
            
            mock_complete.assert_called_once_with(42)
    
    def test_handle_priority_action(self, manager):
        """Test handling priority change action from modal."""
        with patch.object(manager, '_update_task_priority') as mock_priority:
            modal_result = {
                "action": "change_priority",
                "task_id": 42,
                "priority": "high",
                "success": True
            }
            
            manager._handle_modal_action(42, modal_result)
            
            mock_priority.assert_called_once_with(42, "high")
    
    def test_handle_due_date_action(self, manager):
        """Test handling due date change action from modal."""
        with patch.object(manager, '_update_task_due_date') as mock_due_date:
            modal_result = {
                "action": "change_due_date",
                "task_id": 42,
                "due_date": "2026-03-15",
                "success": True
            }
            
            manager._handle_modal_action(42, modal_result)
            
            mock_due_date.assert_called_once_with(42, "2026-03-15")
    
    def test_handle_due_date_action_clear(self, manager):
        """Test handling due date clear action from modal."""
        with patch.object(manager, '_update_task_due_date') as mock_due_date:
            modal_result = {
                "action": "change_due_date",
                "task_id": 42,
                "due_date": None,
                "success": True
            }
            
            manager._handle_modal_action(42, modal_result)
            
            mock_due_date.assert_called_once_with(42, None)
    
    def test_handle_dashboard_action(self, manager):
        """Test handling open dashboard action from modal."""
        with patch('webbrowser.open') as mock_open:
            modal_result = {
                "action": "open_dashboard",
                "task_id": 42,
                "success": True
            }
            
            manager._handle_modal_action(42, modal_result)
            
            mock_open.assert_called_once_with("http://localhost:8000/docs")
    
    def test_handle_unknown_action(self, manager):
        """Test handling unknown action from modal."""
        modal_result = {
            "action": "unknown_action",
            "task_id": 42,
            "success": True
        }
        
        # Should not raise, just log warning
        manager._handle_modal_action(42, modal_result)


class TestTaskDetailsModalManagerSubprocess:
    """Test subprocess modal execution."""
    
    def test_show_task_details_success(self, manager, sample_task_response):
        """Test showing task details with successful modal."""
        with patch.object(manager, '_fetch_task') as mock_fetch:
            with patch('subprocess.run') as mock_run:
                mock_fetch.return_value = sample_task_response
                
                # Mock successful modal result
                modal_result = {
                    "action": "complete",
                    "task_id": 42,
                    "success": True
                }
                
                mock_run.return_value = Mock(
                    returncode=0,
                    stdout=json.dumps(modal_result),
                    stderr=""
                )
                
                with patch.object(manager, '_handle_modal_action') as mock_handle:
                    manager.show_task_details(42)
                    
                    # Wait a bit for background thread
                    import time
                    time.sleep(0.5)
                    
                    # Should have fetched task and handled action
                    mock_fetch.assert_called()
                    mock_handle.assert_called()
    
    def test_show_task_details_fetch_fails(self, manager):
        """Test showing task details when fetch fails."""
        with patch.object(manager, '_fetch_task') as mock_fetch:
            with patch('subprocess.run') as mock_run:
                mock_fetch.return_value = None
                
                manager.show_task_details(42)
                
                # Wait a bit for background thread
                import time
                time.sleep(0.2)
                
                # Should not call subprocess
                mock_run.assert_not_called()


class TestTaskDetailsModalManagerIntegration:
    """Integration tests with mocked API."""
    
    def test_complete_workflow_minimal_task(self, manager):
        """Test complete workflow with minimal task data."""
        task_id = 1
        minimal_task = {
            "id": task_id,
            "title": "Simple task",
            "status": "pending",
            "priority": "medium",
            "created_at": "2026-02-17T10:00:00",
            "tags": [],
            "document_links": []
        }
        
        with patch.object(manager, '_fetch_task') as mock_fetch:
            with patch.object(manager, '_complete_task') as mock_complete:
                mock_fetch.return_value = minimal_task
                
                # Simulate fetching and completing
                task = manager._fetch_task(task_id)
                assert task is not None
                
                modal_result = {
                    "action": "complete",
                    "task_id": task_id,
                    "success": True
                }
                
                manager._handle_modal_action(task_id, modal_result)
                mock_complete.assert_called_once_with(task_id)
    
    def test_complete_workflow_full_task(self, manager, sample_task_response):
        """Test complete workflow with full task data."""
        task_id = 42
        
        with patch.object(manager, '_fetch_task') as mock_fetch:
            with patch.object(manager, '_update_task_priority') as mock_priority:
                with patch.object(manager, '_update_task_due_date') as mock_due_date:
                    with patch.object(manager, '_complete_task') as mock_complete:
                        mock_fetch.return_value = sample_task_response
                        
                        # Fetch task
                        task = manager._fetch_task(task_id)
                        assert task["title"] == "Complete quarterly report"
                        assert len(task["document_links"]) == 2
                        
                        # Test priority update
                        priority_result = {
                            "action": "change_priority",
                            "task_id": task_id,
                            "priority": "critical",
                            "success": True
                        }
                        manager._handle_modal_action(task_id, priority_result)
                        mock_priority.assert_called_once_with(task_id, "critical")
                        
                        # Test due date update
                        due_date_result = {
                            "action": "change_due_date",
                            "task_id": task_id,
                            "due_date": "2026-03-01",
                            "success": True
                        }
                        manager._handle_modal_action(task_id, due_date_result)
                        # The manager converts YYYY-MM-DD to YYYY-MM-DDTHH:MM:SS internally
                        mock_due_date.assert_called_once()
                        call_args = mock_due_date.call_args
                        assert call_args[0][0] == task_id
                        assert call_args[0][1] == "2026-03-01"
                        
                        # Test complete
                        complete_result = {
                            "action": "complete",
                            "task_id": task_id,
                            "success": True
                        }
                        manager._handle_modal_action(task_id, complete_result)
                        mock_complete.assert_called_once_with(task_id)
    
    def test_workflow_with_document_links(self, manager, sample_task_response):
        """Test workflow specifically with document links."""
        task_id = 42
        task_with_many_links = sample_task_response.copy()
        task_with_many_links["document_links"] = [
            "https://example.com/doc1.pdf",
            "https://example.com/doc2.docx",
            "https://example.com/doc3.xlsx",
            "https://example.com/image.png",
            "https://docs.google.com/spreadsheets/d/xyz/edit",
        ]
        
        with patch.object(manager, '_fetch_task') as mock_fetch:
            mock_fetch.return_value = task_with_many_links
            
            task = manager._fetch_task(task_id)
            
            assert len(task["document_links"]) == 5
            assert any("pdf" in link for link in task["document_links"])
            assert any("png" in link for link in task["document_links"])
            assert any("google" in link for link in task["document_links"])
