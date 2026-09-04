---
id: T0004
owner: "@claude"
needs: []
branch: task/T0004-capture-attachment-content
worktree: ./work/T0004-capture-attachment-content
status: completed
started: 2026-08-27
ended: 2026-08-28
---

# T0004: Capture full attachment content, not just metadata

## Goals
Capture actual attachment binary content across Gmail, Outlook PST, and Thunderbird imports.
Store attachments content-addressed under data/attachments and support exporting full attachment payloads.

## Task Execution Steps

- [x] **[Decide]**    Choose storage design between inline SQLite BLOBs and content-addressed filesystem storage.
- [x] **[Decided]**   Store attachment payloads in data/attachments hashed by SHA-256 and reference digests in database.
- [x] **[Decide]**    Determine whether attachment fetching should be opt-in or enabled by default.
- [x] **[Decided]**   Add opt-in --with-attachments flag to preserve lightweight default behavior.
- [x] **[Implement]** Implement AttachmentStore module with content hashing and file persistence.
- [x] **[Implement]** Add content_sha256 column migration to SQLite attachments table.
- [x] **[Implement]** Extract attachment bytes in Gmail, Thunderbird, and PST import parsers.
- [x] **[Implement]** Update export and store-in-gmail commands to reconstruct messages with full attachment payloads.
- [x] **[Verify]**    Verify unit and integration tests across import parsers, export formats, and storage.
- [x] **[Doc]**       Document attachment storage architecture and command flags in README and CLI specs.

## Execution Log

- [2026-08-28] **[Implement]**
  Implemented AttachmentStore, schema migration, import parser payload fetching, and export payload reconstruction.

- [2026-08-28] **[Verify]**
  Passed 174 automated tests covering attachment hashing, parser extraction, and CLI roundtrips.

- [2026-08-28] **[Complete]**
  Shipped opt-in attachment capture and export support across all supported mail sources.
