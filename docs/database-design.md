# Database Design

This document explains *why* `mail-utils`' SQLite schema is shaped the way it is - the tables that exist,
the relationships between them, and the reasoning behind each design decision. For the exact,
column-by-column reference (types, nullability, which commands populate what), see `README.md`'s
["Database contents"](../README.md#database-contents) section instead - that stays the single authoritative
source for the current schema shape; this document explains the reasoning behind it and shouldn't drift
into re-listing columns.

The schema itself lives in `src/mail_utils/db.py`'s `SCHEMA` constant, applied via `init_db`.

---

## Overview

Everything lives in one SQLite file (`data/mails.db` by default, or `<dir>/mails.db` under `--db <dir>` -
see `docs/cli-spec.md`). A handful of design choices run through the whole schema:

- **One database, multiple sources.** Gmail, Outlook (`.pst`), and Thunderbird archives can all land in the
  same database. Every message id is source-prefixed (`gmail:...`, `outlook:...`, `thunderbird:...`) purely
  as a namespacing convention to prevent id collisions across sources sharing one table - there's no
  per-source table split, because every source normalizes down to the same shape (a message with headers,
  a body, addresses, attachments, and folder/label membership) and downstream code (`search`, `stats`,
  `export`) shouldn't have to care which source a row came from.
- **Read-only by default, reflected in the schema too.** Only `store-in-gmail` ever writes back to a live
  mailbox, and its own bookkeeping (`gmail_store_state`) is the only table that exists purely to support a
  write path - see its own section below.
- **No SQLite foreign-key constraints.** Tables like `message_addresses` and `attachments` reference
  `messages.id` logically (see [Relationships](#relationships)), but nothing declares `FOREIGN KEY` or
  turns on `PRAGMA foreign_keys`. Rows are always written by application code (`upsert_message` before
  `upsert_addresses`/`upsert_attachments`, in that order - see `cli.py`'s import loop), so referential
  integrity is maintained by call order, not enforced by the database. This keeps the delete-then-insert
  refresh pattern (below) simple: SQLite's default deferred/absent FK enforcement would otherwise require
  extra care around ordering deletes and inserts across a transaction.

## Tables

### `messages`

The core table - one row per message, keyed by its source-prefixed `id`. Holds header fields (`sender`,
`recipient`, `cc`, `bcc`, `subject`, `date`), the source's own timestamp (`internal_date_ms`, used for
`export`'s year/month bucketing since the raw `date` header isn't reliably parseable or even present
across sources), Gmail's label membership (`label_ids`, comma-separated rather than a join table - see
below), and the body in two forms (`body_text`/`body_mime_type`, `body_html`).

**Why `label_ids` is a comma-separated column, not a join table:** every other many-to-many relationship in
this schema (addresses, attachments) got its own child table. Labels didn't, because label membership is
read as a single unit alongside the rest of a message's metadata in every current code path (`stats`,
`export`, `filters.py`'s `label:` matching) and never queried the other direction ("which messages have
label X" doesn't need an index-backed join - the working set is a single mailbox, not a scale where that
matters). If a future feature needs to query messages by label efficiently, revisit this - a
`message_labels (message_id, label_id)` join table would be the natural evolution, symmetric with
`message_addresses`.

**Why two body columns instead of one:** `body_text` holds whichever single representation is "best" for
a message that only has one (plain text preferred, HTML markup as a fallback when that's all the source
has), while `body_mime_type` records which case it is. `body_html` independently captures the HTML part
whenever one exists, *alongside* `body_text`, so a message that originally had both a plain-text and an
HTML part doesn't lose one representation just because `body_text` had to pick one. This split exists
specifically so `export --format eml` and `store-in-gmail` can reconstruct a proper `multipart/alternative`
body instead of only ever re-exporting a single representation.

**Why upserted, not append-only:** `upsert_message` uses `INSERT ... ON CONFLICT(id) DO UPDATE`, keyed on
the source-prefixed `id`. Re-running an import (a scheduled Gmail sync, a resumed PST import) naturally
revisits already-seen messages; upserting makes that idempotent by construction, rather than needing a
separate "already seen" check before every insert.

### `message_addresses`

One row per `(message, role, address)` - normalized out of `messages` into its own table specifically so
`address` (lowercased) is queryable and indexable independent of which message it belongs to
(`idx_message_addresses_role_address` backs `filters.py`'s `from:`/`to:`/`cc:`/`bcc:` matching without a
full table scan per query). Putting `from`/`to`/`cc`/`bcc` as four columns on `messages` instead - the
naive alternative - can't be indexed for "does any of `to`/`cc`/`bcc` contain this address" without a
much less selective `LIKE` scan, and can't cleanly represent a message with several `To:` recipients (a
single text column would need its own ad hoc parsing at query time, duplicating what
`email.utils.getaddresses` already does once at import time in `gmail_client.py`'s `parse_addresses`).

**Why delete-then-insert on every resync, not a true upsert:** `upsert_addresses` deletes every row for a
`message_id` and reinserts the current set, rather than reconciling additions/removals. This is safe and
correct specifically *because* source messages are immutable - a Gmail message's headers, once sent, never
change, and neither do an already-imported PST/Thunderbird message's. There's never a real "this address
was removed" case to reconcile; delete-then-insert is just simpler than an upsert that can never actually
need to update a row in place.

### `attachments`

One row per attachment part, holding metadata only (`filename`, `mime_type`, `size`, `content_id`) plus two
optional fields: `attachment_id` (Gmail's own API id, needed to fetch that part's bytes later - always
`NULL` for PST/Thunderbird, which have no equivalent handle) and `content_sha256`.

**Why attachment bytes never touch this table, or SQLite at all:** attachment content can be large and
numerous, and a personal mailbox easily has the same image or PDF attached to dozens of messages (a
repeated signature logo, a forwarded thread). Storing bytes as a SQLite `BLOB` column would duplicate
identical content once per message and bloat the database file itself, which everything else (`search`,
`stats`) needs to open quickly. Instead, `attachment_store.py` keeps attachment bytes as content-addressed
files on disk (`<db-dir>/attachments/<content_sha256>`) - identical content is written once regardless of
how many messages reference it, and the database only ever stores the hash. This is why `content_sha256`
is `NULL` unless an import ran with `--with-attachments`: capturing content is opt-in and separate from
capturing metadata, so a lightweight default import isn't forced to also download every attachment's bytes.

**Why `content_id` exists separately from `attachment_id`:** `content_id` is the MIME `Content-ID` header a
part carried (e.g. `<image001@01D...>`), present only when a part is an inline image referenced from the
HTML body via `cid:`. It's what lets `export`/`store-in-gmail` re-embed an attachment as an inline part
under the HTML body instead of a regular attachment, so `<img src="cid:...">` keeps resolving - a distinct
concern from `attachment_id`, which is purely Gmail's API handle for fetching bytes.

Same delete-then-insert rationale as `message_addresses` applies to `upsert_attachments`.

### `labels`

A flat `id -> name` lookup, refreshed in full on every sync (`upsert_labels`, one `INSERT ... ON CONFLICT
DO UPDATE` per label). For Gmail, this mirrors the account's real label list. For PST/Thunderbird, there's
no native "label" concept, so each source synthesizes one label per folder (`outlook:<folder path>` /
`thunderbird:<folder path>`) - this is *why* `labels` exists as a separate table at all rather than only
being meaningful for Gmail: it's the mechanism that lets folder structure from non-Gmail sources survive
and be queried (`filters.py`'s `label:`) the same way real Gmail labels are, without `stats`/`export`/
`filters.py` needing separate code paths per source.

### `sync_state`

A generic `key -> value` table, deliberately schema-free rather than dedicated columns, because it holds
a small and slowly-growing set of unrelated bookkeeping values that don't share a natural row shape:
today, Gmail's History API watermark (`last_history_id`, used to decide full vs. incremental sync) and,
only while a `store-in-gmail` run is in progress, that run's tracking-label name. A new piece of
process-level bookkeeping can be added as a new key without a schema migration.

### `gmail_store_state`

`message_id -> gmail_id`, written only by `store-in-gmail` (the one write-capable command) as it stores
each message into a live Gmail mailbox. This table's entire reason to exist is resumability: `store-in-gmail`
checks it before storing a message, so a rerun after a crash, a `Ctrl-C`, or a deliberate `--max-messages`
cap simply skips whatever was already stored and continues, rather than duplicating messages in the target
mailbox. No other command reads or writes this table - it's kept separate from `sync_state` because it's
row-per-message bookkeeping (naturally keyed like `messages` itself), not a handful of scalar settings.

### `messages_fts`

An FTS5 virtual table (`subject`, `body_text`, `sender`, `recipient`, tokenized `unicode61
remove_diacritics 2` for accent-insensitive matching) backing `search`'s full-text queries. It's a separate
virtual table rather than an FTS5 "content=" shadow of `messages` itself, so its own indexed columns can be
a deliberate subset (e.g. `body_html`, `cc`, `bcc` aren't indexed for search) without pulling in FTS5's
content-table coupling. `id` is stored `UNINDEXED` - present for joining back to `messages`, never matched
against as text.

**Why it's kept in sync per-message rather than always rebuilt:** `upsert_message` deletes and reinserts a
message's own `messages_fts` row inline, in the same call that upserts `messages` itself, so search stays
current after every import without a separate reindex step. `_ensure_fts` additionally backfills the whole
table once, at `init_db` time, if `messages` already has rows but `messages_fts` is empty - the case where
FTS5 is being enabled against a database that predates it, or after the virtual table was dropped and
recreated.

## Schema Evolution

`SCHEMA`'s `CREATE TABLE IF NOT EXISTS` statements only ever apply to a database that doesn't exist yet -
they're silently a no-op against an existing `mails.db` file that predates a new column. `init_db` follows
them with a sequence of `_ensure_column` calls (each one checking `PRAGMA table_info` and issuing an
`ALTER TABLE ... ADD COLUMN` only if missing) for every column added after the table's original shape, so
`init_db` is what actually keeps an existing database current, not `SCHEMA` alone. A column that can't be
added this way (e.g. `attachments.filename` needing to become nullable, which `ALTER TABLE ADD COLUMN`
can't express) goes through a one-off rebuild instead - see `_ensure_attachments_filename_nullable` for
the copy-into-a-new-table-then-rename pattern used there. Any schema change follows this same rule: editing
`SCHEMA` alone is only correct for a column a brand-new database will get; an already-populated `mails.db`
needs the matching `_ensure_*` migration step added to `init_db` too.

## Relationships

No table declares a `FOREIGN KEY` (see [Overview](#overview) for why), but logically:

```
messages (id)
  ├── message_addresses (message_id)   -- 0..N per message, one per (role, address)
  ├── attachments (message_id)         -- 0..N per message, one per attachment part
  └── messages_fts (id)                -- exactly 1 per message, kept in sync inline

labels (id) <-- referenced by messages.label_ids (comma-separated, not a real join)

gmail_store_state (message_id) -- 0..1 per message, only for messages written via store-in-gmail
sync_state                     -- standalone; no relationship to messages
```

`message_addresses` and `attachments` are both scoped to a single message and fully replaced (deleted then
reinserted) on every resync of that message - see each table's own section above for why that's safe.
`messages_fts` is kept in lockstep with `messages` the same way, one row per message, but through explicit
delete+insert calls in `upsert_message` rather than a database-level trigger, since SQLite's own FTS5
external-content sync mechanism (`content=` tables + triggers) wasn't adopted (see the `messages_fts`
section above).
