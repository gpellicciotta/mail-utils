from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .config import CREDENTIALS_PATH, SCOPES, TOKEN_PATH


def get_credentials(scopes: list[str] | None = None) -> Credentials:
    """Return valid Gmail API credentials, refreshing or prompting for
    consent only when necessary.

    The browser-based consent screen is only needed once. After that,
    the cached refresh token in token.json is used to get new access
    tokens silently, so scheduled/unattended runs need no browser.

    `scopes` defaults to the read-only SCOPES every command but
    `store-in-gmail` uses. Passing a broader scope list (e.g. STORE_IN_GMAIL_SCOPES)
    re-runs the consent flow if the cached token doesn't already cover it -
    existing read-only-only usage is unaffected since it never asks for more.
    """
    scopes = scopes if scopes is not None else SCOPES
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), scopes)

    if creds and creds.valid and set(scopes) <= set(creds.scopes or []):
        return creds

    if creds and creds.expired and creds.refresh_token and set(scopes) <= set(creds.scopes or []):
        creds.refresh(Request())
    else:
        if not CREDENTIALS_PATH.exists():
            raise FileNotFoundError(
                f"Missing {CREDENTIALS_PATH}. Download an OAuth 'Desktop app' "
                "client secret from Google Cloud Console and save it there."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), scopes)
        creds = flow.run_local_server(port=0)

    TOKEN_PATH.write_text(creds.to_json())
    return creds
