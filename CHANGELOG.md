# Versioned Changes

A summarized overview of all changes, per version of this project.

> Entries will be added in reverse chronological order, so with the most recent at the top.
> 
> Status codes used are:
> - `[in development]` - actively being developed
> - `[{{date}}]` - frozen/finalized on {{date}}
> - `[released: {{date}}]` - released to package manager or production on {{date}}
> - `[broken]` - considered broken and not be used

---

### vNext
- BackEnd: Capture attachments and inline images carrying no filename (but having a Content-ID or explicitly marked as attachments) across all sources.
- BackEnd: Capture and restore each message's HTML body alongside its plain-text one, across all import sources.
- BackEnd: Preserve inline-image Content-IDs through export/store-in-gmail so `cid:` image references keep resolving.
- BackEnd: Add `check-gmail-account`, reporting an account's authenticated email, granted scopes, and mailbox size.
- BackEnd: Fix a crash when a cached Gmail token's refresh token has been revoked or expired; falls back to re-consent instead.
- DevEx: Have gmail-roundtrip-test.py's cleanup action also delete the label, not just trash its messages.
- Docs: Fix stale claims that attachment content is never captured/stored, pre-dating opt-in `--with-attachments`.

## v3.0.0 [2026-08-28]
- BackEnd: Add `prepare-gmail-account` and `--account` to authorize and select between multiple named Gmail accounts.
- BackEnd: [breaking] Rename the default database file to `mails.db` and change `--db` to a directory holding it plus the attachment cache.
- BackEnd: [breaking] Rename the shared OAuth client credential file to `google-cloud-mail-utils-app-credentials.json`.
- Docs: Add a feasibility study for restoring exported mail back into Gmail, Outlook, and Thunderbird.
- BackEnd: Add opt-in `store-in-gmail` command to write exported or indexed mail into a live Gmail mailbox.
- DevEx: Rename `scripts/generate_sample_pst.py` to `scripts/generate-sample-pst.py` for naming-convention compliance.
- DevEx: Replace `setup.ps1` with cross-platform `scripts/bootstrap-dev-environment.py`.
- BackEnd: Fix crash on a fresh checkout when `import-pst`/`import-thunderbird`/`store-in-gmail` run before `data/` exists.
- DevEx: Give every `scripts/` tool a `version`/`help` action and `-v`/`-h` options matching `mail-utils`'s own CLI format.
- BackEnd: Add `authors`/`classifiers` to `pyproject.toml` package metadata.
- Docs: Fix stale Python-version, CI-matrix, and third-party-dependency claims, and stray numbered/skipped headings across the doc set.
- DevEx: Scope `pytest` to `tests/` so it no longer collides with test files in sibling task worktrees under `work/`.
- BackEnd: Add opt-in `--with-attachments` to capture real attachment content, round-tripped by `export` and `store-in-gmail`.
- BackEnd: Fix `store-in-gmail` silently reusing a cached read-only token instead of requesting its required write scopes.
- BackEnd: Have `store-in-gmail` log the target account's address before writing, to catch a wrong-account mistake early.
- BackEnd: Fix a Subject header round-trip bug that grew whitespace around encoded-word runs on repeated export/store.
- DevEx: Add scripts/gmail-roundtrip-test.py, a reusable seed/compare/cleanup tool for verifying store-in-gmail fidelity against a real account.

## v2.3.0 [released: 2026-08-24]
- Aligned project with latest development guidelines (https://github.com/gpellicciotta/dev-guidelines).
- Renamed `LICENSE` to `LICENSE.md`.
- Restructured `TODO.md` with milestone sections (`## Next Milestone`, `### Backlog`) per coordinating work guidelines, and added `work/` to `.gitignore`.
- Updated mandatory documentation (`docs/requirements.md`, `docs/devops.md`, `docs/index.md`, `README.md`, `CLAUDE.md`).
- Standardized CLI output format and exit codes across commands:
  - Formatted `version` and `--version` output to `{name} v{version} - {copyright}` with exit code 0.
  - Standardized multi-line help message format for `help`, `-h`, `--help`, and no-subcommand invocation with version banner, short description, command usage, and exit codes explanation.
- Updated test suite (`tests/test_cli.py`) to verify version format, multi-line help, exit codes, and mandatory documentation structure.

## v2.2.1 [released: 2026-08-21]
- Fixed POSIX / GitHub Actions CI test failure in `test_run_import_no_args_without_credentials_reports_error` by properly monkeypatching module configuration attributes instead of read-only `Path` instance methods.

## v2.2.0 [released: 2026-08-21]
- Standardized output and logging across all commands (`import`, `import-pst`, `import-thunderbird`, `stats`, `export`, `search`, `schedule`, `unschedule`).
- Console output prints clean human-readable lines without timestamp or loglevel prefixes; log file (`logs/mail-utils.log`) captures all output with UTC timestamp prefixes.
- Multi-line log records in `logs/mail-utils.log` automatically indent subsequent lines to match the first line's header width for clean alignment.
- Standardized operation boundaries across all commands:
  - `Mail Utils <version> operation started: <operation>`
  - `Mail Utils <version> operation ended in <elapsed>: <details>`
- Added `mail-utils search "<query>"` subcommand powered by SQLite `FTS5` full-text indexing, featuring BM25 ranking, snippet matching with excerpts, boolean syntax (`AND`, `OR`, `NOT`, prefix matches), and `--limit` / `--db` options.
- Added `-r` / `--recursive` flag to all import commands (`import`, `import-gmail`, `import-pst`, `import-thunderbird`) to recursively extract and index nested email attachments (`message/rfc822` / `.eml`).
- Renamed direct Gmail API import command to `import-gmail` for naming consistency across sources (`import-gmail`, `import-pst`/`import-outlook`, `import-thunderbird`/`import-pcv`).
- Re-architected `mail-utils import [<source_path>]` as an intelligent unified importer: automatically detects Outlook PST, Thunderbird backups (`.pcv`/`.zip`), and profile folders, or falls back to Gmail API sync when no path is provided (with friendly format identification and errors for unsupported formats like `.eml`, `.msg`, `.mbox`).
- Renamed internal package `mail_utils.pst` to `mail_utils.outlook` for architectural consistency with `mail_utils.thunderbird`, adding `import-outlook` as a CLI alias for `import-pst`.
- Overhauled and restructured project documentation: added `docs/requirements.md` (goals, functional & technical requirements), `docs/cli-spec.md` (full CLI specification and filter grammar), `docs/devops.md` (setup, testing, build, packaging, and CI/CD guide), updated `docs/tutorial.md`, and streamlined `README.md`.
- Added committed, anonymized sample fixtures for Outlook PST (`tests/fixtures/sample.pst`) and Thunderbird (`tests/fixtures/sample.pcv`) with reproducible fixture generators, enabling unconditional end-to-end integration testing in CI without external dependencies.

## v2.1.0 [released: 2026-08-21]
- Added `import-thunderbird <path>` command (with alias `import-pcv`) to import Mozilla Thunderbird archives (`*.pcv`, `*.zip`) and profile directories into the local SQLite database.
- Added `thunderbird/` package implementing Mbox stream parsing, `.sbd` directory hierarchy resolution, MIME body/attachment decoding, and envelope delimiter fallback date handling.
- Messages from Thunderbird are prefixed with `thunderbird:`.
- Added `--format {md,eml}` (`-f`) option to `mail-utils export` to export messages as standard RFC 5322 MIME `.eml` files in addition to Markdown `.md` files (defaults to `md`).
- Added `docs/emails-formats.md`, `docs/eml-export-support-plan.md`, and `docs/thunderbird-import-plan.md`.
- Renamed `RELEASES.md` to the more standard `CHANGELOG.md`.

## v2.0.0 [released: 2026-08-20]
- **Breaking change:** `messages.id` (and matching `message_addresses`/`attachments.message_id`) is now prefixed by source (`gmail:` or `outlook:`). Existing databases require migration via `python scripts/migrate-gmail-id-prefix.py --apply`.
- Added `import-pst <path>` command to import Outlook `.pst` archives using a built-in `[MS-PST]` parser (`pst/` package).
- PST folders map to SQLite `labels` and `messages.label_ids`, enabling `label:` filtering across both sources.

## v1.0.0 [released: 2026-08-19]
- First stable release.
- Added `version` subcommand (alias for `--version`, supports `--verbose`).
- Added `--verbose` flag to `help` and no-subcommand invocation to display full help for all subcommands.
- Formatted `--version` output onto a single line (`mail-utils <version> - Copyright (c) Giovanni Pellicciotta`).

## v0.19.0 [released: 2026-08-19]
- Consolidated secrets and database storage into `data/` (`data/credentials.json`, `data/token.json`, `data/gmail.db`).
- Renamed default database to `data/gmail.db` and log file to `logs/mail-utils.log`.
- Switched console and file logging to UTC timestamps.
- Updated `setup.ps1` to create the `data/` directory.

## v0.18.0 [released: 2026-08-19]
- Added short description to `help` and no-subcommand output.
- Added `--version --verbose` support to print the current version's release notes from disk.
- Added `docs/tutorial.md` and renamed `docs/README.md` to `docs/index.md`.
- Aligned column widths across `stats` summary sections.
- Changed `label:` filter in `stats`/`export` to substring matching.

## v0.17.0 [released: 2026-08-19]
- Added `build` package to `dev` optional dependencies in `pyproject.toml`.
- Added `.editorconfig` (4-space indent, UTF-8, 132-char lines).
- Added `docs/` folder structure.
- Added `.pytest_cache/` and `.ruff_cache/` to `.gitignore`.
- Added `setup.ps1` bootstrap script.

## v0.16.0 [released: 2026-08-19]
- **Breaking change:** Renamed package from `gmail-ingest` to `mail-utils` (package, CLI script, log files, scheduled tasks, and cron comments). Existing scheduled jobs must be re-registered.
- Moved repository to `https://github.com/gpellicciotta/mail-utils`.

## v0.15.0 [released: 2026-08-19]
- Added `ruff` linter and formatter (`line-length = 132`), updated CI workflow.
- Standardized CLI invocations to `mail-utils <command>` across documentation.
- Reflowed documentation to 132 characters.

## v0.14.0 [released: 2026-08-19]
- **Breaking change:** Replaced `register_task.ps1` with cross-platform `schedule`/`unschedule` subcommands (Windows Task Scheduler / cron via `scheduling.py`).
- Added `--db <path>` option to `import`, `stats`, and `export` to support multiple independent databases.
- Added named jobs (`--job-name`) and command validation for scheduled tasks.
- Fixed Task Scheduler duration limits (10-year limit) and cron modulo scheduling calculation.

## v0.13.0 [released: 2026-08-19]
- **Bug fix:** Fixed `config.BASE_DIR` resolution following the src-layout migration.
- Added `tests/test_config.py` regression tests.

## v0.12.0 [released: 2026-08-19]
- Verified cross-platform compatibility in `python:3.11-slim` Linux Docker container.
- Updated documentation regarding cross-platform support.

## v0.11.0 [released: 2026-08-19]
- Added `--version` flag dynamically reading package metadata via `importlib.metadata`.

## v0.10.0 [released: 2026-08-19]
- Migrated codebase to `src/` layout (`src/mail_utils/`).
- Added build step (`python -m build`) to CI workflow.

## v0.9.0 [released: 2026-08-19]
- **Breaking change:** Renamed `update` subcommand to `import`.
- Added `--filter` option to `import` (passed directly to Gmail API search) and to `stats`/`export` (evaluated locally via `filters.py`).

## v0.8.0 [released: 2026-08-19]
- Added `export <output_dir>` command to dump messages into date-bucketed Markdown files with YAML frontmatter.
- Added `body_mime_type` column to `messages` table to differentiate plain text vs HTML bodies.
- Added `PyYAML` dependency.

## v0.7.0 [released: 2026-08-19]
- Moved release notes and TODOs to root `CHANGELOG.md` and `TODO.md`.
- Added GitHub Actions CI workflow (`.github/workflows/ci.yml`).

## v0.6.0 [released: 2026-08-19]
- Added `internal_date_ms` column to `messages` table capturing Gmail's internal timestamp.
- Added automatic column migration via `db._ensure_column`.

## v0.5.0 [released: 2026-08-19]
- **Breaking change:** Replaced `main.py` and `stats.py` with unified `cli.py` entry point (`import`, `stats`, `help`).
- Added console script entry point in `pyproject.toml`.
- Added `tests/test_cli.py` test suite.

## v0.4.0 [released: 2026-08-19]
- Added `attachments` table to store attachment metadata (`message_id`, `attachment_id`, `filename`, `mime_type`, `size`).
- Added attachment summary statistics to `stats` command.

## v0.3.0 [released: 2026-08-19]
- Added `message_addresses` table to store normalized From/To/Cc/Bcc addresses.
- Added recipient and sender breakdown statistics to `stats` command.

## v0.2.0 [released: 2026-08-19]
- Added `cc` and `bcc` columns to `messages` table.

## v0.1.0 [released: 2026-08-19]
- Initial working release.
- Added Google OAuth 2.0 Installed App authentication flow (`auth.py`).
- Added full initial sync and incremental sync via Gmail History API (`gmail_client.py`).
- Added SQLite database storage (`messages`, `sync_state`, `labels` tables in `db.py`).
- Added `stats` reporting command.
- Added `register_task.ps1` for Windows Task Scheduler registration.
- Added packaging setup via `pyproject.toml` and unit tests in `tests/`.

