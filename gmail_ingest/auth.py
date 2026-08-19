from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .config import CREDENTIALS_PATH, SCOPES, TOKEN_PATH


def get_credentials() -> Credentials:
    """Return valid Gmail API credentials, refreshing or prompting for
    consent only when necessary.

    The browser-based consent screen is only needed once. After that,
    the cached refresh token in token.json is used to get new access
    tokens silently, so scheduled/unattended runs need no browser.
    """
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not CREDENTIALS_PATH.exists():
            raise FileNotFoundError(
                f"Missing {CREDENTIALS_PATH}. Download an OAuth 'Desktop app' "
                "client secret from Google Cloud Console and save it there."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
        creds = flow.run_local_server(port=0)

    TOKEN_PATH.write_text(creds.to_json())
    return creds
