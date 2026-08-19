import argparse

import yaml

import gmail_ingest.cli as cli
from gmail_ingest.cli import _run_export, _run_stats, _run_update, build_parser
from gmail_ingest.db import init_db, upsert_attachments, upsert_labels, upsert_message


def test_update_subcommand_routes_to_run_update():
    args = build_parser().parse_args(["update"])
    assert args.command == "update"
    assert args.func is _run_update


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
    _run_export(argparse.Namespace(output_dir=str(output_dir)))

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
    _run_export(argparse.Namespace(output_dir=str(output_dir)))

    assert (output_dir / "unknown" / "msg1.md").exists()
