import argparse
from importlib.metadata import version as package_version

import pytest
import yaml

from mail_utils import cli
from mail_utils.cli import (
    _run_export,
    _run_import,
    _run_schedule,
    _run_stats,
    _run_unschedule,
    _validate_inner_command,
    build_parser,
)
from mail_utils.db import (
    init_db,
    upsert_addresses,
    upsert_attachments,
    upsert_labels,
    upsert_message,
)


def test_version_flag_parses():
    args = build_parser().parse_args(["--version"])
    assert args.version is True
    assert args.verbose is False


def test_print_version_shows_version_and_copyright(capsys):
    cli._print_version(verbose=False)
    out = capsys.readouterr().out
    assert out.splitlines() == [
        f"mail-utils {package_version('mail-utils')}",
        "Copyright (c) Giovanni Pellicciotta",
    ]


def test_print_version_verbose_includes_release_entry(tmp_path, monkeypatch, capsys):
    ver = package_version("mail-utils")
    monkeypatch.setattr(cli, "BASE_DIR", tmp_path)
    (tmp_path / "RELEASES.md").write_text(
        f"# Release Notes\n\n## v{ver}\nReleased on 2026-08-19\n\n- Did a thing.\n\n## v0.0.1\nOlder.\n",
        encoding="utf-8",
    )

    cli._print_version(verbose=True)

    out = capsys.readouterr().out
    assert "Did a thing." in out
    assert "v0.0.1" not in out


def test_main_handles_version_flag(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["mail-utils", "--version"])
    cli.main()
    out = capsys.readouterr().out
    assert out.startswith(f"mail-utils {package_version('mail-utils')}")


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


def test_import_stats_export_accept_db_override():
    assert build_parser().parse_args(["import", "--db", "work.db"]).db == "work.db"
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
        conn,
        "msg1",
        [{"message_id": "msg1", "attachment_id": "a1", "filename": "f.pdf", "mime_type": "application/pdf", "size": 100}],
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


def test_stats_aligns_value_columns_across_all_top_lists(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "gmail_index.db"
    monkeypatch.setattr(cli, "DB_PATH", db_path)

    conn = init_db(db_path)
    upsert_message(conn, _sample_message(id="msg1", label_ids="Label_1"))
    upsert_labels(conn, [{"id": "Label_1", "name": "A"}])
    upsert_addresses(
        conn,
        "msg1",
        [{"message_id": "msg1", "role": "from", "address": "a@example.com", "name": "A Very Long Display Name Indeed"}],
    )
    conn.close()

    _run_stats(argparse.Namespace(filter=None))
    out = capsys.readouterr().out

    # "Top labels" has a short name ("A"), "Top senders" has a much longer one - both value columns
    # should still land in the same place, i.e. every "  <name> <count>" data line is the same width.
    data_lines = [line for line in out.splitlines() if line.startswith("  ")]
    assert len(data_lines) >= 2
    assert len({len(line) for line in data_lines}) == 1
