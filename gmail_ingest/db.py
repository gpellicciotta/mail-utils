import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          TEXT PRIMARY KEY,
    thread_id   TEXT,
    sender      TEXT,
    recipient   TEXT,
    cc          TEXT,
    bcc         TEXT,
    subject     TEXT,
    date        TEXT,
    snippet     TEXT,
    label_ids   TEXT,
    body_text   TEXT,
    fetched_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sync_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS labels (
    id   TEXT PRIMARY KEY,
    name TEXT NOT NULL
);
"""


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, coltype: str) -> None:
    """Add `column` to an existing `table` if it's missing.

    CREATE TABLE IF NOT EXISTS in SCHEMA only applies to brand-new
    databases; a database created before this column existed needs an
    explicit ALTER TABLE to pick it up.
    """
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        conn.commit()


def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    conn.commit()
    _ensure_column(conn, "messages", "cc", "TEXT")
    _ensure_column(conn, "messages", "bcc", "TEXT")
    return conn


def get_sync_state(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_sync_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO sync_state (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def upsert_labels(conn: sqlite3.Connection, labels: list[dict]) -> None:
    conn.executemany(
        "INSERT INTO labels (id, name) VALUES (:id, :name) "
        "ON CONFLICT(id) DO UPDATE SET name = excluded.name",
        labels,
    )
    conn.commit()


def upsert_message(conn: sqlite3.Connection, msg: dict) -> None:
    conn.execute(
        """
        INSERT INTO messages (id, thread_id, sender, recipient, cc, bcc, subject, date, snippet, label_ids, body_text)
        VALUES (:id, :thread_id, :sender, :recipient, :cc, :bcc, :subject, :date, :snippet, :label_ids, :body_text)
        ON CONFLICT(id) DO UPDATE SET
            thread_id = excluded.thread_id,
            sender = excluded.sender,
            recipient = excluded.recipient,
            cc = excluded.cc,
            bcc = excluded.bcc,
            subject = excluded.subject,
            date = excluded.date,
            snippet = excluded.snippet,
            label_ids = excluded.label_ids,
            body_text = excluded.body_text
        """,
        msg,
    )
    conn.commit()
