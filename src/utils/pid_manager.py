"""PID file management for tracking agent process across CLI invocations.

This module provides utilities for writing, reading, and validating PID files
to track whether the agent is running in a separate process.
"""

import logging
import os
import signal
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class PIDFileError(Exception):
    """Base exception for PID file operations."""
    pass


class PIDManager:
    """Manages PID file for agent process tracking."""

    def __init__(self, pid_file_path: Optional[Path] = None):
        """Initialize PID manager.

        Args:
            pid_file_path: Custom PID file path. Defaults to ~/.personal-assistant/agent.pid
        """
        if pid_file_path is None:
            # Default location: ~/.personal-assistant/agent.pid
            data_dir = Path.home() / ".personal-assistant"
            pid_file_path = data_dir / "agent.pid"
        
        self.pid_file_path = Path(pid_file_path)

    def write_pid_file(self, pid: Optional[int] = None) -> None:
        """Write current process PID to file.

        Args:
            pid: Process ID to write. If None, uses current process PID.

        Raises:
            PIDFileError: If unable to write PID file.
        """
        if pid is None:
            pid = os.getpid()

        try:
            # Create directory if it doesn't exist
            self.pid_file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write PID to file
            self.pid_file_path.write_text(str(pid))
            logger.info(f"Wrote PID {pid} to {self.pid_file_path}")

        except (OSError, IOError) as e:
            raise PIDFileError(f"Failed to write PID file: {e}")

    def read_pid_file(self) -> Optional[int]:
        """Read PID from file.

        Returns:
            PID as integer, or None if file doesn't exist or is invalid.
        """
        if not self.pid_file_path.exists():
            return None

        try:
            content = self.pid_file_path.read_text().strip()
            return int(content)
        except (ValueError, OSError, IOError) as e:
            logger.warning(f"Invalid PID file content: {e}")
            return None

    def remove_pid_file(self) -> bool:
        """Remove PID file.

        Returns:
            True if file was removed, False if it didn't exist.
        """
        if not self.pid_file_path.exists():
            return False

        try:
            self.pid_file_path.unlink()
            logger.info(f"Removed PID file: {self.pid_file_path}")
            return True
        except (OSError, IOError) as e:
            logger.warning(f"Failed to remove PID file: {e}")
            return False

    def is_process_running(self, pid: int) -> bool:
        """Check if a process with given PID is running.

        Args:
            pid: Process ID to check.

        Returns:
            True if process is running, False otherwise.
        """
        if pid <= 0:
            return False

        try:
            # Send signal 0 to check if process exists
            # This doesn't actually send a signal, just checks permissions
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            # Process doesn't exist
            return False
        except PermissionError:
            # Process exists but we don't have permission (still running)
            return True
        except Exception as e:
            logger.warning(f"Error checking process {pid}: {e}")
            return False

    def get_agent_pid(self) -> Optional[int]:
        """Get PID of running agent process.

        This reads the PID file and validates that the process is actually running.
        If the PID file exists but the process is not running (stale file),
        it will be cleaned up automatically.

        Returns:
            PID of running agent, or None if agent is not running.
        """
        pid = self.read_pid_file()
        
        if pid is None:
            return None

        # Check if process is actually running
        if self.is_process_running(pid):
            return pid
        else:
            # Stale PID file - clean it up
            logger.info(f"Cleaning up stale PID file for non-existent process {pid}")
            self.remove_pid_file()
            return None

    def is_agent_running(self) -> bool:
        """Check if agent is currently running.

        Returns:
            True if agent is running, False otherwise.
        """
        return self.get_agent_pid() is not None

    def cleanup_stale_pid_file(self) -> bool:
        """Clean up stale PID file if process is not running.

        Returns:
            True if stale file was removed, False if file didn't exist or process is still running.
        """
        pid = self.read_pid_file()
        
        if pid is None:
            return False

        if not self.is_process_running(pid):
            logger.info(f"Cleaning up stale PID file for PID {pid}")
            return self.remove_pid_file()
        
        return False

    def stop_agent(self) -> bool:
        """Stop the running agent process.

        Sends SIGTERM to the agent process for graceful shutdown.

        Returns:
            True if signal was sent successfully, False if agent is not running.

        Raises:
            PIDFileError: If unable to send signal to process.
        """
        pid = self.get_agent_pid()
        
        if pid is None:
            return False

        try:
            os.kill(pid, signal.SIGTERM)
            logger.info(f"Sent SIGTERM to agent process {pid}")
            return True
        except ProcessLookupError:
            # Process already gone
            self.remove_pid_file()
            return False
        except PermissionError as e:
            raise PIDFileError(f"Permission denied to stop process {pid}: {e}")
        except Exception as e:
            raise PIDFileError(f"Failed to stop process {pid}: {e}")


# Global PID manager instance
_pid_manager: Optional[PIDManager] = None


def get_pid_manager(pid_file_path: Optional[Path] = None) -> PIDManager:
    """Get the global PID manager instance.

    Args:
        pid_file_path: Optional custom PID file path.

    Returns:
        Global PIDManager instance.
    """
    global _pid_manager
    if _pid_manager is None:
        _pid_manager = PIDManager(pid_file_path)
    return _pid_manager


def reset_pid_manager() -> None:
    """Reset the global PID manager instance (useful for testing)."""
    global _pid_manager
    _pid_manager = None
