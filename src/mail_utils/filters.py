import shlex
from datetime import datetime, timezone

KNOWN_KEYS = {"label", "from", "to", "cc", "bcc", "subject", "after", "before", "has"}


class FilterError(ValueError):
    """A --filter string used unrecognized syntax."""


def parse_filter(text: str) -> list:
    """Parse a Gmail-like filter string into a list of (key, value) pairs.

    key is one of KNOWN_KEYS, or "*" for a bare word/phrase (matched
    against subject + body). Quoted phrases ("multi word") are one token,
    whether bare or attached to a key (subject:"multi word").

    Raises FilterError on an unrecognized `key:` prefix, rather than
    silently ignoring it - a filter that matches nothing should never
    look identical to one that matches everything.
    """
    tokens = []
    for word in shlex.split(text):
        key, sep, value = word.partition(":")
        if sep and key.lower() in KNOWN_KEYS:
            tokens.append((key.lower(), value))
        elif sep and key.lower() not in KNOWN_KEYS:
            raise FilterError(f"Unrecognized filter keyword '{key}:' in {word!r}")
        else:
            tokens.append(("*", word))
    return tokens


def _parse_gmail_date(value: str) -> int:
    """Parse a Gmail-style YYYY/MM/DD date into epoch ms at UTC midnight."""
    try:
        dt = datetime.strptime(value, "%Y/%m/%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise FilterError(f"Invalid date {value!r} for after:/before: - expected YYYY/MM/DD")
    return int(dt.timestamp() * 1000)


def message_matches(
    tokens: list,
    *,
    labels: list,
    addresses,
    has_attachment: bool,
    internal_date_ms,
    subject,
    body_text,
) -> bool:
    """Return True if a message matches every token (AND semantics).

    labels: resolved label names for this message.
    addresses: dict of role ("from"/"to"/"cc"/"bcc") -> list of
        (address, name) tuples for this message.
    """
    subject_l = (subject or "").lower()
    body_l = (body_text or "").lower()
    label_names_l = [name.lower() for name in labels]

    for key, value in tokens:
        value_l = value.lower()

        if key == "*":
            if value_l not in subject_l and value_l not in body_l:
                return False

        elif key == "subject":
            if value_l not in subject_l:
                return False

        elif key == "label":
            if not any(value_l in name for name in label_names_l):
                return False

        elif key in ("from", "to", "cc", "bcc"):
            role_addresses = addresses.get(key, [])
            if not any(value_l in (addr or "").lower() or value_l in (name or "").lower() for addr, name in role_addresses):
                return False

        elif key == "after":
            boundary = _parse_gmail_date(value)
            if not internal_date_ms or internal_date_ms < boundary:
                return False

        elif key == "before":
            boundary = _parse_gmail_date(value)
            if not internal_date_ms or internal_date_ms >= boundary:
                return False

        elif key == "has":
            if value_l != "attachment":
                raise FilterError(f"Unsupported has: value {value!r} - only has:attachment is supported")
            if not has_attachment:
                return False

    return True
