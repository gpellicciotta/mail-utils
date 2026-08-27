# T0001: Reverse mail import (filesystem exports back into Gmail/Outlook/Thunderbird)

- **Status:** active
- **Owner:** claude
- **Started:** 2026-08-27
- **Branch:** task/T0001-reverse-mail-import
- **Worktree:** ./work/T0001-reverse-mail-import

## Goal

Investigate what it would take to go the *opposite* direction of `mail-utils`' current
`import`/`import-gmail`/`import-pst`/`import-thunderbird` + `export` flow: starting from mail already
exported to the filesystem (the `.md`/`.eml` tree `mail-utils export` produces, or any other local EML/mbox
corpus) and re-importing it into a live Gmail account. Determine feasibility, what information would
necessarily be lost or reconstructed approximately, and produce a concrete implementation plan if it's
viable. Also survey what already exists for the same problem on Outlook and Thunderbird, since a
mail-utils-native solution only makes sense where it beats (or plausibly complements) existing tools.

## Scope

- Gmail: how a third party can inject already-composed messages into a mailbox as if they'd always been
  there (arrival date, read/unread state, labels, thread grouping) — Gmail API `messages.import` vs
  `messages.insert` vs raw IMAP `APPEND`, quota/rate-limit behavior, spam/phishing heuristics on bulk
  historical mail, and what round-trips cleanly given what `mail-utils export` currently keeps
  (`README.md`'s "Database contents" — attachments are metadata-only today, no bytes retained).
- A concrete feasibility verdict and, if viable, an implementation sketch for a `mail-utils` subcommand
  (or a documented external-tool workflow) that performs the restore.
- A survey of existing third-party tools/services that already solve "put EML/mbox files back into
  Gmail", "into Outlook (.pst)", and "into Thunderbird (mbox/profile)" — so the plan can explicitly say
  where mail-utils would add value versus where an existing tool already covers it.

## Out of Scope

- Actually writing GMail-import code in this task — only if the findings clearly justify it and the user
  asks for it as a follow-up task.
- Outlook/Thunderbird-native reverse-import *implementation* (only the survey of what already exists for
  those two, since mail-utils' own export formats are EML/Markdown, not PST/mbox).

## Dependencies

None.

## Approach

1. Research Gmail's supported paths for injecting historical mail (Gmail API `import`/`insert`, IMAP
   `APPEND` against `imap.gmail.com`), and what each does/doesn't preserve (`internalDate`, labels,
   read/starred state, threading, size limits, per-user daily quota).
2. Cross-reference against what `mail-utils export` actually retains today (per `README.md`'s "Database
   contents" and `gmail_client.parse_message`/`parse_attachments`) to identify concrete, current data-loss
   points (e.g. attachment bytes are never captured, so a restore cannot re-attach files).
3. Survey existing tools for the same job across all three ecosystems (Gmail, Outlook, Thunderbird) —
   at minimum look for IMAP-sync tools, Gmail-specific backup/restore tools, and PST-writing tools.
4. Write up findings as a docs/ plan document (feasibility verdict, data-loss/limitations list, tool
   survey with a recommendation, and — if justified — a phased implementation sketch).
5. Update `TODO.md`/`CHANGELOG.md` per the standard workflow and present findings for review.

## Implementation Checklist

- [ ] Research Gmail-side import mechanisms and their guarantees/limits.
- [ ] Map current `mail-utils` export data model against what a restore would need.
- [ ] Survey existing Gmail-restore tools (e.g. backup/restore utilities, IMAP-sync tools).
- [ ] Survey existing Outlook PST-writing / mail-restore tools.
- [ ] Survey existing Thunderbird mbox-reimport tooling/add-ons.
- [ ] Write `docs/reverse-import-plan.md` with feasibility verdict + recommendation.

## Test Strategy

N/A — this task is a research/planning deliverable, not shipped code. If a follow-up implementation task
is opened, that task defines its own test strategy.

## Completion Criteria

`docs/reverse-import-plan.md` exists, answers the three questions the user asked (would it work, what's
lost, what's the plan if not trivial), and includes the cross-tool alternatives survey for Gmail, Outlook,
and Thunderbird. `TODO.md` and `CHANGELOG.md` (if applicable — see note in Validation Record) are updated.

## Progress Log

- 2026-08-27: Task claimed, worktree created, research started.

## Validation Record

N/A (research/planning task; no code paths exercised). No `CHANGELOG.md` entry expected unless the
findings lead directly to a code or doc change beyond the plan document itself.

## Completion Record

(pending)
