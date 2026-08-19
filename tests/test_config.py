from mail_utils.config import BASE_DIR, CREDENTIALS_PATH, DATA_DIR, DB_PATH, LOG_DIR, TOKEN_PATH


def test_base_dir_is_the_actual_project_root():
    # Regression test: BASE_DIR silently broke during the src-layout move
    # (resolved to src/ instead of the repo root) because config.py moved
    # one directory deeper without updating its .parent chain. Anchor it
    # to a file only the real project root has.
    assert (BASE_DIR / "pyproject.toml").exists()
    assert (BASE_DIR / "src" / "mail_utils" / "config.py").exists()


def test_data_paths_live_under_data_dir():
    assert DATA_DIR == BASE_DIR / "data"
    for path in (CREDENTIALS_PATH, TOKEN_PATH, DB_PATH):
        assert path.parent == DATA_DIR


def test_log_dir_is_top_level_not_under_data():
    assert LOG_DIR == BASE_DIR / "logs"
