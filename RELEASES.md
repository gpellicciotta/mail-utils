# Release Notes

## v0.16.0
Released on 2026-08-19

**Breaking change:** the project is renamed from `gmail-ingest` to `mail-utils` — package
`src/gmail_ingest/` → `src/mail_utils/`, `pyproject.toml`'s `name`/`[project.scripts]`, the console script
(`gmail-ingest` → `mail-utils`), every import, the log filename (`gmail_ingest.log` → `mail_utils.log`), the
Windows Task Scheduler task-name prefix (`GmailIngest-<job>` → `MailUtils-<job>`), and the cron marker
comment (`# gmail-ingest:<job>` → `# mail-utils:<job>`). Anything invoking the old module path or console
script name needs to switch; any already-registered `GmailIngest-*` scheduled task or `# gmail-ingest:`
crontab line needs re-registering under the new name (`mail-utils schedule ...`) after upgrading — nothing
migrates those automatically.

**Not renamed, deliberately:** the default database filename `gmail_index.db` (describes its content — a
Gmail index — not the tool's name) and the `gmail.readonly` OAuth scope. This is a project/branding rename,
not a change of what the tool does — it's still Gmail-specific.

Also pushed to a new GitHub repository: https://github.com/gpellicciotta/mail-utils.

## v0.15.0
Released on 2026-08-19

Added `ruff` (dev dependency, `[tool.ruff]` `line-length = 132` in `pyproject.toml`) — ran `ruff format`
across all source and tests, and applied its default lint fixes (modernized `Optional[str]`/`Iterator` typing
imports, explicit `check=False` on `subprocess.run` calls that intentionally don't raise on non-zero exit,
minor import-style cleanup). CI now runs `ruff check` + `ruff format --check` alongside `pytest` and the
build.

Also did a full README.md review and condense pass: fixed a stale "How it works" storage description
(pre-dated `cc`/`bcc`/`internal_date_ms`/`body_mime_type`/the `labels`/`message_addresses`/`attachments`
tables), consolidated the "populated going forward only" caveat — previously repeated near-verbatim in three
separate table sections — into one explanation, standardized on the `gmail-ingest <command>` console-script
form throughout instead of mixing it with the more verbose `python -m gmail_ingest.cli <command>`, and
reflowed everything to the new 132-character line width (433 → 338 lines). `CLAUDE.md` got a lighter version
of the same pass. No functional/behavior change.

## v0.14.0
Released on 2026-08-19

**Breaking change:** `register_task.ps1` is gone, replaced by a cross-platform `schedule`/`unschedule`
CLI subcommand pair (Windows Task Scheduler via PowerShell, or cron on Linux/macOS, dispatched by
`platform.system()`):

```powershell
gmail-ingest schedule --job-name work --interval-minutes 15 -- import --filter "label:Work" --db work.db
gmail-ingest schedule --list
gmail-ingest unschedule --job-name work
```

- Jobs are named (`--job-name`, default `default`), so multiple independently-filtered/independently-databased
  jobs can coexist — Windows task `GmailIngest-<job-name>`, or a crontab line tagged with a
  `# gmail-ingest:<job-name>` marker comment.
- Schedules either `import` or `export` (whichever you put after `--`); the inner command is validated
  (parsed against `gmail-ingest`'s own argument definitions) before registering anything, so a typo'd flag
  fails immediately rather than at the next scheduled run.
- New `gmail_ingest/scheduling.py`: command-construction kept pure/testable, separate from the
  `subprocess`-calling execution.
- Found and fixed two real bugs along the way, both verified against a real Windows Task Scheduler
  registration and a Linux container's crontab:
  - The original `-RepetitionDuration ([TimeSpan]::MaxValue)` (meant as "run indefinitely") produces a
    duration value Task Scheduler's XML schema rejects outright. `register_task.ps1` had never actually been
    run end-to-end before, so this had never been caught. Now uses a 10-year duration instead.
  - cron's minute/hour/day fields are independent modulo-wheels (minutes wrap at 60), not a true
    elapsed-time interval — `*/1440` (attempting "once a day" as a minute step) is simply invalid and cron
    silently misbehaves rather than erroring. `--interval-minutes` now translates to proper cron fields (e.g.
    `0 0 */1 * *` for 1440) and is rejected up front with a clear error for values that don't divide evenly.

`import`, `stats`, and `export` also gained `--db <path>`, to point at a database other than the default
`gmail_index.db` — what makes the multi-job pattern above useful in the first place.

## v0.13.0
Released on 2026-08-19

**Bug fix:** `config.BASE_DIR` silently broke in the `v0.10.0` src-layout
migration — `config.py` moved one directory deeper (`gmail_ingest/` →
`src/gmail_ingest/`) without its `.parent.parent` chain being updated to
match, so `BASE_DIR` (and therefore `DB_PATH`/`CREDENTIALS_PATH`/
`TOKEN_PATH`/`LOG_DIR`) resolved to `src/` instead of the actual project
root. Caught while adding `--db` support (below) — no live database was
actually written to the wrong location (nothing had run a real
`import`/`stats` since the migration; the test suite's mocked `DB_PATH`
never exercised the real computation), but this would have broken the
very next real run. Added `tests/test_config.py` as a regression guard.

## v0.12.0
Released on 2026-08-19

Housekeeping, no code change: verified the full test suite and CLI
(`--version`, `help`) run correctly on Linux, in a `python:3.11-slim`
Docker container matching CI's Python version — confirmed the
pure-Python/pathlib design needed no changes. Updated README/CLAUDE.md's
framing accordingly: the app itself is cross-platform, only the
scheduling story (`register_task.ps1`) is currently Windows-only.

## v0.11.0
Released on 2026-08-19

`gmail-ingest --version` now works, printing the installed version read
live from package metadata (`importlib.metadata.version("gmail-ingest")`)
rather than a second hardcoded string — `pyproject.toml`'s `version` field
stays the only place it's actually written. (Deliberately not copying
`python-template-project`'s hand-synced `__version__` pattern, which is
exactly the kind of duplication that drifts.)

## v0.10.0
Released on 2026-08-19

Housekeeping, no behavior change: moved the package from a flat
`gmail_ingest/` at the repo root to `src/gmail_ingest/` (src layout),
matching `python-template-project`'s convention. `pyproject.toml` no
longer needs an explicit `[tool.setuptools.packages.find]` — setuptools
auto-detects the src layout, same as the template. Also added the
template's CI "build" step (`python -m build`, after tests) to
`.github/workflows/ci.yml`, verified locally.

## v0.9.0
Released on 2026-08-19

**Breaking change:** the `update` subcommand is renamed to `import` —
`python -m gmail_ingest.cli update` is now `python -m gmail_ingest.cli
import` (same for the `gmail-ingest` console script). `register_task.ps1`
is updated to match; anything else invoking the old name needs to switch.

Also: `import`, `stats`, and `export` all gained `--filter "..."`, using
a Gmail-like syntax (`label:`, `from:`, `to:`, `cc:`, `bcc:`, `subject:`,
`after:YYYY/MM/DD`, `before:YYYY/MM/DD`, `has:attachment`, bare
words/`"quoted phrases"`, all ANDed). The three subcommands interpret it
differently by design:

- `import --filter` passes the string straight through to Gmail's own
  search (full Gmail grammar, not just the subset above) and runs a
  filtered full listing instead of incremental sync — `sync_state` is
  deliberately left untouched, so it can't interfere with regular
  unfiltered `import` runs. Since upserts never delete, a sequence of
  differently-filtered imports accumulates a database containing the
  union of everything matched so far — a practical way to build up a
  database covering only the parts of your mailbox you care about.
- `stats --filter` and `export --filter` are evaluated locally (new
  `gmail_ingest/filters.py`, with its own test suite) against columns
  already in the database, supporting only the token subset above — an
  unrecognized `key:` prefix is a hard error, not silently ignored.
  `from:`/`to:`/`cc:`/`bcc:` match against `message_addresses` (address
  or name substring); `label:` is an exact case-insensitive label-name
  match; `after:`/`before:` compare `internal_date_ms` and never match a
  `NULL` row.

See `README.md`'s new "Filtering" section for full details.

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
