---
title: CLI task parse command not saving document links extracted by LLM
date: 2026-02-14
problem_type: bug
components:
  - cli
  - llm_service
  - task_service
severity: medium
tags:
  - document-links
  - task-parsing
  - llm-extraction
  - cli-bug
  - data-loss
related_issues:
  - "#2"
---

# CLI Task Parse Missing Document Links Parameter

## Symptoms

When using the CLI command `pa tasks parse "text with URL"`, document links (URLs) were being extracted by the LLM but not saved to the database. The task would be created successfully, but the `document_links` field remained empty in the resulting task record.

**Example:**
```bash
pa tasks parse "due Monday: complete the cloud team offsite request https://docs.google.com/document/d/1Pa-jDC3hUBqgphmhf5xjVVEQSCWLrhf2ymf1Bm_RDJc/edit?tab=t.0"
```

Result: Task created without the Google Docs link.

## Root Cause

The CLI implementation in `src/cli.py` at line 1747 was missing the `document_links` parameter when calling `TaskService.create_task()`.

The flow worked as follows:
1. `LLMService.extract_tasks_from_text()` correctly extracted document links from the input text
2. The extracted data included `document_links` in the `ExtractedTask` object
3. However, when the CLI code called `task_service.create_task()`, it only passed a subset of the extracted fields
4. The `document_links` parameter was omitted, causing the links to be silently dropped

This was a **data mapping gap** between the extraction layer and the persistence layer in the CLI code path. The API route (`src/api/routes/tasks.py`) did not have this issue as it correctly passed all fields.

## Investigation Steps

1. **Traced the execution path**: Followed the code from CLI entry point → `LLMService.extract_tasks_from_text()` → `TaskService.create_task()`

2. **Verified LLM extraction**: Confirmed that `LLMService` was correctly extracting document links and including them in the `ExtractedTask` object

3. **Compared API vs CLI paths**: Checked the API implementation in `src/api/routes/tasks.py` which correctly passed `document_links`

4. **Identified the gap**: Located the exact line in `src/cli.py:1747` where the `create_task()` call was missing the `document_links` parameter

5. **Reviewed test coverage**: Confirmed there were no existing tests for `pa tasks parse` that would have caught this regression

## Solution

Added the missing `document_links` parameter to the `TaskService.create_task()` call in `src/cli.py`:

```python
# Location: src/cli.py, line 1747
# In the 'tasks_parse' command handler

# Before (missing document_links):
task = service.create_task(
    title=extracted.title,
    description=extracted.description,
    priority=TaskPriority(extracted.priority),
    source=TaskSource.MANUAL,
    due_date=extracted.due_date,
    tags=extracted.tags,
    initiative_id=initiative_id,
)

# After (with document_links):
task = service.create_task(
    title=extracted.title,
    description=extracted.description,
    priority=TaskPriority(extracted.priority),
    source=TaskSource.MANUAL,
    due_date=extracted.due_date,
    tags=extracted.tags,
    document_links=extracted.document_links,  # ← Added this line
    initiative_id=initiative_id,
)
```

The fix is a single-line addition that ensures the document links extracted by the LLM are properly passed to the database layer.

## Verification

### Manual Testing
1. Ran the command: `pa tasks parse "Review PR https://github.com/user/repo/pull/123"`
2. Verified the task was created with the document link preserved
3. Confirmed the link was visible in the database and retrievable via API

### Automated Testing
Added a comprehensive regression test in `tests/unit/test_cli.py:848-907`:

```python
@patch("src.cli.init_db")
@patch("src.cli.load_config")
@patch("src.cli.get_config")
@patch("src.cli.get_db_session")
def test_tasks_parse_extracts_document_links(self, mock_session, mock_get_config, mock_load_config, mock_init_db, runner, mock_config, mock_task):
    """Test tasks parse extracts and passes document links to task creation."""
    mock_load_config.return_value = mock_config
    mock_get_config.return_value = mock_config

    mock_db = MagicMock()
    mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
    mock_session.return_value.__exit__ = MagicMock(return_value=False)

    from src.services.llm_service import ExtractedTask
    from datetime import datetime, timedelta

    # Create extracted task with document links
    doc_url = "https://docs.google.com/document/d/1Pa-jDC3hUBqgphmhf5xjVVEQSCWLrhf2ymf1Bm_RDJc/edit"
    extracted = ExtractedTask(
        title="Complete the cloud team offsite request",
        description="Review and finalize the offsite planning document",
        priority="medium",
        due_date=datetime.now() + timedelta(days=5),
        tags=["team", "offsite"],
        confidence=0.85,
        document_links=[doc_url],  # Include document link
    )

    with patch("src.cli.TaskService") as mock_service_class, \
         patch("src.cli.InitiativeService") as mock_initiative_class, \
         patch("src.services.llm_service.LLMService") as mock_llm_class:
        mock_service = MagicMock()
        mock_service.create_task.return_value = mock_task
        mock_service_class.return_value = mock_service

        # Mock initiative service (no active initiatives for this test)
        mock_initiative = MagicMock()
        mock_initiative.get_active_initiatives.return_value = []
        mock_initiative_class.return_value = mock_initiative

        # Mock LLM to return extracted task with document links
        mock_llm = MagicMock()
        mock_llm.extract_tasks_from_text = AsyncMock(return_value=[extracted])
        mock_llm_class.return_value = mock_llm

        # Use --yes to skip confirmation
        result = runner.invoke(cli, [
            "tasks", "parse",
            f"due Monday: complete the cloud team offsite request {doc_url}",
            "--yes"
        ])

        assert result.exit_code == 0
        assert "Created task" in result.output

        # CRITICAL: Verify document_links were passed to create_task
        mock_service.create_task.assert_called_once()
        call_kwargs = mock_service.create_task.call_args[1]
        assert "document_links" in call_kwargs, "document_links parameter is missing from create_task call"
        assert call_kwargs["document_links"] == [doc_url], f"Expected document_links={[doc_url]}, got {call_kwargs.get('document_links')}"
```

The test verifies that:
- The CLI command executes successfully
- The `create_task()` method is called with the `document_links` parameter
- The parameter value matches the extracted URL

This test prevents future regressions where document links might be dropped during the CLI → service layer handoff.

## Related Documentation

### Existing Documentation

**1. Comprehensive Security Review for document_links Feature**
- **File:** `docs/solutions/security-issues/csv-injection-and-validation-comprehensive-fixes-document-links.md`
- **Description:** Complete problem-solving documentation covering the multi-agent code review that identified 6 critical (P1) security issues in PR #2. Includes root cause analysis, detailed fixes for CSV injection, URL validation, command injection, agent LLM extraction gaps, and missing API tests.

**2. Prevention Strategies Document**
- **File:** `docs/PREVENTION_STRATEGIES.md`
- **Description:** Comprehensive guide with actionable checklists to prevent similar issues in future development. Covers security review requirements, testing requirements, and best practices for data storage patterns and URL validation.

**3. PR #2: External Document Links Feature**
- **Commit:** `35d2be5` (`feat: Add external document links to tasks (#2)`)
- **Description:** Original feature implementation adding document_links field to tasks, including all layers (model, service, API, CLI, macOS). Later augmented with comprehensive security fixes.

**4. Feature Planning Document**
- **File:** `docs/plans/2026-02-10-feat-add-external-document-links-to-tasks-plan.md`
- **Description:** Original architectural plan for document_links feature showing 7 implementation phases, alternative approaches considered, acceptance criteria, and risk analysis.

**5. Recent Fix**
- **Commit:** `eac1a6c` (`fix: Pass document_links from parse command to task creation`)
- **Branch:** `fix/parse-document-links`
- **Date:** 2026-02-13

### Cross-References

#### Similar Issues Found in Codebase

**Code Review identified the same bug in additional locations:**

1. **Voice Service** (`src/services/voice_service.py`)
   - Line 304: Missing `document_links=task_data.document_links`
   - Line 362: Missing `document_links=task_data.document_links` (duplicate code)
   - **Status:** Not yet fixed (follow-up needed)

2. **Integration Manager** (`src/integrations/manager.py`)
   - Line 350: `actionable_item_to_task_params()` doesn't include `document_links`
   - **Status:** Not yet fixed (follow-up needed)

3. **Agent Core** (`src/agent/core.py`)
   - Lines 728-733: Correctly includes `document_links=extracted.document_links or []`
   - **Status:** Already correct (implemented properly in original PR #2)

#### Testing Pattern for Prevention

- **Location:** `tests/unit/test_cli.py`
- **Pattern:** Added comprehensive test `test_tasks_parse_extracts_document_links()` that verifies parameter passing
- **Prevention:** This test would catch similar bugs if new fields are added in the future

## Prevention Strategies

### 1. Centralized Task Creation Function

Create a single, canonical function that all code paths must use to convert `ExtractedTask` → `Task`. This eliminates the pattern of scattered conversion logic across multiple files.

**Implementation:**
```python
# In TaskService
def create_task_from_extracted(self, extracted: ExtractedTask, source: TaskSource, ...) -> Task:
    return self.create_task(
        title=extracted.title,
        description=extracted.description,
        priority=extracted.priority,
        due_date=extracted.due_date,
        tags=extracted.tags,
        document_links=extracted.document_links,  # All fields in one place
        source=source,
        ...
    )

# All consumers call this
task = task_service.create_task_from_extracted(extracted_task, TaskSource.CLI)
```

**Benefit:** New fields only need updating in ONE place instead of 5+ scattered locations.

### 2. Automated Test Coverage for All Consumption Sites

Add integration tests that exercise every code path that creates tasks from `ExtractedTask`:
- `tests/integration/test_task_creation_paths.py`
- Test CLI parse, voice input, Gmail integration, Slack integration, agent extraction
- Each test verifies that all `ExtractedTask` fields (including new ones) are properly preserved
- Tests fail immediately when a new field is added but not handled

### 3. Static Analysis with Type Checking

Leverage Python's type system more strictly:
- Use Pydantic models instead of plain dataclasses for `ExtractedTask`
- Enable strict mypy checking in CI/CD
- Use `model_dump()` patterns that automatically fail when fields are missing

### 4. Code Review Checklist Integration

Add automated checks to pull request templates:
- PR template includes: "If modifying ExtractedTask, have you updated ALL consumption sites?"
- GitHub Actions workflow that searches for `ExtractedTask(` patterns
- Required checklist item before merge approval

## Best Practices

### When Adding Fields to ExtractedTask

**REQUIRED checklist locations to update:**

1. **LLM Service** (`src/services/llm_service.py`):
   - Add field to `ExtractedTask` dataclass
   - Update prompt templates to extract new field
   - Update JSON parsing logic

2. **ALL Task Creation Sites:**
   - [ ] `src/cli.py` - `tasks_parse` command (~line 1747)
   - [ ] `src/services/voice_service.py` - `create_task_from_voice()` (~line 304)
   - [ ] `src/services/voice_service.py` - Fallback path (~line 362)
   - [ ] `src/integrations/manager.py` - `actionable_item_to_task_params()` (~line 350)
   - [ ] `src/agent/core.py` - Agent task creation (~line 733)

3. **Database & API (if persisted):**
   - [ ] Add field to `Task` model in `src/models/task.py`
   - [ ] Create Alembic migration
   - [ ] Update Pydantic schemas in `src/api/schemas.py`

4. **Testing:**
   - [ ] Add unit test in `tests/unit/test_llm_service.py`
   - [ ] Add integration test for each consumption site
   - [ ] Run full test suite: `pytest`
   - [ ] Manual smoke test: `pa tasks parse "Test text with new field"`

### Code Patterns

**GOOD - Centralized:**
```python
# All consumers use the same factory method
task = task_service.create_task_from_extracted(extracted_task, TaskSource.CLI)
```

**BAD - Scattered:**
```python
# Different call sites manually map fields (easy to miss new ones)
task = service.create_task(title=extracted.title, description=extracted.description, ...)
```

## Future Improvements

### 1. Task Factory Pattern (High Priority)

Create `src/services/task_factory.py` with centralized conversion logic:

```python
class TaskFactory:
    """Centralized task creation from all sources."""

    @staticmethod
    def from_extracted_task(
        extracted: ExtractedTask,
        source: TaskSource,
        account_id: str | None = None,
        initiative_id: int | None = None
    ) -> Task:
        """Single source of truth for ExtractedTask → Task conversion."""
        return Task(
            title=extracted.title,
            description=extracted.description,
            priority=extracted.priority,
            due_date=extracted.due_date,
            tags=",".join(extracted.tags) if extracted.tags else None,
            document_links=extracted.document_links,
            source=source,
            account_id=account_id,
            initiative_id=initiative_id,
        )
```

### 2. Use Pydantic Models

Replace dataclasses with Pydantic models for automatic validation:

```python
from pydantic import BaseModel, Field

class ExtractedTask(BaseModel):
    """Pydantic model ensures validation and easy dict conversion."""
    title: str
    description: str | None = None
    priority: str = "medium"
    due_date: str | None = None
    tags: list[str] = Field(default_factory=list)
    document_links: list[str] = Field(default_factory=list)

    def to_task(self, source: TaskSource, **kwargs) -> Task:
        """Built-in conversion method."""
        return Task(
            **self.model_dump(exclude_none=True),
            source=source,
            **kwargs
        )
```

### 3. Pre-Commit Hooks

Add validation that all `ExtractedTask` consumers include required fields:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: check-extractedtask-consumers
        name: Check ExtractedTask consumers
        entry: python scripts/check_extractedtask_coverage.py
        language: python
```

### 4. Integration Test Matrix

Create comprehensive test matrix for all task creation paths:

```python
# tests/integration/test_task_creation_matrix.py
TASK_SOURCES = [
    ("cli_parse", lambda: run_cli_parse("Sample task")),
    ("voice_input", lambda: create_voice_task(audio_file)),
    ("gmail_integration", lambda: process_gmail_message(email)),
    ("slack_integration", lambda: process_slack_message(msg)),
    ("agent_extraction", lambda: agent.extract_task(text)),
]

@pytest.mark.parametrize("source_name,creator_func", TASK_SOURCES)
def test_all_extracted_fields_preserved(source_name, creator_func):
    """Verify all ExtractedTask fields are preserved regardless of source."""
    task = creator_func()
    assert task.document_links is not None  # Verify field exists
```

## Key Learnings

1. **Silent Data Loss**: When dataclass fields have defaults, Python doesn't require them to be passed. This can cause silent data loss that only surfaces in user reports.

2. **Scattered Logic Anti-Pattern**: Having the same conversion logic (ExtractedTask → Task) in multiple files makes it easy to miss updates when adding new fields.

3. **Test Coverage Gaps**: The bug existed because there were no integration tests exercising the full CLI parse → task creation flow with document links.

4. **Defensive Programming**: Consider using Pydantic models with strict validation instead of dataclasses for data transfer objects that cross architectural boundaries.

## Common Bug Pattern

**Pattern Name:** "Missing Parameter in Scattered Conversion Logic"

**Manifestation:**
- A dataclass gains a new field
- Most conversion sites are updated
- One or two sites are missed (often CLI or voice input)
- Code runs without errors (no type checking catches it)
- Data is silently dropped

**Detection:**
- User reports missing data
- Manual testing reveals the gap
- No automated test caught it

**Prevention:**
- Centralize conversion logic (Factory pattern)
- Add integration tests for all data paths
- Use Pydantic models with strict validation
- Enable mypy strict mode
- Add pre-commit hooks

## Impact Assessment

- **Severity:** Medium - Data loss, but not catastrophic
- **Scope:** CLI `tasks parse` command only (API, agent, and other paths unaffected)
- **User Impact:** Users who parsed tasks with URLs lost those links
- **Data Recovery:** Not possible - lost links not stored anywhere
- **Prevention:** Comprehensive test added, similar bugs identified in code review

## Action Items

### Immediate (Completed)
- ✅ Fix CLI parse command (commit `eac1a6c`)
- ✅ Add regression test (`test_tasks_parse_extracts_document_links`)
- ✅ Document the solution (this file)

### Follow-Up (TODO)
- [ ] Fix voice service (2 locations missing `document_links`)
- [ ] Fix integration manager (`actionable_item_to_task_params`)
- [ ] Refactor to use centralized `TaskFactory.from_extracted_task()`
- [ ] Add integration test matrix for all task creation paths
- [ ] Convert `ExtractedTask` from dataclass to Pydantic model
- [ ] Add pre-commit hook for field coverage validation

### Long-Term Improvements
- [ ] Implement full Factory pattern for task creation
- [ ] Add comprehensive integration tests for all data flows
- [ ] Enable strict mypy checking in CI/CD
- [ ] Document architectural guidelines for cross-layer data transfer
