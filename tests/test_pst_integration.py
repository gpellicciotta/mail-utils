"""End-to-end tests against a real PST file.

Skipped entirely when the fixture isn't present: data/personal-email-backup.pst is gitignored
personal data (see CLAUDE.md) and won't exist in CI, same reasoning as why gmail_client.py's own
tests never hit the live Gmail API - the hand-rolled [MS-PST] parser in pst/ has no other way to be
exercised against real-world byte layouts, though, so this fixture is what actually caught every
bug documented in docs/pst-support-plan.md's Phase 1-3 write-ups. The specific counts asserted here
were confirmed by hand against this exact file during that work.
"""

from pathlib import Path

import pytest

from mail_utils.outlook.messages import fetch_message, parse_addresses, parse_attachments, parse_message
from mail_utils.outlook.ndb import PSTFile
from mail_utils.outlook.tree import folder_label_id, labels_for_folders, walk_folders

PST_PATH = Path(__file__).resolve().parent.parent / "data" / "personal-email-backup.pst"

pytestmark = pytest.mark.skipif(not PST_PATH.exists(), reason=f"real PST fixture not present: {PST_PATH}")


def test_header_parses_as_unicode_permute_encoded():
    with PSTFile(PST_PATH) as pst:
        assert pst.header.wVer >= 23
        assert pst.header.crypt_method == 1  # NDB_CRYPT_PERMUTE


def test_walk_folders_finds_the_known_folder_tree():
    with PSTFile(PST_PATH) as pst:
        folders = walk_folders(pst)
    by_path = {f.path: f for f in folders}
    assert "Top of Outlook data file/All Mail/Me" in by_path
    assert len(by_path["Top of Outlook data file/All Mail/Me"].message_nids) == 262
    # Every other known folder in this fixture is empty.
    assert sum(len(f.message_nids) for f in folders) == 262


def test_labels_for_folders_skips_the_root_and_ids_by_path():
    with PSTFile(PST_PATH) as pst:
        folders = walk_folders(pst)
    labels = labels_for_folders(folders)
    assert "" not in {label["name"] for label in labels}  # root folder's blank path is excluded
    assert {"id": folder_label_id("Top of Outlook data file/All Mail/Me"), "name": "Top of Outlook data file/All Mail/Me"} in labels


def test_all_messages_parse_without_error_and_produce_unique_ids():
    with PSTFile(PST_PATH) as pst:
        folders = walk_folders(pst)
        all_nids = [nid for f in folders for nid in f.message_nids]
        assert len(all_nids) == 262

        ids = set()
        with_from_address = 0
        with_body = 0
        total_attachments = 0
        for msg_nid in all_nids:
            raw = fetch_message(pst, msg_nid)
            msg = parse_message(raw)
            addrs = parse_addresses(raw)
            atts = parse_attachments(raw)

            ids.add(msg["id"])
            assert msg["id"].startswith("outlook:")
            if any(a["role"] == "from" for a in addrs):
                with_from_address += 1
            if msg["body_text"]:
                with_body += 1
            total_attachments += len(atts)

    assert len(ids) == 262  # no id collisions
    assert with_from_address == 232
    assert with_body == 183
    assert total_attachments == 1060


def test_subject_prefix_marker_is_stripped_cleanly():
    """Regression test for the Subject Prefix decoding bug (see plan doc Phase 3): every decoded
    subject in this fixture used to leak a stray leading control character."""
    with PSTFile(PST_PATH) as pst:
        folders = walk_folders(pst)
        all_nids = [nid for f in folders for nid in f.message_nids]
        for msg_nid in all_nids:
            raw = fetch_message(pst, msg_nid)
            subject = parse_message(raw)["subject"] or ""
            assert not subject or subject[0].isprintable()
