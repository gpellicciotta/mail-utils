---
id: T0026
title: "Make import-pst --recursive actually extract nested messages"
owner: claude
needs: []
branch: "task/T0026-pst-recursive-nested-message-import (merged into task/T0020-full-archive-import-and-eml-roundtrip, deleted)"
worktree: "./work/T0026-pst-recursive-nested-message-import (removed)"
status: completed
started: 2026-09-02
ended: 2026-09-02
---

# T0026: Make `import-pst --recursive` actually extract nested messages

## Objectives & Scope

### Goal

`import-pst --recursive` used to log `Recursive: True` and do nothing else with the flag - unlike
`import-gmail --recursive` and `import-thunderbird --recursive`, no nested `message/rfc822`-style embedded
message attachment was ever extracted and indexed as its own row. Implement the same recursive behavior for
PST sources that already exists for Gmail and Thunderbird.

### Scope

- `outlook/messages.py::parse_attachments` needs to identify an attachment that is itself an embedded
  message (MAPI's `PidTagAttachMethod` = `afEmbeddedMessage` (5), per [MS-OXCMSG] 2.2.2.9 /
  [MS-PST] - the attachment's data is a nested MAPI message object, not opaque binary content) and expose
  enough for the caller to fetch and parse it as a full `RawMessage`, mirroring how
  `gmail_client.py::gmail_extract_attached_messages`/`thunderbird/messages.py::extract_attached_messages`
  already do for their respective sources.
- Wire `cli.py::_run_import_pst`'s loop to actually use the `recursive` flag it already reads: for each
  embedded-message attachment found, recursively `upsert_message`/`upsert_addresses`/`upsert_attachments`
  the nested message too, incrementing the progress counter the same way the Gmail/Thunderbird recursive
  loops already do.
- Verify against a PST containing a real embedded message (a forwarded `.msg` or `.eml` sent as an actual
  attachment, not a plain file attachment) - `data/inputs/anubex-outlook-backup.pst` almost certainly
  contains some; a synthetic fixture should also be added for the unit test suite if needed.

### Out of Scope

- Any change to Gmail's or Thunderbird's already-working recursive extraction.
- Recursing more than one level deep beyond what the existing Gmail/Thunderbird implementations already
  do (an embedded message that itself embeds another message) - match their existing depth behavior
  exactly, don't extend it.

### Dependencies

Found while working **T0020** (full-archive-import-and-eml-roundtrip), during a performance investigation
of the real `anubex-outlook-backup.pst` import - noticed `_run_import_pst` reads `args.recursive` only to
log it, never to act on it. Not blocking T0020's own completion (the round-trip proof doesn't depend on
recursive nested-message extraction being correct for PST specifically, only on faithfully round-tripping
whatever *is* captured), so it was logged as this separate task rather than fixed inline. Branched off
T0020's own branch tip, merged back into it rather than `main` - see Completion Record.

### Completion Criteria

- `import-pst --recursive` against a PST containing an embedded-message attachment indexes that nested
  message as its own row, the same way `import-gmail --recursive`/`import-thunderbird --recursive` already
  do for their formats.
- Existing non-recursive PST import behavior is unchanged.

## Task Implementation and Verification Steps

- [x] [Read] Studied how an embedded message attachment is actually laid out in a PST, per
  [MS-PST]/[MS-OXCMSG]: `PidTagAttachMethod` (0x3705) = `afEmbeddedMessage` (5) marks it; confirmed
  directly against the real archive (`anubex-friends-email.pst`, already on hand and containing 10 real
  embedded-message attachments - no need for the 26 GB file at all) rather than guessing from the spec
  summary alone, given how easy it is to get an undocumented indirection chain wrong.
- [x] [Implement] Embedded-message attachment detection implemented as a standalone
  `is_embedded_message_attachment(row)` predicate, operating directly on a raw `raw.attachments`
  Attachment Table row - simpler and sufficient; no `parse_attachments` change was needed (revised from the
  original plan of flagging rows inside `parse_attachments` itself - see Progress & Validation Log).
- [x] [Implement] Nested-message fetch function implemented (`fetch_embedded_message`), reusing existing
  MAPI property-reading machinery via a new shared `_fetch_message_from_ref` extracted from
  `fetch_message` (previously inlined there), so both the top-level-NID path and the new subnode-ref path
  build an equally complete `RawMessage`.
- [x] [Implement] `cli.py::_run_import_pst` recurses into embedded messages when `--recursive` is set,
  via a new `_process_pst_message`, self-recursive (mirrors `_process_tb_message`'s shape, not
  `_process_gmail_msg`'s single-level-only loop - a genuinely embedded message can itself embed another
  per MAPI's general message-nesting model, so unbounded recursion is the more correct behavior here,
  matching Thunderbird's existing precedent rather than Gmail's more limited one).
- [x] [Verify] Unit tests added: targeted synthetic fixtures at the function level
  (`_FakePSTForEmbeddedMessage`, mirroring the existing `_FakePSTForAttachmentContent` pattern) covering
  `is_embedded_message_attachment` and `fetch_embedded_message`'s real two-hop resolution chain and its
  failure paths - not a full synthetic PST file, since `scripts/generate-sample-pst.py` has no attachment-
  object support at all and hand-rolling a byte-correct embedded-message subnode structure there would be
  a separate, comparably-sized undertaking for coverage the real archive already gives more directly.
- [x] [Verify] Validated against real embedded messages - found in `anubex-friends-email.pst` (10 real
  examples across 8 distinct parent messages), not the 26 GB file the task's Scope originally guessed at.
  Full real end-to-end run: `import-pst --with-attachments --recursive` processed 685 messages (675
  top-level + 10 embedded), 683 unique rows landed (2 "missing" are correct upsert-by-id deduplication -
  see Progress & Validation Log). Test suite: 257 passed, 2 skipped (6 new tests in
  `tests/test_pst_integration.py`). `ruff check`/`ruff format --check` clean.
- [x] [Visual] N/A - no UI surface; parser/CLI-internals work.

## Progress & Validation Log

- 2026-09-02: Logged (not claimed). Found via a routine code-read while investigating T0020's big-file
  import performance - `_run_import_pst` reads `args.recursive` only to print it, the loop body never
  checks it. No design/implementation work done yet.
- 2026-09-02: Claimed, worktree/branch created off T0020's branch tip (after T0021 merged in). Studied the
  real on-disk structure directly against `data/inputs/anubex-friends-email.pst` before writing any code:
  - Confirmed `PidTagAttachMethod` (`0x3705`) **is** already a column on the Attachment Table itself (no
    extra per-attachment PC fetch needed to detect one) - real values seen: `1` (afByValue, 145x) and `5`
    (afEmbeddedMessage, 10x) in this archive.
  - Traced the real resolution chain for `PidTagAttachDataObject` (`0x3701`, same property id as
    `PidTagAttachDataBinary`, distinguished only by its `PtypObject`/`0x000D` type marker instead of
    `PtypBinary`/`0x0102`) by reading the attachment's own Property Context directly: its dwValueHnid was
    consistently `0x80` (a small in-heap HID, [MS-PST] 2.3.3.3's "<=3580 bytes" branch) across all 10 real
    examples - never the large "value is itself a direct subnode NID" branch. Reading that heap item gave
    an 8-byte descriptor; empirically confirmed (`pst.list_subnodes` on the attachment's own subnode
    BTree) that its first 4 bytes are exactly the embedded message's own NID, scoped to the *attachment's*
    subnode BTree (not the parent message's, and not a top-level NBT entry) - a genuinely separate,
    undocumented-in-the-spec-summary indirection this task had to establish empirically rather than derive
    from the spec text alone (unlike T0021, where the spec text itself was sufficient).
  - Implemented `fetch_embedded_message` in `outlook/messages.py`, extracting a shared
    `_fetch_message_from_ref(pst, bid_data, bid_sub)` out of `fetch_message`. Added
    `is_embedded_message_attachment` as a small standalone predicate on a raw Attachment Table row.
  - Wired `cli.py`: new `_process_pst_message`, self-recursive (mirrors `_process_tb_message`'s shape).
  - **Real end-to-end validation**: `import-pst --with-attachments --recursive` against
    `anubex-friends-email.pst`: 685 messages processed (675 top-level + 10 embedded), 683 unique rows
    landed in the database - the 2 "missing" are correct, expected upsert-by-id deduplication, not a bug:
    2 of the 10 embedded messages are real forwarded copies of an email that *also* exists as its own
    top-level message elsewhere in the same mailbox, sharing the same real `Message-ID` (confirmed by
    hand: both landed on the identical id with matching subject/sender). Spot-checked several extracted
    embedded messages by hand: real subjects ("Fw: glijmiddel", "[Fwd: Fw: Zoek Osama]", "Bobbejaanland"),
    real senders, real body text (including a real corporate disclaimer), and correctly-populated
    `message_addresses` rows from the embedded message's own Recipient Table.
  - Test suite: 257 passed, 2 skipped (6 new tests in `tests/test_pst_integration.py`). `ruff check`/
    `ruff format --check` clean.
- 2026-09-02: Full test suite (257 passed, 2 skipped), `ruff check`, `ruff format --check` all pass.
  Real end-to-end validation against `anubex-friends-email.pst`: `import-pst --with-attachments
  --recursive` correctly extracts and indexes all 10 real embedded-message attachments (683 unique
  messages landed, 2 legitimately deduplicated against pre-existing top-level messages sharing the same
  real Message-ID), with correct subjects/senders/body/addresses throughout. Non-recursive PST import
  behavior unaffected (full suite green, including existing PST integration tests).

## Completion Record

- **Ended:** 2026-09-02
- Merged into `task/T0020-full-archive-import-and-eml-roundtrip` (this task's branch was based on it, not
  `main` - see Dependencies). Worktree/branch removed after merge.
- Follow-up for T0020: the 4-archive import should now pick up nested messages from
  `anubex-outlook-backup.pst`/`anubex-friends-email.pst` when it re-runs with `--recursive`, adding
  real rows beyond what its earlier progress-log entries counted (185,742 messages was without
  recursion).
