# gmail-ingest

Polls a personal Gmail account on a schedule and indexes new messages into a local SQLite database, using the
Gmail API and OAuth 2.0.

Read-only: the app only requests the `gmail.readonly` scope. It never sends, labels, or deletes anything.

The app is cross-platform (verified in a `python:3.11-slim` Docker container; Windows is the primary dev
environment, so the setup commands below are PowerShell, but the underlying commands — `python -m venv`,
`pip install`, `gmail-ingest <command>` — work the same on Linux/macOS with their shell equivalents, including
`gmail-ingest schedule`, see "Scheduling" below).

## How it works

- **Auth**: OAuth 2.0 "Installed App" flow. The browser consent screen is needed **once**. After that, a
  refresh token cached in `token.json` is used to get new access tokens silently — scheduled/unattended runs
  need no browser.
- **Sync**: the first run does a full mailbox listing and records the mailbox's current `historyId`. Every
  later run uses the Gmail History API (`users().history().list`) to fetch only messages added since the last
  run, instead of re-scanning everything. If the stored `historyId` becomes too old for Gmail to diff from,
  the script automatically falls back to a full resync. Progress is logged to `logs/gmail_ingest.log` every 50
  messages; during a full sync this includes a running `%` against the mailbox's reported message total (an
  upper bound, since that total includes Spam/Trash which the sync itself skips, so the percentage may cap out
  just below 100%).
- **Storage**: `gmail_index.db` (SQLite) — see "Database contents" below for the full schema. Upserts are
  keyed on Gmail's message id, so reruns are safe.

## Setup

### 1. Google Cloud Console (one-time)

1. Create/select a project at https://console.cloud.google.com/.
2. Enable the **Gmail API** (APIs & Services -> Enable APIs and services).
3. Configure the OAuth consent screen, split across a few pages under **Google Auth Platform** in the console
   sidebar:
   - **Branding**: an app name, user support email, and developer contact email (your Gmail address works
     for both).
   - **Audience**: user type **External**. Under **Test users**, **+ Add users**, add your own Gmail address,
     and make sure you actually click **Save** — it's easy to type the email and click away without
     confirming, in which case it silently isn't added.
   - **Data Access**: **Add or Remove Scopes**, add `.../auth/gmail.readonly`.
   - Leave **Publishing status** as **Testing** to start, but note: Google expires test users' refresh tokens
     after **7 days**, which would silently break the unattended schedule set up in step 4. Once the
     interactive first run (step 3) works, switch **Publishing status -> In production**. `gmail.readonly` is
     a "sensitive" (not "restricted") scope, so this doesn't require Google's verification process for
     personal/low-usage use — you'll just see a one-time **"Google hasn't verified this app"** warning during
     consent (**Advanced -> Go to \<app name\> (unsafe)**).
4. Create credentials: **Clients** -> **Create Client** -> Application type **Desktop app** -> Create.
   - Try to download the JSON (a download icon on the client's row, or a **Download JSON** button on its
     detail page). If you can't find a download button, build the file yourself: note the **Client ID** and
     **Client secret** shown in the console, then create `credentials.json` in this project's root folder
     with:
     ```json
     {
       "installed": {
         "client_id": "YOUR_CLIENT_ID",
         "client_secret": "YOUR_CLIENT_SECRET",
         "auth_uri": "https://accounts.google.com/o/oauth2/auth",
         "token_uri": "https://oauth2.googleapis.com/token",
         "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
         "redirect_uris": ["http://localhost"]
       }
     }
     ```
     (`project_id` isn't required — `google-auth-oauthlib` only needs the fields above.)

**Troubleshooting**: if step 3 (first run) fails in the browser with `Error 403: access_denied` / "has not
completed the Google verification process" / "can only be accessed by developer-approved testers", the
consent screen is still in Testing status and the signed-in Google account isn't recognized as a test user.
Double check you edited the **Audience** page of the same Cloud project this client belongs to, that your
email is actually listed under Test users (and was saved), and that the browser is signed into that same
account during consent (use an incognito window if you have multiple Google accounts logged in). Switching
**Publishing status -> In production** (above) sidesteps the test-user list entirely.

### 2. Python environment

```powershell
cd C:\Dev-Projects\gmail-ingest
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
```

This installs the project (from `pyproject.toml`) plus its `dev` extra (`pytest`, `ruff`). If you don't need
to run tests, `.venv\Scripts\pip install -e .` is enough.

### 3. First run (interactive, does the one-time browser consent)

```powershell
.venv\Scripts\gmail-ingest import
```

A browser window opens for the Google consent screen. After approving, `token.json` is created and the script
does a full initial sync into `gmail_index.db`. Check `logs/gmail_ingest.log` for a summary. Run it again to
confirm it now does an incremental sync with no browser prompt.

### 4. Schedule it

Once step 3 works and `token.json` exists:

```powershell
.venv\Scripts\gmail-ingest schedule -- import
```

This registers a recurring `import` every 30 minutes (the default) — a Windows Scheduled Task named
`GmailIngest-default` on Windows, a crontab entry on Linux/macOS. See "Scheduling" below for custom intervals,
multiple named jobs, and removing one.

## Project layout

```
gmail-ingest/
  src/
    gmail_ingest/
      auth.py           # OAuth credential loading/refresh
      gmail_client.py   # Gmail API calls + message parsing
      db.py             # SQLite schema and upsert helpers
      filters.py        # Local --filter interpreter for stats/export
      scheduling.py     # Windows Task Scheduler / cron job registration
      cli.py             # Entry point: import/stats/export/schedule/unschedule/help
      config.py          # Paths and scopes
  tests/                     # pytest suite (pure-function tests, no live API)
  .github/workflows/ci.yml  # ruff + pytest + build, on push/PR
  pyproject.toml         # Project metadata, dependencies, ruff config
  RELEASES.md            # Version history
  TODO.md                 # Prioritized backlog
  CLAUDE.md
  credentials.json      # you provide this - gitignored
  token.json            # generated on first run - gitignored
  gmail_index.db        # generated - gitignored
  logs/                  # generated - gitignored
```

`src/` layout: the package lives under `src/gmail_ingest/`, not directly at the repo root. This is standard
modern Python packaging practice — it forces `pip install -e .` (and therefore tests) to exercise the
actually-installed package rather than accidentally importing whatever's in the current working directory,
which a flat root-level package layout can silently do instead.

- **`config.py`**: every path used by the app (`credentials.json`, `token.json`, `gmail_index.db`,
  `logs/gmail_ingest.log`), all resolved relative to the project root, plus `SCOPES` (just `gmail.readonly`).
- **`auth.py`**: `get_credentials()` — loads `token.json` if present and returns it if still valid; refreshes
  it silently via the stored refresh token if expired; otherwise runs the one-time interactive
  `InstalledAppFlow` browser consent (using `credentials.json`) and writes the resulting `token.json`.
- **`gmail_client.py`**: thin wrapper around the Gmail API — `list_all_message_ids` (paginated full-mailbox
  listing, used for the initial sync), `list_changed_message_ids` (paginated `history.list` diffing, raises
  `HistoryExpiredError` on a 404 so the caller can fall back to a full resync), `fetch_message` (fetches one
  message with `format=full`, i.e. complete MIME structure and decoded body — not just headers/snippet), and
  `parse_message` (turns the raw Gmail API message into the flat dict that gets stored — see "Database
  contents" below for exactly what it keeps and drops).
- **`db.py`**: the SQLite schema (see "Database contents" below) and `init_db`/`get_sync_state`/
  `set_sync_state`/`upsert_message` helpers. `upsert_message` keys on Gmail's message `id`, so re-running
  never duplicates rows.
- **`filters.py`**: the local (non-Gmail-API) `--filter` interpreter used by `stats`/`export`. See
  "Filtering" below.
- **`scheduling.py`**: pure command-construction (`build_windows_register_script`, `build_cron_line`, etc. —
  each testable without touching a real crontab/Task Scheduler) plus thin `subprocess`-calling wrappers, used
  by `cli.py`'s `schedule`/`unschedule`. See "Scheduling" below.
- **`cli.py`**: the entry point — `gmail-ingest <command>` once installed (equivalent to
  `python -m gmail_ingest.cli <command>`; see `pyproject.toml`'s `[project.scripts]`). Subcommands:
  - `import` — sets up logging, decides full vs. incremental sync based on whether `sync_state` already has a
    `last_history_id`, and drives the fetch/parse/upsert loop. With `--filter`, see "Filtering" below.
  - `stats` — reads `gmail_index.db` directly (no Gmail API calls, no credentials needed) and prints summary
    stats.
  - `export <output_dir>` — dumps every message as a `.md` file (offline, reads only `gmail_index.db`), one
    file per message under `<output_dir>/<YYYY>/<MM>/<message_id>.md` (bucketed by `internal_date_ms`;
    messages without one land under `<output_dir>/unknown/`). Each file is a YAML frontmatter block (id,
    thread_id, from/to/cc/bcc, subject, date, internal_date, labels resolved to names, attachments as
    filename/mime_type/size, body_mime_type — empty/null fields are omitted rather than written blank)
    followed by `---` and the message body. Reruns just overwrite files with identical content — messages
    are immutable, so there's nothing to reconcile.
  - `schedule`/`unschedule` — register/remove a recurring `import` or `export`. See "Scheduling" below.
  - `help` (or no subcommand at all) — prints usage.

  `import`, `stats`, and `export` all accept `--db <path>` to point at a database other than the default
  `gmail_index.db` — e.g. to maintain several independent databases, one per filter (see "Scheduling" below
  for the multi-job pattern this enables).

  `gmail-ingest --version` prints the installed version, read live from package metadata
  (`importlib.metadata.version("gmail-ingest")`) rather than a separately-maintained string, so it's always
  exactly what `pip` thinks is installed. `pyproject.toml`'s `version` field is the one place the version is
  actually written; bump it, add a matching `RELEASES.md` entry, and re-run `pip install -e .` to pick it up.

### Filtering

`import`, `stats`, and `export` all accept `--filter "..."`, using a Gmail-like syntax: `label:X`, `from:X`,
`to:X`, `cc:X`, `bcc:X`, `subject:X`, `after:YYYY/MM/DD`, `before:YYYY/MM/DD`, `has:attachment`, and bare
words/`"quoted phrases"` (substring match against subject + body). Multiple tokens are ANDed together, e.g.
`--filter 'label:Work from:jane after:2026/01/01 has:attachment'`.

**The three subcommands don't interpret this identically**, and that's deliberate rather than an oversight:

- `import --filter` passes the string **straight through to Gmail's own search** (`list_all_message_ids`'s
  `q` parameter) — so it actually gets Gmail's full query grammar (`OR`, negation, etc.), not just the subset
  listed above. This runs a **filtered full listing** instead of incremental sync, and deliberately does
  **not** update `sync_state`/`last_history_id`, so it can't interfere with your regular unfiltered `import`
  runs' incremental bookkeeping. You can run a sequence of differently-filtered imports to build up a database
  containing just the subsets of your mailbox you care about; each run only adds/updates rows matching its
  own filter (upserts never delete), so the database accumulates the *union* across runs.
- `stats --filter` and `export --filter` are evaluated **locally**, in `gmail_ingest/filters.py`, against
  columns already in the database — they never call the Gmail API. This only supports the token subset listed
  above (no `OR`, no negation, no other Gmail operators); an unrecognized `key:` prefix is a hard error rather
  than being silently ignored, so a filter that matches nothing can't masquerade as one that matches
  everything.
- `label:` matches an exact (case-insensitive) resolved label name. `from:`/`to:`/`cc:`/`bcc:` match
  substrings of either the address or display name, using the `message_addresses` table (so they only work on
  rows synced after that table existed — see the caveat under "Database contents"). `after:`/`before:`
  compare against `internal_date_ms` (UTC midnight boundaries, `after` inclusive/`before` exclusive) and never
  match a row where it's `NULL`. `has:attachment` checks membership in the `attachments` table.

### Scheduling

`gmail-ingest schedule` registers a recurring `import` or `export` — a Windows Scheduled Task on Windows, a
crontab entry on Linux/macOS (also expected to work on macOS, though only Linux has actually been tested, in
a `python:3.11-slim` container). Any flags belonging to the inner command (`--filter`, `--db`, an `export`
output directory, ...) go after a literal `--`, since otherwise there's no way to tell them apart from
`schedule`'s own flags:

```powershell
gmail-ingest schedule --job-name work --interval-minutes 15 -- import --filter "label:Work" --db work.db
gmail-ingest schedule --job-name nightly-export --interval-minutes 1440 -- export C:\exports --filter has:attachment
gmail-ingest schedule --list
gmail-ingest unschedule --job-name work
```

- `--job-name` (default `default`) identifies the job — Task Scheduler task `GmailIngest-<job-name>`, or a
  crontab line tagged with a trailing `# gmail-ingest:<job-name>` marker comment. Multiple job names can
  coexist, so you can run several independently-filtered imports (into different `--db` files) or exports
  side by side. Re-running `schedule` with the same job name replaces that job; different job names don't
  touch each other.
- `--interval-minutes` (default 30). **Windows** accepts any positive value — Task Scheduler's repetition
  interval is true elapsed time. **cron** cannot express an arbitrary interval — its minute/hour/day fields
  are independent modulo-wheels, not elapsed time — so values are translated to plain cron fields and
  rejected with a clear error if they don't divide evenly: under 60 must divide 60 (1, 2, 3, 4, 5, 6, 10, 12,
  15, 20, 30, ...), a whole number of hours must divide 24 (1, 2, 3, 4, 6, 8, 12), and above that must be a
  whole number of days. (`--interval-minutes 1440` for a daily job is exactly the case that first exposed
  this — cron doesn't accept `*/1440` as a minute step, since minutes only run 0-59; it becomes `0 0 */1 * *`
  instead.)
- Only `import` and `export` can be scheduled — `stats` just prints to stdout, and `schedule`/`unschedule`/
  `help` recursively make no sense. The inner command is validated (parsed against `gmail-ingest`'s own
  argument definitions) *before* registering, so a typo'd flag fails immediately rather than at 3am.
- `schedule --list` / a bare `unschedule` don't need `--job-name` unless you want a specific one (default
  `default`); `--list` shows every currently-registered `GmailIngest-*` job.
- Windows registration shells out to PowerShell running `Register-ScheduledTask` with `-StartWhenAvailable`,
  `-DontStopOnIdleEnd`, and a 10-minute execution limit — a 10-year repetition duration is used for "runs
  indefinitely", since Task Scheduler's XML schema rejects `[TimeSpan]::MaxValue` outright.

## Development

```powershell
.venv\Scripts\python -m pytest      # run the test suite
.venv\Scripts\ruff check .          # lint
.venv\Scripts\ruff format .         # format (line-length 132, see pyproject.toml's [tool.ruff])
```

Tests live in `tests/` and cover the pure-function logic (`gmail_client.py`'s parsing, `filters.py`,
`scheduling.py`'s command-construction, `cli.py`'s argument routing) — no live Gmail credentials needed to run
them. CI (`.github/workflows/ci.yml`) runs all three, plus `python -m build`, on every push/PR.

## Database contents

`gmail_index.db` has five tables. Several columns/tables were added after the first version and are
populated **only going forward** — existing rows synced before that code shipped stay `NULL`/absent for the
new data until they're re-synced (a full resync, or a targeted re-fetch of specific messages); this caveat
applies to anything below beyond the original `messages` columns (id, thread_id, sender, recipient, subject,
date, snippet, label_ids, body_text, fetched_at) and `sync_state`, and is only spelled out again below where
it's otherwise non-obvious.

### `messages`

One row per Gmail message, upserted by `id` (so reruns update rather than duplicate rows):

| Column | Source | Notes |
|---|---|---|
| `id` | Gmail message id | Primary key. Stable per message. |
| `thread_id` | Gmail thread id | Groups messages into a conversation. |
| `sender` | `From` header, raw | E.g. `"Jane Doe <jane@example.com>"` — not split into name/address. |
| `recipient` | `To` header, raw | Only the `To` line. |
| `cc` | `Cc` header, raw | `NULL` if the message has no `Cc` line. |
| `bcc` | `Bcc` header, raw | See below — usually `NULL` even on messages that genuinely had Bcc recipients. |
| `subject` | `Subject` header, raw | |
| `date` | `Date` header, raw string | Set by the *sending* client — not normalized, can be missing/malformed, not trustworthy for sorting. Prefer `internal_date_ms`. |
| `internal_date_ms` | Gmail's `internalDate` | Epoch **milliseconds**, UTC — Gmail's own server-side receipt timestamp, reliable and always present (unlike `date`). `Date.fromtimestamp(internal_date_ms / 1000)` (Python) or `new Date(internal_date_ms)` (JS) converts it. |
| `snippet` | Gmail's `snippet` field | Short auto-generated preview (~100–200 chars) — separate from, and much shorter than, `body_text`. |
| `label_ids` | Comma-joined `labelIds` | Gmail's internal label IDs (e.g. `INBOX,UNREAD,IMPORTANT`). Custom labels appear as opaque `Label_12345` ids — join against `labels` (below) for display names. |
| `body_text` | Decoded message body | See "Body text" below. |
| `body_mime_type` | `"text/plain"` or `"text/html"` | Which MIME type `body_text` came from — see "Body text" below. `NULL` if there's no text part at all. |
| `fetched_at` | Local clock, set on upsert | When this app wrote/updated the row — not when the email was sent or received. |

**Body text**: `parse_message` stores the full decoded text of the *first* `text/plain` part found anywhere
in the message (not truncated), recording `body_mime_type = "text/plain"`. If there's no `text/plain` part at
all (HTML-only email), it falls back to the raw `text/html` source **unparsed** — tags and all, not converted
to plain text — with `body_mime_type = "text/html"` so that's distinguishable. Only the primary text body is
kept: attachment bytes are never stored (metadata only, in the `attachments` table below), inline images and
other non-text MIME parts are ignored, and a `multipart/alternative` message keeps only its plain-text half.

**Bcc is captured when it's actually present in the headers, which is rare.** `parse_message` reads `Bcc` the
same way it reads `Cc` — but mail servers (including Gmail, for mail delivered *to* you) almost always strip
`Bcc` before delivery to anyone but the Bcc'd addresses themselves, so most messages never carry one to
capture. The reliable exception is your own `Sent` mail: Gmail keeps `Bcc` in the copy it stores in your own
mailbox.

### `sync_state`

A key/value table (`key`, `value`). Currently one row: `last_history_id`, the mailbox `historyId` as of the
last successful (unfiltered) sync, used to ask the Gmail History API for only what changed since then.

### `labels`

Maps Gmail label id -> display name (`id`, `name`), covering system labels (`INBOX`, `SENT`, ...) and custom
ones. Refreshed in full from `users().labels().list()` at the start of every `import`, so it stays in sync
with renames/additions. Used by `stats`/`export` to show real label names instead of opaque `Label_NNNNNNN`
ids.

### `message_addresses`

One row per (message, role, address) — `message_id`, `role` (`from`/`to`/`cc`/`bcc`), `address`, `name`.
Unlike `messages.sender`/`recipient`/`cc`/`bcc` (raw, unparsed header strings), each individual address is
broken out and normalized (lowercased) here for reliable deduplication — `parse_addresses` does this via
`email.utils.getaddresses`, so `"Bob <bob@x.com>, \"Carl, Jr\" <CARL@x.com>"` becomes two separate rows.
`name` is whatever display name was on that particular message (not normalized — can vary by row for the same
address). Populated at ingest time alongside `upsert_message`, replacing that message's rows on every rerun.
`stats` reads this directly for its "Top senders"/"Top To/Cc/Bcc recipients" breakdowns.

### `attachments`

One row per MIME part that carries a filename — `message_id`, `attachment_id` (Gmail's id, for a later
`attachments.get` fetch if you ever want the bytes), `filename`, `mime_type`, `size`. Includes inline images,
not just conventional attachments — both show up as a filename on their MIME part, and since this only
captures metadata (never the bytes), there's no reason to treat them differently. Populated the same way as
`message_addresses`. `stats` shows a one-line total count and total size.

## Notes

- `credentials.json` and `token.json` are secrets and are gitignored. Never commit them.
- Gmail API personal-use quota (1B units/day) is far more than a 30-minute polling interval will ever use.
- To inspect stored messages with the separate `sqlite3.exe` CLI:
  `sqlite3 gmail_index.db "select date, sender, subject from messages order by fetched_at desc limit 20;"`.
  Without that installed, `gmail-ingest stats` covers the common cases using only Python's built-in `sqlite3`
  module.
