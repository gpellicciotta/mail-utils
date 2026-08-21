"""Folder/message tree enumeration - [MS-PST] 2.4.4 (folders) / 2.4.5 (messages).

Walks the folder hierarchy starting at NID_ROOT_FOLDER, using Table Context (ltp.py) for both a
folder's Hierarchy Table (its child folders) and Contents Table (the messages directly inside it).
A folder/message's own NID is not a separate column value - per [MS-PST] 2.4.4.4/2.4.5, a
hierarchy/contents table row's PidTagLtpRowId (0x67f2) *is* the child folder's/message's own NID,
verified against data/personal-email-backup.pst (its "Me" folder, 262 messages, decoded correctly
this way including across a genuinely multi-block Row Matrix).
"""

import struct
from dataclasses import dataclass, field

from .ltp import read_table_context
from .ndb import NID_ROOT_FOLDER, NID_TYPE_CONTENTS_TABLE, NID_TYPE_HIERARCHY_TABLE, PSTFile, make_nid

PROP_DISPLAY_NAME = 0x3001
PROP_LTP_ROW_ID = 0x67F2


@dataclass
class PSTFolder:
    nid: int
    path: str  # "Inbox/Projects" - "" for the root folder itself
    message_nids: list = field(default_factory=list)  # messages directly in this folder, not recursive


def _row_nid(row: dict) -> int | None:
    value = row.get(PROP_LTP_ROW_ID)
    return struct.unpack_from("<I", value, 0)[0] if value else None


def _row_name(row: dict) -> str:
    value = row.get(PROP_DISPLAY_NAME)
    return value.decode("utf-16-le", errors="replace") if value else ""


def walk_folders(pst: PSTFile, root_nid: int = NID_ROOT_FOLDER) -> list:
    """Return every folder in the PST (including empty ones) as a flat list of PSTFolder, via a
    pre-order walk from `root_nid`. The root folder itself is included with path ""."""
    folders = []

    def _walk(folder_nid: int, path: list) -> None:
        idx = folder_nid >> 5

        message_nids = []
        contents_ref = pst.resolve_nid(make_nid(NID_TYPE_CONTENTS_TABLE, idx))
        if contents_ref is not None:
            for row in read_table_context(pst, *contents_ref):
                nid = _row_nid(row)
                if nid is not None:
                    message_nids.append(nid)
        folders.append(PSTFolder(nid=folder_nid, path="/".join(path), message_nids=message_nids))

        hierarchy_ref = pst.resolve_nid(make_nid(NID_TYPE_HIERARCHY_TABLE, idx))
        if hierarchy_ref is None:
            return
        for row in read_table_context(pst, *hierarchy_ref):
            child_nid = _row_nid(row)
            if child_nid is None:
                continue
            name = _row_name(row) or f"(unnamed {child_nid:#x})"
            _walk(child_nid, [*path, name])

    _walk(root_nid, [])
    return folders


def folder_label_id(path: str) -> str:
    """The synthetic labels.id a PST folder maps to - `outlook:Inbox/Projects`, mirroring how
    Gmail's own label ids are opaque strings looked up in the same `labels` table. Same `outlook:`
    prefix as message ids (see pst/messages.py._make_id) so it can't collide with a Gmail label id."""
    return f"outlook:{path}"


def labels_for_folders(folders: list) -> list:
    """Return [{"id": ..., "name": ...}, ...] rows for db.upsert_labels, one per non-empty folder
    path (skips the root folder itself, whose path is "" and isn't a real named folder)."""
    return [{"id": folder_label_id(f.path), "name": f.path} for f in folders if f.path]
