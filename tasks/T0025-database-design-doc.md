---
id: T0025
title: "Document the database design"
owner: claude
needs: []
branch: "task/T0025-database-design-doc (merged, deleted)"
worktree: "./work/T0025-database-design-doc (removed)"
status: completed
started: 2026-09-02
ended: 2026-09-02
---

# T0025: Document the database design

## Objectives & Scope

### Goal

Write a document explaining the database design: which tables exist and *why* they're shaped the way they
are (normalization choices, relationships, rationale) - complementing, not duplicating, `README.md`'s
"Database contents" section, which is the authoritative column-by-column reference.

### Scope

- New `docs/database-design.md`, covering:
  - Overview: single SQLite file, source-prefixed ids, read-only-by-default posture.
  - Each table's purpose and the design decision behind its shape (`messages`, `message_addresses`,
    `attachments`, `labels`, `sync_state`, `gmail_store_state`, `messages_fts`).
  - Why normalized child tables (`message_addresses`, `attachments`) instead of denormalized columns on
    `messages`.
  - The delete-then-insert refresh pattern for `message_addresses`/`attachments` and why it's safe (source
    messages are immutable).
  - Content-addressed attachment byte storage (`content_sha256`) and why it's separate from the metadata
    row.
  - FTS5 full-text search table and its relationship to `messages` (sync mechanism, `UNINDEXED` id).
  - `gmail_store_state` as the resumability mechanism for `store-in-gmail`.
  - Schema evolution: `CREATE TABLE IF NOT EXISTS` vs. `_ensure_column`/migrations, and why that split
    exists.
  - A relationship diagram (which tables reference `messages.id`, even though there's no actual FK
    enforcement - SQLite FKs are usually off - so this is a logical relationship).
- Link the new doc from `docs/index.md`'s "Core Documentation" section.
- Documentation-only task - no code or schema changes.

### Out of Scope

- Changing the schema itself.
- Duplicating README's per-column reference - link to it instead for exact column lists/types.

### Dependencies

None.

### Completion Criteria

`docs/database-design.md` exists, is linked from `docs/index.md`, and accurately explains the rationale
for every table in the current schema without duplicating README's column reference.

## Task Implementation and Verification Steps

- [x] [Read] Read `src/mail_utils/db.py` (schema + migration helpers) and `README.md`'s "Database
  contents" section as the ground truth for current behavior.
- [x] [Doc] Wrote `docs/database-design.md` explaining the rationale behind each table and their
  relationships (per-table rationale, normalization decisions, delete-then-insert refresh pattern,
  content-addressed attachment storage, FTS5 sync mechanism, schema-evolution approach, and a logical
  relationship diagram).
- [x] [Doc] Linked the new doc from `docs/index.md`'s Core Documentation list, and logged it in
  `CHANGELOG.md`'s `vNext` section.
- [x] [Verify] Documentation-only change - no automated tests apply. Verified by re-reading
  `src/mail_utils/db.py` in full and cross-checking every claim in the new doc against it and against
  README's existing column reference; no discrepancies found.
- [x] [Visual] N/A - no UI surface; documentation-only change.

## Progress & Validation Log

- 2026-09-02: Claimed, worktree/branch created.
- 2026-09-02: Wrote `docs/database-design.md` (per-table rationale, normalization decisions, delete-then-
  insert refresh pattern, content-addressed attachment storage, FTS5 sync mechanism, schema-evolution
  approach, and a logical relationship diagram), cross-checked against `src/mail_utils/db.py` and
  `README.md`'s "Database contents" section for accuracy. Linked from `docs/index.md`'s Core Documentation
  list and logged in `CHANGELOG.md`'s `vNext` section.
- Documentation-only change - no automated tests apply. Verified by re-reading `src/mail_utils/db.py` in
  full and cross-checking every claim in the new doc against it and against README's existing column
  reference; no discrepancies found. Review: No PR, solo, AI Agent - summary presented to the user, who
  approved integrating on 2026-09-02.

## Completion Record

- 2026-09-02: Merged into `main`, removed from `TODO.md`, worktree and branch cleaned up.
