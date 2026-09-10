#!/usr/bin/env python3
"""Install a specific GitHub release version of this project.

Reads the project name from pyproject.toml and the repository URL from git remote,
constructs the release wheel URL, and installs it using pipx (recommended for
CLI tools, with --global) or pip.

Usage:
  python scripts/install-from-github-release.py <version> [--global]
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _cli_common import build_action_parser, get_project_version, print_help, print_version

PROG = "install-from-github-release"
DESCRIPTION = (
    "Install a specific GitHub release version of this project. "
    "Use --global to install system-wide via pipx (preferred for CLI tools) "
    "or pip --user as a fallback."
)
VERSION = get_project_version()
EXIT_CODES = [
    (0, "Success"),
    (1, "Bad arguments or missing tools"),
    (2, "Installation failed"),
]

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_capture(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()


def _read_pyproject() -> tuple[str, str]:
    """Return (project_name, current_version) from pyproject.toml."""
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    name_m = re.search(r'^name\s*=\s*"([^"]+)"', text, re.MULTILINE)
    ver_m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not name_m or not ver_m:
        raise SystemExit("[ERROR] Cannot parse name/version from pyproject.toml")
    return name_m.group(1), ver_m.group(1)


def _get_github_repo() -> str:
    url = _run_capture(["git", "remote", "get-url", "origin"])
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    if not m:
        raise SystemExit(f"[ERROR] Cannot parse GitHub repo from remote URL: {url}")
    return m.group(1)


def _wheel_filename(pkg_name: str, version: str) -> str:
    """Construct the expected wheel filename for a pure-Python package."""
    normalized = pkg_name.replace("-", "_")
    return f"{normalized}-{version}-py3-none-any.whl"


def install_version(version: str, global_install: bool) -> int:
    project_name, _ = _read_pyproject()
    repo = _get_github_repo()
    wheel = _wheel_filename(project_name, version)
    url = f"https://github.com/{repo}/releases/download/v{version}/{wheel}"

    print(f"Project : {project_name}")
    print(f"Version : v{version}")
    print(f"Source  : {url}")
    print()

    if global_install:
        if shutil.which("pipx"):
            print("Installing globally with pipx (isolated environment)...")
            cmd = ["pipx", "install", url, "--force"]
        else:
            print("pipx not found — falling back to 'pip install --user'...")
            print("Tip: install pipx with 'pip install --user pipx' for better isolation.")
            cmd = [sys.executable, "-m", "pip", "install", "--user", url]
    else:
        print("Installing into current Python environment with pip...")
        cmd = [sys.executable, "-m", "pip", "install", url]

    print(f"  $ {' '.join(cmd)}")
    rc = subprocess.run(cmd, check=False).returncode
    if rc != 0:
        print(f"\n[ERROR] Installation failed (exit code {rc})")
        return 2

    print(f"\n[OK] {project_name} v{version} installed.")
    if global_install and shutil.which("pipx"):
        print(f"      Run '{project_name} version' to verify.")
    return 0


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(prog=PROG, description=DESCRIPTION, add_help=False)
    parser.add_argument("version", nargs="?", metavar="VERSION", help="Version to install, e.g. 3.1.1")
    parser.add_argument("-h", "--help", action="store_true", help="Show this help message and exit")
    parser.add_argument("-v", "--version", action="store_true", dest="show_version", help="Show script version and exit")
    parser.add_argument(
        "--global",
        action="store_true",
        dest="global_install",
        help="Install globally via pipx (recommended) or pip --user",
    )
    args = parser.parse_args()

    if args.show_version:
        print_version(PROG, VERSION)
        return 0
    if args.help:
        print_help(PROG, VERSION, DESCRIPTION, parser, EXIT_CODES)
        return 0
    if not args.version:
        print_help(PROG, VERSION, DESCRIPTION, parser, EXIT_CODES)
        print()
        print("[ERROR] <version> argument is required. Example: python scripts/install-from-github-release.py 3.1.1")
        return 1

    return install_version(args.version, args.global_install)


if __name__ == "__main__":
    sys.exit(main())
