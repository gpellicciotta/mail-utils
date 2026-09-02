# T0021: Add ANSI PST format support to the Outlook parser

- **Status:** completed
- **Owner:** @claude
- **Started:** 2026-09-02
- **Ended:** 2026-09-02
- **Branch:** task/T0021-add-ansi-pst-format-support (merged into task/T0020-full-archive-import-and-eml-roundtrip, deleted)
- **Worktree:** ./work/T0021-add-ansi-pst-format-support (removed)

## Goal

`outlook/ndb.py`'s `parse_header` explicitly rejects any PST with `wVer < 23`
(`NotImplementedError: ANSI PST format (wVer=...) is not supported, only Unicode PST`). Extend the parser
to also read the legacy ANSI PST format (Outlook 97-2002, `wVer` 14/15/36/37) so `import-pst` can ingest
these files instead of failing outright.

## Scope

- Add ANSI-format support to the NDB layer (`outlook/ndb.py`): header layout, node/block ID sizes, and
  b-tree page structure all differ from Unicode PST per [MS-PST] 2.2 - see Approach.
- Whatever downstream layers (LTP, property parsing) depend on NID/BID width also need auditing for a
  32-bit vs 64-bit assumption.
- Verify against `data/inputs/anubex-friends-email.pst` (~32 MB, real ANSI-format archive, `wVer=14`) -
  the file that surfaced this gap while working T0020.

## Out of Scope

- Any Unicode-PST-only regression - existing behavior for `wVer >= 23` must not change.
- Full [MS-PST] compliance for every historical PST sub-version beyond what's needed to parse the one real
  file that surfaced this gap; extend further only if another real ANSI PST turns up later.

## Dependencies

Discovered while working **T0020** (full-archive-import-and-eml-roundtrip): `anubex-friends-email.pst` is
ANSI-format and currently fails outright. T0020 is proceeding with its other 3 (Unicode-format) archives
in the meantime; once this task lands, T0020 should import `anubex-friends-email.pst` too and fold it into
its round-trip comparison.

## Approach

1. Study [MS-PST] section 2.2 (Unicode vs. ANSI structural differences): the ANSI header is a different,
   shorter layout (`root_off` differs from the Unicode `180` used today), BIDs/NIDs are 4 bytes instead of
   8, and b-tree pages (`btpage`) use 32-bit entries throughout instead of 64-bit.
2. Branch `parse_header` on `wVer` instead of rejecting the ANSI case, returning a `Header` (or a distinct
   ANSI variant) that downstream code can use to select 32-bit vs 64-bit b-tree page parsing.
3. Extend the b-tree page reader and any other width-sensitive code (`outlook/ndb.py`, and `outlook/ltp.py`
   if it hardcodes width) to branch on format the same way.
4. Validate against `anubex-friends-email.pst`: a full `import-pst --with-attachments --recursive` run
   completes without error and produces plausible message/attachment counts.

## Implementation Checklist

- [x] ANSI header parsing implemented
- [x] ANSI (32-bit) b-tree page parsing implemented
- [x] Downstream NID/BID-width assumptions audited and fixed where needed - `ltp.py` needed none (HIDs
      are always 32-bit in both formats); `outlook/messages.py` and `outlook/tree.py` needed a *different*
      fix than anticipated (default string encoding, not NID/BID width - see Progress Log)
- [x] Unit tests added (targeted synthetic byte-structure fixtures for the ANSI header/b-tree/subnode-
      BTree parsing logic in `tests/test_pst_ndb.py`, not a full synthetic ANSI PST file - see Test
      Strategy for why)
- [x] `anubex-friends-email.pst` imports successfully end-to-end (675/675 messages, 2094 addresses, 145
      attachments, 2.3s)

## Test Strategy

Unit tests against small synthetic ANSI-shaped byte structures (`tests/test_pst_ndb.py`) for the header,
BTPAGE/BTENTRY/BBTENTRY/NBTENTRY, XBLOCK, and SLBLOCK/SIBLOCK parsing logic - built directly at the
`ndb.py` function level (an in-memory `io.BytesIO` "file" plus hand-packed page/block bytes), not a full
synthetic ANSI **PST file** built by extending `scripts/generate-sample-pst.py`: that generator also
builds the HN/BTH/PC layer from scratch, and duplicating all of it a second time for ANSI would be a
comparably-sized undertaking to the ndb.py rewrite itself, for coverage the real archive already gives
more directly. The real, only-actually-ANSI archive on hand (`anubex-friends-email.pst`) provided the
actual end-to-end proof instead (see Validation Record) - manual, not automated, same rationale as
T0020's own Test Strategy (source archives aren't committed to the repo).

## Completion Criteria

- `import-pst` successfully imports `anubex-friends-email.pst` with no crashes and a plausible message
  count.
- Existing Unicode PST behavior is unaffected (full test suite still passes).
- Unit tests cover the new ANSI parsing path.

## Progress Log

- 2026-08-31: Spun off from T0020 after `import-pst` failed immediately on `anubex-friends-email.pst`
  (`wVer=14`, ANSI format) while the other 3 archives (`personal-email-backup.pst`,
  `anubex-outlook-backup.pst`: both `wVer=23`, Unicode; `personal-email-backup.pcv`: Thunderbird, unrelated
  format) parse fine. T0020 continues with those 3 in the meantime.
- 2026-09-02: Promoted to Next Milestone; T0020's dependency is now formal (`TODO.md`: `T0020 (needs
  T0027 T0021 T0026)`) rather than the earlier informal "once this lands, T0020 should import it too" -
  T0020's "three smaller files" round-trip pass explicitly still excludes `anubex-friends-email.pst` until
  this task lands; only the subsequent 4-archive run picks it up. No implementation work done yet - per
  the user's requested work order, **T0027** (comma-splitting bug, unrelated code path) is worked first,
  then this task, then **T0026**.
- 2026-09-02: Claimed, worktree/branch created off T0020's branch tip (after T0027 merged in, `e9dcfa3`) -
  same rationale as T0027: real-data validation needs T0020's `data/inputs` access and tooling, and the
  end result must eventually fold into T0020's own branch anyway.
  - **Exact byte offsets fetched from the real [MS-PST] specification** (learn.microsoft.com/en-us/
    openspecs/office_file_formats/ms-pst), not derived from memory or by analogy - given the cost of a
    silently-wrong offset against real personal email data. Cross-validated the derivation method itself
    against the *existing, known-correct* Unicode code first (recomputed `root_off=180` and
    `bSentinel@512` from the spec's own field-order tables and confirmed they matched the already-shipped
    Unicode implementation exactly) before trusting the same method for the ANSI variant.
  - Implemented in `outlook/ndb.py`: `Header.is_ansi` (from `wVer < 23`, only 14/15 recognized, matching
    the real file), ANSI HEADER (512 bytes total, `bSentinel`@460, root@164/40 bytes) and ROOT (`ibFileEof`
    @4, `BREFNBT`@20, `BREFBBT`@28, all 4-byte fields) layouts, ANSI BTPAGE (`cEnt`@496/`cbEnt`@498/
    `cLevel`@499, no `dwPadding`, `pageTrailer`@500/12 bytes), and BTENTRY(12)/BBTENTRY(12)/NBTENTRY(16)/
    SLENTRY(12)/SIENTRY(8) entry widths - every width-sensitive function now takes an explicit `is_ansi`
    parameter rather than inferring it per-call. Refactored the repeated "resolve BBTENTRY, seek, read,
    round up to 64" pattern (previously duplicated across 4 call sites) into one shared `_read_bbt_block`
    helper while doing this, reducing the risk of missing one of the 4 copies in either format.
  - **First real-data bug, caught immediately by `ib_file_eof`**: after the header/root implementation,
    opened the real `anubex-friends-email.pst` directly and checked `header.root.ib_file_eof` against the
    file's actual on-disk size (33,308,672 bytes) - matched exactly, a strong first confirmation the
    header/root offsets were right before trusting anything built on top of them.
  - **Second real-data bug: wrong assumption about SLBLOCK/SIBLOCK's header size.** Initially assumed (by
    analogy with XBLOCK/BTPAGE, which both keep the same fixed 8-byte header-before-entries offset in
    both formats) that SLBLOCK/SIBLOCK also start their entries at offset 8 for ANSI. Real data
    (`walk_folders` on the real file) immediately hit a `struct.error` buffer-too-short trying to read
    entry 20 of a 20-entry SLBLOCK. Went back to the actual spec instead of guessing again: ANSI
    SLBLOCK/SIBLOCK has **no** `dwPadding` (Unicode-only, existing to keep the following 8-byte-wide
    fields aligned - ANSI's 4-byte-wide fields are already aligned at offset 4 without it), so entries
    start at offset 4, not 8 - the one structure where the *entries' start offset itself*, not just field
    width, differs by format. Fixed via a new `_slblock_entries_off(is_ansi)` helper; added a dedicated
    SIBLOCK-descends-to-SLBLOCK unit test (the case that would have caught this) alongside the SLBLOCK-leaf
    one.
  - **Third real-data bug, found after the above two were fixed and `walk_folders` finally worked**:
    real folder names came back as garbled multi-byte gibberish, not the expected Dutch text. Traced to
    `outlook/tree.py::_row_name` (and, auditing further, `outlook/messages.py::_decode_recipient_rows`/
    `_decode_content_id`/`parse_attachments`) all hardcoding `.decode("utf-16-le")` unconditionally on a
    Table Context row's raw column bytes - which happened to always be correct against every *Unicode*
    PST tested so far (`PidTagDisplayName` etc. are `PtypString` there), but a real ANSI PST stores these
    same properties as `PtypString8` (codepage-dependent 8-bit) instead - confirmed directly by reading
    the raw property (`prop_type=0x1e`, raw bytes already-correct plain text
    `b'Hoofdmap van persoonlijke mappen'`) straight off `read_property_context`, which *is* already
    prop_type-aware and decoded it fine - the bug was specifically in the Table-Context-row read path,
    not property reading itself. This is a real downstream "NID/BID-width assumption" in spirit (an
    ANSI-vs-Unicode PST difference this task's Scope called out to audit for) even though the actual
    mechanism turned out to be string-type width, not NID/BID width. Fixed at the root: `ltp.py::
    read_table_context` now returns `{prop_id: PSTProperty}` per row (same shape as
    `read_property_context`) instead of bare bytes, so every caller reuses the exact same prop_type-aware
    `_decode_string` logic PC-sourced values already used correctly. Updated the 4 affected call sites
    (`tree.py::_row_name`/`_row_nid`, `messages.py::_decode_recipient_rows`/`_recipient_table_summary`/
    `_decode_content_id`/`parse_attachments`/`fetch_attachment_content`) and the 3 existing unit tests
    that hand-constructed the old raw-bytes row shape directly.
  - Full real end-to-end run against `anubex-friends-email.pst`: `import-pst --with-attachments
    --recursive` completed in 2.3s, 675/675 messages, 2094 `message_addresses` rows, 145 attachments,
    all real names/subjects/addresses decoded correctly (verified by hand - Dutch/English text, real
    sender names like "Ambulancier!"/"bram heyns", real attachment `Jeugdwee.xls`).
  - Also ran a full `export --format eml` -> `import-eml` -> `scripts/local-roundtrip-test.py compare`
    against this real data as an extra check (not required by this task's own Completion Criteria, which
    only calls for a successful import): 43 differences, **all** the identical shape (`subject differs:
    '' != None`). Traced to `cli.py::_build_eml_message`'s `if subject: msg["Subject"] = subject` -
    an empty-string subject (common in this casual archive) is treated the same as no subject at all and
    the header is simply omitted, same as the existing `if sender:`/`if recipient:`/etc. guards right next
    to it. **Not an ANSI-specific bug** (would reproduce identically against any Unicode PST with an
    empty-string subject - just never happened to be exercised by the archives tested so far) and not
    something to fix inside this task - flagged here for **T0020** to pick up as another
    `local-roundtrip-test.py` normalization (matching its own precedent of normalizing similar
    non-lossy serialization differences) during its own final round-trip work.
  - Test suite: 251 passed, 2 skipped (22 new/updated in `tests/test_pst_ndb.py`, 3 existing ones in
    `tests/test_pst_integration.py` updated for the new `PSTProperty`-wrapped TC row shape). `ruff check`/
    `ruff format --check` clean.

## Validation Record

- 2026-09-02: Full test suite (251 passed, 2 skipped), `ruff check`, `ruff format --check` all pass.
  Real end-to-end validation against the actual `anubex-friends-email.pst` (the file that originally
  surfaced this gap): full `import-pst --with-attachments --recursive` succeeds, 675/675 messages with
  correctly-decoded real content throughout. A follow-up `export`/`import-eml`/compare cycle against this
  same real data found 43 differences, all one already-understood, non-ANSI-specific, non-lossy pattern
  (empty-string subject vs. no Subject header) - flagged for T0020's own round-trip normalization work,
  not a blocker for this task's own completion. Merged into T0020's branch - see Completion Record.

## Completion Record

- **Ended:** 2026-09-02
- Merged into `task/T0020-full-archive-import-and-eml-roundtrip` (this task's branch was based on it, not
  `main` - see Dependencies). Worktree/branch removed after merge.
- Follow-up for T0020: fold `anubex-friends-email.pst` into the 4-archive `work-mail` import, and add the
  empty-subject-vs-None normalization noted in the Progress Log to `scripts/local-roundtrip-test.py`
  before relying on a clean comparison against it.
