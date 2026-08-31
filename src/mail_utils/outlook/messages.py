"""MAPI property decoding into the same dict/list shapes gmail_client.py produces, so cli.py's
upsert_message/upsert_addresses/upsert_attachments calls don't care which source produced them.

fetch_message() does the PST reads (PC + Recipient/Attachment Tables) once per message; the three
parse_* functions are then pure, deriving their respective dict/list from that single fetch -
mirroring gmail_client.py's fetch_message()/parse_message()/parse_addresses()/parse_attachments()
split exactly.
"""

import hashlib
import struct
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.parser import Parser
from email.utils import getaddresses

from .ltp import PSTProperty, read_property_context, read_table_context
from .ndb import NID_TYPE_ATTACHMENT_TABLE, NID_TYPE_RECIPIENT_TABLE, PSTFile, nid_type

# --- well-known MAPI property tags used here (see [MS-OXPROPS]) --------------------------
PROP_SUBJECT = 0x0037
PROP_CLIENT_SUBMIT_TIME = 0x0039
PROP_MESSAGE_DELIVERY_TIME = 0x0E06
PROP_TRANSPORT_HEADERS = 0x007D
PROP_BODY = 0x1000
PROP_HTML_BODY = 0x1013
PROP_INTERNET_MESSAGE_ID = 0x1035
PROP_MESSAGE_CODEPAGE = 0x3FFD
PROP_SENDER_NAME = 0x0C1A
PROP_SENDER_SMTP_ADDRESS = 0x5D01

PROP_RECIPIENT_TYPE = 0x0C15
PROP_DISPLAY_NAME = 0x3001
PROP_EMAIL_ADDRESS = 0x3003
PROP_SMTP_ADDRESS = 0x39FE

PROP_ATTACH_FILENAME = 0x3704
PROP_ATTACH_LONG_FILENAME = 0x3707
PROP_ATTACH_MIME_TAG = 0x370E
PROP_ATTACH_SIZE = 0x0E20
PROP_ATTACH_DATA_BINARY = 0x3701
PROP_ATTACH_CONTENT_ID = 0x3712  # PidTagAttachContentId - set for an inline image referenced via cid:
PROP_LTP_ROW_ID = 0x67F2  # an Attachment Table row's own attachment-object NID, [MS-PST] 2.4.6.1

PTYPE_STRING = 0x001F  # UTF-16LE
PTYPE_STRING8 = 0x001E  # codepage-dependent 8-bit text

RECIPIENT_TYPE_TO_ROLE = {1: "to", 2: "cc", 3: "bcc"}

# FILETIME (100ns ticks since 1601-01-01) -> Unix epoch (1970-01-01) offset in the same units.
_FILETIME_UNIX_EPOCH_DELTA = 116444736000000000


@dataclass
class RawMessage:
    props: dict  # {prop_id: PSTProperty} from this message's own Property Context
    recipients: list = field(default_factory=list)  # Recipient Table rows, {prop_id: raw_bytes} each
    attachments: list = field(default_factory=list)  # Attachment Table rows, {prop_id: raw_bytes} each
    bid_sub: int = 0  # the message's own subnode BTree bid - needed to fetch individual attachment content


def fetch_message(pst: PSTFile, msg_nid: int) -> RawMessage:
    """Read a message's Property Context plus its Recipient/Attachment Tables (if any).

    A message's Recipient/Attachment Table NIDs are *not* derived from the message's own NID (unlike
    a folder's Hierarchy/Contents Table) - they're arbitrary subnode entries assigned by the writer,
    so finding them means enumerating every subnode and matching by type (verified against
    data/personal-email-backup.pst).
    """
    bid_data, bid_sub = pst.resolve_nid(msg_nid)
    props = read_property_context(pst, bid_data, bid_sub)

    recipients, attachments = [], []
    if bid_sub:
        for nid, sub_bid_data, sub_bid_sub in pst.list_subnodes(bid_sub):
            if nid_type(nid) == NID_TYPE_RECIPIENT_TABLE:
                recipients = read_table_context(pst, sub_bid_data, sub_bid_sub)
            elif nid_type(nid) == NID_TYPE_ATTACHMENT_TABLE:
                attachments = read_table_context(pst, sub_bid_data, sub_bid_sub)
    return RawMessage(props=props, recipients=recipients, attachments=attachments, bid_sub=bid_sub)


def fetch_attachment_content(pst: PSTFile, raw: RawMessage, attachment_row: dict) -> bytes | None:
    """Fetch one attachment's actual bytes (PidTagAttachDataBinary) - a separate resolve + Property
    Context read per attachment, since an Attachment Table row only carries summary properties.
    `attachment_row` identifies which attachment via its own PidTagLtpRowId ([MS-PST] 2.4.6.1), the
    same pattern tree.py uses to get a folder/message's own NID off its hierarchy/contents row -
    except an attachment object is a subnode of its *message* (found via `pst.read_subnode`), not a
    top-level NBT entry."""
    row_id_bytes = attachment_row.get(PROP_LTP_ROW_ID)
    if not row_id_bytes or not raw.bid_sub:
        return None
    attach_nid = struct.unpack_from("<I", row_id_bytes, 0)[0]
    ref = pst.read_subnode(raw.bid_sub, attach_nid)
    if ref is None:
        return None
    bid_data, bid_sub = ref
    attach_props = read_property_context(pst, bid_data, bid_sub)
    data_prop = attach_props.get(PROP_ATTACH_DATA_BINARY)
    return data_prop.value if data_prop is not None else None


# --- low-level property decoding ----------------------------------------------------------


def _codepage(props: dict) -> int:
    prop = props.get(PROP_MESSAGE_CODEPAGE)
    if prop is None:
        return 1252
    return struct.unpack_from("<i", prop.value, 0)[0] or 1252


def _decode_string(prop: PSTProperty, codepage: int) -> str | None:
    if prop is None:
        return None
    if prop.prop_type == PTYPE_STRING:
        return prop.value.decode("utf-16-le", errors="replace")
    # PtypString8, and PtypBinary properties that are really 8-bit text (e.g. PidTagHtmlBody, which
    # carries no type marker of its own beyond PtypBinary) - both are codepage-dependent.
    try:
        return prop.value.decode(f"cp{codepage}", errors="replace")
    except LookupError:
        return prop.value.decode("cp1252", errors="replace")


def _decode_subject(prop: PSTProperty, codepage: int) -> str | None:
    """Strip the optional Subject Prefix marker ([MS-OXCMSG] 2.2.1.10): a leading `tag` character
    (value 1) followed by a `cch` character (the prefix's length) means PidTagSubjectPrefix +
    PidTagNormalizedSubject follow, concatenated. Both marker characters are full characters in the
    property's own encoding - for PtypString that's a whole UTF-16 code unit each (4 bytes total),
    confirmed against real data where treating them as raw bytes left stray leading characters.
    `cch` itself doesn't need decoding: the prefix and normalized subject are contiguous in the
    remaining bytes, so simply dropping the 2-character marker already yields the full, correct,
    displayed subject (prefix and subject back-to-back) regardless of where the prefix ends."""
    if prop is None:
        return None
    raw = prop.value
    if prop.prop_type == PTYPE_STRING:
        if len(raw) >= 4 and struct.unpack_from("<H", raw, 0)[0] == 1:
            raw = raw[4:]
    elif len(raw) >= 2 and raw[0] == 1:
        raw = raw[2:]
    return _decode_string(PSTProperty(prop.prop_type, raw), codepage)


def _decode_time(prop: PSTProperty) -> datetime | None:
    if prop is None or len(prop.value) < 8:
        return None
    filetime = struct.unpack_from("<Q", prop.value, 0)[0]
    unix_100ns = filetime - _FILETIME_UNIX_EPOCH_DELTA
    return datetime.fromtimestamp(unix_100ns / 1e7, tz=UTC)


def _parse_transport_headers(text: str) -> dict:
    msg = Parser().parsestr(text, headersonly=True)
    return {k.lower(): v for k, v in msg.items()}


def _make_id(props: dict) -> str:
    """`outlook:<Message-ID>` when present - so a message that also exists in the Gmail account
    this PST was backed up from naturally dedupes to the same conceptual message on re-import from
    each source, matching the `gmail:`-prefixed id scheme used for Gmail-sourced rows. Falls back
    to a content hash for messages with no Internet Message-ID (not uncommon for meeting requests,
    drafts, or very old mail)."""
    codepage = _codepage(props)
    msg_id = _decode_string(props.get(PROP_INTERNET_MESSAGE_ID), codepage)
    if msg_id and msg_id.strip():
        return f"outlook:{msg_id.strip()}"
    basis_prop = props.get(PROP_TRANSPORT_HEADERS) or props.get(PROP_SUBJECT)
    basis = basis_prop.value if basis_prop else b""
    return f"outlook:sha1:{hashlib.sha1(basis).hexdigest()}"


def _extract_body(props: dict, codepage: int) -> tuple:
    """Mirrors gmail_client._extract_body_text's (text, mime_type) shape. Prefers PidTagBody
    (plain text) over PidTagHtmlBody; a message with neither - compressed-RTF-only, verified to
    occur for meeting requests in data/personal-email-backup.pst - has no body text available
    without implementing RTF decompression ([MS-OXRTFCP]), out of scope for now."""
    body_prop = props.get(PROP_BODY)
    if body_prop is not None and body_prop.value:
        return _decode_string(body_prop, codepage), "text/plain"
    html_prop = props.get(PROP_HTML_BODY)
    if html_prop is not None and html_prop.value:
        return _decode_string(html_prop, codepage), "text/html"
    return "", None


def _extract_html_body(props: dict, codepage: int) -> str | None:
    """Return PidTagHtmlBody's decoded content when present, independent of whether PidTagBody
    (plain text) also exists - mirrors gmail_client.py's _extract_body_html, so both
    representations are preserved rather than only the plain-text one _extract_body prefers."""
    html_prop = props.get(PROP_HTML_BODY)
    if html_prop is not None and html_prop.value:
        return _decode_string(html_prop, codepage)
    return None


def _format_address(name: str | None, address: str | None) -> str | None:
    name = (name or "").strip()
    address = (address or "").strip()
    if name and address:
        return f"{name} <{address}>"
    return address or name or None


# --- public API, mirroring gmail_client.py's shapes ----------------------------------------


def parse_message(raw: RawMessage, label_id: str | None = None) -> dict:
    """`label_id` is the caller's concern (see pst/tree.py's folder_label_id) - a message's PC
    doesn't know which folder it was found in, only the folder walk does."""
    props = raw.props
    codepage = _codepage(props)

    headers_text = _decode_string(props.get(PROP_TRANSPORT_HEADERS), codepage)
    headers = _parse_transport_headers(headers_text) if headers_text else {}

    submit_time = _decode_time(props.get(PROP_CLIENT_SUBMIT_TIME) or props.get(PROP_MESSAGE_DELIVERY_TIME))
    internal_date_ms = int(submit_time.timestamp() * 1000) if submit_time else None

    sender = headers.get("from") or _format_address(
        _decode_string(props.get(PROP_SENDER_NAME), codepage),
        _decode_string(props.get(PROP_SENDER_SMTP_ADDRESS), codepage),
    )
    date = headers.get("date") or (submit_time.strftime("%a, %d %b %Y %H:%M:%S %z") if submit_time else None)
    body_text, body_mime_type = _extract_body(props, codepage)
    recipient_fallback = {} if headers else _recipient_table_summary(raw.recipients)

    return {
        "id": _make_id(props),
        "thread_id": None,  # no Gmail-style threading concept surfaced here
        "sender": sender,
        "recipient": headers.get("to") or recipient_fallback.get("to"),
        "cc": headers.get("cc") or recipient_fallback.get("cc"),
        "bcc": headers.get("bcc") or recipient_fallback.get("bcc"),
        "subject": _decode_subject(props.get(PROP_SUBJECT), codepage),
        "date": date,
        "internal_date_ms": internal_date_ms,
        "snippet": None,
        "label_ids": label_id or "",
        "body_text": body_text,
        "body_mime_type": body_mime_type,
        "body_html": _extract_html_body(props, codepage),
    }


def parse_addresses(raw: RawMessage) -> list:
    props = raw.props
    codepage = _codepage(props)
    message_id = _make_id(props)

    headers_text = _decode_string(props.get(PROP_TRANSPORT_HEADERS), codepage)
    if headers_text:
        headers = _parse_transport_headers(headers_text)
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

    # No transport headers (meeting requests, drafts, ...): sender from the PC, to/cc/bcc from the
    # Recipient Table.
    rows = []
    sender_addr = _decode_string(props.get(PROP_SENDER_SMTP_ADDRESS), codepage)
    if sender_addr and "@" in sender_addr:
        sender_name = _decode_string(props.get(PROP_SENDER_NAME), codepage)
        rows.append(
            {
                "message_id": message_id,
                "role": "from",
                "address": sender_addr.strip().lower(),
                "name": (sender_name or "").strip() or None,
            }
        )

    seen = set()
    for role, addr, name in _decode_recipient_rows(raw.recipients):
        addr = addr.lower()
        if (role, addr) in seen:
            continue
        seen.add((role, addr))
        rows.append({"message_id": message_id, "role": role, "address": addr, "name": name or None})
    return rows


def _decode_recipient_rows(recipients: list) -> list:
    """Decode Recipient Table rows into (role, address, name) tuples, skipping any row with no
    usable (i.e. containing "@") address - known, empirically, to hold PtypString (UTF-16LE)
    values for the columns used here."""
    decoded = []
    for row in recipients:
        type_bytes = row.get(PROP_RECIPIENT_TYPE)
        role = RECIPIENT_TYPE_TO_ROLE.get(struct.unpack_from("<i", type_bytes, 0)[0] if type_bytes else 1, "to")
        addr_bytes = row.get(PROP_SMTP_ADDRESS) or row.get(PROP_EMAIL_ADDRESS)
        addr = addr_bytes.decode("utf-16-le", errors="replace").strip() if addr_bytes else ""
        if "@" not in addr:
            continue
        name_bytes = row.get(PROP_DISPLAY_NAME)
        name = name_bytes.decode("utf-16-le", errors="replace").strip() if name_bytes else ""
        decoded.append((role, addr, name))
    return decoded


def _recipient_table_summary(recipients: list) -> dict:
    """Build {"to": "Name <addr>, ...", "cc": ..., "bcc": ...} header-style strings from the
    Recipient Table, as a recipient/cc/bcc fallback for parse_message() when no transport headers
    are available (so its summary strings stay consistent with what parse_addresses() finds)."""
    by_role = {"to": [], "cc": [], "bcc": []}
    for role, addr, name in _decode_recipient_rows(recipients):
        formatted = _format_address(name, addr)
        if formatted:
            by_role[role].append(formatted)
    return {role: ", ".join(values) or None for role, values in by_role.items()}


def _decode_content_id(content_id_bytes: bytes | None) -> str | None:
    """PidTagAttachContentId stores the bare id (e.g. `image001@01D...`), matching the `cid:` URI
    in the HTML body - but a MIME `Content-ID` header needs it wrapped in angle brackets (RFC 5322
    msg-id syntax), same form gmail_client.py's parse_attachments already captures straight off the
    raw `Content-ID` header. Normalize here so cli.py's EML builder can treat every source's
    content_id the same way, without needing to know which source produced it."""
    if not content_id_bytes:
        return None
    value = content_id_bytes.decode("utf-16-le", errors="replace").strip()
    if not value:
        return None
    return value if value.startswith("<") else f"<{value}>"


def parse_attachments(raw: RawMessage, pst: PSTFile | None = None) -> list:
    """`pst`, when given, additionally fetches each attachment's actual bytes into a "content" key
    via `fetch_attachment_content` - a separate resolve + read per attachment, so left out (`None`)
    unless a caller actually wants content (see cli.py's `--with-attachments`)."""
    message_id = _make_id(raw.props)
    rows = []
    for row in raw.attachments:
        filename_bytes = row.get(PROP_ATTACH_LONG_FILENAME) or row.get(PROP_ATTACH_FILENAME)
        if not filename_bytes:
            continue
        mime_bytes = row.get(PROP_ATTACH_MIME_TAG)
        size_bytes = row.get(PROP_ATTACH_SIZE)
        rows.append(
            {
                "message_id": message_id,
                "attachment_id": None,  # no Gmail-style attachmentId equivalent in a PST
                "filename": filename_bytes.decode("utf-16-le", errors="replace"),
                "mime_type": mime_bytes.decode("utf-16-le", errors="replace") if mime_bytes else None,
                "size": struct.unpack_from("<i", size_bytes, 0)[0] if size_bytes else None,
                "content_id": _decode_content_id(row.get(PROP_ATTACH_CONTENT_ID)),
                "content": fetch_attachment_content(pst, raw, row) if pst is not None else None,
            }
        )
    return rows
