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

Open design questions to resolve (with the user) before/during implementation — this task starts as a
proposal, not a committed design:

- **Is the account rename a like-for-like swap, or a new second account?** i.e. is
  `tester.pellicciotta@gmail.com` the *same* Google account as `katsan.pellicciotta@gmail.com` under a new
  address, or an entirely separate disposable account being introduced instead of (or alongside) it? This
  changes what setup work is actually needed (Cloud Console Test-user whitelisting, fresh OAuth consent,
  etc.) and isn't something the codebase can infer.
- **What to do with `katsan.pellicciotta@gmail.com` references already in version control:**
  - `tasks/T0013-gmail-e2e-safety-and-rollout.md` is a **completed** task's Progress Log / Validation
    Record / Completion Record — it documents what was actually run, against the account that actually
    existed at the time. Editing that text to say `tester.pellicciotta@gmail.com` would misrepresent
    history (the coordination guidelines treat task files as a permanent record, not something rewritten
    after the fact). Candidate options: (a) leave T0013's historical text as-is and only point future work
    at the new address, (b) leave T0013 as-is and add one short note near the top clarifying the account
    was later renamed/replaced, (c) do a literal find-replace anyway if the user decides historical
    accuracy doesn't matter here. Recommend (a) or (b).
  - `scripts/gmail-roundtrip-test.py` hardcodes `katsan.pellicciotta@gmail.com` as the `To:` address on its
    5 seeded test messages — this one is live/forward-looking code, not history, so it should just be
    updated to the new address (or, better, parameterized — see below).
- **Command shape:** a flat `prepare-gmail-account <name>` alongside the existing flat commands
  (`import`, `stats`, ...), or a namespaced `account` subcommand group (`account add`/`account list`/
  `account remove`, maybe `account use` for a default)? mail-utils has no subcommand namespacing today —
  introducing one is a bigger structural decision than the single-verb name suggests.
- **Directory layout:** where do per-account credentials live, and what exactly goes in an account
  directory?
  - Candidate: `data/accounts/<name>/credentials.json` + `data/accounts/<name>/token.json` only, with the
    database still addressed separately via the existing `--db` flag.
  - Alternative: mirror what a worktree gives you today "for free" — each account directory also gets its
    own default `gmail.db`/`attachments/`/`logs/`, so `--account <name>` alone is enough to fully isolate a
    run with no other flags needed.
- **`credentials.json` sharing:** the OAuth client secret is app-level, not account-level (same client,
  many accounts can consent against it — this is exactly what T0013 relied on). Should
  `prepare-gmail-account` copy a shared `credentials.json` into every account directory (duplicated but
  simple), or should account directories only ever hold `token.json` and resolve `credentials.json` from
  one shared location?
- **What the command actually automates**, once the layout is decided — creating the directory, placing
  the client secret, running the interactive consent flow scoped to that directory's `token.json`, and
  printing the resulting account's email (via the same `get_profile` call `store-in-gmail` already uses)
  so the user can eyeball-confirm they signed into the intended account before anything else uses it.
- **Scope selection at setup time:** does `prepare-gmail-account` always request `STORE_IN_GMAIL_SCOPES`
  (read + write), always just `SCOPES` (read-only) and let a later command upgrade it on demand (today's
  existing behavior in `auth.py::get_credentials`), or take a flag?
- **How other commands select an account:** a new `--account <name>` flag resolved in `config.py` next to
  `--db`, with what default when omitted (today's flat `data/credentials.json`/`token.json`, for backward
  compatibility, or a required flag once this lands)? Threading `--account` through also affects
  `schedule`/`unschedule`, since a scheduled job needs to keep pointing at the same account run after run.
- **Docs to update once a design is chosen:** `docs/devops.md`'s "Gmail Testing, Isolation, and Recovery"
  section (the worktree-copy procedure would likely be replaced or marked as a fallback), `docs/cli-spec.md`
  (new command/flag), `CLAUDE.md`, `README.md`.

## Out of Scope

- Actually running any new setup against `giovanni.pellicciotta@gmail.com` (production) — this task is
  about the tooling and the disposable test account only.
- Multi-account *concurrent* operation (e.g. one command touching several accounts in a single run).
  Scope here is one account at a time, selected explicitly.

## Dependencies

None. Builds on the isolation groundwork and safety-net conventions established in **T0013**
(`get_profile` target-account logging, the worktree-based isolation this task aims to make explicit).

## Approach

1. Present the open questions above to the user and get decisions on: rename handling, command shape,
   directory layout, credential-sharing strategy, and default/backward-compatibility behavior.
2. Design the concrete directory layout and `--account` resolution in `config.py`, with unit tests.
3. Implement `prepare-gmail-account` (or the decided command shape) per the agreed automation scope.
4. Thread `--account` through the commands that need it (`import`, `import-gmail`, `store-in-gmail` at
   minimum; `schedule`/`unschedule` if scheduled jobs are meant to target a named account).
5. Apply the decided rename handling to `tasks/T0013-...md` and `scripts/gmail-roundtrip-test.py`.
6. Update `docs/devops.md`, `docs/cli-spec.md`, `CLAUDE.md`, `README.md` to reflect the new setup flow.
7. Present findings/implementation to the user for review (solo, AI agent tier) before marking complete.

## Implementation Checklist

- [ ] Design decisions confirmed with the user (rename handling, command shape, directory layout,
  credential sharing, default/back-compat behavior)
- [ ] `--account` resolution implemented in `config.py`, with tests
- [ ] `prepare-gmail-account` (or decided command) implemented, with tests
- [ ] `--account` threaded through the relevant existing commands
- [ ] Rename applied per the agreed approach
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
