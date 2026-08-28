# Mail Utils

A lightweight, privacy-preserving, local email archive indexing and extraction utility.

`mail-utils` ingests emails from multiple personal mail sources—including live **Gmail** accounts, **Microsoft Outlook** (`.pst`) archives, and **Mozilla Thunderbird** (`.pcv`, `.zip`, profile directories)—into a local SQLite database. Once indexed, you can perform full-text search, analyze statistics, and export messages to clean Markdown or standard RFC 5322 `.eml` files.

---

## Key Features

- **Multi-Source Ingestion**:
  - **Gmail API**: OAuth 2.0 incremental sync with history tracking.
  - **Outlook PST**: Pure Python, zero-dependency `[MS-PST]` Unicode parser.
  - **Thunderbird PCV / Profile**: Pure Python Mbox and `.sbd` directory parser.
  - **Recursive Ingestion**: Extracts nested attached messages (`-r` / `--recursive`).
  - **Attachment Content Capture** (opt-in): Store each attachment's actual bytes, not just its
    filename/type/size, content-addressed under `data/attachments/` (`--with-attachments`).
- **SQLite FTS5 Full-Text Search**: Fast BM25 keyword searches with match highlighting and boolean queries (`mail-utils search "<query>"`).
- **Offline Analytics**: Instant statistics on total messages, threads, labels, senders, and recipients (`mail-utils stats`).
- **Flexible Export**: Export messages organized by year/month into **Markdown** (`.md` with YAML frontmatter) or standard **MIME** (`.eml`).
- **Store in Gmail**: Write mail back into a live Gmail mailbox (`mail-utils store-in-gmail`), sourced from a `.eml` export or directly from the local database — filterable, resumable, and the one opt-in, write-capable command; everything else stays read-only.
- **Task Automation**: Automated scheduling via Windows Task Scheduler or Unix cron (`mail-utils schedule`).
- **Privacy & Safety**: Read-only by default — data stays on your local machine, and no command sends, labels, or deletes anything on the remote mailbox unless you explicitly run `store-in-gmail`.

---

## Quickstart

```powershell
# 1. Setup environment
python -m venv .venv
.venv\Scripts\pip install -e .

# 2. Check version
.venv\Scripts\mail-utils --version

# 3. Import from a local archive or Gmail
.venv\Scripts\mail-utils import path\to\archive.pst
.venv\Scripts\mail-utils import path\to\backup.pcv
.venv\Scripts\mail-utils import-gmail

# 4. Search indexed messages
.venv\Scripts\mail-utils search "project alpha"

# 5. View database statistics
.venv\Scripts\mail-utils stats

# 6. Export messages to Markdown or EML
.venv\Scripts\mail-utils export .\exported-mails --format md

# 7. (Opt-in) Store an EML export back into Gmail - requests additional write scopes
.venv\Scripts\mail-utils store-in-gmail .\exported-mails --dry-run
```

---

## Database contents

Everything lives in a single SQLite file (`data/gmail.db` by default, `--db <path>` elsewhere). Row ids are
source-prefixed (`gmail:...`, `outlook:...`, `thunderbird:...`) so the same database can hold messages
imported from more than one source without collisions.

- **`messages`**: one row per message - `id`, `thread_id`, `sender`, `recipient`, `cc`, `bcc`, `subject`,
  `date` (the raw header string), `internal_date_ms` (Gmail's/the source's actual received timestamp,
  used for `export`'s year/month bucketing), `snippet` (Gmail only - `NULL` for PST/Thunderbird), `label_ids`
  (comma-separated ids, resolved to names via `labels`), `body_text` and `body_mime_type`
  (`text/plain`/`text/html`, whichever the source actually carried), `fetched_at`.
- **`message_addresses`**: one row per (message, role, address) - `message_id`, `role`
  (`from`/`to`/`cc`/`bcc`), `address` (lowercased), `name`. Replaced in full for a message on every
  resync, not merged, since a message's own header content never changes.
- **`attachments`**: one row per attachment part - `message_id`, `attachment_id` (Gmail's API id, needed to
  fetch that attachment's content; always `NULL` for PST/Thunderbird sources, which have no equivalent),
  `filename`, `mime_type`, `size`, `content_sha256`. Filename/type/size are always captured; `content_sha256`
  stays `NULL` unless the import ran with `--with-attachments` (see `docs/cli-spec.md`), in which case it's
  the SHA-256 of the attachment's actual bytes, stored content-addressed at `data/attachments/<content_sha256>`
  (identical attachments across messages share one file). `export` writes that content back out - a real
  MIME part for `--format eml`, a `<message-file-stem>.attachments/` sidecar directory for `--format md` -
  falling back to metadata-only when `content_sha256` is `NULL`. An existing database isn't retroactively
  migrated: pick up content for already-synced messages by rerunning the relevant `import*` command with
  `--with-attachments` against the same database.
- **`labels`**: `id` -> `name`, refreshed in full on every sync. For Gmail this is the account's real label
  list; for PST/Thunderbird it's a synthetic `outlook:<folder path>` / `thunderbird:<folder path>` id per
  folder, so folder structure survives as "labels" the same way Gmail labels do.
- **`sync_state`**: internal bookkeeping - `last_history_id` (Gmail incremental sync watermark) and, while a
  `store-in-gmail` run is in progress, the current run's tracking-label name.
- **`gmail_store_state`**: `message_id` -> the Gmail id it was stored as, written only by `store-in-gmail`,
  so a rerun (or one capped by `--max-messages`) skips messages already stored instead of duplicating them.

---

## Documentation

Comprehensive documentation is available in the [`docs/`](docs/) directory:

- [**Tutorial** (`docs/tutorial.md`)](docs/tutorial.md) — Step-by-step walkthrough for first-time users.
- [**CLI Specification** (`docs/cli-spec.md`)](docs/cli-spec.md) — Detailed reference for all subcommands, options, and filter syntax.
- [**Requirements & Architecture** (`docs/requirements.md`)](docs/requirements.md) — High-level goals, functional requirements, and technical invariants.
- [**DevOps & Infrastructure** (`docs/devops.md`)](docs/devops.md) — Environment setup, testing, linting, packaging, and CI/CD guide.
- [**Email Formats Reference** (`docs/emails-formats.md`)](docs/emails-formats.md) — Guide to `.eml`, `.msg`, `.mbox`, and `.pst` file structures.
- [**Changelog** (`CHANGELOG.md`)](CHANGELOG.md) — Version history and release notes.
- [**Roadmap & Backlog** (`TODO.md`)](TODO.md) — Prioritized upcoming features and improvements.
- [**Development Guidelines**](https://github.com/gpellicciotta/dev-guidelines) — Cross-project development guidelines and coordination protocols.

---

## License

[MIT License](LICENSE.md). Copyright (c) Giovanni Pellicciotta.
