import base64

from gmail_ingest.gmail_client import _extract_body_text, parse_message


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")


def _text_part(mime_type: str, text: str) -> dict:
    return {"mimeType": mime_type, "body": {"data": _b64(text)}}


def test_extract_body_text_prefers_plain_when_siblings():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [_text_part("text/plain", "Plain body"), _text_part("text/html", "<p>HTML body</p>")],
    }
    assert _extract_body_text(payload) == "Plain body"


def test_extract_body_text_falls_back_to_raw_html_when_no_plain_part():
    payload = _text_part("text/html", "<p>Only HTML</p>")
    assert _extract_body_text(payload) == "<p>Only HTML</p>"


def test_extract_body_text_returns_empty_for_no_text_parts():
    payload = {"mimeType": "multipart/mixed", "parts": [{"mimeType": "application/pdf", "body": {}}]}
    assert _extract_body_text(payload) == ""


def test_parse_message_maps_headers_and_metadata():
    raw = {
        "id": "msg1",
        "threadId": "thread1",
        "snippet": "a short preview",
        "labelIds": ["INBOX", "UNREAD"],
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
        "snippet": "a short preview",
        "label_ids": "INBOX,UNREAD",
        "body_text": "Body text",
    }


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
