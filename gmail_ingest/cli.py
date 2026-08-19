import argparse
import logging
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .auth import get_credentials
from .config import DB_PATH, LOG_DIR, LOG_PATH
from .db import (
    get_sync_state,
    init_db,
    set_sync_state,
    upsert_addresses,
    upsert_attachments,
    upsert_labels,
    upsert_message,
)
from .gmail_client import (
    HistoryExpiredError,
    build_gmail_service,
    fetch_message,
    get_current_history_id,
    get_profile,
    list_all_message_ids,
    list_changed_message_ids,
    list_labels,
    parse_addresses,
    parse_attachments,
    parse_message,
)

logger = logging.getLogger("gmail_ingest")

PROGRESS_LOG_INTERVAL = 50


def _setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
    )


def _full_sync(service, conn) -> None:
    logger.info("Running full sync (no prior sync state found)")
    profile = get_profile(service)
    history_id = profile["historyId"]
    total = profile.get("messagesTotal")
    if total:
        logger.info(
            "Mailbox reports ~%d messages total (upper bound - excludes "
            "nothing on Gmail's side, but this sync skips Spam/Trash, so "
            "%%-complete may cap below 100%%)",
            total,
        )
    count = 0
    for msg_id in list_all_message_ids(service):
        raw = fetch_message(service, msg_id)
        upsert_message(conn, parse_message(raw))
        upsert_addresses(conn, raw["id"], parse_addresses(raw))
        upsert_attachments(conn, raw["id"], parse_attachments(raw))
        count += 1
        if count % PROGRESS_LOG_INTERVAL == 0:
            if total:
                logger.info(
                    "Full sync progress: %d/%d messages (%.1f%%)",
                    count, total, 100 * count / total,
                )
            else:
                logger.info("Full sync progress: %d messages indexed so far", count)
    set_sync_state(conn, "last_history_id", history_id)
    logger.info("Full sync complete: %d messages indexed", count)


def _incremental_sync(service, conn, last_history_id: str) -> None:
    try:
        count = 0
        for msg_id in list_changed_message_ids(service, last_history_id):
            raw = fetch_message(service, msg_id)
            upsert_message(conn, parse_message(raw))
            upsert_addresses(conn, raw["id"], parse_addresses(raw))
            upsert_attachments(conn, raw["id"], parse_attachments(raw))
            count += 1
            if count % PROGRESS_LOG_INTERVAL == 0:
                logger.info("Incremental sync progress: %d messages indexed so far", count)
        new_history_id = get_current_history_id(service)
        set_sync_state(conn, "last_history_id", new_history_id)
        logger.info("Incremental sync complete: %d new messages", count)
    except HistoryExpiredError:
        logger.warning("Stored historyId expired; falling back to full sync")
        _full_sync(service, conn)


def _run_update(args: argparse.Namespace) -> None:
    _setup_logging()
    logger.info("Starting gmail_ingest run")

    creds = get_credentials()
    service = build_gmail_service(creds)
    conn = init_db(DB_PATH)

    upsert_labels(conn, list_labels(service))

    last_history_id = get_sync_state(conn, "last_history_id")
    if last_history_id is None:
        _full_sync(service, conn)
    else:
        _incremental_sync(service, conn, last_history_id)

    conn.close()
    logger.info("Run finished")


def _format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024


def _run_stats(args: argparse.Namespace) -> None:
    if not DB_PATH.exists():
        print(f"No database found at {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    (total,) = cur.execute("SELECT COUNT(*) FROM messages").fetchone()
    (threads,) = cur.execute("SELECT COUNT(DISTINCT thread_id) FROM messages").fetchone()
    first_fetched, last_fetched = cur.execute(
        "SELECT MIN(fetched_at), MAX(fetched_at) FROM messages"
    ).fetchone()
    row = cur.execute(
        "SELECT value FROM sync_state WHERE key = 'last_history_id'"
    ).fetchone()
    last_history_id = row[0] if row else None

    fields = [
        ("Database", DB_PATH),
        ("Total messages", total),
        ("Distinct threads", threads),
        ("First indexed", first_fetched),
        ("Last indexed", last_fetched),
        ("Last history ID", last_history_id),
    ]
    key_width = max(len(key) for key, _ in fields)
    for key, value in fields:
        print(f"{key + ':':<{key_width + 1}} {value}")

    try:
        label_names = dict(cur.execute("SELECT id, name FROM labels"))
    except sqlite3.OperationalError:
        label_names = {}

    label_counts = Counter()
    for (label_ids,) in cur.execute("SELECT label_ids FROM messages WHERE label_ids != ''"):
        label_counts.update(label_ids.split(","))

    if label_counts:
        top = label_counts.most_common(15)
        resolved = [(label_names.get(label_id, label_id), count) for label_id, count in top]
        name_width = max(len(name) for name, _ in resolved)

        print("\nTop labels:")
        for name, count in resolved:
            print(f"  {name:<{name_width}} {count:>6}")

        if not label_names:
            print(
                "\n(Label names unavailable - run a sync with the current "
                "code at least once to populate the labels table.)"
            )

    try:
        cur.execute("SELECT 1 FROM message_addresses LIMIT 1")
        has_addresses = True
    except sqlite3.OperationalError:
        has_addresses = False

    if has_addresses:
        for role, title in (
            ("from", "Top senders"),
            ("to", "Top To recipients"),
            ("cc", "Top Cc recipients"),
            ("bcc", "Top Bcc recipients"),
        ):
            rows = cur.execute(
                "SELECT address, MAX(name) AS name, COUNT(*) AS n FROM message_addresses "
                "WHERE role = ? GROUP BY address ORDER BY n DESC LIMIT 15",
                (role,),
            ).fetchall()
            if not rows:
                continue
            labeled = [(f"{name} <{address}>" if name else address, n) for address, name, n in rows]
            width = max(len(label) for label, _ in labeled)
            print(f"\n{title}:")
            for label, n in labeled:
                print(f"  {label:<{width}} {n:>6}")
    else:
        print(
            "\n(Recipient stats unavailable - run a sync with the current "
            "code at least once to populate the message_addresses table.)"
        )

    try:
        att_count, att_size = cur.execute(
            "SELECT COUNT(*), COALESCE(SUM(size), 0) FROM attachments"
        ).fetchone()
        print(f"\nAttachments: {att_count} total, {_format_size(att_size)}")
    except sqlite3.OperationalError:
        print(
            "\n(Attachment stats unavailable - run a sync with the current "
            "code at least once to populate the attachments table.)"
        )

    conn.close()


EXPORT_PROGRESS_INTERVAL = 500


def _run_export(args: argparse.Namespace) -> None:
    if not DB_PATH.exists():
        print(f"No database found at {DB_PATH}")
        return

    output_dir = Path(args.output_dir)
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    label_names = dict(cur.execute("SELECT id, name FROM labels"))

    attachments_by_message = {}
    for message_id, filename, mime_type, size in cur.execute(
        "SELECT message_id, filename, mime_type, size FROM attachments ORDER BY message_id"
    ):
        attachments_by_message.setdefault(message_id, []).append(
            {"filename": filename, "mime_type": mime_type, "size": size}
        )

    rows = cur.execute(
        "SELECT id, thread_id, sender, recipient, cc, bcc, subject, date, "
        "internal_date_ms, label_ids, body_text, body_mime_type FROM messages"
    ).fetchall()
    conn.close()

    count = 0
    for (
        msg_id, thread_id, sender, recipient, cc, bcc, subject, date,
        internal_date_ms, label_ids, body_text, body_mime_type,
    ) in rows:
        if internal_date_ms:
            dt = datetime.fromtimestamp(internal_date_ms / 1000, tz=timezone.utc)
            subdir = output_dir / f"{dt.year:04d}" / f"{dt.month:02d}"
            internal_date_iso = dt.isoformat()
        else:
            subdir = output_dir / "unknown"
            internal_date_iso = None
        subdir.mkdir(parents=True, exist_ok=True)

        labels = [label_names.get(lbl, lbl) for lbl in label_ids.split(",")] if label_ids else []

        frontmatter = {
            "id": msg_id,
            "thread_id": thread_id,
            "from": sender,
            "to": recipient,
            "cc": cc,
            "bcc": bcc,
            "subject": subject,
            "date": date,
            "internal_date": internal_date_iso,
            "labels": labels,
            "body_mime_type": body_mime_type,
            "attachments": attachments_by_message.get(msg_id, []),
        }
        frontmatter = {k: v for k, v in frontmatter.items() if v not in (None, [], "")}

        content = (
            "---\n"
            + yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
            + "---\n\n"
            + (body_text or "")
        )
        (subdir / f"{msg_id}.md").write_text(content, encoding="utf-8")

        count += 1
        if count % EXPORT_PROGRESS_INTERVAL == 0:
            print(f"  exported {count}/{len(rows)}")

    print(f"Exported {count} messages to {output_dir}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gmail-ingest")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("help", help="Show this help message")

    update = subparsers.add_parser("update", help="Sync new mail into the local database")
    update.set_defaults(func=_run_update)

    stats = subparsers.add_parser("stats", help="Print summary stats from the local database")
    stats.set_defaults(func=_run_stats)

    export = subparsers.add_parser("export", help="Export all messages as markdown files")
    export.add_argument("output_dir", help="Directory to write .md files into (created if missing)")
    export.set_defaults(func=_run_export)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None or args.command == "help":
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
