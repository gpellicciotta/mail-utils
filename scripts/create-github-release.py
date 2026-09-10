#!/usr/bin/env python3
"""Create and publish a GitHub release from the current repository state.

Reads the version from pyproject.toml, extracts release notes from CHANGELOG.md,
finalizes version files if still at -pre, creates a git tag, pushes to GitHub,
and creates a GitHub release. Then opens the next development version.

Usage:
  python scripts/create-github-release.py [release|version|help] [--dry-run]
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

# Allow importing _cli_common from the same scripts/ directory.
sys.path.insert(0, str(Path(__file__).parent))
from _cli_common import build_action_parser, get_project_version, print_help, print_version

PROG = "create-github-release"
DESCRIPTION = (
    "Create and publish a GitHub release from the current repository state. "
    "Reads version from pyproject.toml, extracts release notes from CHANGELOG.md, "
    "finalizes version files if still at -pre, tags, pushes, and creates the GitHub release. "
    "Then opens the next development version."
)
VERSION = get_project_version()
EXIT_CODES = [
    (0, "Success"),
    (1, "Precondition failed (dirty tree, missing tool, bad state)"),
    (2, "Release step failed"),
]

REPO_ROOT = Path(__file__).resolve().parent.parent


def _read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def _run(cmd: list[str], dry_run: bool) -> int:
    print(f"  $ {' '.join(cmd)}")
    if dry_run:
        return 0
    return subprocess.run(cmd, check=False).returncode


def _run_capture(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()


def _read_version(pyproject: Path) -> str:
    m = re.search(r'^version\s*=\s*"([^"]+)"', _read_file(pyproject), re.MULTILINE)
    if not m:
        raise SystemExit(f'[ERROR] Could not find version = "..." in {pyproject}')
    return m.group(1)


def _set_version(pyproject: Path, new_version: str, dry_run: bool) -> None:
    new_text = re.sub(
        r'^(version\s*=\s*)"[^"]+"',
        f'\\1"{new_version}"',
        _read_file(pyproject),
        flags=re.MULTILINE,
    )
    print(f'  [edit] {pyproject.name}: version = "{new_version}"')
    if not dry_run:
        _write_file(pyproject, new_text)


def _release_version(ver: str) -> str:
    return ver.removesuffix("-pre")


def _next_dev_version(release_ver: str) -> str:
    parts = release_ver.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts) + "-pre"


def _extract_changelog_notes(changelog: Path, release_ver: str) -> str:
    text = _read_file(changelog)
    # Match: ## v3.1.1   or   ## v3.1.1-pre   or   ## v3.1.1 [released: ...]
    m = re.search(rf"^## v{re.escape(release_ver)}(\s|$|-pre)", text, re.MULTILINE)
    if not m:
        raise SystemExit(
            f"[ERROR] No '## v{release_ver}' section found in CHANGELOG.md\n"
            "        Add the heading before releasing."
        )
    start = m.end()
    next_h = re.search(r"^## ", text[start:], re.MULTILINE)
    end = start + next_h.start() if next_h else len(text)
    return text[start:end].strip()


def _finalize_changelog_heading(changelog: Path, release_ver: str, today: str, dry_run: bool) -> None:
    text = _read_file(changelog)
    replacement = f"## v{release_ver} [released: {today}]"
    new_text = re.sub(rf"^## v{re.escape(release_ver)}-pre\b", replacement, text, flags=re.MULTILINE)
    if new_text == text:
        # Already finalized; verify the heading exists at all
        if not re.search(rf"^## v{re.escape(release_ver)}\b", text, re.MULTILINE):
            raise SystemExit(f"[ERROR] No '## v{release_ver}' or '## v{release_ver}-pre' in CHANGELOG.md")
        return
    print(f"  [edit] CHANGELOG.md: '## v{release_ver}-pre' -> '{replacement}'")
    if not dry_run:
        _write_file(changelog, new_text)


def _prepend_dev_changelog_heading(changelog: Path, next_ver: str, dry_run: bool) -> None:
    text = _read_file(changelog)
    sep = "\n---\n"
    idx = text.find(sep)
    if idx == -1:
        raise SystemExit("[ERROR] Could not find '---' separator in CHANGELOG.md")
    insert_at = idx + len(sep)
    new_text = text[:insert_at] + f"\n## v{next_ver}\n" + text[insert_at:]
    print(f"  [edit] CHANGELOG.md: inserted '## v{next_ver}' heading")
    if not dry_run:
        _write_file(changelog, new_text)


def _get_github_repo() -> str:
    url = _run_capture(["git", "remote", "get-url", "origin"])
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    if not m:
        raise SystemExit(f"[ERROR] Cannot parse GitHub repo from remote URL: {url}")
    return m.group(1)


def release(dry_run: bool) -> int:
    pyproject = REPO_ROOT / "pyproject.toml"
    changelog = REPO_ROOT / "CHANGELOG.md"
    today = date.today().strftime("%Y-%m-%d")

    current_ver = _read_version(pyproject)
    release_ver = _release_version(current_ver)
    next_dev_ver = _next_dev_version(release_ver)
    needs_finalize = current_ver.endswith("-pre")

    print(f"Release version : v{release_ver}")
    print(f"Next dev version: v{next_dev_ver}")
    print(f"Dry run         : {dry_run}")
    print()

    # Check working tree
    dirty_out = _run_capture(["git", "status", "--porcelain"])
    dirty_files = {ln[3:].strip() for ln in dirty_out.splitlines()} if dirty_out else set()
    allowed = {"pyproject.toml", "CHANGELOG.md"} if needs_finalize else set()
    unexpected = dirty_files - allowed
    if unexpected:
        print(f"[ERROR] Uncommitted changes in: {', '.join(sorted(unexpected))}")
        print("        Commit or stash them before releasing.")
        return 1

    # Check gh CLI
    try:
        _run_capture(["gh", "--version"])
    except Exception:
        print("[ERROR] 'gh' CLI is not installed — see https://cli.github.com/")
        return 1

    repo = _get_github_repo()
    notes = _extract_changelog_notes(changelog, release_ver)
    note_lines = notes.splitlines()
    print(f"GitHub repo     : {repo}")
    print(f"Release notes   : {len(note_lines)} lines")
    for line in note_lines[:6]:
        print(f"  {line}")
    if len(note_lines) > 6:
        print(f"  ... ({len(note_lines) - 6} more lines)")
    print()

    # Step 1: finalize -pre if needed
    if needs_finalize:
        print("--- Step 1: Finalize version ---")
        _finalize_changelog_heading(changelog, release_ver, today, dry_run)
        _set_version(pyproject, release_ver, dry_run)
        if _run(["git", "add", "CHANGELOG.md", "pyproject.toml"], dry_run) != 0:
            return 2
        if _run(["git", "commit", "-m", f"Released v{release_ver}."], dry_run) != 0:
            return 2
        print()

    # Step 2: tag and push
    print(f"--- Step 2: Tag and push v{release_ver} ---")
    if _run(["git", "tag", f"v{release_ver}"], dry_run) != 0:
        return 2
    if _run(["git", "push", "origin", "main"], dry_run) != 0:
        return 2
    if _run(["git", "push", "origin", f"v{release_ver}"], dry_run) != 0:
        return 2
    print()

    # Step 3: GitHub release
    print(f"--- Step 3: Create GitHub release v{release_ver} ---")
    if _run(["gh", "release", "create", f"v{release_ver}", "--title", f"v{release_ver}", "--notes", notes], dry_run) != 0:
        return 2
    print()

    # Step 4: open next dev version
    print(f"--- Step 4: Open v{next_dev_ver} ---")
    _prepend_dev_changelog_heading(changelog, next_dev_ver, dry_run)
    _set_version(pyproject, next_dev_ver, dry_run)
    if _run(["git", "add", "CHANGELOG.md", "pyproject.toml"], dry_run) != 0:
        return 2
    if _run(["git", "commit", "-m", f"Opened v{next_dev_ver} development after releasing v{release_ver}."], dry_run) != 0:
        return 2
    if _run(["git", "push", "origin", "main"], dry_run) != 0:
        return 2
    print()

    if dry_run:
        print("[DRY RUN] No changes were made.")
    else:
        print(f"[OK] v{release_ver} released — https://github.com/{repo}/releases/tag/v{release_ver}")
    return 0


def main() -> int:
    parser = build_action_parser(PROG, DESCRIPTION, ["release", "version", "help"], "release")
    parser.add_argument("--dry-run", action="store_true", help="Print every step without making any changes")
    args = parser.parse_args()

    if args.version or args.action == "version":
        print_version(PROG, VERSION)
        return 0
    if args.help or args.action == "help":
        print_help(PROG, VERSION, DESCRIPTION, parser, EXIT_CODES)
        return 0

    return release(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
