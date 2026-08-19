# TODO

Ordered by priority.

1. No automated test suite yet. `gmail_client.parse_message`/`_extract_body_text`
   in particular are pure functions on API response dicts and would be easy
   to unit test without live Gmail credentials.
2. `Cc`/`Bcc` headers aren't captured — `parse_message` only reads `From`
   and `To`. Add `cc`/`bcc` columns and populate them from
   `payload.headers` (see `README.md`'s "Database contents" section for
   the current, documented limitation).
3. Stored `date` is the raw, client-supplied `Date` header — not
   normalized, and not Gmail's own reliable server-side `internalDate`.
   Capture `internalDate` (returned by `messages.get`) alongside it for
   trustworthy chronological sorting.
4. HTML-only messages (no `text/plain` part) are stored as raw, unparsed
   HTML in `body_text`. Convert to plain text (e.g. strip tags) instead.
5. Attachments aren't captured at all, not even filenames/sizes/mime
   types — only the primary text body is stored. Consider capturing
   attachment metadata (not necessarily the bytes themselves).
