"""Unit tests for quick input window controller."""

import pytest
from unittest.mock import Mock, MagicMock, patch

try:
    from src.macos.quick_input import (
        QuickInputWindowController,
        QuickInputHotkeyListener,
        QuickInputManager,
        PYNPUT_AVAILABLE
    )
    PYOBJC_AVAILABLE = True
except ImportError:
    PYOBJC_AVAILABLE = False


@pytest.mark.skipif(not PYOBJC_AVAILABLE, reason="PyObjC not available")
class TestQuickInputWindowController:
    """Tests for QuickInputWindowController."""

    def test_init_creates_instance(self):
        """Test initialization creates controller instance."""
        controller = QuickInputWindowController.alloc().init()
        assert controller is not None
        assert controller.api_url == "http://localhost:8000"
        assert controller.window is None

    def test_init_with_custom_api_url(self):
        """Test initialization with custom API URL."""
        controller = QuickInputWindowController.alloc().init(api_url="http://api:9000")
        assert controller.api_url == "http://api:9000"

    def test_init_with_on_close_callback(self):
        """Test initialization with on_close callback."""
        callback = Mock()
        controller = QuickInputWindowController.alloc().init(on_close=callback)
        assert controller.on_close == callback

    @patch('src.macos.quick_input.NSScreen')
    @patch('src.macos.quick_input.NSWindow')
    def test_create_window(self, mock_window_class, mock_screen_class):
        """Test window creation."""
        mock_screen = MagicMock()
        mock_frame = MagicMock()
        mock_frame.size.width = 1920
        mock_frame.size.height = 1080
        mock_frame.origin.x = 0
        mock_frame.origin.y = 0
        mock_screen.frame.return_value = mock_frame
        mock_screen_class.mainScreen.return_value = mock_screen
        
        mock_window = MagicMock()
        mock_window_class.return_value = mock_window
        
        controller = QuickInputWindowController.alloc().init()
        controller.create_window()
        
        assert controller.window is not None

    def test_window_should_close_delegate(self):
        """Test windowShouldClose_ returns True."""
        controller = QuickInputWindowController.alloc().init()
        result = controller.windowShouldClose_(None)
        assert result is True

    def test_window_should_close_calls_callback(self):
        """Test windowShouldClose_ calls on_close callback."""
        callback = Mock()
        controller = QuickInputWindowController.alloc().init(on_close=callback)
        controller.windowShouldClose_(None)
        callback.assert_called_once()

    def test_close_without_window(self):
        """Test close method when window is None."""
        controller = QuickInputWindowController.alloc().init()
        controller.close()  # Should not raise

    @patch('src.macos.quick_input.httpx.Client')
    def test_close_closes_window_and_client(self, mock_client_class):
        """Test close method closes window and client."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        controller = QuickInputWindowController.alloc().init()
        controller.window = MagicMock()
        
        controller.close()
        
        controller.window.close.assert_called_once()
        mock_client.close.assert_called_once()


class TestQuickInputHotkeyListener:
    """Tests for QuickInputHotkeyListener."""

    def test_init_creates_instance(self):
        """Test initialization creates listener instance."""
        callback = Mock()
        listener = QuickInputHotkeyListener(on_hotkey=callback)
        assert listener is not None
        assert listener.on_hotkey == callback
        assert listener.is_running is False

    def test_is_hotkey_pressed_returns_bool(self):
        """Test _is_hotkey_pressed returns boolean."""
        callback = Mock()
        listener = QuickInputHotkeyListener(on_hotkey=callback)
        result = listener._is_hotkey_pressed(None)
        assert isinstance(result, bool)

    @patch('src.macos.quick_input.PYNPUT_AVAILABLE', False)
    def test_start_graceful_fallback_when_pynput_unavailable(self):
        """Test start gracefully handles missing pynput."""
        callback = Mock()
        listener = QuickInputHotkeyListener(on_hotkey=callback)
        listener.start()  # Should not raise
        assert listener.is_running is False

    @pytest.mark.skipif(not PYNPUT_AVAILABLE, reason="pynput not available")
    def test_start_sets_running_flag(self):
        """Test start sets is_running flag."""
        callback = Mock()
        listener = QuickInputHotkeyListener(on_hotkey=callback)
        listener.start()
        assert listener.is_running is True
        listener.stop()

    @pytest.mark.skipif(not PYNPUT_AVAILABLE, reason="pynput not available")
    def test_stop_clears_running_flag(self):
        """Test stop clears is_running flag."""
        callback = Mock()
        listener = QuickInputHotkeyListener(on_hotkey=callback)
        listener.start()
        listener.stop()
        assert listener.is_running is False

    def test_on_press_with_exception(self):
        """Test _on_press handles exceptions gracefully."""
        callback = Mock()
        listener = QuickInputHotkeyListener(on_hotkey=callback)
        # Should not raise even with invalid key
        listener._on_press(None)


class TestQuickInputManager:
    """Tests for QuickInputManager."""

    def test_init_creates_instance(self):
        """Test initialization creates manager instance."""
        manager = QuickInputManager()
        assert manager is not None
        assert manager.api_url == "http://localhost:8000"
        assert manager.window_controller is None
        assert manager.hotkey_listener is None

    def test_init_with_custom_api_url(self):
        """Test initialization with custom API URL."""
        manager = QuickInputManager(api_url="http://api:9000")
        assert manager.api_url == "http://api:9000"

    @patch('src.macos.quick_input.PYNPUT_AVAILABLE', True)
    @patch('src.macos.quick_input.QuickInputHotkeyListener')
    def test_setup_creates_components(self, mock_listener_class):
        """Test setup creates window controller and hotkey listener."""
        mock_listener = MagicMock()
        mock_listener_class.return_value = mock_listener
        
        manager = QuickInputManager()
        # Patch the window controller allocation
        with patch('src.macos.quick_input.QuickInputWindowController') as mock_window:
            mock_window.alloc.return_value.init.return_value = MagicMock()
            manager.setup()
        
        assert manager.window_controller is not None
        assert manager.hotkey_listener is not None

    def test_show_popup_with_controller(self):
        """Test show_popup when controller exists."""
        manager = QuickInputManager()
        manager.window_controller = MagicMock()
        manager.show_popup()
        manager.window_controller.show_window.assert_called_once()

    def test_show_popup_without_controller(self):
        """Test show_popup when controller is None."""
        manager = QuickInputManager()
        manager.show_popup()  # Should not raise

    def test_cleanup_without_components(self):
        """Test cleanup when components are None."""
        manager = QuickInputManager()
        manager.cleanup()  # Should not raise

    def test_cleanup_with_components(self):
        """Test cleanup with initialized components."""
        manager = QuickInputManager()
        manager.hotkey_listener = MagicMock()
        manager.window_controller = MagicMock()
        
        manager.cleanup()
        
        manager.hotkey_listener.stop.assert_called_once()
        manager.window_controller.close.assert_called_once()

    def test_on_hotkey_pressed_calls_show_popup(self):
        """Test _on_hotkey_pressed shows popup."""
        manager = QuickInputManager()
        manager.window_controller = MagicMock()
        
        manager._on_hotkey_pressed()
        manager.window_controller.show_window.assert_called_once()

    def test_on_window_close(self):
        """Test _on_window_close callback."""
        manager = QuickInputManager()
        manager._on_window_close()  # Should not raise


# Skip all tests if PyObjC is not available
if not PYOBJC_AVAILABLE:
    pytestmark = pytest.mark.skip(reason="PyObjC not available")
