# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`gmail-ingest` polls a single personal Gmail account on a schedule and indexes new messages into a local SQLite
database (`gmail_index.db`), using the Gmail API and OAuth 2.0. It's a personal, single-user tool — not a
package/library, no server, no multi-tenant concerns.

**Read-only is a hard design invariant, not just a default:** the app only ever requests the `gmail.readonly`
scope (`config.py`'s `SCOPES`). It never sends, labels, or deletes anything. Don't add write/send/delete
capability without explicitly discussing it first — that's a deliberate scope decision, not an oversight.

Windows-first: setup docs and `register_task.ps1` assume PowerShell and Windows Task Scheduler.

## Commands

All commands use the project's venv (`.venv`, created once via `python -m venv .venv`).

- Install/update dependencies: `.venv\Scripts\pip install -r requirements.txt`
- Run one sync (full on first run, incremental after): `.venv\Scripts\python -m gmail_ingest.main`
- Print database stats (message count, threads, last sync state, top labels): `.venv\Scripts\python -m gmail_ingest.stats`
- Register the 30-minute scheduled task: `.\register_task.ps1`
- Unregister it: `Unregister-ScheduledTask -TaskName GmailIngest -Confirm:$false`
- No automated test suite yet — see `docs/todo.md`.

## Architecture

Five modules under `gmail_ingest/`, each with one job:

- **`config.py`** — every path (`credentials.json`, `token.json`, `gmail_index.db`, `logs/gmail_ingest.log`) and
  the OAuth `SCOPES` list. Single source of truth for both; nothing else in the codebase hardcodes a path.
- **`auth.py`** — `get_credentials()`: loads/refreshes `token.json` silently when possible, otherwise runs the
  one-time interactive `InstalledAppFlow` browser consent using `credentials.json`.
- **`gmail_client.py`** — thin wrapper over the Gmail API: paginated full-mailbox listing
  (`list_all_message_ids`), paginated History API diffing (`list_changed_message_ids`, raises
  `HistoryExpiredError` on a 404 so the caller can fall back to a full resync), label listing
  (`list_labels`), single-message fetch (`fetch_message`, `format=full`), and `parse_message` — the one place
  that decides what's kept from a raw Gmail API message and what's dropped. See `README.md`'s "Database
  contents" section for the exact, currently-documented behavior (and known gaps — `docs/todo.md` tracks fixing
  them).
- **`db.py`** — SQLite schema and upsert helpers. Three tables: `messages` (upserted by Gmail's message `id`, so
  reruns never duplicate), `sync_state` (currently just `last_history_id`), `labels` (id -> display name,
  refreshed in full every run).
- **`main.py`** — orchestrates one run: sets up logging, refreshes the `labels` table, decides full vs.
  incremental sync from whether `sync_state` has a `last_history_id` yet, drives the fetch/parse/upsert loop with
  progress logging every `PROGRESS_LOG_INTERVAL` (50) messages.
- **`stats.py`** — read-only reporting straight off the local SQLite file via Python's built-in `sqlite3` module;
  no Gmail API calls, so it works offline and needs no credentials.

Full column-by-column documentation of what's actually stored (and, importantly, what *isn't* — e.g. `Cc`/`Bcc`
are silently dropped, attachments are never captured) lives in `README.md`'s "Database contents" section. Treat
that as the authoritative schema reference, not this file — update it whenever `parse_message` or the schema
in `db.py` changes.

## Conventions

- `credentials.json`, `token.json`, `gmail_index.db`, and `logs/` are gitignored secrets/generated data — never
  commit them, and never add code that logs their contents at INFO level or above.
- Keep `README.md`'s "Setup", "Project layout", and "Database contents" sections in sync with the code — they're
  written to be detailed enough that a first-time setup doesn't need external guidance (see the Google Cloud
  Console walkthrough in "Setup" step 1, which was expanded specifically because the console's own UI/naming
  drifted from what the original short version assumed).
- No build-config file carries a version number (this isn't a published package). `docs/release-notes.md`'s
  newest heading is the single source of truth for the current version.
- When adding a feature or fixing a documented limitation, add a corresponding entry to
  `docs/release-notes.md` (version heading, date, bullet list) and update/remove the matching item in
  `docs/todo.md`.
- Any change that alters what's stored (new/changed/removed column, changed parsing behavior) must update both
  `README.md`'s "Database contents" tables and, if it's a behavior change to already-synced data, note whether
  existing rows in someone's `gmail_index.db` need a resync to pick it up (they generally won't be
  auto-migrated — there's no schema migration mechanism here, only `CREATE TABLE IF NOT EXISTS`).
