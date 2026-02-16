---
title: "macOS Menu Bar App: NSAlert Dialog Not Receiving Keyboard Input"
category: ui-bugs
component: macos-menu-bar-app
tags: [AppKit, NSWindow, NSAlert, menu-bar-app, keyboard-focus, tkinter, subprocess]
severity: high
status: solved
date_solved: 2026-02-16
related_issues: []
keywords: [menu-bar, dialog, keyboard, focus, NSAlert, floating-window, modal]
---

# macOS Menu Bar App: NSAlert Dialog Not Receiving Keyboard Input

## Problem Symptom

When clicking the "Quick Input" menu item in the macOS menu bar application, an NSAlert dialog would appear but:
- Keyboard input would not be received by the dialog
- The dialog would either not display at all or display but appear frozen
- Text typed would either go to the background application or be lost
- Using `runModal()` would cause the entire menu bar app to hang indefinitely

### Observable Behavior

1. Menu bar application running correctly
2. User clicks "✏ Quick Input" menu item
3. Expected: Input dialog appears with keyboard focus
4. Actual: 
   - First attempts: No dialog appeared
   - After NSAlert fixes: Dialog appeared but `runModal()` hung forever
   - Keyboard input never reached the dialog

### Error Patterns

In logs during attempts:
```
Creating NSAlert
Alert created, showing modal dialog...
[Process hangs indefinitely - no more log output]
```

## Investigation Steps

### Step 1: Floating Window Approach (Failed)
**Approach**: Create a custom `NSFloatingWindowLevel` window with keyboard handling
- Created `QuickInputWindow` subclass with `canBecomeKeyWindow()` returning True
- Tried multiple activation sequences: `activateIgnoringOtherApps()`, `makeKeyAndOrderFront()`, `orderFrontRegardless()`, `makeKeyWindow()`
- Result: Window appeared but `isKeyWindow()` always returned False
- **Root Cause**: Floating windows are non-intrusive UI elements and do not participate in normal macOS focus management

### Step 2: NSAlert with Custom Text Field (Failed)
**Approach**: Use NSAlert for proper modal dialog handling
- Created NSAlert with `NSTextField` as accessory view
- Initially tried `performSelectorOnMainThread` with unregistered selector
- Then tried using `NSObject` delegate subclass to properly manage the alert
- Result: Alert appeared to create successfully but `alert.runModal()` blocked indefinitely
- **Root Cause**: NSAlert.runModal() requires a parent window; menu bar apps have no main window, so the alert blocks waiting for a parent that never appears

### Step 3: Subprocess with Tkinter (Success!)
**Approach**: Launch dialog in separate process, avoiding AppKit event loop issues
- Created standalone `quick_input_dialog.py` with pure tkinter interface
- Subprocess runs independently with its own event loop
- Dialog outputs JSON result to stdout
- Menu app parses result and processes input
- Result: Dialog displays properly, accepts keyboard input reliably, doesn't block menu bar
- **Why this works**: Tkinter has its own event loop and window management; no dependency on parent windows or AppKit focus management

## Root Cause Analysis

### The Core Issue: AppKit Event Loop and Focus Management

**Menu bar apps in macOS have unique constraints:**
1. They are "background" applications without a traditional application window
2. NSStatusBar items float above the dock but are not part of the standard window hierarchy
3. AppKit's focus management is hierarchical - modal dialogs need a parent window to attach to

**Why each approach failed:**

| Approach | Issue | Technical Reason |
|----------|-------|------------------|
| NSFloatingWindowLevel | Window appeared but wouldn't receive keyboard events | Floating windows explicitly opt-out of focus management; they're meant to be non-intrusive |
| NSWindow (custom) | Even with `canBecomeKeyWindow() = True`, window never became key | Menu bar context doesn't participate in normal window activation sequences |
| NSAlert.runModal() | Process hung indefinitely | `runModal()` blocks waiting for the alert to be dismissed, but without a parent window, the modal event loop never starts |
| NSAlert.beginSheet() | Would require an existing window to attach to | Menu bar apps have no main window to attach sheets to |

### Why Subprocess + Tkinter Works

1. **Independent Event Loop**: Tkinter runs in its own process with its own event loop
2. **No Parent Window Dependency**: Tkinter dialogs are standalone and don't need attachment to parent windows
3. **System Window Management**: Tkinter uses native system calls that properly manage focus and input
4. **Non-Blocking**: The subprocess runs in background thread, menu bar app continues responding
5. **Cross-Platform**: Same code works on macOS, Linux, Windows

## Solution

### Implementation

**1. Created standalone dialog script** (`src/macos/quick_input_dialog.py`):
```python
import json
import tkinter as tk
from tkinter import ttk

def show_input_dialog():
    """Show input dialog and return result as JSON."""
    root = tk.Tk()
    root.title("Quick Task Input")
    root.geometry("500x150")
    
    # ... UI setup ...
    
    # Center and bring to front
    root.lift()
    root.attributes('-topmost', True)
    root.focus_force()
    
    # ... button handlers ...
    
    root.mainloop()
    
    # Output result as JSON
    print(json.dumps(result))
```

**2. Updated QuickInputSheet** (`src/macos/quick_input_sheet.py`):
```python
class QuickInputSheet:
    def show(self, parent_window=None) -> None:
        """Show the quick input dialog."""
        logger.info("Showing quick input dialog")
        
        # Run dialog in background thread
        thread = threading.Thread(
            target=self._show_dialog_in_subprocess, 
            daemon=True
        )
        thread.start()
    
    def _show_dialog_in_subprocess(self) -> None:
        """Show dialog in subprocess."""
        dialog_script = Path(__file__).parent / "quick_input_dialog.py"
        
        # Launch subprocess and capture output
        result = subprocess.run(
            [sys.executable, str(dialog_script)],
            capture_output=True,
            text=True,
            timeout=60.0
        )
        
        # Parse JSON result
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout.strip())
            if data.get("submitted") and data.get("text"):
                self._process_input(data["text"])
```

**3. Updated menu_app.py** to use `QuickInputSheetManager`:
```python
from src.macos.quick_input_sheet import QuickInputSheetManager

class TaskMenuApp:
    def configure(self, api_url, refresh_interval):
        self.quick_input_sheet_manager = QuickInputSheetManager(api_url=api_url)
        self.quick_input_sheet_manager.setup()
    
    def show_quick_input(self, sender=None):
        if self.quick_input_sheet_manager:
            self.quick_input_sheet_manager.show_quick_input()
```

### How It Works

1. User clicks "✏ Quick Input" menu item
2. Menu app calls `show_quick_input()`
3. `QuickInputSheetManager.show_quick_input()` is called
4. `QuickInputSheet.show()` is called in background thread
5. Subprocess launches `quick_input_dialog.py`
6. Tkinter dialog displays with proper keyboard focus
7. User types input and clicks Submit (or presses Enter)
8. Dialog closes and outputs JSON: `{"submitted": true, "text": "user input"}`
9. Menu app parses JSON and calls `_process_input(text)`
10. Input is parsed for commands and submitted to API as task

### Key Features

- **Non-blocking**: Menu bar app stays responsive while dialog is open
- **Proper Focus**: Tkinter dialog receives keyboard input correctly
- **Command Support**: Parses special commands:
  - `parse <text>` - Natural language processing
  - `voice` - Voice input (not yet implemented)
  - `priority <level> <text>` - Set priority
  - Plain text - Regular task input
- **Visual Polish**: Centered on screen, hints for command syntax, works across monitors

## Prevention Strategies

### For Menu Bar App Dialogs

1. **Avoid NSAlert.runModal() in menu bar apps** - Will hang waiting for parent window
2. **Don't use floating windows for interactive input** - They don't receive focus
3. **Consider subprocess approach** for dialogs in background apps that need:
   - User input while app runs other tasks
   - Reliable keyboard focus
   - Simple, isolated UI

### For AppKit Development

1. **Understand window hierarchy** - Modal dialogs require parent windows
2. **Test in menu bar context** - Issues specific to background apps don't appear in foreground apps
3. **Use AppKit when possible** - For pure native feel, but subprocess as fallback for complex scenarios
4. **Document AppKit constraints** - Menu bar apps have different rules than foreground apps

## Related Documentation

- [macOS Menu Bar Application Implementation](../../architecture/macos-menu-bar.md)
- [Python AppKit Dialog Patterns](../../guides/appkit-dialogs.md)
- PyObjC Documentation: NSAlert, NSWindow, NSFloatingWindowLevel

## Testing

### Manual Testing Checklist

- [x] Dialog appears when menu item clicked
- [x] Dialog has keyboard focus (can type immediately)
- [x] Submit button works
- [x] Cancel button closes without action
- [x] Enter key submits
- [x] Escape key cancels
- [x] Plain text input works
- [x] `parse <text>` command works
- [x] `priority <level> <text>` command works
- [x] Tasks are created in API
- [x] Menu bar stays responsive during input

### Automated Tests

Consider adding:
```python
def test_quick_input_dialog_subprocess():
    """Verify subprocess dialog launches and parses output."""
    # Test JSON output parsing
    # Test timeout handling
    # Test subprocess error cases

def test_quick_input_command_parsing():
    """Verify command parser works correctly."""
    # Test parse command
    # Test priority command
    # Test plain text
```

## Commits

```
98a0c05 Fix Phase 3: Switch quick input from floating window to modal sheet
4f19cdc Fix NSAlert display using NSObject delegate pattern
0541056 Switch to subprocess dialog approach for quick input
```

## Lessons Learned

1. **AppKit has different semantics for menu bar apps** - Solutions that work in foreground apps may fail
2. **Modal dialogs need parent windows** - NSAlert.runModal() is not suitable for background apps
3. **Subprocess approach is viable for UI** - Can be cleaner than fighting AppKit event loops
4. **Test in actual context** - Menu bar behavior differs from foreground app behavior
5. **Document platform constraints** - Easy to miss AppKit's focus management requirements

## Status

**SOLVED** ✓

The quick input feature now works reliably:
- Dialog displays when menu item is clicked
- Keyboard input is properly received
- User can type commands or text
- Results are submitted to API
- Menu bar app remains responsive

This unblocks Phases 4 and 5 of the macOS application enhancement project.
