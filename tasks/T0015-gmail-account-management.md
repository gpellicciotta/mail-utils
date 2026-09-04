---
id: T0015
owner: "@claude"
needs: []
branch: task/T0015-gmail-account-management
worktree: ./work/T0015-gmail-account-management
status: completed
started: 2026-08-28
ended: 2026-08-28
---

# T0015: Named Gmail account files and a `prepare-gmail-account` command

## Goals
Provide named Gmail account configuration files and a dedicated prepare-gmail-account command.
Decouple account authentication from data storage and switch --db to directory-scoped database and attachments.

## Task Execution Steps

- [x] **[Decide]**    Decouple account authentication tokens from database and attachment storage locations.
- [x] **[Decided]**   Store named account tokens under data/<name>-account.json and scope data directories under --db.
- [x] **[Implement]** Add account path and database directory resolution helpers in config module.
- [x] **[Implement]** Implement prepare-gmail-account CLI command with scope selection options.
- [x] **[Implement]** Thread --account flag through Gmail import and store-in-gmail subcommands.
- [x] **[Implement]** Configure attachment store directory dynamically based on selected database path.
- [x] **[Verify]**    Verify unit and integration tests across configuration, authentication, and CLI commands.
- [x] **[Doc]**       Document multi-account workflow and setup procedures in README and devops guide.

## Execution Log

- [2026-08-28] **[Implement]**
  Implemented prepare-gmail-account subcommand, --account flag routing, and directory-based --db scoping.

- [2026-08-28] **[Verify]**
  Passed 187 unit and integration tests with mocked OAuth services and directory isolation checks.

- [2026-08-28] **[Complete]**
  Shipped named Gmail account management and directory-scoped database storage layout.
