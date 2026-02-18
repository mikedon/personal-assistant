---
title: feat: Build TUI dashboard for task management with initiative grouping
type: feat
status: active
date: 2026-02-18
---

# feat: Build TUI dashboard for task management with initiative grouping

## Overview
Replace the current CLI interaction model with a modern terminal user interface (TUI) that shows the most important tasks in a tabular format, organizes tasks by initiatives, provides quick access to document links, controls agent polling, and allows inline task completion and merging. The TUI will mirror the functionality visible in the macOS menu bar app but provide a more comprehensive interactive interface.

## Problem Statement
The current CLI uses a command-based interaction model (e.g., `pa tasks list`, `pa tasks complete <id>`) which is functional but requires knowing commands and task IDs. The macOS menu bar app shows a curated list of important tasks, but there's no equivalent TUI for terminal-based workflows. A TUI would provide:
- Real-time task visibility organized by initiatives
- Interactive task management without memorizing task IDs
- Quick document link access
- Agent polling control and status monitoring
- Task operations (complete, merge) without leaving the interface

## Current State
- CLI in `src/cli.py` uses Click framework with Rich formatting
- Task data model in `src/models/task.py:1-100` with priority scoring and initiative linking
- macOS app in `src/macos/` displays tasks by priority
- API in `src/api/` provides data access layer
- Database uses SQLAlchemy ORM with task/initiative relationships
- Configuration system via `config.yaml` with Pydantic validation

## Proposed Solution
Build a TUI application using Textual (Python framework for terminal UIs) with these screens:

1. **Main Dashboard** - Two-column layout:
   - Left: Table of top 10 most important tasks with quick stats
   - Right: Initiative sidebar showing active initiatives and progress
   - Status bar: Agent status, last poll time, polling controls

2. **Full Task List** - Modal/expanded view showing all filtered tasks

3. **Task Details Modal** - Expanded view with full details and actions

4. **Document Links Panel** - Quick-access list with keyboard shortcuts to open links

5. **Agent Control Panel** - View agent status, adjust poll intervals, trigger manual polls

## Technical Approach

### Architecture
- Use **Textual** for the TUI framework (modern, async-ready, composable)
- Create widget hierarchy:
  - `TaskDashboardApp` (main application)
    - `TaskTable` (sortable, selectable task list)
    - `InitiativePanel` (collapsible sidebar)
    - `AgentStatusBar` (bottom status)
    - `DocumentLinksModal` (popup for link access)
    - `TaskDetailsModal` (popup for full details)
- Maintain separation from existing CLI (no breaking changes)
- Reuse existing database layer and models
- Polling state synced with agent via database (PID file already exists)

### Key Features

**Main Dashboard:**
- Auto-refreshing task list (polling interval configurable)
- Task table columns: Priority (emoji), Title, Status, Due Date, Initiative, Link Count
- Keyboard navigation (arrow keys, vim keys)
- Click to expand task details, press 'c' to complete, 'm' to mark for merge
- Initiative sidebar shows:
  - Initiative title with priority emoji
  - Progress bar (completed/total)
  - Task count per initiative
  - Collapsible to show/hide task counts
- Agent status panel shows:
  - Running/stopped status with visual indicator
  - Last poll time (relative: "5 minutes ago")
  - Autonomy level
  - Poll count this session
  - Button to trigger manual poll (shortcut: 'p')
  - Button to toggle auto-polling (shortcut: 'a')

**Full Task List:**
- Modal overlay showing all tasks (not just top 10)
- Filter controls (status, priority, initiative, date range)
- Sort controls (priority, due date, created, title)
- Search input (fuzzy match on title/description)

**Task Details Modal:**
- Show full task info: title, description, tags, due date, links, initiative
- Action buttons: Complete, Delete, Edit, Link Add, Link Remove
- Document links displayed as clickable entries

**Document Links Panel:**
- Show all links for selected task
- Keyboard shortcuts: 'o' + number to open, 'c' to copy
- Support opening with system default (macOS open, xdg-open on Linux)

**Agent Control:**
- Status indicator showing running/stopped with PID
- Last poll time and stats
- Manual poll button with progress indicator
- Poll interval adjustment (increase/decrease)
- Auto-polling toggle

### Technology Stack
- **Textual**: TUI framework (supports async, mouse, colors)
- **Existing**: SQLAlchemy (ORM), Pydantic (config), Rich (formatting)
- **Optional**: watchfiles for file monitoring (if document links need watching)

### Database Changes
No new tables needed. Existing schema supports all required features:
- `tasks` table: id, title, priority, status, due_date, initiative_id, document_links
- `initiatives` table: id, title, priority, status, target_date
- PID file already tracks agent status

### Configuration
Add to config.yaml:

```yaml
tui:
  refresh_interval_seconds: 5
  show_completed: false
  default_group_by: initiative
  default_sort_by: priority_score
  max_tasks_in_dashboard: 10
  enable_mouse: true
  theme: dark
```

### File Structure

```
src/
  tui/
    __init__.py
    app.py
    widgets/
      task_table.py
      initiative_panel.py
      agent_status.py
      document_links.py
      task_details.py
    models.py
    actions.py
    shortcuts.py
  cli.py
```

## Implementation Phases

### Phase 1: Foundation
- Set up Textual project structure
- Create basic application shell with layout
- Implement task table widget with live data binding
- Add initiative sidebar with progress calculation
- Add agent status bar with polling state
- Keyboard navigation (arrow keys, enter/esc)
- Configuration support
- Success: Basic TUI shows live tasks and initiatives

### Phase 2: Core Interactions
- Task actions: complete, delete (with confirmation)
- Task details modal with expandable view
- Document links modal with open capability
- Filter/search functionality in full task list
- Sort controls (priority, due date, title)
- Initiative grouping and collapsing
- Success: All core task operations work from TUI

### Phase 3: Agent Control
- Agent status monitoring (running/stopped)
- Manual poll trigger with progress spinner
- Poll interval adjustment UI
- Auto-polling toggle
- Last poll time display (relative format)
- Success: Full agent control without leaving TUI

### Phase 4: Polish & Integration
- Task merge modal with title merging preview
- Mouse support (click to select, scroll)
- Theme support (dark/light)
- Keyboard shortcut help (press '?')
- Performance optimization for large task lists
- Integration with existing CLI (`pa tui` command)
- Comprehensive tests (unit + integration)
- Documentation (README section, keyboard shortcuts)
- Success: Feature-complete, tested, documented

## Alternative Approaches Considered

1. **Extend Rich with custom TUI**: Would require writing low-level terminal control code. Textual is purpose-built and more maintainable.

2. **Use curses directly**: Too low-level, would mean reimplementing features Textual provides.

3. **Web-based dashboard**: Different workflow (browser vs terminal), adds complexity (web server, dependencies). TUI keeps it terminal-native.

4. **Extend existing Click CLI with interactive menus**: Limited interactivity and real-time updates compared to Textual.

## Acceptance Criteria

### Functional Requirements
- TUI starts with `pa tui` command
- Main dashboard displays top 10 tasks with priority, title, status, due date, initiative
- Initiative sidebar shows active initiatives with progress bars and task counts
- Tasks grouped by initiative in list view
- Can complete tasks by selecting and pressing 'c' (with confirmation)
- Can merge multiple tasks together (modal workflow)
- Can view and open document links (clickable or 'o' shortcut)
- Can see full task details in modal (description, tags, all links)
- Agent status shows running/stopped, last poll time, manual poll button
- Can trigger manual poll from TUI without leaving
- Can adjust polling behavior (auto-poll toggle, interval adjustment)
- Full task list view accessible (modal or 'l' shortcut) with filtering and search
- Keyboard shortcuts work (arrow keys, enter, esc, c, m, o, p, a, ?)
- Mouse support for clicking tasks, scrolling (optional but nice)

### Non-Functional Requirements
- Dashboard refreshes smoothly without lag (< 100ms between polls)
- Handles 100+ tasks without performance degradation
- TUI remains responsive during agent polling
- Database queries optimized (eager load related data)
- No breaking changes to existing CLI
- Configuration optional (sensible defaults)

### Quality Gates
- Test coverage >= 80% (unit tests for widgets, integration tests for flows)
- No errors with 0-500+ tasks
- Documentation includes:
  - README section on TUI usage
  - Keyboard shortcuts reference
  - Configuration options
  - Troubleshooting guide
- Code review approval (style, patterns, architecture)

## Success Metrics
- `pa tui` starts without errors
- Tasks display within 1 second of launch
- Dashboard refresh completes in < 500ms
- All keyboard shortcuts work as documented
- Task operations (complete, merge) execute in < 1 second
- Can manage 10+ initiatives with smooth grouping/collapsing

## Dependencies & Prerequisites
- Textual library (pip install textual)
- Python 3.11+ (already required)
- Existing database and models (no changes needed)
- Agent system already provides polling capability

## Risk Analysis & Mitigation

**Risk: Textual introduces new dependency**
- Mitigation: Optional feature (only required for `pa tui`), doesn't affect CLI/API
- Mitigation: Textual is well-maintained by Textualize, actively developed

**Risk: Large task lists could cause performance issues**
- Mitigation: Implement lazy-loading, paginate in full list view
- Mitigation: Only refresh visible area in dashboard

**Risk: Agent polling state sync complexity**
- Mitigation: Read from existing PID file mechanism (already works)
- Mitigation: Use database for polling stats (already logged)

**Risk: Keyboard shortcut conflicts with terminal**
- Mitigation: Use standard TUI shortcuts (vim-like keys)
- Mitigation: Test on macOS, Linux, WSL (where applicable)

## Resource Requirements
- **Time**: ~6 weeks full-time (4-5 weeks part-time)
- **Skills**: Python async, Textual, terminal UI patterns
- **Infrastructure**: No new services, uses existing database

## Future Considerations
- Export task list to CSV/JSON
- Task calendar view (timeline)
- Initiative burndown charts
- Time tracking integration (Toggl, Clockify)
- Slack status updates from TUI
- Vim-mode and Emacs-mode keybindings
- Custom color themes
- Task history/audit log view

## Documentation Plan

**To be created/updated:**
- `TUI_USAGE.md` - Getting started with TUI, keyboard shortcuts
- `docs/ARCHITECTURE.md` - Add TUI section
- `README.md` - Add TUI section to quick start
- `config.example.yaml` - Add TUI config section
- In-app help screen (press '?' in TUI)

## References & Research

### Internal References
- Architecture: docs/ARCHITECTURE.md (existing design patterns)
- Models: src/models/task.py (task schema), src/models/initiative.py
- Services: src/services/task_service.py (database queries)
- macOS app: src/macos/ (similar task display logic)
- API: src/api/routes/tasks.py (reference for filtering logic)

### External References
- Textual documentation: https://textual.textualize.io/
- Textual widgets guide: https://textual.textualize.io/widgets/
- Terminal UI patterns: https://en.wikipedia.org/wiki/Ncurses
- Python async: https://docs.python.org/3/library/asyncio.html

### Related Work
- Existing CLI commands in src/cli.py (reuse logic where possible)
- macOS menu bar implementation (similar data flow)
