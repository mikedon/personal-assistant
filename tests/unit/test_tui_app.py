"""Tests for TUI application."""

import pytest
from unittest.mock import patch, MagicMock

from src.tui.app import TaskDashboardApp


def test_app_creation():
    """Test that the app can be created."""
    app = TaskDashboardApp()
    assert app is not None
    assert app.title == "Personal Assistant Tasks"


def test_app_has_bindings():
    """Test that the app has expected keyboard bindings."""
    app = TaskDashboardApp()
    bindings_list = [binding[1] for binding in app.BINDINGS]
    assert "complete_task" in bindings_list
    assert "delete_task" in bindings_list
    assert "show_help" in bindings_list
    assert "quit" in bindings_list


def test_app_initialization():
    """Test app initializes with None widgets."""
    app = TaskDashboardApp()
    assert app.task_table is None
    assert app.initiative_panel is None
    assert app.agent_status is None
