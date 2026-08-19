from mail_utils.config import BASE_DIR


def test_base_dir_is_the_actual_project_root():
    # Regression test: BASE_DIR silently broke during the src-layout move
    # (resolved to src/ instead of the repo root) because config.py moved
    # one directory deeper without updating its .parent chain. Anchor it
    # to a file only the real project root has.
    assert (BASE_DIR / "pyproject.toml").exists()
    assert (BASE_DIR / "src" / "mail_utils" / "config.py").exists()
