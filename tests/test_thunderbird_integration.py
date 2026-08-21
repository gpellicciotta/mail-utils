"""End-to-end integration tests for Thunderbird archive parsing and importing."""

import argparse
import mailbox
import tempfile
from pathlib import Path

import pytest

from mail_utils import cli
from mail_utils.cli import _run_import_thunderbird
from mail_utils.db import init_db
from mail_utils.thunderbird.archive import extract_mbox_to_file, walk_folders
from mail_utils.thunderbird.messages import parse_message
from mail_utils.thunderbird.tree import folder_label_id, labels_for_folders

SAMPLE_PCV = Path(__file__).resolve().parent / "fixtures" / "sample.pcv"
LOCAL_PCV = Path(__file__).resolve().parent.parent / "data" / "personal-email-backup.pcv"


def test_sample_pcv_walk_folders():
    folders = walk_folders(SAMPLE_PCV)
    by_path = {f.path: f for f in folders}
    assert "Local Folders/Inbox" in by_path
    assert "Local Folders/Archive/2026" in by_path


def test_sample_pcv_labels_for_folders():
    folders = walk_folders(SAMPLE_PCV)
    labels = labels_for_folders(folders)
    label_names = {label["name"] for label in labels}
    assert "Local Folders/Inbox" in label_names
    assert "Local Folders/Archive/2026" in label_names


def test_sample_pcv_all_messages_parse_cleanly():
    folders = walk_folders(SAMPLE_PCV)
    active_folders = [f for f in folders if f.file_size > 0]
    assert len(active_folders) == 2

    all_ids = set()
    total_messages = 0

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        for folder in active_folders:
            temp_mbox = tmp_dir_path / "current.mbox"
            extract_mbox_to_file(SAMPLE_PCV, folder, temp_mbox)
            box = mailbox.mbox(temp_mbox)
            try:
                label_id = folder_label_id(folder.path)
                for raw_msg in box:
                    msg = parse_message(raw_msg, label_id=label_id)
                    all_ids.add(msg["id"])
                    assert msg["id"].startswith("thunderbird:")
                    assert "example.com" in (msg["sender"] or "")
                    total_messages += 1
            finally:
                box.close()
                if temp_mbox.exists():
                    temp_mbox.unlink()

    assert total_messages == 3
    assert len(all_ids) == 3


def test_sample_pcv_cli_import(tmp_path, monkeypatch):
    db_path = tmp_path / "test_tb.db"
    init_db(db_path).close()
    monkeypatch.setattr(cli, "DB_PATH", db_path)

    _run_import_thunderbird(argparse.Namespace(archive_path=str(SAMPLE_PCV), db=str(db_path), recursive=False))

    conn = init_db(db_path)
    (msg_count,) = conn.execute("SELECT COUNT(*) FROM messages").fetchone()
    assert msg_count == 3

    (label_count,) = conn.execute("SELECT COUNT(*) FROM labels WHERE name LIKE 'Local Folders%'").fetchone()
    assert label_count == 2
    conn.close()


@pytest.mark.skipif(not LOCAL_PCV.exists(), reason="Local PCV fixture not present")
def test_local_pcv_messages_and_counts():
    folders = walk_folders(LOCAL_PCV)
    active_folders = [f for f in folders if f.file_size > 0]
    assert len(active_folders) == 3
