---
id: T0001
owner: "@claude"
needs: []
branch: task/T0001-reverse-mail-import
worktree: ./work/T0001-reverse-mail-import
status: completed
started: 2026-08-27
ended: 2026-08-27
---

# T0001: Reverse mail import (filesystem exports back into Gmail/Outlook/Thunderbird)

## Goals
Investigate reverse mail import from local filesystem exports back into Gmail, Outlook, or Thunderbird.
Determine feasibility, data loss risks, and existing tooling alternatives.

## Task Execution Steps

- [x] **[Read]**      Research Gmail API import methods and IMAP append capabilities.
- [x] **[Read]**      Compare mail-utils export data against restore requirements.
- [x] **[Read]**      Survey existing third-party restore tools across target ecosystems.
- [x] **[Decide]**    Determine write-scope safety requirements for Gmail API restoration.
- [x] **[Decided]**   Require explicit user approval before introducing any write scopes.
- [x] **[Doc]**       Author reverse import plan and document feasibility findings.
- [x] **[Verify]**    Review plan document for completeness and consistency.

## Execution Log

- [2026-08-27] **[Read]**
  Identified attachment bytes as key data-loss limitation and surveyed existing tools.

- [2026-08-27] **[Complete]**
  Published docs/reverse-import-plan.md and established follow-up task T0002 for implementation.
