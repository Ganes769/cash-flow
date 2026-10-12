from langchain.tools import tool
from sqlalchemy import func, select

from src.db.database import SessionLocal
from src.db.schema.xero_sync import XeroInvoiceRecord


def _payload_value(payload: dict, *keys):
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


@tool
def get_invoice(invoice_number: str) -> dict:
    """Retrieve an exact invoice by invoice number from synced Xero records."""

    number = str(invoice_number or "").strip()
    if not number:
        return {"error": "Invoice number is required"}

    with SessionLocal() as db:
        row = db.execute(
            select(XeroInvoiceRecord).where(
                XeroInvoiceRecord.deleted.is_(False),
                func.lower(XeroInvoiceRecord.invoice_number) == number.lower(),
            )
        ).scalars().first()

    if row is None:
        return {"error": f"Invoice {number} not found"}

    payload = row.payload or {}
    contact = payload.get("contact") or payload.get("Contact") or {}
    return {
        "invoice_number": row.invoice_number,
        "customer": _payload_value(contact, "name", "Name"),
        "email": _payload_value(contact, "email_address", "EmailAddress"),
        "total": _payload_value(payload, "total", "Total"),
        "amount_paid": _payload_value(payload, "amount_paid", "AmountPaid"),
        "amount_due": _payload_value(payload, "amount_due", "AmountDue"),
        "currency": _payload_value(payload, "currency_code", "CurrencyCode") or "GBP",
        "invoice_date": str(_payload_value(payload, "date", "Date") or ""),
        "due_date": str(_payload_value(payload, "due_date", "DueDate") or ""),
        "xero_status": row.status,
    }
