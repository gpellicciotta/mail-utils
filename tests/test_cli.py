import argparse
import base64
import email
import logging
import sqlite3
from datetime import datetime
from email.policy import default as email_policy_default
from email.utils import getaddresses
from importlib.metadata import version as package_version
from pathlib import Path

import pytest
import yaml
from googleapiclient.errors import HttpError

from mail_utils import attachment_store, cli
from mail_utils.cli import (
    _eml_tree_candidates,
    _gmail_call_with_backoff,
    _parse_attachment_stub_header,
    _resolve_label_ids,
    _run_check_gmail_account,
    _run_export,
    _run_import,
    _run_import_eml,
    _run_import_gmail,
    _run_import_pst,
    _run_import_thunderbird,
    _run_prepare_gmail_account,
    _run_schedule,
    _run_stats,
    _run_store_in_gmail,
    _run_unschedule,
    _throttle_gmail_store,
    _validate_inner_command,
    build_parser,
)
from mail_utils.db import (
    get_sync_state,
    init_db,
    is_stored_in_gmail,
    upsert_addresses,
    upsert_attachments,
    upsert_labels,
    upsert_message,
)


class _FakeExec:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class _FakeResp:
    def __init__(self, status):
        self.status = status
        self.reason = "rate limit exceeded"


def _rate_limit_error(status=429):
    return HttpError(_FakeResp(status), b"rate limit exceeded")


class _FakeMessagesResource:
    def __init__(self, fail_first_n_imports=0):
        self.import_calls = []
        self._fail_remaining = fail_first_n_imports

    def import_(self, userId, body, internalDateSource, neverMarkSpam):
        if self._fail_remaining > 0:
            self._fail_remaining -= 1
            raise _rate_limit_error()
        self.import_calls.append(
            {"userId": userId, "body": body, "internalDateSource": internalDateSource, "neverMarkSpam": neverMarkSpam}
        )
        return _FakeExec({"id": f"new_gmail_id_{len(self.import_calls)}"})


class _FakeLabelsResource:
    def __init__(self, existing):
        self._existing = list(existing)
        self.create_calls = []

    def list(self, userId):
        return _FakeExec({"labels": list(self._existing)})

    def create(self, userId, body):
        self.create_calls.append(body)
        new = {"id": f"Label_{body['name']}", "name": body["name"]}
        self._existing.append(new)
        return _FakeExec(new)


class _FakeUsers:
    def __init__(self, existing_labels, fail_first_n_imports=0):
        self.messages_resource = _FakeMessagesResource(fail_first_n_imports)
        self.labels_resource = _FakeLabelsResource(existing_labels)

    def messages(self):
        return self.messages_resource

    def labels(self):
        return self.labels_resource

    def getProfile(self, userId):
        return _FakeExec({"emailAddress": "fake-target-account@example.com", "messagesTotal": 42, "threadsTotal": 7})


class _FakeService:
    def __init__(self, existing_labels=(), fail_first_n_imports=0):
        self.users_resource = _FakeUsers(existing_labels, fail_first_n_imports)

    def users(self):
        return self.users_resource


def _write_eml_export(path, **overrides):
    fields = {
        "msg_id": "msg1",
        "thread_id": "thread1",
        "sender": "jane@example.com",
        "recipient": "me@example.com",
        "cc": None,
        "bcc": None,
        "subject": "Hello",
        "date": "Wed, 19 Aug 2026 10:00:00 -0700",
        "internal_date_ms": None,
        "labels": ["INBOX"],
        "body_mime_type": "text/plain",
        "attachments": [],
        "body_text": "Body text",
        "body_html": None,
    }
    fields.update(overrides)
    cli._export_message_eml(path, **fields)


def _build_eml_message(**overrides):
    fields = {
        "msg_id": "msg1",
        "thread_id": None,
        "sender": "jane@example.com",
        "recipient": "me@example.com",
        "cc": None,
        "bcc": None,
        "subject": "Hello",
        "date": "Wed, 19 Aug 2026 10:00:00 -0700",
        "internal_date_ms": None,
        "labels": [],
        "body_mime_type": "text/plain",
        "attachments": [],
        "body_text": "Plain body",
        "body_html": None,
    }
    fields.update(overrides)
    return cli._build_eml_message(**fields)


def test_build_eml_message_preserves_both_bodies_as_multipart_alternative():
    msg = _build_eml_message(body_text="Plain body", body_html="<p>HTML body</p>")

    assert msg.get_content_type() == "multipart/alternative"
    assert msg.get_body(preferencelist=("plain",)).get_content().strip() == "Plain body"
    assert "<p>HTML body</p>" in msg.get_body(preferencelist=("html",)).get_content()


def test_build_eml_message_uses_html_only_when_no_plain_text():
    msg = _build_eml_message(body_text=None, body_html="<p>Only HTML</p>")

    assert msg.get_content_type() == "text/html"
    assert "<p>Only HTML</p>" in msg.get_content()


def test_build_eml_message_uses_html_only_when_body_text_is_the_html_fallback_duplicate():
    """For an html-only message, _extract_body_text's fallback puts the same raw HTML markup into
    body_text (with body_mime_type "text/html") that _extract_body_html also captures - body_text
    isn't genuinely plain text there, so it must not be wrapped as a bogus text/plain alternative
    (that would flip body_mime_type to text/plain on the next import, losing the html/plain distinction
    - caught via a real-account round-trip test)."""
    html = "<html><body><p>Only HTML</p></body></html>"
    msg = _build_eml_message(body_text=html, body_mime_type="text/html", body_html=html)

    assert msg.get_content_type() == "text/html"
    assert "<p>Only HTML</p>" in msg.get_content()


def test_build_eml_message_embeds_inline_image_with_matching_content_id(tmp_path, monkeypatch):
    attachment_store.configure(tmp_path / "attachments")
    digest = attachment_store.save(b"PNG bytes")

    msg = _build_eml_message(
        body_text="Plain body",
        body_html='<p>See <img src="cid:logo@example"></p>',
        attachments=[
            {
                "filename": "logo.png",
                "mime_type": "image/png",
                "size": 9,
                "content_sha256": digest,
                "content_id": "<logo@example>",
            }
        ],
    )

    html_part = msg.get_body(preferencelist=("html",))
    assert html_part.get_content_type() == "text/html"
    related_parts = [p for p in msg.walk() if p.get_content_type() == "image/png"]
    assert len(related_parts) == 1
    assert related_parts[0]["Content-ID"] == "<logo@example>"
    assert related_parts[0].get_content() == b"PNG bytes"
    assert related_parts[0].get_content_disposition() == "inline"
    assert related_parts[0].get_filename() == "logo.png"
    assert list(msg.iter_attachments()) == []


def test_build_eml_message_falls_back_to_regular_attachment_without_html_body(tmp_path, monkeypatch):
    """An inline image's content_id is only actionable once there's an HTML body to embed it into -
    without one (plain-text-only message), it must not be silently dropped."""
    attachment_store.configure(tmp_path / "attachments")
    digest = attachment_store.save(b"PNG bytes")

    msg = _build_eml_message(
        body_text="Plain body",
        body_html=None,
        attachments=[
            {
                "filename": "logo.png",
                "mime_type": "image/png",
                "size": 9,
                "content_sha256": digest,
                "content_id": "<logo@example>",
            }
        ],
    )

    attachment_parts = list(msg.iter_attachments())
    assert len(attachment_parts) == 1
    assert attachment_parts[0].get_filename() == "logo.png"
    assert attachment_parts[0].get_content() == b"PNG bytes"


def test_build_eml_message_quotes_unquoted_at_in_sender_display_name():
    # A real Thunderbird-sourced sender like "Panel @ InSites  <info@insitespanel.com>" has an
    # unquoted "@" in its display name (invalid per RFC 5322, but real archives contain it). Left
    # unquoted, Python's own modern email policy misparses the entire value on the way back through
    # import-eml, discarding the real address entirely - found via T0020's round-trip comparison.
    msg = _build_eml_message(sender="Panel @ InSites  <info@insitespanel.com>")

    assert getaddresses([str(msg.get("From"))]) == [("Panel @ InSites", "info@insitespanel.com")]


def test_build_eml_message_leaves_already_valid_addresses_untouched():
    msg = _build_eml_message(recipient="Kris Ceuppens <kris.ceuppens@astadia.com>, plain@example.com")

    assert getaddresses([str(msg.get("To"))]) == [
        ("Kris Ceuppens", "kris.ceuppens@astadia.com"),
        ("", "plain@example.com"),
    ]


def test_build_eml_message_preserves_non_utf8_text_attachment_bytes_exactly(tmp_path, monkeypatch):
    """A "text/*" attachment isn't guaranteed to be UTF-8 (e.g. a real Windows-1252-encoded .txt file
    from an old Outlook archive) - EmailMessage.add_attachment() decodes "text" maintype content as a
    string before re-encoding it, which silently corrupts any byte sequence that isn't valid under
    whatever charset it guesses (found via T0020's round-trip comparison: a captured attachment's
    content_sha256 differed after re-import even though nothing in mail-utils's own code touched the
    bytes in between). cli._lossless_attachment_type() must force a binary-safe maintype for anything
    outside image/audio/video/application, regardless of the captured mime_type."""
    attachment_store.configure(tmp_path / "attachments")
    non_utf8 = b"milestones for Gial \x96 August 2008"  # \x96 (Windows-1252 en dash) isn't valid UTF-8
    digest = attachment_store.save(non_utf8)

    msg = _build_eml_message(
        attachments=[
            {
                "filename": "notes.txt",
                "mime_type": "text/plain",
                "size": len(non_utf8),
                "content_sha256": digest,
                "content_id": None,
            }
        ],
    )

    attachment_parts = list(msg.iter_attachments())
    assert len(attachment_parts) == 1
    assert attachment_parts[0].get_content() == non_utf8


def _no_sleep(monkeypatch):
    """Stub out time.sleep so throttling/backoff in store-in-gmail tests don't slow the suite down."""
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)


class _IncrementingClock:
    """Fake `datetime` with a `.now()` that advances by a second on every call - used to guarantee two
    store-in-gmail invocations mint distinct tracking-label timestamps, since the real clock's one-second
    resolution could otherwise make two fast, back-to-back test runs collide on the same label name."""

    def __init__(self):
        self._n = 0

    def now(self, tz=None):
        self._n += 1
        return datetime(2026, 1, 1, 0, 0, self._n, tzinfo=tz)


def test_version_flag_parses():
    args = build_parser().parse_args(["--version"])
    assert args.version is True
    assert args.verbose is False


def test_print_version_shows_version_and_copyright(capsys):
    cli._print_version(verbose=False)
    out = capsys.readouterr().out
    assert out.splitlines() == [
        f"mail-utils v{package_version('mail-utils')} - Copyright (c) Giovanni Pellicciotta",
    ]


def test_print_version_verbose_includes_release_entry(tmp_path, monkeypatch, capsys):
    ver = package_version("mail-utils")
    monkeypatch.setattr(cli, "BASE_DIR", tmp_path)
    (tmp_path / "CHANGELOG.md").write_text(
        f"# Versioned Changes\n\n## v{ver}\nReleased on 2026-08-19\n\n- Did a thing.\n\n## v0.0.1\nOlder.\n",
        encoding="utf-8",
    )

    cli._print_version(verbose=True)

    out = capsys.readouterr().out
    assert "Did a thing." in out
    assert "v0.0.1" not in out
    assert f"## v{ver}" not in out


def test_main_handles_version_flag(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["mail-utils", "--version"])
    cli.main()
    out = capsys.readouterr().out
    assert out.startswith(f"mail-utils v{package_version('mail-utils')}")


def _log_record(created: float) -> logging.LogRecord:
    record = logging.LogRecord("mail_utils", logging.INFO, "test.py", 1, "hello world", None, None)
    record.created = created
    record.msecs = (created - int(created)) * 1000
    return record


def test_utc_formatter_uses_utc_time():
    record = _log_record(1735689600.5)  # 2025-01-01T00:00:00.5Z
    formatted = cli._UTCFormatter(cli._LOG_FORMAT).format(record)
    assert "2025-01-01 00:00:00" in formatted
    assert "UTC" in formatted


def test_console_formatter_omits_milliseconds():
    record = _log_record(1735689600.5)
    file_line = cli._UTCFormatter(cli._LOG_FORMAT).format(record)
    console_line = cli._UTCFormatter(cli._LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S").format(record)
    assert "," in file_line
    assert "," not in console_line


def test_import_subcommand_routes_to_run_import():
    args = build_parser().parse_args(["import"])
    assert args.command == "import"
    assert args.source_path is None
    assert args.filter is None
    assert args.func is _run_import


def test_import_subcommand_accepts_positional_source_path():
    args = build_parser().parse_args(["import", "path/to/archive.pst", "--filter", "label:Work"])
    assert args.command == "import"
    assert args.source_path == "path/to/archive.pst"
    assert args.filter == "label:Work"


def test_import_gmail_subcommand_routes_to_run_import_gmail():
    args = build_parser().parse_args(["import-gmail", "--filter", "label:Work"])
    assert args.command == "import-gmail"
    assert args.filter == "label:Work"
    assert args.func is _run_import_gmail


def test_prepare_gmail_account_subcommand_routes_and_parses():
    args = build_parser().parse_args(["prepare-gmail-account", "tester", "--with-write"])
    assert args.command == "prepare-gmail-account"
    assert args.name == "tester"
    assert args.with_write is True
    assert args.func is _run_prepare_gmail_account


def test_prepare_gmail_account_with_write_defaults_false():
    args = build_parser().parse_args(["prepare-gmail-account", "tester"])
    assert args.with_write is False


def test_check_gmail_account_subcommand_routes_and_parses():
    args = build_parser().parse_args(["check-gmail-account", "tester"])
    assert args.command == "check-gmail-account"
    assert args.name == "tester"
    assert args.func is _run_check_gmail_account


def test_store_in_gmail_subcommand_parses_and_routes():
    args = build_parser().parse_args(["store-in-gmail", "some/dir", "--dry-run", "--filter", "label:Work", "--max-messages", "5"])
    assert args.command == "store-in-gmail"
    assert args.source_dir == "some/dir"
    assert args.dry_run is True
    assert args.filter == "label:Work"
    assert args.max_messages == 5
    assert args.func is _run_store_in_gmail


def test_store_in_gmail_subcommand_source_dir_is_optional():
    args = build_parser().parse_args(["store-in-gmail"])
    assert args.source_dir is None
    assert args.max_messages is None


def test_eml_tree_candidates_yields_none_id_for_foreign_file(tmp_path, capsys):
    cli._setup_logging()
    foreign = tmp_path / "foreign.eml"
    foreign.write_bytes(b"From: a@example.com\r\nSubject: Not ours\r\n\r\nBody\r\n")

    (candidate,) = list(_eml_tree_candidates([foreign]))

    assert candidate[0] is None
    assert "no X-Mail-Utils-ID header" in capsys.readouterr().out


def test_eml_tree_candidates_yields_id_and_labels_for_mail_utils_export(tmp_path):
    eml_path = tmp_path / "msg1.eml"
    _write_eml_export(eml_path, labels=["INBOX", "Work"])

    (candidate,) = list(_eml_tree_candidates([eml_path]))

    msg_id, source_path, raw_bytes, label_names = candidate
    assert msg_id == "msg1"
    assert source_path == eml_path
    assert label_names == ["INBOX", "Work"]
    assert b"msg1" in raw_bytes


def test_resolve_label_ids_reuses_cache_without_creating():
    service = _FakeService()
    cache = {"INBOX": "INBOX"}
    ids = _resolve_label_ids(service, ["INBOX"], cache)
    assert ids == ["INBOX"]
    assert service.users_resource.labels_resource.create_calls == []


def test_gmail_call_with_backoff_retries_then_succeeds(monkeypatch):
    _no_sleep(monkeypatch)
    service = _FakeService(fail_first_n_imports=2)

    result = _gmail_call_with_backoff(cli.import_message, service, b"raw", label_ids=["INBOX"])

    assert result == {"id": "new_gmail_id_1"}


def test_gmail_call_with_backoff_gives_up_after_max_retries(monkeypatch):
    _no_sleep(monkeypatch)
    service = _FakeService(fail_first_n_imports=99)

    with pytest.raises(HttpError):
        _gmail_call_with_backoff(cli.import_message, service, b"raw", label_ids=["INBOX"])


def test_throttle_gmail_store_sleeps_when_called_too_soon(monkeypatch):
    sleeps = []
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(cli.time, "time", lambda: 100.0)

    _throttle_gmail_store(last_call_time=100.0)

    assert sleeps and sleeps[0] > 0


def test_throttle_gmail_store_does_not_sleep_when_enough_time_passed(monkeypatch):
    sleeps = []
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(cli.time, "time", lambda: 100.0)

    _throttle_gmail_store(last_call_time=0.0)

    assert sleeps == []


def test_run_prepare_gmail_account_reports_missing_app_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "APP_CREDENTIALS_PATH", tmp_path / "nonexistent-app-credentials.json")
    monkeypatch.setattr(cli, "get_credentials", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")))

    _run_prepare_gmail_account(argparse.Namespace(name=str(tmp_path / "tester-account.json"), with_write=False))

    out = capsys.readouterr().out
    assert "Missing" in out
    assert "nonexistent-app-credentials.json" in out


def test_run_prepare_gmail_account_authorizes_and_reports_email(tmp_path, monkeypatch, capsys):
    app_credentials_path = tmp_path / "app-credentials.json"
    app_credentials_path.write_text("{}")
    monkeypatch.setattr(cli, "APP_CREDENTIALS_PATH", app_credentials_path)

    account_path = tmp_path / "tester-account.json"
    fake_service = _FakeService()
    captured_scopes = []

    def fake_get_credentials(given_account_path, scopes=None):
        assert given_account_path == account_path
        captured_scopes.append(scopes)
        return "fake-creds"

    monkeypatch.setattr(cli, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(cli, "build_gmail_service", lambda creds: fake_service)

    _run_prepare_gmail_account(argparse.Namespace(name=str(account_path), with_write=False))

    out = capsys.readouterr().out
    assert "fake-target-account@example.com" in out
    assert captured_scopes == [cli.SCOPES]


def test_run_prepare_gmail_account_with_write_requests_broader_scopes(tmp_path, monkeypatch, capsys):
    app_credentials_path = tmp_path / "app-credentials.json"
    app_credentials_path.write_text("{}")
    monkeypatch.setattr(cli, "APP_CREDENTIALS_PATH", app_credentials_path)

    account_path = tmp_path / "tester-account.json"
    captured_scopes = []

    def fake_get_credentials(given_account_path, scopes=None):
        captured_scopes.append(scopes)
        return "fake-creds"

    monkeypatch.setattr(cli, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(cli, "build_gmail_service", lambda creds: _FakeService())

    _run_prepare_gmail_account(argparse.Namespace(name=str(account_path), with_write=True))

    assert captured_scopes == [cli.STORE_IN_GMAIL_SCOPES]


def test_run_check_gmail_account_reports_missing_account_file(tmp_path, capsys):
    _run_check_gmail_account(argparse.Namespace(name=str(tmp_path / "tester-account.json")))

    out = capsys.readouterr().out
    assert "No account file found" in out
    assert "prepare-gmail-account" in out


def test_run_check_gmail_account_reports_email_scopes_and_mailbox_size(tmp_path, monkeypatch, capsys):
    account_path = tmp_path / "tester-account.json"
    account_path.write_text("{}")

    class _FakeCreds:
        def __init__(self):
            self.scopes = ["https://www.googleapis.com/auth/gmail.readonly"]

    fake_service = _FakeService()
    monkeypatch.setattr(cli, "get_credentials", lambda given_account_path: _FakeCreds())
    monkeypatch.setattr(cli, "build_gmail_service", lambda creds: fake_service)

    _run_check_gmail_account(argparse.Namespace(name=str(account_path)))

    out = capsys.readouterr().out
    assert "fake-target-account@example.com" in out
    assert "gmail.readonly" in out
    assert "42" in out
    assert "7" in out


def test_run_store_in_gmail_reports_missing_source_dir(tmp_path, capsys):
    _run_store_in_gmail(argparse.Namespace(source_dir=str(tmp_path / "missing"), dry_run=False, db=str(tmp_path)))
    assert "not found" in capsys.readouterr().out


def test_run_store_in_gmail_reports_missing_database_when_source_omitted(tmp_path, capsys):
    _run_store_in_gmail(argparse.Namespace(source_dir=None, dry_run=False, db=str(tmp_path)))
    assert "No database found" in capsys.readouterr().out


def test_run_store_in_gmail_dry_run_from_eml_tree_reports_without_touching_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_credentials", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")))

    source_dir = tmp_path / "export"
    source_dir.mkdir()
    _write_eml_export(source_dir / "msg1.eml")

    _run_store_in_gmail(
        argparse.Namespace(source_dir=str(source_dir), dry_run=True, filter=None, max_messages=None, db=str(tmp_path))
    )

    out = capsys.readouterr().out
    assert "Would store" in out
    assert "1 messages stored, 0 skipped" in out


def test_run_store_in_gmail_dry_run_from_database_reports_without_touching_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_credentials", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")))

    db_path = tmp_path / "mails.db"
    conn = init_db(db_path)
    upsert_message(conn, _sample_message())
    conn.close()

    _run_store_in_gmail(argparse.Namespace(source_dir=None, dry_run=True, filter=None, max_messages=None, db=str(tmp_path)))

    out = capsys.readouterr().out
    assert "Would store" in out
    assert "local database" in out
    assert "1 messages stored, 0 skipped" in out


def test_run_store_in_gmail_end_to_end_stores_applies_tracking_label_and_skips_foreign(tmp_path, monkeypatch, capsys):
    _no_sleep(monkeypatch)
    db_path = tmp_path / "mails.db"

    fake_service = _FakeService(existing_labels=[{"id": "INBOX", "name": "INBOX"}])
    monkeypatch.setattr(cli, "get_credentials", lambda account_path, scopes=None: "fake-creds")
    monkeypatch.setattr(cli, "build_gmail_service", lambda creds: fake_service)

    source_dir = tmp_path / "export"
    source_dir.mkdir()
    _write_eml_export(source_dir / "msg1.eml", msg_id="msg1")
    (source_dir / "foreign.eml").write_bytes(b"From: a@example.com\r\nSubject: Not ours\r\n\r\nBody\r\n")

    _run_store_in_gmail(
        argparse.Namespace(source_dir=str(source_dir), dry_run=False, filter=None, max_messages=None, db=str(tmp_path))
    )

    conn = init_db(db_path)
    assert is_stored_in_gmail(conn, "msg1") is True
    out = capsys.readouterr().out
    assert "Target account: fake-target-account@example.com" in out
    assert "1 messages stored, 1 skipped" in out
    assert "last message stored: msg1" in out

    (import_call,) = fake_service.users_resource.messages_resource.import_calls
    tracking_label_ids = [
        c["id"] for c in fake_service.users_resource.labels_resource._existing if c["name"].startswith("mail-utils-store-in-gmail-")
    ]
    assert len(tracking_label_ids) == 1
    assert "INBOX" in import_call["body"]["labelIds"]
    assert tracking_label_ids[0] in import_call["body"]["labelIds"]


def test_run_store_in_gmail_max_messages_stops_early_and_is_resumable(tmp_path, monkeypatch, capsys):
    _no_sleep(monkeypatch)
    db_path = tmp_path / "mails.db"

    fake_service = _FakeService(existing_labels=[{"id": "INBOX", "name": "INBOX"}])
    monkeypatch.setattr(cli, "get_credentials", lambda account_path, scopes=None: "fake-creds")
    monkeypatch.setattr(cli, "build_gmail_service", lambda creds: fake_service)

    source_dir = tmp_path / "export"
    source_dir.mkdir()
    _write_eml_export(source_dir / "a-msg1.eml", msg_id="msg1")
    _write_eml_export(source_dir / "b-msg2.eml", msg_id="msg2")

    _run_store_in_gmail(
        argparse.Namespace(source_dir=str(source_dir), dry_run=False, filter=None, max_messages=1, db=str(tmp_path))
    )
    first_out = capsys.readouterr().out
    assert "1 messages stored, 0 skipped" in first_out
    assert "Stopped after reaching --max-messages 1" in first_out

    conn = init_db(db_path)
    assert is_stored_in_gmail(conn, "msg1") is True
    assert is_stored_in_gmail(conn, "msg2") is False

    _run_store_in_gmail(
        argparse.Namespace(source_dir=str(source_dir), dry_run=False, filter=None, max_messages=None, db=str(tmp_path))
    )
    second_out = capsys.readouterr().out
    assert "1 messages stored, 1 skipped" in second_out
    assert "last message stored: msg2" in second_out

    conn = init_db(db_path)
    assert is_stored_in_gmail(conn, "msg2") is True

    tracking_labels = [
        lbl for lbl in fake_service.users_resource.labels_resource._existing if lbl["name"].startswith("mail-utils-store-in-gmail-")
    ]
    assert len(tracking_labels) == 1, "the capped run and its continuation should share one tracking label, not mint two"
    call1, call2 = fake_service.users_resource.messages_resource.import_calls
    assert tracking_labels[0]["id"] in call1["body"]["labelIds"]
    assert tracking_labels[0]["id"] in call2["body"]["labelIds"]

    assert get_sync_state(conn, "gmail_store_run_label") == "", "a fully-completed run should clear the run marker"


def test_run_store_in_gmail_starts_a_new_tracking_label_after_a_run_completes(tmp_path, monkeypatch, capsys):
    _no_sleep(monkeypatch)
    monkeypatch.setattr(cli, "datetime", _IncrementingClock())

    fake_service = _FakeService(existing_labels=[{"id": "INBOX", "name": "INBOX"}])
    monkeypatch.setattr(cli, "get_credentials", lambda account_path, scopes=None: "fake-creds")
    monkeypatch.setattr(cli, "build_gmail_service", lambda creds: fake_service)

    source_dir = tmp_path / "export"
    source_dir.mkdir()
    _write_eml_export(source_dir / "msg1.eml", msg_id="msg1")

    _run_store_in_gmail(
        argparse.Namespace(source_dir=str(source_dir), dry_run=False, filter=None, max_messages=None, db=str(tmp_path))
    )
    capsys.readouterr()

    _write_eml_export(source_dir / "msg2.eml", msg_id="msg2")
    _run_store_in_gmail(
        argparse.Namespace(source_dir=str(source_dir), dry_run=False, filter=None, max_messages=None, db=str(tmp_path))
    )
    capsys.readouterr()

    tracking_labels = {
        lbl["name"]
        for lbl in fake_service.users_resource.labels_resource._existing
        if lbl["name"].startswith("mail-utils-store-in-gmail-")
    }
    assert len(tracking_labels) == 2, "a run that completed fully should not have its label reused by the next, unrelated run"


def test_run_store_in_gmail_filter_restricts_database_source(tmp_path, monkeypatch, capsys):
    _no_sleep(monkeypatch)
    db_path = tmp_path / "mails.db"

    conn = init_db(db_path)
    upsert_message(conn, _sample_message(id="msg1", subject="Work update"))
    upsert_message(conn, _sample_message(id="msg2", subject="Personal note"))
    upsert_labels(conn, [{"id": "Label_1", "name": "Work"}])
    conn.close()

    fake_service = _FakeService()
    monkeypatch.setattr(cli, "get_credentials", lambda account_path, scopes=None: "fake-creds")
    monkeypatch.setattr(cli, "build_gmail_service", lambda creds: fake_service)

    _run_store_in_gmail(
        argparse.Namespace(source_dir=None, dry_run=False, filter="subject:Work", max_messages=None, db=str(tmp_path))
    )

    conn = init_db(db_path)
    assert is_stored_in_gmail(conn, "msg1") is True
    assert is_stored_in_gmail(conn, "msg2") is False
    out = capsys.readouterr().out
    assert "Filter matched 1 messages" in out


def test_run_store_in_gmail_from_database_includes_real_attachment_content(tmp_path, monkeypatch, capsys):
    """store-in-gmail's DB-sourced path builds its candidate via the same _build_eml_message() export
    uses, so a captured attachment (--with-attachments at import time) must ride along as a real MIME
    part, not just the metadata-only X-Mail-Utils-Attachment header."""
    _no_sleep(monkeypatch)
    db_path = tmp_path / "mails.db"
    attachment_store.configure(tmp_path / "attachments")

    digest = attachment_store.save(b"PDF bytes")

    conn = init_db(db_path)
    upsert_message(conn, _sample_message())
    upsert_attachments(
        conn,
        "msg1",
        [
            {
                "message_id": "msg1",
                "attachment_id": "a1",
                "filename": "report.pdf",
                "mime_type": "application/pdf",
                "size": 9,
                "content_sha256": digest,
            }
        ],
    )
    conn.close()

    fake_service = _FakeService(existing_labels=[{"id": "INBOX", "name": "INBOX"}])
    monkeypatch.setattr(cli, "get_credentials", lambda account_path, scopes=None: "fake-creds")
    monkeypatch.setattr(cli, "build_gmail_service", lambda creds: fake_service)

    _run_store_in_gmail(argparse.Namespace(source_dir=None, dry_run=False, filter=None, max_messages=None, db=str(tmp_path)))

    (import_call,) = fake_service.users_resource.messages_resource.import_calls
    stored_msg = email.message_from_bytes(base64.urlsafe_b64decode(import_call["body"]["raw"]), policy=email_policy_default)

    assert "X-Mail-Utils-Attachment" not in stored_msg
    attachment_parts = list(stored_msg.iter_attachments())
    assert len(attachment_parts) == 1
    assert attachment_parts[0].get_filename() == "report.pdf"
    assert attachment_parts[0].get_content() == b"PDF bytes"


def test_import_pst_subcommand_routes_to_run_import_pst():
    args = build_parser().parse_args(["import-pst", "archive.pst"])
    assert args.command == "import-pst"
    assert args.pst_path == "archive.pst"
    assert args.func is _run_import_pst

    args_alias = build_parser().parse_args(["import-outlook", "archive.pst"])
    assert args_alias.command == "import-outlook"
    assert args_alias.pst_path == "archive.pst"
    assert args_alias.func is _run_import_pst


def test_import_thunderbird_subcommand_routes_to_run_import_thunderbird():
    args = build_parser().parse_args(["import-thunderbird", "archive.pcv"])
    assert args.command == "import-thunderbird"
    assert args.archive_path == "archive.pcv"
    assert args.func is _run_import_thunderbird

    args_alias = build_parser().parse_args(["import-pcv", "archive.pcv"])
    assert args_alias.command == "import-pcv"
    assert args_alias.archive_path == "archive.pcv"
    assert args_alias.func is _run_import_thunderbird


def test_stats_subcommand_routes_to_run_stats():
    args = build_parser().parse_args(["stats"])
    assert args.command == "stats"
    assert args.func is _run_stats


def test_export_subcommand_routes_to_run_export():
    args = build_parser().parse_args(["export", "some_dir"])
    assert args.command == "export"
    assert args.output_dir == "some_dir"
    assert args.format == "md"
    assert args.func is _run_export


def test_export_flag_format_parses():
    assert build_parser().parse_args(["export", "out", "--format", "eml"]).format == "eml"
    assert build_parser().parse_args(["export", "out", "-f", "eml"]).format == "eml"
    assert build_parser().parse_args(["export", "out", "--format", "md"]).format == "md"


def test_export_flag_format_rejects_invalid():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["export", "out", "--format", "txt"])


def test_import_stats_export_accept_db_override():
    assert build_parser().parse_args(["import", "--db", "work.db"]).db == "work.db"
    assert build_parser().parse_args(["import-pst", "a.pst", "--db", "work.db"]).db == "work.db"
    assert build_parser().parse_args(["import-thunderbird", "a.pcv", "--db", "work.db"]).db == "work.db"
    assert build_parser().parse_args(["stats", "--db", "work.db"]).db == "work.db"
    assert build_parser().parse_args(["export", "out", "--db", "work.db"]).db == "work.db"


def test_schedule_subcommand_routes_and_captures_inner_command():
    args = build_parser().parse_args(
        ["schedule", "--job-name", "work", "--interval-minutes", "15", "--", "import", "--filter", "label:Work"]
    )
    assert args.command == "schedule"
    assert args.job_name == "work"
    assert args.interval_minutes == 15
    assert args.func is _run_schedule
    assert args.inner_command == ["--", "import", "--filter", "label:Work"]


def test_schedule_defaults():
    args = build_parser().parse_args(["schedule", "--", "import"])
    assert args.job_name == "default"
    assert args.interval_minutes == 30
    assert args.list is False


def test_unschedule_subcommand_routes_to_run_unschedule():
    args = build_parser().parse_args(["unschedule", "--job-name", "work"])
    assert args.command == "unschedule"
    assert args.job_name == "work"
    assert args.func is _run_unschedule


def test_validate_inner_command_rejects_empty():
    with pytest.raises(cli.ScheduleError):
        _validate_inner_command([])


def test_validate_inner_command_rejects_disallowed_subcommand():
    with pytest.raises(cli.ScheduleError):
        _validate_inner_command(["stats"])
    with pytest.raises(cli.ScheduleError):
        _validate_inner_command(["schedule", "--", "import"])


def test_validate_inner_command_rejects_bad_flags():
    with pytest.raises(cli.ScheduleError):
        _validate_inner_command(["import", "--not-a-real-flag"])


def test_validate_inner_command_accepts_valid_import_and_export():
    _validate_inner_command(["import", "--filter", "label:Work"])
    _validate_inner_command(["export", "/some/dir", "--filter", "has:attachment"])


def test_run_schedule_rejects_invalid_command_without_registering_anything(capsys, monkeypatch):
    called = []
    monkeypatch.setattr(cli, "schedule_windows", lambda *a, **k: called.append("windows"))
    monkeypatch.setattr(cli, "schedule_cron", lambda *a, **k: called.append("cron"))
    _run_schedule(argparse.Namespace(list=False, inner_command=["--", "stats"], job_name="x", interval_minutes=30))
    assert "Error:" in capsys.readouterr().out
    assert called == []


def test_help_subcommand_has_no_func():
    args = build_parser().parse_args(["help"])
    assert args.command == "help"
    assert not hasattr(args, "func")


def test_no_subcommand_has_no_command():
    args = build_parser().parse_args([])
    assert args.command is None


def test_version_subcommand_has_no_func():
    args = build_parser().parse_args(["version"])
    assert args.command == "version"
    assert not hasattr(args, "func")


def test_main_handles_version_subcommand(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["mail-utils", "version"])
    cli.main()
    out = capsys.readouterr().out
    assert out.startswith(f"mail-utils v{package_version('mail-utils')}")


def test_version_subcommand_verbose_flag_parses():
    args = build_parser().parse_args(["version", "--verbose"])
    assert args.verbose is True


def test_help_subcommand_verbose_flag_parses():
    args = build_parser().parse_args(["help", "--verbose"])
    assert args.verbose is True


def test_main_help_verbose_prints_every_subcommand(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["mail-utils", "help", "--verbose"])
    cli.main()
    out = capsys.readouterr().out
    assert f"mail-utils v{package_version('mail-utils')}" in out
    assert "Exit codes:" in out
    for name in ("import", "import-pst", "import-thunderbird", "stats", "export", "schedule", "unschedule", "version"):
        assert f"mail-utils {name}" in out


def test_main_no_subcommand_verbose_prints_every_subcommand(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["mail-utils", "--verbose"])
    cli.main()
    out = capsys.readouterr().out
    assert f"mail-utils v{package_version('mail-utils')}" in out
    assert "Exit codes:" in out
    for name in ("import", "import-pst", "import-thunderbird", "stats", "export", "schedule", "unschedule", "version"):
        assert f"mail-utils {name}" in out


def test_main_help_standard_formatting(monkeypatch, capsys):
    for argv in (["mail-utils", "help"], ["mail-utils", "--help"], ["mail-utils", "-h"], ["mail-utils"]):
        monkeypatch.setattr("sys.argv", argv)
        cli.main()
        out = capsys.readouterr().out
        assert out.startswith(f"mail-utils v{package_version('mail-utils')} - Copyright (c) Giovanni Pellicciotta")
        assert "A lightweight, privacy-preserving, local email archive indexing and extraction utility." in out
        assert "Exit codes:" in out
        assert "0  Success" in out


def test_main_help_specific_subcommand(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["mail-utils", "help", "import"])
    cli.main()
    out = capsys.readouterr().out
    assert "usage: mail-utils import" in out


def test_mandatory_docs_exist():
    base_dir = cli.BASE_DIR
    for filename in ("LICENSE.md", "CHANGELOG.md", "TODO.md", "README.md"):
        assert (base_dir / filename).is_file(), f"{filename} is missing"
    for doc_name in ("index.md", "requirements.md", "devops.md"):
        assert (base_dir / "docs" / doc_name).is_file(), f"docs/{doc_name} is missing"


def _sample_message(**overrides) -> dict:
    msg = {
        "id": "msg1",
        "thread_id": "thread1",
        "sender": "jane@example.com",
        "recipient": "me@example.com",
        "cc": None,
        "bcc": None,
        "subject": "Hello: a test",
        "date": "Wed, 19 Aug 2026 10:00:00 -0700",
        "internal_date_ms": 1566230400000,
        "snippet": "preview",
        "label_ids": "INBOX,Label_1",
        "body_text": "Body text",
        "body_mime_type": "text/plain",
    }
    msg.update(overrides)
    return msg


def test_export_writes_year_month_bucketed_file_with_frontmatter(tmp_path):
    db_path = tmp_path / "mails.db"

    conn = init_db(db_path)
    upsert_message(conn, _sample_message())
    upsert_labels(conn, [{"id": "Label_1", "name": "Work"}])
    upsert_attachments(
        conn,
        "msg1",
        [{"message_id": "msg1", "attachment_id": "a1", "filename": "f.pdf", "mime_type": "application/pdf", "size": 100}],
    )
    conn.close()

    output_dir = tmp_path / "export"
    _run_export(argparse.Namespace(output_dir=str(output_dir), format="md", filter=None, db=str(tmp_path)))

    written = output_dir / "2019" / "08" / "msg1.md"
    assert written.exists()

    raw = written.read_text(encoding="utf-8")
    front, body = raw.split("---\n", 2)[1:]
    frontmatter = yaml.safe_load(front)
    assert frontmatter["labels"] == ["INBOX", "Work"]
    assert frontmatter["attachments"] == [{"filename": "f.pdf", "mime_type": "application/pdf", "size": 100}]
    assert frontmatter["body_mime_type"] == "text/plain"
    assert "cc" not in frontmatter
    assert body.strip() == "Body text"


def test_export_writes_eml_format_with_headers_and_body(tmp_path):
    db_path = tmp_path / "mails.db"

    conn = init_db(db_path)
    upsert_message(conn, _sample_message(cc="boss@example.com", bcc="audit@example.com"))
    upsert_labels(conn, [{"id": "Label_1", "name": "Work"}])
    upsert_attachments(
        conn,
        "msg1",
        [{"message_id": "msg1", "attachment_id": "a1", "filename": "report.pdf", "mime_type": "application/pdf", "size": 2048}],
    )
    conn.close()

    output_dir = tmp_path / "export"
    _run_export(argparse.Namespace(output_dir=str(output_dir), format="eml", filter=None, db=str(tmp_path)))

    written = output_dir / "2019" / "08" / "msg1.eml"
    assert written.exists()

    msg = email.message_from_bytes(written.read_bytes(), policy=email_policy_default)
    assert msg["Subject"] == "Hello: a test"
    assert msg["From"] == "jane@example.com"
    assert msg["To"] == "me@example.com"
    assert msg["Cc"] == "boss@example.com"
    assert msg["Bcc"] == "audit@example.com"
    assert msg["Date"] == "Wed, 19 Aug 2026 10:00:00 -0700"
    assert msg["X-Mail-Utils-ID"] == "msg1"
    assert msg["X-Mail-Utils-Thread-ID"] == "thread1"
    assert msg["X-Mail-Utils-Labels"] == "INBOX, Work"
    assert msg["X-Mail-Utils-Attachment"] == "report.pdf (type=application/pdf; size=2048)"
    assert msg.get_content_type() == "text/plain"
    assert msg.get_content().strip() == "Body text"


def test_export_eml_subject_with_unicode_survives_repeated_export_round_trips(tmp_path):
    # Regression test: found via T0013's real Gmail round-trip testing. A Subject needing RFC 2047
    # encoding right after existing whitespace (e.g. "topic: 日本語") used to gain one extra space
    # every time it was exported/re-imported, because email.policy.default's header folding
    # duplicates the whitespace it folds on. Fixed by generating with utf8=True (raw UTF-8 headers,
    # no encoded-word folding needed) - this locks that in without requiring a real Gmail account.
    db_path = tmp_path / "mails.db"
    # Long enough (with the "Subject: " prefix) to cross email.policy.default's ~78-char fold
    # threshold right at the space before the encoded word - that's specifically what triggers
    # the whitespace-duplication bug this test guards against; a shorter subject wouldn't fold at all.
    subject = "[mail-utils roundtrip test] two attachments, unicode subject: 日本語のテスト"

    conn = init_db(db_path)
    upsert_message(conn, _sample_message(subject=subject))
    conn.close()

    output_dir = tmp_path / "export"
    _run_export(argparse.Namespace(output_dir=str(output_dir), format="eml", filter=None, db=str(tmp_path)))
    written = output_dir / "2019" / "08" / "msg1.eml"
    msg = email.message_from_bytes(written.read_bytes(), policy=email_policy_default)
    assert str(msg["Subject"]) == subject

    # Simulate a second round-trip (as store-in-gmail would do, rebuilding from the re-synced value)
    # by re-exporting using the already-once-round-tripped subject as the new source value.
    conn = init_db(db_path)
    upsert_message(conn, _sample_message(subject=str(msg["Subject"])))
    conn.close()
    output_dir_2 = tmp_path / "export2"
    _run_export(argparse.Namespace(output_dir=str(output_dir_2), format="eml", filter=None, db=str(tmp_path)))
    written_2 = output_dir_2 / "2019" / "08" / "msg1.eml"
    msg_2 = email.message_from_bytes(written_2.read_bytes(), policy=email_policy_default)
    assert str(msg_2["Subject"]) == subject


def test_export_eml_attaches_real_content_when_present(tmp_path):
    db_path = tmp_path / "mails.db"
    attachment_store.configure(tmp_path / "attachments")

    digest = attachment_store.save(b"PDF bytes")

    conn = init_db(db_path)
    upsert_message(conn, _sample_message())
    upsert_attachments(
        conn,
        "msg1",
        [
            {
                "message_id": "msg1",
                "attachment_id": "a1",
                "filename": "report.pdf",
                "mime_type": "application/pdf",
                "size": 9,
                "content_sha256": digest,
            }
        ],
    )
    conn.close()

    output_dir = tmp_path / "export"
    _run_export(argparse.Namespace(output_dir=str(output_dir), format="eml", filter=None, db=str(tmp_path)))

    written = output_dir / "2019" / "08" / "msg1.eml"
    msg = email.message_from_bytes(written.read_bytes(), policy=email_policy_default)

    assert "X-Mail-Utils-Attachment" not in msg
    attachment_parts = list(msg.iter_attachments())
    assert len(attachment_parts) == 1
    assert attachment_parts[0].get_filename() == "report.pdf"
    assert attachment_parts[0].get_content() == b"PDF bytes"
    assert msg.get_body(preferencelist=("plain",)).get_content().strip() == "Body text"


def test_export_md_writes_sidecar_attachments_directory_when_content_present(tmp_path):
    db_path = tmp_path / "mails.db"
    attachment_store.configure(tmp_path / "attachments")

    digest = attachment_store.save(b"PDF bytes")

    conn = init_db(db_path)
    upsert_message(conn, _sample_message())
    upsert_attachments(
        conn,
        "msg1",
        [
            {
                "message_id": "msg1",
                "attachment_id": "a1",
                "filename": "report.pdf",
                "mime_type": "application/pdf",
                "size": 9,
                "content_sha256": digest,
            }
        ],
    )
    conn.close()

    output_dir = tmp_path / "export"
    _run_export(argparse.Namespace(output_dir=str(output_dir), format="md", filter=None, db=str(tmp_path)))

    sidecar_file = output_dir / "2019" / "08" / "msg1.attachments" / "report.pdf"
    assert sidecar_file.read_bytes() == b"PDF bytes"

    raw = (output_dir / "2019" / "08" / "msg1.md").read_text(encoding="utf-8")
    front = raw.split("---\n", 2)[1]
    frontmatter = yaml.safe_load(front)
    assert frontmatter["attachments"] == [{"filename": "report.pdf", "mime_type": "application/pdf", "size": 9}]
    assert "content_sha256" not in str(frontmatter)


def test_export_md_sanitizes_a_filename_invalid_on_windows(tmp_path):
    # A real Outlook attachment can be named e.g. "RE: Offer: IMS DB Migration" - colons are a valid
    # MAPI/MIME filename character but not a valid Windows one, and writing it straight to disk as a
    # sidecar file crashed a real export (OSError) against the real anubex-outlook-backup.pst archive -
    # found via T0020's full-scale export run.
    db_path = tmp_path / "mails.db"
    attachment_store.configure(tmp_path / "attachments")

    digest = attachment_store.save(b"PDF bytes")

    conn = init_db(db_path)
    upsert_message(conn, _sample_message())
    upsert_attachments(
        conn,
        "msg1",
        [
            {
                "message_id": "msg1",
                "attachment_id": "a1",
                "filename": "RE: Offer: IMS DB Migration.pdf",
                "mime_type": "application/pdf",
                "size": 9,
                "content_sha256": digest,
            }
        ],
    )
    conn.close()

    output_dir = tmp_path / "export"
    _run_export(argparse.Namespace(output_dir=str(output_dir), format="md", filter=None, db=str(tmp_path)))

    sidecar_dir = output_dir / "2019" / "08" / "msg1.attachments"
    written = list(sidecar_dir.iterdir())
    assert len(written) == 1
    assert ":" not in written[0].name
    assert written[0].read_bytes() == b"PDF bytes"

    # The frontmatter still records the real, original filename (metadata, not a filesystem path).
    raw = (output_dir / "2019" / "08" / "msg1.md").read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(raw.split("---\n", 2)[1])
    assert frontmatter["attachments"][0]["filename"] == "RE: Offer: IMS DB Migration.pdf"


def test_export_writes_eml_format_html_body(tmp_path):
    db_path = tmp_path / "mails.db"

    conn = init_db(db_path)
    upsert_message(
        conn,
        _sample_message(
            id="msg_html",
            date=None,
            internal_date_ms=1566230400000,
            body_text="<p>HTML Body</p>",
            body_mime_type="text/html",
        ),
    )
    conn.close()

    output_dir = tmp_path / "export"
    _run_export(argparse.Namespace(output_dir=str(output_dir), format="eml", filter=None, db=str(tmp_path)))

    written = output_dir / "2019" / "08" / "msg_html.eml"
    assert written.exists()

    msg = email.message_from_bytes(written.read_bytes(), policy=email_policy_default)
    assert msg["Subject"] == "Hello: a test"
    assert msg.get_content_type() == "text/html"
    assert "<p>HTML Body</p>" in msg.get_content()
    assert msg["Date"] == "Mon, 19 Aug 2019 16:00:00 +0000"


def test_export_eml_buckets_missing_internal_date_as_unknown(tmp_path):
    db_path = tmp_path / "mails.db"

    conn = init_db(db_path)
    upsert_message(conn, _sample_message(internal_date_ms=None))
    conn.close()

    output_dir = tmp_path / "export"
    _run_export(argparse.Namespace(output_dir=str(output_dir), format="eml", filter=None, db=str(tmp_path)))

    assert (output_dir / "unknown" / "msg1.eml").exists()


def test_parse_attachment_stub_header_with_type_and_size():
    row = _parse_attachment_stub_header("msg1", "report.pdf (type=application/pdf; size=12345)")
    assert row == {
        "message_id": "msg1",
        "filename": "report.pdf",
        "mime_type": "application/pdf",
        "size": 12345,
        "content_sha256": None,
        "content_id": None,
    }


def test_parse_attachment_stub_header_with_no_metadata():
    row = _parse_attachment_stub_header("msg1", "report.pdf")
    assert row["filename"] == "report.pdf"
    assert row["mime_type"] is None
    assert row["size"] is None


def test_import_eml_subcommand_routes_to_run_import_eml():
    args = build_parser().parse_args(["import-eml", "some/export/dir"])
    assert args.command == "import-eml"
    assert args.source_dir == "some/export/dir"
    assert args.func is _run_import_eml


def test_run_import_eml_reports_missing_source_directory(tmp_path, capsys):
    _run_import_eml(argparse.Namespace(source_dir=str(tmp_path / "does-not-exist"), db=str(tmp_path / "db")))
    out = capsys.readouterr().out
    assert "not found" in out


def test_run_import_eml_skips_files_without_mail_utils_id_header(tmp_path):
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    (export_dir / "not-ours.eml").write_bytes(b"Subject: hi\r\n\r\nBody\r\n")

    db_dir = tmp_path / "result"
    _run_import_eml(argparse.Namespace(source_dir=str(export_dir), db=str(db_dir)))

    conn = init_db(db_dir / "mails.db")
    (count,) = conn.execute("SELECT COUNT(*) FROM messages").fetchone()
    assert count == 0
    conn.close()


def test_run_import_eml_round_trips_message_addresses_and_labels(tmp_path):
    origin_dir = tmp_path / "origin"
    conn = init_db(origin_dir / "mails.db")
    upsert_labels(conn, [{"id": "outlook:Inbox/Projects", "name": "Inbox/Projects"}])
    upsert_message(
        conn,
        _sample_message(
            id="outlook:msg1",
            label_ids="outlook:Inbox/Projects",
            cc="carl@example.com",
            bcc="hidden@example.com",
        ),
    )
    conn.close()

    export_dir = tmp_path / "export"
    _run_export(argparse.Namespace(output_dir=str(export_dir), format="eml", filter=None, db=str(origin_dir)))

    result_dir = tmp_path / "result"
    _run_import_eml(argparse.Namespace(source_dir=str(export_dir), db=str(result_dir)))

    conn = init_db(result_dir / "mails.db")
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM messages").fetchone()
    assert row["id"] == "outlook:msg1"
    assert row["sender"] == "jane@example.com"
    assert row["cc"] == "carl@example.com"
    assert row["bcc"] == "hidden@example.com"
    assert row["internal_date_ms"] == 1566230400000
    assert row["body_text"].strip() == "Body text"

    label_names = dict(conn.execute("SELECT id, name FROM labels").fetchall())
    resolved_label_names = {label_names[lbl] for lbl in row["label_ids"].split(",")}
    assert resolved_label_names == {"Inbox/Projects"}

    # _run_import_eml skips per-message FTS maintenance and rebuilds messages_fts once after the loop
    # instead (a real, measured bottleneck against a large archive) - must still be fully populated by
    # the time the command returns.
    (fts_count,) = conn.execute("SELECT COUNT(*) FROM messages_fts").fetchone()
    assert fts_count == 1
    conn.close()


def test_run_import_eml_round_trips_attachment_content_and_content_id(tmp_path):
    origin_dir = tmp_path / "origin"
    attachment_store.configure(origin_dir / "attachments")
    digest = attachment_store.save(b"PNG bytes")

    conn = init_db(origin_dir / "mails.db")
    upsert_message(
        conn,
        _sample_message(
            id="outlook:msg1",
            body_mime_type="text/plain",
            body_text="Plain body",
            body_html='<p>See <img src="cid:logo@example"></p>',
        ),
    )
    upsert_attachments(
        conn,
        "outlook:msg1",
        [
            {
                "message_id": "outlook:msg1",
                "filename": "logo.png",
                "mime_type": "image/png",
                "size": 9,
                "content_sha256": digest,
                "content_id": "<logo@example>",
            },
            {
                "message_id": "outlook:msg1",
                "filename": "unread.pdf",
                "mime_type": "application/pdf",
                "size": 42,
                "content_sha256": None,
                "content_id": None,
            },
        ],
    )
    conn.close()

    export_dir = tmp_path / "export"
    _run_export(argparse.Namespace(output_dir=str(export_dir), format="eml", filter=None, db=str(origin_dir)))

    result_dir = tmp_path / "result"
    attachment_store.configure(result_dir / "attachments")
    _run_import_eml(argparse.Namespace(source_dir=str(export_dir), db=str(result_dir)))

    conn = init_db(result_dir / "mails.db")
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM messages").fetchone()
    assert row["body_html"].strip() == '<p>See <img src="cid:logo@example"></p>'

    atts = {r["filename"]: r for r in conn.execute("SELECT * FROM attachments").fetchall()}
    assert atts["logo.png"]["content_sha256"] == digest
    assert atts["logo.png"]["content_id"] == "<logo@example>"
    assert attachment_store.read(atts["logo.png"]["content_sha256"]) == b"PNG bytes"
    assert atts["unread.pdf"]["content_sha256"] is None
    assert atts["unread.pdf"]["mime_type"] == "application/pdf"
    assert atts["unread.pdf"]["size"] == 42
    conn.close()


def test_run_import_eml_reconstructs_html_only_message_consistently():
    """An html-only message stores the same raw markup in both body_text (as _extract_body_text's
    existing fallback does) and body_html - reconstructing it must not misclassify it as plain text
    (see _build_eml_message's own body_mime_type == "text/plain" guard for the forward direction)."""
    html = "<html><body><p>Only HTML</p></body></html>"
    msg = cli._build_eml_message(
        msg_id="outlook:msg1",
        thread_id=None,
        sender=None,
        recipient=None,
        cc=None,
        bcc=None,
        subject=None,
        date=None,
        internal_date_ms=None,
        labels=[],
        body_mime_type="text/html",
        attachments=[],
        body_text=html,
        body_html=html,
    )
    body_text, body_mime_type, body_html = cli._extract_eml_body(msg)
    assert body_mime_type == "text/html"
    assert body_text.strip() == html
    assert body_html.strip() == html


def test_export_buckets_missing_internal_date_as_unknown(tmp_path):
    db_path = tmp_path / "mails.db"

    conn = init_db(db_path)
    upsert_message(conn, _sample_message(internal_date_ms=None))
    conn.close()

    output_dir = tmp_path / "export"
    _run_export(argparse.Namespace(output_dir=str(output_dir), filter=None, db=str(tmp_path)))

    assert (output_dir / "unknown" / "msg1.md").exists()


def _two_message_db(tmp_path) -> Path:
    db_path = tmp_path / "mails.db"

    conn = init_db(db_path)
    upsert_message(conn, _sample_message(id="msg1", subject="Work update"))
    upsert_addresses(conn, "msg1", [{"message_id": "msg1", "role": "from", "address": "jane@x.com", "name": "Jane"}])
    upsert_attachments(
        conn,
        "msg1",
        [{"message_id": "msg1", "attachment_id": "a1", "filename": "f.pdf", "mime_type": "application/pdf", "size": 100}],
    )

    upsert_message(conn, _sample_message(id="msg2", subject="Personal note"))
    upsert_addresses(conn, "msg2", [{"message_id": "msg2", "role": "from", "address": "bob@x.com", "name": "Bob"}])
    conn.close()
    return db_path


def test_export_filter_only_writes_matching_messages(tmp_path):
    _two_message_db(tmp_path)
    output_dir = tmp_path / "export"

    _run_export(argparse.Namespace(output_dir=str(output_dir), format="md", filter="has:attachment", db=str(tmp_path)))

    written = list(output_dir.rglob("*.md"))
    assert len(written) == 1
    assert written[0].name == "msg1.md"


def test_export_eml_filter_only_writes_matching_messages(tmp_path):
    _two_message_db(tmp_path)
    output_dir = tmp_path / "export"

    _run_export(argparse.Namespace(output_dir=str(output_dir), format="eml", filter="has:attachment", db=str(tmp_path)))

    written = list(output_dir.rglob("*.eml"))
    assert len(written) == 1
    assert written[0].name == "msg1.eml"


def test_export_invalid_filter_does_not_crash(tmp_path, capsys):
    _two_message_db(tmp_path)
    output_dir = tmp_path / "export"

    _run_export(argparse.Namespace(output_dir=str(output_dir), filter="is:unread", db=str(tmp_path)))

    assert "Invalid --filter" in capsys.readouterr().out
    assert not output_dir.exists()


def test_stats_filter_restricts_total_count(tmp_path, capsys):
    _two_message_db(tmp_path)

    _run_stats(argparse.Namespace(filter="from:jane", db=str(tmp_path)))

    out = capsys.readouterr().out
    assert "Total messages:" in out
    assert out.split("Total messages:", 1)[1].split("\n", 1)[0].strip() == "1"


def test_stats_aligns_value_columns_across_all_top_lists(tmp_path, capsys):
    db_path = tmp_path / "mails.db"

    conn = init_db(db_path)
    upsert_message(conn, _sample_message(id="msg1", label_ids="Label_1"))
    upsert_labels(conn, [{"id": "Label_1", "name": "A"}])
    upsert_addresses(
        conn,
        "msg1",
        [{"message_id": "msg1", "role": "from", "address": "a@example.com", "name": "A Very Long Display Name Indeed"}],
    )
    conn.close()

    _run_stats(argparse.Namespace(filter=None, db=str(tmp_path)))
    out = capsys.readouterr().out

    # "Top labels" has a short name ("A"), "Top senders" has a much longer one - both value columns
    # should still land in the same place, i.e. every "  <name> <count>" data line is the same width.
    data_lines = [line for line in out.splitlines() if line.startswith("  ")]
    assert len(data_lines) >= 2
    assert len({len(line) for line in data_lines}) == 1


def test_logging_console_has_no_timestamps_while_logfile_has_timestamps(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "mails.db"
    log_dir = tmp_path / "logs"
    log_path = log_dir / "mail-utils.log"
    monkeypatch.setattr(cli, "LOG_DIR", log_dir)
    monkeypatch.setattr(cli, "LOG_PATH", log_path)

    conn = init_db(db_path)
    upsert_message(conn, _sample_message(id="msg1"))
    conn.close()

    _run_stats(argparse.Namespace(filter=None, db=str(tmp_path)))

    console_out = capsys.readouterr().out
    assert "operation started: Database stats" in console_out
    assert "operation ended in" in console_out
    # Console output lines should not contain "[INFO]" or UTC timestamp prefix
    for line in console_out.splitlines():
        assert "[INFO]" not in line
        assert "UTC [" not in line

    # File log must contain timestamp and [INFO]
    assert log_path.exists()
    file_content = log_path.read_text(encoding="utf-8")
    assert "[INFO] Mail Utils" in file_content
    assert "operation started: Database stats" in file_content
    assert "UTC [INFO]" in file_content


def test_utc_formatter_indents_subsequent_lines_for_multiline_messages():
    record = logging.LogRecord(
        "mail_utils",
        logging.INFO,
        "test.py",
        1,
        "Top senders:\n  Bob <bob@x.com>      5\n  Alice <alice@x.com>    3",
        None,
        None,
    )
    record.created = 1735689600.0
    formatter = cli._UTCFormatter(cli._LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
    formatted = formatter.format(record)
    lines = formatted.splitlines()
    assert len(lines) == 3
    # First line has timestamp and log level prefix
    assert lines[0].startswith("2025-01-01 00:00:00 UTC [INFO] Top senders:")
    header_len = len("2025-01-01 00:00:00 UTC [INFO] ")
    # Subsequent lines are indented by the header length
    assert lines[1] == (" " * header_len) + "  Bob <bob@x.com>      5"
    assert lines[2] == (" " * header_len) + "  Alice <alice@x.com>    3"


def test_search_subcommand_routes_and_parses():
    parser = build_parser()
    args = parser.parse_args(["search", "project alpha", "-n", "10", "--db", "custom.db"])
    assert args.command == "search"
    assert args.query == "project alpha"
    assert args.limit == 10
    assert args.db == "custom.db"


def test_recursive_flags_parse_across_importers():
    parser = build_parser()
    args_import = parser.parse_args(["import", "--recursive"])
    assert args_import.recursive is True

    args_gmail = parser.parse_args(["import-gmail", "-r"])
    assert args_gmail.recursive is True

    args_pst = parser.parse_args(["import-pst", "mail.pst", "-r"])
    assert args_pst.recursive is True

    args_tb = parser.parse_args(["import-thunderbird", "profile.pcv", "-r"])
    assert args_tb.recursive is True


def test_run_import_auto_detects_pst(tmp_path, capsys):
    sample_pst = Path("tests/fixtures/sample.pst")
    if not sample_pst.exists():
        pytest.skip("sample.pst fixture not found")
    db_dir = tmp_path / "auto_pst"
    _run_import(argparse.Namespace(source_path=str(sample_pst), db=str(db_dir), recursive=False, filter=None))
    out = capsys.readouterr().out
    assert "Outlook PST import" in out
    assert "2 messages indexed" in out


def test_run_import_auto_detects_thunderbird_pcv(tmp_path, capsys):
    sample_pcv = Path("tests/fixtures/sample.pcv")
    if not sample_pcv.exists():
        pytest.skip("sample.pcv fixture not found")
    db_dir = tmp_path / "auto_tb"
    _run_import(argparse.Namespace(source_path=str(sample_pcv), db=str(db_dir), recursive=False, filter=None))
    out = capsys.readouterr().out
    assert "Thunderbird archive import" in out
    assert "3 messages indexed" in out


def test_run_import_rejects_unsupported_formats(tmp_path, capsys):
    eml_file = tmp_path / "message.eml"
    eml_file.write_text("From: user@example.com\nSubject: Test\n\nBody", encoding="utf-8")
    _run_import(argparse.Namespace(source_path=str(eml_file), db=None, recursive=False, filter=None))
    out = capsys.readouterr().out
    assert "Direct import of single EML message 'message.eml' is not supported" in out

    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("plain text", encoding="utf-8")
    _run_import(argparse.Namespace(source_path=str(txt_file), db=None, recursive=False, filter=None))
    out = capsys.readouterr().out
    assert "Unsupported file format for 'notes.txt'" in out


def test_run_import_no_args_without_credentials_reports_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "APP_CREDENTIALS_PATH", tmp_path / "nonexistent-app-credentials.json")
    _run_import(
        argparse.Namespace(
            source_path=None, db=None, account=str(tmp_path / "nonexistent-account.json"), recursive=False, filter=None
        )
    )
    out = capsys.readouterr().out
    assert "No import file specified and Gmail credentials not found" in out
