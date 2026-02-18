#!/usr/bin/env python3
"""Minimal test: NSAlert in a menu bar app."""

from AppKit import NSApp, NSAlert, NSStatusBar, NSMenu, NSMenuItem, NSApplication
from Foundation import NSMakeRect
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def show_alert():
    """Show a simple alert dialog."""
    logger.info("Creating NSAlert...")
    try:
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Test Alert")
        alert.setInformativeText_("Type something:")
        alert.addButtonWithTitle_("OK")
        alert.addButtonWithTitle_("Cancel")
        
        logger.info("Showing alert with runModal...")
        response = alert.runModal()
        logger.info(f"Alert response: {response}")
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)


def show_menu_item_clicked(sender):
    """Handle menu item click."""
    logger.info("Menu item clicked!")
    show_alert()


def main():
    app = NSApplication.sharedApplication()
    
    # Create status bar item
    status_bar = NSStatusBar.systemStatusBar()
    status_item = status_bar.statusItemWithLength_(-1)
    status_item.setTitle_("Test")
    
    # Create menu
    menu = NSMenu.alloc().init()
    item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Show Alert", "showAlert:", ""
    )
    menu.addItem_(item)
    
    status_item.setMenu_(menu)
    
    # Set target for menu item
    item.setTarget_(app)
    item.setAction_("showAlert:")
    
    logger.info("App starting, click menu to show alert...")
    app.run()


if __name__ == "__main__":
    main()
