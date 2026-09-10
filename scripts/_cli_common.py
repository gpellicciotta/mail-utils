"""Shared CLI boilerplate for the standalone dev scripts under scripts/ - keeps their
version/help output consistent with each other and with mail_utils.cli's own
`{name} v{version} - {copyright}` + exit-codes template, per the CLI guideline.
"""

from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version
from pathlib import Path

APP_AUTHOR = "Giovanni Pellicciotta"

_REPO_ROOT = Path(__file__).resolve().parent.parent


def get_project_version() -> str:
    """Read the version from pyproject.toml so all scripts self-report consistently."""
    import re

    try:
        text = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if m:
            return m.group(1)
    except OSError:
        pass
    return "0.0.0+unknown"


def get_mail_utils_version() -> str:
    try:
        return _package_version("mail-utils")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def build_action_parser(prog: str, description: str, actions: list, default_action: str) -> argparse.ArgumentParser:
    """Builds an action-oriented parser with its own -h/--help/-v/--version, so the caller
    can print the shared version/help template instead of argparse's default output."""
    parser = argparse.ArgumentParser(prog=prog, description=description, add_help=False)
    parser.add_argument("action", nargs="?", default=default_action, choices=actions, help="Action to perform")
    parser.add_argument("-h", "--help", action="store_true", help="Show this help message and exit")
    parser.add_argument("-v", "--version", action="store_true", help="Show version information and exit")
    return parser


def print_version(prog: str, version: str) -> None:
    print(f"{prog} v{version} - Copyright (c) {APP_AUTHOR}")


def print_help(prog: str, version: str, description: str, parser: argparse.ArgumentParser, exit_codes: list) -> None:
    print_version(prog, version)
    print()
    print(description)
    print()
    parser.print_help()
    print("\nExit codes:")
    for code, meaning in exit_codes:
        print(f"  {code}  {meaning}")
