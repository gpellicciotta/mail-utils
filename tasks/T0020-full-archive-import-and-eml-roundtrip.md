---
id: T0020
owner: "@claude"
needs: []
branch: task/T0020-full-archive-import-and-eml-roundtrip
worktree: ./work/T0020-full-archive-import-and-eml-roundtrip
status: completed
started: 2026-08-31
ended: 2026-09-04
---

# T0020: Import all real archives into work-mail and prove a full EML round trip

## Goals
Import all four real archive files into a combined work-mail database with attachments and recursive nesting.
Export to Markdown and EML formats and prove a lossless roundtrip re-import via import-eml and local-roundtrip-test.

## Task Execution Steps

- [x] **[Decide]**    Choose strategy for validating lossless roundtrip of EML exports.
- [x] **[Decided]**   Implement import-eml CLI command and local-roundtrip-test comparison script using exact identifiers.
- [x] **[Implement]** Build import-eml subcommand to parse EML trees into SQLite databases.
- [x] **[Implement]** Add local-roundtrip-test script comparing messages, addresses, and content-addressed attachment bytes.
- [x] **[Implement]** Fix FTS5 index maintenance performance bottleneck for massive multi-gigabyte PST imports.
- [x] **[Implement]** Fix MIME header encoding, transport header linebreaks, and unquoted display name parsing bugs.
- [x] **[Verify]**    Import 187,353 messages across all four archives and verify zero body or attachment differences.
- [x] **[Doc]**       Document import-eml subcommand in README, CLI specifications, and CHANGELOG.

## Execution Log

- [2026-09-04] **[Verify]**
  Validated 187,353 messages with zero body or attachment differences, resolving eight distinct parsing issues.

- [2026-09-04] **[Complete]**
  Completed full archive import and verified lossless EML roundtrip across all real archive inputs.
