"""Unit tests for PID file manager."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.utils.pid_manager import PIDFileError, PIDManager, get_pid_manager, reset_pid_manager


class TestPIDManager:
    """Tests for PIDManager class."""

    @pytest.fixture
    def temp_pid_file(self, tmp_path):
        """Create a temporary PID file path."""
        return tmp_path / "test_agent.pid"

    @pytest.fixture
    def pid_manager(self, temp_pid_file):
        """Create a PIDManager instance with temporary file."""
        return PIDManager(temp_pid_file)

    def test_init_default_path(self):
        """Test PIDManager initialization with default path."""
        manager = PIDManager()
        expected_path = Path.home() / ".personal-assistant" / "agent.pid"
        assert manager.pid_file_path == expected_path

    def test_init_custom_path(self, temp_pid_file):
        """Test PIDManager initialization with custom path."""
        manager = PIDManager(temp_pid_file)
        assert manager.pid_file_path == temp_pid_file

    def test_write_pid_file_current_process(self, pid_manager, temp_pid_file):
        """Test writing current process PID to file."""
        pid_manager.write_pid_file()
        
        assert temp_pid_file.exists()
        content = temp_pid_file.read_text().strip()
        assert content == str(os.getpid())

    def test_write_pid_file_custom_pid(self, pid_manager, temp_pid_file):
        """Test writing custom PID to file."""
        custom_pid = 12345
        pid_manager.write_pid_file(custom_pid)
        
        assert temp_pid_file.exists()
        content = temp_pid_file.read_text().strip()
        assert content == str(custom_pid)

    def test_write_pid_file_creates_directory(self, tmp_path):
        """Test that write_pid_file creates parent directories."""
        nested_path = tmp_path / "nested" / "dir" / "agent.pid"
        manager = PIDManager(nested_path)
        
        manager.write_pid_file()
        
        assert nested_path.exists()
        assert nested_path.parent.exists()

    def test_write_pid_file_error(self, pid_manager):
        """Test error handling when writing PID file fails."""
        # Make the path unwritable by mocking write_text to raise an error
        with patch.object(Path, "write_text", side_effect=OSError("Permission denied")):
            with pytest.raises(PIDFileError, match="Failed to write PID file"):
                pid_manager.write_pid_file()

    def test_read_pid_file_valid(self, pid_manager, temp_pid_file):
        """Test reading valid PID file."""
        test_pid = 54321
        temp_pid_file.write_text(str(test_pid))
        
        pid = pid_manager.read_pid_file()
        assert pid == test_pid

    def test_read_pid_file_nonexistent(self, pid_manager):
        """Test reading nonexistent PID file."""
        pid = pid_manager.read_pid_file()
        assert pid is None

    def test_read_pid_file_invalid_content(self, pid_manager, temp_pid_file):
        """Test reading PID file with invalid content."""
        temp_pid_file.write_text("not_a_number")
        
        pid = pid_manager.read_pid_file()
        assert pid is None

    def test_read_pid_file_empty(self, pid_manager, temp_pid_file):
        """Test reading empty PID file."""
        temp_pid_file.write_text("")
        
        pid = pid_manager.read_pid_file()
        assert pid is None

    def test_read_pid_file_whitespace(self, pid_manager, temp_pid_file):
        """Test reading PID file with whitespace."""
        test_pid = 99999
        temp_pid_file.write_text(f"  {test_pid}  \n")
        
        pid = pid_manager.read_pid_file()
        assert pid == test_pid

    def test_remove_pid_file_exists(self, pid_manager, temp_pid_file):
        """Test removing existing PID file."""
        temp_pid_file.write_text("12345")
        
        result = pid_manager.remove_pid_file()
        
        assert result is True
        assert not temp_pid_file.exists()

    def test_remove_pid_file_nonexistent(self, pid_manager):
        """Test removing nonexistent PID file."""
        result = pid_manager.remove_pid_file()
        assert result is False

    def test_is_process_running_current_process(self, pid_manager):
        """Test checking if current process is running."""
        current_pid = os.getpid()
        assert pid_manager.is_process_running(current_pid) is True

    def test_is_process_running_nonexistent(self, pid_manager):
        """Test checking if nonexistent process is running."""
        # Use a very high PID that's unlikely to exist
        fake_pid = 999999
        assert pid_manager.is_process_running(fake_pid) is False

    def test_is_process_running_invalid_pid(self, pid_manager):
        """Test checking invalid PIDs."""
        assert pid_manager.is_process_running(0) is False
        assert pid_manager.is_process_running(-1) is False

    def test_is_process_running_permission_error(self, pid_manager):
        """Test handling PermissionError (process exists but no access)."""
        with patch("os.kill", side_effect=PermissionError):
            # Should return True because process exists (even if we can't access it)
            assert pid_manager.is_process_running(12345) is True

    def test_get_agent_pid_running(self, pid_manager, temp_pid_file):
        """Test getting PID of running agent."""
        current_pid = os.getpid()
        temp_pid_file.write_text(str(current_pid))
        
        pid = pid_manager.get_agent_pid()
        assert pid == current_pid

    def test_get_agent_pid_not_running(self, pid_manager, temp_pid_file):
        """Test getting PID when agent is not running."""
        fake_pid = 999999
        temp_pid_file.write_text(str(fake_pid))
        
        pid = pid_manager.get_agent_pid()
        
        # Should return None and clean up stale file
        assert pid is None
        assert not temp_pid_file.exists()

    def test_get_agent_pid_no_file(self, pid_manager):
        """Test getting PID when no PID file exists."""
        pid = pid_manager.get_agent_pid()
        assert pid is None

    def test_is_agent_running_true(self, pid_manager, temp_pid_file):
        """Test checking if agent is running (true case)."""
        current_pid = os.getpid()
        temp_pid_file.write_text(str(current_pid))
        
        assert pid_manager.is_agent_running() is True

    def test_is_agent_running_false(self, pid_manager):
        """Test checking if agent is running (false case)."""
        assert pid_manager.is_agent_running() is False

    def test_cleanup_stale_pid_file(self, pid_manager, temp_pid_file):
        """Test cleaning up stale PID file."""
        fake_pid = 999999
        temp_pid_file.write_text(str(fake_pid))
        
        result = pid_manager.cleanup_stale_pid_file()
        
        assert result is True
        assert not temp_pid_file.exists()

    def test_cleanup_stale_pid_file_process_running(self, pid_manager, temp_pid_file):
        """Test cleanup when process is still running."""
        current_pid = os.getpid()
        temp_pid_file.write_text(str(current_pid))
        
        result = pid_manager.cleanup_stale_pid_file()
        
        assert result is False
        assert temp_pid_file.exists()

    def test_cleanup_stale_pid_file_no_file(self, pid_manager):
        """Test cleanup when no PID file exists."""
        result = pid_manager.cleanup_stale_pid_file()
        assert result is False

    def test_stop_agent_running(self, pid_manager, temp_pid_file):
        """Test stopping running agent."""
        # Use current process as test (won't actually stop it)
        current_pid = os.getpid()
        temp_pid_file.write_text(str(current_pid))
        
        with patch("os.kill") as mock_kill:
            result = pid_manager.stop_agent()
            
            assert result is True
            # Should be called twice: once with signal 0 (check), once with SIGTERM
            assert mock_kill.call_count == 2
            # Verify the SIGTERM call
            import signal
            mock_kill.assert_any_call(current_pid, signal.SIGTERM)

    def test_stop_agent_not_running(self, pid_manager):
        """Test stopping when agent is not running."""
        result = pid_manager.stop_agent()
        assert result is False

    def test_stop_agent_process_not_found(self, pid_manager, temp_pid_file):
        """Test stopping when process no longer exists."""
        fake_pid = 999999
        temp_pid_file.write_text(str(fake_pid))
        
        with patch("os.kill", side_effect=ProcessLookupError):
            result = pid_manager.stop_agent()
            
            assert result is False
            assert not temp_pid_file.exists()

    def test_stop_agent_permission_error(self, pid_manager, temp_pid_file):
        """Test stopping when permission is denied."""
        test_pid = 12345
        temp_pid_file.write_text(str(test_pid))
        
        with patch("os.kill", side_effect=PermissionError("Access denied")):
            # Should still think process is running (permission error in get_agent_pid)
            # But stop_agent will raise PIDFileError
            with patch.object(pid_manager, "is_process_running", return_value=True):
                with pytest.raises(PIDFileError, match="Permission denied"):
                    pid_manager.stop_agent()


class TestGlobalPIDManager:
    """Tests for global PID manager functions."""

    def test_get_pid_manager_singleton(self):
        """Test that get_pid_manager returns singleton instance."""
        reset_pid_manager()
        
        manager1 = get_pid_manager()
        manager2 = get_pid_manager()
        
        assert manager1 is manager2

    def test_get_pid_manager_custom_path(self, tmp_path):
        """Test get_pid_manager with custom path."""
        reset_pid_manager()
        
        custom_path = tmp_path / "custom.pid"
        manager = get_pid_manager(custom_path)
        
        assert manager.pid_file_path == custom_path

    def test_reset_pid_manager(self):
        """Test resetting global PID manager."""
        manager1 = get_pid_manager()
        reset_pid_manager()
        manager2 = get_pid_manager()
        
        assert manager1 is not manager2
