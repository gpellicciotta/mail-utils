"""Content-addressed storage for attachment bytes, under whichever directory `configure()` was last
called with (see `config.attachments_dir_for` - one per `--db` directory, resolved once per CLI
run) - one file per distinct content hash, so identical attachments (e.g. a repeated forwarded logo)
are only ever written once. Deliberately a flat directory (no hash-prefix fan-out): personal-mailbox
attachment counts don't need one, and it keeps `path_for` trivial. Attachment bytes never pass through
SQLite - only the resulting hash is stored in the `attachments` table's `content_sha256` column.
"""

import hashlib
from pathlib import Path

_attachments_dir: Path | None = None


def configure(attachments_dir: Path) -> None:
    """Set the directory `save`/`read`/`path_for` operate under for the rest of this process. Called
    once per CLI run (see `cli.py::_resolve_db_path`), before anything touches attachment content."""
    global _attachments_dir
    _attachments_dir = attachments_dir


def save(content: bytes) -> str:
    """Write `content` to the store if not already present, and return its sha256 hex digest."""
    digest = hashlib.sha256(content).hexdigest()
    path = path_for(digest)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return digest


def path_for(sha256: str) -> Path:
    if _attachments_dir is None:
        raise RuntimeError("attachment_store.configure() must be called before use")
    return _attachments_dir / sha256


def read(sha256: str) -> bytes:
    return path_for(sha256).read_bytes()
