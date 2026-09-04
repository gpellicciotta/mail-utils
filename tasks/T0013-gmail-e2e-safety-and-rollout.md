---
id: T0013
owner: "@claude"
needs: []
branch: task/T0013-gmail-e2e-safety-and-rollout
worktree: ./work/T0013-gmail-e2e-safety-and-rollout
status: completed
started: 2026-08-28
ended: 2026-08-28
---

# T0013: Safe end-to-end Gmail testing, with a path to production rollout

## Goals
Establish safe end-to-end testing procedures against disposable Gmail accounts before production rollout.
Validate roundtrip fidelity, error recovery, OAuth isolation, and documented operational runbooks.

## Task Execution Steps

- [x] **[Decide]**    Isolate test credentials from production configuration using dedicated worktree environments.
- [x] **[Decided]**   Run live account tests inside worktrees using local data directories and disposable test accounts.
- [x] **[Implement]** Add target account email verification logging to store-in-gmail before write execution.
- [x] **[Implement]** Build gmail-roundtrip-test script supporting seeding, comparing, and cleanup operations.
- [x] **[Implement]** Fix OAuth scope validation caching bug and MIME subject header folding whitespace bug.
- [x] **[Verify]**    Execute live end-to-end message sync and byte-level comparison against test Gmail account.
- [x] **[Doc]**       Document Gmail testing, isolation, and recovery playbooks in devops documentation.

## Execution Log

- [2026-08-28] **[Verify]**
  Executed live roundtrip test against katsan.pellicciotta@gmail.com, fixing scope validation and header folding bugs.

- [2026-08-28] **[Complete]**
  Delivered automated roundtrip tool, target account safety verification, and operational recovery playbook.
