from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"

CREDENTIALS_PATH = DATA_DIR / "credentials.json"
TOKEN_PATH = DATA_DIR / "token.json"
DB_PATH = DATA_DIR / "gmail.db"
ATTACHMENTS_DIR = DATA_DIR / "attachments"
LOG_DIR = BASE_DIR / "logs"
LOG_PATH = LOG_DIR / "mail-utils.log"

# Read-only scope: this app never sends, modifies, or deletes anything.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Write-capable scopes, requested only by `store-in-gmail` - every other command keeps using the
# read-only SCOPES above unchanged. gmail.insert covers messages.import/.insert; gmail.labels is needed
# separately to create a label that doesn't exist yet (gmail.insert alone does not cover labels.create).
STORE_IN_GMAIL_SCOPES = SCOPES + [
    "https://www.googleapis.com/auth/gmail.insert",
    "https://www.googleapis.com/auth/gmail.labels",
]
