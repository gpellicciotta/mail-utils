from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .config import APP_CREDENTIALS_PATH, SCOPES


def get_credentials(
    account_path: Path,
    scopes: list[str] | None = None,
    app_credentials_path: Path = APP_CREDENTIALS_PATH,
) -> Credentials:
    """Return valid Gmail API credentials for one account, refreshing or prompting for consent only
    when necessary.

    `account_path` is the account's own token file (see `config.resolve_account_path`) - every
    caller must say which account it means to authenticate as, there is no implicit default here.
    `app_credentials_path` is the shared OAuth *client* secret (one per mail-utils installation, not
    per account); it only needs to be provided once and is reused across every account.

    The browser-based consent screen is only needed once per account. After that, the cached refresh
    token in `account_path` is used to get new access tokens silently, so scheduled/unattended runs
    need no browser.

    `scopes` defaults to the read-only SCOPES every command but `store-in-gmail` uses. Passing a
    broader scope list (e.g. STORE_IN_GMAIL_SCOPES) re-runs the consent flow if the cached token
    doesn't already cover it - existing read-only-only usage is unaffected since it never asks for
    more.
    """
    scopes = scopes if scopes is not None else SCOPES
    creds = None
    if account_path.exists():
        # Deliberately omit `scopes` here: from_authorized_user_file() treats a passed-in
        # scopes list as an override, replacing whatever the token file actually recorded -
        # which would make the coverage check below always pass regardless of what was
        # really granted. Reading the file's real scopes is the whole point of the check.
        creds = Credentials.from_authorized_user_file(str(account_path))

    if creds and creds.valid and set(scopes) <= set(creds.scopes or []):
        return creds

    refreshed = False
    if creds and creds.expired and creds.refresh_token and set(scopes) <= set(creds.scopes or []):
        try:
            creds.refresh(Request())
            refreshed = True
        except RefreshError:
            # The cached refresh token itself has been revoked or expired server-side (e.g. after
            # 6 months of inactivity, or the user revoked access in their Google Account) - not
            # something a retry can fix. Fall through to a fresh interactive consent instead of
            # crashing, same as if account_path had never existed.
            pass

    if not refreshed:
        if not app_credentials_path.exists():
            raise FileNotFoundError(
                f"Missing {app_credentials_path}. Download an OAuth 'Desktop app' "
                "client secret from Google Cloud Console and save it there."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(app_credentials_path), scopes)
        creds = flow.run_local_server(port=0)

    account_path.parent.mkdir(parents=True, exist_ok=True)
    account_path.write_text(creds.to_json())
    return creds
