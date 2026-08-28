# T0013: Safe end-to-end Gmail testing, with a path to production rollout

- **Status:** Completed
- **Owner:** claude
- **Started:** 2026-08-28
- **Branch:** task/T0013-gmail-e2e-safety-and-rollout
- **Worktree:** ./work/T0013-gmail-e2e-safety-and-rollout

## Goal

Establish a safe, repeatable way to run mail-utils's full read/write cycle — especially `store-in-gmail`,
the one write-capable command — end-to-end against real Gmail infrastructure, starting with a disposable
test account, and use that to define the concrete safeguards, go/no-go criteria, and recovery plan needed
before ever pointing mail-utils at the user's real production mailbox
(`giovanni.pellicciotta@gmail.com`). Promoted from **A0012** because it needs a dedicated plan, not a
one-sitting fix — see that entry's cancellation note.

A disposable test account already exists: **`katsan.pellicciotta@gmail.com`**.

## Scope

- **Test/production isolation.** Today `config.py`'s `CREDENTIALS_PATH`/`TOKEN_PATH`/`DB_PATH` are all
  fixed under the single `data/` directory (see `config.py`, `auth.py::get_credentials`) — there is no
  per-run override for credentials/token, only `--db` for the database. Decide and set up how the test
  account's OAuth consent/token stay fully separate from the real account's (candidates: a manual
  swap-the-files procedure, a second `--data-dir`/`--profile`-style checkout, or small `--credentials`/
  `--token` CLI overrides) — see Approach.
- **Risk-tiering.** Document explicitly: read-only commands (`import-gmail`, `search`, `stats`, `export`)
  are safe to run directly against any mailbox, including production, because `gmail.readonly` cannot
  write, label, or delete anything. `store-in-gmail` is the only command that needs the isolation/testing
  below before it touches a real mailbox.
- **Real E2E validation**, executing **A0006**'s checklist against `katsan.pellicciotta@gmail.com` for
  real (not mocked): OAuth consent requests exactly `gmail.insert` + `gmail.labels` on top of the existing
  `gmail.readonly`; stored messages land with correct dates/labels/tracking label; `--max-messages` +
  rerun actually resumes cleanly; throttling/backoff behave sanely under the real API's quota and error
  responses.
- **Recovery playbook**: how to find everything a `store-in-gmail` run wrote (its per-run tracking label,
  cross-checked against the `gmail_store_state` table — see `db.py`), how to bulk-select and delete/trash
  those messages from Gmail if a run needs to be undone, and what mail-utils's write path does and does not
  touch (it only ever calls `messages.import`/`labels.create` — it never modifies or deletes anything that
  was already in the mailbox, so recovery is scoped to "messages this tool itself wrote").
- **Go-live checklist**: the specific, concrete conditions that must hold before running `store-in-gmail`
  (or any command, as a formality) against `giovanni.pellicciotta@gmail.com`.
- **Tool safety nets (decide, don't assume)**: discuss with the user whether anything belongs in the tool
  itself — e.g. printing the target account's email address before a write run so a wrong token file is
  caught by eye, or another lightweight guard — and record the decision. Only implement what's agreed;
  don't add speculative flags nobody asked for.
- **Byte-level round-trip validation** (added after user follow-up): a stronger check than the basic
  checklist above - seed varied test messages (attachments, HTML/unicode bodies), sync with
  `--with-attachments` ("origin env"), export, `store-in-gmail`, re-sync the result ("result env"),
  re-export, and compare origin vs. result (SQLite excluding id/labels-diff/timestamps, and export
  directories byte-level via decoded content) to prove no data loss. Repeated once for reproducibility.

## Out of Scope

- Actually running `store-in-gmail` against `giovanni.pellicciotta@gmail.com`. That stays a separate,
  explicitly user-approved action once this task's criteria are met — this task produces the checklist and
  playbook, it doesn't itself pull the trigger on production.
- Any new feature work unrelated to test/production safety.

## Dependencies

None (supersedes **A0012**). **A0006** depends on this task's real-account E2E execution.

## Approach

1. Decide the test/production isolation mechanism (manual file-swap vs. CLI overrides vs. separate data
   dir) and set it up well enough to run commands against `katsan.pellicciotta@gmail.com` without any risk
   of accidentally touching the real token/credentials.
2. Run the OAuth consent flow against `katsan.pellicciotta@gmail.com`; confirm the exact scopes granted
   match `STORE_IN_GMAIL_SCOPES`.
3. Execute A0006's checklist for real against the test account (dates/labels/tracking label correctness,
   `--max-messages` + resume, throttling/backoff under the live API).
4. Write up the recovery playbook based on what's actually observed in step 3.
5. Write up the go-live checklist and get the user's explicit sign-off criteria.
6. Present findings/checklists/playbook to the user for review (solo, AI agent tier) before this task is
   marked complete.

## Implementation Checklist

- [x] Test/production credential isolation approach decided and set up
- [x] OAuth consent run against `katsan.pellicciotta@gmail.com`; scopes confirmed
- [x] A0006 checklist executed and passed against the test account
- [x] Recovery playbook documented
- [x] Go-live checklist documented
- [x] Byte-level round-trip validation (scripts/gmail-roundtrip-test.py) built and passed twice against the test account
- [x] User review and sign-off

## Test Strategy

Manual, real-API verification against the disposable test account — this task exists specifically to
validate real Gmail API behavior that mocked unit tests (T0002's approach) can't cover, so there is no CI
angle here. Any code changes made for credential isolation (if that route is chosen) get their own unit
tests per the project's normal convention.

## Completion Criteria

A0006's checklist has been executed and passed against `katsan.pellicciotta@gmail.com`; a recovery
playbook and a go-live checklist both exist as docs; the user has explicitly reviewed and signed off on
both. Running against the real production mailbox is intentionally not part of this task's completion bar
(see Out of Scope).

## Progress Log

- 2026-08-28: Task claimed, worktree created. Confirmed `config.py::BASE_DIR` is computed relative to
  `config.py`'s own file location, so this worktree already gets its own independent `data/` directory
  (`work/T0013-gmail-e2e-safety-and-rollout/data/`), fully separate from the main checkout's `data/` —
  isolation between the test account and production requires **no code change**, just running commands
  from inside this worktree. Verified via `python -c "from mail_utils.config import DATA_DIR, ..."`.
  Copied the main checkout's `data/credentials.json` (the OAuth *client secret* — app-level, not tied to
  any one Google account) into this worktree's `data/`; deliberately did **not** copy `data/token.json`
  (that's the production account's authorized token). Created a dedicated `.venv` here and installed
  `mail-utils` in editable mode. Marking Implementation Checklist item 1 (isolation approach) done.
  Next step (running the OAuth consent flow against `katsan.pellicciotta@gmail.com`) is inherently
  interactive — it opens a browser for Google sign-in/consent, which only the user can complete.
- 2026-08-28: User hit `Error 403: access_denied` ("Adhoc Utilities has not completed the Google
  verification process") on first consent attempt — the OAuth client is in Testing publishing status in
  Google Cloud Console, so only accounts on the explicit Test users list can complete consent, and
  `katsan.pellicciotta@gmail.com` wasn't on it. Fixed by the user adding that address under **APIs &
  Services → OAuth consent screen → Audience → Test users** in the Cloud project that owns
  `credentials.json` — no new project/client needed, same client just needed the tester whitelisted.
  Worth carrying into the go-live checklist: confirms the app itself is still unverified/testing-only, so
  the same test-user requirement would apply to any other account too (not a production-readiness signal
  either way, just a prerequisite to remember). Re-ran `mail-utils import-gmail` from the worktree
  afterwards — consent succeeded, `data/token.json` minted scoped to this worktree only, 13 messages
  synced into the isolated `data/gmail.db` (`mail-utils stats` confirms: 13 messages, 10 threads, all To
  `katsan.pellicciotta@gmail.com` as expected). Confirms OAuth consent flow and read-only sync work
  correctly against the test account with full isolation from production.
- 2026-08-28: Ran `store-in-gmail --dry-run` against the test account's local DB first (13 candidates,
  no API calls) to sanity-check candidate selection before touching the live mailbox. With user approval,
  ran `store-in-gmail --max-messages 3` for real and hit `HttpError 403: Insufficient Permission` from
  `labels.create` — despite the run apparently going through a consent step. Investigated: `data/token.json`
  still only recorded `gmail.readonly` after the "failed" run, meaning no fresh consent had actually
  happened at all. Root-caused to a genuine bug in `auth.py::get_credentials`: it called
  `Credentials.from_authorized_user_file(str(TOKEN_PATH), scopes)`, and the underlying `google-auth`
  library (confirmed by reading `Credentials.from_authorized_user_info`'s source) treats an explicit
  `scopes` argument as an *override*, replacing whatever the token file actually recorded rather than
  filtering/validating against it. So `creds.scopes` was always forced to equal the requested scopes,
  making the coverage check `set(scopes) <= set(creds.scopes)` trivially true regardless of what the
  cached token was really authorized for — a stale readonly-only token silently passed as if it already
  covered `STORE_IN_GMAIL_SCOPES`, and the real API rejected the resulting write call. This bug is not
  specific to the test account or this worktree — it would have hit identically on first production use of
  `store-in-gmail`. Fixed by dropping the `scopes` argument from the `from_authorized_user_file` call so
  `creds.scopes` reflects what the token was actually granted. Added `tests/test_auth.py` (previously no
  test file existed for `auth.py` at all): one test confirming a token that already covers the requested
  scopes is reused, and a regression test confirming a token with narrower scopes triggers a fresh consent
  flow rather than being silently accepted — confirmed this second test fails against the pre-fix code and
  passes after. Full suite (179 tests, 2 pre-existing skips), `ruff check`, `ruff format --check` all pass.
  Deleted the worktree's stale `data/token.json` and reran `store-in-gmail --max-messages 3`: a real fresh
  consent prompt appeared this time, requesting exactly `gmail.readonly` + `gmail.insert` + `gmail.labels`
  (visible in the printed auth URL's `scope=` parameter); 3 messages stored under a new tracking label
  (`mail-utils-store-in-gmail-2026-08-28T08-45-36Z`). Reran with no cap: resumed under the *same* tracking
  label, stored the remaining 10, 3 correctly skipped as already-stored. Reran once more with nothing left:
  0 stored, 13 skipped (idempotent). Verified `sync_state.gmail_store_run_label` was cleared after the
  batch completed (confirms the label-persistence/clearing logic from T0002). Cross-checked one round-
  tripped message via a direct Gmail API `messages.get`: `internalDate` matched the original
  `internal_date_ms` exactly (`1639748823000`), and its labels showed the original `CATEGORY_UPDATES` plus
  the tracking label, confirming both date and label round-tripping work correctly against the real API.
  This fully satisfies A0006's checklist against the test account.
- 2026-08-28: Wrote up the isolation setup, recovery playbook (tracking label + `gmail_store_state`
  cross-check, Gmail search-by-label, Trash vs. permanent delete), and a go-live checklist as a new
  "Gmail Testing, Isolation, and Recovery" section in `docs/devops.md`, per the project convention of
  putting operational procedures there. Still open: whether to add a tool-level safety net (e.g. printing
  the authenticated account's email before a live write run) — flagged for the user per the Scope section's
  "decide, don't assume" note, not implemented yet.
- 2026-08-28: User confirmed the safety net should be added. Implemented: `_run_store_in_gmail` now calls
  `gmail_client.get_profile` (already existed, previously unused there) right after building the service
  and logs `Target account: <email>` before any write happens. Updated `_FakeUsers` in `tests/test_cli.py`
  with a `getProfile` stub (previously missing entirely, which broke 5 existing store-in-gmail tests once
  the new call was added) and asserted the new log line in the main end-to-end test. Full suite (177
  passed, 2 skipped), `ruff check`, `ruff format --check` all pass. Verified live against
  `katsan.pellicciotta@gmail.com`: printed `Target account: katsan.pellicciotta@gmail.com` correctly.
  Updated `CLAUDE.md`, `docs/cli-spec.md`, and the go-live checklist in `docs/devops.md` to reference it.
- 2026-08-28: User asked for a much stronger E2E check: seed varied messages (attachments, HTML/unicode
  bodies), sync with `--with-attachments` into an "origin env" DB+export, `store-in-gmail`, re-sync the
  result into a "result env" DB+export, and diff origin vs. result (SQLite excluding id/tracking-label/
  timestamps, filesystem byte-level via decoded content since raw MIME boundaries are randomly generated
  on every serialization and can't be diffed as literal bytes), repeated for reproducibility. Answered:
  no, this hadn't been done (only a 1-message/2-field spot check had); yes, needed for real confidence
  (attachment round-tripping had never been tested against a real mailbox); repeat twice, not three times
  (identical reruns mostly re-exercise the same deterministic code path - better spent on message variety
  than repeat count). Built `scripts/gmail-roundtrip-test.py` (`seed`/`compare`/`cleanup` actions,
  version/help per CLI guidelines) per the user's choice to keep it as a reusable regression tool rather
  than a throwaway script. `seed` builds 5 messages independently of `_build_eml_message` (the code under
  test) - plain text, one PNG attachment, HTML body with unicode, two attachments with a unicode subject,
  and one ~256KB attachment - and inserts them directly via the Gmail API. `cleanup` needed its own
  `gmail.modify`-scoped consent (store-in-gmail's scopes don't cover trash) and deliberately never supports
  permanent delete (would need the much broader `https://mail.google.com/` scope). `compare` pairs
  origin/result messages by (subject, date) and diffs everything else, since ids/threads change.
  First real run found two bugs: (1) a Windows console encoding crash printing a unicode subject mid-`seed`
  (fixed: `sys.stdout.reconfigure(encoding="utf-8")`), and (2) a genuine, real fidelity bug - a Subject
  header needing RFC 2047 encoding right after existing whitespace gained one extra space on every export/
  store round-trip (`email.policy.default`'s header folding duplicates the whitespace it folds on).
  First fix attempt (`utf8=True`, raw UTF-8 headers instead of encoded-words) solved it locally but a
  second real-API run showed it corrupts non-ASCII header bytes in transit (mojibake) - reverted. Correct
  fix: `max_line_length=None` at message-*generation* time only (the shared `_email_policy_default`
  constant in `cli.py`), which disables folding while keeping RFC 2047 encoded-words and leaving already-
  encoded body/attachment content untouched. Added a regression test in `tests/test_cli.py` that doesn't
  need a real account (confirmed it fails on the pre-fix code, passes after). Two independent
  `store-in-gmail` runs from the same origin (for reproducibility) both produced a clean `compare` PASS
  against the live test account: byte-exact attachment content (sha256-verified), addresses, labels
  (minus the tracking label), and now-correct subjects. This is real, meaningful proof against data loss -
  well beyond the earlier spot-check - and it caught a bug the lighter checklist would have missed.

## Validation Record

- `pytest` (worktree venv): 178 passed, 2 skipped.
- `ruff check .`: all checks passed.
- `ruff format --check .`: all files already formatted.
- `python -m build`: sdist and wheel built successfully.
- Real end-to-end runs against `katsan.pellicciotta@gmail.com` (disposable test account, isolated via this
  worktree's own `data/` directory): `import-gmail` (read-only sync, 13 messages), `store-in-gmail --dry-run`,
  `store-in-gmail --max-messages 3` (fresh consent with exactly the expected scopes, after fixing the
  scope-caching bug), an uncapped rerun (resumed under the same tracking label, stored the remaining 10),
  a third rerun (idempotent, 0 stored), and a `messages.get` cross-check confirming exact date/label
  round-tripping. No automated CI coverage of real Gmail API calls, by design (matches T0002's convention
  and this task's own reason for existing) — this task itself *is* the manual real-API verification T0002
  flagged as the user's responsibility.
- Byte-level round-trip (`scripts/gmail-roundtrip-test.py`), against `katsan.pellicciotta@gmail.com`, run
  twice independently from the same origin: both produced `PASS: 5 messages compared, no differences
  found` — SQLite fields (sender/recipient/cc/bcc/body/dates/labels-minus-tracking/attachments/addresses)
  and export-directory decoded content (subject/headers/body/attachment bytes, sha256-equal) all matched
  exactly between origin and result. This is what caught and confirmed the fix for the Subject
  header-folding bug (see Progress Log) — a stronger, byte-level guarantee than the checklist item above.
- No separate reviewer available (solo, AI agent) — per the Review Tiers table, findings are being
  presented to the human user for explicit permission before integration.

## Completion Record

Reviewed and approved by the user on 2026-08-28 (solo, AI agent — no separate reviewer available). Real
end-to-end testing against `katsan.pellicciotta@gmail.com` found and fixed two genuine bugs no mocked test
had caught: `auth.py`'s OAuth scope-coverage check silently accepting a token that didn't actually cover
the requested write scopes, and a Subject header round-trip bug in `_build_eml_message`'s header folding.
Also delivered the recovery playbook, go-live checklist, target-account safety net, and a reusable
`scripts/gmail-roundtrip-test.py` tool per the user's follow-up request for byte-level round-trip proof
beyond the original checklist. That deeper testing additionally surfaced a real, pre-existing, separate
content-fidelity gap (HTML body content and inline images silently dropped in favor of a plain-text
alternative) — logged as **T0014** rather than folded into this task's scope, per explicit user decision.
Test mailbox cleaned up (all seeded/stored test messages trashed) before integration. Integrated into
`main` the same day.
