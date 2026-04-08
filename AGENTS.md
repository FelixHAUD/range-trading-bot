# Agent Roles — Range Trading Bot

This document defines the responsibilities, constraints, and handoff protocol for each agent role in the build system.
All agents must read `CLAUDE.md` before touching any file.

---

## Agent Roles

### Builder
**Trigger:** A task file moves from `tasks/backlog/` to `tasks/in-progress/`.

**Responsibilities:**
- Read the task file in full before writing a single line of code
- Read `CLAUDE.md` and the relevant `<package>/CLAUDE.md`
- Implement only what the task specifies — no extra features, no refactoring of adjacent code
- Write the implementation and its unit tests in the same commit
- Update the package `CLAUDE.md` with any decisions or discoveries made during implementation
- Never hardcode credentials; never act on `is_closed=False` candles; never `import *`
- When done, move the task file to `tasks/ready-for-test/`

**Must NOT:**
- Merge to main
- Touch files outside the task's declared scope
- Leave tests unwritten

---

### Tester
**Trigger:** A task file appears in `tasks/ready-for-test/`.

**Responsibilities:**
- Run `python -m pytest tests/ -k "not integration" -v`
- If **all tests pass**: move the task file to `tasks/ready-for-review/`, create a review file in `reviews/` using the template below
- If **any test fails**: move the task file back to `tasks/in-progress/`, append a `## Test Failures` section to the task file with the full pytest output
- Never modify implementation files

**Review file naming:** `reviews/REVIEW-<NNN>-<slug>.md`

---

### Reviewer
**Trigger:** A review file appears in `reviews/`.

**Responsibilities:**
- Read the implementation files listed in the review
- Verify against the relevant section of `ARCHITECTURE.md`
- Check: no raw exchange data outside `feeds/`, no hardcoded credentials, `is_closed` guard present where required, type hints present, no `import *`
- Append a `## Review Decision` section: `APPROVED` or `CHANGES REQUESTED` with specific line-level feedback
- On `APPROVED`: move the task file to `tasks/approved/`
- On `CHANGES REQUESTED`: move it back to `tasks/in-progress/`

**Must NOT:**
- Approve without checking every item on the checklist
- Merge to main

---

### Merge
**Trigger:** A task file moves to `tasks/approved/`.

**Responsibilities:**
- Confirm the feature branch tests still pass on HEAD
- `git merge --no-ff feature/<branch>` into main
- `git push`
- `git branch -d feature/<branch>` (local) + `git push origin --delete feature/<branch>`
- Move the task file to `tasks/done/`
- Update `tasks/TASKS.md` status to `DONE`
- Unblock any tasks whose `depends_on` list is now fully satisfied

**Must NOT:**
- Fast-forward merge
- Delete the branch before confirming tests pass

---

## Task File Template

```markdown
---
id: TASK-NNN
title: <short title>
branch: feature/<branch-name>
status: backlog | in-progress | ready-for-test | ready-for-review | approved | done
depends_on: []   # list of TASK-IDs that must be DONE first
files:
  - path/to/impl.py
  - tests/test_impl.py
---

## Goal
<What this task must achieve, in plain language.>

## Acceptance criteria
- [ ] All unit tests pass
- [ ] No raw exchange data leaves feeds/
- [ ] is_closed guard in place (if strategy layer)
- [ ] No hardcoded credentials
- [ ] Package CLAUDE.md updated with any decisions

## Implementation notes
<Extracted from ARCHITECTURE.md — the exact spec for this module.>

## Test failures
<!-- Tester appends here on failure -->

## Review decision
<!-- Reviewer appends here -->
```

---

## Handoff Flow

```
backlog → in-progress → ready-for-test → ready-for-review → approved → done
              ↑                 │
              └─── (fail) ──────┘
```

Each agent moves the task file and only the task file to signal the next agent.

---

## Directory Layout

```
tasks/
  TASKS.md          ← master status board
  backlog/          ← not yet started
  in-progress/      ← builder working on it
  ready-for-test/   ← tester picks up
  ready-for-review/ ← reviewer picks up
  approved/         ← merge agent picks up
  done/             ← archived
reviews/
  REVIEW-NNN-slug.md
```
