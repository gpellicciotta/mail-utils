# Release Notes

## v0.8.0
Released on 2026-08-19

New `export` command: `gmail-ingest export <output_dir>` dumps every
message as a YAML-frontmatter markdown file — one `.md` per message,
under `<output_dir>/<YYYY>/<MM>/<message_id>.md` (bucketed by
`internal_date_ms`; `unknown/` for rows synced before that column
existed). Frontmatter covers id/thread_id, from/to/cc/bcc, subject, date,
internal_date, labels (resolved to names), attachments
(filename/mime_type/size), and `body_mime_type`; empty/null fields are
omitted rather than written blank. Entirely offline — reads only the
local database, no Gmail API calls or credentials needed, same as
`stats`. Reruns just overwrite files (messages are immutable, nothing to
reconcile). Uses PyYAML (`safe_dump`) for correct serialization of
subjects/names containing colons, quotes, or unicode — a new runtime
dependency.

Also: `parse_message` now records `body_mime_type` (`"text/plain"` or
`"text/html"`) alongside `body_text` in a new column, so it's clear which
case produced a given `body_text` without re-deriving it — needed by
`export`, but generally useful. Same "populated going forward only"
migration caveat as `internal_date_ms`/`cc`/`bcc`.

## v0.7.0
Released on 2026-08-19

Housekeeping, no behavior change:

- `docs/release-notes.md` and `docs/todo.md` moved to top-level `RELEASES.md`
  and `TODO.md` (all-uppercase), matching the convention now used across all
  projects scaffolded from `python-template-project`. `docs/` is reserved
  for other documentation (design notes, detailed plans) going forward.
- Added `.github/workflows/ci.yml`: installs via `pip install -e ".[dev]"`
  and runs `pytest` on push/PR.

## v0.6.0
Released on 2026-08-19

Capture Gmail's own `internalDate` (epoch milliseconds, UTC) into a new
`internal_date_ms` column — the reliable, server-side receipt timestamp,
unlike the existing `date` column (the raw, client-supplied `Date:`
header, which can be missing, malformed, or spoofed). Migrated onto
existing databases automatically via `_ensure_column`, same as `cc`/`bcc`
in `v0.2.0`; existing rows are `NULL` until re-synced.

## v0.5.0
Released on 2026-08-19

**Breaking change:** `main.py` and `stats.py` are gone, replaced by a single `cli.py` entry point with
subcommands: `update` (was `python -m gmail_ingest.main`, now `python -m gmail_ingest.cli update`), `stats`
(was `python -m gmail_ingest.stats`, now `python -m gmail_ingest.cli stats`), and `help`. Anything invoking the
old module paths directly (a scheduled task, a saved command) needs to switch to the new form —
`register_task.ps1` has been updated, but nothing external is migrated automatically.

Also:
- `pyproject.toml` gained a `[project.scripts]` entry, so after `pip install -e .`, `gmail-ingest update` /
  `gmail-ingest stats` work directly — no `python -m` needed.
- New `tests/test_cli.py` covers the subcommand-routing logic (no live credentials needed).

## v0.4.0
Released on 2026-08-19

Attachment metadata capture: a new `attachments` table (`message_id`,
`attachment_id`, `filename`, `mime_type`, `size`) — `gmail_client.parse_attachments`
walks the MIME tree collecting every part with a filename (inline images
included, since it's metadata-only either way) and `db.upsert_attachments`
stores it, same delete-then-insert-per-message pattern as
`message_addresses`. No extra API call needed — `format=full` already
returns this metadata, just unread until now. Attachment *bytes* are
still never fetched.

`python -m gmail_ingest.stats` gained a one-line "Attachments: N total,
X.X MB" summary.

Same "populated going forward only" caveat as the last two releases:
existing rows won't retroactively gain attachment data until re-synced.

## v0.3.0
Released on 2026-08-19

Recipient statistics: a new `message_addresses` table (`message_id`,
`role`, `address`, `name`) captures every individual address from a
message's From/To/Cc/Bcc headers, normalized (lowercased) for dedup, at
ingest time — computed once by `gmail_client.parse_addresses` and stored
by `db.upsert_addresses` alongside the existing `upsert_message` call in
both the full and incremental sync loops. `python -m gmail_ingest.stats`
now reads that table directly (no header-parsing at query time) to print
"Top senders" / "Top To recipients" / "Top Cc recipients" / "Top Bcc
recipients" sections, same style as the existing "Top labels".

Like `labels`, and like the `cc`/`bcc` columns added in `v0.2.0`, this is
populated going forward only — a database from before this table existed
won't have historical rows until those messages are re-synced.

## v0.2.0
Released on 2026-08-19

Capture `Cc`/`Bcc` headers into new `cc`/`bcc` columns on `messages`.
Migration is automatic — `db.init_db` adds the columns to an existing
`gmail_index.db` via `ALTER TABLE` if they're missing, so a resync isn't
required for the app to keep working, but existing rows won't have
`cc`/`bcc` retroactively populated until they're re-fetched (a full
resync, or a one-off targeted refetch).

Note: `Bcc` is rarely present to capture in the first place — mail
servers, including Gmail for incoming mail, strip it before delivery to
anyone but the Bcc'd recipient. It reliably shows up only in your own
`Sent` copies.

## v0.1.0
Released on 2026-08-19

First working version.

- OAuth 2.0 "Installed App" flow (`auth.py`): one-time interactive browser
  consent, cached refresh token in `token.json` for silent unattended runs
  afterwards.
- Sync (`main.py`, `gmail_client.py`): full mailbox listing on first run;
  every later run uses the Gmail History API to fetch only messages added
  since the last run, with automatic fallback to a full resync if the
  stored `historyId` has expired.
- Progress logging every 50 messages during a sync, with a running `%`
  against the mailbox's reported message total during a full sync.
- SQLite storage (`db.py`) in `gmail_index.db`:
  - `messages` — one row per Gmail message (id, thread_id, sender,
    recipient, subject, date, snippet, label_ids, body_text, fetched_at).
    Upserts are keyed on Gmail's message id, so reruns are safe.
  - `sync_state` — tracks the last processed `historyId`.
  - `labels` — Gmail label id -> display name, refreshed every run, so
    label ids on messages can be resolved to readable names.
- `stats.py`: `python -m gmail_ingest.stats` prints summary stats (message
  count, distinct threads, first/last indexed time, current
  `last_history_id`, top labels by name) straight from the local database,
  using only Python's built-in `sqlite3` module.
- `register_task.ps1`: one-time Windows Task Scheduler registration,
  running the sync every 30 minutes.
- Packaged as a proper `pyproject.toml` project (PEP 621), installed
  editable (`pip install -e .`); `requirements.txt` is gone, `pyproject.toml`
  is now the single source of truth for dependencies. Added a `dev` extra
  (`pytest`) and an initial test suite under `tests/` covering the
  pure-function message-parsing logic in `gmail_client.py`.

Known limitations (tracked in `docs/todo.md`): `Cc`/`Bcc` headers aren't
captured, HTML-only message bodies are stored as raw unparsed HTML,
attachments (including filenames) aren't captured at all, and the stored
`date` is the raw, client-supplied `Date` header rather than Gmail's own
`internalDate`.
