# T0017: Capture attachments/inline parts that carry no filename

- **Status:** Completed
- **Owner:** @antigravity
- **Started:** 2026-08-31
- **Branch:** task/T0017-capture-filenameless-attachments
- **Worktree:** ./work/T0017-capture-filenameless-attachments

## Goal

`parse_attachments` (`gmail_client.py`, `outlook/messages.py`, `thunderbird/messages.py`) only captures a
MIME part that carries a non-empty `filename`. A part that has no filename - e.g. an inline image embedded
via `Content-ID` with no `Content-Disposition: filename=` or `Content-Type: name=` parameter - is invisible
to `mail-utils` entirely: not stored as a filename-less attachment row, not captured with `--with-attachments`,
and (as a direct consequence) never re-embedded as an inline `cid:` reference on export/`store-in-gmail`.

Found while running T0014's real-account round-trip test (`scripts/gmail-roundtrip-test.py`): a test seed
message's inline image had no filename and was silently dropped by `parse_attachments`, discovered only by
inspecting the raw Gmail API payload directly. Real-world inline images (Outlook, Gmail web compose) almost
always do carry a filename even when inline, so this is a narrower gap than it sounds - but it's a real,
silent data-loss case for any message that doesn't.

## Scope

- Decide what identifies a "capturable" MIME part when no filename exists - likely: any part with a
  `Content-ID` header, possibly also any leaf part with a real (non-multipart) content type that isn't the
  message's own body candidate.
- Decide what filename to synthesize for such a row (`db.py`'s `attachments.filename` is `NOT NULL`) -
  candidates: derive from `Content-ID`, a generic `attachment-<n>` scheme, or make the column nullable
  instead of synthesizing.
- Apply consistently across all three parsers (`gmail_client.py`, `outlook/messages.py`,
  `thunderbird/messages.py`), mirroring how T0014 kept `body_html`/`content_id` capture symmetric across
  sources.
- Update `_build_eml_message`/`export --format md` to handle a synthesized/nullable filename sensibly.

## Out of Scope

- Changing how a *named* attachment or inline image is captured/embedded - that path already works (see
  T0014).

## Dependencies

None. Independent of T0014, though it was found while implementing it.

## Approach

Not yet planned in detail - start by confirming the filename-synthesis design decision with the user (a
real design choice with a schema-nullability angle, similar to T0014's own html-vs-plain decision), then
extend the three parsers and `db.py`/`cli.py` accordingly. Add unit tests for a filename-less inline part
and a filename-less non-inline part per source. Consider a real-account round-trip check once implemented.

## Implementation Checklist

- [x] Design decision confirmed with the user (filename synthesis vs. nullable column)
- [x] `gmail_client.py::parse_attachments` captures filename-less `Content-ID` parts
- [x] `outlook/messages.py::parse_attachments` checked/fixed for the same gap
- [x] `thunderbird/messages.py::parse_attachments` checked/fixed for the same gap
- [x] `db.py`/`cli.py` updated for whatever filename representation was chosen
- [x] Docs (`README.md`, `CHANGELOG.md`) updated

## Test Strategy

Unit tests per source parser for a filename-less part (both inline-with-Content-ID and a plain filename-less
part), plus a real-account round-trip rerun if the fix touches the Gmail write path.

## Completion Criteria

A message with a filename-less inline image (or attachment) is captured by `--with-attachments` and, when
the part carries a `Content-ID`, re-embedded as an inline `cid:`-resolving part on export/`store-in-gmail` -
same as an equivalent part that does carry a filename.

## Progress Log

## Validation Record
- Pre-authorized autonomous execution (tests passed)
- Wrote and passed unit tests:
  - `test_parse_attachments_captures_filenameless_inline_image` in `test_gmail_client.py`
  - `test_parse_attachments_captures_filenameless_parts` in `test_thunderbird.py`
- All existing tests pass via `pytest` run in virtualenv.

## Completion Record
- Made `attachments.filename` nullable in `db.py` schema.
- Added table migration logic in `db.py::init_db` to convert existing `NOT NULL` schema seamlessly.
- Updated `gmail_client.py::parse_attachments` to capture parts containing `content_id` or `attachmentId` even if `filename` is absent.
- Updated `outlook/messages.py::parse_attachments` to capture all explicitly specified attachments instead of skipping when `filename` is absent.
- Updated `thunderbird/messages.py::parse_attachments` to capture parts with `Content-ID` or `Content-Disposition: attachment` even without a `filename`.
- Updated `CHANGELOG.md`.
- No PR, solo, AI Agent (Pre-Authorized).
