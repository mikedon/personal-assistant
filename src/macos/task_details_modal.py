#!/usr/bin/env python3
"""Standalone task details modal using tkinter.

This runs as a separate process to avoid blocking the menu bar app.
Displays full task information and provides quick action buttons.
"""

import json
import sys
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime
from typing import Any, Dict, List
import webbrowser


def show_task_details_modal(task_data: Dict[str, Any]) -> Dict[str, Any]:
    """Show a task details modal and return the result as JSON.
    
    Args:
        task_data: Dictionary containing task information
        
    Returns:
        Dictionary with action taken and result
    """
    result = {"action": None, "task_id": task_data.get("id"), "success": False}
    
    def on_complete():
        """Mark task as completed."""
        result["action"] = "complete"
        result["success"] = True
        root.destroy()
    
    def on_priority_changed(priority_value):
        """Handle priority change."""
        result["action"] = "change_priority"
        result["priority"] = priority_value
        result["success"] = True
        root.destroy()
    
    def on_due_date_clicked():
        """Show due date picker dialog."""
        # Simple date picker using tkinter
        date_dialog = tk.Toplevel(root)
        date_dialog.title("Change Due Date")
        date_dialog.geometry("300x150")
        date_dialog.resizable(False, False)
        date_dialog.transient(root)
        date_dialog.grab_set()
        
        frame = ttk.Frame(date_dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="Enter new due date (YYYY-MM-DD):").pack(pady=(0, 10))
        
        current_due = task_data.get("due_date", "")
        entry = ttk.Entry(frame)
        entry.pack(fill=tk.X, pady=(0, 15))
        entry.insert(0, current_due if current_due else "")
        entry.focus_set()
        
        def on_ok():
            date_str = entry.get().strip()
            if date_str:
                try:
                    # Validate date format
                    datetime.fromisoformat(date_str)
                    result["action"] = "change_due_date"
                    result["due_date"] = date_str
                    result["success"] = True
                    date_dialog.destroy()
                    root.destroy()
                except ValueError:
                    messagebox.showerror("Invalid Date", "Please enter date in YYYY-MM-DD format")
            else:
                # Clear due date
                result["action"] = "change_due_date"
                result["due_date"] = None
                result["success"] = True
                date_dialog.destroy()
                root.destroy()
        
        def on_cancel():
            date_dialog.destroy()
        
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text="Cancel", command=on_cancel).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="OK", command=on_ok).pack(side=tk.LEFT)
        
        entry.bind('<Return>', lambda e: on_ok())
        entry.bind('<Escape>', lambda e: on_cancel())
    
    def on_open_dashboard():
        """Open dashboard in browser."""
        result["action"] = "open_dashboard"
        result["success"] = True
        root.destroy()
    
    def on_close():
        """Close modal without action."""
        root.destroy()
    
    # Create window
    root = tk.Tk()
    root.title(f"Task: {task_data.get('title', 'Untitled')}")
    root.geometry("600x500")
    root.resizable(True, True)
    
    # Bring to front
    root.lift()
    root.attributes('-topmost', True)
    root.after_idle(root.attributes, '-topmost', False)
    
    # Create main frame with scrollbar
    main_frame = ttk.Frame(root)
    main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    
    # Canvas for scrollable content
    canvas = tk.Canvas(main_frame, bg='white', highlightthickness=0)
    scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
    scrollable_frame = ttk.Frame(canvas)
    
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    
    # Bind mouse wheel to scroll
    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    canvas.bind_all("<MouseWheel>", _on_mousewheel)
    
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    # Title
    title_label = ttk.Label(
        scrollable_frame,
        text=task_data.get("title", "Untitled"),
        font=('Arial', 14, 'bold')
    )
    title_label.pack(anchor=tk.W, pady=(0, 10))
    
    # Description
    if task_data.get("description"):
        ttk.Label(scrollable_frame, text="Description:", font=('Arial', 10, 'bold')).pack(anchor=tk.W)
        desc_text = tk.Text(scrollable_frame, height=3, width=60, wrap=tk.WORD, bg='#f5f5f5')
        desc_text.insert(tk.END, task_data.get("description", ""))
        desc_text.config(state=tk.DISABLED)
        desc_text.pack(anchor=tk.W, pady=(0, 10))
    
    # Task details grid
    details_frame = ttk.Frame(scrollable_frame)
    details_frame.pack(anchor=tk.W, fill=tk.X, pady=(0, 15))
    
    # Helper function to create detail rows
    def add_detail_row(label_text: str, value_text: str):
        row = ttk.Frame(details_frame)
        row.pack(anchor=tk.W, fill=tk.X, pady=3)
        label = ttk.Label(row, text=f"{label_text}:", font=('Arial', 9, 'bold'), width=15)
        label.pack(side=tk.LEFT)
        value = ttk.Label(row, text=value_text, font=('Arial', 9))
        value.pack(side=tk.LEFT, padx=(10, 0))
        return row
    
    # Priority
    priority = task_data.get("priority", "medium").upper()
    priority_symbols = {
        "CRITICAL": "🔴",
        "HIGH": "🟠",
        "MEDIUM": "🟡",
        "LOW": "🟢",
    }
    priority_symbol = priority_symbols.get(priority, "○")
    add_detail_row("Priority", f"{priority_symbol} {priority}")
    
    # Status
    status = task_data.get("status", "pending").upper()
    add_detail_row("Status", status)
    
    # Due Date
    due_date = task_data.get("due_date", "")
    due_date_text = due_date if due_date else "No due date"
    add_detail_row("Due Date", due_date_text)
    
    # Tags
    tags = task_data.get("tags", [])
    if tags:
        tags_text = " ".join([f"#{tag}" for tag in tags])
        add_detail_row("Tags", tags_text)
    
    # Created At
    created_at = task_data.get("created_at", "")
    if created_at:
        add_detail_row("Created", created_at)
    
    # Initiative
    initiative = task_data.get("initiative_title")
    if initiative:
        add_detail_row("Initiative", initiative)
    
    # Document Links
    document_links = task_data.get("document_links", [])
    if document_links:
        ttk.Label(scrollable_frame, text="Document Links:", font=('Arial', 10, 'bold')).pack(anchor=tk.W, pady=(10, 5))
        
        links_frame = ttk.Frame(scrollable_frame)
        links_frame.pack(anchor=tk.W, fill=tk.X, pady=(0, 15))
        
        for link in document_links:
            # Determine file icon based on URL
            link_text = str(link)
            if link_text.lower().endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx')):
                icon = "📄"
            elif link_text.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                icon = "🖼️"
            else:
                icon = "🔗"
            
            # Create clickable link
            link_button = tk.Label(
                links_frame,
                text=f"{icon} {link_text}",
                fg='blue',
                cursor='hand2',
                font=('Arial', 9),
                wraplength=500,
                justify=tk.LEFT
            )
            link_button.pack(anchor=tk.W, pady=2)
            
            # Make link clickable
            def make_link_handler(url):
                def handler(event=None):
                    try:
                        webbrowser.open(url)
                    except Exception as e:
                        messagebox.showerror("Error", f"Failed to open link: {e}")
                return handler
            
            link_button.bind('<Button-1>', make_link_handler(link_text))
    
    # Quick Actions Section
    actions_frame = ttk.LabelFrame(scrollable_frame, text="Quick Actions", padding="10")
    actions_frame.pack(anchor=tk.W, fill=tk.X, pady=(0, 15))
    
    # Priority dropdown
    priority_frame = ttk.Frame(actions_frame)
    priority_frame.pack(anchor=tk.W, fill=tk.X, pady=(0, 10))
    
    ttk.Label(priority_frame, text="Change Priority:").pack(side=tk.LEFT, padx=(0, 10))
    priority_var = tk.StringVar(value=priority)
    priority_combo = ttk.Combobox(
        priority_frame,
        textvariable=priority_var,
        values=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
        state="readonly",
        width=12
    )
    priority_combo.pack(side=tk.LEFT, padx=(0, 10))
    
    def on_priority_select(event=None):
        new_priority = priority_var.get()
        if new_priority and new_priority != priority:
            on_priority_changed(new_priority.lower())
    
    priority_combo.bind("<<ComboboxSelected>>", on_priority_select)
    
    # Buttons frame
    buttons_frame = ttk.Frame(actions_frame)
    buttons_frame.pack(anchor=tk.W, fill=tk.X, pady=(10, 0))
    
    ttk.Button(
        buttons_frame,
        text="✓ Complete Task",
        command=on_complete
    ).pack(side=tk.LEFT, padx=(0, 10))
    
    ttk.Button(
        buttons_frame,
        text="📅 Change Due Date",
        command=on_due_date_clicked
    ).pack(side=tk.LEFT, padx=(0, 10))
    
    ttk.Button(
        buttons_frame,
        text="→ Open Dashboard",
        command=on_open_dashboard
    ).pack(side=tk.LEFT)
    
    # Bottom buttons
    bottom_buttons = ttk.Frame(root)
    bottom_buttons.pack(fill=tk.X, padx=10, pady=10)
    
    ttk.Button(bottom_buttons, text="Close", command=on_close).pack(side=tk.RIGHT)
    
    # Bind Escape to close
    root.bind('<Escape>', lambda e: on_close())
    
    # Center window on screen
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (root.winfo_width() // 2)
    y = (root.winfo_screenheight() // 2) - (root.winfo_height() // 2)
    root.geometry(f'+{x}+{y}')
    
    root.mainloop()
    
    return result


if __name__ == "__main__":
    try:
        # Read task data from stdin or command line argument
        if len(sys.argv) > 1:
            # Task data passed as JSON argument
            task_json = sys.argv[1]
        else:
            # Read from stdin
            task_json = sys.stdin.read()
        
        task_data = json.loads(task_json)
        result = show_task_details_modal(task_data)
        
        # Output result as JSON to stdout
        output = json.dumps(result)
        print(output, file=sys.stdout)
        sys.stdout.flush()
        sys.exit(0 if result.get("success") else 1)
    
    except Exception as e:
        # Output error as JSON
        error_result = {"action": None, "success": False, "error": str(e)}
        print(json.dumps(error_result), file=sys.stderr)
        sys.exit(1)
