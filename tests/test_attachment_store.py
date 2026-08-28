import hashlib

from mail_utils import attachment_store


def test_save_returns_stable_sha256_digest(tmp_path):
    attachment_store.configure(tmp_path)
    digest = attachment_store.save(b"hello world")
    assert digest == hashlib.sha256(b"hello world").hexdigest()


def test_save_writes_file_at_path_for_digest(tmp_path):
    attachment_store.configure(tmp_path)
    digest = attachment_store.save(b"content bytes")
    assert attachment_store.path_for(digest).read_bytes() == b"content bytes"


def test_save_identical_content_twice_writes_file_only_once(tmp_path):
    attachment_store.configure(tmp_path)
    digest1 = attachment_store.save(b"same bytes")
    digest2 = attachment_store.save(b"same bytes")
    assert digest1 == digest2
    assert len(list(tmp_path.iterdir())) == 1


def test_save_different_content_writes_distinct_files(tmp_path):
    attachment_store.configure(tmp_path)
    digest1 = attachment_store.save(b"content A")
    digest2 = attachment_store.save(b"content B")
    assert digest1 != digest2
    assert len(list(tmp_path.iterdir())) == 2


def test_read_round_trips_saved_content(tmp_path):
    attachment_store.configure(tmp_path)
    digest = attachment_store.save(b"round trip me")
    assert attachment_store.read(digest) == b"round trip me"


def test_save_creates_missing_attachments_directory(tmp_path):
    missing_dir = tmp_path / "does" / "not" / "exist"
    attachment_store.configure(missing_dir)
    attachment_store.save(b"bytes")
    assert missing_dir.exists()


def test_path_for_raises_a_clear_error_when_not_configured(monkeypatch):
    monkeypatch.setattr(attachment_store, "_attachments_dir", None)
    try:
        attachment_store.path_for("deadbeef")
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
