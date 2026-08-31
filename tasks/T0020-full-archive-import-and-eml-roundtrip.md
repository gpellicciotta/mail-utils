# T0020: Import all real archives into "work-mail" and prove a full EML round trip

- **Status:** available
- **Owner:** none
- **Started:** —
- **Branch:** —
- **Worktree:** —

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

- [ ] `import-eml` design confirmed with the user (Approach step 1)
- [ ] All 4 archives imported into `--db data/storage/work-mail` (`--with-attachments --recursive`)
- [ ] `work-mail` exported to `data/exports/work-mail-md/` and `data/exports/work-mail-eml/`
- [ ] `import-eml` implemented and unit-tested
- [ ] Local round-trip comparison tool built
- [ ] Round trip run against the real re-imported data; every difference triaged and resolved (fixed here,
      fixed via a linked child `Tnnnn`, or recorded as an accepted, documented limitation)
- [ ] Final clean round-trip run recorded in the Validation Record

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

## Validation Record

## Completion Record
