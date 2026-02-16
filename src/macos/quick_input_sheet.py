"""Modal sheet-based quick input dialog with proper keyboard focus.

Uses NSAlert-style sheets which properly handle keyboard input in menu bar apps.
Sheets are modal dialogs that appear attached to a window and automatically
become key, receiving keyboard events reliably.
"""

import logging
import threading
from typing import Callable, Optional

import httpx
import objc
from AppKit import (
    NSApp,
    NSAlert,
    NSTextField,
    NSSecureTextField,
)
from Foundation import NSMakeRect

from src.macos.command_parser import CommandParser, ParsedCommand

logger = logging.getLogger(__name__)


class QuickInputSheet:
    """Modal sheet-based input dialog for task creation.
    
    This implementation uses NSAlert with a text field, which:
    - Automatically becomes key when displayed
    - Properly handles keyboard input
    - Works reliably in menu bar app context
    - Provides native macOS appearance and behavior
    """
    
    def __init__(self, api_url: str = "http://localhost:8000", on_submit: Optional[Callable] = None):
        """Initialize the quick input sheet.
        
        Args:
            api_url: Base URL of the API
            on_submit: Callback when user submits (optional for testing)
        """
        self.api_url = api_url
        self.client = httpx.Client(timeout=10.0)
        self.on_submit = on_submit
    
    def show(self, parent_window=None) -> None:
        """Show the quick input dialog as a modal sheet.
        
        Args:
            parent_window: Parent window to attach sheet to (optional)
        """
        logger.info("Showing quick input sheet")
        
        # Dispatch to main thread without blocking using performSelector
        # This allows the menu bar app to stay responsive
        NSApp.performSelectorOnMainThread_withObject_waitUntilDone_(
            "_showQuickInputDialog:",
            self,
            False  # Don't wait - let it run asynchronously
        )
    
    def _showQuickInputDialog_(self) -> None:
        """Show the dialog on the main thread (called via performSelector)."""
        try:
            logger.info("Creating alert on main thread")
            
            # Create alert (which becomes the modal sheet)
            alert = NSAlert.alloc().init()
            alert.setMessageText_("Quick Task Input")
            alert.setInformativeText_("Enter a task or command:")
            
            # Add input field
            input_field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 300, 24))
            input_field.setPlaceholderString_("Type task or 'parse <text>', 'voice', 'priority <level>'")
            alert.setAccessoryView_(input_field)
            
            # Add buttons
            alert.addButtonWithTitle_("Submit")
            alert.addButtonWithTitle_("Cancel")
            
            logger.info("Alert created, showing modal dialog...")
            
            # Show as modal dialog on main thread
            response = alert.runModal()
            logger.info(f"Modal dialog response: {response}")
            
            if response == 1000:  # Submit button (first button)
                text = input_field.stringValue()
                logger.info(f"User submitted: {text}")
                self._process_input(text)
            else:
                logger.info("User cancelled dialog")
                
        except Exception as e:
            logger.error(f"Error showing quick input sheet: {e}", exc_info=True)
    
    def _sheet_did_end_(self, sheet, return_code, context):
        """Callback when sheet closes.
        
        Args:
            sheet: The alert sheet
            return_code: Button pressed (1000=Submit, 1001=Cancel)
            context: Context data
        """
        logger.info(f"Sheet closed with return code: {return_code}")
        
        if return_code == 1000:  # Submit button
            # Get the input field from the alert
            input_field = sheet.accessoryView()
            text = input_field.stringValue()
            logger.info(f"User input: {text}")
            self._process_input(text)
        else:
            logger.info("User cancelled")
    
    def _process_input(self, text: str) -> None:
        """Process user input and submit to API.
        
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
