"""macOS integration module.

Provides menu bar application and launcher for displaying task summaries
in the macOS status bar.
"""

from src.macos.launcher import launch
from src.macos.menu_app import TaskMenuApp, run_menu_app

__all__ = ["TaskMenuApp", "run_menu_app", "launch"]
