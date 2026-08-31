import sqlite3

from mail_utils.db import init_db, upsert_attachments, upsert_message


def test_init_db_creates_missing_parent_directory(tmp_path):
    db_path = tmp_path / "does" / "not" / "exist" / "gmail.db"
    assert not db_path.parent.exists()

    conn = init_db(db_path)
    conn.close()

    assert db_path.exists()


def test_init_db_adds_content_sha256_column_to_pre_existing_attachments_table(tmp_path):
    db_path = tmp_path / "gmail.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE attachments (message_id TEXT NOT NULL, attachment_id TEXT, filename TEXT NOT NULL, "
        "mime_type TEXT, size INTEGER)"
    )
    conn.commit()
    conn.close()

    conn = init_db(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(attachments)")}
    assert "content_sha256" in columns
    conn.close()


def test_upsert_attachments_defaults_content_sha256_to_none_when_not_supplied(tmp_path):
    conn = init_db(tmp_path / "gmail.db")
    upsert_attachments(
        conn,
        "msg1",
        [{"message_id": "msg1", "attachment_id": "a1", "filename": "f.pdf", "mime_type": "application/pdf", "size": 1}],
    )
    row = conn.execute("SELECT content_sha256 FROM attachments WHERE message_id = 'msg1'").fetchone()
    assert row == (None,)
    conn.close()


def test_upsert_attachments_persists_supplied_content_sha256(tmp_path):
    conn = init_db(tmp_path / "gmail.db")
    upsert_attachments(
        conn,
        "msg1",
        [
            {
                "message_id": "msg1",
                "attachment_id": "a1",
                "filename": "f.pdf",
                "mime_type": "application/pdf",
                "size": 1,
                "content_sha256": "abc123",
            }
        ],
    )
    row = conn.execute("SELECT content_sha256 FROM attachments WHERE message_id = 'msg1'").fetchone()
    assert row == ("abc123",)
    conn.close()


def test_upsert_attachments_persists_supplied_content_id(tmp_path):
    conn = init_db(tmp_path / "gmail.db")
    upsert_attachments(
        conn,
        "msg1",
        [
            {
                "message_id": "msg1",
                "attachment_id": "a1",
                "filename": "logo.png",
                "mime_type": "image/png",
                "size": 1,
                "content_id": "<logo@example>",
            }
        ],
    )
    row = conn.execute("SELECT content_id FROM attachments WHERE message_id = 'msg1'").fetchone()
    assert row == ("<logo@example>",)
    conn.close()


def test_init_db_adds_body_html_column_to_pre_existing_messages_table(tmp_path):
    db_path = tmp_path / "gmail.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE messages (id TEXT PRIMARY KEY, subject TEXT)")
    conn.commit()
    conn.close()

    conn = init_db(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
    assert "body_html" in columns
    conn.close()


def test_upsert_message_persists_body_html(tmp_path):
    conn = init_db(tmp_path / "gmail.db")
    upsert_message(
        conn,
        {
            "id": "msg1",
            "thread_id": None,
            "sender": None,
            "recipient": None,
            "cc": None,
            "bcc": None,
            "subject": None,
            "date": None,
            "internal_date_ms": None,
            "snippet": None,
            "label_ids": None,
            "body_text": "Plain body",
            "body_mime_type": "text/plain",
            "body_html": "<p>HTML body</p>",
        },
    )
    row = conn.execute("SELECT body_html FROM messages WHERE id = 'msg1'").fetchone()
    assert row == ("<p>HTML body</p>",)
    conn.close()


def test_upsert_message_defaults_body_html_to_none_when_not_supplied(tmp_path):
    """Callers that predate body_html (e.g. an older test fixture or a source parser not yet
    updated) must not crash upsert_message just because the key is missing from the dict."""
    conn = init_db(tmp_path / "gmail.db")
    upsert_message(
        conn,
        {
            "id": "msg1",
            "thread_id": None,
            "sender": None,
            "recipient": None,
            "cc": None,
            "bcc": None,
            "subject": None,
            "date": None,
            "internal_date_ms": None,
            "snippet": None,
            "label_ids": None,
            "body_text": "Plain body",
            "body_mime_type": "text/plain",
        },
    )
    row = conn.execute("SELECT body_html FROM messages WHERE id = 'msg1'").fetchone()
    assert row == (None,)
    conn.close()
