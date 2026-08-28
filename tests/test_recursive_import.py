import email.message

from mail_utils import attachment_store
from mail_utils.cli import _process_gmail_msg, _process_tb_message
from mail_utils.db import init_db
from mail_utils.gmail_client import extract_attached_messages as gmail_extract_attached_messages
from mail_utils.thunderbird.messages import extract_attached_messages as tb_extract_attached_messages


def _build_mime_with_attached_msg() -> email.message.EmailMessage:
    outer = email.message.EmailMessage()
    outer["Subject"] = "Outer Parent Message"
    outer["From"] = "parent@example.com"
    outer["To"] = "receiver@example.com"
    outer["Date"] = "Fri, 21 Aug 2026 10:00:00 +0000"
    outer["Message-ID"] = "<outer-123@example.com>"
    outer.set_content("Please see the attached forwarded email below.")

    inner = email.message.EmailMessage()
    inner["Subject"] = "Inner Attached Message"
    inner["From"] = "nested@example.com"
    inner["To"] = "parent@example.com"
    inner["Date"] = "Thu, 20 Aug 2026 15:30:00 +0000"
    inner["Message-ID"] = "<inner-456@example.com>"
    inner.set_content("This is the secret content of the inner email.")

    outer.add_attachment(
        inner.as_bytes(),
        maintype="message",
        subtype="rfc822",
        filename="forwarded_email.eml",
    )
    return outer


def test_thunderbird_extract_attached_messages():
    outer = _build_mime_with_attached_msg()
    extracted = tb_extract_attached_messages(outer)
    assert len(extracted) == 1
    assert extracted[0].get("Subject") == "Inner Attached Message"
    assert "secret content" in extracted[0].get_content()


def test_thunderbird_recursive_import(tmp_path):
    db_path = tmp_path / "test_tb_rec.db"
    conn = init_db(db_path)

    outer = _build_mime_with_attached_msg()

    # Non-recursive import -> only 1 message
    count_non_rec = _process_tb_message(conn, outer, label_id="inbox", recursive=False)
    assert count_non_rec == 1
    (total_msgs,) = conn.execute("SELECT COUNT(*) FROM messages").fetchone()
    assert total_msgs == 1

    # Recursive import -> imports 2 messages (parent + child)
    conn.execute("DELETE FROM messages")
    conn.commit()
    count_rec = _process_tb_message(conn, outer, label_id="inbox", recursive=True)
    assert count_rec == 2
    (total_msgs,) = conn.execute("SELECT COUNT(*) FROM messages").fetchone()
    assert total_msgs == 2

    # Check both subjects exist in db
    subjects = {r[0] for r in conn.execute("SELECT subject FROM messages").fetchall()}
    assert subjects == {"Outer Parent Message", "Inner Attached Message"}

    conn.close()


def test_gmail_extract_and_recursive_import(tmp_path, monkeypatch):
    raw_parent = {
        "id": "18e12345678",
        "threadId": "thread999",
        "internalDate": "1767268800000",
        "labelIds": ["INBOX"],
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "parent@example.com"},
                {"name": "To", "value": "me@example.com"},
                {"name": "Subject", "value": "Parent Email"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "headers": [{"name": "Content-Type", "value": "text/plain"}],
                    "body": {"data": "SGVsbG8="},  # "Hello"
                },
                {
                    "mimeType": "message/rfc822",
                    "filename": "attached.eml",
                    "headers": [
                        {"name": "From", "value": "sub@example.com"},
                        {"name": "To", "value": "parent@example.com"},
                        {"name": "Subject", "value": "Child Attached Email"},
                    ],
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "headers": [{"name": "Content-Type", "value": "text/plain"}],
                            "body": {"data": "Q2hpbGQgQm9keQ=="},
                        }
                    ],
                },
            ],
        },
    }

    sub_extracted = gmail_extract_attached_messages(raw_parent)
    assert len(sub_extracted) == 1
    assert sub_extracted[0]["id"] == "18e12345678_att1"

    db_path = tmp_path / "test_gmail_rec.db"
    conn = init_db(db_path)

    # Mock fetch_message to return raw_parent
    class FakeService:
        pass

    monkeypatch.setattr("mail_utils.cli.fetch_message", lambda service, msg_id: raw_parent)

    count_rec = _process_gmail_msg(FakeService(), conn, "18e12345678", recursive=True)
    assert count_rec == 2

    (total_msgs,) = conn.execute("SELECT COUNT(*) FROM messages").fetchone()
    assert total_msgs == 2

    subjects = {r[0] for r in conn.execute("SELECT subject FROM messages").fetchall()}
    assert subjects == {"Parent Email", "Child Attached Email"}

    conn.close()


def test_gmail_recursive_import_with_attachments_uses_real_parent_message_id(tmp_path, monkeypatch):
    """A nested (message/rfc822-attached) sub-message's own attachments still carry attachmentId
    values scoped to the *real* top-level Gmail message, not the synthesized sub-message id
    gmail_extract_attached_messages() invents - fetching content for one must use the parent's real
    id or the Gmail API call would 404."""
    raw_parent = {
        "id": "18e12345678",
        "threadId": "thread999",
        "internalDate": "1767268800000",
        "labelIds": ["INBOX"],
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "parent@example.com"},
                {"name": "To", "value": "me@example.com"},
                {"name": "Subject", "value": "Parent Email"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "headers": [{"name": "Content-Type", "value": "text/plain"}],
                    "body": {"data": "SGVsbG8="},
                },
                {
                    "mimeType": "message/rfc822",
                    "filename": "attached.eml",
                    "headers": [
                        {"name": "From", "value": "sub@example.com"},
                        {"name": "To", "value": "parent@example.com"},
                        {"name": "Subject", "value": "Child Attached Email"},
                    ],
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "headers": [{"name": "Content-Type", "value": "text/plain"}],
                            "body": {"data": "Q2hpbGQgQm9keQ=="},
                        },
                        {
                            "mimeType": "application/pdf",
                            "filename": "nested.pdf",
                            "body": {"attachmentId": "nested-att-1", "size": 42},
                        },
                    ],
                },
            ],
        },
    }

    db_path = tmp_path / "test_gmail_rec_attachments.db"
    conn = init_db(db_path)
    attachment_store.configure(tmp_path / "attachments")
    monkeypatch.setattr("mail_utils.cli.fetch_message", lambda service, msg_id: raw_parent)

    fetch_calls = []

    def fake_fetch_attachment_content(service, message_id, attachment_id):
        fetch_calls.append((message_id, attachment_id))
        return b"nested pdf bytes"

    monkeypatch.setattr("mail_utils.cli.fetch_attachment_content", fake_fetch_attachment_content)

    class FakeService:
        pass

    count = _process_gmail_msg(FakeService(), conn, "18e12345678", recursive=True, with_attachments=True)
    assert count == 2

    # parse_attachments() walks MIME parts without stopping at a message/rfc822 boundary, so the
    # nested pdf is (pre-existing, unrelated to --with-attachments) picked up twice: once attributed
    # to the parent message, once to the extracted child message - both fetches correctly use the
    # real parent id, not the synthesized child id, which is the property this test guards.
    assert fetch_calls == [("18e12345678", "nested-att-1"), ("18e12345678", "nested-att-1")]

    (content_sha256,) = conn.execute("SELECT content_sha256 FROM attachments WHERE filename = 'nested.pdf'").fetchone()
    assert content_sha256 is not None
    assert attachment_store.read(content_sha256) == b"nested pdf bytes"

    conn.close()


def test_gmail_import_without_with_attachments_flag_never_fetches_content(tmp_path, monkeypatch):
    """The most important regression guard here: everyone who never opts into --with-attachments
    must see zero behavior change - no extra API calls, content_sha256 stays NULL."""
    raw_parent = {
        "id": "18e12345678",
        "threadId": "thread999",
        "internalDate": "1767268800000",
        "labelIds": ["INBOX"],
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "parent@example.com"},
                {"name": "To", "value": "me@example.com"},
                {"name": "Subject", "value": "Parent Email"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "headers": [{"name": "Content-Type", "value": "text/plain"}],
                    "body": {"data": "SGVsbG8="},
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "report.pdf",
                    "body": {"attachmentId": "att-1", "size": 42},
                },
            ],
        },
    }

    db_path = tmp_path / "test_gmail_no_attachments_flag.db"
    conn = init_db(db_path)
    monkeypatch.setattr("mail_utils.cli.fetch_message", lambda service, msg_id: raw_parent)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("fetch_attachment_content must not be called when --with-attachments is off")

    monkeypatch.setattr("mail_utils.cli.fetch_attachment_content", _fail_if_called)

    class FakeService:
        pass

    count = _process_gmail_msg(FakeService(), conn, "18e12345678", recursive=False)
    assert count == 1

    (content_sha256,) = conn.execute("SELECT content_sha256 FROM attachments WHERE filename = 'report.pdf'").fetchone()
    assert content_sha256 is None

    conn.close()
