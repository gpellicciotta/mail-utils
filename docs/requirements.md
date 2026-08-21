# Project Requirements

This document outlines the high-level vision, functional requirements, technical constraints, and quality standards for `mail-utils`.

---

## 1. High-Level Vision & Objectives

`mail-utils` is a lightweight, privacy-focused, read-only email indexing and archive utility designed to consolidate, search, and export personal email from disparate email providers and local archive formats into a unified local SQLite database.

### Core Principles
- **Read-Only / Non-Destructive**: Never modifies or deletes emails on remote mail servers or within local archive files.
- **Privacy & Local Execution**: All indexes, databases, and full-text searches remain strictly on the local machine; zero telemetry or external analytics.
- **Zero Heavy External Dependencies**: Core file format parsers (such as Microsoft Outlook PST and Mozilla Thunderbird PCV/Mbox) are implemented with pure Python standard libraries without native C/C++ library dependencies.
- **Unified Querying & Storage**: Ingested messages from diverse providers (Gmail, Outlook, Thunderbird) are normalized into a single database schema with source prefix isolation (`gmail:`, `outlook:`, `thunderbird:`).

---

## 2. Functional Requirements

### 2.1 Multi-Source Ingestion
- **Gmail Ingestion (`mail-utils import`)**:
  - Secure OAuth 2.0 authorization with `gmail.readonly` scope.
  - Automatic initial full sync followed by historyId-based incremental polling.
  - Server-side filtered sync via Gmail search syntax (`--filter`).
- **Outlook PST Ingestion (`mail-utils import-pst` / `import-outlook`)**:
  - Read-only ingestion of Unicode Microsoft Outlook `.pst` files based on `[MS-PST]`.
  - Automatic folder tree traversal with folder-to-label mapping.
- **Thunderbird Ingestion (`mail-utils import-thunderbird` / `import-pcv`)**:
  - Direct import from MozBackup `.pcv` archives, `.zip` backups, or raw profile directories.
  - Automatic `.sbd` hierarchy resolution and RFC 2047 encoded header decoding.
  - Fallback timestamp derivation from Mbox `From -` delimiter envelopes.
- **Recursive Attachment Extraction (`-r` / `--recursive`)**:
  - Optional extraction and indexing of nested emails attached as `message/rfc822` or `.eml` files.

### 2.2 Full-Text Search (`mail-utils search`)
- Fast, indexed keyword search using SQLite `FTS5`.
- BM25 ranked relevance scoring.
- Excerpt snippet generation with highlighted match boundaries.
- Support for boolean syntax (`AND`, `OR`, `NOT`, prefix queries `term*`).

### 2.3 Offline Statistics & Analytics (`mail-utils stats`)
- Immediate reporting of total message counts, distinct thread counts, and indexing time spans.
- Frequency breakdowns for top labels, senders, To recipients, Cc recipients, and Bcc recipients.
- Global column width alignment across all formatted sections.
- Full compatibility with local `--filter` expressions.

### 2.4 Multi-Format Export (`mail-utils export`)
- Export indexed messages into hierarchical date-bucketed directories (`<output_dir>/<YYYY>/<MM>/`).
- **Markdown Export (`--format md`)**: Clean Markdown body with YAML frontmatter containing complete message headers and attachment metadata.
- **EML Export (`--format eml`)**: Standard RFC 5322 MIME messages compatible with external email clients.

### 2.5 Automated Scheduling (`mail-utils schedule` / `unschedule`)
- Native Windows Task Scheduler integration on Windows.
- Native crontab integration on macOS and Linux.
- Listing, verification, and removal of scheduled synchronization and export tasks.

---

## 3. Technical Requirements & Invariants

| Area | Requirement |
| :--- | :--- |
| **Python Runtime** | Python 3.11 or newer (tested on 3.11, 3.12, 3.13) |
| **Database Engine** | SQLite 3 with FTS5 enabled |
| **Logging & Output** | Clean console output without log prefixes; dual-logging to `logs/mail-utils.log` with UTC timestamps |
| **Multi-line Logs** | Subsequent lines of multi-line log records indented to match the first-line header prefix |
| **Operation Boundaries** | Standardized start (`Mail Utils {{version}} operation started: `) and end (`Mail Utils {{version}} operation ended in `) lines |
| **Source Isolation** | Primary keys prefixed with source identifier (`gmail:`, `outlook:`, `thunderbird:`) to prevent cross-source collisions |
| **Paths & Config** | Single source of truth in `mail_utils.config`, with all secrets/databases residing under `data/` |
| **Testing** | 100% test coverage with automated unit tests and committed anonymized sample fixtures |

