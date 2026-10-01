import os
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from src.db.database import SessionLocal
from src.db.schema.company import Company
from src.db.schema.oauth_state import OAuthState
from src.db.schema.xero import XeroConnection

_xero_token = None
_active_tenant_id = None
_STATE_TTL = timedelta(minutes=10)
_SDK_TOKEN_KEYS = (
    "access_token",
    "refresh_token",
    "token_type",
    "scope",
    "expires_in",
    "expires_at",
    "id_token",
)


def _normalize_token(token: dict | None) -> dict | None:
    if not token:
        return token
    if token.get("expires_in") and "expires_at" not in token:
        token = {**token, "expires_at": time.time() + token["expires_in"]}
    return token


def sdk_token(token: dict | None) -> dict | None:
    """Keys accepted by xero_python OAuth2Token.update_token."""
    if not token:
        return None
    token = _normalize_token(dict(token))
    payload = {key: token.get(key) for key in _SDK_TOKEN_KEYS}
    payload["token_type"] = payload.get("token_type") or "Bearer"
    payload["scope"] = payload.get("scope") or []
    if payload.get("expires_in") is None:
        payload["expires_in"] = 0
    return payload


def _scope_to_text(scope) -> str | None:
    if scope is None:
        return None
    if isinstance(scope, list):
        return " ".join(scope)
    return str(scope)


def _expires_at_dt(token: dict) -> datetime | None:
    expires_at = token.get("expires_at")
    if expires_at is None:
        return None
    return datetime.fromtimestamp(float(expires_at), tz=timezone.utc)


def _row_to_token(row: XeroConnection) -> dict:
    token = {
        "access_token": row.access_token,
        "refresh_token": row.refresh_token,
        "token_type": row.token_type or "Bearer",
        "scope": (row.scope or "").split(),
    }
    if row.token_expires_at:
        expires_at = row.token_expires_at.timestamp()
        token["expires_at"] = expires_at
        token["expires_in"] = max(0, int(expires_at - time.time()))
    return token


def _apply_token(row: XeroConnection, token: dict) -> None:
    row.access_token = token.get("access_token")
    row.refresh_token = token.get("refresh_token")
    row.token_type = token.get("token_type") or "Bearer"
    row.scope = _scope_to_text(token.get("scope"))
    row.token_expires_at = _expires_at_dt(token)


def _get_connection(db, tenant_id: str | None = None) -> XeroConnection | None:
    tenant_id = (
        tenant_id
        or _active_tenant_id
        or (os.getenv("XERO_TENANT_ID") or "").strip()
        or None
    )
    stmt = select(XeroConnection)
    if tenant_id:
        stmt = stmt.where(XeroConnection.tenant_id == tenant_id)
    else:
        stmt = stmt.order_by(XeroConnection.updated_at.desc())
    return db.execute(stmt).scalars().first()


def save_token(token):
    global _xero_token
    token = sdk_token(_normalize_token(token))
    _xero_token = token
    if not token:
        return
    with SessionLocal() as db:
        row = _get_connection(db)
        if not row:
            return
        _apply_token(row, token)
        db.commit()


def load_token(tenant_id: str | None = None):
    global _xero_token, _active_tenant_id
    if tenant_id is None and _xero_token is not None:
        return sdk_token(_xero_token)
    with SessionLocal() as db:
        row = _get_connection(db, tenant_id)
        if not row or not row.access_token:
            return None
        _active_tenant_id = row.tenant_id
        _xero_token = sdk_token(_row_to_token(row))
        return _xero_token


def save_tenant_id(tenant_id: str):
    global _active_tenant_id
    _active_tenant_id = tenant_id


def load_tenant_id():
    env_tenant = (os.getenv("XERO_TENANT_ID") or "").strip()
    if env_tenant:
        return env_tenant
    if _active_tenant_id:
        return _active_tenant_id
    with SessionLocal() as db:
        row = _get_connection(db)
        return row.tenant_id if row else None


def save_connection(token: dict, tenant_id: str, tenant_name: str | None = None) -> None:
    global _xero_token, _active_tenant_id
    token = sdk_token(_normalize_token(token))
    _xero_token = token
    _active_tenant_id = tenant_id
    name = (tenant_name or "").strip() or tenant_id

    with SessionLocal() as db:
        company = db.execute(
            select(Company).where(Company.xero_tenant_id == tenant_id)
        ).scalar_one_or_none()
        if company is None:
            company = Company(name=name, xero_tenant_id=tenant_id)
            db.add(company)
            db.flush()
        elif tenant_name:
            company.name = name

        row = db.execute(
            select(XeroConnection).where(XeroConnection.tenant_id == tenant_id)
        ).scalar_one_or_none()
        if row is None:
            row = XeroConnection(company_id=company.id, tenant_id=tenant_id)
            db.add(row)
        _apply_token(row, token)
        db.commit()


def clear_cached_token():
    global _xero_token
    _xero_token = None


def clear_tokens():
    global _xero_token
    _xero_token = None
    with SessionLocal() as db:
        rows = db.execute(select(XeroConnection)).scalars().all()
        for row in rows:
            row.access_token = None
            row.refresh_token = None
            row.token_expires_at = None
        db.commit()


def save_oauth_state(state: str):
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        existing = db.get(OAuthState, state)
        if existing:
            existing.expires_at = now + _STATE_TTL
        else:
            db.add(OAuthState(state=state, expires_at=now + _STATE_TTL))
        db.commit()


def verify_oauth_state(state: str | None) -> bool:
    if not state:
        return False
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        row = db.get(OAuthState, state)
        if not row:
            return False
        valid = row.expires_at > now
        db.delete(row)
        db.commit()
        return valid


def token_is_valid(token) -> bool:
    if not token or not token.get("access_token"):
        return False
    expires_at = token.get("expires_at")
    if expires_at is None:
        return True
    return expires_at > time.time() + 60
