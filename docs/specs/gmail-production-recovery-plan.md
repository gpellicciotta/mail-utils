# Production Store-in-Gmail Detection and Recovery Plan

This document outlines failure detection mechanisms, operational safeguards, and recovery procedures for `mail-utils store-in-gmail` against production mailboxes.

## Principles and Safety Invariants

- Isolated write scope: `store-in-gmail` only calls `messages.import` and `labels.create`.
- Pre-existing mail untouched: the tool never modifies or deletes pre-existing messages in the target account.
- Run tracking isolation: every stored message receives an immutable tracking label (`mail-utils-store-in-gmail-<UTC timestamp>`).
- Local state tracking: every successfully uploaded message records its Gmail ID in the local SQLite database.

## Failure Modes and Detection Vectors

### Authentication or Target Account Mismatch
- Risk: storing messages into the wrong Google account.
- Detection:
  - Run `mail-utils check-gmail-account <name>` before execution to inspect the mapped email address and scopes.
  - Review the startup log line `Target account: <email>` emitted immediately before the first write.
- Preventative gate: abort execution immediately if the authenticated email does not match the intended destination.

### Network Abort, Process Crash, or System Reboot
- Risk: interrupted execution leaves the mailbox partially populated.
- Detection:
  - Command terminates with non-zero exit code or incomplete progress percentage.
  - Log summary indicates fewer messages stored than total candidates.
  - Local `sync_state` retains active `gmail_store_run_label`.
- Mitigation: resume without duplicate uploads by rerunning the identical command.

### Gmail API Rate Limiting and Quota Throttling
- Risk: high request volume exceeds per-user quota (250 units/second).
- Detection:
  - Warnings logged: `Gmail rate limit hit, retrying in Xs (attempt N/5)`.
  - HTTP 429 or HTTP 403 rate-limit error responses.
- Mitigation: automated rate limiter caps calls at 8/sec; exponential backoff retries transient bursts up to 5 times.

### Malformed Content or Schema Parsing Rejection
- Risk: Gmail API rejects a specific malformed RFC 822 payload (HTTP 400).
- Detection:
  - Command crashes with `HttpError 400: Invalid Content`.
  - Log records the specific failing message ID before abortion.
- Mitigation: isolate the offending message with `--filter` or inspect body structure before resumption.

## Pre-Flight Operational Checklist

Before initiating a production migration run:

1. Verify binary and environment:
   - Confirm all unit tests and formatting checks pass (`pytest`, `ruff check .`).
2. Confirm target mailbox identity:
   ```powershell
   mail-utils check-gmail-account <account-name>
   ```
   Confirm the displayed email matches the intended production recipient.
3. Execute dry run:
   ```powershell
   mail-utils store-in-gmail --account <account-name> --db data/ --dry-run
   ```
   Inspect candidate count and label mappings.
4. Execute capped pilot run:
   ```powershell
   mail-utils store-in-gmail --account <account-name> --db data/ --max-messages 50
   ```
5. Inspect pilot in Gmail web UI:
   - Search `label:mail-utils-store-in-gmail-*` in the web client.
   - Verify date ordering, sender names, Unicode body rendering, and attachment integrity.

## Recovery and Rollback Playbooks

### Resuming an Interrupted Run

When a run is stopped prematurely by network drops, rate limits, or `--max-messages`:

1. Re-run the exact command used initially:
   ```powershell
   mail-utils store-in-gmail --account <account-name> --db data/
   ```
2. Verify startup output indicates reuse of the existing tracking label.
3. Observe skipped count matching already stored messages.
4. Confirm run completes with all candidates indexed.

### Full Run Rollback

If imported data must be completely removed from the production mailbox:

1. Retrieve the tracking label from the execution logs or local database:
   ```powershell
   sqlite3 data/mails.db "SELECT value FROM sync_state WHERE key = 'gmail_store_run_label';"
   ```
2. Execute automated cleanup to move all messages with the tracking label to Gmail Trash and delete the label:
   ```powershell
   python scripts/gmail-roundtrip-test.py cleanup --account <account-name> --label <tracking-label-name> --apply
   ```
3. Reset local database storage markers:
   ```powershell
   sqlite3 data/mails.db "UPDATE messages SET stored_in_gmail_id = NULL; UPDATE sync_state SET value = '' WHERE key = 'gmail_store_run_label';"
   ```
4. Verify mailbox cleanliness via `check-gmail-account` or Gmail search.

### Selective Single-Message Correction

If only specific messages require re-upload or removal:

1. Search for specific messages in Gmail web UI using the tracking label and sender/subject query:
   ```
   label:mail-utils-store-in-gmail-<timestamp> from:bad-sender@example.com
   ```
2. Move selected messages to Trash manually in the web UI.
3. Reset the stored status for those specific IDs in the local database:
   ```powershell
   sqlite3 data/mails.db "UPDATE messages SET stored_in_gmail_id = NULL WHERE id IN ('msg_id_1', 'msg_id_2');"
   ```
4. Re-run `store-in-gmail` with a `--filter` targeting those IDs to upload corrected versions.

## Post-Flight Verification Runbook

1. Check completion summary:
   - Ensure the final log entry reports `N messages stored, 0 skipped, last message stored: <id>`.
2. Audit Gmail message count:
   ```powershell
   mail-utils check-gmail-account <account-name>
   ```
   Confirm message and thread totals increased by the expected count.
3. Validate sample roundtrip:
   - Ingest a sample back via `import-gmail --filter "label:<tracking-label>"` into a verification database.
   - Run `stats` to compare message metrics against the origin database.
