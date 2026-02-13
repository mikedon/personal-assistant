---
status: pending
priority: p1
issue_id: "005"
tags: [code-review, agent-native, feature-gap, llm]
dependencies: []
---

# Agent Cannot Extract Document Links from Emails/Slack

## Problem Statement

The autonomous agent cannot automatically extract document URLs from emails or Slack messages and associate them with tasks. This is a critical feature gap because email threads and Slack messages frequently contain Google Docs links, Notion pages, Confluence links, etc., and the agent creates tasks from these sources but loses valuable document context.

**Why This Matters:** This defeats the purpose of the document_links feature for autonomous operation. Users must manually add links that the agent could have extracted automatically.

## Findings

### Agent-Native Review
- **Severity:** HIGH
- **Component:** Agent + Integration + LLM
- **Evidence:**
  1. `src/agent/core.py` (lines 625-685): `_create_task_from_extracted()` doesn't pass `document_links` parameter
  2. `src/services/llm_service.py` (lines 35-45): `ExtractedTask` dataclass missing `document_links` field
  3. `src/integrations/base.py` (lines 32-46): `ActionableItem` missing `document_links` field

**Example Workflow (Broken):**
```python
# Email: "Please review this doc: https://docs.google.com/document/d/abc123"
# Agent extracts: {"title": "Review doc", "description": "Please review..."}
# Document link is LOST - not extracted or stored
```

## Proposed Solutions

### Solution 1: Full LLM Extraction Pipeline (RECOMMENDED)
**Pros:**
- Fully autonomous document link extraction
- Works for all integrations (Gmail, Slack, future)
- LLM can understand context ("the proposal" → extract URL)
- Natural language → structured data

**Cons:**
- Requires LLM prompt changes
- Additional LLM tokens per extraction
- May extract irrelevant URLs (needs confidence threshold)

**Effort:** Medium (3-4 hours)
**Risk:** Low

**Implementation:**

**Step 1: Update ExtractedTask dataclass**
```python
# src/services/llm_service.py
@dataclass
class ExtractedTask:
    title: str
    description: str | None = None
    priority: str = "medium"
    due_date: datetime | None = None
    tags: list[str] | None = None
    confidence: float = 0.5
    suggested_initiative_id: int | None = None
    document_links: list[str] | None = None  # ADD THIS
```

**Step 2: Update LLM prompt**
```python
# src/services/llm_service.py:extract_tasks_from_text()
system_prompt = """...
Extract:
- title: Brief task title
- description: Full context
- priority: low/medium/high/critical
- due_date: ISO format if mentioned
- tags: Relevant keywords
- document_links: Array of URLs found in text (Google Docs, Notion, Confluence, GitHub, Jira, etc.)

Example:
{
  "title": "Review PR #123",
  "document_links": ["https://github.com/org/repo/pull/123"],
  "tags": ["code-review"]
}
"""
```

**Step 3: Update ActionableItem**
```python
# src/integrations/base.py
@dataclass
class ActionableItem:
    type: ActionableItemType
    title: str
    description: str | None = None
    source: IntegrationType
    source_reference: str | None = None
    document_links: list[str] | None = None  # ADD THIS
```

**Step 4: Update agent task creation**
```python
# src/agent/core.py:_create_task_from_extracted()
task = task_service.create_task(
    title=extracted.title,
    description=extracted.description,
    priority=priority,
    source=source,
    source_reference=item.source_reference,
    due_date=extracted.due_date,
    tags=extracted.tags or [],
    document_links=extracted.document_links or [],  # ADD THIS
    initiative_id=extracted.suggested_initiative_id,
)
```

### Solution 2: Simple URL Regex Extraction
**Pros:**
- Fast, no LLM needed
- Low latency
- No additional API costs

**Cons:**
- Extracts ALL URLs (including signatures, footers, ads)
- No context understanding
- May extract irrelevant links

**Effort:** Small (1 hour)
**Risk:** Medium (noise from irrelevant URLs)

**Implementation:**
```python
import re

URL_PATTERN = r'https?://(?:docs\.google\.com|notion\.so|github\.com|confluence\.[a-z]+)[^\s<>"]+'

def extract_urls(text: str) -> list[str]:
    """Extract common document URLs from text."""
    return re.findall(URL_PATTERN, text)

# In agent:
extracted_urls = extract_urls(item.description or "")
task = task_service.create_task(..., document_links=extracted_urls)
```

### Solution 3: Hybrid Approach
**Pros:**
- Best of both worlds
- Fast regex pre-filtering, LLM for relevance
- Reduces false positives

**Cons:**
- More complex
- Still requires LLM changes

**Effort:** Medium (4 hours)
**Risk:** Low

## Recommended Action

**Implement Solution 1 (Full LLM Extraction)**. The LLM is already being called for task extraction, so adding document links to the output is natural and leverages existing infrastructure. The marginal token cost is minimal.

## Technical Details

**Affected Files:**
- `src/services/llm_service.py` - Update ExtractedTask, LLM prompt
- `src/integrations/base.py` - Update ActionableItem
- `src/agent/core.py` - Pass document_links to create_task
- `tests/integration/` - Add agent extraction tests

**LLM Prompt Example:**
```python
user_prompt = f"""Extract tasks from this {source} message:

{text}

For each task, extract any relevant document URLs mentioned (Google Docs, Notion, GitHub, Confluence, Jira, etc.).

Return JSON array of tasks with document_links field."""
```

**Expected LLM Output:**
```json
[
  {
    "title": "Review quarterly plan",
    "description": "Please review and provide feedback",
    "document_links": [
      "https://docs.google.com/document/d/abc123",
      "https://docs.google.com/spreadsheets/d/xyz789"
    ],
    "tags": ["planning", "review"],
    "confidence": 0.9
  }
]
```

## Acceptance Criteria

- [ ] Agent extracts document links from email bodies
- [ ] Agent extracts document links from Slack messages
- [ ] ExtractedTask includes document_links field
- [ ] ActionableItem includes document_links field
- [ ] Agent passes document_links to task creation
- [ ] Integration test: Email with Google Docs link → task with link
- [ ] Integration test: Slack message with GitHub PR → task with link
- [ ] LLM extracts only relevant URLs (not footer/signature links)
- [ ] Agent log shows extracted links for transparency

## Work Log

### 2026-02-11 - Issue Identified
- Agent-native review found critical gap in autonomous extraction
- Confirmed LLM prompt doesn't include document_links
- Traced through agent pipeline: ActionableItem → ExtractedTask → create_task
- All missing document_links field
- Prioritized as P1 (core feature gap for autonomous operation)

## Resources

- **PR:** #2 - feat: Add external document links to tasks
- **Agent Architecture:** `src/agent/core.py`
- **LLM Service:** `src/services/llm_service.py`
- **Integration Base:** `src/integrations/base.py`
- **Example Email:** "Please review https://docs.google.com/document/d/abc123"
- **Example Slack:** "Check out the design: https://figma.com/file/xyz"
