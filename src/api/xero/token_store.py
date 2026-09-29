import json
import os
import time
from pathlib import Path

from src.api.xero.config import STATE_PATH, TOKEN_PATH

_xero_token = None


def _read_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _write_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2))


def save_token(token):
    global _xero_token
    if token and token.get("expires_in") and "expires_at" not in token:
        token = {**token, "expires_at": time.time() + token["expires_in"]}
    _xero_token = token
    payload = _read_json(TOKEN_PATH) or {}
    payload["token"] = token
    _write_json(TOKEN_PATH, payload)


def load_token():
    global _xero_token
    if _xero_token is not None:
        return _xero_token
    payload = _read_json(TOKEN_PATH)
    if not payload:
        return None
    _xero_token = payload.get("token")
    return _xero_token


def save_tenant_id(tenant_id: str):
    payload = _read_json(TOKEN_PATH) or {}
    payload["tenant_id"] = tenant_id
    _write_json(TOKEN_PATH, payload)


def load_tenant_id():
    env_tenant = (os.getenv("XERO_TENANT_ID") or "").strip()
    if env_tenant:
        return env_tenant
    payload = _read_json(TOKEN_PATH)
    if payload:
        return payload.get("tenant_id")
    return None


def save_oauth_state(state: str):
    _write_json(STATE_PATH, {"state": state, "created_at": time.time()})


def verify_oauth_state(state: str | None) -> bool:
    if not state:
        return False
    payload = _read_json(STATE_PATH)
    if not payload:
        return False
    if payload.get("state") != state:
        return False
    if time.time() - payload.get("created_at", 0) > 600:
        return False
    STATE_PATH.unlink(missing_ok=True)
    return True


def token_is_valid(token) -> bool:
    if not token or not token.get("access_token"):
        return False
    expires_at = token.get("expires_at")
    if expires_at is None:
        return True
    return expires_at > time.time() + 60
