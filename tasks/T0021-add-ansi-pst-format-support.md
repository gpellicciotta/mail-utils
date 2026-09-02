# T0021: Add ANSI PST format support to the Outlook parser

- **Status:** available
- **Owner:** none
- **Started:** —
- **Branch:** —
- **Worktree:** —

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

- [ ] ANSI header parsing implemented
- [ ] ANSI (32-bit) b-tree page parsing implemented
- [ ] Downstream NID/BID-width assumptions audited and fixed where needed
- [ ] Unit tests added (synthetic ANSI-format fixtures, mirroring existing Unicode PST test coverage)
- [ ] `anubex-friends-email.pst` imports successfully end-to-end

## Test Strategy

Unit tests against small synthetic ANSI PST fixtures for the header/b-tree parsing logic, plus a manual
smoke-test import of the real `anubex-friends-email.pst` file (not committed to the repo, too
large/personal - same convention as the other 3 archives T0020 uses).

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

## Validation Record

## Completion Record
