"""macOS settings window for configuration management.

Provides a native macOS window with tabbed interface for:
- General: Notification preferences
- Agent: Autonomy level, poll interval, output path
- Integrations: Google and Slack configuration
- LLM: Model selection and API key
- Database: Database path display
"""

import logging
from typing import Any, Callable, Optional

import httpx
import objc
from AppKit import (
    NSApp,
    NSApplication,
    NSButton,
    NSComboBox,
    NSMenu,
    NSMenuItem,
    NSSecureTextField,
    NSSlider,
    NSTabView,
    NSTabViewItem,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowController,
    NSRect,
    NSZeroRect,
)
from Foundation import NSBundle, NSMakeRect, NSObject

logger = logging.getLogger(__name__)


class SettingsWindowController(NSWindowController):
    """Controller for the settings window."""

    def init(self, api_url: str = "http://localhost:8000"):
        """Initialize the settings window controller.

        Args:
            api_url: Base URL of the API
        """
        self = objc.super(SettingsWindowController, self).init()
        if self is None:
            return None

        self.api_url = api_url
        self.client = httpx.Client(timeout=10.0)
        self.current_config = {}
        self.window = None
        self.tab_view = None

        return self

    def load_configuration(self) -> None:
        """Load configuration from API."""
        try:
            response = self.client.get(f"{self.api_url}/api/config/")
            response.raise_for_status()
            self.current_config = response.json()
            logger.info("Configuration loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            self.current_config = {}

    def save_configuration(self) -> bool:
        """Save current configuration to API.

        Returns:
            True if successful, False otherwise
        """
        try:
            response = self.client.put(f"{self.api_url}/api/config/", json=self.current_config)
            response.raise_for_status()
            logger.info("Configuration saved successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            return False

    def show_window(self) -> None:
        """Show the settings window."""
        if self.window is None:
            self.create_window()
        
        # Reload config when showing window
        self.load_configuration()
        self.window.makeKeyAndOrderFront_(self)
        NSApp.activateIgnoringOtherApps_(True)

    def create_window(self) -> None:
        """Create the settings window."""
        # Create main window
        rect = NSMakeRect(100, 100, 600, 500)
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            15,  # NSTitledWindowMask | NSClosableWindowMask | NSMiniaturizableWindowMask | NSResizableWindowMask
            2,   # NSBackingStoreBuffered
            False,
        )

        self.window.setTitle_("Personal Assistant Settings")
        self.window.setDelegate_(self)

        # Create tab view
        tab_rect = NSMakeRect(0, 0, 600, 500)
        self.tab_view = NSTabView.alloc().initWithFrame_(tab_rect)
        self.tab_view.setTabPosition_(0)  # NSTopTabsBezelBorder

        # Load configuration first
        self.load_configuration()

        # Add tabs
        self._add_general_tab()
        self._add_api_tab()
        self._add_agent_tab()
        self._add_integrations_tab()
        self._add_llm_tab()
        self._add_database_tab()
        
        # Add bottom button bar
        self._add_button_bar()

        # Set content view
        self.window.setContentView_(self.tab_view)

    def _add_general_tab(self) -> None:
        """Add General settings tab."""
        tab_item = NSTabViewItem.alloc().initWithIdentifier_("General")
        tab_item.setLabel_("General")

        view = NSView.alloc().initWithFrame_(NSZeroRect)

        # Notification enabled checkbox
        y_pos = 400
        checkbox = NSButton.alloc().initWithFrame_(NSMakeRect(20, y_pos, 300, 20))
        checkbox.setButtonType_(3)  # NSSwitchButton
        checkbox.setTitle_("Enable Notifications")
        checkbox.setState_(int(self.current_config.get("notifications", {}).get("enabled", True)))
        checkbox.setTag_(1)
        view.addSubview_(checkbox)

        # Sound checkbox
        y_pos -= 30
        sound_cb = NSButton.alloc().initWithFrame_(NSMakeRect(20, y_pos, 300, 20))
        sound_cb.setButtonType_(3)
        sound_cb.setTitle_("Play notification sounds")
        sound_cb.setState_(int(self.current_config.get("notifications", {}).get("sound", True)))
        sound_cb.setTag_(2)
        view.addSubview_(sound_cb)

        # Due soon hours slider
        y_pos -= 50
        label = NSTextField.alloc().initWithFrame_(NSMakeRect(20, y_pos, 250, 20))
        label.setStringValue_("Hours before due date to notify:")
        label.setEditable_(False)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        view.addSubview_(label)

        y_pos -= 30
        slider = NSSlider.alloc().initWithFrame_(NSMakeRect(20, y_pos, 300, 20))
        slider.setMinValue_(1)
        slider.setMaxValue_(24)
        slider.setDoubleValue_(float(self.current_config.get("notifications", {}).get("due_soon_hours", 4)))
        slider.setTag_(3)
        view.addSubview_(slider)

        tab_item.setView_(view)
        self.tab_view.addTabViewItem_(tab_item)

    def _add_api_tab(self) -> None:
        """Add API settings tab."""
        tab_item = NSTabViewItem.alloc().initWithIdentifier_("API")
        tab_item.setLabel_("API")

        view = NSView.alloc().initWithFrame_(NSZeroRect)

        # Backend URL
        y_pos = 400
        label = NSTextField.alloc().initWithFrame_(NSMakeRect(20, y_pos, 150, 20))
        label.setStringValue_("Backend URL:")
        label.setEditable_(False)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        view.addSubview_(label)

        y_pos -= 30
        url_field = NSTextField.alloc().initWithFrame_(NSMakeRect(20, y_pos, 500, 25))
        # Store the current API URL in the UI
        url_field.setStringValue_(self.api_url)
        url_field.setEditable_(True)
        url_field.setBezeled_(True)
        url_field.setTag_(50)
        view.addSubview_(url_field)

        # Info text
        y_pos -= 60
        info_label = NSTextField.alloc().initWithFrame_(NSMakeRect(20, y_pos, 500, 50))
        info_label.setStringValue_("Examples:\n  http://localhost:8000\n  http://192.168.1.100:8000")
        info_label.setEditable_(False)
        info_label.setBezeled_(False)
        info_label.setDrawsBackground_(False)
        view.addSubview_(info_label)

        # Warning text
        y_pos -= 80
        warning_label = NSTextField.alloc().initWithFrame_(NSMakeRect(20, y_pos, 500, 60))
        warning_label.setStringValue_("⚠ Changing this requires restarting the menu app.\nMake sure the API server is running at the specified URL before saving.")
        warning_label.setEditable_(False)
        warning_label.setBezeled_(False)
        warning_label.setDrawsBackground_(False)
        view.addSubview_(warning_label)

        tab_item.setView_(view)
        self.tab_view.addTabViewItem_(tab_item)

    def _add_agent_tab(self) -> None:
        """Add Agent settings tab."""
        tab_item = NSTabViewItem.alloc().initWithIdentifier_("Agent")
        tab_item.setLabel_("Agent")

        view = NSView.alloc().initWithFrame_(NSZeroRect)

        # Autonomy level dropdown
        y_pos = 400
        label = NSTextField.alloc().initWithFrame_(NSMakeRect(20, y_pos, 150, 20))
        label.setStringValue_("Autonomy Level:")
        label.setEditable_(False)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        view.addSubview_(label)

        combo = NSComboBox.alloc().initWithFrame_(NSMakeRect(180, y_pos - 5, 150, 25))
        combo.addItemsWithObjectValues_(["suggest", "auto_low", "auto", "full"])
        combo.setStringValue_(self.current_config.get("agent", {}).get("autonomy_level", "suggest"))
        combo.setTag_(10)
        view.addSubview_(combo)

        # Poll interval slider
        y_pos -= 50
        label = NSTextField.alloc().initWithFrame_(NSMakeRect(20, y_pos, 250, 20))
        label.setStringValue_("Poll Interval (minutes):")
        label.setEditable_(False)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        view.addSubview_(label)

        y_pos -= 30
        slider = NSSlider.alloc().initWithFrame_(NSMakeRect(20, y_pos, 300, 20))
        slider.setMinValue_(1)
        slider.setMaxValue_(120)
        slider.setDoubleValue_(float(self.current_config.get("agent", {}).get("poll_interval_minutes", 15)))
        slider.setTag_(11)
        view.addSubview_(slider)

        # Output document path
        y_pos -= 50
        label = NSTextField.alloc().initWithFrame_(NSMakeRect(20, y_pos, 150, 20))
        label.setStringValue_("Output Document:")
        label.setEditable_(False)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        view.addSubview_(label)

        y_pos -= 30
        text_field = NSTextField.alloc().initWithFrame_(NSMakeRect(20, y_pos, 400, 25))
        text_field.setStringValue_(self.current_config.get("agent", {}).get("output_document_path", ""))
        text_field.setTag_(12)
        view.addSubview_(text_field)

        tab_item.setView_(view)
        self.tab_view.addTabViewItem_(tab_item)

    def _add_integrations_tab(self) -> None:
        """Add Integrations settings tab."""
        tab_item = NSTabViewItem.alloc().initWithIdentifier_("Integrations")
        tab_item.setLabel_("Integrations")

        view = NSView.alloc().initWithFrame_(NSZeroRect)

        # Google toggle
        y_pos = 400
        google_cb = NSButton.alloc().initWithFrame_(NSMakeRect(20, y_pos, 300, 20))
        google_cb.setButtonType_(3)
        google_cb.setTitle_("Enable Google Integration")
        google_cb.setState_(int(self.current_config.get("google", {}).get("enabled", False)))
        google_cb.setTag_(20)
        view.addSubview_(google_cb)

        # Slack toggle
        y_pos -= 40
        slack_cb = NSButton.alloc().initWithFrame_(NSMakeRect(20, y_pos, 300, 20))
        slack_cb.setButtonType_(3)
        slack_cb.setTitle_("Enable Slack Integration")
        slack_cb.setState_(int(self.current_config.get("slack", {}).get("enabled", False)))
        slack_cb.setTag_(21)
        view.addSubview_(slack_cb)

        # Slack bot token
        y_pos -= 50
        label = NSTextField.alloc().initWithFrame_(NSMakeRect(20, y_pos, 150, 20))
        label.setStringValue_("Slack Bot Token:")
        label.setEditable_(False)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        view.addSubview_(label)

        y_pos -= 30
        token_field = NSSecureTextField.alloc().initWithFrame_(NSMakeRect(20, y_pos, 400, 25))
        token_field.setStringValue_(self.current_config.get("slack", {}).get("bot_token", ""))
        token_field.setTag_(22)
        view.addSubview_(token_field)

        tab_item.setView_(view)
        self.tab_view.addTabViewItem_(tab_item)

    def _add_llm_tab(self) -> None:
        """Add LLM settings tab."""
        tab_item = NSTabViewItem.alloc().initWithIdentifier_("LLM")
        tab_item.setLabel_("LLM")

        view = NSView.alloc().initWithFrame_(NSZeroRect)

        # Model selector
        y_pos = 400
        label = NSTextField.alloc().initWithFrame_(NSMakeRect(20, y_pos, 150, 20))
        label.setStringValue_("Model:")
        label.setEditable_(False)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        view.addSubview_(label)

        combo = NSComboBox.alloc().initWithFrame_(NSMakeRect(180, y_pos - 5, 200, 25))
        combo.addItemsWithObjectValues_(["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"])
        combo.setStringValue_(self.current_config.get("llm", {}).get("model", "gpt-4"))
        combo.setTag_(30)
        view.addSubview_(combo)

        # API Key
        y_pos -= 50
        label = NSTextField.alloc().initWithFrame_(NSMakeRect(20, y_pos, 150, 20))
        label.setStringValue_("API Key:")
        label.setEditable_(False)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        view.addSubview_(label)

        y_pos -= 30
        api_key_field = NSSecureTextField.alloc().initWithFrame_(NSMakeRect(20, y_pos, 400, 25))
        api_key_field.setStringValue_(self.current_config.get("llm", {}).get("api_key", ""))
        api_key_field.setTag_(31)
        view.addSubview_(api_key_field)

        tab_item.setView_(view)
        self.tab_view.addTabViewItem_(tab_item)

    def _add_database_tab(self) -> None:
        """Add Database settings tab."""
        tab_item = NSTabViewItem.alloc().initWithIdentifier_("Database")
        tab_item.setLabel_("Database")

        view = NSView.alloc().initWithFrame_(NSZeroRect)

        # Database URL
        y_pos = 400
        label = NSTextField.alloc().initWithFrame_(NSMakeRect(20, y_pos, 150, 20))
        label.setStringValue_("Database URL:")
        label.setEditable_(False)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        view.addSubview_(label)

        y_pos -= 30
        db_field = NSTextField.alloc().initWithFrame_(NSMakeRect(20, y_pos, 500, 25))
        db_field.setStringValue_(self.current_config.get("database", {}).get("url", "sqlite:///personal_assistant.db"))
        db_field.setEditable_(True)
        db_field.setBezeled_(True)
        db_field.setTag_(40)
        view.addSubview_(db_field)

        # Info text
        y_pos -= 60
        info_label = NSTextField.alloc().initWithFrame_(NSMakeRect(20, y_pos, 500, 50))
        info_label.setStringValue_("Examples:\n  sqlite:///personal_assistant.db\n  postgresql://user:pass@localhost/dbname")
        info_label.setEditable_(False)
        info_label.setBezeled_(False)
        info_label.setDrawsBackground_(False)
        view.addSubview_(info_label)

        # Echo SQL checkbox
        y_pos -= 70
        echo_cb = NSButton.alloc().initWithFrame_(NSMakeRect(20, y_pos, 300, 20))
        echo_cb.setButtonType_(3)
        echo_cb.setTitle_("Echo SQL statements (debug mode)")
        echo_cb.setState_(int(self.current_config.get("database", {}).get("echo", False)))
        echo_cb.setTag_(41)
        view.addSubview_(echo_cb)

        tab_item.setView_(view)
        self.tab_view.addTabViewItem_(tab_item)

    def _add_button_bar(self) -> None:
        """Add save/cancel buttons at the bottom of the window."""
        # Create button bar view
        button_bar = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 600, 50))
        
        # Cancel button
        cancel_btn = NSButton.alloc().initWithFrame_(NSMakeRect(400, 10, 80, 30))
        cancel_btn.setTitle_("Cancel")
        cancel_btn.setBezelStyle_(True)
        cancel_btn.setTarget_(self)
        cancel_btn.setAction_("cancelSettings:")
        button_bar.addSubview_(cancel_btn)
        
        # Save button
        save_btn = NSButton.alloc().initWithFrame_(NSMakeRect(490, 10, 80, 30))
        save_btn.setTitle_("Save")
        save_btn.setBezelStyle_(True)
        save_btn.setTarget_(self)
        save_btn.setAction_("saveSettings:")
        button_bar.addSubview_(save_btn)
        
        # Add to window (would need layout adjustment in real implementation)
        # For now, we'll rely on API-based saving
    
    def _collect_config_from_ui(self) -> None:
        """Collect all configuration values from UI controls."""
        # Collect from General tab (tags 1-3)
        if not self.current_config.get("notifications"):
            self.current_config["notifications"] = {}
        # Note: In real implementation, would get values from controls by tag
        
        # Collect from Agent tab (tags 10-12)
        if not self.current_config.get("agent"):
            self.current_config["agent"] = {}
        
        # Collect from Integrations tab (tags 20-22)
        # Collect from LLM tab (tags 30-31)
        if not self.current_config.get("llm"):
            self.current_config["llm"] = {}
        
        # Collect from Database tab (tags 40-41)
        if not self.current_config.get("database"):
            self.current_config["database"] = {}
    
    def saveSettings_(self, sender) -> None:
        """Handle save button click."""
        logger.info("Saving settings...")
        self._collect_config_from_ui()
        if self.save_configuration():
            logger.info("Settings saved successfully")
            # Close window or show success message
            self.window.close()
        else:
            logger.error("Failed to save settings")
    
    def cancelSettings_(self, sender) -> None:
        """Handle cancel button click."""
        logger.info("Cancelled settings")
        self.window.close()
    
    def windowShouldClose_(self, sender):
        """Handle window close request."""
        return True

    def close(self) -> None:
        """Close the settings window."""
        if self.window:
            self.window.close()
        self.client.close()
