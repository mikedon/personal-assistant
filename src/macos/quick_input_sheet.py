"""Quick input dialog for task creation in menu bar app.

Uses subprocess with tkinter dialog to avoid blocking issues with NSAlert
in menu bar app context.
"""

import json
import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

import httpx

from src.macos.command_parser import CommandParser, ParsedCommand

logger = logging.getLogger(__name__)


class QuickInputSheet:
    """Dialog for task creation using subprocess + tkinter.
    
    This implementation uses a subprocess to show a tkinter dialog, which:
    - Works reliably without blocking the menu bar app
    - Properly handles keyboard input
    - Doesn't require complex AppKit event loop management
    """
    
    def __init__(self, api_url: str = "http://localhost:8000", on_submit: Optional[Callable] = None):
        """Initialize the quick input dialog.
        
        Args:
            api_url: Base URL of the API
            on_submit: Callback when user submits (optional for testing)
        """
        self.api_url = api_url
        self.on_submit = on_submit
        self.client = httpx.Client(timeout=10.0)
    
    def show(self, parent_window=None) -> None:
        """Show the quick input dialog.
        
        Args:
            parent_window: Parent window (unused, for API compatibility)
        """
        logger.info("Showing quick input dialog")
        
        # Run dialog in background thread to avoid blocking menu bar
        thread = threading.Thread(target=self._show_dialog_in_subprocess, daemon=True)
        thread.start()
    
    def _show_dialog_in_subprocess(self) -> None:
        """Show dialog in subprocess."""
        try:
            # Get path to the dialog script
            dialog_script = Path(__file__).parent / "quick_input_dialog.py"
            
            logger.info(f"Launching dialog subprocess: {dialog_script}")
            
            # Run the dialog as a subprocess
            result = subprocess.run(
                [sys.executable, str(dialog_script)],
                capture_output=True,
                text=True,
                timeout=60.0  # 1 minute timeout
            )
            
            logger.info(f"Dialog subprocess returned: {result.returncode}")
            
            if result.returncode == 0 and result.stdout:
                try:
                    data = json.loads(result.stdout.strip())
                    logger.info(f"Dialog result: {data}")
                    
                    if data.get("submitted") and data.get("text"):
                        self._process_input(data["text"])
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse dialog output: {result.stdout}")
            else:
                logger.info("Dialog cancelled or closed")
        
        except subprocess.TimeoutExpired:
            logger.warning("Dialog subprocess timed out")
        except Exception as e:
            logger.error(f"Error showing dialog: {e}", exc_info=True)
    
    def _process_input(self, text: str) -> None:
        """Process user input.
        
        Args:
            text: User-entered text
        """
        if not text or not text.strip():
            logger.info("Empty input, ignoring")
            return
        
        logger.info(f"Processing input: {text}")
        
        # Parse command
        parsed = CommandParser.parse(text)
        logger.info(f"Parsed command: {parsed}")
        
        # Call submission callback if provided
        if self.on_submit:
            self.on_submit(parsed)
        else:
            # Default: submit to API
            self._submit_to_api(parsed)
    
    def _submit_to_api(self, parsed: ParsedCommand) -> None:
        """Submit parsed command to API.
        
        Args:
            parsed: Parsed command from input
        """
        try:
            if parsed.command_type == "voice":
                logger.info("Voice command received (not yet implemented)")
                return
            
            # Prepare task data
            task_data = {
                "title": parsed.text,
                "priority": parsed.priority or "medium",
            }
            
            if parsed.command_type == "parse":
                task_data["description"] = parsed.text
                task_data["parse_natural_language"] = True
            
            # Submit to API
            response = self.client.post(f"{self.api_url}/api/tasks", json=task_data)
            response.raise_for_status()
            logger.info(f"Task created: {response.json()}")
        
        except Exception as e:
            logger.error(f"Failed to create task: {e}")
    
    def close(self) -> None:
        """Clean up resources."""
        self.client.close()


class QuickInputSheetManager:
    """Manager for quick input sheet functionality in menu bar app."""
    
    def __init__(self, api_url: str = "http://localhost:8000"):
        """Initialize the manager.
        
        Args:
            api_url: Base URL of the API
        """
        self.api_url = api_url
        self.sheet: Optional[QuickInputSheet] = None
        self.parent_window: Optional[object] = None
    
    def setup(self, parent_window=None) -> None:
        """Set up the sheet manager.
        
        Args:
            parent_window: Optional parent window to attach sheets to
        """
        self.parent_window = parent_window
        logger.info("Quick input sheet manager initialized")
    
    def show_quick_input(self) -> None:
        """Show the quick input sheet."""
        logger.info("Showing quick input sheet")
        sheet = QuickInputSheet(api_url=self.api_url)
        sheet.show(parent_window=self.parent_window)
