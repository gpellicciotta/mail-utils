---
id: T0024
owner: "@gio"
needs: []
branch: —
worktree: —
status: needs-review
started: 2026-09-02
ended: —
---

# T0024: Parallel multi-process import for very large PST archives

## Goals
Add an opt-in parallel multi-process import mode to import-pst for very large PST archives.
Evaluate necessity following single-process FTS5 indexing performance improvements.

## Task Execution Steps

- [x] **[Read]**      Profile import performance on large archive and assess single-process FTS5 optimization.
- [x] **[Doc]**       Document multi-process worker partition and merge architecture in docs/parallel-pst-import-plan.md.
- [ ] **[Decide]**    Determine whether parallel PST import should be built or remain backlogged.
- [ ] **[Implement]** Implement worker process entrypoint, partitioning logic, and SQLite database merge helpers.
- [ ] **[Implement]** Add --parallel option to import-pst CLI command.
- [ ] **[Verify]**    Verify byte-level parity between single-process and multi-process imports against test archives.

## Execution Log

- [2026-09-02] **[Read]**
  Single-process FTS5 bulk rebuild reduced import duration to 50.8 minutes, removing immediate performance urgency.

- [2026-09-02] **[Doc]**
  Authored full architecture design in docs/parallel-pst-import-plan.md pending decision on implementation.
