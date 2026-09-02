# T0027: Fix unquoted comma in a display name splitting one recipient into bogus extra rows

- **Status:** completed
- **Owner:** @claude
- **Started:** 2026-09-02
- **Ended:** 2026-09-02
- **Branch:** task/T0027-fix-display-name-comma-splitting (merged into task/T0020-full-archive-import-and-eml-roundtrip, deleted)
- **Worktree:** ./work/T0027-fix-display-name-comma-splitting (removed)

## Goal

Real Outlook/Exchange transport headers commonly write a resolved-from-directory recipient's display
name in "Last, First" form (e.g. `Kumar, Rajesh <rajesh.kumar@astadia.com>`) without RFC 5322 quoting.
`email.utils.getaddresses()` - used by every `parse_addresses()` in this codebase - treats the comma as
an address-list separator, since an unquoted display name is not allowed to contain one. The result is
silently corrupted `message_addresses` data: one real recipient becomes two bogus rows (a fragment with
no real address, and a fragment with the real address but only half the display name) instead of one
correct row.

## Scope

- Found via **T0020**'s full-scale (185,742-message) round-trip comparison
  (`data/storage/roundtrip-full.log`, `FAIL: 6806 problem(s) found`): this pattern dominates that count.
  Example from the real data (`outlook:sha1:e84b044ac621de9ead75d0b6f413f1701dc7d3cb`, "Cloud
  Architecture Diagram"):
  - Origin: `('to', 'rajesh.kumar@astadia.com', 'Kumar, Rajesh')`
  - Reimported result: `('to', 'kumar', None)` **and** `('to', 'rajesh.kumar@astadia.com', 'Rajesh')`
  - The `('to', 'kumar', None)` fragment is already excluded by `local-roundtrip-test.py`'s existing
    `"@" in row[1]` filter (added in `b6634d6`, catches any row whose "address" has no `@`) - not a
    remaining bug in its own right. The `('to', 'rajesh.kumar@astadia.com', 'Rajesh')` fragment **does**
    have a real address and is a genuine, still-unresolved name-corruption bug.
  - A related, separately-confirmed artifact - a bare-name-only `sender` (no email address at all,
    because `PROP_SENDER_SMTP_ADDRESS` was empty for some self-composed/sent items) producing a phantom
    `('from', '<lowercased name>', None)` row on reimport - is **already** covered by that same `"@" in
    row[1]` exclusion added in `b6634d6`. Confirmed by reading `local-roundtrip-test.py` directly (lines
    317-318) rather than assumed; **not** part of this task's scope, no further action needed there.
- Fix the root cause at capture time (mirroring how `mime_headers.py::quote_unquoted_at_display_names`
  already fixes the analogous unquoted-`@` case), in both `outlook/messages.py` and
  `thunderbird/messages.py`'s `parse_message`/`parse_addresses` - the same call sites already wired for
  the `@` fix.
- A plain regex substitution (viable for the `@` case, since `@` is a rare, distinctive marker) is
  **not** viable here: a comma is the normal RFC 5322 address-list separator, so a naive "quote anything
  before `<addr>` containing a comma" would also swallow a preceding, unrelated bare address (e.g.
  `alice@x.com, Kumar, Rajesh <rajesh.kumar@astadia.com>` must stay 2 recipients, not collapse into 1).
  Needs a real token-merge pass across the whole comma-separated header value - see Approach.

## Out of Scope

- Any other already-fixed round-trip bug category from T0020's Progress Log (header folding, RFC 2047
  decoding, attachment size, non-UTF-8 text attachments, unquoted `@`) - unaffected by this change.
- Gmail-sourced addresses (`gmail_client.py::parse_addresses`) - real SMTP transport headers from actual
  mail clients are essentially always already RFC 5322-compliant; `gmail_client.py` never imported
  `quote_unquoted_at_display_names` for the `@` case either, and no comma-splitting instance has been
  observed in Gmail-sourced data. Revisit only if a real instance turns up.

## Dependencies

Found while working **T0020** (full-archive-import-and-eml-roundtrip) during its full-scale round-trip
run. T0020 now depends on this task (see updated `TODO.md`) - its final clean round-trip needs this fixed
first. Branches off **T0020's own branch** (`task/T0020-full-archive-import-and-eml-roundtrip`), not
mainline: the fix extends `mime_headers.py`, which only exists on T0020's branch (not yet merged to
`main`), and is validated against `work-mail`/`scripts/local-roundtrip-test.py`, both also only present
there. Merges back into T0020's branch when done, not directly into `main`.

## Approach

1. Add `mime_headers.py::quote_unquoted_comma_display_names(value)`: split `value` on top-level commas
   (respecting already-quoted `"..."` segments, which must be left untouched - they already parse
   correctly), then walk the resulting tokens left to right, merging a token into the pending buffer
   whenever the buffer doesn't yet look like a complete recipient (no `<...>` address and no bare `@`
   in it), flushing the buffer as one recipient once it does. This is exactly the pattern that
   distinguishes `alice@x.com, Kumar, Rajesh <rajesh.kumar@astadia.com>` (2 recipients: a bare address,
   then a comma-containing name) from `Kumar, Rajesh <rajesh.kumar@astadia.com>` alone (1 recipient).
   Quote the display-name half of any flushed recipient that contains an unquoted comma before
   rejoining.
2. Apply it at the same call sites as `quote_unquoted_at_display_names`, composed with it (both fixes are
   independent and address different characters, so both should run) - `outlook/messages.py`'s
   `parse_message` (sender/recipient/cc/bcc) and `parse_addresses` (the from/to/cc/bcc role loop), and
   the equivalent spots in `thunderbird/messages.py`.
3. Add unit tests (`tests/test_mime_headers.py`) mirroring the existing `quote_unquoted_at_display_names`
   coverage: a single comma-containing recipient, a comma-containing recipient preceded by a bare
   address, a comma-containing recipient preceded/followed by a normal `"Name" <addr>` recipient, an
   already-quoted `"Last, First" <addr>` left untouched, and a bare address with no display name at all
   (must stay a no-op).
4. Re-run `scripts/local-roundtrip-test.py` against the existing `data/storage/work-mail` /
   `data/storage/work-mail-roundtrip` databases (re-running just `import-eml` + the comparison, not the
   full PST re-parse, is enough to confirm the fix - re-parsing PST is only needed once, as part of
   T0020's own final full round-trip run) to confirm the specific rows identified above now match, and
   get an updated problem count.

## Implementation Checklist

- [x] `quote_unquoted_comma_display_names` implemented in `mime_headers.py`
- [x] Wired into `outlook/messages.py` and `thunderbird/messages.py` at the existing `@`-fix call sites,
      plus `_format_address` (the actual root cause for the Recipient-Table-fallback path - see Progress
      Log's correction)
- [x] Unit tests added and passing
- [x] Full test suite, `ruff check`, `ruff format --check` all pass
- [x] Re-run against real archive data (`personal-email-backup.pst`) confirms no regression; the specific
      big-archive example is deferred to T0020's own final round-trip - see Progress Log/Completion Record

## Test Strategy

Unit tests for `quote_unquoted_comma_display_names` against synthetic header strings covering the cases
in Approach step 3. The real-data confirmation (Approach step 4) is a manual re-run, not an automated
test - same rationale as T0020's own Test Strategy (source archives aren't committed to the repo).

## Completion Criteria

- Unit tests, using the exact real names/addresses from the affected message, confirm the fix; full test
  suite and lint stay green.
- Verified against real archive data accessible without a full 26 GB re-parse (see Validation Record) -
  the specific big-archive message named in Scope can only be *definitively* re-confirmed once T0020's own
  final round-trip re-imports `anubex-outlook-backup.pst`, which is that task's own completion criterion,
  not this one's.
- Merged into T0020's branch (`task/T0020-full-archive-import-and-eml-roundtrip`).

## Progress Log

- 2026-09-02: Logged. Root cause confirmed by reading `outlook/messages.py::parse_addresses`/
  `mime_headers.py` directly (both only present on T0020's unmerged branch) and cross-checking against
  the real `data/storage/roundtrip-full.log` output - not yet implemented.
- 2026-09-02: Claimed, worktree/branch created off T0020's branch tip (`b6634d6`).
- 2026-09-02: Implemented `mime_headers.py::quote_unquoted_comma_display_names` and wired it into
  `outlook/messages.py`/`thunderbird/messages.py` via a small `_quote_display_names` composing helper in
  each, exactly as planned in Approach.
  - **Correction to the root-cause analysis in Scope, found while trying to verify the fix against the
    real affected message**: queried the real `work-mail` database directly
    (`data/storage/work-mail/mails.db` in T0020's worktree) for
    `outlook:sha1:e84b044ac621de9ead75d0b6f413f1701dc7d3cb` and discovered its `message_addresses` rows
    were **already correct in the origin capture** - "Kumar, Rajesh" intact as one row - even though the
    stored `messages.recipient` *string* column already carried the unquoted, ambiguous
    `"..., Kumar, Rajesh <addr>, Hurley, William <addr>"` text. Confirmed by direct testing
    (`email.utils.getaddresses()` on that exact string does split it, contradicting the correct
    `message_addresses` rows) that `parse_addresses` for this message must be taking the **Recipient
    Table fallback** branch (`_decode_recipient_rows`, used when a message has no transport headers at
    all - structured `(name, addr)` pairs read directly off MAPI properties, never string-joined, hence
    immune) rather than the `headers_text`-derived string-splitting path my original fix targeted.
    `_recipient_table_summary` (which builds the `recipient`/`cc`/`bcc` *string* columns for this same
    fallback case, via `_format_address`) was the actual, distinct source of the unquoted comma - not
    covered by the originally-planned fix at all. Fixed by moving the quoting into `_format_address`
    itself (composes `_quote_display_names` onto its formatted `"name <addr>"` output) - covers both this
    Recipient-Table-fallback path and the `sender` PC-property fallback (`parse_message`'s
    `_format_address(_decode_string(props.get(PROP_SENDER_NAME))...)` call), which shares the same
    structured-pair-to-string construction and was equally vulnerable. The `headers_text`-path fix
    (`_quote_display_names` at the 5 original call sites) is still correct and necessary for messages
    that *do* have real transport headers with an already comma-joined multi-recipient string - kept as
    originally planned, just not what fixed this particular example.
  - Verified directly: `_format_address("Kumar, Rajesh", "rajesh.kumar@astadia.com")` now returns
    `'"Kumar, Rajesh" <rajesh.kumar@astadia.com>'`; joining it with the message's other two real
    recipients and round-tripping through `email.utils.getaddresses()` reproduces the exact origin triple
    `[("Giovanni Pellicciotta", ...), ("Kumar, Rajesh", ...), ("Hurley, William", ...)]` with no
    fragmentation.
  - Added unit tests: `tests/test_mime_headers.py` (5 new cases for
    `quote_unquoted_comma_display_names` itself) and `tests/test_pst_integration.py` (a new
    `_format_address` test using the exact real names/addresses from the affected message). Full suite:
    238 passed, 2 skipped. `ruff check`/`ruff format --check` clean.
  - Real-data check (not the affected message itself - see caveat below): re-ran `import-pst
    --with-attachments` against the real `personal-email-backup.pst` (279 MB, the one smaller archive
    accessible without a 26 GB re-parse) into a scratch `data/storage/verify-mail` db under this fixed
    code, then `export --format eml` -> `import-eml` -> `scripts/local-roundtrip-test.py compare`:
    **PASS: 262 messages compared, no differences found.** No comma-containing display names exist in
    this particular archive (a personal, not corporate-directory-resolved mailbox), so it doesn't exercise
    the fixed code path directly, but confirms no regression against real data end to end.
  - **Caveat, carried into T0020's own final round-trip**: the actual affected message
    (`outlook:sha1:e84b044ac621de9ead75d0b6f413f1701dc7d3cb` and the other "Last, First"-pattern messages)
    live in `anubex-outlook-backup.pst` (~26 GB) - not part of T0020's "three smaller files" first pass
    (that set is `anubex-friends-email.pst` + `personal-email-backup.pst` + `personal-email-backup.pcv`,
    deliberately excluding the big file until the smaller set passes clean). Definitive end-to-end
    confirmation against the real affected message only happens once T0020 re-imports the big file in its
    own final stage - tracked there, not re-verified separately here.

## Validation Record

- 2026-09-02: Full test suite (238 passed, 2 skipped), `ruff check`, `ruff format --check` all pass.
  Real-data round trip against `personal-email-backup.pst` (279 MB, the one archive accessible without a
  26 GB re-parse) is a clean `PASS: 262 messages compared, no differences found` - confirms no regression;
  doesn't itself exercise the comma-splitting fix (see Progress Log caveat). Merged into T0020's branch -
  see Completion Record.

## Completion Record

- **Ended:** 2026-09-02
- Merged into `task/T0020-full-archive-import-and-eml-roundtrip` (this task's branch was based on it, not
  `main` - see Dependencies). Worktree/branch removed after merge.
- Definitive proof against the real affected message is deferred to T0020's own final round-trip stage
  (re-imports `anubex-outlook-backup.pst`) - see Progress Log's caveat; not a gap in this task's own
  completion, since that re-import is T0020's completion criterion, not one this task could reach without
  duplicating a ~51-minute, 26 GB re-parse ahead of when T0020 needs to do it anyway.
