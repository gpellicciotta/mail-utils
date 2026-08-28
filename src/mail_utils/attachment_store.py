"""Content-addressed storage for attachment bytes, under `config.ATTACHMENTS_DIR` - one file per
distinct content hash, so identical attachments (e.g. a repeated forwarded logo) are only ever
written once. Deliberately a flat directory (no hash-prefix fan-out): personal-mailbox attachment
counts don't need one, and it keeps `path_for` trivial. Attachment bytes never pass through
SQLite - only the resulting hash is stored in the `attachments` table's `content_sha256` column.
"""

import hashlib
from pathlib import Path

from .config import ATTACHMENTS_DIR


def save(content: bytes) -> str:
    """Write `content` to the store if not already present, and return its sha256 hex digest."""
    digest = hashlib.sha256(content).hexdigest()
    path = path_for(digest)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return digest


def path_for(sha256: str) -> Path:
    return ATTACHMENTS_DIR / sha256


def read(sha256: str) -> bytes:
    return path_for(sha256).read_bytes()
