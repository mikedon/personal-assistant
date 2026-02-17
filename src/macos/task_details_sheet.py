"""Task details modal manager for menu bar app.

Uses subprocess with tkinter dialog to display task details and handle quick actions.
"""

import json
import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class TaskDetailsModalManager:
    """Manager for task details modal functionality in menu bar app."""
    
    def __init__(self, api_url: str = "http://localhost:8000"):
        """Initialize the manager.
        
        Args:
            api_url: Base URL of the API
        """
        self.api_url = api_url
        self.client = httpx.Client(timeout=10.0)
    
    def show_task_details(self, task_id: int) -> None:
        """Show the task details modal.
        
        Args:
            task_id: ID of the task to display
        """
        logger.info(f"Showing task details for task {task_id}")
        
        # Run modal in background thread to avoid blocking menu bar
        thread = threading.Thread(
            target=self._show_modal_in_subprocess,
            args=(task_id,),
            daemon=True
        )
        thread.start()
    
    def _show_modal_in_subprocess(self, task_id: int) -> None:
        """Show modal in subprocess.
        
        Args:
            task_id: ID of the task to display
        """
        try:
            # Fetch task data from API
            task_data = self._fetch_task(task_id)
            if not task_data:
                logger.error(f"Failed to fetch task {task_id}")
                return
            
            logger.info(f"Fetched task: {task_data.get('title')}")
            
            # Get path to the modal script
            modal_script = Path(__file__).parent / "task_details_modal.py"
            
            logger.info(f"Launching modal subprocess: {modal_script}")
            
            # Run the modal as a subprocess, passing task data as JSON
            result = subprocess.run(
                [sys.executable, str(modal_script)],
                input=json.dumps(task_data),
                capture_output=True,
                text=True,
                timeout=300.0  # 5 minute timeout
            )
            
            logger.info(f"Modal subprocess returned: {result.returncode}")
            
            if result.stderr:
                logger.warning(f"Modal subprocess stderr: {result.stderr}")
            
            if result.stdout:
                logger.info(f"Modal stdout: {result.stdout.strip()}")
                try:
                    modal_result = json.loads(result.stdout.strip())
                    logger.info(f"Modal result: {modal_result}")
                    
                    if modal_result.get("success") and modal_result.get("action"):
                        self._handle_modal_action(task_id, modal_result)
                    else:
                        logger.info(f"Modal closed without action: {modal_result}")
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse modal output: {result.stdout} - {e}")
            elif result.returncode == 0:
                logger.info("Modal closed without output")
            else:
                logger.info(f"Modal closed with error (returncode={result.returncode})")
        
        except subprocess.TimeoutExpired:
            logger.warning("Modal subprocess timed out")
        except Exception as e:
            logger.error(f"Error showing modal: {e}", exc_info=True)
    
    def _fetch_task(self, task_id: int) -> Optional[dict]:
        """Fetch task details from API.
        
        Args:
            task_id: ID of the task to fetch
            
        Returns:
            Task data dictionary or None if failed
        """
        try:
            response = self.client.get(f"{self.api_url}/api/tasks/{task_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch task {task_id}: {e}")
            return None
    
    def _handle_modal_action(self, task_id: int, modal_result: dict) -> None:
        """Handle action from modal.
        
        Args:
            task_id: ID of the task
            modal_result: Dictionary with action details
        """
        action = modal_result.get("action")
        
        if action == "complete":
            self._complete_task(task_id)
        elif action == "change_priority":
            priority = modal_result.get("priority")
            if priority:
                self._update_task_priority(task_id, priority)
        elif action == "change_due_date":
            due_date = modal_result.get("due_date")
            self._update_task_due_date(task_id, due_date)
        elif action == "open_dashboard":
            import webbrowser
            webbrowser.open(f"{self.api_url}/docs")
        else:
            logger.warning(f"Unknown action: {action}")
    
    def _complete_task(self, task_id: int) -> None:
        """Mark task as completed.
        
        Args:
            task_id: ID of the task
        """
        try:
            logger.info(f"Completing task {task_id}")
            response = self.client.put(
                f"{self.api_url}/api/tasks/{task_id}",
                json={"status": "completed"}
            )
            response.raise_for_status()
            logger.info(f"Task {task_id} completed successfully")
        except Exception as e:
            logger.error(f"Failed to complete task {task_id}: {e}")
    
    def _update_task_priority(self, task_id: int, priority: str) -> None:
        """Update task priority.
        
        Args:
            task_id: ID of the task
            priority: New priority level
        """
        try:
            logger.info(f"Updating task {task_id} priority to {priority}")
            response = self.client.put(
                f"{self.api_url}/api/tasks/{task_id}",
                json={"priority": priority}
            )
            response.raise_for_status()
            logger.info(f"Task {task_id} priority updated to {priority}")
        except Exception as e:
            logger.error(f"Failed to update task {task_id} priority: {e}")
    
    def _update_task_due_date(self, task_id: int, due_date: Optional[str]) -> None:
        """Update task due date.
        
        Args:
            task_id: ID of the task
            due_date: New due date (ISO format) or None to clear
        """
        try:
            logger.info(f"Updating task {task_id} due date to {due_date}")
            
            update_data = {}
            if due_date is None:
                update_data["due_date"] = None
            else:
                # Convert date string to ISO datetime format if needed
                if "T" not in due_date:
                    # Convert YYYY-MM-DD to YYYY-MM-DDTHH:MM:SS
                    due_date = f"{due_date}T00:00:00"
                update_data["due_date"] = due_date
            
            response = self.client.put(
                f"{self.api_url}/api/tasks/{task_id}",
                json=update_data
            )
            response.raise_for_status()
            logger.info(f"Task {task_id} due date updated to {due_date}")
        except Exception as e:
            logger.error(f"Failed to update task {task_id} due date: {e}")
    
    def close(self) -> None:
        """Clean up resources."""
        self.client.close()
