# Tutorial

A complete walkthrough for a first-time user, demonstrating setup, ingestion, searching, analytics, exporting, and scheduling.

---

## Sanity-Check the Installation

```powershell
.venv\Scripts\mail-utils --version
.venv\Scripts\mail-utils help
```

- `--version` prints the installed version and copyright notice; add `--verbose` to view the release changelog.
- `help` prints the available subcommands.

---

## Ingest Messages

### A. Smart Unified Import
`mail-utils import` automatically recognizes the archive format or falls back to Gmail:

```powershell
# Auto-detects and imports Outlook PST
.venv\Scripts\mail-utils import path\to\archive.pst

# Auto-detects and imports Thunderbird backup (.pcv, .zip, or profile folder)
.venv\Scripts\mail-utils import path\to\backup.pcv

# When no file is given, syncs with Gmail (if an account has been set up - see below)
.venv\Scripts\mail-utils import
```

Before the first Gmail sync, authorize an account once (see `docs/devops.md`'s "Gmail Account Setup" for
the one-time app credential setup this needs):

```powershell
.venv\Scripts\mail-utils prepare-gmail-account default
```

This opens a browser consent screen and saves the resulting token to `data/default-account.json` -
picked up automatically by any command that doesn't specify `--account`. The first sync afterwards
performs a full sync into `data/mails.db`. Subsequent runs are fast incremental syncs.

### B. Dedicated Importers
You can also use the explicit format subcommands:
```powershell
# Gmail API
.venv\Scripts\mail-utils import-gmail

# Microsoft Outlook (.pst)
.venv\Scripts\mail-utils import-pst path\to\archive.pst
# (or alias .venv\Scripts\mail-utils import-outlook path\to\archive.pst)

# Mozilla Thunderbird (.pcv, .zip, profile directory)
.venv\Scripts\mail-utils import-thunderbird path\to\backup.pcv
# (or alias .venv\Scripts\mail-utils import-pcv path\to\backup.pcv)
```

Add `--recursive` (or `-r`) to unpack and index nested email attachments.

Add `--with-attachments` to also fetch and store each attachment's actual content (not just its
filename/type/size), content-addressed under `--db`'s attachment cache. Off by default - it adds an extra
API call/read per attachment plus disk space (see `docs/cli-spec.md` and README's "Database contents").

---

## Search Emails with FTS5

Instant full-text keyword search across subjects, bodies, senders, and recipients:

```powershell
.venv\Scripts\mail-utils search "project alpha"
.venv\Scripts\mail-utils search "invoice OR receipt"
.venv\Scripts\mail-utils search "contract NOT draft" -n 10
```

---

## Explore Offline Database Statistics

```powershell
.venv\Scripts\mail-utils stats
```
Displays total messages, distinct conversation threads, date ranges, top labels, and frequency tables for senders and recipients.

Scope stats with local filters:
```powershell
.venv\Scripts\mail-utils stats --filter "from:example.com after:2026/01/01"
.venv\Scripts\mail-utils stats --filter "has:attachment label:INBOX"
```

---

## Export Messages to Disk

### Markdown with YAML Frontmatter
```powershell
.venv\Scripts\mail-utils export .\exported-md --format md --filter "has:attachment"
```

### Standard RFC 5322 MIME (`.eml`) Files
```powershell
.venv\Scripts\mail-utils export .\exported-eml --format eml
```

Messages are organized chronologically into `<output_dir>\<YYYY>\<MM>\<msg_id>.(md|eml)`.

If a message's attachments were imported with `--with-attachments`, their content comes back out too:
a real MIME part in the `.eml` file, or a `<msg_id>.attachments\` sidecar folder next to the `.md` file.

---

## Schedule Recurring Imports

Register a recurring 30-minute sync task:

```powershell
# Windows Task Scheduler (or cron on Linux/macOS)
.venv\Scripts\mail-utils schedule -- import

# List active scheduled jobs
.venv\Scripts\mail-utils schedule --list

# Remove scheduled job
.venv\Scripts\mail-utils unschedule
```
