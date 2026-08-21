# Outlook `.pst` Import — Technical Plan & Architecture

This document details the read-only implementation of the `[MS-PST]` specification for importing Microsoft Outlook `.pst` archives into SQLite.

---

## 1. Overview & Architecture

The Outlook parser lives under `src/mail_utils/outlook/` and is implemented from scratch with zero third-party dependencies:

- **`ndb.py` (Node Database Layer)**:
  - Header validation (`!BDN` magic, Unicode format `wVer` verification, root BREF pointers).
  - B-Tree page traversal: Node B-Tree (NBT) and Block B-Tree (BBT) lookups.
  - Multi-block resolution: Data blocks (XBLOCK, XXBLOCK) and subnode B-Trees (SLBLOCK, SIBLOCK).
  - Permutation decoding (`NDB_CRYPT_PERMUTE`).
- **`ltp.py` (Lists, Tables, Properties Layer)**:
  - Heap-on-Node (HN) parsing across single and multi-block heaps.
  - BTree-on-Heap (BTH) record resolution.
  - Property Context (PC) decoding with MAPI data type resolution (`read_property_context`).
  - Table Context (TC) decoding for folder hierarchies, message contents, recipients, and attachments (`read_table_context`).
- **`tree.py` (Folder & Message Traversal)**:
  - Recursive folder hierarchy walk from `NID_ROOT_FOLDER`.
  - Folder-to-label ID mapping (`outlook:<path>`).
- **`messages.py` (MAPI Property Decoding)**:
  - Decoding MAPI properties into standard dict structures matching the database schema.
  - Address parsing and attachment metadata extraction.

---

## 2. Key `[MS-PST]` Implementation Insights

1. **Table Context Row Matrix Resolution**:
   - In large Table Contexts spanning multiple blocks, each ~8KB block reserves padding at its tail.
   - Row matrix blocks must be truncated to whole record boundaries before concatenation (`_resolve_row_matrix`).
2. **Subnode Table Resolution**:
   - Recipient and Attachment Table NIDs are arbitrary subnodes assigned by the PST writer rather than derived deterministically from the parent message NID.
   - Subnodes are enumerated and resolved by matching `nid_type()`.
3. **MAPI Property Types**:
   - Distinguishing `PtypString` (UTF-16LE) from `PtypString8` (codepage-dependent 8-bit text) is critical for character decoding.
   - `PidTagHtmlBody` is stored as `PtypBinary` (raw bytes requiring codepage decoding).
4. **Subject Prefix Handling**:
   - `PidTagSubject` optional prefix markers (`[MS-OXCMSG]`) consist of two characters in the property's code width. Dropping the prefix control marker yields the complete displayed subject.

---

## 3. Data Invariants & CLI Integration

- **Message IDs**: Stored with `outlook:<Message-ID>` or a deterministic SHA-1 fallback.
- **Labels**: PST folder paths (e.g. `Inbox/Projects`) are mapped to `labels` rows and stored in `messages.label_ids`.
- **Command**:
  ```powershell
  mail-utils import-pst <path/to/archive.pst> [--db <path>] [-r]
  ```
  (with alias `import-outlook`).

---

## 4. Out of Scope

- ANSI (32-bit legacy) PST format (only modern Unicode 64-bit PSTs supported).
- `NDB_CRYPT_CYCLIC` obfuscation.
- PST writing/modification (mail-utils is read-only by design).
