# Tutorial

A complete walkthrough for a first-time user, demonstrating setup, ingestion, searching, analytics, exporting, and scheduling.

---

## 1. Sanity-Check the Installation

```powershell
.venv\Scripts\mail-utils --version
.venv\Scripts\mail-utils help
```

- `--version` prints the installed version and copyright notice; add `--verbose` to view the release changelog.
- `help` prints the available subcommands.

---

## 2. Ingest Messages

### A. Smart Unified Import
`mail-utils import` automatically recognizes the archive format or falls back to Gmail:

```powershell
# Auto-detects and imports Outlook PST
.venv\Scripts\mail-utils import path\to\archive.pst

# Auto-detects and imports Thunderbird backup (.pcv, .zip, or profile folder)
.venv\Scripts\mail-utils import path\to\backup.pcv

# When no file is given, syncs with Gmail (if credentials exist)
.venv\Scripts\mail-utils import
```
The first run prompts for OAuth browser consent, then performs a full sync into `data/gmail.db`. Subsequent runs are fast incremental syncs.

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

---

## 3. Search Emails with FTS5

Instant full-text keyword search across subjects, bodies, senders, and recipients:

```powershell
.venv\Scripts\mail-utils search "project alpha"
.venv\Scripts\mail-utils search "invoice OR receipt"
.venv\Scripts\mail-utils search "contract NOT draft" -n 10
```

---

## 4. Explore Offline Database Statistics

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

## 5. Export Messages to Disk

### Markdown with YAML Frontmatter
```powershell
.venv\Scripts\mail-utils export .\exported-md --format md --filter "has:attachment"
```

### Standard RFC 5322 MIME (`.eml`) Files
```powershell
.venv\Scripts\mail-utils export .\exported-eml --format eml
```

Messages are organized chronologically into `<output_dir>\<YYYY>\<MM>\<msg_id>.(md|eml)`.

---

## 6. Schedule Recurring Imports

Register a recurring 30-minute sync task:

```powershell
# Windows Task Scheduler (or cron on Linux/macOS)
.venv\Scripts\mail-utils schedule -- import

# List active scheduled jobs
.venv\Scripts\mail-utils schedule --list

# Remove scheduled job
.venv\Scripts\mail-utils unschedule
```
