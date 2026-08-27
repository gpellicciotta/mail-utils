import argparse
import hashlib
import logging
import mailbox
import platform
import re
import sqlite3
import sys
import tempfile
import time
import zipfile
from collections import Counter
from collections.abc import Iterator
from datetime import datetime, timezone
from email import message_from_bytes
from email.message import EmailMessage
from email.policy import default as _email_policy_default
from email.utils import format_datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version
from pathlib import Path

import yaml
from googleapiclient.errors import HttpError

from .auth import get_credentials
from .config import BASE_DIR, CREDENTIALS_PATH, DB_PATH, LOG_DIR, LOG_PATH, STORE_IN_GMAIL_SCOPES, TOKEN_PATH
from .db import (
    get_sync_state,
    init_db,
    is_stored_in_gmail,
    mark_stored_in_gmail,
    set_sync_state,
    upsert_addresses,
    upsert_attachments,
    upsert_labels,
    upsert_message,
)
from .filters import FilterError, message_matches, parse_filter
from .gmail_client import (
    HistoryExpiredError,
    build_gmail_service,
    create_label,
    fetch_message,
    get_current_history_id,
    get_profile,
    import_message,
    list_all_message_ids,
    list_changed_message_ids,
    list_labels,
    parse_addresses,
    parse_attachments,
    parse_message,
)
from .gmail_client import (
    extract_attached_messages as gmail_extract_attached_messages,
)
from .outlook.messages import fetch_message as pst_fetch_message
from .outlook.messages import parse_addresses as pst_parse_addresses
from .outlook.messages import parse_attachments as pst_parse_attachments
from .outlook.messages import parse_message as pst_parse_message
from .outlook.ndb import PSTFile
from .outlook.tree import folder_label_id, labels_for_folders, walk_folders
from .scheduling import (
    ALLOWED_COMMANDS,
    ScheduleError,
    list_cron_jobs,
    list_windows_jobs,
    schedule_cron,
    schedule_windows,
    unschedule_cron,
    unschedule_windows,
    windows_task_name,
)
from .thunderbird.archive import extract_mbox_to_file
from .thunderbird.archive import walk_folders as tb_walk_folders
from .thunderbird.messages import (
    extract_attached_messages as tb_extract_attached_messages,
)
from .thunderbird.messages import (
    parse_addresses as tb_parse_addresses,
)
from .thunderbird.messages import (
    parse_attachments as tb_parse_attachments,
)
from .thunderbird.messages import (
    parse_message as tb_parse_message,
)
from .thunderbird.tree import folder_label_id as tb_folder_label_id
from .thunderbird.tree import labels_for_folders as tb_labels_for_folders

logger = logging.getLogger("mail_utils")

PROGRESS_LOG_INTERVAL = 50


def _get_version() -> str:
    try:
        return _package_version("mail-utils")
    except PackageNotFoundError:
        return "2.3.0"


class _UTCFormatter(logging.Formatter):
    """Formats log timestamps in UTC and indents subsequent lines of multi-line messages."""

    converter = time.gmtime

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        lines = formatted.split("\n")
        if len(lines) <= 1:
            return formatted
        first_line_msg = record.getMessage().split("\n")[0]
        prefix_len = len(lines[0]) - len(first_line_msg)
        indent = " " * max(0, prefix_len)
        return lines[0] + "\n" + "\n".join(indent + line if line else line for line in lines[1:])


_LOG_FORMAT = "%(asctime)s UTC [%(levelname)s] %(message)s"


def _setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger.handlers.clear()
    logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(_UTCFormatter(_LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console_handler)


def _process_gmail_msg(service, conn, msg_id: str, recursive: bool) -> int:
    raw = fetch_message(service, msg_id)
    parsed = parse_message(raw)
    upsert_message(conn, parsed)
    upsert_addresses(conn, parsed["id"], parse_addresses(raw))
    upsert_attachments(conn, parsed["id"], parse_attachments(raw))
    count = 1
    if recursive:
        for sub in gmail_extract_attached_messages(raw):
            sub_parsed = parse_message(sub)
            upsert_message(conn, sub_parsed)
            upsert_addresses(conn, sub_parsed["id"], parse_addresses(sub))
            upsert_attachments(conn, sub_parsed["id"], parse_attachments(sub))
            count += 1
    return count


def _full_sync(service, conn, start_time: float, recursive: bool = False) -> int:
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
        count += _process_gmail_msg(service, conn, msg_id, recursive)
        if count % PROGRESS_LOG_INTERVAL == 0:
            elapsed = time.time() - start_time
            if total:
                pct = 100.0 * count / total
                logger.info(
                    "Full sync progress: %d/~%d messages (%.1f%% - elapsed: %.1fs)",
                    count,
                    total,
                    pct,
                    elapsed,
                )
            else:
                logger.info("Full sync progress: %d messages indexed (elapsed: %.1fs)", count, elapsed)
    set_sync_state(conn, "last_history_id", history_id)
    return count


def _incremental_sync(service, conn, last_history_id: str, start_time: float, recursive: bool = False) -> int:
    logger.info("Running incremental sync from history ID %s", last_history_id)
    try:
        count = 0
        for msg_id in list_changed_message_ids(service, last_history_id):
            count += _process_gmail_msg(service, conn, msg_id, recursive)
            if count % PROGRESS_LOG_INTERVAL == 0:
                elapsed = time.time() - start_time
                logger.info("Incremental sync progress: %d messages indexed (elapsed: %.1fs)", count, elapsed)
        new_history_id = get_current_history_id(service)
        set_sync_state(conn, "last_history_id", new_history_id)
        return count
    except HistoryExpiredError:
        logger.warning("Stored historyId expired; falling back to full sync")
        return _full_sync(service, conn, start_time, recursive)


def _filtered_import(service, conn, query: str, start_time: float, recursive: bool = False) -> int:
    """Import only messages matching Gmail's native `q` search syntax.

    Passed straight through to Gmail (full grammar, zero parsing on our
    side) via a filtered full listing - not incremental, and sync_state
    is deliberately left untouched so this can't interfere with regular
    unfiltered `import` runs' historyId-based bookkeeping.
    """
    logger.info("Running filtered import (sync_state is not touched)")
    count = 0
    for msg_id in list_all_message_ids(service, query=query):
        count += _process_gmail_msg(service, conn, msg_id, recursive)
        if count % PROGRESS_LOG_INTERVAL == 0:
            elapsed = time.time() - start_time
            logger.info("Filtered import progress: %d messages indexed (elapsed: %.1fs)", count, elapsed)
    return count


def _resolve_db_path(args: argparse.Namespace) -> Path:
    db = getattr(args, "db", None)
    return Path(db) if db else DB_PATH


def _run_import_gmail(args: argparse.Namespace) -> None:
    _setup_logging()
    version = _get_version()
    start_time = time.time()
    db_path = _resolve_db_path(args)
    recursive = getattr(args, "recursive", False)

    logger.info("Mail Utils %s operation started: Gmail sync", version)
    logger.info("Database:  %s", db_path)
    if getattr(args, "filter", None):
        logger.info("Filter:    %s", args.filter)
    if recursive:
        logger.info("Recursive: True")

    creds = get_credentials()
    service = build_gmail_service(creds)
    conn = init_db(db_path)

    upsert_labels(conn, list_labels(service))

    if getattr(args, "filter", None):
        count = _filtered_import(service, conn, args.filter, start_time, recursive)
    else:
        last_history_id = get_sync_state(conn, "last_history_id")
        if last_history_id is None:
            count = _full_sync(service, conn, start_time, recursive)
        else:
            count = _incremental_sync(service, conn, last_history_id, start_time, recursive)

    conn.close()
    elapsed = time.time() - start_time
    logger.info("Mail Utils %s operation ended in %.1fs: %d messages indexed", version, elapsed, count)


def _resolve_label_ids(service, label_names: list[str], cache: dict[str, str]) -> list[str]:
    """Translate label display names (as written to X-Mail-Utils-Labels)
    back to Gmail label IDs, creating any that don't already exist.

    `cache` should start seeded with every existing label (from
    list_labels()) so system labels (INBOX, STARRED, ...) - whose id equals
    their name - are never mistakenly re-created."""
    ids = []
    for name in label_names:
        label_id = cache.get(name)
        if label_id is None:
            label_id = _gmail_call_with_backoff(create_label, service, name)["id"]
            cache[name] = label_id
        ids.append(label_id)
    return ids


_GMAIL_STORE_MAX_CALLS_PER_SECOND = 8
"""Caps `messages.import` calls under Gmail's per-user quota (25 units/call, 250 units/sec moving
average - roughly 10 calls/sec) with headroom left for the label list/create calls sharing the
same per-user budget."""

_GMAIL_STORE_MAX_RETRIES = 5


def _throttle_gmail_store(last_call_time: float) -> float:
    """Sleep just long enough to keep import calls under _GMAIL_STORE_MAX_CALLS_PER_SECOND.
    Returns the timestamp to pass as `last_call_time` on the next call."""
    min_interval = 1.0 / _GMAIL_STORE_MAX_CALLS_PER_SECOND
    now = time.time()
    wait = min_interval - (now - last_call_time)
    if wait > 0:
        time.sleep(wait)
    return time.time()


def _gmail_call_with_backoff(func, *args, **kwargs):
    """Call a Gmail API function, retrying with exponential backoff if Gmail reports a rate-limit
    error (HTTP 429, or 403 with a rate/quota-related reason) - a transient burst (e.g. right after
    creating several new labels) shouldn't abort an entire store-in-gmail run."""
    delay = 1.0
    for attempt in range(1, _GMAIL_STORE_MAX_RETRIES + 1):
        try:
            return func(*args, **kwargs)
        except HttpError as e:
            status = getattr(e.resp, "status", None)
            is_rate_limit = status == 429 or (status == 403 and "rate" in str(e).lower())
            if not is_rate_limit or attempt == _GMAIL_STORE_MAX_RETRIES:
                raise
            logger.info("Gmail rate limit hit, retrying in %.0fs (attempt %d/%d)", delay, attempt, _GMAIL_STORE_MAX_RETRIES)
            time.sleep(delay)
            delay *= 2


def _eml_tree_candidates(eml_paths: list[Path]) -> Iterator[tuple[str | None, Path, bytes, list[str]]]:
    """Yield (msg_id, source_path, raw_bytes, label_names) for each .eml file - msg_id is None
    (candidate excluded by the caller) for a file with no X-Mail-Utils-ID header, i.e. not
    something `mail-utils export --format eml` wrote."""
    for eml_path in eml_paths:
        raw_bytes = eml_path.read_bytes()
        parsed = message_from_bytes(raw_bytes, policy=_email_policy_default)
        msg_id = parsed.get("X-Mail-Utils-ID")
        if not msg_id:
            logger.info("Skipping %s: no X-Mail-Utils-ID header (not a mail-utils export)", eml_path)
            yield None, eml_path, raw_bytes, []
            continue
        labels_header = parsed.get("X-Mail-Utils-Labels")
        label_names = [name.strip() for name in labels_header.split(",")] if labels_header else []
        yield msg_id, eml_path, raw_bytes, label_names


def _db_candidates(conn: sqlite3.Connection) -> Iterator[tuple[str, Path | None, bytes, list[str]]]:
    """Yield (msg_id, None, raw_bytes, label_names) straight from the local database, building the
    same RFC 5322 shape `export --format eml` would have written (via _build_eml_message) without
    needing a prior export step. Ordered by id for deterministic, resumable processing."""
    label_names_by_id = dict(conn.execute("SELECT id, name FROM labels"))
    attachments_by_message: dict[str, list] = {}
    for message_id, filename, mime_type, size in conn.execute(
        "SELECT message_id, filename, mime_type, size FROM attachments ORDER BY message_id"
    ):
        attachments_by_message.setdefault(message_id, []).append({"filename": filename, "mime_type": mime_type, "size": size})

    rows = conn.execute(
        "SELECT id, thread_id, sender, recipient, cc, bcc, subject, date, "
        "internal_date_ms, label_ids, body_text, body_mime_type FROM messages ORDER BY id"
    ).fetchall()

    for (
        msg_id,
        thread_id,
        sender,
        recipient,
        cc,
        bcc,
        subject,
        date,
        internal_date_ms,
        label_ids,
        body_text,
        body_mime_type,
    ) in rows:
        label_names = [label_names_by_id.get(lbl, lbl) for lbl in label_ids.split(",")] if label_ids else []
        msg = _build_eml_message(
            msg_id=msg_id,
            thread_id=thread_id,
            sender=sender,
            recipient=recipient,
            cc=cc,
            bcc=bcc,
            subject=subject,
            date=date,
            internal_date_ms=internal_date_ms,
            labels=label_names,
            body_mime_type=body_mime_type,
            attachments=attachments_by_message.get(msg_id, []),
            body_text=body_text,
        )
        yield msg_id, None, msg.as_bytes(policy=_email_policy_default), label_names


_GMAIL_STORE_RUN_LABEL_KEY = "gmail_store_run_label"


def _get_or_start_gmail_store_run_label(conn: sqlite3.Connection) -> str:
    """Return the tracking-label name for the current in-progress store-in-gmail run, persisted in
    `sync_state` so an interrupted or --max-messages-capped run continues under the *same* label when
    the command is rerun, rather than minting a fresh timestamp every invocation. Only called once a
    run is actually about to store its first message, so a no-op rerun (nothing left to store) never
    creates a label at all."""
    run_label_name = get_sync_state(conn, _GMAIL_STORE_RUN_LABEL_KEY)
    if not run_label_name:
        run_label_name = f"mail-utils-store-in-gmail-{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ')}"
        set_sync_state(conn, _GMAIL_STORE_RUN_LABEL_KEY, run_label_name)
    return run_label_name


def _finish_gmail_store_run(conn: sqlite3.Connection) -> None:
    """Clear the persisted run label once a run has gone through every candidate without being cut
    short by --max-messages, so the *next* invocation starts a fresh run/label instead of continuing
    this (now complete) one."""
    set_sync_state(conn, _GMAIL_STORE_RUN_LABEL_KEY, "")


def _run_store_in_gmail(args: argparse.Namespace) -> None:
    _setup_logging()
    version = _get_version()
    start_time = time.time()
    db_path = _resolve_db_path(args)
    source_dir = Path(args.source_dir) if getattr(args, "source_dir", None) else None
    dry_run = getattr(args, "dry_run", False)
    filter_str = getattr(args, "filter", None)
    max_messages = getattr(args, "max_messages", None)

    logger.info("Mail Utils %s operation started: Store in Gmail", version)
    logger.info("Source:    %s", f"{source_dir} (EML export directory)" if source_dir else f"{db_path} (local database)")
    logger.info("Database:  %s", db_path)
    if filter_str:
        logger.info("Filter:    %s", filter_str)
    if max_messages is not None:
        logger.info("Max:       %d messages this run", max_messages)
    if dry_run:
        logger.info("Dry run:   True (no messages will be stored)")

    if source_dir is not None and not source_dir.is_dir():
        logger.info("Error: Source directory '%s' not found.", source_dir)
        return
    if source_dir is None and not db_path.exists():
        logger.info("No database found at %s", db_path)
        return

    conn = init_db(db_path)
    cur = conn.cursor()

    matching_ids = None
    if filter_str:
        try:
            matching_ids = _compute_matching_ids(cur, filter_str)
        except FilterError as e:
            logger.info("Invalid --filter: %s", e)
            conn.close()
            return
        logger.info("Filter matched %d messages", len(matching_ids))

    if source_dir is not None:
        eml_paths = sorted(source_dir.rglob("*.eml"))
        candidates = _eml_tree_candidates(eml_paths)
        total = len(matching_ids) if matching_ids is not None else len(eml_paths)
    else:
        candidates = _db_candidates(conn)
        (row_count,) = cur.execute("SELECT COUNT(*) FROM messages").fetchone()
        total = len(matching_ids) if matching_ids is not None else row_count

    service = None
    label_cache: dict[str, str] = {}
    run_label_id = None
    if not dry_run:
        creds = get_credentials(STORE_IN_GMAIL_SCOPES)
        service = build_gmail_service(creds)
        label_cache = {lbl["name"]: lbl["id"] for lbl in list_labels(service)}

    count = 0
    skipped = 0
    last_stored_msg_id = None
    last_call_time = 0.0
    hit_max_messages = False
    for msg_id, source_path, raw_bytes, label_names in candidates:
        if msg_id is None:
            skipped += 1
            continue
        if matching_ids is not None and msg_id not in matching_ids:
            continue
        if is_stored_in_gmail(conn, msg_id):
            skipped += 1
            continue
        if max_messages is not None and count >= max_messages:
            hit_max_messages = True
            break

        if dry_run:
            location = source_path if source_path is not None else msg_id
            logger.info("Would store %s with labels: %s", location, ", ".join(label_names) or "(none)")
            count += 1
            last_stored_msg_id = msg_id
        else:
            if run_label_id is None:
                run_label_name = _get_or_start_gmail_store_run_label(conn)
                run_label_id = _resolve_label_ids(service, [run_label_name], label_cache)[0]
                logger.info("Tracking label: %s", run_label_name)
            label_ids = _resolve_label_ids(service, label_names, label_cache)
            if run_label_id not in label_ids:
                label_ids = [*label_ids, run_label_id]
            last_call_time = _throttle_gmail_store(last_call_time)
            result = _gmail_call_with_backoff(import_message, service, raw_bytes, label_ids=label_ids)
            mark_stored_in_gmail(conn, msg_id, result.get("id"))
            count += 1
            last_stored_msg_id = msg_id
            logger.info("Stored %s as Gmail message %s", msg_id, result.get("id"))

        if (count + skipped) % PROGRESS_LOG_INTERVAL == 0:
            elapsed = time.time() - start_time
            pct = (100.0 * (count + skipped) / total) if total else 0
            logger.info("Store progress: %d/%d messages (%.1f%% - elapsed: %.1fs)", count + skipped, total, pct, elapsed)

    if not dry_run and not hit_max_messages:
        _finish_gmail_store_run(conn)

    conn.close()
    elapsed = time.time() - start_time
    if hit_max_messages:
        logger.info("Stopped after reaching --max-messages %d - rerun the same command to continue.", max_messages)
    logger.info(
        "Mail Utils %s operation ended in %.1fs: %d messages stored, %d skipped, last message stored: %s",
        version,
        elapsed,
        count,
        skipped,
        last_stored_msg_id or "none",
    )


def _detect_file_format(path: Path) -> str:
    """Identify the email/archive file format of a given path.

    Returns: 'pst', 'thunderbird_pcv', 'thunderbird_profile', 'eml', 'msg', 'mbox', or 'unknown'.
    """
    if path.is_dir():
        if (path / "Mail").exists() or (path / "ImapMail").exists() or (path / "prefs.js").exists():
            return "thunderbird_profile"
        try:
            for child in path.iterdir():
                if child.suffix == ".sbd" or child.name in ("Mail", "ImapMail", "prefs.js"):
                    return "thunderbird_profile"
        except OSError:
            pass
        return "unknown"

    if not path.is_file():
        return "unknown"

    suffix = path.suffix.lower()

    # 1. Check Outlook PST
    if suffix == ".pst":
        return "pst"
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
            if magic == b"!BDN":
                return "pst"
    except OSError:
        pass

    # 2. Check Thunderbird PCV / ZIP
    if suffix in (".pcv", ".zip") or zipfile.is_zipfile(path):
        try:
            with zipfile.ZipFile(path, "r") as zf:
                names = zf.namelist()
                if any(n.startswith(("Mail/", "ImapMail/")) or n.endswith(".sbd") or n == "prefs.js" for n in names):
                    return "thunderbird_pcv"
        except (zipfile.BadZipFile, OSError):
            pass

    # 3. Known unsupported single-message / standalone formats
    if suffix == ".eml":
        return "eml"
    if suffix == ".msg":
        return "msg"
    if suffix == ".mbox":
        return "mbox"

    return "unknown"


def _run_import(args: argparse.Namespace) -> None:
    source_path = getattr(args, "source_path", None)

    # When no source path is specified, try Gmail import if credentials exist
    if not source_path:
        if CREDENTIALS_PATH.exists() or TOKEN_PATH.exists():
            _run_import_gmail(args)
            return

        _setup_logging()
        logger.info(
            "Error: No import file specified and Gmail credentials not found at %s.\n"
            "Provide an archive path (e.g. 'mail-utils import archive.pst') or set up Gmail credentials for 'mail-utils import-gmail'.",
            CREDENTIALS_PATH,
        )
        return

    path = Path(source_path)
    if not path.exists():
        _setup_logging()
        logger.info("Error: Import source '%s' not found.", source_path)
        return

    fmt = _detect_file_format(path)

    if fmt == "pst":
        args.pst_path = str(path)
        _run_import_pst(args)
    elif fmt in ("thunderbird_pcv", "thunderbird_profile"):
        args.archive_path = str(path)
        _run_import_thunderbird(args)
    elif fmt == "eml":
        _setup_logging()
        logger.info(
            "Error: Direct import of single EML message '%s' is not supported. "
            "Supported formats: Outlook PST (*.pst), Thunderbird archive (*.pcv, *.zip, profile folder), or Gmail API.",
            path.name,
        )
    elif fmt == "msg":
        _setup_logging()
        logger.info(
            "Error: Direct import of single Outlook MSG file '%s' is not supported. "
            "Supported formats: Outlook PST (*.pst), Thunderbird archive (*.pcv, *.zip, profile folder), or Gmail API.",
            path.name,
        )
    elif fmt == "mbox":
        _setup_logging()
        logger.info(
            "Error: Direct import of standalone Mbox file '%s' is not supported. "
            "Supported formats: Outlook PST (*.pst), Thunderbird archive (*.pcv, *.zip, profile folder), or Gmail API.",
            path.name,
        )
    else:
        _setup_logging()
        logger.info(
            "Error: Unsupported file format for '%s'. "
            "Supported formats: Outlook PST (*.pst), Thunderbird archive (*.pcv, *.zip, profile directory), or Gmail API (when no file is specified).",
            path.name,
        )


def _run_import_pst(args: argparse.Namespace) -> None:
    _setup_logging()
    version = _get_version()
    start_time = time.time()
    db_path = _resolve_db_path(args)
    recursive = getattr(args, "recursive", False)

    logger.info("Mail Utils %s operation started: Outlook PST import", version)
    logger.info("Source:    %s", args.pst_path)
    logger.info("Database:  %s", db_path)
    if recursive:
        logger.info("Recursive: True")

    conn = init_db(db_path)

    with PSTFile(args.pst_path) as pst:
        folders = walk_folders(pst)
        upsert_labels(conn, labels_for_folders(folders))
        total_messages = sum(len(f.message_nids) for f in folders)

        count = 0
        for folder in folders:
            label_id = folder_label_id(folder.path) if folder.path else None
            for msg_nid in folder.message_nids:
                raw = pst_fetch_message(pst, msg_nid)
                parsed = pst_parse_message(raw, label_id=label_id)
                upsert_message(conn, parsed)
                upsert_addresses(conn, parsed["id"], pst_parse_addresses(raw))
                upsert_attachments(conn, parsed["id"], pst_parse_attachments(raw))
                count += 1
                if count % PROGRESS_LOG_INTERVAL == 0:
                    elapsed = time.time() - start_time
                    pct = (100.0 * count / total_messages) if total_messages else 0
                    logger.info(
                        "PST import progress: %d/%d messages (%.1f%% - elapsed: %.1fs)",
                        count,
                        total_messages,
                        pct,
                        elapsed,
                    )

    conn.close()
    elapsed = time.time() - start_time
    logger.info("Mail Utils %s operation ended in %.1fs: %d messages indexed", version, elapsed, count)


def _process_tb_message(conn, raw_msg, label_id, recursive: bool) -> int:
    parsed = tb_parse_message(raw_msg, label_id=label_id)
    upsert_message(conn, parsed)
    upsert_addresses(conn, parsed["id"], tb_parse_addresses(raw_msg))
    upsert_attachments(conn, parsed["id"], tb_parse_attachments(raw_msg))
    count = 1
    if recursive:
        for sub in tb_extract_attached_messages(raw_msg):
            count += _process_tb_message(conn, sub, label_id, recursive=True)
    return count


def _run_import_thunderbird(args: argparse.Namespace) -> None:
    _setup_logging()
    version = _get_version()
    start_time = time.time()
    db_path = _resolve_db_path(args)
    recursive = getattr(args, "recursive", False)

    logger.info("Mail Utils %s operation started: Thunderbird archive import", version)
    logger.info("Source:    %s", args.archive_path)
    logger.info("Database:  %s", db_path)
    if recursive:
        logger.info("Recursive: True")

    conn = init_db(db_path)

    source_path = Path(args.archive_path)
    folders = tb_walk_folders(source_path)
    upsert_labels(conn, tb_labels_for_folders(folders))

    count = 0
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        for folder in folders:
            if folder.file_size == 0 and source_path.is_file():
                continue
            label_id = tb_folder_label_id(folder.path) if folder.path else None
            temp_mbox = tmp_dir_path / "current.mbox"
            extract_mbox_to_file(source_path, folder, temp_mbox)
            box = mailbox.mbox(temp_mbox)
            try:
                for raw_msg in box:
                    count += _process_tb_message(conn, raw_msg, label_id, recursive)
                    if count % PROGRESS_LOG_INTERVAL == 0:
                        elapsed = time.time() - start_time
                        logger.info("Thunderbird import progress: %d messages indexed (elapsed: %.1fs)", count, elapsed)
            finally:
                box.close()
                if temp_mbox.exists():
                    temp_mbox.unlink()

    conn.close()
    elapsed = time.time() - start_time
    logger.info("Mail Utils %s operation ended in %.1fs: %d messages indexed", version, elapsed, count)


def _format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024


def _load_filter_context(cur: sqlite3.Cursor):
    """Load the per-message data message_matches() needs: resolved label
    names, addresses grouped by (message_id, role), and which messages
    have at least one attachment. Missing tables (old database, never
    synced with the current code) degrade to empty - those tokens then
    just never match, rather than erroring."""
    try:
        label_names = dict(cur.execute("SELECT id, name FROM labels"))
    except sqlite3.OperationalError:
        label_names = {}

    addresses_by_message = {}
    try:
        for message_id, role, address, name in cur.execute("SELECT message_id, role, address, name FROM message_addresses"):
            addresses_by_message.setdefault(message_id, {}).setdefault(role, []).append((address, name))
    except sqlite3.OperationalError:
        pass

    try:
        attachment_message_ids = {row[0] for row in cur.execute("SELECT DISTINCT message_id FROM attachments")}
    except sqlite3.OperationalError:
        attachment_message_ids = set()

    return label_names, addresses_by_message, attachment_message_ids


def _compute_matching_ids(cur: sqlite3.Cursor, filter_str: str) -> set:
    tokens = parse_filter(filter_str)
    label_names, addresses_by_message, attachment_message_ids = _load_filter_context(cur)

    matching = set()
    for msg_id, subject, body_text, label_ids, internal_date_ms in cur.execute(
        "SELECT id, subject, body_text, label_ids, internal_date_ms FROM messages"
    ):
        labels = [label_names.get(lbl, lbl) for lbl in label_ids.split(",")] if label_ids else []
        if message_matches(
            tokens,
            labels=labels,
            addresses=addresses_by_message.get(msg_id, {}),
            has_attachment=msg_id in attachment_message_ids,
            internal_date_ms=internal_date_ms,
            subject=subject,
            body_text=body_text,
        ):
            matching.add(msg_id)
    return matching


def _create_filtered_ids_table(conn: sqlite3.Connection, matching_ids: set) -> None:
    conn.execute("CREATE TEMP TABLE filtered_ids (id TEXT PRIMARY KEY)")
    conn.executemany("INSERT INTO filtered_ids (id) VALUES (?)", [(i,) for i in matching_ids])


def _run_stats(args: argparse.Namespace) -> None:
    _setup_logging()
    version = _get_version()
    start_time = time.time()
    db_path = _resolve_db_path(args)
    if not db_path.exists():
        logger.info("No database found at %s", db_path)
        return

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    logger.info("Mail Utils %s operation started: Database stats", version)
    logger.info("Database: %s", db_path)

    filter_str = getattr(args, "filter", None)
    if filter_str:
        try:
            matching_ids = _compute_matching_ids(cur, filter_str)
        except FilterError as e:
            logger.info("Invalid --filter: %s", e)
            conn.close()
            return
        _create_filtered_ids_table(conn, matching_ids)
        msg_join = "JOIN filtered_ids f ON f.id = messages.id"
        addr_join = "JOIN filtered_ids f ON f.id = message_addresses.message_id"
        att_join = "JOIN filtered_ids f ON f.id = attachments.message_id"
        logger.info("Filter:   %r (%d matching messages)", filter_str, len(matching_ids))
    else:
        msg_join = addr_join = att_join = ""

    logger.info("")

    (total,) = cur.execute(f"SELECT COUNT(*) FROM messages {msg_join}").fetchone()
    (threads,) = cur.execute(f"SELECT COUNT(DISTINCT thread_id) FROM messages {msg_join}").fetchone()
    first_fetched, last_fetched = cur.execute(f"SELECT MIN(fetched_at), MAX(fetched_at) FROM messages {msg_join}").fetchone()
    row = cur.execute("SELECT value FROM sync_state WHERE key = 'last_history_id'").fetchone()
    last_history_id = row[0] if row else None

    fields = [
        ("Total messages", total),
        ("Distinct threads", threads),
        ("First indexed", first_fetched),
        ("Last indexed", last_fetched),
        ("Last history ID", last_history_id),
    ]
    key_width = max(len(key) for key, _ in fields)
    for key, value in fields:
        logger.info(f"{key + ':':<{key_width + 1}} {value}")

    try:
        label_names = dict(cur.execute("SELECT id, name FROM labels"))
    except sqlite3.OperationalError:
        label_names = {}

    label_counts = Counter()
    for (label_ids,) in cur.execute(f"SELECT label_ids FROM messages {msg_join} WHERE label_ids != ''"):
        label_counts.update(label_ids.split(","))

    try:
        cur.execute("SELECT 1 FROM message_addresses LIMIT 1")
        has_addresses = True
    except sqlite3.OperationalError:
        has_addresses = False

    sections = []
    if label_counts:
        top = label_counts.most_common(15)
        resolved = [(label_names.get(label_id, label_id), count) for label_id, count in top]
        sections.append(("Top labels", resolved))

    if has_addresses:
        for role, title in (
            ("from", "Top senders"),
            ("to", "Top To recipients"),
            ("cc", "Top Cc recipients"),
            ("bcc", "Top Bcc recipients"),
        ):
            rows = cur.execute(
                f"SELECT address, MAX(name) AS name, COUNT(*) AS n FROM message_addresses {addr_join} "
                "WHERE role = ? GROUP BY address ORDER BY n DESC LIMIT 15",
                (role,),
            ).fetchall()
            if not rows:
                continue
            labeled = [(f"{name} <{address}>" if name else address, n) for address, name, n in rows]
            sections.append((title, labeled))

    if sections:
        # One global width across every section, so the value columns line up down the whole printed page.
        name_width = max(len(name) for _, rows in sections for name, _ in rows)
        for title, rows in sections:
            logger.info(f"\n{title}:")
            for name, count in rows:
                logger.info(f"  {name:<{name_width}} {count:>6}")

    if label_counts and not label_names:
        logger.info("\n(Label names unavailable - run a sync with the current code at least once to populate the labels table.)")

    if not has_addresses:
        logger.info(
            "\n(Recipient stats unavailable - run a sync with the current "
            "code at least once to populate the message_addresses table.)"
        )

    try:
        att_count, att_size = cur.execute(f"SELECT COUNT(*), COALESCE(SUM(size), 0) FROM attachments {att_join}").fetchone()
        logger.info(f"\nAttachments: {att_count} total, {_format_size(att_size)}")
    except sqlite3.OperationalError:
        logger.info(
            "\n(Attachment stats unavailable - run a sync with the current code at least once to populate the attachments table.)"
        )

    conn.close()
    elapsed = time.time() - start_time
    logger.info("\nMail Utils %s operation ended in %.2fs: %d total messages reported", version, elapsed, total)


def _safe_export_filename(msg_id: str) -> str:
    cleaned = re.sub(r'[/\\:*?"<>|]', "_", msg_id)
    return cleaned if len(cleaned) <= 120 else hashlib.sha256(msg_id.encode("utf-8")).hexdigest()


EXPORT_PROGRESS_INTERVAL = 50


def _export_message_md(
    target_file: Path,
    *,
    msg_id: str,
    thread_id: str | None,
    sender: str | None,
    recipient: str | None,
    cc: str | None,
    bcc: str | None,
    subject: str | None,
    date: str | None,
    internal_date_iso: str | None,
    labels: list,
    body_mime_type: str | None,
    attachments: list,
    body_text: str | None,
) -> None:
    frontmatter = {
        "id": msg_id,
        "thread_id": thread_id,
        "date": date,
        "internal_date": internal_date_iso,
        "from": sender,
        "to": recipient,
        "cc": cc,
        "bcc": bcc,
        "subject": subject,
        "labels": labels,
        "body_mime_type": body_mime_type,
        "attachments": attachments,
    }
    frontmatter = {k: v for k, v in frontmatter.items() if v not in (None, [], "")}
    yaml_header = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
    content = f"---\n{yaml_header}---\n\n{body_text or ''}\n"
    target_file.write_text(content, encoding="utf-8")


def _build_eml_message(
    *,
    msg_id: str,
    thread_id: str | None,
    sender: str | None,
    recipient: str | None,
    cc: str | None,
    bcc: str | None,
    subject: str | None,
    date: str | None,
    internal_date_ms: int | None,
    labels: list,
    body_mime_type: str | None,
    attachments: list,
    body_text: str | None,
) -> EmailMessage:
    """Build the same standard RFC 5322 message `export --format eml` writes to disk - also used
    to build store-in-gmail's database-source candidates on the fly, so a database-sourced store
    produces byte-for-byte the same message shape as storing a previously exported .eml file."""
    msg = EmailMessage()
    if subject:
        msg["Subject"] = subject
    if sender:
        msg["From"] = sender
    if recipient:
        msg["To"] = recipient
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    if date:
        msg["Date"] = date
    elif internal_date_ms:
        dt = datetime.fromtimestamp(internal_date_ms / 1000, tz=timezone.utc)
        msg["Date"] = format_datetime(dt)

    msg["X-Mail-Utils-ID"] = msg_id
    if thread_id:
        msg["X-Mail-Utils-Thread-ID"] = thread_id
    if labels:
        msg["X-Mail-Utils-Labels"] = ", ".join(labels)
    if attachments:
        for att in attachments:
            att_desc = att.get("filename", "")
            mime = att.get("mime_type")
            size = att.get("size")
            meta = []
            if mime:
                meta.append(f"type={mime}")
            if size is not None:
                meta.append(f"size={size}")
            if meta:
                att_desc += f" ({'; '.join(meta)})"
            msg["X-Mail-Utils-Attachment"] = att_desc

    if body_mime_type == "text/html":
        msg.set_content(body_text or "", subtype="html", charset="utf-8")
    else:
        msg.set_content(body_text or "", subtype="plain", charset="utf-8")
    return msg


def _export_message_eml(
    target_file: Path,
    *,
    msg_id: str,
    thread_id: str | None,
    sender: str | None,
    recipient: str | None,
    cc: str | None,
    bcc: str | None,
    subject: str | None,
    date: str | None,
    internal_date_ms: int | None,
    labels: list,
    body_mime_type: str | None,
    attachments: list,
    body_text: str | None,
) -> None:
    msg = _build_eml_message(
        msg_id=msg_id,
        thread_id=thread_id,
        sender=sender,
        recipient=recipient,
        cc=cc,
        bcc=bcc,
        subject=subject,
        date=date,
        internal_date_ms=internal_date_ms,
        labels=labels,
        body_mime_type=body_mime_type,
        attachments=attachments,
        body_text=body_text,
    )

    target_file.write_bytes(msg.as_bytes(policy=_email_policy_default))


def _run_export(args: argparse.Namespace) -> None:
    _setup_logging()
    version = _get_version()
    start_time = time.time()
    db_path = _resolve_db_path(args)
    if not db_path.exists():
        logger.info("No database found at %s", db_path)
        return

    output_dir = Path(args.output_dir)
    export_format = getattr(args, "format", "md") or "md"

    logger.info("Mail Utils %s operation started: Message export", version)
    logger.info("Database:         %s", db_path)
    logger.info("Output directory: %s", output_dir)
    logger.info("Format:           %s", export_format)

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    filter_str = getattr(args, "filter", None)
    matching_ids = None
    if filter_str:
        try:
            matching_ids = _compute_matching_ids(cur, filter_str)
        except FilterError as e:
            logger.info("Invalid --filter: %s", e)
            conn.close()
            return
        logger.info("Filter:           %r (%d matching messages)", filter_str, len(matching_ids))

    label_names = dict(cur.execute("SELECT id, name FROM labels"))

    attachments_by_message = {}
    for message_id, filename, mime_type, size in cur.execute(
        "SELECT message_id, filename, mime_type, size FROM attachments ORDER BY message_id"
    ):
        attachments_by_message.setdefault(message_id, []).append({"filename": filename, "mime_type": mime_type, "size": size})

    rows = cur.execute(
        "SELECT id, thread_id, sender, recipient, cc, bcc, subject, date, "
        "internal_date_ms, label_ids, body_text, body_mime_type FROM messages"
    ).fetchall()
    conn.close()

    total_to_export = len(matching_ids) if matching_ids is not None else len(rows)
    count = 0
    for (
        msg_id,
        thread_id,
        sender,
        recipient,
        cc,
        bcc,
        subject,
        date,
        internal_date_ms,
        label_ids,
        body_text,
        body_mime_type,
    ) in rows:
        if matching_ids is not None and msg_id not in matching_ids:
            continue
        if internal_date_ms:
            dt = datetime.fromtimestamp(internal_date_ms / 1000, tz=timezone.utc)
            subdir = output_dir / f"{dt.year:04d}" / f"{dt.month:02d}"
            internal_date_iso = dt.isoformat()
        else:
            subdir = output_dir / "unknown"
            internal_date_iso = None
        subdir.mkdir(parents=True, exist_ok=True)

        labels = [label_names.get(lbl, lbl) for lbl in label_ids.split(",")] if label_ids else []
        stem = _safe_export_filename(msg_id)

        if export_format == "eml":
            _export_message_eml(
                subdir / f"{stem}.eml",
                msg_id=msg_id,
                thread_id=thread_id,
                sender=sender,
                recipient=recipient,
                cc=cc,
                bcc=bcc,
                subject=subject,
                date=date,
                internal_date_ms=internal_date_ms,
                labels=labels,
                body_mime_type=body_mime_type,
                attachments=attachments_by_message.get(msg_id, []),
                body_text=body_text,
            )
        else:
            _export_message_md(
                subdir / f"{stem}.md",
                msg_id=msg_id,
                thread_id=thread_id,
                sender=sender,
                recipient=recipient,
                cc=cc,
                bcc=bcc,
                subject=subject,
                date=date,
                internal_date_iso=internal_date_iso,
                labels=labels,
                body_mime_type=body_mime_type,
                attachments=attachments_by_message.get(msg_id, []),
                body_text=body_text,
            )

        count += 1
        if count % EXPORT_PROGRESS_INTERVAL == 0:
            elapsed = time.time() - start_time
            pct = (100.0 * count / total_to_export) if total_to_export else 0
            logger.info("Export progress: %d/%d messages (%.1f%% - elapsed: %.1fs)", count, total_to_export, pct, elapsed)

    elapsed = time.time() - start_time
    logger.info("Mail Utils %s operation ended in %.1fs: %d messages exported to %s", version, elapsed, count, output_dir)


def _sanitize_fts_query(query: str) -> str:
    words = query.strip().split()
    tokens = []
    for w in words:
        if w.upper() in ("AND", "OR", "NOT"):
            tokens.append(w.upper())
        else:
            clean = w.replace('"', '""')
            tokens.append(f'"{clean}"')
    return " ".join(tokens)


def _run_search(args: argparse.Namespace) -> None:
    _setup_logging()
    version = _get_version()
    start_time = time.time()
    db_path = _resolve_db_path(args)
    if not db_path.exists():
        logger.info("No database found at %s", db_path)
        return

    logger.info("Mail Utils %s operation started: Full-text search", version)
    logger.info("Query:    %r", args.query)
    logger.info("Database: %s", db_path)
    limit = getattr(args, "limit", 20) or 20
    logger.info("Limit:    %d\n", limit)

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    query_str = args.query.strip()
    try:
        cur.execute(
            """
            SELECT
                m.id,
                m.sender,
                m.recipient,
                m.subject,
                m.date,
                m.internal_date_ms,
                snippet(messages_fts, 1, '«', '»', '...', 15) AS subject_snippet,
                snippet(messages_fts, 2, '«', '»', '...', 25) AS body_snippet,
                bm25(messages_fts) AS rank
            FROM messages_fts f
            JOIN messages m ON m.id = f.id
            WHERE messages_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query_str, limit),
        )
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        sanitized = _sanitize_fts_query(query_str)
        try:
            cur.execute(
                """
                SELECT
                    m.id,
                    m.sender,
                    m.recipient,
                    m.subject,
                    m.date,
                    m.internal_date_ms,
                    snippet(messages_fts, 1, '«', '»', '...', 15) AS subject_snippet,
                    snippet(messages_fts, 2, '«', '»', '...', 25) AS body_snippet,
                    bm25(messages_fts) AS rank
                FROM messages_fts f
                JOIN messages m ON m.id = f.id
                WHERE messages_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (sanitized, limit),
            )
            rows = cur.fetchall()
        except sqlite3.OperationalError as e:
            logger.info("Search query error: %s", e)
            conn.close()
            return

    count = len(rows)
    if not rows:
        logger.info("No matching messages found.")
    else:
        for idx, (msg_id, sender, recipient, subject, date_str, internal_date_ms, subj_snip, body_snip, rank) in enumerate(rows, 1):
            date_display = date_str
            if internal_date_ms:
                dt = datetime.fromtimestamp(internal_date_ms / 1000, tz=timezone.utc)
                date_display = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            logger.info(f"[{idx}] {date_display or 'Unknown date'} | {msg_id}")
            if sender:
                logger.info(f"    From:    {sender}")
            if recipient:
                logger.info(f"    To:      {recipient}")
            logger.info(f"    Subject: {subj_snip or subject or '(No Subject)'}")
            if body_snip:
                logger.info(f"    Snippet: {body_snip}")
            logger.info("")

    conn.close()
    elapsed = time.time() - start_time
    logger.info("Mail Utils %s operation ended in %.2fs: %d matching messages found", version, elapsed, count)


def _validate_inner_command(command: list) -> None:
    if not command:
        raise ScheduleError(
            "No command given - e.g. 'mail-utils schedule -- import' or 'mail-utils schedule -- export /path/to/export'."
        )
    if command[0] not in ALLOWED_COMMANDS:
        raise ScheduleError(f"Can only schedule {' or '.join(ALLOWED_COMMANDS)}, not {command[0]!r}.")
    try:
        build_parser().parse_args(command)
    except SystemExit:
        raise ScheduleError(f"Invalid command {' '.join(command)!r} - check it against 'mail-utils {command[0]} --help'.")


def _run_schedule(args: argparse.Namespace) -> None:
    _setup_logging()
    version = _get_version()
    start_time = time.time()
    system = platform.system()

    if args.list:
        logger.info("Mail Utils %s operation started: List scheduled tasks", version)
        if system == "Windows":
            output = list_windows_jobs()
            logger.info(output or "No mail-utils scheduled tasks found.")
        elif system in ("Linux", "Darwin"):
            jobs = list_cron_jobs()
            if not jobs:
                logger.info("No mail-utils crontab entries found.")
            for name, command_str in jobs:
                logger.info("%s: %s", name, command_str)
        else:
            logger.info("Unsupported platform: %s", system)
        elapsed = time.time() - start_time
        logger.info("Mail Utils %s operation ended in %.2fs: listing complete", version, elapsed)
        return

    command = list(args.inner_command)
    if command and command[0] == "--":
        command = command[1:]

    logger.info("Mail Utils %s operation started: Register scheduled task", version)
    logger.info("Job name: %s", args.job_name)
    logger.info("Interval: %d minutes", args.interval_minutes)
    logger.info("Command:  %s", " ".join(command))

    try:
        _validate_inner_command(command)
    except ScheduleError as e:
        logger.info("Error: %s", e)
        return

    python_exe = sys.executable

    try:
        if system == "Windows":
            schedule_windows(args.job_name, args.interval_minutes, python_exe, BASE_DIR, command)
            task_name = windows_task_name(args.job_name)
            logger.info(
                "Registered Windows Scheduled Task %r (every %d min): %s",
                task_name,
                args.interval_minutes,
                " ".join(command),
            )
            elapsed = time.time() - start_time
            logger.info("Mail Utils %s operation ended in %.2fs: task %r registered", version, elapsed, task_name)
        elif system in ("Linux", "Darwin"):
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            line = schedule_cron(args.job_name, args.interval_minutes, python_exe, BASE_DIR, LOG_DIR / "cron.log", command)
            logger.info("Added crontab entry for job %r:\n  %s", args.job_name, line)
            elapsed = time.time() - start_time
            logger.info("Mail Utils %s operation ended in %.2fs: job %r registered", version, elapsed, args.job_name)
        else:
            logger.info("Unsupported platform: %s. Only Windows and Linux/macOS are supported.", system)
    except ScheduleError as e:
        logger.info("Error: %s", e)


def _run_unschedule(args: argparse.Namespace) -> None:
    _setup_logging()
    version = _get_version()
    start_time = time.time()
    system = platform.system()
    logger.info("Mail Utils %s operation started: Unregister scheduled task", version)
    logger.info("Job name: %s", args.job_name)

    try:
        if system == "Windows":
            unschedule_windows(args.job_name)
            task_name = windows_task_name(args.job_name)
            logger.info("Removed Windows Scheduled Task %r (if it existed).", task_name)
            elapsed = time.time() - start_time
            logger.info("Mail Utils %s operation ended in %.2fs: task %r removed", version, elapsed, task_name)
        elif system in ("Linux", "Darwin"):
            removed = unschedule_cron(args.job_name)
            logger.info("%s crontab entry for job %r.", "Removed" if removed else "No", args.job_name)
            elapsed = time.time() - start_time
            logger.info("Mail Utils %s operation ended in %.2fs: job %r removed", version, elapsed, args.job_name)
        else:
            logger.info("Unsupported platform: %s", system)
    except ScheduleError as e:
        logger.info("Error: %s", e)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mail-utils",
        description="A lightweight, privacy-preserving, local email archive indexing and extraction utility.",
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="store_true", help="Show this help message and exit")
    parser.add_argument("--version", action="store_true", help="Show version and exit")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="With --version, also print the matching CHANGELOG.md entry; with help (or no command), "
        "also print full --help for every subcommand",
    )
    subparsers = parser.add_subparsers(dest="command")

    subcommand_parsers = {}

    help_cmd = subparsers.add_parser("help", help="Show this help message and exit", add_help=False)
    help_cmd.add_argument("-h", "--help", action="store_true", help="Show this help message and exit")
    help_cmd.add_argument("--verbose", action="store_true", help="Also print full --help for every subcommand")
    help_cmd.add_argument("subcommand", nargs="?", default=None, help="Optional subcommand to show help for")
    subcommand_parsers["help"] = help_cmd

    version_cmd = subparsers.add_parser("version", help="Show version and exit (same as --version)", add_help=False)
    version_cmd.add_argument("-h", "--help", action="store_true", help="Show this help message and exit")
    version_cmd.add_argument("--verbose", action="store_true", help="Also print the matching CHANGELOG.md entry")
    subcommand_parsers["version"] = version_cmd

    filter_help = (
        "Gmail-style filter, e.g. 'label:Work from:jane after:2026/01/01 has:attachment'. "
        "Supported: label:, from:, to:, cc:, bcc:, subject:, after:YYYY/MM/DD, before:YYYY/MM/DD, "
        'has:attachment, and bare words/"quoted phrases" (subject+body substring).'
    )

    db_help = "Path to the SQLite database (default: gmail_index.db in the project root)."

    import_cmd = subparsers.add_parser(
        "import",
        help="Import mail from an archive file/directory, or from Gmail if no file is provided",
    )
    import_cmd.add_argument(
        "source_path",
        nargs="?",
        default=None,
        help="Path to Outlook .pst archive, Thunderbird .pcv/.zip archive, or profile directory (omit to import from Gmail)",
    )
    import_cmd.add_argument(
        "--filter",
        help=filter_help + " When importing from Gmail, passed through to search; forces full sync.",
    )
    import_cmd.add_argument(
        "-r", "--recursive", action="store_true", help="Recursively import messages attached to incoming emails"
    )
    import_cmd.add_argument("--db", help=db_help)
    import_cmd.set_defaults(func=_run_import)
    subcommand_parsers["import"] = import_cmd

    import_gmail_cmd = subparsers.add_parser("import-gmail", help="Import new mail from Gmail via the Gmail API")
    import_gmail_cmd.add_argument(
        "--filter",
        help=filter_help + " Passed straight through to Gmail's own search; forces a filtered full "
        "listing instead of incremental sync, and does not update sync_state.",
    )
    import_gmail_cmd.add_argument(
        "-r", "--recursive", action="store_true", help="Recursively import messages attached to incoming emails"
    )
    import_gmail_cmd.add_argument("--db", help=db_help)
    import_gmail_cmd.set_defaults(func=_run_import_gmail)
    subcommand_parsers["import-gmail"] = import_gmail_cmd

    import_pst_cmd = subparsers.add_parser(
        "import-pst",
        aliases=["import-outlook"],
        help="Import an Outlook .pst archive's messages into the local database",
    )
    import_pst_cmd.add_argument("pst_path", help="Path to the .pst file to import")
    import_pst_cmd.add_argument(
        "-r", "--recursive", action="store_true", help="Recursively import messages attached to incoming emails"
    )
    import_pst_cmd.add_argument("--db", help=db_help)
    import_pst_cmd.set_defaults(func=_run_import_pst)
    subcommand_parsers["import-pst"] = import_pst_cmd
    subcommand_parsers["import-outlook"] = import_pst_cmd

    import_tb_cmd = subparsers.add_parser(
        "import-thunderbird",
        aliases=["import-pcv"],
        help="Import a Mozilla Thunderbird archive (.pcv, .zip, or profile folder) into the local database",
    )
    import_tb_cmd.add_argument("archive_path", help="Path to the .pcv/.zip archive or Thunderbird profile directory to import")
    import_tb_cmd.add_argument(
        "-r", "--recursive", action="store_true", help="Recursively import messages attached to incoming emails"
    )
    import_tb_cmd.add_argument("--db", help=db_help)
    import_tb_cmd.set_defaults(func=_run_import_thunderbird)
    subcommand_parsers["import-thunderbird"] = import_tb_cmd
    subcommand_parsers["import-pcv"] = import_tb_cmd

    store_in_gmail_cmd = subparsers.add_parser(
        "store-in-gmail",
        help="Store previously-exported (or already-indexed) mail into a live Gmail mailbox (requests write-capable scopes)",
    )
    store_in_gmail_cmd.add_argument(
        "source_dir",
        nargs="?",
        default=None,
        help="Directory of .eml files to store, e.g. output of 'mail-utils export --format eml' "
        "(omit to store directly from the local database instead)",
    )
    store_in_gmail_cmd.add_argument("--filter", help=filter_help + " Evaluated locally against the database.")
    store_in_gmail_cmd.add_argument(
        "--max-messages", type=int, help="Store at most this many messages this run; rerun the same command to continue"
    )
    store_in_gmail_cmd.add_argument(
        "--dry-run", action="store_true", help="Report what would be stored without contacting Gmail or requesting credentials"
    )
    store_in_gmail_cmd.add_argument("--db", help=db_help)
    store_in_gmail_cmd.set_defaults(func=_run_store_in_gmail)
    subcommand_parsers["store-in-gmail"] = store_in_gmail_cmd

    search_cmd = subparsers.add_parser("search", help="Full-text search indexed messages using SQLite FTS5")
    search_cmd.add_argument("query", help="Search query (supports boolean operators AND, OR, NOT, and prefix queries)")
    search_cmd.add_argument("-n", "--limit", type=int, default=20, help="Maximum number of search results to return (default: 20)")
    search_cmd.add_argument("--db", help=db_help)
    search_cmd.set_defaults(func=_run_search)
    subcommand_parsers["search"] = search_cmd

    stats = subparsers.add_parser("stats", help="Print summary stats from the local database")
    stats.add_argument("--filter", help=filter_help + " Evaluated locally against the database.")
    stats.add_argument("--db", help=db_help)
    stats.set_defaults(func=_run_stats)
    subcommand_parsers["stats"] = stats

    export = subparsers.add_parser("export", help="Export all messages as markdown or EML files")
    export.add_argument("output_dir", help="Directory to write exported files into (created if missing)")
    export.add_argument(
        "--format",
        "-f",
        choices=["md", "eml"],
        default="md",
        help="Export format: 'md' (Markdown with YAML frontmatter, default) or 'eml' (standard RFC 5322 MIME format)",
    )
    export.add_argument("--filter", help=filter_help + " Evaluated locally against the database.")
    export.add_argument("--db", help=db_help)
    export.set_defaults(func=_run_export)
    subcommand_parsers["export"] = export

    schedule_cmd = subparsers.add_parser(
        "schedule", help="Register a recurring mail-utils command (Windows Task Scheduler or cron)"
    )
    schedule_cmd.add_argument("--job-name", default="default", help="Identifies this job (default: 'default')")
    schedule_cmd.add_argument("--interval-minutes", type=int, default=30, help="How often to run, in minutes (default: 30)")
    schedule_cmd.add_argument("--list", action="store_true", help="List currently scheduled jobs instead of registering a new one")
    schedule_cmd.add_argument(
        "inner_command",
        nargs=argparse.REMAINDER,
        help="The command to schedule: 'import [...]' or 'export <output_dir> [...]'. Put -- before it if it "
        "has flags of its own, e.g.: mail-utils schedule --job-name work -- import --filter 'label:Work'",
    )
    schedule_cmd.set_defaults(func=_run_schedule)
    subcommand_parsers["schedule"] = schedule_cmd

    unschedule_cmd = subparsers.add_parser("unschedule", help="Remove a job registered by 'schedule'")
    unschedule_cmd.add_argument("--job-name", default="default", help="Which job to remove (default: 'default')")
    unschedule_cmd.set_defaults(func=_run_unschedule)
    subcommand_parsers["unschedule"] = unschedule_cmd

    parser._subcommand_parsers = subcommand_parsers
    return parser


def _find_release_entry(version: str) -> str | None:
    """Return the CHANGELOG.md section for the given version (heading through the next '## ' heading), or None."""
    path = BASE_DIR / "CHANGELOG.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    marker = f"## v{version}"
    start = text.find(marker)
    if start == -1:
        return None
    rest = text[start:]
    next_heading = rest.find("\n## ", 1)
    entry = rest if next_heading == -1 else rest[:next_heading]
    return entry.strip()


def _print_version(verbose: bool = False) -> None:
    ver = _get_version()
    print(f"mail-utils v{ver} - Copyright (c) Giovanni Pellicciotta")
    if verbose:
        entry = _find_release_entry(ver)
        if entry:
            # entry's first line is the '## v<version>' heading itself - skip it, we already printed the version above.
            body = entry.split("\n", 1)[1].strip() if "\n" in entry else ""
            if body:
                print()
                print(body)


def _print_help(parser: argparse.ArgumentParser, verbose: bool = False) -> None:
    ver = _get_version()
    print(f"mail-utils v{ver} - Copyright (c) Giovanni Pellicciotta\n")
    print("A lightweight, privacy-preserving, local email archive indexing and extraction utility.\n")
    if verbose:
        parser.print_help()
        for name, sub in parser._subcommand_parsers.items():
            print(f"\n{'-' * 60}\nmail-utils {name}\n{'-' * 60}")
            sub.print_help()
    else:
        parser.print_help()
    print("\nExit codes:")
    print("  0  Success")
    print("  1  Runtime error or operation failure")
    print("  2  Invalid command-line arguments")


def _print_full_help(parser: argparse.ArgumentParser) -> None:
    _print_help(parser, verbose=True)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if getattr(args, "version", False) or args.command == "version":
        _print_version(getattr(args, "verbose", False))
        return 0

    if getattr(args, "help", False) or args.command in (None, "help"):
        subcmd = getattr(args, "subcommand", None)
        if subcmd and subcmd in parser._subcommand_parsers:
            parser._subcommand_parsers[subcmd].print_help()
            return 0
        _print_help(parser, verbose=getattr(args, "verbose", False))
        return 0

    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
