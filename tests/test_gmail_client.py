import base64

from mail_utils.gmail_client import (
    _extract_body_text,
    create_label,
    fetch_attachment_content,
    import_message,
    parse_addresses,
    parse_attachments,
    parse_message,
)


class _FakeExec:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class _FakeAttachmentsResource:
    def __init__(self):
        self.get_calls = []

    def get(self, userId, messageId, id):
        self.get_calls.append({"userId": userId, "messageId": messageId, "id": id})
        return _FakeExec({"size": 11, "data": _b64("attachment content")})


class _FakeMessagesResource:
    def __init__(self):
        self.import_calls = []
        self.attachments_resource = _FakeAttachmentsResource()

    def import_(self, userId, body, internalDateSource, neverMarkSpam):
        self.import_calls.append(
            {"userId": userId, "body": body, "internalDateSource": internalDateSource, "neverMarkSpam": neverMarkSpam}
        )
        return _FakeExec({"id": "new_gmail_id"})

    def attachments(self):
        return self.attachments_resource


class _FakeLabelsResource:
    def __init__(self):
        self.create_calls = []

    def create(self, userId, body):
        self.create_calls.append({"userId": userId, "body": body})
        return _FakeExec({"id": f"Label_{body['name']}", "name": body["name"]})


class _FakeUsers:
    def __init__(self):
        self.messages_resource = _FakeMessagesResource()
        self.labels_resource = _FakeLabelsResource()

    def messages(self):
        return self.messages_resource

    def labels(self):
        return self.labels_resource


class _FakeService:
    def __init__(self):
        self.users_resource = _FakeUsers()

    def users(self):
        return self.users_resource


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")


def _text_part(mime_type: str, text: str) -> dict:
    return {"mimeType": mime_type, "body": {"data": _b64(text)}}


def test_extract_body_text_prefers_plain_when_siblings():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [_text_part("text/plain", "Plain body"), _text_part("text/html", "<p>HTML body</p>")],
    }
    assert _extract_body_text(payload) == ("Plain body", "text/plain")


def test_extract_body_text_falls_back_to_raw_html_when_no_plain_part():
    payload = _text_part("text/html", "<p>Only HTML</p>")
    assert _extract_body_text(payload) == ("<p>Only HTML</p>", "text/html")


def test_extract_body_text_returns_empty_for_no_text_parts():
    payload = {"mimeType": "multipart/mixed", "parts": [{"mimeType": "application/pdf", "body": {}}]}
    assert _extract_body_text(payload) == ("", None)


def test_parse_message_maps_headers_and_metadata():
    raw = {
        "id": "msg1",
        "threadId": "thread1",
        "snippet": "a short preview",
        "labelIds": ["INBOX", "UNREAD"],
        "internalDate": "1566230400000",
        "payload": {
            "headers": [
                {"name": "From", "value": "Jane Doe <jane@example.com>"},
                {"name": "To", "value": "me@example.com"},
                {"name": "Subject", "value": "Hello"},
                {"name": "Date", "value": "Wed, 19 Aug 2026 10:00:00 -0700"},
            ],
            **_text_part("text/plain", "Body text"),
        },
    }
    parsed = parse_message(raw)
    assert parsed == {
        "id": "gmail:msg1",
        "thread_id": "thread1",
        "sender": "Jane Doe <jane@example.com>",
        "recipient": "me@example.com",
        "cc": None,
        "bcc": None,
        "subject": "Hello",
        "date": "Wed, 19 Aug 2026 10:00:00 -0700",
        "internal_date_ms": 1566230400000,
        "snippet": "a short preview",
        "label_ids": "INBOX,UNREAD",
        "body_text": "Body text",
        "body_mime_type": "text/plain",
    }


def test_parse_message_internal_date_ms_is_none_when_absent():
    raw = {"id": "msg1", "payload": {"headers": []}}
    parsed = parse_message(raw)
    assert parsed["internal_date_ms"] is None


def test_parse_message_captures_cc_and_bcc_headers():
    raw = {
        "id": "msg1",
        "threadId": "thread1",
        "snippet": "",
        "labelIds": [],
        "payload": {
            "headers": [
                {"name": "From", "value": "jane@example.com"},
                {"name": "To", "value": "me@example.com"},
                {"name": "Cc", "value": "carl@example.com"},
                {"name": "Bcc", "value": "hidden@example.com"},
            ],
        },
    }
    parsed = parse_message(raw)
    assert parsed["cc"] == "carl@example.com"
    assert parsed["bcc"] == "hidden@example.com"


def test_parse_addresses_splits_and_normalizes_multi_address_headers():
    raw = {
        "id": "msg1",
        "payload": {
            "headers": [
                {"name": "From", "value": "Jane Doe <Jane@Example.com>"},
                {"name": "To", "value": 'Bob <bob@example.com>, "Carl, Jr" <CARL@example.com>'},
            ],
        },
    }
    rows = parse_addresses(raw)
    assert rows == [
        {"message_id": "gmail:msg1", "role": "from", "address": "jane@example.com", "name": "Jane Doe"},
        {"message_id": "gmail:msg1", "role": "to", "address": "bob@example.com", "name": "Bob"},
        {"message_id": "gmail:msg1", "role": "to", "address": "carl@example.com", "name": "Carl, Jr"},
    ]


def test_parse_addresses_dedupes_repeated_address_in_same_header():
    raw = {
        "id": "msg1",
        "payload": {
            "headers": [{"name": "To", "value": "a@x.com, A@X.COM"}],
        },
    }
    rows = parse_addresses(raw)
    assert rows == [{"message_id": "gmail:msg1", "role": "to", "address": "a@x.com", "name": None}]


def test_parse_addresses_skips_absent_headers():
    raw = {"id": "msg1", "payload": {"headers": [{"name": "From", "value": "a@x.com"}]}}
    rows = parse_addresses(raw)
    assert [r["role"] for r in rows] == ["from"]


def test_parse_attachments_finds_nested_filenamed_parts():
    raw = {
        "id": "msg1",
        "payload": {
            "mimeType": "multipart/mixed",
            "parts": [
                _text_part("text/plain", "Body"),
                {
                    "mimeType": "multipart/mixed",
                    "parts": [
                        {
                            "mimeType": "application/pdf",
                            "filename": "invoice.pdf",
                            "body": {"attachmentId": "att1", "size": 12345},
                        }
                    ],
                },
                {
                    "mimeType": "image/png",
                    "filename": "photo.png",
                    "body": {"attachmentId": "att2", "size": 999},
                },
            ],
        },
    }
    rows = parse_attachments(raw)
    assert rows == [
        {
            "message_id": "gmail:msg1",
            "attachment_id": "att1",
            "filename": "invoice.pdf",
            "mime_type": "application/pdf",
            "size": 12345,
        },
        {"message_id": "gmail:msg1", "attachment_id": "att2", "filename": "photo.png", "mime_type": "image/png", "size": 999},
    ]


def test_parse_attachments_returns_empty_when_none_present():
    raw = {"id": "msg1", "payload": _text_part("text/plain", "Body")}
    assert parse_attachments(raw) == []


def test_import_message_base64url_encodes_raw_bytes_and_sets_flags():
    service = _FakeService()
    raw_bytes = b"From: a@example.com\r\nSubject: Hi\r\n\r\nBody"

    result = import_message(service, raw_bytes, label_ids=["INBOX", "Label_1"])

    assert result == {"id": "new_gmail_id"}
    (call,) = service.users_resource.messages_resource.import_calls
    assert call["userId"] == "me"
    assert call["internalDateSource"] == "dateHeader"
    assert call["neverMarkSpam"] is True
    assert call["body"]["labelIds"] == ["INBOX", "Label_1"]
    assert base64.urlsafe_b64decode(call["body"]["raw"]) == raw_bytes


def test_import_message_omits_label_ids_when_none_given():
    service = _FakeService()
    import_message(service, b"raw", label_ids=None)
    (call,) = service.users_resource.messages_resource.import_calls
    assert "labelIds" not in call["body"]


def test_fetch_attachment_content_decodes_base64url_data():
    service = _FakeService()
    content = fetch_attachment_content(service, "msg1", "att1")
    assert content == b"attachment content"
    (call,) = service.users_resource.messages_resource.attachments_resource.get_calls
    assert call == {"userId": "me", "messageId": "msg1", "id": "att1"}


def test_create_label_calls_labels_create_with_name():
    service = _FakeService()
    result = create_label(service, "Work/Projects")
    assert result == {"id": "Label_Work/Projects", "name": "Work/Projects"}
    (call,) = service.users_resource.labels_resource.create_calls
    assert call == {"userId": "me", "body": {"name": "Work/Projects"}}
