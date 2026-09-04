# Store-In-Gmail End-to-End Test Plan

This specification details the end-to-end verification plan for `mail-utils store-in-gmail`.
It exercises full round-trip fidelity, kill and resume handling, and all edge cases discovered in T0020.

---

## 1. Objectives

- Validate live migration fidelity of `store-in-gmail` against the disposable test account `tester.pellicciotta@gmail.com`.
- Verify resumability and idempotency when an upload run is interrupted or capped via `--max-messages`.
- Verify lossless handling of all complex MIME structures and header edge cases identified in T0020.
- Verify safe teardown and cleanup using `scripts/gmail-roundtrip-test.py cleanup`.

---

## 2. Test Environment and Safety Controls

- **Target Account**: `tester.pellicciotta@gmail.com` (configured via `mail-utils prepare-gmail-account tester --with-write`).
- **Account Verification**: Execute `mail-utils check-gmail-account tester` before every test run.
- **Safety Rule**: Never run test write operations against any production account.
- **Dedicated Workspaces**: Store temporary SQLite databases and EML files under `data/test-run/`.
- **Cleanup Requirement**: All seeded test messages and tracking labels must be trashed and deleted after testing.

---

## 3. Test Scenarios

### Scenario A: Full Round-Trip Fidelity with Curated T0020 Edge Cases

This scenario validates that messages restored to Gmail and synced back match origin attributes exactly.

#### Seed Dataset Composition
1. **Standard Messages**:
   - Plain text body with no attachments.
   - HTML body with UTF-8 Unicode characters (emoji, CJK, accents).
   - Multipart/alternative body with plain text and rich HTML.
2. **Attachment Variations**:
   - Single image attachment (PNG) with inline disposition and Content-ID reference.
   - Dual attachments (text file and arbitrary binary octet-stream).
   - Medium binary payload (256 KB) testing chunked transport.
   - Non-UTF-8 text attachment (Windows-1252 character encoding).
   - Attachment filename containing colons or characters sanitized by filesystem export.
   - Filenameless attachment bearing Content-ID.
3. **MIME and Header Variations**:
   - Display name containing unquoted `@` symbol (e.g. `John @ Work <john@example.com>`).
   - Display name formatted as `Last, First` with unquoted comma.
   - Display name containing unquoted bracket annotations (e.g. `Alice [Contractor] <alice@example.com>`).
   - Attached nested RFC 822 email message (`message/rfc822`).

#### Execution Workflow
1. Seed test mailbox with curated dataset:
   ```powershell
   python scripts/gmail-roundtrip-test.py seed --account tester --to tester.pellicciotta@gmail.com
   ```
2. Ingest source messages into local origin database:
   ```powershell
   mail-utils import-gmail --with-attachments --account tester --db data/test-origin --filter "label:mail-utils-roundtrip-test-source"
   ```
3. Export origin messages to EML format:
   ```powershell
   mail-utils export data/test-origin-export --format eml --db data/test-origin
   ```
4. Restore messages from origin database into Gmail:
   ```powershell
   mail-utils store-in-gmail --account tester --db data/test-origin
   ```
5. Ingest restored messages into result database:
   ```powershell
   mail-utils import-gmail --with-attachments --account tester --db data/test-result --filter "label:mail-utils-store-in-gmail-*"
   ```
6. Export result messages to EML format:
   ```powershell
   mail-utils export data/test-result-export --format eml --db data/test-result
   ```
7. Verify round-trip equivalence across headers, body content, and attachment checksums:
   ```powershell
   python scripts/gmail-roundtrip-test.py compare --origin-db data/test-origin/mails.db --origin-export data/test-origin-export --result-db data/test-result/mails.db --result-export data/test-result-export
   ```

---

### Scenario B: Kill and Resume Interruption Test

This scenario validates that interrupted store operations resume without duplicating messages or minting conflicting tracking labels.

#### Execution Workflow
1. Prepare a local test database with 10 distinct messages.
2. Run store-in-gmail with `--max-messages 4`:
   ```powershell
   mail-utils store-in-gmail --account tester --db data/test-origin --max-messages 4
   ```
3. Verify output reports stoppage after 4 messages and persistence of the run label in `sync_state`.
4. Inspect database `stored_in_gmail_id` values to confirm only the first 4 messages are marked as stored.
5. Resume store-in-gmail without `--max-messages`:
   ```powershell
   mail-utils store-in-gmail --account tester --db data/test-origin
   ```
6. Verify output reports skipping the first 4 messages and storing the remaining 6 messages under the same label.
7. Verify that `sync_state` clears `gmail_store_run_label` upon successful run completion.
8. Re-run the command a third time to verify clean no-op termination with 0 stored messages and 10 skipped.

---

### Scenario C: Directory Source Mode (`.eml` tree)

This scenario validates restoring messages directly from a folder of `.eml` files.

#### Execution Workflow
1. Execute store-in-gmail specifying the exported `.eml` directory:
   ```powershell
   mail-utils store-in-gmail data/test-origin-export --account tester --db data/test-origin
   ```
2. Verify skipped counter increments for messages already marked as stored.
3. Test with a mix of valid `.eml` files and non-export `.eml` files lacking `X-Mail-Utils-ID`.
4. Confirm non-export files are logged and safely skipped without aborting the batch.

---

### Scenario D: Teardown and Cleanup

1. List and trash all test source messages:
   ```powershell
   python scripts/gmail-roundtrip-test.py cleanup --account tester --label mail-utils-roundtrip-test-source --apply
   ```
2. List and trash all restored messages under the generated tracking label:
   ```powershell
   python scripts/gmail-roundtrip-test.py cleanup --account tester --label <tracking-label-name> --apply
   ```
3. Clean local temporary test directories:
   ```powershell
   Remove-Item -Recurse -Force data/test-origin, data/test-origin-export, data/test-result, data/test-result-export
   ```

---

## 4. Pass / Fail Criteria

- **Zero Data Loss**: Decoded plain text and HTML bodies match verbatim.
- **Attachment Integrity**: Binary and text attachment SHA-256 digests match between origin and result.
- **Header Fidelity**: Sender, recipient, CC, BCC, subject, and date headers round-trip without corruption.
- **Resume Idempotency**: Interrupted runs resume cleanly with zero duplicate uploads in Gmail.
- **Clean Teardown**: All test labels and messages are moved to Trash with no persistent clutter.
