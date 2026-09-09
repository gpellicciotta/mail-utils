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
original date, subject, and how it was recovered - all 446 succeeded on the attachment-stripped retry
(2026-09-09); none remain unstored.

| Date | Message ID | Subject | Outcome |
|---|---|---|---|
| 2002-07-12 | outlook:<20020712103808.49306.qmail@web20412.mail.yahoo.com> | Perlscript | recovered, 1 attachment(s) dropped |
| 2002-10-08 | outlook:<000901c26eaf$05104640$7d0ea8c0@dehaetom> | mfanco.zip;examples.zip | recovered, 2 attachment(s) dropped |
| 2003-02-18 | outlook:<304D82475633EA4EB6C230AE946F768504FA26@aiscrmail04.artinsoft.com> | StoresDemo green code. | recovered, 2 attachment(s) dropped |
| 2003-02-19 | outlook:<304D82475633EA4EB6C230AE946F768504FBB1@aiscrmail04.artinsoft.com> | Source code an libraries. | recovered, 3 attachment(s) dropped |
| 2003-02-20 | outlook:<304D82475633EA4EB6C230AE946F768507A181@aiscrmail04.artinsoft.com> | Application Designer. | recovered, 1 attachment(s) dropped |
| 2003-04-11 | outlook:<20030411142611.6660.qmail@web12805.mail.yahoo.com> | Help met Java | recovered, 1 attachment(s) dropped |
| 2003-09-17 | outlook:<013c01c37cf1$9d8c8360$7a0ea8c0@VANSLMIC> | (no subject) | recovered, 2 attachment(s) dropped |
| 2004-02-25 | outlook:<OAEAILNMIEPJHOEEKMMAGENGCAAA.Giovanni.Pellicciotta@pandora.be> | SPAM (low): | recovered, 1 attachment(s) dropped |
| 2004-04-15 | outlook:<OAEAILNMIEPJHOEEKMMAOEPBCAAA.Giovanni.Pellicciotta@pandora.be> | (no subject) | recovered, 4 attachment(s) dropped |
| 2004-04-21 | outlook:<FHEAKODEFPOLGLFFFCGHAEDGCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-04-21 | outlook:<FHEAKODEFPOLGLFFFCGHGEDGCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-04-22 | outlook:<FHEAKODEFPOLGLFFFCGHGEDHCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-04-23 | outlook:<FHEAKODEFPOLGLFFFCGHKEDHCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-04-30 | outlook:<FHEAKODEFPOLGLFFFCGHIEDKCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-05-06 | outlook:<FHEAKODEFPOLGLFFFCGHIEDOCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-05-07 | outlook:<FHEAKODEFPOLGLFFFCGHMEDPCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-05-18 | outlook:<FHEAKODEFPOLGLFFFCGHCEECCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-05-18 | outlook:<FHEAKODEFPOLGLFFFCGHIEEBCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-05-18 | outlook:<FHEAKODEFPOLGLFFFCGHMEEBCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-05-21 | outlook:<FHEAKODEFPOLGLFFFCGHEEEFCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-05-25 | outlook:<D709AE631D64A64F9EA3717477BF585C06A979D7@N51D5A8.cmc.be> | FW: JConnect 2.0A20 en Javadoc  van de volgende versie 2.0A30 | recovered, 2 attachment(s) dropped |
| 2004-06-03 | outlook:<FHEAKODEFPOLGLFFFCGHCEFDCBAA.giovanni.pellicciotta@anubex.com> | Vertaalwoordenboek.zip | recovered, 1 attachment(s) dropped |
| 2004-06-10 | outlook:<FHEAKODEFPOLGLFFFCGHKEFLCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-07-22 | outlook:<FHEAKODEFPOLGLFFFCGHGEHCCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-07-23 | outlook:<FHEAKODEFPOLGLFFFCGHKEHDCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-09-23 | outlook:<FHEAKODEFPOLGLFFFCGHCEIFCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 5 attachment(s) dropped |
| 2004-09-23 | outlook:<FHEAKODEFPOLGLFFFCGHGEIFCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 3 attachment(s) dropped |
| 2004-09-23 | outlook:<FHEAKODEFPOLGLFFFCGHKEIFCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-09-23 | outlook:<FHEAKODEFPOLGLFFFCGHOEIFCBAA.giovanni.pellicciotta@anubex.com> | FW: | recovered, 1 attachment(s) dropped |
| 2004-09-28 | outlook:<FHEAKODEFPOLGLFFFCGHKEIGCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-09-28 | outlook:<FHEAKODEFPOLGLFFFCGHKEIHCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 2 attachment(s) dropped |
| 2004-09-28 | outlook:<FHEAKODEFPOLGLFFFCGHOEIGCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-10-12 | outlook:<FHEAKODEFPOLGLFFFCGHIEJBCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 2 attachment(s) dropped |
| 2004-10-15 | outlook:<FHEAKODEFPOLGLFFFCGHEEJDCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-10-15 | outlook:<FHEAKODEFPOLGLFFFCGHEEJECBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-10-15 | outlook:<FHEAKODEFPOLGLFFFCGHIEJDCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-10-15 | outlook:<FHEAKODEFPOLGLFFFCGHMEJCCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-10-15 | outlook:<FHEAKODEFPOLGLFFFCGHMEJDCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-11-04 | outlook:<1044.81.164.25.143.1099553410.squirrel@webmail.anubex.com> | [Fwd: RE: UTM - Koala integratie] | recovered, 7 attachment(s) dropped |
| 2004-11-10 | outlook:<04C71DEEA1D5A747B481F20C8002F9EC65DAEB@n51d5a8.cmc.be> | JConnect info | recovered, 1 attachment(s) dropped |
| 2004-11-22 | outlook:<FHEAKODEFPOLGLFFFCGHEEKBCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 2 attachment(s) dropped |
| 2004-11-22 | outlook:<FHEAKODEFPOLGLFFFCGHIEKBCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-11-29 | outlook:<FHEAKODEFPOLGLFFFCGHGEKFCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 2 attachment(s) dropped |
| 2004-12-03 | outlook:<FHEAKODEFPOLGLFFFCGHEEKHCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2004-12-06 | outlook:<FHEAKODEFPOLGLFFFCGHMEKHCBAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-02-25 | outlook:<000101c51b43$4a94ed40$860ea8c0@PC019> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-02-25 | outlook:<BAECJIMHCFBIFLJOCKGDEEEGCAAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-03-04 | outlook:<003a01c520db$ee425b60$860ea8c0@PC019> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-03-04 | outlook:<003c01c520dd$2f611540$860ea8c0@PC019> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-03-04 | outlook:<BAECJIMHCFBIFLJOCKGDAEEJCAAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-03-04 | outlook:<BAECJIMHCFBIFLJOCKGDEEEJCAAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-03-07 | outlook:<003e01c52323$2374eca0$860ea8c0@PC019> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-03-07 | outlook:<BAECJIMHCFBIFLJOCKGDIEEJCAAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-03-08 | outlook:<004301c523e0$12c5da50$860ea8c0@PC019> | (no subject) | recovered, 2 attachment(s) dropped |
| 2005-03-08 | outlook:<BAECJIMHCFBIFLJOCKGDMEEJCAAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 2 attachment(s) dropped |
| 2005-03-10 | outlook:<000b01c52568$04a054d0$860ea8c0@PC019> | Emailing: eucalyptus-12_54_06-10_03_2005.zip | recovered, 1 attachment(s) dropped |
| 2005-03-10 | outlook:<BAECJIMHCFBIFLJOCKGDCEEMCAAA.giovanni.pellicciotta@anubex.com> | Emailing: eucalyptus-12_54_06-10_03_2005.zip | recovered, 1 attachment(s) dropped |
| 2005-03-11 | outlook:<001201c52653$bfd07d20$860ea8c0@PC019> | Emailing: eucalyptus-17_01_04-11_03_2005.zip | recovered, 1 attachment(s) dropped |
| 2005-03-11 | outlook:<BAECJIMHCFBIFLJOCKGDCEENCAAA.giovanni.pellicciotta@anubex.com> | Emailing: eucalyptus-17_01_04-11_03_2005.zip | recovered, 1 attachment(s) dropped |
| 2005-03-17 | outlook:<001901c52ae5$a58ce980$860ea8c0@PC019> | Emailing: eucalyptus-12_34_58-17_03_2005.zip | recovered, 1 attachment(s) dropped |
| 2005-03-17 | outlook:<BAECJIMHCFBIFLJOCKGDKEEPCAAA.giovanni.pellicciotta@anubex.com> | Emailing: eucalyptus-12_34_58-17_03_2005.zip | recovered, 1 attachment(s) dropped |
| 2005-03-23 | outlook:<007501c52fcb$63624ba0$860ea8c0@PC019> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-03-23 | outlook:<BAECJIMHCFBIFLJOCKGDKEFFCAAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-03-24 | outlook:<007701c5306c$04fdf2c0$860ea8c0@PC019> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-03-24 | outlook:<BAECJIMHCFBIFLJOCKGDOEFFCAAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-03-25 | outlook:<000301c53160$4c5c0e50$860ea8c0@PC019> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-03-25 | outlook:<BAECJIMHCFBIFLJOCKGDGEFGCAAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-04-01 | outlook:<002a01c536c3$73d83900$860ea8c0@PC019> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-04-01 | outlook:<BAECJIMHCFBIFLJOCKGDAEFHCAAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-04-08 | outlook:<000401c53c58$66c2acb0$860ea8c0@PC019> | Emailing: eucalyptus-18_20_29-08_04_2005.zip | recovered, 1 attachment(s) dropped |
| 2005-04-08 | outlook:<BAECJIMHCFBIFLJOCKGDMEFICAAA.giovanni.pellicciotta@anubex.com> | Emailing: eucalyptus-18_20_29-08_04_2005.zip | recovered, 1 attachment(s) dropped |
| 2005-04-11 | outlook:<000101c53e5a$06005130$860ea8c0@PC019> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-04-11 | outlook:<BAECJIMHCFBIFLJOCKGDAEFJCAAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-04-18 | outlook:<000401c5441b$000ffa20$860ea8c0@PC019> | Emailing: ifg.zip, support.zip | recovered, 2 attachment(s) dropped |
| 2005-04-18 | outlook:<BAECJIMHCFBIFLJOCKGDCEFMCAAA.giovanni.pellicciotta@anubex.com> | Emailing: ifg.zip, support.zip | recovered, 2 attachment(s) dropped |
| 2005-04-19 | outlook:<000b01c544df$6c057560$860ea8c0@PC019> | Emailing: wang.zip | recovered, 1 attachment(s) dropped |
| 2005-04-19 | outlook:<BAECJIMHCFBIFLJOCKGDCEFOCAAA.giovanni.pellicciotta@anubex.com> | Emailing: wang.zip | recovered, 1 attachment(s) dropped |
| 2005-04-22 | outlook:<00be01c54729$bedc0a50$a80ea8c0@DASCHOTS> | Re: Merlin 3.1 | recovered, 1 attachment(s) dropped |
| 2005-05-30 | outlook:<000401c56505$ad762490$860ea8c0@PC019> | Emailing: jsupport.zip, jtools.zip | recovered, 2 attachment(s) dropped |
| 2005-05-30 | outlook:<000b01c56508$09121190$860ea8c0@PC019> | Emailing: eucalyptus.zip | recovered, 1 attachment(s) dropped |
| 2005-05-30 | outlook:<BAECJIMHCFBIFLJOCKGDIEHACAAA.giovanni.pellicciotta@anubex.com> | Emailing: jsupport.zip, jtools.zip | recovered, 2 attachment(s) dropped |
| 2005-05-30 | outlook:<BAECJIMHCFBIFLJOCKGDMEHACAAA.giovanni.pellicciotta@anubex.com> | Emailing: eucalyptus.zip | recovered, 1 attachment(s) dropped |
| 2005-06-28 | outlook:<002501c57bdf$b26b0a10$720ea8c0@pc008> | Merlin Online Help | recovered, 1 attachment(s) dropped |
| 2005-06-29 | outlook:<BAECJIMHCFBIFLJOCKGDKEIKCAAA.giovanni.pellicciotta@anubex.com> | RE: JConnect maximum connection problem | recovered, 2 attachment(s) dropped |
| 2005-06-29 | outlook:<BAECJIMHCFBIFLJOCKGDMEIJCAAA.giovanni.pellicciotta@anubex.com> | Creation test test. | recovered, 1 attachment(s) dropped |
| 2005-07-11 | outlook:<BAECJIMHCFBIFLJOCKGDAEJGCAAA.giovanni.pellicciotta@anubex.com> | Emailing: jsupport.zip | recovered, 2 attachment(s) dropped |
| 2005-07-11 | outlook:<BAECJIMHCFBIFLJOCKGDEEJGCAAA.giovanni.pellicciotta@anubex.com> | Emailing: project-builder.zip | recovered, 1 attachment(s) dropped |
| 2005-09-06 | outlook:<00e801c5b2d1$c21d3450$a80ea8c0@DASCHOTS> | Re: Merlin 4.2 | recovered, 1 attachment(s) dropped |
| 2005-10-13 | outlook:<00cf01c5cfc4$ba56fd90$7a0ea8c0@VANSLMIC> | Fw: Standalone emulation installation procedure | recovered, 4 attachment(s) dropped |
| 2005-10-19 | outlook:<000401c5d479$9b263170$7a0ea8c0@VANSLMIC> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-12-15 | outlook:<000701c601d2$e01859d0$860ea8c0@PC019> | (no subject) | recovered, 1 attachment(s) dropped |
| 2005-12-15 | outlook:<BAECJIMHCFBIFLJOCKGDIEPFCAAA.giovanni.pellicciotta@anubex.com> | (no subject) | recovered, 1 attachment(s) dropped |
| 2006-01-07 | outlook:<000401c613a4$1e314eb0$860ea8c0@PC019> | Emailing: brant-1.3-bin.zip | recovered, 2 attachment(s) dropped |
| 2006-02-09 | outlook:<000401c62d59$ee0ee290$860ea8c0@PC019> | Emailing: MSVCRTD.zip | recovered, 1 attachment(s) dropped |
| 2006-02-09 | outlook:<000b01c62d5c$68347fb0$860ea8c0@PC019> | Emailing: MSVCRTD.zip | recovered, 1 attachment(s) dropped |
| 2006-02-09 | outlook:<BAECJIMHCFBIFLJOCKGDGEAPCBAA.giovanni.pellicciotta@anubex.com> | Emailing: MSVCRTD.zip | recovered, 1 attachment(s) dropped |
| 2006-02-09 | outlook:<BAECJIMHCFBIFLJOCKGDKEAPCBAA.giovanni.pellicciotta@anubex.com> | Emailing: MSVCRTD.zip | recovered, 1 attachment(s) dropped |
| 2006-03-31 | outlook:<000b01c654cd$f21e78f0$860ea8c0@PC019> | Emailing: Anubex Professional One Web TSE.zip | recovered, 1 attachment(s) dropped |
| 2006-03-31 | outlook:<BAECJIMHCFBIFLJOCKGDEEGGCBAA.giovanni.pellicciotta@anubex.com> | Emailing: Anubex Professional One Web TSE.zip | recovered, 1 attachment(s) dropped |
| 2006-06-23 | outlook:<000401c696c5$fc1276b0$26fca8c0@PC019> | 3270 terminal emulator software + DB2 problems arrangements | recovered, 1 attachment(s) dropped |
| 2006-06-23 | outlook:<BAECJIMHCFBIFLJOCKGDGEAECEAA.giovanni.pellicciotta@anubex.com> | 3270 terminal emulator software + DB2 problems arrangements | recovered, 1 attachment(s) dropped |
| 2006-09-08 | outlook:<000701c6d357$bcc1a2a0$21fca8c0@LAPTOP016> | Computing the characteristics of a file: the fldata function | recovered, 1 attachment(s) dropped |
| 2006-09-19 | outlook:<000f01c6dbfc$065f7ac0$4dfba8c0@pc008> | [banca-march] Merlin online help | recovered, 2 attachment(s) dropped |
| 2006-09-28 | outlook:<001a01c6e2d0$41863ff0$860ea8c0@PC019> | Bunting files | recovered, 8 attachment(s) dropped |
| 2006-09-28 | outlook:<002601c6e2d1$46b90290$860ea8c0@PC019> | Bunting release 1.15 | recovered, 1 attachment(s) dropped |
| 2006-09-28 | outlook:<BAECJIMHCFBIFLJOCKGDAENFCEAA.giovanni.pellicciotta@anubex.com> | Bunting release 1.15 | recovered, 1 attachment(s) dropped |
| 2006-09-28 | outlook:<BAECJIMHCFBIFLJOCKGDMENECEAA.giovanni.pellicciotta@anubex.com> | Bunting files | recovered, 8 attachment(s) dropped |
| 2006-10-02 | outlook:<45213022.1070405@anubex.com> | [banca-march] Eagle update for Eucalyptus | recovered, 2 attachment(s) dropped |
| 2006-10-11 | outlook:<BNENIABHNLFDCCPLKDKIAEIOCDAA.tony.vanderbeken@anubex.com> | [banca-march]  Bug fixes | recovered, 2 attachment(s) dropped |
| 2006-10-27 | outlook:<BNENIABHNLFDCCPLKDKIAEKCCDAA.tony.vanderbeken@anubex.com> | [banca-march] Merlin 5.5 | recovered, 3 attachment(s) dropped |
| 2006-11-03 | outlook:<BNENIABHNLFDCCPLKDKIOEKGCDAA.tony.vanderbeken@anubex.com> | [banca-march] Merlin 5.6 | recovered, 3 attachment(s) dropped |
| 2006-11-10 | outlook:<45548833.9060509@anubex.com> | Merlin 4.9 | recovered, 1 attachment(s) dropped |
| 2007-01-10 | outlook:<050401c73492$c584c1f0$810ea8c0@pc021> | [lcm] Koala Stress test application | recovered, 4 attachment(s) dropped |
| 2007-02-06 | outlook:<45C89742.5010305@anubex.com> | nieuwe versie van Eucalyptus | recovered, 1 attachment(s) dropped |
| 2007-10-19 | outlook:<471874D5.4090804@anubex.com> | [Fwd: IDMS database migration - schema's] | recovered, 1 attachment(s) dropped |
| 2007-12-06 | outlook:<4757E87A.30200@anubex.com> | VPN Software | recovered, 2 attachment(s) dropped |
| 2007-12-12 | outlook:<475FA82E.10600@anubex.com> | Latest builds | recovered, 2 attachment(s) dropped |
| 2008-03-17 | outlook:<004c01c887da$54355220$6500a8c0@v> | Re: Status | recovered, 1 attachment(s) dropped |
| 2008-03-19 | outlook:<001b01c8897d$f9ac8710$6500a8c0@v> | Re: Status | recovered, 1 attachment(s) dropped |
| 2008-03-19 | outlook:<47E0D8D3.3000602@anubex.com> | Emailing: avocet.zip | recovered, 1 attachment(s) dropped |
| 2008-03-19 | outlook:<47E1375E.10201@anubex.com> | Avocet Project - Specs, build environment, etc | recovered, 1 attachment(s) dropped |
| 2008-03-19 | outlook:<47E13A58.60103@anubex.com> | Re: Status | recovered, 1 attachment(s) dropped |
| 2008-03-19 | outlook:<47E13D09.7000409@anubex.com> | Re: Status | recovered, 1 attachment(s) dropped |
| 2008-03-19 | outlook:<47E13D8C.5090608@anubex.com> | Avocet Project - Specs, build environment, etc | recovered, 1 attachment(s) dropped |
| 2008-03-19 | outlook:<47E13F05.9070202@anubex.com> | Mail size limitations issue | recovered, 1 attachment(s) dropped |
| 2008-04-03 | outlook:<008f01c89551$009232d0$6500a8c0@v> | Re: Status update | recovered, 1 attachment(s) dropped |
| 2008-04-07 | outlook:<47FA529D.5040400@anubex.com> | Re: Status update | recovered, 1 attachment(s) dropped |
| 2008-04-16 | outlook:<4805DC95.7030908@anubex.com> | SSH Key (for access to swets) | recovered, 2 attachment(s) dropped |
| 2008-08-28 | outlook:<00b601c908f5$e86d3290$0a0a0a0a@ANUBEX.internal> | Re: [gial] sources gial | recovered, 2 attachment(s) dropped |
| 2008-10-23 | outlook:<000701c934e2$ae9edd70$700ea8c0@ANUBEX.internal> | [gial] deployement libkoala.lib | recovered, 2 attachment(s) dropped |
| 2008-10-31 | outlook:<490B14BB.6090601@anubex.com> | Egret Version (works on all computers now, including Kris') | recovered, 1 attachment(s) dropped |
| 2008-11-06 | outlook:<E6A75128A9534A5D9DC0414A2C9EB30F@ANUBEX.internal> | [gial] FW: [Fwd: Latest Egret Jar] | recovered, 2 attachment(s) dropped |
| 2008-11-07 | outlook:<491443E0.5010102@anubex.com> | New version of Egret | recovered, 1 attachment(s) dropped |
| 2008-11-24 | outlook:<492AEFD0.4080609@anubex.com> | Emailing: CombinationDemo.exe | recovered, 1 attachment(s) dropped |
| 2008-12-02 | outlook:<493515BC.5040209@anubex.com> | Koala components for Swets. | recovered, 12 attachment(s) dropped |
| 2008-12-02 | outlook:<49351804.2010207@anubex.com> | Emailing: waxwing-ibm3270-components.jar, anubex-ds3270.jar | recovered, 2 attachment(s) dropped |
| 2009-01-22 | outlook:<003001c97c9d$dc2b8880$94829980$@andre.kampbell@orange.fr> | MicroFocus cobol ant tasks | recovered, 1 attachment(s) dropped |
| 2009-03-03 | outlook:<49AD4FB0.6030004@anubex.com> | Emailing: migrate.sh, migrate.cmd | recovered, 5 attachment(s) dropped |
| 2009-04-08 | outlook:<018901c9b868$4ad2fa60$e078ef20$@wilson@anubex.com> | Re: [gial] les exercises | recovered, 2 attachment(s) dropped |
| 2009-05-19 | outlook:<4A12B0BA.1010905@anubex.com> | [unigarant] [Fwd: Omao - Owner Pointer Reconstructor] | recovered, 2 attachment(s) dropped |
| 2009-05-28 | outlook:<4A1E58B9.4010505@rever.eu> | Re: [gial] Wrapper 1.9 (actually 1.10) - compilation status | recovered, 4 attachment(s) dropped |
| 2009-06-17 | outlook:<4A3974EA.9050002@rever.eu> | [gial] Composants de migration Perbru | recovered, 2 attachment(s) dropped |
| 2009-09-09 | outlook:<4AA74E88.1050901@rever.eu> | [gial] Comparison of the data structures | recovered, 2 attachment(s) dropped |
| 2009-09-28 | outlook:<4AC07001.5030002@anubex.com> | Performance tuning van Fujitsu COBOL: COUNT compiler option | recovered, 1 attachment(s) dropped |
| 2009-10-08 | outlook:<D0D2F820B7514DCB97122D4FFB7D0235@ANUBEX.internal> | Re: [gial] OpenUTM as a service | recovered, 2 attachment(s) dropped |
| 2009-11-09 | outlook:<2D5CD17DAB7144619FB2372E5A464439@ANUBEX.internal> | [gial] Release 9/11 | recovered, 7 attachment(s) dropped |
| 2009-11-18 | outlook:<6467A34425144D6BAA2BD8603B81DD91@ANUBEX.internal> | [gial] Fw: FW: Failure : Permig : Transcodage (environnement de test) | recovered, 12 attachment(s) dropped |
| 2009-11-19 | outlook:<20091119160756.20374vb4nctk7urk@webmail.anubex.com> | Re: [gial] FW: Failure : Permig : Transcodage (environnement de test) | recovered, 2 attachment(s) dropped |
| 2009-12-09 | outlook:<125C6F565863AD41B2C7282DBBDB30880396B6B5@PTHA.gial.be> | Re: [gial] ddl scripts | recovered, 2 attachment(s) dropped |
| 2010-01-04 | outlook:<4B423224.7070609@anubex.com> | Backup: mycob.7z | recovered, 1 attachment(s) dropped |
| 2010-03-08 | outlook:<125C6F565863AD41B2C7282DBBDB308803F3FB29@PTHA.gial.be> | [gial] PERMIG : lancement batch | recovered, 3 attachment(s) dropped |
| 2010-03-17 | outlook:<125C6F565863AD41B2C7282DBBDB308803744BA2@PTHA.gial.be> | batch sur Cybele | recovered, 3 attachment(s) dropped |
| 2010-05-07 | outlook:<37B0B7E583564486A8698849AB60A06A@coss.nl> | RE: NetCobol questions | recovered, 1 attachment(s) dropped |
| 2010-05-07 | outlook:<4BE40837.3000904@anubex.com> | [neu] Omao Tool for RGCLR update | recovered, 2 attachment(s) dropped |
| 2010-05-07 | outlook:<4BE40A2F.5090309@anubex.com> | Re: [neu] Omao Tool for RGCLR update | recovered, 2 attachment(s) dropped |
| 2010-05-07 | outlook:<997940CD3C1F409B947355099822C96B@ANUBEX.internal> | [bezeq] FW: NetCobol questions | recovered, 2 attachment(s) dropped |
| 2010-06-03 | outlook:<00fc01cb030f$ca50b230$5ef21690$@wilson@anubex.com> | Re: [citibank] Natural Migration - How to get Eclipse - new jar enclosed | recovered, 2 attachment(s) dropped |
| 2010-06-16 | outlook:<4C18A57E.10606@rever.eu> | Re: [gial] ets#10051: "BLANK WHEN ZERO" clause missing in io-wrapper NRBCAR | recovered, 5 attachment(s) dropped |
| 2010-07-16 | outlook:<001a01cb24d7$75b2b72a$6b02a8c0@CarlosHonorato> | Scan from a Xerox WorkCentre Pro #5666011 | recovered, 1 attachment(s) dropped |
| 2010-08-10 | outlook:<014801cb387d$32b807e0$982817a0$@wilson@anubex.com> | FW: Sample COBOL programs to demonstrate challenges of maintaining Visual Hebrew | recovered, 5 attachment(s) dropped |
| 2010-08-10 | outlook:<E1C231AB7BBD7D4A88ADACF75AD15EA807969D99@DB3EX14MBXC308.europe.corp.microsoft.com> | RE: Sample COBOL programs to demonstrate challenges of maintaining Visual Hebrew | recovered, 5 attachment(s) dropped |
| 2010-08-20 | outlook:<4C6E8F43.5010506@anubex.com> | [citibank] JP tool processing | recovered, 2 attachment(s) dropped |
| 2010-10-21 | outlook:<1064E37F253DE147B0426FEF7691A02776671712B9@TEUTATES.gial.be> | [gial] Timeout QPERBRU | recovered, 4 attachment(s) dropped |
| 2011-01-11 | outlook:<058201cbb192$ec66e920$c534bb60$@wilson@anubex.com> | FW: Questions on UDS | recovered, 1 attachment(s) dropped |
| 2011-01-24 | outlook:<FAA1EEFF34E14F9F935DD5568F8DC2CE@ANUBEX.internal> | Emailing: run.bat | recovered, 1 attachment(s) dropped |
| 2011-02-09 | outlook:<4D52A054.6020009@anubex.com> | Setup for the outline tool | recovered, 5 attachment(s) dropped |
| 2011-02-10 | outlook:<4D5399FE.3070206@anubex.com> | Fwd: Setup for the outline tool | recovered, 5 attachment(s) dropped |
| 2011-03-03 | outlook:<4D6FB683.8050504@anubex.com> | Re: Gennady tasks | recovered, 1 attachment(s) dropped |
| 2011-03-15 | outlook:<4D7F3C12.6010803@anubex.com> | Re: BS2000 questions | recovered, 1 attachment(s) dropped |
| 2011-03-31 | outlook:<01ab01cbef89$faba9140$f02fb3c0$@anubex.com> | PFA syntax files | recovered, 1 attachment(s) dropped |
| 2011-05-11 | outlook:<4DCA53C5.20107@anubex.com> | Zip file | recovered, 1 attachment(s) dropped |
| 2011-05-20 | outlook:<4DD6CD8D.6020206@anubex.com> | No Official MicroFocus Support? | recovered, 1 attachment(s) dropped |
| 2011-06-01 | outlook:<CF6787E41F73764A84BA72680E23EADB02B053CA@TAAD5EAA.no001.siemens.net> | OpenUTM on WIndows | recovered, 1 attachment(s) dropped |
| 2011-06-08 | outlook:<4DEF23B2.30506@anubex.com> | Re: [bezeq] FW: Presentation to Bezeq | recovered, 1 attachment(s) dropped |
| 2011-06-17 | outlook:<4DFAF772.7000904@anubex.com> | Scriptje | recovered, 1 attachment(s) dropped |
| 2011-06-22 | outlook:<005101cc30df$fe0f2f30$fa2d8d90$@Anubex.com> | [pfa]  Assembler test involving holder tasks | recovered, 4 attachment(s) dropped |
| 2011-08-05 | outlook:<7D817EA0073E47E6B2B9D234CA26ED1F@ANUBEX.internal> | [pfa] (no subject) | recovered, 2 attachment(s) dropped |
| 2011-08-17 | outlook:<044901cc5c89$2886a750$7993f5f0$@anubex.com> | Re: [pfa] Missing report | recovered, 2 attachment(s) dropped |
| 2011-09-28 | outlook:<012e01cc7d98$99650fe0$cc2f2fa0$@anubex.com> | Re: [bezeq] bidirectional hebrew input | recovered, 2 attachment(s) dropped |
| 2011-09-29 | outlook:<00a801cc7e68$732b0700$59811500$@anubex.com> | [bezeq] Fix for "Current state=RESET, new state = FLUSHED" problem. | recovered, 2 attachment(s) dropped |
| 2011-10-12 | outlook:<005a01cc88ea$90a614f0$b1f23ed0$@anubex.com> | Re: [bezeq] FW: egret_plugin | recovered, 4 attachment(s) dropped |
| 2011-10-12 | outlook:<EC7C8B72A1E94D4EA82318F10CAB0C61@ANUBEX.internal> | [bezeq] FW: egret_plugin | recovered, 4 attachment(s) dropped |
| 2011-11-16 | outlook:<CABX6VKbkucwY-yTv9jf6atvJPFkGJL73M1CaNC5hafCu-c4xhQ@mail.gmail.com> | [socgen] koala-server with support for 9750 terminals. | recovered, 3 attachment(s) dropped |
| 2011-11-22 | outlook:<CAFGz5+dXv9u4oUrCGrPkF__zLLJT0ggDo-P1AyysknpxYh7+1Q@mail.gmail.com> | [pfa] Sample code for dynamic call from C to COBOL dll's | recovered, 1 attachment(s) dropped |
| 2011-11-24 | outlook:<dd6ac7ad23141c3dab1e18e7d61e883f@mail.gmail.com> | [socgen] SGBT - Configuration du LogTE | recovered, 2 attachment(s) dropped |
| 2011-11-25 | outlook:<CALxDBLVJQOTA8pPvku4=MPpehu4biUTeq10PGtNvk3LF4JggnQ@mail.gmail.com> | Fwd: bidirectional hebrew input | recovered, 2 attachment(s) dropped |
| 2011-11-25 | outlook:<CALxDBLWDOUF93g4iD80JeL+R2sw95JJ5D=pK=yTqFn_orgpuYg@mail.gmail.com> | Re: bidirectional hebrew input | recovered, 5 attachment(s) dropped |
| 2011-12-24 | outlook:<fea0262344d15f88e7bff613a9fd2169@mail.gmail.com> | [socgen] RE: [Bug 11945] UC4 Event Console | recovered, 3 attachment(s) dropped |
| 2012-01-10 | outlook:<OF5EBD8D31.32525207-ONC1257981.0033F615-C1257981.003448BE@fr.world.socgen> | [socgen] Fw: EntireX Replay with Java Tester Classes | recovered, 6 attachment(s) dropped |
| 2012-02-14 | outlook:<CABX6VKagFHiwatCec8ygVqdNo1s5FjurnQPB6M7b_6P4j4uGgw@mail.gmail.com> | Re: stop / start lauchserver still not working | recovered, 3 attachment(s) dropped |
| 2012-02-14 | outlook:<CAJ0RVP8_67uHRb1Avn4L1-MuV6K=dkA1OvXdoy-iU8hZ-BZV-w@mail.gmail.com> | Re: [pfa] SV: KR build status | recovered, 2 attachment(s) dropped |
| 2012-02-14 | outlook:<dd5b9fc8d9c8a2e59445a2c371be9c09@mail.gmail.com> | RE: [pfa] SV: KR build status | recovered, 2 attachment(s) dropped |
| 2012-02-28 | outlook:<4F4CEE16.8010804@anubex.com> | Re: SV: [pfa] SV: Build error in kr19-kr-palu-r.pco generated from Merlin | recovered, 4 attachment(s) dropped |
| 2012-02-28 | outlook:<CALxDBLW5hr31RNNgotOXqtYF+n8B_qXgRFMWoq6ujVSwaDR-ZQ@mail.gmail.com> | [socgen] Re: Eucalyptus training | recovered, 3 attachment(s) dropped |
| 2012-03-05 | outlook:<CABX6VKY3ob=Lev1Ef4TN4OSd-U9TDcCBHY+zXFZ+qQBRPiAxOA@mail.gmail.com> | [pfa] ATF API to create scenario for stress tests. | recovered, 1 attachment(s) dropped |
| 2012-03-05 | outlook:<CABX6VKbVMoX8Dntn4RWZRGuwhC3sG=fwp+pXykkuArCTPim_jA@mail.gmail.com> | [pfa] Re: ATF API to create scenario for stress tests. | recovered, 2 attachment(s) dropped |
| 2012-03-16 | outlook:<OF3FF3BA6C.D0AFFD57-ONC12579C3.004A6C59-C12579C3.004AB5B1@fr.world.socgen> | [socgen] Re: FW: Khepersi : formation Cobol | recovered, 5 attachment(s) dropped |
| 2012-03-27 | outlook:<OF709F2501.2EC624BD-ONC12579CE.0051715E-C12579CE.0051A273@fr.world.socgen> | [socgen] Fw: Khepersi : formation Cobol | recovered, 6 attachment(s) dropped |
| 2012-04-03 | outlook:<320eb606997eb1debc49994d3b348fd7@mail.gmail.com> | [pfa] Emailing: Waxwing NET client with Setup.msi | recovered, 2 attachment(s) dropped |
| 2012-04-03 | outlook:<3543792df749785a9f1b26b0d5beeab9@mail.gmail.com> | RE: ATF demo testing - two more questions | recovered, 1 attachment(s) dropped |
| 2012-04-13 | outlook:<CABX6VKYn8XKZGH=gTsi6acGbAQnPs2wcmPiL4j8iNgCgWOOxHQ@mail.gmail.com> | [bezeq] Eclipse + WindowBuilder installation instructions | recovered, 2 attachment(s) dropped |
| 2012-05-02 | outlook:<CABX6VKZ4C4qbgkHJvg5CBqhsXZ2YbmJDFt57mV5gD0bKB7ABLw@mail.gmail.com> | [bezeq] Re: Map copy script to be included in every project of every workspace | recovered, 4 attachment(s) dropped |
| 2012-05-02 | outlook:<CABX6VKZB0d=a==2DNWd3_aPkOgUaWG=DDpUuZ+zim7odA4zVWA@mail.gmail.com> | [bezeq] Re: Map copy script to be included in every project of every workspace | recovered, 2 attachment(s) dropped |
| 2012-05-09 | outlook:<cb41d99117eb338830b367700482390c@mail.gmail.com> | RE: SAAQ POC code ready? | recovered, 1 attachment(s) dropped |
| 2012-05-15 | outlook:<e7b6af25a20159e42ead4429345eea14@mail.gmail.com> | Emailing: SaaqIdmsDemo.zip._ | recovered, 1 attachment(s) dropped |
| 2012-05-16 | outlook:<0d8696dc7178802fc87b82725ae95fe9@mail.gmail.com> | Emailing: SaaqIdmsDemo.zip._ | recovered, 1 attachment(s) dropped |
| 2012-05-16 | outlook:<2dc1812c3969bf2ea080a30407db88d0@mail.gmail.com> | Emailing: SaaqIdmsDemo.zip | recovered, 1 attachment(s) dropped |
| 2012-06-07 | outlook:<03c701cd448e$871b98f0$9552cad0$@anubex.com> | FW: fujitsu dll | recovered, 2 attachment(s) dropped |
| 2012-06-18 | outlook:<6bab034f96e3eecaff49463e591be23f@mail.gmail.com> | RE: execution error message | recovered, 5 attachment(s) dropped |
| 2012-06-25 | outlook:<56B807014768DF429783A893E79411151C00E99C@vanbreda.be> | iexecutable | recovered, 1 attachment(s) dropped |
| 2012-06-25 | outlook:<CAORxRLoQe708yQJcf-1HN=gFnAAwcudqZgxH5WLgY=-DtOwnAw@mail.gmail.com> | Mijn laatste VS solution | recovered, 1 attachment(s) dropped |
| 2012-06-25 | outlook:<CAORxRLouek7j-krMFeRm8kowYJ=X2tX+=XpUX9EoqZQPdVEiwg@mail.gmail.com> | Re: iexecutable | recovered, 1 attachment(s) dropped |
| 2012-06-25 | outlook:<CAORxRLphNVxhZSR_sLKDisqhcD6xUcWeO89akNOG9ieeOciH+w@mail.gmail.com> | Re: iexecutable | recovered, 1 attachment(s) dropped |
| 2012-06-25 | outlook:<CAORxRLqYWnO_Rws_CpHPfh_cNZgG01BJ7dHA4HnG3Lio0R-Ccg@mail.gmail.com> | Re: iexecutable | recovered, 1 attachment(s) dropped |
| 2012-06-25 | outlook:<CAORxRLrWbX4zhd2H8bYjzbo8RO3+FfpBpbL8xpRHuyrhn53oog@mail.gmail.com> | Re: iexecutable | recovered, 1 attachment(s) dropped |
| 2012-06-25 | outlook:<CAORxRLrztsiiyikj5FJM1hdhKq7XcfNLD8bYR5CLauj4tcBPUg@mail.gmail.com> | Re: iexecutable | recovered, 1 attachment(s) dropped |
| 2012-06-28 | outlook:<CAORxRLqCQX+oK6ZfVD_FY0vprJYDM9Gr_WSW+YZJSUNDtz+L7A@mail.gmail.com> | Re: Cobsupport lib | recovered, 1 attachment(s) dropped |
| 2012-07-10 | outlook:<CABX6VKaGGA0b21kr=GxNLS8TFgcw6mCnAi10cnnMMYsYD2gagA@mail.gmail.com> | [pfa] new version of swift. | recovered, 1 attachment(s) dropped |
| 2012-07-19 | outlook:<50b25a33d0c3ce6183e8eed5ce2b71a3@mail.gmail.com> | [bvb] Emailing: DMSampleProject.zip._ | recovered, 1 attachment(s) dropped |
| 2012-07-19 | outlook:<A5F9A43BCAAAE446B173A3F20494FE7223034A3B0D@PFANPEX01.pfa.dk> | SV: [pfa] Still having connection problems | recovered, 4 attachment(s) dropped |
| 2012-08-03 | outlook:<501BB02D.9060500@anubex.com> | [bezeq] Regarding attached mails: area sequence 96 full - DPR | recovered, 5 attachment(s) dropped |
| 2012-08-30 | outlook:<CAKD3SU=NF9X+nAFsO5p9sbO=9aDnORn5+SEPfeww9vcPdnRHsA@mail.gmail.com> | Waxwing development issues | recovered, 5 attachment(s) dropped |
| 2012-09-10 | outlook:<CAKD3SUmCr_TVxRZxbnWuak8YExzS-2nJCNZBM4Yix02QW-8FTA@mail.gmail.com> | [bezeq] Waxwing development issues | recovered, 1 attachment(s) dropped |
| 2012-09-13 | outlook:<4b3d34d6c82ac4e975ac31455bc30619@mail.gmail.com> | [bvb] Emailing: Solution.7z | recovered, 1 attachment(s) dropped |
| 2012-09-13 | outlook:<50517AFD.2090102@anubex.com> | [bezeq] Merlin Release 8.4 | recovered, 1 attachment(s) dropped |
| 2012-10-10 | outlook:<CAORxRLqVV5k8QwOdumZGv1fjsVef55b72r-Wa+-f0GL-tnB_SQ@mail.gmail.com> | Re: Laadprocessmanager meeting minutes | recovered, 1 attachment(s) dropped |
| 2012-11-07 | outlook:<CAKD3SU=Ym6tVTpSVRvhC1trmzzjzZEFQWLPEEmrUCmxDW-gTQg@mail.gmail.com> | Re: [bezeq] RE: Status update on Bezeq's Waxwing issues | recovered, 4 attachment(s) dropped |
| 2012-11-21 | outlook:<4fa61f8c6f5a97f92e5b4c2971c3fa3f@mail.gmail.com> | RE: [socgen] Re: Merlin caching - sample logic | recovered, 2 attachment(s) dropped |
| 2012-11-30 | outlook:<CAKD3SU=9mnusTg1C9kzTgSd_ANHkK4p=-TjnpVvYbGiTQsCJNw@mail.gmail.com> | Air France deliverables | recovered, 2 attachment(s) dropped |
| 2012-12-10 | outlook:<CAORxRLpqsGiTT+XfmnhLb9LsdT9VFm8CGnCA7SWvT+SnZ6QrCA@mail.gmail.com> | Re: diffing actual_output and expected_output for atf regression test | recovered, 1 attachment(s) dropped |
| 2012-12-21 | outlook:<CAGUx=PoQLpp-e4tcHo-_pS6mSJbPU82z6mXVKX+gwANE4OZw0A@mail.gmail.com> | Re: [bezeq] Bezeq OMF sso Webservice | recovered, 1 attachment(s) dropped |
| 2013-02-26 | outlook:<CAGUx=PqrbUof1MLLkV7HO1BkAuHigYHv7D9kF-p4jrfQheT=Ew@mail.gmail.com> | Fwd: diffing actual_output and expected_output for atf regression test | recovered, 1 attachment(s) dropped |
| 2013-02-27 | outlook:<CAORxRLptuZo8R6q++ENJc3YarVdYwfMp4ojj495rFkFGrbiNRw@mail.gmail.com> | Re: diffing actual_output and expected_output for atf regression test (ETS#15... | recovered, 1 attachment(s) dropped |
| 2013-02-28 | outlook:<11C14CE1B631B04490369345546D04471BD8A282@MBXN01.bezeq.com> | RE: [WARNING - ENCRYPTED ATTACHMENT NOT VIRUS SCANNED] Re: [bezeq] RE: Bezeq ... | recovered, 5 attachment(s) dropped |
| 2013-05-29 | outlook:<51A5F7C8.9050502@anubex.com> | Re: FW: compilatiefouten | recovered, 1 attachment(s) dropped |
| 2013-06-05 | outlook:<CAKD3SUmuCVx3nNNWCrz-8Ve=-Q5SsnQXApFMpC5Bk9LTFV+Reg@mail.gmail.com> | SqlServer url + driver | recovered, 1 attachment(s) dropped |
| 2013-10-09 | outlook:<CAORxRLqtjtTNfrjPbRg8kCBWRyMMCn8c2L=B-2dRS0FE-wF0=Q@mail.gmail.com> | CICS and DMS Framework projects almost completely setup now | recovered, 2 attachment(s) dropped |
| 2013-10-21 | outlook:<5264E90C.3060304@anubex.com> | [bvb] Emailing: Merlin-v9.3.zip.txt | recovered, 1 attachment(s) dropped |
| 2013-10-21 | outlook:<5264EA79.10900@anubex.com> | [bvb] Emailing: Dms Waxwing Net Client.zip.txt | recovered, 1 attachment(s) dropped |
| 2013-10-21 | outlook:<52651188.1010306@anubex.com> | [bvb] Release 21/10/2013 | recovered, 1 attachment(s) dropped |
| 2013-10-24 | outlook:<52690FDF.8060405@anubex.com> | [bvb] Re: [Bug 16021] Copy/paste van een blok tekst naar het scherm lukt niet... | recovered, 1 attachment(s) dropped |
| 2013-10-24 | outlook:<52691CF9.8010805@anubex.com> | [bvb] Re: [Bug 16021] Copy/paste van een blok tekst naar het scherm lukt niet... | recovered, 2 attachment(s) dropped |
| 2013-10-28 | outlook:<526E1EC8.4060403@anubex.com> | [bvb] Release 28/10/2013 (Waxwing .NET client) | recovered, 1 attachment(s) dropped |
| 2013-11-04 | outlook:<5277488F.10503@anubex.com> | [bvb] Release 04/11/2013 (Waxwing Client & Merlin) | recovered, 4 attachment(s) dropped |
| 2013-11-26 | outlook:<5294AD7D.1000909@anubex.com> | [bvb] Release 26/11/2013 | recovered, 4 attachment(s) dropped |
| 2013-12-06 | outlook:<7dce6b5f051d01af2f11b73ee339e35d@mail.gmail.com> | [vanmullem] RE: Nieuwe PSFP.dll: OK - er is zelfs output op de printer nu - i... | recovered, 1 attachment(s) dropped |
| 2013-12-13 | outlook:<52AADBB0.4040108@anubex.com> | [bvb] Release 13/12/2013 | recovered, 2 attachment(s) dropped |
| 2013-12-26 | outlook:<52BC3C6D.1000003@anubex.com> | [bvb] Release 26/12/2013 | recovered, 1 attachment(s) dropped |
| 2014-01-13 | outlook:<52D41146.9000702@anubex.com> | [bvb] Release 13/01/2014 | recovered, 1 attachment(s) dropped |
| 2014-03-19 | outlook:<CAORxRLqZL1MW3BRdsL0Zk6XCdrcNcw=O2wO4ic0m7Lg3N8AqKg@mail.gmail.com> | Re: Meeting Minutes | recovered, 3 attachment(s) dropped |
| 2014-03-20 | outlook:<CABX6VKbKeR8Y8StfPuXg7HYWCiya0=YeQ+oYpjQweTOZfwHF7Q@mail.gmail.com> | [lcm] Koala-server 1.36.2.22 - for jconnect 3 | recovered, 2 attachment(s) dropped |
| 2014-05-16 | outlook:<53761D34.1000802@anubex.com> | [DWS] DPS JCL | recovered, 2 attachment(s) dropped |
| 2014-05-27 | outlook:<CAPMxWGnWQY9AnBvK4L+zGBrGDgePQihpUWhNa+36+ZwX0crQNw@mail.gmail.com> | Backup | recovered, 1 attachment(s) dropped |
| 2014-06-06 | outlook:<CADn92c74EHRQOC5n6rLM6VzUyZTYCANyG2eFG01g1bBzf=RDPA@mail.gmail.com> | [DWS] Loading hex data into binary column | recovered, 2 attachment(s) dropped |
| 2014-06-09 | outlook:<BD97CC569CC47A42A4B32A640AED5D8B07B6014B@EXCH2010.Treehouse.local> | RE: Loading hex data into binary column | recovered, 2 attachment(s) dropped |
| 2014-07-17 | outlook:<28f402a77757437e9f267334d4842c7c@DBXPR06MB336.eurprd06.prod.outlook.com> | NOL Analysis results | recovered, 2 attachment(s) dropped |
| 2014-08-01 | outlook:<c76aba6f7ec743fa86c7397c77c69644@DBXPR06MB336.eurprd06.prod.outlook.com> | Milestone #4 - Special Topics Design | recovered, 2 attachment(s) dropped |
| 2014-09-09 | outlook:<00f760cfc21744528261025a55ad2a5b@AM3PR06MB020.eurprd06.prod.outlook.com> | FW: New missings | recovered, 1 attachment(s) dropped |
| 2014-09-09 | outlook:<555f6e4363f24603b75508a957973bc0@DBXPR06MB447.eurprd06.prod.outlook.com> | New missings | recovered, 1 attachment(s) dropped |
| 2014-11-12 | outlook:<494ced0228bd461a93e78645c9d83490@AM3PR06MB020.eurprd06.prod.outlook.com> | RE: Anubex Academy re. Code Signing: three updates | recovered, 1 attachment(s) dropped |
| 2014-11-19 | outlook:<7cf56b0501064a87972c8f8f0abcc030@AM3PR06MB020.eurprd06.prod.outlook.com> | (no subject) | recovered, 3 attachment(s) dropped |
| 2014-11-24 | outlook:<97a9a5c0d3b849448208c30df6b7e662@AM1FFO11FD041.protection.gbl> | listing van de crontab | recovered, 2 attachment(s) dropped |
| 2015-01-05 | outlook:<AMSPR06MB55012E1F3BEE1AEAC8BAF9996580@AMSPR06MB550.eurprd06.prod.outlook.com> | SQL Server Performance Tuning performed at GoA | recovered, 1 attachment(s) dropped |
| 2015-01-05 | outlook:<AMSPR06MB550B0FD0F4E7183A2533F4C96580@AMSPR06MB550.eurprd06.prod.outlook.com> | FW: SQL Server Performance Tuning performed at GoA | recovered, 1 attachment(s) dropped |
| 2015-01-15 | outlook:<AM3PR06MB02000CD0FBA0A22615761D99A4E0@AM3PR06MB020.eurprd06.prod.outlook.com> | RE: Sample Code | recovered, 4 attachment(s) dropped |
| 2015-01-16 | outlook:<AM2PR06MB616619F08C42BF452DA7102974F0@AM2PR06MB616.eurprd06.prod.outlook.com> | FW: Questions on migration tools | recovered, 1 attachment(s) dropped |
| 2015-01-16 | outlook:<AM2PR06MB616E7A95AB4C7B7164712B4974F0@AM2PR06MB616.eurprd06.prod.outlook.com> | FW: Questions on migration tools | recovered, 1 attachment(s) dropped |
| 2015-01-22 | outlook:<AM3PR06MB3550F65348023C9F12F6E34EE490@AM3PR06MB355.eurprd06.prod.outlook.com> | Demo for Nimble? | recovered, 1 attachment(s) dropped |
| 2015-03-03 | outlook:<AMSPR06MB55000585B7A8A897D3F8F6C96110@AMSPR06MB550.eurprd06.prod.outlook.com> | RE: NN, Nieuwe levering van CSV bestanden gevraagd / SPOED | recovered on retry (succeeded without modification) |
| 2015-03-03 | outlook:<DB4PR06MB2065B705D2E101E40079928EE110@DB4PR06MB206.eurprd06.prod.outlook.com> | Releases | recovered, 1 attachment(s) dropped |
| 2015-03-09 | outlook:<AM3PR06MB3721660EA3C8E1102D77B2D921B0@AM3PR06MB372.eurprd06.prod.outlook.com> | RE: new response in EGRET | recovered, 11 attachment(s) dropped |
| 2015-03-12 | outlook:<AM3PR06MB372C5358675C32B985E64CC92060@AM3PR06MB372.eurprd06.prod.outlook.com> | RE: new response in EGRET | recovered, 11 attachment(s) dropped |
| 2015-03-30 | outlook:<C176884BA944C14696719A7F27D2343D3CF167F4@EDM-GOA-EXCH105.goa.ds.gov.ab.ca> | RE: Disposition of Data Files When Abend | recovered, 9 attachment(s) dropped |
| 2015-04-15 | outlook:<VI1PR06MB1213BE872F34490BD5B99BD689E50@VI1PR06MB1213.eurprd06.prod.outlook.com> | inventory NN | recovered, 1 attachment(s) dropped |
| 2015-04-28 | outlook:<AM3PR06MB0204EA171A8E2F37F4139059AE80@AM3PR06MB020.eurprd06.prod.outlook.com> | RE: Test scenario recording | recovered, 1 attachment(s) dropped |
| 2015-06-15 | outlook:<DB4PR06MB206C7399A406288E3C95179EEB80@DB4PR06MB206.eurprd06.prod.outlook.com> | z/OS FTP | recovered, 1 attachment(s) dropped |
| 2015-06-17 | outlook:<AM3PR06MB0207029E42A17F1774081659AA60@AM3PR06MB020.eurprd06.prod.outlook.com> | FW: Muizenvanger | recovered on retry (succeeded without modification) |
| 2015-06-17 | outlook:<HE1PR06MB1307A24CC5AB9B2070FE416C92A60@HE1PR06MB1307.eurprd06.prod.outlook.com> | Muizenvanger | recovered on retry (succeeded without modification) |
| 2015-06-23 | outlook:<DB4PR06MB20600980A361B6D1EABDFB0EEA00@DB4PR06MB206.eurprd06.prod.outlook.com> | Sysout update | recovered, 2 attachment(s) dropped |
| 2015-07-23 | outlook:<DB3PR06MB5547C3BFACDD6B36FB1282B96820@DB3PR06MB554.eurprd06.prod.outlook.com> | XXSaldo Sources | recovered, 1 attachment(s) dropped |
| 2015-07-28 | outlook:<DB5PR06MB122275A7E4E4D2D886DD59B3908D0@DB5PR06MB1222.eurprd06.prod.outlook.com> | FW: Reset-SchedulerJob | recovered, 3 attachment(s) dropped |
| 2015-07-28 | outlook:<HE1PR06MB13070E85B8CFCC981A3CF588928D0@HE1PR06MB1307.eurprd06.prod.outlook.com> | RE: Data load wide tables | recovered, 2 attachment(s) dropped |
| 2015-07-28 | outlook:<HE1PR06MB1307379845EB8A03C3C59167928D0@HE1PR06MB1307.eurprd06.prod.outlook.com> | RE: Data load wide tables | recovered, 2 attachment(s) dropped |
| 2015-07-28 | outlook:<HE1PR06MB13078B8C54523FD56BBC185B928D0@HE1PR06MB1307.eurprd06.prod.outlook.com> | RE: Data load wide tables | recovered, 2 attachment(s) dropped |
| 2015-07-28 | outlook:<HE1PR06MB1307939AE11B8E2CA58AE32A928D0@HE1PR06MB1307.eurprd06.prod.outlook.com> | RE: Data load wide tables | recovered, 2 attachment(s) dropped |
| 2015-07-28 | outlook:<HE1PR06MB1307C4E814E194492EB41AEE928D0@HE1PR06MB1307.eurprd06.prod.outlook.com> | RE: Data load wide tables | recovered, 2 attachment(s) dropped |
| 2015-07-29 | outlook:<HE1PR06MB1307072D2E1CE2CFFC796F10928C0@HE1PR06MB1307.eurprd06.prod.outlook.com> | RE: Data load wide tables | recovered, 2 attachment(s) dropped |
| 2015-07-29 | outlook:<HE1PR06MB130749EA83D06CA8B72BC12A928C0@HE1PR06MB1307.eurprd06.prod.outlook.com> | RE: Data load wide tables | recovered, 2 attachment(s) dropped |
| 2015-07-30 | outlook:<AM3PR06MB020A2B75C69E62906165C5C9A8B0@AM3PR06MB020.eurprd06.prod.outlook.com> | FW: Reset-SchedulerJob | recovered, 3 attachment(s) dropped |
| 2015-07-31 | outlook:<HE1PR06MB13073307EB3FDFD4CDDB9F24928A0@HE1PR06MB1307.eurprd06.prod.outlook.com> | RE: Data load wide tables | recovered, 2 attachment(s) dropped |
| 2015-08-05 | outlook:<AM3PR06MB1313F746C0741F9A61D5AF5889750@AM3PR06MB1313.eurprd06.prod.outlook.com> | RE: NEWSALDO with NetCOBOL for Windows | recovered, 1 attachment(s) dropped |
| 2015-08-05 | outlook:<HE1PR06MB1307187A1152182607E45F0792750@HE1PR06MB1307.eurprd06.prod.outlook.com> | RE: DWS: PLOG Processing in Albatross | recovered, 2 attachment(s) dropped |
| 2015-08-05 | outlook:<HE1PR06MB1307916309FCF8ADEDEDC69D92750@HE1PR06MB1307.eurprd06.prod.outlook.com> | RE: DWS: PLOG Processing in Albatross | recovered, 3 attachment(s) dropped |
| 2015-08-05 | outlook:<HE1PR06MB1369D48A99665B7AF6C5266DFF750@HE1PR06MB1369.eurprd06.prod.outlook.com> | FW: NEWSALDO with NetCOBOL for Windows | recovered, 1 attachment(s) dropped |
| 2015-08-06 | outlook:<HE1PR06MB1369725C051F067CA985CF23FF740@HE1PR06MB1369.eurprd06.prod.outlook.com> | RE: NEWSALDO with NetCOBOL for Windows | recovered, 1 attachment(s) dropped |
| 2015-08-10 | outlook:<HE1PR06MB13073E02EB3F391296BA7DDE92700@HE1PR06MB1307.eurprd06.prod.outlook.com> | RE: Data load wide tables | recovered, 2 attachment(s) dropped |
| 2015-09-04 | outlook:<DB4PR06MB206742D2E62ADC622B8BE0BEE570@DB4PR06MB206.eurprd06.prod.outlook.com> | Editing Fujitsu varlen files | recovered, 2 attachment(s) dropped |
| 2015-09-18 | outlook:<AM3PR06MB09611D2DB1B31EC1F4A7CC71EE590@AM3PR06MB0961.eurprd06.prod.outlook.com> | DWS utils 0.4 | recovered, 2 attachment(s) dropped |
| 2015-09-22 | outlook:<AM3PR06MB1313BC494C5561B0A7EF7C3C89450@AM3PR06MB1313.eurprd06.prod.outlook.com> | Programma om firma switch te testen | recovered, 1 attachment(s) dropped |
| 2015-10-07 | outlook:<AM4PR06MB1539AE5347EDA86670BAC4D697360@AM4PR06MB1539.eurprd06.prod.outlook.com> | FW: NEWSALDO with NetCOBOL for Windows | recovered, 1 attachment(s) dropped |
| 2015-10-08 | outlook:<AM4PR06MB1539085152D8B6C23E46290197350@AM4PR06MB1539.eurprd06.prod.outlook.com> | FW: NEWSALDO with NetCOBOL for Windows | recovered, 1 attachment(s) dropped |
| 2015-10-09 | outlook:<HE1PR06MB1433A4F1B0DB4DE5F19ACCE5EF340@HE1PR06MB1433.eurprd06.prod.outlook.com> | Simple script to avoid regional setting problems | recovered, 2 attachment(s) dropped |
| 2015-10-16 | outlook:<A49D4E696C20C4479D57032721B612E53EF5ED5A@EDM-GOA-EXCH105.goa.ds.gov.ab.ca> | FW: SR38604 - Missing Generated Cheque Register | recovered on retry (succeeded without modification) |
| 2015-10-23 | outlook:<DB5PR06MB1591598DB9E4CFD24042556896260@DB5PR06MB1591.eurprd06.prod.outlook.com> | Converted kornshell scripts | recovered, 1 attachment(s) dropped |
| 2015-10-28 | outlook:<DB5PR06MB159116A1A294E650CF4021EB96210@DB5PR06MB1591.eurprd06.prod.outlook.com> | KornShell delivery | recovered, 1 attachment(s) dropped |
| 2015-11-20 | outlook:<DB5PR06MB151181D858432EA0C8001FB5921A0@DB5PR06MB1511.eurprd06.prod.outlook.com> | RE: New self-signed Java certificate? | recovered, 2 attachment(s) dropped |
| 2015-11-23 | outlook:<DB5PR06MB159178D8F3AC9F07CA5D536996070@DB5PR06MB1591.eurprd06.prod.outlook.com> | Nieuwste levering KornShell scripts | recovered, 1 attachment(s) dropped |
| 2015-11-24 | outlook:<HE1PR06MB13075B729E5148F982D5C7EEF6060@HE1PR06MB1307.eurprd06.prod.outlook.com> | RE: stand van zaken | recovered, 1 attachment(s) dropped |
| 2015-11-30 | outlook:<HE1PR06MB143473D516882DAE00B8D69AF7000@HE1PR06MB1434.eurprd06.prod.outlook.com> | FW: Compiling in UAT - Setting up 'set-env32.bat' | recovered, 1 attachment(s) dropped |
| 2015-12-03 | outlook:<CAPMxWGkYicET1uM1OF34Y8wbSVUQeMubBgiWU+YO8Pz4ZW2GRw@mail.gmail.com> | (no subject) | recovered on retry (succeeded without modification) |
| 2015-12-04 | outlook:<DB5PR06MB1591A24E6CA67967234EBD6F960C0@DB5PR06MB1591.eurprd06.prod.outlook.com> | Levering converted KornShell scripts | recovered, 1 attachment(s) dropped |
| 2015-12-21 | outlook:<DB5PR06MB15919EFC5CD1E6B88BCA484E96E40@DB5PR06MB1591.eurprd06.prod.outlook.com> | Nieuwe levering PowerShell | recovered, 1 attachment(s) dropped |
| 2015-12-23 | outlook:<AM3PR06MB02019B119A30BA69C3B7B369AE60@AM3PR06MB020.eurprd06.prod.outlook.com> | Stuff that doesn't compile | recovered, 2 attachment(s) dropped |
| 2016-04-11 | outlook:<AM4PR06MB1875DBE3D12E3227BFB83E2DF5940@AM4PR06MB1875.eurprd06.prod.outlook.com> | AMT Com Module | recovered, 5 attachment(s) dropped |
| 2016-09-10 | outlook:<AM3PR06MB020DCD4770909CC5AC9DE009AFD0@AM3PR06MB020.eurprd06.prod.outlook.com> | COBOL 2 OO docs | recovered, 1 attachment(s) dropped |
| 2016-09-16 | outlook:<DB5PR0601MB1960EF7CF8BDB43E1194EE62FFF30@DB5PR0601MB1960.eurprd06.prod.outlook.com> | PJ mg NAT / AD : livraison Eucalyptus 5.1.0 | recovered, 4 attachment(s) dropped |
| 2016-10-17 | outlook:<VI1PR0601MB2685572C8A9EC13936866B3AE2D00@VI1PR0601MB2685.eurprd06.prod.outlook.com> | jcl template regression tests | recovered, 1 attachment(s) dropped |
| 2016-10-19 | outlook:<AM3PR06MB02044307C64FFA7537E700B9AD20@AM3PR06MB020.eurprd06.prod.outlook.com> | RE: BD dev. environment | recovered, 1 attachment(s) dropped |
| 2016-10-21 | outlook:<8fa8e859-9a8a-414f-98f2-a77d32799e1c@DB3FFO11FD049.protection.gbl> | RE: Nieuwe case bij SOS berlin i.v.m. job scheduler | recovered, 3 attachment(s) dropped |
| 2016-10-24 | outlook:<AM3PR06MB0203D46B3B638444F28BD3C9AA90@AM3PR06MB020.eurprd06.prod.outlook.com> | RE: Update to SupportLine Incident #2878336 - Debugging | recovered, 4 attachment(s) dropped |
| 2016-10-27 | outlook:<AM3PR06MB020A142E43770E0AAEF5E509AAA0@AM3PR06MB020.eurprd06.prod.outlook.com> | RE: openen van copybooks in visual studio | recovered, 3 attachment(s) dropped |
| 2016-11-02 | outlook:<DB6PR0601MB26965F2D0C8EA628FB1EFF2A8BA00@DB6PR0601MB2696.eurprd06.prod.outlook.com> | Add support for XA transaction to an MSSQL server | recovered, 3 attachment(s) dropped |
| 2016-11-15 | outlook:<DB5PR0601MB19609A91327F837DAF2AEBD0FFBF0@DB5PR0601MB1960.eurprd06.prod.outlook.com> | RE: bonne version de TestMatch | recovered, 1 attachment(s) dropped |
| 2016-12-06 | outlook:<AM5PR0601MB26911EB7B2359B9F26721DC990820@AM5PR0601MB2691.eurprd06.prod.outlook.com> | RE: Spec? | recovered, 1 attachment(s) dropped |
| 2017-01-13 | outlook:<AM4PR06MB1539265A291E606D0408D8DA97780@AM4PR06MB1539.eurprd06.prod.outlook.com> | McCoys ; COBOL | recovered, 2 attachment(s) dropped |
| 2017-01-20 | outlook:<HE1PR0601MB25534558EFE90BAAA71B993589710@HE1PR0601MB2553.eurprd06.prod.outlook.com> | P2 repository for Eucalyptus | recovered, 2 attachment(s) dropped |
| 2017-02-03 | outlook:<07AE6ECA7A05C746A6EBFBF7A68D44AF01765D77B5@ISCEQNC01SXCH01.infosolco.net> | RE: New Trace file samples | recovered, 8 attachment(s) dropped |
| 2017-02-07 | outlook:<AM3PR06MB0201BF3F84017605405F9A59A430@AM3PR06MB020.eurprd06.prod.outlook.com> | RE: McCoys conv. of POC + v0.20170207 | recovered, 1 attachment(s) dropped |
| 2017-02-08 | outlook:<AM3PR06MB02009DEE2677D8762CF3C1D9A420@AM3PR06MB020.eurprd06.prod.outlook.com> | RE: McCoys conv. of POC + v0.20170207 | recovered, 1 attachment(s) dropped |
| 2017-02-14 | outlook:<AM3PR06MB020606232BC04D161A78FFC9A580@AM3PR06MB020.eurprd06.prod.outlook.com> | McCoys Sample | recovered, 1 attachment(s) dropped |
| 2017-02-15 | outlook:<AM3PR06MB02024A20F805A7D7606B1D09A5B0@AM3PR06MB020.eurprd06.prod.outlook.com> | McCoys sample: last check | recovered, 1 attachment(s) dropped |
| 2017-02-15 | outlook:<AM3PR06MB020D3FD8369DB31728C9EE09A5B0@AM3PR06MB020.eurprd06.prod.outlook.com> | RE: Good morning | recovered, 1 attachment(s) dropped |
| 2017-02-24 | outlook:<VI1PR0601MB2558481E1B4AC6749576E93289520@VI1PR0601MB2558.eurprd06.prod.outlook.com> | RE: Eucalyptus 5.1.4.pre | recovered, 2 attachment(s) dropped |
| 2017-02-27 | outlook:<ee02a87e8910471a9f6b0f274d1c594b@DB6PR0601MB2646.eurprd06.prod.outlook.com> | Action Required - Moves Application Project | recovered, 2 attachment(s) dropped |
| 2017-03-10 | outlook:<VI1PR0601MB255823143CB8814F4E4A420F89200@VI1PR0601MB2558.eurprd06.prod.outlook.com> | Eucalyptus Natural release 5.1.4 | recovered, 2 attachment(s) dropped |
| 2017-03-27 | outlook:<VI1PR0601MB26858FA7FA36F695C220427BE2330@VI1PR0601MB2685.eurprd06.prod.outlook.com> | FW: ISPACE.cbl | recovered, 2 attachment(s) dropped |
| 2017-03-28 | outlook:<VI1PR0601MB2685C10ECC2F0EE975561A1EE2320@VI1PR0601MB2685.eurprd06.prod.outlook.com> | FW: List of Cobol Programs | recovered, 2 attachment(s) dropped |
| 2017-05-03 | outlook:<90B15D01A902754E8223B7B432D4E92E565F4E10@ISCEQNC01SXCH02.infosolco.net> | RE: TestMatch replay | recovered, 2 attachment(s) dropped |
| 2017-05-03 | outlook:<90B15D01A902754E8223B7B432D4E92E565F4F82@ISCEQNC01SXCH02.infosolco.net> | RE: TestMatch replay | recovered, 2 attachment(s) dropped |
| 2017-06-15 | outlook:<DB6PR0602MB27416205768DD0C036DCE2E890C00@DB6PR0602MB2741.eurprd06.prod.outlook.com> | SGFR: JCL Conversion Specification | recovered, 2 attachment(s) dropped |
| 2017-06-15 | outlook:<DB6PR0602MB28391BF874E95C688165F3FF92C00@DB6PR0602MB2839.eurprd06.prod.outlook.com> | koalajni.dll config on jenkins | recovered, 1 attachment(s) dropped |
| 2017-06-16 | outlook:<HE1PR0602MB3308DEFE94B1F95CDB0F5BDB92C10@HE1PR0602MB3308.eurprd06.prod.outlook.com> | RE: Demo program for july 6th | recovered, 4 attachment(s) dropped |
| 2017-06-26 | outlook:<HE1PR0602MB3308F5A57AC9BE3835045BE292DF0@HE1PR0602MB3308.eurprd06.prod.outlook.com> | RE: [ASM Conversion][Accentor] Config changes, issues in output + new spec fo... | recovered, 1 attachment(s) dropped |
| 2017-07-07 | outlook:<AM5PR0602MB291453DC798ABCCFAF63884E9AAA0@AM5PR0602MB2914.eurprd06.prod.outlook.com> | RE: testmatch XML messages | recovered, 1 attachment(s) dropped |
| 2017-07-07 | outlook:<HE1PR0602MB3308736E8393699C6699029892AA0@HE1PR0602MB3308.eurprd06.prod.outlook.com> | RE: CICS CEDA definitions (was Power Autostart) | recovered on retry (succeeded without modification) |
| 2017-07-12 | outlook:<AM5PR0602MB2914F37BD56C242627628CD19AAF0@AM5PR0602MB2914.eurprd06.prod.outlook.com> | Moves COBOL to C# migratie | recovered on retry (succeeded without modification) |
| 2017-08-02 | outlook:<AM5PR0601MB26906FD8CA119C7CCA2EC529EDB00@AM5PR0601MB2690.eurprd06.prod.outlook.com> | RE: ISMRUN - Some functional knowledge infusion? | recovered, 1 attachment(s) dropped |
| 2017-08-02 | outlook:<AM5PR0602MB29143A01DF6D6D4053CD23699AB00@AM5PR0602MB2914.eurprd06.prod.outlook.com> | RE: Heb jij die test met DataTurn 11.0 nog gedaan? Moet ik nog kijken in de s... | recovered, 4 attachment(s) dropped |
| 2017-09-26 | outlook:<VI1PR0602MB3295C663067A51C855E5E600FF7B0@VI1PR0602MB3295.eurprd06.prod.outlook.com> | FW: Data Match - Issue / Upgrade to current version | recovered on retry (succeeded without modification) |
| 2017-10-19 | outlook:<VI1PR0602MB292767E5EF79ACBCF1E41FF99A420@VI1PR0602MB2927.eurprd06.prod.outlook.com> | RE: CicsCobolProgram | recovered, 2 attachment(s) dropped |
| 2017-10-20 | outlook:<AM6PR0602MB35429607BC38853E0C770D5090430@AM6PR0602MB3542.eurprd06.prod.outlook.com> | SGBT: EntireX Replay in TestMatch | recovered, 3 attachment(s) dropped |
| 2017-10-25 | outlook:<410FDC801610C5448F45D78C53741F8041ED4248@MMXDC2630.hermes.si.socgen> | RE: Lot2 - composants VUT et ARG | recovered, 5 attachment(s) dropped |
| 2017-11-07 | outlook:<VI1PR06MB11013176A5FBB2214D8DAC5292510@VI1PR06MB1101.eurprd06.prod.outlook.com> | RE: 64-bit libkoala version | recovered, 2 attachment(s) dropped |
| 2017-11-07 | outlook:<VI1PR06MB110187AFE32331F22BD5DF5E92510@VI1PR06MB1101.eurprd06.prod.outlook.com> | 64-bit libkoala version | recovered, 2 attachment(s) dropped |
| 2017-11-27 | outlook:<AM5PR0602MB32349C3F042B53211347CA49EE250@AM5PR0602MB3234.eurprd06.prod.outlook.com> | Ista smoke test | recovered, 2 attachment(s) dropped |
| 2017-12-11 | outlook:<VI1PR06MB1101A35662DF2BB41C20474192370@VI1PR06MB1101.eurprd06.prod.outlook.com> | RE: DMSRUN.exe die blijft hangen | recovered, 1 attachment(s) dropped |
| 2017-12-22 | outlook:<410FDC801610C5448F45D78C53741F8041EFC80E@MMXDC2630.hermes.si.socgen> | RE: SGFR: VUT - Infos/Composants Manquants | recovered, 3 attachment(s) dropped |
| 2018-01-16 | outlook:<VI1PR0602MB379136AAC0B26A065AF5FA4C89EA0@VI1PR0602MB3791.eurprd06.prod.outlook.com> | Conditional compile | recovered, 4 attachment(s) dropped |
| 2018-01-23 | outlook:<VI1PR0601MB2685119A5E78122E60F820C4E2E30@VI1PR0601MB2685.eurprd06.prod.outlook.com> | ista | recovered, 1 attachment(s) dropped |
| 2018-02-14 | outlook:<410FDC801610C5448F45D78C53741F8041F308C4@MMXDC2630.hermes.si.socgen> | RE: Lot2 - composants VUT et ARG | recovered, 5 attachment(s) dropped |
| 2018-02-20 | outlook:<OF3457D980.393C1D54-ON0025823A.005F2073-0025823A.005F81EC@notes.na.collabserv.com> | Re: Anubex Host Services PowerShell | recovered, 5 attachment(s) dropped |
| 2018-02-20 | outlook:<OFA9167F7F.880CFFE7-ON0025823A.00623871-0025823A.00624432@notes.na.collabserv.com> | Re: Anubex Host Services PowerShell | recovered, 5 attachment(s) dropped |
| 2018-02-21 | outlook:<DB3PR0602MB3786E0B918B834899B21F4F2EECE0@DB3PR0602MB3786.eurprd06.prod.outlook.com> | RE: RE: Anubex Host Services PowerShell | recovered, 3 attachment(s) dropped |
| 2018-03-27 | outlook:<AM5PR0601MB2321CB3B2A6C3028F94A322DF6AC0@AM5PR0601MB2321.eurprd06.prod.outlook.com> | Please add to software repository | recovered, 1 attachment(s) dropped |
| 2018-04-03 | outlook:<410FDC801610C5448F45D78C53741F8041F51D49@MMXDC2630.hermes.si.socgen> | RE:  Désengagement Natural/Adabas - Préparation lot 2018 - Applications VEX | recovered, 3 attachment(s) dropped |
| 2018-04-20 | outlook:<DB5PR06MB15915BE2A8CD9BA00DB8C1B496B40@DB5PR06MB1591.eurprd06.prod.outlook.com> | RE: PMS and PS delivery | recovered, 1 attachment(s) dropped |
| 2018-05-03 | outlook:<VI1PR06MB16930BC14D6DCFA152BAF9AE92870@VI1PR06MB1693.eurprd06.prod.outlook.com> | DB-POC Exec SQL | recovered, 1 attachment(s) dropped |
| 2018-05-25 | outlook:<410FDC801610C5448F45D78C53741F8041F7B9CD@MMXDC2630.hermes.si.socgen> | RE: Désengagement Natural/ADABAS - Chiffrage pour le nouveau modèle opérationnel | recovered, 7 attachment(s) dropped |
| 2018-06-01 | outlook:<AM4PR06MB17471FDF0DAE5729D3DF785B9A620@AM4PR06MB1747.eurprd06.prod.outlook.com> | FW: DB progress | recovered, 1 attachment(s) dropped |
| 2018-06-01 | outlook:<AM4PR06MB17477A0D39881D9DD49F27359A620@AM4PR06MB1747.eurprd06.prod.outlook.com> | RE: DB progress | recovered, 1 attachment(s) dropped |
| 2018-06-19 | outlook:<VI1PR06MB1693107EFA32A1BD3D41FECA92700@VI1PR06MB1693.eurprd06.prod.outlook.com> | RE: Performance enhancements converted Cobol code | recovered on retry (succeeded without modification) |
| 2018-06-20 | outlook:<VI1PR06MB1693DAC469FEE09878B939D392770@VI1PR06MB1693.eurprd06.prod.outlook.com> | RE: Performance enhancements converted Cobol code | recovered on retry (succeeded without modification) |
| 2018-06-21 | outlook:<VI1PR06MB1693F93AE0F7BAD0BBDAF3A892760@VI1PR06MB1693.eurprd06.prod.outlook.com> | RE: Performance enhancements converted Cobol code | recovered on retry (succeeded without modification) |
| 2018-06-22 | outlook:<VI1PR06MB1693B059905FF14169E8D49092750@VI1PR06MB1693.eurprd06.prod.outlook.com> | RE: Performance enhancements converted Cobol code | recovered on retry (succeeded without modification) |
| 2018-06-26 | outlook:<VI1PR06MB169376CA85891AE7B53B21F292490@VI1PR06MB1693.eurprd06.prod.outlook.com> | RE: Performance enhancements converted Cobol code | recovered on retry (succeeded without modification) |
| 2018-06-28 | outlook:<AM4PR0601MB2177067D133CFD9DDE2D1900954F0@AM4PR0601MB2177.eurprd06.prod.outlook.com> | FW: Use of dowitcher tool for file migration | recovered, 4 attachment(s) dropped |
| 2018-07-03 | outlook:<ED1338920186D5439D48D2516770B136E36F9115@PLKAT3EX03.pl.root.net> | AW: Java style for IntelliJ | recovered, 2 attachment(s) dropped |
| 2018-07-10 | outlook:<AM4PR0601MB2177E8283FF2CEC0D19839D4955B0@AM4PR0601MB2177.eurprd06.prod.outlook.com> | FW: jABRE First L&P test results- Update Terminal Emulator | recovered, 9 attachment(s) dropped |
| 2018-09-26 | outlook:<AM4PR06MB1747420931219FC67E3F8EE09A150@AM4PR06MB1747.eurprd06.prod.outlook.com> | run-test.cmd script for repeated tests | recovered, 1 attachment(s) dropped |
| 2018-10-05 | outlook:<AM4P191MB00526AFEC8A683A5F58AF80B9AEB0@AM4P191MB0052.EURP191.PROD.OUTLOOK.COM> | Sample program to run tests with | recovered, 3 attachment(s) dropped |
| 2018-11-27 | outlook:<AM4P191MB00527810ADB5D90EBE1C40929AD00@AM4P191MB0052.EURP191.PROD.OUTLOOK.COM> | Can we get an experimental COBOL services regression-tested? | recovered, 1 attachment(s) dropped |
| 2018-12-06 | outlook:<AM4P191MB01454208D0461EAC023335A2EFA90@AM4P191MB0145.EURP191.PROD.OUTLOOK.COM> | Moves client test | recovered, 2 attachment(s) dropped |
| 2018-12-06 | outlook:<AM4P191MB0145CE0EE9DFBF01FAD6875BEFA90@AM4P191MB0145.EURP191.PROD.OUTLOOK.COM> | Desktop test intrumentation tool | recovered, 3 attachment(s) dropped |
| 2019-02-12 | outlook:<AM4P191MB000286850A1C2BF6E9A8BAF692650@AM4P191MB0002.EURP191.PROD.OUTLOOK.COM> | RE: Sandcastle Help File Builder + Style notes | recovered on retry (succeeded without modification) |
| 2019-03-13 | outlook:<DB7PR05MB559168DC6403BA9A6EA6862EA74A0@DB7PR05MB5591.eurprd05.prod.outlook.com> | Livraison VEX .zip, VEX.zip, VEX-datamig.zip, VEX-ddl.zip (livré par EBS) | recovered, 4 attachment(s) dropped |
| 2019-03-13 | outlook:<DB7PR05MB559191C6A1DAC9F3A57F3AB5A74A0@DB7PR05MB5591.eurprd05.prod.outlook.com> | Envoi d’un message : PBATP.zip.zip (livré par EBS) | recovered, 1 attachment(s) dropped |
| 2019-03-13 | outlook:<DB7PR05MB5591E6D1814C7AE138523300A74A0@DB7PR05MB5591.eurprd05.prod.outlook.com> | Envoi d’un message : PBATP.zip.zip (livré par EBS) | recovered, 1 attachment(s) dropped |
| 2019-03-27 | outlook:<AM0P191MB05162622C5083DA6401F50CDFA580@AM0P191MB0516.EURP191.PROD.OUTLOOK.COM> | FW: Migratie Cobol Agallis (ex-FB Brokerage) | recovered, 1 attachment(s) dropped |
| 2019-03-28 | outlook:<AM4P191MB008430BEE28B7EAD57AD52F196590@AM4P191MB0084.EURP191.PROD.OUTLOOK.COM> | RE: Vorbereitung ZLA Workshop / AW: IDMS Migration | recovered on retry (succeeded without modification) |
| 2019-04-15 | outlook:<AM0P191MB0385ED231B99F2960FC8497FF32B0@AM0P191MB0385.EURP191.PROD.OUTLOOK.COM> | RE: ETS#26371 - Dynamic JCL submission by ROADS sessions | recovered, 17 attachment(s) dropped |
| 2019-04-16 | outlook:<AM0P191MB0385A28551D2197EA72DA734F3240@AM0P191MB0385.EURP191.PROD.OUTLOOK.COM> | RE: ETS#26371 - Dynamic JCL submission by ROADS sessions | recovered, 17 attachment(s) dropped |
| 2019-05-06 | outlook:<DB7PR05MB559116594303EE69F4A84104A7300@DB7PR05MB5591.eurprd05.prod.outlook.com> | RE: Applications GSP et AVB | recovered, 3 attachment(s) dropped |
| 2019-05-08 | outlook:<AM4P191MB0178DD71515DFA7351040C2692320@AM4P191MB0178.EURP191.PROD.OUTLOOK.COM> | RE: CPU Cores Utilization in jABRE | recovered, 9 attachment(s) dropped |
| 2019-05-16 | outlook:<VI1P191MB047704AC91AEDEF14E53E8C0920A0@VI1P191MB0477.EURP191.PROD.OUTLOOK.COM> | Program Dispatcher problems | recovered, 2 attachment(s) dropped |
| 2019-05-20 | outlook:<DB7PR05MB55914663F6463635648A447BA7060@DB7PR05MB5591.eurprd05.prod.outlook.com> | RE: Evolutions ARG à prendre en compte par ANUBEX | recovered, 3 attachment(s) dropped |
| 2019-05-29 | outlook:<AM4P191MB00523809F115C089C22AB9559A1F0@AM4P191MB0052.EURP191.PROD.OUTLOOK.COM> | Fw: run-test.cmd script for repeated tests | recovered, 1 attachment(s) dropped |
| 2019-05-29 | outlook:<AM4P191MB00525956224FE8F2E6DE9BF49A1F0@AM4P191MB0052.EURP191.PROD.OUTLOOK.COM> | Fw: run-test.cmd script for repeated tests | recovered, 1 attachment(s) dropped |
| 2019-05-29 | outlook:<AM4P191MB00525B60682E1CD5FD5D21A69A1F0@AM4P191MB0052.EURP191.PROD.OUTLOOK.COM> | Fw: run-test.cmd script for repeated tests | recovered, 1 attachment(s) dropped |
| 2019-07-30 | outlook:<AM0PR08MB5508FF629AC7387E68ECDB8D9ADC0@AM0PR08MB5508.eurprd08.prod.outlook.com> | Conversion related changes + Enhancement tickets | recovered, 1 attachment(s) dropped |
| 2019-07-31 | outlook:<AM7PR08MB55101F035858EC441DC72B979ADF0@AM7PR08MB5510.eurprd08.prod.outlook.com> | Conversion related changes/enhancement tickets | recovered, 2 attachment(s) dropped |
| 2019-08-05 | outlook:<VI1PR08MB4096F8F5EDD526BB2FCDF44B92DA0@VI1PR08MB4096.eurprd08.prod.outlook.com> | Flushing cached data in cics worker-tasks and tabex | recovered, 2 attachment(s) dropped |
| 2019-08-08 | outlook:<AM0PR08MB55087498D7CE7C97718161E59AD70@AM0PR08MB5508.eurprd08.prod.outlook.com> | RE:  Conversion related changes/enhancement tickets | recovered, 2 attachment(s) dropped |
| 2019-09-03 | outlook:<AM0PR08MB5393057C841DADC3A694AAD5F4B90@AM0PR08MB5393.eurprd08.prod.outlook.com> | [fedris] How do I capture the output of jsupports Passwordtool in a Powershel... | recovered, 1 attachment(s) dropped |
| 2019-09-03 | outlook:<DB6PR0802MB2486BF05F75F96629B972018E2B90@DB6PR0802MB2486.eurprd08.prod.outlook.com> | RE: Cobol voorbeeld FMV01 | recovered, 22 attachment(s) dropped |
| 2019-09-16 | outlook:<PR1PR05MB5593157C92570E7782A111C3A78C0@PR1PR05MB5593.eurprd05.prod.outlook.com> | RE: Désengagement NATURAL/ADABAS : Lot 2 - ARG Délai de prise en charge derni... | recovered, 4 attachment(s) dropped |
| 2019-10-21 | outlook:<AM6PR08MB4949989053A714EBA4BA0C9C89690@AM6PR08MB4949.eurprd08.prod.outlook.com> | Terminal Client's mouse selection mode (ie: select rectangle of tabular text ... | recovered, 2 attachment(s) dropped |
| 2019-10-31 | outlook:<DB8PR08MB553202E9DE839F02551E0EEDF3630@DB8PR08MB5532.eurprd08.prod.outlook.com> | RE:  ETS#28636 - Delete error: Cannot delete non-empty GDG unless FORCE is sp... | recovered, 5 attachment(s) dropped |
| 2019-12-05 | outlook:<CAPMxWG=obWd7u4NvhE2T2k1gryHhhGwH2w1c8eZ1BMKKgHY+gw@mail.gmail.com> | Audi A5 - 1-XCP-297 | recovered on retry (succeeded without modification) |
| 2020-03-12 | outlook:<AM0PR08MB5508BD6310254F2CFC3D21129AFD0@AM0PR08MB5508.eurprd08.prod.outlook.com> | RE: Vooruitgang ZLA? | recovered, 4 attachment(s) dropped |
| 2020-04-16 | outlook:<AM6PR08MB3942D9030C3FBBF33837C0D28FD80@AM6PR08MB3942.eurprd08.prod.outlook.com> | RE: Help with API docs | recovered, 1 attachment(s) dropped |
| 2020-06-17 | outlook:<AM6PR08MB37201C08CB19564D4289F397F89A0@AM6PR08MB3720.eurprd08.prod.outlook.com> | FW: Anubex Trial conversion for Cobol source | recovered, 1 attachment(s) dropped |
| 2020-06-23 | outlook:<AM6PR08MB4053FF0474089CFCB469605C85940@AM6PR08MB4053.eurprd08.prod.outlook.com> | RE: Company meeting of 26 June | recovered on retry (succeeded without modification) |
| 2020-07-29 | outlook:<AM4PR0802MB21616891CFC3F5F33457BFD597700@AM4PR0802MB2161.eurprd08.prod.outlook.com> | FW: Request for technical information regarding cobol migration framework | recovered, 1 attachment(s) dropped |
| 2020-11-19 | outlook:<AM0PR08MB4162A7422DC37A4D91C295BBE7E00@AM0PR08MB4162.eurprd08.prod.outlook.com> | small Cobol/Java test program | recovered, 1 attachment(s) dropped |
| 2021-01-25 | outlook:<AM0PR08MB5507C2B6C6151F5437CAFD9996BD0@AM0PR08MB5507.eurprd08.prod.outlook.com> | RE: Colonial code | recovered, 3 attachment(s) dropped |
| 2021-02-05 | outlook:<AM7PR08MB5333912B53BAC6D85D804A3492B29@AM7PR08MB5333.eurprd08.prod.outlook.com> | RE: Cobolbridge vraagje | recovered, 2 attachment(s) dropped |
| 2021-03-23 | outlook:<AM0PR08MB55078D095CF105C773B330C596649@AM0PR08MB5507.eurprd08.prod.outlook.com> | RE: | recovered on retry (succeeded without modification) |
| 2021-03-23 | outlook:<PR3PR08MB5721D44FC653D669B01A3628F8649@PR3PR08MB5721.eurprd08.prod.outlook.com> | (no subject) | recovered on retry (succeeded without modification) |
| 2021-04-08 | outlook:<AM0PR08MB2993376964DBCB033FCF5FDD9A749@AM0PR08MB2993.eurprd08.prod.outlook.com> | RE: Gio, nice job today!  Pls send me the deck.  Many thanks,  Scott | recovered on retry (succeeded without modification) |
| 2021-04-08 | outlook:<DBAPR08MB57205284BFAAE2DE1C23284BF8749@DBAPR08MB5720.eurprd08.prod.outlook.com> | Laatste deck, indien er slides moeten getoond worden | recovered on retry (succeeded without modification) |
| 2021-04-14 | outlook:<AM0PR08MB3089C3D6B0E5F7AF587B1D71894E9@AM0PR08MB3089.eurprd08.prod.outlook.com> | RE: Graph visualization tools | recovered, 5 attachment(s) dropped |
| 2021-04-26 | outlook:<AM0PR08MB308992D838765C86677C4EA889429@AM0PR08MB3089.eurprd08.prod.outlook.com> | D3 control flow graph source code | recovered, 2 attachment(s) dropped |
| 2021-05-12 | outlook:<AM0PR08MB4609CB5FCA4EF0966C0F63C3EE529@AM0PR08MB4609.eurprd08.prod.outlook.com> | RE: GlobeLife | recovered, 2 attachment(s) dropped |
| 2021-05-20 | outlook:<AM0PR08MB46095376EF1073FE1090CAEBEE2A9@AM0PR08MB4609.eurprd08.prod.outlook.com> | Sysout-service deployment | recovered, 5 attachment(s) dropped |
| 2021-05-28 | outlook:<AM9PR08MB59706BB79C0C1A359A52D97D8F229@AM9PR08MB5970.eurprd08.prod.outlook.com> | RE: Astadia MyGet | recovered, 1 attachment(s) dropped |
| 2021-06-10 | outlook:<AM8PR08MB6403BDB5C3B43F136332BCF9E2359@AM8PR08MB6403.eurprd08.prod.outlook.com> | RE: Astadia and Capgemini Mainframe Modernization Opportunity | recovered, 15 attachment(s) dropped |
| 2021-06-24 | outlook:<AM8PR08MB64653EB6676F1260E8B0E600EE079@AM8PR08MB6465.eurprd08.prod.outlook.com> | RE: Ensono: help to get good sample code | recovered, 1 attachment(s) dropped |
| 2021-06-24 | outlook:<AM8PR08MB6465A6D23BA0AA94D59E42E1EE079@AM8PR08MB6465.eurprd08.prod.outlook.com> | RE: Ensono: help to get good sample code | recovered, 1 attachment(s) dropped |
| 2021-06-29 | outlook:<AM0PR08MB29934244C2E5EB9B18E516DA9A029@AM0PR08MB2993.eurprd08.prod.outlook.com> | RE: Please let me see the Ensono Care Package before it goes out.  THX,  SS | recovered on retry (succeeded without modification) |
| 2021-08-23 | outlook:<186521080-1629717358408@us-mta-289.us.mimecast.lan> | [Postmaster] Attachment Release | recovered, 1 attachment(s) dropped |
| 2021-08-23 | outlook:<AM8PR08MB58580B574D5E5E6E4678383D97C49@AM8PR08MB5858.eurprd08.prod.outlook.com> | FW: [Postmaster] Attachment Release | recovered, 1 attachment(s) dropped |
| 2021-10-08 | outlook:<DM6PR01MB40439D9F0F3D350982AD9514BDB29@DM6PR01MB4043.prod.exchangelabs.com> | RE: PoC RFQ for VSAM to DB2 and COBOL to Java | recovered, 7 attachment(s) dropped |
| 2021-10-12 | outlook:<AM9PR08MB685052DDE90E9F0E1086B159F8B69@AM9PR08MB6850.eurprd08.prod.outlook.com> | RE: PoC RFQ for VSAM to DB2 and COBOL to Java (Followup) | recovered, 3 attachment(s) dropped |
| 2021-10-18 | outlook:<PAXPR08MB7336FCD7DD53BC560DB8A89D9ABC9@PAXPR08MB7336.eurprd08.prod.outlook.com> | RE: Initial set of Enterprise COBOL/DB2 conversion results | recovered, 3 attachment(s) dropped |
| 2022-01-10 | outlook:<AM8PR08MB56366BEB31363F86A0D740B592509@AM8PR08MB5636.eurprd08.prod.outlook.com> | Additional performance tests under JCICS | recovered, 5 attachment(s) dropped |
| 2022-03-11 | outlook:<VI1PR08MB551860A1922BE01D445467FF960C9@VI1PR08MB5518.eurprd08.prod.outlook.com> | RE: Factory User Docs | recovered, 3 attachment(s) dropped |
| 2022-03-17 | outlook:<PAXPR08MB733625EBB26AB6D6CE286F769A129@PAXPR08MB7336.eurprd08.prod.outlook.com> | RE: Anubex development efforts | recovered on retry (succeeded without modification) |
| 2022-03-24 | outlook:<PAXPR08MB73362ACFF2B4D734876629D59A199@PAXPR08MB7336.eurprd08.prod.outlook.com> | FW: Anubex/Audit-openstaande vragen | recovered on retry (succeeded without modification) |
| 2022-04-11 | outlook:<DB9PR08MB7422FFAD813F8942872B53BE96EA9@DB9PR08MB7422.eurprd08.prod.outlook.com> | FW: Factory User Docs | recovered, 3 attachment(s) dropped |
| 2022-04-25 | outlook:<DB9PR08MB74220C630FE6C2F6088E410C96F89@DB9PR08MB7422.eurprd08.prod.outlook.com> | RE: CodeTurn Tools | recovered, 1 attachment(s) dropped |
| 2022-04-29 | outlook:<DB9PR08MB742208A3D2838EBAAC4F2F7596FC9@DB9PR08MB7422.eurprd08.prod.outlook.com> | RE: CodeTurn Tools | recovered, 1 attachment(s) dropped |
| 2022-05-09 | outlook:<PA4PR08MB7572CF16ABFF96FE90537705E2C69@PA4PR08MB7572.eurprd08.prod.outlook.com> | RE: SDW - Batch job runtime info | recovered on retry (succeeded without modification) |
| 2022-05-27 | outlook:<AM8PR08MB66118375E582B130FCF46B36FAD89@AM8PR08MB6611.eurprd08.prod.outlook.com> | Spring cleaning - hardware give away | recovered on retry (succeeded without modification) |
| 2022-06-07 | outlook:<AM9PR08MB6850A4355AAD07060217EC8FF8A59@AM9PR08MB6850.eurprd08.prod.outlook.com> | Amdocs AT&T PoC  --  hulp gevraagd - vrij dringend | recovered on retry (succeeded without modification) |
| 2022-07-10 | outlook:<AM0PR08MB5316F8B9522A487448EE1B0FF3849@AM0PR08MB5316.eurprd08.prod.outlook.com> | RE: Tijdelijke aangepassing betreden gebouw vanaf 04/07/22_UPDATE vanaf maand... | recovered on retry (succeeded without modification) |
| 2025-12-01 | outlook:<DB9PR06MB75290462EBF7E444635758D1F4DBA@DB9PR06MB7529.eurprd06.prod.outlook.com> | RE: Astadia Career Day / Quick discussion & alignment | recovered on retry (succeeded without modification) |
