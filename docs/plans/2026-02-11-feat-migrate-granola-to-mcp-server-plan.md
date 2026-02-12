---
title: Migrate Granola Integration to MCP Server
type: feat
date: 2026-02-11
status: draft
---

# Migrate Granola Integration to MCP Server

## Overview

Migrate the Granola meeting notes integration from local cache file access to the official Granola MCP (Model Context Protocol) server. This modernizes the integration to use Granola's official API while maintaining all existing functionality (duplicate tracking, workspace filtering, agent automation).

**Current State:** Local file system integration reading `~/Library/Application Support/Granola/cache-v3.json`
**Target State:** HTTP-based integration using Granola MCP server at `https://mcp.granola.ai/mcp`
**Motivation:** Official Granola API support, better structure consistency, OAuth-based authentication

## Problem Statement

### Current Implementation Issues

1. **Unofficial Approach**: Reading Granola's internal cache file is undocumented and fragile
2. **Structure Mismatch**: Current code expects `panels['enhanced_notes']` and `panels['my_notes']` which don't exist in actual cache
3. **Platform Limitations**: Windows APPDATA path validation adds complexity
4. **No Real-time Updates**: Polling local cache misses updates until Granola syncs
5. **Authentication Complexity**: File permission checks, symlink validation, ownership verification all unnecessary with API

### Why MCP Server is Better

1. **Official Support**: Granola-maintained API with guaranteed structure
2. **OAuth Authentication**: Browser-based OAuth flow (no file system concerns)
3. **Consistent Data Format**: Documented API response structure
4. **Cross-Platform**: No platform-specific file paths
5. **Future-Proof**: Direct access to new Granola features (transcripts, enhanced search)

## Proposed Solution

Replace `GranolaIntegration` with an MCP client-based implementation that:
- Connects to Granola MCP server via HTTP
- Uses OAuth for authentication (browser flow)
- Fetches meetings using `list_meetings` and `get_meetings` tools
- Maintains existing duplicate tracking via `processed_granola_notes` table
- Preserves all agent integration points (polling, ActionableItem creation)

### High-Level Architecture

```
┌─────────────────────┐
│  AutonomousAgent    │
│   (poll cycle)      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ IntegrationManager  │
│ (multi-workspace)   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────┐
│  GranolaMCPIntegration          │
│  ┌──────────────────────────┐   │
│  │ HTTP Client              │   │
│  │ ↓                        │   │
│  │ https://mcp.granola.ai   │   │
│  │                          │   │
│  │ Tools:                   │   │
│  │ - list_meetings()        │   │
│  │ - get_meetings()         │   │
│  │ - query_granola_meetings()│   │
│  └──────────────────────────┘   │
│                                  │
│  OAuth Token Storage             │
│  (token.granola.json)            │
└──────────────────────────────────┘
           │
           ▼
┌─────────────────────┐
│ Database            │
│ (processed notes)   │
└─────────────────────┘
```

## Technical Approach

### Phase 1: MCP Client Infrastructure

**Goal:** Set up HTTP client and OAuth authentication for Granola MCP server

**Implementation Tasks:**

1. **Add HTTP Dependencies** (`pyproject.toml`)
   ```toml
   [project]
   dependencies = [
       "httpx>=0.27.0",  # Async HTTP client
       # ... existing deps
   ]
   ```

2. **Create OAuth Manager** (`src/integrations/granola_oauth.py`)
   ```python
   class GranolaOAuthManager:
       """OAuth manager for Granola MCP server authentication."""

       def __init__(self, token_path: Path):
           self.token_path = token_path
           self.mcp_server_url = "https://mcp.granola.ai/mcp"

       async def authenticate(self) -> str:
           """Run browser OAuth flow, return access token."""
           # Browser-based OAuth flow
           # Store token in token.granola.json with 0o600 permissions

       async def get_valid_token(self) -> str:
           """Get current token, refresh if needed."""
           # Load from token_path
           # Check expiration
           # Refresh if needed

       def _save_token(self, token_data: dict) -> None:
           """Atomically save token with restricted permissions."""
           # Follow GoogleOAuthManager pattern
           # os.O_WRONLY | os.O_CREAT | os.O_TRUNC
           # chmod 0o600
   ```

3. **Create MCP Client** (`src/integrations/mcp_client.py`)
   ```python
   class MCPClient:
       """HTTP client for Granola MCP server."""

       def __init__(self, server_url: str, token: str):
           self.server_url = server_url
           self.client = httpx.AsyncClient(
               base_url=server_url,
               headers={"Authorization": f"Bearer {token}"},
               timeout=30.0
           )

       async def list_meetings(
           self,
           limit: int = 100,
           workspace_id: str | None = None
       ) -> list[dict]:
           """Call list_meetings tool."""
           response = await self.client.post(
               "/tools/list_meetings",
               json={"limit": limit, "workspace_id": workspace_id}
           )
           response.raise_for_status()
           return response.json()["meetings"]

       async def get_meetings(
           self,
           query: str | None = None,
           meeting_ids: list[str] | None = None,
           limit: int = 100
       ) -> list[dict]:
           """Call get_meetings tool with content."""
           response = await self.client.post(
               "/tools/get_meetings",
               json={
                   "query": query,
                   "meeting_ids": meeting_ids,
                   "limit": limit
               }
           )
           response.raise_for_status()
           return response.json()["meetings"]
   ```

**Acceptance Criteria:**
- [x] `httpx` added to dependencies
- [x] `GranolaOAuthManager` implements browser OAuth flow
- [x] Tokens saved with 0o600 permissions in `~/.personal-assistant/token.granola.json`
- [x] `MCPClient` wraps MCP API with typed methods
- [x] Connection errors raise `PollError` (matches Gmail/Slack pattern)
- [x] Unit tests for OAuth manager (mock browser flow)
- [x] Unit tests for MCP client (mock HTTP responses)

---

### Phase 2: Replace GranolaIntegration

**Goal:** Rewrite `GranolaIntegration` to use MCP client instead of local cache

**Implementation Tasks:**

1. **Update Integration Class** (`src/integrations/granola_integration.py`)

   **Remove:**
   - `CACHE_PATHS` dictionary (no more file system access)
   - `_get_cache_path()` method
   - `_read_cache()` method
   - File permission/symlink checks in `authenticate()`
   - Windows APPDATA validation

   **Replace with:**
   ```python
   class GranolaIntegration(BaseIntegration):
       """Integration for Granola via official MCP server."""

       def __init__(self, config: dict[str, Any], account_id: str):
           super().__init__(config, account_id)
           self.workspace_id = config.get("workspace_id", "default")
           self.lookback_days = config.get("lookback_days", 7)

           # OAuth setup
           token_path = self._get_token_path()
           self.oauth_manager = GranolaOAuthManager(token_path)
           self.mcp_client: MCPClient | None = None

       def _get_token_path(self) -> Path:
           """Get token storage path."""
           return Path.home() / ".personal-assistant" / "token.granola.json"

       async def authenticate(self) -> bool:
           """Authenticate via OAuth and initialize MCP client."""
           try:
               token = await self.oauth_manager.get_valid_token()
               self.mcp_client = MCPClient(
                   "https://mcp.granola.ai/mcp",
                   token
               )

               # Test connection
               await self.mcp_client.list_meetings(limit=1)

               logger.info("Successfully authenticated with Granola MCP server")
               return True

           except Exception as e:
               raise AuthenticationError(f"Failed to authenticate with Granola: {e}")
   ```

2. **Update Poll Method**
   ```python
   async def poll(self) -> list[ActionableItem]:
       """Poll MCP server for new meetings."""
       try:
           if not self.mcp_client:
               await self.authenticate()

           # Calculate date filter
           cutoff_date = datetime.now(UTC) - timedelta(days=self.lookback_days)

           # Fetch meetings from MCP
           all_meetings = await self.mcp_client.list_meetings(
               limit=100,
               workspace_id=self.workspace_id if self.workspace_id != "all" else None
           )

           # Filter by date
           recent_meetings = [
               m for m in all_meetings
               if self._parse_date(m['date']) > cutoff_date
           ]

           # Filter out processed notes
           new_meetings = self._filter_new_notes(recent_meetings)

           # Fetch full content for new meetings
           meeting_ids = [m['id'] for m in new_meetings]
           if meeting_ids:
               meetings_with_content = await self.mcp_client.get_meetings(
                   meeting_ids=meeting_ids
               )
           else:
               meetings_with_content = []

           # Extract actionable items
           items = []
           for meeting in meetings_with_content:
               item = self._extract_actionable_item(meeting)
               if item:
                   items.append(item)

           self._update_last_poll()
           logger.info(
               f"Polled Granola MCP workspace '{self.workspace_id}': "
               f"{len(items)} actionable items from {len(new_meetings)} new meetings"
           )

           return items

       except httpx.HTTPError as e:
           raise PollError(f"HTTP error polling Granola MCP: {e}")
       except Exception as e:
           logger.error(f"Unexpected error polling Granola MCP: {e}", exc_info=True)
           raise PollError(f"Failed to poll Granola MCP: {e}")
   ```

3. **Update Content Extraction**
   ```python
   def _extract_actionable_item(self, meeting: dict) -> ActionableItem | None:
       """Extract actionable item from MCP meeting response.

       Expected MCP response structure:
       {
           "id": "note123",
           "title": "Team Standup",
           "date": "2026-02-11T10:00:00Z",
           "attendees": ["alice@example.com", "bob@example.com"],
           "content": "Meeting notes content...",  # From enhanced_notes
           "workspace_id": "workspace123"
       }
       """
       content = meeting.get('content', '')
       title = meeting.get('title', 'Untitled Meeting')

       # Add attendee context
       attendees = meeting.get('attendees', [])
       if attendees:
           attendee_str = ", ".join(attendees[:5])
           content += f"\n\n**Attendees:** {attendee_str}"

       return ActionableItem(
           type=ActionableItemType.DOCUMENT_REVIEW,
           title=f"Review meeting: {title}",
           description=content[:1000],
           source=IntegrationType.GRANOLA,
           source_reference=meeting['id'],
           due_date=None,
           priority="medium",
           tags=["meeting-notes", "granola"],
           metadata={
               "note_id": meeting['id'],
               "workspace_id": meeting.get('workspace_id'),
               "date": meeting.get('date'),
               "attendees": attendees,
           },
           account_id=self.account_id,
       )
   ```

4. **Keep Existing Methods**
   - `_filter_new_notes()` - Already uses database sessions correctly (P1 fixes)
   - `mark_note_processed()` - No changes needed (already fixed)
   - `_prosemirror_to_text()` - **REMOVE** (MCP returns plain text content)

**Acceptance Criteria:**
- [ ] `authenticate()` uses OAuth flow instead of file checks
- [ ] `poll()` calls MCP API instead of reading cache file
- [ ] `_extract_actionable_item()` works with MCP response structure
- [ ] Duplicate tracking still functional via `processed_granola_notes`
- [ ] All P1 fixes preserved (session lifecycle, race conditions, transactions)
- [ ] Error handling uses `PollError` consistently
- [ ] HTTP requests logged via `_log_http_request()` callback

---

### Phase 3: Configuration & Setup

**Goal:** Update configuration and add setup documentation

**Implementation Tasks:**

1. **Update Config Models** (`src/utils/config.py`)
   ```python
   class GranolaWorkspaceConfig(BaseModel):
       """Granola MCP workspace configuration."""

       workspace_id: str = Field(..., description="Workspace ID or 'all'")
       display_name: str = Field(default="", description="Friendly name")
       enabled: bool = Field(default=True)
       lookback_days: int = Field(default=7, ge=1, le=90)
       polling_interval_minutes: int = Field(default=15, ge=1, le=1440)

       # OAuth paths (optional - defaults to ~/.personal-assistant/)
       token_path: str | None = Field(
           default=None,
           description="Path to OAuth token file (default: ~/.personal-assistant/token.granola.json)"
       )
   ```

2. **Update Example Config** (`config.example.yaml`)
   ```yaml
   granola:
     enabled: true
     workspaces:
       - workspace_id: "all"  # Or specific workspace ID
         display_name: "All Workspaces"
         enabled: true
         lookback_days: 7
         polling_interval_minutes: 15
         # Optional: custom token path
         # token_path: "/custom/path/token.granola.json"
   ```

3. **Add CLI Authentication Command** (`src/cli.py`)
   ```python
   @accounts.command()
   @click.argument("account_type")
   @click.argument("account_id")
   def authenticate(account_type: str, account_id: str):
       """Authenticate an integration account (OAuth flow).

       Examples:
           pa accounts authenticate google personal
           pa accounts authenticate granola all
       """
       if account_type == "granola":
           # Run Granola OAuth flow
           from src.integrations.granola_oauth import GranolaOAuthManager

           token_path = Path.home() / ".personal-assistant" / "token.granola.json"
           oauth_manager = GranolaOAuthManager(token_path)

           console.print("[bold]Starting Granola OAuth authentication...[/bold]")
           console.print("A browser window will open for you to authorize access.")

           asyncio.run(oauth_manager.authenticate())

           console.print(f"[green]✓[/green] Successfully authenticated Granola account: {account_id}")
   ```

4. **Update README** (`README.md`)
   ```markdown
   #### Granola Meeting Notes Setup (MCP Server)

   The assistant integrates with Granola via the official MCP server for meeting notes.

   **Prerequisites:**
   - Granola desktop app installed
   - Granola account (free or paid tier)

   **Setup:**

   1. Configure Granola in `config.yaml`:
   ```yaml
   granola:
     enabled: true
     workspaces:
       - workspace_id: "all"
         display_name: "All Workspaces"
         enabled: true
         lookback_days: 7
         polling_interval_minutes: 15
   ```

   2. Authenticate via OAuth:
   ```bash
   pa accounts authenticate granola all
   ```

   This will:
   - Open your browser for Granola authorization
   - Store OAuth token in `~/.personal-assistant/token.granola.json`
   - Enable automatic token refresh

   3. Start the agent:
   ```bash
   pa agent start
   ```

   **Features:**
   - Automatically scans meeting notes for action items
   - Tracks processed notes to avoid duplicates
   - Supports multiple workspaces
   - OAuth-based authentication (no local cache access)

   **Limitations (Granola MCP Server):**
   - Free tier: Last 30 days of notes only
   - Rate limit: ~100 requests/minute
   - Shared notes not accessible via MCP
   - Transcripts require paid Granola tier
   ```

**Acceptance Criteria:**
- [ ] Config models support optional token_path
- [ ] `config.example.yaml` shows MCP configuration
- [ ] `pa accounts authenticate granola <id>` runs OAuth flow
- [ ] README documents MCP setup process
- [ ] README notes limitations (free tier 30 days, rate limits)

---

### Phase 4: Testing & Migration

**Goal:** Comprehensive testing and safe deployment

**Implementation Tasks:**

1. **Update Unit Tests** (`tests/unit/test_granola_integration.py`)

   **Remove Tests:**
   - `test_get_cache_path_*` (no more file system)
   - `test_authenticate_missing_file`
   - `test_authenticate_invalid_json`
   - `test_prosemirror_to_text_*` (no more ProseMirror parsing)

   **Add Tests:**
   ```python
   @pytest.fixture
   def mock_mcp_client():
       """Mock MCP client."""
       client = MagicMock()
       client.list_meetings = AsyncMock(return_value=[
           {
               "id": "note123",
               "title": "Team Standup",
               "date": "2026-02-10T10:00:00Z",
               "attendees": ["alice@example.com"],
               "workspace_id": "workspace1"
           }
       ])
       client.get_meetings = AsyncMock(return_value=[
           {
               "id": "note123",
               "title": "Team Standup",
               "date": "2026-02-10T10:00:00Z",
               "attendees": ["alice@example.com"],
               "content": "Discussed project timeline",
               "workspace_id": "workspace1"
           }
       ])
       return client

   @pytest.mark.asyncio
   async def test_authenticate_mcp_success(granola_config, mock_oauth_manager):
       """Test MCP authentication success."""
       mock_oauth_manager.get_valid_token = AsyncMock(return_value="test_token")

       integration = GranolaMCPIntegration(granola_config, "all")
       integration.oauth_manager = mock_oauth_manager

       result = await integration.authenticate()

       assert result is True
       assert integration.mcp_client is not None

   @pytest.mark.asyncio
   async def test_poll_fetches_from_mcp(granola_config, mock_mcp_client):
       """Test polling fetches meetings from MCP server."""
       integration = GranolaMCPIntegration(granola_config, "all")
       integration.mcp_client = mock_mcp_client

       items = await integration.poll()

       assert len(items) > 0
       assert items[0].title == "Review meeting: Team Standup"
       mock_mcp_client.list_meetings.assert_called_once()
       mock_mcp_client.get_meetings.assert_called_once()

   @pytest.mark.asyncio
   async def test_poll_filters_by_workspace(granola_config, mock_mcp_client):
       """Test workspace filtering."""
       granola_config['workspace_id'] = 'workspace1'
       integration = GranolaMCPIntegration(granola_config, "workspace1")
       integration.mcp_client = mock_mcp_client

       await integration.poll()

       # Verify workspace_id passed to API
       call_args = mock_mcp_client.list_meetings.call_args
       assert call_args.kwargs['workspace_id'] == 'workspace1'
   ```

2. **Add Integration Test** (optional but recommended)
   ```python
   @pytest.mark.integration
   @pytest.mark.asyncio
   async def test_full_mcp_flow():
       """Integration test with real MCP server (requires auth)."""
       # Skip if no token file exists
       token_path = Path.home() / ".personal-assistant" / "token.granola.json"
       if not token_path.exists():
           pytest.skip("No Granola OAuth token found")

       config = {"workspace_id": "all", "lookback_days": 7}
       integration = GranolaMCPIntegration(config, "all")

       # Real authentication
       assert await integration.authenticate()

       # Real poll
       items = await integration.poll()

       # Verify structure
       for item in items:
           assert item.source == IntegrationType.GRANOLA
           assert item.source_reference
           assert item.title.startswith("Review meeting:")
   ```

3. **Migration Testing Plan**

   **Pre-Deployment Checklist:**
   - [ ] All unit tests pass (14 tests adapted for MCP)
   - [ ] Manual OAuth flow tested (browser opens, token saved)
   - [ ] Manual poll tested with real Granola account
   - [ ] Verify duplicate tracking works (poll twice, second returns 0)
   - [ ] Check error handling (disconnect network, verify PollError)
   - [ ] Verify workspace filtering (create workspace-specific config)
   - [ ] Test token refresh (modify token to expire, verify auto-refresh)

   **Rollback Plan:**
   - Keep Git history of local cache implementation (tag it)
   - Document how to revert to local cache if MCP issues
   - Add config option to disable Granola entirely

**Acceptance Criteria:**
- [ ] All unit tests updated and passing
- [ ] OAuth flow tested manually with real browser
- [ ] Polling works with real Granola account
- [ ] Duplicate tracking verified (no re-processing)
- [ ] Error handling tested (network failures, invalid tokens)
- [ ] Documentation includes rollback instructions

---

## Alternative Approaches Considered

### Option 1: Hybrid Approach (MCP with Local Cache Fallback)

**Description:** Try MCP first, fall back to local cache if unavailable

**Pros:**
- Best user experience (works even if MCP server down)
- Smooth migration path
- No breaking changes

**Cons:**
- Double the code complexity
- Need to maintain both parsers
- Current cache parser is broken (panels structure mismatch)
- More testing burden

**Rejected Because:** User selected "MCP migration only" approach. Fixing the cache parser adds unnecessary work when MCP is the long-term solution.

### Option 2: Side-by-Side (Separate Integrations)

**Description:** Create `GranolaMCPIntegration` alongside existing `GranolaIntegration`

**Pros:**
- Safest migration (both available)
- Users choose which to use
- Can compare behavior side-by-side

**Cons:**
- Config confusion (which one to enable?)
- Duplicate enum values needed (GRANOLA vs GRANOLA_MCP)
- Eventually need to deprecate old one anyway

**Rejected Because:** Clean cutover is cleaner. Old implementation is broken anyway (structure mismatch), so keeping it provides no value.

### Option 3: Fix Cache Parsing First

**Description:** Fix the `panels` structure bug, THEN migrate to MCP

**Pros:**
- Validates current implementation works
- Useful if MCP migration fails
- Good fallback option

**Cons:**
- Extra work researching actual cache structure
- Need to handle both old and new Granola cache formats
- Delays MCP migration

**Rejected Because:** User selected "MCP migration only". Cache parsing becomes irrelevant once MCP is in place.

---

## Technical Considerations

### Security

**OAuth Token Storage:**
- Follow `GoogleOAuthManager` pattern for token security
- Atomic file creation with `os.O_WRONLY | os.O_CREAT | os.O_TRUNC`
- Restrict permissions to `0o600` (owner read/write only)
- Parent directory at `0o700` (owner access only)
- Store tokens at `~/.personal-assistant/token.granola.json`

**MCP Server Trust:**
- Using official Granola server at `https://mcp.granola.ai/mcp`
- HTTPS enforced (reject non-TLS connections)
- Token transmitted via `Authorization: Bearer` header
- Validate SSL certificates (no `verify=False`)

### Performance

**Rate Limiting:**
- Granola MCP: ~100 requests/minute average
- Current polling: Every 15 minutes = 4 requests/hour
- Each poll: 1x `list_meetings` + 1x `get_meetings` = 2 requests
- Total: 8 requests/hour << 100 requests/minute limit ✓

**Optimization Opportunities:**
- Cache `list_meetings` results in memory (avoid duplicate API calls)
- Batch `get_meetings` requests (fetch multiple meeting contents at once)
- Use ETags if MCP supports (avoid re-fetching unchanged data)

### Error Handling

**Network Failures:**
- Raise `PollError` on HTTP errors (matches Gmail/Slack pattern)
- Use `httpx.HTTPError` for transient network issues
- Retry with exponential backoff (httpx transport retry policy)
- Log full exceptions with `exc_info=True` for debugging

**Authentication Failures:**
- Detect expired tokens (401 Unauthorized)
- Auto-refresh if refresh token available
- Guide user to re-authenticate if refresh fails
- Clear, actionable error messages

**MCP Server Downtime:**
- Catch connection errors gracefully
- Return empty list (don't crash agent)
- Log warnings for monitoring
- Agent continues with other integrations

### Migration Path

**Breaking Changes:**
- Config structure stays same (no breaking changes)
- Authentication method changes (OAuth vs file system)
- Users must run `pa accounts authenticate granola <id>` once

**Backwards Compatibility:**
- Duplicate tracking database unchanged (still uses `processed_granola_notes`)
- `IntegrationManager` unchanged (same `IntegrationKey` pattern)
- Agent core unchanged (still receives `ActionableItem` objects)

**Deprecation:**
- Remove all local cache code in this PR (no hybrid approach)
- Update docs to reference MCP server only
- Tag current commit before merge (easy rollback if needed)

---

## Dependencies & Prerequisites

### Required

- [x] Granola account (free or paid tier)
- [x] Granola desktop app installed and synced
- [ ] `httpx` Python library (add to `pyproject.toml`)
- [ ] Browser for OAuth flow
- [ ] Network access to `https://mcp.granola.ai`

### Optional

- [ ] Paid Granola tier (for transcript access via `get_meeting_transcript`)
- [ ] Multiple workspace IDs (for workspace filtering)

### System Requirements

- **Python**: 3.11+ (already required)
- **OS**: Any (macOS/Linux/Windows)
- **Network**: HTTPS to `mcp.granola.ai` (port 443)
- **Storage**: ~1KB for OAuth token

---

## Success Metrics

### Functional

- [ ] OAuth authentication succeeds (browser flow completes)
- [ ] Meetings fetched from MCP server (verified in logs)
- [ ] Duplicate tracking works (no re-processing on second poll)
- [ ] Tasks created from meeting notes (LLM extracts action items)
- [ ] Workspace filtering works (only notes from specified workspace)

### Performance

- [ ] Poll completes in <5 seconds (2 API calls + database query)
- [ ] No rate limit errors (well under 100 req/min)
- [ ] Memory usage unchanged (~same as local cache approach)

### Quality

- [ ] All 14 unit tests pass
- [ ] Zero regressions in other integrations (Gmail/Slack unaffected)
- [ ] Documentation complete (README + inline comments)
- [ ] Error handling comprehensive (network, auth, parsing)

---

## Risk Analysis & Mitigation

### Risk 1: MCP Server Downtime

**Impact:** Medium
**Likelihood:** Low
**Mitigation:**
- Catch connection errors gracefully (don't crash agent)
- Return empty list on failure (agent continues)
- Log warnings for monitoring
- Consider adding health check endpoint call before polling

### Risk 2: OAuth Flow Complexity

**Impact:** Medium (user friction)
**Likelihood:** Medium
**Mitigation:**
- Clear CLI instructions (`pa accounts authenticate granola all`)
- Browser auto-opens (user doesn't manually copy URL)
- Error messages guide user on auth failures
- Validate token immediately after saving

### Risk 3: API Structure Changes

**Impact:** High (broken integration)
**Likelihood:** Low (official API should be stable)
**Mitigation:**
- Add response validation (Pydantic models for MCP responses)
- Log warnings on unexpected fields
- Comprehensive error messages on parsing failures
- Monitor Granola changelog for API updates

### Risk 4: Rate Limiting

**Impact:** Medium (missed notes)
**Likelihood:** Very Low (8 req/hr << 100 req/min)
**Mitigation:**
- Track API call count in logs
- Add exponential backoff on 429 responses
- Cache `list_meetings` results briefly (avoid redundant calls)
- Configurable polling interval (reduce frequency if needed)

### Risk 5: Free Tier Limitations

**Impact:** Low (user expectations)
**Likelihood:** High (many free tier users)
**Mitigation:**
- Document free tier limitations clearly (30 days only)
- Log info message when older notes skipped
- Suggest paid tier upgrade in docs
- Validate lookback_days ≤ 30 for free tier users (future enhancement)

---

## Documentation Plan

### User-Facing

- [x] README.md: MCP setup instructions (Phase 3)
- [x] config.example.yaml: MCP configuration example (Phase 3)
- [ ] Troubleshooting guide (common OAuth errors)
- [ ] Migration guide (if users had local cache setup)

### Developer-Facing

- [ ] Inline code comments (OAuth flow, MCP API calls)
- [ ] Architecture decision log (why MCP over local cache)
- [ ] API response examples (document MCP response structure)
- [ ] Testing guide (how to run integration tests)

### Updates Needed

- [ ] ARCHITECTURE.md: Add MCP integration pattern
- [ ] CLAUDE.md: Document MCP client usage patterns

---

## References & Research

### External References

- **Granola MCP Docs**: https://docs.granola.ai/help-center/sharing/integrations/mcp
- **MCP Protocol Spec**: https://spec.modelcontextprotocol.io/
- **httpx Documentation**: https://www.python-httpx.org/async/
- **OAuth 2.0 Spec**: https://oauth.net/2/

### Internal References

- **OAuth Pattern**: `src/integrations/oauth_utils.py:GoogleOAuthManager` (lines 15-120)
- **Integration Base**: `src/integrations/base.py:BaseIntegration` (lines 30-80)
- **Error Handling**: `src/integrations/gmail_integration.py:poll()` (lines 224-227)
- **Multi-Account**: `src/integrations/manager.py:IntegrationKey` (lines 22-30)
- **Database Sessions**: `src/models/database.py:get_db_session()` (lines 57-69)

### Related Work

- **Original Implementation**: `src/integrations/granola_integration.py` (current local cache)
- **P1 Fixes**: Commit `03c6030` - Security and session lifecycle fixes
- **Multi-Account PR**: PR #1 - Established multi-workspace pattern
- **Original Plan**: `docs/plans/2026-02-11-feat-granola-notes-integration-plan.md`

### Institutional Learnings

From P1 code review fixes (commit `03c6030`):
1. **Session Lifecycle**: Use `with get_db_session() as db:` for all database operations
2. **Race Conditions**: Check for existing records before insert, handle `IntegrityError`
3. **Transaction Safety**: Explicit rollback on errors, commit only after success
4. **Error Propagation**: Raise `PollError` on failures (don't silently return empty list)
5. **HTTP Logging**: Use `_log_http_request()` callback for observability

---

## Implementation Checklist

### Phase 1: MCP Client Infrastructure
- [ ] Add `httpx>=0.27.0` to `pyproject.toml`
- [ ] Create `src/integrations/granola_oauth.py`
  - [ ] `GranolaOAuthManager` class
  - [ ] Browser OAuth flow implementation
  - [ ] Token storage with 0o600 permissions
  - [ ] Token refresh logic
- [ ] Create `src/integrations/mcp_client.py`
  - [ ] `MCPClient` class
  - [ ] `list_meetings()` method
  - [ ] `get_meetings()` method
  - [ ] Error handling and retries
- [ ] Unit tests for OAuth manager
- [ ] Unit tests for MCP client

### Phase 2: Replace GranolaIntegration
- [ ] Update `src/integrations/granola_integration.py`
  - [ ] Remove `CACHE_PATHS` and file system code
  - [ ] Replace `authenticate()` with OAuth flow
  - [ ] Replace `poll()` with MCP API calls
  - [ ] Update `_extract_actionable_item()` for MCP structure
  - [ ] Remove `_prosemirror_to_text()` method
  - [ ] Keep `_filter_new_notes()` (unchanged)
  - [ ] Keep `mark_note_processed()` (unchanged)
- [ ] Update imports in `src/integrations/manager.py`
- [ ] Verify `IntegrationManager` initialization works

### Phase 3: Configuration & Setup
- [ ] Update `src/utils/config.py`
  - [ ] Add optional `token_path` to config model
- [ ] Update `config.example.yaml`
- [ ] Add CLI command `pa accounts authenticate granola <id>`
- [ ] Update `README.md`
  - [ ] Remove local cache instructions
  - [ ] Add MCP setup instructions
  - [ ] Document limitations (free tier, rate limits)

### Phase 4: Testing & Migration
- [ ] Update `tests/unit/test_granola_integration.py`
  - [ ] Remove file system tests
  - [ ] Add OAuth flow tests
  - [ ] Add MCP client tests
  - [ ] Update poll tests for API structure
- [ ] Manual testing
  - [ ] OAuth flow with real browser
  - [ ] Polling with real Granola account
  - [ ] Duplicate tracking verification
  - [ ] Workspace filtering test
- [ ] Run full test suite (462 tests)
- [ ] Update documentation

### Final
- [ ] Git tag current commit (rollback point)
- [ ] Create PR with comprehensive description
- [ ] Update PR #3 description (note MCP migration)
- [ ] Merge after approval

---

## Estimated Effort

- **Phase 1**: 4-6 hours (OAuth + MCP client)
- **Phase 2**: 3-4 hours (rewrite integration)
- **Phase 3**: 2-3 hours (config + CLI + docs)
- **Phase 4**: 3-4 hours (testing + migration)

**Total**: 12-17 hours

**Complexity**: Medium-High (OAuth flow, new API, comprehensive testing)

---

## Notes

- This replaces the local cache implementation entirely (no hybrid)
- All P1 security/performance fixes from commit `03c6030` are preserved
- Database schema unchanged (`processed_granola_notes` table still used)
- Multi-workspace pattern unchanged (same `IntegrationKey` approach)
- Breaking change: Users must run OAuth authentication once
- Cache structure bug becomes irrelevant (MCP provides consistent API)
