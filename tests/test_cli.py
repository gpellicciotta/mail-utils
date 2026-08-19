import argparse

import yaml

import gmail_ingest.cli as cli
from gmail_ingest.cli import _run_export, _run_import, _run_stats, build_parser
from gmail_ingest.db import (
    init_db,
    upsert_addresses,
    upsert_attachments,
    upsert_labels,
    upsert_message,
)


def test_import_subcommand_routes_to_run_import():
    args = build_parser().parse_args(["import"])
    assert args.command == "import"
    assert args.filter is None
    assert args.func is _run_import


def test_import_subcommand_accepts_filter_flag():
    args = build_parser().parse_args(["import", "--filter", "label:Work"])
    assert args.filter == "label:Work"


def test_stats_subcommand_routes_to_run_stats():
    args = build_parser().parse_args(["stats"])
    assert args.command == "stats"
    assert args.func is _run_stats


def test_export_subcommand_routes_to_run_export():
    args = build_parser().parse_args(["export", "some_dir"])
    assert args.command == "export"
    assert args.output_dir == "some_dir"
    assert args.func is _run_export


def test_help_subcommand_has_no_func():
    args = build_parser().parse_args(["help"])
    assert args.command == "help"
    assert not hasattr(args, "func")


def test_no_subcommand_has_no_command():
    args = build_parser().parse_args([])
    assert args.command is None


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


def test_export_writes_year_month_bucketed_file_with_frontmatter(tmp_path, monkeypatch):
    db_path = tmp_path / "gmail_index.db"
    monkeypatch.setattr(cli, "DB_PATH", db_path)

    conn = init_db(db_path)
    upsert_message(conn, _sample_message())
    upsert_labels(conn, [{"id": "Label_1", "name": "Work"}])
    upsert_attachments(
        conn, "msg1", [{"message_id": "msg1", "attachment_id": "a1", "filename": "f.pdf", "mime_type": "application/pdf", "size": 100}]
    )
    conn.close()

    output_dir = tmp_path / "export"
    _run_export(argparse.Namespace(output_dir=str(output_dir), filter=None))

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


def test_export_buckets_missing_internal_date_as_unknown(tmp_path, monkeypatch):
    db_path = tmp_path / "gmail_index.db"
    monkeypatch.setattr(cli, "DB_PATH", db_path)

    conn = init_db(db_path)
    upsert_message(conn, _sample_message(internal_date_ms=None))
    conn.close()

    output_dir = tmp_path / "export"
    _run_export(argparse.Namespace(output_dir=str(output_dir), filter=None))

    assert (output_dir / "unknown" / "msg1.md").exists()


def _two_message_db(tmp_path, monkeypatch):
    db_path = tmp_path / "gmail_index.db"
    monkeypatch.setattr(cli, "DB_PATH", db_path)

    conn = init_db(db_path)
    upsert_message(conn, _sample_message(id="msg1", subject="Work update"))
    upsert_addresses(
        conn, "msg1", [{"message_id": "msg1", "role": "from", "address": "jane@x.com", "name": "Jane"}]
    )
    upsert_attachments(
        conn, "msg1", [{"message_id": "msg1", "attachment_id": "a1", "filename": "f.pdf", "mime_type": "application/pdf", "size": 100}]
    )

    upsert_message(conn, _sample_message(id="msg2", subject="Personal note"))
    upsert_addresses(
        conn, "msg2", [{"message_id": "msg2", "role": "from", "address": "bob@x.com", "name": "Bob"}]
    )
    conn.close()
    return db_path


def test_export_filter_only_writes_matching_messages(tmp_path, monkeypatch):
    _two_message_db(tmp_path, monkeypatch)
    output_dir = tmp_path / "export"

    _run_export(argparse.Namespace(output_dir=str(output_dir), filter="has:attachment"))

    written = list(output_dir.rglob("*.md"))
    assert len(written) == 1
    assert written[0].name == "msg1.md"


def test_export_invalid_filter_does_not_crash(tmp_path, monkeypatch, capsys):
    _two_message_db(tmp_path, monkeypatch)
    output_dir = tmp_path / "export"

    _run_export(argparse.Namespace(output_dir=str(output_dir), filter="is:unread"))

    assert "Invalid --filter" in capsys.readouterr().out
    assert not output_dir.exists()


def test_stats_filter_restricts_total_count(tmp_path, monkeypatch, capsys):
    _two_message_db(tmp_path, monkeypatch)

    _run_stats(argparse.Namespace(filter="from:jane"))

    out = capsys.readouterr().out
    assert "Total messages:" in out
    assert out.split("Total messages:", 1)[1].split("\n", 1)[0].strip() == "1"
