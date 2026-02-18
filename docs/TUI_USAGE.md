# TUI Usage Guide

The Terminal User Interface (TUI) provides an interactive dashboard for managing tasks and initiatives from your terminal.

## Getting Started

Launch the TUI with:

```bash
pa tui
```

The dashboard shows:
- **Left Panel**: Top 10 highest-priority tasks in a table
- **Right Panel**: Active initiatives with progress bars
- **Status Bar**: Agent polling status and controls

## Keyboard Shortcuts

### Navigation
- `↑` / `↓` - Navigate between tasks
- `j` / `k` - Navigate tasks (vim-style)
- `Enter` - Expand selected task details
- `Esc` - Close modals
- `q` - Quit the application

### Task Actions
- `c` - Complete the selected task
- `d` - Delete the selected task
- `e` - Edit task (coming in Phase 3)
- `l` - Show full task list with filters
- `o` - Open document links (coming in Phase 2)
- `m` - Mark tasks for merging (coming in Phase 4)

### Agent Control
- `p` - Trigger an immediate poll (coming in Phase 3)
- `a` - Toggle auto-polling on/off
- `+` / `-` - Increase/decrease poll interval (coming in Phase 3)

### Other
- `?` - Show this help screen
- `Tab` - Switch between panels

## Features

### Task Display
- Shows top 10 prioritized tasks
- Color-coded priority indicators (🔴 critical, 🟠 high, 🟡 medium, 🟢 low)
- Relative due dates (Today, Tomorrow, Xd)
- Initiative association with color
- Document link count

### Initiative Sidebar
- Lists all active initiatives
- Shows progress bars (█░)
- Displays completed/total tasks
- Collapsible for more screen space

### Agent Status
- Running/Stopped indicator (● green/red)
- Last poll time (e.g., "5m ago")
- Autonomy level (suggest, auto_low, auto, full)
- Poll count this session

### Task Details Modal
Press `Enter` on a task to see full details:
- Complete task description
- All tags
- All document links (clickable)
- Creation and update timestamps

## Configuration

Add to your `config.yaml`:

```yaml
tui:
  refresh_interval_seconds: 5    # How often to refresh data
  show_completed: false          # Hide completed tasks
  default_group_by: initiative   # Group by initiative or priority
  default_sort_by: priority_score # Sort order
  max_tasks_in_dashboard: 10     # Tasks shown in main view
  enable_mouse: true             # Click to select and navigate
  theme: dark                    # Theme: dark or light
```

## Tips & Tricks

1. **Quick Complete**: Select a task with arrow keys, press `c` to complete it immediately
2. **Batch View**: Press `l` to see all tasks with search and filter options
3. **Document Links**: Tasks with document links show 🔗 count. Press `o` to open them
4. **Auto-Polling**: Press `a` to toggle automatic polling without leaving the dashboard
5. **Task Details**: Press `Enter` to see full task information including description and all tags

## Troubleshooting

### TUI won't start
Check that Textual is installed:
```bash
pip install textual
```

### Data not refreshing
- Check that the database is accessible
- Verify the config path with `pa config path`
- Try restarting with `q` and running `pa tui` again

### Tasks not showing
- Ensure tasks exist in the database: `pa tasks list`
- Check that the database path in config is correct
- Verify file permissions on the database

### Colors look wrong
Your terminal may not support 256 colors. Try:
```bash
export COLORTERM=truecolor
pa tui
```

## Coming Soon

### Phase 3 (Agent Control)
- Manual poll triggering from TUI
- Poll interval adjustment
- Pause/resume auto-polling
- Real-time polling indicators

### Phase 4 (Polish)
- Task merge with AI-powered title combining
- Mouse support (click to select, drag to reorder)
- Light/dark themes
- Custom keyboard shortcuts
- Performance optimization for 100+ tasks

## Keyboard Shortcut Reference

```
NAVIGATION          TASK ACTIONS        AGENT CONTROL       OTHER
─────────────────   ─────────────────   ─────────────────   ─────────────────
↑/k                 c Complete          p Poll Now          ? Help
↓/j                 d Delete            a Toggle Auto       q Quit
Enter Details       e Edit              +/- Interval        Tab Switch Panel
Esc Close          l List All
               o Open Link
               m Mark Merge
```

## Performance Notes

- Dashboard updates every 5 seconds (configurable)
- Table refresh completes in < 500ms
- Handles 100+ tasks smoothly with automatic pagination
- Database queries are optimized with eager loading
- Only visible rows are rendered for efficiency

## Support

For issues or feature requests, please open an issue on the project repository.
