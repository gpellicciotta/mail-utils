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
    internal_date_ms INTEGER,
    snippet     TEXT,
    label_ids   TEXT,
    body_text   TEXT,
    body_mime_type TEXT,
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

CREATE TABLE IF NOT EXISTS gmail_store_state (
    message_id TEXT PRIMARY KEY,
    gmail_id   TEXT,
    stored_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS message_addresses (
    message_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    address    TEXT NOT NULL,
    name       TEXT,
    PRIMARY KEY (message_id, role, address)
);

CREATE INDEX IF NOT EXISTS idx_message_addresses_role_address
    ON message_addresses (role, address);

CREATE TABLE IF NOT EXISTS attachments (
    message_id     TEXT NOT NULL,
    attachment_id  TEXT,
    filename       TEXT NOT NULL,
    mime_type      TEXT,
    size           INTEGER
);

CREATE INDEX IF NOT EXISTS idx_attachments_message_id
    ON attachments (message_id);
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


def _ensure_fts(conn: sqlite3.Connection) -> None:
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                id UNINDEXED,
                subject,
                body_text,
                sender,
                recipient,
                tokenize='unicode61 remove_diacritics 2'
            )
            """
        )
        conn.commit()
        # Backfill if messages exist but messages_fts is empty
        (msg_count,) = conn.execute("SELECT COUNT(*) FROM messages").fetchone()
        (fts_count,) = conn.execute("SELECT COUNT(*) FROM messages_fts").fetchone()
        if msg_count > 0 and fts_count == 0:
            conn.execute(
                """
                INSERT INTO messages_fts (id, subject, body_text, sender, recipient)
                SELECT id, COALESCE(subject, ''), COALESCE(body_text, ''), COALESCE(sender, ''), COALESCE(recipient, '')
                FROM messages
                """
            )
            conn.commit()
    except sqlite3.OperationalError:
        pass


def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    conn.commit()
    _ensure_column(conn, "messages", "cc", "TEXT")
    _ensure_column(conn, "messages", "bcc", "TEXT")
    _ensure_column(conn, "messages", "internal_date_ms", "INTEGER")
    _ensure_column(conn, "messages", "body_mime_type", "TEXT")
    _ensure_fts(conn)
    return conn


def get_sync_state(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_sync_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO sync_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def is_stored_in_gmail(conn: sqlite3.Connection, message_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM gmail_store_state WHERE message_id = ?", (message_id,)).fetchone()
    return row is not None


def mark_stored_in_gmail(conn: sqlite3.Connection, message_id: str, gmail_id: str | None) -> None:
    conn.execute(
        "INSERT INTO gmail_store_state (message_id, gmail_id) VALUES (?, ?) "
        "ON CONFLICT(message_id) DO UPDATE SET gmail_id = excluded.gmail_id, stored_at = datetime('now')",
        (message_id, gmail_id),
    )
    conn.commit()


def upsert_labels(conn: sqlite3.Connection, labels: list[dict]) -> None:
    conn.executemany(
        "INSERT INTO labels (id, name) VALUES (:id, :name) ON CONFLICT(id) DO UPDATE SET name = excluded.name",
        labels,
    )
    conn.commit()


def upsert_addresses(conn: sqlite3.Connection, message_id: str, addresses: list) -> None:
    """Replace message_id's rows in message_addresses with `addresses`.

    Delete-then-insert rather than an upsert: Gmail messages are immutable,
    so a rerun's address set for a given message never actually differs,
    but this keeps behavior correct/simple if it ever does.
    """
    conn.execute("DELETE FROM message_addresses WHERE message_id = ?", (message_id,))
    if addresses:
        conn.executemany(
            "INSERT INTO message_addresses (message_id, role, address, name) VALUES (:message_id, :role, :address, :name)",
            addresses,
        )
    conn.commit()


def upsert_attachments(conn: sqlite3.Connection, message_id: str, attachments: list) -> None:
    """Replace message_id's rows in attachments with `attachments`.

    Same delete-then-insert rationale as upsert_addresses.
    """
    conn.execute("DELETE FROM attachments WHERE message_id = ?", (message_id,))
    if attachments:
        conn.executemany(
            "INSERT INTO attachments (message_id, attachment_id, filename, mime_type, size) "
            "VALUES (:message_id, :attachment_id, :filename, :mime_type, :size)",
            attachments,
        )
    conn.commit()


def upsert_message(conn: sqlite3.Connection, msg: dict) -> None:
    conn.execute(
        """
        INSERT INTO messages (id, thread_id, sender, recipient, cc, bcc, subject, date, internal_date_ms, snippet, label_ids, body_text, body_mime_type)
        VALUES (:id, :thread_id, :sender, :recipient, :cc, :bcc, :subject, :date, :internal_date_ms, :snippet, :label_ids, :body_text, :body_mime_type)
        ON CONFLICT(id) DO UPDATE SET
            thread_id = excluded.thread_id,
            sender = excluded.sender,
            recipient = excluded.recipient,
            cc = excluded.cc,
            bcc = excluded.bcc,
            subject = excluded.subject,
            date = excluded.date,
            internal_date_ms = excluded.internal_date_ms,
            snippet = excluded.snippet,
            label_ids = excluded.label_ids,
            body_text = excluded.body_text,
            body_mime_type = excluded.body_mime_type
        """,
        msg,
    )
    try:
        conn.execute("DELETE FROM messages_fts WHERE id = ?", (msg["id"],))
        conn.execute(
            """
            INSERT INTO messages_fts (id, subject, body_text, sender, recipient)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                msg["id"],
                msg.get("subject") or "",
                msg.get("body_text") or "",
                msg.get("sender") or "",
                msg.get("recipient") or "",
            ),
        )
    except sqlite3.OperationalError:
        pass
    conn.commit()
