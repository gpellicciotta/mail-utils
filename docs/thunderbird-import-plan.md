# Thunderbird `.pcv` / Profile Archive Import — Plan

Tracks TODO.md item 1 (v2.1.0 / vNext): import Mozilla Thunderbird archives (`*.pcv`, `*.zip`, or direct profile directories) into the same `data/gmail.db` tables populated by `import` (Gmail API) and `import-pst` (Outlook PST).

Test fixture: `data/personal-email-backup.pcv` (gitignored personal data, not committed; contains 4,731 messages across 3 active Mbox stores).

---

## 1. What is a `.pcv` / Thunderbird Archive?

A `.pcv` file is created by **MozBackup** (Mozilla Backup) or by archiving a Thunderbird profile folder. Internally, it is a standard **ZIP archive** containing the Thunderbird profile directory structure:
- **`Mail/`**: Local Folders and POP3 accounts (e.g. `Mail/Local Folders/`).
- **`ImapMail/`**: IMAP account caches (e.g. `ImapMail/imap.gmail.com/`, `ImapMail/iceage.anubex.com/`).
- Profile metadata files: `prefs.js`, `mimeTypes.rdf`, address books (`*.mab`), etc.

### Thunderbird Storage Format on Disk
- **Mbox Files (Message Stores)**: Flat files with **no extension** (e.g., `INBOX`, `Sent Mail`, `Archives`) containing concatenated RFC 822 / RFC 2822 / RFC 5322 MIME messages separated by `From ` delimiter lines (`From - <Date>`).
- **Index Files (`.msf`)**: Companion Mail Summary Files containing Mork database indexes of headers. They do not contain message bodies and are discarded during import in favor of direct Mbox stream parsing.
- **Directory Trees (`.sbd`)**: Folders containing subfolders have a companion directory ending in `.sbd`. For example, `Mail/Local Folders/Projects.sbd/ClientA` maps to folder path `Local Folders/Projects/ClientA`.

---

## 2. Architecture & Design

### Module Structure under `src/mail_utils/thunderbird/`
- **`archive.py`**: Abstraction over `.pcv` (ZIP) files and uncompressed directory trees. Provides streaming access to Mbox files and resolves folder hierarchies into human-readable label paths.
- **`tree.py`**: Folder tree enumeration, `.sbd` directory hierarchy resolution, and `labels` mapping (e.g., `thunderbird_folder_label_id(path)`).
- **`messages.py`**: Pure parsing functions that transform raw Mbox / MIME messages into the standard `mail-utils` dictionary shapes:
  - `parse_message(raw_msg, label_id)` -> `messages` table row.
  - `parse_addresses(raw_msg)` -> `message_addresses` table rows.
  - `parse_attachments(raw_msg)` -> `attachments` table rows.

### Key Invariants & Data Mapping
1. **Source Prefix & ID Scheme**:
   - Every message ID is prefixed with `thunderbird:`.
   - Primary ID: `thunderbird:<Message-ID>` (using the standard `Message-ID` header, stripped of whitespace/brackets).
   - Fallback ID (for drafts or legacy messages lacking a `Message-ID` header): `thunderbird:sha1:<digest>` computed over the raw envelope and header block.
2. **Date Resolution**:
   - Primary: RFC 5322 `Date:` header.
   - Fallback: The Mbox envelope `From - <Date>` timestamp line (e.g., `From - Thu Jan 15 16:42:05 2009`), ensuring messages without a `Date:` header still get accurate `internal_date_ms` timestamps and date-bucketing.
3. **Folder / Label Mapping**:
   - Mbox folder paths (e.g., `iceage.anubex.com/INBOX`, `Local Folders/Archive/2020`) become `labels` rows.
   - Enables uniform `--filter label:...` across Gmail, Outlook PST, and Thunderbird data.
4. **Body & Attachment Extraction**:
   - `body_text` and `body_mime_type` (`text/plain` vs `text/html`) extracted from MIME parts using the same rules as `gmail_client.py`.
   - Attachment metadata (filename, mime_type, byte size) extracted by walking MIME parts without retaining payload bytes in memory.

---

## 3. Phased Implementation Plan

### Phase 1 — Archive & Folder Tree Resolution (`archive.py`, `tree.py`)
- Support reading directly from `.pcv` files (via Python `zipfile`), `.zip` archives, or uncompressed Thunderbird profile folders.
- Traverse the directory structure, filtering out non-mail files (`*.msf`, `*.dat`, `*.html`, `*.rdf`, `*.js`, `*.mab`).
- Resolve `.sbd` directories into clean hierarchical folder names.
- Map folders to `labels` rows (`id` and `name`).

### Phase 2 — Mbox & MIME Message Parsing (`messages.py`)
- Stream messages from Mbox files using Python's `mailbox.mbox` / `email` modules.
- Decode encoded-word headers (`Subject`, `From`, `To`, `Cc`, `Bcc`) via `email.header.decode_header`.
- Implement address normalization and deduplication for `message_addresses`.
- Implement MIME tree traversal for body text and attachment metadata.
- Implement envelope delimiter fallback for missing `Date:` headers.

### Phase 3 — Database Integration & CLI Command
- Wire into `src/mail_utils/cli.py` via a new subcommand:
  ```powershell
  mail-utils import-thunderbird <archive_or_dir_path> [--db <path>]
  ```
  (with alias `import-pcv`).
- Log progress at `PROGRESS_LOG_INTERVAL` (every 50 messages).
- Upsert into `labels`, `messages`, `message_addresses`, and `attachments` tables.

### Phase 4 — Test Suite & Integration Verification
- **Unit Tests (`tests/test_thunderbird.py`)**:
  - Test `.sbd` path resolution.
  - Test Mbox parsing with synthesized MIME samples (plain text, HTML, attachments, encoded words, missing dates, missing Message-IDs).
  - Test CLI argument parsing and dispatching.
- **Integration Tests against Real Fixture (`tests/test_thunderbird_integration.py`)**:
  - Skipped when `data/personal-email-backup.pcv` is not present (same pattern as PST integration tests).
  - Verifies exact message counts (4,731 total messages: 2,522 in `iceage.anubex.com/INBOX`, 2,089 in `imap.gmail.com/INBOX`, 120 in `iceage.anubex.com/Sent Mail`).
  - Verifies unique IDs, sender address parsing, and zero exceptions.

### Phase 5 — Documentation & Polish
- Update `TODO.md` (mark item 1 complete).
- Update `CHANGELOG.md` with new `import-thunderbird` / `import-pcv` command notes.
- Update `README.md`, `CLAUDE.md`, and `docs/index.md`.
- Run full test suite (`pytest`) and linters (`ruff check .`, `ruff format --check .`).

---

## 4. Verification Targets on `data/personal-email-backup.pcv`

| Target Metric | Expected Value |
| :--- | :--- |
| **Total Mail Stores** | 3 non-empty Mbox files |
| **Total Messages** | 4,731 messages |
| **`iceage.anubex.com/INBOX`** | 2,522 messages |
| **`imap.gmail.com/INBOX`** | 2,089 messages |
| **`iceage.anubex.com/Sent Mail`** | 120 messages |
| **ID Scheme** | All prefixed with `thunderbird:` (no collisions) |

