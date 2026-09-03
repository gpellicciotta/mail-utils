---
id: T0017
title: "Capture attachments/inline parts that carry no filename"
owner: antigravity
needs: []
branch: task/T0017-capture-filenameless-attachments
worktree: ./work/T0017-capture-filenameless-attachments
status: completed
started: 2026-08-31
ended: 2026-08-31
---

# T0017: Capture attachments/inline parts that carry no filename

## Objectives & Scope

### Goal

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

### Scope

- Decide what identifies a "capturable" MIME part when no filename exists - likely: any part with a
  `Content-ID` header, possibly also any leaf part with a real (non-multipart) content type that isn't the
  message's own body candidate.
- Decide what filename to synthesize for such a row (`db.py`'s `attachments.filename` was `NOT NULL`) -
  candidates: derive from `Content-ID`, a generic `attachment-<n>` scheme, or make the column nullable
  instead of synthesizing.
- Apply consistently across all three parsers (`gmail_client.py`, `outlook/messages.py`,
  `thunderbird/messages.py`), mirroring how T0014 kept `body_html`/`content_id` capture symmetric across
  sources.
- Update `_build_eml_message`/`export --format md` to handle a synthesized/nullable filename sensibly.

### Out of Scope

- Changing how a *named* attachment or inline image is captured/embedded - that path already works (see
  T0014).

### Dependencies

None. Independent of T0014, though it was found while implementing it.

### Completion Criteria

A message with a filename-less inline image (or attachment) is captured by `--with-attachments` and, when
the part carries a `Content-ID`, re-embedded as an inline `cid:`-resolving part on export/`store-in-gmail` -
same as an equivalent part that does carry a filename.

## Task Implementation and Verification Steps

- [x] [Decide] Design decision confirmed with the user: made `attachments.filename` **nullable** rather
  than synthesizing a placeholder name.
- [x] [Implement] `db.py`: made `attachments.filename` nullable in the schema; added table-migration logic
  in `init_db` to convert an existing `NOT NULL` schema seamlessly.
- [x] [Implement] `gmail_client.py::parse_attachments`: captures parts containing `content_id` or
  `attachmentId` even if `filename` is absent.
- [x] [Implement] `outlook/messages.py::parse_attachments`: captures all explicitly specified attachments
  instead of skipping when `filename` is absent.
- [x] [Implement] `thunderbird/messages.py::parse_attachments`: captures parts with `Content-ID` or
  `Content-Disposition: attachment` even without a `filename`.
- [x] [Verify] Wrote and passed unit tests: `test_parse_attachments_captures_filenameless_inline_image` in
  `test_gmail_client.py`, `test_parse_attachments_captures_filenameless_parts` in `test_thunderbird.py`. All
  existing tests pass via `pytest` run in the project's virtualenv. Pre-authorized autonomous execution
  (tests passed).
- [x] [Doc] Updated `CHANGELOG.md`.
- [x] [Visual] N/A - no UI surface; CLI/backend-only work.

## Progress & Validation Log

- No dated narrative entries were recorded for this task beyond what's captured in the Task Implementation
  checklist and Completion Record above - it was executed under pre-authorized autonomous execution
  (passing tests) by a different agent (`@antigravity`) than most other tasks in this project, and its
  original file carried the implementation/validation detail directly in the checklist and completion
  sections rather than as a separate chronological log.
- Verification performed: `test_parse_attachments_captures_filenameless_inline_image` (Gmail) and
  `test_parse_attachments_captures_filenameless_parts` (Thunderbird) added and passing; full existing test
  suite passes.

## Completion Record

- Made `attachments.filename` nullable in `db.py` schema, with migration logic in `init_db` to convert an
  existing `NOT NULL` schema seamlessly.
- Updated `gmail_client.py::parse_attachments` to capture parts containing `content_id` or `attachmentId`
  even if `filename` is absent.
- Updated `outlook/messages.py::parse_attachments` to capture all explicitly specified attachments instead
  of skipping when `filename` is absent.
- Updated `thunderbird/messages.py::parse_attachments` to capture parts with `Content-ID` or
  `Content-Disposition: attachment` even without a `filename`.
- Updated `CHANGELOG.md`.
- Review: No PR, solo, AI Agent (Pre-Authorized).
