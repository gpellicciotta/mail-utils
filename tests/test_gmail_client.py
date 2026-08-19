import base64

from gmail_ingest.gmail_client import _extract_body_text, parse_addresses, parse_attachments, parse_message


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
        "id": "msg1",
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
        {"message_id": "msg1", "role": "from", "address": "jane@example.com", "name": "Jane Doe"},
        {"message_id": "msg1", "role": "to", "address": "bob@example.com", "name": "Bob"},
        {"message_id": "msg1", "role": "to", "address": "carl@example.com", "name": "Carl, Jr"},
    ]


def test_parse_addresses_dedupes_repeated_address_in_same_header():
    raw = {
        "id": "msg1",
        "payload": {
            "headers": [{"name": "To", "value": "a@x.com, A@X.COM"}],
        },
    }
    rows = parse_addresses(raw)
    assert rows == [{"message_id": "msg1", "role": "to", "address": "a@x.com", "name": None}]


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
        {"message_id": "msg1", "attachment_id": "att1", "filename": "invoice.pdf", "mime_type": "application/pdf", "size": 12345},
        {"message_id": "msg1", "attachment_id": "att2", "filename": "photo.png", "mime_type": "image/png", "size": 999},
    ]


def test_parse_attachments_returns_empty_when_none_present():
    raw = {"id": "msg1", "payload": _text_part("text/plain", "Body")}
    assert parse_attachments(raw) == []
