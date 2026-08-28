from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"

APP_CREDENTIALS_PATH = DATA_DIR / "google-cloud-mail-utils-app-credentials.json"
LOG_DIR = BASE_DIR / "logs"
LOG_PATH = LOG_DIR / "mail-utils.log"

DB_FILENAME = "mails.db"
ATTACHMENTS_DIRNAME = "attachments"

# Read-only scope: this app never sends, modifies, or deletes anything.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Write-capable scopes, requested only by `store-in-gmail` - every other command keeps using the
# read-only SCOPES above unchanged. gmail.insert covers messages.import/.insert; gmail.labels is needed
# separately to create a label that doesn't exist yet (gmail.insert alone does not cover labels.create).
STORE_IN_GMAIL_SCOPES = SCOPES + [
    "https://www.googleapis.com/auth/gmail.insert",
    "https://www.googleapis.com/auth/gmail.labels",
]


def resolve_account_path(account: str | None) -> Path:
    """Resolve `--account`'s value (or `prepare-gmail-account`'s `name`) to the account file it
    refers to. Accounts are decoupled from where a run's data lives (see `resolve_db_dir`) - this is
    only about which Gmail account to authenticate as.

    A bare name (no path separator, no `.json` extension) resolves to `<name>-account.json` under
    `DATA_DIR`. Anything else - a path separator or an explicit `.json` extension - is used verbatim
    as the file path instead. Omitting `account` entirely falls back to `DATA_DIR /
    "default-account.json"`: there's nothing magic about the name "default", it's simply the
    conventional fallback picked up automatically whenever an account happens to be set up under it.
    """
    if account is None:
        return DATA_DIR / "default-account.json"
    candidate = Path(account)
    if candidate.suffix == ".json" or len(candidate.parts) > 1:
        return candidate
    return DATA_DIR / f"{account}-account.json"


def resolve_db_dir(db: str | None) -> Path:
    """Resolve `--db`'s value to the directory a run's database and attachment cache live in.
    Independent of `resolve_account_path` - any account can be paired with any `--db` directory."""
    return Path(db) if db else DATA_DIR


def db_path_for(db_dir: Path) -> Path:
    return db_dir / DB_FILENAME


def attachments_dir_for(db_dir: Path) -> Path:
    return db_dir / ATTACHMENTS_DIRNAME
