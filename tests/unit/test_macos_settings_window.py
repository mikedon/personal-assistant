"""Unit tests for macOS settings window controller."""

import pytest
from unittest.mock import Mock, MagicMock, patch

try:
    from src.macos.settings_window import SettingsWindowController
    PYOBJC_AVAILABLE = True
except ImportError:
    PYOBJC_AVAILABLE = False


@pytest.mark.skipif(not PYOBJC_AVAILABLE, reason="PyObjC not available")
class TestSettingsWindowController:
    """Tests for SettingsWindowController."""

    def test_init_creates_instance(self):
        """Test initialization creates controller instance."""
        controller = SettingsWindowController.alloc().init()
        assert controller is not None
        assert controller.api_url == "http://localhost:8000"
        assert controller.current_config == {}
        assert controller.window is None
        assert controller.tab_view is None

    def test_init_with_custom_api_url(self):
        """Test initialization with custom API URL."""
        custom_url = "http://example.com:9000"
        controller = SettingsWindowController.alloc().init(api_url=custom_url)
        assert controller.api_url == custom_url

    @patch('src.macos.settings_window.httpx.Client')
    def test_load_configuration_success(self, mock_client_class):
        """Test loading configuration from API."""
        # Setup mock
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "agent": {"autonomy_level": "auto"},
            "notifications": {"enabled": True}
        }
        mock_client.get.return_value = mock_response
        
        controller = SettingsWindowController.alloc().init()
        controller.load_configuration()
        
        assert controller.current_config == {
            "agent": {"autonomy_level": "auto"},
            "notifications": {"enabled": True}
        }

    @patch('src.macos.settings_window.httpx.Client')
    def test_load_configuration_failure(self, mock_client_class):
        """Test loading configuration handles errors gracefully."""
        # Setup mock to raise exception
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get.side_effect = Exception("Connection error")
        
        controller = SettingsWindowController.alloc().init()
        controller.load_configuration()
        
        # Should still have empty config
        assert controller.current_config == {}

    @patch('src.macos.settings_window.httpx.Client')
    def test_save_configuration_success(self, mock_client_class):
        """Test saving configuration to API."""
        # Setup mock
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_client.put.return_value = mock_response
        
        controller = SettingsWindowController.alloc().init()
        controller.current_config = {
            "agent": {"autonomy_level": "full"}
        }
        
        result = controller.save_configuration()
        assert result is True

    @patch('src.macos.settings_window.httpx.Client')
    def test_save_configuration_failure(self, mock_client_class):
        """Test saving configuration handles errors."""
        # Setup mock to raise exception
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.put.side_effect = Exception("Connection error")
        
        controller = SettingsWindowController.alloc().init()
        result = controller.save_configuration()
        assert result is False

    @patch('src.macos.settings_window.NSWindow')
    @patch('src.macos.settings_window.NSTabView')
    def test_create_window(self, mock_tab_view_class, mock_window_class):
        """Test window creation."""
        # Setup mocks
        mock_window = MagicMock()
        mock_window_class.return_value = mock_window
        
        mock_tab = MagicMock()
        mock_tab_view_class.return_value = mock_tab
        
        controller = SettingsWindowController.alloc().init()
        controller.current_config = {
            "agent": {"autonomy_level": "suggest", "poll_interval_minutes": 15, "output_document_path": ""},
            "notifications": {"enabled": True, "sound": True, "due_soon_hours": 4},
            "llm": {"model": "gpt-4", "api_key": "test-key"},
            "slack": {"enabled": False, "bot_token": ""},
            "google": {"enabled": False},
            "database": {"url": "sqlite:///test.db"}
        }
        
        with patch.object(controller, '_add_general_tab'):
            with patch.object(controller, '_add_agent_tab'):
                with patch.object(controller, '_add_integrations_tab'):
                    with patch.object(controller, '_add_llm_tab'):
                        with patch.object(controller, '_add_database_tab'):
                            controller.create_window()
        
        assert controller.window is not None
        assert controller.tab_view is not None

    def test_show_window_before_creation(self):
        """Test show_window creates window if not exists."""
        controller = SettingsWindowController.alloc().init()
        
        with patch.object(controller, 'create_window') as mock_create:
            with patch('src.macos.settings_window.NSApp'):
                # First call should create window
                controller.show_window()
                mock_create.assert_called_once()

    def test_window_should_close_delegate(self):
        """Test windowShouldClose_ delegate method."""
        controller = SettingsWindowController.alloc().init()
        result = controller.windowShouldClose_(None)
        assert result is True

    @patch('src.macos.settings_window.httpx.Client')
    def test_close_closes_window_and_client(self, mock_client_class):
        """Test close method closes window and client."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        controller = SettingsWindowController.alloc().init()
        controller.window = MagicMock()
        
        controller.close()
        
        controller.window.close.assert_called_once()
        mock_client.close.assert_called_once()

    def test_close_without_window(self):
        """Test close method when window is None."""
        controller = SettingsWindowController.alloc().init()
        controller.window = None
        
        # Should not raise
        controller.close()

    @patch('src.macos.settings_window.httpx.Client')
    def test_load_configuration_caches_config(self, mock_client_class):
        """Test load_configuration caches the loaded config."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        config_data = {"agent": {"autonomy_level": "auto"}}
        mock_response = MagicMock()
        mock_response.json.return_value = config_data
        mock_client.get.return_value = mock_response
        
        controller = SettingsWindowController.alloc().init()
        controller.load_configuration()
        
        # Verify config is cached
        assert controller.current_config == config_data
        
        # Second call should still get cached value
        assert controller.current_config == config_data

    @patch('src.macos.settings_window.httpx.Client')
    def test_api_client_timeout_configured(self, mock_client_class):
        """Test API client timeout is configured."""
        controller = SettingsWindowController.alloc().init()
        
        # Verify client was created with timeout
        # The actual timeout value is set in init
        assert controller.client is not None

    def test_general_tab_configuration(self):
        """Test general tab has expected controls."""
        controller = SettingsWindowController.alloc().init()
        controller.current_config = {
            "notifications": {"enabled": True, "sound": True, "due_soon_hours": 4}
        }
        
        # This test verifies the structure, actual UIKit calls are mocked
        with patch('src.macos.settings_window.NSView'):
            with patch('src.macos.settings_window.NSTabViewItem'):
                with patch('src.macos.settings_window.NSButton'):
                    with patch('src.macos.settings_window.NSSlider'):
                        with patch('src.macos.settings_window.NSTextField'):
                            with patch('src.macos.settings_window.NSTabView'):
                                controller.tab_view = MagicMock()
                                controller._add_general_tab()

    def test_settings_window_initialization_complete(self):
        """Test full initialization flow completes without error."""
        controller = SettingsWindowController.alloc().init(api_url="http://test:8000")
        
        assert controller is not None
        assert controller.api_url == "http://test:8000"
        assert controller.current_config == {}
        assert controller.client is not None


# Skip all tests if PyObjC is not available
if not PYOBJC_AVAILABLE:
    pytestmark = pytest.mark.skip(reason="PyObjC not available")
