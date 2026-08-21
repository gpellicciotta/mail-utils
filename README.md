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
- **SQLite FTS5 Full-Text Search**: Fast BM25 keyword searches with match highlighting and boolean queries (`mail-utils search "<query>"`).
- **Offline Analytics**: Instant statistics on total messages, threads, labels, senders, and recipients (`mail-utils stats`).
- **Flexible Export**: Export messages organized by year/month into **Markdown** (`.md` with YAML frontmatter) or standard **MIME** (`.eml`).
- **Task Automation**: Automated scheduling via Windows Task Scheduler or Unix cron (`mail-utils schedule`).
- **Privacy & Safety**: 100% read-only operations. Data stays completely on your local machine.

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
```

---

## Documentation

Comprehensive documentation is available in the [`docs/`](docs/) directory:

- [**Tutorial** (`docs/tutorial.md`)](docs/tutorial.md) — Step-by-step walkthrough for first-time users.
- [**CLI Specification** (`docs/cli-spec.md`)](docs/cli-spec.md) — Detailed reference for all subcommands, options, and filter syntax.
- [**Requirements & Architecture** (`docs/requirements.md`)](docs/requirements.md) — High-level goals, functional requirements, and technical invariants.
- [**DevOps & Infrastructure** (`docs/devops.md`)](docs/devops.md) — Environment setup, testing, linting, packaging, and CI/CD guide.
- [**Email Formats Reference** (`docs/emails-formats.md`)](docs/emails-formats.md) — Guide to `.eml`, `.msg`, `.mbox`, and `.pst` file structures.
- [**Changelog** (`CHANGELOG.md`)](CHANGELOG.md) — Release notes and version history.
- [**Roadmap & Backlog** (`TODO.md`)](TODO.md) — Prioritized upcoming features and improvements.

---

## License

MIT License. Copyright (c) Giovanni Pellicciotta.
