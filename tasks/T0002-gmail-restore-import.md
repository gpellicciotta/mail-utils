---
id: T0002
owner: "@claude"
needs: []
branch: task/T0002-gmail-restore-import
worktree: ./work/T0002-gmail-restore-import
status: completed
started: 2026-08-27
ended: 2026-08-27
---

# T0002: Gmail store command (write mail-utils-indexed mail back into Gmail)

## Goals
Implement the store-in-gmail command to write mail-utils-indexed messages back into Gmail with preserved dates and labels.
Support dual sources from EML trees or local SQLite databases with idempotency and resumability.

## Task Execution Steps

- [x] **[Decide]**    Scope Gmail API write permissions narrowly to store-in-gmail command.
- [x] **[Decided]**   Request write-capable scopes only for store-in-gmail while preserving readonly default.
- [x] **[Implement]** Add scope override handling in auth and configuration modules.
- [x] **[Implement]** Implement Gmail API message import and label creation wrappers.
- [x] **[Implement]** Track stored message identifiers in database for idempotency.
- [x] **[Implement]** Implement store-in-gmail CLI command supporting EML tree and database sources.
- [x] **[Implement]** Add throttling, exponential backoff, and run tracking labels.
- [x] **[Verify]**    Verify mocked unit tests for dual source, filtering, and resumability.
- [x] **[Doc]**       Update documentation and CLI specifications for store-in-gmail.

## Execution Log

- [2026-08-27] **[Implement]**
  Implemented store-in-gmail command with dual sources, throttling, and persistent tracking labels.

- [2026-08-27] **[Verify]**
  Passed 151 unit tests with mocked Gmail API service.

- [2026-08-27] **[Complete]**
  Shipped store-in-gmail subcommand with complete documentation and unit test coverage.
