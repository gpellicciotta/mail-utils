from pathlib import Path

from mail_utils.config import (
    APP_CREDENTIALS_PATH,
    BASE_DIR,
    DATA_DIR,
    LOG_DIR,
    attachments_dir_for,
    db_path_for,
    resolve_account_path,
    resolve_db_dir,
)


def test_base_dir_is_the_actual_project_root():
    # Regression test: BASE_DIR silently broke during the src-layout move
    # (resolved to src/ instead of the repo root) because config.py moved
    # one directory deeper without updating its .parent chain. Anchor it
    # to a file only the real project root has.
    assert (BASE_DIR / "pyproject.toml").exists()
    assert (BASE_DIR / "src" / "mail_utils" / "config.py").exists()


def test_app_credentials_path_lives_under_data_dir():
    assert DATA_DIR == BASE_DIR / "data"
    assert APP_CREDENTIALS_PATH.parent == DATA_DIR
    assert APP_CREDENTIALS_PATH.name == "google-cloud-mail-utils-app-credentials.json"


def test_log_dir_is_top_level_not_under_data():
    assert LOG_DIR == BASE_DIR / "logs"


def test_resolve_account_path_bare_name_resolves_under_data_dir():
    assert resolve_account_path("tester") == DATA_DIR / "tester-account.json"


def test_resolve_account_path_with_separator_is_used_verbatim():
    assert resolve_account_path("a/b/c-account.json") == Path("a/b/c-account.json")


def test_resolve_account_path_with_json_extension_is_used_verbatim():
    assert resolve_account_path("custom.json") == Path("custom.json")


def test_resolve_account_path_none_falls_back_to_default_account():
    assert resolve_account_path(None) == DATA_DIR / "default-account.json"


def test_resolve_db_dir_defaults_to_data_dir():
    assert resolve_db_dir(None) == DATA_DIR


def test_resolve_db_dir_uses_given_path():
    assert resolve_db_dir("some/dir") == Path("some/dir")


def test_db_and_attachments_paths_live_inside_the_resolved_db_dir():
    db_dir = Path("some/dir")
    assert db_path_for(db_dir) == db_dir / "mails.db"
    assert attachments_dir_for(db_dir) == db_dir / "attachments"
