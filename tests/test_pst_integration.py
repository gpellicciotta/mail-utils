"""End-to-end integration tests for Outlook PST parsing and importing."""

import argparse
from pathlib import Path

import pytest

from mail_utils import cli
from mail_utils.cli import _run_import_pst
from mail_utils.db import init_db
from mail_utils.outlook.messages import fetch_message, parse_addresses, parse_attachments, parse_message
from mail_utils.outlook.ndb import PSTFile
from mail_utils.outlook.tree import folder_label_id, labels_for_folders, walk_folders

SAMPLE_PST = Path(__file__).resolve().parent / "fixtures" / "sample.pst"
LOCAL_PST = Path(__file__).resolve().parent.parent / "data" / "personal-email-backup.pst"


def test_sample_pst_header():
    with PSTFile(SAMPLE_PST) as pst:
        assert pst.header.wVer >= 23
        assert pst.header.crypt_method in (0, 1)


def test_sample_pst_walk_folders():
    with PSTFile(SAMPLE_PST) as pst:
        folders = walk_folders(pst)
    by_path = {f.path: f for f in folders}
    assert "" in by_path
    assert "Inbox" in by_path
    assert len(by_path["Inbox"].message_nids) == 2


def test_sample_pst_labels_for_folders():
    with PSTFile(SAMPLE_PST) as pst:
        folders = walk_folders(pst)
    labels = labels_for_folders(folders)
    assert "" not in {label["name"] for label in labels}
    assert {"id": folder_label_id("Inbox"), "name": "Inbox"} in labels


def test_sample_pst_all_messages_parse_cleanly():
    with PSTFile(SAMPLE_PST) as pst:
        folders = walk_folders(pst)
        all_nids = [nid for f in folders for nid in f.message_nids]
        assert len(all_nids) == 2

        parsed_messages = []
        for msg_nid in all_nids:
            raw = fetch_message(pst, msg_nid)
            msg = parse_message(raw)
            addrs = parse_addresses(raw)
            atts = parse_attachments(raw)

            assert msg["id"].startswith("outlook:")
            assert msg["subject"] in ("Welcome to Outlook", "Project Quarterly Update")
            assert "example.com" in (msg["sender"] or "")
            parsed_messages.append((msg, addrs, atts))

    assert len(parsed_messages) == 2


def test_sample_pst_cli_import(tmp_path, monkeypatch):
    db_path = tmp_path / "test_pst.db"
    init_db(db_path).close()
    monkeypatch.setattr(cli, "DB_PATH", db_path)

    _run_import_pst(argparse.Namespace(pst_path=str(SAMPLE_PST), db=str(db_path), recursive=False))

    conn = init_db(db_path)
    (msg_count,) = conn.execute("SELECT COUNT(*) FROM messages").fetchone()
    assert msg_count == 2

    (label_count,) = conn.execute("SELECT COUNT(*) FROM labels WHERE name = 'Inbox'").fetchone()
    assert label_count == 1
    conn.close()


@pytest.mark.skipif(not LOCAL_PST.exists(), reason="Local PST fixture not present")
def test_local_pst_messages_and_counts():
    with PSTFile(LOCAL_PST) as pst:
        folders = walk_folders(pst)
        all_nids = [nid for f in folders for nid in f.message_nids]
        assert len(all_nids) == 262
