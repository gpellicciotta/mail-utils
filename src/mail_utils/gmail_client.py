import base64
from collections.abc import Iterator
from email.utils import getaddresses

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class HistoryExpiredError(Exception):
    """Raised when Gmail can no longer diff from the stored historyId."""


ID_PREFIX = "gmail:"
"""Prefixed onto every row's id/message_id so it can never collide with an `outlook:`-prefixed
row from a PST import into the same database (see pst/messages.py) - the prefix alone carries the
source, so there's no separate `source` column. Raw (unprefixed) Gmail message ids are still what
every Gmail API call itself uses - only the stored row id changes."""


def build_gmail_service(creds: Credentials):
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def get_current_history_id(service) -> str:
    profile = service.users().getProfile(userId="me").execute()
    return profile["historyId"]


def get_profile(service) -> dict:
    """Return the full Gmail profile (historyId, messagesTotal, etc.).

    messagesTotal counts every message including Spam/Trash, whereas
    list_all_message_ids excludes them by default, so it's an upper bound
    on the full-sync message count rather than an exact match.
    """
    return service.users().getProfile(userId="me").execute()


def list_all_message_ids(service, query: str | None = None) -> Iterator[str]:
    """Yield every message id in the mailbox (used for the initial full sync)."""
    page_token = None
    while True:
        resp = service.users().messages().list(userId="me", q=query, pageToken=page_token, maxResults=500).execute()
        for m in resp.get("messages", []):
            yield m["id"]
        page_token = resp.get("nextPageToken")
        if not page_token:
            break


def list_changed_message_ids(service, start_history_id: str) -> Iterator[str]:
    """Yield message ids added since start_history_id.

    Raises HistoryExpiredError if start_history_id is too old for Gmail
    to diff from (typically after ~a week), in which case the caller
    should fall back to a full resync.
    """
    page_token = None
    seen = set()
    while True:
        try:
            resp = (
                service.users()
                .history()
                .list(
                    userId="me",
                    startHistoryId=start_history_id,
                    historyTypes=["messageAdded"],
                    pageToken=page_token,
                )
                .execute()
            )
        except HttpError as e:
            if e.resp.status == 404:
                raise HistoryExpiredError from e
            raise

        for record in resp.get("history", []):
            for added in record.get("messagesAdded", []):
                msg_id = added["message"]["id"]
                if msg_id not in seen:
                    seen.add(msg_id)
                    yield msg_id

        page_token = resp.get("nextPageToken")
        if not page_token:
            break


def list_labels(service) -> list:
    """Return every label in the mailbox as [{"id": ..., "name": ...}, ...].

    Covers both system labels (INBOX, SENT, UNREAD, ...) and the user's
    own custom labels, which otherwise only appear as opaque
    Label_NNNNNNN ids on messages.
    """
    resp = service.users().labels().list(userId="me").execute()
    return [{"id": lbl["id"], "name": lbl["name"]} for lbl in resp.get("labels", [])]


def fetch_message(service, msg_id: str) -> dict:
    return service.users().messages().get(userId="me", id=msg_id, format="full").execute()


def fetch_attachment_content(service, message_id: str, attachment_id: str) -> bytes:
    """Fetch one attachment's actual bytes via `users.messages.attachments.get` - a separate API
    call per attachment (uses the `attachmentId` `parse_attachments` already captures), so a caller
    only pays for it when it actually wants content (see cli.py's `--with-attachments`). `message_id`
    must be the real (unprefixed) Gmail id the attachment belongs to."""
    resp = service.users().messages().attachments().get(userId="me", messageId=message_id, id=attachment_id).execute()
    return base64.urlsafe_b64decode(resp["data"])


def import_message(service, raw_bytes: bytes, label_ids: list[str] | None = None) -> dict:
    """Write `raw_bytes` (a full RFC 5322 message) into the mailbox via
    `users.messages.import` - applies normal spam/classification scanning
    like an incoming SMTP delivery would, except `neverMarkSpam=True`
    suppresses the spam side effect specifically for this restore use case.
    `internalDateSource="dateHeader"` keeps the message's original Date:
    header as its arrival date rather than "now"."""
    body = {"raw": base64.urlsafe_b64encode(raw_bytes).decode("ascii")}
    if label_ids:
        body["labelIds"] = label_ids
    return service.users().messages().import_(userId="me", body=body, internalDateSource="dateHeader", neverMarkSpam=True).execute()


def create_label(service, name: str) -> dict:
    return service.users().labels().create(userId="me", body={"name": name}).execute()


def delete_label(service, label_id: str) -> None:
    """Delete a label outright (not just remove it from messages) - requires gmail.labels or
    gmail.modify, same as create_label. Used by scripts/gmail-roundtrip-test.py's cleanup action so a
    disposable test run doesn't leave an empty label sitting in the mailbox indefinitely."""
    service.users().labels().delete(userId="me", id=label_id).execute()


def _decode_part(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode("UTF-8")).decode("UTF-8", errors="replace")


def _extract_body_text(payload: dict) -> tuple:
    """Return (text, mime_type) for the body text this message stores -
    mime_type is "text/plain" or "text/html" (the raw-HTML fallback case),
    or None alongside "" when there's no text part at all."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return _decode_part(payload["body"]["data"]), "text/plain"

    for part in payload.get("parts", []) or []:
        text, mime_type = _extract_body_text(part)
        if text:
            return text, mime_type

    # Fall back to text/html-only messages: strip nothing, just return raw for now.
    if payload.get("mimeType") == "text/html" and payload.get("body", {}).get("data"):
        return _decode_part(payload["body"]["data"]), "text/html"

    return "", None


def _extract_body_html(payload: dict) -> str | None:
    """Return the raw text/html part's content when this message has one, independent of whether
    a text/plain sibling also exists - unlike _extract_body_text (which prefers plain and only
    falls back to html when no plain part exists anywhere), this always finds the html part so it
    can be preserved alongside body_text rather than lost when both representations are present."""
    if payload.get("mimeType") == "text/html" and payload.get("body", {}).get("data"):
        return _decode_part(payload["body"]["data"])

    for part in payload.get("parts", []) or []:
        html = _extract_body_html(part)
        if html:
            return html

    return None


def _headers(raw: dict) -> dict:
    return {h["name"].lower(): h["value"] for h in raw.get("payload", {}).get("headers", [])}


def parse_message(raw: dict) -> dict:
    headers = _headers(raw)
    payload = raw.get("payload", {})
    body_text, body_mime_type = _extract_body_text(payload)
    return {
        "id": ID_PREFIX + raw["id"],
        "thread_id": raw.get("threadId"),
        "sender": headers.get("from"),
        "recipient": headers.get("to"),
        "cc": headers.get("cc"),
        "bcc": headers.get("bcc"),
        "subject": headers.get("subject"),
        "date": headers.get("date"),
        "internal_date_ms": int(raw["internalDate"]) if raw.get("internalDate") else None,
        "snippet": raw.get("snippet"),
        "label_ids": ",".join(raw.get("labelIds", [])),
        "body_text": body_text,
        "body_mime_type": body_mime_type,
        "body_html": _extract_body_html(payload),
    }


def parse_addresses(raw: dict) -> list:
    """Return one row per distinct (role, address) pair on this message,
    from the From/To/Cc/Bcc headers - e.g.
    [{"message_id": ..., "role": "to", "address": "a@x.com", "name": "A"}, ...]

    Addresses are lowercased for dedup (real-world mail providers, Gmail
    included, treat addresses as case-insensitive even though the RFC
    technically allows a case-sensitive local part). Multiple addresses in
    one header (e.g. several To: recipients) are each their own row;
    duplicate addresses within the same header+message are collapsed.
    """
    message_id = ID_PREFIX + raw["id"]
    headers = _headers(raw)
    rows = []
    for role in ("from", "to", "cc", "bcc"):
        value = headers.get(role)
        if not value:
            continue
        seen = set()
        for name, addr in getaddresses([value]):
            addr = addr.strip().lower()
            if not addr or addr in seen:
                continue
            seen.add(addr)
            rows.append({"message_id": message_id, "role": role, "address": addr, "name": name.strip() or None})
    return rows


def _part_content_id(part: dict) -> str | None:
    """Return this MIME part's `Content-ID` header value (e.g. `<image001.png@01D...>`), or None -
    the marker an HTML body's `<img src="cid:...">` reference points at, present on inline-image
    parts but not on conventional attachments."""
    for header in part.get("headers", []) or []:
        if header.get("name", "").lower() == "content-id":
            return header.get("value")
    return None


def parse_attachments(raw: dict) -> list:
    """Return one row per MIME part that is an attachment or inline image - name (if present),
    mime type, size, Gmail's attachmentId (needed for a future attachments.get fetch;
    the bytes themselves are never fetched here), and content_id (set only for an inline
    image referenced from the HTML body via `cid:`, None for a conventional attachment).

    Includes inline images, not just conventional attachments - this only captures
    metadata, not content, so there's no reason to exclude either.
    """
    message_id = ID_PREFIX + raw["id"]
    attachments = []

    def walk(part: dict) -> None:
        filename = part.get("filename") or None
        body = part.get("body", {})
        attachment_id = body.get("attachmentId")
        content_id = _part_content_id(part)

        if filename or content_id or attachment_id:
            attachments.append(
                {
                    "message_id": message_id,
                    "attachment_id": attachment_id,
                    "filename": filename,
                    "mime_type": part.get("mimeType"),
                    "size": body.get("size"),
                    "content_id": content_id,
                }
            )
        for sub_part in part.get("parts", []) or []:
            walk(sub_part)

    walk(raw.get("payload", {}))
    return attachments


def extract_attached_messages(raw: dict) -> list[dict]:
    """Extract any email messages attached to `raw` (message/rfc822 or .eml)."""
    sub_messages = []

    def walk(part: dict, idx: int) -> int:
        mime = (part.get("mimeType") or "").lower()
        fn = (part.get("filename") or "").lower()
        if (mime == "message/rfc822" or fn.endswith(".eml")) and (part.get("parts") or part.get("headers")):
            sub_id = f"{raw['id']}_att{idx}"
            sub_raw = {
                "id": sub_id,
                "threadId": raw.get("threadId"),
                "internalDate": raw.get("internalDate"),
                "labelIds": raw.get("labelIds", []),
                "snippet": None,
                "payload": part,
            }
            sub_messages.append(sub_raw)
            idx += 1
        for sub_part in part.get("parts", []) or []:
            idx = walk(sub_part, idx)
        return idx

    walk(raw.get("payload", {}), 1)
    return sub_messages
