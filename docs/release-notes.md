# Release Notes

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

Known limitations (tracked in `docs/todo.md`): `Cc`/`Bcc` headers aren't
captured, HTML-only message bodies are stored as raw unparsed HTML,
attachments (including filenames) aren't captured at all, and the stored
`date` is the raw, client-supplied `Date` header rather than Gmail's own
`internalDate`.
