import argparse
import sqlite3

from mail_utils import cli
from mail_utils.cli import _run_search, _sanitize_fts_query
from mail_utils.db import init_db, upsert_message


def _sample_msg(
    *,
    id: str,
    subject: str = "Test Subject",
    body_text: str = "Test Body",
    sender: str = "sender@example.com",
    recipient: str = "recipient@example.com",
) -> dict:
    return {
        "id": id,
        "thread_id": None,
        "sender": sender,
        "recipient": recipient,
        "cc": None,
        "bcc": None,
        "subject": subject,
        "date": "Mon, 1 Jan 2026 12:00:00 +0000",
        "internal_date_ms": 1767268800000,
        "snippet": None,
        "label_ids": "",
        "body_text": body_text,
        "body_mime_type": "text/plain",
    }


def test_db_fts_indexing_and_search(tmp_path):
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)

    upsert_message(
        conn,
        _sample_msg(
            id="msg1",
            subject="Urgent: Quarterly financial report Q3",
            body_text="Please find attached the financial breakdown and profit margins.",
            sender="cfo@company.com",
        ),
    )
    upsert_message(
        conn,
        _sample_msg(
            id="msg2",
            subject="Team lunch on Friday",
            body_text="Let us meet at the Italian restaurant at 12:30pm.",
            sender="alice@company.com",
        ),
    )

    # Search by subject term
    rows = conn.execute(
        "SELECT id FROM messages_fts WHERE messages_fts MATCH ? ORDER BY bm25(messages_fts)",
        ("financial",),
    ).fetchall()
    assert [r[0] for r in rows] == ["msg1"]

    # Search by body term
    rows = conn.execute(
        "SELECT id FROM messages_fts WHERE messages_fts MATCH ? ORDER BY bm25(messages_fts)",
        ("restaurant",),
    ).fetchall()
    assert [r[0] for r in rows] == ["msg2"]

    # Search by sender
    rows = conn.execute(
        "SELECT id FROM messages_fts WHERE messages_fts MATCH ? ORDER BY bm25(messages_fts)",
        ("cfo*",),
    ).fetchall()
    assert [r[0] for r in rows] == ["msg1"]

    conn.close()


def test_sanitize_fts_query():
    assert _sanitize_fts_query("hello world") == '"hello" "world"'
    assert _sanitize_fts_query("hello OR world") == '"hello" OR "world"'
    assert _sanitize_fts_query("hello NOT world") == '"hello" NOT "world"'
    assert _sanitize_fts_query('special "quotes"') == '"special" """quotes"""'


def test_run_search_outputs_matching_messages(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "gmail_index.db"
    monkeypatch.setattr(cli, "DB_PATH", db_path)

    conn = init_db(db_path)
    upsert_message(
        conn,
        _sample_msg(
            id="gmail:101",
            subject="Invoice #4567 for Consulting Services",
            body_text="Thank you for your business. Total amount due is $1,500.",
            sender="Jane Doe <jane@consulting.com>",
            recipient="John Smith <john@example.com>",
        ),
    )
    conn.close()

    _run_search(argparse.Namespace(query="invoice", limit=10, db=str(db_path)))

    out = capsys.readouterr().out
    assert "Mail Utils" in out
    assert "operation started: Full-text search" in out
    assert "Invoice" in out
    assert "jane@consulting.com" in out
    assert "1 matching messages found" in out or "1 matching message found" in out
    assert "operation ended in" in out


def test_run_search_no_matches(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "gmail_index.db"
    monkeypatch.setattr(cli, "DB_PATH", db_path)

    conn = init_db(db_path)
    upsert_message(conn, _sample_msg(id="gmail:101", subject="Meeting notes"))
    conn.close()

    _run_search(argparse.Namespace(query="nonexistent_word_xyz", limit=10, db=str(db_path)))

    out = capsys.readouterr().out
    assert "No matching messages found." in out
    assert "0 matching messages found" in out

