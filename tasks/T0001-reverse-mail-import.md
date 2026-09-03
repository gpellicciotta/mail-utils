---
id: T0001
title: "Reverse mail import (filesystem exports back into Gmail/Outlook/Thunderbird)"
owner: claude
needs: []
branch: task/T0001-reverse-mail-import
worktree: ./work/T0001-reverse-mail-import
status: completed
started: 2026-08-27
ended: 2026-08-27
---

# T0001: Reverse mail import (filesystem exports back into Gmail/Outlook/Thunderbird)

## Objectives & Scope

### Goal

Investigate what it would take to go the *opposite* direction of `mail-utils`' current
`import`/`import-gmail`/`import-pst`/`import-thunderbird` + `export` flow: starting from mail already
exported to the filesystem (the `.md`/`.eml` tree `mail-utils export` produces, or any other local EML/mbox
corpus) and re-importing it into a live Gmail account. Determine feasibility, what information would
necessarily be lost or reconstructed approximately, and produce a concrete implementation plan if it's
viable. Also survey what already exists for the same problem on Outlook and Thunderbird, since a
mail-utils-native solution only makes sense where it beats (or plausibly complements) existing tools.

### Scope

- Gmail: how a third party can inject already-composed messages into a mailbox as if they'd always been
  there (arrival date, read/unread state, labels, thread grouping) - Gmail API `messages.import` vs
  `messages.insert` vs raw IMAP `APPEND`, quota/rate-limit behavior, spam/phishing heuristics on bulk
  historical mail, and what round-trips cleanly given what `mail-utils export` currently keeps
  (`README.md`'s "Database contents" - attachments are metadata-only today, no bytes retained).
- A concrete feasibility verdict and, if viable, an implementation sketch for a `mail-utils` subcommand
  (or a documented external-tool workflow) that performs the restore.
- A survey of existing third-party tools/services that already solve "put EML/mbox files back into
  Gmail", "into Outlook (.pst)", and "into Thunderbird (mbox/profile)" - so the plan can explicitly say
  where mail-utils would add value versus where an existing tool already covers it.

### Out of Scope

- Actually writing Gmail-import code in this task - only if the findings clearly justify it and the user
  asks for it as a follow-up task.
- Outlook/Thunderbird-native reverse-import *implementation* (only the survey of what already exists for
  those two, since mail-utils' own export formats are EML/Markdown, not PST/mbox).

### Dependencies

None.

### Completion Criteria

`docs/reverse-import-plan.md` exists, answers the three questions the user asked (would it work, what's
lost, what's the plan if not trivial), and includes the cross-tool alternatives survey for Gmail, Outlook,
and Thunderbird. `TODO.md` and `CHANGELOG.md` (if applicable - see Progress & Validation Log) are updated.

## Task Implementation and Verification Steps

- [x] [Read] Researched Gmail's supported paths for injecting historical mail (Gmail API
  `messages.import`/`.insert`, IMAP `APPEND`), and what each does/doesn't preserve (`internalDate`, labels,
  read/starred state, threading, size limits, per-user daily quota).
- [x] [Read] Cross-referenced against what `mail-utils export` actually retains today (per `README.md`'s
  "Database contents" and `gmail_client.parse_message`/`parse_attachments`) to identify concrete, current
  data-loss points (e.g. attachment bytes are never captured, so a restore cannot re-attach files).
- [x] [Read] Surveyed existing tools for the same job across all three ecosystems: Gmail-side (GYB,
  imapsync, IMAP Upload for Gmail), Outlook PST-writing/mail-restore tools (Aid4Mail, Outlook COM
  automation), and Thunderbird mbox-reimport tooling/add-ons (ImportExportTools NG).
- [x] [Decide] Flagged the Gmail write-scope decision as the explicit blocker per the project's read-only
  invariant, rather than assuming it away - left for the user to approve before any implementation task
  could start.
- [x] [Doc] Wrote `docs/reverse-import-plan.md` with the feasibility verdict, data-loss/limitations list,
  tool survey with a recommendation, and a conditional phased implementation sketch; linked it from
  `docs/index.md`.
- [x] [Verify] N/A - research/planning task, no code paths exercised. No separate reviewer available (solo,
  AI agent); per the Review Tiers table, findings were presented to the user for explicit permission before
  integration.
- [x] [Visual] N/A - no UI surface; this is a research/planning deliverable, not shipped code.

## Progress & Validation Log

- 2026-08-27: Task claimed, worktree created, research started.
- 2026-08-27: Researched Gmail API `messages.import`/`.insert` semantics, quota/rate limits, and OAuth
  scope requirements; cross-referenced against `gmail_client.parse_attachments`/`parse_message` and
  `README.md`'s "Database contents" to confirm attachment bytes are the one unrecoverable data-loss point
  regardless of target platform. Surveyed existing tools (GYB, imapsync, IMAP Upload for Gmail; Aid4Mail
  and Outlook COM automation for `.pst`; ImportExportTools NG for Thunderbird). Wrote up findings,
  feasibility verdict, and a conditional implementation sketch in `docs/reverse-import-plan.md`, linked
  from `docs/index.md`. Flagged the Gmail write-scope decision as the explicit blocker per `CLAUDE.md`'s
  read-only invariant, rather than assuming it away. Added a `vNext` `CHANGELOG.md` entry for the new doc.

## Completion Record

Reviewed and approved by the user on 2026-08-27 (solo, AI agent - no separate reviewer). The Gmail
write-scope decision flagged in `docs/reverse-import-plan.md`'s "Decision needed" section was also
approved in the same exchange, opening follow-up task T0002 for the actual implementation.
