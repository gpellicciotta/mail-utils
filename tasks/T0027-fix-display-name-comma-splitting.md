# T0027: Fix unquoted comma in a display name splitting one recipient into bogus extra rows

- **Status:** available
- **Owner:** none
- **Started:** —
- **Branch:** —
- **Worktree:** —

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

- [ ] `quote_unquoted_comma_display_names` implemented in `mime_headers.py`
- [ ] Wired into `outlook/messages.py` and `thunderbird/messages.py` at the existing `@`-fix call sites
- [ ] Unit tests added and passing
- [ ] Full test suite, `ruff check`, `ruff format --check` all pass
- [ ] Re-run against real `work-mail` data confirms the specific identified rows now match

## Test Strategy

Unit tests for `quote_unquoted_comma_display_names` against synthetic header strings covering the cases
in Approach step 3. The real-data confirmation (Approach step 4) is a manual re-run, not an automated
test - same rationale as T0020's own Test Strategy (source archives aren't committed to the repo).

## Completion Criteria

- The specific real-data example in Scope (`outlook:sha1:e84b044ac621de9ead75d0b6f413f1701dc7d3cb` and
  the other messages sharing this pattern) compares clean against origin after re-running `import-eml` +
  the comparison tool.
- Unit tests cover the fix; full test suite and lint stay green.
- Merged into T0020's branch (`task/T0020-full-archive-import-and-eml-roundtrip`).

## Progress Log

- 2026-09-02: Logged. Root cause confirmed by reading `outlook/messages.py::parse_addresses`/
  `mime_headers.py` directly (both only present on T0020's unmerged branch) and cross-checking against
  the real `data/storage/roundtrip-full.log` output - not yet implemented.

## Validation Record

## Completion Record
