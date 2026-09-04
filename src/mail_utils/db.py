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
    body_html   TEXT,
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
    filename       TEXT,
    mime_type      TEXT,
    size           INTEGER,
    content_sha256 TEXT,
    content_id     TEXT
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


def _ensure_attachments_filename_nullable(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA table_info(attachments)").fetchall()
    for row in rows:
        if row[1] == "filename" and row[3] == 1:
            conn.execute(
                "CREATE TABLE attachments_new ("
                "message_id TEXT NOT NULL, "
                "attachment_id TEXT, "
                "filename TEXT, "
                "mime_type TEXT, "
                "size INTEGER, "
                "content_sha256 TEXT, "
                "content_id TEXT)"
            )
            conn.execute(
                "INSERT INTO attachments_new SELECT message_id, attachment_id, filename, mime_type, size, content_sha256, content_id FROM attachments"
            )
            conn.execute("DROP TABLE attachments")
            conn.execute("ALTER TABLE attachments_new RENAME TO attachments")
            conn.execute("CREATE INDEX idx_attachments_message_id ON attachments (message_id)")
            conn.commit()
            break


def rebuild_fts(conn: sqlite3.Connection) -> None:
    """Fully repopulate messages_fts from messages in one bulk operation - the counterpart to
    upsert_message(update_fts=False), for a bulk-import loop that skips per-message FTS5 maintenance
    (see its docstring for why) and calls this once after the loop instead.

    Also serves as a one-off repair for a messages_fts index that's degraded from exactly the pattern
    this replaces: FTS5's internal segment structure fragments under many small incremental
    delete+insert operations, and a full rebuild is the straightforward fix (confirmed empirically
    against a real ~3.7GB, 127,874-message database: the bulk rebuild here took ~3 minutes total,
    versus a ~1.5s-per-message cost for the incremental path it replaces - literally orders of
    magnitude apart at that scale)."""
    conn.execute("DELETE FROM messages_fts")
    conn.execute(
        """
        INSERT INTO messages_fts (id, subject, body_text, sender, recipient)
        SELECT id, COALESCE(subject, ''), COALESCE(body_text, ''), COALESCE(sender, ''), COALESCE(recipient, '')
        FROM messages
        """
    )
    conn.commit()


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    # WAL mode avoids the rollback-journal's per-transaction create/fsync/delete cycle (a real,
    # measured bottleneck on a large import: every upsert_message/upsert_addresses/upsert_attachments
    # call used to commit individually under the default journal_mode=DELETE, and the cost grew
    # noticeably worse as the database passed a few GB) - one append-only WAL file instead, checkpointed
    # automatically. synchronous=NORMAL is the documented-safe pairing for WAL (still crash-safe against
    # corruption; the only risk is losing the most recent *uncommitted* batch on a hard crash, which a
    # bulk import already tolerates fine - upsert_message et al. are safe to simply reprocess).
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    conn.commit()
    _ensure_column(conn, "messages", "cc", "TEXT")
    _ensure_column(conn, "messages", "bcc", "TEXT")
    _ensure_column(conn, "messages", "internal_date_ms", "INTEGER")
    _ensure_column(conn, "messages", "body_mime_type", "TEXT")
    _ensure_column(conn, "messages", "body_html", "TEXT")
    _ensure_column(conn, "attachments", "content_sha256", "TEXT")
    _ensure_column(conn, "attachments", "content_id", "TEXT")
    _ensure_attachments_filename_nullable(conn)
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


def upsert_addresses(conn: sqlite3.Connection, message_id: str, addresses: list, commit: bool = True) -> None:
    """Replace message_id's rows in message_addresses with `addresses`.

    Delete-then-insert rather than an upsert: Gmail messages are immutable,
    so a rerun's address set for a given message never actually differs,
    but this keeps behavior correct/simple if it ever does.

    `commit=False` for a bulk-import hot loop batching its own commits instead - see
    upsert_message's docstring for why."""
    conn.execute("DELETE FROM message_addresses WHERE message_id = ?", (message_id,))
    if addresses:
        conn.executemany(
            "INSERT INTO message_addresses (message_id, role, address, name) VALUES (:message_id, :role, :address, :name)",
            addresses,
        )
    if commit:
        conn.commit()


def upsert_attachments(conn: sqlite3.Connection, message_id: str, attachments: list, commit: bool = True) -> None:
    """Replace message_id's rows in attachments with `attachments`.

    Same delete-then-insert rationale as upsert_addresses. `content_sha256` and `content_id` are read
    via `.get()` (defaulting to `None`) since not every caller sets them - `content_sha256` only when
    `--with-attachments` was used, `content_id` only for a Gmail inline-image part that carried one.

    `commit=False` for a bulk-import hot loop batching its own commits instead - see
    upsert_message's docstring for why."""
    conn.execute("DELETE FROM attachments WHERE message_id = ?", (message_id,))
    if attachments:
        rows = [
            {
                "message_id": att["message_id"],
                "attachment_id": att.get("attachment_id"),
                "filename": att["filename"],
                "mime_type": att.get("mime_type"),
                "size": att.get("size"),
                "content_sha256": att.get("content_sha256"),
                "content_id": att.get("content_id"),
            }
            for att in attachments
        ]
        conn.executemany(
            "INSERT INTO attachments (message_id, attachment_id, filename, mime_type, size, content_sha256, content_id) "
            "VALUES (:message_id, :attachment_id, :filename, :mime_type, :size, :content_sha256, :content_id)",
            rows,
        )
    if commit:
        conn.commit()


def upsert_message(conn: sqlite3.Connection, msg: dict, commit: bool = True, update_fts: bool = True) -> None:
    """`body_html` is read via `.get()` (defaulting to `None`) since not every source parser
    populates it yet (see gmail_client.py's `parse_message` vs. outlook/thunderbird's).

    `commit=False` lets a bulk-import hot loop batch its own commits instead of committing on every
    single call (see cli.py's COMMIT_BATCH_INTERVAL) - committing every single message was a real,
    measured bottleneck against a large archive (every commit forces a full fsync under SQLite's
    default settings, and the cost only grows as the database gets larger), while every other, lower-
    volume caller keeps today's simpler commit-immediately default.

    `update_fts=False` skips the messages_fts delete+insert below entirely - the *much* bigger of the
    two bottlenecks, measured against the real archive that motivated both parameters: FTS5's internal
    segment structure fragments under many small incremental delete+insert operations, and at that
    database's actual scale (~127,874 messages) this cost roughly 1.5 SECONDS per message, dwarfing
    even the commit/fsync cost `commit=False` addresses. A bulk-import loop should pass
    `update_fts=False` and call `rebuild_fts(conn)` once after the loop instead - confirmed to cost
    around 3 minutes total for that same database, versus over 50 hours doing it incrementally.
    Low-volume callers keep today's simpler default (correct immediately, no separate rebuild step)."""
    params = {**msg, "body_html": msg.get("body_html")}
    conn.execute(
        """
        INSERT INTO messages (id, thread_id, sender, recipient, cc, bcc, subject, date, internal_date_ms, snippet, label_ids, body_text, body_mime_type, body_html)
        VALUES (:id, :thread_id, :sender, :recipient, :cc, :bcc, :subject, :date, :internal_date_ms, :snippet, :label_ids, :body_text, :body_mime_type, :body_html)
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
            body_mime_type = excluded.body_mime_type,
            body_html = excluded.body_html
        """,
        params,
    )
    if update_fts:
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
    if commit:
        conn.commit()
