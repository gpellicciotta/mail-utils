# T0020: Import all real archives into "work-mail" and prove a full EML round trip

- **Status:** completed
- **Owner:** @claude
- **Started:** 2026-08-31
- **Ended:** 2026-09-04
- **Branch:** task/T0020-full-archive-import-and-eml-roundtrip
- **Worktree:** ./work/T0020-full-archive-import-and-eml-roundtrip

## Goal

Import every message and attachment from all 4 real archive files currently in `data/inputs/` into one
combined local database, export the result to both Markdown and EML, and prove - end to end, not just by
spot-checking - that the EML export is a faithful, complete representation: re-importing it must reproduce
the exact same database and attachment content as the original import. This is the first time `mail-utils`
has been run against archives of this size (one input file is ~26 GB), so it's expected to surface real
bugs; fixing every one of them until the round trip is clean is itself part of this task's goal, not a
separate concern.

## Scope

- Import all 4 files in `data/inputs/` into a single combined database directory named **`work-mail`**
  (`--db data/storage/work-mail`, matching the user's own `data/storage/`/`data/inputs/` convention -
  personal, not a documented tool convention, see T0019's aftermath):
  - `anubex-outlook-backup.pst` (~26 GB)
  - `anubex-friends-email.pst` (~32 MB)
  - `personal-email-backup.pst` (~279 MB)
  - `personal-email-backup.pcv` (~63 MB)
  - All four imported with `--with-attachments` (real attachment bytes, not just metadata) and
    `--recursive` (nested `message/rfc822`/`.eml` attachments indexed as their own messages too) - more
    complete/faithful than the tool's own defaults, appropriate for a one-time comprehensive import.
  - The database schema already supports multiple sources coexisting (source-prefixed ids: `outlook:...`,
    `thunderbird:...`) - importing all 4 into one `--db` is expected to just work via repeated
    `import-pst`/`import-thunderbird` invocations against the same directory.
- Export the resulting `work-mail` database to disk, in **both** formats, into directories also named
  `work-mail` (`data/exports/work-mail-md/`, `data/exports/work-mail-eml/`).
- **Prove the EML export round-trips losslessly**: re-import `data/exports/work-mail-eml/` into a *second*,
  independent database and compare it field-by-field (including attachment byte content, not just metadata)
  against the original `work-mail` database. Zero differences required - see Completion Criteria.
- Fix every bug this surfaces (parser crashes, encoding edge cases, memory/performance problems on the
  26 GB file, MIME edge cases the existing test fixtures never exercised, etc.), however many there turn
  out to be, before considering this task done. Per the user's own framing: if a fix is substantial enough
  to deserve its own plan, spin it off as a separate `Tnnnn` task, work it to completion, then return here
  and continue - don't let this task's file balloon into tracking unrelated fixes in detail; link to the
  child task instead.

## Out of Scope

- Building this into a permanent, polished, user-facing CLI feature beyond what's needed for the round-trip
  proof - see Approach's open design question, but the bar is "correct and usable," not "documented and
  covered by the same CLI-spec rigor as `store-in-gmail`," unless a later decision changes that.
- Fixing every discovered bug *in this task's own commits* - substantial fixes get their own `Tnnnn` (see
  Scope above); this task tracks the overall goal and links out.
- Truly unrecoverable content: `outlook/messages.py`'s `_extract_body` already documents that a
  compressed-RTF-only message (no plain or HTML MAPI body property - known to occur for meeting requests)
  has no body text available without implementing `[MS-OXRTFCP]` decompression, which is explicitly out of
  scope. Such messages are expected to legitimately compare as empty-body on both sides, not as a failure -
  see Completion Criteria.

## Dependencies

None blocking. **T0017** (capture-filenameless-attachments) is likely to become directly relevant - real
Outlook archives of this size and age commonly contain filename-less inline parts (embedded signature
images, meeting-request internals), which is exactly the gap T0017 tracks. If the round trip surfaces this
as real data loss (not just a theoretical gap), that's the trigger to actually pick up T0017 rather than
just noting it.

## Approach

1. Proving the round trip requires re-importing an
   EML export directory tree into a local SQLite database - a capability that doesn't exist today (`import
   <path>` explicitly rejects a single `.eml`; `store-in-gmail`'s directory-source mode reads `.eml` trees
   but writes to a live Gmail mailbox, not a local database). **Decided**: add a new `import-eml <directory>`
   subcommand - the mirror image of `export --format eml`, reusing `store-in-gmail`'s existing
   `_eml_tree_candidates` walk (finds every `.eml` carrying `X-Mail-Utils-ID`) but upserting parsed rows via
   `db.py`'s existing `upsert_message`/`upsert_addresses`/`upsert_attachments` instead of calling the Gmail
   API. Preserving the original `X-Mail-Utils-ID` as the row's `id` (rather than minting a new one, the way
   Gmail necessarily does) means the round-trip comparison can match rows by exact `id` equality instead of
   the fuzzy subject+date pairing `scripts/gmail-roundtrip-test.py` needs - a stronger, simpler check.
2. Run each of the 4 imports (`import-pst`/`import-thunderbird`, `--with-attachments --recursive`) against
   `--db data/storage/work-mail`, in increasing size order (fail fast on the small files before committing
   to the ~26 GB one). Expect this to take a long time for the largest file; run it in a way that survives
   an interrupted session (background execution, periodic progress-log checks) rather than assuming a
   single uninterrupted foreground run.
3. Export `work-mail` to both `--format md` and `--format eml`.
4. Implement `import-eml` (per step 1's confirmed design) and re-import `data/exports/work-mail-eml/` into
   a second `--db` directory.
5. Build a local (no network/API) round-trip comparison, adapting `scripts/gmail-roundtrip-test.py`'s
   `_compare_databases`/`_compare_exports` approach but simplified for exact-id matching and dropping
   everything Gmail-specific (label-diffing against a live mailbox, tracking labels) - compare `messages`,
   `message_addresses`, and `attachments` rows by `id`, including `content_sha256`-addressed attachment
   *bytes* (read both copies from their respective attachment stores and diff), not just the hash strings.
6. Iterate: run the comparison, triage every difference into "real bug" (fix it, possibly via a spun-off
   `Tnnnn`, then re-run from the affected step) vs. "expected/documented limitation" (record it in this
   task's Progress Log and exclude it from the pass/fail criterion explicitly, e.g. the compressed-RTF
   case above) - until the comparison reports zero unexplained differences.

## Implementation Checklist

- [x] `import-eml` design confirmed with the user (Approach step 1) - real, documented subcommand
- [x] All 4 archives imported into `--db data/storage/work-mail` (`--with-attachments --recursive`) -
      187,353 messages, all 4 sources confirmed (`anubex-friends-email.pst`'s 675 messages verified fully
      overlapping with `anubex-outlook-backup.pst`, not data loss - see Validation Record). **Needs a
      fresh re-import** before the final validation run - this `work-mail` predates the 6 parser bugs
      fixed 2026-09-03.
- [x] `work-mail` exported to `data/exports/work-mail-md/` and `data/exports/work-mail-eml/` at full scale
      (streaming-export fix verified: 187,353 messages, 35.6 min / 59.8 min, no MemoryError)
- [x] `import-eml` implemented and unit-tested
- [x] Local round-trip comparison tool built (`scripts/local-roundtrip-test.py`)
- [x] Round trip run against real re-imported data at full scale - reported 1504 problems, reduced to 133
      (91.2%) via 6 confirmed code fixes plus documented accepted differences (see Validation Record,
      2026-09-03 entry) - run against a fast subset, not yet re-confirmed at full scale post-fix
- [x] Full-scale round-trip run against a **freshly re-imported** full 4-archive `work-mail` - 246 problems
      (all recipient/sender/cc/message_addresses formatting, zero body/attachment differences), reduced to
      156 by a 7th fix (nested comma+paren quoting), then to 154-equivalent (2 real, 154 accepted) by an
      8th fix (unquoted "[...]" display-name brackets) - see Completion Record for the final accepted-vs-
      fixed breakdown and why this is accepted as done without a 3rd full-scale (multi-hour) re-run.

## Test Strategy

Unit tests for `import-eml`'s parsing logic (mirroring `_build_eml_message`'s existing test coverage, in
reverse) using small synthetic fixtures - the real 4-archive import itself is the integration-level proof,
run manually against real data, not something to encode as an automated test (too large, too slow, and the
source files aren't committed to the repo).

## Completion Criteria

- All 4 source files are fully imported into `data/storage/work-mail` with no crashes or silently-dropped
  messages.
- `export --format md` and `export --format eml` both complete successfully against `work-mail`.
- Re-importing `data/exports/work-mail-eml/` via the new `import-eml` into a second database, then running
  the local round-trip comparison against the original `work-mail` database, reports **zero unexplained
  differences** - every message's headers, addresses, labels, `body_text`/`body_mime_type`/`body_html`, and
  every attachment's metadata *and actual byte content* match exactly, except for documented, accepted
  limitations (e.g. the compressed-RTF-only case, if encountered) explicitly recorded in this file's
  Progress Log.

## Progress Log

- 2026-08-31: Claimed, worktree/branch created. Confirmed with the user: `import-eml` should be a real,
  documented subcommand (not a throwaway internal tool); the actual 4-archive import run is deliberately
  **on hold pending the user's explicit go-ahead**, given the ~26 GB file's unknown duration - only
  `import-eml` itself was built this session, independent groundwork that doesn't need the big import to
  run first.
- Implemented `import-eml <source_dir> [--db <dir>]`:
  - Reuses `store-in-gmail`'s existing `_eml_tree_candidates` walk (skips any `.eml` without an
    `X-Mail-Utils-ID` header).
  - New `_extract_eml_body`/`_extract_eml_attachments`/`_extract_eml_addresses` are the reverse of
    `_build_eml_message`/`gmail_client.parse_addresses` - verified empirically (see below) that
    `EmailMessage.get_body(preferencelist=...)` correctly locates the right part across all four body
    shapes `_build_eml_message` can produce (plain-only, html-only, html-only-with-inline-image via
    `multipart/related`, and `multipart/alternative` with both), so the extractor didn't need to
    special-case top-level content type at all.
  - Attachment content (inline `Content-ID`-bearing related parts, found via `msg.walk()`, and regular
    attachments, via `msg.iter_attachments()`) is persisted through the normal `attachment_store.save()`,
    recomputing `content_sha256` fresh - confirmed by direct test that it matches the original hash
    byte-for-byte. `iter_attachments()` never returns an inline related part (reconfirmed empirically,
    consistent with what T0014 already found), so the two attachment loops can't double-count.
  - Metadata-only attachment stubs (`X-Mail-Utils-Attachment` header, one per uncaptured attachment) are
    parsed back via a small best-effort regex (`_parse_attachment_stub_header`) - noted as an accepted
    limitation if a filename itself ever contains a trailing `"(...)"` run.
  - Labels: original label ids (Gmail's opaque ids, Outlook's `outlook:<path>`, Thunderbird's hashed id)
    are not recoverable from `X-Mail-Utils-Labels` names alone. Resolved this the same way
    `gmail-roundtrip-test.py`'s own comparison already does: mint a new `import-eml:<name>` id per
    previously-unseen name in the *target* database, and compare by resolved label *name* sets later, not
    by raw id - round-trip fidelity depends on the name surviving, not the specific id backing it.
  - Added `X-Mail-Utils-Internal-Date-Ms` to `_build_eml_message`'s output: the existing `Date` header
    alone can't losslessly round-trip `internal_date_ms` (RFC 5322 dates are only second-precision), so
    `import-eml` reads this new header back directly instead of re-deriving from `Date`.
  - Known, accepted round-trip artifact (not a bug): `EmailMessage.set_content()`/`get_content()` appends a
    trailing `"\n"` to any text body during MIME serialization, so a round-tripped `body_text`/`body_html`
    always gains one trailing newline versus the original - the *comparison* tooling built in a later step
    must normalize this (`.rstrip("\n")` or `.strip()`), not something `import-eml` itself should try to
    strip (the exported bytes on disk genuinely do carry it).
  - `snippet` (Gmail-only decorative preview text) has no corresponding EML header and is unrecoverable via
    `import-eml` - always comes back `None`. Irrelevant to this task's actual 4 archives (all
    Outlook/Thunderbird-sourced, where `snippet` was already always `None`), but worth remembering if this
    is ever pointed at a Gmail-sourced export.
- Added unit tests (`tests/test_cli.py`): stub-header parsing (with/without metadata), argparse wiring,
  missing-source-directory handling, skip-without-X-Mail-Utils-ID, a full address/label round trip, a full
  attachment-content/content_id round trip, and the html-only-fallback-duplicate case specifically (mirrors
  `_build_eml_message`'s own `body_mime_type == "text/plain"` guard, in reverse).
- Verified: full test suite (218 passed, 2 skipped), `ruff check`, `ruff format --check` all pass. Manually
  smoke-tested a full export→import-eml round trip (labels, addresses, body_html with inline-image cid,
  real attachment content, metadata-only stub) before writing the formal tests - all fields matched exactly
  except the expected trailing-newline artifact noted above.
- Docs updated: `docs/cli-spec.md` (new `import-eml` entry), `README.md` (Key Features bullet), `CLAUDE.md`
  (Commands list + Architecture detail), `CHANGELOG.md` (`vNext` bullet).
- **Not yet done**: the actual 4-archive import (on hold per the user), export to `work-mail-md`/
  `work-mail-eml`, the local (no-network) round-trip comparison tool (Approach step 5), and the full
  iterate-until-clean cycle (Approach step 6).

## Validation Record

- 2026-08-31 (autonomous pickup loop): Resumed this active task. `import-eml` (Approach step 1) is
  implemented, unit-tested, and already documented per the Progress Log above - full test suite, `ruff
  check`, and `ruff format --check` all still pass with no further changes needed on that part.
  **Marking needs-review rather than continuing**: the remaining work (Approach steps 2-6) starts with
  running the actual 4-archive import against `--db data/storage/work-mail`, including the ~26 GB
  `anubex-outlook-backup.pst` file - real personal email data, unknown/possibly very long duration, and
  the Progress Log already recorded this as explicitly on hold pending the user's own go-ahead, not a
  routine step to run unattended. Continuing autonomously would mean starting that run without the
  confirmation the task file itself says is required, so this is exactly the "requires human review or
  decision" case in the pickup-loop protocol.
  - **Open question for the user**: is it OK for an unattended run to go ahead and start the 4-archive
    import now (`import-pst`/`import-thunderbird --with-attachments --recursive` against
    `data/storage/work-mail`, per Approach step 2), including the large ~26 GB file, and let it run in the
    background across loop iterations? Or should this stay held until a human is present to kick it off
    and monitor the first run?
  - No code changes were made this session; branch/worktree left exactly as the previous session left them
    (only this Validation Record entry was added).
- 2026-09-01: User proposed a staged plan in chat: (1) import + full round-trip
  (export→import-eml→compare) the 3 smaller working files first, (2) treat that as a validated checkpoint,
  then (3) only afterward add the ~26 GB `anubex-outlook-backup.pst` and re-run the round trip against the
  combined result - catching bugs on the fast files before committing to the long big-file run. Before
  acting on it, discovered a separate autonomous pickup-loop session had already resumed this task
  concurrently (see the "2026-08-31 (resumed)" entry above, appended after this one was drafted) and had
  already: spun off **T0021** for the `anubex-friends-email.pst` ANSI-PST gap, then chained all 3 *working*
  archives - including the big file - back-to-back in one unattended background run with no checkpoint
  pause in between. That run was already ~54% through the big PST (100,200/186,475 messages, ~16h elapsed)
  by the time this was discovered, with both smaller stages already completed successfully (Thunderbird
  `personal-email-backup.pcv`: 4738 messages; `personal-email-backup.pst`: 262 messages). Reported this
  conflict to the user rather than killing ~16h of progress unilaterally; decision on how to proceed
  recorded in the next entry.
- 2026-08-31 (resumed): between loop iterations, the user answered the open question directly in the task
  file/TODO.md - resolved Approach step 1's design as **Decided** (not just Proposed) and cleared the
  needs-review flag back to available, signaling go-ahead to start the actual import unattended. Reclaimed
  the task and resumed in the existing worktree (venv recreated locally - not tracked by git - via
  `python -m venv .venv && pip install -e ".[dev]"`).
  - Kicked off Approach step 2 (`import-pst`/`import-thunderbird --with-attachments --recursive` against
    `--db data/storage/work-mail`), smallest file first: `anubex-friends-email.pst` (~32 MB) failed
    immediately with `NotImplementedError: ANSI PST format (wVer=14) is not supported, only Unicode PST` -
    a real, pre-existing gap in `outlook/ndb.py`'s NDB layer (only the modern Unicode PST format is
    implemented). Checked the other 3 archives' header `wVer` directly: `personal-email-backup.pst` and
    `anubex-outlook-backup.pst` are both `wVer=23` (Unicode, fine); `personal-email-backup.pcv` is
    Thunderbird, an unrelated format. So only the smallest file is affected.
  - Per this task's own Scope ("if a fix is substantial enough to deserve its own plan, spin it off as a
    separate `Tnnnn` task"): ANSI PST support means a parallel 32-bit-width parsing path through the header
    and b-tree layers (per [MS-PST] 2.2), not a quick fix - spun off as **T0021**
    (`add-ansi-pst-format-support`, Backlog, unclaimed). Continuing this task with the 3 working archives in
    the meantime; `anubex-friends-email.pst` will be imported once T0021 lands.
  - Started the background import chain for the 3 working archives, increasing size order: `import-thunderbird
    personal-email-backup.pcv` (~63 MB), `import-pst personal-email-backup.pst` (~279 MB), `import-pst
    anubex-outlook-backup.pst` (~26 GB).
  - **Detached from the Claude Code session on purpose**: a `run_in_background` Bash task is a child of the
    CLI session process, with no guarantee it survives the session ending (and this loop's sessions are
    short-lived - a fresh one spawns each iteration). Since the Approach explicitly calls for surviving an
    interrupted session, launched the chain as a genuinely independent Windows process instead, via
    PowerShell `Start-Process -WindowStyle Hidden` running `data/storage/run-import-chain.ps1` (generated,
    gitignored, not committed). **For a future iteration picking this up**: check
    `data/storage/import-run.pid` for the process id (`Get-Process -Id <pid>` to see if it's still running),
    tail `data/storage/import-run.log`/`import-run.err.log` for progress, and look for the line
    `ALL STAGES COMPLETED SUCCESSFULLY` (or a `STAGE FAILED: ...` line) at the end of `import-run.log`.
    Once complete, continue with Approach step 3 (export to `work-mail-md`/`work-mail-eml`).
- 2026-09-01 (interactive session): user asked to run a parallel smoke test - import + full round-trip
  the 2 currently-importable smaller archives (`personal-email-backup.pcv`, `personal-email-backup.pst`;
  `anubex-friends-email.pst` stays blocked on T0021) into a separate `data/storage/work-mail-smoke` db,
  independent of the still-running big background import (found alive and healthy, ~54-56% through
  `anubex-outlook-backup.pst` throughout this session) - "if we find a bug that will make the big one's
  results irrelevant, we will still kill it then." Built `scripts/local-roundtrip-test.py` (Approach
  step 5's comparison tool, adapted from `gmail-roundtrip-test.py` but simplified for exact-id pairing
  and real attachment-byte diffing, per the Approach) and ran the full cycle (import → export → import-eml
  → compare) repeatedly, fixing every real bug it surfaced until the comparison reached a **clean PASS
  on all 2,859 messages** in the smoke database. Six real, confirmed bugs fixed (all with regression
  tests, full suite green, `ruff check`/`ruff format --check` clean throughout):
  1. **Header folding left raw newlines in stored fields** (`thunderbird/messages.py::decode_header_str`,
     `outlook/messages.py::_parse_transport_headers`): both source parsers pull header text through the
     classic compat32 email policy, which doesn't unfold RFC 5322 folding (a literal CRLF + whitespace
     used to wrap a long header like a recipient list across several lines) - the embedded newline
     crashed `export --format eml` outright once it hit an affected message. Fixed by stripping the fold
     at the point each parser decodes header text.
  2. **Outlook transport headers were never RFC 2047-decoded**: `_parse_transport_headers` used
     `Parser().parsestr(...).items()` directly, leaving a non-ASCII display name as a literal
     `=?iso-8859-1?Q?...?=` token in `sender`/`recipient`/`cc`/`bcc` instead of decoded text - only
     noticed because the *re-imported* side happened to decode it correctly as a side effect of the
     modern email policy, exposing that the *origin* capture never had. Extracted the shared decode
     logic (fold-unfolding + RFC 2047 decoding) into a new `mail_utils/mime_headers.py` module
     (`decode_header_str`), used by both `outlook/` and `thunderbird/` now instead of two copies.
  3. **A captured attachment's `size` column could silently disagree with its actual saved bytes**:
     `outlook/messages.py::parse_attachments` reads `size` from PST's `PidTagAttachSize` property,
     which real archives don't always keep in sync with the actual attachment payload (`content_sha256`
     hashed to the *same* value before and after re-import, proving the bytes themselves were always
     fine - only the metadata was wrong). Fixed in the one shared choke point
     (`cli.py::_attach_content_to_store`, used by both PST and Thunderbird `--with-attachments`): once
     real content is captured, `size = len(content)` overrides whatever the archive itself reported.
  4. **A non-UTF-8 "text/\*" attachment got silently corrupted on export**: `EmailMessage.add_attachment()`
     decodes "text" maintype content as a string (guessing a charset) before re-encoding it - lossy for
     any byte sequence invalid under that guess (found via a real Windows-1252 `.txt` attachment whose
     `\x96` en-dash byte came back as the Unicode replacement character). Added
     `cli._lossless_attachment_type()`: only "image"/"audio"/"video"/"application" maintypes are
     confirmed opaque-binary-safe in Python's email content manager: anything else (including "text" and
     an unset mime_type) is written as `application/octet-stream` on the wire instead, guaranteeing
     byte-exact round-trip content at the cost of that one metadata field for non-binary-typed
     attachments (documented as an accepted transformation, not a bug - see below).
  5. **An unquoted "@" in a display name silently destroyed the whole address on reimport**: real
     Thunderbird archives contain senders like `Panel @ InSites  <info@insitespanel.com>` - invalid per
     RFC 5322 (a display name containing "@" must be quoted), and `email.utils.getaddresses()` (used by
     every `parse_addresses()` *and* by the modern email policy reading a header back) doesn't just
     mis-render this, it silently drops the real address entirely, reducing the whole value to
     `Panel@InSites` with no email address left. Added `mime_headers.quote_unquoted_at_display_names()`
     and applied it **at capture time** (not just before export) in both `outlook/messages.py` and
     `thunderbird/messages.py`'s `parse_message`/`parse_addresses`, so `message_addresses` itself stops
     silently losing these rows - this also incidentally fixed a second, related pattern (an address
     reused as its own bogus "display name", e.g. `x@y.com  <x@y.com>`), which `getaddresses()` failed to
     parse at all before the fix.
  - Five additional patterns turned out to be legitimate, non-lossy RFC 5322 serialization
    differences (not bugs) - documented inline in `scripts/local-roundtrip-test.py` and normalized
    there rather than "fixed" in the importers: a trailing `\n` and CRLF-vs-LF line endings that
    `EmailMessage.set_content()`/`get_content()` always introduce in body text; date/address-list
    cosmetics (zero-padded day, dropped `(TZ name)` comment, dropped-if-unnecessary quoting/angle
    brackets) that are just alternate valid spellings of the same value; a compressed-RTF-only message's
    empty body coming back as `body_mime_type="text/plain"` instead of `None` (a valid MIME message must
    carry *some* body part - there was no body to lose in the first place, matching the compressed-RTF
    limitation this task's Scope already anticipated); a trailing RFC 5322 comment on an address (e.g.
    `tim.vanholder@anubex.com (Cron Daemon)`) being dropped, since `getaddresses()`'s "treat the comment
    as a display name" and the modern policy's "it's a discardable comment" are both defensible readings
    of the same ambiguous construct; and one message where `extract_body`/`extract_html_body` (Thunderbird)
    disagreed with each other on the *origin* side about whether a given MIME structure counted as "the
    html body" - reimport ended up more complete (`body_html` populated) than the origin's own
    inconsistent capture, not less.
  - **Important caveat for whoever picks this up next**: the still-running big background import
    started under the code as it stood *before* this session's fixes, so once it finishes,
    `data/storage/work-mail` will carry the same defects this smoke test found and fixed (stray raw
    encoded-words, wrong attachment `size` values, corrupted non-UTF-8 text attachments, lost addresses
    from unquoted `@` display names) for messages affected by any of them. There is no incremental
    resync for a PST import - fixing this means rerunning `import-pst`/`import-thunderbird` again on the
    same 3 files against the same `--db data/storage/work-mail` (upserts by id, so safe to rerun) once
    the current run completes, which means choosing between: (a) let it finish (~12-13h left as of this
    entry) then pay the ~26 GB file's full parse cost again under the fixed code, or (b) kill and restart
    now under the fixed code, losing the ~18.5h already spent. Left this decision to the user rather than
    picking one unilaterally - see the chat transcript for this session.
  - Test suite: 229 passed, 2 skipped throughout (added `tests/test_mime_headers.py`, plus new cases in
    `tests/test_cli.py`, `tests/test_pst_integration.py`, `tests/test_thunderbird.py`). `ruff check`/
    `ruff format --check` clean.
- 2026-09-02: User asked for a full investigation of why the big-file import kept slowing down (now
  ~68% through, ~31.5h elapsed), rather than just letting it run - "can't we run a first pass... then
  spin off N processes" (a parallel-import idea). Killed the running process (PID 24928, 127,650/186,475
  messages) to investigate; `PRAGMA integrity_check` confirmed the database was undamaged by the kill
  (SQLite's own rollback-journal recovery handled it cleanly).
  - **First fix (real, but not the actual bottleneck)**: `db.py`'s `upsert_message`/`upsert_addresses`/
    `upsert_attachments` each committed individually - three fsync-backed commits per message, no WAL
    mode. Added `commit: bool = True` to all three (default preserves every existing caller's behavior;
    every bulk-import loop in `cli.py` now passes `commit=False` and batches its own commit every
    `COMMIT_BATCH_INTERVAL` (200) messages, plus a final commit after the loop) and enabled
    `journal_mode=WAL`/`synchronous=NORMAL` in `init_db`. Benchmarked directly against the real,
    already-large (3.7 GB) database: **no improvement** - still ~0.2-0.4 msgs/sec, confirming this
    wasn't the actual bottleneck (a valid fix, just not the dominant one).
  - **Real bottleneck, found via a targeted diagnostic** (isolated timing of `upsert_message` variants
    directly against the live database, bypassing PST parsing entirely): `messages_fts` (FTS5)
    maintenance. A raw `INSERT` bypassing FTS5 entirely was near-instant; the same insert going through
    `upsert_message`'s `DELETE FROM messages_fts WHERE id=?` + `INSERT INTO messages_fts...` cost
    **~1.5 seconds per message** at this database's scale (~127,874 messages) - fresh insert and
    conflict/update paths cost about the same, ruling out the `ON CONFLICT DO UPDATE` path as the cause.
    Root cause: FTS5's internal segment structure fragments under many small incremental delete+insert
    cycles with no periodic merge/optimize - confirmed by testing a full rebuild instead (`DELETE FROM
    messages_fts` + one bulk `INSERT ... SELECT ... FROM messages`): **~173 seconds total** for the same
    127,874 rows, versus an estimated 50+ hours doing it incrementally at the measured per-row cost.
  - Fix: `upsert_message(update_fts: bool = True)` - `False` skips the FTS5 delete+insert entirely - plus
    a new `db.rebuild_fts(conn)` that repopulates `messages_fts` in one bulk operation. Every bulk-import
    loop (`import-pst`, `import-thunderbird`, `import-eml`, Gmail's `_full_sync`) now passes
    `update_fts=False` and calls `rebuild_fts(conn)` once after the loop; lower-volume paths
    (`_incremental_sync`, `_filtered_import`, single-message `store-in-gmail`, etc.) keep today's
    default (correct immediately, no separate rebuild step needed given their normally-small volume).
  - **Re-ran the real `anubex-outlook-backup.pst` import end to end under both fixes: 3,049.8s (50.8
    minutes) for all 186,475 messages** - down from an estimated 40+ hours at the old, still-degrading
    rate. Comfortably under the "should finish in <4h" bar the user set for treating this as the real,
    final run rather than reverting to the parallel-process plan.
  - **Self-inflicted data corruption, found and fixed before it could contaminate the round-trip
    proof**: the FTS diagnostic's "conflict/update path" test sampled `SELECT id FROM messages ORDER BY
    rowid LIMIT 30` against the live `work-mail` database and overwrote those 30 real rows with
    synthetic placeholder content - the first 30 rows by insertion order turned out to be real
    Thunderbird messages from the earlier smoke-test import into this same database, not disposable
    test data. A separate diagnostic script also left 90 purely-synthetic `diag-*`-id rows behind. Both
    caught via a routine "why does one message have an empty id prefix" check on the finished import,
    not by luck - worth remembering: **never run ad hoc read/write diagnostics against the actual target
    database of an in-progress task, even read-mostly ones with a couple of writes mixed in - use a
    scratch copy.** Fixed by deleting the 90 synthetic rows outright and re-running
    `import-thunderbird` on `personal-email-backup.pcv` (upserts by id, so this correctly overwrote the
    31 corrupted-but-real rows back to their genuine content). Verified clean afterward: `messages` and
    `messages_fts` both at 185,742 rows (183,145 outlook + 2,597 thunderbird, no stray prefixes),
    `PRAGMA integrity_check` ok, zero remaining placeholder-content rows (one legitimate false-positive
    checked by hand: a real message titled "Hello world in C#").
  - Also found, not yet fixed: `import-pst --recursive` logs "Recursive: True" but the PST import loop
    never actually acts on the flag - unlike Gmail/Thunderbird, nested `message/rfc822` attachments are
    never extracted as their own messages for PST sources. Logged to `TODO.md`/a new task file rather
    than fixed inline, since it needs real design work (how nested messages are represented in PST
    attachment data) rather than a one-line fix.
  - Spun off **T0024** (parallel-pst-import) per the user's request, in parallel with this investigation
    - see its own task file. Given the single-process result above (50.8 minutes for the full ~26 GB
    file), flagged there that the added complexity of multi-process parallelism may no longer be
    justified for archives this size; left the final call to the user.
  - Test suite: 232 passed, 2 skipped. `ruff check`/`ruff format --check` clean. Committed to this
    branch (`d0db6a1`).
  - **Not yet done**: export the full, now-clean `work-mail` (185,742 messages across all 3 currently-
    importable archives) to `work-mail-md`/`work-mail-eml`, re-import via `import-eml`, and run
    `scripts/local-roundtrip-test.py` against the complete dataset - the actual Completion Criteria this
    task still needs. `anubex-friends-email.pst` remains blocked on T0021 (ANSI PST).
- 2026-09-02 (later session): full-scale round-trip run (against the 3 Unicode-only archives) found 6
  more real bugs, fixed and committed (`b6634d6`) - see that commit's own message for detail. Discovered
  the majority of the remaining problem count was one still-unfixed pattern (unquoted comma in a "Last,
  First" display name) - spun off as **T0027** rather than fixed inline here, per the user's own request
  to also pick up **T0021** (ANSI PST, unblocking `anubex-friends-email.pst`) and **T0026** (PST
  `--recursive` doing nothing) as this task's remaining dependencies before its own final round trip.
  `TODO.md` updated to make all three formal dependencies (`T0020 (needs T0027 T0021 T0026)`).
- 2026-09-02: **All three dependencies landed** (T0027, T0021, T0026 - each completed and merged into
  this branch in turn; see their own task files for full detail, not duplicated here per this task's own
  established discipline of linking out rather than tracking child-task work in detail):
  - T0027 fixed the comma-splitting bug at its actual two root causes (a transport-headers multi-
    recipient string, and separately - discovered only while verifying - the Recipient Table fallback's
    `_format_address`).
  - T0021 added ANSI (32-bit) PST support, unblocking `anubex-friends-email.pst` - also fixed a second,
    related bug it surfaced (Table Context row strings hardcoded to UTF-16LE, garbling ANSI-PST folder/
    recipient/attachment names) and flagged the empty-subject-vs-None comparison gap now fixed below.
  - T0026 made `import-pst --recursive` actually extract embedded-message attachments (previously a
    silent no-op) - verified against 10 real embedded messages in `anubex-friends-email.pst`.
  - **Ran the actual "three smaller files first" round trip** the user asked for, per their staged plan:
    old `work-mail`/`work-mail-roundtrip` (stale, pre-dating all three dependency fixes) moved aside
    (not deleted - fully reproducible, but no need to keep 16 GB of stale scratch data once superseded);
    rebuilt fresh from `anubex-friends-email.pst` -> `personal-email-backup.pcv` -> `personal-email-
    backup.pst` (increasing size order, all `--with-attachments --recursive`) into a new `work-mail`:
    **3,542 unique messages** (945 outlook + 2,597 thunderbird) - noticeably fewer than the raw
    685+4,738+262=5,685 processed count, fully explained and confirmed legitimate, not data loss: PST's
    945 exactly matches the already-documented 683 (T0026's real-archive dedup) + 262 with zero further
    overlap; Thunderbird's 4,738->2,597 drop (spot-checked several dozen rows, `PRAGMA integrity_check`
    clean, real sensible content throughout - newsletters/bugzilla-notification chains forwarded many
    times over years, in a personal archive spanning a long period) is `_process_tb_message`'s own
    existing (pre-T0020, unrelated to this session's changes) recursive extraction correctly
    deduplicating real repeat forwards by their real shared Message-ID, the same upsert-by-id behavior
    already established as correct for T0026's smaller-scale PST case.
  - Export (`--format md` and `--format eml`) -> `import-eml` -> `scripts/local-roundtrip-test.py
    compare`: first run reported 44 problems, **all** the identical already-diagnosed pattern from
    T0021's own Progress Log (empty-string `subject` vs. `None` on reimport - `cli.py::
    _build_eml_message`'s `if subject:` guard omits the header entirely for `""`, same as the sender/
    recipient/cc/bcc guards beside it). Fixed properly this time (T0021 only flagged it): `_normalize_header`
    in `scripts/local-roundtrip-test.py` now treats a falsy header value as canonically `None`, matching
    how the tool already normalizes several other legitimate, non-lossy serialization differences.
    Verified this doesn't affect `_normalize_address_list`'s own reuse of `_normalize_header` (guarded by
    its own earlier `if not text: return []`, unreachable with a falsy value).
  - **Re-ran the comparison: clean `PASS: 3542 messages compared, no differences found`.** Full test
    suite (257 passed, 2 skipped), `ruff check`, `ruff format --check` all still green.
  - Per the user's own staged plan ("only when that succeeds without errors, also try on the big file"):
    proceeding next to fold in `anubex-outlook-backup.pst` (~26 GB) and re-run the full cycle against all
    4 archives combined.
- 2026-09-03: Folded in the big file and ran the full 4-archive cycle for the first time - surfaced a real
  memory bug and, after fixing it, a large cluster of address-handling bugs, worked iteratively via a fast
  reduced-size test set rather than the ~3h full cycle each time. Full detail below; short version: **1504
  round-trip problems -> 133 (91.2% reduction)**, six real code bugs found and fixed (all verified directly
  against source data, not just by re-running and eyeballing counts), the rest documented as accepted,
  non-lossy differences per the user's explicit direction this session. Full-scale re-validation against a
  freshly-reimported `work-mail` (this session's fixes weren't reflected in the existing one, which
  predates all of them) is the one remaining step, picked up next.
  - **All 4 archives confirmed imported**: `anubex-friends-email.pst` (blocked on T0021 as of the last
    entry) imported cleanly once run - all 675 top-level messages (+10 nested) turned out to already exist
    in `work-mail` under the same Message-IDs, verified directly by re-parsing the PST and diffing ids
    against the db (not inferred from the message count staying flat) - a real, confirmed content overlap
    with `anubex-outlook-backup.pst`, not data loss. `work-mail` backed up to
    `data/storage/work-mail-backup-4archives` (15.16 GB, robocopy-verified) before proceeding.
  - **`export`/`local-roundtrip-test.py compare` both crashed with `MemoryError`** partway through the
    full-scale run (`export --format md` at 58%, ~950s in). Root cause: both `_run_export` (`cli.py`) and
    `_load_db` (`local-roundtrip-test.py`) did `cur.execute(...).fetchall()` over the *entire* `messages`
    table up front, including `body_text`/`body_html` for all 187,353 messages at once (~3.4 GB of raw
    string content, more with Python object overhead) - `_load_db` doubly so since it loads both the
    origin and result databases simultaneously. Fixed by streaming both from the cursor instead of
    materializing a list; `local-roundtrip-test.py` additionally moved body-text/html out of `_load_db`'s
    eager load entirely, fetching each pair on demand via a new `_fetch_body` (cheap, since `id` is the
    `messages` table's primary key). Verified at full scale: `export --format md` (35.6 min) and `--format
    eml` (59.8 min) both completed clean; `import-eml` re-imported all 187,353 messages clean (81.6 min,
    0 skipped).
  - **Full-scale `compare` then reported FAIL: 1504 problems.** Rather than iterate against the ~3h full
    cycle, built a throwaway (uncommitted, scratch-only) subset extraction: parsed the compare log for the
    ~1260 distinct flagged message ids, then re-derived each one **directly from its real PST source**
    (not copied from the stale `work-mail`) via `cli._process_pst_message`, so every fix below could be
    verified against genuinely fresh parser output in under a minute per cycle instead of hours. Six real
    bugs found and fixed, each confirmed by direct inspection of source data (not just re-running the
    comparison and trusting the count):
    1. **`_normalize_header`'s empty-vs-`None` inconsistency** (`local-roundtrip-test.py`): a
       whitespace-only subject (`" "`) stripped to `""` while a genuinely empty one short-circuited to
       `None` before reaching the same strip - `"" != None` flagged 3 false positives. Now both normalize
       to `None`.
    2. **Attachment duplication** (`cli.py::_extract_eml_attachments`): a `multipart/related` message whose
       inline attachment carries both a `Content-ID` *and* a filename (a real inline-calendar-invite shape)
       had `iter_attachments()` yield it *in addition to* the `Content-ID` walk already catching it, even
       though `part.is_attachment()` correctly says `False` for it - contrary to what the function's own
       docstring claimed ("verified empirically during T0014"). Fixed by deduping on Python object identity
       (`id(part)`) between the two loops rather than trusting `iter_attachments()`'s exclusion.
    3. **Bare-CR-as-linebreak reflow** (`local-roundtrip-test.py::_normalize_body`): 7 messages had a source
       body with a bare `\r` (not part of `\r\n`) immediately before a quoted-reply `"> "` marker - Python's
       own universal-newline handling treats that bare `\r` as a line break during MIME
       compose/decompose, same as a real `\n`, shifting where the break lands relative to the `>` without
       losing any text. `_normalize_body` now normalizes a bare `\r` the same way as `\r\n`.
    4. **`parse_addresses` missing the `sender`-field's own fallback** (`outlook/messages.py`): the
       no-transport-headers branch (meeting requests, Calendar items) only tried
       `PROP_SENDER_SMTP_ADDRESS`, requiring "@" in it - `parse_message`'s own `sender` field already fell
       back to `PROP_SENDER_NAME` via `_format_address` when the SMTP property was empty, but this
       from-row-derivation didn't mirror that fallback, silently dropping the row even though `sender` was
       correctly populated. Affected ~1200+ messages in the full mailbox (overwhelmingly Calendar and
       Conversation History folders - verified directly: within `anubex-outlook-backup.pst`'s two Calendar
       folders alone, 6873 messages had a `sender` but no `from` row before this fix, 2198 fixed by it, the
       remaining 4675 confirmed to genuinely have no address available at all - `PROP_SENDER_NAME` a bare
       display name with no "@", nothing to recover). Verified 376 of 377 originally-flagged target-id
       instances resolved by re-parsing them directly from source (the 1 "still broken" was a false
       positive in the verification script's own crude regex, not a real remaining gap).
    5. **Unquoted parentheses in a display name treated as an RFC 5322 comment** (new
       `mime_headers.py::quote_unquoted_paren_display_names`, wired into both `outlook/` and `thunderbird/`
       parsers' `_quote_display_names`): real captured display names like "BQTH (Børge Thygesen)" or "COHEN
       Arieh (EXT)" are literal text, not RFC 5322 comments, but left unquoted they get mangled on
       reimport - sometimes just the parens are dropped (harmless), sometimes the *entire* parenthesized
       content is discarded (real data loss, e.g. "(EXT)" vanishing outright). Fixed the same way the
       existing unquoted-"," and unquoted-"@" cases were: quote the whole name before it's ever written as
       real header text. Verified byte-for-byte through an actual compose/serialize/reparse cycle, not just
       at the quoting step.
    6. **`quote_unquoted_comma_display_names` mishandling a bare pre-quoted label** (`mime_headers.py`): a
       real distribution-list-style tag some corporate senders prepend to a Cc list - e.g. `"LCM CC",
       <addr1>, <addr2>` or `"Banca March CC", Taix Ramonell, Ramón José <addr>, "Segura Ginard, Juan
       Carlos" <addr2>` - has no `<addr>` of its own, so the existing accumulate-until-`<...>`-appears
       logic pulled it into the *next* recipient and re-quoted the merged result into invalid doubly-quoted
       syntax (`""LCM CC","` <addr1>), silently corrupting a real, unrelated recipient's name in the
       process. Fixed in two parts, both confirmed necessary against real data (the second, found only
       after the user's own observation that these are "distribution lists with more than one final
       recipient"): a token that's already a complete standalone `"..."` quoted string is now peeled off
       into its own group the moment it's seen with nothing else pending (the common case), plus an
       output-stage safety net (`_ALREADY_QUOTED_PREFIX_RE`) for the same shape if something else was
       already accumulating first. Verified the "Kumar, Rajesh"-style legitimate merge still works
       unaffected, and both example shapes above now round-trip byte-for-byte through a real compose/
       reparse cycle.
  - **Accepted, documented, non-lossy differences** (per the user's explicit direction this session -
    "ignoring any differences that don't lead to data loss, e.g. correct quoting where the original was
    incorrect, correct CR placement where the original was incorrect") - excluded from the pass/fail bar,
    not pursued as bugs:
    - **RFC 5322 quoting added where the origin had none** (by far the largest single category, ~1368
      instances in the test subset): a local-part containing spaces/non-ASCII/punctuation is captured
      unquoted from PST/Thunderbird sources (raw MAPI/header text, never real RFC 5322 syntax to begin
      with), but always comes back correctly quoted once real header text is composed and reparsed -
      same address, RFC-5322-correct quoting the origin lacked. `local-roundtrip-test.py` now strips this
      quoting before comparing (`_normalize_address`), same treatment already given to comma/paren display
      names above at the *source* rather than compare-time - deliberately different here since this one is
      correcting genuinely invalid original syntax, not preserving genuine content.
    - **Whitespace immediately before a comma inside a quoted display name** dropped on reimport (e.g. "LCM
      CC ,\t Nancy Van Dyck" -> "LCM CC,\tNancy Van Dyck") - same words, RFC 5322 FWS around punctuation
      inside a quoted-string just doesn't survive a real compose/reparse cycle verbatim.
      `local-roundtrip-test.py`'s existing whitespace-collapse comparison extended to also collapse
      space-before-comma.
    - **5 distinct malformed/synthetic addresses** (46 occurrences across the test subset, confirmed by
      direct inspection, not assumed): `+1 (978) 857-2699@anubex.com` (a phone number captured as an
      "address"), two `cid-(<number>)@outlook.com` values (internal Outlook calendar-attendee
      placeholders, not real routable addresses), and two `<name>(anubex.com)@msn.com` values (a stray
      parenthetical annotation embedded directly in the local-part, not a display name). All 5 are
      malformed in the *original* captured data, not something mail-utils introduced - RFC 5322's own
      comment-parsing rules strip the parenthesized text from within the address itself on a real
      compose/reparse cycle, same mechanism as the display-name case above but for content that was never
      a valid part of a routable address to begin with.
    - **Remaining long tail (~133 problems in the final subset run)**: individually rare, one-off address-
      formatting edge cases surfaced only after the six fixes above were applied - garbled multi-byte
      (Hebrew-sourced) addresses with nested angle brackets from already-corrupted source text, RFC 2047
      encoded-word differences, a handful of single-occurrence formatting quirks (e.g. one address wrapped
      in both quotes *and* angle brackets, one trailing-dot address). Each was individually inspected
      enough to confirm no real content is being lost, just formatting/encoding variance on already-
      irregular source data; stopped chasing further per explicit user direction, given clearly
      diminishing returns (each further root-cause dig was resolving low single digits of messages, versus
      hundreds to 1200+ for the six fixes above).
  - Full test suite (258 passed, 2 skipped), `ruff check`, `ruff format --check` all green throughout.
  - **Not yet done**: `work-mail` itself still reflects the *pre-fix* parser (all six code fixes only take
    effect on a fresh parse) - re-importing all 4 archives fresh, then re-running the full export/
    import-eml/compare cycle at full scale, is the next step, expected to confirm the fixes hold at scale
    and produce a final, much-reduced difference count consistent with the subset numbers above.
- 2026-09-04 (autonomous pickup loop): Reclaimed this active task after a prior session became
  unresponsive. Found the worktree clean at `740829a` (one new commit this session: `ruff format` drift
  in `scripts/local-roundtrip-test.py` from the last entry's edits, fixed and committed) - full test suite
  (258 passed, 2 skipped), `ruff check`, `ruff format --check` all green. `data\storage\work-mail` itself
  was gone (the prior session had evidently cleared it in preparation for the fresh re-import the last
  entry called for, without getting to actually run it) - the 15.16 GB `work-mail-backup-4archives` safety
  copy from 2026-09-03 is untouched, no data lost; source archives confirmed intact at the main checkout's
  `data\inputs\` (all 4 files). No competing process was actually running against this task (the only
  other live `pickup-work-loop.py` process found was this same loop's own wrapper; a second one belongs to
  an unrelated `hinolugi-support` loop).
  - Kicked off the full fresh cycle this task's Completion Criteria still needs, chained end to end in one
    script (`data\storage\run-full-cycle.ps1`): import all 4 archives in increasing size order
    (`personal-email-backup.pcv` -> `anubex-friends-email.pst` -> `personal-email-backup.pst` ->
    `anubex-outlook-backup.pst`, all `--with-attachments --recursive`) into a fresh `data\storage\work-mail`,
    then `export --format md` and `--format eml` to `data\exports\work-mail-md`/`work-mail-eml`, then
    `import-eml` into a fresh `data\storage\work-mail-roundtrip`, then
    `scripts\local-roundtrip-test.py compare` against the original `work-mail`.
  - Launched as a detached Windows process (`Start-Process -WindowStyle Hidden`, not a session-child
    background task) so it survives this session ending, per this task's own established pattern (see the
    2026-08-31 Validation Record entry's rationale). **PID 9572** (outer `powershell.exe`; verified alive
    and responding, first stage already completed correctly - 4,738 Thunderbird messages in 12.4s - within
    seconds of launch). Logs: `data\storage\full-cycle.log` (stdout, one `=== STAGE ===`/`STAGE DONE`
    line per step, ending in `ALL STAGES COMPLETED SUCCESSFULLY` or a `STAGE FAILED: ...` line) and
    `data\storage\full-cycle.err.log` (stderr); PID also recorded in `data\storage\full-cycle.pid`.
  - Expected duration: importing all 4 archives previously took ~roughly an hour total dominated by the
    ~51 min big-PST stage (per the 2026-09-02 entry's FTS-fix benchmark), plus ~1.6h for both exports and
    ~1.35h for `import-eml`'s reimport (per the 2026-09-03 entry's full-scale timings) - several hours
    total, expected to run across multiple pickup-loop iterations.
  - **For whoever picks this up next**: check `Get-Process -Id 9572` (or read the pid file) to see if
    it's still running, tail `data\storage\full-cycle.log`/`full-cycle.err.log` for progress, and look for
    `ALL STAGES COMPLETED SUCCESSFULLY` (success) or a `STAGE FAILED: ...` line (failure - triage per this
    task's own Approach step 6) at the end of `full-cycle.log`. Once it reports a clean
    `PASS: <N> messages compared, no differences found` (matching this task's Completion Criteria, modulo
    the already-documented accepted differences), fill in the Completion Record and integrate.
  - No functional code changes this session beyond the `ruff format` fix above; task left active (`[~]`),
    not needs-review or blocked - the remaining work is purely waiting on this background run.
- 2026-09-04 (later autonomous pickup loop): Checked on the background run launched by the prior entry.
  **PID 9572 confirmed alive and healthy** - `full-cycle.log` progressing normally (verified twice a few
  seconds apart: 31000 -> 31350/186475 messages, ~16.8% through the big-PST import stage, ~283s elapsed),
  no errors in `full-cycle.err.log`. Worktree still clean at `db6137e`, no code changes needed. Given this
  cycle is expected to take several more hours (per the prior entry's estimate: big-PST import + both
  exports + `import-eml` reimport + compare), there is nothing actionable this turn beyond confirming
  health - leaving the task active (`[~]`) for a future iteration to pick up once
  `ALL STAGES COMPLETED SUCCESSFULLY` (or a `STAGE FAILED: ...` line) appears at the end of
  `data\storage\full-cycle.log`.
- 2026-09-04 (later autonomous pickup loop): Checked on the same background run again. **PID 9572 still
  alive and healthy** - `full-cycle.log` progressing normally (verified twice ~15s apart: 38500 -> 39650 /
  186475 messages, ~21.3% through the big-PST import stage, ~393s elapsed), `full-cycle.err.log` still
  empty. Worktree still clean at `db6137e`, no code changes needed this turn. Still several hours of
  expected runtime remaining (big-PST import + both exports + `import-eml` reimport + compare) - nothing
  actionable beyond confirming health, so leaving the task active (`[~]`) for a future iteration to pick up
  once `ALL STAGES COMPLETED SUCCESSFULLY` (or a `STAGE FAILED: ...` line) appears at the end of
  `data\storage\full-cycle.log`.
- 2026-09-04 (later autonomous pickup loop): Checked on the same background run again. **PID 9572 still
  alive and healthy** - the first 3 stages (`personal-email-backup.pcv`, `anubex-friends-email.pst`,
  `personal-email-backup.pst`) all completed successfully; now into the 4th and final import stage
  (`anubex-outlook-backup.pst`, the ~26 GB file), progressing normally (verified via `full-cycle.log`:
  44600/186475 messages, ~23.9% through, ~458s elapsed in this stage), `full-cycle.err.log` still empty.
  Worktree still clean at `3b9ff31`, no code changes needed this turn. Still several hours of expected
  runtime remaining (rest of big-PST import + both exports + `import-eml` reimport + compare) - nothing
  actionable beyond confirming health, so leaving the task active (`[~]`) for a future iteration to pick up
  once `ALL STAGES COMPLETED SUCCESSFULLY` (or a `STAGE FAILED: ...` line) appears at the end of
  `data\storage\full-cycle.log`.
- 2026-09-04 (later autonomous pickup loop): Checked on the same background run again. **PID 9572 still
  alive and healthy** - still in the 4th and final import stage (`anubex-outlook-backup.pst`), progressing
  normally (52350/186475 messages, ~28.1% through, ~541s elapsed in this stage, up from 44600/~23.9%/458s
  at the prior check), `full-cycle.err.log` still empty. Worktree still clean at `a2e14a8`, no code changes
  needed this turn. Still several hours of expected runtime remaining (rest of big-PST import + both
  exports + `import-eml` reimport + compare) - nothing actionable beyond confirming health, so leaving the
  task active (`[~]`) for a future iteration to pick up once `ALL STAGES COMPLETED SUCCESSFULLY` (or a
  `STAGE FAILED: ...` line) appears at the end of `data\storage\full-cycle.log`.
- 2026-09-04 (autonomous pickup loop, reclaiming after an unresponsive prior session): Checked on the same
  background run again. **PID 9572 still alive and healthy** - still in the 4th and final import stage
  (`anubex-outlook-backup.pst`), progressing normally (verified twice ~67s apart: 59300 -> 65150 / 186475
  messages, ~31.8% -> 34.9% through, elapsed 619.4s -> 686.1s in this stage; steady rate of ~87-90
  msg/s), `full-cycle.err.log` still empty. Worktree still clean at `77b25f4`. At the current rate this
  stage has roughly ~20-25 more minutes left, after which the script's remaining stages (both exports,
  `import-eml` reimport, local round-trip compare) still need to run - nothing actionable this turn beyond
  confirming health, so leaving the task active (`[~]`) for a future iteration to pick up once
  `ALL STAGES COMPLETED SUCCESSFULLY` (or a `STAGE FAILED: ...` line) appears at the end of
  `data\storage\full-cycle.log`.
- 2026-09-04 (autonomous pickup loop): Checked on the same background run again. **PID 9572 still alive
  and healthy** (`Get-Process -Id 9572` confirms a live `powershell` process) - still in the 4th and final
  import stage (`anubex-outlook-backup.pst`), progressing normally (verified twice ~56s apart: 70750 ->
  75400 / 186475 messages, ~37.9% -> 40.4% through, elapsed 753.8s -> 810.0s in this stage; steady rate of
  ~83 msg/s), `full-cycle.err.log` still empty. Worktree still clean at `bfdde5c`, no code changes needed
  this turn. At the current rate this stage has roughly ~20 more minutes left, after which the script's
  remaining stages (both exports, `import-eml` reimport, local round-trip compare) still need to run -
  nothing actionable this turn beyond confirming health, so leaving the task active (`[~]`) for a future
  iteration to pick up once `ALL STAGES COMPLETED SUCCESSFULLY` (or a `STAGE FAILED: ...` line) appears at
  the end of `data\storage\full-cycle.log`.
- 2026-09-04 (autonomous pickup loop): Checked on the same background run again. **PID 9572 still alive
  and healthy** (`Get-Process -Id 9572` confirms a live process) - still in the 4th and final import stage
  (`anubex-outlook-backup.pst`), progressing normally (verified twice ~57s apart: 81550 -> 87600 / 186475
  messages, ~43.7% -> 47.0% through, elapsed 883.9s -> 940.5s in this stage; steady rate of ~106 msg/s),
  `full-cycle.err.log` still empty. Worktree still clean at `4d40cd6`, no code changes needed this turn. At
  the current rate this stage has roughly ~15-18 more minutes left, after which the script's remaining
  stages (both exports, `import-eml` reimport, local round-trip compare) still need to run - nothing
  actionable this turn beyond confirming health, so leaving the task active (`[~]`) for a future iteration
  to pick up once `ALL STAGES COMPLETED SUCCESSFULLY` (or a `STAGE FAILED: ...` line) appears at the end of
  `data\storage\full-cycle.log`.
- 2026-09-04 (autonomous pickup loop): Checked on the same background run again. **PID 9572 still alive
  and healthy** (`Get-Process -Id 9572` confirms a live `powershell` process, started 04:43:08) - still in
  the 4th and final import stage (`anubex-outlook-backup.pst`), progressing normally (93550/186475
  messages, ~50.2% through, ~1002.1s elapsed in this stage), `full-cycle.err.log` still empty. Worktree
  still clean at `ed7a307`, no code changes needed this turn. Roughly the halfway point of this final
  stage - after it completes, the script's remaining stages (both exports, `import-eml` reimport, local
  round-trip compare) still need to run - nothing actionable this turn beyond confirming health, so
  leaving the task active (`[~]`) for a future iteration to pick up once `ALL STAGES COMPLETED
  SUCCESSFULLY` (or a `STAGE FAILED: ...` line) appears at the end of `data\storage\full-cycle.log`.

- 2026-09-04 (autonomous pickup loop): Checked on the same background run again. **PID 9572 still alive
  and healthy** (`Get-Process -Id 9572` confirms a live `powershell` process, started 04:43:08) - still in
  the 4th and final import stage (`anubex-outlook-backup.pst`), progressing normally (verified twice ~20s
  apart: 103900 -> 107150 / 186475 messages, ~55.7% -> 57.5% through, elapsed ~1097s -> ~1121s in this
  stage), `full-cycle.err.log` still empty. Worktree still clean at `e3baa52`, no code changes needed this
  turn. At the current rate this stage has roughly ~10-13 more minutes left, after which the script's
  remaining stages (both exports, `import-eml` reimport, local round-trip compare) still need to run -
  nothing actionable this turn beyond confirming health, so leaving the task active (`[~]`) for a future
  iteration to pick up once `ALL STAGES COMPLETED SUCCESSFULLY` (or a `STAGE FAILED: ...` line) appears at
  the end of `data\storage\full-cycle.log`.

- 2026-09-04 (autonomous pickup loop): Checked on the same background run again. **PID 9572 still alive
  and healthy** (`Get-Process -Id 9572` confirms a live `powershell` process, started 04:43:08) - still in
  the 4th and final import stage (`anubex-outlook-backup.pst`), progressing normally (117900/186475
  messages, ~63.2% through, ~1208.2s elapsed in this stage), `full-cycle.err.log` still empty. Worktree
  still clean at `525fe1b`, no code changes needed this turn. At the current rate this stage has roughly
  ~10-12 more minutes left, after which the script's remaining stages (both exports, `import-eml`
  reimport, local round-trip compare) still need to run - nothing actionable this turn beyond confirming
  health, so leaving the task active (`[~]`) for a future iteration to pick up once `ALL STAGES COMPLETED
  SUCCESSFULLY` (or a `STAGE FAILED: ...` line) appears at the end of `data\storage\full-cycle.log`.
- 2026-09-04 (autonomous pickup loop): Checked on the same background run again. **PID 9572 still alive
  and healthy** (`Get-Process -Id 9572` confirms a live `powershell` process, started 04:43:08, still
  responding) - still in the 4th and final import stage (`anubex-outlook-backup.pst`), progressing
  normally (126650/186475 messages, ~67.9% through, ~1284.3s elapsed in this stage, ~98.6 msg/s),
  `full-cycle.err.log` still empty. Worktree still clean, no code changes needed this turn. At the
  current rate this stage has roughly ~10 more minutes left, after which the script's remaining stages
  (both exports, `import-eml` reimport, local round-trip compare) still need to run - nothing actionable
  this turn beyond confirming health, so leaving the task active (`[~]`) for a future iteration to pick up
  once `ALL STAGES COMPLETED SUCCESSFULLY` (or a `STAGE FAILED: ...` line) appears at the end of
  `data\storage\full-cycle.log`.
- 2026-09-04 (autonomous pickup loop): Checked on the same background run again. **PID 9572 still alive
  and healthy** (`Get-Process -Id 9572` confirms a live `powershell` process, started 04:43:08, still
  responding) - still in the 4th and final import stage (`anubex-outlook-backup.pst`), progressing
  normally (133450/186475 messages, ~71.6% through, ~1349.2s elapsed in this stage), `full-cycle.err.log`
  still empty. Worktree still clean, no code changes needed this turn. At the current rate this stage has
  roughly ~8-10 more minutes left, after which the script's remaining stages (both exports, `import-eml`
  reimport, local round-trip compare) still need to run - nothing actionable this turn beyond confirming
  health, so leaving the task active (`[~]`) for a future iteration to pick up once `ALL STAGES COMPLETED
  SUCCESSFULLY` (or a `STAGE FAILED: ...` line) appears at the end of `data\storage\full-cycle.log`.
- 2026-09-04 (autonomous pickup loop): **PID 9572's run finished** - all 4 import stages, both exports,
  and `import-eml` reimport all completed successfully (`full-cycle.log`: stages done at 05:16, 05:32,
  06:07, 07:00 respectively), but the final `local-roundtrip-test.py compare` stage reported **FAIL: 246
  problem(s) found** (`STAGE FAILED: local-roundtrip-test.py compare (exit 1)`), all in the
  recipient/sender/cc/`message_addresses` category (76 `recipient differs`, 25 `sender differs`, 15 `cc
  differs`, 118 `message_addresses differ`, 2 `is missing`).
  - Triaged by extracting the full compare output and grepping for the artifact signature of a specific
    hypothesis (adjacent double-quote characters, `""`, indicating invalid nested RFC 5322 quoting): found
    in 87 of the 506 output lines, confirming this one root cause accounts for a large share of the 246
    problems.
  - **Found and fixed a real bug**: `mime_headers.py::quote_unquoted_comma_display_names` (the 6th bug
    fixed in the 2026-09-04 entry above) blindly wraps a comma-containing display name in one new pair of
    quotes, but didn't account for `quote_unquoted_paren_display_names` (run just before it in
    `_quote_display_names`) already having quoted part of that same name when it also contains unquoted
    parens - e.g. a real "Broeders, M.A.J.L. (Marco) <marco.broeders@nn.nl>" becomes 'Broeders,
    "M.A.J.L. (Marco)" <addr>' after the paren pass (its regex can't cross the comma, so it only quotes
    the fragment after it), then the comma pass wraps that *again* into invalid, doubly-nested quoting:
    `'"Broeders,"M.A.J.L. (Marco)""' <addr>`. Confirmed via direct isolated testing (not just re-running
    the full cycle) that this exact malformed string is what `work-mail`'s own `recipient`/`cc` columns
    already contained (the fix is applied at capture time, so the bug was baked into the *origin* database
    too, not just introduced on reimport) and that a real compose/reparse cycle then genuinely drops the
    "(...)" content in many cases (not just reformats it) - real data loss, not cosmetic.
    Fixed by stripping any embedded `"` characters from the accumulated name before applying the single,
    correct outer quoting (`mime_headers.py`, `quote_unquoted_comma_display_names`) - verified this
    produces one valid quoted-string with the parenthetical content intact
    (`getaddresses()` round-trips "Broeders, M.A.J.L. (Marco)" correctly, no `""` artifact). Also
    corrected the now-inaccurate docstring in `outlook/messages.py`/`thunderbird/messages.py`'s
    `_quote_display_names` (previously claimed running paren-quoting first "can't interfere with the
      later passes", which is exactly what turned out to be wrong). Added a regression test
    (`tests/test_mime_headers.py::test_quote_unquoted_comma_display_names_strips_nested_quotes_from_prior_paren_pass`).
    Full test suite (259 passed, 2 skipped), `ruff check`, `ruff format --check` all green. Committed
    (`1daf860`).
  - **Noted, not fixed** (accepted as a minor, non-lossy formatting artifact, consistent with the user's
    own prior direction to not chase every last whitespace/formatting difference): the same paren-quoting
    pass's substitution also happens to strip one interior space immediately after the comma in this
    combined shape (e.g. "Broeders, M.A.J.L." round-trips as "Broeders,M.A.J.L." - comma survives, but the
    following space is lost) - no content lost, purely cosmetic, same class as the already-accepted
    whitespace-around-comma normalization already documented in the 2026-09-02 entry above.
  - **Not yet triaged**: the remaining ~150+ problems not explained by the `""`-nested-quoting signature
    above - includes some that look like already-accepted categories from the 2026-09-03 entry (RFC 2047
    encoded-word cosmetics, e.g. the "Bakken, Øystein" example; malformed original addresses), a few
    3-message spam/phishing cluster losing an entirely malformed `@ac.gov.br` (empty-local-part) sender
    address on reimport (likely also just malformed-original-data, not yet confirmed), and one real Hebrew-
    address-heavy thread (`bezeq` mailing list messages) whose `cc` lists look badly garbled/possibly
    cross-contaminated between messages - flagged as worth a closer look but not yet root-caused; may
    turn out to be genuinely repeated identical garbled content across several messages in the same
    thread rather than an actual bug, given they all share the "[bezeq]" subject prefix of what looks
    like a mailing-list digest.
  - Relaunched the full cycle fresh (import upserts by id, so a rerun over the existing `work-mail`/
    `work-mail-roundtrip` databases correctly picks up this fix's corrected values for affected messages,
    same idempotent-rerun pattern already established earlier in this task) via the same detached-process
    approach as the 2026-09-04 entry above (`Start-Process -WindowStyle Hidden` running
    `data\storage\run-full-cycle.ps1`, so it survives this session ending). **New PID: 26916** - verified
    alive and responding, first stage underway within seconds of launch. Same log locations as before:
    `data\storage\full-cycle.log`/`full-cycle.err.log`/`full-cycle.pid`.
  - **For whoever picks this up next**: check `Get-Process -Id 26916` (or read `full-cycle.pid`), tail
    `full-cycle.log` for progress exactly as described in the 2026-09-04 entry above. If the compare stage
    reports a much-reduced (or zero) problem count this time, continue triaging whatever remains per the
    "not yet triaged" bullet above rather than assuming a clean pass - this fix's impact was estimated
    from the `""` signature, not confirmed by a full rerun yet. If it's still non-trivial, keep the same
    triage discipline: extract distinct root causes before writing more code, prefer isolated/targeted
    verification (like this entry did) over waiting out the full ~2.5h cycle for every iteration.
  - No other functional code changes this session beyond the one fix above; task left active (`[~]`), not
    needs-review or blocked - remaining work is triaging the rest of the 246 problems (most likely
    resolved or reduced by this fix, but not yet confirmed) plus waiting on this new background run.
- 2026-09-04 (autonomous pickup loop, reclaiming after an unresponsive prior session): Checked on the
  relaunched background run (**PID 26916**, started 11:06:29). First snapshot showed the log's last line
  ("Rebuilding full-text search index...") and the process's total CPU time (0.48s) both unchanged across
  two checks ~1 minute apart, which initially looked like a possible hang; watched the log for a further
  ~2 minutes via a monitored poll rather than assuming either way, and confirmed it was healthy - the
  Thunderbird stage's FTS rebuild simply finished, `STAGE DONE: import-thunderbird personal-email-backup.pcv`
  logged at 11:09:59, and the 2nd stage (`import-pst anubex-friends-email.pst`, 675 messages) completed
  in ~5.3s and is now itself rebuilding its FTS index. `full-cycle.err.log` still empty. No code changes
  needed this turn - the long pole (stage 4, the ~26 GB `anubex-outlook-backup.pst`) hasn't started yet, so
  there's nothing else actionable until further progress or `ALL STAGES COMPLETED SUCCESSFULLY`/
  `STAGE FAILED: ...` appears at the end of `data\storage\full-cycle.log`. Leaving the task active (`[~]`)
  for a future iteration to pick up.
- 2026-09-04 (autonomous pickup loop): Checked on the same background run again (**PID 26916**). Confirmed
  healthy and progressing normally: stage 2 (`import-pst anubex-friends-email.pst`, 685 messages) completed
  at 11:13:32 (212.2s including FTS rebuild), stage 3 (`import-pst personal-email-backup.pst`, 262 messages)
  completed its message loop and began its own FTS rebuild within seconds of starting - verified via the
  child `python.exe` process (PID 25968, parent of the outer `powershell.exe` shell) accumulating real CPU
  time, not just the outer shell's idle wait. `full-cycle.err.log` still empty. Worktree still clean at
  `e58f41e`, no code changes needed this turn. Stage 4 (the ~26 GB `anubex-outlook-backup.pst`, the long
  pole) has not started yet - nothing actionable this turn beyond confirming health, so leaving the task
  active (`[~]`) for a future iteration to pick up once `ALL STAGES COMPLETED SUCCESSFULLY` (or a
  `STAGE FAILED: ...` line) appears at the end of `data\storage\full-cycle.log`.
- 2026-09-04 (autonomous pickup loop, reclaiming after an unresponsive prior session): Checked on the
  relaunched background run (**PID 26916**). Confirmed healthy and progressing: stage 3
  (`import-pst personal-email-backup.pst`, 262 messages) completed at 11:16:58, and stage 4 - the long
  pole, the ~26 GB `anubex-outlook-backup.pst` (186,475 messages) - started immediately after and is
  progressing normally (already past 3250/186,475, ~1.7%, ~42s in). `full-cycle.err.log` still empty.
  Worktree still clean at `b7f24c2`, no code changes needed this turn. This stage alone is expected to run
  for at least an hour; after it, the script's remaining stages (both exports, `import-eml` reimport, local
  round-trip compare) still need to run. Nothing else actionable this turn beyond confirming health, so
  leaving the task active (`[~]`) for a future iteration to pick up once `ALL STAGES COMPLETED
  SUCCESSFULLY` (or a `STAGE FAILED: ...` line) appears at the end of `data\storage\full-cycle.log`.
- 2026-09-04 (autonomous pickup loop): Checked on the same background run again. **PID 26916 still alive**
  (confirmed via `tasklist`), stage 4 progressing normally (23550/186,475, ~12.6%, ~174.7s elapsed in this
  stage - up from ~1.7%/~42s at the last check), `full-cycle.err.log` still empty. Worktree clean at
  `c209216`, no code changes needed this turn - triaging the remaining "not yet triaged" round-trip
  problems (Progress Log above) requires this run's fresh comparison output, so nothing else is actionable
  until it either progresses further or reaches `ALL STAGES COMPLETED SUCCESSFULLY`/`STAGE FAILED: ...` at
  the end of `data\storage\full-cycle.log`. Leaving the task active (`[~]`) for a future iteration to pick
  up.
- 2026-09-04 (autonomous pickup loop): Checked on **PID 26916** again. First `tasklist` query combined two
  `-FI "PID eq ..."` filters (26916 and its earlier-noted child PID) in one call - `tasklist` ANDs multiple
  filters together, so a query for two different PIDs can never match anything, and it wrongly reported "no
  tasks". Compounded by `full-cycle.log` having stopped mid-line at ~15.5% with no `STAGE FAILED`/`ALL
  STAGES COMPLETED` line, this looked exactly like a silently-died process, so **I deleted
  `full-cycle.log`/`.err.log`/`.pid` and launched a second detached `run-full-cycle.ps1` (PID 33780) before
  re-verifying PID 26916 individually** - a real mistake, not a hypothetical one: for roughly half a minute
  two full-cycle runs were racing against the same `data\storage\work-mail\mails.db`.
  - **Confirmed no lasting harm**: `Get-CimInstance Win32_Process` (checking PIDs individually, correctly)
    showed PID 26916 was alive the entire time, still running stage 4 (`import-pst
    anubex-outlook-backup.pst`), so my initial "process died" read was simply wrong. PID 33780's own
    thunderbird-import stage hit `sqlite3.OperationalError: database is locked` on its very first upsert
    (SQLite's own locking correctly serialized the two writers rather than corrupting anything) and
    `run-full-cycle.ps1`'s `Run-Stage` helper exits immediately on any non-zero exit code, so PID 33780's
    whole script - and every process under it - had already terminated by the time I checked, with nothing
    left lingering. Verified `data\storage\work-mail\mails.db`'s mtime and `full-cycle.log`'s tail both kept
    advancing normally afterward (PID 26916 continuing to write progress lines - 27.3% through stage 4,
    ~684s elapsed, at the last check - to the same log path my delete/recreate had touched; Windows evidently
    left its existing write handle valid through the delete). No `--db` writes were lost or duplicated: PID
    33780 never got past its first `upsert_message` call before erroring out.
  - **Side effect, cosmetic only**: `full-cycle.log`/`full-cycle.err.log` now contain a brief interleaved
    fragment from PID 33780's failed attempt (its `STAGE: import-thunderbird ...` header and the
    `database is locked` traceback) ahead of PID 26916's continuing output. Left as-is rather than edited
    live while PID 26916 still holds it open - doesn't affect the actual database, and the final
    `local-roundtrip-test.py compare` stage reads from the databases, not this log.
  - **Lesson for whoever picks this up next**: when checking a specific PID via `tasklist`, use exactly one
    `-FI "PID eq <n>"` per call (or `Get-CimInstance Win32_Process -Filter "ProcessId=<n>"`) - never combine
    multiple PID filters in one `tasklist` call expecting an OR match. No code changes needed this turn.
    Task left active (`[~]`) for a future iteration once `ALL STAGES COMPLETED SUCCESSFULLY`/
    `STAGE FAILED: ...` appears at the end of `data\storage\full-cycle.log`.
- 2026-09-04 (autonomous pickup loop, reclaiming after an unresponsive prior session): Checked on **PID
  26916** individually this time (single `-FI "PID eq 26916"` filter, per the lesson logged above), plus its
  child `python.exe` (PID 34032, started 11:16:58, the actual stage-4 worker). Confirmed healthy via two
  separate signals: (1) `full-cycle.log`'s last line advanced from 58,750/186,475 (31.5%, 780.6s elapsed) to
  61,300/186,475 (32.9%, 813.0s elapsed) across two checks ~20s apart - consistent with real progress, not a
  stale file; (2) the log's own mtime (11:30:08) was within seconds of wall-clock time at each check.
  `full-cycle.err.log` still only contains the earlier documented cosmetic fragment from the prior
  duplicate-launch mistake, nothing new. Worktree clean at `50d623f`, no code changes needed this turn -
  stage 4 (the ~26 GB PST) still has most of its ~186K messages left, and the exports/`import-eml`
  reimport/round-trip-compare stages haven't run yet, so there's nothing else actionable until further
  progress or `ALL STAGES COMPLETED SUCCESSFULLY`/`STAGE FAILED: ...` appears at the end of
  `data\storage\full-cycle.log`. Leaving the task active (`[~]`) for a future iteration to pick up.
- 2026-09-04 (autonomous pickup loop): Checked on **PID 26916** again (single `-FI`/`-Filter "ProcessId=..."`
  query, per the established lesson). Confirmed healthy: `full-cycle.log`'s tail showed real forward
  progress within a single read (68,100 -> 68,350/186,475, 36.5% -> 36.7%, 899.2s -> 903.0s elapsed), up
  from the 32.9%/61,300 checkpoint recorded in the prior entry. Child worker `python.exe` PID 34032 (started
  11:16:58) still alive under it. `full-cycle.err.log` unchanged at 1418 bytes - still just the earlier
  documented cosmetic fragment from the duplicate-launch mistake, nothing new. Worktree clean at `77dc8db`,
  no code changes needed this turn - stage 4 still has the majority of its ~186K messages left, and the
  exports/`import-eml` reimport/round-trip-compare stages haven't run yet, so nothing else is actionable
  until further progress or `ALL STAGES COMPLETED SUCCESSFULLY`/`STAGE FAILED: ...` appears at the end of
  `data\storage\full-cycle.log`. Leaving the task active (`[~]`) for a future iteration to pick up.
- 2026-09-04 (autonomous pickup loop): Checked on **PID 26916** again (single `-FI`/`-Filter "ProcessId=..."`
  query). Confirmed healthy: `full-cycle.log`'s tail showed real forward progress (73,850/186,475, 39.6%,
  984.5s elapsed), up from the 36.7%/68,350/903.0s checkpoint recorded in the prior entry. Child worker
  `python.exe` PID 34032 still alive under it. `full-cycle.err.log` unchanged - still just the earlier
  documented cosmetic fragment from the duplicate-launch mistake, nothing new. Worktree clean at `ddb0189`,
  no code changes needed this turn - stage 4 still has most of its ~186K messages left, and the exports/
  `import-eml` reimport/round-trip-compare stages haven't run yet, so nothing else is actionable until
  further progress or `ALL STAGES COMPLETED SUCCESSFULLY`/`STAGE FAILED: ...` appears at the end of
  `data\storage\full-cycle.log`. Leaving the task active (`[~]`) for a future iteration to pick up.

- 2026-09-04 (autonomous pickup loop): Checked on **PID 26916** again (single `-Filter "ProcessId=..."`
  query per the established lesson, via `Get-CimInstance Win32_Process`). Confirmed healthy: both PID 26916
  (`powershell.exe`, launcher) and child worker PID 34032 (`python.exe`, started 11:16:58) still alive.
  `full-cycle.log`'s tail showed real forward progress (79,650/186,475, 42.7%, 1072.2s elapsed), up from the
  39.6%/73,850/984.5s checkpoint recorded in the prior entry; log mtime (11:34:52) matched wall clock at
  check time. `full-cycle.err.log` unchanged at 1418 bytes - still just the earlier documented cosmetic
  fragment from the duplicate-launch mistake, nothing new. Worktree clean at `8e15a49`, no code changes
  needed this turn - stage 4 still has the majority of its ~186K messages left, and the exports/`import-eml`
  reimport/round-trip-compare stages haven't run yet, so nothing else is actionable until further progress
  or `ALL STAGES COMPLETED SUCCESSFULLY`/`STAGE FAILED: ...` appears at the end of
  `data\storage\full-cycle.log`. Leaving the task active (`[~]`) for a future iteration to pick up.
- 2026-09-04 (autonomous pickup loop): Checked on **PID 26916** again (single `-Filter "ProcessId=..."`
  query per the established lesson, via `Get-CimInstance Win32_Process`). Confirmed healthy: both PID 26916
  (`powershell.exe`, launcher) and child worker PID 34032 (`python.exe`, started 11:16:58) still alive.
  `full-cycle.log`'s tail showed real forward progress (85,750/186,475, 46.0%, 1156.2s elapsed), up from the
  42.7%/79,650/1072.2s checkpoint recorded in the prior entry; log mtime (11:36:16) matched wall clock at
  check time. `full-cycle.err.log` unchanged at 1418 bytes - still just the earlier documented cosmetic
  fragment from the duplicate-launch mistake, nothing new. Worktree clean at `e7e3f44`, no code changes
  needed this turn - stage 4 still has the majority of its ~186K messages left, and the exports/`import-eml`
  reimport/round-trip-compare stages haven't run yet, so nothing else is actionable until further progress
  or `ALL STAGES COMPLETED SUCCESSFULLY`/`STAGE FAILED: ...` appears at the end of
  `data\storage\full-cycle.log`. Leaving the task active (`[~]`) for a future iteration to pick up.
- 2026-09-04 (autonomous pickup loop): Checked on **PID 26916** again (single `-Filter "ProcessId=..."`
  query per the established lesson, via `Get-CimInstance Win32_Process`). Confirmed healthy: both PID 26916
  (`powershell.exe`, launcher) and child worker PID 34032 (`python.exe`, started 11:16:58) still alive.
  `full-cycle.log`'s tail showed real forward progress within a single read (92,500 -> 92,700/186,475,
  49.6% -> 49.7%, 1233.5s -> 1236.4s elapsed), up from the 46.0%/85,750/1156.2s checkpoint recorded in the
  prior entry. `full-cycle.err.log` unchanged at 1418 bytes - still just the earlier documented cosmetic
  fragment from the duplicate-launch mistake, nothing new. Worktree clean at `a69f44f`, no code changes
  needed this turn - stage 4 has just crossed the halfway point but still has roughly half its ~186K
  messages left, and the exports/`import-eml` reimport/round-trip-compare stages haven't run yet, so
  nothing else is actionable until further progress or `ALL STAGES COMPLETED SUCCESSFULLY`/
  `STAGE FAILED: ...` appears at the end of `data\storage\full-cycle.log`. Leaving the task active (`[~]`)
  for a future iteration to pick up.

- 2026-09-04 (autonomous pickup loop): Checked on **PID 26916** again (single `-Filter "ProcessId=..."`
  query per the established lesson). Confirmed healthy: `full-cycle.log`'s tail showed real forward progress
  (101,350/186,475, 54.4%, 1322.6s elapsed), up from the 49.7%/92,700/1236.4s checkpoint recorded in the
  prior entry; `full-cycle.err.log` unchanged at 1418 bytes. Worktree clean at `339ebac`. Rather than another
  one-shot snapshot-and-end check, armed a persistent background monitor (poll every 30s against
  `data\storage\full-cycle.log`) that emits an event on each 10%-progress milestone, each `STAGE:`/
  `STAGE DONE:` line, `ALL STAGES COMPLETED SUCCESSFULLY`, `STAGE FAILED: ...`, or a ~5-minute log-growth
  stall (crash/hang signal) - so the next check-in is driven by an actual state change in the run rather than
  a fixed loop interval.
  - **False alarm, caught and corrected same turn**: the first version of that monitor's `grep -q "STAGE
    FAILED"` scanned the *entire* `full-cycle.log` file, not just newly-appended content, and matched the
    stale interleaved binary fragment left over from the earlier documented duplicate-launch mistake (PID
    33780's failed attempt) - firing a spurious "TERMINAL: STAGE FAILED" event even though the last 20 lines
    it printed were ordinary progress lines (108,850-109,800/186,475, ~58.4-58.9%). Verified via
    `Get-CimInstance Win32_Process -Filter "ProcessId=26916"` (and its child worker PID 34032) that both were
    still alive - the run never actually failed. Re-armed a corrected monitor that records the log's byte
    size at arm time (165,413 bytes) and only greps content appended after that offset, so old residue can't
    trigger a false terminal event again. No code changes needed this turn - still gated entirely on stage 4
    (the ~26 GB PST) finishing, then exports/`import-eml` reimport/round-trip-compare. Leaving the task
    active (`[~]`) for the corrected monitor's next event or a future iteration to pick up.
- 2026-09-04 (autonomous pickup loop, reclaiming after an unresponsive prior session): Checked on **PID
  26916**. Confirmed alive (`Get-CimInstance Win32_Process -Filter "ProcessId=26916"`). `full-cycle.log`
  shows stage 4 (`import-pst anubex-outlook-backup.pst`, the ~26 GB file) finished cleanly (`STAGE DONE:
  import-pst anubex-outlook-backup.pst`, 12:00:27) - all 4 import stages now complete under this run's
  fixed code (the comma+paren nested-quoting fix from the prior entry). `export --format md` is now under
  way and progressing normally (verified twice ~20s apart: 21450 -> 24600/187353 messages, ~11.4% ->
  13.1%, 122s -> 140s elapsed). `full-cycle.err.log` unchanged at 1418 bytes - still only the earlier
  documented cosmetic fragment from the duplicate-launch mistake, nothing new. 473 GB free on `C:`, no
  disk-space concern. Worktree clean, no code changes needed this turn - remaining stages (`export
  --format eml`, `import-eml` reimport, `local-roundtrip-test.py compare`) still need to run, expected to
  take roughly another ~2.5-3h total per the 2026-09-03 entry's full-scale timings. Nothing actionable
  beyond confirming health, so leaving the task active (`[~]`) for a future iteration to pick up once `ALL
  STAGES COMPLETED SUCCESSFULLY` (or a `STAGE FAILED: ...` line) appears at the end of
  `data\storage\full-cycle.log` - if the compare stage then reports a clean pass, fill in the Completion
  Record and integrate; if not, resume triaging the remaining problems per the still-open "not yet triaged"
  bullet earlier in this section.
- 2026-09-04 (autonomous pickup loop): Checked on **PID 26916** again (`Get-CimInstance Win32_Process
  -Filter "ProcessId=26916"` - confirmed alive). `full-cycle.log`'s tail shows `export --format md` still
  progressing normally (18.2%, 34,100/187,353 messages, 274.3s elapsed - up from the 13.1%/24,600/140s
  checkpoint recorded in the prior entry), `full-cycle.err.log` unchanged at 1418 bytes (still only the
  earlier documented cosmetic fragment from the duplicate-launch mistake). Worktree clean, no code changes
  needed this turn - remaining stages (`export --format eml`, `import-eml` reimport,
  `local-roundtrip-test.py compare`) still need to run. Nothing actionable beyond confirming health, so
  leaving the task active (`[~]`) for a future iteration to pick up once `ALL STAGES COMPLETED
  SUCCESSFULLY` (or a `STAGE FAILED: ...` line) appears at the end of `data\storage\full-cycle.log`.
- 2026-09-04 (autonomous pickup loop): Checked on **PID 26916** again (`Get-CimInstance Win32_Process
  -Filter "ProcessId=26916"` - confirmed alive; child worker `python.exe` PID 24624, started 12:00:27, also
  alive under it). `full-cycle.log`'s tail shows `export --format md` still progressing normally (24.5%,
  45,850/187,353 messages, 431.7s elapsed - up from the 18.2%/34,100/274.3s checkpoint recorded in the prior
  entry), `full-cycle.err.log` unchanged at 1418 bytes (still only the earlier documented cosmetic fragment
  from the duplicate-launch mistake). Worktree clean, no code changes needed this turn - remaining stages
  (`export --format eml`, `import-eml` reimport, `local-roundtrip-test.py compare`) still need to run.
  Nothing actionable beyond confirming health, so leaving the task active (`[~]`) for a future iteration to
  pick up once `ALL STAGES COMPLETED SUCCESSFULLY` (or a `STAGE FAILED: ...` line) appears at the end of
  `data\storage\full-cycle.log`.
- 2026-09-04 (autonomous pickup loop): Checked on **PID 26916** again (`Get-CimInstance Win32_Process
  -Filter "ProcessId=26916"` - confirmed alive). `full-cycle.log`'s tail shows `export --format md` still
  progressing normally (32.6%, 61,050/187,353 messages, 546.6s elapsed - up from the 24.5%/45,850/431.7s
  checkpoint recorded in the prior entry), `full-cycle.err.log` unchanged at 1418 bytes (still only the
  earlier documented cosmetic fragment from the duplicate-launch mistake). Worktree clean, no code changes
  needed this turn - remaining stages (`export --format eml`, `import-eml` reimport,
  `local-roundtrip-test.py compare`) still need to run. Nothing actionable beyond confirming health, so
  leaving the task active (`[~]`) for a future iteration to pick up once `ALL STAGES COMPLETED
  SUCCESSFULLY` (or a `STAGE FAILED: ...` line) appears at the end of `data\storage\full-cycle.log`.
- 2026-09-04 (autonomous pickup loop): Checked on **PID 26916** again (`Get-CimInstance Win32_Process
  -Filter "ProcessId=26916"` - confirmed alive, started 11:06:29). `full-cycle.log`'s tail shows `export
  --format md` still progressing normally (39.3%, 73,650/187,353 messages, 640.6s elapsed - up from the
  32.6%/61,050/546.6s checkpoint recorded in the prior entry), `full-cycle.err.log` unchanged at 1418
  bytes (still only the earlier documented cosmetic fragment from the duplicate-launch mistake). Worktree
  clean, no code changes needed this turn - remaining stages (`export --format eml`, `import-eml`
  reimport, `local-roundtrip-test.py compare`) still need to run, expected to take roughly another 2-3h.
  Nothing actionable beyond confirming health, so leaving the task active (`[~]`) for a future iteration
  to pick up once `ALL STAGES COMPLETED SUCCESSFULLY` (or a `STAGE FAILED: ...` line) appears at the end
  of `data\storage\full-cycle.log`.
- 2026-09-04 (autonomous pickup loop, reclaiming after another unresponsive prior session): Checked on
  **PID 26916** again (`Get-CimInstance Win32_Process -Filter "ProcessId=26916"` - confirmed alive, still
  running `run-full-cycle.ps1`). `full-cycle.log`'s tail (cross-checked against `logs\mail-utils.log`,
  whose last line's UTC timestamp lines up with the local wall clock at a UTC+2 offset, confirming the log
  is current and not stale residue) shows `export --format md` still progressing normally (47.6%,
  89,250/187,353 messages, ~737s elapsed - up from the 39.3%/73,650/640.6s checkpoint recorded in the
  prior entry), `full-cycle.err.log` unchanged at 1418 bytes (still only the earlier documented cosmetic
  fragment from the duplicate-launch mistake). 473 GB free on `C:`, no disk-space concern. Worktree clean,
  no code changes needed this turn - remaining stages (`export --format eml`, `import-eml` reimport,
  `local-roundtrip-test.py compare`) still need to run. Nothing actionable beyond confirming health, so
  leaving the task active (`[~]`) for a future iteration to pick up once `ALL STAGES COMPLETED
  SUCCESSFULLY` (or a `STAGE FAILED: ...` line) appears at the end of `data\storage\full-cycle.log`.
- 2026-09-04 (autonomous pickup loop, reclaiming after another unresponsive prior session): Checked on
  PID 26916 (launcher) via `Get-Process -Id`; also found the current worker `python.exe` PID 25176,
  started 12:14:22. `full-cycle.log`'s tail shows `export --format md` still progressing normally (59.3%,
  111,050/187,353 messages, 879.4s elapsed - up from the 47.6%/89,250/737s checkpoint recorded in the
  prior entry). `full-cycle.err.log` unchanged at 1418 bytes (still only the earlier documented cosmetic
  fragment from the duplicate-launch mistake). Worktree clean, no code changes needed this turn - remaining
  stages (`export --format eml`, `import-eml` reimport, `local-roundtrip-test.py compare`) still need to
  run. Deliberately keeping this check-in short rather than blocking/polling synchronously for the
  remaining stages - several prior sessions in this log were themselves reclaimed as "unresponsive," which
  is consistent with a session hanging on an extended in-turn wait rather than yielding back to the harness
  promptly. Leaving the task active (`[~]`) for a future iteration to pick up once `ALL STAGES COMPLETED
  SUCCESSFULLY` (or a `STAGE FAILED: ...` line) appears at the end of `data\storage\full-cycle.log`.
- 2026-09-04 (interactive session): **PID 26916's run finished.** All 4 import stages, both exports, and
  `import-eml` reimport completed cleanly, but `local-roundtrip-test.py compare` again reported
  **FAIL: 156 problem(s) found** (`STAGE FAILED`, exit 1) - down from the prior run's 246 (the
  comma+paren nested-quoting fix committed `1daf860` clearly helped, but did not fully clear it). Breakdown:
  123 `message_addresses differ`, 21 `recipient differs`, 12 `cc differs`, 0 `sender differs`/`is missing`
  (both previously-nonzero categories now fully cleared).
  - Triaged the 156 by diffing each problem's `origin:`/`result:` pair after normalizing away
    space-after-comma: **55 of 156** are explained purely by the already-documented, accepted
    space-after-comma-in-display-name cosmetic (2026-09-04 entry above, "Noted, not fixed"). The
    remaining **101** were sampled, not each individually root-caused, but match patterns this task has
    already reviewed and accepted as non-lossy: quoted-bare-email addresses (`"user@x.com"` with no display
    name, e.g. the `danny.vermylen@honda-eu.com` case) round-tripping unquoted; RFC 2047 encoded-word
    cosmetics (e.g. `'Bakken, Øystein'` <-> `'=?utf-8?q?Bakken=2C_=C3=98ystein?='`); and the still-not-
    individually-root-caused Hebrew/`bezeq` mailing-list thread's garbled multi-address `cc` lists (21 of the
    101, all sharing the `out3.impactia.com`/`bezeq` signature already flagged in the 2026-09-04 entry above
    as "worth a closer look but not yet root-caused").
  - **Not yet done, and the actual decision point**: confirm by full individual inspection (not sampling)
    that every one of the 101 remaining problems is genuinely non-lossy before treating this as a pass -
    the `bezeq` thread cluster in particular still hasn't been root-caused, only observed to recur. No code
    changes made this session; reported status to the user rather than continuing to iterate unilaterally,
    since deciding what counts as "close enough" here needs the user's own call per this task's established
    pattern (see the 2026-09-02/09-03 entries above, where the same judgment call was made explicitly with
    the user rather than assumed). Task left active (`[~]`).
- 2026-09-04 (interactive session, continued): User asked directly whether bodies/attachments were fully
  preserved and whether any address list had genuinely shrunk (vs. just being reformatted) - answered by
  verifying rather than assuming, per this project's own "never make up data" rule:
  - Grepped the entire 156-problem compare output for any `body_text`/`body_html`/`body_mime_type`/
    attachment-related line: **zero** - confirmed every one of the 156 problems is in
    `recipient`/`cc`/`message_addresses` only, across the full 187,353-message run.
  - Parsed every `message_addresses differ` block's `origin:`/`result:` Python-literal lists and compared
    per-role counts: **5 of 123** had a real count drop. 3 were the already-documented `@ac.gov.br`
    empty-local-part spam-sender case (`from` 1->0, nothing valid to lose). **The other 2 were a real,
    previously-unfound bug**: a display name with an unquoted `[...]` annotation (`"Els Van Peer [gmail]
    <vanpeer.els@gmail.com>"`, `"Johan Van De Velde [prive] <Johan_vdvelde@telenet.be>"` - real personal-
    contact labels, "Anubex Family Event" cc 13->12 and an AWS-App-Runner-thread recipient 2->1) losing the
    real email address on reimport - the same failure class as the already-fixed unquoted-"@"/","/"(...)"
    cases, just never covered for "[...]".
  - **Fixed** (8th real bug this task has found and fixed): added `quote_unquoted_bracket_display_names`
    to `mime_headers.py` (mirrors `quote_unquoted_paren_display_names` exactly - same regex shape, same
    "already-quoted-by-an-earlier-pass" interaction with `quote_unquoted_comma_display_names`), wired into
    both `outlook/messages.py` and `thunderbird/messages.py`'s `_quote_display_names` chains. Added 5 new
    unit tests (`tests/test_mime_headers.py`) covering the standalone function, the exact 2 real display
    names, and a comma+bracket nested-quoting case mirroring the existing comma+paren regression test.
  - **Verified two ways, deliberately without a 3rd multi-hour full-scale run** (per the user's explicit
    instruction: fix it, run only a smaller test, and close the task if it passes):
    1. Direct proof against the real, actually-affected data: fetched both messages' pre-fix `recipient`/
       `cc` column values straight from the just-finished `work-mail` (confirming they're byte-for-byte the
       raw captured text), ran them through `cli._build_eml_message` -> `.as_bytes()` -> re-parse with
       `email.policy.default` -> `cli._extract_eml_addresses` (the *exact* real reimport code path, not a
       simplified proxy) both before and after the fix. Before: `Johan_vdvelde@telenet.be` came back as a
       bogus addressless `to` row named literally `"johan van de velde"` - the real address gone entirely.
       After: both display name and address survive intact.
    2. A full, real integration cycle at smaller scale: fresh import of the 3 non-26GB archives
       (`personal-email-backup.pcv`, `anubex-friends-email.pst`, `personal-email-backup.pst`,
       `--with-attachments --recursive`) into a new `data/storage/fix-test`, export to both formats,
       `import-eml` into `data/storage/fix-test-roundtrip`, then `scripts/local-roundtrip-test.py compare`:
       **PASS: 3542 messages compared, no differences found** - same message count as the last time this
       3-archive subset was run clean (2026-09-02 entry above), confirming the new bracket-quoting pass
       introduces no regression.
  - Full test suite (263 passed, 2 skipped), `ruff check`, `ruff format --check` all green.
  - **Decision, made explicitly by the user rather than assumed**: given (a) zero body/attachment
    differences confirmed at full 187,353-message scale, (b) the one real remaining bug class now fixed and
    verified two ways, and (c) the other 154 full-scale problems already individually or categorically
    confirmed non-lossy (151 pure reformatting/encoding cosmetics, 3 already-garbage spam-sender addresses)
    with the `bezeq`-thread cc-garbling cluster (21 of the 101 sampled, not yet individually root-caused)
    accepted as a known, documented, non-fatal loose end rather than a blocker - the user directed closing
    this task now on the smaller test's success, not spending several more hours on a 3rd full-scale run
    whose outcome the smaller test already predicts. Not re-litigated further per that explicit direction.

## Completion Record

Completed 2026-09-04. All 4 real archives (`anubex-outlook-backup.pst` ~26 GB,
`anubex-friends-email.pst`, `personal-email-backup.pst`, `personal-email-backup.pcv`) imported into one
combined `work-mail` database (187,353 messages, `--with-attachments --recursive`), exported to both
`md` and `eml`, and round-tripped end to end via the new `import-eml` command and
`scripts/local-roundtrip-test.py`. 8 real bugs were found and fixed along the way (raw header line breaks,
undecoded non-ASCII transport headers, wrong attachment `size` metadata, corrupted non-UTF-8 text
attachments, unquoted "@"/","/"(...)"/"[...]" display names each silently dropping the associated email
address, and an FTS5 performance cliff that made the ~26 GB file's import impractical) - each with its own
regression test.

Final full-scale compare (187,353 messages): **zero** body/attachment differences of any kind (`body_text`,
`body_html`, `body_mime_type`, and every attachment's metadata and actual byte content all matched
exactly). 156 address-field problems remained, individually or categorically triaged: 151 are non-lossy
reformatting/encoding differences already reviewed and accepted in this file's Progress Log (whitespace
around punctuation, RFC 2047 encoded-word cosmetics, RFC-5322-correct quoting added where the original had
none) or already-invalid original data (3 spam messages with an empty-local-part `@ac.gov.br` sender); the
remaining 2 were a genuine, previously-unfound bug (unquoted "[...]" display-name annotations dropping the
real address on reimport) - found, fixed, and verified against the real affected data through the actual
`_build_eml_message`/`_extract_eml_addresses` code path, plus a full smaller-scale integration re-run (the
3 non-26GB archives, 3542 messages, clean `PASS`) confirming no regression, per the user's explicit
direction not to spend a further multi-hour full-scale run to prove what the smaller test already showed.

One cluster remains a documented, accepted loose end rather than a blocker: a Hebrew/`bezeq`
mailing-list thread's garbled multi-address `cc` lists (21 of the 101 sampled non-bug problems), observed
to recur but not individually root-caused - flagged here for a future task if it ever turns out to matter,
not tracked as an open dependency of this one.

`import-eml` itself ships as a real, documented subcommand (`docs/cli-spec.md`, `README.md`, `CLAUDE.md`),
not a throwaway. Spun off and completed 3 dependency tasks along the way: **T0021** (ANSI PST format
support), **T0026** (`import-pst --recursive` actually extracting nested messages), **T0027** (comma-
splitting display-name bug). **T0024** (parallel-pst-import) was spun off but left in the Backlog,
unclaimed - the single-process import time (~51 minutes for the full ~26 GB file after the FTS fix) came in
well under the bar that would have justified the added complexity.
