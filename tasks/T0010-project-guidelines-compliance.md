# T0010: Bring the project into full compliance with dev-guidelines and python-project-template

- **Status:** Completed
- **Owner:** claude
- **Started:** 2026-08-27
- **Branch:** task/T0010-project-guidelines-compliance
- **Worktree:** ./work/T0010-project-guidelines-compliance

## Goal

Promoted from A0008 (originally just "reconcile the minimum Python version") after the user asked for a
full compliance pass against [dev-guidelines](https://github.com/gpellicciotta/dev-guidelines) and
[python-project-template](https://github.com/gpellicciotta/python-project-template). An actual audit
(diffing `pyproject.toml`, `.gitignore`, `.github/workflows/ci.yml`, and doc structure against the
template, plus scanning all Markdown docs for guideline violations) turned up more than the single
version mismatch, so this became a real multi-file task rather than a one-sitting adhoc fix.

## Scope

Findings from the audit, all to be fixed in this task:

1. `docs/devops.md` says "Python 3.11+" while `pyproject.toml`'s `requires-python` says `>=3.10` and CI
   only actually tests 3.11 - align docs/devops.md to `>=3.10` (matching pyproject.toml and matching
   python-project-template's own docs/devops.md, which says "Python 3.10+"). The original A0008 finding.
2. `pyproject.toml` has no `authors` field - general-guidelines.md requires a single source of truth for
   vendor/author metadata in the build config; currently nothing in `pyproject.toml` carries it at all.
   Add `authors = [{name="Giovanni Pellicciotta", email="giovanni.pellicciotta@gmail.com"}]`, matching
   python-project-template.
3. `pyproject.toml` has no `classifiers` - python-project-template has
   `Programming Language :: Python :: 3` / `License :: OSI Approved :: MIT License` /
   `Operating System :: OS Independent`. Add the same (mail-utils is also MIT-licensed).
4. `docs/index.md` skips a heading level (H1 straight to H3 for "Core Documentation" / "Design & Technical
   Plans" / "Root References") - violates markdown-guidelines.md's "maintain a logical heading hierarchy
   without skipping levels". Bump those three to H2.
5. `docs/cli-spec.md`, `docs/devops.md`, `docs/pst-support-plan.md`, `docs/thunderbird-import-plan.md`, and
   `docs/tutorial.md` all use numbered headings throughout (`## 1. ...`, `### 2.1 ...`) - violates
   markdown-guidelines.md's explicit "Avoid headers starting with numbers" rule. Strip the numbering from
   every heading in all five files (README.md's apparent matches are shell comments inside a code fence,
   not real headings - left alone). `docs/cli-spec.md`'s numbered `store-in-gmail` section (was `### 2.9`)
   was referenced by exact section number ("§2.9") from four other places (`CLAUDE.md` x2,
   `docs/reverse-import-plan.md`, `tasks/T0002-gmail-restore-import.md`) - updated all four to reference it
   by name instead of number so they don't go stale.
   Also: `docs/devops.md`'s CI section claimed a "Python 3.11, 3.12, 3.13 on Ubuntu and Windows" matrix that
   doesn't exist - `.github/workflows/ci.yml` only ever ran a single Ubuntu/3.11 job. Corrected the doc to
   describe the actual job instead of fabricating a matrix to match the false claim.
6. `docs/requirements.md`'s "Technical Requirements & Invariants" claims "3rd Party dependencies limited
   to: Python and SQLite" - factually wrong today: `pyproject.toml` depends on `google-api-python-client`,
   `google-auth-httplib2`, `google-auth-oauthlib` (Gmail API access), and `PyYAML` (Markdown export
   frontmatter). general-guidelines.md requires each third-party dependency to have a documented reason
   it's technically OK and needed - none of these four currently do. Correct the stale requirement and add
   a short justification for each dependency.
7. `.gitignore` is missing `.vscode/`/`.idea/` (python-project-template has both) - add them for IDE-folder
   hygiene parity.

## Out of Scope

- Fixing python-project-template itself (it has the same CI-only-tests-3.11-despite->=3.10 gap as
  mail-utils did) - that's a different repo; log it as a finding in *its own* `TODO.md` instead, per the
  cross-project-findings convention, rather than touching it here.
- The apparent drift between the user's global `~/.claude/CLAUDE.md` "Dev Guidelines (synced from shared
  repository)" section and dev-guidelines' actual latest commit (`0ed9d27`, adding a "Changelog Management
  & Immutability" section) - that's a personal-config sync question for the user, not a mail-utils code
  change, and the user's own more-detailed personal versioning section already takes precedence over the
  synced generic one for this project's `vNext`/freeze/release scheme. Flagged to the user directly instead
  of acted on here.

## Dependencies

None.

## Approach

Straightforward, mechanical fixes to the 5 files listed in Scope - no design decisions needed. Verify with
`ruff check`/`ruff format --check`/`pytest` after the `pyproject.toml` change (adding fields shouldn't
affect behavior, but the editable install should be re-verified), and re-run the heading-hierarchy/
numbered-heading scan afterward to confirm the fixes stuck.

## Implementation Checklist

- [x] Fix `docs/devops.md` Python version text (item 1)
- [x] Add `authors` to `pyproject.toml` (item 2)
- [x] Add `classifiers` to `pyproject.toml` (item 3)
- [x] Fix `docs/index.md` heading levels (item 4)
- [x] Strip numbered headings from all 5 affected docs, fix the CI-matrix claim, fix the 4 stale `§2.9`
      references (item 5)
- [x] Correct `docs/requirements.md`'s dependency claim and justify each real dependency (item 6)
- [x] Add `.vscode/`/`.idea/` to `.gitignore` (item 7)
- [x] Log the python-project-template CI/version-mismatch finding in that repo's own `TODO.md` (edited only
      - not committed there; that repo's own commit/push needs its own separate approval)
- [x] Re-run `ruff check .`, `ruff format --check .`, `pytest -q`

## Test Strategy

No new automated test coverage needed - these are documentation/metadata/packaging-config changes, not
behavior changes. Verification is: full lint/format/test pass, plus a manual re-scan of the doc set for
heading-hierarchy and numbered-heading violations.

## Completion Criteria

All 7 scope items fixed, lint/format/tests green, and the cross-project finding logged in
python-project-template's `TODO.md`.

## Progress Log

- 2026-08-27: Task created from the promoted A0008, scope defined from audit findings above.
- 2026-08-27: All 7 scope items fixed in `./work/T0010-project-guidelines-compliance`. While re-scanning
  after the cli-spec.md/devops.md heading fix, found the same numbered-heading violation also present in
  `docs/pst-support-plan.md`, `docs/thunderbird-import-plan.md`, and `docs/tutorial.md` - fixed those too
  rather than leaving a partial pass. Also found and fixed: `docs/devops.md`'s CI section claimed a
  3-version/2-OS matrix that never existed in `ci.yml`; four files held a `§2.9` reference to `cli-spec.md`
  that would have gone stale once that heading's numbering was removed. Logged the python-project-template
  finding in that repo's `TODO.md` (edit only, not committed - separate repo, separate approval needed).

## Validation Record

- `ruff check .`: All checks passed.
- `ruff format --check .`: all files already formatted.
- `pytest -q`: 152 passed, 2 skipped (the 2 skips are the local-fixture-file integration tests, which skip
  whenever the untracked personal `.pst`/`.pcv` fixtures aren't present locally - expected in a fresh
  worktree, not a regression; same 2 skip in the primary checkout when those files are absent there too).
- Re-ran the heading-hierarchy scan and the numbered-heading grep across all docs after the fix: zero
  remaining violations (README.md's numeric `#` matches are shell comments inside a code fence, confirmed
  not real headings).
- Reviewer: solo AI agent, no PR - summary presented to the user for explicit permission before merging,
  per the "No PR, solo, AI Agent" review tier.

## Completion Record

- **Completed:** 2026-08-27
- **Summary:** Fixed all 7 audited compliance gaps against dev-guidelines/python-project-template, plus 3
  additional numbered-heading violations and a stale CI-matrix claim found during re-verification. Logged
  one cross-project finding in python-project-template's own TODO.md.
