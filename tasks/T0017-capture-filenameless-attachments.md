---
id: T0017
owner: "@antigravity"
needs: []
branch: task/T0017-capture-filenameless-attachments
worktree: ./work/T0017-capture-filenameless-attachments
status: completed
started: 2026-08-31
ended: 2026-08-31
---

# T0017: Capture attachments/inline parts that carry no filename

## Goals
Capture attachments and inline image parts that omit explicit filename parameters.
Make attachment filename column nullable and reconstruct inline parts with Content-IDs.

## Task Execution Steps

- [x] **[Decide]**    Choose schema approach for storing attachments without explicit filenames.
- [x] **[Decided]**   Make attachments.filename column nullable across SQLite table definitions and migrations.
- [x] **[Implement]** Update SQLite attachment schema and table migration logic in db module.
- [x] **[Implement]** Capture filenameless parts with Content-ID or attachmentId in Gmail parser.
- [x] **[Implement]** Capture filenameless attachment rows in PST message parser.
- [x] **[Implement]** Capture filenameless Content-ID and attachment disposition parts in Thunderbird parser.
- [x] **[Verify]**    Verify unit tests for filenameless attachment capture across all parsers.
- [x] **[Doc]**       Record filenameless attachment support in CHANGELOG.md.

## Execution Log

- [2026-08-31] **[Verify]**
  Passed unit tests in test_gmail_client.py and test_thunderbird.py verifying filenameless capture.

- [2026-08-31] **[Complete]**
  Supported filenameless attachments and inline parts across Gmail, PST, and Thunderbird parsers.
