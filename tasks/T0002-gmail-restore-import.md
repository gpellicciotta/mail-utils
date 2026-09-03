---
id: T0002
title: "Gmail store command (write mail-utils-indexed mail back into Gmail)"
owner: claude
needs: []
branch: task/T0002-gmail-restore-import
worktree: ./work/T0002-gmail-restore-import
status: completed
started: 2026-08-27
ended: 2026-08-27
---

# T0002: Gmail store command (write mail-utils-indexed mail back into Gmail)

## Objectives & Scope

### Goal

Implement the Gmail-side restore path sketched in `docs/reverse-import-plan.md` (from T0001): a command
that writes mail-utils-indexed messages back into a live Gmail mailbox via the Gmail API, preserving
original date and labels as closely as the API allows. Shipped as `mail-utils store-in-gmail` (the task
slug/branch name still says "restore" - kept for id stability, see Progress & Validation Log for the rename
story).

This is a deliberate, user-approved exception to the project's read-only invariant (`CLAUDE.md`: *"Read-
only is a hard design invariant... Don't add write/send/delete capability without explicitly discussing
it first"*). The exception is scoped narrowly: only `store-in-gmail` requests write-capable scopes; every
other command keeps requesting `gmail.readonly` only, unchanged.

### Scope

Final scope, after two rounds of user feedback expanded it well beyond the original T0001 sketch:

- `config.py`/`auth.py`: `get_credentials()` accepts an explicit scopes list instead of always using the
  module-level `SCOPES`, so only `store-in-gmail` ever requests the broader `STORE_IN_GMAIL_SCOPES`
  (`gmail.insert` for `messages.import`; `gmail.labels` specifically for `labels.create`, confirmed via
  the Gmail API reference - `gmail.insert` alone does not cover label creation).
- `gmail_client.py`: `import_message(service, raw_bytes, label_ids)` wrapping `users.messages.import`
  (`internalDateSource="dateHeader"`, `neverMarkSpam=True`), and `create_label(service, name)`
  (`users.labels.create`).
- `gmail_store_state` table in `db.py` recording which local message ids have already been stored in
  Gmail (and the Gmail id they got), so reruns are idempotent - this is also the mechanism that makes an
  interrupted or `--max-messages`-capped run resumable by simply rerunning the same command.
- `cli.py`'s `store-in-gmail [<source_dir>]` subcommand:
  - **Dual source**: an EML export directory (`_eml_tree_candidates`) when `source_dir` is given, or the
    local database directly (`_db_candidates`, via `_build_eml_message` - the same builder `export
    --format eml` uses, factored out so both paths produce byte-identical RFC 5322 messages) when it's
    omitted. Explicitly restricted to these two mail-utils-native sources - never arbitrary foreign
    EML/mbox trees (per T0001's original recommendation, reaffirmed by the user).
  - **`--filter`**: same local filter grammar as `stats`/`export` (`_compute_matching_ids`), evaluated
    against the local database regardless of source.
  - **`--max-messages N`**: caps how many messages one run stores, then stops - safe because of the
    `gmail_store_state` tracking above.
  - **Per-run tracking label**: every message stored in a given run also gets a label unique to that run
    (`mail-utils-store-in-gmail-<UTC timestamp>`), so a whole batch is easy to find/review in Gmail
    afterwards. The timestamp is fixed for the whole run and persisted in `sync_state` the moment it's
    minted, cleared only once a run exhausts every candidate - so a `--max-messages`-capped or otherwise
    interrupted run continues under the *same* label on rerun instead of splitting across labels.
  - **Throttling + backoff**: `_throttle_gmail_store` paces `import_message` calls under Gmail's per-user
    quota (25 units/call, ~10 calls/sec ceiling - see T0001's research); `_gmail_call_with_backoff` retries
    with exponential backoff on a 429/rate-limited 403 so a transient burst doesn't abort the run.
  - **Explicit reporting**: every message stored is logged individually (`Stored <id> as Gmail message
    <new-id>`); the final summary always states counts and the last message successfully stored.
  - `--dry-run`: runs the same candidate/skip/filter logic without requesting credentials or calling the
    API - never touches `gmail_store_state`, only previews.
  - `--db <path>`: as with other commands, plus doubles as the message source when `source_dir` is
    omitted.
- Tests (`tests/test_gmail_client.py`, `tests/test_cli.py`): mock the Gmail service; cover label
  resolution/creation, idempotency, `--dry-run`, `--filter`, `--max-messages` + resumability, the tracking
  label, and the backoff/throttle helpers directly.
- Docs: `README.md`, `CLAUDE.md` (Commands + Architecture), `docs/cli-spec.md`'s `store-in-gmail` entry, `docs/requirements.md`,
  `docs/reverse-import-plan.md` (Open questions resolved), `CHANGELOG.md` `vNext`, `TODO.md` entry removed
  on completion.

### Out of Scope

- Attachment restoration - `mail-utils` never captures attachment bytes (metadata only), so stored
  messages are attachment-less regardless of source. Logged separately as **T0004** (backlog) rather than
  bundled into this task.
- Outlook (.pst) or Thunderbird restore - per T0001's findings, out of scope for this project entirely
  (third-party tools already cover Thunderbird for free; Outlook needs either a paid tool or a separate
  COM-automation script, neither of which belongs in this codebase).
- Restoring from arbitrary non-`mail-utils` EML/mbox sources that lack `X-Mail-Utils-*` metadata - the
  user explicitly confirmed the two supported sources are the EML export tree and the local database only.

### Dependencies

None (T0001 is complete; its findings are the basis for this task, not a blocking dependency).

### Completion Criteria

`store-in-gmail` works end-to-end against mocked tests from both sources, round-trips date/labels as
designed, is idempotent and resumable, applies its tracking label, respects `--filter`/`--max-messages`,
leaves every other command's OAuth scope request unchanged, and all docs/changelog/TODO updates land in
the single integration commit.

## Task Implementation and Verification Steps

- [x] [Implement] `auth.py`/`config.py`: scopes-override plumbing (`get_credentials(scopes=None)`,
  `STORE_IN_GMAIL_SCOPES`).
- [x] [Implement] `gmail_client.py`: `import_message`/`create_label`, unit-testable against a fake `service`.
- [x] [Implement] `db.py`: `gmail_store_state` table + `is_stored_in_gmail`/`mark_stored_in_gmail`.
- [x] [Implement] `cli.py`: `_build_eml_message` extracted from `_export_message_eml` (shared by both
  export and the database-source candidate builder); `_eml_tree_candidates`/`_db_candidates`;
  `_resolve_label_ids`; `_throttle_gmail_store`/`_gmail_call_with_backoff`; `_run_store_in_gmail` tying it
  together with `--filter`/`--max-messages`/`--dry-run`/the tracking label/per-message and summary logging.
- [x] [Verify] Unit tests for all of the above, mocking the Gmail API service object - no real Gmail
  account touched in CI, matching this project's existing convention for `import-gmail`. `time.sleep` is
  stubbed in tests exercising the throttle/backoff paths so the suite stays fast. `ruff check`/
  `ruff format`/`pytest`/`python -m build` all pass (151 tests, 2 pre-existing skips).
- [x] [Doc] Updated `README.md`, `CLAUDE.md`, `docs/cli-spec.md` (also fixed a pre-existing missing
  `### 2.8` heading for `schedule`/`unschedule`), `docs/requirements.md`, `docs/reverse-import-plan.md`
  (Open Questions resolved), `CHANGELOG.md`.
- [x] [Visual] N/A - no UI surface; CLI-only feature.
- Manual end-to-end verification against a disposable/sandbox Gmail account was flagged as the user's own
  responsibility (not something this task's CI-only test suite can do) - tracked separately, later executed
  for real in **T0013**.

## Progress & Validation Log

- 2026-08-27: Task claimed following user approval of the Gmail write-scope decision (from T0001's
  findings); worktree created, implementation starting.
- 2026-08-27: First cut implemented as `restore-gmail <source_dir>` (EML-tree source only, no filter/
  throttling/tracking label) - see git history on this branch for that intermediate state. Confirmed via
  the Gmail API Python client reference that the generated method name is `import_` (trailing underscore -
  `import` is a Python keyword) and that `users.labels.create` needs the `gmail.labels` scope specifically
  (`gmail.insert` alone doesn't cover it). Implemented `auth.get_credentials(scopes=None)` with a
  scope-coverage check (`set(scopes) <= set(creds.scopes)`) so a cached read-only token auto-triggers
  re-consent the first time the command runs, without affecting any other command's credential path.
- 2026-08-27: User reviewed the plan doc's open questions and gave targeted feedback in two rounds:
  (1) approved the scope decision and asked for two source modes (EML tree *or* local database, explicitly
  ruling out arbitrary foreign EML/mbox trees) and confirmed GYB isn't being used; separately flagged that
  full attachment capture is a real gap worth its own task (-> logged as **T0004**, not implemented here).
  (2) After seeing the first cut's naming (`restore-gmail`), asked to rename to `store-in-gmail` (flagged,
  and the user agreed, that `import-into-gmail` was one word away from the existing opposite-direction
  `import-gmail` command - too easy to mix up), and requested `--max-messages` plus explicit per-message/
  summary reporting of what was stored and the last successful message, framed around resumability.
  Implemented all of it: renamed every identifier consistently (`STORE_IN_GMAIL_SCOPES`,
  `gmail_store_state`, `is_stored_in_gmail`/`mark_stored_in_gmail`, `_run_store_in_gmail`, etc.), added
  `_db_candidates` (reusing `_build_eml_message`, newly extracted from `_export_message_eml` so both paths
  produce identical message bytes), `--filter` (reusing `_compute_matching_ids`), `--max-messages` with a
  "stopped after reaching cap" log line, the per-run tracking label, `_throttle_gmail_store`/
  `_gmail_call_with_backoff` for quota safety, and per-message + final-summary logging naming the last
  message stored. Rewrote the test suite accordingly (dual-source dry-runs, filter restriction, max-messages
  + resumability across two runs, tracking-label assertion, backoff-retry and throttle unit tests via a
  fake Gmail service with an injectable failure count). Updated all docs (`README.md`, `CLAUDE.md`,
  `docs/cli-spec.md` - also fixed a pre-existing missing `### 2.8` heading for `schedule`/`unschedule` while
  adding the adjacent section, `docs/requirements.md`, `docs/reverse-import-plan.md`'s Open Questions/plan
  sections marked resolved, `CHANGELOG.md`). Full suite (150 tests, 2 pre-existing skips), `ruff check`,
  `ruff format --check`, and `python -m build` all pass. Manually smoke-tested `store-in-gmail --dry-run`
  against both a hand-built EML fixture and directly against an empty local database.
- 2026-08-27: Noted (not fixed, out of scope): `_run_store_in_gmail` inherits a pre-existing gap also
  present in `_run_import_pst`/`_run_import_thunderbird` - `init_db()` raises an unhandled
  `sqlite3.OperationalError` traceback instead of a friendly message when the default `data/` directory
  doesn't exist yet (e.g. a truly fresh checkout). Filed as **A0005** in `TODO.md`.
- 2026-08-27: User caught a real gap in the tracking label: it was minting a fresh timestamp on every
  invocation, so a `--max-messages`-capped or interrupted run would continue under a *different* label
  than the one it started with, scattering one logical batch across several labels. Fixed by persisting
  the run's label name in `sync_state` (`_get_or_start_gmail_store_run_label`/`_GMAIL_STORE_RUN_LABEL_KEY`)
  the moment it's first needed, and only clearing it (`_finish_gmail_store_run`) once a run goes through
  every remaining candidate without being cut short by `--max-messages` - an outright crash/Ctrl-C never
  reaches that clear step either, so it also correctly leaves the label in place for the next rerun to
  continue. Label creation itself also moved from eager (once per invocation) to lazy (only right before
  the first actual store), so a no-op rerun with nothing left to store no longer creates an empty label.
  Added `test_run_store_in_gmail_max_messages_stops_early_and_is_resumable`'s extended assertions (same
  label id used by both the capped run and its continuation, and the run marker cleared in `sync_state`
  afterwards) plus a new `test_run_store_in_gmail_starts_a_new_tracking_label_after_a_run_completes` (a
  fake, incrementing `datetime.now()` clock is monkeypatched in so this test's two independent runs
  reliably mint two *different* label timestamps regardless of how fast the test itself executes). Full
  suite now 151 tests, 2 pre-existing skips; `ruff check`/`ruff format --check`/`python -m build` all still
  pass. Updated `CLAUDE.md` and `docs/cli-spec.md` to describe the persistence behavior.
- `pytest` (worktree venv): 151 passed, 2 skipped. `ruff check .`: all checks passed. `ruff format --check
  .`: all files already formatted. `python -m build`: sdist and wheel built successfully. Manual smoke
  tests: `store-in-gmail --dry-run` against a hand-built `.eml` export directory, and separately with
  `source_dir` omitted against an empty local database - both reported correctly without contacting Gmail
  or requesting credentials. No real Gmail account was exercised (by design). No separate reviewer
  available (solo, AI agent) - per the Review Tiers table, findings were presented to the human user for
  explicit permission before integration, same as T0001.

## Completion Record

Reviewed and approved by the user on 2026-08-27 (solo, AI agent - no separate reviewer), across three
rounds of feedback (source modes/GYB/attachments; naming/max-messages/reporting; tracking-label
persistence). Integrated into `main` the same day. Real-mailbox verification against a disposable/sandbox
Gmail account was explicitly called out as the user's own responsibility (not something this task's CI-only
test suite can do) - tracked separately as **A0006** in `TODO.md`, later executed for real in **T0013**.
