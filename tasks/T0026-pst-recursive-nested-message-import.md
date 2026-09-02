# T0026: Make `import-pst --recursive` actually extract nested messages

- **Status:** completed
- **Owner:** @claude
- **Started:** 2026-09-02
- **Ended:** 2026-09-02
- **Branch:** task/T0026-pst-recursive-nested-message-import (merged into task/T0020-full-archive-import-and-eml-roundtrip, deleted)
- **Worktree:** ./work/T0026-pst-recursive-nested-message-import (removed)

## Goal

`import-pst --recursive` currently logs `Recursive: True` and does nothing else with the flag - unlike
`import-gmail --recursive` and `import-thunderbird --recursive`, no nested `message/rfc822`-style embedded
message attachment is ever extracted and indexed as its own row. Implement the same recursive behavior for
PST sources that already exists for Gmail and Thunderbird.

## Scope

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
  contains some; a synthetic fixture should also be added for the unit test suite (see
  `scripts/generate-sample-pst.py` for the existing synthetic-PST-building pattern, if it needs extending).

## Out of Scope

- Any change to Gmail's or Thunderbird's already-working recursive extraction.
- Recursing more than one level deep beyond what the existing Gmail/Thunderbird implementations already
  do (an embedded message that itself embeds another message) - match their existing depth behavior
  exactly, don't extend it.

## Dependencies

Found while working **T0020** (full-archive-import-and-eml-roundtrip), during a performance investigation
of the real `anubex-outlook-backup.pst` import - noticed `_run_import_pst` reads `args.recursive` only to
log it, never to act on it. Not blocking T0020's own completion (the round-trip proof doesn't depend on
recursive nested-message extraction being correct for PST specifically, only on faithfully round-tripping
whatever *is* captured), so it was logged as this separate task rather than fixed inline.

## Approach

1. Study how an embedded message attachment is actually laid out in a PST, per [MS-PST]/[MS-OXCMSG]:
   `PidTagAttachMethod` (0x3705) = `afEmbeddedMessage` (5) marks it; the embedded message itself is a
   full MAPI message object reachable via the attachment row's own subnode B-tree (distinct from the
   `PidTagAttachDataBinary` binary-content path `outlook/messages.py::fetch_attachment_content` already
   reads for regular attachments).
2. Add a function mirroring `fetch_attachment_content`'s shape but for the embedded-message case -
   resolving and returning a `RawMessage` for the nested message, reusing the existing
   `fetch_message`/property-reading machinery rather than duplicating it.
3. ~~Have `parse_attachments` flag which rows are embedded messages~~ - **revised** (see Progress Log):
   a standalone `is_embedded_message_attachment(row)` predicate, operating directly on a raw
   `raw.attachments` Attachment Table row, turned out to be simpler and sufficient - `cli.py`'s
   recursive loop calls it directly, independent of `parse_attachments`'s own (unrelated, DB-row-
   building) job. No `parse_attachments` change was needed at all.
4. Wire `cli.py::_run_import_pst` to recurse into each embedded-message attachment when `--recursive` is
   set, the same shape as `_process_gmail_msg`'s/`_process_tb_message`'s existing recursive loops.
5. Add unit test coverage (synthetic PST fixture with a real embedded-message attachment) and validate
   against the real `anubex-outlook-backup.pst`.

## Implementation Checklist

- [x] Embedded-message attachment detection (`PidTagAttachMethod` = `afEmbeddedMessage`) implemented
      (`is_embedded_message_attachment`)
- [x] Nested-message fetch function implemented, reusing existing MAPI property-reading machinery
      (`fetch_embedded_message`, via a new shared `_fetch_message_from_ref` extracted from `fetch_message`)
- [x] `cli.py::_run_import_pst` recurses into embedded messages when `--recursive` is set
      (`_process_pst_message`, self-recursive like `_process_tb_message`)
- [x] Unit tests added (targeted synthetic fixtures at the function level, not a full synthetic PST file -
      see Test Strategy for why)
- [x] Validated against real embedded messages - found in the much smaller, already-accessible
      `anubex-friends-email.pst` (10 real examples), not the 26 GB file the task's Scope originally
      guessed at

## Test Strategy

Unit tests against small synthetic fixtures at the function level (`tests/test_pst_integration.py`'s
`_FakePSTForEmbeddedMessage`, mirroring the existing `_FakePSTForAttachmentContent` pattern used for
`fetch_attachment_content`) covering `is_embedded_message_attachment` and `fetch_embedded_message`'s
real two-hop resolution chain and its failure paths - not a full synthetic **PST file** extending
`scripts/generate-sample-pst.py`: that generator has no attachment-object support at all yet (confirmed
by reading it), and hand-rolling a byte-correct embedded-message subnode structure there would be a
separate, comparably-sized undertaking for coverage the real archive already gives more directly and
more trustworthily. The real archive (`anubex-friends-email.pst`, 10 real embedded-message attachments
across 8 distinct parent messages) provided the actual end-to-end proof instead (see Validation Record) -
manual, not automated, same rationale as T0020/T0021's own Test Strategy.

## Completion Criteria

- `import-pst --recursive` against a PST containing an embedded-message attachment indexes that nested
  message as its own row, the same way `import-gmail --recursive`/`import-thunderbird --recursive` already
  do for their formats.
- Existing non-recursive PST import behavior is unchanged.

## Progress Log

- 2026-09-02: Logged (not claimed). Found via a routine code-read while investigating T0020's big-file
  import performance - `_run_import_pst` reads `args.recursive` only to print it, the loop body never
  checks it. No design/implementation work done yet.
- 2026-09-02: Claimed, worktree/branch created off T0020's branch tip (after T0021 merged in). Studied the
  real on-disk structure directly against `data/inputs/anubex-friends-email.pst` (which turned out to
  already contain 10 real embedded-message attachments - no need for the 26 GB file at all) before writing
  any code, given how easy it is to guess wrong about an undocumented indirection chain:
  - Confirmed `PidTagAttachMethod` (`0x3705`) **is** already a column on the Attachment Table itself (no
    extra per-attachment PC fetch needed to detect one) - real values seen: `1` (afByValue, 145x) and `5`
    (afEmbeddedMessage, 10x) in this archive.
  - Traced the real resolution chain for `PidTagAttachDataObject` (`0x3701`, same property id as
    `PidTagAttachDataBinary`, distinguished only by its `PtypObject`/`0x000D` type marker instead of
    `PtypBinary`/`0x0102`) by reading the attachment's own Property Context directly: its dwValueHnid was
    consistently `0x80` (a small in-heap HID, [MS-PST] 2.3.3.3's "<=3580 bytes" branch) across all 10 real
    examples - never the large "value is itself a direct subnode NID" branch, which a small fixed-shape
    reference value plausibly never takes regardless of the referenced message's own size. Reading that
    heap item gave an 8-byte descriptor; empirically confirmed (`pst.list_subnodes` on the attachment's own
    subnode BTree) that its first 4 bytes are exactly the embedded message's own NID, scoped to the
    *attachment's* subnode BTree (not the parent message's, and not a top-level NBT entry) - i.e., a
    genuinely separate, undocumented-in-the-spec-summary indirection this task had to establish
    empirically rather than derive from the spec text alone (unlike T0021, where the spec text itself was
    sufficient).
  - Implemented `fetch_embedded_message` in `outlook/messages.py`, extracting a shared
    `_fetch_message_from_ref(pst, bid_data, bid_sub)` out of `fetch_message` (previously inlined there) so
    both the top-level-NID path and the new subnode-ref path build an equally complete `RawMessage`
    (Property Context + Recipient/Attachment Tables) through one code path. Added
    `is_embedded_message_attachment` as a small standalone predicate on a raw Attachment Table row.
  - Wired `cli.py`: new `_process_pst_message`, self-recursive (mirrors `_process_tb_message`'s shape, not
    `_process_gmail_msg`'s single-level-only loop - a genuinely embedded message can itself embed another
    per MAPI's general message-nesting model, so unbounded recursion is the more correct behavior here,
    matching Thunderbird's existing precedent rather than Gmail's more limited one where the two happened
    to already disagree).
  - **Real end-to-end validation**: `import-pst --with-attachments --recursive` against
    `anubex-friends-email.pst`: 685 messages processed (675 top-level + 10 embedded), 683 unique rows
    landed in the database - the 2 "missing" are correct, expected upsert-by-id deduplication, not a bug:
    2 of the 10 embedded messages are real forwarded copies of an email that *also* exists as its own
    top-level message elsewhere in the same mailbox, sharing the same real `Message-ID`
    (confirmed by hand: both landed on the identical `outlook:<4E1B12BF3B8ED711B7FD0008C7DB5016B53D77@
    CPNEXCNT000MSG.unibanco>` id with matching subject/sender). Spot-checked several extracted embedded
    messages by hand: real subjects (`"Fw: glijmiddel"`, `"[Fwd: Fw: Zoek Osama]"`, `"Bobbejaanland"`),
    real senders, real body text (including a real corporate disclaimer), and correctly-populated
    `message_addresses` rows from the embedded message's own Recipient Table.
  - Test suite: 257 passed, 2 skipped (6 new tests in `tests/test_pst_integration.py`). `ruff check`/
    `ruff format --check` clean.

## Validation Record

- 2026-09-02: Full test suite (257 passed, 2 skipped), `ruff check`, `ruff format --check` all pass.
  Real end-to-end validation against `anubex-friends-email.pst` (see Progress Log): `import-pst
  --with-attachments --recursive` correctly extracts and indexes all 10 real embedded-message
  attachments (683 unique messages landed, 2 legitimately deduplicated against pre-existing top-level
  messages sharing the same real Message-ID), with correct subjects/senders/body/addresses throughout.
  Non-recursive PST import behavior unaffected (full suite green, including existing PST integration
  tests). Merged into T0020's branch - see Completion Record.

## Completion Record

- **Ended:** 2026-09-02
- Merged into `task/T0020-full-archive-import-and-eml-roundtrip` (this task's branch was based on it, not
  `main` - see Dependencies). Worktree/branch removed after merge.
- Follow-up for T0020: the 4-archive import should now pick up nested messages from
  `anubex-outlook-backup.pst`/`anubex-friends-email.pst` when it re-runs with `--recursive`, adding
  real rows beyond what its earlier Progress Log entries counted (185,742 messages was without
  recursion).
