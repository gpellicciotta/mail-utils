---
id: T0030
owner: "@antigravity"
needs: []
branch: task/T0030-plan-store-in-gmail-test-run
worktree: ./work/T0030-plan-store-in-gmail-test-run
status: completed
started: 2026-09-04
ended: 2026-09-04
---

# T0030: Plan store-in-gmail test run against disposable account

## Goals
Plan an end-to-end store-in-gmail test run against the disposable test Gmail account.
Define test scenarios covering kill and resume of long-running imports and curated edge cases from T0020.

## Task Execution Steps

- [x] **[Read]**      Audit store-in-gmail implementation, resume state persistence, and T0020 edge cases.
- [x] **[Decide]**    Determine test dataset composition covering all T0020 edge cases and interruption test protocol.
- [x] **[Implement]** Draft the store-in-gmail test plan document specifying setup, execution phases, and verification criteria.
- [x] **[Implement]** Enhance gmail-roundtrip-test script or test fixtures to generate the curated test dataset.
- [x] **[Verify]**    Verify test plan completeness and ensure all test suite checks pass.
- [x] **[Doc]**       Document the test plan in docs/specs/ and link from devops guides.

## Execution Log

- [2026-09-04] **[Read]**
  Audited store-in-gmail resume mechanism and identified all twelve T0020 edge-case message categories.

- [2026-09-04] **[Implement]**
  Created comprehensive test plan in docs/specs/gmail-store-test-plan.md covering round-trip fidelity, kill/resume, and teardown.
  Enhanced gmail-roundtrip-test.py with seed message generators for all T0020 edge cases.

- [2026-09-04] **[Verify]**
  Ran test suite and verified 271 tests passing with all linting and format checks passing.

- [2026-09-04] **[Doc]**
  Linked the test plan in docs/index.md and docs/devops.md.

- [2026-09-04] **[Complete]**
  Delivered store-in-gmail test plan specification and enhanced round-trip seeding generator.
