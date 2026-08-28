"""End-to-end integration tests for Outlook PST parsing and importing."""

import argparse
import struct
from pathlib import Path

import pytest

from mail_utils.cli import _run_import_pst
from mail_utils.db import init_db
from mail_utils.outlook.ltp import PSTProperty
from mail_utils.outlook.messages import (
    PROP_ATTACH_DATA_BINARY,
    PROP_LTP_ROW_ID,
    RawMessage,
    fetch_attachment_content,
    fetch_message,
    parse_addresses,
    parse_attachments,
    parse_message,
)
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


def test_sample_pst_cli_import(tmp_path):
    db_dir = tmp_path / "test_pst"

    _run_import_pst(argparse.Namespace(pst_path=str(SAMPLE_PST), db=str(db_dir), recursive=False))

    conn = init_db(db_dir / "mails.db")
    (msg_count,) = conn.execute("SELECT COUNT(*) FROM messages").fetchone()
    assert msg_count == 2

    (label_count,) = conn.execute("SELECT COUNT(*) FROM labels WHERE name = 'Inbox'").fetchone()
    assert label_count == 1
    conn.close()


def test_sample_pst_cli_import_with_attachments_flag_does_not_crash(tmp_path):
    # sample.pst has no attachments to actually capture content for - this guards the CLI wiring
    # itself (the --with-attachments plumbing into pst_parse_attachments(raw, pst=pst)) rather than
    # real content capture, which needs a PST fixture with an actual attachment (see
    # test_fetch_attachment_content_reads_binary_property above for that logic in isolation).
    db_dir = tmp_path / "test_pst_with_attachments"

    _run_import_pst(argparse.Namespace(pst_path=str(SAMPLE_PST), db=str(db_dir), recursive=False, with_attachments=True))

    conn = init_db(db_dir / "mails.db")
    (msg_count,) = conn.execute("SELECT COUNT(*) FROM messages").fetchone()
    assert msg_count == 2
    conn.close()


@pytest.mark.skipif(not LOCAL_PST.exists(), reason="Local PST fixture not present")
def test_local_pst_messages_and_counts():
    with PSTFile(LOCAL_PST) as pst:
        folders = walk_folders(pst)
        all_nids = [nid for f in folders for nid in f.message_nids]
        assert len(all_nids) == 262


def test_sample_pst_parse_attachments_with_pst_arg_does_not_crash_when_no_attachments():
    # sample.pst carries no attachments at all, so this only exercises "opted in, nothing to fetch" -
    # fetch_attachment_content() itself is covered directly below via a fake PST, since constructing a
    # real attachment object in the hand-rolled sample.pst generator is a separate, larger undertaking.
    with PSTFile(SAMPLE_PST) as pst:
        folders = walk_folders(pst)
        all_nids = [nid for f in folders for nid in f.message_nids]
        for msg_nid in all_nids:
            raw = fetch_message(pst, msg_nid)
            assert parse_attachments(raw, pst=pst) == []


class _FakePSTForAttachmentContent:
    def __init__(self, ref):
        self._ref = ref
        self.read_subnode_calls = []

    def read_subnode(self, sub_bid, nid):
        self.read_subnode_calls.append((sub_bid, nid))
        return self._ref


def test_fetch_attachment_content_reads_binary_property(monkeypatch):
    fake_pst = _FakePSTForAttachmentContent(ref=(111, 222))
    monkeypatch.setattr(
        "mail_utils.outlook.messages.read_property_context",
        lambda pst, bid_data, bid_sub: {PROP_ATTACH_DATA_BINARY: PSTProperty(0x0102, b"file bytes")},
    )
    raw = RawMessage(props={}, bid_sub=999)
    row = {PROP_LTP_ROW_ID: struct.pack("<I", 42)}

    content = fetch_attachment_content(fake_pst, raw, row)

    assert content == b"file bytes"
    assert fake_pst.read_subnode_calls == [(999, 42)]


def test_fetch_attachment_content_returns_none_when_row_id_missing():
    raw = RawMessage(props={}, bid_sub=999)
    assert fetch_attachment_content(_FakePSTForAttachmentContent(ref=None), raw, {}) is None


def test_fetch_attachment_content_returns_none_when_subnode_not_found():
    raw = RawMessage(props={}, bid_sub=999)
    row = {PROP_LTP_ROW_ID: struct.pack("<I", 42)}
    assert fetch_attachment_content(_FakePSTForAttachmentContent(ref=None), raw, row) is None


def test_fetch_attachment_content_returns_none_when_message_has_no_subnode_btree():
    raw = RawMessage(props={}, bid_sub=0)
    row = {PROP_LTP_ROW_ID: struct.pack("<I", 42)}
    assert fetch_attachment_content(_FakePSTForAttachmentContent(ref=(1, 2)), raw, row) is None
