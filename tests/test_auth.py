import json
from datetime import datetime, timedelta, timezone

from mail_utils import auth


def _write_token(path, scopes, expiry=None):
    path.write_text(
        json.dumps(
            {
                "token": "access-token",
                "refresh_token": "refresh-token",
                "client_id": "client-id",
                "client_secret": "client-secret",
                "scopes": scopes,
                "expiry": (expiry or (datetime.now(timezone.utc) + timedelta(hours=1))).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    )


def test_get_credentials_reuses_a_token_that_already_covers_the_requested_scopes(tmp_path):
    account_path = tmp_path / "tester-account.json"
    _write_token(account_path, ["https://www.googleapis.com/auth/gmail.readonly"])

    creds = auth.get_credentials(account_path, ["https://www.googleapis.com/auth/gmail.readonly"])

    assert creds.scopes == ["https://www.googleapis.com/auth/gmail.readonly"]


def test_get_credentials_does_not_silently_reuse_a_token_with_narrower_scopes(monkeypatch, tmp_path):
    # Regression test: Credentials.from_authorized_user_file(path, scopes) treats a passed-in
    # `scopes` list as an override of the token file's actual recorded scopes, not a filter -
    # so a naive coverage check comparing the requested scopes against the (overridden) result
    # always passes, even when the cached token was only ever granted the narrower gmail.readonly
    # scope. Caught via real end-to-end testing of store-in-gmail (T0013), where this let a
    # readonly-only token slip past the check and fail against the live Gmail API with a 403
    # ("Request had insufficient authentication scopes.") instead of prompting for re-consent.
    account_path = tmp_path / "tester-account.json"
    _write_token(account_path, ["https://www.googleapis.com/auth/gmail.readonly"])

    broader_scopes = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.insert",
        "https://www.googleapis.com/auth/gmail.labels",
    ]
    reached_consent_flow = False

    class _FakeFlow:
        def run_local_server(self, port):
            nonlocal reached_consent_flow
            reached_consent_flow = True
            from google.oauth2.credentials import Credentials

            return Credentials(
                token="new-access-token",
                refresh_token="new-refresh-token",
                token_uri="https://oauth2.googleapis.com/token",
                client_id="client-id",
                client_secret="client-secret",
                scopes=broader_scopes,
            )

    app_credentials_path = tmp_path / "google-cloud-mail-utils-app-credentials.json"
    app_credentials_path.write_text("{}")
    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_secrets_file", staticmethod(lambda *a, **k: _FakeFlow()))

    creds = auth.get_credentials(account_path, broader_scopes, app_credentials_path=app_credentials_path)

    assert reached_consent_flow, "a narrower cached token must trigger a fresh consent flow, not be reused"
    assert set(broader_scopes) <= set(creds.scopes)


def test_get_credentials_raises_a_clear_error_when_app_credentials_are_missing(tmp_path):
    account_path = tmp_path / "tester-account.json"
    app_credentials_path = tmp_path / "google-cloud-mail-utils-app-credentials.json"

    try:
        auth.get_credentials(account_path, app_credentials_path=app_credentials_path)
        assert False, "expected FileNotFoundError"
    except FileNotFoundError as e:
        assert str(app_credentials_path) in str(e)
