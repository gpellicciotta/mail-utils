import sqlite3

from mail_utils.db import init_db, upsert_attachments


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
