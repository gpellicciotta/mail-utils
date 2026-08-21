"""One-off migration: prefix every existing `messages.id` (and the `message_addresses`/
`attachments` rows that reference it) with "gmail:", matching the id scheme `gmail_client.py` now
uses (see docs/pst-support-plan.md, Phase 4) so a future Outlook `.pst` import into the same
database - whose rows are prefixed `outlook:` - can never collide with an existing Gmail row.

Every row in an existing `data/gmail.db` predates this scheme and is Gmail-sourced, so every
still-unprefixed id gets the "gmail:" prefix; anything already prefixed `gmail:` or `outlook:` is
left untouched, so this is safe to run more than once.

Usage:
    .venv\\Scripts\\python scripts\\migrate-gmail-id-prefix.py [--db PATH]           # dry run
    .venv\\Scripts\\python scripts\\migrate-gmail-id-prefix.py [--db PATH] --apply   # applies it

A timestamped backup copy of the database is made before any write.
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from mail_utils.config import DB_PATH

PREFIX = "gmail:"
UNPREFIXED_WHERE = "id NOT LIKE 'gmail:%' AND id NOT LIKE 'outlook:%'"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", help=f"Database to migrate (default: {DB_PATH})")
    parser.add_argument("--apply", action="store_true", help="Actually write the change (default: dry run)")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else DB_PATH
    if not db_path.exists():
        parser.error(f"Database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    unprefixed = conn.execute(f"SELECT COUNT(*) FROM messages WHERE {UNPREFIXED_WHERE}").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    print(f"{db_path}: {unprefixed} of {total} messages need the '{PREFIX}' prefix.")

    if unprefixed == 0:
        print("Nothing to do.")
        conn.close()
        return
    if not args.apply:
        print("Dry run only - re-run with --apply to write this change.")
        conn.close()
        return

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


if __name__ == "__main__":
    main()
