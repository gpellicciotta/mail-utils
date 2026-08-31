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
mail-utils import [<source_path>] [--filter <query>] [-r|--recursive] [--with-attachments] [--account <name>] [--db <dir>]
```

- `<source_path>`: Optional positional path to an Outlook `.pst` file, Thunderbird archive (`.pcv`, `.zip`), or Thunderbird profile folder.
  - If omitted: checks for the app credential file / the resolved account file (see `--account`) and runs a Gmail sync.
  - If an Outlook PST is provided: imports Outlook folders and messages.
  - If a Thunderbird backup/directory is provided: imports Thunderbird folders and messages.
  - If an unsupported or single-message format (e.g. `.eml`, `.msg`, `.mbox`) is provided: reports a descriptive error explaining supported options.
- `--filter <query>`: Server-side search filter when syncing from Gmail.
- `-r`, `--recursive`: Recursively index attached email messages (`message/rfc822` / `.eml`).
- `--with-attachments`: Also fetch and store each attachment's actual content (not just
  filename/type/size) under `--db`'s attachment cache, content-addressed by SHA-256. Off by default - adds
  an extra API call/read per attachment plus disk space. See README's "Database contents" section.
- `--account <name>`: Gmail account to authenticate as, when syncing from Gmail (see "Gmail Account
  Selection" below).
- `--db <dir>`: Directory holding this run's database and attachment cache (default: `data/`). See
  "Database & Attachment Storage" below.

---

### `import-gmail`
Dedicated subcommand to ingest new messages from Gmail via the Gmail API.

```powershell
mail-utils import-gmail [--filter <query>] [-r|--recursive] [--with-attachments] [--account <name>] [--db <dir>]
```

- `--filter <query>`: Server-side search filter (Gmail `q` syntax). Forces a filtered listing without updating incremental sync state.
- `-r`, `--recursive`: Recursively index attached email messages.
- `--with-attachments`: Also fetch and store each attachment's actual content (see `import` above).
- `--account <name>`: Gmail account to authenticate as (see "Gmail Account Selection" below).
- `--db <dir>`: Directory holding this run's database and attachment cache (see "Database & Attachment Storage" below).

---

### `prepare-gmail-account`
Interactively authorizes a Gmail account and saves its resulting OAuth token to an account file, for
later selection via `--account`. See `docs/devops.md`'s "Gmail Account Setup" for the full walkthrough
(including how to obtain the app credential file this command requires).

```powershell
mail-utils prepare-gmail-account <name> [--with-write]
```

- `<name>`: Account name (resolved the same way as `--account`'s value - a bare name saves to
  `data/<name>-account.json`; a value containing a path separator or an explicit `.json` extension is
  used verbatim as the file path).
- `--with-write`: Also request write-capable scopes (`gmail.insert`, `gmail.labels`) up front, for an
  account meant to be used with `store-in-gmail`. Default is read-only (`gmail.readonly`) - a later
  `store-in-gmail` run against the account will trigger a fresh consent prompt to upgrade scope if needed.

Requires `data/google-cloud-mail-utils-app-credentials.json` to already exist. Opens a browser consent
screen, then prints the authenticated account's address so you can confirm you signed into the account
you meant to.

---

### `check-gmail-account`
Read-only sanity check: reports which Google account an `--account` name actually maps to, and what
it's authorized to do - useful after setting up several accounts, to confirm which is which before
running a command against the wrong one.

```powershell
mail-utils check-gmail-account <name>
```

- `<name>`: Account name (resolved the same way as `--account`'s value - see `prepare-gmail-account`
  above).

Prints the authenticated email address, the OAuth scopes actually granted to the cached token (so you
can tell a read-only account from a write-capable one), and the mailbox's message/thread counts (from
Gmail's own profile). Silently refreshes an expired-but-still-valid token the same way any other command
would; if the account file doesn't exist yet, reports a clear error pointing at `prepare-gmail-account`
instead of failing obscurely.

---

### `import-pst` (alias: `import-outlook`)
Ingests messages and folder hierarchies from a Microsoft Outlook `.pst` file.

```powershell
mail-utils import-pst <pst_path> [-r|--recursive] [--with-attachments] [--db <dir>]
mail-utils import-outlook <pst_path> [-r|--recursive] [--with-attachments] [--db <dir>]
```

- `<pst_path>`: Positional path to the Unicode `.pst` archive.
- `-r`, `--recursive`: Recursively index attached email messages.
- `--with-attachments`: Also fetch and store each attachment's actual content (see `import` above).
- `--db <dir>`: Directory holding this run's database and attachment cache (see "Database & Attachment Storage" below).

---

### `import-thunderbird` (alias: `import-pcv`)
Ingests messages from a Mozilla Thunderbird backup (`.pcv`, `.zip`) or profile directory.

```powershell
mail-utils import-thunderbird <archive_path> [-r|--recursive] [--with-attachments] [--db <dir>]
mail-utils import-pcv <archive_path> [-r|--recursive] [--with-attachments] [--db <dir>]
```

- `<archive_path>`: Positional path to `.pcv`/`.zip` file or Thunderbird profile folder.
- `-r`, `--recursive`: Recursively index attached email messages.
- `--with-attachments`: Also fetch and store each attachment's actual content (see `import` above).
- `--db <dir>`: Directory holding this run's database and attachment cache (see "Database & Attachment Storage" below).

---

### `search`
Full-text searches indexed messages using SQLite `FTS5`.

```powershell
mail-utils search <query> [-n|--limit <N>] [--db <dir>]
```

- `<query>`: Search string. Supports boolean operators (`AND`, `OR`, `NOT`) and prefix matching (`term*`).
- `-n`, `--limit <N>`: Maximum number of results to display (default: `20`).
- `--db <dir>`: Directory holding the database to search (see "Database & Attachment Storage" below).

---

### `stats`
Displays offline summary statistics from the local database.

```powershell
mail-utils stats [--filter <filter>] [--db <dir>]
```

- `--filter <filter>`: Local filter expression (e.g. `label:Work from:jane has:attachment`).
- `--db <dir>`: Directory holding the database to query (see "Database & Attachment Storage" below).

---

### `export`
Exports messages to disk as Markdown (`.md`) or standard MIME (`.eml`) files.

```powershell
mail-utils export <output_dir> [-f|--format {md,eml}] [--filter <filter>] [--db <dir>]
```

- `<output_dir>`: Directory where exported files will be written into `<YYYY>/<MM>/` subfolders.
- `-f`, `--format {md,eml}`: Export format (`md` default, or `eml`).
- `--filter <filter>`: Local filter expression to restrict export scope.
- `--db <dir>`: Directory holding the database to read from (see "Database & Attachment Storage" below).

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
mail-utils store-in-gmail [<source_dir>] [--filter <filter>] [--max-messages <N>] [--dry-run] [--account <name>] [--db <dir>]
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
- `--account <name>`: Gmail account to authenticate as (see "Gmail Account Selection" below).
- `--db <dir>`: Directory holding the database used both to track which messages have already been stored
  (so reruns are idempotent and an interrupted or `--max-messages`-capped run is trivially resumable) and,
  when `<source_dir>` is omitted, as the actual source of the messages to store. See "Database & Attachment
  Storage" below.

Before writing anything, logs the authenticated Gmail account's address (`Target account: ...`) as a
safety check against accidentally being signed into the wrong Google account - worth checking by eye
before a run against a real mailbox.

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

## Gmail Account Selection

`--account <name>`, accepted by every command that talks to the Gmail API (`import`, `import-gmail`,
`store-in-gmail`), selects which authorized Gmail account to act as. Accounts are independent of where
a run's data lives (`--db`) - see "Database & Attachment Storage" below.

- A bare name (no path separator, no `.json` extension) resolves to `data/<name>-account.json`.
- A value containing a path separator or an explicit `.json` extension is used verbatim as the file path.
- Omitted: falls back to `data/default-account.json` if that file exists; otherwise the command reports
  a clear error rather than silently picking an arbitrary account.

Account files are produced by `mail-utils prepare-gmail-account` (see above) and are distinct from the
shared app credential file (`data/google-cloud-mail-utils-app-credentials.json`) - see `docs/devops.md`'s
"Gmail Account Setup" for the full explanation and one-time setup walkthrough.

---

## Database & Attachment Storage

`--db <dir>`, accepted by every command that reads or writes the local database, is a **directory**, not
a database file path - it's created if missing, and holds both this run's database (`<dir>/mails.db`)
and its attachment content cache (`<dir>/attachments/`), so the two are always scoped together instead of
an attachment cache being shared across unrelated databases. Defaults to `data/` when omitted, i.e.
`data/mails.db` and `data/attachments/`.

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

