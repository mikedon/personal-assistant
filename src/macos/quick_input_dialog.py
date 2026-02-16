#!/usr/bin/env python3
"""Standalone quick input dialog using tkinter.

This runs as a separate process to avoid blocking the menu bar app.
"""

import json
import sys
import tkinter as tk
from tkinter import ttk


def show_input_dialog():
    """Show a simple input dialog and return the result as JSON."""
    result = {"submitted": False, "text": ""}
    
    def on_submit():
        result["submitted"] = True
        result["text"] = entry.get()
        root.destroy()
    
    def on_cancel():
        root.destroy()
    
    # Create window
    root = tk.Tk()
    root.title("Quick Task Input")
    root.geometry("500x150")
    root.resizable(False, False)
    
    # Bring to front
    root.lift()
    root.attributes('-topmost', True)
    root.after_idle(root.attributes, '-topmost', False)
    root.focus_force()
    
    # Main frame
    frame = ttk.Frame(root, padding="20")
    frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    
    # Label
    label = ttk.Label(frame, text="Enter a task or command:")
    label.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
    
    # Entry
    entry = ttk.Entry(frame, width=50)
    entry.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 20))
    entry.insert(0, "")
    entry.focus_set()
    
    # Placeholder hint
    hint = ttk.Label(frame, text="Examples: 'buy milk', 'parse call mom tomorrow', 'priority high finish report'", 
                     font=('', 9), foreground='gray')
    hint.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(0, 15))
    
    # Buttons frame
    button_frame = ttk.Frame(frame)
    button_frame.grid(row=3, column=0, columnspan=2, sticky=tk.E)
    
    cancel_btn = ttk.Button(button_frame, text="Cancel", command=on_cancel)
    cancel_btn.grid(row=0, column=0, padx=(0, 10))
    
    submit_btn = ttk.Button(button_frame, text="Submit", command=on_submit, default='active')
    submit_btn.grid(row=0, column=1)
    
    # Bind Enter key to submit
    entry.bind('<Return>', lambda e: on_submit())
    entry.bind('<Escape>', lambda e: on_cancel())
    
    # Center window on screen
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (root.winfo_width() // 2)
    y = (root.winfo_screenheight() // 2) - (root.winfo_height() // 2)
    root.geometry(f'+{x}+{y}')
    
    root.mainloop()
    
    # Output result as JSON
    print(json.dumps(result))


if __name__ == "__main__":
    show_input_dialog()
