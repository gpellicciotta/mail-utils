# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`mail-utils` polls a single personal Gmail account on a schedule and indexes new messages into a local SQLite
database (`data/gmail.db`), using the Gmail API and OAuth 2.0. It's a personal, single-user tool — not a
package/library, no server, no multi-tenant concerns.

**Read-only is a hard design invariant, not just a default:** the app only ever requests the `gmail.readonly`
scope (`config.py`'s `SCOPES`). It never sends, labels, or deletes anything. Don't add write/send/delete
capability without explicitly discussing it first — that's a deliberate scope decision, not an oversight.

The app is cross-platform (pure Python/stdlib + pathlib, no Windows-specific code) — verified by running the
full test suite and CLI in a `python:3.11-slim` Docker container. Scheduling is cross-platform too:
`mail-utils schedule` dispatches to Windows Task Scheduler (via PowerShell) or cron, by `platform.system()`.
The Setup walkthrough's shell examples are still PowerShell since that's the primary dev environment, but
nothing about the app itself assumes Windows.

## Commands

All commands use the project's venv (`.venv`, created once via `python -m venv .venv`).

- Install/update in editable mode, with the `dev` extra (pytest, ruff): `.venv\Scripts\pip install -e ".[dev]"`
  (drop `[dev]` if you only need to run the app, not the tests/linter)
- `mail-utils <command>` once installed (equivalent to `.venv\Scripts\python -m mail_utils.cli <command>`):
  `import` (full sync first run, incremental after), `stats` (offline summary), `export <output_dir>`
  (offline markdown dump), `schedule`/`unschedule` (recurring job registration — Windows Task Scheduler or
  cron, dispatched by `platform.system()`; `mail-utils schedule --job-name <name> --interval-minutes N --
  import|export [flags...]`, see README's "Scheduling" section for the `--` requirement and cron's interval
  constraints), `--version` (reads live package metadata, see Conventions below).
- `import`/`stats`/`export` accept `--filter "..."` (see README's "Filtering" — `import --filter` is passed
  straight through to Gmail's own search; `stats`/`export --filter` are evaluated locally by
  `mail_utils/filters.py`, a deliberately smaller subset) and `--db <path>` to point at a database other
  than the default `data/gmail.db`.
- Run the test suite: `.venv\Scripts\python -m pytest`; lint/format: `.venv\Scripts\ruff check .` /
  `.venv\Scripts\ruff format .` (line-length 132, `[tool.ruff]` in `pyproject.toml`; CI runs both plus
  `pytest` plus `python -m build`).

Dependencies are declared once, in `pyproject.toml` — there is no separate `requirements.txt` to keep in sync.

## Architecture

Seven modules under `src/mail_utils/` (src layout — see README's "Project layout" for the rationale),
each with one job:

- **`config.py`** — `DATA_DIR` (`BASE_DIR / "data"`, gitignored in full) holding the secrets/database
  (`data/credentials.json`, `data/token.json`, `data/gmail.db`), plus a separate top-level, also gitignored,
  `LOG_DIR` (`BASE_DIR / "logs"`, `logs/mail-utils.log`) and the OAuth `SCOPES` list. Single source of truth
  for both; nothing else in the codebase hardcodes a path.
- **`auth.py`** — `get_credentials()`: loads/refreshes `data/token.json` silently when possible, otherwise
  runs the one-time interactive `InstalledAppFlow` browser consent using `data/credentials.json`.
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
  README's "Filtering" section for the full rationale and the exact semantics of each token (label match is a
  substring of a resolved label name, not an exact name — e.g. `label:investing` matches `to-read/investing`;
  `from:`/etc. match against `message_addresses`, not the raw header; `after:`/`before:` compare
  `internal_date_ms` and never match a `NULL`).
- **`scheduling.py`** — cross-platform recurring-job registration, dispatched by `platform.system()` in
  `cli.py`. Command-construction is deliberately split from execution: `build_windows_register_script`,
  `build_cron_line`, `cron_schedule_fields`, etc. are pure functions (no subprocess calls) so they're testable
  without touching a real crontab/Task Scheduler; `schedule_windows`/`schedule_cron`/`unschedule_*`/`list_*`
  are the thin `subprocess`-calling wrappers around them. Jobs are named (`--job-name`, default `default`) so
  several can coexist: Windows task `MailUtils-<job-name>`; a crontab line tagged with a trailing
  `# mail-utils:<job-name>` marker comment, used to find-and-replace just that line on re-schedule/remove.
  `cron_schedule_fields` translates `--interval-minutes` into cron's minute/hour/day fields and rejects values
  that don't divide evenly (60 minutes ÷ N, 24 hours ÷ N) — cron's fields are independent modulo-wheels, not a
  true elapsed-time interval like Windows Task Scheduler's, so e.g. `*/1440` (attempting "once a day" as a
  minute-step) is simply invalid; it becomes `0 0 */1 * *` instead. Also fixed a real bug caught while building
  this: the old `register_task.ps1`'s `-RepetitionDuration ([TimeSpan]::MaxValue)` (meant as "indefinitely")
  produces a value Task Scheduler's XML schema rejects outright — `schedule_windows` uses a 10-year duration
  instead. That script was never actually run end-to-end before, so the bug had never been caught.
- **`cli.py`** — the entry point (`python -m mail_utils.cli <command>`, or `mail-utils <command>` once
  installed). `argparse`-based subcommands: `import` (sets up logging, refreshes the `labels` table,
  decides full vs. incremental sync from whether `sync_state` has a `last_history_id` yet, drives the
  fetch/parse/upsert loop with progress logging every `PROGRESS_LOG_INTERVAL` (50) messages; `--filter`
  switches to a filtered full listing that skips `sync_state` entirely, see `filters.py` above), `stats`
  (read-only reporting straight off the local SQLite file; no Gmail API calls, so it works offline and needs
  no credentials), `export <output_dir>` (also offline/local-DB-only — writes one YAML-frontmatter `.md` file or standard RFC 5322 `.eml` file via
  `--format md|eml` per message, bucketed into `<YYYY>/<MM>/` subdirectories by `internal_date_ms`, `unknown/`
  for rows that don't have one yet; uses PyYAML's `safe_dump` for Markdown and standard `email` library for EML
  specifically so subjects/names with colons, quotes, or unicode serialize correctly), `schedule`/`unschedule` (thin wrappers
  around `scheduling.py` — `schedule` validates its inner command by parsing it against this same
  `build_parser()` before registering anything, so a typo'd flag fails immediately rather than at the next
  scheduled run), `help` (prints usage, prefixed with a short one-line description of the tool set via
  `argparse`'s `description=`; so does running with no subcommand — either accepts `--verbose` to also print
  full `--help` for every subcommand in turn, via `_print_full_help`, which walks the `subcommand_parsers`
  dict `build_parser` attaches to the returned parser as `_subcommand_parsers`), and `version` (a subcommand
  alias for `--version`, handled the same way in `main()`; also accepts its own `--verbose`). `import`/`stats`/`export`
  all take `--db <path>` (via `_resolve_db_path`) to override the default `data/gmail.db`. `stats --filter`/
  `export --filter` compute a matching-id set once via `_compute_matching_ids` and either build a
  `filtered_ids` temp table (`stats`, so its existing aggregate SQL queries stay aggregate queries) or just
  filter the already-fetched row list in Python (`export`, simpler since it's not doing SQL aggregation
  anyway). Used to be two separate modules (`main.py`/`stats.py`) — merged here so there's one entry point
  with real subcommands instead of separately invoked scripts. `import` was originally named `update`;
  renamed for clarity once `export` and filtering existed too and "update" no longer distinctly described
  what it did.

Full column-by-column documentation of what's actually stored (and, importantly, what *isn't* — e.g. attachments
are never captured at all) lives in `README.md`'s "Database contents" section. Treat that as the authoritative
schema reference, not this file — update it whenever `parse_message` or the schema in `db.py` changes.

Schema changes to `messages` (like adding `cc`/`bcc`) need a migration, not just an edit to `SCHEMA` in `db.py` —
`CREATE TABLE IF NOT EXISTS` only applies to a database that doesn't exist yet, so an existing
`data/gmail.db` needs an explicit `ALTER TABLE`. See `_ensure_column`/`init_db` in `db.py` for the
pattern to extend.

`config.py`'s `BASE_DIR = Path(__file__).resolve().parent.parent.parent` is relative to `config.py`'s own
location (`src/mail_utils/config.py` → up three levels → project root); `DATA_DIR = BASE_DIR / "data"` and
every other path in `config.py` are derived from it. Any future move of `config.py` itself, or another change
to the directory depth between it and the project root, needs that `.parent` chain recounted to match — it
broke silently in exactly this way during the `v0.10.0` src-layout migration (fixed in `v0.13.0`), because the
test suite always monkeypatches `DB_PATH` directly rather than exercising the real computation, so nothing
caught it until a real run would have. `tests/test_config.py` now guards against a repeat.

## Conventions

- Everything under `data/` (`credentials.json`, `token.json`, `gmail.db`, `logs/`) is gitignored in full
  as secrets/generated data — never commit any of it, and never add code that logs its contents at INFO level
  or above.
- Keep `README.md`'s "Setup", "Project layout", and "Database contents" sections in sync with the code — they're
  written to be detailed enough that a first-time setup doesn't need external guidance (see the Google Cloud
  Console walkthrough in "Setup" step 1, which was expanded specifically because the console's own UI/naming
  drifted from what the original short version assumed).
- `pyproject.toml`'s `version` field drives what actually gets installed; keep `CHANGELOG.md`'s newest
  heading matching it exactly, same as `hinolugi-support`'s `gradle.properties` convention. This is the
  *only* place the version is written — `mail-utils --version` reads it back dynamically via
  `importlib.metadata.version("mail-utils")` (see `cli.py`'s `build_parser`), not a second hardcoded
  string, so there's nothing else to keep in sync. This does mean the installed package metadata must actually be current for
  `--version` to be right — after bumping the version, re-run `pip install -e .` (or reload it) before
  trusting `--version`'s output. `--version --verbose` additionally looks up the `## v<version>` heading in
  `CHANGELOG.md` directly off disk (not packaged metadata) and prints that section, which is exactly why the
  heading has to match the `pyproject.toml` version exactly — a mismatch means `--verbose` silently finds
  nothing to print.
- Every backward-incompatible change bumps the version accordingly and gets a clearly-labeled breaking-change
  note in its `CHANGELOG.md` entry — this project is pre-1.0 (`0.x.y`), so in practice that means: a
  breaking change bumps the **minor** number (the `x` in `0.x.y`), same as every other feature addition does at
  this stage, but call out that it's breaking explicitly rather than letting it read as a routine addition.
- When adding a feature or fixing a documented limitation, add a corresponding entry to
  `CHANGELOG.md` (version heading, date, bullet list) and update/remove the matching item in
  `TODO.md`.
- `CHANGELOG.md` and `TODO.md` live at the repo root, not under `docs/`, for visibility. Other documentation
  (design notes, detailed plans, investigation write-ups) belongs under `docs/` instead.
- Any change that alters what's stored (new/changed/removed column, changed parsing behavior) must update both
  `README.md`'s "Database contents" tables and, if it's a behavior change to already-synced data, note whether
  existing rows in someone's `data/gmail.db` need a resync to pick it up (they generally won't be
  auto-migrated — there's no schema migration mechanism here, only `CREATE TABLE IF NOT EXISTS`).
