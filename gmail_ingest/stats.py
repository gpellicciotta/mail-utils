import sqlite3
from collections import Counter

from .config import DB_PATH


def _format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024


def run() -> None:
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


if __name__ == "__main__":
    run()
