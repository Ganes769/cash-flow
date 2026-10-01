from sqlalchemy import select

from src.db.database import SessionLocal
from src.db.schema.company import Company
from src.db.schema.xero_sync import XeroContactRecord, XeroInvoiceRecord, XeroWebhookEvent


def _company_id(db, tenant_id: str):
    company = db.execute(
        select(Company).where(Company.xero_tenant_id == tenant_id)
    ).scalar_one_or_none()
    return company.id if company else None


def record_webhook_events(payload: dict) -> list:
    events = payload.get("events") or []
    ids = []
    with SessionLocal() as db:
        for event in events:
            row = XeroWebhookEvent(
                tenant_id=event.get("tenantId") or "",
                resource_id=event.get("resourceId") or "",
                event_category=(event.get("eventCategory") or "").upper(),
                event_type=(event.get("eventType") or "").upper(),
                resource_url=event.get("resourceUrl"),
                payload=event,
            )
            db.add(row)
            db.flush()
            ids.append(row.id)
        db.commit()
    return ids


def upsert_contact(tenant_id: str, contact: dict, deleted: bool = False) -> None:
    contact_id = contact.get("ContactID") or contact.get("contact_id")
    if not contact_id:
        return
    with SessionLocal() as db:
        company_id = _company_id(db, tenant_id)
        if not company_id:
            return
        row = db.execute(
            select(XeroContactRecord).where(
                XeroContactRecord.tenant_id == tenant_id,
                XeroContactRecord.xero_contact_id == contact_id,
            )
        ).scalar_one_or_none()
        if row is None:
            row = XeroContactRecord(
                company_id=company_id,
                tenant_id=tenant_id,
                xero_contact_id=contact_id,
            )
            db.add(row)
        row.name = contact.get("Name") or contact.get("name")
        row.email = contact.get("EmailAddress") or contact.get("email_address")
        row.payload = contact
        row.deleted = deleted
        db.commit()


def upsert_invoice(tenant_id: str, invoice: dict, deleted: bool = False) -> None:
    invoice_id = invoice.get("InvoiceID") or invoice.get("invoice_id")
    if not invoice_id:
        return
    with SessionLocal() as db:
        company_id = _company_id(db, tenant_id)
        if not company_id:
            return
        row = db.execute(
            select(XeroInvoiceRecord).where(
                XeroInvoiceRecord.tenant_id == tenant_id,
                XeroInvoiceRecord.xero_invoice_id == invoice_id,
            )
        ).scalar_one_or_none()
        if row is None:
            row = XeroInvoiceRecord(
                company_id=company_id,
                tenant_id=tenant_id,
                xero_invoice_id=invoice_id,
            )
            db.add(row)
        row.invoice_number = invoice.get("InvoiceNumber") or invoice.get("invoice_number")
        row.status = invoice.get("Status") or invoice.get("status")
        row.payload = invoice
        row.deleted = deleted
        db.commit()


def mark_event_processed(event_id, error: str | None = None) -> None:
    with SessionLocal() as db:
        row = db.get(XeroWebhookEvent, event_id)
        if not row:
            return
        row.processed = error is None
        row.error = error
        db.commit()
