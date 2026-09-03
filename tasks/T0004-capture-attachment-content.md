---
id: T0004
title: "Capture full attachment content, not just metadata"
owner: claude
needs: []
branch: task/T0004-capture-attachment-content
worktree: ./work/T0004-capture-attachment-content
status: completed
started: 2026-08-27
ended: 2026-08-28
---

# T0004: Capture full attachment content, not just metadata

## Objectives & Scope

### Goal

Today `mail-utils` only ever captures attachment *metadata* (filename, MIME type, size) across all three
import sources (Gmail, Outlook PST, Thunderbird) - never the actual bytes. Extend `import`/`import-gmail`/
`import-pst`/`import-thunderbird` to optionally store attachment content too, and extend `export` to write
it back out as real files, so an exported message is no longer permanently attachment-less. Raised as a
finding while building T0002 (`import-into-gmail`), whose restore path can only ever be as complete as
what was captured on the way in.

### Scope

- `gmail_client.parse_attachments`: fetch attachment bytes via `users.messages.attachments.get` (uses the
  `attachmentId` already captured) - likely opt-in given the extra API calls and storage cost this adds to
  every sync.
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

### Out of Scope

- Changing `import-into-gmail` itself (T0002) to depend on this - that task ships attachment-less by
  design, matching what's actually stored today; this task is what would later let a *future* restore
  reattach files, not a blocker for T0002.

### Dependencies

None.

### Completion Criteria

- All four import commands support `--with-attachments`, default off, with zero behavior change when it's
  omitted (existing tests for the flag-less path continue to pass unmodified).
- Attachment bytes for a captured attachment round-trip correctly: import with the flag, then `export
  --format eml` (or `--format md`) reproduces the original bytes exactly (byte-for-byte comparison in a test).
- `README.md` and `docs/cli-spec.md` reflect the new column, directory, and flag.
- Full test suite (`pytest`) and lint (`ruff check`/`ruff format --check`) pass.
- `CHANGELOG.md` has a `BackEnd:`-area entry; `TODO.md`'s T0004 line is removed on completion per the
  standard finalize-work protocol.

## Task Implementation and Verification Steps

- [x] [Decide] **Storage: content-addressed files under `data/attachments/<sha256>`, not an inline BLOB
  column.** `data/` is already gitignored in full and every path in the app derives from `config.DATA_DIR`,
  so this is a one-line addition there. A flat directory (no hash-prefix fan-out) is fine at
  personal-mailbox scale. `attachments` gets one new nullable column, `content_sha256 TEXT` (via
  `_ensure_column`): `NULL` means "metadata only, no content captured", a hex digest means the bytes live
  at `data/attachments/<content_sha256>`. Dedup falls out of the addressing scheme for free.
- [x] [Decide] **Opt-in via `--with-attachments`, default off**, on `import`/`import-gmail`/`import-pst`/
  `import-thunderbird`. Mirrors the existing `-r`/`--recursive` pattern. Off by default because it adds
  real cost to every sync: an extra Gmail API call per attachment, extra local disk I/O and space for
  PST/Thunderbird (which already read the bytes to compute `size`, so no extra I/O there - only extra disk
  space).
- [x] [Implement] `config.py`: add `ATTACHMENTS_DIR = DATA_DIR / "attachments"`.
- [x] [Implement] New `attachment_store.py`: `save(content: bytes) -> str` (sha256 hex digest,
  write-if-absent) and `path_for(sha256: str) -> Path` (plus `read()`, used by `export`).
- [x] [Implement] `db.py`: add `content_sha256 TEXT` to the `attachments` schema + `_ensure_column`
  migration; extend `upsert_attachments` to persist it (defaulting to `None`/absent key when a caller
  doesn't supply one).
- [x] [Implement] `gmail_client.py`: add `fetch_attachment_content(service, message_id, attachment_id) ->
  bytes` - one `users.messages.attachments.get` call, base64url-decode the returned `data` field.
- [x] [Implement] `thunderbird/messages.py`: extend `parse_attachments` to optionally return the
  already-decoded payload bytes alongside existing metadata (`with_content` param) - `part.get_payload
  (decode=True)` already runs to compute `size`, so no new I/O.
- [x] [Implement] `outlook/messages.py`: add attachment-content fetch (`PROP_LTP_ROW_ID` -> `pst.
  resolve_nid()` + `read_property_context()` -> read `PROP_ATTACH_DATA_BINARY`); `parse_attachments` takes
  an opt-in `pst` param mirroring the other two. No new low-level NDB/LTP machinery needed - reuses the
  existing large-binary/string property reading `read_property_context`/`PSTProperty` already do.
- [x] [Implement] `cli.py`: add `--with-attachments` to `import`/`import-gmail`/`import-pst`/
  `import-thunderbird`; when set, fetch content per attachment, `attachment_store.save()` it, and pass the
  resulting `content_sha256` into `upsert_attachments`. Gmail's fetch is a dedicated helper
  (`_fetch_and_store_gmail_attachment_content`) since it needs a live API call keyed by the real
  (unprefixed) message id - including for a `--recursive` sub-message's attachments, which are still
  scoped to the *parent* message's id, not the synthesized sub-id (covered by a dedicated regression test).
  PST/Thunderbird share one small generic post-step (`_attach_content_to_store`) since their bytes are
  already in hand locally.
- [x] [Implement] `cli.py` `export`: `--format eml` attaches real content when `content_sha256` is set
  (`_build_eml_message`, via `msg.add_attachment()` after `set_content()`); `--format md` writes the
  `<stem>.attachments/` sidecar directory. Frontmatter/`X-Mail-Utils-Attachment` metadata-only behavior is
  unchanged when `content_sha256` is `NULL`. `store-in-gmail`'s DB-sourced path picks this up for free
  (same `_build_eml_message`) - confirmed with a dedicated test rather than assumed.
- [x] [Verify] `db.py` schema-migration test mirroring the existing `_ensure_column` coverage;
  `attachment_store.py` unit tests (stable hash, write-once dedup, `path_for` round-trip);
  `gmail_client.fetch_attachment_content` mocked-service decode test; extended Thunderbird/Outlook fixture
  tests to assert content bytes match the real fixture payload; `cli.py` integration tests confirming
  `import* --with-attachments` populates `content_sha256` and writes a file, while the same command
  *without* the flag leaves `content_sha256` `NULL` and writes nothing new (regression guard on the default
  path); `export` format tests for both real-MIME-attachment and metadata-only-header cases.
- [x] [Verify] Full suite: 174 passed, 2 skipped (pre-existing local-PST-fixture-only skips, unrelated).
  `ruff check .`/`ruff format --check .`: clean. `python -m build`: sdist + wheel built cleanly,
  `attachment_store.py` present in the wheel.
- [x] [Verify] Manual end-to-end smoke test: built a synthetic Thunderbird `.pcv` with one real attachment,
  ran `mail-utils import-thunderbird --with-attachments` via the real CLI entry point, confirmed
  `content_sha256` populated and exact bytes landed at `data/attachments/<hash>`, then confirmed
  byte-for-byte round-trip via both `export --format eml` (real MIME part, no
  `X-Mail-Utils-Attachment` header) and `--format md` (`<stem>.attachments/report.pdf` sidecar, frontmatter
  still filename/type/size only). Storage-impact note: this was a synthetic single-attachment smoke test,
  not a real mailbox, so it doesn't answer "how much does this grow `data/` for an image/PDF-heavy
  mailbox" with a real number - flagged as outstanding rather than closed out.
- [x] [Doc] `docs/cli-spec.md`: documented `--with-attachments` on all four import subcommands and the
  export fallback behavior.
- [x] [Doc] `README.md`: added the "Database contents" section (didn't exist before this task) documenting
  every table, the new `content_sha256` column, the `data/attachments/` content-addressed layout, and the
  no-auto-migration caveat. Also updated `docs/tutorial.md`'s ingest/export sections and the README "Key
  Features" list.
- [x] [Visual] N/A - no UI surface; CLI-only feature.

## Progress & Validation Log

- 2026-08-27: Claimed and scoped (storage/flag/per-source-fetch decisions - see Task Implementation steps
  above).
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
  anticipated.
- Found and worked around one pre-existing (unrelated to this task) quirk while writing the
  recursive-import + attachments test: `gmail_client.parse_attachments` walks MIME parts without
  stopping at a `message/rfc822` boundary, so a nested sub-message's own attachment gets picked up
  *twice* - once attributed to the parent message, once to the extracted child message - when
  `--recursive` is combined with a forwarded email that itself has an attachment. Not a correctness
  bug (both copies get the right content, just double-fetched/stored under two message ids), so left
  as-is and out of scope here; worth a follow-up adhoc task if it turns out to matter in practice.

## Completion Record

- **Completed:** 2026-08-28
- **Summary:** `import`/`import-gmail`/`import-pst`/`import-thunderbird` gained an opt-in `--with-attachments`
  flag that fetches each attachment's actual bytes and stores them content-addressed under
  `data/attachments/<sha256>`, recorded via a new `attachments.content_sha256` column. `export` and
  `store-in-gmail` (verified on request, no extra code needed) round-trip that content back out; behavior
  is unchanged for anyone who doesn't pass the new flag.
- **Follow-ups spun out, not part of this task:** none filed as new tasks - the two items noted above (the
  pre-existing double-fetch quirk on `--recursive` + a forwarded email with its own attachment, and the
  still-open real-mailbox storage-impact measurement) are left as documented findings rather than new
  backlog entries, since neither blocks this task's own completion criteria.
- **Review:** No PR, solo, AI agent - summary presented to the user in-conversation; user confirmed the
  `store-in-gmail` content pass-through explicitly before authorizing integration ("if yes: proceed").
