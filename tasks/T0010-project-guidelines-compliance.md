---
id: T0010
title: "Bring the project into full compliance with dev-guidelines and python-project-template"
owner: claude
needs: []
branch: task/T0010-project-guidelines-compliance
worktree: ./work/T0010-project-guidelines-compliance
status: completed
started: 2026-08-27
ended: 2026-08-27
---

# T0010: Bring the project into full compliance with dev-guidelines and python-project-template

## Objectives & Scope

### Goal

Promoted from A0008 (originally just "reconcile the minimum Python version") after the user asked for a
full compliance pass against [dev-guidelines](https://github.com/gpellicciotta/dev-guidelines) and
[python-project-template](https://github.com/gpellicciotta/python-project-template). An actual audit
(diffing `pyproject.toml`, `.gitignore`, `.github/workflows/ci.yml`, and doc structure against the
template, plus scanning all Markdown docs for guideline violations) turned up more than the single
version mismatch, so this became a real multi-file task rather than a one-sitting adhoc fix.

### Scope

Findings from the audit, all fixed in this task:

1. `docs/devops.md` said "Python 3.11+" while `pyproject.toml`'s `requires-python` said `>=3.10` and CI
   only actually tested 3.11 - aligned `docs/devops.md` to `>=3.10` (matching `pyproject.toml` and
   python-project-template's own `docs/devops.md`, which says "Python 3.10+"). The original A0008 finding.
2. `pyproject.toml` had no `authors` field - general-guidelines.md requires a single source of truth for
   vendor/author metadata in the build config. Added
   `authors = [{name="Giovanni Pellicciotta", email="giovanni.pellicciotta@gmail.com"}]`, matching
   python-project-template.
3. `pyproject.toml` had no `classifiers` - added the same three python-project-template carries
   (`Programming Language :: Python :: 3` / `License :: OSI Approved :: MIT License` /
   `Operating System :: OS Independent` - mail-utils is also MIT-licensed).
4. `docs/index.md` skipped a heading level (H1 straight to H3 for "Core Documentation" / "Design &
   Technical Plans" / "Root References") - violated markdown-guidelines.md's heading-hierarchy rule.
   Bumped those three to H2.
5. `docs/cli-spec.md`, `docs/devops.md`, `docs/pst-support-plan.md`, `docs/thunderbird-import-plan.md`, and
   `docs/tutorial.md` all used numbered headings throughout (`## 1. ...`, `### 2.1 ...`) - violated
   markdown-guidelines.md's "avoid headers starting with numbers" rule. Stripped the numbering from every
   heading in all five files (README.md's apparent matches are shell comments inside a code fence, not real
   headings - confirmed and left alone). `docs/cli-spec.md`'s numbered `store-in-gmail` section (was
   `### 2.9`) was referenced by exact section number ("§2.9") from four other places (`CLAUDE.md` x2,
   `docs/reverse-import-plan.md`, `tasks/T0002-gmail-restore-import.md`) - updated all four to reference it
   by name instead of number. Also fixed `docs/devops.md`'s CI section, which claimed a
   "Python 3.11, 3.12, 3.13 on Ubuntu and Windows" matrix that doesn't exist - `.github/workflows/ci.yml`
   only ever ran a single Ubuntu/3.11 job; corrected the doc to describe the actual job.
6. `docs/requirements.md`'s "Technical Requirements & Invariants" claimed "3rd Party dependencies limited
   to: Python and SQLite" - factually wrong: `pyproject.toml` depends on `google-api-python-client`,
   `google-auth-httplib2`, `google-auth-oauthlib` (Gmail API access), and `PyYAML` (Markdown export
   frontmatter). Corrected the stale requirement and added a short justification for each dependency.
7. `.gitignore` was missing `.vscode/`/`.idea/` (python-project-template has both) - added them.

### Out of Scope

- Fixing python-project-template itself (it has the same CI-only-tests-3.11-despite->=3.10 gap as
  mail-utils did) - that's a different repo; logged as a finding in *its own* `TODO.md` instead, per the
  cross-project-findings convention, rather than touched here.
- The apparent drift between the user's global `~/.claude/CLAUDE.md` "Dev Guidelines" section and
  dev-guidelines' actual latest commit - a personal-config sync question for the user, not a mail-utils
  code change. Flagged to the user directly instead of acted on here.

### Dependencies

None.

### Completion Criteria

All 7 scope items fixed, lint/format/tests green, and the cross-project finding logged in
python-project-template's `TODO.md`.

## Task Implementation and Verification Steps

- [x] [Read] Audited `pyproject.toml`, `.gitignore`, `.github/workflows/ci.yml`, and doc structure against
  dev-guidelines/python-project-template; scanned all Markdown docs for guideline violations - produced
  the 7-item Scope list above (straightforward, mechanical fixes once found, no further design decisions
  needed).
- [x] [Implement] Fixed `docs/devops.md` Python version text (item 1).
- [x] [Implement] Added `authors` to `pyproject.toml` (item 2).
- [x] [Implement] Added `classifiers` to `pyproject.toml` (item 3).
- [x] [Implement] Fixed `docs/index.md` heading levels (item 4).
- [x] [Implement] Stripped numbered headings from all 5 affected docs (plus 3 more found during
  re-verification - see Progress & Validation Log), fixed the CI-matrix claim, fixed the 4 stale `§2.9`
  references (item 5).
- [x] [Implement] Corrected `docs/requirements.md`'s dependency claim and justified each real dependency
  (item 6).
- [x] [Implement] Added `.vscode/`/`.idea/` to `.gitignore` (item 7).
- [x] [Doc] Logged the python-project-template CI/version-mismatch finding in that repo's own `TODO.md`
  (edited only - not committed there; that repo's own commit/push needs its own separate approval).
- [x] [Verify] Re-ran `ruff check .`, `ruff format --check .`, `pytest -q` after the `pyproject.toml`
  change - no new automated test coverage needed since these are documentation/metadata/packaging-config
  changes, not behavior changes. Also re-ran the heading-hierarchy/numbered-heading scan afterward to
  confirm the fixes stuck.
- [x] [Visual] N/A - no UI surface; documentation/metadata-only change.

## Progress & Validation Log

- 2026-08-27: Task created from the promoted A0008, scope defined from audit findings above.
- 2026-08-27: All 7 scope items fixed in `./work/T0010-project-guidelines-compliance`. While re-scanning
  after the cli-spec.md/devops.md heading fix, found the same numbered-heading violation also present in
  `docs/pst-support-plan.md`, `docs/thunderbird-import-plan.md`, and `docs/tutorial.md` - fixed those too
  rather than leaving a partial pass. Also found and fixed: `docs/devops.md`'s CI section claimed a
  3-version/2-OS matrix that never existed in `ci.yml`; four files held a `§2.9` reference to `cli-spec.md`
  that would have gone stale once that heading's numbering was removed. Logged the python-project-template
  finding in that repo's `TODO.md` (edit only, not committed - separate repo, separate approval needed).
- `ruff check .`: All checks passed. `ruff format --check .`: all files already formatted. `pytest -q`:
  152 passed, 2 skipped (the 2 skips are the local-fixture-file integration tests, expected in a fresh
  worktree). Re-ran the heading-hierarchy scan and the numbered-heading grep across all docs after the fix:
  zero remaining violations (README.md's numeric `#` matches confirmed to be shell comments inside a code
  fence, not real headings). Reviewer: solo AI agent, no PR - summary presented to the user for explicit
  permission before merging, per the "No PR, solo, AI Agent" review tier.

## Completion Record

- **Completed:** 2026-08-27
- **Summary:** Fixed all 7 audited compliance gaps against dev-guidelines/python-project-template, plus 3
  additional numbered-heading violations and a stale CI-matrix claim found during re-verification. Logged
  one cross-project finding in python-project-template's own `TODO.md`.
