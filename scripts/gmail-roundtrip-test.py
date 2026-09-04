"""Round-trip fidelity test for `store-in-gmail`, run against a disposable Gmail account (see
tasks/T0013-gmail-e2e-safety-and-rollout.md). Independent of mail_utils's own message-construction
code (`cli.py::_build_eml_message`) wherever it matters for the test's validity - only the generic
auth/transport plumbing (`auth.get_credentials`, `gmail_client.build_gmail_service`) is reused.

Workflow this script supports (the actual import-gmail/store-in-gmail/export calls are run directly
via `mail-utils`, not by this script - it only seeds, compares, and cleans up). Set up the test
account once via `mail-utils prepare-gmail-account <name> --with-write`, then:

    python scripts/gmail-roundtrip-test.py seed --account <name> --to <name>@example-domain.com
    mail-utils import-gmail --with-attachments --account <name> --db data/origin --filter "label:mail-utils-roundtrip-test-source"
    mail-utils export data/origin-export --format eml --db data/origin
    mail-utils store-in-gmail --account <name> --db data/origin
    mail-utils import-gmail --with-attachments --account <name> --db data/result --filter "label:<the new store-in-gmail tracking label>"
    mail-utils export data/result-export --format eml --db data/result
    python scripts/gmail-roundtrip-test.py compare --origin-db data/origin/mails.db --origin-export data/origin-export --result-db data/result/mails.db --result-export data/result-export
    python scripts/gmail-roundtrip-test.py cleanup --account <name> --label mail-utils-roundtrip-test-source --apply
    python scripts/gmail-roundtrip-test.py cleanup --account <name> --label <the tracking label> --apply

`cleanup --apply` trashes every message carrying the given label, then deletes the label itself - a
disposable test run leaves nothing behind, not even an empty label in the sidebar. Safe to rerun even
after messages are already trashed (which excludes them from the default listing) since deleting the
label doesn't depend on finding any.

`compare` deliberately does not diff exported .eml files as raw bytes: Python's email library embeds
a randomly generated MIME boundary every time a multipart message is serialized, so two semantically
identical messages produce different bytes on that basis alone. Instead it parses both files and
compares decoded content (subject/addresses/body text/attachment bytes+filenames/labels).
"""

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from email.message import EmailMessage
from email.policy import default as email_policy_default
from email.utils import format_datetime
from pathlib import Path

from _cli_common import build_action_parser, get_mail_utils_version, print_help, print_version

from mail_utils.auth import get_credentials
from mail_utils.config import STORE_IN_GMAIL_SCOPES, resolve_account_path
from mail_utils.gmail_client import build_gmail_service, create_label, delete_label, get_profile, import_message, list_labels

PROG = "gmail-roundtrip-test"
DESCRIPTION = (
    "Seeds varied test messages into a disposable Gmail account, compares an origin/result database and "
    "export directory pair for store-in-gmail round-trip fidelity, and cleans up labeled test messages."
)
EXIT_CODES = [
    (0, "Success / comparison found no differences"),
    (1, "Comparison found differences, or the requested operation failed"),
    (2, "Invalid command-line arguments"),
]
SEED_LABEL = "mail-utils-roundtrip-test-source"
SUBJECT_PREFIX = "[mail-utils roundtrip test] "
# cleanup's trash operation needs gmail.modify - not part of STORE_IN_GMAIL_SCOPES, since store-in-gmail
# itself never trashes or modifies anything. Requested only here, only for the cleanup action. Permanent
# delete would need the far broader "https://mail.google.com/" scope, so this script deliberately only
# supports moving to Trash, never permanent deletion.
CLEANUP_SCOPES = [*STORE_IN_GMAIL_SCOPES, "https://www.googleapis.com/auth/gmail.modify"]


def _service(account: str | None, scopes=STORE_IN_GMAIL_SCOPES):
    account_path = resolve_account_path(account)
    creds = get_credentials(account_path, scopes=scopes)
    service = build_gmail_service(creds)
    print(f"Target account: {get_profile(service).get('emailAddress')}")
    return service


def _seed_messages(to_address: str) -> list[EmailMessage]:
    base = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    messages = []

    m1 = EmailMessage()
    m1["Subject"] = f"{SUBJECT_PREFIX}plain text, no attachment"
    m1["From"] = "roundtrip-sender@example.com"
    m1["To"] = to_address
    m1["Date"] = format_datetime(base)
    m1.set_content("Just a plain text body, nothing fancy.\n")
    messages.append(m1)

    m2 = EmailMessage()
    m2["Subject"] = f"{SUBJECT_PREFIX}plain text with one PNG attachment"
    m2["From"] = "roundtrip-sender@example.com"
    m2["To"] = to_address
    m2["Date"] = format_datetime(base + timedelta(hours=1))
    m2.set_content("See the attached tiny PNG.\n")
    smallest_png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
        "53de0000000c4944415408d763f8cfc0c00000030101007e5ac1550000000049454e44ae426082"
    )
    m2.add_attachment(smallest_png, maintype="image", subtype="png", filename="pixel.png")
    messages.append(m2)

    m3 = EmailMessage()
    m3["Subject"] = f"{SUBJECT_PREFIX}HTML body, unicode: Café ☕ 日本語"
    m3["From"] = "roundtrip-sender@example.com"
    m3["To"] = to_address
    m3["Date"] = format_datetime(base + timedelta(hours=2))
    m3.set_content(
        "<html><body><p>HTML body with unicode: café, ☕, 日本語.</p></body></html>\n",
        subtype="html",
    )
    messages.append(m3)

    m4 = EmailMessage()
    m4["Subject"] = f"{SUBJECT_PREFIX}two attachments, unicode subject: 日本語のテスト"
    m4["From"] = "roundtrip-sender@example.com"
    m4["To"] = to_address
    m4["Date"] = format_datetime(base + timedelta(hours=3))
    m4.set_content("Two attachments below: a text file and a binary file.\n")
    m4.add_attachment(
        "Plain text attachment content, with unicode: éèà.\n".encode(),
        maintype="text",
        subtype="plain",
        filename="note.txt",
    )
    m4.add_attachment(bytes(range(256)) * 4, maintype="application", subtype="octet-stream", filename="data.bin")
    messages.append(m4)

    m5 = EmailMessage()
    m5["Subject"] = f"{SUBJECT_PREFIX}one larger binary attachment"
    m5["From"] = "roundtrip-sender@example.com"
    m5["To"] = to_address
    m5["Date"] = format_datetime(base + timedelta(hours=4))
    m5.set_content("One larger (~256KB) attachment below, to exercise more than a trivial payload size.\n")
    large_payload = (bytes(range(256)) * 1024)[:262144]
    m5.add_attachment(large_payload, maintype="application", subtype="octet-stream", filename="large.bin")
    messages.append(m5)

    m6 = EmailMessage()
    m6["Subject"] = f"{SUBJECT_PREFIX}HTML body with inline image"
    m6["From"] = "roundtrip-sender@example.com"
    m6["To"] = to_address
    m6["Date"] = format_datetime(base + timedelta(hours=5))
    m6.set_content("Plain-text fallback: see the logo image below.\n")
    inline_cid = "roundtrip-inline-logo@example.com"
    m6.add_alternative(
        f'<html><body><p>Formatted body with an inline image:</p><img src="cid:{inline_cid}"></body></html>\n',
        subtype="html",
    )
    smallest_png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
        "53de0000000c4944415408d763f8cfc0c00000030101007e5ac1550000000049454e44ae426082"
    )
    # Real-world inline images (Outlook, Gmail compose) carry a filename even though disposition is
    # inline - matching that here matters because gmail_client.py's parse_attachments only captures a
    # MIME part that has one; a filename-less inline part is invisible to it, same as any other
    # attachment (a separate, pre-existing gap - see TODO.md).
    # disposition="inline" is passed explicitly - add_related() defaults to inline disposition only
    # when no filename is given; passing both filename and cid (matching how real mail clients embed
    # inline images) otherwise silently reverts EmailMessage's default to "attachment" (verified
    # empirically), which would defeat the point of this seed message.
    m6.get_payload()[1].add_related(
        smallest_png, maintype="image", subtype="png", filename="logo.png", cid=f"<{inline_cid}>", disposition="inline"
    )
    messages.append(m6)

    m7 = EmailMessage()
    m7["Subject"] = f"{SUBJECT_PREFIX}display name with unquoted at symbol"
    m7["From"] = '"John @ Work" <roundtrip-sender@example.com>'
    m7["To"] = to_address
    m7["Date"] = format_datetime(base + timedelta(hours=6))
    m7.set_content("Testing display name containing an '@' character.\n")
    messages.append(m7)

    m8 = EmailMessage()
    m8["Subject"] = f"{SUBJECT_PREFIX}display name with unquoted comma"
    m8["From"] = '"Smith, Jane" <roundtrip-sender@example.com>'
    m8["To"] = to_address
    m8["Date"] = format_datetime(base + timedelta(hours=7))
    m8.set_content("Testing display name formatted as Last, First.\n")
    messages.append(m8)

    m9 = EmailMessage()
    m9["Subject"] = f"{SUBJECT_PREFIX}display name with bracket annotations"
    m9["From"] = '"Alice [Contractor]" <roundtrip-sender@example.com>'
    m9["To"] = to_address
    m9["Date"] = format_datetime(base + timedelta(hours=8))
    m9.set_content("Testing display name with bracket annotation.\n")
    messages.append(m9)

    m10 = EmailMessage()
    m10["Subject"] = f"{SUBJECT_PREFIX}Windows-1252 encoded text attachment"
    m10["From"] = "roundtrip-sender@example.com"
    m10["To"] = to_address
    m10["Date"] = format_datetime(base + timedelta(hours=9))
    m10.set_content("Testing non-UTF-8 Windows-1252 text attachment preservation.\n")
    # Windows-1252 bytes: 0x93 (left double quote), 0x94 (right double quote), 0x80 (euro symbol)
    win1252_bytes = b"\x93Windows-1252 Special text\x94 with \x80 symbol.\r\n"
    m10.add_attachment(win1252_bytes, maintype="text", subtype="plain", filename="win1252.txt")
    messages.append(m10)

    m11 = EmailMessage()
    m11["Subject"] = f"{SUBJECT_PREFIX}attachment filename with special characters"
    m11["From"] = "roundtrip-sender@example.com"
    m11["To"] = to_address
    m11["Date"] = format_datetime(base + timedelta(hours=10))
    m11.set_content("Testing attachment filename containing colons and special characters.\n")
    m11.add_attachment(b"PDF document simulation bytes", maintype="application", subtype="pdf", filename="RE: Offer: Report.pdf")
    messages.append(m11)

    m12 = EmailMessage()
    m12["Subject"] = f"{SUBJECT_PREFIX}multipart alternative with rich plain and HTML"
    m12["From"] = "roundtrip-sender@example.com"
    m12["To"] = to_address
    m12["Date"] = format_datetime(base + timedelta(hours=11))
    m12.set_content("Plain text body alternative.\n")
    m12.add_alternative("<html><body><h2>Rich HTML Body</h2><p>Paragraph content.</p></body></html>\n", subtype="html")
    messages.append(m12)

    return messages


def _run_seed(args) -> int:
    service = _service(args.account)
    label_names = {lbl["name"]: lbl["id"] for lbl in list_labels(service)}
    label_id = label_names.get(SEED_LABEL) or create_label(service, SEED_LABEL)["id"]

    for msg in _seed_messages(args.to):
        result = import_message(service, msg.as_bytes(), label_ids=[label_id])
        print(f"Seeded: {msg['Subject']!r} -> {result.get('id')}")

    print(f"Done. All seeded messages carry the '{SEED_LABEL}' label.")
    return 0


def _run_cleanup(args) -> int:
    """Trash every message carrying `args.label`, then delete the label itself - deleting a Gmail
    label only removes the label from whatever messages had it (trashed or not), it never touches the
    messages, so this is safe to do unconditionally once trashing is done. Also runs when 0 messages
    currently carry the label (e.g. a prior --apply already trashed them all, which excludes them from
    this listing by default) - otherwise a rerun would report "nothing to do" and leave the now-empty
    label sitting in the mailbox forever, which is exactly the gap this was written to close."""
    service = _service(args.account, CLEANUP_SCOPES)
    label_names = {lbl["name"]: lbl["id"] for lbl in list_labels(service)}
    label_id = label_names.get(args.label)
    if label_id is None:
        print(f"No label named '{args.label}' exists in this mailbox. Nothing to do.")
        return 0

    msg_ids = []
    page_token = None
    while True:
        resp = service.users().messages().list(userId="me", labelIds=[label_id], pageToken=page_token).execute()
        msg_ids.extend(m["id"] for m in resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    print(f"{len(msg_ids)} messages carry label '{args.label}'.")
    if not args.apply:
        print("Dry run only - re-run with --apply to actually move them to Trash and delete the label.")
        return 0

    if msg_ids:
        for msg_id in msg_ids:
            service.users().messages().trash(userId="me", id=msg_id).execute()
        print(f"Trashed {len(msg_ids)} messages.")

    delete_label(service, label_id)
    print(f"Deleted label '{args.label}'.")
    return 0


def _load_db(db_path: Path) -> dict:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    label_name_by_id = dict(conn.execute("SELECT id, name FROM labels"))
    messages = {row["id"]: dict(row) for row in conn.execute("SELECT * FROM messages")}
    attachments = {}
    for row in conn.execute(
        "SELECT message_id, filename, mime_type, size, content_sha256, content_id FROM attachments ORDER BY message_id"
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


def _pair_by_subject_and_date(origin: dict, result: dict) -> tuple[list, list, list]:
    def key(row):
        return (row["subject"], row["date"])

    origin_by_key = {}
    for msg_id, row in origin["messages"].items():
        origin_by_key.setdefault(key(row), []).append(msg_id)
    result_by_key = {}
    for msg_id, row in result["messages"].items():
        result_by_key.setdefault(key(row), []).append(msg_id)

    pairs, unmatched_origin, unmatched_result = [], [], []
    for k, origin_ids in origin_by_key.items():
        result_ids = result_by_key.pop(k, [])
        if len(origin_ids) != 1 or len(result_ids) != 1:
            unmatched_origin.extend(origin_ids)
            unmatched_result.extend(result_ids)
            continue
        pairs.append((origin_ids[0], result_ids[0]))
    for remaining in result_by_key.values():
        unmatched_result.extend(remaining)
    return pairs, unmatched_origin, unmatched_result


def _compare_databases(origin: dict, result: dict) -> list[str]:
    problems = []
    pairs, unmatched_origin, unmatched_result = _pair_by_subject_and_date(origin, result)

    for msg_id in unmatched_origin:
        problems.append(f"Origin message {msg_id!r} ({origin['messages'][msg_id]['subject']!r}) has no unique match in result.")
    for msg_id in unmatched_result:
        problems.append(f"Result message {msg_id!r} ({result['messages'][msg_id]['subject']!r}) has no unique match in origin.")

    exact_fields = ("sender", "recipient", "cc", "bcc", "body_text", "body_mime_type", "body_html", "internal_date_ms")
    for origin_id, result_id in pairs:
        o, r = origin["messages"][origin_id], result["messages"][result_id]
        label = f"{o['subject']!r} ({origin_id} -> {result_id})"
        for field in exact_fields:
            if o[field] != r[field]:
                problems.append(f"{label}: {field} differs: {o[field]!r} != {r[field]!r}")

        o_labels, r_labels = _label_names(origin, origin_id), _label_names(result, result_id)
        extra = r_labels - o_labels
        missing = o_labels - r_labels
        if missing:
            problems.append(f"{label}: result is missing labels {sorted(missing)}")
        if len(extra) != 1 or not next(iter(extra)).startswith("mail-utils-store-in-gmail-"):
            problems.append(f"{label}: unexpected label difference, extra={sorted(extra)}")

        o_atts = sorted(origin["attachments"].get(origin_id, []))
        r_atts = sorted(result["attachments"].get(result_id, []))
        if len(o_atts) != len(r_atts):
            problems.append(f"{label}: attachment count differs: {len(o_atts)} != {len(r_atts)}")
        else:
            o_summary = sorted(((fn or "").strip(), sz, sha, cid) for fn, _, sz, sha, cid in o_atts)
            r_summary = sorted(((fn or "").strip(), sz, sha, cid) for fn, _, sz, sha, cid in r_atts)
            if o_summary != r_summary:
                problems.append(f"{label}: attachments differ:\n  origin: {o_atts}\n  result: {r_atts}")
        if any(sha is None for _, _, _, sha, _ in o_atts):
            problems.append(f"{label}: origin has an attachment with no captured content (missing --with-attachments?)")

        o_addrs = origin["addresses"].get(origin_id, set())
        r_addrs = result["addresses"].get(result_id, set())
        if o_addrs != r_addrs:
            problems.append(f"{label}: message_addresses differ:\n  origin: {sorted(o_addrs)}\n  result: {sorted(r_addrs)}")

    return problems


def _load_export_dir(export_dir: Path) -> dict:
    by_id = {}
    for eml_path in export_dir.rglob("*.eml"):
        parsed = message_from_bytes(eml_path.read_bytes(), policy=email_policy_default)
        msg_id = parsed.get("X-Mail-Utils-ID")
        if msg_id:
            by_id[msg_id] = parsed
    return by_id


def _decoded_body(parsed) -> bytes:
    body_part = parsed.get_body(preferencelist=("html", "plain"))
    return body_part.get_content().encode("utf-8") if body_part else b""


def _decoded_attachments(parsed) -> list:
    result = []
    for part in parsed.iter_attachments():
        result.append((part.get_filename(), part.get_content_type(), part.get_content()))
    return sorted(result, key=lambda t: (t[0] or "", t[1] or ""))


def _decoded_inline_parts(parsed) -> list:
    """Return (content_id, mime_type, bytes) for every MIME part carrying a Content-ID header - an
    inline image embedded via cid: is part of the multipart/related body tree, not something
    iter_attachments() surfaces, so it needs its own walk."""
    result = []
    for part in parsed.walk():
        content_id = part.get("Content-ID")
        if content_id:
            result.append((content_id, part.get_content_type(), part.get_content()))
    return sorted(result, key=lambda t: t[0])


def _labels_from_header(parsed, exclude_prefix: str) -> set:
    raw = parsed.get("X-Mail-Utils-Labels", "")
    names = {n.strip() for n in raw.split(",") if n.strip()}
    return {n for n in names if not n.startswith(exclude_prefix)}


def _compare_exports(origin_dir: Path, result_dir: Path, pairs: list) -> list[str]:
    problems = []
    origin_files = _load_export_dir(origin_dir)
    result_files = _load_export_dir(result_dir)

    for origin_id, result_id in pairs:
        origin_parsed = origin_files.get(origin_id)
        result_parsed = result_files.get(result_id)
        label = f"{origin_id} -> {result_id}"
        if origin_parsed is None:
            problems.append(f"{label}: no exported .eml found in {origin_dir} for origin id {origin_id!r}")
            continue
        if result_parsed is None:
            problems.append(f"{label}: no exported .eml found in {result_dir} for result id {result_id!r}")
            continue

        for header in ("Subject", "From", "To", "Cc", "Bcc", "Date"):
            if (origin_parsed.get(header) or "") != (result_parsed.get(header) or ""):
                problems.append(f"{label}: {header} header differs: {origin_parsed.get(header)!r} != {result_parsed.get(header)!r}")

        if _decoded_body(origin_parsed) != _decoded_body(result_parsed):
            problems.append(f"{label}: decoded body content differs")

        o_atts = _decoded_attachments(origin_parsed)
        r_atts = _decoded_attachments(result_parsed)
        if o_atts != r_atts:
            o_desc = [(f, c, len(b)) for f, c, b in o_atts]
            r_desc = [(f, c, len(b)) for f, c, b in r_atts]
            problems.append(f"{label}: decoded attachment content differs:\n  origin: {o_desc}\n  result: {r_desc}")

        o_inline = _decoded_inline_parts(origin_parsed)
        r_inline = _decoded_inline_parts(result_parsed)
        if o_inline != r_inline:
            o_desc = [(cid, c, len(b)) for cid, c, b in o_inline]
            r_desc = [(cid, c, len(b)) for cid, c, b in r_inline]
            problems.append(f"{label}: decoded inline (cid:) image content differs:\n  origin: {o_desc}\n  result: {r_desc}")

        o_labels = _labels_from_header(origin_parsed, exclude_prefix="mail-utils-store-in-gmail-")
        r_labels = _labels_from_header(result_parsed, exclude_prefix="mail-utils-store-in-gmail-")
        if o_labels != r_labels:
            problems.append(f"{label}: X-Mail-Utils-Labels differ (tracking label excluded): {o_labels} != {r_labels}")

    return problems


def _run_compare(args) -> int:
    origin = _load_db(Path(args.origin_db))
    result = _load_db(Path(args.result_db))
    print(f"Origin database: {len(origin['messages'])} messages. Result database: {len(result['messages'])} messages.")

    db_problems = _compare_databases(origin, result)
    pairs, _, _ = _pair_by_subject_and_date(origin, result)
    export_problems = _compare_exports(Path(args.origin_export), Path(args.result_export), pairs)

    problems = db_problems + export_problems
    if not problems:
        print(f"PASS: {len(pairs)} messages compared, no differences found (beyond expected id/label/timestamp changes).")
        return 0

    print(f"FAIL: {len(problems)} problem(s) found:")
    for p in problems:
        print(f"  - {p}")
    return 1


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    version = get_mail_utils_version()
    parser = build_action_parser(PROG, DESCRIPTION, ["seed", "compare", "cleanup", "version", "help"], "help")
    parser.add_argument(
        "--account", help="Gmail account to authenticate as (see 'mail-utils prepare-gmail-account') (seed, cleanup)"
    )
    parser.add_argument("--to", help="Recipient address to stamp on every seeded message (seed)")
    parser.add_argument("--origin-db", help="Origin database path (compare)")
    parser.add_argument("--origin-export", help="Origin export directory path (compare)")
    parser.add_argument("--result-db", help="Result database path (compare)")
    parser.add_argument("--result-export", help="Result export directory path (compare)")
    parser.add_argument("--label", help="Gmail label name to clean up (cleanup)")
    parser.add_argument("--apply", action="store_true", help="Actually move messages to Trash, instead of a dry run (cleanup)")
    args = parser.parse_args()

    if args.version or args.action == "version":
        print_version(PROG, version)
        return 0
    if args.help or args.action == "help":
        print_help(PROG, version, DESCRIPTION, parser, EXIT_CODES)
        return 0

    if args.action == "seed":
        if not args.to:
            print("seed requires --to", file=sys.stderr)
            return 2
        return _run_seed(args)
    if args.action == "cleanup":
        if not args.label:
            print("cleanup requires --label", file=sys.stderr)
            return 2
        return _run_cleanup(args)
    if args.action == "compare":
        missing = [name for name in ("origin_db", "origin_export", "result_db", "result_export") if not getattr(args, name)]
        if missing:
            print(f"compare requires: {', '.join('--' + m.replace('_', '-') for m in missing)}", file=sys.stderr)
            return 2
        return _run_compare(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
