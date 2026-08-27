#!/usr/bin/env python3
"""Bootstraps a fresh mail-utils checkout: creates the virtual environment, installs the
project in editable mode with the dev extra, lints, tests, and builds distributable artifacts.

Cross-platform (Windows/Linux/macOS) - replaces the old Windows-only setup.ps1. Works on both
platforms since it only calls the venv's own python/pip executables, never assumes PowerShell.

Usage:
  python scripts/bootstrap-dev-environment.py
  python scripts/bootstrap-dev-environment.py --version
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from _cli_common import build_action_parser, print_help, print_version

PROG = "bootstrap-dev-environment"
DESCRIPTION = (
    "Creates the virtual environment, installs mail-utils in editable mode, lints, tests, and builds distributable artifacts."
)
EXIT_CODES = [(0, "Success"), (1, "One or more bootstrap steps failed")]
REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = REPO_ROOT / ".venv"
DATA_DIR = REPO_ROOT / "data"
DIST_DIR = REPO_ROOT / "bin" / "distributions"


def get_project_version() -> str:
    """Resolves the current project version from pyproject.toml."""
    pyproject = REPO_ROOT / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if match:
            return match.group(1).strip()
    return "0.0.0+unknown"


def venv_python() -> Path:
    """Returns the path to the venv's own python executable, cross-platform."""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def run_step(description: str, args: list) -> bool:
    """Runs one bootstrap step, printing its outcome. Returns whether it succeeded."""
    # flush=True keeps these headers in order relative to the child's own output when stdout
    # isn't a TTY (redirected to a file/pipe) - otherwise Python fully buffers stdout and the
    # child's directly-written output can appear before these headers.
    print(f"\n[*] {description}", flush=True)
    print("=" * 60, flush=True)
    result = subprocess.run(args, cwd=str(REPO_ROOT), check=False)
    if result.returncode != 0:
        print(f"[!] {description} failed (exit code {result.returncode})", flush=True)
    return result.returncode == 0


def setup() -> int:
    if not (REPO_ROOT / ".git").exists():
        run_step("Initializing git repository", ["git", "init"])

    # Ensure the (gitignored) data folder exists - credentials.json/token.json/*.db/logs/ all
    # live under it. Doesn't touch anything already there.
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    all_ok = True
    if not venv_python().exists():
        all_ok &= run_step("Creating virtual environment", [sys.executable, "-m", "venv", str(VENV_DIR)])

    python = str(venv_python())
    all_ok &= run_step("Upgrading pip", [python, "-m", "pip", "install", "--upgrade", "pip"])
    all_ok &= run_step("Installing project (editable, dev extra)", [python, "-m", "pip", "install", "-e", ".[dev]"])
    all_ok &= run_step("Linting (ruff check)", [python, "-m", "ruff", "check", "."])
    all_ok &= run_step("Checking formatting (ruff format --check)", [python, "-m", "ruff", "format", "--check", "."])
    all_ok &= run_step("Running unit tests (pytest)", [python, "-m", "pytest", "-q"])

    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    all_ok &= run_step("Building sdist + wheel", [python, "-m", "build", "-o", str(DIST_DIR)])

    return 0 if all_ok else 1


def main() -> int:
    version = get_project_version()
    parser = build_action_parser(PROG, DESCRIPTION, ["setup", "version", "help"], "setup")
    args = parser.parse_args()

    if args.version or args.action == "version":
        print_version(PROG, version)
        return 0
    if args.help or args.action == "help":
        print_help(PROG, version, DESCRIPTION, parser, EXIT_CODES)
        return 0

    return setup()


if __name__ == "__main__":
    sys.exit(main())
