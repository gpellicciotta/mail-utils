# T0013: Safe end-to-end Gmail testing, with a path to production rollout

- **Status:** available
- **Owner:** none
- **Started:** —
- **Branch:** —
- **Worktree:** —

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

- [ ] Test/production credential isolation approach decided and set up
- [ ] OAuth consent run against `katsan.pellicciotta@gmail.com`; scopes confirmed
- [ ] A0006 checklist executed and passed against the test account
- [ ] Recovery playbook documented
- [ ] Go-live checklist documented
- [ ] User review and sign-off

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

## Validation Record

## Completion Record
