import sqlite3
from collections import Counter

from .config import DB_PATH


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

    conn.close()


if __name__ == "__main__":
    run()
