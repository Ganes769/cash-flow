import base64
import hmac
import json
from hashlib import sha256

from xero_python.accounting import AccountingApi
from xero_python.exceptions import HTTPStatusException

from src.api.xero.auth import get_authenticated_client
from src.api.xero.config import WEBHOOK_KEY
from src.api.xero import sync as xero_sync


def verify_signature(payload: bytes, signature: str | None) -> bool:
    if not WEBHOOK_KEY or not signature:
        return False
    digest = hmac.new(WEBHOOK_KEY.encode("utf-8"), payload, sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def _first_item(container, attr: str):
    items = getattr(container, attr, None) or []
    return items[0] if items else None


def _apply_event(event: dict) -> None:
    tenant_id = event.get("tenantId")
    resource_id = event.get("resourceId")
    category = (event.get("eventCategory") or "").upper()
    event_type = (event.get("eventType") or "").upper()
    if not tenant_id or not resource_id:
        return

    deleted = event_type == "DELETE"
    if deleted:
        if category == "CONTACT":
            xero_sync.delete_contacts(tenant_id, [resource_id])
        elif category == "INVOICE":
            xero_sync.delete_invoices(tenant_id, [resource_id])
        return

    api_client, _ = get_authenticated_client(tenant_id)
    accounting = AccountingApi(api_client)
    if category == "CONTACT":
        try:
            response = accounting.get_contact(tenant_id, resource_id)
        except HTTPStatusException as exc:
            if exc.status == 404:
                xero_sync.delete_contacts(tenant_id, [resource_id])
                return
            raise
        contact = _first_item(response, "contacts")
        if contact:
            xero_sync.upsert_contact(tenant_id, contact.to_dict())
        return
    if category == "INVOICE":
        try:
            response = accounting.get_invoice(tenant_id, resource_id)
        except HTTPStatusException as exc:
            if exc.status == 404:
                xero_sync.delete_invoices(tenant_id, [resource_id])
                return
            raise
        invoice = _first_item(response, "invoices")
        if invoice:
            xero_sync.upsert_invoice(tenant_id, invoice.to_dict())


def process_payload(payload: dict) -> None:
    event_ids = xero_sync.record_webhook_events(payload)
    events = payload.get("events") or []
    for event_id, event in zip(event_ids, events):
        try:
            _apply_event(event)
            xero_sync.mark_event_processed(event_id)
        except HTTPStatusException as exc:
            xero_sync.mark_event_processed(event_id, error=str(exc))
        except Exception as exc:
            xero_sync.mark_event_processed(event_id, error=str(exc))
