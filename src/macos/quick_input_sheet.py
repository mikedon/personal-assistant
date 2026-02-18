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
            
            if result.stderr:
                logger.warning(f"Dialog subprocess stderr: {result.stderr}")
            
            if result.stdout:
                logger.info(f"Dialog stdout: {result.stdout.strip()}")
                try:
                    data = json.loads(result.stdout.strip())
                    logger.info(f"Dialog result: {data}")
                    
                    if data.get("submitted") and data.get("text"):
                        logger.info(f"Processing submitted text: {data['text']}")
                        self._process_input(data["text"])
                    else:
                        logger.info(f"Dialog closed without submission: {data}")
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse dialog output: {result.stdout} - {e}")
            elif result.returncode == 0:
                logger.info("Dialog closed without output")
            else:
                logger.info(f"Dialog closed with error (returncode={result.returncode})")
        
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
        
        # Use API parse endpoint for NLP task extraction
        self._submit_to_api(text)
    
    def _submit_to_api(self, text: str) -> None:
        """Submit text to API parse endpoint for task creation.
        
        Args:
            text: User-entered text to parse and create tasks from
        """
        try:
            logger.info(f"Sending to parse API: {text}")
            
            # Call the parse endpoint which uses LLM to extract tasks
            response = self.client.post(
                f"{self.api_url}/api/tasks/parse",
                json={"text": text}
            )
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Parse response: {result}")
            
            # Log created tasks
            created_count = len(result.get("created_tasks", []))
            if created_count > 0:
                logger.info(f"Successfully created {created_count} task(s) from input")
                for task in result.get("created_tasks", []):
                    logger.info(f"  - {task['title']} (priority: {task['priority']})")
            else:
                logger.info("No tasks were created from the input")
        
        except Exception as e:
            logger.error(f"Failed to parse and create tasks: {e}", exc_info=True)
    
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
        # Keep reference to sheet so thread can complete
        self.sheet = QuickInputSheet(api_url=self.api_url)
        self.sheet.show(parent_window=self.parent_window)
