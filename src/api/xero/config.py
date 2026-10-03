import os

from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("XERO_CLIENT_ID")
CLIENT_SECRET = os.getenv("XERO_CLIENT_SECRET")


def _normalize_redirect_uri(value: str) -> str:
    return value.strip().rstrip("/")


REDIRECT_URI = _normalize_redirect_uri(
    os.getenv("XERO_REDIRECT_URI", "http://127.0.0.1:8000/xero/callback")
)

DEFAULT_SCOPES = (
    "offline_access openid profile email "
    "accounting.contacts.read accounting.invoices.read"
)
SCOPES = os.getenv("XERO_SCOPES", DEFAULT_SCOPES)

LOGIN_PATH = "/xero/login"
LOGIN_URL_PATH = "/xero/login/url"
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5190").strip().rstrip("/")
WEBHOOK_KEY = (os.getenv("XERO_WEBHOOK_KEY") or "").strip()
try:
    SYNC_INTERVAL_SECONDS = max(5, int(os.getenv("XERO_SYNC_INTERVAL_SECONDS", "15")))
except ValueError:
    SYNC_INTERVAL_SECONDS = 15
