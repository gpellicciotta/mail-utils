# Changelog

## vNext
- Added `--format {md,eml}` (`-f`) option to `mail-utils export` to export messages as standard RFC 5322 MIME `.eml` files in addition to Markdown `.md` files (defaults to `md`).
- Added `docs/emails-formats.md` and `docs/eml-export-support-plan.md`.
- Renamed `RELEASES.md` to the more standard `CHANGELOG.md`

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

