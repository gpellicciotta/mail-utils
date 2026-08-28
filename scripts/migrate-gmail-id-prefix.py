"""One-off migration: prefix every existing `messages.id` (and the `message_addresses`/
`attachments` rows that reference it) with "gmail:", matching the id scheme `gmail_client.py` now
uses (see docs/pst-support-plan.md, Phase 4) so a future Outlook `.pst` import into the same
database - whose rows are prefixed `outlook:` - can never collide with an existing Gmail row.

Every row in an existing `data/mails.db` predates this scheme and is Gmail-sourced, so every
still-unprefixed id gets the "gmail:" prefix; anything already prefixed `gmail:` or `outlook:` is
left untouched, so this is safe to run more than once.

Usage:
    .venv\\Scripts\\python scripts\\migrate-gmail-id-prefix.py [--db PATH]           # dry run
    .venv\\Scripts\\python scripts\\migrate-gmail-id-prefix.py [--db PATH] --apply   # applies it

A timestamped backup copy of the database is made before any write.
"""

import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from _cli_common import build_action_parser, get_mail_utils_version, print_help, print_version

from mail_utils.config import DATA_DIR, db_path_for

DEFAULT_DB_PATH = db_path_for(DATA_DIR)

PROG = "migrate-gmail-id-prefix"
DESCRIPTION = "One-off migration that prefixes existing messages.id rows with 'gmail:' to match the current id scheme."
EXIT_CODES = [(0, "Success"), (1, "Database not found or migration failed"), (2, "Invalid command-line arguments")]
PREFIX = "gmail:"
UNPREFIXED_WHERE = "id NOT LIKE 'gmail:%' AND id NOT LIKE 'outlook:%'"


def _run_migrate(args) -> int:
    db_path = Path(args.db) if args.db else DEFAULT_DB_PATH
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    unprefixed = conn.execute(f"SELECT COUNT(*) FROM messages WHERE {UNPREFIXED_WHERE}").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    print(f"{db_path}: {unprefixed} of {total} messages need the '{PREFIX}' prefix.")

    if unprefixed == 0:
        print("Nothing to do.")
        conn.close()
        return 0
    if not args.apply:
        print("Dry run only - re-run with --apply to write this change.")
        conn.close()
        return 0

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_name(f"{db_path.stem}.pre-gmail-id-prefix-{stamp}{db_path.suffix}")
    shutil.copy2(db_path, backup_path)
    print(f"Backed up to {backup_path}")

    try:
        conn.execute("BEGIN")
        # message_addresses/attachments are keyed by messages.id but don't carry a real foreign
        # key, so they're re-pointed first (while messages.id is still the OLD, unprefixed value
        # the subquery matches against), then messages.id itself is updated last.
        conn.execute(
            f"UPDATE message_addresses SET message_id = ? || message_id "
            f"WHERE message_id IN (SELECT id FROM messages WHERE {UNPREFIXED_WHERE})",
            (PREFIX,),
        )
        conn.execute(
            f"UPDATE attachments SET message_id = ? || message_id "
            f"WHERE message_id IN (SELECT id FROM messages WHERE {UNPREFIXED_WHERE})",
            (PREFIX,),
        )
        conn.execute(f"UPDATE messages SET id = ? || id WHERE {UNPREFIXED_WHERE}", (PREFIX,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Migrated {unprefixed} messages. Backup kept at {backup_path}.")
    return 0


def main() -> int:
    version = get_mail_utils_version()
    parser = build_action_parser(PROG, DESCRIPTION, ["migrate", "version", "help"], "migrate")
    parser.add_argument("--db", help=f"Database to migrate (default: {DEFAULT_DB_PATH})")
    parser.add_argument("--apply", action="store_true", help="Actually write the change (default: dry run)")
    args = parser.parse_args()

    if args.version or args.action == "version":
        print_version(PROG, version)
        return 0
    if args.help or args.action == "help":
        print_help(PROG, version, DESCRIPTION, parser, EXIT_CODES)
        return 0

    return _run_migrate(args)


if __name__ == "__main__":
    sys.exit(main())
