"""End-to-end integration tests for Outlook PST parsing and importing."""

import argparse
import struct
from pathlib import Path

import pytest

from mail_utils.cli import _run_import_pst
from mail_utils.db import init_db
from mail_utils.outlook.ltp import PSTProperty
from mail_utils.outlook.messages import (
    ATTACH_METHOD_EMBEDDED_MSG,
    PROP_ATTACH_DATA_BINARY,
    PROP_ATTACH_DATA_OBJECT,
    PROP_ATTACH_METHOD,
    PROP_LTP_ROW_ID,
    PROP_SUBJECT,
    RawMessage,
    _format_address,
    _parse_transport_headers,
    fetch_attachment_content,
    fetch_embedded_message,
    fetch_message,
    is_embedded_message_attachment,
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


def test_parse_transport_headers_unfolds_raw_line_breaks():
    # PidTagTransportMessageHeaders stores the raw RFC 5322 header block Outlook received the
    # message with, folding (a CRLF followed by whitespace) included. Parser() parses that block
    # under the classic compat32 policy, which leaves the fold's raw CRLF embedded in the header
    # value - _parse_transport_headers must strip it, since a value containing a literal newline
    # later crashes `export --format eml` when re-serialized as a header (found via T0020's local
    # round-trip comparison against real Outlook PST archive data, where long recipient lists are
    # routinely wrapped across several physical lines).
    headers_text = "To: A <a@example.com>,\r\n\tB <b@example.com>\r\nSubject: line one,\r\n line two\r\n\r\n"
    headers = _parse_transport_headers(headers_text)
    assert headers["to"] == "A <a@example.com>,\tB <b@example.com>"
    assert headers["subject"] == "line one, line two"


def test_parse_transport_headers_decodes_rfc2047_encoded_words():
    # Parser() (classic compat32) also leaves an RFC 2047 encoded-word completely undecoded - a real
    # Outlook PST transport header carrying a non-ASCII display name (e.g. "Kevin Crabbé") showed up
    # as the literal, un-decoded "=?iso-8859-1?Q?...?=" token in the stored `sender` field, found via
    # T0020's round-trip comparison (the reimported side happened to decode it correctly, purely as a
    # side effect of the modern email policy import-eml uses, which exposed that the origin's own
    # capture had never decoded it at all).
    headers_text = "From: =?iso-8859-1?Q?Kevin_Crabb=E9?= <kefke-c@hotmail.com>\r\n\r\n"
    headers = _parse_transport_headers(headers_text)
    assert headers["from"] == "Kevin Crabbé <kefke-c@hotmail.com>"


def test_format_address_quotes_unquoted_comma_in_recipient_table_names():
    # _format_address builds a header-style string straight from structured MAPI (name, addr) pairs -
    # used both for the Recipient Table fallback (_recipient_table_summary, messages with no transport
    # headers at all) and the sender PC-property fallback. A real Exchange-resolved "Last, First"
    # display name (e.g. "Kumar, Rajesh") is a bare Python string here, not RFC 5322 text, so it needs
    # quoting before becoming part of a header value - found via T0020's full-scale round-trip
    # comparison against real Outlook PST data: message_addresses (built directly from the same
    # structured pairs, no string-joining involved) was already correct, but the exported .eml's
    # unquoted "To: Kumar, Rajesh <addr>, Hurley, William <addr>" header split back into 4 bogus
    # fragments on reimport.
    assert _format_address("Kumar, Rajesh", "rajesh.kumar@astadia.com") == '"Kumar, Rajesh" <rajesh.kumar@astadia.com>'
    assert _format_address("Giovanni Pellicciotta", "giovanni.pellicciotta@anubex.com") == (
        "Giovanni Pellicciotta <giovanni.pellicciotta@anubex.com>"
    )
    assert _format_address(None, "plain@example.com") == "plain@example.com"
    assert _format_address("Just A Name", None) == "Just A Name"

    joined = ", ".join(
        [
            _format_address("Giovanni Pellicciotta", "giovanni.pellicciotta@anubex.com"),
            _format_address("Kumar, Rajesh", "rajesh.kumar@astadia.com"),
            _format_address("Hurley, William", "william.hurley@astadia.com"),
        ]
    )
    from email.utils import getaddresses

    assert getaddresses([joined]) == [
        ("Giovanni Pellicciotta", "giovanni.pellicciotta@anubex.com"),
        ("Kumar, Rajesh", "rajesh.kumar@astadia.com"),
        ("Hurley, William", "william.hurley@astadia.com"),
    ]


def test_sample_pst_cli_import(tmp_path):
    db_dir = tmp_path / "test_pst"

    _run_import_pst(argparse.Namespace(pst_path=str(SAMPLE_PST), db=str(db_dir), recursive=False))

    conn = init_db(db_dir / "mails.db")
    (msg_count,) = conn.execute("SELECT COUNT(*) FROM messages").fetchone()
    assert msg_count == 2

    (label_count,) = conn.execute("SELECT COUNT(*) FROM labels WHERE name = 'Inbox'").fetchone()
    assert label_count == 1

    # _run_import_pst skips per-message FTS maintenance (update_fts=False, a real, measured bottleneck
    # against a large archive) and rebuilds messages_fts once after the loop instead - this must still
    # leave the index fully populated by the time the command returns, not just eventually correct.
    (fts_count,) = conn.execute("SELECT COUNT(*) FROM messages_fts").fetchone()
    assert fts_count == 2
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
    row = {PROP_LTP_ROW_ID: PSTProperty(0x0003, struct.pack("<I", 42))}

    content = fetch_attachment_content(fake_pst, raw, row)

    assert content == b"file bytes"
    assert fake_pst.read_subnode_calls == [(999, 42)]


def test_fetch_attachment_content_returns_none_when_row_id_missing():
    raw = RawMessage(props={}, bid_sub=999)
    assert fetch_attachment_content(_FakePSTForAttachmentContent(ref=None), raw, {}) is None


def test_fetch_attachment_content_returns_none_when_subnode_not_found():
    raw = RawMessage(props={}, bid_sub=999)
    row = {PROP_LTP_ROW_ID: PSTProperty(0x0003, struct.pack("<I", 42))}
    assert fetch_attachment_content(_FakePSTForAttachmentContent(ref=None), raw, row) is None


def test_fetch_attachment_content_returns_none_when_message_has_no_subnode_btree():
    raw = RawMessage(props={}, bid_sub=0)
    row = {PROP_LTP_ROW_ID: PSTProperty(0x0003, struct.pack("<I", 42))}
    assert fetch_attachment_content(_FakePSTForAttachmentContent(ref=(1, 2)), raw, row) is None


def test_is_embedded_message_attachment():
    assert is_embedded_message_attachment({PROP_ATTACH_METHOD: PSTProperty(0x0003, struct.pack("<i", ATTACH_METHOD_EMBEDDED_MSG))})
    assert not is_embedded_message_attachment({PROP_ATTACH_METHOD: PSTProperty(0x0003, struct.pack("<i", 1))})  # afByValue
    assert not is_embedded_message_attachment({})


class _FakePSTForEmbeddedMessage:
    """`refs` maps (sub_bid, nid) -> the `read_subnode` result for that exact call - mirrors the two
    real hops `fetch_embedded_message` makes (parent message -> attachment's own PC, then attachment's
    own subnode BTree -> the embedded message's own PC), per the real byte-level structure confirmed
    against `data/inputs/anubex-friends-email.pst` while working T0026 (see the task file)."""

    def __init__(self, refs: dict):
        self._refs = refs
        self.read_subnode_calls = []

    def read_subnode(self, sub_bid, nid):
        self.read_subnode_calls.append((sub_bid, nid))
        return self._refs.get((sub_bid, nid))

    def list_subnodes(self, sub_bid):
        return []


def test_fetch_embedded_message_resolves_the_real_two_hop_chain(monkeypatch):
    # Mirrors the real structure: PidTagAttachDataObject (0x3701, PtypObject) on the *attachment's*
    # own PC resolves to an 8-byte descriptor whose first 4 bytes are the embedded message's NID
    # within the attachment's own subnode BTree.
    def fake_read_property_context(pst, bid_data, bid_sub):
        if (bid_data, bid_sub) == (700, 694):  # the attachment's own PC
            return {PROP_ATTACH_DATA_OBJECT: PSTProperty(0x000D, struct.pack("<II", 0x2000E4, 0))}
        if (bid_data, bid_sub) == (684, 674):  # the embedded message's own PC
            return {PROP_SUBJECT: PSTProperty(0x001F, "Fw: hello".encode("utf-16-le"))}
        raise AssertionError(f"unexpected read_property_context({bid_data}, {bid_sub})")

    monkeypatch.setattr("mail_utils.outlook.messages.read_property_context", fake_read_property_context)

    fake_pst = _FakePSTForEmbeddedMessage(
        refs={
            (999, 42): (700, 694),  # parent's subnode BTree -> attachment's own (bidData, bidSub)
            (694, 0x2000E4): (684, 674),  # attachment's subnode BTree -> embedded message's (bidData, bidSub)
        }
    )
    raw = RawMessage(props={}, bid_sub=999)
    row = {PROP_LTP_ROW_ID: PSTProperty(0x0003, struct.pack("<I", 42))}

    embedded = fetch_embedded_message(fake_pst, raw, row)

    assert embedded is not None
    assert embedded.props[PROP_SUBJECT].value.decode("utf-16-le") == "Fw: hello"
    assert fake_pst.read_subnode_calls == [(999, 42), (694, 0x2000E4)]


def test_fetch_embedded_message_returns_none_when_row_id_missing():
    raw = RawMessage(props={}, bid_sub=999)
    assert fetch_embedded_message(_FakePSTForEmbeddedMessage(refs={}), raw, {}) is None


def test_fetch_embedded_message_returns_none_when_attachment_subnode_not_found():
    raw = RawMessage(props={}, bid_sub=999)
    row = {PROP_LTP_ROW_ID: PSTProperty(0x0003, struct.pack("<I", 42))}
    assert fetch_embedded_message(_FakePSTForEmbeddedMessage(refs={}), raw, row) is None


def test_fetch_embedded_message_returns_none_when_no_data_object_property(monkeypatch):
    monkeypatch.setattr("mail_utils.outlook.messages.read_property_context", lambda pst, bid_data, bid_sub: {})
    fake_pst = _FakePSTForEmbeddedMessage(refs={(999, 42): (700, 694)})
    raw = RawMessage(props={}, bid_sub=999)
    row = {PROP_LTP_ROW_ID: PSTProperty(0x0003, struct.pack("<I", 42))}
    assert fetch_embedded_message(fake_pst, raw, row) is None


def test_fetch_embedded_message_returns_none_when_embedded_subnode_not_found(monkeypatch):
    monkeypatch.setattr(
        "mail_utils.outlook.messages.read_property_context",
        lambda pst, bid_data, bid_sub: {PROP_ATTACH_DATA_OBJECT: PSTProperty(0x000D, struct.pack("<II", 0x2000E4, 0))},
    )
    fake_pst = _FakePSTForEmbeddedMessage(refs={(999, 42): (700, 694)})  # no entry for (694, 0x2000E4)
    raw = RawMessage(props={}, bid_sub=999)
    row = {PROP_LTP_ROW_ID: PSTProperty(0x0003, struct.pack("<I", 42))}
    assert fetch_embedded_message(fake_pst, raw, row) is None
