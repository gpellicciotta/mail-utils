# Tutorial

A short walkthrough for a first-time user, after "Setup" in the top-level README has already been completed
(venv created, `data/credentials.json` in place, dependencies installed).

## 1. Sanity-check the install

```powershell
.venv\Scripts\mail-utils --version
.venv\Scripts\mail-utils help
```

`--version` prints the installed version and copyright; add `--verbose` to also print the matching
`CHANGELOG.md` entry. `help` (or running with no subcommand at all) prints the subcommand list.

## 2. First import

```powershell
.venv\Scripts\mail-utils import
```

The first run opens a browser for the one-time Google consent screen, then does a full mailbox listing into
`data/gmail.db`. Every run after that is incremental (Gmail's History API), with no browser prompt. Progress
is logged to `logs/mail-utils.log`.

## 3. Look at what got indexed

```powershell
.venv\Scripts\mail-utils stats
```

Offline (no Gmail API calls) — reads `data/gmail.db` directly. Prints message/thread counts, top labels, and
top senders/recipients. See README's "Database contents" for exactly what each column holds.

## 4. Try the local filter syntax

`stats` and `export` both accept `--filter`, evaluated locally against the database (see README's "Filtering"
for the full grammar):

```powershell
.venv\Scripts\mail-utils stats --filter "from:example.com after:2026/01/01"
.venv\Scripts\mail-utils stats --filter "has:attachment"
```

## 5. Export a subset to read as markdown

Exporting the whole mailbox writes one `.md` file per message, which can be a lot — scope it with `--filter`
first:

```powershell
.venv\Scripts\mail-utils export .\export-test --filter "has:attachment after:2026/07/01"
```

Each file is a YAML frontmatter block (from/to/subject/labels/attachments/...) followed by the message body,
bucketed under `<output_dir>\<YYYY>\<MM>\`.

## 6. Schedule recurring imports

Once a manual `import` works end-to-end:

```powershell
.venv\Scripts\mail-utils schedule -- import
```

Registers a recurring `import` every 30 minutes (Windows Task Scheduler, or cron on Linux/macOS). See README's
"Scheduling" section for custom intervals, multiple named jobs (`--job-name`), and `unschedule`.
