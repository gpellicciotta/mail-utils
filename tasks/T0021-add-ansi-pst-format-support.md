---
id: T0021
owner: "@claude"
needs: []
branch: task/T0021-add-ansi-pst-format-support
worktree: ./work/T0021-add-ansi-pst-format-support
status: completed
started: 2026-09-02
ended: 2026-09-02
---

# T0021: Add ANSI PST format support to the Outlook parser

## Goals
Extend Outlook PST parser to support legacy 32-bit ANSI PST files alongside Unicode PST files.
Ensure correct header, b-tree page, and codepage string decoding without regressions on Unicode archives.

## Task Execution Steps

- [x] **[Read]**      Review MS-PST specifications for structural differences between ANSI and Unicode PST layouts.
- [x] **[Implement]** Implement ANSI header and 32-bit b-tree page parsing in ndb module.
- [x] **[Implement]** Support ANSI entry widths across BTENTRY, BBTENTRY, NBTENTRY, and subnode blocks.
- [x] **[Implement]** Refactor table context decoding in ltp module to return property types for codepage strings.
- [x] **[Verify]**    Verify unit tests in test_pst_ndb.py and run end-to-end import against real ANSI archive.
- [x] **[Doc]**       Update task documentation and record ANSI PST compatibility in execution logs.

## Execution Log

- [2026-09-02] **[Verify]**
  Passed 251 unit tests and successfully imported 675 messages from real ANSI archive anubex-friends-email.pst.

- [2026-09-02] **[Complete]**
  Shipped 32-bit ANSI PST support across Outlook NDB and LTP parser layers.
