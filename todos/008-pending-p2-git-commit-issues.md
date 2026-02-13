---
status: pending
priority: p2
issue_id: "008"
tags: [code-review, git, commits, metadata]
dependencies: []
---

# Git Commit Issues: Missing Co-Authored-By and Placeholder Author

## Problem Statement

All 7 commits in this PR have three issues:
1. Missing `Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>` tag (CLAUDE.md requirement)
2. Placeholder author info: `Your Name <your-email@example.com>`
3. Large plan file committed that should be removed

**Why This Matters:** Violates project requirements (CLAUDE.md), makes git history unclear about authorship, and clutters repo with ephemeral planning artifacts.

## Findings

### Git History Analyzer
- **Severity:** MEDIUM-HIGH
- **Commits Affected:** All 7 (2825acd through 33d30b6)
- **Issues:**
  - No Co-Authored-By tags
  - Placeholder author on all commits
  - Plan file (828 lines) committed in docs commit

## Proposed Solutions

### Solution 1: Interactive Rebase to Fix All Issues (RECOMMENDED)
**Pros:**
- Fixes all issues at once
- Clean commit history
- Meets project requirements

**Cons:**
- Requires force push
- Rebases all commits

**Effort:** Medium (1 hour)
**Risk:** Low (feature branch only)

**Implementation:**
```bash
# 1. Fix author info for all commits
git rebase -i origin/main

# Mark all commits as 'edit', then for each:
git commit --amend --author="Mike D <miked@example.com>" \
  --message="$(git log --format=%B -n1)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

git rebase --continue

# 2. Remove plan file
git rebase -i origin/main
# Mark 33d30b6 (docs commit) for 'edit'
git reset HEAD^ docs/plans/2026-02-10-feat-add-external-document-links-to-tasks-plan.md
git commit --amend
git rebase --continue

# 3. Force push
git push -f origin feat/add-external-document-links
```

### Solution 2: Add Cleanup Commits
**Pros:**
- No rebase needed
- Preserves original commits

**Cons:**
- Doesn't fix existing commits
- History still has placeholder author

**Effort:** Small (15 minutes)
**Risk:** None

**Implementation:**
```bash
# Remove plan file
git rm docs/plans/2026-02-10-feat-add-external-document-links-to-tasks-plan.md
git commit -m "chore: remove implementation plan file

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

# Note: Can't fix existing commit authors without rebase
```

## Recommended Action

**Implement Solution 1** (interactive rebase) to fully comply with project requirements and clean up commit history.

## Technical Details

**Affected Commits:**
- 2825acd - feat(model): add document_links field
- d9a1bb9 - feat(service): add document_links support
- f5cafb8 - feat(api): add document_links support
- 3506110 - feat(cli): add document_links support
- 596d016 - feat(macos): add document_links support
- cb93ab5 - test: add comprehensive tests
- 33d30b6 - docs: add document_links documentation

**Plan File to Remove:**
- `docs/plans/2026-02-10-feat-add-external-document-links-to-tasks-plan.md` (27KB, 828 lines)

**Correct Commit Format:**
```
feat(scope): descriptive message

- Bullet point changes
- Another change

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

## Acceptance Criteria

- [ ] All commits have real author (not placeholder)
- [ ] All commits include Co-Authored-By tag
- [ ] Plan file removed from history
- [ ] Commit messages unchanged (only metadata fixed)
- [ ] Branch force-pushed successfully

## Work Log

### 2026-02-11 - Issue Identified
- Git history review found missing Co-Authored-By on all 7 commits
- Found placeholder author info
- Identified plan file in docs commit
- Prioritized as P2 (should fix before merge)

## Resources

- **PR:** #2
- **Project Requirements:** CLAUDE.md
- **Git Rebase Guide:** [Interactive Rebase](https://git-scm.com/book/en/v2/Git-Tools-Rewriting-History)
