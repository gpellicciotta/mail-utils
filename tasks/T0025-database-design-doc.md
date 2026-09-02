# T0025: Document the database design

- **Status:** completed
- **Owner:** @claude
- **Started:** 2026-09-02
- **Ended:** 2026-09-02
- **Branch:** task/T0025-database-design-doc (merged, deleted)
- **Worktree:** ./work/T0025-database-design-doc (removed)

## Goal

Write a document explaining the database design: which tables exist and *why* they're shaped the way they
are (normalization choices, relationships, rationale) - complementing, not duplicating, `README.md`'s
"Database contents" section, which is the authoritative column-by-column reference.

## Scope

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

## Out of Scope

- Changing the schema itself.
- Duplicating README's per-column reference - link to it instead for exact column lists/types.

## Approach

1. Read `src/mail_utils/db.py` (schema + migration helpers) and `README.md`'s "Database contents" section
   as the ground truth for current behavior.
2. Write `docs/database-design.md` explaining the rationale behind each table and their relationships.
3. Cross-link: new doc references README for exact columns; README could optionally gain a one-line pointer
   to the new doc for "why", but isn't required to change.
4. Add the new doc to `docs/index.md`.

## Implementation Checklist

- [x] `docs/database-design.md` written
- [x] Linked from `docs/index.md`
- [x] Reviewed against `src/mail_utils/db.py` for accuracy (no drift from actual schema)

## Test Strategy

Documentation-only - no automated tests. Verify by cross-checking every claim against `db.py` and
`README.md` directly.

## Completion Criteria

`docs/database-design.md` exists, is linked from `docs/index.md`, and accurately explains the rationale
for every table in the current schema without duplicating README's column reference.

## Progress Log

- 2026-09-02: Claimed, worktree/branch created.
- 2026-09-02: Wrote `docs/database-design.md` (per-table rationale, normalization decisions, delete-then-
  insert refresh pattern, content-addressed attachment storage, FTS5 sync mechanism, schema-evolution
  approach, and a logical relationship diagram), cross-checked against `src/mail_utils/db.py` and
  `README.md`'s "Database contents" section for accuracy. Linked from `docs/index.md`'s Core Documentation
  list and logged in `CHANGELOG.md`'s `vNext` section.

## Validation Record

- Documentation-only change - no automated tests apply. Verified by re-reading `src/mail_utils/db.py` in
  full and cross-checking every claim in the new doc against it and against README's existing column
  reference; no discrepancies found.
- **Review:** No PR, solo, AI Agent - summary presented to the user, who approved integrating on 2026-09-02.

## Completion Record

- 2026-09-02: Merged into `main`, removed from `TODO.md`, worktree and branch cleaned up.
