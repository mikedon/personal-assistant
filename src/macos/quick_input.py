"""Quick input popup for task creation with global hotkey listener.

Provides a Spotlight-style floating window for fast task entry via Cmd+Shift+A.
Supports quick commands (parse, voice, priority) and direct text input.
"""

import logging
import threading
from typing import Callable, Optional

import httpx
import objc
from AppKit import (
    NSApp,
    NSButton,
    NSComboBox,
    NSEvent,
    NSFont,
    NSScreen,
    NSSecureTextField,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowController,
    NSRect,
    NSZeroRect,
    NSKeyDown,
)
from Foundation import NSMakeRect, NSObject

from src.macos.command_parser import CommandParser, ParsedCommand

logger = logging.getLogger(__name__)

try:
    from pynput.keyboard import Listener, Key, KeyCode
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    logger.warning("pynput not available - global hotkey will not work")


class QuickInputWindow(NSWindow):
    """Custom window with proper keyboard event handling."""
    
    def canBecomeKeyWindow(self) -> bool:
        """Window can become the key window (receive keyboard events)."""
        logger.debug("canBecomeKeyWindow called")
        return True
    
    def canBecomeMainWindow(self) -> bool:
        """Window can become the main window."""
        logger.debug("canBecomeMainWindow called")
        return True
    
    def becomeKeyWindow(self) -> None:
        """Handle becoming key window."""
        logger.debug("becomeKeyWindow called")
        objc.super(QuickInputWindow, self).becomeKeyWindow()
    
    def mouseDown_(self, event) -> None:
        """Handle mouse down event."""
        logger.debug(f"Mouse down event: {event}")
        objc.super(QuickInputWindow, self).mouseDown_(event)
    
    def keyDown_(self, event) -> None:
        """Handle keyboard event."""
        chars = event.characters()
        logger.debug(f"Key down event: {chars} (code: {event.keyCode()})")
        objc.super(QuickInputWindow, self).keyDown_(event)


class QuickInputTextField(NSTextField):
    """Custom text field with improved keyboard handling."""
    
    controller = None  # Reference to the controller
    
    def acceptsFirstResponder(self) -> bool:
        """Allow this field to receive keyboard focus."""
        return True
    
    def becomeFirstResponder(self) -> bool:
        """Handle becoming first responder."""
        return objc.super(QuickInputTextField, self).becomeFirstResponder()


class QuickInputWindowController(NSWindowController):
    """Controller for the quick input popup window."""

    def init(self, api_url: str = "http://localhost:8000", on_close: Optional[Callable] = None):
        """Initialize the quick input window controller.

        Args:
            api_url: Base URL of the API
            on_close: Callback when window closes
        """
        self = objc.super(QuickInputWindowController, self).init()
        if self is None:
            return None

        self.api_url = api_url
        self.client = httpx.Client(timeout=10.0)
        self.on_close = on_close
        self.window = None
        self.text_field = None
        self.suggestions_box = None
        self.submit_button = None

        return self

    def create_window(self) -> None:
        """Create the quick input popup window centered on screen."""
        # Get center of active screen
        screen = NSScreen.mainScreen()
        screen_frame = screen.frame()
        
        # Popup dimensions (Spotlight-like size)
        width = 500
        height = 60
        x = (screen_frame.size.width - width) / 2 + screen_frame.origin.x
        y = (screen_frame.size.height - height) / 2 + screen_frame.origin.y
        
        rect = NSMakeRect(x, y, width, height)
        
        # Create custom window with appropriate style
        style_mask = 1 + 2  # NSWindowStyleMaskTitled + NSWindowStyleMaskClosable
        self.window = QuickInputWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            style_mask,
            2,   # NSBackingStoreBuffered
            False,
        )
        
        self.window.setTitle_("Quick Input")
        self.window.setDelegate_(self)
        self.window.setLevel_(10)  # Floating window level (NSFloatingWindowLevel)
        self.window.setOpaque_(True)
        self.window.setHasShadow_(True)
        self.window.setReleasedWhenClosed_(False)  # Keep window in memory
        self.window.setAcceptsMouseMovedEvents_(True)  # Accept mouse events
        self.window.setCanHide_(False)  # Don't hide with app
        
        # Create content view
        content = NSView.alloc().initWithFrame_(NSZeroRect)
        
        # Create custom text field with improved focus handling
        text_frame = NSMakeRect(10, 10, width - 100, 40)
        self.text_field = QuickInputTextField.alloc().initWithFrame_(text_frame)
        self.text_field.setPlaceholderString_("Enter task or command...")
        self.text_field.setDelegate_(self)
        self.text_field.setEditable_(True)
        self.text_field.setSelectable_(True)
        self.text_field.controller = self
        content.addSubview_(self.text_field)
        
        # Create submit button
        button_frame = NSMakeRect(width - 80, 10, 70, 40)
        self.submit_button = NSButton.alloc().initWithFrame_(button_frame)
        self.submit_button.setTitle_("Submit")
        self.submit_button.setTarget_(self)
        self.submit_button.setAction_("submit:")
        content.addSubview_(self.submit_button)
        
        self.window.setContentView_(content)

    def show_window(self) -> None:
        """Show the quick input window and focus text field."""
        logger.info("===== SHOW WINDOW CALLED =====")
        if self.window is None:
            logger.info("Creating window...")
            self.create_window()
        
        # Clear text field
        if self.text_field:
            logger.info("Clearing text field")
            self.text_field.setStringValue_("")
        
        # Make window key and bring to front (MUST be in this order)
        # 1. Activate the app first
        logger.info("1. Activating app")
        NSApp.activateIgnoringOtherApps_(True)
        
        # 2. Make window key (receives keyboard events)
        logger.info("2. Making window key and ordering front")
        self.window.makeKeyAndOrderFront_(self)
        
        # 3. Ensure window is in front
        logger.info("3. Ordering window front regardless")
        self.window.orderFrontRegardless()
        
        # 4. Set window as main window
        logger.info("4. Setting as main window")
        try:
            NSApp.setMainWindow_(self.window)
        except Exception as e:
            logger.error(f"Error setting main window: {e}")
        
        # 5. Set focus to text field - critical for keyboard input
        try:
            if self.text_field:
                logger.info("5. Making text field first responder")
                # Make sure text field is visible and part of responder chain
                result = self.window.makeFirstResponder_(self.text_field)
                logger.info(f"makeFirstResponder result: {result}")
                logger.info(f"Text field is first responder: {self.window.firstResponder() == self.text_field}")
                logger.info(f"Window first responder: {self.window.firstResponder()}")
            else:
                logger.error("Text field is None!")
        except Exception as e:
            logger.error(f"Error setting first responder: {e}", exc_info=True)
        
        try:
            logger.info(f"Window is key: {self.window.isKeyWindow()}")
            logger.info(f"Window is main: {self.window.isMainWindow()}")
        except Exception as e:
            logger.error(f"Error getting window state: {e}")
        
        logger.info("===== SHOW WINDOW COMPLETE =====")

    def submit_(self, sender=None) -> None:
        """Handle submit button or Enter key."""
        if not self.text_field:
            return
        
        text = self.text_field.stringValue()
        if not text:
            return
        
        # Parse command
        parsed = CommandParser.parse(text)
        
        # Submit to API
        self._submit_command(parsed)
        
        # Close window
        self.close()

    def controlTextDidChange_(self, notification) -> None:
        """Handle text field changes."""
        pass

    def windowShouldClose_(self, sender) -> bool:
        """Handle window close."""
        if self.on_close:
            self.on_close()
        return True

    def close(self) -> None:
        """Close the window and cleanup."""
        if self.window:
            self.window.close()
        self.client.close()

    def _submit_command(self, parsed: ParsedCommand) -> None:
        """Submit parsed command to API in background thread.

        Args:
            parsed: Parsed command from input
        """
        thread = threading.Thread(target=self._submit_to_api, args=(parsed,))
        thread.daemon = True
        thread.start()

    def _submit_to_api(self, parsed: ParsedCommand) -> None:
        """Submit to API (runs in background thread).

        Args:
            parsed: Parsed command
        """
        try:
            if parsed.command_type == "voice":
                # TODO: Implement voice recording
                logger.info("Voice command received")
                return
            
            # Prepare task data
            task_data = {
                "title": parsed.text,
                "priority": parsed.priority or "medium",
            }
            
            if parsed.command_type == "parse":
                # For parse commands, send for NLP processing
                task_data["description"] = parsed.text
                task_data["parse_natural_language"] = True
            
            # Submit to API
            response = self.client.post(f"{self.api_url}/api/tasks", json=task_data)
            response.raise_for_status()
            logger.info(f"Task created: {response.json()}")
            
        except Exception as e:
            logger.error(f"Failed to create task: {e}")


class QuickInputHotkeyListener:
    """Global hotkey listener for quick input popup."""

    def __init__(self, on_hotkey: Callable[[], None]):
        """Initialize hotkey listener.

        Args:
            on_hotkey: Callback when hotkey is pressed
        """
        self.on_hotkey = on_hotkey
        self.listener: Optional[Listener] = None
        self.is_running = False

    def start(self) -> None:
        """Start listening for hotkey (Cmd+Shift+A)."""
        if not PYNPUT_AVAILABLE:
            logger.warning("pynput not available - hotkey listener disabled")
            return
        
        if self.is_running:
            return
        
        self.is_running = True
        self.listener = Listener(on_press=self._on_press)
        self.listener.start()
        logger.info("Quick input hotkey listener started")

    def stop(self) -> None:
        """Stop listening for hotkey."""
        if self.listener:
            self.listener.stop()
            self.is_running = False
            logger.info("Quick input hotkey listener stopped")

    def _on_press(self, key) -> None:
        """Handle key press event.

        Args:
            key: The pressed key
        """
        try:
            # Check for Cmd+Shift+A
            if self._is_hotkey_pressed(key):
                self.on_hotkey()
        except Exception as e:
            logger.error(f"Error handling hotkey: {e}")

    @staticmethod
    def _is_hotkey_pressed(key) -> bool:
        """Check if hotkey (Cmd+Shift+A) was pressed.

        Args:
            key: The pressed key

        Returns:
            True if hotkey was pressed
        """
        # Note: This is a simplified check
        # In real implementation, we track key state across presses
        # For now, return False - will be improved with state tracking
        return False


class QuickInputManager:
    """Manager for quick input popup and hotkey."""

    def __init__(self, api_url: str = "http://localhost:8000"):
        """Initialize quick input manager.

        Args:
            api_url: Base URL of the API
        """
        self.api_url = api_url
        self.window_controller: Optional[QuickInputWindowController] = None
        self.hotkey_listener: Optional[QuickInputHotkeyListener] = None

    def setup(self) -> None:
        """Setup quick input popup and hotkey listener."""
        # Create window controller
        self.window_controller = QuickInputWindowController.alloc().init(
            api_url=self.api_url,
            on_close=self._on_window_close,
        )
        
        # Setup hotkey listener
        self.hotkey_listener = QuickInputHotkeyListener(on_hotkey=self._on_hotkey_pressed)
        self.hotkey_listener.start()

    def show_popup(self) -> None:
        """Show quick input popup."""
        if self.window_controller:
            self.window_controller.show_window()

    def _on_hotkey_pressed(self) -> None:
        """Handle hotkey press."""
        self.show_popup()

    def _on_window_close(self) -> None:
        """Handle window close."""
        # Window closed, ready for next hotkey
        pass

    def cleanup(self) -> None:
        """Cleanup resources."""
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        if self.window_controller:
            self.window_controller.close()
