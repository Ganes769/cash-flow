import secrets
import time
from urllib.parse import urlencode

import httpx
from xero_python.api_client import ApiClient, Configuration
from xero_python.api_client.oauth2 import OAuth2Token
from xero_python.identity import IdentityApi

from src.api.xero.config import (
    CLIENT_ID,
    CLIENT_SECRET,
    LOGIN_PATH,
    LOGIN_URL_PATH,
    REDIRECT_URI,
    SCOPES,
)
from src.api.xero.exceptions import XeroNotConnectedError
from src.api.xero import token_store


def build_authorize_url() -> tuple[str, str]:
    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError("XERO_CLIENT_ID and XERO_CLIENT_SECRET must be set.")
    state = secrets.token_urlsafe(32)
    params = urlencode(
        {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "state": state,
            "prompt": "consent",
        }
    )
    return f"https://login.xero.com/identity/connect/authorize?{params}", state


def _revoke_existing_connections() -> None:
    token = token_store.load_token()
    if not token or not token_store.token_is_valid(token):
        return
    try:
        api_client = _build_api_client()
        api_client.configuration.oauth2_token.update_token(**token_store.sdk_token(token))
        identity = IdentityApi(api_client)
        for connection in identity.get_connections() or []:
            identity.delete_connection(connection.id)
        token_store.clear_tokens()
    except Exception:
        token_store.clear_cached_token()


def begin_oauth() -> str:
    _revoke_existing_connections()
    authorize_url, state = build_authorize_url()
    token_store.save_oauth_state(state)
    return authorize_url


def exchange_code_for_token(code: str) -> dict:
    response = httpx.post(
        "https://identity.xero.com/connect/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
        auth=(CLIENT_ID, CLIENT_SECRET),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Token exchange failed ({response.status_code}): {response.text}"
        )
    token = response.json()
    scope = token.get("scope")
    if isinstance(scope, str):
        token["scope"] = scope.split()
    token["expires_at"] = time.time() + token.get("expires_in", 0)
    return token


def _build_api_client() -> ApiClient:
    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError("XERO_CLIENT_ID and XERO_CLIENT_SECRET must be set.")
    return ApiClient(
        Configuration(
            debug=False,
            oauth2_token=OAuth2Token(
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET,
            ),
        ),
        oauth2_token_saver=token_store.save_token,
        oauth2_token_getter=token_store.load_token,
    )


def _pick_organisation(api_client: ApiClient):
    connections = IdentityApi(api_client).get_connections() or []
    chosen = next(
        (connection for connection in connections if connection.tenant_type == "ORGANISATION"),
        connections[0] if connections else None,
    )
    if not chosen:
        raise RuntimeError(
            "No Xero organisation connected. Complete login at /xero/login."
        )
    return chosen


def resolve_tenant_id(api_client: ApiClient) -> str:
    tenant_id = token_store.load_tenant_id()
    if tenant_id:
        return tenant_id

    chosen = _pick_organisation(api_client)
    token_store.save_tenant_id(chosen.tenant_id)
    return chosen.tenant_id


def get_authenticated_client(tenant_id: str | None = None) -> tuple[ApiClient, str]:
    if tenant_id:
        token_store.save_tenant_id(tenant_id)
        token_store.clear_cached_token()
    token = token_store.load_token(tenant_id)
    if not token:
        raise XeroNotConnectedError(
            "Not connected to Xero yet. Complete OAuth login first."
        )

    api_client = _build_api_client()
    oauth2_token = api_client.configuration.oauth2_token
    oauth2_token.update_token(**token_store.sdk_token(token))

    if not token_store.token_is_valid(token):
        if not token.get("refresh_token"):
            raise RuntimeError("Xero session expired. Open /xero/login again.")
        api_client.refresh_oauth2_token()

    resolved = resolve_tenant_id(api_client)
    return api_client, tenant_id or resolved


def complete_oauth_callback(code: str) -> dict:
    token = exchange_code_for_token(code)
    token_store.save_token(token)

    api_client = _build_api_client()
    api_client.configuration.oauth2_token.update_token(**token_store.sdk_token(token))
    chosen = _pick_organisation(api_client)

    token_store.save_connection(
        token,
        tenant_id=chosen.tenant_id,
        tenant_name=getattr(chosen, "tenant_name", None),
    )
    from src.api.xero.realtime import start_sync

    start_sync(full=True)

    return {
        "connected": True,
        "tenant_id": chosen.tenant_id,
        "scopes": token.get("scope"),
    }


def get_oauth_setup() -> dict:
    return {
        "client_id_prefix": (CLIENT_ID or "")[:8],
        "redirect_uri": REDIRECT_URI,
        "redirect_uri_alternate_localhost": REDIRECT_URI.replace(
            "127.0.0.1", "localhost"
        ),
            "xero_developer_steps": [
                "Open https://developer.xero.com/app/manage",
                "Open your Web app (Client ID must match .env)",
                "Configuration → OAuth 2.0 redirect URIs",
                f"Add this URI exactly (copy/paste): {REDIRECT_URI}",
                "Scopes: enable accounting.contacts.read AND accounting.invoices.read (granular), then save",
                "Webhooks → Delivery URL: https://YOUR_PUBLIC_HOST/xero/webhooks",
                "Copy the webhook key into XERO_WEBHOOK_KEY, then click Intent to receive",
                "Save the app, wait ~1 minute, then retry /xero/login",
            ],
    }


def get_connection_status() -> dict:
    status = {
        "connected": False,
        "credentials_loaded": bool(CLIENT_ID and CLIENT_SECRET),
        "redirect_uri": REDIRECT_URI,
        "scopes": SCOPES,
        "tenant_id": token_store.load_tenant_id(),
        "token_valid": False,
        "connection_count": 0,
        "login_url": LOGIN_PATH,
        "login_url_api": LOGIN_URL_PATH,
        "message": "",
    }

    if not status["credentials_loaded"]:
        status["message"] = "Set XERO_CLIENT_ID and XERO_CLIENT_SECRET in .env"
        return status

    token = token_store.load_token()
    if not token:
        status["message"] = (
            "Not connected. Open /xero/login in the browser, or GET /xero/login/url "
            "and open authorize_url in a new tab."
        )
        return status

    status["connected"] = True
    status["token_valid"] = token_store.token_is_valid(token)
    if status["tenant_id"]:
        status["connection_count"] = 1

    if status["token_valid"]:
        status["message"] = "Connected. GET /xero/contacts and GET /xero/invoices are ready."
    else:
        status["message"] = "Xero session expired. Open /xero/login again."

    return status
