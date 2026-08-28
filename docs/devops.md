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
  data/                     # Gitignored - credentials, account tokens, local SQLite databases
    google-cloud-mail-utils-app-credentials.json  # Shared OAuth client secret (see below)
    default-account.json    # An account's OAuth token - one file per account, see below
    mails.db                # Local SQLite mail database (default location; see --db)
    attachments/            # Attachment content cache (default location; see --db)
  logs/                     # Gitignored - runtime execution logs
    mail-utils.log          # Unified log file with UTC timestamps
```

Account selection (`--account`) and data storage (`--db`) are independent of each other - see "Gmail
Account Setup" below for what each file is and how to obtain it, and `docs/cli-spec.md` for the exact
flag semantics.

---

## Gmail Account Setup

Two different kinds of file are involved in authenticating against Gmail, and it's easy to conflate
them - they're deliberately decoupled and serve different purposes:

- **The app credential file** (`data/google-cloud-mail-utils-app-credentials.json`) identifies the
  *mail-utils application itself* to Google. It's an OAuth 2.0 "Desktop app" client secret, created once
  per installation in Google Cloud Console, and is **not tied to any specific Gmail account** - the same
  file is reused every time you authorize a new account (test or production).
- **An account file** (`data/<name>-account.json`, e.g. `data/default-account.json` or
  `data/tester-account.json`) is the OAuth token proving mail-utils is authorized to act as *one specific
  Gmail account*. Every account you want to use with mail-utils - a disposable test mailbox, your real
  mailbox, or several of each - gets its own account file, produced by `mail-utils prepare-gmail-account`.

### Obtaining the app credential file (one-time, per installation)

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and create a new project (or
   select an existing one) - the exact name doesn't matter, e.g. "mail-utils".
2. Under **APIs & Services → Library**, search for "Gmail API" and enable it for the project.
3. Under **APIs & Services → OAuth consent screen**, configure the consent screen (User Type "External"
   is fine for personal use). While the app is in **Testing** publishing status, only accounts explicitly
   added under **Audience → Test users** can complete consent - add every Gmail account you intend to
   authorize (test and production) to that list.
4. Under **APIs & Services → Credentials**, click **Create Credentials → OAuth client ID**, choose
   application type **Desktop app**, and create it.
5. Download the resulting client secret JSON and save it as
   `data/google-cloud-mail-utils-app-credentials.json` (create the `data/` directory if it doesn't exist
   yet).

This step only needs to be done once - every account file below reuses the same app credential file.

### Obtaining an account file (once per Gmail account)

```powershell
# Read-only account (default) - suitable for import/search/stats/export
.venv\Scripts\mail-utils prepare-gmail-account tester

# Also request write-capable scopes up front, for an account meant to be used with store-in-gmail
.venv\Scripts\mail-utils prepare-gmail-account tester --with-write
```

This opens a browser consent screen (sign in as the account you want to authorize), then saves the
resulting token to `data/tester-account.json` and prints the authenticated address back, so you can
confirm you signed into the account you meant to. Commands that talk to the Gmail API accept `--account
<name>` to select which account file to use; omitting it falls back to `data/default-account.json` if
that file exists.

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

## Gmail Testing, Isolation, and Recovery

`store-in-gmail` is the one command that writes to a live Gmail mailbox (see `CLAUDE.md`'s read-only
note). Every other command (`import`, `import-gmail`, `search`, `stats`, `export`) only ever requests the
`gmail.readonly` scope and cannot write, label, or delete anything — they're safe to run directly against
any mailbox, including a real production one, with no special precautions.

### Testing against a disposable account, isolated from production

Accounts are named and independent (see "Gmail Account Setup" above), so isolation from production no
longer depends on which checkout/worktree a command happens to run from — it's just a matter of which
`--account` you pass:

1. Set up a disposable test account's account file once: `mail-utils prepare-gmail-account tester
   --with-write` (drop `--with-write` if you don't need to test `store-in-gmail` against it). Sign in as
   the **test** account, not production, at the browser consent screen.
2. Pass `--account tester` on every command you run against it (`import-gmail --account tester`,
   `store-in-gmail --account tester`, ...) - the production account's own `default-account.json` (or
   whatever you've named it) is never touched. Pair it with `--db` pointed at a scratch directory too, if
   you don't want test data mixed into your real database.

The OAuth client itself may still be in Google Cloud Console's **Testing** publishing status, which
restricts consent to accounts explicitly added under **APIs & Services → OAuth consent screen → Audience
→ Test users**. If sign-in fails with `Error 403: access_denied` ("has not completed the Google
verification process"), add the account being tested to that list — no new Cloud project or client is
needed.

### Recovery: undoing a `store-in-gmail` run

`store-in-gmail` only ever calls `messages.import` and `labels.create` — it never reads, modifies, or
deletes anything already in the mailbox. Recovery is therefore always scoped to "the messages this tool
itself wrote," never to pre-existing mail.

Every message stored in a given run carries a label unique to that run
(`mail-utils-store-in-gmail-<UTC timestamp>`), and the same mapping is recorded locally in the
`gmail_store_state` table (`message_id` -> the Gmail id it was stored as). To undo a run:

1. In Gmail's search box, search `label:mail-utils-store-in-gmail-<timestamp>` (the exact label name is
   logged by the command, and also readable from `sync_state` while a run is still in progress, or from
   any stored message's labels afterwards).
2. Select all results, move to Trash (or delete permanently, if immediate removal is wanted — Trash is a
   30-day safety net otherwise).
3. Optionally clear the corresponding rows from `gmail_store_state` in the local database, so a future
   `store-in-gmail` run would re-offer those messages as candidates rather than treating them as already
   stored (only relevant if you intend to store them again).

### Go-live checklist: running `store-in-gmail` against a real, non-disposable mailbox

Before ever running `store-in-gmail` against a mailbox you actually care about:

- [ ] The full A0006/T0013 checklist above has passed against a disposable test account (scopes, dates,
  labels, tracking label, `--max-messages` + resume, idempotency).
- [ ] `scripts/gmail-roundtrip-test.py`'s full seed/sync/export/store/re-sync/re-export/`compare` cycle
  (see the script's own docstring for the exact command sequence) has passed against a disposable test
  account - a stronger, byte-level check than the checklist item above, covering attachment content and
  message bodies/headers that the basic checklist doesn't exercise. This is what actually caught the
  Subject header round-trip bug fixed during T0013 - rerun it after any future change to
  `_build_eml_message`, `export`, or `store-in-gmail`.
- [ ] `ruff check`, `ruff format --check`, `pytest`, and `python -m build` all pass on the exact commit
  being run.
- [ ] `store-in-gmail --dry-run` has been run against the real target database and its output reviewed by
  eye — confirm the candidate list and label set are what's actually intended, especially if `--filter` is
  used.
- [ ] The target account is verified explicitly: at the browser consent screen, and again from the
  `Target account: ...` line `store-in-gmail` logs before writing anything — it's easy to be signed into
  the wrong Google account by default.
- [ ] If the OAuth client is still in Testing publishing status, the target account has been added as a
  Test user in Google Cloud Console beforehand, or consent will fail with `access_denied`.
- [ ] The first real run uses a small `--max-messages` cap; the resulting messages are spot-checked by hand
  in the mailbox (correct dates/labels/tracking label) before letting a full, uncapped run proceed.
- [ ] The Recovery section above has been read and is understood, in case anything needs to be undone.

## Development Guidelines

This project adheres to the [cross-project development guidelines](https://github.com/gpellicciotta/dev-guidelines) including coding standards, task coordination protocols, and CLI standards.


