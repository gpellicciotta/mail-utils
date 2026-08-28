import email
import mailbox
import zipfile
from email.message import EmailMessage

from mail_utils import attachment_store, cli
from mail_utils.cli import _run_import_thunderbird, build_parser
from mail_utils.db import init_db
from mail_utils.thunderbird.archive import is_mail_store_file, walk_folders
from mail_utils.thunderbird.messages import (
    decode_header_str,
    extract_body,
    extract_dates,
    make_message_id,
    parse_addresses,
    parse_attachments,
    parse_message,
)
from mail_utils.thunderbird.tree import (
    ThunderbirdFolder,
    clean_folder_path,
    folder_label_id,
    labels_for_folders,
)


def test_clean_folder_path_normalizes_sbd_and_prefixes():
    assert clean_folder_path("Mail/Local Folders/Inbox") == "Local Folders/Inbox"
    assert clean_folder_path("ImapMail/iceage.anubex.com/INBOX") == "iceage.anubex.com/INBOX"
    assert (
        clean_folder_path("ImapMail/iceage.anubex.com/active-client-projects.sbd/swets.sbd/stad-issues")
        == "iceage.anubex.com/active-client-projects/swets/stad-issues"
    )
    assert clean_folder_path("Projects.sbd/2026.sbd/Q1") == "Projects/2026/Q1"
    assert clean_folder_path("Mail\\Local Folders\\Archive.sbd\\2020") == "Local Folders/Archive/2020"


def test_folder_label_id_is_deterministic_and_prefixed():
    lid1 = folder_label_id("Local Folders/Inbox")
    lid2 = folder_label_id("Local Folders/Inbox")
    assert lid1 == lid2
    assert lid1.startswith("thunderbird_folder:")


def test_labels_for_folders_deduplicates_and_maps():
    folders = [
        ThunderbirdFolder(path="Inbox", source_identifier="Inbox"),
        ThunderbirdFolder(path="Inbox", source_identifier="Inbox.2"),
        ThunderbirdFolder(path="", source_identifier="root"),
        ThunderbirdFolder(path="Sent", source_identifier="Sent"),
    ]
    labels = labels_for_folders(folders)
    assert len(labels) == 2
    assert {label["name"] for label in labels} == {"Inbox", "Sent"}


def test_is_mail_store_file_rejects_indexes_and_metadata():
    assert is_mail_store_file("INBOX.msf") is False
    assert is_mail_store_file("msgFilterRules.dat") is False
    assert is_mail_store_file("filterlog.html") is False
    assert is_mail_store_file("panacea.dat") is False
    assert is_mail_store_file("prefs.js") is False
    assert is_mail_store_file(".DS_Store") is False
    assert is_mail_store_file("INBOX") is True
    assert is_mail_store_file("Sent Mail") is True
    assert is_mail_store_file("Custom_Folder") is True


def test_decode_header_str():
    assert decode_header_str("Plain Subject") == "Plain Subject"
    assert decode_header_str("=?utf-8?B?Q2Fmw6kgVGVzdA==?=") == "Café Test"
    assert decode_header_str("") == ""
    assert decode_header_str(None) == ""


def test_make_message_id_uses_header_or_fallback_hash():
    msg = EmailMessage()
    msg["Message-ID"] = "<12345@example.com>"
    assert make_message_id(msg) == "thunderbird:<12345@example.com>"

    msg_no_id = EmailMessage()
    msg_no_id["Subject"] = "No ID"
    msg_no_id["From"] = "test@example.com"
    msg_id = make_message_id(msg_no_id)
    assert msg_id.startswith("thunderbird:sha1:")


def test_extract_dates_with_rfc_date_and_fallback():
    msg = EmailMessage()
    msg["Date"] = "Wed, 19 Aug 2026 10:00:00 -0700"
    date_str, ts = extract_dates(msg)
    assert date_str == "Wed, 19 Aug 2026 10:00:00 -0700"
    assert ts is not None

    # Fallback to get_from envelope
    msg_env = email.message_from_string("Subject: Test\n\nBody")
    msg_env.get_from = lambda: "From - Thu Jan 15 16:42:05 2009"
    date_str2, ts2 = extract_dates(msg_env)
    assert "2009" in date_str2
    assert ts2 == 1232037725000


def test_extract_body_prefers_plain_text():
    msg = EmailMessage()
    msg.set_content("Plain text body")
    msg.add_alternative("<p>HTML body</p>", subtype="html")
    text, mime_type = extract_body(msg)
    assert text.strip() == "Plain text body"
    assert mime_type == "text/plain"


def test_extract_body_html_fallback():
    msg = EmailMessage()
    msg.set_content("<p>HTML only body</p>", subtype="html")
    text, mime_type = extract_body(msg)
    assert "<p>HTML only body</p>" in text
    assert mime_type == "text/html"


def test_parse_message_and_addresses_and_attachments():
    msg = EmailMessage()
    msg["Message-ID"] = "<msg-test-1@example.com>"
    msg["Subject"] = "=?utf-8?B?Q2Fmw6k=?="
    msg["From"] = "Jane Doe <jane@example.com>"
    msg["To"] = "Alice <alice@example.com>, Bob <bob@example.com>"
    msg["Cc"] = "boss@example.com"
    msg["Date"] = "Wed, 19 Aug 2026 10:00:00 +0000"
    msg.set_content("Here is the report.")
    msg.add_attachment(b"PDF content bytes", maintype="application", subtype="pdf", filename="report.pdf")

    parsed = parse_message(msg, label_id="label_123")
    assert parsed["id"] == "thunderbird:<msg-test-1@example.com>"
    assert parsed["subject"] == "Café"
    assert parsed["sender"] == "Jane Doe <jane@example.com>"
    assert parsed["recipient"] == "Alice <alice@example.com>, Bob <bob@example.com>"
    assert parsed["cc"] == "boss@example.com"
    assert parsed["label_ids"] == "label_123"
    assert parsed["body_text"].strip() == "Here is the report."
    assert parsed["body_mime_type"] == "text/plain"

    addrs = parse_addresses(msg)
    assert len(addrs) == 4
    roles = {a["role"] for a in addrs}
    assert roles == {"from", "to", "cc"}

    atts = parse_attachments(msg)
    assert len(atts) == 1
    assert atts[0]["filename"] == "report.pdf"
    assert atts[0]["mime_type"] == "application/pdf"
    assert atts[0]["size"] == len(b"PDF content bytes")
    assert atts[0]["content"] is None

    atts_with_content = parse_attachments(msg, with_content=True)
    assert atts_with_content[0]["content"] == b"PDF content bytes"


def test_walk_folders_and_import_thunderbird_end_to_end(tmp_path, monkeypatch):
    db_path = tmp_path / "gmail.db"
    monkeypatch.setattr(cli, "DB_PATH", db_path)

    # Create a synthetic .pcv archive
    raw_mbox = tmp_path / "raw.mbox"
    mbox = mailbox.mbox(raw_mbox)
    msg1 = mailbox.mboxMessage()
    msg1["Message-ID"] = "<msg1@example.com>"
    msg1["Subject"] = "Test 1"
    msg1["From"] = "a@example.com"
    msg1["To"] = "b@example.com"
    msg1["Date"] = "Wed, 19 Aug 2026 10:00:00 +0000"
    msg1.set_payload("Message 1 body")
    mbox.add(msg1)

    msg2 = mailbox.mboxMessage()
    msg2["Message-ID"] = "<msg2@example.com>"
    msg2["Subject"] = "Test 2"
    msg2["From"] = "c@example.com"
    msg2["To"] = "d@example.com"
    msg2["Date"] = "Wed, 19 Aug 2026 11:00:00 +0000"
    msg2.set_payload("Message 2 body")
    mbox.add(msg2)
    mbox.close()

    pcv_path = tmp_path / "backup.pcv"
    with zipfile.ZipFile(pcv_path, "w") as z:
        z.write(raw_mbox, "ImapMail/account.com/INBOX")
        z.writestr("ImapMail/account.com/INBOX.msf", b"msf index bytes")
        z.writestr("prefs.js", b"user_pref('mail', true);")

    folders = walk_folders(pcv_path)
    assert len(folders) == 1
    assert folders[0].path == "account.com/INBOX"

    # Test CLI execution
    args = build_parser().parse_args(["import-thunderbird", str(pcv_path), "--db", str(db_path)])
    assert args.command == "import-thunderbird"
    assert args.archive_path == str(pcv_path)

    args_alias = build_parser().parse_args(["import-pcv", str(pcv_path)])
    assert args_alias.command == "import-pcv"

    _run_import_thunderbird(args)

    conn = init_db(db_path)
    (msg_count,) = conn.execute("SELECT COUNT(*) FROM messages").fetchone()
    (label_count,) = conn.execute("SELECT COUNT(*) FROM labels").fetchone()
    (addr_count,) = conn.execute("SELECT COUNT(*) FROM message_addresses").fetchone()
    conn.close()

    assert msg_count == 2
    assert label_count == 1
    assert addr_count == 4


def test_import_thunderbird_with_attachments_flag_captures_content(tmp_path, monkeypatch):
    db_path = tmp_path / "gmail.db"
    monkeypatch.setattr(cli, "DB_PATH", db_path)
    monkeypatch.setattr(attachment_store, "ATTACHMENTS_DIR", tmp_path / "attachments")

    raw_mbox = tmp_path / "raw.mbox"
    mbox = mailbox.mbox(raw_mbox)
    msg = EmailMessage()
    msg["Message-ID"] = "<msg1@example.com>"
    msg["Subject"] = "Has an attachment"
    msg["From"] = "a@example.com"
    msg["To"] = "b@example.com"
    msg["Date"] = "Wed, 19 Aug 2026 10:00:00 +0000"
    msg.set_content("Body text")
    msg.add_attachment(b"PDF content bytes", maintype="application", subtype="pdf", filename="report.pdf")
    mbox.add(msg)
    mbox.close()

    pcv_path = tmp_path / "backup.pcv"
    with zipfile.ZipFile(pcv_path, "w") as z:
        z.write(raw_mbox, "ImapMail/account.com/INBOX")
        z.writestr("prefs.js", b"user_pref('mail', true);")

    args = build_parser().parse_args(["import-thunderbird", str(pcv_path), "--db", str(db_path), "--with-attachments"])
    _run_import_thunderbird(args)

    conn = init_db(db_path)
    content_sha256, size = conn.execute("SELECT content_sha256, size FROM attachments").fetchone()
    conn.close()

    assert content_sha256 is not None
    assert size == len(b"PDF content bytes")
    assert attachment_store.read(content_sha256) == b"PDF content bytes"


def test_import_thunderbird_without_with_attachments_flag_leaves_content_sha256_null(tmp_path, monkeypatch):
    db_path = tmp_path / "gmail.db"
    monkeypatch.setattr(cli, "DB_PATH", db_path)
    monkeypatch.setattr(attachment_store, "ATTACHMENTS_DIR", tmp_path / "attachments")

    raw_mbox = tmp_path / "raw.mbox"
    mbox = mailbox.mbox(raw_mbox)
    msg = EmailMessage()
    msg["Message-ID"] = "<msg1@example.com>"
    msg["Subject"] = "Has an attachment"
    msg["From"] = "a@example.com"
    msg["To"] = "b@example.com"
    msg["Date"] = "Wed, 19 Aug 2026 10:00:00 +0000"
    msg.set_content("Body text")
    msg.add_attachment(b"PDF content bytes", maintype="application", subtype="pdf", filename="report.pdf")
    mbox.add(msg)
    mbox.close()

    pcv_path = tmp_path / "backup.pcv"
    with zipfile.ZipFile(pcv_path, "w") as z:
        z.write(raw_mbox, "ImapMail/account.com/INBOX")
        z.writestr("prefs.js", b"user_pref('mail', true);")

    args = build_parser().parse_args(["import-thunderbird", str(pcv_path), "--db", str(db_path)])
    _run_import_thunderbird(args)

    conn = init_db(db_path)
    (content_sha256,) = conn.execute("SELECT content_sha256 FROM attachments").fetchone()
    conn.close()

    assert content_sha256 is None
    assert not (tmp_path / "attachments").exists()
