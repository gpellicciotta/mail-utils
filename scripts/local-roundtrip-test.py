"""Local (no network/API) round-trip fidelity test for `import-eml`, built for T0020 to prove that
`export --format eml` followed by `import-eml` reproduces the original database exactly.

Unlike `gmail-roundtrip-test.py`, pairing is by exact `id` equality: `import-eml` preserves the
original `X-Mail-Utils-ID` as the re-imported row's id, rather than minting a new one the way Gmail
necessarily does on `store-in-gmail` - so there's no need for gmail-roundtrip-test.py's fuzzy
subject+date pairing here. Attachment content is diffed as real bytes read from each database's own
attachment store (via its `content_sha256`), not just by comparing hash strings, per T0020's Approach.

Usage:
    mail-utils import-pst <path> --db data/storage/work-mail --with-attachments --recursive
    mail-utils export data/exports/work-mail-eml --format eml --db data/storage/work-mail
    mail-utils import-eml data/exports/work-mail-eml --db data/storage/work-mail-roundtrip
    python scripts/local-roundtrip-test.py compare \\
        --origin-db data/storage/work-mail/mails.db \\
        --result-db data/storage/work-mail-roundtrip/mails.db
"""

import re
import sqlite3
import sys
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path

from _cli_common import build_action_parser, get_mail_utils_version, print_help, print_version

PROG = "local-roundtrip-test"
DESCRIPTION = (
    "Compares an origin database against a result database re-imported via `import-eml`, for local "
    "(non-Gmail) round-trip fidelity - messages, addresses, and attachment byte content, paired by exact id."
)
EXIT_CODES = [
    (0, "Success / comparison found no differences"),
    (1, "Comparison found differences"),
    (2, "Invalid command-line arguments"),
]

# Compared byte-for-byte between origin and result `messages` rows. body_text/body_html are handled
# separately (see _normalize_body) because EmailMessage.get_content() always appends a trailing "\n"
# during MIME serialization on the way through import-eml - a known, accepted round-trip artifact
# (see T0020's task file), not a bug to flag here. label_ids/attachments are also handled separately
# since ids/hashes are compared by name/content, not by raw value.
EXACT_MESSAGE_FIELDS = ("thread_id", "internal_date_ms", "snippet")

# subject is compared after _normalize_header: `_build_eml_message` (cli.py) applies the same
# normalization before writing it as a real RFC 5322 header, since a raw source value can rarely
# contain a character Python's modern email policy treats as a line break (not just "\n"/"\r"
# header-folding leftovers, already unfolded at each source parser, but also rarer ones like "\x85"
# NEL - found in a real Thunderbird-sourced Subject) - which would otherwise crash export. That
# normalization is a narrow, accepted lossy transform (the character becomes a plain space), so
# comparing it raw would flag a false-positive bug on every re-run.
#
# sender/recipient/cc/bcc are compared as parsed address lists (_normalize_address_list), not as raw
# header strings: Python's modern email policy re-serializes an address list into one of several
# RFC 5322-equivalent textual forms (dropping angle brackets around a bare address with no display
# name, dropping unnecessary quoting around a plain display name, normalizing inter-item whitespace) -
# none of which is data loss, just a different valid spelling of the same address list.
#
# date is compared as a parsed datetime (_normalize_date) for the same reason: the modern policy
# always zero-pads the day-of-month and drops the optional, non-normative trailing "(TZ name)"
# comment on re-serialization.
NORMALIZED_HEADER_FIELDS = ("subject",)
NORMALIZED_ADDRESS_FIELDS = ("sender", "recipient", "cc", "bcc")


def _normalize_body(text: str | None) -> str | None:
    # Three known, accepted MIME-serialization artifacts of routing body content through
    # EmailMessage.set_content()/get_content() on the way through import-eml (see T0020's task file):
    # it always normalizes CRLF line endings to a bare "\n" internally, it appends one trailing "\n",
    # and - the same universal-newline handling responsible for the first point - it also treats a
    # bare "\r" not followed by "\n" as its own line break, same as a real "\n" would be. A source
    # body carrying that shape (found via T0020's full-scale round-trip run: real PST-extracted
    # bodies with a stray "\r" immediately before a quoted-reply "> " marker, itself a pre-existing
    # oddity of the original captured text, not something mail-utils introduced) comes back with the
    # break landing before the "\r" instead of after it - same total text, just reflowed at an
    # already-non-standard line ending, not data loss.
    if not text:
        return text
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")


def _normalize_html_body(text: str | None) -> str | None:
    """Same as _normalize_body, plus collapsing every run of whitespace (including embedded newlines)
    into a single space. A long HTML line can gain internal line breaks purely from quoted-printable
    soft-wrapping on the way through export/reimport (found via T0020's round-trip comparison against
    real archive data: an unbroken quoted-HTML line came back with newlines inserted right after each
    `<br>` tag) - not data loss, since HTML rendering already collapses whitespace/newlines between
    tags to a single space, so the visible result is identical either way. Plain-text bodies don't get
    this treatment (see _normalize_body) - a newline is semantically meaningful there."""
    normalized = _normalize_body(text)
    return re.sub(r"\s+", " ", normalized) if normalized else normalized


def _normalize_header(text: str | None) -> str | None:
    if not text:
        # An empty-string header value and an absent one are the same thing on the wire:
        # cli.py::_build_eml_message's `if subject:` guard (mirrored by the sender/recipient/cc/bcc
        # guards right next to it) omits the header entirely for "", so it always comes back None on
        # reimport - not data loss, just two equally-valid spellings of "no subject" (found via
        # T0020's full-scale round-trip run against real archive data, where an empty-string subject
        # is common enough - short informal replies - to show up as noise on every run otherwise).
        return None
    lines = text.splitlines()
    joined = " ".join(lines) if len(lines) > 1 else text
    # A leading/trailing space around a header's value is conventionally trimmed when the header is
    # unfolded/reserialized (e.g. Python's modern email policy does this for "Subject:") - cosmetic,
    # not data loss (found via T0020's round-trip comparison against real archive data). A
    # whitespace-only value strips down to "" here, same as a genuinely empty one above - without the
    # `or None`, the two would normalize to different results ("" vs None) and register as a false
    # difference on every whitespace-only-subject message (found via the same full-scale run).
    return joined.strip() or None


def _loosely_normalized_raw(text: str | None) -> str:
    """Fallback for when _normalize_address_list's getaddresses()-based parsing itself disagrees on
    two representations of the same value - it's a lenient, RFC-2822-vintage parser with its own
    quirks (e.g. a bare, unquoted multi-word display name with no address at all gets silently
    truncated at the first space: getaddresses(['Giovanni Pellicciotta']) -> [('', 'Giovanni')], while
    the quoted form parses correctly). Stripping quotes and collapsing whitespace catches those
    parser-quirk false positives without masking a real difference (an address that's actually missing
    or changed still won't match after this normalization either)."""
    if not text:
        return ""
    return " ".join(re.sub(r"\s+,", ",", text.replace('"', "")).split())


def _normalize_display_name_ws(text: str) -> str:
    """Collapse whitespace runs the way _loosely_normalized_raw does, plus a space immediately before
    a comma - real header composition/reparsing drops that specific space (see the "LCM CC ," case at
    this function's call site) even though a plain internal whitespace run elsewhere just collapses to
    one space rather than vanishing outright."""
    return " ".join(re.sub(r"\s+,", ",", text).split())


def _strip_trailing_comments(text: str) -> str:
    """Drop an RFC 5322 comment - `(...)`  trailing an address, e.g. a real Thunderbird-sourced
    "tim.vanholder@anubex.com (Cron Daemon)" - before parsing. getaddresses() treats the parenthesized
    text as if it were a display name, but the modern email policy used by import-eml treats it as a
    genuinely discardable comment and drops it - both are defensible readings of an ambiguous
    construct, and the address itself (the actual data) is unaffected either way, so comments are
    ignored on both sides rather than flagged as a difference (found via T0020's round-trip
    comparison).

    Only applied when the text contains no quote character at all: a real quoted display name can
    legitimately contain parentheses as part of its actual content (found against the real dataset:
    a quoted name like "'Hansen, Lars (TS CD)'" got its "(TS CD)" wrongly stripped as if it were a
    trailing comment, corrupting the comparison for messages that never had a comment in the first
    place - getaddresses() already unescapes/parses a quoted name's parentheses correctly on its own,
    so nothing needs stripping there)."""
    if '"' in text:
        return text
    return re.sub(r"\s*\([^()]*\)", "", text)


def _normalize_address_list(text: str | None) -> list:
    if not text:
        return []
    text = _strip_trailing_comments(_normalize_header(text))
    # getaddresses() does not itself strip RFC 5322 quoted-string quoting from a local-part - see
    # _normalize_address for why that quoting is a cosmetic, expected round-trip artifact here.
    return sorted((name.strip(), _normalize_address(addr.strip().lower())) for name, addr in getaddresses([text]))


def _normalize_date(text: str | None):
    if not text:
        return None
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return text


def _load_db(db_path: Path) -> dict:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    label_name_by_id = dict(conn.execute("SELECT id, name FROM labels"))
    # Deliberately excludes body_text/body_html - a full mailbox's worth of both, held for both the
    # origin and result database at once, is gigabytes for a real archive (found via T0020's full-scale
    # round trip against a 187k-message mailbox: the same shape of MemoryError as _run_export's
    # `.fetchall()` bug in cli.py, except worse here since two full databases are loaded
    # simultaneously). _compare_databases fetches each pair's body content on demand instead, via
    # _fetch_body, since `id` is the messages table's primary key so a per-id lookup is cheap.
    messages = {
        row["id"]: dict(row)
        for row in conn.execute(
            "SELECT id, thread_id, sender, recipient, cc, bcc, subject, date, internal_date_ms, "
            "snippet, label_ids, body_mime_type FROM messages"
        )
    }
    attachments = {}
    for row in conn.execute(
        "SELECT message_id, filename, mime_type, size, content_sha256, content_id FROM attachments "
        "ORDER BY message_id, filename, content_id"
    ):
        attachments.setdefault(row["message_id"], []).append(
            (row["filename"], row["mime_type"], row["size"], row["content_sha256"], row["content_id"])
        )
    addresses = {}
    for row in conn.execute("SELECT message_id, role, address, name FROM message_addresses"):
        addresses.setdefault(row["message_id"], set()).add((row["role"], row["address"], row["name"]))
    conn.close()
    return {"messages": messages, "labels": label_name_by_id, "attachments": attachments, "addresses": addresses}


def _label_names(db: dict, msg_id: str) -> set:
    row = db["messages"][msg_id]
    ids = row["label_ids"].split(",") if row["label_ids"] else []
    return {db["labels"].get(i, i) for i in ids}


def _fetch_body(conn: sqlite3.Connection, msg_id: str) -> tuple[str | None, str | None]:
    """On-demand counterpart to `_load_db` excluding body_text/body_html from its eager load - `id` is
    the messages table's primary key, so this is an indexed single-row lookup, not a table scan."""
    row = conn.execute("SELECT body_text, body_html FROM messages WHERE id = ?", (msg_id,)).fetchone()
    return (row[0], row[1]) if row else (None, None)


def _normalize_address(addr: str) -> str:
    """Strip RFC 5322 quoted-string quoting around a local-part, if present. A local-part containing
    characters the RFC requires quoting (spaces, most punctuation, non-ASCII) is captured unquoted
    from PST/Thunderbird sources (raw MAPI/header text, never real RFC 5322 syntax to begin with),
    but always comes back correctly quoted once real header text is composed and reparsed through the
    modern email policy on export/reimport - same address, just with the quoting the origin should
    have had all along (found via T0020's full-scale round-trip comparison - by far the largest
    single category of flagged differences - and confirmed accepted, not data loss, per the user's
    own direction on this task)."""
    local, sep, domain = addr.rpartition("@")
    if not sep:
        return addr
    if len(local) >= 2 and local[0] == '"' and local[-1] == '"':
        local = local[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return f"{local}@{domain}"


def _read_attachment(attachments_dir: Path, sha256: str) -> bytes | None:
    path = attachments_dir / sha256
    return path.read_bytes() if path.exists() else None


def _compare_attachments(origin_dir: Path, result_dir: Path, o_list: list, r_list: list, label: str) -> list[str]:
    """Pairs attachments within one message by (filename, content_id) - their identity within the
    message, independent of the storage-layer hash - then diffs actual bytes read from each
    database's own attachment store rather than trusting that equal content_sha256 strings imply
    equal content."""
    problems = []

    def key(a):
        # A trailing/leading space in a captured filename (e.g. a real PST PidTagAttachLongFilename
        # value) doesn't survive being embedded into a Content-Disposition "filename=" parameter and
        # read back on reimport - cosmetic, not data loss, so pairing strips it too rather than treating
        # the same attachment as two different ones (found via T0020's round-trip comparison).
        return ((a[0] or "").strip(), a[4])

    o_by_key, r_by_key = {}, {}
    for a in o_list:
        o_by_key.setdefault(key(a), []).append(a)
    for a in r_list:
        r_by_key.setdefault(key(a), []).append(a)

    for k in sorted(set(o_by_key) | set(r_by_key), key=lambda k: (k[0] or "", k[1] or "")):
        o_group, r_group = o_by_key.get(k, []), r_by_key.get(k, [])
        if len(o_group) != len(r_group):
            problems.append(
                f"{label}: attachment count differs for filename={k[0]!r} content_id={k[1]!r}: "
                f"origin={len(o_group)} result={len(r_group)}"
            )
            continue
        for o, r in zip(o_group, r_group):
            _, o_mime, o_size, o_sha, _ = o
            _, r_mime, r_size, r_sha, _ = r
            # `_build_eml_message` (cli.py) writes every attachment part under "application/
            # octet-stream" unless the captured mime_type is one of the confirmed-lossless maintypes
            # (image/audio/video/application) - anything else, "text/*" included, gets decoded as a
            # string by Python's email content manager before being re-encoded, silently corrupting
            # any byte sequence that isn't valid under whatever charset it guesses (see
            # cli._lossless_attachment_type). So mime_type "downgrading" to octet-stream is an
            # accepted, deliberate round-trip transformation, not a bug: only flag it when the origin
            # mime_type was already one of the lossless maintypes and still doesn't match.
            o_maintype = (o_mime or "").split("/", 1)[0]
            if o_maintype in ("image", "audio", "video", "application") and o_mime != r_mime:
                problems.append(f"{label}: attachment {k[0]!r} mime_type differs: {o_mime!r} != {r_mime!r}")
            if o_size != r_size:
                problems.append(f"{label}: attachment {k[0]!r} size differs: {o_size!r} != {r_size!r}")
            if (o_sha is None) != (r_sha is None):
                problems.append(f"{label}: attachment {k[0]!r} content capture differs: origin_sha={o_sha!r} result_sha={r_sha!r}")
                continue
            if o_sha is None:
                continue
            o_bytes = _read_attachment(origin_dir, o_sha)
            r_bytes = _read_attachment(result_dir, r_sha)
            if o_bytes is None:
                problems.append(f"{label}: attachment {k[0]!r} origin store missing file for hash {o_sha}")
            if r_bytes is None:
                problems.append(f"{label}: attachment {k[0]!r} result store missing file for hash {r_sha}")
            if o_bytes is not None and r_bytes is not None and o_bytes != r_bytes:
                problems.append(
                    f"{label}: attachment {k[0]!r} byte content differs "
                    f"(origin_sha={o_sha}, result_sha={r_sha}, {len(o_bytes)}B vs {len(r_bytes)}B)"
                )
    return problems


def _compare_databases(
    origin: dict,
    result: dict,
    origin_atts_dir: Path,
    result_atts_dir: Path,
    origin_conn: sqlite3.Connection,
    result_conn: sqlite3.Connection,
) -> list[str]:
    problems = []
    origin_ids, result_ids = set(origin["messages"]), set(result["messages"])

    for mid in sorted(origin_ids - result_ids):
        problems.append(f"Origin message {mid!r} ({origin['messages'][mid]['subject']!r}) missing from result.")
    for mid in sorted(result_ids - origin_ids):
        problems.append(f"Result message {mid!r} ({result['messages'][mid]['subject']!r}) not present in origin.")

    for mid in sorted(origin_ids & result_ids):
        o, r = origin["messages"][mid], result["messages"][mid]
        label = f"{mid} ({o['subject']!r})"
        for field in EXACT_MESSAGE_FIELDS:
            if o[field] != r[field]:
                problems.append(f"{label}: {field} differs: {o[field]!r} != {r[field]!r}")
        for field in NORMALIZED_HEADER_FIELDS:
            if _normalize_header(o[field]) != _normalize_header(r[field]):
                problems.append(f"{label}: {field} differs: {o[field]!r} != {r[field]!r}")
        for field in NORMALIZED_ADDRESS_FIELDS:
            # A field with no "@" anywhere on either side was never a real, routable address to begin
            # with - a bare display-name fragment with no captured SMTP address (e.g. a PST sender with
            # an empty PidTagSenderSmtpAddress). getaddresses() truncation of a bare multi-word name is
            # inherently parser-context-dependent (differs between the origin capture's raw header text
            # and the same text after round-tripping through the modern email policy), so exact string
            # parity here isn't meaningful data fidelity - matches the same exclusion already applied to
            # message_addresses rows below (found via T0020's round-trip comparison against real data).
            if "@" not in (o[field] or "") and "@" not in (r[field] or ""):
                continue
            if _normalize_address_list(o[field]) != _normalize_address_list(r[field]) and _loosely_normalized_raw(
                o[field]
            ) != _loosely_normalized_raw(r[field]):
                problems.append(f"{label}: {field} differs: {o[field]!r} != {r[field]!r}")
        if _normalize_date(o["date"]) != _normalize_date(r["date"]):
            problems.append(f"{label}: date differs: {o['date']!r} != {r['date']!r}")
        o_body_text, o_body_html = _fetch_body(origin_conn, mid)
        r_body_text, r_body_html = _fetch_body(result_conn, mid)
        # A message with no captured body at all (compressed-RTF-only, no PidTagBody/PidTagHtmlBody -
        # documented, accepted limitation, see T0020's task file) has body_mime_type=None and empty
        # body_text/body_html on origin. Since a valid MIME message must always carry some body part,
        # _build_eml_message writes an empty text/plain body for it - reimport reads that back as
        # body_mime_type="text/plain", not the original None. Not real data loss (there was no body to
        # lose), so only flag when origin's body wasn't already empty.
        if o["body_mime_type"] != r["body_mime_type"] and not (o["body_mime_type"] is None and not _normalize_body(o_body_text)):
            problems.append(f"{label}: body_mime_type differs: {o['body_mime_type']!r} != {r['body_mime_type']!r}")
        if _normalize_body(o_body_text) != _normalize_body(r_body_text):
            problems.append(f"{label}: body_text differs (beyond expected trailing newline)")
        # A source parser's own extract_body/extract_html_body pair can disagree on whether a given
        # MIME structure counts as "the html body" - one real Thunderbird message had
        # body_mime_type="text/html" with the markup captured into body_text (extract_body's
        # documented html-only fallback) but body_html left None (extract_html_body missed the same
        # part). _build_eml_message writes a single text/html part for that shape, and
        # _extract_eml_body then populates *both* body_text and body_html from it on reimport - not
        # data loss, just the reimported side ending up more complete than the origin's own
        # inconsistent capture (found via T0020's round-trip comparison), so this specific shape
        # (origin body_html empty, origin body_mime_type "text/html") is accepted rather than flagged.
        if _normalize_html_body(o_body_html) != _normalize_html_body(r_body_html) and not (
            not _normalize_body(o_body_html) and o["body_mime_type"] == "text/html"
        ):
            problems.append(f"{label}: body_html differs (beyond expected trailing newline/whitespace)")

        o_labels, r_labels = _label_names(origin, mid), _label_names(result, mid)
        if o_labels != r_labels:
            problems.append(f"{label}: labels differ: origin={sorted(o_labels)} result={sorted(r_labels)}")

        o_addrs = origin["addresses"].get(mid, set())
        r_addrs = result["addresses"].get(mid, set())
        # A row whose "address" has no "@" at all was never a real, routable email address to begin
        # with - a bare, malformed contact fragment (e.g. a display name with no captured SMTP address,
        # or a truncated fragment left after getaddresses() gives up on genuinely broken input). Its
        # exact spelling is inherently parser-dependent and not comparable data: getaddresses() can
        # truncate a bare multi-word name at the first space in one context and not another (e.g. "'taix
        # ramonell" -> "'taix" from the origin capture's own raw header text, vs the full name surviving
        # once the same text has round-tripped through the modern email policy's own address
        # reconstruction) - found via T0020's round-trip comparison against real archive data. Since
        # there was never a usable address here on either side, these rows are excluded from comparison
        # entirely rather than chasing exact-string parity on already-broken source data.
        o_addrs = {(role, _normalize_address(addr), name) for role, addr, name in o_addrs if "@" in addr}
        r_addrs = {(role, _normalize_address(addr), name) for role, addr, name in r_addrs if "@" in addr}
        extra_in_result = r_addrs - o_addrs
        missing_from_result = o_addrs - r_addrs
        # A trailing RFC 5322 comment on an address (e.g. "tim.vanholder@anubex.com (Cron Daemon)") is
        # ambiguous, non-semantic data (see _strip_trailing_comments above): getaddresses() treats it
        # as a display name at capture time, but the modern email policy drops it as a genuine comment
        # on reimport, so the row survives under the same (role, address) with name=None instead of
        # the comment text. Not a real difference - pair a missing/extra row up by (role, address) and
        # only actually flag it when both sides have a *name* and they disagree, or the row has no
        # counterpart on the other side at all (found via T0020's round-trip comparison).
        o_names_by_key = {(row[0], row[1]): row[2] for row in missing_from_result}
        r_names_by_key = {(row[0], row[1]): row[2] for row in extra_in_result}
        for key, o_name in list(o_names_by_key.items()):
            if key in r_names_by_key:
                r_name = r_names_by_key[key]
                # A name embedding folding whitespace (e.g. a real "Francis\tANDRE", the tab left over
                # from unfolding a header that wrapped mid-name) collapses to plain spaces once
                # reserialized through the modern email policy on reimport - cosmetic, not data loss.
                # A space immediately before a comma (e.g. a real "LCM CC ,\t Nancy Van Dyck", a comma-
                # display-name pair `quote_unquoted_comma_display_names` quotes as one combined name)
                # is dropped the same way - RFC 5322 FWS around punctuation inside a quoted-string
                # doesn't survive a real compose/reparse cycle verbatim, same words either way (found
                # via T0020's full-scale round-trip comparison, the largest remaining category after
                # the paren-quoting fix above).
                if o_name is None or r_name is None or _normalize_display_name_ws(o_name) == _normalize_display_name_ws(r_name):
                    missing_from_result.discard((key[0], key[1], o_name))
                    extra_in_result.discard((key[0], key[1], r_name))
        if extra_in_result or missing_from_result:
            problems.append(f"{label}: message_addresses differ:\n  origin: {sorted(o_addrs)}\n  result: {sorted(r_addrs)}")

        o_atts, r_atts = origin["attachments"].get(mid, []), result["attachments"].get(mid, [])
        problems.extend(_compare_attachments(origin_atts_dir, result_atts_dir, o_atts, r_atts, label))

    return problems


def _run_compare(args) -> int:
    origin_db_path = Path(args.origin_db)
    result_db_path = Path(args.result_db)
    origin_atts_dir = Path(args.origin_attachments) if args.origin_attachments else origin_db_path.parent / "attachments"
    result_atts_dir = Path(args.result_attachments) if args.result_attachments else result_db_path.parent / "attachments"

    origin = _load_db(origin_db_path)
    result = _load_db(result_db_path)
    print(f"Origin database: {len(origin['messages'])} messages. Result database: {len(result['messages'])} messages.")

    origin_conn = sqlite3.connect(str(origin_db_path))
    result_conn = sqlite3.connect(str(result_db_path))
    try:
        problems = _compare_databases(origin, result, origin_atts_dir, result_atts_dir, origin_conn, result_conn)
    finally:
        origin_conn.close()
        result_conn.close()
    if not problems:
        print(f"PASS: {len(origin['messages'])} messages compared, no differences found.")
        return 0

    print(f"FAIL: {len(problems)} problem(s) found:")
    for p in problems:
        print(f"  - {p}")
    return 1


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    version = get_mail_utils_version()
    parser = build_action_parser(PROG, DESCRIPTION, ["compare", "version", "help"], "help")
    parser.add_argument("--origin-db", help="Origin database path (compare)")
    parser.add_argument(
        "--origin-attachments", help="Origin attachments directory (compare) - defaults to <origin-db-dir>/attachments"
    )
    parser.add_argument("--result-db", help="Result database path, re-imported via import-eml (compare)")
    parser.add_argument(
        "--result-attachments", help="Result attachments directory (compare) - defaults to <result-db-dir>/attachments"
    )
    args = parser.parse_args()

    if args.version or args.action == "version":
        print_version(PROG, version)
        return 0
    if args.help or args.action == "help":
        print_help(PROG, version, DESCRIPTION, parser, EXIT_CODES)
        return 0

    if args.action == "compare":
        missing = [name for name in ("origin_db", "result_db") if not getattr(args, name)]
        if missing:
            print(f"compare requires: {', '.join('--' + m.replace('_', '-') for m in missing)}", file=sys.stderr)
            return 2
        return _run_compare(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
