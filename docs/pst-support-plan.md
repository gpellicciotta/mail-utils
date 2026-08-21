# Outlook `.pst` import — plan

Tracks TODO.md item 1 (v2.0.0): import Outlook `.pst` archives into the same `data/gmail.db`
tables Gmail import already populates. Test fixture: `data/personal-email-backup.pst`
(gitignored personal data, not committed).

## What already exists (uncommitted, `src/mail_utils/pst/`)

A hand-rolled, read-only implementation of the relevant slice of `[MS-PST]`, built bottom-up in
two layers, validated end-to-end by hand against `data/personal-email-backup.pst` (a real,
262-message folder was fully enumerated with correct subjects/senders):

- **`ndb.py`** — NDB (Node Database) layer, complete for Unicode-format PSTs: header parsing
  (`!BDN` magic, `wVer` check, root BREFs), BTree page reads, Node BTree (NBT) and Block BTree
  (BBT) leaf lookup, single- and multi-block (XBLOCK/XXBLOCK) data block resolution, subnode BTree
  (SLBLOCK/SIBLOCK) lookup, and `NDB_CRYPT_PERMUTE` decoding. `PSTFile` wraps all of this into
  `resolve_nid` / `read_block` / `read_block_parts` / `read_subnode` (`read_block_parts` is new —
  see Phase 1 below).
- **`ltp.py`** — LTP (Lists, Tables, Properties) layer, now complete: Heap-on-Node (HN) parsing
  (including genuinely multi-block heaps), BTree-on-Heap (BTH) record reading, Property Context
  (PC) reading (`read_property_context`, returns each property's MAPI type alongside its bytes),
  and Table Context (TC) reading (`read_table_context`) — used for folder hierarchy/contents tables
  and per-message recipient/attachment tables.
- **`tree.py`** — folder/message tree enumeration (`walk_folders`), built on `ltp.py`'s TC support.
- **`messages.py`** — MAPI property decoding into `gmail_client.py`-matching dict/list shapes
  (`fetch_message` / `parse_message` / `parse_addresses` / `parse_attachments`).
- **`__init__.py`** — still empty; no public API yet, and nothing in `cli.py` references `pst`.

No tests exist for this module yet, and nothing is wired into the CLI. Everything in
`src/mail_utils/pst/` is untracked (no commits so far). Phases 1–3 below are done and verified end
to end against the real 262-message PST; Phases 4–7 are not yet implemented.

## Phase 1 — Table Context (TC) support — done

This turned out to be the hard part, and along the way surfaced three real bugs in the
already-uncommitted code, all fixed and verified against the real PST:

1. **`read_property_context` byte-layout bug.** It read a PC BTH record's `prop_id`/`prop_type`
   from the wrong offsets (treating the *value*'s type field as the id, and the id was actually
   sitting in the BTH *key*, which was being discarded) and sliced a 2-byte `raw_value` where 4
   were needed. Root-folder decoding threw immediately once this was exercised for real. Fixed by
   reading `prop_id` from `rec.key` and `prop_type`/`dwValueHnid` from the correct offsets in
   `rec.value`.
2. **`read_bth` didn't thread `bIdxLevels`.** It tried to read a `bType`/`cLevel` header off every
   BTH node's own bytes, but only the top-level `BTHHEADER` carries that — leaf/intermediate BTH
   nodes are plain flat arrays. Fixed by having `read_bth_header` return `bIdxLevels` and passing
   it down through the recursion instead.
3. **Multi-block Heap-on-Node wasn't implemented**, only flagged as a gap. A real contents table
   with 262 rows needs a 14-block heap for all its inline strings. Fixed: `ndb.py` gained
   `read_block_parts` (returns each underlying NDB block separately, not concatenated — needed
   because block boundaries matter for structured data), and `parse_heap` now reads every block's
   own page map (`ibHnpm` is always a block's first 2 bytes; only block 0 additionally carries
   `bSig`/`bClientSig`/`hidUserRoot`).

A fourth, more subtle issue came up building `read_table_context` itself: a TC's **Row Matrix**,
when stored via a subnode (any table too large for one block), is *not* safe to read as one
concatenated blob the way every other HNID resolution is — each ~8KB block pads its tail with
unused space rather than starting the next row there (confirmed: an 8176-byte block held exactly
62 rows of 130 bytes, with 116 trailing pad bytes). Naive concatenation splices that padding into
the middle of the row stream. Fixed with a dedicated `_resolve_row_matrix` that truncates each
block to a whole number of rows before joining, using the new `read_block_parts`. Separately, the
Cell Existence Bitmap turned out not to reliably reflect real vs. absent data (the mandatory
`dwRowID` column came back with its CEB bit clear despite holding a real value), so
`read_table_context` decodes every column for every row unconditionally rather than gating on it.

Verified end-to-end: walking the real PST's folder tree (`Top of Outlook data file` → `All Mail` →
`Me`) and its contents table correctly found all 262 messages with legible subjects and sender
names.

**Phase 2 — Folder/message enumeration (`pst/tree.py`) — done.**
`walk_folders()` walks from `NID_ROOT_FOLDER`, pre-order, returning a flat list of
`PSTFolder(nid, path, message_nids)`. Confirmed: a hierarchy/contents table row's `PidTagLtpRowId`
(`0x67f2`) *is* the child folder's/message's own NID (not a separate lookup), so no extra resolve
step is needed per row. Verified against the real PST: found all 7 folders and all 262 messages
under `Top of Outlook data file/All Mail/Me`, matching Phase 1's manual walk exactly.

**Phase 3 — MAPI property decoding → the existing schema (`pst/messages.py`) — done.**
`fetch_message()` reads a message's PC once, plus its Recipient/Attachment Tables if present, into
a `RawMessage`; `parse_message`/`parse_addresses`/`parse_attachments` then derive the same dict/list
shapes `gmail_client.py` produces from it, purely. Ran against all 262 real messages with zero
exceptions; 232/262 resolved a `from` address, 183/262 had extractable body text, 1060 attachment
rows total (includes inline images, same as Gmail's `parse_attachments`).

Real findings along the way:
- **A message's Recipient/Attachment Table NIDs are *not* derived from the message's own NID** —
  unlike a folder's Hierarchy/Contents Table (built via `make_nid(TYPE, folder_nid >> 5)`), these
  are arbitrary subnode entries assigned by the writer with no relationship to the parent message's
  NID (confirmed: message NID `0x200044`'s tables lived at subnode NIDs `0x692`/`0x671`, unrelated
  to `0x200044`). Fixed by adding `ndb.py`'s `list_subnode_entries`/`PSTFile.list_subnodes` to
  enumerate a node's subnodes and match by `nid_type()`, rather than trying to derive the NID.
- **`read_property_context` needed to start returning each property's MAPI type alongside its raw
  bytes** (now `{prop_id: PSTProperty(prop_type, value)}`, was `{prop_id: bytes}`) — decoding a
  string correctly depends on knowing whether it's `PtypString` (UTF-16LE) or `PtypString8`
  (codepage-dependent 8-bit), and some properties are ambiguous without it — e.g. `PidTagHtmlBody`
  turned out to be `PtypBinary` (`0x0102`), not a string type at all, empirically confirmed by
  reading its BTH record's type field directly.
- **Subject Prefix decoding bug, caught by scanning all 262 real subjects for stray leading control
  characters.** `PidTagSubject`'s optional prefix marker (`[MS-OXCMSG]` 2.2.1.10) is 2 full
  *characters* in the property's own width (4 bytes for `PtypString`, one UTF-16 code unit each for
  the tag and `cch`), not 2 raw bytes — the first attempt left a stray leading character (`cch`'s
  low byte, misread as text) on every prefixed subject. Also realized `cch`'s actual value doesn't
  matter for reconstructing the full displayed subject: `PidTagSubjectPrefix` and
  `PidTagNormalizedSubject` are stored back-to-back with nothing removed, so dropping just the
  2-character marker already yields the correct, complete subject regardless of where the prefix
  ends.
- **`parse_message`'s `recipient`/`cc`/`bcc` had no Recipient-Table fallback**, only
  `parse_addresses` did — caught by comparing the two on a headers-absent message, where
  `parse_addresses` found a `to` row but `parse_message`'s `recipient` field stayed `None`. Fixed by
  building the same header-style summary string (`"Name <addr>, ..."`) from the Recipient Table
  when transport headers are absent, so both stay consistent.
- **Known, accepted limitation:** a message with no `PidTagBody`/`PidTagHtmlBody` — compressed
  RTF only (`PidTagRtfCompressed`) — has no extractable body text without implementing RTF
  decompression (`[MS-OXRTFCP]`), out of scope for now; occurs for meeting requests and some Notes
  in the real PST (79/262 messages here). Similarly, a self-sent message whose sender has only an
  Exchange X.500 DN (no `PidTagSenderSmtpAddress`) resolves to a name with no address — the DN can't
  be turned into an SMTP address without an offline directory, so it's left as-is rather than
  guessed at.

**Phase 4 — identity, dedup, and folders-as-labels — done.**
- **Row identity.** `gmail_client.py` gained `ID_PREFIX = "gmail:"`, applied to every id/message_id
  `parse_message`/`parse_addresses`/`parse_attachments` return (the raw unprefixed id is still what
  every Gmail API call itself uses — only the stored row id changes). `pst/messages.py`'s `_make_id`
  already used `outlook:` from Phase 3. Caught and fixed a related bug while wiring this up:
  `cli.py`'s three sync loops passed the *raw* `raw["id"]` (unprefixed) to `upsert_addresses`/
  `upsert_attachments` while `upsert_message` got the *parsed*, now-prefixed dict — silently
  breaking the delete-then-insert cleanup on rerun (stale prefixed rows never matched the
  unprefixed `DELETE ... WHERE message_id = ?`). Fixed by reusing the one `parse_message(raw)`
  result's `["id"]` everywhere per message instead of re-deriving it.
- **Migration script, written, verified, and run against the real `data/gmail.db`.**
  `scripts/migrate-gmail-id-prefix.py` — dry-run by default (`--apply` to write), takes a
  timestamped backup copy before writing, wrapped in one transaction, and idempotent (only touches
  rows not already `gmail:`/`outlook:`-prefixed). Verified first against a scratch copy of the real
  16,258-message `data/gmail.db` (all messages prefixed, zero orphaned
  `message_addresses`/`attachments` rows, second run correctly a no-op), then run for real against
  `data/gmail.db` itself (with your explicit go-ahead) - same result, and `stats` still reads it
  correctly afterward. Backup kept at `data/gmail.pre-gmail-id-prefix-<timestamp>.db`.
- **Folders → labels.** `pst/tree.py` gained `folder_label_id(path)` (`outlook:Inbox/Projects`) and
  `labels_for_folders(folders)` (→ `db.upsert_labels`-ready rows, skipping the root folder's empty
  path); `pst/messages.py`'s `parse_message` takes an optional `label_id` param so the folder walk
  (which knows the path) can set `label_ids` on each message it produces — verified together against
  the real PST.

**Phase 5 — CLI wiring (`cli.py`) — done.**
New `import-pst <pst-path>` subcommand (kept separate from `import`, which is Gmail/OAuth-specific
and has no positional path argument) — `--db <path>` for consistency with the other subcommands.
Drives Phase 2's walk → Phase 3's parsing → the same `upsert_message`/`upsert_addresses`/
`upsert_attachments` calls `import` already uses; the PST's `fetch_message`/`parse_message`/etc.
are imported aliased (`pst_fetch_message`, ...) to avoid shadowing the Gmail ones already imported
under those names. Deliberately *not* added to `scheduling.py`'s `ALLOWED_COMMANDS` — it's a
one-time local-file import, not something that makes sense to poll on a recurring schedule the way
`import`/`export` do.

Ran the real, full command end-to-end (`mail-utils import-pst data/personal-email-backup.pst --db
<scratch>`): all 262 messages imported cleanly, `stats` and `stats --filter label:Me` both matched
all 262 against the PST-derived label, confirming the folder-as-label integration works identically
to Gmail's own labels through the exact same filter code path.

**Phase 6 — tests — done.**
Two tiers, since there's no existing precedent in this repo for binary-fixture tests (Gmail's own
tests just hand-build small JSON dicts):
- `tests/test_pst_ndb.py` — unit tests for the pure/deterministic NDB-layer pieces that don't need
  a full valid PST: `decrypt_permute`'s decode table is a valid bijection over 0-255, and round-trips
  correctly through the spec's own encode table (`mpbbR`); header-parsing error paths (bad magic,
  ANSI-format rejection, short input); `nid_type`/`make_nid` round-trip. No hand-built BTH/TC byte
  fixtures, in the end — after finding four real spec-layout bugs by *reasoning from first
  principles*, hand-crafting more synthetic fixtures felt like it'd risk encoding the same
  misunderstandings into the tests as into the code being tested; the real fixture below already
  exercises every one of these code paths against ground truth.
- `tests/test_pst_integration.py` — opens `data/personal-email-backup.pst` end-to-end: header sanity,
  full folder-tree walk against the known folder/message counts, all 262 messages parsed with zero
  exceptions and exact counts locked in (`232` with a resolvable `from` address, `183` with body
  text, `1060` attachment rows total), and a regression test scanning every decoded subject for the
  stray leading control character the Subject Prefix bug used to leave. Skipped via
  `pytest.mark.skipif` when the file isn't present, since it's gitignored personal data and won't
  exist in CI — same reasoning as why Gmail's own tests never hit the live API. 89 tests total pass
  (75 pre-existing + 14 new), `ruff check`/`ruff format --check` clean across the whole repo.

**Phase 7 — docs — done.**
`README.md`'s "Project layout" (new `pst/` package, `scripts/`), module list (`pst/`, `db.py`'s
prefixed-id note), `import-pst` subcommand doc, and "Database contents" (`messages.id`'s prefix
scheme, `labels`/`label_ids` now covering both sources) all updated. `RELEASES.md` gained an
undated `## v2.0.0` entry (per this repo's versioning convention, not cut/dated until you explicitly
ask for a release) with a clearly-labeled breaking-change note pointing at the migration script.
`TODO.md`'s item 1 cleared (item 2, Thunderbird import, is now item 1).

## Explicitly out of scope (for now, per `ndb.py`'s own docstring)

ANSI (32-bit) PST format, `NDB_CRYPT_CYCLIC` encoding, CRC/signature verification, and write
support (this app is read-only by design — see `CLAUDE.md`).
