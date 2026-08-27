# DevOps & Infrastructure Guide

This document covers setup, building, testing, linting, packaging, and CI/CD infrastructure for `mail-utils`.

---

## Local Environment & Dependencies

`mail-utils` requires Python 3.10+ and uses a standard `src/` layout. All project dependencies and tool configurations are defined in [`pyproject.toml`](../pyproject.toml). There is no separate `requirements.txt`.

### Bootstrap Setup

To create the virtual environment and install in editable mode with development dependencies:

```powershell
# Create virtual environment
python -m venv .venv

# Install package in editable mode with development tools (pytest, ruff, build)
.venv\Scripts\pip install -e ".[dev]"
```

Alternatively, run the automated bootstrap script (cross-platform - creates the virtual environment,
installs the dev extra, lints, tests, and builds distributable artifacts in one step):
```shell
python scripts/bootstrap-dev-environment.py
```

---

## Directory Layout & Data Separation

The repository strictly separates code, configuration, local databases, and runtime logs:

```
mail-utils/
  src/mail_utils/           # Application source code
    outlook/                # Zero-dependency [MS-PST] Unicode PST parser
    thunderbird/            # Zero-dependency Thunderbird Mbox / PCV parser
    auth.py                 # OAuth credential handling
    cli.py                  # CLI entry point and commands
    config.py               # Path definitions and scopes
    db.py                   # SQLite schema and FTS5 indexing
    filters.py              # Local query/filter interpreter
    gmail_client.py         # Gmail API client
    scheduling.py           # Cross-platform scheduler (Task Scheduler / cron)
  tests/                    # Pytest test suite and fixtures
    fixtures/               # Anonymized sample files (PST, PCV)
  docs/                     # Technical specifications and design documents
  data/                     # Gitignored - credentials, tokens, local SQLite databases
    credentials.json        # Google Cloud OAuth client credentials
    token.json              # Generated OAuth refresh/access token
    gmail.db                # Local SQLite mail database
  logs/                     # Gitignored - runtime execution logs
    mail-utils.log          # Unified log file with UTC timestamps
```

---

## Testing

The test suite uses `pytest` and contains unit tests, command tests, and integration tests with anonymized fixtures.

```powershell
# Run the entire test suite
.venv\Scripts\python -m pytest

# Run with verbose output
.venv\Scripts\python -m pytest -v

# Run a specific test module
.venv\Scripts\python -m pytest tests/test_search.py
```

### Test Strategy
- **Unit Tests (`test_cli.py`, `test_filters.py`, `test_search.py`, `test_thunderbird.py`, `test_pst_ndb.py`, `test_recursive_import.py`)**: Fast, pure-function tests using in-memory databases or temporary directories without external network calls.
- **Fixture Integration Tests (`test_pst_integration.py`, `test_thunderbird_integration.py`)**: Exercise end-to-end archive reading against committed anonymized binary fixtures in `tests/fixtures/`.

---

## Linting & Formatting

Code formatting and linting are handled by `ruff` with a maximum line length of 132 characters (configured in `pyproject.toml`).

```powershell
# Check for lint issues
.venv\Scripts\ruff check .

# Automatically fix lint issues where possible
.venv\Scripts\ruff check --fix .

# Verify code formatting
.venv\Scripts\ruff format --check .

# Reformat code
.venv\Scripts\ruff format .
```

---

## Building & Packaging

Build distribution artifacts (Source Distribution `.tar.gz` and Pure Python Wheel `.whl`):

```powershell
# Build distribution packages into dist/
.venv\Scripts\python -m build
```

The resulting packages will be placed in `dist/`:
- `dist/mail_utils-<version>.tar.gz`
- `dist/mail_utils-<version>-py3-none-any.whl`

---

## Continuous Integration (CI)

GitHub Actions runs automated checks on every push and pull request via [`.github/workflows/ci.yml`](../.github/workflows/ci.yml), on Ubuntu with Python 3.11:

- **Lint Check**: `ruff check .`
- **Format Check**: `ruff format --check .`
- **Test Suite**: `pytest`
- **Package Build**: `python -m build`

---

## Development Guidelines

This project adheres to the [cross-project development guidelines](https://github.com/gpellicciotta/dev-guidelines) including coding standards, task coordination protocols, and CLI standards.


