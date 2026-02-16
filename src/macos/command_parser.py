"""Parser for quick input commands.

Supports:
- parse {text}: Create task from natural language description
- voice: Start voice recording for task creation
- priority {text}: Create high-priority task
- {text}: Create simple task with title only
"""

import re
from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class ParsedCommand:
    """Result of parsing a quick input command."""

    command_type: Literal["parse", "voice", "priority", "text"]
    text: str  # The input text or command content
    priority: Optional[str] = None  # Priority level if specified
    success: bool = True  # Whether parsing succeeded


class CommandParser:
    """Parser for quick input commands."""

    # Command patterns
    PARSE_PATTERN = r"^parse\s+(.+)$"
    VOICE_PATTERN = r"^voice\s*$"
    PRIORITY_PATTERN = r"^priority\s+(.+)$"

    @staticmethod
    def parse(input_text: str) -> ParsedCommand:
        """Parse a quick input command.

        Args:
            input_text: The raw input text from the user

        Returns:
            ParsedCommand with command type and content

        Examples:
            >>> parser = CommandParser()
            >>> parser.parse("parse Create a task about project X")
            ParsedCommand(command_type='parse', text='Create a task about project X')

            >>> parser.parse("priority Fix critical bug")
            ParsedCommand(command_type='priority', text='Fix critical bug', priority='high')

            >>> parser.parse("voice")
            ParsedCommand(command_type='voice', text='', success=True)

            >>> parser.parse("Regular task title")
            ParsedCommand(command_type='text', text='Regular task title')
        """
        text = input_text.strip()

        if not text:
            return ParsedCommand(
                command_type="text",
                text="",
                success=False,
            )

        # Check for parse command
        match = re.match(CommandParser.PARSE_PATTERN, text, re.IGNORECASE)
        if match:
            return ParsedCommand(
                command_type="parse",
                text=match.group(1),
            )

        # Check for voice command
        match = re.match(CommandParser.VOICE_PATTERN, text, re.IGNORECASE)
        if match:
            return ParsedCommand(
                command_type="voice",
                text="",
            )

        # Check for priority command
        match = re.match(CommandParser.PRIORITY_PATTERN, text, re.IGNORECASE)
        if match:
            return ParsedCommand(
                command_type="priority",
                text=match.group(1),
                priority="high",
            )

        # Default: plain text
        return ParsedCommand(
            command_type="text",
            text=text,
        )

    @staticmethod
    def get_suggestions() -> list[str]:
        """Get command suggestions for dropdown.

        Returns:
            List of available commands
        """
        return [
            "parse ",  # Include space for convenience
            "voice",
            "priority ",
        ]


def format_command_help() -> str:
    """Get help text for quick input commands.

    Returns:
        Formatted help string
    """
    return """Quick Input Commands:
    parse <text> - Create task from natural language
    voice - Start voice recording
    priority <text> - Create high-priority task
    <text> - Create simple task"""
