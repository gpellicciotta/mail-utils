---
id: T0022
title: "Rewrite all task files to the newly documented format"
owner: claude
needs: []
branch: task/T0022-rewrite-task-files-new-format
worktree: ./work/T0022-rewrite-task-files-new-format
status: active
started: 2026-09-03
ended: —
---

# T0022: Rewrite all task files to the newly documented format

## Objectives & Scope

### Goal

Promoted from A0022. `CLAUDE.md`'s coordinating-work-guidelines now specify a task-file shape different
from the one every existing `tasks/*.md` file was written in: YAML frontmatter (`id`, `title`, `owner`,
`needs`, `branch`, `worktree`, `status`, `started`, `ended`) instead of a bullet-list header, and 4 primary
sections (`Objectives & Scope`, `Task Implementation and Verification Steps`, `Progress & Validation Log`,
`Completion Record`/`Cancellation Record`) instead of the old 11-section layout (`Goal`/`Scope`/`Out of
Scope`/`Dependencies`/`Approach`/`Implementation Checklist`/`Test Strategy`/`Completion Criteria`/
`Progress Log`/`Validation Record`/`Completion Record`). Rewrite every existing task file into the new
shape without losing any essential information — especially for uncompleted tasks, where the file is the
only record of how to actually pick the work back up.

### Scope

- Every file under `tasks/` gets rewritten to the new frontmatter + 4-section shape, folding the old
  sections into the new ones as follows: `Objectives & Scope` absorbs `Goal`/`Scope`/`Out of
  Scope`/`Dependencies`/`Completion Criteria`; `Task Implementation and Verification Steps` absorbs
  `Approach`/`Implementation Checklist`/`Test Strategy` as one checklist whose items are tagged `[Read]`,
  `[Decide]`, `[Implement]`, `[Verify]`, `[Visual]`, `[Doc]`; `Progress & Validation Log` absorbs `Progress
  Log`/`Validation Record` as one chronological narrative; `Completion Record`/`Cancellation Record` is
  carried over as-is.
- **Explicit exception, per the user's direct instruction**: `tasks/T0020-full-archive-import-and-eml-
  roundtrip.md` is deliberately left untouched. The copy of that file on `main` (and therefore in this
  worktree, branched from `main`) is a stale placeholder — T0020 is actively `[~]` in `TODO.md` with real,
  detailed progress living only in its own worktree (`./work/T0020-full-archive-import-and-eml-roundtrip`),
  not yet merged. Rewriting the stale `main` copy now would either lose nothing (it has almost no content
  yet) or, worse, get overwritten/conflict when T0020's own branch eventually merges its real content back.
  T0020's file gets migrated to the new format later, as part of (or right after) its own merge.
- All other 12 files get the full rewrite: `T0001`, `T0002`, `T0004`, `T0010`, `T0013`, `T0014`, `T0015`,
  `T0017`, `T0021`, `T0024`, `T0025`, `T0026`, `T0027`.

### Out of Scope

- Any change to `TODO.md` beyond this task's own claim/completion lifecycle lines.
- Rewriting `T0020`'s task file (see Scope exception above).
- Changing any task's actual outcome, decisions, or historical record — this is a structural
  reformatting pass, not a chance to edit history. Where the old format left a section thin (e.g. `T0024`'s
  `Validation Record`/`Completion Record` are empty since it's not done), the new format stays equally thin
  rather than inventing content.

### Dependencies

None to start. Cannot reach 100% completion (i.e. "all task files rewritten") until **T0020** merges its
own task file's real content back to `main`, since that file is deliberately excluded here (see Scope). Once
T0020 lands, this task should be re-claimed to migrate that one remaining file and then be marked complete.

### Completion Criteria

Every file in `tasks/` except `T0020-full-archive-import-and-eml-roundtrip.md` uses the new frontmatter +
4-section format, with no loss of the substantive content (decisions, root causes, real numbers, follow-ups)
the old format recorded. `T0020`'s file is migrated in a later pass, once its branch merges.

## Task Implementation and Verification Steps

- [x] [Read] Read all 13 existing `tasks/*.md` files in full to inventory what each one's old sections
  actually contain, before designing the new template - the concern in the task's own description
  ("do I know how to implement this based only on the information in the file as it now stands") only holds
  if nothing is silently dropped during the fold.
- [x] [Decide] Designed the section-folding mapping (old 11 sections/header bullets -> new frontmatter + 4
  sections) documented in Scope above, and confirmed with a self-check per file: after the rewrite, is
  every decision, root cause, real measurement, and follow-up reference from the original still present
  somewhere in the new file?
- [x] [Implement] Rewrote `T0001`, `T0002`, `T0004`, `T0010`, `T0013`, `T0014`, `T0015`, `T0017`, `T0021`,
  `T0025`, `T0026`, `T0027` (completed tasks - straightforward historical-record fold) and `T0024`
  (available/uncompleted - extra care taken to keep its design-doc pointer and pending-decision checklist
  items directly actionable in the new format).
- [x] [Verify] Re-read every rewritten file against its original side-by-side-in-memory to confirm no
  section's content was dropped (dates, real numbers, bug root-causes, follow-up task references, and
  reviewer/sign-off notes all carried over); confirmed `T0020`'s file was left byte-for-byte untouched.
- [x] [Visual] N/A - documentation-only change, no UI surface.
- [ ] [Doc] `TODO.md`'s `T0022` line: per explicit instruction, marked back to available (`[ ]`) with
  `(needs T0020)` rather than removed, since the `T0020` file migration is still outstanding - not a normal
  completion.

## Progress & Validation Log

- 2026-09-03: Claimed following the user's request to work T0022 now, with the explicit carve-out that
  `T0020`'s own task file is left alone (it will be merged from its worktree later) - worktree/branch
  created off `main` at `186ca67`.
- 2026-09-03: Read all 13 existing task files in full. Confirmed `tasks/T0020-full-archive-import-and-eml-
  roundtrip.md` on `main` is a near-empty placeholder (Status: available, empty Progress
  Log/Validation Record/Completion Record, all Implementation Checklist items unchecked) - the real,
  detailed T0020 record lives only in its own unmerged worktree, confirming the exception in Scope is
  correct and not just precautionary.
- 2026-09-03: Rewrote the other 12 files to the new frontmatter + 4-section format, preserving every
  decision, root-caused bug, real measurement (test counts, message counts, timings), and follow-up
  reference from the originals. No content was invented or altered - only reorganized.
- 2026-09-03: This task is not being marked complete. Per explicit instruction, `TODO.md`'s `T0022` line
  goes back to `[ ] T0022 (needs T0020) rewrite-task-files-new-format` (available, dependency noted) instead
  of being removed, since the `T0020` file itself still needs migrating once that task's branch merges. This
  worktree/branch is left in place (not cleaned up) so that final step has somewhere to land later.
