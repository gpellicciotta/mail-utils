import email.errors
import email.header
import email.message
import email.policy
import email.utils
import hashlib
import re
from datetime import datetime, timezone


def decode_header_str(val: str | None) -> str:
    """Decode an RFC 2047 MIME encoded-word header into a clean Python string."""
    if not val:
        return ""
    try:
        parts = email.header.decode_header(val)
        res = []
        for part, enc in parts:
            if isinstance(part, bytes):
                try:
                    res.append(part.decode(enc or "utf-8", errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    res.append(part.decode("utf-8", errors="replace"))
            else:
                res.append(str(part))
        return "".join(res)
    except (ValueError, LookupError, UnicodeError, email.errors.HeaderParseError):
        return str(val)


def make_message_id(raw_msg: email.message.Message) -> str:
    """Return a unique `thunderbird:<Message-ID>` string, or a content hash fallback."""
    msg_id = raw_msg.get("Message-ID") or raw_msg.get("Message-Id") or raw_msg.get("Resent-Message-ID")
    if msg_id and msg_id.strip():
        return f"thunderbird:{msg_id.strip()}"

    # Fallback to content-derived hash
    h = hashlib.sha1()
    h.update((raw_msg.get("Subject") or "").encode("utf-8", errors="replace"))
    h.update((raw_msg.get("From") or "").encode("utf-8", errors="replace"))
    h.update((raw_msg.get("Date") or "").encode("utf-8", errors="replace"))
    from_line = getattr(raw_msg, "get_from", lambda: None)() or ""
    h.update(from_line.encode("utf-8", errors="replace"))

    payload = raw_msg.get_payload()
    if isinstance(payload, str):
        h.update(payload[:500].encode("utf-8", errors="replace"))
    elif isinstance(payload, bytes):
        h.update(payload[:500])
    return f"thunderbird:sha1:{h.hexdigest()}"


_FROM_LINE_DATE_PATTERN = re.compile(r"([A-Za-z]{3}\s+[A-Za-z]{3}\s+\d+\s+\d{2}:\d{2}:\d{2}\s+\d{4})")


def extract_dates(raw_msg: email.message.Message) -> tuple[str | None, int | None]:
    """Return (date_string, internal_date_ms), falling back to the Mbox From line."""
    raw_date = raw_msg.get("Date")
    if raw_date:
        date_str = decode_header_str(raw_date).strip()
        try:
            dt = email.utils.parsedate_to_datetime(date_str)
            return date_str, int(dt.timestamp() * 1000)
        except (ValueError, TypeError, email.errors.MessageError):
            pass

    # Fallback to Mbox envelope line (e.g. From - Thu Jan 15 16:42:05 2009)
    from_line = getattr(raw_msg, "get_from", lambda: None)()
    if from_line:
        m = _FROM_LINE_DATE_PATTERN.search(from_line)
        if m:
            try:
                dt = datetime.strptime(m.group(1), "%a %b %d %H:%M:%S %Y").replace(tzinfo=timezone.utc)
                return email.utils.format_datetime(dt), int(dt.timestamp() * 1000)
            except ValueError:
                pass

    return raw_date, None


def extract_body(raw_msg: email.message.Message) -> tuple[str, str | None]:
    """Return (body_text, body_mime_type), preferring text/plain over text/html."""
    if raw_msg.is_multipart():
        # First pass: look for text/plain
        for part in raw_msg.walk():
            fn = part.get_filename()
            if not fn and part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload is not None:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        return payload.decode(charset, errors="replace"), "text/plain"
                    except LookupError:
                        return payload.decode("utf-8", errors="replace"), "text/plain"

        # Second pass: look for text/html
        for part in raw_msg.walk():
            fn = part.get_filename()
            if not fn and part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload is not None:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        return payload.decode(charset, errors="replace"), "text/html"
                    except LookupError:
                        return payload.decode("utf-8", errors="replace"), "text/html"
    else:
        ct = raw_msg.get_content_type()
        if ct in ("text/plain", "text/html"):
            payload = raw_msg.get_payload(decode=True)
            if payload is not None:
                charset = raw_msg.get_content_charset() or "utf-8"
                try:
                    return payload.decode(charset, errors="replace"), ct
                except LookupError:
                    return payload.decode("utf-8", errors="replace"), ct

    return "", None


def extract_html_body(raw_msg: email.message.Message) -> str | None:
    """Return the message's text/html part content, independent of whether a text/plain sibling
    also exists - mirrors gmail_client.py's _extract_body_html, so both representations are
    preserved rather than only the plain-text one extract_body prefers."""
    parts = raw_msg.walk() if raw_msg.is_multipart() else [raw_msg]
    for part in parts:
        if part.get_filename():
            continue
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                return payload.decode(charset, errors="replace")
            except LookupError:
                return payload.decode("utf-8", errors="replace")
    return None


def parse_message(raw_msg: email.message.Message, label_id: str | None = None) -> dict:
    """Parse a raw email.message.Message into a `messages` table row dict."""
    msg_id = make_message_id(raw_msg)
    subject = decode_header_str(raw_msg.get("Subject"))
    sender = decode_header_str(raw_msg.get("From"))
    recipient = decode_header_str(raw_msg.get("To"))
    cc = decode_header_str(raw_msg.get("Cc"))
    bcc = decode_header_str(raw_msg.get("Bcc"))
    date_str, internal_date_ms = extract_dates(raw_msg)
    body_text, body_mime_type = extract_body(raw_msg)

    return {
        "id": msg_id,
        "thread_id": None,
        "sender": sender or None,
        "recipient": recipient or None,
        "cc": cc or None,
        "bcc": bcc or None,
        "subject": subject or None,
        "date": date_str,
        "internal_date_ms": internal_date_ms,
        "snippet": None,
        "label_ids": label_id or "",
        "body_text": body_text,
        "body_mime_type": body_mime_type,
        "body_html": extract_html_body(raw_msg),
    }


def parse_addresses(raw_msg: email.message.Message) -> list[dict]:
    """Extract individual sender/recipient addresses into `message_addresses` table rows."""
    msg_id = make_message_id(raw_msg)
    rows = []
    for role in ("from", "to", "cc", "bcc"):
        header_val = raw_msg.get(role)
        if not header_val:
            continue
        decoded = decode_header_str(header_val)
        seen = set()
        for name, addr in email.utils.getaddresses([decoded]):
            addr = addr.strip().lower()
            if not addr or addr in seen:
                continue
            seen.add(addr)
            rows.append({"message_id": msg_id, "role": role, "address": addr, "name": name.strip() or None})
    return rows


def parse_attachments(raw_msg: email.message.Message, with_content: bool = False) -> list[dict]:
    """Extract metadata for every attachment into `attachments` table rows. When `with_content` is
    set, also include the decoded bytes under "content" - `get_payload(decode=True)` already decodes
    them to compute `size`, so this adds no extra I/O over the metadata-only pass, just keeps what
    would otherwise be discarded."""
    msg_id = make_message_id(raw_msg)
    rows = []
    if raw_msg.is_multipart():
        for part in raw_msg.walk():
            fn = part.get_filename()
            if fn:
                decoded_fn = decode_header_str(fn).strip()
                payload = part.get_payload(decode=True)
                size = len(payload) if payload is not None else 0
                rows.append(
                    {
                        "message_id": msg_id,
                        "attachment_id": None,
                        "filename": decoded_fn,
                        "mime_type": part.get_content_type(),
                        "size": size,
                        "content_id": part.get("Content-ID"),
                        "content": payload if with_content else None,
                    }
                )
    return rows


def extract_attached_messages(raw_msg: email.message.Message) -> list[email.message.Message]:
    """Extract any email messages attached to `raw_msg` (message/rfc822 or .eml)."""
    sub_messages = []
    if raw_msg.is_multipart():
        for part in raw_msg.walk():
            if part == raw_msg:
                continue
            ctype = (part.get_content_type() or "").lower()
            fn = (part.get_filename() or "").lower()
            if ctype == "message/rfc822":
                payload = part.get_payload()
                if isinstance(payload, list):
                    for item in payload:
                        if isinstance(item, email.message.Message):
                            sub_messages.append(item)
                elif isinstance(payload, email.message.Message):
                    sub_messages.append(payload)
                elif isinstance(payload, (bytes, str)):
                    raw_bytes = part.get_payload(decode=True) if isinstance(payload, str) else payload
                    if raw_bytes:
                        try:
                            sub_messages.append(email.message_from_bytes(raw_bytes, policy=email.policy.default))
                        except (ValueError, TypeError, email.errors.MessageError):
                            continue
            elif fn.endswith(".eml"):
                raw_bytes = part.get_payload(decode=True)
                if raw_bytes:
                    try:
                        sub_messages.append(email.message_from_bytes(raw_bytes, policy=email.policy.default))
                    except (ValueError, TypeError, email.errors.MessageError):
                        continue
    return sub_messages
