# Gmail Full-Archive Migration Report (T0020 and T0033)

This report covers local archive preparation (T0020) and the production Gmail migration (T0033).
The destination was account `gio-rw` (`giovanni.pellicciotta@gmail.com`).

## Summary

T0020 imported four email archives and produced 187,353 unique local messages.
T0033 migrated all 187,353 messages into Gmail for account `giovanni.pellicciotta@gmail.com`.
Bulk migration (2026-09-06 to 2026-09-08) stored 186,907 messages.
A cleanup run on 2026-09-09 recovered the remaining 446.

## Inputs

Four source archives were imported as part of T0020.
All four files reside under `data/inputs/`.

- `anubex-outlook-backup.pst` (25.69 GiB)
- `personal-email-backup.pst` (278.77 MiB)
- `personal-email-backup.pcv` (62.75 MiB)
- `anubex-friends-email.pst` (31.77 MiB)

The production SQLite database produced by T0020 is at `data/storage/work-mail/mails.db`,
with attachments at `data/storage/work-mail/attachments/`.
Use `--db data/storage/work-mail` when invoking mail-utils CLI commands against it.

## Verification

T0020 verified the local archive via a full import → EML export → reimport roundtrip on all 187,353 messages.
The comparator found zero body or attachment differences under its documented normalization rules (line endings, trailing newlines, HTML whitespace).
156 address-field findings were reported; 154 were formatting or invalid-source differences; two exposed a real parsing bug that was fixed.
A Hebrew/`bezeq` mailing-list cluster of 21 CC findings remained an accepted exception.
The full comparison was not rerun after the final fix, per explicit user instruction.

## Performance

T0033 completed all 187,353 messages in approximately 56 hours and 21 minutes of active upload time
(2026-09-06 to 2026-09-09), achieving roughly 0.54 messages/second throughout.
Cleanup of the remaining 446 failures took approximately 51 minutes.

> Note: the CLI's progress counter reflects `stored + skipped`. Skipped candidates include already-stored
> messages and failures, so progress percentages do not directly equal successful upload totals.

## Issues

- **Attachments blocked by Gmail API** — 417 messages received `400 Invalid attachment` responses.
  Approach: all 417 were successfully re-imported without their attachments using `_strip_attachments_for_retry`.
  Original attachment bytes remain available locally under `data/storage/work-mail/attachments/`.
  See the [failed messages ledger](gmail-full-archive-migration-failed-messages.md) for the full list.

- **Messages exceeding the local payload guard (25 MiB)** — 29 messages were skipped before the API call
  because their raw EML size exceeded the application's local threshold.
  These 29 were recovered in the cleanup run without modification.

- **Missing `From` or `Date` headers** — some messages in the source archive had no sender or date field.
  Approach: RFC 5322-compliant fallbacks were added (`From: unknown@unknown.invalid`, Unix epoch `Date`)
  to prevent Gmail HTTP 400 rejections.

- **Transient network failures** — DNS drops, socket timeouts, and SSL write errors occurred during
  the multi-day bulk run. Approach: `_gmail_call_with_backoff` was updated to catch
  `TimeoutError`, `ConnectionError`, `OSError`, and `httplib2.HttpLib2Error` with up to 12 exponential
  backoff retries capped at 60 seconds per attempt.

## Finding the Imported Mail in Gmail

Two Gmail labels were applied during the migration run:

- Bulk migration: `label:mail-utils-store-in-gmail-2026-09-04T22-10-55Z`
- Cleanup: `label:mail-utils-store-in-gmail-2026-09-09T10-01-37Z`

Source-folder labels provide another way to browse the imported archive in Gmail.
