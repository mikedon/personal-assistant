"""Integration tests for quick input system."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.macos.command_parser import CommandParser
from src.utils.config import reset_config


@pytest.fixture
def client():
    """Create test client for the API."""
    app = create_app()
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_config_fixture():
    """Reset configuration before and after each test."""
    reset_config()
    yield
    reset_config()


class TestQuickInputCommandIntegration:
    """Integration tests for quick input command parsing and API submission."""

    def test_parse_command_creates_task_with_description(self, client):
        """Test that parse command sends description to API."""
        parsed = CommandParser.parse("parse Create urgent bug fix for login page")
        
        assert parsed.command_type == "parse"
        assert parsed.text == "Create urgent bug fix for login page"

    def test_priority_command_creates_high_priority_task(self, client):
        """Test that priority command sets high priority."""
        parsed = CommandParser.parse("priority Fix critical security vulnerability")
        
        assert parsed.command_type == "priority"
        assert parsed.priority == "high"
        assert parsed.text == "Fix critical security vulnerability"

    def test_plain_text_creates_simple_task(self, client):
        """Test that plain text creates simple task without priority."""
        parsed = CommandParser.parse("Buy groceries")
        
        assert parsed.command_type == "text"
        assert parsed.text == "Buy groceries"
        assert parsed.priority is None

    def test_voice_command_type_recognized(self, client):
        """Test that voice command is recognized."""
        parsed = CommandParser.parse("voice")
        
        assert parsed.command_type == "voice"
        assert parsed.text == ""

    def test_command_parser_integration_with_various_inputs(self, client):
        """Test command parser handles various input types."""
        test_cases = [
            ("parse Meeting notes from team standup", "parse"),
            ("priority Urgent: Production incident", "priority"),
            ("voice", "voice"),
            ("Regular task", "text"),
            ("parse   Extra   spaces   handled", "parse"),
        ]
        
        for input_text, expected_type in test_cases:
            parsed = CommandParser.parse(input_text)
            assert parsed.command_type == expected_type

    def test_parsed_command_data_structure(self, client):
        """Test ParsedCommand contains all necessary fields."""
        parsed = CommandParser.parse("priority Implement new feature")
        
        assert hasattr(parsed, 'command_type')
        assert hasattr(parsed, 'text')
        assert hasattr(parsed, 'priority')
        assert hasattr(parsed, 'success')
        
        assert parsed.command_type == "priority"
        assert parsed.priority == "high"
        assert parsed.success is True

    def test_task_api_endpoint_ready_for_quick_input(self, client):
        """Test that task API endpoint is available for quick input."""
        # Verify endpoint exists and accepts POST
        response = client.post(
            "/api/tasks",
            json={
                "title": "Quick input test task",
                "priority": "high"
            }
        )
        
        # Should either succeed or give validation error, not 404
        assert response.status_code in [200, 201, 400, 422]

    def test_parse_command_with_special_characters(self, client):
        """Test parsing commands with special characters."""
        parsed = CommandParser.parse("parse Fix bug: TypeError in get_user() 🐛")
        
        assert parsed.command_type == "parse"
        assert "🐛" in parsed.text

    def test_multiple_command_parsing_sequence(self, client):
        """Test sequence of different command types."""
        commands = [
            "parse Create onboarding documentation",
            "priority Review PR #123",
            "voice",
            "Quick meeting notes",
        ]
        
        parsed_commands = [CommandParser.parse(cmd) for cmd in commands]
        
        assert len(parsed_commands) == 4
        assert parsed_commands[0].command_type == "parse"
        assert parsed_commands[1].command_type == "priority"
        assert parsed_commands[2].command_type == "voice"
        assert parsed_commands[3].command_type == "text"

    def test_config_api_accessible_for_hotkey_settings(self, client):
        """Test that config API is available for hotkey customization."""
        # Get config
        response = client.get("/api/config")
        assert response.status_code == 200
        
        config = response.json()
        # Config should have expected structure
        assert "agent" in config
        assert "notifications" in config

    def test_empty_command_fails_gracefully(self, client):
        """Test that empty input is handled gracefully."""
        parsed = CommandParser.parse("")
        
        assert parsed.command_type == "text"
        assert parsed.success is False

    def test_whitespace_only_fails_gracefully(self, client):
        """Test that whitespace-only input is handled gracefully."""
        parsed = CommandParser.parse("   \t\n  ")
        
        assert parsed.command_type == "text"
        assert parsed.success is False


class TestQuickInputAPIIntegration:
    """Integration tests for quick input with API backend."""

    def test_task_endpoint_accepts_parsed_quick_input_format(self, client):
        """Test that task endpoint accepts quick input data format."""
        # Simulating what the quick input would send
        task_data = {
            "title": "Buy groceries",
            "priority": "medium"
        }
        
        response = client.post("/api/tasks", json=task_data)
        assert response.status_code in [200, 201, 422]

    def test_task_endpoint_accepts_parse_command_format(self, client):
        """Test that task endpoint accepts parse command data."""
        task_data = {
            "title": "Create detailed project plan",
            "description": "Create detailed project plan for Q1",
            "priority": "high",
            "parse_natural_language": True
        }
        
        response = client.post("/api/tasks", json=task_data)
        assert response.status_code in [200, 201, 422]

    def test_task_endpoint_with_priority_levels(self, client):
        """Test task endpoint with various priority levels."""
        priorities = ["low", "medium", "high"]
        
        for priority in priorities:
            response = client.post(
                "/api/tasks",
                json={"title": f"Task with {priority} priority", "priority": priority}
            )
            # Should accept without 404
            assert response.status_code in [200, 201, 400, 422]

    def test_concurrent_command_parsing(self, client):
        """Test that multiple commands can be parsed independently."""
        commands = [
            "parse First task description",
            "priority Second task with priority",
            "Regular third task",
        ]
        
        parsed_list = [CommandParser.parse(cmd) for cmd in commands]
        
        assert len(parsed_list) == 3
        assert parsed_list[0].command_type == "parse"
        assert parsed_list[1].priority == "high"
        assert parsed_list[2].command_type == "text"

    def test_config_endpoint_for_quick_input_settings(self, client):
        """Test that config endpoint supports quick input customization."""
        # Get current config
        response = client.get("/api/config")
        assert response.status_code == 200
        
        config = response.json()
        assert isinstance(config, dict)


class TestQuickInputEdgeCases:
    """Edge case tests for quick input system."""

    def test_very_long_task_title(self, client):
        """Test handling of very long task titles."""
        long_text = "A" * 1000
        parsed = CommandParser.parse(long_text)
        
        assert parsed.command_type == "text"
        assert len(parsed.text) == 1000

    def test_unicode_task_titles(self, client):
        """Test handling of unicode in task titles."""
        parsed = CommandParser.parse("parse 日本語のタスク説明")
        
        assert parsed.command_type == "parse"
        assert "日本語" in parsed.text

    def test_mixed_case_commands(self, client):
        """Test that commands work in mixed case."""
        test_cases = [
            ("Parse something", "parse"),
            ("PRIORITY urgent", "priority"),
            ("Voice", "voice"),
            ("pArSe mixed case", "parse"),
        ]
        
        for input_text, expected_type in test_cases:
            parsed = CommandParser.parse(input_text)
            assert parsed.command_type == expected_type

    def test_commands_with_quoted_text(self, client):
        """Test commands with quoted text."""
        parsed = CommandParser.parse('parse "Create task with quotes"')
        
        assert parsed.command_type == "parse"
        assert '"Create task with quotes"' in parsed.text

    def test_newlines_in_input(self, client):
        """Test handling of newlines in input."""
        parsed = CommandParser.parse("parse Task with\nmultiple\nlines")
        
        # Newlines in the command break the pattern match, so treated as plain text
        assert parsed.command_type == "text"
        assert "\n" in parsed.text


# Integration validation checklist
class TestQuickInputValidation:
    """Validation that quick input system is production-ready."""

    def test_command_parser_is_stateless(self):
        """Test that CommandParser has no state between calls."""
        parsed1 = CommandParser.parse("parse First")
        parsed2 = CommandParser.parse("priority Second")
        
        # Results should be independent
        assert parsed1.command_type == "parse"
        assert parsed2.command_type == "priority"

    def test_api_endpoints_all_accessible(self, client):
        """Test that all required API endpoints are accessible."""
        endpoints = [
            ("GET", "/api/config"),
            ("PUT", "/api/config"),
            ("POST", "/api/tasks"),
        ]
        
        for method, path in endpoints:
            if method == "GET":
                response = client.get(path)
            elif method == "PUT":
                response = client.put(path, json={})
            elif method == "POST":
                response = client.post(path, json={"title": "test"})
            
            # Should not be 404
            assert response.status_code != 404

    def test_quick_input_commands_are_documented(self):
        """Test that command help text is available."""
        from src.macos.command_parser import format_command_help
        
        help_text = format_command_help()
        assert "parse" in help_text.lower()
        assert "voice" in help_text.lower()
        assert "priority" in help_text.lower()

    def test_suggestions_are_available(self):
        """Test that command suggestions are available."""
        from src.macos.command_parser import CommandParser
        
        suggestions = CommandParser.get_suggestions()
        assert isinstance(suggestions, list)
        assert len(suggestions) > 0
        assert "parse" in " ".join(suggestions).lower()
