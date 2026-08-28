# CLI Specification

This document defines the command-line interface, subcommands, options, exit codes, and output formatting for `mail-utils`.

---

## Global Invocations & Flags

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

## Subcommand Specifications

### `import`
Unified, smart import command. Automatically identifies the source format if a path is provided, or synchronizes with Gmail if no path is given.

```powershell
mail-utils import [<source_path>] [--filter <query>] [-r|--recursive] [--with-attachments] [--db <path>]
```

- `<source_path>`: Optional positional path to an Outlook `.pst` file, Thunderbird archive (`.pcv`, `.zip`), or Thunderbird profile folder.
  - If omitted: checks for Gmail credentials in `data/` and runs a Gmail sync.
  - If an Outlook PST is provided: imports Outlook folders and messages.
  - If a Thunderbird backup/directory is provided: imports Thunderbird folders and messages.
  - If an unsupported or single-message format (e.g. `.eml`, `.msg`, `.mbox`) is provided: reports a descriptive error explaining supported options.
- `--filter <query>`: Server-side search filter when syncing from Gmail.
- `-r`, `--recursive`: Recursively index attached email messages (`message/rfc822` / `.eml`).
- `--with-attachments`: Also fetch and store each attachment's actual content (not just
  filename/type/size) under `data/attachments/`, content-addressed by SHA-256. Off by default - adds
  an extra API call/read per attachment plus disk space. See README's "Database contents" section.
- `--db <path>`: Target SQLite database file (default: `data/gmail.db`).

---

### `import-gmail`
Dedicated subcommand to ingest new messages from Gmail via the Gmail API.

```powershell
mail-utils import-gmail [--filter <query>] [-r|--recursive] [--with-attachments] [--db <path>]
```

- `--filter <query>`: Server-side search filter (Gmail `q` syntax). Forces a filtered listing without updating incremental sync state.
- `-r`, `--recursive`: Recursively index attached email messages.
- `--with-attachments`: Also fetch and store each attachment's actual content (see `import` above).
- `--db <path>`: Target SQLite database file.

---

### `import-pst` (alias: `import-outlook`)
Ingests messages and folder hierarchies from a Microsoft Outlook `.pst` file.

```powershell
mail-utils import-pst <pst_path> [-r|--recursive] [--with-attachments] [--db <path>]
mail-utils import-outlook <pst_path> [-r|--recursive] [--with-attachments] [--db <path>]
```

- `<pst_path>`: Positional path to the Unicode `.pst` archive.
- `-r`, `--recursive`: Recursively index attached email messages.
- `--with-attachments`: Also fetch and store each attachment's actual content (see `import` above).
- `--db <path>`: Target SQLite database file.

---

### `import-thunderbird` (alias: `import-pcv`)
Ingests messages from a Mozilla Thunderbird backup (`.pcv`, `.zip`) or profile directory.

```powershell
mail-utils import-thunderbird <archive_path> [-r|--recursive] [--with-attachments] [--db <path>]
mail-utils import-pcv <archive_path> [-r|--recursive] [--with-attachments] [--db <path>]
```

- `<archive_path>`: Positional path to `.pcv`/`.zip` file or Thunderbird profile folder.
- `-r`, `--recursive`: Recursively index attached email messages.
- `--with-attachments`: Also fetch and store each attachment's actual content (see `import` above).
- `--db <path>`: Target SQLite database file.

---

### `search`
Full-text searches indexed messages using SQLite `FTS5`.

```powershell
mail-utils search <query> [-n|--limit <N>] [--db <path>]
```

- `<query>`: Search string. Supports boolean operators (`AND`, `OR`, `NOT`) and prefix matching (`term*`).
- `-n`, `--limit <N>`: Maximum number of results to display (default: `20`).
- `--db <path>`: Database to search.

---

### `stats`
Displays offline summary statistics from the local database.

```powershell
mail-utils stats [--filter <filter>] [--db <path>]
```

- `--filter <filter>`: Local filter expression (e.g. `label:Work from:jane has:attachment`).
- `--db <path>`: SQLite database to query.

---

### `export`
Exports messages to disk as Markdown (`.md`) or standard MIME (`.eml`) files.

```powershell
mail-utils export <output_dir> [-f|--format {md,eml}] [--filter <filter>] [--db <path>]
```

- `<output_dir>`: Directory where exported files will be written into `<YYYY>/<MM>/` subfolders.
- `-f`, `--format {md,eml}`: Export format (`md` default, or `eml`).
- `--filter <filter>`: Local filter expression to restrict export scope.
- `--db <path>`: Database to read from.

If a message's attachment content was captured (via `--with-attachments` at import time), it's written back
out too: `--format eml` attaches it as a real MIME part, `--format md` writes it into a
`<message-file-stem>.attachments/` directory next to the `.md` file. An attachment with no captured
content (an older sync, or one that ran without `--with-attachments`) falls back to metadata only, same as
before this existed - see README's "Database contents" section.

---

### `schedule` / `unschedule`
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

### `store-in-gmail`
Writes mail-utils messages into a live Gmail mailbox - either from a `mail-utils export --format eml`
directory, or directly from the local database. Unlike every other command, this one requests write-capable
OAuth scopes (`gmail.insert`, `gmail.labels`) on top of the usual read-only `gmail.readonly` - see
`docs/requirements.md`'s "Read-Only / Non-Destructive" principle for why this is a deliberate,
narrowly-scoped exception rather than a default.

```powershell
mail-utils store-in-gmail [<source_dir>] [--filter <filter>] [--max-messages <N>] [--dry-run] [--db <path>]
```

- `<source_dir>` (optional): Directory of `.eml` files to store (searched recursively). Only files carrying
  the `X-Mail-Utils-ID` header `mail-utils export --format eml` writes are stored; any other `.eml` file is
  skipped with a log message. **Omit it** to store directly from the local database instead - no export
  step needed first.
- `--filter <filter>`: Local filter expression (same grammar as `stats`/`export`, e.g. `label:Work
  from:jane has:attachment`), restricting which messages get stored. Evaluated against the local database
  regardless of source.
- `--max-messages <N>`: Store at most `N` messages this run, then stop. Safe to do since progress is
  persisted (see below) - rerun the same command to continue with the next batch.
- `--dry-run`: Reports what would be stored, with which labels, without contacting Gmail or requesting
  (broader) credentials.
- `--db <path>`: Database used both to track which messages have already been stored (so reruns are
  idempotent and an interrupted or `--max-messages`-capped run is trivially resumable) and, when
  `<source_dir>` is omitted, as the actual source of the messages to store.

Preserves the original `Date:` header as the message's arrival date and translates each message's labels
back into Gmail labels, creating any that don't already exist. Every message stored during one run also
gets an additional label unique to that run - `mail-utils-store-in-gmail-<UTC timestamp>` - so the whole
batch is easy to find and review in Gmail afterwards. That timestamp stays fixed for the whole run, and an
interrupted or `--max-messages`-capped run continues under the *same* label when you simply rerun the same
command - only once a run goes through every remaining candidate does the next invocation start a new one.
Calls are paced under Gmail's per-user quota and
retried with backoff on a rate-limit response, so a large store-in-gmail run shouldn't trip Gmail's limits.
Every message stored is logged individually, and the run's final summary always states how many messages
were stored/skipped and which message was stored last.

Attachment *content* is never stored - `mail-utils` has never captured attachment bytes, only metadata
(filename, MIME type, size) - so stored messages are attachment-less regardless of source. Stored messages
get a new Gmail-assigned message ID; the original id survives only as the message's own `X-Mail-Utils-ID`
header.

---

## Local Filter Grammar Reference

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

## Output & Logging Conventions

- **Console Output**: Clean, human-readable text without timestamp or `[INFO]` log prefixes.
- **Log File (`logs/mail-utils.log`)**: Full dual-logged output with UTC timestamps and log levels. Multi-line records are indented to match the header width.
- **Start / End Lifecycle**:
  - `Mail Utils <version> operation started: <operation>`
  - `Mail Utils <version> operation ended in <elapsed>: <details>`

