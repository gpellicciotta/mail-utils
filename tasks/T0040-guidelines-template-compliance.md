---
id: T0040
owner: "@antigravity"
needs: []
branch: task/T0040-guidelines-template-compliance
worktree: ./work/T0040-guidelines-template-compliance
status: completed
started: 2026-09-10
ended: 2026-09-10
---

# T0040: Guidelines and Template Compliance

## Goals

Align mail-utils with the latest dev-guidelines and python-project-template conventions. Fix CHANGELOG heading format, version fallback, missing doc directories, missing deploy script, missing test init, and CI action version. Then close all remaining template gaps: pyproject license/urls/ruff-lint, version -pre suffix, CI matrix/permissions/artifacts, publish workflow, docs index guidelines section, and gitignore improvements.

## Task Execution Steps

- [x] **[Implement]** Rename CHANGELOG active heading to `## v3.1.0-pre` and update legend.
- [x] **[Implement]** Change `_get_version()` fallback to `"0.0.0+unknown"`.
- [x] **[Implement]** Create `docs/adrs/.gitkeep` and `docs/issues/.gitkeep`.
- [x] **[Implement]** Update `docs/index.md` to reference `adrs/` and `issues/`.
- [x] **[Implement]** Add placeholder `scripts/deploy-to-production.py`.
- [x] **[Implement]** Create `tests/__init__.py`.
- [x] **[Implement]** Bump `actions/setup-python@v4` to `@v5` in CI workflow.
- [x] **[Implement]** Add `license` field and `[project.urls]` to `pyproject.toml`.
- [x] **[Implement]** Pin `[tool.ruff.lint] select` rules and fix version to `3.1.0-pre` in `pyproject.toml`.
- [x] **[Implement]** Add `permissions: contents: read`, Python 3.10+3.11 matrix, and `upload-artifact` to CI.
- [x] **[Implement]** Add `publish.yml` release workflow.
- [x] **[Implement]** Add Guidelines section to `docs/index.md` linking all four guideline docs.
- [x] **[Implement]** Add `.coverage`, `htmlcov/` and improve `*.log` → `**/*.log` in `.gitignore`.
- [x] **[Verify]**    Run ruff, pytest, and lint-markdown on edited files.
- [x] **[Doc]**       Update CHANGELOG with compliance entries.

## Execution Log

- [2026-09-10] **[Complete]**
  First pass (steps 1–7) implemented by a previous run without checking the step boxes.
  Second pass (steps 8–15) closed remaining template gaps versus python-project-template and hinolugi-support.python.
  Ruff clean, pytest 276 passed 2 skipped. Solo AI agent review tier — summary presented; human approved continuation.
