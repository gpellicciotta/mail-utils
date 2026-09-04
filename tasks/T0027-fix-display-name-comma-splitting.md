---
id: T0027
owner: "@claude"
needs: []
branch: task/T0027-fix-display-name-comma-splitting
worktree: ./work/T0027-fix-display-name-comma-splitting
status: completed
started: 2026-09-02
ended: 2026-09-02
---

# T0027: Fix unquoted comma in a display name splitting one recipient into bogus extra rows

## Goals
Fix address splitting bug where unquoted commas in contact display names split single recipients into multiple rows.
Ensure RFC 5322 compliant quoting for formatted address strings and transport headers.

## Task Execution Steps

- [x] **[Read]**      Investigate address parsing fragmentation in getaddresses when encountering unquoted commas.
- [x] **[Implement]** Implement quote_unquoted_comma_display_names tokenizer in mime_headers module.
- [x] **[Implement]** Apply display name quoting in address formatting helpers across Outlook and Thunderbird parsers.
- [x] **[Verify]**    Verify unit tests in test_mime_headers.py and test_pst_integration.py with real recipient fixtures.
- [x] **[Doc]**       Update task documentation and record resolution in execution logs.

## Execution Log

- [2026-09-02] **[Verify]**
  Passed 238 unit tests and confirmed correct roundtrip formatting for complex multi-recipient display names.

- [2026-09-02] **[Complete]**
  Shipped display name comma quoting across address formatting and parser pipelines.
