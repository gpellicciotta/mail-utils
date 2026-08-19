# gmail-ingest

Polls a personal Gmail account on a 30' schedule and indexes new messages into a
local SQLite database, using the Gmail API and OAuth 2.0.

Read-only: the app only requests the `gmail.readonly` scope. It never sends,
labels, or deletes anything.

## How it works

- **Auth**: OAuth 2.0 "Installed App" flow. The browser consent screen is
  needed **once**. After that, a refresh token cached in `token.json` is used
  to get new access tokens silently — scheduled/unattended runs need no
  browser.
- **Sync**: the first run does a full mailbox listing and records the
  mailbox's current `historyId`. Every later run uses the Gmail History API
  (`users().history().list`) to fetch only messages added since the last run,
  instead of re-scanning everything. If the stored `historyId` becomes too
  old for Gmail to diff from, the script automatically falls back to a full
  resync. Progress is logged to `logs/gmail_ingest.log` every 50 messages;
  during a full sync this includes a running `%` against the mailbox's
  reported message total (an upper bound, since that total includes
  Spam/Trash which the sync itself skips, so the percentage may cap out
  just below 100%).
- **Storage**: `gmail_index.db` (SQLite), table `messages` (id, thread_id,
  sender, recipient, subject, date, snippet, label_ids, body_text,
  fetched_at) plus a `sync_state` table tracking the last processed
  `historyId`. Upserts are keyed on Gmail's message id, so reruns are safe.

## Setup

### 1. Google Cloud Console (one-time)

1. Create/select a project at https://console.cloud.google.com/.
2. Enable the **Gmail API** (APIs & Services -> Enable APIs and services).
3. Configure the OAuth consent screen, now split across a few pages under
   **Google Auth Platform** in the console sidebar:
   - **Branding**: set an app name, user support email, and developer 
     contact email (your Gmail address works for both).
   - **Audience**: set user type **External**. Under **Test users**, click
     **+ Add users**, add your own Gmail address, and make sure you actually
     click **Save** (it's easy to type the email and click away without
     confirming, in which case it silently isn't added).
   - **Data Access**: click **Add or Remove Scopes** and add
     `.../auth/gmail.readonly`.
   - Leave **Publishing status** as **Testing** to start, but note: Google
     expires test users' refresh tokens after **7 days**. Since step 4 below
     sets up an unattended task running every 30 minutes, a 7-day-expiring
     token will silently break it. Once the interactive first run (step 3)
     works, switch **Publishing status -> In production**. `gmail.readonly`
     is a "sensitive" (not "restricted") scope, so this doesn't require
     Google's verification process for personal/low-usage use — you'll just
     see a one-time **"Google hasn't verified this app"** warning during
     consent (click **Advanced -> Go to \<app name\> (unsafe)**).
4. Create credentials: go to **Clients** -> **Create Client** -> Application
   type **Desktop app** -> Create.
   - Try to download the JSON (a download icon on the client's row, or a
     **Download JSON** button on the client's detail page). If you can't
     find a download button, just build the file yourself: note the
     **Client ID** and **Client secret** shown in the console, then create
     `credentials.json` in this project's root folder (next to this
     README) with:
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
     (`project_id` isn't required — the `google-auth-oauthlib` library only
     needs the fields above.)

**Troubleshooting**: if step 3 (first run) fails in the browser with
`Error 403: access_denied` / "has not completed the Google verification
process" / "can only be accessed by developer-approved testers", the
consent screen is still in Testing status and the signed-in Google account
isn't recognized as a test user. Double check you edited the **Audience**
page of the same Cloud project this client belongs to, that your email is
actually listed under Test users (and was saved), and that the browser is
signed into that same account during consent (use an incognito window if
you have multiple Google accounts logged in). Switching **Publishing
status -> In production** (see above) sidesteps the test-user list
entirely.

### 2. Python environment

```powershell
cd C:\Dev-Projects\gmail-ingest
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### 3. First run (interactive, does the one-time browser consent)

```powershell
.venv\Scripts\python -m gmail_ingest.main
```

A browser window opens for the Google consent screen. After approving,
`token.json` is created and the script does a full initial sync into
`gmail_index.db`. Check `logs/gmail_ingest.log` for a summary.

Run it again to confirm it now does an incremental sync with no browser
prompt.

### 4. Schedule it (Windows Task Scheduler)

Once step 3 works and `token.json` exists:

```powershell
.\register_task.ps1
```

This registers a "GmailIngest" task that runs every 30 minutes. Edit the
`-RepetitionInterval` in `register_task.ps1` before registering to change the
frequency, or adjust it afterwards in Task Scheduler.

To remove it later:

```powershell
Unregister-ScheduledTask -TaskName GmailIngest -Confirm:$false
```

## Project layout

```
gmail-ingest/
  gmail_ingest/
    auth.py             # OAuth credential loading/refresh
    gmail_client.py     # Gmail API calls + message parsing
    db.py               # SQLite schema and upsert helpers
    main.py             # Orchestrates a single sync run
    config.py           # Paths and scopes
  register_task.ps1     # One-time Task Scheduler registration
  requirements.txt
  credentials.json      # you provide this - gitignored
  token.json            # generated on first run - gitignored
  gmail_index.db        # generated - gitignored
  logs/                 # generated - gitignored
```

- **`config.py`**: defines every path used by the app (`credentials.json`,
  `token.json`, `gmail_index.db`, `logs/gmail_ingest.log`), all resolved
  relative to the project root, plus `SCOPES` (just `gmail.readonly`).
- **`auth.py`**: `get_credentials()` — loads `token.json` if present and
  returns it if still valid; refreshes it silently via the stored refresh
  token if expired; otherwise runs the one-time interactive
  `InstalledAppFlow` browser consent (using `credentials.json`) and writes
  the resulting `token.json`.
- **`gmail_client.py`**: thin wrapper around the Gmail API —
  `list_all_message_ids` (paginated full-mailbox listing, used for the
  initial sync), `list_changed_message_ids` (paginated `history.list`
  diffing, raises `HistoryExpiredError` on a 404 so the caller can fall
  back to a full resync), `fetch_message` (fetches one message with
  `format=full`, i.e. complete MIME structure and decoded body — not just
  headers/snippet), and `parse_message` (turns the raw Gmail API message
  into the flat dict that gets stored — see below for exactly what it
  keeps and drops).
- **`db.py`**: the SQLite schema (see below) and `init_db` /
  `get_sync_state` / `set_sync_state` / `upsert_message` helpers.
  `upsert_message` keys on Gmail's message `id`, so re-running never
  duplicates rows.
- **`main.py`**: orchestrates one run — sets up logging to
  `logs/gmail_ingest.log`, decides full vs. incremental sync based on
  whether `sync_state` already has a `last_history_id`, and drives the
  fetch/parse/upsert loop.

## Database contents

`gmail_index.db` has two tables.

### `messages`

One row per Gmail message, upserted by `id` (so reruns update rather than
duplicate rows). Columns, and exactly what each one holds:

| Column       | Source                          | Notes |
|--------------|----------------------------------|-------|
| `id`         | Gmail message id                 | Primary key. Stable per message. |
| `thread_id`  | Gmail thread id                  | Groups messages into a conversation. |
| `sender`     | `From` header, raw               | E.g. `"Jane Doe <jane@example.com>"` — not split into name/address. |
| `recipient`  | `To` header, raw                 | Only the `To` line. If you were only `Cc`'d (not `To`'d), your address won't appear here at all — see below. |
| `subject`    | `Subject` header, raw             | |
| `date`       | `Date` header, raw string         | As set by the *sending* client — not normalized, and not Gmail's own server-side receipt timestamp (`internalDate`, which this app doesn't currently capture). |
| `snippet`    | Gmail's own `snippet` field       | Gmail's short auto-generated preview (~100–200 chars) — separate from, and much shorter than, `body_text`. |
| `label_ids`  | Comma-joined `labelIds`           | Gmail's internal label IDs (e.g. `INBOX,UNREAD,IMPORTANT`). Custom user labels appear as opaque IDs like `Label_12345` — join against the `labels` table (below) to get display names. |
| `body_text`  | Decoded message body              | See "Body text" below. |
| `fetched_at` | Local clock, set on upsert        | When this app wrote/updated the row — not when the email was sent or received. |

**Body text**: `parse_message` walks the MIME tree and stores the full
decoded text of the *first* `text/plain` part it finds anywhere in the
message (not truncated — the whole plain-text body). If a message has no
`text/plain` part at all (HTML-only email), it falls back to storing the
raw `text/html` source **unparsed** — i.e. with all HTML tags still in it,
not converted to plain text. Only the primary text body is stored:

- **Attachments are never stored.** The Gmail API's `format=full` doesn't
  inline attachment bytes anyway (only an `attachmentId` you'd have to
  fetch separately with `attachments.get`), and this app doesn't do that.
  Attachment filenames aren't captured either.
- **Inline images and other non-text MIME parts are ignored.**
- If a message is `multipart/alternative` with both plain and HTML
  versions, only the plain-text version is kept.

**Bcc is not captured, at all.** `parse_message` only reads the `From` and
`To` headers out of the message; `Cc` and `Bcc` are never read, even when
present in `payload.headers`, so there's no column and no way to recover
them from this database. In practice `Bcc` is also usually stripped by
mail servers before delivery to non-Bcc'd recipients, so it often wouldn't
be present to capture in the first place — but even Gmail messages that do
retain `Cc` info (e.g. mail you sent) won't have it stored here, since
`Cc` is silently dropped by `parse_message` just like `Bcc`.

### `sync_state`

A simple key/value table (`key`, `value`). Currently only one row is used:
`last_history_id`, the mailbox `historyId` as of the last successful sync,
used to ask the Gmail History API for only what changed since then.

### `labels`

Maps Gmail label id -> display name (`id`, `name`), covering both system
labels (`INBOX`, `SENT`, ...) and the user's own custom labels. Refreshed
in full from `users().labels().list()` at the start of every run, so it
stays in sync with any label renames/additions. Used by
`python -m gmail_ingest.stats` to show real label names instead of opaque
`Label_NNNNNNN` ids — a database from before this table existed will just
show raw ids until it's synced again with the current code.

## Notes

- `credentials.json` and `token.json` are secrets and are gitignored. Never commit them.
- Gmail API personal-use quota (1B units/day) is far more than a 30-minute polling interval will ever use.
- To inspect stored messages: `sqlite3 gmail_index.db "select date, sender, subject from messages order by fetched_at desc limit 20;"`
  (requires the separate `sqlite3.exe` CLI). If you don't have that
  installed, `.venv\Scripts\python -m gmail_ingest.stats` prints summary
  stats (total message count, distinct threads, first/last indexed time,
  current `last_history_id`, and a label breakdown) using only Python's
  built-in `sqlite3` module — no extra install needed.

