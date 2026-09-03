---
id: T0015
title: "Named Gmail account files and a prepare-gmail-account command"
owner: claude
needs: []
branch: task/T0015-gmail-account-management
worktree: ./work/T0015-gmail-account-management
status: completed
started: 2026-08-28
ended: 2026-08-28
---

# T0015: Named Gmail account files and a `prepare-gmail-account` command

## Objectives & Scope

### Goal

Give mail-utils a first-class, repeatable way to set up and switch between multiple named Gmail accounts
(disposable test accounts, and eventually production), replacing today's ad hoc, worktree-only isolation
mechanism (see `docs/devops.md`'s "Testing against a disposable account, isolated from production",
written during **T0013**). Concretely: a dedicated CLI action that produces one self-contained,
per-account credential file, a `--account` flag other commands use to select which one to authenticate
as, and a `--db` flag that scopes a run's database *and* attachment cache together - with account
selection and data-storage location kept fully independent of each other.

Also triggered by, and in scope for, a rename: the disposable test account used throughout T0013
(`katsan.pellicciotta@gmail.com`) should become `tester.pellicciotta@gmail.com` going forward. How that
rename is actually carried out (see Scope) depends on decisions this task needs to make first, so it's
folded in here rather than done as a quick standalone edit.

### Scope

**Design (confirmed with the user on 2026-08-28):**

- **Account rename:** `tester.pellicciotta@gmail.com` is a brand-new, separate disposable account - not a
  rename/alias of `katsan.pellicciotta@gmail.com`. It needs its own from-scratch setup (Cloud Console
  Test-user whitelisting, fresh OAuth consent), same as `katsan.pellicciotta@gmail.com` originally did in
  T0013. `katsan.pellicciotta@gmail.com` references already committed stay as an accurate historical
  record: `tasks/T0013-gmail-e2e-safety-and-rollout.md` is a **completed** task's log documenting what was
  actually run - left untouched. Only the live, forward-looking `scripts/gmail-roundtrip-test.py`
  (hardcodes `katsan.pellicciotta@gmail.com` as the seeded messages' `To:` address) gets updated -
  parameterized to accept the target account's address rather than hardcoding either one.
- **Command shape:** a flat `prepare-gmail-account <name>`, matching the existing flat command style
  (`import`, `stats`, ...) rather than introducing a new `account` subcommand namespace.
- **Backward compatibility** with the old flat, unnamed credential/token/database layout is explicitly not
  a concern for this task - free to land the cleanest layout without a migration path or dual-mode
  fallback.
- **Accounts and data storage are decoupled.** An account file identifies *who mail-utils authenticates
  as*; `--db` identifies *where a run's data lives*. Neither implies the other - any account can be used
  with any `--db` location, and switching database doesn't require switching account.
- **App credential file** (the OAuth client secret identifying the *application*, not any one Google
  account) is renamed to the more self-explanatory
  `data/google-cloud-mail-utils-app-credentials.json`. It stays a single shared file - the same client
  already consents multiple accounts today (T0013 reused it as-is for `katsan.pellicciotta@gmail.com`
  alongside the production account) - obtained once via the Google Cloud Console walkthrough documented in
  `README.md`'s Setup section, which gets updated to reference the new filename.
- **Account file:** one self-contained JSON file per authorized Gmail account (structurally what
  `token.json` held before), named `<name>-account.json`. Default location `data/<name>-account.json`; a
  value containing a path separator or explicit `.json` extension is used verbatim as the file path instead
  (`--account a/b/c-account.json`). No directory nesting, no bundled database/attachments - just the one
  file.
- **`--account` flag**, added to every Gmail-API-touching command (`import`, `import-gmail`,
  `store-in-gmail`, and whatever `schedule`/`unschedule` wrap that includes those):
  - `--account xxx` -> `data/xxx-account.json`.
  - `--account a/b/c-account.json` -> that exact path.
  - Omitted -> falls back to `data/default-account.json` if it exists; otherwise the command errors
    clearly, asking for `--account` to be specified.
- **`prepare-gmail-account <name>`:** resolves its target path the same way `--account` does, requires
  `data/google-cloud-mail-utils-app-credentials.json` to already exist (clear error pointing at the docs
  otherwise), runs the interactive consent flow, writes the resulting token to that account file, and
  prints the authenticated address (via the existing `get_profile` call) so the user can eyeball-confirm
  they signed into the intended account. Requests read-only `SCOPES` by default; a `--with-write` flag
  requests `STORE_IN_GMAIL_SCOPES` instead, for accounts being set up specifically to test
  `store-in-gmail`.
- **`--db` becomes a directory, not a file.** `--db <dir>` creates `<dir>` if missing and scopes both the
  database and the attachment cache inside it: `<dir>/mails.db` + `<dir>/attachments/`. Renamed from
  `gmail.db` to `mails.db` - the database isn't Gmail-specific (PST/Thunderbird imports land in it too).
  This directly fixed a latent gap in the previous code: `config.py`'s attachments directory was a single
  fixed global path with **no** `--db`-style override, so two different databases already selected via
  `--db` silently shared one attachment cache; scoping attachments inside the same directory as the
  database they belong to closes that.

**Docs updated once implemented:** `README.md`'s Setup walkthrough, `docs/devops.md`'s "Gmail Testing,
Isolation, and Recovery" section, `docs/cli-spec.md`, `CLAUDE.md`'s architecture notes.

### Out of Scope

- Actually running any new setup against `giovanni.pellicciotta@gmail.com` (production) - this task is
  about the tooling and the disposable test account only.
- Multi-account *concurrent* operation (e.g. one command touching several accounts in a single run).
  Scope here is one account at a time, selected explicitly.

### Dependencies

None. Builds on the isolation groundwork and safety-net conventions established in **T0013**
(`get_profile` target-account logging, the worktree-based isolation this task aims to make explicit).

### Completion Criteria

The account-file/app-credential-file split, `--account` resolution, and directory-based `--db` are
implemented and tested; `prepare-gmail-account` works end-to-end; the rename is applied per the agreed
approach; docs reflect the new setup flow; the user has reviewed and approved before integration.

## Task Implementation and Verification Steps

- [x] [Decide] Confirmed the design via chat with the user (rename handling, decoupled account/data-storage
  model, `mails.db` filename) before starting.
- [x] [Implement] `config.py`'s `resolve_account_path`/`resolve_db_dir`/`db_path_for`/
  `attachments_dir_for` and `APP_CREDENTIALS_PATH`, replacing the old fixed constants. Refactored
  `auth.py::get_credentials` to take explicit `account_path`/`app_credentials_path` arguments. Made
  `attachment_store.py` take a `configure(attachments_dir)` call instead of importing a fixed constant,
  called once per CLI run from `cli.py::_resolve_db_path`, so all 7 of its existing call sites picked up
  correct per-directory attachment scoping with no further changes needed at those sites.
- [x] [Implement] `prepare-gmail-account <name>` (`--with-write` for `STORE_IN_GMAIL_SCOPES`, read-only
  default) and `--account` threaded through `import`, `import-gmail`, `store-in-gmail`. `schedule`/
  `unschedule` needed no separate change since `schedule` already validates its inner command against the
  same `build_parser()` that now includes `--account`. Updated `_run_import`'s Gmail-fallback detection to
  check `APP_CREDENTIALS_PATH`/the resolved account file instead of the old fixed paths.
- [x] [Implement] Updated `scripts/migrate-gmail-id-prefix.py` (a separate one-off script, importing the
  now-removed fixed-path constant for its default) and `scripts/gmail-roundtrip-test.py` (added `--account`/
  `--to`, parameterizing the previously-hardcoded `katsan.pellicciotta@gmail.com` seed recipient).
- [x] [Verify] Updated all affected tests (`test_config.py`, `test_auth.py`, `test_attachment_store.py`,
  `test_cli.py`, `test_pst_integration.py`, `test_search.py`, `test_thunderbird.py`,
  `test_thunderbird_integration.py`, `test_recursive_import.py`) to the new explicit-path/directory
  conventions, replacing fixed-constant monkeypatches (no longer possible) with passing `db=str(tmp_path)`
  through `argparse.Namespace` the same way real CLI invocations do. Full suite: 187 passed, 2 skipped.
  `ruff check`/`ruff format --check` clean. Manually smoke-tested `prepare-gmail-account --help`,
  `import-pst --db <dir>` (confirmed `<dir>/mails.db` created), and `stats --db <dir>` against the result.
- [x] [Doc] Updated `README.md` (Database contents, Key Features, Quickstart), `docs/tutorial.md` (Gmail
  sync now mentions `prepare-gmail-account` first), `docs/cli-spec.md` (new `prepare-gmail-account` entry,
  `--account` on every Gmail-API command, `--db` semantics, new reference sections), `docs/devops.md` (new
  "Gmail Account Setup" section with the Google Cloud Console walkthrough for the app credential file plus
  the `prepare-gmail-account` walkthrough for account files, replacing the old manual worktree-copy
  isolation procedure), and `CLAUDE.md`'s Architecture section. Added `CHANGELOG.md` entries under `vNext`,
  two marked `[breaking]` (the `--db` directory change and the app-credential rename).
- [x] [Verify] `pytest` (worktree venv): 187 passed, 2 skipped. `ruff check .`: all checks passed.
  `ruff format --check .`: all files formatted. Manual smoke test: `mail-utils prepare-gmail-account --help`
  and `mail-utils import-gmail --help` show the new `--account` flag; `mail-utils help` lists
  `prepare-gmail-account`; `mail-utils stats --db ./mydata` against a nonexistent directory correctly
  reports "No database found" without creating anything; `mail-utils import-pst
  tests/fixtures/sample.pst --db <dir> --with-attachments` creates `<dir>/mails.db` and a subsequent
  `mail-utils stats --db <dir>` reports the expected 2 messages/labels/senders. No real Gmail API testing
  performed (no live account available in this environment) - covered by unit tests with mocked
  credentials/API only, matching this project's existing convention.
- [x] [Visual] N/A - no UI surface; CLI-only feature.

## Progress & Validation Log

- 2026-08-28: Task claimed, worktree created, venv bootstrapped. Confirmed the design via chat with the
  user (rename handling, decoupled account/data-storage model, `mails.db` filename) before starting.
- 2026-08-28: Implemented `config.py`'s `resolve_account_path`/`resolve_db_dir`/`db_path_for`/
  `attachments_dir_for` and `APP_CREDENTIALS_PATH`, replacing the old fixed constants. Refactored
  `auth.py::get_credentials` to take explicit `account_path`/`app_credentials_path` arguments. Made
  `attachment_store.py` take a `configure(attachments_dir)` call instead of importing a fixed constant,
  called once per CLI run from `cli.py::_resolve_db_path` (which now resolves `--db` as a directory and
  configures the attachment store as a side effect, so all 7 of its existing call sites across `cli.py`
  picked up correct per-directory attachment scoping with no further changes needed at those sites).
- 2026-08-28: Implemented `prepare-gmail-account <name>` (`--with-write` for `STORE_IN_GMAIL_SCOPES`,
  read-only default) and threaded `--account` through `import`, `import-gmail`, `store-in-gmail`.
  `schedule`/`unschedule` need no separate change since `schedule` already validates its inner command
  against the same `build_parser()` that now includes `--account`. Updated `_run_import`'s Gmail-fallback
  detection to check `APP_CREDENTIALS_PATH`/the resolved account file instead of the old fixed paths.
- 2026-08-28: Updated `scripts/migrate-gmail-id-prefix.py` and `scripts/gmail-roundtrip-test.py` (added
  `--account`/`--to`, parameterizing the previously-hardcoded `katsan.pellicciotta@gmail.com` seed
  recipient).
- 2026-08-28: Updated all affected tests to the new explicit-path/directory conventions. Full suite: 187
  passed, 2 skipped. `ruff check`/`ruff format --check` clean. Manually smoke-tested
  `prepare-gmail-account --help`, `import-pst --db <dir>` (confirmed `<dir>/mails.db` created, `--db`'s own
  `--help` text correct), and `stats --db <dir>` against the result.
- 2026-08-28: Updated `README.md` (Database contents, Key Features, Quickstart), `docs/tutorial.md`,
  `docs/cli-spec.md`, `docs/devops.md` (new "Gmail Account Setup" section - filling a gap CLAUDE.md had
  pointed at README's "Setup" section for, which turned out not to actually exist), and `CLAUDE.md`'s
  Architecture section. Added `CHANGELOG.md` entries under `vNext`, two marked `[breaking]`.

## Completion Record

Reviewed and approved by the user on 2026-08-28 (solo, AI agent - no separate reviewer available; the
user confirmed integration directly after reviewing the implementation summary). Delivered: a
`prepare-gmail-account` command and `--account` flag decoupling Gmail-account selection from where a
run's data lives; a directory-based `--db` (`<dir>/mails.db` + `<dir>/attachments/`) that also closes a
pre-existing gap where the attachment cache was a single fixed global path shared across every database;
a renamed, clearly-documented shared app credential file
(`data/google-cloud-mail-utils-app-credentials.json`); a new "Gmail Account Setup" section in
`docs/devops.md` with the Google Cloud Console walkthrough this project's docs had never actually
contained despite `CLAUDE.md` pointing at it; and a parameterized `scripts/gmail-roundtrip-test.py` no
longer hardcoding the `katsan.pellicciotta@gmail.com` test address. No code changes were made to the
completed **T0013** task file, since its log is an accurate historical account of what was actually run
and rewriting it would misrepresent that record - per explicit user decision recorded in this task's
Scope. Two `[breaking]`-tagged `CHANGELOG.md` entries cover the `--db` and app-credential-file renames. No
real Gmail API testing was performed (no live account available in this environment); `prepare-gmail-
account` and the consent-flow changes are covered by unit tests with mocked credentials only, consistent
with this project's existing testing convention.
