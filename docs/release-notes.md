# Release Notes

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
