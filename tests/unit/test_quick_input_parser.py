"""Unit tests for quick input command parser."""

import pytest

from src.macos.command_parser import CommandParser, ParsedCommand, format_command_help


class TestCommandParser:
    """Tests for CommandParser."""

    def test_parse_plain_text(self):
        """Test parsing plain text as a task title."""
        result = CommandParser.parse("Buy groceries")
        assert result.command_type == "text"
        assert result.text == "Buy groceries"
        assert result.priority is None
        assert result.success is True

    def test_parse_plain_text_with_special_chars(self):
        """Test parsing text with special characters."""
        result = CommandParser.parse("Fix bug: TypeError in get_user() 🐛")
        assert result.command_type == "text"
        assert result.text == "Fix bug: TypeError in get_user() 🐛"

    def test_parse_command(self):
        """Test parsing parse command."""
        result = CommandParser.parse("parse Create a task about project requirements")
        assert result.command_type == "parse"
        assert result.text == "Create a task about project requirements"

    def test_parse_command_case_insensitive(self):
        """Test parse command is case insensitive."""
        result = CommandParser.parse("PARSE Something to do")
        assert result.command_type == "parse"
        assert result.text == "Something to do"

    def test_parse_command_with_extra_spaces(self):
        """Test parse command with multiple spaces."""
        result = CommandParser.parse("parse   Extra    spaces   in   text")
        assert result.command_type == "parse"
        assert "Extra" in result.text

    def test_voice_command(self):
        """Test parsing voice command."""
        result = CommandParser.parse("voice")
        assert result.command_type == "voice"
        assert result.text == ""
        assert result.success is True

    def test_voice_command_case_insensitive(self):
        """Test voice command is case insensitive."""
        result = CommandParser.parse("VOICE")
        assert result.command_type == "voice"

    def test_voice_command_with_spaces(self):
        """Test voice command with trailing spaces."""
        result = CommandParser.parse("voice  ")
        assert result.command_type == "voice"

    def test_priority_command(self):
        """Test parsing priority command."""
        result = CommandParser.parse("priority Fix critical bug")
        assert result.command_type == "priority"
        assert result.text == "Fix critical bug"
        assert result.priority == "high"

    def test_priority_command_case_insensitive(self):
        """Test priority command is case insensitive."""
        result = CommandParser.parse("PRIORITY Important task")
        assert result.command_type == "priority"
        assert result.text == "Important task"

    def test_empty_input(self):
        """Test parsing empty input."""
        result = CommandParser.parse("")
        assert result.command_type == "text"
        assert result.text == ""
        assert result.success is False

    def test_whitespace_only_input(self):
        """Test parsing input with only whitespace."""
        result = CommandParser.parse("   \t\n  ")
        assert result.command_type == "text"
        assert result.text == ""
        assert result.success is False

    def test_parse_command_no_args(self):
        """Test parse command without arguments."""
        result = CommandParser.parse("parse")
        # Should fail to match pattern and be treated as plain text
        assert result.command_type == "text"
        assert result.text == "parse"

    def test_priority_command_no_args(self):
        """Test priority command without arguments."""
        result = CommandParser.parse("priority")
        # Should fail to match pattern and be treated as plain text
        assert result.command_type == "text"
        assert result.text == "priority"

    def test_priority_with_emoji(self):
        """Test priority command with emoji in text."""
        result = CommandParser.parse("priority Urgent 🚨 system downtime")
        assert result.command_type == "priority"
        assert "🚨" in result.text

    def test_parse_with_long_text(self):
        """Test parse command with very long text."""
        long_text = "This is a very long description " * 20
        result = CommandParser.parse(f"parse {long_text}")
        assert result.command_type == "parse"
        assert long_text.strip() in result.text

    def test_mixed_commands_treated_as_text(self):
        """Test that mixed or unrecognized commands are treated as plain text."""
        result = CommandParser.parse("unknown_cmd something")
        assert result.command_type == "text"
        assert result.text == "unknown_cmd something"

    def test_suggestions(self):
        """Test getting command suggestions."""
        suggestions = CommandParser.get_suggestions()
        assert isinstance(suggestions, list)
        assert "parse " in suggestions
        assert "voice" in suggestions
        assert "priority " in suggestions
        assert len(suggestions) == 3

    def test_format_help(self):
        """Test format help text."""
        help_text = format_command_help()
        assert "parse" in help_text
        assert "voice" in help_text
        assert "priority" in help_text
        assert "Quick Input Commands" in help_text

    def test_parsed_command_dataclass(self):
        """Test ParsedCommand dataclass."""
        cmd = ParsedCommand(
            command_type="text",
            text="Test task",
            priority=None,
            success=True
        )
        assert cmd.command_type == "text"
        assert cmd.text == "Test task"
        assert cmd.priority is None
        assert cmd.success is True

    def test_parsed_command_with_priority(self):
        """Test ParsedCommand with priority set."""
        cmd = ParsedCommand(
            command_type="priority",
            text="Important task",
            priority="high",
        )
        assert cmd.priority == "high"

    def test_text_with_command_keywords(self):
        """Test plain text that contains command keywords."""
        result = CommandParser.parse("Please parse the voice priority of this task")
        assert result.command_type == "text"
        assert result.text == "Please parse the voice priority of this task"

    def test_unicode_handling(self):
        """Test proper handling of unicode characters."""
        result = CommandParser.parse("parse Café 日本語 Ελληνικά")
        assert result.command_type == "parse"
        assert "Café" in result.text
        assert "日本語" in result.text
        assert "Ελληνικά" in result.text

    def test_leading_trailing_spaces(self):
        """Test handling of leading and trailing spaces."""
        result = CommandParser.parse("  parse   Something   ")
        assert result.command_type == "parse"
        # Should have stripped leading/trailing from overall command
        assert result.text.strip() == "Something"
