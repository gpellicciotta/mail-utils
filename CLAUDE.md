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

- Install/update in editable mode, with the `dev` extra (pytest): `.venv\Scripts\pip install -e ".[dev]"`
  (drop `[dev]` if you only need to run the app, not the tests)
- Run one sync (full on first run, incremental after): `.venv\Scripts\python -m gmail_ingest.cli import`
  (or `gmail-ingest import` after install — see `pyproject.toml`'s `[project.scripts]`)
- Print database stats (message count, threads, last sync state, top labels, recipients, attachments):
  `.venv\Scripts\python -m gmail_ingest.cli stats`
- Export every message as markdown (offline, reads only the local DB): `.venv\Scripts\python -m gmail_ingest.cli export <output_dir>`
- All three of the above accept `--filter "..."` — see README's "Filtering" section for the syntax and the
  important semantic difference between `import --filter` (passed straight through to Gmail's own search) and
  `stats`/`export --filter` (evaluated locally by `gmail_ingest/filters.py`, a deliberately smaller subset).
- Check the installed version: `gmail-ingest --version` (reads live package metadata — see Conventions below)
- Run the test suite: `.venv\Scripts\python -m pytest`
- Register the 30-minute scheduled task: `.\register_task.ps1`
- Unregister it: `Unregister-ScheduledTask -TaskName GmailIngest -Confirm:$false`

Dependencies are declared once, in `pyproject.toml` — there is no separate `requirements.txt` to keep in sync.

## Architecture

Six modules under `src/gmail_ingest/` (src layout — see README's "Project layout" for the rationale),
each with one job:

- **`config.py`** — every path (`credentials.json`, `token.json`, `gmail_index.db`, `logs/gmail_ingest.log`) and
  the OAuth `SCOPES` list. Single source of truth for both; nothing else in the codebase hardcodes a path.
- **`auth.py`** — `get_credentials()`: loads/refreshes `token.json` silently when possible, otherwise runs the
  one-time interactive `InstalledAppFlow` browser consent using `credentials.json`.
- **`gmail_client.py`** — thin wrapper over the Gmail API: paginated full-mailbox listing
  (`list_all_message_ids`), paginated History API diffing (`list_changed_message_ids`, raises
  `HistoryExpiredError` on a 404 so the caller can fall back to a full resync), label listing
  (`list_labels`), single-message fetch (`fetch_message`, `format=full`), `parse_message` — the one place
  that decides what's kept from a raw Gmail API message and what's dropped, for the `messages` table row — and
  `parse_addresses`, a sibling pure function that splits/normalizes the same message's From/To/Cc/Bcc headers
  into individual `message_addresses` rows (via `email.utils.getaddresses`, lowercased for dedup), and
  `parse_attachments`, which walks the MIME tree collecting every part with a filename (metadata only —
  filename/mime type/size/`attachmentId` — never the bytes). `parse_message`'s body extraction also records
  `body_mime_type` (`"text/plain"` or `"text/html"`) alongside `body_text`, so downstream consumers (like
  `cli.py`'s `export`) can tell which case they're in without re-deriving it. See `README.md`'s "Database
  contents" section for the exact, currently-documented behavior (and known gaps — `TODO.md` tracks fixing
  them).
- **`db.py`** — SQLite schema and upsert helpers. Five tables: `messages` (upserted by Gmail's message `id`, so
  reruns never duplicate), `sync_state` (currently just `last_history_id`), `labels` (id -> display name,
  refreshed in full every run), `message_addresses` and `attachments` (each one row per message/role/address or
  message/attachment, replaced in full for a given message on every rerun via `upsert_addresses`/
  `upsert_attachments` — delete-then-insert, not an upsert, since Gmail messages are immutable so there's
  nothing to merge).
- **`filters.py`** — `parse_filter`/`message_matches`: the local (non-Gmail-API) filter interpreter used by
  `stats --filter`/`export --filter`. Deliberately a smaller grammar than Gmail's own — `label:`, `from:`,
  `to:`, `cc:`, `bcc:`, `subject:`, `after:YYYY/MM/DD`, `before:YYYY/MM/DD`, `has:attachment`, bare
  words/quoted phrases (subject+body substring), all ANDed. `parse_filter` raises `FilterError` on an
  unrecognized `key:` prefix rather than silently ignoring it. `import --filter` does *not* use this module —
  it passes the raw string straight to Gmail's own search instead, getting Gmail's full grammar for free. See
  README's "Filtering" section for the full rationale and the exact semantics of each token (label match is
  exact-name not substring; `from:`/etc. match against `message_addresses`, not the raw header; `after:`/
  `before:` compare `internal_date_ms` and never match a `NULL`).
- **`cli.py`** — the entry point (`python -m gmail_ingest.cli <command>`, or `gmail-ingest <command>` once
  installed). `argparse`-based, four subcommands: `import` (sets up logging, refreshes the `labels` table,
  decides full vs. incremental sync from whether `sync_state` has a `last_history_id` yet, drives the
  fetch/parse/upsert loop with progress logging every `PROGRESS_LOG_INTERVAL` (50) messages — this is what
  `register_task.ps1` schedules; `--filter` switches to a filtered full listing that skips `sync_state`
  entirely, see `filters.py` above), `stats` (read-only reporting straight off the local SQLite file; no Gmail
  API calls, so it works offline and needs no credentials), `export <output_dir>` (also offline/local-DB-only —
  writes one YAML-frontmatter `.md` file per message, bucketed into `<YYYY>/<MM>/` subdirectories by
  `internal_date_ms`, `unknown/` for rows that don't have one yet; uses PyYAML's `safe_dump` rather than
  hand-rolled string formatting specifically so subjects/names with colons, quotes, or unicode serialize
  correctly), and `help` (prints usage; so does running with no subcommand). `stats --filter`/`export --filter`
  compute a matching-id set once via `_compute_matching_ids` and either build a `filtered_ids` temp table
  (`stats`, so its existing aggregate SQL queries stay aggregate queries) or just filter the already-fetched
  row list in Python (`export`, simpler since it's not doing SQL aggregation anyway). Used to be two separate
  modules (`main.py`/`stats.py`) — merged here so there's one entry point with real subcommands instead of
  separately invoked scripts. `import` was originally named `update`; renamed for clarity once `export` and
  filtering existed too and "update" no longer distinctly described what it did.

Full column-by-column documentation of what's actually stored (and, importantly, what *isn't* — e.g. attachments
are never captured at all) lives in `README.md`'s "Database contents" section. Treat that as the authoritative
schema reference, not this file — update it whenever `parse_message` or the schema in `db.py` changes.

Schema changes to `messages` (like adding `cc`/`bcc`) need a migration, not just an edit to `SCHEMA` in `db.py` —
`CREATE TABLE IF NOT EXISTS` only applies to a database that doesn't exist yet, so an existing `gmail_index.db`
needs an explicit `ALTER TABLE`. See `_ensure_column`/`init_db` in `db.py` for the pattern to extend.

## Conventions

- `credentials.json`, `token.json`, `gmail_index.db`, and `logs/` are gitignored secrets/generated data — never
  commit them, and never add code that logs their contents at INFO level or above.
- Keep `README.md`'s "Setup", "Project layout", and "Database contents" sections in sync with the code — they're
  written to be detailed enough that a first-time setup doesn't need external guidance (see the Google Cloud
  Console walkthrough in "Setup" step 1, which was expanded specifically because the console's own UI/naming
  drifted from what the original short version assumed).
- `pyproject.toml`'s `version` field drives what actually gets installed; keep `RELEASES.md`'s newest
  heading matching it exactly, same as `hinolugi-support`'s `gradle.properties` convention. This is the
  *only* place the version is written — `gmail-ingest --version` reads it back dynamically via
  `importlib.metadata.version("gmail-ingest")` (see `cli.py`'s `build_parser`), not a second hardcoded
  string, so there's nothing else to keep in sync. (`python-template-project` instead hand-maintains a
  duplicate `__version__` in `__init__.py` — deliberately not copied here, since a second copy is exactly
  the kind of thing that drifts.) This does mean the installed package metadata must actually be current for
  `--version` to be right — after bumping the version, re-run `pip install -e .` (or reload it) before
  trusting `--version`'s output.
- Every backward-incompatible change bumps the version accordingly and gets a clearly-labeled breaking-change
  note in its `RELEASES.md` entry — this project is pre-1.0 (`0.x.y`), so in practice that means: a
  breaking change bumps the **minor** number (the `x` in `0.x.y`), same as every other feature addition does at
  this stage, but call out that it's breaking explicitly rather than letting it read as a routine addition.
- When adding a feature or fixing a documented limitation, add a corresponding entry to
  `RELEASES.md` (version heading, date, bullet list) and update/remove the matching item in
  `TODO.md`.
- `RELEASES.md` and `TODO.md` live at the repo root, not under `docs/`, for visibility. Other documentation
  (design notes, detailed plans, investigation write-ups) belongs under `docs/` instead.
- Any change that alters what's stored (new/changed/removed column, changed parsing behavior) must update both
  `README.md`'s "Database contents" tables and, if it's a behavior change to already-synced data, note whether
  existing rows in someone's `gmail_index.db` need a resync to pick it up (they generally won't be
  auto-migrated — there's no schema migration mechanism here, only `CREATE TABLE IF NOT EXISTS`).
