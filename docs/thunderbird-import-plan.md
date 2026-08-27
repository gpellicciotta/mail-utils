# Thunderbird Archive Import — Technical Plan & Architecture

This document details the design and implementation of Mozilla Thunderbird archive (`*.pcv`, `*.zip`) and profile folder ingestion for `mail-utils`.

---

## Thunderbird Archive Structure

Thunderbird profiles and MozBackup `.pcv` files use a standard ZIP layout:
- **`Mail/`**: Local Folders and POP3 accounts (e.g. `Mail/Local Folders/`).
- **`ImapMail/`**: Cached IMAP account directories.
- **Mbox Files**: Flat files without extensions (e.g. `INBOX`, `Sent Mail`) containing concatenated RFC 5322 MIME messages separated by `From ` delimiter lines (`From - <Date>`).
- **Directory Trees (`.sbd`)**: Subfolder directories representing mail hierarchies (e.g. `Mail/Local Folders/Projects.sbd/ClientA`).
- **Index Files (`.msf`)**: Companion Mork database header indexes (ignored in favor of direct Mbox stream parsing).

---

## Architecture & Design

### Module Structure under `src/mail_utils/thunderbird/`
- **`archive.py`**: Abstraction over `.pcv` (ZIP) archives and filesystem directory trees. Provides streaming extraction of Mbox stores into temporary files.
- **`tree.py`**: Folder hierarchy traversal, `.sbd` directory mapping, and label ID generation (`thunderbird:<path>`).
- **`messages.py`**: MIME parsing, RFC 2047 encoded header decoding, body text extraction, attachment metadata extraction, and nested attachment parsing.

### Invariants & Data Mapping
1. **Source Prefix & ID Scheme**:
   - Primary: `thunderbird:<Message-ID>`.
   - Fallback: `thunderbird:sha1:<hash>` over the envelope and header block.
2. **Date Resolution**:
   - Primary: RFC 5322 `Date:` header.
   - Fallback: Envelope `From - <Date>` timestamp line.
3. **Folder / Label Mapping**:
   - Folder paths (e.g. `Local Folders/Archive/2026`) become `labels` rows.
4. **Body & Attachment Extraction**:
   - Plain text preferred over HTML.
   - Attachment metadata (filename, mime type, size) extracted without retaining content bytes in memory.

---

## CLI Command

```powershell
mail-utils import-thunderbird <archive_or_directory_path> [--db <path>] [-r]
mail-utils import-pcv <archive_or_directory_path> [--db <path>] [-r]
```
