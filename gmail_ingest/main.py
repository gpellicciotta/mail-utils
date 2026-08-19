import logging

from .auth import get_credentials
from .config import DB_PATH, LOG_DIR, LOG_PATH
from .db import get_sync_state, init_db, set_sync_state, upsert_labels, upsert_message
from .gmail_client import (
    HistoryExpiredError,
    build_gmail_service,
    fetch_message,
    get_current_history_id,
    get_profile,
    list_all_message_ids,
    list_changed_message_ids,
    list_labels,
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
        parsed = parse_message(fetch_message(service, msg_id))
        upsert_message(conn, parsed)
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
            parsed = parse_message(fetch_message(service, msg_id))
            upsert_message(conn, parsed)
            count += 1
            if count % PROGRESS_LOG_INTERVAL == 0:
                logger.info("Incremental sync progress: %d messages indexed so far", count)
        new_history_id = get_current_history_id(service)
        set_sync_state(conn, "last_history_id", new_history_id)
        logger.info("Incremental sync complete: %d new messages", count)
    except HistoryExpiredError:
        logger.warning("Stored historyId expired; falling back to full sync")
        _full_sync(service, conn)


def run() -> None:
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


if __name__ == "__main__":
    run()
