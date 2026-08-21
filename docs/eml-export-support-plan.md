# EML Export Support Plan

Add an option to `mail-utils export` to export messages as standard RFC 5322 `.eml` files in addition to the existing `.md` Markdown files with YAML frontmatter.

## Background & Rationale

`mail-utils export` previously dumped messages solely as Markdown files with YAML frontmatter. While this format is convenient for text processing and human-readable notes, standard email clients (Thunderbird, Apple Mail, Outlook, etc.) and email processing toolchains work natively with standard RFC 5322 MIME `.eml` files.

Adding a `--format` option (`--format md` or `--format eml`) allows users to choose their desired export format, retaining `.md` as the default for 100% backward compatibility.

## Proposed Changes

### `mail_utils.cli`

- **CLI Options**:
  - Add `--format` / `-f` argument with `choices=["md", "eml"]`, defaulting to `"md"`.
  - Update `export` subcommand help text.
- **Export Logic**:
  - Extract `_export_message_md(path, ...)` and `_export_message_eml(path, ...)`.
  - In `_export_message_eml`:
    - Construct an `email.message.EmailMessage` using Python's standard library `email` module.
    - Set standard RFC 5322 headers: `Subject`, `From`, `To`, `Cc`, `Bcc`, `Date` (formatting from `internal_date_ms` via `email.utils.format_datetime` if raw `Date` header is absent).
    - Set metadata headers: `X-Mail-Utils-ID`, `X-Mail-Utils-Thread-ID`, `X-Mail-Utils-Labels`, and `X-Mail-Utils-Attachment` (recording metadata for any associated attachments).
    - Set body content with charset `utf-8` and MIME subtype matching `body_mime_type` (`text/html` or `text/plain`).
    - Write serialized RFC 5322 bytes to `<output_dir>/<YYYY>/<MM>/<safe_msg_id>.eml` (or `unknown/` if date is unavailable).

### Tests

- Update `tests/test_cli.py`:
  - Verify `build_parser()` parses `--format eml` and `--format md`.
  - Verify `_run_export` with `--format eml` creates valid `.eml` files in the correct year/month directories.
  - Verify headers (`Subject`, `From`, `To`, `Cc`, `Bcc`, `Date`, `X-Mail-Utils-ID`, `X-Mail-Utils-Labels`, `X-Mail-Utils-Attachment`) and bodies (plain text / HTML) parse accurately via `email.message_from_bytes`.
  - Verify `--filter` works with `--format eml`.
  - Verify scheduled commands with `mail-utils schedule -- export ... --format eml` validate correctly.

### Documentation & Release Notes

- Update `TODO.md` (remove item 1).
- Update `RELEASES.md` under `## vNext`.
- Update `README.md`, `CLAUDE.md`, and `docs/index.md`.

