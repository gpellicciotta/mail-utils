---
id: T0014
title: "Preserve HTML body content and inline images instead of silently dropping them"
owner: claude
needs: []
branch: task/T0014-preserve-html-body-and-inline-images
worktree: ./work/T0014-preserve-html-body-and-inline-images
status: completed
started: 2026-08-28
ended: 2026-08-31
---

# T0014: Preserve HTML body content and inline images instead of silently dropping them

## Objectives & Scope

### Goal

Stop silently discarding real message content. Found during T0013's real-account round-trip testing: a
forwarded HTML email (bold text, a horizontal rule, an embedded company-logo image) was visually confirmed
to lose all of that when synced and restored via `store-in-gmail` - the restored copy showed literal
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

### Scope

- Change body selection to prefer `text/html` over `text/plain` when both exist, or determine, after
  investigation, that some other strategy (storing both; converting HTML to a plain-text approximation)
  fits better. This is a real design decision, not a given - see Task Implementation steps.
- Preserve `Content-ID` on inline-image attachments through the full round trip (capture in `db.py`'s
  `attachments` schema if not already retrievable via the existing Gmail payload data; re-attach with a
  matching `Content-ID` in `_build_eml_message` so `<img src="cid:...">` references keep resolving after
  `export`/`store-in-gmail`).
- Check whether the Outlook (`outlook/`) and Thunderbird (`thunderbird/`) parsers have an equivalent
  plain-over-html preference or inline-image gap - this task was found via the Gmail path specifically, but
  the other two source formats deserve at least a quick check, even if fixing them turns out to be a
  separate follow-up.
- Decide whether this needs a schema migration (e.g. if both html and plain text end up being stored) and,
  if so, whether existing `data/gmail.db` rows need a resync to benefit (no auto-migration mechanism,
  only `CREATE TABLE IF NOT EXISTS`).

### Out of Scope

- Rewriting `store-in-gmail`'s or `export`'s command-line interface - this is a content-fidelity fix, not a
  new feature.
- General HTML sanitization/rendering concerns beyond what's needed to preserve the original content
  faithfully.

### Dependencies

None. Found during **T0013** but independent of it - T0013's own scope (safe testing methodology, go-live
checklist) doesn't depend on this being fixed first.

### Completion Criteria

An HTML email with an inline image, synced via `import-gmail` and restored via `store-in-gmail`, renders
with its original formatting and image intact when viewed in Gmail - verified against a real disposable
test account, not just unit tests.

**Met**: verified 2026-08-28 against the disposable `tester.pellicciotta@gmail.com` account (see Progress &
Validation Log) - an HTML email with an inline image, synced via `import-gmail` and restored via
`store-in-gmail`, round-trips with its formatting and image intact.

## Task Implementation and Verification Steps

- [x] [Decide] Confirmed the html-vs-plain design decision with the user via `AskUserQuestion`: **store
  both** `body_text` (plain) and a new `body_html` column, rather than flipping the existing
  plain-vs-html preference. Rationale: most faithful option, no data lost; a schema migration is cheap
  here since `db.py` already has the `_ensure_column` pattern for exactly this.
- [x] [Implement] `db.py`: added `messages.body_html` and `attachments.content_id` columns (both migrated
  via `_ensure_column` for pre-existing databases); `upsert_message`/`upsert_attachments` persist them
  (`.get()`-defaulted so callers that don't know about the new fields don't break).
- [x] [Implement] `gmail_client.py`: new `_extract_body_html` walks the MIME tree independently of
  `_extract_body_text` (which keeps its existing plain-preferred/html-fallback behavior unchanged, for
  `body_text`/`body_mime_type`/FTS/search backward compatibility) so the html part is captured whenever
  present, not only when it's the sole representation. `parse_attachments` now also captures each part's
  `Content-ID` header (`_part_content_id`) - `None` for a conventional attachment, set for an inline image.
- [x] [Implement] `cli.py::_build_eml_message`: when both `body_text` and `body_html` are present, builds a
  real `multipart/alternative` body (plain first, html second) instead of picking one; an attachment with
  both `content_sha256` (real bytes, i.e. `--with-attachments` was used) and `content_id` is embedded via
  `add_related` under the html alternative instead of as a regular attachment, so `<img src="cid:...">`
  keeps resolving. Falls back to existing single-representation behavior when only one side is present, and
  to a regular attachment if there's no html body to embed an inline image into.
- [x] [Implement] `_db_candidates`/`_run_export`: extended SELECTs and attachment dicts to carry
  `body_html`/`content_id` through to `_build_eml_message`.
- [x] [Read] Checked Outlook (`outlook/messages.py`) and Thunderbird (`thunderbird/messages.py`) parsers
  for the same gap - found the identical plain-over-html preference and no inline-image `Content-ID`
  capture.
- [x] [Implement] **Fixed both**, not just filed as a follow-up, since the fix is a small, symmetric
  addition once the schema/CLI side already supports `body_html`/`content_id`. Outlook's
  `PidTagAttachContentId` stores the bare id (no angle brackets, unlike Gmail's raw header capture) -
  normalized to the bracketed form at parse time (`_decode_content_id`) so `cli.py`'s EML builder can
  treat every source's `content_id` uniformly.
- [x] [Implement] `scripts/gmail-roundtrip-test.py`: added a 6th seed message (HTML body + inline image via
  `cid:`, `add_related`); extended `_compare_databases`'s exact-field list with `body_html` and the
  attachment comparison tuple with `content_id`; added `_decoded_inline_parts`/comparison in
  `_compare_exports` since an inline related image isn't returned by `EmailMessage.iter_attachments()`
  and needed its own `Content-ID`-keyed walk.
- [x] [Doc] `README.md`'s "Database contents" section updated for both new columns and the
  multipart/alternative + inline-embedding behavior; `CHANGELOG.md` `vNext` given two bullets.
- [x] [Verify] Full test suite (190 passed, 2 skipped), `ruff check`, `ruff format --check` all pass in the
  worktree.
- [x] [Verify] Real-account rerun of `scripts/gmail-roundtrip-test.py`'s seed/compare cycle against
  `tester.pellicciotta@gmail.com` (a disposable test account with a cached, scope-covering OAuth token, so
  this could run non-interactively) - found and fixed 3 real bugs (see Progress & Validation Log), then
  reached a final `PASS: 7 messages compared, no differences found`.
- [x] [Visual] N/A - no UI surface; CLI/backend-only work (the "visual confirmation" referenced in Goal was
  a manual check of the rendered HTML in the Gmail web UI, not this project's own UI - there is none).

## Progress & Validation Log

- 2026-08-28: Claimed, worktree/branch created.
- 2026-08-28: Confirmed design decision with the user via `AskUserQuestion`: **store both** `body_text`
  (plain) and a new `body_html` column, rather than flipping the existing plain-vs-html preference.
- Implemented: `db.py` (`body_html`/`content_id` columns + migrations), `gmail_client.py`
  (`_extract_body_html`, `Content-ID` capture in `parse_attachments`), `cli.py::_build_eml_message`
  (multipart/alternative + inline embedding via `add_related`, verified empirically that
  `EmailMessage.add_related(cid=...)` sets `Content-ID` to exactly the value passed, so the DB's stored
  value needs to already carry the surrounding `<...>` - true for Gmail's raw header capture),
  `_db_candidates`/`_run_export` (threading the new fields through), Outlook/Thunderbird parsers (fixed the
  identical gap, not just filed as follow-up), and `scripts/gmail-roundtrip-test.py`'s 6th seed message.
  Docs (`README.md`, `CHANGELOG.md`) updated.
- Verified: full test suite (190 passed, 2 skipped), `ruff check`, `ruff format --check` all pass in the
  worktree.
- **Outstanding at that point**: the actual live-account rerun. Flagged to the user rather than claiming
  this was done, since this session had no OAuth-authenticated access at the time.
- 2026-08-28 (later): merged `main` twice more to pick up T0015's `--account`/directory-`--db` changes
  (landed while T0014 was in progress) and the subsequent `v3.0.0` freeze - the freeze conflict was resolved
  by filing T0014's `CHANGELOG.md` bullets under the freshly-opened `### vNext` rather than reopening the
  frozen `v3.0.0` entry, since freezing/unfreezing is a human decision, not an agent's to reverse. One merge
  defect was caught and fixed: the auto-merge left the new 6th seed message's `To` header hardcoded instead
  of picking up main's `--to` parameterization.
- 2026-08-28: user confirmed a disposable test account (`tester`) already existed with a cached, scope-
  covering OAuth token, so the live-account verification could run non-interactively (no browser needed) -
  ran it directly rather than only handing back instructions. Copied the app credential + account file
  into the worktree's (gitignored) `data/` dir; used fresh scratch `--db` directories throughout; never
  touched the `default`/`gio-*`/`katsan` accounts or the main checkout's own database.
  - First full cycle surfaced two real bugs, both caught by the live round trip rather than local unit
    tests, both fixed and covered by new regression tests:
    1. The 6th seed message's inline image had no `filename` (only a `Content-ID`) - Gmail's API only
       reports a `filename` for a MIME part that actually carries one, so `parse_attachments` silently
       never captured it at all (a pre-existing gap in attachment capture generally, not specific to this
       task - logged as a follow-up, see below). Fixed the seed script to set a filename, matching how real
       mail clients embed inline images.
    2. Fixing that then exposed a second, real bug in `_build_eml_message` itself:
       `EmailMessage.add_related()` silently reverts `Content-Disposition` from `inline` to `attachment`
       when `filename` is passed without also passing `disposition="inline"` explicitly - undocumented
       behavior, confirmed empirically. Fixed in the production `_build_eml_message` code, with a new
       regression test asserting both `get_content_disposition() == "inline"` and the filename.
    3. A third bug, unrelated to the first two: for an html-only message, `_build_eml_message`'s
       multipart/alternative branch checked only `if body_text and body_html`, not whether `body_text` was
       genuinely plain - `_extract_body_text`'s existing fallback puts the *same* raw HTML markup into
       `body_text` (with `body_mime_type` `text/html`) that the new `_extract_body_html` also independently
       captures, so the branch wrapped raw HTML in a bogus `text/plain` part. Caught directly: re-importing
       the stored message showed `body_mime_type` flipped from `text/html` to `text/plain`. Fixed by also
       requiring `body_mime_type == "text/plain"` in that branch's condition, with a regression test.
  - After both fixes, re-ran the affected messages through the real API directly (cleared
    `gmail_store_state` for just the affected message, re-ran `store-in-gmail`, re-imported, compared
    fields directly) to confirm each fix in isolation before the final full-cycle confirmation.
  - Final full cycle: `compare` reported **`PASS: 7 messages compared, no differences found (beyond
    expected id/label/timestamp changes)`** - the 7th message being the corrected inline-image seed (the
    original, pre-fix seeding of that message is still sitting in the test mailbox as inert leftover data
    from debugging, distinguishable by a different `Date` header; harmless, cleaned up per the note below).
  - Follow-up **not yet logged to `TODO.md`** at the time: `parse_attachments` (all three source parsers)
    only captures a MIME part that has a `filename` - a part with a `Content-ID` but no filename is
    invisible to `mail-utils` entirely, not just uninlined. Out of scope for T0014 itself (the originating
    bug report's forwarded Outlook logo did have a filename, as do essentially all real-world
    composer-embedded inline images). Logged as **T0017** once `main`'s `TODO.md` was clean of another
    agent's in-progress edit.
- `PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q` (from the worktree, final state): 200 passed, 2
  skipped. `ruff check .`/`ruff format --check .`: clean. Real-account round trip against
  `tester.pellicciotta@gmail.com`: seeded 6 messages (+ 1 corrected replacement after the first two bugs
  above were found), `import-gmail --with-attachments`, `export --format eml`, `store-in-gmail`,
  `import-gmail --with-attachments` on the result, `export --format eml` on the result,
  `scripts/gmail-roundtrip-test.py compare` -> **PASS: 7 messages compared, no differences found**. Local
  scratch databases/exports cleaned up after verification; the disposable account itself still holds the
  seeded/stored test messages under their tracking labels (plus one inert leftover message from
  mid-debugging) - cleanup needs `gmail.modify`, which the cached token doesn't cover, so it needs one
  interactive consent the user should run themselves via `scripts/gmail-roundtrip-test.py cleanup`.
  Review Tier: No PR, solo, AI Agent - summary presented to the user, who gave explicit permission to
  integrate on 2026-08-31.

## Completion Record

- **Completed:** 2026-08-31
- Merged into `main` as a single squash commit (code, `CHANGELOG.md`, `TODO.md` removal, and this task
  file's completion update combined).
- Follow-up filed as **T0017** rather than fixed here - a pre-existing gap (all three parsers require a
  `filename` to capture any MIME part) found via this task's own real-account verification, but out of
  scope for T0014 itself.
- Outstanding, left for the user: run `scripts/gmail-roundtrip-test.py cleanup --account tester --label
  <name> --apply` for the three labels named in the Progress & Validation Log above - needs one interactive
  OAuth consent (`gmail.modify`) this session couldn't complete headlessly.
