---
id: T0014
owner: "@claude"
needs: []
branch: task/T0014-preserve-html-body-and-inline-images
worktree: ./work/T0014-preserve-html-body-and-inline-images
status: completed
started: 2026-08-28
ended: 2026-08-31
---

# T0014: Preserve HTML body content and inline images instead of silently dropping them

## Goals
Preserve HTML message bodies and inline image Content-IDs across Gmail, Outlook, and Thunderbird import paths.
Construct proper multipart/alternative payloads during export and restore operations.

## Task Execution Steps

- [x] **[Decide]**    Choose storage strategy between HTML body replacement and dual plain/HTML representation.
- [x] **[Decided]**   Store both plain body_text and body_html columns to ensure maximum content fidelity.
- [x] **[Implement]** Add body_html and content_id column migrations to SQLite database schema.
- [x] **[Implement]** Extract HTML body parts and attachment Content-IDs across Gmail, PST, and Thunderbird parsers.
- [x] **[Implement]** Update EML builder to create multipart/alternative structures with inline attachments.
- [x] **[Verify]**    Execute live message seeding, sync, and comparison against disposable Gmail account.
- [x] **[Doc]**       Update database schema documentation and release notes in README and CHANGELOG.

## Execution Log

- [2026-08-31] **[Verify]**
  Passed 200 automated tests and verified 7 seeded HTML and inline-image messages against live Gmail account.

- [2026-08-31] **[Complete]**
  Shipped dual plain/HTML body preservation and Content-ID inline attachment reconstruction across all parsers.
