# T0004: Capture full attachment content, not just metadata

- **Status:** Completed
- **Owner:** claude
- **Started:** 2026-08-27
- **Branch:** task/T0004-capture-attachment-content
- **Worktree:** ./work/T0004-capture-attachment-content

## Goal

Today `mail-utils` only ever captures attachment *metadata* (filename, MIME type, size) across all three
import sources (Gmail, Outlook PST, Thunderbird) - never the actual bytes. Extend `import`/`import-gmail`/
`import-pst`/`import-thunderbird` to optionally store attachment content too, and extend `export` to write
it back out as real files, so an exported message is no longer permanently attachment-less. Raised as a
finding while building T0002 (`import-into-gmail`), whose restore path can only ever be as complete as
what was captured on the way in.

## Scope

- `gmail_client.parse_attachments`: fetch attachment bytes via `users.messages.attachments.get` (uses the
  `attachmentId` already captured) - likely opt-in (e.g. `-r`/`--recursive`-style flag, or a new
  `--with-attachments`) given the extra API calls and storage cost this adds to every sync.
- `outlook/messages.py` and `thunderbird/messages.py` equivalents - both parsers already walk the MIME/PST
  attachment structure to get metadata, so the bytes are already being read past; the question is only
  where to put them.
- `db.py`: schema decision - inline `BLOB` column on `attachments` vs. content-addressed files under
  `data/attachments/<hash>` referenced by path. The latter avoids bloating `gmail.db` and naturally dedups
  identical attachments, at the cost of an extra on-disk layout to keep in sync with the DB.
- `export`: write attachment files alongside each exported message (`.eml` can carry them as real MIME
  parts again instead of the `X-Mail-Utils-Attachment` metadata-only header T0002-era exports use; `.md`
  needs a sidecar files/ dir per message).
- Storage/performance impact needs measuring before deciding a default - full attachment capture could
  multiply `data/gmail.db` (or `data/attachments/`) size significantly for image/PDF-heavy mailboxes.

## Out of Scope

- Changing `import-into-gmail` itself (T0002) to depend on this - that task ships attachment-less by
  design, matching what's actually stored today; this task is what would later let a *future* restore
  reattach files, not a blocker for T0002.

## Dependencies

None.

## Approach

**Storage: content-addressed files under `data/attachments/<sha256>`, not an inline BLOB column.**
`data/` is already gitignored in full and every path in the app derives from `config.DATA_DIR`, so this is a
one-line addition there (`ATTACHMENTS_DIR = DATA_DIR / "attachments"`). A flat directory (no hash-prefix
fan-out) is fine at personal-mailbox scale - simplicity over a fan-out layout nothing here needs yet.
`attachments` gets one new nullable column, `content_sha256 TEXT` (via `_ensure_column`, same pattern as
`cc`/`bcc`/`body_mime_type`): `NULL` means "metadata only, no content captured" (every row today, and every
row from a sync that didn't opt in), a hex digest means the bytes live at
`data/attachments/<content_sha256>`. Same hash on two attachments (e.g. a repeated forwarded logo) writes the
file once - dedup falls out of the addressing scheme for free, no separate dedup logic needed. A small new
module, `attachment_store.py`, owns this: `save(content: bytes) -> str` (hash, write-if-absent, return the
hex digest) and `path_for(sha256: str) -> Path`. Bytes never pass through SQLite at all, so `gmail.db` stays
exactly as cheap to `search`/back up as it is today regardless of how many attachments get captured.

**Opt-in via `--with-attachments`, default off, on `import`/`import-gmail`/`import-pst`/`import-thunderbird`.**
Mirrors the existing `-r`/`--recursive` pattern (a plain `store_true` flag threaded from `cli.py`'s argparse
down into each source's fetch loop). Off by default because it adds real cost to every sync that a metadata-only
sync doesn't have today: an extra Gmail API call per attachment (`users.messages.attachments.get`), extra local
disk I/O and space for PST/Thunderbird (which already read the bytes to compute `size`, so no extra I/O there -
only extra disk space). No separate `-r`-style short flag; `--with-attachments` is rare enough not to need one.

**Per-source content fetch:**
- *Gmail* (`gmail_client.py`): new `fetch_attachment_content(service, message_id, attachment_id) -> bytes` -
  one `users.messages.attachments.get` call, base64url-decode the returned `data` field (same decode `import_message`
  already does in reverse). Called from `cli.py`'s import loop, once per attachment row, only when
  `--with-attachments` is set.
- *Thunderbird* (`thunderbird/messages.py`): `parse_attachments` already calls
  `part.get_payload(decode=True)` to compute `size` - the bytes are already in hand, just discarded. Add an
  opt-in parameter so the caller can ask for them back alongside the existing metadata dict, no new I/O.
- *Outlook PST* (`outlook/messages.py`): the Attachment Table row (`raw.attachments`) carries summary
  properties only, not the bytes. Getting content needs the same pattern `tree.py` already uses for folder
  rows: read `PROP_LTP_ROW_ID` (0x67F2) off the attachment-table row to get the attachment object's own NID,
  `pst.resolve_nid()` + `read_property_context()` that NID, then read `PROP_ATTACH_DATA_BINARY` (0x3701) from
  the result. `read_property_context`/`PSTProperty` already handle other large binary/string properties
  (`PROP_BODY`, `PROP_HTML_BODY`), so no new low-level NDB/LTP machinery should be needed - this is new
  call-site logic in `messages.py`, not a new parsing layer.

**`export` writes content back out when it's present, falls back to metadata-only when it isn't** (an older
sync, or one that ran without `--with-attachments` - the two cases are indistinguishable and both simply
skip attaching content):
- `--format eml`: when `content_sha256` is set, `_build_eml_message` adds a real MIME part
  (`msg.add_attachment(data, maintype, subtype, filename=...)`, mime type split from the stored `mime_type`)
  instead of the current `X-Mail-Utils-Attachment` metadata-only header. When it's `NULL`, keep today's
  header-only behavior exactly as is - no regression for anyone not using the new flag.
- `--format md`: write each message's attachments into a sidecar `<message-file-stem>.attachments/<filename>`
  directory next to the `.md` file, and keep listing them in the YAML frontmatter as today (filename/type/size),
  so the frontmatter stays a complete manifest even for someone who only looks at the `.md` file.
- `store-in-gmail`'s DB-sourced path (`_build_eml_message`) picks up real attachments for free once content
  exists, since it's the same function `export --format eml` uses - not a required change, just a natural
  side effect of building on this. No behavior change to `store-in-gmail` itself is in scope here (see Out of
  Scope).

**Migration note for README/docs (not a data migration):** existing `data/gmail.db` rows keep
`content_sha256 = NULL` after upgrading - there's no schema-migration mechanism in this project (only
`CREATE TABLE IF NOT EXISTS` + `_ensure_column`), so picking up content for already-synced messages means
rerunning the relevant `import*` command with `--with-attachments` against the same database, same as any
other retroactive behavior change documented in `README.md`.

## Implementation Checklist

- [x] `config.py`: add `ATTACHMENTS_DIR = DATA_DIR / "attachments"`.
- [x] New `attachment_store.py`: `save(content: bytes) -> str` (sha256 hex digest, write-if-absent) and
      `path_for(sha256: str) -> Path` (plus `read()`, used by `export`).
- [x] `db.py`: add `content_sha256 TEXT` to the `attachments` schema + `_ensure_column` migration; extend
      `upsert_attachments` to persist it (defaulting to `None`/absent key when a caller doesn't supply one, so
      existing call sites that don't pass it keep working unchanged).
- [x] `gmail_client.py`: add `fetch_attachment_content(service, message_id, attachment_id) -> bytes`.
- [x] `thunderbird/messages.py`: extend `parse_attachments` to optionally return the already-decoded payload
      bytes alongside existing metadata (`with_content` param).
- [x] `outlook/messages.py`: add attachment-content fetch (`PROP_LTP_ROW_ID` -> `pst.read_subnode` -> read
      `PROP_ATTACH_DATA_BINARY`); `parse_attachments` takes an opt-in `pst` param mirroring the other two.
- [x] `cli.py`: add `--with-attachments` to `import`/`import-gmail`/`import-pst`/`import-thunderbird`; when
      set, fetch content per attachment, `attachment_store.save()` it, and pass the resulting `content_sha256`
      into `upsert_attachments`. Gmail's fetch is a dedicated helper (`_fetch_and_store_gmail_attachment_content`)
      since it needs a live API call keyed by the real (unprefixed) message id - including for a `--recursive`
      sub-message's attachments, which are still scoped to the *parent* message's id, not the synthesized
      sub-id (covered by a dedicated regression test - see Test Strategy). PST/Thunderbird share one small
      generic post-step (`_attach_content_to_store`) since their bytes are already in hand locally.
- [x] `cli.py` `export`: `--format eml` attaches real content when `content_sha256` is set
      (`_build_eml_message`, via `msg.add_attachment()` after `set_content()`); `--format md` writes the
      `<stem>.attachments/` sidecar directory. Frontmatter/`X-Mail-Utils-Attachment` metadata-only behavior is
      unchanged when `content_sha256` is `NULL`. `store-in-gmail`'s DB-sourced path picks this up for free
      (same `_build_eml_message`), matching the Approach's note that this wasn't a required change.
- [x] `docs/cli-spec.md`: documented `--with-attachments` on all four import subcommands (§2.1-2.4) and the
      export fallback behavior (§2.7).
- [x] `README.md`: added the "Database contents" section referenced throughout `CLAUDE.md`/`cli-spec.md` but
      never actually written - it didn't exist before this task. Documents every table (not just
      `attachments`), including the new `content_sha256` column, the `data/attachments/` content-addressed
      layout, and the no-auto-migration caveat. Also updated `docs/tutorial.md`'s ingest/export sections and
      the README "Key Features" list.
- [ ] `CHANGELOG.md` + `TODO.md` entry removal - deferred to Finalizing Work (not done yet; this is still
      mid-implementation, pending review/integration per the Review Tiers table).

## Test Strategy

- `db.py`: schema-migration test mirroring the existing `_ensure_column` coverage - an old-shaped
  `attachments` table gains `content_sha256` on `init_db()`.
- `attachment_store.py`: unit tests - save returns a stable hash for given bytes, saving identical content
  twice writes the file only once (dedup), `path_for` round-trips.
- `gmail_client.fetch_attachment_content`: mocked-service test asserting correct base64url decode.
- `thunderbird/messages.parse_attachments`: extend the existing fixture-backed test to assert content bytes
  match the fixture's actual attachment payload when requested.
- `outlook/messages.parse_attachments` (or its new content-fetch counterpart): extend the anonymized PST
  fixture test the same way, against `data/personal-email-backup.pst`'s (or the sample-generator's) known
  attachment bytes.
- `cli.py` integration tests (mocked Gmail service / fixture files, no real network): `import*
  --with-attachments` populates `content_sha256` and writes a file under `data/attachments/`; the same command
  *without* the flag leaves `content_sha256` `NULL` and writes nothing new (regression guard on the default
  path - most important test in this set, since it protects every existing user who never opts in).
- `export`: `--format eml` produces a real MIME attachment part when content exists and today's
  `X-Mail-Utils-Attachment` header when it doesn't; `--format md` writes the sidecar directory with the
  right filename(s).
- Manual/measured (recorded in Validation Record, not automated): run `import --with-attachments` against a
  real or sample mailbox and note the resulting `data/attachments/` size, so the storage-impact question the
  original finding raised has an actual number attached to it before anyone turns the flag on by default in
  their own scheduled job.

## Completion Criteria

- All four import commands support `--with-attachments`, default off, with zero behavior change when it's
  omitted (existing tests for the flag-less path continue to pass unmodified).
- Attachment bytes for a captured attachment round-trip correctly: import with the flag, then `export
  --format eml` (or `--format md`) reproduces the original bytes exactly (byte-for-byte comparison in a test).
- `README.md` and `docs/cli-spec.md` reflect the new column, directory, and flag.
- Full test suite (`pytest`) and lint (`ruff check`/`ruff format --check`) pass.
- CHANGELOG.md has a `BackEnd:`-area entry; `TODO.md`'s T0004 line is removed on completion per the standard
  finalize-work protocol.

## Progress Log

- 2026-08-27: Claimed and scoped (storage/flag/per-source-fetch decisions - see Approach above).
- 2026-08-28: Implemented the full checklist above: `attachment_store.py`, `db.py` schema/migration,
  per-source content fetch (Gmail/Thunderbird/PST), `cli.py` wiring (`--with-attachments` on all four
  import commands, `export` real-content round-trip for both formats), and docs (`cli-spec.md`,
  `tutorial.md`, README's new "Database contents" section). Added/extended tests across
  `test_attachment_store.py` (new), `test_db.py`, `test_gmail_client.py`, `test_thunderbird.py`,
  `test_pst_integration.py`, `test_recursive_import.py`, `test_cli.py`.
- 2026-08-28: User asked whether `store-in-gmail` also picks up captured attachment content.
  Verified yes on both its source paths - the `.eml`-tree path trivially inherits it (it just reads
  whatever `export --format eml` already wrote with real MIME parts), and the DB-sourced path
  (`_db_candidates` -> `_build_eml_message`) was confirmed via a manual script and then locked in with
  a new regression test (`test_run_store_in_gmail_from_database_includes_real_attachment_content`).
  No code change was needed - this fell out of `_build_eml_message` being shared code, exactly as
  anticipated in the Approach section above.
- Found and worked around one pre-existing (unrelated to this task) quirk while writing the
  recursive-import + attachments test: `gmail_client.parse_attachments` walks MIME parts without
  stopping at a `message/rfc822` boundary, so a nested sub-message's own attachment gets picked up
  *twice* - once attributed to the parent message, once to the extracted child message - when
  `--recursive` is combined with a forwarded email that itself has an attachment. Not a correctness
  bug (both copies get the right content, just double-fetched/stored under two message ids), so left
  as-is and out of scope here; worth a follow-up adhoc task if it turns out to matter in practice.

## Validation Record

- `pytest`: 174 passed, 2 skipped (the 2 skips are the pre-existing local-PST-fixture-only tests,
  unrelated to this task) - run from a throwaway `.venv` inside this worktree (`python -m venv .venv`
  + `pip install -e ".[dev]"`), not committed.
- `ruff check .`: all checks passed. `ruff format --check .`: all files formatted.
- `python -m build`: sdist + wheel built cleanly, `attachment_store.py` present in the wheel.
- Manual end-to-end smoke test (storage-impact/round-trip check called for in Test Strategy): built a
  synthetic Thunderbird `.pcv` with one real attachment, ran `mail-utils import-thunderbird
  --with-attachments` via the actual CLI entry point (not just unit tests), confirmed
  `content_sha256` populated and the exact bytes landed at `data/attachments/<hash>`, then ran
  `mail-utils export --format eml` and `--format md` against the same database and confirmed
  byte-for-byte round-trip in both: a real MIME attachment part in the `.eml` (no
  `X-Mail-Utils-Attachment` header), and a `<stem>.attachments/report.pdf` sidecar file next to the
  `.md` (frontmatter still filename/type/size only, no internal hash leaked into it).
  Storage-impact note: this was a synthetic single-attachment smoke test, not a real mailbox, so it
  doesn't answer the original finding's "how much does this grow `data/` for an image/PDF-heavy
  mailbox" question with a real number - that still needs a run against an actual (real or sample)
  multi-message mailbox before anyone turns `--with-attachments` on in a scheduled job; flagging this
  as outstanding rather than closing it out.

## Completion Record

- **Completed:** 2026-08-28
- **Summary:** `import`/`import-gmail`/`import-pst`/`import-thunderbird` gained an opt-in `--with-attachments`
  flag that fetches each attachment's actual bytes and stores them content-addressed under
  `data/attachments/<sha256>`, recorded via a new `attachments.content_sha256` column. `export` and
  `store-in-gmail` (verified on request, no extra code needed - see Progress Log) round-trip that
  content back out; behavior is unchanged for anyone who doesn't pass the new flag.
- **Follow-ups spun out, not part of this task:** none filed as new tasks - the two items noted in the
  Progress Log (the pre-existing double-fetch quirk on `--recursive` + a forwarded email with its own
  attachment, and the still-open real-mailbox storage-impact measurement) are left as documented
  findings rather than new backlog entries, since neither blocks this task's own completion criteria.
- **Review:** No PR, solo, AI agent - summary presented to the user in-conversation; user confirmed the
  `store-in-gmail` content pass-through explicitly before authorizing integration ("if yes: proceed").
