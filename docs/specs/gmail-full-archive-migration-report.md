# Gmail Full-Archive Migration Report (T0020 and T0033)

This report covers local archive preparation in T0020 and the production Gmail migration in T0033.
The destination was account `gio-rw` (`giovanni.pellicciotta@gmail.com`).

The sources are [T0020's task report](../../tasks/T0020-full-archive-import-and-eml-roundtrip.md)
and [T0033's task report](../../tasks/T0033-execute-store-in-gmail-full-archive.md).
T0020's detailed execution record survives in Git at commit `d42a6f6`, before its condensation in `3614049`.
Read that version with:

```text
git show d42a6f6:tasks/T0020-full-archive-import-and-eml-roundtrip.md
```

## Summary

- T0020 imported four archives with attachments and recursive extraction, producing 187,353 unique local messages.
- The full local roundtrip found zero body or attachment differences under the comparator's documented normalization rules.
  Address exceptions remained; see [Source database provenance](#source-database-provenance-t0020).
- T0033 recorded all 187,353 messages as stored in Gmail after cleanup on 2026-09-09.
  This is message-count completion; some Gmail copies have attachments removed and their MIME bodies rebuilt.
- Bulk migration stored 186,907 messages (99.76%) by 2026-09-08 23:53:32 UTC.
  Cleanup recovered the remaining 446 (0.24%).
- The previous report recorded 204,025 messages and 199,095 threads in the destination account after cleanup.
  Those mailbox-wide totals are absent from the task reports and were not independently rechecked during this review.
- T0033's task file remains `needs-review`, with no completion date.
  Its execution log records successful migration while explicitly leaving code integration pending human review.

## Source database provenance (T0020)

T0020 ran from 2026-08-31 through 2026-09-04.
It implemented `import-eml` and `scripts/local-roundtrip-test.py`, then exercised the complete import/export/reimport pipeline.

The user subsequently relocated the original inputs, production database, and mail exports under
`C:\Dev-Projects\mail-utils\data`.
Paths below distinguish current artifacts from historical validation locations.

- Import: all four inputs exist under `data/inputs/`.
  Sizes below are rounded from their current byte lengths, using binary units.
  - `anubex-outlook-backup.pst`: 25.69 GiB.
  - `personal-email-backup.pst`: 278.77 MiB.
  - `personal-email-backup.pcv`: 62.75 MiB.
  - `anubex-friends-email.pst`: 31.77 MiB.

- Store: the production database is `data/storage/work-mail/mails.db`.
  Its attachment store is `data/storage/work-mail/attachments/`.
  Use `--db data/storage/work-mail`; neither `--db data/` nor `--db data/storage/` identifies that database.

- Export: the relocated Markdown export is `data/exports/work-mail-md/`.
  T0020 also produced a full EML export, historically named `data/exports/work-mail-eml/` inside its worktree.
  That full EML directory was not found at either the historical or proposed relocated path during this review.
  The existing `data/exports/work-mail-smoke-eml/` is a separate smoke-test artifact.

- Reimport: T0020 imported the EML export into a separate roundtrip database.
  That database still exists at
  `work/T0020-full-archive-import-and-eml-roundtrip/data/storage/work-mail-roundtrip/mails.db`.
  It was not found at the previously stated relocated path, `data/storage/work-mail-roundtrip/`.

- Verify: the comparator paired messages by preserved `X-Mail-Utils-ID` and compared attachment bytes from each database's store.
  Body comparisons normalized line endings and trailing newlines; HTML comparisons also normalized whitespace.
  This was a fidelity check with accepted transformations, rather than byte-identical equality of every message field.

The last full comparison covered 187,353 messages and reported 156 address-field findings, with zero body or attachment findings.
The detailed record ultimately classified 151 as formatting/encoding differences and three as already-invalid spam addresses.
The remaining two exposed a real bracketed-display-name parsing bug.
That fix passed direct checks against the affected messages and a fresh 3,542-message integration cycle.
The full 187,353-message comparison was not rerun after that final fix, following the user's explicit instruction.

A Hebrew/`bezeq` mailing-list cluster remained an accepted, incompletely investigated address exception.
The detailed record identifies 21 CC findings in that cluster.
Consequently, neither “zero differences across all fields” nor unconditional losslessness accurately describes T0020's final evidence.

## Timeline

Dates without times follow the task records. Timed migration log entries below use UTC unless explicitly marked CEST.

- `2026-08-31`: T0020 was claimed; `import-eml` was implemented with preserved identifiers, attachment content, and internal timestamps.
  Initial validation passed 218 tests, with two skipped.
  After authorization, archive import began; the smallest PST exposed unsupported ANSI format, creating dependency T0021.

- `2026-09-01`: A separate small-archive smoke test ran while the large PST import continued.
  It exposed header unfolding, non-ASCII address decoding, attachment size/encoding, and unquoted-display-name problems.

- `2026-09-02`: Investigation stopped the slowing large import after approximately 31.5 hours.
  Per-message FTS5 maintenance was the dominant bottleneck; bulk index rebuilding and transaction batching were implemented.
  A subsequent complete large-PST import processed 186,475 entries in 3,049.8 seconds (50.8 minutes).
  Diagnostic writes had also contaminated the working database; synthetic rows were removed and affected source content was reimported.

- `2026-09-02`: T0021 added ANSI PST support, T0026 enabled recursive PST extraction, and T0027 fixed comma-separated display names.
  A fresh three-small-archive cycle passed with 3,542 unique messages.
  T0024's parallel-import implementation remained deferred after the single-process performance improvement.

- `2026-09-03`: All four archives produced 187,353 unique messages.
  Export and comparison hit memory exhaustion from loading complete message bodies simultaneously.
  Streaming fixes enabled full Markdown and EML exports.
  The first full comparison reported 1,504 findings; focused reparsing and fixes reduced the subset result to 133.
  That subset count was not a final full-archive result.

- `2026-09-04`: Fresh full cycles reduced address findings from 246 to 156, with zero body or attachment findings.
  The final bracketed-display-name fix passed affected-message checks and a 3,542-message rerun.
  T0020 closed with accepted address exceptions and no further full-scale rerun; 263 tests passed, with two skipped.

- `2026-09-05`: T0033 was claimed and its production migration plan initialized.
  Missing From/Date fallbacks and initial transient-error backoff were committed that day.

- `2026-09-06`: OAuth was verified for `gio-rw`; T0033 reported 187,353 candidates and a 76,295 already-stored baseline.
  That baseline's precise derivation is not preserved in the task report.
  Attribution to T0031/T0032 pilots is unsupported: T0031 tested a disposable account, and T0032 documented recovery procedures.
  DNS/`HttpLib2Error` handling, twelve retry attempts, and the local payload-size guard were committed by this date.

- `2026-09-06 to 2026-09-08`: The bulk run continued with periodic monitoring and transient network failures.
  Many hourly task entries called the CLI's processed counter “stored”; those counts include skipped candidates.

- `2026-09-08 ~17:09 CEST`: The task report records a host restart interrupting the upload at 170,350 processed candidates.
  The last preceding log activity was at 15:01:49 UTC (17:01:49 CEST); the exact interruption time is uncertain.
  Relaunch occurred at 15:12:38 UTC (17:12:38 CEST), using existing storage checkpoints.

- `2026-09-08 15:12:38–23:53:32 UTC`: The final bulk invocation stored 16,970 messages and skipped 170,383.
  Its completion summary accounts for all 187,353 candidates.
  The last periodic progress line, 187,350/187,353, was not the completion total.

- `2026-09-08 23:53:32 UTC` (`2026-09-09 01:53:32 CEST`): Bulk migration completed with 186,907 stored and 446 unresolved.

- `2026-09-09`: The handoff investigation reconciled storage counts and resolved an apparent missing-database alarm.
  The production run had used T0020's worktree database instead of the documented default.
  That historical path discrepancy predates the user's relocation of the production database into top-level `data/storage/work-mail/`.

- `2026-09-09`: Attachment-retry support passed the recorded suite of 276 tests, with two skipped.
  A 10-message pilot and targeted 436-message run recovered all 446 failures.
  T0033 recorded 187,353 storage-state rows matching its message count, while retaining pending integration status.

## Error catalogue

T0033 reconciled the 446 messages unresolved after bulk migration into two categories:

- 417 messages received Gmail API `400 Invalid attachment` responses.
  The exact reason for each attachment rejection was not established.
  The linked [Gmail attachment guidance](https://support.google.com/mail/answer/6590) describes blocked file types and archive contents.
  It does not establish malformed MIME encoding as the cause.

- 29 messages exceeded mail-utils' local payload threshold of `25 * 1024 * 1024` bytes (25 MiB).
  They were skipped before an API call, so this category does not demonstrate a Gmail rejection.

The previous wording called the second category “Gmail's 25 MB import limit.”
That conflated the implementation's local guard with the service limit.
The [Gmail import reference](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/import)
currently documents a 150 MB maximum message size.
This review corrects the historical description; it does not change the application threshold.

The earlier report counted 1,459 error-level failed-store entries and 55 oversized-payload warnings across repeated attempts.
Those are log-event totals, rather than unique failed messages; they should not replace the reconciled 417 + 29 count.

## Attachment-stripped retry

T0033 added `_strip_attachments_for_retry` in [cli.py](../../src/mail_utils/cli.py).
The task report records 10/10 pilot recoveries followed by 436/436 targeted recoveries, with no remaining failures.

The [failure ledger](gmail-full-archive-migration-failed-messages.md) contains 446 rows:

- 417 rows record attachments dropped, totaling 931 recorded attachments.
- 29 rows say “recovered on retry (succeeded without modification).”

These outcome counts happen to match the original failure-category sizes.
The ledger does not identify those 29 unchanged successes as the 29 original oversized messages.
Nor does it establish whether “without modification” overlooked any preprocessing in the targeted script.
The previous report's one-to-one mapping between failure categories and recovery mechanisms was therefore unsupported.

The retry helper rebuilds the MIME message, copying non-content headers and choosing HTML preferentially over plain text.
For plain-only mail, it appends the audit note.
For HTML mail, it keeps the HTML body and supplies the note as the plain-text alternative.
Original MIME headers and alternative-body structure are not preserved verbatim, and stripped inline images cannot render from their removed parts.

The helper leaves the source database and attachment store unchanged.
Removed attachment bytes remain available locally for later export.
This means T0033 achieved full message-count coverage, while narrowing its original lossless-upload goal for affected Gmail copies.

## Performance

The CLI's progress count is `stored + skipped`.
Skipped candidates include already-stored messages and failures, so progress percentages cannot establish successful storage totals.

- Reconciliation: 187,353 candidates = 186,907 bulk stores + 446 cleanup recoveries.
- Calendar span: T0033's claim at 2026-09-05 00:05:45 CEST to bulk completion at 2026-09-09 01:53:32 CEST.
  This is approximately four days, one hour, and 48 minutes; cleanup occurred afterward.
- Segment A: first log at 2026-09-06 15:21:24 UTC through last activity at 2026-09-08 15:01:49 UTC.
  The observed interval is 171,625 seconds (47 hours, 40 minutes).
- Segment B: 2026-09-08 15:12:38–23:53:32 UTC.
  The completion summary reports 31,254.4 seconds and 16,970 new stores: 0.543 messages/second.
  The 170,383 skips reconcile as 169,937 previously stored messages plus 446 failures.
- **[Estimation]** Combined observed runtime is 202,879.4 seconds, approximately 56 hours and 21 minutes.
  Using the reported 76,295 baseline gives approximately 110,612 new stores at 0.545 messages/second.
  This baseline was not independently verified; the result must not be labeled “verified new stores.”
- Reported cleanup durations: 290.9 seconds for the pilot and 2,768.8 seconds for the remaining 436 messages.
  Together, that is 3,059.7 seconds (approximately 51 minutes), or 0.146 recovered messages/second.
  These timings come from the earlier summary and are not specified in T0033's task report.

These intervals include scanning, MIME construction, network calls, throttling, and retries.
The records do not isolate those costs sufficiently to attribute throughput chiefly to throttling or exclude network latency.
Likewise, they do not establish an exact one-call/two-call breakdown for the cleanup categories.

## Finding the imported mail in Gmail

The application applies a run-tracking label and labels derived from each message's source folders.
An interrupted or capped invocation reuses the persisted run label.
A complete scan clears that local label state, even if individual messages failed.

The earlier report recorded these production labels:

- Bulk migration: `label:mail-utils-store-in-gmail-2026-09-04T22-10-55Z`.
- Cleanup: `label:mail-utils-store-in-gmail-2026-09-09T10-01-37Z`.
- Combined search:
  `label:mail-utils-store-in-gmail-2026-09-04T22-10-55Z OR label:mail-utils-store-in-gmail-2026-09-09T10-01-37Z`.

These searches select the named runs; they do not establish coverage of every historical mail-utils invocation.
Source-folder labels provide another way to browse the imported archive.

The implementation does not explicitly add `INBOX` and requests `neverMarkSpam=True`.
However, the [import API](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/import)
performs delivery scanning and classification.
Those settings alone do not substantiate the previous guarantee that no imported message can appear in the inbox.

## Review findings and remaining uncertainties

The 2026-09-09 review corrected the timeline, provenance, and interpretation of the recorded results.

- T0020's condensed report obscures the detailed record's accepted address differences and limited final rerun.
  Its historical Completion Record also ambiguously groups 151 formatting findings and three invalid-source findings.
  The preceding explicit decision entry resolves the accounting as 151 + 3 + 2 = 156.
- T0033's hourly entries confuse processed candidates with successful stores.
  One entry also calls 66.03% “surpassing two-thirds”; two-thirds is approximately 66.67%.
- T0033 records successful execution but remains `needs-review`; its task entry is absent from `TODO.md`.
  Migration completion and integration status are separate facts.
- An empty `gmail_store_run_label` establishes cleared run state, not a history proving that two particular invocations completed.
  Completion summaries and storage reconciliation provide the relevant evidence.
- Current artifact inspection confirms the relocated source database, attachment directory, input archives, and Markdown export.
  It also finds the roundtrip database in the old worktree and no full EML export at either documented location.
- No Gmail calls or fresh full-archive comparison were performed during this documentation review.
  Read-only attempts to open the relocated SQLite database failed with “unable to open database file.”
  The final storage totals therefore remain attributed to T0033's recorded reconciliation.

## Failed Messages Ledger

The [companion ledger](gmail-full-archive-migration-failed-messages.md) lists each initially unresolved message and its recorded recovery outcome.
All 446 are recorded as recovered; the attachment-preservation qualifications above still apply.
