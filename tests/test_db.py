from mail_utils.db import init_db


def test_init_db_creates_missing_parent_directory(tmp_path):
    db_path = tmp_path / "does" / "not" / "exist" / "gmail.db"
    assert not db_path.parent.exists()

    conn = init_db(db_path)
    conn.close()

    assert db_path.exists()
