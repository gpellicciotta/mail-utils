from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

CREDENTIALS_PATH = BASE_DIR / "credentials.json"
TOKEN_PATH = BASE_DIR / "token.json"
DB_PATH = BASE_DIR / "gmail_index.db"
LOG_DIR = BASE_DIR / "logs"
LOG_PATH = LOG_DIR / "mail_utils.log"

# Read-only scope: this app never sends, modifies, or deletes anything.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
