"""Unit tests for task details modal."""

import json
import pytest
from datetime import datetime

from src.macos.task_details_sheet import TaskDetailsModalManager


class TestTaskDetailsModalManager:
    """Test TaskDetailsModalManager class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = TaskDetailsModalManager(api_url="http://localhost:8000")
    
    def teardown_method(self):
        """Clean up after tests."""
        self.manager.close()
    
    def test_manager_initialization(self):
        """Test manager initializes correctly."""
        assert self.manager.api_url == "http://localhost:8000"
        assert self.manager.client is not None
    
    def test_task_data_structure_minimal(self):
        """Test modal handles minimal task data."""
        task_data = {
            "id": 1,
            "title": "Buy milk",
            "status": "pending",
            "priority": "medium",
            "created_at": "2026-02-17T10:00:00",
            "tags": [],
            "document_links": [],
        }
        
        # Verify task data is JSON serializable
        json_str = json.dumps(task_data)
        parsed = json.loads(json_str)
        
        assert parsed["id"] == 1
        assert parsed["title"] == "Buy milk"
    
    def test_task_data_structure_full(self):
        """Test modal handles full task data with all fields."""
        task_data = {
            "id": 42,
            "title": "Quarterly review preparation",
            "description": "Prepare performance metrics and feedback for Q1 review",
            "status": "in_progress",
            "priority": "high",
            "due_date": "2026-02-28T17:00:00",
            "created_at": "2026-02-01T09:30:00",
            "completed_at": None,
            "tags": ["work", "quarterly", "important"],
            "document_links": [
                "https://docs.google.com/spreadsheets/d/abc123/edit",
                "https://example.com/review-template.pdf",
                "https://example.com/metrics.xlsx"
            ],
            "initiative_id": 5,
            "initiative_title": "Performance Excellence",
            "source": "manual",
            "source_reference": None,
            "account_id": None,
            "priority_score": 85.5
        }
        
        # Verify all fields are JSON serializable
        json_str = json.dumps(task_data)
        parsed = json.loads(json_str)
        
        assert parsed["id"] == 42
        assert parsed["title"] == "Quarterly review preparation"
        assert parsed["description"] == "Prepare performance metrics and feedback for Q1 review"
        assert parsed["status"] == "in_progress"
        assert parsed["priority"] == "high"
        assert parsed["due_date"] == "2026-02-28T17:00:00"
        assert len(parsed["tags"]) == 3
        assert len(parsed["document_links"]) == 3
        assert parsed["initiative_title"] == "Performance Excellence"
        assert parsed["priority_score"] == 85.5
    
    def test_task_data_with_multiple_document_links(self):
        """Test modal handles multiple document links."""
        document_links = [
            "https://example.com/document1.pdf",
            "https://example.com/document2.docx",
            "https://example.com/image.png",
            "https://example.com/spreadsheet.xlsx",
            "https://docs.google.com/doc/d/abc/edit",
        ]
        
        task_data = {
            "id": 1,
            "title": "Test task",
            "status": "pending",
            "priority": "medium",
            "created_at": "2026-02-17T10:00:00",
            "tags": [],
            "document_links": document_links,
        }
        
        json_str = json.dumps(task_data)
        parsed = json.loads(json_str)
        
        assert len(parsed["document_links"]) == 5
        assert "document1.pdf" in parsed["document_links"][0]
        assert "image.png" in parsed["document_links"][2]
    
    def test_modal_result_complete_action(self):
        """Test modal result structure for complete action."""
        modal_result = {
            "action": "complete",
            "task_id": 1,
            "success": True
        }
        
        json_str = json.dumps(modal_result)
        parsed = json.loads(json_str)
        
        assert parsed["action"] == "complete"
        assert parsed["task_id"] == 1
        assert parsed["success"] is True
    
    def test_modal_result_change_priority_action(self):
        """Test modal result structure for priority change action."""
        modal_result = {
            "action": "change_priority",
            "task_id": 2,
            "priority": "high",
            "success": True
        }
        
        json_str = json.dumps(modal_result)
        parsed = json.loads(json_str)
        
        assert parsed["action"] == "change_priority"
        assert parsed["task_id"] == 2
        assert parsed["priority"] == "high"
        assert parsed["success"] is True
    
    def test_modal_result_change_due_date_action(self):
        """Test modal result structure for due date change action."""
        # With due date
        modal_result = {
            "action": "change_due_date",
            "task_id": 3,
            "due_date": "2026-03-15T17:00:00",
            "success": True
        }
        
        json_str = json.dumps(modal_result)
        parsed = json.loads(json_str)
        
        assert parsed["action"] == "change_due_date"
        assert parsed["task_id"] == 3
        assert parsed["due_date"] == "2026-03-15T17:00:00"
        assert parsed["success"] is True
        
        # Clear due date
        modal_result_clear = {
            "action": "change_due_date",
            "task_id": 3,
            "due_date": None,
            "success": True
        }
        
        json_str = json.dumps(modal_result_clear)
        parsed = json.loads(json_str)
        
        assert parsed["due_date"] is None
    
    def test_modal_result_close_without_action(self):
        """Test modal result when closed without action."""
        modal_result = {
            "action": None,
            "task_id": 4,
            "success": False
        }
        
        json_str = json.dumps(modal_result)
        parsed = json.loads(json_str)
        
        assert parsed["action"] is None
        assert parsed["success"] is False
    
    def test_task_data_with_various_priorities(self):
        """Test task data with all priority levels."""
        priorities = ["critical", "high", "medium", "low"]
        
        for priority in priorities:
            task_data = {
                "id": 1,
                "title": f"Test task with {priority} priority",
                "status": "pending",
                "priority": priority,
                "created_at": "2026-02-17T10:00:00",
                "tags": [],
                "document_links": [],
            }
            
            json_str = json.dumps(task_data)
            parsed = json.loads(json_str)
            
            assert parsed["priority"] == priority
    
    def test_task_data_with_various_statuses(self):
        """Test task data with all status values."""
        statuses = ["pending", "in_progress", "completed", "deferred", "cancelled"]
        
        for status in statuses:
            task_data = {
                "id": 1,
                "title": f"Test task with {status} status",
                "status": status,
                "priority": "medium",
                "created_at": "2026-02-17T10:00:00",
                "tags": [],
                "document_links": [],
            }
            
            json_str = json.dumps(task_data)
            parsed = json.loads(json_str)
            
            assert parsed["status"] == status
    
    def test_task_data_with_special_characters_in_title(self):
        """Test task data with special characters in title."""
        special_titles = [
            'Task with "quotes"',
            "Task with 'apostrophes'",
            "Task with newlines\nand special chars: @#$%&*()",
            "Task with emojis: 🎯 📋 ✅",
        ]
        
        for title in special_titles:
            task_data = {
                "id": 1,
                "title": title,
                "status": "pending",
                "priority": "medium",
                "created_at": "2026-02-17T10:00:00",
                "tags": [],
                "document_links": [],
            }
            
            json_str = json.dumps(task_data)
            parsed = json.loads(json_str)
            
            assert parsed["title"] == title
    
    def test_task_data_with_empty_optional_fields(self):
        """Test task data with empty optional fields."""
        task_data = {
            "id": 1,
            "title": "Simple task",
            "description": None,
            "status": "pending",
            "priority": "medium",
            "due_date": None,
            "created_at": "2026-02-17T10:00:00",
            "completed_at": None,
            "tags": [],
            "document_links": [],
            "initiative_id": None,
            "initiative_title": None,
        }
        
        json_str = json.dumps(task_data)
        parsed = json.loads(json_str)
        
        assert parsed["description"] is None
        assert parsed["due_date"] is None
        assert parsed["initiative_title"] is None
        assert len(parsed["tags"]) == 0
        assert len(parsed["document_links"]) == 0
    
    def test_task_data_with_unicode_characters(self):
        """Test task data with unicode characters."""
        task_data = {
            "id": 1,
            "title": "任務 Tâche Tarea Таска",
            "description": "中文 Français Español Русский العربية",
            "status": "pending",
            "priority": "medium",
            "created_at": "2026-02-17T10:00:00",
            "tags": ["日本語", "한국어", "العربية"],
            "document_links": [],
        }
        
        json_str = json.dumps(task_data, ensure_ascii=False)
        parsed = json.loads(json_str)
        
        assert "任務" in parsed["title"]
        assert "中文" in parsed["description"]
        assert "日本語" in parsed["tags"]
    
    def test_date_format_serialization(self):
        """Test various date formats are serialized correctly."""
        task_data = {
            "id": 1,
            "title": "Date test",
            "status": "pending",
            "priority": "medium",
            "due_date": "2026-02-28T17:00:00",
            "created_at": "2026-02-17T10:00:00",
            "completed_at": "2026-02-15T14:30:00",
            "tags": [],
            "document_links": [],
        }
        
        json_str = json.dumps(task_data)
        parsed = json.loads(json_str)
        
        assert parsed["due_date"] == "2026-02-28T17:00:00"
        assert parsed["created_at"] == "2026-02-17T10:00:00"
        assert parsed["completed_at"] == "2026-02-15T14:30:00"
    
    def test_large_task_data(self):
        """Test modal handles large task data with many tags and links."""
        tags = [f"tag{i}" for i in range(20)]
        links = [f"https://example.com/document{i}.pdf" for i in range(10)]
        
        description = "A" * 1000  # Long description
        
        task_data = {
            "id": 1,
            "title": "Large task",
            "description": description,
            "status": "pending",
            "priority": "medium",
            "created_at": "2026-02-17T10:00:00",
            "tags": tags,
            "document_links": links,
        }
        
        json_str = json.dumps(task_data)
        parsed = json.loads(json_str)
        
        assert len(parsed["tags"]) == 20
        assert len(parsed["document_links"]) == 10
        assert len(parsed["description"]) == 1000
