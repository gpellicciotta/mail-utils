"""End-to-end tests against a real Thunderbird PCV backup archive.

Skipped entirely when the fixture isn't present: data/personal-email-backup.pcv is gitignored
personal data (see CLAUDE.md) and won't exist in CI, matching the pattern used in test_pst_integration.py.
"""

import mailbox
import tempfile
from pathlib import Path

import pytest

from mail_utils.thunderbird.archive import extract_mbox_to_file, walk_folders
from mail_utils.thunderbird.messages import parse_addresses, parse_attachments, parse_message
from mail_utils.thunderbird.tree import folder_label_id, labels_for_folders

PCV_PATH = Path(__file__).resolve().parent.parent / "data" / "personal-email-backup.pcv"

pytestmark = pytest.mark.skipif(not PCV_PATH.exists(), reason=f"real PCV fixture not present: {PCV_PATH}")


def test_walk_folders_finds_the_known_folder_tree():
    folders = walk_folders(PCV_PATH)
    by_path = {f.path: f for f in folders}
    assert "iceage.anubex.com/INBOX" in by_path
    assert "iceage.anubex.com/Sent Mail" in by_path
    assert "imap.gmail.com/INBOX" in by_path
    assert len(folders) == 11


def test_labels_for_folders_produces_valid_labels():
    folders = walk_folders(PCV_PATH)
    labels = labels_for_folders(folders)
    label_names = {label["name"] for label in labels}
    assert "iceage.anubex.com/INBOX" in label_names
    assert "iceage.anubex.com/Sent Mail" in label_names
    assert "imap.gmail.com/INBOX" in label_names
    assert {"id": folder_label_id("iceage.anubex.com/INBOX"), "name": "iceage.anubex.com/INBOX"} in labels


def test_all_messages_parse_without_error_and_produce_unique_ids():
    folders = walk_folders(PCV_PATH)
    active_folders = [f for f in folders if f.file_size > 0]
    assert len(active_folders) == 3

    counts = {}
    all_ids = set()
    total_messages = 0
    total_addresses = 0
    total_attachments = 0

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        for folder in active_folders:
            temp_mbox = tmp_dir_path / "current.mbox"
            extract_mbox_to_file(PCV_PATH, folder, temp_mbox)
            box = mailbox.mbox(temp_mbox)
            try:
                folder_count = 0
                label_id = folder_label_id(folder.path)
                for raw_msg in box:
                    msg = parse_message(raw_msg, label_id=label_id)
                    addrs = parse_addresses(raw_msg)
                    atts = parse_attachments(raw_msg)

                    all_ids.add(msg["id"])
                    assert msg["id"].startswith("thunderbird:")
                    total_addresses += len(addrs)
                    total_attachments += len(atts)
                    folder_count += 1

                counts[folder.path] = folder_count
                total_messages += folder_count
            finally:
                box.close()
                if temp_mbox.exists():
                    temp_mbox.unlink()

    assert counts["iceage.anubex.com/INBOX"] == 2522
    assert counts["imap.gmail.com/INBOX"] == 2089
    assert counts["iceage.anubex.com/Sent Mail"] == 120
    assert total_messages == 4731
    assert len(all_ids) == 2595
    assert total_addresses > 8000
    assert total_attachments > 300
