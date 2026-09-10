---
id: T0040
owner: "@antigravity"
needs: []
branch: task/T0040-guidelines-template-compliance
worktree: ./work/T0040-guidelines-template-compliance
status: active
started: 2026-09-10
ended: —
---

# T0040: Guidelines and Template Compliance

## Goals

Align mail-utils with the latest dev-guidelines and python-project-template conventions. Fix CHANGELOG heading format, version fallback, missing doc directories, missing deploy script, missing test init, and CI action version.

## Task Execution Steps

- [ ] **[Implement]** Rename CHANGELOG active heading to `## v3.1.0-pre` and update legend.
- [ ] **[Implement]** Change `_get_version()` fallback to `"0.0.0+unknown"`.
- [ ] **[Implement]** Create `docs/adrs/.gitkeep` and `docs/issues/.gitkeep`.
- [ ] **[Implement]** Update `docs/index.md` to reference `adrs/` and `issues/`.
- [ ] **[Implement]** Add placeholder `scripts/deploy-to-production.py`.
- [ ] **[Implement]** Create `tests/__init__.py`.
- [ ] **[Implement]** Bump `actions/setup-python@v4` to `@v5` in CI workflow.
- [ ] **[Verify]**    Run ruff, pytest, and lint-markdown on edited files.
- [ ] **[Doc]**       Update CHANGELOG with compliance entry.

## Execution Log
