# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`mail-utils` polls a single personal Gmail account on a schedule and indexes new messages into a local SQLite
database (`data/mails.db` by default), using the Gmail API and OAuth 2.0. It's a personal, single-user tool —
not a package/library, no server, no multi-tenant concerns, though it does support authorizing and switching
between more than one named Gmail account (see `prepare-gmail-account`/`--account` below) for testing
against a disposable mailbox before ever pointing a command at production.

**Read-only is the default, not an absolute rule — but any exception is a deliberate, narrowly-scoped
decision, never an oversight.** Every command except one only ever requests the `gmail.readonly` scope
(`config.py`'s `SCOPES`) and never sends, labels, or deletes anything. The one exception is `store-in-gmail`
(see `docs/reverse-import-plan.md` for the feasibility study behind it, and `docs/cli-spec.md`'s
`store-in-gmail` entry for the command itself): it writes mail-utils messages back into a live Gmail
mailbox via `users.messages.import`, sourced either from a `mail-utils export --format eml` directory
or directly from the local database, and requests the additional `gmail.insert`/`gmail.labels` scopes
(`config.py`'s `STORE_IN_GMAIL_SCOPES`) only
when actually invoked — every other command's credential request is unaffected. Don't add further
write/send/delete capability without explicitly discussing it first.

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
  `import [<source_path>]` (smart unified import with auto-detection for Outlook PST, Thunderbird backup/profile, or Gmail fallback),
  `import-gmail` (Gmail API sync), `prepare-gmail-account <name>` (interactively authorizes a Gmail account
  and saves its token as `<name>-account.json`, for later selection via `--account` — see Architecture below),
  `check-gmail-account <name>` (read-only: reports the authenticated email, granted OAuth scopes, and
  mailbox size for an account, without changing anything — useful for confirming which account a name
  actually maps to after setting up several),
  `import-pst <path>` (Outlook .pst import, alias `import-outlook`),
  `import-thunderbird <path>` (Thunderbird .pcv/profile import, alias `import-pcv`),
  `search <query>` (SQLite FTS5 full-text search), `stats` (offline summary),
  `export <output_dir>` (offline markdown/EML dump via `--format md|eml`),
  `store-in-gmail [<source_dir>]` (writes mail into a live Gmail mailbox — the one write-capable command,
  see the read-only note above and docs/cli-spec.md's `store-in-gmail` entry; source is a `mail-utils export --format eml`
  directory, or the local database directly if `source_dir` is omitted),
  `schedule`/`unschedule` (recurring job registration — Windows Task Scheduler or cron, dispatched by `platform.system()`;
  `mail-utils schedule --job-name <name> --interval-minutes N -- import|import-gmail|export [flags...]`, see docs/cli-spec.md for
  scheduling details), `version` / `--version` (reads live package metadata), `help` / `-h` / `--help` (usage and exit codes).
- `import`/`import-gmail`/`import-pst`/`import-thunderbird`/`search`/`stats`/`export`/`store-in-gmail` accept `--db <dir>` to point at a
  directory other than the default `data/` — the database (`<dir>/mails.db`) and attachment cache (`<dir>/attachments/`) both live inside
  it, scoped together. `import`/`import-gmail`/`store-in-gmail` also accept `--account <name>` to select which authorized Gmail account
  to use (a bare name resolves to `data/<name>-account.json`, a path is used verbatim; omitted falls back to `data/default-account.json`
  if present) — decoupled from `--db`, so any account can pair with any data directory. `import`/`import-gmail`/`import-pst`/
  `import-thunderbird` accept `-r`/`--recursive` to import nested email attachments. `import`/`import-gmail`/`stats`/`export`/
  `store-in-gmail` also accept `--filter "..."` (see docs/cli-spec.md). `store-in-gmail` additionally accepts `--dry-run` (preview
  without contacting Gmail or requesting credentials) and `--max-messages N` (cap this run's writes — pairs with the persistent
  `gmail_store_state` table to make an interrupted or capped run resumable by simply rerunning the same command).
- Run the test suite: `.venv\Scripts\python -m pytest`; lint/format: `.venv\Scripts\ruff check .` /
  `.venv\Scripts\ruff format .` (line-length 132, `[tool.ruff]` in `pyproject.toml`; CI runs both plus
  `pytest` plus `python -m build`).

Dependencies are declared once, in `pyproject.toml` — there is no separate `requirements.txt` to keep in sync.

## Architecture

Modules and packages under `src/mail_utils/` (src layout — see README's "Project layout" for the rationale):

- **`outlook/`** — read-only Outlook `.pst` parser (NDB/LTP layers) with zero external dependencies.
- **`thunderbird/`** — read-only Thunderbird archive (`*.pcv`, `*.zip`, profile folders) parser: `archive.py`
  (Mbox store discovery and extraction), `tree.py` (`.sbd` hierarchy walk and label id derivation), and
  `messages.py` (Mbox parsing, MIME extraction, fallback date handling).
- **`config.py`** — `DATA_DIR` (`BASE_DIR / "data"`, gitignored in full) holding the shared app credential
  file (`APP_CREDENTIALS_PATH`, `data/google-cloud-mail-utils-app-credentials.json` — the OAuth client
  secret identifying the mail-utils application itself, not any one Google account) plus a separate
  top-level, also gitignored, `LOG_DIR` (`BASE_DIR / "logs"`, `logs/mail-utils.log`) and the OAuth `SCOPES`
  list (read-only, used by every command but one). `STORE_IN_GMAIL_SCOPES` extends `SCOPES` with
  `gmail.insert`/`gmail.labels`, requested only by `store-in-gmail`. Accounts and data storage are
  deliberately decoupled and resolved by two independent pure functions rather than fixed constants:
  `resolve_account_path(account)` (a bare name → `data/<name>-account.json`; a value with a path separator
  or `.json` extension → used verbatim; `None` → `data/default-account.json`) and `resolve_db_dir(db)` (the
  `--db` directory, defaulting to `DATA_DIR`), paired with `db_path_for`/`attachments_dir_for` which append
  the fixed `DB_FILENAME`/`ATTACHMENTS_DIRNAME` (`mails.db`/`attachments`) onto whatever directory
  `resolve_db_dir` returned. Single source of truth for all of this; nothing else in the codebase hardcodes
  a path.
- **`auth.py`** — `get_credentials(account_path, scopes=None, app_credentials_path=APP_CREDENTIALS_PATH)`:
  loads/refreshes the given account's token file silently when possible, otherwise runs the one-time
  interactive `InstalledAppFlow` browser consent using the shared app credential file, then writes the
  result back to `account_path` (creating its parent directory if needed). Every caller must say which
  account it means (`config.resolve_account_path`'s result) — there is no implicit default inside `auth.py`
  itself. `scopes` defaults to `SCOPES`; `store-in-gmail` and `prepare-gmail-account --with-write` pass
  `STORE_IN_GMAIL_SCOPES` instead, which re-triggers consent if the cached token doesn't already cover the
  broader set (checked via `creds.scopes`) — every other caller is unaffected since it never asks for more
  than the cached read-only token already grants. A refresh attempt that raises `RefreshError` (the cached
  refresh token was revoked or expired server-side — Google expires unused ones after 6 months, or the
  user can revoke access directly) is caught and treated the same as no cached token at all, falling
  through to a fresh interactive consent rather than crashing — found while manually verifying
  `check-gmail-account` against a real stale account; `tests/test_auth.py` has the regression test.
- **`attachment_store.py`** — content-addressed attachment byte storage. `configure(attachments_dir)` sets
  a module-level directory (called once per CLI run, from `cli.py::_resolve_db_path`, right after `--db` is
  resolved — see below); `save`/`read`/`path_for` operate under whatever directory was last configured,
  raising `RuntimeError` if used before `configure()` is ever called. Deliberately module-level state rather
  than a parameter threaded through every call site, since a single CLI invocation only ever needs one
  attachments directory.
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
  `cli.py`'s `export`) can tell which case they're in without re-deriving it. `import_message` (writes a raw
  RFC 5322 message via `users.messages.import`, base64url-encoding it, with `internalDateSource="dateHeader"`
  and `neverMarkSpam=True`) and `create_label` (`users.labels.create`) are the write-side counterparts used
  only by `store-in-gmail`. See `README.md`'s "Database contents" section for the exact, currently-documented
  behavior (and known gaps — `TODO.md` tracks fixing them).
- **`db.py`** — SQLite schema and upsert helpers. `messages` (upserted by Gmail's message `id`, so
  reruns never duplicate), `sync_state` (currently just `last_history_id`), `labels` (id -> display name,
  refreshed in full every run), `message_addresses` and `attachments` (each one row per message/role/address or
  message/attachment, replaced in full for a given message on every rerun via `upsert_addresses`/
  `upsert_attachments` — delete-then-insert, not an upsert, since Gmail messages are immutable so there's
  nothing to merge), and `gmail_store_state` (`message_id` -> the Gmail-assigned `gmail_id` it was stored as,
  via `is_stored_in_gmail`/`mark_stored_in_gmail`) so `store-in-gmail` reruns skip messages already stored
  instead of duplicating them — this is also what makes an interrupted or `--max-messages`-capped run
  resumable: rerunning the same command just picks up where the last one left off.
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
  switches to a filtered full listing that skips `sync_state` entirely, see `filters.py` above),
  `prepare-gmail-account <name>` (resolves the target account path the same way `--account` does, requires
  the app credential file to already exist, runs `get_credentials` directly to drive consent, defaults to
  read-only `SCOPES` with `--with-write` requesting `STORE_IN_GMAIL_SCOPES` instead, and prints the
  authenticated address via `get_profile` for confirmation), `check-gmail-account <name>` (a read-only
  counterpart - resolves the account path the same way, reports "no account file found" instead of
  attempting anything if it's missing, otherwise calls `get_credentials` with the default read-only
  `scopes` - which can't itself widen an account's permissions, and silently refreshes an expired token
  exactly like every other command - then prints the authenticated email, `creds.scopes` (the token's
  actual granted permissions, not just what was requested), and `get_profile`'s `messagesTotal`/
  `threadsTotal`), `stats`
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
  alias for `--version`, handled the same way in `main()`; also accepts its own `--verbose`), and `store-in-gmail [<source_dir>]`
  (the one write-capable command — candidates come from `_eml_tree_candidates` (walks `.eml` files under
  `source_dir`, sorted by path, skipping any without an `X-Mail-Utils-ID` header) when `source_dir` is
  given, or from `_db_candidates` (reads the local database directly, ordered by `id`, building the same
  RFC 5322 shape via `_build_eml_message` that `export --format eml` would have written) when it's omitted;
  either way, candidates already present in `gmail_store_state` are skipped, `--filter` (same grammar as
  `stats`/`export`, via `_compute_matching_ids`) can further restrict them, and `--max-messages` stops the
  run early once that many have been stored — safe to do since `gmail_store_state` makes rerunning the same
  command pick up exactly where it left off. Every message stored also gets one label unique to that run
  (`mail-utils-store-in-gmail-<UTC timestamp>`, resolved/created lazily on the run's first actual store via
  `_get_or_start_gmail_store_run_label`/`_resolve_label_ids`). That label name is itself persisted in
  `sync_state` (`_GMAIL_STORE_RUN_LABEL_KEY`) the moment it's minted and only cleared once a run goes
  through every candidate without being cut short by `--max-messages` (`_finish_gmail_store_run`) — so a
  capped run, or one interrupted outright (crash, Ctrl-C), continues under the *same* timestamp label when
  rerun instead of scattering its messages across several differently-timestamped labels; only a run that
  actually finished starts a fresh label next time. `_throttle_gmail_store` paces `messages.import` calls
  under Gmail's per-user quota (25 units/call, ~10 calls/sec ceiling) and `_gmail_call_with_backoff` retries
  with exponential backoff on a 429/rate-limited 403 so a transient burst doesn't abort the run. Before any
  write, the authenticated account's own address is logged (`Target account: ...`, via `get_profile`) as a
  guard against running against the wrong Google account by mistake. Labels are
  resolved to IDs via `_resolve_label_ids`, creating any that don't already exist. `--dry-run` runs the same
  candidate/skip/filter logic without requesting credentials or calling the API, so it never touches
  `gmail_store_state`, only previews what a real run would do — and every stored message, plus the run's
  final summary, is logged explicitly (`Stored <id> as Gmail message <new-id>` per message; the end-of-run
  line always states the last message successfully stored). `import`/`stats`/`export`/`store-in-gmail`
  all take `--db <dir>` (via `_resolve_db_path`, which resolves `<dir>/mails.db` via `config.resolve_db_dir`/
  `db_path_for` and, as a side effect, calls `attachment_store.configure` on `<dir>/attachments` — every one
  of its 7 call sites across `cli.py` gets a correctly-scoped attachment store for free without threading the
  directory through separately) to override the default `data/`. `import`/`import-gmail`/`store-in-gmail`
  also take `--account <name>` (via `_resolve_account_path`/`config.resolve_account_path`) to select which
  authorized account's token file `get_credentials` uses. `stats --filter`/
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
`data/mails.db` needs an explicit `ALTER TABLE`. See `_ensure_column`/`init_db` in `db.py` for the
pattern to extend.

`config.py`'s `BASE_DIR = Path(__file__).resolve().parent.parent.parent` is relative to `config.py`'s own
location (`src/mail_utils/config.py` → up three levels → project root); `DATA_DIR = BASE_DIR / "data"` and
every other path in `config.py` are derived from it. Any future move of `config.py` itself, or another change
to the directory depth between it and the project root, needs that `.parent` chain recounted to match — it
broke silently in exactly this way during the `v0.10.0` src-layout migration (fixed in `v0.13.0`), because the
test suite at the time always monkeypatched a fixed `DB_PATH` constant directly rather than exercising the
real computation, so nothing caught it until a real run would have. `tests/test_config.py` guards against a
repeat by exercising `resolve_db_dir`/`db_path_for`/`resolve_account_path` against the real `DATA_DIR`.

## Conventions

- Everything under `data/` (the app credential file, account files, `mails.db`, `attachments/`) plus the
  top-level `logs/` is gitignored in full as secrets/generated data — never commit any of it, and never add
  code that logs its contents at INFO level or above.
- Keep `README.md`'s "Database contents" section and `docs/devops.md`'s "Gmail Account Setup" section in
  sync with the code — the latter is written to be detailed enough that a first-time setup doesn't need
  external guidance (see its Google Cloud Console walkthrough, expanded specifically because the console's
  own UI/naming tends to drift from whatever the last short version assumed).
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
- This project complies with the [cross-project development guidelines](https://github.com/gpellicciotta/dev-guidelines) (task coordination, coding guidelines, CLI standards).
- Any change that alters what's stored (new/changed/removed column, changed parsing behavior) must update both
  `README.md`'s "Database contents" tables and, if it's a behavior change to already-synced data, note whether
  existing rows in someone's `mails.db` need a resync to pick it up (they generally won't be
  auto-migrated — there's no schema migration mechanism here, only `CREATE TABLE IF NOT EXISTS`).

