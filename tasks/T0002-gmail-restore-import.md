# T0002: Gmail restore command (write mail from `mail-utils export` output back into Gmail)

- **Status:** active
- **Owner:** claude
- **Started:** 2026-08-27
- **Branch:** task/T0002-gmail-restore-import
- **Worktree:** ./work/T0002-gmail-restore-import

## Goal

Implement the Gmail-side restore path sketched in `docs/reverse-import-plan.md` (from T0001): a new
`mail-utils restore-gmail <path>` command that walks a directory of `mail-utils export --format eml`
output and writes those messages back into a live Gmail mailbox via the Gmail API, preserving original
date and labels as closely as the API allows.

This is a deliberate, user-approved exception to the project's read-only invariant (`CLAUDE.md`: *"Read-
only is a hard design invariant... Don't add write/send/delete capability without explicitly discussing
it first"*). The exception is scoped narrowly: only `restore-gmail` requests write-capable scopes: every
other command keeps requesting `gmail.readonly` only, unchanged.

## Scope

- `config.py`/`auth.py`: make `get_credentials()` accept an explicit scopes list instead of always using
  the module-level `SCOPES`, so only `restore-gmail` ever requests the broader set. Add
  `RESTORE_SCOPES = SCOPES + ["https://www.googleapis.com/auth/gmail.insert", "https://www.googleapis.com/auth/gmail.labels"]`
  (`gmail.insert` for `messages.import`; `gmail.labels` specifically for `labels.create`, confirmed via
  the Gmail API reference — `gmail.insert` alone does not cover label creation).
- `gmail_client.py`: add `import_message(service, raw_bytes, label_ids, internal_date_source="dateHeader")`
  wrapping `users.messages.import` with `neverMarkSpam=True`, and `ensure_label(service, name)` (get-or-
  create via `labels.list`/`labels.create`) for translating `X-Mail-Utils-Labels` names back to label IDs.
- New `restore_state` table in `db.py` (mirrors `sync_state`'s shape) recording which `X-Mail-Utils-ID`
  values have already been restored, so re-running the command is idempotent.
- `cli.py`: new `restore-gmail <path>` subcommand — walks the given directory for `.eml` files (reuse the
  directory-walk shape `import-thunderbird` already has), parses each with `email.message_from_bytes`,
  reads `X-Mail-Utils-ID`/`X-Mail-Utils-Labels` headers, skips any id already in `restore_state`, calls
  `gmail_client.import_message`, records the id on success. Accepts `--db <path>` like the other commands
  (for the idempotency table) and a `--dry-run` flag that reports what would be restored without calling
  the API.
- Tests (`tests/test_gmail_client.py`, `tests/test_cli.py`): mock the Gmail service the same way existing
  Gmail tests do; verify label resolution/creation, `internalDateSource`/`neverMarkSpam` are set correctly
  on the API call, idempotency (a second run skips already-restored ids), and `--dry-run` makes no API
  calls.
- Docs: `README.md` (Setup/Commands + a new note that this command requests additional scopes),
  `CLAUDE.md` (Commands + Architecture sections), `docs/cli-spec.md`, `docs/index.md` if a note is
  warranted, `CHANGELOG.md` `vNext` entry, remove this item from `TODO.md` on completion.

## Out of Scope

- Attachment restoration (nothing to restore — `mail-utils` never captures attachment bytes; see
  `docs/reverse-import-plan.md`'s tl;dr).
- Outlook (.pst) or Thunderbird restore — per T0001's findings, out of scope for this project (third-party
  tools already cover Thunderbird for free; Outlook needs either a paid tool or separate COM-automation
  script, neither of which belongs in this codebase).
- Restoring from arbitrary non-`mail-utils` EML/mbox sources that lack `X-Mail-Utils-*` headers — first
  cut targets `mail-utils export --format eml` output specifically. Best-effort fallback parsing for
  foreign `.eml` files (no `X-Mail-Utils-Labels`, just `Date`/headers) can be a fast-follow if needed.

## Dependencies

None (T0001 is complete; its findings are the basis for this task, not a blocking dependency).

## Approach

1. `auth.py`: change `get_credentials(scopes: list[str] = SCOPES)` signature; keep default behavior
   identical for every existing caller (they don't pass `scopes`, so nothing changes for them).
2. `config.py`: add `RESTORE_SCOPES` alongside the existing `SCOPES`, with a comment explaining why it's
   separate and only used by one command.
3. `gmail_client.py`: add `import_message`/`ensure_label`, unit-testable with a mocked `service` the same
   way `list_labels`/`fetch_message` already are.
4. `db.py`: add `restore_state` table + `is_restored`/`mark_restored` helpers.
5. `cli.py`: add the `restore-gmail` subcommand, argument parsing, and the walk/parse/restore loop with
   the same progress-logging convention (`PROGRESS_LOG_INTERVAL`) other commands use.
6. Tests for all of the above, run `ruff check`/`ruff format` and the full suite.
7. Update `README.md`, `CLAUDE.md`, `docs/cli-spec.md`, `CHANGELOG.md` (`vNext`), remove `TODO.md` entry.
8. Present to the user for review (solo/AI-agent tier) before integrating — this changes the OAuth
   consent surface, so flag that explicitly in the summary, and note real-mailbox testing against a
   disposable/sandbox account is the user's own responsibility before relying on it (not something this
   task can validate in CI).

## Implementation Checklist

- [ ] `get_credentials()` accepts an explicit scopes override.
- [ ] `RESTORE_SCOPES` added to `config.py`.
- [ ] `gmail_client.import_message` + `ensure_label` implemented and unit tested.
- [ ] `restore_state` table + helpers in `db.py`.
- [ ] `restore-gmail` subcommand in `cli.py` (including `--dry-run`, `--db`).
- [ ] Idempotency verified (second run skips already-restored messages).
- [ ] `ruff check` / `ruff format --check` / `pytest` all pass.
- [ ] Docs updated (`README.md`, `CLAUDE.md`, `docs/cli-spec.md`, `CHANGELOG.md`).

## Test Strategy

Unit tests only, mocking the Gmail API service object — no real Gmail account is touched in CI, matching
this project's existing convention for the `import-gmail` path. Manual end-to-end verification against a
disposable Gmail account is called out as the user's responsibility in the Validation Record before this
is trusted against a real mailbox.

## Completion Criteria

`restore-gmail` works end-to-end against mocked tests, round-trips date/labels as designed, is idempotent,
leaves every other command's OAuth scope request unchanged, and all docs/changelog/TODO updates land in
the single integration commit.

## Progress Log

- 2026-08-27: Task claimed following user approval of the Gmail write-scope decision (from T0001's
  findings); worktree created, implementation starting.

## Validation Record

(pending)

## Completion Record

(pending)
