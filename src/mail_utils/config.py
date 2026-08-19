from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"

CREDENTIALS_PATH = DATA_DIR / "credentials.json"
TOKEN_PATH = DATA_DIR / "token.json"
DB_PATH = DATA_DIR / "gmail.db"
LOG_DIR = BASE_DIR / "logs"
LOG_PATH = LOG_DIR / "mail-utils.log"

# Read-only scope: this app never sends, modifies, or deletes anything.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
