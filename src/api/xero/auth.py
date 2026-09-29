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
        }
    )
    return f"https://login.xero.com/identity/connect/authorize?{params}", state


def begin_oauth() -> str:
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


def resolve_tenant_id(api_client: ApiClient) -> str:
    tenant_id = token_store.load_tenant_id()
    if tenant_id:
        return tenant_id

    connections = IdentityApi(api_client).get_connections() or []
    for connection in connections:
        if connection.tenant_type == "ORGANISATION":
            token_store.save_tenant_id(connection.tenant_id)
            return connection.tenant_id

    if connections:
        token_store.save_tenant_id(connections[0].tenant_id)
        return connections[0].tenant_id

    raise RuntimeError("No Xero organisation connected. Complete login at /xero/login.")


def get_authenticated_client() -> tuple[ApiClient, str]:
    token = token_store.load_token()
    if not token:
        raise XeroNotConnectedError(
            "Not connected to Xero yet. Complete OAuth login first."
        )

    api_client = _build_api_client()
    oauth2_token = api_client.configuration.oauth2_token
    oauth2_token.update_token(**token)

    if not token_store.token_is_valid(token):
        if not token.get("refresh_token"):
            raise RuntimeError("Xero session expired. Open /xero/login again.")
        api_client.refresh_oauth2_token()

    tenant_id = resolve_tenant_id(api_client)
    return api_client, tenant_id


def complete_oauth_callback(code: str) -> dict:
    token = exchange_code_for_token(code)
    token_store.save_token(token)

    api_client = _build_api_client()
    api_client.configuration.oauth2_token.update_token(**token)
    tenant_id = resolve_tenant_id(api_client)

    return {
        "connected": True,
        "tenant_id": tenant_id,
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

    try:
        api_client, _ = get_authenticated_client()
        connections = IdentityApi(api_client).get_connections() or []
        status["connection_count"] = len(connections)
        if connections and not status["tenant_id"]:
            status["tenant_id"] = connections[0].tenant_id
        status["message"] = "Connected. GET /xero/contacts is ready."
    except RuntimeError as exc:
        status["message"] = str(exc)

    return status
