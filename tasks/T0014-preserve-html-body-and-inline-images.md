# T0014: Preserve HTML body content and inline images instead of silently dropping them

- **Status:** available
- **Owner:** none
- **Started:** —
- **Branch:** —
- **Worktree:** —

## Goal

Stop silently discarding real message content. Found during T0013's real-account round-trip testing: a
forwarded HTML email (bold text, a horizontal rule, an embedded company-logo image) was visually confirmed
to lose all of that when synced and restored via `store-in-gmail` — the restored copy showed literal
`*asterisks*` and `----------` dashes instead of rendered formatting, and no image at all.

Root-caused to `gmail_client.py::_extract_body_text`: for any `multipart/alternative` message (both a
`text/plain` and a `text/html` part - the common case for real HTML mail, which usually ships a plain-text
fallback alongside the HTML), it does a depth-first walk and returns the **first `text/plain` part found**,
falling back to `text/html` only when no plain part exists anywhere. So the HTML representation - and any
image referenced only from within it - is discarded at the very first `import-gmail` read, before storage
or `store-in-gmail` ever enter the picture. This is **not a round-trip bug**: mail-utils faithfully stores
and restores whatever it captured (confirmed via T0013's `scripts/gmail-roundtrip-test.py`, which correctly
reports a byte-exact match, since origin and result both carry the same already-degraded plain-text body).
The loss happens earlier, at capture time.

A second, related gap: `parse_attachments` does capture inline-image parts (they carry a `filename`, same
as a conventional attachment), and `--with-attachments` captures their real bytes too - but
`cli.py::_build_eml_message` reattaches every captured attachment as a plain, non-inline MIME part with no
`Content-ID` header. So even if the HTML body were preserved, `<img src="cid:...">` references inside it
would still resolve to nothing after a restore - the image would exist as a regular attachment, not inline.

## Scope

- Change body selection to prefer `text/html` over `text/plain` when both exist (the HTML part is normally
  the richer, more complete representation of what the sender actually intended to be seen) - or determine,
  after investigation, that some other strategy (storing both; converting HTML to a plain-text
  approximation for the `text/plain`-only case) fits better. This is a real design decision, not a given -
  see Approach.
- Preserve `Content-ID` on inline-image attachments through the full round trip (capture in `db.py`'s
  `attachments` schema if not already retrievable via the existing Gmail payload data; re-attach with a
  matching `Content-ID` in `_build_eml_message` so `<img src="cid:...">` references keep resolving after
  `export`/`store-in-gmail`).
- Check whether the Outlook (`outlook/`) and Thunderbird (`thunderbird/`) parsers have an equivalent
  plain-over-html preference or inline-image gap - this task was found via the Gmail path specifically, but
  the other two source formats deserve at least a quick check, even if fixing them turns out to be a
  separate follow-up.
- Decide whether this needs a schema migration (e.g. if both html and plain text end up being stored) and,
  if so, whether existing `data/gmail.db` rows need a resync to benefit (per `CLAUDE.md`'s note: there's no
  auto-migration mechanism, only `CREATE TABLE IF NOT EXISTS`).

## Out of Scope

- Rewriting `store-in-gmail`'s or `export`'s command-line interface - this is a content-fidelity fix, not a
  new feature.
- General HTML sanitization/rendering concerns beyond what's needed to preserve the original content
  faithfully.

## Dependencies

None. Found during **T0013** but independent of it - T0013's own scope (safe testing methodology, go-live
checklist) doesn't depend on this being fixed first.

## Approach

1. Confirm the exact scope of the html-vs-plain preference question with the user before implementing -
   in particular whether both representations should be retained (bigger schema change) or only the richer
   one (simpler, but still lossy relative to the original in a different way).
2. Fix `_extract_body_text` (or its replacement) accordingly, with unit tests covering: html-only,
   plain-only, multipart/alternative with both, and multipart/alternative with html containing an inline
   image.
3. Fix `_build_eml_message` to preserve `Content-ID` for inline-image attachments so restored HTML bodies
   keep resolving their embedded images.
4. Re-run `scripts/gmail-roundtrip-test.py`'s seed/compare cycle (extending its seed set with an
   HTML+inline-image message, since the current 5 don't include one) against a disposable test account to
   confirm the fix holds against the real API, not just mocks.
5. Update `README.md`'s "Database contents" section and any other docs describing what's captured.
6. Note in `CHANGELOG.md` whether this is a breaking change to existing `data/gmail.db` rows (old rows
   captured before this fix keep their already-degraded plain-text body; only a resync picks up the fix).

## Implementation Checklist

- [ ] Design decision confirmed with the user (Approach step 1)
- [ ] `_extract_body_text` fixed, with unit tests for the four MIME shapes listed above
- [ ] `_build_eml_message` preserves `Content-ID` for inline images
- [ ] `scripts/gmail-roundtrip-test.py` extended with an HTML+inline-image seed message; real-account rerun passes
- [ ] Outlook/Thunderbird parsers checked for the same gap (fix or file separately, per findings)
- [ ] Docs (`README.md`, `CHANGELOG.md`) updated

## Test Strategy

Unit tests for the MIME-parsing/rebuilding logic (no real account needed), plus a real-account rerun of
`scripts/gmail-roundtrip-test.py` (see T0013) once its seed set includes an HTML+inline-image message, to
confirm the fix holds against the real Gmail API and not just local parsing.

## Completion Criteria

An HTML email with an inline image, synced via `import-gmail` and restored via `store-in-gmail`, renders
with its original formatting and image intact when viewed in Gmail - verified against a real disposable
test account, not just unit tests.

## Progress Log

## Validation Record

## Completion Record
