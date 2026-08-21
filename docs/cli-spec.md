# CLI Specification

This document defines the command-line interface, subcommands, options, exit codes, and output formatting for `mail-utils`.

---

## 1. Global Invocations & Flags

```powershell
mail-utils [--version] [--verbose] [<command>] [<args>...]
```

### Global Flags
- `--version`: Print package version and copyright notice:
  ```
  mail-utils 2.2.1 - Copyright (c) Giovanni Pellicciotta
  ```
  With `--verbose`, also prints the matching release entry from `CHANGELOG.md`.
- `help` (or no command): Print summary help for all subcommands. With `--verbose`, prints full `--help` for every subcommand.
- `version`: Subcommand alias for `--version`.

---

## 2. Subcommand Specifications

### 2.1 `import`
Unified, smart import command. Automatically identifies the source format if a path is provided, or synchronizes with Gmail if no path is given.

```powershell
mail-utils import [<source_path>] [--filter <query>] [-r|--recursive] [--db <path>]
```

- `<source_path>`: Optional positional path to an Outlook `.pst` file, Thunderbird archive (`.pcv`, `.zip`), or Thunderbird profile folder.
  - If omitted: checks for Gmail credentials in `data/` and runs a Gmail sync.
  - If an Outlook PST is provided: imports Outlook folders and messages.
  - If a Thunderbird backup/directory is provided: imports Thunderbird folders and messages.
  - If an unsupported or single-message format (e.g. `.eml`, `.msg`, `.mbox`) is provided: reports a descriptive error explaining supported options.
- `--filter <query>`: Server-side search filter when syncing from Gmail.
- `-r`, `--recursive`: Recursively index attached email messages (`message/rfc822` / `.eml`).
- `--db <path>`: Target SQLite database file (default: `data/gmail.db`).

---

### 2.2 `import-gmail`
Dedicated subcommand to ingest new messages from Gmail via the Gmail API.

```powershell
mail-utils import-gmail [--filter <query>] [-r|--recursive] [--db <path>]
```

- `--filter <query>`: Server-side search filter (Gmail `q` syntax). Forces a filtered listing without updating incremental sync state.
- `-r`, `--recursive`: Recursively index attached email messages.
- `--db <path>`: Target SQLite database file.

---

### 2.3 `import-pst` (alias: `import-outlook`)
Ingests messages and folder hierarchies from a Microsoft Outlook `.pst` file.

```powershell
mail-utils import-pst <pst_path> [-r|--recursive] [--db <path>]
mail-utils import-outlook <pst_path> [-r|--recursive] [--db <path>]
```

- `<pst_path>`: Positional path to the Unicode `.pst` archive.
- `-r`, `--recursive`: Recursively index attached email messages.
- `--db <path>`: Target SQLite database file.

---

### 2.4 `import-thunderbird` (alias: `import-pcv`)
Ingests messages from a Mozilla Thunderbird backup (`.pcv`, `.zip`) or profile directory.

```powershell
mail-utils import-thunderbird <archive_path> [-r|--recursive] [--db <path>]
mail-utils import-pcv <archive_path> [-r|--recursive] [--db <path>]
```

- `<archive_path>`: Positional path to `.pcv`/`.zip` file or Thunderbird profile folder.
- `-r`, `--recursive`: Recursively index attached email messages.
- `--db <path>`: Target SQLite database file.

---

### 2.5 `search`
Full-text searches indexed messages using SQLite `FTS5`.

```powershell
mail-utils search <query> [-n|--limit <N>] [--db <path>]
```

- `<query>`: Search string. Supports boolean operators (`AND`, `OR`, `NOT`) and prefix matching (`term*`).
- `-n`, `--limit <N>`: Maximum number of results to display (default: `20`).
- `--db <path>`: Database to search.

---

### 2.6 `stats`
Displays offline summary statistics from the local database.

```powershell
mail-utils stats [--filter <filter>] [--db <path>]
```

- `--filter <filter>`: Local filter expression (e.g. `label:Work from:jane has:attachment`).
- `--db <path>`: SQLite database to query.

---

### 2.7 `export`
Exports messages to disk as Markdown (`.md`) or standard MIME (`.eml`) files.

```powershell
mail-utils export <output_dir> [-f|--format {md,eml}] [--filter <filter>] [--db <path>]
```

- `<output_dir>`: Directory where exported files will be written into `<YYYY>/<MM>/` subfolders.
- `-f`, `--format {md,eml}`: Export format (`md` default, or `eml`).
- `--filter <filter>`: Local filter expression to restrict export scope.
- `--db <path>`: Database to read from.

---

Registers and manages recurring scheduled tasks (Windows Task Scheduler or cron).

```powershell
mail-utils schedule [--job-name <name>] [--interval-minutes <N>] -- <command>
mail-utils schedule --list
mail-utils unschedule [--job-name <name>]
```

- `--job-name <name>`: Task identifier (default: `"default"`).
- `--interval-minutes <N>`: Execution interval in minutes (default: `30`).
- `--list`: List currently active scheduled jobs.
- `-- <command>`: The inner command to execute (e.g. `import` or `export /backup/dir`).

---

## 3. Local Filter Grammar Reference

The local `--filter` syntax used by `stats` and `export` supports:
- `label:<name>` (e.g. `label:INBOX`, `label:"Work/Projects"`)
- `from:<address_or_domain>`
- `to:<address_or_domain>`
- `cc:<address_or_domain>`
- `bcc:<address_or_domain>`
- `subject:<word_or_phrase>`
- `after:YYYY/MM/DD`
- `before:YYYY/MM/DD`
- `has:attachment`
- Bare words / `"quoted phrases"` (matches subject or body substring).

---

## 4. Output & Logging Conventions

- **Console Output**: Clean, human-readable text without timestamp or `[INFO]` log prefixes.
- **Log File (`logs/mail-utils.log`)**: Full dual-logged output with UTC timestamps and log levels. Multi-line records are indented to match the header width.
- **Start / End Lifecycle**:
  - `Mail Utils <version> operation started: <operation>`
  - `Mail Utils <version> operation ended in <elapsed>: <details>`

