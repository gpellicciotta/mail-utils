# Reverse Import — Filesystem Exports Back Into Gmail/Outlook/Thunderbird

`mail-utils` today only moves mail in one direction: Gmail API / `.pst` / Thunderbird archive → local
SQLite → `export` to `.md`/`.eml` files on disk. This note investigates the opposite direction — starting
from files already on disk (either `mail-utils export`'s own output, or any other EML/mbox corpus) and
putting that mail back into a live mailbox — for each of the three ecosystems this project already
touches: Gmail, Outlook, and Thunderbird.

## tl;dr

- **Gmail:** technically works well via the Gmail API's `messages.import` method. The catch isn't
  feasibility, it's that `mail-utils` currently promises `gmail.readonly` as a hard invariant
  (`CLAUDE.md`) — restoring mail requires a write-capable OAuth scope, which is a deliberate scope
  decision this note deliberately does **not** make on its own. See [Decision needed](#decision-needed).
- **Outlook:** not something `mail-utils` should build itself. `.pst` is a proprietary binary format; the
  practical paths are a paid third-party converter (Aid4Mail, etc.) or driving Outlook itself via COM
  automation on Windows — never a from-scratch `.pst` writer.
- **Thunderbird:** already solved by an existing, free, actively-maintained add-on
  (ImportExportTools NG). No gap for `mail-utils` to fill here at all.
- **Data loss, independent of platform:** attachment *bytes* are gone. `mail-utils` has only ever stored
  attachment metadata (filename/type/size), never content (`gmail_client.parse_attachments`,
  `README.md`'s "Database contents"), and `export`'s `.eml` output reflects that — attachments show up
  only as an `X-Mail-Utils-Attachment` metadata header, not as a real MIME attachment part. Nothing can
  restore what was never captured. Restoring from `mail-utils export` output means restoring
  attachment-less messages; restoring from some *other* EML/mbox source that does carry attachments is
  unaffected by this limitation.

## Gmail

### How historical mail actually gets into a mailbox

Three mechanisms exist; only two matter for restoring a whole archive of old mail:

- **`users.messages.import`** — adds a message to the mailbox with the same scanning/classification Gmail
  applies to normal incoming SMTP mail (spam/phishing filters, categorization), but *without* actually
  sending anything and *without* SPF verification. Preserves the message's labels and its internal date;
  `internalDateSource` picks whether that date comes from the message's own `Date:` header, a `Received:`
  header, or "now" — for a restore, `dateHeader` is what keeps messages appearing on their original date
  instead of all landing "today". A `neverMarkSpam` flag exists specifically to suppress the spam-scanning
  side effect during bulk historical imports.
- **`users.messages.insert`** — behaves like a raw IMAP `APPEND`: drops the message straight into the
  mailbox, bypassing most of the scanning/classification `import` applies.
- **Plain IMAP `APPEND`** against `imap.gmail.com` — the non-API equivalent of `insert`, useful mainly
  because it needs no Google Cloud project/OAuth client of its own (just the existing Gmail account +
  an app password or OAuth2 IMAP token), which is how generic tools like `imapsync` and *IMAP Upload* do
  it.

For a `mail-utils`-native restore, `messages.import` with `internalDateSource=dateHeader` and
`neverMarkSpam=true` is the right primitive: it's the one method Google explicitly documents as
preserving both label assignment and the original date, which is exactly what round-tripping
`mail-utils export` output needs (its `.eml` files already carry a real `Date:` header and the labels as
an `X-Mail-Utils-Labels` metadata header that a restore command would translate back into label IDs via
`users.labels.list`/`.create`).

### Costs and limits

- **Quota:** both `import` and `insert` cost 25 quota units per call. The per-user rate limit is 250
  units/second (moving average), so roughly 10 messages/second sustained per account — a mailbox of
  50,000 messages is on the order of an hour and a half at the rate limit, well inside the 1,000,000,000
  units/day project-wide cap (not a practical constraint for a single personal mailbox).
- **Message size:** 150 MB per message (matches Gmail's normal send/receive limit).
- **Scopes:** `messages.import`/`.insert` accept the narrower `gmail.insert` scope — not the broad
  `mail.google.com` scope, and not `gmail.modify` either, though both of those also work. `gmail.insert`
  is the minimal correct scope for this specific capability.
- **Google Workspace bulk-migration path:** Workspace accounts (not applicable to this project's single
  personal Gmail account) have a dedicated Data Migration Service with its own 500 MB/2,500 MB-per-day
  bandwidth caps; irrelevant here but worth knowing it exists if this ever targets a Workspace mailbox.

### Decision needed

`CLAUDE.md` states plainly: *"Read-only is a hard design invariant, not just a default... Don't add
write/send/delete capability without explicitly discussing it first — that's a deliberate scope decision,
not an oversight."* A restore command is unambiguously a write capability — it requires adding
`gmail.insert` (or broader) to `config.py`'s `SCOPES`, which means every existing user re-consents via the
OAuth flow the next time they authenticate. This note stops short of proposing that scope change as a
foregone conclusion; it's flagged here as the one decision that actually gates whether any of the
implementation sketch below gets built.

### What survives the round trip, and what doesn't

| Data                          | Preserved via `messages.import`?                                         |
|--------------------------------|---------------------------------------------------------------------------|
| Body text/HTML                 | Yes                                                                       |
| Subject/From/To/Cc/Bcc/Date     | Yes (already real RFC 5322 headers in `mail-utils export`'s `.eml` files) |
| Original received date         | Yes, with `internalDateSource=dateHeader`                                |
| Labels                         | Yes, if translated from `X-Mail-Utils-Labels` to label IDs before import |
| Thread grouping                | Approximate — Gmail derives threads from `References`/`In-Reply-To`/normalized subject, not an explicit field, so a thread reassembles correctly only if those headers survived export (they do, since `.eml` output is a real RFC 5322 message) |
| Read/unread, starred           | Only if explicitly re-applied as labels (`UNREAD`, `STARRED`) after import — `mail-utils`'s DB does track `label_ids` per message today, so this is recoverable, just not automatic |
| Attachments                    | **No** — never captured in the first place (see tl;dr)                   |
| Original Gmail message ID      | No — Gmail assigns a new ID on import; the old one only survives as `X-Mail-Utils-ID` |

### Alternatives already out there (Gmail)

- **[GYB — Got Your Back](https://github.com/GAM-team/got-your-back)** (open source, GAM-team): the most
  directly relevant existing tool. Backs up a Gmail mailbox via the Gmail API into local `mbox`-plus-SQLite
  storage and can restore that same backup back into a Gmail account, including from a Google Takeover
  export. If the goal were simply "back up and restore my own Gmail account," GYB already does this
  end-to-end and is a reasonable recommendation on its own — `mail-utils` doesn't need to reinvent it
  for that narrow case.
- **`imapsync`**: general IMAP-to-IMAP sync tool with Gmail OAuth2 support; works for mbox/EML sources
  fed through an intermediate IMAP server, but is overkill for "just restore my own export."
- **IMAP Upload** (`imap-upload.sourceforge.net`): a small, focused tool specifically for uploading a
  local mbox file into an IMAP mailbox including Gmail — closer in spirit to what a `mail-utils restore`
  subcommand would be, but doesn't know about `mail-utils`'s own label/thread metadata conventions.

None of these know about `mail-utils`'s specific `.md`/`.eml` export format or its `X-Mail-Utils-*`
metadata headers, so picking one over building a native command is a trade of "less code to
maintain" against "loses the label/read-state round-trip that only `mail-utils`'s own metadata makes
possible."

## Outlook (.pst)

`.pst` is a proprietary, non-trivial binary format (the same NDB/LTP structure `mail_utils.outlook`
already parses *read-only*). Writing a valid `.pst` from scratch is a much bigger undertaking than
parsing one, and isn't a good fit for this project's "keep dependencies minimal" and "read-only by
design" posture. Realistic options, none of which involve `mail-utils` writing `.pst` bytes itself:

- **Aid4Mail** (commercial, Windows): converts 40+ mailbox formats including EML/mbox into `.pst`,
  Gmail, or IMAP directly. The most capable and most cited tool for this specific direction; not free.
- **Driving Outlook via COM automation** (Windows-only, no paid tool needed): since this project already
  runs on Windows and Outlook exposes a full COM automation interface, a script using `pywin32` could
  create a new `.pst` data file via `Outlook.Application` / `Namespace.AddStoreEx` and then call
  `MAPIFolder.Items.Add`/`olMailItem` (or import each `.eml` from disk into a folder Outlook manages) — no
  proprietary format to write directly, since Outlook itself does the writing. This is the only path here
  that doesn't require a commercial license, but it's Windows-and-Outlook-installed-only, and firmly out
  of scope unless Outlook restore is separately prioritized.
- Numerous smaller commercial "EML to PST converter" utilities exist (outlookfreeware.com,
  CoolUtils, eSoftTools, MailsDaddy, etc.) — same category as Aid4Mail, generally narrower and
  cheaper/freemium.

**Verdict:** not worth `mail-utils` building. If Outlook restore is ever needed, either point the user at
Aid4Mail or write a small separate COM-automation script — neither belongs inside this project's
read-only, dependency-light core.

## Thunderbird

Thunderbird already reads mbox natively, so "restore" is much less of a gap than the other two — the file
format `mail-utils` already exports as `.eml` is exactly what Thunderbird itself consumes.

- **[ImportExportTools NG](https://addons.thunderbird.net/en-us/thunderbird/addon/importexporttools-ng/)**
  (free, actively maintained, the spiritual successor to the older ImportExportTools add-on that
  `docs/thunderbird-import-plan.md` already references for the read side): right-click a folder →
  *Import EML Messages → All EML Messages From A Directory And Subdirectories*, or import a whole `mbox`
  file directly. It preserves the folder structure `mail-utils export` already lays out
  (`<YYYY>/<MM>/`), reconstructing an equivalent folder tree in Thunderbird.

**Verdict:** nothing for `mail-utils` to build. This is a five-minute manual operation with an existing,
well-maintained free add-on. Worth a doc pointer, not code.

## Resolution

All three open questions below were answered, and the resulting command shipped as T0002 — see
`docs/cli-spec.md`'s `store-in-gmail` entry and `tasks/T0002-gmail-restore-import.md` for the implementation record. This
section is kept as the historical record of the decision; treat the CLI spec as authoritative for current
behavior.

- **Gmail write scope**: approved, narrowly scoped to one command only (`STORE_IN_GMAIL_SCOPES` in
  `config.py`, requested only when that command runs — see `CLAUDE.md`'s read-only note).
- **Source**: restricted to `mail-utils`-native representations only, as this note originally
  recommended — but expanded from "EML export directory only" to *either* an EML export directory *or*
  the local database directly (skipping the export step entirely). Arbitrary foreign EML/mbox trees
  remain explicitly out of scope.
- **GYB**: decided against - a native command was preferred over routing through GYB's separate backup
  format, since it lets `mail-utils`'s own label/date metadata round-trip directly.
- The shipped command is named `store-in-gmail`, not `import-to-gmail`/`restore-gmail` as sketched below -
  renamed specifically to avoid being one word away from the existing (and semantically opposite)
  `import-gmail` command.
- Scope grew beyond the original sketch during implementation: `--filter` (same grammar as `export`),
  `--max-messages` (capped, resumable runs), a per-run tracking label, and quota-aware throttling with
  retry/backoff were all added - see the task file for the full rationale.

## Original sketch (superseded by the Resolution above)

1. Add `gmail.insert` to `config.py`'s `SCOPES` behind a clear, separate opt-in (e.g. only requested when
   the new command is actually used, or a `--i-understand-this-is-not-read-only` style explicit flag) so
   existing read-only-only usage isn't silently upgraded.
2. New `mail-utils import-to-gmail <path>` (or `restore-gmail`) subcommand: walks a directory of
   `mail-utils`-exported `.eml` files (reuse the same directory-walk logic `import-thunderbird` already
   has for a similar shape), parses each file's `X-Mail-Utils-Labels`/`X-Mail-Utils-ID` headers, resolves
   label names to Gmail label IDs (creating any that don't exist via `users.labels.create`), and calls
   `messages.import` with `internalDateSource=dateHeader`, `neverMarkSpam=true`.
3. Track already-restored `X-Mail-Utils-ID` values (e.g. a `restore_state` table, mirroring
   `sync_state`) so re-running the command is idempotent instead of duplicating messages Gmail's own
   dedup doesn't otherwise catch across a full-mailbox `import`.
4. Document explicitly, in `README.md` and the command's own `--help`, that attachments are not restored
   (nothing to restore from) and that restored messages get new Gmail message IDs.
5. Test against a disposable/sandbox Gmail account before ever pointing this at anything real.

## Open questions (resolved — see Resolution above)

- Does the user actually want a Gmail write path in `mail-utils`, given the explicit read-only design
  invariant? (Primary blocker — see [Decision needed](#decision-needed).)
- If yes: restore *from* `mail-utils export` output only, or from arbitrary EML/mbox trees too (the
  latter needs to handle messages with no `X-Mail-Utils-*` metadata at all — labels/date fall back to
  best-effort header parsing)?
- Is GYB (for pure Gmail-to-Gmail backup/restore, no `mail-utils`-specific metadata needed) sufficient for
  the user's actual use case, making a native command unnecessary?
