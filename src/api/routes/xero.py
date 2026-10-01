import json
import logging
import threading
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select

from src.api.xero.auth import (
    begin_oauth,
    complete_oauth_callback,
    get_connection_status,
    get_oauth_setup,
)
from src.api.xero.config import FRONTEND_ORIGIN, LOGIN_PATH, LOGIN_URL_PATH, WEBHOOK_KEY
from src.api.xero.contacts import fetch_contacts, refresh_synced_contacts
from src.api.xero.invoices import fetch_invoices, refresh_synced_invoices
from src.api.xero.exceptions import XeroNotConnectedError
from src.api.xero.realtime import last_sync_status, run_sync, start_sync
from src.api.xero import token_store
from src.api.xero.webhooks import process_payload, verify_signature
from src.db.database import SessionLocal
from src.db.schema.xero_sync import XeroContactRecord, XeroInvoiceRecord, XeroWebhookEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/xero", tags=["Xero"])


def _not_connected_response(exc: XeroNotConnectedError) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={
            "message": str(exc),
            "login_url": LOGIN_PATH,
            "login_url_api": LOGIN_URL_PATH,
        },
    )


@router.get("/login")
def login():
    """Browser: redirects to Xero. Do not call from Swagger (use GET /xero/login/url)."""
    try:
        authorize_url = begin_oauth()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return RedirectResponse(authorize_url, status_code=302)


@router.post("/webhooks")
async def xero_webhooks(request: Request):
    payload = await request.body()
    signature = request.headers.get("x-xero-signature")
    if not WEBHOOK_KEY or not verify_signature(payload, signature):
        raise HTTPException(status_code=401, detail="Invalid Xero webhook signature")
    try:
        body = json.loads(payload.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        body = {}
    threading.Thread(target=process_payload, args=(body,), daemon=True).start()
    return Response(status_code=200)


@router.get("/login/url")
def login_url():
    """Swagger-safe: returns authorize_url to open in a browser tab."""
    try:
        authorize_url = begin_oauth()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "authorize_url": authorize_url,
        "instruction": "Paste authorize_url into a new browser tab.",
    }


def _app_redirect(path: str = "/login/xero", error: str | None = None) -> RedirectResponse:
    url = f"{FRONTEND_ORIGIN}{path}"
    if error:
        url = f"{url}?xero_error={error}"
    return RedirectResponse(url, status_code=302)


def _wants_html(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    first = accept.split(",")[0].strip()
    return first.startswith("text/html")


@router.get("/callback")
def oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error:
        return _app_redirect("/login", error=error)
    if not code:
        return _app_redirect("/login", error="missing_code")
    if not token_store.verify_oauth_state(state):
        # State was issued by another host (e.g. Render). Do not consume the code.
        query = urlencode({"code": code, "state": state or ""})
        return RedirectResponse(f"{FRONTEND_ORIGIN}/login/xero?{query}", status_code=302)
    try:
        complete_oauth_callback(code)
    except RuntimeError:
        return _app_redirect("/login", error="token_exchange_failed")
    return _app_redirect("/login/xero")


@router.get("/status")
def status(request: Request):
    payload = get_connection_status()
    payload["last_sync"] = last_sync_status()
    if _wants_html(request):
        if payload.get("connected") and payload.get("token_valid"):
            return _app_redirect("/login/xero")
        return _app_redirect("/login")
    return payload


@router.get("/setup")
def oauth_setup():
    return get_oauth_setup()


@router.get("/contacts")
def get_contacts(page: int = 1, page_size: int = 100):
    try:
        return fetch_contacts(page=page, page_size=page_size)
    except XeroNotConnectedError as exc:
        raise _not_connected_response(exc) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/invoices")
def get_invoices(page: int = 1, page_size: int = 100):
    try:
        return fetch_invoices(page=page, page_size=page_size)
    except XeroNotConnectedError as exc:
        raise _not_connected_response(exc) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/sync")
def trigger_sync(full: bool = False, wait: bool = False):
    if wait:
        try:
            return run_sync(full=full)
        except XeroNotConnectedError as exc:
            raise _not_connected_response(exc) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    start_sync(full=full)
    return {"status": "started", "mode": "full" if full else "changed"}


@router.get("/synced/contacts")
def synced_contacts(refresh: bool = False):
    if refresh:
        try:
            refresh_synced_contacts()
        except (XeroNotConnectedError, RuntimeError, Exception):
            logger.exception("Contact refresh failed")
    with SessionLocal() as db:
        rows = db.execute(
            select(XeroContactRecord)
            .where(XeroContactRecord.deleted.is_(False))
            .order_by(XeroContactRecord.updated_at.desc())
        ).scalars().all()
        return {
            "count": len(rows),
            "contacts": [
                {
                    "id": str(row.xero_contact_id),
                    "name": row.name,
                    "email": row.email,
                    "deleted": row.deleted,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    "payload": row.payload,
                }
                for row in rows
            ],
        }


@router.get("/synced/invoices")
def synced_invoices(refresh: bool = False):
    if refresh:
        try:
            refresh_synced_invoices()
        except (XeroNotConnectedError, RuntimeError, Exception):
            logger.exception("Invoice refresh failed")
    with SessionLocal() as db:
        rows = db.execute(
            select(XeroInvoiceRecord)
            .where(XeroInvoiceRecord.deleted.is_(False))
            .order_by(XeroInvoiceRecord.updated_at.desc())
        ).scalars().all()
        return {
            "count": len(rows),
            "invoices": [
                {
                    "id": str(row.xero_invoice_id),
                    "invoice_number": row.invoice_number,
                    "status": row.status,
                    "deleted": row.deleted,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    "payload": row.payload,
                }
                for row in rows
            ],
        }


@router.get("/webhooks/events")
def webhook_events(limit: int = 50):
    with SessionLocal() as db:
        rows = db.execute(
            select(XeroWebhookEvent)
            .order_by(XeroWebhookEvent.created_at.desc())
            .limit(limit)
        ).scalars().all()
        return {
            "count": len(rows),
            "events": [
                {
                    "id": str(row.id),
                    "tenant_id": row.tenant_id,
                    "resource_id": row.resource_id,
                    "event_category": row.event_category,
                    "event_type": row.event_type,
                    "processed": row.processed,
                    "error": row.error,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ],
        }
