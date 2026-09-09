# Gmail Full-Archive Migration Report (T0033)

This document is the full execution record for `store-in-gmail`'s first production run: migrating the
complete local archive into the `gio-rw` Gmail account (`giovanni.pellicciotta@gmail.com`). It exists
because the run spanned several days, several agent handoffs, and one investigation into an apparently
missing database - the numbers below are the reconciled ground truth, not any single log excerpt.

## Summary

- Candidates: 187,353 messages (sourced from Outlook `.pst` and Thunderbird `.pcv` archives, previously
  imported into a local database).
- **All 187,353 messages (100%) are now stored in Gmail.** The bulk migration stored 186,907
  (99.76%) by 2026-09-08 23:53:32; the remaining 446 (0.24%) initially failed Gmail's attachment
  validation and were recovered on 2026-09-09 by retrying with attachments stripped - see
  [Attachment-stripped retry](#attachment-stripped-retry).
- Target account confirmed live (2026-09-09, post-cleanup): 204,025 messages / 199,095 threads in
  `gio-rw` (`giovanni.pellicciotta@gmail.com`).
- Both runs completed cleanly: `sync_state.gmail_store_run_label` is empty, meaning
  `_finish_gmail_store_run` ran each time (every candidate was processed, neither run was cut short).

## Timeline

- 2026-09-05: T0033 claimed. Full archive migration plan initialized.
- 2026-09-06: OAuth verified for `gio-rw`; 187,353 total candidates confirmed, of which 76,295 were
  already marked stored (carried over from earlier `store-in-gmail` pilot activity in T0032/T0031, before
  T0033 itself started uploading).
- 2026-09-06 to 2026-09-08: Iterative resumable runs, progress logged roughly hourly (`git log
  task/T0033-execute-store-in-gmail-full-archive` has ~34 progress commits). Four code fixes landed
  during this window to harden the run against real-world failures:
  - Exponential backoff retries for transient network timeouts/server errors.
  - `HttpLib2Error` handling and a larger retry buffer for DNS drops.
  - Retry attempts extended to twelve, with a 60-second backoff cap.
  - Pre-emptive skip for messages exceeding Gmail's 25 MB import limit, plus catching unsendable
    payload errors instead of crashing.
- 2026-09-08 ~17:09 CEST: host server restart killed the upload process mid-run at 170,350 stored
  (90.9%); relaunched 17:12 CEST and resumed cleanly from the local DB checkpoint - no duplicate
  uploads, confirming the dedup-by-`gmail_store_state` design worked as intended under a real crash.
- 2026-09-08 15:12:38 to 23:53:32 (final run, 31,254.4s / ~8h 41m): 16,970 newly stored, 170,383 skipped
  (already-stored dedup plus this run's own permanent failures), ending at 187,350/187,353 in the live
  progress counter.
- 2026-09-08 23:53:32: `store-in-gmail` process logged its completion summary and exited. No further
  mail-utils activity is logged again until the next morning.
- 2026-09-09 06:08-06:59: a `stats`/`check-gmail-account` check (run by the antigravity agent, per its
  own account-mismatch retry pattern in the log) discovered `data/mails.db` missing at the documented
  default path and re-verified the live account totals. No further task-file/TODO.md update followed -
  antigravity ran out of credits at this point and Claude took over the investigation.
- 2026-09-09 10:01-10:06: 10-message pilot of the new attachment-stripped retry, all 10 recovered.
- 2026-09-09 (targeted completion run, 2,768.8s / ~46 min): all remaining 436 messages retried via a
  script querying only the still-unstored rows directly (avoiding a 187k-row rescan) - **436/436
  recovered, 0 permanent failures**. Combined with the pilot: all 446 originally-failed messages are now
  stored. `mails.db`'s `gmail_store_state` table has 187,353 rows, matching `messages` exactly.

## The "missing database" false alarm

`docs/specs/gmail-production-recovery-plan.md` documents `--db data/` (the project default) as the run's
database location. The actual production run was pointed at
`work/T0020-full-archive-import-and-eml-roundtrip/data/storage/work-mail/mails.db` (5.4 GB) instead -
reusing T0020's existing full-archive database rather than building a fresh one under `data/`. That
database was never lost; the recovery-plan doc and the task file simply never recorded the real path,
so both antigravity's own morning check and Claude's independent investigation looked in the wrong place
and (briefly, and incorrectly) suspected data loss. `docs/specs/gmail-production-recovery-plan.md` should
be corrected to reference the actual path, or the run should be pointed at the documented default on any
future full-archive migration, so this doesn't recur.

No evidence in the log suggests the database was ever deleted or corrupted - mail-utils itself never
deletes its own database file, and the file's contents (187,353 messages, then 186,907
`gmail_store_state` rows, now 187,353 after the cleanup below) are fully consistent with the log's own
reported progress.

## Error catalogue

As of 2026-09-08 23:53:32, every one of the 446 permanently unstored messages fell into one of two
mutually exclusive, deterministic categories - confirmed by cross-referencing the local database's
`gmail_store_state` gap against the log's error text. **All 446 were subsequently recovered** by the
attachment-stripped retry below; this section documents *why* they originally failed, not their current
state:

- **417 messages: Gmail API `400 Invalid attachment`** (`reason: invalidArgument`). Gmail's
  `messages.import` endpoint rejected the message's MIME structure, most likely due to malformed or
  non-conformant attachment encoding inherited from very old Outlook `.pst` entries (see
  [Gmail's attachment guidance](https://support.google.com/mail/answer/6590), referenced directly in the
  API's own error response). Retried identically on each subsequent run (the same ~417 messages recur
  every time, never succeeding as-is), confirming this is a deterministic per-message rejection, not a
  transient fault - resolved only once the offending attachment(s) were removed before import.
- **29 messages: payload exceeds Gmail's 25 MB import limit.** Caught pre-emptively by mail-utils'
  own size check before even calling the API (added specifically for this run - see Timeline above).

Across the full log history (all iterations combined, including repeated retries of the same
still-failing messages on each successive run): 1,459 `ERROR`-level "Failed to store ... (skipping
message)" entries and 55 `WARN`-level oversized-payload skips were logged in total. The unique-message
counts above (417 and 29) are what matters for final disposition; the larger totals simply reflect the
same messages being retried on every run until this report's investigation confirmed the retries were
futile.

## Attachment-stripped retry

Both failure categories are attachment-driven, so a targeted fix - retry each of the 446 with its
attachments stripped, keeping the message body, headers, and an audit note of what was removed - was
implemented (`_strip_attachments_for_retry` in `cli.py`) and run against all 446:

- 10-message pilot (2026-09-09 10:01-10:06): **10/10 recovered**.
- Full completion run against the remaining 436 (2026-09-09, 2,768.8s / ~46 min, via a targeted
  script querying only the still-unstored rows directly rather than re-scanning the full 187,353-row
  table): **436/436 recovered, 0 permanent failures**.
- **Result: 446/446 (100%) recovered.** 417 needed at least one attachment actually removed (931
  attachment files dropped in total, ~2.2 per message on average); the other 29 (the oversized-payload
  category) succeeded immediately once mail-utils' own pre-emptive size check stripped them before ever
  calling the Gmail API.
- Every stripped message keeps its original headers, subject, and body verbatim, with one line prepended
  noting how many attachments were removed and why - the original attachment bytes remain in the local
  attachment cache and are still recoverable from there (or via `export --format eml`) if ever needed;
  they are simply not present in the Gmail copy.

See the [Failed Messages Ledger](#failed-messages-ledger) below for the per-message outcome, and the
Execution Log in
[`tasks/T0033-execute-store-in-gmail-full-archive.md`](../../tasks/T0033-execute-store-in-gmail-full-archive.md)
for the task-level summary.

## Performance

Two figures matter here and they are not the same thing: **active processing time** (time the
`store-in-gmail` process actually spent throttled-calling the Gmail API) versus **calendar time**
(wall-clock span including idle gaps between sessions, restarts, and agent handoffs). Reporting only
the calendar figure would understate the throughput; reporting only the active figure would hide how
long the whole exercise actually took end-to-end.

A terminology note first, because it explains an apparent discrepancy in the source data: the CLI's own
`Store progress: X/Y messages` line reports `X = count + skipped` - candidates *examined*, not candidates
*stored* (`skipped` bags both already-stored dedup skips and this run's own permanent failures together).
The hourly task-log entries written during the run (e.g. "170,350 stored (90.9%)") were transcribed
straight from that line, so they are actually **processed** counts, not **stored** counts - they overstate
true storage progress by however many permanent failures had already accumulated at that point. The
figures below correct for this, using only values that are independently verifiable: the final
`gmail_store_state` row count (queried directly) and each run's own end-of-run completion summary (which
reports true `stored`/`skipped` separately, not the ambiguous progress-line total).

- **Verified reconciliation:** 187,353 candidates = 186,907 stored + 446 permanently failed as of
  2026-09-08 23:53:32 (exact - see [Error catalogue](#error-catalogue)); all 446 later recovered, so the
  database now shows 187,353 = 187,353 stored + 0 failed.
- **Calendar span:** T0033 claimed 2026-09-05 00:05:45 CEST -> final bulk-store completion
  2026-09-09 01:53:32 CEST = **~4 days 1h 48m**.
- **Active processing time, bulk migration** (two continuous segments, separated by the 2026-09-08
  server restart):
  - Segment A: 2026-09-06 15:21:24 -> 2026-09-08 15:01:49 UTC (killed by the restart) = 171,625s
    (~47h 40m). Its "170,350 stored" task-log entry is a *processed* figure; the true stored count
    entering segment B (derived below) was 169,937, so segment A actually stored approximately
    169,937 minus its own starting baseline (~76,295, itself a self-reported progress-log figure and
    the one number in this section not independently re-verified) = **~93,642 messages**, roughly
    **0.546 msg/s**.
  - Segment B: 2026-09-08 15:12:38 -> 23:53:32 UTC (clean completion) = 31,254.4s (~8h 41m). Its own
    completion line is exact and self-consistent: 16,970 stored + 170,383 skipped = 187,353 (the full
    candidate count, confirming it rescanned the whole table from message #1 rather than resuming from
    an index) = **0.543 msg/s**. Working backward, stored-before-segment-B = 186,907 - 16,970 =
    **169,937**; of segment B's 170,383 skips, 169,937 were already-stored dedup and 446 were
    permanent-failure skips (413 already known from segment A, 33 newly discovered during segment B
    itself) - 169,937 + 446 + 16,970 = 187,353, which closes exactly.
  - Combined active runtime: 202,879.4s (**~56h 21m**) for 186,907 - 76,295 = **110,612 verified new
    stores**, averaging **~0.545 msg/s** (~1,963 messages/hour). This throughput is dominated by the
    per-message Gmail API throttle (`_throttle_gmail_store`, ~1/s) plus building each candidate's MIME
    representation from the local database - not by network latency or backoff retries, which were rare.
- **Active processing time, attachment-stripped cleanup** (2026-09-09, this report's own fix):
  - 10-message pilot: 290.9s for 10 recovered (0.034 msg/s) - dominated by having to scan/skip the
    187k-row table via the normal `store-in-gmail` CLI path to reach 10 targets, not by the API calls
    themselves.
  - Full 436-message completion: 2,768.8s (~46 min) for 436 recovered, **0.157 msg/s** - roughly 3.5x
    slower per-message than the bulk migration despite having zero table-scan overhead (a direct SQL
    query selected only the 436 target rows up front), because most of these messages (the 407 in the
    "invalid attachment" category) needed *two* throttled API calls each - the original attempt, which
    Gmail was already known to reject, followed by the stripped retry - while the remainder (the
    oversized-payload category) needed only one, having been stripped pre-emptively before ever calling
    the API.
  - Combined cleanup: 3,059.7s (~51 min) recovering all 446, **0.146 msg/s** overall.

## Finding the imported mail in Gmail

Every message `store-in-gmail` writes gets two kinds of Gmail label, both applied via
`users.labels.create`/`messages.import`'s `labelIds`:

1. **A run-tracking label**, unique to the invocation that stored it, named
   `mail-utils-store-in-gmail-<UTC timestamp>`. This is the fastest way to find "everything mail-utils
   ever imported" as one Gmail search:
   - Bulk migration (187,353 candidates, 2026-09-04 22:10 -> 2026-09-08 23:53 UTC, surviving the
     2026-09-08 server restart since the label is persisted in `sync_state` until a run finishes
     uninterrupted): search Gmail for
     `label:mail-utils-store-in-gmail-2026-09-04T22-10-55Z`.
   - Today's attachment-stripped cleanup (446 messages, 2026-09-09): search Gmail for
     `label:mail-utils-store-in-gmail-2026-09-09T10-01-37Z`.
   - Both together: `label:mail-utils-store-in-gmail-2026-09-04T22-10-55Z OR label:mail-utils-store-in-gmail-2026-09-09T10-01-37Z`.
2. **The message's original folder label(s)**, translated from its source mailbox (e.g. an Outlook
   folder path or Thunderbird folder), created in Gmail if they didn't already exist there. These are
   what let you browse imported mail by its original folder structure rather than as one undifferentiated
   dump - e.g. Gmail's left-hand label list will show the recreated folder hierarchy alongside the two
   run labels above.

None of the imported mail lands in the Gmail inbox as "new" - `neverMarkSpam=True` is set but nothing
forces `INBOX` placement, so it's only visible via label/search, not by scrolling the inbox. This was a
deliberate design choice (see `docs/reverse-import-plan.md`) so a 187k-message import doesn't bury
everyday mail.

## Failed Messages Ledger

Every one of the 446 messages that initially failed Gmail's `messages.import` validation, with its
original date, subject, and how it was recovered, is listed in a separate companion file:
[`gmail-full-archive-migration-failed-messages.md`](gmail-full-archive-migration-failed-messages.md).
All 446 succeeded on the attachment-stripped retry (2026-09-09); none remain unstored.
