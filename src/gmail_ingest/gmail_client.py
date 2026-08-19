import base64
from collections.abc import Iterator
from email.utils import getaddresses

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class HistoryExpiredError(Exception):
    """Raised when Gmail can no longer diff from the stored historyId."""


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


def _headers(raw: dict) -> dict:
    return {h["name"].lower(): h["value"] for h in raw.get("payload", {}).get("headers", [])}


def parse_message(raw: dict) -> dict:
    headers = _headers(raw)
    body_text, body_mime_type = _extract_body_text(raw.get("payload", {}))
    return {
        "id": raw["id"],
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
    message_id = raw["id"]
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


def parse_attachments(raw: dict) -> list:
    """Return one row per MIME part that carries a filename - name, mime
    type, size, and Gmail's attachmentId (needed for a future
    attachments.get fetch; the bytes themselves are never fetched here).

    Includes inline images, not just conventional attachments - both show
    up as a "filename" on their MIME part, and this only captures
    metadata, not content, so there's no reason to exclude either.
    """
    message_id = raw["id"]
    attachments = []

    def walk(part: dict) -> None:
        filename = part.get("filename")
        if filename:
            body = part.get("body", {})
            attachments.append(
                {
                    "message_id": message_id,
                    "attachment_id": body.get("attachmentId"),
                    "filename": filename,
                    "mime_type": part.get("mimeType"),
                    "size": body.get("size"),
                }
            )
        for sub_part in part.get("parts", []) or []:
            walk(sub_part)

    walk(raw.get("payload", {}))
    return attachments
