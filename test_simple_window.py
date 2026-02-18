#!/usr/bin/env python3
"""Minimal test: Create a simple window with text input to debug focus issues."""

import sys
from AppKit import NSApp, NSWindow, NSTextField, NSRect, NSApplication, NSMenu, NSMenuItem
from Foundation import NSMakeRect, NSObject
import objc


class AppDelegate(NSObject):
    """Minimal app delegate to handle app lifecycle."""
    
    def applicationDidFinishLaunching_(self, notification):
        """Called when app finishes launching."""
        print("App launched")
    
    def applicationShouldTerminateAfterLastWindowClosed_(self, sender):
        """Allow app to terminate when window closes."""
        return True


class SimpleTextWindow:
    """Minimal window to test keyboard input."""
    
    def __init__(self):
        self.window = None
        self.text_field = None
    
    def create_window(self):
        """Create a very simple window."""
        # Window frame
        rect = NSMakeRect(100, 100, 400, 100)
        
        # Create window
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            15,  # All style options
            2,   # NSBackingStoreBuffered
            False
        )
        
        self.window.setTitle_("Test Input")
        self.window.setLevel_(10)  # Floating
        
        # Create text field directly in window (no custom view)
        text_rect = NSMakeRect(10, 10, 380, 80)
        self.text_field = NSTextField.alloc().initWithFrame_(text_rect)
        self.text_field.setPlaceholderString_("Type here...")
        self.text_field.setEditable_(True)
        self.text_field.setSelectable_(True)
        
        self.window.contentView().addSubview_(self.text_field)
    
    def show(self):
        """Show window and focus text field."""
        print("Creating window...")
        self.create_window()
        
        print("Activating app...")
        NSApp.activateIgnoringOtherApps_(True)
        
        print("Showing window...")
        self.window.makeKeyAndOrderFront_(self)
        
        print(f"Window is key: {self.window.isKeyWindow()}")
        print(f"Window is main: {self.window.isMainWindow()}")
        
        print("Focusing text field...")
        self.window.makeFirstResponder_(self.text_field)
        print(f"First responder: {self.window.firstResponder()}")
        
        print("\nType in the window. Press Ctrl+C to exit.")


def main():
    # Create app
    app = NSApplication.sharedApplication()
    
    # Set app delegate
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    
    # Create minimal menu (required for proper app behavior)
    menu = NSMenu.alloc().init()
    menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit", "terminate:", "q")
    menu.addItem_(menu_item)
    app.setMainMenu_(menu)
    
    # Create and show window
    test_window = SimpleTextWindow()
    test_window.show()
    
    # Run app loop
    app.run()


if __name__ == "__main__":
    main()
