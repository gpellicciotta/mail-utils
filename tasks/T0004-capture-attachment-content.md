# T0004: Capture full attachment content, not just metadata

- **Status:** active
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

Not yet planned - flagged for scoping when picked up. Needs an explicit decision on storage location
(inline BLOB vs. content-addressed files) and default behavior (opt-in flag vs. always-on) before
implementation starts.

## Implementation Checklist

(not yet planned)

## Test Strategy

(not yet planned)

## Completion Criteria

(not yet planned)

## Progress Log

(not started)

## Validation Record

(not started)

## Completion Record

(not started)
