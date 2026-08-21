import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ThunderbirdFolder:
    """Represents a logical mail folder within a Thunderbird profile or archive."""

    path: str
    source_identifier: str  # internal zip filename or filesystem path
    file_size: int = 0


def folder_label_id(path: str) -> str:
    """Stable label id derived from the folder's human-readable path."""
    return "thunderbird_folder:" + hashlib.sha1(path.encode("utf-8")).hexdigest()[:16]


def labels_for_folders(folders: list[ThunderbirdFolder]) -> list[dict]:
    """Generate `labels` table rows for every non-empty folder path."""
    seen = set()
    labels = []
    for f in folders:
        if not f.path or f.path in seen:
            continue
        seen.add(f.path)
        labels.append({"id": folder_label_id(f.path), "name": f.path})
    return labels


_SBD_PATTERN = re.compile(r"\.sbd[/\\]", re.IGNORECASE)


def clean_folder_path(raw_path: str | Path) -> str:
    """Transform an internal Thunderbird file path into a clean folder path.

    - Replaces `.sbd/` subfolder container markers with `/`
    - Strips leading `Mail/` or `ImapMail/` prefix
    - Normalizes slashes
    """
    path_str = str(raw_path).replace("\\", "/")

    # Strip leading Mail/ or ImapMail/
    if path_str.startswith("Mail/"):
        path_str = path_str[5:]
    elif path_str.startswith("ImapMail/"):
        path_str = path_str[9:]

    # Replace .sbd/ with /
    cleaned = _SBD_PATTERN.sub("/", path_str)

    # Clean up double slashes and strip
    cleaned = re.sub(r"/+", "/", cleaned).strip("/")
    return cleaned
