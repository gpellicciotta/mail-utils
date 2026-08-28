# T0015: Named Gmail account files and a `prepare-gmail-account` command

- **Status:** available
- **Owner:** none
- **Started:** —
- **Branch:** —
- **Worktree:** —

## Goal

Give mail-utils a first-class, repeatable way to set up and switch between multiple named Gmail accounts
(disposable test accounts, and eventually production), replacing today's ad hoc, worktree-only isolation
mechanism (see `docs/devops.md`'s "Testing against a disposable account, isolated from production",
written during **T0013**). Concretely: a dedicated CLI action that produces one self-contained,
per-account credential file, a `--account` flag other commands use to select which one to authenticate
as, and a `--db` flag that scopes a run's database *and* attachment cache together — with account
selection and data-storage location kept fully independent of each other.

Also triggered by, and in scope for, a rename: the disposable test account used throughout T0013
(`katsan.pellicciotta@gmail.com`) should become `tester.pellicciotta@gmail.com` going forward. How that
rename is actually carried out (see Scope) depends on decisions this task needs to make first, so it's
folded in here rather than done as a quick standalone edit.

## Scope

**Design (confirmed with the user on 2026-08-28):**

- **Account rename:** `tester.pellicciotta@gmail.com` is a brand-new, separate disposable account — not a
  rename/alias of `katsan.pellicciotta@gmail.com`. It needs its own from-scratch setup (Cloud Console
  Test-user whitelisting, fresh OAuth consent), same as `katsan.pellicciotta@gmail.com` originally did in
  T0013. `katsan.pellicciotta@gmail.com` references already committed stay as an accurate historical
  record: `tasks/T0013-gmail-e2e-safety-and-rollout.md` is a **completed** task's Progress Log / Validation
  Record / Completion Record documenting what was actually run — left untouched. Only the live,
  forward-looking `scripts/gmail-roundtrip-test.py` (hardcodes `katsan.pellicciotta@gmail.com` as the
  seeded messages' `To:` address) gets updated — parameterized to accept the target account's address
  rather than hardcoding either one, so this doesn't recur next time an account changes.
- **Command shape:** a flat `prepare-gmail-account <name>`, matching the existing flat command style
  (`import`, `stats`, ...) rather than introducing a new `account` subcommand namespace.
- **Backward compatibility** with today's flat, unnamed `data/credentials.json`/`data/token.json`/
  `data/gmail.db` layout is explicitly not a concern for this task — free to land the cleanest layout
  without a migration path or dual-mode fallback.
- **Accounts and data storage are decoupled.** An account file identifies *who mail-utils authenticates
  as*; `--db` identifies *where a run's data lives*. Neither implies the other — any account can be used
  with any `--db` location, and switching database doesn't require switching account.
- **App credential file** (the OAuth client secret identifying the *application*, not any one Google
  account) is renamed from `data/credentials.json` to the more self-explanatory
  `data/google-cloud-mail-utils-app-credentials.json`. It stays a single shared file — the same client
  already consents multiple accounts today (T0013 reused it as-is for
  `katsan.pellicciotta@gmail.com` alongside the production account) — obtained once via the Google Cloud
  Console walkthrough already documented in `README.md`'s Setup section, which gets updated to reference
  the new filename.
- **Account file:** one self-contained JSON file per authorized Gmail account (structurally what
  `token.json` holds today — the OAuth refresh/access token), named `<name>-account.json`. Default
  location `data/<name>-account.json`; a value containing a path separator or explicit `.json` extension
  is used verbatim as the file path instead (`--account a/b/c-account.json`). No directory nesting, no
  bundled database/attachments — just the one file.
- **`--account` flag**, added to every Gmail-API-touching command (`import`, `import-gmail`,
  `store-in-gmail`, and whatever `schedule`/`unschedule` wrap that includes those):
  - `--account xxx` -> `data/xxx-account.json`.
  - `--account a/b/c-account.json` -> that exact path.
  - Omitted -> falls back to `data/default-account.json` if it exists (no magic: "default" is just an
    account name someone can choose to set up via `prepare-gmail-account default`, picked up
    automatically only because it's the conventional fallback name); otherwise the command errors clearly,
    asking for `--account` to be specified.
- **`prepare-gmail-account <name>`:** resolves its target path the same way `--account` does, requires
  `data/google-cloud-mail-utils-app-credentials.json` to already exist (clear error pointing at the docs
  otherwise), runs the interactive consent flow, writes the resulting token to that account file, and
  prints the authenticated address (via the existing `get_profile` call) so the user can eyeball-confirm
  they signed into the intended account. Requests read-only `SCOPES` by default; a `--with-write` flag
  requests `STORE_IN_GMAIL_SCOPES` instead, for accounts being set up specifically to test
  `store-in-gmail` — otherwise the first real `store-in-gmail` run against that account upgrades scope on
  its own via `auth.py::get_credentials`'s existing re-consent behavior, unchanged.
- **`--db` becomes a directory, not a file.** `--db <dir>` creates `<dir>` if missing and scopes both the
  database and the attachment cache inside it: `<dir>/mails.db` + `<dir>/attachments/` (default remains
  `data/`, i.e. `data/mails.db` + `data/attachments/`, when `--db` is omitted). Renamed from `gmail.db` to
  `mails.db` — the database isn't Gmail-specific (PST/Thunderbird imports land in it too), and `mails.db`
  reads better as the generic per-directory filename now that `--db` addresses a directory rather than one
  file. This directly fixes a latent gap in the current code: `config.py`'s `ATTACHMENTS_DIR` is a single
  fixed global path today with **no** `--db`-style override, so two different databases already selected
  via `--db` silently share one attachment cache; scoping attachments inside the same directory as the
  database they belong to closes that.

**Docs to update once implemented:**

- `README.md`'s Setup walkthrough — the app-credential file's new name, and a pointer to
  `prepare-gmail-account` for producing an account file (replacing/supplementing the one-time OAuth-consent
  description currently there).
- `docs/devops.md`'s "Gmail Testing, Isolation, and Recovery" section — the manual worktree-copy procedure
  gets replaced by `prepare-gmail-account` + `--account`/`--db`; needs its own subsection explaining what an
  account file is, how to obtain one, and why it's needed (the account-level authorization, distinct from
  the app-level credential file), per the user's explicit ask for this to be documented clearly.
- `docs/cli-spec.md` — new command, new `--account` flag, `--db`'s changed (directory) semantics.
- `CLAUDE.md` — architecture notes for `config.py`/`auth.py`/`cli.py` once the refactor lands.

## Out of Scope

- Actually running any new setup against `giovanni.pellicciotta@gmail.com` (production) — this task is
  about the tooling and the disposable test account only.
- Multi-account *concurrent* operation (e.g. one command touching several accounts in a single run).
  Scope here is one account at a time, selected explicitly.

## Dependencies

None. Builds on the isolation groundwork and safety-net conventions established in **T0013**
(`get_profile` target-account logging, the worktree-based isolation this task aims to make explicit).

## Approach

1. Rename `config.py`'s `CREDENTIALS_PATH`/constant and underlying file to
   `data/google-cloud-mail-utils-app-credentials.json`. Add account-file resolution (bare name vs.
   path-like value, `default-account.json` fallback) and directory-based `--db` resolution (database +
   `attachments/` both scoped inside it), with unit tests.
2. Refactor `auth.py::get_credentials` to accept explicit `account_path`/`app_credentials_path` arguments
   instead of importing the flat module-level constants directly — the core change that makes per-account
   token files possible.
3. Implement `prepare-gmail-account <name>` (account-path resolution, requires the app credential file,
   runs consent, `--with-write` flag, prints the authenticated address), with tests.
4. Thread `--account` through `import`, `import-gmail`, `store-in-gmail`, and `schedule`/`unschedule`;
   convert every command's existing `--db` handling to the new directory semantics
   (`import`, `import-gmail`, `import-pst`, `import-thunderbird`, `search`, `stats`, `export`,
   `store-in-gmail`).
5. Parameterize `scripts/gmail-roundtrip-test.py`'s hardcoded `katsan.pellicciotta@gmail.com` `To:` address
   into a flag/argument.
6. Update `README.md`, `docs/devops.md`, `docs/cli-spec.md`, `CLAUDE.md` per the Scope list above.
7. Present findings/implementation to the user for review (solo, AI agent tier) before marking complete.

## Implementation Checklist

- [ ] App credential file renamed; account-file and directory-`--db` (`mails.db` + `attachments/`)
  resolution implemented in `config.py`,
  with tests
- [ ] `get_credentials` takes explicit account/app-credential paths, with tests
- [ ] `prepare-gmail-account <name>` implemented (default scope + `--with-write`), with tests
- [ ] `--account` threaded through Gmail-API commands; every command's `--db` converted to directory
  semantics
- [ ] `scripts/gmail-roundtrip-test.py`'s target address parameterized
- [ ] Docs updated (`README.md`, `docs/devops.md`, `docs/cli-spec.md`, `CLAUDE.md`)

## Test Strategy

Unit tests for path resolution and command wiring (mocked credentials/API, following the project's
existing convention — see T0002). The interactive OAuth consent step itself isn't unit-testable; any real
end-to-end verification against a live disposable account is manual, same as T0013.

## Completion Criteria

The account-file/app-credential-file split, `--account` resolution, and directory-based `--db` are
implemented and tested; `prepare-gmail-account` works end-to-end; the rename is applied per the agreed
approach; docs reflect the new setup flow; the user has reviewed and approved before integration.

## Progress Log

## Validation Record

## Completion Record
