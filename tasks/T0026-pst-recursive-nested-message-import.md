# T0026: Make `import-pst --recursive` actually extract nested messages

- **Status:** available
- **Owner:** none
- **Started:** —
- **Branch:** —
- **Worktree:** —

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
3. Have `parse_attachments` flag which rows are embedded messages (vs. regular binary attachments) so the
   caller can tell them apart without re-deriving `PidTagAttachMethod` itself.
4. Wire `cli.py::_run_import_pst` to recurse into each embedded-message attachment when `--recursive` is
   set, the same shape as `_process_gmail_msg`'s/`_process_tb_message`'s existing recursive loops.
5. Add unit test coverage (synthetic PST fixture with a real embedded-message attachment) and validate
   against the real `anubex-outlook-backup.pst`.

## Implementation Checklist

- [ ] Embedded-message attachment detection (`PidTagAttachMethod` = `afEmbeddedMessage`) implemented
- [ ] Nested-message fetch function implemented, reusing existing MAPI property-reading machinery
- [ ] `cli.py::_run_import_pst` recurses into embedded messages when `--recursive` is set
- [ ] Unit tests added (synthetic PST fixture)
- [ ] Validated against a real embedded message in `anubex-outlook-backup.pst`

## Test Strategy

Unit tests against a synthetic PST fixture containing a real embedded-message attachment, mirroring the
existing Gmail/Thunderbird recursive-import test coverage. A manual spot-check against the real archive
confirms the synthetic fixture matches real-world structure.

## Completion Criteria

- `import-pst --recursive` against a PST containing an embedded-message attachment indexes that nested
  message as its own row, the same way `import-gmail --recursive`/`import-thunderbird --recursive` already
  do for their formats.
- Existing non-recursive PST import behavior is unchanged.

## Progress Log

- 2026-09-02: Logged (not claimed). Found via a routine code-read while investigating T0020's big-file
  import performance - `_run_import_pst` reads `args.recursive` only to print it, the loop body never
  checks it. No design/implementation work done yet.

## Validation Record

## Completion Record
