# T0015: Named Gmail account directories and a `prepare-gmail-account` command

- **Status:** available
- **Owner:** none
- **Started:** —
- **Branch:** —
- **Worktree:** —

## Goal

Give mail-utils a first-class, repeatable way to set up and switch between multiple named Gmail accounts
(disposable test accounts, and eventually production), replacing today's ad hoc, worktree-only isolation
mechanism (see `docs/devops.md`'s "Testing against a disposable account, isolated from production",
written during **T0013**). Concretely: a dedicated CLI action that walks through getting a `credentials.json`
+ `token.json` pair in place for one named account, and a storage layout that lets other commands
(`import`, `import-gmail`, `store-in-gmail`, `schedule`, ...) point at a specific account by name instead of
relying on which physical checkout/worktree they happen to run from.

Also triggered by, and in scope for, a rename: the disposable test account used throughout T0013
(`katsan.pellicciotta@gmail.com`) should become `tester.pellicciotta@gmail.com` going forward. How that
rename is actually carried out (see Scope) depends on decisions this task needs to make first, so it's
folded in here rather than done as a quick standalone edit.

## Scope

**Decisions confirmed with the user (2026-08-28):**

- `tester.pellicciotta@gmail.com` is a brand-new, separate disposable account — not a rename/alias of
  `katsan.pellicciotta@gmail.com`. It needs its own from-scratch setup (Cloud Console Test-user
  whitelisting, fresh OAuth consent), same as `katsan.pellicciotta@gmail.com` originally did in T0013.
  `katsan.pellicciotta@gmail.com` references already committed stay as an accurate historical record:
  `tasks/T0013-gmail-e2e-safety-and-rollout.md` is a **completed** task's Progress Log / Validation
  Record / Completion Record documenting what was actually run — left untouched. Only the live,
  forward-looking `scripts/gmail-roundtrip-test.py` (hardcodes `katsan.pellicciotta@gmail.com` as the
  seeded messages' `To:` address) gets updated — parameterized to accept the target account's address
  rather than hardcoding either one, so this doesn't recur next time an account changes.
- Command shape: a flat `prepare-gmail-account <name>`, matching the existing flat command style
  (`import`, `stats`, ...) rather than introducing a new `account` subcommand namespace.
- Backward compatibility with today's flat, unnamed `data/credentials.json`/`data/token.json`/
  `data/gmail.db` layout is explicitly not a concern for this task — free to land the cleanest layout
  without a migration path or dual-mode fallback.

**Directory layout (recommended design, not yet confirmed):**

```
data/
  credentials.json          # shared OAuth client secret (app-level, one Cloud project/client; unchanged)
  accounts/
    <name>/
      token.json              # this account's OAuth token
      gmail.db                # this account's default database (still overridable via --db)
      attachments/             # this account's attachment cache
  logs/
    mail-utils.log            # stays global/shared - "Target account: ..." lines already disambiguate
```

Rationale: `credentials.json` is the OAuth *client* secret, not tied to any one Google account — the same
client already consents multiple accounts today (T0013 reused it as-is for `katsan.pellicciotta@gmail.com`
alongside the production account), so it stays a single shared file rather than being duplicated into every
account directory. `token.json` + `gmail.db` + `attachments/` are the actually account-specific state, so
each gets its own subdirectory under `data/accounts/<name>/` — this also fixes a latent gap in
`config.py`'s current `ATTACHMENTS_DIR`: it's a fixed global constant today with no `--db`-style override,
so two databases selected via `--db` already silently share one attachment cache; giving each account (and
implicitly each `--db`) its own `attachments/` closes that. `--account <name>` becomes a new flag,
resolved in `config.py` next to `--db`: when given, it sets the default `token.json`/`gmail.db`/
`attachments/` paths to that account's subdirectory; an explicit `--db` on top still wins, same precedence
`--db` already has today. Omitting `--account` keeps using the flat `data/token.json`/`data/gmail.db`/
`data/attachments/` paths unchanged — useful for the single-account/production case that doesn't need this
machinery, and free since back-compat isn't otherwise a constraint here.

**Still open, needs a decision before/during implementation:**

- **Scope requested at setup time:** `prepare-gmail-account <name>` always requests read-only `SCOPES` by
  default (matching this project's "read-only is the default" principle), with a `--with-write` flag to
  request `STORE_IN_GMAIL_SCOPES` directly for accounts destined for `store-in-gmail` testing — otherwise
  the first `store-in-gmail` run against that account upgrades scope on its own via `auth.py::
  get_credentials`'s existing re-consent behavior. Recommended default; not yet explicitly confirmed.
- Threading `--account` through `schedule`/`unschedule` (a scheduled job needs to keep targeting the same
  named account run after run) — mechanically straightforward once the flag exists elsewhere, but worth
  calling out since scheduled jobs build and store a full command line.
- **Docs to update once implemented:** `docs/devops.md`'s "Gmail Testing, Isolation, and Recovery" section
  (the manual worktree-copy procedure gets replaced by pointing at `prepare-gmail-account`), `docs/
  cli-spec.md` (new command/flag), `CLAUDE.md`, `README.md`.

## Out of Scope

- Actually running any new setup against `giovanni.pellicciotta@gmail.com` (production) — this task is
  about the tooling and the disposable test account only.
- Multi-account *concurrent* operation (e.g. one command touching several accounts in a single run).
  Scope here is one account at a time, selected explicitly.

## Dependencies

None. Builds on the isolation groundwork and safety-net conventions established in **T0013**
(`get_profile` target-account logging, the worktree-based isolation this task aims to make explicit).

## Approach

1. Confirm the recommended directory layout and the still-open setup-scope default with the user.
2. Implement `--account` resolution in `config.py` (default `token.json`/`gmail.db`/`attachments/` paths
   under `data/accounts/<name>/` when given; `--db` still overrides on top), with unit tests. Refactor
   `auth.py::get_credentials` to accept explicit `token_path`/`credentials_path` instead of importing the
   flat module-level constants directly — the core change that makes per-account tokens possible.
3. Implement `prepare-gmail-account <name>` (creates the account directory, requires the shared
   `data/credentials.json` to already exist, runs consent scoped to that account's `token.json`, prints the
   resulting email via `get_profile` for eyeball confirmation), with tests.
4. Thread `--account` through `import`, `import-gmail`, `import-pst`, `import-thunderbird`, `search`,
   `stats`, `export`, `store-in-gmail`, and `schedule`/`unschedule`.
5. Parameterize `scripts/gmail-roundtrip-test.py`'s hardcoded `katsan.pellicciotta@gmail.com` `To:` address
   into a flag/argument.
6. Update `docs/devops.md`, `docs/cli-spec.md`, `CLAUDE.md`, `README.md` to reflect the new setup flow.
7. Present findings/implementation to the user for review (solo, AI agent tier) before marking complete.

## Implementation Checklist

- [ ] Directory layout and setup-scope default confirmed with the user
- [ ] `--account` resolution implemented in `config.py`; `get_credentials` takes explicit paths, with tests
- [ ] `prepare-gmail-account <name>` implemented, with tests
- [ ] `--account` threaded through the relevant existing commands
- [ ] `scripts/gmail-roundtrip-test.py`'s target address parameterized
- [ ] Docs updated (`docs/devops.md`, `docs/cli-spec.md`, `CLAUDE.md`, `README.md`)

## Test Strategy

Unit tests for path resolution and command wiring (mocked credentials/API, following the project's
existing convention — see T0002). The interactive OAuth consent step itself isn't unit-testable; any real
end-to-end verification against a live disposable account is manual, same as T0013.

## Completion Criteria

Design decisions are made and recorded here; the account directory layout and `prepare-gmail-account` (or
decided equivalent) are implemented and tested; the rename is applied per the agreed approach; docs reflect
the new setup flow; the user has reviewed and approved before integration.

## Progress Log

## Validation Record

## Completion Record
