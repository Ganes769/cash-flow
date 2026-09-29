import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TOKEN_PATH = PROJECT_ROOT / ".xero_token.json"
STATE_PATH = PROJECT_ROOT / ".xero_oauth_state.json"

CLIENT_ID = os.getenv("XERO_CLIENT_ID")
CLIENT_SECRET = os.getenv("XERO_CLIENT_SECRET")


def _normalize_redirect_uri(value: str) -> str:
    return value.strip().rstrip("/")


REDIRECT_URI = _normalize_redirect_uri(
    os.getenv("XERO_REDIRECT_URI", "http://127.0.0.1:8000/xero/callback")
)

DEFAULT_SCOPES = (
    "offline_access openid profile email accounting.contacts.read"
)
SCOPES = os.getenv("XERO_SCOPES", DEFAULT_SCOPES)

LOGIN_PATH = "/xero/login"
LOGIN_URL_PATH = "/xero/login/url"
